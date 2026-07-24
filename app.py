import sqlite3
import requests
import time
import json
from base64 import b64encode
from datetime import datetime, timedelta
from decimal import Decimal
from flask import Flask, render_template, request, redirect, url_for, jsonify
from update_job_types import update_job_types, update_job_addresses, update_pickup_dates, PARSE_ERRORS
from datetime_parser import events_from_install_removal, parse_install_removal
from ollama_client import parse_datetimes_with_ollama
from timesheets import allocate_staff, summarise_rostered_vs_paid
from import_timesheets import import_timesheets_if_present
from roster import (
    get_aliases,
    get_roster,
    list_timesheet_employees,
    refresh_aliases,
    refresh_roster,
    suggest_employee,
    update_aliases,
)
import logging
from threading import Thread, Lock

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("performance.log"),
        logging.StreamHandler()
    ]
)

# Global variable to track sync status
sync_status = {"ongoing": False, "last_sync_time": None, "error": None}
sync_lock = Lock()
sync_complete = False
report_jobs = {}
report_jobs_lock = Lock()

# API Setup
API_URL = "http://api.fieldmagic.co/jobs"
CUSTOMER_INVOICES_API_URL = "https://api.fieldmagic.co/customer_invoices"
username = "c3d1beb4687f6a20"
password = "310b7da2d2fe630739fa6a12"

# Flask Setup
app = Flask(__name__)

def format_datetime_label(value):
    """Format an ISO datetime string for display, e.g. 'Sun 29 Jun 2025, 9:00am'."""
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return value
    time_label = parsed.strftime("%I:%M%p").lstrip("0").lower()
    return f"{parsed.strftime('%a %d %b %Y')}, {time_label}"

def count_events_of_type(events, event_type):
    return sum(1 for event in (events or []) if event.get("type") == event_type)

def extra_events_title(events, event_type, primary_datetime):
    """Tooltip listing the non-primary events of a type."""
    others = [
        event
        for event in (events or [])
        if event.get("type") == event_type and event.get("datetime") != primary_datetime
    ]
    if not others:
        return ""
    parts = []
    for event in others:
        label = (event.get("label") or event_type).strip()
        when = format_datetime_label(event.get("datetime")) or event.get("datetime") or ""
        parts.append(f"{label}: {when}" if when else label)
    return " | ".join(parts)

@app.template_filter("datetime_label")
def datetime_label_filter(value):
    return format_datetime_label(value)

@app.template_filter("event_extra_count")
def event_extra_count_filter(events, event_type):
    total = count_events_of_type(events, event_type)
    return max(total - 1, 0)

@app.template_filter("event_extra_title")
def event_extra_title_filter(events, event_type, primary_datetime):
    return extra_events_title(events, event_type, primary_datetime)

# Database Initialization
DB_NAME = "jobs_cache.db"
REPORT_PERIODS = {
    "fy25": {
        "report_key": "fy25-report",
        "report_title": "FY25 Report",
        "start_date": datetime(2024, 7, 1).date(),
        "end_date": datetime(2025, 6, 30).date(),
    },
    "fy26": {
        "report_key": "fy26-report",
        "report_title": "FY26 Report",
        "start_date": datetime(2025, 7, 1).date(),
        "end_date": datetime(2026, 6, 30).date(),
    },
}

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            job_number TEXT PRIMARY KEY,
            job_summary TEXT,
            job_location TEXT,
            last_modified TIMESTAMP,
            job_type TEXT,
            job_date TEXT,
            arrival_time TEXT,
            removal_time TEXT,
            priority TEXT,
            due_date TEXT,
            status TEXT,
            date_completed TIMESTAMP,
            id TEXT
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS invoice_report_cache (
            report_key TEXT PRIMARY KEY,
            fetched_at TIMESTAMP,
            payload TEXT
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS invoice_detail_cache (
            invoice_id TEXT PRIMARY KEY,
            fetched_at TIMESTAMP,
            payload TEXT
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS invoice_datetime_cache (
            invoice_id TEXT PRIMARY KEY,
            install_datetime TEXT,
            removal_datetime TEXT,
            source TEXT,
            fetched_at TIMESTAMP,
            events TEXT
        )
        """)
        cursor.execute("PRAGMA table_info(jobs)")
        columns = {column[1] for column in cursor.fetchall()}
        if "id" not in columns:
            cursor.execute("ALTER TABLE jobs ADD COLUMN id TEXT")
            logging.info("Added missing 'id' column to jobs table.")
        cursor.execute("PRAGMA table_info(invoice_datetime_cache)")
        datetime_columns = {column[1] for column in cursor.fetchall()}
        if "events" not in datetime_columns:
            cursor.execute("ALTER TABLE invoice_datetime_cache ADD COLUMN events TEXT")
            logging.info("Added missing 'events' column to invoice_datetime_cache table.")
        conn.commit()

# Encrypting FieldMagic Username & Password (API Key and Secret)
def basic_auth(username, password):
    token = b64encode(f"{username}:{password}".encode('utf-8')).decode("ascii")
    return f'Basic {token}'

def api_headers():
    return {
        'Authorization': basic_auth(username, password),
        'Content-Type': 'application/json',
        'Client-Id': 'b48698b2-d589-4b64-af1f-4482e7fbe599',
    }

# Fetch Data from API with Pagination
def fetch_jobs(last_modified=None):
    start_time = time.time() # Start timing
    headers = api_headers()
    params = {}
    if last_modified:
        params["last_modified"] = last_modified

    all_jobs = []
    next_token = None

    while True:
        if next_token:
            params["next_token"] = next_token

        response = requests.get(API_URL, headers=headers, params=params)

        if response.status_code != 200:
            logging.error(f"Failed to fetch jobs: {response.status_code} {response.text}")
            break

        response_data = response.json()
        jobs = response_data.get("data", [])

        # Filter out jobs that have a completed_date
        filtered_jobs = [job for job in jobs if not job.get("date_completed")]

        all_jobs.extend(filtered_jobs)

        next_token = response_data.get("next_token")
        if not next_token:
            break
    end_time=time.time()
    logging.info(f"API call completed in {end_time - start_time:.2f} seconds")
    return all_jobs

def parse_api_datetime(value):
    if not value:
        return None
    return datetime.fromisoformat(value)

def format_date_label(value):
    return f"{value.day} {value.strftime('%B %Y')}"

def fetch_invoices_for_period(start_date, end_date, progress_callback=None):
    params = {"date_invoice": start_date.isoformat()}
    invoices = []
    next_token = None
    api_call_count = 0

    while True:
        if next_token:
            params["next_token"] = next_token

        api_call_count += 1
        if progress_callback:
            progress_callback(
                15,
                f"Invoice data API call {api_call_count} in progress"
            )

        response = requests.get(CUSTOMER_INVOICES_API_URL, headers=api_headers(), params=params, timeout=30)
        if response.status_code != 200:
            raise RuntimeError(f"Failed to fetch customer invoices: {response.status_code} {response.text}")

        response_data = response.json()
        for invoice in response_data.get("data", []):
            invoice_datetime = parse_api_datetime(invoice.get("date_invoice"))
            if not invoice_datetime:
                continue

            invoice_date = invoice_datetime.date()
            if start_date <= invoice_date <= end_date:
                invoices.append(invoice)

        next_token = response_data.get("next_token")
        if not next_token:
            break

    return invoices

def get_cached_invoice_report(report_key):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT fetched_at, payload FROM invoice_report_cache WHERE report_key = ?",
            (report_key,)
        )
        row = cursor.fetchone()

    if not row:
        return None, None

    fetched_at = datetime.fromisoformat(row[0])
    invoices = json.loads(row[1])
    return invoices, fetched_at

def cache_invoice_report(report_key, invoices, fetched_at):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO invoice_report_cache (report_key, fetched_at, payload)
            VALUES (?, ?, ?)
        """, (report_key, fetched_at.isoformat(), json.dumps(invoices)))
        conn.commit()

def get_cached_invoice_detail(invoice_id):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT fetched_at, payload FROM invoice_detail_cache WHERE invoice_id = ?",
            (invoice_id,)
        )
        row = cursor.fetchone()

    if not row:
        return None, None

    fetched_at = datetime.fromisoformat(row[0])
    invoice_detail = json.loads(row[1])
    return invoice_detail, fetched_at

def cache_invoice_detail(invoice_id, invoice_detail, fetched_at):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO invoice_detail_cache (invoice_id, fetched_at, payload)
            VALUES (?, ?, ?)
        """, (invoice_id, fetched_at.isoformat(), json.dumps(invoice_detail)))
        conn.commit()

def get_all_invoice_datetime_cache():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT invoice_id, install_datetime, removal_datetime, source, events "
                "FROM invoice_datetime_cache"
            )
            rows = cursor.fetchall()
        except sqlite3.OperationalError:
            try:
                cursor.execute(
                    "SELECT invoice_id, install_datetime, removal_datetime, source "
                    "FROM invoice_datetime_cache"
                )
                rows = [(row[0], row[1], row[2], row[3], None) for row in cursor.fetchall()]
            except sqlite3.OperationalError:
                return {}

    cache = {}
    for row in rows:
        events = []
        if row[4]:
            try:
                events = json.loads(row[4]) or []
            except (TypeError, json.JSONDecodeError):
                events = []
        if not events:
            events = events_from_install_removal(row[1], row[2])
        cache[row[0]] = {
            "install_datetime": row[1],
            "removal_datetime": row[2],
            "source": row[3],
            "events": events,
        }
    return cache

def cache_invoice_datetimes(
    invoice_id,
    install_datetime,
    removal_datetime,
    source,
    fetched_at,
    events=None,
):
    if events is None:
        events = events_from_install_removal(install_datetime, removal_datetime)
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO invoice_datetime_cache (
                invoice_id, install_datetime, removal_datetime, source, fetched_at, events
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            invoice_id,
            install_datetime,
            removal_datetime,
            source,
            fetched_at.isoformat(),
            json.dumps(events),
        ))
        conn.commit()

def apply_parsed_datetimes(invoice, parsed):
    """Attach primary datetimes and the full events list to an invoice dict."""
    events = parsed.get("events") or []
    invoice["install_datetime"] = parsed.get("install")
    invoice["removal_datetime"] = parsed.get("removal")
    invoice["install_ok"] = bool(parsed.get("install_ok"))
    invoice["removal_ok"] = bool(parsed.get("removal_ok"))
    invoice["datetime_events"] = events
    invoice["install_event_count"] = count_events_of_type(events, "install")
    invoice["removal_event_count"] = count_events_of_type(events, "removal")

def resolve_invoice_datetimes(invoices):
    """Attach install/removal datetimes to each invoice.

    Resolution priority: a cached ollama/manual result overrides the regex parser.
    """
    cache = get_all_invoice_datetime_cache()

    for invoice in invoices:
        invoice_id = invoice.get("id")
        cached = cache.get(invoice_id) if invoice_id else None

        if cached and cached.get("source") in ("ollama", "manual"):
            events = cached.get("events") or events_from_install_removal(
                cached.get("install_datetime"),
                cached.get("removal_datetime"),
            )
            apply_parsed_datetimes(
                invoice,
                {
                    "install": cached.get("install_datetime"),
                    "removal": cached.get("removal_datetime"),
                    "install_ok": bool(cached.get("install_datetime")),
                    "removal_ok": bool(cached.get("removal_datetime")),
                    "events": events,
                },
            )
            continue

        parsed = parse_install_removal(
            invoice.get("invoice_summary"),
            invoice.get("job_summary")
        )
        apply_parsed_datetimes(invoice, parsed)
def fetch_invoice_detail(invoice_id):
    response = requests.get(
        f"{CUSTOMER_INVOICES_API_URL}/{invoice_id}",
        headers=api_headers(),
        timeout=30
    )
    if response.status_code != 200:
        raise RuntimeError(f"Failed to fetch invoice detail {invoice_id}: {response.status_code} {response.text}")

    return response.json()

def get_invoice_detail(invoice_id, force_refresh=False):
    invoice_detail, _ = get_invoice_detail_with_source(invoice_id, force_refresh=force_refresh)
    return invoice_detail

def get_invoice_detail_with_source(invoice_id, force_refresh=False):
    if not invoice_id:
        return None, "missing"

    cached_invoice, _ = get_cached_invoice_detail(invoice_id)
    if cached_invoice is not None and not force_refresh:
        return cached_invoice, "sqlite"

    invoice_detail = fetch_invoice_detail(invoice_id)
    cache_invoice_detail(invoice_id, invoice_detail, datetime.now())
    return invoice_detail, "api"

def format_invoice_line_items(line_items):
    formatted_line_items = []
    for line_item in line_items or []:
        formatted_line_items.append({
            "quantity": line_item.get("quantity", ""),
            "description": line_item.get("description", ""),
            "unit_price": line_item.get("unit_price", 0),
            "item_name": line_item.get("item_name", "")
        })

    return formatted_line_items

def enrich_invoices_with_line_items(invoices, force_refresh=False, progress_callback=None):
    invoice_count = len(invoices)
    for index, invoice in enumerate(invoices, start=1):
        invoice["line_items"] = []
        invoice_id = invoice.get("id")
        if not invoice_id:
            continue

        try:
            invoice_detail, source = get_invoice_detail_with_source(invoice_id, force_refresh=force_refresh)
        except Exception as e:
            logging.error(f"Failed to enrich invoice {invoice.get('invoice_number')}: {e}")
            continue

        invoice["line_items"] = format_invoice_line_items(invoice_detail.get("line_items") if invoice_detail else [])
        if invoice_detail:
            # The report list already carries invoice_summary; job_summary only
            # exists on the detail, so capture it for the datetime parser.
            if invoice_detail.get("job_summary"):
                invoice["job_summary"] = invoice_detail.get("job_summary")
            if not invoice.get("invoice_summary") and invoice_detail.get("invoice_summary"):
                invoice["invoice_summary"] = invoice_detail.get("invoice_summary")
        if progress_callback and invoice_count:
            progress = 45 + int((index / invoice_count) * 50)
            progress_callback(
                progress,
                f"Invoice line item data {source} call {index} out of {invoice_count}"
            )

def get_invoices_for_period(report_key, start_date, end_date, force_refresh=False, progress_callback=None):
    now = datetime.now()
    if progress_callback:
        progress_callback(5, "Invoice data sqlite call 1 out of 1")

    cached_invoices, fetched_at = get_cached_invoice_report(report_key)

    if (
        not force_refresh
        and cached_invoices is not None
    ):
        return cached_invoices, fetched_at

    invoices = fetch_invoices_for_period(start_date, end_date, progress_callback=progress_callback)
    cache_invoice_report(report_key, invoices, now)
    return invoices, now

# Sync with API
def sync_with_api(overall=False):
    global sync_status
    try:
        sync_status["error"] = None  # Reset error status before sync
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()

            last_modified = None if overall else (datetime.now() - timedelta(hours=1)).isoformat()
            jobs = fetch_jobs(last_modified)

            for job in jobs:
                last_modified_value = job.get("last_modified", None)
                if last_modified_value:
                    last_modified_value = datetime.fromisoformat(last_modified_value)

                cursor.execute("""
                    INSERT OR REPLACE INTO jobs (
                        job_number, job_summary, job_location, last_modified,
                        job_type, job_date, arrival_time, removal_time, priority,
                        due_date, status, date_completed, id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    job["job_number"],
                    job.get("job_summary", "No Summary"),
                    job.get("address_text", "No Location"),
                    last_modified_value,
                    job.get("type", "Unknown"),
                    job.get("due_date", "Unknown"),
                    job.get("arrival_time", "Unknown"),
                    job.get("removal_time", "Unknown"),
                    job.get("priority", "Unknown"),
                    job.get("due_date", "Unknown"),
                    job.get("status", "Unknown"),
                    job.get("date_completed") or None,
                    job.get("id", None)  # Use "id" from the API response
                ))
                logging.info(f"Job fetched: {job}")


            conn.commit()
            update_job_types()
            update_job_addresses()
            update_pickup_dates()
            sync_status["last_sync_time"] = datetime.now().isoformat()
            logging.info(f"Sync completed with {len(jobs)} jobs.")
    except Exception as e:
        sync_status["error"] = str(e)
        logging.error(f"Sync failed: {e}")

# Background Sync
def background_sync(overall=False):
    """
    Runs sync_with_api in a separate thread and updates sync status.
    """
    def run_sync():
        with sync_lock:
            sync_status["ongoing"] = True
            sync_status["error"] = None
        try:
            logging.info("Starting background sync...")
            sync_with_api(overall=overall)
            logging.info("Background sync completed.")
        finally:
            with sync_lock:
                sync_status["ongoing"] = False

    thread = Thread(target=run_sync)
    thread.daemon = True
    thread.start()


# Get Cached Jobs
def get_cached_jobs(page=1, per_page=20, search_query=None):
    offset = (page - 1) * per_page
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        
        if search_query:
            cursor.execute("""
                SELECT job_number, job_type, job_date, arrival_time, removal_time, job_summary, job_location, last_modified, id
                FROM jobs
                WHERE (job_summary LIKE ? OR job_location LIKE ?)
                    AND (date_completed IS NULL OR date_completed = '')
                ORDER BY last_modified DESC
                LIMIT ? OFFSET ?
            """, (f"%{search_query}%", f"%{search_query}%", per_page, offset))
        else:
            cursor.execute("""
                SELECT job_number, job_type, job_date, arrival_time, removal_time, job_summary, job_location, last_modified, id
                FROM jobs
                WHERE date_completed IS NULL OR date_completed = ''
                ORDER BY last_modified DESC
                LIMIT ? OFFSET ?
            """, (per_page, offset))
        
        jobs = cursor.fetchall()
        
        # Get total job count for pagination
        cursor.execute("""
            SELECT COUNT(*)
            FROM jobs
            WHERE (job_summary LIKE ? OR job_location LIKE ?)
                AND (date_completed IS NULL OR date_completed = '')
        """, (f"%{search_query}%", f"%{search_query}%" if search_query else "%%"))
        total_jobs = cursor.fetchone()[0]

    return jobs, total_jobs

@app.route("/")
def home():
    page = int(request.args.get('page', 1))
    search_query = request.args.get('search', None)
    jobs, total_jobs = get_cached_jobs(page=page, per_page=20, search_query=search_query)
    
    logging.info(f"Jobs fetched for page {page}: {jobs}")
    
    total_pages = (total_jobs + 19) // 20 # Calculate total pages
    return render_template(
        "index.html",
        jobs=jobs,
        current_page=page,
        total_pages=total_pages,
        search_query=search_query
    )

# Refresh Data Endpoint
@app.route("/refresh")
def refresh():
    background_sync(overall=True)
    return ("", 204)  # Return a success status immediately

# Sync Status Endpoint
@app.route("/sync-status")
def sync_status_endpoint():
    with sync_lock:  # Ensure thread-safe access to sync_status
        #logging.info(f"Sync status requested: {sync_status}")
        return jsonify(sync_status)

# Admin Portal Endpoint
@app.route("/admin")
def admin_portal():
    roster = get_roster()
    aliases = get_aliases()
    employees = list_timesheet_employees()
    employee_set = set(employees)
    nicknames = sorted(roster.nicknames, key=lambda n: n.lower())
    nickname_rows = []
    for nick in nicknames:
        mapped = aliases.get(nick) or ""
        # Case-insensitive recover if the saved key casing drifted.
        if not mapped:
            for key, value in aliases.items():
                if key.lower() == nick.lower():
                    mapped = value
                    break
        suggested = suggest_employee(nick, employee_set) or ""
        nickname_rows.append(
            {
                "nickname": nick,
                "mapped": mapped if mapped in employee_set else "",
                "suggested": suggested,
            }
        )
    return render_template(
        "admin.html",
        parse_errors=PARSE_ERRORS,
        nickname_rows=nickname_rows,
        employees=employees,
        roster_source=roster.source_path,
        roster_entry_count=roster.entry_count,
        roster_nickname_count=len(roster.nicknames),
        roster_load_error=roster.load_error,
        alias_count=sum(1 for row in nickname_rows if row["mapped"]),
    )


@app.route("/admin/roster-aliases", methods=["POST"])
def admin_save_roster_aliases():
    payload = request.get_json(silent=True)
    if payload is None:
        # Form post: nickname_<token> fields
        aliases = {}
        for key, value in request.form.items():
            if not key.startswith("alias:"):
                continue
            nick = key[len("alias:"):].strip()
            name = (value or "").strip()
            if nick and name:
                aliases[nick] = name
    else:
        aliases = payload.get("aliases") if isinstance(payload, dict) else None
        if not isinstance(aliases, dict):
            return jsonify({"error": "Expected JSON body with an 'aliases' object."}), 400
        aliases = {
            str(k).strip(): str(v).strip()
            for k, v in aliases.items()
            if str(k).strip() and str(v).strip()
        }

    saved = update_aliases(aliases)
    logging.info("Saved %d roster nickname aliases.", len(saved))
    if request.accept_mimetypes.best == "application/json" or payload is not None:
        return jsonify({"ok": True, "alias_count": len(saved), "aliases": saved})
    return redirect(url_for("admin_portal"))


@app.route("/admin/roster-reload", methods=["POST"])
def admin_reload_roster():
    roster = refresh_roster()
    refresh_aliases()
    if roster.load_error or not roster.entry_count:
        return jsonify(
            {
                "ok": False,
                "error": roster.load_error
                or "Roster file loaded but no job/staff rows were found.",
                "source_path": roster.source_path,
                "entry_count": roster.entry_count,
                "nickname_count": len(roster.nicknames),
            }
        ), 400
    return jsonify(
        {
            "ok": True,
            "source_path": roster.source_path,
            "entry_count": roster.entry_count,
            "nickname_count": len(roster.nicknames),
        }
    )

def update_report_job(job_id, **updates):
    with report_jobs_lock:
        report_jobs.setdefault(job_id, {}).update(updates)

def build_report_payload(report_year, report_key, report_title, start_date, end_date, include_voided=False, force_refresh=False, progress_callback=None):
    error = None
    invoices = []
    fetched_at = None

    try:
        invoices, fetched_at = get_invoices_for_period(
            report_key,
            start_date,
            end_date,
            force_refresh=force_refresh,
            progress_callback=progress_callback
        )
    except Exception as e:
        error = str(e)
        logging.error(f"{report_title} invoice report failed: {e}")

    voided_count = sum(1 for invoice in invoices if (invoice.get("status") or "").lower() == "voided")
    if not include_voided:
        invoices = [invoice for invoice in invoices if (invoice.get("status") or "").lower() != "voided"]

    enrich_invoices_with_line_items(
        invoices,
        force_refresh=force_refresh,
        progress_callback=progress_callback
    )

    if progress_callback:
        progress_callback(96, "Resolving job install/removal datetimes")
    resolve_invoice_datetimes(invoices)

    if progress_callback:
        progress_callback(98, "Matching staff timesheets to jobs")
    try:
        allocate_staff(invoices)
    except Exception as e:
        logging.error(f"Staff allocation failed: {e}")

    roster_vs_paid = summarise_rostered_vs_paid(start_date, end_date)

    total_amount = sum((Decimal(invoice.get("amount_tax_ex") or "0") for invoice in invoices), Decimal("0"))
    return {
        "report_title": report_title,
        "report_year": report_year,
        "start_date_label": format_date_label(start_date),
        "end_date_label": format_date_label(end_date),
        "invoices": invoices,
        "invoice_count": len(invoices),
        "include_voided": include_voided,
        "voided_count": voided_count,
        "total_amount": f"{total_amount:,.2f}",
        "fetched_at": fetched_at.strftime("%Y-%m-%d %H:%M:%S") if fetched_at else None,
        "roster_vs_paid": roster_vs_paid,
        "error": error
    }

def load_report_in_background(job_id, report_year, include_voided=False, force_refresh=False):
    report_config = REPORT_PERIODS[report_year]

    def report_progress(progress, message):
        update_report_job(
            job_id,
            progress=progress,
            message=message
        )

    try:
        update_report_job(
            job_id,
            status="loading",
            progress=1,
            message="Preparing report load"
        )
        payload = build_report_payload(
            report_year=report_year,
            include_voided=include_voided,
            force_refresh=force_refresh,
            progress_callback=report_progress,
            **report_config
        )
        update_report_job(
            job_id,
            status="complete",
            progress=100,
            message="Report loaded",
            result=payload
        )
    except Exception as e:
        logging.error(f"Report load failed: {e}")
        update_report_job(
            job_id,
            status="error",
            progress=100,
            message=str(e)
        )

# Reports Endpoint
@app.route("/reports")
def reports():
    report_year = request.args.get("year", "fy26")
    if report_year not in REPORT_PERIODS:
        report_year = "fy26"

    report_config = REPORT_PERIODS[report_year]
    include_voided = request.args.get("include_voided") == "1"
    return render_template(
        "fy_report.html",
        report_title=report_config["report_title"],
        report_year=report_year,
        report_url=url_for("reports"),
        refresh_url=url_for(
            "reports",
            year=report_year,
            refresh=1,
            include_voided=1 if include_voided else None
        ),
        start_date_label=format_date_label(report_config["start_date"]),
        end_date_label=format_date_label(report_config["end_date"]),
        include_voided=include_voided,
        force_refresh=request.args.get("refresh") == "1"
    )

@app.route("/reports/start")
def start_report_load():
    report_year = request.args.get("year", "fy26")
    if report_year not in REPORT_PERIODS:
        report_year = "fy26"

    include_voided = request.args.get("include_voided") == "1"
    force_refresh = request.args.get("refresh") == "1"
    job_id = f"{report_year}-{int(time.time() * 1000)}"
    update_report_job(
        job_id,
        status="queued",
        progress=0,
        message="Queued report load"
    )

    thread = Thread(
        target=load_report_in_background,
        args=(job_id, report_year, include_voided, force_refresh)
    )
    thread.daemon = True
    thread.start()
    return jsonify({"job_id": job_id})

@app.route("/reports/status/<job_id>")
def report_load_status(job_id):
    with report_jobs_lock:
        job = report_jobs.get(job_id)

    if not job:
        return jsonify({"status": "error", "progress": 100, "message": "Report load was not found"}), 404

    return jsonify({
        "status": job.get("status"),
        "progress": job.get("progress", 0),
        "message": job.get("message", "")
    })

@app.route("/reports/content/<job_id>")
def report_load_content(job_id):
    with report_jobs_lock:
        job = report_jobs.get(job_id)

    if not job:
        return ("Report load was not found", 404)
    if job.get("status") != "complete":
        return ("Report is still loading", 202)

    return render_template("report_content.html", **job["result"])

@app.route("/invoices/<invoice_id>")
def invoice_detail_page(invoice_id):
    error = None
    invoice = None

    try:
        invoice = get_invoice_detail(invoice_id)
    except Exception as e:
        error = str(e)
        logging.error(f"Invoice detail page failed for {invoice_id}: {e}")

    return render_template("invoice_detail.html", invoice=invoice, error=error)

@app.route("/invoices/<invoice_id>/parse-datetimes", methods=["POST"])
def parse_invoice_datetimes(invoice_id):
    try:
        detail = get_invoice_detail(invoice_id)
    except Exception as e:
        logging.error(f"parse-datetimes failed to load invoice {invoice_id}: {e}")
        return jsonify({"error": f"Unable to load invoice: {e}"}), 502

    if not detail:
        return jsonify({"error": "Invoice not found"}), 404

    text = "\n\n".join(
        part for part in (detail.get("invoice_summary"), detail.get("job_summary")) if part
    )

    try:
        parsed = parse_datetimes_with_ollama(text)
    except requests.exceptions.RequestException as e:
        logging.error(f"Ollama unavailable for invoice {invoice_id}: {e}")
        return jsonify({"error": "AI service is unavailable. Is Ollama running?"}), 503
    except (ValueError, json.JSONDecodeError) as e:
        logging.error(f"Ollama returned an unreadable response for invoice {invoice_id}: {e}")
        return jsonify({"error": "AI returned an unreadable response."}), 502

    install_datetime = parsed.get("install_datetime")
    removal_datetime = parsed.get("removal_datetime")
    events = events_from_install_removal(install_datetime, removal_datetime)
    cache_invoice_datetimes(
        invoice_id,
        install_datetime,
        removal_datetime,
        "ollama",
        datetime.now(),
        events=events,
    )

    invoice = dict(detail)
    apply_parsed_datetimes(
        invoice,
        {
            "install": install_datetime,
            "removal": removal_datetime,
            "install_ok": bool(install_datetime),
            "removal_ok": bool(removal_datetime),
            "events": events,
        },
    )

    try:
        allocate_staff([invoice])
    except Exception as e:
        logging.error(f"Staff allocation failed for invoice {invoice_id}: {e}")

    return jsonify({
        "install_datetime": install_datetime,
        "removal_datetime": removal_datetime,
        "install_ok": bool(install_datetime),
        "removal_ok": bool(removal_datetime),
        "datetime_events": events,
        "install_event_count": invoice.get("install_event_count", 0),
        "removal_event_count": invoice.get("removal_event_count", 0),
        "install_label": format_datetime_label(install_datetime),
        "removal_label": format_datetime_label(removal_datetime),
        "staff_allocations": invoice.get("staff_allocations", []),
        "staff_status": invoice.get("staff_status", "no_match"),
        "paid_hours_total": invoice.get("paid_hours_total", 0.0),
    })

# FY25 Report Endpoint
@app.route("/fy25-report")
def fy25_report():
    return redirect(url_for("reports", year="fy25"))

# FY26 Report Endpoint
@app.route("/fy26-report")
def fy26_report():
    return redirect(url_for("reports", year="fy26"))

if __name__ == "__main__":
    init_db()
    logging.info("Database initialized.")
    # Prefer Deputy-synced timesheets when tokens exist so a local JSON
    # re-import does not wipe roster_comment on every server start.
    from pathlib import Path

    if Path("deputy_tokens.json").exists():
        from import_timesheets import create_timesheets_table
        import sqlite3

        with sqlite3.connect("jobs_cache.db") as conn:
            create_timesheets_table(conn)
        logging.info(
            "Deputy tokens found; skipping JSON timesheet import. "
            "Run `python sync_deputy.py sync --from … --to …` to refresh."
        )
    else:
        imported = import_timesheets_if_present()
        logging.info(f"Timesheet import complete ({imported} rows).")
    # Warm the roster cache in a background thread so the server starts quickly
    # (parsing the full Schedule workbook takes ~1 minute).
    def _warm_roster():
        try:
            roster = refresh_roster()
            refresh_aliases()
            logging.info(
                "Roster loaded (%s entries from %s).",
                roster.entry_count,
                roster.source_path or "none",
            )
        except Exception as exc:
            logging.warning("Roster warm-up failed: %s", exc)

    Thread(target=_warm_roster, daemon=True).start()
    background_sync(overall=True)
    logging.info("Triggered initial background sync.")
    app.run(host="0.0.0.0", port=5000, debug=True)

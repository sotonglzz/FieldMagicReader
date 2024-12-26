import sqlite3
import requests
import time
from base64 import b64encode
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, jsonify
from update_job_types import update_job_types, update_job_addresses, update_pickup_dates, PARSE_ERRORS
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

# API Setup
API_URL = "http://api.fieldmagic.co/jobs"
username = "c3d1beb4687f6a20"
password = "310b7da2d2fe630739fa6a12"

# Flask Setup
app = Flask(__name__)

# Database Initialization
DB_NAME = "jobs_cache.db"

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
            date_completed TIMESTAMP
        )
        """)
        conn.commit()

# Encrypting FieldMagic Username & Password (API Key and Secret)
def basic_auth(username, password):
    token = b64encode(f"{username}:{password}".encode('utf-8')).decode("ascii")
    return f'Basic {token}'

# Fetch Data from API with Pagination
def fetch_jobs(last_modified=None):
    start_time = time.time() # Start timing
    headers = {
        'Authorization': basic_auth(username, password),
        'Content-Type': 'application/json',
        'Client-Id': 'b48698b2-d589-4b64-af1f-4482e7fbe599',
    }
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
        end_time = time.time() # End timing
        logging.info(f"API call completed in {end_time - start_time:.2f} seconds")
        jobs = response_data.get("data", [])

        # Filter out jobs that have a completed_date
        filtered_jobs = [job for job in jobs if not job.get("date_completed")]

        all_jobs.extend(filtered_jobs)

        next_token = response_data.get("next_token")
        if not next_token:
            break
    endtime=time.time()
    logging.info(f"API call completed in {end_time - start_time:.2f} seconds")
    return all_jobs


# Sync with API
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
                        job_type, job_date, arrival_time, removal_time, priority, due_date, status, date_completed
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    job.get("date_completed", None)
                ))

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
                SELECT job_number, job_type, job_date, arrival_time, removal_time, job_summary, job_location, last_modified
                FROM jobs
                WHERE (job_summary LIKE ? OR job_location LIKE ?) AND date_completed IS NULL
                ORDER BY last_modified DESC
                LIMIT ? OFFSET ?
            """, (f"%{search_query}%", f"%{search_query}%", per_page, offset))
        else:
            cursor.execute("""
                SELECT job_number, job_type, job_date, arrival_time, removal_time, job_summary, job_location, last_modified
                FROM jobs
                WHERE date_completed IS NULL
                ORDER BY last_modified DESC
                LIMIT ? OFFSET ?
            """, (per_page, offset))
        
        jobs = cursor.fetchall()
        
        # Get total job count for pagination
        cursor.execute("""
            SELECT COUNT(*)
            FROM jobs
            WHERE (job_summary LIKE ? OR job_location LIKE ?) AND date_completed IS NULL
        """, (f"%{search_query}%", f"%{search_query}%" if search_query else "%%"))
        total_jobs = cursor.fetchone()[0]

    return jobs, total_jobs

@app.route("/")
def home():
    page = int(request.args.get('page', 1))
    search_query = request.args.get('search', None)
    jobs, total_jobs = get_cached_jobs(page=page, per_page=20, search_query=search_query)
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
    return render_template("admin.html", parse_errors=PARSE_ERRORS)

if __name__ == "__main__":
    init_db()
    logging.info("Database initialized.")
    background_sync(overall=True)
    logging.info("Triggered initial background sync.")
    app.run(debug=True)

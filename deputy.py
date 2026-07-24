"""Deputy API client: OAuth + timesheet/roster sync helpers.

Uses OAuth 2.0 with ``longlife_refresh_token`` scope. Client id/secret live in
``.env``; access/refresh tokens are stored in ``deputy_tokens.json`` so refresh
rotation does not rewrite the env file.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

from import_timesheets import create_timesheets_table

logger = logging.getLogger(__name__)

DB_NAME = "jobs_cache.db"
TOKENS_PATH = Path("deputy_tokens.json")
ONCE_AUTH_URL = "https://once.deputy.com/my/oauth/login"
ONCE_TOKEN_URL = "https://once.deputy.com/my/oauth/access_token"
DEFAULT_REDIRECT_URI = "http://localhost"
OAUTH_SCOPE = "longlife_refresh_token"
PAGE_SIZE = 500


def _load_dotenv():
    """Best-effort load of ``.env`` into ``os.environ`` (no-op if missing)."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        env_path = Path(".env")
        if not env_path.exists():
            return
        for line in env_path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text or text.startswith("#") or "=" not in text:
                continue
            key, _, value = text.partition("=")
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = value
        return
    load_dotenv()


def _env(name, default=None):
    _load_dotenv()
    value = os.environ.get(name, default)
    if value is None:
        return default
    value = str(value).strip()
    return value or default


def deputy_configured():
    """True when client credentials are present (tokens may still be missing)."""
    return bool(_env("DEPUTY_CLIENT_ID") and _env("DEPUTY_CLIENT_SECRET"))


def authorization_url(redirect_uri=None):
    """Build the browser URL for the one-time OAuth consent step."""
    client_id = _env("DEPUTY_CLIENT_ID")
    if not client_id:
        raise RuntimeError("DEPUTY_CLIENT_ID is not set in the environment / .env")
    redirect = redirect_uri or _env("DEPUTY_REDIRECT_URI", DEFAULT_REDIRECT_URI)
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": OAUTH_SCOPE,
        }
    )
    return f"{ONCE_AUTH_URL}?{query}"


def _save_tokens(payload):
    """Persist tokens from an OAuth token response."""
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token")
    endpoint = payload.get("endpoint") or ""
    expires_in = int(payload.get("expires_in") or 86400)
    if not access_token or not refresh_token:
        raise RuntimeError(f"Unexpected Deputy token response: {payload!r}")

    # Endpoint comes back as ``install.geo.deputy.com`` (no scheme).
    endpoint = str(endpoint).strip().rstrip("/")
    if endpoint.startswith("https://"):
        api_base = endpoint
    elif endpoint:
        api_base = f"https://{endpoint}"
    else:
        api_base = (_env("DEPUTY_API_BASE") or "").rstrip("/")

    data = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "endpoint": endpoint,
        "api_base": api_base,
        "expires_at": time.time() + expires_in - 60,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    TOKENS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("Saved Deputy tokens to %s (endpoint=%s)", TOKENS_PATH, endpoint or api_base)
    return data


def _load_tokens():
    if not TOKENS_PATH.exists():
        return None
    try:
        return json.loads(TOKENS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read %s: %s", TOKENS_PATH, exc)
        return None


def exchange_code(code, redirect_uri=None):
    """Exchange an OAuth authorization code for access + refresh tokens."""
    client_id = _env("DEPUTY_CLIENT_ID")
    client_secret = _env("DEPUTY_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("DEPUTY_CLIENT_ID and DEPUTY_CLIENT_SECRET must be set")
    redirect = redirect_uri or _env("DEPUTY_REDIRECT_URI", DEFAULT_REDIRECT_URI)
    response = requests.post(
        ONCE_TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect,
            "grant_type": "authorization_code",
            "code": code.strip(),
            "scope": OAUTH_SCOPE,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=60,
    )
    if not response.ok:
        raise RuntimeError(
            f"Deputy token exchange failed ({response.status_code}): {response.text}"
        )
    return _save_tokens(response.json())


def _refresh_access_token(tokens):
    client_id = _env("DEPUTY_CLIENT_ID")
    client_secret = _env("DEPUTY_CLIENT_SECRET")
    redirect = _env("DEPUTY_REDIRECT_URI", DEFAULT_REDIRECT_URI)
    api_base = (tokens.get("api_base") or _env("DEPUTY_API_BASE") or "").rstrip("/")
    if not api_base:
        raise RuntimeError(
            "No Deputy API base URL. Re-run `python sync_deputy.py auth` "
            "or set DEPUTY_API_BASE in .env."
        )
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise RuntimeError("No refresh token stored; run `python sync_deputy.py auth`")

    response = requests.post(
        f"{api_base}/oauth/access_token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": OAUTH_SCOPE,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=60,
    )
    if not response.ok:
        raise RuntimeError(
            f"Deputy token refresh failed ({response.status_code}): {response.text}"
        )
    payload = response.json()
    # Refresh responses may omit endpoint; keep the existing one.
    if not payload.get("endpoint") and tokens.get("endpoint"):
        payload["endpoint"] = tokens["endpoint"]
    return _save_tokens(payload)


def get_session():
    """Return ``(api_base, headers)`` with a valid Bearer token."""
    tokens = _load_tokens()
    if not tokens or not tokens.get("access_token"):
        raise RuntimeError(
            "Deputy is not authorised yet. Run: python sync_deputy.py auth"
        )

    expires_at = float(tokens.get("expires_at") or 0)
    if expires_at and time.time() >= expires_at:
        tokens = _refresh_access_token(tokens)

    api_base = (tokens.get("api_base") or _env("DEPUTY_API_BASE") or "").rstrip("/")
    if not api_base:
        raise RuntimeError("DEPUTY_API_BASE is missing; re-run auth to capture endpoint")

    headers = {
        "Authorization": f"Bearer {tokens['access_token']}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    return api_base, headers


def _unix_to_iso(value):
    if value in (None, "", 0):
        return None
    try:
        ts = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(ts).replace(microsecond=0).isoformat()


def _localized_to_iso(value):
    if value in (None, ""):
        return None
    text = str(value).strip()
    # Deputy returns e.g. ``2022-09-01T09:00:00+10:00`` — store naive local wall time.
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed.replace(microsecond=0).isoformat()


def _status_label(row):
    if row.get("Discarded"):
        return "Discarded"
    if row.get("isInProgress") or row.get("IsInProgress"):
        return "On shift"
    if row.get("PayStaged"):
        return "Paid"
    if row.get("PayRuleApproved"):
        return "Pay approved"
    if row.get("TimeApproved"):
        return "Time approved"
    return "Pending"


def _leave_policy(row):
    if not (row.get("IsLeave") or row.get("LeaveId") or row.get("LeaveRule")):
        return None
    leave_rule = row.get("LeaveRuleObject") or {}
    if isinstance(leave_rule, dict):
        name = leave_rule.get("Name") or leave_rule.get("LeaveRuleName")
        if name:
            return str(name)
    leave = row.get("Leave") or {}
    if isinstance(leave, dict):
        name = leave.get("Comment") or leave.get("Status")
        if name:
            return str(name)
    return "Leave"


def _employee_name(row):
    employee = row.get("EmployeeObject") or {}
    if isinstance(employee, dict):
        display = employee.get("DisplayName")
        if display:
            return str(display).strip()
        first = (employee.get("FirstName") or "").strip()
        last = (employee.get("LastName") or "").strip()
        name = f"{first} {last}".strip()
        if name:
            return name
    meta = (row.get("_DPMetaData") or {}).get("EmployeeInfo") or {}
    display = meta.get("DisplayName")
    return str(display).strip() if display else None


def _area_location(row):
    op_unit = row.get("OperationalUnitObject") or {}
    meta = (row.get("_DPMetaData") or {}).get("OperationalUnitInfo") or {}
    area = None
    location = None
    if isinstance(op_unit, dict):
        area = op_unit.get("OperationalUnitName") or op_unit.get("CompanyName")
        location = op_unit.get("CompanyName")
    if not area:
        area = meta.get("OperationalUnitName")
    if not location:
        location = meta.get("CompanyName") or meta.get("LabelWithCompany")
    return (
        str(area).strip() if area else None,
        str(location).strip() if location else None,
    )


def _normalize_timesheet(row):
    """Map a Deputy Timesheet (+ joins) resource into a local timesheets row."""
    roster = row.get("RosterObject") or {}
    if not isinstance(roster, dict):
        roster = {}

    timesheet_start = _localized_to_iso(row.get("StartTimeLocalized")) or _unix_to_iso(
        row.get("StartTime")
    )
    timesheet_end = _localized_to_iso(row.get("EndTimeLocalized")) or _unix_to_iso(
        row.get("EndTime")
    )
    shift_start = (
        _localized_to_iso(roster.get("StartTimeLocalized"))
        or _unix_to_iso(roster.get("StartTime"))
        or timesheet_start
    )
    shift_end = (
        _localized_to_iso(roster.get("EndTimeLocalized"))
        or _unix_to_iso(roster.get("EndTime"))
        or timesheet_end
    )

    roster_comment = roster.get("Comment")
    if roster_comment is not None:
        roster_comment = str(roster_comment).strip() or None

    area, location = _area_location(row)
    roster_id = roster.get("Id") or row.get("Roster")
    employee_id = row.get("Employee")

    total_time = roster.get("TotalTime")
    if total_time in (None, ""):
        total_time = None
    else:
        try:
            total_time = round(float(total_time), 2)
        except (TypeError, ValueError):
            total_time = None

    timesheet_total = row.get("TotalTime")
    if timesheet_total in (None, ""):
        timesheet_total = None
    else:
        try:
            timesheet_total = round(float(timesheet_total), 2)
        except (TypeError, ValueError):
            timesheet_total = None

    return {
        "timesheet_id": str(row.get("Id")),
        "team_member": _employee_name(row),
        "shift_start": shift_start,
        "shift_end": shift_end,
        "timesheet_start": timesheet_start,
        "timesheet_end": timesheet_end,
        "total_time": total_time,
        "timesheet_total_time": timesheet_total,
        "area": area,
        "location": location,
        "leave_policy": _leave_policy(row),
        "status": _status_label(row),
        "roster_id": str(roster_id) if roster_id not in (None, "") else None,
        "roster_comment": roster_comment,
        "deputy_employee_id": str(employee_id) if employee_id not in (None, "") else None,
    }


def fetch_timesheets(start_date, end_date):
    """Fetch timesheets in ``[start_date, end_date]`` with Roster / Employee joins.

    ``start_date`` / ``end_date`` may be ``date``, ``datetime``, or ``YYYY-MM-DD``
    strings. Returns a list of normalised dicts ready for DB upsert.
    """
    if isinstance(start_date, datetime):
        start_date = start_date.date()
    elif isinstance(start_date, str):
        start_date = date.fromisoformat(start_date[:10])
    if isinstance(end_date, datetime):
        end_date = end_date.date()
    elif isinstance(end_date, str):
        end_date = date.fromisoformat(end_date[:10])

    api_base, headers = get_session()
    url = f"{api_base}/api/v1/resource/Timesheet/QUERY"
    start = 0
    rows: list[dict[str, Any]] = []

    while True:
        payload = {
            "search": {
                "s1": {
                    "field": "Date",
                    "type": "ge",
                    "data": start_date.isoformat(),
                },
                "s2": {
                    "field": "Date",
                    "type": "le",
                    "data": end_date.isoformat(),
                },
            },
            "join": [
                "RosterObject",
                "EmployeeObject",
                "OperationalUnitObject",
                "LeaveRuleObject",
            ],
            "sort": {"Date": "asc"},
            "start": start,
            "max": PAGE_SIZE,
        }
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        if response.status_code == 401:
            # One retry after forced refresh.
            tokens = _load_tokens() or {}
            tokens = _refresh_access_token(tokens)
            headers["Authorization"] = f"Bearer {tokens['access_token']}"
            response = requests.post(url, headers=headers, json=payload, timeout=120)
        if not response.ok:
            raise RuntimeError(
                f"Deputy Timesheet QUERY failed ({response.status_code}): {response.text}"
            )

        batch = response.json()
        if not isinstance(batch, list):
            raise RuntimeError(f"Unexpected Timesheet QUERY response: {batch!r}")
        if not batch:
            break

        for item in batch:
            if isinstance(item, dict) and item.get("Id") is not None:
                rows.append(_normalize_timesheet(item))

        if len(batch) < PAGE_SIZE:
            break
        start += PAGE_SIZE
        # Be polite to the Resource API.
        time.sleep(0.2)

    logger.info(
        "Fetched %s Deputy timesheets from %s to %s",
        len(rows),
        start_date.isoformat(),
        end_date.isoformat(),
    )
    return rows


def upsert_timesheets(rows, db_name=DB_NAME):
    """Insert or replace normalised timesheet rows; returns count written."""
    if not rows:
        return 0
    with sqlite3.connect(db_name) as conn:
        create_timesheets_table(conn)
        cursor = conn.cursor()
        for row in rows:
            cursor.execute(
                """
                INSERT OR REPLACE INTO timesheets (
                    timesheet_id, team_member, shift_start, shift_end,
                    timesheet_start, timesheet_end,
                    total_time, timesheet_total_time,
                    area, location, leave_policy, status,
                    roster_id, roster_comment, deputy_employee_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["timesheet_id"],
                    row.get("team_member"),
                    row.get("shift_start"),
                    row.get("shift_end"),
                    row.get("timesheet_start"),
                    row.get("timesheet_end"),
                    row.get("total_time"),
                    row.get("timesheet_total_time"),
                    row.get("area"),
                    row.get("location"),
                    row.get("leave_policy"),
                    row.get("status"),
                    row.get("roster_id"),
                    row.get("roster_comment"),
                    row.get("deputy_employee_id"),
                ),
            )
        conn.commit()
    return len(rows)


def sync_timesheets(start_date, end_date, db_name=DB_NAME):
    """Fetch from Deputy and upsert into the local ``timesheets`` table."""
    rows = fetch_timesheets(start_date, end_date)
    written = upsert_timesheets(rows, db_name=db_name)
    with_notes = sum(1 for row in rows if row.get("roster_comment"))
    logger.info(
        "Synced %s timesheets (%s with roster comments) into %s",
        written,
        with_notes,
        db_name,
    )
    return {"written": written, "with_roster_comment": with_notes, "rows": rows}

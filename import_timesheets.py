"""Load ``Timesheet details.json`` into the ``timesheets`` table.

The export has no job key, so matching is purely temporal (see ``timesheets.py``).
Some rows have null Shift Start/End, in which case the Timesheet Start/End Time is
used as a fallback.
"""

import json
import logging
import os
import re
import sqlite3
from dateutil import parser as date_parser

logger = logging.getLogger(__name__)

DB_NAME = "jobs_cache.db"
TIMESHEET_JSON = "Timesheet details.json"


def create_timesheets_table(conn):
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS timesheets (
            timesheet_id TEXT PRIMARY KEY,
            team_member TEXT,
            shift_start TIMESTAMP,
            shift_end TIMESTAMP,
            total_time REAL,
            area TEXT,
            location TEXT
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_timesheets_shift_date ON timesheets(date(shift_start))"
    )
    conn.commit()


def _normalize_key(key):
    """Collapse spaces/underscores and lowercase so key variants compare equal."""
    return re.sub(r"[\s_]+", "", str(key)).lower()


def _normalize_row(row):
    return {_normalize_key(key): value for key, value in row.items()}


def _get(norm_row, *keys):
    """Return the first non-empty value from a normalized row for any candidate key."""
    for key in keys:
        value = norm_row.get(_normalize_key(key))
        if value not in (None, ""):
            return value
    return None


def _parse_dt(value):
    if value in (None, ""):
        return None
    try:
        return date_parser.parse(str(value)).replace(microsecond=0).isoformat()
    except (ValueError, OverflowError, TypeError):
        return None


def _parse_hours(value):
    if value in (None, ""):
        return None
    text = str(value).strip()
    # Accept plain numbers ("7.5") and "HH:MM" durations.
    if ":" in text:
        try:
            hours, minutes = text.split(":", 1)
            return round(int(hours) + int(minutes) / 60.0, 2)
        except (ValueError, TypeError):
            return None
    try:
        return round(float(text), 2)
    except (ValueError, TypeError):
        return None


def import_timesheets(path=TIMESHEET_JSON, db_name=DB_NAME):
    """Load timesheet rows from ``path`` into the ``timesheets`` table.

    Returns the number of rows imported. Raises ``FileNotFoundError`` if the
    export is missing (callers that want it optional should check first).
    """
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    if isinstance(data, dict):
        records = data.get("data") or data.get("timesheets") or data.get("rows") or []
    else:
        records = data

    imported = 0
    with sqlite3.connect(db_name) as conn:
        create_timesheets_table(conn)
        cursor = conn.cursor()
        # The export is a full snapshot, so replace the previous contents.
        cursor.execute("DELETE FROM timesheets")
        for index, row in enumerate(records):
            if not isinstance(row, dict):
                continue

            norm = _normalize_row(row)

            # Prefer the scheduled shift window; fall back to the actual
            # timesheet clock in/out when the shift times are blank.
            shift_start = _parse_dt(_get(norm, "Shift Start Time", "Shift Start")) or _parse_dt(
                _get(norm, "Timesheet Start Time", "Timesheet Start")
            )
            shift_end = _parse_dt(_get(norm, "Shift End Time", "Shift End")) or _parse_dt(
                _get(norm, "Timesheet End Time", "Timesheet End")
            )
            team_member = _get(
                norm, "Team member", "Team Member", "Employee", "Name", "User"
            )
            if not team_member:
                first = _get(norm, "First name", "First Name")
                last = _get(norm, "Last name", "Last Name")
                team_member = " ".join(part for part in (first, last) if part) or None
            total_time = _parse_hours(
                _get(norm, "Shift Total Time", "Timesheet Total Time", "Total Time", "Hours")
            )
            area = _get(norm, "Timesheet area", "Area")
            location = _get(norm, "Timesheet location", "Location", "Site")

            timesheet_id = (
                _get(norm, "Timesheet ID", "ID")
                or f"{team_member}|{shift_start}|{index}"
            )

            cursor.execute(
                """
                INSERT OR REPLACE INTO timesheets (
                    timesheet_id, team_member, shift_start, shift_end,
                    total_time, area, location
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (str(timesheet_id), team_member, shift_start, shift_end, total_time, area, location),
            )
            imported += 1

        conn.commit()

    logger.info("Imported %s timesheet rows from %s", imported, path)
    return imported


def import_timesheets_if_present(path=TIMESHEET_JSON, db_name=DB_NAME):
    """Import timesheets when the export exists; otherwise create an empty table."""
    if not os.path.exists(path):
        logger.warning(
            "Timesheet export %r not found; staff matching will be empty until it is added.",
            path,
        )
        with sqlite3.connect(db_name) as conn:
            create_timesheets_table(conn)
        return 0

    try:
        return import_timesheets(path, db_name)
    except Exception as exc:  # noqa: BLE001 - importer should never break startup
        logger.error("Failed to import timesheets from %r: %s", path, exc)
        with sqlite3.connect(db_name) as conn:
            create_timesheets_table(conn)
        return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    count = import_timesheets_if_present()
    print(f"Imported {count} timesheet rows.")

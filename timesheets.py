"""Timesheet matching engine: attribute staff shift hours to jobs.

The timesheet export has no job key, so a shift is matched to a job event
(install/removal) purely by time:

* Dedicated match: the shift starts near the job's anchor time, allowing for a
  travel lead (~1h) plus tolerance (+/-2h).
* Absorbed match: a job with no dedicated shift whose anchor falls inside a
  running shift is absorbed by that shift.

Each shift is then segmented across the sorted anchors it is responsible for:
the first job owns from shift start to the next anchor; every later job owns from
its own anchor to the next anchor (or shift end for the last one).

v1 attributes allocated HOURS only (no dollar cost).
"""

import logging
import sqlite3
from collections import defaultdict
from datetime import timedelta
from dateutil import parser as date_parser

from datetime_parser import is_diy_pickup

logger = logging.getLogger(__name__)

DB_NAME = "jobs_cache.db"

# Hardcoded defaults (easy to expose in the UI later).
TRAVEL_LEAD = timedelta(hours=1)
TOLERANCE = timedelta(hours=2)

_EVENT_FIELDS = (
    ("install", "install_datetime", "install_ok"),
    ("removal", "removal_datetime", "removal_ok"),
)


def _parse_dt(value):
    if value in (None, ""):
        return None
    try:
        parsed = date_parser.parse(str(value))
    except (ValueError, OverflowError, TypeError):
        return None
    # Work in naive local time so anchors and shifts are always comparable.
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed


def _has_time(value):
    """A stored ISO value carries a time-of-day when it contains a 'T' separator."""
    return isinstance(value, str) and "T" in value


def _format_time(dt):
    label = dt.strftime("%I:%M%p").lstrip("0").lower()
    return label


def _format_span(start, end):
    if start.date() == end.date():
        return f"{start.strftime('%a %d %b')} {_format_time(start)}\u2013{_format_time(end)}"
    return (
        f"{start.strftime('%a %d %b')} {_format_time(start)} \u2013 "
        f"{end.strftime('%a %d %b')} {_format_time(end)}"
    )


def _load_shifts(db_name, min_date, max_date):
    shifts = []
    with sqlite3.connect(db_name) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT timesheet_id, team_member, shift_start, shift_end,
                       timesheet_start, timesheet_end,
                       total_time, timesheet_total_time
                FROM timesheets
                WHERE shift_start IS NOT NULL AND shift_end IS NOT NULL
                  AND date(shift_start) BETWEEN ? AND ?
                  -- Only rentals shifts do on-site installs/removals; the
                  -- Braeside (sales) and Office locations never attend jobs.
                  AND (location IS NULL
                       OR (location NOT LIKE '%Braeside%'
                           AND location NOT LIKE '%Office%'))
                  -- Drop non-job areas: sales desk/design/sandbagging/RDO,
                  -- administration/office, maintenance, and delivery-run
                  -- templates (Dlt - RUN 01). Blank areas are kept.
                  AND (area IS NULL
                       OR (area NOT LIKE '%Sales%'
                           AND area NOT LIKE '%Admin%'
                           AND area NOT LIKE '%Maintenance%'
                           AND area NOT LIKE '%Run 01%'
                           AND area NOT LIKE '%Run01%'))
                  -- Leave rows (Annual/Sick/Public Holiday/etc.) carry shift
                  -- times but are not on-site at a job, so never match them.
                  AND (leave_policy IS NULL OR leave_policy = '')
                  -- Only finalised timesheets are real worked shifts;
                  -- exclude drafts (On shift/Pending) and Discarded rows.
                  AND status IN ('Pay approved', 'Paid', 'Time approved')
                """,
                (min_date.isoformat(), max_date.isoformat()),
            )
            rows = cursor.fetchall()
        except sqlite3.OperationalError:
            # timesheets table not created yet.
            return shifts

    for (timesheet_id, team_member, shift_start, shift_end,
         timesheet_start, timesheet_end, total_time, timesheet_total_time) in rows:
        start = _parse_dt(shift_start)
        end = _parse_dt(shift_end)
        if not start or not end or end <= start:
            continue
        shifts.append(
            {
                "timesheet_id": timesheet_id,
                "team_member": team_member or "Unknown",
                "shift_start": start,
                "shift_end": end,
                "timesheet_start": _parse_dt(timesheet_start),
                "timesheet_end": _parse_dt(timesheet_end),
                # Paid totals (breaks removed): rostered vs actually worked.
                "total_time": total_time,
                "timesheet_total_time": timesheet_total_time,
            }
        )
    return shifts


def _build_events(invoices):
    """Return (events, invoice_by_id). Also sets default staff fields on invoices."""
    events = []
    invoice_by_id = {}

    for invoice in invoices:
        invoice["staff_allocations"] = []

        # DIY/Pickup jobs are self-service (customer collects and returns the
        # products), so they never need staff and are excluded from matching.
        if is_diy_pickup(invoice.get("invoice_summary"), invoice.get("job_summary")):
            invoice["is_diy_pickup"] = True
            invoice["staff_status"] = "diy_pickup"
            continue

        invoice["is_diy_pickup"] = False
        invoice["staff_status"] = "needs_datetime"
        invoice_id = invoice.get("id") or invoice.get("invoice_id")
        if not invoice_id:
            continue
        invoice_by_id[invoice_id] = invoice

        for kind, value_key, ok_key in _EVENT_FIELDS:
            value = invoice.get(value_key)
            if invoice.get(ok_key) and value and _has_time(value):
                anchor = _parse_dt(value)
                if anchor:
                    events.append(
                        {
                            "invoice_id": invoice_id,
                            "kind": kind,
                            "anchor": anchor,
                            "has_dedicated": False,
                        }
                    )

    return events, invoice_by_id


def allocate_staff(invoices, db_name=DB_NAME):
    """Attach ``staff_allocations`` and ``staff_status`` to each invoice.

    ``staff_status`` is one of:
        * ``diy_pickup``     - self-service job (collect/pickup/DIY/return); no staff needed
        * ``needs_datetime`` - no usable (timed) install/removal datetime
        * ``no_match``       - has timed events but no shift covered them
        * ``matched``        - at least one staff allocation was produced
    """
    events, invoice_by_id = _build_events(invoices)
    if not events:
        return invoices

    # Any invoice with a usable event is at least "no_match" until proven matched.
    for event in events:
        invoice = invoice_by_id[event["invoice_id"]]
        if invoice["staff_status"] == "needs_datetime":
            invoice["staff_status"] = "no_match"

    min_date = min(event["anchor"] for event in events).date() - timedelta(days=1)
    max_date = max(event["anchor"] for event in events).date() + timedelta(days=1)
    shifts = _load_shifts(db_name, min_date, max_date)
    if not shifts:
        return invoices

    shift_events = defaultdict(list)

    # Dedicated match: shift starts near an anchor (accounting for travel lead).
    for event in events:
        anchor = event["anchor"]
        low = anchor - TRAVEL_LEAD - TOLERANCE
        high = anchor + TOLERANCE
        for shift in shifts:
            if low <= shift["shift_start"] <= high:
                shift_events[shift["timesheet_id"]].append(event)
                event["has_dedicated"] = True

    # Absorbed match: an undedicated anchor that falls inside a running shift.
    for event in events:
        if event["has_dedicated"]:
            continue
        anchor = event["anchor"]
        for shift in shifts:
            if shift["shift_start"] <= anchor <= shift["shift_end"]:
                shift_events[shift["timesheet_id"]].append(event)

    shift_by_id = {shift["timesheet_id"]: shift for shift in shifts}

    for timesheet_id, responsible in shift_events.items():
        shift = shift_by_id[timesheet_id]

        # De-duplicate by (invoice, kind), keeping earliest anchor, then sort.
        unique = {}
        for event in responsible:
            key = (event["invoice_id"], event["kind"])
            if key not in unique or event["anchor"] < unique[key]["anchor"]:
                unique[key] = event
        ordered = sorted(unique.values(), key=lambda event: event["anchor"])
        anchors = [event["anchor"] for event in ordered]

        # Raw rostered span, used only to apportion the paid totals below.
        span_hours = (shift["shift_end"] - shift["shift_start"]).total_seconds() / 3600.0

        # Paid totals (breaks excluded); fall back to the raw span when absent.
        rostered_total = shift.get("total_time")
        if rostered_total in (None, ""):
            rostered_total = span_hours
        paid_total = shift.get("timesheet_total_time")

        timesheet_start = shift.get("timesheet_start")
        timesheet_end = shift.get("timesheet_end")
        if timesheet_start and timesheet_end and timesheet_end > timesheet_start:
            timesheet_span = _format_span(timesheet_start, timesheet_end)
        else:
            timesheet_span = ""

        for index, event in enumerate(ordered):
            segment_start = shift["shift_start"] if index == 0 else event["anchor"]
            segment_end = anchors[index + 1] if index + 1 < len(ordered) else shift["shift_end"]
            hours = (segment_end - segment_start).total_seconds() / 3600.0
            if hours <= 0:
                continue

            # Apportion the shift's paid totals by this segment's share of the
            # rostered span, so multi-job shifts split proportionally.
            fraction = hours / span_hours if span_hours > 0 else 0
            rostered_hours = round(rostered_total * fraction, 2)
            paid_hours = round(paid_total * fraction, 2) if paid_total not in (None, "") else None

            invoice = invoice_by_id[event["invoice_id"]]
            invoice["staff_allocations"].append(
                {
                    "name": shift["team_member"],
                    "kind": event["kind"],
                    "rostered_span": _format_span(shift["shift_start"], shift["shift_end"]),
                    "timesheet_span": timesheet_span,
                    "rostered_hours": rostered_hours,
                    "paid_hours": paid_hours,
                }
            )
            invoice["staff_status"] = "matched"

    return invoices

"""Timesheet matching engine: attribute staff shift hours to jobs.

The timesheet export has no job key, so a shift is matched to a job event
(install/removal) purely by time. Multi-day jobs may expose several install
and/or removal anchors; each timed event is matched independently.

* Dedicated match: the shift starts near the job's anchor time, allowing for a
  travel lead (~1h) plus tolerance (+/-2h).
* Absorbed match: a job with no dedicated shift whose anchor falls inside a
  running shift is absorbed by that shift.

When the Excel roster has staff listed for a job, those nicknames (resolved via
admin aliases) are used only as a FILTER on the time-based candidates — never as
a source of new matches. Missing/blank roster rows leave time matching alone.

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
from roster import build_allowed_names, get_aliases, get_roster, list_timesheet_employees

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


# Shared filter for "real" on-site rentals shifts (also used by the
# rostered-vs-paid summary on the report profitability view).
_SHIFT_FILTER_SQL = """
    shift_start IS NOT NULL AND shift_end IS NOT NULL
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
"""


def _load_shifts(db_name, min_date, max_date):
    shifts = []
    with sqlite3.connect(db_name) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                f"""
                SELECT timesheet_id, team_member, shift_start, shift_end,
                       timesheet_start, timesheet_end,
                       total_time, timesheet_total_time, roster_comment
                FROM timesheets
                WHERE {_SHIFT_FILTER_SQL}
                """,
                (min_date.isoformat(), max_date.isoformat()),
            )
            rows = cursor.fetchall()
        except sqlite3.OperationalError as exc:
            # Older DBs may lack roster_comment; retry without it.
            if "roster_comment" in str(exc):
                cursor.execute(
                    f"""
                    SELECT timesheet_id, team_member, shift_start, shift_end,
                           timesheet_start, timesheet_end,
                           total_time, timesheet_total_time
                    FROM timesheets
                    WHERE {_SHIFT_FILTER_SQL}
                    """,
                    (min_date.isoformat(), max_date.isoformat()),
                )
                rows = [(*row, None) for row in cursor.fetchall()]
            else:
                # timesheets table not created yet.
                return shifts

    for (timesheet_id, team_member, shift_start, shift_end,
         timesheet_start, timesheet_end, total_time, timesheet_total_time,
         roster_comment) in rows:
        start = _parse_dt(shift_start)
        end = _parse_dt(shift_end)
        if not start or not end or end <= start:
            continue
        note = (roster_comment or "").strip() or None
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
                "roster_comment": note,
            }
        )
    return shifts


def summarise_rostered_vs_paid(min_date, max_date, db_name=DB_NAME):
    """Compare rostered ``total_time`` vs paid ``timesheet_total_time``.

    Uses the same Braeside/leave/area/status filters as ``_load_shifts``.
    Returns totals only for shifts that have both values present.
    """
    empty = {
        "shift_count": 0,
        "rostered_hours": 0.0,
        "paid_hours": 0.0,
        "diff_hours": 0.0,
        "diff_pct_of_paid": 0.0,
    }
    try:
        with sqlite3.connect(db_name) as conn:
            rows = conn.execute(
                f"""
                SELECT total_time, timesheet_total_time
                FROM timesheets
                WHERE {_SHIFT_FILTER_SQL}
                """,
                (min_date.isoformat(), max_date.isoformat()),
            ).fetchall()
    except sqlite3.OperationalError:
        return empty

    rostered_sum = 0.0
    paid_sum = 0.0
    count = 0
    for total_time, ts_total in rows:
        if total_time in (None, "") or ts_total in (None, ""):
            continue
        try:
            rostered = float(total_time)
            paid = float(ts_total)
        except (TypeError, ValueError):
            continue
        count += 1
        rostered_sum += rostered
        paid_sum += paid

    diff = rostered_sum - paid_sum
    return {
        "shift_count": count,
        "rostered_hours": round(rostered_sum, 2),
        "paid_hours": round(paid_sum, 2),
        "diff_hours": round(diff, 2),
        "diff_pct_of_paid": round((diff / paid_sum * 100.0), 1) if paid_sum else 0.0,
    }


def _iter_invoice_event_anchors(invoice):
    """Yield ``(kind, anchor_dt, label)`` for every usable timed schedule event."""
    events = invoice.get("datetime_events") or []
    emitted = False
    for event in events:
        kind = event.get("type")
        value = event.get("datetime")
        if kind not in ("install", "removal"):
            continue
        if not event.get("ok") or not value or not _has_time(value):
            continue
        anchor = _parse_dt(value)
        if not anchor:
            continue
        emitted = True
        yield kind, anchor, event.get("label") or ""

    if emitted:
        return

    # Fallback for invoices that only have the legacy single-pair fields.
    for kind, value_key, ok_key in _EVENT_FIELDS:
        value = invoice.get(value_key)
        if invoice.get(ok_key) and value and _has_time(value):
            anchor = _parse_dt(value)
            if anchor:
                yield kind, anchor, ""


def _build_events(invoices):
    """Return (events, invoice_by_id). Also sets default staff fields on invoices."""
    events = []
    invoice_by_id = {}

    for invoice in invoices:
        invoice["staff_allocations"] = []
        invoice["paid_hours_total"] = 0.0
        invoice["staff_match_sources"] = []

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

        for kind, anchor, label in _iter_invoice_event_anchors(invoice):
            events.append(
                {
                    "invoice_id": invoice_id,
                    "kind": kind,
                    "anchor": anchor,
                    "label": label,
                    "has_dedicated": False,
                }
            )

    return events, invoice_by_id


def _roster_allowed_for_event(event, invoice, roster, aliases, employees):
    """Return (allowed_names_or_None, has_roster_signal).

    ``allowed_names`` is None when the roster has no staff for this job event
    (caller must not filter). Otherwise it is the set of timesheet names that
    are permitted to stay attached to the event.
    """
    if roster is None or not roster.entry_count:
        return None, False

    job_text = invoice.get("job_text") or ""
    nicknames = roster.rostered_staff(job_text, event["kind"], event["anchor"].date())
    if not nicknames:
        return None, False

    allowed = build_allowed_names(nicknames, aliases, employees)
    # Roster signal exists but no nickname resolved yet — still filter using
    # an empty allow-list would wipe everyone. Prefer keeping time matches
    # until aliases are configured for at least one nickname.
    if not allowed:
        return None, False
    return allowed, True


def allocate_staff(invoices, db_name=DB_NAME):
    """Attach ``staff_allocations`` and ``staff_status`` to each invoice.

    ``staff_status`` is one of:
        * ``diy_pickup``     - self-service job (collect/pickup/DIY/return); no staff needed
        * ``needs_datetime`` - no usable (timed) install/removal datetime
        * ``no_match``       - has timed events but no shift covered them
        * ``matched``        - at least one staff allocation was produced

    Each allocation includes ``match_source``:
        * ``time``         - time window only (no roster filter applied)
        * ``time+roster``  - time match kept because the person is on the Excel roster
    """
    events, invoice_by_id = _build_events(invoices)
    if not events:
        return invoices

    # Any invoice with a usable event is at least "no_match" until proven matched.
    for event in events:
        invoice = invoice_by_id[event["invoice_id"]]
        if invoice["staff_status"] == "needs_datetime":
            invoice["staff_status"] = "no_match"
        invoice["staff_match_sources"] = []

    min_date = min(event["anchor"] for event in events).date() - timedelta(days=1)
    max_date = max(event["anchor"] for event in events).date() + timedelta(days=1)
    shifts = _load_shifts(db_name, min_date, max_date)
    if not shifts:
        return invoices

    roster = get_roster()
    aliases = get_aliases()
    employees = set(list_timesheet_employees(db_name))

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

    # Roster filter: when the Excel lists staff for a job event, drop time
    # matches whose team_member is not on that list (after alias resolution).
    for timesheet_id, responsible in list(shift_events.items()):
        shift = next((s for s in shifts if s["timesheet_id"] == timesheet_id), None)
        if not shift:
            continue
        kept = []
        for event in responsible:
            invoice = invoice_by_id[event["invoice_id"]]
            allowed, has_signal = _roster_allowed_for_event(
                event, invoice, roster, aliases, employees
            )
            if has_signal and shift["team_member"] not in allowed:
                continue
            # Tag the event so apportioning can set match_source on the allocation.
            event = dict(event)
            event["roster_filtered"] = bool(has_signal)
            kept.append(event)
        if kept:
            shift_events[timesheet_id] = kept
        else:
            del shift_events[timesheet_id]

    shift_by_id = {shift["timesheet_id"]: shift for shift in shifts}

    for timesheet_id, responsible in shift_events.items():
        shift = shift_by_id[timesheet_id]

        # De-duplicate exact anchors, keeping earliest label, then sort.
        # Same kind on different days must stay distinct so multi-day jobs
        # can match a shift to each day's install/removal.
        unique = {}
        for event in responsible:
            key = (event["invoice_id"], event["kind"], event["anchor"])
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

            match_source = "time+roster" if event.get("roster_filtered") else "time"
            invoice = invoice_by_id[event["invoice_id"]]
            invoice["staff_allocations"].append(
                {
                    "name": shift["team_member"],
                    "kind": event["kind"],
                    "label": event.get("label") or "",
                    "rostered_span": _format_span(shift["shift_start"], shift["shift_end"]),
                    "timesheet_span": timesheet_span,
                    "rostered_hours": rostered_hours,
                    "paid_hours": paid_hours,
                    "match_source": match_source,
                    "roster_note": shift.get("roster_comment") or "",
                }
            )
            invoice["staff_status"] = "matched"
            if match_source not in invoice["staff_match_sources"]:
                invoice["staff_match_sources"].append(match_source)

    for invoice in invoices:
        paid_total = 0.0
        for allocation in invoice.get("staff_allocations") or []:
            paid_hours = allocation.get("paid_hours")
            if paid_hours not in (None, ""):
                paid_total += float(paid_hours)
        invoice["paid_hours_total"] = round(paid_total, 2)

    return invoices

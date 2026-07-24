"""Regex + dateutil extraction of install/removal datetimes from invoice text.

Schedule lines are found date-first: any line containing a date hint is parsed,
then the text before the date is used to classify install vs removal. Multi-day
jobs therefore yield multiple events (each becomes a timesheet matching anchor).

A value that only resolves to a date (no time-of-day) is marked ``ok=False`` so
the caller can route it to the on-demand AI fallback when nothing usable exists.
"""

import logging
import re
from datetime import datetime
from dateutil import parser as date_parser

logger = logging.getLogger(__name__)

# Plausible year window. Fuzzy parsing product dimensions ("4.8m x 2.1m")
# can produce nonsense datetimes; anything outside this range is discarded so
# it routes to the AI/manual fallback instead of showing a wrong date.
_MIN_YEAR = 2018
_MAX_YEAR = datetime.now().year + 3

# Start of a date fragment on a schedule line (weekday, day+month, or numeric).
_DATE_START_RE = re.compile(
    r"(?:"
    r"\b(?:mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:r(?:s(?:day)?)?)?|"
    r"fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b|"
    r"\b\d{1,2}(?:st|nd|rd|th)?\s+"
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?)\b|"
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?\b|"
    r"\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}\b|"
    r"\b\d{1,2}[-/]\d{1,2}[-/]20\d{2}\b"
    r")",
    re.IGNORECASE,
)

# Prefix text that marks an install / bump-in style activity.
_INSTALL_CLASSIFY_RE = re.compile(
    r"\b(?:"
    r"install(?:ation|ed|ing)?|"
    r"collect(?:ion|ed|ing)?|"
    r"pick\s*[-\s]?up|"
    r"delivery|deliver(?:ed|ing)?|"
    r"site[-\s]?mark|"
    r"drop\s*weights?|"
    r"set\s*up|setup|"
    r"bump\s*in|"
    r"drop\s*off|dropoff"
    r")\b",
    re.IGNORECASE,
)

# Prefix text that marks a removal / bump-out style activity.
_REMOVAL_CLASSIFY_RE = re.compile(
    r"\b(?:"
    r"remov(?:e|al|ed|ing)?|"
    r"return(?:ed|ing)?|"
    r"bump\s*out|"
    r"pack\s*down|packdown"
    r")\b",
    re.IGNORECASE,
)

# Keywords that mark a self-service (DIY/Pickup) job: the customer collects and
# returns the products themselves, so no staff shift should be matched to it.
# Note: "delivery" is deliberately excluded - that means the company delivers,
# which does require staff.
_DIY_PICKUP_RE = re.compile(
    r"\b(?:diy|collect(?:s|ed|ing|ion)?|pick\s*[-\s]?up(?:s)?|return(?:s|ed|ing)?)\b",
    re.IGNORECASE,
)

# A time-of-day token, e.g. 9am, 9:30am, 2.15pm, 14:00.
_TIME_RE = re.compile(
    r"\b\d{1,2}(?:[:.]\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)\b|\b\d{1,2}:\d{2}\b",
    re.IGNORECASE,
)

# Range separators, used to split "9am - 4pm" so we keep the start value. Only
# whitespace-delimited hyphens/dashes count so ISO dates ("2025-06-29") survive.
_RANGE_SPLIT_RE = re.compile(r"\s+(?:-|\u2013|\u2014|to|until|till|through)\s+", re.IGNORECASE)

# Words that add no date/time value and can confuse the fuzzy parser.
_NOISE_RE = re.compile(r"\b(?:tbc|tba|approx(?:imately)?|around|circa|est|from)\b", re.IGNORECASE)

# Leading separators to strip from a captured fragment (":", "-", "@", spaces).
_LEAD_STRIP = " \t:-\u2013\u2014@>"

# Product quantity lines ("21 x 3m marquee...") are not schedule rows even when
# they casually mention "install Sunday morning".
_PRODUCT_LINE_RE = re.compile(r"^\d+\s*x\b", re.IGNORECASE)

# Bare weekdays ("Sunday morning") are too vague; require a calendar day
# (day+month and/or an explicit year) before accepting a match.
_CALENDAR_DATE_RE = re.compile(
    r"\b20\d{2}\b|"
    r"\b\d{1,2}(?:st|nd|rd|th)?\s+"
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?)\b|"
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?\b|"
    r"\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}\b|"
    r"\b\d{1,2}[-/]\d{1,2}[-/]20\d{2}\b",
    re.IGNORECASE,
)


def _parse_segment(segment):
    """Return ``(iso_value_or_None, ok)`` for a captured fragment.

    ``ok`` is only True when the fragment contains an explicit time-of-day.
    """
    if not segment:
        return None, False

    if not _CALENDAR_DATE_RE.search(segment):
        return None, False

    # For a range like "9am - 4pm" take the start value.
    start = _RANGE_SPLIT_RE.split(segment)[0]
    has_time = bool(_TIME_RE.search(start))
    cleaned = _NOISE_RE.sub(" ", start).replace("@", " ").strip()

    if not cleaned:
        return None, False

    try:
        parsed = date_parser.parse(cleaned, fuzzy=True)
    except (ValueError, OverflowError, TypeError):
        return None, False

    if not (_MIN_YEAR <= parsed.year <= _MAX_YEAR):
        return None, False

    # Store naive local time for consistent downstream comparisons.
    parsed = parsed.replace(microsecond=0, tzinfo=None)

    if has_time:
        return parsed.isoformat(), True

    # A date with no time is not directly usable for matching.
    return parsed.date().isoformat(), False


def _classify_prefix(prefix):
    """Return ``\"install\"``, ``\"removal\"``, or None from line text before the date."""
    if not prefix:
        return None
    # Removal first so "remove after install prep" style phrases lean removal.
    if _REMOVAL_CLASSIFY_RE.search(prefix):
        return "removal"
    if _INSTALL_CLASSIFY_RE.search(prefix):
        return "install"
    return None


def _sort_key(iso_value):
    """Sortable key for ISO date or datetime strings."""
    return iso_value or ""


def _extract_events_from_text(text):
    """Return classified schedule events found in one text block."""
    events = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or _PRODUCT_LINE_RE.match(line):
            continue

        match = _DATE_START_RE.search(line)
        if not match:
            continue

        prefix = line[: match.start()].strip().rstrip(_LEAD_STRIP).strip()
        kind = _classify_prefix(prefix)
        if kind is None:
            # Require an explicit install/removal-style label; casual date
            # mentions in notes are ignored rather than guessed.
            continue

        segment = line[match.start() :].lstrip(_LEAD_STRIP).strip()
        value, ok = _parse_segment(segment)
        if not value:
            continue

        events.append(
            {
                "type": kind,
                "datetime": value,
                "label": prefix,
                "ok": ok,
            }
        )
    return events


def _dedupe_events(events):
    """Drop exact duplicates while preserving order."""
    seen = set()
    unique = []
    for event in events:
        key = (event.get("type"), event.get("datetime"), event.get("label") or "")
        if key in seen:
            continue
        seen.add(key)
        unique.append(event)
    return unique


def _pick_display(group, prefer_last=False):
    """Choose the primary display datetime for a type group.

    Prefers timed (ok) events; falls back to date-only. Earliest by default,
    latest when ``prefer_last`` is True.
    """
    if not group:
        return None, False

    ok_ones = [event for event in group if event.get("ok")]
    pool = ok_ones or group
    chosen = max(pool, key=lambda event: _sort_key(event["datetime"])) if prefer_last else min(
        pool, key=lambda event: _sort_key(event["datetime"])
    )
    return chosen["datetime"], bool(chosen.get("ok"))


def events_from_install_removal(install_datetime, removal_datetime):
    """Build a minimal events list from a single install/removal pair (AI cache)."""
    events = []
    if install_datetime:
        events.append(
            {
                "type": "install",
                "datetime": install_datetime,
                "label": "",
                "ok": isinstance(install_datetime, str) and "T" in install_datetime,
            }
        )
    if removal_datetime:
        events.append(
            {
                "type": "removal",
                "datetime": removal_datetime,
                "label": "",
                "ok": isinstance(removal_datetime, str) and "T" in removal_datetime,
            }
        )
    return events


def parse_install_removal(invoice_summary, job_summary=None):
    """Extract install/removal schedule events from invoice text.

    Scans ``invoice_summary`` first, then ``job_summary``. Returns a dict with:

    * ``events`` – list of ``{type, datetime, label, ok}``
    * ``install`` / ``removal`` – primary display ISO strings (earliest of each)
    * ``install_ok`` / ``removal_ok`` – whether the primary value has a time-of-day
    """
    events = []
    for text in (invoice_summary, job_summary):
        if text:
            events.extend(_extract_events_from_text(text))

    events = _dedupe_events(events)
    events.sort(key=lambda event: (_sort_key(event["datetime"]), event["type"]))

    installs = [event for event in events if event["type"] == "install"]
    removals = [event for event in events if event["type"] == "removal"]
    install_value, install_ok = _pick_display(installs, prefer_last=False)
    removal_value, removal_ok = _pick_display(removals, prefer_last=False)

    return {
        "install": install_value,
        "removal": removal_value,
        "install_ok": install_ok,
        "removal_ok": removal_ok,
        "events": events,
    }


def is_diy_pickup(invoice_summary, job_summary=None):
    """Return True if the invoice text marks a self-service (DIY/Pickup) job.

    A job is treated as DIY/Pickup when the text mentions collect / pickup / DIY /
    return, meaning the customer collects and returns the products themselves and
    no staff is required. Scans ``invoice_summary`` and ``job_summary``.
    """
    for text in (invoice_summary, job_summary):
        if text and _DIY_PICKUP_RE.search(text):
            return True
    return False

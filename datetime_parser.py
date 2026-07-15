"""Regex + dateutil extraction of install/removal datetimes from invoice text.

Follows the same pattern as ``update_job_types.extract_pickup_date``: try a set of
labelled regular expressions, then fall back to ``dateutil.parser.parse(fuzzy=True)``
to turn the captured fragment into a real datetime.

The install labels are Install / Collect / Pickup / Delivery and the removal labels
are Remove / Return. A value that only resolves to a date (no time-of-day) is marked
as ``not ok`` so the caller can route it to the on-demand AI fallback, because the
timesheet matching engine needs a time-of-day to work.
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

# Labels that mark the start (install) of a job.
_INSTALL_LABEL_RE = re.compile(
    r"\b(?:install(?:ation|ed|ing)?|collect(?:ion|ed|ing)?|pick\s*[-\s]?up|"
    r"delivery|deliver(?:ed|ing)?)\b",
    re.IGNORECASE,
)

# Labels that mark the end (removal) of a job.
_REMOVAL_LABEL_RE = re.compile(
    r"\b(?:remov(?:e|al|ed|ing)?|return(?:ed|ing)?)\b",
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
_NOISE_RE = re.compile(r"\b(?:tbc|tba|approx(?:imately)?|around|circa|est)\b", re.IGNORECASE)

# Leading separators to strip from a captured fragment (":", "-", "@", spaces).
_LEAD_STRIP = " \t:-\u2013\u2014@>"


def _segments_after_label(text, label_re):
    """Yield the remainder of each line that starts with a matching label."""
    for match in label_re.finditer(text):
        line_end = text.find("\n", match.end())
        if line_end == -1:
            line_end = len(text)
        segment = text[match.end():line_end].lstrip(_LEAD_STRIP).strip()
        if segment:
            yield segment


def _parse_segment(segment):
    """Return ``(iso_value_or_None, ok)`` for a captured fragment.

    ``ok`` is only True when the fragment contains an explicit time-of-day.
    """
    if not segment:
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


def _extract(text, label_re):
    """Return the best ``(value, ok)`` for a label in a single text block."""
    best_value = None
    best_ok = False
    for segment in _segments_after_label(text, label_re):
        value, ok = _parse_segment(segment)
        if not value:
            continue
        if ok:
            return value, True
        if best_value is None:
            best_value = value
    return best_value, best_ok


def parse_install_removal(invoice_summary, job_summary=None):
    """Extract install/removal datetimes from invoice text.

    Scans ``invoice_summary`` first, then ``job_summary``. Returns a dict with
    ``install``/``removal`` ISO strings (or None) and ``install_ok``/``removal_ok``
    flags indicating whether a usable time-of-day was found.
    """
    result = {"install": None, "removal": None, "install_ok": False, "removal_ok": False}

    for text in (invoice_summary, job_summary):
        if not text:
            continue

        if not result["install_ok"]:
            value, ok = _extract(text, _INSTALL_LABEL_RE)
            if value and (result["install"] is None or ok):
                result["install"] = value
                result["install_ok"] = ok

        if not result["removal_ok"]:
            value, ok = _extract(text, _REMOVAL_LABEL_RE)
            if value and (result["removal"] is None or ok):
                result["removal"] = value
                result["removal_ok"] = ok

    return result


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

"""On-demand Ollama fallback for parsing install/removal datetimes.

Sends the invoice/job summary text to a locally running Ollama instance
(``llama3:8b``) and asks for a strict JSON object of ISO datetimes. Used only
when the regex parser fails a field and the user clicks "Parse with AI".
"""

import json
import logging
import requests
from dateutil import parser as date_parser

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3:8b"

# JSON schema handed to Ollama's ``format`` so the response is constrained.
_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "install_datetime": {"type": "string"},
        "removal_datetime": {"type": "string"},
    },
    "required": ["install_datetime", "removal_datetime"],
}

_PROMPT_TEMPLATE = (
    "You extract scheduling datetimes from a marquee/equipment hire job's notes.\n"
    "The install (also called delivery, set up, drop off or bump in) is when the "
    "equipment is put up. The removal (also called pack down, collection, return or "
    "bump out) is when it is taken away.\n\n"
    "Return ONLY JSON with keys \"install_datetime\" and \"removal_datetime\" in "
    "ISO 8601 format (YYYY-MM-DDTHH:MM:SS), using 24-hour time. If a value is not "
    "present, return an empty string for it. Do not invent a year, month, day or "
    "time that is not implied by the text. If a time range is given, use the start "
    "time.\n\n"
    "Notes:\n\"\"\"\n{text}\n\"\"\"\n"
)


def _normalise(value):
    """Coerce a model-supplied datetime string to a clean ISO string or None."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return date_parser.parse(text).replace(microsecond=0, tzinfo=None).isoformat()
    except (ValueError, OverflowError, TypeError):
        logger.warning("Ollama returned an unparseable datetime: %r", value)
        return None


def parse_datetimes_with_ollama(text, timeout=180):
    """Ask Ollama for install/removal datetimes.

    Returns ``{"install_datetime": iso_or_None, "removal_datetime": iso_or_None}``.
    Raises ``requests.RequestException`` if the service is unreachable and
    ``ValueError`` if the response is not valid JSON.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": _PROMPT_TEMPLATE.format(text=text or ""),
        "format": _RESPONSE_SCHEMA,
        "stream": False,
        "options": {"temperature": 0},
    }

    response = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
    response.raise_for_status()

    body = response.json()
    content = (body.get("response") or "").strip()
    if not content:
        raise ValueError("Ollama returned an empty response")

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Ollama returned invalid JSON: {content!r}") from exc

    return {
        "install_datetime": _normalise(parsed.get("install_datetime")),
        "removal_datetime": _normalise(parsed.get("removal_datetime")),
    }

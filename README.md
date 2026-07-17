# FieldMagic Reader

A Flask web app that syncs jobs and customer invoices from the [FieldMagic](https://www.fieldmagic.co/) API, caches them in a local SQLite database, and produces financial-year reports. It parses install/removal datetimes from invoice/job notes (regex first, with an optional local AI fallback) and matches staff timesheet shifts to jobs to attribute labour hours.

## Features

- **Job sync** – pulls open jobs from the FieldMagic API and caches them locally.
- **FY reports** – FY25 and FY26 customer-invoice reports with line items and totals.
- **Datetime parsing** – extracts install/removal times from invoice notes via regex, with an optional "Parse with AI" fallback using a local [Ollama](https://ollama.com/) model.
- **Timesheet matching** – allocates staff shift hours to jobs by time proximity.

## Requirements

- Python 3.9+
- (Optional) [Ollama](https://ollama.com/) running locally with the `llama3:8b` model, only needed for the "Parse with AI" button.

## Setup

From the project root (`FieldMagicReader`):

```bash
# 1. Create and activate a virtual environment
python -m venv venv

# Windows (PowerShell)
venv\Scripts\Activate.ps1

# macOS / Linux
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt
```

## Running the app

```bash
python app.py
```

Then open http://localhost:5000 in your browser.

On startup the app will:

1. Initialise the SQLite database (`jobs_cache.db`, created automatically).
2. Import timesheets from `Timesheet details.json` if that file is present (otherwise staff matching stays empty until you add it).
3. Kick off a background sync with the FieldMagic API.

The server runs on `0.0.0.0:5000` with debug mode enabled.

## Key routes

| Route | Description |
| --- | --- |
| `/` | Home page – paginated, searchable list of cached jobs |
| `/refresh` | Triggers a full background re-sync from the API |
| `/reports?year=fy25` / `?year=fy26` | Financial-year invoice reports |
| `/invoices/<invoice_id>` | Invoice detail page |
| `/admin` | Admin portal (shows parse errors) |

## Optional: AI datetime parsing (Ollama)

The "Parse with AI" feature calls a local Ollama instance at `http://localhost:11434` using the `llama3:8b` model. To enable it:

```bash
ollama pull llama3:8b
ollama serve
```

If Ollama is not running, the rest of the app works normally; only the AI parse button will report the service as unavailable.

## Project structure

| File | Purpose |
| --- | --- |
| `app.py` | Flask app, routes, API sync, and database setup |
| `update_job_types.py` | Post-sync enrichment of job types, addresses, and pickup dates |
| `datetime_parser.py` | Regex-based install/removal datetime parsing |
| `ollama_client.py` | Optional local-AI datetime parsing fallback |
| `timesheets.py` | Matches timesheet shifts to jobs and allocates hours |
| `import_timesheets.py` | Loads `Timesheet details.json` into the database |
| `templates/` | Jinja2 HTML templates |
| `static/` | CSS and JavaScript assets |
| `jobs_cache.db` | SQLite cache (auto-generated) |
| `performance.log` | Runtime log output (auto-generated) |

## Notes

- The FieldMagic API credentials are currently hardcoded in `app.py`. For anything beyond local use, move these into environment variables.

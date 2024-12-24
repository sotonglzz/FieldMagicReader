import sqlite3
import requests
import time
from base64 import b64encode
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for

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
            last_modified TIMESTAMP
        )
        """)
        conn.commit()

def basic_auth(username, password):
    token = b64encode(f"{username}:{password}".encode('utf-8')).decode("ascii")
    return f'Basic {token}'

# Fetch Data from API with Pagination
def fetch_jobs(last_modified=None):
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
            print(f"Failed to fetch jobs: {response.status_code} {response.text}")
            break

        response_data = response.json()
        jobs = response_data.get("data", [])
        all_jobs.extend(jobs)

        next_token = response_data.get("next_token")
        if not next_token:
            break

    return all_jobs

# Sync with API
def sync_with_api(overall=False):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()

        last_modified = None if overall else (datetime.now() - timedelta(hours=1)).isoformat()
        jobs = fetch_jobs(last_modified)

        for job in jobs:
            last_modified_value = job.get("last_modified", None)
            if last_modified_value:
                last_modified_value = datetime.fromisoformat(last_modified_value)
            
            cursor.execute("""
            INSERT OR REPLACE INTO jobs (job_number, job_summary, job_location, last_modified)
            VALUES (?, ?, ?, ?)
            """, (
                job["job_number"],
                job.get("job_summary", "No Summary"),
                job.get("address_text", "No Location"),
                last_modified_value
            ))
        conn.commit()

# Get Cached Jobs
def get_cached_jobs(page=1, per_page=20, search_query=None):
    offset = (page - 1) * per_page
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        
        if search_query:
            cursor.execute("""
                SELECT job_number, job_summary, job_location, last_modified
                FROM jobs
                WHERE job_summary LIKE ? OR job_location LIKE ?
                ORDER BY last_modified DESC
                LIMIT ? OFFSET ?
            """, (f"%{search_query}%", f"%{search_query}%", per_page, offset))
        else:
            cursor.execute("""
                SELECT job_number, job_summary, job_location, last_modified
                FROM jobs
                ORDER BY last_modified DESC
                LIMIT ? OFFSET ?
            """, (per_page, offset))
        
        jobs = cursor.fetchall()
        
        # Get total job count for pagination
        cursor.execute("""
            SELECT COUNT(*)
            FROM jobs
            WHERE job_summary LIKE ? OR job_location LIKE ?
        """, (f"%{search_query}%", f"%{search_query}%" if search_query else "%%"))
        total_jobs = cursor.fetchone()[0]

    return jobs, total_jobs


@app.route("/")
def home():
    page = int(request.args.get('page', 1))
    search_query = request.args.get('search', None)
    jobs, total_jobs = get_cached_jobs(page=page, per_page=20, search_query=search_query)
    total_pages = (total_jobs + 19) // 20  # Calculate total pages
    return render_template(
        "index.html",
        jobs=jobs,
        current_page=page,
        total_pages=total_pages,
        search_query=search_query
    )

@app.route("/refresh")
def refresh():
  
    sync_with_api(overall=True)
    return redirect(url_for("home"))

if __name__ == "__main__":
    init_db()
    sync_with_api()
    app.run(debug=True)

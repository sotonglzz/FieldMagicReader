import sqlite3

DB_NAME = "jobs_cache.db"

def add_date_completed_column():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        # Check if the column already exists
        cursor.execute("PRAGMA table_info(jobs)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'date_completed' not in columns:
            cursor.execute("ALTER TABLE jobs ADD COLUMN date_completed TEXT")
            print("Added 'date_completed' column to the 'jobs' table.")
        else:
            print("'date_completed' column already exists.")

add_date_completed_column()

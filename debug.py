import sqlite3

DB_NAME = "jobs_cache.db"

def add_id_column():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        # Check if the column already exists
        cursor.execute("PRAGMA table_info(jobs)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'id' not in columns:
            cursor.execute("ALTER TABLE jobs ADD COLUMN id TEXT")
            print("Added 'id' column to the 'jobs' table.")
        else:
            print("'id' column already exists.")

add_id_column()

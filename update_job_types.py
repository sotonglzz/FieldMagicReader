import sqlite3
import re
import logging
from datetime import datetime
from dateutil import parser # This is for a more flexible date parsing

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Intialized Global Variables
DB_NAME = "jobs_cache.db"
PARSE_ERRORS = [] # Store parsing errors

def extract_job_type(job_summary, address):
    """
    Extracts the job type from the job summary or address.
    """
    if job_summary:
        if "Install" in job_summary or "Delivery" in job_summary:
            return "Delivery/Install"
        elif "DIY" in job_summary or "Pickup" in job_summary:
            return "DIY/Pickup"


    if address:
        if "Capella Crescent" in address:
            return "DIY/Pickup"
        else:
            return "Delivery/Install"
    return "Unknown"

def update_job_types():
    """
    Updates the job_type column in the database based on job_summary or address.
    """
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        # Fetch jobs with missing or empty job_type
        cursor.execute("""
            SELECT job_number, job_summary, job_location, job_type
            FROM jobs
            WHERE job_type IS NULL OR job_type = '' OR job_type = 'Unknown'
        """)
        jobs = cursor.fetchall()

        logging.info(f"Found {len(jobs)} jobs with missing job_type.")
        for job in jobs:
            job_number, job_summary, address, current_type = job
            new_job_type = extract_job_type(job_summary, address)
            #logging.info(f"Updating Job {job_number}: {new_job_type}")
            # Update the job_type in the database
            cursor.execute("""
                UPDATE jobs
                SET job_type = ?
                WHERE job_number = ?
            """, (new_job_type, job_number))

        conn.commit()
        logging.info(f"Job types updated for {len(jobs)} jobs.")
        
def update_job_addresses():
    """
    Updates the job_location to 'Capella' if job_type is 'DIY/Pickup'.
    """
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()

        # Fetch jobs where job_type is 'DIY/Pickup' but address is not 'Capella'
        cursor.execute("""
            SELECT job_number, job_location, job_type
            FROM jobs
            WHERE job_type = 'DIY/Pickup' AND job_location != 'Capella'
        """)
        jobs = cursor.fetchall()

        logging.info(f"Found {len(jobs)} jobs where address needs to be updated to 'Capella'.")
        for job in jobs:
            job_number, current_address, job_type = job
            #logging.info(f"Updating address for Job {job_number} from '{current_address}' to 'Capella'.")
            
            # Update the job_location in the database
            cursor.execute("""
                UPDATE jobs
                SET job_location = ?
                WHERE job_number = ?
            """, ('Capella', job_number))

        conn.commit()
        logging.info(f"Updated addresses for {len(jobs)} jobs.")

def extract_pickup_date(job_summary):
    """
    Extracts the pickup date from the job summary if it contains a date.
    Returns the date in 'YYYY-MM-DD' format or None if not found.
    """
    if not job_summary:
        return None

    try:
        # Match the date using regex (accounts for various patterns)
        date_match = re.search(
            r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+\d{1,2}(?:st|nd|rd|th)?\s+\w+\s+\d{4}\b",
            job_summary,
        )
        if date_match:
            date_str = date_match.group(0)
            # Parse using dateutil.parser for flexibility
            parsed_date = parser.parse(date_str)
            return parsed_date.strftime("%Y-%m-%d")
    except Exception as e:
        logging.error(f"Error parsing date from job summary: '{job_summary}' - {e}")
        return None

    return None

def update_pickup_dates():
    """
    Updates the job_date column in the database based on the pickup date in the job_summary.
    Also logs any parsing errors.
    """
    global PARSE_ERRORS
    PARSE_ERRORS.clear()  # Clear previous errors

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()

        # Fetch jobs with job_type 'DIY/Pickup' and missing or empty job_date
        cursor.execute("""
            SELECT job_number, job_summary, job_date
            FROM jobs
            WHERE job_type = 'DIY/Pickup' AND (job_date IS NULL OR job_date = '' OR job_date = 'Unknown')
        """)
        jobs = cursor.fetchall()

        logging.info(f"Found {len(jobs)} jobs with missing pickup dates.")
        for job in jobs:
            job_number, job_summary, current_date = job
            new_date = extract_pickup_date(job_summary)
            if new_date:
                logging.info(f"Updating Job {job_number}: Pickup Date to {new_date}")
                # Update the job_date in the database
                cursor.execute("""
                    UPDATE jobs
                    SET job_date = ?
                    WHERE job_number = ?
                """, (new_date, job_number))
            else:
                PARSE_ERRORS.append(
                    {"job_number": job_number, "job_summary": job_summary}
                )

        conn.commit()
        logging.info(f"Pickup dates updated for {len(jobs)} jobs.")


if __name__ == "__main__":
    update_job_types()
    update_job_addresses()
    update_pickup_dates()
    

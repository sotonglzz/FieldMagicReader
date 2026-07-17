"""Quick comparison: rostered hours (total_time) vs paid hours
(timesheet_total_time) for the shifts that pass timesheets.py's filters
(ignoring Braeside/Office, sales/admin/etc, leaves, and non-finalised rows).
"""

import sqlite3

DB_NAME = "jobs_cache.db"

# Same WHERE clause as timesheets._load_shifts, minus the date-range bound.
FILTER_SQL = """
    SELECT total_time, timesheet_total_time
    FROM timesheets
    WHERE shift_start IS NOT NULL AND shift_end IS NOT NULL
      AND (location IS NULL
           OR (location NOT LIKE '%Braeside%'
               AND location NOT LIKE '%Office%'))
      AND (area IS NULL
           OR (area NOT LIKE '%Sales%'
               AND area NOT LIKE '%Admin%'
               AND area NOT LIKE '%Maintenance%'
               AND area NOT LIKE '%Run 01%'
               AND area NOT LIKE '%Run01%'))
      AND (leave_policy IS NULL OR leave_policy = '')
      AND status IN ('Pay approved', 'Paid', 'Time approved')
"""


def main():
    with sqlite3.connect(DB_NAME) as conn:
        rows = conn.execute(FILTER_SQL).fetchall()

    n = 0
    rostered_sum = 0.0
    paid_sum = 0.0
    both = 0
    over = 0   # rostered > paid
    under = 0  # rostered < paid
    exact = 0

    for total_time, ts_total in rows:
        if total_time in (None, "") or ts_total in (None, ""):
            continue
        try:
            r = float(total_time)
            p = float(ts_total)
        except (TypeError, ValueError):
            continue
        n += 1
        rostered_sum += r
        paid_sum += p
        both += 1
        if r > p:
            over += 1
        elif r < p:
            under += 1
        else:
            exact += 1

    print(f"Shifts passing filters (with both totals): {n}")
    print(f"Total rostered hours: {rostered_sum:,.2f}")
    print(f"Total paid hours:     {paid_sum:,.2f}")
    diff = rostered_sum - paid_sum
    print(f"Difference (rostered - paid): {diff:,.2f} h "
          f"({(diff / paid_sum * 100 if paid_sum else 0):+.1f}% of paid)")
    if n:
        print(f"Avg rostered/shift: {rostered_sum / n:.2f} h")
        print(f"Avg paid/shift:     {paid_sum / n:.2f} h")
    print(f"Shifts over-rostered (rostered > paid):  {over}")
    print(f"Shifts under-rostered (rostered < paid): {under}")
    print(f"Shifts exact:                            {exact}")


if __name__ == "__main__":
    main()

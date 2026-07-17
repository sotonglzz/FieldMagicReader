import openpyxl
import re
import io
import sqlite3

FN = 'Schedule July 2025 - June 2026 - copy.xlsx'
OUT = io.open('_xlsx_report.txt', 'w', encoding='utf-8')

def w(*args):
    print(*args, file=OUT)

wb = openpyxl.load_workbook(FN, read_only=True, data_only=True)

MONTHS = ['July','August','September','October','November','December',
          'January','February','March','April','May','June']

jobnum_re = re.compile(r'\(?\b(Q?\d{3,6}(?:-\d+)?)\)')
all_jobnums = []

for m in MONTHS:
    ws = wb[m]
    rows = list(ws.iter_rows(values_only=True))
    w('\n' + '=' * 80)
    w(f'MONTH: {m}  (rows={len(rows)})')
    w('=' * 80)
    colmap = None
    total_jobrows = with_jobnum = with_staff = with_times = with_type = 0
    sample = []
    for r in rows:
        vals = list(r)
        if vals and vals[0] == 'Arrive':
            colmap = {}
            for i, c in enumerate(vals):
                if c is not None:
                    colmap[str(c).strip().lower()] = i
            continue
        if colmap is None:
            continue
        def get(name):
            i = colmap.get(name)
            return vals[i] if (i is not None and i < len(vals)) else None
        suburb = get('suburb')
        if not suburb:
            continue
        arrive = get('arrive'); finish = get('finish')
        typ = get('type'); staff = get('staff')
        total_jobrows += 1
        jm = jobnum_re.search(str(suburb))
        if jm:
            with_jobnum += 1
            all_jobnums.append(jm.group(1))
        if staff and str(staff).strip():
            with_staff += 1
        if arrive or finish:
            with_times += 1
        if typ and str(typ).strip():
            with_type += 1
        if len(sample) < 10:
            sample.append((arrive, finish, typ, suburb, staff))
    w(f'colmap: {colmap}')
    w(f'job rows: {total_jobrows} | jobnum(): {with_jobnum} | staff: {with_staff} | times: {with_times} | type: {with_type}')
    w('  --- sample (arrive|finish|type|suburb|staff) ---')
    for s in sample:
        w('   ', ' || '.join('' if x is None else str(x) for x in s))

# --- Job number formats found ---
w('\n' + '=' * 80); w('JOB NUMBER SAMPLES FROM EXCEL (first 60 unique)'); w('=' * 80)
uniq = sorted(set(all_jobnums))
w('total jobnum tokens:', len(all_jobnums), '| unique:', len(uniq))
w(', '.join(uniq[:60]))

# --- DB job_number formats ---
w('\n' + '=' * 80); w('DB job_number + invoice job linkage'); w('=' * 80)
try:
    conn = sqlite3.connect('jobs_cache.db')
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    w('tables:', [t[0] for t in cur.fetchall()])
    cur.execute('SELECT job_number, job_summary FROM jobs LIMIT 20')
    w('-- jobs.job_number samples --')
    for jn, js in cur.fetchall():
        w('  ', repr(jn), '|', (str(js)[:70] if js else ''))
    cur.execute('SELECT COUNT(*) FROM jobs')
    w('jobs count:', cur.fetchone()[0])
except Exception as e:
    w('DB error:', e)

OUT.close()
print('done')

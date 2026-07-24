# Implementation Plan: Deputy Roster Shift Notes for Job Matching

## Goal

Use Deputy **rostered shift notes** (typically suburb / job nicknames such as `Midsumma`) as the primary signal for attributing staff timesheets to FieldMagic jobs in the `/reports` **Job Profitability** view.

Operators must be able to **see each staff member’s roster shift note** next to their allocation, so matching can be confirmed by eye without leaving the report.

## Problem today

Job Profitability labour comes from `timesheets.py`:

1. **Time window matching** — a shift start near an install/removal attaches that shift to the job (`TRAVEL_LEAD` + `TOLERANCE`).
2. **Excel roster filter** — when the schedule spreadsheet lists staff for a job number, non-listed people are dropped. Excel never *creates* or *reassigns* matches.
3. **Multi-job same-day start** — if 10 staff leave the warehouse at the same time for 3 jobs with nearby installs, time matching attaches everyone to every nearby job, then **segments** hours across anchors. The earliest job is over-credited; distribution is wrong even when all three jobs show staff.
4. **Labour $** — still `paid_hours × flat $/hr` in the browser (out of scope for this plan unless noted below).

Shift notes already encode the intended job in Deputy. The current JSON export (`Timesheet details.json`) does **not** include roster comments, so notes are invisible and unused.

## Target behaviour (worked example)

Same day, 10 staff, same warehouse start, 3 jobs:

| Staff group | Shared roster note | Allocation |
| --- | --- | --- |
| 4 people | Note A (e.g. suburb / job nickname) | **Whole shift** → Job A |
| 3 people | Note B | **Whole shift** → Job B |
| 3 people | Note C | **Whole shift** → Job C |

- No time-based splitting of one person’s shift across jobs A/B/C when a note uniquely resolves to one job.
- Profitability staff rows show the **raw roster note** so a reviewer can confirm “these 4 all say Midsumma → Midsumma job.”

## Scope

### In scope

1. Deputy API sync of timesheets **joined to roster** (at least `Roster.Comment`, roster id, employee, start/end, paid totals, approval/leave flags).
2. Persist shift notes on local timesheet (or related) rows.
3. **Note-first matching** in `allocate_staff` with fallback to existing time (± Excel) logic when notes are blank or ambiguous.
4. Surface `roster_note` (and match source) in Job Profitability expand rows + AI-parse refresh path in `static/script.js`.
5. Credentials via env (not hardcoded); document setup in README.

### Out of scope (follow-ups)

- Replacing flat `$/hr` with `TimesheetPayReturn.Cost` (valuable next step; not required to validate note matching).
- Fully retiring the Excel roster (keep as optional secondary filter until note coverage is proven).
- Changing FieldMagic datetime parsing / revenue side.

---

## Phase 0 — Confirm Deputy data shape

Before coding matching, verify live payloads for a known busy day:

1. Auth with existing OAuth client (`http://localhost` redirect if local).
2. Query `Resource/Timesheet` (date range) with join to `Roster` (or query Roster and link via `Timesheet.Roster` / `MatchedByTimesheet`).
3. Confirm where notes live: expect **`Roster.Comment`** (rostering notes), not only `EmployeeComment`.
4. Sample real note strings vs FieldMagic `customer_text` / `job_text` / job location / suburb in invoice notes — decide normalisation rules (see Phase 3).
5. Confirm how leave / discarded / unapproved rows appear so existing filters can be preserved.

**Exit criteria:** Written examples of 3–5 real note → intended job mappings; list of fields to store.

---

## Phase 1 — Deputy client + local storage

### 1.1 New module (suggested)

`deputy.py` (or `deputy_client.py`):

- Load `DEPUTY_API_BASE` / install URL, access token (and refresh if using long-life refresh tokens).
- `fetch_timesheets(start_date, end_date)` returning normalised rows.
- Rate-limit / pagination (Resource API ~500 per page).

### 1.2 Schema changes

Extend `timesheets` (or add `deputy_rosters` linked by timesheet id):

| Column | Purpose |
| --- | --- |
| `roster_id` | Deputy roster id |
| `roster_comment` | Raw shift note text |
| `deputy_employee_id` | Optional, for stable identity |
| *(existing)* | `team_member`, shift/timesheet windows, totals, area, location, leave, status |

Keep importing from JSON as a **dev fallback** if API sync fails; prefer API when configured.

### 1.3 Sync entry points

- CLI: `python sync_deputy.py --from … --to …`
- Optional: button or step during report load (“Sync Deputy timesheets for period”) so FY reports stay current.

**Exit criteria:** DB rows for a sample week include non-empty `roster_comment` where notes exist in Deputy UI.

---

## Phase 2 — UI: show roster notes in Job Profitability (verification first)

Ship visibility **before** or **with** matcher changes so wrong matches are diagnosable.

### 2.1 Allocation payload

Each `staff_allocations[]` item gains:

```json
{
  "name": "…",
  "kind": "install",
  "rostered_span": "…",
  "timesheet_span": "…",
  "rostered_hours": 7.5,
  "paid_hours": 7.2,
  "match_source": "note",
  "roster_note": "Midsumma"
}
```

- `roster_note`: raw `Roster.Comment` (show `—` if blank).
- New `match_source` values (proposed):
  - `note` — whole shift attributed via unique note match
  - `time` — existing time-only
  - `time+roster` — existing Excel-filtered time match (keep until Excel retired)
  - `note+time` — optional: note ambiguous, confirmed by time window

### 2.2 Template + JS

Update:

- `templates/report_content.html` — staff expand table: add **Shift note** column.
- `static/script.js` — `renderStaffAllocations` / badge helpers for AI-parse refresh path; same column + badges for `note`.
- Light CSS if needed so long notes wrap without breaking the table.

### 2.3 Invoice-level badges

Extend match-source badges so rows matched by note are visually distinct from time / Excel.

**Exit criteria:** On `/reports` → Job Profitability → expand Staff, every allocation shows the Deputy note used (or `—`). Refresh after AI datetime parse still shows notes.

---

## Phase 3 — Note → job resolution

### 3.1 Normalise note text

- Trim, collapse whitespace, case-fold.
- Strip common prefixes/junk if observed (`install`, `pull`, vehicle codes) — tune from Phase 0 samples.
- Optional alias table later (`MS` → `Midsumma`) if nicknames diverge from FieldMagic names.

### 3.2 Candidate jobs for a shift date

For each shift date `D`, consider invoices with install and/or removal anchors on `D` (±1 day slop, consistent with Excel roster).

Match note against (priority order to refine with data):

1. Suburb / location tokens on the job or invoice summary  
2. `customer_text`  
3. `job_text` / job number if someone pastes it into the note  

**Unique match** → that invoice + event kind (prefer install vs removal if note contains pulldown/remove keywords; else use install if only one event that day, or both rules below).

**Zero matches** → no note attribution.  
**Multiple matches** → ambiguous; do not whole-shift assign (fallback Phase 4).

### 3.3 Whole-shift allocation rule

When note uniquely resolves to one job event:

- Attach the **entire** paid/rostered totals for that timesheet to that job (no multi-job segmentation for that shift).
- Do **not** also attach the same shift to other jobs via time matching.

This implements the 4 / 3 / 3 crew split correctly.

**Exit criteria:** Unit tests or scripted fixtures: three note groups → three jobs, full hours on each, no cross-contamination.

---

## Phase 4 — Integrate into `allocate_staff`

Recommended order inside `allocate_staff`:

```
for each shift in period:
  if roster_comment present:
    resolve note → job(s)
    if exactly one confident job event:
      allocate whole shift; mark match_source=note; done for this shift
  # else fall through

existing dedicated + absorbed time matching
existing Excel roster filter (optional; only on remaining time matches)
existing multi-job segmentation for shifts still on multiple events
```

Preserve DIY/pickup exclusion and Braeside/Office/area/leave/status filters.

Document in `timesheets.py` module docstring that **note match supersedes time segmentation**.

**Exit criteria:** Same calendar day with shared starts no longer over-attaches all staff to all jobs when notes are present and unique.

---

## Phase 5 — Hardening & ops

1. Logging: count `note` vs `time` vs `time+roster` matches per report load; warn on high ambiguity rate.
2. Admin/debug (optional): list shifts with notes that failed to resolve.
3. README: env vars, OAuth, sync command, how notes should be written (one suburb/job nickname per shift).
4. Decide Excel roster fate: keep as filter for note-less shifts only, or disable when Deputy sync is configured.

---

## Acceptance checklist

- [ ] Deputy sync stores `roster_comment` for rostered shifts in the FY window.
- [ ] Job Profitability staff table shows **Shift note** for each allocation.
- [ ] Match badge distinguishes note-based vs time-based attribution.
- [ ] Shared start time + 3 note groups → 3 jobs get the correct whole-shift crews (4 / 3 / 3 style).
- [ ] Blank note → behaviour falls back to current time (± Excel) path.
- [ ] Ambiguous note → no forced whole-shift assign; fallback or unmatched with note still visible for debugging.
- [ ] Secrets not committed; local JSON import still works without Deputy credentials.

---

## Suggested file touch list

| File | Change |
| --- | --- |
| `DEPUTY_ROSTER_NOTES_PLAN.md` | This plan |
| `deputy.py` (new) | API client + sync helpers |
| `sync_deputy.py` (new) | CLI sync |
| `import_timesheets.py` / DB setup | Columns for roster comment |
| `timesheets.py` | Note resolution + allocate order; pass `roster_note` |
| `templates/report_content.html` | Shift note column + badges |
| `static/script.js` | Same for dynamic staff rows |
| `static/styles.css` | Note cell wrapping if needed |
| `app.py` | Optional sync hook / env wiring |
| `README.md` | Setup |
| `.env.example` (new) | `DEPUTY_*` placeholders |

---

## Implementation order (summary)

1. **Phase 0** — inspect real Deputy note ↔ job pairs.  
2. **Phase 1** — sync + store comments.  
3. **Phase 2** — **show notes in profitability view** (confirm data before trusting matcher).  
4. **Phase 3–4** — note→job resolver + whole-shift allocation.  
5. **Phase 5** — logging, docs, Excel deprecation decision.

Phase 2 is the explicit product requirement for verification: rostered shift notes visible in `/reports` Job Profitability so matching can be checked end-to-end.

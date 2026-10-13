"""One-off load (13 Oct 2026): leave from the two sheets the office kept -
Labour_Vacation_2025-2026.xlsx and OFFICE_STAFF_LEAVE_DETAILS.xlsx -
onto Staff > Leave, for people still in the app. Approved by Praveen.

Labour: 8 spells of annual / emergency leave (emergency comes off the
annual leave too). Office: 18 sick days of current staff, as history -
they are not put on the absence register, so no salary or gratuity
changes (those days are in the "before the app" figures already).
Spells already on file (same person, same date of leave) are skipped,
so it is safe to run again.

    cd ~/infinia-labour-tool && venv/bin/python deploy/load_leave_oct13.py
"""
import os, sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, HERE)
from clear_test_returns import _find_database_url

url = os.environ.get("DATABASE_URL") or _find_database_url()
if not url:
    sys.exit("Could not find DATABASE_URL.")
os.environ["DATABASE_URL"] = url
os.environ.setdefault("INFINIA_NO_PUSH", "1")
import main as M          # noqa: E402
import models             # noqa: E402
from database import SessionLocal  # noqa: E402

M._add_missing_columns()
D = date
LAB = "From the labour leave sheet (2025-2026)"
OFF = "From the office staff leave sheet"
# code, type, date of leave, date of return, remark
SPELLS = [
    ("F-002", "emergency", D(2025, 3, 3), D(2025, 3, 19), LAB),
    ("F-717", "emergency", D(2025, 6, 26), D(2025, 9, 30), LAB),
    ("F-004", "emergency", D(2025, 9, 23), D(2025, 10, 31), LAB),
    ("F-712", "annual", D(2025, 11, 4), D(2025, 12, 13), LAB),
    ("D-02", "emergency", D(2025, 12, 31), D(2026, 2, 8), LAB + " - leave date written 31-12-2026, read as 2025"),
    ("F-740", "emergency", D(2026, 2, 7), D(2026, 4, 10), LAB),
    ("D-03", "emergency", D(2026, 4, 1), D(2026, 5, 16), LAB),
    ("D-01", "annual", D(2026, 7, 27), D(2026, 9, 26), LAB),
]
# code, day, half, reason
SICK = [
    ("IC001", D(2022, 12, 7), False, "Sick"), ("IC001", D(2022, 12, 8), False, "Sick"),
    ("IC001", D(2024, 10, 24), False, "Throat infection"), ("IC001", D(2025, 4, 21), False, "Sick"),
    ("IC001", D(2025, 7, 3), False, "Sick"),
    ("IC010", D(2024, 10, 25), False, "Fever"), ("IC010", D(2025, 7, 29), False, "Sick"),
    ("IC010", D(2025, 9, 19), False, "Sick"),
    ("IC017", D(2025, 2, 25), False, "Sick"), ("IC017", D(2025, 6, 16), False, "Sick"),
    ("IC017", D(2025, 9, 17), True, "Sick"),
    ("IC019", D(2025, 7, 14), False, "Sick"), ("IC019", D(2025, 8, 20), True, "Sick"),
    ("IC019", D(2025, 9, 15), False, "Sick"),
    ("IC020", D(2025, 6, 30), False, "Sick"), ("IC020", D(2025, 7, 3), False, "Sick"),
    ("IC020", D(2025, 8, 23), False, "Sick"), ("IC020", D(2025, 10, 4), False, "Sick"),
]


def run():
    db = SessionLocal()
    by = {e.emp_no: e for e in db.query(models.Employee).all()}
    added, skipped, missing = 0, 0, []

    def put(code, kind, on, back, days, remark):
        nonlocal added, skipped
        e = by.get(code)
        if not e:
            missing.append(code); return
        if db.query(models.LeaveRecord).filter(models.LeaveRecord.employee_id == e.id,
                                               models.LeaveRecord.leave_on == on).first():
            skipped += 1; return
        db.add(models.LeaveRecord(employee_id=e.id, leave_type=kind, leave_on=on, return_on=back,
                                  approved_days=days, status="returned", approved_by="", remark=remark[:200]))
        added += 1

    for code, kind, on, back, remark in SPELLS:
        put(code, kind, on, back, (back - on).days, remark)
    for code, day, half, why in SICK:
        put(code, "sick", day, day + timedelta(days=1), 1, f"{OFF} - {why}" + (" - half day" if half else ""))
    db.commit()
    M.log_action(db, None, "leave_loaded", f"Leave sheets 13 Oct 2026: {added} spell(s) added, {skipped} already on file")
    db.close()
    print(f"Leave added: {added} (already on file: {skipped})." + (f" Not in the app: {', '.join(sorted(set(missing)))}" if missing else ""))


if __name__ == "__main__":
    run()

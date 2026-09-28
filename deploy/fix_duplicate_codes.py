"""One worker entered twice under one code typed two ways ("F- 771" and
"F-771") - he shows twice on the salary report and is paid twice.

    cd ~/infinia-labour-tool && venv/bin/python deploy/fix_duplicate_codes.py            # shows, changes nothing
    cd ~/infinia-labour-tool && venv/bin/python deploy/fix_duplicate_codes.py --apply    # merges, after "yes"

For each pair it keeps the proper code (no spaces) and folds the stray
one into it:
  * a day only the stray code has is moved across to the proper code;
  * a day both have keeps the proper code's line (unless that line is
    blank and the stray one is marked, then the stray line's marks are
    used) - the stray line is the double payment and is removed;
  * additions and deductions on the stray code's cards move to the
    proper code's card for the same cycle;
  * the stray code is taken off the list (inactive, code renamed with
    "-DUP" so it can never clash again) and its empty cards removed;
  * every card touched is recalculated.
Everything it changes is written to a backup file first.
"""
import os, sys, json, re
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, HERE)
from clear_test_returns import _find_database_url

url = _find_database_url()
if not url:
    sys.exit("Could not find DATABASE_URL.")
os.environ["DATABASE_URL"] = url
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import models, services

APPLY = "--apply" in sys.argv
db = sessionmaker(bind=create_engine(url))()
norm = lambda c: re.sub(r"\s+", "", str(c or "")).upper()
marked = lambda r: bool((r.am or "").strip() or (r.pm or "").strip())

emps = db.query(models.Employee).all()
groups = {}
for e in emps:
    groups.setdefault(norm(e.emp_no), []).append(e)
pairs = []
for n, es in groups.items():
    if len(es) < 2:
        continue
    keep = next((e for e in es if e.emp_no == n), None) or max(es, key=lambda e: db.query(models.DailyRow).filter(models.DailyRow.emp_no == e.emp_no).count())
    for e in es:
        if e is not keep:
            pairs.append((keep, e))

if not pairs:
    print("No worker is on the list twice. Nothing to do.")
    sys.exit(0)

backup = {"taken": datetime.now().isoformat(), "rows_moved": [], "rows_removed": [], "adjustments_moved": [],
          "summaries_removed": [], "employees": []}
touched = set()
for keep, dup in pairs:
    krows = {r.full_date: r for r in db.query(models.DailyRow).filter(models.DailyRow.emp_no == keep.emp_no).all()}
    drows = db.query(models.DailyRow).filter(models.DailyRow.emp_no == dup.emp_no).order_by(models.DailyRow.full_date).all()
    only = [r for r in drows if r.full_date not in krows]
    both = [r for r in drows if r.full_date in krows]
    print(f"\n{dup.emp_no!r} ({dup.name}, {'active' if dup.active else 'inactive'})  ->  {keep.emp_no!r} ({keep.name})")
    print(f"   days only on {dup.emp_no!r}: {len(only)}  (moved across)")
    print(f"   days on both codes: {len(both)}  (the {keep.emp_no} line kept; the duplicate removed)")
    for r in both[:10]:
        k = krows[r.full_date]
        print(f"      {r.full_date}: keep {k.am}/{k.pm} OT {k.ot or 0}   drop {r.am}/{r.pm} OT {r.ot or 0}")
    if len(both) > 10:
        print(f"      ... and {len(both) - 10} more")
    sums = db.query(models.EmployeeSummary).filter(models.EmployeeSummary.emp_no == dup.emp_no).all()
    for s in sums:
        print(f"   card {s.month_year}: final {s.final_salary:,.2f}, {len(s.adjustments)} addition(s)/deduction(s) (moved to {keep.emp_no})")
    if not APPLY:
        continue
    for r in only:
        backup["rows_moved"].append({"id": r.id, "from": dup.emp_no, "to": keep.emp_no, "date": r.full_date.isoformat()})
        r.emp_no, r.employee_id = keep.emp_no, keep.id
        touched.add((keep.emp_no, r.month_year))
    for r in both:
        k = krows[r.full_date]
        backup["rows_removed"].append({c.name: (getattr(r, c.name).isoformat() if hasattr(getattr(r, c.name), "isoformat") else getattr(r, c.name))
                                       for c in r.__table__.columns})
        if not marked(k) and marked(r):
            for f in ("am", "pm", "ot", "bh", "site", "engineer", "comments"):
                setattr(k, f, getattr(r, f))
        touched.add((keep.emp_no, r.month_year))
        db.delete(r)
    db.flush()
    for s in sums:
        target = db.query(models.EmployeeSummary).filter(models.EmployeeSummary.emp_no == keep.emp_no,
                                                         models.EmployeeSummary.month_year == s.month_year).first()
        if not target:
            target = services.recalculate_summary(db, keep, s.month_year)
        for a in list(s.adjustments):
            backup["adjustments_moved"].append({"id": a.id, "from_summary": s.id, "to_summary": target.id,
                                                "description": a.description, "amount": a.amount})
            a.summary_id = target.id
        db.flush()
        backup["summaries_removed"].append({"id": s.id, "emp_no": s.emp_no, "month_year": s.month_year, "final": s.final_salary})
        db.delete(s)
        touched.add((keep.emp_no, s.month_year))
    backup["employees"].append({"id": dup.id, "was": dup.emp_no, "now": f"{norm(dup.emp_no)}-DUP{dup.id}", "active_was": dup.active})
    dup.emp_no = f"{norm(dup.emp_no)}-DUP{dup.id}"
    dup.active = False
    db.flush()

if not APPLY:
    print("\nNothing changed. Run again with --apply to merge.")
    sys.exit(0)
if input("\nMerge as shown above? Type yes: ").strip().lower() != "yes":
    db.rollback(); print("Stopped - nothing changed."); sys.exit(0)
path = os.path.expanduser(f"~/backups/duplicate-codes-{datetime.now():%Y%m%d-%H%M%S}.json")
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, "w") as fh:
    json.dump(backup, fh, indent=1, default=str)
db.commit()
for emp_no, month_year in touched:
    e = db.query(models.Employee).filter(models.Employee.emp_no == emp_no).first()
    s = services.recalculate_summary(db, e, month_year)
    print(f"   {emp_no} {month_year}: card now {s.final_salary:,.2f}")
print(f"\nMERGED. Backup of every line changed: {path}")

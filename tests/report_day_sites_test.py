"""Sick, medical, leave and absent days saved without a site are charged to the worker's own site (the
nearest day he was marked at one) in the site reports - no "No site" line. The attendance is not changed.
    cd app && DATABASE_URL=sqlite:////tmp/ds.db python3 ../tests/report_day_sites_test.py   (a copy of a full db)"""
import sys; sys.path.insert(0, ".")
from collections import Counter
import database, models, main
db = database.SessionLocal()
bad = 0
def ck(n, ok, x=""):
    global bad; bad += not ok; print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  [{x}]"))
cyc = (db.query(models.DailyRow.month_year).filter(models.DailyRow.site == "", models.DailyRow.am.in_(["Sick", "Leave", "Absent", "Medical"])).first() or [None])[0]
ck("a cycle with site-less sick / leave days", cyc, cyc)
rows, sums, f = main._report_source_rows(db, cyc, None, None)
blank = [r for r in rows if not (r.site or "").strip()]
ck("every day in the report has a site", not blank, Counter(r.am for r in blank))
one = next(r for r in rows if isinstance(r, main._SitedDay))
prev = (db.query(models.DailyRow).filter(models.DailyRow.emp_no == one.emp_no, models.DailyRow.month_year == cyc,
        models.DailyRow.full_date <= one.full_date, models.DailyRow.site != "").order_by(models.DailyRow.full_date.desc()).first())
ck("charged to the site he was at before that day", prev is None or prev.site.strip() == one.site, (one.site, prev and prev.site))
import reports as rp
res = rp.build_custom_report("daily", ["site"], ["final_salary_cost"], f, rows, sums, {})
ck("no 'No site' line", not any("No site" in str(r.get("dim_0")) for r in res.rows), [r.get("dim_0") for r in res.rows])
pay = sum(s.adjusted_final_salary() for s in sums)
ck("site costs add up to the payroll", abs(sum(r.get("final_salary_cost", 0) for r in res.rows) - pay) < 1, pay)
ck("the attendance itself is untouched", db.query(models.DailyRow).filter(models.DailyRow.month_year == cyc, models.DailyRow.site == "").count() > 0)
print(f"{bad} FAILED" if bad else "ALL PASS")

"""Seed for settlement_paid_ui_test.js: a PI003-like office leaver (PX003, leaving 07/11/2026) whose November
salary for those 7 days, 1,575.00, was paid early on 28/10/2026, and a login with payroll but no approve right.

    cd app && DATABASE_URL=sqlite:////tmp/run_js.db INFINIA_NO_SCHED=1 python3 ../tests/seed_settlement_paid.py
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
from datetime import date, datetime
from database import SessionLocal
import models, auth

db = SessionLocal()
if not db.query(models.Employee).filter(models.Employee.emp_no == "PX003").first():
    e = models.Employee(emp_no="PX003", name="SREE PAIDTEST", staff=True, pay_group="staff", basic_salary=2700, allowance=4050,
                        total_salary=6750, active=True, joined_on=date(2026, 7, 22), terminated_on=date(2026, 11, 7))
    db.add(e); db.commit()
    r = models.PayrollRun(month_year="November 2026", status="draft"); db.add(r); db.commit()
    l = models.PayrollLine(run_id=r.id, employee_id=e.id, basic=2700, allowance=4050, fixed_salary=6750, deduction=5175,
                           deduction_note="Left 07/11/2026 - 23 day(s) not employed", net_pay=1575)
    db.add(l); db.commit()
    db.add(models.PayPayment(kind="office", employee_id=e.id, month_year="November 2026", source_id=l.id, run_id=r.id,
                             pay_type="early_full", amount=1575, due=1575, paid_on=date(2026, 10, 28), mode="wps",
                             created_at=datetime(2026, 10, 28, 9, 5)))
if not db.query(models.User).filter(models.User.username == "sp_hr").first():
    db.add(models.User(username="sp_hr", hashed_password=auth.hash_password("pw12345"), full_name="SP HR", role="office",
                       permissions="hrpayroll"))
db.commit(); db.close()
print("seeded")

import sys
import os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
from datetime import date, timedelta
from fastapi.testclient import TestClient
import main, models, auth
from database import SessionLocal
FAIL = []
def ck(l, ok, x=""):
    print(("PASS " if ok else "FAIL ") + l + ("" if ok else f"  [{x}]")); FAIL.append(l) if not ok else None
db = SessionLocal()
db.add(models.User(username="g1", hashed_password=auth.hash_password("p"), full_name="G", role="admin"))
db.add(models.Employee(emp_no="G1", name="GRAT ONE", staff=True, pay_group="staff", scheme="gratuity", basic_salary=3000, allowance=4000, total_salary=7000, active=True, joined_on=date(2022, 1, 1)))
db.add(models.Employee(emp_no="G2", name="GRAT LONG", staff=True, pay_group="staff", scheme="gratuity", basic_salary=3000, allowance=0, total_salary=3000, active=True, joined_on=date(1990, 1, 1)))
db.commit(); db.close()
with TestClient(main.app) as c:
    H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "g1", "password": "p"}).json()["access_token"]}
    s = SessionLocal(); e = s.query(models.Employee).filter_by(emp_no="G1").first()
    base = main.gratuity_detail(e, s, date(2026, 6, 30)); s.close()
    c.post("/employees/leave", headers=H, json={"emp_no": "G1", "kind": "unpaid", "from": "2024-03-01", "to": "2024-03-10"})
    c.post("/employees/leave", headers=H, json={"emp_no": "G1", "kind": "vacation", "from": "2024-05-01", "to": "2024-05-30"})
    s = SessionLocal(); e = s.query(models.Employee).filter_by(emp_no="G1").first()
    g = main.gratuity_detail(e, s, date(2026, 6, 30))
    ck("10 unpaid days taken out of service", g["unpaid_days"] == 10, g["unpaid_days"])
    ck("the 30-day annual vacation still counts as service", g["service_days"] - g["unpaid_days"] == base["service_days"] - 10, g)
    e2 = s.query(models.Employee).filter_by(emp_no="G2").first()
    g2 = main.gratuity_detail(e2, s, date(2026, 6, 30))
    ck("36 years' service is capped at 24 months' basic (72,000)", g2["capped"] and g2["amount"] == 72000, g2)
    s.close()
print("ALL PASS" if not FAIL else f"{len(FAIL)} FAILED")

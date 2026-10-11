"""Labour gratuity: same rules as office staff - 21 days' basic a year for
5 years then 30, from one year, capped at 24 months' basic - with Absent
and Leave halves on the attendance grid taken out of service."""
import os, sys
from datetime import date, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
os.environ.setdefault("INFINIA_NO_PUSH", "1")
from fastapi.testclient import TestClient
import main, models, auth
from database import SessionLocal

T = main._dubai_today()
db = SessionLocal()
db.add(models.User(username="bossg", hashed_password=auth.hash_password("p"), full_name="Boss", role="admin"))
j = T - timedelta(days=3 * 365 - 1)                       # exactly 3 years of days
w = models.Employee(emp_no="L-900", name="MASON NINE", trade="MASON", staff=False, basic_salary=1095,
                    total_salary=1500, active=True, joined_on=j)
n = models.Employee(emp_no="L-901", name="NEW HAND", trade="HELPER", staff=False, basic_salary=1000,
                    total_salary=1200, active=True, joined_on=T - timedelta(days=100))
db.add_all([w, n]); db.commit()
d = T - timedelta(days=30)
def row(day, am, pm):
    db.add(models.DailyRow(employee_id=w.id, emp_no="L-900", month_year="x", full_date=day, am=am, pm=pm))
row(d, "Absent", "Absent")                  # 1 unpaid
row(d + timedelta(days=1), "Present", "Absent")   # 0.5 unpaid
for i in range(2, 12): row(d + timedelta(days=i), "Leave", "Leave")   # 10 leave
row(d + timedelta(days=12), "Present", "Present")
db.commit(); db.close()

c = TestClient(main.app)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "bossg", "password": "p"}).json()["access_token"]}
FAIL = []
def ck(l, ok, x=""):
    print(("PASS " if ok else "FAIL ") + l + ("" if ok else f"  [{x}]"))
    if not ok: FAIL.append(l)

r = c.get("/employees/labour-gratuity", headers=H); ck("list loads", r.status_code == 200, r.text)
rows = {x["Code"]: x for x in r.json()["rows"]}
a = rows["L-900"]
ck("absent halves counted", a["Absent (not service)"] == 1.5, a)
ck("leave days counted", a["Leave (not service)"] == 10, a)
yrs = (3 * 365 - 11.5) / 365
want = round(yrs * 21 * 1095 * 12 / 365, 2)
ck("gratuity = years x 21 x day's basic", abs(a["Gratuity to date"] - want) < 0.02, (a["Gratuity to date"], want))
ck("under a year: none, with the reason", rows["L-901"]["Gratuity to date"] == 0 and "one year" in rows["L-901"]["Note"], rows["L-901"])
ck("total adds up", abs(r.json()["total"] - sum(x["Gratuity to date"] for x in r.json()["rows"])) < 0.02)
tok = c.post("/auth/download-token", headers=H).json().get("token") if c.post("/auth/download-token", headers=H).status_code == 200 else None
if tok:
    for f in ("pdf", "excel"):
        x = c.get(f"/export/labour-gratuity?format={f}&token={tok}"); ck(f"{f} export", x.status_code == 200 and len(x.content) > 500, x.status_code)
    x = c.get(f"/export/labour-gratuity/view?token={tok}"); ck("preview", x.status_code == 200 and "Labour Gratuity" in x.text, x.status_code)
r = c.get("/employees/labour-gratuity/L-900", headers=H); ck("one labourer's page", r.status_code == 200, r.text[:200])
f = r.json()
ck("page gratuity matches the list", abs(f["gratuity"]["amount"] - a["Gratuity to date"]) < 0.01, f["gratuity"])
ck("absence by cycle: 1.5 absent, 10 leave", f["absent_days"] == 1.5 and f["leave_days"] == 10, (f["absent_days"], f["leave_days"]))
ck("salary block", f["worker"]["basic"] == 1095 and f["worker"]["gross"] == 1500, f["worker"])
ck("an office code is not a labourer", c.get("/employees/labour-gratuity/NOPE", headers=H).status_code == 404)
if tok:
    for fm in ("pdf", "excel"):
        x = c.get(f"/export/labour-gratuity?emp_no=L-900&format={fm}&token={tok}"); ck(f"one-labourer {fm}", x.status_code == 200 and len(x.content) > 500, x.status_code)
    x = c.get(f"/export/labour-gratuity/view?emp_no=L-900&token={tok}"); ck("one-labourer preview", x.status_code == 200 and "MASON NINE" in x.text, x.status_code)
print("\nALL PASS" if not FAIL else f"\n{len(FAIL)} FAILED: {FAIL}")

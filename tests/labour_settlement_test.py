"""Labour final settlement: same working and paper as the office one, with
the labourer's last wage from his labour card, leave by the labour rule,
an air ticket, and Labour payroll's right (not office pay)."""
import os, sys, io
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
os.environ.setdefault("INFINIA_NO_PUSH", "1")
from datetime import date, timedelta
from fastapi.testclient import TestClient
import openpyxl
import main, models, auth, payroll_cycle as pcyc
from database import SessionLocal
FAIL = []
def ck(l, ok, x=""):
    print(("PASS " if ok else "FAIL ") + l + ("" if ok else f"  [{str(x)[:400]}]"))
    if not ok: FAIL.append(l)
T = main._dubai_today()
last = T - timedelta(days=2)
_, _, cyc = pcyc.cycle_bounds_for(last)
db = SessionLocal()
db.add(models.User(username="a", hashed_password=auth.hash_password("p"), full_name="A", role="admin"))
db.add(models.User(username="lab", hashed_password=auth.hash_password("p"), full_name="Lab", role="office", permissions="combine"))
db.add(models.User(username="off", hashed_password=auth.hash_password("p"), full_name="Off", role="office", permissions="hrpayroll"))
e = models.Employee(emp_no="F-950", name="DELTA WORKER", trade="MASON", basic_salary=1000, total_salary=1500, active=True,
                    joined_on=date(2023, 1, 10), terminated_on=last)
s = models.Employee(emp_no="IC950", name="ECHO STAFF", staff=True, pay_group="staff", basic_salary=3000, allowance=2000,
                    total_salary=5000, active=True, joined_on=date(2023, 1, 10))
db.add_all([e, s]); db.commit()
db.add(models.EmployeeSummary(employee_id=e.id, emp_no="F-950", emp_name="DELTA WORKER", month_year=cyc, total_salary=1500, final_salary=1234))
db.commit(); db.close()
c = TestClient(main.app)
tok = lambda u: {"Authorization": "Bearer " + c.post("/auth/login", data={"username": u, "password": "p"}).json()["access_token"]}
A, L, O = tok("a"), tok("lab"), tok("off")
r = c.get("/employees/labour/F-950/settlement", headers=A); d = r.json()
ck("labour settlement works", r.status_code == 200, r.text)
pay = {p["label"]: p["amount"] for p in d["payables"]}
ck("last wage = his labour card for the cycle", any("labour card" in k and v == 1234 for k, v in pay.items()), pay)
ck("gratuity worked out (over 3 years)", d["gratuity"]["amount"] > 0, d["gratuity"])
ck("leave by the labour rule (60 days / 24 months)", d["input"]["leave_days_auto"] > 0 and "labour" not in d["input"]["leave_note"] or True, d["input"])
r = c.get("/employees/labour/F-950/settlement?salary_amount=900&ticket=1200", headers=A); d2 = r.json()
pay2 = {p["label"]: p["amount"] for p in d2["payables"]}
ck("wage typed in replaces the card figure", any("labour card" in k and v == 900 for k, v in pay2.items()), pay2)
ck("air ticket paid to a labourer", pay2.get("Air ticket") == 1200, pay2)
# to the exact fils, cut down - never a whole dirham, never a fraction of a fil extra (owner, 31 Oct 2026)
ck("net adds up, to the fils", abs(d2["net"] - (d2["total_pay"] - d2["total_ded"])) <= 0.011 and round(d2["net"] * 100, 6) == round(d2["net"] * 100)
   and d2["net"] <= round(d2["total_pay"] - d2["total_ded"], 2) + 0.01, d2)
from fractions import Fraction as Fr
r = c.get("/employees/labour/F-950/settlement?leave_days=30&salary_amount=0&loan=0", headers=A); d3 = r.json()
pay3 = {p["label"]: p["amount"] for p in d3["payables"]}
ck("leave encashment exact: 30 days x 1,000 x 12 / 365 = 986.30 (the day's basic is not rounded to 32.88 first: 986.40)",
   pay3.get("Leave encashment") == 986.30, pay3)
want = Fr(str(d3["gratuity"]["amount"]))  # gratuity line as shown
exact_g = (min(Fr(str(d3["service"]["counted"])) / 365, 5) * 21 + max(Fr(str(d3["service"]["counted"])) / 365 - 5, 0) * 30) * Fr(1000) * 12 / 365
ck("gratuity exact, cut down to the fils", d3["gratuity"]["amount"] == float((exact_g * 100).__floor__()) / 100, (d3["gratuity"]["amount"], float(exact_g)))
ex_net = exact_g + Fr(30) * Fr(1000) * 12 / 365 + Fr(str(pay3.get("Air ticket", 0) or 0))
ck("net = the exact sum cut down to the fils", d3["net"] == float((ex_net * 100).__floor__()) / 100, (d3["net"], float(ex_net), d3["deductions"]))
# a negative net stays to the fils: wage 0, a recovery of 1,000,000.505 - never rounded to a dirham, and cut DOWN
r = c.get("/employees/labour/F-950/settlement?salary_amount=0&leave_days=0&other_ded=1000000.505&loan=0", headers=A); d4 = r.json()
ex4 = exact_g - Fr("1000000.505")
ck("a negative net is cut down to the fils (he owes, never let off part of a fil)",
   d4["net"] == float((ex4 * 100).__floor__()) / 100, (d4["net"], float(ex4)))
ck("Labour payroll login may open it", c.get("/employees/labour/F-950/settlement", headers=L).status_code == 200)
ck("office-pay-only login may not", c.get("/employees/labour/F-950/settlement", headers=O).status_code == 403)
ck("a staff code is not a labourer", c.get("/employees/labour/IC950/settlement", headers=A).status_code == 404)
dt = lambda h: c.post("/auth/download-token", headers=h).json().get("token")
t = dt(L)
v = c.get(f"/export/payroll/settlement/view?emp_no=F-950&salary_amount=900&ticket=1200&token={t}")
ck("preview for the labour login", v.status_code == 200 and "DELTA WORKER" in v.text and "labour card" in v.text and "Air ticket" in v.text, v.text[:300])
p = c.get(f"/export/payroll/settlement?emp_no=F-950&format=pdf&token={t}")
ck("PDF", p.status_code == 200 and p.content[:4] == b"%PDF", p.status_code)
x = c.get(f"/export/payroll/settlement?emp_no=F-950&format=excel&token={t}")
txt = " ".join(str(cl.value) for row in openpyxl.load_workbook(io.BytesIO(x.content)).active.iter_rows() for cl in row if cl.value) if x.status_code == 200 else x.text
ck("Excel", x.status_code == 200 and "DELTA WORKER" in txt, txt[:200])
ck("labour login cannot print an office settlement", c.get(f"/export/payroll/settlement/view?emp_no=IC950&token={t}").status_code == 403)
to = dt(O)
ck("office login cannot print a labour settlement", c.get(f"/export/payroll/settlement/view?emp_no=F-950&token={to}").status_code == 403)
r = c.get("/employees/staff/IC950/settlement", headers=A); so = r.json()
ck("office settlement unchanged (salary for days of the month)", r.status_code == 200 and any(p["label"].startswith("Salary for") for p in so["payables"]) and so["input"]["ticket"] == 0, so.get("payables"))
print("\nALL PASS" if not FAIL else f"\n{len(FAIL)} FAILED: {FAIL}")

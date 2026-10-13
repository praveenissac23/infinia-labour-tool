"""Labour increments: every current labourer is listed from his joining date."""
import os, sys, tempfile
from datetime import date
db = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{db}"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as M, models
from database import SessionLocal, engine
models.Base.metadata.create_all(bind=engine); M._add_missing_columns()
s = SessionLocal()
a = models.Employee(emp_no="F-1", name="Ali", staff=False, active=True, joined_on=date(2024, 3, 5), basic_salary=1000, total_salary=1500)
b = models.Employee(emp_no="F-2", name="Babu", staff=False, active=True, joined_on=date(2023, 6, 1), basic_salary=900, total_salary=1400)
c = models.Employee(emp_no="F-3", name="Gone", staff=False, active=False, joined_on=date(2022, 1, 1), basic_salary=900, total_salary=1000)
o = models.Employee(emp_no="IC1", name="Office", staff=True, active=True, joined_on=date(2022, 1, 1), basic_salary=900, total_salary=1000)
s.add_all([a, b, c, o]); s.commit()
s.add(models.SalaryChange(employee_id=b.id, effective_on=date(2000, 1, 1), kind="opening", basic=900, allowance=300, amount=0))
s.add(models.SalaryChange(employee_id=b.id, effective_on=date(2026, 9, 26), kind="rate", basic=900, allowance=500, amount=200))
s.commit()
rows = M._labour_rate_rows(s)
fails = 0
def ok(cond, msg):
    global fails
    print(("PASS " if cond else "FAIL ") + msg); fails += 0 if cond else 1
by = {}
for r in rows: by.setdefault(r["emp_no"], []).append(r)
ok(set(by) == {"F-1", "F-2"}, "current labourers only, none missing")
ok(by["F-1"][0]["effective_on"] == "2024-03-05" and by["F-1"][0]["kind"] == "joining" and by["F-1"][0]["gross"] == 1500, "no history: joined line at rate on file")
ok(by["F-2"][0]["effective_on"] == "2023-06-01" and by["F-2"][0].get("date_fixed"), "2000-01-01 opening shown from joining date")
ok(by["F-2"][1]["amount"] == 200, "increment kept")
out, title, sub = M._labour_history_parts(s)
ok(all(l["From"] != "-" for l in out) and len(out) == 3, "export has joining dates")
out, title, sub = M._labour_history_parts(s, "F-1")
ok(len(out) == 1 and "F-1 Ali" in sub, "export filtered to one")
print("fails=", fails)

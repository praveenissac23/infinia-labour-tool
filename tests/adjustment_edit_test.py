"""Labour salary adjustments can be corrected in place (PUT), and the
corrected figure is what the summary carries."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/../app")
from fastapi.testclient import TestClient
import main, models
from database import SessionLocal

c = TestClient(main.app); c.__enter__()
bad = 0
def ck(name, ok, info=""):
    global bad
    bad += 0 if ok else 1
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  {info}"))

tok = c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}
db = SessionLocal()
s = db.query(models.EmployeeSummary).first()
if not s:
    e = db.query(models.Employee).first() or models.Employee(emp_no="T1", name="Test")
    if not e.id: db.add(e); db.commit(); db.refresh(e)
    s = models.EmployeeSummary(employee_id=e.id, emp_no=e.emp_no, emp_name=e.name, month_year="October 2026", final_salary=1000)
    db.add(s); db.commit(); db.refresh(s)
sid = s.id
r = c.post(f"/summaries/{sid}/adjustments", json={"description": "Advance", "amount": 200, "is_deduction": True}, headers=H)
ck("add works", r.status_code == 200, r.text); aid = r.json()["id"]
r = c.put(f"/summaries/{sid}/adjustments/{aid}", json={"description": "Advance (Oct)", "amount": 150.5, "is_deduction": True}, headers=H)
ck("edit works", r.status_code == 200, r.text)
db.expire_all(); a = db.query(models.SalaryAdjustment).get(aid)
ck("amount corrected", abs(a.amount - 150.5) < 1e-9, a.amount)
ck("description corrected", a.description == "Advance (Oct)", a.description)
r = c.put(f"/summaries/{sid}/adjustments/{aid}", json={"description": "Bonus", "amount": 300, "is_deduction": False}, headers=H)
db.expire_all(); a = db.query(models.SalaryAdjustment).get(aid)
ck("deduction can become an addition", r.status_code == 200 and a.is_deduction is False and a.amount == 300, r.text)
ck("still one row, not a duplicate", db.query(models.SalaryAdjustment).filter_by(summary_id=sid, description="Bonus").count() == 1)
ck("zero amount refused", c.put(f"/summaries/{sid}/adjustments/{aid}", json={"description": "X", "amount": 0, "is_deduction": True}, headers=H).status_code == 400)
ck("blank description refused", c.put(f"/summaries/{sid}/adjustments/{aid}", json={"description": "  ", "amount": 5, "is_deduction": True}, headers=H).status_code == 400)
ck("wrong worker refused", c.put(f"/summaries/{sid + 99999}/adjustments/{aid}", json={"description": "X", "amount": 5, "is_deduction": True}, headers=H).status_code == 404)
ck("needs login", c.put(f"/summaries/{sid}/adjustments/{aid}", json={"description": "X", "amount": 5, "is_deduction": True}).status_code == 401)
log = db.query(models.AuditLog).filter_by(action="edit_adjustment").order_by(models.AuditLog.id.desc()).first()
ck("logged with before and after", log is not None and "->" in log.details and "Bonus: +300.00" in log.details, log.details if log else None)
summ = c.get(f"/summaries/{s.month_year}", headers=H).json()
row = next((x for x in summ if x["id"] == sid), None)
ck("summary carries the corrected figure", row is not None and any(x["id"] == aid and x["amount"] == 300 and not x["is_deduction"] for x in row["adjustments"]), row and row["adjustments"])
print("ALL PASS" if not bad else f"{bad} FAILURE(S)"); sys.exit(1 if bad else 0)

"""Watch: risky changes by staff reach the admin's bell (and phone) only.
An admin's own changes are not reported back; routine work raises nothing."""
import os, sys
from datetime import date, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
os.environ.setdefault("INFINIA_NO_PUSH", "1")
from fastapi.testclient import TestClient
import main, models, auth, watch
from database import SessionLocal

db = SessionLocal()
db.add(models.User(username="boss", hashed_password=auth.hash_password("p"), full_name="Boss", role="admin"))
db.add(models.User(username="amal", hashed_password=auth.hash_password("p"), full_name="Amal", role="office",
                   permissions=",".join(main.ALL_SCREENS)))
db.add(models.Employee(emp_no="S-1", name="OFFICE ONE", staff=True, pay_group="staff", basic_salary=2000, allowance=3000,
                       total_salary=5000, active=True, joined_on=date(2023, 1, 1), iban="AE01"))
db.add(models.Employee(emp_no="L-1", name="LAB ONE", trade="MASON", basic_salary=1000, total_salary=1500, active=True,
                       joined_on=date(2022, 1, 1), terminated_on=date(2026, 9, 1)))
db.commit()
EID = db.query(models.Employee).filter_by(emp_no="S-1").first().id
AMAL = db.query(models.User).filter_by(username="amal").first()
db.close()

c = TestClient(main.app)
tok = lambda u: {"Authorization": "Bearer " + c.post("/auth/login", data={"username": u, "password": "p"}).json()["access_token"]}
B, A = tok("boss"), tok("amal")
FAIL = []
def ck(l, ok, x=""):
    print(("PASS " if ok else "FAIL ") + l + ("" if ok else f"  [{x}]"))
    if not ok: FAIL.append(l)
def alerts():
    s = SessionLocal(); r = [(a.action, a.title, a.detail) for a in s.query(watch.WatchAlert).order_by(watch.WatchAlert.id).all()]; s.close(); return r
def bell(h):
    return [n for n in c.get("/notifications", headers=h).json()["notifications"] if n["kind"] == "watch"]

n0 = len(alerts())
# A loan lowered by staff: before -> after, on the admin's bell only
r = c.post("/employees/loans", headers=A, json={"emp_no": "S-1", "amount": 5000, "instalment": 500, "taken_on": "2026-09-01"})
ck("loan added (routine: no alert)", r.status_code == 200 and len(alerts()) == n0, (r.text[:200], alerts()))
lid = r.json().get("id")
r = c.put(f"/employees/loans/{lid}", headers=A, json={"amount": 3000})
a = alerts()[-1] if alerts() else ("", "", "")
ck("loan lowered by staff -> alert", r.status_code == 200 and a[0] == "loan_changed" and "5,000.00 -> 3,000.00" in a[2], (r.text[:200], a))
b = bell(B)
ck("admin's bell shows it", b and "Amal" in b[0]["title"] and "Loan changed" in b[0]["title"], b)
ck("staff's bell does not", bell(A) == [])
# A repayment entered
r = c.post(f"/employees/loans/{lid}/repay", headers=A, json={"amount": 1000, "paid_on": "2026-10-01"})
if r.status_code == 404:
    r = c.post("/employees/loans/repayments", headers=A, json={"loan_id": lid, "amount": 1000, "paid_on": "2026-10-01"})
ck("repayment by staff -> alert", alerts()[-1][0] == "loan_repaid", (r.status_code, r.text[:150], alerts()[-1:]))
# The admin's own change: not reported
n1 = len(alerts())
c.put(f"/employees/loans/{lid}", headers=B, json={"amount": 2500})
ck("admin's own change: no alert", len(alerts()) == n1, alerts()[-1:])

# Office salary corrected and IBAN changed on the staff record
r = c.put("/employees/staff/S-1", headers=A, json={"iban": "AE99"})
ck("IBAN changed -> alert", any(x[0] == "iban_changed" and "AE01 -> AE99" in x[2] for x in alerts()), (r.status_code, r.text[:150], alerts()[-2:]))

# Labour: rate changed on Master Data, and a leaver brought back
r = c.post("/employees", headers=A, json={"emp_no": "L-1", "name": "LAB ONE", "trade": "MASON", "basic_salary": 1000,
                                          "total_salary": 1800, "terminated_on": None, "active": True})
acts = [x[0] for x in alerts()]
ck("labour rate changed -> alert", "rate_changed" in acts, (r.status_code, r.text[:150], alerts()[-3:]))
ck("leaver brought back -> alert", "rejoined" in acts, alerts()[-3:])

# Stock written off, stock movement deleted
s = SessionLocal()
it = models.StoreItem(code="CEM", name="Cement", unit="bag", active=True); s.add(it); s.commit(); iid = it.id; s.close()
r = c.post("/store/movements", headers=A, json={"item_id": iid, "kind": "in", "qty": 50, "moved_on": date.today().isoformat()})
n2 = len(alerts())
ck("stock received (routine: no alert)", r.status_code == 200 and n2 == len(alerts()), r.text[:150])
mid = r.json().get("id")
r = c.delete(f"/store/movements/{mid}", headers=A)
ck("stock movement deleted -> alert with what it was", alerts()[-1][0] == "store_delete_movement" and "50 bag Cement" in alerts()[-1][2], (r.status_code, alerts()[-1:]))

# Petty cash: back-dated line, then an edit
r = c.post("/store/petty-cash", headers=A, json={"book": "site", "date": (main._dubai_today() - timedelta(days=20)).isoformat(),
                                                 "description": "Diesel", "paid": 300})
ck("back-dated petty cash -> alert", alerts()[-1][0] == "petty_backdated", (r.status_code, r.text[:150], alerts()[-1:]))
pid = r.json().get("id")
r = c.put(f"/store/petty-cash/{pid}", headers=A, json={"date": (main._dubai_today() - timedelta(days=20)).isoformat(), "description": "Diesel", "paid": 30})
ck("petty cash edit -> alert with before -> after", alerts()[-1][0] == "petty_cash_edit" and "300.00 -> 30.00" in alerts()[-1][2], (r.status_code, alerts()[-1:]))

# Access: a backup downloaded by staff is reported; via log_action directly
s = SessionLocal(); main.log_action(s, AMAL.id, "download_backup", "backup #3"); s.close()
ck("backup downloaded -> alert", alerts()[-1][0] == "download_backup")
s = SessionLocal(); main.log_action(s, AMAL.id, "project_payment", "912 MEP added"); s.close()
ck("project payment added (routine): no alert", alerts()[-1][0] == "download_backup")
s = SessionLocal(); main.log_action(s, AMAL.id, "project_payment", "912 MEP removed"); s.close()
ck("project payment removed -> alert", alerts()[-1][0] == "project_payment")

# Five wrong passwords in ten minutes: one alert, for any login (admin too)
for _ in range(6):
    c.post("/auth/login", data={"username": "boss", "password": "wrong"})
ck("wrong-password burst -> one alert", sum(1 for x in alerts() if x[0] == "login_burst") == 1, [x for x in alerts() if x[0] == "login_burst"])

# The settings list shows the group to the admin only
g = {x["id"]: x for x in c.get("/notifications/settings", headers=B).json()["groups"]}
ck("admin can switch Watch on/off", g.get("watch", {}).get("allowed") is True, g.get("watch"))
g = {x["id"]: x for x in c.get("/notifications/settings", headers=A).json()["groups"]}
ck("staff cannot", not g.get("watch", {}).get("allowed"), g.get("watch"))
print("\nALL PASS" if not FAIL else f"\n{len(FAIL)} FAILED: {FAIL}")

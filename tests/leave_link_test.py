"""The leave register and the absence register are one record: a spell
approved on either side shows on the other, and the salary cycle deducts
it once. Also: contract expiry and the contract document, the air ticket
and the file's last ticket, and the pay group and the People register."""
import os, sys
from datetime import date, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
os.environ.setdefault("INFINIA_NO_PUSH", "1")
from fastapi.testclient import TestClient
import main, models, auth
from database import SessionLocal

db = SessionLocal()
db.add(models.User(username="boss3", hashed_password=auth.hash_password("p"), full_name="Boss", role="admin"))
db.add(models.Employee(emp_no="S-101", name="OFFICE ONE", staff=True, pay_group="staff",
                       basic_salary=3000, allowance=0, total_salary=3000, active=True, joined_on=date(2024, 1, 1)))
db.add(models.Employee(emp_no="L-101", name="LABOUR ONE", trade="MASON", total_salary=1500, basic_salary=1000, active=True))
db.commit()
EID = db.query(models.Employee).filter_by(emp_no="S-101").first().id
db.close()
c = TestClient(main.app)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "boss3", "password": "p"}).json()["access_token"]}
FAIL = []
def ck(l, ok, x=""):
    print(("PASS " if ok else "FAIL ") + l + ("" if ok else f"  [{x}]"))
    if not ok: FAIL.append(l)

def days(batch=None):
    s = SessionLocal()
    q = s.query(models.StaffLeave).filter(models.StaffLeave.employee_id == EID)
    if batch:
        q = q.filter(models.StaffLeave.batch == batch)
    out = sorted((l.on_date, l.kind) for l in q.all()); s.close(); return out

def spells():
    return [r for r in c.get("/employees/people/leave-register", headers=H).json()["rows"] if r["emp_no"] == "S-101"]

T = main._dubai_today()
d0 = T + timedelta(days=40)

# 1. Leave register -> absence register
r = c.post("/employees/people/leave-register", headers=H, json={"emp_no": "S-101", "leave_type": "annual", "status": "pending",
           "leave_on": d0.isoformat(), "return_on": (d0 + timedelta(days=5)).isoformat()})
ck("spell added (pending)", r.status_code == 200, r.text); rid = r.json()["id"]
ck("pending: nothing on the absence register yet", days() == [], days())
r = c.put(f"/employees/people/leave-register/{rid}", headers=H, json={"status": "approved"})
ck("approve", r.status_code == 200, r.text)
ck("approved: 5 vacation days on the absence register", days() == [(d0 + timedelta(days=i), "vacation") for i in range(5)], days())
ab = c.get("/employees/leave", headers=H, params={"emp_no": "S-101"}).json()["rows"]
ck("the absence register lists it as one entry", len(ab) == 1 and ab[0]["days"] == 5, ab)
r = c.put(f"/employees/people/leave-register/{rid}", headers=H, json={"status": "returned", "return_on": (d0 + timedelta(days=3)).isoformat()})
ck("came back early: 3 days", len(days()) == 3, days())
r = c.put(f"/employees/people/leave-register/{rid}", headers=H, json={"leave_type": "unpaid"})
ck("changed to unpaid: the days follow", {k for _, k in days()} == {"unpaid"}, days())
ck("no second spell made", len(spells()) == 1, spells())
c.delete(f"/employees/people/leave-register/{rid}", headers=H)
ck("spell deleted: its days come off", days() == [], days())

# 2. Absence register -> leave register
d1 = T + timedelta(days=60)
r = c.post("/employees/leave", headers=H, json={"emp_no": "S-101", "kind": "vacation", "from": d1.isoformat(),
           "to": (d1 + timedelta(days=9)).isoformat(), "leave_salary": 1500})
ck("vacation on the absence register", r.status_code == 200, r.text); batch = r.json()["batch"]
sp = spells()
ck("shows on the leave register as an approved annual spell", len(sp) == 1 and sp[0]["leave_type"] == "annual"
   and sp[0]["leave_on"] == d1.isoformat() and sp[0]["approved_days"] == 10, sp)
ck("same batch links them", batch == f"lr{sp[0]['id']}", (batch, sp))
s = SessionLocal(); ls = s.query(models.PayItem).filter(models.PayItem.source == f"leave:{batch}").count(); s.close()
ck("leave salary kept with it", ls == 1)
r = c.put(f"/employees/leave/entry/{batch}", headers=H, json={"emp_no": "S-101", "kind": "vacation", "from": d1.isoformat(),
          "to": (d1 + timedelta(days=4)).isoformat(), "leave_salary": 1500})
sp = spells()
ck("shortened on the absence register: the spell follows", len(sp) == 1 and sp[0]["approved_days"] == 5, sp)
r = c.put(f"/employees/people/leave-register/{sp[0]['id']}", headers=H, json={"remark": "ok"})
ck("saving the spell keeps the days and the leave salary", len(days(batch)) == 5, days(batch))
s = SessionLocal(); ls = s.query(models.PayItem).filter(models.PayItem.source == f"leave:{batch}").count(); s.close()
ck("leave salary still there", ls == 1)
r = c.put(f"/employees/leave/entry/{batch}", headers=H, json={"emp_no": "S-101", "kind": "absent", "from": d1.isoformat(), "to": d1.isoformat()})
ck("turned into a plain absence: off the leave register", spells() == [], spells())
newb = r.json()["batch"]
c.delete(f"/employees/leave/entry/{newb}", headers=H)
r = c.post("/employees/leave", headers=H, json={"emp_no": "S-101", "kind": "sick", "from": d1.isoformat(), "to": (d1 + timedelta(days=1)).isoformat()})
b2 = r.json()["batch"]
ck("sick days show as sick leave", [x["leave_type"] for x in spells()] == ["sick"], spells())
c.delete(f"/employees/leave/entry/{b2}", headers=H)
ck("deleted on the absence register: gone from the leave register", spells() == [], spells())

# 3. The same days typed on both sides are not doubled
c.post("/employees/leave", headers=H, json={"emp_no": "S-101", "kind": "absent", "from": d0.isoformat(), "to": d0.isoformat()})
r = c.post("/employees/people/leave-register", headers=H, json={"emp_no": "S-101", "leave_type": "annual", "status": "approved",
           "leave_on": d0.isoformat(), "approved_days": 3})
ck("a spell over a day already recorded still saves", r.status_code == 200, r.text)
ck("that day is not entered twice", len(days()) == 3 and sum(1 for d, _ in days() if d == d0) == 1, days())

# 4. Labour: spells stay on the leave register only (pay is by days present)
r = c.post("/employees/people/leave-register", headers=H, json={"emp_no": "L-101", "leave_type": "annual", "status": "approved",
           "leave_on": d0.isoformat(), "approved_days": 3})
s = SessionLocal(); n = s.query(models.StaffLeave).join(models.Employee).filter(models.Employee.emp_no == "L-101").count(); s.close()
ck("labour spell saves, no office absence days", r.status_code == 200 and n == 0, r.text)

# 5. Contract expiry <-> contract document
exp = (T + timedelta(days=200)).isoformat()
r = c.post("/employees/documents", headers=H, json={"emp_no": "S-101", "kind": "contract", "number": "MOL-77", "expires_on": exp})
ck("contract document saved", r.status_code == 200, r.text)
s = SessionLocal(); p = s.query(models.PeopleProfile).filter_by(employee_id=EID).first(); s.close()
ck("the People file shows the same contract", p and p.contract_expiry and p.contract_expiry.isoformat() == exp and p.contract_no == "MOL-77",
   p and (p.contract_expiry, p.contract_no))

# 6. Air ticket with a vacation -> last ticket on the file
d2 = T + timedelta(days=90)
c.post("/employees/leave", headers=H, json={"emp_no": "S-101", "kind": "vacation", "from": d2.isoformat(), "to": (d2 + timedelta(days=2)).isoformat(), "air_ticket": 1200})
s = SessionLocal(); p = s.query(models.PeopleProfile).filter_by(employee_id=EID).first(); s.close()
ck("air ticket paid: the file's last ticket follows", p.last_ticket_on == d2, p.last_ticket_on)

print("\nALL PASS" if not FAIL else f"\n{len(FAIL)} FAILED: {FAIL}")

# 7. Typed twice before the link existed: tied together at start-up, no day changed
d3 = T + timedelta(days=150)
s = SessionLocal()
s.add(models.LeaveRecord(employee_id=EID, leave_type="annual", status="approved", leave_on=d3, approved_days=4))
for i in range(4):
    s.add(models.StaffLeave(employee_id=EID, on_date=d3 + timedelta(days=i), portion=1.0, kind="vacation", pay_rule="auto", batch="oldbatch1", paid=False))
s.commit(); rid = s.query(models.LeaveRecord).order_by(models.LeaveRecord.id.desc()).first().id; s.close()
import people
people.link_existing_leave(SessionLocal)
ck("old double entry linked, still 4 days", days(f"lr{rid}") == [(d3 + timedelta(days=i), "vacation") for i in range(4)], days(f"lr{rid}"))
c.delete(f"/employees/people/leave-register/{rid}", headers=H)
ck("and now deleting the spell clears its days", days(f"lr{rid}") == [], days(f"lr{rid}"))
print("\nALL PASS (with start-up link)" if not FAIL else f"\n{len(FAIL)} FAILED: {FAIL}")

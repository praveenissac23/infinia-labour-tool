"""Expiry Reminder: 'Mark started' stops the reminders for that document,
the page keeps showing it, and renewing it clears the mark."""
import os, sys
from datetime import timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
os.environ.setdefault("INFINIA_NO_PUSH", "1")
from fastapi.testclient import TestClient
import main, models, auth
from database import SessionLocal

db = SessionLocal()
db.add(models.User(username="boss2", hashed_password=auth.hash_password("p"), full_name="Boss", role="admin"))
db.add(models.Employee(emp_no="X-1", name="ALI ONE", trade="MASON", total_salary=1500, basic_salary=1000, active=True))
db.add(models.Employee(emp_no="X-2", name="BABU TWO", trade="MASON", total_salary=1500, basic_salary=1000, active=True))
db.commit(); db.close()
c = TestClient(main.app)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "boss2", "password": "p"}).json()["access_token"]}
FAIL = []
def ck(l, ok, x=""):
    print(("PASS " if ok else "FAIL ") + l + ("" if ok else f"  [{x}]"))
    if not ok: FAIL.append(l)

today = main._dubai_today()
d1 = c.post("/employees/documents", headers=H, json={"emp_no": "X-1", "kind": "visa", "number": "V1", "expires_on": (today - timedelta(days=3)).isoformat()}).json()
d2 = c.post("/employees/documents", headers=H, json={"emp_no": "X-2", "kind": "eid", "number": "E2", "expires_on": (today + timedelta(days=7)).isoformat()}).json()
ck("two documents on file", d1.get("id") and d2.get("id"), (d1, d2))

def bell():
    n = [x for x in c.get("/notifications", headers=H).json()["notifications"] if x.get("kind") == "expiry"]
    return n[0] if n else None
b = bell()
ck("the bell names both", b and "ALI ONE" in b["detail"] and "BABU TWO" in b["detail"], b)

r = c.post("/employees/expiry/started", headers=H, json={"type": "person", "id": d1["id"], "on": True})
ck("mark started", r.status_code == 200, r.text)
ck("listed as started", [x["id"] for x in c.get("/employees/expiry/started", headers=H).json()["rows"]] == [d1["id"]])
b = bell()
ck("the bell drops the started one, keeps the other", b and "ALI ONE" not in b["detail"] and "BABU TWO" in b["detail"] and "1 expired" not in b["title"], b)
import expiry
s = SessionLocal()
subj, text, html, has = expiry.mail_body(s)
ck("the morning email leaves it out", "ALI ONE" not in text and "BABU TWO" in text, text[:300])
ck("the page still shows it", any(x["id"] == d1["id"] for x in c.get("/employees/documents", headers=H).json()["rows"]))
ck("page counts unchanged", c.get("/employees/expiry/summary", headers=H).json()["expired"] == 1)

c.post("/employees/expiry/started", headers=H, json={"type": "person", "id": d2["id"], "on": True})
ck("both started: no expiry notice at all", bell() is None, bell())

# renewed - but the new date is also near, so the reminders must come back for it
c.post("/employees/documents", headers=H, json={"id": d1["id"], "emp_no": "X-1", "kind": "visa", "number": "V1b", "expires_on": (today + timedelta(days=2)).isoformat()})
ck("renewing clears the mark", d1["id"] not in [x["id"] for x in c.get("/employees/expiry/started", headers=H).json()["rows"]])
b = bell()
ck("renewed date is reminded again", b and "ALI ONE" in b["detail"], b)

c.post("/employees/expiry/started", headers=H, json={"type": "person", "id": d2["id"], "on": False})
b = bell()
ck("undo brings it back", b and "BABU TWO" in b["detail"], b)
ck("a bad id is refused", c.post("/employees/expiry/started", headers=H, json={"type": "person", "id": 99999}).status_code == 404)
s.close()
print("\nALL PASS" if not FAIL else f"\n{len(FAIL)} FAILED: {FAIL}")

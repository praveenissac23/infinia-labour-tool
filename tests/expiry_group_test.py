"""Expiry Reminder: a man's visa, labour card and Emirates ID are one renewal -
one reminder line, one 'Mark started' for the three."""
import os, sys, tempfile
from datetime import timedelta
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
os.environ["INFINIA_CRED_KEY_FILE"] = tempfile.mktemp(suffix=".key")
os.environ.setdefault("INFINIA_NO_PUSH", "1")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
from fastapi.testclient import TestClient
import main, models, auth, expiry
from database import SessionLocal

db = SessionLocal()
db.add(models.User(username="boss3", hashed_password=auth.hash_password("p"), full_name="Jomon", role="admin"))
db.add(models.Employee(emp_no="G-1", name="ERIC MAMBO", trade="MASON", total_salary=1500, basic_salary=1000, active=True))
db.add(models.Employee(emp_no="G-2", name="IAN KIP", trade="MASON", total_salary=1500, basic_salary=1000, active=True))
db.commit(); db.close()
c = TestClient(main.app)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "boss3", "password": "p"}).json()["access_token"]}
FAIL = []
def ck(l, ok, x=""):
    print(("PASS " if ok else "FAIL ") + l + ("" if ok else f"  [{x}]"))
    if not ok: FAIL.append(l)
today = main._dubai_today()
D = lambda n: (today + timedelta(days=n)).isoformat()
add = lambda emp, kind, n: c.post("/employees/documents", headers=H, json={"emp_no": emp, "kind": kind, "number": kind, "expires_on": D(n)}).json()["id"]
v = add("G-1", "visa", 7); lc = add("G-1", "labour_card", 8); e = add("G-1", "eid", 9); pp = add("G-1", "passport", 3)
iv = add("G-2", "visa", 2); ie = add("G-2", "eid", 400)           # his EID is good for another year

s = SessionLocal()
its = [i for i in expiry.notice_items(s) if i["who"].startswith("G-1")]
grp = [i for i in its if i["what"] == expiry.GROUP_LABEL]
ck("Eric: visa, labour card and EID on ONE line", len(grp) == 1 and grp[0]["days_left"] == 7, its)
ck("passport stays its own line", any(i["what"] == "Passport" for i in its) and len(its) == 2, its)
ian = [i for i in expiry.notice_items(s) if i["who"].startswith("G-2")]
ck("Ian: visa and EID on one line even with the EID a year away", len(ian) == 1 and ian[0]["what"] == expiry.GROUP_LABEL and ian[0]["days_left"] == 2, ian)
mail = expiry.mail_body(s)[1]
ck("morning email: Eric's three as one line", mail.count("G-1 ERIC MAMBO: " + expiry.GROUP_LABEL) == 1 and "G-1 ERIC MAMBO: Labour card" not in mail, mail)
ck("the count treats the three as one", expiry.summary(s)["badge"] == 3, expiry.summary(s)["badge"])  # Eric group, Eric passport, Ian visa

r = c.post("/employees/expiry/started", headers=H, json={"type": "person", "id": lc, "on": True})
ck("Mark started on any one of the three", r.status_code == 200, r.text)
st = {x["id"] for x in c.get("/employees/expiry/started", headers=H).json()["rows"]}
ck("all three show Started", {v, lc, e} <= st and pp not in st, st)
s.close(); s = SessionLocal()
its = [i for i in expiry.notice_items(s) if i["who"].startswith("G-1")]
ck("no more reminder for the three; passport still reminded", [i["what"] for i in its] == ["Passport"], its)
b = [x for x in c.get("/notifications", headers=H).json()["notifications"] if x.get("kind") == "expiry"][0]
ck("the bell leaves Eric's visa group out", "ERIC MAMBO (" + expiry.GROUP_LABEL not in b["detail"], b)

c.post("/employees/expiry/started", headers=H, json={"type": "person", "id": iv, "on": True})
st = {x["id"] for x in c.get("/employees/expiry/started", headers=H).json()["rows"]}
ck("Ian: started marks his visa and EID", iv in st and ie in st, st)
x = c.get(f"/employees/expiry/close?type=person&id={iv}", headers=H).json()
ck("Ian's Close pop-up: Visa, Labour card (not on file), Emirates ID", [d["what"] for d in x["docs"]] == ["Visa", "Labour card", "Emirates ID"] and x["docs"][1]["id"] == "new:labour_card", x)
r = c.post("/employees/expiry/close", headers=H, json={"type": "person", "id": iv, "dates": {str(iv): D(730), str(ie): D(400), "new:labour_card": D(730)}})
docs = [d for d in c.get("/employees/documents", headers=H).json()["rows"] if d["emp_no"] == "G-2"]
ck("visa renewed, EID left as it was, labour card added", r.status_code == 200 and {d["kind"]: d["expires_on"] for d in docs} == {"visa": D(730), "eid": D(400), "labour_card": D(730)}, (r.text, docs))

# visa renewed first, EID still in process: stays quiet
c.post("/employees/documents", headers=H, json={"id": v, "emp_no": "G-1", "kind": "visa", "number": "v2", "expires_on": D(730)})
s.close(); s = SessionLocal()
ck("visa renewed, EID still in process: still no reminder", not any(i["who"].startswith("G-1") and i["kind"] in expiry.GROUP and i["days_left"] <= 90 for i in expiry.notice_items(s)))
c.post("/employees/expiry/started", headers=H, json={"type": "person", "id": e, "on": False})
st = {x["id"] for x in c.get("/employees/expiry/started", headers=H).json()["rows"]}
ck("undo takes the mark off the group", lc not in st and e not in st, st)
s.close()

# ---- Close: set new expiry, or delete the entry ----
x = c.get(f"/employees/expiry/close?type=person&id={lc}", headers=H).json()
ck("Close pop-up: always Visa, Labour card, Emirates ID", [d["what"] for d in x["docs"]] == ["Visa", "Labour card", "Emirates ID"] and sorted(d["id"] for d in x["docs"]) == sorted([v, lc, e]), x)
r = c.post("/employees/expiry/close", headers=H, json={"type": "person", "id": lc, "dates": {str(lc): D(5)}})
ck("a date before the old one is refused", r.status_code == 400, r.text)
c.post("/employees/expiry/started", headers=H, json={"type": "person", "id": lc, "on": True})
r = c.post("/employees/expiry/close", headers=H, json={"type": "person", "id": lc, "dates": {str(v): D(730), str(lc): D(731), str(e): D(732)}})
ck("Set new expiry: labour card and EID saved, visa unchanged left alone", r.status_code == 200 and r.json()["n"] == 2, r.text)
docs = {d["id"]: d for d in c.get("/employees/documents", headers=H).json()["rows"]}
ck("new dates on file", docs[lc]["expires_on"] == D(731) and docs[e]["expires_on"] == D(732), (docs[lc], docs[e]))
st = {x["id"] for x in c.get("/employees/expiry/started", headers=H).json()["rows"]}
ck("started mark cleared on close", lc not in st and e not in st, st)
r = c.post("/employees/expiry/remove", headers=H, json={"type": "person", "id": pp})
docs = {d["id"] for d in c.get("/employees/documents", headers=H).json()["rows"]}
ck("Delete entry: the passport is gone", r.status_code == 200 and pp not in docs and lc in docs, r.text)
s = SessionLocal()
ck("closing and deleting are in the activity log", s.query(models.AuditLog).filter(models.AuditLog.action.in_(["expiry_closed", "expiry_removed"])).count() == 3)
s.close()

# ---- the PRO's visa file: open = started; completed = new dates asked ----
import visa as V
s = SessionLocal()
g3 = models.Employee(emp_no="G-3", name="PRADEEP K", trade="MASON", total_salary=1500, basic_salary=1000, active=True); s.add(g3); s.commit()
s.close()
pv = add("G-3", "visa", 4); pe = add("G-3", "eid", 4)
s = SessionLocal()
ck("no visa file: Pradeep is reminded", any(i["who"].startswith("G-3") for i in expiry.notice_items(s)))
adm = s.query(models.User).filter(models.User.username == "boss3").one()
f = V.file_for(s, "G-3", adm.id); s.commit()
ck("visa file open: reminders stop", not any(i["who"].startswith("G-3") for i in expiry.notice_items(s)))
st = {x["id"]: x for x in c.get("/employees/expiry/started", headers=H).json()["rows"]}
ck("page shows Started (visa file) on his visa and EID", st.get(pv, {}).get("visa") and st.get(pe, {}).get("visa"), st)
r = V.complete(f.id, s, adm)
ck("visa completed: the Close pop-up is offered for his documents", r.get("expiry_doc") in (pv, pe), r)
ck("completed, dates not yet set: reminders come back", any(i["who"].startswith("G-3") for i in expiry.notice_items(s)))
s.close()
print("\nALL PASS" if not FAIL else f"\n{len(FAIL)} FAILED: {FAIL}"); sys.exit(1 if FAIL else 0)

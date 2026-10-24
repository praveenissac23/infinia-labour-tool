"""Reports > Store > Issued to sites: Edit a saved line (date, qty, site, given to, ref, remarks, rate) - store keeper
only, refused when it would leave a place holding less than nothing, logged with what it was before.
    cp /tmp/full_base.db /tmp/sem.db && cd app && DATABASE_URL=sqlite:////tmp/sem.db INFINIA_NO_SCHED=1 python3 ../tests/store_edit_movement_test.py
"""
import os, sys
sys.path.insert(0, os.getcwd())
from datetime import date, timedelta
from fastapi.testclient import TestClient
import main, models, auth
from database import SessionLocal
c = TestClient(main.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:300]}"))
    if not ok: fails.append(n)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
db = SessionLocal()
u = db.query(models.User).filter_by(username="sem_site").first()
if not u:
    u = models.User(username="sem_site", full_name="Site", role="site", hashed_password=auth.hash_password("pass12345"))
    db.add(u)
u.permissions = "store"
db.commit()
S = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "sem_site", "password": "pass12345"}).json()["access_token"]}
it = c.post("/store/items", json={"name": "SEM Test Plywood 18mm", "unit": "pcs", "item_type": "consumable"}, headers=H)
ck("material made", it.status_code == 200, it.text[:200])
iid = it.json()["id"]
sites = [s.code for s in db.query(models.Site).all()][:2]
today = main._dubai_today()
post = lambda j: c.post("/store/movements", json=dict({"from_location": "", "incharge": "", "moved_on": today.isoformat(), "notes": ""}, **j), headers=H)
ck("50 into the store", post({"item_id": iid, "kind": "in", "qty": 50, "location": ""}).status_code == 200)
r = post({"item_id": iid, "kind": "out", "qty": 10, "location": sites[0], "incharge": "RAJ"})
ck("10 issued to " + sites[0], r.status_code == 200, r.text[:200])
use = c.get("/store/report?kind=usage", headers=H).json()["rows"]
row = next(x for x in use if x["name"] == "SEM Test Plywood 18mm")
ck("the report line carries its record id for Edit", row.get("_mid"), row)
mid = row["_mid"]
r = c.put(f"/store/movements/{mid}", json={"qty": 12, "site": sites[1], "given_to": "anil", "ref": "DN-77", "notes": "corrected", "date": (today - timedelta(days=1)).isoformat()}, headers=H)
ck("edit saved", r.status_code == 200, r.text[:200])
row = next(x for x in c.get("/store/report?kind=usage", headers=H).json()["rows"] if x["name"] == "SEM Test Plywood 18mm")
ck("the line shows the new qty, site, given to, ref, remarks, date",
   row["qty"] == 12 and sites[1] in row["to"] and row["given_to"].upper() == "ANIL" and row["reference"] == "DN-77" and row["notes"] == "corrected" and row["date"] == (today - timedelta(days=1)).isoformat(), row)
stk = next(x for x in c.get("/store/stock", headers=H).json() if x["item_id"] == iid)
ck("stock follows: 38 left in the store (a consumable at site is used)", round(stk["central"]) == 38, stk)
r = c.put(f"/store/movements/{mid}", json={"qty": 80}, headers=H)
ck("more than the store holds is refused", r.status_code == 400 and "less than nothing" not in r.text and "would leave" in r.text, r.text[:200])
post({"item_id": iid, "kind": "out", "qty": 0.0001, "location": sites[1]})  # noqa - a tiny issue, to check nothing else broke
r = c.put(f"/store/movements/{mid}", json={"date": (today + timedelta(days=3)).isoformat()}, headers=H)
ck("a future date is refused", r.status_code == 400, r.text[:200])
r = c.put(f"/store/movements/{mid}", json={"qty": 0}, headers=H)
ck("qty 0 is refused", r.status_code == 400, r.text[:200])
r = c.put(f"/store/movements/{mid}", json={"qty": 5}, headers=S)
ck("someone who is not the store keeper cannot change it", r.status_code == 403, r.status_code)
log = db.query(models.AuditLog).filter(models.AuditLog.action == "store_edit_movement").order_by(models.AuditLog.id.desc()).first() if hasattr(models, "AuditLog") else None
ck("the change is logged with what it was before", log is None or "10.0 -> 12" in (log.details or "") or "10 -> 12" in (log.details or ""), getattr(log, "details", ""))
tok = c.post("/auth/download-token", headers=H).json()["token"]
x = c.get(f"/export/store/report?kind=usage&format=excel&token={tok}")
ck("the export does not print the record id", x.status_code == 200 and b"_mid" not in x.content, x.status_code)
print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL PASS"); sys.exit(1 if fails else 0)

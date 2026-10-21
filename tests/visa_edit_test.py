"""PRO petty cash > Visa: payments can be changed or removed on an ongoing visa and on a completed one
(its total in General follows) until accounts approve; the visa total in General can be reworded and
removing it puts the visa back to ongoing.
    cd app && DATABASE_URL=sqlite:////tmp/visaed.db INFINIA_NO_SCHED=1 python3 ../tests/visa_edit_test.py
"""
import os, sys, time
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main, models
from database import SessionLocal
c = TestClient(main.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {x}"))
    if not ok: fails.append(n)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
who = "Visa Test " + str(int(time.time()) % 100000)
r = c.post("/store/visa/payments", json={"person": who, "date": "2026-10-20", "step": "Medical", "amount": "300", "description": "first"}, headers=H)
fid = r.json()["file_id"]
c.post("/store/visa/payments", json={"person": who, "date": "2026-10-20", "step": "EID", "amount": "370", "description": "second"}, headers=H)
held = c.get("/store/visa/held", headers=H).json()
v = next(x for x in held["ongoing"] if x["id"] == fid)
p1 = next(p for p in v["payments"] if p["description"] == "first")
x = c.put(f"/store/visa/payments/{p1['id']}", json={"date": "2026-10-20", "step": "Medical", "amount": "300", "description": "Medical test - Al Qusais"}, headers=H)
held = c.get("/store/visa/held", headers=H).json(); v = next(x for x in held["ongoing"] if x["id"] == fid)
ck("description changed on an ongoing visa", any(p["description"] == "Medical test - Al Qusais" for p in v["payments"]), x.text)
c.post(f"/store/visa/files/{fid}/complete", json={}, headers=H)
db = SessionLocal()
vf = db.get(models.VisaFile, fid); line = db.get(models.PettyCash, vf.posted_id)
ck("completed: 670 in General", round(line.paid, 2) == 670, line.paid)
held = c.get("/store/visa/held", headers=H).json(); v = next(x for x in held["completed"] if x["id"] == fid)
p2 = next(p for p in v["payments"] if p["description"] == "second")
x = c.put(f"/store/visa/payments/{p2['id']}", json={"date": "2026-10-20", "step": "EID", "amount": "400", "description": "EID - typing centre"}, headers=H)
db.expire_all(); line = db.get(models.PettyCash, vf.posted_id)
ck("payment of a completed visa changed - the General total follows (700)", x.status_code == 200 and round(line.paid, 2) == 700, (x.text, line.paid))
x = c.delete(f"/store/visa/payments/{p1['id']}", headers=H)
db.expire_all(); line = db.get(models.PettyCash, vf.posted_id)
ck("payment removed - total 400, '1 payment' in the wording", x.status_code == 200 and round(line.paid, 2) == 400 and "(1 payment)" in line.description, (line.paid, line.description))
x = c.put(f"/store/petty-cash/{line.id}", json={"date": "2026-10-21", "description": f"{who} - visa renewal 2026", "paid": "1", "received": 0, "book": "pro"}, headers=H)
db.expire_all(); line = db.get(models.PettyCash, vf.posted_id)
ck("visa total in General reworded; amount stays the payments", x.status_code == 200 and line.description.endswith("visa renewal 2026") and round(line.paid, 2) == 400, (x.text, line.description, line.paid))
x = c.delete(f"/store/petty-cash/{line.id}", headers=H)
db.expire_all(); vf = db.get(models.VisaFile, fid)
ck("removing the visa total puts the visa back to ongoing", x.status_code == 200 and x.json().get("reopened") == who and vf.status == "ongoing" and vf.posted_id is None, x.text)
c.post(f"/store/visa/files/{fid}/complete", json={}, headers=H)
db.expire_all(); vf = db.get(models.VisaFile, fid); line = db.get(models.PettyCash, vf.posted_id); line.zoho_status = "approved"; db.commit()
held = c.get("/store/visa/held", headers=H).json(); v = next(x for x in held["completed"] if x["id"] == fid)
x = c.delete(f"/store/visa/payments/{v['payments'][0]['id']}", headers=H)
ck("once accounts approve, the payments are locked", x.status_code == 400 and "approved" in x.text, x.text)
print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL PASS"); sys.exit(1 if fails else 0)

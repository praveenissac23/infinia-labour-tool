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
# ---- a wrong name typed under Whose visa: renamed, put together, payment moved, empty visa removed ----
tag = str(int(time.time()) % 100000)
bad = c.post("/store/visa/payments", json={"person": "Ceaser New Visa Exppense " + tag, "date": "2026-10-21", "step": "Replacement Contract", "amount": "228.42"}, headers=H).json()["file_id"]
empty = c.post("/store/visa/payments", json={"person": "Ceaser Out Side " + tag, "date": "2026-10-21", "amount": "10"}, headers=H).json()["file_id"]
x = c.put(f"/store/visa/files/{bad}", json={"person": "Ceaser " + tag}, headers=H)
ck("visa renamed (the name typed wrong)", x.status_code == 200 and x.json()["person"] == "Ceaser " + tag, x.text)
held = c.get("/store/visa/held", headers=H).json(); ve = next(v for v in held["ongoing"] if v["id"] == empty)
x = c.put(f"/store/visa/payments/{ve['payments'][0]['id']}", json={"person": "Ceaser " + tag, "date": "2026-10-21", "amount": "10", "step": "Medical"}, headers=H)
held = c.get("/store/visa/held", headers=H).json()
vc = next(v for v in held["ongoing"] if v["id"] == bad)
ck("payment moved to the right name; the visa left empty is gone", x.status_code == 200 and len(vc["payments"]) == 2 and not any(v["id"] == empty for v in held["ongoing"]), [v["person"] for v in held["ongoing"]])
dup = c.post("/store/visa/payments", json={"person": "Ceaser Dup " + tag, "date": "2026-10-21", "amount": "5"}, headers=H).json()["file_id"]
x = c.put(f"/store/visa/files/{dup}", json={"person": "Ceaser " + tag}, headers=H)
held = c.get("/store/visa/held", headers=H).json(); vc = next(v for v in held["ongoing"] if v["id"] == bad)
ck("renamed to someone with a visa in progress: put together", x.json().get("merged_into") == bad and len(vc["payments"]) == 3 and not any(v["id"] == dup for v in held["ongoing"]), x.text)
nopay = c.post("/store/visa/payments", json={"person": "Nobody " + tag, "date": "2026-10-21", "amount": "1"}, headers=H).json()["file_id"]
held = c.get("/store/visa/held", headers=H).json(); vn = next(v for v in held["ongoing"] if v["id"] == nopay)
ck("a visa with payments cannot be removed", c.delete(f"/store/visa/files/{nopay}", headers=H).status_code == 400)
c.delete(f"/store/visa/payments/{vn['payments'][0]['id']}", headers=H)
ck("an empty visa can be removed", c.delete(f"/store/visa/files/{nopay}", headers=H).status_code == 200)
print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL PASS"); sys.exit(1 if fails else 0)

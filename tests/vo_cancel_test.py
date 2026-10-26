"""Variations: cancel one with a note (e.g. done before the portal) - kept on the log, not counted, no number,
the ones after it move up (V05 becomes V04); restore brings it back; "QS log ref." taken off the remarks.
    cp /tmp/full_base.db /tmp/vc.db && cd app && DATABASE_URL=sqlite:////tmp/vc.db INFINIA_NO_SCHED=1 python3 ../tests/vo_cancel_test.py
"""
import os, sys
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main as M
import estimation as E
c = TestClient(M.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:300]}"))
    if not ok: fails.append(n)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
pid = next(p for p in c.get("/store/est/meta", headers=H).json()["projects"] if p["code"] == "914")["id"]
ids = []
for i, (t, amt, st) in enumerate([("Shoring", 10000, "Approved"), ("Dewatering", 20000, "Approved"), ("Extra blockwork", 5000, "Submitted"),
                                  ("Swimming Pool Excavation Works", 30000, "Approved"), ("Pool tiling change", 8000, "Submitted")], 1):
    r = c.post("/store/est/variations", headers=H, json={"project_id": pid, "title": t, "submitted_amount": amt, "approved_amount": amt if st == "Approved" else 0,
                                                         "status": st, "notes": f"QS log ref. OHP-CP0{i} - kept remark {i}" if i == 4 else ("QS log ref. CP03" if i == 3 else "")}).json()
    ids.append(r["id"])
vos = lambda: {v["id"]: v for v in c.get(f"/store/est/projects/{pid}", headers=H).json()["variations"]}
summ = lambda: c.get(f"/store/est/projects/{pid}", headers=H).json()["summary"]
refs = [vos()[i]["ref"] for i in ids]
base = int(refs[0][1:]) - 1
ck("five variations numbered in order", refs == [E.vref(base + k) for k in range(1, 6)], refs)
app0 = summ()["approved_vo"]
r = c.post(f"/store/est/variations/{ids[3]}/cancel", headers=H, json={})
ck("cancel needs a note", r.status_code == 400)
r = c.post(f"/store/est/variations/{ids[3]}/cancel", headers=H, json={"note": "Implemented before the portal"})
v = vos()
ck("cancelled: kept, marked Cancelled with its note and date", r.status_code == 200 and v[ids[3]]["status"] == "Cancelled" and v[ids[3]]["cancel_note"] == "Implemented before the portal" and v[ids[3]]["cancelled_on"], v[ids[3]])
ck("cancelled: no number", v[ids[3]]["ref"] == "")
ck("the one after moves up (V05 -> V04)", v[ids[4]]["ref"] == E.vref(base + 4), v[ids[4]]["ref"])
ck("the ones before keep their numbers", [v[i]["ref"] for i in ids[:3]] == [E.vref(base + k) for k in range(1, 4)])
ck("not counted in the approved variations / contract value", summ()["approved_vo"] == round(app0 - 30000, 2), (app0, summ()["approved_vo"]))
n = c.post("/store/est/variations", headers=H, json={"project_id": pid, "title": "New one", "submitted_amount": 1000}).json()["id"]
ck("a new variation takes the next number with no gap", vos()[n]["ref"] == E.vref(base + 5), vos()[n]["ref"])
tok = c.post("/auth/download-token", headers=H).json()["token"]
x = c.get(f"/export/est/variations?token={tok}&pid={pid}&format=preview").text
ck("the log export lists it as Cancelled with the note", "Cancelled" in x and "Implemented before the portal" in x)
r = c.post(f"/store/est/variations/{ids[3]}/cancel", headers=H, json={"restore": True})
v = vos()
ck("restore: back to its old status, at the end of the log with the next number", v[ids[3]]["status"] == "Approved" and v[ids[3]]["ref"] == E.vref(base + 6), (v[ids[3]]["status"], v[ids[3]]["ref"]))
ck("restore: counted again", summ()["approved_vo"] == app0)
# QS log ref taken off the remarks (once, on start)
db = M.SessionLocal()
db.query(M.models.Setting).filter(M.models.Setting.key == "est_vo_qsref_gone").delete(); db.commit(); db.close()
E.drop_qs_log_refs(M.SessionLocal)
ck('"QS log ref. OHP-CP04 - " taken off, the remark kept', vos()[ids[3]]["notes"] == "kept remark 4", vos()[ids[3]]["notes"])
ck("...the QS number kept out of sight", E.EstVariation and M.SessionLocal().get(E.EstVariation, ids[3]).qs_ref == "OHP-CP04")
ck('a remark that was only "QS log ref. CP03" is now empty', vos()[ids[2]]["notes"] == "", vos()[ids[2]]["notes"])
print("ALL PASS" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)

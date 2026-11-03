"""912 (3 Nov 2026): old certificates typed in only to bring the history up to date were going through the whole
approval chain to Accounts and the MD. 'Old PC - already paid' takes one straight to Paid - nobody is told -
but never the newest certificate of a subcontract (that one still goes through the approvals).
    cd app && DATABASE_URL=sqlite:////tmp/op.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/pc_old_paid_test.py
"""
import os, sys
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main as M
import estimation as E
import database
c = TestClient(M.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:300]}"))
    if not ok: fails.append(n)
login = lambda u, p: {"Authorization": "Bearer " + c.post("/auth/login", data={"username": u, "password": p}).json().get("access_token", "")}
H = login("admin", "changeme123")
def user(name, perms):
    r = c.post("/users", headers=H, json={"username": name, "password": name + "12345", "full_name": name.title(), "role": "office"})
    uid = r.json()["id"] if r.status_code in (200, 201) else next(u["id"] for u in c.get("/users", headers=H).json() if u["username"] == name)
    c.post(f"/users/{uid}/permissions", headers=H, json={"permissions": perms})
    return uid, login(name, name + "12345")
_, HQ = user("anoopold", "estimation_projects")
acc_id, HA = user("accold", "accounts_bank")
pid = next(p for p in c.get("/store/est/meta", headers=H).json()["projects"] if p["code"] == "912")["id"]
sid = c.post("/store/est/subs", headers=H, json={"project_id": pid, "name": "Old Paid Manpower", "value": 200000, "ret_pct": 5, "vat_pct": 5}).json()["id"]
pcs = []
for n, work in [(1, 20000), (2, 45000), (3, 70000)]:
    i = c.post("/store/est/subpcs", headers=HQ, json={"sub_id": sid, "inv_ref": f"OP/{n}", "inv_amount": 1000, "inv_date": f"2026-0{n + 5}-15", "received": f"2026-0{n + 5}-16"}).json()["id"]
    c.patch(f"/store/est/subpcs/{i}", headers=HQ, json={"work_cum": work})
    pcs.append(i)
step = lambda h, i, st: c.post(f"/store/est/subpcs/{i}/step", headers=h, json={"step": st})
# PC 01 entered and pushed on to Accounts the way it happened on 912 (Certified -> Prepared -> CM approved -> Verified)
for st, h in [("Certified", HQ), ("Prepared", HQ), ("CM approved", H), ("Verified", HA)]:
    step(h, pcs[0], st)
sheet = lambda: {p["id"]: p for p in next(s for s in c.get(f"/store/est/projects/{pid}/book", headers=H).json()["subs"] if s["id"] == sid)["pcs"]} \
    if c.get(f"/store/est/projects/{pid}/book", headers=H).status_code == 200 else {}
db = database.SessionLocal()
st1 = db.get(E.EstSubPC, pcs[0]).status; db.close()
ck(f"PC 01 is with Accounts (Verified) before - {st1}", st1 == "Verified", st1)
acc_bell = lambda: [x for x in E.bell_items(database.SessionLocal(), database.SessionLocal().get(M.models.User, acc_id))]

r = c.post(f"/store/est/subpcs/{pcs[0]}/oldpaid", headers=HA, json={})
ck("Accounts alone cannot mark an old PC as already paid (Estimation does it)", r.status_code == 403, r.text)
r = c.post(f"/store/est/subpcs/{pcs[2]}/oldpaid", headers=HQ, json={})
ck("the newest certificate (PC 03) cannot be marked as already paid - it goes through the approvals", r.status_code == 400 and "newest" in r.text, r.text)
r = c.post(f"/store/est/subpcs/{pcs[0]}/oldpaid", headers=HQ, json={})
ck("Estimation marks PC 01 (with Accounts) as already paid", r.status_code == 200 and r.json()["status"] == "Paid", r.text)
r = c.post(f"/store/est/subpcs/{pcs[1]}/oldpaid", headers=HQ, json={"amount": 25000, "date": "2026-07-20", "ref": "CHQ 4411"})
ck("PC 02 (not yet sent anywhere) marked already paid with its own amount, date and cheque", r.status_code == 200, r.text)
db = database.SessionLocal()
p1, p2, p3 = (db.get(E.EstSubPC, i) for i in pcs)
calc = {x["id"]: x for x in E.chain(db.query(E.EstSubPC).filter(E.EstSubPC.sub_id == sid).all(), 0, 5, 5)}
ck(f"PC 01: Paid, the payable paid ({p1.paid_amount} = {calc[pcs[0]]['payable']}), on its invoice date, 'Paid before the app'",
   p1.status == "Paid" and abs(p1.paid_amount - calc[pcs[0]]["payable"]) < 0.005 and str(p1.paid_on) == "2026-06-15" and p1.paid_ref == "Paid before the app", (p1.status, p1.paid_amount, p1.paid_on, p1.paid_ref))
ck("PC 02: Paid 25,000 on 20/07/2026, CHQ 4411", p2.status == "Paid" and p2.paid_amount == 25000 and str(p2.paid_on) == "2026-07-20" and p2.paid_ref == "CHQ 4411", (p2.status, p2.paid_amount, p2.paid_on))
ck("PC 03 untouched (still Received, unpaid)", p3.status == "Received" and not p3.paid_on, p3.status)
ck("the history says it was an old certificate, already paid", "already paid before the app" in (p1.flow_log or ""), p1.flow_log)
ck("audit log has it", db.query(M.models.AuditLog).filter(M.models.AuditLog.action == "pc_old_paid").count() == 2)
db.close()
bell = acc_bell()
ck("Accounts' bell no longer has PC 01 or 02", not any(str(pcs[0]) in str(x) or "Old Paid Manpower" in str(x) for x in bell), bell)
r = c.post(f"/store/est/subpcs/{pcs[0]}/oldpaid", headers=HQ, json={})
ck("pressing it again changes nothing", r.status_code == 200 and r.json()["status"] == "Paid", r.text)
# undo: back to where it was (PC 01 was with Accounts - Verified), not on to Accounts to pay
r = c.post(f"/store/est/subpcs/{pcs[0]}/step", headers=HQ, json={"step": "Paid", "undo": True})
db = database.SessionLocal(); p1 = db.get(E.EstSubPC, pcs[0])
ck(f"undo (by Estimation): PC 01 back to Verified, the paid figures cleared - {p1.status}", r.status_code == 200 and p1.status == "Verified" and not p1.paid_on and not p1.paid_amount, (r.text, p1.status, p1.paid_amount))
db.close()
r = c.post(f"/store/est/subpcs/{pcs[0]}/oldpaid", headers=HQ, json={})
ck("and marked already paid again", r.status_code == 200 and r.json()["status"] == "Paid", r.text)
# PC 03 still goes the normal way
for st, h in [("Certified", HQ), ("Prepared", HQ)]:
    r = step(h, pcs[2], st)
ck("PC 03 goes the normal way (Certified -> Prepared)", r.status_code == 200 and r.json()["status"] == "Prepared", r.text)
print("ALL PASS" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)

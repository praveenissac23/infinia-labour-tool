"""Send to MD rings the MD's phone straight away - not at the next two-minute round - and tapping it opens the
certificate's approval page. (The phone itself is stood in for: push.send records what would go out.)
    cd app && DATABASE_URL=sqlite:////tmp/mp.db INFINIA_NO_SCHED=1 INFINIA_PUSH_ANYTIME=1 python3 ../tests/md_push_now_test.py
"""
import os, sys, time
sys.path.insert(0, os.getcwd())
os.environ.pop("INFINIA_NO_PUSH", None)
from fastapi.testclient import TestClient
import main as M
import push
import database
sent = []
push.available = lambda: True
push.send = lambda key, pub, sub, msg, ttl=86400: (sent.append((sub.user_id, msg)), 201)[1]
push.start_loop = lambda *a, **k: None          # no two-minute round in this test: only the straight-away push
c = TestClient(M.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:300]}"))
    if not ok: fails.append(n)
login = lambda u, p: {"Authorization": "Bearer " + c.post("/auth/login", data={"username": u, "password": p}).json().get("access_token", "")}
H = login("admin", "changeme123")
def user(name, full, perms):
    r = c.post("/users", headers=H, json={"username": name, "password": name + "12345", "full_name": full, "role": "office"})
    uid = r.json()["id"] if r.status_code in (200, 201) else next(u["id"] for u in c.get("/users", headers=H).json() if u["username"] == name)
    c.post(f"/users/{uid}/permissions", headers=H, json={"permissions": perms})
    return login(name, name + "12345")
HQ = user("arathiq", "Arathi Sajeendran", "estimation_projects")
HC = user("anoopc", "Anoop S", "estimation_projects")
HA = user("shafeeqa", "Shafeeq", "accounts_bank")
c.put("/store/est/rules", headers=H, json={"pc_cm": "Anoop", "stuck_days": 2})
pid = next(p for p in c.get("/store/est/meta", headers=H).json()["projects"] if p["code"] == "909")["id"]
sid = c.post("/store/est/subs", headers=H, json={"project_id": pid, "name": "Push Joinery", "value": 500000, "adv_pct": 10, "ret_pct": 5, "vat_pct": 5}).json()["id"]
pc = c.post("/store/est/subpcs", headers=HQ, json={"sub_id": sid, "inv_ref": "PJ/1", "inv_amount": 50000, "received": "2026-10-20"}).json()["id"]
step = lambda h, body: c.post(f"/store/est/subpcs/{pc}/step", headers=h, json=body)
step(HQ, {"step": "At site"}); step(HQ, {"step": "Certified", "by": "Akhil"})
c.patch(f"/store/est/subpcs/{pc}", headers=HQ, json={"work_cum": 100000})
step(HQ, {"step": "Prepared"}); step(HC, {"step": "CM approved"})
r = step(HA, {"step": "Verified"})
ck("Accounts verifies", r.status_code == 200, r.text)

# the MD's phone is signed up for notifications; everything already on its bell counts as told
db = database.SessionLocal()
admin = db.query(M.models.User).filter(M.models.User.username == "admin").first()
db.add(push.PushSubscription(user_id=admin.id, endpoint="https://push.example/md-iphone", p256dh="x", auth="y", device="iPhone"))
db.commit()
push.push_new(database.SessionLocal, M.models, M._notes_for, seed=True, only_user=admin.id)
sent.clear()
time.sleep(1); sent.clear()

r = step(HA, {"step": "Sent to MD"})
ck("Accounts presses Send to MD", r.status_code == 200 and r.json().get("md_sent"), r.text)
t0 = time.time()
while time.time() - t0 < 8 and not any(u == admin.id for u, _ in sent):
    time.sleep(0.2)
md = [m for u, m in sent if u == admin.id]
ck(f"the MD's phone is told within seconds ({time.time() - t0:.1f}s), not at the next round", bool(md), sent)
ck("the notification is the certificate, and tapping it opens its approval page",
   md and "Push Joinery" in md[0]["title"] and md[0]["url"].startswith("/portal/approve.html?pc=") and str(pc) in md[0]["url"], md)
n_before = len(sent)
r = step(HA, {"step": "Sent to MD"})              # pressed again: nothing new, nothing pushed twice
time.sleep(2)
ck("pressing it again does not ring the phone twice", len([m for u, m in sent if u == admin.id]) == len(md), sent[n_before:])
print("ALL PASS" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)

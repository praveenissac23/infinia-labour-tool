"""Estimation: the margin (contract less subcontracts) is shown to the admin only - not in the API for anyone else.
    cp /tmp/full_base.db /tmp/em.db && cd app && DATABASE_URL=sqlite:////tmp/em.db INFINIA_NO_SCHED=1 python3 ../tests/est_margin_admin_test.py
"""
import os, sys
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main as M, models, auth
from database import SessionLocal
c = TestClient(M.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:300]}"))
    if not ok: fails.append(n)
db = SessionLocal()
u = db.query(models.User).filter_by(username="em_qs").first()
if not u:
    u = models.User(username="em_qs", full_name="Qs", role="office", hashed_password=auth.hash_password("pass12345"))
    db.add(u)
u.permissions = "settings,estimation,estimation_projects,estimation_boards"
db.commit()
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
Q = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "em_qs", "password": "pass12345"}).json()["access_token"]}
d = c.get("/store/est/dash", headers=H).json()
ck("admin: margin on the dashboard", all("margin" in r for r in d["projects"]) and d["projects"])
dq = c.get("/store/est/dash", headers=Q)
ck("QS opens the dashboard", dq.status_code == 200, dq.text[:200])
ck("QS: no margin on the dashboard", dq.status_code == 200 and not any("margin" in r for r in dq.json()["projects"]))
pid = d["projects"][0]["id"]
ck("admin: margin on the project", "margin" in c.get(f"/store/est/projects/{pid}", headers=H).json()["summary"])
pq = c.get(f"/store/est/projects/{pid}", headers=Q)
ck("QS: no margin on the project", pq.status_code == 200 and "margin" not in pq.json()["summary"], pq.text[:200])
ck("admin still sees it after a QS looked (nothing shared changed)", "margin" in c.get(f"/store/est/projects/{pid}", headers=H).json()["summary"])
print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL PASS"); sys.exit(1 if fails else 0)

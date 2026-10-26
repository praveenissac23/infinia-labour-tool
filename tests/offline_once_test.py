"""Working offline: the same save sent twice (X-Req-Id) is done once - the second gets the first answer.
    cp /tmp/full_base.db /tmp/oo.db && cd app && DATABASE_URL=sqlite:////tmp/oo.db INFINIA_NO_SCHED=1 python3 ../tests/offline_once_test.py
"""
import os, sys
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main as M
c = TestClient(M.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:300]}"))
    if not ok: fails.append(n)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
pid = next(p for p in c.get("/store/est/meta", headers=H).json()["projects"] if p["code"] == "914")["id"]
n0 = len([l for l in c.get(f"/store/est/projects/{pid}", headers=H).json()["logs"] if l["kind"] == "rfi"])
h = dict(H, **{"X-Req-Id": "test-offline-1"})
r1 = c.post("/store/est/logs", headers=h, json={"kind": "rfi", "project_id": pid, "title": "Offline RFI"})
r2 = c.post("/store/est/logs", headers=h, json={"kind": "rfi", "project_id": pid, "title": "Offline RFI"})
n1 = len([l for l in c.get(f"/store/est/projects/{pid}", headers=H).json()["logs"] if l["kind"] == "rfi"])
ck("first save done", r1.status_code == 200 and r1.json().get("id"), r1.text)
ck("the same save again: same answer, marked replayed", r2.status_code == 200 and r2.json() == r1.json() and r2.headers.get("x-replayed") == "1", [r2.text, dict(r2.headers)])
ck("saved once, not twice", n1 == n0 + 1, [n0, n1])
r3 = c.post("/store/est/logs", headers=dict(H, **{"X-Req-Id": "test-offline-2"}), json={"kind": "rfi", "project_id": pid, "title": "Another"})
ck("a different save goes through", r3.status_code == 200 and r3.json()["id"] != r1.json()["id"])
r4 = c.post("/store/est/logs", headers=H, json={"kind": "rfi", "project_id": pid, "title": "No id"})
ck("saves without an id work as before", r4.status_code == 200)
g = c.get("/store/est/meta", headers=H)
ck("reads untouched (gzip etc.)", g.status_code == 200 and "projects" in g.json())
print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL PASS"); sys.exit(1 if fails else 0)

"""Estimation: one project under several contracts with the client (shell & core, MEP, swimming pool ...).
Each contract has its own value, advance, retention, VAT, certificates, variations and bills; the project is their sum.
    cp /tmp/full_base.db /tmp/ec.db && cd app && DATABASE_URL=sqlite:////tmp/ec.db INFINIA_NO_SCHED=1 python3 ../tests/est_contracts_test.py
"""
import os, sys
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main as M
c = TestClient(M.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:400]}"))
    if not ok: fails.append(n)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
api = lambda m, u, j=None: getattr(c, m)(u, headers=H, **({"json": j} if j is not None else {}))
meta = api("get", "/store/est/meta").json()
P = next(p for p in meta["projects"] if p["code"] == "914")
pid = P["id"]
api("patch", f"/store/est/projects/{pid}", {"contract_value": 4850000, "adv_pct": 10, "ret_pct": 10, "vat_pct": 5})
b = api("get", f"/store/est/projects/{pid}").json()
ck("one agreement: no contracts list, the project is the contract", b["contracts"] == [] and b["summary"]["contract"] == 4850000, b["contracts"])
v1 = api("post", "/store/est/variations", {"project_id": pid, "title": "Extra boundary wall", "status": "Approved", "approved_amount": 62400}).json()["id"]
pc1 = api("post", "/store/est/clientpcs", {"project_id": pid, "claimed_cum": 1000000, "certified_cum": 1000000, "status": "Certified"}).json()["id"]
r = api("post", "/store/est/contracts", {"project_id": pid, "name": "MEP", "ref": "IC/914/MEP", "value": 1620000, "adv_pct": 0, "ret_pct": 5, "vat_pct": 5, "first_name": "Shell & Core"})
ck("add a second contract", r.status_code == 200, r.text)
b = api("get", f"/store/est/projects/{pid}").json()
ks = b["contracts"]; sc = next((k for k in ks if k["name"] == "Shell & Core"), None); mep = next((k for k in ks if k["name"] == "MEP"), None)
ck("the existing agreement became 'Shell & Core' with its figures (4,850,000 · adv 10 · ret 10)", sc and sc["value"] == 4850000 and sc["adv_pct"] == 10 and sc["ret_pct"] == 10, ks)
ck("project contract value = sum of the contracts (6,470,000)", b["summary"]["contract"] == 6470000, b["summary"]["contract"])
ck("the earlier variation and certificate went with Shell & Core", next(v for v in b["variations"] if v["id"] == v1)["contract_id"] == sc["id"]
   and next(x for x in b["clientpcs"] if x["id"] == pc1)["contract_id"] == sc["id"])
ck("Shell & Core: VO 62,400, certified 1,000,000 less 10% adv recovery... (net), retention 100,000", sc["approved_vo"] == 62400 and sc["retention"] == 100000 and sc["work_certified"] == 1000000, sc)
r = api("post", "/store/est/clientpcs", {"project_id": pid, "claimed_cum": 300000})
ck("with several contracts a certificate must say which one", r.status_code == 400 and "contract" in r.text.lower(), r.text)
pc2 = api("post", "/store/est/clientpcs", {"project_id": pid, "contract_id": mep["id"], "claimed_cum": 300000, "certified_cum": 300000, "status": "Certified"}).json()["id"]
b = api("get", f"/store/est/projects/{pid}").json()
mep = next(k for k in b["contracts"] if k["name"] == "MEP"); x2 = next(x for x in b["clientpcs"] if x["id"] == pc2)
ck("MEP certificate is MEP PC 01, on MEP's own 5% retention (15,000), no advance", x2["seq"] == 1 and x2["ret_cum"] == 15000 and x2["adv_rec_cum"] == 0, x2)
ck("MEP figures: certified 285,000, retention 15,000", mep["certified"] == 285000 and mep["retention"] == 15000, mep)
ck("project certified = Shell & Core + MEP", abs(b["summary"]["client_certified"] - (next(k for k in b["contracts"] if k["name"] == "Shell & Core")["certified"] + 285000)) < .01, b["summary"])
r = api("post", "/store/est/variations", {"project_id": pid, "title": "Pool lighting", "contract_id": 999999})
ck("a contract from another project is refused", r.status_code == 400, r.text)
r = api("post", "/store/est/ipa/new", {"project_id": pid, "contract_id": mep["id"]})
ck("a bill for MEP needs MEP's own bill format", r.status_code == 400 and "contract" in r.text, r.text)
r = api("delete", f"/store/est/contracts/{mep['id']}")
ck("a contract with certificates on it cannot be removed", r.status_code == 400, r.text)
api("delete", f"/store/est/clientpcs/{pc2}")
r = api("delete", f"/store/est/contracts/{mep['id']}")
b = api("get", f"/store/est/projects/{pid}").json()
ck("removed: back to one contract, the project's value is Shell & Core's again", r.status_code == 200 and len(b["contracts"]) == 1 and b["summary"]["contract"] == 4850000, [r.text, b["summary"]["contract"]])
dash = api("get", "/store/est/dash")
ck("the all-projects dashboard still opens", dash.status_code == 200, dash.text[:200])
print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL PASS"); sys.exit(1 if fails else 0)

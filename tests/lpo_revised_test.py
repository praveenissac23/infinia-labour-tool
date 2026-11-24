"""REVISED LPO (24/11/2026, purchaser): a REVISED button on the LPO form and in the register. It opens the same LPO
under the next revision number - IC/LPO/20260219 -> IC/LPO/20260219R1, then R2 - and saving it cancels the earlier
one as 'Replaced by'. A cancelled one can't be revised; revising R1 gives R2, not R1 again.
    cd app && DATABASE_URL=sqlite:////tmp/lr.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/lpo_revised_test.py
"""
import os, sys
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main, database, models
c = TestClient(main.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:400]}"))
    if not ok: fails.append(n)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
body = lambda ref, rate: {"supplier_name": "Ghantoot Building Materials", "order_date": "2026-11-24", "project_location": "913", "plot_no": "3471004",
                          "ref": ref, "job_scope": "Steel for the roof slab - a long description kept as typed",
                          "lines": [{"description": "Steel 20MM (Jindal)", "qty": 9.091, "unit": "TON", "rate": rate, "tax_pct": 5}]}
r = c.post("/store/purchase/orders", json=body("IC/LPO/20260219", 2840), headers=H)
ck("LPO IC/LPO/20260219 raised", r.status_code == 200 and r.json()["ref"] == "IC/LPO/20260219", r.text[:300])
o1 = r.json()["id"]
r = c.get(f"/store/purchase/orders/{o1}/next-revision", headers=H)
ck("REVISED on IC/LPO/20260219 -> IC/LPO/20260219R1", r.status_code == 200 and r.json()["ref"] == "IC/LPO/20260219R1" and r.json()["replaces"] == "IC/LPO/20260219", r.text)
r = c.post("/store/purchase/orders", json=body("IC/LPO/20260219R1", 2800), headers=H)
ck("the revision saves", r.status_code == 200 and r.json()["ref"] == "IC/LPO/20260219R1", r.text[:300])
o2 = r.json()["id"]
db = database.SessionLocal()
a, b = db.get(models.PurchaseOrder, o1), db.get(models.PurchaseOrder, o2)
ck("the earlier one is cancelled, replaced by R1", a.status == "cancelled" and a.superseded_by == "IC/LPO/20260219R1", (a.status, a.superseded_by))
ck("R1 carries the same plot, site, scope and the new rate", b.plot_no == "3471004" and b.project_location == "913" and b.job_scope.startswith("Steel for the roof") and b.lines[0].rate == 2800)
db.close()
r = c.get(f"/store/purchase/orders/{o2}/next-revision", headers=H)
ck("REVISED on R1 -> R2", r.json().get("ref") == "IC/LPO/20260219R2", r.text)
r = c.get(f"/store/purchase/orders/{o1}/next-revision", headers=H)
ck("the cancelled original can't be revised - points to R1", r.status_code == 400 and "IC/LPO/20260219R1" in r.json()["detail"], r.text)
r = c.get("/store/purchase/orders/999999/next-revision", headers=H)
ck("an LPO that is not there: 404", r.status_code == 404)
# a typed number of another shape
r = c.post("/store/purchase/orders", json=body("IC/LPO/9103374", 10), headers=H)
r = c.get(f"/store/purchase/orders/{r.json()['id']}/next-revision", headers=H)
ck("any LPO number takes R1 the same way", r.json().get("ref") == "IC/LPO/9103374R1", r.text)
js = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app-classic.html"), encoding="utf-8").read()
ck("the form and the register have the REVISED button", 'id="lpo-revise-btn"' in js and "lprRevise(${row.id})" in js and "async function lpoRevise()" in js)
print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED"))
sys.exit(1 if fails else 0)

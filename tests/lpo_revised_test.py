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
# the supplier's bill already checked on the first LPO (amount for 9.091 t at 2,800 + VAT)
r = c.post(f"/store/purchase/orders/{o1}/bill", json={"bill_no": "INV-5521", "bill_date": "2026-11-24", "bill_amount": 26727.54, "checked": True}, headers=H)
ck("bill checked on the first LPO", r.status_code == 200, r.text[:200])
r = c.post("/store/purchase/orders", json=body("IC/LPO/20260219R1", 2800), headers=H)
ck("the revision saves", r.status_code == 200 and r.json()["ref"] == "IC/LPO/20260219R1", r.text[:300])
o2 = r.json()["id"]
db = database.SessionLocal()
a, b = db.get(models.PurchaseOrder, o1), db.get(models.PurchaseOrder, o2)
ck("the earlier one is cancelled, replaced by R1", a.status == "cancelled" and a.superseded_by == "IC/LPO/20260219R1", (a.status, a.superseded_by))
ck("R1 carries the same plot, site, scope and the new rate", b.plot_no == "3471004" and b.project_location == "913" and b.job_scope.startswith("Steel for the roof") and b.lines[0].rate == 2800)
ck("the supplier's bill check moved to R1 (it is the same bill)", b.bill_no == "INV-5521" and b.bill_checked and not a.bill_no, (a.bill_no, b.bill_no))
# accounts: only R1 counts - site costs, register totals, the Zoho list - and the bell says so with the difference
import projexpense as PX, pozoho as PZ
from datetime import date as _d
got = [x["ref"] for x in PX._lpos(db, lambda *a: ["913"], _d(2026, 11, 1), _d(2026, 11, 30))]
ck("site costs: only R1 (the first LPO is not added on top)", "IC/LPO/20260219R1" in got and "IC/LPO/20260219" not in got, got)
rep = c.get("/store/purchase/report?group_by=supplier&measures=total&status=issued", headers=H).json()
tot = sum(float(r_.get("total") or 0) for r_ in rep.get("rows", []))
want = round(9.091 * 2800 * 1.05, 2)
ck(f"LPO register by supplier: AED {want:,.2f} - R1 only, not both", abs(tot - want) < 0.01, (tot, rep.get("rows")))
bl = [x for x in PZ.bell(db) if x["lpo_id"] == o1]
ck("accounts bell: 'replaced by R1', both totals and the difference", bl and "replaced by IC/LPO/20260219R1" in bl[0]["title"]
   and any("difference -" in x for x in bl[0]["changes"]) and any("Only IC/LPO/20260219R1 counts" in x for x in bl[0]["changes"]), bl)
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
# review 24/11/2026 --------------------------------------------------------------------------------------------
# a number that does not end in a digit can't be replaced by a revision: refused, not offered
r = c.post("/store/purchase/orders", json=body("LPO-ABC", 10), headers=H)
r = c.get(f"/store/purchase/orders/{r.json()['id']}/next-revision", headers=H)
ck("'LPO-ABC' can't take a revision - a clear message instead of a number that would leave both live", r.status_code == 400 and "does not end in a number" in r.json()["detail"], r.text)
# an old number typed with a space (before spaces were taken out) is still replaced
db = database.SessionLocal()
sp = models.PurchaseOrder(po_no=99000123, ref="IC/LPO/777 R1", order_date=main._dubai_today(), supplier_name="Old Trader", status="issued")
db.add(sp); db.commit(); spid = sp.id; db.close()
r = c.get(f"/store/purchase/orders/{spid}/next-revision", headers=H)
ck("'IC/LPO/777 R1' -> IC/LPO/777R2", r.json().get("ref") == "IC/LPO/777R2", r.text)
r = c.post("/store/purchase/orders", json=body("IC/LPO/777R2", 5), headers=H)
db = database.SessionLocal()
ck("saving R2 cancels 'IC/LPO/777 R1' (space ignored)", db.get(models.PurchaseOrder, spid).status == "cancelled", db.get(models.PurchaseOrder, spid).status)
db.close()
# the old PO still in Zoho (could not be cancelled - billed already): R1's bill tick is taken off, the bell says so
r = c.post("/store/purchase/orders", json=body("IC/LPO/20260300", 2840), headers=H); z1 = r.json()["id"]
c.post(f"/store/purchase/orders/{z1}/bill", json={"bill_no": "INV-9", "bill_amount": round(9.091 * 2840 * 1.05, 2), "checked": True}, headers=H)
db = database.SessionLocal(); zz = db.get(models.PurchaseOrder, z1); zz.zoho_status = "sent"; zz.zoho_id = "4800000000123"; db.commit(); db.close()
r = c.post("/store/purchase/orders", json=body("IC/LPO/20260300R1", 2840), headers=H); z2 = r.json()["id"]
db = database.SessionLocal()
ck("old PO still in Zoho: R1 keeps the bill number but not the tick (check it again)", db.get(models.PurchaseOrder, z2).bill_no == "INV-9" and not db.get(models.PurchaseOrder, z2).bill_checked)
bl = [x for x in PZ.bell(db) if x["lpo_id"] == z1]
ck("old PO still in Zoho: the bell warns not to bill R1 again, and doesn't claim it is out of Zoho",
   bl and any("STILL in Zoho" in x for x in bl[0]["changes"]) and not any("register totals and Zoho" in x for x in bl[0]["changes"]), bl and bl[0]["changes"])
db.close()
# the bill amount no longer agrees with the revision's total: the tick is taken off
r = c.post("/store/purchase/orders", json=body("IC/LPO/20260301", 2840), headers=H); q1 = r.json()["id"]
c.post(f"/store/purchase/orders/{q1}/bill", json={"bill_no": "INV-10", "bill_amount": round(9.091 * 2840 * 1.05, 2), "checked": True}, headers=H)
r = c.post("/store/purchase/orders", json=body("IC/LPO/20260301R1", 2700), headers=H)
db = database.SessionLocal(); q2 = db.get(models.PurchaseOrder, r.json()["id"])
ck("bill no longer agrees with R1's total: moved, but to be checked again", q2.bill_no == "INV-10" and not q2.bill_checked); db.close()
# a rate with 4 decimals (5.0389): the accounts note gives the LPO's real total, not one from a rounded rate
r = c.post("/store/purchase/orders", json=dict(body("IC/LPO/20260302", 0), lines=[{"description": "Solid block 6in", "qty": 1500, "unit": "NOS", "rate": 5.0389, "tax_pct": 5}]), headers=H)
w1 = r.json()["id"]
c.post("/store/purchase/orders", json=dict(body("IC/LPO/20260302R1", 0), lines=[{"description": "Solid block 6in", "qty": 1500, "unit": "NOS", "rate": 5.0, "tax_pct": 5}]), headers=H)
db = database.SessionLocal()
ch = [x for x in PZ.bell(db) if x["lpo_id"] == w1][0]["changes"]
ck("accounts note: 'Total was AED 7,936.27' (1,500 x 5.0389 + VAT), difference -61.27", any("Total was AED 7,936.27" in x for x in ch) and any("difference -61.27" in x for x in ch), ch)
db.close()
# LPO register (24/11/2026, purchaser): search by LPO no lists the original and its revisions; they sit together,
# newest revision first, whatever their dates; a revision carries its number for the purple REVISED tag
c.post("/store/purchase/orders", json=dict(body("IC/LPO/20260400", 10), order_date="2026-11-01"), headers=H)
c.post("/store/purchase/orders", json=dict(body("IC/LPO/20260401", 10), order_date="2026-11-02"), headers=H)
for k in range(1, 11):                                              # R1 ... R10 (R10 must come above R2, not below)
    c.post("/store/purchase/orders", json=dict(body(f"IC/LPO/20260400R{k}", 10 + k), order_date="2026-11-24"), headers=H)
rep = c.get("/store/purchase/report?group_by=order&status=all&lpo=20260400", headers=H).json()["rows"]
labs = [x["label"] for x in rep]
ck("search '20260400': the original and all 10 revisions, nothing else", labs[-1] == "IC/LPO/20260400" and len(labs) == 11 and "IC/LPO/20260401" not in labs, labs)
ck("listed R10, R9 ... R1, then the original (R10 above R2)", labs == [f"IC/LPO/20260400R{k}" for k in range(10, 0, -1)] + ["IC/LPO/20260400"], labs)
ck("rows carry revision no. and family (for the REVISED tag and purple edge)", rep[0]["revision"] == 10 and rep[-1]["revision"] == 0 and all(x.get("family") == 11 for x in rep), rep[0])
rep = c.get("/store/purchase/report?group_by=order&status=all", headers=H).json()["rows"]
labs = [x["label"] for x in rep]
i = labs.index("IC/LPO/20260400")
ck("whole register: the family together, right under IC/LPO/20260401 - not split by date", labs[i - 10:i + 1] == [f"IC/LPO/20260400R{k}" for k in range(10, 0, -1)] + ["IC/LPO/20260400"] and labs[i - 11] == "IC/LPO/20260401", labs[max(0, i - 12):i + 2])
ck("search with a space or lower case ('lpo/20260400 r1') still finds R1 and R10",
   {"IC/LPO/20260400R1", "IC/LPO/20260400R10"} <= {x["label"] for x in c.get("/store/purchase/report?group_by=order&status=all&lpo=lpo/20260400%20r1", headers=H).json()["rows"]})
import agent as AG
ck("INFI is told to leave cancelled / replaced LPOs out of spend", "skip status 'cancelled' (also revised ones)" in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app", "agent.py")).read())
js = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app-classic.html"), encoding="utf-8").read()
ck("the form and the register have the REVISED button", 'id="lpo-revise-btn"' in js and "lprRevise(${row.id})" in js and "async function lpoRevise()" in js)
ck("REVISED keeps the original LPO date (cost stays in its month; a pre-Zoho LPO stays out of Zoho)",
   "isoLocal(new Date())" not in js[js.index("async function lpoRevise()"):js.index("function closeLpoForm()")])
ck("register: LPO no box and the purple REVISED tag", 'id="lpr-lpo"' in js and "lpr-revtag" in js and "lpr-fam" in js)
ck("REVISED is hidden on a cancelled LPO", '["superseded", "cancelled"].includes(o.status)' in js)
print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED"))
sys.exit(1 if fails else 0)

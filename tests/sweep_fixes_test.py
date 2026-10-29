"""The problems the whole-app sweep found (Oct 2026), each checked so it stays fixed. Runs on a copy of the full
database (tests/seed_full.py):

    cp /tmp/full.db /tmp/sf.db && cd app && DATABASE_URL=sqlite:////tmp/sf.db INFINIA_NO_SCHED=1 python3 ../tests/sweep_fixes_test.py
"""
import io, sys
sys.path.insert(0, ".")
import openpyxl
import main, models, database
from fastapi.testclient import TestClient

c = TestClient(main.app); c.__enter__()
bad = []
def ck(name, ok, info=""):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  [{str(info)[:300]}]"))
    if not ok: bad.append(name)
def tok(u, p):
    r = c.post("/auth/login", data={"username": u, "password": p}).json()
    return {"Authorization": "Bearer " + r["access_token"]}
A, K, O, S, I = tok("admin", "changeme123"), tok("amaltest", "amal12345"), tok("chiefacc", "chief12345"), tok("siteeng", "site12345"), tok("invonly", "inv12345")

# ---- access ---------------------------------------------------------------------------------------------
mv = c.get("/store/movements", headers=A).json()
ck("a site login cannot delete a stock record", c.delete(f"/store/movements/{mv[0]['id']}", headers=S).status_code == 403)
items = {i["code"]: i for i in c.get("/store/items", headers=A).json()}
ck("a site login cannot remove a material", c.delete(f"/store/items/{items['CEM-OPC50']['id']}", headers=S).status_code == 403)
ck("an accounts-only login cannot clear a day of attendance", c.delete("/attendance/2026-10-20", headers=I).status_code == 403)
ck("an accounts-only login cannot save attendance", c.post("/attendance/save", headers=I, json={"rows": []}).status_code == 403)
ck("an accounts-only login cannot add a site", c.post("/sites", headers=I, json={"code": "999"}).status_code == 403)

# ---- store ----------------------------------------------------------------------------------------------
r = c.post("/store/requests", headers=K, json={"site": "911", "requested_by": "Gopan", "requested_on": "2026-10-20",
                                                "lines": [{"item_id": items["CEM-OPC50"]["id"], "qty_requested": 30, "unit": "bag"}]}).json()
rid, lid = r["id"], r["lines"][0]["id"]
ck("a pending request cannot be booked as delivered",
   c.post(f"/store/requests/{rid}/receive-bulk", headers=K, json={"lines": [{"line_id": lid, "qty": 5}], "supplier": "x"}).status_code == 400)
c.post(f"/store/requests/{rid}/status", headers=O, json={"status": "approved"})
po = c.post("/store/purchase/orders", headers=O, json={"supplier_name": "Al Noor Building Materials Trading LLC", "order_date": "2026-10-20",
            "request_id": rid, "request_line_ids": [lid], "lines": [{"item_id": items["CEM-OPC50"]["id"], "description": "Cement OPC 50kg",
            "qty": 30, "unit": "bag", "rate": 17.5, "tax_pct": 5}]}).json()
c.post(f"/store/purchase/orders/{po['id']}/cancel", json={'reason': 'not needed'}, headers=O)
mr = next(x for x in c.get("/store/requests", headers=A).json() if x["id"] == rid)
ck("cancelling an LPO puts its materials back to waiting for an order", mr["status"] == "approved" and not mr["lines"][0]["supplier"], mr)
ck("...and they are on the to-order list again", any(x["line_id"] == lid for x in c.get("/store/purchase/pending", headers=O).json()))
r2 = c.post("/store/requests", headers=K, json={"site": "911", "requested_by": "Gopan", "requested_on": "2026-10-20",
                                                 "lines": [{"item_id": items["CEM-OPC50"]["id"], "qty_requested": 5, "unit": "bag"}]}).json()
c.post(f"/store/request-lines/{r2['lines'][0]['id']}/decision", headers=O, json={"decision": "rejected", "reason": "not needed"})
x = c.post("/store/purchase/orders", headers=O, json={"supplier_name": "Al Noor Building Materials Trading LLC", "order_date": "2026-10-20",
           "request_line_ids": [r2["lines"][0]["id"]], "lines": [{"item_id": items["CEM-OPC50"]["id"], "description": "Cement", "qty": 5, "unit": "bag", "rate": 17.5, "tax_pct": 5}]})
ck("an LPO cannot bring a rejected material back to life", x.status_code == 400, x.text)
o = c.post("/store/purchase/orders", headers=O, json={"supplier_name": "Al Noor Building Materials Trading LLC", "order_date": "2026-10-21", "discount_pct": 10,
           "lines": [{"description": "Authority fee", "qty": 1, "unit": "LS", "rate": 100, "tax_pct": 0},
                     {"description": "Sand", "qty": 1, "unit": "m3", "rate": 90, "tax_pct": 5}]}).json()
reg = next(x for x in c.get("/store/purchase/orders", headers=O).json() if x["id"] == o["id"])
ck("LPO register: each line's own VAT after discount (90 + 81 + 4.05 = 175.05)", abs(reg["total"] - 175.05) < 0.005, reg["total"])
auto = next(x for x in c.get("/store/requests", headers=A).json() if x["id"] == o.get("request_id")) if o.get("request_id") else None
ck("the store request opened for a stock LPO is dated the LPO's day", auto is None or auto["requested_on"] == "2026-10-21", auto and auto["requested_on"])
new = c.post("/store/items", headers=A, json={"name": "Grout Sealer 1L", "unit": "can", "item_type": "consumable"}).json()
c.post("/store/movements", headers=K, json={"item_id": new["id"], "kind": "in", "qty": 10, "location": "", "reference": "DN-5501", "supplier": "Al Noor", "moved_on": "2026-10-20"})
issue = c.post("/store/movements", headers=K, json={"item_id": new["id"], "kind": "out", "qty": 5, "location": "901", "moved_on": "2026-10-01"})
ck("stock delivered on 20 Oct cannot be issued on 1 Oct", issue.status_code == 400, issue.text)
ok_issue = c.post("/store/movements", headers=K, json={"item_id": items["PPE-EAR"]["id"], "kind": "out", "qty": 1, "location": "901", "moved_on": "2026-09-05"})
ck("...but opening stock / stock put in by hand counts as held from before", ok_issue.status_code == 200, ok_issue.text)
op = c.get("/store/requests/report?kind=open", headers=A).json()
ck("the open requests report includes ordered requests", any(x["status"] == "ordered" for x in op["rows"]))
pur = c.get("/store/report?kind=purchases", headers=A).json()
ck("purchases received names opening stock as counted, not bought", any("Opening stock" in (r.get("suppliers") or "") for r in pur["rows"]))

# ---- accounts -------------------------------------------------------------------------------------------
H = A
inv = lambda n: next(x for x in c.get("/employees/accounts/invoices?kind=tax", headers=H).json()["rows"] if x["number"] == n)
x = c.post(f"/employees/accounts/invoices/{inv('IC/26/915/01')['id']}/cancel", headers=H, json={"reason": "test"})
ck("an invoice with money received on it cannot be cancelled until the receipt is changed", x.status_code == 400, x.text)
pdcs = c.post("/employees/pdc", headers=H, json={"payee": "Landlord", "cheque_no": "000901", "bank": "ADCB", "date": "2026-10-01", "amount": 1000, "status": "cleared", "repeat": 3}).json()
got = [p for p in c.get("/employees/pdc", headers=H).json()["rows"] if p["id"] in pdcs["ids"]]
ck("a cheque series marked cleared clears only the cheques already due", sorted(p["status"] for p in got) == ["cleared", "pending", "pending"], [(p["date"], p["status"]) for p in got])
aug = c.get("/store/petty-cash?book=pro&month=2026-08", headers=H).json()
ck("PRO petty cash: visa payments made in October are not taken off August", (aug.get("visa_held") or 0) == 0, aug.get("visa_held"))
vs = c.get("/store/visa/files?status=ongoing", headers=H).json()
ck("an ongoing visa's spent includes its held payments", all(r["spent"] >= r.get("held", 0) for r in vs["rows"]))
sec = [x for x in c.get("/employees/security-cheques", headers=H).json()["rows"] if x["status"] == "encashed"]
ck("an encashed security cheque cannot be collected back", not sec or c.post(f"/employees/security-cheques/{sec[0]['id']}/returned", headers=H).status_code == 400)
wb = openpyxl.Workbook(); ws = wb.active
ws.append(["Transaction Date", "Value Date", "Customer Reference", "Cheque No", "Transaction Description", "Debit Amount", "Credit Amount", "Running Balance"])
ws.append(["09/10/2026", "09/10/2026", "", "000533", "CLEARING CHQ", 5555.55, "", 94444.45])
buf = io.BytesIO(); wb.save(buf)
c.post("/store/bank", headers=H, json={"kind": "vendor", "date": "2026-10-01", "party": "Test Supplier", "mode": "Cheque", "reference": "000533", "amount": "5555.55"})
up = c.post("/store/bank/stmt/upload", headers=H, files={"file": ("adcb.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}).json()
ck("a statement's separate Cheque No column is read and matched", up.get("matched", 0) >= 1, up)

# ---- payroll --------------------------------------------------------------------------------------------
runs = c.get("/employees/payroll/runs", headers=H).json()["rows"]
sep = next(r for r in runs if r["month_year"] == "September 2026" and r["company"] == "Infinia" and r["group"] == "staff")
c.post(f"/employees/payroll/runs/{sep['id']}/reopen", headers=H)
d = c.get(f"/employees/payroll/runs/{sep['id']}", headers=H).json()
ic101 = next(l for l in d["lines"] if l["emp_no"] == "IC101")
ck("a loan taken in October is not recovered in September", (ic101["loan_deduction"] or 0) == 0, ic101["loan_deduction"])
octr = next(r for r in runs if r["month_year"] == "October 2026" and r["company"] == "Infinia" and r["group"] == "staff")
od = c.get(f"/employees/payroll/runs/{octr['id']}", headers=H).json()
held_line = od["lines"][0]
c.put(f"/employees/payroll/runs/{octr['id']}", headers=H, json={"lines": [{"id": held_line["id"], "held": True}]})
lst = next(r for r in c.get("/employees/payroll/runs", headers=H).json()["rows"] if r["id"] == octr["id"])
run = c.get(f"/employees/payroll/runs/{octr['id']}", headers=H).json()
ck("the runs list leaves held lines out of its net, like the run", abs(lst["net_pay"] - sum(l["net_pay"] for l in run["lines"] if not l["held"])) < 0.01, (lst["net_pay"]))

print("\n" + (f"{len(bad)} FAILED" if bad else "ALL PASS")); sys.exit(1 if bad else 0)

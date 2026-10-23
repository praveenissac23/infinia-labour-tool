"""Send to Zoho: a petty cash line sent as Payment Made - the cash paid to a supplier, set against his open bill in
Zoho (no new expense). The supplier and bill the chief accountant picked are kept on the line.
    cd app && rm -f /tmp/zpm.db && DATABASE_URL=sqlite:////tmp/zpm.db INFINIA_NO_SCHED=1 python3 ../tests/zoho_payment_made_test.py
"""
import os, sys
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main as M, models, zohoapi as Z
from database import SessionLocal
c = TestClient(M.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {x}"))
    if not ok: fails.append(n)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
d = M._dubai_today().isoformat()
c.post("/store/petty-cash", json={"date": d, "description": "Bus A/C service D2075", "supplier": "Swaidan Trading Co LLC", "site": "", "received": 0, "paid": 500,
                                   "book": "office", "vat": True, "trn": "104765970900003"}, headers=H)
s = SessionLocal(); x = s.query(models.PettyCash).filter(models.PettyCash.description.like("Bus A/C%")).first(); xid = x.id; s.close()
# a bare approve as Payment Made without a supplier is refused
r = c.post("/store/zoho/approve", json={"lines": [{"id": xid, "zoho_kind": "payment", "vat_claim": "claim"}]}, headers=H).json()
ck("Payment Made without a supplier is refused", r.get("refused") and "supplier" in r["refused"][0]["why"].lower(), r)
r = c.post("/store/zoho/approve", json={"lines": [{"id": xid, "zoho_kind": "payment", "vat_claim": "claim", "vendor_id": "V-SWAIDAN", "vendor": "Swaidan Trading Co LLC",
                                                   "bill_id": "B-77", "bill_no": "SWD/26/1180"}]}, headers=H).json()
ck("approved as Payment Made against the bill", r.get("approved") == 1, r)
s = SessionLocal(); x = s.get(models.PettyCash, xid)
ck("supplier and bill kept on the line", x.zoho_kind == "payment" and x.zoho_vendor_id == "V-SWAIDAN" and x.zoho_bill_id == "B-77" and x.zoho_bill_no == "SWD/26/1180", (x.zoho_kind, x.zoho_vendor_id, x.zoho_bill_id))
ck("the account reads Payment to the supplier", x.zoho_account.startswith("Payment to Swaidan"), x.zoho_account)
calls = []
real = (Z.call, Z.account_id)
def fake(db, m, path, params=None, body=None):
    calls.append((m, path, body))
    if path == "bills/B-77": return {"bill": {"bill_id": "B-77", "bill_number": "SWD/26/1180", "balance": 1200.0, "status": "open"}}
    if path == "vendorpayments": return {"vendorpayment": {"payment_id": "P-9", "payment_number": "2245"}}
    return {}
Z.call = fake; Z.account_id = lambda db, n: "ACC-" + n
try:
    zid, label = Z.push(s, x)
finally:
    Z.call, Z.account_id = real
vp = [b for m, p, b in calls if p == "vendorpayments"]
ck("Zoho gets a Payment Made (vendorpayments), not an expense", vp and not any(p == "expenses" for m, p, b in calls), [p for m, p, b in calls])
ck("...to the supplier, 500 applied to his bill, paid through the petty cash box", vp and vp[0]["vendor_id"] == "V-SWAIDAN" and vp[0]["bills"] == [{"bill_id": "B-77", "amount_applied": 500.0}]
   and vp[0]["amount"] == 500 and vp[0]["paid_through_account_id"].startswith("ACC-") and vp[0]["payment_mode"] == "Cash", vp)
ck("the line is marked Payment Made 2245 · bill", zid == "vendorpayment:P-9" and label.startswith("Payment Made 2245") and "SWD/26/1180" in label, (zid, label))
# a bill already paid in Zoho is refused, nothing sent
calls.clear()
def fake2(db, m, path, params=None, body=None):
    calls.append((m, path, body))
    if path == "bills/B-77": return {"bill": {"bill_id": "B-77", "bill_number": "SWD/26/1180", "balance": 0, "status": "paid"}}
    return {}
Z.call = fake2; Z.account_id = lambda db, n: "ACC-" + n
try:
    Z.push(s, x); ck("a bill already paid is refused", False)
except Exception as e:
    ck("a bill already paid is refused, nothing sent", "already paid" in str(e) and not any(p == "vendorpayments" for m, p, b in calls), str(e))
finally:
    Z.call, Z.account_id = real
# switched back to an expense (the line put back to waiting first): the supplier and bill go
x.zoho_status = ""; s.commit()
r = c.post("/store/zoho/approve", json={"lines": [{"id": xid, "zoho_kind": "expense", "account": "Office › Vehicle Repair and Maintenance Expenses", "vat_claim": "claim"}]}, headers=H).json()
s.refresh(x)
ck("as an expense again: no supplier payment fields kept", x.zoho_kind == "expense" and not x.zoho_vendor_id and not x.zoho_bill_id, (x.zoho_kind, x.zoho_vendor_id))
s.close()
ck("bills list answers when Zoho is not connected", c.get("/store/zoho/bills?vendor_id=V-1", headers=H).json() == {"bills": []})
print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL PASS"); sys.exit(1 if fails else 0)

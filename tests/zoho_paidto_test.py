"""Send to Zoho: "Paid to" - the chief accountant picks the Zoho supplier on a petty cash line; it is kept on the
line and the expense goes to Zoho under that supplier.
    cd app && rm -f /tmp/zpt.db && DATABASE_URL=sqlite:////tmp/zpt.db INFINIA_NO_SCHED=1 python3 ../tests/zoho_paidto_test.py
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
c.post("/store/petty-cash", json={"date": d, "description": "Cement bags", "supplier": "al hassai", "site": "", "received": 0, "paid": 525,
                                   "book": "office", "vat": True, "trn": "100234567800003"}, headers=H)
s = SessionLocal(); x = s.query(models.PettyCash).filter(models.PettyCash.description == "Cement bags").first(); xid = x.id; s.close()
q = c.get("/store/zoho/queue", headers=H).json(); row = next(r for r in q["rows"] if r["id"] == xid)
ck("queue row carries Paid to (empty yet)", row.get("vendor_id") == "" and "vendor" in row, row)
ck("vendors list answers (not connected: empty)", c.get("/store/zoho/vendors", headers=H).status_code == 200)
acc = row["account"] or "Office › Office Expenses"
r = c.post("/store/zoho/approve", json={"lines": [{"id": xid, "account": acc, "vat_claim": "claim", "vendor_id": "460000000012345", "vendor": "Al Hassai Building Materials Trading LLC"}]}, headers=H)
ck("approved", r.status_code == 200 and r.json().get("approved") == 1, r.text)
s = SessionLocal(); x = s.get(models.PettyCash, xid)
ck("Paid to kept on the petty cash line", x.zoho_vendor_id == "460000000012345" and x.zoho_vendor.startswith("Al Hassai"), (x.zoho_vendor_id, x.zoho_vendor))
# the push: Zoho calls caught
sent = []
real_call, real_acc, real_vat = Z.call, Z.account_id, Z.vat_fields
Z.call = lambda db, m, path, params=None, body=None: (sent.append((m, path, body)), {"expense": {"expense_id": "EXP1"}})[1]
Z.account_id = lambda db, n: "ACC-" + n
Z.vat_fields = lambda db, vat, trn, claim: {"tax_id": "T5"} if vat else {}
try:
    Z.push(s, x)
finally:
    Z.call, Z.account_id, Z.vat_fields = real_call, real_acc, real_vat
exp = [b for m, p, b in sent if p == "expenses"]
ck("the expense goes to Zoho under the supplier picked", exp and exp[0].get("vendor_id") == "460000000012345", exp)
ck("...and is not put on 'add the supplier in Zoho'", (x.zoho_todo or "") == "", x.zoho_todo)
s.close()
print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL PASS"); sys.exit(1 if fails else 0)

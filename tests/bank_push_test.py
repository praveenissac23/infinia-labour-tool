"""Bank: each kind of ADCB line becomes the right Zoho entry (stand-in Zoho)."""
import os, sys, tempfile, json
from datetime import date
db = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{db}"
os.environ["INFINIA_CRED_KEY_FILE"] = tempfile.mktemp(suffix=".key")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as M, models, zohoapi as Z, bank, credentials
from database import SessionLocal, engine
from fastapi import HTTPException
models.Base.metadata.create_all(bind=engine); M._add_missing_columns()
s = SessionLocal()
fails = 0
def ok(c, m):
    global fails
    print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1
ACC = {"ADCB": "B", "Company Petty Cash": "C", "Bank Fees and Charges": "BF", "Authority Payment": "AP"}
POSTED = []
def fake(db_, method, path, params=None, body=None):
    if path == "chartofaccounts":
        return {"chartofaccounts": [{"account_name": k, "account_id": v} for k, v in ACC.items()], "page_context": {}}
    if path == "projects":
        return {"projects": [{"project_code": "918", "project_id": "P918", "customer_id": "C918"}]}
    if path == "settings/taxes":
        return {"taxes": []}
    if path == "contacts":
        names = {"vendor": ["Al Raida Electromechanical Services", "Al Raida Trading"], "customer": ["Emkaan Design LLC"]}[params["contact_type"]]
        return {"contacts": [{"contact_id": "ID-" + n, "contact_name": n} for n in names if params["contact_name_contains"].lower() in n.lower()]}
    if method == "POST":
        POSTED.append((path, body))
        return {"vendorpayment": {"payment_id": "VP1", "payment_number": "2180"}, "payment": {"payment_id": "CP1", "payment_number": "99"},
                "banktransaction": {"transaction_id": "T1"}, "expense": {"expense_id": "E1"}}
    return {}
Z.call = fake
M.put_setting(s, "zoho_refresh", credentials.lock("rt")); s.commit()
def add(**k):
    d = bank._clean(k); x = models.BankEntry(**d); s.add(x); s.commit(); return x
try:
    bank._clean({"kind": "vendor", "date": "2026-10-13", "amount": 10, "party": "X", "mode": "Cheque"})
    ok(False, "cheque without number refused")
except HTTPException:
    ok(True, "cheque without number refused")
try:
    bank._clean({"kind": "vendor", "date": "2026-10-13", "amount": 100, "party": "X", "docs": [{"id": "b1", "amount": 150}]})
    ok(False, "bills more than the amount refused")
except HTTPException:
    ok(True, "bills more than the amount refused")
v = add(kind="vendor", date="2026-10-10", party="Al Raida Electromechanical Services", amount=83535.22, reference="PHUB732241116",
        notes="908PC08", docs=[{"id": "BILL1", "number": "908PC08", "amount": 83535.22}])
c = add(kind="customer", date="2026-10-12", party="Emkaan Design LLC", amount=250000, reference="PHUB732906914",
        docs=[{"id": "INV7", "number": "IC/26/915/IPA07", "amount": 250000}])
q = add(kind="vendor", date="2026-10-19", party="Al Raida", amount=48596.1, mode="Cheque", reference="000156")
e = add(kind="expense", date="2026-10-09", party="", amount=3150, reference="PHUB731759745", account="01. Preliminaries Including Mobilization › Authority Payments", site="918")
g = add(kind="charge", date="2026-10-06", amount=26.25, reference="TT fee")
t = add(kind="transfer", date="2026-10-10", amount=15000, account="Company Petty Cash", reference="PHUB732297071")
sent, failed = bank._send(s, [v, c, q, e, g, t], M.models.User(id=1))
ok(sent == 5 and len(failed) == 1 and failed[0]["id"] == q.id and "not one supplier" in failed[0]["why"], f"5 sent; 'Al Raida' matches two suppliers so it is refused, not guessed ({failed})")
P = {b.get("reference_number"): (p, b) for p, b in POSTED}
pv = P["PHUB732241116"]
ok(pv[0] == "vendorpayments" and pv[1]["vendor_id"] == "ID-Al Raida Electromechanical Services" and pv[1]["paid_through_account_id"] == "B"
   and pv[1]["bills"] == [{"bill_id": "BILL1", "amount_applied": 83535.22}] and pv[1]["payment_mode"] == "Bank Transfer", "supplier paid against his bill, from ADCB")
pc = P["PHUB732906914"]
ok(pc[0] == "customerpayments" and pc[1]["account_id"] == "B" and pc[1]["invoices"][0]["invoice_id"] == "INV7", "client payment against the invoice, into ADCB")
pe = P["PHUB731759745"]
ok(pe[0] == "expenses" and pe[1]["account_id"] == "AP" and pe[1]["project_id"] == "P918", "direct expense with its project")
ok(P["TT fee"][1]["account_id"] == "BF", "bank charge to Bank Fees and Charges")
ok(P["PHUB732297071"][0] == "banktransactions" and P["PHUB732297071"][1]["to_account_id"] == "C", "transfer ADCB -> Company Petty Cash")
s.refresh(v); s.refresh(q)
ok(v.zoho_status == "sent" and v.zoho_ref == "Payment Made 2180", "sent line shows its Zoho payment number")
ok(q.zoho_status == "" and q.zoho_err, "refused line waits with Zoho's reason")
print("fails=", fails)

"""Tax invoice Release to Zoho: right fields, never twice, locked after."""
import os, sys, tempfile, json
from datetime import date
db = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{db}"
os.environ["INFINIA_CRED_KEY_FILE"] = tempfile.mktemp(suffix=".key")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as M, models, zohoapi as Z, invzoho, accounts as A, credentials
from database import SessionLocal, engine
from fastapi import HTTPException
models.Base.metadata.create_all(bind=engine); M._add_missing_columns()
s = SessionLocal()
fails = 0
def ok(c, m):
    global fails
    print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1
ca = models.User(username="ca", full_name="CA", hashed_password="x", role="office", permissions="accounts_invoices,accounts_zoho")
st = models.User(username="st", full_name="ST", hashed_password="x", role="office", permissions="accounts_invoices")
s.add_all([ca, st]); s.commit()
inv = A.Invoice(kind="tax", number="IC/26/913/IPA10", inv_date=date(2026, 10, 12), client="FARIDA AKBARALI AKBARALI GULAM ABBAS",
                project_no="913", project="Villa", lines=json.dumps([{"description": "IPA 10", "amount": 900000, "vat": 5},
                                                                       {"description": "Retention release", "amount": 10000, "vat": 0}]),
                subtotal=910000, vat=45000, total=955000)
s.add(inv); s.commit()
POSTED, EXIST = [], set()
def fake(db_, method, path, params=None, body=None):
    if path == "invoices" and method == "GET":
        return {"invoices": [{"invoice_id": "OLD", "invoice_number": n} for n in EXIST if n == params.get("invoice_number")]}
    if path == "contacts":
        return {"contacts": [{"contact_id": "CUS913", "contact_name": "FARIDA AKBARALI AKBARALI GULAM ABBAS"}]}
    if path == "chartofaccounts":
        return {"chartofaccounts": [{"account_name": "Progressive Payments", "account_id": "INC1"}], "page_context": {}}
    if path == "settings/taxes":
        return {"taxes": [{"tax_name": "Standard Rate", "tax_percentage": 5, "tax_id": "V5"}, {"tax_name": "Zero Rate", "tax_percentage": 0, "tax_id": "V0"}]}
    if path == "projects":
        return {"projects": [{"project_code": "913", "project_id": "P913", "customer_id": "CUS913"}]}
    if method == "POST":
        POSTED.append((path, params, body)); return {"invoice": {"invoice_id": "NEW1"}}
    return {}
Z.call = fake
try:
    invzoho._user(st); ok(False, "staff without the right refused")
except HTTPException:
    ok(True, "only admin / chief accountant may release")
try:
    invzoho.release(inv.id, {}, db=s, user=ca); ok(False, "not connected refused")
except HTTPException as e:
    ok("not connected" in e.detail, "refused while Zoho is not connected")
M.put_setting(s, "zoho_refresh", credentials.lock("rt")); s.commit()
r = invzoho.release(inv.id, {"account": "Progressive Payments"}, db=s, user=ca)
s.refresh(inv)
p, params, b = POSTED[0]
ok(p == "invoices" and params == {"ignore_auto_number_generation": "true"} and b["invoice_number"] == "IC/26/913/IPA10", "made in Zoho with the portal's own number")
ok(b["customer_id"] == "CUS913" and b["project_id"] == "P913" and b["date"] == "2026-10-12", "client, project and invoice date")
ok([(i["rate"], i["tax_id"], i["account_id"]) for i in b["line_items"]] == [(900000, "V5", "INC1"), (10000, "V0", "INC1")], "lines at net with 5% / zero-rated VAT and the income account")
ok(inv.zoho_status == "sent" and inv.zoho_id == "invoice:NEW1", "invoice marked In Zoho")
try:
    invzoho.release(inv.id, {}, db=s, user=ca); ok(False, "twice refused")
except HTTPException as e:
    ok("already" in e.detail and len(POSTED) == 1, "a second release is refused - never twice")
try:
    A.edit_invoice(inv.id, {}, db=s, user=ca); ok(False, "edit refused")
except HTTPException as e:
    ok("released to Zoho" in e.detail, "a released invoice cannot be edited in the portal")
A.cancel_invoice(inv.id, {"reason": "wrong amount"}, db=s, user=ca); s.refresh(inv)
ok(inv.zoho_err.startswith("Cancelled here"), "cancelling a released invoice flags it to be voided in Zoho")
inv2 = A.Invoice(kind="tax", number="IC/26/913/IPA11", inv_date=date(2026, 10, 13), client="FARIDA AKBARALI AKBARALI GULAM ABBAS",
                 lines=json.dumps([{"description": "x", "amount": 1, "vat": 5}]), subtotal=1, vat=0.05, total=1.05)
s.add(inv2); s.commit(); EXIST.add("IC/26/913/IPA11")
r = invzoho.release(inv2.id, {}, db=s, user=ca); s.refresh(inv2)
ok(r["label"] == "Found in Zoho" and inv2.zoho_id == "invoice:OLD" and len(POSTED) == 1, "an invoice already typed in Zoho under that number is linked, not made again")
inv3 = A.Invoice(kind="tax", number="IC/26/999/01", inv_date=date(2026, 10, 13), client="Unknown Client", lines=json.dumps([{"description": "x", "amount": 1, "vat": 5}]))
s.add(inv3); s.commit()
try:
    invzoho.release(inv3.id, {}, db=s, user=ca); ok(False, "unknown client refused")
except HTTPException as e:
    s.refresh(inv3)
    ok("exact name" in e.detail and inv3.zoho_status == "" and inv3.zoho_err, "a client not in Zoho under that exact name is refused, kept Held with the reason")
print("fails=", fails)

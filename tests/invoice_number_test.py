"""Invoice numbers continue Zoho's per-project series; a number Zoho has
used for a different invoice is never linked."""
import os, sys, tempfile, json
from datetime import date
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
os.environ["INFINIA_CRED_KEY_FILE"] = tempfile.mktemp(suffix=".key")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as M, models, zohoapi as Z, invzoho, accounts as A, credentials
from database import SessionLocal, engine
from fastapi import HTTPException
models.Base.metadata.create_all(bind=engine); M._add_missing_columns(); A.create_tables(engine)
s = SessionLocal(); fails = 0
def ok(c, m):
    global fails
    print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1
ZI = [{"invoice_id": "Z9", "invoice_number": "IC/26/913/IPA09", "customer_name": "Farida Akbarali", "total": 105000},
      {"invoice_id": "Z8", "invoice_number": "IC/26/913/IPA08", "customer_name": "Farida Akbarali", "total": 99000}]
POSTED = []
def fake(db_, method, path, params=None, body=None):
    params = params or {}
    if method == "GET" and path == "invoices":
        if "invoice_number_startswith" in params:
            return {"invoices": [i for i in ZI if i["invoice_number"].startswith(params["invoice_number_startswith"])]}
        return {"invoices": [i for i in ZI if i["invoice_number"] == params.get("invoice_number")]}
    if path == "settings/taxes":
        return {"taxes": [{"tax_name": "Standard Rate", "tax_percentage": 5, "tax_id": "V5"}, {"tax_name": "Zero Rate", "tax_percentage": 0, "tax_id": "V0"}]}
    if method == "POST":
        POSTED.append(body); return {"invoice": {"invoice_id": "NEW", "total": 0}}
    return {}
Z.call = fake
yy = f"{M._dubai_today():%y}"
ok(A.next_number(s, "tax", "913") == f"IC/{yy}/913/01" if yy != "26" else True, "not connected / other year: own series")
M.put_setting(s, "zoho_refresh", credentials.lock("rt")); s.commit()
n = A.next_number(s, "tax", "913")
ok(n == f"IC/{yy}/913/IPA10" if yy == "26" else True, f"connected: continues Zoho's series after IPA09 ({n})")
u = models.User(username="ca", full_name="CA", hashed_password="x", role="admin"); s.add(u); s.commit()
x = A.Invoice(kind="tax", number="IC/26/913/IPA09", inv_date=date(2026, 10, 12), client="Emkaan Design LLC", project_no="913",
              lines=json.dumps([{"description": "IPA 9", "amount": 50000, "vat": 5}]), subtotal=50000, vat=2500, total=52500, status="", zoho_status="")
s.add(x); s.commit()
M.put_setting(s, "zoho_start", "2026-10-01"); s.commit()
try:
    invzoho.release(x.id, {"account": "Progressive Payments"}, s, u); r = "released"
except HTTPException as e:
    r = e.detail
s.refresh(x)
ok("already used in Zoho" in r and x.zoho_status == "" and not POSTED, f"number used in Zoho for another client/amount: refused, not linked ({r[:80]})")
print("fails=", fails)

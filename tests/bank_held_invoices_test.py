"""A client's receipt: tax invoices made here but not released to Zoho show
in the open-invoices list as held, next to Zoho's unpaid ones."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/../app")
from datetime import date
import main, models, bank, zohoapi
from accounts import Invoice
from database import SessionLocal
bad = 0
def ck(n, ok, info=""):
    global bad; bad += 0 if ok else 1; print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  {info!r}"))
db = SessionLocal()
db.query(Invoice).delete(); db.commit()
db.add_all([Invoice(kind="tax", number="IC/26/02-10", inv_date=date(2026, 10, 12), client="Mr. Jamal Khan", total=242818.8, status="issued"),
            Invoice(kind="tax", number="IC/26/906/01-10", inv_date=date(2026, 10, 12), client="Mr. Jamal KHAN", total=83244.65, status="issued"),
            Invoice(kind="tax", number="IC/26/02-11", inv_date=date(2026, 10, 15), client="Mr. Jamal Khan", total=200000, status="issued", zoho_status="sent", zoho_id="invoice:1"),
            Invoice(kind="proforma", number="PI/26/01", inv_date=date(2026, 10, 17), client="Mr. Jamal Khan", total=1000, status="issued"),
            Invoice(kind="tax", number="IC/26/99", inv_date=date(2026, 10, 1), client="Mr. Jamal Khan", total=5, status="cancelled"),
            Invoice(kind="tax", number="IC/26/77", inv_date=date(2026, 10, 1), client="Someone Else", total=9, status="issued")])
db.commit()
def fake_call(db_, method, path, params=None, body=None, **k):
    if path == "contacts/C1": return {"contact": {"contact_id": "C1", "contact_name": "Mr. Jamal Khan"}}
    if path == "invoices": return {"invoices": [{"invoice_id": "Z9", "invoice_number": "IC/26/02-11", "date": "2026-10-15", "balance": 50000, "total": 200000}]}
    return {}
zohoapi.call = fake_call; zohoapi.connected = lambda d: True
d = bank.open_docs("C1", "customer", db, None)["docs"]
ck("Zoho's unpaid invoice first", d[0]["id"] == "Z9" and not d[0].get("held"), d[0])
held = [x for x in d if x.get("held")]
ck("the two held tax invoices follow (name matched ignoring case)", [x["number"] for x in held] == ["IC/26/02-10", "IC/26/906/01-10"], held)
ck("held ones carry the portal id and no Zoho id", all(x["portal_id"] and x["id"] == "" for x in held))
ck("proforma, cancelled, other client, already-released are left out", len(d) == 3, [x["number"] for x in d])
ck("balance = total for a held invoice", held[0]["balance"] == 242818.8)
print("ALL PASS" if not bad else f"{bad} FAILURE(S)"); sys.exit(1 if bad else 0)

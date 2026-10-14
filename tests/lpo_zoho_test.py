"""LPOs into Zoho as purchase orders: portal number, linked vendor, lines
with VAT and discount, once only; changes and cancellations flagged."""
import os, sys, tempfile
from datetime import date
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
os.environ["INFINIA_CRED_KEY_FILE"] = tempfile.mktemp(suffix=".key")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as M, models, zohoapi as Z, pozoho, credentials
from database import SessionLocal, engine
models.Base.metadata.create_all(bind=engine); M._add_missing_columns()
s = SessionLocal(); fails = 0
def ok(c, m):
    global fails
    print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1
POSTED, EXIST = [], []
def fake(db_, method, path, params=None, body=None):
    if path == "settings/taxes":
        return {"taxes": [{"tax_name": "Standard Rate", "tax_percentage": 5, "tax_id": "V5"}, {"tax_name": "Zero Rate", "tax_percentage": 0, "tax_id": "V0"}]}
    if method == "GET" and path == "purchaseorders":
        return {"purchaseorders": [e for e in EXIST if e["purchaseorder_number"] == params.get("purchaseorder_number")]}
    if method == "POST" and path == "purchaseorders":
        POSTED.append((params, body)); return {"purchaseorder": {"purchaseorder_id": f"PO{len(POSTED)}"}}
    return {}
Z.call = fake
M.put_setting(s, "zoho_refresh", credentials.lock("rt")); M.put_setting(s, "zoho_start", "2026-10-01"); s.commit()
u = models.User(username="ca", full_name="CA", hashed_password="x", role="admin"); s.add(u)
sup = models.Supplier(name="Dani Trading LLC", name_key=M._supplier_key("Dani Trading LLC"), zoho_id="V-DANI"); s.add(sup)
sup2 = models.Supplier(name="New Shop", name_key=M._supplier_key("New Shop"), zoho_id=""); s.add(sup2)
mr = models.MaterialRequest(ref="MR-0101", site="918", requested_on=date(2026, 10, 5)); s.add(mr); s.commit()
def po(no, supplier, d=date(2026, 10, 10), **k):
    o = models.PurchaseOrder(po_no=no, ref=f"IC/LPO/{no}", order_date=d, supplier_id=supplier.id, supplier_name=supplier.name,
                             request_id=mr.id, supplier_ref="Q-55", discount_pct=k.pop("disc", 0), status="issued", zoho_status="")
    s.add(o); s.flush()
    for desc, q, rate, tax in k.pop("lines"):
        s.add(models.PurchaseOrderLine(order_id=o.id, description=desc, qty=q, unit="bag", rate=rate, tax_pct=tax))
    s.commit(); return o
a = po(20260120, sup, lines=[("Cement OPC", 50, 16.5, 5), ("Sand", 2, 300, 0)], disc=2)
b = po(20260121, sup2, lines=[("Paint", 4, 90, 5)])
old = po(20260099, sup, d=date(2026, 9, 25), lines=[("Old", 1, 10, 5)])
rows = pozoho.pos(s, u)["rows"]
ok(sorted(r["ref"] for r in rows) == ["IC/LPO/20260120", "IC/LPO/20260121"], "LPOs from 1 Oct waiting; September not offered")
ok(next(r for r in rows if r["ref"].endswith("121"))["linked"] is False, "supplier not linked shown")
r = pozoho.send({}, s, u)
ok(r["sent"] == 1 and r["failed"][0]["ref"] == "IC/LPO/20260121" and "Link" in r["failed"][0]["why"], "unlinked supplier refused - a PO needs its vendor")
params, body = POSTED[0]
ok(params.get("ignore_auto_number_generation") == "true" and body["purchaseorder_number"] == "IC/LPO/20260120" and body["vendor_id"] == "V-DANI",
   "sent with the portal's LPO number and the linked vendor")
ok([(l["description"], l["quantity"], l["rate"], l["tax_id"]) for l in body["line_items"]] == [("Cement OPC", 50, 16.5, "V5"), ("Sand", 2, 300, "V0")],
   "lines with qty, rate and the right VAT (5% / zero)")
ok(body["discount"] == "2.0%" and body["is_discount_before_tax"] and "918" in body["reference_number"], "discount and project 918 carried")
s.refresh(a)
ok(a.zoho_status == "sent" and a.zoho_id == "purchaseorder:PO1", "marked sent with the Zoho PO")
ok(pozoho.send({}, s, u)["sent"] == 0 and len(POSTED) == 1, "pressing Send again sends nothing twice")
# already in Zoho under the same number (typed by hand): linked, not made again
sup2.zoho_id = "V-NEW"; s.commit()
EXIST.append({"purchaseorder_id": "POX", "purchaseorder_number": "IC/LPO/20260121"})
pozoho.send({}, s, u); s.refresh(b)
ok(b.zoho_status == "sent" and b.zoho_id == "purchaseorder:POX" and len(POSTED) == 1, "same number already in Zoho: linked, not created twice")
# changed after Zoho -> flagged; Done clears
from types import SimpleNamespace
a.zoho_status = "sent"; s.commit()
import schemas
pl = schemas.PurchaseOrderIn(supplier_name="Dani Trading LLC", order_date="2026-10-10",
                             lines=[{"description": "Cement OPC", "qty": 60, "unit": "bag", "rate": 16.5, "tax_pct": 5}])
try:
    M.update_purchase_order(a.id, pl, s, u)
except Exception as e:
    print("note: edit call", type(e).__name__, str(e)[:120])
s.refresh(a)
ok(a.zoho_status == "changed" and "change the PO in Zoho" in a.zoho_err, "LPO edited after Zoho: flagged to change in Zoho")
ok(any(r["id"] == a.id for r in pozoho.pos(s, u)["rows"]), "flag shown on Send to Zoho")
pozoho.corrected({"id": a.id}, s, u); s.refresh(a)
ok(a.zoho_status == "sent" and not a.zoho_err, "Done in Zoho clears it - never sent again")
M.cancel_purchase_order(b.id, s, u); s.refresh(b)
ok("cancel the PO in Zoho" in b.zoho_err, "cancelled after Zoho: flagged to cancel there")
print("fails=", fails)

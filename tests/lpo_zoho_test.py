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
    if method == "GET" and path == "chartofaccounts":
        return {"chartofaccounts": [{"account_name": "Concrete Materials", "account_id": "ACC-CON", "account_type": "cost_of_goods_sold"},
                                    {"account_name": "Administration Fee", "account_id": "ACC-ADM", "account_type": "expense"}],
                "page_context": {"has_more_page": False}}
    if path == "settings/taxes":
        return {"taxes": [{"tax_name": "Standard Rate", "tax_percentage": 5, "tax_id": "V5"}, {"tax_name": "Zero Rate", "tax_percentage": 0, "tax_id": "V0"}]}
    if method == "GET" and path == "purchaseorders":
        return {"purchaseorders": [e for e in EXIST if e["purchaseorder_number"] == params.get("purchaseorder_number")]}
    if method == "POST" and path == "purchaseorders":
        POSTED.append((params, body)); return {"purchaseorder": {"purchaseorder_id": f"PO{len(POSTED)}"}}
    if method in ("PUT", "POST") and path.startswith("purchaseorders/"):
        if REFUSE:
            raise Z.ZohoError(400, REFUSE)
        CHANGED.append((method, path, body)); return {"purchaseorder": {}}
    return {}
REFUSE, CHANGED = "", []
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
r0 = pozoho.send({"ids": [a.id]}, s, u)
ok(r0["sent"] == 0 and "account" in r0["failed"][0]["why"].lower(), "no Zoho account picked: refused before anything is sent")
pozoho.set_account(a.id, {"account": "Concrete Materials"}, s, u)
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
ok(all(l["account_id"] == "ACC-CON" for l in body["line_items"]), "each line carries the picked account (Zoho refuses 'non-purchase item' without)")
ok(body.get("discount_account_id") == "ACC-ADM", "discount booked to the account his own POs use")
ok(body["discount"] == "2.0%" and body["is_discount_before_tax"] and "918" in body["reference_number"], "discount and project 918 carried")
# A discount worked back from a round total (IC/LPO/20260131 live: 7.5811%) - Zoho keeps a % to 2 places
# ("7.58%" made its PO 66,701.12 against the LPO's 66,700.34), so it goes as the amount the portal takes off.
odd = po(20260190, sup, lines=[("Block 20cm", 2, 1762, 5)], disc=0.0053)
odd.zoho_account = "Concrete Materials"; s.commit()
body2 = pozoho._body(s, odd)
gross = 2 * 1762
ok(body2["discount"] == f"{round(gross * 0.0053 / 100, 2):.2f}" == "0.19" and body2["is_discount_before_tax"],
   f"discount 0.0053% sent as AED 0.19 off (not '0.01%', which made Zoho's PO 3,699.83 vs 3,700.00): {body2['discount']}")
net = gross - 0.19
ok(round(net + round(net * 0.05, 2), 2) == pozoho._total(odd) == 3700.0, "Zoho's total from that amount = the LPO total 3,700.00")
s.delete(odd); s.query(models.PurchaseOrderLine).filter(models.PurchaseOrderLine.order_id == odd.id).delete(); s.commit()
s.refresh(a)
ok(a.zoho_status == "sent" and a.zoho_id == "purchaseorder:PO1", "marked sent with the Zoho PO")
ok(pozoho.send({}, s, u)["sent"] == 0 and len(POSTED) == 1, "pressing Send again sends nothing twice")
# already in Zoho under the same number (typed by hand): linked, not made again
sup2.zoho_id = "V-NEW"; s.commit()
pozoho.set_account(b.id, {"account": "Concrete Materials"}, s, u)
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
ok(a.zoho_status == "sent" and not a.zoho_err and CHANGED and CHANGED[-1][:2] == ("PUT", "purchaseorders/PO1") and CHANGED[-1][2]["line_items"][0]["quantity"] == 60,
   "LPO edited after Zoho: the PO in Zoho updated automatically (qty 60)")
nt = pozoho.note_of(a)
ok({"Line 1 Cement OPC: qty 50 bag -> 60 bag", "Removed: Sand - 2 bag @ 300.00", "Discount: 2% -> 0%", "Total incl. VAT: AED 1,436.92 -> AED 1,039.50"} <= set(nt["items"][-1]["changes"]) and "Updated in Zoho automatically" in nt["items"][-1]["zoho"],
   "accounts told exactly what changed, and that Zoho was updated")
ok(any(n["id"].startswith(f"lpochg-{a.id}-") and "edited" in n["title"] for n in pozoho.bell(s)), "a notice on the accounts bell")
row = next(r for r in pozoho.pos(s, u)["rows"] if r["id"] == a.id)
ok(row["note"] and row["status"] == "sent", "shown on Send to Zoho with the changes")
pozoho.note_seen(a.id, s, u); s.refresh(a)
ok(not pozoho.bell(s) and not any(r["id"] == a.id for r in pozoho.pos(s, u)["rows"]), "Seen: off the bell and the list")
# Zoho refuses the update (e.g. already billed): flagged for accounts to change by hand
REFUSE = "This purchase order has been billed"
pl2 = schemas.PurchaseOrderIn(supplier_name="Dani Trading LLC", order_date="2026-10-10",
                              lines=[{"description": "Cement OPC", "qty": 55, "unit": "bag", "rate": 17, "tax_pct": 5}])
M.update_purchase_order(a.id, pl2, s, u); s.refresh(a)
ok(a.zoho_status == "changed" and "change the PO in Zoho" in a.zoho_err and "billed" in a.zoho_err, "Zoho refuses: flagged to change in Zoho, with Zoho's reason")
nt = pozoho.note_of(a)
ok("by hand" in nt["items"][-1]["zoho"] and "Line 1 Cement OPC: qty 60 bag -> 55 bag, rate 16.50 -> 17.00" in nt["items"][-1]["changes"], "accounts told what to change by hand")
ok(any(r["id"] == a.id for r in pozoho.pos(s, u)["rows"]), "flag shown on Send to Zoho")
pozoho.corrected({"id": a.id}, s, u); s.refresh(a)
ok(a.zoho_status == "sent" and not a.zoho_err and pozoho.note_of(a)["seen"], "Done in Zoho clears it - never sent again")
# saving with nothing changed tells nobody
n0 = len(CHANGED); REFUSE = ""
M.update_purchase_order(a.id, pl2, s, u); s.refresh(a)
ok(len(CHANGED) == n0 and pozoho.note_of(a)["seen"], "saved with no change: Zoho and accounts left alone")
# cancel
try:
    M.cancel_purchase_order(b.id, {}, s, u); ok(False, "a reason is required")
except Exception as e:
    ok("why" in str(getattr(e, "detail", e)).lower(), "a reason is required to cancel")
M.cancel_purchase_order(b.id, {"reason": "Site says not needed"}, s, u); s.refresh(b)
ok(b.status == "cancelled" and b.cancel_reason == "Site says not needed" and CHANGED[-1][:2] == ("POST", "purchaseorders/POX/status/cancelled"), "cancelled: marked cancelled in Zoho automatically")
nt = pozoho.note_of(b)
ok(nt["items"][-1]["kind"] == "cancel" and "Cancelled - Site says not needed" in nt["items"][-1]["changes"], "accounts told it was cancelled and why")
c = po(20260122, sup, lines=[("Tiles", 10, 40, 5)]); c.zoho_status, c.zoho_id = "sent", "purchaseorder:POC"; s.commit()
REFUSE = "Draft purchase orders cannot be cancelled"
M.cancel_purchase_order(c.id, {"reason": "Duplicate LPO"}, s, u); s.refresh(c)
ok("cancel the PO in Zoho" in c.zoho_err, "Zoho refuses the cancel: flagged to cancel there by hand")
print("fails=", fails)

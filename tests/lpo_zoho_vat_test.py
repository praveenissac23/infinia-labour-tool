"""LPO -> Zoho VAT treatment: a 0% LPO to a vendor Zoho holds as not VAT registered goes with no tax on the
lines (Zoho refused Zero Rate there - IC/LPO/20260157, Al Maharah Global Trading FZE LLC); 5% to such a
vendor goes as VAT registered with the TRN; registered vendors go exactly as before (5% / Zero Rate)."""
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
POSTED = []
TREAT = {"V-MAH": "vat_not_registered", "V-GEM": "vat_registered", "V-DZ": "dz_vat_registered"}
def fake(db_, method, path, params=None, body=None):
    if method == "GET" and path == "chartofaccounts":
        return {"chartofaccounts": [{"account_name": "Materials for Electrical Work", "account_id": "ACC-EL", "account_type": "cost_of_goods_sold"}],
                "page_context": {"has_more_page": False}}
    if path == "settings/taxes":
        return {"taxes": [{"tax_name": "Standard Rate", "tax_percentage": 5, "tax_id": "V5"}, {"tax_name": "Zero Rate", "tax_percentage": 0, "tax_id": "V0"}]}
    if method == "GET" and path.startswith("contacts/"):
        return {"contact": {"contact_id": path.split("/")[1], "tax_treatment": TREAT.get(path.split("/")[1], "")}}
    if method == "GET" and path == "purchaseorders":
        return {"purchaseorders": []}
    if method == "POST" and path == "purchaseorders":
        # what Zoho itself does: no VAT rate at all on a not-registered PO
        tr = body.get("tax_treatment") or TREAT.get(body["vendor_id"], "")
        if tr in pozoho.NOT_REGISTERED and any(l.get("tax_id") for l in body["line_items"]):
            raise Z.ZohoError(400, "VAT or Exemption cannot be applied for this VAT Treatment.")
        if tr == "vat_registered" and TREAT.get(body["vendor_id"]) in pozoho.NOT_REGISTERED and not body.get("tax_reg_no"):
            raise Z.ZohoError(400, "Enter the TRN")
        POSTED.append(body); return {"purchaseorder": {"purchaseorder_id": f"PO{len(POSTED)}"}}
    return {}
Z.call = fake
M.put_setting(s, "zoho_refresh", credentials.lock("rt")); M.put_setting(s, "zoho_start", "2026-10-01"); s.commit()
u = models.User(username="ca", full_name="CA", hashed_password="x", role="admin"); s.add(u)
def sup(name, zid, trn=""):
    x = models.Supplier(name=name, name_key=M._supplier_key(name), zoho_id=zid, trn=trn); s.add(x); s.commit(); return x
mah = sup("Al Maharah Global Trading FZE LLC", "V-MAH", "262661260888")          # 12 digits, as in the portal
gem = sup("Gemini Building Materials LLC", "V-GEM", "100208907400003")
dz = sup("Free Zone Supplies FZE", "V-DZ", "100111222300003")
def po(no, supplier, lines):
    o = models.PurchaseOrder(po_no=no, ref=f"IC/LPO/{no}", order_date=date(2026, 10, 26), supplier_id=supplier.id, supplier_name=supplier.name,
                             status="issued", zoho_status="", zoho_account="Materials for Electrical Work")
    s.add(o); s.flush()
    for desc, q, rate, tax in lines:
        s.add(models.PurchaseOrderLine(order_id=o.id, description=desc, qty=q, unit="nos", rate=rate, tax_pct=tax))
    s.commit(); return o
send = lambda o: pozoho.send({"ids": [o.id]}, s, u)
# 1. IC/LPO/20260157 as it stands: 0% to a not-registered vendor - refused before, sent now
a = po(20260157, mah, [("Legrand Mallia Senses 13A Switched Socket Single (Champagne Gold)", 20, 40, 0)])
a.zoho_err = "VAT or Exemption cannot be applied for this VAT Treatment."; s.commit()      # the refusal on the screen
r = send(a); s.refresh(a)
b1 = POSTED[-1] if POSTED else {}
ok(r["sent"] == 1 and a.zoho_status == "sent" and not a.zoho_err, "IC/LPO/20260157 (0%, vendor not VAT registered): sent, refusal cleared")
ok(b1.get("tax_treatment") == "vat_not_registered" and all("tax_id" not in l for l in b1.get("line_items", [])), "...as not VAT registered, no tax on the line")
ok(b1["line_items"][0]["quantity"] == 20 and b1["line_items"][0]["rate"] == 40 and b1["line_items"][0]["account_id"] == "ACC-EL", "...20 x 40.00 = 800.00 to Materials for Electrical Work")
# 2. 5% to the same not-registered vendor, no proper TRN: a plain message, nothing sent
b = po(20260158, mah, [("Socket", 10, 40, 5)])
r = send(b); s.refresh(b)
ok(r["sent"] == 0 and "TRN" in b.zoho_err and "Zoho" in b.zoho_err, "5% to a not-registered vendor without a 15-digit TRN: plain message, nothing sent")
mah.trn = "100999888700003"; s.commit()
r = send(b); s.refresh(b); b2 = POSTED[-1]
ok(r["sent"] == 1 and b2.get("tax_treatment") == "vat_registered" and b2.get("tax_reg_no") == "100999888700003" and b2["line_items"][0]["tax_id"] == "V5",
   "...TRN put on the supplier: sent as VAT registered, 5% Standard Rate")
# 3. registered vendor: exactly as before - 5% and Zero Rate on the lines, no treatment sent
c = po(20260159, gem, [("Channel", 100, 7.1, 5), ("Clips", 10, 2, 0)])
r = send(c); b3 = POSTED[-1]
ok(r["sent"] == 1 and [l["tax_id"] for l in b3["line_items"]] == ["V5", "V0"] and "tax_treatment" not in b3, "registered vendor, 5% + 0%: unchanged (Standard Rate / Zero Rate)")
d = po(20260160, gem, [("Clips", 10, 2, 0)])
r = send(d); b4 = POSTED[-1]
ok(r["sent"] == 1 and b4["line_items"][0]["tax_id"] == "V0" and "tax_treatment" not in b4, "registered vendor, all 0%: Zero Rate, unchanged")
e = po(20260161, dz, [("Cable", 5, 100, 0)])
r = send(e); b5 = POSTED[-1]
ok(r["sent"] == 1 and b5["line_items"][0]["tax_id"] == "V0", "free-zone registered vendor, 0%: Zero Rate, unchanged")
# 4. Zoho cannot say the vendor's treatment: as before
TREAT["V-GEM"] = ""
f = po(20260162, gem, [("Paint", 4, 90, 5)])
r = send(f); b6 = POSTED[-1]
ok(r["sent"] == 1 and b6["line_items"][0]["tax_id"] == "V5" and "tax_treatment" not in b6, "vendor treatment unknown: sent exactly as before")
print("fails=", fails)

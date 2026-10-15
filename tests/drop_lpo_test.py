"""The two admin LPOs are deleted (with their material requests); one still
in Zoho waits until it is reversed; nothing else is touched."""
import os, sys, tempfile
from datetime import date
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
os.environ["INFINIA_CRED_KEY_FILE"] = tempfile.mktemp(suffix=".key")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as M, models, pozoho as P
from database import SessionLocal, engine
models.Base.metadata.create_all(bind=engine); M._add_missing_columns()
s = SessionLocal(); f = []
def ok(c, m): print(("PASS " if c else "FAIL ") + m); f.append(c)
def po(no, sup, zid=""):
    mr = models.MaterialRequest(ref=f"MR-{no}", site="STORE", requested_on=date(2026, 10, 9)); s.add(mr); s.flush()
    s.add(models.MaterialRequestLine(request_id=mr.id, description="x"))
    o = models.PurchaseOrder(po_no=no, ref=f"IC/LPO/{no}", order_date=date(2026, 10, 9), supplier_name=sup, request_id=mr.id, status="issued", zoho_id=zid)
    s.add(o); s.flush(); s.add(models.PurchaseOrderLine(order_id=o.id, description="x", qty=1, rate=10)); s.commit(); return o.id, mr.id
a = po(20260125, "Abc International Tr LLC"); b = po(20260126, "Absolute Royal Technologies", "purchaseorder:1"); c = po(20260124, "Seomaa")
w = P.drop_admin_lpos(s)
ok(w == ["IC/LPO/20260126"], "0125 deleted; 0126 waits while still in Zoho")
ok(s.get(models.PurchaseOrder, a[0]) is None and s.get(models.MaterialRequest, a[1]) is None, "0125 and its request gone")
ok(s.get(models.PurchaseOrder, c[0]) is not None, "other LPOs untouched")
s.get(models.PurchaseOrder, b[0]).zoho_id = ""; s.commit()          # reversed on Sent to Zoho
ok(P.drop_admin_lpos(s) == [] and s.get(models.PurchaseOrder, b[0]) is None, "after the reverse: 0126 deleted too")
ok(s.query(models.PurchaseOrderLine).count() == 1 and s.query(models.MaterialRequest).count() == 1, "only the other LPO's lines and request remain")
ok(P.drop_admin_lpos(s) == [], "done once")
print("ALL PASS" if all(f) else "FAILED")

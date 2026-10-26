"""LPO signature: a new purchaser's signature applies from the moment it is uploaded - orders sent before keep
the signature they went out with (and orders from before any signature on record print unsigned until
'the signature for the earlier orders' is uploaded).
    cp /tmp/full_base.db /tmp/sg.db && cd app && INFINIA_DATA_DIR=/tmp/sgdata DATABASE_URL=sqlite:////tmp/sg.db INFINIA_NO_SCHED=1 python3 ../tests/lpo_signature_history_test.py
"""
import os, sys, io, time, shutil
d = os.environ.get("INFINIA_DATA_DIR", "/tmp/sgdata"); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
os.environ["INFINIA_DATA_DIR"] = d
sys.path.insert(0, os.getcwd())
from datetime import datetime, timedelta
from PIL import Image
from fastapi.testclient import TestClient
import main as M, models, export_web
from database import SessionLocal
c = TestClient(M.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:300]}"))
    if not ok: fails.append(n)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
def png(color):
    b = io.BytesIO(); Image.new("RGB", (300, 120), color).save(b, "PNG"); return b.getvalue()
def up(color, name, earlier=0):
    return c.post(f"/store/purchase/signature?kind=lpo&name={name}&earlier={earlier}", headers=H, files={"file": ("s.png", png(color), "image/png")})
db = SessionLocal()
def order(when):
    o = models.PurchaseOrder(po_no=int(time.time() * 1000) % 10**9, ref=f"IC/LPO/T{time.time_ns()}", order_date=when.date(), supplier_name="X", created_at=when)
    db.add(o); db.commit(); return o
old_o = order(datetime.utcnow() - timedelta(days=30))
r = up((200, 0, 0), "Previous purchaser"); ck("first signature uploaded", r.status_code == 200, r.text)
time.sleep(1.2)
mid_o = order(datetime.utcnow())
time.sleep(1.2)
r = up((0, 0, 200), "Arun"); ck("Arun's signature uploaded", r.status_code == 200, r.text)
new_o = order(datetime.utcnow() + timedelta(seconds=2))
def who(p):
    if not p: return None
    for e in export_web.sig_history("lpo"):
        if os.path.join(export_web.DATA_DIR, e["file"]) == p: return e["name"]
    return "current"
f_mid, f_new, f_old = export_web.signature_file(mid_o.created_at), export_web.signature_file(new_o.created_at), export_web.signature_file(old_o.created_at)
ck("an order sent before Arun keeps the previous purchaser's signature", who(f_mid) == "Previous purchaser", who(f_mid))
ck("an order made after prints Arun's", who(f_new) == "Arun", who(f_new))
ck("an order from before any signature on record prints unsigned (not someone else's)", f_old is None, f_old)
r = up((0, 160, 0), "Earlier man", earlier=1)
f_old = export_web.signature_file(old_o.created_at)
ck("'signature for the earlier orders' covers them", who(f_old) == "Earlier man", who(f_old))
import filecmp
ck("the current signature is still Arun's", filecmp.cmp(export_web.signature_file(), os.path.join(export_web.DATA_DIR, [e for e in export_web.sig_history("lpo") if e["name"] == "Arun"][0]["file"]), shallow=False))
st = c.get("/store/purchase/signature-status", headers=H).json()
ck("status lists who signed from when", [h["name"] for h in st["history"]] == ["Earlier man", "Previous purchaser", "Arun"], st.get("history"))
tok = c.post("/auth/download-token", headers=H).json()["token"]
pdf = c.get(f"/export/purchase/{mid_o.id}?token={tok}&format=pdf")
ck("the order's PDF still opens", pdf.status_code == 200 and pdf.content[:4] == b"%PDF", pdf.status_code)
print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL PASS"); sys.exit(1 if fails else 0)

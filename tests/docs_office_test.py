"""Store > Stock > Docs to office: the store keeper sends, the office checks in."""
import os, sys, tempfile
from datetime import date, timedelta
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
os.environ["INFINIA_CRED_KEY_FILE"] = tempfile.mktemp(suffix=".key")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as M, models, docsoffice as D
from database import SessionLocal, engine
from fastapi import HTTPException
models.Base.metadata.create_all(bind=engine); M._add_missing_columns()
s = SessionLocal(); fails = 0
def ok(c, m):
    global fails
    print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1
def refused(fn, m):
    try:
        fn(); ok(False, m)
    except HTTPException:
        ok(True, m)
admin = models.User(username="ad", full_name="Admin", hashed_password="x", role="admin")
amal = models.User(username="amal", full_name="Amal", hashed_password="x", role="user", permissions='["docs_send"]')
muh = models.User(username="muh", full_name="Muhsina", hashed_password="x", role="user", permissions='["docs_verify"]')
s.add_all([admin, amal, muh, models.Site(code="913")]); s.commit()
today = M._dubai_today()
L = D.listing(s, admin)
ok(L["next_ref"] == "DOF:005", "numbering starts at DOF:005 after the paper forms")
p = {"date": today.isoformat(), "from_site": "913", "lines": [
    {"description": "Delivery note", "dn_no": "DN-11", "site": "913", "date": today.isoformat()},
    {"description": "Invoice copy", "dn_no": "INV-7"}, {"description": "", "dn_no": ""}]}
x = D.create(p, s, admin)
ok(x["ref"] == "DOF:005" and len(x["lines"]) == 2, "sent with its number; the empty row is left out")
ok(D.listing(s, admin)["next_ref"] == "DOF:006", "the next one is DOF:006")
refused(lambda: D.create({**p, "date": (today + timedelta(days=1)).isoformat()}, s, admin), "a future date is refused")
refused(lambda: D.create({"date": today.isoformat(), "lines": []}, s, admin), "at least one document is needed")
x = D.edit(x["id"], {**p, "lines": p["lines"][:1]}, s, admin)
ok(len(x["lines"]) == 1, "the store keeper can change it before the office checks")
x = D.edit(x["id"], p, s, admin)
ids = [l["id"] for l in x["lines"]]
refused(lambda: D.receive(x["id"], {"lines": [{"id": ids[0], "received": True}]}, s, admin), "every document must be ticked")
s.rollback()
r = D.receive(x["id"], {"lines": [{"id": ids[0], "received": True}, {"id": ids[1], "received": False}], "note": "invoice missing"}, s, admin)
ok(r["status"] == "partial" and r["n_missing"] == 1, "one missing: marked partial")
refused(lambda: D.edit(x["id"], p, s, admin), "cannot change once the office has checked")
refused(lambda: D.remove(x["id"], s, admin), "cannot delete once the office has checked")
pdf = D.build_pdf(s.get(models.DocTransmittal, x["id"]), D._users(s)).read()
ok(pdf[:4] == b"%PDF" and len(pdf) > 2000, "the form prints as a PDF")
r = D.reopen(x["id"], s, admin)
ok(r["status"] == "sent" and r["n_received"] == 0, "the office can reopen it")
r = D.receive(x["id"], {"lines": [{"id": i, "received": True} for i in ids]}, s, admin)
ok(r["status"] == "received", "all ticked: received")
y = D.create(p, s, admin); D.remove(y["id"], s, admin)
ok(s.get(models.DocTransmittal, y["id"]) is None, "an unchecked one can be deleted")
ok(s.query(models.AuditLog).filter(models.AuditLog.action.like("docs_%")).count() >= 6, "every step is in the activity log")
print("ALL PASS" if not fails else f"{fails} FAILED"); sys.exit(1 if fails else 0)

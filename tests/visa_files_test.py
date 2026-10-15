"""Visa files: one file per visa process, PRO payments tied to it by stage,
stages ticked, completed files drop off the PRO's list, money adds up."""
import os, sys, tempfile
from datetime import date, timedelta
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
os.environ["INFINIA_CRED_KEY_FILE"] = tempfile.mktemp(suffix=".key")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as M, models, visa as V, pettycash as P
from database import SessionLocal, engine
from fastapi import HTTPException
models.Base.metadata.create_all(bind=engine); M._add_missing_columns()
s = SessionLocal(); fails = 0
def ok(c, m, i=""):
    global fails
    print(("PASS " if c else "FAIL ") + m + ("" if c else f"  {i}")); fails += 0 if c else 1
def refused(fn, m):
    try:
        fn(); ok(False, m)
    except HTTPException:
        s.rollback(); ok(True, m)
admin = models.User(username="ad", full_name="Jomon Thomas", hashed_password="x", role="admin")
e = models.Employee(emp_no="IC-L-0412", name="ERIC MAMBO", active=True)
s.add_all([admin, e]); s.commit()
today = M._dubai_today()
f = V.create({"employee_id": e.id, "kind": "new"}, s, admin)
ok(f["person"] == "Eric Mambo" and len(f["stages"]) == 8 and f["next"] == "Entry permit", "new visa file: 8 stages, next Entry permit")
refused(lambda: V.create({"employee_id": e.id, "kind": "new"}, s, admin), "a second ongoing new-visa file for him is refused")
g = V.create({"person": "Md Imran Alam", "emp_no": "F767", "kind": "cancel"}, s, admin)
ok(len(g["stages"]) == 3, "cancellation: 3 stages, person typed by name")
o = V.open_files(s, admin)
ok(len(o["files"]) == 2 and o["supplier"] == "MOHRE & GDRFA", "both on the PRO's list")
def pay(amt, stage, fid=f["id"], book="pro"):
    return P.add_petty_cash({"book": book, "date": today.isoformat(), "description": f"Eric Mambo - New visa - {stage}", "supplier": "MOHRE & GDRFA",
                             "paid": amt, "visa_file_id": fid, "visa_stage": stage}, s, admin)["id"]
pay(2750, "Entry permit"); pay(1320.33, "Change of status"); p3 = pay(500, "Medical test")
L = V.listing(s, "ongoing"); r = next(x for x in L["rows"] if x["id"] == f["id"])
ok(r["spent"] == 4570.33 and r["n_done"] == 3 and r["next"] == "Emirates ID", "three payments: AED 4,570.33, 3 of 8, next Emirates ID")
ok(L["tiles"]["ongoing"] == 2 and L["tiles"]["spent_ongoing"] == 4570.33, "tiles: 2 ongoing, AED 4,570.33")
refused(lambda: pay(10, "Not a stage"), "a stage not on the file is refused")
x = s.get(models.PettyCash, p3)
ok(x.visa_file_id == f["id"] and x.visa_stage == "Medical test", "the petty cash line carries the file and stage")
reg = P.register(s, today.strftime("%Y-%m"), "pro")
ok(any(rr["visa_person"] == "Eric Mambo" and rr["visa_stage"] == "Medical test" for rr in reg["rows"]), "register shows the visa file on the line")
# editing the line without the visa fields leaves the link alone
P.edit_petty_cash(p3, {"date": today.isoformat(), "description": "Medical", "paid": 500}, s, admin); s.refresh(x)
ok(x.visa_file_id == f["id"], "an edit that does not send the visa fields keeps the link")
P.edit_petty_cash(p3, {"date": today.isoformat(), "description": "Medical", "paid": 500, "visa_file_id": None}, s, admin); s.refresh(x)
ok(x.visa_file_id is None, "choosing not a visa cost unties it")
V.link(f["id"], {"petty_id": p3, "stage": "Medical test"}, s, admin); s.refresh(x)
ok(x.visa_file_id == f["id"], "a payment made before can be tied from Visa files")
site = P.add_petty_cash({"book": "site", "date": today.isoformat(), "description": "Visa", "paid": 5, "visa_file_id": f["id"]}, s, admin)["id"]
ok(s.get(models.PettyCash, site).visa_file_id is None, "a site petty cash line is never tied to a visa file")
V.stage(f["id"], {"stage": "Emirates ID", "done": True}, s, admin)
r = V._out(s, s.get(models.VisaFile, f["id"]))
ok(r["n_done"] == 4 and r["next"] == "Labour contract (MOHRE)", "a stage ticked by hand")
refused(lambda: V.remove(f["id"], s, admin), "a file with payments cannot be deleted")
V.complete(f["id"], s, admin)
ok(len(V.open_files(s, admin)["files"]) == 1, "completed: drops off the PRO's list")
refused(lambda: pay(100, "Visa stamping"), "a new payment on a completed file is refused")
P.edit_petty_cash(p3, {"date": today.isoformat(), "description": "Medical", "paid": 500, "visa_file_id": f["id"], "visa_stage": "Medical test"}, s, admin)
ok(True, "a line already on a completed file can still be edited")
C = V.listing(s, "completed")
ok(len(C["rows"]) == 1 and C["rows"][0]["spent"] == 4570.33 and C["tiles"]["completed_year"] == 1, "completed list keeps the full cost")
V.reopen(f["id"], s, admin)
ok(len(V.open_files(s, admin)["files"]) == 2, "reopened: back on the list")
V.remove(g["id"], s, admin)
ok(s.get(models.VisaFile, g["id"]) is None, "an empty file can be deleted")
ok(any(u["description"] for u in V._unlinked(s)) or True, "unlinked suggestions run")
# a stage paid from Visa files goes into PRO petty cash
h = V.create({"person": "Hebson Test", "kind": "new_out"}, s, admin)
r = V.pay(h["id"], {"stage": "Medical test", "date": today.isoformat(), "amount": "320.50"}, s, admin)
px = s.query(models.PettyCash).filter(models.PettyCash.visa_file_id == h["id"]).one()
ok(px.book == "pro" and px.paid == 320.5 and px.supplier == "MOHRE & GDRFA" and px.description == "Hebson Test - New visa (outside UAE) - Medical test",
   "Enter the payment now: a PRO petty cash line, supplier and description filled")
ok(r["spent"] == 320.5 and "Medical test" in r["done"], "the stage is ticked and the cost on the file")
refused(lambda: V.pay(h["id"], {"stage": "", "date": today.isoformat(), "amount": "5"}, s, admin), "a payment needs its stage")
r = V.pay_stage(h["id"], {"petty_id": px.id, "stage": "Entry permit"}, s, admin)
ok("Entry permit" in r["done"] and r["payments"][0]["stage"] == "Entry permit", "a payment's stage can be pinpointed after")
# a visa cost on PRO petty cash must name its file
refused(lambda: P.add_petty_cash({"book": "pro", "date": today.isoformat(), "description": "Ali visa exp", "paid": 50}, s, admin),
        "PRO: 'visa' in the description without a visa file is refused")
P.add_petty_cash({"book": "pro", "date": today.isoformat(), "description": "Diesel for car", "paid": 50}, s, admin)
ok(True, "PRO: other costs save as before")
P.add_petty_cash({"book": "site", "date": today.isoformat(), "description": "visa photo copies", "paid": 5}, s, admin)
ok(True, "site book is not asked for a visa file")
old = P.add_petty_cash({"book": "pro", "date": (V.START - timedelta(days=3)).isoformat(), "description": "Old visa exp", "paid": 9}, s, admin)
ok(True, "a line dated before Visa files started is not asked")

# the visas in progress at go-live: opened once, payments tied, money exact
s.add(models.Employee(emp_no="F-727", name="BENCHEP OLIVER KARNGONG", active=True))
for pid, amt, *_ in V.SEED:
    s.add(models.PettyCash(id=pid, book="pro", on_date=date(2026, 10, 14), description="visa", paid=amt))
s.flush(); s.get(models.PettyCash, 2896).paid = 1.0     # changed since: left alone
s.commit()
n = V.seed_existing(s)
ok(n == 7, "seed: 7 files opened, the changed line left for the PRO", n)
ok(V.seed_existing(s) == 0, "seed runs once only")
seeded = [r for r in V.listing(s, "ongoing")["rows"] if r["note"].startswith("Opened when")]
ok(round(sum(r["spent"] for r in seeded), 2) == 25468.19, "seeded total exact", round(sum(r["spent"] for r in seeded), 2))
b = next(r for r in seeded if r["emp_no"] == "F-727")
ok(b["person"] == "Benchep Oliver Karngong" and b["kind"] == "renewal" and b["started"] == "2026-10-14", "renewal file named from the staff list")
ok(any(r["person"] == "Eric Mambo" and r["kind"] == "new" for r in seeded), "Eric Mambo: new visa by name")
print("ALL PASS" if not fails else f"{fails} FAILED"); sys.exit(1 if fails else 0)

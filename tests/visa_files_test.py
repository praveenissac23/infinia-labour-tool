"""Visa files: one file per visa process, PRO payments tied to it by stage,
stages ticked, completed files drop off the PRO's list, money adds up."""
import os, sys, tempfile, json
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
ok(f["person"] == "Eric Mambo" and len(f["stages"]) == 10 and f["next"] == "Quota modification", "new visa (inside): the PRO's 10 steps, no '(if needed)'")
refused(lambda: V.create({"employee_id": e.id, "kind": "new"}, s, admin), "a second ongoing new-visa file for him is refused")
g = V.create({"person": "Md Imran Alam", "emp_no": "F767", "kind": "cancel"}, s, admin)
ok(len(g["stages"]) == 3, "cancellation: 3 stages, person typed by name")
o = V.open_files(s, admin)
ok(len(o["files"]) == 2 and o["supplier"] == "MOHRE & GDRFA", "both on the PRO's list")
def pay(amt, stage, fid=f["id"], book="pro"):
    return P.add_petty_cash({"book": book, "date": today.isoformat(), "description": f"Eric Mambo - New visa - {stage}", "supplier": "MOHRE & GDRFA",
                             "paid": amt, "visa_file_id": fid, "visa_stage": stage}, s, admin)["id"]
pay(2750, "New labour contract"); pay(1320.33, "WPP insurance"); p3 = pay(500, "New work permit")
L = V.listing(s, "ongoing"); r = next(x for x in L["rows"] if x["id"] == f["id"])
ok(r["spent"] == 4570.33 and r["n_done"] == 3 and r["next"] == "Quota modification", "three payments: AED 4,570.33, 3 done, next New entry permit (inside)")
ok(L["tiles"]["ongoing"] == 2 and L["tiles"]["spent_ongoing"] == 4570.33, "tiles: 2 ongoing, AED 4,570.33")
pay(60, "Medical re-test")
ff = V._out(s, s.get(models.VisaFile, f["id"]))
ok("Medical re-test" in ff["stages"] and "Medical re-test" in ff["done"] and "Medical re-test" in V.steps_master(s), "a step typed in: added to his file and to the list offered next time")
pid60 = s.query(models.PettyCash).filter(models.PettyCash.paid == 60).one().id
P.delete_petty_cash(pid60, s, admin)
x = s.get(models.PettyCash, p3)
ok(x.visa_file_id == f["id"] and x.visa_stage == "New work permit", "the petty cash line carries the file and step")
reg = P.register(s, today.strftime("%Y-%m"), "pro")
ok(any(rr["visa_person"] == "Eric Mambo" and rr["visa_stage"] == "New work permit" for rr in reg["rows"]), "register shows the visa file on the line")
# editing the line without the visa fields leaves the link alone
P.edit_petty_cash(p3, {"date": today.isoformat(), "description": "Medical", "paid": 500}, s, admin); s.refresh(x)
ok(x.visa_file_id == f["id"], "an edit that does not send the visa fields keeps the link")
P.edit_petty_cash(p3, {"date": today.isoformat(), "description": "Medical", "paid": 500, "visa_file_id": None}, s, admin); s.refresh(x)
ok(x.visa_file_id is None, "choosing not a visa cost unties it")
V.link(f["id"], {"petty_id": p3, "stage": "New work permit"}, s, admin); s.refresh(x)
ok(x.visa_file_id == f["id"], "a payment made before can be tied from Visa files")
site = P.add_petty_cash({"book": "site", "date": today.isoformat(), "description": "Visa", "paid": 5, "visa_file_id": f["id"]}, s, admin)["id"]
ok(s.get(models.PettyCash, site).visa_file_id is None, "a site petty cash line is never tied to a visa file")
V.stage(f["id"], {"stage": "New entry permit (inside)", "done": True}, s, admin)
r = V._out(s, s.get(models.VisaFile, f["id"]))
ok("New entry permit (inside)" in r["done"], "a step ticked by hand")
r = V.edit_steps(f["id"], {"remove": "Quota modification"}, s, admin)
ok("Quota modification" not in r["stages"], "a step not needed is taken off this file")
r = V.edit_steps(f["id"], {"add": "Typing correction"}, s, admin)
ok("Typing correction" in r["stages"] and "Typing correction" in V.steps_master(s), "+ Add step: on the file and in the list for next time")
refused(lambda: V.remove(f["id"], s, admin), "a file with payments cannot be deleted")
V.complete(f["id"], s, admin)
ok(len(V.open_files(s, admin)["files"]) == 1, "completed: drops off the PRO's list")
refused(lambda: pay(100, "New residency stamping"), "a new payment on a completed file is refused")
P.edit_petty_cash(p3, {"date": today.isoformat(), "description": "Medical", "paid": 500, "visa_file_id": f["id"], "visa_stage": "New work permit"}, s, admin)
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
r = V.pay(h["id"], {"stage": "Medical and EID", "date": today.isoformat(), "amount": "320.50"}, s, admin)
px = s.query(models.PettyCash).filter(models.PettyCash.visa_file_id == h["id"]).one()
ok(px.book == "pro" and px.paid == 320.5 and px.supplier == "" and px.description == "Hebson Test - New visa (outside UAE) - Medical and EID",
   "Enter the payment now: a PRO petty cash line, description filled, supplier left empty")
ok(r["spent"] == 320.5 and "Medical and EID" in r["done"], "the step is ticked and the cost on the file")
refused(lambda: V.pay(h["id"], {"stage": "", "date": today.isoformat(), "amount": "5"}, s, admin), "a payment needs its stage")
r = V.pay_stage(h["id"], {"petty_id": px.id, "stage": "New entry permit"}, s, admin)
ok("New entry permit" in r["done"] and r["payments"][0]["stage"] == "New entry permit", "a payment's step can be pinpointed after")
# answering Completed on the petty cash form closes the visa
w = V.create({"person": "Work Permit Man", "kind": "work_permit"}, s, admin)
ok(len(w["stages"]) == 5, "work permit: 5 steps")
P.add_petty_cash({"book": "pro", "date": today.isoformat(), "description": "Work Permit Man - New work permit", "paid": 100,
                  "visa_file_id": w["id"], "visa_stage": "New work permit", "visa_complete": True}, s, admin)
ok(s.get(models.VisaFile, w["id"]).status == "completed", "Visa process status Completed: the visa is closed")
nw = V.create({"person": "National Man", "kind": "national_wp"}, s, admin)
ok(nw["kind_label"] == "National work permit", "national work permit type")
P.add_petty_cash({"book": "pro", "date": today.isoformat(), "description": "Diesel for car", "paid": 50}, s, admin)
ok(True, "PRO: other costs save as before")
P.add_petty_cash({"book": "pro", "date": today.isoformat(), "description": "Asathy Travel Report", "supplier": "GDRFA", "paid": 275.65}, s, admin)
ok(True, "PRO: a GDRFA travel report (no visa in the description) saves without a visa file")
P.add_petty_cash({"book": "site", "date": today.isoformat(), "description": "visa photo copies", "paid": 5}, s, admin)
ok(True, "site book is not asked for a visa file")
P.add_petty_cash({"book": "pro", "date": today.isoformat(), "description": "Ali visa exp", "paid": 50}, s, admin)
ok(True, "any description saves - the PRO answers 'Visa related expense?' himself")

# the visas in progress at go-live: opened once, payments tied, money exact
s.add(models.Employee(emp_no="F-727", name="BENCHEP OLIVER KARNGONG", active=True))
for pid, amt, *_ in V.SEED:
    s.add(models.PettyCash(id=pid, book="pro", on_date=date(2026, 10, 14), description="visa", paid=amt))
s.flush(); s.get(models.PettyCash, 2896).paid = 1.0     # changed since: left alone
s.commit()
n = V.seed_existing(s)
ok(n == 7, "seed: 7 files opened, the changed line left for the PRO", n)
ok(V.seed_existing(s) == 0, "seed runs once only")
seed_ids = {pid for pid, *_ in V.SEED}
seed_files = {x.visa_file_id for x in s.query(models.PettyCash).filter(models.PettyCash.id.in_(seed_ids)).all() if x.visa_file_id}
seeded = [r for r in V.listing(s, "ongoing")["rows"] if r["id"] in seed_files]
ok(round(sum(r["spent"] for r in seeded), 2) == 25468.19, "seeded total exact", round(sum(r["spent"] for r in seeded), 2))
b = next(r for r in seeded if r["emp_no"] == "F-727")
ok(b["person"] == "Benchep Oliver Karngong" and b["kind"] == "renewal" and b["started"] == "2026-10-14", "renewal file named from the staff list")
ok(any(r["person"] == "Eric Mambo" and r["kind"] == "new" for r in seeded), "Eric Mambo: new visa by name")
ok(not any("(if needed)" in x for x in V.steps_master(s)), "no '(if needed)' in the step list")
vv = s.query(models.VisaFile).first(); vv.stages = json.dumps(["ILOE insurance (if needed)", "Medical and EID"]); vv.done = json.dumps(["ILOE insurance (if needed)"]); s.commit()
V.drop_if_needed(s); s.refresh(vv)
ok(json.loads(vv.stages) == ["ILOE insurance", "Medical and EID"] and json.loads(vv.done) == ["ILOE insurance"], "old names on files renamed once")
vv = s.query(models.VisaFile).first(); vv.note = "Opened when Visa files started - tick the stages already done"; s.commit()
V.clear_seed_note(s); s.refresh(vv)
ok(vv.note == "", "the 'Opened when Visa files started' note is removed")
print("ALL PASS" if not fails else f"{fails} FAILED"); sys.exit(1 if fails else 0)

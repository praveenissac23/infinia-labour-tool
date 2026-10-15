"""PRO petty cash, 'Visa related expense?' Yes: whose visa (ongoing, or a new
name that opens a visa by itself), step (picked or typed - typed ones are
kept), Completed takes the name off the list; amount booked that month."""
import os, sys, tempfile
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
os.environ["INFINIA_CRED_KEY_FILE"] = tempfile.mktemp(suffix=".key")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as M, models, visa as V, pettycash as P
from database import SessionLocal, engine
models.Base.metadata.create_all(bind=engine); M._add_missing_columns()
s = SessionLocal(); f = []
def ok(c, m, i=""): print(("PASS " if c else "FAIL ") + m + ("" if c else f"  {i}")); f.append(c)
u = models.User(username="jomon", full_name="Jomon", hashed_password="x", role="admin"); s.add(u)
s.add(models.Employee(emp_no="F-728", name="DIWAKAR", active=True)); s.commit()
t = M._dubai_today().isoformat()
def add(desc, amt, who="", step="", done=False, sup="Cash payment"):
    p = {"book": "pro", "date": t, "description": desc, "supplier": sup, "paid": amt}
    if who is not None:
        p.update({"visa_person": who, "visa_stage": step, "visa_complete": done})
    return P.add_petty_cash(p, s, u)["id"]
add("Diesel", 40, who="")
ok(V.open_files(s, u)["files"] == [], "'No': a normal petty cash line, no visa")
a = add("Eric medical", 320, who="Eric Mambo", step="Medical and EID")
fl = V.open_files(s, u)["files"]
ok(len(fl) == 1 and fl[0]["person"] == "Eric Mambo", "a new name typed: a visa opens by itself")
add("Eric labour contract", 500, who="eric mambo", step="New labour contract")
fl = V.open_files(s, u)["files"]
ok(len(fl) == 1 and fl[0]["spent"] == 820.0, "same name again (any case): the same visa, AED 820.00 so far")
add("Diwakar renewal", 5272.7, who="Diwakar", step="Typing correction")
fl = {x["person"]: x for x in V.open_files(s, u)["files"]}
ok(fl["Diwakar"]["emp_no"] == "F-728", "a name on the staff list is linked to him")
ok("Typing correction" in V.steps_master(s), "a step typed in is kept for next time")
ok("Medical and EID" in V.steps_master(s) and "New residency stamping" in V.steps_master(s), "Jomon's standard steps are in the list")
add("Eric residency", 1000, who="Eric Mambo", step="New residency stamping", done=True)
names = [x["person"] for x in V.open_files(s, u)["files"]]
ok(names == ["Diwakar"], "Completed: Eric is no longer offered", names)
reg = P.register(s, t[:7], "pro")
ok(round(reg["paid"], 2) == 7132.7, "all booked in this month's petty cash", reg["paid"])
ok(any(r["visa_person"] == "Eric Mambo" and r["visa_stage"] == "Medical and EID" for r in reg["rows"]), "the line shows whose visa and the step")
add("Eric again", 50, who="Eric Mambo", step="Medical re-test")
ok(len([x for x in V.open_files(s, u)["files"] if x["person"] == "Eric Mambo"]) == 1, "a completed name typed again: a new visa for him")
print("ALL PASS" if all(f) else "FAILED")

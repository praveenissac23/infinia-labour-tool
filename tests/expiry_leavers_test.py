"""Expiry Reminder drops a man who has left once the pay cycle he left in
is over - from the documents list, the missing list, the counters, the
bell, the export and Staff > Documents due. Inside that cycle he stays.

Run: cd app && DATABASE_URL=sqlite:////tmp/el.db python3 ../tests/expiry_leavers_test.py
"""
import sys, os
from datetime import date, timedelta
sys.path.insert(0, os.getcwd())
import main as M                      # first, so expiry imports cleanly
import expiry, people, models
from database import SessionLocal, Base, engine
from fastapi.testclient import TestClient

Base.metadata.create_all(bind=engine)
bad = 0
def ck(name, ok, info=""):
    global bad
    bad += not ok
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"   {info}"))

db = SessionLocal()
today = M._dubai_today()
from payroll_cycle import cycle_bounds_for
start, end, _ = cycle_bounds_for(today)
before = start - timedelta(days=5)          # left in the cycle that is over
inside = start + timedelta(days=1) if start + timedelta(days=1) <= today else today   # left in this cycle
later = end - timedelta(days=2)              # leaving later this cycle
men = {"LV-OLD": before, "LV-NOW": inside, "LV-SOON": later, "LV-STAY": None}
for code, left in men.items():
    e = db.query(models.Employee).filter_by(emp_no=code).first()
    if not e:
        e = models.Employee(emp_no=code, name="TEST " + code, company="Infinia", active=True, staff=False, terminated_on=left)
        db.add(e); db.flush()
        db.add(models.EmployeeDocument(employee_id=e.id, kind="eid", expires_on=today - timedelta(days=3)))   # expired: would be on every list
db.add(models.Employee(emp_no="LV-OLDNODOC", name="TEST OLD NO DOC", company="Infinia", active=True, staff=False, terminated_on=before)) if not db.query(models.Employee).filter_by(emp_no="LV-OLDNODOC").first() else None
db.add(models.Employee(emp_no="LV-NOWNODOC", name="TEST NOW NO DOC", company="Infinia", active=True, staff=False, terminated_on=inside)) if not db.query(models.Employee).filter_by(emp_no="LV-NOWNODOC").first() else None
db.commit()

listed = {r["emp_no"] for r in M.list_documents(db=db, user=None)["rows"]}
ck(f"left {before} (cycle ended {start - timedelta(days=1)}): off the documents list", "LV-OLD" not in listed)
ck(f"left {inside} (this cycle): still on the list", "LV-NOW" in listed)
ck(f"leaving {later} (this cycle): still on the list", "LV-SOON" in listed)
ck("still working: on the list", "LV-STAY" in listed)
miss = {p["emp_no"] for p in expiry.missing_people(db)}
ck("missing-documents list: the old leaver is gone", "LV-OLDNODOC" not in miss, miss)
ck("missing-documents list: this cycle's leaver still shows", "LV-NOWNODOC" in miss)
s = expiry.summary(db)
att = {i["who"].split()[0] for i in s["attention"]}
ck("expired counter and attention list: old leaver not counted", "LV-OLD" not in att and "LV-NOW" in att, att)
due = {r["emp_no"] for r in people.documents_due(days=90, group="", db=db, user=models.User(role="admin", username="t"))["rows"]}
ck("Staff > Documents due: old leaver gone, this cycle's leaver there", "LV-OLD" not in due and "LV-NOW" in due, due)
# The day after his cycle ends the man who left in this cycle drops off too.
e = db.query(models.Employee).filter_by(emp_no="LV-NOW").first()
ck("and the morning after this cycle ends, he drops off as well", M.doc_tracked(e, end) and not M.doc_tracked(e, end + timedelta(days=1)))
print("LEAVERS LEAVE THE REMINDERS" if not bad else f"{bad} FAILED")
sys.exit(1 if bad else 0)

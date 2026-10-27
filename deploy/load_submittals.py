"""Load the material submittal logs of 914 (ae5548), 915 (ae5549) and 919 (ae5556) into
Estimation > a project > Site & technical > Submittals.

    cd ~/infinia-labour-tool && venv/bin/python deploy/load_submittals.py

From deploy/submittals_oct27.json - read from "Material Submittal Log - ae5548 ae5549 ae5556.xlsx"
(updated 27 Oct 2026; 919 on 19 Oct): every line as on the log - discipline (CIVIL, ELECTRICAL,
PLUMBING, HVAC, SHOP DRAWINGS), Sr. No, material, specification, manufacturer / supplier, rev,
submitted, reviewed and the consultant's status (NS, UR, A, AAN, R&R, R). Another supplier for an
item is kept under it with the same Sr. No.

Safe to run more than once: a project that has submittals in the app already is left alone
(nothing is added twice, nothing typed in the app is overwritten).
"""
import json, os, sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, HERE)
from clear_test_returns import _find_database_url

url = _find_database_url()
if not url:
    sys.exit("Could not find DATABASE_URL.")
os.environ["DATABASE_URL"] = url
os.environ.setdefault("INFINIA_NO_SCHED", "1"); os.environ.setdefault("INFINIA_NO_PUSH", "1")
import main as M                       # the app first (Estimation is part of it)
from database import SessionLocal, engine
import models
import estimation as E

E.create_tables(engine)                 # the new submittal columns (Sr. No, specification, supplier)
DATA = json.load(open(os.path.join(HERE, "submittals_oct27.json")))
EXPECT = {"914": 52, "915": 47, "919": 18}
d = lambda v: date.fromisoformat(v) if v else None

db = SessionLocal()
try:
    days = E._rules(db).get("submittal_days", 14)
    for code, rows in DATA.items():
        assert len(rows) == EXPECT[code], (code, len(rows))
        p = db.query(E.EstProject).filter(E.EstProject.code == code).first()
        if not p:
            print(f"{code}: no such project in Estimation - skipped"); continue
        have = db.query(E.EstLog).filter(E.EstLog.project_id == p.id, E.EstLog.kind == "submittal").count()
        if have:
            print(f"{code}: {have} submittals in the app already - left as they are"); continue
        for n, x in enumerate(rows, 1):
            sent, rep = d(x["sent"]), d(x["replied"])
            db.add(E.EstLog(project_id=p.id, kind="submittal", seq=n, sort=n, group=x["group"], item_no=x["no"], title=x["title"] or "-",
                            spec=x["spec"], supplier=x["supplier"], rev=x["rev"], party="Consultant", discipline=x["group"].title(),
                            sent=sent, replied=rep, due=(sent + timedelta(days=days)) if sent and not rep else None,
                            status=x["status"]))
        db.commit()
        by = {}
        for x in rows:
            by[x["status"] or "(heading)"] = by.get(x["status"] or "(heading)", 0) + 1
        print(f"{code}: {len(rows)} submittals loaded - " + ", ".join(f"{k} {v}" for k, v in by.items()))
finally:
    db.close()

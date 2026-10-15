"""The October ongoing visa lines move from PRO petty cash to the Visa tab
(held) once; completed ones stay; balance in hand unchanged; a line already
approved for Zoho is never moved."""
import os, sys, tempfile, json
from datetime import date
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
os.environ["INFINIA_CRED_KEY_FILE"] = tempfile.mktemp(suffix=".key")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as M, models, visa as V, pettycash as P
from database import SessionLocal, engine
models.Base.metadata.create_all(bind=engine); M._add_missing_columns()
s = SessionLocal(); f = []
def ok(c, m, i=""): print(("PASS " if c else "FAIL ") + m + ("" if c else f"  {i}")); f.append(c)
d = date(2026, 10, 14)
s.add(models.PettyCash(id=1, book="pro", on_date=date(2026, 10, 1), description="Cash", received=40000))
people = {2891: ("Eric Mambo", 4570.33), 3050: ("Hebson Hondra", 278.77), 3051: ("Ian Kiplayapy", 76.14), 2895: ("Pradeep Yadav", 5272.70),
          2896: ("Pardum Sahani", 5272.70), 2893: ("Benchep", 5272.70), 2894: ("Diwakar", 5272.70), 2897: ("Chhanu", 5272.70)}
for pid, (who, amt) in people.items():
    v = models.VisaFile(person=who, kind="renewal", stages="[]", done="[]", started_on=d, status="completed" if pid == 2894 else "ongoing"); s.add(v); s.flush()
    s.add(models.PettyCash(id=pid, book="pro", on_date=d, description=f"{who} visa", paid=amt, visa_file_id=v.id))
s.commit()
s.get(models.PettyCash, 3051).zoho_status = "approved"; s.commit()     # pretend: already approved - must stay
before = P.register(s, "2026-10", "pro"); hand0 = round(before["closing"] - before["visa_held"], 2)
moved = V.move_ongoing_to_held(s)
ok(len(moved) == 4, "4 ongoing moved (the approved one left in General)", moved)
after = P.register(s, "2026-10", "pro")
ok(round(after["visa_held"], 2) == round(4570.33 + 278.77 + 5272.70 * 2, 2), "held on the Visa tab", after["visa_held"])
ok(round(after["closing"] - after["visa_held"], 2) == hand0, "Balance in hand unchanged", (hand0, after["closing"], after["visa_held"]))
ok(all(s.get(models.PettyCash, i) is None for i in (2891, 3050, 2895, 2896)) and s.get(models.PettyCash, 3051) is not None, "moved lines left General; approved one stayed")
ok(all(s.get(models.PettyCash, i) for i in (2893, 2894, 2897)), "completed visas stay in General")
st = {v.person: v.status for v in s.query(models.VisaFile)}
ok(st["Benchep"] == "completed" and st["Chhanu"] == "completed" and st["Eric Mambo"] == "ongoing", "completed ones marked completed; ongoing stay ongoing", st)
ok(V.move_ongoing_to_held(s) == [], "runs once")
H = V.held_listing(s)
e = next(x for x in H["ongoing"] if x["person"] == "Eric Mambo")
ok(e["total"] == 4570.33 and e["payments"][0]["date"] == "2026-10-14", "Eric on the Visa tab with his payment and its date")
# 15 Oct tidy: Ian's line (now 354.91, not approved) moves; empty test visas go
ian = s.get(models.PettyCash, 3051); ian.zoho_status = ""; ian.paid = 354.91; s.commit()
for n in ("Abdul Matin", "sreelakshmi new visa exp out side"):
    s.add(models.VisaFile(person=n, kind="other", stages="[]", done="[]", started_on=d, status="ongoing"))
s.commit()
h0 = P.register(s, "2026-10", "pro"); hand1 = round(h0["closing"] - h0["visa_held"], 2)
t = V.tidy_oct15(s)
ok(len(t) == 3, "Ian moved, 2 empty visas removed", t)
h1 = P.register(s, "2026-10", "pro")
ok(round(h1["closing"] - h1["visa_held"], 2) == hand1 and s.get(models.PettyCash, 3051) is None, "Ian moved, balance in hand unchanged")
ok(not s.query(models.VisaFile).filter(models.VisaFile.person.in_(["Abdul Matin", "sreelakshmi new visa exp out side"])).count(), "empty visas gone")
ok(V.tidy_oct15(s) == [], "tidy runs once")
print("ALL PASS" if all(f) else "FAILED")

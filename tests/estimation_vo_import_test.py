"""Variation log import (est_voimport.py + /variations/import + the one-time seed).

    cd app && DATABASE_URL=sqlite:////tmp/estvo.db INFINIA_NO_SCHED=1 python3 ../tests/estimation_vo_import_test.py [folder with the QS .xlsx]

Checks every project's accepted / absorbed totals against the totals line of
the QS sheet, that the contract goes back to the original only once, that a
second run adds nothing, and the Excel upload (preview, then save).
"""
import glob, json, os, sys
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main, models, auth, estimation as E
from database import SessionLocal, engine

main._add_missing_columns()
E.create_tables(engine)
c = TestClient(main.app); c.__enter__()
fails = []
def ck(name, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  -> {extra}"))
    if not ok: fails.append(name)

seed = json.load(open(E.VO_SEED_FILE))
# The totals line of each QS sheet (accepted, absorbed) - typed from the files.
SHEET = {"908": (294140.0, 77800.0), "909": (1692144.85, 0), "911": (218807.26, 28108.33), "912": (896316.5, 0),
         "913": (2511654.57, 0), "919": (0, 0)}
ORIGINAL = {"908": 2859973.19, "909": 3673040.0, "911": 4693749.0, "912": 5100000.0, "913": 5747000.0, "919": 2035850.0}

db = SessionLocal()
for m in reversed(E.TABLES):
    db.query(m).delete()
db.query(models.Setting).filter(models.Setting.key == "est_vo_seed_v1").delete()
for code, x in seed.items():
    db.add(E.EstProject(code=code, name="Plot " + code, contract_value=x["contract_with_vos"], status="Running"))
db.commit()

E.seed_variations(SessionLocal)
db.expire_all()
for code, (acc, absd) in SHEET.items():
    p = db.query(E.EstProject).filter_by(code=code).one()
    vs = db.query(E.EstVariation).filter_by(project_id=p.id).order_by(E.EstVariation.seq).all()
    a = round(sum(v.approved_amount for v in vs if v.status == "Approved"), 2)
    b = round(sum(v.absorbed_amount or 0 for v in vs), 2)
    ck(f"{code}: {len(vs)} lines, approved {a:,.2f} = sheet total", abs(a - acc) < 0.005, (a, acc))
    ck(f"{code}: absorbed {b:,.2f} = sheet total", abs(b - absd) < 0.005, (b, absd))
    ck(f"{code}: contract back to the original {ORIGINAL[code]:,.2f}", abs(p.contract_value - ORIGINAL[code]) < 0.005, p.contract_value)
    ck(f"{code}: original + approved = the contract as it stood", abs(p.contract_value + a - seed[code]["contract_with_vos"]) < 0.005)
    ck(f"{code}: numbered 1..n", [v.seq for v in vs] == list(range(1, len(vs) + 1)))

# Line by line spot checks against the sheets.
def one(code, ref, title_start=""):
    p = db.query(E.EstProject).filter_by(code=code).one()
    return next(v for v in db.query(E.EstVariation).filter_by(project_id=p.id) if v.ref == ref and v.title.startswith(title_start))
v = one("911", "V11")
ck("911 V11: submitted 175.79, revised and accepted -2,709.74 (credit kept as a minus)", (v.submitted_amount, v.revised_amount, v.approved_amount) == (175.79, -2709.74, -2709.74), (v.submitted_amount, v.approved_amount))
v = one("908", "CP01.B")
ck("908 CP01.B: omission of 2,000", v.kind == "Omission" and v.approved_amount == -2000 and v.status == "Approved")
v = one("908", "CP03")
ck("908 CP03 metal & glazing: rejected, revised 1,196,781 kept", v.status == "Rejected" and v.revised_amount == 1196781)
v = one("908", "V01")
ck("908 V01: absorbed 74,300, nothing added to the contract", v.status == "Absorbed" and v.absorbed_amount == 74300 and v.approved_amount == 0)
v = one("909", "V03", "Joinery")
ck("909 V03 Joinery: submitted 998,790.10, revised 945,894.40, accepted 907,500, dates", (v.submitted_amount, v.revised_amount, v.approved_amount, str(v.submitted), str(v.approved_on)) == (998790.1, 945894.4, 907500, "2026-07-31", "2026-09-15"), (v.submitted_amount, v.revised_amount, v.approved_amount, v.submitted, v.approved_on))
v = one("909", "OHP-2")
ck("909 OHP home automation: coordination 17,040, claimed 70%, not in the contract", v.kind == "Coordination" and v.submitted_amount == 17040 and v.status == "Claimed" and "70%" in v.notes)
v = one("913", "CP04")
ck("913 CP04 dewatering: accepted 1,187,910, per-day text kept in remarks", v.approved_amount == 1187910 and "41,900+Per day items" in v.notes and v.pc_ref == "Item VIII")
v = one("911", "V05", "Variation for Design Revision of Stair case - Option 2")
ck("911 V05 option 2: 106,000 from '*106,000.00', rejected", v.submitted_amount == 106000 and v.status == "Rejected")
v = one("911", "", "Shaft Opening")
ck("911 shaft opening absorbed 2,343.33 with its breakdown", v.absorbed_amount == 2343.33 and "Cleanout door 1,500.00" in v.notes and "MEP labour charge 500.00" in v.notes, v.notes)
v = one("908", "V03")
ck("908 V03 (no price yet): Identified, both description lines kept", v.status == "Identified" and "Block work for 908 bathroom" in v.notes)
v = one("912", "V03")
ck("912 V03 AC escalation: Identified, 'to prepare' kept", v.status == "Identified" and "to prepare" in v.notes.lower())

# The seed runs once only.
n0 = db.query(E.EstVariation).count()
db.query(models.Setting).filter(models.Setting.key == "est_vo_seed_v1").delete(); db.commit()
E.seed_variations(SessionLocal)
db.expire_all()
ck("seed again: a project that has variations is never touched", db.query(E.EstVariation).count() == n0 and
   abs(db.query(E.EstProject).filter_by(code="912").one().contract_value - 5100000) < 0.005)

# The page: bundle totals, then the Excel upload (preview, then save).
db.query(models.User).filter_by(username="vo_qs").delete(); db.commit()
db.add(models.User(username="vo_qs", full_name="Qs", role="office", hashed_password=auth.hash_password("qs1234567"),
                   permissions="settings,estimation_projects")); db.commit()
tok = c.post("/auth/login", data={"username": "vo_qs", "password": "qs1234567"}).json()["access_token"]
H = {"Authorization": "Bearer " + tok}
p912 = db.query(E.EstProject).filter_by(code="912").one()
b = c.get(f"/store/est/projects/{p912.id}", headers=H).json()
ck("912 page: revised contract = 5,996,316.50 again (original + approved VOs)", abs(b["summary"]["revised"] - 5996316.5) < 0.005 if "summary" in b else False, list(b.keys()))
ck("912 page: variations carry revised / absorbed / claimed in PC", all(k in b["variations"][0] for k in ("revised_amount", "absorbed_amount", "pc_ref")))

folder = sys.argv[1] if len(sys.argv) > 1 else ""
files = sorted(glob.glob(os.path.join(folder, "*91[19]*Variation_Log*.xlsx"))) if folder else []
if files:
    f = files[0]
    p = E.EstProject(code="T911", name="Upload test", contract_value=4912556.26, status="Running")
    db.add(p); db.commit()
    r = c.post(f"/store/est/projects/{p.id}/variations/import", headers=H, files={"file": (os.path.basename(f), open(f, "rb"))}, data={"save": "0"})
    j = r.json()
    ck("upload preview: lines and totals, nothing saved", r.status_code == 200 and j["rows"] > 0 and db.query(E.EstVariation).filter_by(project_id=p.id).count() == 0, j if r.status_code != 200 else "")
    r = c.post(f"/store/est/projects/{p.id}/variations/import", headers=H, files={"file": (os.path.basename(f), open(f, "rb"))}, data={"save": "1", "take_off_contract": "1"})
    j = r.json(); db.expire_all()
    ck("upload save: lines in, contract less the approved", r.status_code == 200 and db.query(E.EstVariation).filter_by(project_id=p.id).count() == j["rows"] and abs(j["contract"] - (4912556.26 - j["approved"])) < 0.005, j)
    r = c.post(f"/store/est/projects/{p.id}/variations/import", headers=H, files={"file": ("x.xlsx", b"not excel")}, data={"save": "0"})
    ck("a file that isn't a variation log: a plain message", r.status_code == 400 and "variation log" in r.json()["detail"])
    ex = c.get(f"/export/est/variations?pid={p.id}&format=excel&token=" + c.post("/auth/download-token", headers=H).json().get("token", ""))
    ck("Excel export of the log", ex.status_code == 200 and len(ex.content) > 1000, ex.status_code)
else:
    print("(no folder given - upload checks skipped)")

print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL PASS")
sys.exit(1 if fails else 0)

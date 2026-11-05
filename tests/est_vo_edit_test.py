"""Variations fully editable after they are made or brought in (5 Nov 2026) - the number too.

    cd app && DATABASE_URL=sqlite:////tmp/voed.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/est_vo_edit_test.py
"""
import os, sys
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main, models, auth, estimation as E, est_pcsheet as S
from database import SessionLocal, engine

main._add_missing_columns()
E.create_tables(engine)
c = TestClient(main.app); c.__enter__()
fails = []
def ck(name, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  -> {extra}"))
    if not ok: fails.append(name)

db = SessionLocal()
for m in reversed(E.TABLES):
    db.query(m).delete()
u = db.query(models.User).filter_by(username="vo_qs").first() or models.User(username="vo_qs")
u.full_name, u.role, u.permissions, u.hashed_password = "QS", "office", "settings,estimation_projects", auth.hash_password("qs1234567")
db.add(u); db.commit()
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "vo_qs", "password": "qs1234567"}).json()["access_token"]}
p = E.EstProject(code="991", name="Villa 991", status="Running"); db.add(p); db.commit(); P = p.id

ids = [c.post("/store/est/variations", json={"project_id": P, "title": t, "submitted_amount": a}, headers=H).json()["id"]
       for t, a in (("Extra lights", 1000), ("Pergola", 2000), ("Gate", 3000), ("Pool fence", 4000))]
def log():
    return {v["id"]: v for v in c.get(f"/store/est/projects/{P}", headers=H).json()["variations"]}
def patch(i, d):
    return c.patch(f"/store/est/variations/{i}", json=d, headers=H)

ck("made in order: V01..V04", [log()[i]["ref"] for i in ids] == ["V01", "V02", "V03", "V04"], [log()[i]["ref"] for i in ids])
r = patch(ids[1], {"title": "Pergola - timber", "kind": "Omission", "source": "Design change", "submitted_amount": 2500, "revised_amount": 2400,
                   "status": "Submitted", "notes": "corrected", "pc_ref": "PC 02"})
v = log()[ids[1]]
ck("every field edits (description, type, source, amounts, status, PC, remarks)", r.status_code == 200 and v["title"] == "Pergola - timber" and v["kind"] == "Omission"
   and v["source"] == "Design change" and abs(v["revised_amount"]) == 2400 and v["status"] == "Submitted" and v["notes"] == "corrected" and v["pc_ref"] == "PC 02", v)
ck("... and its number stays", v["ref"] == "V02")

r = patch(ids[0], {"ref": "VO-1A"})
L = log()
ck("the number can be typed (VO-1A)", r.status_code == 200 and L[ids[0]]["ref"] == "VO-1A" and L[ids[0]]["ref_typed"], r.text)
ck("... only that one changes", [L[i]["ref"] for i in ids[1:]] == ["V02", "V03", "V04"], [L[i]["ref"] for i in ids])

r = patch(ids[3], {"ref": "v 2"})
L = log()
ck("typed V02 (v 2) on V04: kept as V02, the one numbered V02 in order moves out of the way", r.status_code == 200 and L[ids[3]]["ref"] == "V02"
   and L[ids[1]]["ref"] != "V02" and len({L[i]["ref"] for i in ids}) == 4, [L[i]["ref"] for i in ids])
r = patch(ids[2], {"ref": "VO-1A"})
ck("one number on two lines is allowed (old logs do that: CP02 on three lines)", r.status_code == 200 and log()[ids[2]]["ref"] == "VO-1A", r.text)
patch(ids[2], {"ref": ""})

# a cancel renumbers the ones in order - the typed ones stay as typed
c.post(f"/store/est/variations/{ids[2]}/cancel", json={"note": "Withdrawn"}, headers=H)
L = log()
ck("after a cancel the typed numbers are kept", L[ids[0]]["ref"] == "VO-1A" and L[ids[3]]["ref"] == "V02", [L[i]["ref"] for i in ids])
ck("... and no number is used twice", len({L[i]["ref"] for i in ids if L[i]["status"] != "Cancelled"}) == 3, [L[i]["ref"] for i in ids])

r = patch(ids[0], {"ref": ""})
L = log()
ck("clearing the box puts it back to a number in order", r.status_code == 200 and not L[ids[0]]["ref_typed"] and L[ids[0]]["ref"].startswith("V")
   and L[ids[0]]["ref"] not in {L[i]["ref"] for i in ids[1:] if L[i]["status"] != "Cancelled"}, [L[i]["ref"] for i in ids])

# made with a number typed
n = c.post("/store/est/variations", json={"project_id": P, "title": "Late one", "ref": "CP-07"}, headers=H).json()["id"]
ck("a new variation can be given its own number", log()[n]["ref"] == "CP-07")

# the numbers sent to the consultant (QS log: CP01, CP02, V01, OHP-1) put back on a past log; new ones go on V..
p2 = E.EstProject(code="992", name="Villa 992", status="Running"); db.add(p2); db.commit()
past = [("Lift", "CP01"), ("VRF", "CP02"), ("Sliding door", "CP02"), ("Civil for lift", "V01"), ("Staircase", "V01"), ("Tiles", "V02"), ("Lift OHP", "OHP-1"), ("No QS no.", "")]
for i, (t, q) in enumerate(past, 1):
    db.add(E.EstVariation(project_id=p2.id, seq=i, ref=E.vref(i), title=t, qs_ref=q, status="Approved"))
db.commit()
pv = c.post(f"/store/est/projects/{p2.id}/variations/qs-numbers", json={"save": 0}, headers=H).json()
ck("preview: each line, its number now and the number sent", [x["will"] for x in pv["lines"]] == ["CP01", "CP02", "CP02", "V01", "V01", "V02", "OHP-1", "V08"]
   and pv["changes"] == 7, pv)
ck("... nothing changed yet", [v["ref"] for v in c.get(f"/store/est/projects/{p2.id}", headers=H).json()["variations"]][:2] == ["V01", "V02"])
ck("... the next new one will be V03", pv["next"] == "V03", pv["next"])
c.post(f"/store/est/projects/{p2.id}/variations/qs-numbers", json={"save": 1}, headers=H)
nw = c.post("/store/est/variations", json={"project_id": p2.id, "title": "New after go-live"}, headers=H).json()["id"]
L2 = c.get(f"/store/est/projects/{p2.id}", headers=H).json()["variations"]
ck("saved: the past log shows the numbers sent to the consultant", [v["ref"] for v in L2 if v["id"] != nw] == ["CP01", "CP02", "CP02", "V01", "V01", "V02", "OHP-1", "V08"], [v["ref"] for v in L2])
newv = next(v for v in L2 if v["id"] == nw)
ck("a new variation carries on: V03 (none of V01, V02 used twice), at the end of the log", newv["ref"] == "V03" and L2[-1]["id"] == nw, [v["ref"] for v in L2])
c.post(f"/store/est/variations/{L2[0]['id']}/cancel", json={"note": "Withdrawn"}, headers=H)
L2 = {v["id"]: v for v in c.get(f"/store/est/projects/{p2.id}", headers=H).json()["variations"]}
ck("a cancel on that log moves no other number", L2[nw]["ref"] == "V03" and L2[L2[nw]["id"]]["ref"] == "V03" and sorted(v["ref"] for v in L2.values() if v["status"] != "Cancelled")
   == sorted(["CP02", "CP02", "V01", "V01", "V02", "OHP-1", "V08", "V03"]), [v["ref"] for v in L2.values()])

# subcontract variations: the number edits too, and the PC sheet lines follow it
sid = c.post("/store/est/subs", json={"project_id": P, "name": "AL RAIDA", "scope": "MEP", "value": 100000}, headers=H).json()["id"]
a = c.post("/store/est/subvos", json={"sub_id": sid, "title": "Extra DB", "amount": 5000}, headers=H).json()["id"]
b = c.post("/store/est/subvos", json={"sub_id": sid, "title": "Extra pump", "amount": 7000}, headers=H).json()["id"]
db.add(S.EstSubItem(sub_id=sid, description="Extra DB", is_var=True, var_ref="V01", amount=5000)); db.commit()
r = c.patch(f"/store/est/subvos/{a}", json={"ref": "V05", "title": "Extra DB board", "amount": 5500}, headers=H)
db.expire_all()
x = db.get(E.EstSubVO, a)
ck("subcontract variation: number, description and amount edit", r.status_code == 200 and x.ref == "V05" and x.title == "Extra DB board" and x.amount == 5500, r.text)
ck("... the PC sheet line claimed against it follows the new number",
   db.query(S.EstSubItem).filter_by(sub_id=sid, description="Extra DB").first().var_ref == "V05")
r = c.patch(f"/store/est/subvos/{b}", json={"ref": "V05"}, headers=H)
ck("... two on one subcontract can't share a number", r.status_code == 400, r.text)

print("ALL PASS" if not fails else f"{len(fails)} FAILED")

"""Every variation is V01, V02 ... (client log and subcontracts), and old refs are renumbered once.

    cd app && DATABASE_URL=sqlite:////tmp/vnum.db INFINIA_NO_SCHED=1 python3 ../tests/est_vnum_test.py
"""
import os, sys
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main, models, estimation as E, est_pcsheet as S
from database import SessionLocal, engine

main._add_missing_columns()
E.create_tables(engine)
c = TestClient(main.app); c.__enter__()
fails = []
def ck(name, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  -> {extra}"))
    if not ok: fails.append(name)

tok = c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]
H = {"Authorization": "Bearer " + tok}
db = SessionLocal()
pid = c.post("/store/est/projects", json={"code": "VN1", "name": "V numbering test", "contract_value": 1000000}, headers=H).json().get("id")
if not pid:
    pid = db.query(E.EstProject).filter(E.EstProject.code == "VN1").first().id
db.query(E.EstVariation).filter(E.EstVariation.project_id == pid).delete(); db.commit()

ids = [c.post("/store/est/variations", json={"project_id": pid, "title": t, "ref": r}, headers=H).json()["id"]
       for t, r in [("Lift", "CP01"), ("Blockwork", ""), ("OHP for lift", "OHP-1")]]
refs = [db.get(E.EstVariation, i).ref for i in ids]
ck("new variations are V01, V02, V03 whatever is typed", refs == ["V01", "V02", "V03"], refs)
c.patch(f"/store/est/variations/{ids[0]}", json={"ref": "CP09", "title": "Lift (4 stops)"}, headers=H)
db.expire_all(); v = db.get(E.EstVariation, ids[0])
ck("editing keeps the number (title still changes)", v.ref == "V01" and v.title == "Lift (4 stops)", (v.ref, v.title))

# old data the way the QS log had it, then the one-time renumbering
for i, (r, sq) in enumerate([("CP02", 2), ("CP01", 1), ("V01", 3), ("OHP-1", 4), ("", 5)]):
    db.add(E.EstVariation(project_id=pid, seq=sq + 10, ref=r, title=f"old {i}", notes="n" if r == "CP02" else ""))
sid = c.post("/store/est/subs", json={"project_id": pid, "name": "VN SUB LLC", "scope": "Joinery", "value": 50000}, headers=H).json()["id"]
from datetime import date
db.add(E.EstSubVO(sub_id=sid, on_date=date(2026, 1, 5), ref="Var 01", title="Handrail", amount=100))
db.add(E.EstSubVO(sub_id=sid, on_date=date(2026, 2, 5), ref="Amendment", title="Extra doors", amount=200))
db.add(S.EstSubItem(sub_id=sid, description="Handrail", is_var=True, var_ref="Var 01", amount=100))
db.add(S.EstSubItem(sub_id=sid, description="LPO line", is_var=True, var_ref="LPO 9103", amount=50))
db.query(models.Setting).filter(models.Setting.key == "est_vo_vnumbers").delete()
db.commit()
E.renumber_variations(SessionLocal)
db.expire_all()
L = db.query(E.EstVariation).filter(E.EstVariation.project_id == pid).order_by(E.EstVariation.seq).all()
ck("renumbered V01..V08 in log order, no gaps or repeats", [v.ref for v in L] == [f"V{i:02d}" for i in range(1, 9)] and [v.seq for v in L] == list(range(1, 9)), [(v.seq, v.ref) for v in L])
old = {v.title: v for v in L}
ck("the old reference is kept in the remarks", old["old 0"].notes == "QS log ref. CP02 - n" and old["old 3"].notes.startswith("QS log ref. OHP-1"), old["old 0"].notes)
ck("CP01 (seq 1) comes before CP02 (seq 2)", old["old 1"].ref < old["old 0"].ref)
sv = db.query(E.EstSubVO).filter(E.EstSubVO.sub_id == sid).order_by(E.EstSubVO.on_date).all()
ck("subcontract variations V01, V02", [x.ref for x in sv] == ["V01", "V02"], [x.ref for x in sv])
ck("a word reference is kept on the description", sv[1].title == "Extra doors (Amendment)" and sv[0].title == "Handrail", [x.title for x in sv])
it = {x.description: x.var_ref for x in db.query(S.EstSubItem).filter(S.EstSubItem.sub_id == sid)}
ck("item lines follow (Var 01 -> V01), an LPO no. stays", it == {"Handrail": "V01", "LPO line": "LPO 9103"}, it)
E.renumber_variations(SessionLocal); db.expire_all()
ck("runs once only", db.get(E.EstSubVO, sv[0].id).ref == "V01" and old["old 0"].notes.count("QS log ref.") == 1)
r = c.post("/store/est/subvos", json={"sub_id": sid, "ref": "X", "title": "More", "amount": 10}, headers=H).json()
ck("a new subcontract variation is the next number (V03)", db.get(E.EstSubVO, r["id"]).ref == "V03")
c.delete(f"/store/est/subs/{sid}", headers=H)
print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL PASS")
sys.exit(1 if fails else 0)

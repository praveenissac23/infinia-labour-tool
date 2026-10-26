"""ESTIMATION DUMMY DATA: put in only where a project's part is empty, never over real data,
and taken out again exactly (MODE off).

    cd app && DATABASE_URL=sqlite:////tmp/estdummy.db INFINIA_NO_SCHED=1 python3 ../tests/est_dummy_test.py
"""
import os, sys
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main, models, estimation as E, est_pcsheet as S, est_dummy as D
from database import SessionLocal, engine

main._add_missing_columns()
E.create_tables(engine)
c = TestClient(main.app); c.__enter__()
fails = []
def ck(name, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  -> {extra}"))
    if not ok: fails.append(name)

db = SessionLocal()
# start from the live picture: 27 projects, variation logs on 6, approvals/finals on some, nothing else
D.clear(db)
for m in reversed(E.TABLES):
    if m is not E.EstProject and m is not E.EstVariation:
        db.query(m).delete()
db.query(models.Setting).filter(models.Setting.key.in_([D.DONE_KEY, D.V2_KEY])).delete(synchronize_session=False)
db.commit()
projects = db.query(E.EstProject).order_by(E.EstProject.code).all()
ck("27 projects to work on", len(projects) == 27, len(projects))
P1, P2 = projects[0], projects[1]
user = db.query(models.User).filter_by(username="admin").first()
E._seed_project(db, P1, user)                        # approvals + finals already set up on the first project (real)
real_sub = E.EstSub(project_id=P2.id, name="REAL SUB LLC", scope="Real work", value=1000)     # a real subcontract on the second
db.add(real_sub); db.commit()
before = {m.__tablename__: db.query(m).count() for m in E.TABLES}
real_appr = db.query(E.EstLog).filter_by(project_id=P1.id, kind="approval").count()
vars_before = db.query(E.EstVariation).count()
with_log = {x[0] for x in db.query(E.EstVariation.project_id).distinct().all()}
appr_before = sorted((a.id, a.status, a.sent) for a in db.query(E.EstLog).filter_by(project_id=P1.id, kind="approval"))
fin_before = sorted((f.id, f.st, f.sc) for f in db.query(E.EstFinal).filter_by(project_id=P1.id))

D.MODE = "on"
D.run(SessionLocal)
db.expire_all()
n = db.query(D.EstDummy).count()
ck("dummy rows put in and every one written down", n > 1000 and db.query(models.Setting).filter_by(key=D.DONE_KEY).first() is not None, n)
ck("nothing added to a project that already had subcontracts", db.query(E.EstSub).filter_by(project_id=P2.id).count() == 1)
ck("project 1's unfilled approvals list: no rows added, statuses filled", db.query(E.EstLog).filter_by(project_id=P1.id, kind="approval").count() == real_appr
   and db.query(E.EstLog).filter(E.EstLog.project_id == P1.id, E.EstLog.kind == "approval", E.EstLog.status == "Approved").count() > 0)
ck("project 1's empty finalization log filled", db.query(E.EstFinal).filter(E.EstFinal.project_id == P1.id, E.EstFinal.st == "✔").count() > 0)
ck("real variation logs untouched; the other projects got one", all(db.query(E.EstVariation).filter_by(project_id=pid).count() == db.query(E.EstVariation).filter_by(project_id=pid).count() for pid in with_log)
   and all(db.query(E.EstVariation).filter_by(project_id=p.id).count() == 9 for p in projects if p.id not in with_log))
ck("every other project got 3 dummy subcontracts", all(db.query(E.EstSub).filter_by(project_id=p.id).count() == 3 for p in projects[2:]))
ck("no 'dummy' written anywhere", not any("dummy" in (x.name or "").lower() for x in db.query(E.EstSub).all())
   and not any("dummy" in str(v).lower() for p_ in db.query(E.EstSubPC).all() for v in (p_.prep_by, p_.remarks, p_.paid_ref, p_.verified_by))
   and not any("dummy" in (b.description or "").lower() for b in db.query(E.EstBoq).all()))
st = {x[0] for x in db.query(E.EstSubPC.status).distinct().all()}
ck("certificates at every step (received, at site, prepared, MD approved, paid)", {"Received", "At site", "Prepared", "MD approved", "Paid"} <= st, st)
ck("item schedules, sheet lines and deductions in", db.query(S.EstSubItem).count() and db.query(S.EstPCLine).count() and db.query(S.EstPCDeduct).count())
ck("client PCs, BOQ, RFIs, submittals, approvals and finalization where empty",
   all(db.query(m).count() for m in (E.EstClientPC, E.EstBoq, E.EstFinal)) and {x[0] for x in db.query(E.EstLog.kind).distinct().all()} >= {"rfi", "submittal", "approval"})
# the money adds up on a dummy subcontract
sub = db.query(E.EstSub).filter(E.EstSub.name.like("Glassline%"), E.EstSub.project_id == projects[3].id).first()
pcs = db.query(E.EstSubPC).filter_by(sub_id=sub.id).order_by(E.EstSubPC.seq).all()
calc = E.chain(pcs, sub.adv_pct, sub.ret_pct, sub.vat_pct)
ck("dummy aluminium PC03: lines worked out, advance recovered, retention held", pcs[2].work_cum > 0 and pcs[2].var_cum > 0 and pcs[2].adv_rec_cum > 0 and pcs[2].ret_cum > 0, (pcs[2].work_cum, pcs[2].var_cum))
ck("paid certificates carry their payable as paid", all(abs(p.paid_amount - c_["payable"]) < .01 for p, c_ in zip(pcs, calc) if p.status == "Paid"))
# the pages open with the dummy data
tok = c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]
H = {"Authorization": "Bearer " + tok}
ok = all(c.get(f"/store/est/projects/{p.id}", headers=H).status_code == 200 for p in projects)
ck("every project opens", ok)
ck("the dashboard opens and the meta says dummy data is in", c.get("/store/est/dash", headers=H).status_code == 200 and c.get("/store/est/meta", headers=H).json()["dummy"] == n)
t = c.post("/auth/download-token", headers=H).json()["token"]
ck("a dummy certificate prints (preview and PDF)", c.get(f"/export/est/pc/{pcs[2].id}?token={t}").status_code == 200 and c.get(f"/export/est/pc/{pcs[2].id}?token={t}&format=pdf").content[:4] == b"%PDF")
# while testing, the user adds things on top of the dummy data
r = c.post("/store/est/subpcs", json={"sub_id": sub.id, "inv_ref": "USER TEST"}, headers=H)          # a new certificate on a dummy subcontract
user_pc = r.json()["id"]
fin = db.query(E.EstFinal).filter_by(project_id=P1.id).first()
c.patch(f"/store/est/finals/{fin.id}", json={"sub_id": sub.id}, headers=H)                        # a real finalization line linked to a dummy subcontract
c.post("/store/est/subs", json={"project_id": P2.id, "name": "USER TEST SUB", "value": 5}, headers=H)     # a subcontract the user makes himself
D.run(SessionLocal)
db.expire_all()
ck("running again while on adds nothing", db.query(D.EstDummy).count() == n)

D.MODE = "off"
D.run(SessionLocal)
db.expire_all()
after = {m.__tablename__: db.query(m).count() for m in E.TABLES}
ck("reverse: the register is empty and the switch reset", db.query(D.EstDummy).count() == 0 and db.query(models.Setting).filter_by(key=D.DONE_KEY).first() is None)
ck("reverse: no test subcontract left", db.query(E.EstSub).count() == 2)
ck("reverse: project 1's approvals and finalization back exactly as they were",
   sorted((a.id, a.status, a.sent) for a in db.query(E.EstLog).filter_by(project_id=P1.id, kind="approval")) == appr_before
   and sorted((f.id, f.st, f.sc) for f in db.query(E.EstFinal).filter_by(project_id=P1.id)) == fin_before)
ck("reverse: the certificate made on a dummy subcontract went with it", db.get(E.EstSubPC, user_pc) is None and db.query(S.EstPCLine).filter_by(pc_id=user_pc).count() == 0)
ck("reverse: the real finalization line stays, just unlinked", db.get(E.EstFinal, fin.id) is not None and db.get(E.EstFinal, fin.id).sub_id is None)
ck("reverse: the real subcontract and the one made while testing stay", db.query(E.EstSub).filter(E.EstSub.name.in_(["REAL SUB LLC", "USER TEST SUB"])).count() == 2)
for tbl in ("est_boq", "est_client_pcs", "est_sub_items", "est_pc_lines", "est_pc_deducts", "est_sub_vos"):
    ck(f"reverse: {tbl} back to what it was", after[tbl] == before[tbl], (before[tbl], after[tbl]))
ck("reverse: logs and finalization back to the real ones", after["est_logs"] == before["est_logs"] and after["est_finals"] == before["est_finals"], (before["est_logs"], after["est_logs"], before["est_finals"], after["est_finals"]))
ck("reverse: variation logs untouched", db.query(E.EstVariation).count() == vars_before)
D.MODE = "on"
D.run(SessionLocal)
db.expire_all()
ck("it can be put in again afterwards", db.query(D.EstDummy).count() > 1000)

# ---- the live case: the first round is in (with "(dummy)" in names), then this version starts ----
D.MODE = "off"; D.run(SessionLocal); D.MODE = "on"; D.run(SessionLocal); db.expire_all()
s0 = db.query(E.EstSub).filter(E.EstSub.name.like("Glassline%")).first(); s0.name = s0.name + " (dummy)"
p0 = db.query(E.EstSubPC).filter(E.EstSubPC.prep_by == "Arathi.S").first(); p0.prep_by = "QS (dummy)"
for v in db.query(E.EstVariation).filter(E.EstVariation.project_id.notin_(with_log)).all():
    db.delete(v)
db.query(D.EstDummy).filter_by(tbl="est_variations").delete()
db.query(models.Setting).filter_by(key=D.V2_KEY).delete(); db.commit()
D.run(SessionLocal); db.expire_all()
ck("upgrade: '(dummy)' taken out of names, people on the sign-offs", "dummy" not in db.get(E.EstSub, s0.id).name and db.get(E.EstSubPC, p0.id).prep_by == "Arathi.S")
ck("upgrade: the tabs still empty got filled (variation logs)", all(db.query(E.EstVariation).filter_by(project_id=p.id).count() == 9 for p in projects if p.id not in with_log))
D.MODE = "off"; D.run(SessionLocal); db.expire_all()
ck("and it all reverses", db.query(D.EstDummy).count() == 0 and db.query(E.EstVariation).count() == vars_before and db.query(E.EstSub).count() == 2)

print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL PASS")
sys.exit(1 if fails else 0)

"""Every Estimation figure worked out again from the raw rows, independently of the app's own code,
and compared with what the app shows - project page, dashboard, PC sheets, certificate documents.

    cd app && DATABASE_URL=sqlite:////tmp/audit.db INFINIA_NO_SCHED=1 python3 ../tests/est_math_audit.py

Uses whatever data is in the database (the dummy projects on a fresh one).
"""
import os, sys
from decimal import Decimal, ROUND_HALF_UP
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main, estimation as E, est_pcsheet as S
from database import SessionLocal, engine

main._add_missing_columns()
E.create_tables(engine)
c = TestClient(main.app); c.__enter__()
tok = c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]
H = {"Authorization": "Bearer " + tok}
db = SessionLocal()
fails, checks = [], [0]


def r2(v):
    return float(Decimal(str(v or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def same(name, a, b, tol=0.005):
    checks[0] += 1
    if abs((a or 0) - (b or 0)) > tol:
        fails.append(f"{name}: app {a} / worked out {b}")


def pc_chain(pcs, adv_pct, ret_pct, vat_pct, work_of):
    """The certificate sums, written out plainly."""
    out, prev, adv = {}, 0.0, 0.0
    for p in sorted(pcs, key=lambda p: (p.seq or 0, p.id)):
        adv = r2(adv + (p.adv_amount or 0))
        work, var = r2(work_of(p)), r2(getattr(p, "var_cum", 0) or 0)
        net = r2(work + var + (p.mos_cum or 0) + adv - (p.adv_rec_cum or 0) - (p.ret_cum or 0) + (p.ret_rel_cum or 0) - (p.other_cum or 0))
        this = r2(net - prev)
        vat = r2(this * (vat_pct or 0) / 100)
        out[p.id] = dict(work=work, var=var, adv=adv, net=net, prev=prev, this=this, vat=vat, payable=r2(this + vat))
        prev = net
    return out


def line_value(it, ln):
    if it.measure == "qty":
        stage = (ln.pct / 100) if ln.pct else 1
        return r2((ln.qty or 0) * (it.rate or 0) * stage - (ln.deduct or 0))
    return r2(((it.amount if it.amount else (it.qty or 0) * (it.rate or 0)) - (ln.deduct or 0)) * (ln.pct or 0) / 100)


dash = c.get("/store/est/dash", headers=H).json()
drow = {r["id"]: r for r in dash["projects"]}
tot = {k: 0.0 for k in dash["totals"]}
for p in db.query(E.EstProject).order_by(E.EstProject.code).all():
    b = c.get(f"/store/est/projects/{p.id}", headers=H).json()
    sm = b["summary"]
    tag = p.code
    # ---- subcontracts ----
    committed = cert = paid = to_pay = 0.0
    for sb in b["subs"]:
        s = db.get(E.EstSub, sb["id"])
        vos = db.query(E.EstSubVO).filter_by(sub_id=s.id).all()
        pcs = db.query(E.EstSubPC).filter_by(sub_id=s.id).all()
        revised = r2((s.value or 0) + sum(v.amount or 0 for v in vos) - (s.cancelled or 0))
        same(f"{tag} {s.name}: revised value", sb["revised"], revised)
        items = {i.id: i for i in db.query(S.EstSubItem).filter_by(sub_id=s.id).all()}
        ch = pc_chain(pcs, s.adv_pct, s.ret_pct, s.vat_pct, lambda x: x.work_cum)
        for pc in sb["pcs"]:
            w = ch[pc["id"]]
            for k, kk in (("work", "work"), ("var", "var"), ("adv_paid_cum", "adv"), ("net_cum", "net"), ("prev_net", "prev"), ("this", "this"), ("vat", "vat"), ("payable", "payable")):
                same(f"{tag} {s.name} PC{pc['seq']:02d} {k}", pc[k], w[kk])
            # lines -> work / variations to date (a certificate with lines)
            lines = db.query(S.EstPCLine).filter_by(pc_id=pc["id"]).all()
            row = db.get(E.EstSubPC, pc["id"])
            if lines and items:
                same(f"{tag} {s.name} PC{pc['seq']:02d} work = its lines", row.work_cum, r2(sum(line_value(items[l.item_id], l) for l in lines if l.item_id in items and not items[l.item_id].is_var)))
                same(f"{tag} {s.name} PC{pc['seq']:02d} variations = its lines", row.var_cum or 0, r2(sum(line_value(items[l.item_id], l) for l in lines if l.item_id in items and items[l.item_id].is_var)))
            # retention / recovery when worked out
            if row.ret_auto and row.status not in E.LOCKED_STATUS:
                same(f"{tag} {s.name} PC{pc['seq']:02d} retention {s.ret_pct}%", row.ret_cum, r2(((row.work_cum or 0) + (row.var_cum or 0)) * (s.ret_pct or 0) / 100))
            if row.adv_auto and s.adv_pct and row.status not in E.LOCKED_STATUS:
                same(f"{tag} {s.name} PC{pc['seq']:02d} advance recovered {s.adv_pct}%", row.adv_rec_cum, r2(min(w["adv"], (row.work_cum or 0) * s.adv_pct / 100)))
            # the printed certificate says the same
            if items:
                d = S.build_doc(db, row)
                same(f"{tag} {s.name} PC{pc['seq']:02d} doc: A = work + variations", d["A_total"], r2(w["work"] + w["var"]))
                same(f"{tag} {s.name} PC{pc['seq']:02d} doc: net due", d["net"], w["this"])
                same(f"{tag} {s.name} PC{pc['seq']:02d} doc: payable", d["payable"], w["payable"])
                same(f"{tag} {s.name} PC{pc['seq']:02d} doc: A + B - C + D + MOS - E = net", r2(d["A_total"] + sum(x[2] for x in d["B"]) - d["C_total"] + sum(x[2] for x in d["D"]) + d["mos"] - d["E_total"]), d["net"])
                same(f"{tag} {s.name} PC{pc['seq']:02d} doc: E = previous certificates", d["E_total"], w["prev"])
                same(f"{tag} {s.name} PC{pc['seq']:02d} doc: Appendix A total = A", r2(sum(bl["cum"] for bl in d["bills"])), d["A_total"])
        last = ch[max(ch, key=lambda k: (db.get(E.EstSubPC, k).seq or 0, k))] if ch else None
        s_cert = last["net"] if last else 0.0
        s_paid = r2(sum(x.paid_amount or 0 for x in pcs))
        s_vat = r2(sum(v["vat"] for v in ch.values()))
        same(f"{tag} {s.name}: certified to date", sb["certified"], s_cert)
        same(f"{tag} {s.name}: paid", sb["paid"], s_paid)
        same(f"{tag} {s.name}: to pay = certified + VAT - paid", sb["to_pay"], r2(s_cert + s_vat - s_paid))
        same(f"{tag} {s.name}: balance = revised - work done", sb["balance"], r2(revised - ((last["work"] + last["var"]) if last else 0)))
        if s.status != "Cancelled":
            committed += revised
        cert += s_cert; paid += s_paid; to_pay += r2(s_cert + s_vat - s_paid)
    same(f"{tag}: committed (subcontracts)", sm["committed"], r2(committed))
    same(f"{tag}: subcontractors certified", sm["sub_certified"], r2(cert))
    same(f"{tag}: subcontractors paid", sm["sub_paid"], r2(paid))
    same(f"{tag}: subcontractors to pay", sm["sub_to_pay"], r2(to_pay))
    # ---- client side ----
    vars_ = db.query(E.EstVariation).filter_by(project_id=p.id).all()
    appr = r2(sum(v.approved_amount or 0 for v in vars_ if v.status == "Approved"))
    same(f"{tag}: approved variations", sm["approved_vo"], appr)
    same(f"{tag}: revised contract = contract + approved VOs", sm["revised"], r2(sm["contract"] + appr))
    same(f"{tag}: margin = revised - committed", sm["margin"], r2(sm["contract"] + appr - committed))
    boq = db.query(E.EstBoq).filter_by(project_id=p.id).all()
    same(f"{tag}: BOQ value (in scope)", sm["boq_value"], r2(sum((r2(x.amount) if x.amount is not None else r2((x.qty or 0) * (x.rate or 0))) for x in boq if not (x.scope or ""))))
    cpcs = db.query(E.EstClientPC).filter_by(project_id=p.id).all()
    work_of = lambda x: (x.certified_cum if (x.certified_cum or 0) > 0 or x.status in ("Certified", "Invoiced", "Paid") else x.claimed_cum) or 0
    cc = pc_chain(cpcs, p.adv_pct, p.ret_pct, p.vat_pct, work_of)
    for x in b["clientpcs"]:
        w = cc[x["id"]]
        for k, kk in (("net_cum", "net"), ("this", "this"), ("vat", "vat"), ("payable", "payable")):
            same(f"{tag} client PC{x['seq']:02d} {k}", x[k], w[kk])
    # ---- dashboard line = project page ----
    for k in ("contract", "revised", "client_certified", "committed", "sub_certified", "sub_paid", "sub_to_pay", "approved_vo", "margin"):
        same(f"{tag}: dashboard {k} = project page", drow[p.id][k], sm[k])
    for k in tot:
        tot[k] += drow[p.id][k]
for k, v in tot.items():
    same(f"dashboard total {k} = sum of projects", dash["totals"][k], r2(v))
# dashboard: money with Accounts = the PCs with Accounts
wa = r2(sum(pc["payable"] for p in db.query(E.EstProject).all() for sb in c.get(f"/store/est/projects/{p.id}", headers=H).json()["subs"] for pc in sb["pcs"] if pc["status"] == "MD approved"))
same("dashboard: with Accounts amount", dash["kpi"]["with_accounts_amount"], wa)
# Accounts > Subcontractor payments lists the same payable per PC
pay = c.get("/store/est/payqueue", headers=H)
if pay.status_code == 200:
    rows = pay.json().get("rows", [])
    same("Accounts payments list is not empty", 1 if rows else 0, 1)
    allpc = {pc["id"]: pc for p in db.query(E.EstProject).all() for sb in c.get(f"/store/est/projects/{p.id}", headers=H).json()["subs"] for pc in sb["pcs"]}
    for r in rows:
        if r.get("pc_id") in allpc:
            same(f"Accounts payments: {r.get('sub')} PC{r.get('seq')} payable", r.get("payable"), allpc[r["pc_id"]]["payable"])
print(f"{checks[0]} figures checked")
for f in fails[:60]:
    print("FAIL", f)
print(f"\n{len(fails)} FAILED" if fails else "\nALL PASS")
sys.exit(1 if fails else 0)

"""ESTIMATION DUMMY DATA - test data for Estimation, fully reversible.

Put in once on start-up while MODE is "on": for every project, only where that
part is still EMPTY (real data is never touched) - subcontracts with their
variations, item schedules, payment certificates at every step (sheet lines,
deductions, sign-offs, paid ones), client payment certificates, BOQ & budget,
RFIs, submittals, NOCs & approvals and the finalization log. Not Trello, not
Trello. (Variation logs only on projects that have none.)

Every row made is written down in est_dummy (table, id). "Reverse estimation
dummy data" = MODE "off": on the next start-up exactly those rows are deleted
(and anything the app hung on them since, such as a certificate line or a
deduction typed on a dummy certificate), and nothing else.

Template lists the app made by itself and nobody has filled yet (NOCs & approvals
all "Not started", a finalization log with every box empty) get statuses too;
their old values are written down and put back on reverse.
"""
import json
from datetime import timedelta

from sqlalchemy import Column, Integer, String, Text

import estimation as E
import models
from database import Base

MODE = "off"         # "on" = put the dummy data in (once) · "off" = take it all out again  (off: Estimation went live 26 Oct 2026)
DONE_KEY = "est_dummy_done"
V2_KEY = "est_dummy_v2"      # second round: every tab filled, the word "dummy" gone


class EstDummy(Base):
    __tablename__ = "est_dummy"
    id = Column(Integer, primary_key=True)
    tbl = Column(String, nullable=False, index=True)
    row_id = Column(Integer, nullable=False)
    old = Column(Text, default="")      # set: a row that was there before - these values go back on reverse


E.TABLES.append(EstDummy)


def _models():
    import est_pcsheet as S
    return {"est_subs": E.EstSub, "est_sub_vos": E.EstSubVO, "est_sub_pcs": E.EstSubPC, "est_client_pcs": E.EstClientPC,
            "est_boq": E.EstBoq, "est_logs": E.EstLog, "est_finals": E.EstFinal, "est_sub_items": S.EstSubItem,
            "est_pc_lines": S.EstPCLine, "est_pc_deducts": S.EstPCDeduct, "est_variations": E.EstVariation}


def run(SessionLocal):
    db = SessionLocal()
    try:
        done = db.query(models.Setting).filter(models.Setting.key == DONE_KEY).first()
        v2 = db.query(models.Setting).filter(models.Setting.key == V2_KEY).first()
        if MODE == "on" and not (done and v2):
            if done:
                reword(db)              # the first round's rows: no "(dummy)" in names, people's names on sign-offs
            n = create(db)              # fills whatever is still empty (every tab)
            if not done:
                db.add(models.Setting(key=DONE_KEY, value=str(n)))
            db.add(models.Setting(key=V2_KEY, value=str(n)))
            db.commit()
            print(f"Estimation dummy data: {n} rows put in")
        elif MODE == "off" and (done or v2 or db.query(EstDummy).first()):
            n = clear(db)
            for x in (done, v2):
                if x:
                    db.delete(x)
            db.commit()
            print(f"Estimation dummy data: {n} rows taken out")
    except Exception:
        db.rollback()
        import traceback
        traceback.print_exc()
    finally:
        db.close()


def clear(db):
    import est_pcsheet as S
    M = _models()
    ids = {}
    for d in db.query(EstDummy).all():
        if d.old:                       # a row that was there before: its old values go back
            row = db.get(M[d.tbl], d.row_id)
            if row is not None:
                for k, v in json.loads(d.old).items():
                    if k in ("sent", "replied", "due", "on_date"):
                        v = E.date.fromisoformat(v) if v else None
                    setattr(row, k, v)
            continue
        ids.setdefault(d.tbl, set()).add(d.row_id)
    sub_ids, pc_ids = ids.get("est_subs", set()), ids.get("est_sub_pcs", set())
    # Anything hung on a dummy subcontract / certificate since goes with it.
    if sub_ids:
        pc_ids |= {p.id for p in db.query(E.EstSubPC.id).filter(E.EstSubPC.sub_id.in_(sub_ids)).all()}
    n = 0
    if pc_ids:
        n += db.query(S.EstPCLine).filter(S.EstPCLine.pc_id.in_(pc_ids)).delete(synchronize_session=False)
        n += db.query(S.EstPCDeduct).filter(S.EstPCDeduct.pc_id.in_(pc_ids)).delete(synchronize_session=False)
    if sub_ids:
        for m in (S.EstSubItem, S.EstPCDeduct, E.EstSubVO, E.EstSubPC):
            n += db.query(m).filter(m.sub_id.in_(sub_ids)).delete(synchronize_session=False)
        db.query(E.EstFinal).filter(E.EstFinal.sub_id.in_(sub_ids)).update({E.EstFinal.sub_id: None}, synchronize_session=False)
        db.query(E.EstVariation).filter(E.EstVariation.sub_id.in_(sub_ids)).update({E.EstVariation.sub_id: None}, synchronize_session=False)
    for tbl in ("est_pc_lines", "est_pc_deducts", "est_sub_items", "est_sub_vos", "est_sub_pcs", "est_subs", "est_client_pcs", "est_boq", "est_logs", "est_finals", "est_variations"):
        rid = ids.get(tbl)
        if rid:
            m = M[tbl]
            n += db.query(m).filter(m.id.in_(rid)).delete(synchronize_session=False)
    db.query(EstDummy).delete(synchronize_session=False)
    db.flush()
    return n


def reword(db):
    """Rows of the first round: names and remarks without "(dummy)", people on the sign-offs."""
    M = _models()
    names = {"QS (dummy)": "Arathi.S", "Anoop (dummy)": "Anoop.S", "Accounts (dummy)": "Shafeeq", "Manager (dummy)": "Praveen", "Site engineer (dummy)": "Febiyans Lucas"}
    for d in db.query(EstDummy).filter(EstDummy.old.is_(None) | (EstDummy.old == "")).all():
        row = db.get(M[d.tbl], d.row_id) if d.tbl in M else None
        if row is None:
            continue
        for col in row.__table__.columns:
            v = getattr(row, col.name)
            if isinstance(v, str) and "dummy" in v.lower():
                if v in names:
                    v = names[v]
                else:
                    v = v.replace(" (dummy)", "").replace("(dummy)", "").strip()
                setattr(row, col.name, v)
    db.flush()


# ---------------------------------------------------------------------------------------------

def create(db):
    import est_pcsheet as S
    made = []

    def add(row):
        db.add(row)
        db.flush()
        made.append((row.__tablename__, row.id, ""))
        return row

    def edit(row, **new):
        """Fill a row that was there before; its old values are kept for the reverse."""
        old = {k: (getattr(row, k).isoformat() if hasattr(getattr(row, k), "isoformat") else getattr(row, k)) for k in new}
        for k, v in new.items():
            setattr(row, k, v)
        made.append((row.__tablename__, row.id, json.dumps(old)))
    t = E.today()
    ago = lambda d: t - timedelta(days=d)
    projects = db.query(E.EstProject).order_by(E.EstProject.code).all()
    for i, p in enumerate(projects):
        base = p.contract_value or (2500000 + 150000 * (i % 7))
        has = lambda m: db.query(m).filter(m.project_id == p.id).first() is not None
        # ---------------- subcontracts, certificates, sheets ----------------
        if not db.query(E.EstSub).filter(E.EstSub.project_id == p.id).first():
            _subs(db, add, p, i, ago, S)
        # ---------------- client payment certificates ----------------
        if not has(E.EstClientPC):
            for n, (pct, st, d) in enumerate([(0.12, "Paid", 95), (0.27, "Certified", 40), (0.38, "Submitted", 8)], 1):
                cl = E.r2(base * pct)
                add(E.EstClientPC(project_id=p.id, seq=n, pc_type="Interim", period_to=ago(d + 5), submitted=ago(d), claimed_cum=cl,
                                  certified_cum=E.r2(cl * 0.97) if st != "Submitted" else 0, certified_on=ago(d - 10) if st != "Submitted" else None,
                                  status=st, invoice_no=f"IC/26/{p.code}/IPA{n:02d}" if st == "Paid" else "", remarks=""))
            db.flush()
            E._refill_client(db, p.id)
        # ---------------- BOQ & budget ----------------
        if not has(E.EstBoq):
            rows = [("SUBSTRUCTURE", "A1", "Excavation and disposal", "m3", 640, 28, 21, 100), ("SUBSTRUCTURE", "A2", "Blinding concrete C20", "m3", 42, 420, 355, 100),
                    ("SUBSTRUCTURE", "A3", "Reinforced concrete footings C40", "m3", 118, 980, 840, 100), ("SUPERSTRUCTURE", "B1", "RC columns C50", "m3", 64, 1150, 960, 85),
                    ("SUPERSTRUCTURE", "B2", "RC slabs C40", "m3", 310, 1020, 870, 70), ("SUPERSTRUCTURE", "B3", "Blockwork 200mm", "m2", 1850, 78, 61, 55),
                    ("FINISHES", "C1", "Internal plaster", "m2", 4200, 32, 24, 30), ("FINISHES", "C2", "Porcelain floor tiles", "m2", 960, 145, 118, 10),
                    ("FINISHES", "C3", "Painting - emulsion", "m2", 5100, 22, 15, 0), ("MEP", "D1", "Electrical works (provisional)", "LS", 1, 285000, 240000, 25),
                    ("MEP", "D2", "Plumbing & drainage", "LS", 1, 198000, 162000, 20), ("MEP", "D3", "HVAC - VRF system", "LS", 1, 410000, 352000, 5)]
            for n, (sec, code, desc, unit, qty, rate, cost, done) in enumerate(rows, 1):
                add(E.EstBoq(project_id=p.id, section=sec, code=code, description=desc, unit=unit, qty=qty, rate=rate, cost_rate=cost, done_pct=done, sort=n))
        # ---------------- RFIs and submittals ----------------
        if not db.query(E.EstLog).filter(E.EstLog.project_id == p.id, E.EstLog.kind == "rfi").first():
            for n, (title, party, sent, st, rep) in enumerate([("Clarification on lintel detail at staircase", "Consultant", 30, "Answered", 24),
                                                                ("Level of roof parapet vs. elevation drawing", "Consultant", 14, "Open", None),
                                                                ("Grade of waterproofing membrane for wet areas", "Consultant", 50, "Closed", 41)], 1):
                add(E.EstLog(project_id=p.id, kind="rfi", seq=n, title=title, party=party, discipline="Civil", ref=f"RFI-{n:03d}",
                             sent=ago(sent), due=ago(sent - 7), replied=ago(rep) if rep else None, status=st, sort=n))
        if not db.query(E.EstLog).filter(E.EstLog.project_id == p.id, E.EstLog.kind == "submittal").first():
            for n, (title, disc, sent, st, rep, spec, sup) in enumerate([("Porcelain tiles", "FINISHES", 35, "Approved", 25, "60x120 matt", "RAK Ceramics"),
                                                                         ("Aluminium & glazing", "FACADE", 20, "Revise & resubmit", 12, "Thermal break system", "Alumil"),
                                                                         ("VRF indoor units", "HVAC", 6, "Under review", None, "Ducted, 4.5 kW", "Daikin")], 1):
                add(E.EstLog(project_id=p.id, kind="submittal", seq=n, group=disc, item_no=str(n), title=title, spec=spec, supplier=sup, party="Consultant",
                             discipline=disc.title(), ref=f"SUB-{n:03d}", rev="0", sent=ago(sent), due=ago(sent - 10), replied=ago(rep) if rep else None, status=st, sort=n))
        # ---------------- NOCs & approvals, finalization log (only where not yet set up) ----------------
        appr = db.query(E.EstLog).filter(E.EstLog.project_id == p.id, E.EstLog.kind == "approval").order_by(E.EstLog.sort).all()
        if appr and all((a.status or "Not started") == "Not started" and not a.sent for a in appr):
            sts = ["Approved", "Approved", "Submitted", "Not started", "N/A"]
            for n, a in enumerate(appr):
                st = sts[(n + i) % len(sts)]
                edit(a, status=st, sent=ago(60 - n) if st in ("Approved", "Submitted") else None, replied=ago(40 - n) if st == "Approved" else None)
        fins = db.query(E.EstFinal).filter(E.EstFinal.project_id == p.id).order_by(E.EstFinal.sort).all()
        if fins and all(not (f.sc or f.rt or f.sd or f.ma or f.aa or f.st) for f in fins):
            marks = ["✔", "X", "✔", "", "N/A"]
            for n, f in enumerate(fins):
                m = marks[(n + i) % len(marks)]
                edit(f, sc="C" if m != "N/A" else "N/A", rt=m, sd=m, ma=m, aa=marks[(n + 1) % 5], st=m)
        if not db.query(E.EstVariation).filter(E.EstVariation.project_id == p.id).first():
            _variations(add, p, base, ago)
        if not appr:
            sts = ["Approved", "Approved", "Submitted", "Not started", "N/A"]
            for n, (g, title, party) in enumerate(E.APPROVALS):
                st = sts[(n + i) % len(sts)]
                add(E.EstLog(project_id=p.id, kind="approval", seq=n + 1, group=g, title=title, party=party, status=st, sort=n,
                             sent=ago(60 - n) if st in ("Approved", "Submitted") else None, replied=ago(40 - n) if st == "Approved" else None, note=""))
        if not fins:
            n = 0
            marks = ["✔", "X", "✔", "", "N/A"]
            for sec, items in E.FINAL_ITEMS.items():
                for it in items:
                    m = marks[(n + i) % len(marks)]
                    add(E.EstFinal(project_id=p.id, section=sec, item=it, sc="C" if m != "N/A" else "N/A", rt=m, sd=m, ma=m, aa=marks[(n + 1) % 5], st=m, note="", sort=n))
                    n += 1
    for tbl, rid, old in made:
        db.add(EstDummy(tbl=tbl, row_id=rid, old=old))
    db.flush()
    return len(made)


def _subs(db, add, p, i, ago, S):
    """Three subcontracts per project: aluminium & glazing (measured W x H), MEP (bills by %),
    manpower (quantities x rates, deductions) - each with certificates at different steps."""
    t = E.today()
    # --- 1. aluminium & glazing: measured, a variation, advance + two interims (paid, at site) ---
    s1 = add(E.EstSub(project_id=p.id, name="Glassline Aluminium Works LLC", scope="Aluminium & glazing", trade="Facade", kind="Subcontract",
                      agreement=f"IC/{p.code}/SCA/03/26", lpo="", value=186450.0, adv_pct=10, ret_pct=10, vat_pct=5, status="Active",
                      start_date=ago(150), agreement_date=ago(160), contract_type="Contract progressive payment",
                      pay_terms="10% advance against undated security cheque\n15% upon drawing submission & approval of sample\n40% against material delivery\n35% against installation\nRetention 10%"))
    add(E.EstSubVO(sub_id=s1.id, on_date=ago(70), ref="V01", title="Additional glass handrail at staircase", amount=12600.0))
    alu = [("1", "Sliding door 4 shutter (2 slide + 2 fix) slim system", "SD1", 1, "No", 36400.0), ("2", "Sliding door 2 shutter with top fixed panel", "SD2", 2, "No", 11650.0),
           ("3", "Curtain wall fixed glass - 6 panels", "W1", 1, "No", 35200.0), ("4", "Hinge window with top fixed glass", "W2", 4, "No", 1240.0),
           ("5", "Sky light - double laminated glass", "SKY", 1, "No", 2350.0), ("6", "Glass handrail 17.52 laminated with top rail", "GH", 28, "m", 860.0)]
    items1 = []
    for n, (no, d, ref, q, u, r) in enumerate(alu, 1):
        items1.append(add(S.EstSubItem(sub_id=s1.id, sort=n, no=no, description=d, ref=ref, qty=q, unit=u, rate=r, amount=E.r2(q * r), measure="size")))
    v1 = add(S.EstSubItem(sub_id=s1.id, sort=99, no="1", description="Additional glass handrail at staircase", ref="GH", qty=14.65, unit="m", rate=860, amount=12600.0,
                          measure="size", is_var=True, var_ref="V01"))
    pc_adv = add(E.EstSubPC(sub_id=s1.id, seq=1, pc_type="Advance", inv_ref="Advance", adv_amount=E.r2(186450 * .1), status="Prepared", certified_on=ago(140),
                            issued=ago(139), measured_on=ago(140), prep_by="Arathi.S", prep_on=ago(140), chk_by="Anoop.S", chk_on=ago(139)))
    pc2 = add(E.EstSubPC(sub_id=s1.id, seq=2, inv_ref="GL/INV/0412", inv_date=ago(62), inv_amount=78000, received=ago(60), to_site=ago(59), site_back=ago(55),
                         certified_on=ago(52), issued=ago(51), to_accounts=ago(50), status="Prepared", measured_on=ago(56),
                         verified_by="Febiyans Lucas", verified_on=ago(55), prep_by="Arathi.S", prep_on=ago(52), chk_by="Anoop.S", chk_on=ago(51),
                         rev_by="Shafeeq", rev_on=ago(50), app_by="Praveen", app_on=ago(50), remarks="Progressive payment"))
    for it, (w, h, pct) in zip(items1, [(5.1, 3.5, 40), (3.0, 3.0, 40), (4.5, 7.5, 55), (0.95, 1.2, 40), (0, 0, 0), (0, 0, 0)]):
        add(S.EstPCLine(pc_id=pc2.id, item_id=it.id, w=w, h=h, pct=pct))
    pc3 = add(E.EstSubPC(sub_id=s1.id, seq=3, inv_ref="GL/INV/0466", inv_date=ago(9), inv_amount=64000, received=ago(8), to_site=ago(7), status="At site",
                         measured_on=ago(9), remarks=""))
    for it, (w, h, pct, ded) in zip(items1, [(5.1, 3.5, 95, 1250), (3.0, 3.0, 95, 520), (4.5, 7.5, 100, 880), (0.95, 1.2, 100, 0), (1.5, 1.3, 100, 0), (26.4, 0, 60, 0)]):
        add(S.EstPCLine(pc_id=pc3.id, item_id=it.id, w=w, h=h, pct=pct, deduct=ded))
    add(S.EstPCLine(pc_id=pc3.id, item_id=v1.id, w=14.65, h=0, pct=95))
    S.refresh_sub(db, s1.id)
    _pay(db, s1.id, [pc_adv.id, pc2.id], ago)
    # --- 2. MEP: three bills by %, an amendment; advance paid, interim with Accounts ---
    s2 = add(E.EstSub(project_id=p.id, name="Powerline Electromechanical LLC", scope="MEP", trade="MEP", kind="Subcontract",
                      agreement=f"IC/{p.code}/SCA/05/26", value=612000.0, adv_pct=10, ret_pct=10, vat_pct=5, status="Active", start_date=ago(120),
                      agreement_date=ago(125), contract_type="Lump sum contract",
                      pay_terms="10% advance against undated company guarantee cheque\n100% progressive payment after certification with recovery of advance and retention\n10% retention"))
    add(E.EstSubVO(sub_id=s2.id, on_date=ago(45), ref="Amendment-01", title="Additional DB for future gym", amount=6500.0))
    bills = [("B1", "Electrical Works", [("1", "MDB, SMDBs and DBs with breakers", 64000), ("2", "Conduits, wiring and accessories", 58000), ("3", "Light fittings installation", 31000)]),
             ("B2", "Plumbing Works", [("1", "Water supply PPR pipes and fittings", 52000), ("2", "Drainage uPVC pipes and manholes", 61000), ("3", "Sanitary installation", 33000)]),
             ("B3", "Air Conditioning and Ventilation", [("1", "VRF outdoor and indoor units", 248000), ("2", "Copper piping and insulation", 41000), ("3", "Exhaust fans and ducting", 23000)])]
    it2 = []
    n = 0
    for bill, title, rows in bills:
        for no, d, amt in rows:
            n += 1
            it2.append(add(S.EstSubItem(sub_id=s2.id, sort=n, bill=bill, bill_title=title, no=no, description=d, qty=1, unit="LS", amount=amt, measure="pct")))
    v2 = add(S.EstSubItem(sub_id=s2.id, sort=99, no="1", description="Additional DB for future gym", qty=1, unit="LS", amount=6500, measure="pct", is_var=True, var_ref="Amendment-01"))
    pa = add(E.EstSubPC(sub_id=s2.id, seq=1, pc_type="Advance", inv_ref="Advance", adv_amount=61200.0, status="Prepared", certified_on=ago(115), issued=ago(114),
                        prep_by="Arathi.S", prep_on=ago(115)))
    pb = add(E.EstSubPC(sub_id=s2.id, seq=2, inv_ref="PL/2026/118", inv_date=ago(20), inv_amount=52000, received=ago(19), to_site=ago(18), site_back=ago(16),
                        certified_on=ago(14), issued=ago(13), to_accounts=ago(12), status="MD approved", measured_on=ago(17), verified_by="Febiyans Lucas",
                        verified_on=ago(16), prep_by="Arathi.S", prep_on=ago(14), chk_by="Anoop.S", chk_on=ago(13), rev_by="Shafeeq", rev_on=ago(12)))
    for it, pct in zip(it2, [35, 20, 0, 25, 30, 0, 10, 15, 0]):
        add(S.EstPCLine(pc_id=pb.id, item_id=it.id, pct=pct))
    add(S.EstPCLine(pc_id=pb.id, item_id=v2.id, pct=100))
    S.refresh_sub(db, s2.id)
    _pay(db, s2.id, [pa.id], ago)
    # --- 3. manpower: quantities x rates, deductions, one paid and one just received ---
    s3 = add(E.EstSub(project_id=p.id, name="Al Noor Technical Manpower", scope="Manpower - steel & shuttering", trade="Civil", kind="Manpower",
                      agreement=f"IC/{p.code}/SCA/01/26", value=0, ret_pct=10, vat_pct=5, status="Active", start_date=ago(100), agreement_date=ago(105),
                      contract_type="Unit rate re-measurement contract", pay_terms="Progressive payment against invoice as approved by the Project Engineer\nRetention 10%"))
    mp = [("A", "Substructure", [("1", "Footings and strap beams", 235), ("2", "Tie beams and stub columns", 235), ("3", "Grade slab", 120)]),
          ("B", "Superstructure", [("4", "Columns", 235), ("5", "Slab - first floor", 235), ("6", "Slab - roof", 235)])]
    it3 = []
    n = 0
    for bill, title, rows in mp:
        for no, d, rate in rows:
            n += 1
            it3.append(add(S.EstSubItem(sub_id=s3.id, sort=n, bill=bill, bill_title=title, no=no, description=d, unit="m3", rate=rate, measure="qty")))
    q1 = add(E.EstSubPC(sub_id=s3.id, seq=1, inv_ref="ANT/07", inv_date=ago(48), inv_amount=31000, received=ago(47), to_site=ago(46), site_back=ago(44),
                        certified_on=ago(42), issued=ago(41), to_accounts=ago(40), status="Prepared", measured_on=ago(45), verified_by="Febiyans Lucas",
                        verified_on=ago(44), prep_by="Arathi.S", prep_on=ago(42), app_by="Praveen", app_on=ago(40)))
    for it, q in zip(it3, [98, 31, 0, 0, 0, 0]):
        add(S.EstPCLine(pc_id=q1.id, item_id=it.id, qty=q, claimed_qty=q + 2))
    add(S.EstPCDeduct(sub_id=s3.id, pc_id=q1.id, cat="Manpower", on_date=ago(50), description="Labour supplied by Infinia - 6 nos x 2 days", qty=12, unit="No", rate=137, amount=1644))
    q2 = add(E.EstSubPC(sub_id=s3.id, seq=2, inv_ref="ANT/09", inv_date=ago(3), inv_amount=38500, received=ago(2), status="Received", remarks=""))
    for it, q in zip(it3, [118, 36, 22, 40, 0, 0]):
        add(S.EstPCLine(pc_id=q2.id, item_id=it.id, qty=q, claimed_qty=q))
    add(S.EstPCDeduct(sub_id=s3.id, pc_id=q2.id, cat="Plant & Equipment", on_date=ago(10), description="Jack hammer - 4 days", qty=4, unit="Day", rate=88, amount=352))
    add(S.EstPCDeduct(sub_id=s3.id, pc_id=q2.id, cat="Other", on_date=ago(6), description="Safety violation - no harness", amount=300, counted=True))
    S.refresh_sub(db, s3.id)        # PC01 left certified, waiting to be issued


def _pay(db, sid, pc_ids, ago):
    """Mark these certificates paid at their payable amount (after the chain is worked out)."""
    pcs = db.query(E.EstSubPC).filter(E.EstSubPC.sub_id == sid).all()
    s = db.query(E.EstSub).get(sid)
    calc = {c["id"]: c for c in E.chain(pcs, s.adv_pct, s.ret_pct, s.vat_pct)}
    for p in pcs:
        if p.id in pc_ids:
            p.status = "Paid"
            p.paid_amount = calc[p.id]["payable"]
            p.paid_on = (p.issued or ago(30)) + timedelta(days=12)
            p.paid_ref = f"CHQ {100000 + p.id}"
            p.to_accounts = p.to_accounts or p.issued
    db.flush()


def _variations(add, p, base, ago):
    """A variation log: approved, submitted, revised, rejected, absorbed, one to price and a coordination line."""
    k = base / 3000000.0
    rows = [("CP01", "Supply & installation of lift (4 stops)", "Addition", 124000, 0, 124000, 0, 160, 150, "Item V", "Approved", "Accepted"),
            ("CP02", "Change of DX system to VRF (Daikin) with Reiri home control", "Addition", 98500, 91000, 91000, 0, 120, 95, "Item VI", "Approved", "Accepted after negotiation"),
            ("V01", "Additional blockwork and plaster - revised maid room layout", "Addition", 18650, 0, 18650, 0, 90, 82, "V01", "Approved", "Accepted by client"),
            ("V02", "Omission of external pergola", "Omission", 22000, 0, 22000, 0, 80, 70, "V02", "Approved", "Deducted in IPA"),
            ("V03", "Material price escalation - steel and concrete", "Addition", 146000, 132500, 0, 0, 25, None, "", "Submitted", "Under management review"),
            ("V04", "Feature wall cladding at entrance", "Addition", 38400, 0, 0, 0, 60, None, "", "Rejected", "Rejected by client"),
            ("V05", "Re-routing of drainage due to site condition", "Addition", 0, 0, 0, 12750, None, None, "", "Absorbed", "Absorbed - site condition"),
            ("V06", "Swimming pool shell and filtration", "Addition", 0, 0, 0, 0, None, None, "", "Identified", "To prepare")]
    for n, (ref, title, kind, sub, rev, app, absd, sd, ad, pc, st, note) in enumerate(rows, 1):
        f = lambda v: E.r2(v * k)
        sign = -1 if kind == "Omission" else 1
        add(E.EstVariation(project_id=p.id, seq=n, ref=E.vref(n), title=title, kind=kind, source="Client instruction", submitted=ago(sd) if sd else None,
                           on_date=ago(sd) if sd else ago(5), submitted_amount=sign * f(sub), revised_amount=sign * f(rev), approved_amount=sign * f(app),
                           approved_on=ago(ad) if ad else None, absorbed_amount=f(absd), pc_ref=pc, status=st, notes=note))
    add(E.EstVariation(project_id=p.id, seq=len(rows) + 1, ref=E.vref(len(rows) + 1), title="For lift works - coordination and builders' work", kind="Coordination",
                       source="Coordination & attendance", submitted_amount=E.r2(12300 * k), status="Claimed", notes="Claimed 90%"))

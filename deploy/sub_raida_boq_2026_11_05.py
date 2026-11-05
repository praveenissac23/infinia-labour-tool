"""914 and 915 - Al Raida Electromechanical (MEP subcontracts): item schedules replaced by Raida's final BOQs (5 Nov 2026).

914: RAIDA_914_MEP_BOQ.xls - 568,800 (HVAC 243,000 / Plumbing 153,000 / Electrical 172,800); Raida moved prices between
     lines since the morning file, same total. Anoop: final.
915: RAIDA_915_MEP_BOQ.xls (Anoop, 17:05) - 580,500 (HVAC 243,000 / Plumbing 153,000 / Electrical 184,500) = the
     subcontract value; the 116,100 advance (20%) stands.

Read by the app's own BOQ reader (every bill = its summary sheet); the lines are in deploy/raida_91x_boq_final.json.
Work typed on a line is carried to the same line; a paid PC with work on it, or a BOQ that is not the subcontract value,
stops it. The PC 02s are not entered here. Run twice = the same result.

    cd ~/infinia-labour-tool && venv/bin/python deploy/sub_raida_boq_2026_11_05.py            (dry run - shows it)
    cd ~/infinia-labour-tool && venv/bin/python deploy/sub_raida_boq_2026_11_05.py --apply    (writes it)
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, HERE)
FILES = (("914", "raida_914_boq_final.json"), ("915", "raida_915_boq_final.json"))


def find_url():
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    from clear_test_returns import _find_database_url
    return _find_database_url()


def norm(t):
    return re.sub(r"\s+", " ", (t or "").strip().lower())


def one(db, E, S, code, r, apply):
    sub = [x for x in db.query(E.EstSub).filter(E.EstSub.name.ilike("%AL RAIDA%")).all()
           if (db.get(E.EstProject, x.project_id).code or "") == code]
    if len(sub) != 1:
        sys.exit(f"Expected one {code} Al Raida subcontract, found {len(sub)} - nothing done.")
    sub = sub[0]
    have = db.query(S.EstSubItem).filter(S.EstSubItem.sub_id == sub.id, S.EstSubItem.is_var == False).order_by(S.EstSubItem.sort, S.EstSubItem.id).all()  # noqa: E712
    pcs = db.query(E.EstSubPC).filter(E.EstSubPC.sub_id == sub.id).order_by(E.EstSubPC.seq).all()
    lines = db.query(S.EstPCLine).filter(S.EstPCLine.pc_id.in_([p.id for p in pcs] or [-1]), S.EstPCLine.item_id.in_([i.id for i in have] or [-1])).all()
    work = [l for l in lines if (l.pct or 0) or (l.qty or 0) or (l.w or 0) or (l.deduct or 0) or (l.remark or "").strip()]
    print(f"\n===== {code} {sub.name} - subcontract value {sub.value:,.2f}")
    print(f"Now:  {len(have)} schedule lines, {sum(i.amount or 0 for i in have):,.2f}")
    print(f"In:   {len(r['lines'])} lines from {r['file']}, {r['total']:,.2f}")
    for s in r["sheets"]:
        print(f"      {s['bill']:<12}{s['lines']:>4} lines {s['contract']:>14,.2f}")
    if abs((sub.value or 0) - r["total"]) > 0.01:
        sys.exit(f"{code}: the BOQ ({r['total']:,.2f}) is not the subcontract value ({sub.value:,.2f}) - nothing done.")
    print("      = the subcontract value")
    for p in pcs:
        if (p.paid_on or (p.status or "") == "Paid") and any(l.pc_id == p.id for l in work):
            sys.exit(f"{code}: PC {p.seq:02d} is paid and has work on its lines - nothing done.")
    carry = []
    for l in work:
        it = next((i for i in have if i.id == l.item_id), None)
        new = [x for x in r["lines"] if it and norm(x["description"])[:120] == norm(it.description)[:120] and abs((x["amount"] or 0) - (it.amount or 0)) < 0.01]
        pc = next(p for p in pcs if p.id == l.pc_id)
        print(f"Work on PC {pc.seq:02d}: {l.pct or 0:g}% / qty {l.qty or 0:g} on '{(it.description if it else '?')[:60]}' -> "
              + ("carried to the same line" if len(new) == 1 else "NO MATCH"))
        if len(new) != 1:
            sys.exit(f"{code}: a line with work on it has no single match in the new schedule - nothing done.")
        carry.append((l, new[0]))
    print(f"PCs: " + (", ".join(f"PC {p.seq:02d} {p.pc_type or ''} {p.status}" for p in pcs) or "none") + f"; work typed on lines: {len(work)}")
    if not apply:
        return
    db.query(S.EstPCLine).filter(S.EstPCLine.id.in_([l.id for l in lines] or [-1])).delete(synchronize_session=False)
    for i in have:
        db.delete(i)
    db.flush()
    made = []
    for n, x in enumerate(r["lines"], 1):
        it = S.EstSubItem(sub_id=sub.id, sort=n, bill=x["bill"][:20], bill_title=x["bill_title"][:120], section=x["section"][:200],
                          no=x["no"][:20], description=x["description"], ref=(x.get("words") or "")[:120], qty=x["qty"], unit=x["unit"][:20],
                          rate=x["rate"], amount=x["amount"], measure=x["measure"], is_var=False)
        db.add(it)
        made.append((x, it))
    db.flush()
    for l, x in carry:
        it = next(i for xx, i in made if xx is x)
        db.add(S.EstPCLine(pc_id=l.pc_id, item_id=it.id, pct=l.pct, qty=l.qty, claimed_qty=l.claimed_qty, w=l.w, h=l.h,
                           deduct=l.deduct, remark=l.remark))
    db.flush()
    S.refresh_sub(db, sub.id)
    print(f"Done: {len(made)} lines, {sum(i.amount or 0 for x, i in made):,.2f}.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    url = find_url()
    if not url:
        sys.exit("Could not find DATABASE_URL.")
    os.environ["DATABASE_URL"] = url
    os.environ.setdefault("INFINIA_NO_PUSH", "1")
    os.environ.setdefault("INFINIA_NO_SCHED", "1")
    import main as M  # noqa: F401 - the tables and columns
    import estimation as E
    import est_pcsheet as S
    from database import SessionLocal
    db = SessionLocal()
    try:
        for code, jf in FILES:
            one(db, E, S, code, json.load(open(os.path.join(HERE, jf))), a.apply)
        if a.apply:
            db.commit()
            print("\nWritten. Open the subcontracts to see the schedules.")
        else:
            print("\nDry run - nothing written. Run again with --apply.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

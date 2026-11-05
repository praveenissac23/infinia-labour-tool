"""915 - Al Raida Electromechanical Services LLC (MEP subcontract): item schedule from their priced BOQ (5 Nov 2026).

915's schedule has only three lump sums (Complete Electrical 172,800 / Plumbing 153,000 / VRF 243,000 = 568,800) - 914's
figures. It is replaced by the 49 lines of RAIDA_R2_ae5549_BOQ_MEP_VE208.xls read by the new reader (in
sub_915_raida_mep.json beside this script): HVAC 234,900, Electrical 184,500, Plumbing 153,000 = 572,400, every bill
page equal to its own subtotal. No certificate has work on the lump sums. The subcontract value (568,800) is NOT
changed: the BOQ's own collection says 580,500 (it counts HVAC page 5 twice, 8,100) and its lines make 572,400 - the
contracts team decides the value. Run twice = the same result.

    cd ~/infinia-labour-tool && venv/bin/python deploy/sub_915_raida_2026_11_05.py            (dry run - shows it)
    cd ~/infinia-labour-tool && venv/bin/python deploy/sub_915_raida_2026_11_05.py --apply    (writes it)
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, HERE)


def find_url():
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    from clear_test_returns import _find_database_url
    return _find_database_url()


def norm(t):
    return re.sub(r"\s+", " ", (t or "").strip().lower())


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
    r = json.load(open(os.path.join(HERE, "sub_915_raida_mep.json")))
    db = SessionLocal()
    try:
        sub = db.query(E.EstSub).filter(E.EstSub.name.ilike("%AL RAIDA%")).all()
        sub = [x for x in sub if (db.get(E.EstProject, x.project_id).code or "") == "915"]
        if len(sub) != 1:
            sys.exit(f"Expected one 915 Al Raida subcontract, found {len(sub)} - nothing done.")
        sub = sub[0]
        have = db.query(S.EstSubItem).filter(S.EstSubItem.sub_id == sub.id).order_by(S.EstSubItem.sort, S.EstSubItem.id).all()
        pcs = db.query(E.EstSubPC).filter(E.EstSubPC.sub_id == sub.id).order_by(E.EstSubPC.seq).all()
        lines = db.query(S.EstPCLine).filter(S.EstPCLine.pc_id.in_([p.id for p in pcs] or [-1])).all()
        work = [l for l in lines if (l.pct or 0) or (l.qty or 0) or (l.w or 0) or (l.deduct or 0) or (l.remark or "").strip()]
        print(f"915 {sub.name} - subcontract value {sub.value:,.2f}")
        print(f"Now:  {len(have)} schedule lines, {sum(i.amount or 0 for i in have):,.2f}")
        print(f"In:   {len(r['lines'])} lines from {r['file']}, {r['total']:,.2f}")
        for s in r["sheets"]:
            print(f"      {s['bill']:<12}{s['lines']:>4} lines {s['contract']:>14,.2f}")
        print(f"      value - lines = {sub.value - r['total']:,.2f}  (the BOQ's own collection says 580,500: HVAC page 5 counted twice)\n")
        for p in pcs:
            if (p.paid_on or (p.status or "") == "Paid") and any(l.pc_id == p.id for l in work):
                sys.exit(f"PC {p.seq:02d} is paid and has work on its lines - nothing done.")
        carry = []
        for l in work:
            it = next((i for i in have if i.id == l.item_id), None)
            new = [x for x in r["lines"] if it and norm(x["description"])[:120] == norm(it.description)[:120] and abs((x["amount"] or 0) - (it.amount or 0)) < 0.01]
            pc = next(p for p in pcs if p.id == l.pc_id)
            print(f"Work on PC {pc.seq:02d}: {l.pct or 0:g}% / qty {l.qty or 0:g} on '{(it.description if it else '?')[:60]}' -> "
                  + (f"carried to the same line ({new[0]['amount']:,.2f})" if len(new) == 1 else "NO MATCH"))
            if len(new) != 1:
                sys.exit("A line with work on it has no single match in the new schedule - nothing done.")
            carry.append((l, new[0]))
        if not a.apply:
            print("\nDry run - nothing written. Run again with --apply.")
            return
        db.query(S.EstPCLine).filter(S.EstPCLine.pc_id.in_([p.id for p in pcs] or [-1])).delete(synchronize_session=False)
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
        db.commit()
        tot = sum(i.amount or 0 for x, i in made)
        print(f"\nDone: {len(made)} lines, {tot:,.2f}. Open the subcontract to see the schedule.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

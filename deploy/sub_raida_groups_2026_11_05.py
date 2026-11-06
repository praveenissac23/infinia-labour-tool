"""914 and 915 - Al Raida Electromechanical (MEP): the items priced together as one lump sum (a bracket in the BOQ) put
back under their group (5 Nov 2026). Run after deploy/sub_raida_boq_2026_11_05.py and deploy/pc_raida_pc02_2026_11_05.py.

The schedules went in this afternoon with the lump sum on one item and the other items of the bracket left out (Plumbing
"Sanitary Fittings & Accessories": "Clean Out, CO 12,000" - Catch Basin, Floor Drain ... missing). The same files are read
again by the new reader: each group is one line with its lump sum (certified by %), its items listed under it at nil.
914: 215 lines - 16 groups with 115 items; 915: 217 lines - 16 groups with 118 items. Money unchanged: 568,800 / 580,500.

The certificates' lines are moved to the line that now carries their money (same bill, same amount, the same item or its
group) - nothing is typed again. Before anything is written, every certificate's work to date, every bill's total and
every line's certified figure are checked to be exactly what they were; any difference stops it with nothing changed.
Run twice = the same result.

    cd ~/infinia-labour-tool && venv/bin/python deploy/sub_raida_groups_2026_11_05.py            (dry run - shows it)
    cd ~/infinia-labour-tool && venv/bin/python deploy/sub_raida_groups_2026_11_05.py --apply    (writes it)
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, HERE)
FILES = (("914", "raida_914_boq_groups.json"), ("915", "raida_915_boq_groups.json"))


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
    plines = db.query(S.EstPCLine).filter(S.EstPCLine.pc_id.in_([p.id for p in pcs] or [-1]), S.EstPCLine.item_id.in_([i.id for i in have] or [-1])).all()
    print(f"\n===== {code} {sub.name} - value {sub.value:,.2f}")
    print(f"Now:  {len(have)} lines, {sum(i.amount or 0 for i in have):,.2f}; groups {sum(1 for i in have if (i.grp or '') == 'head')}")
    new = r["lines"]
    print(f"In:   {len(new)} lines from {r['file']}, {r['total']:,.2f} - {sum(1 for x in new if x['grp'] == 'head')} groups, "
          f"{sum(1 for x in new if x['grp'] == 'in')} items listed under them")
    if abs(r["total"] - (sub.value or 0)) > 0.01:
        sys.exit(f"{code}: the file ({r['total']:,.2f}) is not the subcontract value - nothing done.")
    for s in r["sheets"]:
        rw = s.get("rows") or {}
        print(f"      {s['bill']:<12}{s['contract']:>14,.2f}   rows in the file {rw.get('rows')}, accounted {rw.get('accounted')} "
              f"(lines {rw.get('lines')}, in groups {rw.get('members')}, headings {rw.get('headings')}, review {rw.get('review')})")
        if rw and rw.get("rows") != rw.get("accounted"):
            sys.exit(f"{code}: {s['bill']} - not every row of the file is accounted for - nothing done.")
    if any((i.grp or "") for i in have) and len(have) == len(new):
        print("Already in groups - nothing to do.")
        return
    # where each certificate line goes: the line now carrying its money - same bill, same amount; the same item, or
    # the group it is listed in
    members_of, h = {}, None
    for k, x in enumerate(new):
        if x["grp"] == "head":
            h = k
            members_of[k] = []
        elif x["grp"] == "in" and h is not None:
            members_of[h].append(norm(x["description"]))
        else:
            h = None
    priced = [k for k, x in enumerate(new) if x["grp"] != "in"]
    target, drop = {}, set()
    item_of = {i.id: i for i in have}
    nothing = lambda iid: all(abs(S.line_amount(item_of[iid], pl)) < 0.005 and not (pl.pct or 0) and not (pl.qty or 0)
                              for pl in plines if pl.item_id == iid)
    alike = lambda d, k: (norm(new[k]["description"]) == d or norm(new[k]["description"]).startswith(d[:60])
                          or d.startswith(norm(new[k]["description"])[:60]))
    for it in sorted({pl.item_id: item_of[pl.item_id] for pl in plines}.values(), key=lambda i: nothing(i.id)):
        d = norm(it.description)
        same = [k for k in priced if new[k]["bill"] == it.bill and abs((new[k]["amount"] or 0) - (it.amount or 0)) < 0.01]
        if len(same) > 1:
            same = [k for k in same if alike(d, k) or d in members_of.get(k, [])]
        if len(same) != 1 and nothing(it.id):
            # a line with nothing certified on it (an item at nil, now listed under its group): its own line if it
            # is there, else it is not needed - it carried no money on any certificate
            same = [k for k, x in enumerate(new) if x["bill"] == it.bill and alike(d, k) and k not in target.values()]
            if len(same) != 1:
                drop.add(it.id)
                print(f"  {it.bill:<11}{it.description[:44]:<45}{it.amount:>11,.2f} -> nothing certified on it: its blank certificate line taken off")
                continue
        if len(same) != 1:
            sys.exit(f"{code}: '{it.description[:60]}' ({it.amount:,.2f}) has {len(same)} matching lines in the new schedule - nothing done.")
        if same[0] in target.values() and nothing(it.id):
            drop.add(it.id)
            continue
        target[it.id] = same[0]
        x = new[same[0]]
        print(f"  {it.bill:<11}{it.description[:44]:<45}{it.amount:>11,.2f} -> {'GROUP ' if x['grp'] == 'head' else ''}{x['description'][:60]}")
    if len(set(target.values())) != len(target):
        sys.exit(f"{code}: two certificate lines would land on one line - nothing done.")
    # the figures before: each certificate's work to date, each line's certified figure, each bill
    before_pc = {p.id: round(p.work_cum or 0, 2) for p in pcs}
    before_ln = {(pl.pc_id, pl.item_id): S.line_amount(next(i for i in have if i.id == pl.item_id), pl) for pl in plines}
    bills = lambda rows: {b: round(sum((x.amount if hasattr(x, "amount") else x["amount"]) or 0 for x in rows
                                       if (x.bill if hasattr(x, "bill") else x["bill"]) == b), 2) for b in {(x.bill if hasattr(x, "bill") else x["bill"]) for x in rows}}
    if bills(have) != bills(new):
        sys.exit(f"{code}: the bill totals would change ({bills(have)} -> {bills(new)}) - nothing done.")
    print(f"PCs: " + ", ".join(f"PC {p.seq:02d} {p.status} {p.work_cum or 0:,.2f}" for p in pcs) + f"; certificate lines moved: {sum(1 for pl in plines if pl.item_id not in drop)}, blank ones taken off: {sum(1 for pl in plines if pl.item_id in drop)}")
    if not apply:
        return
    made = []
    for n, x in enumerate(new, 1):
        it = S.EstSubItem(sub_id=sub.id, sort=n, bill=x["bill"][:20], bill_title=x["bill_title"][:120], section=x["section"][:200], no=x["no"][:20],
                          description=x["description"], ref=(x.get("words") or "")[:120], qty=x["qty"], unit=x["unit"][:20],
                          rate=0.0 if x["grp"] == "in" else x["rate"], amount=0.0 if x["grp"] == "in" else x["amount"], measure=x["measure"],
                          is_var=False, grp=x["grp"])
        db.add(it)
        made.append(it)
    db.flush()
    for pl in plines:
        if pl.item_id in drop:
            db.delete(pl)
        else:
            pl.item_id = made[target[pl.item_id]].id
    for i in have:
        db.delete(i)
    db.flush()
    vars_ = db.query(S.EstSubItem).filter(S.EstSubItem.sub_id == sub.id, S.EstSubItem.is_var == True).all()  # noqa: E712
    for k, v in enumerate(vars_, len(made) + 1):
        v.sort = k                                          # variation lines stay after the schedule
    S.refresh_sub(db, sub.id)
    db.flush()
    db.expire_all()
    after = {p.id: round(db.get(E.EstSubPC, p.id).work_cum or 0, 2) for p in pcs}
    newmap = {i.id: i for i in made}
    for pl in db.query(S.EstPCLine).filter(S.EstPCLine.pc_id.in_([p.id for p in pcs] or [-1])).all():
        it = newmap.get(pl.item_id)
        if it is None:
            continue
        old = next(v for (pc_, iid), v in before_ln.items() if pc_ == pl.pc_id and target.get(iid) is not None and made[target[iid]].id == pl.item_id)
        if abs(S.line_amount(it, pl) - old) > 0.005:
            db.rollback()
            sys.exit(f"{code}: '{it.description[:50]}' would certify {S.line_amount(it, pl):,.2f}, it was {old:,.2f} - nothing written.")
    if after != before_pc:
        db.rollback()
        sys.exit(f"{code}: work to date would change {before_pc} -> {after} - nothing written.")
    print(f"Done: {len(made)} lines ({sum(1 for i in made if i.grp == 'head')} groups); work to date on each certificate unchanged: "
          + ", ".join(f"{v:,.2f}" for v in after.values()))


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
            print("\nWritten.")
        else:
            print("\nDry run - nothing written. Run again with --apply.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

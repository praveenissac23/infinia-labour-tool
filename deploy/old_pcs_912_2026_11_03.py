"""912 - Quebec Bridge: PC 01 to PC 08 were typed in on 02-03/11/2026 only to bring the history up to date; they were
paid before the app. They had gone on to the Contracts manager / Accounts. Here they are marked 'already paid' -
straight to Paid, the payable on each certificate as the amount paid, the invoice date as the paid date - the same as
Anoop pressing 'Old PC - already paid' on each. PC 09 (the current one) is NOT touched: it goes through the approvals.

Checked first: the subcontract is found by project 912 and the name 'Quebec'; only certificates 1-8 that are not yet
Paid are marked; nothing is marked if PC 09 is missing (the newest is never marked). Run twice = no change.

    cd ~/infinia-labour-tool && venv/bin/python deploy/old_pcs_912_2026_11_03.py            (dry run - shows the figures)
    cd ~/infinia-labour-tool && venv/bin/python deploy/old_pcs_912_2026_11_03.py --apply    (writes it)
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, HERE)
SEQS = range(1, 9)


def find_url():
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    from clear_test_returns import _find_database_url
    return _find_database_url()


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
    import models
    import main as M
    import estimation as E
    from database import SessionLocal
    db = SessionLocal()
    try:
        prj = db.query(E.EstProject).filter(E.EstProject.code == "912").first()
        subs = [s for s in db.query(E.EstSub).filter(E.EstSub.project_id == prj.id).all() if "quebec" in (s.name or "").lower()] if prj else []
        if len(subs) != 1:
            sys.exit(f"Expected one Quebec subcontract on 912, found {len(subs)} - nothing done.")
        s = subs[0]
        pcs = db.query(E.EstSubPC).filter(E.EstSubPC.sub_id == s.id).all()
        newest = max((p.seq or 0) for p in pcs) if pcs else 0
        if newest < 9:
            sys.exit(f"The newest certificate is PC {newest:02d}, not PC 09 - nothing done.")
        calc = {c["id"]: c for c in E.chain(pcs, s.adv_pct, s.ret_pct, s.vat_pct)}
        who = db.query(models.User).filter(models.User.role == "admin").first()
        now = E.dubai_now()
        print(f"{s.name} - project 912\n")
        print(f"{'PC':<5}{'Invoice':<9}{'Step now':<14}{'This PC':>13}{'VAT':>11}{'Paid (payable)':>17}  Paid on")
        tot = 0.0
        todo = []
        for p in sorted(pcs, key=lambda x: x.seq or 0):
            c = calc[p.id]
            mark = (p.seq in SEQS) and p.status != "Paid" and (p.seq or 0) < newest
            on = p.inv_date or p.received
            print(f"{p.seq:02d}   {p.inv_ref or '':<9}{p.status:<14}{c['this']:>13,.2f}{c['vat']:>11,.2f}{c['payable']:>17,.2f}  "
                  + (f"{on:%d/%m/%Y}  -> mark already paid" if mark else ("already Paid" if p.status == "Paid" else "left as it is (goes through approvals)")))
            if mark:
                todo.append((p, c["payable"], on))
                tot += c["payable"]
        print(f"\n{len(todo)} certificate(s) to mark as already paid, AED {tot:,.2f} in total.")
        if not a.apply:
            print("Dry run - nothing written. Run again with --apply to write it.")
            return
        for p, amt, on in todo:
            old = p.status
            p.paid_amount = E.r2(amt)
            p.paid_ref = p.paid_ref or "Paid before the app"
            p.paid_by = "Old certificate (already paid)"
            p.paid_on = on
            p.status = "Paid"
            p.stage_at = now
            E._log(p, {"s": "Paid", "from": old, "by": "Old certificate (already paid)", "at": now.isoformat(timespec="minutes"),
                       "note": "Old certificate - already paid before the app (clean-up 03/11/2026)", "old": True})
            p.updated_by = who.id if who else None
        db.commit()
        M.log_action(db, who.id if who else None, "pc_old_paid",
                     f"912 {s.name}: PC " + ", ".join(f"{p.seq:02d}" for p, _, _ in todo) + f" marked already paid (AED {tot:,.2f}) - clean-up 03/11/2026")
        print(f"Done - {len(todo)} marked as already paid. PC {newest:02d} left for the approvals.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

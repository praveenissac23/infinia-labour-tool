"""912 and 914: Overview > BOQ & budget replaced with their internal BOQs (5 Nov 2026).

Both came in (27 Oct / 3 Nov) with the old reader, which counted lines the workbook leaves out:
  912  208 lines, 5,130,500  ->  912_Internal_BOQ_-_R8.xlsx: 181 priced lines, 5,100,000 (= the contract value)
  914  152 lines, 2,209,485  ->  914-Internal_BOQ_R5.xlsx:   133 priced lines, 1,887,000
Every bill tallies with the workbook's own SUMMARY sheet. The lines are in boq_912_internal.json / boq_914_internal.json
beside this script (the Excels are not needed on the server). No line on either has a done % or cost rate yet, so
nothing typed is lost. The same as pressing Upload BOQ > Replace on the screen. Run twice = the same result.

    cd ~/infinia-labour-tool && venv/bin/python deploy/boq_912_914_2026_11_05.py            (dry run - shows the figures)
    cd ~/infinia-labour-tool && venv/bin/python deploy/boq_912_914_2026_11_05.py --apply    (writes it)
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, HERE)


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
    import main as M  # noqa: F401 - the tables and columns
    import estimation as E
    from database import SessionLocal, engine
    E.create_tables(engine)
    db = SessionLocal()
    try:
        who = db.query(models.User).filter(models.User.role == "admin").first()
        for code in ("912", "914"):
            r = json.load(open(os.path.join(HERE, f"boq_{code}_internal.json")))
            p = db.query(E.EstProject).filter(E.EstProject.code == code).first()
            if not p:
                print(f"Project {code} not found - skipped."); continue
            have = db.query(E.EstBoq).filter(E.EstBoq.project_id == p.id).all()
            now_amt = round(sum(E.boq_amount(b) for b in have), 2)
            typed = [b for b in have if (b.done_pct or 0) or (b.cost_rate or 0)]
            print(f"===== {code} {p.name[:60]}  (contract value {p.contract_value or 0:,.2f})")
            print(f"Now:   {len(have)} lines, AED {now_amt:,.2f} - taken out")
            print(f"In:    {len(r['lines'])} priced lines from {r['file']}, AED {r['total']:,.2f} "
                  f"(workbook SUMMARY {r['summary_total']:,.2f}, {'tallies' if r['tally_ok'] else 'DOES NOT TALLY'})")
            print(f"{'Bill':44}{'Lines':>6}{'Amount':>16}{'Workbook':>16}")
            for b in r["bills"]:
                print(f"{b['bill'][:43]:44}{b['lines']:>6}{b['counted']:>16,.2f}{(b['summary'] or 0):>16,.2f}  {'ok' if b['ok'] else 'DIFF'}")
            for s in r["skipped"]:
                print(f"  left out: {s['bill']} - {s['why']} ({s['amount']:,.2f})")
            for b in r["bills"]:
                for s in b["sections_out"]:
                    print(f"  left out: {b['bill']}: {s['name']} - {s['why']} ({s['amount']:,.2f})")
            if not r["tally_ok"]:
                print("The lines do not tally with the workbook - skipped."); continue
            if typed:
                print(f"{len(typed)} line(s) have a done % or cost rate typed - skipped, nothing changed."); continue
            if not a.apply:
                print("Dry run - nothing written.\n"); continue
            out = E._boq_take(db, p, r, 1, "replace", who, r["file"])
            M.log_action(db, who.id if who else None, "boq_replace",
                         f"{code} BOQ replaced with {r['file']}: {len(have)} lines (AED {now_amt:,.2f}) out, {out['saved']} priced lines "
                         f"(AED {r['total']:,.2f}) in - clean-up 05/11/2026")
            print(f"Done - {out['saved']} lines in, BOQ value AED {r['total']:,.2f}.\n")
        if not a.apply:
            print("Run again with --apply to write it.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

"""913 (WS-25): Overview > BOQ & budget replaced with the internal BOQ WS25_Internal_BOQ_R10_Final_.xlsx (3 Nov 2026).

The 230 lines there now came in with the old reader (Swimming pool sheet missed, bills checked against the wrong summary
figures, balancing "Summary" lines). They are taken out and the R10 workbook's 216 priced lines go in - read by the new
reader, every bill tallying with the workbook's SUMMARY sheet (5,746,999.99). The lines are in boq_913_ws25_r10.json
beside this script (the Excel is not needed on the server). Cost rates / done % typed on a line that comes back are kept
(none on 913 today). The same as pressing Upload BOQ > Replace on the screen. Run twice = the same result.

    cd ~/infinia-labour-tool && venv/bin/python deploy/boq_913_ws25_2026_11_03.py            (dry run - shows the figures)
    cd ~/infinia-labour-tool && venv/bin/python deploy/boq_913_ws25_2026_11_03.py --apply    (writes it)
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
    E.create_tables(engine)                      # the new boq_tally column, if the app has not added it yet
    r = json.load(open(os.path.join(HERE, "boq_913_ws25_r10.json")))
    db = SessionLocal()
    try:
        p = db.query(E.EstProject).filter(E.EstProject.code == "913").first()
        if not p:
            sys.exit("Project 913 not found - nothing done.")
        have = db.query(E.EstBoq).filter(E.EstBoq.project_id == p.id).all()
        now_amt = round(sum(E.boq_amount(b) for b in have), 2)
        print(f"913 {p.name[:60]}")
        print(f"Now:   {len(have)} lines, AED {now_amt:,.2f} - taken out")
        print(f"In:    {len(r['lines'])} priced lines from {r['file']}, AED {r['total']:,.2f} "
              f"(workbook SUMMARY {r['summary_total']:,.2f}, {'tallies' if r['tally_ok'] else 'DOES NOT TALLY'})\n")
        print(f"{'Bill':44}{'Lines':>6}{'Amount':>16}{'Workbook':>16}")
        for b in r["bills"]:
            print(f"{b['bill'][:43]:44}{b['lines']:>6}{b['counted']:>16,.2f}{(b['summary'] or 0):>16,.2f}  {'ok' if b['ok'] else 'DIFF'}")
        if r["skipped"] or any(b["sections_out"] for b in r["bills"]):
            print("\nLeft out (the workbook does not price these):")
            for b in r["bills"]:
                for s in b["sections_out"]:
                    print(f"  {b['bill']}: {s['name']} - {s['why']} ({s['amount']:,.2f})")
        if not r["tally_ok"]:
            sys.exit("\nThe lines do not tally with the workbook - nothing done.")
        if not a.apply:
            print("\nDry run - nothing written. Run again with --apply to write it.")
            return
        who = db.query(models.User).filter(models.User.role == "admin").first()
        out = E._boq_take(db, p, r, 1, "replace", who, r["file"])
        M.log_action(db, who.id if who else None, "boq_replace",
                     f"913 BOQ replaced with {r['file']}: {len(have)} lines (AED {now_amt:,.2f}) out, {out['saved']} priced lines "
                     f"(AED {r['total']:,.2f}) in - clean-up 03/11/2026")
        print(f"\nDone - {out['saved']} lines in, BOQ value AED {r['total']:,.2f}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

"""MR-0065 (site 915: Black Sand 6 m3, Aggregate 3 m3) was ordered on IC/LPO/20260172 (Srayedin: Black Sand 3M3 x2
trips, 3/4 Aggregate 3M3 x1 trip) from the ticked lines, but editing the LPO (rate, payment terms) dropped the link
because the LPO names the materials differently - so MR-0065 was back on the 'waiting to be ordered' list, and the
LPO had made its own second request for the same sand and aggregate (MR-0067). This puts the link back (the request
reads 'ordered' from Srayedin, off the waiting list) and closes MR-0067 (nothing has arrived on it). No stock, no
amount, nothing in Zoho is touched.

    cd ~/infinia-labour-tool && venv/bin/python deploy/fix_mr0065_2026_11_02.py            (dry run - nothing written)
    cd ~/infinia-labour-tool && venv/bin/python deploy/fix_mr0065_2026_11_02.py --apply    (writes it)
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, HERE)
TAG = "MR-0065 linked back to IC/LPO/20260172 02/11/2026"


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
    from database import SessionLocal
    db = SessionLocal()
    try:
        o = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.ref == "IC/LPO/20260172").first()
        mr = db.query(models.MaterialRequest).filter(models.MaterialRequest.ref == "MR-0065").first()
        if not o or not mr or (o.status or "") == "cancelled":
            sys.exit("Refused: IC/LPO/20260172 (live) or MR-0065 not found.")
        want = [l for l in mr.lines if (l.description or "").strip().lower() in ("black sand", "aggregate")]
        if len(want) != 2:
            sys.exit(f"Refused: expected MR-0065's Black Sand and Aggregate lines, found {len(want)}.")
        if any((l.qty_received or 0) > 0 for l in want):
            sys.exit("Refused: something has already arrived on MR-0065 - check by hand.")
        ids = [int(x) for x in (o.request_line_ids or "").split(",") if x.strip().isdigit()]
        add = [l.id for l in want if l.id not in ids]
        own = [r for r in db.query(models.MaterialRequest).filter(models.MaterialRequest.lpo_id == o.id).all()]
        print(("DRY RUN - nothing is written" if not a.apply else "WRITING") + f" - {TAG}")
        if not add and all(l.supplier_id == o.supplier_id for l in want):
            print("  Nothing to do: MR-0065 is already linked to IC/LPO/20260172.")
            return
        for l in want:
            print(f"  - MR-0065 {l.description} {l.qty_requested:g} {l.unit}: ordered on IC/LPO/20260172 from {o.supplier_name}")
        for r in own:
            print(f"  - {r.ref} ({r.notes}): " + ", ".join(f"{x.description} {x.qty_requested:g} (received {x.qty_received or 0:g})" for x in r.lines)
                  + " - the LPO's own copy of the same order: closed, nothing arrived on it")
        if not a.apply:
            print("\nDry run - nothing was written. Run again with --apply to make this change.")
            return
        o.request_line_ids = "," + ",".join(map(str, ids + add)) + ","
        for l in want:
            l.supplier_id, l.status = o.supplier_id, "approved"
        if mr.status in ("approved", "pending"):
            mr.status = "ordered"
        db.flush()
        M._track_lpo(db, o, None)          # with the fix: the ticked lines cover the LPO - its own copy goes
        db.add(models.AuditLog(user_id=None, action="purchasing_fix",
                               details=f"MR-0065 Black Sand + Aggregate linked back to IC/LPO/20260172 (dropped by an LPO edit); "
                                       f"{', '.join(r.ref for r in own)} closed [{TAG}]"))
        db.commit()
        for r in own:
            db.refresh(r)
            print(f"  {r.ref} now: {r.status}, {len(r.lines)} line(s)")
        print("\nWritten - one activity-log entry, tagged '" + TAG + "'.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

"""Put the 45 kg of Wire Nail 2.5 Inch (ITM3366, IC/LPO/20260166, DN00003232, 29/10/2026) back in the central store.

The purchasing correction of 31/10/2026 moved it to site 913 because the LPO charges it to 913, but the store keeper
had kept it in the central store and issued from there (11 kg to 919 on 30/10, 5 kg to 926 on 31/10) - so the central
store showed -5. This puts the delivery back where it was received. The LPO and its cost to 913 are not touched.

    cd ~/infinia-labour-tool && venv/bin/python deploy/fix_wirenail_2026_11_01.py            (dry run - nothing written)
    cd ~/infinia-labour-tool && venv/bin/python deploy/fix_wirenail_2026_11_01.py --apply    (writes it)
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, HERE)
TAG = "wire nail back to central store 01/11/2026"


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
    from database import SessionLocal
    db = SessionLocal()
    try:
        item = db.query(models.StoreItem).filter(models.StoreItem.code == "ITM3366").first()
        if not item:
            sys.exit("Refused: material ITM3366 (Wire Nail 2.5 Inch) is not on file.")
        mv = (db.query(models.StoreMovement)
              .filter(models.StoreMovement.item_id == item.id, models.StoreMovement.kind == "in",
                      models.StoreMovement.reference == "DN00003232").all())
        if len(mv) != 1:
            sys.exit(f"Refused: expected one delivery DN00003232 of {item.name}, found {len(mv)}.")
        m = mv[0]
        where = m.location or ""
        print(("DRY RUN - nothing is written" if not a.apply else "WRITING") + f" - {TAG}")
        if where == "":
            print(f"  Nothing to do: {m.qty:g} {item.unit or ''} of {item.name} (DN00003232) is already in the central store.")
            return
        print(f"  - {item.name} {m.qty:g} {item.unit or ''} (DN00003232, 29/10/2026): site {where} -> central store "
              f"(it was issued from the central store afterwards: 11 to 919 on 30/10, 5 to 926 on 31/10)")
        if not a.apply:
            print("\nDry run - nothing was written. Run again with --apply to make this change.")
            return
        m.location = ""
        m.notes = ((m.notes or "") + f" | back to the central store: received and issued there ({TAG})")[:2000]
        db.add(models.AuditLog(user_id=None, action="purchasing_fix",
                               details=f"{item.name} {m.qty:g} (DN00003232) moved back from site {where} to the central store [{TAG}]"))
        db.commit()
        print("\nWritten - one activity-log entry, tagged '" + TAG + "'.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

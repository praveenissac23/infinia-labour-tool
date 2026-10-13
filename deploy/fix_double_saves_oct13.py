"""Fix of 13 Oct 2026: stock moves saved twice by a double tap on Save.

Two taps sent the same return twice in the same instant (Electric
Vibrator and Electric Vibrator Needle, back from site 915), so the site
showed -1 and the central store one too many. This takes out the second
copy of any move that is an exact twin of another - same login, material,
kind, quantity, from, to, note and date, saved within 3 seconds. Moves
that differ in anything (a different worker's name in the note) stay.

    cd ~/infinia-labour-tool && venv/bin/python deploy/fix_double_saves_oct13.py
"""
import os, sys
from datetime import timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, HERE)
from clear_test_returns import _find_database_url

url = os.environ.get("DATABASE_URL") or _find_database_url()
if not url:
    sys.exit("Could not find DATABASE_URL.")
os.environ["DATABASE_URL"] = url
os.environ.setdefault("INFINIA_NO_PUSH", "1")
import main as M          # noqa: E402
import models             # noqa: E402
from database import SessionLocal  # noqa: E402

M._add_missing_columns()


def run():
    db = SessionLocal()
    rows = db.query(models.StoreMovement).order_by(models.StoreMovement.id).all()
    seen, gone = {}, []
    for m in rows:
        k = (m.created_by, m.item_id, m.kind, round(m.qty or 0, 6), m.from_location or "", m.location or "",
             (m.notes or "").strip(), m.moved_on, m.reference or "")
        first = seen.get(k)
        if first is not None and first.created_at and m.created_at and abs(m.created_at - first.created_at) <= timedelta(seconds=3):
            gone.append(m)
            continue
        seen[k] = m
    for m in gone:
        it = m.item
        print(f"  taken out: #{m.id} {m.kind} {m.qty:g} {it.code if it else ''} {it.name if it else ''}"
              f" from '{m.from_location or 'store'}' to '{m.location or 'store'}' ({m.created_at})")
        db.delete(m)
    db.commit()
    if gone:
        M.log_action(db, None, "store_movement", f"Double-saved moves taken out: {', '.join('#' + str(m.id) for m in gone)}")
    db.close()
    print(f"Double saves taken out: {len(gone)}.")


if __name__ == "__main__":
    run()

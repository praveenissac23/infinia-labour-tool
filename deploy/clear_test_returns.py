"""
Remove test entries from the store: return notes and lost/damaged
write-offs that were only a trial.

Shows everything it is about to remove and waits for "yes" before it
touches anything. Nothing else in the ledger is changed.

    cd ~/infinia-labour-tool && python3 deploy/clear_test_returns.py RN-0005 RN-0006

Each reference named is a return note: the note, its lines, and every
stock movement that note posted (returned and lost) are removed. On top
of that, "lost" movements with the note "test" (a hand-typed trial
write-off) are removed too. Pass --no-test-lost to leave those.
"""
import os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))


def _find_database_url():
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    for unit in ("infinia", "infinia.service"):
        try:
            out = subprocess.run(["systemctl", "show", unit, "-p", "Environment", "--value"],
                                 capture_output=True, text=True, timeout=10).stdout
            m = re.search(r"DATABASE_URL=(\S+)", out or "")
            if m:
                return m.group(1)
            out = subprocess.run(["systemctl", "show", unit, "-p", "EnvironmentFiles", "--value"],
                                 capture_output=True, text=True, timeout=10).stdout
            for path in re.findall(r"(/\S+?)(?:\s|$)", out or ""):
                path = path.rstrip("()").lstrip("-")
                if os.path.exists(path):
                    for line in open(path):
                        if line.strip().startswith("DATABASE_URL="):
                            return line.split("=", 1)[1].strip().strip("'\"")
        except Exception:
            pass
    for env in (os.path.join(HERE, "..", ".env"), os.path.join(HERE, "..", "app", ".env")):
        if os.path.exists(env):
            for line in open(env):
                if line.strip().startswith("DATABASE_URL="):
                    return line.split("=", 1)[1].strip().strip("'\"")
    return None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    keep_test_lost = "--no-test-lost" in sys.argv
    url = _find_database_url()
    if not url:
        sys.exit("Could not find DATABASE_URL. Run with it in front:  DATABASE_URL='...' python3 deploy/clear_test_returns.py RN-0005")
    os.environ["DATABASE_URL"] = url
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import models

    db = sessionmaker(bind=create_engine(url))()
    refs = [a.upper() for a in args]
    notes = db.query(models.HireReturn).filter(models.HireReturn.ref.in_(refs)).all() if refs else []
    missing = sorted(set(refs) - {n.ref for n in notes})
    if missing:
        print("Not found (skipped):", ", ".join(missing))
    moves = []
    if notes:
        moves += db.query(models.StoreMovement).filter(models.StoreMovement.reference.in_([n.ref for n in notes])).all()
    if not keep_test_lost:
        moves += [m for m in db.query(models.StoreMovement).filter(models.StoreMovement.kind == "lost").all()
                  if (m.notes or "").strip().lower() == "test" and m not in moves]
    if not notes and not moves:
        print("Nothing to remove.")
        return

    items = {i.id: i for i in db.query(models.StoreItem).all()}
    print("\nThis will remove:\n")
    for n in notes:
        print(f"  Return note {n.ref} ({n.status}) to {n.supplier_name}, {n.return_date}, {len(n.lines)} line(s)")
        for l in n.lines:
            print(f"      {l.description}: returned {l.qty_returned or 0}, short {l.qty_short or 0} {l.short_reason or ''}".rstrip())
    for m in moves:
        it = items.get(m.item_id)
        print(f"  Movement #{m.id} {m.moved_on} {m.kind:<11} {it.code if it else '?'} {it.name if it else ''} "
              f"qty {m.qty} at {m.location or m.from_location or '-'}  ({m.notes or ''})")
    print()
    if input("Type yes to remove these: ").strip().lower() != "yes":
        print("Nothing changed.")
        return
    for m in moves:
        db.delete(m)
    for n in notes:
        for l in list(n.lines):
            db.delete(l)
        db.delete(n)
    db.commit()
    print(f"Removed {len(notes)} return note(s) and {len(moves)} movement(s). Stock figures follow the ledger, so they are already right.")


if __name__ == "__main__":
    main()

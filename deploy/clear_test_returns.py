"""
Remove test entries from the store: return notes and lost/damaged
write-offs that were only a trial.

Shows everything it is about to remove and waits for "yes" before it
touches anything. Nothing else in the ledger is changed.

    cd ~/infinia-labour-tool && venv/bin/python deploy/clear_test_returns.py RN-0005 RN-0006
    cd ~/infinia-labour-tool && venv/bin/python deploy/clear_test_returns.py --items ITM1221 ITM1222 ITM1223

With --items, the codes named are materials to remove outright: the
item, every stock movement of it, every return note line of it (and a
note left with no lines), and it is unlinked from any request or order
line that named it (the line keeps its description).

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
    items_mode = "--items" in sys.argv
    url = _find_database_url()
    if not url:
        sys.exit("Could not find DATABASE_URL. Run with it in front:  DATABASE_URL='...' python3 deploy/clear_test_returns.py RN-0005")
    os.environ["DATABASE_URL"] = url
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import models

    db = sessionmaker(bind=create_engine(url))()
    print("Database:", re.sub(r"://([^:@/]+):[^@]*@", r"://\1:***@", url))
    if items_mode:
        return remove_items(db, models, [a.upper() for a in args])
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
        allnotes = db.query(models.HireReturn).order_by(models.HireReturn.id).all()
        print("Return notes on this database:", ", ".join(f"{n.ref} ({n.status})" for n in allnotes) or "none")
        lost = db.query(models.StoreMovement).filter(models.StoreMovement.kind == "lost").all()
        print("Lost/damaged movements:", len(lost))
        for m in lost:
            print(f"   #{m.id} {m.moved_on} qty {m.qty} at {m.location or '-'} ref {m.reference or '-'} notes {m.notes!r}")
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


def remove_items(db, models, codes):
    items = db.query(models.StoreItem).filter(models.StoreItem.code.in_(codes)).all()
    missing = sorted(set(codes) - {i.code for i in items})
    if missing:
        print("Not found (skipped):", ", ".join(missing))
    if not items:
        print("Nothing to remove.")
        return
    ids = [i.id for i in items]
    moves = db.query(models.StoreMovement).filter(models.StoreMovement.item_id.in_(ids)).order_by(models.StoreMovement.id).all()
    rlines = db.query(models.HireReturnLine).filter(models.HireReturnLine.item_id.in_(ids)).all()
    polines = db.query(models.PurchaseOrderLine).filter(models.PurchaseOrderLine.item_id.in_(ids)).all()
    mrlines = db.query(models.MaterialRequestLine).filter(models.MaterialRequestLine.item_id.in_(ids)).all()
    print("\nThis will remove:\n")
    for i in items:
        print(f"  Material {i.code} {i.name} ({i.item_type or ''}, {i.unit or ''})")
    for m in moves:
        print(f"  Movement #{m.id} {m.moved_on} {m.kind:<11} qty {m.qty} at {m.location or m.from_location or '-'} ref {m.reference or '-'} ({m.notes or ''})")
    for l in rlines:
        print(f"  Return note line on {l.ret.ref if l.ret else '?'}: {l.description} returned {l.qty_returned or 0}, short {l.qty_short or 0}")
    empties = []
    for l in rlines:
        n = l.ret
        if n and n not in empties and all(x in rlines for x in n.lines):
            empties.append(n)
    for n in empties:
        print(f"  Return note {n.ref} ({n.status}) - nothing left on it")
    for l in polines:
        print(f"  Purchase order line kept, unlinked from the material: {l.description}")
    for l in mrlines:
        print(f"  Request line kept, unlinked from the material: {l.description}")
    print()
    if input("Type yes to remove these: ").strip().lower() != "yes":
        print("Nothing changed.")
        return
    for l in polines:
        l.item_id = None
    for l in mrlines:
        l.item_id = None
    for m in moves:
        db.delete(m)
    for l in rlines:
        db.delete(l)
    for n in empties:
        db.delete(n)
    for i in items:
        db.delete(i)
    db.commit()
    print(f"Removed {len(items)} material(s), {len(moves)} movement(s), {len(rlines)} return line(s), {len(empties)} return note(s).")


if __name__ == "__main__":
    main()

"""How long the server takes to answer each heavy screen, on the real data - read only, safe any time.

    cd ~/infinia-labour-tool && venv/bin/python deploy/time_screens.py

It asks the app exactly what a browser asks when the screen opens (as admin and as a few staff logins), three
times each, and prints the slowest first: milliseconds and the size sent. Nothing is changed (opening a Trello
board only notes that admin "saw" it, as a click would). Send the printout back to Claude.
"""
import os, sys, time, json, statistics

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, HERE)
from clear_test_returns import _find_database_url

url = _find_database_url()
if not url:
    sys.exit("Could not find DATABASE_URL.")
os.environ["DATABASE_URL"] = url
os.environ.setdefault("INFINIA_NO_SCHED", "1"); os.environ.setdefault("INFINIA_NO_PUSH", "1")
import main as M                        # the app, without starting it (no start-up jobs run)
import auth, models
from database import SessionLocal
from fastapi.testclient import TestClient

c = TestClient(M.app)                    # not entered: start-up events are not run
db = SessionLocal()
users = {u.username: u for u in db.query(models.User).all()}


def hdr(username):
    return {"Authorization": "Bearer " + auth.create_access_token({"sub": username})}


def first(q):
    try:
        x = q.first()
        return x
    except Exception:
        return None


# what to ask for: the screens that feel slow
est = db.query(M.estimation.EstProject).order_by(M.estimation.EstProject.code).all()
big = [p for p in est if p.code in ("914", "915", "919", "909", "920")][:3] or est[:3]
import est_bills as EB
bill = first(db.query(EB.EstBill).order_by(EB.EstBill.id.desc()))
import boards as KB
kb = sorted(db.query(KB.KBoard).all(), key=lambda b: -db.query(KB.KCard).filter(KB.KCard.board_id == b.id, KB.KCard.closed == False).count())[:2]  # noqa: E712
db.close()

ADMIN = "admin" if "admin" in users else next(u for u, x in users.items() if x.role == "admin")
WHO = [ADMIN] + [u for u in ("anoop", "shafiq", "arun", "amal", "arathi") if u in users]
CHECKS = []
for u in WHO:
    CHECKS.append((u, "/notifications", "the bell (every open tab asks every 20 s)"))
CHECKS += [
    (ADMIN, "/store/est/meta", "Estimation opens"),
    (ADMIN, "/store/est/dash", "Estimation dashboard"),
    (ADMIN, "/store/est/payqueue", "Accounts > Subcontractor payments"),
] + [(ADMIN, f"/store/est/projects/{p.id}", f"Estimation project {p.code}") for p in big] + \
    [(ADMIN, f"/store/est/ipa/list?project_id={p.id}", f"Bills list {p.code}") for p in big[:1]] + \
    ([(ADMIN, f"/store/est/ipa/bill/{bill.id}", "a bill opened")] if bill else []) + [
    (ADMIN, "/store/kb/boards", "Trello: boards"),
    (ADMIN, "/store/kb/summary", "Trello: summary"),
] + [(ADMIN, f"/store/kb/boards/{b.id}", f"Trello board '{b.title}'") for b in kb] + [
    (ADMIN, "/store/kb/notes", "Trello: my notes (asked every 30 s)"),
    (ADMIN, "/store/items", "Store: materials list"),
    (ADMIN, "/store/stock", "Store: stock"),
    (ADMIN, "/store/movements", "Store: movements"),
    (ADMIN, "/employees", "Staff list"),
]

rows = []
for u, path, what in CHECKS:
    h = hdr(u)
    ts, size, code = [], 0, 0
    for _ in range(3):
        t0 = time.perf_counter()
        r = c.get(path, headers=h)
        ts.append((time.perf_counter() - t0) * 1000)
        size, code = len(r.content), r.status_code
    rows.append((statistics.median(ts), max(ts), size, code, u, path, what))

rows.sort(reverse=True)
print(f"{'ms (typical)':>12} {'ms (worst)':>10} {'KB':>7}  code  login     what")
for med, worst, size, code, u, path, what in rows:
    print(f"{med:12.0f} {worst:10.0f} {size / 1024:7.0f}  {code:4d}  {u:9s} {what}  [{path}]")

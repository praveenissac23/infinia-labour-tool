"""Proof that the rental work touches only rentals (owner, 01/11/2026: "Make sure you touch only rentals. Nothing
else."). On a copy of the live records (tests/rental_fix_replica.py), three readings are compared:

    A  the app BEFORE this change (commit 852d68d), database before the correction
    B  the app AFTER this change, database before the correction
    C  the app AFTER this change, database after deploy/fix_rentals_2026_11_01.py --apply

and must be identical, byte for byte, for:
  - every non-rental material (never held a supplier's stock, not typed Rental, not named 'Rental ...'): its stock at
    every place, its Current stock / Owned assets / Items to reorder rows as they print
  - every LPO's money (lines' qty x rate, discount, VAT, round off, LPO total)
  - Accounts > Project expense: every project's figures and lines, the totals and the unlinked amounts
  - every table outside the store's rental records (payroll, attendance, accounts, petty cash, Zoho, estimation ...):
    the rows themselves

    python3 tests/rental_scope_test.py [work-dir]"""
import hashlib, json, os, shutil, sqlite3, subprocess, sys, tarfile, io, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import rental_fix_replica as RR

BASE = "852d68d"
W = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp()
os.makedirs(W, exist_ok=True)
FAIL = []


def ck(l, ok, x=""):
    print(("PASS " if ok else "FAIL ") + l + ("" if ok else f"  [{str(x)[:1500]}]"))
    if not ok:
        FAIL.append(l)


# the app as it was before this change
OLD = os.path.join(W, "old")
shutil.rmtree(OLD, ignore_errors=True)
os.makedirs(OLD)
arc = subprocess.run(["git", "archive", BASE, "app"], cwd=ROOT, capture_output=True, check=True).stdout
tarfile.open(fileobj=io.BytesIO(arc)).extractall(OLD)
OLD_APP, NEW_APP = os.path.join(OLD, "app"), os.path.join(ROOT, "app")

# The store's rental records - the only tables the change and the correction may write. Everything else must not move.
STORE_TABLES = {"store_items", "store_movements", "lpo_receipts", "rental_maps", "purchase_orders", "audit_log"}

READ = r'''
import json, sys
import main as M, models
from database import SessionLocal
import projexpense as PX
db = SessionLocal()
items = {i.id: i for i in db.query(models.StoreItem).all()}
ever = {i for (i,) in db.query(models.StoreMovement.item_id).filter(models.StoreMovement.owner_id.isnot(None)).distinct()}
non_rental = sorted(json.loads(sys.argv[1])) if len(sys.argv) > 1 and sys.argv[1] != "-" else sorted(
    i for i, it in items.items() if i not in ever and (it.item_type or "") != "rental" and not (it.name or "").lower().startswith("rental "))
N = set(non_rental)
codes = {items[i].code for i in N if i in items}
out = {"non_rental": non_rental}
out["stock"] = sorted(f"{i}|{l}|{round(q, 4)}" for (i, l), q in M._stock_map(db).items() if i in N and abs(q) > 1e-9)
def paper(rows):
    return sorted(json.dumps({k: v for k, v in r.items() if not str(k).startswith("_")}, sort_keys=True) for r in rows if r.get("code") in codes)
for kind in ("stock", "assets", "low"):
    out["report_" + kind] = paper(M.store_report(kind=kind, db=db, user=None)["rows"])
out["lpo_money"] = sorted(f"{o.ref}|{M.lpo_total(o)}|{o.discount_pct}|{o.round_off}|{o.tax_pct}|" +
                          ";".join(f"{l.id}:{l.qty}:{l.rate}:{l.tax_pct}" for l in o.lines)
                          for o in db.query(models.PurchaseOrder).all())
g = PX._gather(db)
out["px_rows"] = g["rows"]
out["px_totals"] = g["totals"]
out["px_unlinked"] = g["unlinked"]
out["px_lines"] = {k: sorted(json.dumps(x, sort_keys=True, default=str) for x in v
                             if x.get("cat") != "store" or x.get("code") in codes) for k, v in g["lines"].items()}
out["px_store_rental_lines"] = sum(1 for v in g["lines"].values() for x in v if x.get("cat") == "store" and x.get("code") not in codes)
print("JSON" + json.dumps(out, default=str, sort_keys=True))
'''


def read(app, db, non_rental=None):
    env = dict(os.environ, DATABASE_URL=f"sqlite:///{db}", INFINIA_NO_SCHED="1", INFINIA_NO_PUSH="1", PYTHONDONTWRITEBYTECODE="1")
    p = subprocess.run([sys.executable, "-c", READ, json.dumps(non_rental) if non_rental is not None else "-"], cwd=app, env=env,
                       capture_output=True, text=True)
    line = [x for x in p.stdout.splitlines() if x.startswith("JSON")]
    if not line:
        print(p.stdout[-1500:], p.stderr[-3000:])
        raise SystemExit("reading failed")
    return json.loads(line[-1][4:])


def tables(db):
    c = sqlite3.connect(db)
    names = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    h = {}
    for t in names:
        if t in STORE_TABLES:
            continue
        rows = c.execute(f'SELECT * FROM "{t}" ORDER BY 1').fetchall()
        h[t] = hashlib.sha1(repr(rows).encode()).hexdigest()
    c.close()
    return h


DB = os.path.join(W, "scope.db")
RR.build(DB)
# both versions of the app once, so whatever either does on start-up is done before anything is compared
read(OLD_APP, DB); read(NEW_APP, DB)
t0 = tables(DB)
A = read(OLD_APP, DB)
N = A["non_rental"]
print(f"     ({len(N)} non-rental materials, {len(A['stock'])} stock figures, {len(A['lpo_money'])} LPOs, "
      f"{len(A['px_rows'])} projects, {len(t0)} other tables compared)")
B = read(NEW_APP, DB, N)
env = dict(os.environ, INFINIA_NO_SCHED="1", INFINIA_NO_PUSH="1")
env.pop("DATABASE_URL", None)
p = subprocess.run([sys.executable, os.path.join(ROOT, "deploy", "fix_rentals_2026_11_01.py"), "--database-url", f"sqlite:///{DB}", "--apply"],
                   cwd=NEW_APP, env=env, capture_output=True, text=True)
ck("the rental correction applies", p.returncode == 0, (p.stdout + p.stderr)[-1500:])
C = read(NEW_APP, DB, N)
t1 = tables(DB)

for key, label in (("stock", "stock of every non-rental material at every place"),
                   ("report_stock", "Current stock rows of non-rental materials, as they print"),
                   ("report_assets", "Owned assets rows"), ("report_low", "Items to reorder rows"),
                   ("lpo_money", "every LPO's money (lines, discount, VAT, round off, total)"),
                   ("px_rows", "Project expense: every project's figures"), ("px_totals", "Project expense totals"),
                   ("px_unlinked", "Project expense unlinked amounts"),
                   ("px_lines", "Project expense lines (labour, LPOs, petty cash, non-rental store issues) per project")):
    diff = lambda a, b: (sorted(set(map(str, a)) - set(map(str, b)))[:5], sorted(set(map(str, b)) - set(map(str, a)))[:5]) \
        if isinstance(a, list) else ""
    ck(f"{label}: before the change = after the change", A[key] == B[key], diff(A[key], B[key]))
    ck(f"{label}: before the correction = after the correction", B[key] == C[key], diff(B[key], C[key]))
ck("every table outside the store's rental records (payroll, attendance, accounts, petty cash, Zoho, estimation ...) "
   "is byte-identical after the correction", t0 == t1, [k for k in t0 if t0[k] != t1.get(k)])
print(f"\n{len(FAIL)} FAILED" if FAIL else "\nALL PASSED")
sys.exit(1 if FAIL else 0)

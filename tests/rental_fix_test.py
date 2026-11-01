"""The 01 Nov 2026 rental stock correction (deploy/fix_rentals_2026_11_01.py), run on a copy of the live records
(tests/rental_fix_replica.py): dry run writes nothing; --apply makes the changes; --apply again changes nothing;
payroll, LPO money and every stock movement kept; then the same in both orders with the purchasing correction
(deploy/fix_purchasing_2026_10_31.py); the result read through the app: Stock (Rental) = Rentals, ours and rental
never one row.

    python3 tests/rental_fix_test.py [work-dir]"""
import hashlib, os, shutil, sqlite3, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import rental_fix_replica as RR

W = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp()
os.makedirs(W, exist_ok=True)
FAIL = []


def ck(l, ok, x=""):
    print(("PASS " if ok else "FAIL ") + l + ("" if ok else f"  [{str(x)[:900]}]"))
    if not ok:
        FAIL.append(l)


def run(db, script, *extra):
    env = dict(os.environ, INFINIA_NO_SCHED="1", INFINIA_NO_PUSH="1")
    env.pop("DATABASE_URL", None)
    p = subprocess.run([sys.executable, os.path.join(ROOT, "deploy", script), "--database-url", f"sqlite:///{db}", *extra],
                       cwd=os.path.join(ROOT, "app"), env=env, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


RENT = "fix_rentals_2026_11_01.py"
PURCH = "fix_purchasing_2026_10_31.py"


def n_changes(out):
    try:
        return int(out.split("changes in all")[0].rsplit("\n", 1)[-1].strip() or 0)
    except ValueError:
        return -1


def table_hash(db, tables):
    c = sqlite3.connect(db); h = {}
    for t in tables:
        rows = c.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall()
        h[t] = hashlib.sha1(repr(rows).encode()).hexdigest()
    c.close(); return h


def money(db):
    c = sqlite3.connect(db)
    out = {r[0]: r[1:] for r in c.execute("""SELECT o.ref, o.discount_pct, coalesce(o.round_off,0), o.tax_pct,
        (SELECT group_concat(l.id || ':' || l.qty || ':' || l.rate || ':' || l.tax_pct) FROM purchase_order_lines l WHERE l.order_id=o.id)
        FROM purchase_orders o""")}
    c.close(); return out


def movements(db):
    c = sqlite3.connect(db)
    out = {r[0]: r[1:] for r in c.execute("SELECT id, kind, qty, location, from_location, moved_on, reference FROM store_movements")}
    c.close(); return out


STORE = ["purchase_orders", "purchase_order_lines", "material_requests", "material_request_lines", "store_movements", "lpo_receipts",
         "rental_maps", "audit_log", "store_items", "suppliers"]
PAYROLL = ["employees", "daily_rows", "employee_summaries", "salary_adjustments", "petty_cash"]

# ---- refuses what is not the live shape ----------------------------------------------------------------------------
DB0 = os.path.join(W, "rf_plain.db")
shutil.copy("/tmp/claude-0/full.db", DB0)
rc, out = run(DB0, RENT)
ck("refuses a database without the new LPO 'Rental' column (app not deployed yet)", rc != 0 and "Refused" in out and "deploy" in out, out[-400:])
env = dict(os.environ, DATABASE_URL=f"sqlite:///{DB0}", INFINIA_NO_SCHED="1", INFINIA_NO_PUSH="1")
subprocess.run([sys.executable, "-c", "import main; main._add_missing_columns()"], cwd=os.path.join(ROOT, "app"), env=env, capture_output=True)
rc, out = run(DB0, RENT)
ck("refuses a database that does not look like the live one", rc != 0 and "does not look like the live database" in out, out[-400:])

# ---- this script alone: dry run, apply, apply again ----------------------------------------------------------------
DB = os.path.join(W, "rf_a.db")
RR.build(DB)
before, pay0, money0, mv0 = table_hash(DB, STORE), table_hash(DB, PAYROLL), money(DB), movements(DB)
rc, out = run(DB, RENT)
ck("dry run runs", rc == 0, out[-1500:])
ck("dry run says nothing is written, names the run order and lists the changes",
   "DRY RUN - nothing is written" in out and "Run order:" in out and "changes in all" in out, out[:600])
ck("dry run wrote nothing", table_hash(DB, STORE) == before)
n_dry = n_changes(out)
print(f"     (dry run: {n_dry} changes)")
ck("dry run: Stock (Rental) = Rentals, and no material left holding ours and rental on one row",
   "show the same quantity for every material, supplier and place: yes" in out and "holding ours and rental on one row: 0" in out, out[-1200:])
open(os.path.join(W, "dry_run_alone.txt"), "w").write(out)

rc, out = run(DB, RENT, "--apply")
ck("apply runs", rc == 0, out[-1500:])
n_app = n_changes(out)
ck("apply makes exactly the changes the dry run listed", n_app == n_dry and n_app > 100, (n_dry, n_app))
c = sqlite3.connect(DB)
logs = c.execute("SELECT count(*) FROM audit_log WHERE action='rental_stock_fix' AND details LIKE '%[rental stock 01/11/2026]'").fetchone()[0]
c.close()
ck("one activity-log entry per change, tagged 'rental stock 01/11/2026'", logs == n_app, (logs, n_app))
ck("payroll untouched", table_hash(DB, PAYROLL) == pay0)
ck("no money amount on any LPO changed", money(DB) == money0)
mv1 = movements(DB)
ck("no stock movement deleted, none changed in quantity, place or date", all(k in mv1 and mv1[k] == v for k, v in mv0.items()),
   [k for k, v in mv0.items() if mv1.get(k) != v][:10])
after1 = table_hash(DB, STORE)
rc, out = run(DB, RENT, "--apply")
ck("apply again: nothing changes", rc == 0 and " 0  changes in all" in out and table_hash(DB, STORE) == after1, out[-900:])

# ---- what the app now says -----------------------------------------------------------------------------------------
CHECK = r'''
import json, sys
import main as M, purchasing as P, models
from database import SessionLocal
db = SessionLocal()
out = {}
st = M._stock_rows(db)
rows = st["rows"]
a, b = {}, {}
for r in rows:
    if r["item_type"] == "rental":
        for loc, q in [("", r["in_store"])] + list(r["by_site"].items()):
            if abs(q) > 1e-9: a[f'{r["_item_id"]}|{r["_supplier_id"]}|{loc}'] = round(q, 2)
for r in M._on_rent(db):
    for loc, q in r["by_location"].items():
        if abs(q) > 1e-9: b[f'{r["item_id"]}|{r["supplier_id"]}|{loc}'] = round(q, 2)
out["same"] = a == b
out["n_rent"] = len(b)
pos = M._stock_map(db, by_owner=True)
owned = {i for (i, l, o), q in pos.items() if o is None and abs(q) > 1e-9}
hired = {i for (i, l, o), q in pos.items() if o is not None and abs(q) > 1e-9}
out["both"] = sorted(owned & hired)
items = {i.id: i for i in db.query(models.StoreItem).all()}
out["hired_not_rental"] = sorted(i for i in hired if items[i].item_type != "rental")
out["owned_on_rental"] = sorted(i for i in owned if items[i].item_type == "rental")
def row(name, rental):
    return [{k: v for k, v in r.items() if not k.startswith("_") or k in ("_type_label",)} for r in rows
            if r["name"] == name and ((r["item_type"] == "rental") == rental)]
out["l18_ours"] = row("Ledger 1.8 M", False)
out["l18_rent"] = row("Rental Ledger 1.8M", True)
out["s20_926"] = pos.get((3704, "926", 94), 0), pos.get((3704, "926", None), 0)
out["types"] = {k: v["materials"] for k, v in st["type_totals"].items()}
o = {x.ref: x for x in db.query(models.PurchaseOrder).all()}
out["rental_flags"] = {r: o[r].rental for r in ("IC/LPO/20260103", "IC/LPO/20260109", "IC/LPO/20260148", "IC/LPO/20260150R1", "IC/LPO/20260170")}
book = P.Book(db)
out["lpo_status"] = {r: book.of(o[r])["status"] for r in ("IC/LPO/20260148", "IC/LPO/20260150R1", "IC/LPO/20260170", "IC/LPO/20260103")}
out["services"] = [(i.code, i.item_type, i.category) for i in items.values() if i.code in ("ITM1014", "ITM1019", "ITM1114", "ITM1102", "ITM1200", "ITM1078")]
out["positions"] = sorted([f"{i}|{l}|{o}|{round(q, 2)}" for (i, l, o), q in pos.items() if abs(q) > 1e-9 and i in items
                           and (items[i].item_type == "rental" or o is not None)])
print("JSON" + json.dumps(out, default=str))
'''


def read_app(db):
    env = dict(os.environ, DATABASE_URL=f"sqlite:///{db}", INFINIA_NO_SCHED="1", INFINIA_NO_PUSH="1")
    p = subprocess.run([sys.executable, "-c", CHECK], cwd=os.path.join(ROOT, "app"), env=env, capture_output=True, text=True)
    import json
    line = [x for x in p.stdout.splitlines() if x.startswith("JSON")]
    if not line:
        print(p.stdout[-2000:], p.stderr[-3000:])
        return {}
    return json.loads(line[-1][4:])


r = read_app(DB)
ck("Stock (type Rental) = Rentals, per material, supplier and place", r.get("same") and r.get("n_rent", 0) > 80, r.get("n_rent"))
ck("no material holds ours and rental together", r.get("both") == [], r.get("both"))
ck("every material holding rental stock is type Rental; none of ours sits on a Rental material",
   r.get("hired_not_rental") == [] and r.get("owned_on_rental") == [], (r.get("hired_not_rental"), r.get("owned_on_rental")))
l18o, l18r = r.get("l18_ours") or [], r.get("l18_rent") or []
ck("Ledger 1.8 M: our 239 at the sites (Asset); Desarch's 405 at 914 now on Rental Ledger 1.8M (Rental - Desarch)",
   len(l18o) == 1 and l18o[0]["total"] == 239 and l18o[0]["item_type"] == "asset"
   and len(l18r) == 1 and l18r[0]["by_site"].get("914") == 405 and l18r[0]["_type_label"].startswith("Rental – Desarch"), (l18o, l18r))
ck("926: Rental Standard 2.0M is 30 (Desarch's), not 60 - the copy booked twice as ours is taken off", r.get("s20_926") == [30, 0], r.get("s20_926"))
ck("rental LPOs ticked (20260103, 148, 150R1, 170); 20260109 (lost items bought) not rental",
   r.get("rental_flags") == {"IC/LPO/20260103": True, "IC/LPO/20260109": False, "IC/LPO/20260148": True, "IC/LPO/20260150R1": True,
                             "IC/LPO/20260170": True}, r.get("rental_flags"))
ck("20260148 and 20260170 read Delivered from what Rentals booked; 20260150R1 part (1 prop short); 20260103 still Ordered",
   r.get("lpo_status") == {"IC/LPO/20260148": "delivered", "IC/LPO/20260150R1": "part", "IC/LPO/20260170": "delivered", "IC/LPO/20260103": "ordered"},
   r.get("lpo_status"))
ck("the six non-materials are left exactly as they were (typed rental, no category) - only listed",
   len(r.get("services") or []) == 6 and all(t == "rental" and not c for _, t, c in r["services"]), r.get("services"))
alone = r

# ---- both orders with the purchasing correction ---------------------------------------------------------------------
DB1 = os.path.join(W, "rf_purch_first.db")
RR.build(DB1)
pay1, money1, mvp = table_hash(DB1, PAYROLL), money(DB1), movements(DB1)
rc, out = run(DB1, PURCH, "--apply"); ck("order 1: purchasing correction applies first", rc == 0, out[-800:])
rc, out = run(DB1, RENT); ck("order 1: rental dry run after it says the purchasing correction is already applied", rc == 0 and "has already been applied" in out, out[:600])
open(os.path.join(W, "dry_run_after_purchasing.txt"), "w").write(out)
n1 = n_changes(out)
rc, out = run(DB1, RENT, "--apply"); ck("order 1: rental correction applies", rc == 0 and n_changes(out) == n1, out[-800:])
h1 = table_hash(DB1, STORE)
rc, out = run(DB1, RENT, "--apply"); ck("order 1: rental again - nothing", rc == 0 and " 0  changes in all" in out and table_hash(DB1, STORE) == h1, out[-600:])
rc, out = run(DB1, PURCH, "--apply"); ck("order 1: purchasing again - nothing", rc == 0 and " 0  changes in all" in out, out[-600:])
ck("order 1: payroll and LPO money untouched", table_hash(DB1, PAYROLL) == pay1 and money(DB1) == money1)
r1 = read_app(DB1)

DB2 = os.path.join(W, "rf_rental_first.db")
RR.build(DB2)
rc, out = run(DB2, RENT, "--apply"); ck("order 2: rental correction applies first", rc == 0, out[-800:])
rc, out = run(DB2, PURCH, "--apply"); ck("order 2: purchasing correction applies after it", rc == 0, out[-1500:])
h2 = table_hash(DB2, STORE)
rc, out = run(DB2, PURCH, "--apply"); ck("order 2: purchasing again - nothing", rc == 0 and " 0  changes in all" in out, out[-600:])
rc, out = run(DB2, RENT, "--apply")
ck("order 2: rental again after the purchasing correction - only the LPO-named twins its requests were still waiting for",
   rc == 0 and n_changes(out) >= 0 and all(sec == "6 LPO-named twins" for sec in
                                           [l[3:-3] for l in out.splitlines() if l.startswith("== ") and "Not changed" not in l]), out[-900:])
h2 = table_hash(DB2, STORE)
rc, out = run(DB2, RENT, "--apply"); ck("order 2: rental a third time - nothing", rc == 0 and " 0  changes in all" in out and table_hash(DB2, STORE) == h2, out[-600:])
r2 = read_app(DB2)
for nm, rr in (("purchasing first", r1), ("rental first", r2)):
    ck(f"{nm}: Stock (Rental) = Rentals; no material ours and rental together; rental stock only on Rental materials",
       rr.get("same") and rr.get("both") == [] and rr.get("hired_not_rental") == [] and rr.get("owned_on_rental") == [],
       {k: rr.get(k) for k in ("same", "both", "hired_not_rental", "owned_on_rental")})
    ck(f"{nm}: 20260148 / 170 delivered, 150R1 delivered (1 prop closed by the purchasing correction)",
       rr.get("lpo_status", {}).get("IC/LPO/20260148") == "delivered" and rr.get("lpo_status", {}).get("IC/LPO/20260170") == "delivered"
       and rr.get("lpo_status", {}).get("IC/LPO/20260150R1") == "delivered", rr.get("lpo_status"))
ck("both orders end with the same rental stock in every place", r1.get("positions") == r2.get("positions") == alone.get("positions"),
   (len(r1.get("positions") or []), len(r2.get("positions") or [])))

print(f"\n{len(FAIL)} FAILED" if FAIL else "\nALL PASSED")
sys.exit(1 if FAIL else 0)

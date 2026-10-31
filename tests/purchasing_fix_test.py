"""The 31 Oct 2026 purchasing data correction (deploy/fix_purchasing_2026_10_31.py), run on a copy of the live
records (tests/purchasing_fix_replica.py): dry run writes nothing; --apply makes the changes; --apply again changes
nothing; payroll and LPO money untouched; the result read through the app is what the purchaser said.

    python3 tests/purchasing_fix_test.py [work-dir]"""
import hashlib, os, sqlite3, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import purchasing_fix_replica as R

W = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp()
DB = os.path.join(W, "fix_replica.db")
FAIL = []
def ck(l, ok, x=""):
    print(("PASS " if ok else "FAIL ") + l + ("" if ok else f"  [{str(x)[:600]}]"))
    if not ok: FAIL.append(l)

def run(*extra):
    env = dict(os.environ, INFINIA_NO_SCHED="1", INFINIA_NO_PUSH="1")
    env.pop("DATABASE_URL", None)
    p = subprocess.run([sys.executable, os.path.join(ROOT, "deploy", "fix_purchasing_2026_10_31.py"), "--database-url", f"sqlite:///{DB}", *extra],
                       cwd=os.path.join(ROOT, "app"), env=env, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr

def table_hash(tables):
    c = sqlite3.connect(DB); h = {}
    for t in tables:
        rows = c.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall()
        h[t] = hashlib.sha1(repr(rows).encode()).hexdigest()
    c.close(); return h

def money():
    c = sqlite3.connect(DB)
    out = {r[0]: r[1:] for r in c.execute("""SELECT o.ref, o.discount_pct, coalesce(o.round_off,0), o.tax_pct,
        (SELECT round(sum(l.qty*l.rate),4) FROM purchase_order_lines l WHERE l.order_id=o.id),
        (SELECT group_concat(l.id || ':' || l.qty || ':' || l.rate || ':' || l.tax_pct) FROM purchase_order_lines l WHERE l.order_id=o.id)
        FROM purchase_orders o""")}
    c.close(); return out

# refuses a database that is not the live one's shape: an older one without the new columns, one without the LPOs
import shutil
shutil.copy("/tmp/claude-0/full.db", DB)
rc, out = run()
ck("refuses a database without the new purchasing columns (app not deployed yet)", rc != 0 and "Refused" in out and "deploy" in out, out[-400:])
env = dict(os.environ, DATABASE_URL=f"sqlite:///{DB}", INFINIA_NO_SCHED="1", INFINIA_NO_PUSH="1")
subprocess.run([sys.executable, "-c", "import main; main._add_missing_columns()"], cwd=os.path.join(ROOT, "app"), env=env, capture_output=True)
rc, out = run()
ck("refuses a database that does not hold the questionnaire's LPOs", rc != 0 and "does not look like the live database" in out, out[-400:])

R.build(DB)
STORE = ["purchase_orders", "purchase_order_lines", "material_requests", "material_request_lines", "store_movements", "lpo_receipts",
         "rental_maps", "audit_log", "store_items", "suppliers"]
PAYROLL = [t for t in ("employees", "daily_rows", "employee_summaries", "salary_adjustments", "payroll_runs", "payroll_lines", "pay_payments",
                       "staff_loans", "loan_repayments", "staff_leave", "payslips", "petty_cash") if t]
before, pay0, money0 = table_hash(STORE), table_hash(PAYROLL), money()

rc, out = run()
ck("dry run runs", rc == 0, out[-1500:])
ck("dry run says nothing is written, and lists the changes", "DRY RUN - nothing is written" in out and "changes in all" in out, out[:400])
ck("dry run wrote nothing", table_hash(STORE) == before, "")
n_dry = int(out.split("changes in all")[0].rsplit("\n", 1)[-1].strip() or 0)
print(f"     (dry run: {n_dry} changes)")

rc, out = run("--apply")
ck("apply runs", rc == 0, out[-1500:])
n_app = int(out.split("changes in all")[0].rsplit("\n", 1)[-1].strip() or 0)
ck("apply makes exactly the changes the dry run listed", n_app == n_dry and n_app > 100, (n_dry, n_app))
c = sqlite3.connect(DB)
logs = c.execute("SELECT count(*) FROM audit_log WHERE action='purchasing_fix' AND details LIKE '%[purchasing questionnaire 31/10/2026]'").fetchone()[0]
ck("one activity-log entry per change, tagged", logs == n_app, (logs, n_app))
c.close()
ck("payroll untouched", table_hash(PAYROLL) == pay0)
ck("no money amount on any LPO changed", money() == money0)

after1 = table_hash(STORE)
rc, out = run("--apply")
ck("apply again: nothing changes", rc == 0 and " 0  changes in all" in out and table_hash(STORE) == after1, out[-800:])

# ---- what the app now says ---------------------------------------------------------------------------------------
os.environ["DATABASE_URL"] = f"sqlite:///{DB}"
os.environ.setdefault("INFINIA_NO_SCHED", "1"); os.environ.setdefault("INFINIA_NO_PUSH", "1")
sys.path.insert(0, os.path.join(ROOT, "app"))
os.chdir(os.path.join(ROOT, "app"))
import main as M, purchasing as P, models
from database import SessionLocal
db = SessionLocal()
book = P.Book(db)
st = {o.ref: book.of(o)["status"] for o in book.orders}
import importlib.util
spec = importlib.util.spec_from_file_location("fixmod", os.path.join(ROOT, "deploy", "fix_purchasing_2026_10_31.py"))
fx = importlib.util.module_from_spec(spec); spec.loader.exec_module(fx)
not_done = {f"IC/LPO/{n}": st.get(f"IC/LPO/{n}") for n in fx.FULL + fx.HIRE if st.get(f"IC/LPO/{n}") != "delivered"}
ck("every LPO the purchaser marked Full (and the two Desarch hires) reads Delivered", not not_done, not_done)
ck("20260157 cancelled; 20260152 / 159 still Ordered; 162 Part delivered; 163 / 164 Ordered",
   st.get("IC/LPO/20260157") == "cancelled" and st.get("IC/LPO/20260152") == "ordered" and st.get("IC/LPO/20260159") == "ordered"
   and st.get("IC/LPO/20260162") == "part" and st.get("IC/LPO/20260163") == "ordered" and st.get("IC/LPO/20260164") == "ordered",
   {k: st.get(k) for k in ("IC/LPO/20260157", "IC/LPO/20260152", "IC/LPO/20260159", "IC/LPO/20260162", "IC/LPO/20260163", "IC/LPO/20260164")})
mr = lambda r: db.query(models.MaterialRequest).filter(models.MaterialRequest.ref == r).first()
ck("MR-0038 closed - not needed", mr("MR-0038").status == "closed" and all((l.status or "") == "rejected" for l in mr("MR-0038").lines))
ck("MR-0040 / 0041 / 0045 left open for Amal", mr("MR-0040").status == "partial" and mr("MR-0041").status == "ordered" and mr("MR-0045").status == "ordered")
ck("MR-0045 now under its site 915 (was STORE)", mr("MR-0045").site == "915")
stock = M._stock_map(db)
ck("pump / temperature control no longer stock in the central store",
   abs(stock.get((3519, ""), 0)) < 1e-6 and abs(stock.get((3520, ""), 0)) < 1e-6 and abs(stock.get((3469, ""), 0)) < 1e-6,
   {k: v for k, v in stock.items() if k[0] in (3519, 3520, 3469)})
ck("black sand / aggregate / rebar / sockets moved to their sites",
   stock.get((583, "914")) == 5 and stock.get((583, "912")) == 1 and stock.get((583, "915")) == 1 and stock.get((84, "914")) == 1
   and stock.get((3527, "913")) == 2.88 and abs(stock.get((3528, "919"), 0) - 3.33) < 1e-6 and stock.get((3726, "906")) == 20
   and not stock.get((583, "")) and not stock.get((3726, "")),
   {k: v for k, v in stock.items() if k[0] in (583, 84, 3527, 3528, 3726)})
ck("wire nails of 20260166 (cost to 913) at 913", stock.get((3369, "913"), 0) >= 45)
ck("hired material not booked twice: Rental Prop 5.0M at 913 still 99, at 919 still 125",
   stock.get((3710, "913")) == 99 and stock.get((3710, "919")) == 125, (stock.get((3710, "913")), stock.get((3710, "919"))))
r1 = next(o for o in book.orders if o.ref == "IC/LPO/20260150R1")
props = next(x for x in book.of(r1)["lines"] if x["description"].startswith("M.D Props 3.20 to 5"))
ck("20260150R1 props: 99 came, 1 closed (damaged, returned)", props["delivered"] == 99 and props["closed"] == 1 and props["remaining"] == 0, props)
reqs ={r["ref"]: r for r in M.list_material_requests(db=db, user=db.query(models.User).filter(models.User.role == "admin").first())}
follow = [(r["ref"], l.get("item_name")) for r in reqs.values() if r["status"] not in ("delivered", "received", "closed", "rejected")
          for l in r["lines"] if (l.get("status") or "") != "rejected" and (l["qty_requested"] or 0) - (l["qty_received"] or 0) > 1e-6]
ck("Order follow-up: only the blocks (MR-0040/41/45) and the requests nobody has ordered are left; nothing of a delivered LPO",
   not any(ref in ("MR-0036", "MR-0037", "MR-0019", "MR-0057", "MR-0058", "MR-0059", "MR-0038") for ref, _ in follow), follow)
ck("the cancelled 20260157 is not on the store keeper's list",
   "IC/LPO/20260157" not in {o["ref"] for o in P.deliveries(show="all", db=db, user=None)["orders"]})
sites_of = {o["ref"]: o["deliver_to"] for o in P.deliveries(show="all", db=db, user=None)["orders"]}
ck("the store keeper's list holds the October LPOs, each to its site", sites_of.get("IC/LPO/20260118") == "913" and sites_of.get("IC/LPO/20260154") == "STORE")
db.close()
print(f"\n{len(FAIL)} FAILED" if FAIL else "\nALL PASSED")
sys.exit(1 if FAIL else 0)

"""Appendix A (previous payments): the Sl No is always worked out by the app, never typed (28/11/2026).

Reported: "Payment Application No 10" put in on row 20 had a blank Sl No - it should have read 15. Rule: every line
with words in the description AND something in the amount is numbered in order from 1 (row 5, Initial Advance
Payment); a heading or blank line ("Previous Payments", no amount) gets none and the count carries on past it; the
total row and everything below it is never touched. Renumbered on every save - typed, added (by the office or by
the app at roll-over), removed or moved - and when a bill still being made is opened.
    python3 tests/make_ipa_appa_sn.py /tmp/claude-0/bills/appa-sn.xlsx
    python3 tests/run_all.py bill_appa_sn
"""
import os, sys, subprocess, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.getcwd())
X = "/tmp/claude-0/bills/appa-sn.xlsx"
if not os.path.exists(X):
    os.makedirs(os.path.dirname(X), exist_ok=True)
    subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "make_ipa_appa_sn.py"), X], check=True, capture_output=True)
import database, models, auth
models.Base.metadata.create_all(database.engine)
from fastapi.testclient import TestClient
import main as M
import est_bills as EB, est_bills_engine as BE
db = database.SessionLocal()
if not db.query(models.User).filter_by(username="admin").first():
    db.add(models.User(username="admin", hashed_password=auth.hash_password("changeme123"), full_name="Administrator", role="admin")); db.commit()
c = TestClient(M.app); c.__enter__()
FAIL = []


def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:500]}"))
    if not ok:
        FAIL.append(n)


H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
meta = c.get("/store/est/meta", headers=H).json()
if not meta.get("projects"):
    c.post("/store/est/projects", headers=H, json={"code": "913", "name": "Asif Akbar villa", "client": "Asif Akbar"})
    meta = c.get("/store/est/meta", headers=H).json()
pid = meta["projects"][-1]["id"]
r = c.post("/store/est/ipa/format", headers=H, data={"project_id": str(pid)}, files={"file": ("appa-sn.xlsx", open(X, "rb").read(), "application/octet-stream")})
ck("the workbook is taken", r.status_code == 200, r.text)
fid = r.json()["id"]
bid = c.post("/store/est/ipa/new", headers=H, json={"project_id": pid, "format_id": fid}).json()["id"]


def col_a():
    db.expire_all()
    b = db.get(EB.EstBill, bid); fmt = db.get(EB.EstBillFormat, b.format_id)
    inp = EB._inputs(b); m = EB._bill_model(fmt, inp); v = BE.calculate(m, inp).get("APP A", {})
    t = next(p for p in m["map"]["payments"] if p["sheet"] == "APP A")
    rows = {rr: (v.get(f"{rr},1"), v.get(f"{rr},2"), v.get(f"{rr},5")) for rr in range(t["head_row"] + 1, t["total_row"] + 3)}
    return rows, t


def put(cells):
    return c.put(f"/store/est/ipa/bill/{bid}", headers=H, json={"set": {"APP A": cells}})


def nums(rows):
    return {rr: x[0] for rr, x in rows.items() if x[0] not in (None, "")}


rows, t = col_a()
ck("the table is found: header row 4, total row 24", t["head_row"] == 4 and t["total_row"] == 24, t)
ck("the Sl No column is A (headed 'Sl No')", BE.pay_sn_col(c and EB._bill_model(db.get(EB.EstBillFormat, fid), {}), t) == 1)
n = nums(rows)
ck("Initial Advance Payment on row 5 is 1, the four bills after it 2-5", [n.get(x) for x in range(5, 10)] == [1, 2, 3, 4, 5], n)
ck("the 'Previous Payments' heading (no amount) has no number", 10 not in n, rows[10])
ck("...and the count carries on past it: row 11 is 6, row 18 is 13", n.get(11) == 6 and n.get(18) == 13, n)
ck("a line with no money yet (Payment Application No 13) has no number", 19 not in n, rows[19])
ck("the total row and the note under it are never touched (the note keeps its 99)",
   24 not in n and rows.get(26, (None,))[0] == 99, (rows.get(24), rows.get(26)))

# the reported case: the next bill's line put in with its amount -> it reads the next number
r = put({"19,5": 213000})
rows, _ = col_a(); n = nums(rows)
ck("money typed on Payment Application No 13: it becomes 14", r.status_code == 200 and n.get(19) == 14, (r.status_code, n.get(19)))
r = put({"20,2": "Payment Application No 14", "20,3": 45980, "20,5": 214000})
rows, _ = col_a(); n = nums(rows)
ck("a new line typed on row 20 with its amount reads 15 at once", r.status_code == 200 and n.get(20) == 15, n.get(20))

# a number typed by hand is the app's again on the next save
r = put({"12,1": 42})
rows, _ = col_a(); n = nums(rows)
ck("a Sl No typed by hand is put right on saving (row 12 back to 7)", n.get(12) == 7, n.get(12))

# removed: the amount taken off a line -> no number, everything after moves up
r = put({"7,5": ""})
rows, _ = col_a(); n = nums(rows)
ck("a line's amount taken off: it loses its number, the next ones move up (row 8 = 3, row 20 = 14)", 7 not in n and n.get(8) == 3 and n.get(20) == 14, n)
put({"7,5": 182000})
rows, _ = col_a(); n = nums(rows)
ck("...put back: numbered again, row 20 back to 15", n.get(7) == 3 and n.get(20) == 15, n)

# a row put in above (the office inserting a line in the table): all below are renumbered
r = c.post(f"/store/est/ipa/bill/{bid}/rows", headers=H, json={"sheet": "APP A", "at": 12, "n": 1})
ck("a row is put in at row 12", r.status_code == 200, r.text)
rows, t2 = col_a(); n = nums(rows)
ck("...the empty new row has no number; the line it pushed down keeps 7 on row 13", 12 not in n and n.get(13) == 7, n)
r = put({"12,2": "Payment Application No 5A", "12,5": 5000})
rows, t2 = col_a(); n = nums(rows)
ck("...filled in, it is 7 and every line under it moves on one (last line 16 on row 21)", n.get(12) == 7 and n.get(13) == 8 and n.get(21) == 16 and t2["total_row"] == 25, (n, t2["total_row"]))
ck("...the total row has moved down with it and still has no number", 25 not in n)

# a heading typed in the middle (words, no amount): no number, the count carries on
put({"22,2": "Retention released", "22,5": ""})
rows, _ = col_a(); n = nums(rows)
ck("a heading typed in (words, no amount) gets no number", 22 not in n and n.get(21) == 16, n)

# a line with a formula for its amount counts as a payment line
put({"23,2": "Advance recovery adjustment", "23,5": "=-E5*0.1"})
rows, _ = col_a(); n = nums(rows)
ck("a line whose amount is a formula is numbered (17)", n.get(23) == 17, (n.get(23), rows.get(23)))

# opening a bill still being made numbers it too (a bill saved before this change)
db.expire_all()
b = db.get(EB.EstBill, bid); inp = EB._inputs(b); inp["APP A"]["21,1"] = ""; b.inputs = EB.json.dumps(inp); db.commit()
rows, _ = col_a()
ck("(a bill left without the number, as before this change)", rows[21][0] in (None, ""), rows[21])
c.get(f"/store/est/ipa/bill/{bid}", headers=H)
rows, _ = col_a(); n = nums(rows)
ck("...opening it on screen numbers it (row 21 = 16) and keeps it", n.get(21) == 16, n.get(21))

# the next bill (roll-over): the line the app adds itself is numbered once it has money
c.post(f"/store/est/ipa/bill/{bid}/status", headers=H, json={"status": "Approved"})
bid0 = bid
bid = c.post("/store/est/ipa/new", headers=H, json={"project_id": pid, "format_id": fid}).json()["id"]
rows, t3 = col_a(); n = nums(rows)
seq = [n[k] for k in sorted(n) if t3["head_row"] < k < t3["total_row"]]
ck("the next bill: numbers run 1, 2, 3 ... with no gap and no repeat", seq == list(range(1, len(seq) + 1)), seq)
ck("...every numbered line has words and an amount; every line with both is numbered",
   all((isinstance(x[1], str) and x[1].strip() and x[2] not in (None, "")) == (x[0] not in (None, "")) for k, x in rows.items() if t3["head_row"] < k < t3["total_row"]),
   {k: x for k, x in rows.items() if t3["head_row"] < k < t3["total_row"]})

# a signed bill is never renumbered on opening
db.expire_all()
b0 = db.get(EB.EstBill, bid0); before = b0.inputs
c.get(f"/store/est/ipa/bill/{bid0}", headers=H)
db.expire_all()
ck("an approved bill is not changed on opening", db.get(EB.EstBill, bid0).inputs == before)

# the rule on its own: no Sl No column -> nothing written
m = EB._bill_model(db.get(EB.EstBillFormat, fid), {})
fake = {"map": {"payments": [{"sheet": "APP A", "head_row": 4, "total_row": 24, "cols": {"desc": 1, "amount": 5}}]}, "sheets": m["sheets"]}
ck("a table with nothing left of the description is left alone", BE.with_pay_numbers(fake, {}) == {})
print("\nALL PASS" if not FAIL else f"\n{len(FAIL)} FAILED")
sys.exit(1 if FAIL else 0)

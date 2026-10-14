"""October check: portal lines 1-14 Oct already typed into Zoho are found
(same date + amount, paid from the book's account) and, once confirmed,
never sent."""
import os, sys, tempfile
from datetime import date
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
os.environ["INFINIA_CRED_KEY_FILE"] = tempfile.mktemp(suffix=".key")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as M, models, zohoapi as Z, zohosync, credentials
from database import SessionLocal, engine
models.Base.metadata.create_all(bind=engine); M._add_missing_columns()
s = SessionLocal(); fails = 0
def ok(c, m):
    global fails
    print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1
ZE = {"expenses": [
        {"expense_id": "E1", "date": "2026-10-10", "total": 66.05, "account_name": "Office Pantry Expenses", "paid_through_account_name": "Company Petty Cash", "vendor_name": "NOON", "reference_number": "AJJ2593601"},
        {"expense_id": "E2", "date": "2026-10-10", "total": 40.0, "account_name": "Office Pantry Expenses", "paid_through_account_name": "Company Petty Cash", "vendor_name": "Riviere"},
        {"expense_id": "E3", "date": "2026-10-09", "total": 120.0, "account_name": "DM Service Fee", "paid_through_account_name": "ADCB"}],
      "journals": [], "banktransactions": [{"transaction_id": "T1", "date": "2026-10-12", "amount": 1000, "offset_account_name": "Company Petty Cash"}]}
CALLS = []
def fake(db_, method, path, params=None, body=None):
    CALLS.append((path, params))
    if method == "GET" and path in ZE:
        return {path: ZE[path], "page_context": {"has_more_page": False}}
    return {}
Z.call = fake
M.put_setting(s, "zoho_refresh", credentials.lock("rt")); M.put_setting(s, "zoho_start", "2026-10-01"); s.commit()
u = models.User(username="ca", full_name="CA", hashed_password="x", role="admin"); s.add(u); s.commit()
def line(**k):
    x = models.PettyCash(zoho_status="", **k); s.add(x); s.commit(); return x
a = line(book="office", on_date=date(2026, 10, 10), description="Cleaning clothes", supplier="NOON", paid=66.05)
b = line(book="office", on_date=date(2026, 10, 10), description="Water", paid=40)
c = line(book="site", on_date=date(2026, 10, 9), description="DM fee", paid=120)          # in Zoho but paid via ADCB
d = line(book="office", on_date=date(2026, 10, 11), description="Not typed", paid=55)
e = line(book="office", on_date=date(2026, 10, 15), description="After changeover", paid=66.05)
f = line(book="office", on_date=date(2026, 10, 12), description="From Jomon", received=1000)
done = line(book="office", on_date=date(2026, 10, 10), description="Marked before", paid=66.05); done.zoho_status = "inzoho"; s.commit()
r = zohosync.october(s, u)
R = {x["id"]: x for x in r["rows"]}
ok(e.id not in R and done.id not in R, "only 1-14 Oct lines not yet marked are checked")
ok(R[a.id]["match"]["id"] == "E1" and R[a.id]["sure"], "NOON 66.05 found in Zoho, paid from Company Petty Cash - ticked")
ok(R[b.id]["match"]["id"] == "E2", "water 40.00 found")
ok(R[c.id]["match"] and not R[c.id]["sure"], "same date and amount but paid from another account: shown, not ticked - he checks")
ok(R[d.id]["match"] is None, "not in Zoho: will be sent")
ok(R[f.id]["match"]["kind"] == "banktransactions", "cash received found as a transfer")
ok(r["matched"] == 4 and r["missing"] == 1, f"4 found, 1 missing ({r['matched']}, {r['missing']})")
n = len(CALLS); zohosync.october(s, u)
ok(len(CALLS) == n, "a second look uses the kept read - no new calls to Zoho")
zohosync.october_confirm({"items": [{"id": a.id, "label": "Expense", "zid": "E1"}, {"id": f.id, "label": "Transfer", "zid": "T1"}]}, s, u)
s.refresh(a); s.refresh(f)
ok(a.zoho_status == "inzoho" and "#E1" in a.zoho_ref, "confirmed: marked in Zoho with the entry it matched")
ok(all(x.id not in (a.id, f.id) for x in zohosync._waiting(s)), "confirmed lines are not on the list to send")
r2 = zohosync.october(s, u)
ok(all(x["match"] is None or x["match"]["id"] != "E1" for x in r2["rows"]), "a Zoho entry already matched is not offered again")
print("fails=", fails)

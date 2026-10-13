"""Staff loans paid from ADCB / Cash go to Zoho's Employee Advance once (stand-in Zoho)."""
import os, sys, tempfile, time
from datetime import date
db = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{db}"
os.environ["INFINIA_CRED_KEY_FILE"] = tempfile.mktemp(suffix=".key")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as M, models, zohoapi as Z, zohosync, credentials
from database import SessionLocal, engine
from fastapi import HTTPException
models.Base.metadata.create_all(bind=engine); M._add_missing_columns()
s = SessionLocal()
fails = 0
def ok(c, m):
    global fails
    print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1
ACC = {"ADCB": "B", "Cash": "CA", "Employee Advance": "EA"}
POSTED, EXIST = [], []
def fake(db_, method, path, params=None, body=None):
    if path == "chartofaccounts":
        return {"chartofaccounts": [{"account_name": k, "account_id": v} for k, v in ACC.items()], "page_context": {}}
    if method == "GET" and path == "journals":
        return {"journals": [j for j in EXIST if j["reference_number"] == params.get("reference_number")]}
    if method == "POST" and path == "journals":
        POSTED.append(body)
        return {"journal": {"journal_id": f"J{len(POSTED)}"}}
    return {}
Z.call = fake
M.put_setting(s, "zoho_refresh", credentials.lock("rt")); M.put_setting(s, "zoho_start", "2026-10-01"); s.commit()
u = models.User(username="ca", full_name="CA", hashed_password="x", role="admin"); s.add(u)
e = models.Employee(emp_no="1001", name="Ravi Kumar"); s.add(e); s.commit()

def add(**k):
    p = {"emp_no": "1001", "amount": 1000, "taken_on": "2026-10-05"}; p.update(k)
    return M.add_loan(p, s, u)

# where it was paid from
try:
    add(paid_from="Bank"); ok(False, "unknown 'paid from' refused")
except HTTPException:
    ok(True, "unknown 'paid from' refused")
a = add(amount=2500, paid_from="ADCB")
c = add(amount=300.5, paid_from="Cash", taken_on="2026-10-07")
p = add(amount=400, paid_from="petty")
n = add(amount=700)                                     # not said - stays out of Zoho
old = add(amount=900, paid_from="ADCB", taken_on="2026-09-20")   # before the start date
w = zohosync.loans(s, u)["rows"]
ok(sorted(r["id"] for r in w) == sorted([a["id"], c["id"]]),
   "only ADCB/Cash loans from 1 Oct wait (petty goes with its book line; blank and September stay out)")

r = zohosync.send_loans({}, s, u)
ok(r["sent"] == 2 and not r["failed"], f"two journals sent ({r})")
J = {b["reference_number"]: b for b in POSTED}
ja = J[f"LN-{a['id']}"]
ok([(l["account_id"], l["debit_or_credit"], l["amount"]) for l in ja["line_items"]] == [("EA", "debit", 2500), ("B", "credit", 2500)]
   and ja["journal_date"] == "2026-10-05" and "1001 Ravi Kumar" in ja["notes"], "ADCB loan: Employee Advance debit / ADCB credit, dated, named")
jc = J[f"LN-{c['id']}"]
ok([(l["account_id"], l["debit_or_credit"], l["amount"]) for l in jc["line_items"]] == [("EA", "debit", 300.5), ("CA", "credit", 300.5)],
   "Cash loan: Employee Advance debit / Cash credit")
ok(sum(l["amount"] for l in ja["line_items"] if l["debit_or_credit"] == "debit") ==
   sum(l["amount"] for l in ja["line_items"] if l["debit_or_credit"] == "credit"), "journal balances")

# sent once
r2 = zohosync.send_loans({}, s, u)
ok(r2["sent"] == 0 and len(POSTED) == 2, "pressing Send again sends nothing")
la = s.query(models.StaffLoan).get(a["id"]); s.refresh(la)
ok(la.zoho_status == "sent" and la.zoho_id == "journal:J1", "loan marked sent with its Zoho journal")

# guards once in Zoho
for what, pay in (("amount", {"amount": 3000}), ("date", {"taken_on": "2026-10-06"}), ("paid from", {"paid_from": "Cash"})):
    try:
        M.edit_loan(a["id"], pay, s, u); ok(False, f"{what} change refused once in Zoho")
    except HTTPException as ex:
        ok("in Zoho" in ex.detail, f"{what} change refused once in Zoho")
M.edit_loan(a["id"], {"instalment": 500, "notes": "monthly", "amount": 2500}, s, u)
s.refresh(la)
ok(la.instalment == 500, "instalment and notes still editable (same amount passes)")
try:
    M.delete_loan(a["id"], s, u); ok(False, "delete refused once in Zoho")
except HTTPException:
    ok(True, "delete refused once in Zoho")
M.edit_loan(n["id"], {"amount": 750}, s, u)
ok(s.query(models.StaffLoan).get(n["id"]).amount == 750, "loan not in Zoho edits freely")

# a try that died after Zoho saved it: found, not sent twice
d = add(amount=1200, paid_from="ADCB", taken_on="2026-10-10")
ld = s.query(models.StaffLoan).get(d["id"])
ld.zoho_status, ld.zoho_err = "sending", f"sending@{int(time.time()) - 600}"; s.commit()
EXIST.append({"journal_id": "JX", "reference_number": f"LN-{d['id']}"})
r3 = zohosync.send_loans({}, s, u); s.refresh(ld)
ok(r3["sent"] == 1 and len(POSTED) == 2 and ld.zoho_id == "journal:JX", "stuck 'sending' line found in Zoho by LN-id, not posted again")

# a fresh 'sending' (another press in progress) is left alone
f = add(amount=50, paid_from="Cash", taken_on="2026-10-11")
lf = s.query(models.StaffLoan).get(f["id"])
lf.zoho_status, lf.zoho_err = "sending", f"sending@{int(time.time())}"; s.commit()
zohosync.send_loans({}, s, u)
ok(len(POSTED) == 2, "a line another press is sending right now is not sent again")

# Zoho refuses: reason kept, line waits
del ACC["Cash"]
g = add(amount=80, paid_from="Cash", taken_on="2026-10-12")
for k in list(getattr(Z, "_CACHE", {}) or {}):
    Z._CACHE.pop(k, None)
r4 = zohosync.send_loans({"ids": [g["id"]]}, s, u)
lg = s.query(models.StaffLoan).get(g["id"])
ok(r4["sent"] == 0 and lg.zoho_status == "" and "Cash" in lg.zoho_err and len(POSTED) == 2,
   f"Zoho has no Cash account: nothing posted, line waits with the reason ({lg.zoho_err})")
print("fails=", fails)

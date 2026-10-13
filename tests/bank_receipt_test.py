"""Client receipts on Bank fill Project payments (net of VAT) and stay in
step; a line can never be sent to Zoho twice."""
import os, sys, tempfile, json
from datetime import date, timedelta
db = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{db}"
os.environ["INFINIA_CRED_KEY_FILE"] = tempfile.mktemp(suffix=".key")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as M, models, zohoapi as Z, bank, projectpay as pp, credentials
from database import SessionLocal, engine
from fastapi import HTTPException
models.Base.metadata.create_all(bind=engine); M._add_missing_columns()
s = SessionLocal()
fails = 0
def ok(c, m):
    global fails
    print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1
u = models.User(username="ca", hashed_password="x", full_name="CA", role="office", permissions="accounts_bank,accounts_zoho,accounts_projects")
s.add(u); s.commit()
sc = pp.ProjectScope(project="913", scope="DESIGN & BUILD", contract=2_000_000)
sc.payments = [pp.ProjectPayment(on_date=date(2026, 9, 5), amount=699752.38, note="IPA08")]
s.add(sc); s.commit()
def body(**k):
    b = {"kind": "customer", "date": "2026-10-08", "party": "FARIDA AKBARALI", "amount": 989148, "reference": "000102",
         "mode": "Cheque", "scope_id": sc.id, "net_amount": 942045.71, "docs": [{"id": "INV9", "number": "IC/26/913/IPA09", "amount": 989148}]}
    b.update(k); return b
r = bank.add(body(), db=s, user=u)
x = s.get(models.BankEntry, r["id"]); s.refresh(sc)
line = s.get(pp.ProjectPayment, x.pp_id)
ok(line and line.amount == 942045.71 and line.scope_id == sc.id and line.source == f"bank:{x.id}" and "IPA09" in line.note,
   "receipt added to Project payments net of VAT, marked as from Bank")
bank.edit(x.id, body(amount=989000, net_amount=941904.76, docs=[{"id": "INV9", "number": "IC/26/913/IPA09", "amount": 989000}]), db=s, user=u)
s.refresh(line)
ok(line.amount == 941904.76 and s.query(pp.ProjectPayment).filter(pp.ProjectPayment.source.like("bank:%")).count() == 1, "changing the receipt changes that tracker line (no second line)")
# The tracker may not change or drop the Bank line, but other edits keep it.
pays = [{"date": "2026-09-05", "amount": 699752.38, "note": "IPA08"}, {"date": "2026-10-08", "amount": 941904.76, "note": line.note}]
pp.edit_scope(sc.id, {"project": "913", "scope": "DESIGN & BUILD", "contract": 2_000_000, "payments": pays + [{"date": "2026-10-10", "amount": 100, "note": "x"}]}, db=s, user=u)
s.refresh(sc)
ok(any(p.id == x.pp_id for p in sc.payments) and len(sc.payments) == 3, "tracker edit elsewhere keeps the Bank line (same id)")
try:
    pp.edit_scope(sc.id, {"project": "913", "scope": "DESIGN & BUILD", "contract": 2_000_000, "payments": pays[:1]}, db=s, user=u)
    ok(False, "tracker cannot drop a Bank payment")
except HTTPException as e:
    ok("Accounts > Bank" in e.detail, "tracker cannot drop a Bank payment")
s.rollback()
try:
    bank.add(body(amount=500000, net_amount=476190.48, reference="X1", docs=[]), db=s, user=u)
    ok(False, "over the contract refused")
except HTTPException as e:
    ok("past its contract" in e.detail, "a receipt taking the scope past its contract is refused, nothing saved")
s.rollback()
ok(s.query(models.BankEntry).count() == 1, "the refused receipt left nothing behind")
try:
    bank.add(body(net_amount=999999999), db=s, user=u)
    ok(False, "net more than received refused")
except HTTPException:
    ok(True, "net more than the amount received refused")
s.rollback()
fut = (M._dubai_today() + timedelta(days=20)).isoformat()
r2 = bank.add(body(date=fut, amount=105, net_amount=100, reference="000200", docs=[]), db=s, user=u)
x2 = s.get(models.BankEntry, r2["id"])
ok(x2.pp_id is None, "post-dated client cheque waits - not on Project payments before its date")
try:
    bank.add(body(mode="Bank Transfer", date=fut, reference="PHUB1", docs=[]), db=s, user=u)
    ok(False, "future transfer refused")
except HTTPException as e:
    ok("future" in e.detail, "a transfer dated in the future is refused (only cheques may)")
s.rollback()
bank.delete(x.id, db=s, user=u)
ok(s.query(pp.ProjectPayment).filter(pp.ProjectPayment.source == f"bank:{x.id}").count() == 0, "removing the receipt removes its tracker line")

# ---- never twice -------------------------------------------------------------
M.put_setting(s, "zoho_refresh", credentials.lock("rt")); s.commit()
calls = []
def fake(db_, method, path, params=None, body=None):
    if path == "chartofaccounts":
        return {"chartofaccounts": [{"account_name": "ADCB", "account_id": "B"}], "page_context": {}}
    if method == "GET" and path == "customerpayments":
        return {"customerpayments": [{"payment_id": "OLD1", "description": f"[BK-{x2.id}] FARIDA"}]}
    if method == "GET":
        return {}
    calls.append(path)
    return {"payment": {"payment_id": "CP9", "payment_number": "77"}}
Z.call = fake
y = s.get(models.BankEntry, x2.id)
ok(Z.claim(s, models.BankEntry, y, ("",)), "first press takes the line")
ok(not Z.claim(s, models.BankEntry, y, ("",)), "a second press at the same time does not")
y.zoho_status, y.zoho_err, y.party_id = "", "", "C1"; s.commit()
sent, failed = bank._send(s, [y], u)
ok(sent == 1 and calls == ["customerpayments"], "sent once")
sent, failed = bank._send(s, [y], u)
ok(sent == 0 and calls == ["customerpayments"], "pressing Send again sends nothing more")
# A try that got no answer: Zoho is asked first and the existing entry is found.
y.zoho_status, y.zoho_err, y.zoho_id = "", "No answer from Zoho (timeout)", ""; s.commit()
sent, failed = bank._send(s, [y], u)
s.refresh(y)
ok(sent == 1 and calls == ["customerpayments"] and y.zoho_id == "customerpayment:OLD1", "after a timeout, the entry already in Zoho is found - not sent twice")
print("fails=", fails)

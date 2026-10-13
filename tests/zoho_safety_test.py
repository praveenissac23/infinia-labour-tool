"""Never twice, never wrong: the cases an independent review found
(stand-in Zoho). Each must hold before money goes through the link."""
import os, sys, tempfile, time, json
from datetime import date
db = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{db}"
os.environ["INFINIA_CRED_KEY_FILE"] = tempfile.mktemp(suffix=".key")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as M, models, zohoapi as Z, zohosync, bank, pettycash, invzoho, accounts as A, credentials
from database import SessionLocal, engine
from fastapi import HTTPException
models.Base.metadata.create_all(bind=engine); M._add_missing_columns(); A.create_tables(engine)
s = SessionLocal()
fails = 0
def ok(c, m):
    global fails
    print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1
def refused(fn, *a):
    try:
        fn(*a); return ""
    except HTTPException as e:
        return e.detail or "refused"

ACC = {"ADCB": "B", "Site Petty Cash": "S", "Bank Fees and Charges": "BF", "Authority Payment": "AP", "Progressive Payments": "INC", "Employee Advance": "EA"}
POSTED, EXIST = [], []
SEARCH_BROKEN = [False]
TAXES = [{"tax_name": "Standard Rate", "tax_percentage": 5, "tax_id": "V5"}, {"tax_name": "Zero Rate", "tax_percentage": 0, "tax_id": "V0"}]
def fake(db_, method, path, params=None, body=None):
    params = params or {}
    if path == "chartofaccounts":
        return {"chartofaccounts": [{"account_name": k, "account_id": v, "account_type": "income" if k == "Progressive Payments" else "x"} for k, v in ACC.items()], "page_context": {}}
    if path == "projects":
        return {"projects": []}
    if path == "settings/taxes":
        return {"taxes": TAXES}
    if path == "contacts":
        return {"contacts": [{"contact_id": "C1", "contact_name": "Emkaan Design LLC"}, {"contact_id": "V1", "contact_name": "Al Raida Trading"}]}
    if method == "GET" and path in ("expenses", "journals", "banktransactions", "vendorpayments", "customerpayments", "invoices"):
        if SEARCH_BROKEN[0]:
            raise Z.ZohoError(500, "search failed")
        tok = next(iter(v for k, v in params.items() if k not in ("per_page",)), "")
        return {path: [e for e in EXIST if e["_path"] == path and tok and tok in (e.get("reference_number", "") + " " + e.get("description", ""))]}
    if method == "POST":
        POSTED.append((path, body))
        n = str(len(POSTED))
        return {"expense": {"expense_id": "E" + n}, "journal": {"journal_id": "J" + n}, "banktransaction": {"transaction_id": "T" + n},
                "vendorpayment": {"payment_id": "VP" + n, "payment_number": n}, "payment": {"payment_id": "CP" + n},
                "invoice": {"invoice_id": "I" + n, "total": round(sum(l["rate"] * (1.05 if l.get("tax_id") == "V5" else 1) for l in body.get("line_items", [])), 2)}}
    return {}
Z.call = fake
M.put_setting(s, "zoho_refresh", credentials.lock("rt")); M.put_setting(s, "zoho_start", "2026-10-01"); s.commit()
chief = models.User(username="chief", full_name="Chief", hashed_password="x", role="admin"); s.add(chief); s.commit()

# 1. A petty line changed after it went to Zoho is confirmed, not posted again.
p = models.PettyCash(book="site", on_date=date(2026, 10, 9), description="Cement", site="913", paid=1000, zoho_status="approved",
                     zoho_account="01. Preliminaries Including Mobilization › Authority Payments")
ACC["Authority Payments"] = "AP2"
s.add(p); s.commit()
Z.push_many(s, [p]); s.refresh(p)
n0 = len(POSTED)
ok(p.zoho_status == "sent" and n0 == 1, "petty line sent once")
pettycash.edit_petty_cash(p.id, {"date": "2026-10-09", "description": "Cement", "site": "913", "paid": 1100}, s, chief); s.refresh(p)
ok(p.zoho_status == "changed", "edited after Zoho -> flagged 'changed'")
r0 = zohosync.approve({"lines": [{"id": p.id, "account": p.zoho_account}]}, s, chief); s.refresh(p)
ok(len(POSTED) == n0 and p.zoho_status == "changed" and r0["refused"], "plain approve of a changed line is refused - nothing posted")
zohosync.approve({"lines": [{"id": p.id, "corrected": True}]}, s, chief); s.refresh(p)
ok(len(POSTED) == n0 and p.zoho_status == "sent" and "corrected" in p.zoho_ref, "Corrected in Zoho confirms it - nothing posted twice")
ok(refused(zohosync.mark, {"ids": [p.id], "status": ""}, s, chief), "a line in Zoho cannot be put back to waiting (would send twice)")

# 2/3. Timeout after Zoho saved it: edits blocked, next send finds it.
q = models.PettyCash(book="site", on_date=date(2026, 10, 10), description="Sand", site="913", paid=500, zoho_status="approved",
                     zoho_account="01. Preliminaries Including Mobilization › Authority Payments",
                     zoho_err="No answer from Zoho (ReadTimeout) - press Send again; Zoho is checked first")
s.add(q); s.commit()
EXIST.append({"_path": "expenses", "expense_id": "EX9", "reference_number": f"PC-{q.id}"})
ok("did not answer" in refused(pettycash.edit_petty_cash, q.id, {"date": "2026-10-10", "description": "Sand", "site": "913", "paid": 600}, s, chief),
   "petty line in doubt: change refused, even for the chief accountant")
ok("did not answer" in refused(pettycash.delete_petty_cash, q.id, s, chief), "petty line in doubt: delete refused")
zohosync.retry({}, s, chief); s.refresh(q)
ok(q.zoho_status == "sent" and q.zoho_id == "expense:EX9" and len(POSTED) == n0, "send again finds it in Zoho by PC-id - not posted twice")

# 7. A line left 'sending' by a request that died is picked up (and checked).
r = models.PettyCash(book="site", on_date=date(2026, 10, 11), description="Nails", site="913", paid=40, zoho_status="sending",
                     zoho_err=f"sending@{int(time.time()) - 900}", zoho_account="01. Preliminaries Including Mobilization › Authority Payments")
s.add(r); s.commit()
pend = [x["id"] for x in zohosync.queue(s, chief)["pending"]]
ok(r.id in pend, "a stuck 'sending' line is shown as pending")
zohosync.retry({}, s, chief); s.refresh(r)
ok(r.zoho_status == "sent" and len(POSTED) == n0 + 1, "stuck line: checked, not found, sent once")

# 8. Zoho search fails: never sent blind, stays blocked.
t = models.PettyCash(book="site", on_date=date(2026, 10, 12), description="Wire", site="913", paid=75, zoho_status="approved",
                     zoho_err="No answer from Zoho (ConnectError) - press Send again; Zoho is checked first",
                     zoho_account="01. Preliminaries Including Mobilization › Authority Payments")
s.add(t); s.commit()
SEARCH_BROKEN[0] = True
n1 = len(POSTED)
zohosync.retry({"ids": [t.id]}, s, chief); s.refresh(t)
ok(len(POSTED) == n1 and t.zoho_status == "approved" and t.zoho_err.startswith("Could not check"), "Zoho search failed -> not sent, reason kept")
ok("did not answer" in refused(pettycash.edit_petty_cash, t.id, {"date": "2026-10-12", "description": "Wire", "site": "913", "paid": 80}, s, chief),
   "still blocked from edits after a failed check")
SEARCH_BROKEN[0] = False

# Bank
def bk(**k):
    x = models.BankEntry(**bank._clean(k), bank="ADCB"); s.add(x); s.commit(); return x
v = bk(kind="charge", date="2026-10-06", amount=26.25, reference="TT fee", notes="N" * 290)
bank._send(s, [v], chief); s.refresh(v)
body = POSTED[-1][1]
ok(v.zoho_status == "sent" and body["description"].startswith(f"[BK-{v.id}] "), "4. BK-id tag is first in the description, never cut off by long notes")
w = bk(kind="charge", date="2026-10-07", amount=10.5, reference="fee 2")
w.zoho_err = "No answer from Zoho (ReadTimeout) - press Send again; Zoho is checked first"; s.commit()
ok("did not answer" in refused(bank.edit, w.id, {"kind": "charge", "date": "2026-10-07", "amount": 11, "reference": "fee 2"}, s, chief),
   "2. bank line in doubt: edit refused (the warning cannot be wiped)")
ok("did not answer" in refused(bank.delete, w.id, s, chief), "bank line in doubt: delete refused")
EXIST.append({"_path": "banktransactions", "transaction_id": "TX5", "description": f"[BK-{w.id}] fee 2"})
n2 = len(POSTED)
bank.send({}, s, chief); s.refresh(w)
ok(w.zoho_status == "sent" and w.zoho_id.endswith("TX5") and len(POSTED) == n2, "send checks Zoho first and links it - not posted twice")
c = bk(kind="charge", date="2026-10-08", amount=5, reference="fee 3")
c.zoho_status, c.zoho_err = "cancelled", "Deleted in Zoho (13 Oct 2026)"; s.commit()
n3 = len(POSTED)
bank.send({}, s, chief); s.refresh(c)
ok(len(POSTED) == n3 and c.zoho_status == "cancelled", "5. a line deleted in Zoho is not sent again by Send")
old = bk(kind="charge", date="2026-09-28", amount=7, reference="Sept fee")
sent, failed = bank._send(s, [old], chief); s.refresh(old)
ok(sent == 0 and failed and "Dated before" in failed[0]["why"] and old.zoho_status == "", "6. a September bank line is not sent (start 1 Oct)")
st = bk(kind="charge", date="2026-10-09", amount=3, reference="stuck")
st.zoho_status, st.zoho_err = "sending", f"sending@{int(time.time()) - 900}"; s.commit()
bank.send({}, s, chief); s.refresh(st)
ok(st.zoho_status == "sent", "7. a stuck 'sending' bank line is picked up by Send")

# 5xx: Zoho may have saved it -> in doubt, not editable
orig = Z.call
def five(db_, method, path, params=None, body=None):
    if method == "POST":
        raise Z.ZohoError(504, "Gateway timeout")
    return orig(db_, method, path, params, body)
Z.call = five
g5 = bk(kind="charge", date="2026-10-10", amount=99, reference="g5")
bank._send(s, [g5], chief); s.refresh(g5)
ok(g5.zoho_err.startswith("No answer") and "did not answer" in refused(bank.edit, g5.id, {"kind": "charge", "date": "2026-10-10", "amount": 120, "reference": "g5"}, s, chief),
   "Zoho 504 on a bank send -> kept in doubt, amount cannot be changed")
l5 = models.StaffLoan(employee_id=1, amount=500, taken_on=date(2026, 10, 10), paid_from="ADCB", zoho_status="")
s.add(l5); s.commit()
zohosync.send_loans({"ids": [l5.id]}, s, chief); s.refresh(l5)
ok(l5.zoho_err.startswith("No answer"), "Zoho 504 on a loan send -> kept in doubt")
Z.call = orig
# BK-1 must not be taken for BK-10
EXIST.append({"_path": "banktransactions", "transaction_id": "TXW", "description": f"[BK-{g5.id}0] other line"})
bank.send({"ids": [g5.id]}, s, chief); s.refresh(g5)
ok(g5.zoho_id != "banktransaction:TXW", f"[BK-{g5.id}] is not matched to [BK-{g5.id}0]")

# Invoices
def inv(num, d, lines):
    x = A.Invoice(kind="tax", number=num, inv_date=d, client="Emkaan Design LLC", project_no="918", lines=json.dumps(lines),
                  subtotal=sum(l["amount"] for l in lines), vat=round(sum(l["amount"] * l["vat"] / 100 for l in lines), 2),
                  total=round(sum(l["amount"] * (1 + l["vat"] / 100) for l in lines), 2), status="", zoho_status="")
    s.add(x); s.commit(); return x
sep = inv("IC/26/918/IPA05", date(2026, 9, 20), [{"description": "IPA 5", "amount": 100000, "vat": 5}])
ok("Dated before" in refused(invzoho.release, sep.id, {"account": "Progressive Payments"}, s, chief), "6. a September invoice is not released")
TAXES[:] = [x for x in TAXES if x["tax_id"] != "V5"]; Z._CACHE.clear()
nv = inv("IC/26/918/IPA06", date(2026, 10, 12), [{"description": "IPA 6", "amount": 200000, "vat": 5}])
n4 = len(POSTED)
ok("Standard Rate" in refused(invzoho.release, nv.id, {"account": "Progressive Payments"}, s, chief) and len(POSTED) == n4,
   "8. no 5% tax in Zoho -> invoice refused, never posted without VAT")
TAXES.insert(0, {"tax_name": "Standard Rate", "tax_percentage": 5, "tax_id": "V5"}); Z._CACHE.clear()
s.refresh(nv)
invzoho.release(nv.id, {"account": "Progressive Payments"}, s, chief); s.refresh(nv)
ib = POSTED[-1][1]
ok(nv.zoho_status == "sent" and ib["line_items"][0]["rate"] == 200000 and ib["line_items"][0]["tax_id"] == "V5" and not nv.zoho_err,
   "invoice posted at net 200,000 with 5% VAT; Zoho total 210,000 matches")
d2 = inv("IC/26/918/IPA07", date(2026, 10, 13), [{"description": "IPA 7", "amount": 50000, "vat": 5}])
d2.zoho_err = "No answer from Zoho (ReadTimeout) - release again; Zoho is checked first"; s.commit()
ok(refused(A.edit_invoice, d2.id, {"number": "IC/26/918/IPA07X", "date": "2026-10-13", "client": "Emkaan Design LLC",
                                   "lines": [{"description": "IPA 7", "amount": 50000, "vat": 5}]}, s, chief),
   "invoice in doubt: renumbering refused (a new number would create a second invoice)")
print("fails=", fails)

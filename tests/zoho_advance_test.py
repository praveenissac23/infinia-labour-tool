"""Send to Zoho: supplier advances.
  Send Anyway  - no open bill in Zoho: a Payment Made with no bill applied, Zoho keeps it all as the supplier's advance.
  Send Excess  - more than the bill's balance: the balance is applied to the bill, the rest stays as an advance.
Lines with an open bill and amount <= balance send exactly as before. Zoho is never called - a stand-in answers.
    cd app && DATABASE_URL=sqlite:////tmp/zadv.db INFINIA_NO_SCHED=1 python3 ../tests/zoho_advance_test.py
"""
import os, sys, tempfile, json
if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
os.environ.setdefault("INFINIA_CRED_KEY_FILE", tempfile.mktemp(suffix=".key"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
from fastapi.testclient import TestClient
import main as M, models, zohoapi as Z, bank, zoholog
from database import SessionLocal
c = TestClient(M.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {x}"))
    if not ok: fails.append(n)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
d = M._dubai_today().isoformat()

# ---- the stand-in Zoho (below zohoapi.call, so the Sent to Zoho log is written as live) ----
CALLS, BILLS, N = [], {}, [2300]
def fake_call(db, method, path, params=None, body=None):
    CALLS.append((method, path, json.loads(json.dumps(body)) if body is not None else None))
    if path.startswith("bills/"):
        return {"bill": BILLS[path.split("/")[1]]}
    if method == "POST" and path == "vendorpayments":
        N[0] += 1
        return {"vendorpayment": {"payment_id": f"VP-{N[0]}", "payment_number": str(N[0]), "vendor_name": "EngiNova Technical Services"}}
    if method == "GET" and path.startswith("vendorpayments/"):
        return {"vendorpayment": {"payment_id": path.split("/")[1], "balance": 375.0}}
    if path == "contacts":
        return {"contacts": [{"contact_id": "V-ENG", "contact_name": "EngiNova Technical Services"}]}
    return {}
Z._call = fake_call
Z.account_id = lambda db, n: "ACC-" + n

def line(desc, amt, rcpt=""):
    r = c.post("/store/petty-cash", json={"date": d, "description": desc, "supplier": "EngiNova Technical Services L.L.C", "site": "", "received": 0,
                                         "paid": amt, "book": "office", "vat": False, "trn": "", "receipt_no": rcpt}, headers=H)
    s = SessionLocal(); x = s.query(models.PettyCash).filter(models.PettyCash.description == desc).first(); i = x.id; s.close()
    return i
def approve(i, **k):
    ln = dict({"id": i, "zoho_kind": "payment", "vat_claim": "none", "vendor_id": "V-ENG", "vendor": "EngiNova Technical Services"}, **k)
    return c.post("/store/zoho/approve", json={"lines": [ln]}, headers=H).json()
def send(i):
    CALLS.clear()
    s = SessionLocal(); x = s.get(models.PettyCash, i)
    sent, failed = Z.push_many(s, [x], s.get(models.User, 1))
    out = (sent, failed, x.zoho_id, x.zoho_ref)
    s.close()
    return out
def vp(): return [b for m, p, b in CALLS if m == "POST" and p == "vendorpayments"]

# ---- 1. Send Anyway: no open bill ----
a = line("Salary for Enginova Staff by Cash (Arun Natarajan)", 1175, "1486")
r = approve(a, advance="advance")
ck("Send Anyway: approved with no bill", r.get("approved") == 1, r)
s = SessionLocal(); x = s.get(models.PettyCash, a)
ck("...kept on the line as an advance", x.zoho_advance == "advance" and x.zoho_kind == "payment" and not x.zoho_bill_id, (x.zoho_advance, x.zoho_bill_id)); s.close()
sent, failed, zid, ref = send(a)
ck("sent", sent == 1 and not failed, failed)
want = {"vendor_id": "V-ENG", "payment_mode": "Cash", "amount": 1175.0, "date": d, "reference_number": f"PC-{a}",
        "paid_through_account_id": "ACC-Company Petty Cash",
        "description": f"Advance / payment on account – PC-{a} · Rcpt 1486 · Salary for Enginova Staff by Cash (Arun Natarajan) · EngiNova Technical Services L.L.C"}
ck("Zoho payload: a Payment Made, no bills applied, advance description", vp() == [want], vp())
ck("no expense made", not any(p == "expenses" for m, p, b in CALLS))
ck("line reads Payment Made 2301 · advance", zid == "vendorpayment:VP-2301" and ref == f"Payment Made 2301 · advance · PC-{a}", (zid, ref))

# ---- 2. Send Excess: 1,175.00 against a bill of 800.00 ----
BILLS["B-1"] = {"bill_id": "B-1", "bill_number": "ENG-26-041", "balance": 800.0, "status": "open"}
e = line("Manpower supply week 42", 1175)
r = approve(e, advance="excess", bill_id="B-1", bill_no="ENG-26-041")
ck("Send Excess: approved against the bill", r.get("approved") == 1, r)
sent, failed, zid, ref = send(e)
want = {"vendor_id": "V-ENG", "payment_mode": "Cash", "amount": 1175.0, "date": d, "reference_number": f"PC-{e}",
        "paid_through_account_id": "ACC-Company Petty Cash",
        "description": f"Bill ENG-26-041 800.00 + advance 375.00 on account – PC-{e} · Manpower supply week 42 · EngiNova Technical Services L.L.C",
        "bills": [{"bill_id": "B-1", "amount_applied": 800.0}]}
ck("Zoho payload: 800.00 applied to the bill, 1,175.00 paid (375.00 left unused)", vp() == [want], vp())
ck("line reads Payment Made 2302 · bill ENG-26-041 · advance 375.00", ref == f"Payment Made 2302 · bill ENG-26-041 · advance 375.00 · PC-{e}", ref)

# ---- 3. refused combinations ----
f1 = line("Advance with a bill picked", 100)
r = approve(f1, advance="advance", bill_id="B-1", bill_no="ENG-26-041")
ck("Send Anyway with a bill picked is refused", r.get("approved") == 0 and "no open bill" in r["refused"][0]["why"], r)
r = approve(f1, advance="excess")
ck("Send Excess without a bill is refused", r.get("approved") == 0 and "needs the bill" in r["refused"][0]["why"], r)
r = c.post("/store/zoho/approve", json={"lines": [{"id": f1, "zoho_kind": "expense", "account": "Office › Vehicle Repair and Maintenance Expenses",
                                                   "vat_claim": "none", "advance": "advance"}]}, headers=H).json()
s = SessionLocal(); ck("an expense never carries the advance mark", s.get(models.PettyCash, f1).zoho_advance == "", s.get(models.PettyCash, f1).zoho_advance); s.close()

# ---- 4. unchanged: open bill, amount <= balance ----
BILLS["B-2"] = {"bill_id": "B-2", "bill_number": "ENG-26-050", "balance": 1200.0, "status": "open"}
u = line("Bus A/C service D2075", 500)
r = approve(u, bill_id="B-2", bill_no="ENG-26-050")
sent, failed, zid, ref = send(u)
want = {"vendor_id": "V-ENG", "payment_mode": "Cash", "amount": 500.0, "date": d, "reference_number": f"PC-{u}",
        "paid_through_account_id": "ACC-Company Petty Cash", "description": "Bus A/C service D2075 · EngiNova Technical Services L.L.C",
        "bills": [{"bill_id": "B-2", "amount_applied": 500.0}]}
ck("unchanged: amount within the bill - same payload as before", vp() == [want], vp())
ck("unchanged: same label", ref == f"Payment Made 2303 · bill ENG-26-050 · PC-{u}", ref)
# picked "On account (no bill)" while he has bills (no Send Anyway) - as before: no bills, plain description
o = line("On account as before", 250)
approve(o)
send(o)
ck("unchanged: On account with no advance mark - plain description, no bills", vp() and "bills" not in vp()[0] and vp()[0]["description"] == "On account as before · EngiNova Technical Services L.L.C", vp())

# ---- 5. log, Sent to Zoho, advances list ----
S = c.get(f"/store/zoho/sent?start={d}&end={d}", headers=H).json()["rows"]
by = {r["ref"]: r for r in S}
ck("Sent to Zoho: Send Anyway shows advance 1,175.00", by[f"PC-{a}"]["advance"] == 1175.0 and by[f"PC-{a}"]["applied"] == 0, by.get(f"PC-{a}"))
ck("Sent to Zoho: Send Excess shows applied 800.00 · advance 375.00", by[f"PC-{e}"]["advance"] == 375.0 and by[f"PC-{e}"]["applied"] == 800.0, by.get(f"PC-{e}"))
ck("Sent to Zoho: a payment within the bill has no advance", by[f"PC-{u}"]["advance"] == 0, by.get(f"PC-{u}"))
A = c.get("/store/zoho/advances", headers=H).json()
ck("advances: one supplier, three payments (1,175 + 375 + 250 = 1,800.00)", len(A["suppliers"]) == 1 and A["count"] == 3 and A["total"] == 1800.0, A)
ck("advances: dated, with amount and Zoho number", all(r["date"] == d and r["number"] for r in A["suppliers"][0]["rows"]), A)
ck("advances: no Zoho read unless asked", A["suppliers"][0]["unused"] is None and not A["live"])
Z.connected = lambda db: True
A2 = c.get("/store/zoho/advances?live=1", headers=H).json()
ck("advances live: Zoho's unused amount read (GET only)", A2["suppliers"][0]["rows"][0]["unused"] == 375.0
   and all(m == "GET" for m, p, b in CALLS if p.startswith("vendorpayments/")), A2["suppliers"][0]["rows"][0])
logs = [l.action for l in SessionLocal().query(models.AuditLog).filter(models.AuditLog.action.like("zoho_advance%")).all()]
ck("activity log: confirmed and sent advances logged", logs.count("zoho_advance_ok") == 2 and logs.count("zoho_advance") == 2, logs)
for fmt in ("excel", "pdf"):
    tok = c.post("/auth/download-token", headers=H).json().get("token") if hasattr(c, "post") else ""
    rr = c.get(f"/export/zoho/advances?format={fmt}&token={tok}")
    ck(f"advances {fmt} export", rr.status_code == 200 and len(rr.content) > 500, rr.status_code)
ck("advances need the Send to Zoho right", c.get("/store/zoho/advances").status_code in (401, 403))

# ---- 6. bank: a supplier payment with less typed against bills than paid ----
s = SessionLocal()
bx = models.BankEntry(**bank._clean({"kind": "vendor", "date": d, "party": "EngiNova Technical Services", "party_id": "V-ENG", "amount": 1175,
                                     "reference": "PHUB1", "docs": [{"id": "B-9", "number": "ENG-9", "amount": 800}]}))
s.add(bx); s.commit(); CALLS.clear()
ck("bank row shows the advance", bank._row(bx, {})["advance"] == 375.0)
sent, failed = bank._send(s, [bx], s.get(models.User, 1))
ck("bank: payload as before (bills typed applied, nothing else changed)", vp() == [{"vendor_id": "V-ENG", "payment_mode": "Bank Transfer", "amount": 1175.0,
   "date": d, "reference_number": "PHUB1", "paid_through_account_id": "ACC-ADCB", "description": f"[BK-{bx.id}] EngiNova Technical Services",
   "bills": [{"bill_id": "B-9", "amount_applied": 800.0}]}], vp())
l = s.query(models.ZohoLog).filter(models.ZohoLog.source == "bank").first()
ck("bank: the log marks 375.00 as advance", json.loads(l.detail)["advance"] == 375.0, l.detail)
ck("bank: activity logged", s.query(models.AuditLog).filter(models.AuditLog.action == "zoho_advance", models.AuditLog.details.like("bank #%")).count() == 1)
s.close()
print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL PASS"); sys.exit(1 if fails else 0)

"""Bank > a line deleted in Zoho (21/11/2026, Al Raida 42,924.00, ref PHUB753519384): entered twice in the portal,
sent twice (Payment Made 2345, 2346), both deleted in Zoho and typed there again by hand (2348). The portal still said
"In Zoho" for both and would neither change nor remove them. Now:
  * Remove / Edit asks Zoho at once: gone -> cancelled (removable); gone but typed again by hand -> the line follows it;
  * the background check asks the newest bank lines first;
  * a second line with the same ADCB reference, amount and party is refused;
  * sending a line that Zoho already holds (typed by hand) links to it instead of adding a second payment.
Stand-in Zoho."""
import os, sys, tempfile
from datetime import date
db = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{db}"
os.environ["INFINIA_CRED_KEY_FILE"] = tempfile.mktemp(suffix=".key")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as M, models, zohoapi as Z, bank, credentials, auth
from database import SessionLocal, engine
from fastapi import HTTPException
from fastapi.testclient import TestClient
models.Base.metadata.create_all(bind=engine); M._add_missing_columns()
s = SessionLocal()
FAIL = []
def ok(c, m, x=""):
    print(("PASS " if c else "FAIL ") + m + ("" if c else f"  [{x}]"))
    if not c: FAIL.append(m)

ZOHO = {}          # payment_id -> payment
NEXT = [2345]
CALLS = []
def fake(db_, method, path, params=None, body=None):
    CALLS.append((method, path))
    if path == "chartofaccounts":
        return {"chartofaccounts": [{"account_name": "ADCB", "account_id": "B"}], "page_context": {}}
    if path in ("projects", "settings/taxes"):
        return {"projects": [], "taxes": []}
    if path == "contacts":
        return {"contacts": [{"contact_id": "V-RAIDA", "contact_name": "Al Raida Electromechanical Services LLC"}]}
    if path == "vendorpayments" and method == "POST":
        pid = f"P{NEXT[0]}"
        ZOHO[pid] = {"payment_id": pid, "payment_number": str(NEXT[0]), "reference_number": body.get("reference_number"),
                     "amount": body.get("amount"), "vendor_id": body.get("vendor_id"), "description": body.get("description", "")}
        NEXT[0] += 1
        return {"vendorpayment": ZOHO[pid]}
    if path == "vendorpayments" and method == "GET":
        ref = (params or {}).get("reference_number")
        txt = (params or {}).get("description_contains")
        return {"vendorpayments": [p for p in ZOHO.values() if (ref and p["reference_number"] == ref) or (txt and txt in p["description"])]}
    if path.startswith("vendorpayments/") and method == "GET":
        pid = path.split("/")[1]
        if pid not in ZOHO:
            raise Z.ZohoError(404, "Payments Made does not exist.")
        return {"vendorpayment": ZOHO[pid]}
    if method == "GET":
        return {}
    raise AssertionError(f"unexpected {method} {path}")
Z.call = fake
M.put_setting(s, "zoho_refresh", credentials.lock("rt")); s.commit()
s.add(models.User(username="shafeeq", hashed_password=auth.hash_password("p"), full_name="Shafeeq", role="admin")); s.commit()
c = TestClient(M.app)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "shafeeq", "password": "p"}).json()["access_token"]}
LINE = {"kind": "vendor", "date": "2026-11-20", "party": "Al Raida Electromechanical Services LLC", "party_id": "V-RAIDA", "amount": 42924,
        "reference": "PHUB753519384", "notes": "906ACWORKSPC10 · O/W TRF753519384"}

# the two copies as they are on live (entered before this fix) - put straight in, then sent
a = models.BankEntry(**bank._clean(LINE)); b = models.BankEntry(**bank._clean(LINE)); s.add_all([a, b]); s.commit()
bank._send(s, [a], models.User(id=1)); bank._send(s, [b], models.User(id=1))
s.refresh(a); s.refresh(b)
ok(a.zoho_ref == "Payment Made 2345" and b.zoho_ref.startswith("Payment Made 2345 (typed in Zoho)") is False, "set-up: the first went in as 2345", (a.zoho_ref, b.zoho_ref))

# --- a new line with the same reference, amount and party is refused
r = c.post("/store/bank", headers=H, json=LINE)
ok(r.status_code == 400 and "Already entered" in r.json()["detail"] and "PHUB753519384" in r.json()["detail"], "the same ADCB line entered again: refused", r.text[:200])
r = c.post("/store/bank", headers=H, json=dict(LINE, amount=1000))
ok(r.status_code == 200, "same reference, another amount (part of a split): allowed", r.text[:200])

# --- while in Zoho: Remove refused, saying where it is
r = c.delete(f"/store/bank/{a.id}", headers=H)
ok(r.status_code == 400 and "Payment Made 2345" in r.json()["detail"], "still in Zoho: Remove refused, names the Zoho entry", r.text[:200])

# --- accounts deletes both in Zoho and types the payment there by hand
for pid in list(ZOHO):
    if ZOHO[pid]["reference_number"] == "PHUB753519384" and ZOHO[pid]["amount"] == 42924:
        del ZOHO[pid]
ZOHO["P2348"] = {"payment_id": "P2348", "payment_number": "2348", "reference_number": "PHUB753519384", "amount": 42924.0, "vendor_id": "V-RAIDA", "description": ""}

r = c.delete(f"/store/bank/{a.id}", headers=H)
s.expire_all(); a = s.get(models.BankEntry, a.id)
ok(r.status_code == 400 and "2348" in r.json()["detail"] and a.zoho_id == "vendorpayment:P2348" and a.zoho_status == "sent" and "typed in Zoho" in a.zoho_ref,
   "first copy: Zoho asked at once - deleted there, typed again by hand -> the line now follows Payment Made 2348", (r.text[:200], a.zoho_id, a.zoho_ref))
bid = b.id
r = c.delete(f"/store/bank/{bid}", headers=H)
s.close(); s = SessionLocal()
ok(r.status_code == 200 and s.query(models.BankEntry).filter(models.BankEntry.id == bid).count() == 0, "second copy: deleted in Zoho, 2348 already followed by the first -> removed", r.text[:200])
ok(len([p for p in ZOHO.values() if p["reference_number"] == "PHUB753519384" and p["amount"] == 42924]) == 1, "Zoho holds the 42,924.00 payment once")

# --- edit of a line deleted in Zoho: allowed (it is cancelled first); no Zoho: refused as before
x = models.BankEntry(**bank._clean(dict(LINE, reference="PHUB000000001", amount=500))); s.add(x); s.commit()
bank._send(s, [x], models.User(id=1)); s.refresh(x)
r = c.put(f"/store/bank/{x.id}", headers=H, json=dict(LINE, reference="PHUB000000001", amount=600))
ok(r.status_code == 400 and "in Zoho already" in r.json()["detail"], "in Zoho: changing the amount refused as before", r.text[:200])
ZOHO.pop(x.zoho_id.split(":")[1])
r = c.put(f"/store/bank/{x.id}", headers=H, json=dict(LINE, reference="PHUB000000001", amount=600))
s.expire_all(); x = s.get(models.BankEntry, x.id)
ok(r.status_code == 200 and x.amount == 600 and x.zoho_status == "sent" and x.zoho_id != "", "deleted in Zoho: the change is taken and sent again", (r.text[:200], x.amount, x.zoho_status))

# --- sending a line that Zoho already holds by hand: linked, not posted twice
ZOHO["P9001"] = {"payment_id": "P9001", "payment_number": "9001", "reference_number": "PHUB111", "amount": 700.0, "vendor_id": "V-RAIDA", "description": ""}
n_before = len(ZOHO)
r = c.post("/store/bank", headers=H, json=dict(LINE, reference="PHUB111", amount=700))
s.expire_all(); y = s.get(models.BankEntry, r.json()["id"])
ok(y.zoho_id == "vendorpayment:P9001" and len(ZOHO) == n_before and "typed in Zoho" in y.zoho_ref, "already typed in Zoho by hand: the new line links to it, no second payment", (y.zoho_id, y.zoho_ref, len(ZOHO)))
ZOHO["P9002"] = {"payment_id": "P9002", "payment_number": "9002", "reference_number": "PHUB222", "amount": 999.0, "vendor_id": "V-RAIDA", "description": ""}
r = c.post("/store/bank", headers=H, json=dict(LINE, reference="PHUB222", amount=700))
s.expire_all(); y = s.get(models.BankEntry, r.json()["id"])
ok(y.zoho_id != "vendorpayment:P9002", "same reference but another amount in Zoho: not taken for it", y.zoho_id)

# --- background check: newest bank lines first, and before the petty cash
for i in range(5):
    s.add(models.PettyCash(book="site", on_date=date(2026, 11, 1), description=f"p{i}", paid=1, zoho_status="sent", zoho_id=f"vendorpayment:GONE{i}"))
s.commit()
CALLS.clear()
Z._check_deleted_now(s)
gets = [p for m, p in CALLS if m == "GET" and p.startswith("vendorpayments/")]
bank_ids = [int(e.zoho_id.split(":")[1][1:]) if e.zoho_id.split(":")[1][1:].isdigit() else 0 for e in s.query(models.BankEntry).filter(models.BankEntry.zoho_status == "sent").order_by(models.BankEntry.id.desc())]
ok(gets and not gets[0].startswith("vendorpayments/GONE"), "background check asks the bank lines before the petty cash", gets[:4])
ok(all(p.zoho_status == "cancelled" for p in s.query(models.PettyCash).all()), "petty cash lines deleted in Zoho still found and cancelled")
print("\n" + ("ALL PASS" if not FAIL else f"{len(FAIL)} FAILED"))
sys.exit(1 if FAIL else 0)

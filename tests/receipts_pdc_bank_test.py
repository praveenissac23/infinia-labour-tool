"""Post-dated cheques count as received on their cheque date; a client's payment on Bank makes its receipt
(linked, editable, kept in step).
    cd app && rm -f /tmp/rpb.db && DATABASE_URL=sqlite:////tmp/rpb.db INFINIA_NO_SCHED=1 python3 ../tests/receipts_pdc_bank_test.py
"""
import os, sys, json
from datetime import timedelta
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main as M, models, receipts as RC
from database import SessionLocal
c = TestClient(M.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {x}"))
    if not ok: fails.append(n)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
today = M._dubai_today(); later = (today + timedelta(days=30)).isoformat(); past = (today - timedelta(days=3)).isoformat()
mk = lambda no, amt: c.post("/employees/accounts/invoices", json={"kind": "tax", "number": no, "date": past, "client": "Pdc Client LLC", "project_no": "977",
                                                                   "lines": [{"description": "x", "amount": amt, "vat": 5}]}, headers=H).json()["id"]
inv = lambda: {x["id"]: x for x in c.get("/employees/accounts/invoices?kind=tax", headers=H).json()["rows"]}
rcs = lambda: c.get("/employees/accounts/receipts", headers=H).json()
a, b, d = mk("PT/977/1", 10000), mk("PT/977/2", 20000), mk("PT/977/3", 4000)     # 10,500 / 21,000 / 4,200

# ---- 1. post-dated cheque -------------------------------------------------------------------------------
base = {"date": today.isoformat(), "client": "Pdc Client LLC", "project_no": "977", "bank": "ENBD"}
r = c.post("/employees/accounts/receipts", json=dict(base, number="RC/T/1", mode="PDC", reference="000777", cheque_date=later, amount="10500",
                                                     allocations=[{"invoice_id": a, "amount": "10500"}]), headers=H)
ck("PDC receipt saved", r.status_code == 200, r.text)
pid = r.json()["id"]
i = inv()[a]
ck("PDC not counted as received before its date", i["received"] == 0 and i["balance"] == 10500, i)
ck("...shown as on a post-dated cheque", i["pdc"] == 10500, i)
ck("...and no PAID stamp yet", not i["paid_stamp"], i)
x = c.post("/employees/accounts/receipts", json=dict(base, number="RC/T/2", mode="Bank transfer", amount="100", allocations=[{"invoice_id": a, "amount": "100"}]), headers=H)
ck("the same money cannot be set against the invoice twice", x.status_code == 400, x.text)
L = rcs()
me = next(r for r in L["rows"] if r["id"] == pid)
ck("receipts list marks it not due yet", me["due"] is False and L["totals"]["pdc"] == 10500, (me["due"], L["totals"]))
oi = next(r for r in L["invoices"] if r["id"] == a)
ck("the receipt form sees nothing left to receive on it", oi["open"] == 0 and oi["pdc"] == 10500, oi)
# the date comes
s = SessionLocal(); rr = s.get(RC.Receipt, pid); rr.cheque_date = today - timedelta(days=1); s.commit(); s.close()
i = inv()[a]
ck("once its date has come it counts as received", i["received"] == 10500 and i["balance"] == 0 and i["pdc"] == 0, i)
ck("...and the PAID stamp goes on, dated the cheque date", i["paid_stamp"] and i["paid_on"] == (today - timedelta(days=1)).isoformat(), (i["paid_stamp"], i["paid_on"]))
c.post(f"/employees/accounts/receipts/{pid}/cancel", json={}, headers=H)
i = inv()[a]
ck("cancelled: money and stamp off", i["received"] == 0 and not i["paid_stamp"], i)
# a cheque dated today or earlier counts at once
r = c.post("/employees/accounts/receipts", json=dict(base, number="RC/T/3", mode="Cheque", reference="000778", cheque_date=past, amount="4200",
                                                     allocations=[{"invoice_id": d, "amount": "4200"}]), headers=H)
i = inv()[d]
ck("a cheque already dated counts at once and is stamped", i["received"] == 4200 and i["paid_stamp"] and i["paid_on"] == past, i)

# ---- 2. a client's payment on Bank makes its receipt ------------------------------------------------------
bk = c.post("/store/bank", json={"kind": "customer", "date": today.isoformat(), "party": "Pdc Client LLC", "mode": "Bank Transfer", "reference": "PHUB123",
                                 "amount": "21000", "docs": [{"id": "Z1", "number": "PT/977/2", "amount": 21000}]}, headers=H)
ck("bank line saved", bk.status_code == 200, bk.text)
bid = bk.json()["id"]
L = rcs()
mine = [r for r in L["rows"] if r["bank_id"] == bid]
ck("one receipt made from it", len(mine) == 1, mine)
m = mine[0]
ck("...for the client, amount, date, mode and reference", m["client"] == "Pdc Client LLC" and m["amount"] == 21000 and m["date"] == today.isoformat()
   and m["mode"] == "Bank transfer" and m["reference"] == "PHUB123", m)
ck("...set against the invoice the bank line names", [(al["invoice_id"], al["amount"]) for al in m["allocations"]] == [(b, 21000)], m["allocations"])
ck("...numbered in the project's series", m["number"].startswith("RC/") and "/977/" in m["number"], m["number"])
ck("...and shows its bank line", m["bank_line"] and m["bank_line"]["id"] == bid, m["bank_line"])
ck("invoice paid and stamped", inv()[b]["balance"] == 0 and inv()[b]["paid_stamp"])
row = next(r for r in c.get(f"/store/bank?month={today:%Y-%m}", headers=H).json()["rows"] if r["id"] == bid)
ck("the bank line shows its receipt number", row["receipt"] and row["receipt"]["number"] == m["number"], row.get("receipt"))
# editable
e = dict(base, number=m["number"], date=m["date"], mode="Bank transfer", reference="PHUB123", amount="21000", notes="checked by Shafeeq",
         allocations=[{"invoice_id": b, "amount": "21000"}])
ck("the receipt can be edited", c.put(f"/employees/accounts/receipts/{m['id']}", json=e, headers=H).status_code == 200)
# bank line amount down: receipt follows, invoice part paid
c.put(f"/store/bank/{bid}", json={"kind": "customer", "date": today.isoformat(), "party": "Pdc Client LLC", "mode": "Bank Transfer", "reference": "PHUB123",
                                  "amount": "15000", "docs": [{"id": "Z1", "number": "PT/977/2", "amount": 15000}]}, headers=H)
m2 = next(r for r in rcs()["rows"] if r["id"] == m["id"])
ck("bank amount changed: the receipt follows", m2["amount"] == 15000 and m2["allocations"][0]["amount"] == 15000, m2)
ck("...the office's note stays", m2["notes"] == "checked by Shafeeq", m2["notes"])
ck("...the invoice is part paid again and its stamp off", inv()[b]["balance"] == 6000 and not inv()[b]["paid_stamp"], inv()[b])
ck("still one receipt for the line", len([r for r in rcs()["rows"] if r["bank_id"] == bid]) == 1)
# removed: receipt cancelled
c.delete(f"/store/bank/{bid}", headers=H)
m3 = next(r for r in rcs()["rows"] if r["id"] == m["id"])
ck("bank line removed: its receipt is cancelled (and let go of the line)", m3["status"] == "cancelled" and m3["bank_id"] is None, (m3["status"], m3["bank_id"]))
ck("...and the money comes off the invoice", inv()[b]["received"] == 0)

# ---- 3. a post-dated cheque on Bank ----------------------------------------------------------------------
bk = c.post("/store/bank", json={"kind": "customer", "date": later, "party": "Pdc Client LLC", "mode": "Cheque", "reference": "000555",
                                 "amount": "21000", "docs": [{"id": "Z1", "number": "PT/977/2", "amount": 21000}]}, headers=H).json()
m = next(r for r in rcs()["rows"] if r["bank_id"] == bk["id"])
ck("PDC on Bank: receipt is a PDC dated today with the cheque date", m["mode"] == "PDC" and m["date"] == today.isoformat() and m["cheque_date"] == later, m)
ck("...not counted until the cheque date", inv()[b]["received"] == 0 and inv()[b]["pdc"] == 21000, inv()[b])

# ---- 4. a receipt typed by hand first is linked, not doubled ------------------------------------------------
h = c.post("/employees/accounts/receipts", json=dict(base, number="RC/T/9", client="Hand Client", mode="Bank transfer", reference="TT-88", amount="5000", allocations=[]), headers=H).json()
bk = c.post("/store/bank", json={"kind": "customer", "date": today.isoformat(), "party": "Hand Client", "mode": "Bank Transfer", "reference": "TT88", "amount": "5000", "docs": []}, headers=H).json()
mine = [r for r in rcs()["rows"] if r["bank_id"] == bk["id"]]
ck("a receipt already typed for the same money is linked, no second one", len(mine) == 1 and mine[0]["id"] == h["id"], mine)
# kind changed away from client: the receipt goes
c.put(f"/store/bank/{bk['id']}", json={"kind": "charge", "date": today.isoformat(), "mode": "Bank Transfer", "amount": "5000"}, headers=H)
ck("bank line no longer a client's payment: its receipt is cancelled", next(r for r in rcs()["rows"] if r["id"] == h["id"])["status"] == "cancelled")

# ---- 5. the once-only fill for lines already on Bank ---------------------------------------------------------
s = SessionLocal()
old = models.BankEntry(kind="customer", on_date=today, party="Old Client", mode="Bank Transfer", reference="OLD1", amount=7000, docs="[]")
s.add(old); s.commit()
RC.backfill(s); RC.backfill(s)
ck("lines already on Bank get one receipt each (run twice, still one)", s.query(RC.Receipt).filter(RC.Receipt.bank_id == old.id).count() == 1)
s.close()
print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL PASS"); sys.exit(1 if fails else 0)

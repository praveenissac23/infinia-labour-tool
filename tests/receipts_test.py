"""Receipts against tax invoices and the PAID stamp (API).
    cd app && DATABASE_URL=sqlite:////tmp/rcpt.db INFINIA_NO_SCHED=1 python3 ../tests/receipts_test.py
"""
import os, sys
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main
c = TestClient(main.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {x}"))
    if not ok: fails.append(n)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
mk = lambda no, amt: c.post("/employees/accounts/invoices", json={"kind": "tax", "number": no, "date": "2026-10-01", "client": "Test Client LLC", "project_no": "999",
                                                                   "lines": [{"description": "x", "amount": amt, "vat": 5}]}, headers=H).json()["id"]
import time; run = str(int(time.time()) % 100000)
a, b = mk("T/" + run + "/1", 10000), mk("T/" + run + "/2", 20000)       # 10,500 and 21,000 with VAT
# PAID stamp by hand
ck("PAID stamp on", c.post(f"/employees/accounts/invoices/{a}/paid", json={"paid": True, "paid_on": "2026-10-05"}, headers=H).json()["paid_stamp"])
t = c.post("/auth/download-token", headers=H).json()["token"]
ck("invoice PDF with the stamp", c.get(f"/export/accounts/invoice/{a}?token={t}").content[:4] == b"%PDF")
c.post(f"/employees/accounts/invoices/{a}/paid", json={"paid": False}, headers=H)
nxt = c.get("/employees/accounts/receipts/next?project_no=999", headers=H).json()["number"]
ck("receipt numbered per project", nxt.startswith("RC/") and "/999/" in nxt, nxt)
base = {"number": nxt, "date": "2026-10-21", "client": "Test Client LLC", "project_no": "999", "mode": "Cheque", "reference": "123", "bank": "ENBD", "cheque_date": "2026-10-21"}
r = c.post("/employees/accounts/receipts", json=dict(base, amount="40000", allocations=[{"invoice_id": a, "amount": "10500"}, {"invoice_id": b, "amount": "21000"}]), headers=H)
ck("receipt saved with an advance over the invoices", r.status_code == 200, r.text)
rid = r.json()["id"]
rows = c.get("/employees/accounts/receipts", headers=H).json()["rows"]
me = next(x for x in rows if x["id"] == rid)
ck("applied 31,500, advance 8,500", me["applied"] == 31500 and me["advance"] == 8500, me)
inv = {x["id"]: x for x in c.get("/employees/accounts/invoices?kind=tax", headers=H).json()["rows"]}
ck("both invoices received in full and stamped PAID on the receipt date", inv[a]["balance"] == 0 and inv[b]["balance"] == 0 and inv[a]["paid_stamp"] and inv[a]["paid_on"] == "2026-10-21")
r2 = c.post("/employees/accounts/receipts", json=dict(base, number=nxt + "X", amount="100", allocations=[{"invoice_id": a, "amount": "100"}]), headers=H)
ck("cannot receive more than the balance due", r2.status_code == 400 and "still due" in r2.text, r2.text)
r3 = c.post("/employees/accounts/receipts", json=dict(base, number=nxt, amount="5", allocations=[]), headers=H)
ck("number used twice is refused", r3.status_code == 400)
ck("receipt PDF", c.get(f"/export/accounts/receipt/{rid}?token={t}").content[:4] == b"%PDF")
ck("receipt view page", c.get(f"/export/accounts/receipt/{rid}/view?token={t}").status_code == 200)
c.put(f"/employees/accounts/receipts/{rid}", json=dict(base, amount="20000", allocations=[{"invoice_id": a, "amount": "10500"}, {"invoice_id": b, "amount": "9500"}]), headers=H)
inv = {x["id"]: x for x in c.get("/employees/accounts/invoices?kind=tax", headers=H).json()["rows"]}
ck("edit down: second invoice part paid again, its stamp off", inv[b]["balance"] == 11500 and not inv[b]["paid_stamp"] and inv[a]["paid_stamp"], (inv[b]["balance"], inv[b]["paid_stamp"]))
c.post(f"/employees/accounts/receipts/{rid}/cancel", json={}, headers=H)
inv = {x["id"]: x for x in c.get("/employees/accounts/invoices?kind=tax", headers=H).json()["rows"]}
ck("cancel: money and stamp off", inv[a]["balance"] == 10500 and not inv[a]["paid_stamp"])
print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL PASS"); sys.exit(1 if fails else 0)

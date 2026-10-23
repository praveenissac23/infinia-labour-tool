"""Petty cash VAT: the chief accountant takes VAT off a bill entered with it, or gives VAT to one entered without,
on Send to Zoho; the line itself is changed.
    cd app && rm -f /tmp/pvc.db && DATABASE_URL=sqlite:////tmp/pvc.db INFINIA_NO_SCHED=1 python3 ../tests/petty_vat_chief_test.py
"""
import os, sys
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main as M, models
from database import SessionLocal
c = TestClient(M.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {x}"))
    if not ok: fails.append(n)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
d = M._dubai_today().isoformat()
add = lambda desc, amt, vat, trn="": c.post("/store/petty-cash", json={"date": d, "description": desc, "supplier": "Shop", "site": "", "received": 0, "paid": amt,
                                                                      "book": "office", "vat": vat, "trn": trn}, headers=H)
r1 = add("Taxi - VAT ticked by mistake", 105, True); r2 = add("Hardware - VAT not ticked", 210, False)
ck("two bills saved", r1.status_code == 200 and r2.status_code == 200, (r1.text, r2.text))
s = SessionLocal()
a = s.query(models.PettyCash).filter(models.PettyCash.description.like("Taxi%")).first(); b = s.query(models.PettyCash).filter(models.PettyCash.description.like("Hardware%")).first()
s.close()
q = c.get("/store/zoho/queue", headers=H).json()
rows = {r["id"]: r for r in q.get("rows", [])}
ck("both on Send to Zoho", a.id in rows and b.id in rows, list(rows)[:5])
acc = next((r["account"] for r in q["rows"] if r.get("account")), "") or "Office › Transportation"
heads = c.get("/store/zoho/heads", headers=H).json()
x = c.post("/store/zoho/approve", json={"lines": [{"id": a.id, "account": rows[a.id]["account"] or acc, "vat_claim": "none"},
                                                  {"id": b.id, "account": rows[b.id]["account"] or acc, "vat_claim": "claim", "trn": "100234567800003"}]}, headers=H)
ck("approve call answered", x.status_code == 200, x.text)
s = SessionLocal(); a2 = s.get(models.PettyCash, a.id); b2 = s.get(models.PettyCash, b.id)
ck("VAT taken off: the line now has no VAT (whole amount the cost)", a2.vat is False and (a2.vat_claim or "") == "", (a2.vat, a2.vat_claim))
ck("VAT added: the line now has VAT, claimed, with the TRN", b2.vat is True and b2.vat_claim == "claim" and b2.trn == "100234567800003", (b2.vat, b2.vat_claim, b2.trn))
s.close()
print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL PASS"); sys.exit(1 if fails else 0)

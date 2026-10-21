"""Reports > Store > On rent / rentals / assets read the rental ledger: equipment delivered hired from a
trader (owner on the movement) shows on rent and is not counted as company assets.
    cd app && DATABASE_URL=sqlite:////tmp/hired.db INFINIA_NO_SCHED=1 python3 ../tests/hired_reports_test.py
"""
import os, sys
sys.path.insert(0, os.getcwd())
from datetime import date
from fastapi.testclient import TestClient
import main, models
from database import SessionLocal
c = TestClient(main.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {x}"))
    if not ok: fails.append(n)
db = SessionLocal()
sup = models.Supplier(name="Hire Test Scaffolding LLC", name_key=main._supplier_key("Hire Test Scaffolding LLC")); db.add(sup)
it = models.StoreItem(code="HT-STD", name="Hire test standard", unit="nos", item_type="asset", active=True); db.add(it)
rt = models.StoreItem(code="HT-RNT", name="Hire test rental", unit="nos", item_type="rental", rental_supplier="Hire Test Scaffolding LLC", active=True); db.add(rt)
db.commit()
db.add(models.StoreMovement(item_id=it.id, kind="in", qty=230, location="914", owner_id=sup.id, moved_on=date(2026, 6, 16)))
db.add(models.StoreMovement(item_id=it.id, kind="in", qty=20, location="", moved_on=date(2026, 9, 28)))
db.add(models.StoreMovement(item_id=rt.id, kind="in", qty=5, location="", moved_on=date(2026, 9, 1)))
db.commit()
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
h = {r["code"]: r for r in c.get("/store/report?kind=hired", headers=H).json()["rows"]}
ck("material delivered hired from a trader is on rent, at its site", "HT-STD" in h and h["HT-STD"]["on_hire"] == 230 and h["HT-STD"]["by_site"] == {"914": 230} and h["HT-STD"]["hired_from"] == "Hire Test Scaffolding LLC", h.get("HT-STD"))
ck("a material typed Rental is on rent too", "HT-RNT" in h and h["HT-RNT"]["on_hire"] == 5 and h["HT-RNT"]["in_store"] == 5, h.get("HT-RNT"))
ck("since = the day it came", h["HT-STD"]["since"] == "2026-06-16")
r = {x["code"]: x for x in c.get("/store/report?kind=rentals", headers=H).json()["rows"]}
ck("rented equipment list agrees", r["HT-STD"]["qty"] == 230 and r["HT-STD"]["supplier"] == "Hire Test Scaffolding LLC")
a = {x["code"]: x for x in c.get("/store/report?kind=assets", headers=H).json()["rows"]}
ck("owned assets count only our own 20, not the 230 hired", a["HT-STD"]["total"] == 20, a.get("HT-STD"))
print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL PASS"); sys.exit(1 if fails else 0)

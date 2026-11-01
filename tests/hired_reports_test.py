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
# One rule (01/11/2026): the 230 delivered as the trader's go onto the material's Rental twin, never onto our own
tw = db.query(models.StoreItem).filter(models.StoreItem.name == "Rental Hire test standard").first()
ck("the trader's 230 are booked on the Rental twin 'Rental Hire test standard' (type Rental)",
   tw is not None and tw.item_type == "rental" and tw.rental_supplier == "Hire Test Scaffolding LLC", tw and (tw.item_type, tw.rental_supplier))
TW = tw.code if tw else "?"
h = {r["code"]: r for r in c.get("/store/report?kind=hired", headers=H).json()["rows"]}
ck("material delivered from a rental supplier is on rental, at its site", TW in h and h[TW]["on_hire"] == 230 and h[TW]["by_site"] == {"914": 230} and h[TW]["hired_from"] == "Hire Test Scaffolding LLC", h.get(TW))
ck("our own 20 are not on rental", "HT-STD" not in h, h.get("HT-STD"))
ck("a material typed Rental is on rent too", "HT-RNT" in h and h["HT-RNT"]["on_hire"] == 5 and h["HT-RNT"]["in_store"] == 5, h.get("HT-RNT"))
ck("since = the day it came", h[TW]["since"] == "2026-06-16")
r = {x["code"]: x for x in c.get("/store/report?kind=rentals", headers=H).json()["rows"]}
ck("rented equipment list agrees", r[TW]["qty"] == 230 and r[TW]["supplier"] == "Hire Test Scaffolding LLC")
st = c.get("/store/report?kind=stock", headers=H).json()
rows = {(x["code"], x["item_type"]): x for x in st["rows"]}
ck("Current stock: our 20 as Asset, the 230 as Rental - Hire Test Scaffolding LLC",
   rows.get(("HT-STD", "asset"), {}).get("total") == 20 and rows.get((TW, "rental"), {}).get("total") == 230
   and rows[(TW, "rental")]["_type_label"] == "Rental \u2013 Hire Test Scaffolding LLC", rows)
ck("totals per type kept apart: the 230 are never in the Asset total",
   st["type_totals"]["asset"]["total"] == 20 and st["type_totals"]["rental"]["total"] == 235, st["type_totals"])
a = {x["code"]: x for x in c.get("/store/report?kind=assets", headers=H).json()["rows"]}
ck("owned assets count only our own 20, not the 230 hired", a["HT-STD"]["total"] == 20, a.get("HT-STD"))
print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL PASS"); sys.exit(1 if fails else 0)

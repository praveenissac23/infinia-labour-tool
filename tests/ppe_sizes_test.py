"""PPE stock by size: safety shoes and uniforms counted and received size by
size; an issue in a size takes it off that size; the item totals agree."""
import os, sys, tempfile, json
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
os.environ["INFINIA_CRED_KEY_FILE"] = tempfile.mktemp(suffix=".key")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as M, models, ppe
from database import SessionLocal, engine
from fastapi import HTTPException
models.Base.metadata.create_all(bind=engine); M._add_missing_columns()
s = SessionLocal(); fails = 0
def ok(c, m, i=""):
    global fails
    print(("PASS " if c else "FAIL ") + m + ("" if c else f"  {i}")); fails += 0 if c else 1
M.put_setting(s, "ppe_seeded", "1"); M.put_setting(s, "ppe_moves_migrated", "1")
u = models.User(username="jomon", full_name="Jomon", hashed_password="x", role="admin")
w = models.Employee(emp_no="F-901", name="TEST MAN", trade="Helper", active=True, staff=False)
s.add_all([u, w]); s.commit()
ppe.set_stock({"item": "Safety Shoes", "location": "Store", "sizes": {"40": "5", "42": "10", "44": ""}}, s, u)
ppe.received({"item": "Safety Shoes", "location": "Store", "sizes": {"42": 4, "44": 6}, "note": "LPO 1"}, s, u)
ppe.received({"item": "Safety Shoes", "location": "Office", "sizes": {"43": 3}}, s, u)
def give(item, size, qty=1, src="Store"):
    ppe.add({"employee_id": w.id, "item": item, "size": size, "qty": qty, "date": M._dubai_today().isoformat(), "condition": "Issued", "source": src}, s, u)
give("Safety Shoes", "42", 2); give("Safety Shoes", " 44 "); give("Safety Shoes", "")
d = ppe.dashboard(s)
sh = next(x for x in d["by_size"] if x["item"] == "Safety Shoes")
c = sh["cells"]
ok(c["40"]["Store"] == 5 and c["42"]["Store"] == 12 and c["44"]["Store"] == 5, "Store by size: 40 = 5, 42 = 10 + 4 - 2 = 12, 44 = 6 - 1 = 5", c)
ok(c["43"]["Office"] == 3 and c["43"]["Store"] is None and c["43"]["total"] == 3, "Office 43 = 3; not counted at the Store", c["43"])
ok(c["38"]["total"] is None, "a size never counted shows nothing (—)")
ok(sh["no_size"] == 1, "the issue with no size written is shown as 'no size'", sh["no_size"])
it = next(x for x in d["stock"] if x["item"] == "Safety Shoes")
ok(it["Store"]["in_hand"] == 15 + 10 - 4 and it["Office"]["in_hand"] == 3, "item totals still right: Store 21, Office 3", (it["Store"], it["Office"]))
ok(sum(v["Store"] or 0 for v in c.values()) == it["Store"]["in_hand"] + sh["no_size"], "sizes add up to the item total plus the one with no size")
try:
    ppe.set_stock({"item": "Safety Shoes", "location": "Store", "sizes": {"52": 1}}, s, u); ok(False, "a size not in the list is refused")
except HTTPException:
    s.rollback(); ok(True, "a size not in the list is refused")
ppe.received({"item": "Coverall", "location": "Store", "sizes": {"xl": 8, "L": 4}}, s, u)
give("Coverall", "XL", 3)
cv = next(x for x in ppe.dashboard(s)["by_size"] if x["item"] == "Coverall")["cells"]
ok(cv["XL"]["Store"] == 5 and cv["L"]["Store"] == 4, "coverall: XL 8 - 3 = 5, L 4 (sizes typed in small letters taken)", cv)
h = ppe.stock_history("Safety Shoes", s, u)
rec = next(m for m in h["moves"] if m["kind"] == "received" and m["place"] == "Store")
ok(rec["qty"] == 10 and rec["sizes"] == {"42": 4, "44": 6}, "history shows one line with its sizes", rec)
ok(len(h["moves"]) == 3, "only the whole entries are listed (3), not each size", len(h["moves"]))
ppe.delete_move(rec["id"], s, u)
c2 = next(x for x in ppe.dashboard(s)["by_size"] if x["item"] == "Safety Shoes")["cells"]
ok(c2["42"]["Store"] == 8 and c2["44"]["Store"] == -1, "removing the delivery takes its sizes away too (42: 10 - 2, 44: 0 - 1)", c2)
print("ALL PASS" if not fails else f"{fails} FAILED"); sys.exit(1 if fails else 0)

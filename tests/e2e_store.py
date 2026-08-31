import sys
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main

db = database.SessionLocal()
db.add(models.User(username="admin", hashed_password=auth.hash_password("test123"),
                   full_name="Admin", role="admin"))
db.commit(); db.close()

c = TestClient(main.app)
FAIL = []
def check(label, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + label + (f"  [{extra}]" if extra and not cond else ""))
    if not cond: FAIL.append(label)

r = c.post("/auth/login", data={"username": "admin", "password": "test123"})
check("login", r.status_code == 200, r.text[:150])
H = {"Authorization": f"Bearer {r.json().get('access_token','')}"}

r = c.post("/store/items", json={"name": "cement opc 42.5", "unit": "bag", "item_type": "consumable"}, headers=H)
check("create item blank code", r.status_code == 200, r.text[:150])
item = r.json() if r.status_code == 200 else {}
check("item got ITM code", str(item.get("code","")).startswith("ITM"), str(item))

r = c.post("/store/requests", json={"site": "704", "requested_by": "Amal", "needed_by": "2026-08-30",
    "urgency": "normal", "notes": "", "lines": [
      {"item_id": item.get("id"), "description": "", "qty_requested": 100, "unit": "bag", "purpose": "slab", "item_type": "consumable", "est_cost": 0, "notes": ""},
      {"item_id": None, "description": "cushions", "qty_requested": 5, "unit": "pcs", "purpose": "office", "item_type": "consumable", "est_cost": 0, "notes": ""}]}, headers=H)
check("raise request with typed material", r.status_code == 200, r.text[:250])
mr = r.json() if r.status_code == 200 else {}
check("typed material auto-catalogued", bool(mr.get("new_items")), str(mr.get("new_items")))
check("both lines linked to items", all(l.get("item_id") for l in mr.get("lines", [])), str([l.get("item_id") for l in mr.get("lines",[])]))
rid = mr.get("id"); lines = mr.get("lines") or [{},{}]; l1, l2 = lines[0], lines[1]

r = c.post(f"/store/requests/{rid}/status", json={"status": "ordered", "supplier": "AL RAHA TRADING LLC",
    "contact_person": "rashid", "phone": "0501234567", "line_ids": [l1.get("id")]}, headers=H)
check("order line1 from Al Raha", r.status_code == 200, r.text[:150])
r = c.post(f"/store/requests/{rid}/status", json={"status": "ordered", "supplier": "ghantoot",
    "line_ids": [l2.get("id")]}, headers=H)
check("order line2 from Ghantoot", r.status_code == 200, r.text[:150])

r = c.get("/store/suppliers", headers=H)
sups = r.json() if r.status_code == 200 else []
check("two suppliers exist", len(sups) == 2, str(sups)[:250])
alraha = next((s for s in sups if "raha" in s.get("name","").lower()), {})
check("Al Raha tidy + contact kept", alraha.get("name","").startswith("Al Raha") and alraha.get("phone")=="0501234567", str(alraha))
r = c.post("/store/suppliers", json={"name": "al-raha trading", "phone": "", "contact_person": ""}, headers=H)
check("variant spelling reuses record", r.status_code == 200 and r.json().get("id") == alraha.get("id"), r.text[:150])

r = c.get("/store/requests", headers=H)
mr2 = next((x for x in r.json() if x["id"] == rid), {})
lsups = [(l.get("supplier") or {}).get("name") for l in mr2.get("lines",[])]
check("lines carry their suppliers", bool(lsups) and all(lsups), str(lsups))
check("request supplier None when split", mr2.get("supplier") is None, str(mr2.get("supplier")))

r = c.post(f"/store/requests/{rid}/receive-bulk", json={"supplier": "al raha trading",
    "reference": "DO-1", "notes": "", "received_on": None, "lines": [{"line_id": l1["id"], "qty": 100}]}, headers=H)
check("receive line1", r.status_code == 200, r.text[:250])
check("status partial", r.status_code==200 and r.json().get("status") == "partial", r.text[:150])

r = c.post(f"/store/requests/{rid}/receive-bulk", json={"supplier": "Ghantoot", "reference": "DO-2",
    "notes": "", "received_on": None, "lines": [{"line_id": l2["id"], "qty": 5}]}, headers=H)
check("receive line2 -> delivered", r.status_code == 200 and r.json().get("status") in ("delivered","received"), r.text[:250])

r = c.get("/store/stock", headers=H)
stock = r.json()
cem = next((s for s in stock if s["code"] == item.get("code")), {})
check("cement central 100", cem.get("central") == 100, str(cem))
cush = next((s for s in stock if "cushion" in s.get("name","").lower()), {})
check("cushions central 5, tidy name", cush.get("central") == 5 and cush.get("name","").startswith("Cushions"), str(cush))

r = c.post("/store/movements", json={"item_id": item["id"], "kind": "out", "qty": 500,
    "location": "704", "incharge": "Amal", "notes": "", "moved_on": "2026-08-29"}, headers=H)
check("server blocks over-issue", r.status_code == 400, r.text[:150])
r = c.post("/store/movements", json={"item_id": item["id"], "kind": "out", "qty": 40,
    "location": "704", "incharge": "Amal", "notes": "", "moved_on": "2026-08-29"}, headers=H)
check("give-out works", r.status_code == 200, r.text[:250])
r = c.post("/store/movements", json={"item_id": item["id"], "kind": "return", "qty": 10,
    "from_location": "704", "location": "", "incharge": "", "notes": "", "moved_on": "2026-08-29"}, headers=H)
check("return from site", r.status_code == 200, r.text[:250])
r = c.get("/store/stock", headers=H)
cem = next(s for s in r.json() if s["code"] == item["code"])
check("central 70 / site 30 after out+return", cem["central"] == 70 and (cem.get("by_site") or {}).get("704") == 30, str(cem))

for kind in ["stock","by_site","usage","assets","lost","hired"]:
    r = c.get(f"/store/report?kind={kind}", headers=H)
    check(f"report {kind}", r.status_code == 200, r.text[:150])

r = c.get("/store/items/suggest-units", headers=H)
check("suggest-units", r.status_code == 200, r.text[:150])
r = c.get("/store/movements?item_id=%d&limit=8" % item["id"], headers=H)
check("movement history per item", r.status_code == 200 and len(r.json()) >= 3, r.text[:150])

print(); print("FAILURES:" if FAIL else "ALL PASSED", FAIL if FAIL else "")

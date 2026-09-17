"""Build the database the browser audits expect.

Run: python3 tests/seed_audit_db.py        (then start serve_like_nginx.py)

The audits used to run against whatever happened to be on the machine,
so they passed or failed depending on leftovers. This builds the same
starting point every time: three logins, two sites, a worker, and one
material request already ordered and waiting for its delivery - which is
what the data-flow audit follows from the follow-up screen through to
the stock figures.
"""
import os, sys, shutil

DB = "/tmp/audit_app.db"
os.environ["DATABASE_URL"] = "sqlite:///" + DB
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.join(ROOT, "app"))
sys.path.insert(0, ".")

if os.path.exists(DB):
    os.remove(DB)

import database, models, auth                                   # noqa: E402
models.Base.metadata.create_all(database.engine)
import main                                                     # noqa: E402
from fastapi.testclient import TestClient                       # noqa: E402

d = database.SessionLocal()
for u in d.query(models.User).all():          # drop whatever main.py seeded
    d.delete(u)
d.commit()
d.add(models.User(username="admin", hashed_password=auth.hash_password("p"),
                  full_name="Administrator", role="admin"))
d.add(models.User(username="office", hashed_password=auth.hash_password("p"),
                  full_name="Office", role="office",
                  permissions="attendance,summaries,adjustments,live,reports,"
                              "store,requests,approvals,purchase,followup,lporegister"))
d.add(models.User(username="amal", hashed_password=auth.hash_password("p"),
                  full_name="Amal", role="office",
                  permissions="store,storekeeper,requests,followup"))
d.add(models.User(username="site1", hashed_password=auth.hash_password("p"),
                  full_name="Site Engineer", role="site", permissions="attendance,requests"))
for no, nm in (("101", "Rajan"), ("102", "Suresh")):
    d.add(models.Employee(emp_no=no, name=nm, trade="Mason", total_salary=2500,
                          basic_salary=1500, active=True))
for code in ("901", "904"):
    d.add(models.Site(code=code, active=True))
d.add(models.Engineer(name="Febiyan", mobile="0501234567", active=True))
d.commit(); d.close()

c = TestClient(main.app)
H = {"Authorization": "Bearer " + c.post("/auth/login",
     data={"username": "admin", "password": "p"}).json()["access_token"]}

cement = c.post("/store/items", json={"name": "Cement OPC 50kg", "unit": "bag",
                                      "item_type": "consumable", "reorder_level": 20},
                headers=H).json()
c.post("/store/items", json={"name": "Rebar 12mm", "unit": "pcs",
                             "item_type": "consumable"}, headers=H)

mr = c.post("/store/requests", json={
    "site": "901", "requested_by": "Febiyan", "needed_by": "2026-09-25", "urgency": "urgent",
    "notes": "slab pour", "lines": [{"item_id": cement["id"], "qty_requested": 100,
    "unit": "bag", "purpose": "slab", "item_type": "consumable", "description": "",
    "est_cost": 16.0, "notes": ""}]}, headers=H).json()
r = c.post(f"/store/requests/{mr['id']}/status",
           json={"status": "ordered", "supplier": "Al Raha Trading LLC",
                 "contact_person": "Rashid", "phone": "0501234567",
                 "expected_on": "2026-09-20"}, headers=H)
assert r.status_code == 200, r.text[:200]

c.post("/store/purchase/orders", json={
    "order_date": "2026-09-16", "supplier_name": "Al Raha Trading LLC",
    "request_id": mr["id"], "terms": "Due on Receipt",
    "lines": [{"item_id": cement["id"], "description": "Cement OPC 50kg", "qty": 100,
               "unit": "bag", "rate": 16.0, "tax_pct": 5.0}]}, headers=H)

print(f"seeded {DB}: {mr['ref']} ordered for site 901, awaiting delivery")

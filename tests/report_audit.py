"""Every report column must carry real data.

Run: cd app && DATABASE_URL=sqlite:////tmp/ra.db python3 ../tests/report_audit.py

Seeds a realistic store - consumable, asset and rental; a request
ordered and part-delivered; issues, a return and a loss - then checks
that no report column is empty for every row, and that every export
builds. Exists because columns were reading fields nothing ever fills
(hired from, since, category, value), so reports showed rows of dashes
while the store already knew the answers.
"""
import sys
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main

db = database.SessionLocal()
for u, r in [('office', 'office'), ('site', 'site'), ('keeper', 'staff')]:
    db.add(models.User(username=u, hashed_password=auth.hash_password('p'), full_name=u, role=r))
db.commit(); db.close()
c = TestClient(main.app)
def H(u): return {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': u, 'password': 'p'}).json()['access_token']}
O, S, K = H('office'), H('site'), H('keeper')

items = {}
for name, unit, typ in [('Cement OPC 42.5', 'bag', 'consumable'), ('Steel Rebar 20MM', 't', 'consumable'),
                        ('Steel Cutting Machine', 'pcs', 'asset'), ('Scaffold Ledger 1.20M', 'pcs', 'rental')]:
    items[name] = c.post('/store/items', json={'name': name, 'unit': unit, 'item_type': typ, 'reorder_level': 20}, headers=K).json()
mr = c.post('/store/requests', json={'site': '904', 'requested_by': 'febiyan', 'needed_by': '2026-09-02',
    'urgency': 'urgent', 'notes': '', 'lines': [
      {'item_id': items['Cement OPC 42.5']['id'], 'qty_requested': 100, 'unit': 'bag', 'purpose': 'slab', 'item_type': 'consumable', 'description': '', 'est_cost': 0, 'notes': ''},
      {'item_id': items['Steel Rebar 20MM']['id'], 'qty_requested': 10, 'unit': 't', 'purpose': 'columns', 'item_type': 'consumable', 'description': '', 'est_cost': 0, 'notes': ''}]}, headers=S).json()
L = [l['id'] for l in mr['lines']]
c.post(f"/store/requests/{mr['id']}/status", json={'status': 'ordered', 'supplier': 'Al Raha Trading',
    'contact_person': 'bijuam', 'phone': '050090890', 'expected_on': '2026-09-01', 'line_ids': L}, headers=O)
c.post(f"/store/requests/{mr['id']}/receive-bulk", json={'supplier': 'Al Raha Trading', 'reference': 'INV-778',
    'notes': '', 'received_on': '2026-08-25', 'lines': [{'line_id': L[0], 'qty': 100}]}, headers=K)
for it, q, sup, dt in [('Steel Cutting Machine', 2, 'Newstar', '2026-08-20'), ('Scaffold Ledger 1.20M', 700, 'Gateway Scaffolding', '2026-08-18')]:
    c.post('/store/movements', json={'item_id': items[it]['id'], 'kind': 'in', 'qty': q, 'location': '',
        'supplier': sup, 'reference': 'DO-1', 'moved_on': dt}, headers=K)
c.post('/store/movements', json={'item_id': items['Cement OPC 42.5']['id'], 'kind': 'out', 'qty': 40, 'location': '904', 'incharge': 'Akhil', 'moved_on': '2026-08-27'}, headers=K)
c.post('/store/movements', json={'item_id': items['Scaffold Ledger 1.20M']['id'], 'kind': 'out', 'qty': 125, 'location': '905', 'incharge': 'Raj', 'moved_on': '2026-08-26'}, headers=K)
c.post('/store/movements', json={'item_id': items['Steel Cutting Machine']['id'], 'kind': 'out', 'qty': 1, 'location': '907', 'incharge': 'Muhsina', 'moved_on': '2026-08-28'}, headers=K)
c.post('/store/movements', json={'item_id': items['Scaffold Ledger 1.20M']['id'], 'kind': 'lost', 'qty': 5, 'from_location': '905', 'moved_on': '2026-08-30', 'notes': 'damaged on site'}, headers=K)

bad = []
for k in ["stock", "low", "by_site", "purchases", "usage", "assets", "lost", "hired"]:
    d = c.get(f'/store/report?kind={k}', headers=K)
    if d.status_code != 200:
        print(f"FAIL {k:12} HTTP {d.status_code}"); bad.append(k); continue
    rows = d.json().get('rows', [])
    if not rows:
        print(f"     {k:12} (no rows)"); continue
    empt = [col for col in rows[0] if all(r.get(col) in (None, "", "-", {}, []) for r in rows)]
    print(("FAIL " if empt else "PASS ") + f"{k:12} {len(rows):2} rows, {len(rows[0]):2} cols" + (f"   EMPTY: {empt}" if empt else ""))
    if empt: bad.append(k)

# A typo or retired report must fail loudly, not quietly return stock.
if c.get('/store/report?kind=nonsense', headers=K).status_code != 400:
    print("FAIL unknown report kind is not rejected"); bad.append("unknown-kind")
else:
    print("PASS unknown report kind is rejected")

tok = c.post('/auth/download-token', headers=K).json().get('token', '')
fails = [f"{k} {f}" for k in ["stock", "purchases", "hired", "lost", "assets", "usage", "by_site", "low"]
         for f in ("excel", "pdf")
         if c.get(f'/export/store/report?kind={k}&format={f}&token={tok}', headers=K).status_code != 200]
print(("FAIL exports: " + ", ".join(fails)) if fails else "PASS every export builds")
bad += fails

print()
print("REPORTS CLEAN" if not bad else f"{len(bad)} PROBLEM(S): {bad}")
sys.exit(1 if bad else 0)

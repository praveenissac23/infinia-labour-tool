"""A backup must hold the whole business, and a restore must bring it back.

Run: cd app && DATABASE_URL=sqlite:////tmp/bk.db python3 ../tests/backup_test.py

Builds a company with attendance and a working store, takes a backup,
wipes both, restores, and checks everything came back - including the
links between requests, suppliers and stock. Exists because the backup
covered only the payroll tables: the entire store, thousands of
materials, every movement and request, existed only on the live server.
"""
import sys, json
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main

db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Administrator', role='admin'))
db.add(models.Employee(emp_no='101', name='Rajan', trade='Mason', total_salary=2500, basic_salary=1500, active=True))
db.add(models.Site(code='904', active=True))
db.add(models.Engineer(name='Febiyan', active=True))
db.commit(); db.close()
c = TestClient(main.app)
H = {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': 'admin', 'password': 'p'}).json()['access_token']}
FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{x}]'))
    if not ok: FAIL.append(l)

# A working store: materials, an ordered and delivered request, movements.
it1 = c.post('/store/items', json={'name': 'Cement OPC', 'unit': 'bag', 'item_type': 'consumable', 'reorder_level': 20}, headers=H).json()
it2 = c.post('/store/items', json={'name': 'Scaffold Ledger', 'unit': 'pcs', 'item_type': 'rental'}, headers=H).json()
mr = c.post('/store/requests', json={'site': '904', 'requested_by': 'Febiyan', 'needed_by': '2026-09-05',
    'urgency': 'urgent', 'notes': 'for slab', 'lines': [{'item_id': it1['id'], 'qty_requested': 100, 'unit': 'bag',
    'purpose': 'slab', 'item_type': 'consumable', 'description': '', 'est_cost': 0, 'notes': ''}]}, headers=H).json()
LN = mr['lines'][0]['id']
c.post(f"/store/requests/{mr['id']}/status", json={'status': 'ordered', 'supplier': 'Al Raha Trading',
    'contact_person': 'bijuam', 'phone': '050090890', 'expected_on': '2026-09-02'}, headers=H)
c.post(f"/store/requests/{mr['id']}/receive-bulk", json={'supplier': 'Al Raha Trading', 'reference': 'INV-1',
    'notes': '', 'received_on': '2026-08-28', 'lines': [{'line_id': LN, 'qty': 100}]}, headers=H)
c.post('/store/movements', json={'item_id': it2['id'], 'kind': 'in', 'qty': 700, 'location': '', 'supplier': 'Gateway', 'moved_on': '2026-08-20'}, headers=H)
c.post('/store/movements', json={'item_id': it1['id'], 'kind': 'out', 'qty': 40, 'location': '904', 'incharge': 'Akhil', 'moved_on': '2026-08-29'}, headers=H)
c.post('/attendance/save', json={'month_year': 'August 2026', 'rows': [{'emp_no': '101', 'full_date': '2026-08-28',
    'am': 'Present', 'pm': 'Present', 'site': '904', 'engineer': 'Febiyan', 'ot': 2, 'bh': 0, 'comments': ''}]}, headers=H)

before = {
    'items': len(c.get('/store/items', headers=H).json()),
    'stock': {s['code']: (s['central'], s['out_at_sites']) for s in c.get('/store/stock', headers=H).json()},
    'requests': len(c.get('/store/requests', headers=H).json()),
    'suppliers': sorted(s['name'] for s in c.get('/store/suppliers', headers=H).json()),
    'employees': len(c.get('/employees', headers=H).json()),
    'attendance': len(c.get('/attendance/2026-08-28', headers=H).json()),
}

bid = c.post('/backup/create', headers=H).json()['id']
raw = json.loads(database.SessionLocal().query(models.Backup).filter(models.Backup.id == bid).first().data)
for key in ['users', 'employees', 'sites', 'engineers', 'daily_rows',
            'suppliers', 'store_items', 'store_movements', 'material_requests', 'material_request_lines']:
    ck(f'backup carries {key}', key in raw and len(raw[key]) > 0, f"{len(raw.get(key, []))} rows")

# Lose everything, as a dead server would.
d2 = database.SessionLocal()
for m in (models.MaterialRequestLine, models.MaterialRequest, models.StoreMovement, models.StoreItem,
          models.Supplier, models.DailyRow, models.SalaryAdjustment, models.Employee, models.Site, models.Engineer):
    d2.query(m).delete()
d2.commit(); d2.close()
ck('store really was wiped', len(c.get('/store/items', headers=H).json()) == 0)

ck('restore ran', c.post(f'/backup/{bid}/restore', headers=H).status_code == 200)
after = {
    'items': len(c.get('/store/items', headers=H).json()),
    'stock': {s['code']: (s['central'], s['out_at_sites']) for s in c.get('/store/stock', headers=H).json()},
    'requests': len(c.get('/store/requests', headers=H).json()),
    'suppliers': sorted(s['name'] for s in c.get('/store/suppliers', headers=H).json()),
    'employees': len(c.get('/employees', headers=H).json()),
    'attendance': len(c.get('/attendance/2026-08-28', headers=H).json()),
}
for key in before:
    ck(f'{key} came back exactly', after[key] == before[key], f"{after[key]} vs {before[key]}")
req = c.get('/store/requests', headers=H).json()[0]
ck('a request keeps its supplier link', (req['lines'][0].get('supplier') or {}).get('name') == 'Al Raha Trading')
ck('a request keeps what arrived', req['lines'][0]['qty_received'] == 100)
ck('admin can still sign in after a restore', c.post('/auth/login', data={'username': 'admin', 'password': 'p'}).status_code == 200)

print()
print('BACKUP COMPLETE AND RESTORABLE' if not FAIL else f'{len(FAIL)} PROBLEM(S): {FAIL}')
sys.exit(1 if FAIL else 0)

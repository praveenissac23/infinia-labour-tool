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
it2 = c.post('/store/items', json={'name': 'Scaffold Ledger', 'unit': 'pcs', 'item_type': 'rental',
                                   'rental_supplier': 'Al Raha Scaffolding'}, headers=H).json()
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
raw = main._backup_json(database.SessionLocal().query(models.Backup).filter(models.Backup.id == bid).first())
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

# ---- An OLD backup must never erase data it predates. A snapshot taken
# before the store existed carries no store keys at all; restoring it
# should bring back the payroll side and leave the inventory alone.
old_style = {"generated_at": "2026-08-01T00:00:00",
             "employees": [{"id": 1, "emp_no": "101", "name": "Rajan", "trade": "Mason",
                            "total_salary": 2500.0, "basic_salary": 1500.0, "active": True,
                            "created_at": None, "updated_at": None}],
             "sites": [], "engineers": [], "daily_rows": [], "summaries": [], "adjustments": []}
d3 = database.SessionLocal()
d3.add(models.Backup(created_by=1, trigger='old-format', data=json.dumps(old_style)))
d3.commit()
old_id = d3.query(models.Backup).order_by(models.Backup.id.desc()).first().id
d3.close()
items_before_old = len(c.get('/store/items', headers=H).json())
ck('an old-format backup restores without error',
   c.post(f'/backup/{old_id}/restore', headers=H).status_code == 200)
ck('an old backup does not erase the store',
   len(c.get('/store/items', headers=H).json()) == items_before_old,
   f"{len(c.get('/store/items', headers=H).json())} vs {items_before_old}")

# ---- Restoring onto a REBUILT server, which is the real disaster case.
# The rescue admin already holds an id the snapshot claims, so this is
# where an id collision would break the whole restore.
import subprocess, os, tempfile
snap = json.dumps(main._backup_json(database.SessionLocal().query(models.Backup)
                             .filter(models.Backup.id == bid).first()))
fresh = tempfile.NamedTemporaryFile(suffix='.db', delete=False).name
script = f"""
import sys, json; sys.path.insert(0, '.')
import os
os.environ['DATABASE_URL'] = 'sqlite:///{fresh}'
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main
db = database.SessionLocal()
db.add(models.User(username='rescue', hashed_password=auth.hash_password('p'), full_name='R', role='admin'))
db.add(models.Backup(created_by=1, trigger='file', data=open({fresh!r} + '.json').read()))
db.commit(); db.close()
c = TestClient(main.app)
H = {{'Authorization': 'Bearer ' + c.post('/auth/login', data={{'username': 'rescue', 'password': 'p'}}).json()['access_token']}}
bid = database.SessionLocal().query(models.Backup).first().id
r = c.post(f'/backup/{{bid}}/restore', headers=H)
items = len(c.get('/store/items', headers=H).json())
reqs = c.get('/store/requests', headers=H).json()
stock = {{s['code']: s['central'] for s in c.get('/store/stock', headers=H).json()}}
login = c.post('/auth/login', data={{'username': 'admin', 'password': 'p'}}).status_code
print(json.dumps({{'status': r.status_code, 'items': items, 'requests': len(reqs),
                  'supplier': (reqs[0]['lines'][0].get('supplier') or {{}}).get('name') if reqs else None,
                  'stock': stock, 'old_admin_login': login}}))
"""
open(fresh + '.json', 'w').write(snap)
env = dict(os.environ); env['DATABASE_URL'] = f'sqlite:///{fresh}'
res = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, env=env, cwd='.')
try:
    out = json.loads(res.stdout.strip().splitlines()[-1])
    ck('restores onto a rebuilt server', out['status'] == 200, res.stderr[-200:])
    ck('materials came back there too', out['items'] == before['items'], str(out))
    ck('requests and supplier links came back', out['requests'] == before['requests'] and out['supplier'] == 'Al Raha Trading', str(out))
    ck('original staff can sign in on the new server', out['old_admin_login'] == 200)
except Exception as e:
    ck('rebuilt-server restore readable', False, f"{e} :: {res.stdout[-200:]} {res.stderr[-200:]}")

# ---- A backup is the whole company, so not everyone may take one ----
# /backup/latest/download had always checked. /backup/{id}/download,
# which hands out the same complete copy, checked nothing: a site
# engineer with a download token took every salary, every login and the
# audit log with them. Both routes share one gate now, and one rule
# about the stored passwords.
db = database.SessionLocal()
db.add(models.User(username='sitelad', hashed_password=auth.hash_password('p'),
                   full_name='Site Engineer', role='site'))
db.commit(); db.close()
SITE = {'Authorization': 'Bearer ' + c.post(
    '/auth/login', data={'username': 'sitelad', 'password': 'p'}).json()['access_token']}

stored = c.get('/backup/list', headers=H).json()
stored = stored if isinstance(stored, list) else stored.get('backups', [])
# Not the old-format fixture planted above: that one is a deliberately
# thin snapshot, and picking it made the completeness check below
# measure the fixture instead of the route.
full = [b for b in stored if b.get('trigger') != 'old-format']
bid = full[0]['id'] if full else None
ck('there is a stored backup to test against', bid is not None)

site_dl = c.post('/auth/download-token', headers=SITE).json().get('token', '')
ck('a site engineer can still mint a download token', bool(site_dl))
for route in (f'/backup/{bid}/download', '/backup/latest/download'):
    r = c.get(f'{route}?token={site_dl}')
    ck(f'a site engineer is refused {route}', r.status_code == 403,
       f'{r.status_code} {r.text[:120]}')

admin_dl = c.post('/auth/download-token', headers=H).json().get('token', '')
for route in (f'/backup/{bid}/download', '/backup/latest/download'):
    r = c.get(f'{route}?token={admin_dl}')
    ck(f'an admin still gets {route}', r.status_code == 200, r.status_code)
    if r.status_code != 200:
        continue
    d = json.loads(r.content.decode('utf-8'))
    ck(f'{route} is still a complete copy', len(d.get('tables', [])) > 10,
       len(d.get('tables', [])))
    left = [u['username'] for u in d.get('users', []) if u.get('hashed_password')]
    ck(f'{route} carries no stored passwords', not left, left)

print()
print('BACKUP COMPLETE AND RESTORABLE' if not FAIL else f'{len(FAIL)} PROBLEM(S): {FAIL}')
sys.exit(1 if FAIL else 0)

"""Who can see what. Run after any change to permissions or endpoints.

Run: cd app && DATABASE_URL=sqlite:////tmp/sa.db python3 ../tests/security_audit.py

Checks that download links refuse a missing, mangled or wrong-scope
token; that a store keeper or site engineer can read worker names but
not pay, and cannot list staff logins; that admin still sees
everything; and that nothing at all is readable without logging in.
"""
import sys
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main

db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='A', role='admin'))
db.add(models.User(username='keeper', hashed_password=auth.hash_password('p'), full_name='K', role='staff',
                   permissions='dashboard,store,requests,followup'))
db.add(models.User(username='site', hashed_password=auth.hash_password('p'), full_name='S', role='site'))
db.add(models.Employee(emp_no='101', name='Rajan', trade='Mason', total_salary=2500, basic_salary=1500, active=True))
db.commit(); db.close()
c = TestClient(main.app)
def H(u): return {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': u, 'password': 'p'}).json()['access_token']}
FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{x}]'))
    if not ok: FAIL.append(l)

# Download links
for p in ['/employees/export', '/export/store/report?kind=stock', '/export/2026-08/excel', '/export/store/request/1']:
    ck(f'missing token refused: {p[:30]}', c.get(p).status_code in (401, 422), str(c.get(p).status_code))
ck('mangled token refused', c.get('/export/store/report?kind=stock&token=rubbish').status_code == 401)
login_tok = c.post('/auth/login', data={'username': 'admin', 'password': 'p'}).json()['access_token']
ck('a login token is not a download link', c.get(f'/export/store/report?kind=stock&token={login_tok}').status_code == 401)
dl = c.post('/auth/download-token', headers=H('admin')).json()['token']
ck('a proper download token works', c.get(f'/export/store/report?kind=stock&token={dl}', headers=H('admin')).status_code == 200)

# Pay and logins
for role in ('keeper', 'site'):
    e = c.get('/employees?active_only=true', headers=H(role)).json()
    ck(f'{role} sees worker names', bool(e) and e[0]['name'] == 'Rajan')
    ck(f'{role} cannot see pay', e[0]['total_salary'] == 0 and e[0]['basic_salary'] == 0, str(e[0]))
    ck(f'{role} cannot list staff logins', c.get('/users', headers=H(role)).status_code == 403)
    ck(f'{role} cannot read salary adjustments', c.get('/salary-adjustments', headers=H(role)).status_code in (403, 404))
a = c.get('/employees', headers=H('admin')).json()
ck('admin still sees pay', a[0]['total_salary'] == 2500)
ck('admin still lists logins', c.get('/users', headers=H('admin')).status_code == 200)

# A site engineer may raise a request but must not approve, order or
# delete one - the screens hide those, and the API must too.
db2 = database.SessionLocal()
db2.add(models.User(username='site2', hashed_password=auth.hash_password('p'), full_name='S2', role='site'))
db2.add(models.User(username='office', hashed_password=auth.hash_password('p'), full_name='O', role='office'))
db2.commit(); db2.close()
S2, OF = H('site2'), H('office')
it = c.post('/store/items', json={'name': 'Cement', 'unit': 'bag'}, headers=OF).json()
mr = c.post('/store/requests', json={'site': '905', 'requested_by': 'Amal', 'needed_by': '2026-09-05',
    'urgency': 'normal', 'notes': '', 'lines': [{'item_id': it['id'], 'qty_requested': 10, 'unit': 'bag',
    'purpose': 'x', 'item_type': 'consumable', 'description': '', 'est_cost': 0, 'notes': ''}]}, headers=S2).json()
LN = mr['lines'][0]['id']
ck('site can raise a request', 'id' in mr)
ck('site cannot approve its own request',
   c.post(f"/store/requests/{mr['id']}/status", json={'status': 'approved'}, headers=S2).status_code == 403)
ck('site cannot approve a single material',
   c.post(f'/store/request-lines/{LN}/decision', json={'decision': 'approved'}, headers=S2).status_code == 403)
ck('site cannot order from a supplier',
   c.post(f"/store/requests/{mr['id']}/status", json={'status': 'ordered', 'supplier': 'X'}, headers=S2).status_code == 403)
ck('site cannot delete a request', c.delete(f"/store/requests/{mr['id']}", headers=S2).status_code == 403)
ck('office can approve',
   c.post(f"/store/requests/{mr['id']}/status", json={'status': 'approved'}, headers=OF).status_code == 200)

# Settings is open to everyone, but only for your own password and a
# backup. Everything else on that screen is administration.
db4 = database.SessionLocal()
db4.add(models.User(username='office2', hashed_password=auth.hash_password('p'), full_name='O2', role='office'))
db4.commit(); db4.close()
O2 = H('office2')
ck('a non-admin can reach Settings',
   'settings' in main.effective_permissions(
       database.SessionLocal().query(models.User).filter(models.User.username == 'office2').first()))
ck('a non-admin can change their own password',
   c.post('/auth/change-password', json={'current_password': 'p', 'new_password': 'newpass123'}, headers=O2).status_code == 200)
ck('a non-admin can take a backup', c.post('/backup/create', headers=O2).status_code == 200)
ck('a non-admin cannot restore', c.post('/backup/1/restore', headers=O2).status_code == 403)
ck('a non-admin cannot delete a backup', c.delete('/backup/1', headers=O2).status_code == 403)
ck('a non-admin cannot create a login',
   c.post('/users', json={'username': 'zz', 'password': 'pw123456', 'full_name': 'Z', 'role': 'site'}, headers=O2).status_code == 403)
ck('a non-admin cannot reset another password',
   c.post('/users/1/reset-password', json={'new_password': 'hacked123'}, headers=O2).status_code == 403)
ck('a non-admin cannot clear the data',
   c.post('/backup/fresh-start', json={'confirm': 'CLEAR EVERYTHING'}, headers=O2).status_code == 403)

# Nothing without a login
for p in ['/store/requests', '/store/items', '/notifications', '/store/suppliers', '/employees', '/users']:
    ck(f'no login refused: {p}', c.get(p).status_code in (401, 403), str(c.get(p).status_code))

print()
print('SECURITY CLEAN' if not FAIL else f'{len(FAIL)} PROBLEM(S): {FAIL}')
sys.exit(1 if FAIL else 0)

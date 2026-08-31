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

# Nothing without a login
for p in ['/store/requests', '/store/items', '/notifications', '/store/suppliers', '/employees', '/users']:
    ck(f'no login refused: {p}', c.get(p).status_code in (401, 403), str(c.get(p).status_code))

print()
print('SECURITY CLEAN' if not FAIL else f'{len(FAIL)} PROBLEM(S): {FAIL}')
sys.exit(1 if FAIL else 0)

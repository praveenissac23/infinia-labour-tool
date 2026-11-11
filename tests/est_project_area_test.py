"""Project details: area statement (typed unit kept), type of contract, duration, activity log, contract types list.
    cd app && DATABASE_URL=sqlite:////tmp/epa.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/est_project_area_test.py   (empty db)"""
import sys
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main
db = database.SessionLocal()
if not db.query(models.User).filter(models.User.username == 'admin').first():
    db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Administrator', role='admin')); db.commit()
c = TestClient(main.app, raise_server_exceptions=False)
H = {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': 'admin', 'password': 'p'}).json()['access_token']}
FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{str(x)[:300]}]'))
    if not ok: FAIL.append(l)
r = c.post('/store/est/projects', json={'code': 'T99', 'contract_type': 'Lump Sum', 'bua': '1,250', 'bua_u': 'sqm', 'plot_area': 37350.73, 'plot_area_u': 'sqft', 'duration_months': 14.5}, headers=H)
ck('new project with the new fields', r.status_code == 200, r.text); pid = r.json()['id']
p = c.get(f'/store/est/projects/{pid}', headers=H).json()['project']
ck('typed value and unit kept exactly', p['plot_area'] == 37350.73 and p['plot_area_u'] == 'sqft' and p['bua'] == 1250 and p['bua_u'] == 'sqm', p)
ck('empty stays empty', p['gfa'] is None and p['gfa_u'] is None, p)
ck('duration with decimals', p['duration_months'] == 14.5, p)
ck('below zero refused', c.patch(f'/store/est/projects/{pid}', json={'gfa': '-3', 'gfa_u': 'sqm'}, headers=H).status_code == 400)
ck('zero duration refused', c.patch(f'/store/est/projects/{pid}', json={'duration_months': '0'}, headers=H).status_code == 400)
ck('edit', c.patch(f'/store/est/projects/{pid}', json={'gfa': '1100', 'gfa_u': 'sqm', 'contract_type': 'Turnkey works', 'duration_months': ''}, headers=H).status_code == 200)
p = c.get(f'/store/est/projects/{pid}', headers=H).json()['project']
ck('Other type typed in is kept; duration emptied', p['contract_type'] == 'Turnkey works' and p['duration_months'] is None, p)
db = database.SessionLocal()
a = db.query(models.AuditLog).filter(models.AuditLog.action == 'est_project_edit').order_by(models.AuditLog.id.desc()).first()
ck('activity log: old -> new', a and 'GFA: - -> 1,100.00 Sqm' in a.details and 'Type of contract: Lump Sum -> Turnkey works' in a.details and 'Project duration: 14.5 months -> -' in a.details, a and a.details)
ck('undo = the old values back', c.patch(f'/store/est/projects/{pid}', json={'gfa': '', 'gfa_u': '', 'contract_type': 'Lump Sum', 'duration_months': 14.5}, headers=H).status_code == 200
   and c.get(f'/store/est/projects/{pid}', headers=H).json()['project']['gfa'] is None)
ck('list: type and duration', any(r['id'] == pid and r['contract_type'] == 'Lump Sum' and r['duration_months'] == 14.5 for r in c.get('/store/est/dash', headers=H).json()['projects']))
r = c.put('/store/est/contract-types', json={'types': 'Lump Sum\nOther\nRe-measured\nlump sum'}, headers=H)
ck('contract types: saved, Other and repeats dropped', r.status_code == 200 and r.json()['types'] == ['Lump Sum', 'Re-measured'], r.text)
ck('meta carries the list', c.get('/store/est/meta', headers=H).json()['contract_types'] == ['Lump Sum', 'Re-measured'])
c.put('/store/est/contract-types', json={'types': ['Lump Sum', 'Re-measured', 'Design & Build', 'Cost Plus', 'Unit Rate', 'Labour Only']}, headers=H)
print(f"{len(FAIL)} FAILED" if FAIL else 'ALL PASS')

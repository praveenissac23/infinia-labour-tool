"""Work types (13/11/2026): "Deep Cleaning Works" on the Work list of every subcontract / LPO / manpower, in every
project; kept spelt as the list has it; fills Trade = Cleaning; Settings > Work types (admin) adds, renames, removes;
the one-time fix for M/s. Manzel Al Rabhee (IC/LPO/20260201).
    cd app && DATABASE_URL=sqlite:////tmp/ewt.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/est_work_types_test.py   (empty db)"""
import sys
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main, estimation as E
db = database.SessionLocal()
if not db.query(models.User).filter(models.User.username == 'admin').first():
    db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Administrator', role='admin'))
    db.add(models.User(username='qs', hashed_password=auth.hash_password('p'), full_name='QS', role='office', permissions='estimation'))
    db.commit()
c = TestClient(main.app, raise_server_exceptions=False)
H = {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': 'admin', 'password': 'p'}).json()['access_token']}
HQ = {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': 'qs', 'password': 'p'}).json()['access_token']}
FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{str(x)[:300]}]'))
    if not ok: FAIL.append(l)

m = c.get('/store/est/meta', headers=H).json()
ck('Deep Cleaning Works is on the Work list', 'Deep Cleaning Works' in m['scopes'], m['scopes'][:8])
body = [x for x in m['scopes'] if x != 'Other']
ck('alphabetical, Other last', body == sorted(body, key=str.lower) and m['scopes'][-1] == 'Other', m['scopes'])
ck('typing "deep" or "clean" finds it', [x for x in m['scopes'] if 'deep' in x.lower()] == ['Deep Cleaning Works'] and 'Deep Cleaning Works' in [x for x in m['scopes'] if 'clean' in x.lower()])
ck('it fills Trade = Cleaning', m['scope_trade'].get('Deep Cleaning Works') == 'Cleaning', m.get('scope_trade'))
ck('Cleaning is on the Trade list', 'Cleaning' in m['trades'], m['trades'])

ids = []
for code in ('T1', 'T2'):
    ids.append(c.post('/store/est/projects', json={'code': code, 'name': 'Villa ' + code}, headers=H).json()['id'])
subs = {}
for pid, kind, typed in ((ids[0], 'LPO', 'deep cleaning works'), (ids[0], 'Subcontract', '  Deep  Cleaning Works '), (ids[1], 'Manpower', 'DEEP CLEANING WORKS')):
    r = c.post('/store/est/subs', json={'project_id': pid, 'name': 'Cleaner ' + kind, 'kind': kind, 'scope': typed, 'trade': 'Cleaning', 'value': 1000, 'ret_pct': 0}, headers=H)
    ck(f'{kind} saved', r.status_code == 200, r.text); subs[kind] = r.json().get('id')
db = database.SessionLocal()
got = {s.kind: s.scope for s in db.query(E.EstSub).all()}
ck('typed by hand in any case or spacing, saved exactly "Deep Cleaning Works" for every type and project', set(got.values()) == {'Deep Cleaning Works'}, got)
ck('edit keeps the spelling too', c.patch(f"/store/est/subs/{subs['LPO']}", json={'scope': 'deep cleaning WORKS'}, headers=H).status_code == 200)
db.expire_all(); ck('... "Deep Cleaning Works"', db.query(E.EstSub).get(subs['LPO']).scope == 'Deep Cleaning Works')
r = c.post('/store/est/subs', json={'project_id': ids[0], 'name': 'Other one', 'kind': 'LPO', 'scope': 'Window cleaning', 'value': 10, 'ret_pct': 0}, headers=H)
db.expire_all(); ck('a work not on the list is kept as typed', db.query(E.EstSub).get(r.json()['id']).scope == 'Window cleaning')
b = c.get(f'/store/est/projects/{ids[0]}', headers=H).json()
ck('project shows the Work', any(s['scope'] == 'Deep Cleaning Works' for s in b['subs']))
tk = c.post('/auth/download-token', headers=H).json().get('token') or ''
for fmt in ('excel', 'pdf', 'preview'):
    x = c.get(f'/export/est/subs?pid={ids[0]}&format={fmt}&token={tk}')
    ck(f'subcontractors {fmt} has the Work', x.status_code == 200 and (fmt != 'preview' or 'Deep Cleaning Works' in x.text), x.status_code)

# Settings > Work types: admin only; rename moves the subcontracts; removed stays on them
ck('not for a non-admin', c.put('/store/est/work-types', json={'types': [{'name': 'X'}]}, headers=HQ).status_code == 403)
cur = c.get('/store/est/work-types', headers=H).json()['types']
new = [x if x['name'] != 'Deep Cleaning Works' else {'name': 'Deep Cleaning & Sanitising', 'trade': 'Cleaning'} for x in cur if x['name'] != 'Wardrobes'] + [{'name': 'Façade Cleaning', 'trade': 'Cleaning'}]
r = c.put('/store/est/work-types', json={'types': new, 'renames': {'Deep Cleaning Works': 'Deep Cleaning & Sanitising'}}, headers=H).json()
ck('rename moved the 3 subcontracts with it', r['moved'] == 3, r)
names = [x['name'] for x in r['types']]
ck('added, removed, still alphabetical with Other last', 'Façade Cleaning' in names and 'Wardrobes' not in names and names[-1] == 'Other' and names[:-1] == sorted(names[:-1], key=str.lower), names)
db.expire_all()
ck('subcontracts carry the new name', {s.scope for s in db.query(E.EstSub).filter(E.EstSub.name.like('Cleaner%')).all()} == {'Deep Cleaning & Sanitising'})
m = c.get('/store/est/meta', headers=H).json()
ck('the form list follows Settings', 'Façade Cleaning' in m['scopes'] and m['scope_trade'].get('Façade Cleaning') == 'Cleaning')
ck('back to the standard list', c.put('/store/est/work-types', json={'types': c.get('/store/est/work-types', headers=H).json()['standard']}, headers=H).status_code == 200
   and 'Deep Cleaning Works' in c.get('/store/est/meta', headers=H).json()['scopes'])

# one-time: M/s. Manzel Al Rabhee, LPO IC/LPO/20260201 (Work was blank, Trade Civil)
mz = E.EstSub(project_id=ids[1], name='M/s. Manzel Al Rabhee Technical Services & Cleaning', kind='LPO', lpo=': IC/LPO/20260201', agreement='IC/LPO/20260201', scope='', trade='Civil', value=14700)
ot = E.EstSub(project_id=ids[1], name='Somebody else', kind='LPO', lpo='IC/LPO/20260202', scope='', trade='Civil', value=1)
db.add_all([mz, ot]); db.commit()
main._fix_manzel_work(db); db.refresh(mz); db.refresh(ot)
ck('Manzel: Work = Deep Cleaning Works, Trade = Cleaning', mz.scope == 'Deep Cleaning Works' and mz.trade == 'Cleaning', (mz.scope, mz.trade))
ck('nobody else touched', ot.scope == '' and ot.trade == 'Civil')
mz.scope = 'Changed later'; db.commit(); main._fix_manzel_work(db); db.refresh(mz)
ck('only once', mz.scope == 'Changed later')
print('\n' + ('ALL PASS' if not FAIL else f'{len(FAIL)} FAILED'))
sys.exit(1 if FAIL else 0)

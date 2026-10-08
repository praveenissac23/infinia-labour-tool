"""Notifications: the role's allow-list on Access, the person's own switches,
and both the bell and the phone follow them.

Run: cd app && rm -f /tmp/ns.db && DATABASE_URL=sqlite:////tmp/ns.db INFINIA_NO_PUSH=1 python3 ../tests/notif_settings_test.py
"""
import sys
from datetime import date
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main, push

FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{x}]'))
    if not ok: FAIL.append(l)

db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='A', role='admin'))
db.add(models.User(username='pro', hashed_password=auth.hash_password('p'), full_name='Jomon', role='office',
                   permissions='dashboard,settings,approvals,requests,store,expiry'))
db.add(models.Site(code='913', active=True))
db.add(models.StoreItem(code='ITM1', name='Cement', unit='bag', item_type='consumable', active=True))
db.commit(); db.close()
c = TestClient(main.app)
tok = lambda u: {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': u, 'password': 'p'}).json()['access_token']}
A, P = tok('admin'), tok('pro')
# an approved request waiting for an LPO, and a new pending one
r2 = c.post('/store/requests', headers=A, json={'site': '913', 'requested_by': 'Raj', 'urgency': 'normal', 'lines': [{'item_id': 1, 'qty_requested': 5, 'unit': 'bag'}]}).json()
for l in r2['lines']: c.post(f"/store/request-lines/{l['id']}/decision", headers=A, json={'decision': 'approved', 'reason': ''})
r1 = c.post('/store/requests', headers=A, json={'site': '913', 'requested_by': 'Raj', 'urgency': 'urgent', 'lines': [{'description': 'Nails', 'qty_requested': 2, 'unit': 'kg'}]}).json()
ck('two requests: one pending, one approved', r1.get('status') == 'pending' and r2['ref'] != r1.get('ref'), (r1.get('status'), r2['ref']))
kinds = lambda h: sorted({n['kind'] for n in c.get('/notifications', headers=h).json()['notifications']})
ck('bell: new request and a purchasing item for an office login', 'request' in kinds(P) and 'purchase' in kinds(P), kinds(P))
s = c.get('/notifications/settings', headers=P).json()
ck('settings list the groups, purchasing allowed and on', any(g['id'] == 'purchase' and g['allowed'] and g['on'] for g in s['groups']), s)
ck('a group the login has no right for is greyed', any(g['id'] == 'attendance' and not g['allowed'] for g in s['groups']))
# the PRO switches purchasing off for himself
on = [g['id'] for g in s['groups'] if g['id'] != 'purchase']
s2 = c.post('/notifications/settings', headers=P, json={'on': on}).json()
ck('switched off for himself', not next(g for g in s2['groups'] if g['id'] == 'purchase')['on'])
ck('bell no longer shows purchasing, still shows requests', 'purchase' not in kinds(P) and 'request' in kinds(P), kinds(P))
# the phone follows the same list
db = database.SessionLocal(); u = db.query(models.User).filter_by(username='pro').first()
notes = main._notes_for(db, u); db.close()
ck('phone list is the same filtered list', 'purchase' not in {n['kind'] for n in notes} and any(n['kind'] == 'request' for n in notes))
# the admin takes requests away from the role
role = c.post('/permissions/roles', headers=A, json={'name': 'PRO', 'tabs': ['store.requests.approvals', 'store.requests.requests', 'store.store.home'], 'notif': ['store', 'expiry']}).json()
ck('role saved with its notification list', role['notif'] == ['expiry', 'store'], role)
c.post('/permissions/roles/assign', headers=A, json={'user_id': u.id, 'role_id': role['id']})
ck('requests gone from the bell once the role disallows them', 'request' not in kinds(P), kinds(P))
s3 = c.get('/notifications/settings', headers=P).json()
ck('and shown as not allowed in his settings', not next(g for g in s3['groups'] if g['id'] == 'requests')['allowed'])
ck('a role never set keeps everything (old roles unchanged)', c.post('/permissions/roles', headers=A, json={'name': 'Old', 'tabs': ['store.store.home']}).json()['notif'] is None)
ck('admin sees everything', 'purchase' in kinds(A) and 'request' in kinds(A), kinds(A))
print('\nALL PASS' if not FAIL else f'\n{len(FAIL)} FAILED: {FAIL}')

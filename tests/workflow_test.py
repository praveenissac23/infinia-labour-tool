"""The whole material workflow, walked as office, site and keeper.

Run: cd app && DATABASE_URL=sqlite:////tmp/wf.db python3 ../tests/workflow_test.py

Covers the path a real request takes: raised by site, ordered per
material from different traders, delivered separately days apart, and
the stock and chase list that result. Exists because unit-level checks
passed while the screens still contradicted each other.
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
FAIL = []
def ck(l, ok, x=''):
    print(('  PASS ' if ok else '  FAIL ') + l + ('' if ok else f'   [{x}]'))
    if not ok: FAIL.append(l)
def get(rid, h=O): return next(x for x in c.get('/store/requests', headers=h).json() if x['id'] == rid)

i1 = c.post('/store/items', json={'name': 'Steel Rebar 20MM', 'unit': 't'}, headers=K).json()
i2 = c.post('/store/items', json={'name': 'Subcon Cladding', 'unit': 'pcs'}, headers=K).json()

print("STEP 1  site raises a request with two materials")
mr = c.post('/store/requests', json={'site': '910', 'requested_by': 'febiyan', 'needed_by': '2026-09-01',
    'urgency': 'normal', 'notes': '', 'lines': [
      {'item_id': i1['id'], 'qty_requested': 10, 'unit': 't', 'purpose': 'slab', 'item_type': 'consumable', 'description': '', 'est_cost': 0, 'notes': ''},
      {'item_id': i2['id'], 'qty_requested': 10, 'unit': 'pcs', 'purpose': 'slab', 'item_type': 'consumable', 'description': '', 'est_cost': 0, 'notes': ''}]}, headers=S).json()
L = [l['id'] for l in mr['lines']]
ck('request waiting on office', mr['status'] == 'pending', mr['status'])
ck('both materials waiting', [l['status'] for l in mr['lines']] == ['pending', 'pending'])
ck('office is notified', any('New material request' in n['title'] for n in c.get('/notifications', headers=O).json()['notifications']))

print("STEP 2  office orders material 2 from Newstar without approving first")
c.post(f"/store/requests/{mr['id']}/status", json={'status': 'ordered', 'supplier': 'Newstar',
    'contact_person': 'ajay', 'phone': '0509080202', 'line_ids': [L[1]]}, headers=O)
cur = get(mr['id']); l2 = cur['lines'][1]
ck('ordering approves the material', l2['status'] == 'approved', l2['status'])
ck('ordered material has its supplier', (l2['supplier'] or {}).get('name') == 'Newstar')
ck('the other material is untouched', cur['lines'][0]['status'] == 'pending')
ck('an ordered material cannot be rejected',
   c.post(f"/store/request-lines/{L[1]}/decision", json={'decision': 'rejected', 'reason': 'x'}, headers=O).status_code == 400)

print("STEP 3  office approves material 1, then orders it from Al Raha")
c.post(f"/store/request-lines/{L[0]}/decision", json={'decision': 'approved'}, headers=O)
c.post(f"/store/requests/{mr['id']}/status", json={'status': 'ordered', 'supplier': 'Al Raha',
    'phone': '050090890', 'contact_person': 'bijuam', 'line_ids': [L[0]]}, headers=O)
cur = get(mr['id'])
ck('both materials on order from their own traders',
   [(l['supplier'] or {}).get('name') for l in cur['lines']] == ['Al Raha', 'Newstar'])
ck('request reads as ordered', cur['status'] == 'ordered', cur['status'])

print("STEP 4  site sees the follow-up picture")
sn = c.get('/notifications', headers=S).json()['notifications']
ck('site told it was ordered, with the supplier',
   any('ordered' in n['title'] and ('Al Raha' in n['detail'] or 'Newstar' in n['detail']) for n in sn))

print("STEP 5  Al Raha delivers only its material")
r = c.post(f"/store/requests/{mr['id']}/receive-bulk", json={'supplier': 'Al Raha', 'reference': 'DO-1',
    'notes': '', 'received_on': None, 'lines': [{'line_id': L[0], 'qty': 10}]}, headers=K)
ck('delivery accepted', r.status_code == 200, r.text[:90])
cur = get(mr['id'])
ck('only that material is marked arrived', cur['lines'][0]['qty_received'] == 10 and cur['lines'][1]['qty_received'] == 0)
ck('request is part delivered', cur['status'] == 'partial', cur['status'])
mv = {m['item_code']: m['supplier'] for m in c.get('/store/movements?limit=5', headers=K).json() if m['kind'] == 'in'}
ck('stock recorded against Al Raha', mv.get(i1['code']) == 'Al Raha', str(mv))

print("STEP 6  Newstar delivers days later")
c.post(f"/store/requests/{mr['id']}/receive-bulk", json={'supplier': 'Newstar', 'reference': 'DO-2',
    'notes': '', 'received_on': None, 'lines': [{'line_id': L[1], 'qty': 10}]}, headers=K)
cur = get(mr['id'])
ck('request finishes itself', cur['status'] in ('delivered', 'received'), cur['status'])
mv = {m['item_code']: m['supplier'] for m in c.get('/store/movements?limit=5', headers=K).json() if m['kind'] == 'in'}
ck('each material kept its own trader', mv.get(i1['code']) == 'Al Raha' and mv.get(i2['code']) == 'Newstar')
st = {s['code']: s for s in c.get('/store/stock', headers=K).json()}
ck('stock is right', st[i1['code']]['central'] == 10 and st[i2['code']]['central'] == 10)
ck('nothing left on the chase list', not [1 for x in c.get('/store/requests', headers=S).json()
     for l in x['lines'] if x['status'] not in ('delivered', 'received', 'closed', 'rejected')
     and (l['qty_requested'] - l['qty_received']) > 0])

print()
print('FAILURES:' if FAIL else 'WORKFLOW CLEAN', FAIL if FAIL else '')
sys.exit(1 if FAIL else 0)

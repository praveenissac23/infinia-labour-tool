"""An LPO raised from ticked request lines, ordering them under the supplier's own name and unit (site asked
'Black Sand' 6 m3 and 'Aggregate' 3 m3; the LPO orders 'Black Sand 3M3' 2 trips and '3/4 Aggregate 3M3' 1 trip -
MR-0065 / IC/LPO/20260172, 2 Nov 2026). Editing the LPO (a rate, the payment terms) must not send the request back
to 'to order'; a delivery of 1 trip is 3 m3 on the request; the rest arriving closes the request.

Run: cd app && DATABASE_URL=sqlite:////tmp/lon.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/lpo_other_name_test.py
"""
import sys
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main

db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Administrator', role='admin'))
db.add(models.Site(code='915', active=True))
db.commit(); db.close()
c = TestClient(main.app, raise_server_exceptions=False)
H = {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': 'admin', 'password': 'p'}).json()['access_token']}
FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{x}]'))
    if not ok: FAIL.append(l)

sand = c.post('/store/items', json={'name': 'Black Sand', 'unit': 'm3', 'item_type': 'consumable'}, headers=H).json()
agg = c.post('/store/items', json={'name': 'Aggregate', 'unit': 'm3', 'item_type': 'consumable'}, headers=H).json()
mr = c.post('/store/requests', json={'site': '915', 'requested_by': 'Akhil', 'lines': [
    {'item_id': sand['id'], 'description': 'Black Sand', 'qty_requested': 6, 'unit': 'm3', 'purpose': 'FF, GF BLOCK AND LINTEL WORK'},
    {'item_id': agg['id'], 'description': 'Aggregate', 'qty_requested': 3, 'unit': 'm3', 'purpose': 'FF, GF BLOCK AND LINTEL WORK'}]}, headers=H).json()
c.post(f"/store/requests/{mr['id']}/status", json={'status': 'approved'}, headers=H)
pend = [p for p in c.get('/store/purchase/pending', headers=H).json() if p['ref'] == mr['ref']]
ck('approved: both lines wait for an LPO', len(pend) == 2, pend)
ids = [p['line_id'] for p in pend]
body = {'order_date': '2026-11-02', 'supplier_name': 'Srayedin Building Materials', 'project_location': '915',
        'request_line_ids': ids, 'terms': 'Due on Receipt', 'lines': [
            {'description': 'Black Sand 3M3', 'qty': 2, 'unit': 'trips', 'rate': 290, 'tax_pct': 5},
            {'description': '3/4 Aggregate 3M3', 'qty': 1, 'unit': 'trip', 'rate': 350, 'tax_pct': 5}]}
po = c.post('/store/purchase/orders', json=body, headers=H)
ck('LPO raised from the ticked lines', po.status_code == 200, po.text[:300]); po = po.json()
left = lambda: [p for p in c.get('/store/purchase/pending', headers=H).json() if p['ref'] == mr['ref']]
ck('after the LPO: off the waiting list', not left(), left())
for n, change in enumerate([{'rate': 345}, {'terms': 'Net 45'}], 1):
    b = dict(body); b['lines'] = [dict(x) for x in body['lines']]
    if 'rate' in change: b['lines'][1]['rate'] = change['rate']
    else: b['terms'] = change['terms']
    r = c.put(f"/store/purchase/orders/{po['id']}", json=b, headers=H)
    ck(f'edit {n} saved', r.status_code == 200, r.text[:200])
    ck(f'after edit {n}: still off the waiting list (not back to "to order")', not left(), left())
o = c.get(f"/store/purchase/orders/{po['id']}/deliveries", headers=H).json()
lines = {l['description']: l['line_id'] for l in o['lines']}
r = c.post(f"/store/purchase/orders/{po['id']}/deliver", json={'dn_no': 'DN1', 'dn_date': '2026-11-02', 'lines': [{'line_id': lines['Black Sand 3M3'], 'qty': 1}]}, headers=H)
ck('1 trip of black sand booked', r.status_code == 200, r.text[:300])
req = [x for x in c.get('/store/requests', headers=H).json() if x['id'] == mr['id']][0]
got = {l['description']: l['qty_received'] for l in req['lines']}
ck('the request reads 3 of 6 m3 black sand (1 of 2 trips)', abs(got['Black Sand'] - 3) < 1e-6, got)
r = c.post(f"/store/purchase/orders/{po['id']}/deliver", json={'dn_no': 'DN2', 'dn_date': '2026-11-02', 'lines': [
    {'line_id': lines['Black Sand 3M3'], 'qty': 1}, {'line_id': lines['3/4 Aggregate 3M3'], 'qty': 1}]}, headers=H)
ck('the rest booked', r.status_code == 200, r.text[:400])
req = [x for x in c.get('/store/requests', headers=H).json() if x['id'] == mr['id']][0]
got = {l['description']: l['qty_received'] for l in req['lines']}
ck('the rest arrived: 6 m3 sand, 3 m3 aggregate, request delivered', abs(got['Black Sand'] - 6) < 1e-6 and abs(got['Aggregate'] - 3) < 1e-6 and req['status'] == 'delivered', (got, req['status']))
print('\nALL PASS' if not FAIL else f'\n{len(FAIL)} FAILED'); sys.exit(1 if FAIL else 0)

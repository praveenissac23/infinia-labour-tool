"""LPO cancelled (29 Oct 2026): the material request it was raised for moves too - off Approvals and Order
follow-up when the material is no longer needed, or back to waiting to be ordered when it is still needed.
    cd app && DATABASE_URL=sqlite:////tmp/lcr.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/lpo_cancel_request_test.py   (empty db)"""
import sys
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main

db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Administrator', role='admin'))
db.add(models.Site(code='938', active=True)); db.commit(); db.close()
c = TestClient(main.app, raise_server_exceptions=False)
H = {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': 'admin', 'password': 'p'}).json()['access_token']}
FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{str(x)[:300]}]'))
    if not ok: FAIL.append(l)

sand = c.post('/store/items', json={'name': 'Black Sand', 'unit': 'm3', 'item_type': 'consumable'}, headers=H).json()
agg = c.post('/store/items', json={'name': 'Aggregate 20MM', 'unit': 'm3', 'item_type': 'consumable'}, headers=H).json()
def request_and_lpo(sup):
    mr = c.post('/store/requests', json={'site': '938', 'requested_by': 'Site', 'needed_by': '2026-11-02', 'urgency': 'normal', 'notes': '',
        'lines': [{'item_id': sand['id'], 'qty_requested': 9, 'unit': 'm3', 'purpose': ''}, {'item_id': agg['id'], 'qty_requested': 9, 'unit': 'm3', 'purpose': ''}]}, headers=H).json()
    c.post(f"/store/requests/{mr['id']}/status", json={'status': 'approved'}, headers=H)
    full = c.get('/store/requests', headers=H).json(); r = [x for x in full if x['id'] == mr['id']][0]
    ids = [l['id'] for l in r['lines']]
    # raised with its own wording (as the purchaser types it), not the request's
    po = c.post('/store/purchase/orders', json={'supplier_name': sup, 'order_date': '2026-10-28', 'request_line_ids': ids,
        'lines': [{'description': 'Black Sand 3M3', 'qty': 3, 'unit': 'load', 'rate': 300, 'tax_pct': 5},
                  {'description': '3/4 Aggregate 3m3', 'qty': 3, 'unit': 'load', 'rate': 320, 'tax_pct': 5}]}, headers=H).json()
    return mr, po
req = lambda mid: [x for x in c.get('/store/requests', headers=H).json() if x['id'] == mid][0]

mr, po = request_and_lpo('Al Hamd Sand Suppliers')
ck('the request is ordered', req(mr['id'])['status'] == 'ordered', req(mr['id'])['status'])
r = c.post(f"/store/purchase/orders/{po['id']}/cancel", json={'reason': 'Site says material no longer needed', 'not_needed': True}, headers=H)
ck('cancelled: no longer needed', r.status_code == 200 and r.json()['freed'] == 2, r.text)
x = req(mr['id'])
ck('the request is closed, not "ordered" (off Approvals and Order follow-up)', x['status'] == 'closed', x['status'])
ck('each material says why', all(l['status'] == 'rejected' and 'no longer needed' in (l.get('reject_reason') or '') for l in x['lines']), x['lines'])
ck('and nothing is left with a supplier to arrive', all(not l.get('supplier') and not l.get('supplier_id') for l in x['lines']) and not x.get('supplier'), x)

mr2, po2 = request_and_lpo('Al Hamd Sand Suppliers')
r = c.post(f"/store/purchase/orders/{po2['id']}/cancel", json={'reason': 'Supplier cannot supply', 'not_needed': False}, headers=H)
x = req(mr2['id'])
ck('still needed: back to waiting to be ordered', x['status'] == 'approved' and all((l['status'] or '') == 'approved' and not l.get('supplier_id') for l in x['lines']), (x['status'], x['lines']))

# the LPO cancelled this morning before the link was kept: put right once at start
mr3, po3 = request_and_lpo('Al Hamd Sand Suppliers')
db = database.SessionLocal()
o = db.get(models.PurchaseOrder, po3['id']); o.ref = 'IC/LPO/20260153'; o.request_line_ids = ''; o.status = 'cancelled'; o.cancel_reason = 'Site says material no longer needed'
m = db.get(models.MaterialRequest, mr3['id']); m.ref = 'MR-0038'; db.commit()
main._fix_lpo_0153(db); main._fix_lpo_0153(db)
db.close()
x = req(mr3['id'])
ck('IC/LPO/20260153: MR-0038 closed, its materials not needed', x['status'] == 'closed' and all(l['status'] == 'rejected' for l in x['lines']), (x['status'], x['lines']))
print(f"{len(FAIL)} FAILED" if FAIL else 'ALL PASS')

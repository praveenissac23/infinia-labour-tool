"""Two store keeper asks (28 Oct 2026):
 1. A request sent with a mistake can be corrected, or deleted and sent again - by the keeper who sent it,
    while the office has not acted on it. Once approved / ordered / on an LPO it is the office's to change.
 2. Rentals: 50 ledgers taken on the 1st and 10 more a week later are two deliveries, each with its own
    date and days on rent - and what goes back is taken off the oldest first.
    cd app && DATABASE_URL=sqlite:////tmp/rq.db python3 ../tests/request_edit_rent_batches_test.py   (empty db)"""
import sys
sys.path.insert(0, '.')
from datetime import timedelta
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main

db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Administrator', role='admin'))
db.add(models.User(username='amal', hashed_password=auth.hash_password('p'), full_name='Amal', role='office', permissions='requests,store'))
db.add(models.User(username='keeper2', hashed_password=auth.hash_password('p'), full_name='Keeper Two', role='office', permissions='requests,store'))
db.add(models.Site(code='901', active=True))
db.commit(); db.close()

c = TestClient(main.app, raise_server_exceptions=False)
tok = lambda u: {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': u, 'password': 'p'}).json()['access_token']}
H, AMAL, K2 = tok('admin'), tok('amal'), tok('keeper2')
FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{str(x)[:220]}]'))
    if not ok: FAIL.append(l)

cement = c.post('/store/items', json={'name': 'Cement OPC 50kg', 'unit': 'bag', 'item_type': 'consumable'}, headers=H).json()
sand = c.post('/store/items', json={'name': 'Sand', 'unit': 'm3', 'item_type': 'consumable'}, headers=H).json()

# ---- 1. correct or delete a request ---------------------------------------------------------------
body = {'site': '901', 'requested_by': 'Amal', 'needed_by': '2026-11-02', 'urgency': 'normal', 'notes': '',
        'lines': [{'item_id': cement['id'], 'qty_requested': 500, 'unit': 'bag', 'purpose': 'slab'}]}
mr = c.post('/store/requests', json=body, headers=AMAL).json()
ck('the keeper sends a request (500 bags - meant 50)', mr.get('ref'), mr)
mine = [r for r in c.get('/store/requests', headers=AMAL).json() if r['id'] == mr['id']][0]
ck('he may correct it (not yet taken up)', mine['can_edit'] and mine['mine'], mine)
other = [r for r in c.get('/store/requests', headers=K2).json() if r['id'] == mr['id']][0]
ck('another keeper may not', not other['can_edit'], other)
fix = dict(body, lines=[{'item_id': cement['id'], 'qty_requested': 50, 'unit': 'bag', 'purpose': 'slab'},
                        {'item_id': sand['id'], 'qty_requested': 4, 'unit': 'm3', 'purpose': 'slab'}])
r = c.put(f"/store/requests/{mr['id']}", json=fix, headers=AMAL)
ck('he corrects it: 50 bags and the sand he missed', r.status_code == 200, r.text)
r = r.json()
ck('same number', r['ref'] == mr['ref'], r['ref'])
ck('the office sees the corrected list', sorted((l['item_name'], l['qty_requested']) for l in r['lines']) == [('Cement OPC 50kg', 50), ('Sand', 4)], r['lines'])
ck('another keeper cannot change it', c.put(f"/store/requests/{mr['id']}", json=body, headers=K2).status_code == 403)
ck('nor delete it', c.delete(f"/store/requests/{mr['id']}", headers=K2).status_code == 403)
# once the office approves, it is theirs
c.post(f"/store/requests/{mr['id']}/status", json={'status': 'approved'}, headers=H)
r = c.put(f"/store/requests/{mr['id']}", json=body, headers=AMAL)
ck('approved: the keeper can no longer change it', r.status_code == 400 and 'office' in r.text, r.text)
ck('nor delete it', c.delete(f"/store/requests/{mr['id']}", headers=AMAL).status_code == 400)
ck('and it shows as not editable', not [x for x in c.get('/store/requests', headers=AMAL).json() if x['id'] == mr['id']][0]['can_edit'])
# delete and send again
mr2 = c.post('/store/requests', json=dict(body, lines=[{'item_id': sand['id'], 'qty_requested': 9, 'unit': 'm3', 'purpose': 'x'}]), headers=AMAL).json()
ck('a wrong request can be deleted by its keeper', c.delete(f"/store/requests/{mr2['id']}", headers=AMAL).status_code == 200)
ck('and it is gone', not [x for x in c.get('/store/requests', headers=AMAL).json() if x['id'] == mr2['id']])
ck('the office can still delete any request', c.delete(f"/store/requests/{mr['id']}", headers=H).status_code == 200)

# ---- 2. rentals: each delivery its own date and days ------------------------------------------------
today = main._dubai_today()
d1, d2 = today - timedelta(days=27), today - timedelta(days=20)
ldg = c.post('/store/items', json={'name': 'Ledger 2.0M', 'unit': 'pcs', 'item_type': 'rental', 'rental_supplier': 'Al Raha Scaffolding'}, headers=H).json()
for d, q in ((d1, 50), (d2, 10)):
    rr = c.post('/store/hire/in', json={'supplier_name': 'Al Raha Scaffolding', 'received_on': d.isoformat(), 'reference': f'DN-{q}',
                                        'lines': [{'item_id': ldg['id'], 'qty': q}]}, headers=H)
    ck(f'{q} ledgers hired in on {d}', rr.status_code == 200, rr.text)
g = c.get('/store/hire', headers=H).json()
item = [i for s in g['suppliers'] for i in s['items'] if i['item_id'] == ldg['id']][0]
ck('60 on rent', item['qty'] == 60, item)
ck('as two deliveries, each its own date and days',
   [(b['since'], b['qty'], b['days']) for b in item['batches']] == [(d1.isoformat(), 50, 27), (d2.isoformat(), 10, 20)], item['batches'])
rep = c.get('/store/report?kind=hired', headers=H).json()['rows']
mine = [x for x in rep if x['name'] == 'Ledger 2.0M']
ck('the On Rent Now report: a line per delivery', [(x['on_hire'], x['days_out']) for x in mine] == [(50, 27), (10, 20)], mine)
sid = item['supplier_id']
note = c.post('/store/returns', json={'supplier_id': sid, 'return_date': today.isoformat(),
                                      'lines': [{'item_id': ldg['id'], 'qty_returned': 20}]}, headers=H)
ck('20 go back', note.status_code == 200, note.text)
nid = note.json()['id']
c.post(f"/store/returns/{nid}/issue", headers=H)
cf = c.post(f"/store/returns/{nid}/confirm", json={'confirmed_on': today.isoformat()}, headers=H)
ck('the signed note is confirmed', cf.status_code == 200, cf.text)
item = [i for s in c.get('/store/hire', headers=H).json()['suppliers'] for i in s['items'] if i['item_id'] == ldg['id']]
item = item[0] if item else {}
ck('taken off the oldest delivery first: 30 of the first, the 10 untouched',
   [(b['qty'], b['days']) for b in item.get('batches', [])] == [(30, 27), (10, 20)], item.get('batches'))
print(f"{len(FAIL)} FAILED" if FAIL else 'ALL PASS')

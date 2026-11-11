"""Already on an LPO (11 Nov 2026): request lines ordered on an LPO raised by hand under the supplier's own names
(MR-0109's pipes on IC/LPO/20260199) are put on that LPO - they leave 'waiting for LPO', the request is ordered,
and the 'Ordered direct' request the LPO made for the same pipes is taken off.
    cd app && DATABASE_URL=sqlite:////tmp/lll.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/lpo_link_lines_test.py   (empty db)"""
import sys
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main

db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Administrator', role='admin'))
db.add(models.Site(code='914', active=True)); db.add(models.Site(code='925', active=True)); db.commit(); db.close()
c = TestClient(main.app, raise_server_exceptions=False)
H = {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': 'admin', 'password': 'p'}).json()['access_token']}
FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{str(x)[:400]}]'))
    if not ok: FAIL.append(l)
it = lambda n: c.post('/store/items', json={'name': n, 'unit': 'pcs', 'item_type': 'consumable'}, headers=H).json()
p2, p3, wc = it('2" U PVC CLASS E PIPE'), it('3" PVC PIPE 4 MTR'), it('Indian Closet')
def mr(site, lines):
    m = c.post('/store/requests', json={'site': site, 'requested_by': 'Premraj', 'needed_by': '2026-11-11', 'urgency': 'normal', 'notes': '',
        'lines': [{'item_id': i['id'], 'qty_requested': q, 'unit': 'pcs', 'purpose': 'PUMP ROOM WORK'} for i, q in lines]}, headers=H).json()
    c.post(f"/store/requests/{m['id']}/status", json={'status': 'approved'}, headers=H)
    return [x for x in c.get('/store/requests', headers=H).json() if x['id'] == m['id']][0]
m109 = mr('914', [(p2, 2), (p3, 1)]); m108 = mr('925', [(wc, 1)])
po = c.post('/store/purchase/orders', json={'supplier_name': 'Al Raha Building Materials', 'order_date': '2026-11-10', 'project_location': '925',
    'request_line_ids': [m108['lines'][0]['id']],
    'lines': [{'description': 'WC Arabic Type Kit', 'qty': 1, 'unit': 'pcs', 'rate': 55, 'tax_pct': 5},
              {'description': 'PVC Pipe 2"X 6mtr Grey H/P Cosmoplast', 'qty': 2, 'unit': 'pcs', 'rate': 89, 'tax_pct': 5, 'cost_to': '914'},
              {'description': 'UPVC Pipe 3" X 6mtr Red Cosmoplast', 'qty': 1, 'unit': 'pcs', 'rate': 80, 'tax_pct': 5, 'cost_to': '914'}]}, headers=H)
ck('LPO raised', po.status_code == 200, po.text); po = po.json()
pend = lambda: {p['line_id'] for p in c.get('/store/purchase/pending', headers=H).json()}
ids109 = [l['id'] for l in m109['lines']]
ck('before: MR-0109 pipes still waiting for an LPO', set(ids109) <= pend(), pend())
direct = lambda: [x for x in c.get('/store/requests', headers=H).json() if 'Ordered direct' in (x.get('notes') or '') and x['status'] != 'closed']
ck('before: the LPO made its own "Ordered direct" request for the pipes', any(any('Cosmoplast' in (l.get('description') or '') for l in x['lines']) for x in direct()), direct())
full = c.get(f"/store/purchase/orders/{po['id']}", headers=H).json()
pl = {l['description']: l['id'] for l in full['lines']}
r = c.post('/store/purchase/link-lines', json={'order_id': po['id'], 'links': [
    {'line_id': ids109[0], 'lpo_line_id': pl['PVC Pipe 2"X 6mtr Grey H/P Cosmoplast']},
    {'line_id': ids109[1], 'lpo_line_id': pl['UPVC Pipe 3" X 6mtr Red Cosmoplast']}]}, headers=H)
ck('put on the LPO', r.status_code == 200 and r.json()['linked'] == 2, r.text)
ck('they leave the waiting list', not (set(ids109) & pend()), pend())
x = [x for x in c.get('/store/requests', headers=H).json() if x['id'] == m109['id']][0]
ck('MR-0109 is ordered, from that supplier', x['status'] == 'ordered' and all(l.get('supplier_id') or l.get('supplier') for l in x['lines']), x)
ck('each line says what was asked and what it was ordered as', all("Asked as" in (l.get('notes') or '') for l in x['lines']), [l.get('notes') for l in x['lines']])
ck('the "Ordered direct" request for the pipes is gone', not any(any('Cosmoplast' in (l.get('description') or '') for l in d['lines']) for d in direct()), direct())
ck('the WC (own request line) is untouched', any(l['id'] == m108['lines'][0]['id'] for l in [l for x in c.get('/store/requests', headers=H).json() if x['id'] == m108['id'] for l in x['lines']]))
r = c.post('/store/purchase/link-lines', json={'order_id': po['id'], 'links': [{'line_id': ids109[0], 'lpo_line_id': pl['PVC Pipe 2"X 6mtr Grey H/P Cosmoplast']}]}, headers=H)
ck('twice: refused, already on an LPO', r.status_code == 400, r.text)

# the real fix: ticked, raised, then renamed on an edit - the request stays ordered on the LPO
m2 = mr('914', [(p2, 2), (p3, 1)]); ids2 = [l['id'] for l in m2['lines']]
po2 = c.post('/store/purchase/orders', json={'supplier_name': 'Al Raha Building Materials', 'order_date': '2026-11-10', 'project_location': '914',
    'request_line_ids': ids2, 'lines': [{'item_id': p2['id'], 'description': p2['name'], 'qty': 2, 'unit': 'pcs', 'rate': 0, 'tax_pct': 5},
                                        {'item_id': p3['id'], 'description': p3['name'], 'qty': 1, 'unit': 'pcs', 'rate': 0, 'tax_pct': 5}]}, headers=H).json()
ck('ticked and raised: off the waiting list', not (set(ids2) & pend()), pend())
r = c.put(f"/store/purchase/orders/{po2['id']}", json={'supplier_name': 'Al Raha Building Materials', 'order_date': '2026-11-10', 'project_location': '914',
    'lines': [{'description': 'PVC Pipe 2"X 6mtr Grey H/P Cosmoplast', 'qty': 2, 'unit': 'pcs', 'rate': 89, 'tax_pct': 5},
              {'description': 'UPVC Pipe 3" X 6mtr Red Cosmoplast', 'qty': 1, 'unit': 'pcs', 'rate': 80, 'tax_pct': 5}]}, headers=H)
ck('renamed completely on an edit', r.status_code == 200, r.text)
ck('still off the waiting list', not (set(ids2) & pend()), pend())
x = [x for x in c.get('/store/requests', headers=H).json() if x['id'] == m2['id']][0]
ck('the request stays ordered, its lines now the renamed materials', x['status'] == 'ordered' and sorted(l['description'] for l in x['lines']) == ['PVC Pipe 2"X 6mtr Grey H/P Cosmoplast', 'UPVC Pipe 3" X 6mtr Red Cosmoplast'], x)
d2 = [d for d in direct() if d.get('lpo_id') == po2['id'] or any(po2['ref'] in (d.get('notes') or '') for _ in [0])]
ck('no "Ordered direct" request made for the renamed pipes', not d2, d2)
r = c.put(f"/store/purchase/orders/{po2['id']}", json={'supplier_name': 'Al Raha Building Materials', 'order_date': '2026-11-10', 'project_location': '914',
    'lines': [{'description': 'PVC Pipe 2"X 6mtr Grey H/P Cosmoplast', 'qty': 2, 'unit': 'pcs', 'rate': 89, 'tax_pct': 5}]}, headers=H)
ck('a line really taken off goes back to waiting', ids2[1] in pend() and ids2[0] not in pend(), pend())
# the live case, put right once at start: ticked, raised, renamed on an edit before this fix
m3 = mr('914', [(p2, 2), (p3, 1)]); ids3 = [l['id'] for l in m3['lines']]
po3 = c.post('/store/purchase/orders', json={'supplier_name': 'Al Raha Building Materials', 'order_date': '2026-11-10', 'project_location': '925,914', 'combined': True,
    'request_line_ids': [], 'lines': [{'description': 'WC Arabic Type Kit', 'qty': 1, 'unit': 'pcs', 'rate': 55, 'tax_pct': 5, 'cost_to': '925'},
        {'description': 'PVC Pipe 2"X 6mtr Grey H/P Cosmoplast', 'qty': 2, 'unit': 'pcs', 'rate': 89, 'tax_pct': 5, 'cost_to': '914'},
        {'description': 'UPVC Pipe 3" X 6mtr Red Cosmoplast', 'qty': 1, 'unit': 'pcs', 'rate': 80, 'tax_pct': 5, 'cost_to': '914'}]}, headers=H).json()
db = database.SessionLocal()
db.get(models.PurchaseOrder, po3['id']).ref = 'IC/LPO/20260199'; db.get(models.MaterialRequest, m3['id']).ref = 'MR-0109'; db.commit()
ck('replica: MR-0109 waiting, LPO made its own request for the pipes', set(ids3) <= pend() and any(any('Cosmoplast' in (l.description or '') for l in r.lines) for r in main._lpo_tracked_requests(db, db.get(models.PurchaseOrder, po3['id'])) if r.site == '914' and r.status != 'closed'))
main._fix_lpo_0199(db); main._fix_lpo_0199(db); db.close()
ck('put right: MR-0109 off the waiting list', not (set(ids3) & pend()), pend())
db = database.SessionLocal()
ck('and the LPO has no own request left for the pipes', not any(r.site == '914' and r.status != 'closed' for r in main._lpo_tracked_requests(db, db.get(models.PurchaseOrder, po3['id']))))
ck('the WC request it made is still there', any(r.site == '925' and r.status != 'closed' for r in main._lpo_tracked_requests(db, db.get(models.PurchaseOrder, po3['id']))))
db.close()
print(f"{len(FAIL)} FAILED" if FAIL else 'ALL PASS')

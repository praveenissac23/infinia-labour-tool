"""One material of a request not needed (MR-0061: the solid blocks wanted, the hollow ones not): only that line is
taken off, with the reason; part arrived - it asks for what came; still on a live LPO - refused (change the LPO).

Run: cd app && DATABASE_URL=sqlite:////tmp/rln.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/request_line_not_needed_test.py
"""
import sys
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main
db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Administrator', role='admin'))
db.add(models.Site(code='102', active=True)); db.commit(); db.close()
c = TestClient(main.app, raise_server_exceptions=False)
H = {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': 'admin', 'password': 'p'}).json()['access_token']}
FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{x}]'))
    if not ok: FAIL.append(l)
it = lambda n, u: c.post('/store/items', json={'name': n, 'unit': u, 'item_type': 'consumable'}, headers=H).json()
solid, hollow, cem = it('Solid Block 8 Inch', 'pcs'), it('Hollow Block 4 Inch', 'pcs'), it('Cement 50KG', 'bag')
mr = c.post('/store/requests', json={'site': '102', 'requested_by': 'Premraj', 'lines': [
    {'item_id': solid['id'], 'description': 'Solid Block 8 Inch', 'qty_requested': 650, 'unit': 'pcs'},
    {'item_id': hollow['id'], 'description': 'Hollow Block 4 Inch', 'qty_requested': 80, 'unit': 'pcs'},
    {'item_id': cem['id'], 'description': 'Cement 50KG', 'qty_requested': 20, 'unit': 'bag'}]}, headers=H).json()
c.post(f"/store/requests/{mr['id']}/status", json={'status': 'approved'}, headers=H)
L = {l['description']: l['id'] for l in mr['lines']}
r = c.post(f"/store/request-lines/{L['Hollow Block 4 Inch']}/not-needed", json={'reason': ''}, headers=H)
ck('a reason is required', r.status_code == 400, r.text)
r = c.post(f"/store/request-lines/{L['Hollow Block 4 Inch']}/not-needed", json={'reason': 'Site wants only solid blocks'}, headers=H)
ck('hollow block not needed', r.status_code == 200, r.text[:200])
d = c.get(f"/store/purchase/tracker/request/{mr['id']}", headers=H).json()
st = {l['description']: (l['status'], l['reject_reason']) for l in d['lines']}
ck('only the hollow block is off, with the reason; solid blocks and cement still approved',
   st['Hollow Block 4 Inch'] == ('rejected', 'Not needed: Site wants only solid blocks') and st['Solid Block 8 Inch'][0] == 'approved'
   and st['Cement 50KG'][0] == 'approved' and d['status'] == 'approved', (st, d['status']))
pend = [p['description'] for p in c.get('/store/purchase/pending', headers=H).json() if p['ref'] == mr['ref']]
ck('the LPO waiting list has the solid blocks and cement, not the hollow blocks', sorted(pend) == ['Cement 50KG', 'Solid Block 8 Inch'], pend)
po = c.post('/store/purchase/orders', json={'order_date': '2026-11-02', 'supplier_name': 'Unimix Block Industry', 'project_location': '102',
     'request_line_ids': [L['Solid Block 8 Inch']], 'lines': [{'item_id': solid['id'], 'description': 'Solid Block 8 Inch', 'qty': 650, 'unit': 'pcs', 'rate': 3, 'tax_pct': 5}]}, headers=H).json()
r = c.post(f"/store/request-lines/{L['Solid Block 8 Inch']}/not-needed", json={'reason': 'test'}, headers=H)
ck('a material still on a live LPO: refused - change the LPO', r.status_code == 400 and 'change the LPO' in r.text, r.text[:200])
# cement bought with petty cash: 5 of 20 came on the request, the rest not needed
db = database.SessionLocal(); x = db.get(models.MaterialRequestLine, L['Cement 50KG']); x.qty_received = 5; db.commit(); db.close()   # 5 came (petty cash)
r = c.post(f"/store/request-lines/{L['Cement 50KG']}/not-needed", json={'reason': 'Enough came'}, headers=H)
d = c.get(f"/store/purchase/tracker/request/{mr['id']}", headers=H).json()
ce = [l for l in d['lines'] if l['description'] == 'Cement 50KG'][0]
ck('part came: the line now asks for what came (5), the rest closed with the reason', ce['qty_requested'] == ce['qty_received'] and ce['status'] == 'approved' and 'rest not needed: Enough came' in (ce['notes'] or ''), (ce['qty_requested'], ce['qty_received'], ce['notes']))
print('\nALL PASS' if not FAIL else f'\n{len(FAIL)} FAILED'); sys.exit(1 if FAIL else 0)

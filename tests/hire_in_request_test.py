"""Hired material booked in on Rentals reaches the request it was ordered on (29 Oct 2026): the scaffolding on
IC/LPO/20260148 / 150 was booked in at 913 and 919, but MR-0036 / MR-0037 still showed 'to arrive' on Order follow-up.
    cd app && DATABASE_URL=sqlite:////tmp/hr.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/hire_in_request_test.py   (empty db)"""
import sys
sys.path.insert(0, '.')
from datetime import date
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main

db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Administrator', role='admin'))
for s in ('913', '919'): db.add(models.Site(code=s, active=True))
db.commit(); db.close()
c = TestClient(main.app, raise_server_exceptions=False)
H = {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': 'admin', 'password': 'p'}).json()['access_token']}
FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{str(x)[:400]}]'))
    if not ok: FAIL.append(l)
item = lambda n, t='asset': c.post('/store/items', json={'name': n, 'unit': 'nos', 'item_type': t}, headers=H).json()
SUP = 'Desarch Building Contracting L.l.c'
# what purchasing ordered (store items) ...
ordered = {n: item(n) for n in ['Ledger 1.2m', 'Ledger 0.9m', 'Aluminium Beam 1.5m', 'Aluminium Beam 3.5m', 'Standard 2.0m',
                                'Adjustable Base/base jack', 'M.D Props 3.20 to 5.0m', 'Bracing Tube 4.0m']}
def lpo(lines):
    po = c.post('/store/purchase/orders', json={'supplier_name': SUP, 'order_date': '2026-10-24',
        'lines': [{'item_id': ordered[n]['id'], 'description': n, 'qty': q, 'unit': 'nos', 'rate': 1, 'tax_pct': 5} for n, q in lines]}, headers=H).json()
    return po
p1 = lpo([('Ledger 1.2m', 85), ('Ledger 0.9m', 80), ('Aluminium Beam 1.5m', 30), ('Aluminium Beam 3.5m', 145)])     # -> store request A
p2 = lpo([('Ledger 0.9m', 70), ('Standard 2.0m', 50), ('Adjustable Base/base jack', 20), ('M.D Props 3.20 to 5.0m', 100), ('Bracing Tube 4.0m', 125)])  # -> B
reqs = lambda: {r['id']: r for r in c.get('/store/requests', headers=H).json()}
A = next(r for r in reqs().values() if 'Ledger 1.2m' in [l['description'] for l in r['lines']])
B = next(r for r in reqs().values() if 'Standard 2.0m' in [l['description'] for l in r['lines']])
ck('two store orders waiting', A['status'] == 'ordered' and B['status'] == 'ordered', (A['status'], B['status']))
# ... and what the keeper booked in on Rentals (the hire company's own names), at the sites
rent = {n: item('Rental ' + n) for n in ['Ledger 0.9M', 'Standard 2.0M', 'ADJ Base Jack', 'Prop 5.0M', 'Tube 4.0M', 'Ledger 1.2M', 'Aluminium Beam 3.5m']}
r = c.post('/store/hire/in', json={'supplier_name': SUP, 'received_on': '2026-10-26', 'location': '913', 'reference': '402370',
    'lines': [{'item_id': rent[n]['id'], 'qty': q} for n, q in [('Ledger 0.9M', 70), ('Standard 2.0M', 50), ('ADJ Base Jack', 20), ('Prop 5.0M', 99), ('Tube 4.0M', 125)]]}, headers=H)
ck('delivery note 402370 booked in at 913', r.status_code == 200, r.text)
ck('and received on its request', r.json()['requests'] == [B['ref']], r.json())
b = reqs()[B['id']]
got = {l['description']: l['qty_received'] for l in b['lines']}
ck('ledger 0.9 (70), standard, base jack, bracing tube received - on B, not A', got == {'Ledger 0.9m': 70, 'Standard 2.0m': 50, 'Adjustable Base/base jack': 20, 'M.D Props 3.20 to 5.0m': 0, 'Bracing Tube 4.0m': 125}, got)
ck('B part delivered (the props are not the same size)', b['status'] == 'partial', b['status'])
ck('A untouched', all(l['qty_received'] == 0 for l in reqs()[A['id']]['lines']))
# one already in before this: matched once at start
db = database.SessionLocal()
for n, q in [('Ledger 1.2M', 85), ('Ledger 0.9M', 80), ('Aluminium Beam 3.5m', 145)]:
    db.add(models.StoreMovement(item_id=rent[n]['id'], kind='in', qty=q, location='919', owner_id=db.query(models.Supplier).filter_by(name=SUP).first().id,
                                supplier=SUP, reference='402422', moved_on=date(2026, 10, 27)))
db.commit()
main._hire_in_to_requests_once(db); main._hire_in_to_requests_once(db)
db.close()
a = reqs()[A['id']]
got = {l['description']: l['qty_received'] for l in a['lines']}
ck('earlier hire-ins put on A once: all but the 1.5m beams', got == {'Ledger 1.2m': 85, 'Ledger 0.9m': 80, 'Aluminium Beam 1.5m': 0, 'Aluminium Beam 3.5m': 145}, got)
# a material on both orders, its delivery note matching one of each: goes to the order already arriving at that site
db = database.SessionLocal()
cf = item('Cantilever Frame 1.5m'); rcf = item('Rental Cantilever Frame 1.5M')
for mr_, q in ((A, 65), (B, 40)):
    m_ = db.get(models.MaterialRequest, mr_['id']); m_.status = 'ordered'
    db.add(models.MaterialRequestLine(request_id=mr_['id'], item_id=cf['id'], description='Cantilever Frame 1.5m', qty_requested=q, qty_approved=q,
                                      unit='nos', status='approved', supplier_id=db.query(models.Supplier).filter_by(name=SUP).first().id))
db.commit(); db.close()
c.post('/store/hire/in', json={'supplier_name': SUP, 'received_on': '2026-10-27', 'location': '913', 'reference': '402408',
       'lines': [{'item_id': rcf['id'], 'qty': 40}]}, headers=H)
ck('cantilever 40 at 913 goes to B (already arriving at 913, 40 asked), not the older A',
   next(l for l in reqs()[B['id']]['lines'] if l['description'].startswith('Cantilever'))['qty_received'] == 40 and
   next(l for l in reqs()[A['id']]['lines'] if l['description'].startswith('Cantilever'))['qty_received'] == 0)
# the props came another way: marked by hand, no stock added
props = next(l for l in reqs()[B['id']]['lines'] if l['description'].startswith('M.D'))
n0 = len(c.get('/store/movements', headers=H).json()) if c.get('/store/movements', headers=H).status_code == 200 else None
r = c.post(f"/store/requests/{B['id']}/lines/{props['id']}/arrived", json={}, headers=H)
b = reqs()[B['id']]
ck('Already booked in: the props off the list, B delivered', r.status_code == 200 and b['status'] == 'delivered', (r.text, b['status']))
print(f"{len(FAIL)} FAILED" if FAIL else 'ALL PASS')

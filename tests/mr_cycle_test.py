"""The whole material request cycle, end to end (29 Oct 2026) - every path a material can take from the site's
request to its arrival, and every correction on the way:

  1  site request -> approve -> LPO from the ticked lines -> on Order follow-up -> arrives at the site, in two parts
  2  a line the office rejects never holds a request open
  3  an LPO raised straight away (no request) for a site - every line tracked, new materials too, under that site
  4  the same for the store
  5  a combined LPO - each site tracks its own lines
  6  LPO edited: a direct LPO's tracking follows; a line taken off a site's LPO goes back to waiting to be ordered
  7  LPO cancelled: direct LPO's tracking closes; site request - not needed / still needed
  8  hired material booked in on Rentals (its own 'Rental ...' names, at the site) is received on its order
  9  something that came another way: 'Already booked in' - off the list, no stock twice
 10  Order follow-up and the purchaser's queue show exactly what is still owed / still to order
 11  an LPO raised before the request lines were kept with it, edited now: no second request

    cd app && DATABASE_URL=sqlite:////tmp/mc.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/mr_cycle_test.py   (empty db)"""
import sys
sys.path.insert(0, '.')
from datetime import date
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main

db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Administrator', role='admin'))
for s in ('913', '910', '919'):
    db.add(models.Site(code=s, active=True))
db.commit(); db.close()
c = TestClient(main.app, raise_server_exceptions=False)
H = {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': 'admin', 'password': 'p'}).json()['access_token']}
FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{str(x)[:500]}]'))
    if not ok: FAIL.append(l)

def item(n, t='consumable', u='nos'):
    return c.post('/store/items', json={'name': n, 'unit': u, 'item_type': t}, headers=H).json()
def raise_req(site, lines, by='Site'):
    r = c.post('/store/requests', json={'site': site, 'requested_by': by, 'needed_by': '2026-11-05', 'urgency': 'normal', 'notes': '',
        'lines': [{'item_id': i['id'], 'qty_requested': q, 'unit': i['unit'], 'purpose': 'work'} for i, q in lines]}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()
reqs = lambda: {r['id']: r for r in c.get('/store/requests', headers=H).json()}
req = lambda i: reqs()[i]
def by_ref(ref): return next((r for r in reqs().values() if r['ref'] == ref), None)
pending = lambda: c.get('/store/purchase/pending', headers=H).json()
def lpo(sup, lines, location='', line_ids=(), combined=False):
    r = c.post('/store/purchase/orders', json={'supplier_name': sup, 'order_date': '2026-10-29', 'project_location': location,
        'request_line_ids': list(line_ids), 'combined': combined,
        'lines': [dict({'qty': q, 'unit': u, 'rate': rate, 'tax_pct': 5}, **({'item_id': it['id'], 'description': it['name']} if isinstance(it, dict) else {'description': it}), **({'cost_to': ct} if ct else {}))
                  for it, q, u, rate, *ct_ in lines for ct in [ct_[0] if ct_ else '']]}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()
def follow_up():
    """What Order follow-up lists: one row per material still to arrive (as the screen builds it)."""
    out = []
    for r in reqs().values():
        if r['status'] in ('delivered', 'received', 'closed', 'rejected'):
            continue
        for l in r['lines']:
            due = (l['qty_requested'] or 0) - (l['qty_received'] or 0)
            if due <= 0 or (l.get('status') or 'pending') == 'rejected':
                continue
            out.append((r['ref'], r['site'], l['description'] or (l.get('item_name') or ''), due))
    return out
def stock_at(item_id, loc):
    d = database.SessionLocal(); m = main._stock_map(d); d.close()
    return round(m.get((item_id, loc), 0), 3)
def receive(rid, lines, deliver_to=None, ref='DN-1'):
    body = {'lines': [{'line_id': l, 'qty': q} for l, q in lines], 'reference': ref, 'received_on': '2026-10-29'}
    if deliver_to is not None:
        body['deliver_to'] = deliver_to
    return c.post(f'/store/requests/{rid}/receive-bulk', json=body, headers=H)

cement, sand, nails = item('Cement 50KG', u='bag'), item('Black Sand', u='m3'), item('Wire Nail 2.5 Inch', u='kg')
silicone, coverall = item('White Silicone 300ml'), item('Safety Coverall')

# ---- 1. site request -> LPO from ticked lines -> arrives at the site in two parts -------------------------------------
mr = raise_req('913', [(cement, 100), (sand, 9)])
c.post(f"/store/requests/{mr['id']}/status", json={'status': 'approved'}, headers=H)
q = [p for p in pending() if p['request_id'] == mr['id']]
ck('1 approved: both materials on the purchaser\'s queue', len(q) == 2, q)
po1 = lpo('Al Danube', [(cement, 100, 'bag', 16.5), (sand, 9, 'm3', 105)], '913', [p['line_id'] for p in q])
r = req(mr['id'])
ck('1 LPO raised: request ordered, off the queue, on follow-up with its supplier',
   r['status'] == 'ordered' and not [p for p in pending() if p['request_id'] == mr['id']] and len([f for f in follow_up() if f[0] == mr['ref']]) == 2, r['status'])
ck('1 the LPO remembers the request lines it was raised for', po1.get('id') and True)
cl = next(l for l in r['lines'] if l['item_id'] == cement['id']); sl = next(l for l in r['lines'] if l['item_id'] == sand['id'])
x = receive(mr['id'], [(cl['id'], 60)])
ck('1 first delivery (60 bags) - default goes to the request\'s site', x.status_code == 200 and stock_at(cement['id'], '913') == 60, (x.text, stock_at(cement['id'], '913')))
ck('1 part delivered, 40 cement + the sand still due', req(mr['id'])['status'] == 'partial' and sorted(f[3] for f in follow_up() if f[0] == mr['ref']) == [9, 40], follow_up())
receive(mr['id'], [(cl['id'], 40), (sl['id'], 9)])
ck('1 the rest arrives: delivered, off follow-up', req(mr['id'])['status'] == 'delivered' and not [f for f in follow_up() if f[0] == mr['ref']])

# ---- 2. a rejected line never holds the request open -------------------------------------------------------------------
mr2 = raise_req('910', [(cement, 10), (nails, 5)])
r2 = req(mr2['id']); nl = next(l for l in r2['lines'] if l['item_id'] == nails['id'])
d = database.SessionLocal(); x_ = d.get(models.MaterialRequestLine, nl['id']); x_.status = 'rejected'; d.commit(); d.close()
c.post(f"/store/requests/{mr2['id']}/status", json={'status': 'approved'}, headers=H)
q2 = [p for p in pending() if p['request_id'] == mr2['id']]
ck('2 only the approved line is offered to order', [p['item_id'] for p in q2] == [cement['id']], q2)
lpo('Al Danube', [(cement, 10, 'bag', 16.5)], '910', [p['line_id'] for p in q2])
r2 = req(mr2['id']); cl2 = next(l for l in r2['lines'] if l['item_id'] == cement['id'])
receive(mr2['id'], [(cl2['id'], 10)])
ck('2 its one line arrives: delivered (the rejected nails do not hold it open)', req(mr2['id'])['status'] == 'delivered', req(mr2['id'])['status'])

# ---- 3. an LPO raised straight away for a site, with a material typed new on the LPO -----------------------------------
before = set(reqs())
po3 = lpo('Shafa Al Nahdah', [(cement, 20, 'bag', 16), ('Concrete C40/20 OPC', 12, 'm3', 280), ('Pump 42mtr', 1, 'trip', 950)], '919')
new = [reqs()[i] for i in set(reqs()) - before]
ck('3 a direct LPO is tracked: one request for it', len(new) == 1, new)
t3 = new[0] if new else {}
ck('3 ... for the LPO\'s site (919), not "STORE"', t3.get('site') == '919', t3.get('site'))
ck('3 ... with every line, the newly typed concrete and pump too', sorted(l['description'] for l in t3.get('lines', [])) == sorted(['Cement 50KG', 'Concrete C40/20 OPC', 'Pump 42mtr']),
   [l['description'] for l in t3.get('lines', [])])
ck('3 ... on follow-up for 919', sorted(f[1] for f in follow_up() if f[0] == t3.get('ref')) == ['919'] * 3, follow_up())
tl = {l['description']: l for l in t3.get('lines', [])}
if tl:
    receive(t3['id'], [(tl['Cement 50KG']['id'], 20)])
    ck('3 arrival goes to site 919, not the central store', stock_at(cement['id'], '919') == 20 and stock_at(cement['id'], '') == 0, (stock_at(cement['id'], '919'), stock_at(cement['id'], '')))

# ---- 4. a direct LPO for the store -------------------------------------------------------------------------------------
before = set(reqs())
lpo('Seomaa', [(coverall, 20, 'pcs', 28)], 'Store')
t4 = [reqs()[i] for i in set(reqs()) - before]
ck('4 store LPO tracked under STORE', len(t4) == 1 and t4[0]['site'] == 'STORE', t4)
if t4:
    receive(t4[0]['id'], [(t4[0]['lines'][0]['id'], 20)])
    ck('4 arrives into the central store', stock_at(coverall['id'], '') == 20, stock_at(coverall['id'], ''))

# ---- 5. a combined LPO: each site tracks its own lines -----------------------------------------------------------------
before = set(reqs())
lpo('Al Waha Hardware', [(coverall, 5, 'pcs', 28, 'STORE'), (nails, 25, 'kg', 6.5, '913'), (silicone, 24, 'pcs', 9.5, '910')], 'STORE', combined=True)
t5 = sorted((reqs()[i]['site'], [l['description'] for l in reqs()[i]['lines']]) for i in set(reqs()) - before)
ck('5 combined LPO: tracked per site - store, 910, 913', t5 == [('910', ['White Silicone 300ml']), ('913', ['Wire Nail 2.5 Inch']), ('STORE', ['Safety Coverall'])], t5)

# ---- 6. LPO edited ----------------------------------------------------------------------------------------------------
getpo = lambda i: (lambda d: dict(d, delivery_date=d.get('delivery_date') or None, order_date=d.get('order_date') or None))(c.get(f"/store/purchase/orders/{i}", headers=H).json())
full = getpo(po3['id'])
body = dict(full, lines=[dict(l, qty=15) if l['description'] == 'Concrete C40/20 OPC' else l for l in full['lines'] if l['description'] != 'Pump 42mtr']
                        + [{'description': 'Temperature control', 'qty': 12, 'unit': 'm3', 'rate': 15, 'tax_pct': 5}])
x = c.put(f"/store/purchase/orders/{po3['id']}", json=body, headers=H)
t3b = req(t3['id']) if t3 else {}
got = sorted((l['description'], l['qty_requested'], l['qty_received']) for l in t3b.get('lines', []))
ck('6 direct LPO edited: its tracking follows (concrete 12->15, pump off, temperature control on, cement kept as received)',
   x.status_code == 200 and got == [('Cement 50KG', 20, 20), ('Concrete C40/20 OPC', 15, 0), ('Temperature control', 12, 0)], got)
mr6 = raise_req('910', [(cement, 30), (sand, 4)])
c.post(f"/store/requests/{mr6['id']}/status", json={'status': 'approved'}, headers=H)
q6 = [p for p in pending() if p['request_id'] == mr6['id']]
po6 = lpo('Al Danube', [(cement, 30, 'bag', 16.5), (sand, 4, 'm3', 105)], '910', [p['line_id'] for p in q6])
full = getpo(po6['id'])
c.put(f"/store/purchase/orders/{po6['id']}", json=dict(full, lines=[l for l in full['lines'] if l['item_id'] == cement['id']]), headers=H)
ck('6 sand taken off the site\'s LPO: back on the purchaser\'s queue', [p['item_id'] for p in pending() if p['request_id'] == mr6['id']] == [sand['id']], pending())

# ---- 7. LPO cancelled ---------------------------------------------------------------------------------------------------
before = set(reqs())
po7 = lpo('Rashidco', [(cement, 50, 'bag', 16)], '913')
t7 = [reqs()[i] for i in set(reqs()) - before][0]
c.post(f"/store/purchase/orders/{po7['id']}/cancel", json={'reason': 'Duplicate LPO', 'not_needed': False}, headers=H)
ck('7 direct LPO cancelled: its tracking closes (nobody asked for it - not back on the queue)',
   req(t7['id'])['status'] == 'closed' and not [p for p in pending() if p['request_id'] == t7['id']], (req(t7['id'])['status'], [p for p in pending() if p['request_id'] == t7['id']]))
mr7 = raise_req('919', [(sand, 6)])
c.post(f"/store/requests/{mr7['id']}/status", json={'status': 'approved'}, headers=H)
q7 = [p for p in pending() if p['request_id'] == mr7['id']]
po7b = lpo('Srayedin', [('Black Sand 3M3', 6, 'load', 105)], '919', [p['line_id'] for p in q7])
c.post(f"/store/purchase/orders/{po7b['id']}/cancel", json={'reason': 'Supplier cannot supply', 'not_needed': False}, headers=H)
ck('7 site LPO cancelled, still needed: back on the queue (even with the LPO\'s own wording)', [p['request_id'] for p in pending()].count(mr7['id']) == 1)
po7c = lpo('Al Danube', [(sand, 6, 'm3', 105)], '919', [p['line_id'] for p in pending() if p['request_id'] == mr7['id']])
c.post(f"/store/purchase/orders/{po7c['id']}/cancel", json={'reason': 'Site says not needed', 'not_needed': True}, headers=H)
ck('7 ... reordered, then not needed: the request closes, off follow-up', req(mr7['id'])['status'] == 'closed' and not [f for f in follow_up() if f[0] == mr7['ref']])

# ---- 8. hired scaffolding booked in on Rentals -------------------------------------------------------------------------
ledger, beam = item('Ledger 1.2m', 'asset'), item('Aluminium Beam 3.5m', 'asset')
r_ledger, r_beam = item('Rental Ledger 1.2M', 'asset'), item('Rental Aluminium Beam 3.5M', 'asset')
before = set(reqs())
po8 = lpo('Desarch Building Contracting', [(ledger, 85, 'nos', 0.35), (beam, 145, 'nos', 5.25)], '919')
t8 = [reqs()[i] for i in set(reqs()) - before][0]
x = c.post('/store/hire/in', json={'supplier_name': 'Desarch Building Contracting', 'received_on': '2026-10-27', 'location': '919', 'reference': '402422',
    'lines': [{'item_id': r_ledger['id'], 'qty': 85}, {'item_id': r_beam['id'], 'qty': 100}]}, headers=H)
t8b = req(t8['id'])
ck('8 booked in on Rentals at 919: received on its LPO\'s request (ledger 85, beam 100 of 145)',
   x.status_code == 200 and sorted((l['description'], l['qty_received']) for l in t8b['lines']) == [('Aluminium Beam 3.5m', 100), ('Ledger 1.2m', 85)], (x.text, t8b['lines']))
ck('8 ... part delivered, 45 beams still to come', t8b['status'] == 'partial' and [f[3] for f in follow_up() if f[0] == t8['ref']] == [45], follow_up())
ck('8 ... and the hired stock is the hire company\'s, at 919', stock_at(r_beam['id'], '919') == 100)

# ---- 9. came another way: Already booked in ----------------------------------------------------------------------------
bl = next(l for l in t8b['lines'] if l['description'].startswith('Aluminium'))
x = c.post(f"/store/requests/{t8['id']}/lines/{bl['id']}/arrived", json={}, headers=H)
ck('9 the last 45 beams marked "already booked in": delivered, no stock added twice',
   x.status_code == 200 and req(t8['id'])['status'] == 'delivered' and stock_at(beam['id'], '919') == 0 and stock_at(r_beam['id'], '919') == 100)

# ---- 10. the lists ------------------------------------------------------------------------------------------------------
fu = follow_up()
ck('10 follow-up: nothing delivered, closed or rejected is listed', all(by_ref(f[0])['status'] not in ('delivered', 'closed', 'rejected') for f in fu), fu)
ck('10 purchaser\'s queue: nothing already on an LPO', all(not p.get('supplier') for p in pending()))

# ---- 11. an LPO raised before the request lines were kept with it, edited now: no second request for it --------------
mr11 = raise_req('914', [(cement, 70)])
c.post(f"/store/requests/{mr11['id']}/status", json={'status': 'approved'}, headers=H)
q11 = [p for p in pending() if p['request_id'] == mr11['id']]
po11 = lpo('Unimix', [(cement, 70, 'bag', 16)], '914', [p['line_id'] for p in q11])
d = database.SessionLocal(); o_ = d.get(models.PurchaseOrder, po11['id']); o_.request_line_ids = ''; d.commit(); d.close()   # as raised before 29 Oct
n0 = len(reqs())
full = getpo(po11['id'])
c.put(f"/store/purchase/orders/{po11['id']}", json=dict(full, lines=[dict(l, rate=17) for l in full['lines']]), headers=H)
ck('11 older LPO edited: its site request stands, no second request made', len(reqs()) == n0 and req(mr11['id'])['status'] == 'ordered', (len(reqs()), n0))
print(f"{len(FAIL)} FAILED" if FAIL else 'ALL PASS')

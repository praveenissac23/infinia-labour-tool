"""Purchasing the way the purchaser works (31 Oct 2026, Arun's questionnaire) - every change, through the API:

  a  an LPO raised straight away (no request) is on the store keeper's delivery list; booked in part, then the
     rest, with the DN number and date; to the LPO's site; status Ordered -> Part delivered -> Delivered
  b  DN number and date are required; more than is still to come is refused
  c  service lines (pump, temperature control, transport ...) never stock; the 'Service' tick decides when set;
     a store LPO books into the central store; Project expense: a site LPO is the site's cost even when its
     request was a store top-up
  d  an approved request with no LPO arrives, bought with petty cash - linked to the petty cash bill line
  e  cancelling an LPO cancels it everywhere: request lines back to 'To order' (or closed, not needed);
     an old cancellation (request left 'ordered') reads 'To order' when read, and is on the purchaser's list
  f  LPO name <-> Rentals name links (prefilled from the answers and by name, one to many); a hire LPO line reads
     delivered from what Rentals booked in at the site; booking it from the LPO books it on Rentals
  g  supplier bill check: no., date, amount, ticked; difference to the LPO total incl. round off; on Send to Zoho
  h  a typed material name close to one on the list is pointed out
  i  a revision (R1) replaces the order before it everywhere
  -  request-based LPO: delivery booked on the LPO moves the request; one booked on the request moves the LPO
  -  the rest of a line closed (not needed); an edited LPO keeps its deliveries

    cd app && DATABASE_URL=sqlite:////tmp/pu.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/purchasing_test.py   (empty db)"""
import sys
sys.path.insert(0, '.')
from datetime import date
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main, purchasing, projexpense

db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Administrator', role='admin'))
for s in ('913', '910', '919', '912'):
    db.add(models.Site(code=s, active=True))
db.commit(); db.close()
c = TestClient(main.app, raise_server_exceptions=False)
H = {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': 'admin', 'password': 'p'}).json()['access_token']}
FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{str(x)[:600]}]'))
    if not ok: FAIL.append(l)

def item(n, t='consumable', u='nos'):
    r = c.post('/store/items', json={'name': n, 'unit': u, 'item_type': t}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()
def lpo(sup, lines, location='', line_ids=(), ref='', date_='2026-10-20', round_off=None):
    body = {'supplier_name': sup, 'order_date': date_, 'project_location': location, 'request_line_ids': list(line_ids), 'ref': ref,
            'lines': [dict({'qty': q, 'unit': u, 'rate': rate, 'tax_pct': 5}, **({'item_id': it['id'], 'description': it['name']} if isinstance(it, dict) else {'description': it}), **extra)
                      for it, q, u, rate, *ex in lines for extra in [ex[0] if ex else {}]]}
    if round_off is not None:
        body['round_off'] = round_off
    r = c.post('/store/purchase/orders', json=body, headers=H)
    assert r.status_code == 200, r.text
    return r.json()
def dlv(show='open'):
    return {o['ref']: o for o in c.get(f'/store/purchase/deliveries?show={show}', headers=H).json()['orders']}
def odl(oid):
    return c.get(f'/store/purchase/orders/{oid}/deliveries', headers=H).json()
def deliver(oid, lines, dn='DN-1', on='2026-10-25', **kw):
    return c.post(f'/store/purchase/orders/{oid}/deliver', json=dict({'dn_no': dn, 'dn_date': on, 'lines': lines}, **kw), headers=H)
def stock_at(item_id, loc):
    d = database.SessionLocal(); m = main._stock_map(d); d.close()
    return round(m.get((item_id, loc), 0), 3)
def raise_req(site, lines):
    r = c.post('/store/requests', json={'site': site, 'requested_by': 'Site', 'needed_by': '2026-11-05', 'urgency': 'normal', 'notes': '',
        'requested_on': '2026-10-19',
        'lines': [{'item_id': i['id'], 'qty_requested': q, 'unit': i['unit'], 'purpose': 'work'} for i, q in lines]}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()
reqs = lambda: {r['id']: r for r in c.get('/store/requests', headers=H).json()}

cement, sand, concrete, pump, temp = item('Cement 50KG', u='bag'), item('Black Sand', u='trip'), item('Concrete C40/20', u='m3'), \
    item('PUMP 42MTR', u='m3'), item('TEMPERATURE CONTROL 32*', u='m3')

# ---- a, b, c: a direct LPO for 913 with concrete, pump, temperature control ------------------------------------------
o = lpo('Shafa Al Nahdah', [(concrete, 116, 'm3', 353), (pump, 116, 'm3', 15), (temp, 116, 'm3', 12)], location='913')
d = dlv()
ck('a direct LPO is on the store keeper\'s delivery list', o['ref'] in d, list(d))
row = d.get(o['ref'], {'lines': []})
ck('to be delivered to its site 913', row.get('deliver_to') == '913', row.get('deliver_to'))
sv = {l['description']: l['service'] for l in row['lines']}
ck('pump and temperature control are services, concrete is not', sv == {'Concrete C40/20': False, 'PUMP 42MTR': True, 'TEMPERATURE CONTROL 32*': True}, sv)
lid = {l['description']: l['line_id'] for l in row['lines']}
r = deliver(o['id'], [{'line_id': lid['Concrete C40/20'], 'qty': 50}], dn='')
ck('b no DN number - refused', r.status_code == 400 and 'DN' in r.text, r.text)
r = deliver(o['id'], [{'line_id': lid['Concrete C40/20'], 'qty': 50}], on='')
ck('b no DN date - refused', r.status_code == 400, r.text)
r = deliver(o['id'], [{'line_id': lid['Concrete C40/20'], 'qty': 500}])
ck('b more than ordered - refused', r.status_code == 400 and '116' in r.text, r.text)
r = deliver(o['id'], [{'line_id': lid['Concrete C40/20'], 'qty': 50}, {'line_id': lid['PUMP 42MTR'], 'qty': 50}], dn='DN-501')
ck('a part delivery booked', r.status_code == 200 and r.json()['status'] == 'part', r.text)
ck('a concrete into stock at 913 (not the central store)', stock_at(concrete['id'], '913') == 50 and stock_at(concrete['id'], '') == 0,
   (stock_at(concrete['id'], '913'), stock_at(concrete['id'], '')))
ck('c pump is never stock', stock_at(pump['id'], '913') == 0 and stock_at(pump['id'], '') == 0)
p = {l['description']: l for l in odl(o['id'])['lines']}
ck('a remaining shown per line', p['Concrete C40/20']['remaining'] == 66 and p['PUMP 42MTR']['remaining'] == 66 and p['TEMPERATURE CONTROL 32*']['remaining'] == 116, p)
hist = odl(o['id'])['history']
ck('a the DN number and date kept with the delivery', any(h['dn'] == 'DN-501' and h['date'] == '2026-10-25' for h in hist), hist)
r = deliver(o['id'], [{'line_id': v, 'qty': 66 if k != 'TEMPERATURE CONTROL 32*' else 116} for k, v in lid.items()], dn='DN-502', on='2026-10-26')
ck('a the rest booked: Delivered', r.status_code == 200 and r.json()['status'] == 'delivered', r.text)
ck('a off the open delivery list once delivered', o['ref'] not in dlv() and o['ref'] in dlv('all'))
reg = {x['label']: x for x in c.get('/store/purchase/report?group_by=order&status=all', headers=H).json()['rows']}
ck('a the register shows it Delivered', reg[o['ref']].get('delivery') == 'delivered', reg[o['ref']])
mv = database.SessionLocal().query(models.StoreMovement).filter(models.StoreMovement.reference == 'DN-501').first()
ck('a the stock movement carries the DN number and the LPO rate', mv and mv.unit_cost == 353 and o['ref'] in (mv.notes or ''), mv and (mv.unit_cost, mv.notes))

# the 'Service' tick: transport ticked NOT a service, a 'Fixing kit' ticked a service
kit, trans = item('Fixing Kit'), item('Transportation')
o2 = lpo('Dani Trading', [(trans, 1, 'trip', 700, {'service': False}), (kit, 2, 'nos', 50, {'service': True})], location='910')
sv = {l['description']: l['service'] for l in odl(o2['id'])['lines']}
ck('c the Service tick wins over the words', sv == {'Transportation': False, 'Fixing Kit': True}, sv)
got = c.get(f"/store/purchase/orders/{o2['id']}", headers=H).json()
ck('c the tick is kept on the LPO', [l['service'] for l in got['lines']] == [False, True], got['lines'])

# a store LPO goes into the central store
brush = item('Soft Brush')
o3 = lpo('Seomaa', [(brush, 6, 'nos', 14)], location='STORE')
l3 = odl(o3['id'])['lines'][0]
deliver(o3['id'], [{'line_id': l3['line_id'], 'qty': 6}], dn='S-1')
ck('c a store LPO books into the central store', stock_at(brush['id'], '') == 6, stock_at(brush['id'], ''))

# Project expense: a site LPO whose request was a store top-up is still the site's cost
d_ = database.SessionLocal()
mr_store = models.MaterialRequest(ref='MR-9001', site='STORE', status='ordered', requested_on=date(2026, 10, 14), notes='Stock for the store, ordered on X')
d_.add(mr_store); d_.flush()
po = models.PurchaseOrder(po_no=99001, ref='IC/LPO/99001', order_date=date(2026, 10, 14), supplier_name='Shafa', project_location='912',
                          request_id=mr_store.id, status='issued')
d_.add(po); d_.flush()
d_.add(models.PurchaseOrderLine(order_id=po.id, description='PUMP 42MTR', qty=100, rate=15, tax_pct=5)); d_.commit()
projexpense._CACHE.clear()
g = projexpense.gather(d_)
lines912 = [x for x in g['lines'].get('912', []) if x.get('cat') == 'lpo'] if isinstance(g, dict) and 'lines' in g else None
if lines912 is None:
    lpos = projexpense._lpos(d_, projexpense._site_matcher(projexpense._projects(d_)), None, None)
    hit = [x for x in lpos if x['ref'] == 'IC/LPO/99001']
    ck('c Project expense: a 912 LPO raised as a store top-up is 912\'s cost', hit and hit[0]['sites'] == ['912'] and not hit[0]['to_store'], hit)
else:
    ck('c Project expense: a 912 LPO raised as a store top-up is 912\'s cost', any(x['ref'] == 'IC/LPO/99001' for x in lines912), lines912)
d_.close()

# ---- request-based LPO: the two ways of booking keep each other right --------------------------------------------
mr = raise_req('910', [(cement, 100), (sand, 3)])
ml = {l['item_id']: l['id'] for l in mr['lines']}
c.post(f"/store/requests/{mr['id']}/status", json={'status': 'approved'}, headers=H)
o4 = lpo('Al Danube', [(cement, 100, 'bag', 16), (sand, 3, 'trip', 300)], location='910', line_ids=ml.values())
l4 = {l['description']: l['line_id'] for l in odl(o4['id'])['lines']}
r = deliver(o4['id'], [{'line_id': l4['Cement 50KG'], 'qty': 100}], dn='AD-1')
rq = reqs()[mr['id']]
got = {l['item_id']: l['qty_received'] for l in rq['lines']}
ck('booked on the LPO: the request line it was raised for moves too', got[cement['id']] == 100 and rq['status'] == 'partial', (got, rq['status']))
r = c.post(f"/store/requests/{mr['id']}/receive-bulk", json={'lines': [{'line_id': ml[sand['id']], 'qty': 3}], 'reference': 'AD-2', 'received_on': '2026-10-26'}, headers=H)
p = odl(o4['id'])
ck('booked on the request: the LPO reads Delivered too', p['status'] == 'delivered', p)
ck('nothing counted twice (cement 100 at 910)', stock_at(cement['id'], '910') == 100, stock_at(cement['id'], '910'))
ck('the LPO is not on the open list twice', o4['ref'] not in dlv())

# ---- d: an approved request with no LPO, bought with petty cash ----------------------------------------------------
broom = item('Plastic Broom')
mr2 = raise_req('910', [(broom, 20)])
c.post(f"/store/requests/{mr2['id']}/status", json={'status': 'approved'}, headers=H)
d_ = database.SessionLocal()
d_.add(models.PettyCash(book='site', on_date=date(2026, 10, 21), description='Plastic broom 20 pcs', supplier='Hardware shop', paid=94.5))
d_.add(models.PettyCash(book='site', on_date=date(2026, 10, 21), description='Taxi', paid=20)); d_.commit(); d_.close()
cands = c.get(f"/store/requests/{mr2['id']}/petty-candidates", headers=H).json()['rows']
ck('d the petty cash bill is offered (the taxi is not)', len(cands) == 1 and 'broom' in cands[0]['description'].lower(), cands)
r = c.post(f"/store/requests/{mr2['id']}/arrived-petty", json={'lines': [{'line_id': mr2['lines'][0]['id'], 'qty': 20}],
                                                              'received_on': '2026-10-22', 'petty_cash_id': cands[0]['id']}, headers=H)
ck('d marked arrived - bought with petty cash', r.status_code == 200 and r.json()['status'] == 'delivered', r.text)
rq = reqs()[mr2['id']]
ck('d the line says petty cash; stock at the request\'s site', rq['lines'][0]['source'] == 'petty' and stock_at(broom['id'], '910') == 20, (rq['lines'][0], stock_at(broom['id'], '910')))
d_ = database.SessionLocal()
mv = d_.query(models.StoreMovement).filter(models.StoreMovement.item_id == broom['id']).first()
ck('d no cost made up (no LPO)', mv.unit_cost == 0 and d_.query(models.MaterialRequestLine).get(mr2['lines'][0]['id']).petty_cash_id == cands[0]['id'])
d_.close()

# ---- e: cancel everywhere --------------------------------------------------------------------------------------------
mr3 = raise_req('913', [(cement, 50)])
c.post(f"/store/requests/{mr3['id']}/status", json={'status': 'approved'}, headers=H)
o5 = lpo('Rashidco', [('Cement 50KG Cemex', 50, 'bag', 16)], location='913', line_ids=[mr3['lines'][0]['id']])
ck('e ordered: off the purchaser\'s list', not any(x['request_id'] == mr3['id'] for x in c.get('/store/purchase/pending', headers=H).json()))
r = c.post(f"/store/purchase/orders/{o5['id']}/cancel", json={'reason': 'Site says not needed', 'not_needed': False}, headers=H)
rq = reqs()[mr3['id']]
ck('e cancelled, still needed: the request line is back to To order', rq['lines'][0]['supplier'] is None and rq['status'] == 'approved', rq)
ck('e ...and on the purchaser\'s list again', any(x['request_id'] == mr3['id'] for x in c.get('/store/purchase/pending', headers=H).json()))
ck('e a cancelled LPO is not on the delivery list', o5['ref'] not in dlv('all'))
# an old cancellation that left its request 'ordered' (as IC/LPO/20260151 did): put right when read
mr4 = raise_req('102', [(cement, 100)])
c.post(f"/store/requests/{mr4['id']}/status", json={'status': 'approved'}, headers=H)
o6 = lpo('Rashidco', [('Cement 50KG cemex', 100, 'bag', 16)], location='102', date_='2026-10-24')
d_ = database.SessionLocal()
ml4 = d_.query(models.MaterialRequestLine).get(mr4['lines'][0]['id'])
ml4.supplier_id = d_.query(models.PurchaseOrder).get(o6['id']).supplier_id
d_.query(models.MaterialRequest).get(mr4['id']).status = 'ordered'
po6 = d_.query(models.PurchaseOrder).get(o6['id']); po6.status = 'cancelled'; po6.cancel_reason = 'old'
d_.commit(); d_.close()
rq = reqs()[mr4['id']]
ck('e an old cancelled LPO\'s request reads To order, never Ordered', rq['status'] == 'approved' and rq['lines'][0]['supplier'] is None
   and rq['lines'][0].get('lpo_cancelled') == o6['ref'], rq)
ck('e ...and is on the purchaser\'s list', any(x['request_id'] == mr4['id'] for x in c.get('/store/purchase/pending', headers=H).json()))
# cancelling now with 'not needed' on a request it was not raised from (older LPO): found by supplier + name
mr5 = raise_req('912', [(sand, 9)])
c.post(f"/store/requests/{mr5['id']}/status", json={'status': 'approved'}, headers=H)
o7 = lpo('Srayedin', [('BLACK SAND', 9, 'trip', 300)], location='912')
d_ = database.SessionLocal()
d_.query(models.MaterialRequestLine).get(mr5['lines'][0]['id']).supplier_id = d_.query(models.PurchaseOrder).get(o7['id']).supplier_id
d_.query(models.MaterialRequest).get(mr5['id']).status = 'ordered'; d_.commit(); d_.close()
c.post(f"/store/purchase/orders/{o7['id']}/cancel", json={'reason': 'not needed', 'not_needed': True}, headers=H)
rq = reqs()[mr5['id']]
ck('e cancelled, not needed: the request closes', rq['status'] == 'closed' and rq['lines'][0]['status'] == 'rejected', rq)

# ---- f: Rentals links -------------------------------------------------------------------------------------------------
ledger, spigot, props = item('Ledger 1.2m', t='asset'), item('Spigot / Nut & Bolt', t='asset'), item('M.D Props 3.20 to 5.0m', t='asset')
r_ledger, r_pin, r_nut, r_prop = item('Rental Ledger 1.2M', t='asset'), item('Rental Spigot Pin', t='asset'), item('Rental Spigot Pin Nut/Bolt', t='asset'), item('Rental Prop 5.0M', t='asset')
oh = lpo('Desarch', [(ledger, 85, 'nos', 0.3), (spigot, 235, 'nos', 0.1), (props, 100, 'nos', 0.5)], location='919', date_='2026-10-23')
# Rentals: booked in at 919 from Desarch (one delivery note each) - before any link exists
hin = lambda lines, ref, loc='919': c.post('/store/hire/in', json={'supplier_name': 'Desarch', 'location': loc, 'received_on': '2026-10-27', 'reference': ref,
                                                                  'lines': [{'item_id': i['id'], 'qty': q} for i, q in lines]}, headers=H)
r = hin([(r_ledger, 85), (r_pin, 235), (r_nut, 235), (r_prop, 99)], '402417')
ck('f hire-in booked', r.status_code == 200, r.text)
ck('f before the links: the LPO\'s own request took what the old name match found - never more than ordered',
   all(l['delivered'] <= l['ordered'] for l in odl(oh['id'])['lines']), odl(oh['id'])['lines'])
r = c.post('/store/rental-map/prefill', headers=H).json()
names = {(a['lpo_name'], a['rental_name']) for a in r['added']}
ck('f prefill: the answers (spigot = two items, props = Prop 5.0M) and by name (Ledger 1.2m)',
   {('Spigot / Nut & Bolt', 'Rental Spigot Pin'), ('Spigot / Nut & Bolt', 'Rental Spigot Pin Nut/Bolt'), ('M.D Props 3.20 to 5.0m', 'Rental Prop 5.0M'),
    ('Ledger 1.2m', 'Rental Ledger 1.2M')} <= names, names)
r2 = c.post('/store/rental-map/prefill', headers=H).json()
ck('f prefill twice adds nothing', r2['added'] == [], r2['added'])
p = {l['description']: l for l in odl(oh['id'])['lines']}
ck('f hire lines read delivered from Rentals at the site (spigot needs both items)', p['Ledger 1.2m']['delivered'] == 85 and p['Spigot / Nut & Bolt']['delivered'] == 235
   and p['M.D Props 3.20 to 5.0m']['delivered'] == 99 and p['M.D Props 3.20 to 5.0m']['remaining'] == 1, p)
ck('f status Part delivered (1 prop short)', odl(oh['id'])['status'] == 'part')
# the last prop: damaged, returned - not needed
r = deliver(oh['id'], [{'line_id': p['M.D Props 3.20 to 5.0m']['line_id'], 'qty': 0, 'close': True}], dn='402417')
ck('f the 1 short closed as not needed -> Delivered', r.status_code == 200 and r.json()['status'] == 'delivered', r.text)
ck('f nothing booked twice on Rentals', stock_at(r_prop['id'], '919') == 99 and stock_at(props['id'], '919') == 0)
# the same material at another site is not this LPO's
oh2 = lpo('Desarch', [(ledger, 10, 'nos', 0.3)], location='913', date_='2026-10-24')
hin([(r_ledger, 10)], '402500', loc='919')
ck('f a hire-in at 919 does not deliver a 913 LPO', odl(oh2['id'])['status'] == 'ordered')
# booked from the LPO: it goes on Rentals under its Rentals name, owned by the supplier
r = deliver(oh2['id'], [{'line_id': odl(oh2['id'])['lines'][0]['line_id'], 'qty': 10}], dn='402600')
ck('f a hire line booked from the LPO goes on Rentals', r.status_code == 200 and stock_at(r_ledger['id'], '913') == 10 and stock_at(ledger['id'], '913') == 0, r.text)
d_ = database.SessionLocal()
mv = d_.query(models.StoreMovement).filter(models.StoreMovement.reference == '402600').first()
ck('f ...owned by the supplier (hired, not ours)', mv and mv.owner_id is not None)
d_.close()
# a link added and removed by hand
rm = c.get('/store/rental-map', headers=H).json()
r = c.post('/store/rental-map', json={'lpo_name': 'Swivel Coupler - Forged', 'rental_item_id': r_pin['id']}, headers=H)
ck('f a link added by hand', r.status_code == 200 and r.json()['added'], r.text)
lk = next(x for x in r.json()['rows'] if x['lpo_name'] == 'Swivel Coupler - Forged')
r = c.delete(f"/store/rental-map/{lk['id']}", headers=H)
ck('f ...and taken off', r.status_code == 200 and not any(x['lpo_name'] == 'Swivel Coupler - Forged' for x in r.json()['rows']))

# ---- g: bill check ------------------------------------------------------------------------------------------------------
og = lpo('Gemini', [(brush, 10, 'nos', 13.3)], location='909', round_off=0.35)      # 133 + 6.65 + 0.35 = 140.00
r = c.post(f"/store/purchase/orders/{og['id']}/bill", json={'bill_no': 'INV-77', 'bill_date': '2026-10-28', 'bill_amount': 140.0, 'checked': True}, headers=H)
b = r.json()
ck('g bill recorded, checked; LPO total includes the round off; no difference', r.status_code == 200 and b['lpo_total'] == 140.0 and b['bill_diff'] == 0 and b['bill_checked'], b)
r = c.post(f"/store/purchase/orders/{og['id']}/bill", json={'bill_no': 'INV-77', 'bill_date': '2026-10-28', 'bill_amount': 141.5, 'checked': False}, headers=H)
ck('g a difference is shown', r.json()['bill_diff'] == 1.5, r.json())
r = c.post(f"/store/purchase/orders/{og['id']}/bill", json={'bill_no': '', 'bill_amount': '', 'checked': True}, headers=H)
ck('g cannot tick checked without the bill no. and amount', r.status_code == 400)
c.post(f"/store/purchase/orders/{og['id']}/bill", json={'bill_no': 'INV-77', 'bill_date': '28/10/2026', 'bill_amount': 140, 'checked': True}, headers=H)
zr = c.get('/store/zoho/pos', headers=H)
row = next((x for x in zr.json().get('rows', []) if x['id'] == og['id']), None) if zr.status_code == 200 else None
ck('g the Send to Zoho list shows the bill is checked', row is not None and row['bill_checked'] and row['bill_no'] == 'INV-77', (zr.status_code, row))
ck('g the register shows it', {x['label']: x for x in c.get('/store/purchase/report?group_by=order&status=all', headers=H).json()['rows']}[og['ref']]['bill_checked'])

# ---- h: material names --------------------------------------------------------------------------------------------------
s = c.get('/store/items/similar', params={'name': 'cement 50 kg'}, headers=H).json()
ck('h a close name is pointed out', any(x['name'] == 'Cement 50KG' for x in s['close']), s)
s = c.get('/store/items/similar', params={'name': 'Ledger 1.3m'}, headers=H).json()
ck('h a different size is not the same material', not any(x['name'] == 'Ledger 1.2m' for x in s['close']), s)
s = c.get('/store/items/similar', params={'name': 'Cement 50KG'}, headers=H).json()
ck('h the exact name is the material itself', s['exact'] and s['exact']['name'] == 'Cement 50KG', s)

# ---- i: a revision replaces the order before it -------------------------------------------------------------------------
mr6 = raise_req('913', [(ledger, 200)])
c.post(f"/store/requests/{mr6['id']}/status", json={'status': 'approved'}, headers=H)
ob = lpo('Desarch', [(ledger, 200, 'nos', 0.3)], location='913', line_ids=[mr6['lines'][0]['id']], ref='IC/LPO/77150', date_='2026-10-24')
rev = lpo('Desarch', [(ledger, 180, 'nos', 0.3)], location='913', ref='IC/LPO/77150R1', date_='2026-10-24')
old = c.get(f"/store/purchase/orders/{ob['id']}", headers=H).json()
ck('i the original is cancelled - replaced by R1', old['status'] == 'cancelled' and old['superseded_by'] == 'IC/LPO/77150R1' and 'R1' in old['cancel_reason'], old)
rq = reqs()[mr6['id']]
ck('i the request stays ordered - on the revision now', rq['lines'][0]['supplier'] is not None and rq['status'] == 'ordered', rq)
ck('i only the revision is on the delivery list', 'IC/LPO/77150R1' in dlv() and 'IC/LPO/77150' not in dlv('all'))
reg = {x['label']: x for x in c.get('/store/purchase/report?group_by=order&status=all', headers=H).json()['rows']}
ck('i the register says superseded', reg['IC/LPO/77150'].get('delivery') == 'superseded', reg['IC/LPO/77150'])

# ---- an edited LPO keeps what was delivered against it --------------------------------------------------------------------
oe = lpo('Al Raha', [(brush, 10, 'nos', 5), (kit, 4, 'nos', 9)], location='910')
le = {l['description']: l['line_id'] for l in odl(oe['id'])['lines']}
deliver(oe['id'], [{'line_id': le['Soft Brush'], 'qty': 10}], dn='AR-1')
full = c.get(f"/store/purchase/orders/{oe['id']}", headers=H).json()
full['lines'] = [dict(l, qty=6 if l['description'] == 'Fixing Kit' else l['qty']) for l in full['lines']]
r = c.put(f"/store/purchase/orders/{oe['id']}", json={k: v for k, v in full.items() if k in ('supplier_name', 'order_date', 'project_location', 'lines', 'ref')}, headers=H)
p = {l['description']: l for l in odl(oe['id'])['lines']}
ck('edited LPO: the brush delivery still counts, the kit 6 to come', r.status_code == 200 and p['Soft Brush']['delivered'] == 10 and p['Fixing Kit']['remaining'] == 6, (r.text[:200], p))

# ---- activity log --------------------------------------------------------------------------------------------------------
d_ = database.SessionLocal()
acts = {a.action for a in d_.query(models.AuditLog).all()}
d_.close()
ck('every change is in the activity log', {'lpo_delivery', 'lpo_bill_check', 'rental_map', 'cancel_lpo', 'material_request_receive'} <= acts, acts)

print(f"\n{len(FAIL)} FAILED" if FAIL else "\nALL PASSED")
sys.exit(1 if FAIL else 0)

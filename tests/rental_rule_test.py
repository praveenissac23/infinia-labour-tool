"""One rule for rental stock (01 Nov 2026, owner: "If any items are rental - even if I add it as rental, even if I get it
from the purchase as rental - it must be under rental. It must be shown in the stock and in the rental area."):
a material is RENTAL when a supplier owns it. Through the API, on an empty database:

  1  a Rental material added with an opening quantity: in Stock as 'Rental - <supplier>' and on Rentals, same figures
  2  Rental in of one of our own materials: the rented part goes onto its Rental twin - two rows, ours and rental
  3  a material booked in as received on a Rental material with no supplier said: the rental supplier's
  4  an LPO from a supplier we rent from is ticked Rental by itself (editable); a delivery on it books into Rentals on a
     Rental material (made / found), never our stock; the LPO reads Delivered; nothing booked twice
  5  an LPO unticked (bought outright) from the same supplier, for a Rental material: our own stock, on the owned twin
  6  Stock: per-type totals apart (rental never in the Asset total); exports and preview say 'Rental - <supplier>'
  7  every step: Stock (type Rental) = Rentals, per material, supplier and place; no material ours and rental at once

    cd app && DATABASE_URL=sqlite:////tmp/rr.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/rental_rule_test.py   (empty db)"""
import io, sys
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main, purchasing

db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Administrator', role='admin'))
for s in ('913', '919', '926'):
    db.add(models.Site(code=s, active=True))
db.commit(); db.close()
c = TestClient(main.app, raise_server_exceptions=False)
H = {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': 'admin', 'password': 'p'}).json()['access_token']}
FAIL = []


def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{str(x)[:700]}]'))
    if not ok:
        FAIL.append(l)


def items():
    return {i['name']: i for i in c.get('/store/items?active_only=false', headers=H).json()}


def stock():
    return c.get('/store/report?kind=stock', headers=H).json()


def same_as_rentals(label):
    """Stock (type Rental) and Rentals: the same quantity for every material, supplier and place."""
    a, b = {}, {}
    for r in stock()['rows']:
        if r['item_type'] == 'rental':
            for loc, q in [('', r['in_store'])] + list(r['by_site'].items()):
                if q:
                    a[(r['_item_id'], r['_supplier_id'], loc)] = q
    for g in c.get('/store/hire', headers=H).json()['suppliers']:
        for i in g['items']:
            for loc, q in i['by_location'].items():
                if q:
                    b[(i['item_id'], i['supplier_id'], loc)] = q
    d = database.SessionLocal()
    pos = main._stock_map(d, by_owner=True)
    d.close()
    owned = {i for (i, l, o), q in pos.items() if o is None and abs(q) > 1e-9}
    hired = {i for (i, l, o), q in pos.items() if o is not None and abs(q) > 1e-9}
    ck(f'{label}: Stock (Rental) = Rentals, per material, supplier and place', a == b and bool(b), (a, b))
    ck(f'{label}: no material holds ours and rental at once', not (owned & hired), owned & hired)


def lpo(sup, lines, location='919', rental=None):
    body = {'supplier_name': sup, 'order_date': '2026-10-28', 'project_location': location, 'ref': '',
            'lines': [{'description': d, 'qty': q, 'unit': 'nos', 'rate': 1, 'tax_pct': 5, **({'item_id': i} if i else {})} for d, q, i in lines]}
    if rental is not None:
        body['rental'] = rental
    r = c.post('/store/purchase/orders', json=body, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def deliver(oid, lines, dn='DN-9', on='2026-10-29'):
    return c.post(f'/store/purchase/orders/{oid}/deliver', json={'dn_no': dn, 'dn_date': on, 'lines': lines}, headers=H)


# ---- 1 a Rental material added with an opening quantity ------------------------------------------------------------
r = c.post('/store/items', json={'name': 'Rental Ledger 1.8M', 'unit': 'pcs', 'item_type': 'rental',
                                 'rental_supplier': 'Desarch Building Contracting', 'opening_qty': 100,
                                 'opening_location': '913'}, headers=H)
ck('a Rental material with an opening quantity saves', r.status_code == 200, r.text[:200])
st = stock()
row = [x for x in st['rows'] if x['name'] == 'Rental Ledger 1.8M']
ck("in Stock as 'Rental - Desarch Building Contracting', 100 at 913",
   len(row) == 1 and row[0]['item_type'] == 'rental' and row[0]['_type_label'] == 'Rental – Desarch Building Contracting'
   and row[0]['by_site'] == {'913': 100} and row[0]['total'] == 100, row)
hire = c.get('/store/hire', headers=H).json()
ck('and on Rentals under Desarch, 100 at 913', any(i['name'] == 'Rental Ledger 1.8M' and i['by_location'] == {'913': 100}
                                                   for g in hire['suppliers'] for i in g['items']), hire)
same_as_rentals('1')

# ---- 2 Rental in of one of our own materials -------------------------------------------------------------------------
std = c.post('/store/items', json={'name': 'Standard 2.0M', 'unit': 'pcs', 'item_type': 'asset', 'opening_qty': 40}, headers=H).json()
r = c.post('/store/hire/in', json={'supplier_name': 'Desarch Building Contracting', 'received_on': '2026-10-27', 'location': '913',
                                   'reference': 'DN-402370', 'lines': [{'item_id': std['id'], 'qty': 50}]}, headers=H)
ck('Rental in of our own Standard 2.0M is booked', r.status_code == 200, r.text[:300])
ck('the reply says it went onto Rental Standard 2.0M and uses the word rental',
   'Rental Standard 2.0M' in r.json().get('detail', '') and 'on rental from' in r.json().get('detail', '') and 'hire' not in r.json().get('detail', '').lower(),
   r.json())
it = items()
ck('Rental Standard 2.0M is a Rental material, rented from Desarch',
   it['Rental Standard 2.0M']['item_type'] == 'rental' and it['Rental Standard 2.0M']['rental_supplier'] == 'Desarch Building Contracting', it.get('Rental Standard 2.0M'))
rows = {(x['name'], x['item_type']): x for x in stock()['rows']}
ck('two rows: our 40 as Asset, the 50 as Rental - Desarch at 913',
   rows[('Standard 2.0M', 'asset')]['total'] == 40 and rows[('Rental Standard 2.0M', 'rental')]['by_site'] == {'913': 50}, rows)
same_as_rentals('2')

# ---- 3 received as 'in' on a Rental material with no supplier said ---------------------------------------------------
r = c.post('/store/movements', json={'item_id': it['Rental Standard 2.0M']['id'], 'kind': 'in', 'qty': 30, 'location': '926',
                                     'moved_on': '2026-10-31', 'supplier': 'Desarch Building Contracting', 'reference': '402545'}, headers=H)
ck('stock received on a Rental material', r.status_code == 200, r.text[:300])
d = database.SessionLocal()
m = d.query(models.StoreMovement).filter(models.StoreMovement.reference == '402545').first()
sup = d.query(models.Supplier).filter(models.Supplier.name == 'Desarch Building Contracting').first()
ck("is the rental supplier's, not ours (owner Desarch)", m is not None and sup is not None and m.owner_id == sup.id, m and m.owner_id)
d.close()
same_as_rentals('3')

# ---- 4 a rental LPO ----------------------------------------------------------------------------------------------------
sups = {s['name']: s for s in c.get('/store/suppliers', headers=H).json()}
ck('Desarch is marked as a supplier we rent from (the LPO tick sets itself)', sups.get('Desarch Building Contracting', {}).get('rental') is True, sups)
o = lpo('Desarch Building Contracting', [('Ledger 1.8m', 40, None), ('Cuplock Standard 1.3M', 10, None)])
full = c.get(f"/store/purchase/orders/{o['id']}", headers=H).json()
ck('an LPO from Desarch reads Rental (by itself)', full.get('rental') is True and full.get('rental_set') is None, (full.get('rental'), full.get('rental_set')))
dl = c.get(f"/store/purchase/orders/{o['id']}/deliveries", headers=H).json()
ck('the delivery window says Rental LPO, each line rental',
   dl.get('rental') is True and all(x['rental'] for x in dl['lines']), dl)
it = items()
ck("a material made new for a rental LPO line is a Rental material ('Cuplock Standard 1.3M', rented from Desarch)",
   it['Cuplock Standard 1.3M']['item_type'] == 'rental' and it['Cuplock Standard 1.3M']['rental_supplier'] == 'Desarch Building Contracting',
   it.get('Cuplock Standard 1.3M'))
lines = {x['description']: x for x in dl['lines']}
r = deliver(o['id'], [{'line_id': lines['Ledger 1.8m']['line_id'], 'qty': 40}, {'line_id': lines['Cuplock Standard 1.3M']['line_id'], 'qty': 10}])
ck('a delivery on the rental LPO is booked', r.status_code == 200, r.text[:400])
ck('it says rental, not hire', 'booked in on rental as Rental Ledger 1.8M' in ' '.join(r.json().get('done', [])) and
   'hire' not in ' '.join(r.json().get('done', [])).lower(), r.json().get('done'))
ck('the LPO reads Delivered', r.json().get('status') == 'delivered', r.json().get('status'))
rows = {(x['name'], x['item_type']): x for x in stock()['rows']}
ck('Ledger 1.8m (the LPO name) holds nothing; Rental Ledger 1.8M holds 100 at 913 + 40 at 919',
   ('Ledger 1.8m', 'consumable') not in rows and rows[('Rental Ledger 1.8M', 'rental')]['by_site'] == {'913': 100, '919': 40}, rows)
ck('Cuplock Standard 1.3M: 10 at 919 as Rental - Desarch', rows.get(('Cuplock Standard 1.3M', 'rental'), {}).get('by_site') == {'919': 10}, rows)
same_as_rentals('4')
r = deliver(o['id'], [{'line_id': lines['Ledger 1.8m']['line_id'], 'qty': 1}])
ck('nothing more can be booked on it - nothing booked twice', r.status_code == 400, r.text[:200])

# the tick can be changed by hand
full['rental'] = False
body = {k: full[k] for k in ('ref', 'order_date', 'supplier_name', 'project_location')}
body.update({'rental': False, 'lines': [{'item_id': l['item_id'], 'description': l['description'], 'qty': l['qty'], 'unit': l['unit'],
                                          'rate': l['rate'], 'tax_pct': l['tax_pct']} for l in full['lines']]})
r = c.put(f"/store/purchase/orders/{o['id']}", json=body, headers=H)
ck('the Rental tick can be unticked by hand', r.status_code == 200 and r.json().get('rental') is False and r.json().get('rental_set') is False, r.text[:300])
body['rental'] = True
r = c.put(f"/store/purchase/orders/{o['id']}", json=body, headers=H)
ck('and ticked again', r.status_code == 200 and r.json().get('rental') is True, r.text[:300])

# ---- 5 bought outright from the same supplier ------------------------------------------------------------------------
o2 = lpo('Desarch Building Contracting', [('Rental Ledger 1.8M', 5, items()['Rental Ledger 1.8M']['id'])], location='926', rental=False)
dl2 = c.get(f"/store/purchase/orders/{o2['id']}/deliveries", headers=H).json()
ck('an LPO unticked (bought - lost items replaced) is not rental', dl2.get('rental') is False and not dl2['lines'][0]['rental'], dl2)
r = deliver(o2['id'], [{'line_id': dl2['lines'][0]['line_id'], 'qty': 5}], dn='DN-10')
ck('its delivery is booked', r.status_code == 200, r.text[:300])
rows = {(x['name'], x['item_type']): x for x in stock()['rows']}
ck('the 5 bought are ours, on the owned twin Ledger 1.8M (Asset) - never on the Rental material',
   rows.get(('Ledger 1.8M', 'asset'), {}).get('by_site') == {'926': 5} and rows[('Rental Ledger 1.8M', 'rental')]['total'] == 140, rows)
same_as_rentals('5')

# ---- 6 totals and paper ----------------------------------------------------------------------------------------------
st = stock()
tt = st['type_totals']
ck('totals per type kept apart: Asset 45 (ours), Rental 230 (suppliers)', tt['asset']['total'] == 45 and tt['rental']['total'] == 230, tt)
low = c.get('/store/report?kind=by_site&site=913', headers=H).json()['rows']
ck('What a site holds: the rental row says Rental', any(x['item_type'] == 'rental' and x['_type_label'].startswith('Rental –') for x in low), low)
t = c.post('/auth/download-token', headers=H).json()['token']
pv = c.get(f'/export/store/report/view?kind=stock&token={t}')
ck('the stock preview prints the type as Rental - Desarch and the totals per type',
   pv.status_code == 200 and 'Rental – Desarch Building Contracting' in pv.text and 'suppliers, not ours' in pv.text, pv.text[:300])
xl = c.get(f'/export/store/report?kind=stock&format=excel&token={t}')
import openpyxl
wb = openpyxl.load_workbook(io.BytesIO(xl.content))
cells = [str(v) for row in wb.active.iter_rows(values_only=True) for v in row if v is not None]
ck('the Excel says Rental - Desarch too, and has no screen-only columns',
   any('Rental – Desarch' in x for x in cells) and not any(x in ('_item_id', '_key', 'Item Id', 'Key') for x in cells), cells[:40])
ck('no screen or paper word says hire', 'hire' not in pv.text.lower().replace('/store/hire', ''), None)

print('\n' + ('ALL PASS' if not FAIL else f'{len(FAIL)} FAILED: ' + '; '.join(FAIL)))
sys.exit(1 if FAIL else 0)

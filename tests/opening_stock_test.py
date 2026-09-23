"""Opening stock: the shelves were full before the system started.

Run: cd app && DATABASE_URL=sqlite:////tmp/os.db python3 ../tests/opening_stock_test.py

The store went live with material already on the shelves. It goes in
from one sheet - every material listed, a quantity typed against each
one held - and each quantity lands in the ledger as a receipt marked
"Opening stock". A material already received is skipped, so the sheet
can be imported twice without doubling anything, and the single-item
"Already have" box works for a material that exists but has never come
in.
"""
import sys, io, warnings
warnings.simplefilter('ignore')
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main, openpyxl

db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Praveen', role='admin'))
db.add(models.User(username='amal', hashed_password=auth.hash_password('p'), full_name='Amal', role='office', permissions='store,storekeeper'))
db.add(models.User(username='site1', hashed_password=auth.hash_password('p'), full_name='Site', role='site', permissions='attendance,requests'))
db.add(models.Site(code='901', active=True))
db.commit(); db.close()
c = TestClient(main.app, raise_server_exceptions=False)
def tok(u):
    return {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': u, 'password': 'p'}).json()['access_token']}
ADMIN, KEEPER, SITE = tok('admin'), tok('amal'), tok('site1')
FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{str(x)[:160]}]'))
    if not ok: FAIL.append(l)

# The material list, as imported before go-live. Nothing received yet.
def item(name, kind, unit):
    return c.post('/store/items', json={'name': name, 'unit': unit, 'item_type': kind}, headers=KEEPER).json()
cem = item('Cement OPC 50kg', 'consumable', 'bag')
sand = item('Sand Washed', 'consumable', 'm3')
drill = item('Hilti Drill TE-60', 'asset', 'pcs')
scaff = item('Scaffold Ledger 2m', 'rental', 'pcs')
tiles = item('Tile Laying Gurumala', 'consumable', 'pcs')
# One material that HAS been received already, through the normal route.
c.post('/store/movements', json={'item_id': tiles['id'], 'kind': 'in', 'qty': 301, 'location': '', 'supplier': 'Al Raha', 'moved_on': '2026-09-19'}, headers=KEEPER)

# ---- The sheet -------------------------------------------------------
t = c.post('/auth/download-token', headers=KEEPER).json()['token']
r = c.get(f'/export/store/opening-template?token={t}')
ck('the opening stock sheet downloads', r.status_code == 200, r.status_code)
ws = openpyxl.load_workbook(io.BytesIO(r.content)).active
rows = list(ws.iter_rows(values_only=True))
ck('headed Code / Material / Unit / Type / Quantity in store', list(rows[0]) == ['Code', 'Material', 'Unit', 'Type', 'Quantity in store'], rows[0])
ck('every material is listed', {r[1] for r in rows[1:]} == {'Cement OPC 50kg', 'Sand Washed', 'Hilti Drill TE-60', 'Scaffold Ledger 2m', 'Tile Laying Gurumala'})
ck('the quantity column is blank to fill', all(r[4] is None for r in rows[1:] if r[1] != 'Tile Laying Gurumala'))
ck('a material already received says so', next(r[4] for r in rows[1:] if r[1] == 'Tile Laying Gurumala') == 'already received')

# ---- Filled in the way a keeper would --------------------------------
for r in ws.iter_rows(min_row=2):
    name = r[1].value
    r[4].value = {'Cement OPC 50kg': 50, 'Sand Washed': 12.5, 'Hilti Drill TE-60': 3, 'Scaffold Ledger 2m': 0,
                  'Tile Laying Gurumala': 999}.get(name)
buf = io.BytesIO(); ws.parent.save(buf); buf.seek(0)
filled = buf.getvalue()

ck('a site engineer cannot import an opening count',
   c.post('/store/items/opening-import', files={'file': ('o.xlsx', filled)}, headers=SITE).status_code == 403)
r = c.post('/store/items/opening-import', files={'file': ('o.xlsx', filled)}, headers=KEEPER)
ck('the keeper imports it', r.status_code == 200, r.text[:200]); out = r.json()
ck('three materials counted in (a zero is not a count)', out['added'] == 3, out)
ck('the one already received was skipped, not doubled', out['skipped_received'] == [tiles['code']], out)
ck('the reply says so in words', 'already been received' in out['detail'], out['detail'])

st = {s['name']: s for s in c.get('/store/stock', headers=KEEPER).json()}
ck('cement: 50 in the store', st['Cement OPC 50kg']['central'] == 50, st['Cement OPC 50kg'])
ck('sand: 12.5 - a decimal survives', st['Sand Washed']['central'] == 12.5, st['Sand Washed'])
ck('drill: 3', st['Hilti Drill TE-60']['central'] == 3)
ck('scaffolding: none (was 0 on the sheet)', st['Scaffold Ledger 2m']['central'] == 0)
ck('tiles: still 301, untouched by the 999 on the sheet', st['Tile Laying Gurumala']['central'] == 301, st['Tile Laying Gurumala'])

mv = c.get(f"/store/movements?item_id={cem['id']}", headers=KEEPER).json()
ck('the count is in the ledger as an opening receipt', len(mv) == 1 and mv[0]['kind'] == 'in' and mv[0]['reference'] == 'Opening stock', mv)

# ---- Imported again by mistake ---------------------------------------
r2 = c.post('/store/items/opening-import', files={'file': ('o.xlsx', filled)}, headers=KEEPER).json()
ck('a second import adds nothing', r2['added'] == 0, r2)
ck('and skips everything already counted', len(r2['skipped_received']) == 4, r2)
st = {s['name']: s for s in c.get('/store/stock', headers=KEEPER).json()}
ck('cement still 50 - nothing doubled', st['Cement OPC 50kg']['central'] == 50)

# ---- A sheet with a row that is not on the list ----------------------
ws.append(['ITM999', 'Unicorn Dust', 'kg', 'Consumable', 5])
buf = io.BytesIO(); ws.parent.save(buf); buf.seek(0)
r3 = c.post('/store/items/opening-import', files={'file': ('o.xlsx', buf.getvalue())}, headers=KEEPER).json()
ck('an unknown material is reported, not invented', r3['unknown'] == ['itm999'] and r3['added'] == 0, r3)

# ---- The single-item "Already have" box ------------------------------
lad = item('Aluminium Ladder 3m', 'asset', 'pcs')
r = c.post('/store/items', json={'code': lad['code'], 'name': 'Aluminium Ladder 3m', 'unit': 'pcs', 'item_type': 'asset', 'opening_qty': 4}, headers=KEEPER)
ck('Already have works for a material that exists but was never received', r.status_code == 200
   and next(s for s in c.get('/store/stock', headers=KEEPER).json() if s['item_id'] == lad['id'])['central'] == 4)
c.post('/store/items', json={'code': lad['code'], 'name': 'Aluminium Ladder 3m', 'unit': 'pcs', 'item_type': 'asset', 'opening_qty': 4}, headers=KEEPER)
ck('saving the item again with the box filled does not add again',
   next(s for s in c.get('/store/stock', headers=KEEPER).json() if s['item_id'] == lad['id'])['central'] == 4)

# ---- After the count, the store works as normal ----------------------
ck('the counted cement can be issued', c.post('/store/movements', json={'item_id': cem['id'], 'kind': 'out', 'qty': 20, 'from_location': '', 'location': '901', 'incharge': 'Amal', 'moved_on': '2026-09-20'}, headers=KEEPER).status_code == 200)
ck('and the store is down to 30', next(s for s in c.get('/store/stock', headers=KEEPER).json() if s['item_id'] == cem['id'])['central'] == 30)
ck('the opening count shows in the purchases report as received',
   any('Cement' in r['name'] for r in c.get('/store/report?kind=purchases', headers=KEEPER).json()['rows']))

# ---- The Materials-panel table: add stock any time -------------------
r = c.post('/store/items/opening', json={'lines': [{'item_id': cem['id'], 'item_type': 'consumable', 'qty': 20},
                                                    {'item_id': drill['id'], 'item_type': 'asset', 'qty': 1}]}, headers=KEEPER)
ck('a few lines added by hand', r.status_code == 200 and len(r.json()['added']) == 2, r.text[:200])
ck('cement went from 30 to 50', next(s for s in c.get('/store/stock', headers=KEEPER).json() if s['item_id'] == cem['id'])['central'] == 50)
r = c.post('/store/items/opening', json={'lines': [{'item_id': cem['id'], 'item_type': 'consumable', 'qty': 5}]}, headers=KEEPER)
ck('and again later - it is not a one-off', r.status_code == 200 and next(s for s in c.get('/store/stock', headers=KEEPER).json() if s['item_id'] == cem['id'])['central'] == 55)
ck('each addition is a receipt in the ledger',
   sum(1 for m in c.get(f"/store/movements?item_id={cem['id']}", headers=KEEPER).json() if m['reference'] == 'Added by hand') == 2)
ck('a site engineer cannot add stock', c.post('/store/items/opening', json={'lines': [{'item_id': cem['id'], 'qty': 1}]}, headers=SITE).status_code == 403)
ck('an empty table is refused', c.post('/store/items/opening', json={'lines': []}, headers=KEEPER).status_code == 400)

# ---- Stock can be put straight onto a site, not only the yard --------
site_add = c.post('/store/items/opening', json={'location': '901', 'lines': [
    {'item_id': drill['id'], 'item_type': 'asset', 'qty': 3}]}, headers=KEEPER)
ck('stock can be added straight to a site', site_add.status_code == 200, site_add.text[:200])
drow = next(s for s in c.get('/store/stock', headers=KEEPER).json() if s['item_id'] == drill['id'])
ck('and it lands at the site, not the central store', drow['by_site'].get('901') == 3, drow)
ck('the reply says where it went', 'site 901' in site_add.json()['detail'], site_add.json()['detail'])
ck('a site that is not on file is refused',
   c.post('/store/items/opening', json={'location': 'NOWHERE', 'lines': [
       {'item_id': drill['id'], 'qty': 1}]}, headers=KEEPER).status_code == 400)

# ---- Hired stock added here really goes on hire ----------------------
# Marking a line 'rental' says what kind of thing it is, never whose it
# is. Left at that, a hired quantity was booked as ours and the hire
# list stayed empty - the whole point of the hire tracking missed by one
# unasked question.
trap = c.post('/store/items/opening', json={'lines': [
    {'item_id': drill['id'], 'item_type': 'rental', 'qty': 150}]}, headers=KEEPER)
ck('a rental line with nobody named is refused, not silently owned',
   trap.status_code == 400, f'{trap.status_code} {trap.text[:160]}')
ck('and the refusal says to name the trader',
   'hired from' in trap.text.lower() or 'trader' in trap.text.lower(), trap.text[:200])

hired = c.post('/store/items/opening', json={
    'owner_name': 'Al Raha Scaffolding', 'lines': [
        {'item_id': drill['id'], 'item_type': 'rental', 'qty': 150}]}, headers=KEEPER)
ck('naming the trader books it in on hire', hired.status_code == 200, hired.text[:200])
on_hire = c.get('/store/hire', headers=KEEPER).json()
ck('and it shows on the hire list', on_hire['lines'] == 1, on_hire)
ck('under the trader it is hired from',
   on_hire['suppliers'][0]['supplier'] == 'Al Raha Scaffolding', on_hire['suppliers'][0])
ck('for the quantity added', on_hire['suppliers'][0]['items'][0]['qty'] == 150, on_hire['suppliers'][0])
drow = next(s for s in c.get('/store/stock', headers=KEEPER).json() if s['item_id'] == drill['id'])
ck('the stock list separates it from what we own', drow['hired'] == 150, drow)

print('\n' + ('ALL PASS' if not FAIL else f'{len(FAIL)} FAILED: ' + '; '.join(FAIL)))
sys.exit(1 if FAIL else 0)

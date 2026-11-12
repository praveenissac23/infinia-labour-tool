"""Purchasing > Requests register (12/11/2026): every material the store asked for, as asked, kept after it is
ordered (even renamed on the LPO) and delivered; next to what was ordered and what came; the LPO's own requests
left out; Preview / PDF / Excel.
    cd app && DATABASE_URL=sqlite:////tmp/rr.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/requests_register_test.py  (empty db)"""
import io, sys
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main

db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Administrator', role='admin'))
db.add(models.Site(code='914', active=True)); db.add(models.Site(code='919', active=True)); db.commit(); db.close()
c = TestClient(main.app, raise_server_exceptions=False)
H = {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': 'admin', 'password': 'p'}).json()['access_token']}
FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{str(x)[:400]}]'))
    if not ok: FAIL.append(l)
it = lambda n, u='pcs': c.post('/store/items', json={'name': n, 'unit': u, 'item_type': 'consumable'}, headers=H).json()
g9, g4, nail = it('Angle Grinder 9 Inch'), it('Angle Grinder 4.5 Inch'), it('Wire Nail 2.5 Inch', 'kg')
m = c.post('/store/requests', json={'site': '914', 'requested_by': 'Amal', 'needed_by': '2026-11-11', 'urgency': 'normal', 'notes': '',
    'lines': [{'item_id': g9['id'], 'qty_requested': 1, 'unit': 'pcs', 'purpose': 'FOR BLOCK AND STEEL CUTTING'},
              {'item_id': g4['id'], 'qty_requested': 1, 'unit': 'pcs', 'purpose': 'FOR STEEL CUTTING'},
              {'item_id': nail['id'], 'qty_requested': 45, 'unit': 'kg', 'purpose': '913,919 SLAB WORKS'}]}, headers=H).json()
c.post(f"/store/requests/{m['id']}/status", json={'status': 'approved'}, headers=H)
m = [x for x in c.get('/store/requests', headers=H).json() if x['id'] == m['id']][0]
ids = {l['description'] or l.get('item_name') or '': l['id'] for l in m['lines']}
lid = [l['id'] for l in m['lines']]
reg = lambda k='asked': {r['asked']: r for r in c.get(f'/store/requests/report?kind={k}', headers=H).json()['rows'] if r['ref'] == m['ref']}
r0 = reg()
ck('waiting: all three, as asked, with what for and who asked', set(r0) == {'Angle Grinder 9 Inch', 'Angle Grinder 4.5 Inch', 'Wire Nail 2.5 Inch'}
   and r0['Wire Nail 2.5 Inch']['asked_qty'] == 45 and r0['Wire Nail 2.5 Inch']['what_for'] == '913,919 SLAB WORKS' and r0['Angle Grinder 9 Inch']['asked_by'] == 'Amal', r0)
po = c.post('/store/purchase/orders', json={'supplier_name': 'Tools Trading', 'order_date': '2026-11-12', 'project_location': '914', 'request_line_ids': lid,
    'lines': [{'item_id': g9['id'], 'description': 'Angle Grinder 9 Inch', 'qty': 1, 'unit': 'pcs', 'rate': 250, 'tax_pct': 5},
              {'item_id': g4['id'], 'description': 'Angle Grinder 4.5 Inch', 'qty': 1, 'unit': 'pcs', 'rate': 120, 'tax_pct': 5},
              {'item_id': nail['id'], 'description': 'Wire Nail 2.5 Inch', 'qty': 40, 'unit': 'kg', 'rate': 6, 'tax_pct': 5}]}, headers=H).json()
# the purchaser renames the 9 inch grinder to the supplier's name on an edit
c.put(f"/store/purchase/orders/{po['id']}", json={'supplier_name': 'Tools Trading', 'order_date': '2026-11-12', 'project_location': '914',
    'lines': [{'description': 'Makita GA9020 Grinder 230mm', 'qty': 1, 'unit': 'pcs', 'rate': 250, 'tax_pct': 5},
              {'item_id': g4['id'], 'description': 'Angle Grinder 4.5 Inch', 'qty': 1, 'unit': 'pcs', 'rate': 120, 'tax_pct': 5},
              {'item_id': nail['id'], 'description': 'Wire Nail 2.5 Inch', 'qty': 40, 'unit': 'kg', 'rate': 6, 'tax_pct': 5}]}, headers=H)
r1 = reg()
ck('ordered: still listed under what the store asked, not the LPO name', set(r1) == set(r0), list(r1))
ck('the renamed one shows what it was ordered as, marked changed', 'Makita GA9020' in r1['Angle Grinder 9 Inch']['ordered_as'] and r1['Angle Grinder 9 Inch']['changed'] == 'Yes'
   and r1['Angle Grinder 9 Inch']['lpo'] == po['ref'], r1['Angle Grinder 9 Inch'])
ck('fewer ordered than asked (40 of 45 kg) is marked changed', r1['Wire Nail 2.5 Inch']['changed'] == 'Yes' and '40 kg' in r1['Wire Nail 2.5 Inch']['ordered_as'], r1['Wire Nail 2.5 Inch'])
ck('ordered exactly as asked is not marked', r1['Angle Grinder 4.5 Inch']['changed'] == '', r1['Angle Grinder 4.5 Inch'])
ck('"Ordered differently" shows only the two', set(reg('asked_changed')) == {'Angle Grinder 9 Inch', 'Wire Nail 2.5 Inch'}, list(reg('asked_changed')))
rows = c.get('/store/requests/report?kind=asked', headers=H).json()['rows']
ck('the LPO\'s own requests are not in the register', all(r['ref'] == m['ref'] for r in rows), [r['ref'] for r in rows])
for f in ('excel', 'pdf'):
    tk = c.post('/auth/download-token', headers=H).json().get('token') or ''
    x = c.get(f'/export/store/report?kind=mr_asked&format={f}&token={tk}')
    ck(f'{f} downloads', x.status_code == 200 and len(x.content) > 800, x.status_code)
tk = c.post('/auth/download-token', headers=H).json().get('token') or ''
v = c.get(f'/export/store/report/view?kind=mr_asked&token={tk}')
ck('preview shows what was asked', v.status_code == 200 and 'Angle Grinder 9 Inch' in v.text and 'Makita' in v.text, v.status_code)
# a line made before the register: what was asked comes from the rename note
db = database.SessionLocal()
l = db.get(models.MaterialRequestLine, lid[0]); l.asked_name = None; l.asked_qty = None; db.commit()
main._backfill_asked(db); db.refresh(l)
ck('older lines: what was asked recovered from the rename note', l.asked_name == 'Angle Grinder 9 Inch' and l.asked_qty == 1, (l.asked_name, l.asked_qty, l.notes))
db.close()
# the reviewer's cases: an old note with no name (line picked from the list, renamed before 12/11), two notes on a line
db = database.SessionLocal()
l = db.get(models.MaterialRequestLine, lid[1]); l.asked_name = None; l.notes = "Asked as '', ordered as 'Air Type Tyre For Barrow' on IC/LPO/1"; db.commit()
l2 = db.get(models.MaterialRequestLine, lid[2]); l2.asked_name = None
l2.notes = "Asked as 'Wire Nail 2.5 Inch', ordered as 'Nail 65mm' on IC/LPO/1; Asked as 'Nail 65mm', ordered as 'Nail 2.5in box' on IC/LPO/2"; db.commit()
main._backfill_asked(db); db.refresh(l); db.refresh(l2)
ck('no name kept in the old note: said so, not the LPO name', l.asked_name == main.RENAMED_UNKNOWN, l.asked_name)
ck('two renames: the first name asked', l2.asked_name == 'Wire Nail 2.5 Inch', l2.asked_name)
db.close()
ck('and the unknown one shows as ordered differently', reg()[main.RENAMED_UNKNOWN]['changed'] == 'Yes', list(reg()))
# split over two LPOs: 45 kg asked, 25 + 20 ordered -> not changed; one LPO line for two requests -> not compared on qty
m2 = c.post('/store/requests', json={'site': '919', 'requested_by': 'Amal', 'needed_by': '2026-11-20', 'urgency': 'normal', 'notes': '',
    'lines': [{'item_id': nail['id'], 'qty_requested': 45, 'unit': 'kg', 'purpose': 'slab'}]}, headers=H).json()
c.post(f"/store/requests/{m2['id']}/status", json={'status': 'approved'}, headers=H)
l45 = [x for x in c.get('/store/requests', headers=H).json() if x['id'] == m2['id']][0]['lines'][0]['id']
for q in (25, 20):
    c.post('/store/purchase/orders', json={'supplier_name': 'Nails Co', 'order_date': '2026-11-12', 'project_location': '919', 'request_line_ids': [l45],
        'lines': [{'item_id': nail['id'], 'description': 'Wire Nail 2.5 Inch', 'qty': q, 'unit': 'kg', 'rate': 6, 'tax_pct': 5}]}, headers=H)
rr = [r for r in c.get('/store/requests/report?kind=asked', headers=H).json()['rows'] if r['ref'] == m2['ref']]
ck('45 kg ordered as 25 + 20 on two LPOs is not "changed"', rr and rr[0]['changed'] == '' and rr[0]['lpo'].count('IC/LPO') == 2, rr)
# Late / All open / Done & closed chips (12 Nov 2026): an open request past its needed-by date is late
m3 = c.post('/store/requests', json={'site': '921', 'requested_by': 'Amal', 'needed_by': '2020-01-01', 'urgency': 'normal', 'notes': '',
    'lines': [{'item_id': nail['id'], 'qty_requested': 3, 'unit': 'kg', 'purpose': 'old one'}]}, headers=H).json()
m4 = c.post('/store/requests', json={'site': '921', 'requested_by': 'Amal', 'needed_by': '2099-01-01', 'urgency': 'normal', 'notes': '',
    'lines': [{'item_id': nail['id'], 'qty_requested': 4, 'unit': 'kg', 'purpose': 'not due'}]}, headers=H).json()
late = {r['ref']: r for r in c.get('/store/requests/report?kind=asked_late', headers=H).json()['rows']}
ck('a request past its needed-by date shows under Late, with its days', m3['ref'] in late and late[m3['ref']]['days_late'] > 2000, late.get(m3['ref']))
ck('one not yet due is not late', m4['ref'] not in late)
allr = {r['ref']: r for r in c.get('/store/requests/report?kind=asked', headers=H).json()['rows']}
ck('open lines carry done = False for the chips', allr[m4['ref']]['_done'] is False and allr[m4['ref']]['days_late'] == '')
c.post(f"/store/requests/{m3['id']}/status", json={'status': 'rejected'}, headers=H)
late = {r['ref'] for r in c.get('/store/requests/report?kind=asked_late', headers=H).json()['rows']}
done = {r['ref'] for r in c.get('/store/requests/report?kind=asked_done', headers=H).json()['rows']}
ck('rejected: no longer late, now under Done & closed', m3['ref'] not in late and m3['ref'] in done)
tk = c.post('/auth/download-token', headers=H).json().get('token') or ''
x = c.get(f'/export/store/report/view?kind=mr_asked_late&token={tk}')
ck('the Late list previews', x.status_code == 200 and '_done' not in x.text, x.status_code)
x = c.get(f'/export/store/report?kind=mr_asked&format=excel&token={tk}')
ck('Excel downloads without the inner done flag', x.status_code == 200, x.status_code)
# Access (12 Nov 2026): saved roles and logins list tabs one by one - whoever has the LPO register gets the new tab, once
db = database.SessionLocal()
db.query(models.Setting).filter(models.Setting.key == "reqreg_granted").delete(); db.commit()
pm = models.AccessRole(name='Purchase Manager', screens='store,approvals,store.purchasing.lporegister,store.purchasing.purchase')
sk = models.AccessRole(name='Store keeper', screens='store,store.store.home,store.requests.requests')
lu = models.User(username='buyer2', hashed_password=auth.hash_password('p'), full_name='Buyer', role='office',
                 permissions='store,approvals,store.purchasing.lporegister')
db.add_all([pm, sk, lu]); db.commit()
main._grant_requests_register(db)
db.refresh(pm); db.refresh(sk); db.refresh(lu)
ck('a role with the LPO register now has the Requests register', 'store.purchasing.reqreg' in pm.screens.split(','), pm.screens)
ck('so does a login with its own ticks', 'store.purchasing.reqreg' in lu.permissions.split(','), lu.permissions)
ck('a store keeper role is left as it was', sk.screens == 'store,store.store.home,store.requests.requests', sk.screens)
pm.screens = 'store,approvals,store.purchasing.lporegister'; db.commit()
main._grant_requests_register(db); db.refresh(pm)
ck('only once - unticked later stays unticked', 'store.purchasing.reqreg' not in pm.screens, pm.screens)
db.close()
db = database.SessionLocal()
u = models.User(username='hr', hashed_password=auth.hash_password('p'), full_name='HR', role='office', permissions='staff'); db.add(u); db.commit(); db.close()
HR = {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': 'hr', 'password': 'p'}).json()['access_token']}
ck('a login without purchasing cannot read the register', c.get('/store/requests/report?kind=asked', headers=HR).status_code == 403)
tk = c.post('/auth/download-token', headers=HR).json().get('token') or ''
ck('nor download it', c.get(f'/export/store/report?kind=mr_asked&format=excel&token={tk}').status_code == 403)
print(f"{len(FAIL)} FAILED" if FAIL else 'ALL PASS')

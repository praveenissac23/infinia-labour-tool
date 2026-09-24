"""Go-live rehearsal for the store: cleared as it will be, then lived in.

Run: cd app && DATABASE_URL=sqlite:////tmp/gl2.db python3 ../tests/store_go_live_rehearsal.py

Attendance and payroll are live and are not touched. The store holds
practice entries; tomorrow it is cleared and used for real. So this
does exactly that, in order: a month of live attendance sits in the
database; the store is filled with practice; it is cleared the way the
Settings button clears it; the live side is checked to the row; and
then the store is put through its whole life from empty, as the three
people who will use it - a site engineer asking, the office approving
and ordering, the store keeper receiving and issuing - with every
report, every export and every notification checked along the way.
"""
import sys, io, warnings
warnings.simplefilter('ignore')
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main

db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Praveen', role='admin'))
db.add(models.User(username='office', hashed_password=auth.hash_password('p'), full_name='Office', role='office',
                   permissions='attendance,summaries,adjustments,livecard,reports,store,requests,approvals,purchase,followup,lporegister'))
db.add(models.User(username='amal', hashed_password=auth.hash_password('p'), full_name='Amal', role='office',
                   permissions='store,storekeeper,requests,followup'))
db.add(models.User(username='febiyan', hashed_password=auth.hash_password('p'), full_name='Febiyan', role='site',
                   permissions='attendance,requests'))
for no, nm in (('F-701', 'RAJAN'), ('F-702', 'SURESH'), ('F-703', 'ANIL')):
    db.add(models.Employee(emp_no=no, name=nm, trade='MASON', total_salary=2500, basic_salary=1500, active=True))
for code in ('901', '904', '915'):
    db.add(models.Site(code=code, plot_no=f'P-{code}', active=True))
db.add(models.Engineer(name='Febiyan', mobile='0501234567', active=True))
db.commit(); db.close()

c = TestClient(main.app, raise_server_exceptions=False)
def tok(u):
    return {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': u, 'password': 'p'}).json()['access_token']}
ADMIN, OFFICE, KEEPER, SITE = tok('admin'), tok('office'), tok('amal'), tok('febiyan')
FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{str(x)[:160]}]'))
    if not ok: FAIL.append(l)
def section(t): print(f'\n--- {t} ---')

# ======================================================================
section('Live attendance that must survive')
rows = [{'emp_no': no, 'full_date': f'2026-09-{d:02d}', 'am': 'Present', 'pm': 'Present', 'site': '904',
         'engineer': 'Febiyan', 'ot': 2, 'bh': 0, 'comments': ''} for no in ('F-701', 'F-702', 'F-703') for d in range(1, 16)]
c.post('/attendance/save', json={'month_year': 'September 2026', 'rows': rows}, headers=OFFICE)
sid = c.get('/summaries/September 2026', headers=OFFICE).json()[0]['id']
c.post(f'/summaries/{sid}/adjustments', json={'description': 'Advance', 'amount': 300, 'is_deduction': True}, headers=OFFICE)
def live():
    d = database.SessionLocal()
    try:
        return (d.query(models.DailyRow).count(), d.query(models.EmployeeSummary).count(),
                d.query(models.SalaryAdjustment).count(), d.query(models.Employee).count(),
                d.query(models.Site).count(), d.query(models.Engineer).count(), d.query(models.User).count())
    finally: d.close()
before = live()
ck('attendance in place: 45 days, 3 summaries, 1 adjustment', before[:3] == (45, 3, 1), before)

# ======================================================================
section('Practice entries in the store')
def item(name, kind, unit, who=KEEPER):
    body = {'name': name, 'unit': unit, 'item_type': kind}
    if kind == 'rental':
        body['rental_supplier'] = 'Al Raha Scaffolding'
    return c.post('/store/items', json=body, headers=who).json()
old_cem = item('Cement OPC 50kg', 'consumable', 'bag')
old_drill = item('Hilti Drill TE-60', 'returnable', 'pcs')
c.post('/store/movements', json={'item_id': old_cem['id'], 'kind': 'in', 'qty': 100, 'location': '', 'supplier': 'Practice Trader', 'moved_on': '2026-09-01'}, headers=KEEPER)
mr0 = c.post('/store/requests', json={'site': '901', 'requested_by': 'Febiyan', 'needed_by': '2026-09-10', 'urgency': 'normal', 'notes': 'practice',
    'lines': [{'item_id': old_cem['id'], 'qty_requested': 20, 'unit': 'bag', 'purpose': 'test', 'item_type': 'consumable', 'description': '', 'est_cost': 0, 'notes': ''}]}, headers=SITE).json()
c.post(f"/store/requests/{mr0['id']}/status", json={'status': 'approved'}, headers=OFFICE)
c.post('/store/purchase/orders', json={'order_date': '2026-09-02', 'supplier_name': 'Practice Trader', 'request_id': mr0['id'],
    'lines': [{'item_id': old_cem['id'], 'description': 'Cement', 'qty': 20, 'unit': 'bag', 'rate': 16, 'tax_pct': 5}]}, headers=OFFICE)
ck('practice request numbered MR-0001', mr0['ref'] == 'MR-0001', mr0['ref'])
ck('practice order numbered from the first LPO', c.get('/store/purchase/orders', headers=OFFICE).json()[0]['ref'] == 'IC/LPO/20260100')

# ======================================================================
section('Cleared the way the Settings button clears it')
ck('a store keeper cannot press it', c.post('/backup/store-reset', json={'confirm': 'CLEAR STORE'}, headers=KEEPER).status_code == 403)
ck('the wrong words are refused', c.post('/backup/store-reset', json={'confirm': 'clear store'}, headers=ADMIN).status_code == 400)
r = c.post('/backup/store-reset', json={'confirm': 'CLEAR STORE'}, headers=ADMIN)
ck('cleared by the admin', r.status_code == 200, r.text[:200])
ck('movements, requests, orders all gone',
   not c.get('/store/movements', headers=KEEPER).json() and not c.get('/store/requests', headers=OFFICE).json()
   and not c.get('/store/purchase/orders', headers=OFFICE).json())
ck('every stock figure zero', all(not s['central'] and not s['out_at_sites'] for s in c.get('/store/stock', headers=KEEPER).json()))
ck('material list kept (boxes unticked)', len(c.get('/store/items', headers=KEEPER).json()) == 2)
ck('supplier list kept (boxes unticked)', len(c.get('/store/suppliers', headers=OFFICE).json()) == 1)
after = live()
ck(f'attendance and payroll untouched to the row: {before}', after == before, after)
ck('a backup was taken first', any(b['trigger'] == 'before-store-reset' for b in c.get('/backup/list', headers=ADMIN).json()))
# The cement has a reorder level. Nothing has been received since the
# clearance, so it is "not stocked yet", not "running low" - the keeper
# must not open the store on day one to a wall of low-stock warnings.
again = c.post('/store/items', json={'name': 'CEMENT OPC 50KG', 'unit': 'bag', 'item_type': 'consumable', 'reorder_level': 20}, headers=KEEPER).json()
ck('adding a material by a name the store knows updates it, never makes a twin',
   again['id'] == old_cem['id'] and len([i for i in c.get('/store/items', headers=KEEPER).json() if 'cement' in i['name'].lower()]) == 1, again)
ck('an emptied store raises no low-stock warnings',
   not [n for n in c.get('/notifications', headers=KEEPER).json()['notifications'] if n.get('kind') == 'low'])
ck('and the reorder report is empty', c.get('/store/report?kind=low', headers=KEEPER).json()['rows'] == [])
ck('no notifications left over from practice',
   not [n for n in c.get('/notifications', headers=OFFICE).json()['notifications'] if 'MR-' in str(n)])

# ======================================================================
section('Day one: the site engineer asks for material')
sand = item('Sand Washed', 'consumable', 'm3')
# Named here because it is hired from Gateway further down, and a
# rental carries the name of whoever it goes back to.
scaff = c.post('/store/items', json={'name': 'Scaffold Ledger 2m', 'unit': 'pcs',
                                     'item_type': 'rental',
                                     'rental_supplier': 'Gateway Scaffolding'},
                headers=KEEPER).json()
mixer = item('Concrete Mixer 350L', 'asset', 'pcs')
mr = c.post('/store/requests', json={'site': '901', 'requested_by': 'Febiyan', 'needed_by': '2026-09-25', 'urgency': 'urgent', 'notes': 'slab pour Thursday',
    'lines': [{'item_id': old_cem['id'], 'qty_requested': 100, 'unit': 'bag', 'purpose': 'slab', 'item_type': 'consumable', 'description': '', 'est_cost': 16, 'notes': ''},
              {'item_id': sand['id'], 'qty_requested': 15, 'unit': 'm3', 'purpose': 'slab', 'item_type': 'consumable', 'description': '', 'est_cost': 0, 'notes': ''},
              {'item_id': None, 'description': 'Curing compound', 'qty_requested': 4, 'unit': 'can', 'purpose': 'slab', 'item_type': 'consumable', 'est_cost': 0, 'notes': ''}]}, headers=SITE)
ck('request accepted from the site login', mr.status_code == 200, mr.text[:200]); mr = mr.json()
ck('first live request is MR-0001 again', mr['ref'] == 'MR-0001', mr['ref'])
ck('a typed material joined the list', bool(mr.get('new_items')) and all(l['item_id'] for l in mr['lines']))
ck('a duplicate sent twice comes back as the same request',
   c.post('/store/requests', json={'site': '901', 'requested_by': 'Febiyan', 'needed_by': '2026-09-25', 'urgency': 'urgent', 'notes': 'again',
    'lines': [{'item_id': old_cem['id'], 'qty_requested': 100, 'unit': 'bag', 'purpose': 'slab', 'item_type': 'consumable', 'description': '', 'est_cost': 16, 'notes': ''},
              {'item_id': sand['id'], 'qty_requested': 15, 'unit': 'm3', 'purpose': 'slab', 'item_type': 'consumable', 'description': '', 'est_cost': 0, 'notes': ''},
              {'item_id': None, 'description': 'Curing compound', 'qty_requested': 4, 'unit': 'can', 'purpose': 'slab', 'item_type': 'consumable', 'est_cost': 0, 'notes': ''}]},
    headers=SITE).json().get('duplicate_of') == 'MR-0001')
ck('the site engineer cannot approve his own request', c.post(f"/store/requests/{mr['id']}/status", json={'status': 'approved'}, headers=SITE).status_code == 403)
ck('the site engineer cannot see stock movements', c.get('/store/movements', headers=SITE).status_code == 403)
ck('the site engineer cannot see a salary', c.get('/live-card/F-701/September 2026', headers=SITE).status_code == 403)
offn = c.get('/notifications', headers=OFFICE).json()['notifications']
ck('the office is told a request arrived', any('MR-0001' in str(n) for n in offn), [str(n)[:80] for n in offn][:3])
ck('the request prints as a PDF', c.get(f"/export/store/request/{mr['id']}?token=" + c.post('/auth/download-token', headers=OFFICE).json()['token']).content[:4] == b'%PDF')

# ======================================================================
section('The office approves, prices and orders')
lines = {l['description'] or l['item_name']: l for l in c.get('/store/requests', headers=OFFICE).json()[0]['lines']}
cur = next(l for l in mr['lines'] if 'Curing' in (l.get('description') or ''))
ck('one material can be turned down on its own',
   c.post(f"/store/request-lines/{cur['id']}/decision", json={'decision': 'rejected', 'reason': 'Not needed for this slab'}, headers=OFFICE).status_code == 200)
ck('the request is approved', c.post(f"/store/requests/{mr['id']}/status", json={'status': 'approved'}, headers=OFFICE).status_code == 200)
ck('the site is told it was approved', any('approved' in str(n).lower() for n in c.get('/notifications', headers=SITE).json()['notifications']))
pend = c.get('/store/purchase/pending', headers=OFFICE).json()
pend_lines = pend if isinstance(pend, list) else pend.get('lines', pend.get('rows', []))
ck('approved lines wait in the purchase queue, the rejected one does not',
   len(pend_lines) == 2 and not any('Curing' in str(x) for x in pend_lines), pend_lines)
ck('the next LPO number starts from the first', c.get('/store/purchase/next-no', headers=OFFICE).json()['ref'] == 'IC/LPO/20260100')
cem_line = next(l for l in mr['lines'] if l['item_id'] == old_cem['id'])
sand_line = next(l for l in mr['lines'] if l['item_id'] == sand['id'])
po = c.post('/store/purchase/orders', json={'order_date': '2026-09-18', 'supplier_name': 'Al Raha Trading LLC', 'supplier_trn': '100200300', 'request_id': mr['id'],
    'contact_person': 'Amal', 'mobile': '0509876543', 'request_line_ids': [cem_line['id'], sand_line['id']],
    'lines': [{'item_id': old_cem['id'], 'description': 'Cement OPC 50kg', 'qty': 100, 'unit': 'bag', 'rate': 16.5, 'tax_pct': 5},
              {'item_id': sand['id'], 'description': 'Sand Washed', 'qty': 15, 'unit': 'm3', 'rate': 45, 'tax_pct': 5}]}, headers=OFFICE)
ck('LPO raised', po.status_code == 200, po.text[:200]); po = po.json()
ck('numbered IC/LPO/20260100', po['ref'] == 'IC/LPO/20260100', po['ref'])
tokO = c.post('/auth/download-token', headers=OFFICE).json()['token']
orders = c.get('/store/purchase/orders', headers=OFFICE).json()
ck('the LPO register lists it with its supplier', orders and orders[0]['supplier'] == 'Al Raha Trading LLC', orders[:1])
ck('the supplier was created from the order', any(s['name'] == 'Al Raha Trading LLC' for s in c.get('/store/suppliers', headers=OFFICE).json()))
ck('marked ordered, with the supplier and a date',
   c.post(f"/store/requests/{mr['id']}/status", json={'status': 'ordered', 'supplier': 'Al Raha Trading LLC', 'expected_on': '2026-09-20'}, headers=OFFICE).status_code == 200)
ck('the keeper sees it on the chase list',
   any(x['status'] == 'ordered' for x in c.get('/store/requests', headers=KEEPER).json()))
ps = c.get('/store/purchase/price-search?q=cement', headers=OFFICE).json()
ck('price search finds what cement was last bought at', any(abs(float(m.get('last_rate', 0)) - 16.5) < 0.01 for m in ps.get('materials', [])), ps)
ck('a movement dated in the future is refused', c.post('/store/movements', json={'item_id': old_cem['id'], 'kind': 'in', 'qty': 1, 'location': '', 'moved_on': '2026-12-01'}, headers=KEEPER).status_code == 400)

# ======================================================================
section('The keeper receives the delivery')
rb = c.post(f"/store/requests/{mr['id']}/receive-bulk", json={'supplier': 'Al Raha Trading LLC', 'reference': 'DO-4471', 'notes': '', 'received_on': '2026-09-20',
    'lines': [{'line_id': cem_line['id'], 'qty': 60}]}, headers=KEEPER)
ck('a part delivery is received', rb.status_code == 200 and rb.json().get('status') == 'partial', rb.text[:200])
ck('the request shows what is still owed', next(l for l in c.get('/store/requests', headers=KEEPER).json()[0]['lines'] if l['item_id'] == old_cem['id'])['qty_received'] == 60)
rb2 = c.post(f"/store/requests/{mr['id']}/receive-bulk", json={'supplier': 'Al Raha Trading LLC', 'reference': 'DO-4480', 'notes': '', 'received_on': '2026-09-21',
    'lines': [{'line_id': cem_line['id'], 'qty': 40}, {'line_id': sand_line['id'], 'qty': 15}]}, headers=KEEPER)
ck('the rest arrives and the request completes', rb2.status_code == 200 and rb2.json().get('status') in ('delivered', 'received'), rb2.text[:200])
ck('the site is told it was delivered', any('deliver' in str(n).lower() for n in c.get('/notifications', headers=SITE).json()['notifications']))
at = c.get('/store/at-site?site=901', headers=KEEPER).json()
ck('delivered to 901 and shown as last sent there (consumables are used, not held)',
   not at['rows'] and {r['item_id'] for r in at['recent']} >= {old_cem['id'], sand['id']}, at)
ck('nothing went into the central store by mistake', all(s['central'] == 0 for s in c.get('/store/stock', headers=KEEPER).json() if s['item_id'] in (old_cem['id'], sand['id'])))
ck('nothing left to chase', not [x for x in c.get('/store/requests', headers=KEEPER).json() if x['status'] in ('ordered', 'partial')])

# ======================================================================
section('Stock bought straight into the store, issued, moved, returned, lost, counted')
def move(it, kind, qty, frm='', to='', who=KEEPER, **extra):
    body = {'item_id': it['id'], 'kind': kind, 'qty': qty, 'from_location': frm, 'location': to, 'incharge': 'Amal', 'notes': '', 'moved_on': str(__import__('datetime').date.today() - __import__('datetime').timedelta(days=1))}
    body.update(extra)
    return c.post('/store/movements', json=body, headers=who)
ck('the site engineer cannot record stock', move(scaff, 'in', 10, who=SITE).status_code == 403)
ck('scaffolding hired in', move(scaff, 'in', 600, supplier='Gateway Scaffolding', reference='HIRE-22').status_code == 200)
ck('a mixer bought', move(mixer, 'in', 2, supplier='Al Raha Trading LLC').status_code == 200)
ck('cement bought into the store', move(old_cem, 'in', 200, supplier='Al Raha Trading LLC').status_code == 200)
ck('more than the store holds is refused', move(scaff, 'out', 1000, to='904').status_code == 400)
ck('a negative quantity is refused', move(scaff, 'out', -5, to='904').status_code in (400, 422))
ck('scaffolding sent to 904', move(scaff, 'out', 400, to='904').status_code == 200)
ck('a mixer sent to 904', move(mixer, 'out', 1, to='904').status_code == 200)
ck('cement sent to 904', move(old_cem, 'out', 50, to='904').status_code == 200)
ck('scaffolding moved from 904 straight to 915', move(scaff, 'transfer', 100, frm='904', to='915').status_code == 200)
ck('more than 904 holds cannot be moved on', move(scaff, 'transfer', 5000, frm='904', to='915').status_code == 400)
ck('some scaffolding returned to the store', move(scaff, 'return', 50, frm='904', to='').status_code == 200)
ck('two ledgers lost at 915', move(scaff, 'lost', 2, frm='915').status_code == 200)
ck('a count correction in the store', move(old_cem, 'adjust', -3, to='', notes='count 22 Sep').status_code == 200)
ck('once stocked, running out IS flagged',
   move(old_cem, 'out', 140, to='915').status_code == 200 and
   any(n.get('kind') == 'low' and 'cement' in n['title'].lower() for n in c.get('/notifications', headers=KEEPER).json()['notifications']))
move(old_cem, 'return', 140, frm='915', to='')
st = {s['name']: s for s in c.get('/store/stock', headers=KEEPER).json()}
st['Cement OPC 50kg'] = next(s for s in st.values() if s['item_id'] == old_cem['id'])
ck('scaffolding: 250 in store (600 in, 400 out, 50 back)', st['Scaffold Ledger 2m']['central'] == 250, st['Scaffold Ledger 2m'])
ck('scaffolding: 250 at 904, 98 at 915', st['Scaffold Ledger 2m']['by_site'] == {'904': 250, '915': 98}, st['Scaffold Ledger 2m']['by_site'])
ck('mixer: 1 in store, 1 at 904', st['Concrete Mixer 350L']['central'] == 1 and st['Concrete Mixer 350L']['by_site'] == {'904': 1}, st['Concrete Mixer 350L'])
ck('cement: 147 in store, none carried at sites', st['Cement OPC 50kg']['central'] == 147 and st['Cement OPC 50kg']['by_site'] == {}, st['Cement OPC 50kg'])
at904 = c.get('/store/at-site?site=904', headers=KEEPER).json()
ck('904 holds the scaffolding and the mixer, and shows cement as last sent',
   {r['name'] for r in at904['rows']} == {'Scaffold Ledger 2m', 'Concrete Mixer 350L'} and any(r['item_id'] == old_cem['id'] for r in at904['recent']), at904)
hist = c.get(f"/store/movements?item_id={scaff['id']}", headers=KEEPER).json()
ck('the ledger holds every scaffolding movement', len(hist) == 5, len(hist))

# ======================================================================
section('Every report, on screen and on paper')
tokK = c.post('/auth/download-token', headers=KEEPER).json()['token']
for kind in ('stock', 'low', 'by_site', 'purchases', 'usage', 'assets', 'lost', 'hired'):
    r = c.get(f'/store/report?kind={kind}', headers=KEEPER)
    ok = r.status_code == 200 and 'rows' in r.json()
    for fmt in ('excel', 'pdf'):
        e = c.get(f'/export/store/report?kind={kind}&format={fmt}&token={tokK}')
        ok = ok and e.status_code == 200 and len(e.content) > 500
    ck(f'report {kind}: screen, Excel, PDF', ok)
assets = {r['name'] for r in c.get('/store/report?kind=assets', headers=KEEPER).json()['rows']}
ck('the asset register holds the mixer only', assets == {'Concrete Mixer 350L'}, assets)
hired = c.get('/store/report?kind=hired', headers=KEEPER).json()['rows']
ck('the hire register: scaffolding from Gateway, 2 lost', hired and hired[0]['hired_from'] == 'Gateway Scaffolding' and hired[0]['lost_damaged'] == 2, hired)
lost = c.get('/store/report?kind=lost', headers=KEEPER).json()['rows']
ck('the lost report names 915', any('915' in str(r) for r in lost), lost)
bys = c.get('/store/report?kind=by_site', headers=KEEPER).json()['rows']
ck('the sites report leaves cement out and shows the scaffolding at both sites',
   not any('Cement' in r['name'] for r in bys) and {r['site'] for r in bys if 'Scaffold' in r['name']} == {'904', '915'}, bys)
ck('the LPO prints', c.get(f"/export/store/purchase-report?token={tokO}").status_code == 200)
pr = c.get('/store/purchase/report', headers=OFFICE)
ck('the purchase report builds', pr.status_code == 200)
mreq = c.get('/store/requests/report?kind=history', headers=OFFICE)
ck('the request history report builds', mreq.status_code == 200, mreq.status_code)
ck('a supplier template downloads', c.get(f'/export/store/suppliers/template?token={tokO}').status_code == 200)
ck('the supplier list exports', c.get(f'/export/store/suppliers?token={tokO}').status_code == 200)

# ======================================================================
section('Cache and headers')
r = c.get('/store/stock', headers=KEEPER)
ck('API answers are never cached by a browser', 'no-store' in r.headers.get('cache-control', ''), r.headers.get('cache-control'))
r = c.get(f'/export/store/report?kind=stock&format=pdf&token={tokK}')
ck('downloads are left cacheable so the browser can save them', 'no-store' not in r.headers.get('cache-control', ''))

# ======================================================================
section('The store keeper permission')
ck('the keeper can record stock (permission ticked)', move(old_cem, 'in', 1, supplier='x').status_code == 200)
plain = tok('office')
ck('an office login without the "records stock" tick cannot', move(old_cem, 'in', 1, supplier='x', who=plain).status_code == 403)

# ======================================================================
section('Backup after a day of real work')
b = c.post('/backup/create', headers=ADMIN)
ck('a backup can be taken', b.status_code == 200)
ck('and downloaded', c.get('/backup/latest/download?token=' + c.post('/auth/download-token', headers=ADMIN).json()['token']).status_code == 200)
final = live()
ck(f'attendance and payroll still untouched at the end: {final}', final == before, final)

print('\n' + ('GO-LIVE REHEARSAL CLEAN' if not FAIL else f'{len(FAIL)} FAILED: ' + '; '.join(FAIL)))
sys.exit(1 if FAIL else 0)

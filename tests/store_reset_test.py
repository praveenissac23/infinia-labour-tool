"""Clearing the store must not cost a single day of live attendance.

Run: cd app && DATABASE_URL=sqlite:////tmp/sr.db python3 ../tests/store_reset_test.py

The store went live on its own, months after attendance did, so the
practice entries in the store had to be wiped while real payroll data
sat in the same database. This builds both sides, clears the store, and
checks the attendance side is untouched to the row - then checks the
numbering starts again from the first number, twice in a row, because
the id counter does not go back when rows are deleted.
"""
import sys
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main

db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'),
                   full_name='Administrator', role='admin'))
db.add(models.User(username='amal', hashed_password=auth.hash_password('p'),
                   full_name='Amal', role='office', permissions='store,storekeeper'))
for no, nm in (('101', 'Rajan'), ('102', 'Suresh'), ('103', 'Anil')):
    db.add(models.Employee(emp_no=no, name=nm, trade='Mason', total_salary=2500,
                           basic_salary=1500, active=True))
db.add(models.Site(code='904', active=True))
db.add(models.Site(code='901', active=True))
db.add(models.Engineer(name='Febiyan', mobile='0501234567', active=True))
db.commit(); db.close()

c = TestClient(main.app)
def tok(u):
    return {'Authorization': 'Bearer ' +
            c.post('/auth/login', data={'username': u, 'password': 'p'}).json()['access_token']}
H = tok('admin')
KEEPER = tok('amal')

FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{x}]'))
    if not ok: FAIL.append(l)

# ---- A month of live attendance, and a salary adjustment on top -------
rows = []
for day in range(1, 29):
    for no in ('101', '102', '103'):
        rows.append({'emp_no': no, 'full_date': f'2026-08-{day:02d}', 'am': 'Present',
                     'pm': 'Present', 'site': '904', 'engineer': 'Febiyan',
                     'ot': 2, 'bh': 0, 'comments': ''})
c.post('/attendance/save', json={'month_year': 'August 2026', 'rows': rows}, headers=H)
sums = c.get('/summaries/August 2026', headers=H).json()
assert sums, 'no payroll summaries were produced - fixture is wrong'
c.post(f"/summaries/{sums[0]['id']}/adjustments",
       json={'description': 'advance', 'amount': 150, 'is_deduction': True}, headers=H)

# ---- A store full of practice entries --------------------------------
it1 = c.post('/store/items', json={'name': 'Cement OPC', 'unit': 'bag',
                                   'item_type': 'consumable', 'reorder_level': 20}, headers=H).json()
it2 = c.post('/store/items', json={'name': 'Rebar 12mm', 'unit': 'pcs',
                                   'item_type': 'consumable'}, headers=H).json()
mr = c.post('/store/requests', json={
    'site': '904', 'requested_by': 'Febiyan', 'needed_by': '2026-09-05', 'urgency': 'urgent',
    'notes': 'practice', 'lines': [{'item_id': it1['id'], 'qty_requested': 100, 'unit': 'bag',
    'purpose': 'slab', 'item_type': 'consumable', 'description': '', 'est_cost': 0, 'notes': ''}]},
    headers=H).json()
ck('practice request is MR-0001', mr['ref'] == 'MR-0001', mr['ref'])
c.post(f"/store/requests/{mr['id']}/status", json={'status': 'ordered', 'supplier': 'Al Raha Trading',
    'contact_person': 'Biju', 'phone': '050090890', 'expected_on': '2026-09-02'}, headers=H)
c.post(f"/store/requests/{mr['id']}/receive-bulk", json={'supplier': 'Al Raha Trading',
    'reference': 'INV-1', 'notes': '', 'received_on': '2026-08-28',
    'lines': [{'line_id': mr['lines'][0]['id'], 'qty': 100}]}, headers=H)
mv_in = c.post('/store/movements', json={'item_id': it2['id'], 'kind': 'in', 'qty': 700,
                                         'location': '', 'supplier': 'Gateway',
                                         'moved_on': '2026-08-20'}, headers=H)
ck('rebar received into the central store', mv_in.status_code == 200, mv_in.text[:200])
# The cement was delivered straight to 904, because a delivery books to
# the site that asked for it - so it is issued FROM 904, not from the
# central store, which holds none of it.
mv_out = c.post('/store/movements', json={'item_id': it2['id'], 'kind': 'out', 'qty': 40,
                                          'from_location': '', 'location': '904',
                                          'incharge': 'Akhil', 'moved_on': '2026-08-29'}, headers=H)
ck('rebar issued to the site', mv_out.status_code == 200, mv_out.text[:200])
# And the guard that made this test honest in the first place: the
# central store has no cement, so it cannot issue any.
over = c.post('/store/movements', json={'item_id': it1['id'], 'kind': 'out', 'qty': 40,
                                        'from_location': '', 'location': '904',
                                        'incharge': 'Akhil', 'moved_on': '2026-08-29'}, headers=H)
ck('issuing stock the central store does not hold is refused', over.status_code == 400,
   over.status_code)
po = c.post('/store/purchase/orders', json={
    'order_date': '2026-08-25', 'supplier_name': 'Al Raha Trading', 'request_id': mr['id'],
    'terms': 'Due on Receipt', 'lines': [{'item_id': it1['id'], 'description': 'Cement OPC',
    'qty': 100, 'unit': 'bag', 'rate': 16.0, 'tax_pct': 5.0}]}, headers=H)
ck('practice LPO raised', po.status_code == 200, po.text[:200])

# ---- What the live side looked like before we touched anything -------
def live_snapshot():
    d = database.SessionLocal()
    try:
        return {
            'attendance days': d.query(models.DailyRow).count(),
            'payroll summaries': d.query(models.EmployeeSummary).count(),
            'salary adjustments': d.query(models.SalaryAdjustment).count(),
            'workers': d.query(models.Employee).count(),
            'sites': d.query(models.Site).count(),
            'engineers': d.query(models.Engineer).count(),
            'logins': d.query(models.User).count(),
        }
    finally:
        d.close()

before = live_snapshot()
ck('attendance really is populated', before['attendance days'] == 84, before['attendance days'])

# ---- Guards before the real thing ------------------------------------
ck('the wrong phrase is refused',
   c.post('/backup/store-reset', json={'confirm': 'clear store'}, headers=H).status_code == 400)
ck('a store keeper cannot clear the store',
   c.post('/backup/store-reset', json={'confirm': 'CLEAR STORE'}, headers=KEEPER).status_code in (401, 403))
ck('nothing was cleared by the refused attempts',
   len(c.get('/store/requests', headers=H).json()) == 1)

# ---- Clear the store, keeping the master lists -----------------------
r = c.post('/backup/store-reset', json={'confirm': 'CLEAR STORE'}, headers=H)
ck('store reset runs', r.status_code == 200, r.text[:300])
out = r.json()

ck('stock movements gone', not c.get('/store/movements', headers=H).json())
ck('material requests gone', not c.get('/store/requests', headers=H).json())
ck('purchase orders gone', not c.get('/store/purchase/orders', headers=H).json())
ck('every stock figure is zero',
   all(not s['central'] and not s['out_at_sites'] for s in c.get('/store/stock', headers=H).json()))
ck('material list kept', len(c.get('/store/items', headers=H).json()) == 2)
sup_kept = sorted(s['name'] for s in c.get('/store/suppliers', headers=H).json())
ck('supplier list kept', sup_kept == ['Al Raha Trading', 'Gateway'], sup_kept)

after = live_snapshot()
for k in before:
    ck(f'{k} untouched: {before[k]}', before[k] == after[k], f'{before[k]} -> {after[k]}')
ck('August attendance still reads back',
   len(c.get('/attendance/2026-08-15', headers=H).json()) == 3)
ck('the reply says attendance survived',
   out['kept']['attendance days'] == before['attendance days'], out['kept'])

# ---- A backup was taken first, and it holds the cleared store --------
import json as _j
d = database.SessionLocal()
b = (d.query(models.Backup).filter(models.Backup.trigger == 'before-store-reset')
     .order_by(models.Backup.id.desc()).first())
ck('a backup was taken before clearing', b is not None)
if b:
    raw = main._backup_json(b)
    ck('that backup holds the cleared movements', len(raw.get('store_movements', [])) >= 3,
       len(raw.get('store_movements', [])))
    ck('that backup still holds the live attendance',
       len(raw.get('daily_rows', [])) == before['attendance days'],
       len(raw.get('daily_rows', [])))
    ck('that backup holds the cleared orders', len(raw.get('purchase_orders', [])) == 1)
d.close()

# ---- Numbering starts again, and keeps going straight ----------------
# Each asks for a different quantity on purpose: an identical request
# sent twice within ten minutes is treated as a double-click and returns
# the first one, which is right, and would hide the numbering here.
def new_request(qty):
    return c.post('/store/requests', json={
        'site': '901', 'requested_by': 'Febiyan', 'needed_by': '2026-09-20', 'urgency': 'normal',
        'notes': f'live {qty}', 'lines': [{'item_id': it1['id'], 'qty_requested': qty,
        'unit': 'bag', 'purpose': 'real', 'item_type': 'consumable', 'description': '',
        'est_cost': 0, 'notes': ''}]}, headers=H).json()

first, second, third = new_request(5), new_request(6), new_request(7)
ck('first live request is MR-0001', first['ref'] == 'MR-0001', first['ref'])
ck('second live request is MR-0002', second['ref'] == 'MR-0002', second['ref'])
ck('third live request is MR-0003', third['ref'] == 'MR-0003', third['ref'])

nxt = c.get('/store/purchase/next-no', headers=H).json()
ck('orders start again at IC/LPO/20260100', nxt['ref'] == 'IC/LPO/20260100', nxt)

# ---- And the deeper option really does empty the lists ---------------
r2 = c.post('/backup/store-reset', json={'confirm': 'CLEAR STORE',
                                         'clear_materials': True, 'clear_suppliers': True}, headers=H)
ck('reset with both boxes ticked runs', r2.status_code == 200, r2.text[:200])
ck('material list emptied when asked', not c.get('/store/items', headers=H).json())
ck('supplier list emptied when asked', not c.get('/store/suppliers', headers=H).json())
last = live_snapshot()
ck('attendance still untouched after the deeper clear', last == before, f'{before} -> {last}')

print('\n' + ('ALL PASS' if not FAIL else f'{len(FAIL)} FAILED: ' + '; '.join(FAIL)))
sys.exit(1 if FAIL else 0)

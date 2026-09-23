"""Scaffolding that belongs to somebody else, tracked as such.

Run: cd app && DATABASE_URL=sqlite:////tmp/hire.db python3 ../tests/hire_tracking_test.py

The yard holds the same standards and ledgers whether Infinia bought
them or hired them, and until the ledger could say which, the two piles
were one number. Hired kit went out with ours, came back short, and the
argument happened weeks later against an invoice with nothing to put
against it.

The fix is one dimension - whose - carried on every movement. This
walks the whole cycle on it: owned stock and hired stock of the same
material side by side, issued to a site, partly returned, some declared
lost, settled on a signed note, and the position correct at every step.
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
db.add(models.User(username='site', hashed_password=auth.hash_password('p'),
                   full_name='Site Engineer', role='office', permissions='store'))
for no, nm in (('101', 'Rajan'), ('102', 'Suresh')):
    db.add(models.Employee(emp_no=no, name=nm, trade='Mason', total_salary=2500,
                           basic_salary=1500, active=True))
db.add(models.Site(code='901', active=True))
db.add(models.Engineer(name='Febiyan', mobile='0501234567', active=True))
db.commit(); db.close()

c = TestClient(main.app, raise_server_exceptions=False)
def tok(u):
    return {'Authorization': 'Bearer ' +
            c.post('/auth/login', data={'username': u, 'password': 'p'}).json()['access_token']}
H, SITE = tok('admin'), tok('site')

FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{str(x)[:200]}]'))
    if not ok: FAIL.append(l)

def stock_row(item_id):
    return next(s for s in c.get('/store/stock', headers=H).json() if s['item_id'] == item_id)

# ---- A month of live attendance, so we can prove we never touch it ---
rows = [{'emp_no': no, 'full_date': f'2026-08-{d:02d}', 'am': 'Present', 'pm': 'Present',
         'site': '901', 'engineer': 'Febiyan', 'ot': 2, 'bh': 0, 'comments': ''}
        for d in range(1, 15) for no in ('101', '102')]
c.post('/attendance/save', json={'month_year': 'August 2026', 'rows': rows}, headers=H)
def payroll_snapshot():
    d = database.SessionLocal()
    try:
        return (d.query(models.DailyRow).count(), d.query(models.EmployeeSummary).count(),
                d.query(models.Employee).count())
    finally:
        d.close()
before_payroll = payroll_snapshot()
ck('attendance is populated before we start', before_payroll[0] == 28, before_payroll)

std = c.post('/store/items', json={'name': 'Standard 3.0m', 'unit': 'pcs',
                                   'item_type': 'returnable'}, headers=H).json()
ldg = c.post('/store/items', json={'name': 'Ledger 1.8m', 'unit': 'pcs',
                                   'item_type': 'returnable'}, headers=H).json()

# ---- Before anything is hired, the store is not asked whose it is ----
c.post('/store/movements', json={'item_id': std['id'], 'kind': 'in', 'qty': 180,
                                 'location': '', 'moved_on': '2026-08-01'}, headers=H)
row = stock_row(std['id'])
ck('a store with nothing on hire carries no owner split', 'rented' not in row, list(row))

# ---- Hire 60 of the same standard in from a trader -------------------
r = c.post('/store/hire/in', json={
    'supplier_name': 'Al Raha Scaffolding', 'received_on': '2026-08-05',
    'reference': 'DN-88', 'incharge': 'amal',
    'lines': [{'item_id': std['id'], 'qty': 60}, {'item_id': ldg['id'], 'qty': 240}]}, headers=H)
ck('the hire is booked in', r.status_code == 200, r.text[:200])

row = stock_row(std['id'])
ck('the total counts both piles', row['total'] == 240, row)
ck('and says 180 are ours', row['owned'] == 180, row)
ck('and 60 are hired', row['rented'] == 60, row)
ck('naming the trader they belong to',
   row['rented_from'].get('Al Raha Scaffolding') == 60, row['rented_from'])

hire = c.get('/store/hire', headers=H).json()
ck('the hire list shows one trader', len(hire['suppliers']) == 1, hire)
sid = hire['suppliers'][0]['supplier_id']
ck('with both materials on it', hire['suppliers'][0]['lines'] == 2, hire['suppliers'][0])
ck('and the days it has been out', hire['suppliers'][0]['items'][0]['days'] > 0,
   hire['suppliers'][0]['items'][0])

# ---- The guard that stops the mix-up ---------------------------------
over = c.post('/store/movements', json={'item_id': std['id'], 'kind': 'out', 'qty': 100,
                                        'from_location': '', 'location': '901',
                                        'owner_id': sid, 'moved_on': '2026-08-10'}, headers=H)
ck('hired stock cannot be issued beyond what is hired', over.status_code == 400, over.status_code)
ck('and the refusal names the trader', 'Al Raha' in over.text, over.text[:200])

over2 = c.post('/store/movements', json={'item_id': std['id'], 'kind': 'out', 'qty': 200,
                                         'from_location': '', 'location': '901',
                                         'moved_on': '2026-08-10'}, headers=H)
ck('and our own pile cannot borrow from the hired one', over2.status_code == 400, over2.status_code)

# ---- Issue hired scaffolding to a site, where it is still the trader's
out = c.post('/store/movements', json={'item_id': std['id'], 'kind': 'out', 'qty': 50,
                                       'from_location': '', 'location': '901',
                                       'owner_id': sid, 'incharge': 'Akhil',
                                       'moved_on': '2026-08-10'}, headers=H)
ck('hired scaffolding issues to a site', out.status_code == 200, out.text[:200])
row = stock_row(std['id'])
ck('it is still on hire once it is standing on site', row['rented'] == 60, row)
ck('and still counted at the site', row['out_at_sites'] == 50, row)

# ---- The return note -------------------------------------------------
note = c.post('/store/returns', json={
    'supplier_id': sid, 'return_date': '2026-09-01', 'driver': 'Rajan', 'vehicle': 'DXB 1234',
    'lines': [
        {'item_id': std['id'], 'qty_returned': 56, 'qty_short': 4, 'short_reason': 'lost'},
        {'item_id': ldg['id'], 'qty_returned': 200, 'qty_short': 6, 'short_reason': 'damaged'},
    ]}, headers=H)
ck('the return note is raised', note.status_code == 200, note.text[:250])
note = note.json()
ck('numbered from RN-0001', note['ref'] == 'RN-0001', note['ref'])
ck('totalling what goes back', note['total_returned'] == 256, note)
ck('and what is short', note['total_short'] == 10, note)
ck('the ledger line still shows what stays on hire',
   [l for l in note['lines'] if l['item_id'] == ldg['id']][0]['still_on_hire'] == 34, note['lines'])

bad = c.post('/store/returns', json={'supplier_id': sid, 'return_date': '2026-09-01',
    'lines': [{'item_id': std['id'], 'qty_returned': 500}]}, headers=H)
ck('a note cannot return more than is on hire', bad.status_code == 400, bad.status_code)
noreason = c.post('/store/returns', json={'supplier_id': sid, 'return_date': '2026-09-01',
    'lines': [{'item_id': std['id'], 'qty_returned': 1, 'qty_short': 2}]}, headers=H)
ck('a shortfall without a reason is refused', noreason.status_code == 400, noreason.status_code)

# ---- Nothing moves until the trader has signed -----------------------
row = stock_row(std['id'])
ck('raising the note moves no stock', row['rented'] == 60, row)

t = c.post('/auth/download-token', headers=H).json()['token']
pdf = c.get(f"/export/store/return/{note['id']}?token={t}&format=pdf")
ck('the note prints as a PDF for the driver',
   pdf.status_code == 200 and pdf.content[:4] == b'%PDF', pdf.status_code)
xl = c.get(f"/export/store/return/{note['id']}?token={t}&format=excel")
ck('and as an Excel copy', xl.status_code == 200 and len(xl.content) > 3000, xl.status_code)

# ---- The signed copy comes back --------------------------------------
cf = c.post(f"/store/returns/{note['id']}/confirm",
            json={'received_by': 'Biju', 'confirmed_on': '2026-09-02'}, headers=H)
ck('the note settles when it comes back signed', cf.status_code == 200, cf.text[:200])
ck('and reports the shortfall', cf.json()['total_short'] == 10, cf.json())

row = stock_row(std['id'])
ck('the hired standards are off our books', row.get('rented', 0) == 0, row)
ck('our own 180 are untouched', row['owned' if 'owned' in row else 'total'] == 180, row)
ck('and the total is our own again', row['total'] == 180, row)

led = stock_row(ldg['id'])
ck('the ledger material still shows 34 on hire', led['rented'] == 34, led)

hire = c.get('/store/hire', headers=H).json()
ck('the hire list now shows only what is left',
   sum(g['lines'] for g in hire['suppliers']) == 1, hire)

# ---- The settlement comes off where the material actually stood ------
# Sixty standards arrived in the yard and fifty went up at a site. A
# return settled against the yard alone would drive it to minus fifty
# while the site still showed the rest: the total nets out and the
# ledger quietly stops describing anything real.
d = database.SessionLocal()
positions = {k: v for k, v in main._stock_map(d, by_owner=True).items()
             if k[2] == sid and abs(v) > 1e-9}
d.close()
ck('no location is left holding a negative of the trader\'s stock',
   not any(v < -1e-9 for v in positions.values()), positions)
ck('the settled standards are gone from every location, not just netted',
   not any(k[0] == std['id'] for k in positions), positions)

again = c.post(f"/store/returns/{note['id']}/confirm", json={'received_by': 'Biju'}, headers=H)
ck('a settled note cannot be settled twice', again.status_code == 400, again.status_code)
edit = c.put(f"/store/returns/{note['id']}", json={'supplier_id': sid, 'return_date': '2026-09-01',
    'lines': [{'item_id': ldg['id'], 'qty_returned': 1}]}, headers=H)
ck('and cannot be edited after signing', edit.status_code == 400, edit.status_code)

# ---- The write-off is on the ledger, against the right owner ---------
movs = c.get('/store/movements', headers=H).json()
lost = [m for m in movs if m['kind'] == 'lost']
ck('the shortfall is written off on the ledger', len(lost) == 2, len(lost))
ck('against the trader who owned it', all(m['owner_id'] == sid for m in lost), lost)
ck('referencing the note both sides signed',
   all(m['reference'] == 'RN-0001' for m in lost), lost)

# ---- Permission, and the live side ------------------------------------
ck('someone without the keeper right cannot book a hire in',
   c.post('/store/hire/in', json={'supplier_name': 'X', 'received_on': '2026-09-01',
          'lines': [{'item_id': std['id'], 'qty': 1}]}, headers=SITE).status_code in (401, 403))

after_payroll = payroll_snapshot()
ck(f'attendance and payroll untouched throughout: {before_payroll}',
   before_payroll == after_payroll, f'{before_payroll} -> {after_payroll}')
ck('August attendance still reads back',
   len(c.get('/attendance/2026-08-05', headers=H).json()) == 2)

# ---- Stock booked under the wrong name, put right --------------------
# Material can enter the store by several doors, and one of them did not
# ask whose it was - so a hired quantity sat in the owned pile and the
# hire list stayed empty. Correcting it must not invent a delivery: the
# quantity changes hands where it stands and the total never moves.
prop = c.post('/store/items', json={'name': 'L.D Props 5.0m', 'unit': 'pcs',
                                    'item_type': 'returnable'}, headers=H).json()
c.post('/store/items/opening', json={'lines': [
    {'item_id': prop['id'], 'item_type': 'asset', 'qty': 150}]}, headers=H)
before_total = stock_row(prop['id'])['total']
ck('the wrongly-owned stock is there as ours', before_total == 150, before_total)
ck('and shows on no hire list', not any(
   i['item_id'] == prop['id'] for g in c.get('/store/hire', headers=H).json()['suppliers']
   for i in g['items']))

fix = c.post('/store/hire/reassign', json={
    'item_id': prop['id'], 'qty': 150, 'location': '',
    'from_owner_name': '', 'to_owner_name': 'Al Raha Scaffolding'}, headers=H)
ck('the owner can be corrected', fix.status_code == 200, fix.text[:200])
row = stock_row(prop['id'])
ck('the total did not move - nothing was received', row['total'] == before_total, row)
ck('but it is now hired, not ours', row['rented'] == 150 and row['owned'] == 0, row)
onh = [i for g in c.get('/store/hire', headers=H).json()['suppliers']
       for i in g['items'] if i['item_id'] == prop['id']]
ck('it appears on the hire list', len(onh) == 1 and onh[0]['qty'] == 150, onh)
ck('carrying the date it went under that name', bool(onh[0]['since']), onh[0])

ck('more than is held cannot be reassigned',
   c.post('/store/hire/reassign', json={'item_id': prop['id'], 'qty': 999,
          'from_owner_name': '', 'to_owner_name': 'Ghantoot'}, headers=H).status_code == 400)
ck('and reassigning to the same name is refused',
   c.post('/store/hire/reassign', json={'item_id': prop['id'], 'qty': 1,
          'from_owner_name': 'Al Raha Scaffolding',
          'to_owner_name': 'Al Raha Scaffolding'}, headers=H).status_code == 400)

back = c.post('/store/hire/reassign', json={
    'item_id': prop['id'], 'qty': 50, 'from_owner_name': 'Al Raha Scaffolding',
    'to_owner_name': ''}, headers=H)
ck('it can be put back to ours as well', back.status_code == 200, back.text[:200])
row = stock_row(prop['id'])
ck('leaving the split right', row['owned'] == 50 and row['rented'] == 100, row)
ck('and the total still untouched', row['total'] == before_total, row)

# ---- Added straight from the material list, the way it reads --------
# A material marked Rental is hired from somebody, and the form asks who
# on the same screen. Taking that name is what the person adding 150
# ledgers there expects; anything else leaves them looking at an empty
# hire list wondering what they did wrong.
mat = c.post('/store/items', json={'name': 'Cantilever Frame', 'unit': 'pcs',
                                   'item_type': 'rental',
                                   'rental_supplier': 'Ghantoot Equipment Rental',
                                   'opening_qty': 20}, headers=H)
ck('a rental material added from the material list saves', mat.status_code == 200, mat.text[:200])
frame = next(s for s in c.get('/store/stock', headers=H).json() if s['name'] == 'Cantilever Frame')
ck('its quantity is hired, not ours', frame['rented'] == 20 and frame['owned'] == 0, frame)
ck('from the rental supplier named on the form',
   frame['rented_from'].get('Ghantoot Equipment Rental') == 20, frame['rented_from'])
listed = [i for g in c.get('/store/hire', headers=H).json()['suppliers']
          for i in g['items'] if i['name'] == 'Cantilever Frame']
ck('and it is on the hire list straight away', len(listed) == 1 and listed[0]['qty'] == 20, listed)

nameless = c.post('/store/items', json={'name': 'Spigot Nut & Bolt', 'unit': 'pcs',
                                        'item_type': 'rental', 'opening_qty': 40}, headers=H)
ck('a rental material with no supplier named still saves', nameless.status_code == 200,
   nameless.text[:160])
loose = [i for g in c.get('/store/hire', headers=H).json()['suppliers']
         for i in g['items'] if i['name'] == 'Spigot Nut & Bolt']
ck('and it still shows on the rental list - rented is rented',
   len(loose) == 1 and loose[0]['qty'] == 40, loose)
ck('under a name that says the job is unfinished',
   loose and loose[0]['supplier'] == '(no supplier set)', loose)
row = next(s for s in c.get('/store/stock', headers=H).json() if s['name'] == 'Spigot Nut & Bolt')
ck('and the stock list counts it as rented, not ours', row['rented'] == 40, row)

print('\n' + ('ALL PASS' if not FAIL else f'{len(FAIL)} FAILED: ' + '; '.join(FAIL)))
sys.exit(1 if FAIL else 0)

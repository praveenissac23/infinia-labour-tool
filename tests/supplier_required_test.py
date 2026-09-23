"""A supplier on the master carries everything an order prints, or it
is not saved.

Run: cd app && DATABASE_URL=sqlite:////tmp/sq.db python3 ../tests/supplier_required_test.py

Half a supplier record is only ever found later, with a purchase order
already waiting to go out and a blank where the TRN should be. The
master screen, the edit, and the spreadsheet import all hold the same
line - otherwise the quickest way round the rule would be to import the
row instead of typing it.

Raising an order for a trader not yet on file still works: that is how
a name is learned in the first place, and the master screen shows what
is still missing rather than refusing the order.
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
db.commit(); db.close()

c = TestClient(main.app, raise_server_exceptions=False)
H = {'Authorization': 'Bearer ' + c.post('/auth/login',
     data={'username': 'admin', 'password': 'p'}).json()['access_token']}

FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{str(x)[:200]}]'))
    if not ok: FAIL.append(l)

FULL = {'name': 'Al Raha Trading LLC', 'contact_person': 'Biju', 'phone': '0500908900',
        'trn': '100200300400500', 'email': 'sales@alraha.ae', 'payment_terms': 'Net 30'}

# ---- Every field is needed, and the reply says which is missing ------
for field, word in (('contact_person', 'contact person'), ('phone', 'phone number'),
                    ('trn', 'TRN'), ('email', 'email'), ('payment_terms', 'payment terms')):
    partial = dict(FULL); partial[field] = ''
    r = c.post('/store/suppliers', json=partial, headers=H)
    ck(f'saving without {word} is refused', r.status_code == 400, f'{r.status_code} {r.text[:120]}')
    ck(f'and the message names the {word}', word.split()[0].lower() in r.text.lower(), r.text[:120])

r = c.post('/store/suppliers', json={'name': ''}, headers=H)
ck('a nameless supplier is refused', r.status_code == 400, r.status_code)

ck('nothing was saved by any refused attempt',
   len(c.get('/store/suppliers', headers=H).json()) == 0,
   c.get('/store/suppliers', headers=H).json())

# ---- The complete record saves ---------------------------------------
r = c.post('/store/suppliers', json=FULL, headers=H)
ck('the complete supplier saves', r.status_code == 200, r.text[:200])
got = c.get('/store/suppliers', headers=H).json()
ck('and every field came back', len(got) == 1 and all(got[0][k] for k in
   ('contact_person', 'phone', 'trn', 'email', 'payment_terms')), got)

# ---- Editing holds the same line, and actually saves the three that
#      used to be dropped --------------------------------------------
sid = got[0]['id']
half = dict(FULL); half['trn'] = ''
ck('an edit that empties the TRN is refused',
   c.put(f'/store/suppliers/{sid}', json=half, headers=H).status_code == 400)

changed = dict(FULL, trn='999888777666555', email='accounts@alraha.ae',
               payment_terms='Net 45')
r = c.put(f'/store/suppliers/{sid}', json=changed, headers=H)
ck('a complete edit is accepted', r.status_code == 200, r.text[:200])
after = c.get('/store/suppliers', headers=H).json()[0]
ck('the new TRN really was saved', after['trn'] == '999888777666555', after['trn'])
ck('the new email really was saved', after['email'] == 'accounts@alraha.ae', after['email'])
ck('the new terms really were saved', after['payment_terms'] == 'Net 45', after['payment_terms'])

# ---- An order for a trader not yet on file still works ---------------
item = c.post('/store/items', json={'name': 'Cement OPC 50kg', 'unit': 'bag',
                                    'item_type': 'consumable'}, headers=H).json()
po = c.post('/store/purchase/orders', json={
    'order_date': '2026-09-21', 'supplier_name': 'Brand New Trading LLC',
    'lines': [{'item_id': item['id'], 'description': 'Cement OPC 50kg',
               'qty': 10, 'unit': 'bag', 'rate': 16.5, 'tax_pct': 5}]}, headers=H)
ck('an order can still be raised for a new trader', po.status_code == 200, po.text[:200])
names = [s['name'] for s in c.get('/store/suppliers', headers=H).json()]
ck('and that trader is on the master to be completed',
   any('Brand New' in n for n in names), names)

# ---- The spreadsheet cannot slip an incomplete row past --------------
import io
from openpyxl import Workbook
wb = Workbook(); ws = wb.active
ws.append(['Name', 'Contact Person', 'Phone', 'TRN', 'Email', 'Payment Terms'])
ws.append(['Gateway Trading', 'Anil', '0501112222', '100100100100100', 'a@gw.ae', 'Net 30'])
ws.append(['Half Filled Trading', 'Sam', '0503334444', '', '', ''])
buf = io.BytesIO(); wb.save(buf)
r = c.post('/store/suppliers/import',
           files={'file': ('suppliers.xlsx', buf.getvalue(),
                           'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},
           headers=H)
ck('the import runs', r.status_code == 200, r.text[:200])
out = r.json()
ck('the complete row was taken', out['created'] == 1, out)
ck('the half-filled row was left out', out['skipped'] == 1, out)
ck('and it is named so the sheet can be fixed',
   any('Half Filled' in x for x in out.get('incomplete', [])), out.get('incomplete'))
ck('the incomplete trader is not on the master',
   not any('Half Filled' in s['name'] for s in c.get('/store/suppliers', headers=H).json()))

print('\n' + ('ALL PASS' if not FAIL else f'{len(FAIL)} FAILED: ' + '; '.join(FAIL)))
sys.exit(1 if FAIL else 0)

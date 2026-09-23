"""Reissuing a purchase order corrects it in place - same number, same
date first raised, everything else replaced.

Run: cd app && DATABASE_URL=sqlite:////tmp/le.db python3 ../tests/lpo_edit_test.py

An order saved too soon, or missing a line, should not have to become a
second order with its own number - that is confusing on the supplier's
side and doubles the register for nothing. Editing replaces the order's
own content the way editing any other document does.
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
                   full_name='Amal', role='office', permissions='store'))
db.add(models.Site(code='901', active=True))
db.commit(); db.close()

c = TestClient(main.app, raise_server_exceptions=False)
def tok(u):
    return {'Authorization': 'Bearer ' +
            c.post('/auth/login', data={'username': u, 'password': 'p'}).json()['access_token']}
H = tok('admin')
NOKEEPER = tok('amal')

FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{x}]'))
    if not ok: FAIL.append(l)

item = c.post('/store/items', json={'name': 'Cement OPC 50kg', 'unit': 'bag',
                                    'item_type': 'consumable'}, headers=H).json()

po = c.post('/store/purchase/orders', json={
    'order_date': '2026-09-01', 'supplier_name': 'Al Raha Trading LLC',
    'lines': [{'item_id': item['id'], 'description': 'Cement OPC 50kg',
               'qty': 100, 'unit': 'bag', 'rate': 16.5, 'tax_pct': 5}]}, headers=H)
ck('the order can be raised', po.status_code == 200, po.text[:200]); po = po.json()
orig_ref, orig_no, orig_date = po['ref'], po['po_no'], po['order_date']

# ---- Without permission, an edit is refused --------------------------
nope = c.put(f"/store/purchase/orders/{po['id']}", json={
    'order_date': orig_date, 'supplier_name': 'Al Raha Trading LLC',
    'lines': [{'description': 'Cement OPC 50kg', 'qty': 100, 'unit': 'bag', 'rate': 16.5}]},
    headers=NOKEEPER)
ck('a user without the screen cannot edit it', nope.status_code in (401, 403), nope.status_code)

# ---- Add a line and fix a rate that was saved wrong -------------------
edited = c.put(f"/store/purchase/orders/{po['id']}", json={
    'order_date': orig_date, 'terms': 'Net 30', 'supplier_name': 'Al Raha Trading LLC',
    'supplier_trn': '100200300400500', 'plot_no': 'PLOT-1', 'notes': 'corrected',
    'lines': [
        {'item_id': item['id'], 'description': 'Cement OPC 50kg', 'qty': 100, 'unit': 'bag', 'rate': 17.0, 'tax_pct': 5},
        {'description': 'Rebar 12mm', 'qty': 50, 'unit': 'pcs', 'rate': 9.5, 'tax_pct': 5},
    ]}, headers=H)
ck('the edit is accepted', edited.status_code == 200, edited.text[:300])
edited = edited.json()
ck('the same number is kept', edited['po_no'] == orig_no, edited['po_no'])
ck('the same reference is kept', edited['ref'] == orig_ref, edited['ref'])
ck('the same order date is kept', edited['order_date'] == orig_date, edited['order_date'])
ck('the rate correction took', edited['lines'][0]['rate'] == 17.0, edited['lines'][0]['rate'])
ck('the new line was added', len(edited['lines']) == 2, len(edited['lines']))
ck('a field only edit supplied took', edited['terms'] == 'Net 30', edited['terms'])

# ---- The register itself shows the correction, not a second order ----
reg = c.get('/store/purchase/orders', headers=H).json()
ck('still only one order on the register', len(reg) == 1, len(reg))
ck('the register copy matches the correction', reg[0]['lines'] == 2, reg[0]['lines'])

# ---- The register marks it edited, and only after a real edit --------
def reg_row(ref):
    rows = c.get('/store/purchase/report?group_by=order&measures=total&status=all',
                 headers=H).json()['rows']
    return next((r for r in rows if r['label'] == ref), None)

row = reg_row(orig_ref)
ck('the edited order is on the register', row is not None, row)
ck('and the register marks it edited', row and row['edited'] is True, row)
ck('with the date it was corrected', row and row['edited_on'], row)

fresh = c.post('/store/purchase/orders', json={
    'order_date': '2026-09-03', 'supplier_name': 'Metrabar Trading',
    'lines': [{'description': 'Binding wire', 'qty': 5, 'unit': 'kg', 'rate': 12}]}, headers=H).json()
ck('an order never edited is not marked edited',
   reg_row(fresh['ref'])['edited'] is False, reg_row(fresh['ref']))

# ---- Editing without a supplier or without lines is refused ----------
bad1 = c.put(f"/store/purchase/orders/{po['id']}", json={
    'order_date': orig_date, 'supplier_name': '', 'lines': [{'description': 'x', 'qty': 1, 'rate': 1}]}, headers=H)
ck('an edit with no supplier is refused', bad1.status_code == 400, bad1.status_code)
bad2 = c.put(f"/store/purchase/orders/{po['id']}", json={
    'order_date': orig_date, 'supplier_name': 'Al Raha Trading LLC', 'lines': []}, headers=H)
ck('an edit with no lines is refused', bad2.status_code == 400, bad2.status_code)

# ---- A cancelled order cannot be edited back to life ------------------
po2 = c.post('/store/purchase/orders', json={
    'order_date': '2026-09-02', 'supplier_name': 'Gateway Trading',
    'lines': [{'description': 'Plywood', 'qty': 10, 'unit': 'sheet', 'rate': 45}]}, headers=H).json()
c.post(f"/store/purchase/orders/{po2['id']}/cancel", headers=H)
blocked = c.put(f"/store/purchase/orders/{po2['id']}", json={
    'order_date': '2026-09-02', 'supplier_name': 'Gateway Trading',
    'lines': [{'description': 'Plywood', 'qty': 20, 'unit': 'sheet', 'rate': 45}]}, headers=H)
ck('a cancelled order cannot be edited', blocked.status_code == 400, blocked.status_code)

# ---- Editing a missing order 404s -------------------------------------
missing = c.put('/store/purchase/orders/999999', json={
    'order_date': orig_date, 'supplier_name': 'Al Raha Trading LLC',
    'lines': [{'description': 'x', 'qty': 1, 'rate': 1}]}, headers=H)
ck('editing an order that does not exist 404s', missing.status_code == 404, missing.status_code)

# ---- The reissued order still prints ----------------------------------
tok_dl = c.post('/auth/download-token', headers=H).json()['token']
pdf = c.get(f"/export/purchase/{po['id']}?token={tok_dl}&format=pdf")
ck('the corrected order still prints', pdf.status_code == 200 and pdf.content[:4] == b'%PDF', pdf.status_code)

print('\n' + ('ALL PASS' if not FAIL else f'{len(FAIL)} FAILED: ' + '; '.join(FAIL)))
sys.exit(1 if FAIL else 0)

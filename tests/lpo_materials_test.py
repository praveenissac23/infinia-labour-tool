"""Every material on an LPO is on the material list.

Run: cd app && rm -f /tmp/lm.db && DATABASE_URL=sqlite:////tmp/lm.db python3 ../tests/lpo_materials_test.py
"""
import sys
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main

db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Administrator', role='admin'))
db.add(models.StoreItem(code='ITM1', name='Cement OPC 50kg', unit='bag', item_type='consumable', active=True))
db.add(models.Site(code='913', active=True))
db.commit(); db.close()

c = TestClient(main.app)
H = {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': 'admin', 'password': 'p'}).json()['access_token']}
FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{x}]'))
    if not ok: FAIL.append(l)

body = {'supplier_name': 'Al Hassai', 'order_date': '2026-10-05', 'lines': [
    {'description': 'cement opc 50kg', 'qty': 10, 'unit': 'bag', 'rate': 14.5},        # on the list, spelt differently
    {'description': 'Plywood 18mm', 'qty': 50, 'unit': 'sheet', 'rate': 100},          # new
    {'description': 'Binding  Wire (MS Wire)', 'qty': 2, 'unit': 'roll', 'rate': 110}, # new, double space
]}
r = c.post('/store/purchase/orders', headers=H, json=body)
ck('order raised', r.status_code == 200, r.text[:200])
d = r.json()
ck('two new materials reported', sorted(d.get('materials_added', [])) == ['ITM2 Plywood 18mm', 'ITM3 Binding Wire (MS Wire)'], d.get('materials_added'))
items = {i['name']: i for i in c.get('/store/items', headers=H).json()}
ck('new materials on the list with the LPO unit', items.get('Plywood 18mm', {}).get('unit') == 'sheet' and items.get('Binding Wire (MS Wire)', {}).get('unit') == 'roll', list(items))
ck('existing one not duplicated', sum(1 for n in items if n.lower() == 'cement opc 50kg') == 1)
lines = {l['description']: l for l in d['lines']}
ck('every line linked to its material', all(l.get('item_id') for l in d['lines']), d['lines'])
# the price now reaches the reports
db = database.SessionLocal()
it = db.query(models.StoreItem).filter_by(name='Plywood 18mm').first()
db.add(models.StoreMovement(item_id=it.id, kind='in', qty=50, location='', moved_on=main._dubai_today()))
db.add(models.StoreMovement(item_id=it.id, kind='out', qty=10, location='913', incharge='Raj', moved_on=main._dubai_today()))
db.commit(); db.close()
u = c.get('/store/report?kind=usage', headers=H).json()
ck('issued line priced from the LPO', any(r['name'] == 'Plywood 18mm' and r.get('rate') == 100 for r in u['rows']), u['rows'])
# editing an order with a new typed line adds that too
r = c.put(f"/store/purchase/orders/{d['id']}", headers=H, json={**body, 'lines': body['lines'] + [{'description': 'Nails 2in', 'qty': 5, 'unit': 'kg', 'rate': 8}]})
ck('edited order adds its new line to the list', r.status_code == 200 and r.json().get('materials_added') == ['ITM4 Nails 2in'], r.text[:200])
# the one-time catch-up for old orders
db = database.SessionLocal()
o = models.PurchaseOrder(po_no=999, ref='IC/LPO/OLD', supplier_name='X', order_date=main._dubai_today(), status='issued')
db.add(o); db.flush()
db.add(models.PurchaseOrderLine(order_id=o.id, item_id=None, description='Old Material', qty=1, unit='pcs', rate=1))
db.query(models.Setting).filter(models.Setting.key == 'materials_from_lpos').delete()
db.commit()
main._materials_from_old_lpos(db)
ck('old orders caught up once', db.query(models.StoreItem).filter_by(name='Old Material').first() is not None)
n = db.query(models.StoreItem).count(); main._materials_from_old_lpos(db)
ck('and not again', db.query(models.StoreItem).count() == n)
db.close()
print('\nALL PASS' if not FAIL else f'\n{len(FAIL)} FAILED: {FAIL}')

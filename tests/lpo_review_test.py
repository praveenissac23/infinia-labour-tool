"""A new LPO is 'Under review' until the purchaser marks it approved; the store is told only then (27/11/2026).

The purchaser: "once I approve their request & raise the LPO, store get notification that LPO raised against some
supplier, so he started calling the supplier immediately, but it was waiting under your approval". Decided with the
owner: the approval stays on WhatsApp (whoever in the group is free approves); in the portal a new LPO shows
'Under review' and the purchaser himself marks it approved. Until then the store's screens do not name the
supplier or his number and its notification says 'LPO under review'. Every LPO from before counts as approved.

Run: python3 tests/run_all.py lpo_review
"""
import sys
sys.path.insert(0, '.')
from datetime import date
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main

db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Administrator', role='admin'))
db.add(models.User(username='keeper', hashed_password=auth.hash_password('p'), full_name='Store Keeper', role='site'))
for s in ('908', '909'):
    db.add(models.Site(code=s, active=True))
db.commit()
c = TestClient(main.app, raise_server_exceptions=False)
tok = lambda u: {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': u, 'password': 'p'}).json()['access_token']}
H, K = tok('admin'), tok('keeper')
FAIL = []


def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{str(x)[:300]}]'))
    if not ok:
        FAIL.append(l)


sup = c.post('/store/suppliers', json={'name': 'Al Noor Building Materials LLC', 'contact_person': 'Rashid', 'phone': '0501234567',
                                         'trn': '100123456700003', 'payment_terms': 'Due on Receipt', 'email': 'sales@alnoor.example', 'address': 'Al Quoz, Dubai'}, headers=H).json()
cement = c.post('/store/items', json={'name': 'Cement 50KG', 'unit': 'pcs', 'item_type': 'consumable'}, headers=H).json()
mr = c.post('/store/requests', json={'site': '908', 'requested_by': 'Site Engineer', 'needed_by': date.today().isoformat(), 'lines': [
    {'item_id': cement['id'], 'description': '', 'qty_requested': 30, 'unit': 'pcs', 'purpose': 'BATHROOM & MAID ROOM PLASTERING'}]}, headers=H).json()
ln = mr['lines'][0]['id']
c.post(f'/store/request-lines/{ln}/decision', json={'decision': 'approved', 'reason': ''}, headers=H)


def lpo(lines, req=None, combined=False, loc='908'):
    r = c.post('/store/purchase/orders', json={
        'order_date': date.today().isoformat(), 'terms': 'Due on Receipt', 'supplier_name': sup['name'], 'supplier_id': sup['id'],
        'project_location': loc, 'job_scope': 'PLASTERING', 'contact_person': 'Akhil', 'mobile': '0562133135',
        'discount_pct': 0, 'tax_pct': 5, 'combined': combined, 'request_line_ids': req or [], 'lines': lines}, headers=H)
    return r


r = lpo([{'item_id': cement['id'], 'description': 'Cement 50KG', 'qty': 30, 'unit': 'pcs', 'rate': 14.5, 'tax_pct': 5}], req=[ln])
ck('the LPO is raised', r.status_code == 200, r.text)
o = r.json()
ck('...and starts under review', o.get('under_review') is True and o.get('approved_on') == '', o)
reg = [x for x in c.get('/store/purchase/orders', headers=H).json() if x['id'] == o['id']][0]
ck('the LPO register shows it under review', reg.get('under_review') is True, reg)


def keeper_req():
    return [x for x in c.get('/store/requests', headers=K).json() if x['id'] == mr['id']][0]


def office_req():
    return [x for x in c.get('/store/requests', headers=H).json() if x['id'] == mr['id']][0]


k = keeper_req()
ck('the store sees the request as LPO under review', k.get('lpo_review') is True and k['lines'][0].get('lpo_review') == o['ref'], k)
ck('...with no supplier and no number to ring', k.get('supplier') is None and k['lines'][0].get('supplier') is None, (k.get('supplier'), k['lines'][0].get('supplier')))
f = office_req()
ck('the office still sees who it is ordered from', f['lines'][0].get('supplier') and f['lines'][0]['supplier']['name'] == sup['name'] and f.get('lpo_review') is True, f['lines'][0])


def note():
    d = c.get('/notifications', headers=K).json()
    return [n for n in (d.get('notifications') if isinstance(d, dict) else d) if n.get('request_id') == mr['id'] and n.get('kind') == 'status']


n = note()
ck('the store\'s notification says under review, and names no supplier',
   len(n) == 1 and 'under review' in n[0]['title'].lower() and sup['name'] not in (n[0]['title'] + n[0]['detail']) and 'wait' in n[0]['detail'].lower(), n)


def trow():
    return [x for x in c.get('/store/purchase/tracker', headers=K).json()['rows'] if x['key'] == f"lpo{o['id']}"][0]


t = trow()
ck('Order tracker: the purchaser is next - Mark approved - not the store', t['review'] is True and t['role'] == 'purchaser' and t['action'] == 'Mark approved' and t['stage'] == 2, t)
ck('...and the supplier, his man and his number are not shown to the store yet', t['supplier'] == '' and t['contact'] == '' and t['phone'] == '', (t['supplier'], t['contact'], t['phone']))
to = [x for x in c.get('/store/purchase/tracker', headers=H).json()['rows'] if x['key'] == f"lpo{o['id']}"][0]
ck('...the office sees the supplier on the tracker (it raised the LPO), but no number to ring by mistake', to['supplier'] == sup['name'] and to['phone'] == '' and to['review'] is True, to)
dl = [x for x in c.get('/store/purchase/deliveries', headers=K).json()['orders'] if x['id'] == o['id']][0]
ck('the store\'s delivery list marks it under review', dl.get('review') is True, dl)

# the three other places the store could have learnt the supplier (found by the independent check)
dv = c.get(f"/store/purchase/orders/{o['id']}/deliveries", headers=K).json()
ck('the "It arrived" window does not name the supplier to the store either', dv.get('supplier') == '' and dv.get('review') is True, dv.get('supplier'))
ck('...the office sees it there', c.get(f"/store/purchase/orders/{o['id']}/deliveries", headers=H).json().get('supplier') == sup['name'])
rd = c.get(f"/store/purchase/tracker/request/{mr['id']}", headers=K).json()
ck('the request opened from the tracker: under review, no supplier or number for the store',
   rd['lines'][0].get('lpo_review') == o['ref'] and rd['lines'][0].get('supplier') is None and sup['phone'] not in str(rd), rd['lines'][0])
r = c.post(f"/store/purchase/orders/{o['id']}/approve", headers=K)
ck('the store keeper cannot mark it approved', r.status_code in (401, 403), r.status_code)
r = c.post(f"/store/purchase/orders/{o['id']}/approve", json={}, headers=H)
ck('the purchaser marks it approved', r.status_code == 200 and r.json()['under_review'] is False and r.json()['approved_on'] == date.today().strftime('%d/%m/%Y'), r.text)
ck('...and is told the store now sees it', 'ordered from ' + sup['name'] in r.json()['detail'], r.json().get('detail'))
k = keeper_req()
ck('now the store sees it ordered, from the supplier, with his number', not k.get('lpo_review') and k['lines'][0].get('supplier') and k['lines'][0]['supplier']['phone'] == '0501234567', k['lines'][0])
n = note()
ck('...and gets "ordered - from the supplier"', any('ordered' in x['title'] and sup['name'] in x['detail'] for x in n) and not any('under review' in x['title'].lower() for x in n), n)
t = trow()
ck('Order tracker: now the store is next - Book delivery - with the number to ring', t['review'] is False and t['role'] == 'store' and t['action'] == 'Book delivery' and t['phone'] == '0501234567', t)
r = c.post(f"/store/purchase/orders/{o['id']}/approve", json={}, headers=H)
ck('pressing it twice changes nothing', r.status_code == 200 and 'already approved' in r.json()['detail'], r.text)

# pressed by mistake: back under review - until material has come
r = c.post(f"/store/purchase/orders/{o['id']}/approve", json={'undo': True}, headers=H)
ck('pressed by mistake: it can go back under review', r.status_code == 200 and r.json()['under_review'] is True, r.text)
ck('...and the store is back to "under review"', keeper_req().get('lpo_review') is True and trow()['action'] == 'Mark approved')
c.post(f"/store/purchase/orders/{o['id']}/approve", json={}, headers=H)
d = c.post(f"/store/purchase/orders/{o['id']}/deliver", json={'dn_no': 'DN-771', 'dn_date': date.today().isoformat(),
           'lines': [{'line_id': o['lines'][0]['id'], 'qty': 10}]}, headers=H)
ck('a delivery is booked on it', d.status_code == 200, d.text)
r = c.post(f"/store/purchase/orders/{o['id']}/approve", json={'undo': True}, headers=H)
ck('once material has come it stays approved', r.status_code == 400 and 'already come' in r.json()['detail'], r.text)

# a request with one material on an approved LPO and another on an LPO still under review: the bell names only the approved supplier
sup2 = c.post('/store/suppliers', json={'name': 'Gulf Steel Trading LLC', 'contact_person': 'Imran', 'phone': '0507654321', 'trn': '100765432100003',
                                          'payment_terms': 'Due on Receipt', 'email': 'sales@gulfsteel.example', 'address': 'Jebel Ali'}, headers=H).json()
steel = c.post('/store/items', json={'name': 'Steel Rebar 10MM', 'unit': 't', 'item_type': 'consumable'}, headers=H).json()
mrx = c.post('/store/requests', json={'site': '909', 'requested_by': 'Site Engineer', 'lines': [
    {'item_id': cement['id'], 'description': '', 'qty_requested': 5, 'unit': 'pcs'}, {'item_id': steel['id'], 'description': '', 'qty_requested': 2, 'unit': 't'}]}, headers=H).json()
for x in mrx['lines']:
    c.post(f"/store/request-lines/{x['id']}/decision", json={'decision': 'approved', 'reason': ''}, headers=H)
la = lpo([{'item_id': cement['id'], 'description': 'Cement 50KG', 'qty': 5, 'unit': 'pcs', 'rate': 14.5, 'tax_pct': 5}], req=[mrx['lines'][0]['id']], loc='909').json()
c.post(f"/store/purchase/orders/{la['id']}/approve", json={}, headers=H)
rb = c.post('/store/purchase/orders', json={'order_date': date.today().isoformat(), 'terms': 'Due on Receipt', 'supplier_name': sup2['name'], 'supplier_id': sup2['id'],
     'project_location': '909', 'job_scope': 'STEEL', 'contact_person': 'Akhil', 'mobile': '0562133135', 'discount_pct': 0, 'tax_pct': 5,
     'request_line_ids': [mrx['lines'][1]['id']], 'lines': [{'item_id': steel['id'], 'description': 'Steel Rebar 10MM', 'qty': 2, 'unit': 't', 'rate': 2400, 'tax_pct': 5}]}, headers=H)
ck('a second LPO for the same request, from another supplier, is raised', rb.status_code == 200, rb.text)
dn = c.get('/notifications', headers=K).json()
nx = [n for n in (dn.get('notifications') if isinstance(dn, dict) else dn) if n.get('request_id') == mrx['id'] and n.get('kind') == 'status']
ck('one material approved, one still under review: the bell names the approved supplier only', len(nx) == 1 and sup['name'] in nx[0]['detail'] and sup2['name'] not in nx[0]['detail'], nx)
kx = [x for x in c.get('/store/requests', headers=K).json() if x['id'] == mrx['id']][0]
ck('...and the request shows the approved line\'s supplier, the other line under review with none',
   kx['lines'][0].get('supplier') and kx['lines'][0]['supplier']['name'] == sup['name'] and kx['lines'][1].get('supplier') is None and kx['lines'][1].get('lpo_review') == rb.json()['ref'] and not kx.get('lpo_review'), kx['lines'])

# a revision of an approved LPO stays approved; a revision of one under review waits with it
rv = c.post('/store/purchase/orders', json={'ref': la['ref'] + 'R1', 'order_date': date.today().isoformat(), 'terms': 'Due on Receipt', 'supplier_name': sup['name'], 'supplier_id': sup['id'],
     'project_location': '909', 'job_scope': 'PLASTERING', 'contact_person': 'Akhil', 'mobile': '0562133135', 'discount_pct': 0, 'tax_pct': 5,
     'lines': [{'item_id': cement['id'], 'description': 'Cement 50KG', 'qty': 6, 'unit': 'pcs', 'rate': 14.5, 'tax_pct': 5}]}, headers=H)
ck('a revision (R1) of an approved LPO is raised', rv.status_code == 200 and rv.json()['ref'].endswith('R1'), rv.text)
ck('...and stays approved - the store keeps seeing the supplier it has been chasing', rv.json()['under_review'] is False and rv.json()['approved_on'] != '', rv.json().get('under_review'))
rv2 = c.post('/store/purchase/orders', json={'ref': rb.json()['ref'] + 'R1', 'order_date': date.today().isoformat(), 'terms': 'Due on Receipt', 'supplier_name': sup2['name'], 'supplier_id': sup2['id'],
     'project_location': '909', 'job_scope': 'STEEL', 'contact_person': 'Akhil', 'mobile': '0562133135', 'discount_pct': 0, 'tax_pct': 5,
     'lines': [{'item_id': steel['id'], 'description': 'Steel Rebar 10MM', 'qty': 3, 'unit': 't', 'rate': 2400, 'tax_pct': 5}]}, headers=H)
ck('a revision of an LPO still under review is under review too', rv2.status_code == 200 and rv2.json()['under_review'] is True, rv2.text)

# material booked on the request itself (no delivery note on the LPO), or a bill: it cannot go back under review
lb = lpo([{'item_id': cement['id'], 'description': 'Cement 50KG', 'qty': 8, 'unit': 'pcs', 'rate': 14.5, 'tax_pct': 5}], loc='908').json()
c.post(f"/store/purchase/orders/{lb['id']}/approve", json={}, headers=H)
sb = database.SessionLocal(); ob = sb.get(models.PurchaseOrder, lb['id']); ob.bill_no = 'INV-5521'; sb.commit(); sb.close()
r = c.post(f"/store/purchase/orders/{lb['id']}/approve", json={'undo': True}, headers=H)
ck('with its bill entered it stays approved', r.status_code == 400 and 'bill' in r.json()['detail'], r.text)

# an LPO raised straight away (no request): the request it makes for itself is under review too
r2 = lpo([{'description': 'Gypsum Board 12MM', 'qty': 40, 'unit': 'pcs', 'rate': 22, 'tax_pct': 5}], loc='909').json()
ks = [x for x in c.get('/store/requests', headers=K).json() if any(l.get('lpo_review') == r2['ref'] for l in x['lines'])]
ck('an LPO raised straight away: its own tracking request is under review for the store, no supplier', len(ks) == 1 and ks[0].get('lpo_review') is True and ks[0]['lines'][0].get('supplier') is None, ks)

# cancelled while under review: nothing is left "under review"
c.post(f"/store/purchase/orders/{r2['id']}/cancel", json={'reason': 'not approved in the group'}, headers=H)
reg = [x for x in c.get('/store/purchase/orders', headers=H).json() if x['id'] == r2['id']][0]
ck('cancelled while under review: it reads cancelled, not under review', reg['status'] == 'cancelled' and reg['under_review'] is False, reg)
ck('...and nothing of it stays under review for the store', not [x for x in c.get('/store/requests', headers=K).json() if any(l.get('lpo_review') == r2['ref'] for l in x['lines'])])

# every LPO from before this was kept counts as approved
s = database.SessionLocal()
old = models.PurchaseOrder(po_no=20260001, ref='IC/LPO/20260001', order_date=date(2026, 10, 3), supplier_name='Old Supplier', project_location='908')
s.add(old); s.commit()
ck('an LPO from before (nothing kept) counts as approved', main._lpo_dict(old)['under_review'] is False)
import purchasing
ck('...and is on nobody\'s under-review list', old.ref not in purchasing.review_lines(s).values())
s.close()

src = open('main.py', encoding='utf-8').read()
ck('the supplier\'s copy (PDF) is not marked or held back while under review - it is what is shared for approval',
   'under_review' not in src[src.index('def _lpo_html(o):'):src.index('def _lpo_html(o):') + 9000])
import tabrights
ck('marking approved needs the purchasing right', tabrights.__dict__ and ('store.purchasing.purchase' in str([v for k, v in vars(tabrights).items() if isinstance(v, dict) and ('POST', '/store/purchase/orders/{order_id}/approve') in v])))
print("\nALL PASS" if not FAIL else f"\n{len(FAIL)} FAILED")
sys.exit(1 if FAIL else 0)

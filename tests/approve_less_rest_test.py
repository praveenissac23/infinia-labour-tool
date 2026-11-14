"""Approve less (14/11/2026): 6 m3 sand asked, 3 approved to split between two suppliers - the other 3 stays on the
request, waiting on the office, until it is approved or rejected. Plus the one-time put-back for MR-0134.
    cd app && DATABASE_URL=sqlite:////tmp/al.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/approve_less_rest_test.py  (empty db)"""
import sys
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main

db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Administrator', role='admin'))
db.add(models.Site(code='925', active=True)); db.commit(); db.close()
c = TestClient(main.app, raise_server_exceptions=False)
H = {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': 'admin', 'password': 'p'}).json()['access_token']}
FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{str(x)[:400]}]'))
    if not ok: FAIL.append(l)
def it(name, unit='pcs'):
    return c.post('/store/items', json={'name': name, 'unit': unit, 'category': 'Consumables'}, headers=H).json()
def req(id_):
    return [x for x in c.get('/store/requests', headers=H).json() if x['id'] == id_][0]

sand, dpc = it('Black Sand', 'm3'), it('DPC Roll 25CM', 'm')
m = c.post('/store/requests', json={'site': '925', 'requested_by': 'Akhil', 'needed_by': '2026-11-15', 'urgency': 'normal', 'notes': '',
    'lines': [{'item_id': sand['id'], 'qty_requested': 6, 'unit': 'm3', 'purpose': 'FF BLOCK WORK'},
              {'item_id': dpc['id'], 'qty_requested': 20, 'unit': 'm', 'purpose': ''}]}, headers=H).json()
ls = {l['item_id']: l for l in req(m['id'])['lines']}
r = c.post(f"/store/request-lines/{ls[sand['id']]['id']}/approve-less", json={'qty': 3, 'reason': 'Need to send 2 different Supplier'}, headers=H)
ck('approve 3 of 6', r.status_code == 200, r.text)
lines = req(m['id'])['lines']
sl = [l for l in lines if l['item_id'] == sand['id']]
first = [l for l in sl if l['status'] == 'approved']
rest = [l for l in sl if l['status'] == 'pending']
ck('3 m3 approved', len(first) == 1 and first[0]['qty_requested'] == 3, sl)
ck('the other 3 m3 still on the request, waiting on the office', len(rest) == 1 and rest[0]['qty_requested'] == 3 and rest[0]['unit'] == 'm3', sl)
ck('same material and purpose', rest and rest[0]['purpose'] == 'FF BLOCK WORK')
ck('the other material untouched', [l for l in lines if l['item_id'] == dpc['id']][0]['status'] == 'pending')
db = database.SessionLocal()
ck('activity log says so', 'the other 3 waits on the office' in db.query(models.AuditLog).filter(models.AuditLog.action == 'request_line_decision').order_by(models.AuditLog.id.desc()).first().details)
db.close()

rows = [x for x in c.get('/store/requests/report?kind=asked', headers=H).json()['rows'] if x['ref'] == m['ref'] and x['asked'] == 'Black Sand']
ck('register: the 6 asked, 3 approved - and the rest 3, waiting on office', sorted((x['asked_qty'], x['approved'], x['status']) for x in rows) == [(3, '', 'Waiting on office'), (6, 3, 'Office approved')], rows)
ck('register says where the rest came from', any(x['what_for'].startswith('6 m3 asked, 3 approved first') for x in rows), [x['what_for'] for x in rows])
ck('the rest is under All open', any(x['ref'] == m['ref'] and x['approved'] == '' for x in c.get('/store/requests/report?kind=asked_open', headers=H).json()['rows'] if x['asked'] == 'Black Sand'))

# later: the rest approved in full for the second supplier, or rejected
rid = rest[0]['id']
r = c.post(f'/store/request-lines/{rid}/decision', json={'decision': 'approved', 'reason': ''}, headers=H)
ck('the rest approved later', r.status_code == 200 and [l for l in req(m['id'])['lines'] if l['id'] == rid][0]['status'] == 'approved', r.text)

m2 = c.post('/store/requests', json={'site': '925', 'requested_by': 'Akhil', 'needed_by': '2026-11-15', 'urgency': 'normal', 'notes': '',
    'lines': [{'item_id': sand['id'], 'qty_requested': 10, 'unit': 'm3', 'purpose': 'PLASTER'}]}, headers=H).json()
l0 = req(m2['id'])['lines'][0]['id']
c.post(f'/store/request-lines/{l0}/approve-less', json={'qty': 4}, headers=H)
r1 = [l for l in req(m2['id'])['lines'] if l['status'] == 'pending'][0]
c.post(f"/store/request-lines/{r1['id']}/approve-less", json={'qty': 2.5}, headers=H)
pend = [l for l in req(m2['id'])['lines'] if l['status'] == 'pending']
ck('approve less again on the rest: 4 + 2.5 approved, 3.5 still waiting', len(pend) == 1 and abs(pend[0]['qty_requested'] - 3.5) < 1e-9, req(m2['id'])['lines'])
r = c.post(f"/store/request-lines/{pend[0]['id']}/decision", json={'decision': 'rejected', 'reason': 'Enough on site'}, headers=H)
ln = req(m2['id'])['lines']
ck('rejected: gone from what waits, the approved parts stay', r.status_code == 200 and not [l for l in ln if l['status'] == 'pending'] and sorted(l['qty_requested'] for l in ln if l['status'] == 'approved') == [2.5, 4], ln)
ck('approving in full makes no rest line', c.post(f'/store/request-lines/{l0}/approve-less', json={'qty': 4}, headers=H).status_code == 200 and len(req(m2['id'])['lines']) == 3)

# review 14/11/2026: the approved part is on the tracker to order while the rest waits; stock arriving cannot fill the
# rest; the 3 m3 comes, then the rest is rejected - the request closes as delivered, not stuck at part delivered
m3 = c.post('/store/requests', json={'site': '925', 'requested_by': 'Akhil', 'needed_by': '2026-11-15', 'urgency': 'normal', 'notes': '',
    'lines': [{'item_id': sand['id'], 'qty_requested': 6, 'unit': 'm3', 'purpose': 'FF BLOCK WORK'}]}, headers=H).json()
a = req(m3['id'])['lines'][0]['id']
c.post(f'/store/request-lines/{a}/approve-less', json={'qty': 3}, headers=H)
rest3 = [l for l in req(m3['id'])['lines'] if l['status'] == 'pending'][0]['id']
tr = [r for r in c.get('/store/purchase/tracker', headers=H).json()['rows'] if r.get('kind') == 'mr' and r['id'] == m3['id']]
ck('tracker: the rest under Approve and the 3 m3 under To order, both', sorted(r['stage'] for r in tr) == [0, 1] and len({r['key'] for r in tr}) == 2, [(r['stage'], r['key']) for r in tr])
ck('the To order row lists only the approved 3', [l['qty'] for r in tr if r['stage'] == 1 for l in r['lines']] == [3])
x = c.post(f"/store/requests/{m3['id']}/receive?line_id={rest3}&qty=3", headers=H)
ck('the rest cannot be booked in while it waits on the office', x.status_code == 400, x.text)
x = c.post(f"/store/requests/{m3['id']}/receive?line_id={a}&qty=3&supplier=Sand+Co", headers=H)
ck('the approved 3 m3 is booked in', x.status_code == 200, x.text)
ck('... part delivered while the rest waits', req(m3['id'])['status'] == 'partial', req(m3['id'])['status'])
c.post(f'/store/request-lines/{rest3}/decision', json={'decision': 'rejected', 'reason': 'One load is enough'}, headers=H)
ck('rest rejected after the 3 came: the request is delivered, not stuck', req(m3['id'])['status'] == 'delivered', req(m3['id'])['status'])

# one-time put-back: MR-0134's Black Sand (approved 3 of 6 before this change)
db = database.SessionLocal()
import datetime as _dt
mr = models.MaterialRequest(ref='MR-0134', site='925', requested_by='Akhil', status='approved', requested_on=_dt.date(2026, 11, 14))
db.add(mr); db.flush()
bs = models.MaterialRequestLine(request_id=mr.id, item_id=sand['id'], description='', qty_requested=3, qty_approved=3, unit='m3', status='approved',
                                notes='Asked for 6, approved 3: Need to send 2 different Supplier', asked_qty=6, asked_name='Black Sand')
ok = models.MaterialRequestLine(request_id=mr.id, item_id=dpc['id'], description='', qty_requested=20, unit='m', status='approved')
db.add_all([bs, ok]); db.commit()
main._fix_rest_mr0134(db)
db.expire_all()
back = [l for l in db.query(models.MaterialRequestLine).filter(models.MaterialRequestLine.request_id == mr.id).all() if l.source == 'rest']
ck('MR-0134: the other 3 m3 back, waiting on the office', len(back) == 1 and back[0].qty_requested == 3 and back[0].status == 'pending' and back[0].unit == 'm3', [(l.qty_requested, l.status) for l in back])
main._fix_rest_mr0134(db)
db.query(models.Setting).filter(models.Setting.key == 'rest_mr0134').delete(); db.commit(); main._fix_rest_mr0134(db)
ck('never twice', db.query(models.MaterialRequestLine).filter(models.MaterialRequestLine.request_id == mr.id, models.MaterialRequestLine.source == 'rest').count() == 1)
db.close()
print('\n' + ('ALL PASS' if not FAIL else f'{len(FAIL)} FAILED'))
sys.exit(1 if FAIL else 0)

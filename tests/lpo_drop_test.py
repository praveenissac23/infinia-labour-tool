"""Purchasing > Waiting to be ordered: a material not needed any more is taken off right there (26/11/2026).

MR-0158 (site 102): Steel Rebar 10MM and Cover Block 4CM approved; the purchaser no longer wants the cover blocks.
An approved request can't be edited, so the line stayed on the list. The x on the line turns it down on its request,
with the reason, and the rest of the request stays waiting.

Run: python3 tests/run_all.py lpo_drop
"""
import sys
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main

db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Administrator', role='admin'))
db.add(models.Site(code='102', active=True)); db.commit(); db.close()
c = TestClient(main.app, raise_server_exceptions=False)
H = {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': 'admin', 'password': 'p'}).json()['access_token']}
FAIL = []


def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{x}]'))
    if not ok:
        FAIL.append(l)


it = lambda n, u: c.post('/store/items', json={'name': n, 'unit': u, 'item_type': 'consumable'}, headers=H).json()
rebar, cover = it('Steel Rebar 10MM', 't'), it('Cover Block 4CM', 'pcs')
mr = c.post('/store/requests', json={'site': '102', 'requested_by': 'Premraj', 'needed_by': '2026-11-25', 'lines': [
    {'item_id': rebar['id'], 'description': '', 'qty_requested': 1.8, 'unit': 't', 'purpose': 'SWIMMING POOL WORK'},
    {'item_id': cover['id'], 'description': 'Cover Block 4CM', 'qty_requested': 200, 'unit': 'pcs', 'purpose': 'SWIMMING POOL WORK'}]},
    headers=H).json()
lines = {l['description'] or l.get('item_name', ''): l['id'] for l in mr['lines']}
for lid in [l['id'] for l in mr['lines']]:
    c.post(f'/store/request-lines/{lid}/decision', json={'decision': 'approved', 'reason': ''}, headers=H)
pend = lambda: [p['description'] for p in c.get('/store/purchase/pending', headers=H).json() if p['ref'] == mr['ref']]
ck('both approved materials wait to be ordered', sorted(pend()) == ['Cover Block 4CM', 'Steel Rebar 10MM'], pend())
r = c.put(f"/store/requests/{mr['id']}", json={'site': '102', 'lines': [{'item_id': rebar['id'], 'qty_requested': 1.8, 'unit': 't'}]}, headers=H)
ck('editing the approved request is refused (why the cover blocks stayed)', r.status_code == 400, r.text)

cover_line = [l['id'] for l in mr['lines'] if l['item_id'] == cover['id']][0]
r = c.post(f'/store/request-lines/{cover_line}/decision', json={'decision': 'rejected', 'reason': 'not needed any more'}, headers=H)
ck('the x turns the cover blocks down', r.status_code == 200, r.text)
ck('...they are off the list; the rebar still waits', pend() == ['Steel Rebar 10MM'], pend())
db = database.SessionLocal()
ln = db.get(models.MaterialRequestLine, cover_line)
ck('...the reason is on the request for the site to see', ln.status == 'rejected' and ln.reject_reason == 'not needed any more')
ck('...the request itself stays open for the rebar', db.get(models.MaterialRequest, mr['id']).status not in ('rejected', 'closed'))
db.close()

page = open('../app-classic.html', encoding='utf-8').read()
ck('each waiting line has an x that asks first, with a reason', 'onclick="lpoDropLine(${p.line_id})"' in page and 'function lpoDropLine' in page
   and 'id="lpo-drop-why"' in page and '>Keep it</button>' in page)
ck('it uses the same decision as Reject this (rejected, with the reason)', 'decision: "rejected", reason: o.querySelector("#lpo-drop-why").value.trim()' in page)
ck('the table has a column for it (9 columns)', 'colspan="9" class="empty-note">Nothing waiting' in page)

print("\nALL PASS" if not FAIL else f"\n{len(FAIL)} FAILED")
sys.exit(1 if FAIL else 0)

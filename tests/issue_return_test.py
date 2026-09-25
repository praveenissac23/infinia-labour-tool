"""A measuring tape goes to site 901 in the morning and comes back in the
evening: the issue & return register shows one line, closed, with who
took it, who brought it back and its condition.

Run: cd app && DATABASE_URL=sqlite:////tmp/ir.db python3 ../tests/issue_return_test.py
"""
import sys
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models
models.Base.metadata.create_all(database.engine)
import main

FAIL = []
def ck(l, ok, c=None):
    print(("PASS " if ok else "FAIL ") + l + ("" if ok else f"   [{c}]"))
    if not ok: FAIL.append(l)

c = TestClient(main.app)
with c:
    H = {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': 'admin', 'password': 'changeme123'}).json()['access_token']}
    today = main._dubai_today().isoformat()
    tape = c.post('/store/items', json={'code': 'TAPE', 'name': 'Measuring tape 5m', 'category': 'Tools', 'unit': 'pcs', 'item_type': 'asset', 'reorder_level': 0, 'opening_qty': 3}, headers=H)
    ck('a tool is on the books', tape.status_code == 200, tape.text[:150])
    tid = tape.json()['id']
    r = c.post('/store/movements', json={'item_id': tid, 'kind': 'out', 'qty': 1, 'from_location': '', 'location': '901', 'incharge': 'AMAL', 'moved_on': today}, headers=H)
    ck('issued to site 901 to Amal in the morning', r.status_code == 200, r.text[:150])
    reg = c.get('/store/report?kind=issues', headers=H).json()
    row = next((x for x in reg['rows'] if x['code'] == 'TAPE'), None)
    ck('the register shows it out, taken by Amal, one still out', row and row['given_to'].upper() == 'AMAL' and row['still_out'] == 1 and row['site'].endswith('901'), row)
    ck('and the register counts one tool still out', reg['still_out'] == 1, reg.get('still_out'))
    r = c.post('/store/movements', json={'item_id': tid, 'kind': 'return', 'qty': 1, 'from_location': '901', 'location': '', 'incharge': 'RAJESH', 'condition': 'Damaged', 'notes': 'lock broken', 'moved_on': today}, headers=H)
    ck('returned in the evening by Rajesh, damaged', r.status_code == 200, r.text[:150])
    reg = c.get('/store/report?kind=issues', headers=H).json()
    row = next((x for x in reg['rows'] if x['code'] == 'TAPE'), None)
    ck('the same line now closes: returned today, by Rajesh, condition Damaged, nothing still out',
       row and row['returned_on'] == today and row['returned_by'].upper() == 'RAJESH' and row['condition'] == 'Damaged'
       and row['still_out'] == 0 and row['qty_back'] == 1 and 'lock broken' in row['notes'], row)
    ck('nothing still out', reg['still_out'] == 0)
    stock = next(x for x in c.get('/store/stock', headers=H).json() if x['item_id'] == tid)
    ck('the store records show all three tapes back in the central store', stock['central'] == 3 and stock['out_at_sites'] == 0, stock)
    t = c.post('/auth/download-token', headers=H).json()['token']
    for fmt in ('excel', 'pdf'):
        r = c.get(f'/export/store/report?kind=issues&format={fmt}&token={t}')
        ck(f'the register exports as {fmt}', r.status_code == 200 and len(r.content) > 1000, r.status_code)
    r = c.get(f'/export/store/report/view?kind=issues&token={t}')
    ck('and previews', r.status_code == 200 and 'Returned' in r.text, r.status_code)
print()
if FAIL: print(f"{len(FAIL)} FAILED"); sys.exit(1)
print("OUT IN THE MORNING, BACK IN THE EVENING, ONE LINE")

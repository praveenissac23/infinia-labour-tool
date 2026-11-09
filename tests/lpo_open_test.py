"""Open LPO (9 Nov 2026, purchaser): the agreed rates for the whole project - the rates print, every amount and
the total are 0, OPEN LPO prints under the items; nothing to Zoho or the site costs.
    cp /tmp/claude-0/bn.db /tmp/claude-0/rt/ol.db; cd app && DATABASE_URL=sqlite:////tmp/claude-0/rt/ol.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/lpo_open_test.py
"""
import os, sys, subprocess, tempfile, warnings
warnings.filterwarnings("ignore"); sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import main, models, database
from openpyxl import load_workbook
c = TestClient(main.app, raise_server_exceptions=False); c.__enter__()
H = {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': 'admin', 'password': 'changeme123'}).json()['access_token']}
DL = lambda: c.post('/auth/download-token', headers=H).json()['token']
FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{str(x)[:400]}]')); ok or FAIL.append(l)
L = [('Supply and apply one coat of primer on swimming pool area.', 1, 'sqm', 2), ('4mm SBS membrane two layers', 1, 'sqm', 57)]
def body(open_=None, **k):
    b = {'supplier_name': 'Rukn Muwalih Tech. Cont. L.L.C', 'order_date': '2026-11-09', 'project_location': '914', 'round_off': 0.5,
         'lines': [{'description': d, 'qty': q, 'unit': u, 'rate': r, 'tax_pct': 5} for d, q, u, r in L]}
    if open_ is not None: b['open_lpo'] = open_
    b.update(k); return b
r = c.post('/store/purchase/orders', json=body(True), headers=H); ck('open LPO raised', r.status_code == 200, r.text); a = r.json()
o = c.get(f"/store/purchase/orders/{a['id']}", headers=H).json()
ck('saved as open, total 0, rates kept', o.get('open_lpo') is True and o['total'] == 0 and [l['rate'] for l in o['lines']] == [2, 57], (o.get('open_lpo'), o['total']))
reg = {x['id']: x for x in c.get('/store/purchase/orders?limit=5000', headers=H).json()}
ck('register total 0', reg[a['id']]['total'] == 0, reg[a['id']].get('total'))
db = database.SessionLocal(); h = main._lpo_html(db.get(models.PurchaseOrder, a['id'])); db.close()
ck('printed: rates 2.00 and 57.00 shown', '2.00' in h and '57.00' in h)
ck('printed: OPEN LPO band, total AED 0.00, no round off', 'OPEN LPO' in h and 'AED 0.00' in h and 'Round off' not in h)
ck('printed: no 57.00 in the amount column', h.count('57.00') == 1, h.count('57.00'))
with tempfile.TemporaryDirectory() as td:
    p = c.get(f"/export/purchase/{a['id']}?token={DL()}&format=pdf"); fp = os.path.join(td, 'x.pdf'); open(fp, 'wb').write(p.content)
    t = ' '.join(subprocess.run(['pdftotext', '-layout', fp, '-'], capture_output=True, text=True).stdout.split())
    ck('PDF: OPEN LPO, rate 57.00 once, Total AED 0.00', 'OPEN LPO' in t and t.count('57.00') == 1 and 'AED 0.00' in t, t[:600])
    x = c.get(f"/export/purchase/{a['id']}?token={DL()}&format=excel"); fx = os.path.join(td, 'a.xlsx'); open(fx, 'wb').write(x.content)
    ws = load_workbook(fx).active
    vals = [cl.value for row in ws.iter_rows() for cl in row if cl.value is not None]
    ck('Excel: amounts 0, no ROUND formula, rate 57 kept', 57 in vals and not any(isinstance(v, str) and v.startswith('=ROUND(C') for v in vals), [v for v in vals if isinstance(v, str) and v.startswith('=')][:5])
zl = {x['id']: x for x in c.get('/store/zoho/pos', headers=H).json()['rows']}
ck('not in the Send to Zoho list', a['id'] not in zl)
# untick: amounts come back
r = c.put(f"/store/purchase/orders/{a['id']}", json=body(False), headers=H); ck('edit: untick open', r.status_code == 200, r.text)
o = c.get(f"/store/purchase/orders/{a['id']}", headers=H).json()
ck('unticked: total 62.45 (59 + 5% VAT + 0.50)', abs(o['total'] - 62.45) < 0.005, o['total'])
r = c.post('/store/purchase/orders', json=body(), headers=H); b2 = c.get(f"/store/purchase/orders/{r.json()['id']}", headers=H).json()
ck('a normal LPO is not open and keeps its total', not b2.get('open_lpo') and b2['total'] == 62.45, (b2.get('open_lpo'), b2['total']))
print('FAILS:', FAIL or 'none')

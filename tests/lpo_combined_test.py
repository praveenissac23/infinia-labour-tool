"""Combined LPO (29 Oct 2026): one supplier, items for different sites. Each line says who pays (Store or a
site) - kept for accounts and site costs only; the printed LPO is unchanged. Off: an LPO exactly as before.
    cp /tmp/full.db /tmp/cb.db; cd app && DATABASE_URL=sqlite:////tmp/cb.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/lpo_combined_test.py"""
import sys
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models
import main, pozoho, projexpense

c = TestClient(main.app, raise_server_exceptions=False); c.__enter__()   # startup: adds the new columns to an older db
H = {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': 'admin', 'password': 'changeme123'}).json()['access_token']}
FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{str(x)[:400]}]'))
    if not ok: FAIL.append(l)

lines = [('SAFETY COVERALL (WORKLAND)', 20, 'pcs', 28, 'Store'), ('WIRE NAIL 2.5"', 25, 'kg', 6.5, '913'),
         ('SOFT BRUSH 12" WITH STICK', 6, 'pcs', 14, '910'), ('WHITE SILICONE 300ML', 24, 'pcs', 9.5, '910'),
         ('MMA WELDING MACHINE ( ESAB ROGUE ES201I)', 1, 'nos', 1450, 'STORE')]
body = {'supplier_name': 'Al Waha Hardware Trading LLC', 'order_date': '2026-10-29', 'project_location': 'STORE', 'combined': True,
        'lines': [{'description': d, 'qty': q, 'unit': u, 'rate': r, 'tax_pct': 5, 'cost_to': t} for d, q, u, r, t in lines]}
bad = dict(body, lines=body['lines'][:-1] + [dict(body['lines'][-1], cost_to='')])
r = c.post('/store/purchase/orders', json=bad, headers=H)
ck('combined: every item must say who pays', r.status_code == 400 and 'MMA WELDING' in r.text, r.text)
r = c.post('/store/purchase/orders', json=body, headers=H)
ck('one combined LPO raised', r.status_code == 200, r.text)
po = r.json()
ck('it keeps who pays for each line', po['combined'] and [l['cost_to'] for l in po['lines']] == ['STORE', '913', '910', '910', 'STORE'], po['lines'])
db = database.SessionLocal(); o = db.get(models.PurchaseOrder, po['id'])
sp = main.lpo_split(o)
ck('split: Store 2,010 / 910 312 / 913 162.50 (before VAT)', sp == [('STORE', 2010.0, 100.5), ('910', 312.0, 15.6), ('913', 162.5, 8.12)], sp)
html = main._lpo_html(o)
ck('the printed LPO is unchanged: no site per line', '913' not in html and '910' not in html and 'Cost to' not in html)
ck('one project location on it', 'STORE' in html)
# Zoho: each line says whose cost it is
import zohoapi as Z
Z.vat_tax = lambda db_: 'V5'; Z.zero_tax = lambda db_: 'V0'; Z.account_id = lambda db_, n: 'ACC'
pozoho._vendor = lambda db_, o_: 'VEN'; pozoho._vendor_treatment = lambda db_, v: ''
o.zoho_account = 'Materials'; db.commit()
zb = pozoho._body(db, o)
ck('Zoho PO: each line says whose cost it is', [l['description'].split(' | ')[-1] for l in zb['line_items']] == ['Cost to: Store', 'Cost to: 913', 'Cost to: 910', 'Cost to: 910', 'Cost to: Store'], zb['line_items'])
ck('and the reference says combined', zb['reference_number'].startswith('Combined: Store, 910, 913'), zb['reference_number'])
row = [x for x in c.get('/store/zoho/pos', headers=H).json()['rows'] if x['id'] == po['id']]
ck('Send to Zoho shows the split', row and [s['to'] for s in row[0]['split']] == ['Store', '910', '913'], row)
db.close()
# site costs: 910 and 913 each get their own lines; the store part is stock
projexpense._CACHE.clear()
g = projexpense.gather(database.SessionLocal(), '2026-10-29', '2026-10-29')
got = {k: [x for x in v if x.get('cat') == 'lpo' and x.get('id') == po['id']] for k, v in g.get('lines', {}).items()} if 'lines' in g else {}
d910 = projexpense.detail(g, '910'); d913 = projexpense.detail(g, '913')
txt910, txt913 = str(d910), str(d913)
ck('910 is charged the brush and silicone (312.00)', 'SOFT BRUSH' in txt910 and 'WIRE NAIL' not in txt910 and '312.0' in txt910, txt910[:400])
ck('913 is charged the nails (162.50)', 'WIRE NAIL' in txt913 and 'SILICONE' not in txt913 and '162.5' in txt913, txt913[:400])
# edit: a site change is told to accounts
b2 = dict(body, lines=[dict(l) for l in body['lines']]); b2['lines'][1]['cost_to'] = '910'
c.put(f"/store/purchase/orders/{po['id']}", json=b2, headers=H)
db = database.SessionLocal(); o = db.get(models.PurchaseOrder, po['id'])
nt = pozoho.note_of(o)
ck('changing who pays is told to accounts', any('cost to 913 -> 910' in x for x in nt['items'][-1]['changes']), nt)
# off: an ordinary LPO, as before
b3 = dict(body, combined=False)
p3 = c.post('/store/purchase/orders', json=b3, headers=H).json()
ck('switched off: an ordinary LPO, no split kept', not p3['combined'] and all(not l['cost_to'] for l in p3['lines']), p3['lines'])
print(f"{len(FAIL)} FAILED" if FAIL else 'ALL PASS')

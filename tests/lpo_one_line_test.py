"""Combined LPO: the same material for several sites is ONE line for the supplier (27/11/2026).

The purchaser: "in this combined LPO, if different site need same materials, better to make a single line of item,
but in the combined LPO section it should take separate line of items ... if it shows like 3 times same cement bag
its not looking good". Decided with the owner: nothing about what is stored changes - each site keeps its own line
(that is what tells accounts and the store whose it is) - only what is SHOWN: the supplier's LPO (page, PDF, Excel)
and the purchaser's form show one line with the quantities added. A site with its own rate stays a line of its own.

Run: python3 tests/run_all.py lpo_one_line
"""
import io, sys
sys.path.insert(0, '.')
from datetime import date
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main

db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Administrator', role='admin'))
for s in ('908', '909', '925'):
    db.add(models.Site(code=s, active=True))
db.commit()
c = TestClient(main.app, raise_server_exceptions=False)
H = {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': 'admin', 'password': 'p'}).json()['access_token']}
FAIL = []


def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{str(x)[:400]}]'))
    if not ok:
        FAIL.append(l)


sup = c.post('/store/suppliers', json={'name': 'Al Noor Building Materials LLC', 'contact_person': 'Rashid', 'phone': '0501234567',
                                         'trn': '100123456700003', 'payment_terms': 'Due on Receipt', 'email': 'sales@alnoor.example',
                                         'address': 'Al Quoz, Dubai'}, headers=H).json()
cement = c.post('/store/items', json={'name': 'Cement 50KG', 'unit': 'pcs', 'item_type': 'consumable'}, headers=H).json()


def lpo(lines, combined=True, discount=0, round_off=0):
    r = c.post('/store/purchase/orders', json={
        'order_date': date.today().isoformat(), 'terms': 'Due on Receipt', 'supplier_name': sup['name'], 'supplier_id': sup['id'],
        'project_location': '908', 'job_scope': 'BATHROOM & MAID ROOM PLASTERING', 'contact_person': 'Akhil', 'mobile': '0562133135',
        'discount_pct': discount, 'round_off': round_off, 'tax_pct': 5, 'combined': combined, 'lines': lines}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def L(desc, qty, rate, to, **k):
    return {'item_id': cement['id'] if desc == 'Cement 50KG' else None, 'description': desc, 'qty': qty, 'unit': k.pop('unit', 'pcs'),
            'rate': rate, 'tax_pct': k.pop('tax_pct', 5), 'cost_to': to, **k}


o = lpo([L('Cement 50KG', 30, 14.5, '908'), L('Tile Adhesive 20KG', 12, 32, '908', unit='bag'),
         L('Cement 50KG', 20, 14.5, '909'), L('Cement 50KG', 50, 14.5, '925')])
ck('stored as always: every site its own line', [(l['description'], l['qty'], l['cost_to']) for l in o['lines']] ==
   [('Cement 50KG', 30, '908'), ('Tile Adhesive 20KG', 12, '908'), ('Cement 50KG', 20, '909'), ('Cement 50KG', 50, '925')], o['lines'])
s = database.SessionLocal()
po = s.get(models.PurchaseOrder, o['id'])
pl = main.lpo_print_lines(po)
ck('the supplier\'s copy: ONE cement line of 100, in its first place, then the adhesive',
   [(l.description, l.qty, l.unit, l.rate) for l in pl] == [('Cement 50KG', 100, 'pcs', 14.5), ('Tile Adhesive 20KG', 12, 'bag', 32)], [(l.description, l.qty) for l in pl])
ck('...the stored lines are not touched by printing', [l.qty for l in po.lines] == [30, 12, 20, 50])
d = main._lpo_for_print(po)
ck('the PDF and the Excel get the same two lines', [(l['description'], l['qty']) for l in d['lines']] == [('Cement 50KG', 100), ('Tile Adhesive 20KG', 12)], d['lines'])
ck('...and the money is the same to the fils: 1,834.00 + 91.70 = 1,925.70',
   abs(sum(l['qty'] * l['rate'] for l in d['lines']) - 1834.0) < 1e-9 and abs(d['total'] - 1925.70) < 0.005 and abs(main.lpo_total(po) - 1925.70) < 0.005, d['total'])
html = main._lpo_html(po)
ck('the LPO page shows one cement row of 100.00 at 1,450.00', html.count('Cement 50KG') == 1 and '<td class="r">100.00</td>' in html and '1,450.00' in html and 'AED 1,925.70' in html)
ck('accounts still get every site\'s share (859.95 / 304.50 / 761.25)',
   {k: round(n + v, 2) for k, n, v in main.lpo_split(po)} == {'908': 859.95, '909': 304.5, '925': 761.25}, main.lpo_split(po))
import export_web
pdf = export_web.build_lpo_pdf(d)
pdf = pdf.getvalue() if hasattr(pdf, 'getvalue') else pdf
ck('the PDF is made', pdf[:4] == b'%PDF' and len(pdf) > 3000)
xl = export_web.build_lpo_excel(d)
xl = xl.getvalue() if hasattr(xl, 'getvalue') else xl
from openpyxl import load_workbook
cells = [str(v) for row in load_workbook(io.BytesIO(xl)).active.iter_rows(values_only=True) for v in row if v is not None]
ck('the Excel has one cement line', sum(1 for v in cells if v.strip() == 'Cement 50KG') == 1, [v for v in cells if 'Cement' in v])

# a site with its own rate stays its own line
o2 = lpo([L('Cement 50KG', 30, 14.5, '908'), L('Cement 50KG', 20, 15.0, '909'), L('Cement 50KG', 50, 14.5, '925')])
p2 = main.lpo_print_lines(s.get(models.PurchaseOrder, o2['id']))
ck('a site with a different rate keeps its own line (80 at 14.50, 20 at 15.00)', [(l.qty, l.rate) for l in p2] == [(80, 14.5), (20, 15.0)], [(l.qty, l.rate) for l in p2])
# different description under it, unit, or tax: not the same thing
o3 = lpo([L('Cement 50KG', 30, 14.5, '908', description2='OPC'), L('Cement 50KG', 20, 14.5, '909', description2='SRC'),
          L('Cement 50KG', 5, 14.5, '925', unit='bag'), L('Cement 50KG', 7, 14.5, '925', tax_pct=0)])
ck('a different description, unit or tax is a different line', len(main.lpo_print_lines(s.get(models.PurchaseOrder, o3['id']))) == 4)
# spaces and capitals typed differently are the same material
o4 = lpo([L('Cement 50KG', 30, 14.5, '908'), L('cement  50kg ', 20, 14.5, '909')])
p4 = main.lpo_print_lines(s.get(models.PurchaseOrder, o4['id']))
ck('typed with other spacing or capitals: still one line, printed as the first was typed', len(p4) == 1 and p4[0].qty == 50 and p4[0].description == 'Cement 50KG', [(l.description, l.qty) for l in p4])
# an ordinary LPO prints line for line, as before
o5 = lpo([L('Cement 50KG', 30, 14.5, ''), L('Cement 50KG', 20, 14.5, '')], combined=False)
ck('an ordinary (not combined) LPO prints line for line, as before', [l.qty for l in main.lpo_print_lines(s.get(models.PurchaseOrder, o5['id']))] == [30, 20])
# discount and round off: same total either way
o6 = lpo([L('Cement 50KG', 33.333, 14.55, '908'), L('Cement 50KG', 21.667, 14.55, '909'), L('Cement 50KG', 9.091, 14.55, '925')], discount=2.5, round_off=-0.37)
po6 = s.get(models.PurchaseOrder, o6['id']); d6 = main._lpo_for_print(po6)
ck('odd quantities, a discount and a round off: the one line comes to the same sub total as the three',
   len(d6['lines']) == 1 and abs(d6['lines'][0]['qty'] - 64.091) < 1e-9 and abs(d6['lines'][0]['qty'] * 14.55 - sum(l.qty * l.rate for l in po6.lines)) < 1e-6
   and abs(d6['total'] - main.lpo_total(po6)) < 1e-9, (d6['lines'], d6['total']))
ck('...and the quantity prints as typed, never rounded', main.lpo_qty(d6['lines'][0]['qty']) == '64.091', main.lpo_qty(d6['lines'][0]['qty']))
s.close()

page = open('../app-classic.html', encoding='utf-8').read()
ck('the form shows them as one row: followers kept but not shown, the total not typed there',
   'const hid = lpoGrpHidden(i);' in page and 'class="lpo-dup" style="display:none;"' in page and 'q.readOnly = true; q.classList.add("lpo-tot")' in page)
ck('...one rate for all of them, taken before totals, the Combined box and saving', page.count('lpoGrpSync();') >= 4
   and '"item_id", "description", "description2", "unit", "rate", "tax_pct", "service", "bold", "style", "description_fmt"' in page)
ck('...each site\'s quantity is typed in the Combined LPO box', 'class="cmb-qty"' in page and 'onchange="lpoCmbQty(${i}, this.value)"' in page)
ck('...only on a Combined LPO, and "show separately" puts the rows back', 'if (!lpoCmbOn()) return;' in page and 'function lpoUngroup(i)' in page and '>show separately</a>' in page)
ck('...the same material asked by two or more sites switches Combined on by itself', 'if (sameForSites && !lpoCmbOn())' in page)
ck('what is saved is every line, as before (nothing merged on the way to the server)', 'const lines = lpoLines\n    .filter(l => (l.description || "").trim() && (parseFloat(l.qty) || 0) > 0)' in page)
ck('the built page carries it (python3 deploy/build_temporary_pages.py)', 'lpoGrpSync' in open('../app.html', encoding='utf-8').read())
print("\nALL PASS" if not FAIL else f"\n{len(FAIL)} FAILED")
sys.exit(1 if FAIL else 0)

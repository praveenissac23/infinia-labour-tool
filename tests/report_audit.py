import re
"""Every report column must carry real data.

Run: cd app && DATABASE_URL=sqlite:////tmp/ra.db python3 ../tests/report_audit.py

Seeds a realistic store - consumable, asset and rental; a request
ordered and part-delivered; issues, a return and a loss - then checks
that no report column is empty for every row, and that every export
builds. Exists because columns were reading fields nothing ever fills
(hired from, since, category, value), so reports showed rows of dashes
while the store already knew the answers.
"""
import sys
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main

db = database.SessionLocal()
# 'staff' was retired; the keeper is an office login like the real one.
for u, r in [('office', 'office'), ('site', 'site'), ('keeper', 'office')]:
    db.add(models.User(username=u, hashed_password=auth.hash_password('p'), full_name=u, role=r))
db.commit(); db.close()
c = TestClient(main.app)
def H(u): return {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': u, 'password': 'p'}).json()['access_token']}
O, S, K = H('office'), H('site'), H('keeper')

items = {}
for name, unit, typ in [('Cement OPC 42.5', 'bag', 'consumable'), ('Steel Rebar 20MM', 't', 'consumable'),
                        ('Steel Cutting Machine', 'pcs', 'asset'), ('Scaffold Ledger 1.20M', 'pcs', 'rental')]:
    body = {'name': name, 'unit': unit, 'item_type': typ, 'reorder_level': 20}
    if typ == 'rental':
        body['rental_supplier'] = 'Al Raha Scaffolding'
    items[name] = c.post('/store/items', json=body, headers=K).json()
mr = c.post('/store/requests', json={'site': '904', 'requested_by': 'febiyan', 'needed_by': '2026-09-02',
    'urgency': 'urgent', 'notes': '', 'lines': [
      {'item_id': items['Cement OPC 42.5']['id'], 'qty_requested': 100, 'unit': 'bag', 'purpose': 'slab', 'item_type': 'consumable', 'description': '', 'est_cost': 0, 'notes': ''},
      {'item_id': items['Steel Rebar 20MM']['id'], 'qty_requested': 10, 'unit': 't', 'purpose': 'columns', 'item_type': 'consumable', 'description': '', 'est_cost': 0, 'notes': ''}]}, headers=S).json()
L = [l['id'] for l in mr['lines']]
c.post(f"/store/requests/{mr['id']}/status", json={'status': 'ordered', 'supplier': 'Al Raha Trading',
    'contact_person': 'bijuam', 'phone': '050090890', 'expected_on': '2026-09-01', 'line_ids': L}, headers=O)
c.post(f"/store/requests/{mr['id']}/receive-bulk", json={'supplier': 'Al Raha Trading', 'reference': 'INV-778',
    'notes': '', 'received_on': '2026-08-25', 'lines': [{'line_id': L[0], 'qty': 100}]}, headers=K)
for it, q, sup, dt in [('Steel Cutting Machine', 2, 'Newstar', '2026-08-20'), ('Scaffold Ledger 1.20M', 700, 'Gateway Scaffolding', '2026-08-18')]:
    c.post('/store/movements', json={'item_id': items[it]['id'], 'kind': 'in', 'qty': q, 'location': '',
        'supplier': sup, 'reference': 'DO-1', 'moved_on': dt}, headers=K)
# Cement ordered for 904 is delivered to 904, so there is none standing
# in the central store to issue out of - that is what the delivery does.
c.post('/store/movements', json={'item_id': items['Steel Cutting Machine']['id'], 'kind': 'out', 'qty': 1, 'location': '904', 'incharge': 'Akhil', 'moved_on': '2026-08-27', 'reference': 'MI-0003', 'notes': 'For the raft'}, headers=K)
c.post('/store/movements', json={'item_id': items['Scaffold Ledger 1.20M']['id'], 'kind': 'out', 'qty': 125, 'location': '905', 'incharge': 'Raj', 'moved_on': '2026-08-26'}, headers=K)
c.post('/store/movements', json={'item_id': items['Steel Cutting Machine']['id'], 'kind': 'out', 'qty': 1, 'location': '907', 'incharge': 'Muhsina', 'moved_on': '2026-08-28'}, headers=K)
c.post('/store/movements', json={'item_id': items['Scaffold Ledger 1.20M']['id'], 'kind': 'lost', 'qty': 5, 'from_location': '905', 'incharge': 'Raj', 'moved_on': '2026-08-30', 'notes': 'damaged on site'}, headers=K)

bad = []
for k in ["stock", "low", "by_site", "purchases", "usage", "assets", "lost", "hired"]:
    d = c.get(f'/store/report?kind={k}', headers=K)
    if d.status_code != 200:
        print(f"FAIL {k:12} HTTP {d.status_code}"); bad.append(k); continue
    rows = d.json().get('rows', [])
    if not rows:
        print(f"     {k:12} (no rows)"); continue
    empt = [col for col in rows[0] if all(r.get(col) in (None, "", "-", {}, []) for r in rows)]
    print(("FAIL " if empt else "PASS ") + f"{k:12} {len(rows):2} rows, {len(rows[0]):2} cols" + (f"   EMPTY: {empt}" if empt else ""))
    if empt: bad.append(k)

# A typo or retired report must fail loudly, not quietly return stock.
if c.get('/store/report?kind=nonsense', headers=K).status_code != 400:
    print("FAIL unknown report kind is not rejected"); bad.append("unknown-kind")
else:
    print("PASS unknown report kind is rejected")

tok = c.post('/auth/download-token', headers=K).json().get('token', '')
fails = [f"{k} {f}" for k in ["stock", "purchases", "hired", "lost", "assets", "usage", "by_site", "low"]
         for f in ("excel", "pdf")
         if c.get(f'/export/store/report?kind={k}&format={f}&token={tok}', headers=K).status_code != 200]
print(("FAIL exports: " + ", ".join(fails)) if fails else "PASS every export builds")
bad += fails

# ---- What was moved, who took it, and when ---------------------------
# The issued report used to total a material per site, which threw away
# the two things written down when stock is given out: the date and the
# man who signed for it. A total saying 40 bags went to 901 answers
# nobody asking when, or who has them.
import export_web
issued = c.get('/store/report?kind=usage', headers=K).json()['rows']
need = ("date", "given_to", "from", "to", "qty", "name", "unit", "reference")
missing = [col for col in need if not issued or col not in issued[0]]
print(("FAIL " if missing else "PASS ") + "issued report names the day and the man"
      + (f"   MISSING: {missing}" if missing else ""))
if missing: bad.append("usage-columns")
if issued:
    dated = [r for r in issued if r.get("date")]
    named = [r for r in issued if (r.get("given_to") or "-") != "-"]
    ok = len(dated) == len(issued) and named
    print(("PASS " if ok else "FAIL ") + "every issue carries its date, and the men are on it")
    if not ok: bad.append("usage-blank")

# One alignment per column, and the heading takes the same one. A
# centred heading over a left-hand column read as two layouts at once.
al_bad = []
for k in ["stock", "by_site", "usage", "purchases", "assets", "hired", "lost", "low"]:
    rows = c.get(f'/store/report?kind={k}', headers=K).json().get('rows', [])
    if not rows:
        continue
    for col in rows[0]:
        if export_web.col_align(col, rows) not in ("L", "C"):
            al_bad.append(f"{k}.{col}")
print(("FAIL alignment: " + ", ".join(al_bad)) if al_bad
      else "PASS every report column has one settled alignment")
bad += al_bad

# The preview IS the printed sheet, not a plainer table holding the same
# figures: the same letterhead, the same red heading band, the same
# title, the same landscape page. A preview that differs from the file
# it previews gets approved and then something else comes out.
pv_bad = []
for k in ["stock", "usage", "by_site", "assets", "hired", "lost", "purchases", "low"]:
    pv = c.get(f'/export/store/report/view?kind={k}&token={tok}')
    if pv.status_code != 200:
        pv_bad.append(f"{k}:HTTP{pv.status_code}"); continue
    want = {
        "the Infinia logo": 'data:image/png;base64,' in pv.text,
        "the letterhead": "INFINIA CONTRACTING LLC" in pv.text,
        "the brand heading band": "#" + export_web.BRAND_RED in pv.text,
        # A4, the way round this report prints - upright for a narrow
        # one, on its side for a wide one.
        "an A4 page": ("297mm" in pv.text) or ("210mm" in pv.text),
        "the report's own title": (c.get(f'/store/report?kind={k}', headers=K)
                                    .json().get("title", "") in pv.text),
        # Visible text only - the heading cells carry the field name as
        # an attribute so the download can follow a re-ordered column.
        "headings, not field names": "given_to" not in re.sub(r"<[^>]+>", " ", pv.text),
    }
    pv_bad += [f"{k}: no {w}" for w, ok in want.items() if not ok]
print(("FAIL preview: " + "; ".join(pv_bad)) if pv_bad
      else "PASS every preview is the sheet that prints, letterhead and all")
bad += pv_bad

# The page stands up or lies on its side to suit the report, and the
# preview, the PDF and the spreadsheet must all agree on which - a
# preview shown upright while the file comes out sideways is not a
# preview of that file.
import io as _io
from pypdf import PdfReader
from openpyxl import load_workbook
turn_bad = []
for k in ["stock", "usage", "by_site", "assets", "hired", "lost", "purchases", "low"]:
    rows = c.get(f'/store/report?kind={k}', headers=K).json().get('rows', [])
    if not rows:
        continue
    want = export_web.choose_orientation(rows)
    box = PdfReader(_io.BytesIO(
        c.get(f'/export/store/report?kind={k}&format=pdf&token={tok}').content)).pages[0].mediabox
    got_pdf = "landscape" if box.width > box.height else "portrait"
    pv = c.get(f'/export/store/report/view?kind={k}&token={tok}').text
    got_pv = "portrait" if "width:210mm" in pv else "landscape"
    ws = load_workbook(_io.BytesIO(
        c.get(f'/export/store/report?kind={k}&format=excel&token={tok}').content)).active
    if got_pdf != got_pv:
        turn_bad.append(f"{k}: pdf {got_pdf} but preview {got_pv}")
    # openpyxl hands back an int where its own constant is a string.
    if int(ws.page_setup.paperSize or 0) != int(ws.PAPERSIZE_A4):
        turn_bad.append(f"{k}: the sheet is not set to A4")
    if not (ws.page_setup.fitToWidth and ws.sheet_properties.pageSetUpPr.fitToPage):
        turn_bad.append(f"{k}: the sheet does not fit the page width")
    if not ws.print_title_rows:
        turn_bad.append(f"{k}: the heading row does not repeat on later pages")
print(("FAIL print setup: " + "; ".join(turn_bad)) if turn_bad
      else "PASS every report is print-ready, and all three copies agree which way up")
bad += turn_bad

print()
print("REPORTS CLEAN" if not bad else f"{len(bad)} PROBLEM(S): {bad}")
sys.exit(1 if bad else 0)

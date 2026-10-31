"""Purchasing > Suppliers: Delete beside Edit (31 Oct 2026).

A supplier nothing uses is deleted after a yes. One that is used (LPOs, requests, return notes, hired stock,
Estimation subcontracts, a Zoho link ...) is never deleted outright: it is merged into the supplier kept - every
reference moves in one transaction, the kept one's empty boxes are filled from it, the names printed on issued LPOs
stay as printed, and the duplicate is deleted. Live: 216 "Uni Mix Block Industry" and 369 "Unimix Block Industry".

    cp /tmp/claude-0/full.db /tmp/sm.db; cd app && DATABASE_URL=sqlite:////tmp/sm.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 \
        python3 ../tests/supplier_delete_merge_test.py
Zoho is never called (its calls are replaced here and counted).
"""
import os, subprocess, sys, tempfile
from datetime import date

sys.path.insert(0, '.')
from fastapi.testclient import TestClient  # noqa: E402
import database, models, main, auth  # noqa: E402
import zohoapi as Z  # noqa: E402
import estimation as E  # noqa: E402

FAIL = []


def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{str(x)[:500]}]'))
    if not ok:
        FAIL.append(l)


ZCALLS = []
Z.call = lambda *a, **k: ZCALLS.append((a[1:3] if len(a) > 2 else a)) or {}
c = TestClient(main.app, raise_server_exceptions=False); c.__enter__()
H = {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': 'admin', 'password': 'changeme123'}).json()['access_token']}
DL = lambda h=H: c.post('/auth/download-token', headers=h).json()['token']

db = database.SessionLocal()
for un, perms in (("sm_buyer", "approvals,store.purchasing.purchase,store.purchasing.lporegister,store.purchasing.suppliers"),
                  ("sm_nosup", "approvals,store.purchasing.purchase,store.purchasing.lporegister"),
                  ("sm_site", "requests")):
    if not db.query(models.User).filter(models.User.username == un).first():
        db.add(models.User(username=un, full_name=un, role="office", hashed_password=auth.hash_password("pw12345"), permissions=perms))
db.commit()
login = lambda un: {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': un, 'password': 'pw12345'}).json()['access_token']}
HB, HN, HS = login("sm_buyer"), login("sm_nosup"), login("sm_site")


def sup(name, **k):
    s = models.Supplier(name=name, name_key=main._supplier_key(name), active=True, **k)
    db.add(s); db.commit(); return s


keep = sup("Uni Mix Block Industry", contact_person="Rashid", phone="0501112222", email="", trn="", payment_terms="Net 30",
           zoho_id="Z-KEEP")
gone = sup("Unimix Block Industry", contact_person="Sameer", phone="0559998888", email="sales@unimix.ae",
           trn="100223344500003", address="Ajman Industrial 2", zoho_id="Z-GONE")
lone = sup("Never Used Trading", contact_person="X", phone="1", email="x@y.z", trn="1", payment_terms="Due on Receipt")
lone2 = sup("Typed By Mistake")
kid, gid, lid = keep.id, gone.id, lone.id
ck('two names folded differently: two records (the live duplicate)', kid != gid)

# LPOs for each, raised through the screen's own endpoint
def lpo(supplier, lines, d='2026-10-20'):
    r = c.post('/store/purchase/orders', headers=H, json={'supplier_name': supplier, 'order_date': d, 'project_location': '913',
               'lines': [{'description': a, 'qty': q, 'unit': 'nos', 'rate': rt, 'tax_pct': 5} for a, q, rt in lines]})
    assert r.status_code == 200, r.text
    return r.json()


k1 = lpo("Uni Mix Block Industry", [('BLOCK 20CM SOLID', 1000, 3.1)])
g1 = lpo("Unimix Block Industry", [('BLOCK 15CM HOLLOW', 2000, 2.35), ('BLOCK 10CM', 500, 1.9)])
g2 = lpo("Unimix Block Industry", [('BLOCK 20CM SOLID', 800, 3.05)], d='2026-10-22')
ck('the LPOs went to the two records', db.get(models.PurchaseOrder, g1['id']).supplier_id == gid and db.get(models.PurchaseOrder, k1['id']).supplier_id == kid)
# an older order with an empty vendor phone box: it printed the duplicate's phone from its record
og = db.get(models.PurchaseOrder, g2['id']); og.supplier_phone = ""; db.commit()

# every other kind of reference
mr = models.MaterialRequest(ref="MR-SM01", site="913", requested_on=date(2026, 10, 19), supplier_id=gid, status="ordered"); db.add(mr); db.flush()
db.add(models.MaterialRequestLine(request_id=mr.id, description="BLOCK", qty_requested=10, unit="nos", supplier_id=gid, status="approved"))
db.add(models.HireReturn(ref="RN-SM01", supplier_id=gid, supplier_name=gone.name, return_date=date(2026, 10, 21)))
it = db.query(models.StoreItem).first()
db.add(models.StoreMovement(item_id=it.id, kind="in", qty=1, owner_id=gid, supplier=gone.name, moved_on=date(2026, 10, 21)))
db.add(E.EstSub(project_id=1, supplier_id=gid, name="Unimix Block Industry"))
db.add(models.ZohoLog(source="supplier", item_id=gid, ref=gone.name, action="update", kind="contact", zoho_id="Z-GONE"))
db.commit()


def refs(sid):
    return {lab: db.query(model).filter(getattr(model, col) == sid).count() for lab, model, col in main._supplier_refs()} | \
           {"zoho log": db.query(models.ZohoLog).filter(models.ZohoLog.source == "supplier", models.ZohoLog.item_id == sid).count()}


before_g, before_k = refs(gid), refs(kid)
# (each LPO also keeps a material request of its own for the site - those point at the supplier too)
ck('the duplicate is used everywhere: 2 LPOs, requests and their lines, a return note, a movement, a subcontract, a Zoho log',
   before_g['LPOs'] == 2 and before_g['material requests'] >= 1 and before_g['material request lines'] >= 1 and before_g['return notes'] == 1
   and before_g['store movements (hired from it)'] == 1 and before_g['subcontracts / LPOs on Estimation projects'] == 1 and before_g['zoho log'] == 1, before_g)
N_G = sum(before_g.values())

# ---- rights --------------------------------------------------------------------------------------------------
r = c.get(f'/store/suppliers/{lid}/usage', headers=HS)
ck('a login without the purchasing right cannot even ask', r.status_code == 403, r.status_code)
r = c.delete(f'/store/suppliers/{lid}', headers=HS)
ck('... nor delete (403)', r.status_code == 403, r.status_code)
r = c.delete(f'/store/suppliers/{lid}', headers=HN)
ck('a ticked login without the Suppliers tab: refused (same tick as Edit)', r.status_code == 403 and 'Suppliers' in r.text, (r.status_code, r.text))
r = c.post(f'/store/suppliers/{gid}/merge', headers=HN, json={'into': kid})
ck('... and cannot merge', r.status_code == 403, r.status_code)
r = c.put(f'/store/suppliers/{lid}', headers=HN, json={'name': 'Never Used Trading', 'contact_person': 'X', 'phone': '1', 'trn': '1', 'email': 'x@y.z', 'payment_terms': 'Due on Receipt'})
ck('(the same login cannot Edit either - the rights match)', r.status_code == 403, r.status_code)
ck('nothing was deleted by the refused calls', db.get(models.Supplier, lid) is not None)

# ---- delete one nothing uses ------------------------------------------------------------------------------------
u = c.get(f'/store/suppliers/{lid}/usage', headers=HB).json()
ck('unused supplier: usage says nothing uses it', u['in_use'] is False and u['used'] == [], u)
r = c.delete(f'/store/suppliers/{lid}', headers=HB)
ck('unused supplier deleted by the buyer with the Suppliers tab', r.status_code == 200 and r.json()['deleted'] == 'Never Used Trading', r.text)
db.expire_all()
ck('it is gone from the database and the list', db.get(models.Supplier, lid) is None
   and 'Never Used Trading' not in [s['name'] for s in c.get('/store/suppliers', headers=H).json()])
log = db.query(models.AuditLog).filter(models.AuditLog.action == 'delete_supplier').order_by(models.AuditLog.id.desc()).first()
ck('activity log: who and what', log and log.user_id == db.query(models.User).filter(models.User.username == 'sm_buyer').first().id
   and 'Never Used Trading' in log.details, log and log.details)
r = c.delete(f'/store/suppliers/{lone2.id}', headers=H)
ck('the admin deletes one too', r.status_code == 200, r.text)

# ---- a used one: refused, merge offered ---------------------------------------------------------------------------
u = c.get(f'/store/suppliers/{gid}/usage', headers=HB).json()
ck('used supplier: usage counts 2 LPOs and the rest', u['in_use'] and u['lpos'] == 2 and any(x['what'] == 'link to a Zoho vendor' for x in u['used']), u)
ck('the likely duplicate is suggested first: Uni Mix Block Industry', u['likely'] and u['likely'][0]['id'] == kid, u['likely'])
r = c.delete(f'/store/suppliers/{gid}', headers=HB)
ck('plain delete of a used supplier refused, with how many records use it', r.status_code == 400 and '2 LPOs' in r.text and 'Merge' in r.text, r.text)
db.expire_all()
ck('... and nothing moved or deleted', db.get(models.Supplier, gid) is not None and refs(gid) == before_g)
for bad_into, why in ((gid, 'itself'), (0, 'nothing picked'), (999999, 'no such supplier')):
    r = c.post(f'/store/suppliers/{gid}/merge', headers=HB, json={'into': bad_into})
    ck(f'merge into {why}: refused', r.status_code == 400, (r.status_code, r.text))

# what the reports and the printed LPOs say before the merge
rep0 = {x['label']: x for x in c.get('/store/purchase/report?group_by=supplier&date_from=2026-10-01&date_to=2026-10-31', headers=H).json()['rows']}
tot0 = rep0['Uni Mix Block Industry']['total'] + rep0['Unimix Block Industry']['total']
n0 = rep0['Uni Mix Block Industry']['orders'] + rep0['Unimix Block Industry']['orders']
all0 = c.get('/store/purchase/report?group_by=supplier', headers=H).json()['totals']


def pdf_text(oid):
    r = c.get(f'/export/purchase/{oid}?token={DL()}&format=pdf')
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
        f.write(r.content); fp = f.name
    t = subprocess.run(['pdftotext', '-layout', fp, '-'], capture_output=True, text=True).stdout
    os.unlink(fp); return t


pdf0 = {i: pdf_text(i) for i in (g1['id'], g2['id'], k1['id'])}
import re  # noqa: E402
NOTOK = lambda t: ' '.join(re.sub(r'token=[^"&\s]+', 'token=X', t).split())   # its own download token aside; HTML reads runs of spaces as one
html0 = {i: NOTOK(c.get(f'/export/purchase/{i}/view?token={DL()}').text) for i in (g1['id'], g2['id'], k1['id'])}
ck('the older LPO printed the duplicate\'s phone from its record', '0559998888' in pdf0[g2['id']])
nz = len(ZCALLS)

# ---- merge ---------------------------------------------------------------------------------------------------------
r = c.post(f'/store/suppliers/{gid}/merge', headers=HB, json={'into': kid})
ck('merged by the buyer', r.status_code == 200, r.text)
m = r.json()
ck(f'it says what moved: {N_G} records', m['total'] == N_G and m['kept'] == 'Uni Mix Block Industry' and m['removed'] == 'Unimix Block Industry', m)
db.expire_all()
ck('the duplicate is deleted', db.get(models.Supplier, gid) is None)
after_k = refs(kid)
ck('every reference now points at the kept supplier (kept\'s own + the duplicate\'s)', all(after_k[k] == before_k[k] + before_g[k] for k in before_g), (before_k, before_g, after_k))
ck('nothing points at the deleted id any more', all(v == 0 for v in refs(gid).values()), refs(gid))
k = db.get(models.Supplier, kid)
ck('kept supplier keeps its own details (contact Rashid, phone, Net 30)', (k.contact_person, k.phone, k.payment_terms) == ('Rashid', '0501112222', 'Net 30'))
ck('... and its empty boxes are filled from the duplicate (TRN, email, address)', (k.trn, k.email, k.address) == ('100223344500003', 'sales@unimix.ae', 'Ajman Industrial 2'),
   (k.trn, k.email, k.address))
ck('different Zoho vendors: the kept one\'s stays linked', k.zoho_id == 'Z-KEEP', k.zoho_id)
ck('no Zoho call was made', len(ZCALLS) == nz, ZCALLS[nz:])
log = db.query(models.AuditLog).filter(models.AuditLog.action == 'merge_supplier').order_by(models.AuditLog.id.desc()).first()
ck('activity log: who, what, how many moved, the other Zoho vendor noted',
   log and log.user_id == db.query(models.User).filter(models.User.username == 'sm_buyer').first().id and f'{N_G} record(s) moved' in log.details
   and '2 LPOs' in log.details and 'Z-GONE' in log.details and 'Unimix Block Industry' in log.details, log and log.details)
ck('issued LPOs keep the supplier name they were printed with', db.get(models.PurchaseOrder, g1['id']).supplier_name == 'Unimix Block Industry')
pdf1 = {i: pdf_text(i) for i in pdf0}
import difflib  # noqa: E402
ck('LPO PDFs unchanged, word for word (3 LPOs, incl. the older one whose phone came from the record)', pdf1 == pdf0,
   [(i, [x for x in difflib.unified_diff(pdf0[i].splitlines(), pdf1[i].splitlines(), lineterm='', n=0)][:8]) for i in pdf0 if pdf0[i] != pdf1[i]])
ck('preview pages unchanged too (token aside, as the browser shows them)', all(NOTOK(c.get(f'/export/purchase/{i}/view?token={DL()}').text) == html0[i] for i in html0))
rep1 = {x['label']: x for x in c.get('/store/purchase/report?group_by=supplier&date_from=2026-10-01&date_to=2026-10-31', headers=H).json()['rows']}
ck(f'report by supplier: the kept supplier now has both ({tot0:,.2f}, {n0} orders), the duplicate no row',
   'Unimix Block Industry' not in rep1 and abs(rep1['Uni Mix Block Industry']['total'] - tot0) < 0.005 and rep1['Uni Mix Block Industry']['orders'] == n0,
   (rep1.get('Uni Mix Block Industry'), tot0, n0))
all1 = c.get('/store/purchase/report?group_by=supplier', headers=H).json()['totals']
ck('report grand totals unchanged', all(abs(all1[k] - all0[k]) < 0.005 for k in all0), (all0, all1))
r = c.get('/store/purchase/report?group_by=order&supplier=unimix', headers=H).json()
ck('searching the register by the old printed name still finds those LPOs', {x['id'] for x in r['rows']} >= {g1['id'], g2['id']}, [x['label'] for x in r['rows']])
names = [s['name'] for s in c.get('/store/suppliers', headers=H).json()]
ck('the list shows one Uni Mix', names.count('Uni Mix Block Industry') == 1 and 'Unimix Block Industry' not in names)
# a new LPO typed with the old spelling finds a supplier again (a new record), it does not error
r = c.post('/store/purchase/orders', headers=H, json={'supplier_name': 'Uni Mix Block Industry', 'order_date': '2026-10-30',
           'lines': [{'description': 'BLOCK', 'qty': 1, 'unit': 'nos', 'rate': 1, 'tax_pct': 5}]})
ck('a new LPO for the kept name goes to the kept supplier', r.status_code == 200 and db.get(models.PurchaseOrder, r.json()['id']).supplier_id == kid, r.text[:200])

# ---- merge where only the duplicate had a Zoho vendor: the link moves to the kept one -------------------------------
a = sup("Alpha Steel Works", phone="1"); b = sup("Alfa Steel Works", zoho_id="Z-ALPHA")
lpo("Alfa Steel Works", [('REBAR', 1, 10)])
r = c.post(f'/store/suppliers/{b.id}/merge', headers=H, json={'into': a.id})
db.expire_all()
ck('only the duplicate linked to Zoho: the kept one takes over its Zoho vendor', r.status_code == 200 and db.get(models.Supplier, a.id).zoho_id == 'Z-ALPHA'
   and 'Zoho vendor link' in r.json()['filled'], r.text)
ck('still no Zoho call', len(ZCALLS) == nz, ZCALLS[nz:])

db.close()
print(f"{len(FAIL)} FAILED" if FAIL else 'ALL PASS')
sys.exit(1 if FAIL else 0)

"""Purchasing > Suppliers: Delete beside Edit (owner, 31 Oct 2026: "No need to merge. Whatever in past is ok.
I should have a delete option against supplier. I will correct it myself.").

A supplier nothing uses is deleted after a yes. One that is used (LPOs, requests, return notes, hired stock,
Estimation subcontracts, a Zoho link ...) is only taken off the list (suppliers.deleted_at): it no longer shows
on the list or in any supplier picker, and everything already recorded against it - LPO PDFs and previews,
the purchase report (grouped by the name printed on the order, as before), requests, Zoho links - stays
exactly the same. Same right as Edit. No merge any more.

    cp /tmp/claude-0/full.db /tmp/sd.db; cd app && DATABASE_URL=sqlite:////tmp/sd.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 \
        python3 ../tests/supplier_soft_delete_test.py
Zoho is never called (its calls are replaced here and counted).
"""
import os, re, subprocess, sys, tempfile, difflib
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
for un, perms in (("sd_buyer", "store,store.purchasing.purchase,store.purchasing.lporegister,store.purchasing.suppliers"),
                  ("sd_nosup", "approvals,store.purchasing.purchase,store.purchasing.lporegister"),
                  ("sd_site", "requests")):
    if not db.query(models.User).filter(models.User.username == un).first():
        db.add(models.User(username=un, full_name=un, role="office", hashed_password=auth.hash_password("pw12345"), permissions=perms))
db.commit()
login = lambda un: {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': un, 'password': 'pw12345'}).json()['access_token']}
HB, HN, HS = login("sd_buyer"), login("sd_nosup"), login("sd_site")


def sup(name, **k):
    s = models.Supplier(name=name, name_key=main._supplier_key(name), active=True, **k)
    db.add(s); db.commit(); return s


keep = sup("Uni Mix Block Industry", contact_person="Rashid", phone="0501112222", email="r@unimix.ae", trn="100200300400003",
           payment_terms="Net 30")
gone = sup("Unimix Block Industry", contact_person="Sameer", phone="0559998888", email="sales@unimix.ae",
           trn="100223344500003", address="Ajman Industrial 2", zoho_id="Z-GONE")
lone = sup("Never Used Trading", contact_person="X", phone="1", email="x@y.z", trn="1", payment_terms="Due on Receipt")
kid, gid, lid = keep.id, gone.id, lone.id


def lpo(supplier, lines, d='2026-10-20', h=H):
    return c.post('/store/purchase/orders', headers=h, json={'supplier_name': supplier, 'order_date': d, 'project_location': '913',
                  'lines': [{'description': a, 'qty': q, 'unit': 'nos', 'rate': rt, 'tax_pct': 5} for a, q, rt in lines]})


k1 = lpo("Uni Mix Block Industry", [('BLOCK 20CM SOLID', 1000, 3.1)]).json()
g1 = lpo("Unimix Block Industry", [('BLOCK 15CM HOLLOW', 2000, 2.35), ('BLOCK 10CM', 500, 1.9)]).json()
g2 = lpo("Unimix Block Industry", [('BLOCK 20CM SOLID', 800, 3.05)], d='2026-10-22').json()
og = db.get(models.PurchaseOrder, g2['id']); og.supplier_phone = ""; db.commit()   # an older order printing the record's phone
ck('the LPOs went to the two records', db.get(models.PurchaseOrder, g1['id']).supplier_id == gid and db.get(models.PurchaseOrder, k1['id']).supplier_id == kid)

mr = models.MaterialRequest(ref="MR-SD01", site="913", requested_on=date(2026, 10, 19), supplier_id=gid, status="ordered"); db.add(mr); db.flush()
db.add(models.MaterialRequestLine(request_id=mr.id, description="BLOCK", qty_requested=10, unit="nos", supplier_id=gid, status="approved"))
db.add(models.HireReturn(ref="RN-SD01", supplier_id=gid, supplier_name=gone.name, return_date=date(2026, 10, 21)))
it = db.query(models.StoreItem).first()
db.add(models.StoreMovement(item_id=it.id, kind="in", qty=1, owner_id=gid, supplier=gone.name, moved_on=date(2026, 10, 21)))
db.add(E.EstSub(project_id=1, supplier_id=gid, name="Unimix Block Industry"))
db.add(models.ZohoLog(source="supplier", item_id=gid, ref=gone.name, action="update", kind="contact", zoho_id="Z-GONE"))
db.commit()


def refs(sid):
    return {lab: db.query(model).filter(getattr(model, col) == sid).count() for lab, model, col in main._supplier_refs()} | \
           {"zoho log": db.query(models.ZohoLog).filter(models.ZohoLog.source == "supplier", models.ZohoLog.item_id == sid).count()}


before_g, before_k = refs(gid), refs(kid)

# ---- the merge is gone -----------------------------------------------------------------------------------------
r = c.post(f'/store/suppliers/{gid}/merge', headers=H, json={'into': kid})
ck('no merge endpoint any more', r.status_code in (404, 405), r.status_code)

# ---- rights: the same as Edit -----------------------------------------------------------------------------------
FULLSUP = lambda n: {'name': n, 'contact_person': 'X', 'phone': '1', 'trn': '1', 'email': 'x@y.z', 'payment_terms': 'Due on Receipt'}
for who, h in (("a login with the Suppliers tab ticked (store right, no approvals)", HB),
               ("a ticked login without the Suppliers tab", HN), ("a never-ticked requests login", HS)):
    t = sup(f"Rights Check {who[:20]}", contact_person="X", phone="1", email="x@y.z", trn="1", payment_terms="Due on Receipt")
    pe = c.put(f'/store/suppliers/{t.id}', headers=h, json=FULLSUP(t.name)).status_code
    de = c.delete(f'/store/suppliers/{t.id}', headers=h).status_code
    ck(f'{who}: Delete allowed exactly when Edit is (Edit {pe}, Delete {de})', (pe == 200) == (de == 200), (pe, de))
    if h is HN:
        ck('... refused for the login without the Suppliers tab', pe == 403 and de == 403, (pe, de))
    if h is HB:
        ck('... allowed for the one with it', pe == 200 and de == 200, (pe, de))
r = c.get('/store/suppliers', headers={'Authorization': 'Bearer x'})
ck('no login: refused', r.status_code == 401, r.status_code)
ck('nothing else was deleted by those calls', db.get(models.Supplier, lid) is not None)

# ---- unused: hard delete -----------------------------------------------------------------------------------------
u = c.get(f'/store/suppliers/{lid}/usage', headers=HB).json()
ck('unused supplier: usage says nothing uses it', u['in_use'] is False and u['used'] == [], u)
r = c.delete(f'/store/suppliers/{lid}', headers=HB)
ck('... and the same login can Delete it', r.status_code == 200 and r.json()['deleted'] == 'Never Used Trading' and r.json()['kept_for_records'] is False, r.text)
db.expire_all()
ck('it is gone from the database (hard delete) and the list', db.get(models.Supplier, lid) is None
   and 'Never Used Trading' not in [s['name'] for s in c.get('/store/suppliers', headers=H).json()])
log = db.query(models.AuditLog).filter(models.AuditLog.action == 'delete_supplier').order_by(models.AuditLog.id.desc()).first()
ck('activity log: who and what', log and log.user_id == db.query(models.User).filter(models.User.username == 'sd_buyer').first().id
   and 'Never Used Trading' in log.details and 'nothing used it' in log.details, log and log.details)

# ---- what the past looks like before the used one is deleted -------------------------------------------------------
def pdf_text(oid):
    r = c.get(f'/export/purchase/{oid}?token={DL()}&format=pdf')
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
        f.write(r.content); fp = f.name
    t = subprocess.run(['pdftotext', '-layout', fp, '-'], capture_output=True, text=True).stdout
    os.unlink(fp); return t


STRIP = lambda b: re.sub(rb'/(CreationDate|ModDate) \([^)]*\)|/ID\s*\[[^\]]*\]', b'', b)
pdfb = lambda oid: STRIP(c.get(f'/export/purchase/{oid}?token={DL()}&format=pdf').content)
NOTOK = lambda t: re.sub(r'token=[^"&\s]+', 'token=X', t)
OIDS = (g1['id'], g2['id'], k1['id'])
pdf0 = {i: pdf_text(i) for i in OIDS}
pdfb0 = {i: pdfb(i) for i in OIDS}
html0 = {i: NOTOK(c.get(f'/export/purchase/{i}/view?token={DL()}').text) for i in OIDS}
lpo0 = {i: c.get(f'/store/purchase/orders/{i}', headers=H).json() for i in OIDS}
REPS = ['/store/purchase/report?group_by=supplier&date_from=2026-10-01&date_to=2026-10-31', '/store/purchase/report?group_by=supplier',
        '/store/purchase/report?group_by=order&supplier=unimix', '/store/purchase/report?group_by=material']
rep0 = {u_: c.get(u_, headers=H).json() for u_ in REPS}
reg0 = c.get('/store/purchase/orders?limit=500', headers=H).json()
ck('the older LPO prints the supplier record\'s phone', '0559998888' in pdf0[g2['id']])
ck('report by supplier shows the two names apart (as printed)', {'Uni Mix Block Industry', 'Unimix Block Industry'} <=
   {x['label'] for x in rep0[REPS[0]]['rows']}, [x['label'] for x in rep0[REPS[0]]['rows']])
nz = len(ZCALLS)

# ---- used: soft delete ------------------------------------------------------------------------------------------
u = c.get(f'/store/suppliers/{gid}/usage', headers=HB).json()
ck('used supplier: usage counts 2 LPOs and the rest', u['in_use'] and u['lpos'] == 2 and any(x['what'] == 'link to a Zoho vendor' for x in u['used']), u)
r = c.delete(f'/store/suppliers/{gid}', headers=HB)
ck('deleting a used supplier is accepted', r.status_code == 200 and r.json()['kept_for_records'] is True, r.text)
db.expire_all()
g = db.get(models.Supplier, gid)
ck('the row is kept, marked deleted', g is not None and g.deleted_at is not None and g.active is False)
ck('every reference is untouched', refs(gid) == before_g and refs(kid) == before_k, (refs(gid), before_g))
ck('the Zoho link on the record is kept, and no Zoho call was made', g.zoho_id == 'Z-GONE' and len(ZCALLS) == nz, (g.zoho_id, ZCALLS[nz:]))
log = db.query(models.AuditLog).filter(models.AuditLog.action == 'delete_supplier').order_by(models.AuditLog.id.desc()).first()
ck('activity log says it was removed from the list and what still uses it', log and 'removed from the supplier list' in log.details
   and '2 LPOs' in log.details and 'Unimix Block Industry' in log.details, log and log.details)

# hidden from the list and from every picker / search
names = [s['name'] for s in c.get('/store/suppliers', headers=H).json()]
ck('gone from the supplier list (and the LPO / request supplier boxes fed by it)', 'Unimix Block Industry' not in names and 'Uni Mix Block Industry' in names)
meta = c.get('/store/est/meta', headers=H).json()
ck('gone from the Estimation subcontractor picker', gid not in [s['id'] for s in meta['suppliers']] and kid in [s['id'] for s in meta['suppliers']])
zs = c.get('/store/zoho/suppliers', headers=H)
ck('gone from Zoho > Suppliers', zs.status_code == 200 and 'Unimix Block Industry' not in zs.text, zs.status_code)
pdc = c.get('/employees/pdc', headers=H).json()
ck('gone from the PDC payee list', 'Unimix Block Industry' not in pdc.get('payees', []))
docs = c.get('/store/docs', headers=H).json()
ck('gone from the transmittal supplier box', 'Unimix Block Industry' not in docs.get('suppliers', []), docs.get('suppliers', [])[:20])
xl = c.get(f'/export/store/suppliers?token={DL()}')
import openpyxl, io  # noqa: E402
xn = [r_[0] for r_ in openpyxl.load_workbook(io.BytesIO(xl.content)).active.iter_rows(min_row=2, values_only=True)]
ck('gone from the supplier list Excel', 'Unimix Block Industry' not in xn and 'Uni Mix Block Industry' in xn)
rv = c.get(f'/export/store/suppliers/report/view?token={DL()}').text
ck('gone from the supplier list preview', 'Unimix Block Industry' not in rv and 'Uni Mix Block Industry' in rv)
ck('its own Edit / usage / delete answer "not found" now', c.get(f'/store/suppliers/{gid}/usage', headers=H).status_code == 404
   and c.delete(f'/store/suppliers/{gid}', headers=H).status_code == 404
   and c.put(f'/store/suppliers/{gid}', headers=H, json={'name': 'Unimix Block Industry', 'contact_person': 'a', 'phone': '1', 'trn': '1', 'email': 'a@b.c', 'payment_terms': 'x'}).status_code == 404)

# the past exactly as it was
pdf1 = {i: pdf_text(i) for i in OIDS}
ck('LPO PDFs unchanged word for word (incl. the older one whose phone comes from the record)', pdf1 == pdf0,
   [(i, list(difflib.unified_diff(pdf0[i].splitlines(), pdf1[i].splitlines(), lineterm='', n=0))[:8]) for i in OIDS if pdf0[i] != pdf1[i]])
_same = [i for i in OIDS if pdfb(i) == pdfb0[i]]
ck('LPO PDF files byte-identical (creation date / file id aside)', len(_same) == len(OIDS),
   [(i, (lambda a, b, k: (a[k - 60:k + 60], b[k - 60:k + 60]))(pdfb(i), pdfb0[i], next((k for k, (x, y) in enumerate(zip(pdfb(i), pdfb0[i])) if x != y), 0))) for i in OIDS if i not in _same])
ck('LPO previews identical (download token aside)', all(NOTOK(c.get(f'/export/purchase/{i}/view?token={DL()}').text) == html0[i] for i in OIDS))
ck('LPO records identical', all(c.get(f'/store/purchase/orders/{i}', headers=H).json() == lpo0[i] for i in OIDS))
ck('purchase reports identical (by supplier, by order searched by name, by material, all dates)',
   all(c.get(u_, headers=H).json() == rep0[u_] for u_ in REPS), [u_ for u_ in REPS if c.get(u_, headers=H).json() != rep0[u_]])
ck('LPO register identical', c.get('/store/purchase/orders?limit=500', headers=H).json() == reg0)

# an old LPO of the deleted supplier can still be edited and keeps its supplier
o = c.get(f'/store/purchase/orders/{g1["id"]}', headers=H).json()
body = {k: o.get(k) for k in ('supplier_name', 'order_date', 'project_location', 'terms', 'ref', 'notes') if o.get(k) is not None}
if o.get('delivery_date'):
    body['delivery_date'] = o['delivery_date']
body['lines'] = [{'description': l['description'], 'qty': l['qty'], 'unit': l['unit'], 'rate': l['rate'], 'tax_pct': l.get('tax_pct', 5)} for l in o['lines']]
r = c.put(f'/store/purchase/orders/{g1["id"]}', headers=H, json=body)
db.expire_all()
ck('an LPO already raised for it can still be edited, still under it', r.status_code == 200 and db.get(models.PurchaseOrder, g1['id']).supplier_id == gid, r.text[:300])
ck('... and that edit did not put it back on the list', db.get(models.Supplier, gid).deleted_at is not None
   and 'Unimix Block Industry' not in [s['name'] for s in c.get('/store/suppliers', headers=H).json()])
r = lpo("Unimix Block Industry", [('BLOCK', 1, 1)])
ck('a NEW LPO typed with the deleted name is refused, pointing to the list', r.status_code == 400 and 'deleted from the supplier list' in r.text, r.text[:200])
body2 = dict(body, supplier_name='Unimix Block Industry')
r = c.put(f'/store/purchase/orders/{k1["id"]}', headers=H, json=dict(body2, lines=[{'description': 'B', 'qty': 1, 'unit': 'nos', 'rate': 1, 'tax_pct': 5}]))
ck('switching another LPO to the deleted supplier is refused too', r.status_code == 400, r.text[:200])
r = lpo("Uni Mix Block Industry", [('BLOCK', 1, 1)], d='2026-10-30')
ck('a new LPO for the kept name goes to the kept supplier', r.status_code == 200 and db.get(models.PurchaseOrder, r.json()['id']).supplier_id == kid, r.text[:200])

# added again by hand: the same record comes back
r = c.post('/store/suppliers', headers=H, json={'name': 'Unimix Block Industry', 'contact_person': 'Sameer', 'phone': '0559998888',
                                                 'trn': '100223344500003', 'email': 'sales@unimix.ae', 'payment_terms': 'Net 30'})
db.expire_all()
ck('adding the same name again by hand puts the same record back on the list', r.status_code == 200 and r.json()['id'] == gid
   and db.get(models.Supplier, gid).deleted_at is None and 'Unimix Block Industry' in [s['name'] for s in c.get('/store/suppliers', headers=H).json()], r.text[:200])

db.close()
print(f"{len(FAIL)} FAILED" if FAIL else 'ALL PASS')
sys.exit(1 if FAIL else 0)

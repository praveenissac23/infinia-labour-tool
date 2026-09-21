"""A backup has to bring back everything, or it is not a backup.

Run: cd app && DATABASE_URL=sqlite:////tmp/bc.db python3 ../tests/backup_completeness_test.py

Builds a company with every kind of record in it - attendance, payroll,
adjustments, the store, purchase orders, settings, monthly notes - takes
a backup, destroys the lot, restores, and checks each one came back.
Exists because purchase orders were captured in the snapshot and never
put back by the restore, and the settings table was not captured at all.
"""
import sys, json, warnings
warnings.simplefilter('ignore')
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main

db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Praveen', role='admin'))
db.add(models.Employee(emp_no='F-701', name='RAJAN', trade='MASON', total_salary=2500, basic_salary=1500, active=True))
db.add(models.Site(code='901', plot_no='P-901', active=True))
db.add(models.Engineer(name='Febiyan', mobile='0501234567', active=True))
db.commit(); db.close()
c = TestClient(main.app, raise_server_exceptions=False)
H = {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': 'admin', 'password': 'p'}).json()['access_token']}
FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{str(x)[:160]}]'))
    if not ok: FAIL.append(l)

CYCLE = 'September 2026'
# ---- A company with something of everything in it --------------------
c.post('/attendance/save', json={'month_year': CYCLE, 'rows': [
    {'emp_no': 'F-701', 'full_date': f'2026-09-{d:02d}', 'am': 'Present', 'pm': 'Present',
     'site': '901', 'engineer': 'Febiyan', 'ot': 2, 'bh': 0, 'comments': ''} for d in range(1, 11)]}, headers=H)
sid = c.get(f'/summaries/{CYCLE}', headers=H).json()[0]['id']
c.post(f'/summaries/{sid}/adjustments', json={'description': 'Advance', 'amount': 300, 'is_deduction': True}, headers=H)
cem = c.post('/store/items', json={'name': 'Cement OPC 50kg', 'unit': 'bag', 'item_type': 'consumable', 'reorder_level': 20}, headers=H).json()
c.post('/store/movements', json={'item_id': cem['id'], 'kind': 'in', 'qty': 200, 'location': '',
                                 'supplier': 'Al Raha Trading LLC', 'moved_on': '2026-09-05'}, headers=H)
mr = c.post('/store/requests', json={'site': '901', 'requested_by': 'Febiyan', 'needed_by': '2026-09-25',
    'urgency': 'urgent', 'notes': 'slab', 'lines': [{'item_id': cem['id'], 'qty_requested': 100, 'unit': 'bag',
    'purpose': 'slab', 'item_type': 'consumable', 'description': '', 'est_cost': 16, 'notes': ''}]}, headers=H).json()
po = c.post('/store/purchase/orders', json={'order_date': '2026-09-18', 'supplier_name': 'Al Raha Trading LLC',
    'supplier_trn': '100200300', 'request_id': mr['id'],
    'lines': [{'item_id': cem['id'], 'description': 'Cement OPC 50kg', 'qty': 100, 'unit': 'bag',
               'rate': 16.5, 'tax_pct': 5}]}, headers=H).json()
c.post(f'/reports/monthly-notes/{CYCLE}', json={'emp_no': 'F-701', 'note': 'Advance recovered this month.'}, headers=H)
c.post('/settings/company', json={'store_incharge': 'Amal', 'company_trn': '100999888'}, headers=H)

def snapshot():
    return {
        'workers': len(c.get('/employees', headers=H).json()),
        'attendance': len(c.get('/attendance/2026-09-05', headers=H).json()),
        'summaries': len(c.get(f'/summaries/{CYCLE}', headers=H).json()),
        'adjustments': sum(len(x.get('adjustments') or []) for x in c.get(f'/summaries/{CYCLE}', headers=H).json()),
        'materials': len(c.get('/store/items', headers=H).json()),
        'movements': len(c.get('/store/movements', headers=H).json()),
        'requests': len(c.get('/store/requests', headers=H).json()),
        'suppliers': len(c.get('/store/suppliers', headers=H).json()),
        'orders': len(c.get('/store/purchase/orders', headers=H).json()),
        'order_lines': sum(len(c.get(f"/store/purchase/orders/{o['id']}", headers=H).json().get('lines') or [])
                           for o in c.get('/store/purchase/orders', headers=H).json()),
        'monthly_notes': c.get(f'/reports/monthly-notes/{CYCLE}', headers=H).json()['notes'],
        'company': {k: v for k, v in c.get('/settings/company', headers=H).json().items() if k in ('store_incharge', 'company_trn')},
        'stock': next(s['central'] for s in c.get('/store/stock', headers=H).json() if s['item_id'] == cem['id']),
    }

before = snapshot()
ck('the company is fully populated', before['orders'] == 1 and before['order_lines'] == 1
   and before['monthly_notes'] and before['company'].get('store_incharge') == 'Amal', before)

# ---- Back it up, then destroy everything -----------------------------
bid = c.post('/backup/create', headers=H).json()['id']
r = c.post('/backup/fresh-start', json={'confirm': 'CLEAR EVERYTHING'}, headers=H)
ck('everything wiped', r.status_code == 200, r.text[:160])
d = database.SessionLocal()
d.query(models.Setting).delete(); d.commit(); d.close()      # settings gone too
gone = snapshot()
ck('nothing left to restore from but the backup',
   gone['attendance'] == 0 and gone['orders'] == 0 and not gone['monthly_notes'], gone)

# ---- Restore -----------------------------------------------------------
r = c.post(f'/backup/{bid}/restore', headers=H)
ck('restore runs', r.status_code == 200, r.text[:200])
after = snapshot()

for key in ('workers', 'attendance', 'summaries', 'adjustments', 'materials',
            'movements', 'requests', 'suppliers', 'stock'):
    ck(f'{key} restored: {before[key]}', after[key] == before[key], f'{before[key]} -> {after[key]}')
ck('purchase orders restored', after['orders'] == before['orders'], f"{before['orders']} -> {after['orders']}")
ck('their lines restored too', after['order_lines'] == before['order_lines'], f"{before['order_lines']} -> {after['order_lines']}")
ck('the order keeps its number and supplier',
   any(o['ref'] == po['ref'] and o['supplier'] == 'Al Raha Trading LLC'
       for o in c.get('/store/purchase/orders', headers=H).json()),
   c.get('/store/purchase/orders', headers=H).json()[:1])
ck('monthly notes restored', after['monthly_notes'] == before['monthly_notes'], f"{before['monthly_notes']} -> {after['monthly_notes']}")
ck('company settings restored', after['company'] == before['company'], f"{before['company']} -> {after['company']}")
ck('the admin can still sign in after a restore',
   c.post('/auth/login', data={'username': 'admin', 'password': 'p'}).status_code == 200)

# ---- The guard: every table the app defines is in the snapshot -------
# This is what keeps the backup complete as the app grows. Add a table
# next year and it is in the backup the day it is created; if that ever
# stops being true, this fails rather than being discovered the day
# someone needs to restore.
d = database.SessionLocal()
raw = main._backup_json(d.query(models.Backup).order_by(models.Backup.id.desc()).first())
d.close()
declared = {t.name for t in models.Base.metadata.sorted_tables}
skipped = main.BACKUP_SKIP_TABLES
missing = sorted(declared - skipped - set(raw.keys()))
ck(f'every one of the {len(declared - skipped)} tables is in the snapshot', not missing, missing)
ck('the activity log is kept too', 'audit_log' in raw, sorted(raw.keys()))
ck('only the backups table is skipped', skipped == {'backups'}, skipped)
ck('the snapshot names the tables it carries', set(raw.get('tables', [])) == declared - skipped,
   sorted(set(raw.get('tables', [])) ^ (declared - skipped)))

# ---- Stored compressed, and still readable either way ----------------
d = database.SessionLocal()
b = d.query(models.Backup).order_by(models.Backup.id.desc()).first()
ck('the snapshot is stored compressed', b.data.startswith('gz:'), b.data[:12])
ck('and reads back as the same data', main._backup_json(b)['format'] == 3)
# Measured on the records only: the signature and logo are images, which
# are already compressed and so ride along at their own size.
_data_only = {k: v for k, v in main.build_backup_data(d).items() if k != 'files'}
plain = json.dumps(_data_only, default=str)
ck('the records compress to a fraction of their size',
   len(main._backup_dump(_data_only)) < len(plain) * 0.5,
   f'{len(main._backup_dump(_data_only))} vs {len(plain)}')
# A backup written by the old version, uncompressed, must still restore.
d.add(models.Backup(created_by=None, trigger='manual', data=plain)); d.commit()
old_id = d.query(models.Backup).order_by(models.Backup.id.desc()).first().id
d.close()
ck('an uncompressed backup from an older version still restores',
   c.post(f'/backup/{old_id}/restore', headers=H).status_code == 200)
ck('and the data is still all there', snapshot()['orders'] == before['orders'])

# ---- The downloaded file is readable JSON, not the stored blob -------
tok = c.post('/auth/download-token', headers=H).json()['token']
dl = c.get(f'/backup/{bid}/download?token={tok}')
ck('a downloaded backup is plain JSON', dl.status_code == 200 and json.loads(dl.content)['format'] == 3,
   dl.content[:40])

# ---- The files on disk: the signature and the logo -------------------
# They live in a directory, not a table, and were the last thing a
# restore could not bring back.
import os, base64, export_web
sig = os.path.join(export_web.DATA_DIR, 'signature.png')
open(sig, 'wb').write(b'PRAVEEN-SIGNATURE-IMAGE-BYTES')
open(os.path.join(export_web.DATA_DIR, 'stamp.png'), 'wb').write(b'A-FILE-ADDED-LATER')
bid2 = c.post('/backup/create', headers=H).json()['id']
d = database.SessionLocal()
raw2 = main._backup_json(d.query(models.Backup).filter(models.Backup.id == bid2).first())
d.close()
ck('the signature is in the snapshot', 'signature.png' in (raw2.get('files') or {}), sorted((raw2.get('files') or {})))
ck('and so is a file added later, without anyone listing it', 'stamp.png' in (raw2.get('files') or {}))
ck('the logo travels too', 'logo.png' in (raw2.get('files') or {}))
ck('stored as the real bytes',
   base64.b64decode(raw2['files']['signature.png']) == b'PRAVEEN-SIGNATURE-IMAGE-BYTES')

os.remove(sig); os.remove(os.path.join(export_web.DATA_DIR, 'stamp.png'))
ck('signature really is gone before the restore', not os.path.exists(sig))
ck('restore runs with files in it', c.post(f'/backup/{bid2}/restore', headers=H).status_code == 200)
ck('the signature is back on disk', os.path.exists(sig))
ck('byte for byte', open(sig, 'rb').read() == b'PRAVEEN-SIGNATURE-IMAGE-BYTES')
ck('and the later file with it', os.path.exists(os.path.join(export_web.DATA_DIR, 'stamp.png')))
ck('the app can see its signature again',
   c.get('/store/purchase/signature-status', headers=H).json().get('present') is not False)
# A snapshot must never be able to write outside its own directory.
before_files = set(os.listdir(export_web.DATA_DIR))
main.restore_backup_files({'../../escaped.png': base64.b64encode(b'x').decode()})
ck('a path in a filename cannot escape the directory',
   not os.path.exists(os.path.join(export_web.DATA_DIR, '..', '..', 'escaped.png')))
for junk in ('stamp.png', 'signature.png', 'escaped.png'):
    try: os.remove(os.path.join(export_web.DATA_DIR, junk))
    except OSError: pass

# ---- One routine snapshot a day, not two or three --------------------
# Signing in took one and downloading a copy took another, both holding
# the same company, so a busy day kept three copies of itself.
d = database.SessionLocal()
d.query(models.Backup).delete(); d.commit(); d.close()
c.post('/auth/login', data={'username': 'admin', 'password': 'p'})      # the auto one
tok = c.post('/auth/download-token', headers=H).json()['token']
c.get(f'/backup/latest/download?token={tok}')                            # would have taken another
c.get(f'/backup/latest/download?token={tok}')
c.post('/auth/login', data={'username': 'admin', 'password': 'p'})
d = database.SessionLocal()
routine = d.query(models.Backup).filter(models.Backup.trigger.in_(main.ROUTINE_TRIGGERS)).all()
ck('four routine events in one day leave one snapshot', len(routine) == 1,
   [(b.id, b.trigger) for b in routine])
# A deliberate one still stands beside it.
c.post('/backup/create', headers=H)
kinds = [b.trigger for b in d.query(models.Backup).all()]
d.close()
ck('a manual backup is kept alongside', sorted(kinds) == ['auto', 'manual'] or sorted(kinds) == ['daily', 'manual'], kinds)

print('\n' + ('BACKUP IS COMPLETE AND RESTORABLE' if not FAIL else f'{len(FAIL)} FAILED: ' + '; '.join(FAIL)))
sys.exit(1 if FAIL else 0)

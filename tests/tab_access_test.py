"""Settings > Access, tab by tab: ticks, what they open, what the server refuses,
and nobody changed by the arrival of ticks.

Run: cd app && rm -f /tmp/ta.db && DATABASE_URL=sqlite:////tmp/ta.db python3 ../tests/tab_access_test.py
"""
import sys
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main, tabrights, people

FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{x}]'))
    if not ok: FAIL.append(l)

# ---- The tree --------------------------------------------------------------
routes = set()
def _collect(rs):
    for r in rs:
        if hasattr(r, 'original_router'):
            _collect(r.original_router.routes)
        elif hasattr(r, 'path'):
            for m in (getattr(r, 'methods', None) or []):
                routes.add((m, r.path))
_collect(main.app.routes)
ck('every gated endpoint exists', all(k in routes for k in tabrights.GATES), [k for k in tabrights.GATES if k not in routes])
named = {x for v in tabrights.GATES.values() if isinstance(v, list) for x in v}
ck('every tab a gate names is in the tree', named <= set(tabrights.LEAVES), named - set(tabrights.LEAVES))
grants = {g for l in tabrights.LEAVES.values() for g in l['grant']}
ck('every right can be given by a tick', all(s in grants for s in main.ALL_SCREENS if s != 'settings'),
   [s for s in main.ALL_SCREENS if s not in grants])
ck('pages in the app order', [p['id'] for p in tabrights.TREE] == ['dashboard', 'attendance', 'people', 'payroll', 'store', 'expiry', 'accounts', 'reports', 'settings'])
ck('three levels: page > tab > tab inside', 'store.store.items' in tabrights.LEAVES and 'people.leave.office' in tabrights.LEAVES
   and 'accounts.petty.pro' in tabrights.LEAVES and 'payroll.hrpayroll.loans' in tabrights.LEAVES)

# ---- Logins ------------------------------------------------------------------
db = database.SessionLocal()
U = lambda n, perms, role='office': models.User(username=n, hashed_password=auth.hash_password('p'), full_name=n, role=role, permissions=perms)
db.add(U('admin', '', 'admin'))
db.add(U('oldkeeper', 'dashboard,store,storekeeper,requests,settings'))          # never ticked
db.add(U('oldhr', 'settings,hrpayroll,people_labour,people_office,expiry'))      # never ticked
db.add(U('blank', '', 'office'))                                                 # role defaults
db.add(U('acc', 'settings,settings_access,store,storekeeper,requests'))          # Access tab, old style
db.add(models.Employee(emp_no='F-1', name='LABOUR ONE', total_salary=1000, basic_salary=600, active=True))
db.add(models.Employee(emp_no='IC1', name='OFFICE ONE', staff=True, pay_group='staff', designation='X', total_salary=9000, basic_salary=4000, active=True))
db.add(models.StoreItem(code='ITM1', name='Cement', unit='bag', item_type='consumable', active=True))
db.add(models.Site(code='913', active=True))
db.commit()
ids = {u.username: u.id for u in db.query(models.User).all()}
db.close()

c = TestClient(main.app)
tok = lambda u: {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': u, 'password': 'pppppp' if u in ('amal', 'clerk', 'pf') else 'p'}).json()['access_token']}
A = tok('admin')
me = lambda h: c.get('/permissions/me', headers=h).json()

# ---- Nothing changes for a login never ticked -----------------------------------
for name in ('oldkeeper', 'oldhr', 'blank'):
    m = me(tok(name))
    ck(f'{name}: tabs = what its rights opened before', m['tabs'] == tabrights.from_rights(m['screens']), m['tabs'])
OK_ = tok('oldkeeper')
ck('old keeper: every store tab', {'store.store.home', 'store.store.items', 'store.store.give', 'store.rentals.hire', 'reports.storerep.usage'} <= set(me(OK_)['tabs']))
r = c.post('/store/items', headers=OK_, json={'code': 'ITM1', 'name': 'Cement', 'unit': 'bag', 'item_type': 'consumable'})
ck('old keeper: still edits the material list', r.status_code == 200, r.text[:150])
ck('old keeper: still reads every store report', c.get('/store/report?kind=usage', headers=OK_).status_code == 200)
OH = tok('oldhr')
ck('old HR: sees both registers', c.get('/employees/people?group=office', headers=OH).status_code == 200
   and c.get('/employees/people?group=labour', headers=OH).status_code == 200)
ck('old HR: client birthdays as before (office register)', c.get('/employees/people/birthday-contacts', headers=OH).status_code == 200)
ck('old HR: loans export as before', c.get(f"/export/payroll/loans?token={auth.create_download_token('oldhr')}").status_code == 200)

# ---- A role ticked tab by tab ----------------------------------------------------
keeper_tabs = ['dashboard.dashboard', 'store.store.home', 'store.store.give', 'store.store.arrive',
               'store.requests.requests', 'store.requests.followup', 'reports.storerep.stock', 'reports.storerep.usage',
               'people.leave.labour', 'people.bday.labour', 'accounts.petty.site']
r = c.post('/permissions/roles', headers=A, json={'name': 'Store keeper', 'tabs': keeper_tabs})
ck('role saved from ticks', r.status_code == 200 and sorted(r.json()['tabs']) == sorted(keeper_tabs), r.text[:300])
role = r.json()
ck('ticks bring the rights behind them', set(role['screens']) == {'dashboard', 'store', 'storekeeper', 'requests', 'people_labour', 'petty_site', 'settings'}, role['screens'])
ck('unknown tick refused', c.post('/permissions/roles', headers=A, json={'name': 'Bad', 'tabs': ['store.nope']}).status_code == 400)
r = c.post('/permissions/roles/new-user', headers=A, json={'username': 'amal', 'full_name': 'Amal', 'password': 'pppppp', 'role_id': role['id']})
ck('login made on the role', r.status_code == 200, r.text)
AM = tok('amal')
m = me(AM)
ck('login carries the ticks', sorted(m['tabs']) == sorted(keeper_tabs), m['tabs'])

# What the server lets him do
ck('reads stock on hand', c.get('/store/report?kind=stock', headers=AM).status_code == 200)
ck('reads Issued to sites (ticked)', c.get('/store/report?kind=usage', headers=AM).status_code == 200)
r = c.get('/store/report?kind=site_cost', headers=AM)
ck('Site costs report refused (not ticked)', r.status_code == 403 and 'Site costs' in r.text, r.text[:200])
r = c.post('/store/items', headers=AM, json={'code': 'ITM1', 'name': 'Cement OPC', 'unit': 'bag', 'item_type': 'consumable'})
ck('editing the material list refused (Material list not ticked)', r.status_code == 403 and 'Material list' in r.text, r.text[:200])
r = c.post('/store/items', headers=AM, json={'name': 'Plywood 18mm', 'unit': 'sheet', 'item_type': 'consumable'})
ck('adding a new material on a delivery still allowed', r.status_code == 200, r.text[:200])
r = c.post('/store/movements', headers=AM, json={'item_id': 1, 'kind': 'in', 'qty': 10, 'location': '', 'moved_on': str(main._dubai_today())})
ck('material arrived (ticked)', r.status_code == 200, r.text[:200])
r = c.post('/store/movements', headers=AM, json={'item_id': 1, 'kind': 'lost', 'qty': 1, 'from_location': '', 'location': '', 'moved_on': str(main._dubai_today())})
ck('lost / correction refused (Returns, lost & corrections not ticked)', r.status_code == 403, r.text[:200])
ck('purchase order refused (no Purchasing tick, no right)', c.post('/store/purchase/orders', headers=AM, json={}).status_code == 403)
ck('return note refused (Rentals not ticked)', c.post('/store/returns', headers=AM, json={}).status_code == 403)
# Staff: leave for labour only
ck('labour leave list', c.get('/employees/people/leave-register?group=labour', headers=AM).status_code == 200)
rr = c.get('/employees/people?group=labour', headers=AM)
ck('labour register shows nobody (Register not ticked)', rr.status_code == 200 and rr.json()['rows'] == [], rr.text[:150])
ck('office leave refused', c.get('/employees/people/leave-register?group=office', headers=AM).status_code == 403)
ck('person file refused without Register', c.get('/employees/people/F-1', headers=AM).status_code == 403)
ck('client birthdays refused (Clients not ticked)', c.get('/employees/people/birthday-contacts', headers=AM).status_code == 403)
bd = c.get('/employees/people/birthdays/upcoming', headers=AM)
ck('birthdays: labour only', bd.status_code == 200 and all(x['group'] in ('labour',) for x in bd.json()['rows']), bd.text[:200])

# ---- Office payroll section by section -----------------------------------------
r = c.post('/permissions/roles', headers=A, json={'name': 'Payroll clerk', 'tabs': ['payroll.hrpayroll.cycle', 'payroll.hrpayroll.leave']})
c.post('/permissions/roles/new-user', headers=A, json={'username': 'clerk', 'full_name': 'Clerk', 'password': 'pppppp', 'role_id': r.json()['id']})
CL = tok('clerk')
ck('clerk: office payroll opens', c.get('/employees/staff', headers=CL).status_code == 200)
r = c.post('/employees/loans', headers=CL, json={'emp_no': 'IC1', 'amount': 100})
ck('clerk: loans refused (Loans not ticked)', r.status_code == 403 and 'Loans' in r.text, r.text[:200])
ck('clerk: loans report refused', c.get(f"/export/payroll/loans?token={auth.create_download_token('clerk')}").status_code == 403)
ck('clerk: gratuity refused', c.get('/employees/staff/IC1/settlement', headers=CL).status_code == 403)
ck('clerk: statement allowed', c.get(f"/export/payroll/statement?token={auth.create_download_token('clerk')}").status_code != 403)

# ---- Invoices: tax and proforma apart -----------------------------------------
r = c.post('/permissions/roles', headers=A, json={'name': 'Proforma only', 'tabs': ['accounts.proforma']})
c.post('/permissions/roles/new-user', headers=A, json={'username': 'pf', 'full_name': 'PF', 'password': 'pppppp', 'role_id': r.json()['id']})
PF = tok('pf')
ck('proforma list', c.get('/employees/accounts/invoices?kind=proforma', headers=PF).status_code == 200)
ck('tax invoices refused', c.get('/employees/accounts/invoices?kind=tax', headers=PF).status_code == 403)
ck('a tax invoice cannot be raised', c.post('/employees/accounts/invoices', headers=PF, json={'kind': 'tax'}).status_code == 403)

# ---- Untick all / tick all ----------------------------------------------------
r = c.post('/permissions/roles', headers=A, json={'id': role['id'], 'name': 'Store keeper', 'tabs': []})
ck('untick all: nothing but own settings', r.status_code == 200 and r.json()['tabs'] == [] and r.json()['screens'] == ['settings'], r.json())
ck('the login follows at once', me(tok('amal'))['tabs'] == [] and c.get('/store/stock', headers=tok('amal')).status_code == 403)
r = c.post('/permissions/roles', headers=A, json={'id': role['id'], 'name': 'Store keeper', 'tabs': sorted(tabrights.LEAVES)})
ck('tick all: every tab', sorted(r.json()['tabs']) == sorted(tabrights.LEAVES))
ck('tick all: every right', set(r.json()['screens']) == set(main.ALL_SCREENS), set(main.ALL_SCREENS) - set(r.json()['screens']))
c.post('/permissions/roles', headers=A, json={'id': role['id'], 'name': 'Store keeper', 'tabs': keeper_tabs})

# ---- Nobody climbs above what he holds -----------------------------------------
db = database.SessionLocal()
db.query(models.User).filter_by(username='acc').first().permissions = tabrights.stored(
    ['settings.access', 'store.store.home', 'store.store.give'], main.ALL_SCREENS)
db.commit(); db.close()
AC = tok('acc')
ck('access holder: gives ticks he has', c.post('/permissions/roles', headers=AC, json={'name': 'Helper', 'tabs': ['store.store.home']}).status_code == 200)
r = c.post('/permissions/roles', headers=AC, json={'name': 'Helper2', 'tabs': ['store.store.home', 'store.store.items']})
ck('access holder: not a tick he lacks (same broad right)', r.status_code == 403 and 'Material list' in r.text, r.text[:200])
ck('access holder: cannot change the Store keeper role (holds more)',
   c.post('/permissions/roles', headers=AC, json={'id': role['id'], 'name': 'Store keeper', 'tabs': ['store.store.home']}).status_code == 403)
d = c.get('/permissions/roles', headers=AC).json()
ck('roles list carries the tree and each role\'s ticks', d['tree'] and all('tabs' in x for x in d['rows']))

# ---- Old-style save still works (no ticks sent) --------------------------------
r = c.post('/permissions/roles', headers=A, json={'name': 'Old style', 'screens': ['store', 'requests']})
ck('old-style role: tabs follow the rights', r.status_code == 200 and r.json()['tabs'] == tabrights.from_rights(['store', 'requests', 'settings']), r.text[:200])

print('\nALL PASS' if not FAIL else f'\n{len(FAIL)} FAILED: {FAIL}')

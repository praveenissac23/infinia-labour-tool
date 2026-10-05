"""Settings tabs as rights on Settings > Access - and nobody climbing above
what they were given through the Logins or Access tab.

Run: cd app && rm -f /tmp/sr2.db && DATABASE_URL=sqlite:////tmp/sr2.db python3 ../tests/settings_rights_test.py
"""
import sys
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main

db = database.SessionLocal()
U = lambda n, perms, role='office': models.User(username=n, hashed_password=auth.hash_password('p'), full_name=n, role=role, permissions=perms)
db.add(U('admin', '', 'admin'))
db.add(U('plain', 'dashboard,settings'))
db.add(U('hrlog', 'dashboard,settings,settings_logins,people_labour'))                 # Logins tab
db.add(U('acc', 'dashboard,settings,settings_access,store'))                            # Access tab
db.add(U('co', 'settings,settings_company,settings_companies,settings_data,activity'))  # the rest
db.add(U('chief', 'dashboard,settings,hrpayroll,pdc'))                                  # more than hrlog has
db.add(U('keeper', 'dashboard,settings,people_labour'))                                 # within hrlog's
db.add(models.AccessRole(name='Labour clerk', screens='settings,people_labour'))
db.add(models.AccessRole(name='Accountant', screens='settings,hrpayroll,pdc'))
db.commit()
ids = {u.username: u.id for u in db.query(models.User).all()}
roles = {r.name: r.id for r in db.query(models.AccessRole).all()}
db.close()

c = TestClient(main.app)
tok = lambda u: {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': u, 'password': 'p'}).json()['access_token']}
A, PL, HL, AC, CO = tok('admin'), tok('plain'), tok('hrlog'), tok('acc'), tok('co')
FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{x}]'))
    if not ok: FAIL.append(l)

# ---- The rights exist and are laid out under Settings -------------------------
d = c.get('/permissions/roles', headers=A).json()
pg = dict((p, k) for p, k in d['pages'])
ck('Settings lists its tabs', pg.get('Settings') == ['settings_company', 'settings_data', 'settings_companies', 'settings_logins', 'settings_access', 'activity'], pg.get('Settings'))
ck('each has a label', all(d['labels'].get(k) for k in pg['Settings']))

# ---- Without the rights: refused ------------------------------------------------
ck('plain: logins refused', c.get('/users', headers=PL).status_code == 403)
ck('plain: roles refused', c.get('/permissions/roles', headers=PL).status_code == 403)
ck('plain: company settings refused', c.post('/settings/company', headers=PL, json={'store_incharge': 'x'}).status_code == 403)
ck('plain: activity monitor refused', c.get('/users/audit-log', headers=PL).status_code == 403)
ck('plain: clear store refused', c.post('/backup/store-reset', headers=PL, json={'confirm': 'CLEAR STORE'}).status_code == 403)
ck('plain: companies refused', c.post('/employees/companies', headers=PL, json={'name': 'X'}).status_code == 403)
ck('plain: own password still allowed', c.post('/auth/change-password', headers=PL, json={'current_password': 'p', 'new_password': 'pppppp'}).status_code == 200)

# ---- General, Companies, data, Activity --------------------------------------
ck('co: company settings', c.post('/settings/company', headers=CO, json={'store_incharge': 'Amal'}).status_code == 200)
ck('co: activity monitor', c.get('/users/audit-log', headers=CO).status_code == 200)
r = c.post('/employees/companies', headers=CO, json={'name': 'Test Co LLC', 'short_name': 'TC'})
ck('co: companies & sites', r.status_code == 200, r.text)
ck('co: no logins tab', c.get('/users', headers=CO).status_code == 403)

# ---- Logins tab, within its own rights ------------------------------------------
ck('hrlog: sees the logins', c.get('/permissions/roles/users', headers=HL).status_code == 200)
ck('hrlog: reads the roles to pick from', c.get('/permissions/roles', headers=HL).status_code == 200)
r = c.post('/permissions/roles/new-user', headers=HL, json={'username': 'newclerk', 'full_name': 'New', 'password': 'pppppp', 'role_id': roles['Labour clerk']})
ck('hrlog: new login on a role within his rights', r.status_code == 200, r.text)
r = c.post('/permissions/roles/new-user', headers=HL, json={'username': 'newacct', 'full_name': 'New', 'password': 'pppppp', 'role_id': roles['Accountant']})
ck('hrlog: not on a role with rights he lacks', r.status_code == 403, r.status_code)
ck('hrlog: cannot create an admin', c.post('/users', headers=HL, json={'username': 'x2', 'password': 'pppppp', 'role': 'admin'}).status_code == 403)
ck('hrlog: cannot make an admin', c.post('/permissions/roles/assign', headers=HL, json={'user_id': ids['keeper'], 'role_id': 'admin'}).status_code == 403)
ck("hrlog: cannot reset an admin's password", c.post(f"/users/{ids['admin']}/reset-password", headers=HL, json={'new_password': 'pppppp'}).status_code == 403)
ck('hrlog: cannot reset a login holding more', c.post(f"/users/{ids['chief']}/reset-password", headers=HL, json={'new_password': 'pppppp'}).status_code == 403)
ck('hrlog: resets a login within his rights', c.post(f"/users/{ids['keeper']}/reset-password", headers=HL, json={'new_password': 'pppppp'}).status_code == 200)
ck('hrlog: cannot delete a login holding more', c.delete(f"/users/{ids['chief']}", headers=HL).status_code == 403)
ck('hrlog: cannot re-role a login holding more', c.post('/permissions/roles/assign', headers=HL, json={'user_id': ids['chief'], 'role_id': roles['Labour clerk']}).status_code == 403)
ck('hrlog: cannot edit roles (Access tab)', c.post('/permissions/roles', headers=HL, json={'id': roles['Labour clerk'], 'name': 'Labour clerk', 'screens': ['people_labour']}).status_code == 403)
ck('hrlog: direct rights beyond his own refused', c.post(f"/users/{ids['keeper']}/permissions", headers=HL, json={'permissions': 'settings,people_labour,hrpayroll'}).status_code == 403)

# ---- Access tab, within its own rights ------------------------------------------
r = c.post('/permissions/roles', headers=AC, json={'name': 'Store helper', 'screens': ['store']})
ck('acc: new role with rights he holds', r.status_code == 200, r.text)
ck('acc: not with rights he lacks', c.post('/permissions/roles', headers=AC, json={'name': 'Bad', 'screens': ['hrpayroll']}).status_code == 403)
ck('acc: cannot take a right he lacks off a role', c.post('/permissions/roles', headers=AC, json={'id': roles['Accountant'], 'name': 'Accountant', 'screens': ['pdc']}).status_code == 403)
ck('acc: cannot delete a role holding more', c.delete(f"/permissions/roles/{roles['Accountant']}", headers=AC).status_code == 403)
ck('acc: cannot hand out the Access tab to a role unless he has it', c.post('/permissions/roles', headers=AC, json={'name': 'Store helper2', 'screens': ['store', 'settings_logins']}).status_code == 403)
ck('acc: no logins tab', c.get('/permissions/roles/users', headers=AC).status_code == 403)

# ---- Admin unchanged -------------------------------------------------------------
ck('admin: everything', all(c.get(u, headers=A).status_code == 200 for u in ('/users', '/permissions/roles', '/permissions/roles/users', '/users/audit-log')))
ck('admin: gives any right', c.post('/permissions/roles', headers=A, json={'name': 'Settings clerk', 'screens': ['settings_company', 'settings_logins']}).status_code == 200)

print('\nALL PASS' if not FAIL else f'\n{len(FAIL)} FAILED: {FAIL}')

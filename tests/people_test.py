"""The People register and the Access page, checked end to end.

Run: cd app && DATABASE_URL=sqlite:////tmp/people.db python3 ../tests/people_test.py

The promise these pages make is that they add nothing that will have to
be merged later: a person is the same row whether Master Data, the
Staff Register or People touched him last. So most of what is checked
here is that promise - a labourer added on the old screen is on the new
one, a passport typed on the new one is on the old tracker, a leaving
date set on either side lands on the same record.
"""
import sys
from datetime import date, timedelta

sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth

models.Base.metadata.create_all(database.engine)
import main

FAIL = []


def ck(label, ok, ctx=None):
    print(("PASS " if ok else "FAIL ") + label + ("" if ok else f"   [{ctx}]"))
    if not ok:
        FAIL.append(label)


db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Praveen', role='admin'))
db.add(models.User(username='office', hashed_password=auth.hash_password('p'), full_name='Office', role='office'))
db.add(models.User(username='site', hashed_password=auth.hash_password('p'), full_name='Site', role='site'))
db.commit(); db.close()

c = TestClient(main.app)


def tok(u):
    return {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': u, 'password': 'p'}).json()['access_token']}


H, O, S = tok('admin'), tok('office'), tok('site')
today = main._dubai_today()

# ---- Only admin, until handed out ----------------------------------------
ck('the office login cannot open People', c.get('/employees/people', headers=O).status_code == 403)
ck('nor the site login', c.get('/employees/people', headers=S).status_code == 403)
ck('nor the Access page', c.get('/permissions/roles', headers=O).status_code == 403)
ck('admin can', c.get('/employees/people', headers=H).status_code == 200)
ck('the new rights are known to the app', all(s in c.get('/permissions/screens', headers=H).json()['screens']
                                                for s in ('people_labour', 'people_office', 'people_local', 'people_household', 'access')))

# ---- A company and a labourer from the OLD screens ------------------------
co = c.post('/employees/companies', json={'name': 'INFINIA CONTRACTING L.L.C.', 'short_name': 'Infinia', 'code_prefix': 'IC'}, headers=H).json()
r = c.post('/employees', json={'emp_no': '101', 'name': 'MOHAMED SALIM', 'trade': 'Mason', 'company': 'Infinia',
                               'pay_type': 'daily', 'total_salary': 1500, 'basic_salary': 1200}, headers=H)
ck('a labourer added on Master Data', r.status_code == 200, r.text[:120])
rows = c.get('/employees/people?group=labour', headers=H).json()['rows']
ck('is on the Labour tab of People at once', any(x['emp_no'] == '101' for x in rows), [x['emp_no'] for x in rows])
lab = next(x for x in rows if x['emp_no'] == '101')
ck('with his salary as Master Data holds it', lab['gross'] == 1500 and lab['basic'] == 1200, lab)

# ---- Office staff from the OLD staff register -------------------------------
r = c.post('/employees/staff', json={'emp_no': 'IC022', 'name': 'MOHAMED SHAFEEQ', 'company_id': co['id'],
                                     'designation': 'Site Engineer', 'joined_on': '2025-09-01',
                                     'basic': 2800, 'allowance': 4200, 'pay_route': 'wps'}, headers=H)
ck('an office staff member added on the Staff Register', r.status_code == 200, r.text[:120])
c.post('/employees/staff', json={'emp_no': 'IC015', 'name': 'KHADIJA FARIS', 'company_id': co['id'], 'designation': 'Admin',
                                 'joined_on': '2024-03-01', 'basic': 3000, 'allowance': 3000, 'pay_group': 'local',
                                 'scheme': 'pension', 'pension': 700}, headers=H)
c.post('/employees/staff', json={'emp_no': 'IC008', 'name': 'RAJI MOL', 'company_id': co['id'], 'designation': 'Maid',
                                 'joined_on': '2023-01-15', 'basic': 600, 'allowance': 900}, headers=H)
counts = c.get('/employees/people', headers=H).json()['counts']
ck('each lands on the right tab without anyone sorting them', counts == {'labour': 1, 'office': 1, 'local': 1, 'household': 1, 'left': 0}, counts)

# ---- The HR file: written on People, read back everywhere -------------------
f = c.get('/employees/people/IC022', headers=H).json()
ck('the file opens with the salary the register holds', f['person']['gross'] == 7000 and f['person']['group'] == 'office', f['person'])
ck('and nothing invented in the HR fields', f['profile']['nationality'] == '' and f['profile']['mobile'] == '')
r = c.put('/employees/people/IC022', json={'profile': {'nationality': 'Indian', 'date_of_birth': '1994-06-14', 'mobile': '+971 55 000 4471',
                                                       'emergency_name': 'Fathima', 'emergency_relation': 'wife', 'emergency_phone': '+91 98 000 2210',
                                                       'contract_no': 'MB-2025-114872', 'contract_expiry': '2027-08-31', 'bank_name': 'Mashreq',
                                                       'accommodation': 'Al Qusais 2, flat 304'},
                                           'employee': {'iban': 'AE070331000000004412', 'designation': 'Senior Site Engineer'}}, headers=H)
ck('the file saves', r.status_code == 200, r.text[:200])
f = r.json()
ck('and reads back', f['profile']['nationality'] == 'Indian' and f['profile']['contract_expiry'] == '2027-08-31' and f['profile']['accommodation'].startswith('Al Qusais'))
old = next(s for s in c.get('/employees/staff', headers=H).json()['rows'] if s['emp_no'] == 'IC022')
ck('the designation and IBAN typed on People are what the OLD Staff Register shows',
   old['designation'] == 'Senior Site Engineer' and old['iban'] == 'AE070331000000004412', old)
ck('salary is not touched by a file save', old['gross'] == 7000, old['gross'])

# Documents: one table, both pages.
r = c.post('/employees/documents', json={'emp_no': 'IC022', 'kind': 'passport', 'number': 'P4471183', 'expires_on': '2031-03-12'}, headers=H)
ck('a passport recorded on the OLD document tracker', r.status_code == 200, r.text[:120])
c.post('/employees/documents', json={'emp_no': 'IC022', 'kind': 'medical', 'number': 'DHA-1', 'expires_on': (today + timedelta(days=20)).isoformat()}, headers=H)
c.post('/employees/documents', json={'emp_no': '101', 'kind': 'visa', 'number': 'V-1', 'expires_on': (today - timedelta(days=8)).isoformat()}, headers=H)
f = c.get('/employees/people/IC022', headers=H).json()
ck('is on his People file, with the new medical-fitness kind beside it',
   {d['kind'] for d in f['documents']} == {'passport', 'medical'}, f['documents'])
due = c.get('/employees/people/documents-due?days=90', headers=H).json()['rows']
ck('Documents due lists the expired visa first, then the medical', [d['kind'] for d in due] == ['visa', 'medical'], due)
ck('and says which register each is on', due[0]['group'] == 'labour' and due[1]['group'] == 'office')
ck('narrowed to office it drops the labourer', [d['emp_no'] for d in c.get('/employees/people/documents-due?days=90&group=office', headers=H).json()['rows']] == ['IC022'])

# ---- Leave: labour 60 days after two years; staff 30 a year ------------------
c.put('/employees/people/101', json={'employee': {'joined_on': '2022-03-12'}}, headers=H)
f = c.get('/employees/people/101', headers=H).json()
lv = f['leave']
months = main.people._months_between(date(2022, 3, 12), today)
ck('a labourer accrues 60 days per 24 months from his joining date', lv['rule_days'] == 60 and lv['rule_months'] == 24
   and abs(lv['accrued'] - round(60 * months / 24, 1)) < 0.11, lv)
ck('with nothing taken his first block fell due two years after joining', lv['next_due'] == '2024-03-12' and lv['due_state'] == 'due', lv)
# Ten days marked Leave on the attendance grid count as taken.
md = date(2024, 4, 1)
for i in range(10):
    d = md + timedelta(days=i)
    r = c.post('/attendance/save', json={'rows': [{'emp_no': '101', 'full_date': d.isoformat(), 'am': 'Leave', 'pm': 'Leave'}]}, headers=H)
    if r.status_code != 200 and i == 0:
        print('   attendance save refused:', r.text[:200])
lv = c.get('/employees/people/101', headers=H).json()['leave']
ck('days marked Leave on the attendance grid come off the balance', lv['taken'] == 10 and lv['last_vacation'].startswith('01 Apr 2024'), lv)
f = c.get('/employees/people/IC022', headers=H).json()
lv = f['leave']
ck('office staff accrue 30 days a year', lv['rule_days'] == 30 and lv['rule_months'] == 12, lv)
ck('and the first year fell due on the anniversary', lv['next_due'] == '2026-09-01', lv)
r = c.post('/employees/leave', json={'emp_no': 'IC022', 'kind': 'vacation', 'from': (today.replace(day=1) - timedelta(days=1)).replace(day=1).isoformat(),
                                     'to': ((today.replace(day=1) - timedelta(days=1)).replace(day=1) + timedelta(days=4)).isoformat()}, headers=H)
ck('a vacation recorded on the OLD Absence register', r.status_code == 200, r.text[:150])
lv = c.get('/employees/people/IC022', headers=H).json()['leave']
ck('is taken off his leave balance on People', lv['taken'] == 5 and len(lv['vacations']) == 1, lv)
# A contract that says otherwise.
c.put('/employees/people/IC022', json={'profile': {'leave_days': 22, 'leave_months': 12, 'leave_opening': 3, 'leave_opening_on': '2026-01-01'}}, headers=H)
lv = c.get('/employees/people/IC022', headers=H).json()['leave']
ck('a contract rule and an opening balance override the group rule', lv['rule_days'] == 22 and lv['opening'] == 3 and lv['counted_from'] == '2026-01-01', lv)
bal = c.get('/employees/people/leave-balances?group=labour', headers=H).json()['rows']
ck('the leave-balance list for labour', len(bal) == 1 and bal[0]['emp_no'] == '101' and bal[0]['taken'] == 10, bal)

# ---- Household and the register tab -------------------------------------------
r = c.put('/employees/people/IC008', json={'group': 'office'}, headers=H)
ck('a maid can be moved to the office tab', r.status_code == 200 and r.json()['person']['group'] == 'office', r.text[:150])
r = c.put('/employees/people/IC008', json={'group': 'household'}, headers=H)
ck('and back', r.json()['person']['group'] == 'household')
r = c.put('/employees/people/IC008', json={'group': 'labour'}, headers=H)
ck('but never onto the labour register from here', r.status_code == 400, r.text[:150])
r = c.put('/employees/people/IC015', json={'group': 'office'}, headers=H)
old = next(s for s in c.get('/employees/staff', headers=H).json()['rows'] if s['emp_no'] == 'IC015')
ck('moving a local to the office tab moves her to the office statement in the OLD app too', old['pay_group'] == 'staff', old)
c.put('/employees/people/IC015', json={'group': 'local'}, headers=H)

# ---- New people from the NEW page, seen by the OLD screens ----------------------
r = c.post('/employees/people', json={'group': 'labour', 'emp_no': '102', 'name': 'Barsati', 'designation': 'Helper',
                                      'company_id': co['id'], 'joined_on': '2024-01-20', 'gross': 1250, 'basic': 1000}, headers=H)
ck('a labourer added on People', r.status_code == 200, r.text[:150])
md_rows = c.get('/employees', headers=H).json()
ck('is on Master Data, in capitals, daily paid, with the salary', any(e['emp_no'] == '102' and e['name'] == 'BARSATI' and e['pay_type'] == 'daily'
   and e['total_salary'] == 1250 for e in md_rows), [e for e in md_rows if e['emp_no'] == '102'])
r = c.post('/employees/people', json={'group': 'office', 'emp_no': 'IC030', 'name': 'New Architect', 'designation': 'Architect',
                                      'company_id': co['id'], 'joined_on': today.isoformat(), 'basic': 3200, 'allowance': 4800, 'pay_route': 'wps'}, headers=H)
ck('an office joiner added on People', r.status_code == 200, r.text[:150])
ck('is on the OLD Staff Register with a salary history started', any(s['emp_no'] == 'IC030' and s['gross'] == 8000
   for s in c.get('/employees/staff', headers=H).json()['rows']))
r = c.post('/employees/people', json={'group': 'labour', 'emp_no': '102', 'name': 'X', 'joined_on': '2024-01-01'}, headers=H)
ck('a code already in use is refused', r.status_code == 400)
r = c.post('/employees/people', json={'group': 'office', 'emp_no': 'IC031', 'name': 'X', 'company_id': co['id']}, headers=H)
ck('and a joiner without a joining date', r.status_code == 400 and 'joining' in r.text.lower(), r.text[:120])

# ---- Leaving, from either side ------------------------------------------------------
left = (today - timedelta(days=3)).isoformat()
r = c.put('/employees/people/102', json={'employee': {'terminated_on': left}, 'profile': {'leaving_reason': 'Resigned'}}, headers=H)
ck('a leaving date set on People', r.status_code == 200 and r.json()['person']['active'] is False, r.text[:150])
ck('moves him to Left on People', any(x['emp_no'] == '102' for x in c.get('/employees/people?group=left', headers=H).json()['rows']))
ck('and Master Data shows the same leaving date', any(e['emp_no'] == '102' and e['terminated_on'] == left and e['active'] is False
   for e in c.get('/employees', headers=H).json()))

r = c.delete('/employees/people/IC030', headers=H)
ck('a joiner added by mistake can be removed while nothing hangs off him', r.status_code == 200, r.text[:120])
ck('and is gone from the OLD register too', not any(s['emp_no'] == 'IC030' for s in c.get('/employees/staff', headers=H).json()['rows']))
r = c.delete('/employees/people/101', headers=H)
ck('but not a man with attendance on file', r.status_code == 400 and 'attendance' in r.text, r.text[:120])

# ---- Assets ----------------------------------------------------------------------------
a = c.post('/employees/people/IC022/assets', json={'item': 'Laptop Dell 5540', 'tag': 'INF-LT-031', 'issued_on': '2025-09-02'}, headers=H).json()
ck('an asset is issued', a['item'].startswith('Laptop') and a['issued_on'] == '2025-09-02', a)
a2 = c.put(f"/employees/people/assets/{a['id']}", json={'returned_on': today.isoformat(), 'condition': 'Good'}, headers=H).json()
ck('and returned', a2['returned_on'] == today.isoformat())
ck('it is on the file', len(c.get('/employees/people/IC022', headers=H).json()['assets']) == 1)
ck('and removable', c.delete(f"/employees/people/assets/{a['id']}", headers=H).status_code == 200)
ck('the history on a file is the app log for that code', any('IC022' in h['what'] for h in c.get('/employees/people/IC022', headers=H).json()['history']))

# ---- Reports -----------------------------------------------------------------------------
t = c.post('/auth/download-token', headers=H).json()['token']
for kind, extra in (('register', '&group=labour'), ('register', '&group=office'), ('file', '&emp_no=IC022'),
                    ('documents-due', '&days=90'), ('leave', '&group=labour')):
    for fmt in ('pdf', 'excel'):
        r = c.get(f'/export/people/{kind}?token={t}&format={fmt}{extra}')
        ck(f'{kind} {extra} as {fmt}', r.status_code == 200 and len(r.content) > 1000, (r.status_code, r.text[:100]))
    r = c.get(f'/export/people/{kind}/view?token={t}{extra}')
    ck(f'{kind} {extra} preview', r.status_code == 200 and 'Infinia' in r.text, r.status_code)
t2 = c.post('/auth/download-token', headers=O).json()['token']
ck('a login without the right cannot open the reports either', c.get(f'/export/people/register?token={t2}&group=labour').status_code == 403)

# ---- One right per register: office salaries stay with those given them ----
uid_o = next(u['id'] for u in c.get('/users', headers=H).json() if u['username'] == 'office')
c.post(f'/users/{uid_o}/permissions', json={'permissions': 'dashboard,people_labour,settings'}, headers=H)
LO = tok('office')
d = c.get('/employees/people', headers=LO).json()
ck('a labour-only login opens People and sees labour alone', d['allowed'] == ['labour'] and all(r['group'] == 'labour' for r in d['rows']) and len(d['rows']) >= 1, d.get('allowed'))
ck('office staff are not even counted for it', d['counts']['office'] == 0, d['counts'])
ck('an office file is refused outright', c.get('/employees/people/IC022', headers=LO).status_code == 403)
ck('so is adding to the office register', c.post('/employees/people', json={'group': 'office', 'emp_no': 'IC099', 'name': 'X', 'company_id': co['id'], 'joined_on': '2026-01-01', 'basic': 1, 'allowance': 1}, headers=LO).status_code == 403)
ck('documents due shows labour rows only', all(r['group'] == 'labour' for r in c.get('/employees/people/documents-due?days=3650', headers=LO).json()['rows']))
ck('leave balances for office are refused', c.get('/employees/people/leave-balances?group=office', headers=LO).json()['rows'] == [])
t3 = c.post('/auth/download-token', headers=LO).json()['token']
ck('the office register report is refused', c.get(f'/export/people/register?token={t3}&group=office').status_code == 403)
ck('an office person\'s file report is refused', c.get(f'/export/people/file?token={t3}&emp_no=IC022').status_code == 403)
ck('the labour register report is allowed', c.get(f'/export/people/register?token={t3}&group=labour').status_code == 200)
c.post(f'/users/{uid_o}/permissions', json={'permissions': ''}, headers=H)

# ---- Access: named roles -----------------------------------------------------------------------
r = c.post('/permissions/roles', json={'name': 'Assistant Accountant', 'screens': ['dashboard', 'attendance', 'masterdata', 'reports', 'combine', 'errorcheck']}, headers=H)
ck('a role is made', r.status_code == 200 and 'settings' in r.json()['screens'], r.text[:150])
role = r.json()
uid = next(u['id'] for u in c.get('/users', headers=H).json() if u['username'] == 'office')
r = c.post('/permissions/roles/assign', json={'user_id': uid, 'role_id': role['id']}, headers=H)
ck('a login is given the role', r.status_code == 200 and 'masterdata' in r.json()['screens'], r.text[:150])
me = c.get('/permissions/me', headers=tok('office')).json()['screens']
ck('and the OLD app sees exactly those rights - nothing new to read', 'masterdata' in me and 'store' not in me, me)
ck('while People and Access stay closed to it', c.get('/employees/people', headers=tok('office')).status_code == 403)
ck('the roles page lists rights by page and tab', any(pg == 'People' for pg, _ in c.get('/permissions/roles', headers=H).json()['pages']))
r = c.post('/permissions/roles', json={'id': role['id'], 'name': 'Assistant Accountant', 'screens': ['dashboard', 'attendance', 'reports']}, headers=H)
me = c.get('/permissions/me', headers=tok('office')).json()['screens']
ck('changing the role changes every login that carries it', 'masterdata' not in me and 'attendance' in me, me)
r = c.post('/permissions/roles/new-user', json={'username': 'storeman', 'password': 'store123', 'full_name': 'Store Keeper', 'role_id': role['id']}, headers=H)
ck('a new login can be made from a role', r.status_code == 200, r.text[:150])
ck('and signs in with those rights', 'attendance' in c.get('/permissions/me', headers={'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': 'storeman', 'password': 'store123'}).json()['access_token']}).json()['screens'])
ck('the same role with a different name is refused twice', c.post('/permissions/roles', json={'name': 'Assistant Accountant', 'screens': []}, headers=H).status_code == 400)
ck('an unknown screen is refused', c.post('/permissions/roles', json={'name': 'X', 'screens': ['nope']}, headers=H).status_code == 400)
ck('admin cannot be given a role', c.post('/permissions/roles/assign', json={'user_id': 1, 'role_id': role['id']}, headers=H).status_code == 400)
ck('roles list their members', any(m['username'] == 'office' for m in c.get('/permissions/roles', headers=H).json()['rows'][0]['members']))
ck('deleting the role leaves its logins with the rights they had', c.delete(f"/permissions/roles/{role['id']}", headers=H).status_code == 200
   and 'attendance' in c.get('/permissions/me', headers=tok('office')).json()['screens'])
ck('the users list shows who follows which role', any(u['username'] == 'storeman' and u['access_role'] == '' for u in c.get('/permissions/roles/users', headers=H).json()['rows']))

# ---- Nothing else moved ------------------------------------------------------------------------------
ck('the office document tracker still lists everything, new kinds included',
   {d['kind'] for d in c.get('/employees/documents', headers=H).json()['rows']} >= {'passport', 'medical', 'visa'})

print()
if FAIL:
    print(f"{len(FAIL)} FAILED"); sys.exit(1)
print("ONE RECORD, TWO PAGES, NOTHING TO MERGE")

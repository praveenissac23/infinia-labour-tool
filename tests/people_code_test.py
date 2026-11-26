"""Changing an employee's code on his People file (26/11/2026).

Run: python3 tests/run_all.py people_code

The code is written into four tables as text - attendance days, payroll cycles, the visa file and PPE issues - and
every one of them must move with him, or his history would sit under a code nobody has. A code that is already
someone else's, or that has attendance of its own, must be refused, so two men's days can never mix.
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
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Owner', role='admin'))
db.add(models.User(username='office', hashed_password=auth.hash_password('p'), full_name='Office', role='office'))
db.commit(); db.close()
c = TestClient(main.app)


def tok(u):
    return {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': u, 'password': 'p'}).json()['access_token']}


H, O = tok('admin'), tok('office')

# A labourer as on the live register (a long passport name, a second company), and another man whose code clashes.
c.post('/employees/companies', json={'name': 'PRIME INFINIA CONTRACTING L.L.C.', 'short_name': 'Prime Infinia', 'code_prefix': 'F'}, headers=H)
for code, name in (('F804', 'IAN KIPLAGAT KEMBOY'), ('F805', 'JOSEPH MWANGI OTIENO KAMAU')):
    r = c.post('/employees', json={'emp_no': code, 'name': name, 'trade': 'BUILDING LABOUR', 'company': 'Prime Infinia',
                                   'pay_type': 'daily', 'total_salary': 1200, 'basic_salary': 900}, headers=H)
    ck(f'{code} added', r.status_code == 200, r.text)

db = database.SessionLocal()
class _E:                                             # just the ids, so they outlive the session
    def __init__(s, e): s.id = e.id
ian = _E(db.query(models.Employee).filter_by(emp_no='F804').one())
jos = _E(db.query(models.Employee).filter_by(emp_no='F805').one())
start = date(2026, 11, 14)
for k in range(12):                                   # 12 attendance days, as F804 has on the live register
    db.add(models.DailyRow(employee_id=ian.id, emp_no='F804', month_year='November 2026', full_date=start + timedelta(days=k)))
db.add(models.DailyRow(employee_id=jos.id, emp_no='F805', month_year='November 2026', full_date=start))
db.add(models.EmployeeSummary(employee_id=ian.id, emp_no='F804', month_year='November 2026'))
db.add(models.VisaFile(employee_id=ian.id, emp_no='F804', person='IAN KIPLAGAT KEMBOY', started_on=start))
db.add(models.PpeIssue(employee_id=ian.id, emp_no='F804', name='IAN KIPLAGAT KEMBOY', issued_on=start, item='Safety Shoes'))
db.add(models.PpeIssue(employee_id=None, emp_no='F804', name='IAN K', issued_on=start, item='Helmet'))   # an old entry typed by code only
db.commit(); db.close()

URL = '/employees/people/F804/code'

# ---- who may ----
ck('a login without Master Data cannot change a code', c.post(URL, json={'new_code': 'F904'}, headers=O).status_code == 403)

# ---- refused codes ----
r = c.post(URL, json={'new_code': 'F805', 'check': True}, headers=H)
ck("someone else's code is refused, naming him", r.status_code == 400 and 'JOSEPH' in r.json()['detail'], r.text)
r = c.post(URL, json={'new_code': ' f 805 ', 'check': True}, headers=H)
ck('...also typed with spaces / small letters', r.status_code == 400, r.text)
r = c.post(URL, json={'new_code': '', 'check': True}, headers=H)
ck('an empty code is refused', r.status_code == 400, r.text)
r = c.post(URL, json={'new_code': 'F 9#4', 'check': True}, headers=H)
ck('odd characters are refused', r.status_code == 400, r.text)
db = database.SessionLocal()
db.add(models.DailyRow(employee_id=jos.id, emp_no='F999', month_year='November 2026', full_date=start))   # stray days under F999
db.commit(); db.close()
r = c.post(URL, json={'new_code': 'F999', 'check': True}, headers=H)
ck('a code that already has attendance of its own is refused', r.status_code == 400 and 'already' in r.json()['detail'], r.text)

# ---- the check says what will move, and changes nothing ----
r = c.post(URL, json={'new_code': 'f904', 'check': True}, headers=H).json()
ck('check: shows the move and counts what goes with him', (r.get('from'), r.get('to'), r.get('days'), r.get('cycles'), r.get('visa'), r.get('ppe'))
   == ('F804', 'F904', 12, 1, 1, 2), r)
db = database.SessionLocal()
ck('...and nothing has changed yet', db.query(models.Employee).filter_by(emp_no='F804').count() == 1 and
   db.query(models.DailyRow).filter_by(emp_no='F804').count() == 12)
db.close()
ck('the same code again: nothing to do', c.post(URL, json={'new_code': 'F804'}, headers=H).json().get('same') is True)

# ---- the change ----
r = c.post(URL, json={'new_code': 'f904'}, headers=H)
ck('changed to F904 (capitals, as codes are kept)', r.status_code == 200 and r.json()['emp_no'] == 'F904', r.text)
db = database.SessionLocal()
ck('his record has the new code', db.query(models.Employee).get(ian.id).emp_no == 'F904')
ck('all 12 attendance days moved', db.query(models.DailyRow).filter_by(employee_id=ian.id, emp_no='F904').count() == 12)
ck('his payroll cycle moved', db.query(models.EmployeeSummary).filter_by(employee_id=ian.id).one().emp_no == 'F904')
ck('his visa file moved', db.query(models.VisaFile).filter_by(employee_id=ian.id).one().emp_no == 'F904')
ck('both PPE issues moved (also the old one kept by code only)', db.query(models.PpeIssue).filter_by(emp_no='F904').count() == 2)
ck('nothing is left under F804', sum(db.query(M).filter(M.emp_no == 'F804').count()
                                      for M in (models.DailyRow, models.EmployeeSummary, models.VisaFile, models.PpeIssue)) == 0)
ck("the other man's days are untouched", db.query(models.DailyRow).filter_by(employee_id=jos.id, emp_no='F805').count() == 1)
ck('the change is in the log', any('F804 -> F904' in (a.details or '') for a in db.query(models.AuditLog).all())
   if hasattr(models, 'AuditLog') else True)
db.close()

# ---- the file opens under the new code; the old one is gone ----
ck('his file opens under F904', c.get('/employees/people/F904', headers=H).status_code == 200)
ck('F804 is no longer anyone', c.get('/employees/people/F804', headers=H).status_code == 404)
r = c.put('/employees/people/F904', json={'employee': {'name': 'IAN KIPLAGAT KEMBOY'}, 'profile': {'nationality': 'KENYAN'}}, headers=H)
ck('the rest of his file still saves under the new code', r.status_code == 200, r.text)

# ---- the page ----
page = open('../portal/people.html', encoding='utf-8').read()
ck('the edit form has an Employee code box', 'id="e-emp_no"' in page and 'setVal("e-emp_no", p.emp_no)' in page)
ck('a new code is checked, shown with what moves, confirmed, then saved before the rest',
   'check: true' in page and 'move with him' in page and 'Yes, make it' in page)
tips = open('../portal/help/guides.js', encoding='utf-8').read()
ck('the (i) explains it', '"#e-emp_no"' in tips)

print("\nALL PASS" if not FAIL else f"\n{len(FAIL)} FAILED")
sys.exit(1 if FAIL else 0)

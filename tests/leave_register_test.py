"""Staff > Leave: spells of leave, their standing, who may see them, the report.

Run: cd app && rm -f /tmp/lr.db && DATABASE_URL=sqlite:////tmp/lr.db python3 ../tests/leave_register_test.py
"""
import sys
from datetime import timedelta
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main, people

db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Administrator', role='admin'))
db.add(models.User(username='hr', hashed_password=auth.hash_password('p'), full_name='HR', role='office',
                   permissions='people_labour'))
db.add(models.Employee(emp_no='F-754', name='HARI SHANKAR CHAUHAN', trade='MASON', total_salary=1300, basic_salary=800, active=True))
db.add(models.Employee(emp_no='F-716', name='AVINAS PASWAN', trade='STEEL FIXER', total_salary=1500, basic_salary=900, active=True))
db.add(models.Employee(emp_no='IC001', name='JOMON THOMAS', designation='P.R.O', staff=True, pay_group='staff',
                       total_salary=6500, basic_salary=2600, active=True))
db.commit(); db.close()

c = TestClient(main.app)
def tok(u):
    return {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': u, 'password': 'p'}).json()['access_token']}
H, HR = tok('admin'), tok('hr')
FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{x}]'))
    if not ok: FAIL.append(l)

today = main._dubai_today()
d = lambda n: (today + timedelta(days=n)).isoformat()

r = c.post('/employees/people/leave-register', headers=HR, json={
    'emp_no': 'F-754', 'leave_type': 'annual', 'leave_on': d(0), 'return_on': d(31), 'status': 'approved',
    'approved_by': 'HR Manager', 'home_phone': '+91 98765 43210', 'remark': ''})
ck('labour login adds leave for a labourer', r.status_code == 200, r.text)
ck('approved leave starting today reads On leave', r.json().get('standing') == 'On leave', r.json())
hari = r.json()['id']
f = c.get('/employees/people/F-754', headers=H).json()
ck('home-country number written to the staff file', f['profile']['home_phone'] == '+91 98765 43210', f['profile'].get('home_phone'))

r = c.post('/employees/people/leave-register', headers=HR, json={
    'emp_no': 'F-716', 'leave_on': d(-60), 'approved_days': 30, 'status': 'approved'})
ck('approved days passed with no return = Overdue', r.json().get('standing') == 'Overdue' and r.json()['days_late'] == 30, r.json())
avi = r.json()['id']
r = c.post('/employees/people/leave-register', headers=HR, json={'emp_no': 'F-716', 'leave_on': d(20), 'status': 'approved'})
ck('approved, not gone yet = Approved', r.json().get('standing') == 'Approved', r.json())
r = c.post('/employees/people/leave-register', headers=HR, json={'emp_no': 'F-716', 'leave_on': d(5), 'status': 'pending'})
ck('pending stays Pending', r.json().get('standing') == 'Pending', r.json())

ck('office staff closed to a labour-only login',
   c.post('/employees/people/leave-register', headers=HR, json={'emp_no': 'IC001', 'leave_on': d(1)}).status_code == 403)
ck('date of leave required', c.post('/employees/people/leave-register', headers=H, json={'emp_no': 'F-754'}).status_code == 400)
ck('return before leave refused', c.post('/employees/people/leave-register', headers=H,
   json={'emp_no': 'F-754', 'leave_on': d(5), 'return_on': d(1)}).status_code == 400)

r = c.put(f'/employees/people/leave-register/{avi}', headers=HR, json={'status': 'returned', 'return_on': d(-2)})
ck('marking returned', r.json().get('standing') == 'Returned', r.json())

lst = c.get('/employees/people/leave-register?group=labour', headers=HR).json()
st = [x['standing'] for x in lst['rows']]
ck('away first, then pending, approved, returned', st == ['On leave', 'Pending', 'Approved', 'Returned'], st)
ck('counts', lst['counts'] == {'away': 1, 'pending': 1, 'upcoming': 1, 'returned': 1}, lst['counts'])
ck('filter: on leave', [x['emp_no'] for x in c.get('/employees/people/leave-register?group=labour&show=away', headers=HR).json()['rows']] == ['F-754'])
ck('office register refused to labour-only login', c.get('/employees/people/leave-register?group=office', headers=HR).status_code == 403)

T = auth.create_download_token('admin') if hasattr(auth, 'create_download_token') else None
if T is None:
    T = c.get('/auth/download-token', headers=H).json().get('token')
for fmt in ('pdf', 'excel'):
    r = c.get(f'/export/people/leave-register?group=labour&token={T}&format={fmt}')
    ck(f'report {fmt}', r.status_code == 200 and len(r.content) > 1500, r.status_code)
r = c.get(f'/export/people/leave-register/view?group=labour&token={T}')
ck('report preview', r.status_code == 200 and 'Leave Details' in r.text and 'HARI SHANKAR CHAUHAN' in r.text, r.status_code)
rows, title, sub = people._leave_reg_parts(database.SessionLocal(), 'labour', '', None)
ck('empty columns left off the paper', 'Remark' not in rows[0] and 'Approved By' in rows[0], list(rows[0]))

# ---- Days taken in the leave balance, and the person's file --------------
db = database.SessionLocal()
e = db.query(models.Employee).filter_by(emp_no='F-716').first()
e.joined_on = today - timedelta(days=900)
from datetime import date as _date
db.add(models.DailyRow(employee_id=e.id, emp_no='F-716', month_year='x', full_date=today - timedelta(days=59), am='Leave', pm='Leave'))  # inside the returned spell
db.commit()
lv = people.leave_state(db, e, people._profile(db, e), 'labour')
# Returned spell: leave d(-60) .. return d(-2) -> 58 days, one already on attendance -> 57 from the register, 58 taken.
ck('returned annual leave counts as days taken, nothing twice', lv['taken'] == 58 and lv['from_register'] == 57, (lv['taken'], lv['from_register']))
db.close()
f = c.get('/employees/people/F-716', headers=HR).json()
ck('the file lists his leave', len(f['leave_spells']) == 3 and f['leave'].get('from_register') == 57, (len(f['leave_spells']), f['leave'].get('from_register')))
r = c.post('/employees/people/leave-register', headers=HR, json={'emp_no': 'F-716', 'leave_type': 'sick', 'leave_on': d(-10), 'return_on': d(-5), 'status': 'returned'})
f = c.get('/employees/people/F-716', headers=HR).json()
ck('sick leave does not touch the annual balance', f['leave']['taken'] == 58, f['leave']['taken'])

ck('delete', c.delete(f'/employees/people/leave-register/{hari}', headers=HR).json().get('ok'))

print('\nALL PASS' if not FAIL else f'\n{len(FAIL)} FAILED: {FAIL}')

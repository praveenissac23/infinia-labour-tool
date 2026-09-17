"""A card must carry the name the worker has now, not the one he had.

Run: cd app && DATABASE_URL=sqlite:////tmp/nm.db python3 ../tests/name_sync_test.py

A payroll summary wrote the worker's name once, when the row was first
created, and never again. Correcting a name in Master Data therefore
left the worker list showing the new name and his card, beside it,
showing the old one - on a pay screen that reads as another man's wages.
This checks the name follows the master record through the card, the
salary list, the printed card, and a plain restart.
"""
import sys
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main, services

CYCLE = 'September 2026'

db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'),
                   full_name='Administrator', role='admin'))
db.add(models.Employee(emp_no='F-763', name='GANESH KUMAR', trade='MASON',
                       total_salary=1350, basic_salary=900, active=True))
db.add(models.Employee(emp_no='F-764', name='GANESH KUMAR', trade='MASON',
                       total_salary=1350, basic_salary=900, active=True))
db.add(models.Site(code='914', active=True))
db.add(models.Engineer(name='AKHIL', active=True))
db.commit(); db.close()

c = TestClient(main.app)
H = {'Authorization': 'Bearer ' + c.post('/auth/login',
     data={'username': 'admin', 'password': 'p'}).json()['access_token']}

FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{x}]'))
    if not ok: FAIL.append(l)

rows = [{'emp_no': no, 'full_date': f'2026-09-{d:02d}', 'am': 'Present', 'pm': 'Present',
         'site': '914', 'engineer': 'AKHIL', 'ot': 2, 'bh': 0, 'comments': ''}
        for no in ('F-763', 'F-764') for d in range(1, 6)]
c.post('/attendance/save', json={'month_year': CYCLE, 'rows': rows}, headers=H)

def card_name(no):
    return (c.get(f'/live-card/{no}/{CYCLE}', headers=H).json().get('summary') or {}).get('emp_name')

ck('card shows the name it was created with', card_name('F-764') == 'GANESH KUMAR', card_name('F-764'))

# The correction an office makes in Master Data: F-764 was entered under
# the wrong name and is really Mohammed Zubair.
d = database.SessionLocal()
emp_id = d.query(models.Employee).filter_by(emp_no='F-764').first().id
d.close()
r = c.post('/employees', json={'emp_no': 'F-764', 'name': 'MOHAMMED ZUBAIR',
           'trade': 'CARPENTER', 'total_salary': 1350, 'basic_salary': 900,
           'active': True}, headers=H)
ck('master data accepts the correction', r.status_code == 200, r.text[:200])

listed = {e['emp_no']: e['name'] for e in c.get('/employees', headers=H).json()}
ck('worker list shows the corrected name', listed.get('F-764') == 'MOHAMMED ZUBAIR', listed.get('F-764'))
ck('the card now agrees with the list', card_name('F-764') == 'MOHAMMED ZUBAIR', card_name('F-764'))
ck('the other worker is left alone', card_name('F-763') == 'GANESH KUMAR', card_name('F-763'))

sal = {s['emp_no']: s['emp_name'] for s in c.get(f'/summaries/{CYCLE}', headers=H).json()}
ck('Salary Cards list shows the corrected name', sal.get('F-764') == 'MOHAMMED ZUBAIR', sal.get('F-764'))
ck('and the trade followed too',
   next(s['trade'] for s in c.get(f'/summaries/{CYCLE}', headers=H).json() if s['emp_no'] == 'F-764') == 'CARPENTER')

# The stored row itself must be right, because the printed card reads
# from it rather than from the master record.
d = database.SessionLocal()
stored = d.query(models.EmployeeSummary).filter_by(emp_no='F-764', month_year=CYCLE).first()
ck('the stored summary carries the corrected name', stored.emp_name == 'MOHAMMED ZUBAIR', stored.emp_name)
ck('the stored summary points at the right worker', stored.employee_id == emp_id, stored.employee_id)

# A summary left stale by an older version must heal on a restart, which
# is the only thing that will fix the cards already on the live server.
stored.emp_name = 'GANESH KUMAR'
stored.trade = 'MASON'
d.commit(); d.close()
ck('a stale row is still served correctly on the card',
   card_name('F-764') == 'MOHAMMED ZUBAIR', card_name('F-764'))

d = database.SessionLocal()
main._recalculate_all_summaries(d)
healed = d.query(models.EmployeeSummary).filter_by(emp_no='F-764', month_year=CYCLE).first()
ck('a restart repairs the stored name', healed.emp_name == 'MOHAMMED ZUBAIR', healed.emp_name)
ck('a restart repairs the stored trade', healed.trade == 'CARPENTER', healed.trade)

# And none of this may move a single dirham.
before = healed.final_salary
services.recalculate_summary(d, d.query(models.Employee).filter_by(emp_no='F-764').first(), CYCLE)
after = d.query(models.EmployeeSummary).filter_by(emp_no='F-764', month_year=CYCLE).first().final_salary
d.close()
ck('the pay figure is untouched by the name fix', before == after, f'{before} -> {after}')

# Error Check names the worker from the day's row, which carries its own
# copy of the name - so it had the same fault.
c.post('/attendance/save', json={'month_year': CYCLE, 'rows': [
    {'emp_no': 'F-764', 'full_date': '2026-09-06', 'am': 'Present', 'pm': 'Present',
     'site': '914', 'engineer': 'AKHIL', 'ot': 14, 'bh': 0, 'comments': ''}]}, headers=H)
checked = c.get(f'/error-check/{CYCLE}', headers=H).json()['rows']
flagged = [p for p in checked if p['emp_no'] == 'F-764']
ck('Error Check raises the high OT',
   any('OT' in p.get('kind', '') for p in flagged), [p.get('kind') for p in flagged])
ck('Error Check names him as he is called now',
   all(p['name'] == 'MOHAMMED ZUBAIR' for p in flagged),
   sorted({p['name'] for p in flagged}))

print('\n' + ('ALL PASS' if not FAIL else f'{len(FAIL)} FAILED: ' + '; '.join(FAIL)))
sys.exit(1 if FAIL else 0)

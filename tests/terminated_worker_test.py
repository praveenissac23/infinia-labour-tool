"""A man who leaves keeps his last card, then stops appearing - but
never leaves the master list.

Run: cd app && DATABASE_URL=sqlite:////tmp/tw.db python3 ../tests/terminated_worker_test.py

What the office needs: the cycle he left in still shows him, marked
Terminated from his last day, because those days have to be paid. From
the next cycle he is not on the attendance screen at all, because he is
not there to mark. And his name and card number stay in Master Data for
good, as the record of who he was.
"""
import sys
from datetime import date
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main

LEFT_IN = 'September 2026'      # cycle 26 Aug - 25 Sep
NEXT = 'October 2026'           # cycle 26 Sep - 25 Oct
LEFT_ON = '2026-09-10'

db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'),
                   full_name='Administrator', role='admin'))
db.add(models.User(username='site1', hashed_password=auth.hash_password('p'),
                   full_name='Site Engineer', role='site', permissions='attendance'))
db.add(models.Employee(emp_no='F-780', name='RAJU SINGH', trade='MASON',
                       total_salary=1500, basic_salary=1000, active=True))
db.add(models.Employee(emp_no='F-781', name='ANIL YADAV', trade='MASON',
                       total_salary=1500, basic_salary=1000, active=True))
db.add(models.Site(code='914', active=True))
db.add(models.Engineer(name='AKHIL', active=True))
db.commit(); db.close()

c = TestClient(main.app)
H = {'Authorization': 'Bearer ' + c.post('/auth/login',
     data={'username': 'admin', 'password': 'p'}).json()['access_token']}
SITE = {'Authorization': 'Bearer ' + c.post('/auth/login',
        data={'username': 'site1', 'password': 'p'}).json()['access_token']}

FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{x}]'))
    if not ok: FAIL.append(l)

# He works the first half of the cycle, and is marked Present past the
# day he actually left - which is what really happens.
rows = [{'emp_no': no, 'full_date': f'2026-09-{d:02d}', 'am': 'Present', 'pm': 'Present',
         'site': '914', 'engineer': 'AKHIL', 'ot': 0, 'bh': 0, 'comments': ''}
        for no in ('F-780', 'F-781') for d in range(1, 15)]
c.post('/attendance/save', json={'month_year': LEFT_IN, 'rows': rows}, headers=H)

# The office records that he left on the 10th.
r = c.post('/employees', json={'emp_no': 'F-780', 'name': 'RAJU SINGH', 'trade': 'MASON',
           'total_salary': 1500, 'basic_salary': 1000, 'active': True,
           'terminated_on': LEFT_ON}, headers=H)
ck('leaving date is accepted', r.status_code == 200, r.text[:200])

def on_screen(day, headers=H):
    return {e['emp_no'] for e in
            c.get(f'/employees?active_only=true&as_of={day}', headers=headers).json()}

ck('still on the attendance screen the day he left', 'F-780' in on_screen(LEFT_ON))
ck('still on the screen later in the same cycle', 'F-780' in on_screen('2026-09-20'))
ck('gone from the screen in the next cycle', 'F-780' not in on_screen('2026-10-05'),
   on_screen('2026-10-05'))
ck('gone for a site engineer too', 'F-780' not in on_screen('2026-10-05', SITE))
ck('and the cycle after that', 'F-780' not in on_screen('2026-11-05'))
ck('the man still working is unaffected', 'F-781' in on_screen('2026-11-05'))

# The master list is the record of who worked here, so he stays on it.
master = {e['emp_no']: e for e in c.get('/employees?active_only=true', headers=H).json()}
ck('still in Master Data', 'F-780' in master, sorted(master))
ck('with his name', master.get('F-780', {}).get('name') == 'RAJU SINGH')
ck('with his card number', master.get('F-780', {}).get('emp_no') == 'F-780')
ck('and his leaving date on the record',
   str(master.get('F-780', {}).get('terminated_on')) == LEFT_ON,
   master.get('F-780', {}).get('terminated_on'))

# The days after he left are rewritten, or he would be paid for a
# fortnight he did not work.
card = c.get(f'/live-card/F-780/{LEFT_IN}', headers=H).json()
days = card['days']
ck('his last day is left as it was', days.get('2026-09-10', {}).get('am') == 'Present',
   days.get('2026-09-10'))
after = [days[d]['am'] for d in sorted(days) if d > LEFT_ON]
ck('every day after it reads Terminated', after and all(a == 'Terminated' for a in after),
   sorted(set(after)))
ck('he keeps his card for the cycle he left in', bool(card.get('summary')))

# And he is not asked about again in the cycles that follow.
nxt = c.get(f'/live-card/F-780/{NEXT}', headers=H).json()
ck('no card for the next cycle', not nxt.get('summary'), nxt.get('summary'))

listed = {e['emp_no'] for e in c.get(f'/employees?active_only=true&month_year={NEXT}',
                                     headers=H).json()}
ck('not on the next cycle\'s payroll list', 'F-780' not in listed, listed)
listed_now = {e['emp_no'] for e in c.get(f'/employees?active_only=true&month_year={LEFT_IN}',
                                         headers=H).json()}
ck('but on the list for the cycle he left in', 'F-780' in listed_now)

print('\n' + ('ALL PASS' if not FAIL else f'{len(FAIL)} FAILED: ' + '; '.join(FAIL)))
sys.exit(1 if FAIL else 0)

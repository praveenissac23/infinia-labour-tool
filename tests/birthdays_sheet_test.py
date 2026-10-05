"""Birthdays.xlsx: staff dates of birth onto their files, clients into the birthday list.

Run: cd app && rm -f /tmp/bs.db && DATABASE_URL=sqlite:////tmp/bs.db python3 ../tests/birthdays_sheet_test.py
"""
import sys
from datetime import date
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main, people

db = database.SessionLocal()
db.query(models.Setting).filter(models.Setting.key == "birthdays_sheet_loaded").delete()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Administrator', role='admin'))
db.add(models.User(username='lab', hashed_password=auth.hash_password('p'), full_name='Lab', role='office', permissions='people_labour'))
for no, nm in (('IC001', 'JOMON THOMAS'), ('IC022', 'MOHAMED SHAFEEQ'), ('PI001', 'SHYJU THOMAS'), ('IC201', 'SHAJI MATHEW'),
               ('IC021', 'MOHAMMED ALI'), ('IC010', 'AYSHA HIBA')):
    db.add(models.Employee(emp_no=no, name=nm, staff=True, pay_group='staff', designation='X', total_salary=5000, basic_salary=2000, active=True))
db.commit()
e10 = db.query(models.Employee).filter_by(emp_no='IC010').first()
db.add(models.PeopleProfile(employee_id=e10.id, date_of_birth=date(2001, 8, 2)))   # already on file, differs from the sheet
db.commit(); db.close()

people.seed_birthdays(database.SessionLocal)
db = database.SessionLocal()
dob = lambda no: getattr(people._profile(db, db.query(models.Employee).filter_by(emp_no=no).first()), 'date_of_birth', None)
FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{x}]'))
    if not ok: FAIL.append(l)

ck('by code and name', dob('IC001') == date(1995, 4, 20), dob('IC001'))
ck('sheet code IC021 belongs to someone else: found by name on IC022', dob('IC022') == date(1990, 4, 18) and (dob('IC021') is None), (dob('IC022'), dob('IC021')))
ck('same code, spelt differently (Shaiju / SHYJU THOMAS)', dob('PI001') == date(1986, 3, 29), dob('PI001'))
ck('owner by code (Shaji Sir / SHAJI MATHEW)', dob('IC201') == date(1962, 10, 5), dob('IC201'))
ck('a date already on file is kept', dob('IC010') == date(2001, 8, 2), dob('IC010'))
names = {c.name.title(): c for c in db.query(models.BirthdayContact).all()}
ck('clients loaded, with and without a date', names.get('Karim Panju') and names['Karim Panju'].date_of_birth == date(1978, 4, 25)
   and names.get('Gourav') and names['Gourav'].date_of_birth is None and names['Aditya Bhagra'].date_of_birth == date(1988, 1, 5), list(names))
ck('Rizwana (left Infinia) not on the list', not any('RIZWANA' in n.upper() for n in names))
log = db.query(models.AuditLog).filter_by(action='birthdays_loaded').first()
ck('what happened is in the activity log', log and 'kept the date already on file' in log.details, log and log.details)
db.close()
people.seed_birthdays(database.SessionLocal)
db = database.SessionLocal()
ck('runs once only', db.query(models.BirthdayContact).count() == len(names))
db.close()

c = TestClient(main.app)
tok = lambda u: {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': u, 'password': 'p'}).json()['access_token']}
H, LAB = tok('admin'), tok('lab')
up = c.get('/employees/people/birthdays/upcoming', headers=H).json()
ck('admin sees clients among the birthdays', any(r['group'] == 'client' for r in up['rows']))
ck('labour-only login does not', not any(r['group'] == 'client' for r in c.get('/employees/people/birthdays/upcoming', headers=LAB).json()['rows']))
ck('client list closed to labour-only login', c.get('/employees/people/birthday-contacts', headers=LAB).status_code == 403)
r = c.post('/employees/people/birthday-contacts', headers=H, json={'name': 'New Client', 'relation': 'Client', 'project_no': '912', 'date_of_birth': '1980-10-07'})
ck('add a client birthday, name in capitals', r.status_code == 200 and r.json()['name'] == 'NEW CLIENT', r.text)
cid = r.json()['id']
ck('edit', c.put(f'/employees/people/birthday-contacts/{cid}', headers=H, json={'date_of_birth': '1981-10-07'}).json()['date_of_birth'] == '1981-10-07')
ck('delete', c.delete(f'/employees/people/birthday-contacts/{cid}', headers=H).json().get('ok'))
T = auth.create_download_token('admin')
r = c.get(f'/export/people/birthdays/view?group=client&token={T}')
ck('clients report', r.status_code == 200 and 'Birthdays - Clients' in r.text and 'KARIM PANJU' in r.text, r.status_code)

print('\nALL PASS' if not FAIL else f'\n{len(FAIL)} FAILED: {FAIL}')

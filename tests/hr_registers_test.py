"""The office registers: absence, additions and deductions, loans, history.

Run: cd app && DATABASE_URL=sqlite:////tmp/hr.db python3 ../tests/hr_registers_test.py

Everyone is at work unless something is recorded, and the salary cycle
fills itself from what is recorded - the same way the labour cards fill
from attendance. These are the rules the office pays by, as they were
given:

  * one sick day a month is paid; any more that month count as absent
  * a half day absent is half a day
  * a vacation's days are deducted like absence, and leave salary is paid
    for them separately, as an addition, when he goes
  * a range of days is counted in calendar days, Sundays included
"""
import sys
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


def money(a, b):
    return abs(round(a, 2) - round(b, 2)) < 0.005


db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'),
                   full_name='Praveen', role='admin'))
db.commit(); db.close()
c = TestClient(main.app)
H = {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': 'admin', 'password': 'p'}).json()['access_token']}

CO = c.post('/employees/companies', json={'name': 'TEST CO', 'short_name': 'Test'}, headers=H).json()
for code, name, joined, basic, allow in (('T01', 'ALI', '2024-01-10', 2400, 3600),
                                         ('T02', 'BINA', '2026-01-05', 1200, 1800)):
    r = c.post('/employees/staff', json={'emp_no': code, 'name': name, 'company_id': CO['id'],
               'joined_on': joined, 'basic': basic, 'allowance': allow}, headers=H)
    assert r.status_code == 200, r.text
SEP, OCT = 'September 2026', 'October 2026'


def leave(**kw):
    return c.post('/employees/leave', json=kw, headers=H)


def cycle(month=SEP):
    r = c.post('/employees/payroll/runs', json={'month_year': month, 'company_id': CO['id'],
                                                'group': 'staff'}, headers=H).json()
    return r, {l['emp_no']: l for l in r['lines']}


# ---- The sick-day rule ------------------------------------------------
# Ali, 6,000 a month: a day is 200.
ck('a sick day goes in', leave(emp_no='T01', kind='sick', **{'from': '2026-09-03'}).status_code == 200)
ck('and a second one', leave(emp_no='T01', kind='sick', **{'from': '2026-09-10'}).status_code == 200)
run, L = cycle()
ck("the month's first sick day is paid and the second deducted: 200.00",
   money(L['T01']['deduction'], 200), (L['T01']['deduction'], L['T01']['deduction_note']))
ck('and the note names the kind and the day deducted', 'Sick 10 Sep' in L['T01']['deduction_note'],
   L['T01']['deduction_note'])

# Bina: a half sick day uses half the allowance, so a full sick day after
# it is half paid and half deducted. 3,000 a month: a day is 100.
leave(emp_no='T02', kind='sick', half=True, **{'from': '2026-09-05'})
leave(emp_no='T02', kind='sick', **{'from': '2026-09-12'})
run, L = cycle()
ck('after a paid half sick day, the next sick day is half deducted: 50.00',
   money(L['T02']['deduction'], 50), L['T02']['deduction'])

# ---- Half day absent, and an override ---------------------------------
leave(emp_no='T01', kind='absent', half=True, **{'from': '2026-09-15'})
r = leave(emp_no='T01', kind='sick', pay_rule='paid', **{'from': '2026-09-11'})
run, L = cycle()
ck('a half day absent is half a day: 100.00 more, 300.00 in all',
   money(L['T01']['deduction'], 300), L['T01']['deduction'])
ck('a sick day the accountant marks paid costs nothing, allowance or not',
   money(L['T01']['deduction'], 300))

# ---- A vacation -------------------------------------------------------
r = leave(emp_no='T01', kind='vacation', **{'from': '2026-09-20', 'to': '2026-09-29'},
          leave_salary=6000, air_ticket=1200, pay_month=SEP)
ck('ten days of vacation go in as one entry', r.status_code == 200 and r.json()['days'] == 10, r.text[:200])
vac = r.json()['batch']
run, L = cycle()
ck('the ten days are deducted: 2,000.00 more, 2,300.00 in all',
   money(L['T01']['deduction'], 2300), L['T01']['deduction'])
ck('and leave salary and the ticket are on the same cycle',
   money(L['T01']['leave_salary'], 6000) and money(L['T01']['air_ticket'], 1200),
   (L['T01']['leave_salary'], L['T01']['air_ticket']))
ck('net pay is salary less the days away, plus leave salary and ticket: 10,900.00',
   money(L['T01']['net_pay'], 6000 - 2300 + 6000 + 1200), L['T01']['net_pay'])
lst = c.get(f'/employees/leave?month_year={SEP}', headers=H).json()
v = [x for x in lst['rows'] if x['batch'] == vac][0]
ck('the register shows the vacation as one line, 20 to 29 September',
   v['from'] == '2026-09-20' and v['to'] == '2026-09-29' and v['days'] == 10, v)
ck('and what it costs this month', money(v['cost'], 2000), v['cost'])
ck('a day already taken cannot be recorded twice',
   leave(emp_no='T01', kind='absent', **{'from': '2026-09-25'}).status_code == 400)

# ---- Changing an entry ------------------------------------------------
r = c.put(f'/employees/leave/entry/{vac}', json={'kind': 'vacation', 'from': '2026-09-20',
          'to': '2026-09-24', 'leave_salary': 5000, 'pay_month': SEP}, headers=H)
ck('the vacation can be shortened', r.status_code == 200, r.text[:200])
run, L = cycle()
ck('and the cycle follows: five days, 1,300.00 in all', money(L['T01']['deduction'], 1300),
   L['T01']['deduction'])
ck('with the new leave salary and no ticket',
   money(L['T01']['leave_salary'], 5000) and L['T01']['air_ticket'] == 0,
   (L['T01']['leave_salary'], L['T01']['air_ticket']))
sick2 = [x for x in c.get(f'/employees/leave?month_year={SEP}', headers=H).json()['rows']
         if x['emp_no'] == 'T01' and x['from'] == '2026-09-10'][0]
ck('an entry can be removed', c.delete(f"/employees/leave/entry/{sick2['batch']}", headers=H).status_code == 200)
run, L = cycle()
ck('and its deduction goes with it: 1,100.00', money(L['T01']['deduction'], 1100), L['T01']['deduction'])

# ---- Across a month end, and a whole month away -----------------------
leave(emp_no='T02', kind='vacation', **{'from': '2026-09-28', 'to': '2026-10-03'})
run, L = cycle()
ck('a vacation across the month end counts only its September days here: 3 days, 300.00 + 50.00',
   money(L['T02']['deduction'], 350), L['T02']['deduction'])
leave(emp_no='T02', kind='unpaid', **{'from': '2026-10-04', 'to': '2026-10-31'})
orun, OL = cycle(OCT)
ck('a whole month away costs the month, not a day more: 3,000.00',
   money(OL['T02']['deduction'], 3000), OL['T02']['deduction'])
ck('and never leaves the salary below nothing', OL['T02']['net_pay'] >= 0, OL['T02']['net_pay'])

# ---- Additions and deductions -----------------------------------------
r = c.post('/employees/pay-items', json={'emp_no': 'T02', 'month_year': SEP, 'direction': 'add',
           'category': 'taxi', 'amount': '1,250.50', 'notes': 'Taxi bills'}, headers=H)
ck('a taxi bill goes in', r.status_code == 200, r.text[:200])
item = r.json()['id']
c.post('/employees/pay-items', json={'emp_no': 'T02', 'month_year': SEP, 'direction': 'deduct',
       'category': 'fine', 'amount': 300, 'notes': 'Speeding'}, headers=H)
run, L = cycle()
ck('the open cycle picks up the bill and the fine',
   money(L['T02']['other_allowance'], 1250.50) and money(L['T02']['statutory'], 300),
   (L['T02']['other_allowance'], L['T02']['statutory']))
ck('and writes the remark from them', 'Taxi bills' in L['T02']['remarks'] and 'Speeding' in L['T02']['remarks'],
   L['T02']['remarks'])
ck('a bill can be corrected', c.put(f'/employees/pay-items/{item}', json={
   'emp_no': 'T02', 'month_year': SEP, 'direction': 'add', 'category': 'taxi', 'amount': 1000,
   'notes': 'Taxi bills'}, headers=H).status_code == 200)
run, L = cycle()
ck('and the cycle follows', money(L['T02']['other_allowance'], 1000), L['T02']['other_allowance'])
ck('an amount of nothing is refused', c.post('/employees/pay-items', json={
   'emp_no': 'T02', 'month_year': SEP, 'direction': 'add', 'category': 'taxi', 'amount': 0},
   headers=H).status_code == 400)

# ---- The sheet keeps what was decided on it -------------------------
c.post('/employees/loans', json={'emp_no': 'T02', 'amount': 1500, 'taken_on': '2026-08-01',
       'instalment': 500, 'terms': 'Monthly 500'}, headers=H)
run, L = cycle()
ck('a loan recorded after the cycle was opened still reaches it', L['T02']['loan_deduction'] == 500,
   L['T02']['loan_deduction'])
ck('and the remark says what is left to pay after it', 'Loan 500.00, balance 1,000.00' in L['T02']['remarks'],
   L['T02']['remarks'])
r = c.put(f"/employees/payroll/runs/{run['id']}", json={'lines': [
    {'id': L['T02']['id'], 'loan_deduction': 0, 'remarks': 'Instalment skipped this month'}]}, headers=H)
run, L = cycle()
ck('an instalment skipped on the sheet stays skipped', L['T02']['loan_deduction'] == 0,
   L['T02']['loan_deduction'])
ck('and so does the remark typed there', L['T02']['remarks'] == 'Instalment skipped this month')
c.put(f"/employees/payroll/runs/{run['id']}", json={'lines': [
    {'id': L['T02']['id'], 'loan_reset': True, 'remarks': ''}]}, headers=H)
run, L = cycle()
ck('and can be put back to the proposal', L['T02']['loan_deduction'] == 500 and
   'Taxi bills' in L['T02']['remarks'], (L['T02']['loan_deduction'], L['T02']['remarks']))

# ---- An approved month is closed to changes ---------------------------
c.post(f"/employees/payroll/runs/{run['id']}/approve", headers=H)
ck('absence in an approved month is refused',
   leave(emp_no='T01', kind='absent', **{'from': '2026-09-02'}).status_code == 400)
ck('and says to reopen the cycle first',
   'Reopen' in leave(emp_no='T01', kind='absent', **{'from': '2026-09-02'}).json()['detail'])
ck('so is a bill for that month', c.post('/employees/pay-items', json={
   'emp_no': 'T01', 'month_year': SEP, 'direction': 'add', 'category': 'taxi', 'amount': 10},
   headers=H).status_code == 400)
ck('and changing one already there', c.delete(f'/employees/pay-items/{item}', headers=H).status_code == 400)
c.post(f"/employees/payroll/runs/{run['id']}/reopen", headers=H)
ck('once reopened it can be changed again',
   leave(emp_no='T01', kind='absent', **{'from': '2026-09-02'}).status_code == 200)
ck('a draft can be thrown away', c.delete(f"/employees/payroll/runs/{orun['id']}", headers=H).status_code == 200)

# ---- Loans: dated repayments, corrections -----------------------------
loan = [l for l in c.get('/employees/loans', headers=H).json()['rows'] if l['emp_no'] == 'T02'][0]
r = c.post(f"/employees/loans/{loan['id']}/repay", json={'amount': 200, 'paid_on': '2026-09-14',
           'source': 'cash', 'notes': 'Paid at the office'}, headers=H)
ck('a repayment goes in with its own date', r.status_code == 200, r.text[:200])
rep = [x for x in r.json()['repayments'] if x['amount'] == 200][0]
ck('and keeps it', rep['paid_on'] == '2026-09-14' and rep['notes'] == 'Paid at the office', rep)
ck('its date and amount can be corrected', c.put(f"/employees/loans/repayments/{rep['id']}",
   json={'amount': 250, 'paid_on': '2026-09-15'}, headers=H).status_code == 200)
loan = [l for l in c.get('/employees/loans', headers=H).json()['rows'] if l['emp_no'] == 'T02'][0]
ck('and the balance follows: 1,250.00', money(loan['balance'], 1250), loan['balance'])
ck('the loan itself can be corrected', c.put(f"/employees/loans/{loan['id']}", json={
   'instalment': 250, 'terms': 'Monthly 250'}, headers=H).status_code == 200)
ck('a repayment can be removed', c.delete(f"/employees/loans/repayments/{rep['id']}", headers=H).status_code == 200)
c.post(f"/employees/payroll/runs/{run['id']}/approve", headers=H)
loan = [l for l in c.get('/employees/loans', headers=H).json()['rows'] if l['emp_no'] == 'T02'][0]
pay = [x for x in loan['repayments'] if x['source'] == 'payroll']
ck('approving September took its instalment', len(pay) == 1 and money(pay[0]['amount'], 250), loan['repayments'])
ck('which cannot be edited from the loan - it is part of what was paid',
   c.put(f"/employees/loans/repayments/{pay[0]['id']}", json={'amount': 1}, headers=H).status_code == 400)
ck('and a loan with salary instalments cannot be deleted',
   c.delete(f"/employees/loans/{loan['id']}", headers=H).status_code == 400)

# ---- Salary history ---------------------------------------------------
r = c.post('/employees/increments', json={'emp_no': 'T01', 'effective_on': '2027-02-01',
           'amount': 500, 'reason': 'Promised'}, headers=H)
inc = [x for x in c.get('/employees/increments?emp_no=T01', headers=H).json()['rows'] if x['kind'] == 'increment'][0]
ck('a rise to come can be corrected', c.put(f"/employees/increments/{inc['id']}", json={
   'basic': 2400, 'allowance': 4400}, headers=H).status_code == 200)
inc = [x for x in c.get('/employees/increments?emp_no=T01', headers=H).json()['rows'] if x['kind'] == 'increment'][0]
ck('and the rise is worked out again: 800.00', money(inc['amount'], 800), inc['amount'])
ck('and removed', c.delete(f"/employees/increments/{inc['id']}", headers=H).status_code == 200)
j = [x for x in c.get('/employees/increments?emp_no=T01', headers=H).json()['rows'] if x['kind'] == 'joining'][0]
ck('but not the joining salary, which is where the history starts',
   c.delete(f"/employees/increments/{j['id']}", headers=H).status_code == 400)
r = c.post('/employees/increments', json={'emp_no': 'T02', 'effective_on': '2026-06-01',
           'amount': 300, 'reason': 'Mid-year'}, headers=H)
inc = [x for x in c.get('/employees/increments?emp_no=T02', headers=H).json()['rows'] if x['kind'] == 'increment'][0]
c.put(f"/employees/increments/{inc['id']}", json={'basic': 1200, 'allowance': 2200}, headers=H)
st = {s['emp_no']: s for s in c.get('/employees/staff', headers=H).json()['rows']}
ck('correcting a rise already in force corrects the salary on the record', st['T02']['gross'] == 3400,
   st['T02']['gross'])

# ---- What was on the sheets before the registers ---------------------
db = database.SessionLocal()
e = db.query(models.Employee).filter(models.Employee.emp_no == 'T01').first()
old = models.PayrollRun(company_id=CO['id'], month_year='July 2026', group='staff', status='approved')
db.add(old); db.flush()
db.add(models.PayrollLine(run_id=old.id, employee_id=e.id, basic=2400, allowance=3600,
                          fixed_salary=6000, other_allowance=412.5, statutory=126,
                          remarks='Taxi Bills; ILOE', net_pay=6286.5))
db.add(models.StaffLeave(employee_id=e.id, on_date=main.date(2026, 7, 7), portion=1.0,
                         reason='sick', paid=False))
main.put_setting(db, 'hr_items_migrated', '')
db.commit()
main._migrate_hr(db)
items = c.get('/employees/pay-items?month_year=July 2026', headers=H).json()['rows']
ck('bills typed straight onto an old sheet become register entries',
   sorted((i['category'], i['amount']) for i in items) == [('iloe', 126.0), ('taxi', 412.5)], items)
lv = c.get('/employees/leave?month_year=July 2026', headers=H).json()['rows']
ck('an old leave day keeps the decision it was paid on',
   len(lv) == 1 and lv[0]['pay_rule'] == 'unpaid' and lv[0]['kind'] == 'sick', lv)
c.post(f'/employees/payroll/runs/{old.id}/reopen', headers=H)
again = c.get(f'/employees/payroll/runs/{old.id}', headers=H).json()
ln = again['lines'][0]
ck('and re-opening that old month gives the same figures',
   money(ln['other_allowance'], 412.5) and money(ln['statutory'], 126) and ln['remarks'] == 'Taxi Bills; ILOE',
   (ln['other_allowance'], ln['statutory'], ln['remarks']))
db.close()

# ---- The papers --------------------------------------------------------
DL = c.post('/auth/download-token', headers=H).json()['token']
for label, base in (('absence', f'/export/payroll/leave?month_year=September%202026'),
                    ('additions and deductions', f'/export/payroll/items?month_year=September%202026'),
                    ('salary history', '/export/payroll/increments?')):
    sep = '' if base.endswith('?') else '&'
    pv = c.get(base.replace('?', '/view?', 1) + f'{sep}token={DL}')
    ck(f'the {label} report previews', pv.status_code == 200 and 'Download PDF' in pv.text, pv.status_code)
    for fmt, head in (('pdf', b'%PDF'), ('excel', b'PK')):
        r = c.get(f'{base}{sep}token={DL}&format={fmt}')
        ck(f'the {label} report downloads as {fmt}', r.status_code == 200 and r.content[:2] == head[:2],
           r.status_code)

print()
if FAIL:
    print(f'{len(FAIL)} FAILED')
    for f in FAIL:
        print('  -', f)
    sys.exit(1)
print('THE REGISTERS PAY BY THE RULES')

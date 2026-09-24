"""August 2026, rebuilt in the app, matched against the signed statements.

Run: cd app && DATABASE_URL=sqlite:////tmp/op.db python3 ../tests/office_payroll_test.py

The whole point of moving office payroll off the spreadsheet is that
every document comes from one set of figures and none of them can
disagree. The way to know that works is to rebuild a month somebody
already signed and see whether the app produces the same numbers.

August 2026 is that month. The signed statements total 86,609.50 for
Infinia and 17,378.50 for Prime Infinia, and the consolidated statement
produced alongside them says 93,187.00 - short by 10,801, because three
staff lost a deduction, two lost their leave salary and one lost a loan
instalment somewhere between one document and the next. The app has to
produce the signed figures and a consolidated total that agrees with
them.

Everything entered below is taken from the statements, the leave sheet
and the loan sheet as they stand. The only thing invented is a staff
code for the five people the spreadsheet never gave one - the two paid
by cash and the three drawing remuneration by bank transfer - because a
record has to be called something.
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
db.add(models.User(username='muhsina', hashed_password=auth.hash_password('p'),
                   full_name='Muhsina', role='office'))
db.commit()
db.close()

c = TestClient(main.app)


def tok(u):
    return {'Authorization': 'Bearer ' + c.post(
        '/auth/login', data={'username': u, 'password': 'p'}).json()['access_token']}


H, OFFICE = tok('admin'), tok('muhsina')

CYCLE = 'August 2026'

# ---- The two companies ------------------------------------------------
IC = c.post('/employees/companies', json={
    'name': 'INFINIA CONTRACTING L.L.C.', 'short_name': 'Infinia',
    'code_prefix': 'IC', 'trn': '100602393900003'}, headers=H).json()
PI = c.post('/employees/companies', json={
    'name': 'PRIME INFINIA', 'short_name': 'Prime Infinia',
    'code_prefix': 'PI'}, headers=H).json()
ck('the companies go on file', IC.get('id') and PI.get('id'), [IC, PI])

# ---- The staff, as the August statements show them --------------------
# emp_no, name, joined, basic, allowance, company, designation, route
STAFF = [
    ('IC001', 'JOMON THOMAS',        '2022-08-22', 2600, 3900, IC, 'P.R.O', 'wps'),
    ('IC010', 'AYSHA HIBA',          '2024-07-19', 2800, 4200, IC, 'Design', 'wps'),
    ('IC017', 'ARATHI SAJEENDRAN',   '2025-02-11', 3200, 4800, IC, 'QS', 'wps'),
    ('IC019', 'NEETHU TREESA JOSE',  '2025-06-24', 2800, 4200, IC, 'QS', 'wps'),
    ('IC020', 'RAJASEKAR MUNIYAN',   '2025-06-09', 4800, 7200, IC, 'Project Engineer', 'wps'),
    ('IC022', 'MOHAMED SHAFEEQ',     '2025-09-01', 2800, 4200, IC, 'Accounts', 'wps'),
    ('IC023', 'AKHIL R',             '2025-12-11', 4400, 6600, IC, 'Project Engineer', 'wps'),
    ('IC024', 'FEBIYANS LUCAS',      '2025-12-19', 4000, 6000, IC, 'Project Engineer', 'wps'),
    ('IC025', 'PREENU ANNIE DANIEL', '2026-03-14', 2000, 3000, IC, 'QS', 'wps'),
    # Paid in cash, and carrying no basic/allowance split on the sheet.
    ('IC101', 'PREM RAJ',            '2025-09-08', 12000, 0, IC, 'Site Engineer', 'cash'),
    ('IC102', 'MATHEW GEORGE',       '2026-06-18', 2500, 0, IC, 'Office Assistant', 'cash'),
    # Remuneration, drawn by bank transfer. No joining date is printed on
    # the statement, so none is entered.
    ('IC201', 'SHAJI MATHEW',        '', 20000, 0, IC, 'Project Director', 'bank'),
    ('IC202', 'NAVEEN MATHEW SHAJI', '', 40000, 0, IC, 'Manager', 'bank'),
    ('IC203', 'PRAVEEN ISSAC SHAJI', '', 40000, 0, IC, 'Manager', 'bank'),
    ('PI001', 'SHYJU THOMAS',        '2026-06-01', 2000, 3000, PI, 'Site Supervisor', 'wps'),
    ('PI002', 'SYED ABDUL REHIM',    '2026-07-13', 1600, 2400, PI, 'Junior Engineer', 'wps'),
    ('PI003', 'SREEKANTH R',         '2026-07-22', 2700, 4050, PI, 'Purchase', 'wps'),
    ('PI004', 'MUHSINA PALERI',      '2026-08-01', 1200, 1800, PI, 'Admin', 'wps'),
]
for emp_no, name, joined, basic, allow, co, desig, route in STAFF:
    c.post('/employees', json={'emp_no': emp_no, 'name': name, 'trade': desig,
                               'company': co['short_name'], 'total_salary': basic + allow,
                               'basic_salary': basic}, headers=H)
    r = c.put(f'/employees/staff/{emp_no}', json={
        'company_id': co['id'], 'joined_on': joined, 'designation': desig,
        'basic': basic, 'allowance': allow, 'contract_basic': basic,
        'pay_route': route}, headers=H)
    assert r.status_code == 200, f'{emp_no}: {r.text[:200]}'
# The two who joined Prime in September, put on file the way the screen
# does it. They must not turn up in August.
for code, name, joined, basic, allow, desig in (
        ('PI005', 'Amal P K', '2026-09-10', 1200, 1800, 'Communication Asst'),
        ('PI006', 'Anoop Subramanian', '2026-09-15', 5600, 8400, 'Senior QS')):
    r = c.post('/employees/staff', json={
        'emp_no': code, 'name': name, 'company_id': PI['id'], 'joined_on': joined,
        'designation': desig, 'basic': basic, 'allowance': allow,
        'contract_basic': basic, 'pay_route': 'wps'}, headers=H)
    ck(f'{name} is added straight onto the staff register', r.status_code == 200, r.text[:200])
ck('a staff code already in use is refused',
   c.post('/employees/staff', json={'emp_no': 'PI005', 'name': 'X', 'company_id': PI['id'],
                                    'joined_on': '2026-09-01'}, headers=H).status_code == 400)

# A labourer, so the labour side has someone of its own.
c.post('/employees', json={'emp_no': '5001', 'name': 'RAJAN', 'trade': 'Mason',
                           'company': 'Infinia', 'total_salary': 1500, 'basic_salary': 900},
       headers=H)

staff = {s['emp_no']: s for s in c.get('/employees/staff', headers=H).json()['rows']}
ck('all twenty staff are on file', len(staff) == 20, len(staff))

# ---- None of them are labourers ----------------------------------------
labour = [e['emp_no'] for e in c.get('/employees', headers=H).json()]
ck('the labour list does not carry a single office name',
   labour == ['5001'], labour)
ck('the workforce report leaves them out too',
   all(r['emp_no'] == '5001' for r in main._employee_report_rows(database.SessionLocal())))
r = c.post('/employees', json={'emp_no': 'IC022', 'name': 'OVERWRITTEN', 'trade': 'Helper',
                               'total_salary': 1, 'basic_salary': 1}, headers=H)
ck('Master Data cannot overwrite an office record', r.status_code == 400, r.status_code)
ck('and says where to go instead', 'HR & Payroll' in r.json().get('detail', ''), r.json())
ck('Master Data cannot delete one either',
   c.delete('/employees/IC022', headers=H).status_code == 400)

# A labour import deactivates anyone not in the file. Office staff are
# never in the labour file, so this used to switch every one of them off.
import io, openpyxl
wb = openpyxl.Workbook(); ws = wb.active
tpl = c.get('/employees/template', headers=H)
if tpl.status_code == 200:
    hdr = [x.value for x in openpyxl.load_workbook(io.BytesIO(tpl.content)).active[1]]
else:
    hdr = ['Emp No', 'Name', 'Trade', 'Company', 'Total Salary', 'Basic Salary']
ws.append(hdr)
row = {h: '' for h in hdr}
for h in hdr:
    k = str(h).lower()
    if 'no' in k: row[h] = '5001'
    elif 'name' in k: row[h] = 'RAJAN'
    elif 'trade' in k: row[h] = 'Mason'
    elif 'total' in k: row[h] = 1500
    elif 'basic' in k: row[h] = 900
    elif 'company' in k: row[h] = 'Infinia'
ws.append([row[h] for h in hdr])
buf = io.BytesIO(); wb.save(buf); buf.seek(0)
r = c.post('/employees/import', data={'mode': 'replace', 'duplicate_handling': 'update'},
           files={'file': ('labour.xlsx', buf.getvalue())}, headers=H)
still = len(c.get('/employees/staff', headers=H).json()['rows'])
ck('a labour import leaves every office record active', still == 20,
   f'{r.status_code} {r.text[:160]} -> {still} active')
ck('the 40/60 split came through on the WPS nine',
   all(abs(staff[k]['basic_pct'] - 40) < 0.05
       for k in staff if k.startswith('IC0') or k.startswith('PI')),
   [(k, staff[k]['basic_pct']) for k in sorted(staff)])

# ---- The leave sheet for August --------------------------------------
# Which days cost money is the accountant's judgement, and the August
# sheet shows it exercised: some sick days were paid and some were not.
# Marked here exactly as the deductions on the signed statements imply.
LEAVE = [
    # emp_no, date, half?, paid?, reason
    ('IC017', '2026-08-14', True,  False, 'sick'),          # deducted: 133.00
    ('IC017', '2026-08-26', True,  True,  'Onam day off'),
    ('IC019', '2026-08-15', False, True,  'sick'),
    ('IC020', '2026-08-18', False, True,  'sick'),
    ('IC020', '2026-08-24', False, False, 'absent'),        # deducted: 400.00
    ('IC025', '2026-08-18', False, True,  'sick'),
    ('IC025', '2026-08-24', False, False, 'sick'),          # deducted: 166.00
    ('IC010', '2026-08-25', False, True,  'sick'),
    ('IC101', '2026-08-08', True,  True,  'sick (2 hrs)'),
    ('IC101', '2026-08-29', False, False, 'absent'),        # deducted: 400.00
    ('PI002', '2026-08-20', False, True,  'sick'),
    ('PI002', '2026-08-21', False, False, 'sick'),          # deducted: 133.00
    ('PI003', '2026-08-15', False, True,  'sick'),
    ('PI003', '2026-08-27', True,  False, 'sick'),          # deducted: 112.50
    ('PI004', '2026-08-24', False, True,  'sick'),
]
for emp_no, on, half, paid, reason in LEAVE:
    r = c.post('/employees/leave', json={'emp_no': emp_no, 'on_date': on,
                                         'half': half, 'paid': paid, 'reason': reason},
               headers=H)
    assert r.status_code == 200, f'{emp_no} {on}: {r.text[:160]}'
ck('the leave sheet is loaded - fifteen events, thirteen days',
   c.get(f'/employees/leave?month_year={CYCLE}', headers=H).json()['days'] == 13.0,
   c.get(f'/employees/leave?month_year={CYCLE}', headers=H).json()['days'])

# ---- The loan sheet ---------------------------------------------------
loans = [('IC001', 55000, '2022-11-01', 'Reimbursement through Pettycash', 0),
         ('IC022', 12000, '2025-09-15', 'Reimbursement monthly 3000 each', 3000),
         ('PI002', 1000,  '2026-07-13', 'Monthly 500 reimbursement', 500),
         ('PI003', 3000,  '2026-07-22', 'Monthly 500 reimbursement', 500)]
for emp_no, amt, when, terms, inst in loans:
    r = c.post('/employees/loans', json={'emp_no': emp_no, 'amount': amt,
                                         'taken_on': when, 'terms': terms,
                                         'instalment': inst}, headers=H)
    assert r.status_code == 200, r.text[:160]
# Jomon's 55,000 is already down to 22,000 by August, and Shafeeq's
# 12,000 to 9,000 - August's instalment is the fourth, and the loan
# sheet printed with the payroll shows 6,000 left after it.
rows = {l['emp_no']: l for l in c.get('/employees/loans', headers=H).json()['rows']}
c.post(f"/employees/loans/{rows['IC001']['id']}/repay", json={
    'amount': 33000, 'paid_on': '2026-07-31', 'source': 'cash',
    'notes': 'Recovered through petty cash to July'}, headers=H)
c.post(f"/employees/loans/{rows['IC022']['id']}/repay", json={
    'amount': 3000, 'paid_on': '2026-07-31', 'source': 'cash'}, headers=H)
after = {l['emp_no']: l['balance'] for l in c.get('/employees/loans', headers=H).json()['rows']}
ck("Jomon's balance reads 22,000 as the loan sheet says", after.get('IC001') == 22000, after)
ck("Shafeeq's reads 9,000 before August's instalment", after.get('IC022') == 9000, after)

# ======================================================================
#  INFINIA - the nine on WPS, two in cash, three by transfer
# ======================================================================
run = c.post('/employees/payroll/runs', json={
    'month_year': CYCLE, 'company_id': IC['id'], 'group': 'staff'}, headers=H)
ck('the Infinia cycle opens', run.status_code == 200, run.text[:200])
run = run.json()
ck('with a row for each of the fourteen', len(run['lines']) == 14, len(run['lines']))

lines = {l['emp_no']: l for l in run['lines']}
ck('the fixed salary arrived without being typed',
   lines['IC020']['fixed_salary'] == 12000 and lines['IC001']['fixed_salary'] == 6500,
   {k: v['fixed_salary'] for k, v in lines.items()})

# The four deductions the app proposes on its own, and the signed
# statement's figures beside them. The daily rate is gross over thirty
# dropped to whole dirhams, which is what makes 8,000 give 133.00 and
# not 133.34.
for emp_no, want in (('IC020', 400.00), ('IC017', 133.00),
                     ('IC025', 166.00), ('IC101', 400.00)):
    ck(f'it proposes {lines[emp_no]["name"].title()} {want:,.2f} unprompted',
       money(lines[emp_no]['deduction'], want), lines[emp_no]['deduction'])
ck('and nothing for the paid sick days',
   lines['IC019']['deduction'] == 0 and lines['IC010']['deduction'] == 0)
ck('the loan instalment due is on the row', lines['IC022']['loan_deduction'] == 3000,
   lines['IC022']['loan_deduction'])
ck("and nothing for Jomon, whose loan comes back through petty cash",
   lines['IC001']['loan_deduction'] == 0, lines['IC001']['loan_deduction'])
ck('the deduction says which days it is for',
   '24 Aug' in lines['IC020']['deduction_note'], lines['IC020']['deduction_note'])

# What is left is what only the month knows: the bills, the leave
# salary, the ticket. They go in the additions register, as the
# accountant will enter them, and the open cycle picks them up.
ITEMS = [
    ('IC001', 'add', 'leave_salary', 7000, ''),
    ('IC001', 'add', 'air_ticket', 500, ''),
    ('IC010', 'add', 'taxi', 1228.00, 'Taxi Bills'),
    ('IC017', 'add', 'taxi', 328.00, 'Taxi Bills'),
    ('IC019', 'add', 'taxi', 315.50, 'Taxi Bills'),
    ('IC020', 'add', 'fees', 241.50, 'SOE Fee 241.50'),
    ('IC022', 'add', 'leave_salary', 7000, ''),
    ('IC025', 'add', 'taxi', 195.50, 'Taxi Bills'),
]
for emp, d, cat, amt, note in ITEMS:
    r = c.post('/employees/pay-items', json={'emp_no': emp, 'month_year': CYCLE,
               'direction': d, 'category': cat, 'amount': amt, 'notes': note}, headers=H)
    assert r.status_code == 200, r.text[:200]
REMARKS = {'IC101': 'BY CASH', 'IC102': 'BY CASH',
           'IC201': "Project Director's remuneration",
           'IC202': "Manager's remuneration", 'IC203': "Manager's remuneration"}
r = c.put(f"/employees/payroll/runs/{run['id']}",
          json={'lines': [{'id': lines[k]['id'], 'remarks': v} for k, v in REMARKS.items()]},
          headers=H)
ck('the additions register fills the open cycle by itself', r.status_code == 200, r.text[:200])
run = r.json()
lines = {l['emp_no']: l for l in run['lines']}
ck('with the remark written from the entries',
   lines['IC020']['remarks'].startswith('SOE Fee 241.50'), lines['IC020']['remarks'])
ck("and a remark typed on the sheet kept", lines['IC101']['remarks'] == 'BY CASH',
   lines['IC101']['remarks'])

# Against the signed sheet, line by line.
SIGNED_IC = {
    # emp_no: (salary payable, loan, leave salary, net pay)
    'IC001': (6500.00,  0.00, 7500.00, 14000.00),
    'IC010': (8228.00,  0.00,    0.00,  8228.00),
    'IC017': (8195.00,  0.00,    0.00,  8195.00),
    'IC019': (7315.50,  0.00,    0.00,  7315.50),
    'IC020': (11841.50, 0.00,    0.00, 11841.50),
    'IC022': (7000.00,  3000.00, 7000.00, 11000.00),
    'IC023': (11000.00, 0.00,    0.00, 11000.00),
    'IC024': (10000.00, 0.00,    0.00, 10000.00),
    'IC025': (5029.50,  0.00,    0.00,  5029.50),
    'IC101': (11600.00, 0.00,    0.00, 11600.00),
    'IC102': (2500.00,  0.00,    0.00,  2500.00),
}
bad = [(k, lines[k]['payable'], lines[k]['loan_deduction'],
        round(lines[k]['leave_salary'] + lines[k]['air_ticket'], 2), lines[k]['net_pay'])
       for k, v in SIGNED_IC.items()
       if not (money(lines[k]['payable'], v[0]) and money(lines[k]['loan_deduction'], v[1])
               and money(lines[k]['leave_salary'] + lines[k]['air_ticket'], v[2])
               and money(lines[k]['net_pay'], v[3]))]
ck('every Infinia line matches the signed statement', not bad, bad)

t = run['totals']
for label, got, want in (('basic', t['basic'], 29400.00 + 114500.00),
                         ('fixed allowance', t['allowance'], 44100.00),
                         ('taxi and other bills', t['other_allowance'], 2308.50),
                         ('deductions', t['deduction'], 699.00 + 400.00),
                         ('loan reimbursement', t['loan_deduction'], 3000.00),
                         ('leave salary', t['leave_salary'], 14500.00)):
    ck(f'the Infinia {label} total is {want:,.2f}', money(got, want), got)

ck('WPS TOTAL comes to 86,609.50 exactly',
   money(run['by_route'].get('wps', 0), 86609.50), run['by_route'])
ck('BANK TRANSFER comes to 100,000.00',
   money(run['by_route'].get('bank', 0), 100000.00), run['by_route'])
ck('CASH SALARY TOTAL comes to 14,100.00',
   money(run['by_route'].get('cash', 0), 14100.00), run['by_route'])

# ======================================================================
#  PRIME INFINIA - four on WPS
# ======================================================================
prun = c.post('/employees/payroll/runs', json={
    'month_year': CYCLE, 'company_id': PI['id'], 'group': 'staff'}, headers=H).json()
pl = {l['emp_no']: l for l in prun['lines']}
ck('the Prime cycle opens with four rows - not the two who joined in September',
   len(prun['lines']) == 4, [l['emp_no'] for l in prun['lines']])
ck("Syed's 133.00 and Sreekanth's 112.50 come up on their own",
   money(pl['PI002']['deduction'], 133.00) and money(pl['PI003']['deduction'], 112.50),
   (pl['PI002']['deduction'], pl['PI003']['deduction']))
ck("and Muhsina's sick day, which was paid, costs her nothing",
   pl['PI004']['deduction'] == 0, pl['PI004']['deduction'])
ck('both 500 instalments are proposed',
   pl['PI002']['loan_deduction'] == 500 and pl['PI003']['loan_deduction'] == 500)

# Shyju's 126.00 is an ILOE premium, not an absence - it goes in the
# statutory column, and prints in the same place on the sheet.
r = c.post('/employees/pay-items', json={'emp_no': 'PI001', 'month_year': CYCLE,
           'direction': 'deduct', 'category': 'iloe', 'amount': 126, 'notes': 'ILOE DEDUCTION'},
           headers=H)
ck('an ILOE premium goes in as a deduction', r.status_code == 200, r.text[:200])
prun = c.get(f"/employees/payroll/runs/{prun['id']}", headers=H).json()
pl = {l['emp_no']: l for l in prun['lines']}

SIGNED_PI = {'PI001': (4874.00, 0.00, 4874.00), 'PI002': (3867.00, 500.00, 3367.00),
             'PI003': (6637.50, 500.00, 6137.50), 'PI004': (3000.00, 0.00, 3000.00)}
bad = [(k, pl[k]['payable'], pl[k]['loan_deduction'], pl[k]['net_pay'])
       for k, v in SIGNED_PI.items()
       if not (money(pl[k]['payable'], v[0]) and money(pl[k]['loan_deduction'], v[1])
               and money(pl[k]['net_pay'], v[2]))]
ck('every Prime line matches the signed statement', not bad, bad)

pt = prun['totals']
for label, got, want in (('basic', pt['basic'], 7500.00),
                         ('fixed allowance', pt['allowance'], 11250.00),
                         ('deductions', pt['deduction'], 371.50),
                         ('salary payable', pt['payable'], 18378.50),
                         ('loan reimbursement', pt['loan_deduction'], 1000.00)):
    ck(f'the Prime {label} total is {want:,.2f}', money(got, want), got)
ck('Prime WPS TOTAL comes to 17,378.50 exactly',
   money(prun['by_route'].get('wps', 0), 17378.50), prun['by_route'])
ck('and Prime has nobody in cash', prun['by_route'].get('cash', 0) == 0, prun['by_route'])

# ======================================================================
#  The consolidated sheet - the one that went wrong
# ======================================================================
con = c.get(f'/employees/payroll/consolidated?month_year={CYCLE}', headers=H)
ck('the consolidated sheet builds', con.status_code == 200, con.text[:200])
con = con.json()
ck('it carries the eighteen paid in August', len(con['rows']) == 18, len(con['rows']))
ck('the WPS figure is 103,988.00, not the 93,187.00 that was signed off',
   money(con['by_route'].get('wps', 0), 103988.00), con['by_route'])
ck('which is exactly the two statements added up',
   money(con['by_route'].get('wps', 0), 86609.50 + 17378.50))
ck('the three deductions survive the crossing',
   money(con['totals']['deduction'], 699.00 + 400.00 + 371.50),
   con['totals']['deduction'])
ck('and so does the leave salary',
   money(con['totals']['leave_salary'], 14500.00), con['totals']['leave_salary'])
ck('and so does the loan instalment',
   money(con['totals']['loan_deduction'], 4000.00), con['totals']['loan_deduction'])
ck('it says both companies are still in draft',
   sorted(con['draft_companies']) == ['Infinia', 'Prime Infinia'], con['draft_companies'])

# ======================================================================
#  Approving is what moves money
# ======================================================================
bal = {l['emp_no']: l['balance'] for l in c.get('/employees/loans', headers=H).json()['rows']}
ck('nothing has come off a loan while the run is a draft',
   bal['IC022'] == 9000 and bal['PI002'] == 1000, bal)

r = c.post(f"/employees/payroll/runs/{run['id']}/approve", headers=H)
ck('the Infinia run approves', r.status_code == 200, r.text[:200])
r2 = c.post(f"/employees/payroll/runs/{prun['id']}/approve", headers=H)
ck('and so does Prime', r2.status_code == 200, r2.text[:200])
bal = {l['emp_no']: l['balance'] for l in c.get('/employees/loans', headers=H).json()['rows']}
ck("Shafeeq's balance is now 6,000, as the loan sheet printed with the payroll says",
   bal['IC022'] == 6000, bal)
ck("Syed's is 500 and Sreekanth's 2,500",
   bal['PI002'] == 500 and bal['PI003'] == 2500, bal)
ck("Jomon's 22,000 is untouched, because nothing was deducted",
   bal['IC001'] == 22000, bal)

edit = c.put(f"/employees/payroll/runs/{run['id']}",
             json={'lines': [{'id': lines['IC023']['id'], 'other_allowance': 999}]}, headers=H)
ck('an approved run will not take an edit', edit.status_code == 400, edit.status_code)
ck('and it says so in words the accountant can act on',
   'reopen' in edit.json().get('detail', '').lower(), edit.json())

c.post(f"/employees/payroll/runs/{run['id']}/reopen", headers=H)
bal = {l['emp_no']: l['balance'] for l in c.get('/employees/loans', headers=H).json()['rows']}
ck('reopening puts the loan recovery back so it cannot be taken twice',
   bal['IC022'] == 9000, bal)
again = c.post(f"/employees/payroll/runs/{run['id']}/approve", headers=H).json()
bal = {l['emp_no']: l['balance'] for l in c.get('/employees/loans', headers=H).json()['rows']}
ck('and approving again takes it once, not twice', bal['IC022'] == 6000, bal)
ck('the totals are unchanged by the round trip',
   money(again['by_route'].get('wps', 0), 86609.50), again['by_route'])

# ======================================================================
#  Who may look
# ======================================================================
ck('the receptionist cannot open the staff list',
   c.get('/employees/staff', headers=OFFICE).status_code == 403)
ck('nor the payroll runs',
   c.get('/employees/payroll/runs', headers=OFFICE).status_code == 403)
ck('nor a single run she knows the number of',
   c.get(f"/employees/payroll/runs/{run['id']}", headers=OFFICE).status_code == 403)
ck('nor the consolidated sheet',
   c.get(f'/employees/payroll/consolidated?month_year={CYCLE}',
         headers=OFFICE).status_code == 403)
ck('nor the loan balances',
   c.get('/employees/loans', headers=OFFICE).status_code == 403)
ck('nor the leave register',
   c.get(f'/employees/leave?month_year={CYCLE}', headers=OFFICE).status_code == 403)
ck('and she still has her own screens',
   c.get('/employees', headers=OFFICE).status_code == 200)

# ======================================================================
#  September: a rise, and two people who started part way through
# ======================================================================
r = c.post('/employees/increments', json={
    'emp_no': 'IC022', 'effective_on': '2026-09-01', 'amount': 750,
    'reason': 'Increment Sep-26'}, headers=H)
ck("Shafeeq's September rise is recorded", r.status_code == 200, r.text[:160])
ck('and goes on the allowance, with the basic left alone',
   r.json().get('basic') == 2800 and r.json().get('allowance') == 4950, r.json())

# August re-read after the rise is still August: the signed month does
# not quietly pick up September's figure.
again = c.get(f"/employees/payroll/runs/{run['id']}", headers=H).json()
ck("August still pays Shafeeq 7,000", {l['emp_no']: l for l in again['lines']}['IC022']
   ['fixed_salary'] == 7000)

sep = c.post('/employees/payroll/runs', json={
    'month_year': 'September 2026', 'company_id': PI['id'], 'group': 'staff'}, headers=H).json()
sl = {l['emp_no']: l for l in sep['lines']}
ck('September for Prime has all six', len(sl) == 6, sorted(sl))
ck('Amal, from the 10th, is proposed nine days off: 900.00',
   money(sl['PI005']['deduction'], 900.00), (sl['PI005']['deduction'], sl['PI005']['deduction_note']))
ck('Anoop, from the 15th, fourteen days at 466: 6,524.00',
   money(sl['PI006']['deduction'], 6524.00), (sl['PI006']['deduction'], sl['PI006']['deduction_note']))
ck('and the row says why', 'joined 10 sep' in sl['PI005']['deduction_note'].lower(),
   sl['PI005']['deduction_note'])
ck('Syed carries his last 500 instalment', sl['PI002']['loan_deduction'] == 500,
   sl['PI002']['loan_deduction'])

isep = c.post('/employees/payroll/runs', json={
    'month_year': 'September 2026', 'company_id': IC['id'], 'group': 'staff'}, headers=H).json()
il = {l['emp_no']: l for l in isep['lines']}
ck("September for Infinia pays Shafeeq 7,750", il['IC022']['fixed_salary'] == 7750,
   il['IC022']['fixed_salary'])
ck('with the basic still at 2,800', il['IC022']['basic'] == 2800, il['IC022']['basic'])

# A salary corrected by hand on the staff record stays corrected.
c.put('/employees/staff/IC024', json={'basic': 4000, 'allowance': 6100}, headers=H)
c.post('/employees/payroll/runs', json={
    'month_year': 'October 2026', 'company_id': IC['id'], 'group': 'staff'}, headers=H)
f = {s['emp_no']: s for s in c.get('/employees/staff', headers=H).json()['rows']}['IC024']
ck('a correction on the record survives the next cycle being opened',
   f['allowance'] == 6100, f['allowance'])

# ======================================================================
#  The papers
# ======================================================================
DL = c.post('/auth/download-token', headers=H).json().get('token', '')
OFF_DL = c.post('/auth/download-token', headers=OFFICE).json().get('token', '')
ck('the accountant can mint a download token', bool(DL))

PAPERS = [
    ('the salary statement', f"/export/payroll/statement?run_id={run['id']}"),
    ('the consolidated statement',
     f"/export/payroll/consolidated?month_year={CYCLE.replace(' ', '%20')}"),
    ('the loan statement', '/export/payroll/loans?'),
    ('the leave register', f"/export/payroll/leave?month_year={CYCLE.replace(' ', '%20')}"),
    ('the document tracker', '/export/payroll/documents?'),
    ('the staff register', '/export/payroll/staff?'),
]
for label, base in PAPERS:
    sep = '' if base.endswith('?') else '&'
    v = c.get(f'{base}{sep}token={DL}'.replace('?&', '?').replace('&&', '&'))
    # The preview first.
    pv = c.get(f'{base}{sep}token={DL}'.replace('/export/payroll/', '/export/payroll/')
               .replace('?', '/view?', 1))
    ck(f'{label} previews', pv.status_code == 200, pv.status_code)
    if pv.status_code == 200:
        body = pv.text
        ck(f'{label} preview carries the Infinia letterhead',
           'data:image/png;base64' in body, body[:120])
        for want in ('Download PDF', 'Download Excel', 'Print'):
            ck(f'{label} preview offers {want}', want in body)
    for fmt, head in (('pdf', b'%PDF'), ('excel', b'PK')):
        r = c.get(f'{base}{sep}token={DL}&format={fmt}')
        ck(f'{label} downloads as {fmt}',
           r.status_code == 200 and r.content[:4].startswith(head),
           f'{r.status_code} {r.content[:12]}')
    r = c.get(f'{base}{sep}token={OFF_DL}')
    ck(f'the receptionist is refused {label}', r.status_code == 403, r.status_code)

# The statement is the one that has to read like the sheet it replaces.
pv = c.get(f"/export/payroll/statement/view?run_id={run['id']}&token={DL}").text
for gone in ('Sr.', 'Salary Paid', 'Basic Salary', 'Fix Allown.', 'Leave Salary', 'Salary Payable'):
    ck(f'the statement no longer carries "{gone}"', f'>{gone}<' not in pv)
for want in ('Gross Salary', 'Add / Ded.', 'Absent Ded.', 'Loan', 'Net Pay'):
    ck(f'the statement keeps the column "{want}"', want in pv)
for want in ('86,609.50', 'WPS TOTAL', 'BANK TRANSFER', 'CASH SALARY TOTAL'):
    ck(f'and prints {want}', want in pv, want)

print()
if FAIL:
    print(f'{len(FAIL)} FAILED')
    for f in FAIL:
        print('  -', f)
    sys.exit(1)
print('August 2026 rebuilds to the dirham.')

"""Paid status and payslips - office and labour payroll (29 Oct 2026, Shafeeq's list).

    cd app && DATABASE_URL=sqlite:////tmp/ps.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/pay_status_test.py   (empty db)"""
import sys, io, json, zipfile
sys.path.insert(0, '.')
from datetime import date, timedelta
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main, services, paystatus
import payroll_cycle as pcyc

FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{str(x)[:500]}]'))
    if not ok: FAIL.append(l)
T = main._dubai_today()
MONTH = T.strftime('%B %Y')                       # the office month now running
db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Praveen', role='admin'))
db.add(models.User(username='shafeeq', hashed_password=auth.hash_password('p'), full_name='Shafeeq', role='office', permissions='hrpayroll,combine'))
db.add(models.User(username='store', hashed_password=auth.hash_password('p'), full_name='Store', role='office', permissions='store'))
co = models.Company(name='INFINIA CONTRACTING L.L.C.', short_name='Infinia', code_prefix='IC'); db.add(co); db.flush()
def staff(code, name, basic, allow, joined='2024-07-25'):
    e = models.Employee(emp_no=code, name=name, staff=True, pay_group='staff', company_id=co.id, company='Infinia',
                        basic_salary=basic, allowance=allow, total_salary=basic + allow, active=True,
                        joined_on=date.fromisoformat(joined), designation='Purchase Officer', iban='AE630260001015808416101', pay_route='wps')
    db.add(e); db.flush(); return e
arun = staff('IC011', 'ARUN NATARAJAN', 1600, 2400)
aysha = staff('IC010', 'AYSHA HIBA', 2800, 4200)
neethu = staff('IC019', 'NEETHU TREESA JOSE', 2800, 4200)
jomon = staff('IC001', 'JOMON THOMAS', 2600, 3900, '2022-08-22')
db.add(models.StaffLoan(employee_id=arun.id, amount=1000, taken_on=date(2026, 9, 1), instalment=250, closed=False))
db.add(models.StaffLoan(employee_id=jomon.id, amount=3000, taken_on=date(2026, 9, 1), instalment=500, closed=False))
db.commit()
IDS = {e.emp_no: e.id for e in (arun, aysha, neethu, jomon)}
db.close()
c = TestClient(main.app); c.__enter__()
tok = lambda u: {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': u, 'password': 'p'}).json()['access_token']}
H, S, X = tok('admin'), tok('shafeeq'), tok('store')

run = c.post('/employees/payroll/runs', json={'month_year': MONTH, 'company_id': 1, 'group': 'staff'}, headers=S).json()
L = {l['emp_no']: l for l in run['lines']}
ck('the sheet: every row carries a pay status (none yet)', all(l['pay']['state'] == 'none' for l in run['lines']), [l['pay'] for l in run['lines']])
rid = run['id']
reload = lambda: {l['emp_no']: l for l in c.get(f'/employees/payroll/runs/{rid}', headers=S).json()['lines']}

# ---- office: regular (salary to date) mid-month, then the balance --------------------------------------------------
pv = c.post('/employees/pay/preview', json={'kind': 'office', 'source_id': L['IC011']['id'], 'type': 'regular'}, headers=S).json()
ck('regular = salary to date', abs(pv['amount'] - L['IC011']['to_date']) < 0.01, (pv, L['IC011']['to_date']))
r = c.post('/employees/pay/mark', json={'kind': 'office', 'source_id': L['IC011']['id'], 'type': 'regular', 'mode': 'wps', 'reference': 'WPS-OCT-1', 'paid_on': T.isoformat()}, headers=S)
ck('Mark paid works while the sheet is a draft', r.status_code == 200 and run['status'] == 'draft', r.text)
row = reload()['IC011']
full_net = L['IC011']['net_pay']
if T.day < 28:
    ck('paid to date: partial, the rest is the balance', row['pay']['state'] == 'partial' and abs(row['pay']['balance'] - (full_net - pv['amount'])) < 0.02, row['pay'])
r = c.post('/employees/pay/mark', json={'kind': 'office', 'source_id': L['IC011']['id'], 'type': 'balance', 'mode': 'bank', 'paid_on': T.isoformat()}, headers=S)
row = reload()['IC011']
ck('Pay balance: paid in full, locked', r.status_code == 200 and row['pay']['state'] == 'paid' and row['pay']['locked'] and row['pay']['balance'] == 0, (r.text, row['pay']))
ck('two payments, each with its date, type and mode', [p['type'] for p in row['pay']['payments']] in (['regular', 'balance'],) , row['pay']['payments'])
d = database.SessionLocal()
reps = d.query(models.LoanRepayment).all()
ck('loan instalment (250) taken once, when the row was paid in full', [(r_.amount, r_.source) for r_ in reps] == [(250.0, 'payment')], [(r_.amount, r_.source) for r_ in reps])
d.close()
ck('nothing more to pay: refused', c.post('/employees/pay/mark', json={'kind': 'office', 'source_id': L['IC011']['id'], 'type': 'balance'}, headers=S).status_code == 400)

# ---- office: an absence / addition entered after it was paid -> carried to next month ----------------------------
d = database.SessionLocal()
d.add(models.PayItem(employee_id=IDS['IC011'], month_year=MONTH, direction='add', category='taxi', amount=120, notes='Taxi bill'))
d.commit(); d.close()
row = reload()['IC011']
ck('the paid row keeps the figures it was paid on', abs(row['net_pay'] - full_net) < 0.01 and row['pay']['locked'], (row['net_pay'], full_net))
nxt = paystatus._next_month(MONTH)
d = database.SessionLocal()
carry = d.query(models.PayItem).filter(models.PayItem.month_year == nxt, models.PayItem.employee_id == IDS['IC011']).all()
ck('the taxi bill (120) is carried to next month\'s additions', [(i.direction, i.amount, i.category) for i in carry] == [('add', 120.0, 'carry')], [(i.direction, i.amount, i.category, i.notes) for i in carry])
ck('and the row shows it was carried', row['pay']['carry'] == 120 and row['pay']['carry_to'] == nxt, row['pay'])
d.add(models.PayItem(employee_id=IDS['IC011'], month_year=MONTH, direction='deduct', category='other_ded', amount=200, notes='Fine'))
d.commit(); d.close()
reload()
d = database.SessionLocal()
carry = d.query(models.PayItem).filter(models.PayItem.month_year == nxt, models.PayItem.employee_id == IDS['IC011']).all()
ck('a later deduction: the one carry follows (120 - 200 = deduct 80)', [(i.direction, i.amount) for i in carry] == [('deduct', 80.0)], [(i.direction, i.amount) for i in carry])
d.close()

# ---- office: early full month, custom (partial), final settlement --------------------------------------------------
c.post('/employees/pay/mark', json={'kind': 'office', 'source_id': L['IC010']['id'], 'type': 'early_full', 'mode': 'wps', 'paid_on': T.isoformat()}, headers=S)
row = reload()['IC010']
ck('early full month = the whole month\'s net, locked', row['pay']['state'] == 'paid' and abs(row['pay']['paid'] - row['net_pay']) < 0.01, row['pay'])
c.post('/employees/pay/mark', json={'kind': 'office', 'source_id': L['IC019']['id'], 'type': 'custom', 'amount': 3000, 'mode': 'cash', 'note': 'Advance on salary'}, headers=S)
row = reload()['IC019']
ck('custom 3,000: partial - amount paid, balance', row['pay']['state'] == 'partial' and row['pay']['paid'] == 3000 and abs(row['pay']['balance'] - (row['net_pay'] - 3000)) < 0.01, row['pay'])
pv = c.post('/employees/pay/preview', json={'kind': 'office', 'source_id': L['IC001']['id'], 'type': 'final', 'last_day': T.isoformat(), 'reason': 'resignation', 'notice_served': 30}, headers=S).json()
ck('final settlement worked out: gratuity, leave, salary, loan off', any('gratuity' in k[0].lower() for k in pv['lines']) and any('Loan' in k[0] for k in pv['lines']), pv.get('lines'))
r = c.post('/employees/pay/mark', json={'kind': 'office', 'source_id': L['IC001']['id'], 'type': 'final', 'last_day': T.isoformat(), 'reason': 'resignation', 'notice_served': 30, 'mode': 'bank', 'reference': 'FS-001'}, headers=S)
d = database.SessionLocal(); j = d.get(models.Employee, IDS['IC001'])
lo = d.query(models.StaffLoan).filter(models.StaffLoan.employee_id == j.id).first()
ck('final: paid, the whole loan (3,000) off, made inactive', r.status_code == 200 and not j.active and lo.closed and j.terminated_on == T, (r.text, j.active, lo.closed))
d.close()
row = reload()['IC001']
ck('final: the row shows settled', row['pay']['state'] == 'settled' and row['pay']['locked'], row['pay'])

# ---- approve & lock skips paid rows ---------------------------------------------------------------------------------
c.post(f'/employees/payroll/runs/{rid}/approve', headers=S)
d = database.SessionLocal()
reps = [(r_.amount, r_.source) for r_ in d.query(models.LoanRepayment).join(models.StaffLoan).filter(models.StaffLoan.employee_id == IDS['IC011']).all()]
ck('Approve & lock: Arun\'s instalment not taken a second time', reps == [(250.0, 'payment')], reps)
d.close()

# ---- payslips: generate (versioned), view, settlement slip, ZIP --------------------------------------------------------
row = reload()['IC011']
pid = row['pay']['payments'][-1]['id']
a = c.post(f'/employees/pay/{pid}/payslip', headers=S).json()
b = c.post(f'/employees/pay/{pid}/payslip', headers=S).json()
ck('payslip versions: v1 then v2, never written over', a['version'] == 1 and b['version'] == 2 and a['id'] != b['id'], (a, b))
dt = c.post('/auth/download-token', headers=S).json()['token']
pdf = c.get(f"/export/pay/payslip/{a['id']}?token={dt}")
ck('payslip PDF', pdf.status_code == 200 and pdf.content[:4] == b'%PDF', pdf.status_code)
open('/tmp/claude-0/payslip_office.pdf', 'wb').write(pdf.content)
fpid = reload()['IC001']['pay']['payments'][-1]['id']
fs = c.post(f'/employees/pay/{fpid}/payslip', headers=S).json()
ck('final settlement gets the settlement slip', fs.get('slip_no') and c.get(f"/export/pay/payslip/{fs['id']}?token={dt}").content[:4] == b'%PDF', fs)
d = database.SessionLocal(); ck('slip type is settlement', d.get(models.Payslip, fs['id']).slip_type == 'settlement'); d.close()
open('/tmp/claude-0/payslip_settlement.pdf', 'wb').write(c.get(f"/export/pay/payslip/{fs['id']}?token={dt}").content)
bulk = c.post('/employees/pay/bulk', json={'kind': 'office', 'action': 'payslips', 'source_ids': [l['id'] for l in run['lines']]}, headers=S).json()
ck('Generate payslips (bulk): the ones without a slip', bulk['payslips'] >= 2, bulk)
z = c.get(f"/export/pay/payslips.zip?token={dt}&kind=office&month_year={MONTH}&run_ids={rid}")
names = zipfile.ZipFile(io.BytesIO(z.content)).namelist() if z.status_code == 200 else []
ck('Download all payslips (ZIP): the latest version of each', z.status_code == 200 and len(names) >= 4 and any('v2' in n for n in names), names)
slips = c.get('/employees/pay/payslips?emp_no=IC011', headers=S).json()
ck('the Staff profile\'s Payslips tab lists every version', len(slips['payslips']) >= 2 and len(slips['payments']) == 2, slips)
ck('a store login cannot see payslips', c.get('/employees/pay/payslips?emp_no=IC011', headers=X).status_code == 403)

# ---- cancel a payment made by mistake ----------------------------------------------------------------------------------
cp = reload()['IC019']['pay']['payments'][0]['id']
ck('cancel needs a reason', c.post(f'/employees/pay/{cp}/cancel', json={}, headers=S).status_code == 400)
ck('cancelled', c.post(f'/employees/pay/{cp}/cancel', json={'reason': 'wrong person'}, headers=S).status_code == 200)

# ==== LABOUR ==========================================================================================================
cs, ce, CYC = pcyc.cycle_bounds_for(T)                    # the cycle running now
pcs, pce, PCYC = pcyc.cycle_bounds_for(cs - timedelta(days=1))   # the last one, closed
d = database.SessionLocal()
def worker(code, name):
    e = models.Employee(emp_no=code, name=name, trade='MASON', basic_salary=1000, total_salary=1500, active=True, company='Infinia',
                        joined_on=date(2023, 1, 10), pay_type='daily')
    d.add(e); d.flush(); return e
w1, w2, w3 = worker('F-101', 'RAJAN'), worker('F-102', 'MOHAN'), worker('F-103', 'SURESH')
def mark_days(e, a, b, st='Present'):
    x = a
    while x <= b:
        _, _, cy = pcyc.cycle_bounds_for(x)
        row = d.query(models.DailyRow).filter_by(emp_no=e.emp_no, full_date=x).first() or models.DailyRow(employee_id=e.id, emp_no=e.emp_no, emp_name=e.name, month_year=cy, full_date=x, day=x.day)
        row.am = row.pm = ('Sunday' if x.weekday() == 6 and st == 'Present' else st)
        d.add(row); x += timedelta(days=1)
    d.commit()
for w in (w1, w2, w3):
    mark_days(w, pcs, pce)
    mark_days(w, cs, T)
    services.recalculate_summary(d, w, PCYC); services.recalculate_summary(d, w, CYC)
W = {w.emp_no: w.id for w in (w1, w2, w3)}
d.close()
lab = c.get(f'/employees/pay/labour?month_year={PCYC}', headers=S).json()
rows = {r_['emp_no']: r_ for g in lab['groups'] for r_ in g['rows']}
ck('labour: every card of the cycle, by company, none paid', set(rows) == {'F-101', 'F-102', 'F-103'} and all(r_['pay']['state'] == 'none' for r_ in rows.values()), rows)
bulk = c.post('/employees/pay/bulk', json={'kind': 'labour', 'type': 'regular', 'mode': 'wps', 'reference': 'WPS-' + PCYC, 'source_ids': [rows['F-101']['source_id'], rows['F-102']['source_id']]}, headers=S).json()
lab = c.get(f'/employees/pay/labour?month_year={PCYC}', headers=S).json()
rows = {r_['emp_no']: r_ for g in lab['groups'] for r_ in g['rows']}
ck('Mark selected as paid: two workers paid, locked (the cycle is over)', bulk['paid'] == 2 and rows['F-101']['pay']['state'] == 'paid' and rows['F-101']['pay']['locked'] and rows['F-103']['pay']['state'] == 'none', (bulk, rows['F-101']['pay']))
# an absence marked on a paid closed cycle -> carried to this cycle's card
d = database.SessionLocal()
w1_ = d.get(models.Employee, W['F-101'])
day = pce - timedelta(days=1) if (pce - timedelta(days=1)).weekday() != 6 else pce - timedelta(days=2)
r_ = d.query(models.DailyRow).filter_by(emp_no='F-101', full_date=day).first(); r_.am = r_.pm = 'Absent'; d.commit()
services.recalculate_summary(d, w1_, PCYC)
nc = d.query(models.EmployeeSummary).filter_by(emp_no='F-101', month_year=paystatus._next_month(PCYC)).first()
adj = [(a.description[:22], a.amount, a.is_deduction) for a in (nc.adjustments if nc else [])]
ck('an absence marked after payment: carried to the next cycle as a deduction', len(adj) == 1 and adj[0][2] and adj[0][1] > 0, adj)
d.close()
# early full cycle for one worker, this cycle
rows_now = {r_['emp_no']: r_ for g in c.get(f'/employees/pay/labour?month_year={CYC}', headers=S).json()['groups'] for r_ in g['rows']}
pv = c.post('/employees/pay/preview', json={'kind': 'labour', 'source_id': rows_now['F-102']['source_id'], 'type': 'early_full'}, headers=S).json()
r = c.post('/employees/pay/mark', json={'kind': 'labour', 'source_id': rows_now['F-102']['source_id'], 'type': 'early_full', 'mode': 'wps'}, headers=S)
d = database.SessionLocal()
card = d.query(models.EmployeeSummary).filter_by(emp_no='F-102', month_year=CYC).first()
ck('early full cycle (one worker): his card becomes the whole cycle, paid, locked', r.status_code == 200 and abs(card.final_salary - pv['amount']) < 2 and
   card.final_salary > rows_now['F-102']['salary'], (pv, card.final_salary, rows_now['F-102']['salary']))
other = d.query(models.EmployeeSummary).filter_by(emp_no='F-103', month_year=CYC).first()
ck('... the others stay at salary to date', abs(other.final_salary - rows_now['F-103']['salary']) < 0.01)
d.close()
# Pay full salary now (everyone) skips the paid worker
c.post(f'/summaries/{CYC}/full-cycle', json={'on': True}, headers=H)
c.post(f'/summaries/{CYC}/full-cycle', json={'on': False}, headers=H)
d = database.SessionLocal()
card = d.query(models.EmployeeSummary).filter_by(emp_no='F-102', month_year=CYC).first()
ck('Pay full salary now / back: the paid worker\'s card is left as paid', abs(card.final_salary - pv['amount']) < 2, card.final_salary)
d.close()
# labour final settlement
r = c.post('/employees/pay/mark', json={'kind': 'labour', 'source_id': rows_now['F-103']['source_id'], 'type': 'final', 'last_day': T.isoformat(), 'reason': 'resignation', 'mode': 'cash'}, headers=S)
d = database.SessionLocal(); w3_ = d.get(models.Employee, W['F-103'])
ck('labour final settlement: paid, made inactive', r.status_code == 200 and not w3_.active, r.text)
d.close()
lp = c.get(f'/employees/pay/labour?month_year={PCYC}', headers=S).json()
p1 = next(r_ for g in lp['groups'] for r_ in g['rows'] if r_['emp_no'] == 'F-101')['pay']['payments'][0]['id']
sl = c.post(f'/employees/pay/{p1}/payslip', headers=S).json()
pdf = c.get(f"/export/pay/payslip/{sl['id']}?token={dt}")
open('/tmp/claude-0/payslip_labour.pdf', 'wb').write(pdf.content)
ck('labour payslip PDF (with attendance)', pdf.status_code == 200 and pdf.content[:4] == b'%PDF')
d = database.SessionLocal(); data = json.loads(d.get(models.Payslip, sl['id']).data); d.close()
ck('... days present and overtime on it', any(k == 'Days present' for k, _ in data['attendance']), data.get('attendance'))
lab_only = c.post('/auth/login', data={'username': 'store', 'password': 'p'})
ck('labour pay needs Labour payroll', c.get(f'/employees/pay/labour?month_year={PCYC}', headers=X).status_code == 403)
print(f"{len(FAIL)} FAILED" if FAIL else 'ALL PASS')

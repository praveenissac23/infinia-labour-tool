"""Payable amounts to the nearest whole dirham, from the November 2026 cycle (owner, 28/11/2026).

Accounts: "The payroll amounts are currently displaying decimal values ... round all final payable salary amounts to
the nearest whole AED: below 50 fils down, 50 fils and above up (Excel =ROUND(x,0)) ... the actual final payable
amounts are rounded in the calculations, not hidden by formatting. All payroll summaries and totals must reflect the
rounded payable amounts." Before (31/10 - 27/11) November was cut down to the fils. The owner chose: nearest dirham,
labour and office alike. The lines keep their fils; the difference is a "Round off" line so every slip adds up.
October 2026 and earlier are never rewritten.

Run: python3 tests/run_all.py payroll_round_dirham
"""
import sys, io
sys.path.insert(0, '.')
from datetime import date, timedelta
from fractions import Fraction as F
from decimal import Decimal
from types import SimpleNamespace as NS
from fastapi.testclient import TestClient
import database, models, auth
models.Base.metadata.create_all(database.engine)
import main, payroll_cycle as pcyc, data_engine, services

FAIL = []


def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{str(x)[:400]}]'))
    if not ok:
        FAIL.append(l)


# ---- 1. the rule itself, with the examples from accounts
for got, want in (('2500.49', 2500), ('2500.50', 2501), ('2500.75', 2501), ('2500.00', 2500), ('0.49', 0), ('0.5', 1),
                  ('-175.49', -175), ('-175.50', -176), ('-0.49', 0)):
    ck(f'{got} -> {want}', pcyc.dirham(Decimal(got)) == want and pcyc.dirham(float(got)) == want and pcyc.dirham(F(got)) == want,
       (pcyc.dirham(Decimal(got)), pcyc.dirham(float(got)), pcyc.dirham(F(got))))
ck('an exact third is not pushed over by float noise (1,911.666... + 400.8333... = 2,312.50 -> 2,313)',
   pcyc.dirham(F(1850) * 31 / 30 + F(1850) / 30 / 8 * 52) == 2313)
ck('never -0.0', str(pcyc.dirham(-0.2)) == '0.0')
ck('which cycles: November 2026 on, not October', pcyc.exact_fils('November 2026') and pcyc.exact_fils('December 2026') and not pcyc.exact_fils('October 2026'))

# ---- 2. a labour card: the live case F-707 (1,850 a month, 27 days, 52 OT hours) and F-741
def card(total, present, ot, month_exact, absent=0):
    rows = []
    d0 = date(2026, 10, 26)
    for k in range(present):
        rows.append(NS(full_date=d0 + timedelta(days=k), am='Present', pm='Present', ot=(ot if k == 0 else 0), bh=0))
    for k in range(absent):
        rows.append(NS(full_date=d0 + timedelta(days=present + k), am='Absent', pm='Absent', ot=0, bh=0))
    try:
        return data_engine.recalculate_from_daily_rows(rows, total, exact_fils=month_exact)
    except Exception as e:
        return {'error': str(e)}


r = card(1850, 31, 52, True)
ck('labour card, November 2026: 1,911.67 + OT 400.83 = 2,312.50 is paid as 2,313', r.get('final_salary') == 2313.0, r)
r = card(1850, 31, 52, False)
ck('...the same card under the October rule is also a whole dirham (2,313)', r.get('final_salary') == 2313.0, r)
r = card(1450, 31, 54, True)
ck('F-741-like: 1,498.33 + 326.25 = 1,824.58 -> 1,825', r.get('final_salary') == 1825.0, r)
r = card(1100, 1, 1, True)
ck('F-806-like (one day): 36.67 + 4.58 = 41.25 -> 41', r.get('final_salary') == 41.0, r)

# additions with fils on a card: what is paid is rounded once more
sm = NS(final_salary=2313.0, month_year='November 2026', adjustments=[NS(amount=12.34, is_deduction=True), NS(amount=0.10, is_deduction=False)])
ck('additions / deductions with fils: 2,313 - 12.34 + 0.10 = 2,300.76 is paid as 2,301', services.adjusted_final_salary(sm) == 2301.0, services.adjusted_final_salary(sm))
sm_old = NS(final_salary=2313.0, month_year='October 2026', adjustments=[NS(amount=12.34, is_deduction=True)])
ck('...October 2026 and earlier keep what they paid (2,300.66, not rounded again)', services.adjusted_final_salary(sm_old) == 2300.66)

# ---- 3. office staff: net pay
def line(**k):
    base = dict(fixed_salary=0, deduction=0, statutory=0, loan_deduction=0, other_allowance=0, leave_salary=0, air_ticket=0, net_pay=0)
    base.update(k)
    return NS(**base)


l1 = line(fixed_salary=6500, deduction=216.67)
l1.net_pay = main._line_net(l1, 'November 2026')
ck('office, November 2026: 6,500 - 216.67 = 6,283.33 -> net 6,283', l1.net_pay == 6283.0, l1.net_pay)
ck('...its round off is -0.33', main._line_round_off(l1, 'November 2026') == -0.33, main._line_round_off(l1, 'November 2026'))
l2 = line(fixed_salary=5000, other_allowance=429.5)
l2.net_pay = main._line_net(l2, 'November 2026')
ck('office: 5,000 + 429.50 = 5,429.50 -> 5,430 (round off +0.50)', l2.net_pay == 5430.0 and main._line_round_off(l2, 'November 2026') == 0.5, l2.net_pay)
l3 = line(fixed_salary=10000, deduction=4833.34)
l3.net_pay = main._line_net(l3, 'November 2026')
ck('office: 10,000 - 4,833.34 = 5,166.66 -> 5,167', l3.net_pay == 5167.0)
l4 = line(fixed_salary=8000, deduction=266.67)
l4.net_pay = main._line_net(l4, 'October 2026')
ck('office, October 2026: unchanged (7,733.33, no round off)', l4.net_pay == 7733.33 and main._line_round_off(l4, 'October 2026') == 0.0, l4.net_pay)

# ---- 4. through the app: an office month and its payslip, statement and settlement
db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Administrator', role='admin')); db.commit()
c = TestClient(main.app, raise_server_exceptions=False)
H = {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': 'admin', 'password': 'p'}).json()['access_token']}
IC = c.post('/employees/companies', json={'name': 'INFINIA CONTRACTING L.L.C.', 'short_name': 'Infinia', 'code_prefix': 'IC', 'trn': '100602393900003'}, headers=H).json()
for no, name, basic, allow in (('IC025', 'PREENU ANNIE DANIEL', 2000, 3000), ('IC001', 'JOMON THOMAS', 2600, 3900), ('IC024', 'FEBIYANS LUCAS', 4000, 6000)):
    c.post('/employees', json={'emp_no': no, 'name': name, 'trade': 'QS', 'company': 'Infinia', 'total_salary': basic + allow, 'basic_salary': basic}, headers=H)
    r = c.put(f'/employees/staff/{no}', json={'company_id': IC['id'], 'joined_on': '2025-03-14', 'designation': 'QS', 'basic': basic, 'allowance': allow,
                                              'contract_basic': basic, 'pay_route': 'wps'}, headers=H)
    assert r.status_code == 200, r.text[:200]
c.post('/employees/pay-items', json={'emp_no': 'IC025', 'month_year': 'November 2026', 'direction': 'add', 'category': 'taxi', 'amount': 429.5, 'notes': 'Taxi Bills'}, headers=H)
c.post('/employees/pay-items', json={'emp_no': 'IC001', 'month_year': 'November 2026', 'direction': 'deduct', 'category': 'other_ded', 'amount': 216.67, 'notes': 'Fine'}, headers=H)
run = c.post('/employees/payroll/runs', json={'month_year': 'November 2026', 'company_id': IC['id'], 'group': 'staff'}, headers=H)
ck('the November office month opens', run.status_code == 200, run.text[:300])
run = run.json()
L = {l['emp_no']: l for l in run['lines']}
ck('net pay on the sheet is a whole dirham: 5,430 / 6,283 / 10,000', (L['IC025']['net_pay'], L['IC001']['net_pay'], L['IC024']['net_pay']) == (5430.0, 6283.0, 10000.0),
   {k: (v['net_pay'], v['round_off']) for k, v in L.items()})
ck('...with the round off on each line (+0.50 / -0.33 / 0)', (L['IC025']['round_off'], L['IC001']['round_off'], L['IC024']['round_off']) == (0.5, -0.33, 0.0))
ck('...and the sheet total is the rounded nets added up (21,713)', run.get('totals', {}).get('net_pay', sum(l['net_pay'] for l in run['lines'])) == 21713.0,
   run.get('totals'))
import paystatus
s2 = database.SessionLocal()
rr = s2.get(models.PayrollRun, run['id']); ln = next(x for x in rr.lines if x.employee_id == L['IC001']['employee_id']); e = s2.get(models.Employee, ln.employee_id)
fg = paystatus.office_figures(s2, rr, ln, e)
tot = round(sum(v for _, v in fg['earnings']) - sum(v for _, v in fg['deductions']), 2)
ck('the payslip shows a Round off line and adds up to its net exactly (6,283)', fg['net'] == 6283.0 and tot == 6283.0
   and ('Round off', 0.33) in fg['deductions'], (fg['earnings'], fg['deductions'], fg['net']))
s2.close()
rows = main._statement_rows(run['lines'])
r1 = next(x for x in rows if x['Emp. Code'] == 'IC001')
ck('the salary statement has a Round Off column beside Net Pay (-0.33, net 6,283)', r1.get('Round Off') == -0.33 and r1.get('Net Pay') == 6283.0
   and list(r1).index('Round Off') == list(r1).index('Net Pay') - 1, r1)
ck('...and it is a money column (totalled like the others)', 'Round Off' in main.STATEMENT_MONEY)
rows_oct = main._statement_rows([dict(l, round_off=0.0) for l in run['lines']])
ck('...a month with no round off shows no such column', all('Round Off' not in x for x in rows_oct))

# a final settlement: the payable is a whole dirham, with its Round off line
st = c.get('/employees/staff/IC001/settlement', params={'last_day': '2026-11-20', 'reason': 'resigned'}, headers=H)
ck('an office final settlement opens', st.status_code == 200, st.text[:300])
d = st.json()
ck('...its payable is a whole dirham', d['net'] == int(d['net']), d['net'])
ck('...and the paper adds up: gross payable - total deductions = net (Round off as its own line when needed)',
   abs(d['net'] - (d['total_pay'] - d['total_ded'])) < 0.005
   and (any(x['label'] == 'Round off' for x in d['payables'] + d['deductions']) or abs(d['total_pay'] - d['total_ded'] - round(d['total_pay'] - d['total_ded'])) < 0.005),
   (d['net'], d['total_pay'], d['total_ded'], d['payables'], d['deductions']))
# a settlement whose last day is before November 2026 keeps the rule it was worked out under (no Round off line)
so = c.get('/employees/staff/IC001/settlement', params={'last_day': '2026-10-20', 'reason': 'resigned'}, headers=H).json()
ck('a settlement with its last day in October 2026 is not rounded to the dirham, and has no Round off line',
   not any(x['label'] == 'Round off' for x in so['payables'] + so['deductions']) and abs(so['net'] - (so['total_pay'] - so['total_ded'])) < 0.005,
   (so['net'], so['total_pay'], so['total_ded']))
# the early full-cycle preview uses the rule that is paid
import paystatus as _ps
src = open('paystatus.py', encoding='utf-8').read()
ck('the early full-cycle preview is worked out by the same rule as what is paid', 'return M.pcyc.dirham(_r2(t)) if M.pcyc.exact_fils(month) else _r2(t)' in src)
ck('a line paid to the fils before this rule is not a change after payment (no carry of a few fils)',
   'was = M._line_net(l, r.month_year) if M._om.exact_month(r.month_year) else (l.net_pay or 0)' in src)
page = open('../app.html', encoding='utf-8').read()
ck('the office sheet on screen rounds the net the same way while typing', 'hrWholeDirham' in page)
print("\nALL PASS" if not FAIL else f"\n{len(FAIL)} FAILED")
sys.exit(1 if FAIL else 0)

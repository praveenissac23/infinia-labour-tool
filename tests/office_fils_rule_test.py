"""Owner's rule (31/10/2026): office pay never gives a fraction of a fils extra - from the November 2026 month.

Run (on a COPY of a database holding office staff, e.g. /tmp/claude-0/full.db):
    cd app && DATABASE_URL=sqlite:////tmp/copy.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/office_fils_rule_test.py

  * November 2026 on: a day off is gross x days / 30 exactly, rounded UP to the fils (13,000 a month: one day
    433.34, not 433.00); salary to date is exact, rounded DOWN; the October sheet keeps whole-dirham days (433.00);
  * gratuity, leave encashment, last days' salary: exact, DOWN to the fils; notice not served: UP to the fils;
  * the final settlement's net is exact to the fils (no whole dirham), and adds up.
"""
import os, sys
from datetime import date
from decimal import Decimal as D, ROUND_FLOOR, ROUND_CEILING
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import main
main._dubai_today = lambda: date(2026, 11, 16)          # the middle of November 2026
c = TestClient(main.app); c.__enter__()
tok = None
for pw in (os.environ.get('ADMIN_PW'), 'changeme123', 'p'):
    tok = pw and c.post('/auth/login', data={'username': 'admin', 'password': pw}).json().get('access_token')
    if tok:
        break
H = {'Authorization': 'Bearer ' + tok}
FAIL = []
def ck(m, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + m + ('' if ok else f'  [{x}]'))
    if not ok: FAIL.append(m)
dn = lambda v: float(D(v).quantize(D('0.01'), rounding=ROUND_FLOOR))
up = lambda v: float(D(v).quantize(D('0.01'), rounding=ROUND_CEILING))

staff = [s for s in c.get('/employees/staff', headers=H).json().get('rows', []) if s.get('active', True)
         and s.get('pay_group', 'staff') == 'staff' and s.get('joined_on') and s['joined_on'] < '2026-10-01']
# someone whose gross / 30 is not a whole number of fils, so the old and new rules differ
# ... and with nothing off in November yet (so the one day added below is the only one)
def _nov(s):
    run = c.post('/employees/payroll/runs', json={'month_year': 'November 2026', 'company_id': s['company_id'], 'group': 'staff'}, headers=H).json()
    return next((l for l in run.get('lines', []) if l['emp_no'] == s['emp_no']), None)
who = next(s for s in staff if (D(str(s['gross'])) / 30) != (D(str(s['gross'])) / 30).quantize(D('0.01'))
           and (_nov(s) or {}).get('deduction') == 0)
code, gross, co = who['emp_no'], who['gross'], who['company_id']
print(f"   {code}: gross {gross:,.2f}, a day {D(str(gross)) / 30}")
for month, day in (('November 2026', '2026-11-03'), ('October 2026', '2026-10-06')):
    r = c.post('/employees/leave', json={'emp_no': code, 'kind': 'absent', 'from': day}, headers=H)
    if r.status_code != 200:
        print('   leave refused:', month, r.text[:150])
def line(month):
    run = c.post('/employees/payroll/runs', json={'month_year': month, 'company_id': co, 'group': 'staff'}, headers=H).json()
    return run, next(l for l in run['lines'] if l['emp_no'] == code)
run, l = line('November 2026')
ck(f"November: one day absent costs gross x 1 / 30 up to the fils = {up(D(str(gross)) / 30):,.2f}",
   l['deduction'] == up(D(str(gross)) / 30), l['deduction'])
ck("November: net = gross - absence (+/- items, loan), to the fils",
   abs(l['net_pay'] - round(l['fixed_salary'] - l['deduction'] - l['statutory'] - l['loan_deduction'] + l['other_allowance']
                            + l['leave_salary'] + l['air_ticket'], 2)) < 0.001, l)
want = dn(D(str(l['fixed_salary'])) * 16 / 30)
ck(f"November 16th: salary earned so far = gross x 16 / 30 down to the fils = {want:,.2f}", l['earned_to_date'] == want, l['earned_to_date'])
ck("the running TOTAL is the rows' salary to date added up",
   abs(run['progress']['to_date'] - round(sum(x['to_date'] for x in run['lines'] if not x['held']), 2)) < 0.001)
_, lo = line('October 2026')
if lo['deduction']:
    ck(f"October keeps the old rule: the day is gross / 30 dropped to whole dirhams ({int(gross / 30):,.2f} a day)",
       float(lo['deduction']) == float(int(gross / 30)) * round(lo['deduction'] / int(gross / 30)), lo['deduction'])

# Gratuity and final settlement (not yet paid): exact, to the fils, never up.
for s in staff[:12]:
    st = c.get(f"/employees/staff/{s['emp_no']}/settlement",
               params={'last_day': '2026-11-16', 'reason': 'resignation', 'notice_served': '7'}, headers=H).json()
    if 'payables' not in st:
        continue
    basic = st['salary']['basic']; g = st['gratuity']
    amt = {x['label']: x['amount'] for x in st['payables'] + st['deductions']}
    two = all(abs(v * 100 - round(v * 100)) < 1e-6 for v in amt.values()) and abs(st['net'] * 100 - round(st['net'] * 100)) < 1e-6
    ck(f"{s['emp_no']}: every settlement figure is to the fils", two, amt)
    ck(f"{s['emp_no']}: net {st['net']:,.2f} = payables - deductions exactly",
       abs(st['net'] - round(st['total_pay'] - st['total_ded'], 2)) < 0.001, (st['net'], st['total_pay'], st['total_ded']))
    ck(f"{s['emp_no']}: leave encashment exact, down to the fils",
       amt['Leave encashment'] == dn(D(str(st['input']['leave_days'])) * D(str(basic)) * 12 / 365), amt['Leave encashment'])
    ck(f"{s['emp_no']}: 16 days' salary = gross x 16 / 30 down to the fils",
       st['input']['salary_amount'] == dn(D(str(st['salary']['gross'])) * D(str(st['input']['salary_days'])) / st['input']['month_days']))
    if g['amount'] and not g['capped']:
        y = D(str(st['service']['counted'])) / 365
        ck(f"{s['emp_no']}: gratuity exact, down to the fils (= the Gratuity screen), and its two lines add up to it",
           g['amount'] == dn((min(y, D(5)) * 21 + max(y - 5, D(0)) * 30) * D(str(basic)) * 12 / 365)
           and abs(g['first5_amt'] + g['after5_amt'] - g['amount']) < 0.001, (g['amount'], g['first5_amt'], g['after5_amt']))
    nd = next((v for k, v in amt.items() if k.startswith('Notice not served')), None)
    if nd is not None:
        short = st['input']['notice_required'] - st['input']['notice_served']
        ck(f"{s['emp_no']}: notice not served ({short:g} days) taken up to the fils",
           nd == up(D(str(st['salary']['gross'])) * D(str(short)) / 30), nd)
print(f"\n{len(FAIL)} FAILED" if FAIL else "\nOFFICE PAY IS TO THE FILS, NEVER A FILS EXTRA")
sys.exit(1 if FAIL else 0)

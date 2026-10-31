"""Snapshot of every office figure up to October 2026 (and labour gratuity / settlement), for the before / after proof
of the to-the-fils rule (app/office_money.py): run once on the code before the change and once after, on fresh
copies of the same database, and compare the two files - October 2026 and earlier must be byte-identical.

Run: cd app && DATABASE_URL=sqlite:////tmp/copy.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 \
        SNAP_TODAY=2026-10-31 python3 ../tests/office_fils_snapshot.py OUT.json
"""
import hashlib, json, os, re, sqlite3, sys
from datetime import date
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import main
if os.environ.get('SNAP_TODAY'):
    main._dubai_today = lambda: date.fromisoformat(os.environ['SNAP_TODAY'])
c = TestClient(main.app); c.__enter__()
tok = None
for pw in (os.environ.get('ADMIN_PW'), 'changeme123', 'p'):
    tok = pw and c.post('/auth/login', data={'username': 'admin', 'password': pw}).json().get('access_token')
    if tok:
        break
H = {'Authorization': 'Bearer ' + tok}
dl = lambda: c.post('/auth/download-token', headers=H).json()['token']
raw = sqlite3.connect(os.environ['DATABASE_URL'].split('sqlite:///', 1)[1]); raw.row_factory = sqlite3.Row
out = {}
NUM = ('basic', 'allowance', 'fixed_salary', 'deduction', 'statutory', 'other_allowance', 'loan_deduction',
       'leave_salary', 'air_ticket', 'pension', 'net_pay', 'earned_to_date', 'to_date', 'deduction_note', 'remarks')
for r in raw.execute("select * from payroll_runs order by id").fetchall():
    if main._staff_month_bounds(r['month_year'])[0] >= date(2026, 11, 1):
        continue
    api = c.get(f"/employees/payroll/runs/{r['id']}", headers=H).json()
    out[f"run {r['id']} {r['month_year']} {r['group']}"] = {
        'lines': [{k: l.get(k) for k in ('emp_no',) + NUM} for l in api['lines']],
        'totals': api['totals'], 'by_route': api['by_route'], 'progress_to_date': api['progress']['to_date']}
    v = c.get('/export/payroll/statement/view', params=dict(run_id=r['id'], token=dl())).text
    v = re.sub(r'(token=)[^"&\']+', r'\1X', v)
    out[f"run {r['id']} preview"] = hashlib.sha256(v.encode()).hexdigest()
    out[f"run {r['id']} stored"] = [dict(x) for x in raw.execute(
        "select id, employee_id, basic, allowance, fixed_salary, deduction, statutory, other_allowance, loan_deduction,"
        " leave_salary, air_ticket, pension, net_pay from payroll_lines where run_id=? order by id", (r['id'],))]
for month in sorted({r['month_year'] for r in raw.execute("select month_year from payroll_runs")}):
    if main._staff_month_bounds(month)[0] >= date(2026, 11, 1):
        continue
    for g in ('staff', 'local'):
        v = c.get('/export/payroll/consolidated/view', params=dict(month_year=month, group=g, token=dl())).text
        v = re.sub(r'(token=)[^"&\']+', r'\1X', v)
        out[f"consolidated {month} {g}"] = hashlib.sha256(v.encode()).hexdigest()
out['payslips'] = [dict(x) for x in raw.execute("select id, data from payslips order by id")] if raw.execute(
    "select 1 from sqlite_master where name='payslips'").fetchone() else []
out['payments'] = [dict(x) for x in raw.execute("select id, amount, due, figures from pay_payments order by id")] if raw.execute(
    "select 1 from sqlite_master where name='pay_payments'").fetchone() else []
# Labour: gratuity and final settlement are not the office's to change.
for e in raw.execute("select emp_no from employees where staff=0 and active=1 order by emp_no limit 40"):
    s = c.get(f"/employees/labour/{e['emp_no']}/settlement", params={'last_day': '2026-10-31'}, headers=H)
    out[f"labour settlement {e['emp_no']}"] = s.json() if s.status_code == 200 else s.status_code
json.dump(out, open(sys.argv[1], 'w'), indent=1, sort_keys=True, default=str)
print(len(out), 'figures saved to', sys.argv[1])

"""Office pay, worked out again by hand and held against everything the app shows and prints.

Run (on a COPY of a database that holds office staff - never the live one):
    cd app && DATABASE_URL=sqlite:////tmp/copy.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/office_pay_arith_audit_test.py

Nothing here calls the app's payroll arithmetic. The registers are read with plain SQL and every figure is
worked out from the rules as agreed (calendar month for office / local staff):

  * a day = gross / 30 dropped to whole dirhams, half a day half of that;
  * one sick day a month is paid (the first by date); further sick days, absent, vacation and unpaid leave are
    deducted; holiday and paid leave are not; a pay rule typed on the day (paid / unpaid) overrides;
  * a whole month away costs the month's salary, never more;
  * days before joining / after leaving come off at the same day rate;
  * salary = the one in force on the last day of the month;
  * add / ded = the month's additions less its deductions;
  * loan = min(instalment, balance) for each open loan taken by the month end, unless typed on the sheet;
  * net = gross - absence - deductions - loan + additions (pension printed, never added);
  * to date (month still running) = gross x days gone / days in month - absence + add/ded (loan at month end);
  * held rows are on no total; a row paid in full keeps the figures it was paid on.

Checked for every cycle on file, on two dates (the real today and the middle of the newest month, so the
"salary to date" figures are exercised): the sheet (API), its totals and route totals; the salary statement
Preview, Excel and PDF for everybody and for a ticked subset (rows, the TOTAL line = the rows added up, the
route figures, "(Already paid)"); the all-companies statements; Pay full month now for a ticked subset;
gratuity for every member of staff; and the final settlement sheet's own sums.
"""
import io
import math
import os
import re
import sqlite3
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import main
import models
import auth
from database import SessionLocal

FAIL = []
NCHK = [0]


def ck(label, ok, ctx=None):
    NCHK[0] += 1
    if not ok:
        print("FAIL " + label + f"   [{ctx}]")
        FAIL.append(label)
    elif os.environ.get("VERBOSE"):
        print("PASS " + label)


def same(a, b, tol=0.005):
    return abs(round(float(a or 0), 2) - round(float(b or 0), 2)) < tol


DB = os.environ['DATABASE_URL'].split('sqlite:///', 1)[1]
raw = sqlite3.connect(DB)
raw.row_factory = sqlite3.Row


def q(sql, *args):
    return [dict(r) for r in raw.execute(sql, args).fetchall()]


def d(s):
    return datetime.strptime(str(s)[:10], '%Y-%m-%d').date() if s else None


def bounds(month_year):
    a = datetime.strptime('1 ' + month_year, '%d %B %Y').date()
    return a, date(a.year + (a.month == 12), a.month % 12 + 1, 1) - timedelta(days=1)


def day_rate(gross):
    return float(int(gross / 30.0))


def judged(emp_id, a, b):
    """[(row, unpaid portion)] for one calendar month, by the house rules."""
    out, sick_left = [], 1.0
    for r in q("select * from staff_leave where employee_id=? and on_date>=? and on_date<=? order by on_date, id",
               emp_id, a.isoformat(), b.isoformat()):
        kind = r['kind'] or ('sick' if 'sick' in (r['reason'] or '').lower() else ('paid_leave' if r['paid'] else 'absent'))
        por, rule = r['portion'] or 1.0, r['pay_rule'] or 'auto'
        if rule == 'paid':
            paid = por
        elif rule == 'unpaid':
            paid = 0.0
        elif kind == 'sick':
            paid = min(por, max(sick_left, 0.0))
            sick_left -= paid
        elif kind in ('holiday', 'paid_leave'):
            paid = por
        else:
            paid = 0.0
        out.append((dict(r, kind=kind), por - paid))
    return out


def absence(emp_id, a, b, gross):
    unpaid = sum(u for _, u in judged(emp_id, a, b))
    if not unpaid:
        return 0.0
    if unpaid >= (b - a).days + 1:
        return gross
    return round(min(day_rate(gross) * unpaid, gross), 2)


def part_month(e, a, b, gross):
    j, t, n = d(e['joined_on']), d(e['terminated_on']), 0
    if j and a < j <= b:
        n += (j - a).days
    if t and a <= t < b:
        n += (b - t).days
    return round(min(day_rate(gross) * n, gross), 2) if n else 0.0


def salary_on(e, day):
    ch = q("select basic, allowance from salary_changes where employee_id=? and effective_on<=? "
           "order by effective_on desc, id desc limit 1", e['id'], day.isoformat())
    if ch:
        return round(ch[0]['basic'] or 0, 2), round(ch[0]['allowance'] or 0, 2)
    return round(e['basic_salary'] or 0, 2), round(e['allowance'] or 0, 2)


def items(emp_id, month_year):
    rows = q("select direction, amount from pay_items where employee_id=? and month_year=?", emp_id, month_year)
    return (round(sum(r['amount'] for r in rows if r['direction'] == 'add'), 2),
            round(sum(r['amount'] for r in rows if r['direction'] == 'deduct'), 2))


def loan_due(emp_id, month_end):
    due = 0.0
    for l in q("select * from staff_loans where employee_id=? and closed=0 and taken_on<=?", emp_id, month_end.isoformat()):
        left = (l['amount'] or 0) - sum(r['amount'] for r in q("select amount from loan_repayments where loan_id=?", l['id']))
        if left > 0.005:
            due += min(l['instalment'] or 0, left)
    return round(due, 2)


def frozen_line_ids(run_id):
    """Lines paid in full (not void) - kept on the figures they were paid on."""
    by = {}
    for p in q("select * from pay_payments where kind='office' and run_id=? and void=0 order by id", run_id):
        by.setdefault(p['source_id'], []).append(p)
    return {lid for lid, ps in by.items()
            if any(p['pay_type'] == 'final' for p in ps) or sum(p['amount'] for p in ps) >= (ps[-1]['due'] or 0) - 0.01}


c = TestClient(main.app)
c.__enter__()          # run the start-up (column migrations) the way the server does
with SessionLocal() as _db:
    adm = _db.query(models.User).filter(models.User.username == 'admin').first()
    if adm is None:
        adm = models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Admin', role='admin')
        _db.add(adm)
    else:
        adm.hashed_password = auth.hash_password('p')
    _db.commit()
H = {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': 'admin', 'password': 'p'}).json()['access_token']}


def tok():
    return c.post('/auth/download-token', headers=H).json()['token']


def xlsx_rows(content):
    import openpyxl
    ws = openpyxl.load_workbook(io.BytesIO(content), data_only=True).active
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    hi = next(i for i, r in enumerate(rows) if r and 'Emp. Code' in [str(v) for v in r])
    head = [str(v) if v is not None else '' for v in rows[hi]]
    body, total, sub = [], None, ' '.join(str(v) for r in rows[:hi] for v in r if v)
    for r in rows[hi + 1:]:
        if not r or all(v in (None, '') for v in r):
            continue
        if any(isinstance(v, str) and v.strip().upper() == 'TOTAL' for v in r):
            total = dict(zip(head, r))
        else:
            body.append(dict(zip(head, r)))
    return head, body, total, sub


def pdf_text(content):
    import pdfplumber
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


def money(v):
    return f"{v:,.2f}"


ROUTE_NAME = {'wps': 'WPS TOTAL', 'bank': 'BANK TRANSFER', 'cash': 'CASH SALARY TOTAL'}


def full_month_ids(month_year, group):
    v = (q("select value from settings where key=?", f"hr_full_month:{month_year}:{group}") or [{'value': ''}])[0]['value'] or ''
    if not v:
        return False, None
    if '|' in v:
        return True, {int(x) for x in v.split('|', 1)[1].split(',') if x.strip().isdigit()}
    return True, None


def audit_run(r, today, label_extra=""):
    """Every line of one company's sheet, and the papers printed from it."""
    api = c.get(f"/employees/payroll/runs/{r['id']}", headers=H).json()
    a, b = bounds(r['month_year'])
    label = f"[{today:%d/%m/%Y}] {r['short_name']} {r['month_year']} ({r['group']}){label_extra}"
    days = (b - a).days + 1
    done = 0 if today < a else days if today > b else (today - a).days + 1
    fm_on, fm_ids = full_month_ids(r['month_year'], r['group'] or 'staff')
    whole = r['status'] == 'approved' or (fm_on and fm_ids is None)
    lines = api['lines']
    running = 0 < done < days and not (whole or (lines and all(l['full_month'] for l in lines)))
    ck(f"{label}: running flag", bool((api.get('progress') or {}).get('running')) == running, api.get('progress'))
    frozen = frozen_line_ids(r['id'])
    stored = {x['id']: x for x in q("select * from payroll_lines where run_id=?", r['id'])}
    mine = {}
    for l in lines:
        e = q("select * from employees where id=?", l['employee_id'])[0]
        st = stored[l['id']]
        if r['status'] == 'approved' or l['id'] in frozen:
            # Kept on the figures it was approved / paid on: check its own sum.
            gross, absent, add, ded, loan = st['fixed_salary'], st['deduction'], \
                (st['other_allowance'] or 0) + (st['leave_salary'] or 0) + (st['air_ticket'] or 0), st['statutory'], st['loan_deduction']
        else:
            basic, allow = salary_on(e, b)
            gross = round(basic + allow, 2)
            absent = round(min(absence(e['id'], a, b, gross) + part_month(e, a, b, gross), gross), 2)
            add, ded = items(e['id'], r['month_year'])
            loan = st['loan_deduction'] if st['loan_edited'] else loan_due(e['id'], b)
        net = round(gross - absent - ded - loan + add, 2)
        full = r['status'] == 'approved' or (fm_on and (fm_ids is None or e['id'] in fm_ids))
        locked = bool((l.get('pay') or {}).get('locked'))
        # Salary to date: the month's net once the month is over, the row is on the whole month (Pay full month
        # now / approved) or it is already paid in full; otherwise earned so far (no loan - that is at month end).
        to_date = net if (full or locked or done >= days) else round(round(gross * done / days, 2) - absent + add - ded, 2)
        m = dict(gross=gross, absent=absent, adjust=round(add - ded, 2), loan=loan, net=net, to_date=to_date,
                 held=bool(l['held']), route=l['pay_route'], emp_id=e['id'], code=e['emp_no'],
                 paid_full=bool((l.get('pay') or {}).get('locked')))
        mine[l['id']] = m
        ok = (same(l['fixed_salary'], gross) and same(l['deduction'], absent) and same(l['adjust'], m['adjust'])
              and same(l['loan_deduction'], loan) and same(l['net_pay'], net) and same(l['to_date'], to_date))
        ck(f"{label}: {e['emp_no']} {e['name']}", ok,
           f"mine={m} app=gross {l['fixed_salary']} absent {l['deduction']} adjust {l['adjust']} loan {l['loan_deduction']} "
           f"net {l['net_pay']} to_date {l['to_date']}")
        # the sheet's own sum: net = gross - absence + add/ded - loan, to the fils
        ck(f"{label}: {e['emp_no']} row adds up",
           same(l['net_pay'], l['fixed_salary'] - l['deduction'] + l['adjust'] - l['loan_deduction']), l)
        # payable column = gross + other additions - absence - deductions (leave salary / ticket after it)
        ck(f"{label}: {e['emp_no']} payable", same(l['payable'], l['fixed_salary'] + l['other_allowance'] - l['deduction'] - l['statutory']), l)
    paid = [m for m in mine.values() if not m['held']]
    T = api['totals']
    for k, f in (('fixed_salary', 'gross'), ('net_pay', 'net'), ('loan_deduction', 'loan')):
        ck(f"{label}: total {k}", same(T[k], sum(m[f] for m in paid)), (T[k], sum(m[f] for m in paid)))
    ck(f"{label}: total absence + deductions",
       same(T['deduction'], sum(l['deduction'] + l['statutory'] for l in lines if not l['held'])), T)
    routes = {}
    for m in paid:
        routes[m['route']] = round(routes.get(m['route'], 0) + m['net'], 2)
    ck(f"{label}: route totals {routes}", set(routes) == set(api['by_route']) and all(same(api['by_route'][k], v) for k, v in routes.items()),
       api['by_route'])
    ck(f"{label}: progress to-date total", same(api['progress']['to_date'], sum(m['to_date'] for m in paid)), api['progress'])

    # ---- the printed statement: everybody not held, then every other one of them ------------------------
    picks = [[m['emp_id'] for m in paid]]
    if len(paid) > 1:
        picks.append([m['emp_id'] for m in paid][::2])
    last_col = 'Salary To Date' if running else 'Net Pay'
    for pick in picks:
        if not pick:
            continue
        want = [m for m in mine.values() if not m['held'] and m['emp_id'] in pick]
        emps = ",".join(map(str, pick))
        tag = f"{label}: statement ({len(want)} ticked)"
        x = c.get('/export/payroll/statement', params=dict(run_id=r['id'], token=tok(), format='excel', emps=emps))
        ck(f"{tag} Excel downloads", x.status_code == 200, x.status_code)
        if x.status_code != 200:
            continue
        head, body, total, sub = xlsx_rows(x.content)
        ck(f"{tag} Excel last money column is {last_col}", last_col in head, head)
        by_code = {str(rw['Emp. Code']): rw for rw in body}
        ck(f"{tag} Excel prints exactly the ticked rows", sorted(by_code) == sorted(m['code'] for m in want),
           (sorted(by_code), sorted(m['code'] for m in want)))
        for m in want:
            rw = by_code.get(m['code'])
            if not rw:
                continue
            ok = (same(rw['Gross Salary'], m['gross']) and same(rw['Add / Ded.'], m['adjust']) and same(rw['Absent Ded.'], m['absent'])
                  and same(rw['Loan'], m['loan']) and same(rw[last_col], m['to_date'] if running else m['net']))
            ck(f"{tag} Excel row {m['code']}", ok, (rw, m))
            ck(f"{tag} Excel {m['code']} '(Already paid)' only when paid in full",
               ('(Already paid)' in str(rw['Employee Name'])) == m['paid_full'], rw['Employee Name'])
        for col in ('Gross Salary', 'Add / Ded.', 'Absent Ded.', 'Loan', last_col):
            ck(f"{tag} Excel TOTAL {col} = rows added up",
               total is not None and same(total.get(col), sum(float(rw[col] or 0) for rw in body)), (total, col))
        ck(f"{tag} Excel TOTAL {last_col} = hand figure",
           total is not None and same(total.get(last_col), sum(m['to_date'] if running else m['net'] for m in want)), total)
        rts = {}
        for m in want:
            rts[m['route']] = round(rts.get(m['route'], 0) + (m['to_date'] if running else m['net']), 2)
        for k, v in rts.items():
            ck(f"{tag} heading carries {ROUTE_NAME.get(k, k)} {money(v)}", f"{ROUTE_NAME.get(k, k.upper())}: {money(v)}" in sub, sub)
        ck(f"{tag} heading counts {len(want)} staff", f"{len(want)} staff" in sub, sub)
        # PDF: the same rows and the same total
        p = c.get('/export/payroll/statement', params=dict(run_id=r['id'], token=tok(), format='pdf', emps=emps))
        ck(f"{tag} PDF downloads", p.status_code == 200 and p.content[:4] == b'%PDF', p.status_code)
        if p.status_code == 200:
            txt = pdf_text(p.content)
            tot_line = next((ln for ln in txt.splitlines() if ln.strip().upper().startswith('TOTAL')), '')
            ck(f"{tag} PDF TOTAL line carries {money(sum(m['to_date'] if running else m['net'] for m in want))}",
               money(sum(m['to_date'] if running else m['net'] for m in want)) in tot_line, tot_line)
            for m in want:
                ck(f"{tag} PDF has {m['code']}", m['code'] in txt)
        # Preview: the totals line
        v = c.get('/export/payroll/statement/view', params=dict(run_id=r['id'], token=tok(), emps=emps))
        ck(f"{tag} Preview opens", v.status_code == 200, v.status_code)
        if v.status_code == 200:
            foot = re.search(r'<tr class="tot">(.*?)</tr>', v.text, re.S)
            ck(f"{tag} Preview TOTAL carries {money(sum(m['to_date'] if running else m['net'] for m in want))}",
               foot is not None and money(sum(m['to_date'] if running else m['net'] for m in want)) in foot.group(1),
               foot.group(1)[:300] if foot else None)
    return api, mine, running


def audit_consolidated(month, group, runs_here, mines):
    """All companies for one statement: the same lines read a second time; ticked subset honoured."""
    rows = [m for rid in runs_here for m in mines[rid].values() if not m['held']]
    if not rows:
        return
    for pick in ([m['emp_id'] for m in rows], [m['emp_id'] for m in rows][1::2]):
        if not pick:
            continue
        want = [m for m in rows if m['emp_id'] in pick]
        x = c.get('/export/payroll/consolidated', params=dict(month_year=month, group=group, token=tok(), format='excel',
                                                              emps=",".join(map(str, pick))))
        tag = f"all companies {month} {group} ({len(want)} ticked)"
        ck(f"{tag}: Excel downloads", x.status_code == 200, x.status_code)
        if x.status_code != 200:
            continue
        head, body, total, sub = xlsx_rows(x.content)
        ck(f"{tag}: exactly the ticked rows", sorted(str(b_['Emp. Code']) for b_ in body) == sorted(m['code'] for m in want))
        ck(f"{tag}: TOTAL net {money(sum(m['net'] for m in want))}",
           total is not None and same(total.get('Net Pay'), sum(m['net'] for m in want)), total)
        ck(f"{tag}: TOTAL = rows added up", total is not None and same(total.get('Net Pay'), sum(float(b_['Net Pay'] or 0) for b_ in body)))
        rts = {}
        for m in want:
            rts[m['route']] = round(rts.get(m['route'], 0) + m['net'], 2)
        for k, v in rts.items():
            ck(f"{tag}: heading {ROUTE_NAME.get(k, k)} {money(v)}", f"{ROUTE_NAME.get(k, k.upper())}: {money(v)}" in sub, sub)


def audit_gratuity(today):
    for e in q("select * from employees where staff=1 and active=1 order by emp_no"):
        g = c.get(f"/employees/staff/{e['emp_no']}/file", headers=H).json()['gratuity']
        if (e['scheme'] or 'gratuity') != 'gratuity' or not e['joined_on']:
            ck(f"gratuity {e['emp_no']}: none ({e['scheme']}, joined {e['joined_on']})", same(g['amount'], 0), g)
            continue
        end = min(today, d(e['terminated_on'])) if e['terminated_on'] else today
        service = (end - d(e['joined_on'])).days + 1
        months = sorted({r['on_date'][:7] for r in q("select on_date from staff_leave where employee_id=? and on_date>=? and on_date<=?",
                                                       e['id'], e['joined_on'], end.isoformat())})
        unpaid = vac = 0.0
        for ym in months:
            y, mth = map(int, ym.split('-'))
            a = date(y, mth, 1)
            b = date(y + (mth == 12), mth % 12 + 1, 1) - timedelta(days=1)
            for row, u in judged(e['id'], a, b):
                if d(row['on_date']) > end or d(row['on_date']) < d(e['joined_on']):
                    continue
                if row['kind'] == 'vacation':
                    vac += row['portion'] or 1.0          # company rule: vacation is not service
                else:
                    unpaid += u
        ns = unpaid + vac + float(e['past_not_service'] or 0)
        years = max(service - ns, 0) / 365.0
        basic = e['basic_salary'] or 0
        if years < 1:
            amount = 0.0
        else:
            amount = min((min(years, 5) * 21 + max(years - 5, 0) * 30) * basic * 12 / 365.0, basic * 24)
        ck(f"gratuity {e['emp_no']} {e['name']}: {amount:,.2f} ({years:.3f} yrs, {ns:g} days not service)",
           same(g['amount'], amount), (g['amount'], g.get('why')))
        # The final settlement drawn on the same day must carry the same gratuity and add up.
        if d(e['joined_on']) > end:
            continue
        s = c.get(f"/employees/staff/{e['emp_no']}/settlement",params={'last_day': end.isoformat()}, headers=H)
        if s.status_code != 200:
            ck(f"settlement {e['emp_no']} opens", False, s.text[:200])
            continue
        s = s.json()
        ck(f"settlement {e['emp_no']}: gratuity {g['amount']:,.2f} = Gratuity screen", same(s['gratuity']['amount'], g['amount'], 0.011),
           (s['gratuity']['amount'], g['amount']))
        ck(f"settlement {e['emp_no']}: payables add up", same(s['total_pay'], sum(x['amount'] for x in s['payables'])))
        ck(f"settlement {e['emp_no']}: deductions add up", same(s['total_ded'], sum(x['amount'] for x in s['deductions'])))
        ck(f"settlement {e['emp_no']}: net = payable - deductions to the dirham",
           same(s['net'], math.floor(s['total_pay'] - s['total_ded'] + 0.5)), s['net'])
        ck(f"settlement {e['emp_no']}: leave pay = days x basic x 12 / 365",
           same(next(x['amount'] for x in s['payables'] if x['label'] == 'Leave encashment'),
                s['input']['leave_days'] * round(basic * 12 / 365.0, 2)))


def runs_on_file():
    return q("select r.*, c.short_name from payroll_runs r join companies c on c.id=r.company_id order by r.month_year, r.id")


REAL_TODAY = main._dubai_today()
runs = runs_on_file()
ck("there are office cycles on file", len(runs) > 0)
months = sorted({r['month_year'] for r in runs}, key=lambda m: datetime.strptime(m, '%B %Y'))
latest = [m for m in months if bounds(m)[0] <= REAL_TODAY] or months
newest = latest[-1]
mid = bounds(newest)[0] + timedelta(days=14)
_orig_today = main._dubai_today
for today in sorted({REAL_TODAY, mid}):
    main._dubai_today = lambda t=today: t
    mines = {}
    for r in runs_on_file():
        if r['month_year'] not in months[-3:]:
            continue
        api, mine, running = audit_run(r, today)
        mines[r['id']] = mine
    for m in months[-3:]:
        for g in ('staff', 'local'):
            audit_consolidated(m, g, [r['id'] for r in runs_on_file() if r['month_year'] == m and (r['group'] or 'staff') == g], mines)
    # Pay full month now for a ticked half of a draft that is still running.
    if today == mid:
        for r in runs_on_file():
            if r['month_year'] != newest or r['status'] == 'approved':
                continue
            lines = [x for x in q("select * from payroll_lines where run_id=? and held=0", r['id'])]
            if len(lines) < 2:
                continue
            key = f"hr_full_month:{r['month_year']}:{r['group']}"
            before = (q("select value from settings where key=?", key) or [{'value': None}])[0]['value']
            ids = [x['employee_id'] for x in lines][::2]
            res = c.post('/employees/payroll/full-month', json={'month_year': r['month_year'], 'group': r['group'], 'on': True,
                                                                 'employee_ids': ids}, headers=H)
            ck(f"Pay full month now ({len(ids)} ticked) accepted", res.status_code == 200, res.text[:200])
            audit_run(r, today, " after Pay full month for the ticked")
            c.post('/employees/payroll/full-month', json={'month_year': r['month_year'], 'group': r['group'], 'on': False}, headers=H)
            if before:
                raw.execute("update settings set value=? where key=?", (before, key)); raw.commit()
            break
    audit_gratuity(today)
main._dubai_today = _orig_today

print(f"{NCHK[0]} checks")
if FAIL:
    print(f"{len(FAIL)} FAILED")
    sys.exit(1)
print("EVERY OFFICE PAY FIGURE AGREES WITH THE HAND CALCULATION")

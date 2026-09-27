"""Every labour salary card recomputed by hand from the raw attendance.

Run: python3 tests/labour_card_audit.py /tmp/scen.db
Reads the database with plain SQL and works each card out again from the
rules - a day is 1/30 of the monthly rate; Present, Sick, Medical, Sunday,
Friday, Holiday are paid; a daily worker loses a day's pay for each Absent
day on top of not earning it; a fixed worker is capped at his salary; OT
and BH pay 1/8 of a day per hour; rounding half away from zero. The rate
is the one in force at the end of the cycle. Additions and deductions
are added to the final figure separately.
"""
import sqlite3, sys, math
from datetime import date, datetime, timedelta
db = sqlite3.connect(sys.argv[1] if len(sys.argv) > 1 else "/tmp/scen.db")
PAID = {"present", "sick", "medical", "friday", "sunday", "holiday"}
def bounds(label):
    d = datetime.strptime("25 " + label, "%d %B %Y").date()
    start = (d.replace(day=1) - timedelta(days=1)).replace(day=26)
    return start, d
def rnd(x): return math.floor(x + 0.5 + 1e-9) if x >= 0 else math.ceil(x - 0.5 - 1e-9)
cards = db.execute("select id, emp_no, month_year, total_salary, present_days, absent_days, sunday_days, holiday_days, terminated_days, ot_hours, bh_hours, final_salary, allowances, other_deduction from employee_summaries").fetchall()
emp = {r[0]: r for r in db.execute("select emp_no, pay_type, total_salary from employees")}
bad = checked = 0
for (sid, no, label, total, pres, absn, sun, hol, term, ot, bh, final, allow, odd) in cards:
    s, e = bounds(label)
    rows = db.execute("select am, pm, ot, bh from daily_rows where emp_no=? and full_date between ? and ?", (no, s.isoformat(), e.isoformat())).fetchall()
    cnt = {}
    o = b = 0.0
    for am, pm, r_ot, r_bh in rows:
        for x in (am, pm):
            x = (x or "").strip().lower()
            if x: cnt[x] = cnt.get(x, 0) + 0.5
        o += r_ot or 0; b += r_bh or 0
    # the rate in force at the end of the cycle (dated rate changes), else the master rate
    ch = db.execute("""select sc.basic + sc.allowance from salary_changes sc join employees e on e.id = sc.employee_id
                       where e.emp_no=? and sc.kind in ('rate','opening') and sc.effective_on <= ? order by sc.effective_on desc, sc.id desc limit 1""",
                    (no, e.isoformat())).fetchone() if db.execute("select name from sqlite_master where name='salary_changes'").fetchone() else None
    rate_total = (ch[0] if ch and ch[0] else None) or emp[no][2]
    day = rate_total / 30.0 if rate_total else 0
    paid = sum(v for k, v in cnt.items() if k in PAID)
    if emp[no][1] == "fixed":
        comp = min(paid * day, rate_total); ded = 0
    else:
        comp = paid * day; ded = day * cnt.get("absent", 0)
    want = rnd(comp + day / 8 * o + day / 8 * b + (allow or 0) - ded - (odd or 0))
    checked += 1
    probs = []
    if abs((pres or 0) - cnt.get("present", 0)) > 1e-6: probs.append(f"present {pres} vs {cnt.get('present', 0)}")
    if abs((absn or 0) - cnt.get("absent", 0)) > 1e-6: probs.append(f"absent {absn} vs {cnt.get('absent', 0)}")
    if abs((ot or 0) - o) > 1e-6: probs.append(f"OT {ot} vs {o}")
    if abs((total or 0) - rate_total) > 0.01: probs.append(f"rate {total} vs {rate_total}")
    if int(final) != want: probs.append(f"final {final} vs {want}")
    if probs:
        bad += 1
        print(f"FAIL {no} {label}: " + "; ".join(probs))
adj = db.execute("select count(*), sum(case when is_deduction then -amount else amount end) from salary_adjustments").fetchone()
print(f"{checked} cards recomputed; {adj[0]} additions/deductions on file (net {adj[1] or 0:+.2f})")
print("EVERY LABOUR CARD AGREES WITH THE HAND CALCULATION" if not bad else f"{bad} CARDS DISAGREE")
sys.exit(1 if bad else 0)

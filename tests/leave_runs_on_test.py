"""Leave runs on to the next working day (23/11/2026, Praveen): on leave till Saturday, back on Monday -> the Sunday
is leave, not a paid rest day; a public holiday after the leave the same. Labour (Leave mark) and office staff
(vacation / unpaid). A plain Absent does not pull the Sunday in. From the November 2026 cycle; earlier cycles as paid."""
import os, sys, tempfile
from datetime import date, timedelta
db_path = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as M, models, services
from database import SessionLocal, engine
models.Base.metadata.create_all(bind=engine); M._add_missing_columns()
s = SessionLocal()
FAIL = []
def ok(c, m, x=""):
    print(("PASS " if c else "FAIL ") + m + ("" if c else f"  [{x}]"))
    if not c: FAIL.append(m)

def worker(no, pay="daily"):
    e = models.Employee(emp_no=no, name="W " + no, trade="Mason", total_salary=1500, basic_salary=1000, pay_type=pay, active=True, staff=False,
                        joined_on=date(2025, 1, 1))
    s.add(e); s.commit(); return e

def mark(e, d, am, pm=None, ot=0):
    _, _, my = M.pcyc.cycle_bounds_for(d)
    s.add(models.DailyRow(employee_id=e.id, emp_no=e.emp_no, emp_name=e.name, trade=e.trade, month_year=my, full_date=d, day=d.day,
                          am=am, pm=pm if pm is not None else am, ot=ot, bh=0, site="913", engineer="", comments=""))

def fill(e, a, b, leave=(), absent=(), holiday=(), present_sun=(), sick=()):
    d = a
    while d <= b:
        if d in leave: mark(e, d, "Leave")
        elif d in absent: mark(e, d, "Absent")
        elif d in holiday: mark(e, d, "Holiday")
        elif d in sick: mark(e, d, "Sick")
        elif d.weekday() == 6 and d not in present_sun: mark(e, d, "Sunday")
        else: mark(e, d, "Present")
        d += timedelta(days=1)
    s.commit()

A, B = date(2026, 10, 26), date(2026, 11, 25)                      # the November 2026 cycle
sat, sun, mon = date(2026, 11, 7), date(2026, 11, 8), date(2026, 11, 9)
ok(sat.weekday() == 5 and sun.weekday() == 6, "set-up: 07/11/2026 is a Saturday")

# 1. leave Wed-Sat, back Monday: Sunday becomes Leave
w1 = worker("T-1")
fill(w1, A, B, leave={date(2026, 11, 4), date(2026, 11, 5), date(2026, 11, 6), sat})
sm = services.recalculate_summary(s, w1, "November 2026"); s.commit()
ok(sm.leave_days == 5 and sm.sunday_days == 3, "leave Wed-Sat: the Sunday after is leave too (5 leave days, 3 of the 4 Sundays paid)", (sm.leave_days, sm.sunday_days))
rows = services.card_rows(s, w1, "November 2026", s.query(models.DailyRow).filter_by(emp_no="T-1", month_year="November 2026").all())
r = next(x for x in rows if x.full_date == sun)
ok(r.am == "Leave" and "next working day" in r.comments, "the card prints that Sunday as Leave, with the reason", (r.am, r.comments))
ok(s.query(models.DailyRow).filter_by(emp_no="T-1", full_date=sun).first().am == "Sunday", "the attendance itself is not changed")

# 2. a plain Absent on Saturday: Sunday stays paid
w2 = worker("T-2")
fill(w2, A, B, absent={sat})
sm2 = services.recalculate_summary(s, w2, "November 2026"); s.commit()
ok(sm2.sunday_days == 4 and sm2.leave_days == 0, "absent on Saturday: Sunday still paid (Praveen: normal absence is fine)", (sm2.sunday_days, sm2.leave_days))

# 3. leave Saturday, Sunday, then a public holiday on Monday: both leave; Tuesday back
w3 = worker("T-3")
fill(w3, A, B, leave={sat}, holiday={mon})
sm3 = services.recalculate_summary(s, w3, "November 2026"); s.commit()
ok(sm3.leave_days == 3 and sm3.holiday_days == 0, "leave Saturday + Sunday + public holiday Monday: all three leave", (sm3.leave_days, sm3.holiday_days))

# 4. a holiday elsewhere in the month, not after leave: stays paid
w4 = worker("T-4")
fill(w4, A, B, holiday={date(2026, 11, 18)})
sm4 = services.recalculate_summary(s, w4, "November 2026"); s.commit()
ok(sm4.holiday_days == 1 and sm4.leave_days == 0, "a holiday not after leave: paid as before")

# 5. leave starting Monday: the Sunday before stays paid
w5 = worker("T-5")
fill(w5, A, B, leave={mon, date(2026, 11, 10)})
sm5 = services.recalculate_summary(s, w5, "November 2026"); s.commit()
ok(sm5.leave_days == 2 and sm5.sunday_days == 4, "leave from Monday: the Sunday before it stays paid", (sm5.leave_days, sm5.sunday_days))

# 6. he worked that Sunday (Present) after leave on Saturday: Present stands
w6 = worker("T-6")
fill(w6, A, B, leave={sat}, present_sun={sun})
sm6 = services.recalculate_summary(s, w6, "November 2026"); s.commit()
ok(sm6.leave_days == 1 and sm6.present_days >= 1, "came in on that Sunday: it stays Present", (sm6.leave_days,))

# 7. half-day leave on Saturday morning, worked the afternoon: Sunday paid
w7 = worker("T-7")
fill(w7, A, B)
r7 = s.query(models.DailyRow).filter_by(emp_no="T-7", full_date=sat).first(); r7.am, r7.pm = "Leave", "Present"; s.commit()
sm7 = services.recalculate_summary(s, w7, "November 2026"); s.commit()
ok(sm7.leave_days == 0.5 and sm7.sunday_days == 4, "leave Saturday morning only, back in the afternoon: Sunday paid", (sm7.leave_days, sm7.sunday_days))

# 8. leave through Saturday 24/10 and Sunday 25/10 (October's cycle), a public holiday on Monday 26/10 - the first
#    day of November's cycle: the holiday follows the leave, so it is leave (the day before the cycle is looked up)
w8 = worker("T-8")
fill(w8, date(2026, 9, 26), date(2026, 10, 25), leave={date(2026, 10, 24), date(2026, 10, 25)})
fill(w8, A, B, holiday={A})
sm8 = services.recalculate_summary(s, w8, "November 2026"); s.commit()
ok(A.weekday() == 0 and sm8.leave_days == 1 and sm8.holiday_days == 0, "holiday on the cycle's first day right after leave in the cycle before: leave", (sm8.leave_days, sm8.holiday_days))
smo = services.recalculate_summary(s, w8, "October 2026"); s.commit()
ok(smo.leave_days == 2, "October 2026 and earlier cycles are as they were paid")

# 9. older cycle untouched
w9 = worker("T-9")
fill(w9, date(2026, 9, 26), date(2026, 10, 25), leave={date(2026, 10, 10)})       # a Saturday in October's cycle
smb = services.recalculate_summary(s, w9, "October 2026"); s.commit()
ok(date(2026, 10, 10).weekday() == 5 and smb.leave_days == 1, "October cycle: the Sunday after leave stays paid (rule starts in November)", smb.leave_days)

# 10. fixed-pay worker: the Sunday after leave comes off as a leave day
w10 = worker("T-10", pay="fixed")
fill(w10, A, B, leave={sat})
f_with = services.recalculate_summary(s, w10, "November 2026").final_salary; s.commit()
w11 = worker("T-11", pay="fixed")
fill(w11, A, B, leave={date(2026, 11, 5)})     # a Thursday: no Sunday after it
f_one = services.recalculate_summary(s, w11, "November 2026").final_salary; s.commit()
ok(round(f_one - f_with, 2) == 50.0, "fixed pay: leave on Saturday costs two days (Sat + Sun), on Thursday one - 50.00 apart (1,500/30)", (f_one, f_with))

# ---- office staff (vacation / unpaid on the absence register) ----
st = models.Employee(emp_no="S-1", name="Staff One", trade="QS", total_salary=6000, basic_salary=2400, pay_type="fixed", active=True, staff=True,
                     joined_on=date(2024, 1, 1))
s.add(st); s.commit()
def leave(e, d, kind, portion=1.0, rule="auto"):
    s.add(models.StaffLeave(employee_id=e.id, on_date=d, portion=portion, kind=kind, paid=False, pay_rule=rule, reason="", batch="b1")); s.commit()
for d in (date(2026, 11, 5), date(2026, 11, 6), sat):
    leave(st, d, "unpaid")
a, b = M._staff_month_bounds("November 2026")
rows = M._month_rows(s, st.id, a, b)
ok([(x.on_date, x.kind) for x in rows if getattr(x, "run_on", False)] == [(sun, "unpaid")], "staff: unpaid leave Thu-Sat adds Sunday 08/11 as unpaid", [(x.on_date, x.kind) for x in rows])
ded, why = M._absence_deduction(s, st, "November 2026")
ok("08/11/2026" in why or "07/11/2026 - 08/11/2026" in why or "05/11/2026 - 08/11/2026" in why, "the deduction names the Sunday", why)
one = models.Employee(emp_no="S-1b", name="Staff One b", trade="QS", total_salary=6000, basic_salary=2400, pay_type="fixed", active=True, staff=True, joined_on=date(2024, 1, 1))
s.add(one); s.commit(); leave(one, date(2026, 11, 11), "unpaid")
ded1, _ = M._absence_deduction(s, one, "November 2026")
ok(ded1 > 0 and abs(ded - 4 * ded1) < 0.02, "4 days deducted (3 + the Sunday), each the same as one ordinary unpaid day", (ded, ded1))
# a vacation ending Saturday 31/10 (October): Sunday 01/11 is in November - added there
st2 = models.Employee(emp_no="S-2", name="Staff Two", trade="QS", total_salary=3000, basic_salary=1200, pay_type="fixed", active=True, staff=True, joined_on=date(2024, 1, 1))
s.add(st2); s.commit()
leave(st2, date(2026, 10, 30), "vacation"); leave(st2, date(2026, 10, 31), "vacation")
ok(date(2026, 10, 31).weekday() == 5 and [x.on_date for x in M._month_rows(s, st2.id, a, b)] == [date(2026, 11, 1)], "vacation till Saturday 31/10: Sunday 01/11 counted in November", [x.on_date for x in M._month_rows(s, st2.id, a, b)])
ok([x.on_date for x in M._month_rows(s, st2.id, date(2026, 10, 1), date(2026, 10, 31))] == [date(2026, 10, 30), date(2026, 10, 31)], "October itself unchanged")
# sick / absent do not pull a Sunday in; a half day does not
st3 = models.Employee(emp_no="S-3", name="Staff Three", trade="QS", total_salary=3000, basic_salary=1200, pay_type="fixed", active=True, staff=True, joined_on=date(2024, 1, 1))
s.add(st3); s.commit()
leave(st3, sat, "absent")
leave(st3, date(2026, 11, 14), "unpaid", portion=0.5)
leave(st3, date(2026, 11, 21), "sick")
ok(not [x for x in M._month_rows(s, st3.id, a, b) if getattr(x, "run_on", False)], "absent / sick / half-day leave on a Saturday: Sunday not added")
# company holiday on the Monday after: given way, unpaid
st4 = models.Employee(emp_no="S-4", name="Staff Four", trade="QS", total_salary=3000, basic_salary=1200, pay_type="fixed", active=True, staff=True, joined_on=date(2024, 1, 1))
s.add(st4); s.commit()
leave(st4, sat, "vacation"); leave(st4, mon, "holiday")
got = [(x.on_date, M._leave_kind(x)) for x in M._month_rows(s, st4.id, a, b)]
ok(got == [(sat, "vacation"), (sun, "vacation"), (mon, "vacation")], "vacation Saturday + Sunday + company holiday Monday: all vacation", got)
# a Sunday with its own entry keeps it
st5 = models.Employee(emp_no="S-5", name="Staff Five", trade="QS", total_salary=3000, basic_salary=1200, pay_type="fixed", active=True, staff=True, joined_on=date(2024, 1, 1))
s.add(st5); s.commit()
leave(st5, sat, "unpaid"); leave(st5, sun, "sick")
got = [(x.on_date, M._leave_kind(x)) for x in M._month_rows(s, st5.id, a, b)]
ok(got == [(sat, "unpaid"), (sun, "sick")], "a Sunday with its own entry keeps it", got)
print("\n" + ("ALL PASS" if not FAIL else f"{len(FAIL)} FAILED"))
sys.exit(1 if FAIL else 0)

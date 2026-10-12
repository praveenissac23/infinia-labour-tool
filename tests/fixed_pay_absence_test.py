"""Fixed monthly pay (foremen, drivers): an absent or leave day costs one
thirtieth, once, shows on the card as the Absence/Leave line, and the
month cap never swallows it. Daily wage: an absent day costs two (the
day not earned + one deducted), a leave day one."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
from types import SimpleNamespace as R
import data_engine as de
FAIL = []
def ck(l, ok, x=""):
    print(("PASS " if ok else "FAIL ") + l + ("" if ok else f"  [{x}]"))
    if not ok: FAIL.append(l)
def rows(p=0, a=0, l=0, s=0):
    return [R(am="Present", pm="Present", ot=0, bh=0)] * p + [R(am="Absent", pm="Absent", ot=0, bh=0)] * a + \
           [R(am="Leave", pm="Leave", ot=0, bh=0)] * l + [R(am="Sunday", pm="Sunday", ot=0, bh=0)] * s
fx = lambda *a: de.recalculate_from_daily_rows(rows(*a), 4000, 1600, pay_type="fixed")
r = fx(13, 1, 0, 3)     # Barsati, 12 Oct: 13 present, 3 Sundays, 1 absent so far
ck("mid-cycle: absence shown as a deduction", round(r["deduction"], 2) == 133.33, r)
ck("mid-cycle: final unchanged (16 paid days)", r["final_salary"] == 2133, r)
r = fx(25, 1, 0, 4)     # 30-day cycle, one absent
ck("30-day cycle, 1 absent: one day off", r["final_salary"] == 3867 and round(r["deduction"], 2) == 133.33, r)
r = fx(26, 1, 0, 4)     # 31-day cycle, one absent: used to be paid in full
ck("31-day cycle, 1 absent: one day off (cap no longer hides it)", r["final_salary"] == 3867, r)
r = fx(27, 0, 0, 4)
ck("31-day cycle, no absence: the salary, capped", r["final_salary"] == 4000 and r["deduction"] == 0, r)
r = fx(24, 0, 2, 4)
ck("leave: one day each, once", r["final_salary"] == 3733, r)
r = de.recalculate_from_daily_rows(rows(0, 0, 31), 3200, 1000, pay_type="fixed")
ck("whole month on leave: nothing, never negative", r["final_salary"] == 0, r)
d = de.recalculate_from_daily_rows(rows(25, 1, 0, 4), 3000, 1000, pay_type="daily")
ck("daily wage, 1 absent: 2 days off (day not earned + 1 deducted)", d["final_salary"] == 2800 and d["deduction"] == 100, d)
d = de.recalculate_from_daily_rows(rows(25, 0, 1, 4), 3000, 1000, pay_type="daily")
ck("daily wage, 1 leave: 1 day off", d["final_salary"] == 2900 and d["deduction"] == 0, d)
print("\nALL PASS" if not FAIL else f"\n{len(FAIL)} FAILED: {FAIL}")

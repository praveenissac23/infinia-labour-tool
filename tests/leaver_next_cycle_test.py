"""A worker who leaves must never block the next cycle's attendance.

Run: cd app && DATABASE_URL=sqlite:////tmp/leaver.db python3 ../tests/leaver_next_cycle_test.py

He is given a leaving date in one cycle; in the next cycle he is off the
day's grid, a save of everyone on the grid goes through, and the calendar
shows the day complete. In the cycle he left in he is still expected.
"""
import os, sys
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/../app")
from fastapi.testclient import TestClient
import main, payroll_cycle as pcyc

fails = 0
def ck(name, ok, info=""):
    global fails
    fails += 0 if ok else 1
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  {info}"))

with TestClient(main.app) as c:
    tok = c.post("/auth/login", data={"username": "admin", "password": os.environ.get("ADMIN_PW", "changeme123")}).json()["access_token"]
    H = {"Authorization": "Bearer " + tok}
    today = main._dubai_today()
    cs, ce, _ = pcyc.cycle_bounds_for(today)
    prev_day = cs - timedelta(days=3)                       # in the previous cycle
    site = (c.get("/sites", headers=H).json() or [{"name": "901"}])[0]
    site = site.get("name") or site.get("code") or "901"
    eng = (c.get("/engineers", headers=H).json() or [{"name": "ENG"}])[0]
    eng = eng.get("name") if isinstance(eng, dict) else eng
    staff = [e for e in c.get("/employees?active_only=true", headers=H).json()]
    if len(staff) < 3:
        for i in range(3):
            c.post("/employees", headers=H, json={"emp_no": f"LV{i}", "name": f"LEAVER TEST {i}", "trade": "HELPER", "total_salary": 1500, "basic_salary": 1000})
        staff = c.get("/employees?active_only=true", headers=H).json()
    leaver = staff[0]
    body = {k: leaver.get(k) for k in ("emp_no", "name", "trade", "company", "pay_type", "total_salary", "basic_salary")}
    body["terminated_on"] = prev_day.isoformat()
    r = c.post("/employees", headers=H, json=body)
    ck("a leaving date is recorded in the previous cycle", r.status_code == 200, r.text[:200])
    all_active = c.get("/employees?active_only=true", headers=H).json()
    ck("he is still active (so his last cycle is paid)", any(e["emp_no"] == leaver["emp_no"] for e in all_active))
    day = c.get(f"/employees?active_only=true&as_of={today.isoformat()}", headers=H).json()
    ck("he is off today's grid", all(e["emp_no"] != leaver["emp_no"] for e in day))
    rows = [{"emp_no": e["emp_no"], "full_date": today.isoformat(), "am": "Present", "pm": "Present", "site": site, "engineer": eng, "ot": 0, "bh": 0, "comments": ""} for e in day]
    r = c.post("/attendance/save", headers=H, json={"rows": rows})
    ck("saving everyone on today's grid goes through", r.status_code == 200, r.text[:300])
    month = date(ce.year, ce.month, 1).strftime("%B %Y")
    comp = {d["date"]: d for d in c.get(f"/attendance/completion/{month}?mode=cycle", headers=H).json()["days"]}
    t = comp.get(today.isoformat(), {})
    ck("today shows complete on the calendar", t.get("complete") is True, t)
    ck("and counts exactly the grid", t.get("total") == len(day), t)
    pmonth = date(prev_day.year, prev_day.month, 1)
    pcs, pce, _ = pcyc.cycle_bounds_for(prev_day)
    plabel = date(pce.year, pce.month, 1).strftime("%B %Y")
    pd = {d["date"]: d for d in c.get(f"/attendance/completion/{plabel}?mode=cycle", headers=H).json()["days"]}.get(prev_day.isoformat(), {})
    ck("in the cycle he left in he is still expected", pd.get("total") == len(day) + 1, pd)

print("A LEAVER NEVER BLOCKS THE NEXT CYCLE" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)

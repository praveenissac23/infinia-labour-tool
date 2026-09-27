"""Real-life test data: the situations that break payroll, on a copy of
the office data, entered through the app's own API the way people do.

Run: cd app && DATABASE_URL=sqlite:////tmp/scen.db ADMIN_PW=changeme123 python3 ../tests/seed_scenarios.py
     (start from a copy: cp /tmp/full_clean.db /tmp/scen.db)

What it puts in:
  * 12 sites (so the site lists are long, as they are live) and a third company, Enginova
  * attendance for the whole previous cycle and this cycle up to yesterday:
    mostly Present, with Absent, Sick, Medical, Leave, Holiday, Sunday, half days and OT/BH
  * LEAVER-PREV  left in the previous cycle  -> off this cycle's grid, still active
  * LEAVER-NOW   leaves in this cycle         -> Terminated after his last day
  * REMOVED      taken off the list            -> inactive
  * NEW-TODAY    added today                   -> no attendance yet
  * ENGINOVA     a worker of the third company
  * a labour rate change in the middle of the previous cycle
  * additions and deductions on several cards
Prints a summary of who is where, for the checks that follow.
"""
import os, sys, random
from datetime import date, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
from fastapi.testclient import TestClient
import main, payroll_cycle as pcyc

random.seed(27)
c = TestClient(main.app); c.__enter__()
tok = c.post("/auth/login", data={"username": "admin", "password": os.environ.get("ADMIN_PW", "changeme123")}).json()["access_token"]
H = {"Authorization": "Bearer " + tok}
def ok(r, what):
    if r.status_code >= 400:
        print("FAILED:", what, r.status_code, r.text[:300]); sys.exit(1)
    return r.json() if r.text else {}

today = main._dubai_today()
cs, ce, label = pcyc.cycle_bounds_for(today)
pcs, pce, plabel = pcyc.cycle_bounds_for(cs - timedelta(days=1))

# ---- sites, engineers, a third company --------------------------------
have = {s["code"] for s in c.get("/sites", headers=H).json()}
for code in ["901", "902", "903", "904", "905", "906", "907", "908", "909", "910", "911", "912"]:
    if code not in have:
        ok(c.post("/sites", headers=H, json={"code": code}), f"site {code}")
sites = [s["code"] for s in c.get("/sites", headers=H).json()]
engs = [e["name"] for e in c.get("/engineers", headers=H).json()]
cos = c.get("/employees/companies", headers=H).json()
if not any((x.get("short_name") or x.get("name")) == "Enginova" for x in cos):
    ok(c.post("/employees/companies", headers=H, json={"name": "ENGINOVA TECHNICAL SERVICES", "short_name": "Enginova", "code_prefix": "EN"}), "company Enginova")

# ---- the special workers ----------------------------------------------
def put(emp_no, name, **kw):
    body = {"emp_no": emp_no, "name": name, "trade": kw.pop("trade", "HELPER"), "company": kw.pop("company", "Infinia"),
            "pay_type": kw.pop("pay_type", "daily"), "total_salary": kw.pop("total", 1500), "basic_salary": kw.pop("basic", 1000),
            "joined_on": kw.pop("joined_on", "2026-01-05")}
    body.update(kw)
    return ok(c.post("/employees", headers=H, json=body), f"worker {emp_no}")

put("T-901", "LEAVER PREV CYCLE")
put("T-902", "LEAVER THIS CYCLE")
put("T-903", "REMOVED WORKER")
put("T-905", "ENGINOVA WORKER", company="Enginova", trade="TECHNICIAN", total=2200, basic=1400)
put("T-906", "FIXED FOREMAN", pay_type="fixed", trade="FOREMAN", total=3100, basic=2000)

# ---- attendance: previous cycle and this cycle up to yesterday --------
def status_for(emp_no, d):
    if d.weekday() == 6: return ("Sunday", "Sunday")
    r = random.random()
    if r < 0.80: return ("Present", "Present")
    if r < 0.85: return ("Present", "Absent")            # half day
    if r < 0.90: return ("Absent", "Absent")
    if r < 0.94: return ("Sick", "Sick")
    if r < 0.96: return ("Medical", "Medical")
    if r < 0.98: return ("Leave", "Leave")
    return ("Present", "Present")

holiday = pcs + timedelta(days=9)
while holiday.weekday() == 6: holiday += timedelta(days=1)
home = {}
d = pcs
saved_days = 0
while d < today:
    staff = c.get(f"/employees?active_only=true&as_of={d.isoformat()}", headers=H).json()
    rows = []
    for e in staff:
        home.setdefault(e["emp_no"], random.choice(sites))
        am, pm = ("Holiday", "Holiday") if d == holiday else status_for(e["emp_no"], d)
        worked = am in ("Present",) or pm in ("Present",)
        site = home[e["emp_no"]] if (worked or am in ("Sunday", "Holiday")) else ""
        eng = engs[hash(site) % len(engs)] if site else ""
        ot = random.choice([0, 0, 0, 1, 2, 2.5]) if am == pm == "Present" else 0
        bh = 1 if (am == pm == "Present" and random.random() < 0.05) else 0
        rows.append({"emp_no": e["emp_no"], "full_date": d.isoformat(), "am": am, "pm": pm, "site": site, "engineer": eng,
                     "ot": ot, "bh": bh, "comments": ""})
    r = c.post("/attendance/save", headers=H, json={"rows": rows})
    if r.status_code >= 400:
        print("attendance refused", d, r.text[:400]); sys.exit(1)
    saved_days += 1
    d += timedelta(days=1)

# ---- leavers, removal, new joiner (after their attendance exists) -----
emp = {e["emp_no"]: e for e in c.get("/employees?active_only=false", headers=H).json()}
def terminate(no, when):
    e = emp[no]
    body = {k: e.get(k) for k in ("emp_no", "name", "trade", "company", "pay_type", "total_salary", "basic_salary")}
    body["terminated_on"] = when.isoformat()
    ok(c.post("/employees", headers=H, json=body), f"terminate {no}")
terminate("T-901", pcs + timedelta(days=12))                     # left in the previous cycle
terminate("T-902", max(cs, today - timedelta(days=1)))            # leaves in this cycle
ok(c.delete("/employees/T-903", headers=H), "remove T-903")
put("T-904", "NEW JOINER TODAY", joined_on=None)          # no date given: joins today

# ---- a labour rate change mid previous cycle ---------------------------
lab = [e for e in emp.values() if e.get("active") and e.get("pay_type") == "daily" and not e["emp_no"].startswith("T-")]
rc = lab[3]
r = c.put(f"/employees/people/{rc['emp_no']}", headers=H,
          json={"employee": {"gross": (rc.get("total_salary") or 1500) + 200, "basic": (rc.get("basic_salary") or 1000) + 100,
                             "effective_on": (pcs + timedelta(days=15)).isoformat(), "reason": "scenario rate change"}})
rate_note = f"{rc['emp_no']} rate +200 from {(pcs + timedelta(days=15)).isoformat()} ({r.status_code})"

# ---- additions and deductions ------------------------------------------
sums = c.get(f"/summaries/{plabel}", headers=H).json()
adds = 0
for s in sums[:6]:
    ok(c.post(f"/summaries/{s['id']}/adjustments", headers=H, json={"description": "Food allowance", "amount": 150, "is_deduction": False}), "addition")
    ok(c.post(f"/summaries/{s['id']}/adjustments", headers=H, json={"description": "Advance", "amount": 200, "is_deduction": True}), "deduction")
    adds += 2

print(f"cycles: previous {plabel} ({pcs}..{pce}), current {label} ({cs}..{ce}); today {today}")
print(f"attendance saved for {saved_days} days; holiday {holiday}; sites {len(sites)}; {adds} adjustments")
print(f"leaver prev T-901 left {pcs + timedelta(days=12)}; leaver now T-902 left {max(cs, today - timedelta(days=1))}; removed T-903; new T-904; Enginova T-905; fixed T-906")
print(rate_note)
print("SCENARIO DATA READY")

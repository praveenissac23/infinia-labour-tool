"""Final settlement takes off salary already paid for the same days (owner, 31 Oct 2026) - office and labour.

Live case: office PI003, November salary 1,575.00 for 7 days (to 07/11/2026) paid early on 28/10/2026; his
settlement paid those 7 days' salary again. Now a line "Less: salary already paid on 28/10/2026 (period
01/11/2026 - 07/11/2026)" takes the amount actually paid for the overlapping days off - on screen, preview, PDF,
Excel and in the payment. A payment that covered more days than the settlement's salary days comes off pro rata
(exact, taken up to the fils). Only a login with the approve right can take the line out, with a reason that is
kept, printed as a note and logged. A settlement with no earlier payment is unchanged.

    cd app && DATABASE_URL=sqlite:////tmp/spd.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/settlement_paid_days_test.py
(an empty database)
"""
import os, sys, io, subprocess, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
os.environ.setdefault("INFINIA_NO_PUSH", "1")
from datetime import date, datetime, timedelta
from fractions import Fraction
from fastapi.testclient import TestClient
import openpyxl
import main, models, auth, payroll_cycle as pcyc, paystatus as PS
from database import SessionLocal

FAIL = []


def ck(l, ok, x=""):
    print(("PASS " if ok else "FAIL ") + l + ("" if ok else f"  [{str(x)[:500]}]"))
    if not ok:
        FAIL.append(l)


db = SessionLocal()
for un, role, perms in (("a", "admin", ""), ("hr", "office", "hrpayroll"), ("hrap", "office", "hrpayroll,approvals"),
                        ("lab", "office", "combine"), ("labap", "office", "combine,approvals")):
    db.add(models.User(username=un, hashed_password=auth.hash_password("p"), full_name=un.upper(), role=role, permissions=perms))
# PI003-like: gross 6,750 (basic 2,700 + allowance 4,050), joined 22/07/2026, leaving 07/11/2026
pi = models.Employee(emp_no="PX003", name="SREE TEST", staff=True, pay_group="staff", basic_salary=2700, allowance=4050,
                     total_salary=6750, active=True, joined_on=date(2026, 7, 22), terminated_on=date(2026, 11, 7))
# partial overlap: paid the whole of December early, leaves on 10/12/2026
pt = models.Employee(emp_no="PX004", name="PARTIAL TEST", staff=True, pay_group="staff", basic_salary=2000, allowance=3000,
                     total_salary=5000, active=True, joined_on=date(2025, 1, 5), terminated_on=date(2026, 12, 10))
# nothing paid before
np_ = models.Employee(emp_no="PX005", name="NOPAY TEST", staff=True, pay_group="staff", basic_salary=4000, allowance=2000,
                      total_salary=6000, active=True, joined_on=date(2024, 3, 1), terminated_on=date(2026, 11, 20))
db.add_all([pi, pt, np_]); db.commit()

run_nov = models.PayrollRun(month_year="November 2026", status="draft")
run_dec = models.PayrollRun(month_year="December 2026", status="draft")
db.add_all([run_nov, run_dec]); db.commit()
l_pi = models.PayrollLine(run_id=run_nov.id, employee_id=pi.id, basic=2700, allowance=4050, fixed_salary=6750, deduction=5175,
                          deduction_note="Left 07/11/2026 - 23 day(s) not employed", net_pay=1575)
l_pt = models.PayrollLine(run_id=run_dec.id, employee_id=pt.id, basic=2000, allowance=3000, fixed_salary=5000, net_pay=5000)
db.add_all([l_pi, l_pt]); db.commit()
p_pi = models.PayPayment(kind="office", employee_id=pi.id, month_year="November 2026", source_id=l_pi.id, run_id=run_nov.id,
                         pay_type="early_full", amount=1575, due=1575, paid_on=date(2026, 10, 28), mode="wps",
                         created_at=datetime(2026, 10, 28, 9, 5))
p_pt = models.PayPayment(kind="office", employee_id=pt.id, month_year="December 2026", source_id=l_pt.id, run_id=run_dec.id,
                         pay_type="early_full", amount=5000, due=5000, paid_on=date(2026, 11, 30), mode="wps",
                         created_at=datetime(2026, 11, 30, 9, 0))
db.add_all([p_pi, p_pt]); db.commit()

# labour: a card for the cycle he leaves in, 800.00 of it paid to date already
T = main._dubai_today()
last = T - timedelta(days=2)
cs, ce, cyc = pcyc.cycle_bounds_for(last)
lw = models.Employee(emp_no="F-951", name="LABOUR PAIDTEST", trade="MASON", basic_salary=1000, total_salary=1500, active=True,
                     joined_on=date(2023, 1, 10), terminated_on=last)
db.add(lw); db.commit()
card = models.EmployeeSummary(employee_id=lw.id, emp_no="F-951", emp_name=lw.name, month_year=cyc, total_salary=1500, final_salary=1234)
db.add(card); db.commit()
p_lw = models.PayPayment(kind="labour", employee_id=lw.id, month_year=cyc, source_id=card.id, pay_type="regular", amount=800,
                         due=1234, paid_on=cs, mode="cash", created_at=datetime(cs.year, cs.month, cs.day, 8, 0))
db.add(p_lw); db.commit()
IDS = {"pi": pi.id, "line_pi": l_pi.id, "p_pi": p_pi.id, "p_pt": p_pt.id, "p_lw": p_lw.id, "card": card.id}
db.close()

c = TestClient(main.app)
tok = lambda u: {"Authorization": "Bearer " + c.post("/auth/login", data={"username": u, "password": "p"}).json()["access_token"]}
A, HR, HRAP, LAB, LABAP = tok("a"), tok("hr"), tok("hrap"), tok("lab"), tok("labap")
DL = lambda h=A: c.post("/auth/download-token", headers=h).json()["token"]
less = lambda d: [x for x in d["deductions"] if x["label"].startswith("Less: salary already paid")]
pay = lambda d, k: next((x["amount"] for x in d["payables"] if x["label"].startswith(k)), None)


def pdf_text(url):
    r = c.get(url)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(r.content); fp = f.name
    t = subprocess.run(["pdftotext", "-layout", fp, "-"], capture_output=True, text=True).stdout
    os.unlink(fp); return " ".join(t.split())


def xl_rows(url):
    wb = openpyxl.load_workbook(io.BytesIO(c.get(url).content))
    return [[v for v in r if v is not None] for r in wb.active.iter_rows(values_only=True)]


# ---- 1. office, PI003-like ---------------------------------------------------------------------------------------
d = c.get("/employees/staff/PX003/settlement", headers=A).json()
ck("office: salary for 7 days of Nov 2026 = 1,575.00", pay(d, "Salary for 7 day(s)") == 1575.0, d["payables"])
L = less(d)
LBL = "Less: salary already paid on 28/10/2026 (period 01/11/2026 – 07/11/2026)"
ck(f'office: line "{LBL}" = 1,575.00', len(L) == 1 and L[0]["label"] == LBL and L[0]["amount"] == 1575.0, d["deductions"])
ck("office: net = payables - deductions, exact to the fils",
   abs(d["net"] - round(sum(x["amount"] for x in d["payables"]) - sum(x["amount"] for x in d["deductions"]), 2)) < 0.001, d)
ck("office: paid_before lists the payment, deducted 1,575.00", d["paid_before"] and d["paid_before"][0]["payment_id"] == IDS["p_pi"]
   and d["paid_before"][0]["deducted"] == 1575.0 and d["paid_before"][0]["days"] == 7, d.get("paid_before"))
ck("office: admin may take the line out (can_remove_paid)", d["can_remove_paid"] is True)
ck("office: plain payroll login may not", c.get("/employees/staff/PX003/settlement", headers=HR).json()["can_remove_paid"] is False)
NET_AFTER = d["net"]
q = "emp_no=PX003"
html = c.get(f"/export/payroll/settlement/view?{q}&token={DL()}").text
ck("preview shows the line and its amount", LBL in html and "1,575.00" in html.split(LBL)[1][:200])
pdf = pdf_text(f"/export/payroll/settlement?{q}&format=pdf&token={DL()}")
ck("PDF shows the line", "Less: salary already paid on 28/10/2026" in pdf and "01/11/2026" in pdf and "07/11/2026" in pdf, pdf[:1500])
ck("PDF net is the screen net", f"AED {abs(NET_AFTER):,.2f}" in pdf, (NET_AFTER, pdf[-600:]))
xr = xl_rows(f"/export/payroll/settlement?{q}&format=excel&token={DL()}")
ck("Excel has the line with 1,575 as a number", any(r and r[0] == LBL and 1575 in r for r in xr), [r for r in xr if r and "Less" in str(r[0])])

# the payment dialog and the payment itself
pv = c.post("/employees/pay/preview", headers=A, json={"kind": "office", "source_id": IDS["line_pi"], "type": "final",
                                                        "last_day": "2026-11-07"}).json()
ck("pay preview: to pay now = the settlement net (the 1,575.00 is not taken off twice)", pv["amount"] == round(max(NET_AFTER, 0), 2)
   and pv["paid_before"] == 0, (pv["amount"], NET_AFTER, pv.get("paid_before")))
ck("pay preview lists the Less line once", sum(1 for k, _ in pv["lines"] if k.startswith("Less: salary already paid")) == 1
   and not any(k.startswith("less Less") for k, _ in pv["lines"]), pv["lines"])

# ---- 4. removal with reason ----------------------------------------------------------------------------------------
r = c.post("/employees/settlement/paid-line", headers=HR, json={"emp_no": "PX003", "payment_id": IDS["p_pi"], "reason": "agreed"})
ck("removal: payroll login without the approve right refused (403)", r.status_code == 403, r.status_code)
r = c.post("/employees/settlement/paid-line", headers=LABAP, json={"emp_no": "PX003", "payment_id": IDS["p_pi"], "reason": "agreed"})
ck("removal: approver without office pay refused (403)", r.status_code == 403, r.status_code)
r = c.post("/employees/settlement/paid-line", headers=HRAP, json={"emp_no": "PX003", "payment_id": IDS["p_pi"], "reason": " "})
ck("removal: no reason refused (400)", r.status_code == 400, (r.status_code, r.text))
r = c.post("/employees/settlement/paid-line", headers=HRAP, json={"emp_no": "PX003", "payment_id": IDS["p_lw"], "reason": "x y z"})
ck("removal: someone else's payment refused (404)", r.status_code == 404, r.status_code)
r = c.post("/employees/settlement/paid-line", headers=HRAP,
           json={"emp_no": "PX003", "payment_id": IDS["p_pi"], "reason": "November was a gift, agreed with MD"})
ck("removal: approver with a reason", r.status_code == 200 and r.json()["removed"] is True, r.text)
d2 = c.get("/employees/staff/PX003/settlement", headers=A).json()
ck("removed: no Less line, net back up by exactly 1,575.00 (the old figure)", not less(d2) and abs(d2["net"] - NET_AFTER - 1575) < 0.001,
   (d2["net"], NET_AFTER))
NET_BEFORE = d2["net"]
note = next((n for n in d2["notes"] if "not deducted" in n), "")
ck("removed: a note says who, when and why", "HRAP" in note and "November was a gift, agreed with MD" in note and "28/10/2026" in note, d2["notes"])
html = c.get(f"/export/payroll/settlement/view?{q}&token={DL()}").text
pdf = pdf_text(f"/export/payroll/settlement?{q}&format=pdf&token={DL()}")
xr = xl_rows(f"/export/payroll/settlement?{q}&format=excel&token={DL()}")
ck("removed: the note is on the preview, the PDF and the Excel", "November was a gift" in html and "November was a gift" in pdf
   and any("November was a gift" in str(r[0]) for r in xr if r))
db = SessionLocal()
lg = db.query(models.AuditLog).filter(models.AuditLog.action == "settlement_paid_line").order_by(models.AuditLog.id.desc()).first()
ck("removed: activity log with the reason", lg and "NOT deducted" in lg.details and "November was a gift" in lg.details, lg and lg.details)
db.close()
pv2 = c.post("/employees/pay/preview", headers=A, json={"kind": "office", "source_id": IDS["line_pi"], "type": "final",
                                                         "last_day": "2026-11-07"}).json()
ck("removed: the payment falls back to the old rule (row payment taken off the payment) - never double-paid",
   pv2["amount"] == round(max(NET_BEFORE - 1575, 0), 2), (pv2["amount"], NET_BEFORE))
r = c.post("/employees/settlement/paid-line", headers=A, json={"emp_no": "PX003", "payment_id": IDS["p_pi"], "action": "restore"})
d3 = c.get("/employees/staff/PX003/settlement", headers=A).json()
ck("put back: the line and the net return", r.status_code == 200 and len(less(d3)) == 1 and d3["net"] == NET_AFTER, (d3["net"], NET_AFTER))

# pay it: the payment is the settlement net, the row reads paid in full
r = c.post("/employees/pay/mark", headers=A, json={"kind": "office", "source_id": IDS["line_pi"], "type": "final", "last_day": "2026-11-07",
                                                   "paid_on": "2026-11-07", "mode": "wps"})
ck("paid: the final payment is the settlement net", r.status_code == 200 and r.json()["payment"]["amount"] == round(NET_AFTER, 2), r.text[:300])
db = SessionLocal()
e_ = db.get(models.Employee, IDS["pi"])
st = PS.row_state(db, "office", e_, "November 2026", 1575)
ck("paid: total paid for his November row = 1,575.00 early + the settlement, no balance, settled",
   st["state"] == "settled" and st["balance"] == 0 and abs(st["paid"] - (1575 + NET_AFTER)) < 0.001 and abs(st["due"] - st["paid"]) < 0.001, st)
ck("never double-paid: everything paid = the settlement worked out without the 1,575.00 line (old net) once",
   abs(st["paid"] - NET_BEFORE) < 0.001, (st["paid"], NET_BEFORE))
db.close()

# ---- 2. labour, a paid card in the settlement cycle ------------------------------------------------------------
d = c.get("/employees/labour/F-951/settlement", headers=A).json()
L = less(d)
ck("labour: wages = his card 1,234.00", any("labour card" in x["label"] and x["amount"] == 1234 for x in d["payables"]), d["payables"])
ck(f"labour: Less line for the 800.00 paid on {cs:%d/%m/%Y} (period {cs:%d/%m/%Y} - ...)",
   len(L) == 1 and L[0]["amount"] == 800.0 and L[0]["label"].startswith(f"Less: salary already paid on {cs:%d/%m/%Y} (period {cs:%d/%m/%Y} –"), d["deductions"])
gross = sum(Fraction(str(x["amount"])) for x in d["payables"])
ck("labour: net = payables - deductions, cut down to the fils",
   d["net"] <= float(gross - sum(Fraction(str(x["amount"])) for x in d["deductions"])) + 0.0001, d)
pv = c.post("/employees/pay/preview", headers=A, json={"kind": "labour", "source_id": IDS["card"], "type": "final",
                                                        "last_day": last.isoformat()}).json()
ck("labour: the payment is the net (800 not taken off again)", pv["amount"] == round(max(d["net"], 0), 2) and pv["due"] == round(d["net"] + 800, 2),
   (pv["amount"], pv["due"], d["net"]))
ck("labour: with the plain Labour payroll login no remove; with approvals yes",
   c.get("/employees/labour/F-951/settlement", headers=LAB).json()["can_remove_paid"] is False
   and c.get("/employees/labour/F-951/settlement", headers=LABAP).json()["can_remove_paid"] is True)
r = c.post("/employees/settlement/paid-line", headers=HRAP, json={"emp_no": "F-951", "payment_id": IDS["p_lw"], "reason": "abc def"})
ck("labour: office approver without Labour payroll refused", r.status_code == 403, r.status_code)
html = c.get(f"/export/payroll/settlement/view?emp_no=F-951&token={DL()}").text
ck("labour: on the preview", "Less: salary already paid on" in html)

# ---- 3. partial overlap ---------------------------------------------------------------------------------------
d = c.get("/employees/staff/PX004/settlement", headers=A).json()
L = less(d)
exact = Fraction(5000) * 10 / 31
ck("partial: salary for 10 days of December = 5,000 x 10 / 31 cut down = 1,612.90", pay(d, "Salary for 10 day(s)") == 1612.9, d["payables"])
ck("partial: the whole month (31 days) was paid early - only 10 of 31 days come off, taken UP to the fils = 1,612.91",
   len(L) == 1 and L[0]["amount"] == float(pcyc.fils_up(exact)) == 1612.91 and "10 of the 31 days" in L[0]["label"]
   and "(period 01/12/2026 – 10/12/2026)" in L[0]["label"], L)

# ---- 5. nothing paid before: unchanged ---------------------------------------------------------------------------
d = c.get("/employees/staff/PX005/settlement", headers=A).json()
ck("no earlier payment: no Less line, paid_before empty", not less(d) and d["paid_before"] == [], d["deductions"])
ck("no earlier payment: deductions as before (none)", d["deductions"] == [{"label": "No deductions", "amount": 0.0}], d["deductions"])
ck("no earlier payment: net = gross payable", d["net"] == d["total_pay"], (d["net"], d["total_pay"]))

print(f"{len(FAIL)} FAILED" if FAIL else "ALL PASS")
sys.exit(1 if FAIL else 0)

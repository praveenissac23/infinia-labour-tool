"""
Entered once, seen everywhere.

Every kind of record is entered in one place and then looked for in
every other place that shows it - and, where there are two places to
enter it, entered from the other side too.

Run: cd app && DATABASE_URL=sqlite:////tmp/cross.db python3 ../tests/cross_link_test.py
     (a copy of a database with the office staff loaded; admin password
      as the second argument, default 'changeme123')
"""
import os, sys, io
sys.path.insert(0, os.getcwd())
from datetime import date
from fastapi.testclient import TestClient
import main

PW = sys.argv[1] if len(sys.argv) > 1 else "changeme123"
bad = 0


def ck(name, ok, detail=None):
    global bad
    if not ok:
        bad += 1
    print(("PASS " if ok else "FAIL ") + name + ("" if ok or detail is None else f"   [{detail}]"))


with TestClient(main.app) as c:
    H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": PW}).json()["access_token"]}
    g = lambda u: c.get(u, headers=H)
    post = lambda u, j: c.post(u, json=j, headers=H)
    today = date.today()
    month = today.strftime("%B %Y")

    staff = g("/employees/staff").json()["rows"]
    s = next(r for r in staff if r.get("active", True) and not r.get("terminated_on"))
    code = s["emp_no"]
    print(f"-- using {code} {s['name']}")

    # ---- 1. Increment entered on the Increments register ------------------------------
    P = lambda: g(f"/employees/people/{code}").json()
    before = P()["person"]
    r = post("/employees/increments", {"emp_no": code, "amount": 250, "effective_on": today.isoformat(), "reason": "XL test rise"})
    ck("increment accepted", r.status_code == 200, r.text[:120])
    full = P(); after = full["person"]
    ck("staff file: allowance up by 250", round(after["allowance"] - before["allowance"], 2) == 250, (before["allowance"], after["allowance"]))
    ck("staff file: salary history carries it", any(h.get("reason") == "XL test rise" for h in full["salary_history"]))
    reg = next(r for r in g("/employees/staff").json()["rows"] if r["emp_no"] == code)
    ck("staff register: new salary", round(reg["allowance"], 2) == round(after["allowance"], 2), (reg["allowance"], after["allowance"]))
    inc = [r for r in g(f"/employees/increments?emp_no={code}").json()["rows"] if r.get("reason") == "XL test rise"]
    ck("increments register lists it", len(inc) == 1)
    # the open cycle for this month picks it up
    co = after.get("company_id")
    run = post("/employees/payroll/runs", {"month_year": month, "company_id": co, "group": "staff"}).json()
    line = next((l for l in run.get("lines", []) if l["emp_no"] == code), None)
    ck("this month's cycle: allowance on the line", line is not None and round(line["allowance"], 2) == round(after["allowance"], 2),
       line and (line["allowance"], after["allowance"]))
    hist = g(f"/employees/people/{code}").json()["history"]
    ck("staff file history: the change is logged", any("250" in h["what"] for h in hist))

    # ---- 2. Loan entered from the staff file (same register) -----------------------------
    r = post("/employees/loans", {"emp_no": code, "amount": 1200, "taken_on": today.isoformat(), "instalment": 300, "terms": "XL test loan"})
    ck("loan accepted", r.status_code == 200, r.text[:120])
    lid = r.json().get("id")
    ck("loans register lists it", any(l["terms"] == "XL test loan" for l in g("/employees/loans").json()["rows"]))
    ck("staff file: money section lists it", any(l["terms"] == "XL test loan" for l in g(f"/employees/people/{code}").json()["loans"]))
    run = post("/employees/payroll/runs", {"month_year": month, "company_id": co, "group": "staff"}).json()
    line = next((l for l in run.get("lines", []) if l["emp_no"] == code), None)
    ck("this month's cycle: instalment taken", line is not None and line["loan_deduction"] >= 300, line and line["loan_deduction"])
    ck("this month's cycle: remark shows the balance", line is not None and "balance" in (line.get("remarks") or "").lower(), line and line.get("remarks"))
    t = c.post("/auth/download-token", headers=H).json()["token"]
    ck("loans report prints it", "XL test loan" in c.get(f"/export/payroll/loans/view?token={t}").text)
    # repayment from the staff file reflects on the register
    r = post(f"/employees/loans/{lid}/repay", {"amount": 200, "paid_on": today.isoformat(), "how": "cash", "notes": "XL cash"})
    ck("repayment accepted", r.status_code == 200, r.text[:120])
    L = next(l for l in g("/employees/loans").json()["rows"] if l["id"] == lid)
    ck("loans register: balance after the repayment", round(L["balance"], 2) == 1000, L["balance"])
    L2 = next(l for l in g(f"/employees/people/{code}").json()["loans"] if l["id"] == lid)
    ck("staff file: the same balance", round(L2["balance"], 2) == 1000, L2["balance"])

    # ---- 3. Document entered on the staff file -> HR documents and documents due ---------
    r = post("/employees/documents", {"emp_no": code, "kind": "passport", "number": "XL123", "expires_on": date(today.year, today.month, min(today.day, 28)).replace(year=today.year + (1 if today.month == 12 else 0)).isoformat() if False else (today.replace(day=1)).isoformat()})
    ck("document accepted", r.status_code == 200, r.text[:120])
    ck("HR documents list shows it", any(d.get("number") == "XL123" for d in g("/employees/documents").json().get("rows", [])))
    ck("documents due shows it", any(d.get("number") == "XL123" for d in g("/employees/people/documents-due?days=90").json()["rows"]))
    ck("staff file documents show it", any(d.get("number") == "XL123" for d in g(f"/employees/people/{code}").json().get("documents", [])))

    # ---- 4. Absence entered on HR -> staff file ------------------------------------------
    r = post("/employees/leave", {"emp_no": code, "kind": "sick", "from": today.isoformat(), "to": today.isoformat(), "reason": "XL sick"})
    ck("absence accepted", r.status_code == 200, r.text[:120])
    ab = g(f"/employees/people/{code}").json()["absence"]
    ck("staff file: absence listed", any(a["kind"] == "sick" and a["from"] == today.isoformat() for a in ab), ab[:2])

    # ---- 5. A company added -> every company list ----------------------------------------
    r = post("/employees/companies", {"name": "XL ENGINEERING LLC", "short_name": "XLEng", "code_prefix": "XL"})
    ck("company accepted", r.status_code == 200, r.text[:120])
    names = [x.get("short_name") for x in g("/employees/companies").json()]
    ck("companies list has it (HR, Staff, Master Data, reports read this)", "XLEng" in names)
    # a labourer can be put on it, and the import recognises it
    r = post("/employees", {"emp_no": "XL-01", "name": "XL WORKER", "trade": "Helper", "basic_salary": 900, "company": "XLEng"})
    ck("labourer saved on the new company", r.status_code == 200 and r.json().get("company") == "XLEng", r.text[:120])
    ck("staff page: labour register shows him on it", any(p["emp_no"] == "XL-01" and p["company"] == "XLEng" for p in g("/employees/people?group=labour").json()["rows"]))
    ck("attendance list shows him", any(e["emp_no"] == "XL-01" for e in g("/employees?active_only=true").json()))

    # ---- 6. A person added on the staff page -> master data / attendance -----------------
    r = post("/employees/people", {"group": "labour", "emp_no": "XL-02", "name": "XL SECOND", "designation": "Mason", "company_id": [x for x in g("/employees/companies").json() if x["short_name"] == "XLEng"][0]["id"], "basic": 1000, "allowance": 200, "joined_on": today.isoformat()})
    ck("person accepted on the staff page", r.status_code == 200, r.text[:160])
    emp = next((e for e in g("/employees?active_only=true").json() if e["emp_no"] == "XL-02"), None)
    ck("master data / attendance list has him", emp is not None)
    ck("with his company and salary", emp is not None and emp.get("company") == "XLEng" and round(emp.get("basic_salary") or 0) == 1000, emp and (emp.get("company"), emp.get("basic_salary")))

    # ---- 7. A name corrected on the staff page -> master data ----------------------------
    r = c.put("/employees/people/XL-02", json={"employee": {"name": "XL SECOND CORRECTED"}}, headers=H)
    ck("name edit accepted", r.status_code == 200, r.text[:120])
    emp = next((e for e in g("/employees?active_only=true").json() if e["emp_no"] == "XL-02"), None)
    ck("master data shows the corrected name", emp is not None and emp["name"] == "XL SECOND CORRECTED", emp and emp["name"])

    # ---- 8. A labourer's rate changed on master data -> staff page ----------------------
    r = post("/employees", {"emp_no": "XL-01", "name": "XL WORKER", "trade": "Helper", "basic_salary": 950, "company": "XLEng"})
    p = next(p for p in g("/employees/people?group=labour").json()["rows"] if p["emp_no"] == "XL-01")
    ck("staff page shows the new rate", round(p["basic"]) == 950, p["basic"])

    # ---- 9. A site added -> attendance, requests, store ----------------------------------
    r = post("/sites", {"code": "977", "name": "XL site"})
    ck("site accepted", r.status_code == 200, r.text[:120])
    ck("site list (attendance, requests, moves read this)", any(x["code"] == "977" for x in g("/sites").json()))

    # ---- 10. A supplier and a rental item -> store, rental, requests ---------------------
    r = post("/store/suppliers", {"name": "XL Scaffold Hire LLC", "trn": "100200300400003", "contact_person": "Ravi", "phone": "0501112233", "email": "hire@xl.ae", "payment_terms": "30 days"})
    ck("supplier accepted", r.status_code == 200, r.text[:120])
    sup = r.json()
    r = post("/store/items", {"code": "XLR1", "name": "XL Ledger 2.0M", "item_type": "rental", "unit": "pcs", "category": "Scaffold", "rental_supplier": "XL Scaffold Hire LLC"})
    ck("rental item accepted", r.status_code == 200, r.text[:120])
    item = r.json()
    ck("material list shows it", any(i["code"] == "XLR1" for i in g("/store/items").json()))
    r = post("/store/hire/in", {"supplier_id": sup.get("id"), "supplier_name": "XL Scaffold Hire LLC", "received_on": today.isoformat(), "reference": "XL-DO-1", "lines": [{"item_id": item["id"], "qty": 40}]})
    ck("hired in", r.status_code == 200, r.text[:160])
    hire = g("/store/hire").json()
    held = [h for s_ in hire.get("suppliers", []) for h in s_.get("items", []) if h.get("item_id") == item["id"]]
    ck("rental materials: on hire from the supplier", held and round(held[0]["qty"]) == 40, held[:1])
    stk = next((s_ for s_ in g("/store/stock").json() if s_["item_id"] == item["id"]), None)
    ck("stock: in the central store", stk is not None and round(stk.get("central", 0)) == 40, stk)
    rep = g("/store/report?kind=hired").json()
    ck("on-rent report lists it", any("XL Ledger" in str(r_.get("name", "")) for r_ in rep.get("rows", [])))

    # ---- 11. An increment corrected, then removed -> everywhere back --------------------
    cid = inc[0]["id"] if inc else None
    if cid:
        r = c.delete(f"/employees/increments/{cid}", headers=H)
        ck("increment removed", r.status_code == 200, r.text[:120])
        back = P()["person"]
        ck("staff file: allowance back where it was", round(back["allowance"], 2) == round(before["allowance"], 2), (back["allowance"], before["allowance"]))
        reg = next(r for r in g("/employees/staff").json()["rows"] if r["emp_no"] == code)
        ck("staff register: back too", round(reg["allowance"], 2) == round(before["allowance"], 2), reg["allowance"])

    # ---- tidy up the loan so the database is as it was for money ------------------------
    if lid:
        c.delete(f"/employees/loans/{lid}", headers=H)

print("\n" + ("ENTERED ONCE, SEEN EVERYWHERE" if not bad else f"{bad} FAILED"))

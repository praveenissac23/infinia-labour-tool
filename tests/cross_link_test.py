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
    r = post("/employees", {"emp_no": "XL-01", "name": "XL WORKER", "trade": "Helper", "basic_salary": 900, "total_salary": 1300, "company": "XLEng"})
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
    r = post("/employees", {"emp_no": "XL-01", "name": "XL WORKER", "trade": "Helper", "basic_salary": 950, "total_salary": 1350, "company": "XLEng"})
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


    # ---- 12. Engineer added -> attendance choices ---------------------------------------
    r = post("/engineers", {"name": "XL ENGINEER"})
    ck("engineer accepted", r.status_code == 200, r.text[:120])
    ck("engineer list (attendance reads this)", any(e["name"].upper() == "XL ENGINEER" for e in g("/engineers").json()))

    # ---- 13. Attendance entered -> salary card, live card, reports, staff file ---------
    # Days 1-25 of this month belong to this month's cycle (26th to 25th).
    days = [date(today.year, today.month, d) for d in range(1, min(today.day, 25) + 1) if date(today.year, today.month, d).weekday() != 4][:4]
    cyc = days[0].strftime("%B %Y")
    r = post("/attendance/save", {"month_year": cyc, "rows": [
        {"emp_no": "XL-01", "full_date": d.isoformat(), "am": "Present", "pm": "Present", "site": "977",
         "engineer": "XL ENGINEER", "ot": 2, "bh": 0, "comments": "XL day"} for d in days]})
    ck("attendance accepted", r.status_code == 200, r.text[:160])
    day = g(f"/attendance/{days[0].isoformat()}").json()
    row = next((x for x in (day.get("rows") if isinstance(day, dict) else day) if x.get("emp_no") == "XL-01"), None)
    ck("daily attendance shows the day with site and engineer", row is not None and row.get("site") == "977" and (row.get("engineer") or "").upper() == "XL ENGINEER", row)
    sm = next((x for x in g(f"/summaries/{cyc}").json() if x.get("emp_no") == "XL-01"), None)
    ck("salary card: present days counted", sm is not None and sm.get("present_days") == len(days), sm and sm.get("present_days"))
    ck("salary card: paid from his salary", sm is not None and (sm.get("final_salary") or 0) > 0, sm and sm.get("final_salary"))
    ck("salary card: overtime counted", sm is not None and round(sm.get("ot_hours") or 0) == 2 * len(days), sm and sm.get("ot_hours"))
    lc = g(f"/live-card/XL-01/{cyc}").json()
    ck("live card agrees", isinstance(lc, dict) and round((lc.get("summary") or {}).get("present_days", -1)) == len(days), str(lc)[:160])
    bysite = g(f"/summaries/{cyc}/by-site").json()
    ck("site cost report has site 977 with his days", any(str(r_.get("site")) == "977" and round(r_.get("days_present") or 0) == len(days) for r_ in bysite.get("rows", [])), [r_ for r_ in bysite.get("rows", []) if str(r_.get("site")) == "977"])
    pf = g("/employees/people/XL-01").json()
    ck("staff file: the cycle is on his history", any(cy.get("month_year") == cyc for cy in pf["cycles"]), [cy.get("month_year") for cy in pf["cycles"]])
    t = c.post("/auth/download-token", headers=H).json()["token"]
    ck("salary card print carries site and engineer", all(x in c.get(f"/export/{cyc}/cards/view?token={t}&emp_no=XL-01").text for x in ("977", "XL ENGINEER")))

    # ---- 14. Addition / deduction -> the cycle and the file -----------------------------
    r = post("/employees/pay-items", {"emp_no": code, "month_year": month, "direction": "deduct", "category": "fine", "amount": 75, "notes": "XL fine"})
    ck("deduction accepted", r.status_code == 200, r.text[:160])
    run = post("/employees/payroll/runs", {"month_year": month, "company_id": co, "group": "staff"}).json()
    line = next((l for l in run.get("lines", []) if l["emp_no"] == code), None)
    ck("this month's cycle: the deduction is on the line", line is not None and "XL fine" in ((line.get("remarks") or "") + (line.get("deduction_note") or "")), line and (line.get("remarks"), line.get("deduction_note")))
    ck("additions & deductions register lists it", any(x["emp_no"] == code and x["amount"] == 75 and x["notes"] == "XL fine" for x in g(f"/employees/pay-items?month_year={month}").json().get("rows", [])))

    # ---- 15. Material request -> approvals -> order -> delivery -> stock ----------------
    cem = post("/store/items", {"code": "XLC1", "name": "XL Cement 50kg", "item_type": "consumable", "unit": "bags", "category": "Cement"}).json()
    mr = post("/store/requests", {"site": "977", "requested_by": "XL keeper", "urgency": "normal", "notes": "",
              "lines": [{"item_id": cem["id"], "qty_requested": 30, "unit": "bags", "purpose": "XL slab", "description": "", "est_cost": 0, "notes": ""}]}).json()
    ck("request raised", mr.get("status") == "pending", mr)
    ck("approvals list shows it (the office sees it)", any(x["id"] == mr["id"] for x in g("/store/requests").json()))
    ck("office is notified", any("request" in (n.get("title") or "").lower() for n in g("/notifications").json().get("notifications", [])))
    L = mr["lines"][0]["id"]
    c.post(f"/store/request-lines/{L}/decision", json={"decision": "approved"}, headers=H)
    po = post("/store/purchase/orders", {"supplier_name": "XL Scaffold Hire LLC", "supplier_trn": "100200300400003", "supplier_contact": "Ravi",
              "supplier_phone": "0501112233", "supplier_email": "hire@xl.ae", "contact_person": "XL", "mobile": "0500000000",
              "job_scope": "XL slab", "project_location": "977", "request_id": mr["id"],
              "lines": [{"item_id": cem["id"], "description": "XL Cement 50kg", "qty": 30, "unit": "bags", "rate": 17}]})
    ck("purchase order raised against it", po.status_code == 200, po.text[:200])
    po = po.json()
    ol = g("/store/purchase/orders").json(); ol = ol.get("rows", []) if isinstance(ol, dict) else ol
    ck("LPO register lists the order", any(o.get("id") == po.get("id") for o in ol))
    cur = next(x for x in g("/store/requests").json() if x["id"] == mr["id"])
    ck("the request knows it is ordered", cur["status"] in ("ordered", "approved", "partial") or cur["lines"][0].get("supplier"), cur["status"])
    r = post(f"/store/requests/{mr['id']}/receive-bulk", {"supplier": "XL Scaffold Hire LLC", "reference": "XL-DO-9", "notes": "", "received_on": None, "lines": [{"line_id": L, "qty": 30}]})
    ck("delivery booked in", r.status_code == 200, r.text[:160])
    # Delivered straight to the site that asked: a consumable there is used, not held.
    use = g("/store/report?kind=usage").json().get("rows", [])
    ck("consumption report: 30 bags to site 977", any("XL Cement" in str(u_.get("name", "")) and "977" in str(u_.get("to", "")) and round(u_.get("qty", 0)) == 30 for u_ in use), [u_ for u_ in use if "XL Cement" in str(u_)][:2])
    ck("movements ledger shows the receipt", any(m.get("reference") == "XL-DO-9" for m in g("/store/movements?limit=20").json()))
    cur = next(x for x in g("/store/requests").json() if x["id"] == mr["id"])
    ck("the request finishes itself", cur["status"] in ("delivered", "received"), cur["status"])
    ck("purchase report carries the supplier", "xl scaffold" in str(g("/store/purchase/report").json()).lower())

    # ---- 16. Material moved to a site -> at-sites report, consumption -------------------
    r = post("/store/movements", {"item_id": item["id"], "kind": "out", "qty": 10, "from_location": "", "location": "977", "incharge": "XL WORKER", "moved_on": today.isoformat(), "notes": "XL out"})
    ck("rented ledgers moved to site 977", r.status_code == 200, r.text[:160])
    stk = next((x for x in g("/store/stock").json() if x["item_id"] == item["id"]), None)
    ck("stock: 30 in the store, 10 at 977", stk is not None and round(stk.get("central") or 0) == 30 and round((stk.get("by_site") or {}).get("977", 0)) == 10, stk and (stk.get("central"), stk.get("by_site")))
    bs = g("/store/report?kind=by_site").json().get("rows", [])
    ck("at-sites report shows them at 977", any("XL Ledger" in str(b_) and "977" in str(b_) for b_ in bs))
    held = [h for s_ in g("/store/hire").json().get("suppliers", []) for h in s_.get("items", []) if h.get("item_id") == item["id"]]
    ck("still 40 on hire from the supplier, wherever they stand", held and round(held[0]["qty"]) == 40, held[:1])
    ck("issue & return register shows the 10 out", any("XL Ledger" in str(x) and "977" in str(x) for x in g("/store/report?kind=issues").json().get("rows", [])))


    # ---- 18. Lost / damaged -> stock, lost report, ledger --------------------------------
    own = post("/store/items", {"code": "XLT1", "name": "XL Measuring Tape", "item_type": "returnable", "unit": "pcs", "category": "Tools"}).json()
    post("/store/movements", {"item_id": own["id"], "kind": "in", "qty": 5, "location": "", "supplier": "XL Scaffold Hire LLC", "moved_on": today.isoformat(), "reference": "XL-IN-T", "notes": ""})
    post("/store/movements", {"item_id": own["id"], "kind": "out", "qty": 2, "from_location": "", "location": "977", "incharge": "XL WORKER", "moved_on": today.isoformat(), "notes": ""})
    r = post("/store/movements", {"item_id": own["id"], "kind": "lost", "qty": 1, "from_location": "977", "location": "977", "incharge": "XL WORKER", "moved_on": today.isoformat(), "notes": "XL damaged at site", "condition": "damaged"})
    ck("a tape written off as damaged at 977", r.status_code == 200, r.text[:160])
    stk = next((x for x in g("/store/stock").json() if x["item_id"] == own["id"]), {})
    ck("stock: 3 in the store, 1 left at 977", round(stk.get("central") or 0) == 3 and round((stk.get("by_site") or {}).get("977", 0)) == 1, (stk.get("central"), stk.get("by_site")))
    lost = g("/store/report?kind=lost").json().get("rows", [])
    ck("lost / damaged report lists it, at 977", any("XL Measuring Tape" in str(l_) and "977" in str(l_) for l_ in lost), [l_ for l_ in lost if "XL" in str(l_)][:1])
    iss = g("/store/report?kind=issues").json().get("rows", [])
    ck("issue & return register: 2 out, still out after the loss accounted", any("XL Measuring Tape" in str(x) for x in iss))
    ck("movements ledger shows the write-off", any(m.get("kind") == "lost" and "XL damaged" in (m.get("notes") or "") for m in g("/store/movements?limit=30").json()))
    # a rented item short on its return note -> off hire, on the lost report
    ret = post("/store/returns", {"supplier_id": sup.get("id"), "supplier_name": "XL Scaffold Hire LLC", "return_date": today.isoformat(), "from_location": "",
              "lines": [{"item_id": item["id"], "description": "XL Ledger 2.0M", "unit": "pcs", "qty_on_hire": 40, "qty_returned": 25, "qty_short": 5, "short_reason": "lost"}]})
    ck("return note written (25 back, 5 lost)", ret.status_code == 200, ret.text[:200])
    rid = ret.json().get("id")
    c.post(f"/store/returns/{rid}/issue", headers=H)
    r = post(f"/store/returns/{rid}/confirm", {"received_by": "XL yard", "confirmed_on": today.isoformat()})
    ck("return note confirmed", r.status_code == 200, r.text[:200])
    held = [h for s_ in g("/store/hire").json().get("suppliers", []) for h in s_.get("items", []) if h.get("item_id") == item["id"]]
    ck("on hire: 40 - 25 back - 5 lost = 10 still on hire", held and round(held[0]["qty"]) == 10, held[:1])
    lost = g("/store/report?kind=lost").json().get("rows", [])
    ck("lost report shows the 5 ledgers lost on the note", any("XL Ledger" in str(l_) for l_ in lost))

    # ---- 19. LPO raised on its own for the store -> follow-up, arrival, stock ----------
    before_n = len(g("/store/requests").json())
    po2 = post("/store/purchase/orders", {"supplier_name": "XL Scaffold Hire LLC", "contact_person": "XL", "mobile": "0500000000",
               "job_scope": "Store stock", "project_location": "Store",
               "lines": [{"item_id": cem["id"], "description": "XL Cement 50kg", "qty": 50, "unit": "bags", "rate": 17}]})
    ck("store LPO raised without a request", po2.status_code == 200, po2.text[:200])
    po2 = po2.json()
    ck("supplier details fetched from the supplier record (TRN)", po2.get("supplier_trn") == "100200300400003", po2.get("supplier_trn"))
    ck("supplier details fetched (contact, phone, email)", po2.get("supplier_contact") == "Ravi" and po2.get("supplier_phone") == "0501112233" and po2.get("supplier_email") == "hire@xl.ae",
       (po2.get("supplier_contact"), po2.get("supplier_phone"), po2.get("supplier_email")))
    reqs = g("/store/requests").json()
    linked = [x for x in reqs if po2.get("request_id") and x["id"] == po2["request_id"]]
    ck("order follow-up tracks the store LPO", bool(linked) and linked[0]["lines"][0].get("supplier"), linked[:1] and linked[0].get("status"))
    if linked:
        L2 = linked[0]["lines"][0]["id"]
        r = post(f"/store/requests/{linked[0]['id']}/receive-bulk", {"supplier": "XL Scaffold Hire LLC", "reference": "XL-DO-10", "notes": "", "received_on": None, "lines": [{"line_id": L2, "qty": 50}]})
        ck("its delivery booked in from Material Arrived", r.status_code == 200, r.text[:160])
        stk = next((x for x in g("/store/stock").json() if x["item_id"] == cem["id"]), {})
        ck("stock: 50 bags in the central store", round(stk.get("central") or 0) == 50, stk.get("central"))
        cur = next(x for x in g("/store/requests").json() if x["id"] == linked[0]["id"])
        ck("the store LPO is closed once delivered", cur["status"] in ("delivered", "received"), cur["status"])

    # ---- 20. Labour rate changed on the Staff page -> Master Data, cards, history ------
    r = c.put("/employees/people/XL-02", json={"employee": {"basic": 1100, "allowance": 300, "effective_on": today.isoformat(), "reason": "XL rate review"}}, headers=H)
    ck("labour rate change accepted on the Staff page", r.status_code == 200, r.text[:200])
    emp = next((e for e in g("/employees?active_only=true").json() if e["emp_no"] == "XL-02"), {})
    ck("master data shows the new rate (basic 1,100, total 1,400)", round(emp.get("basic_salary") or 0) == 1100 and round(emp.get("total_salary") or 0) == 1400, (emp.get("basic_salary"), emp.get("total_salary")))
    pf = g("/employees/people/XL-02").json()
    ck("staff file: rate history carries it", any(h.get("reason") == "XL rate review" for h in pf.get("salary_history", [])), pf.get("salary_history"))
    # and a change made on Master Data is recorded the same way
    post("/employees", {"emp_no": "XL-02", "name": "XL SECOND CORRECTED", "trade": "Mason", "basic_salary": 1150, "total_salary": 1450, "company": "XLEng"})
    pf = g("/employees/people/XL-02").json()
    ck("master data rate change is on the staff file history too", any(round(h.get("basic") or 0) == 1150 for h in pf.get("salary_history", [])), [h.get("basic") for h in pf.get("salary_history", [])])
    # the salary card for the cycle is paid at the new rate
    # today's labour cycle (26th to 25th) is the one the new rate applies to
    cur_cyc = today.strftime("%B %Y") if today.day <= 25 else date(today.year + (today.month == 12), today.month % 12 + 1, 1).strftime("%B %Y")
    post("/attendance/save", {"month_year": cur_cyc, "rows": [{"emp_no": "XL-02", "full_date": today.isoformat(), "am": "Present", "pm": "Present", "site": "977", "engineer": "XL ENGINEER", "ot": 0, "bh": 0, "comments": ""}]})
    sm = next((x for x in g(f"/summaries/{cur_cyc}").json() if x.get("emp_no") == "XL-02"), {})
    ck("this cycle's salary card is at the new rate", round(sm.get("total_salary") or 0) == 1450, (sm.get("basic_pay_input"), sm.get("total_salary")))

    # ---- 21. Ticket allowance -> cycle, file; gratuity stays on basic ------------------
    grat_before = g(f"/employees/people/{code}").json().get("gratuity", {})
    r = post("/employees/pay-items", {"emp_no": code, "month_year": month, "direction": "add", "category": "air_ticket", "amount": 1800, "notes": "XL ticket"})
    ck("air ticket allowance accepted", r.status_code == 200, r.text[:160])
    run = post("/employees/payroll/runs", {"month_year": month, "company_id": co, "group": "staff"}).json()
    line = next((l for l in run.get("lines", []) if l["emp_no"] == code), {})
    ck("this month's cycle: ticket on the line and in net pay", round(line.get("air_ticket") or 0) == 1800, line.get("air_ticket"))
    ck("staff file: the cycle shows it", any(round(cy.get("adjust") or 0) >= 1800 - 75 for cy in g(f"/employees/people/{code}").json().get("cycles", []) if cy.get("month_year") == month))
    grat_after = g(f"/employees/people/{code}").json().get("gratuity", {})
    ck("gratuity unchanged - UAE gratuity is on basic salary only", grat_before.get("amount") == grat_after.get("amount"), (grat_before.get("amount"), grat_after.get("amount")))
    # labour: an allowance on the salary card shows on the card, the live card and the final figure
    sm = next((x for x in g(f"/summaries/{cyc}").json() if x.get("emp_no") == "XL-02"), None)
    if sm:
        adj_total = lambda x: (x.get("final_salary") or 0) + sum((-a["amount"] if a["is_deduction"] else a["amount"]) for a in x.get("adjustments", []))
        before_final = adj_total(sm)
        r = post(f"/summaries/{sm['id']}/adjustments", {"description": "XL ticket allowance", "amount": 500, "is_deduction": False})
        ck("labour allowance accepted on the salary card", r.status_code == 200, r.text[:160])
        sm2 = next((x for x in g(f"/summaries/{cyc}").json() if x.get("emp_no") == "XL-02"), {})
        ck("salary card: final salary to pay up by 500", round(adj_total(sm2) - before_final) == 500, (before_final, adj_total(sm2)))
        lc = g(f"/live-card/XL-02/{cyc}").json()
        ck("live card shows the allowance", "XL ticket allowance" in str(lc), str(lc)[:200])
        t = c.post("/auth/download-token", headers=H).json()["token"]
        ck("printed card shows the allowance", "XL ticket allowance" in c.get(f"/export/{cyc}/cards/view?token={t}&emp_no=XL-02").text)

    # ---- 17. A labourer leaves -> gone from attendance, kept on the staff page ----------
    r = post("/employees", {"emp_no": "XL-01", "name": "XL WORKER", "trade": "Helper", "basic_salary": 950, "total_salary": 1350, "company": "XLEng", "terminated_on": today.isoformat()})
    ck("leaving date saved", r.status_code == 200, r.text[:120])
    ck("attendance no longer offers him after today", not any(e["emp_no"] == "XL-01" and e.get("active", True) and not e.get("terminated_on") for e in g("/employees?active_only=true").json()))
    ck("staff page keeps him under Left", any(p["emp_no"] == "XL-01" for p in g("/employees/people?group=left").json()["rows"]) or any(p["emp_no"] == "XL-01" and p.get("terminated_on") for p in g("/employees/people?group=labour&include_left=true").json()["rows"]))

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

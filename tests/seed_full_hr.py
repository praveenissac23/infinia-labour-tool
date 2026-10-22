"""HR / People / Documents part of the full, live-like database (see seed_full.py).

Everything goes in through the app's own API, the way the office would type it:
companies, office + local staff with their files, pay items, absences and leave spells,
loans and repayments, increments (office and labour), the office payroll (September
approved, October open and paid as a full month), documents with expiries for staff and
labour, company expiries and renewals, assets, birthday contacts, the labour camp, the
PPE register and the site-to-office document transmittals.

    run(c, H)    c: an entered fastapi TestClient, H: admin auth headers

Dates are written for "today" = 22 Oct 2026 (Dubai). Labour attendance and the labour
cards already in the base database are not touched (a labour increment recalculates that
labourer's cards, which is what the app does).
"""
import random
from datetime import date, timedelta

TODAY = date(2026, 10, 22)
C = H = None
LOG = []


class SeedError(RuntimeError):
    pass


def call(method, path, body=None, params=None, ok=(200,)):
    r = C.request(method, path, json=body, params=params, headers=H)
    if r.status_code not in ok:
        msg = f"{method} {path} -> {r.status_code}: {r.text[:600]}\n   body: {str(body)[:400]}"
        print("!! " + msg)
        raise SeedError(msg)
    try:
        return r.json()
    except ValueError:
        return r.text


def iso(d):
    return d.isoformat()


def d_(s):
    return date.fromisoformat(s)


# ---------------------------------------------------------------- people
# code, name, designation, company key, joined, basic, allowance, route, extra
STAFF = [
    ("IC101", "Arathi Menon", "Accountant", "INF", "2021-03-14", 4000, 6000, "wps", {}),
    ("IC102", "Rahul Nair", "Quantity Surveyor", "INF", "2022-07-01", 5200, 7800, "wps", {}),
    ("IC103", "Fathima Beevi", "HR & Admin Officer", "INF", "2023-01-09", 3200, 4800, "wps", {}),
    ("IC104", "Vinod Kumar", "Site Engineer", "INF", "2019-11-20", 6000, 9000, "wps", {}),
    ("IC105", "Deepa Thomas", "Receptionist", "INF", "2025-12-01", 1800, 2700, "wps",
     {"probation_end": "2026-05-31"}),
    ("IC106", "Sajid Khan", "Office Driver", "INF", "2020-05-05", 1200, 1800, "cash", {}),
    ("IC107", "Merin Jose", "Estimation Engineer", "INF", "2024-02-15", 4400, 6600, "wps", {}),
    ("IC108", "George Mathew", "Project Manager", "INF", "2016-04-01", 10000, 15000, "wps", {"notice_days": 90}),
    ("IC109", "Priya Sundar", "Admin Assistant", "ENG", "2024-09-10", 2400, 3600, "wps", {}),
    ("IC110", "Joseph Antony", "MEP Coordinator", "INF", "2026-10-12", 3600, 5400, "wps",
     {"probation_end": "2027-04-11"}),
]
LOCAL = [
    ("IC111", "Khalid Al Mansoori", "Government Relations Officer", "INF", "2018-02-01", 9000, 11000, 1125),
    ("IC112", "Maryam Al Hashimi", "Business Development Executive", "INF", "2022-06-15", 7000, 8000, 875),
]
PROFILES = {
    "IC101": dict(date_of_birth="1990-10-22", gender="Female", nationality="Indian", mobile="+971 50 412 7781",
                  department="Accounts", bank_name="ADCB", marital_status="Married", home_phone="+91 484 255 1190"),
    "IC102": dict(date_of_birth="1988-11-02", gender="Male", nationality="Indian", mobile="+971 55 298 3304",
                  department="Contracts", bank_name="Emirates NBD", home_phone="+91 471 233 8812"),
    "IC103": dict(date_of_birth="1993-04-18", gender="Female", nationality="Indian", mobile="+971 52 771 0045",
                  department="HR & Admin", bank_name="ADCB"),
    "IC104": dict(date_of_birth="1985-10-29", gender="Male", nationality="Indian", mobile="+971 50 655 2190",
                  department="Projects", bank_name="Mashreq", home_phone="+91 495 270 4410"),
    "IC105": dict(date_of_birth="1999-01-27", gender="Female", nationality="Filipino", mobile="+971 56 901 3378",
                  department="Front Office", bank_name="ADCB"),
    "IC106": dict(date_of_birth="1982-07-09", gender="Male", nationality="Pakistani", mobile="+971 50 118 9902",
                  department="Transport", accommodation="Company camp"),
    "IC107": dict(date_of_birth="1995-12-03", gender="Female", nationality="Indian", mobile="+971 54 330 7812",
                  department="Estimation", bank_name="RAKBANK"),
    "IC108": dict(date_of_birth="1978-11-15", gender="Male", nationality="Indian", mobile="+971 50 776 1123",
                  department="Projects", bank_name="Emirates NBD", leave_opening=12, leave_opening_on="2024-04-01"),
    "IC109": dict(date_of_birth="1997-06-21", gender="Female", nationality="Sri Lankan", mobile="+971 58 443 2290",
                  department="Admin", bank_name="ADCB"),
    "IC110": dict(date_of_birth="1991-02-11", gender="Male", nationality="Indian", mobile="+971 52 610 4471",
                  department="MEP", bank_name="ADCB"),
    "IC111": dict(date_of_birth="1984-10-30", gender="Male", nationality="Emirati", mobile="+971 50 300 1188",
                  department="Government Relations", bank_name="Abu Dhabi Islamic Bank"),
    "IC112": dict(date_of_birth="1996-03-08", gender="Female", nationality="Emirati", mobile="+971 50 422 9031",
                  department="Business Development", bank_name="Dubai Islamic Bank"),
}


# Workers given annual leave below: joined long enough ago (labour: 60 days per two years).
LONG_SERVING = {"F-707": "2019-10-02", "F-716": "2018-03-15", "F-775": "2020-01-20", "F-781": "2021-04-11",
                "F794": "2022-08-01", "F796": "2019-06-30", "F-740": "2023-02-05", "F-755": "2020-09-14"}


def iban(n):
    return f"AE{(n * 7919) % 90 + 10:02d}0{(n * 104729) % 10**9:09d}{(n * 15485863) % 10**11:011d}"[:23]


def seed_people(S):
    cos = {c["name"]: c for c in call("GET", "/employees/companies")}
    inf = call("POST", "/employees/companies", {"name": "INFINIA CONTRACTING L.L.C.", "short_name": "Infinia",
                                                  "code_prefix": "IC", "trn": "100456789200003",
                                                  "wps_id": "0000012345678", "address": "Al Quoz Industrial 3, Dubai, UAE"})
    eng = next(iter(cos.values()))
    S["co"] = {"INF": inf["id"], "ENG": eng["id"]}
    S["co_name"] = {"INF": inf["short_name"], "ENG": eng["short_name"]}
    n = 0
    for i, (code, name, desig, co, joined, basic, allow, route, extra) in enumerate(STAFF):
        body = {"group": "office", "emp_no": code, "name": name, "designation": desig, "company_id": S["co"][co],
                "joined_on": joined, "basic": basic, "allowance": allow, "pay_route": route,
                "iban": "" if route == "cash" else iban(i + 1), **extra}
        call("POST", "/employees/people", body); n += 1
    for i, (code, name, desig, co, joined, basic, allow, pension) in enumerate(LOCAL):
        call("POST", "/employees/people", {"group": "local", "emp_no": code, "name": name, "designation": desig,
                                           "company_id": S["co"][co], "joined_on": joined, "basic": basic,
                                           "allowance": allow, "pension": pension, "scheme": "pension",
                                           "pay_route": "wps", "iban": iban(50 + i)}); n += 1
    for code, prof in PROFILES.items():
        p = dict(prof)
        p.setdefault("work_email", code.lower() + "@infinia.ae")
        p.setdefault("employment_type", "unlimited")
        p.setdefault("emergency_name", "Family contact")
        p.setdefault("emergency_phone", "+971 50 000 " + code[-3:].rjust(4, "0"))
        call("PUT", f"/employees/people/{code}", {"profile": p})
    LOG.append(f"office/local staff: {n} added with profiles (companies Infinia #{inf['id']}, {eng['short_name']} #{eng['id']})")

    # Labour: give the long-serving gang joining dates (base DB has none), so service,
    # leave and gratuity can be worked out. Dates all before the two seeded cycles.
    lab = call("GET", "/employees/people", params={"group": "labour"})["rows"]
    S["labour"] = {r["emp_no"]: r for r in lab}
    rnd = random.Random(7)
    k = 0
    for r in lab:
        if r["emp_no"].startswith("T-"):
            continue                       # the scenario's joiners / leavers stay as they are
        y = rnd.choice([2017, 2019, 2020, 2021, 2022, 2023, 2024, 2025])
        j = date(y, rnd.randint(1, 12), rnd.randint(1, 28))
        if j > date(2026, 6, 1):
            j = date(2025, 6, 1)
        if r["emp_no"] in LONG_SERVING:          # those on the leave register have earned their leave
            j = d_(LONG_SERVING[r["emp_no"]])
        nat = rnd.choice(["Indian", "Indian", "Indian", "Pakistani", "Bangladeshi", "Nepali"])
        call("PUT", f"/employees/people/{r['emp_no']}",
             {"employee": {"joined_on": iso(j)},
              "profile": {"nationality": nat, "mobile": f"+971 5{rnd.randint(0, 8)} {rnd.randint(100, 999)} {rnd.randint(1000, 9999)}",
                          "accommodation": "Company camp, Al Quoz"}})
        S["labour"][r["emp_no"]]["joined_on"] = iso(j)
        k += 1
    LOG.append(f"labour: joining date + nationality set on {k} workers")


# ---------------------------------------------------------------- payroll inputs
def seed_increments(S):
    call("POST", "/employees/increments", {"emp_no": "IC104", "effective_on": "2026-08-01", "amount": 1000,
                                           "reason": "Annual increment 2026"})
    call("POST", "/employees/increments", {"emp_no": "IC101", "effective_on": "2026-10-01", "amount": 500,
                                           "to_basic": 200, "reason": "Performance review"})   # to_basic ignored: house rule
    call("POST", "/employees/increments", {"emp_no": "IC107", "effective_on": "2027-01-01", "amount": 750,
                                           "reason": "Agreed on confirmation, from January"})
    call("POST", "/employees/increments", {"emp_no": "IC111", "effective_on": "2026-09-01", "amount": 1500,
                                           "reason": "Housing allowance revision"})
    call("POST", "/employees/labour-increments", {"emp_no": "F-707", "amount": 150, "onto": "allowance",
                                                  "from": "this", "reason": "Skilled carpenter rate"})
    call("POST", "/employees/labour-increments", {"emp_no": "F-002", "amount": 100, "onto": "basic",
                                                  "from": "previous", "reason": "Foreman - agreed in September"})
    LOG.append("increments: 4 office (one dated 2027 = future), 2 labour")


SEPT_ITEMS = [
    ("IC101", "add", "taxi", 185.50, "Taxi bills - bank / municipality visits"),
    ("IC102", "add", "overtime", 650, "Tender submission weekend"),
    ("IC104", "add", "fees", 420, "DM inspection fees paid personally"),
    ("IC106", "deduct", "fine", 600, "Traffic fine - Sheikh Zayed Rd, Aug"),
    ("IC103", "deduct", "iloe", 5, ""),
    ("IC107", "deduct", "advance", 1000, "Salary advance taken 10 Sep"),
    ("IC108", "add", "bonus", 2500, "Handover bonus - Villa 920"),
    ("IC109", "add", "bills", 140, "Stationery"),
    ("IC111", "add", "fees", 1350, "Visa / typing fees paid"),
]
OCT_ITEMS = [
    ("IC101", "add", "bills", 230, "Courier & printing"),
    ("IC104", "add", "taxi", 312.75, ""),
    ("IC106", "deduct", "fine", 300, "Salik + parking fine"),
    ("IC102", "deduct", "iloe", 5, ""),
    ("IC108", "add", "other_add", 1200, "Mobile + fuel reimbursement"),
    ("IC107", "deduct", "damage", 250, "Lost site tablet charger + case"),
    ("IC109", "add", "taxi", 95, ""),
    ("IC112", "add", "bonus", 1000, "New client lead"),
]


def seed_pay_items(S, items, month):
    for code, direction, cat, amt, notes in items:
        call("POST", "/employees/pay-items", {"emp_no": code, "month_year": month, "direction": direction,
                                              "category": cat, "amount": amt, "notes": notes})
    LOG.append(f"pay items {month}: {len(items)}")


def seed_leave_september(S):
    call("POST", "/employees/leave", {"emp_no": "IC101", "kind": "sick", "from": "2026-09-08", "to": "2026-09-09",
                                      "certificate": True, "notes": "Fever - clinic note"})
    call("POST", "/employees/leave", {"emp_no": "IC103", "kind": "absent", "on_date": "2026-09-17", "half": True})
    call("POST", "/employees/leave", {"emp_no": "IC107", "kind": "unpaid", "from": "2026-09-21", "to": "2026-09-23",
                                      "notes": "Family function"})
    call("POST", "/employees/leave", {"emp_no": "IC106", "kind": "absent", "on_date": "2026-09-28"})
    call("POST", "/employees/leave", {"emp_no": "IC109", "kind": "holiday", "on_date": "2026-09-04",
                                      "notes": "Prophet's birthday (company holiday)"})
    LOG.append("absences September: 5 entries")


def seed_leave_october(S):
    call("POST", "/employees/leave", {"emp_no": "IC104", "kind": "vacation", "from": "2026-10-05", "to": "2026-10-18",
                                      "leave_salary": 16000, "notes": "Annual vacation - Kerala"})
    call("POST", "/employees/leave", {"emp_no": "IC105", "kind": "vacation", "from": "2026-10-14", "to": "2026-10-16",
                                      "leave_salary": 1500, "notes": "Asked as vacation"})   # first year -> unpaid
    call("POST", "/employees/leave", {"emp_no": "IC102", "kind": "holiday", "on_date": "2026-10-01"})
    call("POST", "/employees/leave", {"emp_no": "IC108", "kind": "sick", "on_date": "2026-10-20"})
    call("POST", "/employees/leave", {"emp_no": "IC103", "kind": "sick", "from": "2026-10-12", "to": "2026-10-13",
                                      "pay_rule": "paid", "certificate": True, "notes": "Marked paid by HR"})
    LOG.append("absences October: 5 entries (IC105 first-year vacation -> unpaid)")


def seed_leave_register(S):
    LR = [
        # staff spells
        {"emp_no": "IC107", "leave_type": "annual", "status": "approved", "leave_on": "2026-11-09", "approved_days": 21,
         "approved_by": "George Mathew", "remark": "Annual leave - Kochi", "home_phone": "+91 484 240 1122"},
        {"emp_no": "IC102", "leave_type": "annual", "status": "pending", "leave_on": "2026-12-20", "approved_days": 10,
         "remark": "Christmas"},
        {"emp_no": "IC108", "leave_type": "annual", "status": "returned", "leave_on": "2026-07-01", "return_on": "2026-07-31",
         "approved_by": "Managing Partner", "remark": "Summer leave"},
        # labour spells (labour have no absence register - the grid is theirs)
        {"emp_no": "F-707", "leave_type": "annual", "status": "returned", "leave_on": "2026-06-01", "return_on": "2026-07-31",
         "approved_by": "Vinod Kumar"},
        {"emp_no": "F-716", "leave_type": "annual", "status": "approved", "leave_on": "2026-10-01", "return_on": "2026-11-30",
         "approved_by": "Vinod Kumar", "remark": "60 days - 2 yr completed", "home_phone": "+91 612 222 4410"},
        {"emp_no": "F-775", "leave_type": "annual", "status": "approved", "leave_on": "2026-08-15", "return_on": "2026-10-15",
         "approved_by": "Vinod Kumar", "remark": "Not back yet"},
        {"emp_no": "F-781", "leave_type": "annual", "status": "approved", "leave_on": "2026-11-05", "approved_days": 60,
         "approved_by": "Vinod Kumar"},
        {"emp_no": "F794", "leave_type": "emergency", "status": "approved", "leave_on": "2026-10-10", "return_on": "2026-10-24",
         "approved_by": "George Mathew", "remark": "Father hospitalised"},
        {"emp_no": "F796", "leave_type": "annual", "status": "pending", "leave_on": "2027-01-10", "approved_days": 45},
        {"emp_no": "F-740", "leave_type": "sick", "status": "returned", "leave_on": "2026-09-02", "return_on": "2026-09-06"},
        {"emp_no": "F-755", "leave_type": "annual", "status": "cancelled", "leave_on": "2026-10-28", "approved_days": 30,
         "remark": "Postponed - project handover"},
    ]
    S["lr"] = {}
    for x in LR:
        r = call("POST", "/employees/people/leave-register", x)
        S["lr"][x["emp_no"]] = r["id"]
    LOG.append(f"leave register: {len(LR)} spells (staff + labour: away, overdue, upcoming, pending, returned, cancelled)")


def seed_loans_before_sept(S):
    L = {}
    L["IC106"] = call("POST", "/employees/loans", {"emp_no": "IC106", "amount": 6000, "taken_on": "2026-05-10",
                                                   "instalment": 1000, "terms": "6 months from June", "paid_from": "Cash",
                                                   "notes": "Family emergency"})["id"]
    call("POST", f"/employees/loans/{L['IC106']}/repay", {"amount": 1000, "paid_on": "2026-07-31", "month_year": "July 2026",
                                                         "source": "cash", "notes": "Handed in cash"})
    call("POST", f"/employees/loans/{L['IC106']}/repay", {"amount": 1000, "paid_on": "2026-08-31", "month_year": "August 2026",
                                                         "source": "cash"})
    L["IC103"] = call("POST", "/employees/loans", {"emp_no": "IC103", "amount": 3000, "taken_on": "2026-08-01",
                                                   "instalment": 500, "terms": "500 a month", "paid_from": "ADCB"})["id"]
    L["IC102"] = call("POST", "/employees/loans", {"emp_no": "IC102", "amount": 2000, "taken_on": "2026-03-01",
                                                   "instalment": 500, "paid_from": "ADCB"})["id"]
    call("POST", f"/employees/loans/{L['IC102']}/repay", {"amount": 1500, "paid_on": "2026-06-30", "source": "settlement",
                                                         "notes": "Bonus set against the loan"})
    L["IC109"] = call("POST", "/employees/loans", {"emp_no": "IC109", "amount": 1500, "taken_on": "2026-09-15",
                                                   "instalment": 0, "paid_from": "petty", "terms": "To be agreed"})["id"]
    S["loans"] = L
    LOG.append("loans: 4 before September (cash + settlement repayments)")


def seed_payroll(S):
    inf, eng = S["co"]["INF"], S["co"]["ENG"]
    sept = call("POST", "/employees/payroll/runs", {"month_year": "September 2026", "company_id": inf, "group": "staff"})
    sept_l = call("POST", "/employees/payroll/runs", {"month_year": "September 2026", "company_id": inf, "group": "local"})
    eng_sept = call("POST", "/employees/payroll/runs", {"month_year": "September 2026", "company_id": eng, "group": "staff"})
    S["runs"] = {"sept": sept["id"], "sept_local": sept_l["id"], "eng_sept": eng_sept["id"]}
    S["pre_approve"] = {"sept": sept, "sept_local": sept_l, "eng_sept": eng_sept}
    call("PUT", f"/employees/payroll/runs/{sept['id']}", {"notes": "September salaries - WPS 01 Oct"})
    for k in ("sept", "sept_local", "eng_sept"):
        call("POST", f"/employees/payroll/runs/{S['runs'][k]}/approve")
    LOG.append("payroll September 2026: Infinia office + local + Enginova approved")


def seed_loans_after_sept(S):
    S["loans"]["IC101"] = call("POST", "/employees/loans", {"emp_no": "IC101", "amount": 5000, "taken_on": "2026-10-05",
                                                            "instalment": 1250, "terms": "4 months Oct-Jan",
                                                            "paid_from": "ADCB", "notes": "School fees"})["id"]
    LOG.append("loans: IC101 5,000 taken in October")


def seed_october_runs(S):
    inf, eng = S["co"]["INF"], S["co"]["ENG"]
    call("POST", "/employees/payroll/full-month", {"month_year": "October 2026", "group": "staff", "on": True})
    oct_ = call("POST", "/employees/payroll/runs", {"month_year": "October 2026", "company_id": inf, "group": "staff"})
    oct_l = call("POST", "/employees/payroll/runs", {"month_year": "October 2026", "company_id": inf, "group": "local"})
    eng_o = call("POST", "/employees/payroll/runs", {"month_year": "October 2026", "company_id": eng, "group": "staff"})
    S["runs"].update({"oct": oct_["id"], "oct_local": oct_l["id"], "eng_oct": eng_o["id"]})
    # On the sheet itself: Sajid pays half his instalment this month (fine taken too).
    ln = next(l for l in oct_["lines"] if l["emp_no"] == "IC106")
    call("PUT", f"/employees/payroll/runs/{oct_['id']}",
         {"lines": [{"id": ln["id"], "loan_deduction": 500, "remarks": "Half instalment agreed - fine deducted this month"}],
          "notes": "October - paid as full month (holiday on 1 Nov)"})
    LOG.append("payroll October 2026: Infinia office (full month on, one instalment changed) + local + Enginova, left open")


# ---------------------------------------------------------------- documents
VALID_YEARS = {"passport": 10, "eid": 2, "visa": 2, "labour_card": 2, "insurance": 1, "medical": 2}


def _offset(rnd, idx):
    """Most later; some expired, some within 30 days, some within 90."""
    roll = idx % 20
    if roll in (0, 7):
        return -rnd.randint(1, 75)          # expired
    if roll in (3, 11):
        return rnd.randint(0, 30)           # urgent
    if roll in (5, 15):
        return rnd.randint(31, 90)          # soon
    return rnd.randint(91, 720)


def seed_documents(S):
    rnd = random.Random(2026)
    idx, n = 0, 0
    staff_codes = [s[0] for s in STAFF]
    for code in staff_codes + [x[0] for x in LOCAL]:
        kinds = ["passport", "eid", "insurance"] if code in ("IC111", "IC112") else \
            ["passport", "eid", "visa", "labour_card", "insurance", "medical"]
        for k in kinds:
            off = _offset(rnd, idx); idx += 1
            exp = TODAY + timedelta(days=off)
            iss = exp.replace(year=exp.year - VALID_YEARS[k]) + timedelta(days=1)
            num = {"passport": f"{'U' if code != 'IC105' else 'P'}{rnd.randint(1000000, 9999999)}",
                   "eid": f"784-{rnd.randint(1975, 2000)}-{rnd.randint(1000000, 9999999)}-{rnd.randint(1, 9)}",
                   "visa": f"201/2025/{rnd.randint(1000000, 9999999)}", "labour_card": f"{rnd.randint(10000000, 99999999)}",
                   "insurance": f"DHA-{rnd.randint(100000, 999999)}", "medical": f"MF{rnd.randint(100000, 999999)}"}[k]
            call("POST", "/employees/documents", {"emp_no": code, "kind": k, "number": num, "issued_on": iso(iss),
                                                  "expires_on": iso(exp)})
            n += 1
    # Labour: every long-serving worker, every document - plus the scenario's leaver / joiner.
    labs = [c for c in sorted(S["labour"]) if not c.startswith("T-")] + ["T-901", "T-902", "T-904"]
    for code in labs:
        for k in ("passport", "eid", "visa", "labour_card", "insurance", "medical"):
            if code == "T-904" and k in ("visa", "labour_card"):
                continue                        # new joiner, visa still in process -> "missing"
            off = _offset(rnd, idx); idx += 1
            exp = TODAY + timedelta(days=off)
            iss = exp.replace(year=exp.year - VALID_YEARS[k]) + timedelta(days=1)
            call("POST", "/employees/documents", {"emp_no": code, "kind": k, "number": f"{k[:2].upper()}{rnd.randint(100000, 999999)}",
                                                  "issued_on": iso(iss), "expires_on": iso(exp),
                                                  "notes": "Renewal with PRO" if off < 0 else ""})
            n += 1
    # Custom kinds, typed by name.
    call("POST", "/employees/documents", {"emp_no": "IC104", "kind": "custom", "kind_label": "Civil Defence card",
                                          "number": "CD-77812", "expires_on": "2027-03-31"}); n += 1
    call("POST", "/employees/documents", {"emp_no": "IC106", "kind": "driving", "number": "DL 2231987",
                                          "expires_on": "2026-11-04"}); n += 1
    call("POST", "/employees/documents", {"emp_no": "D-01", "kind": "driving", "number": "DL 1190023",
                                          "expires_on": "2026-10-19"}); n += 1
    # Labour contract kept on the People file (same record as the contract document).
    call("PUT", "/employees/people/IC103", {"profile": {"contract_no": "MOHRE-ST-55120", "contract_expiry": "2026-11-30"}})
    LOG.append(f"documents: {n} posted (+1 contract via People file)")


EXPIRIES = [
    ("Trade licence", "Infinia Contracting L.L.C. - DED trade licence", "Trade licence", "CN-1123456", "2025-11-14", 23),
    ("Establishment card", "Infinia - immigration establishment card", "Establishment card", "2/6/123456", "2024-12-01", -5),
    ("Vehicle", "Toyota Hilux - Dubai P 41823", "Registration (Mulkiya)", "P 41823", "2025-11-01", 10),
    ("Vehicle", "Toyota Hilux - Dubai P 41823", "Insurance", "MOT-2291188", "2025-11-01", 10),
    ("Vehicle", "Nissan Urvan - Dubai K 77310", "Registration (Mulkiya)", "K 77310", "2026-01-20", 90),
    ("Vehicle", "Mitsubishi Canter - Dubai J 22014", "Registration (Mulkiya)", "J 22014", "2025-08-15", -68),
    ("Vehicle", "Toyota Prado - Dubai R 9090", "Registration (Mulkiya)", "R 9090", "2026-04-02", 162),
    ("Insurance", "Workmen's compensation - all labour", "Insurance", "WC/2026/00871", "2026-01-01", 70),
    ("Insurance", "Contractor's All Risk - Villa 909", "Insurance", "CAR-909-2026", "2026-02-10", 210),
    ("Tenancy / Ejari", "Labour camp - Al Quoz 4 (rooms 49-65)", "Tenancy contract", "EJ-0987123", "2025-12-15", 54),
    ("Tenancy / Ejari", "Head office - Al Quoz Industrial 3", "Tenancy contract", "EJ-0765432", "2026-03-01", 130),
    ("Certificate / approval", "Civil Defence - contractor approval", "Civil Defence NOC", "DCD-CT-4412", "2025-09-30", 343),
    ("Certificate / approval", "Dubai Municipality contractor classification", "Contractor classification", "DM-G4-3321", "2026-06-30", 251),
    ("Site / project", "Sobha Hartland VE278 - developer access", "Access pass", "SH-AP-278", "2026-09-01", 2),
    ("Other", "Chamber of Commerce membership", "Chamber of Commerce", "DCCI-554120", "2025-10-20", -2),
]


def seed_expiries(S):
    S["expiry_ids"] = []
    for cat, item, kind, num, issued, off in EXPIRIES:
        r = call("POST", "/employees/expiries", {"category": cat, "item": item, "kind": kind, "number": num,
                                                 "issued_on": issued, "expires_on": iso(TODAY + timedelta(days=off))})
        S["expiry_ids"].append(r["id"])
    LOG.append(f"company expiries: {len(EXPIRIES)}")


def seed_renewals(S):
    """The Expiry Reminder page: two renewals marked started, one closed with its new date."""
    docs = call("GET", "/employees/documents")["rows"]
    visa = next(d for d in docs if d["kind"] in ("visa", "labour_card", "eid") and d["status"] == "urgent")
    call("POST", "/employees/expiry/started", {"type": "person", "id": visa["id"], "on": True})
    exp_co = next(x for x in call("GET", "/employees/expiries")["rows"] if x["status"] == "expired")
    call("POST", "/employees/expiry/started", {"type": "company", "id": exp_co["id"], "on": True})
    pp = next(d for d in docs if d["kind"] == "passport" and d["status"] == "expired")
    new = d_(pp["expires_on"]).replace(year=d_(pp["expires_on"]).year + 10)
    call("POST", "/employees/expiry/close", {"type": "person", "id": pp["id"], "dates": {str(pp["id"]): iso(new)}})
    S["renewed_passport"] = (pp["emp_no"], iso(new))
    call("POST", "/employees/expiry/mail", {"to": "engineers@infinia.ae, hr@infinia.ae"})
    LOG.append(f"expiry reminder: visa renewal started ({visa['emp_no']}), company item started ({exp_co['item']}), "
               f"passport {pp['emp_no']} renewed to {iso(new)}")


# ---------------------------------------------------------------- assets, birthdays
def seed_assets(S):
    A = [
        ("IC101", {"item": "Laptop - Dell Latitude 5440", "tag": "INF-IT-031", "issued_on": "2024-01-08", "condition": "Good"}),
        ("IC102", {"item": "Laptop - Lenovo ThinkPad E14", "tag": "INF-IT-027", "issued_on": "2022-07-01", "condition": "Fair"}),
        ("IC107", {"item": "Laptop - HP ProBook 450", "tag": "INF-IT-040", "issued_on": "2024-02-15", "condition": "Good"}),
        ("IC104", {"item": "Mobile - Samsung A54 + SIM 050 655 2190", "tag": "INF-MB-012", "issued_on": "2023-05-01"}),
        ("IC108", {"item": "Company car - Toyota Prado R 9090", "tag": "INF-VH-004", "issued_on": "2021-09-12",
                   "notes": "Fuel card FC-8812"}),
        ("IC108", {"item": "Mobile - iPhone 14 + SIM", "tag": "INF-MB-003", "issued_on": "2023-01-10"}),
        ("IC106", {"item": "Vehicle - Nissan Urvan K 77310 (keys)", "tag": "INF-VH-007", "issued_on": "2020-05-05"}),
        ("IC111", {"item": "Laptop - MacBook Air M2", "tag": "INF-IT-035", "issued_on": "2023-06-01"}),
        ("F-002", {"item": "Laser level - Bosch GLL 3-80", "tag": "INF-TL-118", "issued_on": "2026-03-10", "condition": "Good"}),
    ]
    ids = []
    for code, body in A:
        ids.append(call("POST", f"/employees/people/{code}/assets", body)["id"])
    old = call("POST", "/employees/people/IC103/assets", {"item": "Laptop - Dell Vostro (old)", "tag": "INF-IT-012",
                                                           "issued_on": "2023-01-09", "condition": "Worn"})
    call("PUT", f"/employees/people/assets/{old['id']}", {"returned_on": "2026-08-20", "condition": "Returned - battery weak",
                                                          "notes": "Replaced by INF-IT-044"})
    call("POST", "/employees/people/IC103/assets", {"item": "Laptop - Dell Latitude 3540", "tag": "INF-IT-044",
                                                     "issued_on": "2026-08-20", "condition": "New"})
    LOG.append(f"assets: {len(A) + 2} issued (1 returned)")


def seed_birthdays(S):
    B = [("Sunit Jain", "Client", "IC/916", "1975-10-25"), ("Arunkumar Jain", "Client", "IC/928", "1979-11-03"),
         ("Dharmesh Birla", "Client", "GA46", "1981-02-14"), ("Mrs. Asif", "Client's family", "", "1988-10-22")]
    for name, rel, prj, dob in B:
        call("POST", "/employees/people/birthday-contacts", {"name": name, "relation": rel, "project_no": prj,
                                                              "date_of_birth": dob})
    LOG.append(f"birthday contacts: {len(B)}")


# ---------------------------------------------------------------- camp
def seed_camp(S):
    camp = call("GET", "/store/camp")             # loads the 9 Oct allocation sheet into the empty camp
    rooms = {r["name"]: r for r in camp["rooms"]}
    call("POST", "/store/camp/room", {"name": "64", "beds": 6})
    call("POST", "/store/camp/room", {"name": "65", "beds": 4})
    call("POST", "/store/camp/room", {"name": "49", "beds": 8})       # two more bunks in 49
    camp = call("GET", "/store/camp")
    rooms = {r["name"]: r for r in camp["rooms"]}
    nobed = [p for p in camp["nobed"] if not p["no"].startswith("T-")]
    free = [(r["id"], b["bed"], r["name"]) for r in camp["rooms"] for b in r["beds"] if b["kind"] == "free"]
    n = 0
    for p, (rid, bed, rname) in zip(nobed[:10], free):
        call("POST", "/store/camp/assign", {"room_id": rid, "bed": bed, "employee_id": p["id"]}); n += 1
    camp = call("GET", "/store/camp")
    rooms = {r["name"]: r for r in camp["rooms"]}
    free = [(r["id"], b["bed"], r["name"]) for r in camp["rooms"] for b in r["beds"] if b["kind"] == "free"]
    (r1, b1, _), (r2, b2, _), (r3, b3, _), (r4, b4, _) = free[:4]
    call("POST", "/store/camp/book", {"room_id": r1, "bed": b1, "name": "Suresh Yadav", "trade": "Mason", "date": "2026-10-28"})
    call("POST", "/store/camp/book", {"room_id": r2, "bed": b2, "name": "Imran Ali", "trade": "Steel fixer", "date": "2026-10-15"})
    call("POST", "/store/camp/guest", {"room_id": r3, "bed": b3, "name": "Subcontractor driver - Ali Raza"})
    # A move: the first worker in room 63 goes to a free bed in 64.
    r63 = rooms["63"]
    w = next(b for b in r63["beds"] if b["kind"] in ("in", "vac"))
    call("POST", "/store/camp/assign", {"room_id": r4, "bed": b4, "employee_id": w["emp_id"]})
    # A guest leaves: Sayed (room 55 bed 1) moved out.
    call("POST", "/store/camp/free", {"room_id": rooms["55"]["id"], "bed": 1, "reason": "Moved to own accommodation"})
    S["camp_moves"] = {"assigned": n, "booked": 2, "guest": 1, "moved": w["no"]}
    LOG.append(f"camp: rooms 64/65 added, 49 -> 8 beds, {n} workers given beds, 2 bookings, 1 guest, 1 move, 1 freed")


# ---------------------------------------------------------------- PPE
def seed_ppe(S):
    lab = S["labour"]
    ids = {k: v["id"] for k, v in lab.items()}
    rnd = random.Random(11)
    hist = []
    codes = [c for c in sorted(lab) if not c.startswith("T-")]
    # History (before today's count): handed out Jul - Oct.
    for i, code in enumerate(codes[:45]):
        d0 = date(2026, 7, 1) + timedelta(days=rnd.randint(0, 100))
        hist.append({"employee_id": ids[code], "item": "Coverall", "size": rnd.choice(["M", "L", "XL", "XXL"]), "qty": 2,
                     "date": iso(d0), "site": rnd.choice(["Villa 909", "Villa 920", "VE278"]), "source": "Store"})
        if i % 3 == 0:
            hist.append({"employee_id": ids[code], "item": "Safety Shoes", "size": str(rnd.randint(40, 45)), "qty": 1,
                         "date": iso(d0 + timedelta(days=rnd.randint(0, 20))), "source": "Store"})
        if i % 4 == 0:
            hist.append({"employee_id": ids[code], "item": "Helmet", "size": rnd.choice(["Yellow", "White"]), "qty": 1,
                         "date": iso(min(d0 + timedelta(days=3), TODAY - timedelta(days=1))), "source": "Store"})
    # A quick repeat: same coverall again 12 days later (worn out on the slab pour).
    hist.append({"employee_id": ids["F-723"], "item": "Coverall", "size": "L", "qty": 1, "date": "2026-10-01", "source": "Store"})
    hist.append({"employee_id": ids["F-723"], "item": "Coverall", "size": "L", "qty": 1, "date": "2026-10-13",
                 "condition": "Replacement", "remarks": "Torn during slab pour", "source": "Store"})
    hist.append({"employee_id": ids["F-724"], "item": "Safety Shoes", "size": "42", "qty": 1, "date": "2026-10-20",
                 "condition": "Eligible", "remarks": "Approved - awaiting size 42"})
    for b in hist:
        if d_(b["date"]) >= TODAY:
            b["date"] = iso(TODAY - timedelta(days=1))
        call("POST", "/store/ppe", b)
    # Office stock: no count, a delivery on 1 Oct, given from the office since.
    call("POST", "/store/ppe/received", {"item": "Helmet", "location": "Office", "qty": 20, "date": "2026-10-01",
                                         "note": "PO-2026-0412"})
    office_given = 0
    for code in codes[50:55]:
        call("POST", "/store/ppe", {"employee_id": ids[code], "item": "Helmet", "size": "White", "qty": 1,
                                    "date": "2026-10-08", "source": "Office"}); office_given += 1
    # Store count today (sized for shoes / coveralls), then today's deliveries and issues.
    call("POST", "/store/ppe/stock", {"item": "Coverall", "location": "Store", "reorder": 15,
                                      "sizes": {"S": 4, "M": 18, "L": 22, "XL": 14, "XXL": 6, "XXXL": 2}})
    call("POST", "/store/ppe/stock", {"item": "Safety Shoes", "location": "Store", "reorder": 8,
                                      "sizes": {"38": 0, "39": 2, "40": 5, "41": 7, "42": 6, "43": 4, "44": 3, "45": 1, "46": 0}})
    call("POST", "/store/ppe/stock", {"item": "Helmet", "location": "Store", "counted": 35, "reorder": 10})
    call("POST", "/store/ppe/stock", {"item": "Safety Vest", "location": "Store", "counted": 4, "reorder": 10})
    call("POST", "/store/ppe/received", {"item": "Safety Shoes", "location": "Store", "date": iso(TODAY),
                                         "sizes": {"42": 6, "43": 6}, "note": "DN 88123"})
    call("POST", "/store/ppe/received", {"item": "Coverall", "location": "Store", "qty": 30, "date": iso(TODAY),
                                         "note": "Unsized bundle - to be sorted"})
    today_issues = [("F-724", "Safety Shoes", "42", 1), ("F-726", "Safety Shoes", "43", 1), ("F-727", "Coverall", "XL", 2),
                    ("F-728", "Coverall", "L", 2), ("F-729", "Helmet", "Yellow", 1), ("F-730", "Safety Vest", "XL", 1)]
    for code, item, size, qty in today_issues:
        call("POST", "/store/ppe", {"employee_id": ids[code], "item": item, "size": size, "qty": qty,
                                    "date": iso(TODAY), "source": "Store", "instructed_by": "Vinod Kumar"})
    S["ppe"] = {"hist": len(hist), "today": today_issues, "office_given": office_given}
    LOG.append(f"PPE: {len(hist)} past issues (1 eligible, 1 quick repeat), 4 store counts, 3 deliveries, "
               f"{len(today_issues) + office_given} issues after the counts")


# ---------------------------------------------------------------- docs to office
def seed_transmittals(S):
    T = [
        {"date": "2026-10-12", "from_site": "VILLA 909", "note": "Week 41 delivery notes",
         "lines": [{"description": "Gulf Buildmart Trading", "dn_no": "DN-44102", "site": "909", "date": "2026-10-09"},
                   {"description": "Star Steel Industries LLC", "dn_no": "SS/2231", "site": "909", "date": "2026-10-10"},
                   {"description": "Al Noor Readymix", "dn_no": "RMX-77801", "site": "909", "date": "2026-10-11",
                    "remarks": "Slab pour 42 m3"}]},
        {"date": "2026-10-17", "from_site": "VILLA 920",
         "lines": [{"description": "Gulf Buildmart Trading", "dn_no": "DN-44190", "site": "920", "date": "2026-10-15"},
                   {"description": "Emirates Blocks Factory", "dn_no": "EBF-9021", "site": "920", "date": "2026-10-16"}]},
        {"date": "2026-10-21", "from_site": "VE278",
         "lines": [{"description": "Delta Hardware & Tools", "dn_no": "DH-5512", "site": "VE278", "date": "2026-10-20"},
                   {"description": "Al Noor Readymix", "dn_no": "RMX-78022", "site": "VE278", "date": "2026-10-21"}]},
        {"date": "2026-10-22", "from_site": "VILLA 909", "note": "Sent with Amal",
         "lines": [{"description": "Star Steel Industries LLC", "dn_no": "SS/2290", "site": "909", "date": "2026-10-22"}]},
    ]
    ids = [call("POST", "/store/docs", t)["id"] for t in T]
    got = call("GET", "/store/docs")["rows"]
    by = {x["id"]: x for x in got}
    # 1: all received. 2: one paper missing. 3: received, then reopened. 4: still with the office.
    call("POST", f"/store/docs/{ids[0]}/receive", {"lines": [{"id": l["id"], "received": True} for l in by[ids[0]]["lines"]]})
    l2 = by[ids[1]]["lines"]
    call("POST", f"/store/docs/{ids[1]}/receive", {"lines": [{"id": l2[0]["id"], "received": True},
                                                             {"id": l2[1]["id"], "received": False}],
                                                   "note": "EBF-9021 not in the envelope"})
    call("POST", f"/store/docs/{ids[2]}/receive", {"lines": [{"id": l["id"], "received": True} for l in by[ids[2]]["lines"]]})
    call("POST", f"/store/docs/{ids[2]}/reopen")
    S["docs"] = ids
    LOG.append("docs to office: 4 transmittals (received / partial / reopened / sent)")


# ---------------------------------------------------------------- run
def run(c, h):
    global C, H
    C, H = c, h
    LOG.clear()
    S = {}
    steps = [seed_people, seed_increments,
             lambda S: seed_pay_items(S, SEPT_ITEMS, "September 2026"), seed_leave_september,
             seed_leave_register, seed_loans_before_sept, seed_payroll, seed_loans_after_sept,
             lambda S: seed_pay_items(S, OCT_ITEMS, "October 2026"), seed_leave_october, seed_october_runs,
             seed_documents, seed_expiries, seed_renewals, seed_assets, seed_birthdays,
             seed_camp, seed_ppe, seed_transmittals]
    for f in steps:
        f(S)
    # Summary from the app's own GETs.
    docs = call("GET", "/employees/documents")
    exp = call("GET", "/employees/expiries")
    runs = call("GET", "/employees/payroll/runs")["rows"]
    loans = call("GET", "/employees/loans")
    camp = call("GET", "/store/camp")["totals"]
    print("HR seed:")
    for line in LOG:
        print("  -", line)
    print(f"  documents: {len(docs['rows'])} tracked {docs['counts']}")
    print(f"  company expiries: {len(exp['rows'])} {exp['counts']}")
    for r in runs:
        print(f"  run #{r['id']} {r['company']} {r['month_year']} {r['group']}: {r['status']}, {r['lines']} lines, net {r['net_pay']:,.2f}")
    print(f"  loans: lent {loans['total_lent']:,.2f}, outstanding {loans['total_outstanding']:,.2f}")
    print(f"  camp: {camp}")
    return S


if __name__ == "__main__":
    print(__doc__)

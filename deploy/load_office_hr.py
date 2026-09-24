"""Put the office HR records on file - once - from the papers the accounts
office already keeps.

Run on the server, after the update is pulled and the service restarted:

    cd ~/infinia-labour-tool/app && ../venv/bin/python ../deploy/load_office_hr.py

What it loads, and where each figure comes from:

  * The two companies.                                  (LPO letterhead)
  * 20 office staff with joining dates, basic and allowance.
                                   (AUG 26 salary statement, signed)
  * Amal P K and Anoop Subramanian, who joined Prime in September.
                                   (salary increment file)
  * The 5 local and household staff, on their own statement.
                                   (SEP 26 local staff statement,
                                    document tracker)
  * Each person's salary history - joining figure and every increment.
                                   (salary increment file)
  * The two rises still to come: Shafeeq's 750 from September and
    Neethu's 1,000 from January 2027.
  * The four loans and what was recovered before August.
                                   (AUG 26 loan statement)
  * August's leave.                (AUG 26 leave details)
  * Emirates ID, visa and passport expiry for every office and local
    staff member, and for the labourers.
                                   (the two document trackers)
  * August 2026 for both companies, rebuilt and approved - but only if it
    comes out at the signed figures to the dirham. If it does not, the
    months are left as drafts and nothing is approved.

It takes a backup first, and it can be run again safely: anything already
on file is left as it is rather than added twice.
"""
import os, re, subprocess, sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))


def _find_database_url():
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    for unit in ("infinia", "infinia.service"):
        try:
            out = subprocess.run(["systemctl", "show", unit, "-p", "Environment", "--value"],
                                 capture_output=True, text=True, timeout=10).stdout
            m = re.search(r"DATABASE_URL=(\S+)", out or "")
            if m:
                return m.group(1)
            out = subprocess.run(["systemctl", "show", unit, "-p", "EnvironmentFiles", "--value"],
                                 capture_output=True, text=True, timeout=10).stdout
            for path in re.findall(r"(/\S+?)(?:\s|$)", out or ""):
                path = path.rstrip("()").lstrip("-")
                if os.path.exists(path):
                    for line in open(path):
                        if line.strip().startswith("DATABASE_URL="):
                            return line.split("=", 1)[1].strip().strip("'\"")
        except Exception:
            pass
    for env in (os.path.join(HERE, "..", ".env"), os.path.join(HERE, "..", "app", ".env")):
        if os.path.exists(env):
            for line in open(env):
                if line.strip().startswith("DATABASE_URL="):
                    return line.split("=", 1)[1].strip().strip("'\"")
    return None


_url = _find_database_url()
if not _url:
    sys.exit("Could not find DATABASE_URL. Run:  sudo systemctl show infinia -p Environment\n"
             "then run this again with it in front:\n"
             "  DATABASE_URL='...' ../venv/bin/python ../deploy/load_office_hr.py")
os.environ["DATABASE_URL"] = _url

import database, models  # noqa: E402
import main              # noqa: E402
from fastapi import HTTPException  # noqa: E402

main._add_missing_columns()
models.Base.metadata.create_all(database.engine)

AUG = "August 2026"
NOTES = []          # things the accountant should look at afterwards


def say(msg=""):
    print(msg, flush=True)


# ======================================================================
#  The figures
# ======================================================================

INFINIA = {"name": "INFINIA CONTRACTING L.L.C.", "short_name": "Infinia",
           "code_prefix": "IC", "trn": "100602393900003"}
PRIME = {"name": "PRIME INFINIA", "short_name": "Prime Infinia", "code_prefix": "PI"}

# code, name, company, designation, joined, basic, allowance, paid by,
# statement, scheme, monthly pension
STAFF = [
    ("IC001", "JOMON THOMAS",         "IC", "P.R.O",            "2022-08-22", 2600, 3900, "wps", "staff", "gratuity", 0),
    ("IC010", "AYSHA HIBA",           "IC", "Design",           "2024-07-19", 2800, 4200, "wps", "staff", "gratuity", 0),
    ("IC017", "ARATHI SAJEENDRAN",    "IC", "QS",               "2025-02-11", 3200, 4800, "wps", "staff", "gratuity", 0),
    ("IC019", "NEETHU TREESA JOSE",   "IC", "QS",               "2025-06-24", 2800, 4200, "wps", "staff", "gratuity", 0),
    ("IC020", "RAJASEKAR MUNIYAN",    "IC", "Project Engineer", "2025-06-09", 4800, 7200, "wps", "staff", "gratuity", 0),
    ("IC022", "MOHAMED SHAFEEQ",      "IC", "Accounts",         "2025-09-01", 2800, 4200, "wps", "staff", "gratuity", 0),
    ("IC023", "AKHIL R",              "IC", "Project Engineer", "2025-12-11", 4400, 6600, "wps", "staff", "gratuity", 0),
    ("IC024", "FEBIYANS LUCAS",       "IC", "Project Engineer", "2025-12-19", 4000, 6000, "wps", "staff", "gratuity", 0),
    ("IC025", "PREENU ANNIE DANIEL",  "IC", "QS",               "2026-03-14", 2000, 3000, "wps", "staff", "gratuity", 0),
    # Paid in cash; the statement gives them no staff code, so these are ours.
    ("IC101", "PREM RAJ",             "IC", "Staff (cash)",     "2025-09-08", 12000, 0, "cash", "staff", "gratuity", 0),
    ("IC102", "MATHEW GEORGE",        "IC", "Staff (cash)",     "2026-06-18", 2500, 0, "cash", "staff", "gratuity", 0),
    # Remuneration by bank transfer; no codes or joining dates on the sheet.
    ("IC201", "SHAJI MATHEW",         "IC", "Project Director", "", 20000, 0, "bank", "staff", "gratuity", 0),
    ("IC202", "NAVEEN MATHEW SHAJI",  "IC", "Manager",          "", 40000, 0, "bank", "staff", "gratuity", 0),
    ("IC203", "PRAVEEN ISSAC SHAJI",  "IC", "Manager",          "", 40000, 0, "bank", "staff", "gratuity", 0),
    # Prime Infinia.
    ("PI001", "SHYJU THOMAS",         "PI", "Site Supervisor",  "2026-06-01", 2000, 3000, "wps", "staff", "gratuity", 0),
    ("PI002", "SYED ABDUL REHIM",     "PI", "Junior Engineer",  "2026-07-13", 1600, 2400, "wps", "staff", "gratuity", 0),
    ("PI003", "SREEKANTH R",          "PI", "Purchase",         "2026-07-22", 2700, 4050, "wps", "staff", "gratuity", 0),
    ("PI004", "MUHSINA PALERI",       "PI", "Admin",            "2026-08-01", 1200, 1800, "wps", "staff", "gratuity", 0),
    ("PI005", "AMAL P K",             "PI", "Communication Asst", "2026-09-10", 1200, 1800, "wps", "staff", "gratuity", 0),
    ("PI006", "ANOOP SUBRAMANIAN",    "PI", "Senior QS",        "2026-09-15", 5600, 8400, "wps", "staff", "gratuity", 0),
    # The local statement: nationals on GPSSA, and the household staff.
    ("IC015", "KHADIJA FARIS ABDULLA", "IC", "Local staff",     "2024-12-01", 2400, 3600, "wps", "local", "pension", 700),
    ("IC018", "AYA ADIL",             "IC", "Local staff",      "2025-06-23", 2400, 3600, "wps", "local", "pension", 1175),
    ("IC026", "SARA ADIL",            "IC", "Local staff",      "2026-06-17", 2400, 3600, "wps", "local", "pension", 1410),
    ("IC008", "RAJI MOL",             "IC", "Maid",             "", 0, 0, "wps", "local", "gratuity", 0),
    ("IC028", "SARASWATHI",           "IC", "Maid",             "", 0, 0, "wps", "local", "gratuity", 0),
]

# Salary history from the increment file: the joining gross, then each
# rise as (month, amount). Every figure on the statements is split 40/60,
# so each past step is recorded that way. Rises still to come are below.
HISTORY = {
    "IC001": (3800, [("2024-01-01", 200), ("2024-05-01", 500), ("2024-11-01", 500),
                     ("2025-08-01", 500), ("2026-05-01", 1000)]),
    "IC010": (4000, [("2025-07-01", 1500), ("2025-08-01", 500), ("2026-08-01", 1000)]),
    "IC017": (6000, [("2025-08-01", 500), ("2026-04-01", 1500)]),
    "IC019": (6000, [("2026-07-01", 1000)]),
    "IC020": (10000, [("2026-07-01", 2000)]),
}
# Agreed and not yet reached in August. Recorded after August is closed,
# through the increment screen's own rule: onto the allowance, basic kept.
FUTURE_RISES = [("IC022", "2026-09-01", 750, "Increment Sep-26 (increment file)"),
                ("IC019", "2027-01-01", 1000, "Increment Jan-27 (increment file)")]

# emp, amount, date, terms, monthly, recovered before August
LOANS = [
    ("IC001", 55000, "2022-08-22", "Reimbursement through Pettycash", 0, 33000),
    ("IC022", 12000, "2025-09-01", "Reimbursement monthly 3000 each", 3000, 3000),
    ("PI002", 1000,  "2026-07-13", "Monthly 500 reimbursement", 500, 0),
    ("PI003", 3000,  "2026-07-22", "Monthly 500 reimbursement", 500, 0),
]

LEAVE = [   # emp, date, half day?, paid?, reason
    ("IC017", "2026-08-14", True,  False, "Sick"),
    ("IC017", "2026-08-26", True,  True,  "Onam - half day off"),
    ("IC019", "2026-08-15", False, True,  "Sick"),
    ("IC020", "2026-08-18", False, True,  "Sick"),
    ("IC020", "2026-08-24", False, False, "Absent"),
    ("IC025", "2026-08-18", False, True,  "Sick"),
    ("IC025", "2026-08-24", False, False, "Sick"),
    ("IC010", "2026-08-25", False, True,  "Sick"),
    ("IC101", "2026-08-08", True,  True,  "Sick - 2 hrs"),
    ("IC101", "2026-08-29", False, False, "Absent"),
    ("PI002", "2026-08-20", False, True,  "Sick"),
    ("PI002", "2026-08-21", False, False, "Sick"),
    ("PI003", "2026-08-15", False, True,  "Sick"),
    ("PI003", "2026-08-27", True,  False, "Sick"),
    ("PI004", "2026-08-24", False, True,  "Sick"),
]

# What only August knew: bills, leave salary, tickets, the ILOE premium -
# entered in the additions register, as they will be every month.
AUG_ITEMS = [   # emp, add/deduct, category, amount, note
    ("IC001", "add", "leave_salary", 7000, ""), ("IC001", "add", "air_ticket", 500, ""),
    ("IC010", "add", "taxi", 1228.00, "Taxi Bills"), ("IC017", "add", "taxi", 328.00, "Taxi Bills"),
    ("IC019", "add", "taxi", 315.50, "Taxi Bills"), ("IC020", "add", "fees", 241.50, "SOE Fee 241.50"),
    ("IC022", "add", "leave_salary", 7000, ""), ("IC025", "add", "taxi", 195.50, "Taxi Bills"),
    ("PI001", "deduct", "iloe", 126.00, "ILOE DEDUCTION"),
]
# The remarks as the signed statements word them.
AUG_REMARKS = {
    "IC001": "Leave salary & Air Ticket", "IC010": "Taxi Bills", "IC017": "Taxi Bills",
    "IC019": "Taxi Bills", "IC020": "SOE Fee 241.50", "IC022": "Leave salary & Loan Reimbursement",
    "IC025": "Taxi Bills", "IC101": "BY CASH", "IC102": "BY CASH",
    "IC201": "Project Director's remuneration", "IC202": "Manager's remuneration",
    "IC203": "Manager's remuneration", "PI001": "ILOE DEDUCTION",
}
SIGNED = {"Infinia": {"wps": 86609.50, "bank": 100000.00, "cash": 14100.00},
          "Prime Infinia": {"wps": 17378.50}}

# Office document tracker: code, EID, visa / labour card, passport.
OFFICE_DOCS = [
    ("IC001", "2028-08-23", "2028-08-28", "2035-12-22"),
    ("IC010", "2027-10-06", "2028-07-19", "2030-11-20"),
    ("IC015", "2028-07-02", "2026-12-19", "2028-05-08"),
    ("IC017", "2027-03-10", "2027-03-10", "2029-08-15"),
    ("IC018", "2033-09-02", "2027-06-23", "2027-02-02"),
    ("IC019", "2027-06-29", "2027-06-29", "2031-09-02"),
    ("IC020", "2027-08-03", "2027-08-03", "2034-10-28"),
    ("IC022", "2027-11-17", "2027-11-17", "2033-01-29"),
    ("IC023", "2028-02-01", "2028-02-01", "2035-10-14"),
    ("IC024", "2028-02-03", "2028-02-03", "2034-09-19"),
    ("IC025", "2028-03-22", "2028-03-22", "2032-01-06"),
    ("IC008", "2028-01-21", "2028-01-21", "2033-09-11"),
    ("IC026", "2028-09-09", "2028-06-17", "2027-01-03"),
    ("IC028", "2028-07-22", "2028-07-22", "2033-12-03"),
    ("PI001", "2028-06-03", "2028-06-03", "2036-01-04"),
    ("PI002", "2028-07-23", "2028-07-23", "2033-04-23"),
    ("PI003", "2028-08-14", "2028-08-14", "2035-09-16"),
    ("PI004", "2027-11-17", "2028-08-03", "2033-03-01"),
    ("PI005", "2028-09-15", "2028-09-09", "2033-08-15"),
    ("PI006", "2028-09-18", "2028-09-13", "2027-06-20"),
]

# Labour document tracker, matched to the labour list by name.
LABOUR_DOCS = [
    # name as on the tracker, company, EID expiry, labour card expiry, passport expiry, remark
    ('M0HAMED SALIM', 'INFINIA', '2027-01-21', '2027-01-10', '2032-11-24', ''),
    ('MUHAMMED USMAN', 'INFINIA', '2026-11-19', '2026-11-14', '2032-01-16', ''),
    ('AHMAD ALI', 'INFINIA', '2028-03-02', '2028-01-29', '2032-08-08', ''),
    ('RAM BRIKSH SHYAM RAJ', 'INFINIA', '2027-07-31', '2027-07-29', '2036-03-17', ''),
    ('BARSATI', 'INFINIA', '2027-03-07', '2027-03-04', '2026-09-27', 'RENEWED'),
    ('RAJENDRA SINGH', 'INFINIA', '2027-05-18', '2027-05-13', '2035-01-26', ''),
    ('SAMARJEET SINGH', 'INFINIA', '2027-04-06', '2027-03-29', '2031-04-13', ''),
    ('LAKHWINDER SINGH', 'INFINIA', '2027-10-07', '2027-10-07', '2028-03-14', ''),
    ('SHIV CHARAN', 'INFINIA', '2028-06-21', '2028-06-18', '2029-07-24', ''),
    ('AVINAS PASWAN', 'INFINIA', '2028-07-02', '2028-06-29', '2033-04-02', ''),
    ('ABID', 'INFINIA', '2028-07-06', '2028-07-03', '2027-01-24', ''),
    ('SATYA DEV', 'INFINIA', '2028-08-23', '2028-08-28', '2033-08-27', ''),
    ('DILSHAD KHAN', 'INFINIA', '2028-09-14', '2026-09-13', '2034-03-06', 'RENEWED'),
    ('AJAY KUMAR', 'INFINIA', '2028-09-14', '2026-09-13', '2031-08-31', 'RENEWED'),
    ('SOMARY PRASAD', 'INFINIA', '2028-09-14', '2026-09-13', '2026-11-16', 'RENEWED'),
    ('BENCHEP OLIVER KARNGONG', 'INFINIA', '2026-10-14', '2026-10-07', '2027-02-17', ''),
    ('DIWAKAR', 'INFINIA', '2026-10-14', '2026-10-10', '2034-01-04', ''),
    ('PRADEEP', 'INFINIA', '2026-10-14', '2026-10-12', '2031-04-20', ''),
    ('PARDUM', 'INFINIA', '2026-10-14', '2026-10-12', '2029-10-08', ''),
    ('CHHANU MAHATO', 'INFINIA', '2026-10-18', '2026-10-15', '2028-11-21', ''),
    ('VIJAY KUMAR SINGH', 'INFINIA', '2026-12-09', '2026-12-07', '2032-05-12', ''),
    ('BHIM BAHADUR', 'INFINIA', '2027-01-19', '2026-12-06', '2035-12-18', ''),
    ('DILIP KUMAR CHAUDHARY', 'INFINIA', '2026-12-10', '2026-12-06', '2034-02-22', ''),
    ('MONIR', 'INFINIA', '2026-12-12', '2026-12-16', '2026-12-07', ''),
    ('MUNNA KUMAR YADAV', 'INFINIA', '2027-01-20', '2026-12-19', '2028-04-30', ''),
    ('DEEPAK PUN MAGAR', 'INFINIA', '2027-01-20', '2026-12-30', '2031-01-21', ''),
    ('LATIF ANSARI', 'INFINIA', '2027-01-20', '2026-12-30', '2033-01-02', ''),
    ('GUDDU KUMAR', 'INFINIA', '2027-02-18', '2027-02-11', '2030-04-22', ''),
    ('RAMPRAVESH', 'INFINIA', '2027-02-18', '2027-02-11', '2036-05-28', ''),
    ('JITENDRA KUMAR', 'INFINIA', '2027-03-23', '2027-03-16', '2031-08-25', ''),
    ('RAVI RAYI', 'INFINIA', '2027-03-26', '2027-03-24', '2027-10-09', ''),
    ('CHANDAN KUMAR', 'INFINIA', '2027-05-04', '2027-04-15', '2035-01-28', ''),
    ('SANDEEP KUMAR', 'INFINIA', '2027-05-03', '2027-04-15', '2034-04-23', ''),
    ('HARISHANKAR', 'INFINIA', '2027-05-02', '2027-04-16', '2027-03-30', ''),
    ('DIP KUMAR', 'INFINIA', '2027-05-04', '2027-05-02', '2027-03-27', ''),
    ('HARERAM', 'INFINIA', '2027-05-02', '2027-04-19', '2034-04-17', ''),
    ('SANJAY KUMAR', 'INFINIA', '2027-05-02', '2027-04-29', '2035-03-17', ''),
    ('NANDLAL', 'INFINIA', '2027-05-18', '2027-05-05', '2030-12-28', ''),
    ('DHARAM PAL', 'INFINIA', '2027-08-15', '2027-08-11', '2036-05-13', ''),
    ('SANTHOSH', 'INFINIA', '2027-09-16', '2027-09-16', '2035-04-18', ''),
    ('SOM BAHADUR', 'INFINIA', '2027-09-28', '2027-09-25', '2035-05-06', ''),
    ('GANESH KUMAR', 'INFINIA', '2027-09-25', '2027-09-25', '2035-07-07', ''),
    ('MOHAMMAD ZUBAIR ALAM', 'INFINIA', '2027-09-30', '2027-09-30', '2032-12-04', ''),
    ('MOHAMMAD RAJID', 'INFINIA', '2027-09-30', '2027-09-30', '2028-07-29', ''),
    ('MECHHAFA', 'INFINIA', '2027-05-11', '2027-05-11', '2029-11-21', ''),
    ('SAFIKUL MONDAL', 'INFINIA', '2027-05-11', '2027-05-11', '2036-08-24', ''),
    ('RAMESH KUMAR', 'INFINIA', '2027-11-12', '2027-11-12', '2033-03-22', ''),
    ('RAM NATH', 'INFINIA', '2027-12-30', '2027-12-30', '2035-08-25', ''),
    ('IMTYAJ ALI', 'INFINIA', '2027-11-20', '2027-11-24', '2032-07-12', ''),
    ('DANIEL', 'INFINIA', '2027-11-26', '2027-11-27', '2032-03-30', ''),
    ('SANDEEP YADAV', 'INFINIA', '2027-04-12', '2027-04-12', '2032-12-13', ''),
    ('MUNTAZIR ALAM', 'INFINIA', '2027-03-12', '2027-03-12', '2035-10-15', ''),
    ('SAJANPREET SINGH', 'INFINIA', '2027-09-12', '2027-09-12', '2035-09-10', ''),
    ('AKASH MAHTO', 'INFINIA', '2027-12-16', '2027-12-16', '2035-07-31', ''),
    ('CHRIS CHAZIMA ANDAMBI', 'INFINIA', '2028-01-13', '2028-01-13', '2031-11-01', ''),
    ('PETER MUNENE', 'INFINIA', '2028-02-27', '2028-02-27', '2035-10-02', ''),
    ('PHILIP MAINA', 'INFINIA', '2028-02-27', '2028-02-27', '2034-03-13', ''),
    ('CHUNNA ALAM', 'INFINIA', '2028-03-11', '2028-11-03', '2035-09-23', ''),
    ('ABDULA MATIN', 'INFINIA', '2028-03-11', '2028-11-03', '2036-01-20', ''),
    ('MD MINTO', 'INFINIA', '2028-03-11', '2028-11-03', '2033-09-18', ''),
    ('AZAD ALAM', 'INFINIA', '2028-03-11', '2028-11-03', '2035-12-16', ''),
    ('SHAMSHER SINGH', 'INFINIA', '2028-03-11', '2028-11-03', '2032-08-04', ''),
    ('RAJMAN KUMAR', 'INFINIA', '2028-03-11', '2028-11-03', '2035-08-10', ''),
    ('FALVDAR', 'PRIME', '2028-04-22', '2028-04-22', '2034-07-24', ''),
    ('AMANDEEP SINGH', 'PRIME', '2028-06-21', '2028-06-08', '2030-01-20', ''),
    ('ABHISHEK', 'PRIME', '2028-10-06', '2028-06-10', '2035-03-25', ''),
    ('SURESH CHAMAR', 'PRIME', '2028-06-15', '2028-06-11', '2031-03-08', ''),
    ('MOHAN KUMAR', 'PRIME', '2028-06-15', '2028-08-11', '2035-01-16', ''),
    ('ARUN YADAV', 'PRIME', '2028-07-18', '2028-07-14', '2036-03-09', ''),
    ('JAYA PRAKASH', 'PRIME', '2028-07-28', '2028-07-24', '2028-09-26', ''),
    ('MIRAJUL ANSARI', 'PRIME', '2028-07-28', '2028-07-24', '2034-06-27', ''),
    ('PALDURAI PICHAI', 'PRIME', '2028-08-18', '2028-08-12', '2036-07-08', ''),
]


# ======================================================================
#  Loading
# ======================================================================

def split(gross):
    basic = round(gross * 0.4, 2)
    return basic, round(gross - basic, 2)


def call(fn, *a, **kw):
    """Run one of the app's own endpoints, turning a refusal into text."""
    try:
        return fn(*a, **kw), None
    except HTTPException as e:
        return None, str(e.detail)


def has_doc(db, emp_no, kind):
    """Already on file - in which case the app's date stands. A renewal
    entered on the screen must not be put back to the tracker's date by
    running this a second time."""
    return (db.query(models.EmployeeDocument)
              .join(models.Employee, models.Employee.id == models.EmployeeDocument.employee_id)
              .filter(models.Employee.emp_no == emp_no,
                      models.EmployeeDocument.kind == kind).first() is not None)


def main_load():
    db = database.SessionLocal()
    admin = (db.query(models.User).filter(models.User.role == "admin")
               .order_by(models.User.id).first())
    if not admin:
        sys.exit("No admin login on this server - nothing was changed.")

    # ---- A clash with the labour list stops everything ----------------
    codes = [s[0] for s in STAFF]
    clash = [e for e in db.query(models.Employee).filter(models.Employee.emp_no.in_(codes)).all()
             if not e.staff]
    if clash:
        say("These staff codes are already used by labourers, so nothing was loaded:")
        for e in clash:
            say(f"   {e.emp_no}  {e.name}")
        sys.exit("Tell Claude which codes to use instead.")

    # ---- Backup first -------------------------------------------------
    db.add(models.Backup(created_by=admin.id, trigger="manual",
                         data=main._backup_dump(main.build_backup_data(db))))
    db.commit()
    say("Backup taken (Settings > Backups, marked manual).")

    # ---- Companies ----------------------------------------------------
    ic, _ = call(main.save_company, dict(INFINIA), db=db, user=admin)
    pi, _ = call(main.save_company, dict(PRIME), db=db, user=admin)
    co = {"IC": ic, "PI": pi}
    say(f"Companies: {ic['name']}, {pi['name']}")

    # ---- Staff --------------------------------------------------------
    added = kept = 0
    for (code, name, c, desig, joined, basic, allow, route, group, scheme, pension) in STAFF:
        e = db.query(models.Employee).filter(models.Employee.emp_no == code).first()
        if e:
            kept += 1
            continue
        e = models.Employee(emp_no=code, name=name, trade=desig, pay_type="fixed",
                            staff=True, active=True)
        db.add(e); db.commit()
        payload = {"company_id": co[c]["id"], "designation": desig, "pay_route": route,
                   "pay_group": group, "scheme": scheme, "pension": pension,
                   "contract_basic": basic, "basic": basic, "allowance": allow}
        if joined:
            payload["joined_on"] = joined
        # Where the increment file gives a history, the history is written
        # first, so the joining figure is the real one and not today's.
        if code in HISTORY:
            payload.pop("joined_on", None)
        _, err = call(main.save_staff, code, payload, db=db, user=admin)
        if err:
            say(f"   {code}: {err}")
            continue
        if code in HISTORY:
            e = db.query(models.Employee).filter(models.Employee.emp_no == code).first()
            e.joined_on = date.fromisoformat(joined)
            start, rises = HISTORY[code]
            b, a = split(start)
            db.add(models.SalaryChange(employee_id=e.id, effective_on=e.joined_on,
                                       kind="joining", basic=b, allowance=a, amount=0,
                                       reason="On joining (increment file)",
                                       created_by=admin.id))
            gross = start
            for when, amt in rises:
                gross += amt
                b, a = split(gross)
                db.add(models.SalaryChange(employee_id=e.id,
                                           effective_on=date.fromisoformat(when),
                                           kind="increment", basic=b, allowance=a, amount=amt,
                                           reason="From the increment file", created_by=admin.id))
            db.commit()
            if (b, a) != (basic, allow):
                NOTES.append(f"{code}: the increment file ends at {b + a:,.2f} but August "
                             f"paid {basic + allow:,.2f} - check the history.")
        added += 1
    say(f"Staff: {added} added, {kept} already on file.")

    # ---- Loans --------------------------------------------------------
    have = {(l["emp_no"], l["amount"]) for l in main.list_loans(db=db, user=admin)["rows"]}
    for code, amt, when, terms, inst, before in LOANS:
        if (code, float(amt)) in have:
            continue
        l, err = call(main.add_loan, {"emp_no": code, "amount": amt, "taken_on": when,
                                      "terms": terms, "instalment": inst,
                                      "notes": "Date taken is not on the loan sheet - "
                                               "the joining date is used."},
                      db=db, user=admin)
        if err:
            say(f"   loan {code}: {err}")
            continue
        if before:
            db.add(models.LoanRepayment(loan_id=l["id"], amount=before,
                                        paid_on=date(2026, 7, 31), month_year="",
                                        source="opening"))
            db.commit()
    say("Loans: on file.")

    # ---- August leave -------------------------------------------------
    n = 0
    for code, on, half, paid, reason in LEAVE:
        _, err = call(main.add_leave, {"emp_no": code, "on_date": on, "half": half,
                                       "paid": paid, "reason": reason}, db=db, user=admin)
        n += 0 if err else 1
    say(f"Leave: {n} new day(s) recorded for August.")

    # ---- Documents ----------------------------------------------------
    n = 0
    for code, eid, visa, pp in OFFICE_DOCS:
        for kind, exp in (("eid", eid), ("visa", visa), ("passport", pp)):
            if exp and not has_doc(db, code, kind):
                _, err = call(main.save_document, {"emp_no": code, "kind": kind,
                                                   "expires_on": exp}, db=db, user=admin)
                n += 0 if err else 1
    say(f"Office documents: {n} new.")

    def norm(s):
        s = str(s or "").upper().replace("0", "O")
        return " ".join(re.sub(r"[^A-Z ]", " ", s).split())
    labour = [e for e in main._labour(db.query(models.Employee)).all()]
    by_name = {}
    for e in labour:
        by_name.setdefault(norm(e.name), []).append(e)
    matched, missing, stale = 0, [], []
    for name, company, eid, lcard, pp, remark in LABOUR_DOCS:
        key = norm(name)
        hits = by_name.get(key, [])
        if not hits:
            # The same words in another order, or one name held in full
            # and the other shortened - but only on two or more words in
            # common, and only if it points at one man. "Suresh" on the
            # labour list is not evidence enough to hang SURESH CHAMAR's
            # passport on him: a document on the wrong man is worse than
            # one left for the accountant to place by hand.
            words = set(key.split())
            hits = []
            for e in labour:
                theirs = set(norm(e.name).split())
                small = words if len(words) <= len(theirs) else theirs
                if len(small) >= 2 and (words <= theirs or theirs <= words):
                    hits.append(e)
        if len(hits) != 1:
            missing.append(f"{name} ({company})" + (" - several matches" if hits else ""))
            continue
        e = hits[0]
        for kind, exp in (("eid", eid), ("labour_card", lcard), ("passport", pp)):
            if exp and not has_doc(db, e.emp_no, kind):
                call(main.save_document, {"emp_no": e.emp_no, "kind": kind, "expires_on": exp,
                                          "notes": remark}, db=db, user=admin)
        if remark.upper() == "RENEWED":
            stale.append(f"{e.emp_no} {e.name}")
        matched += 1
    say(f"Labour documents: {matched} of {len(LABOUR_DOCS)} labourers matched by name.")
    if missing:
        NOTES.append("No labourer on file matches these tracker names, so their documents "
                     "were not loaded: " + "; ".join(missing))
    if stale:
        NOTES.append("Marked RENEWED on the tracker but the dates were never updated - enter "
                     "the new expiry under HR & Payroll > Documents: " + "; ".join(stale))

    # ---- August, rebuilt and checked ----------------------------------
    for code, d, cat, amt, note in AUG_ITEMS:
        e = db.query(models.Employee).filter(models.Employee.emp_no == code).first()
        if db.query(models.PayItem).filter(models.PayItem.employee_id == e.id,
                                           models.PayItem.month_year == AUG,
                                           models.PayItem.category == cat).first():
            continue
        call(main.add_pay_item, {"emp_no": code, "month_year": AUG, "direction": d,
                                 "category": cat, "amount": amt, "notes": note},
             db=db, user=admin)
    for key, c in (("Infinia", ic), ("Prime Infinia", pi)):
        run, err = call(main.open_payroll_run, {"month_year": AUG, "company_id": c["id"],
                                                "group": "staff"}, db=db, user=admin)
        if err:
            say(f"   August for {key}: {err}")
            continue
        if run["status"] == "approved":
            say(f"August for {key}: already approved.")
            continue
        by = {l["emp_no"]: l for l in run["lines"]}
        lines = [{"id": by[k]["id"], "remarks": v} for k, v in AUG_REMARKS.items() if k in by]
        run = main.save_payroll_run(run["id"], {"lines": lines}, db=db, user=admin)
        got = run["by_route"]
        want = SIGNED[key]
        ok = all(abs(got.get(k, 0) - v) < 0.005 for k, v in want.items())
        shown = ", ".join(f"{k.upper()} {got.get(k, 0):,.2f}" for k in want)
        if not ok:
            say(f"August for {key}: {shown} - does NOT match the signed statement. "
                "Left as a draft; nothing approved.")
            NOTES.append(f"August for {key} did not match the signed statement: {shown}.")
            continue
        main.approve_payroll_run(run["id"], db=db, user=admin)
        say(f"August for {key}: {shown} - matches the signed statement, approved.")

    # ---- Rises that come after August --------------------------------
    for code, when, amt, why in FUTURE_RISES:
        already = (db.query(models.SalaryChange)
                     .join(models.Employee, models.Employee.id == models.SalaryChange.employee_id)
                     .filter(models.Employee.emp_no == code,
                             models.SalaryChange.effective_on == date.fromisoformat(when),
                             models.SalaryChange.kind == "increment").first())
        if already:
            continue
        r, err = call(main.add_increment, {"emp_no": code, "effective_on": when, "amount": amt,
                                           "to_basic": 0, "reason": why}, db=db, user=admin)
        say(f"Increment {code} +{amt:,.0f} from {when}: " + (err or r["detail"]))

    # ---- What is on file now -----------------------------------------
    loans = main.list_loans(db=db, user=admin)
    say("")
    say("Loan balances now: " + ", ".join(f"{l['emp_no']} {l['balance']:,.2f}"
                                          for l in loans["rows"] if not l["closed"]))
    docs = main.list_documents(within=30, db=db, user=admin)
    if docs["rows"]:
        say(f"Documents expired or due within 30 days: {len(docs['rows'])}")
        for d in docs["rows"][:15]:
            say(f"   {d['emp_no']:>7}  {d['name'][:26]:<26} {d['kind_label']:<20} "
                f"{d['expires_on']}  ({d['days_left']} days)")
    if NOTES:
        say("\nTo look at:")
        for n in NOTES:
            say(" - " + n)
    say("\nDone. Open HR & Payroll to see it.")


if __name__ == "__main__":
    main_load()

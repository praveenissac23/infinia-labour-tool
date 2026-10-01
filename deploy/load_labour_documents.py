"""Load the labour document tracker (01.DOCUMENT_TRACKER - LABOURS.xlsx,
72 workers, Infinia and Prime) into Expiry Reminder > People:
Emirates ID, labour card and passport expiry for each man.

    cd ~/infinia-labour-tool && venv/bin/python deploy/load_labour_documents.py

The sheet has names only, typed in their own way ("RAVI RAYI" is RAVI
ROY, "FALVDAR" is FAVLDAR), so each line below carries the worker code it
was matched to by hand. On the server every match is checked again: the
code must be on the list and share a name with the sheet's, or the line
is skipped and named. Three men were not on the copy of the list used to
match (GUDDU KUMAR, JAYA PRAKASH, MIRAJUL ANSARI; PALDURAI PICHAI is F-801); they
are found by name on the server, and skipped if not found exactly once.

Checked against the sheet before loading:
  * "Days left" in the sheet are formulas (date minus today) - always
    right in Excel, never copied here; the app works them out every day.
  * Six labour cards (rows 58-63) read 03-Nov-2028 against an Emirates ID
    of 11-Mar-2028: day and month typed the wrong way round. Loaded as
    11-Mar-2028, the same as their Emirates ID (as for the rest of that
    batch).
  * ABHISHEK (row 66): Emirates ID 06-Oct-2028 against a labour card of
    10-Jun-2028 - the same mix-up. Loaded as 10-Jun-2028.
  * BARSATI (row 5): passport 27-Sep-2026 with the remark RENEWED - the
    new passport date was never typed in. The old date is not loaded; put
    the new one in on the app.
  * MOHAN KUMAR (row 68): labour card 11-Aug-2028 but Emirates ID
    15-Jun-2028 (a labour card normally ends with or before the ID).
    Loaded as on the sheet - please check against the card.
  * Names cleaned (leading spaces, "M0HAMED" with a zero).

A date already on the app is never moved backwards: if the app has a
later date (renewed since the sheet was made) it is kept. Safe to run
again - nothing is added twice.
"""
import os, re, sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, HERE)
from clear_test_returns import _find_database_url

url = _find_database_url()
if not url:
    sys.exit("Could not find DATABASE_URL.")
os.environ["DATABASE_URL"] = url
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import models

D = lambda s: date(*map(int, s.split("-"))) if s else None
# row, name on the sheet, code matched, company, EID, labour card, passport
ROWS = [
    (1, "MOHAMED SALIM", "D-01", "Infinia", "2027-01-21", "2027-01-10", "2032-11-24"),
    (2, "MUHAMMED USMAN", "D-02", "Infinia", "2026-11-19", "2026-11-14", "2032-01-16"),
    (3, "AHMAD ALI", "D-03", "Infinia", "2028-03-02", "2028-01-29", "2032-08-08"),
    (4, "RAM BRIKSH SHYAM RAJ", "F-002", "Infinia", "2027-07-31", "2027-07-29", "2036-03-17"),
    (5, "BARSATI", "F-004", "Infinia", "2027-03-07", "2027-03-04", None),          # passport renewed - new date not on sheet
    (6, "RAJENDRA SINGH", "F-005", "Infinia", "2027-05-18", "2027-05-13", "2035-01-26"),
    (7, "SAMARJEET SINGH", "F-707", "Infinia", "2027-04-06", "2027-03-29", "2031-04-13"),
    (8, "LAKHWINDER SINGH", "F-712", "Infinia", "2027-10-07", "2027-10-07", "2028-03-14"),
    (9, "SHIV CHARAN", "F-715", "Infinia", "2028-06-21", "2028-06-18", "2029-07-24"),
    (10, "AVINAS PASWAN", "F-716", "Infinia", "2028-07-02", "2028-06-29", "2033-04-02"),
    (11, "ABID", "F-717", "Infinia", "2028-07-06", "2028-07-03", "2027-01-24"),
    (12, "SATYA DEV", "F-722", "Infinia", "2028-08-23", "2028-08-28", "2033-08-27"),
    (13, "DILSHAD KHAN", "F-723", "Infinia", "2028-09-14", "2028-09-12", "2034-03-06"),
    (14, "AJAY KUMAR", "F-724", "Infinia", "2028-09-14", "2028-09-12", "2031-08-31"),
    (15, "SOMARY PRASAD", "F-726", "Infinia", "2028-09-14", "2028-09-12", "2026-11-16"),
    (16, "BENCHEP OLIVER KARNGONG", "F-727", "Infinia", "2026-10-14", "2026-10-07", "2027-02-17"),
    (17, "DIWAKAR", "F-728", "Infinia", "2026-10-14", "2026-10-10", "2034-01-04"),
    (18, "PRADEEP", "F-729", "Infinia", "2026-10-14", "2026-10-12", "2031-04-20"),
    (19, "PARDUM", "F-730", "Infinia", "2026-10-14", "2026-10-12", "2029-10-08"),
    (20, "CHHANU MAHATO", "F-732", "Infinia", "2026-10-18", "2026-10-15", "2028-11-21"),
    (21, "VIJAY KUMAR SINGH", "F-734", "Infinia", "2026-12-09", "2026-12-07", "2032-05-12"),
    (22, "BHIM BAHADUR", "F-735", "Infinia", "2027-01-19", "2026-12-06", "2035-12-18"),
    (23, "DILIP KUMAR CHAUDHARY", "F-736", "Infinia", "2026-12-10", "2026-12-06", "2034-02-22"),
    (24, "MONIR", "F-740", "Infinia", "2026-12-12", "2026-12-16", "2026-12-07"),
    (25, "MUNNA KUMAR YADAV", "F-741", "Infinia", "2027-01-20", "2026-12-19", "2028-04-30"),
    (26, "DEEPAK PUN MAGAR", "F-742", "Infinia", "2027-01-20", "2026-12-30", "2031-01-21"),
    (27, "LATIF ANSARI", "F-743", "Infinia", "2027-01-20", "2026-12-30", "2033-01-02"),
    (28, "GUDDU KUMAR", None, "Infinia", "2027-02-18", "2027-02-11", "2030-04-22"),
    (29, "RAMPRAVESH", "F-746", "Infinia", "2027-02-18", "2027-02-11", "2036-05-28"),
    (30, "JITENDRA KUMAR", "F-749", "Infinia", "2027-03-23", "2027-03-16", "2031-08-25"),
    (31, "RAVI RAYI", "F-751", "Infinia", "2027-03-26", "2027-03-24", "2027-10-09"),
    (32, "CHANDAN KUMAR", "F-752", "Infinia", "2027-05-04", "2027-04-15", "2035-01-28"),
    (33, "SANDEEP KUMAR", "F-753", "Infinia", "2027-05-03", "2027-04-15", "2034-04-23"),
    (34, "HARISHANKAR", "F-754", "Infinia", "2027-05-02", "2027-04-16", "2027-03-30"),
    (35, "DIP KUMAR", "F-755", "Infinia", "2027-05-04", "2027-05-02", "2027-03-27"),
    (36, "HARERAM", "F-756", "Infinia", "2027-05-02", "2027-04-19", "2034-04-17"),
    (37, "SANJAY KUMAR", "F-757", "Infinia", "2027-05-02", "2027-04-29", "2035-03-17"),
    (38, "NANDLAL", "F-758", "Infinia", "2027-05-18", "2027-05-05", "2030-12-28"),
    (39, "DHARAM PAL", "F-759", "Infinia", "2027-08-15", "2027-08-11", "2036-05-13"),
    (40, "SANTHOSH", "F-760", "Infinia", "2027-09-16", "2027-09-16", "2035-04-18"),
    (41, "SOM BAHADUR", "F-762", "Infinia", "2027-09-28", "2027-09-25", "2035-05-06"),
    (42, "GANESH KUMAR", "F-763", "Infinia", "2027-09-25", "2027-09-25", "2035-07-07"),
    (43, "MOHAMMAD ZUBAIR ALAM", "F-764", "Infinia", "2027-09-30", "2027-09-30", "2032-12-04"),
    (44, "MOHAMMAD RAJID", "F-766", "Infinia", "2027-09-30", "2027-09-30", "2028-07-29"),
    (45, "MECHHAFA", "F-770", "Infinia", "2027-05-11", "2027-05-11", "2029-11-21"),
    (46, "SAFIKUL MONDAL", "F-771", "Infinia", "2027-05-11", "2027-05-11", "2036-08-24"),
    (47, "RAMESH KUMAR", "F-773", "Infinia", "2027-11-12", "2027-11-12", "2033-03-22"),
    (48, "RAM NATH", "F-775", "Infinia", "2027-12-30", "2027-12-30", "2035-08-25"),
    (49, "IMTYAJ ALI", "F-776", "Infinia", "2027-11-20", "2027-11-24", "2032-07-12"),
    (50, "DANIEL", "F-777", "Infinia", "2027-11-26", "2027-11-27", "2032-03-30"),
    (51, "SANDEEP YADAV", "F-778", "Infinia", "2027-04-12", "2027-04-12", "2032-12-13"),
    (52, "MUNTAZIR ALAM", "F-779", "Infinia", "2027-03-12", "2027-03-12", "2035-10-15"),
    (53, "SAJANPREET SINGH", "F-780", "Infinia", "2027-09-12", "2027-09-12", "2035-09-10"),
    (54, "AKASH MAHTO", "F-781", "Infinia", "2027-12-16", "2027-12-16", "2035-07-31"),
    (55, "CHRIS CHAZIMA ANDAMBI", "F-782", "Infinia", "2028-01-13", "2028-01-13", "2031-11-01"),
    (56, "PETER MUNENE", "F-784", "Infinia", "2028-02-27", "2028-02-27", "2035-10-02"),
    (57, "PHILIP MAINA", "F-785", "Infinia", "2028-02-27", "2028-02-27", "2034-03-13"),
    # 58-63: labour card typed 03-Nov-2028 (day and month swapped) - 11-Mar-2028
    (58, "CHUNNA ALAM", "F-786", "Infinia", "2028-03-11", "2028-03-11", "2035-09-23"),
    (59, "ABDULA MATIN", "F-787", "Infinia", "2028-03-11", "2028-03-11", "2036-01-20"),
    (60, "MD MINTO", "F-788", "Infinia", "2028-03-11", "2028-03-11", "2033-09-18"),
    (61, "AZAD ALAM", "F-789", "Infinia", "2028-03-11", "2028-03-11", "2035-12-16"),
    (62, "SHAMSHER SINGH", "F-790", "Infinia", "2028-03-11", "2028-03-11", "2032-08-04"),
    (63, "RAJMAN KUMAR", "F-791", "Infinia", "2028-03-11", "2028-03-11", "2035-08-10"),
    (64, "FALVDAR", "F793", "Prime Infinia", "2028-04-22", "2028-04-22", "2034-07-24"),
    (65, "AMANDEEP SINGH", "F794", "Prime Infinia", "2028-06-21", "2028-06-08", "2030-01-20"),
    # 66: Emirates ID typed 06-Oct-2028 (day and month swapped) - 10-Jun-2028
    (66, "ABHISHEK", "F795", "Prime Infinia", "2028-06-10", "2028-06-10", "2035-03-25"),
    (67, "SURESH CHAMAR", "F796", "Prime Infinia", "2028-06-15", "2028-06-11", "2031-03-08"),
    (68, "MOHAN KUMAR", "F797", "Prime Infinia", "2028-06-15", "2028-08-11", "2035-01-16"),   # labour card: please check
    (69, "ARUN YADAV", "F798", "Prime Infinia", "2028-07-18", "2028-07-14", "2036-03-09"),
    (70, "JAYA PRAKASH", None, "Prime Infinia", "2028-07-28", "2028-07-24", "2028-09-26"),
    (71, "MIRAJUL ANSARI", None, "Prime Infinia", "2028-07-28", "2028-07-24", "2034-06-27"),
    (72, "PALDURAI PICHAI", "F-801", "Prime Infinia", "2028-08-18", "2028-08-12", "2036-07-08"),
]
KINDS = (("eid", "Emirates ID"), ("labour_card", "Labour card"), ("passport", "Passport"))
FIXED = {5: "passport not loaded - sheet says RENEWED but still has the old date 27-Sep-2026; put the new date in",
         58: "labour card 03-Nov-2028 read as 11-Mar-2028 (day/month swapped)",
         59: "labour card 03-Nov-2028 read as 11-Mar-2028 (day/month swapped)",
         60: "labour card 03-Nov-2028 read as 11-Mar-2028 (day/month swapped)",
         61: "labour card 03-Nov-2028 read as 11-Mar-2028 (day/month swapped)",
         62: "labour card 03-Nov-2028 read as 11-Mar-2028 (day/month swapped)",
         63: "labour card 03-Nov-2028 read as 11-Mar-2028 (day/month swapped)",
         66: "Emirates ID 06-Oct-2028 read as 10-Jun-2028 (day/month swapped)",
         68: "labour card 11-Aug-2028 is two months after the Emirates ID 15-Jun-2028 - please check the card"}

# Typos fixed on purpose: these replace whatever the app has (an earlier
# load carried the same mistakes in).
FORCE = {(58, "labour_card"), (59, "labour_card"), (60, "labour_card"), (61, "labour_card"),
         (62, "labour_card"), (63, "labour_card"), (66, "eid")}

norm_code = lambda c: re.sub(r"[\s\-]+", "", str(c or "")).upper()
words = lambda s: set(re.sub(r"[^A-Z ]", " ", (s or "").upper().replace("0", "O")).split()) - {"MD", "MOHAMMAD", "MOHAMMED", "MOHAMED", "MUHAMMED", "MUHAMMAD", "KUMAR", "SINGH"}

def same_man(a, b):
    """The sheet's spelling against the app's: a shared word, or the letters
    mostly the same ("HARISHANKAR" / "HARI SHANKAR", "FALVDAR" / "FAVLDAR")."""
    from difflib import SequenceMatcher
    if words(a) & words(b):
        return True
    x = re.sub(r"[^A-Z]", "", (a or "").upper().replace("0", "O"))
    y = re.sub(r"[^A-Z]", "", (b or "").upper())
    if bool(x and y) and (x in y or y in x or SequenceMatcher(None, x, y[:len(x) + 3]).ratio() >= 0.7):
        return True
    # First names alone ("PALDURAI PICHAI" / "PALADURAI").
    fa = re.sub(r"[^A-Z]", "", (a or "").upper().replace("0", "O").split()[0]) if (a or "").split() else ""
    fb = re.sub(r"[^A-Z]", "", (b or "").upper().split()[0]) if (b or "").split() else ""
    return len(fa) >= 4 and len(fb) >= 4 and SequenceMatcher(None, fa, fb).ratio() >= 0.85


engine = create_engine(url)
db = sessionmaker(bind=engine)()
emps = db.query(models.Employee).all()
by_code = {norm_code(e.emp_no): e for e in emps}
today = date.today()

added = updated = kept = same = 0
skipped, notes = [], []
for row, name, code, company, *dates in ROWS:
    e = by_code.get(norm_code(code)) if code else None
    if code and e and not same_man(name, e.name):
        skipped.append(f"row {row} {name}: code {code} is '{e.name}' on the app - not the same man, skipped")
        continue
    if not e:
        # Found by name: every word of the sheet's name in his name, exactly one man.
        want = set(re.sub(r"[^A-Z ]", " ", name.upper()).split())
        hits = [x for x in emps if want <= set(re.sub(r"[^A-Z ]", " ", (x.name or "").upper()).split())]
        if len(hits) != 1:
            skipped.append(f"row {row} {name}: " + ("not on the worker list - add him, then put his dates in on the app"
                                                    if not hits else "more than one worker by that name: " + ", ".join(f"{x.emp_no} {x.name}" for x in hits)))
            continue
        e = hits[0]
    if row in FIXED:
        notes.append(f"row {row} {name} ({e.emp_no}): {FIXED[row]}")
    for (kind, label), ds in zip(KINDS, dates):
        d = D(ds)
        if not d:
            continue
        have = db.query(models.EmployeeDocument).filter(models.EmployeeDocument.employee_id == e.id,
                                                         models.EmployeeDocument.kind == kind).first()
        if have and have.expires_on == d:
            same += 1
        elif have and have.expires_on and have.expires_on > d and (row, kind) not in FORCE:
            kept += 1
            notes.append(f"{e.emp_no} {e.name}: {label} on the app {have.expires_on:%d-%b-%Y} is later than the sheet's {d:%d-%b-%Y} - kept")
        elif have:
            print(f"  updated  {e.emp_no:7} {e.name[:26]:26} {label:12} {have.expires_on or '-'} -> {d:%d-%b-%Y}")
            have.expires_on = d
            updated += 1
        else:
            db.add(models.EmployeeDocument(employee_id=e.id, kind=kind, expires_on=d, number="", notes=""))
            added += 1
db.commit()

print(f"\nDONE: {added} added, {updated} updated, {same} already the same, {kept} kept (app had a later date).")
if notes:
    print("\nChecked and corrected / please look:")
    for n in notes:
        print("  - " + n)
if skipped:
    print("\nNOT loaded:")
    for s in skipped:
        print("  - " + s)
listed = {norm_code(c) for _, _, c, *_ in ROWS if c}
missing = [e for e in emps if e.active and not e.staff and norm_code(e.emp_no) not in listed
           and not db.query(models.EmployeeDocument).filter(models.EmployeeDocument.employee_id == e.id).first()]
if missing:
    print("\nLabourers on the app but not on the sheet (no documents yet):")
    for e in missing:
        print(f"  - {e.emp_no} {e.name}")
print("\nOpen Expiry Reminder > People to see them.")

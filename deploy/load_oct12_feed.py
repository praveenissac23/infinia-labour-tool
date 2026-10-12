"""Feed of 12 Oct 2026: labour joining dates, security cheques and
deposits, and the company's saved logins.

    cd ~/infinia-labour-tool && venv/bin/python deploy/load_oct12_feed.py

Safe to run more than once: a joining date only fills an empty one, and
a cheque, deposit or login already on file (same party and amount / same
name and username) is skipped. Passwords are encrypted as they go in,
with the server's own key (data/credentials.key); each login's logo is
fetched from its website.
"""
import os, sys
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, HERE)
from clear_test_returns import _find_database_url

url = _find_database_url()
if not url:
    sys.exit("Could not find DATABASE_URL.")
os.environ["DATABASE_URL"] = url
os.environ.setdefault("INFINIA_NO_PUSH", "1")
import main as M          # noqa: E402  (tables and columns made as the app makes them)
import models             # noqa: E402
import credentials as CR  # noqa: E402
import seccheque as SC    # noqa: E402
from database import SessionLocal  # noqa: E402

REMIND = date(2027, 4, 12)          # six months from 12 Oct 2026, as asked
BANK = "ADCB"

JOINING = [["D01", "MOHAMED SALIM", "DRIVER", "13-01-2023"], ["D02", "MUHAMMAD USMAN", "DRIVER", "31-10-2024"], ["D03", "AHMAD ALI", "DRIVER", "12-01-2026"], ["F002", "RAM BRIKSH - FOREMAN", "FOREMAN", "01-08-2023"], ["F004", "BARSATI-FOREMAN", "FOREMAN", "01-03-2025"], ["F707", "SAMARJEET SINGH", "CARPENTER", "01-04-2023"], ["F712", "LAKHWINDER SINGH", "MASON", "01-10-2023"], ["F715", "SHIV CHARAN", "MASON", "21-06-2024"], ["F716", "AVINAS PASWAN", "STEEL FIXER", "02-07-2024"], ["F717", "ABID", "MASON", "06-07-2024"], ["F722", "SATYA DEV", "OL", "31-08-2024"], ["F723", "DILSHAD KHAN", "OL", "16-09-2024"], ["F724", "AJAY KUMAR", "OL", "16-09-2024"], ["F726", "SOMARY PRASAD", "CARPENTER", "16-09-2024"], ["F727", "BENCHEP OLIVER KARNGONG", "OL", "07-10-2024"], ["F728", "DIWAKAR", "CARPENTER", "12-10-2024"], ["F729", "PRADEEP", "CARPENTER", "14-10-2024"], ["F730", "PARDUM", "CARPENTER", "14-10-2024"], ["F732", "CHHANU MATO", "MASON", "17-10-2024"], ["F734", "VIJAY KUMAR SINGH", "STEEL FIXER", "09-12-2024"], ["F735", "BHIM BAHADUR", "STEEL FIXER", "09-12-2024"], ["F736", "DILIP KUMAR CHAUDHARY", "MASON", "09-12-2024"], ["F740", "MONIR", "MASON", "12-12-2024"], ["F741", "MUNNA KUMAR YADAV", "CARPENTER", "18-12-2024"], ["F742", "DEEPAK PUN MAGAR", "CARPENTER", "21-12-2024"], ["F743", "LATIF ANSARI", "CARPENTER", "02-01-2025"], ["F745", "GUDDU KUMAR", "STEEL FIXER", "13-02-2025"], ["F746", "RAMPRAVESH", "STEEL FIXER", "13-02-2025"], ["F749", "JITENTRA", "STEEL FIXER", "19-03-2025"], ["F751", "RAVI RAY", "ELECTRICIAN CUM OL", "26-03-2025"], ["F752", "CHANDAN KUMAR", "HELPER", "17-04-2025"], ["F753", "SANDEEP KUMAR", "MASON", "17-04-2025"], ["F754", "HARI SHANKAR CHAUHAN", "MASON", "18-04-2025"], ["F755", "DIP KUMAR", "MASON (IN CHARGE)", "21-04-2025"], ["F756", "HARERAM YADAV", "CARPENTER", "25.04.2025"], ["F757", "SANJAY KUMAR", "MASON", "30.04.2025"], ["F758", "NANDLAL", "CARPENTER", "03.05.2025"], ["F759", "DHARAM PAL", "MASON", "13.08.2025"], ["F760", "SANTOSH NISHAD", "LABOUR CUM WATCHMAN", "13.09.2025"], ["F762", "SOM BAHADUR TAMANG", "MASON", "25.09.2025"], ["F763", "GANESH KUMAR", "MASON", "25.09.2025"], ["F764", "MOHAMMED ZUBAIR", "MASON", "30.09.2025"], ["F766", "MOHAMED RAJID", "MASON", "30.09.2025"], ["F770", "MACHHAFA MONDAL", "ASSISTANT CARPENTER", "30.10.2025"], ["F771", "SAFIKUL MONDAL", "MASON", "30.10.2025"], ["F773", "RAMESH KUMAR", "CARPENTER", "10.11.2025"], ["F775", "RAM NATH", "MASON", "21.11.2025"], ["F776", "IMTAYAJ ALI", "PAINTER&HELPER", "21.11.2025"], ["F777", "DANIEL GACHUKI", "HELPER", "27.11.2025"], ["F778", "SANDEEP YADAV", "HELPER", "03.12.2025"], ["F779", "MUTAZIR ALAM", "HELPER", "03.12.2025"], ["F780", "SAJANPREET SINGH", "HELPER", "08.12.2025"], ["F781", "AKASH MAHTO", "HELPER", "13.12.2025"], ["F782", "CHRIS CHAZIMA", "HELPER", "10.01.2026"], ["F784", "PETER MUNENE", "HELPER", "26.02.2026"], ["F785", "PHILIP MAINA", "HELPER", "26.02.2026"], ["F786", "MD CHUNNA ALAM", "MASON", "05.03.2026"], ["F787", "ABDUL MATIN", "MASON", "05.03.2026"], ["F788", "MD MINTO", "MASON", "05.03.2026"], ["F789", "MD AZAD ALAM", "MASON", "05.03.2026"], ["F790", "SHAMSHER SINGH", "HELPER", "05.03.2026"], ["F791", "RAJMAN KUMAR", "HELPER", "10.03.2026"], ["F793", "FAVLDAR", "CARPENTER", "17.06.2026"], ["F794", "AMANDEEP SINGH", "MASON", "05.06.2026"], ["F795", "ABHISHEK", "ASSISTANT CEILING FIXER", "12.06.2026"], ["F796", "SURESH CHAMAR", "CEILING FIXER", "13.06.2026"], ["F797", "MOHAN KUMAR RAI", "CEILING FIXER", "13.06.2026"], ["F798", "ARUN YADAV", "ASSISTANT CEILING FIXER", "16.07.2026"], ["F799", "JAYA PRAKASH", "STEEL FIXER", "27.07.2026"], ["F800", "MIRAJUL ANSARI", "STEEL FIXER", "27.07.2026"], ["F801", "PALDURAI PITCHAI", "STEEL FIXER", "14.08.2026"]]

CHEQUES = [["DESARCH BUILDING", 150000.0, "2023-05-18", "000007", "FOR SECURITY"], ["MOHAMMED ANIS", 457800.0, "2023-07-14", "000008", "FOR SECURITY 902 RENAISSANCE"], ["MOHAMMED ANIS", 436000.0, "2023-07-14", "000009", "FOR SECURITY 902 RENAISSANCE"], ["DCM COMMUNITIES LLC", 50000.0, "2023-08-04", "000011", "FOR SECURITY"], ["BUCOMAC INDUSTRIES", 250000.0, "2023-08-18", "000012", "FOR CREDIT APPLICATION"], ["CONMIX LIMITED CO LLC", 100000.0, "2023-09-01", "000017", "FOR SECURITY"], ["AL RAHA INTERNATIONAL", 25000.0, "2023-09-09", "000018", "FOR SECURITY"], ["PHASE 1 DUBAI PARK LLC", 50000.0, "2023-12-07", "000033", "FOR SECURITY"], ["AVV GENERAL TRADING", 50000.0, "2024-03-20", "000044", "FOR CREDIT APPLICATION"], ["MERAAS REAL ESTATE", 50000.0, "2024-04-29", "000049", "FOR SECURITY"], ["FIRST GOAL FORM WORK", 2000.0, "2025-02-04", "000089", "FOR SECURITY"], ["UNI MIX BLOCK", 100000.0, "2025-03-03", "000099", "FOR CREDIT APPLICATION"], ["NAD SHABEEB", 5000.0, "2025-03-22", "00104", "FOR SECURITY"], ["QUAD DREAM SCAFFOLDING", 198189.0, "2025-04-16", "000107", "FOR CREDIT APPLICATION"], ["AL DANUBE BUILDING MATERIALS", 100000.0, "2025-08-26", "000123", "FOR CREDIT APPLICATION"], ["GEMINI BUILDING MATERIALS", 25000.0, "2026-05-06", "000134", "FOR CREDIT APPLICATION"], ["ELEGANT EXECUTION", 65940.0, "2026-08-18", "000149", "FOR SECUIRTY (102 PROJECT) IT WILL RETURN ONCE CONCRETE DONE"], ["SHAFA AL NAHDA", 100000.0, "2026-10-09", "000155", "FOR CREDIT APPLICATION"], ["MAG PARK REAL ESTATE DEVELOPMENT", 25000.0, "2026-09-24", "000157", "FOR COMMUNITY PROTECTION SECURITY CHEQUE - 918"]]

DEPOSITS = [["ALTIA ONE", "SECURITY DEPOSIT - APARTMENT", 6000.0, "2026-01-19", "RENTAL UNIT - SECURITY DEPOSIT"], ["DEWA", "SECURITY DEPOSIT - APARTMENT", 2155.0, "2026-01-23", "ALTIA ONE - DEWA CONNECTION"], ["DEWA", "SECURITY DEPOSIT - 905", 4000.0, "2026-02-19", "PERMANENT DEWA CONNECTION"], ["SOLIVING", "SECURITY DEPOSIT - LABOUR CAMP", 32400.0, "2026-05-21", "LABOUR CAMP 26-27"], ["DM", "FIC INSPECTION FEE", 10020.0, "2026-09-09", "SOBHA WILL REFUND THIS"]]

LOGINS = [{"category": "Email & IT", "name": "JOB PORTAL MAIL ID", "url": "", "username": "infiniacontracing.job@gmail.com", "secret": "Infinia@2025", "notes": ""}, {"category": "Email & IT", "name": "JOB PORTAL MAIL ID", "url": "", "username": "INFINIAJOBS@GMAIL.COM", "secret": "Infinia@2025", "notes": ""}, {"category": "Email & IT", "name": "JOB PORTAL MAIL ID", "url": "", "username": "accounts@infinia.ae", "secret": "accounts765!", "notes": "Name carried from the line above in the sheet"}, {"category": "Email & IT", "name": "JOB PORTAL MAIL ID", "url": "", "username": "info@infina.ae", "secret": "Infoinfi876#", "notes": "Name carried from the line above in the sheet"}, {"category": "Email & IT", "name": "JOB PORTAL MAIL ID", "url": "", "username": "primeinfiniatechnicalservices@gmail.com", "secret": "Infinia@2026", "notes": "Name carried from the line above in the sheet"}, {"category": "Email & IT", "name": "JOB PORTAL MAIL ID", "url": "", "username": "enginova.office@gmail.com", "secret": "Password:enginova@123", "notes": "Name carried from the line above in the sheet"}, {"category": "Email & IT", "name": "ZOHO BOOKS", "url": "https://books.zoho.com/", "username": "accounts@infinia.ae", "secret": "Zoho@2026", "notes": ""}, {"category": "Email & IT", "name": "SYNOLOGY", "url": "https://quickconnect.to", "username": "Anoop", "secret": "Infinia@2026", "notes": ""}, {"category": "Email & IT", "name": "SYNOLOGY", "url": "https://quickconnect.to", "username": "Arathi", "secret": "Infinia@2026", "notes": ""}, {"category": "Email & IT", "name": "SYNOLOGY", "url": "https://quickconnect.to", "username": "FrontDesk", "secret": "Infinia@2026", "notes": ""}, {"category": "Email & IT", "name": "SYNOLOGY", "url": "https://quickconnect.to", "username": "Accounts", "secret": "Shafeeq@2025", "notes": ""}, {"category": "Email & IT", "name": "SYNOLOGY", "url": "https://quickconnect.to", "username": "OFFICE WIFI PASSWORD", "secret": "p@infinia", "notes": "Name carried from the line above in the sheet"}, {"category": "Email & IT", "name": "SYNOLOGY", "url": "https://quickconnect.to", "username": "PO Box", "secret": "85567", "notes": "Name carried from the line above in the sheet"}, {"category": "Utilities", "name": "DEWA Account", "url": "https://www.dewa.gov.ae", "username": "infiniacontracting", "secret": "Infiniadxb1#", "notes": ""}, {"category": "Email & IT", "name": "GMAIL", "url": "https://mail.google.com", "username": "infiniacontracting@gmail.com", "secret": "Infiniadxb1#", "notes": ""}, {"category": "Government", "name": "DM & DED", "url": "https://www.dm.gov.ae", "username": "pro@infinia.ae", "secret": "pro@jomon1", "notes": ""}, {"category": "Government", "name": "LABOUR DEPT", "url": "https://www.mohre.gov.ae", "username": "1462908 : Company num", "secret": "", "notes": ""}, {"category": "Government", "name": "FTA", "url": "https://eservices.tax.gov.ae", "username": "infiniacontracting@gmail.com", "secret": "Account@infinia1", "notes": ""}, {"category": "Utilities", "name": "ETISALAT NIC PORTAL", "url": "https://m.nic.ae", "username": "6410356138", "secret": "Infiniadxb1#", "notes": ""}, {"category": "Utilities", "name": "ETISALAT BUSINESS PORTAL", "url": "https://www.etisalat.ae", "username": "infiniacontracting@gmail.com", "secret": "Infiniadxb1!", "notes": ""}, {"category": "Email & IT", "name": "ROUTER: 192.168.1.1", "url": "", "username": "admin", "secret": "admin123", "notes": "Router address 192.168.1.1"}, {"category": "Email & IT", "name": "BIGROCK", "url": "https://www.bigrock.in", "username": "infiniacontracting@gmail.com", "secret": "Infinia@2026", "notes": ""}, {"category": "Email & IT", "name": "WORDPRESS", "url": "https://wordpress.com", "username": "Infiniacontracting", "secret": "Infiniadxb1#", "notes": ""}, {"category": "Email & IT", "name": "CPANEL", "url": "", "username": "https://sh003.bigrock.com:2083/", "secret": "infin5y6", "notes": ""}, {"category": "Email & IT", "name": "WEBMAILS", "url": "", "username": "https://webmail.infinia.ae", "secret": "", "notes": ""}, {"category": "Email & IT", "name": "WEBMAILS", "url": "", "username": "info@infinia.ae", "secret": "Info@654#", "notes": "Name carried from the line above in the sheet"}, {"category": "Government", "name": "RTA", "url": "https://www.rta.ae", "username": "praveenissac", "secret": "Infiniadxb1#", "notes": ""}, {"category": "Government", "name": "SALIK", "url": "https://www.salik.ae", "username": "35616618", "secret": "4276", "notes": ""}, {"category": "Government", "name": "SALIK OUR CAR", "url": "https://www.salik.ae", "username": "35630592", "secret": "7495", "notes": ""}, {"category": "Other", "name": "LOCKER", "url": "", "username": "#9847#", "secret": "", "notes": ""}, {"category": "Government", "name": "INDIAN EMBASSY EMIGRATE", "url": "https://emigrate.gov.in", "username": "FE5800171", "secret": "X4A6A@Px", "notes": ""}, {"category": "Government", "name": "TRAFFIC CODE NUMBER", "url": "", "username": "50516190", "secret": "", "notes": ""}, {"category": "Government", "name": "EMIGRATE", "url": "https://emigrate.gov.in", "username": "FE5800171", "secret": "Infinia@pro1", "notes": "Pet name : Infinia@123"}, {"category": "Government", "name": "DDA LOGIN", "url": "https://www.dda.gov.ae", "username": "pro@infinia.ae", "secret": "Infinia@dda2026", "notes": ""}, {"category": "Government", "name": "DDA LOGIN", "url": "https://www.dda.gov.ae", "username": "office@infinia.ae", "secret": "infinia@123", "notes": ""}, {"category": "Government", "name": "POST OFFICE PORTAL", "url": "https://www.emiratespost.ae", "username": "pro@infinia.ae", "secret": "Epostinfinia@1", "notes": ""}, {"category": "Government", "name": "Salik", "url": "https://www.salik.ae", "username": "Infiniasalik", "secret": "Infiniasalik@123", "notes": ""}, {"category": "Government", "name": "Salik Account", "url": "https://www.salik.ae", "username": "35630592", "secret": "7495", "notes": ""}, {"category": "Utilities", "name": "Etisalat login", "url": "https://www.etisalat.ae", "username": "pro@infinia.ae", "secret": "Infinia@etisalat26", "notes": ""}, {"category": "Government", "name": "Dubai Building Permit System", "url": "https://www.dm.gov.ae", "username": "infinia", "secret": "Infinia@123", "notes": ""}, {"category": "Government", "name": "TRAKHEES PORTAL", "url": "https://www.trakhees.ae", "username": "infiniaprojects", "secret": "Voss#12345", "notes": ""}, {"category": "Government", "name": "DEQ", "url": "", "username": "pro@infinia.ae", "secret": "pro@jomon1", "notes": ""}, {"category": "Government", "name": "E supply", "url": "https://esupply.dubai.gov.ae", "username": "Infiniacontracting", "secret": "Infinia123", "notes": ""}, {"category": "Email & IT", "name": "cpanel", "url": "", "username": "https://sh003.bigrock.com:2083/", "secret": "Classmate123#", "notes": ""}, {"category": "Email & IT", "name": "Webflow website hosting", "url": "https://webflow.com", "username": "infi@UAE25", "secret": "", "notes": "Account: infiniacontracting@gmail.com"}, {"category": "Government", "name": "EMIRATES POST", "url": "https://www.emiratespost.ae", "username": "engineers@infinia.ae", "secret": "EPInfini@23", "notes": ""}, {"category": "Utilities", "name": "Etisalat portal", "url": "https://www.etisalat.ae", "username": "Infinia@etisalat27", "secret": "", "notes": ""}, {"category": "Government", "name": "Makkani Number", "url": "https://www.makani.ae", "username": "3327696938", "secret": "", "notes": ""}, {"category": "Email & IT", "name": "microsoft email", "url": "https://outlook.office.com", "username": "accounts@infinia.ae", "secret": "Acc@inf*2020!", "notes": ""}, {"category": "Email & IT", "name": "microsoft email", "url": "https://outlook.office.com", "username": "info@infinia.ae", "secret": "Inf@Inf*9511!", "notes": ""}, {"category": "Government", "name": "DCD portal", "url": "https://www.dcd.gov.ae", "username": "infiniadcd25", "secret": "Infiniadcd@25", "notes": ""}, {"category": "Email & IT", "name": "chatgpt+", "url": "https://chatgpt.com", "username": "engineers@infinia.ae", "secret": "infinia@engineers", "notes": ""}, {"category": "Utilities", "name": "Dewa business", "url": "https://www.dewa.gov.ae", "username": "Infiniadewa", "secret": "Infinia1#", "notes": ""}]


def _day(s):
    for f in ("%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s.strip(), f).date()
        except ValueError:
            pass
    return None


def _cheque_fields(remark):
    r = remark.upper()
    purpose = "Supplier credit" if "CREDIT" in r else "Community protection security" if "COMMUNITY" in r else "Security"
    project, notes = "", ""
    if "902" in r: project, notes = "902", "Renaissance"
    if "102" in r: project, notes = "102 project", "Will return once concrete is done"
    if "918" in r: project = "918"
    return purpose, project, notes


def main():
    db = SessionLocal()
    # 1. Labour joining dates
    filled = skipped = missing = 0
    import re
    key = lambda c: re.sub(r"[^A-Z0-9]", "", str(c or "").upper())
    by_key = {key(e.emp_no): e for e in db.query(models.Employee).filter(models.Employee.staff != True).all()}  # noqa: E712
    for code, name, trade, when in JOINING:
        e = by_key.get(key(code))
        if e and name and e.name and name.split()[0].upper() not in e.name.upper():
            print("  name differs - check:", code, name, "vs", e.emp_no, e.name)
        d = _day(str(when))
        if not e or not d:
            missing += 1; print("  not found / bad date:", code, name, when); continue
        if e.joined_on:
            skipped += 1; continue
        e.joined_on = d; filled += 1
    db.commit()
    print(f"Joining dates: {filled} filled, {skipped} already had one, {missing} not matched")

    # 2. Security cheques and deposits
    n = 0
    for party, amt, given, no, remark in CHEQUES:
        if db.query(SC.SecurityCheque).filter(SC.SecurityCheque.kind == "cheque", SC.SecurityCheque.cheque_no == no,
                                              SC.SecurityCheque.amount == amt).first():
            continue
        purpose, project, notes = _cheque_fields(remark)
        db.add(SC.SecurityCheque(kind="cheque", party=party, purpose=purpose, project=project, bank=BANK, cheque_no=no,
                                 amount=amt, cheque_date=None, given_on=_day(given), remind_on=REMIND, status="held", notes=notes))
        n += 1
    for party, desc, amt, given, remark in DEPOSITS:
        purpose = desc.capitalize().replace("Security deposit - ", "Security deposit - ")
        if db.query(SC.SecurityCheque).filter(SC.SecurityCheque.kind == "deposit", SC.SecurityCheque.amount == amt,
                                              SC.SecurityCheque.given_on == _day(given)).first():
            continue
        db.add(SC.SecurityCheque(kind="deposit", party=party,
                                 purpose=purpose, project="", bank="", cheque_no="", amount=amt, cheque_date=None,
                                 given_on=_day(given), remind_on=REMIND, status="held", notes=remark.capitalize()))
        n += 1
    db.commit()
    print(f"Security cheques and deposits: {n} added")

    # 3. Saved logins (encrypted)
    seen = {(c.name.lower(), (c.username or "").lower()) for c in db.query(CR.Credential).all()}
    added = 0
    for x in LOGINS:
        key = (x["name"].lower(), (x["username"] or "").lower())
        if key in seen:
            continue
        dom = CR.domain_of(x["url"])
        c = CR.Credential(name=x["name"][:80], url=x["url"], domain=dom, kind="login",
                          category=x["category"] if x["category"] in CR.CATEGORIES else "Other",
                          username=x["username"], secret=CR.lock(x["secret"]), notes=CR.lock(x["notes"]),
                          logo=CR.fetch_logo(dom) if dom else "", admin_only=False)
        db.add(c); db.commit(); seen.add(key); added += 1
        print("  login:", x["name"], "-", "logo found" if c.logo else "no logo")
    print(f"Saved logins: {added} added")
    db.close()


if __name__ == "__main__":
    main()

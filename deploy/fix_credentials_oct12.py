"""Fix of 12 Oct 2026: the saved logins fed from password_details.xlsx.

The first feed copied the name of the row above into rows that had no
name (so the office Wi-Fi and the PO Box showed under SYNOLOGY), put
everything in "Email & IT", and kept values in the wrong fields (a
cPanel address as the username, a Webflow password as the username).

This takes out exactly the logins the first feed added (same name and
username) and puts the sheet in again, row by row, read properly.
Logins added or changed by hand since are not touched.

    cd ~/infinia-labour-tool && venv/bin/python deploy/fix_credentials_oct12.py
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, HERE)
from clear_test_returns import _find_database_url

url = os.environ.get("DATABASE_URL") or _find_database_url()
if not url:
    sys.exit("Could not find DATABASE_URL.")
os.environ["DATABASE_URL"] = url
os.environ.setdefault("INFINIA_NO_PUSH", "1")
import main as M          # noqa: E402
import credentials as CR  # noqa: E402
from database import SessionLocal  # noqa: E402
import ast  # noqa: E402
# what the first feed put in (read from that script, without running it)
_src = open(os.path.join(HERE, "load_oct12_feed.py")).read()
OLD = next(ast.literal_eval(n.value) for n in ast.parse(_src).body
           if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "LOGINS")

NO_LOGO = os.environ.get("INFINIA_NO_LOGO") == "1"     # tests: no web calls

# category, name, website, kind, username, password / PIN, notes   (sheet row)
NEW = [
 ("Email & IT", "Job portal mail ID", "https://mail.google.com", "login", "infiniacontracing.job@gmail.com", "Infinia@2025", ""),          # 2
 ("Email & IT", "Job portal mail ID", "https://mail.google.com", "login", "INFINIAJOBS@GMAIL.COM", "Infinia@2025", ""),                    # 3
 ("Email & IT", "Accounts mailbox", "", "login", "accounts@infinia.ae", "accounts765!", ""),                                                 # 4
 ("Email & IT", "Info mailbox", "", "login", "info@infina.ae", "Infoinfi876#", "As written in the sheet (infina.ae)"),                      # 5
 ("Email & IT", "Prime Infinia Gmail", "https://mail.google.com", "login", "primeinfiniatechnicalservices@gmail.com", "Infinia@2026", ""),  # 6
 ("Email & IT", "Enginova Gmail", "https://mail.google.com", "login", "enginova.office@gmail.com", "enginova@123", ""),                     # 7
 ("Software", "Zoho Books", "https://books.zoho.com/", "login", "accounts@infinia.ae", "Zoho@2026", ""),                                   # 8
 ("Software", "Synology (office server)", "https://quickconnect.to", "login", "Anoop", "Infinia@2026", ""),                                # 9
 ("Software", "Synology (office server)", "https://quickconnect.to", "login", "Arathi", "Infinia@2026", ""),                               # 10
 ("Software", "Synology (office server)", "https://quickconnect.to", "login", "FrontDesk", "Infinia@2026", ""),                            # 11
 ("Software", "Synology (office server)", "https://quickconnect.to", "login", "Accounts", "Shafeeq@2025", ""),                             # 12
 ("Office", "Office Wi-Fi", "", "login", "", "p@infinia", ""),                                                                              # 13
 ("Office", "PO Box", "", "note", "", "", "PO Box 85567"),                                                                                 # 14
 ("Utilities", "DEWA account", "https://www.dewa.gov.ae", "login", "infiniacontracting", "Infiniadxb1#", ""),                              # 15
 ("Email & IT", "Gmail (company)", "https://mail.google.com", "login", "infiniacontracting@gmail.com", "Infiniadxb1#", ""),                 # 16
 ("Government", "DM & DED", "https://www.dm.gov.ae", "login", "pro@infinia.ae", "pro@jomon1", ""),                                         # 17
 ("Government", "Labour Dept (MOHRE) - company number", "https://www.mohre.gov.ae", "note", "", "", "Company number 1462908"),             # 18
 ("Government", "FTA (tax)", "https://eservices.tax.gov.ae", "login", "infiniacontracting@gmail.com", "Account@infinia1", ""),             # 19
 ("Utilities", "Etisalat NIC portal", "https://m.nic.ae", "login", "6410356138", "Infiniadxb1#", ""),                                     # 20
 ("Utilities", "Etisalat business portal", "https://www.etisalat.ae", "login", "infiniacontracting@gmail.com", "Infiniadxb1!", ""),       # 21
 ("Office", "Office router", "http://192.168.1.1", "login", "admin", "admin123", "Router address 192.168.1.1"),                           # 22
 ("Email & IT", "BigRock (domain)", "https://www.bigrock.in", "login", "infiniacontracting@gmail.com", "Infinia@2026", ""),               # 23
 ("Email & IT", "WordPress", "https://wordpress.com", "login", "Infiniacontracting", "Infiniadxb1#", ""),                                 # 24
 ("Email & IT", "cPanel (BigRock hosting)", "https://sh003.bigrock.com:2083/", "login", "", "infin5y6", ""),                             # 25
 ("Email & IT", "Webmail", "https://webmail.infinia.ae", "login", "info@infinia.ae", "Info@654#", ""),                                   # 26 + 27
 ("Government", "RTA", "https://www.rta.ae", "login", "praveenissac", "Infiniadxb1#", ""),                                                # 28
 ("Government", "Salik", "https://www.salik.ae", "login", "35616618", "4276", "Account number and PIN"),                                  # 29
 ("Government", "Salik - our car", "https://www.salik.ae", "login", "35630592", "7495", "Account number and PIN"),                        # 30 (39 is the same)
 ("Office", "Locker", "", "pin", "", "#9847#", ""),                                                                                        # 31
 ("Government", "Indian Embassy - eMigrate", "https://emigrate.gov.in", "login", "FE5800171", "X4A6A@Px", ""),                            # 32
 ("Government", "Traffic code number", "https://www.rta.ae", "note", "", "", "Traffic code number 50516190"),                            # 33
 ("Government", "eMigrate", "https://emigrate.gov.in", "login", "FE5800171", "Infinia@pro1", "Security question - pet name: Infinia@123"),  # 34
 ("Government", "DDA", "https://www.dda.gov.ae", "login", "pro@infinia.ae", "Infinia@dda2026", ""),                                       # 35
 ("Government", "DDA", "https://www.dda.gov.ae", "login", "office@infinia.ae", "infinia@123", ""),                                        # 36
 ("Government", "Emirates Post portal", "https://www.emiratespost.ae", "login", "pro@infinia.ae", "Epostinfinia@1", ""),                  # 37
 ("Government", "Salik (online account)", "https://www.salik.ae", "login", "Infiniasalik", "Infiniasalik@123", ""),                      # 38
 ("Utilities", "Etisalat login", "https://www.etisalat.ae", "login", "pro@infinia.ae", "Infinia@etisalat26", ""),                        # 40
 ("Government", "Dubai Building Permit System", "https://www.dm.gov.ae", "login", "infinia", "Infinia@123", ""),                         # 41
 ("Government", "Trakhees portal", "https://www.trakhees.ae", "login", "infiniaprojects", "Voss#12345", ""),                             # 42
 ("Government", "DEQ", "", "login", "pro@infinia.ae", "pro@jomon1", ""),                                                                  # 43
 ("Government", "eSupply (Dubai)", "https://esupply.dubai.gov.ae", "login", "Infiniacontracting", "Infinia123", ""),                      # 44
 ("Email & IT", "cPanel (BigRock hosting)", "https://sh003.bigrock.com:2083/", "login", "", "Classmate123#", "Second password in the sheet - check which one is current"),  # 45
 ("Email & IT", "Webflow (website hosting)", "https://webflow.com", "login", "infiniacontracting@gmail.com", "infi@UAE25", ""),           # 46
 ("Government", "Emirates Post", "https://www.emiratespost.ae", "login", "engineers@infinia.ae", "EPInfini@23", ""),                      # 47
 ("Utilities", "Etisalat portal", "https://www.etisalat.ae", "login", "", "Infinia@etisalat27", "The sheet has no username for this one - may be the newer password of 'Etisalat login' (pro@infinia.ae)"),  # 48
 ("Government", "Makani number (office)", "https://www.makani.ae", "note", "", "", "Makani number 3327696938"),                         # 49
 ("Email & IT", "Microsoft email", "https://outlook.office.com", "login", "accounts@infinia.ae", "Acc@inf*2020!", ""),                    # 50
 ("Email & IT", "Microsoft email", "https://outlook.office.com", "login", "info@infinia.ae", "Inf@Inf*9511!", ""),                        # 51
 ("Government", "DCD portal (Civil Defence)", "https://www.dcd.gov.ae", "login", "infiniadcd25", "Infiniadcd@25", ""),                    # 52
 ("Software", "ChatGPT Plus", "https://chatgpt.com", "login", "engineers@infinia.ae", "infinia@engineers", ""),                           # 53
 ("Utilities", "DEWA business", "https://www.dewa.gov.ae", "login", "Infiniadewa", "Infinia1#", ""),                                      # 54
]


def main():
    db = SessionLocal()
    old = {(x["name"].lower(), (x["username"] or "").lower()) for x in OLD}
    removed = 0
    for c in db.query(CR.Credential).all():
        if (c.name.lower(), (c.username or "").lower()) in old:
            db.delete(c); removed += 1
    db.commit()
    have = {(c.name.lower(), (c.username or "").lower(), CR.unlock(c.secret)) for c in db.query(CR.Credential).all()}
    logos = {}
    added = 0
    for cat, name, site, kind, user, secret, notes in NEW:
        if (name.lower(), user.lower(), secret) in have:
            continue
        dom = CR.domain_of(site) if site and not site.startswith("http://192.") else ""
        if dom and dom not in logos:
            logos[dom] = "" if NO_LOGO else CR.fetch_logo(dom)
        db.add(CR.Credential(name=name[:80], url=site, domain=dom, kind=kind,
                             category=cat if cat in CR.CATEGORIES else "Other",
                             username=user, secret=CR.lock(secret), notes=CR.lock(notes),
                             logo=logos.get(dom, ""), admin_only=False))
        added += 1
    db.commit()
    M.log_action(db, None, "credential_changed", f"Saved logins re-entered from the sheet: {removed} taken out, {added} put in")
    db.close()
    print(f"Saved logins: {removed} taken out, {added} put in again (read properly).")


if __name__ == "__main__":
    main()

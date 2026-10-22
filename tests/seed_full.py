"""A full, live-like database for the whole-app sweep: every login the UI tests sign in as, two payroll cycles
of attendance (seed_scenarios.py), Estimation data, and - from the seed_full_*.py parts when present - store,
purchasing, accounts, petty cash, PDCs, HR payroll, documents and expiries.

    python3 tests/seed_full.py [/tmp/full.db]       (base only:  BASE_ONLY=1)
"""
import os, sys, runpy, importlib

DB = sys.argv[1] if len(sys.argv) > 1 else "/tmp/full.db"
os.environ["DATABASE_URL"] = "sqlite:///" + DB
os.environ.setdefault("INFINIA_NO_SCHED", "1")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.join(ROOT, "app"))
sys.path.insert(0, "."); sys.path.insert(0, os.path.join(ROOT, "tests"))
if os.path.exists(DB) and not os.environ.get("KEEP"):
    os.remove(DB)

import database, models, auth  # noqa: E402
models.Base.metadata.create_all(database.engine)
import main  # noqa: E402,F401

ALL_ACC = "accounts_invoices,petty_site,petty_pro,petty_office,petty_naveen,petty_praveen,accounts_projects,accounts_expense,accounts_bank,accounts_zoho,accounts_register"
USERS = [  # username, password, name, role, broad rights
    ("amaltest", "amal12345", "Amal", "office", "store,storekeeper,requests,followup,petty_site"),
    ("chiefacc", "chief12345", "Shafeeq", "office", "pdc,security_cheques,settings,accounts_invoices,accounts_register,petty_naveen,petty_praveen,accounts_projects,approvals,store,requests,expiry"),
    ("shafiq", "pass12345", "Shafeeq S", "office", "accounts_bank,accounts_zoho"),
    ("docsonly", "docs12345", "Docs Clerk", "office", "expiry,docs_send"),
    ("protest", "pro12345", "Jomon", "office", "petty_pro,expiry"),
    ("invonly", "inv12345", "Invoice Clerk", "office", "accounts_invoices"),
    ("acctest", "acc12345", "Muhsina", "office", ALL_ACC + ",docs_verify"),
    ("hrtest", "hr12345", "HR Officer", "office", "hrpayroll,people_labour,people_office,people_local,expiry,combine,adjustments,errorcheck,reports,attendance"),
    ("siteeng", "site12345", "Site Engineer", "site", "attendance"),
    ("esttest", "est12345", "Anoop", "office", "estimation_projects,estimation_boards"),
    ("sweepuser", "sweep123", "Sweep User", "office", "people_labour,people_office"),
    ("jomon", "pass12345", "Jomon", "office", "petty_pro,expiry,docs_send"),
    ("muhsina", "pass12345", "Muhsina", "office", ALL_ACC + ",docs_verify,docs_send"),
    ("amal", "pass12345", "Amal", "office", "store,storekeeper,requests,followup,petty_site,docs_send"),
    ("keeper2", "keep12345", "Keeper Two", "office", "store,storekeeper,requests,followup,petty_site"),
    ("assistant", "pass12345", "Assistant", "office", "dashboard,attendance,reports"),
]
d = database.SessionLocal()
have = {u.username for u in d.query(models.User).all()}
for un, pw, name, role, rights in USERS:
    if un not in have:
        d.add(models.User(username=un, hashed_password=auth.hash_password(pw), full_name=name, role=role, permissions=rights))
d.commit(); d.close()
print("users ready:", ", ".join(u[0] for u in USERS))

os.environ.setdefault("ADMIN_PW", "changeme123")
sys.argv = [sys.argv[0]]
runpy.run_path(os.path.join(ROOT, "tests", "seed_scenarios.py"), run_name="__main__")

if not os.environ.get("BASE_ONLY"):
    from fastapi.testclient import TestClient
    c = TestClient(main.app); c.__enter__()
    tok = c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]
    H = {"Authorization": "Bearer " + tok}
    for part in ("seed_full_store", "seed_full_accounts", "seed_full_hr"):
        try:
            m = importlib.import_module(part)
        except ModuleNotFoundError:
            print("(no", part + ")"); continue
        print("==", part); m.run(c, H)
print("FULL DATABASE READY:", DB)

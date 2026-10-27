"""Data for the Help pictures, on a COPY of a test database (never the live one):
Estimation filled on every tab (the reversible dummy data), the 914 / 915 / 919 submittal logs, a client bill
laid out like 914's (with a draft bill on it), and a Trello board with lists, cards, due dates and time logged.

    python3 tests/make_ipa_like_914.py /tmp/claude-0/bills/914-like.xlsx
    cp /tmp/claude-0/bn.db /tmp/help.db
    cd app && DATABASE_URL=sqlite:////tmp/help.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/seed_help_data.py
"""
import os, sys, json, subprocess
from datetime import date, timedelta
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main as M
import estimation as E
import est_dummy as ED
from database import SessionLocal

BILL = os.environ.get("BILL", "/tmp/claude-0/bills/914-like.xlsx")
c = TestClient(M.app); c.__enter__()
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}

# 1. the real submittal logs of 914, 915, 919
here = os.path.dirname(os.path.abspath(__file__))
r = subprocess.run([sys.executable, os.path.join(here, "..", "deploy", "load_submittals.py")], env=dict(os.environ), capture_output=True, text=True)
print((r.stdout or r.stderr).strip()[-300:])

# 2. (after the loader: starting the app takes the dummy rows out again) Estimation: every tab (subcontracts, certificates at every step, client certificates, BOQ, RFIs, submittals...)
db = SessionLocal()
try:
    ED.create(db)
    db.query(ED.EstDummy).delete()      # on this copy they stay as ordinary rows (a start-up would otherwise take them out)
    db.commit()
except Exception as e:
    print("dummy data:", e)
db.close()

# 3. a client bill on 914: the format (as the consultant's workbook) and this month's bill
projects = {p["code"]: p["id"] for p in c.get("/store/est/meta", headers=H).json()["projects"]}
pid = projects.get("914") or next(iter(projects.values()))
if os.path.exists(BILL) and not c.get(f"/store/est/ipa/list?project_id={pid}", headers=H).json()["formats"]:
    f = c.post("/store/est/ipa/format", headers=H, data={"project_id": str(pid)}, files={"file": ("914 - IPA - 07.xlsx", open(BILL, "rb").read(), "application/octet-stream")})
    print("bill format:", f.status_code)
    b = c.post("/store/est/ipa/new", headers=H, json={"project_id": pid}).json()
    if b.get("id"):
        c.post(f"/store/est/ipa/bill/{b['id']}/line", headers=H, json={"sheet": "Division 03-Concrete Works", "after": 12,
               "values": {"item": "3.2.2.3", "desc": "Additional lintel beams", "unit": "M3", "c5": 4, "c6": 2000}})
        print("bill:", b["id"])

# 4. Trello: a board with lists, cards, due dates, members and time
if not c.get("/store/kb/boards", headers=H).json().get("boards"):
    bd = c.post("/store/kb/boards", headers=H, json={"title": "Estimation"}).json()
    t = date.today()
    for li, (lt, cards) in enumerate([("To do", ["914 - Prepare IPA 08", "915 - Submit shop drawings", "919 - Price variation V07"]),
                                      ("Doing", ["909 - Joinery subcontract review", "920 - BOQ for phase 2"]),
                                      ("Done", ["914 - Submittal log updated"])]):
        l = c.post(f"/store/kb/boards/{bd['id']}/lists", headers=H, json={"title": lt}).json()
        for ci, ct in enumerate(cards):
            cd = c.post(f"/store/kb/lists/{l['id']}/cards", headers=H, json={"title": ct}).json()
            c.patch(f"/store/kb/cards/{cd['id']}", headers=H, json={"due": (t + timedelta(days=2 + ci * 3 + li)).isoformat(), "start": t.isoformat()})
            if ci == 0:
                c.post(f"/store/kb/cards/{cd['id']}/time", headers=H, json={"hours": 2.5, "note": "Measured on site"})
    print("trello board:", bd.get("id"))
print("est project for the pictures:", pid)

"""The chief accountant puts the project on a petty cash line in Send to
Zoho: saved on the petty cash line itself, sent to Zoho as the project."""
import os, sys, tempfile
from datetime import date
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
os.environ["INFINIA_CRED_KEY_FILE"] = tempfile.mktemp(suffix=".key")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as M, models, zohoapi as Z, zohosync as ZS, credentials
from database import SessionLocal, engine
from fastapi import HTTPException
models.Base.metadata.create_all(bind=engine); M._add_missing_columns()
s = SessionLocal(); fails = 0
def ok(c, m):
    global fails
    print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1
POSTED = []
def fake(db_, method, path, params=None, body=None):
    if method == "GET" and path == "chartofaccounts":
        return {"chartofaccounts": [{"account_name": "Site Petty Cash", "account_id": "S"}, {"account_name": "Company Petty Cash", "account_id": "C"},
                                    {"account_name": "Machinery Rent", "account_id": "MR", "account_type": "cost_of_goods_sold"}], "page_context": {}}
    if method == "GET" and path == "projects":
        return {"projects": [{"project_code": "913", "project_id": "PRJ913", "customer_id": "C913"}]}
    if method == "POST":
        POSTED.append((path, body)); return {"expense": {"expense_id": "E1"}}
    return {}
Z._call = fake
M.put_setting(s, "zoho_refresh", credentials.lock("rt")); s.commit()
u = models.User(username="ca", full_name="Shafeeq", hashed_password="x", role="admin"); s.add(u)
s.add_all([models.Site(code="913"), models.Site(code="920")])
x = models.PettyCash(book="office", on_date=date(2026, 10, 15), description="Generator rent", paid=750, site="")
s.add(x); s.commit()
ZS.set_site({"id": x.id, "site": "913"}, s, u); s.refresh(x)
ok(x.site == "913", "project picked in Send to Zoho is saved on the petty cash line")
ok(s.query(models.AuditLog).filter(models.AuditLog.action == "petty_site").count() == 1, "the change is in the activity log")
try:
    ZS.set_site({"id": x.id, "site": "999"}, s, u); ok(False, "unknown project refused")
except HTTPException:
    ok(True, "unknown project refused")
ZS.set_site({"id": x.id, "site": "920"}, s, u); s.refresh(x)
ok(x.site == "920", "can be corrected before approval")
POSTED.clear()
r = ZS.approve({"lines": [{"id": x.id, "account": "Machinery Rent", "site": "913"}]}, s, u); s.refresh(x)
ok(r["approved"] == 1 and x.site == "913", "changed again on approval: the petty cash line takes it")
ok(POSTED and POSTED[0][1].get("project_id") == "PRJ913", f"sent to Zoho with the project ({POSTED[0][1].get('project_id') if POSTED else None})")
try:
    ZS.set_site({"id": x.id, "site": "920"}, s, u); ok(False, "")
except HTTPException as e:
    ok("already" in e.detail, "after it is approved, the project is changed in Zoho, not here")
print("fails=", fails)

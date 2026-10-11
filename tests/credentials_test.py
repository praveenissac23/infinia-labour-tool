"""Accounts > Credentials: encrypted at rest, only for those given the tab,
every password shown is logged (and alerted when not the admin), papers
never carry a password."""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
os.environ.setdefault("INFINIA_NO_PUSH", "1")
os.environ["INFINIA_CRED_KEY_FILE"] = os.path.join(tempfile.mkdtemp(), "k.key")
from fastapi.testclient import TestClient
import main, models, auth, watch, credentials as CRD
from database import SessionLocal
from unittest import mock

db = SessionLocal()
db.add(models.User(username="boss", hashed_password=auth.hash_password("p"), full_name="Boss", role="admin"))
db.add(models.User(username="pro", hashed_password=auth.hash_password("p"), full_name="Jomon", role="office", permissions="dashboard,accounts_credentials"))
db.add(models.User(username="site", hashed_password=auth.hash_password("p"), full_name="Site", role="office", permissions="dashboard,store"))
db.commit(); db.close()
c = TestClient(main.app)
tok = lambda u: {"Authorization": "Bearer " + c.post("/auth/login", data={"username": u, "password": "p"}).json()["access_token"]}
B, P, S = tok("boss"), tok("pro"), tok("site")
FAIL = []
def ck(l, ok, x=""):
    print(("PASS " if ok else "FAIL ") + l + ("" if ok else f"  [{x}]"))
    if not ok: FAIL.append(l)

with mock.patch.object(CRD, "fetch_logo", lambda d: "data:image/png;base64,AAAA" if d else ""), \
     mock.patch.object(CRD, "fetch_title", lambda u: "DEWA"):
    r = c.get("/employees/accounts/credentials/lookup?url=https://www.dewa.gov.ae/en/login", headers=P)
    ck("lookup: domain, name from the page title, logo", r.json() == {"domain": "dewa.gov.ae", "name": "DEWA", "logo": "data:image/png;base64,AAAA"}, r.text)
    r = c.post("/employees/accounts/credentials", headers=P, json={"url": "https://www.dewa.gov.ae", "name": "DEWA", "kind": "login",
               "category": "Utilities", "username": "accounts@infinia.ae", "secret": "S3cret!x", "notes": "token with Jomon"})
    ck("PRO adds a login", r.status_code == 200 and r.json()["logo"].startswith("data:image"), r.text[:200])
    cid = r.json()["id"]
    r = c.post("/employees/accounts/credentials", headers=P, json={"name": "Office door", "kind": "pin", "category": "Other", "secret": "4821"})
    pin = r.json()["id"]
s = SessionLocal(); row = s.get(CRD.Credential, cid); s.close()
ck("password is not stored as typed", row.secret and "S3cret" not in row.secret and "Jomon" not in row.notes, row.secret[:20])
lst = c.get("/employees/accounts/credentials", headers=P).json()["rows"]
ck("the list carries no password", all("secret" not in x and "notes" not in x for x in lst) and "S3cret" not in str(lst), lst)
ck("a login without the tab is refused", c.get("/employees/accounts/credentials", headers=S).status_code == 403)
r = c.post(f"/employees/accounts/credentials/{cid}/reveal", headers=P, json={"how": "copy"})
ck("reveal gives the password and notes", r.json() == {"secret": "S3cret!x", "notes": "token with Jomon"}, r.text)
s = SessionLocal(); al = [a for a in s.query(watch.WatchAlert).all() if a.action == "credential_shown"]; s.close()
ck("PRO copying a password alerts the admin", al and "DEWA" in al[-1].detail and "copied" in al[-1].detail, [(a.action, a.detail) for a in al])
n = len(al)
c.post(f"/employees/accounts/credentials/{pin}/reveal", headers=B, json={"how": "show"})
s = SessionLocal(); al = [a for a in s.query(watch.WatchAlert).all() if a.action == "credential_shown"]; s.close()
ck("admin's own look is logged, not alerted", len(al) == n)
s = SessionLocal(); logged = s.query(models.AuditLog).filter(models.AuditLog.action == "credential_shown").count(); s.close()
ck("both looks are in the activity log", logged == 2, logged)
# Editing without typing a password keeps it
r = c.put(f"/employees/accounts/credentials/{cid}", headers=P, json={"url": "https://www.dewa.gov.ae", "name": "DEWA Business", "kind": "login",
          "category": "Utilities", "username": "accounts@infinia.ae", "logo": "data:image/png;base64,AAAA"})
ck("edit keeps the password when none typed", c.post(f"/employees/accounts/credentials/{cid}/reveal", headers=P, json={}).json()["secret"] == "S3cret!x")
# Papers: no password
t = c.post("/auth/download-token", headers=P).json()["token"]
for f in ("pdf", "excel"):
    x = c.get(f"/export/accounts/credentials?format={f}&token={t}")
    ck(f"{f} export works", x.status_code == 200 and len(x.content) > 500, x.status_code)
x = c.get(f"/export/accounts/credentials/view?token={t}")
ck("preview lists the logins, never a password", x.status_code == 200 and "DEWA Business" in x.text and "S3cret" not in x.text and "4821" not in x.text, x.status_code)
ts = c.post("/auth/download-token", headers=S).json()["token"]
ck("export refused without the tab", c.get(f"/export/accounts/credentials/view?token={ts}").status_code == 403)
g = c.get("/employees/accounts/credentials/generate", headers=P).json()["password"]
ck("generated password is strong", len(g) >= 14 and any(ch.isdigit() for ch in g) and any(ch.isupper() for ch in g), g)
# Delete by PRO: alert
c.delete(f"/employees/accounts/credentials/{pin}", headers=P)
s = SessionLocal(); ok = any(a.action == "credential_deleted" for a in s.query(watch.WatchAlert).all()); s.close()
ck("deleted by PRO -> admin alerted", ok)
# Start-up grant: the PRO and Chief Accountant roles get the tab, others not
s = SessionLocal()
s.query(models.Setting).filter(models.Setting.key == "credentials_granted").delete()
for nm in ("PRO", "Chief Accountant", "Store Keeper"):
    s.add(models.AccessRole(name=nm, screens="dashboard,store"))
s.commit()
rid = s.query(models.AccessRole).filter_by(name="PRO").first().id
s.add(models.User(username="jomon2", full_name="Jomon", hashed_password="x", role="office", permissions="dashboard,store", access_role_id=rid)); s.commit()
CRD.grant_once(s)
roles = {r.name: r.screens for r in s.query(models.AccessRole).all()}
u = s.query(models.User).filter_by(username="jomon2").first().permissions
s.close()
ck("PRO and Chief Accountant roles get the tab", "accounts_credentials" in roles["PRO"] and "accounts_credentials" in roles["Chief Accountant"], roles)
ck("Store Keeper does not", "accounts_credentials" not in roles["Store Keeper"])
ck("a login on the PRO role gets it too", "accounts_credentials" in u, u)
# The real logo fetcher: Google's plain globe is not taken as a logo
with mock.patch.object(CRD, "_get", side_effect=[(b"x" * 300, "image/png"), (b"\x89PNG\r\n\x1a\n" + b"y" * 900, "image/png")]):
    ck("globe skipped, next icon used", CRD.fetch_logo("example.ae").startswith("data:image/png;base64,"))
with mock.patch.object(CRD, "_get", return_value=(b"<html><title>DEWA | Dubai Electricity</title>", "text/html")):
    ck("page title trimmed to the name", CRD.fetch_title("dewa.gov.ae") == "DEWA", CRD.fetch_title("dewa.gov.ae"))
ck("name from a domain", CRD.name_from_domain("dubaitrade.ae") == "Dubaitrade" and CRD.name_from_domain("mohre.gov.ae") == "Mohre")
print("\nALL PASS" if not FAIL else f"\n{len(FAIL)} FAILED: {FAIL}")

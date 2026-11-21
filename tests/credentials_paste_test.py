"""Accounts > Credentials > Paste a list (21/11/2026): logins pasted the way they are sent on WhatsApp
("*Heading*", "Username: x", "Username : x", "Password: y" with * and @ inside), read, shown back without the
passwords, saved encrypted on one press, admin only, already-saved ones skipped. Made-up passwords only."""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
os.environ.setdefault("INFINIA_NO_PUSH", "1")
os.environ["INFINIA_CRED_KEY_FILE"] = os.path.join(tempfile.mkdtemp(), "k.key")
from fastapi.testclient import TestClient
import main, models, auth, credentials as CRD
from database import SessionLocal
from unittest import mock

db = SessionLocal()
db.add(models.User(username="boss", hashed_password=auth.hash_password("p"), full_name="Boss", role="admin"))
db.add(models.User(username="acc", hashed_password=auth.hash_password("p"), full_name="Accounts", role="office", permissions="dashboard,accounts_credentials"))
db.commit(); db.close()
c = TestClient(main.app)
tok = lambda u: {"Authorization": "Bearer " + c.post("/auth/login", data={"username": u, "password": "p"}).json()["access_token"]}
B, A = tok("boss"), tok("acc")
FAIL = []
def ck(l, ok, x=""):
    print(("PASS " if ok else "FAIL ") + l + ("" if ok else f"  [{x}]"))
    if not ok: FAIL.append(l)

LIST = """*Company email login credentials*

Username: one@example.com
Password: Ab@Cd*123

Username: two@example.com
Password: Two@321

Username : three@example.com
Password : Thr@ee#9

Username: four@example.com
Password: F*our!x*
"""
p = CRD.parse_list(LIST)
ck("parse: four logins, heading skipped", [x["username"] for x in p] == ["one@example.com", "two@example.com", "three@example.com", "four@example.com"], p)
ck("parse: passwords exactly as typed (* @ # ! kept, spaces around trimmed)", [x["secret"] for x in p] == ["Ab@Cd*123", "Two@321", "Thr@ee#9", "F*our!x*"], [x["secret"] for x in p])
ck("parse: other labels (Email / Pass / Website)", CRD.parse_list("Website: dewa.gov.ae\nEmail: a@b.com\nPass: x1") == [{"username": "a@b.com", "secret": "x1", "url": "dewa.gov.ae"}],
   CRD.parse_list("Website: dewa.gov.ae\nEmail: a@b.com\nPass: x1"))
ck("parse: a username with no password is kept (flagged later)", CRD.parse_list("Username: a\nUsername: b\nPassword: y") == [{"username": "a", "secret": "", "url": ""}, {"username": "b", "secret": "y", "url": ""}])
ck("parse: nothing recognisable -> empty", CRD.parse_list("hello\nworld") == [])

with mock.patch.object(CRD, "fetch_logo", lambda d: "data:image/png;base64,AAAA" if d else ""):
    r = c.post("/employees/accounts/credentials/paste", headers=A, json={"text": LIST})
    ck("not admin: refused", r.status_code == 403, r.status_code)
    r = c.post("/employees/accounts/credentials/paste", headers=B, json={"text": "nothing here"})
    ck("no logins in the text: a clear message", r.status_code == 400 and "Username" in r.json()["detail"], r.text)
    r = c.post("/employees/accounts/credentials/paste", headers=B, json={"text": LIST, "category": "Email & IT", "admin_only": True})
    d = r.json()
    ck("check: four rows ready, nothing saved yet", r.status_code == 200 and [x["state"] for x in d["rows"]] == ["ok"] * 4 and d["saved"] == 0, r.text[:300])
    ck("check: the answer never carries a password", "Ab@Cd*123" not in r.text and "Two@321" not in r.text and d["rows"][0]["chars"] == 9, r.text[:300])
    ck("check: named by the email, domain from the email", d["rows"][0]["name"] == "one@example.com" and d["rows"][0]["domain"] == "example.com", d["rows"][0])
    s = SessionLocal(); n0 = s.query(CRD.Credential).count(); s.close()
    ck("check saved nothing", n0 == 0, n0)
    r = c.post("/employees/accounts/credentials/paste", headers=B, json={"text": LIST, "category": "Email & IT", "admin_only": True, "save": True})
    ck("save: four saved", r.json()["saved"] == 4 and all(x["state"] == "saved" for x in r.json()["rows"]), r.text[:300])
    s = SessionLocal(); rows = s.query(CRD.Credential).order_by(CRD.Credential.id).all()
    ck("saved encrypted, admin only, category, username", len(rows) == 4 and all(x.admin_only and x.category == "Email & IT" for x in rows)
       and "Ab@Cd*123" not in rows[0].secret and CRD.unlock(rows[0].secret) == "Ab@Cd*123" and CRD.unlock(rows[3].secret) == "F*our!x*"
       and rows[2].username == "three@example.com", [(x.username, x.admin_only, x.category) for x in rows])
    s.close()
    ck("accounts login does not see the admin-only ones", c.get("/employees/accounts/credentials", headers=A).json()["rows"] == [])
    ck("the admin sees all four", len(c.get("/employees/accounts/credentials", headers=B).json()["rows"]) == 4)
    rid = c.get("/employees/accounts/credentials", headers=B).json()["rows"][0]["id"]
    ck("the admin can reveal a pasted password", c.post(f"/employees/accounts/credentials/{rid}/reveal", headers=B, json={"how": "show"}).json().get("secret") in ("Ab@Cd*123", "Two@321", "Thr@ee#9", "F*our!x*"))
    r = c.post("/employees/accounts/credentials/paste", headers=B, json={"text": LIST + "\nUsername: five@example.com\nPassword: Fi5e\nUsername: six@example.com\n", "save": True})
    st = [x["state"] for x in r.json()["rows"]]
    ck("pasted again: the four skipped as already saved, the new one saved, one without password skipped",
       st == ["already saved"] * 4 + ["saved", "no password"] and r.json()["saved"] == 1, st)
    r = c.post("/employees/accounts/credentials/paste", headers=B, json={"text": "Username: info@example.com\nPassword: z1", "url": "outlook.office.com"})
    ck("with a website: name and logo from the website", r.json()["rows"][0]["name"] == "Office - info@example.com" and r.json()["rows"][0]["domain"] == "outlook.office.com", r.json()["rows"][0])
    log = SessionLocal().query(models.AuditLog).filter(models.AuditLog.action == "credential_added").all() if hasattr(models, "AuditLog") else None
    ck("activity log records the paste (count only, no passwords)", log is None or (any("pasted as a list" in (x.details or "") for x in log) and not any("Ab@Cd" in (x.details or "") for x in log)))
print("\n" + ("ALL PASS" if not FAIL else f"{len(FAIL)} FAILED"))
sys.exit(1 if FAIL else 0)

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
# 21/11/2026: Save all pressed three times while the first was still saving -> each login three times
import threading, time as _t
slow = lambda d: (_t.sleep(0.4), "data:image/png;base64,AAAA")[1]
with mock.patch.object(CRD, "fetch_logo", slow):
    TXT = "Username: x1@corp.com\nPassword: a1\nUsername: x2@corp.com\nPassword: a2"
    outs = []
    th = [threading.Thread(target=lambda: outs.append(c.post("/employees/accounts/credentials/paste", headers=B, json={"text": TXT, "save": True}).json())) for _ in range(3)]
    [t.start() for t in th]; [t.join() for t in th]
s = SessionLocal(); n = s.query(CRD.Credential).filter(CRD.Credential.username.in_(["x1@corp.com", "x2@corp.com"])).count(); s.close()
ck("three presses of Save all at once: each login saved once", n == 2 and sorted(o["saved"] for o in outs) == [0, 0, 2], (n, [o.get("saved") for o in outs]))
js = open(os.path.join(os.path.dirname(__file__), "..", "app-classic.html"), encoding="utf-8").read()
ck("the page lets one press through at a time (button shows Saving...)", "if (CR_PASTING) return;" in js and 'bt.textContent = "Saving..."' in js)
# the one-time fix takes out twins saved together, keeps the first, leaves older look-alikes
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "deploy"))
from datetime import datetime as _dt, timedelta as _td
s = SessionLocal()
base = _dt(2026, 11, 21, 5, 11)
mk = lambda **k: CRD.Credential(kind="login", category="Email & IT", admin_only=True, notes=CRD.lock(""), **k)
for i in range(3):
    s.add(mk(name="dup@corp.ae", username="dup@corp.ae", domain="corp.ae", secret=CRD.lock("P1"), created_at=base + _td(seconds=i * 20)))
s.add(mk(name="dup@corp.ae", username="dup@corp.ae", domain="corp.ae", secret=CRD.lock("OTHER"), created_at=base))           # different password: kept
s.add(mk(name="old@corp.ae", username="old@corp.ae", domain="corp.ae", secret=CRD.lock("P2"), created_at=base - _td(days=40)))
s.add(mk(name="old@corp.ae", username="old@corp.ae", domain="corp.ae", secret=CRD.lock("P2"), created_at=base))              # 40 days apart: kept
s.commit()
import importlib.util
spec = importlib.util.spec_from_file_location("fixtw", os.path.join(os.path.dirname(__file__), "..", "deploy", "fix_credential_twins_2026_11_21.py"))
FX = importlib.util.module_from_spec(spec); spec.loader.exec_module(FX)
g = FX.twins(s)
ck("fix: the two extra copies found, the first kept, the different password and the old look-alike left",
   sorted(x.username for x, _ in g) == ["dup@corp.ae", "dup@corp.ae"] and all(f.id < x.id for x, f in g), [(x.id, f.id, x.username) for x, f in g])
ids_before = s.query(CRD.Credential).count(); s.close()
FX.run(False)
s = SessionLocal(); ck("fix without --apply changes nothing", s.query(CRD.Credential).count() == ids_before); s.close()
FX.run(True)
s = SessionLocal(); ck("fix with --apply takes out exactly two", s.query(CRD.Credential).count() == ids_before - 2 and not FX.twins(s)); s.close()
print("\n" + ("ALL PASS" if not FAIL else f"{len(FAIL)} FAILED"))
sys.exit(1 if FAIL else 0)

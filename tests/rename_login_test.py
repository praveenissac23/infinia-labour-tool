"""Settings > Logins: Edit name (username and full name).

    cd app && DATABASE_URL=sqlite:////tmp/rn.db INFINIA_NO_SCHED=1 python3 ../tests/rename_login_test.py
"""
import os, sys
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main, models, auth
from database import SessionLocal
c = TestClient(main.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f" -> {x}"))
    if not ok: fails.append(n)
db = SessionLocal()
for un, perms, role in [("rn_a", "settings,settings_logins", "office"), ("rn_b", "settings", "office"), ("rn_c", "settings", "office")]:
    u = db.query(models.User).filter_by(username=un).first() or models.User(username=un, full_name=un, role=role, hashed_password=auth.hash_password("pass123456"))
    u.permissions = perms; db.add(u)
db.query(models.User).filter(models.User.username.in_(["rn_new", "rn_me"])).delete(synchronize_session=False)
db.commit()
def tok(u, p): return {"Authorization": "Bearer " + c.post("/auth/login", data={"username": u, "password": p}).json()["access_token"]}
A = tok("admin", "changeme123"); O = tok("rn_a", "pass123456"); B = tok("rn_b", "pass123456")
ids = {u.username: u.id for u in db.query(models.User).all()}
r = c.post(f"/users/{ids['rn_b']}/name", json={"username": " RN_New ", "full_name": "Rahul Nair"}, headers=A)
ck("admin renames a login", r.status_code == 200 and r.json()["username"] == "rn_new", r.text)
ck("new username signs in, password kept", c.post("/auth/login", data={"username": "rn_new", "password": "pass123456"}).status_code == 200)
ck("old username no longer signs in", c.post("/auth/login", data={"username": "rn_b", "password": "pass123456"}).status_code != 200)
ck("taken username refused", c.post(f"/users/{ids['rn_b']}/name", json={"username": "rn_c"}, headers=A).status_code == 400)
ck("space refused", c.post(f"/users/{ids['rn_b']}/name", json={"username": "rn x"}, headers=A).status_code == 400)
ck("empty refused", c.post(f"/users/{ids['rn_b']}/name", json={"username": " "}, headers=A).status_code == 400)
r = c.post(f"/users/{ids['rn_b']}/name", json={"full_name": "R. Nair"}, headers=A)
ck("full name alone", r.status_code == 200 and r.json()["full_name"] == "R. Nair" and r.json()["username"] == "rn_new")
ck("same username kept is fine", c.post(f"/users/{ids['rn_b']}/name", json={"username": "rn_new"}, headers=A).status_code == 200)
ck("logins user can rename a plain login", c.post(f"/users/{ids['rn_c']}/name", json={"full_name": "Cee"}, headers=O).status_code == 200)
ck("non-admin cannot rename the admin", c.post(f"/users/{ids['admin']}/name", json={"full_name": "x"}, headers=O).status_code == 403)
ck("without the Logins right refused", c.post(f"/users/{ids['rn_c']}/name", json={"full_name": "x"}, headers=tok("rn_new", "pass123456")).status_code == 403)
r = c.post(f"/users/{ids['rn_a']}/name", json={"username": "rn_me"}, headers=O)
ck("renaming yourself asks to sign in again", r.status_code == 200 and r.json()["signin_again"] is True, r.text)
c.post(f"/users/{ids['rn_a']}/name", json={"username": "rn_a"}, headers=tok("admin", "changeme123"))
print("\nALL PASS" if not fails else f"\n{len(fails)} failed"); sys.exit(1 if fails else 0)

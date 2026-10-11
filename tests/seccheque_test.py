"""Security cheques: only for those given the tab; undated by default;
the bell reminds a week before the collect-back date and after it until
the cheque is marked collected back; changes by staff alert the admin."""
import os, sys
from datetime import timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
os.environ.setdefault("INFINIA_NO_PUSH", "1")
from fastapi.testclient import TestClient
import main, models, auth, watch, seccheque as SCM
from database import SessionLocal

db = SessionLocal()
db.add(models.User(username="boss", hashed_password=auth.hash_password("p"), full_name="Boss", role="admin"))
db.add(models.User(username="pro", hashed_password=auth.hash_password("p"), full_name="Jomon", role="office", permissions="dashboard,security_cheques"))
db.add(models.User(username="site", hashed_password=auth.hash_password("p"), full_name="Site", role="office", permissions="dashboard,expiry"))
db.commit(); db.close()
c = TestClient(main.app)
tok = lambda u: {"Authorization": "Bearer " + c.post("/auth/login", data={"username": u, "password": "p"}).json()["access_token"]}
B, P, S = tok("boss"), tok("pro"), tok("site")
FAIL = []
def ck(l, ok, x=""):
    print(("PASS " if ok else "FAIL ") + l + ("" if ok else f"  [{x}]"))
    if not ok: FAIL.append(l)
T = main._dubai_today()

r = c.post("/employees/security-cheques", headers=P, json={"party": "Emaar", "purpose": "Performance guarantee", "project": "912",
           "bank": "ADCB", "cheque_no": "000451", "amount": "25,000", "undated": True, "remind_on": (T + timedelta(days=5)).isoformat()})
ck("PRO adds an undated cheque", r.status_code == 200 and r.json()["cheque_date"] == "" and r.json()["amount"] == 25000, r.text[:200])
a = r.json()["id"]
r = c.post("/employees/security-cheques", headers=P, json={"party": "Landlord", "amount": 10000, "remind_on": (T - timedelta(days=2)).isoformat()})
b = r.json()["id"]
c.post("/employees/security-cheques", headers=P, json={"party": "DEWA", "amount": 2000})
ck("a login without the tab is refused", c.get("/employees/security-cheques", headers=S).status_code == 403)
d = c.get("/employees/security-cheques", headers=P).json()
s = d["summary"]
ck("summary: 3 out, 1 due, 1 within 30 days, 1 with no date", (s["held"], s["due"], s["soon"], s["no_reminder"]) == (3, 1, 1, 1), s)
ck("overdue one first in the list", d["rows"][0]["party"] == "Landlord" and d["rows"][0]["days_left"] == -2, d["rows"][0])
bell = [n for n in c.get("/notifications", headers=P).json()["notifications"] if n["kind"] == "seccheque"]
ck("the PRO's bell reminds", bell and "1 due to collect back" in bell[0]["title"] and "1 within 7 days" in bell[0]["title"], bell)
ck("admin's bell too", any(n["kind"] == "seccheque" for n in c.get("/notifications", headers=B).json()["notifications"]))
ck("not on a login without the tab", not any(n["kind"] == "seccheque" for n in c.get("/notifications", headers=S).json()["notifications"]))
c.post(f"/employees/security-cheques/{b}/returned", headers=P)
s = c.get("/employees/security-cheques", headers=P).json()["summary"]
ck("collected back: no longer due", s["due"] == 0 and s["held"] == 2, s)
r = c.put(f"/employees/security-cheques/{a}", headers=P, json={"party": "Emaar", "amount": 20000, "undated": True})
s2 = SessionLocal(); al = [(x.action, x.detail) for x in s2.query(watch.WatchAlert).all()]; s2.close()
ck("PRO lowering the amount alerts the admin", any(x[0] == "seccheque_changed" and "25,000.00 -> 20,000.00" in x[1] for x in al), al)
t = c.post("/auth/download-token", headers=P).json()["token"]
for f in ("pdf", "excel"):
    x = c.get(f"/export/security-cheques?format={f}&token={t}")
    ck(f"{f} export", x.status_code == 200 and len(x.content) > 500, x.status_code)
x = c.get(f"/export/security-cheques/view?token={t}&show=all")
ck("preview lists all, incl. collected back", x.status_code == 200 and "Landlord" in x.text and "Collected back" in x.text, x.status_code)
ts = c.post("/auth/download-token", headers=S).json()["token"]
ck("export refused without the tab", c.get(f"/export/security-cheques/view?token={ts}").status_code == 403)
c.delete(f"/employees/security-cheques/{a}", headers=P)
s2 = SessionLocal(); ok = any(x.action == "seccheque_deleted" for x in s2.query(watch.WatchAlert).all()); s2.close()
ck("deleted by PRO -> admin alerted", ok)
s2 = SessionLocal()
s2.query(models.Setting).filter(models.Setting.key == "seccheque_granted").delete()
for nm in ("PRO", "Chief Accountant", "Store Keeper"):
    s2.add(models.AccessRole(name=nm, screens="dashboard"))
s2.commit(); SCM.grant_once(s2)
roles = {r.name: r.screens for r in s2.query(models.AccessRole).all()}; s2.close()
ck("PRO and Chief Accountant roles get it, Store Keeper not",
   "security_cheques" in roles["PRO"] and "security_cheques" in roles["Chief Accountant"] and "security_cheques" not in roles["Store Keeper"], roles)
print("\nALL PASS" if not FAIL else f"\n{len(FAIL)} FAILED: {FAIL}")

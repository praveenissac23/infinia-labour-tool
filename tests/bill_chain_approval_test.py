"""Client bills: QS prepares -> Chief Accountant checks -> Contracts Manager approves (10 Nov 2026).
The chief accountant has no Estimation access: he is told (bell), sees Accounts > Client bills, opens the
approval page and its PDF, approves or sends back.
    cd app && DATABASE_URL=sqlite:////tmp/claude-0/rt/ch.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/bill_chain_approval_test.py
"""
import os, sys, json, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main as M, auth, models
from database import SessionLocal
c = TestClient(M.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:500]}"))
    if not ok: fails.append(n)
db = SessionLocal()
for un, fn, perms in (("t_qs", "Neethu Treesa Jose", "estimation_projects"), ("t_ca", "Shafeeq", "accounts_bank"), ("t_cm", "Anoop", "estimation_projects")):
    u = db.query(models.User).filter(models.User.username == un).first() or models.User(username=un)
    u.full_name, u.permissions, u.role, u.active, u.hashed_password = fn, perms, "office", True, auth.hash_password("pass12345")
    db.add(u)
# no other login may answer to the same names
for u in db.query(models.User).filter(models.User.username.notin_(["t_qs", "t_ca", "t_cm", "admin"])).all():
    u.active = False
    u.full_name = "Other " + u.username
db.commit()
def H(un, pw="pass12345"):
    return {"Authorization": "Bearer " + c.post("/auth/login", data={"username": un, "password": pw}).json()["access_token"]}
A, QS, CA, CM = H("admin", "changeme123"), H("t_qs"), H("t_ca"), H("t_cm")
BID = int(os.environ.get("BID", "26"))
b = c.get(f"/store/est/ipa/bill/{BID}", headers=A).json()
g = {x.get("role"): x for x in b["signers"]}
r = c.put(f"/store/est/ipa/bill/{BID}", headers=A, json={"signs": {g["prep"]["key"]: {"name": "Neethu Treesa Jose"}}})
ck("QS picked", r.status_code == 200, r.text)
r = c.post(f"/store/est/ipa/bill/{BID}/sign", headers=QS, json={"key": g["prep"]["key"]})
ck("QS signs (submits)", r.status_code == 200 and r.json()["status"] == "Awaiting approval", r.text)
ck("...next is Shafeeq", (r.json().get("next") or {}).get("name") == "Shafeeq", r.json().get("next"))
ck("chief accountant cannot open Estimation", c.get(f"/store/est/ipa/bill/{BID}", headers=CA).status_code == 403)
n = c.get("/notifications", headers=CA).json()["notifications"]
bn = [x for x in n if x.get("kind") == "bill"]
ck("chief accountant's bell has the bill, to the approval page", bn and bn[0].get("url") == f"/portal/approve.html?bill={BID}", n[:3])
ck("contracts manager not told yet", not [x for x in c.get("/notifications", headers=CM).json()["notifications"] if x.get("kind") == "bill"])
t = c.get("/store/est/ipa/to-check", headers=CA)
row = next((x for x in t.json()["rows"] if x["id"] == BID), None) if t.status_code == 200 else None
ck("Accounts > Client bills lists it, mine, waiting on Shafeeq", row and row["mine"] and row["waiting_on"] == "Shafeeq" and row["state"] == "waiting", t.text[:400])
ck("...chain QS, Shafeeq, Anoop (no consultant)", row and [s["name"] for s in row["steps"]] == ["Neethu Treesa Jose", "Shafeeq", "Anoop Subramanian"], row and row["steps"])
a = c.get(f"/store/est/ipa/bill/{BID}/approval", headers=CA).json()
ck("approval page: can act, step Checked", a.get("can_act") and a["next"]["step"] == 1, a)
tok = c.post("/auth/download-token", headers=CA).json()["token"]
p = c.get(f"/export/est/ipa/{BID}?format=pdf&token={tok}")
ck("chief accountant gets the PDF", p.status_code == 200 and p.content[:4] == b"%PDF", p.status_code)
ck("contracts manager cannot approve before the check", c.post(f"/store/est/ipa/bill/{BID}/approval", headers=CM, json={"ok": True}).status_code == 403)
# send back
r = c.post(f"/store/est/ipa/bill/{BID}/approval", headers=CA, json={"back": True, "note": ""})
ck("send back needs a note", r.status_code == 400)
r = c.post(f"/store/est/ipa/bill/{BID}/approval", headers=CA, json={"back": True, "note": "Check the previous payments"})
ck("sent back", r.status_code == 200, r.text)
b2 = c.get(f"/store/est/ipa/bill/{BID}", headers=A).json()
ck("...a draft, nobody signed", b2["status"] == "Draft" and not any(x["signed_at"] for x in b2["signers"]), [(x["name"], x["signed_at"]) for x in b2["signers"]])
qn = [x for x in c.get("/notifications", headers=QS).json()["notifications"] if x.get("kind") == "bill"]
ck("QS told, with the note", qn and "Check the previous payments" in qn[0]["detail"] and "Shafeeq" in qn[0]["title"], qn)
row = next((x for x in c.get("/store/est/ipa/to-check", headers=CA).json()["rows"] if x["id"] == BID), None)
ck("Client bills: in Sent back", row and row["state"] == "back" and row["back"]["note"] == "Check the previous payments", row)
# again
r = c.post(f"/store/est/ipa/bill/{BID}/sign", headers=QS, json={"key": g["prep"]["key"]})
ck("QS signs again", r.status_code == 200 and r.json()["status"] == "Awaiting approval", r.text)
ck("...QS's sent-back notice gone", not [x for x in c.get("/notifications", headers=QS).json()["notifications"] if x.get("kind") == "bill"])
r = c.post(f"/store/est/ipa/bill/{BID}/approval", headers=CA, json={"ok": True})
ck("chief accountant approves (checked)", r.status_code == 200 and (r.json().get("next") or {}).get("name") == "Anoop Subramanian", r.text)
ck("...not his any more", not c.get(f"/store/est/ipa/bill/{BID}/approval", headers=CA).json()["can_act"])
cn = [x for x in c.get("/notifications", headers=CM).json()["notifications"] if x.get("kind") == "bill"]
ck("contracts manager told", cn and cn[0].get("url") == f"/portal/approve.html?bill={BID}", cn)
r = c.post(f"/store/est/ipa/bill/{BID}/approval", headers=CM, json={"ok": True})
ck("contracts manager approves -> Approved", r.status_code == 200 and r.json()["status"] == "Approved", r.text)
row = next((x for x in c.get("/store/est/ipa/to-check", headers=CA).json()["rows"] if x["id"] == BID), None)
ck("Client bills: Approved, all three signed", row and row["state"] == "approved" and all(s["signed"] for s in row["steps"]), row)
u = db.query(models.User).filter(models.User.username == "t_x").first() or models.User(username="t_x")
u.full_name, u.permissions, u.role, u.active, u.hashed_password = "Stranger Person", "store", "office", True, auth.hash_password("pass12345")
db.add(u); db.commit()
X = H("t_x")
ck("a stranger cannot open it or its PDF", c.get(f"/store/est/ipa/bill/{BID}/approval", headers=X).status_code == 403 and
   c.get(f"/export/est/ipa/{BID}?format=pdf&token=" + c.post("/auth/download-token", headers=X).json()["token"]).status_code == 403)
ck("...nor the Client bills list", c.get("/store/est/ipa/to-check", headers=X).status_code == 403)
print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAIL: {fails}"))

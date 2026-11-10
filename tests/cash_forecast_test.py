"""Accounts > Cash forecast (10 Nov 2026): bank now from the statement, PDCs / salaries / subcontractor
certificates / client bills / renewals collected, expected expenses typed - once or repeating; a cheque made from
one goes on the PDC register and is counted once; lines moved or left out.
    cp /tmp/aud.db /tmp/claude-0/rt/cf.db && cd app && DATABASE_URL=sqlite:////tmp/claude-0/rt/cf.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/cash_forecast_test.py
"""
import os, sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.getcwd())
from datetime import timedelta
from fastapi.testclient import TestClient
import main as M, models
from database import SessionLocal
c = TestClient(M.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:500]}"))
    if not ok: fails.append(n)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
t = M._dubai_today()
db = SessionLocal()
F = lambda **k: c.get("/store/cash/forecast", headers=H, params=k).json()
d = F()
pend = db.query(models.Pdc).filter(models.Pdc.status == "pending").all()
end = d["months"][-1]["to"]
want = round(sum(p.amount for p in pend if p.cheque_date.isoformat() <= end), 2)
got = round(sum(i["out"] for i in d["items"] if i["key"].startswith("pdc:")), 2)
ck("every pending PDC up to the last month is going out", abs(want - got) < 0.01, (want, got))
ck("past-date PDCs counted today", all(i["date"] >= t.isoformat() for i in d["items"]))
last = db.query(models.BankStmtLine).filter(models.BankStmtLine.balance.isnot(None)).order_by(models.BankStmtLine.on_date.desc(), models.BankStmtLine.id.desc()).first()
ck("bank now = last statement balance (+ Bank tab entries since)", last is None or abs(d["bank"]["balance"] - last.balance) < 0.01, (d["bank"], last and last.balance))
m0 = d["months"][0]
ck("months chain: closing = opening + in - out, next opening = closing", all(abs(m["opening"] + m["in"] - m["out"] - m["closing"]) < 0.02 for m in d["months"]) and
   all(abs(a["closing"] - b["opening"]) < 0.02 for a, b in zip(d["months"], d["months"][1:])))
ck("balance after the last line = last closing", not d["items"] or abs(d["items"][-1]["after"] - d["months"][-1]["closing"]) < 0.02)
# expected expense once
r = c.post("/store/cash/expected", headers=H, json={"what": "Test insurance Q1", "amount": "60,000", "on_date": (t + timedelta(days=5)).isoformat(), "kind": "Insurance"})
ck("add expected expense", r.status_code == 200, r.text); xid = r.json()["id"]
d2 = F()
ck("...counted: closing of the month 60,000 lower", abs(m0["closing"] - 60000 - next(m for m in d2["months"] if m["m"] == m0["m"])["closing"]) < 0.02 if (t + timedelta(days=5)).month == t.month else True)
ck("...on the list, type Expected", any(i["what"].startswith("Test insurance Q1") and i["out"] == 60000 and i["type"] == "expected" for i in d2["items"]))
# repeating rent: 3 lines in 3 months
r = c.post("/store/cash/expected", headers=H, json={"what": "Store rent", "amount": 10000, "on_date": (t + timedelta(days=3)).isoformat(), "repeat": "month", "kind": "Rent"})
d3 = F(); n = len([i for i in d3["items"] if i["what"].startswith("Store rent")])
ck("every month: one line a month", n == len(d3["months"]) or n == len(d3["months"]) - 1, n)
# make it a cheque: off the forecast as expected, on as a PDC - once
r = c.post(f"/store/cash/expected/{xid}/cheque", headers=H, json={"cheque_no": "777001"})
ck("make it a cheque", r.status_code == 200, r.text)
d4 = F()
ins = [i for i in d4["items"] if "test insurance q1" in i["what"].lower() and i["out"] == 60000]
ck("...counted once, from the PDC register", len(ins) == 1 and ins[0]["key"].startswith("pdc:"), ins)
# a repeating one made a cheque moves on to the next month
rid = r.json()
rent = next(x for x in d4["expected"] if x["what"] == "Store rent")
c.post(f"/store/cash/expected/{rent['id']}/cheque", headers=H, json={})
d5 = F(); x5 = next(x for x in d5["expected"] if x["what"] == "Store rent")
ck("repeating: after its cheque the next one stays expected", x5["on_date"] > rent["on_date"], (rent["on_date"], x5["on_date"]))
# paid
c.put(f"/store/cash/expected/{x5['id']}", headers=H, json={"status": "paid"})
ck("paid: off the forecast", not any(i["what"].startswith("Store rent") and i["type"] == "expected" for i in F()["items"]))
# salaries: a month with no salary on the PDC register gets the last payroll
sal = [i for i in d["items"] if i["key"].startswith("sal:")]
pdcsal = {(p.cheque_date.year, p.cheque_date.month) for p in pend if "salar" in (p.payee or "").lower()}
ck("salary estimate only for months with no salary PDC", all((int(i["key"][4:8]), int(i["key"][9:11])) not in pdcsal for i in sal), [i["key"] for i in sal])
# move / leave out a found line
auto = next((i for i in F()["items"] if i["key"].split(":")[0] in ("sal", "client", "sub")), None)
if auto:
    nd = (t + timedelta(days=40)).isoformat()
    c.post("/store/cash/move", headers=H, json={"key": auto["key"], "on_date": nd})
    mv = next((i for i in F()["items"] if i["key"] == auto["key"]), None)
    ck("move a found line to another date", mv and mv["date"] == nd and mv["moved"], mv)
    c.post("/store/cash/move", headers=H, json={"key": auto["key"], "skip": True})
    ck("leave it out", not any(i["key"] == auto["key"] for i in F()["items"]))
    c.post("/store/cash/move", headers=H, json={"key": auto["key"], "reset": True})
    ck("back as found", any(i["key"] == auto["key"] for i in F()["items"]))
ck("PDC lines cannot be moved here", c.post("/store/cash/move", headers=H, json={"key": "exp:1"}).status_code == 400)
# exports
tok = c.post("/auth/download-token", headers=H).json()["token"]
ck("PDF", c.get(f"/export/accounts/cash?format=pdf&token={tok}").content[:4] == b"%PDF")
ck("Excel", c.get(f"/export/accounts/cash?format=excel&token={tok}").status_code == 200)
# rights: a store login cannot see it
u = db.query(models.User).filter(models.User.username == "amal").first()
if u:
    import auth
    u.hashed_password = auth.hash_password("pass12345"); u.permissions = "store"; db.commit()
    S = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "amal", "password": "pass12345"}).json()["access_token"]}
    ck("a store login cannot open it", c.get("/store/cash/forecast", headers=S).status_code == 403)
# only the chief accountant (his role) and admin
for un, perms, ok in (("acctest", "accounts_bank,accounts.bank", False),):
    u = db.query(models.User).filter(models.User.username == un).first()
    if u:
        import auth
        u.hashed_password = auth.hash_password("pass12345"); u.permissions = perms; u.access_role_id = None; db.commit()
        S = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": un, "password": "pass12345"}).json()["access_token"]}
        ck("Bank tab alone does not open the Cash forecast", c.get("/store/cash/forecast", headers=S).status_code == 403)
ca = [r for r in db.query(models.AccessRole).all() if (r.name or "").lower() == "chief accountant"]
db.expire_all()
ck("Chief Accountant role has the Cash forecast", all("accounts_cash" in (r.screens or "") and "accounts.cash" in (r.screens or "") for r in db.query(models.AccessRole).all() if (r.name or "").lower() == "chief accountant"), [r.screens[-80:] for r in ca])
others = [r.name for r in db.query(models.AccessRole).all() if (r.name or "").lower() != "chief accountant" and "accounts_cash" in (r.screens or "")]
ck("no other role has it", not others, others)
print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAIL: {fails}"))

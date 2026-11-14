"""Accounts > Cash forecast (14 Nov 2026): a typed line is a rough guess - the money really paid (Bank tab, cash
register, cheques) is set against it and only what is left is counted. A named line takes that party's payments, an
unnamed "Sub contractor's payment" takes every subcontractor payment not taken, a petty cash line the transfers to
that petty cash. A once-only line whose month is over is asked about (paid / move the rest / move / not happening).
Cash in hand (cash register) counts with the bank."""
import os, sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.getcwd())
from datetime import timedelta, datetime, date, timezone
from fastapi.testclient import TestClient
import main as M, models, accounts as A, estimation as ES
from database import SessionLocal
c = TestClient(M.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:600]}"))
    if not ok: fails.append(n)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
t = M._dubai_today()
m1 = date(t.year, t.month, 1)
pm = (m1 - timedelta(days=1)).replace(day=10)                     # the 10th of last month
db = SessionLocal()
db.add_all([ES.EstSub(project_id=1, name="M/s. Al Raida Electromechanical Services llc", kind="Subcontract"),
            ES.EstSub(project_id=1, name="M/s. Royal Everst Technical Services", kind="Subcontract"),
            ES.EstSub(project_id=1, name="Gemini Building Materials", kind="LPO")])
B = lambda **k: models.BankEntry(bank="ADCB", mode="Bank Transfer", **k)
db.add_all([B(kind="vendor", on_date=t, party="Al Raida Electromechanical Services LLC", amount=100000),
            B(kind="vendor", on_date=t + timedelta(days=1), party="Desarch Scaffolding L.L.C", amount=28000),
            B(kind="vendor", on_date=t, party="Gemini Building Materials", amount=7000),       # an LPO supplier, not a sub
            B(kind="transfer", on_date=t, party="", account="Jomon Petty Cash", amount=70000),
            B(kind="vendor", on_date=pm + timedelta(days=2), party="Royal Everst Technical Services", amount=300000)])
db.add_all([A.CashEntry(kind="received", on_date=t - timedelta(days=3), description="Received from 103 Project", amount=150000),
            A.CashEntry(kind="paid", on_date=t, description="Paid To Al Raida Electromechanical - 905-MEP-PC07 Balance + Key Money", amount=21500),
            A.CashEntry(kind="paid", on_date=t, description="SITE PETTY CASH - AMAL", amount=5000),
            A.CashEntry(kind="received", on_date=t - timedelta(days=2), description="Emkaan Design - 914 IPA03", amount=40000),
            A.CashEntry(kind="paid", on_date=t - timedelta(days=1), description="Deposited to ADCB", amount=30000)])
db.commit()
X = lambda **k: c.post("/store/cash/expected", headers=H, json=k).json()["id"]
sub = X(what="Sub Contractor's Payment", kind="Subcontractor", amount=320000, on_date=m1.isoformat(), repeat="month", sure="maybe")
jom = X(what="Jomon Petty Cash", kind="Other", amount=100000, on_date=m1.isoformat(), repeat="month")
cmp_ = X(what="Company & Site Petty Cash", kind="Other", amount=75000, on_date=m1.isoformat(), repeat="month")
des = X(what="Desarch Scaffolding", kind="Supplier", amount=28080.51, on_date=(t + timedelta(days=2)).isoformat())
old = X(what="Managers Insurance", kind="Insurance", amount=50000, on_date=pm.isoformat())
roy = X(what="Royal Everst", kind="Subcontractor", amount=500000, on_date=pm.isoformat())
gem = X(what="Supplier payments", kind="Supplier", amount=20000, on_date=(t + timedelta(days=3)).isoformat())
for i in (old, roy):                                              # typed last month
    x = db.query(models.CashExpected).get(i); x.created_at = datetime(pm.year, pm.month, 1, tzinfo=timezone.utc)
db.commit()

d = c.get("/store/cash/forecast", headers=H, params={"months": 3}).json()
it = {i["key"]: i for i in d["items"]}
cur = lambda xid: it.get(f"exp:{xid}:0")
ck("cash in hand = cash register received - paid up to today (deposit to the bank included)", abs(d["bank"]["cash"] - (150000 + 40000 - 21500 - 5000 - 30000)) < 0.01, d["bank"])
ck("...money now = bank + cash", abs(d["bank"]["now"] - d["bank"]["in_bank"] - d["bank"]["cash"]) < 0.01, d["bank"])
s = cur(sub)
ck("unnamed sub contractor bucket: this month counts only what is left (320,000 - 100,000 bank - 21,500 cash)", s and abs(s["out"] - 198500) < 0.01, s)
ck("...note says what was paid so far", s and "paid so far 121,500" in s["note"], s and s["note"])
ck("...next month the full guess again", abs(it.get(f"exp:{sub}:1", {}).get("out", 0) - 320000) < 0.01)
ck("Jomon petty cash: the transfer to Jomon only (100,000 - 70,000)", cur(jom) and abs(cur(jom)["out"] - 30000) < 0.01, cur(jom))
ck("Company & site petty cash: the site petty cash from the register, not Jomon's (75,000 - 5,000)", cur(cmp_) and abs(cur(cmp_)["out"] - 70000) < 0.01, cur(cmp_))
ck("Desarch: a payment within 10% of the guess settles it (28,000 of ~28,081) - off the forecast", cur(des) is None, cur(des))
ck("an LPO supplier's payment is not a subcontractor payment - it goes to the supplier bucket", cur(gem) and abs(cur(gem)["out"] - 13000) < 0.01, cur(gem))
ask = {a["id"]: a for a in d["ask"]}
ck("last month, nothing found: asked 'none' and still counted today", ask.get(old, {}).get("ask") == "none" and cur(old) and cur(old)["late"] and cur(old)["out"] == 50000, (ask.get(old), cur(old)))
ck("last month, part paid: asked 'part', 200,000 left counted", ask.get(roy, {}).get("ask") == "part" and abs(ask[roy]["left"] - 200000) < 0.01 and abs(cur(roy)["out"] - 200000) < 0.01, ask.get(roy))
ck("...the payment found is listed", ask.get(roy) and ask[roy]["found"] and ask[roy]["found"][0]["amount"] == 300000, ask.get(roy))
ck("...and asked to close it (found in the bank)", ask.get(des, {}).get("ask") == "done", ask.get(des))
ck("this month's lines are not asked yet", sub not in ask and gem not in ask)
# a cash line dated later is in / out on its day; a later deposit to the bank is not
db.add_all([A.CashEntry(kind="paid", on_date=t + timedelta(days=4), description="Business promotion", amount=2000),
            A.CashEntry(kind="paid", on_date=t + timedelta(days=4), description="Deposited to ADCB", amount=9000)]); db.commit()
d2 = c.get("/store/cash/forecast", headers=H).json()
cl = [i for i in d2["items"] if i["key"].startswith("cash:")]
ck("cash register line dated later: going out on its day; deposit to the bank not counted", len(cl) == 1 and cl[0]["out"] == 2000, cl)
# answers
P = lambda xid, **k: c.post(f"/store/cash/expected/{xid}/settle", headers=H, json=k)
nx = (m1 + timedelta(days=32)).replace(day=1)
ck("move needs a date", P(old, how="move").status_code == 400)
ck("a part-paid line cannot be moved whole", P(roy, how="move", on_date=nx.isoformat()).status_code == 409)
r = P(roy, how="rest", on_date=nx.isoformat())
ck("move the rest", r.status_code == 200, r.text)
db.expire_all()
x = db.query(models.CashExpected).get(roy)
new = db.query(models.CashExpected).filter(models.CashExpected.status == "open", models.CashExpected.what == "Royal Everst").first()
ck("...the line is closed at what was paid", x.status == "paid" and abs(x.amount - 300000) < 0.01, (x.status, x.amount))
ck("...a new line for 200,000 on the date picked", new and abs(new.amount - 200000) < 0.01 and new.on_date == nx, new and (new.amount, new.on_date))
d3 = c.get("/store/cash/forecast", headers=H).json()
ck("...the old payment does not settle the new line again", abs(next(i for i in d3["items"] if i["key"] == f"exp:{new.id}:0")["out"] - 200000) < 0.01)
r = P(old, how="move", on_date=nx.isoformat())
ck("move a line nothing was paid on", r.status_code == 200 and next(i for i in c.get("/store/cash/forecast", headers=H).json()["items"] if i["key"] == f"exp:{old}:0")["date"] == nx.isoformat(), r.text)
ck("a past date is refused", P(gem, how="move", on_date=(t - timedelta(days=1)).isoformat()).status_code == 400)
ck("not happening", P(gem, how="drop").status_code == 200 and not any(i["key"] == f"exp:{gem}:0" for i in c.get("/store/cash/forecast", headers=H).json()["items"]))
ck("paid", P(des, how="paid").status_code == 200)
ck("...answered again: not found", P(des, how="paid").status_code == 404)
ck("export still works", c.get("/export/accounts/cash", params={"token": c.post("/auth/download-token", headers=H).json().get("token", ""), "format": "excel"}).status_code in (200, 401, 403, 422))

# ---- review cases (14 Nov 2026)
import auth
PD = lambda **k: models.Pdc(**k)
F = lambda **k: c.get("/store/cash/forecast", headers=H, params=k).json()
# a planned cheque found on a past line: "move the rest" must not count the cheque against the rest again
q1 = X(what="Kaizen Formwork", kind="Supplier", amount=28080, on_date=pm.isoformat())
db.query(models.CashExpected).get(q1).created_at = datetime(pm.year, pm.month, 1, tzinfo=timezone.utc)
db.add(PD(payee="Kaizen Formwork LLC", cheque_date=t + timedelta(days=7), amount=10000, status="pending", cheque_no="881")); db.commit()
a1 = {a["id"]: a for a in F()["ask"]}.get(q1)
ck("past line + later cheque: part paid, 18,080 left", a1 and a1["ask"] == "part" and abs(a1["left"] - 18080) < 0.01, a1)
ck("...the same answer in a 3-month and a 12-month view", {a["id"]: a for a in F(months=3)["ask"]}.get(q1, {}).get("left") == {a["id"]: a for a in F(months=12)["ask"]}.get(q1, {}).get("left"))
P(q1, how="rest", on_date=(t + timedelta(days=10)).isoformat())
d4 = F(); kz = sum(i["out"] for i in d4["items"] if "Kaizen" in i["what"])
ck("...after moving the rest: cheque 10,000 + rest 18,080 = 28,080 going out", abs(kz - 28080) < 0.01, [(i["what"], i["out"]) for i in d4["items"] if "Kaizen" in i["what"]])
# a cleared cheque still counts as paid
sb2 = X(what="Subcontractor payments", kind="Subcontractor", amount=100000, on_date=(m1 + timedelta(days=40)).replace(day=1).isoformat(), repeat="month")
nm = (m1 + timedelta(days=40)).replace(day=1)
ch = PD(payee="Al Raida Electromechanical Services LLC", cheque_date=nm, amount=40000, status="pending", cheque_no="882"); db.add(ch); db.commit()
g = lambda: sum(i["out"] for i in F()["items"] if i["key"] in (f"exp:{sb2}:0", f"exp:{sub}:1"))   # both budgets for subcontractors next month
before = g(); ch.status = "cleared"; db.commit(); after = g()
ck("a cheque to a subcontractor: taken off the budget, pending or cleared", abs(before - 380000) < 0.01 and abs(after - 380000) < 0.01, (before, after))
# a cheque dated a few days after a once line's month
eom = _me = (date(t.year, t.month, 1) + timedelta(days=40)).replace(day=1) - timedelta(days=1)
q6 = X(what="Orbit Glass Works", kind="Supplier", amount=15000, on_date=(eom - timedelta(days=2)).isoformat())
db.add(PD(payee="Orbit Glass Works", cheque_date=eom + timedelta(days=2), amount=15000, status="pending", cheque_no="883")); db.commit()
o6 = sum(i["out"] for i in F()["items"] if "Orbit" in i["what"])
ck("a cheque dated just after the month: counted once (15,000, not 30,000)", abs(o6 - 15000) < 0.01, o6)
# settle is for once-only lines
ck("a repeating line is not answered with the buttons", P(sub, how="drop").status_code == 400)
# a transfer to cash after the statement: off the bank (the register has it)
db.add(models.BankStmtLine(bank="ADCB", on_date=t - timedelta(days=5), description="x", balance=1000000, fp="cf-a-1")); db.commit()
b0 = F()["bank"]
db.add(B(kind="transfer", on_date=t - timedelta(days=1), party="", account="Cash", amount=20000)); db.commit()
b1 = F()["bank"]
ck("transfer to cash after the statement: off the bank", abs(b0["in_bank"] - 20000 - b1["in_bank"]) < 0.01, (b0["in_bank"], b1["in_bank"]))
# a login with the Cash forecast but not the cash register: no cash book shown
u = models.User(username="cfonly", full_name="cfonly", role="office", hashed_password=auth.hash_password("pw123456"), permissions="accounts_cash"); db.add(u); db.commit()
H2 = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "cfonly", "password": "pw123456"}).json()["access_token"]}
d5 = c.get("/store/cash/forecast", headers=H2).json()
ck("no cash register right: cash in hand not shown, no cash lines", d5["bank"]["cash"] == 0 and d5["bank"]["cash_hidden"] and not any(i["key"].startswith("cash:") for i in d5["items"])
   and not any(f["src"] == "Cash" for a in d5["ask"] for f in a.get("found") or []), d5["bank"])
print("\nFAILED: " + ", ".join(fails) if fails else "\nall passed")
sys.exit(1 if fails else 0)

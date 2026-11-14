"""Owner's dashboard (14 Nov 2026): the first card shows the bank balance today (last statement + Bank tab since,
per bank, cash in hand beside it) - no more "Net position · next 30 days"."""
import os, sys, re, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.getcwd())
from datetime import timedelta
from fastapi.testclient import TestClient
import main as M, models
from database import SessionLocal
c = TestClient(M.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:400]}"))
    if not ok: fails.append(n)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
html = open(os.path.join(ROOT, "app-classic.html"), encoding="utf-8").read()
ck("the net position card is gone", "Net position · next 30 days" not in html)
ck("the bank card is there, filled from the cash forecast", 'id="od-bank-v"' in html and "odBank(f.bank)" in html and "function odBank" in html)
ck("the cash forecast card says what it starts from (bank + cash), and its rings are month-end", "Starts from <b>" in html and "end ${m.label.slice(0, 3)}" in html and "Bank today <b>" not in html)
ck("app.html built from it", 'id="od-bank-v"' in open(os.path.join(ROOT, "app.html"), encoding="utf-8").read())
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
t = M._dubai_today()
db = SessionLocal()
db.add(models.BankStmtLine(bank="ADCB", on_date=t - timedelta(days=2), description="x", balance=1777233.31, fp="od-1"))
db.add(models.BankEntry(bank="ADCB", mode="Bank Transfer", kind="vendor", on_date=t - timedelta(days=1), party="Desarch Scaffolding", amount=10000))
db.commit()
b = c.get("/store/cash/forecast", headers=H, params={"months": 3, "with_in": 1}).json()["bank"]
ck("in the bank today = statement - paid since", abs(b["in_bank"] - 1767233.31) < 0.01, b)
ck("per bank, with the statement date", b["banks"] and b["banks"][0]["bank"] == "ADCB" and b["banks"][0]["as_of"] == (t - timedelta(days=2)).isoformat(), b["banks"])
print("\nFAILED: " + ", ".join(fails) if fails else "\nall passed")
sys.exit(1 if fails else 0)

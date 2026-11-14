"""Owner's dashboard, last row (14 Nov 2026): project profit (work certified to the client vs cost so far =
Project expense + subcontract work certified), spend this month (materials, subcontract certified this month,
labour, petty cash; vs last month to the same day without labour), documents expiring in 30 days."""
import os, sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.getcwd())
from datetime import timedelta
from fastapi.testclient import TestClient
import main as M, models, estimation as ES, auth
from database import SessionLocal
c = TestClient(M.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:500]}"))
    if not ok: fails.append(n)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
t = M._dubai_today()
db = SessionLocal()
p = ES.EstProject(code="981", name="Al Mamzar villa with a long name for the card", client="Mr. Jamal Khan", status="Running", contract_value=5000000, ret_pct=0, vat_pct=5)
q = ES.EstProject(code="982", name="", status="Running")                         # no certificate, no cost: left out
db.add_all([p, q]); db.commit()
db.add(ES.EstClientPC(project_id=p.id, seq=1, claimed_cum=1000000, certified_cum=1000000, status="Certified", submitted=t - timedelta(days=20))); db.commit()
sb = ES.EstSub(project_id=p.id, name="M/s. Al Raida Electromechanical Services llc", kind="Subcontract", value=2000000); db.add(sb); db.commit()
db.add(ES.EstSubPC(sub_id=sb.id, seq=1, work_cum=1100000, status="Certified", certified_on=t)); db.commit()
db.add(models.CompanyExpiry(category="Trade licence", item="Trade licence", kind="Renewal", expires_on=t + timedelta(days=9)))
db.add(models.CompanyExpiry(category="Vehicle", item="Toyota Hilux - Dubai P 12345", kind="Insurance", expires_on=t + timedelta(days=90)))
db.commit()
r = c.get("/permissions/owner/more", headers=H)
ck("loads", r.status_code == 200, r.text)
d = r.json()
pr = {x["code"]: x for x in d.get("profit") or []}
ck("project with a certificate and a subcontract: certified vs cost", "981" in pr and pr["981"]["certified"] > 0 and pr["981"]["subs"] >= 1000000, pr.get("981"))
ck("...losing money shows a minus margin and comes first", pr.get("981", {}).get("margin") is not None and pr["981"]["margin"] < 0 and d["profit"][0]["code"] == "981", d.get("profit"))
ck("a project with nothing is left out", "982" not in pr)
sp = d.get("spend") or {}
ck("spend this month: subcontract certified this month counted", sp.get("subs", 0) > 0 and abs(sp["total"] - (sp["labour"] + sp["materials"] + sp["petty"] + sp["subs"])) < 0.01, sp)
ex = d.get("expiring") or {}
ck("expiring: the trade licence in 9 days, not the one in 90", ex.get("count") == 1 and ex["company"] and ex["company"][0]["days"] == 9 and "Trade licence" in ex["company"][0]["what"], ex)
u = models.User(username="notowner", full_name="x", role="office", hashed_password=auth.hash_password("pw123456"), permissions="accounts_cash"); db.add(u); db.commit()
H2 = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "notowner", "password": "pw123456"}).json()["access_token"]}
ck("only the admin", c.get("/permissions/owner/more", headers=H2).status_code == 403)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
html = open(os.path.join(ROOT, "app.html"), encoding="utf-8").read()
ck("the three cards on the page", all(x in html for x in ('id="od-profit"', 'id="od-spend"', 'id="od-exp"', "function odMore")))
print("\nFAILED: " + ", ".join(fails) if fails else "\nall passed")
sys.exit(1 if fails else 0)

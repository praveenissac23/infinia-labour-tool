"""913 bill 10 (7 Nov 2026): a section and a line added to the Cost Proposal Log (VI VARIATION ORDER - 04 /
Construction of Swimming Pool 312,000) go on the Summary too - after the last Cost Proposal line, its figures linked,
the sections after it renumbered - so the Summary's totals, the work to date and TOTAL DUE take them in; taking the
line out takes its copy off again.
    python3 tests/make_ipa_like_913.py /tmp/claude-0/bills/913-like.xlsx
    cp /tmp/full.db /tmp/claude-0/mi.db && cd app && DATABASE_URL=sqlite:////tmp/claude-0/mi.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/bill_mirror_summary_test.py"""
import os, sys, warnings, json
warnings.filterwarnings("ignore")
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main as M
c = TestClient(M.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:400]}"))
    if not ok: fails.append(n)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
pid = c.get("/store/est/meta", headers=H).json()["projects"][0]["id"]
r = c.post("/store/est/ipa/format", headers=H, data={"project_id": str(pid)}, files={"file": ("913-like.xlsx", open("/tmp/claude-0/bills/913-like.xlsx", "rb").read(), "application/octet-stream")})
ck("format uploaded", r.status_code == 200, r.text)
bid = c.post("/store/est/ipa/new", headers=H, json={"project_id": pid, "format_id": r.json()["id"]}).json()["id"]
import est_bills as EB, est_bills_engine as BE
from database import SessionLocal
def state():
    db = SessionLocal(); b = db.get(EB.EstBill, bid); f = db.get(EB.EstBillFormat, b.format_id); inp = EB._inputs(b)
    m = EB._bill_model(f, inp); v = BE.calculate(m, inp); db.close(); return m, v, inp
m0, v0, _ = state()
rcv0 = v0["Summary"]["12,3"]
r = c.post(f"/store/est/ipa/bill/{bid}/line", headers=H, json={"sheet": "Cost Proposal Log", "after": 11, "kind": "head", "values": {"item": "IV", "desc": "VARIATION ORDER - 04"}})
ck("section added", r.status_code == 200, r.text[:300])
r = c.post(f"/store/est/ipa/bill/{bid}/line", headers=H, json={"sheet": "Cost Proposal Log", "after": 12, "kind": "line", "values": {"item": "1", "desc": "Construction of Swimming Pool", "unit": "Item", "amount": 312000}})
ck("line added", r.status_code == 200, r.text[:300])
b = r.json(); cpl = next(t for t in b["progress"] if t["sheet"] == "Cost Proposal Log")
ck("Work done: Cost Proposal Log has 4 lines (headings not counted), value 451,000", len(cpl["lines"]) == 4 and abs(sum(l["amount"] or 0 for l in cpl["lines"]) - 451000) < 0.01, [(l["item"], l["amount"]) for l in cpl["lines"]])
m1, v1, inp1 = state()
S = v1["Summary"]
txt = {k: S[k] for k in S if k.endswith(",2")}
ck("Summary: VARIATION ORDER - 04 and Construction of Swimming Pool right after Interior design Works (rows 11, 12)",
   S.get("11,2") == "VARIATION ORDER - 04" and S.get("12,2") == "Construction of Swimming Pool", txt)
ck("Summary: the new section numbered V, VARIATION ORDER - 01 moved on to VI", S.get("11,1") == "V" and S.get("13,1") == "VI", (S.get("11,1"), S.get("13,1")))
ck("REVISED CONTRACT VALUE takes the 312,000 in", abs(S["14,3"] - rcv0 - 312000) < 0.01, (rcv0, S.get("14,3")))
lr = next(l for l in cpl["lines"] if "Swimming" in (l["desc"] or ""))
due0 = b["total_due"]
r = c.put(f"/store/est/ipa/bill/{bid}", headers=H, json={"set": {"Cost Proposal Log": {lr["tot_key"]: 0.2}}})
ck("20% on the Swimming Pool = +62,400 in TOTAL DUE", abs(r.json()["total_due"] - due0 - 62400) < 0.01, (due0, r.json()["total_due"]))
m2, v2, _ = state()
ck("Summary work to date takes the 62,400", abs(v2["Summary"]["14,8"] - v1["Summary"]["14,8"] - 62400) < 0.01, (v1["Summary"]["14,8"], v2["Summary"]["14,8"]))
r = c.post(f"/store/est/ipa/bill/{bid}/line/remove", headers=H, json={"sheet": "Cost Proposal Log", "r": lr["r"]})
ck("line taken out", r.status_code == 200, r.text[:300])
m3, v3, _ = state()
ck("... its copy on the Summary goes too (REVISED back to +0 for the line)", v3["Summary"].get("12,2") != "Construction of Swimming Pool" and abs(v3["Summary"]["13,3"] - rcv0) < 0.01,
   {k: v3["Summary"][k] for k in v3["Summary"] if k.endswith(",2") or k.endswith(",3")})
# ---- a bill from before the fix: the line on the Cost Proposal Log, not on the Summary -> put on it at the deploy
r = c.post(f"/store/est/ipa/bill/{bid}/line", headers=H, json={"sheet": "Cost Proposal Log", "after": 12, "kind": "line", "values": {"item": "1", "desc": "Construction of Swimming Pool", "unit": "Item", "amount": 312000}})
db = SessionLocal(); bb = db.get(EB.EstBill, bid); inp = EB._inputs(bb); inp.pop("Summary", None); bb.inputs = json.dumps(inp); db.commit(); db.close()
mo, vo, _ = state()
ck("(old bill: Summary without the added rows)", vo["Summary"].get("11,2") != "VARIATION ORDER - 04")
import est_onetime, models
db = SessionLocal(); db.query(models.Setting).filter(models.Setting.key == "est_onetime_summary_mirror_20261107").delete(); db.commit(); db.close()
est_onetime.summary_mirror(SessionLocal)
m4, v4, _ = state()
S4 = v4["Summary"]
ck("at the deploy: VO-04 and the Swimming Pool put on the Summary in place, numbered, REVISED +312,000",
   S4.get("11,2") == "VARIATION ORDER - 04" and S4.get("12,2") == "Construction of Swimming Pool" and S4.get("11,1") == "V" and S4.get("13,1") == "VI" and abs(S4["14,3"] - rcv0 - 312000) < 0.01,
   {k: S4[k] for k in S4 if k.endswith(",2") or k.endswith(",1")})
db = SessionLocal(); log = db.query(models.AuditLog).filter(models.AuditLog.action == "est_onetime").order_by(models.AuditLog.id.desc()).first(); db.close()
ck("... and written to the audit log with the before / after totals", log and "put on the Summary" in log.details and "total due" in log.details, log and log.details)
est_onetime.summary_mirror(SessionLocal)
m5, v5, _ = state()
ck("runs once: nothing added twice", v5["Summary"] == v4["Summary"])
print("ALL PASS" if not fails else f"{len(fails)} FAILED")

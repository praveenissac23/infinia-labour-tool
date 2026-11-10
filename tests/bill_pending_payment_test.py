"""Payments received: Received on = a date or Pending (10 Nov 2026). Pending amounts stay on the line but are out of
the total of previous payments (cover, APP A total, total due, Excel formula); that earlier bill's authority fees
are carried onto this bill's Appendix B as a read-only line until it is Received.
    python3 tests/make_ipa_with_appab.py /tmp/claude-0/bills/ab-like.xlsx
    cp /tmp/full.db /tmp/claude-0/rt/pd.db && cd app && DATABASE_URL=sqlite:////tmp/claude-0/rt/pd.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/bill_pending_payment_test.py
"""
import os, sys, warnings, io, re
warnings.filterwarnings("ignore")
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main as M
c = TestClient(M.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:600]}"))
    if not ok: fails.append(n)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
pid = c.get("/store/est/meta", headers=H).json()["projects"][-1]["id"]
r = c.post("/store/est/ipa/format", headers=H, data={"project_id": str(pid)}, files={"file": ("ab-like.xlsx", open("/tmp/claude-0/bills/ab-like.xlsx", "rb").read(), "application/octet-stream")})
fid = r.json()["id"]
b1 = c.post("/store/est/ipa/new", headers=H, json={"project_id": pid, "format_id": fid}).json()["id"]
B1 = c.get(f"/store/est/ipa/bill/{b1}", headers=H).json()
print("bill 1", B1["label"], "fees", [(x["rows"] and [(rr["desc"]["value"], rr["amount"]["value"]) for rr in x["rows"]]) for x in B1["fees"]], "fees total", B1["fees"][0]["total"])
fr = [x for x in B1["fees"][0]["rows"] if not x["head"]][0]
B1 = c.put(f"/store/est/ipa/bill/{b1}", headers=H, json={"set": {"APP B": {fr["desc"]["key"]: "Trakhees permit", fr["amount"]["key"]: 1250}}}).json()
fee1 = B1["fees"][0]["total"]
ck("bill 1 has its own authority fees", abs(fee1 - 1250) < 0.01, fee1)
c.post(f"/store/est/ipa/bill/{b1}/status", headers=H, json={"status": "Approved"})
b2 = c.post("/store/est/ipa/new", headers=H, json={"project_id": pid, "format_id": fid}).json()["id"]
B = c.get(f"/store/est/ipa/bill/{b2}", headers=H).json()
pay = B["payments"][0]
print("bill 2", B["label"], "pay rows", [(x["desc"]["value"], x.get("received", {}).get("value"), x["amount"]["value"]) for x in pay["rows"] if x["desc"]["value"]])
row = next(x for x in pay["rows"] if re.search(rf"\b{re.escape(str(B1['label']))}\s*$", str(x["desc"]["value"] or "")))
due0, tot0, fees0 = B["total_due"], pay["total"], B["fees"][0]["total"]
# the amount of B1 typed as received money, no date yet
B = c.put(f"/store/est/ipa/bill/{b2}", headers=H, json={"set": {"APP A": {row["amount"]["key"]: "=(989148-280)/1.05"}}, "why": {"page": "pay"}}).json()
amt = (989148 - 280) / 1.05
tot1, due1 = B["payments"][0]["total"], B["total_due"]
ck("amount typed counts in the total (as before)", abs(tot1 - tot0 - amt) < 0.01, (tot0, tot1))
# Pending
r = c.put(f"/store/est/ipa/bill/{b2}", headers=H, json={"set": {"APP A": {row["received"]["key"]: "Pending"}}, "why": {"page": "pay"}})
ck("mark Pending saves", r.status_code == 200, r.text[:300]); B = r.json()
p2 = B["payments"][0]; rw = next(x for x in p2["rows"] if x["r"] == row["r"])
ck("row says pending, amount still there", rw["pending"] and abs(rw["amount"]["value"] - amt) < 0.01, rw)
ck("left out of the total of previous payments", abs(p2["total"] - tot0) < 0.01, (p2["total"], tot0))
f2 = B["fees"][0]
carried = [x for x in f2["rows"] if x.get("carry")]
ck("one carried line on Appendix B", len(carried) == 1 and abs(carried[0]["amount"]["value"] - fee1) < 0.01, [(x["desc"]["value"], x["amount"]["value"], x.get("carry")) for x in f2["rows"]])
ck("...reads 'Carried from ... (Pending)'", carried and carried[0]["desc"]["value"] == f"Carried from {row['desc']['value'].strip()} (Pending)", carried and carried[0]["desc"]["value"])
ck("Appendix B total = own + carried", abs(f2["total"] - fees0 - fee1) < 0.01, (f2["total"], fees0, fee1))
ck("total due up by the payment and the carried fees", abs(B["total_due"] - (due1 + amt + fee1)) < 0.02, (B["total_due"], due1, amt, fee1))
print("cover", B.get("cover") and {k: v for k, v in B["cover"].items() if k != "facts"})
cov = {x["label"]: x["amount"] for x in (B.get("cover") or {}).get("rows", [])}
if cov:
    ck("cover: Less previous = total without pending", abs((cov.get("Less Previous Progressive Payments (Appendix A)") or 0) - tot0) < 0.01, cov)
# Excel: the SUMIF formula and the same total; the check passes
tok = c.post("/auth/download-token", headers=H).json()["token"]
x = c.get(f"/export/est/ipa/{b2}?format=excel&token={tok}")
ck("Excel exports (its check passes)", x.status_code == 200, x.text[:300])
if x.status_code == 200:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(x.content)); ws = wb["APP A"]
    f = ws.cell(23, 5).value
    ck("Excel total is a SUMIF leaving Pending out", isinstance(f, str) and "SUMIF" in f and "Pending" in f, f)
    ck("Excel row shows Pending", ws.cell(row["r"], 4).value == "Pending", ws.cell(row["r"], 4).value)
    wb2 = openpyxl.load_workbook(io.BytesIO(x.content), data_only=True)
    ck("Excel cached total = app", abs((wb2["APP A"].cell(23, 5).value or 0) - p2["total"]) < 0.01, wb2["APP A"].cell(23, 5).value)
p = c.get(f"/export/est/ipa/{b2}?format=pdf&token={tok}")
ck("PDF exports", p.status_code == 200 and p.content[:4] == b"%PDF", p.status_code)
# Undo takes it back to received-without-date (and the carried line off)
u = c.post(f"/store/est/ipa/bill/{b2}/undo", headers=H, json={})
ck("Undo the Pending", u.status_code == 200, u.text[:300])
B = c.get(f"/store/est/ipa/bill/{b2}", headers=H).json()
ck("...total back, no carried line", abs(B["payments"][0]["total"] - tot1) < 0.01 and not [x for x in B["fees"][0]["rows"] if x.get("carry")], (B["payments"][0]["total"], [x["desc"]["value"] for x in B["fees"][0]["rows"]]))
c.post(f"/store/est/ipa/bill/{b2}/undo", headers=H, json={"redo": True})
B = c.get(f"/store/est/ipa/bill/{b2}", headers=H).json()
ck("Redo: pending again with its line", [x for x in B["fees"][0]["rows"] if x.get("carry")] and abs(B["payments"][0]["total"] - tot0) < 0.01)
# Received: a date
r = c.put(f"/store/est/ipa/bill/{b2}", headers=H, json={"set": {"APP A": {row["received"]["key"]: 46335}}, "why": {"page": "pay"}}); B = r.json()
ck("Received: in the total again", abs(B["payments"][0]["total"] - tot1) < 0.01, B["payments"][0]["total"])
ck("...carried line taken off, Appendix B back", not [x for x in B["fees"][0]["rows"] if x.get("carry")] and abs(B["fees"][0]["total"] - fees0) < 0.01, [(x["desc"]["value"], x["amount"]["value"]) for x in B["fees"][0]["rows"]])
ck("...total due as with the payment counted", abs(B["total_due"] - due1) < 0.02, (B["total_due"], due1))
# still pending on the next bill: carried again unless a bill already sent carried it
c.put(f"/store/est/ipa/bill/{b2}", headers=H, json={"set": {"APP A": {row["received"]["key"]: "Pending"}}})
c.post(f"/store/est/ipa/bill/{b2}/status", headers=H, json={"status": "Approved"})
b3 = c.post("/store/est/ipa/new", headers=H, json={"project_id": pid, "format_id": fid}).json()["id"]
B3 = c.get(f"/store/est/ipa/bill/{b3}", headers=H).json()
r3 = next((x for x in B3["payments"][0]["rows"] if x["r"] == row["r"]), None)
ck("next bill: still Pending", r3 and r3["pending"], r3)
ck("...but not carried twice (bill 2 already claimed it)", not [x for x in B3["fees"][0]["rows"] if x.get("carry") and str(B1["label"]) in x["desc"]["value"]], [(x["desc"]["value"], x["amount"]["value"]) for x in B3["fees"][0]["rows"]])
import models
from database import SessionLocal
db = SessionLocal()
logs = [a.details for a in db.query(models.AuditLog).filter(models.AuditLog.action == "est_bill_pending").all()] if hasattr(models, "AuditLog") else []
print("log", logs[-3:])
print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAIL: {fails}"))

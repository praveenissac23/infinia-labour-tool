"""Previous bills not paid yet (10 Nov 2026): Received on = a date or Pending. A Pending bill is left out of what was
paid, so the next bill claims it again in full - its work with its VAT (the cover's cumulative sum) and its authority
fees (a carried line on Appendix B). A new bill marks the bill before it Pending by itself. Received with a date: the
amount counts as paid and the carried fees come off. Never claimed twice.
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
G = lambda bid: c.get(f"/store/est/ipa/bill/{bid}", headers=H).json()
P = lambda bid, body: c.put(f"/store/est/ipa/bill/{bid}", headers=H, json=body)
row = lambda B, n: next((x for x in B["payments"][0]["rows"] if re.search(rf"No 0*{n}\s*$", str(x["desc"]["value"] or "").strip())), None)
carried = lambda B: [(x["desc"]["value"], x["amount"]["value"]) for x in B["fees"][0]["rows"] if x.get("carry")]
paid = lambda B: B["payments"][0]["total"]
cov = lambda B: {x["label"]: x["amount"] for x in (B.get("cover") or {}).get("rows", [])}

# bill 9 (the first in the app): PA 8 - from before the app - has no money yet: Pending by itself, its 140 carried
b1 = c.post("/store/est/ipa/new", headers=H, json={"project_id": pid, "format_id": fid}).json()["id"]
B1 = G(b1)
ck("bill 9: PA 8 (no money yet) marked Pending by itself", row(B1, 8) and row(B1, 8)["pending"], row(B1, 8))
ck("...its authority fees (140, from the IPA 8 lines) carried", carried(B1) == [("Carried from Payment Application No 8 (Pending)", 140)], carried(B1))
fr = [x for x in B1["fees"][0]["rows"] if not x["head"] and not x.get("carry")][0]
B1 = P(b1, {"set": {"APP B": {fr["desc"]["key"]: "Trakhees permit", fr["amount"]["key"]: 1250}}}).json()
ck("bill 9 own fees 1250 + carried 140", abs(B1["fees"][0]["total"] - 1390) < 0.01, B1["fees"][0]["total"])
# PA 8 paid before bill 9 goes: Received with date and amount -> counts as paid, the 140 comes off
r8 = row(B1, 8)
B1 = P(b1, {"set": {"APP A": {r8["received"]["key"]: 46330, r8["amount"]["key"]: 20000}}}).json()
ck("PA 8 Received: paid total +20,000, the 140 line comes off", abs(paid(B1) - 100000) < 0.01 and not carried(B1) and abs(B1["fees"][0]["total"] - 1250) < 0.01, (paid(B1), carried(B1)))
c.post(f"/store/est/ipa/bill/{b1}/status", headers=H, json={"status": "Approved"})
due9 = B1["total_due"]

# bill 10: bill 9 not paid -> Pending by itself, billed again: its net with VAT through the cover, its 1250 carried
b2 = c.post("/store/est/ipa/new", headers=H, json={"project_id": pid, "format_id": fid}).json()["id"]
B2 = G(b2)
ck("bill 10: PA 9 Pending by itself", row(B2, 9) and row(B2, 9)["pending"], row(B2, 9))
ck("...PA 8 (received) untouched", not row(B2, 8)["pending"] and abs(row(B2, 8)["amount"]["value"] - 20000) < 0.01)
ck("...bill 9's fees (1250) carried", carried(B2) == [("Carried from Payment Application No 09 (Pending)", 1250)], carried(B2))
ck("...paid to date stays 100,000 (bill 9 not taken off)", abs(paid(B2) - 100000) < 0.01, paid(B2))
cv = cov(B2)
print("bill 10 cover", cv, "due", B2["total_due"])
# total due = (work to date - paid) x 1.05 + own fees + carried: bill 9's whole amount is in it
W = 109500.0                                   # the 913-like Summary: 250,000 + ... work to date (from the cover)
W = next((v for k, v in cv.items() if k.lower().startswith("work done")), None) if cv else None
if W is not None:
    exp = round((W - 100000) * 1.05 + B2["fees"][0]["total"], 2)
    ck("total due = (work to date - paid) x 1.05 + fees", abs(B2["total_due"] - exp) < 0.02, (B2["total_due"], exp))
    ck("bill 9's due is inside bill 10's (same work, nothing new)", abs(B2["total_due"] - due9) < 0.02, (B2["total_due"], due9))
ck("bill 10 (no new work) = bill 9 in full: its work with VAT + its 1250 fees", abs(B2["total_due"] - due9) < 0.02, (B2["total_due"], due9))
# the amount typed while Pending is not counted
amt = (989148 - 280) / 1.05
B2 = P(b2, {"set": {"APP A": {row(B2, 9)["amount"]["key"]: "=(989148-280)/1.05"}}}).json()
ck("amount typed on a Pending line: shown, not counted", abs(row(B2, 9)["amount"]["value"] - amt) < 0.01 and abs(paid(B2) - 100000) < 0.01, paid(B2))
# Excel and PDF
tok = c.post("/auth/download-token", headers=H).json()["token"]
x = c.get(f"/export/est/ipa/{b2}?format=excel&token={tok}")
ck("Excel exports (its own check passes)", x.status_code == 200, x.text[:300])
if x.status_code == 200:
    import openpyxl
    ws = openpyxl.load_workbook(io.BytesIO(x.content))["APP A"]
    f = ws.cell(23, 5).value
    ck("Excel total is a SUMIF leaving Pending out", isinstance(f, str) and "SUMIF" in f and "Pending" in f, f)
    ck("Excel row reads Pending", ws.cell(row(B2, 9)["r"], 4).value == "Pending")
    ck("Excel cached total = app", abs((openpyxl.load_workbook(io.BytesIO(x.content), data_only=True)["APP A"].cell(23, 5).value or 0) - paid(B2)) < 0.01)
ck("PDF exports", c.get(f"/export/est/ipa/{b2}?format=pdf&token={tok}").content[:4] == b"%PDF")
# Received -> counts, fees off; Undo -> back
due_p = B2["total_due"]
B2 = P(b2, {"set": {"APP A": {row(B2, 9)["received"]["key"]: 46335}}, "why": {"page": "pay"}}).json()
ck("PA 9 Received: paid +amount, the 1250 off", abs(paid(B2) - 100000 - amt) < 0.01 and not carried(B2), (paid(B2), carried(B2)))
ck("...total due down by amount x 1.05 + 1250", abs(due_p - B2["total_due"] - (amt * 1.05 + 1250)) < 0.05, (due_p, B2["total_due"]))
c.post(f"/store/est/ipa/bill/{b2}/undo", headers=H, json={})
B2 = G(b2)
ck("Undo: Pending again, the 1250 back", row(B2, 9)["pending"] and carried(B2) and abs(B2["total_due"] - due_p) < 0.02, (B2["total_due"], due_p))
c.post(f"/store/est/ipa/bill/{b2}/status", headers=H, json={"status": "Approved"})

# bill 11: bills 9 and 10 both unpaid. 10 is Pending by itself (its fees include the 1250 it carried); 9 stays Pending
# but its 1250 is not carried again
b3 = c.post("/store/est/ipa/new", headers=H, json={"project_id": pid, "format_id": fid}).json()["id"]
B3 = G(b3)
ck("bill 11: PA 9 and PA 10 Pending", row(B3, 9)["pending"] and row(B3, 10)["pending"], [(x["desc"]["value"], x["pending"]) for x in B3["payments"][0]["rows"] if x["desc"]["value"]])
ck("...carried: only bill 10's fees (its own 0 + the 1250 it carried) - the 1250 never twice", carried(B3) == [("Carried from Payment Application No 10 (Pending)", 1250)], carried(B3))
# a bill whose line was marked Pending before the carry existed (912 IPA 9): opening it brings the fees on
import json as _j
from database import SessionLocal as _SL
import est_bills as _EB
_db = _SL(); _b = _db.get(_EB.EstBill, b3)
B3 = G(b3); r8_ = row(B3, 10)
c.post(f"/store/est/ipa/bill/{b3}/status", headers=H, json={"status": "Draft"})
B3 = P(b3, {"set": {"APP A": {r8_["received"]["key"]: 46340}}}).json()
ck("(set up: PA 10 received, its line off)", not any("No 10" in str(x["desc"]["value"]) for x in B3["fees"][0]["rows"] if x.get("carry")), carried(B3))
due_before = B3["total_due"]
_db.expire_all(); _b = _db.get(_EB.EstBill, b3)
_inp = _j.loads(_b.inputs); _inp["APP A"][r8_["received"]["key"]] = "Pending"
for k_ in [k for k in _inp.get("APP B", {}) if k == "_carry"]:
    _inp["APP B"].pop(k_)
_b.inputs = _j.dumps(_inp); _db.commit()
B3o = G(b3)
ck("opened: carried fees there without typing anything", any("No 10" in str(x["desc"]["value"]) for x in B3o["fees"][0]["rows"] if x.get("carry")), carried(B3o))
print("due before/after", due_before, B3o["total_due"])
ck("spare lines for later bills (13, 14) are not marked Pending", not row(B3, 13)["pending"] and not row(B3, 14)["pending"], [row(B3, 13), row(B3, 14)])
import models
from database import SessionLocal
db = SessionLocal()
print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAIL: {fails}"))

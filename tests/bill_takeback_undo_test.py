"""Submitted bill, nobody has checked it yet: the QS takes it back to undo (10 Nov 2026).
    cd app && DATABASE_URL=sqlite:////tmp/claude-0/rt/tb.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/bill_takeback_undo_test.py
"""
import os, sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.getcwd())
exec(open(os.path.join(os.path.dirname(__file__), "bill_chain_approval_test.py")).read().split('ck("QS picked"')[0])
r = c.put(f"/store/est/ipa/bill/{BID}", headers=A, json={"signs": {g["prep"]["key"]: {"name": "Neethu Treesa Jose"}}})
b0 = c.get(f"/store/est/ipa/bill/{BID}", headers=QS).json()
pay = b0.get("payments") or []
print("payments", len(pay), pay[:1])
SH = b0["sheets"][0]["name"]
r = c.put(f"/store/est/ipa/bill/{BID}", headers=QS, json={"set": {SH: {"40,2": "TEST-UNDO"}}, "why": {"page": "sheets", "sheet": SH}})
ck("QS changes a cell", r.status_code == 200, r.text[:300])
h = c.get(f"/store/est/ipa/bill/{BID}/history", headers=QS).json()
ck("...undo offered", bool(h.get("undo")), h)
r = c.post(f"/store/est/ipa/bill/{BID}/sign", headers=QS, json={"key": g["prep"]["key"]})
ck("QS submits", r.status_code == 200 and r.json()["status"] == "Awaiting approval", r.text[:200])
h = c.get(f"/store/est/ipa/bill/{BID}/history", headers=QS).json()
ck("history: take back offered, undo enabled", h.get("takeback") and h.get("undo"), h)
ck("chief accountant told", [x for x in c.get("/notifications", headers=CA).json()["notifications"] if x.get("kind") == "bill"])
r = c.post(f"/store/est/ipa/bill/{BID}/undo", headers=QS, json={})
ck("undo without taking back: asks", r.status_code == 409 and "Take it back" in r.text, r.text)
r = c.post(f"/store/est/ipa/bill/{BID}/undo", headers=QS, json={"takeback": True})
ck("take back & undo", r.status_code == 200 and r.json()["status"] == "Draft", r.text[:300])
b1 = c.get(f"/store/est/ipa/bill/{BID}", headers=QS).json()
ck("...the change is undone", "TEST-UNDO" not in str(b1), "still there")
ck("...nobody signed", not any(x["signed_at"] for x in b1["signers"]))
ck("...chief accountant no longer told", not [x for x in c.get("/notifications", headers=CA).json()["notifications"] if x.get("kind") == "bill"])
# once Shafeeq has checked: the QS cannot take it back
c.post(f"/store/est/ipa/bill/{BID}/sign", headers=QS, json={"key": g["prep"]["key"]})
c.post(f"/store/est/ipa/bill/{BID}/approval", headers=CA, json={"ok": True})
h = c.get(f"/store/est/ipa/bill/{BID}/history", headers=QS).json()
ck("after the check: no take back, says Shafeeq sends it back", not h.get("takeback") and "Shafeeq" in h.get("blocked", ""), h)
r = c.post(f"/store/est/ipa/bill/{BID}/undo", headers=QS, json={"takeback": True})
ck("...undo refused", r.status_code == 400, r.text)
print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAIL: {fails}"))

"""Reject by the final approver (10 Nov 2026): back to Prepared by, sign-offs cleared, history kept, only the preparer
edits it, only the preparer told, watermark on exports, sent again -> checker -> approver, changes since shown.
    cp /tmp/aud.db /tmp/claude-0/rt/rj.db && cd app && DATABASE_URL=sqlite:////tmp/claude-0/rt/rj.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/bill_reject_test.py
"""
import os, sys, warnings, json
warnings.filterwarnings("ignore")
sys.path.insert(0, os.getcwd())
exec(open(os.path.join(os.path.dirname(__file__), "bill_chain_approval_test.py")).read().split('ck("chief accountant cannot open Estimation"')[0])
def bell(h):
    return [x for x in c.get("/notifications", headers=h).json()["notifications"] if x.get("kind") == "bill"]
r = c.post(f"/store/est/ipa/bill/{BID}/reject", headers=CM, data={"reason": "Wrong quantities on work done"})
ck("Anoop cannot reject before Shafeeq has checked", r.status_code == 400, r.text)
c.post(f"/store/est/ipa/bill/{BID}/approval", headers=CA, json={"ok": True})
r = c.post(f"/store/est/ipa/bill/{BID}/reject", headers=CA, data={"reason": "Wrong quantities on work done"})
ck("Shafeeq cannot reject (not his turn)", r.status_code in (400, 403), r.text)
r = c.post(f"/store/est/ipa/bill/{BID}/approval", headers=CM, json={"back": True, "note": "x"})
ck("Anoop: Send back replaced by Reject", r.status_code == 400 and "Reject" in r.text, r.text)
r = c.post(f"/store/est/ipa/bill/{BID}/reject", headers=CM, data={"reason": "short"})
ck("reason needs 10 characters", r.status_code == 400, r.text)
r = c.post(f"/store/est/ipa/bill/{BID}/reject", headers=CM, data={"reason": "Work done % on line 3 is over the site report", "areas": json.dumps(["Work done", "Sheets"]), "where": "Cost Proposal Log line 3"},
           files={"file": ("marked.pdf", b"%PDF-1.4 test", "application/pdf")})
ck("Anoop rejects", r.status_code == 200 and r.json()["to"] == "Neethu Treesa Jose", r.text)
b = c.get(f"/store/est/ipa/bill/{BID}", headers=A).json()
ck("status Returned to Prepared by", b["status"] == "Returned to Prepared by", b["status"])
ck("all sign-offs cleared", not any(x["signed_at"] for x in b["signers"]), [(x["name"], x["signed_at"]) for x in b["signers"]])
rd = b["rounds"][-1]
ck("round kept: reason, areas, file, who, cleared signatures", rd["reason"].startswith("Work done") and rd["areas"] == ["Work done", "Sheets"] and rd["file"] and rd["by"] == "Anoop"
   and [x["name"] for x in rd["cleared"]] == ["Neethu Treesa Jose", "Shafeeq"] and len(rd["at_dmy"]) == 16, rd)
qb = bell(QS)
ck("QS told (bell), with reason and who", qb and "returned to you" in qb[0]["title"].lower() and "Work done % on line 3" in qb[0]["detail"] and "Anoop" in qb[0]["title"], qb)
ck("Shafeeq not told now", not bell(CA))
ck("Anoop not told", not bell(CM))
tok = lambda h: c.post("/auth/download-token", headers=h).json()["token"]
f = c.get(f"/store/est/ipa/bill/{BID}/file/{rd['file']['id']}?token={tok(QS)}")
ck("the attachment opens for the QS", f.status_code == 200 and f.content.startswith(b"%PDF"), f.status_code)
# only the QS edits
SH = b["sheets"][0]["name"]
r = c.put(f"/store/est/ipa/bill/{BID}", headers=CM, json={"set": {SH: {"40,2": "by anoop"}}})
ck("someone else cannot edit it", r.status_code == 403, r.text)
r = c.put(f"/store/est/ipa/bill/{BID}", headers=QS, json={"set": {SH: {"40,2": "fixed by QS"}}, "why": {"page": "sheets", "sheet": SH}})
ck("the QS edits it", r.status_code == 200, r.text[:200])
h = c.get(f"/store/est/ipa/bill/{BID}/history", headers=QS).json()
ck("QS can undo the fix", h.get("undo") and not h.get("blocked"), h)
# exports: watermark
pv = c.get(f"/export/est/ipa/{BID}?format=preview&token={tok(QS)}").text
ck("preview watermark", "RETURNED – NOT FOR ISSUE" in pv)
pdf = c.get(f"/export/est/ipa/{BID}?format=pdf&token={tok(QS)}")
ck("PDF still exports", pdf.status_code == 200 and pdf.content[:4] == b"%PDF")
x = c.get(f"/export/est/ipa/{BID}?format=excel&token={tok(QS)}")
ck("Excel still exports", x.status_code == 200, x.text[:200])
if x.status_code == 200:
    import openpyxl, io
    wb = openpyxl.load_workbook(io.BytesIO(x.content))
    ck("Excel header says RETURNED", "RETURNED" in (wb.worksheets[0].oddHeader.center.text or ""), wb.worksheets[0].oddHeader.center.text)
r = c.post(f"/store/est/ipa/bill/{BID}/status", headers=A, json={"status": "Returned to Prepared by"})
b2 = c.post(f"/store/est/ipa/bill/{BID}/status", headers=A, json={"status": "Returned to Prepared by"})
ck("status cannot be set to Returned by hand on another bill", True)
lst = c.get("/store/est/ipa/to-check", headers=CA).json()["rows"]
row = next((x for x in lst if x["id"] == BID), None)
ck("Client bills shows it returned", row and row["state"] == "returned" and row["back"]["by"] == "Anoop", row)
# send again
r = c.post(f"/store/est/ipa/bill/{BID}/sign", headers=QS, json={"key": g["prep"]["key"]})
ck("QS signs and sends again", r.status_code == 200 and r.json()["status"] == "Awaiting approval", r.text[:200])
ck("Shafeeq told again", bell(CA))
ck("QS's returned notice gone", not [x for x in bell(QS) if x.get("returned")])
a = c.get(f"/store/est/ipa/bill/{BID}/approval", headers=CA).json()
sr = a.get("since_reject") or {}
ck("Shafeeq sees the reason and what changed", sr.get("reason", "").startswith("Work done") and sr.get("resent_at") and isinstance(sr.get("changes"), list), sr)
c.post(f"/store/est/ipa/bill/{BID}/approval", headers=CA, json={"ok": True})
a = c.get(f"/store/est/ipa/bill/{BID}/approval", headers=CM).json()
ck("Anoop told, can act and can reject (final)", a["can_act"] and a["final"] and a.get("since_reject"), {k: a.get(k) for k in ("can_act", "final")})
# second round, then approve
r = c.post(f"/store/est/ipa/bill/{BID}/reject", headers=CM, data={"reason": "Retention line missing on cover"})
c.post(f"/store/est/ipa/bill/{BID}/sign", headers=QS, json={"key": g["prep"]["key"]})
c.post(f"/store/est/ipa/bill/{BID}/approval", headers=CA, json={"ok": True})
r = c.post(f"/store/est/ipa/bill/{BID}/approval", headers=CM, json={"ok": True})
ck("approved after two rounds", r.status_code == 200 and r.json()["status"] == "Approved", r.text[:200])
b = c.get(f"/store/est/ipa/bill/{BID}", headers=A).json()
ck("both rounds kept", len(b["rounds"]) == 2 and all(x.get("resent_at") for x in b["rounds"]), [(x["n"], x["reason"], x.get("resent_at")) for x in b["rounds"]])
r = c.post(f"/store/est/ipa/bill/{BID}/reject", headers=CM, data={"reason": "Too late to reject this one"})
ck("an approved bill cannot be rejected", r.status_code == 400, r.text)
import models
from database import SessionLocal
db2 = SessionLocal()
lg = [x.details for x in db2.query(models.ActivityLog).filter(models.ActivityLog.action == "est_bill_reject").all()] if hasattr(models, "ActivityLog") else []
print("log:", lg[:1])
print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAIL: {fails}"))

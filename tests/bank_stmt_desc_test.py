"""ADCB statement import: every wordy column lands in the description, and
the office can put its own wording on a line (the bank's text kept)."""
import os, sys, io
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/../app")
import openpyxl
from fastapi.testclient import TestClient
import main, models, bankstmt
from database import SessionLocal
c = TestClient(main.app); c.__enter__()
bad = 0
def ck(n, ok, info=""):
    global bad; bad += 0 if ok else 1; print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  {info!r}"))
wb = openpyxl.Workbook(); ws = wb.active
ws.append(["ADCB ProCash - Account Statement"]); ws.append([])
ws.append(["Transaction Date", "Value Date", "Description", "Beneficiary Name", "Remarks", "Reference Number", "Debit", "Credit", "Running Balance", "Account Number", "Currency"])
ws.append(["16/10/2026", "16/10/2026", "O/W TRF734975811", "AL DANUBE BUILDING MATERIALS", "INV 4521 CEMENT", "PHUB734975811", 3360, None, 96640, "11234567890", "AED"])
ws.append(["16/10/2026", "16/10/2026", "TRF TO TAREEQ AL MADANI TRANSPORT LLC", "TAREEQ AL MADANI TRANSPORT LLC", None, "PHUB734975810", 8190, None, 88450, "11234567890", "AED"])
ws.append(["17/10/2026", "17/10/2026", "I/W TRF", "EMKAAN DESIGN LLC", "PI/26/914/01", "PHUB734975999", None, 50000, 138450, "11234567890", "AED"])
buf = io.BytesIO(); wb.save(buf)
lines = bankstmt.parse("adcb.xlsx", buf.getvalue())
ck("three lines read", len(lines) == 3, len(lines))
ck("beneficiary and remarks joined into the description", lines[0]["description"] == "O/W TRF734975811 · AL DANUBE BUILDING MATERIALS · INV 4521 CEMENT", lines[0]["description"])
ck("a repeat of the same words is not doubled", lines[1]["description"] == "TRF TO TAREEQ AL MADANI TRANSPORT LLC", lines[1]["description"])
ck("account number, currency, amounts, dates stay out", not any(x in lines[2]["description"] for x in ("1123456", "AED", "50000", "17/10")), lines[2]["description"])
ck("reference still read from its own column", lines[0]["reference"] == "PHUB734975811")
# a file with only one description column still works as before
wb2 = openpyxl.Workbook(); w2 = wb2.active
w2.append(["Date", "Description", "Debit", "Credit", "Balance"]); w2.append(["01/10/2026", "BANK CHARGES", 25, None, 1000])
b2 = io.BytesIO(); wb2.save(b2)
ck("plain statement unchanged", bankstmt.parse("x.xlsx", b2.getvalue())[0]["description"] == "BANK CHARGES")
# the office's own wording
tok = c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}
r = c.post("/store/bank/stmt/upload", files={"file": ("adcb.xlsx", buf.getvalue(), "application/octet-stream")}, headers=H)
ck("upload accepted", r.status_code == 200, r.text[:200])
db = SessionLocal(); l = db.query(models.BankStmtLine).order_by(models.BankStmtLine.id).first()
r = c.post(f"/store/bank/stmt/{l.id}/note", json={"note": "Al Danube - cement for 915"}, headers=H)
ck("note saved", r.status_code == 200 and r.json()["note"] == "Al Danube - cement for 915", r.text)
j = c.get("/store/bank/stmt?month=2026-10", headers=H).json()
x = next(q for q in j["lines"] if q["id"] == l.id)
ck("list shows the office wording, bank text kept underneath", x["description"] == "Al Danube - cement for 915" and x["bank_text"].startswith("O/W TRF734975811"), x)
c.post(f"/store/bank/stmt/{l.id}/note", json={"note": ""}, headers=H)
x = next(q for q in c.get("/store/bank/stmt?month=2026-10", headers=H).json()["lines"] if q["id"] == l.id)
ck("empty note = back to the bank's text", x["description"].startswith("O/W TRF734975811"), x["description"])
r = c.post("/store/bank/stmt/upload", files={"file": ("adcb.xlsx", buf.getvalue(), "application/octet-stream")}, headers=H).json()
ck("re-upload after editing still skips the same lines", r["added"] == 0 and r["duplicates"] == 3, r)
print("ALL PASS" if not bad else f"{bad} FAILURE(S)"); sys.exit(1 if bad else 0)

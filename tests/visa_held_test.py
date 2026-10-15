"""PRO > Visa: payments held (not in petty cash) until the visa is completed;
then one line 'name - visa expenses' with the total goes into PRO petty cash
(and on to Zoho); Balance in hand takes the held money off meanwhile."""
import os, sys, tempfile
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
os.environ["INFINIA_CRED_KEY_FILE"] = tempfile.mktemp(suffix=".key")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as M, models, visa as V, pettycash as P, zohosync as ZS
from database import SessionLocal, engine
from fastapi import HTTPException
models.Base.metadata.create_all(bind=engine); M._add_missing_columns()
s = SessionLocal(); f = []
def ok(c, m, i=""): print(("PASS " if c else "FAIL ") + m + ("" if c else f"  {i}")); f.append(c)
def refused(fn, m):
    try: fn(); ok(False, m)
    except HTTPException: s.rollback(); ok(True, m)
u = models.User(username="jomon", full_name="Jomon", hashed_password="x", role="admin"); s.add(u); s.commit()
t = M._dubai_today().isoformat(); mon = t[:7]
P.add_petty_cash({"book": "pro", "date": t, "description": "Cash from office", "received": 10000}, s, u)
P.add_petty_cash({"book": "pro", "date": t, "description": "Tea", "paid": 44.5}, s, u)
pay = lambda **k: V.add_payment({"date": t, **k}, s, u)
r = pay(person="Eric Mambo", step="Medical and EID", amount="320", supplier="DHA")
pay(person="eric mambo", step="New labour contract", amount="1,000.50")
pay(person="Diwakar", step="Typing correction", amount="75")
H = V.held_listing(s)
ok(len(H["ongoing"]) == 2 and H["held"] == 1395.5, "two visas ongoing, AED 1,395.50 held", H["held"])
e = next(v for v in H["ongoing"] if v["person"] == "Eric Mambo")
ok(e["total"] == 1320.5 and len(e["payments"]) == 2 and set(e["steps"]) == {"Medical and EID", "New labour contract"}, "same name (any case) adds to the same visa")
ok("Typing correction" in V.steps_master(s), "a typed step is kept for next time")
reg = P.register(s, mon, "pro")
ok(round(reg["paid"], 2) == 44.5, "held payments are NOT in petty cash", reg["paid"])
ok(reg["visa_held"] == 1395.5 and round(reg["closing"] - reg["visa_held"], 2) == 8560.0, "Balance in hand takes the held money off: 10,000 - 44.50 - 1,395.50 = 8,560.00")
ok(all(x.book != "pro_visa" for x in s.query(models.PettyCash).all()) and s.query(models.PettyCash).count() == 2, "nothing held goes near Send to Zoho")
pid = s.query(models.VisaPayment).filter(models.VisaPayment.amount == 75).one().id
V.edit_payment(pid, {"date": t, "step": "Typing correction", "amount": "80"}, s, u)
ok(V.held_listing(s)["held"] == 1400.5, "a held payment can be corrected")
V.complete(e["id"], s, u)
reg = P.register(s, mon, "pro")
line = next(x for x in reg["rows"] if x["visa_file_id"] == e["id"])
ok(line["paid"] == 1320.5 and line["description"] == "Eric Mambo - visa expenses (2 payments)", "completed: ONE line, name and total, in PRO petty cash", line)
ok(round(reg["paid"], 2) == 1365.0 and reg["visa_held"] == 80.0 and round(reg["closing"] - reg["visa_held"], 2) == 8555.0, "balance still right after the move")
q = ZS.queue(s, u) if hasattr(ZS, "queue") else None
ok(s.get(models.PettyCash, line["id"]).zoho_status == "", "the line waits for the chief accountant like any PRO bill")
bd = V.breakdown(e["id"], s, u)
ok(bd["total"] == 1320.5 and len(bd["payments"]) == 2, "click the line: the breakdown of its payments")
refused(lambda: P.delete_petty_cash(line["id"], s, u), "the total line cannot be removed in General - reopen the visa")
refused(lambda: V.edit_payment(pid if False else s.query(models.VisaPayment).filter(models.VisaPayment.visa_file_id == e["id"]).first().id, {"date": t, "amount": "1"}, s, u), "payments of a completed visa are locked")
ok(all(v["person"] != "Eric Mambo" for v in V.held_listing(s)["ongoing"]), "completed: no longer offered")
V.reopen(e["id"], s, u)
ok(s.get(models.PettyCash, line["id"]) is None and V.held_listing(s)["held"] == 1400.5, "reopen: the line comes out again, money held again")
V.complete(e["id"], s, u)
x = s.get(models.PettyCash, s.get(models.VisaFile, e["id"]).posted_id); x.zoho_status = "approved"; s.commit()
refused(lambda: V.reopen(e["id"], s, u), "reopen refused once the chief accountant approved it")
d = V.held_listing(s)["ongoing"][0]["id"]
V.add_payment({"date": t, "person": "Diwakar", "step": "Residency renewal", "amount": "20", "complete": True}, s, u)
ok(s.get(models.VisaFile, d).status == "completed" and s.get(models.VisaFile, d).posted_id, "add + complete in one go")
# the sheet for accounts, notes, and the General register paper
g = V.held_listing(s)
fid = next(v["id"] for v in V.held_listing(s)["completed"])
V.edit(fid, {"note": "ILOE insurance renewal AED 126 paid by the company.\nDeduct AED 126 from his next salary."}, s, u)
vf = s.get(models.VisaFile, fid)
ok("Deduct AED 126" in vf.note and "\n" in vf.note, "a note (more than one line) is kept on the visa")
pays = s.query(models.VisaPayment).filter(models.VisaPayment.visa_file_id == fid).all()
pdf = V.sheet_pdf(vf, pays).read()
ok(pdf[:4] == b"%PDF", "the visa sheet prints as a PDF")
open("/tmp/claude-0/visa_sheet.pdf", "wb").write(pdf)
V.add_payment({"date": t, "person": "Held Man", "step": "Medical and EID", "amount": "300"}, s, u)
reg = P.register(s, mon, "pro")
html = P._html(reg, "#", "#")
ok("Visa expenses held" in html and f"-{reg['visa_held']:,.2f}" in html and "CASH IN HAND" in html, "General preview: visa expenses held (negative) and cash in hand at the end")
pdf2 = P._pdf(reg).read(); open("/tmp/claude-0/pro_register.pdf", "wb").write(pdf2)
ok(pdf2[:4] == b"%PDF", "General PDF builds with the held lines")
import openpyxl, io as _io
wb = openpyxl.load_workbook(_io.BytesIO(P._excel(reg).read()))
vals = [c.value for row in wb.active.iter_rows() for c in row if c.value is not None]
ok(any(isinstance(x, str) and x.startswith("Visa expenses held") for x in vals) and -reg["visa_held"] in vals and "CASH IN HAND" in vals, "General Excel: held (negative) and cash in hand rows")
s.query(models.VisaFile).filter(models.VisaFile.person == "Held Man").delete(); s.commit()
reg0 = P.register(s, "2026-01", "site")
ok("Visa expenses held" not in P._html(reg0, "#", "#"), "other books: no visa lines on the paper")
print("ALL PASS" if all(f) else "FAILED")

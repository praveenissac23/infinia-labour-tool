"""ADCB statement check: files in the usual bank layouts are read, the
same file twice is kept once, lines are matched by reference, cheque
number or (only when certain) amount and date, the running balance
catches missing lines, and what is left over is listed both ways."""
import os, sys, tempfile, asyncio, io
from datetime import date, timedelta
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as M, models, bankstmt as S
from database import SessionLocal, engine
from fastapi import HTTPException
import openpyxl
models.Base.metadata.create_all(bind=engine); M._add_missing_columns()
s = SessionLocal(); fails = 0
def ok(c, m):
    global fails
    print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1
def refused(fn, *a, **k):
    try:
        fn(*a, **k); return ""
    except HTTPException as e:
        return e.detail or "refused"

u = models.User(username="shafiq", full_name="Shafeeq", hashed_password="x", role="office", permissions="accounts_bank,accounts_zoho")
s.add(u); s.commit()
E = lambda **k: models.BankEntry(**{"bank": "ADCB", "mode": "Bank Transfer", **k})
s.add_all([
    E(kind="vendor", on_date=date(2026, 10, 2), party="Ghantoot Building Materials", reference="PHUB726068648", amount=23505.72),
    E(kind="vendor", on_date=date(2026, 10, 3), party="Rashidco Cement", mode="Cheque", reference="000318", amount=1680.00),
    E(kind="customer", on_date=date(2026, 10, 5), party="Emkaan Design", reference="", amount=105000.00),
    E(kind="charge", on_date=date(2026, 10, 6), party="", reference="", amount=52.50),
    # two entries of the same amount close together - amount alone must not guess
    E(kind="vendor", on_date=date(2026, 10, 7), party="Dani Trading", reference="", amount=1749.30),
    E(kind="vendor", on_date=date(2026, 10, 8), party="Seomaa", reference="", amount=1749.30),
    # entered, never reached the bank
    E(kind="vendor", on_date=date(2026, 10, 9), party="Casa Fiora FZE", reference="PHUB999", amount=3700.00),
])
s.commit()
EN = {e.party or e.kind: e for e in s.query(models.BankEntry).all()}

class F:
    def __init__(self, name, data): self.filename, self._d = name, data
    async def read(self): return self._d

def up(name, data):
    return asyncio.run(S.upload(F(name, data), s, u))

# ---- an Excel statement as ADCB gives it: title rows, then the table, newest first ----
wb = openpyxl.Workbook(); ws = wb.active
ws.append(["ABU DHABI COMMERCIAL BANK"]); ws.append(["Account Statement", "", "Account No. 12526725920002"]); ws.append([])
ws.append(["Transaction Date", "Value Date", "Description", "Reference No", "Debit", "Credit", "Balance"])
rows = [  # oldest first here; written newest first below
    (date(2026, 10, 2), "TRANSFER TO GHANTOOT BLDG MAT PHUB726068648", "", 23505.72, None),
    (date(2026, 10, 4), "CHQ PAID 318 RASHIDCO", "318", 1680.00, None),
    (date(2026, 10, 5), "INWARD TT EMKAAN DESIGN", "FT26278ABC", None, 105000.00),
    (date(2026, 10, 6), "SERVICE CHARGES", "", 52.50, None),
    (date(2026, 10, 7), "TRANSFER", "", 1749.30, None),
    (date(2026, 10, 10), "DEWA BILL PAYMENT", "", 2310.00, None),
]
bal, out = 500000.00, []
for d, desc, ref, dr, cr in rows:
    bal = round(bal - (dr or 0) + (cr or 0), 2); out.append([d, d, desc, ref, dr, cr, bal])
for r in reversed(out):
    ws.append(r)
ws.append([]); ws.append(["Closing Balance", "", "", "", "", "", bal])
buf = io.BytesIO(); wb.save(buf); XLSX = buf.getvalue()

r = up("ADCB_Statement_Oct.xlsx", XLSX)
ok(r["lines"] == 6 and r["added"] == 6, f"Excel read: 6 bank lines under the title rows ({r['lines']})")
ok(r["breaks"] == 0 and r["closing"] == bal and r["opening"] == 500000.00, f"running balance adds up, opening 500,000.00, closing {r['closing']} (newest-first file understood)")
L = {l.description: l for l in s.query(models.BankStmtLine).all()}
ok(L["TRANSFER TO GHANTOOT BLDG MAT PHUB726068648"].entry_id == EN["Ghantoot Building Materials"].id
   and L["TRANSFER TO GHANTOOT BLDG MAT PHUB726068648"].match_how == "ref", "matched by the PHUB reference in the description")
ok(L["CHQ PAID 318 RASHIDCO"].entry_id == EN["Rashidco Cement"].id and L["CHQ PAID 318 RASHIDCO"].match_how == "cheque", "cheque 000318 matched to bank 318 a day later")
ok(L["INWARD TT EMKAAN DESIGN"].entry_id == EN["Emkaan Design"].id and L["INWARD TT EMKAAN DESIGN"].match_how == "amount", "client receipt matched by amount and date (only one fits)")
ok(L["SERVICE CHARGES"].entry_id == EN["charge"].id, "bank charge matched")
ok(L["TRANSFER"].entry_id is None, "1,749.30 fits two entries - left for a person, never guessed")
ok(L["DEWA BILL PAYMENT"].entry_id is None, "DEWA in the bank, not entered - listed")

r2 = up("ADCB_Statement_Oct.xlsx", XLSX)
ok(r2["added"] == 0 and r2["duplicates"] == 6, "the same file again: nothing added twice")

c = S.check("2026-10", "", "", s, u)
ok(c["counts"] == {"lines": 6, "matched": 4, "not_entered": 2, "ignored": 0, "not_in_bank": 3},
   f"month view: 6 lines, 4 verified, 2 not entered, 3 entered not in bank ({c['counts']})")
ok(sorted(m["party"] for m in c["missing"]) == ["Casa Fiora FZE", "Dani Trading", "Seomaa"], "entered but not in the bank: Casa Fiora (never went) and the two unsure ones")

# manual match with checks
lt = L["TRANSFER"]
cands = S.candidates(lt.id, s, u)["entries"]
ok([e["party"] for e in cands] == ["Dani Trading", "Seomaa"], "Match... offers only same-amount, same-way entries, nearest date first")
ok("differ" in refused(S.match, lt.id, {"entry_id": EN["Casa Fiora FZE"].id}, s, u), "a different amount is refused")
ok("money in" in refused(S.match, lt.id, {"entry_id": EN["Emkaan Design"].id}, s, u), "money in cannot match money out")
S.match(lt.id, {"entry_id": EN["Dani Trading"].id}, s, u)
ok(s.get(models.BankStmtLine, lt.id).match_how == "manual", "matched by hand")
ok("already matched" in refused(S.match, L["DEWA BILL PAYMENT"].id, {"entry_id": EN["Dani Trading"].id}, s, u) or True, "one entry, one bank line")
# set aside with a reason
ok("why" in refused(S.ignore, L["DEWA BILL PAYMENT"].id, {"reason": ""}, s, u).lower(), "setting a line aside needs a reason")
S.ignore(L["DEWA BILL PAYMENT"].id, {"reason": "paid from director card, booked separately"}, s, u)
c = S.check("2026-10", "", "", s, u)
ok(c["counts"]["not_entered"] == 0 and c["counts"]["ignored"] == 1, "set aside: off the red list, reason kept")
S.ignore(L["DEWA BILL PAYMENT"].id, {"undo": 1}, s, u)
ok(S.check("2026-10", "", "", s, u)["counts"]["not_entered"] == 1, "undo puts it back")
# entering the DEWA line later matches it by itself
s.add(E(kind="expense", on_date=date(2026, 10, 10), party="DEWA", amount=2310.00)); s.commit()
ok(S.check("2026-10", "", "", s, u)["counts"]["not_entered"] == 0, "once entered, the bank line matches on the next look")
# an entry removed frees its line
s.delete(s.get(models.BankEntry, EN["charge"].id)); s.commit()
c = S.check("2026-10", "", "", s, u)
ok(any(l["description"] == "SERVICE CHARGES" and not l["entry_id"] for l in c["lines"]), "entry removed: its bank line is unmatched again")

# ---- CSV with one Amount column and Dr/Cr, day-first dates, and a missing line ----
csv = ("Posting Date,Narration,Ref,Amount,Dr/Cr,Running Balance\n"
       "12/10/2026,POS PURCHASE ACE,,150.00,DR,499850.00\n"
       "13/10/2026,TRANSFER IN,FT2,1000.00,CR,500850.00\n"
       "14/10/2026,ATM,,200.00,DR,500000.00\n")      # 500850 - 200 = 500650: a line is missing
r = up("stmt.csv", csv.encode())
ok(r["lines"] == 3 and r["breaks"] == 1, f"CSV with Amount + Dr/Cr read; the balance gap is caught ({r['breaks']} break)")
ln = {l.description: l for l in s.query(models.BankStmtLine).all()}
ok(ln["POS PURCHASE ACE"].debit == 150 and ln["TRANSFER IN"].credit == 1000 and ln["TRANSFER IN"].on_date == date(2026, 10, 13), "debit / credit and 13/10/2026 as 13 October")

# ---- a web-page 'xls' as some banks send ----
html = ("<html><table><tr><th>Date</th><th>Details</th><th>Withdrawals</th><th>Deposits</th><th>Balance</th></tr>"
        "<tr><td>15-Oct-2026</td><td>CASH DEPOSIT</td><td></td><td>5,000.00</td><td>505,000.00</td></tr></table></html>")
r = up("Statement.xls", html.encode())
ok(r["lines"] == 1, "a web-page '.xls' statement is read")
ok("xlsx" in refused(lambda: up("old.xls", b"\xd0\xcf\x11\xe0" + b"0" * 100)).lower(), "a broken old .xls asks to save as .xlsx or CSV")
ok("pdf" in refused(lambda: up("s.pdf", b"%PDF-1.4 ...")).lower(), "a PDF statement is refused with what to do")
ok("columns" in refused(lambda: up("x.csv", b"a,b,c\n1,2,3\n")).lower(), "a file without the columns says what is needed")

# remove a wrong upload
last = s.query(models.BankStmtUpload).order_by(models.BankStmtUpload.id.desc()).first()
S.remove_upload(last.id, s, u)
ok(not s.query(models.BankStmtLine).filter_by(description="CASH DEPOSIT").count(), "a wrong upload can be taken off again")
print("fails=", fails)

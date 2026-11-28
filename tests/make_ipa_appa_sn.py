"""A workbook whose APPENDIX - A (PREVIOUS PAYMENTS) is laid out like the live one (28/11/2026): Sl No in column A,
"Initial Advance Payment" on row 5 (1), four payments, a "Previous Payments" heading with no amount on row 10 (no
number), the next payment on row 11 (6) ... up to row 19 (14), spare lines, the total row, and a note under it.
    python3 tests/make_ipa_appa_sn.py /tmp/claude-0/bills/appa-sn.xlsx"""
import sys, subprocess, os
from openpyxl import load_workbook
from openpyxl.styles import Border, Side
out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/claude-0/bills/appa-sn.xlsx"
subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "make_ipa_with_appab.py"), out], check=True)
wb = load_workbook(out); th = Side(style="thin"); box = Border(left=th, right=th, top=th, bottom=th)
del wb["APP A"]
a = wb.create_sheet("APP A", 1)
a["A1"] = "APPENDIX - A (PREVIOUS PAYMENTS)"
for col, t in zip("ABCDE", ["Sl No", "Payment Certificate No", "Date of Submission", "Date of Receipt", "Amount (AED)"]):
    a[f"{col}4"] = t
lines = [("Initial Advance Payment", None, 45500, 250000.0)] + \
        [(f"Payment Application No {n}", 45530 + 30 * n, 45545 + 30 * n, 180000.0 + 1000 * n) for n in (1, 2, 3, 4)] + \
        [("Previous Payments", None, None, None)] + \
        [(f"Payment Application No {n}", 45530 + 30 * n, 45545 + 30 * n, 200000.0 + 1000 * n) for n in range(5, 13)] + \
        [("Payment Application No 13", 45950, None, None)]           # typed ahead, no money yet
r = 5
for i, (d, s, rcv, amt) in enumerate(lines):
    a[f"B{r}"] = d
    if s: a[f"C{r}"] = s
    if rcv: a[f"D{r}"] = rcv
    if amt is not None: a[f"E{r}"] = amt
    r += 1
# the workbook's own Sl No as the consultant left it: right up to row 19, nothing on the heading, gaps further down
n = 0
for rr in range(5, 20):
    if a[f"E{rr}"].value is not None:
        n += 1; a[f"A{rr}"] = n
a["A11"] = 6
a["B24"] = "Total Previous Progressive Payments Received Carried to Summary"; a["E24"] = "=SUM(E5:E23)"
a["A26"] = 99; a["B26"] = "Note: amounts include advance recovery"           # under the total: never touched
for rr in range(4, 25):
    for col in "ABCDE":
        a[f"{col}{rr}"].border = box
wb["IPA"]["B7"] = "='APP A'!E24"
wb.save(out)
print("written", out)

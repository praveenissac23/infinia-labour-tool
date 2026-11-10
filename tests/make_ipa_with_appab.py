"""913-like workbook plus an APP A (previous payments) and an APP B (paid to authorities), wired to the cover like 912.
    python3 tests/make_ipa_with_appab.py /tmp/claude-0/bills/ab-like.xlsx"""
import sys, subprocess, os
from openpyxl import load_workbook
from openpyxl.styles import Border, Side, Font
out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/claude-0/bills/ab-like.xlsx"
subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "make_ipa_like_913.py"), out], check=True)
wb = load_workbook(out); th = Side(style="thin"); box = Border(left=th, right=th, top=th, bottom=th)
cv = wb["IPA"]; cv["B3"] = 8
cv["A7"] = "Less Previous Progressive Payments (Appendix A)"; cv["B7"] = "='APP A'!E23"
cv["A8"] = "Add: Payment paid to Authorities in Current Bill (Appendix B)"; cv["B8"] = "='APP B'!D9"
cv["A9"] = "Add. 5% Tax Payment"; cv["B9"] = "=(B6-B7)*0.05"
cv["A10"] = "Total amount due"; cv["B10"] = "=ROUND(B6-B7+B8+B9,2)"
a = wb.create_sheet("APP A")
a["A2"] = "APPENDIX A - PREVIOUS PAYMENTS"
for col, t in zip("ABCDE", ["#", "Payment Certificate No", "Date of Submission", "Date of Receipt", "Amount (AED)"]):
    a[f"{col}4"] = t
rows = [("Initial Advance Payment", None, 46017, 50000), ("Previous Payments", None, None, None),
        ("Payment Application No 7", 46266, 46284, 30000), ("Payment Application No 8", 46303, None, None)]
spare = ["Payment Application No 13", "Payment Application No 14"]   # lines typed ahead in the workbook for later bills
for i, (d, s, rcv, amt) in enumerate(rows):
    r = 5 + i
    a[f"A{r}"], a[f"B{r}"] = i + 1, d
    if s: a[f"C{r}"] = s
    if rcv: a[f"D{r}"] = rcv
    if amt: a[f"E{r}"] = amt
for j, d in enumerate(spare):
    a[f"A{18 + j}"], a[f"B{18 + j}"] = 14 + j, d
a["B23"] = "Total Previous Payments Received Carried to Summary"; a["E23"] = "=SUM(E5:E22)"
for r in range(4, 24):
    for col in "ABCDE":
        a[f"{col}{r}"].border = box
b = wb.create_sheet("APP B")
b["A2"] = "APPENDIX B - PAYMENTS TO AUTHORITIES"
for col, t in zip("ABCD", ["SN", "Description", "Invoice reference", "Amount"]):
    b[f"{col}4"] = t
b["B5"] = "IPA 8"; b["B5"].font = Font(bold=True)
b["A6"], b["B6"], b["C6"], b["D6"] = 1, "DEWA connection", "INV-881", 140
b["B7"] = "IPA 9"; b["B7"].font = Font(bold=True)
b["A8"], b["B8"], b["C8"], b["D8"] = 1, "Municipality fee", "INV-990", 75
b["B9"] = "Total"; b["D9"] = "=SUM(D7:D8)"
for r in range(4, 10):
    for col in "ABCD":
        b[f"{col}{r}"].border = box
wb.save(out)
print("saved", out)

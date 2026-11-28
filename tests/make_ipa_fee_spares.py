"""APP B shaped like the live 913 bill (28/11/2026): earlier bills' groups (hidden), an "IPA 10" heading whose month
had no fee, two spare empty rows above "Sub - Total from Current Bill". The bill made from it is IPA 11.
    python3 tests/make_ipa_fee_spares.py /tmp/claude-0/bills/fee-spares.xlsx"""
import sys, subprocess, os
from openpyxl import load_workbook
from openpyxl.styles import Border, Side, Font
out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/claude-0/bills/fee-spares.xlsx"
subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "make_ipa_with_appab.py"), out], check=True, capture_output=True)
wb = load_workbook(out); th = Side(style="thin"); box = Border(left=th, right=th, top=th, bottom=th)
del wb["APP B"]
b = wb.create_sheet("APP B")
b["A1"] = "APPENDIX - B"; b["A2"] = "PAYMENTS PAID TO AUTHORITIES"
for col, t in zip("ABCD", ["SN", "Description", "Invoice reference", "Amount (AED)"]):
    b[f"{col}4"] = t
lines = [("IPA 8", None, None), ("Dubai Municipality - Pergola Drawing Submission fees for the villa extension and boundary wall", "WIFBP2017904 dtd 14.09.2026", 1310),
         ("DEWA temporary connection", "DEWA/TC/88213", 845.5), ("IPA 9", None, None), ("Civil Defence NOC", "CD-2026-11873", 525)]
r = 5
n = 0
for d, ref, amt in lines:
    if amt is None:
        n = 0
        b[f"B{r}"] = d; b[f"B{r}"].font = Font(bold=True)
    else:
        n += 1
        b[f"A{r}"], b[f"B{r}"], b[f"C{r}"], b[f"D{r}"] = n, d, ref, amt
    r += 1
first = r          # 10
b[f"B{r}"] = "IPA 10"; b[f"B{r}"].font = Font(bold=True); r += 1          # a month with no fee: heading alone
r += 2             # two spare empty rows kept above the sub-total, as the office's sheet has
b[f"B{r}"] = "Sub - Total from Current Bill"; b[f"D{r}"] = f"=SUM(D{first + 1}:D{r - 1})"
for rr in range(4, r + 1):
    for col in "ABCD":
        b[f"{col}{rr}"].border = box
    b[f"D{rr}"].number_format = "#,##0.00"
wb["APP A"]["D8"], wb["APP A"]["E8"] = 46320, 25000   # bill 8 paid: nothing carried from a Pending bill here
for rr in range(5, first):         # earlier bills' lines kept in the file, not printed
    b.row_dimensions[rr].hidden = True
wb["IPA"]["B8"] = f"='APP B'!D{r}"
wb["IPA"]["B3"] = 10           # this workbook is bill 10: the next one made from it is IPA 11
wb.save(out)
print("saved", out, "sub-total row", r)

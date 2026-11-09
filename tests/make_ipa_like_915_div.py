# A workbook laid out like the 915 / 919 / 914 bills: cover, a landscape Division sheet whose pages each end with
# "TOTAL CARRIED TO COLLECTION" and the next page heading row, only one manual break, a narrow Percentage breakdown.
#   python3 tests/make_ipa_like_915_div.py /tmp/claude-0/bills/div3.xlsx
"""A workbook like 915 / 919's IPA: a cover, APP A, and a landscape Division sheet of 170 rows with the consultant's
page breaks (fit to width, no fit to height), a narrow Percentage breakdown (5 columns)."""
import sys
from openpyxl import Workbook
from openpyxl.styles import Font, Border, Side, Alignment
from openpyxl.worksheet.pagebreak import Break
out = sys.argv[1]
wb = Workbook(); th = Side(style="thin"); box = Border(left=th, right=th, top=th, bottom=th); B = Font(bold=True)
cv = wb.active; cv.title = "IPA"
cv["A1"] = "PAYMENT APPLICATION"; cv["A3"] = "Interim Bill No"; cv["B3"] = 8; cv["A4"] = "Issue Date"; cv["B4"] = "07.11.2026"
cv["A6"] = "Total Value of Work done"; cv["B6"] = "='Division 01-General Requirement'!L170"; cv["A7"] = "Less previous"; cv["B7"] = 1000; cv["A8"] = "Total Amount due for Payment"; cv["B8"] = "=B6-B7"
for r in range(10, 44): cv[f"A{r}"] = ["Signature :", "Prepared by", "Checked by", ""][r % 4]
cv["A44"] = "Approved by"; cv["A45"] = "M/S. Consultant"; cv["A46"] = "Date :"
cv.page_setup.fitToWidth = 1; cv.page_setup.fitToHeight = 0; cv.sheet_properties.pageSetUpPr.fitToPage = True
d = wb.create_sheet("Division 01-General Requirement")
d.page_setup.orientation = "landscape"; d.page_setup.fitToWidth = 1; d.page_setup.fitToHeight = 0; d.sheet_properties.pageSetUpPr.fitToPage = True
d.print_title_rows = "1:5"
d["A1"] = "PROPOSED (G+1) RESIDENTIAL VILLA"; d["A2"] = "PLOT NO. 3474803"; d["A3"] = "PROJECT CODE : AE 5549"; d["L1"] = "consultant"
for col, t in zip("ABCDEFGHIJKLM", ["Ref.No.C", "Ref.No.BO", "WORK DESCRIPTION", "UNIT", "QTY", "RATE (AED)", "AMOUNT (AED)", "Previous %", "Current %", "Total %", "Previous", "Current", "Total"]):
    d[f"{col}5"] = t; d[f"{col}5"].font = B
for c, w in zip("ABCDEFGHIJKLM", [6, 6, 42, 6, 6, 9, 12, 10, 10, 10, 12, 12, 12]):
    d.column_dimensions[c].width = w
d["C6"] = "DIVISION 01 - GENERAL REQUIREMENTS"; d["C6"].font = B
r = 7; n = 0
while r < 168:
    if n % 5 == 0:
        d[f"C{r}"] = f"Heading {n // 5 + 1}"; d[f"C{r}"].font = B; r += 1
    d[f"A{r}"] = n + 1; d[f"C{r}"] = ("The Contractor shall provide sufficient staff and equipment to perform the administrative duties " if n % 3 == 0 else "Line of work ") + str(n + 1)
    d[f"C{r}"].alignment = Alignment(wrap_text=True); d[f"D{r}"] = "Item"; d[f"E{r}"] = 1; d[f"G{r}"] = 1000 + n * 10
    d[f"H{r}"] = 0.5; d[f"I{r}"] = f"=J{r}-H{r}"; d[f"J{r}"] = 0.55; d[f"K{r}"] = f"=G{r}*H{r}"; d[f"L{r}"] = f"=G{r}*I{r}"; d[f"M{r}"] = f"=K{r}+L{r}"
    d.row_dimensions[r].height = 30 if n % 3 == 0 else 15
    r += 1; n += 1
d["C170"] = "TOTAL CARRIED TO COLLECTION"; d["C170"].font = B; d["G170"] = "=SUM(G7:G169)"; d["K170"] = "=SUM(K7:K169)"; d["L170"] = "=SUM(L7:L169)"; d["M170"] = "=SUM(M7:M169)"
for rr in range(5, 171):
    for col in "ABCDEFGHIJKLM": d[f"{col}{rr}"].border = box
for br in (40, 80, 118, 150):  # carried rows
    for col in "ABCDEFGHIJKLM": d[f"{col}{br}"] = None; d[f"{col}{br+1}"] = None
    d[f"C{br}"] = "TOTAL CARRIED TO COLLECTION"; d[f"G{br}"] = f"=SUM(G7:G{br-1})"
    for col, t in zip("ABCDEFGHIJKLM", ["Ref.No.C", "Ref.No.BO", "WORK DESCRIPTION", "UNIT", "QTY", "RATE (AED)", "AMOUNT (AED)", "Previous %", "Current %", "Total %", "Previous", "Current", "Total Work Done"]):
        d[f"{col}{br+1}"] = t
    if br == 40: d.row_breaks.append(Break(id=br))
d.oddFooter.center.text = "Page &P of &N"
pb = wb.create_sheet("Percentage breakdown")
pb["A1"] = "PERCENTAGE BREAKDOWN"; pb["A1"].font = B
for col, t in zip("ABCDE", ["Item", "Description", "Allotted %", "Done %", "Net %"]): pb[f"{col}3"] = t
for i in range(4, 60):
    pb[f"A{i}"] = i - 3; pb[f"B{i}"] = f"Element {i-3}"; pb[f"C{i}"] = 0.1; pb[f"D{i}"] = 0.4; pb[f"E{i}"] = f"=C{i}*D{i}"
    for col in "ABCDE": pb[f"{col}{i}"].border = box
pb.column_dimensions["B"].width = 36
pb.page_setup.fitToWidth = 1; pb.page_setup.fitToHeight = 0; pb.sheet_properties.pageSetUpPr.fitToPage = True; pb.print_area = "A1:E60"
wb.save(out); print("saved", out)

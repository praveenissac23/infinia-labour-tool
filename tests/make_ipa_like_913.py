"""A workbook laid out like 913's IPA: a cover (bill no., date, total due from the Summary), a Summary that copies the
Cost Proposal Log line by line (='Cost Proposal Log'!F7 ...) under its own numbered sections, REVISED CONTRACT VALUE
and work to date as SUMs over them, and the Cost Proposal Log (I COST PROPOSAL - 01 / line, II ... / line, no total).
    python3 tests/make_ipa_like_913.py /tmp/claude-0/bills/913-like.xlsx"""
import sys
from openpyxl import Workbook
from openpyxl.styles import Font, Border, Side
out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/claude-0/bills/913-like.xlsx"
wb = Workbook(); th = Side(style="thin"); box = Border(left=th, right=th, top=th, bottom=th); B = Font(bold=True)
cv = wb.active; cv.title = "IPA"
cv["A1"] = "INTERIM PAYMENT APPLICATION"; cv["A3"] = "Interim Bill No"; cv["B3"] = 10; cv["A4"] = "Issue Date"; cv["B4"] = "07.11.2026"
cv["A6"] = "Work done to date"; cv["B6"] = "=Summary!H12"; cv["A7"] = "Less previous"; cv["B7"] = 100000; cv["A8"] = "Total amount due"; cv["B8"] = "=B6-B7"
cp = wb.create_sheet("Cost Proposal Log")
cp["A3"] = "COST PRPOSAL LOG"
for col, t in zip("ABCDEFGJ", ["SL. NO.", "ITEM DESCRIPTION", "QTY", "UNIT", "UNIT RATE", "AMOUNT IN AED", "Percentage of Work Done", "Total Work Done"]):
    cp[f"{col}4"] = t
for col, t in zip("GHIJKL", ["Previous %", "Current %", "Total %", "Previous", "Current", "Total"]):
    cp[f"{col}5"] = t
items = [(6, "I", "COST PROPOSAL - 01", 7, "Redesign fees", 85000, 1, 1), (8, "II", "COST PROPOSAL - 02", 9, "Soil Re-investigation", 4000, 1, 1),
         (10, "III", "COST PROPOSAL - 03", 11, "Interior design Works", 50000, 0.5, 0.5)]
for hr, rn, hd, lr, desc, amt, pv, tv in items:
    cp[f"A{hr}"], cp[f"B{hr}"] = rn, hd; cp[f"B{hr}"].font = B
    cp[f"A{lr}"], cp[f"B{lr}"], cp[f"C{lr}"], cp[f"D{lr}"], cp[f"E{lr}"], cp[f"F{lr}"] = 1, desc, 1, "Item", "LS", amt
    cp[f"G{lr}"], cp[f"H{lr}"], cp[f"I{lr}"] = pv, f"=I{lr}-G{lr}", tv
    cp[f"J{lr}"], cp[f"K{lr}"], cp[f"L{lr}"] = f"=F{lr}*G{lr}", f"=F{lr}*H{lr}", f"=J{lr}+K{lr}"
for r in range(4, 12):
    for col in "ABCDEFGHIJKL":
        cp[f"{col}{r}"].border = box
sm = wb.create_sheet("Summary")
sm["A2"] = "SUMMARY"
for col, t in zip("ABCDEFGH", ["SL. NO.", "DESCRIPTION", "AMOUNT", "Previous %", "Current %", "Total %", "Previous", "Total"]):
    sm[f"{col}3"] = t
sm["A4"], sm["B4"], sm["C4"], sm["H4"] = "I", "MC SCOPE", 500000, 250000
row = 5
for k, (hr, rn, hd, lr, desc, amt, pv, tv) in enumerate(items):
    sm[f"A{row}"] = ["II", "III", "IV"][k]; sm[f"B{row}"] = f"='Cost Proposal Log'!B{hr}"; sm[f"B{row}"].font = B
    row += 1
    sm[f"A{row}"] = "A"; sm[f"B{row}"] = f"='Cost Proposal Log'!B{lr}"; sm[f"C{row}"] = f"='Cost Proposal Log'!F{lr}"
    sm[f"D{row}"], sm[f"E{row}"], sm[f"F{row}"] = f"='Cost Proposal Log'!G{lr}", f"='Cost Proposal Log'!H{lr}", f"='Cost Proposal Log'!I{lr}"
    sm[f"G{row}"], sm[f"H{row}"] = f"='Cost Proposal Log'!J{lr}", f"='Cost Proposal Log'!L{lr}"
    row += 1
sm["A11"], sm["B11"], sm["C11"] = "V", "VARIATION ORDER - 01", 20000
sm["B12"], sm["C12"], sm["H12"] = "REVISED CONTRACT VALUE", "=SUM(C4:C11)", "=SUM(H4:H11)"
for r in range(3, 13):
    for col in "ABCDEFGH":
        sm[f"{col}{r}"].border = box
wb.save(out)

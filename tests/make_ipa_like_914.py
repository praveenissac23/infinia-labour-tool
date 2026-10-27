"""A workbook laid out like 914's real IPA (the consultant's format): a cover with the bill no., date and total due,
a summary that collects each sheet's total, APP C (approved variations: Total % = Previous + Current, spare V02-V05
lines, a Sub-Total) and a Division sheet (Ref / description / unit / QTY x RATE = AMOUNT, Previous / Current / Total %,
a heading row, a spec paragraph, TOTAL CARRIED TO COLLECTION over the rows including blanks).
    python3 tests/make_ipa_like_914.py /tmp/claude-0/bills/914-like.xlsx"""
import sys
from openpyxl import Workbook
from openpyxl.styles import Font, Border, Side

out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/claude-0/bills/914-like.xlsx"
wb = Workbook()
thin = Side(style="thin"); box = Border(left=thin, right=thin, top=thin, bottom=thin)
B = Font(bold=True)

cv = wb.active; cv.title = "IPA"
cv["A1"] = "INTERIM PAYMENT APPLICATION"; cv["A1"].font = B
cv["A3"] = "Bill No."; cv["B3"] = 7
cv["A4"] = "Date"; cv["B4"] = "15.09.2026"
cv["A6"] = "Work done to date"; cv["B6"] = "=Summary!C6"
cv["A7"] = "Less previous"; cv["B7"] = 1000000
cv["A8"] = "Total amount due"; cv["B8"] = "=B6-B7"

sm = wb.create_sheet("Summary")
sm["A1"] = "SUMMARY"; sm["A1"].font = B
sm["A3"], sm["B3"], sm["C3"] = "Ref", "Section", "To date"
sm["A4"], sm["B4"], sm["C4"] = "C", "Approved variations", "='APP C'!I11"
sm["A5"], sm["B5"], sm["C5"] = "03", "Concrete", "='Division 03-Concrete Works'!M20"
sm["B6"], sm["C6"] = "Total", "=SUM(C4:C5)"

c = wb.create_sheet("APP C")
c["A1"] = "APPENDIX - C"; c["A2"] = "APPROVED VARIATIONS"
for col, t in zip("ABCDGHI", ["Ref.No", "Description", "Total Amount", "Percentage of Work Done", "Total Work Done", "", ""]):
    if t: c[f"{col}3"] = t
for col, t in zip("DEFGHI", ["Previous %", "Current %", "Total %", "Previous", "Current", "Total"]):
    c[f"{col}4"] = t
c["A5"], c["B5"], c["C5"], c["D5"], c["E5"], c["F5"] = "V01", "Design Revision for Lift Pit", "=52826.96/2", 1, "=F5-D5", 1
c["G5"], c["H5"], c["I5"] = "=D5*C5", "=E5*C5", "=C5*F5"
for r in range(6, 10):
    c[f"A{r}"] = f"V0{r - 4}"; c[f"D{r}"] = 0; c[f"E{r}"] = 0; c[f"F{r}"] = f"=SUM(D{r}:E{r})"
    c[f"G{r}"], c[f"H{r}"], c[f"I{r}"] = f"=D{r}*C{r}", f"=E{r}*C{r}", f"=C{r}*F{r}"
c["C10"], c["D10"], c["E10"], c["F10"], c["G10"], c["H10"], c["I10"] = "=0", 0, "=F10-D10", 0, "=C10*D10", 0, "=C10*F10"
c["B11"] = "Sub - Total"
c["C11"], c["D11"], c["E11"], c["F11"] = "=SUM(C5:C10)", "=G11/C11", "=H11/C11", "=I11/$C$11"
c["G11"], c["H11"], c["I11"] = "=SUM(G5:G10)", "=SUM(H5:H10)", "=SUM(I5:I10)"
for r in range(3, 12):
    for col in "ABCDEFGHI":
        c[f"{col}{r}"].border = box

d = wb.create_sheet("Division 03-Concrete Works")
for col, t in zip("ABCDEFGHK", ["Ref.No.CSI", "Ref.No.BOQ", "WORK DESCRIPTION", "UNIT", "QTY", "RATE (AED)", "AMOUNT (AED)", "Percentage of Work Done", "Total Work Done"]):
    d[f"{col}4"] = t
for col, t in zip("HIJKLM", ["Previous\n%", "Current\n%", "Total\n%", "Previous", "Current", "Total"]):
    d[f"{col}5"] = t
d["B7"], d["C7"] = "3.1.1", "Concrete (PCC/Blinding C20)"; d["C7"].font = B
d["C8"] = "Execution of all works beneath the foundations of the villa as per drawings and specification."
rows = [(9, "3.1.1.1", "for villa", "M3", 18.97, 492, 1, 1), (10, "3.1.1.2", "Boundary wall", "M3", 3.17, "=+F9", 0.9, 0.9),
        (12, "3.2.2.1", "Villa Parapet & capping Beam", "M3", 9, 2428, 0, 0)]
d["B11"], d["C11"] = "3.2.2", "Superstructure"; d["C11"].font = B
for r, ref, desc, u, q, rate, pv, tv in rows:
    d[f"B{r}"], d[f"C{r}"], d[f"D{r}"], d[f"E{r}"], d[f"F{r}"] = ref, desc, u, q, rate
    d[f"G{r}"] = f"=+F{r}*E{r}"; d[f"H{r}"] = pv; d[f"I{r}"] = f"=J{r}-H{r}"; d[f"J{r}"] = tv
    d[f"K{r}"], d[f"L{r}"], d[f"M{r}"] = f"=H{r}*G{r}", f"=I{r}*G{r}", f"=J{r}*G{r}"
    d[f"N{r}"] = "=30.02+0.745"                       # a side note outside the table
d["C20"], d["E20"] = "TOTAL CARRIED TO COLLECTION", "DIV03/4"
d["G20"], d["K20"], d["L20"], d["M20"] = "=SUM(G9:G19)", "=SUM(K9:K19)", "=SUM(L9:L19)", "=SUM(M9:M19)"
d["H20"], d["J20"] = "=K20/G20", "=M20/G20"
for r in range(4, 21):
    for col in "ABCDEFGHIJKLM":
        d[f"{col}{r}"].border = box
# Division 02 laid out exactly as 914's: the title and column headings repeated on every printed page (the title
# as =$C$6&" (CONT'D)"), items priced "Included" (no %), specification paragraphs, a total per page and a collection.
e = wb.create_sheet("Division 02-Site Construction")
def hdr(r):
    for col, t in zip("ABCDEFGHK", ["Ref.No.CSI", "Ref.No.BOQ", "WORK DESCRIPTION", "UNIT", "QTY", "RATE (AED)", "AMOUNT (AED)", "Percentage of Work Done", "Total Work Done"]):
        e[f"{col}{r}"] = t
    for col, t in zip("HIJKLM", ["Previous %", "Current %", "Total %", "Previous", "Current", "Total"]):
        e[f"{col}{r + 1}"] = t
e["A1"] = "PROPOSED (G+1) RESIDENTIAL VILLA PLOT NO"; e["A2"] = "PROJECT CODE : AE 5548"; e["A3"] = "CLIENT: Supreme Holdings Limited"
hdr(4); e["C6"] = "DIVISION 02 - SITE CONSTRUCTION"; e["C6"].font = B
e["C16"] = "Excavation"; e["C16"].font = B
e["A17"], e["B17"], e["C17"] = 2150, 3, "Excavation in all types of soil, sand, rock and the like, to the levels and dimensions shown on the drawings, including all dewatering and shoring as required."
for r, it, d_ in [(22, "3.1", "Main Villa"), (23, "3.2", "Boundary wall"), (24, "3.3", "Underground water tank")]:
    e[f"B{r}"], e[f"C{r}"], e[f"D{r}"], e[f"E{r}"], e[f"F{r}"], e[f"G{r}"] = it, d_, "M3", 80, 50, "Included"
e["C26"], e["E26"], e["G26"] = "TOTAL CARRIED TO COLLECTION", "DIV02/1", "=SUM(G6:G25)"
hdr(27); e["C29"] = '=$C$6&" (CONT\'D)"'
e["C31"] = "Back Fill (with excavated soil)"; e["C31"].font = B
e["A32"], e["B32"], e["C32"] = "31.23.16", 4, "Supply, placement, compaction, and finishing of approved back fill material from excavated soil in layers not exceeding 250 mm."
for r, it, d_, q, rate, pv in [(33, "4.1", "Main Villa", 1050.6, 46, 1), (34, "4.2", "Boundary wall", 56.41, "=46-9", 0.9), (35, "4.3", "Underground water tank", 73.6, 46, 0)]:
    e[f"B{r}"], e[f"C{r}"], e[f"D{r}"], e[f"E{r}"], e[f"F{r}"] = it, d_, "M3", q, rate
    e[f"G{r}"] = f"=+F{r}*E{r}"; e[f"H{r}"] = pv; e[f"I{r}"] = f"=J{r}-H{r}"; e[f"J{r}"] = pv
    e[f"K{r}"], e[f"L{r}"], e[f"M{r}"] = f"=H{r}*G{r}", f"=I{r}*G{r}", f"=J{r}*G{r}"
e["C36"] = " Road Base"; e["C36"].font = B
e["A37"], e["B37"], e["C37"] = "31.23.16", 5, "Supply, placement, and compaction of approved road base material under slabs on grade, 150 mm thick."
for r, it, d_ in [(38, "5.1", "Main Villa"), (39, "5.2", "Underground water tank")]:
    e[f"B{r}"], e[f"C{r}"], e[f"D{r}"], e[f"E{r}"], e[f"G{r}"] = it, d_, "M3", 10, "Included"
e["C46"], e["E46"], e["G46"], e["K46"], e["M46"] = "TOTAL CARRIED TO COLLECTION", "DIV02/2", "=SUM(G29:G45)", "=SUM(K29:K45)", "=SUM(M29:M45)"
hdr(47); e["C49"] = '=$C$6&" (CONT\'D)"'
e["B52"], e["C52"] = 6, "Anti-termite treatment"; e["C52"].font = B
e["C53"] = "Provision of anti-termite treatment for all areas below ground floor slab, including a 10 year guarantee."
for r, it, d_, q, pv in [(59, "6.1", "Main Villa (under footing & SOG & Interlock)", "=95.33+322+192", 1), (60, "6.2", "Boundary wall (under footing)", 80.39, 0.9), (61, "6.3", "Underground water tank (under footing)", 26.6, 0)]:
    e[f"B{r}"], e[f"C{r}"], e[f"D{r}"], e[f"E{r}"], e[f"F{r}"] = it, d_, "M2", q, 10 if r == 59 else "=F59"
    e[f"G{r}"] = f"=+F{r}*E{r}"; e[f"H{r}"] = pv; e[f"I{r}"] = f"=J{r}-H{r}"; e[f"J{r}"] = pv
    e[f"K{r}"], e[f"L{r}"], e[f"M{r}"] = f"=H{r}*G{r}", f"=I{r}*G{r}", f"=J{r}*G{r}"
e["C63"], e["D63"] = "Immediately prior to handing over the works, general cleaning of the site.", "Item"
e["C77"], e["E77"], e["G77"], e["K77"], e["M77"] = "TOTAL CARRIED TO COLLECTION", "DIV02/3", "=SUM(G49:G76)", "=SUM(K49:K76)", "=SUM(M49:M76)"
hdr(78); e["C80"] = '=$C$6&" (CONT\'D)"'
e["C83"] = "Any Other Items"; e["C85"], e["G85"] = "The Contractor will list here and price any other items.", "N/A"
e["C123"] = '=$C$6&" (CONT\'D)"'; e["C125"] = "COLLECTION"
e["C127"], e["G127"], e["M127"] = "From Page DIV 02/ 1", "=+G26", 0
e["C129"], e["G129"], e["M129"] = "From Page DIV 02/ 2", "=+G46", "=+M46"
e["C131"], e["G131"], e["M131"] = "From Page DIV 02/ 3", "=+G77", "=+M77"
e["C171"], e["E171"], e["G171"], e["M171"] = "TOTAL CARRIED TO GENERAL SUMMARY", "DIV02/5", "=SUM(G123:G170)", "=SUM(M123:M170)"
sm["A6"], sm["B6"], sm["C6"] = "02", "Site construction", "='Division 02-Site Construction'!M171"
sm["B7"], sm["C7"] = "Total", "=SUM(C4:C6)"
cv["B6"] = "=Summary!C7"
wb.save(out)
print(out)

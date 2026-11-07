"""Sheets step: every cell of a Remarks column can be typed in (items, headings, blank rows) - plain text, never a
total; kept for the next bill unless "Clear remarks for next bill" was ticked.   cd app && python3 ../tests/bill_remarks_test.py"""
import io, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
from openpyxl import Workbook
from openpyxl.styles import Border, Side
import est_bills_engine as BE, est_bills_render as BR
bad = 0
def ck(n, ok, i=""):
    global bad
    bad += not ok; print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  " + str(i)[:300]))
wb = Workbook(); ws = wb.active; ws.title = "Summary"
th = Side(style="thin"); bd = Border(left=th, right=th, top=th, bottom=th)
for i, h in enumerate(["SL. NO.", "DESCRIPTION", "AMOUNT", "Remarks"], 1):
    ws.cell(2, i, h).border = bd
rows = [("I", "CIVIL WORKS", None, None), ("A", "SITE WORKS", 287497, "Backfilling done"), ("B", "RCC", 1867584, None), (None, None, None, None), ("", "TOTAL Carried to Summary", "=SUM(C4:C6)", None)]
for r, row in enumerate(rows, 3):
    for c, v in enumerate(row, 1):
        x = ws.cell(r, c, v); x.border = bd
ws.cell(10, 2, "Checked by:"); ws.cell(10, 4).border = bd; ws.cell(11, 4).border = bd
buf = io.BytesIO(); wb.save(buf); data = buf.getvalue()
m = BE.read_format(data, "s.xlsx"); s = m["sheets"][0]
rc = BE.remarks_cols(s, m["styles"])
ck("Remarks column found: rows 3-7 (heading, items, blank row, total) - not the signature block", rc == {4: (3, 7)}, rc)
v = BE.calculate(m, {})
h, _, _ = BR.sheet_html(m, s, v, {}, edit=True)
import re
eds = re.findall(r'<td[^>]*data-k="(\d+),4"[^>]*class="([^"]*)"', h)
ck("every Remarks cell 3-7 can be typed in and is marked rm", sorted(int(k) for k, c in eds if "rm" in c) == [3, 4, 5, 6, 7], eds)
ck("signature rows are not Remarks", not re.search(r'data-k="1[01],4"[^>]*class="[^"]*rm', h))
inp = {"Summary": {"6,4": "Blank row note\nline two"}}
v2 = BE.calculate(m, inp)
ck("a remark never changes the total", v2["Summary"]["7,3"] == v["Summary"]["7,3"], (v2["Summary"].get("7,3"), v["Summary"].get("7,3")))
nxt = BE.roll_over(m, inp, v2)
ck("kept for the next bill by default", nxt["Summary"].get("6,4") == "Blank row note\nline two" and "4,4" not in nxt["Summary"])
inp2 = dict(inp, _opts={"clear_remarks": True})
nxt2 = BE.roll_over(m, inp2, v2)
ck("Clear remarks for next bill: typed and the consultant's remarks start empty", nxt2["Summary"].get("6,4") == "" and nxt2["Summary"].get("4,4") == "", nxt2.get("Summary"))
ck("... and the choice itself does not carry on", "_opts" not in nxt2)
pdf = BR.render_pdf(BE.apply_fmt(m, inp), v2, "t", inp)
pdf = pdf.getvalue() if hasattr(pdf, "getvalue") else pdf
import pdfplumber
t = pdfplumber.open(io.BytesIO(pdf)).pages[0].extract_text()
ck("PDF prints the remark on two lines", "note" in t and "line two" in t, t)
print("ALL PASS" if not bad else f"{bad} FAILED")

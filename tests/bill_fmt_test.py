"""Sheets step toolbar: the office's own size / bold / italic / underline and "Match row above" on a bill - drawn on
screen and in the PDF from the model, written into the Excel file, carried when rows are put in or taken out, and
never changing the wording, figures or number formats.   cd app && python3 ../tests/bill_fmt_test.py"""
import io, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Border, Side, Alignment
import est_bills_engine as BE, est_bills_render as BR
bad = 0
def ck(n, ok, i=""):
    global bad
    bad += not ok; print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  " + str(i)[:300]))
wb = Workbook(); ws = wb.active; ws.title = "Breakdown"
th = Side(style="thin"); bd = Border(left=th, right=th, top=th, bottom=th)
ws["B2"] = "7"; ws["C2"] = "MASONRY WORKS"
for c in ("B2", "C2"):
    ws[c].font = Font(name="Arial", size=9.5, bold=True); ws[c].border = bd
ws["B3"] = "A."; ws["C3"] = "Total % alloted"; ws["D3"] = 0.45
ws["B4"] = "B."; ws["C4"] = "Milestone as per Contract"; ws["D4"] = 990000
for r in (3, 4):
    for c in "BCD":
        ws[f"{c}{r}"].font = Font(name="Arial", size=9.5); ws[f"{c}{r}"].border = bd; ws[f"{c}{r}"].alignment = Alignment(horizontal="left")
ws["D3"].number_format = "0%"; ws["D4"].number_format = "#,##0.00"
ws["D4"].font = Font(name="Arial", size=14, bold=True)
buf = io.BytesIO(); wb.save(buf); data = buf.getvalue()
model = BE.read_format(data, "t.xlsx"); sh = "Breakdown"
st = lambda m, k: m["styles"][next(x for x in m["sheets"] if x["name"] == sh)["cells"][k]["s"]]
inputs = {sh: {"_fmt": {"3,3": {"sz": 12, "b": True}, "3,2": {"i": True, "u": True}, "4,4": {"s": next(x for x in model["sheets"] if x["name"] == sh)["cells"]["3,4"]["s"]}},
               "_rowh": {"3": 30}}}
m2 = BE.apply_fmt(model, inputs)
ck("size + bold on C3", st(m2, "3,3")["sz"] == 12 and st(m2, "3,3")["b"] is True, st(m2, "3,3"))
ck("italic + underline on B3", st(m2, "3,2")["i"] is True and st(m2, "3,2")["u"], st(m2, "3,2"))
ck("Match row above on D4: size / bold of D3 ...", st(m2, "4,4")["sz"] == 9.5 and not st(m2, "4,4")["b"], st(m2, "4,4"))
ck("... but D4 keeps its own number format (990,000.00)", st(m2, "4,4")["nf"] == st(model, "4,4")["nf"], (st(m2, "4,4")["nf"], st(model, "4,4")["nf"]))
ck("row height", next(x for x in m2["sheets"] if x["name"] == sh)["rowh"]["3"] == 30)
ck("the format itself untouched", st(model, "3,3")["sz"] == 9.5 and not st(model, "3,3")["b"] and model["styles"] is not m2["styles"])
ck("nothing set: same model back", BE.apply_fmt(model, {sh: {"D3": 1}}) is model)
values = BE.calculate(m2, inputs)
html, _w, _h = BR.sheet_html(m2, next(x for x in m2["sheets"] if x["name"] == sh), values, inputs, edit=True)
import re
td = re.search(r'<td[^>]*data-c="3"[^>]*style="([^"]*)"[^>]*>Total % alloted', html) or re.search(r'<td[^>]*style="([^"]*)"[^>]*>Total % alloted', html)
ck("sheet step draws C3 at 12pt bold", td and "font-size:12pt" in td.group(1) and re.search(r"font-weight:\s*700", td.group(1)), td and td.group(1))
ck("cells carry data-c for the toolbar", 'data-c="3"' in html)
x = BE.write_xlsx(data, m2, inputs, values)
a = load_workbook(io.BytesIO(x))[sh]
ck("Excel: C3 12 pt bold", a["C3"].font.sz == 12 and a["C3"].font.b, (a["C3"].font.sz, a["C3"].font.b))
ck("Excel: B3 italic underline", a["B3"].font.i and a["B3"].font.u, (a["B3"].font.i, a["B3"].font.u))
ck("Excel: D4 like D3 (9.5, not bold) with its own #,##0.00", a["D4"].font.sz == 9.5 and not a["D4"].font.b and a["D4"].number_format == "#,##0.00", (a["D4"].font.sz, a["D4"].font.b, a["D4"].number_format))
ck("Excel: row 3 height 30", a.row_dimensions[3].height == 30, a.row_dimensions[3].height)
ck("Excel: text and figures as typed", a["C3"].value == "Total % alloted" and a["D4"].value == 990000 and a["D3"].number_format == "0%")
ck("Excel: untouched cells keep their look", a["C2"].font.b and a["C2"].font.sz == 9.5)
# rows put in above / taken out: the formatting moves with its rows
sft = BE.shift_inputs(inputs[sh], sh, 3, 2)
ck("2 rows put in above row 3: formatting moves to 5 / 6", set(sft["_fmt"]) == {"5,3", "5,2", "6,4"} and sft["_rowh"] == {"5": 30}, (sft.get("_fmt"), sft.get("_rowh")))
ins = {sh: dict(inputs[sh], _rows=[[3, 1, [3]]])}
ins[sh] = BE.shift_inputs(inputs[sh], sh, 3, 1); ins[sh]["_rows"] = [[3, 1, [3], {"kind": "line"}]]
back = BE.drop_added(ins, sh, 3)
ck("the added row taken out again: formatting back on 3 / 4", back and set(back[sh]["_fmt"]) == {"3,3", "3,2", "4,4"}, back and back[sh].get("_fmt"))
# ---- number formats and decimal alignment (7 / 8)
ACC = '_("AED "* #,##0.00_);_("AED "* (#,##0.00);_("AED "* "-"??_);_(@_)'
ck("General 1318577.14", BR.fmt(1318577.14, "General") == "1318577.14")
ck("Number 1,318,577.14", BR.fmt(1318577.14, "#,##0.00") == "1,318,577.14")
ck("Number 0 dp 1,318,577", BR.fmt(1318577.14, "#,##0") == "1,318,577")
ck("Percentage 45% / 45.00%", BR.fmt(0.45, "0%") == "45%" and BR.fmt(0.45, "0.00%") == "45.00%")
lead, t, red = BR.num_look(1318577.14, ACC)
ck("Accounting: AED at the left, figure apart", lead == "AED" and t.strip() == "1,318,577.14", (lead, t))
lead, t, red = BR.num_look(-1234.56, "#,##0.00;[Red](#,##0.00)")
ck("Negative in ( ) and red", t == "(1,234.56)" and red, (t, red))
ck("145841.9 shows 145,841.90", BR.fmt(145841.9, "#,##0.00") == "145,841.90")
ck("decimal padding: 8,250.5 under 2 decimals gets one blank place", BR.dec_pad("8,250.5", 2) == "0" and BR.dec_pad("45%", 2) == ".00" and BR.dec_pad("1.25", 2) == "")
wb2 = Workbook(); w = wb2.active; w.title = "Pay"
for i, v in enumerate([124936.19, 1318577.14, 8250.5, -1234.56], 2):
    w.cell(i, 2, v)
w["A1"] = "Amounts"
buf2 = io.BytesIO(); wb2.save(buf2); d2 = buf2.getvalue()
m0 = BE.read_format(d2, "p.xlsx")
inp2 = {"Pay": {"_fmt": {"2,2": {"nf": "#,##0.00", "ha": "dec"}, "3,2": {"nf": ACC}, "4,2": {"nf": "#,##0.0", "ha": "dec"}, "5,2": {"nf": "#,##0.00;[Red](#,##0.00)"}}}}
m3 = BE.apply_fmt(m0, inp2); v3 = BE.calculate(m3, inp2)
h3, _, _ = BR.sheet_html(m3, m3["sheets"][0], v3, inp2, edit=True)
ck("screen: 124,936.19 decimal-aligned (tabular figures)", re.search(r'tabular-nums[^"]*"[^>]*>124,936\.19', h3) is not None, h3[:200])
ck("screen: 8,250.5 padded with a hidden 0 after it", re.search(r'>8,250\.5<span class="dp" style="visibility:hidden">0</span>', h3) is not None)
ck("screen: accounting AED left / figure right", 'class="acc"' in h3 and ">AED<" in h3)
ck("screen: negative red in brackets", "color:#C00000" in h3 and "(1,234.56)" in h3)
x3 = BE.write_xlsx(d2, m3, inp2, v3)
a3 = load_workbook(io.BytesIO(x3))["Pay"]
ck("Excel: real number formats", a3["B2"].number_format == "#,##0.00" and a3["B3"].number_format == ACC and a3["B5"].number_format == "#,##0.00;[Red](#,##0.00)",
   (a3["B2"].number_format, a3["B3"].number_format, a3["B5"].number_format))
ck("Excel: values stay numbers, full figure kept", a3["B2"].value == 124936.19 and a3["B4"].value == 8250.5 and isinstance(a3["B3"].value, float))
ck("Excel: decimal-aligned = right", a3["B2"].alignment.horizontal == "right" and a3["B4"].alignment.horizontal == "right")
pdf = BR.render_pdf(m3, v3, "t", inp2)
pdf = pdf.getvalue() if hasattr(pdf, "getvalue") else pdf
ck("PDF builds with the formats", len(pdf) > 500)
try:
    import pdfplumber
    txt = pdfplumber.open(io.BytesIO(pdf)).pages[0].extract_text()
    ck("PDF: 1,318,577.14 with AED, (1,234.56)", "1,318,577.14" in txt and "AED" in txt and "(1,234.56)" in txt and "124,936.19" in txt, txt)
except ImportError:
    pass
print("ALL PASS" if not bad else f"{bad} FAILED")

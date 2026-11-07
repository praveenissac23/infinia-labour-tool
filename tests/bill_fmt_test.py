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
print("ALL PASS" if not bad else f"{bad} FAILED")

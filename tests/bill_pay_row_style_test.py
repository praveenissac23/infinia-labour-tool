"""Previous payments: a bill line filled in a spare row of the workbook (styled 18 pt where the bill lines are 16 pt)
is drawn like the first bill line - on screen, in the PDF and in the Excel file (914 APP A, 7 Nov 2026).
  cd app && python3 ../tests/bill_pay_row_style_test.py"""
import io, os, sys, re, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Border, Side, Alignment
import est_bills_engine as BE, est_bills_render as BR
bad = 0
def ck(n, ok, i=""):
    global bad
    bad += not ok; print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  " + str(i)[:300]))
wb = Workbook(); ws = wb.active; ws.title = "APP A-Payment summary"
th = Side(style="thin"); bd = Border(left=th, right=th, top=th, bottom=th)
ws["A1"] = "Project X"; ws["E2"] = "Bill 3"; ws["E2"].font = Font(size=12)
hd = ["No", "Payment Certificate No", "Date of IPA Submission", "Date of Certification", "Amount (AED)"]
for i, h in enumerate(hd, 1):
    c = ws.cell(3, i, h); c.font = Font(name="Arial Narrow", size=16, bold=True); c.border = bd
for r in range(4, 14):
    for c in range(1, 6):
        x = ws.cell(r, c); x.border = bd
        x.font = Font(name="Arial Narrow", size=16 if r < 6 else 18)
        x.alignment = Alignment(horizontal="center")
    ws.row_dimensions[r].height = 25 if r < 6 else 31
for r, n in ((4, 1), (5, 2)):
    ws.cell(r, 1, n); ws.cell(r, 2, f"Payment Application No {n}"); ws.cell(r, 3, 46100 + r); ws.cell(r, 5, 1000 * n)
ws.cell(14, 1, "Total Previous Payments Received Carried to Summary"); ws.cell(14, 5, "=SUM(E4:E13)")
ws.cell(14, 1).font = Font(size=20, bold=True)
buf = io.BytesIO(); wb.save(buf); data = buf.getvalue()
model = BE.read_format(data, "t.xlsx")
mp = model["map"]
ck("payments table found", bool(mp.get("payments")), mp.get("payments"))
p = mp["payments"][0]; sh = p["sheet"]
inputs = {sh: {f"6,{p['cols']['desc']}": "Payment Application No 3", f"6,{p['cols']['amount']}": 2500}}
pairs = BE.pay_rows_like(model, inputs)
ck("the filled spare row (6) is to be drawn like the first bill line (4)", pairs.get(sh) == {6: 4}, pairs)
m2 = BE.restyle_pay_rows(model, inputs)
s2 = next(x for x in m2["sheets"] if x["name"] == sh); s0 = next(x for x in model["sheets"] if x["name"] == sh)
st = m2["styles"]
ck("row 6 now 16 pt like row 4, every column", all(st[s2["cells"][f"6,{c}"]["s"]]["sz"] == st[s2["cells"][f"4,{c}"]["s"]]["sz"] == 16 for c in range(1, 6)),
   [st[s2["cells"][f"6,{c}"]["s"]]["sz"] for c in range(1, 6)])
ck("row 6 height like row 4", s2["rowh"].get("6") == s0["rowh"].get("4"), (s2["rowh"].get("6"), s0["rowh"].get("4")))
ck("empty spare rows, header and total untouched", all(s2["cells"].get(f"{r},2") == s0["cells"].get(f"{r},2") and s2["cells"].get(f"{r},1") == s0["cells"].get(f"{r},1") for r in (3, 7, 12, 14)))
ck("the format itself is not changed", st is model["styles"] and s0["cells"]["6,2"]["s"] != s0["cells"]["4,2"]["s"])
ck("nothing to do - same model back", BE.restyle_pay_rows(model, {}) is model)
values = BE.calculate(m2, inputs)
html = BR.preview_html(m2, values, "t", "", "", inputs)
sh_html, _w, _h = BR.sheet_html(m2, s2, values, inputs, edit=True, mark={f"6,{c}": "tot" for c in range(1, 6)})
def font(txt, h):
    m = re.search(r'<td[^>]*style="([^"]*)"[^>]*>(?:<div[^>]*>)?(?:<span>)?' + re.escape(txt), h)
    if not m:
        return None
    return sorted(x.strip() for x in m.group(1).split(";") if re.match(r"\s*(font|text-align|color|height)", x))
a3, a2 = font("Payment Application No 3", sh_html), font("Payment Application No 2", sh_html)
ck("sheet step (yellow = changed): new line same font as line 2", a3 is not None and a3 == a2, (a3, a2))
b3, b2 = font("Payment Application No 3", html), font("Payment Application No 2", html)
ck("preview: new line same font as line 2", b3 is not None and b3 == b2, (b3, b2))
x = BE.write_xlsx(data, m2, inputs, values)
w2 = load_workbook(io.BytesIO(x)); a = w2[sh]
ck("Excel: row 6 font 16 like row 4", [a.cell(6, c).font.sz for c in range(1, 6)] == [a.cell(4, c).font.sz for c in range(1, 6)], [a.cell(6, c).font.sz for c in range(1, 6)])
ck("Excel: row 6 height like row 4", a.row_dimensions[6].height == a.row_dimensions[4].height, (a.row_dimensions[6].height, a.row_dimensions[4].height))
ck("Excel: typed text and amount kept", a.cell(6, 2).value == "Payment Application No 3" and a.cell(6, 5).value == 2500, (a.cell(6, 2).value, a.cell(6, 5).value))
ck("Excel: empty spare row still 18 pt", a.cell(8, 2).font.sz == 18)
print("ALL PASS" if not bad else f"{bad} FAILED")

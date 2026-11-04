"""The printed bill (preview and PDF) keeps the consultant's content exactly and fixes only the layout (4 Nov 2026):
a row too short for its wrapped description is made taller (never shrunk or cut), the pages are broken with those
heights so nothing runs into the page-number footer, and every sheet is centred - equal margins left and right.
    cd app && python3 ../tests/bill_print_fit_test.py
"""
import io, os, re, subprocess, sys, tempfile
sys.path.insert(0, os.getcwd())
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Side
import est_bills_engine as BE
import est_bills_render as BR
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:300]}"))
    if not ok: fails.append(n)
DESC = ["Provision for Surveying Equipment & Site Survey", "Supply, installation and maintenance of Corrugated fencing all around the plot",
        "Provision of scaffolding, tools and services required for the proper execution of the works",
        "Providing site office, toilets and other requirements as per the client requirements", "Project Engineer",
        "Liasing & Coordinating all the works for subcontractors and nominated sub-contractors"] * 4


def book(short, filler=6):
    """short=True: the consultant's rows are a single line high for two- and three-line descriptions."""
    thin = Side(style="thin"); B = Border(left=thin, right=thin, top=thin, bottom=thin)
    wb = Workbook(); ws = wb.active; ws.title = "IPA"
    for k, v in {"A": 6, "B": 36, "C": 7, "D": 13, "E": 13}.items():
        ws.column_dimensions[k].width = v
    for i, h in enumerate(["SN", "DESCRIPTION", "UNIT", "AMOUNT", "TOTAL"], 1):
        ws.cell(row=1, column=i, value=h)
    for i in range(filler):
        ws.cell(row=2 + i, column=2, value=f"filler {i}")
    r0 = 2 + filler
    for i, d in enumerate(DESC):
        r = r0 + i
        ws.cell(row=r, column=1, value=str(55 + i))
        c = ws.cell(row=r, column=2, value=d); c.alignment = Alignment(wrap_text=True, vertical="center")
        n = 1 if len(d) < 38 else (2 if len(d) < 76 else 3)
        ws.row_dimensions[r].height = 15 if short else {1: 15, 2: 28.5, 3: 42}[n]
        for col in range(1, 6):
            ws.cell(row=r, column=col).border = B
    last = r0 + len(DESC) - 1
    for col, v in ((3, "LS"), (4, 283200), (5, 212400)):
        ws.merge_cells(start_row=r0, start_column=col, end_row=last, end_column=col)
        ws.cell(row=r0, column=col, value=v)
    ws.cell(row=last + 1, column=2, value="TOTAL FOR PRELIMINARIES")
    ws.page_setup.orientation = "landscape"; ws.page_setup.paperSize = 9
    ws.page_margins.left, ws.page_margins.right = 0.25, 1.2          # lopsided margins in the format
    ws.oddFooter.center.text = "&P of &N"
    ws.print_title_rows = "1:1"
    f = io.BytesIO(); wb.save(f); return f.getvalue()


def plan(data):
    m = BE.read_format(data, "t.xlsx"); model = m[0] if isinstance(m, tuple) else m
    v = BE.calculate(model)
    sh = BR.printed_sheets(model)[0]
    return model, v, sh, BR.page_plan(model, sh, None, v)


model, v, sh, pl = plan(book(False))
ck("rows the consultant made high enough are left as they are", not pl["grow"], pl["grow"])
model, v, sh, pl = plan(book(True))
ck("rows too short for their wrapped description are made taller", len(pl["grow"]) >= 8, pl["grow"])
ah = pl["ph"] - pl["mt"] - pl["mb"]
worst = max(sum(pl["rh"][r] for r in prow) * 0.75 * pl["sc"] for prow, own in pl["pages"])
ck(f"every page's rows fit above the footer ({worst:.0f} of {ah:.0f} pt)", worst <= ah + 0.6, worst)
right = pl["pw"] - pl["x0"] - sum(pl["cw"][c] for c in pl["cols"]) * 0.75 * pl["sc"]
ck(f"the sheet is centred: left margin {pl['x0']:.1f} = right margin {right:.1f}", abs(pl["x0"] - right) < 0.5, (pl["x0"], right))
html = BR.preview_html(model, v, "t", "#", "#", fname="t.xlsx")
ck("the preview uses the taller rows", all(f'height:{h}px' in html for h in set(pl["grow"].values())))
pages = html.split('<section class="pg ')[1:]
ck(f"a merged Unit/Amount/Total block carried onto the next page keeps its columns there ({len(pages)} pages)",
   len(pages) > 1 and all("rowspan=" in g for g in pages[:2]), [g.count("rowspan=") for g in pages])
pdf = BR.render_pdf(model, v, "t")
f = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False); f.write(pdf.getvalue() if hasattr(pdf, "getvalue") else pdf); f.close()
txt = re.sub(r"\s+", " ", subprocess.run(["pdftotext", f.name, "-"], capture_output=True, text=True).stdout)
ck("every description is printed whole, word for word", all(d in txt for d in set(DESC)), [d for d in set(DESC) if d not in txt])
print("ALL PASS" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)

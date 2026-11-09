"""The bill as an Excel file - built from the same bill the PDF is drawn from (9 Nov 2026).

The old Excel export patched the uploaded workbook and let Excel work every formula out again on opening; where the
workbook and the bill had drifted apart (lines added here, cells the office typed over, links to sheets that are not
printed) Excel came back with other figures than the PDF (913 IPA 10: total due -211,722 in Excel, 490,816 on the
PDF) and Excel sometimes had to "repair" the file.

Now each printed sheet of the PDF is written as a worksheet of its own, in the same order, from the same cells,
figures, styles, merged cells, row heights, pictures and signatures, with the same page set-up. Every formula is a
real Excel formula with the bill's own figure saved beside it, and the file tells Excel the figures are already
worked out - so it opens showing exactly the PDF's figures. A formula that would point at something not in the file
(a sheet that is not printed, another workbook, a named range) is written as its figure instead."""
import io
import re
import zipfile

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.drawing.spreadsheet_drawing import OneCellAnchor, AnchorMarker
from openpyxl.drawing.xdr import XDRPositiveSize2D
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

import est_bills_engine as BE
import est_bills_render as BR

EMU = 9525                       # EMU per pixel
_BAD_NAME = re.compile(r"[\[\]:*?/\\]")
_SHEET_REF = re.compile(r"'((?:[^']|'')+)'!|([A-Za-z_À-￿][\w.À-￿]*)!")
_STRINGS = re.compile(r'"(?:[^"]|"")*"')
_REF = re.compile(r"\$?[A-Za-z]{1,3}\$?\d+")
_NAME = re.compile(r"(?<![\w.$!:'\"#])([A-Za-z_\\][\w.]*)(?![\w.(!])")
_WHOLE = re.compile(r"\$?[A-Za-z]{1,3}:\$?[A-Za-z]{1,3}\b|\$?\d+:\$?\d+")
_OK_WORDS = {"TRUE", "FALSE"}


def _sides(st):
    bd = st.get("bd") or [0, 0, 0, 0]
    names = st.get("bds") or [None] * 4
    col = (st.get("bdc") or "000000").upper()
    out = []
    for w, nm in zip(bd, names):
        if not w:
            out.append(Side())
            continue
        style = nm or {1: "thin", 2: "medium", 3: "thick"}.get(w, "thin")
        out.append(Side(style=style, color="FF" + col))
    return Border(left=out[0], right=out[1], top=out[2], bottom=out[3])


def _look(st):
    """openpyxl style objects for one of the bill's styles."""
    fc = (st.get("fc") or "").upper()
    font = Font(name=st.get("font") or "Calibri", size=st.get("sz") or 11, bold=bool(st.get("b")), italic=bool(st.get("i")),
                underline="single" if st.get("u") else None, color=("FF" + fc) if len(fc) == 6 else None)
    fill = PatternFill("solid", fgColor="FF" + st["fill"].upper()) if st.get("fill") and len(st["fill"]) == 6 else PatternFill()
    ha = st.get("ha") or None
    ha = {"dec": "right", "general": None}.get(ha, ha)
    va = st.get("va") or None
    al = Alignment(horizontal=ha, vertical=va, wrap_text=bool(st.get("wrap")), indent=int(st.get("ind") or 0))
    nf = st.get("nf") or "General"
    if BE.is_date_nf(nf):
        nf = BE.DMY                                   # dates DD/MM/YYYY, still real dates
    return font, fill, al, _sides(st), nf


def _sheets_named(f):
    return {(m.group(1) or "").replace("''", "'") if m.group(1) is not None else m.group(2) for m in _SHEET_REF.finditer(_STRINGS.sub('""', f))}


def _refs_ok(f, names):
    """A formula only stays a formula when everything it points at is in the file."""
    if "[" in f:                                       # another workbook
        return False
    for m in _SHEET_REF.finditer(f):
        nm = (m.group(1) or "").replace("''", "'") if m.group(1) is not None else m.group(2)
        if nm not in names:
            return False
    bare = _STRINGS.sub('""', f)
    bare = _SHEET_REF.sub("", bare)
    bare = _REF.sub("", bare)
    bare = _WHOLE.sub("", bare)
    for m in _NAME.finditer(bare):                     # a named range: not carried over
        w = m.group(1)
        if w.upper() not in _OK_WORDS:
            return False
    return True


def _cached(v):
    """The <v> of a formula cell and its type."""
    if isinstance(v, bool):
        return ("1" if v else "0"), "b"
    if isinstance(v, (int, float)):
        if v != v or v in (float("inf"), float("-inf")):
            return "#NUM!", "e"
        return repr(float(v)) if isinstance(v, float) else str(v), None
    if v is None:
        return None, None
    s = str(v)
    if s.startswith("#") and s.rstrip("!?/0").upper() in ("#DIV", "#N", "#NUM", "#REF", "#VALUE", "#NAME", "#NULL", "#N/A") or s in ("#DIV/0!", "#N/A", "#NUM!", "#REF!", "#VALUE!", "#NAME?", "#NULL!"):
        return s, "e"
    return s, "str"


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def render_xlsx(model, values, title, inputs=None, fname=""):
    """bytes of the .xlsx - one worksheet per printed sheet, exactly as the PDF."""
    inputs = inputs or {}
    model = BR.autowrap(model, values, inputs)
    styles = model.get("styles") or [{}]
    sheets = BR.printed_sheets(model)
    printed = [s["name"] for s in sheets]
    # a sheet the bill does not print but its formulas link to (hidden in the consultant's workbook too) comes along,
    # hidden, so those links stay formulas
    by = {s["name"]: s for s in model["sheets"]}
    want, todo = set(printed), list(sheets)
    while todo:
        s0 = todo.pop()
        for cell in s0["cells"].values():
            for nm in (_sheets_named(cell["f"]) if cell.get("f") else ()):
                if nm in by and nm not in want:
                    want.add(nm); todo.append(by[nm])
    extra = [s for s in model["sheets"] if s["name"] in want and s["name"] not in printed]
    names = want
    stamps = BE.stamp_sheets(model)
    bill = model.get("_bill") or title
    wb = Workbook()
    wb.remove(wb.active)
    looks = {}
    cached = []                                        # per worksheet: {A1: (value, type)}
    stamp_on = []                                      # worksheet numbers (1-based) carrying the stamp
    for si, s in enumerate(sheets + extra):
        if si >= len(sheets):                          # a linked sheet that is not printed: its cells, hidden
            ws = wb.create_sheet(_BAD_NAME.sub("-", s["name"])[:31] or f"Sheet{si + 1}")
            ws.sheet_state = "hidden"
            cache = {}
            vals = values.get(s["name"], {})
            for k in set(s["cells"]) | {k for k in vals if re.match(r"^\d+,\d+$", k)}:
                r, c = (int(x) for x in k.split(","))
                cell = s["cells"].get(k) or {}
                v = vals.get(k, cell.get("v"))
                xc = ws.cell(row=r, column=c)
                f = cell.get("f")
                if f and _refs_ok(f, names):
                    xc.value = "=" + f
                    cv, t = _cached(v)
                    if cv is not None:
                        cache[xc.coordinate] = (cv, t)
                elif v is not None and v != "":
                    xc.value = v
                    if isinstance(v, str):
                        xc.data_type = "s"
            cached.append(cache)
            continue
        pl = BR.page_plan(model, s, inputs, values)
        ws = wb.create_sheet(_BAD_NAME.sub("-", s["name"])[:31] or f"Sheet{si + 1}")
        vals = values.get(s["name"], {})
        typed = {k for k in (inputs.get(s["name"]) or {}) if not k.startswith("_")}
        cache = {}
        cols, rh = pl["cols"], pl["rh"]
        prow_all = []
        for prow, own in pl["pages"]:
            prow_all += [r for r in own if r not in prow_all]
        shown = set(prow_all)
        r1, c1, r2, c2 = s["print_area"]
        maxr = max([s.get("maxr") or r2, r2] + [int(k.split(",")[0]) for k in list(s["cells"]) + list(vals)] or [1])
        maxc = max([s.get("maxc") or c2, c2] + [int(k.split(",")[1]) for k in list(s["cells"]) + list(vals)] or [1])
        # the cells: figures, text, formulas - all of them, the hidden ones too, so every formula still works
        keys = set(s["cells"]) | {k for k in vals if re.match(r"^\d+,\d+$", k)}
        for k in keys:
            r, c = (int(x) for x in k.split(","))
            cell = s["cells"].get(k) or {}
            v = vals.get(k, cell.get("v"))
            xc = ws.cell(row=r, column=c)
            f = cell.get("f")
            inp = (inputs.get(s["name"]) or {}).get(k)
            if k in typed and not (isinstance(inp, str) and inp.startswith("=")):
                f = None                               # typed over on the bill: the figure typed
            elif isinstance(inp, str) and inp.startswith("="):
                f = inp[1:]
            if f and _refs_ok(f, names):
                xc.value = "=" + f
                cv, t = _cached(v)
                if cv is not None:
                    cache[xc.coordinate] = (cv, t)
            elif v is not None and v != "":
                if isinstance(v, str):
                    xc.value = v
                    xc.data_type = "s"                 # text that starts with = stays text
                else:
                    xc.value = v
            si_ = cell.get("s", 0)
            if si_:
                if si_ not in looks:
                    looks[si_] = _look(styles[si_] if si_ < len(styles) else {})
                font, fill, al, bd, nf = looks[si_]
                xc.font, xc.fill, xc.alignment, xc.border, xc.number_format = font, fill, al, bd, nf
        cached.append(cache)
        for m in s.get("merges") or []:
            mr1, mc1, mr2, mc2 = m
            if mr2 > mr1 or mc2 > mc1:
                # added straight to the list: openpyxl's merge_cells() would empty the cells under the block, and
                # a figure kept there (a formula may read it, as in Excel) would be lost
                from openpyxl.worksheet.cell_range import CellRange
                ws.merged_cells.add(CellRange(min_row=mr1, min_col=mc1, max_row=mr2, max_col=mc2))
        # columns and rows: the PDF's own sizes; what the PDF leaves out is hidden
        dcw = s.get("dcw", 8.43)
        for c in range(1, maxc + 1):
            w = s["colw"].get(str(c), s["colw"].get(c, dcw))
            cd = ws.column_dimensions[get_column_letter(c)]
            cd.width = w if w else 0
            if c not in cols:
                cd.hidden = True
        for r in range(1, maxr + 1):
            rd = ws.row_dimensions[r]
            if r in shown:
                rd.height = round(rh[r] * 0.75, 2)
            else:
                rd.hidden = True
        # pictures: the logo, and the signatures of those who have signed (the stamp goes in the footer)
        colx, x = {}, 0
        for c in cols:
            colx[c] = x; x += pl["cw"][c]
        rowy, y = {}, 0
        for r in prow_all:
            rowy[r] = y; y += rh[r]
        for im in s.get("images", []):
            if BE.is_stamp(im) or not BR._img_on(im, shown, s):
                continue
            box = BR._img_box(im, cols, prow_all, colx, rowy, pl["cw"], rh, s)
            if not box:
                continue
            bx, by, bw, bh = box
            ac = next((c for c in cols if colx[c] <= bx < colx[c] + pl["cw"][c]), cols[0] if bx < 0 else cols[-1])
            ar = next((r for r in prow_all if rowy[r] <= by < rowy[r] + rh[r]), prow_all[0] if by < 0 else prow_all[-1])
            try:
                import base64
                pic = XLImage(io.BytesIO(base64.b64decode(im["data"])))
            except Exception:
                continue
            ox, oy = max(0, bx - colx[ac]), max(0, by - rowy[ar])
            pic.anchor = OneCellAnchor(_from=AnchorMarker(col=ac - 1, colOff=int(ox * EMU), row=ar - 1, rowOff=int(oy * EMU)),
                                       ext=XDRPositiveSize2D(int(bw * EMU), int(bh * EMU)))
            ws.add_image(pic)
        # printing: A4, the PDF's orientation, scale, margins, headings on every page and its page breaks
        ps = ws.page_setup
        ps.paperSize = 9
        ps.orientation = "landscape" if pl["pw"] > pl["ph"] else "portrait"
        if len(pl["pages"]) == 1:                      # one page in the PDF: one page wide and tall in Excel
            ws.sheet_properties.pageSetUpPr.fitToPage = True
            ps.fitToWidth, ps.fitToHeight = 1, 1
        else:
            # more pages: the PDF's own scale with its page breaks (Excel ignores page breaks under "Fit to"), a touch
            # smaller so a column never runs onto a page of its own where Excel measures a font a little wider
            ws.sheet_properties.pageSetUpPr.fitToPage = False
            ps.scale = max(10, min(400, int(pl["sc"] * 97 + 1e-6)))
        pm = ws.page_margins
        pm.left, pm.right, pm.top, pm.bottom = pl["ml"] / 72, pl["mr"] / 72, pl["mt"] / 72, pl["mb"] / 72
        pm.header, pm.footer = pl["mh"] / 72, pl["mf"] / 72
        ws.print_options.horizontalCentered = pl["x0"] > pl["ml"] + 1
        if cols and prow_all:
            ws.print_area = f"{get_column_letter(cols[0])}{prow_all[0]}:{get_column_letter(cols[-1])}{prow_all[-1]}"
        tt = (s.get("print") or {}).get("titles")
        if tt:
            ws.print_title_rows = f"{tt[0]}:{tt[1]}"
        from openpyxl.worksheet.pagebreak import Break, RowBreak
        ws.row_breaks = RowBreak()
        for prow, own in pl["pages"][:-1]:
            ws.row_breaks.append(Break(id=own[-1]))
        hf = ws.oddFooter
        hf.left.text, hf.left.size = bill.replace("&", "&&"), 7
        hf.center.text, hf.center.size = "&A", 7
        hf.right.text, hf.right.size = "Page &P of &N", 7
        for k, t in (pl.get("hf") or {}).items():       # the consultant's own header stays
            if k[0] == "h" and t:
                part = {"l": ws.oddHeader.left, "c": ws.oddHeader.center, "r": ws.oddHeader.right}.get(k[1])
                if part is not None:
                    part.text = BR.hf_text(t, 1, 1, s["name"], title, bill).replace("&", "&&") if "&P" not in t else t
        if s["name"] in stamps:
            stamp_on.append(si + 1)
        ws.sheet_view.showGridLines = False
        ws.sheet_view.view = "pageBreakPreview" if False else "normal"
    buf = io.BytesIO()
    wb.save(buf)
    data = _finish(buf.getvalue(), cached, stamps and BE._stamp_png(next(iter(stamps.values()))), stamp_on, bool(model.get("precision_shown")))
    return data


def _finish(data, cached, stamp_png, stamp_on, precision_shown):
    """The figures beside every formula, Excel told they are worked out already, and the stamp in the footer."""
    zin = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    zout = zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED)
    names = set(zin.namelist())
    for item in zin.infolist():
        raw = zin.read(item.filename)
        m = re.match(r"xl/worksheets/sheet(\d+)\.xml$", item.filename)
        if m:
            n = int(m.group(1))
            cache = cached[n - 1] if n - 1 < len(cached) else {}
            x = raw.decode("utf-8")

            def put(mm, cache=cache):
                attrs, body = mm.group(1), mm.group(2)
                ref = re.search(r'\br="([A-Z]+\d+)"', attrs)
                hit = cache.get(ref.group(1)) if ref else None
                if not hit or "<f>" not in body:
                    return mm.group(0)
                cv, t = hit
                attrs = re.sub(r'\st="[^"]*"', "", attrs) + (f' t="{t}"' if t else "")
                body = re.sub(r"<v>.*?</v>|<v\s*/>", "", body, flags=re.S) + f"<v>{_esc(cv)}</v>"
                return f"<c{attrs}>{body}</c>"
            x = re.sub(r"<c\b([^>]*)>(.*?)</c>", put, x, flags=re.S)
            if n in stamp_on:
                x = BE._hf_stamp(x)
                x = BE._legacy_hf(x, "rIdInfStampHF")
            raw = x.encode("utf-8")
        elif item.filename == "xl/workbook.xml":
            x = raw.decode("utf-8")
            calc = '<calcPr calcId="999999" fullCalcOnLoad="0" calcCompleted="1"' + (' fullPrecision="0"' if precision_shown else "") + "/>"
            if "<calcPr" in x:
                x = re.sub(r"<calcPr\b[^>]*/>", calc, x, count=1)
            else:
                x = x.replace("</workbook>", calc + "</workbook>")
            raw = x.encode("utf-8")
        elif item.filename == "[Content_Types].xml" and stamp_on:
            if b'Extension="png"' not in raw:
                raw = raw.replace(b"<Default ", b'<Default Extension="png" ContentType="image/png"/><Default ', 1)
            if b'Extension="vml"' not in raw:
                raw = raw.replace(b"<Default ", b'<Default Extension="vml" ContentType="application/vnd.openxmlformats-officedocument.vmlDrawing"/><Default ', 1)
        else:
            mr = re.match(r"xl/worksheets/_rels/sheet(\d+)\.xml\.rels$", item.filename)
            if mr and int(mr.group(1)) in stamp_on:
                raw = BE._add_rel(raw, "rIdInfStampHF", BE.VML_REL, f"../drawings/vmlDrawingInfStamp{mr.group(1)}.vml")
        zout.writestr(item, raw)
    for n in stamp_on:
        rp = f"xl/worksheets/_rels/sheet{n}.xml.rels"
        if rp not in names:
            zout.writestr(rp, BE._add_rel(None, "rIdInfStampHF", BE.VML_REL, f"../drawings/vmlDrawingInfStamp{n}.vml"))
        zout.writestr(f"xl/drawings/vmlDrawingInfStamp{n}.vml", BE._stamp_vml(n))
        zout.writestr(f"xl/drawings/_rels/vmlDrawingInfStamp{n}.vml.rels", BE._add_rel(None, "rId1", BE.IMG_REL, "../media/infstamp.png"))
    if stamp_on and stamp_png:
        zout.writestr("xl/media/infstamp.png", stamp_png)
    zout.close()
    return out.getvalue()


class ExportCheck(Exception):
    pass


def _read_back(data):
    """The workbook as written: [(sheet name, visible, {"r,c": {"f": .. | "v": ..}})] straight from its XML (openpyxl
    would drop the figures kept under a merged block)."""
    from openpyxl.utils import column_index_from_string as CI
    z = zipfile.ZipFile(io.BytesIO(data))
    wbx = z.read("xl/workbook.xml").decode("utf-8")
    rels = z.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    tgt = dict(re.findall(r'<Relationship[^>]*Id="([^"]+)"[^>]*Target="([^"]+)"', rels))
    tgt.update({k: v for v, k in re.findall(r'<Relationship[^>]*Target="([^"]+)"[^>]*Id="([^"]+)"', rels)})
    sst = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in re.findall(r"<si>(.*?)</si>", z.read("xl/sharedStrings.xml").decode("utf-8"), re.S):
            sst.append(BE._unesc("".join(re.findall(r"<t[^>]*>(.*?)</t>", si, re.S))))
    out = []
    for m in re.finditer(r"<sheet\b([^>]*)/>", wbx):
        at = m.group(1)
        nm = BE._unesc(re.search(r'name="([^"]*)"', at).group(1))
        vis = 'state="hidden"' not in at and 'state="veryHidden"' not in at
        rid = re.search(r'r:id="([^"]+)"', at).group(1)
        path = tgt[rid].lstrip("/")
        path = path if path.startswith("xl/") else "xl/" + path
        x = z.read(path).decode("utf-8")
        cells = {}
        for cm in re.finditer(r"<c\b([^>]*?)(?:/>|>(.*?)</c>)", x, re.S):
            ca, body = cm.group(1), cm.group(2) or ""
            ref = re.search(r'\br="([A-Z]+)(\d+)"', ca)
            k = f"{int(ref.group(2))},{CI(ref.group(1))}"
            t = (re.search(r'\bt="([^"]+)"', ca) or [None, "n"])[1]
            fm = re.search(r"<f[^>]*>(.*?)</f>", body, re.S)
            vm = re.search(r"<v>(.*?)</v>", body, re.S)
            if fm:
                cells[k] = {"f": BE._unesc(fm.group(1))}
            elif t == "inlineStr":
                cells[k] = {"v": BE._unesc("".join(re.findall(r"<t[^>]*>(.*?)</t>", body, re.S)))}
            elif vm:
                v = BE._unesc(vm.group(1))
                cells[k] = {"v": sst[int(v)] if t == "s" else (v == "1" if t == "b" else (v if t in ("str", "e") else float(v)))}
        out.append((nm, vis, cells))
    return out


def check(data, model, values):
    """The file read back and every formula worked out again from what is in it: each figure, each formula and
    the sheets must be the bill's own - otherwise the file is not handed out. [] when all is well."""
    from openpyxl.utils import get_column_letter as L
    back = _read_back(data)
    printed = [s["name"] for s in BR.printed_sheets(model)]
    shown = [n for n, vis, _ in back if vis]
    bad = []
    if shown != [_BAD_NAME.sub("-", n)[:31] for n in printed]:
        bad.append(f"sheets {shown} - the PDF has {printed}")
    orig = {_BAD_NAME.sub("-", s["name"])[:31]: s for s in model["sheets"]}
    m2 = {"sheets": [], "styles": model.get("styles") or [{}], "precision_shown": model.get("precision_shown")}
    nform_x = 0
    for n, vis, cells in back:
        o = orig.get(n, {"cells": {}})
        for k, cl in cells.items():
            if "f" in cl:
                nform_x += 1
            cl["s"] = (o["cells"].get(k) or {}).get("s", 0)
        rc = [tuple(int(x) for x in k.split(",")) for k in cells] or [(1, 1)]
        m2["sheets"].append(dict({k_: v_ for k_, v_ in o.items() if k_ not in ("cells", "images")}, name=n, cells=cells,
                                 maxr=max(r for r, _ in rc), maxc=max(c for _, c in rc)))
    book = BE.Book(m2)
    nform_app = 0
    for name in printed:
        s0 = next(s for s in model["sheets"] if s["name"] == name)
        nform_app += sum(1 for c in s0["cells"].values() if c.get("f"))
        n2 = _BAD_NAME.sub("-", name)[:31]
        vals = values.get(name, {})
        for k, v in vals.items():
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not re.match(r"^\d+,\d+$", k):
                continue
            r, c = (int(x) for x in k.split(","))
            here = book.value(n2, r, c)
            try:
                here = float(here or 0)
            except Exception:
                bad.append(f"{name} {L(c)}{r}: app {v:,.2f} / Excel {here!r}")
                continue
            if abs(here - float(v)) > 0.005:
                bad.append(f"{name} {L(c)}{r}: app {v:,.2f} / Excel {here:,.2f}")
            if len(bad) >= 20:
                return bad
    return bad

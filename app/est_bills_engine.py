"""Bills to the client (Estimation > Bills): the consultant's / client's own Excel bill is the format.

The workbook is read once when it is uploaded (read_format) into a small model: every cell in the sheets'
used area with its value or formula and its look, merged cells, column widths, row heights, the print
area and the pictures (logo, stamps, signatures). Each month only the typed cells change - the % done on
each line, the bill no., the issue date, payments, authority fees. The formulas are worked out here exactly
as Excel does (calculate), and the bill comes out as the same workbook (write_xlsx: the original file with
only those cells changed and every formula's figure filled in, pictures and formatting untouched), or as a
printed page / PDF drawn from the same model.

Standard library and openpyxl only (nothing to install on the server).
"""
import base64
import datetime as _dt
import io
import os
import tempfile
import math
import re
import zipfile
from decimal import Decimal, ROUND_HALF_UP, ROUND_UP, ROUND_DOWN
from xml.etree import ElementTree as ET

import openpyxl
from openpyxl.utils import get_column_letter, column_index_from_string

EPOCH = _dt.datetime(1899, 12, 30)
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
      "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
      "a": "http://schemas.openxmlformats.org/drawingml/2006/main"}


class BillError(Exception):
    pass


# ============================================================================ reading the format

def _serial(v):
    if isinstance(v, _dt.datetime):
        return (v - EPOCH).total_seconds() / 86400.0
    if isinstance(v, _dt.date):
        return float((_dt.datetime(v.year, v.month, v.day) - EPOCH).days)
    if isinstance(v, _dt.time):
        return (v.hour * 3600 + v.minute * 60 + v.second) / 86400.0
    return v


THEME = []          # the workbook's theme colours, read per file (lt1, dk1, lt2, dk2, accent1-6, hlink, folHlink)


def _theme_colors(z):
    names = ["lt1", "dk1", "lt2", "dk2", "accent1", "accent2", "accent3", "accent4", "accent5", "accent6", "hlink", "folHlink"]
    out = ["FFFFFF", "000000", "EEECE1", "1F497D", "4F81BD", "C0504D", "9BBB59", "8064A2", "4BACC6", "F79646", "0000FF", "800080"]
    try:
        tpath = next(n for n in z.namelist() if n.startswith("xl/theme/") and n.endswith(".xml"))
        root = ET.fromstring(z.read(tpath))
        cs = root.find(".//a:clrScheme", NS)
        found = {}
        for el in list(cs):
            tag = el.tag.split("}")[-1]
            ch = list(el)[0] if list(el) else None
            if ch is None:
                continue
            val = ch.get("lastClr") or ch.get("val")
            if val:
                found[tag] = val[-6:]
        order = {"lt1": found.get("lt1"), "dk1": found.get("dk1"), "lt2": found.get("lt2"), "dk2": found.get("dk2")}
        for i, n in enumerate(names):
            v = order.get(n) or found.get(n)
            if v:
                out[i] = v
    except Exception:
        pass
    return out


def _tint(hexs, t):
    try:
        r, g, b = (int(hexs[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return hexs
    import colorsys
    h, l, s_ = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    l = l * (1 + t) if t < 0 else l * (1 - t) + t
    r, g, b = colorsys.hls_to_rgb(h, max(0, min(1, l)), s_)
    return "%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def _color(c):
    """A cell colour as RRGGBB: plain, theme (with its tint) or the old palette; "" for automatic."""
    try:
        if c is None:
            return ""
        t = getattr(c, "type", None)
        if t == "rgb" and isinstance(c.rgb, str) and c.rgb:
            return c.rgb[-6:].upper()
        if t == "theme" and THEME:
            i = int(c.theme)
            base = THEME[i] if 0 <= i < len(THEME) else "000000"
            return _tint(base, float(c.tint or 0)).upper()
        if t == "indexed":
            from openpyxl.styles.colors import COLOR_INDEX
            i = int(c.indexed)
            if i in (64, 65):
                return ""
            return COLOR_INDEX[i][-6:].upper() if 0 <= i < len(COLOR_INDEX) else ""
    except Exception:
        return ""
    return ""


def _style(cell):
    f, al, b, fl = cell.font, cell.alignment, cell.border, cell.fill
    fill = ""
    try:
        if fl is not None and fl.fill_type == "solid":
            fill = _color(fl.fgColor) or _color(fl.start_color)
            if fill.upper() in ("FFFFFF",):
                fill = ""
    except Exception:
        fill = ""
    bd = []
    for side in (b.left, b.right, b.top, b.bottom):
        st = side.style if side is not None else None
        bd.append({"thin": 1, "hair": 1, "dotted": 1, "dashed": 1, "medium": 2, "mediumDashed": 2, "thick": 3, "double": 3}.get(st or "", 0))
    return {"b": bool(f.b), "i": bool(f.i), "u": bool(f.u), "sz": float(f.sz or 11), "fc": _color(f.color), "fill": fill,
            "ha": al.horizontal or "", "va": al.vertical or "", "wrap": bool(al.wrap_text), "ind": int(al.indent or 0),
            "bd": bd, "nf": cell.number_format or "General", "font": (f.name or "")}


def _rng(ref):
    """'A1:F40' or "'IPA'!$A$1:$F$40" -> (r1, c1, r2, c2)."""
    if not ref:
        return None
    ref = str(ref).split(",")[0]
    ref = ref.split("!")[-1].replace("$", "")
    m = re.match(r"([A-Z]{1,3})(\d+)(?::([A-Z]{1,3})(\d+))?$", ref)
    if not m:
        return None
    c1, r1 = column_index_from_string(m.group(1)), int(m.group(2))
    c2, r2 = (column_index_from_string(m.group(3)), int(m.group(4))) if m.group(3) else (c1, r1)
    return (min(r1, r2), min(c1, c2), max(r1, r2), max(c1, c2))


def _sheet_paths(z):
    """sheet name -> its xml path inside the xlsx; also the drawing of each sheet."""
    wbx = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    rmap = {r.get("Id"): r.get("Target") for r in rels.findall("rel:Relationship", NS)}
    out = {}
    for s in wbx.findall("m:sheets/m:sheet", NS):
        t = rmap.get(s.get("{%s}id" % NS["r"]), "")
        t = t.lstrip("/")
        out[s.get("name")] = t if t.startswith("xl/") else "xl/" + t
    return out


def _images(z, sheet_xml):
    """The pictures on a sheet: [{c, r, dx, dy, c2, r2, dx2, dy2, data, ext}] (0-based cells, EMU offsets)."""
    out = []
    folder, base = sheet_xml.rsplit("/", 1)
    rels_path = f"{folder}/_rels/{base}.rels"
    if rels_path not in z.namelist():
        return out
    rels = ET.fromstring(z.read(rels_path))
    for r in rels.findall("rel:Relationship", NS):
        if not r.get("Type", "").endswith("/drawing"):
            continue
        dpath = _join(folder, r.get("Target"))
        if dpath not in z.namelist():
            continue
        dfolder, dbase = dpath.rsplit("/", 1)
        drels_path = f"{dfolder}/_rels/{dbase}.rels"
        drels = {}
        if drels_path in z.namelist():
            for x in ET.fromstring(z.read(drels_path)).findall("rel:Relationship", NS):
                drels[x.get("Id")] = _join(dfolder, x.get("Target"))
        d = ET.fromstring(z.read(dpath))
        ai = -1
        for anc in list(d):
            tag = anc.tag.split("}")[-1]
            if tag not in ("twoCellAnchor", "oneCellAnchor", "absoluteAnchor"):
                continue
            ai += 1                                         # the anchor's place in the drawing (for a signature swapped in)
            blip = anc.find(".//a:blip", NS)
            if blip is None:
                continue
            emb = blip.get("{%s}embed" % NS["r"])
            ipath = drels.get(emb)
            if not ipath or ipath not in z.namelist():
                continue
            fr = anc.find("xdr:from", NS)
            g = lambda e, k: int(float(e.find("xdr:" + k, NS).text)) if e is not None and e.find("xdr:" + k, NS) is not None else 0
            item = {"c": g(fr, "col"), "r": g(fr, "row"), "dx": g(fr, "colOff"), "dy": g(fr, "rowOff"),
                    "ext": ipath.rsplit(".", 1)[-1].lower(), "data": base64.b64encode(z.read(ipath)).decode(),
                    "drawing": dpath, "anchor": ai}
            to = anc.find("xdr:to", NS)
            if to is not None:
                item.update({"c2": g(to, "col"), "r2": g(to, "row"), "dx2": g(to, "colOff"), "dy2": g(to, "rowOff")})
            else:
                ext = anc.find("xdr:ext", NS)
                item.update({"cx": int(ext.get("cx", 0)) if ext is not None else 0, "cy": int(ext.get("cy", 0)) if ext is not None else 0})
            out.append(item)
    return out


def _join(folder, target):
    if target.startswith("/"):
        return target.lstrip("/")
    parts = folder.split("/")
    for t in target.split("/"):
        if t == "..":
            parts.pop()
        elif t and t != ".":
            parts.append(t)
    return "/".join(parts)


def _hf(part):
    try:
        return (part.text or "") if part is not None else ""
    except Exception:
        return ""


def parse_hf(t):
    """An Excel header/footer string -> its left / centre / right parts (&L &C &R; text before any is centre)."""
    out, cur, buf, i = {}, "c", "", 0
    while i < len(t):
        if t[i] == "&" and i + 1 < len(t) and t[i + 1] in "LCR":
            if buf:
                out[cur] = out.get(cur, "") + buf
            cur, buf = t[i + 1].lower(), ""
            i += 2
            continue
        buf += t[i]; i += 1
    if buf:
        out[cur] = out.get(cur, "") + buf
    return {k: v for k, v in out.items() if v.strip()}


def print_setup(ws, xml=""):
    """How the consultant set the sheet to print: paper, orientation, scale or fit-to-page, margins, centring,
    rows repeated at the top of each page, manual page breaks, header and footer."""
    ps, pm = ws.page_setup, ws.page_margins
    try:
        fit = bool(ws.sheet_properties.pageSetUpPr and ws.sheet_properties.pageSetUpPr.fitToPage)
    except Exception:
        fit = False
    titles = None
    try:
        t = ws.print_title_rows
        if t:
            m = re.match(r"^\$?(\d+):\$?(\d+)$", str(t).split(",")[0].strip())
            if m:
                titles = [int(m.group(1)), int(m.group(2))]
    except Exception:
        titles = None
    def num(v, d=None):
        try:
            return float(v) if v is not None else d
        except (TypeError, ValueError):
            return d
    out = {"paper": int(ps.paperSize) if ps.paperSize else 9, "landscape": ps.orientation == "landscape",
           "fit": fit, "fw": int(ps.fitToWidth) if ps.fitToWidth is not None else None, "fh": int(ps.fitToHeight) if ps.fitToHeight is not None else None,
           "scale": int(ps.scale) if ps.scale else 100,
           "m": [num(pm.left, .7), num(pm.right, .7), num(pm.top, .75), num(pm.bottom, .75), num(pm.header, .3), num(pm.footer, .3)],
           "hc": bool(ws.print_options.horizontalCentered), "vc": bool(ws.print_options.verticalCentered),
           "titles": titles, "breaks": sorted(int(b.id) for b in ws.row_breaks.brk if b.id),
           "hf": {}}
    import html as _h
    for tag, pre in (("oddHeader", "h"), ("oddFooter", "f")):
        m = re.search(rf"<{tag}>(.*?)</{tag}>", xml or "", re.S)
        if m:
            for k, v in parse_hf(_h.unescape(m.group(1))).items():
                if not FILE_HF.search(v):                 # the file / sheet name is Excel's own, not for the client
                    out["hf"][pre + k] = v
    return out


def add_print(model, data):
    """Formats read before the print set-up was kept: read it now from the stored workbook."""
    if all("print" in s for s in model.get("sheets", [])):
        return model
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=False)
        for s in model["sheets"]:
            if "print" not in s and s["name"] in wb.sheetnames:
                s["print"] = print_setup(wb[s["name"]])            # (formats re-read in full now: see MODEL_VERSION)
    except Exception:
        pass
    return model


def shown_rows(model, sheet, inputs):
    """Rows hidden in the format that are shown this month: a spare row of the previous-payments table once it
    is filled. Nothing else is unhidden - a hidden % line stays hidden even though its Previous % is rolled on."""
    out = set()
    inp = (inputs or {}).get(sheet, {})
    for p in (model.get("map") or {}).get("payments", []):
        if p["sheet"] != sheet:
            continue
        keys = [p["cols"][k] for k in ("desc", "amount") if k in p["cols"]]
        for r in range(p["head_row"] + 1, p["total_row"]):
            if any(inp.get(f"{r},{c}") not in (None, "") for c in keys):
                out.add(r)
    return out


def _col_n(letters):
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def slim(data: bytes) -> bytes:
    """The same workbook without the empty formatted cells far to the right of everything (a sheet formatted out
    to column XFD holds half a million of them, and reading those took a minute). Only for reading the format -
    the workbook kept and sent out is the original."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        paths = _sheet_paths(z)
        wbx = z.read("xl/workbook.xml").decode("utf-8", "ignore")
        order = [m.group(1) for m in re.finditer(r'<sheet\b[^>]*\bname="([^"]*)"', wbx)]
        pa_col = {}
        for m in re.finditer(r'<definedName[^>]*name="_xlnm.Print_Area"[^>]*localSheetId="(\d+)"[^>]*>([^<]*)</definedName>', wbx):
            cols = [_col_n(c) for c in re.findall(r"\$?([A-Z]{1,3})\$?\d+", m.group(2))]
            i = int(m.group(1))
            if cols and i < len(order):
                pa_col[order[i]] = max(cols)
        bypath = {v: k for k, v in paths.items()}
    except Exception:
        return data
    out = io.BytesIO()
    zo = zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED)
    cell_re = re.compile(r'<c r="([A-Z]{1,3})(\d+)"[^>]*/>')
    for it in z.infolist():
        raw = z.read(it.filename)
        if it.filename in bypath and len(raw) > 2_000_000:
            x = raw.decode("utf-8", "ignore")
            used = [_col_n(m.group(1)) for m in re.finditer(r'<c r="([A-Z]{1,3})\d+"[^>]*>', x) if not m.group(0).endswith("/>")]
            bound = max(used + [pa_col.get(bypath[it.filename], 0), 1]) + 2
            x = cell_re.sub(lambda m: "" if _col_n(m.group(1)) > bound else m.group(0), x)
            raw = x.encode("utf-8")
        zo.writestr(it, raw)
    zo.close()
    return out.getvalue()


def xls_to_xlsx(data: bytes) -> bytes:
    """An old-format Excel bill (.xls) -> .xlsx, converted on the server with LibreOffice (formulas, layout and
    formatting kept), so the bill can be uploaded as it is instead of being re-saved in Excel first."""
    import shutil, subprocess
    exe = shutil.which("soffice") or shutil.which("libreoffice")
    if not exe:
        raise BillError("This is the old Excel format (.xls) and the server cannot convert it yet. Open it in Excel and save it as "
                        ".xlsx (File > Save As > Excel Workbook), then upload that.")
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "bill.xls")
        with open(src, "wb") as f:
            f.write(data)
        try:
            subprocess.run([exe, "--headless", "--norestore", f"-env:UserInstallation=file://{d}/lo", "--convert-to", "xlsx",
                            "--outdir", d, src], capture_output=True, timeout=150, env={**os.environ, "HOME": d})
        except subprocess.TimeoutExpired:
            raise BillError("Converting the .xls took too long. Save it as .xlsx in Excel and upload that.")
        out = os.path.join(d, "bill.xlsx")
        if not os.path.exists(out) or os.path.getsize(out) == 0:
            raise BillError("That .xls file could not be converted. Open it in Excel, save it as .xlsx and upload that.")
        with open(out, "rb") as f:
            return f.read()


def read_format(data: bytes, filename: str = ""):
    """The uploaded bill -> the model kept for the project (JSON-able)."""
    if not (filename.lower().endswith(".xls") or data[:4] == b"\xd0\xcf\x11\xe0"):
        data = slim(data)
    if filename.lower().endswith(".xls") or data[:4] == b"\xd0\xcf\x11\xe0":
        raise BillError("This is the old Excel format (.xls). Open it in Excel and save it as .xlsx (File > Save As > Excel Workbook), then upload that.")
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=False)
        wbv = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    except Exception:
        raise BillError("That file could not be opened as an Excel workbook (.xlsx).")
    paths = _sheet_paths(z)
    THEME[:] = _theme_colors(z)
    blank = {"b": False, "i": False, "u": False, "sz": 11.0, "fc": "", "fill": "", "ha": "", "va": "", "wrap": False, "ind": 0,
             "bd": [0, 0, 0, 0], "nf": "General", "font": ""}
    styles, skey = [blank], {repr(sorted(blank.items())): 0}       # style 0: a blank cell (no borders, no fill)
    sheets = []
    for ws in wb.worksheets:
        wv = wbv[ws.title]
        pa = _rng(ws.print_area) if ws.print_area else None
        # the used area: cells with something in them (a sheet formatted out to column XFD is not 16,000 columns)
        maxr = maxc = 0
        for (r, c), cell in ws._cells.items():
            if cell.value is not None and cell.value != "":
                maxr, maxc = max(maxr, r), max(maxc, c)
        if pa:
            maxr, maxc = max(maxr, pa[2]), max(maxc, pa[3])
        maxc = min(maxc, 60)
        cells = {}
        for (r, c), cell in ws._cells.items():
            if r > maxr or c > maxc:
                continue
            v = cell.value
            st = _style(cell)
            k = repr(sorted(st.items()))
            if k not in skey:
                skey[k] = len(styles); styles.append(st)
            sid = skey[k]
            if v is None or v == "":
                if sid and (any(st["bd"]) or st["fill"]):
                    cells[f"{r},{c}"] = {"s": sid}
                continue
            item = {"s": sid}
            if isinstance(v, str) and v.startswith("="):
                item["f"] = v[1:]
                cv = wv.cell(r, c).value
                item["x"] = _serial(cv)          # Excel's own figure when the file was saved (to check against)
            elif hasattr(v, "text") and type(v).__name__ in ("ArrayFormula", "DataTableFormula"):
                item["f"] = str(getattr(v, "text", "") or "").lstrip("=")
                item["x"] = _serial(wv.cell(r, c).value)
            else:
                item["v"] = _serial(v)
            cells[f"{r},{c}"] = item
        # the sheet's own default column width / row height (not Excel's 8.43 / 15 when the sheet sets others)
        try:
            dcw = float(ws.sheet_format.defaultColWidth) if ws.sheet_format.defaultColWidth else (float(ws.sheet_format.baseColWidth) + 0.43 if ws.sheet_format.baseColWidth else 8.43)
        except (TypeError, ValueError):
            dcw = 8.43
        try:
            drh = float(ws.sheet_format.defaultRowHeight) if ws.sheet_format.defaultRowHeight else 15.0
        except (TypeError, ValueError):
            drh = 15.0
        colw = {}
        for c in range(1, maxc + 1):
            d = ws.column_dimensions.get(get_column_letter(c))
            colw[c] = round(float(d.width), 2) if d is not None and d.width else dcw
            if d is not None and d.hidden:
                colw[c] = 0
        # column ranges defined as min..max
        for key, d in ws.column_dimensions.items():
            if d.min and d.max and d.max > d.min:
                for c in range(d.min, min(d.max, maxc) + 1):
                    colw[c] = 0 if d.hidden else (round(float(d.width), 2) if d.width else colw.get(c, dcw))
        rowh, hidden_rows = {}, []
        for r in range(1, maxr + 1):
            d = ws.row_dimensions.get(r)
            if d is not None:
                if d.hidden:
                    hidden_rows.append(r)
                if d.height:
                    rowh[r] = round(float(d.height), 2)
        merges = [list(_rng(str(m)) or ()) for m in ws.merged_cells.ranges]
        try:
            fit = bool(ws.sheet_properties.pageSetUpPr and ws.sheet_properties.pageSetUpPr.fitToPage)
        except Exception:
            fit = False
        sheets.append({"name": ws.title, "visible": ws.sheet_state == "visible", "print_area": list(pa) if pa else [1, 1, maxr, maxc],
                       "maxr": maxr, "maxc": maxc, "cells": cells, "colw": colw, "rowh": rowh, "hidden_rows": hidden_rows, "dcw": dcw, "drh": drh,
                       "merges": [m for m in merges if m], "fit": fit,
                       "landscape": (ws.page_setup.orientation == "landscape"), "print": print_setup(ws, z.read(paths[ws.title]).decode("utf-8", "ignore") if paths.get(ws.title) in z.namelist() else ""),
                       "images": _images(z, paths.get(ws.title, "")) if paths.get(ws.title) in z.namelist() else []})
    model = {"sheets": sheets, "styles": styles, "filename": filename, "mv": MODEL_VERSION}
    model["map"] = find_inputs(model)
    return model


# ============================================================================ the formula engine

class Err(object):
    __slots__ = ("code",)

    def __init__(self, code):
        self.code = code

    def __repr__(self):
        return self.code


DIV0, VALUE, NAME, REF, NA = Err("#DIV/0!"), Err("#VALUE!"), Err("#NAME?"), Err("#REF!"), Err("#N/A")

TOKEN = re.compile(r"""
  (?P<ws>\s+)
| (?P<str>"(?:[^"]|"")*")
| (?P<err>\#(?:DIV/0!|VALUE!|REF!|NAME\?|N/A|NUM!|NULL!))
| (?P<ref>(?:'(?:[^']|'')+'|[A-Za-z0-9_\.]+)?!?\$?[A-Za-z]{1,3}\$?\d+(?::\$?[A-Za-z]{1,3}\$?\d+)?)
| (?P<sheetref>(?:'(?:[^']|'')+'|[A-Za-z0-9_\.]+)!\$?[A-Za-z]{1,3}\$?\d+(?::\$?[A-Za-z]{1,3}\$?\d+)?)
| (?P<num>(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)
| (?P<func>[A-Za-z_][A-Za-z0-9_\.]*(?=\())
| (?P<bool>TRUE|FALSE)
| (?P<op><>|<=|>=|[-+*/^&=<>%(),:;])
""", re.X)


def _tokens(f):
    out, i = [], 0
    while i < len(f):
        m = TOKEN.match(f, i)
        if not m:
            raise BillError(f"Cannot read the formula ={f}")
        i = m.end()
        k = m.lastgroup
        if k == "ws":
            continue
        t = m.group(k)
        if k == "ref":
            # a bare word followed by ! belongs to the sheet; "A1" alone is a ref; "SUM" alone is not
            if "!" not in t and not re.match(r"\$?[A-Za-z]{1,3}\$?\d+(:\$?[A-Za-z]{1,3}\$?\d+)?$", t):
                raise BillError(f"Cannot read the formula ={f}")
        if k == "sheetref":
            k = "ref"
        out.append((k, t))
    return out


def _split_ref(t):
    sheet = None
    if "!" in t:
        sheet, t = t.rsplit("!", 1)
        if sheet.startswith("'"):
            sheet = sheet[1:-1].replace("''", "'")
    t = t.replace("$", "").upper()
    if ":" in t:
        a, b = t.split(":")
    else:
        a = b = t
    ma, mb = re.match(r"([A-Z]+)(\d+)", a), re.match(r"([A-Z]+)(\d+)", b)
    c1, r1, c2, r2 = column_index_from_string(ma.group(1)), int(ma.group(2)), column_index_from_string(mb.group(1)), int(mb.group(2))
    return sheet, min(r1, r2), min(c1, c2), max(r1, r2), max(c1, c2), (":" in t)


class _P(object):
    """Excel formula -> a tree: ("n", 1.5) ("s", "x") ("b", True) ("e", Err) ("ref", sheet, r1, c1, r2, c2, isrange)
    ("neg", x) ("pct", x) ("bin", op, a, b) ("fn", NAME, [args])."""

    def __init__(self, toks, sheet):
        self.t, self.i, self.sheet = toks, 0, sheet

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def take(self, val=None):
        k, v = self.peek()
        if val is not None and v != val:
            raise BillError(f"Formula: expected {val}")
        self.i += 1
        return k, v

    def expr(self):
        a = self.concat()
        while self.peek()[1] in ("=", "<>", "<", ">", "<=", ">="):
            op = self.take()[1]; a = ("bin", op, a, self.concat())
        return a

    def concat(self):
        a = self.add()
        while self.peek()[1] == "&":
            self.take(); a = ("bin", "&", a, self.add())
        return a

    def add(self):
        a = self.mul()
        while self.peek()[1] in ("+", "-"):
            op = self.take()[1]; a = ("bin", op, a, self.mul())
        return a

    def mul(self):
        a = self.pow()
        while self.peek()[1] in ("*", "/"):
            op = self.take()[1]; a = ("bin", op, a, self.pow())
        return a

    def pow(self):
        a = self.unary()
        while self.peek()[1] == "^":
            self.take(); a = ("bin", "^", a, self.unary())
        return a

    def unary(self):
        k, v = self.peek()
        if v == "-":
            self.take(); return ("neg", self.unary())
        if v == "+":
            self.take(); return self.unary()
        return self.postfix()

    def postfix(self):
        a = self.primary()
        while self.peek()[1] == "%":
            self.take(); a = ("pct", a)
        return a

    def primary(self):
        k, v = self.take()
        if k == "num":
            return ("n", float(v))
        if k == "str":
            return ("s", v[1:-1].replace('""', '"'))
        if k == "bool":
            return ("b", v.upper() == "TRUE")
        if k == "err":
            return ("e", Err(v))
        if k == "ref":
            sh, r1, c1, r2, c2, isr = _split_ref(v)
            return ("ref", sh or self.sheet, r1, c1, r2, c2, isr)
        if k == "func":
            name = v.upper().replace("_XLFN.", "").replace("_XLWS.", "")
            self.take("(")
            args = []
            if self.peek()[1] == ")":
                self.take(); return ("fn", name, args)
            while True:
                if self.peek()[1] in (",", ";"):
                    args.append(("none",))
                else:
                    args.append(self.expr())
                k2, v2 = self.take()
                if v2 == ")":
                    break
                if v2 not in (",", ";"):
                    raise BillError("Formula: expected , or )")
                if self.peek()[1] == ")":
                    args.append(("none",)); self.take(); break
            return ("fn", name, args)
        if v == "(":
            a = self.expr(); self.take(")"); return a
        raise BillError(f"Formula: unexpected {v}")


def parse_formula(f, sheet):
    p = _P(_tokens(f), sheet)
    tree = p.expr()
    if p.i != len(p.t):
        raise BillError(f"Cannot read the formula ={f}")
    return tree


def _num(v):
    if isinstance(v, Err):
        return v
    if v is None:
        return 0.0
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        if s == "":
            return 0.0
        try:
            return float(s[:-1]) / 100 if s.endswith("%") else float(s)
        except ValueError:
            return VALUE
    return VALUE


def general(v):
    """A number as Excel's General format writes it (for & and CONCAT)."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, float):
        if v == int(v) and abs(v) < 1e15:
            return str(int(v))
        s = f"{v:.15g}"
        if "e" in s:
            s = f"{v:.10G}"
        return s
    return str(v)


def _round(x, n, mode):
    if isinstance(x, Err):
        return x
    if isinstance(n, Err):
        return n
    d = Decimal(repr(float(x)))
    q = Decimal(1).scaleb(-int(n)) if int(n) >= 0 else Decimal(10) ** (-int(n))
    if int(n) >= 0:
        return float(d.quantize(q, rounding=mode))
    return float((d / q).quantize(Decimal(1), rounding=mode) * q)


class Book(object):
    """Works out the formulas of a model, with the typed cells changed (inputs: {sheet: {"r,c": value}})."""

    def __init__(self, model, inputs=None):
        self.model = model
        self.by_name = {s["name"]: s for s in model["sheets"]}
        self.lower = {s["name"].strip().lower(): s["name"] for s in model["sheets"]}
        self.inputs = inputs or {}
        self.memo, self.busy, self.trees, self.circ = {}, set(), {}, set()

    def sheet(self, name):
        if name in self.by_name:
            return name
        return self.lower.get((name or "").strip().lower())

    def raw(self, sheet, r, c):
        """('v', value) | ('f', formula) | None"""
        k = f"{r},{c}"
        inp = self.inputs.get(sheet)
        if inp is not None and k in inp and not k.startswith("_"):
            v = inp[k]
            if isinstance(v, str) and v.startswith("="):
                return ("f", v[1:])
            return ("v", v)
        cell = self.by_name[sheet]["cells"].get(k)
        if not cell:
            return None
        if "f" in cell:
            return ("f", cell["f"])
        return ("v", cell.get("v"))

    def value(self, sheet, r, c):
        sheet = self.sheet(sheet)
        if sheet is None:
            return REF
        key = (sheet, r, c)
        if key in self.memo:
            return self.memo[key]
        raw = self.raw(sheet, r, c)
        if raw is None:
            v = None
        elif raw[0] == "v":
            v = raw[1]
        else:
            if key in self.busy:
                # a formula that reaches itself (=MAX($A9:A$104)+1 in its own column): Excel keeps the figures the
                # cells had - so does this, from the file as saved, for every cell caught in the loop
                self.circ |= self.busy
                x = self.by_name[sheet]["cells"].get(f"{r},{c}", {}).get("x")
                return float(x) if isinstance(x, (int, float)) else 0.0
            self.busy.add(key)
            try:
                tk = (sheet, raw[1])
                tree = self.trees.get(tk)
                if tree is None:
                    try:
                        tree = parse_formula(raw[1], sheet)
                    except BillError:
                        tree = ("e", NAME)
                    self.trees[tk] = tree
                v = self.ev(tree)
                if isinstance(v, list):
                    v = v[0] if v else None
                if v is None:
                    v = 0.0
                if key in self.circ:
                    x = self.by_name[sheet]["cells"].get(f"{r},{c}", {}).get("x")
                    if x is not None:
                        v = float(x) if isinstance(x, (int, float)) else x
            finally:
                self.busy.discard(key)
        self.memo[key] = v
        return v

    def rng(self, node):
        _, sh, r1, c1, r2, c2, _isr = node
        sh2 = self.sheet(sh)
        if sh2 is None:
            return [REF]
        s = self.by_name[sh2]
        r2 = min(r2, max(s["maxr"], r1)); c2 = min(c2, max(s["maxc"], c1))
        return [self.value(sh2, r, c) for r in range(r1, r2 + 1) for c in range(c1, c2 + 1)]

    def ev(self, n):
        k = n[0]
        if k == "n" or k == "s" or k == "b":
            return n[1]
        if k == "e":
            return n[1]
        if k == "none":
            return None
        if k == "ref":
            if n[6]:
                return self.rng(n)
            v = self.value(n[1], n[2], n[3])
            return v
        if k == "neg":
            x = _num(self.scalar(self.ev(n[1])))
            return x if isinstance(x, Err) else -x
        if k == "pct":
            x = _num(self.scalar(self.ev(n[1])))
            return x if isinstance(x, Err) else x / 100.0
        if k == "bin":
            return self.binop(n[1], self.scalar(self.ev(n[2])), self.scalar(self.ev(n[3])))
        if k == "fn":
            return self.fn(n[1], n[2])
        return NAME

    @staticmethod
    def scalar(v):
        if isinstance(v, list):
            return v[0] if v else None
        return v

    def binop(self, op, a, b):
        if op == "&":
            if isinstance(a, Err):
                return a
            if isinstance(b, Err):
                return b
            return general(a) + general(b)
        if op in ("=", "<>", "<", ">", "<=", ">="):
            if isinstance(a, Err):
                return a
            if isinstance(b, Err):
                return b
            x, y = (a if a is not None else (0.0 if not isinstance(b, str) else "")), (b if b is not None else (0.0 if not isinstance(a, str) else ""))
            if isinstance(x, str) and isinstance(y, str):
                x, y = x.lower(), y.lower()
            elif isinstance(x, str) or isinstance(y, str):
                res = {"=": False, "<>": True}.get(op)
                if res is not None:
                    return res
                x, y = (1, 0) if isinstance(x, str) else (0, 1)
            else:
                x, y = float(x), float(y)
            return {"=": x == y, "<>": x != y, "<": x < y, ">": x > y, "<=": x <= y, ">=": x >= y}[op]
        x, y = _num(a), _num(b)
        if isinstance(x, Err):
            return x
        if isinstance(y, Err):
            return y
        if op == "+":
            return x + y
        if op == "-":
            return x - y
        if op == "*":
            return x * y
        if op == "/":
            return DIV0 if y == 0 else x / y
        if op == "^":
            try:
                return float(x ** y)
            except Exception:
                return VALUE
        return NAME

    def nums(self, args, strict_text=False):
        """The numbers in the arguments as SUM sees them: ranges skip text/blank/TRUE; typed values count."""
        out = []
        for a in args:
            if a[0] == "none":
                continue
            v = self.ev(a)
            if isinstance(v, list):
                for x in v:
                    if isinstance(x, Err):
                        return x
                    if isinstance(x, (int, float)) and not isinstance(x, bool):
                        out.append(float(x))
            else:
                if isinstance(v, Err):
                    return v
                x = _num(v)
                if isinstance(x, Err):
                    if strict_text:
                        return x
                    continue
                out.append(x)
        return out

    def fn(self, name, args):
        if name == "SUM":
            xs = self.nums(args)
            return xs if isinstance(xs, Err) else float(sum(xs))
        if name in ("MAX", "MIN"):
            xs = self.nums(args)
            if isinstance(xs, Err):
                return xs
            return float((max if name == "MAX" else min)(xs)) if xs else 0.0
        if name == "PRODUCT":
            xs = self.nums(args)
            if isinstance(xs, Err):
                return xs
            p = 1.0
            for x in xs:
                p *= x
            return p if xs else 0.0
        if name == "AVERAGE":
            xs = self.nums(args)
            if isinstance(xs, Err):
                return xs
            return sum(xs) / len(xs) if xs else DIV0
        if name in ("COUNT", "COUNTA"):
            n = 0
            for a in args:
                v = self.ev(a)
                for x in (v if isinstance(v, list) else [v]):
                    if name == "COUNT" and isinstance(x, (int, float)) and not isinstance(x, bool):
                        n += 1
                    elif name == "COUNTA" and x not in (None, ""):
                        n += 1
            return float(n)
        if name in ("ROUND", "ROUNDUP", "ROUNDDOWN"):
            x = _num(self.scalar(self.ev(args[0])))
            nd = _num(self.scalar(self.ev(args[1]))) if len(args) > 1 and args[1][0] != "none" else 0.0
            return _round(x, nd, {"ROUND": ROUND_HALF_UP, "ROUNDUP": ROUND_UP, "ROUNDDOWN": ROUND_DOWN}[name])
        if name == "INT":
            x = _num(self.scalar(self.ev(args[0])))
            return x if isinstance(x, Err) else float(math.floor(x))
        if name == "ABS":
            x = _num(self.scalar(self.ev(args[0])))
            return x if isinstance(x, Err) else abs(x)
        if name == "IFERROR":
            v = self.scalar(self.ev(args[0]))
            if isinstance(v, Err):
                return self.scalar(self.ev(args[1])) if len(args) > 1 else 0.0
            return v
        if name == "IF":
            c = self.scalar(self.ev(args[0]))
            if isinstance(c, Err):
                return c
            cond = bool(_num(c)) if not isinstance(c, str) else c != ""
            if cond:
                return self.scalar(self.ev(args[1])) if len(args) > 1 else True
            return self.scalar(self.ev(args[2])) if len(args) > 2 and args[2][0] != "none" else False
        if name in ("CONCAT", "CONCATENATE"):
            out = []
            for a in args:
                v = self.ev(a)
                for x in (v if isinstance(v, list) else [v]):
                    if isinstance(x, Err):
                        return x
                    out.append(general(x))
            return "".join(out)
        if name == "AND" or name == "OR":
            vals = [bool(_num(self.scalar(self.ev(a)))) for a in args]
            return all(vals) if name == "AND" else any(vals)
        if name == "UPPER":
            return general(self.scalar(self.ev(args[0]))).upper()
        if name == "TEXT":
            return general(self.scalar(self.ev(args[0])))
        return NAME

    def all_values(self, only_visible=False):
        """Every cell's figure: {sheet: {"r,c": value}} (formulas worked out, typed cells as typed)."""
        out = {}
        for s in self.model["sheets"]:
            if only_visible and not s["visible"]:
                continue
            vals = {}
            keys = set(s["cells"]) | {k for k in self.inputs.get(s["name"], {}) if not k.startswith("_")}
            for k in keys:
                r, c = (int(x) for x in k.split(","))
                v = self.value(s["name"], r, c)
                if v is not None:
                    vals[k] = v
            out[s["name"]] = vals
        return out


def calculate(model, inputs=None):
    return Book(model, inputs).all_values()


def check_against_excel(model):
    """How many formulas give Excel's own figure (the file as saved) - the engine checking itself on a new format."""
    b = Book(model)
    total = same = 0
    bad = []
    for s in model["sheets"]:
        for k, cell in s["cells"].items():
            if "f" not in cell or "x" not in cell:
                continue
            x = cell["x"]
            r, c = (int(v) for v in k.split(","))
            v = b.value(s["name"], r, c)
            total += 1
            if _same(v, x):
                same += 1
            elif len(bad) < 30:
                bad.append({"sheet": s["name"], "cell": f"{get_column_letter(c)}{r}", "formula": "=" + cell["f"], "excel": x, "here": repr(v)})
    return {"formulas": total, "same": same, "different": bad}


def _same(v, x):
    if x is None:
        return v in (None, 0, 0.0, "")
    if isinstance(x, str) and x.startswith("#"):
        return isinstance(v, Err)
    if isinstance(x, bool) or isinstance(v, bool):
        return bool(x) == bool(v)
    if isinstance(x, (int, float)):
        if isinstance(v, Err) or isinstance(v, str):
            return False
        v = 0.0 if v is None else float(v)
        return abs(v - float(x)) <= max(1e-6, abs(float(x)) * 1e-9)
    return general(v) == str(x)


# ============================================================================ what is typed each month

PCT_HEAD = re.compile(r"\b(previous|prev\.?)\b", re.I)
TOT_HEAD = re.compile(r"\b(total|cumulative|cumm?\.?|up ?to ?date|to date)\b", re.I)
CUR_HEAD = re.compile(r"\b(current|this (month|period|bill))\b", re.I)


def _text(s, r, c):
    cell = s["cells"].get(f"{r},{c}")
    if not cell:
        return ""
    v = cell.get("v")
    return v if isinstance(v, str) else ""


MAP_VERSION = 5          # 5: the item / unit / last column of each progress table
MODEL_VERSION = 4          # what read_format keeps: 3 = the sheet's default sizes and its print set-up


def find_inputs(model):
    """Where the month's figures go, per sheet:
       progress tables  - lines with Previous % / Current % / Total % (Total typed, Previous rolled from last month)
       bill no. and issue date on the cover
       previous payments table (one row per bill paid)
       the amount in words under the total due."""
    out = {"progress": [], "bill_no": None, "issue_date": None, "payments": [], "words": [], "total_due": None, "signs": [], "fees": [], "v": MAP_VERSION}
    for s in model["sheets"]:
        name = s["name"]
        # ---- header row of a progress table: a "Previous" and a "Total/Cumulative" with % under / in it
        for r in range(1, min(s["maxr"], 40) + 1):
            heads = {}
            for c in range(1, s["maxc"] + 1):
                t = " ".join(filter(None, [_text(s, r, c), _text(s, r + 1, c)]))
                if not t:
                    continue
                heads[c] = t
            prev = [c for c, t in heads.items() if PCT_HEAD.search(t)]
            tot = [c for c, t in heads.items() if TOT_HEAD.search(t) and not re.search(r"amount|value|contract", t, re.I)]
            if not prev or not tot:
                continue
            # the % group: the first Previous whose header carries % (or the first Previous)
            pc = next((c for c in prev if "%" in heads[c]), prev[0])
            tc = next((c for c in tot if c > pc and ("%" in heads[c] or c - pc <= 3)), None)
            if not tc:
                continue
            cc = next((c for c in range(pc + 1, tc) if CUR_HEAD.search(heads.get(c, ""))), (pc + 1 if tc - pc == 2 else None))
            amount_c = None
            for c in range(pc - 1, 0, -1):
                t = (heads.get(c) or "").lower()
                if re.search(r"amount|value|total|cost", t):
                    amount_c = c; break
            desc_c = next((c for c, t in heads.items() if re.search(r"description", t, re.I) and c < pc and c != amount_c), None) or \
                     next((c for c, t in heads.items() if re.search(r"work|item", t, re.I) and c < pc and c != amount_c), None)
            unit_c = next((c for c, t in heads.items() if re.fullmatch(r"\s*unit\s*", t, re.I) and c < pc), None)
            # the item / ref. no. column: a heading like Item, Ref, No., S.No left of the description (the last such: BOQ ref over CSI ref)
            item_c = None
            for c in sorted(heads):
                if desc_c and c >= desc_c:
                    break
                if re.search(r"\b(item|ref|no|s\.?\s*no|sr)\b", heads[c], re.I):
                    item_c = c
            item_c = item_c or 1
            start = r + 2 if any(_text(s, r + 1, c) for c in (pc, tc)) else r + 1
            lines = []
            for rr in range(start, s["maxr"] + 1):
                tcell = s["cells"].get(f"{rr},{tc}")
                pcell = s["cells"].get(f"{rr},{pc}")
                ccell = s["cells"].get(f"{rr},{cc}") if cc else None
                typed_t = tcell is not None and "v" in tcell and isinstance(tcell.get("v"), (int, float))
                typed_p = pcell is not None and "v" in pcell and isinstance(pcell.get("v"), (int, float))
                typed_c = ccell is not None and "v" in ccell and isinstance(ccell.get("v"), (int, float))
                if not (typed_t or typed_p):
                    continue
                if tcell is not None and "f" in tcell and pcell is not None and "f" in pcell:
                    continue
                desc = ""
                if desc_c:
                    desc = _text(s, rr, desc_c)
                if not desc:
                    for c in range(1, pc):
                        t = _text(s, rr, c)
                        if len(t) > len(desc) and c != amount_c:
                            desc = t
                # where this month's figure is typed: Total % (most formats) or Current % (Total = Previous + Current)
                how = "tot" if typed_t else ("cur" if typed_c and tcell is not None and "f" in tcell else None)
                follows = ""
                if not how and tcell is not None and "f" in tcell:
                    f = tcell["f"]
                    m2 = re.match(r"^'?([^'!]+)'?!", f)
                    if "!" in f and m2:
                        follows = f"set on the {m2.group(1).strip()} sheet"
                    else:
                        m3 = re.fullmatch(r"\$?([A-Z]{1,3})\$?(\d+)", f.strip())
                        follows = f"follows the line on row {m3.group(2)}" if m3 else "worked out by the sheet"
                item = s["cells"].get(f"{rr},{item_c}", {}).get("v") if s["cells"].get(f"{rr},{item_c}") else None
                lines.append({"r": rr, "item": general(item) if item is not None else "", "desc": desc[:300],
                              "unit": _text(s, rr, unit_c) if unit_c else "",
                              "typed_total": typed_t, "typed_prev": typed_p, "typed_cur": typed_c, "how": how, "follows": follows})
            if lines:
                out["progress"].append({"sheet": name, "head_row": r, "prev_c": pc, "cur_c": cc, "tot_c": tc, "amount_c": amount_c,
                                        "desc_c": desc_c, "item_c": item_c, "unit_c": unit_c, "start": start,
                                        "last_c": max([c for c in heads] + [tc]), "lines": lines})
            break                                   # one progress table per sheet
        # ---- cover: bill no. / issue date (the cell to the right of the label)
        for k, cell in s["cells"].items():
            v = cell.get("v")
            if not isinstance(v, str):
                continue
            r, c = (int(x) for x in k.split(","))
            t = v.strip().lower()
            if out["bill_no"] is None and re.match(r"^(interim\s+)?(bill|payment application|ipa|certificate)\s*(no|number|#)\.?\s*:?\s*$", t):
                vc = _right(s, r, c)
                if vc:
                    out["bill_no"] = {"sheet": name, "r": r, "c": vc}
            if out["issue_date"] is None and re.match(r"^(issue|submission|bill)\s*date\s*:?\s*$|^date\s+of\s+(issue|submission)\s*:?\s*$", t):
                vc = _right(s, r, c)
                if vc:
                    out["issue_date"] = {"sheet": name, "r": r, "c": vc}
            if out["total_due"] is None and re.search(r"total\s+amount\s+(due|payable)", t):
                tcol = None
                for cc in range(c + 1, s["maxc"] + 1):
                    x = s["cells"].get(f"{r},{cc}")
                    if x and ("f" in x or isinstance(x.get("v"), (int, float))):
                        tcol = cc; break
                if tcol:
                    out["total_due"] = {"sheet": name, "r": r, "c": tcol}
                    for rr in range(r + 1, r + 4):
                        for cc in range(1, s["maxc"] + 1):
                            w = _text(s, rr, cc)
                            if re.search(r"dirham|aed|only", w, re.I) and re.search(r"thousand|hundred|million|only", w, re.I):
                                out["words"].append({"sheet": name, "r": rr, "c": cc, "upper": w.upper() == w,
                                                     "of": {"sheet": name, "r": r, "c": tcol}})
                                break
        # ---- previous payments: the table under "Payment Certificate No" with a total row
        for k, cell in s["cells"].items():
            v = cell.get("v")
            if not isinstance(v, str) or not re.search(r"payment\s+certificate\s+no", v, re.I):
                continue
            r, c = (int(x) for x in k.split(","))
            cols = {}
            for cc in range(1, s["maxc"] + 1):
                t = _text(s, r, cc).lower()
                if not t:
                    continue
                if "certificate" in t:
                    cols["desc"] = cc
                elif "submission" in t:
                    cols["submitted"] = cc
                elif "certification" in t:
                    cols["certified"] = cc
                elif "receipt" in t or "received" in t:
                    cols["received"] = cc
                elif "amount" in t:
                    cols["amount"] = cc
            total_r = None
            for pat in (r"total.*(previous|received)", r"^\s*total\b(?!\s+for)"):
                for rr in range(r + 1, s["maxr"] + 1):
                    if any(re.search(pat, _text(s, rr, cc), re.I) for cc in range(1, cols.get("amount", c) + 1)):
                        total_r = rr; break
                if total_r:
                    break
            if cols.get("amount") and total_r:
                out["payments"].append({"sheet": name, "head_row": r, "total_row": total_r, "cols": cols})
            break
        # ---- payments to authorities (and any other small table): a "Description | Invoice reference | Amount" head
        # with a total row under it - its rows are typed line by line
        for k, cell in sorted(s["cells"].items(), key=lambda kv: [int(x) for x in kv[0].split(",")]):
            v = cell.get("v")
            if not isinstance(v, str) or not re.fullmatch(r"\s*(description|particulars)\s*", v, re.I):
                continue
            r, c = (int(x) for x in k.split(","))
            heads = {cc: _text(s, r, cc).lower() for cc in range(1, s["maxc"] + 1) if _text(s, r, cc)}
            ref_c = next((cc for cc, t in heads.items() if cc > c and re.search(r"invoice|reference|receipt|ref\b", t)), None)
            amt_c = next((cc for cc, t in heads.items() if cc > c and re.search(r"amount", t)), None)
            if not (ref_c and amt_c) or not s.get("visible", True) or any(p["sheet"] == name and p["head_row"] == r for p in out["payments"]):
                continue
            total_r = next((rr for rr in range(r + 1, min(r + 60, s["maxr"]) + 1)
                            if any(re.search(r"\btotal\b", _text(s, rr, cc), re.I) for cc in range(1, amt_c))), None)
            if not total_r:
                continue
            cols = {"desc": c, "ref": ref_c, "amount": amt_c}
            sn = next((cc for cc, t in heads.items() if cc < c and re.search(r"^(sn|sl|s\.?\s*no|no)\b", t)), None)
            if sn:
                cols["sn"] = sn
            out["fees"].append({"sheet": name, "head_row": r, "total_row": total_r, "cols": cols})
            break
        if s.get("visible", True):
            out["signs"].extend(find_signs(s))
    return out


def _img_ratio(im):
    try:
        from PIL import Image
        w, h = Image.open(io.BytesIO(base64.b64decode(im["data"]))).size
        return w / max(1, h)
    except Exception:
        return 2.0


STAMP_PT = 68                                  # the company stamp on the printed page: 68 pt (2.4 cm) square


def is_stamp(im):
    """The round company stamp: a square picture in coloured ink (blue / red / purple), not a client's square
    logo in black and grey, not a signature."""
    if im.get("sig"):
        return False
    if "_stamp" not in im:
        ok = False
        try:
            from PIL import Image
            I = Image.open(io.BytesIO(base64.b64decode(im["data"]))).convert("RGBA")
            w, h = I.size
            if 0.9 <= w / max(1, h) <= 1.1:
                bg = Image.new("RGBA", I.size, (255, 255, 255, 255)); bg.alpha_composite(I)
                J = bg.convert("RGB").resize((48, 48))
                px, hs = list(J.getdata()), list(J.convert("HSV").getdata())
                ink = [i for i, q in enumerate(px) if min(q) < 190]
                ok = len(ink) >= 0.1 * len(px) and sum(hs[i][1] for i in ink) / len(ink) / 255 >= 0.25
        except Exception:
            ok = False
        im["_stamp"] = ok
    return im["_stamp"]


def stamp_sheets(model):
    """{sheet name: the stamp picture} for the printed sheets that carry the company stamp - it goes at the
    bottom right of each of their pages instead of wherever it was dropped on the sheet."""
    out = {}
    for s in model["sheets"]:
        if not s.get("visible", True):
            continue
        st = next((im for im in s.get("images", []) if is_stamp(im)), None)
        if st:
            out[s["name"]] = st
    return out


def _stamp_png(im):
    raw = base64.b64decode(im["data"])
    if im.get("ext") == "png":
        return raw
    from PIL import Image
    b = io.BytesIO(); Image.open(io.BytesIO(raw)).save(b, "PNG")
    return b.getvalue()


def _hf_stamp(xml):
    """The sheet's footer gets the stamp picture on the right (&G), on every page as Excel prints it."""
    def add(t):
        t = t.replace("&amp;G", "")
        if "&amp;R" in t:
            return t.replace("&amp;R", "&amp;R&amp;G", 1)
        return t + "&amp;R&amp;G"
    m = re.search(r"<headerFooter\b([^>]*)(/>|>(.*?)</headerFooter>)", xml, re.S)
    if not m:
        body = "<oddFooter>&amp;R&amp;G</oddFooter>"
        new = f"<headerFooter>{body}</headerFooter>"
        for tag in ("pageSetup", "pageMargins", "printOptions"):
            mm = re.search(rf"<{tag}\b[^>]*?(/>|>.*?</{tag}>)", xml, re.S)
            if mm:
                return xml[:mm.end()] + new + xml[mm.end():]
        return xml.replace("</sheetData>", "</sheetData>" + new, 1)
    inner = m.group(3) or ""
    if "<oddFooter" in inner:
        inner = re.sub(r"<oddFooter>(.*?)</oddFooter>", lambda x: f"<oddFooter>{add(x.group(1))}</oddFooter>", inner, flags=re.S)
        inner = re.sub(r"<oddFooter/>", "<oddFooter>&amp;R&amp;G</oddFooter>", inner)
    else:
        # oddFooter comes after oddHeader
        if "</oddHeader>" in inner:
            inner = inner.replace("</oddHeader>", "</oddHeader><oddFooter>&amp;R&amp;G</oddFooter>", 1)
        else:
            inner = "<oddFooter>&amp;R&amp;G</oddFooter>" + inner
    for tag in ("evenFooter", "firstFooter"):
        inner = re.sub(rf"<{tag}>(.*?)</{tag}>", lambda x, tag=tag: f"<{tag}>{add(x.group(1))}</{tag}>", inner, flags=re.S)
    return xml[:m.start()] + f"<headerFooter{m.group(1)}>{inner}</headerFooter>" + xml[m.end():]


def _legacy_hf(xml, rid):
    """<legacyDrawingHF> goes after drawing / legacyDrawing and before picture, oleObjects, controls, tableParts..."""
    xml = re.sub(r"<legacyDrawingHF\b[^>]*/>", "", xml)
    tag = f'<legacyDrawingHF xmlns:r="{R_NS}" r:id="{rid}"/>'
    for t in ("picture", "oleObjects", "controls", "webPublishItems", "tableParts", "extLst"):
        mm = re.search(rf"<{t}\b", xml)
        if mm:
            return xml[:mm.start()] + tag + xml[mm.start():]
    return xml.replace("</worksheet>", tag + "</worksheet>")


def _stamp_vml(n):
    return (f'<xml xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel">'
            f'<o:shapelayout v:ext="edit"><o:idmap v:ext="edit" data="{900 + n}"/></o:shapelayout>'
            '<v:shapetype id="_x0000_t75" coordsize="21600,21600" o:spt="75" o:preferrelative="t" path="m@4@5l@4@11@9@11@9@5xe" filled="f" stroked="f">'
            '<v:stroke joinstyle="miter"/><v:formulas><v:f eqn="if lineDrawn pixelLineWidth 0"/><v:f eqn="sum @0 1 0"/><v:f eqn="sum 0 0 @1"/>'
            '<v:f eqn="prod @2 1 2"/><v:f eqn="prod @3 21600 pixelWidth"/><v:f eqn="prod @3 21600 pixelHeight"/><v:f eqn="sum @0 0 1"/>'
            '<v:f eqn="prod @6 1 2"/><v:f eqn="prod @7 21600 pixelWidth"/><v:f eqn="sum @8 21600 0"/><v:f eqn="prod @7 21600 pixelHeight"/>'
            '<v:f eqn="sum @10 21600 0"/></v:formulas><v:path o:extrusionok="f" gradientshapeok="t" o:connecttype="rect"/><o:lock v:ext="edit" aspectratio="t"/></v:shapetype>'
            f'<v:shape id="RF" o:spid="_x0000_s{(900 + n) * 1024 + 1}" type="#_x0000_t75" style="position:absolute;margin-left:0;margin-top:0;width:{STAMP_PT}pt;height:{STAMP_PT}pt;z-index:1">'
            '<v:imagedata o:relid="rId1" o:title="Stamp"/><o:lock v:ext="edit" rotation="t"/></v:shape></xml>')


SIGN_LABEL = re.compile(r"^\s*((prepared|checked|approved|verified|submitted|reviewed|certified)\s+by|signature)\s*:?\s*$", re.I)


def find_signs(s):
    """The signing places on a sheet: a "Prepared by:" / "Checked by:" / "Signature :" label, the name under it
    ("Name: Anoop S"), the designation under that, and the signature picture beside it (if the format has one)."""
    out = []
    txt = lambda r, c: _text(s, r, c)
    for k, cell in s["cells"].items():
        v = cell.get("v")
        if not isinstance(v, str) or not SIGN_LABEL.match(v):
            continue
        r, c = (int(x) for x in k.split(","))
        name = None
        for rr in range(r, r + 5):
            for cc in (c, c + 1):
                t = txt(rr, cc)
                if not t or (rr == r and cc == c):
                    continue
                m = re.match(r"^\s*name\s*:?\s*(.*)$", t, re.I)
                if m:
                    if m.group(1).strip():
                        name = {"r": rr, "c": cc, "prefix": t[:len(t) - len(m.group(1))], "orig": m.group(1).strip()}
                    else:                                   # "Name:" with the name in the next cell
                        nc = next((x for x in range(cc + 1, cc + 4) if txt(rr, x)), None)
                        if nc:
                            name = {"r": rr, "c": nc, "prefix": "", "orig": txt(rr, nc)}
                    break
            if name:
                break
        if not name:                                        # no "Name:" - the first words under the label
            for rr in range(r + 1, r + 4):
                t = txt(rr, c)
                if t and not SIGN_LABEL.match(t):
                    name = {"r": rr, "c": c, "prefix": "", "orig": t}
                    break
        if not name:
            continue
        title = None
        for rr in range(name["r"] + 1, name["r"] + 3):
            t = txt(rr, name["c"]) or txt(rr, c)
            if t and not SIGN_LABEL.match(t) and not re.match(r"^\s*(name|date)\b", t, re.I):
                title = {"r": rr, "c": name["c"] if txt(rr, name["c"]) else c, "orig": t}
                break
        # the signature picture anchored around the label - not the round company stamp (square), not a logo
        cands = []
        for i, im in enumerate(s.get("images", [])):
            ir, ic = im["r"] + 1, im["c"] + 1
            if not (r - 3 <= ir <= name["r"] and c - 1 <= ic <= c + 2) or ir <= 8:
                continue
            ratio = _img_ratio(im)
            if 0.82 <= ratio <= 1.22:
                continue                                    # square: the company stamp
            cands.append((abs(ir - r) + 2 * abs(ic - c), i))
        out.append({"sheet": s["name"], "label": v.strip().rstrip(":").strip(), "r": r, "c": c, "name": name, "title": title, "img": None, "_c": cands})
    # each picture belongs to one signing place: the nearest
    pairs = sorted((d, bi, i) for bi, b in enumerate(out) for d, i in b["_c"])
    used_b, used_i = set(), set()
    for d, bi, i in pairs:
        if bi in used_b or i in used_i:
            continue
        out[bi]["img"] = i; used_b.add(bi); used_i.add(i)
    for b in out:
        b.pop("_c", None)
    out.sort(key=lambda x: (x["r"], x["c"]))
    return out


def _right(s, r, c):
    for cc in range(c + 1, min(c + 6, s["maxc"] + 1)):
        x = s["cells"].get(f"{r},{cc}")
        if x and ("v" in x or "f" in x):
            return cc
        merged = next((m for m in s["merges"] if m[0] <= r <= m[2] and m[1] <= c <= m[3]), None)
        if merged and cc <= merged[3]:
            continue
    # the next cell, empty in the format
    return c + 1


# ============================================================================ the month's bill

def bill_no_next(v):
    """'9' -> 10, '7-R2' -> 8, 'IPA 08' -> 'IPA 09', 8.0 -> 9."""
    if isinstance(v, (int, float)):
        return float(int(v) + 1)
    s = str(v or "").strip()
    s = re.sub(r"\s*[-/ ]?\s*R\d+\s*$", "", s, flags=re.I)      # a revision suffix goes
    m = re.search(r"(\d+)(?!.*\d)", s)
    if not m:
        if re.search(r"\bpre[\s-]*final\b", s, re.I):
            return re.sub(r"\bpre[\s-]*final\b", "Final", s, flags=re.I)       # after the pre-final bill: the final bill
        return s
    n = m.group(1)
    return s[:m.start()] + str(int(n) + 1).zfill(len(n)) + s[m.end():]


def date_input(model, t):
    """The issue date as the format has it: typed as text (06.10.2026) is written the same way, else a real date."""
    d = model["map"]["issue_date"]
    sd = next(x for x in model["sheets"] if x["name"] == d["sheet"])
    was = (sd["cells"].get(f"{d['r']},{d['c']}") or {}).get("v")
    if isinstance(was, str) and re.match(r"^\s*\d{1,2}([./-])\d{1,2}\1\d{2,4}\s*$", was):
        sep = re.search(r"[./-]", was).group(0)
        return f"{t.day:02d}{sep}{t.month:02d}{sep}{t.year}"
    return _serial(t)


def roll_over(model, prev_inputs, prev_values, today=None):
    """The next month's typed cells from last month's: Previous % = last Total %, Total % stays (to be changed),
    the bill no. moves on, the issue date is today, last bill goes on the previous payments as a line to complete."""
    inputs = {k: dict(v) for k, v in (prev_inputs or {}).items()}
    mp = model["map"]
    for t in mp["progress"]:
        sh = t["sheet"]
        vals = prev_values.get(sh, {})
        for ln in t["lines"]:
            tot = vals.get(f"{ln['r']},{t['tot_c']}")
            if isinstance(tot, (int, float)):
                inputs.setdefault(sh, {})[f"{ln['r']},{t['prev_c']}"] = float(tot)
                if ln["typed_total"]:
                    inputs[sh][f"{ln['r']},{t['tot_c']}"] = float(tot)
                elif ln.get("how") == "cur" and t.get("cur_c"):
                    inputs[sh][f"{ln['r']},{t['cur_c']}"] = 0.0          # Total = Previous + Current: nothing done yet this month
    if mp.get("bill_no"):
        b = mp["bill_no"]
        cur = prev_values.get(b["sheet"], {}).get(f"{b['r']},{b['c']}")
        inputs.setdefault(b["sheet"], {})[f"{b['r']},{b['c']}"] = bill_no_next(cur)
    if mp.get("issue_date"):
        d = mp["issue_date"]
        inputs.setdefault(d["sheet"], {})[f"{d['r']},{d['c']}"] = date_input(model, today or _dt.date.today())
    # last month's bill goes on the previous payments as a line - its amount is typed when the money comes in
    if mp.get("payments") and mp.get("bill_no"):
        b = mp["bill_no"]
        last_no = prev_values.get(b["sheet"], {}).get(f"{b['r']},{b['c']}")
        last_date = prev_values.get(mp["issue_date"]["sheet"], {}).get(f"{mp['issue_date']['r']},{mp['issue_date']['c']}") if mp.get("issue_date") else None
        p = mp["payments"][0]; sh = p["sheet"]; cols = p["cols"]
        s = next(x for x in model["sheets"] if x["name"] == sh)
        n = general(last_no).strip()
        n = re.sub(r"\s*[-/ ]?\s*R\d+\s*$", "", n, flags=re.I)
        label = (f"Payment Application No {n}" if re.match(r"^\d", n) else n) if n else ""      # "Pre Final Bill" by its name
        def cellv(r, c):
            k = f"{r},{c}"
            if k in inputs.get(sh, {}):
                return inputs[sh][k]
            x = s["cells"].get(k)
            return None if not x else (x.get("v") if "v" in x else ("=" + x["f"] if "f" in x else None))
        already = any(label and isinstance(cellv(r, cols["desc"]), str) and re.sub(r"\s+", " ", cellv(r, cols["desc"]).strip().lower()) == label.lower()
                      for r in range(p["head_row"] + 1, p["total_row"]))
        if label and not already:
            for r in range(p["head_row"] + 1, p["total_row"]):
                dv, av = cellv(r, cols["desc"]), cellv(r, cols["amount"])
                if (dv in (None, "") or (isinstance(dv, str) and re.match(r"^payment (application|certificate) no\.?\s*\d*\s*$", dv.strip(), re.I) and av in (None, "", 0))) and av in (None, "", 0):
                    inputs.setdefault(sh, {})[f"{r},{cols['desc']}"] = label
                    if cols.get("submitted") and isinstance(last_date, (int, float)):
                        inputs[sh][f"{r},{cols['submitted']}"] = float(last_date)
                    break
    # payments to authorities: last month's lines are hidden (kept in the file), and a heading for this bill with
    # one empty line is put in above the total, ready to type - as the office does in Excel
    label_new = None
    if mp.get("bill_no"):
        b = mp["bill_no"]
        label_new = general(inputs.get(b["sheet"], {}).get(f"{b['r']},{b['c']}", "")).strip()
    for t in mp.get("fees", []):
        sh = t["sheet"]
        s = next(x for x in model["sheets"] if x["name"] == sh)
        hid = set(s.get("hidden_rows") or []) | set(int(x) for x in inputs.get(sh, {}).get("_hide") or [])
        vis = [r for r in range(t["head_row"] + 1, t["total_row"]) if r not in hid]
        def has(r):
            return any(inputs.get(sh, {}).get(f"{r},{c}") not in (None, "") or (s["cells"].get(f"{r},{c}") or {}).get("v") not in (None, "")
                       for c in (t["cols"]["desc"], t["cols"]["ref"], t["cols"]["amount"]))
        filled = [r for r in vis if has(r)]
        if not filled:
            continue
        inp = inputs.setdefault(sh, {})
        inp["_hide"] = sorted((hid - set(s.get("hidden_rows") or [])) | set(filled))
        # new rows go in after the last line of last month's bill (before the empty row kept above the total)
        at = filled[-1] + 1
        heads = [r for r in filled if (inputs.get(sh, {}).get(f"{r},{t['cols']['amount']}") in (None, "") and (s["cells"].get(f"{r},{t['cols']['amount']}") or {}).get("v") in (None, ""))]
        datas = [r for r in filled if r not in heads]
        like = [heads[-1] if heads else filled[-1], datas[-1] if datas else filled[-1]]
        inputs[sh] = shift_inputs(inp, sh, at, 2)
        inputs[sh].setdefault("_rows", []).append([at, 2, like])
        hc, ac = t["cols"]["desc"], t["cols"]["amount"]
        inputs[sh][f"{at},{hc}"] = f"IPA {label_new}" if label_new else "This bill"
        # the sub-total counts this bill's lines only (the office rewrites it each month in Excel)
        tr = t["total_row"] + 2
        col = get_column_letter(ac)
        inputs[sh][f"{tr},{ac}"] = f"=SUM({col}{at}:{col}{tr - 1})"
    return inputs


ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split()


def _words(n, use_and=False):
    """A whole number in English words; use_and: the British "two hundred and nineteen"."""
    n = int(n)
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10 - 2] + ("-" + ONES[n % 10] if n % 10 else "")
    if n < 1000:
        r = n % 100
        return ONES[n // 100] + " hundred" + (((" and " if use_and else " ") + _words(r, use_and)) if r else "")
    for div, name in ((10 ** 9, "billion"), (10 ** 6, "million"), (1000, "thousand")):
        if n >= div:
            r = n % div
            return _words(n // div, use_and) + " " + name + (((" and " if use_and and r < 100 else " ") + _words(r, use_and)) if r else "")
    return str(n)


_NW = sorted("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen "
             "eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand million billion".split(), key=len, reverse=True)
NUMWORD = r"\b(?:" + "|".join(_NW) + r")\b"
# the run of words that is the figure: number words joined by spaces, hyphens and "and", with any "... fils" part
_RUN = re.compile(NUMWORD + r"(?:(?:\s+|-|\s+and\s+)" + NUMWORD + r")*(?:\s+(?:and\s+)?" + NUMWORD + r"(?:(?:\s+|-)" + NUMWORD + r")*\s+fils\b)?", re.I)


def _case_like(body, sample):
    """Write the words in the case the format writes them: ALL CAPS, Title Case or lower case."""
    letters = re.sub(r"[^A-Za-z]", "", sample)
    if letters and letters.isupper():
        return body.upper()
    if sample[:1].isupper():
        t = " ".join(w.capitalize() if w.lower() not in ("and",) else "and" for w in body.split(" "))
        return re.sub(r"-([a-z])", lambda m: "-" + m.group(1).upper(), t)
    return body.lower()


def amount_words(v, upper=None, like=""):
    """The figure in words, written exactly the way the format writes it - its words before and after the figure
    kept, the same case, hyphens ("fifty-three") or not, "hundred and" or not:
    "(DIRHAMS EIGHT HUNDRED SEVENTY EIGHT THOUSAND TWO HUNDRED AND NINETEEN Only)"."""
    v = round(float(v or 0), 2)
    neg = v < 0                                       # the bill comes out below nothing: "MINUS ..." (never an error)
    v = abs(v)
    d, f = int(v), int(round((v - int(v)) * 100))
    if f == 100:
        d, f = d + 1, 0
    like = like or ""
    hyphen = bool(re.search(NUMWORD + r"-" + NUMWORD, like, re.I)) or not re.search(NUMWORD, like, re.I)
    use_and = bool(re.search(r"\b(hundred|thousand|million)\s+and\b", like, re.I))
    def w(n):
        # "and" only before the last part, as the consultants write it: "... thousand two hundred and nineteen"
        t = _words(n)
        if use_and and n >= 100 and n % 100:
            head, tail = _words(n - n % 100), _words(n % 100)
            t = head + " and " + tail
        return t if hyphen else t.replace("-", " ")
    body = ("minus " if neg else "") + w(d) + ((" and " + w(f) + " fils") if f else "")
    runs = list(_RUN.finditer(like))
    if runs:
        m = max(runs, key=lambda x: len(x.group(0)))          # the figure is the longest run of number words
        out = like[:m.start()] + _case_like(body, m.group(0)) + like[m.end():]
    else:
        out = "(Dirhams " + _case_like(body, "Title") + " Only)"
        if upper:
            out = out.upper()
    return out


def with_words(model, inputs):
    """The amount in words under the total due, written from the figure (it is text in the format)."""
    b = Book(model, inputs)
    out = {k: dict(v) for k, v in (inputs or {}).items()}
    for w in model["map"].get("words", []):
        v = b.value(w["of"]["sheet"], w["of"]["r"], w["of"]["c"])
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            like = _text(next(s for s in model["sheets"] if s["name"] == w["sheet"]), w["r"], w["c"])
            try:
                out.setdefault(w["sheet"], {})[f"{w['r']},{w['c']}"] = amount_words(v, w.get("upper", True), like)
            except Exception:
                pass                                  # the words are left as they were rather than stop the bill saving
    return out


# ============================================================================ the bill out as Excel

def _esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _unesc(t):
    return str(t).replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&amp;", "&")



def _num_txt(v):
    v = float(v)
    return str(int(v)) if v.is_integer() and abs(v) < 1e15 else repr(v)


def _attrs_without(attrs, *names):
    for n in names:
        attrs = re.sub(r'\s%s="[^"]*"' % n, "", attrs)
    return attrs


def _typed_cell(attrs, v):
    """A <c> holding a typed value (number, or text as an inline string). attrs keeps r= and s= (the look)."""
    a = _attrs_without(attrs, "t")
    if v is None or v == "":
        return f"<c{a}/>"
    if isinstance(v, bool):
        return f'<c{a} t="b"><v>{1 if v else 0}</v></c>'
    if isinstance(v, (int, float)):
        return f"<c{a}><v>{_num_txt(v)}</v></c>"
    return f'<c{a} t="inlineStr"><is><t xml:space="preserve">{_esc(v)}</t></is></c>'


def _cached(attrs, fxml, v):
    """A formula cell with this month's figure as its cached value."""
    a = _attrs_without(attrs, "t")
    if isinstance(v, Err):
        return f'<c{a} t="e">{fxml}<v>{_esc(v.code)}</v></c>'
    if isinstance(v, bool):
        return f'<c{a} t="b">{fxml}<v>{1 if v else 0}</v></c>'
    if isinstance(v, (int, float)):
        return f"<c{a}>{fxml}<v>{repr(float(v))}</v></c>"
    if isinstance(v, str):
        return f'<c{a} t="str">{fxml}<v>{_esc(v)}</v></c>'
    return f"<c{a}>{fxml}</c>"


A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
IMG_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"


def _sig_anchor(p, r, c, dx, dy, cx, cy, rid, n):
    return (f'<{p}:oneCellAnchor><{p}:from><{p}:col>{c}</{p}:col><{p}:colOff>{dx}</{p}:colOff><{p}:row>{r}</{p}:row><{p}:rowOff>{dy}</{p}:rowOff></{p}:from>'
            f'<{p}:ext cx="{cx}" cy="{cy}"/><{p}:pic xmlns:a="{A_NS}" xmlns:r="{R_NS}"><{p}:nvPicPr><{p}:cNvPr id="{9000 + n}" name="Signature {n}"/>'
            f'<{p}:cNvPicPr><a:picLocks noChangeAspect="1"/></{p}:cNvPicPr></{p}:nvPicPr><{p}:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></{p}:blipFill>'
            f'<{p}:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></{p}:spPr></{p}:pic><{p}:clientData/></{p}:oneCellAnchor>')


def _sign_patches(model, signs):
    """Per drawing: {anchor index: new anchor xml or "" (taken off)}, new anchors, new media and relationships."""
    out, n = {}, 0
    for sp in signs or []:
        sh = next((x for x in model["sheets"] if x["name"] == sp["sheet"]), None)
        if not sh or not sh.get("images"):
            continue
        if sp["img"] is not None:
            im = sh["images"][sp["img"]]
        else:
            im = sh["images"][0]                       # a sheet with pictures already has its drawing: the new one goes in it
        dpath = im.get("drawing")
        if not dpath:
            continue
        d = out.setdefault(dpath, {"replace": {}, "add": [], "media": []})
        if sp["png"] is None:
            if sp["img"] is not None:
                d["replace"][im["anchor"]] = None
            continue
        n += 1
        rid, media = f"rIdInfSig{n}", f"xl/media/infsig{n}.png"
        d["media"].append((rid, media, sp["png"]))
        if sp["img"] is not None:
            box = sp.get("box") or {}
            d["replace"][im["anchor"]] = (im["r"], im["c"], im.get("dx", 0), im.get("dy", 0), box.get("cx") or im.get("cx") or 1143000, box.get("cy") or im.get("cy") or 381000, rid, n)
        else:
            pl = sp["place"]
            d["add"].append((pl["r"], pl["c"], pl["dx"], pl["dy"], pl["cx"], pl["cy"], rid, n))
    return out


VML_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/vmlDrawing"


def _rels_path(p):
    d, f = p.rsplit("/", 1)
    return f"{d}/_rels/{f}.rels"


def _rels_owner(rp):
    d, f = rp.split("/_rels/")
    return f"{d}/{f[:-5]}"


def _add_rel(raw, rid, typ, target):
    rel = f'<Relationship Id="{rid}" Type="{typ}" Target="{target}"/>'
    if raw is None:
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                + rel + "</Relationships>").encode("utf-8")
    x = raw.decode("utf-8")
    x = re.sub(rf'<Relationship[^>]*Id="{rid}"[^>]*/>', "", x)
    return x.replace("</Relationships>", rel + "</Relationships>").encode("utf-8")


def _patch_drawing(raw, patch):
    x = raw.decode("utf-8")
    m = re.search(r"<(\w+):wsDr\b", x)
    p = m.group(1) if m else "xdr"
    anchors = list(re.finditer(rf"<{p}:(twoCellAnchor|oneCellAnchor|absoluteAnchor)\b.*?</{p}:\1>", x, re.S))
    for i in sorted(patch["replace"], reverse=True):
        if i >= len(anchors):
            continue
        a = anchors[i]
        new = "" if patch["replace"][i] is None else _sig_anchor(p, *patch["replace"][i])
        x = x[:a.start()] + new + x[a.end():]
    if patch["add"]:
        end = x.rfind(f"</{p}:wsDr>")
        x = x[:end] + "".join(_sig_anchor(p, *a) for a in patch["add"]) + x[end:]
    return x.encode("utf-8")


def _patch_rels(raw, media, dpath):
    x = raw.decode("utf-8") if raw else f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>'
    add = "".join(f'<Relationship Id="{rid}" Type="{IMG_REL}" Target="../media/{m.rsplit("/", 1)[1]}"/>' for rid, m, _ in media)
    return x.replace("</Relationships>", add + "</Relationships>").encode("utf-8")


def write_xlsx(data: bytes, model, inputs, values, signs=None):
    """The original workbook with this month's typed cells written in and every formula's figure updated, and this
    bill's signatures in place of the format's. Everything else (pictures, page setup, styles, hidden sheets) is left
    exactly as it was."""
    for prefix, uri in NS.items():
        if prefix in ("m",):
            ET.register_namespace("", uri)
        else:
            ET.register_namespace(prefix, uri)
    zin = zipfile.ZipFile(io.BytesIO(data))
    paths = _sheet_paths(zin)
    by_path = {}
    for s in model["sheets"]:
        p = paths.get(s["name"])
        if p:
            by_path[p] = s
    out = io.BytesIO()
    zout = zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED)
    dpatch = _sign_patches(model, signs)
    stamps = stamp_sheets(model)
    for s in model["sheets"]:                        # the stamp comes off the sheet: it is printed in the footer instead
        if s["name"] not in stamps:
            continue
        for im in s.get("images", []):
            if is_stamp(im) and im.get("drawing") and im.get("anchor") is not None:
                d = dpatch.setdefault(im["drawing"], {"replace": {}, "add": [], "media": []})
                d["replace"].setdefault(im["anchor"], None)
    stamp_png = _stamp_png(next(iter(stamps.values()))) if stamps else None
    hf_rels = {}                                     # sheet path -> the vml drawing number
    for i, s in enumerate(model["sheets"]):
        if s["name"] in stamps and paths.get(s["name"]):
            hf_rels[paths[s["name"]]] = i + 1
    rels_of = {f'{d.rsplit("/", 1)[0]}/_rels/{d.rsplit("/", 1)[1]}.rels': d for d in dpatch}
    names = set(zin.namelist())
    ins = [(sh, int(x[0]), int(x[1]), x[2] if len(x) > 2 else None, row_opts(x)) for sh, inp in (inputs or {}).items() if isinstance(inp, dict) for x in (inp.get("_rows") or [])]
    draw_of = {}
    for s in model["sheets"]:
        for im in s.get("images", []):
            if im.get("drawing"):
                draw_of[im["drawing"]] = s["name"]
    for item in zin.infolist():
        raw = zin.read(item.filename)
        if item.filename in by_path:
            s = by_path[item.filename]
            if ins:
                xml = raw.decode("utf-8")
                for sh, r, n, like, op in ins:            # rows put in, in the order they were added
                    if sh == s["name"]:
                        xml = _xml_shift_attr(xml, r, n)
                        xml = _xml_insert_rows(xml, s, r, n, like)
                    def ff(m, sh=sh, r=r, n=n, op=op):
                        f = shift_formula(_unesc(m.group(2)), s["name"], sh, r, n)
                        if op.get("kind") == "line":
                            f = grow_ranges(f, s["name"], sh, r, n)
                        return "<f" + m.group(1) + ">" + _esc(f) + "</f>"
                    xml = re.sub(r"<f\b([^>]*)>(.*?)</f>", ff, xml, flags=re.S)
                raw = xml.encode("utf-8")
            inp_s = (inputs or {}).get(s["name"], {})
            new = {k: ("=" + c["f"]) if "f" in c else c.get("v") for k, c in s["cells"].items() if c.get("new")}
            if new:                                       # the formulas of lines put in on the bill
                inp_s = dict(new, **inp_s)
            raw = _patch_sheet(raw, s, inp_s, values.get(s["name"], {}), shown_rows(model, s["name"], inputs))
            if item.filename in hf_rels:
                raw = _legacy_hf(_hf_stamp(raw.decode("utf-8")), "rIdInfStampHF").encode("utf-8")
        elif item.filename == "xl/workbook.xml":
            raw = _full_calc(raw)
            if ins:
                xml = raw.decode("utf-8")
                for sh, r, n, _l, _o in ins:
                    def dn(m, sh=sh, r=r, n=n):
                        return m.group(1) + _esc(shift_formula(_unesc(m.group(2)), "", sh, r, n)) + "</definedName>"
                    xml = re.sub(r"(<definedName\b[^>]*>)(.*?)</definedName>", dn, xml, flags=re.S)
                raw = xml.encode("utf-8")
        elif ins and item.filename in draw_of and item.filename not in dpatch:
            xml = raw.decode("utf-8")
            for sh, r, n, _l, _o in ins:
                if sh == draw_of[item.filename]:
                    xml = re.sub(r"<xdr:row>(\d+)</xdr:row>", lambda m: m.group(0) if int(m.group(1)) + 1 < r else f"<xdr:row>{int(m.group(1)) + n}</xdr:row>", xml)
            raw = xml.encode("utf-8")
        elif item.filename == "xl/calcChain.xml":
            continue                                   # Excel rebuilds it
        elif item.filename in dpatch:
            if ins and item.filename in draw_of:       # rows put in move the pictures below them first
                xml = raw.decode("utf-8")
                for sh, r, n, _l, _o in ins:
                    if sh == draw_of[item.filename]:
                        xml = re.sub(r"<xdr:row>(\d+)</xdr:row>", lambda m: m.group(0) if int(m.group(1)) + 1 < r else f"<xdr:row>{int(m.group(1)) + n}</xdr:row>", xml)
                raw = xml.encode("utf-8")
            raw = _patch_drawing(raw, dpatch[item.filename])
        elif item.filename in {_rels_path(p) for p in hf_rels}:
            raw = _add_rel(raw, "rIdInfStampHF", VML_REL, f"../drawings/vmlDrawingInfStamp{hf_rels[_rels_owner(item.filename)]}.vml")
        elif item.filename in rels_of:
            raw = _patch_rels(raw, dpatch[rels_of[item.filename]]["media"], rels_of[item.filename])
        elif item.filename == "[Content_Types].xml":
            if (dpatch or stamps) and b'Extension="png"' not in raw:
                raw = raw.replace(b"<Default ", b'<Default Extension="png" ContentType="image/png"/><Default ', 1)
            if stamps and b'Extension="vml"' not in raw:
                raw = raw.replace(b"<Default ", b'<Default Extension="vml" ContentType="application/vnd.openxmlformats-officedocument.vmlDrawing"/><Default ', 1)
        zout.writestr(item, raw)
    for sp, n in hf_rels.items():
        if _rels_path(sp) not in names:
            zout.writestr(_rels_path(sp), _add_rel(None, "rIdInfStampHF", VML_REL, f"../drawings/vmlDrawingInfStamp{n}.vml"))
        zout.writestr(f"xl/drawings/vmlDrawingInfStamp{n}.vml", _stamp_vml(n))
        zout.writestr(f"xl/drawings/_rels/vmlDrawingInfStamp{n}.vml.rels", _add_rel(None, "rId1", IMG_REL, "../media/infstamp.png"))
    if hf_rels:
        zout.writestr("xl/media/infstamp.png", stamp_png)
    for rp, d in rels_of.items():
        if rp not in names and dpatch[d]["media"]:
            zout.writestr(rp, _patch_rels(None, dpatch[d]["media"], d))
    for d in dpatch.values():
        for rid, media, png in d["media"]:
            zout.writestr(media, png)
    zout.close()
    # the content types and relationships must not point at the removed calcChain
    return _drop_calcchain_refs(out.getvalue())


def _drop_calcchain_refs(data):
    zin = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    zout = zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED)
    for item in zin.infolist():
        raw = zin.read(item.filename)
        if item.filename == "[Content_Types].xml":
            raw = re.sub(rb'<Override[^>]*calcChain[^>]*/>', b"", raw)
        elif item.filename == "xl/_rels/workbook.xml.rels":
            raw = re.sub(rb'<Relationship[^>]*calcChain[^>]*/>', b"", raw)
        zout.writestr(item, raw)
    zout.close()
    return out.getvalue()


def _full_calc(raw):
    s = raw.decode("utf-8")
    if "<calcPr" in s:
        s = re.sub(r"<calcPr([^>]*?)/>", lambda m: "<calcPr" + re.sub(r'\s(fullCalcOnLoad|calcCompleted)="[^"]*"', "", m.group(1)) + ' fullCalcOnLoad="1"/>', s, count=1)
    else:
        s = s.replace("</workbook>", '<calcPr fullCalcOnLoad="1"/></workbook>')
    return s.encode("utf-8")


CELL = re.compile(r'<c\b([^>]*?)(/>|>(.*?)</c>)', re.S)
FORMULA = re.compile(r'<f\b[^>]*?(?:/>|>.*?</f>)', re.S)
ROW = re.compile(r'<row\b[^>]*?\br="(\d+)"[^>]*?(?:/>|>.*?</row>)', re.S)


FILE_HF = re.compile(r"&[FAZ]")       # &F file name, &A sheet name, &Z path: Excel's own in a header - not for the client


def _drop_file_hf(xml):
    """A page header or footer that prints the file / sheet name (IC/913_IPA_10.xlsx/IPA/26) is taken off;
    "Page 1 of 9" stays."""
    def fix(m):
        return "" if FILE_HF.search(m.group(2).replace("&amp;", "&")) else m.group(0)
    return re.sub(r"<((?:odd|even|first)(?:Header|Footer))>(.*?)</\1>", fix, xml, flags=re.S)


REF_RE = re.compile(r"(?<![A-Za-z0-9_.])(?:('(?:[^']|'')+'|[A-Za-z0-9_.]+)!)?(\$?)([A-Z]{1,3})(\$?)(\d+)(?![A-Za-z0-9_(])")


def _unq(name):
    name = name or ""
    return name[1:-1].replace("''", "'") if name.startswith("'") else name


def shift_formula(f, own_sheet, target, r, n):
    """Cell refs on `target` at or below row r moved down by n - refs written in a formula on own_sheet
    (unprefixed refs mean own_sheet)."""
    def one(m):
        sheet = _unq(m.group(1)) if m.group(1) else own_sheet
        if sheet.strip().lower() != target.strip().lower():
            return m.group(0)
        row = int(m.group(5))
        if row < r:
            return m.group(0)
        pre = m.group(0)[:m.start(2) - m.start(0)]
        return f"{pre}{m.group(2)}{m.group(3)}{m.group(4)}{row + n}"
    return REF_RE.sub(one, f)


RANGE_RE = re.compile(r"(?<![A-Za-z0-9_.])(?:('(?:[^']|'')+'|[A-Za-z0-9_.]+)!)?(\$?[A-Z]{1,3}\$?)(\d+):(\$?[A-Z]{1,3}\$?)(\d+)(?![A-Za-z0-9_(])")


def grow_ranges(f, own_sheet, target, r, n):
    """A total over the rows just above an insertion takes the new rows in: A5:A20 with rows put in at 21 -> A5:A21.
    (Only ranges of more than one row on `target` that end on row r-1.)"""
    def one(m):
        sheet = _unq(m.group(1)) if m.group(1) else own_sheet
        if sheet.strip().lower() != target.strip().lower():
            return m.group(0)
        a, b = int(m.group(3)), int(m.group(5))
        if b != r - 1 or a >= b:
            return m.group(0)
        return m.group(0)[:m.start(5) - m.start(0)] + str(b + n)
    return RANGE_RE.sub(one, f)


def _same_row_formula(f, own_sheet, row):
    """The formula's refs are all on `row` of its own sheet, relative (G13 = F13*E13, I13 = J13-H13): it can be copied
    to another line. Arithmetic with no refs at all (=52826.96/2) is a typed figure, not copied."""
    refs = list(REF_RE.finditer(f))
    if not refs:
        return False
    for m in refs:
        if m.group(1) and _unq(m.group(1)).strip().lower() != own_sheet.strip().lower():
            return False
        if m.group(4) or int(m.group(5)) != row:
            return False
    return True


def _move_row(f, frm, to):
    return REF_RE.sub(lambda m: m.group(0)[:m.start(5) - m.start(0)] + str(to) if int(m.group(5)) == frm and not m.group(4) else m.group(0), f)


def row_opts(x):
    """The options of a `_rows` entry [at, n, like, opts]: {"kind": "line"|"head", "last_c", "zero": [cols]}."""
    return x[3] if len(x) > 3 and isinstance(x[3], dict) else {}


def insert_rows(model, sheet, r, n, like=None, opts=None):
    """A new model with n rows put in before row r of `sheet`: cells below move down, every formula in the
    workbook that points at them follows, so do merges, heights, hidden rows, pictures, print area and breaks.
    The new rows take the look (borders, fonts) of the row they were put in front of."""
    import copy
    m = dict(model); m["sheets"] = []
    for s in model["sheets"]:
        s2 = dict(s)
        if s["name"] == sheet:
            cells = {}
            for k, cell in s["cells"].items():
                rr, cc = (int(x) for x in k.split(","))
                cell = dict(cell)
                if "f" in cell:
                    cell["f"] = shift_formula(cell["f"], s["name"], sheet, r, n)
                if "f" in cell and opts and opts.get("kind") == "line":
                    cell["f"] = grow_ranges(cell["f"], s["name"], sheet, r, n)
                cells[f"{rr + n if rr >= r else rr},{cc}"] = cell
            # the new rows: the ruled, empty look of the rows they are modelled on (row r unless told otherwise)
            srcs = [int(x) for x in (like or [])] or [r]
            for i in range(n):
                sr = srcs[min(i, len(srcs) - 1)]
                for cc in range(1, s["maxc"] + 1):
                    src = s["cells"].get(f"{sr},{cc}")
                    if src and src.get("s"):
                        cells[f"{r + i},{cc}"] = {"s": src["s"]}
                if opts and opts.get("kind") == "line":     # a new line: the row-by-row formulas of the line it is modelled on
                    zero = set(int(z) for z in opts.get("zero") or [])
                    for cc in range(1, int(opts.get("last_c") or s["maxc"]) + 1):
                        src = s["cells"].get(f"{sr},{cc}")
                        if not src:
                            continue
                        if "f" in src and _same_row_formula(src["f"], s["name"], sr):
                            cells[f"{r + i},{cc}"] = {"s": src.get("s"), "f": _move_row(src["f"], sr, r + i), "new": True}
                        elif cc in zero:
                            cells[f"{r + i},{cc}"] = {"s": src.get("s"), "v": 0, "new": True}
            s2["cells"] = cells
            s2["maxr"] = s["maxr"] + n
            rowh = {str(k): v for k, v in s["rowh"].items()}
            s2["rowh"] = {(str(int(k) + n) if int(k) >= r else k): v for k, v in rowh.items()}
            for i in range(n):
                sr = srcs[min(i, len(srcs) - 1)]
                if str(sr) in rowh:
                    s2["rowh"][str(r + i)] = rowh[str(sr)]
            s2["hidden_rows"] = [x + n if x >= r else x for x in s.get("hidden_rows", [])]
            s2["merges"] = [[a + n if a >= r else a, b, c2 + n if c2 >= r else c2, d] for a, b, c2, d in s.get("merges", [])]
            pa = list(s["print_area"]); pa[2] = pa[2] + n if pa[2] >= r else pa[2]; s2["print_area"] = pa
            if s.get("print"):
                pr = dict(s["print"]); pr["breaks"] = [x + n if x >= r else x for x in pr.get("breaks", [])]
                if pr.get("titles"):
                    pr["titles"] = [x + n if x >= r else x for x in pr["titles"]]
                s2["print"] = pr
            ims = []
            for im in s.get("images", []):
                im = dict(im)
                if im["r"] + 1 >= r:
                    im["r"] += n
                if "r2" in im and im["r2"] + 1 >= r:
                    im["r2"] += n
                ims.append(im)
            s2["images"] = ims
        else:
            cells = {}
            for k, cell in s["cells"].items():
                if "f" in cell and sheet.lower() in cell["f"].lower():
                    cell = dict(cell); cell["f"] = shift_formula(cell["f"], s["name"], sheet, r, n)
                    if opts and opts.get("kind") == "line":
                        cell["f"] = grow_ranges(cell["f"], s["name"], sheet, r, n)
                cells[k] = cell
            s2["cells"] = cells
        m["sheets"].append(s2)
    return m


def expand(model, inputs):
    """The format with this bill's inserted rows applied ({sheet: {"_rows": [[r, n], ...]}}); the map read again."""
    rows = [(sh, x) for sh, inp in (inputs or {}).items() for x in (inp.get("_rows") or []) if isinstance(inp, dict)]
    if not rows:
        return model
    m = model
    for sh, x in rows:
        m = insert_rows(m, sh, int(x[0]), int(x[1]), x[2] if len(x) > 2 else None, row_opts(x))
    m["map"] = find_inputs(m)
    return m


def shift_inputs(inp, sheet, at, n):
    """A sheet's typed cells after n rows are put in before row `at`: keys below move down, formulas typed on the
    sheet follow, the hidden-row list too."""
    out = {}
    for k, v in (inp or {}).items():
        if k.startswith("_"):
            out[k] = v; continue
        r, c = (int(x) for x in k.split(","))
        if isinstance(v, str) and v.startswith("="):
            v = "=" + shift_formula(v[1:], sheet, sheet, at, n)
        out[f"{r + n if r >= at else r},{c}"] = v
    for hk in ("_hide", "_heads"):
        if out.get(hk):
            out[hk] = [r + n if r >= at else r for r in out[hk]]
    return out


def added_rows(inputs, sheet):
    """Rows put in on the bill (or an earlier bill) as lines / headings: {row now: (index in _rows, kind)}."""
    rows = ((inputs or {}).get(sheet) or {}).get("_rows") or []
    out = {}
    for j, x in enumerate(rows):
        kind = row_opts(x).get("kind")
        if not kind:
            continue
        for i in range(int(x[1])):
            p = int(x[0]) + i
            for y in rows[j + 1:]:                       # moved down by the rows put in above it later
                if int(y[0]) <= p:
                    p += int(y[1])
            out[p] = (j, kind)
    return out


def drop_added(inputs, sheet, row):
    """A line / heading put in on the bill taken out again: the rows below move back up, every later insertion,
    typed cell and formula with them. Returns the new inputs (None if the row was not put in on the bill)."""
    inp = dict((inputs or {}).get(sheet) or {})
    rows = [list(x) for x in inp.get("_rows") or []]
    hit = added_rows(inputs, sheet).get(row)
    if not hit or int(rows[hit[0]][1]) != 1:
        return None
    j = hit[0]
    p = int(rows[j][0])                                  # where it is at each later insertion
    for y in rows[j + 1:]:
        if int(y[0]) <= p:
            p += int(y[1])
        else:
            y[0] = int(y[0]) - 1
            if len(y) > 2 and y[2]:
                y[2] = [int(z) - 1 if int(z) > p else int(z) for z in y[2]]
    del rows[j]
    out = {}
    for k, v in inp.items():
        if k.startswith("_"):
            continue
        r, c = (int(x) for x in k.split(","))
        if r == row:
            continue
        if isinstance(v, str) and v.startswith("="):
            v = "=" + shift_formula(v[1:], sheet, sheet, row + 1, -1)
        out[f"{r - 1 if r > row else r},{c}"] = v
    for hk in ("_hide", "_heads"):
        if inp.get(hk):
            out[hk] = [r - 1 if r > row else r for r in inp[hk] if r != row]
    for k, v in inp.items():
        if k.startswith("_") and k not in ("_hide", "_heads", "_rows"):
            out[k] = v
    if rows:
        out["_rows"] = rows
    res = dict(inputs); res[sheet] = out
    # formulas typed on other sheets that point below the row move back up too
    for sh, other in list(res.items()):
        if sh == sheet or sh.startswith("_") or not isinstance(other, dict):
            continue
        o2 = {}
        for k, v in other.items():
            if isinstance(v, str) and v.startswith("=") and sheet.lower() in v.lower():
                v = "=" + shift_formula(v[1:], sh, sheet, row + 1, -1)
            o2[k] = v
        res[sh] = o2
    return res


def hidden_extra(inputs, sheet):
    """Rows this bill hides (last month's lines of a table, kept in the file but not printed)."""
    inp = (inputs or {}).get(sheet) or {}
    return set(int(x) for x in (inp.get("_hide") or []))


def _xml_shift_attr(xml, r, n):
    """Row numbers in a sheet's XML moved down: <row r>, <c r>, mergeCell refs, dimension, breaks, sqref."""
    def row_fix(m):
        rr = int(m.group(2))
        return m.group(0) if rr < r else f'{m.group(1)}{rr + n}"'
    xml = re.sub(r'(<row\b[^>]*?\br=")(\d+)"', row_fix, xml)
    xml = re.sub(r'(<c\b[^>]*?\br="[A-Z]+)(\d+)"', row_fix, xml)
    def ref_fix(m):                                      # A1:B9 style refs in attributes
        return REF_RE.sub(lambda x: x.group(0) if int(x.group(5)) < r else f"{x.group(2)}{x.group(3)}{x.group(4)}{int(x.group(5)) + n}", m.group(0))
    xml = re.sub(r'(?:ref|sqref)="[^"]*"', ref_fix, xml)
    xml = re.sub(r'<brk\b[^>]*?\bid="(\d+)"', lambda m: m.group(0) if int(m.group(1)) < r else m.group(0).replace(f'id="{m.group(1)}"', f'id="{int(m.group(1)) + n}"'), xml)
    return xml


def _xml_insert_rows(xml, s_before, r, n, like=None):
    """n rows put in before row r (after the numbers below were moved down), each with the look of the row it is
    modelled on (row r unless told otherwise; `like` rows are numbered as before the move)."""
    m = re.search(r'<row\b[^>]*?\br="%d"[^>]*?(?:/>|>.*?</row>)' % (r + n), xml, re.S)
    if not m:
        return xml
    srcs = [int(x) for x in (like or [])] or [r]
    new = []
    for i in range(n):
        sr = srcs[min(i, len(srcs) - 1)]
        sr_now = sr + n if sr >= r else sr
        sm = re.search(r'<row\b[^>]*?\br="%d"[^>]*?(?:/>|>.*?</row>)' % sr_now, xml, re.S)
        row = (sm or m).group(0)
        row = re.sub(r'(<row\b[^>]*?\br=")\d+"', lambda x: f'{x.group(1)}{r + i}"', row, count=1)
        row = re.sub(r'(<c\b[^>]*?\br="[A-Z]+)\d+"', lambda x: f'{x.group(1)}{r + i}"', row)
        row = re.sub(r'\shidden="(1|true)"', "", row, count=1)
        row = CELL.sub(lambda x: "<c" + _attrs_without(x.group(1), "t") + "/>", row)        # values dropped, look kept
        new.append(row)
    return xml[:m.start()] + "".join(new) + xml[m.start():]


def _patch_sheet(raw, s, inp, vals, shown=None):
    """Text edits on the sheet's XML: only the cells that change are rewritten, nothing else is touched."""
    xml = _drop_file_hf(raw.decode("utf-8"))
    done = set()

    def one(m):
        attrs, inner = m.group(1), m.group(3) or ""
        rm = re.search(r'\br="([A-Z]+)(\d+)"', attrs)
        if not rm:
            return m.group(0)
        r, c = int(rm.group(2)), column_index_from_string(rm.group(1))
        k = f"{r},{c}"
        if k in inp and not k.startswith("_"):
            done.add(k)
            v = inp[k]
            if isinstance(v, str) and v.startswith("="):
                return _cached(attrs, f"<f>{_esc(v[1:])}</f>", vals.get(k))
            return _typed_cell(attrs, v)
        fm = FORMULA.search(inner)
        if fm and k in vals:
            return _cached(attrs, fm.group(0), vals.get(k))
        return m.group(0)

    xml = CELL.sub(one, xml)
    # a row hidden in the format that is filled in this month (a spare payments row) is shown
    filled = shown or set()
    if filled:
        def unhide(m):
            r = int(m.group(1))
            if r not in filled:
                return m.group(0)
            head_end = m.group(0).index(">")
            head = re.sub(r'\shidden="(1|true)"', "", m.group(0)[:head_end])
            return head + m.group(0)[head_end:]
        xml = ROW.sub(unhide, xml)
    hide = set(int(x) for x in (inp.get("_hide") or []))
    if hide:
        def dohide(m):
            if int(m.group(1)) not in hide or 'hidden="1"' in m.group(0)[:m.group(0).index(">")]:
                return m.group(0)
            head_end = m.group(0).index(">")
            head = m.group(0)[:head_end]
            if head.endswith("/"):
                head = head[:-1] + ' hidden="1"/'
            else:
                head += ' hidden="1"'
            return head + m.group(0)[head_end:]
        xml = ROW.sub(dohide, xml)
    # typed cells that are empty in the format (no <c> there yet)
    todo = {}
    for k, v in inp.items():
        if k.startswith("_"):
            continue
        if k not in done:
            r, c = (int(x) for x in k.split(","))
            todo.setdefault(r, []).append((c, v))
    if todo:
        def add_to_row(m):
            r = int(m.group(1))
            if r not in todo:
                return m.group(0)
            row = m.group(0)
            for c, v in sorted(todo.pop(r)):
                new = _typed_cell(f' r="{get_column_letter(c)}{r}"', v)
                if row.endswith("/>"):
                    row = row[:-2] + ">" + new + "</row>"
                    continue
                # in column order
                pos = None
                for cm in CELL.finditer(row):
                    rm = re.search(r'\br="([A-Z]+)\d+"', cm.group(1))
                    if rm and column_index_from_string(rm.group(1)) > c:
                        pos = cm.start(); break
                if pos is None:
                    pos = row.rindex("</row>")
                row = row[:pos] + new + row[pos:]
            return row
        xml = ROW.sub(add_to_row, xml)
        if todo:                                        # whole rows that do not exist yet
            sd_end = xml.index("</sheetData>") if "</sheetData>" in xml else None
            for r in sorted(todo):
                cells = "".join(_typed_cell(f' r="{get_column_letter(c)}{r}"', v) for c, v in sorted(todo[r]))
                new_row = f'<row r="{r}">{cells}</row>'
                nxt = next((m for m in ROW.finditer(xml) if int(m.group(1)) > r), None)
                if nxt:
                    xml = xml[:nxt.start()] + new_row + xml[nxt.start():]
                elif "<sheetData/>" in xml:
                    xml = xml.replace("<sheetData/>", f"<sheetData>{new_row}</sheetData>")
                else:
                    i2 = xml.index("</sheetData>"); xml = xml[:i2] + new_row + xml[i2:]
    return xml.encode("utf-8")


# ---- pages added on a bill: a copy of one of the consultant's sheets ----------------------------------------------
# A bill's inputs may hold {"_pages": {"list": [{"name": "Variations 2", "from": "Variations"}]}}: each is a copy of
# the sheet named, added after the last sheet (so no sheet's print settings move), with its own typed cells and
# lines like any sheet. The next bill keeps it (roll-over copies the inputs).
PAGE_BAD = re.compile(r"[\[\]:*?/\\]")


def pages_of(inputs):
    p = (inputs or {}).get("_pages")
    return [x for x in (p.get("list") if isinstance(p, dict) else []) or [] if isinstance(x, dict) and x.get("name") and x.get("from")]


def add_pages(model, inputs):
    """The format with this bill's added pages (before its inserted rows are applied)."""
    import copy
    pages = pages_of(inputs)
    if not pages:
        return model
    m = dict(model); m["sheets"] = list(model["sheets"])
    have = {s["name"] for s in m["sheets"]}
    for pg in pages:
        src = next((s for s in model["sheets"] if s["name"] == pg["from"]), None)
        if src is None or pg["name"] in have:
            continue
        s2 = copy.deepcopy(src)
        s2["name"] = pg["name"]; s2["visible"] = True
        s2["page_of"] = src["name"]
        m["sheets"].append(s2); have.add(pg["name"])
    m["map"] = find_inputs(m)
    return m


def add_pages_xlsx(data: bytes, inputs):
    """The workbook with this bill's added pages as real sheets: each a copy of its sheet's xml (and its drawing, so
    the logo comes too), added after the last sheet, with the copy's print area."""
    pages = pages_of(inputs)
    if not pages:
        return data
    zin = zipfile.ZipFile(io.BytesIO(data))
    names = set(zin.namelist())
    paths = _sheet_paths(zin)
    wb = zin.read("xl/workbook.xml").decode("utf-8")
    rels = zin.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    ct = zin.read("[Content_Types].xml").decode("utf-8")
    extra = {}
    sheet_ids = [int(x) for x in re.findall(r'<sheet\b[^>]*\bsheetId="(\d+)"', wb)] or [0]
    n_sheets = len(re.findall(r"<sheet\b", wb))
    for k, pg in enumerate(pages):
        src = paths.get(pg["from"])
        if not src or src not in names or pg["name"] in paths:
            continue
        new = f"xl/worksheets/sheetInfPage{k + 1}.xml"
        xml = zin.read(src).decode("utf-8")
        # only the drawing goes with the copy; other links of the sheet (printer settings, comments, tables) do not
        xml = re.sub(r"<legacyDrawing(HF)?\b[^>]*/>", "", xml)
        xml = re.sub(r"<tableParts\b.*?</tableParts>|<tableParts\b[^>]*/>", "", xml, flags=re.S)
        xml = re.sub(r"<hyperlinks>.*?</hyperlinks>", "", xml, flags=re.S)
        xml = re.sub(r'(<pageSetup\b[^>]*?)\s+r:id="[^"]*"', r"\1", xml)
        xml = re.sub(r'(<sheetView\b[^>]*?)\s+tabSelected="1"', r"\1", xml)
        src_rels = f'{src.rsplit("/", 1)[0]}/_rels/{src.rsplit("/", 1)[1]}.rels'
        new_rels = []
        dm = re.search(r'<drawing\b[^>]*r:id="([^"]+)"', xml)
        if dm and src_rels in names:
            rx = zin.read(src_rels).decode("utf-8")
            t = re.search(r'<Relationship\b[^>]*Id="%s"[^>]*Target="([^"]+)"' % re.escape(dm.group(1)), rx) or \
                re.search(r'<Relationship\b[^>]*Target="([^"]+)"[^>]*Id="%s"' % re.escape(dm.group(1)), rx)
            if t:
                dsrc = _join(src.rsplit("/", 1)[0], t.group(1))
                if dsrc in names:
                    dnew = f"xl/drawings/drawingInfPage{k + 1}.xml"
                    extra[dnew] = zin.read(dsrc)
                    drels = f'xl/drawings/_rels/{dsrc.rsplit("/", 1)[1]}.rels'
                    if drels in names:
                        extra[f"xl/drawings/_rels/drawingInfPage{k + 1}.xml.rels"] = zin.read(drels)
                    new_rels.append(f'<Relationship Id="{dm.group(1)}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/drawingInfPage{k + 1}.xml"/>')
                    if f'PartName="/{dnew}"' not in ct:
                        ct = ct.replace("</Types>", f'<Override PartName="/{dnew}" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/></Types>')
        if not new_rels:
            xml = re.sub(r"<drawing\b[^>]*/>", "", xml)
        else:
            extra[f"xl/worksheets/_rels/sheetInfPage{k + 1}.xml.rels"] = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                + "".join(new_rels) + "</Relationships>").encode("utf-8")
        extra[new] = xml.encode("utf-8")
        rid = f"rIdInfPage{k + 1}"
        sid = max(sheet_ids) + 1; sheet_ids.append(sid)
        wb = wb.replace("</sheets>", f'<sheet xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" name="{_esc(pg["name"])}" sheetId="{sid}" r:id="{rid}"/></sheets>', 1)
        rels = rels.replace("</Relationships>", f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheetInfPage{k + 1}.xml"/></Relationships>')
        ct = ct.replace("</Types>", f'<Override PartName="/{new}" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        # the copy prints the same part of the page as its sheet
        src_idx = next((i for i, (nm, _p) in enumerate(paths.items()) if nm == pg["from"]), None)
        pa = re.search(r'<definedName\b[^>]*name="_xlnm\.Print_Area"[^>]*localSheetId="%s"[^>]*>([^<]*)</definedName>' % src_idx, wb) if src_idx is not None else None
        if pa:
            ref = re.sub(r"^'?[^'!]+'?!", "", _unesc(pa.group(1)).split(",")[0])
            dn = f'<definedName name="_xlnm.Print_Area" localSheetId="{n_sheets}">{_esc(chr(39) + pg["name"].replace(chr(39), chr(39) * 2) + chr(39) + "!" + ref)}</definedName>'
            wb = wb.replace("</definedNames>", dn + "</definedNames>", 1) if "</definedNames>" in wb else wb.replace("</sheets>", "</sheets><definedNames>" + dn + "</definedNames>", 1)
        n_sheets += 1
    out = io.BytesIO()
    zout = zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED)
    for item in zin.infolist():
        raw = zin.read(item.filename)
        if item.filename == "xl/workbook.xml":
            raw = wb.encode("utf-8")
        elif item.filename == "xl/_rels/workbook.xml.rels":
            raw = rels.encode("utf-8")
        elif item.filename == "[Content_Types].xml":
            raw = ct.encode("utf-8")
        zout.writestr(item, raw)
    for k, v in extra.items():
        zout.writestr(k, v)
    zout.close()
    return out.getvalue()

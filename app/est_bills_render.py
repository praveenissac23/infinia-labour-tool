"""Drawing a bill from its format model: the sheet as the consultant laid it out - column widths, row heights,
merged cells, borders, fills, fonts, number formats, the logo / stamps / signatures - on screen (sheet_html:
the same table for the editor and the preview) and as a PDF (render_pdf, reportlab).
"""
import base64
import datetime as _dt
import io
import os
import math
import re
from html import escape

from est_bills_engine import Err, general, EPOCH

EMU_PX = 9525.0


# ---------------------------------------------------------------------------------------------- number formats

def _sections(nf):
    out, cur, q = [], "", False
    for ch in nf:
        if ch == '"':
            q = not q
        if ch == ";" and not q:
            out.append(cur); cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


def _date_text(serial, fmt):
    try:
        d = EPOCH + _dt.timedelta(days=float(serial))
    except Exception:
        return general(serial)
    f = re.sub(r"\[[^\]]*\]", "", fmt)
    f = re.sub(r'"([^"]*)"', lambda m: "\x00" + m.group(1) + "\x01", f).replace("\\", "")
    out, i = "", 0
    names = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    lit = False
    while i < len(f):
        ch = f[i]
        if ch == "\x00":
            lit = True; i += 1; continue
        if ch == "\x01":
            lit = False; i += 1; continue
        if lit:
            out += ch; i += 1; continue
        low = f[i:].lower()
        for tok, val in (("yyyy", f"{d.year}"), ("yy", f"{d.year % 100:02d}"), ("mmmm", names[d.month - 1]), ("mmm", names[d.month - 1][:3]),
                         ("mm", f"{d.month:02d}"), ("m", f"{d.month}"), ("dddd", days[d.weekday()]), ("ddd", days[d.weekday()][:3]),
                         ("dd", f"{d.day:02d}"), ("d", f"{d.day}")):
            if low.startswith(tok):
                out += val; i += len(tok); break
        else:
            if ch.lower() in "hs" or low.startswith("am/pm"):
                i += 1; continue
            out += ch; i += 1
    return out.strip()


_RAWNUM = re.compile(r"(?<![\w.\-/,])(-?\d{4,}\.\d+|-?\d+\.\d{3,}|(?<=AED )-?\d{4,}|(?<=AED)-?\d{4,}|(?<=Dhs )-?\d{4,})(?![\w.\-/,])")


def tidy_text(t):
    """Text a formula builds from figures (="= AED "&E14) shows them as Excel would print a raw number - 3589674.704.
    On screen and on the PDF they are shown as money: 3,589,674.70. The Excel file keeps the consultant's formula."""
    if not t:
        return t
    return _RAWNUM.sub(lambda m: f"{float(m.group(1)):,.2f}", t)


def fmt(v, nf="General"):
    """A value as Excel shows it with that number format."""
    if v is None:
        return ""
    if isinstance(v, Err):
        return v.code
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, str):
        secs = _sections(nf or "")
        if len(secs) >= 4 and "@" in secs[3]:
            return _literals(secs[3]).replace("@", v)
        return v
    v = float(v)
    nf = (nf or "General").strip()
    if nf in ("General", "@", ""):
        if v == int(v) and abs(v) < 1e11:
            return str(int(v))
        s = f"{v:.10g}"
        return s if "e" not in s else f"{v:.4E}"
    secs = _sections(nf)
    sec = secs[0]
    neg_own = False
    if v < 0 and len(secs) > 1 and secs[1].strip():
        sec, neg_own = secs[1], True
    elif v == 0 and len(secs) > 2 and secs[2].strip():
        sec = secs[2]
    body = re.sub(r"\[(Red|Black|Blue|Green|Color\d+|White|Yellow|Magenta|Cyan)\]", "", sec, flags=re.I)
    body = re.sub(r"\[\$([^\-\]]*)(?:-[^\]]*)?\]", lambda m: '"' + m.group(1) + '"', body)      # [$AED-409], [$AED] -> AED
    body = re.sub(r"\[[<>=][^\]]*\]", "", body)
    plain = re.sub(r'"[^"]*"', "", body)
    if re.search(r"[dmy]", plain.replace("General", ""), re.I) and not re.search(r"[0#?]", plain):
        return _date_text(v, body)
    x = abs(v) if (neg_own or v >= 0) else abs(v)
    pct = plain.count("%")
    x = x * (100 ** pct)
    m = re.search(r"[#0?,]*\.?[#0?]*(?:[eE][+-][0#]+)?", plain)
    num_pat = ""
    for mm in re.finditer(r"[#0?][#0?,]*(?:\.[#0?]*)?|\.[#0?]+", plain):
        num_pat = mm.group(0); break
    if not num_pat:
        txt = _literals(body)
        return ("-" if v < 0 and not neg_own else "") + txt
    dec = num_pat.split(".")[1] if "." in num_pat else ""
    nd = len(dec)
    mind = dec.count("0")
    comma = "," in num_pat.split(".")[0]
    # trailing commas scale by thousands
    tail = re.search(r"([#0?])(,+)(?:\.|$|[^#0?,])", num_pat + " ")
    if tail and not num_pat.split(".")[0].rstrip(",").count(","):
        pass
    s = f"{round(x + 0.0, nd):,.{nd}f}" if comma else f"{round(x + 0.0, nd):.{nd}f}"
    if nd > mind and "." in s:
        s = s.rstrip("0")
        if len(s.split(".")[1]) < mind:
            s += "0" * (mind - len(s.split(".")[1]))
        if s.endswith("."):
            s = s[:-1]
    int_pat = num_pat.split(".")[0].replace(",", "")
    if int_pat and not int_pat.count("0") and s.split(".")[0] in ("0", ""):
        # '#' / '?' places show nothing for a leading zero ("-"?? in accounting formats shows just the dash)
        s = s[1:] if s.startswith("0") and (nd and "." in s) else ("" if s == "0" else s)
    # put the number back among the format's literals
    i = body.find(num_pat) if num_pat in body else -1
    if i >= 0:
        pre, post = body[:i], body[i + len(num_pat):]
    else:
        pre, post = "", ""
    txt = _literals(pre) + s + _literals(post)
    if v < 0 and not neg_own and x != 0:
        txt = "-" + txt
    return txt


def _literals(t):
    """The fixed text of a format: quoted text, \\x, spaces for _x, no fills."""
    out, i = "", 0
    while i < len(t):
        ch = t[i]
        if ch == '"':
            j = t.find('"', i + 1); j = len(t) if j < 0 else j
            out += t[i + 1:j]; i = j + 1; continue
        if ch == "\\" and i + 1 < len(t):
            out += t[i + 1]; i += 2; continue
        if ch == "_" and i + 1 < len(t):
            out += " "; i += 2; continue
        if ch == "*" and i + 1 < len(t):
            i += 2; continue
        if ch == "%":
            out += "%"; i += 1; continue
        out += ch; i += 1
    return out


# ---------------------------------------------------------------------------------------------- geometry

def colpx(w):
    return 0 if not w else int(w * 7 + 5)


def rowpx(h):
    return int(round((h if h else 15) * 96 / 72))


def layout(s, area=None, shown=None, hide=None):
    """Visible columns and rows of the area with their pixel sizes, and the merged blocks. shown: rows that are
    hidden in the format but filled in this month (a spare payments row) - they show; hide: rows this bill hides."""
    r1, c1, r2, c2 = area or s["print_area"]
    dcw, drh = s.get("dcw", 8.43), s.get("drh", 15.0)
    cols = [c for c in range(c1, c2 + 1) if colpx(s["colw"].get(str(c), s["colw"].get(c, dcw))) > 0]
    hidden = (set(s.get("hidden_rows") or []) | set(hide or ())) - set(shown or ())
    rows = [r for r in range(r1, r2 + 1) if r not in hidden]
    cw = {c: colpx(s["colw"].get(str(c), s["colw"].get(c, dcw))) for c in cols}
    rh = {r: rowpx(s["rowh"].get(str(r), s["rowh"].get(r)) or drh) for r in rows}
    if any(rh[r] == 0 for r in rows):
        rows = [r for r in rows if rh[r] > 0]
    merges = {}
    covered = set()
    for m in s.get("merges", []):
        mr1, mc1, mr2, mc2 = m
        if mr2 < r1 or mr1 > r2 or mc2 < c1 or mc1 > c2:
            continue
        merges[(mr1, mc1)] = (mr2, mc2)
        for r in range(mr1, mr2 + 1):
            for c in range(mc1, mc2 + 1):
                if (r, c) != (mr1, mc1):
                    covered.add((r, c))
    return cols, rows, cw, rh, merges, covered


SERIF = re.compile(r"times|cambria|georgia|garamond|book antiqua|palatino|serif", re.I)


def _family(name):
    n = (name or "").strip()
    if not n:
        return ""
    fb = "'Times New Roman',serif" if SERIF.search(n) else "Calibri,sans-serif"
    return f"font-family:'{n}',{fb}"


def _style_css(st, num):
    css = []
    if st.get("font") and st["font"].lower() not in ("calibri",):
        css.append(_family(st["font"]))
    if st.get("b"):
        css.append("font-weight:700")
    if st.get("i"):
        css.append("font-style:italic")
    if st.get("u"):
        css.append("text-decoration:underline")
    sz = st.get("sz") or 11
    if abs(sz - 11) > 0.1:
        css.append(f"font-size:{sz:g}pt")
    if st.get("fc") and st["fc"].upper() not in ("000000",):
        css.append(f"color:#{st['fc']}")
    if st.get("fill"):
        css.append(f"background:#{st['fill']}")
    ha = st.get("ha") or ""
    ha = {"centerContinuous": "center", "general": "", "fill": "left", "justify": "left", "distributed": "center"}.get(ha, ha)
    if not ha:
        ha = "right" if num else "left"
    css.append(f"text-align:{ha}")
    va = {"center": "middle", "top": "top", "bottom": "bottom"}.get(st.get("va") or "", "bottom")
    css.append(f"vertical-align:{va}")
    if st.get("wrap") and not num:                       # Excel wraps text at spaces - never a number, never mid-word
        css.append("white-space:pre-wrap;overflow-wrap:normal")
    if st.get("ind"):
        css.append(f"padding-left:{3 + st['ind'] * 9}px")
    return css


def _border_css(bd):
    names = ("left", "right", "top", "bottom")
    out = []
    for n, w in zip(names, bd or [0, 0, 0, 0]):
        if w:
            out.append(f"border-{n}:{'1px' if w == 1 else ('2px' if w == 2 else '3px')} {'double' if w == 3 else 'solid'} #000")
    return out


def editable(model, sheet, k, inputs):
    """A cell staff may type in: a typed value in the format, or typed arithmetic (=200000/1.05) - never a formula
    that works something out from other cells."""
    if k in (inputs or {}).get(sheet["name"], {}):
        return True
    cell = sheet["cells"].get(k)
    if not cell:
        return True                                      # an empty cell
    if "f" in cell:
        return not re.search(r"[A-Za-z]{1,3}\$?\d+|!", cell["f"]) or bool(re.match(r"^\s*[-+]?[\d.\s()+\-*/]+$", cell["f"]))
    return True


def sheet_html(model, s, values, inputs=None, edit=False, area=None, mark=None, rows_only=None, img_rows=None, stamp="below"):
    """The sheet as an HTML table at its own sizes, with its pictures. edit=True marks the cells staff can type in.
    rows_only: just these rows, in this order (one printed page: the rows repeated at the top, then the page's own);
    img_rows: the rows whose pictures belong on it."""
    styles = model["styles"]
    vals = values.get(s["name"], {})
    inp = (inputs or {}).get(s["name"], {})
    cols, rows, cw, rh, merges, covered = layout(s, area, shown_rows(model, s["name"], inputs), hidden_extra(inputs, s["name"]))
    if rows_only is not None:
        rows = [r for r in rows_only if r in rh]
    colx, x = {}, 0
    for c in cols:
        colx[c] = x; x += cw[c]
    width = x
    rowy, y = {}, 0
    for r in rows:
        rowy[r] = y; y += rh[r]
    height = y
    rowset, colset = set(rows), set(cols)
    h = [f'<div class="xs" data-sheet="{escape(s["name"])}" style="width:{width}px;height:{height}px">']
    h.append(f'<table class="xt" style="width:{width}px"><colgroup>' + "".join(f'<col style="width:{cw[c]}px">' for c in cols) + "</colgroup>")
    for r in rows:
        h.append(f'<tr data-r="{r}" style="height:{rh[r]}px">' if edit else f'<tr style="height:{rh[r]}px">')
        for c in cols:
            if (r, c) in covered:
                continue
            k = f"{r},{c}"
            cell = s["cells"].get(k) or {}
            st = styles[cell.get("s", 0)] if styles else {}
            span = ""
            if (r, c) in merges:
                mr2, mc2 = merges[(r, c)]
                cs = sum(1 for cc in cols if c <= cc <= mc2)
                rs = sum(1 for rr in rows if r <= rr <= mr2)
                span = (f' colspan="{cs}"' if cs > 1 else "") + (f' rowspan="{rs}"' if rs > 1 else "")
                # the merged block takes the right / bottom borders of its far cells
                far = s["cells"].get(f"{r},{mc2}") or {}
                low = s["cells"].get(f"{mr2},{c}") or {}
                bd = list(st.get("bd") or [0, 0, 0, 0])
                if far:
                    bd[1] = max(bd[1], (styles[far.get("s", 0)].get("bd") or [0, 0, 0, 0])[1])
                if low:
                    bd[3] = max(bd[3], (styles[low.get("s", 0)].get("bd") or [0, 0, 0, 0])[3])
            else:
                bd = st.get("bd") or [0, 0, 0, 0]
            v = vals.get(k) if k in vals else (inp.get(k) if k in inp else cell.get("v"))
            num = isinstance(v, (int, float)) and not isinstance(v, bool)
            text = fmt(v, st.get("nf", "General")) if v is not None else ""
            if isinstance(v, str) and "f" in cell:
                text = tidy_text(text)
            css = _style_css(st, num) + _border_css(bd)
            cls = []
            if text and not num and not st.get("wrap") and (r, c) not in merges and (st.get("ha") or "left") in ("left", "general", ""):
                nxt = next((cc for cc in cols if cc > c), None)
                if nxt and f"{r},{nxt}" not in vals and (s["cells"].get(f"{r},{nxt}") or {}).get("v") in (None, "") and (r, nxt) not in covered:
                    cls.append("ov")                       # long text runs over the empty cell beside it, as in Excel
            attrs = ""
            # typed in: a cell with something in it, or an empty ruled cell of a table (an empty row to fill); never the
            # blank page around the tables
            if edit and (v not in (None, "") or (cell and any((st.get("bd") or [0, 0, 0, 0])))) and editable(model, s, k, inputs):
                raw = inp.get(k, cell.get("v") if "v" in cell else (("=" + cell["f"]) if "f" in cell else ""))
                if isinstance(raw, float) and raw.is_integer():
                    raw = int(raw)
                cls.append("ed" + (" ch" if k in inp else "") + (" n" if num else ""))
                attrs = f' data-k="{k}" data-raw="{escape(str(raw if raw is not None else ""), quote=True)}" data-nf="{escape(st.get("nf", "General"), quote=True)}"'
            if mark and k in mark:
                cls.append(mark[k])
            body_ = f"<span>{escape(text)}</span>" if "ov" in cls else escape(text)
            h.append(f'<td{span}{attrs}{(" class=" + chr(34) + " ".join(cls) + chr(34)) if cls else ""} style="{";".join(css)}">{body_}</td>')
        h.append("</tr>")
    h.append("</table>")
    # pictures where the consultant put them (logo, signatures); the company stamp at the bottom right - of each
    # printed page (preview_html / render_pdf draw it there), or under the sheet on screen
    from est_bills_engine import is_stamp, STAMP_PT
    st_im = None
    for im in s.get("images", []):
        if is_stamp(im):
            st_im = st_im or im
            continue
        if img_rows is not None and not _img_on(im, img_rows, s):
            continue
        pos = _img_box(im, cols, rows, colx, rowy, cw, rh, s)
        if not pos:
            continue
        x0, y0, w, hh = pos
        mime = "image/png" if im["ext"] == "png" else ("image/jpeg" if im["ext"] in ("jpg", "jpeg") else f"image/{im['ext']}")
        h.append(f'<img class="xi" src="data:{mime};base64,{im["data"]}" style="left:{x0}px;top:{y0}px;width:{w}px;height:{hh}px" alt="">')
    if st_im is not None and stamp == "below":
        sz = int(STAMP_PT * 4 / 3)
        h.append(f'<img class="xi" src="data:{_mime(st_im)};base64,{st_im["data"]}" style="left:{max(0, width - sz)}px;top:{height + 8}px;width:{sz}px;height:{sz}px" alt="">')
        h[0] = h[0].replace(f"height:{height}px", f"height:{height + sz + 12}px", 1)
        height += sz + 12
    h.append("</div>")
    return "".join(h), width, height


def _mime(im):
    return "image/png" if im["ext"] == "png" else ("image/jpeg" if im["ext"] in ("jpg", "jpeg") else f"image/{im['ext']}")


def _pos(idx, off, axis, cols, rows, colx, rowy, cw, rh, s):
    """Pixel position of a 0-based column/row index + EMU offset within the drawn area."""
    if axis == "x":
        c = idx + 1
        if c in colx:
            return colx[c] + min(off / EMU_PX, cw[c])
        before = [cc for cc in cols if cc < c]
        if not before:
            return off / EMU_PX - sum(colpx(s["colw"].get(str(cc), s["colw"].get(cc, s.get("dcw", 8.43)))) for cc in range(c, cols[0])) if cols else 0
        last = before[-1]
        return colx[last] + cw[last]
    r = idx + 1
    if r in rowy:
        return rowy[r] + min(off / EMU_PX, rh[r])
    before = [rr for rr in rows if rr < r]
    if not before:
        return -10 ** 6
    last = before[-1]
    return rowy[last] + rh[last]


def _img_box(im, cols, rows, colx, rowy, cw, rh, s):
    if not cols or not rows:
        return None
    if im["r"] + 1 > rows[-1] or im["c"] + 1 > cols[-1]:
        return None
    x0 = _pos(im["c"], im["dx"], "x", cols, rows, colx, rowy, cw, rh, s)
    y0 = _pos(im["r"], im["dy"], "y", cols, rows, colx, rowy, cw, rh, s)
    if y0 < -1000:
        return None
    if "c2" in im:
        x1 = _pos(im["c2"], max(0, im.get("dx2", 0)), "x", cols, rows, colx, rowy, cw, rh, s)
        y1 = _pos(im["r2"], max(0, im.get("dy2", 0)), "y", cols, rows, colx, rowy, cw, rh, s)
    else:
        x1, y1 = x0 + im.get("cx", 0) / EMU_PX, y0 + im.get("cy", 0) / EMU_PX
    w, hh = max(1, x1 - x0), max(1, y1 - y0)
    # the picture keeps its own shape (a logo is never squashed or stretched), inside the place it was given
    from est_bills_engine import _img_ratio
    if "_ratio" not in im:
        im["_ratio"] = _img_ratio(im)
    ratio = im["_ratio"] or (w / hh)
    nw, nh = (hh * ratio, hh) if w / hh > ratio else (w, w / ratio)
    nx, ny = x0 + (w - nw) / 2, y0 + (hh - nh) / 2
    if not im.get("sig"):
        # a logo sits in the middle of the merged cell it was put in (the heading band), as it should
        for m in s.get("merges") or []:
            r1, c1, r2, c2 = m
            if r1 <= im["r"] + 1 <= r2 and c1 <= im["c"] + 1 <= c2 and c1 in colx and c2 in colx and r1 in rowy and r2 in rowy:
                ax0, ax1 = colx[c1], colx[c2] + cw[c2]
                ay0, ay1 = rowy[r1], rowy[r2] + rh[r2]
                if ax1 - ax0 >= nw and x0 >= ax0 - 4 and x0 + w <= ax1 + 4:
                    nx = ax0 + (ax1 - ax0 - nw) / 2
                    if ay1 - ay0 >= nh and y0 >= ay0 - 4 and y0 + hh <= ay1 + 4:
                        ny = ay0 + (ay1 - ay0 - nh) / 2
                break
    return int(round(nx)), int(round(ny)), int(round(nw)), int(round(nh))


def _faces():
    """The fonts the consultants' sheets use, with free look-alikes of the same widths for computers without them
    (a Mac has no Calibri): text then sits in its cells exactly as in Excel."""
    out = []
    for fam, files in (("Calibri", "Carlito"), ("Cambria", "Caladea"), ("Arial", "LiberationSans"), ("Times New Roman", "LiberationSerif")):
        for w, st_, suf in (("400", "normal", "Regular"), ("700", "normal", "Bold"), ("400", "italic", "Italic"), ("700", "italic", "BoldItalic")):
            loc = fam + ("" if suf == "Regular" else " " + {"Bold": "Bold", "Italic": "Italic", "BoldItalic": "Bold Italic"}[suf])
            out.append(f'@font-face{{font-family:"{fam}";font-weight:{w};font-style:{st_};src:local("{loc}"),url(/portal/fonts/{files}-{suf}.ttf) format("truetype")}}')
    return "\n".join(out)


SHEET_CSS = _faces() + """
.xs{position:relative;font-family:Calibri,sans-serif;font-size:11pt;color:#000;background:#fff}
.xt{border-collapse:collapse;table-layout:fixed}
.xt td{padding:0 3px;overflow:hidden;white-space:nowrap;text-overflow:clip;line-height:1.15}
.xi{position:absolute;pointer-events:none}
.xt td.ov{overflow:visible}
.xt td.ov>span{position:relative;z-index:1}
"""


# ---------------------------------------------------------------------------------------------- the printed bill (HTML)

def shown_rows(model, sheet, inputs):
    from est_bills_engine import shown_rows as _s
    return _s(model, sheet, inputs)


def hidden_extra(inputs, sheet):
    from est_bills_engine import hidden_extra as _h
    return _h(inputs, sheet)


def _img_on(im, rows, s):
    """A picture belongs on the page that holds the row it is anchored to (or, anchored on a hidden row, the page
    the next shown row is on)."""
    r = im["r"] + 1
    if r in rows:
        return True
    hidden = set(s.get("hidden_rows") or [])
    while r in hidden:
        r += 1
    return r in rows


def printed_sheets(model):
    """The sheets that make up the bill: the visible ones, in the workbook's order."""
    return [s for s in model["sheets"] if s["visible"]]


def preview_html(model, values, title, pdf_url, excel_url, inputs=None, embed=False, fname=""):
    """The bill page by page exactly as it prints (and as the PDF comes out): each sheet on its own paper and
    orientation, at its print scale, margins and centring, broken where the consultant broke it, the heading rows
    repeated on every page, his header and footer on each page."""
    PX = 96 / 72
    from est_bills_engine import stamp_sheets, STAMP_PT
    sheets = printed_sheets(model)
    plans = [page_plan(model, sh, inputs) for sh in sheets]
    total = sum(len(pl["pages"]) for pl in plans)
    stamps = stamp_sheets(model)
    out, pno = [], 0
    for sh, pl in zip(sheets, plans):
        size = "a3" if max(pl["pw"], pl["ph"]) > 1000 else "a4"
        orient = "l" if pl["pw"] > pl["ph"] else "p"
        for prow, own in pl["pages"]:
            pno += 1
            body, w, hgt = sheet_html(model, sh, values, inputs, rows_only=prow, img_rows=set(prow), stamp=None)
            hf = []
            for k, t in pl["hf"].items():
                txt = escape(hf_text(t, pno, total, sh["name"], fname or title))
                if not txt:
                    continue
                pos = (f"top:{pl['mh'] * PX:.1f}px" if k[0] == "h" else f"bottom:{pl['mf'] * PX:.1f}px")
                side = {"l": f"left:{pl['ml'] * PX:.1f}px", "r": f"right:{pl['mr'] * PX:.1f}px", "c": "left:0;right:0;text-align:center"}[k[1]]
                hf.append(f'<div class="hf" style="{pos};{side}">{txt}</div>')
            if sh["name"] in stamps:                   # the company stamp: bottom right of every page, in the footer
                im = stamps[sh["name"]]
                hf.append(f'<img class="stp" src="data:{_mime(im)};base64,{im["data"]}" alt="" style="right:{pl["mr"] * PX:.1f}px;bottom:{pl["mf"] * PX:.1f}px;width:{STAMP_PT * PX:.1f}px;height:{STAMP_PT * PX:.1f}px">')
            out.append(f'<section class="pg {size}{orient}" style="width:{pl["pw"] * PX:.1f}px;height:{pl["ph"] * PX:.1f}px">'
                       f'<div class="pz" style="left:{pl["x0"] * PX:.1f}px;top:{pl["y0"] * PX:.1f}px"><div style="zoom:{pl["sc"]:.4f}">{body}</div></div>{"".join(hf)}'
                       f'<div class="pno">{pno} / {total}</div></section>')
    t = escape(title)
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{t}</title><style>
body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#E4E2DE;margin:0;color:#22262A}}
.bar{{position:sticky;top:0;z-index:5;background:#22262A;color:#fff;padding:9px 14px;display:flex;gap:8px;align-items:center}}
.bar b{{flex:1;font-size:13px}} .bar a,.bar button{{background:#C0392B;color:#fff;border:0;border-radius:6px;padding:7px 12px;font-weight:600;text-decoration:none;font-size:13px;cursor:pointer}}
.pages{{padding:16px 0 30px}}
.pg{{position:relative;background:#fff;margin:0 auto 18px;box-shadow:0 2px 12px rgba(0,0,0,.12);overflow:hidden;box-sizing:border-box}}
.pz{{position:absolute}}
.hf{{position:absolute;font:9pt Arial,Helvetica,sans-serif;color:#000;white-space:nowrap}}
.stp{{position:absolute;pointer-events:none}}
.pno{{position:absolute;right:8px;bottom:4px;font:10px Arial;color:#aaa}}
{SHEET_CSS}
@page a4p{{size:A4 portrait;margin:0}} @page a4l{{size:A4 landscape;margin:0}} @page a3p{{size:A3 portrait;margin:0}} @page a3l{{size:A3 landscape;margin:0}}
.a4p{{page:a4p}} .a4l{{page:a4l}} .a3p{{page:a3p}} .a3l{{page:a3l}}
@media print{{.bar,.pno{{display:none}} body{{background:#fff}} .pages{{padding:0}} .pg{{box-shadow:none;margin:0;break-after:page;zoom:1!important}} .xs,.xt td{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}}}
</style></head><body><div class="bar"><b>{t}</b><button onclick="print()">Print</button><a href="{pdf_url}">PDF</a><a href="{excel_url}">Excel</a><button onclick="shr()">Share</button></div>
<script>async function shr(){{try{{const r=await fetch("{pdf_url}");const b=await r.blob();const f=new File([b],{repr(re.sub(r'[^A-Za-z0-9]+', '_', title).strip('_') + '.pdf')},{{type:"application/pdf"}});if(navigator.canShare&&navigator.canShare({{files:[f]}}))await navigator.share({{files:[f],title:"{t}"}});else{{const a=document.createElement("a");a.href=URL.createObjectURL(b);a.download=f.name;a.click();}}}}catch(e){{}}}}
function fit(){{var W=document.documentElement.clientWidth-24;document.querySelectorAll(".pg").forEach(function(p){{var w=parseFloat(p.style.width);p.style.zoom=w>W?(W/w).toFixed(4):"";}});}}
addEventListener("resize",fit);addEventListener("DOMContentLoaded",fit);</script>
<div class="pages">{''.join(out)}</div>{"<style>.bar{display:none}</style>" if embed else ""}</body></html>"""


# ---------------------------------------------------------------------------------------------- PDF

PAPER = {9: (595.28, 841.89), 8: (841.89, 1190.55), 1: (612.0, 792.0), 5: (612.0, 1008.0), 11: (419.53, 595.28)}


def page_plan(model, s, inputs=None):
    """The sheet's printed pages as Excel prints them: its paper and orientation, its scale (or fit to page),
    margins and centring, the rows repeated at the top of every page, its manual page breaks, and new pages where
    the rows run past the bottom. pages: [(rows drawn, the page's own rows)]. Sizes in points."""
    pr = s.get("print") or {"paper": 9, "landscape": s.get("landscape"), "fit": s.get("fit"), "fw": 1, "fh": 0, "scale": 100,
                             "m": [.7, .7, .75, .75, .3, .3], "hc": False, "vc": False, "titles": None, "breaks": [], "hf": {}}
    w, h = PAPER.get(pr.get("paper") or 9, PAPER[9])
    pw, ph = (h, w) if pr.get("landscape") else (w, h)
    ml, mr, mt, mb, mh, mf = [float(x) * 72 for x in (pr.get("m") or [.7, .7, .75, .75, .3, .3])]
    cols, rows, cw, rh, merges, covered = layout(s, None, shown_rows(model, s["name"], inputs), hidden_extra(inputs, s["name"]))
    px = 0.75
    cont_w = sum(cw[c] for c in cols) * px
    cont_h = sum(rh[r] for r in rows) * px
    aw, ah = pw - ml - mr, ph - mt - mb
    if pr.get("fit") and not (pr.get("scale") and pr["scale"] != 100):
        fw = 1 if pr.get("fw") is None else pr["fw"]
        fh = 1 if pr.get("fh") is None else pr["fh"]
        sc = 1.0
        if fw and cont_w:
            sc = min(sc, aw * fw / cont_w)
        if fh and cont_h:
            sc = min(sc, ah * fh / cont_h)
    else:
        # a fit-to-page sheet keeps the scale Excel worked out for it when it was saved - the scale the consultant's
        # own print came out at, so the pages break where his did
        sc = (pr.get("scale") or 100) / 100.0
    if cont_w and cont_w * sc > aw + mr * 0.8:         # never cut columns off: shrink to the page width
        sc = aw / cont_w
    sc = max(sc, 0.1)
    t = pr.get("titles")
    titles = [r for r in rows if t and t[0] <= r <= t[1]]
    tset = set(titles)
    breaks = set(pr.get("breaks") or [])
    # The consultant set his page breaks (or a short sheet) to fill whole pages. Excel prints a little smaller than
    # the screen sizes suggest, so a block that comes out only slightly too long is brought onto its page by
    # printing the sheet a touch smaller - never a near-empty extra page with one or two rows on it.
    segs, cur_h, first = [], 0.0, True
    for r in rows:
        cur_h += rh[r] * px
        if r in breaks:
            segs.append(cur_h); cur_h = 0.0
    segs.append(cur_h)
    tpt = sum(rh[r] for r in titles) * px
    need = sc
    for i, hseg in enumerate(segs):
        full = hseg + (tpt if i and titles else 0)
        if full * sc > ah and full * sc <= ah * 1.12:
            need = min(need, ah / full)
    sc = max(need, sc * 0.88)
    th = tpt * sc
    pages, cur, own, used = [], [], [], 0.0
    for r in rows:
        if pages and r in tset:
            continue                                    # repeated rows are already at the top of this page
        hgt = rh[r] * px * sc
        if own and used + hgt > ah + 0.5:
            pages.append((cur, own)); cur, own, used = list(titles), [], th
        cur.append(r); own.append(r); used += hgt
        if r in breaks:
            pages.append((cur, own)); cur, own, used = list(titles), [], th
    if own:
        pages.append((cur, own))
    cw_pt = cont_w * sc
    x0 = ml + ((aw - cw_pt) / 2 if pr.get("hc") else 0)
    x0 = max(ml * 0.2, min(x0, pw - mr * 0.2 - cw_pt)) if cw_pt > aw else x0
    return {"pw": pw, "ph": ph, "ml": ml, "mr": mr, "mt": mt, "mb": mb, "mh": mh, "mf": mf, "sc": sc, "x0": x0, "y0": mt,
            "cols": cols, "cw": cw, "rh": rh, "merges": merges, "covered": covered, "pages": pages, "hf": pr.get("hf") or {},
            "vc": pr.get("vc")}


def hf_text(t, page, pages, sheet, title):
    """An Excel header/footer section with its codes filled in: &P page, &N pages, &A sheet, &F / &Z file, &D date."""
    import datetime as _d
    t = re.sub(r'&"[^"]*"', "", t)
    t = re.sub(r"&\d+", "", t)
    t = t.replace("&&", "\x00")
    t = (t.replace("&P", str(page)).replace("&N", str(pages)).replace("&A", sheet).replace("&F", title).replace("&Z", "")
          .replace("&D", _d.date.today().strftime("%d/%m/%Y")).replace("&T", ""))
    t = re.sub(r"&[A-Za-z]", "", t).replace("\x00", "&")
    return " ".join(t.split())


_PDF_FONTS = None


def _pdf_fonts():
    """The same look-alike fonts in the PDF (portal/fonts), so its text has Excel's widths."""
    global _PDF_FONTS
    if _PDF_FONTS is not None:
        return _PDF_FONTS
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "portal", "fonts")
    ok = True
    try:
        for fam in ("Carlito", "Caladea", "LiberationSans", "LiberationSerif"):
            for suf in ("Regular", "Bold", "Italic", "BoldItalic"):
                pdfmetrics.registerFont(TTFont(f"{fam}-{suf}", os.path.join(d, f"{fam}-{suf}.ttf")))
    except Exception:
        ok = False
    _PDF_FONTS = ok
    return ok


def render_pdf(model, values, title, inputs=None, fname=""):
    """Each printed sheet on A4 (landscape when the sheet is), scaled to the page width as Excel's 'fit to page'
    does, rows carried onto the next page when they run past the bottom."""
    from reportlab.lib.pagesizes import A4, landscape as LS
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    cv = canvas.Canvas(buf, pagesize=A4)
    cv.setTitle(title)
    styles = model["styles"]
    M = 28.0                                         # margin, points

    fams = _pdf_fonts()
    from est_bills_engine import stamp_sheets, STAMP_PT, is_stamp
    stamps = stamp_sheets(model)

    def font(st):
        b, i = st.get("b"), st.get("i")
        n = (st.get("font") or "Calibri").lower()
        fam = "Carlito" if "calibri" in n or not n.strip() else ("Caladea" if "cambria" in n else ("LiberationSerif" if SERIF.search(n) else "LiberationSans"))
        if fams:
            return f"{fam}-" + ("BoldItalic" if b and i else "Bold" if b else "Italic" if i else "Regular")
        if fam in ("Caladea", "LiberationSerif"):
            return "Times-BoldItalic" if b and i else ("Times-Bold" if b else ("Times-Italic" if i else "Times-Roman"))
        return "Helvetica-BoldOblique" if b and i else ("Helvetica-Bold" if b else ("Helvetica-Oblique" if i else "Helvetica"))

    def rgb(hexs):
        try:
            return tuple(int(hexs[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
        except Exception:
            return (0, 0, 0)

    plans = [page_plan(model, sh, inputs) for sh in printed_sheets(model)]
    total_pages = sum(len(pl["pages"]) for pl in plans)
    pno = 0
    for s, pl in zip(printed_sheets(model), plans):
        vals = values.get(s["name"], {})
        cols, cw, rh, merges, covered = pl["cols"], pl["cw"], pl["rh"], pl["merges"], pl["covered"]
        if not cols or not pl["pages"]:
            continue
        PW, PH = pl["pw"], pl["ph"]
        px, sc = 0.75, pl["sc"]
        colx, x = {}, 0.0
        for c in cols:
            colx[c] = x; x += cw[c] * px * sc
        for pi, (prow, own) in enumerate(pl["pages"]):
            pno += 1
            cv.setPageSize((PW, PH))
            M = pl["x0"]                               # left edge of the sheet on the page (margin, or centred)
            TOP = PH - pl["y0"]
            rowy, y = {}, TOP
            for r in prow:
                rowy[r] = y; y -= rh[r] * px * sc
            pset = set(prow)
            # fills and text
            for r in prow:
                for c in cols:
                    if (r, c) in covered:
                        continue
                    k = f"{r},{c}"
                    cell = s["cells"].get(k) or {}
                    st = styles[cell.get("s", 0)] if styles else {}
                    x0 = M + colx[c]
                    w = cw[c] * px * sc
                    top = rowy[r]
                    hgt = rh[r] * px * sc
                    if (r, c) in merges:
                        mr2, mc2 = merges[(r, c)]
                        w = sum(cw[cc] * px * sc for cc in cols if c <= cc <= mc2)
                        hgt = sum(rh[rr] * px * sc for rr in prow if r <= rr <= mr2)
                    if st.get("fill"):
                        cv.setFillColorRGB(*rgb(st["fill"])); cv.rect(x0, top - hgt, w, hgt, stroke=0, fill=1)
                    v = vals.get(k, cell.get("v"))
                    if v is None or v == "":
                        continue
                    num = isinstance(v, (int, float)) and not isinstance(v, bool)
                    text = fmt(v, st.get("nf", "General"))
                    if isinstance(v, str) and "f" in cell:
                        text = tidy_text(text)
                    if not text:
                        continue
                    fs = max(4.0, (st.get("sz") or 11) * sc)
                    fn = font(st)
                    cv.setFillColorRGB(*(rgb(st["fc"]) if st.get("fc") else (0, 0, 0)))
                    ha = {"centerContinuous": "center", "general": ""}.get(st.get("ha") or "", st.get("ha") or "") or ("right" if num else "left")
                    pad = 2.0 * sc + (st.get("ind") or 0) * 6 * sc
                    if st.get("wrap") and not num:
                        lines = _wrap(text, fn, fs, w - 2 * pad, stringWidth)
                    else:
                        lines = text.split("\n")
                    if len(lines) > 1 and fs * 1.15 * len(lines) > hgt - 1:
                        one = " ".join(x.strip() for x in lines)
                        if stringWidth(one, fn, fs) <= w - 2 * pad:
                            lines = [one]                                  # fits on one line: as the screen shows it
                        else:
                            fs = max(3.5, (hgt - 1) / (1.15 * len(lines)))  # wrapped text kept inside its cell
                    lh = fs * 1.15
                    block = lh * len(lines)
                    va = st.get("va") or "bottom"
                    if va == "top":
                        ty = top - fs - 1 * sc
                    elif va == "center":
                        ty = top - (hgt - block) / 2 - fs * 0.95
                    else:
                        ty = top - hgt + block - fs * 0.95 - 0.8 * sc
                        ty = min(ty, top - fs)
                    cv.setFont(fn, fs)
                    # long text that is not wrapped runs over the empty cells to its right, as Excel shows it
                    room = w
                    if not st.get("wrap") and not num and (r, c) not in merges and ha == "left":
                        cc_ = c
                        for nxt in cols[cols.index(c) + 1:]:
                            if f"{r},{nxt}" in vals or (s["cells"].get(f"{r},{nxt}") or {}).get("v") not in (None, "") or (r, nxt) in covered:
                                break
                            room += cw[nxt] * px * sc
                    if num and lines and stringWidth(lines[0], fn, fs) > w - 2 * pad and w > 4:
                        fs = max(3.5, fs * (w - 2 * pad) / stringWidth(lines[0], fn, fs))   # a figure always shows whole
                        cv.setFont(fn, fs)
                    for ln in lines:
                        tw = stringWidth(ln, fn, fs)
                        if ha == "right":
                            tx = x0 + w - pad - tw
                        elif ha in ("center", "distributed"):
                            tx = x0 + (w - tw) / 2
                        else:
                            tx = x0 + pad
                        if tw > room - pad and ha == "left":
                            # clip text that would run past its room
                            cv.saveState(); p = cv.beginPath(); p.rect(x0, top - hgt, room, hgt); cv.clipPath(p, stroke=0, fill=0)
                            cv.drawString(tx, ty, ln); cv.restoreState()
                        else:
                            cv.drawString(tx, ty, ln)
                        ty -= lh
            # borders (a merged block shows only its outer edges, as Excel draws it)
            cv.setStrokeColorRGB(0, 0, 0)
            inblock = {}
            for (mr1, mc1), (mr2, mc2) in merges.items():
                for rr in range(mr1, mr2 + 1):
                    for cc in range(mc1, mc2 + 1):
                        inblock[(rr, cc)] = (mr1, mc1, mr2, mc2)
            for r in prow:
                for c in cols:
                    cell = s["cells"].get(f"{r},{c}") or {}
                    bd = (styles[cell.get("s", 0)].get("bd") if styles else None) or [0, 0, 0, 0]
                    if not any(bd):
                        continue
                    blk = inblock.get((r, c))
                    x0 = M + colx[c]; w = cw[c] * px * sc; top = rowy[r]; hgt = rh[r] * px * sc
                    for side, wd in zip(("l", "r", "t", "b"), bd):
                        if not wd:
                            continue
                        if blk and ((side == "l" and c != blk[1]) or (side == "r" and c != blk[3]) or (side == "t" and r != blk[0]) or (side == "b" and r != blk[2])):
                            continue
                        cv.setLineWidth({1: 0.5, 2: 1.1, 3: 1.6}.get(wd, 0.5) * max(sc, 0.6))
                        if side == "l":
                            cv.line(x0, top, x0, top - hgt)
                        elif side == "r":
                            cv.line(x0 + w, top, x0 + w, top - hgt)
                        elif side == "t":
                            cv.line(x0, top, x0 + w, top)
                        else:
                            cv.line(x0, top - hgt, x0 + w, top - hgt)
            # pictures
            pxcolx = {c: colx[c] / (px * sc) for c in cols}
            for im in s.get("images", []):
                if is_stamp(im) or not _img_on(im, set(prow), s):
                    continue
                rowy_px = {r: (TOP - rowy[r]) / (px * sc) for r in prow}
                cwp = {c: cw[c] for c in cols}
                rhp = {r: rh[r] for r in prow}
                box = _img_box(im, cols, prow, pxcolx, rowy_px, cwp, rhp, s)
                if not box:
                    continue
                bx, by, bw, bh = box
                try:
                    img = ImageReader(io.BytesIO(base64.b64decode(im["data"])))
                    cv.drawImage(img, M + bx * px * sc, TOP - (by + bh) * px * sc, bw * px * sc, bh * px * sc, mask="auto", preserveAspectRatio=False)
                except Exception:
                    pass
            if s["name"] in stamps:                     # the company stamp: bottom right of every page, in the footer
                try:
                    img = ImageReader(io.BytesIO(base64.b64decode(stamps[s["name"]]["data"])))
                    cv.drawImage(img, PW - pl["mr"] - STAMP_PT, pl["mf"], STAMP_PT, STAMP_PT, mask="auto", preserveAspectRatio=True)
                except Exception:
                    pass
            # the sheet's own header and footer (Page 1 of 9, sheet name ...), at the consultant's margins
            for k, t in pl["hf"].items():
                txt = hf_text(t, pno, total_pages, s["name"], fname or title)
                if not txt:
                    continue
                cv.setFont("Helvetica", 8); cv.setFillColorRGB(0, 0, 0)
                yy = PH - pl["mh"] - 8 if k[0] == "h" else pl["mf"]
                if k[1] == "l":
                    cv.drawString(pl["ml"], yy, txt)
                elif k[1] == "r":
                    cv.drawRightString(PW - pl["mr"], yy, txt)
                else:
                    cv.drawCentredString(PW / 2, yy, txt)
            cv.showPage()
    cv.save()
    buf.seek(0)
    return buf


def _wrap(text, fn, fs, width, sw):
    out = []
    for para in str(text).split("\n"):
        words, cur = para.split(" "), ""
        for w in words:
            t = (cur + " " + w).strip()
            if sw(t, fn, fs) <= width or not cur:
                cur = t
            else:
                out.append(cur); cur = w
        out.append(cur)
    return out

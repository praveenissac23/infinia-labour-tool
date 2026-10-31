"""Word (.docx) and the lines the browser already sends (portal/est/agreement.js) into the layout model."""
import io
import re

from .model import Cell, Doc, Region, Row


def read_docx(data, name=""):
    from docx import Document
    d = Document(io.BytesIO(data))
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    rows = []
    body = d.element.body
    y = 0
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    for el in body.iterchildren():
        tag = el.tag.replace(W, "")
        if tag == "p":
            t = re.sub(r"\s+", " ", Paragraph(el, d).text).strip()
            if t:
                y += 1
                # a paragraph with tab stops is laid out like cells ("Contract Sum:<tab>AED 1,250,000")
                parts = [p.strip() for p in re.split(r"\t+", Paragraph(el, d).text) if p.strip()]
                cells = [Cell(text=p, x0=i * 10, x1=i * 10 + 9, y0=y - 1, y1=y, page=1, src=f"para {y}") for i, p in enumerate(parts or [t])]
                rows.append(Row(cells=cells, page=1, y=y))
        elif tag == "tbl":
            tbl = Table(el, d)
            for ri, tr in enumerate(tbl.rows):
                y += 1
                cells, seen, x = [], set(), 0
                for ci, tc in enumerate(tr.cells):
                    span = 1
                    if id(tc._tc) in seen:
                        cells[-1].x1 += 10
                        continue
                    seen.add(id(tc._tc))
                    t = re.sub(r"\s+", " ", tc.text).strip()
                    cells.append(Cell(text=t, x0=ci * 10, x1=ci * 10 + 10 * span - 1, y0=y - 1, y1=y, page=1, src=f"table row {ri + 1}", col=ci + 1))
                cells = [c for c in cells if c.text]
                if cells:
                    rows.append(Row(cells=cells, page=1, y=y))
    return Doc(regions=[Region(name="Document", page=1, rows=rows, kind="docx")], kind="docx", name=name)


def from_lines(lines, name=""):
    """The browser's lines ({p, y, c: [cells], x: [starts], xe: [ends], ocr}) -> the layout model, so documents
    already read on a computer can go through the same reader."""
    pages = {}
    for k, l in enumerate(lines or []):
        if not l:
            continue
        cs = l.get("c") or [l.get("t", "")]
        xs, xe = l.get("x"), l.get("xe")
        p = int(l.get("p") or 1)
        y = float(l.get("y") if l.get("y") is not None else k)
        cells = []
        for j, t in enumerate(cs):
            t = re.sub(r"\s+", " ", str(t or "")).strip()
            if not t:
                continue
            if isinstance(xs, list) and isinstance(xe, list) and len(xs) == len(cs) and len(xe) == len(cs):
                x0, x1 = float(xs[j]), float(xe[j])
            elif isinstance(xs, list) and len(xs) == len(cs):
                # only where each cell starts: it ends about a letter-width per letter later, before the next cell
                x0 = float(xs[j])
                x1 = x0 + 4.6 * max(1, len(t))
                if j + 1 < len(xs) and float(xs[j + 1]) > x0:
                    x1 = min(x1, float(xs[j + 1]) - 2)
            else:
                x0, x1 = float(j), float(j + 1)
            src = f"{l.get('sheet')}!row {k + 1}" if l.get("sheet") else f"p{p}"
            cells.append(Cell(text=t, x0=x0, x1=x1, y0=y, y1=y + float(l.get("h") or 1), page=p, src=src, conf=0.8 if l.get("ocr") else 1.0,
                              col=(j + 1) if not isinstance(xs, list) else None))
        if cells:
            pages.setdefault(p, []).append(Row(cells=cells, page=p, y=y, ocr=bool(l.get("ocr"))))
    grid = not any(isinstance(l.get("x"), list) for l in (lines or []) if l)
    regions = [Region(name=f"Page {p}", page=p, rows=rows, kind="grid" if grid else "page") for p, rows in sorted(pages.items())]
    doc = Doc(regions=regions, kind="lines", name=name)
    doc.ocr_pages = sorted({r.page for reg in regions for r in reg.rows if r.ocr})
    return doc

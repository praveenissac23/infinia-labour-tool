"""Typed PDFs into the layout model: every word with its box (pdfplumber), put into lines by height and into cells
by the gaps between words and the table rules drawn on the page. A page with no text layer (a scan inside the PDF)
is sent to text recognition (ocr.py) - page by page, so a PDF mixing typed and scanned pages reads both.
"""
import io

from .model import Cell, Doc, Region, Row, Word


def words_to_rows(words, page, rules=None, ocr=False, src="", gap_k=0.9):
    """Words -> lines -> cells. Two words stay in one cell when the gap between them is small (a space) and no
    column rule runs between them; a figure column is its own cell."""
    rules = rules or []
    words = [w for w in words if w.text.strip()]
    words.sort(key=lambda w: ((w.y0 + w.y1) / 2, w.x0))
    lines = []
    for w in words:
        h = max(1.0, w.y1 - w.y0)
        cy = (w.y0 + w.y1) / 2
        best = None
        for ln in lines[-6:]:
            lh = max(1.0, ln["y1"] - ln["y0"])
            ov = min(ln["y1"], w.y1) - max(ln["y0"], w.y0)
            if ov >= 0.45 * min(h, lh) and abs(cy - ln["cy"]) <= 0.6 * max(h, lh):
                if best is None or abs(cy - ln["cy"]) < abs(cy - best["cy"]):
                    best = ln
        if best is None:
            lines.append({"y0": w.y0, "y1": w.y1, "cy": cy, "w": [w]})
        else:
            best["w"].append(w)
            n = len(best["w"])
            best["cy"] = (best["cy"] * (n - 1) + cy) / n
            best["y0"], best["y1"] = min(best["y0"], w.y0), max(best["y1"], w.y1)
    lines.sort(key=lambda ln: ln["cy"])
    rows = []
    for ln in lines:
        ws = sorted(ln["w"], key=lambda w: w.x0)
        hs = sorted(w.y1 - w.y0 for w in ws)
        h = hs[len(hs) // 2] if hs else 8
        cells, cur = [], None
        for w in ws:
            split = cur is None
            if cur is not None:
                gap = w.x0 - cur["x1"]
                if gap > max(3.0, h * gap_k):
                    split = True
                elif any(cur["x1"] - 1 <= rx <= w.x0 + 1 and ry0 <= ln["cy"] <= ry1 for rx, ry0, ry1 in rules):
                    split = True
            if split:
                cur = {"w": [w], "x0": w.x0, "x1": w.x1}
                cells.append(cur)
            else:
                cur["w"].append(w)
                cur["x1"] = max(cur["x1"], w.x1)
        out = []
        for c in cells:
            text = " ".join(w.text for w in c["w"])
            conf = min(w.conf for w in c["w"])
            out.append(Cell(text=text, x0=c["x0"], x1=c["x1"], y0=min(w.y0 for w in c["w"]), y1=max(w.y1 for w in c["w"]),
                            page=page, src=src or f"p{page}", conf=conf, words=list(c["w"])))
        rows.append(Row(cells=out, page=page, y=ln["cy"], ocr=ocr))
    return rows


def _rules(page):
    """Vertical rules drawn on the page (table column lines): (x, y0, y1)."""
    out = []
    try:
        for e in page.edges:
            if e.get("orientation") == "v" and (e["bottom"] - e["top"]) > 6:
                out.append((e["x0"], e["top"], e["bottom"]))
    except Exception:
        pass
    return out


def read_pdf(data, name="", ocr=True, dpi=300, parallel=2):
    import pdfplumber
    regions, scanned = [], []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for i, page in enumerate(pdf.pages):
            pn = i + 1
            try:
                ws = page.extract_words(x_tolerance=1.5, y_tolerance=2.5, keep_blank_chars=False, use_text_flow=False)
            except Exception:
                ws = []
            chars = sum(len(w["text"]) for w in ws)
            if chars < 25:
                scanned.append(pn)
                regions.append(Region(name=f"Page {pn}", page=pn, rows=[], kind="scan", width=float(page.width), height=float(page.height)))
                continue
            words = [Word(w["text"], float(w["x0"]), float(w["top"]), float(w["x1"]), float(w["bottom"])) for w in ws]
            rows = words_to_rows(words, pn, _rules(page))
            regions.append(Region(name=f"Page {pn}", page=pn, rows=rows, kind="page", width=float(page.width), height=float(page.height)))
    doc = Doc(regions=regions, kind="pdf", name=name)
    if scanned and ocr:
        from .ocr import ocr_pdf_pages
        got = ocr_pdf_pages(data, scanned, dpi=dpi, parallel=parallel)
        for r in doc.regions:
            if r.page in got:
                r.rows = got[r.page]
        doc.ocr_pages = scanned
        if len(scanned) == len(regions):
            doc.kind = "scan"
    elif scanned:
        doc.notes.append(f"{len(scanned)} page(s) have no text layer (scanned) and were not read.")
    return doc

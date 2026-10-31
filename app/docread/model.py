"""One layout model for every kind of file.

A document is a list of regions (an Excel sheet, a PDF page, a scanned page, a Word body). A region is a list of
rows in reading order; a row is a list of cells left to right. Every cell knows where it came from:

  * x0, x1   - its horizontal extent. Excel: column numbers (a merged cell spans several); PDF: points; scan: pixels
               scaled to points. Used to put a figure under its column heading.
  * y0, y1   - its vertical extent (Excel: row numbers).
  * src      - "Sheet1!E14" for Excel, "p2" for a page (the bbox says where on it).
  * num      - the number Excel stored in the cell (its cached value), with its number format in `fmt`.
  * conf     - how sure the text recognition was (1.0 for typed text and Excel).
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Word:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    conf: float = 1.0


@dataclass
class Cell:
    text: str
    x0: float
    x1: float
    y0: float
    y1: float
    page: int                       # region number, 1-based
    src: str = ""                   # "Sheet!B12" or "p3"
    num: Optional[float] = None     # Excel's own number (cached value)
    fmt: str = ""                   # Excel number format ("0.00%", "#,##0;(#,##0)")
    formula: str = ""
    conf: float = 1.0
    words: List[Word] = field(default_factory=list)
    col: Optional[int] = None       # Excel column (1-based) of the cell's top-left
    is_date: bool = False

    @property
    def xc(self):
        return (self.x0 + self.x1) / 2

    def bbox(self):
        return [round(self.x0, 1), round(self.y0, 1), round(self.x1, 1), round(self.y1, 1)]

    def where(self):
        """Where the figure is, for the confirm screen: {"page":, "ref": "Sheet!E14"} or {"page":, "bbox": [...]}."""
        if "!" in self.src:
            return {"page": self.page, "ref": self.src}
        return {"page": self.page, "bbox": self.bbox()}


@dataclass
class Row:
    cells: List[Cell]
    page: int
    y: float
    idx: int = 0                    # position in the document (all regions run together)
    ocr: bool = False

    @property
    def text(self):
        return "  ".join(c.text for c in self.cells if c.text)


@dataclass
class Region:
    name: str
    page: int
    rows: List[Row]
    kind: str = "page"              # "sheet" | "page" | "scan" | "docx"
    width: float = 0.0
    height: float = 0.0
    vrules: list = field(default_factory=list)   # vertical table rules (x, y0, y1) on a page
    hrules: list = field(default_factory=list)   # horizontal table rules (y, x0, x1) on a page


@dataclass
class Doc:
    regions: List[Region]
    kind: str                       # "xlsx" | "xls" | "pdf" | "scan" | "image" | "docx" | "lines"
    name: str = ""
    notes: List[str] = field(default_factory=list)
    timing: dict = field(default_factory=dict)
    ocr_pages: List[int] = field(default_factory=list)

    def rows(self):
        out = []
        for r in self.regions:
            out.extend(r.rows)
        for i, r in enumerate(out):
            r.idx = i
        return out

    @property
    def ocr(self):
        return bool(self.ocr_pages)

    def text(self):
        return "\n".join(r.text for r in self.rows())


def merge_bands(region):
    """A table cell whose words wrap onto two or three lines is one cell: lines that sit between the same two
    horizontal rules of a ruled table are put together, column by column (the description's lines joined, the
    figures beside them kept)."""
    ys = sorted({round(y, 1) for y, x0, x1 in region.hrules if x1 - x0 > 40})
    clean = []
    for y in ys:
        if not clean or y - clean[-1] > 3:
            clean.append(y)
    if len(clean) < 3 or not region.rows:
        return region
    import bisect
    out, band = [], []

    def flush():
        if not band:
            return
        if len(band) == 1:
            out.append(band[0])
            return
        cells = []
        for r in band:
            for c in r.cells:
                hit = None
                for m in cells:
                    ov = min(m.x1, c.x1) - max(m.x0, c.x0)
                    if ov > 0.3 * min(m.x1 - m.x0, c.x1 - c.x0) or (ov > -4 and not any(ch.isdigit() for ch in c.text + m.text)):
                        hit = m
                        break
                if hit is None:
                    cells.append(Cell(text=c.text, x0=c.x0, x1=c.x1, y0=c.y0, y1=c.y1, page=c.page, src=c.src, num=c.num, fmt=c.fmt,
                                      conf=c.conf, words=list(c.words)))
                else:
                    hit.text = (hit.text + " " + c.text).strip()
                    hit.x0, hit.x1 = min(hit.x0, c.x0), max(hit.x1, c.x1)
                    hit.y0, hit.y1 = min(hit.y0, c.y0), max(hit.y1, c.y1)
                    hit.conf = min(hit.conf, c.conf)
                    hit.words += c.words
        anchor = max(band, key=lambda r: len(r.cells))
        out.append(Row(cells=sorted(cells, key=lambda c: c.x0), page=anchor.page, y=anchor.y, ocr=anchor.ocr))
    key = None
    for r in sorted(region.rows, key=lambda r: r.y):
        k = bisect.bisect_left(clean, r.y)
        inside = 0 < k < len(clean) and clean[k] - clean[k - 1] <= 70
        if inside and k == key:
            band.append(r)
            continue
        flush()
        band = [r] if inside else []
        if not inside:
            out.append(r)
        key = k if inside else None
    flush()
    region.rows = out
    return region

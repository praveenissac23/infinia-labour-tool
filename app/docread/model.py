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

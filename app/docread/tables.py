"""Table understanding: which rows are column headings, and under which heading each figure stands.

A heading can be two or three rows deep ("Total Work Done" over "Previous | Current | Total"); every heading row
above a figure that overlaps it horizontally adds its meaning, the lowest (most specific) one winning. A figure
belongs to a heading when their horizontal extents overlap (figures are right-aligned, headings centred - they
still overlap); Excel columns overlap a merged heading spanning them.
"""
import re
from dataclasses import dataclass, field
from typing import List, Optional

from .model import Row
from .numparse import numbers
from .vocab import col_roles

CUR_WORD = r"\b(?:AED|A\.E\.D|Dhs?\.?|DHS|Dirhams?)(?=[\s\d(.\-/]|$)"
HEAD_ROLES = ("p", "t", "c", "pct", "amount", "contract", "qty", "rate", "desc", "claimed", "certified", "remarks", "unit")


@dataclass
class Tok:
    """One figure on a row."""
    value: float
    pct: bool
    x0: float
    x1: float
    cell: object
    k: int                      # its order on the row (0 = leftmost figure)
    in_label: bool = False      # written inside the label's text ("Retention 10%")
    raw: bool = False
    fixed: bool = False
    money_like: bool = True
    role: str = ""              # p / t / c / pct / contract / qty / rate / amount / "" (no heading)
    role_score: float = 0.0
    head: str = ""

    @property
    def key(self):
        return (id(self.cell), self.k)


@dataclass
class RowInfo:
    row: object
    label: str
    toks: List[Tok] = field(default_factory=list)
    header: Optional[dict] = None   # for heading rows: [(cell, roles)]
    grid: bool = False              # rows are spreadsheet rows (y = row number), not points on a page


def cell_numbers(c, ocr):
    """Figures in a cell: Excel's own number when it has one, else read from the text."""
    t = c.text.strip()
    if c.num is not None and not c.is_date:
        pct = "%" in (c.fmt or "")
        v = c.num * 100 if pct else c.num
        return [(v, pct, 0, len(t), True, False, True)]
    if re.fullmatch(r"[-–—]+|nil|n/?a", t, re.I):
        return [(0.0, False, 0, len(t), False, False, True)]
    out = []
    for n in numbers(t, ocr=ocr or c.conf < 1.0):
        out.append((n.value, n.pct, n.start, n.end, False, n.fixed, n.money_like))
    return out


def _span_x(c, a, b):
    """The horizontal extent of characters a..b of a cell's text (from its words when known)."""
    if not c.words or len(c.words) == 1:
        if c.words and len(c.text) > 0:
            w = c.x1 - c.x0
            return c.x0 + w * a / len(c.text), c.x0 + w * b / len(c.text)
        return c.x0, c.x1
    pos, xs = 0, []
    for w in c.words:
        s, e = pos, pos + len(w.text)
        if e > a and s < b:
            xs.append((w.x0, w.x1))
        pos = e + 1
    if not xs:
        return c.x0, c.x1
    return min(x for x, _ in xs), max(x for _, x in xs)


def analyse(doc):
    """Every row -> RowInfo (its label, its figures); heading rows are marked."""
    infos = []
    for reg in doc.regions:
        for row in reg.rows:
            ocr = row.ocr
            toks, label_parts, seen_fig = [], [], False
            k = 0
            for c in row.cells:
                nums = cell_numbers(c, ocr)
                money = [n for n in nums if (n[6] or n[4]) and not n[1]]
                txt = c.text
                letters = re.sub(CUR_WORD + r"|[\d.,()%\-\s:]", "", txt, flags=re.I)
                is_label = len(letters) >= 3 and not c.num is not None
                if is_label:
                    # a label cell: its own figures are percentages ("Retention 10%") or a figure after the words
                    if not seen_fig:
                        label_parts.append(txt)
                    for v, pct, a, b, raw, fixed, ml in nums:
                        tail = txt[b:].strip()
                        if pct or (ml and not re.search(r"[A-Za-z]{3,}", tail)):
                            x0, x1 = _span_x(c, a, b)
                            toks.append(Tok(v, pct, x0, x1, c, k, in_label=not seen_fig and pct, raw=raw, fixed=fixed, money_like=ml))
                            k += 1
                            if not pct:
                                seen_fig = True
                    continue
                for v, pct, a, b, raw, fixed, ml in nums:
                    x0, x1 = (c.x0, c.x1) if raw else _span_x(c, a, b)
                    toks.append(Tok(v, pct, x0, x1, c, k, raw=raw, fixed=fixed, money_like=ml or raw))
                    k += 1
                if money:
                    seen_fig = True
            label = " ".join(label_parts).strip()
            kvcells = [c for c in row.cells if re.search(r"[A-Za-z]{3}", re.sub(CUR_WORD, "", c.text, flags=re.I)) and c.num is None and
                       re.search(r"[\d)]\s*-?\s*(AED)?\s*$", c.text) and any((n[6] and not n[1]) for n in cell_numbers(c, ocr))]
            if len(kvcells) >= 2:
                # "Retention: 12,345.00   Advance recovered: 6,789.00" - each cell is its own line
                for c in kvcells:
                    sub = Row(cells=[c], page=row.page, y=row.y, ocr=row.ocr)
                    ns = [n for n in cell_numbers(c, ocr) if n[6] and not n[1]]
                    v, pct, a, b, raw, fixed, ml = ns[-1]
                    x0, x1 = _span_x(c, a, b)
                    st = [Tok(v, pct, x0, x1, c, 0, raw=raw, fixed=fixed, money_like=ml)]
                    for n in cell_numbers(c, ocr):
                        if n[1]:
                            st.append(Tok(n[0], True, c.x0, c.x1, c, 1, in_label=True))
                    infos.append(RowInfo(row=sub, label=c.text[:a].strip(" :-"), toks=st, grid=reg.kind in ("sheet", "docx", "grid")))
                continue
            ri = RowInfo(row=row, label=label, toks=toks, grid=reg.kind in ("sheet", "docx", "grid"))
            # a heading row: two or more cells that read as column headings, figures few
            heads = []
            for c in row.cells:
                if c.num is not None or any(n[6] and not n[1] for n in cell_numbers(c, ocr)):
                    continue
                r = col_roles(c.text)
                words = re.sub(r"\((aed|dhs?|%)\)", "", c.text, flags=re.I).split()
                if r and len(c.text) <= 48 and len(words) <= 6:
                    heads.append((c, r))
            money_toks = [t for t in toks if not t.pct and t.money_like and abs(t.value) >= 1]
            strong = [h for h in heads if set(h[1]) & {"p", "t", "c", "pct", "qty", "rate", "contract", "claimed", "certified"} and len(h[0].text) <= 25]
            filled = [c for c in row.cells if c.text.strip()]
            mostly = len(heads) >= max(2, 0.6 * len(filled)) or (strong and len(filled) <= 2 and len(heads) == len(filled))
            if not money_toks and mostly:
                ri.header = heads
            infos.append(ri)
    # a heading row must have figures under it: within the next few rows, a figure standing under one of its
    # headings ("Contract Value: Re-measurable ..." is a label, not a table heading)
    for i, ri in enumerate(infos):
        if ri.header is None:
            continue
        ok, seen = False, 0
        for o in infos[i + 1:]:
            if o.row.page != ri.row.page:
                break
            if o.header is not None:
                continue
            seen += 1
            if seen > 5:
                break
            for t in o.toks:
                if t.pct and not any("pct" in r for _, r in ri.header):
                    continue
                if any(min(c.x1, t.x1) - max(c.x0, t.x0) > 0 for c, _ in ri.header):
                    ok = True
                    break
            if ok:
                break
        if not ok:
            # a heading directly over another heading row passes on to it
            nxt = infos[i + 1] if i + 1 < len(infos) else None
            if not (nxt is not None and nxt.header is not None and nxt.row.page == ri.row.page):
                ri.header = None
    return infos


def assign_roles(infos, max_gap_rows=40, max_gap_pt=600):
    """Each figure gets the column heading above it."""
    by_page = {}
    for i, ri in enumerate(infos):
        by_page.setdefault(ri.row.page, []).append(i)
    for page, idxs in by_page.items():
        last_heads = []          # the heading block in force: list of (row index, heads)
        last_y, pitch = None, []
        for i in idxs:
            ri = infos[i]
            if ri.header is not None:
                # a heading row directly under another heading row deepens it; otherwise it starts a new block
                if last_heads and _close(infos[last_heads[-1][0]].row, ri.row, ri.grid):
                    last_heads.append((i, ri.header))
                else:
                    last_heads = [(i, ri.header)]
                    pitch = []
                last_y = ri.row.y
                continue
            if not last_heads:
                continue
            top = infos[last_heads[-1][0]].row
            if _far(top, ri.row, ri.grid, max_gap_rows, max_gap_pt):
                last_heads = []
                continue
            # the table ends: a gap well over its line spacing, or a label running across the figure columns
            dy = ri.row.y - (last_y if last_y is not None else top.y)
            if not ri.grid and pitch and dy > 1.6 * sorted(pitch)[len(pitch) // 2] + 2:
                last_heads = []
                continue
            if ri.grid and dy > 2.5:
                last_heads = []
                continue
            fig_heads = [c for _, hs in last_heads for c, r in hs if set(r) & {"p", "t", "c", "amount", "contract"}]
            lab = next((c for c in ri.row.cells if re.search(r"[A-Za-z]{3}", c.text) and c.num is None), None)
            if lab is not None and fig_heads and ri.grid and any(min(lab.x1, h.x1) - max(lab.x0, h.x0) > 0.5 for h in fig_heads) \
                    and lab.x0 < min(h.x0 for h in fig_heads):
                last_heads = []
                continue
            if last_y is not None and dy > 0:
                pitch.append(dy)
            last_y = ri.row.y
            for t in ri.toks:
                if t.in_label:
                    continue
                roles, heads_txt = {}, []
                for _, heads in last_heads:          # top heading row first; lower rows override
                    best, bo = None, 0.0
                    for c, r in heads:
                        ov = min(c.x1, t.x1) - max(c.x0, t.x0)
                        if ov > bo:
                            best, bo = (c, r), ov
                    if best is None:
                        # no overlap: the nearest heading within half a column
                        for c, r in heads:
                            d = abs(c.xc - (t.x0 + t.x1) / 2)
                            lim = 0.6 if ri.grid else max(20, (c.x1 - c.x0))
                            if d < lim and (best is None or d < abs(best[0].xc - (t.x0 + t.x1) / 2)):
                                best = (c, r)
                    if best:
                        heads_txt.append(best[0].text)
                        for k, s in best[1].items():
                            roles[k] = s
                        # a more specific row below replaces p/t/c of the row above
                        if set(best[1]) & {"p", "t", "c"}:
                            for k in ("p", "t", "c"):
                                if k not in best[1]:
                                    roles.pop(k, None)
                if not roles:
                    continue
                t.head = " / ".join(heads_txt)
                if "pct" in roles and not t.pct and (abs(t.value) <= 1.0 or "%" in t.head):
                    t.role, t.role_score = "pct", roles["pct"]
                elif any(k in roles for k in ("p", "t", "c")):
                    k = max(("p", "t", "c"), key=lambda k: roles.get(k, 0))
                    t.role, t.role_score = k, roles[k]
                elif "contract" in roles:
                    t.role, t.role_score = "contract", roles["contract"]
                elif "qty" in roles or "rate" in roles:
                    t.role, t.role_score = ("qty" if roles.get("qty", 0) >= roles.get("rate", 0) else "rate"), 0.9
                elif "amount" in roles or "claimed" in roles or "certified" in roles:
                    t.role, t.role_score = "amount", 0.7
                    if "claimed" in roles and "certified" not in roles:
                        t.role = "claimed"
                    if "certified" in roles and "claimed" not in roles and roles["certified"] >= 0.6:
                        t.role = "certified"
    return infos


def _close(a, b, grid):
    if a.page != b.page:
        return False
    return abs(b.y - a.y) <= (2 if grid else 28)


def _far(a, b, grid, rows, pts):
    if a.page != b.page:
        return True
    return abs(b.y - a.y) > (rows if grid else pts)

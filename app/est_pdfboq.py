"""A priced BOQ that is only a PDF (or a scan) - read as fully as the Excel (5 Nov 2026).

The page is put back into rows and columns from where its words sit: the column headings on each page (ITEM | WORK
DESCRIPTION | UNIT | QTY | UNIT RATE | AMOUNT, or a certificate's % columns) give the columns; a description wrapped
over several lines (lines close together) is one row; the figures of a long item, printed half-way down its words, go
with it; a figure line between items (the lump sum of a bracket: "LS 10,800.00" among "Clean Out ... No") stays a row
of its own. The rows are then read by the same reader as the Excel (est_itemimport) - page totals, the collection,
the summary sheet and items priced together as one lump sum, with the same checks.

  to_workbook(lines) -> xlsx bytes, or None when the file has no BOQ table (an agreement's letter pages ...)
  read(lines)        -> est_itemimport.read_schedule(...), or None
"""
import io
import re

import openpyxl

NUM = re.compile(r"^\(?-?[\d,]+(?:\.\d+)?\)?%?$")
CODE = re.compile(r"^(?:[A-Z]{1,3}\)?|\(?[A-Za-z]\)|\d{1,3}(?:\.\d{1,3}){0,3}\.?|[A-Z]{1,2}[-.]?\d{1,3}(?:\.\d{1,3}){0,2}|[ivx]{1,4}\))$")
FOOT = re.compile(r"^page\s+\d+\s+(?:of\s+\d+)?$|^\S+\.(?:xlsx?|pdf)$", re.I)
UNITW = {"ls", "l.s", "l.s.", "lumpsum", "lump sum", "no", "no.", "nos", "nos.", "item", "items", "set", "sets", "m", "lm", "rm", "m2", "sqm",
         "m3", "cum", "kg", "ton", "pair", "lot", "unit", "units", "nr", "each", "job", "pcs"}
FIGW = {"ls", "l.s", "lump sum", "lumpsum", "included", "incl", "inc", "excluded", "excl", "n.a", "na", "n/a", "nil", "rate only",
        "by others", "by client", "provisional", "p.s", "ps", "free", "foc", "optional"}
HEADWORDS = re.compile(r"description|amount|rate|qty|quantity|unit|item|previous|current|cumulative|total|work done|%|\(aed\)|aed|s\.?\s*no|ref", re.I)


def _cells(l):
    return [(x, (l.get("xe") or [None] * len(l["c"]))[i] or (x + 6 * len(c)), c.strip()) for i, (x, c) in enumerate(zip(l["x"], l["c"])) if c.strip()]


def _num(t):
    t = t.replace(",", "").strip()
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()")
    try:
        v = float(t.rstrip("%"))
    except ValueError:
        return None
    if t.endswith("%"):
        v = v / 100.0
    return -v if neg else v


SPLITHEAD = re.compile(r"\s(?=(?:amount|qty|quantity|total)\b)|(?<!unit)\s(?=rate\b)|\s(?=unit\s+rate\b)|\s(?=unit\b(?!\s*rate))|\s(?=description\b)", re.I)


def _header_cols(hlines):
    """Columns from the heading lines of a page: [(centre, label)] left to right. Headings printed close together
    and taken as one piece ("UNIT RATE AMOUNT (AED)") are parted where each heading starts."""
    cs = []
    for l in hlines:
        for x, xe, c in _cells(l):
            cuts = [0] + [m.end() for m in SPLITHEAD.finditer(c)] + [len(c) + 1]
            parts = [(cuts[i], c[cuts[i]:cuts[i + 1]].strip()) for i in range(len(cuts) - 1)]
            parts = [(i, t) for i, t in parts if t]
            if len(parts) > 1 and not re.search(r"work\s+description|unit\s+rate$", c, re.I) or len(parts) > 2:
                w = (xe - x) / max(len(c), 1)
                for i, t in parts:
                    cs.append((x + w * (i + len(t) / 2.0), x + w * i, x + w * (i + len(t)), t, l["y"]))
                continue
            cs.append(((x + xe) / 2.0, x, xe, c, l["y"]))
    cs.sort()
    cols = []
    for ctr, x, xe, c, y in cs:
        if cols and (min(cols[-1]["xe"], xe) - max(cols[-1]["x"], x) > 2 or abs(cols[-1]["ctr"] - ctr) < 8):   # one heading over two lines
            cols[-1]["parts"].append((y, c))
            cols[-1]["x"], cols[-1]["xe"] = min(cols[-1]["x"], x), max(cols[-1]["xe"], xe)
        else:
            cols.append({"ctr": ctr, "x": x, "xe": xe, "parts": [(y, c)]})
    for c in cols:
        c["label"] = " ".join(t for _, t in sorted(c["parts"]))
    return cols


def _page_header(plines):
    """The heading lines of a page (the line with DESCRIPTION and the lines just above / below it that are headings)."""
    hit = next((l for l in plines if any(re.search(r"description", c, re.I) for c in l["c"])
                and any(HEADWORDS.search(c) for c in l["c"] if not re.search(r"description", c, re.I))), None)
    if hit is None:
        hit = next((l for l in plines if any(re.search(r"description", c, re.I) for c in l["c"])), None)
    if hit is None:
        return None, None
    y0 = hit["y"]
    hs = [l for l in plines if abs(l["y"] - y0) <= 26 and all(HEADWORDS.search(c) and len(c) < 45 for c in l["c"] if c.strip())]
    labels = " ".join(c for l in hs for c in l["c"])
    if not re.search(r"amount|rate|total", labels, re.I):
        return None, None
    return hs, max(l["y"] for l in hs)


def _sig(cols):
    return tuple(re.sub(r"[^a-z%]", "", c["label"].lower())[:12] for c in cols)


def _same_rows(pl):
    """Lines a few points apart whose pieces do not overlap are one row of the table ("13,500.00" and "LS" of one item)."""
    out = []
    for l in pl:
        o = out[-1] if out else None
        if o is not None and abs(l["y"] - o["y"]) <= 5:
            a, b = _cells(o), _cells(l)
            if not any(x < xe2 and x2 < xe for x, xe, _ in a for x2, xe2, _ in b):
                cs = sorted(a + b)
                out[-1] = dict(o, c=[c for _, _, c in cs], x=[x for x, _, _ in cs], xe=[xe for _, xe, _ in cs])
                continue
        out.append(l)
    return out


def _brackets(s):
    """Items priced together as one lump sum. In the Excel the lump sum is one cell merged down beside them; the PDF
    prints it once, half-way down the run (on a line of its own, or on the middle item's line). Put it back on the
    first item and merge it down the run again, so the reader sees what it sees in the Excel.
    -> [(first row, last row, column)]"""
    rows, di, cols = s["rows"], s["di"], s["cols"]
    price = [k for k, c in enumerate(cols) if k > di and re.search(r"rate|amount|price|total", c["label"], re.I)]
    uq = [k for k, c in enumerate(cols) if k > di and k not in price]
    has = lambda r, ks: any(r[k] not in (None, "") for k in ks)
    code = lambda r: bool(di and r[0] not in (None, ""))
    unit_only = lambda r: bool(r[di]) and has(r, uq) and not has(r, price)
    plain = lambda r: bool(r[di]) and not code(r) and not has(r, uq) and not has(r, price)
    rate = next((k for k in price if re.search(r"rate|price", cols[k]["label"], re.I)), None)
    total = re.compile(r"collection|carried|^\s*(sub[- ]?)?total\b|brought\s+forward", re.I)

    def carrier(k):
        r = rows[k]
        if not has(r, price) or total.search(str(r[di] or "")):
            return False
        if not r[di] and not code(r) and not has(r, uq):
            return True                                # the lump sum on a line of its own
        # on an item's own line: the lump sum printed half-way down a run of items with a unit and no price of their
        # own (the merge runs on below the last item, so it can fall on the last one) - never an item priced by quantity
        lump = (rate is not None and isinstance(r[rate], str)) or not any(isinstance(r[c], (int, float)) and r[c] > 0 for c in uq)
        return bool(r[di]) and lump and k > 0 and unit_only(rows[k - 1])

    # an item's figures on a line of their own just under its words ("Item 1 8,100.00 8,100.00"): one row, as in the Excel
    for k in range(1, len(rows)):
        r, o = rows[k], rows[k - 1]
        if not r[di] and not code(r) and has(r, uq) and plain(o):
            for c in uq + price:
                o[c] = r[c]
            r[:] = [None] * len(r)
    rows[:] = [r for r in rows if any(v not in (None, "") for v in r)]
    merges, drop, used, k = [], set(), set(), 0
    pv = lambda r: tuple(r[c] for c in price)
    while k < len(rows):
        if not carrier(k):
            k += 1
            continue
        r, key = rows[k], pv(rows[k])
        alone = not r[di] and not code(r) and not has(r, uq)

        def again(j, near=True):
            """The same lump sum printed again where the bracket runs over a page (at the foot of one page, on the next):
            right next to its items - or, past other words, only when it is a sum of money ("Included" is too common)."""
            o = rows[j]
            return j != k and has(o, price) and pv(o) == key and (near or any(isinstance(v, (int, float)) and v > 0 for v in key)) \
                and not total.search(str(o[di] or "")) and (
                not o[di] or (rate is not None and isinstance(o[rate], str)) or not any(isinstance(o[c], (int, float)) and o[c] > 0 for c in uq))
        member = lambda j, near=True: j not in used and (unit_only(rows[j]) or again(j, near))
        a = k
        while a - 1 >= 0 and member(a - 1):
            a -= 1
        if a == k and alone:                           # printed under the words at the foot of a page: the items above them
            j = k - 1
            while j >= 0 and j not in used and plain(rows[j]) and k - j <= 4:
                j -= 1
            if 0 <= j < k - 1 and member(j, False):
                a = j
                while a - 1 >= 0 and member(a - 1):
                    a -= 1
        b = k
        while True:
            while b + 1 < len(rows) and member(b + 1):
                b += 1
            j = b + 1                                  # words between items of the bracket stay in it - unless the items
            while j < len(rows) and plain(rows[j]):    # after them are a bracket of their own
                j += 1
            if j == b + 1 or j >= len(rows) or not member(j, False):
                break
            e = j
            while e < len(rows) and (member(e, False) or plain(rows[e])):
                e += 1
            if e < len(rows) and carrier(e):
                break
            b = j
        dups = [j for j in range(a, b + 1) if again(j)]
        dups = [j for j in dups if again(j, False) or any(abs(j - m) == 1 and not plain(rows[m]) for m in range(a, b + 1))]
        gone = {j for j in [k] + dups if not rows[j][di] and not code(rows[j]) and not has(rows[j], uq)}
        run = [j for j in range(a, b + 1) if j not in gone]
        if not run:
            k += 1
            continue
        for j in dups:
            for c in price:
                rows[j][c] = None
        move = [c for c in uq + price if r[c] not in (None, "") and all(rows[j][c] in (None, "") for j in run if j != k)]
        if alone:
            move = [c for c in move if c in price or not any(rows[j][c] not in (None, "") for j in run)]
        top = run[0]
        for c in move:
            v = r[c]
            r[c] = None
            rows[top][c] = v
            if len(run) > 1:
                merges.append((top, run[-1], c))
        drop |= gone
        used.update(range(a, b + 1))
        k = b + 1
    if drop:
        keep = [j for j in range(len(rows)) if j not in drop]
        pos = {j: n for n, j in enumerate(keep)}
        def shift(j, up):
            while j not in pos:
                j += -1 if up else 1
            return pos[j]
        merges = [(shift(a, False), shift(b, True), c) for a, b, c in merges]
        s["rows"] = [rows[j] for j in keep]
    return merges


def to_workbook(lines):
    pages = {}
    for l in lines or []:
        if l.get("c"):
            pages.setdefault(l["p"], []).append(l)
    sheets, cur, last_sig = [], None, None
    for p in sorted(pages):
        pl = _same_rows(sorted([l for l in pages[p] if not FOOT.match(" ".join(l["c"]).strip())], key=lambda l: l["y"]))
        hs, hbot = _page_header(pl)
        if hs is None:
            continue
        cols = _header_cols(hs)
        di = next((i for i, c in enumerate(cols) if re.search(r"description", c["label"], re.I)), None)
        if di is None or len(cols) < 3:
            continue
        sig = _sig(cols)
        if cur is None or len(sig) != len(last_sig) or cur.get("ended"):
            cur = {"cols": cols, "di": di, "rows": [], "name": "", "ended": False, "coll": False}
            sheets.append(cur)
        last_sig = sig
        cols, di = cur["cols"], cur["di"]
        right = cols[di + 1:]
        bounds = [(right[k]["ctr"] + right[k + 1]["ctr"]) / 2.0 for k in range(len(right) - 1)]
        desc_left = cols[di]["x"] - 200
        item_cols = cols[:di]

        def col_of(ctr):
            k = 0
            while k < len(bounds) and ctr > bounds[k]:
                k += 1
            return di + 1 + k

        # figures stand to the right of their column: placed by where they end, against where the headings end
        ends = [(right[k]["xe"] + right[k + 1]["xe"]) / 2.0 for k in range(len(right) - 1)]

        def col_end(xe):
            k = 0
            while k < len(ends) and xe > ends[k]:
                k += 1
            return di + 1 + k

        # each line: its item code, its words, its figures (column -> value)
        items = []
        hy = min(l["y"] for l in hs)
        unit_left0 = right[0]["x"] - 8 if right else 10 ** 6
        xs = [round(x) for l in pl if l["y"] > hbot for x, xe, c in _cells(l) if x < unit_left0 and len(c) > 12]
        desc_x = max(set(xs), key=xs.count) if xs else cols[di]["x"]
        for l in pl:
            if l["y"] <= hbot or l["y"] < hy:
                continue
            txt = " ".join(l["c"]).strip()
            if FOOT.match(txt):
                continue
            code, words, figs, we, notes = "", [], {}, 0, {}
            unit_left = unit_left0
            for x, xe, c in _cells(l):
                ctr = (x + xe) / 2.0
                toks = c.split()
                if len(toks) >= 2 and right and x >= unit_left - 4 and len(toks) <= len(right) and (
                        all(_num(t) is not None for t in toks) or all(_num(t) is not None or t.lower().strip(". ") in UNITW for t in toks)):
                    # figures run together in one piece ("5,400.00 5,400.00"): the last is the right-most column it reaches
                    k = col_end(xe)
                    for t in reversed(toks):                   # ("- -": noughts)
                        if k > di:
                            figs.setdefault(k, t)
                        k -= 1
                    continue
                if right and (ctr >= unit_left or (x >= unit_left - 4)):
                    if _num(c) is not None:
                        figs.setdefault(col_end(xe), c)
                    elif c.lower().strip(". ") in UNITW or c.lower().strip(". ") in FIGW or re.match(r"^[-–—.\s]+$", c):
                        figs.setdefault(col_of(ctr), c)
                    else:                                      # a remark written in a figure column ("Only water supply ...")
                        notes[col_of(x + 4)] = c
                elif not words and not code and item_cols and CODE.match(c) and x < desc_x - 4 and len(c) <= 6:
                    code = c
                else:
                    words.append(c)
                    we = max(we, xe)
            items.append({"y": l["y"], "h": l.get("h") or 10.0, "code": code, "words": " ".join(words).strip(), "figs": figs, "we": we, "notes": notes})
        wmax = max([it["we"] for it in items] or [0])
        # rows: words close together are one description; the figures half-way down it go with it
        rows = []
        for it in items:
            if not it["words"] and not it["code"]:
                continue
            last = rows[-1] if rows else None
            gap = it["y"] - last["y1"] if last else 999
            # the line before ran to the edge of the column (the words wrapped) and the next is close under it
            wrapped = last and last["we"] >= wmax - 0.3 * (wmax - cols[di]["x"] + 40)
            caps = lambda t: bool(re.search(r"[A-Z]", t)) and not re.search(r"[a-z]", t)
            heading = last and caps(last["words"]) and not caps(it["words"])     # "LIGHT FITTINGS ..." over "Supply, Install ..."
            if last and not it["code"] and (gap <= 1.12 * it["h"] or (wrapped and not heading and gap <= 1.4 * it["h"])) \
                    and (not it["figs"] or not last["figs"]) and last["words"]:
                last["words"] += " " + it["words"]
                last["y1"] = it["y"]
                last["we"] = it["we"]
                for k, v in it["figs"].items():
                    last["figs"].setdefault(k, v)
                continue
            rows.append({"y0": it["y"], "y1": it["y"], "code": it["code"], "words": it["words"], "figs": dict(it["figs"]), "we": it["we"]})
        for it in items:
            if it["words"] or it["code"] or not it["figs"]:
                continue
            host = next((r for r in rows if r["y0"] - 3 <= it["y"] <= r["y1"] + 3 and not r["figs"] and r["y1"] > r["y0"]), None)
            if host is None:
                host = next((r for r in rows if abs(r["y0"] - it["y"]) <= 3 and not r["figs"]), None)
            if host is not None:
                host["figs"] = dict(it["figs"])
            else:
                rows.append({"y0": it["y"], "y1": it["y"], "code": "", "words": "", "figs": dict(it["figs"])})
        rows.sort(key=lambda r: r["y0"])
        for it in items:                                       # remarks go with the row they sit beside, as in the Excel
            for k, v in it["notes"].items():
                near = [r for r in rows if r["words"] or r["code"]]
                if not near:
                    continue
                host = min(near, key=lambda r: 0 if r["y0"] - 3 <= it["y"] <= r["y1"] + 3 else min(abs(r["y0"] - it["y"]), abs(r["y1"] - it["y"])))
                host.setdefault("notes", {}).setdefault(k, []).append(v)
        # a description that runs over the page break: the page's first words go on with the last row of the page before
        prev = cur["rows"][-1] if cur["rows"] else None
        if rows and prev is not None and prev[di] and not rows[0]["code"] and rows[0]["words"][:1].islower():
            prev[di] = prev[di] + " " + rows[0]["words"]
            for k, v in rows[0]["figs"].items():
                if prev[k] in (None, ""):
                    n = _num(v)
                    prev[k] = n if n is not None else v
            rows = rows[1:]
        for r in rows:
            out = [None] * len(cols)
            if item_cols and r["code"]:
                out[0] = r["code"]
            out[di] = r["words"] or None
            for k, v in r["figs"].items():
                n = _num(v)
                if n is None and re.match(r"^[-–—\s]+$", v.strip()):
                    n = 0.0                                    # a nought shown as "-" (the accounting format)
                out[k] = n if n is not None else v
            for k, v in (r.get("notes") or {}).items():
                if out[k] in (None, ""):
                    out[k] = " ".join(v)
            cur["rows"].append(out)
            w = (r["words"] or "").strip()
            if re.match(r"^collection$", w, re.I):
                cur["coll"] = True
            m = re.search(r"^(.*?)\bbill\s*page\b", w, re.I)
            if m and not cur["name"]:
                cur["name"] = re.sub(r"[^A-Za-z ]", " ", m.group(1)).strip().upper()
            if cur["coll"] and re.search(r"^(total\s+)?carried\s+to\s+collection|^total\b", w, re.I) and not re.search(r"systems?$", w, re.I):
                cur["ended"] = True                            # the sheet's collection closed: the next pages are the next sheet
    if not any(s["rows"] for s in sheets):
        return None
    for s in sheets:
        s["merges"] = _brackets(s)
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    used = set()
    for n, s in enumerate(sheets, 1):
        if not s["rows"]:
            continue
        name = s["name"] or ("SUMMARY" if s["coll"] and not any(re.search(r"bill\s*page", str(r[s["di"]] or ""), re.I) for r in s["rows"]) else f"Sheet {n}")
        name = name[:28]
        while name in used:
            name += "_"
        used.add(name)
        ws = wb.create_sheet(name)
        ws.append([c["label"] for c in s["cols"]])
        for r in s["rows"]:
            ws.append(r)
        for a, b, k in s["merges"]:
            ws.merge_cells(start_row=a + 2, start_column=k + 1, end_row=b + 2, end_column=k + 1)
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


class NotTable(Exception):
    """A PDF / scan with no BOQ table in it (the 422 the upload falls back on: the agreement reader reads it instead)."""


def workbook_of(data, name=""):
    """An uploaded file -> the xlsx bytes of its BOQ table; None when it is not a PDF or an image; NotTable when it is
    one but no priced table (ITEM / DESCRIPTION ... AMOUNT) is in it, or this server cannot read it now."""
    import est_fileread as F
    try:
        from docread.load import sniff
        kind = sniff(data, name)
    except Exception:
        kind = ""
    if kind not in ("pdf", "image"):
        return None
    try:
        doc = F.load_doc(data, name)
        lines = F.old_lines(data, name, doc)
    except F.Unavailable as e:
        raise NotTable(str(e))
    wb = to_workbook(lines)
    if wb is None:
        raise NotTable("No priced table (DESCRIPTION ... AMOUNT columns) was found in this file.")
    return wb


def read(lines):
    import est_itemimport
    data = to_workbook(lines)
    if data is None:
        return None
    try:
        return est_itemimport.read_schedule(data)
    except ValueError:
        return None

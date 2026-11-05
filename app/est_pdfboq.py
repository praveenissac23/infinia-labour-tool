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


SPLITHEAD = re.compile(r"(?<!total)(?<!contract)\s(?=(?:amount|value)\b)|\s(?=(?:qty|quantity|quantities|uom|u/m|particulars|details|remarks)\b)|(?<!total)\s(?=total\b)"
                       r"|(?<!unit)(?<!total)\s(?=(?:rate|price)\b)|\s(?=unit\s+(?:rate|price)\b)|\s(?=unit\b(?!\s*(?:rate|price)))|(?<!item)(?<!work)(?<!of)\s(?=description\b)", re.I)


_HW = r"(?:rate|unit|amount|qty|quantity|price|total|description|uom|remarks?|value|aed)\b"


def _unstick(c):
    """Two headings printed touching: "(Approx.)U/M", "QtyRATE", "QtyRate"."""
    c = re.sub(r"\)(?=[A-Za-z])", ") ", c)
    c = re.sub(r"(?<=[a-z.])(?=[A-Z]{2,})", " ", c)
    return re.sub(r"(?<=[a-z])(?=[A-Z][a-z]+)", lambda m: " " if re.match(_HW, c[m.start():], re.I) else "", c)


def _headish(c):
    """A piece of a heading row: a column heading of any wording (the same words the Excel reader knows), or a unit
    line under one ("(AED)")."""
    import est_itemimport as I
    t = _unstick(c.strip())
    if not t or len(t) > 45:
        return False
    if re.fullmatch(r"[\(\[]?\s*(aed|dhs?|qr|usd|%|nos?\.?)\s*[\)\]]?", t, re.I):
        return True
    if NUM.match(t):
        return False
    if I._role(I._hk(t)):
        return True
    parts = [p for p in SPLITHEAD.split(t) if p.strip()] or [t]
    return all(re.fullmatch(r"est\.?|approx\.?|estimated|\(?aed\)?|of|no\.?", p.strip(), re.I) or I._role(I._hk(p)) or re.fullmatch(r"quantity|quantities|rate\s*\(?aed\)?|amount\s*\(?aed\)?|supply|install(ation)?|material|labou?r|total|fixing",
                                                   p.strip(), re.I) for p in parts)


def _role_of(label):
    import est_itemimport as I
    return I._role(I._hk(label))


def _header_cols(hlines):
    """Columns from the heading lines of a page, left to right: the line with the most headings gives the columns;
    a heading on another line over one column is part of its name ("UNIT RATE" / "(AED)"), over several the name of
    them all ("QUANTITY" over Qty | Unit), over none a column of its own. Headings printed close together and taken
    as one piece ("UNIT RATE AMOUNT (AED)") are parted where each heading starts."""
    pieces = []
    for l in hlines:
        for x, xe, c in _cells(l):
            c = _unstick(c)                                  # "(Approx.)U/M", "QtyRATE": two headings printed touching
            if l.get("hdr"):
                pieces.append((l["y"], x, xe, c))
                continue
            cuts = [0] + [m.end() for m in SPLITHEAD.finditer(c)] + [len(c) + 1]
            parts = [(cuts[i], c[cuts[i]:cuts[i + 1]].strip()) for i in range(len(cuts) - 1)]
            parts = [(i, t) for i, t in parts if t]
            # a word that is no heading by itself goes with the heading after it ("Estimated" + "Qty")
            j = 0
            while j < len(parts) - 1:
                if not _role_of(parts[j][1]) and not re.fullmatch(r"\(?aed\)?|quantity|quantities|rate\s*\(?aed\)?", parts[j][1], re.I):
                    parts[j:j + 2] = [(parts[j][0], parts[j][1] + " " + parts[j + 1][1])]
                else:
                    j += 1
            if len(parts) > 1 and not re.search(r"work\s+description|unit\s+rate$", c, re.I) or len(parts) > 2:
                w = (xe - x) / max(len(c), 1)
                for i, t in parts:
                    pieces.append((l["y"], x + w * i, x + w * (i + len(t)), t))
                continue
            pieces.append((l["y"], x, xe, c))
    if not pieces:
        return []
    ys = {}
    for y, x, xe, c in pieces:
        ys.setdefault(y, []).append((x, xe, c))
    base_y = max(ys, key=lambda y: (len(ys[y]), -y))
    cols = [{"x": x, "xe": xe, "parts": [(base_y, c)], "parents": []} for x, xe, c in sorted(ys[base_y])]
    for y in sorted(k for k in ys if k != base_y):
        for x, xe, c in sorted(ys[y]):
            over = [col for col in cols if min(col["xe"], xe) - max(col["x"], x) > 2]
            if not over:
                near = [col for col in cols if abs((col["x"] + col["xe"]) / 2 - (x + xe) / 2) < 8]
                over = near[:1]
            base_role = _role_of(" ".join(t for _, t in over[0]["parts"])) if len(over) == 1 else None
            if len(over) == 1 and base_role and _role_of(c) and _role_of(c) != base_role:
                over[0]["parents"].append((y, c))           # "QUANTITY" printed over "UOM" only: a parent heading
            elif len(over) == 1:
                over[0]["parts"].append((y, c))
                over[0]["x"], over[0]["xe"] = min(over[0]["x"], x), max(over[0]["xe"], xe)
            elif len(over) > 1:
                for col in over:
                    col["parents"].append((y, c))           # "QUANTITY" over Qty | Unit
            else:
                cols.append({"x": x, "xe": xe, "parts": [(y, c)], "parents": []})
    cols.sort(key=lambda c: c["x"])
    for c in cols:
        c["ctr"] = (c["x"] + c["xe"]) / 2.0
        own = " ".join(t for _, t in sorted(c["parts"]))
        par = " ".join(t for _, t in sorted(c["parents"]))
        c["label"] = own
        ro = _role_of(own)
        # the heading over several columns names them only where their own heading needs it: "RATE (AED)" over
        # Supply | Install | Total; "QUANTITY" over UOM | Qty says nothing more
        if par and (ro is None or (re.fullmatch(r"total|supply|install(ation)?|material|labou?r|fixing", own.strip(), re.I)
                                   and _role_of(par) in ("rate", "price"))):
            c["label"] = f"{par} {own}"
        c["role"] = _role_of(c["label"]) or ro
    return cols


def _line_headish(l):
    """A heading line: its pieces are headings (a word between them - "Item Ref Item Description" - is allowed)."""
    cs = [c for c in l["c"] if c.strip()]
    if not cs:
        return False
    if all(_headish(c) for c in cs):
        return True
    if any(NUM.match(c.strip().replace(" ", "")) for c in cs if len(c.strip()) > 2):
        return False
    good = sum(len(c) for c in cs if _headish(c) or any(_headish(p) for p in SPLITHEAD.split(_unstick(c)) if p.strip()))
    return len(cs) >= 3 and good >= 0.8 * sum(len(c) for c in cs)


def _page_header(plines):
    """The heading lines of a page: a line whose pieces are all headings, with a description heading and a price
    heading among it and the heading lines next to it (any wording - Description / Particulars / Scope of Work ...)."""
    for k, l in enumerate(plines):
        if not _line_headish(l):
            continue
        hs = [o for o in plines if abs(o["y"] - l["y"]) <= 26 and _line_headish(o)]
        cols = _header_cols(hs)
        roles = {c["role"] for c in cols}
        if "desc" in roles and roles & {"amount", "rate", "price"} and len(cols) >= 3:
            return hs, max(o["y"] for o in hs)
    return None, None


def _sig(cols):
    return tuple(re.sub(r"[^a-z%]", "", c["label"].lower())[:12] for c in cols)


def _same_rows(pl):
    """Lines a few points apart whose pieces do not overlap are one row of the table ("13,500.00" and "LS" of one item)."""
    out = []
    for l in pl:
        o = out[-1] if out else None
        if o is not None and abs(l["y"] - o["y"]) <= 0.42 * max(l.get("h") or 10.0, o.get("h") or 10.0):
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
    price = [k for k, c in enumerate(cols) if k > di and (c.get("role") in ("rate", "amount", "price", "cert_amt") or re.search(r"rate|amount|price|total", c["label"], re.I))]
    uq = [k for k, c in enumerate(cols) if k > di and k not in price]
    has = lambda r, ks: any(r[k] not in (None, "") for k in ks)
    code = lambda r: bool(di and r[0] not in (None, ""))
    # "LS" alone in the rate column of an item (the merged rate cell printed at the foot of the bracket): an item of
    # the bracket all the same - its "LS" belongs to the bracket's line
    ls_word = lambda v: isinstance(v, str) and v.strip().lower().strip(".") in ("ls", "l.s", "lump sum", "lumpsum", "l/s")
    ls_only = lambda r: has(r, price) and all(r[c] in (None, "") or ls_word(r[c]) for c in price)
    unit_only = lambda r: bool(r[di]) and has(r, uq) and (not has(r, price) or ls_only(r))
    plain = lambda r: bool(r[di]) and not code(r) and not has(r, uq) and not has(r, price)
    rate = next((k for k in price if cols[k].get("role") == "rate" or re.search(r"rate|price", cols[k]["label"], re.I)), None)
    total = re.compile(r"collection|carried|^\s*(sub[- ]?)?total\b|brought\s+forward", re.I)

    def carrier(k):
        r = rows[k]
        if not has(r, price) or total.search(str(r[di] or "")) or ls_only(r):
            return False
        if not r[di] and not code(r) and not has(r, uq):
            return True                                # the lump sum on a line of its own
        # on an item's own line: the lump sum printed half-way down a run of items with a unit and no price of their
        # own (the merge runs on below the last item, so it can fall on the last one) - never an item priced by quantity
        lump = (rate is not None and (ls_word(r[rate]) or (isinstance(r[rate], str) and r[rate].strip().lower().strip(".") in FIGW))) \
            or not any(isinstance(r[c], (int, float)) and r[c] > 0 for c in uq) and not any(re.match(r"^\s*\(?[\d,]*\.?\d*[1-9]", r[c]) for c in uq if isinstance(r[c], str))
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
    def money_(v):
        if isinstance(v, (int, float)):
            return float(v) or None
        if isinstance(v, str):
            return _num(re.sub(r"(?i)\b(aed|dhs?)\b\.?", "", v).strip()) or None
        return None
    def pv(r):
        """The money printed ("AED 44,400.00", an "LS" beside it or not) - or, with no money, the word ("Included")."""
        m = tuple(m for m in (money_(r[c]) for c in price) if m)
        if m:
            return m
        return tuple(str(r[c]).strip().lower().strip(".") for c in price if isinstance(r[c], str) and not ls_word(r[c]) and r[c].strip())
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
            return j != k and key and has(o, price) and pv(o) == key and (near or any(isinstance(v, (int, float)) and v > 0 for v in key)) \
                and not total.search(str(o[di] or "")) and (
                not o[di] or (rate is not None and isinstance(o[rate], str)) or not any(isinstance(o[c], (int, float)) and o[c] > 0 for c in uq))
        # "LS" alone on a line (the merged rate cell printed again at the foot of a page): part of the bracket
        bare_ls = lambda j: not rows[j][di] and not code(rows[j]) and not has(rows[j], uq) and ls_only(rows[j])
        member = lambda j, near=True: j not in used and (unit_only(rows[j]) or again(j, near) or bare_ls(j))
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
        gone = {j for j in [k] + dups + [j for j in range(a, b + 1) if bare_ls(j)] if not rows[j][di] and not code(rows[j]) and not has(rows[j], uq)}
        run = [j for j in range(a, b + 1) if j not in gone]
        if not run:
            k += 1
            continue
        for j in dups:
            for c in price:
                rows[j][c] = None
        lsw = None
        for j in run:                                  # the bracket's "LS" printed on one of its items: the bracket's
            if j != k and ls_only(rows[j]):
                for c in price:
                    if ls_word(rows[j][c]):
                        lsw = (c, rows[j][c])
                        rows[j][c] = None
        move = [c for c in uq + price if r[c] not in (None, "") and all(rows[j][c] in (None, "") for j in run if j != k)]
        if alone:
            move = [c for c in move if c in price or not any(rows[j][c] not in (None, "") for j in run)]
        top = run[0]
        if lsw and rows[top][lsw[0]] in (None, "") and r[lsw[0]] in (None, ""):
            r[lsw[0]] = lsw[1]
            if lsw[0] not in move:
                move.append(lsw[0])
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
        di = next((i for i, c in enumerate(cols) if c.get("role") == "desc"), None)
        if di is None or len(cols) < 3:
            continue
        sig = _sig(cols)
        if cur is None or len(sig) != len(last_sig) or cur.get("ended") or cur.get("closed"):
            carry_ = []
            if cur is not None and len(sig) == len(last_sig):
                # headings at the foot of the page before ("BILL NO. 3 - LANDSCAPING") open the next bill: they go with it
                while cur["rows"] and not any(v not in (None, "") for k_, v in enumerate(cur["rows"][-1]) if k_ != cur["di"] and k_ > 0) \
                        and not re.search(r"\btotal\b|carried|collection|summary", str(cur["rows"][-1][cur["di"]] or ""), re.I):
                    carry_.insert(0, cur["rows"].pop())
            cur = {"cols": cols, "di": di, "rows": carry_, "name": "", "ended": False, "coll": False}
            for r_ in carry_:
                w_ = str(r_[di] or "")
                if w_.isupper() and len(w_) <= 40:
                    cur["first_caps"] = cur.get("first_caps") or w_
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
            code, words, figs, we, notes, wx = "", [], {}, 0, {}, None
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
                    wx = x if wx is None else min(wx, x)
            items.append({"y": l["y"], "h": l.get("h") or 10.0, "code": code, "words": " ".join(words).strip(), "figs": figs, "we": we, "notes": notes,
                          "cw": ((we - wx) / max(1, len(" ".join(words)))) if (words and wx is not None) else 5.0})
        wmax = max([it["we"] for it in items] or [0])
        # "included." under "MEP works" in the amount column: the remark goes on - a word of it, not a price
        for a_, b_ in zip(items, items[1:]):
            if a_["notes"] and b_["y"] - a_["y"] <= 1.5 * b_["h"]:
                for k in list(b_["figs"]):
                    if k in a_["notes"] and _num(b_["figs"][k]) is None:
                        b_["notes"].setdefault(k, b_["figs"].pop(k))
        # rows: words close together are one description; the figures half-way down it go with it
        rows = []
        for it in items:
            if not it["words"] and not it["code"]:
                continue
            last = rows[-1] if rows else None
            gap = it["y"] - last["y1"] if last else 999
            # the line before ran to the edge of the column (the words wrapped) and the next is close under it
            # the words wrapped: the next line's first word would not have fitted at the end of this one
            fw = (it["words"].split() or [""])[0]
            edge = max(wmax, (right[0]["x"] - 4) if right else wmax)      # the description column's right edge
            wrapped = last and last["we"] + it.get("cw", 5.0) * (len(fw) + 1) > min(edge, max(wmax, last["we"]) + 0.6 * (edge - wmax)) - 1
            caps = lambda t: bool(re.search(r"[A-Z]", t)) and not re.search(r"[a-z]", t)
            heading = last and caps(last["words"]) and not caps(it["words"])     # "LIGHT FITTINGS ..." over "Supply, Install ..."
            numf = lambda f: f
            tot_ = lambda t: re.match(r"^(total\b|sub\s*-?\s*total|carried|brought|b\s*/\s*f|c\s*/\s*f|page\s+total|collection\b|bill\s+total|grand\s+total)", t or "", re.I)
            if last and not it["code"] and not heading and not tot_(it["words"]) and not tot_(last["words"]) and ((gap <= 1.12 * it["h"] and (wrapped or not it["figs"])) or (wrapped and gap <= 1.45 * it["h"])) \
                    and (not numf(it["figs"]) or not numf(last["figs"])) and last["words"]:
                last["words"] += " " + it["words"]
                last["y1"] = it["y"]
                last["we"] = it["we"]
                for k, v in it["figs"].items():
                    if k in last["figs"] and k in numf(it["figs"]) and k not in numf(last["figs"]):
                        last.setdefault("notes", {}).setdefault(k, []).append(last["figs"][k])   # words beside: a remark
                        last["figs"][k] = v
                    else:
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
            # a bill's own closing total ("Total of Painting", "TOTAL CARRIED TO SUMMARY", "Bill total") as the last line
            # before a new page with its headings: the next page starts the next bill (the next sheet of the workbook)
            cur["closed"] = bool(re.search(r"^(sub\s*-?\s*)?total\b(?!\s+carried\s+(forward|over|to\s+collection))|\bbill\s+total\b|carried\s+to\s+(the\s+)?(summary|main)",
                                           w, re.I)) and not re.search(r"carried\s+(forward|over)|to\s+collection|c\s*/\s*f", w, re.I) \
                and any(v not in (None, "") for k_, v in enumerate(out) if k_ > di)
            if not cur["name"] and w and w.isupper() and len(w) <= 40 and not any(v not in (None, "") for k_, v in enumerate(out) if k_ > di) \
                    and not re.search(r"bill\s+of\s+quantities|summary|collection", w, re.I):
                cur["first_caps"] = cur.get("first_caps") or w
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
        name = s["name"] or re.sub(r"[^A-Za-z0-9 &]", " ", s.get("first_caps") or "").strip()[:28] or \
            ("SUMMARY" if s["coll"] and not any(re.search(r"bill\s*page", str(r[s["di"]] or ""), re.I) for r in s["rows"]) else f"Sheet {n}")
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


def column_lines(doc, data=None):
    """The pages read on the server (every word with its box, typed or recognised from a scan) put into the table's
    own columns (5 Nov 2026): the column headings give the columns; the line between two columns is drawn where the
    figures under them leave a clear channel (or on the table's own vertical rule); every word goes to the column it
    starts in (a figure: where it ends - figures stand to the right). A page that does not repeat the headings keeps
    the columns of the page before. -> lines as to_workbook reads them, or None when no table heading is found."""
    out, cols_prev = [], None
    from docread.model import Word
    fine = {}
    if data is not None and data[:4] == b"%PDF":
        # the words again, split finer than the reader's lines: figures in narrow columns printed almost touching
        # ("235.46Nos", "2456.472,328,733.56") come apart
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                for n, pg in enumerate(pdf.pages, 1):
                    ws_ = pg.extract_words(x_tolerance=1.0, y_tolerance=2.0, keep_blank_chars=False, use_text_flow=False)
                    if len(ws_) < 3:
                        continue
                    vr = []                                    # the table's vertical rules (cell borders), if drawn
                    for o in (pg.lines or []) + (pg.rects or []):
                        if (o["bottom"] - o["top"]) > 8 and abs(o["x1"] - o["x0"]) < 1.5:
                            vr.append(((o["x0"] + o["x1"]) / 2, o["top"], o["bottom"]))
                    wl_ = []
                    for w in ws_:
                        m_ = re.fullmatch(r"(\(?[\d,]*\.?\d+\)?)([A-Za-z][A-Za-z0-9/.²³]*)", w["text"])
                        if m_ and not re.fullmatch(r"\d+(mm|cm|m|kg|kw|w|v|a|l|mm2|m2|m3|x\d.*)", w["text"], re.I):
                            # a quantity and its unit printed touching ("52Set", "1514lm"): two words
                            cw = (w["x1"] - w["x0"]) / max(1, len(w["text"]))
                            xm = w["x0"] + cw * len(m_.group(1))
                            w1 = Word(text=m_.group(1), x0=w["x0"], x1=xm, y0=w["top"], y1=w["bottom"])
                            w2 = Word(text=m_.group(2), x0=xm + 0.01, x1=w["x1"], y0=w["top"], y1=w["bottom"])
                            w2.glue = True                     # back together if both halves land in one column
                            wl_ += [w1, w2]
                        else:
                            wl_.append(Word(text=w["text"], x0=w["x0"], x1=w["x1"], y0=w["top"], y1=w["bottom"]))
                    fine[n] = (wl_, vr)
        except Exception:
            fine = {}
    regs = list(getattr(doc, "regions", []) or [])
    for reg in regs:
        rows = []
        if reg.page in fine:
            wl, vr_ = fine[reg.page]
            reg = type("R", (), {"page": reg.page, "vrules": vr_ or getattr(reg, "vrules", []), "rows": []})()
            lines_ = []
            for w in sorted(wl, key=lambda w: ((w.y0 + w.y1) / 2, w.x0)):
                cy, h = (w.y0 + w.y1) / 2, max(1.0, w.y1 - w.y0)
                ln = next((L for L in lines_[-4:] if abs(L["cy"] - cy) <= 0.45 * max(h, L["h"])), None)
                if ln is None:
                    lines_.append({"cy": cy, "h": h, "w": [w]})
                else:
                    ln["w"].append(w)
            for L in lines_:
                ws_ = sorted(L["w"], key=lambda w: w.x0)
                cells, cur = [], None
                for w in ws_:
                    if cur is not None and w.x0 - cur[1] < 0.45 * L["h"]:
                        cur[1], cur[2] = w.x1, cur[2] + " " + w.text
                    else:
                        cur = [w.x0, w.x1, w.text]
                        cells.append(cur)
                hs = sorted(w.y1 - w.y0 for w in ws_)
                rows.append({"y": round(L["cy"], 1), "h": hs[len(hs) // 2], "w": ws_, "cells": [tuple(c) for c in cells]})
        for row in reg.rows:
            ws_ = [w for c in row.cells for w in (c.words or []) if w.text.strip()]
            if not ws_:
                ws_ = []
                for c in row.cells:
                    if c.text.strip():
                        ws_.append(Word(text=c.text, x0=c.x0, x1=c.x1, y0=c.y0, y1=c.y1))
            if ws_:
                ws_.sort(key=lambda w: w.x0)
                hs = sorted(w.y1 - w.y0 for w in ws_)
                rows.append({"y": round(sum((w.y0 + w.y1) / 2 for w in ws_) / len(ws_), 1), "h": hs[len(hs) // 2], "w": ws_,
                             "cells": [(c.x0, c.x1, c.text.strip()) for c in row.cells if c.text.strip()]})
        if not rows:
            continue
        rows.sort(key=lambda r: r["y"])
        tl = [{"p": reg.page, "y": r["y"], "h": r["h"], "c": [t for _, _, t in r["cells"]], "x": [a for a, _, _ in r["cells"]],
               "xe": [b for _, b, _ in r["cells"]]} for r in rows]
        hs_, hbot = _page_header(tl)
        if hs_ is not None:
            cols = _header_cols(hs_)
            htop = min(l["y"] for l in hs_)
        elif cols_prev is not None:
            cols, htop, hbot = cols_prev, None, None
        else:
            continue
        data = [r for r in rows if hbot is None or r["y"] > hbot + 0.5]
        # the line between two columns: the clearest channel near the gap between their headings (or the page's rule)
        vr = sorted({round(x) for x, y0, y1 in (getattr(reg, "vrules", None) or [])})
        bounds = []
        for i in range(len(cols) - 1):
            a, b = cols[i], cols[i + 1]
            lo = a["xe"] - 0.35 * (a["xe"] - a["x"]) if i else a["xe"] - 0.2 * (a["xe"] - a["x"])
            hi = b["x"] + 0.35 * (b["xe"] - b["x"])
            if hi <= lo:
                lo, hi = min(a["xe"], b["x"]) - 2, max(a["xe"], b["x"]) + 2
            rule = [x for x in vr if lo - 6 <= x <= hi + 6]
            if rule:
                bounds.append(min(rule, key=lambda x: abs(x - (a["xe"] + b["x"]) / 2)))
                continue
            best, bx = None, (lo + hi) / 2
            x = lo
            while x <= hi:
                occ = sum(1 for r in data for w in r["w"] if w.x0 < x < w.x1)
                d = abs(x - (a["xe"] + b["x"]) / 2)
                if best is None or occ < best[0] or (occ == best[0] and d < best[1]):
                    best, bx = (occ, d), x
                x += 0.5
            bounds.append(bx)
        cols_prev = cols

        def col_at(x):
            k = 0
            while k < len(bounds) and x >= bounds[k]:
                k += 1
            return k
        di = next((i for i, c in enumerate(cols) if c.get("role") == "desc"), 0)
        if hs_ is not None:
            out.append({"p": reg.page, "y": hbot, "h": 10.0, "hdr": True, "c": [c["label"] for c in cols],
                        "x": [c["x"] for c in cols], "xe": [c["xe"] for c in cols]})
        else:
            out.append({"p": reg.page, "y": (data[0]["y"] - 30) if data else 0, "h": 10.0, "hdr": True, "c": [c["label"] for c in cols],
                        "x": [c["x"] for c in cols], "xe": [c["xe"] for c in cols]})
        for r in data:
            # phrases: words a space apart; words of a heading running on past its column stay in it
            ph, cur = [], None
            for w in r["w"]:
                if cur is not None and w.x0 - cur[-1].x1 < 0.45 * max(r["h"], 4):
                    cur.append(w)
                else:
                    cur = [w]
                    ph.append(cur)
            cells = {}
            for p_ in ph:
                k0 = col_at(p_[0].x0 + 0.5)
                txt = " ".join(w.text for w in p_)
                if k0 <= di and not NUM.match(p_[0].text.replace(",", "")) and col_at(p_[-1].x1 - 0.5) > di and \
                        not any(NUM.match(w.text.replace(",", "")) or w.text.lower().strip(".") in UNITW for w in p_[1:]):
                    cells.setdefault(k0, []).append(p_)          # the words run over the next columns (an empty cell)
                    continue
                if k0 > di and len(p_) == 2 and NUM.match(p_[0].text.replace(",", "")) and p_[1].text.lower().strip(".") in UNITW:
                    cells.setdefault(k0, []).append(p_)          # "57 Pair": a quantity written with its unit, one cell
                    continue
                for w in p_:
                    num = NUM.match(w.text.strip()) is not None or re.fullmatch(r"\(?[\d,]+\.\d+\)?", w.text.strip()) is not None
                    k = col_at((w.x1 - 0.5) if num else (w.x0 + 0.5))
                    cells.setdefault(k, []).append([w])
            line = {"p": reg.page, "y": r["y"], "h": r["h"], "c": [], "x": [], "xe": []}
            for k in sorted(cells):
                ws2 = [w for grp in cells[k] for w in grp]
                ws2.sort(key=lambda w: w.x0)
                t = ""
                for w in ws2:
                    t += ("" if (not t or getattr(w, "glue", False)) else " ") + w.text
                t = t.strip()
                if not t:
                    continue
                if k <= di:                                    # words: where they stand
                    x0, x1 = ws2[0].x0, ws2[-1].x1
                else:                                          # figures: exactly under their heading
                    x0, x1 = cols[k]["x"], cols[k]["xe"]
                line["c"].append(t)
                line["x"].append(x0)
                line["xe"].append(x1)
            if line["c"]:
                out.append(line)
    return out if out else None


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
    except F.Unavailable as e:
        raise NotTable(str(e))
    # two readings of the page: the words put into the table's own columns, and the lines as the browser gives
    # them - the one whose figures tie out (every page / bill = its own total, nothing left for review) is taken
    cands = []
    try:
        cl = column_lines(doc, data)
        if cl:
            cands.append(to_workbook(cl))
    except Exception:
        pass
    try:
        cands.append(to_workbook(F.old_lines(data, name, doc)))
    except F.Unavailable as e:
        if not any(cands):
            raise NotTable(str(e))
    except Exception:
        pass
    cands = [c for c in cands if c]
    wb = cands[0] if cands else None
    if len(cands) > 1:
        import est_itemimport as I

        def mark(c):
            try:
                r = I.read_schedule(c)
            except Exception:
                return (-1,)
            alarms = sum(1 for n in r["notes"] if re.search(r" says |add up to|not the|accounted for", n))
            return (int(r["all_checked"]), -alarms)
        # the column reading is the one to trust; the browser-line reading only when the column one found nothing
        m0 = mark(cands[0])
        wb = cands[0] if m0 != (-1,) else cands[1]
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

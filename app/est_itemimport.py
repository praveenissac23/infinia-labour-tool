"""Read a subcontractor's item schedule out of an Excel workbook - the agreement BOQ or any of
its payment certificates (Appendix A / the Bill sheets) - into schedule lines.

The file is read in memory and never kept. Every sheet with a heading row that has a
Description column and an amount / rate column is read:

  * 908 / 909 MEP:  "Bill No | Description | Approx. Qty | Unit | Rate | Amount | Previous % |
                     Current % | Total % Work Done | Certified Amount | Remarks"   (one sheet per bill)
  * 915 civil:      "Bill No | Description | Estimated Quantity | Quantity Claimed | Quantity of
                     Work Done at Site | Unit | Rate | Certified Amount | Remarks"
  * 911 finishes:   "Bill No | Description | Estimated Quantity | SC Claimed Qty | Certified Qty |
                     % of work completed | Unit | SC Rate | Certified Amount ..."

Lump sums (Rate "LS", an Amount) are measured by % done; lines with a quantity and a rate and a
certified quantity are measured by quantity. An amount written in words ("Included", "Excluded",
"NA") is kept on the line with no money. A line in capitals with no figures is a heading; a
sentence with no figures introduces the lettered lines under it ("a. M.D.B ...").

Every sheet is checked against its own total row ("Total To-date carried over ..."): the contract
amount and, where the file is a certificate, the certified amount to date.
"""
import io
import re

import openpyxl


def _s(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return re.sub(r"\s+", " ", str(v)).strip()


def _n(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).replace(",", "").replace("AED", "").strip()
    if t.endswith("%"):
        try:
            return float(t[:-1]) / 100.0
        except ValueError:
            return None
    try:
        return float(t)
    except ValueError:
        return None


def _key(t):
    return re.sub(r"[^a-z% ]", "", _s(t).lower().replace("\n", " ")).strip()


def _header(row):
    """Column positions from a heading row, or None if this row is not one."""
    cols = {}
    for i, v in enumerate(row):
        k = _key(v)
        if not k:
            continue
        if "description" in k and "desc" not in cols:
            cols["desc"] = i
        elif k in ("bill no", "item", "item no", "sr no", "sno", "sl no", "no", "ref", "bill") and "no" not in cols:
            cols["no"] = i
        elif ("certified amount" in k or "amount certified" in k) and "cert_amt" not in cols:
            cols["cert_amt"] = i
        elif "claimed from client" in k or "received from client" in k or "amount claimed" in k:
            continue
        elif k in ("amount", "amount aed", "total amount", "contract amount") and "amount" not in cols:
            cols["amount"] = i
        elif "rate" in k and "rate" not in cols:
            cols["rate"] = i
        elif k == "unit" and "unit" not in cols:
            cols["unit"] = i
        elif ("certified qty" in k or "work done at" in k or "quantity done" in k) and "cert_qty" not in cols:
            cols["cert_qty"] = i
        elif "claimed" in k and ("qty" in k or "quantity" in k) and "claim_qty" not in cols:
            cols["claim_qty"] = i
        elif ("estimated" in k or "approx" in k or k in ("qty", "quantity")) and "qty" not in cols:
            cols["qty"] = i
        elif "previous" in k and "%" in k:
            cols["prev_pct"] = i
        elif "current" in k and "%" in k:
            cols["cur_pct"] = i
        elif ("% work done" in k or "% of work" in k or "total %" in k) and "pct" not in cols:
            cols["pct"] = i
        elif "remark" in k and "remark" not in cols:
            cols["remark"] = i
        elif k == "appendix":
            cols["appendix"] = i
    if "desc" not in cols or not ({"amount", "rate"} & set(cols)):
        return None
    if "appendix" in cols:          # a summary of the bills (909 Appendix A), not a schedule
        return None
    return cols


LETTERED = re.compile(r"^\(?([a-z]|[ivx]{1,5})[.)]\s+", re.I)
# A priced BOQ in bill pages (914 Al Raida MEP): each page ends "TO COLLECTION" / "TOTAL CARRIED TO COLLECTION" with
# its own subtotal, the sheet ends with a COLLECTION of "HVAC BILL PAGE 1/6 ... 6/6", and a summary sheet carries the
# trade totals. Those are roll-ups of the lines - never lines themselves; they are used only to check the lines.
PAGE_TOTAL = re.compile(r"^(total\s+)?(carried\s+)?to\s+collection\b|^carried\s+(forward|over)\b|^page\s+total\b", re.I)
BILL_PAGE = re.compile(r"\bbill\s*page\s*\d+\s*/\s*\d+", re.I)
COLLECTION_HEAD = re.compile(r"^(collection|summary|general summary|collection sheet|bill summary|grand summary)$", re.I)
UNIT_WORDS = {"ls", "l.s", "l.s.", "lumpsum", "lump sum", "no", "no.", "nos", "nos.", "item", "items", "set", "sets", "m", "lm", "rm",
              "m2", "sqm", "sq.m", "m3", "cum", "kg", "ton", "pair", "lot", "unit", "units"}
SIZE_LINE = re.compile(r"^\d+(\.\d+)?\s*mm\b", re.I)


def _bill_from_sheet(title):
    """A trade sheet's own short name for its bill: "MEP_BOQ_HVAC" -> HVAC, "MEP_BOQ_ELECTRICAL" -> ELECTRICAL."""
    toks = [t for t in re.split(r"[\s_\-.]+", title or "") if t and t.upper() not in ("MEP", "BOQ", "BILL", "SHEET", "NO", "OF", "DIVISION", "DIV", "SECTION") and not t.isdigit()]
    return " ".join(toks).upper()[:20]
WORDS_ZERO = ("-", "--", "0", "nil")


def read_schedule(data: bytes):
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    items, sheets, notes, summaries, review = [], [], [], [], []
    for ws in wb.worksheets:
        if ws.sheet_state != "visible":
            continue
        rows = [list(r) + [None] * 6 for r in ws.iter_rows(values_only=True)]
        r0, c0 = 1, 1                                          # iter_rows always starts at A1: rows[i] is sheet row 1 + i, r[j] column 1 + j
        hi, cols = None, None
        for i, r in enumerate(rows[:40]):
            c = _header(r)
            if c:
                hi, cols = i, c
                break
        if cols is None:
            continue
        # the % column is read one way for the whole column: written as whole numbers (if any figure is over 1:
        # 1 = 1%, 50 = 50%) or as fractions (0.5 = 50%) - never 1 = 100% in one row and 50 = 50% in the next
        pct_whole = "pct" in cols and any((_n(r[cols["pct"]]) or 0) > 1.0000001 for r in rows[hi + 1:])
        as_pct = lambda p_: p_ if pct_whole else p_ * 100
        # bill: "Appendix - B1" above the heading, its title the text line after it
        bill, title = "", ""
        for r in rows[:hi]:
            for v in r:
                t = _s(v)
                m = re.match(r"^appendix\s*-?\s*([A-Z]\d*)$", t, re.I)
                if m:
                    bill = m.group(1).upper()
                elif t and not title and bill and not re.match(r"^(value of work|payment certificate|date)", t, re.I) and len(t) < 80:
                    title = t.title() if t.isupper() else t
        if not bill:
            m = re.match(r"^bill\s*(\d+)\s*-?\s*(.*)$", ws.title, re.I)
            if m:
                bill, title = "B" + m.group(1), title or m.group(2).strip()
        # Several items priced as ONE lump sum (a bracket drawn beside them in the BOQ): the price is a cell merged down
        # all their rows, its figure / "LS" / "Included" in the top row (914/915 Al Raida: Sanitary fittings, pipe
        # sizes, cable trays, final circuits ...). The bracket itself is a drawing - the merged cell is what is read.
        groups = {}                                            # first sheet row -> last sheet row
        pcols = [cols[k] + c0 for k in ("amount", "rate") if k in cols]
        for m in getattr(ws, "merged_cells", None).ranges if getattr(ws, "merged_cells", None) else []:
            if m.max_row <= m.min_row or m.min_row <= r0 + hi or not any(m.min_col <= pc <= m.max_col for pc in pcols):
                continue
            top_vals = [rows[m.min_row - r0][pc - c0] for pc in pcols if 0 <= m.min_row - r0 < len(rows)]
            if not any(_s(v) for v in top_vals):
                continue                                       # a merged cell with nothing in it prices nothing
            # a lump sum is a figure, LS or "Included" - merged words like "N.A." / "Excluded" over lines are notes;
            # and a row under it with a price of its own means it is not one lump sum for them all
            if not any(_n(v) or _s(v).lower().strip(". ") in ("ls", "l.s", "lumpsum", "lump sum", "included", "incl", "inclusive")
                       for v in top_vals):
                continue
            own = any(_n(rows[k - r0][pc - c0]) for k in range(m.min_row + 1, m.max_row + 1) for pc in pcols if 0 <= k - r0 < len(rows))
            if own:
                continue
            a, b = m.min_row, m.max_row
            for k in list(groups):                             # rate and amount merged over the same rows: one group
                if k <= b and groups[k] >= a:
                    a, b = min(a, k), max(b, groups.pop(k))
            groups[a] = b
        top, section, parent, mine, skipped = "", "", "", [], 0
        heads, pending, open_grp = [], [], None                # heading lines over the next item; unpriced rows waiting; the group being filled
        counts = {"rows": 0, "lines": 0, "members": 0, "headings": 0, "review": 0, "groups": 0}
        NUMBERED = re.compile(r"^\(?\d{1,2}\s*[.)]\s+")
        total_row = None
        is_qty = "cert_qty" in cols
        amt_of = lambda r: _n(r[cols["amount"]]) if "amount" in cols else None
        label_of = lambda r: " ".join(x for x in (_s(r[cols["no"]]) if "no" in cols else "", _s(r[cols["desc"]])) if x)
        # a sheet in bill pages: its page subtotals, and the roll-ups after its COLLECTION heading
        has_pages = any(PAGE_TOTAL.match(label_of(r)) for r in rows[hi + 1:])
        pages, rollups, pstart, in_coll = [], [], 0, False
        intro, group = "", ""
        row_no = {id(r_): r0 + i_ for i_, r_ in enumerate(rows)}
        xr_of = lambda r_: row_no.get(id(r_), 0)
        page_heads = []                                        # (sheet row, no., words) of the heading rows on this page

        def merge_page():
            """A bill page with ONE price (a group) and only unpriced items besides: they are all that group's - the
            bracket runs the length of the page, through its sub-headings (914 fire alarm: 2,700 for rows 303-344)."""
            if not has_pages:
                return
            page = mine[pstart:]
            gs = [x for x in page if x.get("grp") == "head"]
            if len(gs) != 1 or not any(x.get("review") for x in page):
                return
            g = gs[0]
            if not all(x is g or x.get("grp") == "in" or x.get("review") for x in page):
                return
            rest = [x for x in page if x is not g]
            for x in rest:
                if x.pop("review", None):
                    counts["review"] -= 1
                    counts["members"] += 1
                    x["grp"] = "in"
            lo, hi_ = min(x["_xr"] for x in rest), max(x["_xr"] for x in rest)
            sub = [h for h in page_heads if lo < h[0] < hi_ and h[0] not in {x["_xr"] for x in rest}]
            for xr_, no_, d_ in sub:
                counts["headings"] -= 1
                counts["members"] += 1
                rest.append({"bill": bill, "bill_title": title[:120], "section": section[:200], "no": no_[:20], "description": d_[:2000],
                             "qty": 0.0, "unit": "", "rate": 0.0, "amount": 0.0, "measure": "pct", "words": "", "remark": "", "done_pct": None,
                             "done_qty": None, "claimed_qty": None, "certified": None, "stage_pct": None, "rate_missing": False, "grp": "in",
                             "_xr": xr_})
            if g.get("_parts"):                                # a sub-heading now listed under the group leaves its name
                inside = {d_ for _, _, d_ in sub}
                left = [t for t in g["_parts"] if t not in inside]
                if left:
                    g["description"] = title_of(left)[:2000]
            mine[pstart:] = [g] + sorted(rest, key=lambda x: x["_xr"])

        def unit_qty(r):
            """A row's unit and quantity - the unit may be typed in the QTY column ("No | 5")."""
            q = _n(r[cols["qty"]]) if "qty" in cols else None
            u = _s(r[cols["unit"]]) if "unit" in cols else ""
            qt = _s(r[cols["qty"]]).lower() if "qty" in cols else ""
            if q is None and qt in UNIT_WORDS and (not u or _n(u) is not None):
                if _n(u) is not None:
                    q = _n(u)
                u = _s(r[cols["qty"]])
            return u, q

        def short(t, n=200):
            return t if len(t) <= n else t[:n - 3].rsplit(" ", 1)[0] + "..."

        def member(r, why):
            """A row priced in its group: shown under the group, never counted."""
            no_, d_ = (_s(r[cols["no"]]) if "no" in cols else ""), _s(r[cols["desc"]])
            u_, q_ = unit_qty(r)
            counts["members"] += 1
            return {"bill": bill, "bill_title": title[:120], "section": section[:200], "no": no_[:20], "description": d_[:2000],
                    "qty": round(q_ or 0, 4), "unit": u_[:20], "rate": 0.0, "amount": 0.0, "measure": "pct", "words": "", "remark": "",
                    "done_pct": None, "done_qty": None, "claimed_qty": None, "certified": None, "stage_pct": None, "rate_missing": False,
                    "grp": "in", "_why": why, "_xr": xr_of(r)}

        def group_head(desc_, no_, amt_, words_, r_top):
            counts["groups"] += 1
            pct_ = _n(r_top[cols["pct"]]) if "pct" in cols else None
            cert_ = _n(r_top[cols["cert_amt"]]) if "cert_amt" in cols else None
            amount_ = round(amt_ or 0, 2)
            dp = round(as_pct(pct_), 4) if pct_ is not None else (round(100 * cert_ / amount_, 4) if (cert_ is not None and amount_) else None)
            return {"bill": bill, "bill_title": title[:120], "section": section[:200], "no": no_[:20], "description": desc_[:2000],
                    "qty": 1.0, "unit": "LS", "rate": amount_, "amount": amount_, "measure": "pct", "words": words_[:60], "remark": "",
                    "done_pct": dp, "done_qty": None, "claimed_qty": None, "certified": round(cert_, 2) if cert_ is not None else None,
                    "stage_pct": None, "rate_missing": False, "grp": "head", "_xr": xr_of(r_top), "_parts": []}

        def flush_pending(why):
            """Unpriced item rows no group took: brought in at nil and listed for review - never dropped."""
            nonlocal_pending = list(pending)
            pending.clear()
            for r_, xr_ in nonlocal_pending:
                x = member(r_, "")
                counts["members"] -= 1
                counts["review"] += 1
                x["grp"] = ""
                x["review"] = f"{ws.title} row {xr_}: '{x['description'][:70]}' - no price and no group ({why}) - brought in at nil"
                mine.append(x)

        # a group's name: its heading ("Sanitary Fittings & Accessories") - the sentence under a short heading is the
        # BOQ's wording of the work, not the name; a single sentence (no heading over it) is the name
        title_of = lambda parts: (parts[0] if len(parts) >= 2 and len(parts[0]) <= 80 else " - ".join(parts))
        group_title = lambda: title_of(heads) or group or (section.split(" ", 1)[1] if re.match(r"^\S{1,4}\s", section or "") else section)

        def new_group(desc_, no_, amt_, words_, r_top):
            g_ = group_head(desc_, no_, amt_, words_, r_top)
            if not no_ and heads and desc_ == title_of(heads):
                g_["_parts"] = list(heads)
            return g_
        skip_to = 0
        for ri, r in enumerate(rows[hi + 1:], start=hi + 1):
            xr = r0 + ri
            if xr <= skip_to:
                continue
            no = _s(r[cols["no"]]) if "no" in cols else ""
            desc = _s(r[cols["desc"]])
            if xr in groups and not in_coll and not BILL_PAGE.search(" ".join(x for x in (no, desc) if x)) \
                    and not PAGE_TOTAL.match(" ".join(x for x in (no, desc) if x)):
                # the bracket: every row of the merged price cell, the price on one line (the group), the rows under it
                end = groups[xr]
                skip_to = end
                flush_pending("before a priced group")
                open_grp = None
                rr = [(rows[k - r0], k) for k in range(xr, end + 1) if 0 <= k - r0 < len(rows)]
                amt_g = amt_of(r)
                araw = r[cols["amount"]] if "amount" in cols else None
                words_g = "" if amt_g is not None or araw is None else _s(araw)
                if amt_g is None and "rate" in cols and _n(r[cols["rate"]]) is not None and not _s(araw):
                    amt_g = _n(r[cols["rate"]])                # a figure in the rate column only
                rows_txt = [(rr_, k) for rr_, k in rr if _s(rr_[cols["desc"]]) or (("no" in cols) and _s(rr_[cols["no"]]))]
                u0, q0 = unit_qty(r)
                # the first row with words, with no unit or quantity of its own, is the group's title ("S TELEPHONE AND DATA
                # SYSTEM", "AB Fire Alarm Control Panel"); else the group is named by the heading lines over it
                t0 = rows_txt[0][0] if rows_txt else None
                tu, tq = unit_qty(t0) if t0 is not None else ("", None)
                title_row = rows_txt[0] if (t0 is not None and _s(t0[cols["desc"]]) and not tu and not tq and len(rows_txt) > 1) else None
                tdesc = _s(title_row[0][cols["desc"]]) if title_row else ""
                tno = (_s(title_row[0][cols["no"]]) if "no" in cols else "") if title_row else ""
                gtitle = tdesc if title_row else (group_title() or (_s(rows_txt[0][0][cols["desc"]]) if rows_txt else "Lump sum"))
                counts["rows"] += len(rows_txt)
                if title_row:
                    counts["headings"] += 1
                mine.append(new_group(_s(gtitle), tno, amt_g, words_g, r))
                for rr_, k in rows_txt:
                    if title_row and k == title_row[1]:
                        continue
                    mine.append(member(rr_, f"{ws.title} rows {xr}-{end}"))
                heads, parent, intro = [], "", ""
                continue
            rowtext = " ".join(_s(x) for x in r[:12]).lower()
            label = label_of(r)
            if BILL_PAGE.search(label):                         # "HVAC BILL PAGE 3/6": a page's subtotal brought to the collection
                rollups.append((label, amt_of(r) or 0.0))
                continue
            if PAGE_TOTAL.match(label) and in_coll:             # the sheet's own total, under its collection
                if amt_of(r):
                    total_row = r
                continue
            if PAGE_TOTAL.match(label):                         # the page ends: its lines must add up to its subtotal
                flush_pending("the page ends")
                open_grp = None
                merge_page()
                page_heads = []
                v = amt_of(r)
                if v is not None:
                    pages.append({"label": label, "sheet": round(v, 2), "lines": mine[pstart:]})
                    total_row = r
                pstart = len(mine)
                continue
            if desc and COLLECTION_HEAD.match(desc) and amt_of(r) is None:
                flush_pending("the collection starts")
                open_grp = None
                in_coll = True                                  # from here the sheet only adds up what is above
                continue
            if in_coll:
                v = amt_of(r)
                if v is not None or (desc and "rate" in cols and _n(r[cols["rate"]])):
                    rollups.append((label, v or 0.0))
                    if re.match(r"^\s*(grand\s+)?total\b", label, re.I) and v:
                        total_row = r
                continue
            if desc and re.match(r"^\s*(sub\s*-?\s*|grand\s+)?total\b", desc, re.I) and not no and has_pages:
                if amt_of(r):
                    total_row = r                               # "TOTAL HVAC SYSTEMS  Item 1 243,000": a total, rate or not
                continue
            # a total row - not an item that only has the word in it ("Total station survey", with its no. / unit / qty)
            itemish = bool(no) or ("unit" in cols and _s(r[cols["unit"]])) or ("qty" in cols and _n(r[cols["qty"]]))
            starts_total = re.match(r"^\s*(sub\s*-?\s*|grand\s+)?total\b", desc, re.I)
            if re.search(r"\btotal\b", rowtext) and not (desc and _n(r[cols["rate"]]) if "rate" in cols else False) \
                    and (starts_total or not desc or not itemish):
                if any(_n(r[cols[k]]) for k in ("amount", "cert_amt") if k in cols):
                    total_row = r
                if mine:
                    parent = ""
                continue
            if re.match(r"^(m/?s\.?\s*)?(sub ?-?contractor|contractor)\s*:|^date\s*:", rowtext.strip()):
                break                                   # the signature block
            if not desc and not has_pages and total_row is None and mine and any(_n(r[cols[k]]) for k in ("amount", "cert_amt") if k in cols) \
                    and not any(_s(r[cols[k]]) for k in ("no", "unit", "rate", "qty") if k in cols):
                total_row = r                           # a total with no words beside it (911)
                continue
            if not desc and not in_coll and pending:
                a_ = amt_of(r)
                araw_ = r[cols["amount"]] if "amount" in cols else None
                w_ = "" if a_ is not None or araw_ is None else _s(araw_)
                rr_ = _s(r[cols["rate"]]).upper() if "rate" in cols else ""
                if a_ or (w_ and w_.lower() not in WORDS_ZERO) or rr_ in ("LS", "L.S", "L.S.", "LUMPSUM", "LUMP SUM"):
                    # 914 hot water pipes: "15mm" / "0 Included" / "20mm" - the price row in the run prices the run
                    g = new_group(group_title() or "Lump sum", "", a_, w_, r)
                    g["_xr"] = pending[0][1]
                    mine.append(g)
                    for r_, xr_ in pending:
                        mine.append(member(r_, "the run priced by the row inside it"))
                    pending.clear()
                    open_grp = g
                    heads, parent, intro = [], "", ""
                    continue
            if not desc and has_pages and amt_of(r):
                # a lump sum written on a row of its own under the lines it prices (914: "LS 4,500" under the cable
                # tray sizes) - it is that group's line, named by the group and the sentence that introduces it
                desc = (intro if len(intro) <= 200 else intro[:197].rsplit(" ", 1)[0] + "...") or group or section or "Lump sum"
                no = ""
            if not desc:
                continue
            counts["rows"] += 1
            qty = _n(r[cols["qty"]]) if "qty" in cols else None
            unit = _s(r[cols["unit"]]) if "unit" in cols else ""
            rate_raw = r[cols["rate"]] if "rate" in cols else None
            rate = _n(rate_raw)
            amt_raw = r[cols["amount"]] if "amount" in cols else None
            amt = _n(amt_raw)
            qty_txt = _s(r[cols["qty"]]).lower() if "qty" in cols else ""
            if qty is None and qty_txt in UNIT_WORDS and (not unit or _n(unit) is not None):
                # the unit typed in the QTY column (914 plumbing: "No | 5 | 4,500"): the figure beside it is the quantity
                if _n(unit) is not None:                # ... and the quantity in the UNIT column ("3 | no.")
                    qty = _n(unit)
                unit = _s(r[cols["qty"]])
                if unit.lower().startswith("l") and amt:
                    rate_raw, rate, qty = "LS", amt, 1.0
                elif amt and rate and qty is None:
                    qty, rate = rate, round(amt / rate, 4)
                elif rate and qty is None:
                    qty, rate = rate, None
            words = "" if amt is not None or amt_raw is None else _s(amt_raw)
            if words.lower() in WORDS_ZERO:
                words = ""
            cert_qty = _n(r[cols["cert_qty"]]) if "cert_qty" in cols else None
            pct = _n(r[cols["pct"]]) if "pct" in cols else None
            cert_amt = _n(r[cols["cert_amt"]]) if "cert_amt" in cols else None
            remark = _s(r[cols["remark"]]) if "remark" in cols else ""
            priced = bool(amt) or bool(qty and rate) or (is_qty and bool(qty or rate))
            if not priced and not words:
                if not (qty or rate or unit or cert_amt):
                    counts["headings"] += 1
                    page_heads.append((xr, no, desc))
                    head = f"{no} {desc}".strip() if no and len(no) <= 3 else desc
                    if open_grp is not None or pending:
                        flush_pending("a heading follows")
                        open_grp = None
                    if NUMBERED.match(desc) and len(desc) <= 60:
                        section, parent = head, ""             # "10) TELEPHONE SYSTEM:", "17) Any Other Items"
                        intro = group = ""
                        heads = []
                    elif desc.upper() == desc and len(desc) < 120:
                        top = section = head                   # "9 ELECTRICAL WORKS", "BOOSTER SET"
                        parent = ""
                        intro = group = ""
                        heads = []
                    elif no and len(no) <= 4 and len(desc) <= 80:
                        section, parent, intro, group = head, "", "", ""   # "A) Watse, Soil & Vent Pipes"
                        heads = []
                    else:
                        parent = desc
                        if len(desc) >= 40:
                            intro = desc                       # "Supply, install and connect hot dip galvanized cable trays ..."
                        elif desc.strip(" :.").lower() not in ("generally", "general", "note", "notes"):
                            group, intro = desc, ""            # "Storm Water Drainage"
                        if desc.strip(" :.").lower() not in ("generally", "general", "note", "notes") and not re.search(r"\(\s*cont", desc, re.I):
                            heads.append(short(desc))          # the words over the next item / group (not "... (Cont.)" - a page's repeat)
                else:
                    # an item with its unit (and maybe a quantity) but no price: one of several priced together,
                    # waiting for the row that carries their lump sum - or, if none comes, brought in for review
                    if open_grp is not None:
                        mine.append(member(r, "after the priced row"))
                    else:
                        pending.append((r, xr))
                    if len(desc) >= 40:
                        intro = desc                           # "Supply, Install, test ... PRV station" (qty 0, no price)
                    skipped += 1
                continue
            if pending:
                ls_row = (isinstance(rate_raw, str) and rate_raw.strip().upper() in ("LS", "L.S", "L.S.", "LUMPSUM", "LUMP SUM")) or \
                    unit.strip().lower() in ("ls", "l.s", "l.s.", "lumpsum", "lump sum", "item", "lot")
                numbered = bool(no) or any(("no" in cols and _s(r_[cols["no"]])) for r_, _ in pending)
                if ls_row and amt and not numbered:
                    # the rows above with no price + this one with the lump sum: one group (no merged cell to say so) -
                    # unless they carry item numbers: a numbered item is an item of its own
                    counts["groups"] += 1
                    g = new_group(group_title() or desc, "", amt, "", r)
                    mine.append(g)
                    for r_, xr_ in pending:
                        mine.append(member(r_, "before the priced row"))
                    pending.clear()
                    mine.append(member(r, "the priced row"))
                    open_grp = g
                    heads, parent, intro = [], "", ""
                    continue
                flush_pending("the next row has its own price")
            open_grp = None
            if NUMBERED.match(desc) and section != top:
                section = top                                  # "11) ..." is back at the bill's own level
            if parent and LETTERED.match(desc):
                p = parent if len(parent) <= 90 else parent[:87].rsplit(" ", 1)[0] + "..."
                desc = f"{p} - {desc}"
            elif not LETTERED.match(desc):
                parent = ""
            ls = isinstance(rate_raw, str) and rate_raw.strip().upper() in ("LS", "L.S", "L.S.", "LUMPSUM", "LUMP SUM")
            if ls and amt:
                qty, rate, unit = (qty or 1.0), (rate or amt), (unit or "LS")
            if SIZE_LINE.match(desc) and intro and not LETTERED.match(desc):
                # "75mm diameter" alone says nothing - it is a size of the pipes the sentence above describes
                desc = f"{intro if len(intro) <= 110 else intro[:107].rsplit(' ', 1)[0] + '...'} - {desc}"
            measure = "qty" if (is_qty and (rate or qty) and not ls and not amt) else "pct"
            amount = round(amt, 2) if amt else (round((qty or 0) * (rate or 0), 2) if (qty and rate) else 0.0)
            done_pct = None
            if measure == "pct":
                if pct is not None:
                    done_pct = round(as_pct(pct), 4)
                elif cert_amt is not None and amount:
                    done_pct = round(100 * cert_amt / amount, 4)
            mine.append({"_calc": amt is None and bool(qty and rate) and "amount" in cols and has_pages,
                         "bill": bill, "bill_title": title[:120], "section": section[:200], "no": no[:20], "description": desc[:2000],
                         "qty": round(qty or 0, 4),
                         "unit": ("LS" if ls and not unit else unit)[:20], "rate": round(rate or 0, 4), "amount": amount,
                         "measure": measure, "words": words[:60], "remark": remark[:200],
                         "done_pct": done_pct, "done_qty": round(cert_qty, 4) if (measure == "qty" and cert_qty is not None) else None,
                         "claimed_qty": round(_n(r[cols["claim_qty"]]) or 0, 4) if "claim_qty" in cols else None,
                         "certified": round(cert_amt, 2) if cert_amt is not None else None,
                         "stage_pct": round(as_pct(pct), 4) if (measure == "qty" and pct) else None,
                         "rate_missing": bool(qty) and not rate and not amt and not words, "grp": ""})
            counts["lines"] += 1
            heads = []
        flush_pending("the sheet ends")
        if has_pages and pstart < len(mine):
            merge_page()
        if pstart < len(mine) and pages:
            pages.append({"label": "after the last page", "sheet": None, "lines": mine[pstart:]})
        # each page: its lines must make its own subtotal. A quantity x rate the BOQ left without an amount is not in
        # the page total (914: "bib tap 6 x 315", no amount) - it comes in at nil, said so.
        for pg in pages:
            if pg["sheet"] is None:
                continue
            got = round(sum(x["amount"] for x in pg["lines"]), 2)
            if abs(got - pg["sheet"]) < 0.01:
                continue
            calc = [x for x in pg["lines"] if x.get("_calc")]
            if calc and abs(round(got - sum(x["amount"] for x in calc), 2) - pg["sheet"]) < 0.01:
                for x in calc:
                    notes.append(f"{ws.title}: '{x['description'][:50]}' has {x['qty']:g} x {x['rate']:,.2f} but no amount in the BOQ - "
                                 f"brought in at nil, as the page total has it")
                    x["amount"], x["words"] = 0.0, "not priced"
                continue
            notes.append(f"{ws.title}: the page ending '{pg['label']}' says {pg['sheet']:,.2f}, its lines add up to {got:,.2f}")
        for x in mine:
            x.pop("_calc", None)
        page_sums = [round(sum(x["amount"] for x in pg["lines"]), 2) for pg in pages if pg["sheet"] is not None]
        # the sheet's COLLECTION: "BILL PAGE k/n" must be page k's own total - a page counted twice or left out is said
        bp = [(lab, v) for lab, v in rollups if BILL_PAGE.search(lab)]
        if bp and mine:
            for k, (lab, v) in enumerate(bp):
                own = page_sums[k] if k < len(page_sums) else None
                if own is None:
                    notes.append(f"{ws.title}: '{lab}' ({v:,.2f}) has no page of its own in the sheet")
                elif abs(round(v, 2) - own) >= 0.01:
                    twice = [j + 1 for j, q in enumerate(page_sums) if j != k and abs(q - round(v, 2)) < 0.01]
                    notes.append(f"{ws.title}: '{lab}' says {v:,.2f} but page {k + 1} adds up to {own:,.2f}"
                                 + (f" - it repeats page {twice[0]}'s total, so the sheet's collection counts that page twice" if twice else ""))
            if len(bp) < len(page_sums):
                notes.append(f"{ws.title}: the collection lists {len(bp)} pages, the sheet has {len(page_sums)}")
            nums = [re.search(r"(\d+)\s*/\s*(\d+)", lab) for lab, _ in bp]
            if any(m and int(m.group(2)) != len(bp) for m in nums):
                notes.append(f"{ws.title}: the collection is numbered '/{nums[0].group(2)}' but has {len(bp)} pages")
            seen = {}
            for lab, _ in bp:
                key = re.sub(r"\s+", " ", lab.upper())
                if key in seen:
                    notes.append(f"{ws.title}: '{lab}' is listed twice in the collection (the last one should be the next page)")
                seen[key] = 1
        if not mine:
            if rollups:
                summaries.append((ws.title, rollups))
            continue
        if not bill and has_pages:
            for x in mine:
                x["_sheet"] = ws.title                  # one bill per trade sheet - named once all sheets are read
        contract = round(sum(x["amount"] for x in mine), 2)
        certified = round(sum(x["certified"] or 0 for x in mine), 2)
        chk = {}
        if total_row is not None:
            t_amt = _n(total_row[cols["amount"]]) if "amount" in cols else None
            t_cert = _n(total_row[cols["cert_amt"]]) if "cert_amt" in cols else None
            if t_amt is not None:
                chk["contract"] = (round(t_amt, 2), abs(round(t_amt, 2) - contract) < 0.01)
            if t_cert is not None:
                chk["certified"] = (round(t_cert, 2), abs(round(t_cert, 2) - certified) < 0.01)
        for k, (v, ok) in chk.items():
            if not ok:
                notes.append(f"{ws.title}: lines add up to {contract if k == 'contract' else certified:,.2f}, the sheet's total row says {v:,.2f} ({k})")
        # every line: its % / quantity done x its amount / rate must give the certified figure printed beside it
        off = []
        for x in mine:
            if x["certified"] is None:
                continue
            calc = (x["amount"] * (x["done_pct"] or 0) / 100.0) if x["measure"] == "pct" else \
                ((x["done_qty"] or 0) * x["rate"] * ((x["stage_pct"] / 100.0) if x.get("stage_pct") else 1.0))
            if abs(round(calc, 2) - x["certified"]) > 0.01:
                off.append(f"{x['no'] or x['description'][:30]} ({calc:,.2f} v {x['certified']:,.2f})")
        if off:
            notes.append(f"{ws.title}: {len(off)} line(s) where done x amount is not the certified figure: {', '.join(off[:4])}")
            chk["lines"] = (len(off), False)
        missing = [x["description"][:50] for x in mine if x["rate_missing"]]
        if missing:
            notes.append(f"{ws.title}: {len(missing)} line(s) have a quantity but no rate - type the rate after bringing them in ({', '.join(missing[:4])}{'...' if len(missing) > 4 else ''})")
        # every description row of the sheet is accounted for: a line, an item in a group, a heading - or for review
        acc = counts["lines"] + counts["members"] + counts["headings"] + counts["review"]
        if acc != counts["rows"]:
            notes.append(f"{ws.title}: {counts['rows']} description rows in the file, {acc} accounted for - check the schedule")
        for x in mine:
            if x.get("review"):
                review.append(x["review"])
        if counts["groups"]:
            notes.append(f"{ws.title}: {counts['groups']} group(s) of items priced together (one lump sum each) - "
                         f"{counts['members']} items listed under their group, counted once")
        sheets.append({"sheet": ws.title, "bill": bill, "title": title, "lines": len(mine), "contract": contract, "certified": certified,
                       "check": {k: {"sheet": v, "ok": ok} for k, (v, ok) in chk.items()}, "unpriced": skipped,
                       "rows": dict(counts, accounted=acc)})
        items += mine
    # a BOQ of several trade sheets in bill pages (MEP_BOQ_HVAC / _ELECTRICAL / _PLUMBING): each sheet is its own bill
    paged = [sh for sh in sheets if any(x.get("_sheet") == sh["sheet"] for x in items)]
    if len(paged) > 1:
        for sh in paged:
            sh["bill"] = _bill_from_sheet(sh["sheet"]) or sh["sheet"][:20]
            for x in items:
                if x.get("_sheet") == sh["sheet"]:
                    x["bill"] = sh["bill"]
    for x in items:
        x.pop("_sheet", None)
        x.pop("_why", None)
        x.pop("_xr", None)
        x.pop("_parts", None)
        x.setdefault("grp", "")
    # the summary sheet ("TOTAL HVAC SYSTEMS 243,000"): each trade's figure there against its own sheet's lines
    for sname, rows_ in summaries:
        for lab, v in rows_:
            if re.search(r"grand|carried|all\b", lab, re.I) and not re.search(r"system|works", lab, re.I):
                continue
            words = set(re.findall(r"[a-z]{4,}", lab.lower().replace("systems", " ").replace("total", " ")))
            hit = next((sh for sh in sheets if words & set(re.findall(r"[a-z]{4,}", sh["sheet"].lower()))), None)
            if not hit:
                continue
            title_ = re.sub(r"^\s*total\s+", "", lab, flags=re.I).strip()
            title_ = re.sub(r"(?i)(electrical|plumbing|hvac)(systems)", r"\1 \2", title_)
            for x in items:
                if x["bill"] == hit["bill"] and not x["bill_title"]:
                    x["bill_title"] = title_.title().replace("Hvac", "HVAC")[:120]
            hit["title"] = hit["title"] or title_.title().replace("Hvac", "HVAC")
            if abs(round(v, 2) - hit["contract"]) >= 0.01:
                notes.append(f"{sname}: '{lab}' says {v:,.2f}, the lines of {hit['sheet']} add up to {hit['contract']:,.2f} "
                             f"(difference {v - hit['contract']:,.2f})")
                hit["check"]["summary"] = {"sheet": round(v, 2), "ok": False}
            else:
                hit["check"]["summary"] = {"sheet": round(v, 2), "ok": True}
    if not items:
        raise ValueError("No schedule lines found. Upload the agreement BOQ or a payment certificate with its Appendix / Bill sheets "
                         "(a heading row with Description and Amount or Rate).")
    # one sheet per bill (908) or one sheet only (915, 911): a single unnamed bill needs no bill code
    if len({x["bill"] for x in items}) == 1 and len(sheets) == 1:
        for x in items:
            x["bill"] = x["bill"] if x["bill"] not in ("A",) else ""
    return {"items": items, "sheets": sheets, "notes": notes, "review": review,
            "contract": round(sum(x["amount"] for x in items), 2),
            "certified": round(sum(x["certified"] or 0 for x in items), 2),
            "all_checked": all(c["ok"] for s in sheets for c in s["check"].values()) and all(s["check"] for s in sheets)}

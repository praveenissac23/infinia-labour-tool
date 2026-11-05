"""Read Infinia's internal BOQ workbook (the estimation team's priced take-off) into BOQ lines.

The file itself is never kept: it is read in memory and only the lines go into the database.

No fixed template (3 Nov 2026 - WS-25 R10 had SWIMMING POOL between 2.SUBSTR and 3.SUPERSTR, and the
summary numbered the bills 1 to 21 differently from the sheet names). The workbook explains itself:
  * its SUMMARY sheet lists the bills - number, name, amount (or words: Excluded, Phase 02, Rate only ...).
    Each BOQ sheet is matched to its summary line by NAME (PRELIM = Preliminaries, SUBSTR = Sub structure,
    SWIMMING POOL = Swimming pool & holding tank, FF & FA = Fire Fighting & Fire Alarm ...), with the order
    of the sheets as the tie-break - the bill is named and numbered as the summary has it;
  * a sheet (any name) is a BOQ sheet when it has "S/NO. | ITEMS | ... | AMOUNT" header rows;
  * a section is the heading just above a header row ("A. EARTHWORKS", "UNDERGROUND WATER TANK",
    "B. PUMP ROOM ... (From 907 Int.BOQ)") - lettered or not, notes beside it or not;
  * what is priced: the sheet's own SUMMARY block (A..H, in the order of the sections) and each section's
    TOTAL row say which sections count ("exclude", "Rate only" = not priced); the main SUMMARY says which
    bills count;
  * only priced lines in the priced scope come in. Lines with no price (By Client, Included, N/A, Phase 02,
    blank template rows) and sections / bills left out are NOT brought in - each is listed in the notes with
    its value, and either can be asked for (keep_unpriced / keep_out);
  * nothing is invented: every bill is tallied against its summary figure and a difference is SHOWN (never
    put in as a balancing line). Only a discount on the summary's grand total comes in as one line.
"""
import io
import re

import openpyxl

TITLE = re.compile(r"^\s*(\d{1,2})\s*[.\-)_ ]\s*([A-Za-z].*)$")     # "1.PRELIM", "2 SUBSTR", "3-SUPER", "4) FINISHES"
SECTION = re.compile(r"^\s*([A-Z])\s*[.)]\s*(.+)$")
OUT_WORDS = re.compile(r"(exclud|phase|n/?a$|not in|by client|by others|omit|rate only)", re.I)
NOT_BOQ = re.compile(r"(summary|cover|project details|price bank|ps amount|comparison)", re.I)


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
    neg = t.startswith("(") and t.endswith(")")            # (2,500.00) is a minus figure, as accountants write it
    try:
        x = float(t.strip("()").strip())
    except ValueError:
        return None
    return -x if neg else x


SMALL = {"And": "and", "Of": "of", "For": "for", "To": "to", "In": "in", "Ac": "AC", "A/C": "A/C", "Mep": "MEP", "Rcc": "RCC", "Ss": "SS",
         "Pt": "PT", "Ff": "FF", "Fa": "FA", "Lpg": "LPG", "Ug": "UG"}


def _bill_name(num, text):
    words = [SMALL.get(w, w) for w in re.sub(r"\s+", " ", text.strip()).title().split()]
    return (f"{int(num):02d}. " if num is not None else "") + " ".join(words)


def _header(row):
    """Column positions from an S/NO. header row, or None."""
    first = _s(row[0]).upper() if row else ""
    if not first.startswith("S/NO") and not first.startswith("S.NO") and first not in ("SNO", "S NO"):
        return None
    cols = {}
    for i, v in enumerate(row):
        t = _s(v).upper().replace(".", "").strip()
        if not t:
            continue
        if t in ("ITEM", "ITEMS", "DESCRIPTION", "ITEM DESCRIPTION") and "desc" not in cols:
            cols["desc"] = i
        elif t in ("IC QTY", "QTY", "QUANTITY") and "qty" not in cols:
            cols["qty"] = i
        elif t == "CONS QTY":
            cols["cons"] = i
        elif t == "UNIT" and "unit" not in cols:
            cols["unit"] = i
        elif t == "RATE" and "rate" not in cols:
            cols["rate"] = i
        elif t in ("AMOUNT", "LUMPSUM AMOUNT", "LUMP SUM AMOUNT", "TOTAL AMOUNT") and "amount" not in cols:
            cols["amount"] = i
        elif t == "SIZE":
            cols["size"] = i
        elif t == "TYPE":
            cols["type"] = i
    if "desc" not in cols or "amount" not in cols:
        return None
    if "qty" not in cols and "cons" in cols:
        cols["qty"] = cols["cons"]
    return cols


# ---- the summary sheet, and which sheet is which bill ----------------------------------------------------------

def _summary(wb):
    """The workbook's own summary sheet (the one listing the most bills): [{num, name, amount, words, note, pos}],
    its grand total, its name."""
    best = ([], None, "")
    for name in wb.sheetnames:
        if "SUMMARY" not in name.upper():
            continue
        out, total = [], None
        for row in wb[name].iter_rows(max_col=5, values_only=True):
            row = list(row) + [None] * 5
            m = re.match(r"^\s*(\d{1,2})\s*\.?\s*$", _s(row[0]))
            if m and _s(row[1]) and not any(x["num"] == int(m.group(1)) for x in out):
                v = row[2]
                out.append({"num": int(m.group(1)), "name": _s(row[1]), "amount": _n(v), "words": "" if _n(v) is not None else _s(v),
                            "note": _s(row[3]) if _n(row[3]) is None else "", "pos": len(out)})
            elif out and total is None and "TOTAL" in _s(row[1]).upper() and _n(row[2]) is not None:
                total = _n(row[2])
        if len(out) > len(best[0]):
            best = (out, total, name)
    return best


ABBR = {"ELEC": "ELECTRICAL", "FF": "FIRE FIGHTING", "FA": "FIRE ALARM", "WP": "WATERPROOFING", "SUBSTR": "SUBSTRUCTURE",
        "SUPERSTR": "SUPERSTRUCTURE", "AL": "ALUMINUM", "SS": "STAINLESS", "PRELIM": "PRELIMINARIES", "INT": "INTERNAL",
        "EXT": "EXTERNAL", "MECH": "MECHANICAL", "LV": "LOW CURRENT", "ELV": "LOW CURRENT", "UG": "UNDERGROUND", "AC": "AC"}
STOP = {"AND", "OF", "THE", "WORKS", "WORK", "ITEMS", "ITEM", "INCLUDING", "TOTAL", "FOR", "TO", "IN", "WITH", "OTHER", "OTHERS", "BOQ"}


def _words(text, expand=False):
    t = re.sub(r"[^A-Z ]", " ", str(text or "").upper().replace("&", " ").replace("A/C", "AC").replace("/", ""))
    out = []
    for w in t.split():
        if expand and w in ABBR:
            out += ABBR[w].split()
        elif len(w) >= 2 and w not in STOP:
            out.append(w)
    out = [w for w in out if w not in STOP]
    joined = [a + b for a, b in zip(out, out[1:])]          # "SUB STRUCTURE" also as "SUBSTRUCTURE"
    return out, out + joined


def _pfx(a, b):
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def _score(sheet_text, bill_name):
    mine, _ = _words(sheet_text, expand=True)
    _, theirs = _words(bill_name)
    s = 0
    for w in mine:
        best = max((_pfx(w, u) for u in theirs), default=0)
        if best >= 3 or (best == len(w) == 2):
            s += best
    return s


def _match(sheets, bills):
    """{sheet index: summary line}: by name, the order of the sheets breaking a tie."""
    pairs = []
    for i, sh in enumerate(sheets):
        for b in bills:
            sc = _score(sh["text"], b["name"])
            if sc >= 3:
                pairs.append((-sc, abs(i - b["pos"]), i, b["num"]))
    pairs.sort()
    got, used = {}, set()
    for _sc, _d, i, num in pairs:
        if i in got or num in used:
            continue
        got[i] = next(b for b in bills if b["num"] == num)
        used.add(num)
    return got


def _sheet_summary(rows):
    """A trade sheet's own SUMMARY block: [(letter, amount or None, words)] in order."""
    out, on = [], False
    for r in rows:
        first = _s(r[0]) if r else ""
        if first.upper().startswith("SUMMARY"):
            on = True
            continue
        if not on:
            continue
        if re.search(r"total", " ".join(_s(x) for x in r[:3]), re.I):
            continue
        m = re.match(r"^([A-Z])\s*[.)]?$", first)
        if m:
            val = next((v for v in list(r)[2:12] if _s(v) != ""), None)
            out.append((m.group(1), _n(val), "" if _n(val) is not None else _s(val)))
    return out


def _scope_word(words, note=""):
    w = (words or note or "").strip()
    if not w or w in ("-", "0"):
        return "Not in summary"
    if re.match(r"^exclud", w, re.I) or w.lower() == "exclude":
        return "Excluded"
    if re.match(r"^phase\s*0?2", w, re.I):
        return "Phase 02"
    if re.match(r"^n/?a$", w, re.I):
        return "N/A"
    if re.match(r"^rate\s*only", w, re.I):
        return "Rate only"
    return w[:40]


def _has_number(r, cols=None):
    idx = [cols[k] for k in ("qty", "rate", "amount") if k in cols] if cols else range(1, min(len(r), 12))
    return any(_n(r[i]) not in (None, 0.0) for i in idx if i < len(r))


# ---- one sheet --------------------------------------------------------------------------------------------------

def _read_sheet(ws, bill, keep_unpriced, keep_out):
    """(lines, sections [{name, scope, amount}], unpriced lines [desc], notes)."""
    hidden = {i for i, d in ws.row_dimensions.items() if d.hidden}
    numbered = [(i, list(r) + [None] * 6) for i, r in enumerate(ws.iter_rows(values_only=True), start=1) if i not in hidden]
    rows = [r for _, r in numbered]
    row_no = {id(r): i for i, r in numbered}               # iter_rows starts at A1: rows keep their sheet row numbers
    # Several items priced as ONE lump sum (a bracket beside them): the amount cell merged down their rows, the figure
    # in the top row (5 Nov 2026) - read as one group line with the lump sum, its items under it at nil, never dropped
    merged = [(m.min_row, m.max_row, m.min_col, m.max_col) for m in ws.merged_cells.ranges if m.max_row > m.min_row]
    notes = [f"{ws.title}: {len(hidden)} hidden row(s) left out."] if hidden else []
    ssum = _sheet_summary(rows)
    sections, section, cols, parent, mine, unpriced = [], None, None, "", [], []
    last_text = None             # the last row with words and no figures: a heading, if a header row follows
    pend, open_g, skip_to = [], None, 0
    heads_g = []                 # the words over the next group (a heading, the sentence under it)

    def g_line(desc, amt, words, r, grp):
        return {"bill": bill, "section": section["name"] if section else "", "code": (_s(r[0]) if grp != "head" else "")[:20], "description": desc[:500],
                "unit": ("LS" if grp == "head" else (_s(r[cols["unit"]]) if "unit" in cols else ""))[:20],
                "qty": 1.0 if grp == "head" else round(_n(r[cols["qty"]]) or 0.0, 4) if "qty" in cols else 0.0,
                "rate": round(amt or 0.0, 4) if grp == "head" else 0.0, "amount": round(amt, 2) if (grp == "head" and amt) else 0.0,
                "remark": words[:120] if grp == "head" else "", "scope": "", "_sec": section, "_raw": (amt or 0.0) if grp == "head" else 0.0, "grp": grp}

    def g_title():
        return (heads_g[0] if len(heads_g) >= 2 and len(heads_g[0]) <= 80 else " - ".join(heads_g)) or parent or "Lump sum"

    def flush_pend():
        nonlocal pend
        for r_ in pend:                  # items with no price and no group: listed with the unpriced lines (never dropped)
            x = g_line(_s(r_[cols["desc"]]), 0, "", r_, "")
            x["remark"] = "no price - not in a group"
            unpriced.append(x)
        pend = []

    def new_section(name):
        nonlocal section
        section = {"name": name, "scope": "", "amount": 0.0, "left": 0.0, "n": 0}
        sections.append(section)

    for r in rows:
        first = _s(r[0])
        up = first.upper()
        if up.startswith("SUMMARY") and not _s(r[1]):
            break
        h = _header(r)
        if h:
            # the heading above this header row names the section - lettered ("A. EARTHWORKS") or not ("UNDERGROUND WATER TANK")
            if last_text is not None:
                new_section(last_text)
            elif section is None:
                new_section("")
            cols, parent, last_text = h, "", None
            continue
        if up.startswith("PRICE COMPARISON") or up.startswith("SL.NO") or up.startswith("SL NO"):
            cols, last_text = None, None
            continue
        texts = [_s(x) for x in r[:12] if _s(x)]
        sm = SECTION.match(first)
        if sm and not _has_number(r):
            last_text = f"{sm.group(1)}. {sm.group(2).strip()}"
            if cols is not None:          # a lettered heading straight after items, before its own header row
                cols = None
            continue
        if not first and texts and not _has_number(r) and len(texts) == 1 and texts[0] == texts[0].upper() and len(texts[0]) > 5 \
                and not re.match(r"^(sub ?total|total)\b", texts[0], re.I):
            last_text = texts[0]          # an unlettered heading, e.g. "UNDERGROUND WATER TANK"
            continue
        if TITLE.match(first) and not _has_number(r):
            last_text = None              # the bill title row
            continue
        if cols is None:
            continue
        xr = row_no.get(id(r), 0)
        if xr and xr <= skip_to:
            continue
        acol, rcol = cols["amount"] + 1, (cols["rate"] + 1 if "rate" in cols else None)
        mg = next((m for m in merged if m[0] == xr and m[2] <= acol <= m[3]), None)
        top = r[cols["amount"]] if mg else None
        if mg:
            # a merged AMOUNT is a group's lump sum only when it is a figure and no row under it has a price of its own -
            # merged words ("N.A." over lines with their own rates, "Included in Item 21") are notes: rows read one by one
            inside = [rr for rr in rows if mg[0] < row_no.get(id(rr), 0) <= mg[1]]
            own = any(("rate" in cols and _n(rr[cols["rate"]])) or _n(rr[cols["amount"]]) for rr in inside)
            if not (_n(top) and _n(top) > 0) or own:
                mg = None
        if mg:
            # the bracket: every row of the merged price cell
            if section is None:
                new_section("")
            flush_pend()
            in_rows = [rr for rr in rows if mg[0] <= row_no.get(id(rr), 0) <= mg[1] and _s(rr[cols["desc"]])]
            amt_g = _n(top)
            words_g = ""
            t0 = in_rows[0] if in_rows else None
            titled = t0 is not None and len(in_rows) > 1 and not ("qty" in cols and _n(t0[cols["qty"]])) and not ("unit" in cols and _s(t0[cols["unit"]]))
            g = g_line(_s(t0[cols["desc"]]) if titled else g_title(), amt_g, words_g, r, "head")
            (mine if amt_g else unpriced).append(g)
            for rr in in_rows[1 if titled else 0:]:
                (mine if amt_g else unpriced).append(g_line(_s(rr[cols["desc"]]), 0, "", rr, "in"))
            skip_to, parent, heads_g, open_g, last_text = mg[1], "", [], None, None
            continue
        desc = _s(r[cols["desc"]])
        if not desc and pend and (_n(r[cols["amount"]]) or (_s(r[cols["amount"]]) and _n(r[cols["amount"]]) is None and _s(r[cols["amount"]]) not in ("-", "--", "0"))):
            # a price on a row of its own among items with none: those items, priced together (a bracket, no merged cell)
            if section is None:
                new_section("")
            a_ = _n(r[cols["amount"]])
            g = g_line(g_title(), a_, "" if a_ is not None else _s(r[cols["amount"]]), r, "head")
            (mine if a_ else unpriced).append(g)
            for r_ in pend:
                (mine if a_ else unpriced).append(g_line(_s(r_[cols["desc"]]), 0, "", r_, "in"))
            pend, open_g, heads_g, parent = [], (g if a_ else None), [], ""
            continue
        if not desc or re.match(r"^(sub ?total|total)\b", desc, re.I) or re.search(r"\btotal$", desc, re.I) or desc.upper().startswith("TOTAL"):
            if pend:
                flush_pend()
            open_g = None
            if desc and section is not None and re.match(r"^total$", desc, re.I) and not section["scope"]:
                w = " ".join(_s(x) for x in r[cols["desc"] + 1:] if _n(x) is None and _s(x))
                mo = OUT_WORDS.search(w)
                if mo:
                    section["scope"] = _scope_word(w[mo.start():])     # the section's own TOTAL says "exclude" / "Rate only"
            if desc:
                parent = ""
            continue
        last_text = None
        qty = _n(r[cols["qty"]]) if "qty" in cols else None
        unit = _s(r[cols["unit"]]) if "unit" in cols else ""
        rate = _n(r[cols["rate"]]) if "rate" in cols else None
        raw = r[cols["amount"]]
        amt = _n(raw)
        words = "" if amt is not None else _s(raw)
        if words in ("-", "--", "0"):
            words = ""
        if not amt and not words:
            if not (qty or rate or unit) and len(desc) > 6:
                parent = desc
                if pend:
                    flush_pend()
                open_g = None
                heads_g = (heads_g + [desc])[-2:]
            elif unit and not qty and not rate:
                # an item with only its unit: one of several priced together, waiting for the price - under the group
                # already open, or brought in as unpriced (never dropped). It still names a short line under it
                # ("Bicycle Parkings" over "Others"), as before.
                if len(desc) > 6:
                    parent = desc
                if section is None:
                    new_section("")
                if open_g is not None:
                    mine.append(g_line(desc, 0, "", r, "in"))
                else:
                    pend.append(r)
            elif qty or rate:
                # a take-off line with a quantity / rate and no amount: listed with the unpriced lines (was left out unsaid)
                if section is None:
                    new_section("")
                if pend:
                    flush_pend()
                open_g = None
                x = g_line(desc, 0, "", r, "")
                x["rate"], x["remark"] = round(rate or 0.0, 4), "no amount"
                unpriced.append(x)
            continue
        if pend:
            lsish = unit.strip().lower() in ("ls", "l.s", "l.s.", "lumpsum", "lump sum", "item", "lot", "job") or \
                ("rate" in cols and _s(r[cols["rate"]]).upper() in ("LS", "L.S", "L.S.", "LUMPSUM", "LUMP SUM"))
            # a numbered item is an item of its own: the rows above join it as one group only when neither it nor
            # they carry an item number (the Sanitary fittings bracket: "Clean Out, CO" ... no numbers)
            numbered = bool(first) or any(_s(r_[0]) for r_ in pend)
            if lsish and amt and not numbered:
                if section is None:
                    new_section("")
                g = g_line(g_title(), amt, words, r, "head")
                mine.append(g)
                for r_ in pend:
                    mine.append(g_line(_s(r_[cols["desc"]]), 0, "", r_, "in"))
                mine.append(g_line(desc, 0, "", r, "in"))
                pend, open_g, heads_g, parent = [], g, [], ""
                continue
            flush_pend()
        open_g = None
        heads_g = []
        if re.fullmatch(r"(others?|ohp)", desc, re.I) and not amt:
            continue
        if _n(unit) is not None:
            unit = ""
        if (not first or len(desc) <= 6) and parent:
            desc = f"{parent} - {desc}"
        extra = []
        if "size" in cols:
            a, b = _n(r[cols["size"]]), _n(r[cols["size"] + 1])
            if a and b:
                extra.append(f"{a:g} x {b:g} m")
        if "type" in cols and _s(r[cols["type"]]):
            extra.append(_s(r[cols["type"]]))
        if extra:
            desc += " (" + ", ".join(extra) + ")"
        if "qty" not in cols and "rate" not in cols:       # preliminaries: a lump sum
            qty, rate, unit = (1.0, amt, "LS") if amt else (0.0, 0.0, "LS")
        if section is None:
            new_section("")
        line = {"bill": bill, "section": section["name"], "code": first[:20], "description": desc[:500], "unit": unit[:20],
                "qty": round(qty or 0.0, 4), "rate": round(rate or 0.0, 4), "amount": round(amt, 2) if amt else 0.0,
                "remark": words[:120], "scope": "", "_sec": section, "_raw": amt or 0.0, "grp": ""}
        if not amt:
            unpriced.append(line)
            continue
        mine.append(line)
    if pend:
        flush_pend()
    # the sheet's own summary: one letter per section, in order
    if ssum and len(ssum) == len([s for s in sections if s["name"]]):
        for s, (_l, a, w) in zip([s for s in sections if s["name"]], ssum):
            if a is None or (w and OUT_WORDS.search(w)):
                s["scope"] = s["scope"] or _scope_word(w)
            elif a == 0 and not any(x["_sec"] is s for x in mine):
                s["scope"] = s["scope"] or "Not priced"
    elif ssum:
        notes.append(f"{ws.title}: its own summary has {len(ssum)} line(s) but {len([s for s in sections if s['name']])} section(s) were found - "
                     f"each section's TOTAL row was used instead.")
    for x in mine + unpriced:
        x["scope"] = x["_sec"]["scope"]
    for x in mine:
        s = x["_sec"]
        if s["scope"]:
            s["left"] = round(s["left"] + x["amount"], 2)
        else:
            s["amount"] = round(s["amount"] + x["amount"], 2)
            s["n"] += 1
    return mine, sections, unpriced, notes


# ---- the workbook -----------------------------------------------------------------------------------------------

def read_internal_boq(data: bytes, keep_unpriced=False, keep_out=False):
    """Lines, bills, tally and notes from an internal BOQ workbook.
    keep_unpriced: also bring lines with no price (By Client, Included, Phase 02 ...), at 0.
    keep_out: also bring sections / bills the workbook leaves out (kept aside, not counted)."""
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=False)
    summ, summary_total, summary_sheet = _summary(wb)
    # the BOQ sheets, in workbook order: any sheet with S/NO. header rows that is not the summary / cover / price bank
    sheets = []
    for ws in wb.worksheets:
        if NOT_BOQ.search(ws.title) and not TITLE.match(ws.title):
            continue
        has = False
        for r in ws.iter_rows(max_row=min(ws.max_row, 400), max_col=12, values_only=True):
            if _header(list(r) + [None] * 6):
                has = True
                break
        if not has:
            continue
        t1 = next((_s(r[0]) for r in ws.iter_rows(max_row=3, max_col=1, values_only=True) if TITLE.match(_s(r[0]))), "")
        sheets.append({"ws": ws, "text": f"{ws.title} {t1}", "title1": t1})
    match = _match(sheets, summ) if summ else {}
    lines, bills, notes, skipped = [], [], [], []
    for i, sh in enumerate(sheets):
        ws, b = sh["ws"], match.get(i)
        if b:
            bill = _bill_name(b["num"], b["name"])
        else:
            m = TITLE.match(sh["title1"]) or TITLE.match(ws.title)
            bill = _bill_name(int(m.group(1)), m.group(2)) if m else _bill_name(None, ws.title)
        bill_out = ""
        if b and b["amount"] is None:
            bill_out = _scope_word(b["words"], b["note"])
        elif b and not b["amount"]:
            bill_out = "Not priced"
        elif not b and summ:
            bill_out = "Not on the summary"
        if ws.sheet_state != "visible" and (bill_out or not b):
            continue                                       # a hidden sheet that is not priced: the template's spare trade
        mine, secs, unpriced, sn = _read_sheet(ws, bill, keep_unpriced, keep_out)
        notes += sn
        if bill_out:
            for x in mine + unpriced:
                x["scope"] = bill_out
        raw = sum(x["_raw"] for x in mine if not x["scope"])          # unrounded: the workbook's own figures
        counted = round(raw, 2)
        left = round(sum(x["amount"] for x in mine if x["scope"]), 2)
        if not mine and not unpriced:
            continue
        if bill_out and not counted:
            skipped.append({"bill": bill, "why": bill_out, "amount": left, "lines": len(mine)})
        take = [x for x in mine if keep_out or not x["scope"]] + ([x for x in unpriced if keep_out or not x["scope"]] if keep_unpriced else [])
        take.sort(key=lambda x: (secs.index(x["_sec"]) if x["_sec"] in secs else 0))
        if keep_unpriced:                                 # back into the workbook's order within each section
            order = {id(x): k for k, x in enumerate(mine + unpriced)}
            take.sort(key=lambda x: (secs.index(x["_sec"]) if x["_sec"] in secs else 0, order[id(x)]))
        for x in take:
            x.pop("_sec", None)
            x.pop("_raw", None)
        lines += take
        s_amt = b["amount"] if b else None
        diff = (raw - s_amt) if (s_amt is not None and not bill_out) else None
        if bill_out and not counted:
            continue
        bills.append({"bill": bill, "sheet": ws.title, "lines": len([x for x in take if not x["scope"]]), "counted": counted,
                      "summary": round(s_amt, 2) if s_amt is not None else None, "summary_words": (b["words"] or b["note"]) if b else "",
                      "diff": round(diff, 2) if diff is not None else None,
                      "ok": diff is None or abs(diff) < 0.01, "scope": bill_out, "left_out": left,
                      "sections_out": [{"name": s["name"] or "General", "why": s["scope"], "amount": s["left"]} for s in secs if s["scope"] and s["left"]],
                      "unpriced": len(unpriced)})
        if diff is not None and abs(diff) >= 0.01:
            notes.append(f"{bill}: the lines add up to {counted:,.2f}, the {summary_sheet} sheet says {s_amt:,.2f} - "
                         f"{abs(diff):,.2f} {'more' if diff > 0 else 'less'} - check that bill before saving.")
    if not lines:
        raise ValueError("No priced BOQ lines found. Upload the internal BOQ workbook (the sheets with S/NO. | ITEMS | ... | AMOUNT).")
    # bills on the summary with money but no sheet read
    read_nums = {match[i]["num"] for i in match}
    for b in summ:
        if b["amount"] and b["num"] not in read_nums:
            notes.append(f"The {summary_sheet} sheet lists {b['num']}. {b['name']} ({b['amount']:,.2f}) but no sheet was found for it.")
    total = round(sum(x["amount"] for x in lines if not x["scope"]), 2)
    # a discount on the summary itself (the grand total below the bills added up): one line, as the summary has it
    if summary_total is not None and summ:
        bills_sum = round(sum(b["amount"] or 0 for b in summ), 2)
        d = round(summary_total - bills_sum, 2)
        if abs(d) >= 0.01:
            lines.append({"bill": "99. Summary", "section": "", "code": "", "description": "Discount / rounding as per summary total",
                          "unit": "", "qty": 0.0, "rate": 0.0, "amount": d, "remark": "as per summary", "scope": ""})
            bills.append({"bill": "99. Summary", "sheet": summary_sheet, "lines": 1, "counted": d, "summary": d, "summary_words": "",
                          "diff": 0.0, "ok": True, "scope": "", "left_out": 0.0, "sections_out": [], "unpriced": 0})
            total = round(total + d, 2)
    unpriced_n = sum(b["unpriced"] for b in bills)
    return {"lines": lines, "bills": bills, "notes": notes, "skipped": skipped, "summary_sheet": summary_sheet,
            "summary_total": summary_total, "total": total, "left_out": round(sum(b["left_out"] for b in bills), 2),
            "unpriced": unpriced_n, "tally_ok": all(b["ok"] for b in bills) and (summary_total is None or abs(total - summary_total) < 0.015)}

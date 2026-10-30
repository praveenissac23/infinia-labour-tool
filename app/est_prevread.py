"""Previous records (Estimation > a project > Previous records): reading a certified client bill (IPA) and a
subcontractor payment certificate that were made before the app, so the history can be brought in.

The file is opened on the computer (portal/est/agreement.js - Excel, PDF, a scanned PDF or a photo, read by
text recognition on that computer); only its words come here, laid out in lines and cells. Every figure is read
from the cell beside its words on the certificate, and then checked against the certificate's own arithmetic -
the lines must add up to the amount due, the VAT must be 5% of it, the amount in words must say the same - so a
figure a scan misread shows up before anything is saved. Nothing is guessed: what is not found is left empty
for the QS to type, and the QS confirms every figure before it is saved.
"""
import re

import est_agreement as A
import est_docread as R

NUM = re.compile(r"\(?\s*-?\s*(?:AED|Dhs?\.?)?\s*\(?\s*-?\s*\d[\d,]*(?:\.\d+)?\s*\)?", re.I)


def _amounts(text, loose=False):
    """Every money figure in a piece of text, signed: (1,234.50), -1,234.50 and 'AED (1,234.50)' are negative.
    Percentages and dates are not money."""
    out = []
    t = text or ""
    for m in NUM.finditer(t):
        s = m.group(0)
        end = m.end()
        if end < len(t) and t[end:end + 1] == "%":
            continue
        if re.search(r"\d[./-]\d{1,2}[./-]\d{2,4}", t[max(0, m.start() - 1):end + 6]):
            continue
        digits = re.sub(r"[^\d.]", "", s)
        if not digits or digits.count(".") > 1:
            continue
        # a bare small integer (an item no., "IPC 12") is not an amount unless it carries decimals or a comma;
        # a whole-dirham total written without a comma (8522) is - but not a year standing alone (2026)
        if "." not in digits and "," not in s and not re.search(r"AED|Dh", s, re.I):
            if not loose or len(digits) < 4 or (len(digits) == 4 and 1990 <= int(digits) <= 2100):
                continue
        try:
            v = float(digits)
        except ValueError:
            continue
        neg = "(" in s or re.search(r"(^|\s)-\s*(AED\s*)?\d", s) is not None or s.strip().startswith("-")
        out.append(-v if neg else v)
    return out


def _money(vals):
    """The line's amount among its figures: the first one, passing over a bare fraction (0.0358 - a percentage
    written as a number in the column before the amount) when a real amount is on the line too."""
    real = [v for v in vals if abs(v) >= 1]
    return (real or vals)[0]


def _seq(label):
    """A bill / certificate number from its label: the last number once the revision and a year are taken off -
    "VE207/IPA/03 R1" -> 3, "914-IPA-07" -> 7, "IPA 07/2026" -> 7, "IPC 12" -> 12."""
    t = re.sub(r"[\s\-/(]*\b(R|Rev\.?|Revision)\s*\.?\s*\d+\s*\)?\s*$", "", label or "", flags=re.I)
    nums = [n for n in re.findall(r"\d+", t) if not (len(n) == 4 and 1990 <= int(n) <= 2100)]
    return int(nums[-1]) if nums else None


def _cells(l):
    return [str(c or "").strip() for c in (l.get("c") or [l.get("t", "")])]


def _row(lines, pat, start=0, stop=None, avoid=None):
    """The first line whose label matches `pat` (and not `avoid`) -> (index, the figures after the label).
    A line with the words but no figure (a heading) is passed over; a dash means none (0)."""
    rx = re.compile(pat, re.I)
    ax = re.compile(avoid, re.I) if avoid else None
    for i in range(start, len(lines) if stop is None else min(stop, len(lines))):
        cells = _cells(lines[i])
        for j, c in enumerate(cells):
            if rx.search(c) and not (ax and ax.search(c)):
                after = cells[j + 1:]
                inline = c[rx.search(c).end():]
                vals = _amounts(inline + " " + " ".join(after))
                if not vals:               # only a whole-dirham figure written without a comma (8522)
                    vals = _amounts(inline + " " + " ".join(after), loose=True)
                if vals:
                    return i, vals
                if any(re.fullmatch(r"[-–—]+|nil|n/?a", x.strip(), re.I) for x in after if x.strip()):
                    return i, [0.0]
                break
    return None, []


LABELISH = re.compile(r"^(date|measurement\s+date|project\s+code|ipc\b|inv\.?|invoice|commencement|agreement|scope|client|"
                      r"issue\s+date|interim\s+bill|contractor|sub-?contractor)\b", re.I)


def _value_after(cells, j, m):
    """The value written after a label: on the label's own cell after the colon, else the next cell that is not
    empty, not a lone colon and not the next label."""
    inline = cells[j][m.end():].strip(" :\t")
    if inline:
        return inline
    for x in cells[j + 1:j + 4]:
        x = x.strip()
        if not x or x == ":":
            continue
        x = x.lstrip(": ").strip()
        if not x or LABELISH.match(x):
            return ""
        return x
    return ""


def _find(lines, pat):
    """(cells, index, match) of the first cell that STARTS with the label."""
    rx = re.compile(r"^\s*(?:" + pat + r")", re.I)
    for l in lines:
        cells = _cells(l)
        for j, c in enumerate(cells):
            m = rx.match(c)
            if m:
                yield cells, j, m


def _date_cell(lines, pat):
    for cells, j, m in _find(lines, pat):
        v = _value_after(cells, j, m)
        d = A.a_date(v) if v else None
        if d:
            return d.isoformat()
    return ""


def _text_cell(lines, pat, maxlen=80):
    for cells, j, m in _find(lines, pat):
        v = _value_after(cells, j, m)
        if v:
            return v[:maxlen]
    return ""


def _only_figures(cells):
    t = " ".join(cells)
    return bool(_amounts(t)) and not re.search(r"[A-Za-z]{3,}", re.sub(r"\bAED\b|\bDhs?\b", "", t, flags=re.I))


def _join_ocr(lines):
    """A scan read by text recognition puts a figure on its own line, a few pixels above the words it belongs to
    (the figures are taller, the page a little crooked). Each figure-only line is put back on the line of words it
    stands beside - the nearest one just below it, else just above - so 'Retention   10,588.75' reads as one line.
    Typed PDFs and Excel are left as they are."""
    if not any(l.get("ocr") for l in lines):
        return lines
    out = [dict(l, c=_cells(l)) for l in lines]
    nodate = lambda t: re.sub(r"\d{1,2}[-/ .]?[A-Za-z]{3,9}[-/ .,]*\d{2,4}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4}", " ", t)
    words = [i for i, l in enumerate(out) if not _only_figures(l["c"]) and re.search(r"[A-Za-z]{3,}", nodate(" ".join(l["c"])))]
    taken = set()
    for i, l in enumerate(out):
        if not _only_figures(l["c"]):
            continue
        best = None
        for j in words:
            w = out[j]
            if w.get("p") != l.get("p") or j in taken or _amounts(" ".join(w["c"][1:])):
                continue
            dy = (w.get("y") or 0) - (l.get("y") or 0)
            if -4 <= dy <= 9:
                score = dy if dy >= 0 else 10 - dy
                if best is None or score < best[0]:
                    best = (score, j)
        if best:
            j = best[1]
            w = out[j]
            for k in ("x", "xe"):            # each cell keeps its place across the page (the rows are put together by it later)
                if isinstance(w.get(k), list) and isinstance(l.get(k), list) and len(w[k]) == len(w["c"]) and len(l[k]) == len(l["c"]):
                    w[k] = w[k] + l[k]
                else:
                    w.pop(k, None)
            w["c"] = w["c"] + l["c"]
            w["t"] = "  ".join(w["c"])
            l["c"], l["t"] = [], ""
            taken.add(j)
    return [l for l in out if l["c"]]


def _between(lines, i0, i1):
    """The figures on the lines between two lines (exclusive)."""
    vals = []
    for i in range(i0 + 1, i1):
        cells = _cells(lines[i])
        vals += _amounts(" ".join(cells))
    return vals


def _check(name, ok, detail):
    return {"name": name, "ok": bool(ok), "detail": detail}


# ---- a client bill (interim payment application / certificate) ------------------------------------------

def read_ipa(lines, flat):
    lines = _join_ocr(lines)
    f, checks, notes = {}, [], []
    bill = _text_cell(lines, r"(interim\s+bill|payment\s+application|ipa|interim\s+payment\s+(?:certificate|application)|certificate)\s*(no\.?|number|#)\s*:?", 30)
    if bill:
        f["bill_label"] = bill
        n = _seq(bill)
        if n is not None:
            f["seq"] = n
        elif re.search(r"final", bill, re.I):
            f["pc_type"] = "Final"
    d = _date_cell(lines, r"(issue|submission|bill|application)\s*date\s*:?") or _date_cell(lines, r"^\s*date\s*:?\s*")
    if d:
        f["submitted"] = f["period_to"] = d
    rows = {}
    pats = {
        "work": (r"(total\s+)?value\s+of\s+work\s+(done|executed)|gross\s+value\s+of\s+work|work\s+done\s+to\s+date", r"previous|variation"),
        "variation": (r"approved\s+variation|variations?\s+(executed|approved)", None),
        "advance": (r"advance\s+(payment\s+)?recover", None),
        "retention": (r"(less[:\s]*)?retention(?!\s+releas)", r"releas"),
        "release": (r"retention\s+releas|release\s+of\s+retention", None),
        "previous": (r"previous(ly)?\s+(progressive\s+)?(payments?|certified)|less\s+previous", None),
        "vat": (r"\b(5\s*%\s*)?(tax|vat)\b", r"excl|exclud|total\s+amount|trn"),
        "authority": (r"authorit", None),
        "total": (r"total\s+amount\s+(due|payable)|amount\s+due\s+for\s+payment|net\s+amount\s+(due|payable)", None),
    }
    for k, (p, av) in pats.items():
        i, vals = _row(lines, p, avoid=av)
        if i is not None:
            rows[k] = {"i": i, "v": _money(vals), "label": " ".join(_cells(lines[i]))[:90]}
    # other lines of the payment summary ("Add: Supervision Fee") - between the work done and the total
    extra = []
    if "work" in rows and "total" in rows:
        used = {r["i"] for r in rows.values()}
        for i in range(rows["work"]["i"] + 1, rows["total"]["i"]):
            if i in used:
                continue
            cells = [c for c in _cells(lines[i]) if c]
            if cells and re.match(r"\s*(add|less)\b", cells[0], re.I) and not any(re.search(p_, cells[0], re.I) for p_, _a in pats.values()):
                vals = _amounts(" ".join(cells[1:]) or cells[0])
                if vals:
                    sign = -1 if re.match(r"\s*less\b", cells[0], re.I) else 1
                    extra.append({"label": cells[0][:60], "v": sign * abs(vals[0])})
    if "vat" not in rows and "total" in rows:          # a scan that lost the word VAT: the line just above the total that says 5%
        for i in range(rows["total"]["i"] - 1, max(-1, rows["total"]["i"] - 4), -1):
            cells = _cells(lines[i])
            if re.search(r"5\s*%", " ".join(cells)) and _amounts(" ".join(cells).split("%", 1)[-1]):
                rows["vat"] = {"i": i, "v": _amounts(" ".join(cells).split("%", 1)[-1])[0], "label": " ".join(cells)[:90]}
                notes.append("VAT was read from the line marked 5% above the total - check it.")
                break
    work = rows.get("work", {}).get("v")
    var = rows.get("variation", {}).get("v") or 0.0
    if work is not None:
        f["claimed_cum"] = round(abs(work) + abs(var), 2)
        f["work"] = round(abs(work), 2)
        if var:
            f["variation"] = round(abs(var), 2)
    if "advance" in rows:
        f["adv_rec_cum"] = round(abs(rows["advance"]["v"]), 2)
    if "retention" in rows:
        f["ret_cum"] = round(abs(rows["retention"]["v"]), 2)
    if "release" in rows:
        f["ret_rel_cum"] = round(abs(rows["release"]["v"]), 2)
    for k in ("previous", "vat", "authority", "total"):
        if k in rows:
            f[k] = round(abs(rows[k]["v"]), 2)
    if extra:
        f["extra"] = extra
    # the certificate's own arithmetic
    if work is not None and "total" in rows:
        s = abs(work) + abs(var) - f.get("adv_rec_cum", 0) - f.get("ret_cum", 0) + f.get("ret_rel_cum", 0) - f.get("previous", 0) \
            + f.get("vat", 0) + f.get("authority", 0) + sum(e["v"] for e in extra)
        checks.append(_check("The lines add up to the amount due", abs(s - f["total"]) <= 1.0,
                             f"{s:,.2f} worked out, {f['total']:,.2f} on the bill" + (" (rounded to the dirham)" if 0.005 < abs(s - f["total"]) <= 1.0 else "")))
        net = s - f.get("vat", 0) - f.get("authority", 0)
        if f.get("vat"):
            checks.append(_check("VAT is 5% of the net", abs(net * 0.05 - f["vat"]) <= 0.05,
                                 f"5% of {net:,.2f} = {net * 0.05:,.2f}, the bill says {f['vat']:,.2f}"))
    # the amount in words written with the total (just under it) - not another figure in words elsewhere in the file
    w = None
    if "total" in rows:
        near = " ".join(" ".join(_cells(l)) for l in lines[rows["total"]["i"]:rows["total"]["i"] + 4])
        if re.search(r"dirham|only", near, re.I):
            w = R.words_amount(near)
    if w is not None and f.get("total") is not None:
        checks.append(_check("The amount in words says the same", abs(w - f["total"]) <= 0.5, f"words: {w:,.2f}"))
    if work is None:
        notes.append("The total value of work done was not found - type it from the bill.")
    found = [("seq", "Bill no."), ("submitted", "Issue date"), ("claimed_cum", "Work done to date"), ("adv_rec_cum", "Advance recovered"),
             ("ret_cum", "Retention"), ("previous", "Previous payments"), ("vat", "VAT"), ("total", "Amount due")]
    return R._out(f, found, notes, checks=checks)


# ---- a subcontractor payment certificate (Infinia's own IPC sheet) -------------------------------------

def read_subpc(lines, flat, subs=None):
    lines = _join_ocr(lines)
    f, checks, notes = {}, [], []
    no = _text_cell(lines, r"\b(IPC|payment\s+certificate|PC)\s*(no\.?|number|#)\s*:?", 12)
    n = _seq(no or "")
    if n is not None:
        f["seq"] = n
    f["inv_ref"] = _text_cell(lines, r"\binv(oice)?\.?\s*(ref|no)\.?\s*:?", 60)
    # the invoice date is the "Date :" on the invoice line
    for cells, j, m in _find(lines, r"inv(oice)?\.?\s*(ref|no)\b"):
        for k in range(j + 1, len(cells)):
            mm = re.match(r"^\s*date\s*:?", cells[k], re.I)
            if mm:
                d = A.a_date(_value_after(cells, k, mm))
                if d:
                    f["inv_date"] = d.isoformat()
                break
        break
    f["received"] = _date_cell(lines, r"inv(oice)?\.?\s*received\s*(date|on)\s*:?")
    f["issued"] = _date_cell(lines, r"(IPC|certificate)\s*issued\s*(date|on)\s*:?")
    f["measured_on"] = _date_cell(lines, r"measurement\s*date\s*:?")
    f["agreement"] = _text_cell(lines, r"agreement\s*ref\.?\s*:?", 60)
    f["scope_hint"] = _text_cell(lines, r"scope\s+of\s+work\s*:?", 90)
    # the subcontractor: the other "M/s." on the line that names Infinia (the details of both parties)
    name = ""
    for l in lines:
        cells = _cells(l)
        if not any(re.match(r"^\s*M\s*/\s*S\.?\s*INFINIA", c, re.I) for c in cells):
            continue
        for c in cells:
            mm = re.match(r"^\s*M\s*/\s*S\.?\s*(.+)", c, re.I)
            if mm and "infinia" not in mm.group(1).lower():
                name = re.split(r"\s+(?:P\.?\s*O\.?\s*Box|Office|Tel|Mob|TRN|Dubai|,)", mm.group(1), maxsplit=1, flags=re.I)[0].strip(" .,")
                break
        if name:
            break
    trns = re.findall(r"TRN\s*(?:No\.?)?\s*:?\s*(\d{15})", flat, re.I)
    trns = [t for t in trns if t != "100602393900003"]
    if trns:
        f["trn"] = trns[0]
    if name:
        f["sub_name"] = name
        best = R._match_sub(name, subs or [])
        if best is not None:
            f["sub_id"] = best
        else:
            f["new_sub"] = name.title().replace("Llc", "LLC").replace("L.L.C", "L.L.C") if name.isupper() else name
            notes.append(f"{f['new_sub']} is not a subcontractor on this project yet - add it as a new one below.")
    def amt(p, avoid=None):
        i, v = _row(lines, p, avoid=avoid)
        return (_money(v) if v else None), i
    f["work_cum"], _ = amt(r"value\s+of\s+work\s+executed\s+to\s+date|work\s+done\s+to\s+date", r"variation|total")
    f["var_cum"], _ = amt(r"value\s+of\s+variations?\s+executed")
    tot_work, _ = amt(r"total\s+value\s+of\s+work\s+executed")
    f["adv_cum"], _ = amt(r"^\s*advance\s+payment\s*$|^\s*advance\s+payment(?!\s+recover)", r"recover|IPC|PC\s*0")
    f["adv_rec_cum"], _ = amt(r"advance\s+(payment\s+)?recover")
    f["ret_cum"], _ = amt(r"^\s*retention(?!\s+releas)", r"releas")
    mat, _ = amt(r"material\s+supplied")
    man, _ = amt(r"manpower\s+supplied")
    plant, _ = amt(r"plant\s*(&|and)?\s*equipment\s+supplied")
    oth, oi = amt(r"other\s+deduction")
    f["ret_rel_cum"], _ = amt(r"retention\s+releas")
    prev, pi = amt(r"total\s+previou\w*\s+certified")
    net, ni = amt(r"net\s+amount\s+due")
    vat, _ = amt(r"^\s*vat\b|value\s+added\s+tax", r"trn|excl")
    total, ti = amt(r"total\s+amount\s+due")
    if prev is None:
        # the total of section E not read (a scan): the certificates listed above it, added up
        hi, _v = _row(lines, r"less\s*:?\s*previou\w*\s+certified")
        pl = next((i for i, l in enumerate(lines) if re.search(r"total\s+previou\w*\s+certified", " ".join(_cells(l)), re.I)), None)
        if hi is not None or pl is not None:
            h = next((i for i, l in enumerate(lines) if re.search(r"less\s*:?\s*previou\w*\s+certified", " ".join(_cells(l)), re.I)), None)
            if h is not None and pl is not None and pl > h:
                vals = _between(lines, h, pl)
                if vals:
                    prev = sum(abs(x) for x in vals)
                    notes.append(f"Previously certified worked out from the certificates listed: {prev:,.2f} - check it.")
    if vat is None and ni is not None and ti is not None and ti > ni:
        vals = _between(lines, ni, ti)
        if len(vals) == 1:
            vat = vals[0]
            notes.append("VAT was read from the line between the net amount and the total - check it.")
    parts = [x for x in (mat, man, plant, oth) if x]
    f["other_cum"] = round(sum(abs(x) for x in parts), 2) if parts else (0.0 if any(x is not None for x in (mat, man, plant, oth)) else None)
    why = []
    for lab, x in (("Material supplied", mat), ("Manpower supplied", man), ("Plant & equipment supplied", plant)):
        if x:
            why.append(f"{lab} {abs(x):,.2f}")
    if oth:
        lab = _cells(lines[oi])[0] if oi is not None else "Other deductions"
        lab = re.sub(r"^\s*other\s+deductions?\s*[-–:]*\s*", "", lab, flags=re.I) or "Other deductions"
        why.append(f"{lab} {abs(oth):,.2f}")
    if why:
        f["other_note"] = "; ".join(why)[:200]
    for k in ("work_cum", "var_cum", "adv_cum", "adv_rec_cum", "ret_cum", "ret_rel_cum"):
        if f.get(k) is not None:
            f[k] = round(abs(f[k]), 2)
    for k, x in (("prev_cert", prev), ("net", net), ("vat", vat), ("total", total), ("total_work", tot_work)):
        if x is not None:
            f[k] = round(abs(x), 2) if k != "net" else round(x, 2)
    # the certificate's own arithmetic: (A + B - C + D - E) = net, VAT 5%, total = net + VAT
    if f.get("work_cum") is not None and f.get("net") is not None:
        a = (f.get("work_cum") or 0) + (f.get("var_cum") or 0)
        if f.get("total_work") is not None:
            checks.append(_check("Work + variations = total work executed", abs(a - f["total_work"]) <= 0.05, f"{a:,.2f} / {f['total_work']:,.2f}"))
        s = a + (f.get("adv_cum") or 0) - (f.get("adv_rec_cum") or 0) - (f.get("ret_cum") or 0) - (f.get("other_cum") or 0) \
            + (f.get("ret_rel_cum") or 0) - (f.get("prev_cert") or 0)
        checks.append(_check("A + B - C + D - E = the net amount due", abs(s - f["net"]) <= 0.05, f"{s:,.2f} worked out, {f['net']:,.2f} on the certificate"))
    if f.get("net") is not None and f.get("vat") is not None:
        checks.append(_check("VAT is 5% of the net", abs(f["net"] * 0.05 - f["vat"]) <= 0.02, f"5% of {f['net']:,.2f} = {f['net'] * 0.05:,.2f}, certificate {f['vat']:,.2f}"))
    if f.get("net") is not None and f.get("vat") is not None and f.get("total") is not None:
        d = f["net"] + f["vat"] - f["total"]
        checks.append(_check("Net + VAT = total amount due", abs(d) <= 1.0, f"{f['net'] + f['vat']:,.2f} / {f['total']:,.2f}" + (" (rounded)" if 0.005 < abs(d) <= 1.0 else "")))
    if f.get("work_cum") is None:
        notes.append("The value of work executed to date was not found - type it from the certificate.")
    found = [("sub_id", "Subcontractor"), ("seq", "PC no."), ("inv_ref", "Invoice no."), ("issued", "Issued on"), ("work_cum", "Work to date"),
             ("var_cum", "Variations to date"), ("adv_cum", "Advance paid"), ("adv_rec_cum", "Advance recovered"), ("ret_cum", "Retention"),
             ("other_cum", "Deductions"), ("ret_rel_cum", "Retention released"), ("prev_cert", "Previously certified"), ("net", "Net due"), ("total", "Total due")]
    return R._out(f, found, notes, checks=checks)


R.READERS["ipa"] = read_ipa
R.READERS["subpc"] = read_subpc

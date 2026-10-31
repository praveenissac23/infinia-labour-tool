"""Contracts, letters of award and subcontract agreements: the parties, the contract value, advance and
retention %, dates.

The contract value is chosen among every figure the document gives for it (the labelled value, the figure in a
sentence "contract sum of AED ...", the value before and after VAT, the priced schedule's total, the amount in
words) by how many of the others agree with it - not by which comes first.
"""
import re
import time
from datetime import date, timedelta

from . import kv
from .numparse import a_date, numbers
from .tables import cell_numbers

VALUE_LABEL = re.compile(r"(?:sub-?\s*)?contract\s+(?:value|sum|price|amount)|lump\s*-?\s*sum(?:\s+price)?|accepted\s+contract\s+amount|"
                         r"total\s+contract\s+(?:value|price|sum|amount)|award(?:ed)?\s+(?:value|amount)|agreement\s+(?:value|amount)|"
                         r"(?:total\s+)?(?:po|lpo|order)\s+(?:value|amount)", re.I)
VAT_EX = re.compile(r"excl(?:\.|uding|usive)?\s*(?:of\s+)?(?:vat|tax)|before\s+vat|without\s+vat|plus\s+vat|\+\s*vat|vat\s+extra", re.I)
VAT_IN = re.compile(r"incl(?:\.|uding|usive)?\s*(?:of\s+)?(?:vat|tax)|with\s+vat|vat\s+included", re.I)


def _flat(doc):
    return re.sub(r"\s+", " ", "\n".join(r.text for r in doc.rows()))


def _strip_ms(v):
    return re.sub(r"^M\s*/\s*S\.?\s*", "", v or "", flags=re.I).strip(" .,:;")


def _value_cands(doc, flat):
    cands = []      # (value, score, why, cell)
    rows = doc.rows()
    for r in rows:
        txt = r.text
        m = VALUE_LABEL.search(txt)
        if not m:
            continue
        after = txt[m.end():]
        if re.search(r"\bvariation|\bwork\s+done|\bcertified|\bpaid\b|\bprevious", txt[:m.start()] + txt[m.end():m.end() + 25], re.I):
            continue
        ex = bool(VAT_EX.search(txt))
        inc = bool(VAT_IN.search(txt)) and not ex
        k = 0
        for c in r.cells:
            if c.x1 <= r.cells[0].x0 and c is not r.cells[0]:
                continue
            for v, pct, a, b, raw, fixed, ml in cell_numbers(c, r.ocr):
                if pct or not (ml or raw) or abs(v) < 1000:
                    continue
                # only figures after the label
                if c.text.find(m.group(0)) >= 0 and a < c.text.find(m.group(0)):
                    continue
                cands.append({"v": abs(v), "s": 1.0 - 0.15 * k, "why": "labelled", "ex": ex, "inc": inc, "cell": c})
                k += 1
    # a sentence: "... contract sum of AED 1,250,000.00 (exclusive of VAT)"
    for m in re.finditer(r"(?:contract\s+(?:sum|value|price|amount)|lump\s*sum|sub-?contract\s+(?:value|sum|price))[^.\d]{0,80}?"
                         r"(?:AED|Dhs?\.?|UAE\s+Dirhams?)\s*([\d,]+(?:\.\d{1,2})?)", flat, re.I):
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        tail = flat[m.end():m.end() + 60]
        cands.append({"v": v, "s": 0.85, "why": "sentence", "ex": bool(VAT_EX.search(tail)), "inc": bool(VAT_IN.search(tail)) and not VAT_EX.search(tail), "cell": None})
    return cands


def _schedule_total(doc):
    """The priced schedule: the largest 'Total' / 'Grand total' figure that equals the sum of the lines above it."""
    rows = doc.rows()
    best = None
    amounts = []
    for r in rows:
        nums = []
        for c in r.cells:
            for v, pct, a, b, raw, fixed, ml in cell_numbers(c, r.ocr):
                if not pct and (ml or raw):
                    nums.append(v)
        label = r.cells[0].text if r.cells else ""
        if re.match(r"\s*(grand\s+)?total|\s*sub[\s-]*total", label, re.I) and nums:
            tot = nums[-1]
            s = round(sum(amounts), 2)
            if abs(s - tot) <= max(1.0, tot * 0.0005) and tot > 0:
                if best is None or tot > best:
                    best = tot
            if re.match(r"\s*sub", label, re.I):
                continue
            amounts = []
        elif nums and len(nums) >= 2 and re.search(r"[A-Za-z]{3}", " ".join(c.text for c in r.cells)):
            amounts.append(nums[-1])
    return best


def read_contract(doc, kind="project"):
    t0 = time.perf_counter()
    rows = doc.rows()
    flat = _flat(doc)
    f, detail, notes, checks = {}, {}, [], []

    def tf(key, pat, maxlen=120, strip=False):
        v, c = kv.text_field(rows, pat, maxlen)
        if v:
            v = _strip_ms(v) if strip else v
            if v:
                f[key] = v
                detail[key] = {"value": v, "confidence": 0.8, "status": "ok", "where": c.where() if c else None}
    tf("name", r"(project\s+name|name\s+of\s+(?:the\s+)?(?:project|work)|project\s+title|project)\s*:?", 160)
    tf("client", r"(client|employer|owner)(\s+name)?\s*:?", 100, True)
    tf("consultant", r"(consultant|engineer|project\s+consultant|supervision\s+consultant)\s*:?", 100, True)
    tf("location", r"(location|plot\s+no\.?|project\s+location|site)\s*:?", 120)
    if not f.get("client"):
        m = re.search(r"between\s+((?:M/?S\.?\s+)?[A-Z][^,()]{2,80}?)\s*(?:\(|,)\s*(?:hereinafter[^)]*)?(?:the\s+)?[\"“]?(?:employer|client|owner)", flat, re.I)
        if m:
            f["client"] = _strip_ms(m.group(1))
    # the subcontractor (agreements)
    if kind == "agreement":
        v, c = kv.text_field(rows, r"(sub-?\s*contractor|vendor|supplier)(\s+name)?\s*:", 100)
        name = _strip_ms(v) if v and "infinia" not in v.lower() else ""
        if not name:
            m = re.search(r"\band\s+((?:M/?S)\.?\s+[A-Z][^,;\n(]{2,80}?)(?:,|\s+\(|\s+hereinafter|\s+having|\s+located|$)", flat)
            if m and "infinia" not in m.group(1).lower():
                name = _strip_ms(m.group(1))
        if name:
            f["sub_name"] = name
        m = re.search(r"\b([A-Z]{2,5}/[\w&\- ]{1,20}/(?:SCA|SC|SUB|SCO|AGR|AGM|LPO|PO)[\w]*/[\w/\-]{1,20})", flat)
        if m:
            f["agreement"] = m.group(1).strip().rstrip(".,;")
        else:
            v, c = kv.text_field(rows, r"(agreement|contract|lpo|po|order)\s*(no|ref|number)\.?\s*:?", 40)
            if v and re.search(r"\d", v):
                f["agreement"] = v
        trn = [t for t in re.findall(r"TRN\s*(?:No\.?)?\s*[:\-]?\s*(\d{15})", flat, re.I) if t != "100602393900003"]
        if trn:
            f["trn"] = trn[0]
        t = flat.lower()
        if re.search(r"re-?\s?measur|remeasur|measured contract|unit rate contract|based on actual quantit", t):
            f["contract_type"] = "Unit rate re-measurement contract"
        elif "lump sum" in t or "lumpsum" in t:
            f["contract_type"] = "Lump sum contract"
    # the contract value: every candidate, scored by how many others agree
    cands = _value_cands(doc, flat)
    sched = _schedule_total(doc)
    words = None
    for r in rows:
        if re.search(r"dirhams?|only", r.text, re.I) and re.search(r"thousand|hundred|million|lac", r.text, re.I):
            words = kv.words_amount(r.text)
            if words:
                break
    if sched:
        cands.append({"v": sched, "s": 0.6, "why": "schedule total", "ex": False, "inc": False, "cell": None})
    best = None
    for c in cands:
        sc = c["s"]
        agree = []
        for o in cands:
            if o is c:
                continue
            if abs(o["v"] - c["v"]) <= 0.5:
                sc += 0.5
                agree.append(o["why"])
            elif abs(o["v"] - c["v"] * 1.05) <= 1.0 and not c["inc"]:
                sc += 0.6                       # the other is this value plus VAT: this one is before VAT
                agree.append("with VAT")
                c["ex"] = True
        if words is not None and (abs(words - c["v"]) <= 0.5 or abs(words - c["v"] * 1.05) <= 1.0):
            sc += 0.7
            agree.append("amount in words")
        if c["inc"]:
            sc -= 0.4
        c["score"], c["agree"] = sc, agree
        if best is None or sc > best["score"]:
            best = c
    if best is not None:
        v = round(best["v"], 2)
        key = "contract_value" if kind == "project" else "value"
        f[key] = v
        conf = 0.6 + 0.15 * min(2, len(best["agree"]))
        detail[key] = {"value": v, "confidence": round(min(0.99, conf), 2), "status": "ok" if conf >= 0.8 else "check",
                       "where": best["cell"].where() if best["cell"] is not None else None, "note": ", ".join(best["agree"]) or best["why"]}
        if best["inc"]:
            notes.append("The contract value found includes VAT - check it.")
        if sched is not None:
            checks.append({"name": "The priced schedule adds up to the contract value", "ok": abs(sched - v) <= 1.0, "detail": f"schedule {sched:,.2f}"})
        if words is not None:
            checks.append({"name": "The amount in words says the same", "ok": abs(words - v) <= 0.5 or abs(words - v * 1.05) <= 1.0, "detail": f"words: {words:,.2f}"})
    # percentages: advance and retention
    for key, word in (("adv_pct", r"(?:mobili[sz]ation\s+)?advance(?:\s+payment)?"), ("ret_pct", r"retention(?:\s+money)?")):
        p = None
        m = re.search(word + r"[^.%\d]{0,70}?(\d{1,2}(?:\.\d+)?)\s*%", flat, re.I) or \
            re.search(r"(\d{1,2}(?:\.\d+)?)\s*%[^.%\d]{0,50}?" + word, flat, re.I)
        if m:
            p = float(m.group(1))
        if p is None:
            # "advance payment of AED 125,000" against the value
            m = re.search(word + r"[^.\d]{0,50}?(?:AED|Dhs?\.?)\s*([\d,]+(?:\.\d+)?)", flat, re.I)
            cv = f.get("contract_value") or f.get("value")
            if m and cv:
                x = float(m.group(1).replace(",", ""))
                q = round(x / cv * 100, 2)
                if 0 < q <= 50:
                    p = q
                    notes.append(f"{'Advance' if key == 'adv_pct' else 'Retention'} % worked out from AED {x:,.2f} of the contract value.")
        if p is not None and 0 < p <= 50:
            f[key] = p
            detail[key] = {"value": p, "confidence": 0.85, "status": "ok", "where": None}
    if VAT_EX.search(flat) or re.search(r"\bvat\b[^.]{0,30}5\s*%|5\s*%\s*vat", flat, re.I):
        f["vat_pct"] = 5.0
    # dates
    def dt(key, pat):
        d, c = kv.date_field(rows, pat)
        if not d:
            m = re.search(r"(?:" + pat + r")[^.\d]{0,40}?(\d{1,2}(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?[A-Za-z]{3,9}\.?,?\s+\d{4}|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})", flat, re.I)
            x = a_date(m.group(1)) if m else None
            d = x.isoformat() if x else ""
        if d:
            f[key] = d
            detail[key] = {"value": d, "confidence": 0.8, "status": "ok", "where": c.where() if c else None}
    dt("start_date", r"commencement\s+date|start\s+date|date\s+of\s+commencement|site\s+possession(?:\s+date)?|commence(?:ment)?\s+on")
    dt("end_date", r"completion\s+date|date\s+of\s+completion|end\s+date|to\s+be\s+completed\s+by")
    if kind == "agreement":
        d, c = kv.date_field(rows, r"(agreement\s+)?date\s*:?")
        if not d:
            m = re.search(r"made\s+(?:on|this)\s+(?:the\s+)?(.{0,40}?\d{4})", flat, re.I)
            x = a_date(m.group(1)) if m else None
            d = x.isoformat() if x else ""
        if d:
            f["agreement_date"] = d
    m = re.search(r"(?:duration|time\s+for\s+completion|contract\s+period|completion\s+period|period\s+of)[^.\d]{0,40}?(\d{1,3})\s*\(?[a-z\s-]*\)?\s*(months?|weeks?|days?)", flat, re.I)
    if m:
        n, u = int(m.group(1)), m.group(2).lower()
        f["duration"] = f"{n} {u}"
        if f.get("start_date"):
            d0 = date.fromisoformat(f["start_date"])
            if u.startswith("month"):
                y, mo = d0.year + (d0.month - 1 + n) // 12, (d0.month - 1 + n) % 12 + 1
                end = date(y, mo, min(d0.day, 28))
            else:
                end = d0 + timedelta(days=n * (7 if u.startswith("week") else 1))
            if f.get("end_date"):
                e = date.fromisoformat(f["end_date"])
                checks.append({"name": "Start + duration = completion", "ok": abs((e - end).days) <= 3, "detail": f"{end.isoformat()} worked out"})
            else:
                f["end_date"] = end.isoformat()
                detail["end_date"] = {"value": f["end_date"], "confidence": 0.6, "status": "derived", "note": f"start + {n} {u}"}
    found = [("name", "Project name"), ("client", "Client"), ("consultant", "Consultant"), ("location", "Location"), ("contract_value", "Contract value"),
             ("value", "Contract value"), ("adv_pct", "Advance %"), ("ret_pct", "Retention %"), ("start_date", "Start"), ("end_date", "Completion")]
    return {"fields": {k: v for k, v in f.items() if v not in (None, "")}, "found": [n for k, n in found if f.get(k) not in (None, "")],
            "notes": notes, "checks": checks, "detail": detail, "engine": "docread",
            "timing": dict(doc.timing, solve_ms=round((time.perf_counter() - t0) * 1000, 1))}

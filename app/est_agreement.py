"""A subcontract agreement read for the subcontract form - any layout, any number of pages.

The browser opens the file (PDF, Word or Excel) and sends only its text, line by line with the
cells of each line (portal/est/agreement.js). Nothing of the file is kept. Here the text is read
the way a QS reads an agreement:

  * the parties, the agreement number and date, the contract value and type, from the labels an
    agreement uses ("Contract value", "Sub-contractor", "Ref", "made on the 22nd day of ...");
  * the advance and retention %, and the payment stages as the certificate prints them;
  * the priced schedule - every line with an amount, its item number, its section (A, B, C ...),
    quantities and rates where given - chosen as the table whose lines add up to the contract value.

Every figure is checked: the schedule against the contract value, each section against its own
sub-total in the agreement. What could not be found is said, never guessed.
"""
import json
import re
from datetime import date

from fastapi import Body, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from database import get_db
import estimation as E

router = E.router

MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
MONEY = re.compile(r"^\(?-?(?:AED|Dhs?\.?|Dirhams?)?\s*(\d{1,3}(?:,\d{3})+(?:\.\d{0,2})?|\d+\.\d{2}|\d{4,}(?:\.\d{1,2})?)\s*(?:AED|/-)?\)?$", re.I)
MONEY_IN = re.compile(r"(?:AED|Dhs?\.?)\s*(\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)|(\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?)\s*(?:AED|Dirhams)", re.I)
PCT = re.compile(r"^(\d{1,3}(?:\.\d+)?)\s*%$")
CODE = re.compile(r"^(?:[A-Z]{1,3}[-.]?\d{1,3}(?:\.\d{1,3}){0,3}|\d{1,3}(?:\.\d{1,3}){0,3}\.?|\(?[a-z]\)|[ivx]{1,4}\))$")
UNITS = {"ls", "l.s", "l.s.", "lumpsum", "lump sum", "no", "no.", "nos", "nos.", "nr", "item", "items", "set", "sets", "m", "lm", "l.m", "rm", "rmt",
         "m2", "sqm", "sq.m", "m²", "m3", "cum", "cu.m", "m³", "kg", "ton", "tons", "mt", "pcs", "pc", "each", "ea", "job", "lot", "day", "days",
         "month", "months", "hr", "hrs", "hour", "hours", "sqft", "sft", "rft", "ltr", "l", "unit", "units", "pair", "pairs", "point", "points", "pt", "pts",
         "trip", "trips", "load", "loads", "visit", "visits", "week", "weeks",
         "bag", "bags", "roll", "rolls", "box", "boxes", "carton", "cartons", "ctn", "drum", "drums", "pail", "pails", "tin", "tins", "bundle", "bundles",
         "sheet", "sheets", "length", "lengths", "litre", "litres", "liter", "pkt", "packet", "packets", "coil", "coils", "bucket", "buckets", "can", "cans", "bottle", "bottles"}


def squash(s):
    """Letters only, lower case - 'S U B - C O N T R A C T O R' and 'Sub-Contractor' read the same."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def money(s):
    m = MONEY.match((s or "").strip().replace("AED ", "AED"))
    if not m:
        m = MONEY.match((s or "").strip())
    if not m:
        return None
    try:
        v = float(m.group(1).replace(",", "").rstrip("."))
    except ValueError:
        return None
    return -v if s.strip().startswith(("(", "-")) else v


def money_in(s):
    for m in MONEY_IN.finditer(s or ""):
        v = (m.group(1) or m.group(2) or "").replace(",", "")
        try:
            return float(v)
        except ValueError:
            pass
    return None


def a_date(s):
    """22 October 2026 / 22nd day of October, 2026 / October 22, 2026 / 22/10/2026 / 2026-10-22 / 22-Oct-26."""
    s = (s or "").replace(",", " ")
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?([A-Za-z]{3,9})\.?\s+(\d{2,4})", s)
    if m and m.group(2)[:3].lower() in MONTHS:
        y = int(m.group(3)); y = y + 2000 if y < 100 else y
        try:
            return date(y, MONTHS[m.group(2)[:3].lower()], int(m.group(1)))
        except ValueError:
            pass
    m = re.search(r"([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?\s+(\d{4})", s)
    if m and m.group(1)[:3].lower() in MONTHS:
        try:
            return date(int(m.group(3)), MONTHS[m.group(1)[:3].lower()], int(m.group(2)))
        except ValueError:
            pass
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    m = re.search(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b", s)
    if m:
        y = int(m.group(3)); y = y + 2000 if y < 100 else y
        try:
            return date(y, int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    m = re.search(r"\b(\d{1,2})-([A-Za-z]{3})-(\d{2,4})\b", s)
    if m and m.group(2).lower() in MONTHS:
        y = int(m.group(3)); y = y + 2000 if y < 100 else y
        try:
            return date(y, MONTHS[m.group(2).lower()], int(m.group(1)))
        except ValueError:
            pass
    return None


def unspace(s):
    """'J O I N E R Y  W O R K S' -> 'JOINERY WORKS' (letter-spaced headings)."""
    t = (s or "").strip()
    if re.fullmatch(r"(?:\S ){3,}\S(?: (?:\S ){1,}\S)*", t) and all(len(w) == 1 for w in t.split(" ")):
        return re.sub(r"(?<=\S) (?=\S)", "", t)
    return t


# ---- the lines, cleaned ---------------------------------------------------------------------------

def clean_lines(lines):
    """Page headers and footers (the same words on most pages, 'Page 3 of 12') are not the agreement."""
    out = [dict(l, c=[str(c or "").strip() for c in (l.get("c") or [l.get("t", "")])]) for l in lines if l]
    out = _merge_ocr_rows(out)
    pages = {l.get("p", 1) for l in out}
    if len(pages) >= 3:
        seen = {}
        for l in out:
            k = squash(" ".join(l["c"]))
            k = re.sub(r"\d+", "", k)
            seen.setdefault(k, set()).add(l.get("p", 1))
        rep = {k for k, ps in seen.items() if len(ps) >= max(3, len(pages) * 0.5) and k}
        out = [l for l in out if re.sub(r"\d+", "", squash(" ".join(l["c"]))) not in rep]
    out = [l for l in out if not re.match(r"^page\s*\d+\s*(of\s*\d+)?$", " ".join(l["c"]).strip(), re.I)]
    # the band at the top and the foot of each page: running heads and footers, wherever a scan put them
    ys = [l["y"] for l in out if "y" in l]
    if ys and len({l.get("p") for l in out}) >= 2:
        bottom = max(ys)
        for l in out:
            if "y" not in l or len(" ".join(l["c"])) >= 110:
                continue
            band = 28 if l.get("ocr") else 22          # a scan's footer sits less exactly
            contact = re.search(r"P\.?\s?O\.?\s*Box|\bTel\b|\bFax\b|www\.|@[a-z0-9-]+\.|\bMob(ile)?\b", " ".join(l["c"]), re.I)
            if l["y"] < 50 or l["y"] > bottom - band or (contact and (l["y"] < 90 or l["y"] > bottom - 70)):
                l["edge"] = 1
    for l in out:
        xs = l.get("x")
        if xs and len(xs) == len(l["c"]):
            xe = l.get("xe") if l.get("xe") and len(l["xe"]) == len(xs) else [x + 8 * len(c) for x, c in zip(xs, l["c"])]
            nc, nx, ne = [], [], []
            for c, x, e in zip(l["c"], xs, xe):
                parts = _split_figures([c])
                nc += parts
                if len(parts) == 1:
                    nx.append(x); ne.append(e)
                else:                                        # share the cell's width out by the length of each piece
                    tot = sum(len(q) + 1 for q in parts) or 1
                    pos = x
                    for q in parts:
                        w = (e - x) * (len(q) + 1) / tot
                        nx.append(round(pos)); ne.append(round(pos + w)); pos += w
            l["c"], l["x"], l["xe"] = nc, nx, ne
        else:
            l["c"] = _split_figures(l["c"])
            if xs:
                l.pop("x", None); l.pop("xe", None)
        l["t"] = "  ".join(c for c in l["c"] if c)
    return out


def _overlap(a, b):
    """Two pieces side by side (not one above the other): their cells do not cover the same x."""
    ax, bx = a.get("x") or [], b.get("x") or []
    return any(abs(x - y) < 8 for x in ax for y in bx)


def _merge_ocr_rows(out):
    """A scan's text comes in pieces: one table row can arrive as three 'lines' (the item no., the words,
    the amount) a pixel or two apart. Pieces at the same height on the same page are one line again."""
    if not any(l.get("ocr") for l in out):
        return out
    res = []
    for l in sorted(out, key=lambda l: (l.get("p", 1), l.get("y", 0))):
        prev = res[-1] if res else None
        if prev is not None and l.get("ocr") and prev.get("ocr") and prev.get("p") == l.get("p") and "x" in l and "x" in prev \
                and abs(l["y"] - prev["y"]) <= max(5, 0.7 * max(l.get("h") or 8, prev.get("h") or 8)) and not _overlap(prev, l):
            pe, le = prev.get("xe") or prev["x"], l.get("xe") or l["x"]
            cells = sorted(list(zip(prev["x"], prev["c"], pe)) + list(zip(l["x"], l["c"], le)))
            prev["x"], prev["c"], prev["xe"] = [c[0] for c in cells], [c[1] for c in cells], [c[2] for c in cells]
            prev["h"] = max(prev.get("h") or 0, l.get("h") or 0)
            prev["y"] = min(prev["y"], l["y"])
            continue
        res.append(dict(l))
    return res


_TAILNUM = re.compile(r"^(.*\S)\s+(\(?-?(?:AED\s*)?\d[\d,]*\.\d{2}\)?|\d{1,3}(?:\.\d+)?\s*%)$")


def _split_figures(cells):
    """A scanned line can run two columns together ('25.00 16,000.00', 'Total 534,000.00'): the sums of
    money at the end of a cell are put in cells of their own, so the amount column is found."""
    out = []
    for c in cells:
        tail = []
        while True:
            m = _TAILNUM.match(c)
            if not m or len(tail) >= 4:
                break
            tail.insert(0, m.group(2))
            c = m.group(1)
        out.append(c)
        out.extend(tail)
    return out


def blocks(lines):
    """Lines that belong together: on a PDF, lines closer than a line and a half (a table row with its
    wrapped description); in Word and Excel every line / table row stands alone."""
    out, cur = [], []
    for l in lines:
        if cur and "y" in l and "y" in cur[-1] and l.get("p") == cur[-1].get("p") \
                and 0 <= l["y"] - cur[-1]["y"] <= 1.45 * max(l.get("h") or 9, cur[-1].get("h") or 9):
            cur.append(l)
        else:
            if cur:
                out.append(cur)
            cur = [l]
    if cur:
        out.append(cur)
    return out


# ---- labelled fields ------------------------------------------------------------------------------

def _value_after(lines, i, j, keys):
    """The value of a label in cell j of line i: the next cell on the line, else the cell under it."""
    l = lines[i]
    cell = l["c"][j]
    # "Label: value" in one cell
    m = re.match(r"^[^:]{2,40}:\s*(.+)$", cell)
    if m and any(squash(cell.split(":")[0]).startswith(k) for k in keys):
        return m.group(1).strip()
    if j + 1 < len(l["c"]) and l["c"][j + 1] and not any(squash(l["c"][j + 1]).startswith(k) for k in LABELS_ALL):
        return l["c"][j + 1]
    # a row of labels with their values on the next line, in the same column
    for k in range(i + 1, min(i + 3, len(lines))):
        n = lines[k]
        if "x" in l and "x" in n and j < len(l.get("x") or []):
            x0 = l["x"][j]
            best = min(range(len(n["c"])), key=lambda q: abs((n.get("x") or [0] * len(n["c"]))[q] - x0)) if n["c"] else None
            if best is not None and abs(n["x"][best] - x0) <= 30 and n["c"][best]:
                return n["c"][best]
        elif len(n["c"]) == len(l["c"]) and n["c"][j]:
            return n["c"][j]
    return ""


LABELS = {
    "agreement": ["agreementno", "agreementref", "subcontractno", "subcontractref", "contractno", "contractref", "reference", "refno", "ref"],
    "date": ["contractdate", "agreementdate", "dateofagreement", "dateofcontract", "dateofissue", "issuedate", "issuedon", "dateissued", "orderdate",
             "lpodate", "podate", "workorderdate", "dated", "date"],
    "value": ["contractvalue", "contractamount", "subcontractamount", "subcontractvalue", "subcontractsum", "contractsum", "agreementvalue",
              "agreementamount", "lumpsumamount", "totalcontractvalue", "totalcontractamount", "lposum", "lpoamount", "lpovalue"],
    "type": ["contracttype", "typeofcontract", "natureofcontract"],
    "sub": ["subcontractor", "subcontractorname", "nameofsubcontractor", "secondparty", "contractor2"],
    "works": ["subcontractworks", "scopeofwork", "scopeofworks", "worksdescription", "descriptionofworks", "natureofwork", "subject", "works"],
    "start": ["commencementdate", "startdate", "dateofcommencement"],
    "lpo": ["lpono", "lponumber", "purchaseorderno", "pono"],
    "quote": ["quotationreference", "quotationref", "quotationno", "quoteref"],
}
LABELS_ALL = [k for v in LABELS.values() for k in v]


def find_label(lines, field, exact_first=True):
    keys = LABELS[field] if isinstance(field, str) else list(field)
    hits = []
    for i, l in enumerate(lines):
        for j, c in enumerate(l["c"]):
            sq = squash(c.split(":")[0] if ":" in c and len(c.split(":")[0]) < 40 else c)
            if not sq or len(sq) > 40:
                continue
            for rank, k in enumerate(keys):
                if sq == k or (sq.startswith(k) and len(sq) - len(k) <= 3):
                    v = _value_after(lines, i, j, keys)
                    if v:
                        hits.append((rank, i, v))
                    break
    hits.sort()
    return hits[0][2] if hits else ""


# ---- the whole reading ------------------------------------------------------------------------------

def read(lines, trades=None, names=None):
    raw = " ".join(" ".join(str(c) for c in (l.get("c") or [l.get("t", "")])) for l in lines if l)
    lines = clean_lines(lines)
    text = "\n".join(l["t"] for l in lines)
    flat = re.sub(r"\s+", " ", text)
    pflat = re.sub(r"\b\d{1,2}\.\d{1,2}\.(?=\s*\d)", " ", flat)      # "8.1.30% Advance" -> " 30% Advance" (clause numbers off)
    f, found, notes = {}, [], []

    # agreement number - the label, else a reference that looks like one (IC/909/SCA/01/26)
    ref = ""
    m = re.search(r"\b([A-Z]{2,5}/[\w&\- ]{1,20}/(?:SCA|SC|SUB|SCO|AGR|AGM|LPO|PO)[\w]*/[\w/\-]{1,20})", flat) or \
        re.search(r"\b([A-Z]{2,5}/[\w&\- ]{1,20}/(?:SCA|SC|SUB|SCO|AGR|AGM|LPO|PO)[\w]*/[\w/\-]{1,20})", raw)
    if m:
        ref = m.group(1).strip()
    if not ref:
        v = find_label(lines, "agreement")
        if v and re.search(r"\d", v) and len(v) <= 40:
            ref = v
    if ref:
        f["agreement"] = ref.rstrip(".,;")
        found.append("Agreement no.")

    v = find_label(lines, "lpo")
    if v and re.search(r"\d", v) and len(v) <= 30:
        f["lpo"] = v

    # date of the agreement
    d = None
    for k in ("date",):
        v = find_label(lines, k)
        d = a_date(v) if v else None
    if not d:
        m = re.search(r"made\s+(?:on|this)\s+(?:the\s+)?(.{0,40}?\d{4})", flat, re.I)
        d = a_date(m.group(1)) if m else None
    if d:
        f["agreement_date"] = d.isoformat()
        found.append("Agreement date")
    v = find_label(lines, "start")
    if v and a_date(v):
        f["start_date"] = a_date(v).isoformat()
        found.append("Commencement date")

    # contract value
    val = None
    v = find_label(lines, "value")
    if v:
        val = money_in(v) if money_in(v) is not None else money(v)
    if val is None:
        m = re.search(r"(?:contract|sub-?contract)\s+(?:value|amount|sum|price)[^.\d]{0,60}?(?:AED|Dhs?\.?)\s*([\d,]+(?:\.\d{1,2})?)", flat, re.I)
        if m:
            val = float(m.group(1).replace(",", ""))
    if val is not None:
        f["value"] = round(val, 2)
        found.append("Contract value")

    # contract type
    t = (find_label(lines, "type") + " " + flat[:20000]).lower()
    if re.search(r"re-?\s?measur|remeasur|measured contract|unit rate contract|based on actual quantit", t):
        f["contract_type"] = "Unit rate re-measurement contract"
    elif "lump sum" in t or "lumpsum" in t:
        f["contract_type"] = "Lump sum contract"
    elif "manpower" in t and "rate" in t:
        f["contract_type"] = "Manpower rates"
    if f.get("contract_type"):
        found.append("Contract type")

    # the subcontractor
    name = ""
    v = find_label(lines, "sub")
    if v and not re.search(r"infinia", v, re.I) and len(v) < 90 and not re.match(r"^(hereinafter|shall|the\b)", v, re.I):
        name = v
    if not name:
        m = re.search(r"\band\s+((?i:M/?S)\.?\s+[A-Z][^,;\n(]{2,80}?)(?:,|\s+\(|\s+hereinafter|\s+having|\s+located|$)", text)
        if m and "infinia" not in m.group(1).lower():
            name = m.group(1)
    if not name:
        for l in lines:
            for c in l["c"]:
                if re.match(r"^M/?S\.?\s+\S", c, re.I) and "infinia" not in c.lower():
                    name = c
                    break
            if name:
                break
    name = re.sub(r"^M/?S\.?\s*", "", name, flags=re.I).strip(" .,:")
    if name:
        f["name"] = name
        found.append("Subcontractor")
        # its address: the line under the name, same column
        for i, l in enumerate(lines):
            if any(name in c for c in l["c"]) and i + 1 < len(lines):
                j = next(k for k, c in enumerate(l["c"]) if name in c)
                n = lines[i + 1]
                if "x" in l and "x" in n and n["c"]:
                    q = min(range(len(n["c"])), key=lambda q: abs(n["x"][q] - l["x"][j]))
                    if abs(n["x"][q] - l["x"][j]) < 30 and not re.search(r"represent", n["c"][q], re.I):
                        f["address"] = n["c"][q]
                break
        m = re.search(r"\bTRN\s*(?:No\.?)?\s*[:\-]?\s*(\d{15})", flat)
        if m:
            f["trn"] = m.group(1)

    # the work: "Joinery Works" in the title, else the scope of works
    works = ""
    for l in lines[:25]:
        for c in l["c"]:
            u = unspace(c)
            m = re.search(r"(?:agreement|contract)\s*[—–:\-]\s*([A-Za-z&/,\- ]{3,40}?)\s+works?\b", u, re.I) or \
                re.match(r"^([A-Za-z&/,\- ]{3,40}?)\s+works?\b", u, re.I)
            if m and not re.search(r"agreement|contract|sub|terms|scope", m.group(1), re.I):
                works = m.group(1).strip(" -,")
                break
        if works:
            break
    desc = find_label(lines, "works")
    if not works and desc:
        m = re.search(r"(?:of|for)\s+([A-Za-z&/ ]{3,40}?)\s+works", desc, re.I)
        works = m.group(1) if m else ""
    if works and re.search(r"\bof\b", works, re.I):
        works = re.split(r"\bof\b", works, flags=re.I)[-1].strip()       # "Maintenance of Elevator" -> "Elevator"
    if works:
        f["scope"] = works.strip().title() if works.isupper() else works.strip()[:1].upper() + works.strip()[1:]
        found.append("Work")
    if desc:
        # the full description, kept with the subcontract
        i = next((k for k, l in enumerate(lines) if desc in l["c"]), None)
        full = desc
        if i is not None:
            for n in lines[i + 1:i + 6]:
                if len(n["c"]) == 1 and "x" in n and "x" in lines[i] and len(lines[i]["x"]) > 1 and abs(n["x"][0] - lines[i]["x"][-1]) < 12:
                    full += " " + n["c"][0]
                else:
                    break
        f["works"] = full
    if trades:
        hay = (f.get("scope", "") + " " + f.get("works", "")).lower()
        KEY = [("Joinery", ["joinery", "carpentry", "wood", "cabinet", "wardrobe", "kitchen"]),
               ("MEP", ["mep", "electrical", "plumbing", "hvac", "mechanical", "elevator", "lift", "fire fighting", "firefighting", "drainage"]),
               ("Aluminium", ["aluminium", "aluminum", "glazing", "window", "curtain wall", "facade"]),
               ("Steel", ["steel structure", "structural steel", "metal work", "metalwork", "steel works"]),
               ("Finishes", ["paint", "tiling", "gypsum", "ceiling", "flooring", "marble", "plaster", "waterproof"]),
               ("External", ["landscap", "pool", "external works", "paving", "boundary wall"]),
               ("Manpower", ["manpower", "labour supply", "labor supply"]),
               ("Civil", ["civil", "concrete", "blockwork", "shoring", "piling", "excavation", "structure", "foundation"])]
        best = ""
        for k, ws in KEY:                               # what the work is, not a word like "supply" in every agreement
            if any(w in hay for w in ws):
                best = next((tr for tr in trades if k.lower() in tr.lower()), "")
                if best:
                    break
        if best:
            f["trade"] = best
    v = find_label(lines, "quote")
    if v:
        f["quote"] = v

    # money tables: the schedule and the payment stages
    tables = _tables(lines)
    pay = [t for t in tables if t["pct_rows"] >= max(2, len(t["rows"]) * 0.5)]
    sched = [t for t in tables if t not in pay and t["rows"]]
    target = f.get("value")
    best = None
    for t in sched:
        s = round(sum(r["amount"] for r in t["rows"]), 2)
        t["sum"] = s
        score = (1 if target is not None and abs(s - target) < 1 else 0,
                 1 if t["total"] is not None and abs(s - t["total"]) < 1 else 0, len(t["rows"]))
        if best is None or score > best[0]:
            best = (score, t)
    items = []
    checks = {}
    if best:
        t = best[1]
        items = [{k: r[k] for k in ("bill", "bill_title", "section", "no", "description", "qty", "unit", "rate", "amount")} for r in t["rows"]]
        checks["items"] = len(items)
        checks["items_total"] = t["sum"]
        checks["total_in_doc"] = t["total"]
        if target is None and t["total"] is not None:
            f["value"] = t["total"]
            found.append("Contract value (from the schedule total)")
            target = t["total"]
        checks["contract_value"] = target
        checks["match"] = target is not None and abs(t["sum"] - target) < 1
        checks["sections"] = []
        for b, st in t["subtotals"]:
            got = round(sum(r["amount"] for r in t["rows"] if r["bill"] == b), 2)
            checks["sections"].append({"bill": b, "total": got, "in_doc": st, "ok": abs(got - st) < 1})
        if not checks["match"] and target is not None:
            notes.append(f"The schedule adds up to {t['sum']:,.2f}, not the contract value {target:,.2f} - check the lines before saving.")
    elif f.get("value") and f.get("contract_type") == "Lump sum contract":
        items = [{"bill": "", "bill_title": "", "section": "", "no": "1", "description": (f.get("works") or f.get("scope") or "Subcontract works")[:400].strip(),
                  "qty": 1, "unit": "LS", "rate": f["value"], "amount": f["value"]}]
        checks = {"items": 1, "items_total": f["value"], "total_in_doc": None, "contract_value": f["value"], "match": True, "sections": []}
        notes.append("The agreement has no priced schedule - one lump-sum line is made from the contract amount, certified by % done.")
    else:
        notes.append("No priced schedule was found in the file - the item schedule can be pasted or imported afterwards.")

    # payment terms: advance, stages, retention
    adv = None
    stages = []
    if pay:
        p = max(pay, key=lambda t: t["pct_rows"])
        for r in p["rows"]:
            if r.get("pct") is None:
                continue
            g = (r.get("group") or "")
            words = r["description"]
            stages.append({"pct": r["pct"], "text": words, "group": g, "amount": r["amount"]})
            if adv is None and re.search(r"advance", g + " " + words, re.I):
                adv = r["pct"]
    if not stages:
        stages = _stages_in_text(lines)
        for s_ in stages:
            if adv is None and re.search(r"advance", s_["text"], re.I):
                adv = s_["pct"]
    if adv is None:
        m = re.search(r"(?<![\d.])(\d{1,2}(?:\.\d+)?)\s*%\s*(?:of the (?:sub-?)?contract (?:value|amount)\s*)?(?:as\s+)?(?:an?\s+)?advance", pflat, re.I) or \
            re.search(r"advance(?:\s+payment)?\s+(?:of\s+)?(\d{1,2}(?:\.\d+)?)\s*%", pflat, re.I)
        if m:
            adv = float(m.group(1))
    if adv is not None:
        f["adv_pct"] = adv
        found.append("Advance %")
    m = re.search(r"retention\s+(?:money\s+)?(?:of\s+)?(\d{1,2}(?:\.\d+)?)\s*%", pflat, re.I) or \
        re.search(r"(?<![\d.])(\d{1,2}(?:\.\d+)?)\s*%\s*(?:of\s+[a-z ]{0,30})?retention", pflat, re.I)
    if m:
        f["ret_pct"] = float(m.group(1))
        found.append("Retention %")
    if re.search(r"excl(?:uding|usive of|\.)?\s*(?:of\s+)?VAT|exclusive\s+of\s+VAT|plus\s+VAT|\+\s*VAT", flat, re.I):
        f["vat_pct"] = 5.0
    elif re.search(r"zero[- ]rated|VAT\s*(?:@|at)?\s*0\s*%", flat, re.I):
        f["vat_pct"] = 0.0
    terms = []
    for s_ in stages:
        g = s_.get("group") or ""
        lead = "advance" if re.search(r"advance", g + s_["text"], re.I) and not re.match(r"advance", s_["text"], re.I) else ""
        txt = s_["text"].rstrip(".")
        terms.append(f"{s_['pct']:g}% {lead + ' - ' if lead else '- '}{txt[:1].lower() + txt[1:]}" +
                     (f" ({g.split('—', 1)[-1].split('-', 1)[-1].strip()})" if lead and ("—" in g or " - " in g) else ""))
    if not terms and f.get("adv_pct"):
        terms.append(f"{f['adv_pct']:g}% advance" + (" against security cheque" if re.search(r"cheque|guarantee", flat, re.I) else ""))
    if not stages and re.search(r"interim|progress(?:ive)?\s+payment|monthly", flat, re.I):
        terms.append(f"{100 - (f.get('adv_pct') or 0):g}% progressive payment after certification" if f.get("adv_pct") else "100% progressive payment after certification")
    if f.get("ret_pct"):
        terms.append(f"{f['ret_pct']:g}% retention")
    if terms:
        f["pay_terms"] = "\n".join(terms)
        found.append("Payment terms")
    if f.get("value") is not None and stages:
        tot = round(sum(s_["pct"] for s_ in stages), 2)
        if abs(tot - 100) > 0.01:
            notes.append(f"The payment stages add up to {tot:g}%, not 100%.")
    f["kind"] = "LPO" if f.get("lpo") and not f.get("agreement") and re.search(r"purchase order|\bLPO\b", flat[:3000], re.I) else "Subcontract"
    return {"fields": f, "items": items, "checks": checks, "stages": stages, "found": found, "notes": notes}


def _stages_in_text(lines):
    """Payment terms written as a numbered list, not a table: '8.1. 30% Advance payment / 8.2. 50% upon complete
    material delivery to site ...' - each stage with its %, the words carried over the line ends."""
    start = next((i for i, l in enumerate(lines) if re.search(r"terms\s+of\s+payment|payment\s+terms|payment\s+schedule|mode\s+of\s+payment", l["t"], re.I)), None)
    if start is None:
        return []
    head = re.match(r"^\s*(\d{1,2})\.", lines[start]["t"])
    out = []
    for l in lines[start + 1:start + 40]:
        t = l["t"].strip()
        if re.match(r"^(note|remarks?)\b", t, re.I) or (head and re.match(r"^(\d{1,2})\.\s*[A-Z]", t) and re.match(r"^(\d{1,2})\.", t).group(1) != head.group(1)
                                                        and not re.match(r"^\d{1,2}\.\d", t)):
            break
        t2 = re.sub(r"^\d{1,2}(?:\.\d{1,2})?\.?\s*(?=\d{1,3}(?:\.\d+)?\s*%)", "", t)       # "8.1.30% ..." -> "30% ..."
        if t2 == t:
            t2 = re.sub(r"^\d{1,2}(?:\.\d{1,2})*\.?\s+", "", t)
        m = re.match(r"^(\d{1,3}(?:\.\d+)?)\s*%\s*(.+)$", t2)
        bullet = re.match(r"^(?:[a-z][.)]|\([a-z]\)|[ivx]+[.)])\s*(.+)$", t)
        if m and not bullet:
            out.append({"pct": float(m.group(1)), "text": m.group(2).strip().rstrip("."), "group": "", "amount": None})
        elif out and bullet:                     # the parts of a stage: "a. 10% of advance upon signing ..."
            out[-1]["text"] += ("; " if ":" in out[-1]["text"] else ": ") + bullet.group(1).strip().rstrip(".")
        elif out and len(t) < 160 and not re.match(r"^\d", t):
            out[-1]["text"] += " " + t.rstrip(".")
    return out if 0 < sum(s["pct"] for s in out) <= 100.01 and len(out) >= 2 else []


def _cells_of(line):
    return [c for c in line["c"] if c]


def _tables(lines):
    """Every run of rows with amounts, with its sections, sub-totals and total."""
    tables, cur = [], None
    bill, bill_title, group = "", "", ""

    def close():
        nonlocal cur
        if cur and (cur["rows"] or cur["total"] is not None):
            tables.append(cur)
        cur = None

    for blk in blocks(lines):
        if all(l.get("edge") for l in blk):
            continue                      # a page head or foot - the table carries on across it
        mlines = [l for l in blk if _row_money(l) is not None]
        texts = [" ".join(_cells_of(l)) for l in blk]
        joined = " ".join(texts).strip()
        if not mlines:
            one = joined
            if len(blk) <= 2 and len(one) < 140 and re.search(r"\b(advance|progressive|progress|retention|interim)\b.*\bpayment|\bpayment\b.*\b(advance|progress)", one, re.I):
                group = one               # "Advance payment - against ..." heads the stages under it
                continue
            if len(blk) == 1 and re.match(r"^(?:section|bill|part|schedule)\s+[A-Z0-9]{1,3}\b", one, re.I) and len(one) < 160:
                m = re.match(r"^(?:section|bill|part|schedule)\s+([A-Z0-9]{1,3})\s*[—–:\-.]?\s*(.*)$", one, re.I)
                bill, bill_title = m.group(1).upper(), _tidy_title(m.group(2))
                group = ""
                if cur is None:
                    cur = _new_table()
                continue
            if _heading_block(blk) and not (len(blk) == 1 and one.isupper() and len(one) > 30):
                continue                  # column titles (a table carried on to the next page)
            if cur is not None and len(blk) <= 2 and len(one) < 140 and not re.match(r"^\d+\.\s", one):
                if one.isupper() and len(one) > 6 and not re.search(r"\d", one):
                    bill_title = _tidy_title(one)
                continue                  # a heading row or column titles inside a table
            if cur is not None and (len(blk) >= 2 or len(joined) > 140 or re.match(r"^\d+\.\s", one)):
                close()
                bill, bill_title, group = "", "", ""
            continue
        rows = [blk] if len(mlines) == 1 else [[l] for l in blk if _row_money(l) is not None]
        for rb in rows:
            ml = next(l for l in rb if _row_money(l) is not None)
            amt = _row_money(ml)
            cells = _cells_of(ml)
            label = " ".join(c for c in cells if money(c) is None and not PCT.match(c)).strip()
            if re.search(r"\btotal\b", label, re.I) and not re.search(r"\btotal\s+of\s+\d", label, re.I):
                if cur is None:
                    continue
                if re.search(r"sub[- ]?total", label, re.I):
                    m = re.search(r"section\s+([A-Z0-9]{1,3})\b|bill\s+([A-Z0-9]{1,3})\b", label, re.I)
                    b = (m.group(1) or m.group(2)).upper() if m else bill
                    cur["subtotals"].append((b, amt))
                else:
                    cur["total"] = amt
                    close()
                    bill, bill_title, group = "", "", ""
                continue
            if cur is None:
                cur = _new_table()
            row = _row(rb, ml, amt)
            row["bill"] = bill or (re.match(r"^([A-Z]{1,2})[-.]?\d", row["no"]).group(1) if re.match(r"^[A-Z]{1,2}[-.]?\d", row["no"] or "") else "")
            row["bill_title"] = bill_title
            row["section"] = ""
            row["group"] = group
            if row.get("pct") is not None:
                cur["pct_rows"] += 1
            if not row["description"] and not row["no"]:
                continue
            cur["rows"].append(row)
    close()
    # a table that stopped without its total carries on in the next one (a page break, a scan's broken row)
    out = []
    for t in tables:
        if out and out[-1]["total"] is None and out[-1]["rows"] and (t["pct_rows"] > 0) == (out[-1]["pct_rows"] > 0):
            p = out[-1]
            p["rows"] += t["rows"]; p["subtotals"] += t["subtotals"]; p["total"] = t["total"]; p["pct_rows"] += t["pct_rows"]
        else:
            out.append(t)
    return out


COLWORDS = {"no", "sno", "slno", "sl", "sr", "srno", "item", "itemno", "description", "particulars", "details", "qty", "quantity", "unit", "uom",
            "rate", "unitrate", "price", "unitprice", "amount", "total", "value", "aed", "amountaed", "totalaed", "remarks", "ref", "code", "vat", "net"}


def _col_titles(l):
    """A row of column titles ('S.No  Description  Qty  Unit  Rate  Amount')."""
    words = [A for c in _cells_of(l) for A in re.split(r"\s+", c) if A]
    return len(words) >= 3 and sum(1 for w in words if squash(w) in COLWORDS or squash(w).startswith(("amount", "rate", "qty"))) >= 0.75 * len(words)


def _heading_block(blk):
    """Column titles: letter-spaced or short capitals, no figures."""
    cells = [c for l in blk for c in _cells_of(l)]
    if not cells:
        return True
    head = 0
    for c in cells:
        u = unspace(c)
        if (u != c.strip() or (u.isupper() and len(u) < 45)) and not re.search(r"\d{2,}", u):
            head += 1
    return head >= 0.7 * len(cells)


def _new_table():
    return {"rows": [], "total": None, "subtotals": [], "pct_rows": 0}


def _tidy_title(s):
    s = (s or "").strip(" —–:-")
    return s.title().replace(" And ", " and ").replace(" Of ", " of ") if s.isupper() else s


def _row_money(l):
    """The amount of a table row: the last cell that is only a sum of money."""
    cells = _cells_of(l)
    if len(cells) < 2:
        return None
    v = money(cells[-1])
    if v is None:
        return None
    if len(cells) == 2 and PCT.match(cells[0]):
        return v
    return v


def _fix_code(c):
    if re.fullmatch(r"[A-Z]{1,2}[lI|i!0-9OoSs]{1,3}", c or "") and not re.fullmatch(r"[A-Z]{1,2}", c):
        head = re.match(r"[A-Z]{1,2}", c).group(0)
        tail = c[len(head):].translate(str.maketrans({"l": "1", "I": "1", "|": "1", "i": "1", "!": "1", "O": "0", "o": "0", "S": "5", "s": "5"}))
        return head + tail if tail.isdigit() else c
    return c


def _row(blk, ml, amt):
    cells = _cells_of(ml)
    if cells and ml.get("ocr"):
        cells = [_fix_code(cells[0])] + cells[1:]
    no = cells[0] if cells and CODE.match(cells[0]) and len(cells) > 1 else ""
    qty = unit = rate = pct = None
    words = []
    mid = cells[1 if no else 0:-1]
    nums = []
    for c in mid:
        if PCT.match(c):
            pct = float(PCT.match(c).group(1))
        elif c.lower().strip(". ") in UNITS or c.lower() in UNITS:
            unit = c
        elif money(c) is not None or re.fullmatch(r"\d+(?:\.\d+)?", c.replace(",", "")):
            nums.append(float(c.replace(",", "")))
        else:
            words.append(c)
    if words and unit is None:          # "640 hrs" run together on a scan, or at the end of the words
        m = re.search(r"(?:^|\s)(\d[\d,]*(?:\.\d+)?)\s+([A-Za-z.²³0-9]{1,6})\.?$", words[-1])
        if m and m.group(2).lower().strip(".") in {u.strip(".") for u in UNITS}:
            qty, unit = float(m.group(1).replace(",", "")), m.group(2)
            words[-1] = words[-1][:m.start()].strip()
            words = [w for w in words if w]
    if nums:
        if qty is not None:
            rate = nums[-1]
        elif len(nums) >= 2:
            qty, rate = nums[0], nums[-1]
        else:
            qty = nums[0]
    title = " ".join(words).strip()
    above, below = [], []
    seen = False
    for l in blk:
        if l is ml:
            seen = True
            continue
        if _col_titles(l):
            continue
        t = " ".join(_cells_of(l)).strip()
        if t:
            (below if seen else above).append(t)
    desc = " ".join(above + ([title] if title else []) + below).strip() if above else \
        (title + (" - " + " ".join(below) if below and title else " ".join(below))).strip()
    desc = re.sub(r"\s+", " ", desc).replace("- ", "- ").strip()
    # "14 nos. @ AED 3,500.00" in the words
    m = re.search(r"(\d+(?:\.\d+)?)\s*(nos?\.?|no\.|sets?|pcs|m2|sqm|lm|m)\s*@\s*(?:AED\s*)?([\d,]+(?:\.\d+)?)", desc, re.I)
    if m and rate is None:
        q, r = float(m.group(1)), float(m.group(3).replace(",", ""))
        if abs(q * r - amt) < 1:
            qty, rate = q, r
            unit = unit or ("Nos" if m.group(2).lower().startswith("no") else m.group(2))
    if qty is not None and rate is None and qty and unit and unit.lower().strip(".") not in ("ls", "l.s", "lumpsum", "lump sum", "item", "job", "lot"):
        rate = round(amt / qty, 4)
    return {"no": no.rstrip("."), "description": desc, "qty": qty or (1 if unit else None), "unit": unit or "", "rate": rate, "amount": round(amt, 2), "pct": pct}


# ---- endpoint ---------------------------------------------------------------------------------------

@router.post("/store/est/subs/agreement/read")
async def read_agreement(request: Request, db: Session = Depends(get_db), user=E.VIEW):
    """An agreement -> the subcontract's details and its schedule. Nothing is saved; the form shows it all to check
    before Save. Sent as the file itself (multipart: file, or upload_id / parts / filename; trades as JSON): read on
    the server (est_fileread.read_agreement_doc - the header by app/docread beside this reader, the schedule by this
    reader, checked against the contract value). Sent as the browser's text ({"lines": [...]}): as before, with the
    same header check; 501 + the reason when this server cannot read the file itself."""
    import est_fileread as F
    if (request.headers.get("content-type") or "").startswith(("multipart/", "application/x-www-form-urlencoded")):
        form = await request.form()
        data, fname = await E.upload_data(form.get("file") or None, form.get("upload_id") or "", int(form.get("parts") or 0), form.get("filename") or "", user)
        if len(data) > E.MAX_FILE:
            raise HTTPException(413, "That file is over 25 MB.")
        try:
            trades = json.loads(form.get("trades") or "[]")
        except ValueError:
            trades = []
        try:
            r = await run_in_threadpool(F.read_agreement_doc, data, fname, None, trades)
        except F.Unavailable as e:
            raise HTTPException(501, str(e))
    else:
        try:
            payload = await request.json()
        except ValueError:
            raise HTTPException(400, "No text came from that file.")
        if not isinstance(payload, dict):
            raise HTTPException(400, "No text came from that file.")
        lines = payload.get("lines") or []
        if not isinstance(lines, list) or not lines:
            raise HTTPException(400, "No text came from that file.")
        if len(lines) > 20000:
            raise HTTPException(400, "That file is too long to read here.")
        r = await run_in_threadpool(F.read_agreement_doc, None, "", lines, payload.get("trades") or [])
    # the subcontractor as it is already known (Store & Purchasing suppliers, earlier subcontracts)
    nm = r["fields"].get("name")
    if nm:
        import models
        key = squash(re.sub(r"\b(llc|l\.l\.c|fze|fzc|est|establishment|co|company|trading|contracting)\b", "", nm.lower()))
        known = [(s.id, s.name) for s in db.query(models.Supplier).filter(models.Supplier.deleted_at.is_(None)).all()] + [(None, x[0]) for x in db.query(E.EstSub.name).distinct().all()]
        for sid, n in known:
            k2 = squash(re.sub(r"\b(llc|l\.l\.c|fze|fzc|est|establishment|co|company|trading|contracting)\b", "", (n or "").lower()))
            k2 = re.sub(r"^ms", "", k2)
            if key and k2 and (key == k2 or (len(key) > 6 and (key.startswith(k2) or k2.startswith(key)))):
                r["fields"]["name"] = n
                if isinstance(r.get("detail"), dict) and r["detail"].get("name"):
                    r["detail"]["name"] = dict(r["detail"]["name"], value=n, note=f"already known as {n}")
                if sid:
                    r["fields"]["supplier_id"] = sid
                r["known"] = True
                break
    return r


# ---- a table read under its own headings (bank statements, variation logs ...) -----------------------

NUMLIKE = re.compile(r"^[(\-]?(?:AED\s*)?[\d,]+(?:\.\d+)?\)?(?:\s*(?:cr|dr))?$", re.I)


def grid(lines, is_header):
    """The rows under a heading row, each cell put in its heading's column - by where it sits on the page
    (a figure by where it ends, words by where they start), so a scanned or PDF table reads like the Excel
    one. Word and Excel tables come with their cells already in order. A heading repeated on the next page
    sets the columns again. -> (heading cells, [{"cells": [...], "p": page}])"""
    lines = clean_lines(lines)
    hi = next((i for i, l in enumerate(lines) if is_header(l["c"])), None)
    if hi is None:
        return None, []
    head = lines[hi]
    names = list(head["c"])
    rows = []

    def anchors(h):
        xs = h.get("x")
        xe = h.get("xe") if h.get("xe") and len(h["xe"]) == len(xs or []) else ([x + 6 * len(c) for x, c in zip(xs, h["c"])] if xs else None)
        return xs, xe
    hx, he = anchors(head)
    for l in lines[hi + 1:]:
        if is_header(l["c"]):
            if len(l["c"]) == len(names):
                hx, he = anchors(l)
            continue
        if l.get("edge"):
            continue
        if hx is None or "x" not in l:
            cells = list(l["c"]) + [""] * max(0, len(names) - len(l["c"]))
            rows.append({"cells": cells[:max(len(names), len(l["c"]))], "p": l.get("p", 1)})
            continue
        row = [""] * len(names)
        xe = l.get("xe") if l.get("xe") and len(l["xe"]) == len(l["x"]) else [x + 6 * len(c) for x, c in zip(l["x"], l["c"])]
        for c, x, e in zip(l["c"], l["x"], xe):
            if NUMLIKE.match(c.replace(" ", "")):
                # under the heading it overlaps most; if it overlaps none, the heading it ends nearest
                ov = [min(e, he[j]) - max(x, hx[j]) for j in range(len(names))]
                best = max(range(len(names)), key=lambda j: ov[j])
                k = best if ov[best] > 0 else min(range(len(names)), key=lambda j: abs(e - he[j]))
            else:
                k = min(range(len(names)), key=lambda j: (0 if hx[j] - 6 <= x <= he[j] + 6 else min(abs(x - hx[j]), abs(x - he[j])), abs(x - hx[j])))
            row[k] = (row[k] + " " + c).strip()
        rows.append({"cells": row, "p": l.get("p", 1)})
    return names, rows

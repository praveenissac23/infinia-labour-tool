"""Read a document into an Estimation form - the same way the subcontract agreement is read.

The browser opens the PDF, Word or Excel file and sends only its text (portal/est/agreement.js);
nothing of the file is kept. Each form has its reader, and every reader works on the words an
office uses rather than on one company's template:

  project    letter of award / main contract  -> name, client, consultant, location, value, advance,
                                                 retention, VAT, start and completion
  tender     tender invitation / enquiry        -> name, client, consultant, location, received, due
  invoice    a subcontractor's invoice / claim  -> which subcontractor, invoice no., date, amount, lines
  subvo      a variation to a subcontract       -> description, addition or omission, amount, date
  variation  a variation / cost proposal        -> description, type, submitted amount and date, ref
  clientpc   an interim payment certificate     -> period, work claimed and certified to date, material
                                                 on site, retention released, certificate no.
  log        an RFI or submittal / its letter   -> subject, letter no., sent, reply due, question
  approval   a NOC / permit / authority letter   -> item, authority, ref / permit no., dates
  items      a priced schedule only             -> the lines (as the agreement schedule)

What is not found is left for the user and said, never guessed.
"""
import re
from datetime import date, timedelta

from fastapi import Body, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
import estimation as E
import est_agreement as A

router = E.router


def _flat(lines):
    return re.sub(r"\s+", " ", "\n".join(l["t"] for l in lines))


def _lab(lines, *keys):
    return A.find_label(lines, keys)


def _date_of(lines, *keys):
    v = _lab(lines, *keys) if keys else ""
    d = A.a_date(v) if v else None
    return d.isoformat() if d else ""


def _letter_date(lines):
    """The date of the letter: 'Date: ...' near the top, else the first date in the first lines."""
    d = _date_of(lines, "date", "dated", "issuedon", "dateofissue", "letterdate", "invoicedate", "documentdate")
    if d:
        return d
    for l in lines[:25]:
        x = A.a_date(l["t"])
        if x and 2000 < x.year < 2100:
            return x.isoformat()
    return ""


def _subject(lines):
    v = _lab(lines, "subject", "sub", "re", "regarding", "reference subject", "title", "projecttitle")
    if v:
        return v.strip(" :-")
    m = re.search(r"\b(?:Subject|Sub|Re|RE)\s*[:\-]\s*([^\n]{5,200})", "\n".join(l["t"] for l in lines))
    return m.group(1).strip() if m else ""


def _ref(lines, *keys):
    v = _lab(lines, *(keys or ("ourref", "ref", "refno", "reference", "letterno", "documentno", "docno")))
    if v and re.search(r"\d", v) and len(v) <= 60:
        return v.strip(" .,;")
    return ""


def _money_label(lines, *keys):
    v = _lab(lines, *keys)
    if not v:
        return None
    x = A.money_in(v)
    if x is None:
        x = A.money(v)
    if x is None:
        for tok in v.replace("(", " ").split():
            x = A.money(tok)
            if x is not None:
                break
    return x


def _pct_near(flat, word):
    m = re.search(word + r"[^.%\d]{0,60}?(\d{1,2}(?:\.\d+)?)\s*%", flat, re.I) or re.search(r"(\d{1,2}(?:\.\d+)?)\s*%[^.%]{0,40}?" + word, flat, re.I)
    return float(m.group(1)) if m else None


def _out(f, found_names, notes=None, **extra):
    f = {k: v for k, v in f.items() if v not in (None, "")}
    r = {"fields": f, "found": [n for k, n in found_names if f.get(k) not in (None, "")], "notes": notes or []}
    r.update(extra)
    return r


# ---- readers -------------------------------------------------------------------------------------------

def read_project(lines, flat):
    f = {}
    f["name"] = _lab(lines, "projectname", "project", "nameofproject", "nameofwork", "works", "projecttitle") or _subject(lines)
    f["client"] = re.sub(r"^M/?S\.?\s*", "", _lab(lines, "client", "employer", "owner", "clientname", "employername"), flags=re.I)
    if not f["client"]:
        m = re.search(r"between\s+((?:M/?S\.?\s+)?[A-Z][^,()]{2,80}?)\s*(?:\(|,)\s*(?:hereinafter[^)]*)?(?:the\s+)?[\"“]?(?:employer|client|owner)", flat, re.I)
        f["client"] = re.sub(r"^M/?S\.?\s*", "", m.group(1), flags=re.I).strip() if m else ""
    f["consultant"] = re.sub(r"^M/?S\.?\s*", "", _lab(lines, "consultant", "engineer", "supervisionconsultant", "projectconsultant"), flags=re.I)
    if f["consultant"] and not re.search(r"[A-Za-z]{3}", f["consultant"]):
        f["consultant"] = ""
    f["location"] = _lab(lines, "location", "plotno", "plot", "site", "projectlocation", "address")
    v = _money_label(lines, "contractvalue", "contractsum", "contractprice", "contractamount", "lumpsumprice", "totalcontractvalue", "acceptedcontractamount", "awardvalue", "contractsumexclusiveofvat")
    if v is None:
        m = re.search(r"(?:contract\s+(?:sum|value|price|amount)|accepted\s+(?:contract\s+)?amount|lump\s*sum)[^.\d]{0,80}?(?:AED|Dhs?\.?)\s*([\d,]+(?:\.\d{1,2})?)", flat, re.I)
        v = float(m.group(1).replace(",", "")) if m else None
    f["contract_value"] = v
    f["adv_pct"] = _pct_near(flat, r"advance")
    f["ret_pct"] = _pct_near(flat, r"retention")
    f["vat_pct"] = 5.0 if re.search(r"excl\w*\.?\s*(?:of\s+)?VAT|exclusive\s+of\s+VAT|plus\s+VAT", flat, re.I) else None
    st = _date_of(lines, "commencementdate", "startdate", "dateofcommencement", "siteposessiondate", "sitepossession")
    en = _date_of(lines, "completiondate", "dateofcompletion", "enddate", "timeforcompletion")
    if not en and st:
        m = re.search(r"(?:duration|time for completion|contract period|completion period)[^.\d]{0,40}?(\d{1,3})\s*(months?|weeks?|days?)", flat, re.I)
        if m:
            n, u = int(m.group(1)), m.group(2).lower()
            d0 = date.fromisoformat(st)
            if u.startswith("month"):
                y, mo = d0.year + (d0.month - 1 + n) // 12, (d0.month - 1 + n) % 12 + 1
                en = date(y, mo, min(d0.day, 28)).isoformat()
            else:
                en = (d0 + timedelta(days=n * (7 if u.startswith("week") else 1))).isoformat()
    f["start_date"], f["end_date"] = st, en
    return _out(f, [("name", "Project name"), ("client", "Client"), ("consultant", "Consultant"), ("location", "Location"), ("contract_value", "Contract value"),
                    ("adv_pct", "Advance %"), ("ret_pct", "Retention %"), ("start_date", "Start"), ("end_date", "Completion")])


def read_tender(lines, flat):
    f = {}
    f["name"] = _lab(lines, "projectname", "project", "tender", "tendername", "nameofproject", "nameofwork", "works") or _subject(lines)
    f["client"] = re.sub(r"^M/?S\.?\s*", "", _lab(lines, "client", "employer", "owner", "developer"), flags=re.I)
    f["consultant"] = re.sub(r"^M/?S\.?\s*", "", _lab(lines, "consultant", "engineer", "architect"), flags=re.I)
    f["location"] = _lab(lines, "location", "plotno", "plot", "site", "projectlocation")
    f["due"] = _date_of(lines, "submissiondate", "closingdate", "tenderclosingdate", "duedate", "submissiondeadline", "lastdateofsubmission", "tendersubmissiondate", "bidsubmissiondate")
    if not f["due"]:
        m = re.search(r"(?:submi\w+|clos\w+|due|deadline)[^.]{0,60}?(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\.?,?\s+\d{4}|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})", flat, re.I)
        d = A.a_date(m.group(1)) if m else None
        f["due"] = d.isoformat() if d else ""
    f["received"] = _letter_date(lines)
    if f["received"] == f["due"]:
        f["received"] = ""
    low = flat.lower()
    f["kind"] = "Design & Build" if re.search(r"design\s*(?:&|and)\s*build", low) else ("Fit-out" if "fit-out" in low or "fitout" in low else None)
    return _out(f, [("name", "Tender / project"), ("client", "Client"), ("consultant", "Consultant"), ("location", "Location"), ("received", "Received"), ("due", "Submission due")])


_ONES = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
                                     "seventeen eighteen nineteen".split())}
_TENS = {w: 10 * (i + 2) for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split())}
_TYPO = {"eigtheen": "eighteen", "eighten": "eighteen", "fourty": "forty", "ninty": "ninety", "thousands": "thousand", "hundreds": "hundred",
         "lakh": "lac", "lakhs": "lac", "lacs": "lac", "millions": "million"}


def words_amount(flat):
    """The dirhams written in words ('Eleven Thousand One Hundred Eighteen and Eighteen Fils Only') -> 11118.18, or None.
    The longest run of number words is the dirhams; number words just before 'fils' are the fils."""
    toks = re.findall(r"[a-z]+", flat.lower())
    toks = [_TYPO.get(t, t) for t in toks]
    NUMW = set(_ONES) | set(_TENS) | {"hundred", "thousand", "lac", "million"}
    def num(ws):
        total = cur = 0
        for w in ws:
            if w in _ONES: cur += _ONES[w]
            elif w in _TENS: cur += _TENS[w]
            elif w == "hundred": cur = (cur or 1) * 100
            elif w == "thousand": total += (cur or 1) * 1000; cur = 0
            elif w == "lac": total += (cur or 1) * 100000; cur = 0
            elif w == "million": total += (cur or 1) * 1000000; cur = 0
        return total + cur
    runs, cur = [], []                                   # runs of number words ("and" allowed inside)
    for k, t in enumerate(toks):
        if t in NUMW or (t == "and" and cur and k + 1 < len(toks) and toks[k + 1] in NUMW):
            cur.append((k, t))
        else:
            if cur: runs.append(cur)
            cur = []
    if cur: runs.append(cur)
    runs = [r for r in runs if any(t in NUMW for _, t in r)]
    if not runs:
        return None
    # the dirhams: the run followed by dirhams / fils / only (or the biggest-valued run with 'thousand' or 'hundred')
    def after(r): return toks[r[-1][0] + 1] if r[-1][0] + 1 < len(toks) else ""
    fils_run = next((r for r in runs if after(r) == "fils"), None)
    if fils_run is not None and {"thousand", "hundred", "lac", "million"} & {t for _, t in fils_run}:
        fils_run = None                                  # one run holds both: "... Eighteen and Eighteen Fils" - split below
    dh_run = None
    for r in runs:
        if r is fils_run:
            continue
        ws = [t for _, t in r]
        if after(r) in ("dirham", "dirhams", "only", "fils", "and", "aed") or {"thousand", "hundred", "lac", "million"} & set(ws):
            if dh_run is None or num([t for _, t in r if t != "and"]) > num([t for _, t in dh_run if t != "and"]):
                dh_run = r
    if dh_run is None:
        return None
    ws = [t for _, t in dh_run if t != "and"]
    # "... Eighteen and Eighteen Fils": the run swallowed the fils - split at the last "and" before fils
    fils = 0
    if fils_run is None and after(dh_run) == "fils":
        parts = [t for _, t in dh_run]
        if "and" in parts:
            cut = len(parts) - 1 - parts[::-1].index("and")
            ws = [t for t in parts[:cut] if t != "and"]; fils = num([t for t in parts[cut + 1:] if t != "and"])
        else:
            return None
    elif fils_run is not None:
        fils = num([t for _, t in fils_run if t != "and"])
    dh = num(ws)
    if not dh or fils >= 100:
        return None
    return round(dh + fils / 100, 2)


def check_total(lines, flat, tot, notes):
    """The total, checked against the bill's own figures. A scan easily drops a digit ("11118.18" read as "1118.18"):
    total before VAT + VAT, and the amount written in words, put it right - and it is said, to check."""
    sub = _money_label(lines, "totalbeforevat", "totalexclvat", "totalexcludingvat", "subtotal", "taxableamount", "netamount", "totalamount", "amount")
    vat = _money_label(lines, "vatamount", "vat5", "vat", "valueaddedtax", "tax5", "tax")
    calc = None
    if sub and vat is not None and 0 < vat <= sub * 0.06 and abs(vat - sub * 0.05) <= max(1.0, sub * 0.002):
        calc = round(sub + vat, 2)
    words = words_amount(flat)
    pick, why = None, ""
    if calc is not None and (tot is None or abs(tot - calc) > 0.05):
        pick, why = calc, f"total {sub:,.2f} + VAT {vat:,.2f} = {calc:,.2f}"
        if words is not None and abs(words - calc) > 0.05 and tot is not None and abs(words - tot) <= 0.05:
            pick = None                                   # the words agree with the total read: keep it
    elif words is not None and tot is not None and abs(words - tot) > 0.05 and calc is None:
        a, b = str(int(round(tot))), str(int(round(words)))
        if len(b) == len(a) + 1 and any(b[:i] + b[i + 1:] == a for i in range(len(b))):     # one digit dropped
            pick, why = words, f"the amount in words ({words:,.2f})"
    elif tot is None and words is not None:
        pick, why = words, f"the amount in words ({words:,.2f})"
    if pick is not None:
        if tot is not None:
            notes.append(f"The total read as {tot:,.2f} does not match {why} - {pick:,.2f} is filled in. Check it against the bill.")
        return pick
    return tot


def read_invoice(lines, flat, subs=None):
    f = {}
    f["inv_ref"] = _ref(lines, "invoiceno", "taxinvoiceno", "invoicenumber", "invno", "billno", "invoice", "proformainvoiceno", "claimno", "applicationno")
    f["inv_date"] = _date_of(lines, "invoicedate", "dateofinvoice", "billdate", "date", "dated") or _letter_date(lines)
    tot = _money_label(lines, "totalamountincludingvat", "totalincludingvat", "totalincvat", "grandtotal", "totalamountpayable", "totalpayable", "amountdue",
                       "netamountpayable", "invoicetotal", "totalinvoiceamount", "totalamount", "total")
    tables = A._tables(lines)
    if tot is None:
        tt = [t["total"] for t in tables if t.get("total")]
        tot = max(tt) if tt else None
    # Check the total against its parts: a scan easily drops a digit ("11118.18" read as "1118.18"). Total before
    # VAT + VAT is the invoice's own sum - when the total read disagrees with it, the sum is used and said.
    notes = []
    tot = check_total(lines, flat, tot, notes)
    f["inv_amount"] = tot
    # the bill's own lines
    rows = max(tables, key=lambda t: len(t["rows"]))["rows"] if tables else []
    inv_lines = [{"d": r["description"][:300], "a": r["amount"]} for r in rows if r["description"]][:40]
    if inv_lines:
        import json
        f["inv_lines"] = json.dumps(inv_lines)
    # which subcontractor: the company that issued the invoice (its name at the top - never ours, the "To"),
    # matched to one on this project. Not on the project -> its name is given so it can be added as a new one.
    issuer = _vendor(lines)
    best = _match_sub(issuer, subs or []) if issuer else None
    if best is None:
        # no clear issuer: a subcontractor's full name written on the invoice, but never one read from our own lines
        hay = A.squash(" ".join(l["t"] for l in lines if "infinia" not in l["t"].lower()))
        for s in subs or []:
            key = _sub_key(s.get("name"))
            if len(key) >= 8 and key in hay and (best is None or len(key) > best[1]):
                best = (s["id"], len(key))
        best = best[0] if best else None
    if best is not None:
        f["sub_id"] = best
    elif issuer:
        f["new_sub"] = issuer = (issuer.title().replace("Llc", "LLC").replace("Fze", "FZE").replace("L.L.C", "L.L.C") if issuer.isupper() else issuer)
        notes.append(f"{issuer} is not a subcontractor on this project yet - add it as a new one below.")
    m = re.search(r"(?:work\s+done|value\s+of\s+work|cumulative|gross\s+value)[^.\d]{0,50}?(?:to\s+date)?[^.\d]{0,30}?(?:AED\s*)?([\d,]{4,}(?:\.\d{1,2})?)", flat, re.I)
    if m and re.search(r"to\s+date|cumulative", m.group(0), re.I):
        f["work_cum"] = float(m.group(1).replace(",", ""))
    if not f.get("inv_ref"):
        m = re.search(r"\binvoice\s*(?:no\.?|number|#)\s*[:\-.]?\s*([A-Z0-9][A-Z0-9/\-]{0,30})", flat, re.I)
        if m and re.search(r"\d", m.group(1)):
            f["inv_ref"] = m.group(1).strip("-/")
    sc = re.search(r"(?:payment|invoice|claim|bill)\s+for\s+(?:the\s+)?(.{6,90}?\bworks?\b)", flat, re.I)
    if sc:
        f["scope_hint"] = sc.group(1).strip(" ,.-").title()[:90]
    return _out(f, [("sub_id", "Subcontractor"), ("inv_ref", "Invoice no."), ("inv_date", "Invoice date"), ("inv_amount", "Invoice amount"),
                    ("inv_lines", "Bill lines"), ("work_cum", "Work done to date")], notes)


_SUFFIX = r"\b(llc|l\.l\.c\.?|fze|fzc|fzco|est\.?|establishment|co\.?|company|trading|contracting|technical|services|general|ms|m/s|the)\b"


def _sub_key(name):
    return A.squash(re.sub(_SUFFIX, " ", (name or "").lower()))


def _match_sub(issuer, subs):
    """The subcontractor whose name is the issuer's (ignoring LLC, EST, TRADING ...), or None."""
    want = _sub_key(issuer)
    if len(want) < 3:
        return None
    best = None
    for s in subs:
        key = _sub_key(s.get("name"))
        if len(key) < 3:
            continue
        import difflib
        close = difflib.SequenceMatcher(None, key, want).ratio()
        if key == want or (len(key) >= 5 and (key in want or want in key)) or (min(len(key), len(want)) >= 6 and close >= 0.85):
            score = 1000 if key == want else (len(key) if (key in want or want in key) else close * 100)
            if best is None or score > best[1]:
                best = (s["id"], score)
    return best[0] if best else None


def read_subvo(lines, flat):
    f = {}
    f["title"] = _subject(lines) or _lab(lines, "description", "scope", "variationdescription")
    tot = _money_label(lines, "totalamount", "total", "grandtotal", "variationamount", "amount", "netamount", "totalexclvat", "totalexcludingvat")
    if tot is None:
        tt = [t["total"] for t in A._tables(lines) if t.get("total")]
        tot = tt[-1] if tt else None
    f["amount"] = abs(tot) if tot is not None else None
    f["sign"] = "Omission" if re.search(r"\bomission|\bomit|\bdeduct|\bcredit\s+note|\breduction", flat, re.I) and not re.search(r"\baddition", flat, re.I) else "Addition"
    f["on_date"] = _letter_date(lines)
    r = _ref(lines)
    if r and f.get("title") and r not in f["title"]:
        f["title"] = f"{f['title']} ({r})"
    return _out(f, [("title", "Description"), ("amount", "Amount"), ("on_date", "Date")])


def read_variation(lines, flat):
    f = {}
    f["title"] = _subject(lines) or _lab(lines, "description", "variationdescription", "scope")
    f["title"] = re.sub(r"^(?:cost\s+proposal|variation(?:\s+order)?|request\s+for\s+variation)\s*(?:no\.?\s*[\w/-]+)?\s*[:\-–—]\s*", "", f["title"], flags=re.I) if f["title"] else ""
    tot = _money_label(lines, "totalamount", "totalcost", "total", "grandtotal", "variationamount", "proposalamount", "netamount", "totalexclvat", "totalexcludingvat", "amount")
    if tot is None:
        tt = [t["total"] for t in A._tables(lines) if t.get("total")]
        tot = tt[-1] if tt else None
    f["submitted_amount"] = abs(tot) if tot is not None else None
    f["kind"] = "Omission" if re.search(r"\bomission|\bomit|\bdeduct|\bsaving", flat, re.I) and not re.search(r"\baddition", flat, re.I) else "Addition"
    f["submitted"] = _letter_date(lines)
    r = _ref(lines, "cpno", "costproposalno", "variationno", "vono", "ourref", "ref", "refno", "reference")
    if r:
        f["notes"] = f"Letter ref. {r}"
    if re.search(r"instruction|SI\s*No|site\s+instruction", flat, re.I):
        f["source"] = "Client instruction"
    return _out(f, [("title", "Description"), ("submitted_amount", "Submitted amount"), ("submitted", "Submitted on"), ("kind", "Type")])


def read_clientpc(lines, flat):
    f = {}
    def amt(*keys):
        return _money_label(lines, *keys)
    f["claimed_cum"] = amt("totalvalueofworkdonetodate", "valueofworkdonetodate", "workdonetodate", "grossvaluetodate", "totalworkdone", "cumulativevalue",
                           "totalworkexecutedtodate", "valueofworkexecutedtodate", "claimedtodate", "grossvalueofworkdone", "totalclaimed")
    f["certified_cum"] = amt("certifiedtodate", "totalcertified", "amountcertified", "grosscertified", "certifiedvalue", "certifiedamount")
    f["mos_cum"] = amt("materialonsite", "materialsonsite", "mos")
    f["ret_rel_cum"] = amt("retentionreleased", "releaseofretention", "retentionrelease")
    f["period_to"] = _date_of(lines, "periodending", "periodupto", "periodto", "valuationdate", "upto", "periodending")
    if not f["period_to"]:
        m = re.search(r"(?:period|work\s+done)\s+(?:ending|up\s*to|until|till)[^\d]{0,15}(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\.?,?\s+\d{4}|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})", flat, re.I)
        d = A.a_date(m.group(1)) if m else None
        f["period_to"] = d.isoformat() if d else ""
    f["submitted"] = _date_of(lines, "submittedon", "dateofsubmission", "applicationdate") or _letter_date(lines)
    m = re.search(r"(?:IPC|payment\s+certificate|interim\s+payment\s+(?:certificate|application)|PC)\s*(?:No\.?|#)?\s*[:\-]?\s*(\d{1,3})\b", flat, re.I)
    if m:
        f["remarks"] = f"Certificate no. {int(m.group(1)):02d}"
    if f.get("certified_cum") is None and re.search(r"certif", flat, re.I) and f.get("claimed_cum") is not None:
        pass
    return _out(f, [("claimed_cum", "Work done to date - claimed"), ("certified_cum", "Certified to date"), ("period_to", "Period up to"),
                    ("submitted", "Submitted on"), ("mos_cum", "Material on site"), ("ret_rel_cum", "Retention released")])


AUTH = ["DEWA", "Dubai Municipality", "DM", "Civil Defence", "DCD", "RTA", "Etisalat", "du", "Trakhees", "Nakheel", "Emaar", "Sobha", "Meraas",
        "Dubai Properties", "DDA", "Empower", "Tabreed", "Dubai Police", "DLD", "JAFZA", "Ministry"]


def read_log(lines, flat):
    f = {}
    f["title"] = _subject(lines) or _lab(lines, "description", "query", "item")
    f["ref"] = _ref(lines, "rfino", "rfinumber", "submittalno", "submittalref", "transmittalno", "letterno", "ourref", "ref", "refno", "reference", "documentno")
    f["sent"] = _date_of(lines, "datesent", "sentdate", "submittedon", "dateofsubmission", "date", "dated") or _letter_date(lines)
    f["due"] = _date_of(lines, "replyrequiredby", "responserequiredby", "responsedue", "replydue", "requiredby", "duedate", "replyby")
    q = _lab(lines, "question", "query", "queries", "description", "details", "remarks")
    f["note"] = q if q and q != f.get("title") else ""
    m = re.search(r"\bRev(?:ision)?\.?\s*(?:No\.?)?\s*[:\-]?\s*(\d)\b", flat, re.I)
    if m:
        f["rev"] = m.group(1)
    return _out(f, [("title", "Subject"), ("ref", "Ref. / letter no."), ("sent", "Sent on"), ("due", "Reply due"), ("note", "Question")])


def read_approval(lines, flat):
    f = {}
    f["title"] = _subject(lines) or _lab(lines, "description", "noc", "permit", "approvalfor")
    f["ref"] = _ref(lines, "nocno", "permitno", "approvalno", "certificateno", "applicationno", "referenceno", "ref", "refno")
    for a in AUTH:
        if re.search(r"\b" + re.escape(a) + r"\b", flat):
            f["party"] = a
            break
    f["replied"] = _date_of(lines, "issuedate", "dateofissue", "issuedon", "approvaldate", "approvedon", "date") or _letter_date(lines)
    return _out(f, [("title", "Item"), ("party", "Authority"), ("ref", "Ref. / permit no."), ("replied", "Approved")])


def read_items(lines, flat):
    r = A.read(lines)
    return {"fields": {}, "found": [f"{len(r['items'])} priced lines"] if r["items"] else [], "notes": r["notes"], "items": r["items"], "checks": r["checks"]}


READERS = {"project": read_project, "tender": read_tender, "invoice": read_invoice, "subvo": read_subvo, "variation": read_variation,
           "clientpc": read_clientpc, "log": read_log, "approval": read_approval, "items": read_items}


@router.post("/store/est/read/{kind}")
def read_document(kind: str, payload: dict = Body(...), db: Session = Depends(get_db), user=E.VIEW):
    """The text of a document opened in the browser -> the fields of one Estimation form. Nothing is saved."""
    if kind not in READERS:
        raise HTTPException(404, "Nothing reads that kind of document.")
    lines = payload.get("lines") or []
    if not isinstance(lines, list) or not lines:
        raise HTTPException(400, "No text came from that file.")
    if len(lines) > 20000:
        raise HTTPException(400, "That file is too long to read here.")
    lines = A.clean_lines(lines)
    flat = _flat(lines)
    if kind == "invoice":
        return read_invoice(lines, flat, payload.get("subs") or [])
    return READERS[kind](lines, flat)


# ---- the rest of the app: receipts, cheques, ID documents, delivery notes, quotations -------------------

COMPANY = re.compile(r"\b(L\.?L\.?C|LLC|FZE|FZC|FZCO|TRADING|EST\.?|ESTABLISHMENT|CO\.|COMPANY|CONTRACTING|SUPPLIES|SUPPLY|INDUSTRIES|GROUP|ENTERPRISES|"
                     r"BUILDING MATERIALS|HARDWARE|ELECTRICAL|TECHNICAL|SERVICES|STORES?|CENTRE|CENTER|FACTORY|SUPERMARKET|HYPERMARKET|RESTAURANT|CAFETERIA|PHARMACY|GARAGE|STATION)\b", re.I)


def _vendor(lines, avoid=("infinia",)):
    """Who issued it: a company name near the top (LLC, TRADING, EST ...), not ours, not 'TAX INVOICE'."""
    for l in lines[:14]:
        for c in l["c"]:
            t = c.strip(" :-")
            if len(t) < 4 or any(a in t.lower() for a in avoid) or re.search(r"invoice|receipt|quotation|delivery|statement|tax|date|trn|tel|phone|p\.?o\.? box|email|www", t, re.I):
                continue
            if COMPANY.search(t) and len(t) <= 80:
                # the whole name when the line was split in pieces ("ROYAL" | "EVERST TECHNICAL SERVICES EST.")
                whole = " ".join(re.sub(r"[^\x20-\x7E]", " ", c).strip() for c in l["c"]).strip()
                whole = re.sub(r"\s+", " ", whole)
                if t in whole and len(whole) <= 80 and not re.search(r"invoice|receipt|quotation|delivery|statement|tax|date|trn|tel|phone|email|www|\d{3,}", whole, re.I) \
                        and not any(a in whole.lower() for a in avoid):
                    t = whole.strip(" :-")
                i = lines.index(l)
                nxt = lines[i + 1]["c"][0].strip() if i + 1 < len(lines) and lines[i + 1]["c"] else ""
                if re.fullmatch(r"(L\.?L\.?C\.?|LLC|FZE|FZC|FZCO|FZ-?LLC|EST\.?|CO\.?|W\.?L\.?L\.?|\(L\.?L\.?C\.?\))", nxt, re.I) and not re.search(nxt.replace(".", r"\.") + "$", t):
                    t = t + " " + nxt
                return re.sub(r"^M/?S\.?\s*", "", t, flags=re.I)
    for l in lines[:6]:
        t = " ".join(l["c"]).strip()
        if t.isupper() and 5 < len(t) <= 60 and not re.search(r"invoice|receipt|quotation|delivery|statement|tax", t, re.I) and not any(a in t.lower() for a in avoid):
            return t.title()
    return ""


def _trn(flat):
    m = re.search(r"\bTRN\b\s*(?:No\.?|Number)?\s*[:\-]?\s*(1\d{14})\b", flat, re.I) or re.search(r"\b(100\d{12})\b", flat)
    return m.group(1) if m else ""


def read_receipt(lines, flat):
    """A shop receipt or supplier bill paid in cash -> date, supplier, receipt no., total, VAT, TRN, what for."""
    f = {}
    f["supplier"] = _vendor(lines)
    f["receipt_no"] = _ref(lines, "receiptno", "invoiceno", "taxinvoiceno", "billno", "invno", "receiptnumber", "invoicenumber", "voucherno", "docno", "transactionno")
    f["date"] = _date_of(lines, "date", "invoicedate", "receiptdate", "billdate", "dated", "transactiondate") or _letter_date(lines)
    tot = _money_label(lines, "totalamountincludingvat", "totalincludingvat", "totalinclvat", "totalincvat", "grandtotal", "nettotal", "netamount", "totalamount",
                       "amountpaid", "amountdue", "totalpayable", "total", "cash", "paid")
    if tot is None:
        nums = [A.money(c) for l in lines for c in l["c"] if A.money(c) is not None]
        tot = max(nums) if nums else None
    notes = []
    tot = check_total(lines, flat, tot, notes)
    f["amount"] = tot
    vat = _money_label(lines, "vatamount", "totalvat", "outputvat", "taxamount", "vat5", "vat", "tax")
    if vat is None or (tot and abs(vat - 5) < 0.001):         # 'VAT 5% ........ 23.00': the figure at the end of the row
        for l in lines:
            if re.match(r"^\s*(total\s+)?(vat|tax)\b", l["c"][0], re.I) and not re.search(r"incl|excl|before|after|\btrn\b|registration", l["t"], re.I):
                nums = [A.money(c) for c in l["c"][1:] if A.money(c) is not None]
                nums = [x for x in nums if x != 5]
                if nums:
                    vat = nums[-1]
                    break
    if vat is not None and tot and vat < tot * 0.2:
        f["vat"] = vat
    f["trn"] = _trn(flat)
    rows = max(A._tables(lines), key=lambda t: len(t["rows"]))["rows"] if A._tables(lines) else []
    words = [r["description"] for r in rows if r["description"] and not re.search(r"total|vat|cash|change", r["description"], re.I)][:3]
    tidy = lambda w: re.sub(r"(\s+[\d.,|\[\]]+)+\s*$", "", re.sub(r"[|\[\]]", " ", w)).strip(" ,-")
    words = [w for w in words if not re.search(r"\bamount\b|description|sl\.?\s*no|qty|unit\s*price|rate\b", w, re.I) and sum(ch.isalpha() for ch in w) >= 4]
    f["description"] = ", ".join(tidy(w)[:60] for w in words if tidy(w))
    sent = re.search(r"(?:submit\s+our|being|towards)\s+(.{6,120}?\bworks?\b)", flat, re.I) or re.search(r"\b((?:\w+\s+){0,3}payment\s+for\s+.{4,100}?\bworks?\b)", flat, re.I)
    if sent:
        f["description"] = re.sub(r"\s+", " ", sent.group(1)).strip(" ,.-")[:120].capitalize()
    if not f.get("receipt_no"):
        m = re.search(r"\b(?:invoice|receipt|bill)\s*(?:no\.?|number|#)\s*[:\-.]?\s*([A-Z0-9][A-Z0-9/\-]{0,30})", flat, re.I)
        if m and re.search(r"\d", m.group(1)):
            f["receipt_no"] = m.group(1).strip("-/")
    return _out(f, [("date", "Date"), ("supplier", "Supplier"), ("receipt_no", "Receipt no."), ("amount", "Amount"), ("vat", "VAT"), ("trn", "TRN")], notes)


BANKS = [("ADCB", r"ADCB|Abu Dhabi Commercial"), ("Emirates NBD", r"Emirates\s*NBD|ENBD"), ("FAB", r"First Abu Dhabi|\bFAB\b|NBAD"), ("Mashreq", r"Mashreq"),
         ("RAKBANK", r"RAK\s*BANK|National Bank of Ras"), ("CBD", r"Commercial Bank of Dubai|\bCBD\b"), ("DIB", r"Dubai Islamic|\bDIB\b"),
         ("ADIB", r"Abu Dhabi Islamic|ADIB"), ("Emirates Islamic", r"Emirates Islamic"), ("NBF", r"National Bank of Fujairah|\bNBF\b"),
         ("HSBC", r"HSBC"), ("Standard Chartered", r"Standard Chartered"), ("Ajman Bank", r"Ajman Bank"), ("Sharjah Islamic", r"Sharjah Islamic"), ("UAB", r"United Arab Bank")]


def read_cheque(lines, flat):
    """A cheque (photo or scan) -> cheque no., date, amount, payee, bank."""
    f = {}
    for name, rx in BANKS:
        if re.search(rx, flat, re.I):
            f["bank"] = name
            break
    m = re.search(r"\bPay(?:\s+to(?:\s+the\s+order\s+of)?)?\s*[:\-]?\s+([A-Z][A-Za-z0-9&.,'()/ \-]{3,70}?)(?:\s+or\s+(?:bearer|order)\b|\s{2,}|$|\s+(?:AED|Dirhams|the\s+sum))", flat, re.I)
    if m:
        f["payee"] = re.sub(r"^M/?S\.?\s*", "", m.group(1).strip(" .,-"), flags=re.I)
    # the amount in figures: AED **12,500.00** / 12500/- / the biggest sum on the cheque
    cands = [float(x.replace(",", "")) for x in re.findall(r"(?:AED|Dhs?\.?|\*{1,}|#)\s*\**\s*(\d{1,3}(?:,\d{3})+(?:\.\d{2})?|\d+(?:\.\d{2})?)\s*(?:/-|\**)", flat, re.I)]
    cands += [A.money(c) for l in lines for c in l["c"] if A.money(c) is not None and ("," in c or "." in c)]
    cands = [c for c in cands if c and c < 1e9]
    if cands:
        f["amount"] = max(cands)
    # the date: dd/mm/yyyy, or the eight date boxes read as one number (15102026)
    d = None
    m = re.search(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](20\d{2})\b", flat)
    if m:
        try:
            d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            d = None
    if not d:
        m = re.search(r"\b(\d{2})\s?(\d{2})\s?(20\d{2})\b", flat)
        if m:
            try:
                d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except ValueError:
                d = None
    if not d:
        x = A.a_date(flat)
        d = x if x and 2000 < x.year < 2100 else None
    f["date"] = d.isoformat() if d else ""
    # cheque no.: the six digits at the start of the code line along the bottom
    m = re.search(r"(?:Cheque|Chq)\s*(?:No\.?|Number)\s*[:\-]?\s*(\d{6})\b", flat, re.I)
    if not m:
        bottom = " ".join(l["t"] for l in lines[-4:])
        m = re.search(r"[⑈|\"'«]?\s*(\d{6})\s*[⑈|\"'»]", bottom) or re.search(r"\b(\d{6})\b", bottom)
    if m:
        f["no"] = m.group(1)
    return _out(f, [("no", "Cheque no."), ("date", "Date"), ("amount", "Amount"), ("payee", "Payee"), ("bank", "Bank")])


def _mrz_date(s, future):
    try:
        y, mo, d = int(s[:2]), int(s[2:4]), int(s[4:6])
    except ValueError:
        return ""
    y += 2000 if (future or y <= (date.today().year % 100) + 1) else 1900
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return ""


def read_iddoc(lines, flat):
    """Passport (from the code lines at the bottom), Emirates ID, residence visa, labour card ->
    the kind of document, its number, issue and expiry dates, the name."""
    f = {}
    raw = [re.sub(r"\s+", "", l["t"]).upper().replace("«", "<").replace("K<", "<<") for l in lines]
    mrz = [x for x in raw if x.count("<") >= 4 and len(x) >= 30]
    if len(mrz) >= 2 and mrz[-2].startswith("P"):
        l1, l2 = mrz[-2], mrz[-1]
        f["kind"] = "passport"
        f["number"] = l2[:9].replace("<", "").replace("O", "0") if len(l2) >= 9 else ""
        f["nationality"] = l2[10:13].replace("<", "") if len(l2) >= 13 else ""
        f["dob"] = _mrz_date(l2[13:19], False) if len(l2) >= 19 else ""
        f["expires_on"] = _mrz_date(l2[21:27], True) if len(l2) >= 27 else ""
        names = l1[5:].split("<<", 1)
        f["name"] = (names[1].replace("<", " ").strip() + " " + names[0].replace("<", " ").strip()).strip().title() if len(names) == 2 else ""
    low = flat.lower()
    if not f.get("kind"):
        if re.search(r"identity card|emirates id|\bid number\b|784-\d{4}", low):
            f["kind"] = "eid"
        elif re.search(r"residence|residency|entry permit|visa", low):
            f["kind"] = "visa"
        elif re.search(r"labou?r card|work permit|mohre|ministry of human resources", low):
            f["kind"] = "labour_card"
        elif "passport" in low:
            f["kind"] = "passport"
    if not f.get("number"):
        m = re.search(r"\b(784-?\d{4}-?\d{7}-?\d)\b", flat)
        if m:
            d = re.sub(r"\D", "", m.group(1))
            f["number"] = f"{d[:3]}-{d[3:7]}-{d[7:14]}-{d[14:]}"
        else:
            f["number"] = _ref(lines, "idnumber", "passportno", "passportnumber", "fileno", "filenumber", "uidno", "permitno", "cardno", "cardnumber",
                               "documentno", "visano", "entrypermitno", "labourcardno", "workpermitno", "personalno")
    if not f.get("expires_on"):
        f["expires_on"] = _date_of(lines, "expirydate", "dateofexpiry", "expiry", "expireson", "validuntil", "validtill", "validupto", "expdate", "expires")
    f["issued_on"] = _date_of(lines, "issuedate", "dateofissue", "issuedon", "issuingdate", "dateofissuing", "issued")
    if not f.get("expires_on"):                  # an ID card with two dates: the later is the expiry
        ds = sorted({A.a_date(m.group(0)) for m in re.finditer(r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{4}\b", flat)} - {None})
        if len(ds) >= 2:
            f["expires_on"], f["issued_on"] = ds[-1].isoformat(), f.get("issued_on") or ds[-2].isoformat()
    if not f.get("name"):
        v = _lab(lines, "name", "fullname", "nameofholder", "holdername")
        f["name"] = v if v and len(v) < 60 else ""
    return _out(f, [("kind", "Document"), ("number", "Number"), ("issued_on", "Issued"), ("expires_on", "Expires"), ("name", "Name")])


def read_delivery(lines, flat):
    """A delivery note / supplier invoice for material -> supplier, DO / invoice no., date, LPO ref and the lines
    (material, quantity, unit) - priced or not."""
    f = {}
    f["supplier"] = _vendor(lines)
    f["ref"] = _ref(lines, "dono", "deliverynoteno", "deliveryno", "dnno", "deliveryorderno", "invoiceno", "taxinvoiceno", "invno", "challanno", "ref", "refno")
    f["date"] = _date_of(lines, "deliverydate", "dodate", "date", "invoicedate", "dated") or _letter_date(lines)
    f["lpo"] = _ref(lines, "lpono", "lpo", "pono", "purchaseorderno", "yourpono", "orderno", "yourref", "customerref")
    f["trn"] = _trn(flat)
    f["items"] = _material_rows(lines)
    return _out(f, [("supplier", "Supplier"), ("ref", "DO / invoice no."), ("date", "Date"), ("lpo", "LPO ref."), ("items", "Material lines")])


def _material_rows(lines):
    """The material lines under a 'Description ... Qty' heading: on each row the words are the material, the
    last figure the quantity, a short word like 'ton' / 'bag' the unit, a priced row's rate kept too. Read row by
    row rather than by column, so a scan that joins or loses a column still gives the lines."""
    def is_head(l):
        s = " ".join(A.squash(c) for c in l["c"])
        return any(k in s for k in ("description", "material", "particular", "product", "itemname")) and any(k in s for k in ("qty", "quantity", "qnty", "unit", "uom"))
    hi = next((i for i, l in enumerate(lines) if is_head(l)), None)
    if hi is None:
        return []
    units = {u.strip(".") for u in A.UNITS}
    items = []
    for l in lines[hi + 1:]:
        if is_head(l):
            continue
        if re.search(r"\b(total|received|receiver|signature|driver|remarks|terms|prepared|checked|thank)\b", l["t"], re.I) and not items == []:
            break
        if l.get("edge"):
            continue
        NUM = re.compile(r"'?\d[\d,]*(\.\d+)?")
        cells = []
        for c in l["c"]:
            c = c.strip(" |'`")
            if not c:
                continue
            # 'roll 10' / 'ton 2.5': a unit and the quantity run into one cell
            m = re.fullmatch(r"(.*?)\s*\b([A-Za-z.]{1,8})\s+(\d[\d,]*(?:\.\d+)?)((?:\s+\d[\d,]*(?:\.\d+)?)*)", c)
            if m and m.group(2).lower().strip(".") in units:
                if m.group(1).strip():
                    cells.append(m.group(1).strip())
                cells += [m.group(2), m.group(3)] + m.group(4).split()
                continue
            cells.append(c)
        kinds = ["n" if NUM.fullmatch(c) else ("u" if c.lower().strip(".") in units else "t") for c in cells]
        texts = [k for k, t in enumerate(kinds) if t == "t"]
        if not texts:
            if items and items[-1]["qty"] is None and "n" in kinds:
                items[-1]["qty"] = float(cells[max(k for k, t in enumerate(kinds) if t == "n")].strip("'").replace(",", ""))
            continue
        desc = " ".join(cells[k] for k in texts)
        desc = re.sub(r"^['`]?\d{1,3}[.)]?\s+", "", desc).strip(" -|")
        if len(desc) < 3 or not re.search(r"[A-Za-z]{2}", desc):
            continue
        after = [float(cells[k].strip("'").replace(",", "")) for k in range(texts[-1] + 1, len(cells)) if kinds[k] == "n"]
        unit = next((cells[k].lower().strip(".") for k in range(texts[-1] + 1, len(cells)) if kinds[k] == "u"), "")
        qty = after[0] if after else None
        rate = after[1] if len(after) >= 3 else None
        items.append({"description": desc, "qty": qty, "unit": unit, "rate": rate})
    return items


def read_quotation(lines, flat):
    """A supplier's quotation -> supplier, quotation ref and date, TRN, the priced lines (for a purchase order)."""
    f = {}
    f["supplier"] = _vendor(lines)
    f["ref"] = _ref(lines, "quotationno", "quoteno", "quotationref", "quoteref", "qtnno", "ourref", "refno", "ref", "proformano", "offerno")
    f["date"] = _date_of(lines, "quotationdate", "quotedate", "date", "dated") or _letter_date(lines)
    f["trn"] = _trn(flat)
    r = A.read(lines)
    f["items"] = [{"description": x["description"], "qty": x.get("qty") or 1, "unit": x.get("unit") or "", "rate": x.get("rate") or x["amount"],
                   "amount": x["amount"]} for x in r["items"]]
    f["total"] = r["checks"].get("total_in_doc") or r["checks"].get("items_total")
    return _out(f, [("supplier", "Supplier"), ("ref", "Quotation ref."), ("date", "Date"), ("trn", "TRN"), ("items", "Priced lines")])


APP_READERS = {"receipt": read_receipt, "cheque": read_cheque, "iddoc": read_iddoc, "delivery": read_delivery, "quotation": read_quotation}


import auth as _auth  # noqa: E402
import models as _models  # noqa: E402


@router.post("/store/docread/{kind}")
def read_any(kind: str, payload: dict = Body(...), user: _models.User = Depends(_auth.get_current_user)):
    """The text of a document opened in the browser (receipt, cheque, passport / ID, delivery note, quotation)
    -> the fields of the form it is for. For any signed-in user; nothing is saved here."""
    fn = APP_READERS.get(kind)
    if not fn:
        raise HTTPException(404, "Nothing reads that kind of document.")
    lines = payload.get("lines") or []
    if not isinstance(lines, list) or not lines or len(lines) > 20000:
        raise HTTPException(400, "No text came from that file.")
    lines = A.clean_lines(lines)
    r = fn(lines, _flat(lines))
    if kind in ("delivery", "quotation"):
        r["items"] = r["fields"].pop("items", [])
    return r

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
    f["inv_amount"] = tot
    # the bill's own lines
    rows = max(tables, key=lambda t: len(t["rows"]))["rows"] if tables else []
    inv_lines = [{"d": r["description"][:300], "a": r["amount"]} for r in rows if r["description"]][:40]
    if inv_lines:
        import json
        f["inv_lines"] = json.dumps(inv_lines)
    # which subcontractor: a name on the invoice that matches one on this project
    hay = A.squash(flat)
    best = None
    for s in subs or []:
        key = A.squash(re.sub(r"\b(llc|l\.l\.c|fze|fzc|est|establishment|co|company|trading|contracting|ms)\b", "", (s.get("name") or "").lower()))
        if len(key) >= 5 and key in hay and (best is None or len(key) > best[1]):
            best = (s["id"], len(key))
    if best:
        f["sub_id"] = best[0]
    m = re.search(r"(?:work\s+done|value\s+of\s+work|cumulative|gross\s+value)[^.\d]{0,50}?(?:to\s+date)?[^.\d]{0,30}?(?:AED\s*)?([\d,]{4,}(?:\.\d{1,2})?)", flat, re.I)
    if m and re.search(r"to\s+date|cumulative", m.group(0), re.I):
        f["work_cum"] = float(m.group(1).replace(",", ""))
    return _out(f, [("sub_id", "Subcontractor"), ("inv_ref", "Invoice no."), ("inv_date", "Invoice date"), ("inv_amount", "Invoice amount"),
                    ("inv_lines", "Bill lines"), ("work_cum", "Work done to date")])


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

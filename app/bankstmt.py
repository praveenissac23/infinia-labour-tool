"""ADCB statement check - Accounts > Bank.

The statement downloaded from ADCB (Excel or CSV) is uploaded here. Each
line is matched to what was entered on the Bank tab:

  1. the ADCB reference (PHUB...) found on the statement line,
  2. for a cheque, its number on the statement line,
  3. otherwise the same amount, the same way (in / out), within 3 days -
     only when exactly one entry fits, never a guess between two.

What is left over is the work: lines in the bank that nobody entered,
and entries that never reached the bank. The running balance printed on
the statement is added up line by line, so a file with lines missing is
caught too.
"""
import csv
import hashlib
import io
import re
from datetime import date, datetime, timedelta
from html.parser import HTMLParser

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

import main as M
import models
from database import get_db

router = APIRouter()
BK = Depends(M.require_any_screen("accounts_bank"))
AMOUNT_DAYS = 3      # same amount within this many days
REF_DAYS = 45        # a reference match may be further apart
CHEQUE_DAYS = 90     # cheques clear late

# Column names seen on bank statements -> what they are.
SYN = {
    "date": ["transaction date", "posting date", "post date", "txn date", "trans date", "tran date", "booking date", "date"],
    "value": ["value date", "val date"],
    "desc": ["description", "narration", "narrative", "transaction details", "details", "particulars", "remarks", "transaction description"],
    "ref": ["reference number", "reference no", "reference", "ref no", "ref", "cheque no", "cheque number", "chq no",
            "customer reference", "bank reference", "transaction reference", "instrument no", "ref/cheque no"],
    "debit": ["debit amount", "debit", "withdrawal", "withdrawals", "amount dr", "dr amount", "dr", "money out", "paid out"],
    "credit": ["credit amount", "credit", "deposit", "deposits", "amount cr", "cr amount", "cr", "money in", "paid in"],
    "amount": ["transaction amount", "amount", "amount aed", "amount (aed)"],
    "drcr": ["dr/cr", "cr/dr", "debit/credit", "type", "dr / cr", "transaction type"],
    "balance": ["running balance", "balance", "available balance", "ledger balance", "balance aed"],
}


def _norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9/ ]", " ", str(s or "").lower())).strip()


def _key(s):
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


def _num(v):
    """'1,250.00' / '(500.00)' / '500.00 DR' / 1250 -> float, or None."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().upper().replace("AED", "").replace(",", "").replace(" ", "")
    neg = s.startswith("(") and s.endswith(")") or s.endswith("DR") or s.startswith("-")
    s = s.strip("()").replace("DR", "").replace("CR", "").lstrip("-+")
    try:
        n = float(s)
    except ValueError:
        return None
    return -n if neg else n


MON = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def _date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v or "").strip()
    if not s:
        return None
    s = s.split(" ")[0] if re.match(r"^\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4} \d", s) else s
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.match(r"^(\d{1,2})[-/. ]([A-Za-z]{3,9})[-/. ,]*(\d{2,4})$", s)
        if m:
            d, mo, y = int(m.group(1)), MON.get(m.group(2)[:3].lower()), int(m.group(3))
        else:
            m = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})$", s)     # day first, as in the UAE
            if not m:
                return None
            d, mo, y = map(int, m.groups())
        if y < 100:
            y += 2000
    try:
        return date(y, mo, d)
    except (TypeError, ValueError):
        return None


class _Html(HTMLParser):
    """Banks often send 'Excel' that is really a web page table."""
    def __init__(self):
        super().__init__(); self.rows, self.row, self.cell, self.inc = [], None, "", False

    def handle_starttag(self, tag, a):
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th"):
            self.inc, self.cell = True, ""

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.row is not None:
            self.row.append(self.cell.strip()); self.inc = False
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row); self.row = None

    def handle_data(self, d):
        if self.inc:
            self.cell += d


def read_rows(name, data):
    """The file as rows of cells, whatever the bank sent."""
    head = data[:8]
    if head.startswith(b"PK"):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
        best = []
        for ws in wb.worksheets:
            rows = [list(r) for r in ws.iter_rows(values_only=True)]
            if len(rows) > len(best):
                best = rows
        return best
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        # ADCB ProCash's "Listing Report" download is the old .xls format.
        try:
            import xlrd
        except ImportError:
            raise HTTPException(status_code=400, detail="This is an old Excel file (.xls) and the server cannot read it yet. Open it in Excel, Save As .xlsx or CSV, and upload that.")
        try:
            wb = xlrd.open_workbook(file_contents=data)
        except Exception:
            raise HTTPException(status_code=400, detail="This .xls file could not be read. Open it in Excel, Save As .xlsx or CSV, and upload that.")
        best = []
        for ws in wb.sheets():
            rows = [[c.value for c in ws.row(i)] for i in range(ws.nrows)]
            if len(rows) > len(best):
                best = rows
        return best
    if head.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="A PDF statement cannot be read. Download the statement from ADCB as Excel or CSV.")
    text = None
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = data.decode(enc); break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise HTTPException(status_code=400, detail="The file could not be read. Upload the statement as Excel (.xlsx) or CSV.")
    if "<table" in text[:20000].lower() or "<tr" in text[:20000].lower():
        p = _Html(); p.feed(text); return p.rows
    try:
        dialect = csv.Sniffer().sniff(text[:4000], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return [r for r in csv.reader(io.StringIO(text), dialect)]


def _header(rows):
    """Find the heading row and which column is which."""
    for i, r in enumerate(rows[:60]):
        names = [_norm(c) for c in r]
        cols = {}
        for kind in ("value", "date", "desc", "ref", "debit", "credit", "drcr", "amount", "balance"):
            for syn in SYN[kind]:
                hit = next((j for j, n in enumerate(names) if n == syn and j not in cols.values()), None)
                if hit is None:
                    hit = next((j for j, n in enumerate(names) if n and syn in n and len(syn) > 3 and j not in cols.values()
                                and not (kind == "date" and "value" in n)), None)
                if hit is not None:
                    cols[kind] = hit
                    break
        if "date" not in cols and "value" in cols:
            cols["date"] = cols["value"]
        if "date" in cols and (("debit" in cols and "credit" in cols) or "amount" in cols):
            return i, cols
    return None, None


REF_RX = re.compile(r"\b(PHUB\d{5,}|[A-Z]{2,6}\d{7,}|\d{10,})\b")


def parse(name, data):
    """-> list of {date, value_date, description, reference, debit, credit, balance} in file order."""
    return parse_rows(read_rows(name, data))


def parse_rows(rows):
    h, cols = _header(rows)
    if h is None:
        raise HTTPException(status_code=400, detail=(
            "Could not find the columns. The statement needs a Date column and either Debit and Credit columns "
            "or an Amount column. Send the file to the admin if it is the normal ADCB download."))
    out = []
    g = lambda r, k: r[cols[k]] if k in cols and cols[k] < len(r) else None
    # Every wordy column goes into the description, not just the one called
    # "description": ADCB's download keeps the beneficiary, the narration and
    # the remarks in separate columns, and a line that read "O/W TRF734975811"
    # alone told the office nothing.
    SKIP = re.compile(r"account|acc no|a/c|currency|branch|serial|^s\.? ?no|^sl|^sr|^no$|cheque|chq|instrument")
    heads = [_norm(c) for c in rows[h]]
    # In the file's own column order: on ADCB's download the "Customer
    # Reference" (what the office typed when paying) comes before the
    # bank's own "Transaction Description" (O/W TRF...), which reads best.
    text_cols = sorted([j for j, n in enumerate(heads) if n and j not in cols.values() and not SKIP.search(n)]
                       + ([cols["desc"]] if "desc" in cols else []))
    def words(r):
        seen, parts = set(), []
        for j in text_cols:
            v = r[j] if j < len(r) else None
            if v is None or isinstance(v, (int, float)) or isinstance(v, (date, datetime)):
                continue
            t = re.sub(r"\s+", " ", str(v)).strip()
            if not t or not re.search(r"[A-Za-z]", t) or _num(t) is not None or _date(t):
                continue      # "." and "-" mean nothing was typed
            k = t.upper()
            if k in seen or any(k in q for q in seen):
                continue
            seen.add(k); parts.append(t)
        return " · ".join(parts)
    chq_col = next((j for j, n in enumerate(heads) if re.search(r"\b(cheque|chq|instrument)\b", n or "")
                    and j != cols.get("ref")), None)
    for r in rows[h + 1:]:
        if not r or all(c in (None, "") for c in r):
            continue
        d = _date(g(r, "date"))
        if not d:
            continue
        desc = words(r) or str(g(r, "desc") or "").strip()
        if re.match(r"^(opening|closing|brought|carried) (balance|forward)", desc.lower()):
            continue
        if "debit" in cols and "credit" in cols:
            dr, cr = _num(g(r, "debit")), _num(g(r, "credit"))
            dr, cr = abs(dr or 0), abs(cr or 0)
        else:
            a = _num(g(r, "amount"))
            if a is None:
                continue
            way = _norm(g(r, "drcr"))
            if way.startswith(("dr", "debit", "d")) and way:
                dr, cr = abs(a), 0.0
            elif way.startswith(("cr", "credit", "c")) and way:
                dr, cr = 0.0, abs(a)
            else:
                dr, cr = (abs(a), 0.0) if a < 0 else (0.0, a)
        if not dr and not cr:
            continue
        ref = str(g(r, "ref") or "").strip()
        if ref.endswith(".0") and ref[:-2].isdigit():
            ref = ref[:-2]
        # A separate cheque number column (ADCB keeps one beside "Customer Reference"): read it too - it is
        # how a cheque payment is matched, and it belongs in the line's words.
        if chq_col is not None and chq_col < len(r) and r[chq_col] not in (None, ""):
            chq = str(r[chq_col]).strip()
            if chq.endswith(".0") and chq[:-2].isdigit():
                chq = chq[:-2]
            if chq and chq != ref:
                if _key(chq) not in _key(desc):
                    desc = (desc + f" CHQ {chq}").strip()
                ref = ref or chq
        if not ref:
            m = REF_RX.search(desc.upper())
            ref = m.group(1) if m else ""
        out.append({"date": d, "value_date": _date(g(r, "value")), "description": desc[:300], "reference": ref[:80],
                    "debit": round(dr, 2), "credit": round(cr, 2), "balance": _num(g(r, "balance"))})
    if not out:
        raise HTTPException(status_code=400, detail="No bank lines found under the headings in this file.")
    return out


def balance_check(lines):
    """Add the lines up against the balance the bank printed. Returns
    (breaks, opening, closing) - breaks = places it does not add up,
    usually a line missing from the file."""
    bal = [l for l in lines if l["balance"] is not None]
    if len(bal) < 2:
        return 0, None, None
    def run(seq):
        n = 0
        for a, b in zip(seq, seq[1:]):
            if abs(a["balance"] + b["credit"] - b["debit"] - b["balance"]) > 0.011:
                n += 1
        return n
    fwd, back = run(bal), run(bal[::-1])
    seq = bal if fwd <= back else bal[::-1]
    first, last = seq[0], seq[-1]
    return min(fwd, back), round(first["balance"] - first["credit"] + first["debit"], 2), round(last["balance"], 2)


def _fp(l, n):
    base = "|".join([l["date"].isoformat(), f"{l['debit']:.2f}", f"{l['credit']:.2f}",
                     "" if l["balance"] is None else f"{l['balance']:.2f}", _key(l["reference"]), _key(l["description"])[:60], str(n)])
    return hashlib.sha1(base.encode()).hexdigest()


# ---- matching ---------------------------------------------------------------------------

def _out(e):
    return e.kind != "customer"


def _digits(s):
    return re.sub(r"\D", "", str(s or "")).lstrip("0")


def match_all(db, lines=None):
    """Match the unmatched statement lines to entries. Safe to run again
    and again - only certain matches are made."""
    taken = {l.entry_id for l in db.query(models.BankStmtLine).filter(models.BankStmtLine.entry_id.isnot(None)).all()}
    # an entry that was removed frees its line
    live = {e.id for e in db.query(models.BankEntry.id).all()}
    for l in db.query(models.BankStmtLine).filter(models.BankStmtLine.entry_id.isnot(None)).all():
        if l.entry_id not in live:
            taken.discard(l.entry_id); l.entry_id, l.match_how = None, ""
    todo = lines if lines is not None else db.query(models.BankStmtLine).filter(
        models.BankStmtLine.entry_id.is_(None), models.BankStmtLine.ignored.is_(False)).all()
    todo = [l for l in todo if l.entry_id is None and not l.ignored]
    if not todo:
        db.commit(); return 0
    lo = min(l.on_date for l in todo) - timedelta(days=CHEQUE_DAYS)
    hi = max(l.on_date for l in todo) + timedelta(days=CHEQUE_DAYS)
    entries = [e for e in db.query(models.BankEntry).filter(models.BankEntry.on_date >= lo, models.BankEntry.on_date <= hi).all()
               if e.id not in taken]
    made = 0

    def amt_ok(l, e):
        return abs((l.debit if _out(e) else l.credit) - (e.amount or 0)) < 0.005 and ((l.debit > 0) == _out(e))

    # 1-2: reference and cheque number - certain
    for l in todo:
        text = _key(l.reference) + " " + _key(l.description)
        nums = set(re.findall(r"\d+", (l.reference or "") + " " + (l.description or "")))
        nums = {n.lstrip("0") for n in nums if n.strip("0")}
        for e in entries:
            if e.id in taken or not amt_ok(l, e):
                continue
            ek = _key(e.reference)
            gap = abs((l.on_date - e.on_date).days)
            if (e.mode or "") == "Cheque":
                if _digits(e.reference) and _digits(e.reference) in nums and gap <= CHEQUE_DAYS:
                    l.entry_id, l.match_how = e.id, "cheque"; taken.add(e.id); made += 1; break
            elif len(ek) >= 5 and ek in text and gap <= REF_DAYS:
                l.entry_id, l.match_how = e.id, "ref"; taken.add(e.id); made += 1; break
    # 3: the same amount, the same way, within 3 days - only when it can be nothing else
    rest = [l for l in todo if l.entry_id is None]
    for l in rest:
        cands = [e for e in entries if e.id not in taken and amt_ok(l, e) and abs((l.on_date - e.on_date).days) <= AMOUNT_DAYS]
        if len(cands) != 1:
            continue
        e = cands[0]
        rivals = [x for x in rest if x is not l and x.entry_id is None and amt_ok(x, e) and abs((x.on_date - e.on_date).days) <= AMOUNT_DAYS]
        if rivals:
            continue
        l.entry_id, l.match_how = e.id, "amount"; taken.add(e.id); made += 1
    db.commit()
    return made


# ---- endpoints --------------------------------------------------------------------------

def _line(l, ents):
    e = ents.get(l.entry_id)
    return {"id": l.id, "date": l.on_date.isoformat(), "description": l.note or l.description or "", "bank_text": l.description or "",
            "note": l.note or "", "reference": l.reference or "",
            "debit": l.debit or 0, "credit": l.credit or 0, "balance": l.balance, "entry_id": l.entry_id, "how": l.match_how or "",
            "entry": ({"party": e.party or "", "kind": e.kind, "date": e.on_date.isoformat(), "reference": e.reference or ""} if e else None),
            "ignored": bool(l.ignored), "ignore_reason": l.ignore_reason or ""}


@router.post("/store/bank/stmt/upload")
async def upload(file: UploadFile = File(...), db: Session = Depends(get_db), user: models.User = BK):
    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="The file is too big for a statement (over 8 MB).")
    return _ingest(db, user, file.filename or "", parse(file.filename or "", data))


@router.post("/store/bank/stmt/upload-text")
def upload_text(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = BK):
    """A PDF statement - or a scan of one - opened in the browser: only its words come here, laid out in
    lines and cells (portal/est/agreement.js). Each cell is put under its heading, a narration carried onto
    the next line is joined to its line, and the lines go in exactly as from the Excel download."""
    import est_agreement as A
    lines = payload.get("lines") or []
    if not lines:
        raise HTTPException(status_code=400, detail="No text came from that file.")
    names, rows = A.grid(lines, lambda cells: _header([cells])[0] is not None)
    if names is None:
        raise HTTPException(status_code=400, detail="Could not find the statement's headings (Date, Description, Debit, Credit, Balance) in that file.")
    _, cols = _header([names])
    ocr = any(l.get("ocr") for l in lines if isinstance(l, dict))
    table = [names]
    for r in rows:
        c = [_ocr_cell(x) for x in r["cells"]] if ocr else r["cells"]
        has_date = bool(_date(c[cols["date"]])) if cols["date"] < len(c) else False
        nums = any(_num(c[cols[k]]) is not None for k in ("debit", "credit", "amount", "balance") if k in cols and cols[k] < len(c))
        if not has_date and not nums and len(table) > 1:
            j = cols.get("desc", next((k for k, n in enumerate(names) if "desc" in _norm(n) or "narr" in _norm(n) or "particular" in _norm(n)), None))
            words = " ".join(x for x in c if x).strip()
            if j is not None and words and not re.match(r"^(opening|closing|total|balance)\b", words, re.I):
                table[-1][j] = (str(table[-1][j] or "") + " " + words).strip()
            continue
        table.append(list(c))
    got = parse_rows(table)
    mended = 0
    if ocr:                                   # newest first on some statements: mend in date order
        fwd = sorted(range(len(got)), key=lambda i: (got[i]["date"], i))
        back = got[0]["date"] > got[-1]["date"]
        seq = got[::-1] if back else got
        mended = _mend(seq)
    out = _ingest(db, user, str(payload.get("name") or "statement.pdf"), got)
    out["mended"] = mended
    return out


def _ocr_cell(v):
    """What a scan does to a statement's figures and dates: '321.270.00' (a comma read as a point),
    '0510/2026' (a slash lost), two dates run into one cell."""
    t = str(v or "").strip()
    if re.fullmatch(r"[\d.,]+", t) and t.count(".") >= 2:
        head, _, tail = t.rpartition(".")
        t = head.replace(".", ",") + "." + tail
    m = re.fullmatch(r"(\d{2})(\d{2})[/.-](20\d{2})", t) or re.fullmatch(r"(\d{2})[/.-](\d{2})(20\d{2})", t)
    if m:
        t = f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
    m = re.fullmatch(r"(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})\s+\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}", t)
    if m:
        t = m.group(1)
    return t


def _mend(lines):
    """A scanned statement: a figure the scan misread is put right from the running balance the bank printed -
    only where the balance says exactly what it must be AND the misread figure has (nearly) the same digits.
    Anything else is left for the balance check to warn about. -> how many figures were put right."""
    def digits(x):
        return f"{abs(x):.2f}".replace(".", "").rstrip("0").lstrip("0") or "0"

    def near(a, b):                       # the same digits, or one digit added / lost / misread
        a, b = digits(a), digits(b)
        if a == b:
            return True
        if abs(len(a) - len(b)) > 1:
            return False
        if len(a) == len(b):
            return sum(x != y for x, y in zip(a, b)) <= 1
        s, t = (a, b) if len(a) < len(b) else (b, a)
        return any(t[:i] + t[i + 1:] == s for i in range(len(t)))

    ok = lambda a, b: a["balance"] is not None and b["balance"] is not None and abs(a["balance"] + b["credit"] - b["debit"] - b["balance"]) <= 0.011
    n = 0
    # a balance misread: the lines either side add up across it
    for i in range(1, len(lines) - 1):
        a, b, c = lines[i - 1], lines[i], lines[i + 1]
        if a["balance"] is None or c["balance"] is None or (ok(a, b) and ok(b, c)):
            continue
        want = round(a["balance"] + b["credit"] - b["debit"], 2)
        if abs(want + c["credit"] - c["debit"] - c["balance"]) <= 0.011 and (b["balance"] is None or near(b["balance"], want)):
            b["balance"] = want; n += 1
    # an amount misread: the balances before and after say what it was
    for i in range(1, len(lines)):
        a, b = lines[i - 1], lines[i]
        if a["balance"] is None or b["balance"] is None or ok(a, b):
            continue
        delta = round(b["balance"] - a["balance"], 2)
        read = b["debit"] or b["credit"]
        if delta and read and near(read, delta):
            b["debit"], b["credit"] = (round(-delta, 2), 0.0) if delta < 0 else (0.0, delta)
            n += 1
    return n


def _ingest(db, user, filename, lines):
    breaks, opening, closing = balance_check(lines)
    up = models.BankStmtUpload(filename=(filename or "")[:120], date_from=min(l["date"] for l in lines),
                               date_to=max(l["date"] for l in lines), lines=len(lines), breaks=breaks,
                               opening=opening, closing=closing, uploaded_by=user.id)
    db.add(up); db.flush()
    seen, have, new, reworded = {}, {f for (f,) in db.query(models.BankStmtLine.fp).all()}, [], 0
    # The same bank line, when its description was read differently last
    # time (an earlier version kept only one column): recognised by date,
    # amounts, balance and reference, and its text brought up to date.
    loose = {}
    for x in (db.query(models.BankStmtLine).filter(models.BankStmtLine.on_date >= up.date_from,
                                                  models.BankStmtLine.on_date <= up.date_to).all()):
        loose.setdefault((x.on_date, round(x.debit or 0, 2), round(x.credit or 0, 2), x.balance, _key(x.reference)), []).append(x)
    for l in lines:
        base = (l["date"], l["debit"], l["credit"], l["balance"], _key(l["reference"]), _key(l["description"])[:60])
        seen[base] = seen.get(base, 0) + 1
        fp = _fp(l, seen[base])
        if fp in have:
            continue
        twins = loose.get((l["date"], l["debit"], l["credit"], l["balance"], _key(l["reference"])), []) if l["reference"] else []
        twin = next((x for x in twins if _key(x.description)[:60] and _key(x.description)[:60] in _key(l["description"])
                     and _key(x.description) != _key(l["description"])), None)
        if twin is not None:
            twin.description, twin.fp = l["description"], fp; have.add(fp); twins.remove(twin); reworded += 1
            continue
        have.add(fp)
        x = models.BankStmtLine(on_date=l["date"], value_date=l["value_date"], description=l["description"], reference=l["reference"],
                                debit=l["debit"], credit=l["credit"], balance=l["balance"], fp=fp, upload_id=up.id)
        db.add(x); new.append(x)
    up.added = len(new)
    db.commit()
    made = match_all(db, new)
    M.log_action(db, user.id, "bank_statement", f"ADCB statement {up.date_from} to {up.date_to}: {len(lines)} lines, {len(new)} new, {made} matched")
    return {"ok": True, "lines": len(lines), "added": len(new), "duplicates": len(lines) - len(new), "matched": made, "reworded": reworded,
            "from": up.date_from.isoformat(), "to": up.date_to.isoformat(), "breaks": breaks, "opening": opening, "closing": closing}


@router.get("/store/bank/stmt")
def check(month: str = "", start: str = "", end: str = "", db: Session = Depends(get_db), user: models.User = BK):
    import bank
    a, b, _label = bank._period(month, start, end)
    match_all(db)
    q = db.query(models.BankStmtLine).filter(models.BankStmtLine.on_date >= a, models.BankStmtLine.on_date <= b)
    lines = q.order_by(models.BankStmtLine.on_date, models.BankStmtLine.id).all()
    ents = {e.id: e for e in db.query(models.BankEntry).filter(models.BankEntry.id.in_([l.entry_id for l in lines if l.entry_id] or [0])).all()}
    last = db.query(models.BankStmtUpload).order_by(models.BankStmtUpload.date_to.desc(), models.BankStmtUpload.id.desc()).first()
    ups = [(u.date_from or u.date_to, u.date_to) for u in db.query(models.BankStmtUpload).all() if u.date_to]
    covered = max((t for f, t in ups), default=None)
    # only a day a statement was uploaded for can say an entry is missing (no statement for 15 Oct: nothing to say)
    on_statement = lambda d: any(f <= d <= t for f, t in ups)
    # entries this month the statement should already show, that it does not
    matched_ids = {l.entry_id for l in db.query(models.BankStmtLine).filter(models.BankStmtLine.entry_id.isnot(None)).all()}
    missing = []
    if covered:
        for e in db.query(models.BankEntry).filter(models.BankEntry.on_date >= a, models.BankEntry.on_date <= min(b, covered)).all():
            if e.id in matched_ids or not on_statement(e.on_date):
                continue
            # a cheque can clear days after its date - give it a week before calling it missing
            if (e.mode or "") == "Cheque" and (covered - e.on_date).days < 7:
                continue
            missing.append({"id": e.id, "date": e.on_date.isoformat(), "party": e.party or "", "kind": e.kind,
                            "reference": e.reference or "", "amount": round(e.amount or 0, 2), "out": _out(e), "mode": e.mode or ""})
    users = {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}
    out = [_line(l, ents) for l in lines]
    return {"month": f"{a:%Y-%m}", "lines": out, "missing": missing,
            "counts": {"lines": len(out), "matched": sum(1 for l in out if l["entry_id"]),
                       "not_entered": sum(1 for l in out if not l["entry_id"] and not l["ignored"]),
                       "ignored": sum(1 for l in out if l["ignored"]), "not_in_bank": len(missing)},
            "covered_to": covered.isoformat() if covered else "",
            "last": ({"at": last.created_at.isoformat() if last.created_at else "", "by": users.get(last.uploaded_by, ""),
                      "file": last.filename, "from": last.date_from.isoformat(), "to": last.date_to.isoformat(),
                      "breaks": last.breaks, "closing": last.closing, "id": last.id} if last else None)}


def _get(db, lid):
    l = db.get(models.BankStmtLine, lid)
    if not l:
        raise HTTPException(status_code=404, detail="That statement line is not there.")
    return l


@router.get("/store/bank/stmt/{lid}/candidates")
def candidates(lid: int, db: Session = Depends(get_db), user: models.User = BK):
    """Entries that could be this line: same way (in / out), same amount, not matched yet."""
    l = _get(db, lid)
    taken = {x.entry_id for x in db.query(models.BankStmtLine).filter(models.BankStmtLine.entry_id.isnot(None)).all()}
    amt = l.debit or l.credit
    es = [e for e in db.query(models.BankEntry).filter(models.BankEntry.on_date >= l.on_date - timedelta(days=CHEQUE_DAYS),
                                                       models.BankEntry.on_date <= l.on_date + timedelta(days=CHEQUE_DAYS)).all()
          if e.id not in taken and _out(e) == (l.debit > 0) and abs((e.amount or 0) - amt) < 0.005]
    es.sort(key=lambda e: abs((e.on_date - l.on_date).days))
    return {"entries": [{"id": e.id, "date": e.on_date.isoformat(), "party": e.party or "", "kind": e.kind, "reference": e.reference or "",
                         "amount": round(e.amount or 0, 2), "mode": e.mode or ""} for e in es[:30]]}


@router.post("/store/bank/stmt/{lid}/match")
def match(lid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = BK):
    l = _get(db, lid)
    e = db.get(models.BankEntry, int(payload.get("entry_id") or 0))
    if not e:
        raise HTTPException(status_code=400, detail="Pick the entry this bank line is.")
    if _out(e) != (l.debit > 0):
        raise HTTPException(status_code=400, detail="One is money in and the other money out - they cannot be the same.")
    if abs((e.amount or 0) - (l.debit or l.credit)) >= 0.005:
        raise HTTPException(status_code=400, detail=f"The amounts differ ({e.amount:,.2f} entered, {(l.debit or l.credit):,.2f} in the bank). Correct the entry first.")
    other = db.query(models.BankStmtLine).filter(models.BankStmtLine.entry_id == e.id, models.BankStmtLine.id != l.id).first()
    if other:
        raise HTTPException(status_code=400, detail="That entry is already matched to another bank line.")
    l.entry_id, l.match_how, l.matched_by, l.ignored = e.id, "manual", user.id, False
    db.commit()
    M.log_action(db, user.id, "bank_statement", f"bank line {l.on_date} {(l.debit or l.credit):,.2f} matched by hand to entry #{e.id}")
    return {"ok": True}


@router.post("/store/bank/stmt/{lid}/unmatch")
def unmatch(lid: int, db: Session = Depends(get_db), user: models.User = BK):
    l = _get(db, lid)
    l.entry_id, l.match_how = None, ""
    db.commit()
    return {"ok": True}


@router.post("/store/bank/stmt/{lid}/ignore")
def ignore(lid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = BK):
    l = _get(db, lid)
    why = M.tidy_text(payload.get("reason"))[:200]
    if payload.get("undo"):
        l.ignored, l.ignore_reason = False, ""
    else:
        if not why:
            raise HTTPException(status_code=400, detail="Write why this bank line needs no entry (e.g. reversed the same day).")
        l.ignored, l.ignore_reason, l.entry_id, l.match_how = True, why, None, ""
    db.commit()
    M.log_action(db, user.id, "bank_statement", f"bank line {l.on_date} {(l.debit or l.credit):,.2f} " + ("back on the list" if payload.get("undo") else f"set aside: {why}"))
    return {"ok": True}


@router.post("/store/bank/stmt/{lid}/note")
def note(lid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = BK):
    """The office's own wording for a bank line (the bank's text is kept
    underneath, so a re-uploaded statement still recognises the line)."""
    l = _get(db, lid)
    l.note = M.tidy_text(payload.get("note"))[:300]
    db.commit()
    M.log_action(db, user.id, "bank_statement", f"bank line {l.on_date} {(l.debit or l.credit):,.2f} described as: {l.note or '(bank text)'}")
    return {"ok": True, "note": l.note}


@router.delete("/store/bank/stmt/upload/{uid}")
def remove_upload(uid: int, db: Session = Depends(get_db), user: models.User = BK):
    """A wrong file uploaded: take its lines off again."""
    up = db.get(models.BankStmtUpload, uid)
    if not up:
        raise HTTPException(status_code=404, detail="That upload is not there.")
    n = db.query(models.BankStmtLine).filter(models.BankStmtLine.upload_id == uid).delete()
    db.delete(up); db.commit()
    M.log_action(db, user.id, "bank_statement", f"statement upload #{uid} ({up.filename}) removed, {n} lines")
    return {"ok": True, "removed": n}

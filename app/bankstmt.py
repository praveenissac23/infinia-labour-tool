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
        raise HTTPException(status_code=400, detail="This is an old Excel file (.xls). Open it in Excel, Save As .xlsx or CSV, and upload that.")
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
    rows = read_rows(name, data)
    h, cols = _header(rows)
    if h is None:
        raise HTTPException(status_code=400, detail=(
            "Could not find the columns. The statement needs a Date column and either Debit and Credit columns "
            "or an Amount column. Send the file to the admin if it is the normal ADCB download."))
    out = []
    g = lambda r, k: r[cols[k]] if k in cols and cols[k] < len(r) else None
    for r in rows[h + 1:]:
        if not r or all(c in (None, "") for c in r):
            continue
        d = _date(g(r, "date"))
        if not d:
            continue
        desc = str(g(r, "desc") or "").strip()
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
    return {"id": l.id, "date": l.on_date.isoformat(), "description": l.description or "", "reference": l.reference or "",
            "debit": l.debit or 0, "credit": l.credit or 0, "balance": l.balance, "entry_id": l.entry_id, "how": l.match_how or "",
            "entry": ({"party": e.party or "", "kind": e.kind, "date": e.on_date.isoformat(), "reference": e.reference or ""} if e else None),
            "ignored": bool(l.ignored), "ignore_reason": l.ignore_reason or ""}


@router.post("/store/bank/stmt/upload")
async def upload(file: UploadFile = File(...), db: Session = Depends(get_db), user: models.User = BK):
    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="The file is too big for a statement (over 8 MB).")
    lines = parse(file.filename or "", data)
    breaks, opening, closing = balance_check(lines)
    up = models.BankStmtUpload(filename=(file.filename or "")[:120], date_from=min(l["date"] for l in lines),
                               date_to=max(l["date"] for l in lines), lines=len(lines), breaks=breaks,
                               opening=opening, closing=closing, uploaded_by=user.id)
    db.add(up); db.flush()
    seen, have, new = {}, {f for (f,) in db.query(models.BankStmtLine.fp).all()}, []
    for l in lines:
        base = (l["date"], l["debit"], l["credit"], l["balance"], _key(l["reference"]), _key(l["description"])[:60])
        seen[base] = seen.get(base, 0) + 1
        fp = _fp(l, seen[base])
        if fp in have:
            continue
        have.add(fp)
        x = models.BankStmtLine(on_date=l["date"], value_date=l["value_date"], description=l["description"], reference=l["reference"],
                                debit=l["debit"], credit=l["credit"], balance=l["balance"], fp=fp, upload_id=up.id)
        db.add(x); new.append(x)
    up.added = len(new)
    db.commit()
    made = match_all(db, new)
    M.log_action(db, user.id, "bank_statement", f"ADCB statement {up.date_from} to {up.date_to}: {len(lines)} lines, {len(new)} new, {made} matched")
    return {"ok": True, "lines": len(lines), "added": len(new), "duplicates": len(lines) - len(new), "matched": made,
            "from": up.date_from.isoformat(), "to": up.date_to.isoformat(), "breaks": breaks, "opening": opening, "closing": closing}


@router.get("/store/bank/stmt")
def check(month: str = "", db: Session = Depends(get_db), user: models.User = BK):
    import bank
    a, b = bank._month(month)
    match_all(db)
    q = db.query(models.BankStmtLine).filter(models.BankStmtLine.on_date >= a, models.BankStmtLine.on_date <= b)
    lines = q.order_by(models.BankStmtLine.on_date, models.BankStmtLine.id).all()
    ents = {e.id: e for e in db.query(models.BankEntry).filter(models.BankEntry.id.in_([l.entry_id for l in lines if l.entry_id] or [0])).all()}
    last = db.query(models.BankStmtUpload).order_by(models.BankStmtUpload.date_to.desc(), models.BankStmtUpload.id.desc()).first()
    covered = max((u.date_to for u in db.query(models.BankStmtUpload).all() if u.date_to), default=None)
    # entries this month the statement should already show, that it does not
    matched_ids = {l.entry_id for l in db.query(models.BankStmtLine).filter(models.BankStmtLine.entry_id.isnot(None)).all()}
    missing = []
    if covered:
        for e in db.query(models.BankEntry).filter(models.BankEntry.on_date >= a, models.BankEntry.on_date <= min(b, covered)).all():
            if e.id in matched_ids:
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

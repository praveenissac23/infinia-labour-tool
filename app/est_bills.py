"""Estimation > Bills: the monthly bill (interim payment application) to the client / consultant, in their own format.

A project's format is uploaded once - the last bill as the consultant wants it, as an Excel workbook. Each month
"New bill" starts from the last one: Previous % takes last month's Total %, the bill no. moves on, the issue date
is today, last bill goes onto the previous payments to be completed when the money comes in. Staff type the
month's Total % on each line (and anything else typed on the sheets - payments, authority fees); every formula is
worked out as Excel does. The bill goes out as the same workbook (Excel), or printed / PDF.
"""
import io
import json
import os
import tempfile
import re
from datetime import date, datetime

from fastapi import Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy import Column, Date, DateTime, Float, Integer, LargeBinary, String, Text, func
from sqlalchemy.orm import Session

import auth
import models
from database import Base, get_db
import estimation as E
import est_bills_engine as BE
import est_bills_render as BR

router = E.router
STATUSES = ["Draft", "Submitted", "Certified", "Paid"]


class EstBillFormat(Base):
    __tablename__ = "est_bill_formats"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, nullable=False, index=True)
    name = Column(String, default="")              # "IPA - Emkaan format"
    filename = Column(String, default="")
    data = Column(LargeBinary)                     # the workbook as uploaded (the bill comes out as this file)
    model = Column(Text, default="")               # read once: cells, formulas, look, where the month's figures go
    checked = Column(Text, default="")             # how many formulas give Excel's own figures
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class EstBill(Base):
    __tablename__ = "est_bills"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, nullable=False, index=True)
    format_id = Column(Integer, nullable=False, index=True)
    seq = Column(Integer, default=1)
    label = Column(String, default="")             # the bill no. as on the bill (9, 7-R2 ...)
    issue_date = Column(Date, nullable=True)
    status = Column(String, default="Draft")
    inputs = Column(Text, default="{}")            # {sheet: {"r,c": value}} - what was typed this month
    total_due = Column(Float, default=0.0)
    work_done = Column(Float, default=0.0)
    notes = Column(Text, default="")
    created_by = Column(Integer, nullable=True)
    updated_by = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


def create_tables(engine):
    for t in (EstBillFormat, EstBill):
        t.__table__.create(bind=engine, checkfirst=True)


_MODEL_CACHE = {}


def _model(fmt):
    hit = _MODEL_CACHE.get(fmt.id)
    if hit is None:
        hit = json.loads(fmt.model or "{}")
        if hit.get("sheets") and hit.get("mv") != BE.MODEL_VERSION and fmt.data:
            try:                                          # read before the latest reading rules: read the kept workbook again
                hit = BE.read_format(fmt.data, fmt.filename or "")
            except Exception:
                pass
        if hit.get("sheets") and (hit.get("map") or {}).get("v") != BE.MAP_VERSION:
            hit["map"] = BE.find_inputs(hit)             # a format read before the latest reading rules
        _MODEL_CACHE[fmt.id] = hit
        if len(_MODEL_CACHE) > 12:
            _MODEL_CACHE.pop(next(iter(_MODEL_CACHE)))
    return hit


def _inputs(b):
    try:
        return json.loads(b.inputs or "{}")
    except ValueError:
        return {}


def _get(db, model, i):
    x = db.query(model).get(i)
    if not x:
        raise HTTPException(404, "That bill is not there any more." if model is EstBill else "That format is not there any more.")
    return x


def _date_of(v):
    if isinstance(v, (int, float)) and 20000 < v < 80000:
        return (BE.EPOCH.date() + __import__("datetime").timedelta(days=int(v)))
    if isinstance(v, str):
        m = re.match(r"^\s*(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\s*$", v)
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            try:
                return date(y + 2000 if y < 100 else y, mo, d)
            except ValueError:
                return None
    return None


def _facts(model, values):
    """Bill no., issue date, total due and work done to date, read from the worked-out sheets."""
    mp = model.get("map", {})
    g = lambda ref: values.get(ref["sheet"], {}).get(f"{ref['r']},{ref['c']}") if ref else None
    bno = g(mp.get("bill_no"))
    label = BE.general(bno) if bno is not None else ""
    total = g(mp.get("total_due"))
    work = 0.0
    for t in mp.get("progress", []):
        pass
    return {"label": label, "issue_date": _date_of(g(mp.get("issue_date"))), "total_due": float(total) if isinstance(total, (int, float)) else 0.0}


def _progress(model, values, inputs):
    """The lines staff update each month, sheet by sheet: description, amount, Previous %, Total %, this month."""
    out = []
    for t in model.get("map", {}).get("progress", []):
        sh = t["sheet"]
        vals = values.get(sh, {})
        lines = []
        for ln in t["lines"]:
            r = ln["r"]
            amt = vals.get(f"{r},{t['amount_c']}") if t.get("amount_c") else None
            prev = vals.get(f"{r},{t['prev_c']}")
            tot = vals.get(f"{r},{t['tot_c']}")
            how = ln.get("how", "tot" if ln["typed_total"] else None)
            cur = vals.get(f"{r},{t['cur_c']}") if t.get("cur_c") else None
            lines.append({"r": r, "item": ln["item"], "desc": ln["desc"], "unit": ln.get("unit", ""),
                          "amount": amt if isinstance(amt, (int, float)) else None, "amount_text": amt if isinstance(amt, str) else "",
                          "prev": prev if isinstance(prev, (int, float)) else None, "total": tot if isinstance(tot, (int, float)) else None,
                          "cur": cur if isinstance(cur, (int, float)) else None,
                          "tot_key": f"{r},{t['tot_c']}", "prev_key": f"{r},{t['prev_c']}", "cur_key": f"{r},{t['cur_c']}" if t.get("cur_c") else None,
                          "how": how, "follows": ln.get("follows", ""),
                          "tot_typed": how == "tot", "prev_typed": ln["typed_prev"],
                          "changed": isinstance(tot, (int, float)) and isinstance(prev, (int, float)) and abs(tot - prev) > 1e-9})
        vis = next((x["visible"] for x in model["sheets"] if x["name"] == sh), True)
        out.append({"sheet": sh, "lines": lines, "hidden": not vis})
    out.sort(key=lambda t: t["hidden"])                  # sheets the consultant hid (not printed) go last
    return out


def _payments(model, values, inputs):
    mp = model.get("map", {})
    out = []
    for p in mp.get("payments", []):
        sh, cols = p["sheet"], p["cols"]
        vals = values.get(sh, {})
        s = next(x for x in model["sheets"] if x["name"] == sh)
        rows = []
        for r in range(p["head_row"] + 1, p["total_row"]):
            row = {"r": r}
            for k, c in cols.items():
                key = f"{r},{c}"
                raw = inputs.get(sh, {}).get(key)
                cell = s["cells"].get(key) or {}
                if raw is None:
                    raw = cell.get("v") if "v" in cell else (("=" + cell["f"]) if "f" in cell else None)
                row[k] = {"key": key, "value": vals.get(key), "raw": raw, "nf": model["styles"][cell.get("s", 0)].get("nf", "General")}
            rows.append(row)
        total = vals.get(f"{p['total_row']},{cols['amount']}")
        out.append({"sheet": sh, "cols": list(cols.keys()), "rows": rows, "total": total if isinstance(total, (int, float)) else None})
    return out


def _cover(model, values):
    """The payment summary on the cover, as the consultant set it out: each line's words and amount, the total due
    and the amount in words - shown on the bill's first step."""
    mp = model.get("map", {})
    td = mp.get("total_due")
    if not td:
        return None
    s = next((x for x in model["sheets"] if x["name"] == td["sheet"]), None)
    if not s:
        return None
    vals = values.get(s["name"], {})
    g = lambda r, c: vals.get(f"{r},{c}") if f"{r},{c}" in vals else (s["cells"].get(f"{r},{c}") or {}).get("v")
    top = td["r"]
    for r in range(td["r"] - 1, max(1, td["r"] - 30), -1):
        if any(isinstance(g(r, c), str) and re.fullmatch(r"\s*description\s*", g(r, c), re.I) for c in range(1, td["c"])):
            top = r
            break
    rows = []
    for r in range(top + 1, td["r"] + 1):
        if r in set(s.get("hidden_rows") or []):
            continue
        texts = [g(r, c) for c in range(1, td["c"]) if isinstance(g(r, c), str) and g(r, c).strip()]
        amt = g(r, td["c"])
        if not texts and not isinstance(amt, (int, float)):
            continue
        rows.append({"label": texts[0].strip() if texts else "", "detail": BR.tidy_text(" ".join(t.strip() for t in texts[1:])) if len(texts) > 1 else "",
                     "amount": amt if isinstance(amt, (int, float)) else None, "total": r == td["r"]})
    words = ""
    for w in mp.get("words", []):
        x = values.get(w["sheet"], {}).get(f"{w['r']},{w['c']}")
        if isinstance(x, str):
            words = x.strip()
    # the cover's own facts: "Project", "Location", "Client" ... with the value beside or under the label
    facts = {}
    want = {"project": r"project(\s+name)?", "location": r"location|site", "client": r"client|employer", "consultant": r"consultant|engineer"}
    for r in range(1, top):
        for c in range(1, s["maxc"] + 1):
            x = g(r, c)
            if not isinstance(x, str):
                continue
            t = x.strip().rstrip(":").strip()
            for k, pat in want.items():
                if k in facts:
                    continue
                m = re.match(rf"^({pat})\s*:\s*(.+)$", t, re.I | re.S)
                if m:                                          # "PROJECT NAME: PROPOSED ..." in one cell
                    facts[k] = m.group(m.lastindex).strip(); continue
                if re.fullmatch(pat, t, re.I):
                    right = next((g(r, cc) for cc in range(c + 1, min(c + 6, s["maxc"] + 1)) if isinstance(g(r, cc), str) and g(r, cc).strip()), None)
                    below = next((g(rr, c) for rr in range(r + 1, min(r + 4, top)) if isinstance(g(rr, c), str) and g(rr, c).strip()), None)
                    # Client / Consultant are usually headings with the name under them; Project / Location have it beside
                    v = (below or right) if k in ("client", "consultant") else (right or below)
                    if v and not re.fullmatch(r"(client|consultant|contractor|project|location)\s*:?", v.strip(), re.I):
                        facts[k] = v.strip()
    if "project" not in facts:                          # a title line across the top with no label
        for r in range(1, min(top, 4)):
            for c in range(1, s["maxc"] + 1):
                x = g(r, c)
                if isinstance(x, str) and len(x.strip()) > 25 and not re.search(r"payment application|interim", x, re.I):
                    facts["project"] = x.strip(); break
            if "project" in facts:
                break
    return {"rows": rows, "words": words, "facts": facts}


def _bill_out(b, fmt, model, values, inputs, users=None):
    f = _facts(model, values)
    return {"id": b.id, "project_id": b.project_id, "format_id": b.format_id, "format": fmt.name or fmt.filename, "seq": b.seq,
            "label": f["label"] or b.label, "issue_date": (f["issue_date"] or b.issue_date).isoformat() if (f["issue_date"] or b.issue_date) else "",
            "status": b.status, "total_due": f["total_due"], "notes": b.notes or "",
            "by": (users or {}).get(b.updated_by or b.created_by, ""),
            "sheets": [{"i": i, "name": s["name"]} for i, s in enumerate(model["sheets"]) if s["visible"]],
            "progress": _progress(model, values, inputs), "payments": _payments(model, values, inputs), "cover": _cover(model, values),
            "bill_no_raw": BE.general(values.get(model["map"]["bill_no"]["sheet"], {}).get(f"{model['map']['bill_no']['r']},{model['map']['bill_no']['c']}")) if model.get("map", {}).get("bill_no") else "",
            "has_date": bool(model.get("map", {}).get("issue_date")), "has_no": bool(model.get("map", {}).get("bill_no")),
            "changed": sum(len(v) for v in inputs.values())}


def _save_totals(b, model, values):
    f = _facts(model, values)
    b.total_due = f["total_due"]
    b.label = f["label"] or b.label
    b.issue_date = f["issue_date"] or b.issue_date


def _calc(model, inputs):
    inputs = BE.with_words(model, inputs)
    return inputs, BE.calculate(model, inputs)


# ---------------------------------------------------------------------------------------------------- reading

@router.get("/store/est/ipa/list")
def list_bills(project_id: int, db: Session = Depends(get_db), user: models.User = E.VIEW):
    users = {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}
    fmts = db.query(EstBillFormat).filter(EstBillFormat.project_id == project_id).order_by(EstBillFormat.id).all()
    bills = db.query(EstBill).filter(EstBill.project_id == project_id).order_by(EstBill.seq.desc(), EstBill.id.desc()).all()
    out_f = []
    for f in fmts:
        try:
            chk = json.loads(f.checked or "{}")
        except ValueError:
            chk = {}
        m = _model(f)
        mp = m.get("map", {})
        out_f.append({"id": f.id, "name": f.name or f.filename, "filename": f.filename, "on": f.created_at.date().isoformat() if f.created_at else "",
                      "by": users.get(f.created_by, ""), "formulas": chk.get("formulas", 0), "same": chk.get("same", 0),
                      "sheets": [s["name"] for s in m.get("sheets", []) if s["visible"]],
                      "lines": sum(len(t["lines"]) for t in mp.get("progress", [])), "bill_no": bool(mp.get("bill_no")),
                      "issue_date": bool(mp.get("issue_date")), "total_due": bool(mp.get("total_due")),
                      "bills": sum(1 for b in bills if b.format_id == f.id)})
    return {"formats": out_f, "statuses": STATUSES,
            "bills": [{"id": b.id, "seq": b.seq, "label": b.label, "issue_date": b.issue_date.isoformat() if b.issue_date else "",
                       "status": b.status, "total_due": round(b.total_due or 0, 2), "format_id": b.format_id,
                       "by": users.get(b.updated_by or b.created_by, ""), "updated": (b.updated_at or b.created_at).isoformat() if (b.updated_at or b.created_at) else ""}
                      for b in bills]}


@router.get("/store/est/ipa/bill/{bid}")
def get_bill(bid: int, db: Session = Depends(get_db), user: models.User = E.VIEW):
    b = _get(db, EstBill, bid)
    fmt = _get(db, EstBillFormat, b.format_id)
    model = _model(fmt)
    inputs = _inputs(b)
    values = BE.calculate(model, inputs)
    users = {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}
    return _bill_out(b, fmt, model, values, inputs, users)


@router.get("/store/est/ipa/bill/{bid}/sheet/{i}")
def bill_sheet(bid: int, i: int, db: Session = Depends(get_db), user: models.User = E.VIEW):
    """One sheet of the bill as laid out by the consultant, the cells staff may type in marked."""
    b = _get(db, EstBill, bid)
    fmt = _get(db, EstBillFormat, b.format_id)
    model = _model(fmt)
    if not (0 <= i < len(model["sheets"])):
        raise HTTPException(404, "No such sheet.")
    inputs = _inputs(b)
    values = BE.calculate(model, inputs)
    s = model["sheets"][i]
    mark = {}
    for t in model.get("map", {}).get("progress", []):
        if t["sheet"] == s["name"]:
            for ln in t["lines"]:
                mark[f"{ln['r']},{t['tot_c']}"] = "tot"
    html, w, h = BR.sheet_html(model, s, values, inputs, edit=b.status not in ("Paid",), mark=mark)
    return {"html": html, "width": w, "height": h, "name": s["name"], "css": BR.SHEET_CSS}


# ---------------------------------------------------------------------------------------------------- the format

_PARTS = os.path.join(tempfile.gettempdir(), "infinia_ipa_parts")


@router.post("/store/est/ipa/format/part")
async def upload_part(upload_id: str = Form(...), index: int = Form(...), file: UploadFile = File(...), user: models.User = E.VIEW):
    """A big workbook comes in pieces (the web server takes about 1 MB per request); put together by upload_format."""
    if not re.fullmatch(r"[a-f0-9]{16,40}", upload_id) or not (0 <= index < 60):
        raise HTTPException(400, "Bad upload.")
    os.makedirs(_PARTS, exist_ok=True)
    data = await file.read()
    with open(os.path.join(_PARTS, f"{user.id}_{upload_id}_{index:02d}"), "wb") as f:
        f.write(data)
    return {"ok": True, "bytes": len(data)}


def _joined(user_id, upload_id, parts):
    if not re.fullmatch(r"[a-f0-9]{16,40}", upload_id) or not (1 <= parts <= 60):
        raise HTTPException(400, "Bad upload.")
    out = b""
    for i in range(parts):
        fp = os.path.join(_PARTS, f"{user_id}_{upload_id}_{i:02d}")
        if not os.path.exists(fp):
            raise HTTPException(400, "Part of the file did not arrive - please upload it again.")
        with open(fp, "rb") as f:
            out += f.read()
        os.remove(fp)
    return out


@router.post("/store/est/ipa/format")
async def upload_format(project_id: int = Form(...), name: str = Form(""), file: UploadFile = File(None),
                        upload_id: str = Form(""), parts: int = Form(0), filename: str = Form(""),
                        db: Session = Depends(get_db), user: models.User = E.VIEW):
    E._project(db, project_id)
    if file is None:
        if not upload_id:
            raise HTTPException(400, "Pick the Excel bill.")
        data = _joined(user.id, upload_id, parts)

        class _F:                                         # the pieces put back together, named as picked
            pass
        file = _F(); file.filename = filename or "bill.xlsx"
    else:
        data = await file.read()
    if not data:
        raise HTTPException(400, "That file is empty.")
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(400, "That workbook is over 25 MB - remove pictures it does not need and upload it again.")
    try:
        model = BE.read_format(data, file.filename or "")
    except BE.BillError as e:
        raise HTTPException(400, str(e))
    chk = BE.check_against_excel(model)
    mp = model["map"]
    if not mp.get("progress"):
        raise HTTPException(400, "No lines with Previous % / Total % were found in this workbook. Upload the bill as sent to the consultant "
                                 "(the sheets with the % of work done).")
    f = EstBillFormat(project_id=project_id, name=(name or "").strip()[:120] or re.sub(r"\.xlsx?$", "", file.filename or "Bill format", flags=re.I)[:120],
                      filename=(file.filename or "")[:200], data=data, model=json.dumps(model), checked=json.dumps(chk), created_by=user.id)
    db.add(f)
    db.commit()
    E.M.log_action(db, user.id, "est_bill_format", f"project #{project_id}: bill format {f.filename} ({chk['same']}/{chk['formulas']} formulas as Excel)")
    return {"id": f.id, "formulas": chk["formulas"], "same": chk["same"], "different": chk["different"][:10],
            "lines": sum(len(t["lines"]) for t in mp["progress"]), "sheets": [t["sheet"] for t in mp["progress"]],
            "bill_no": bool(mp.get("bill_no")), "issue_date": bool(mp.get("issue_date")), "total_due": bool(mp.get("total_due")),
            "payments": bool(mp.get("payments"))}


@router.delete("/store/est/ipa/format/{fid}")
def delete_format(fid: int, db: Session = Depends(get_db), user: models.User = E.VIEW):
    f = _get(db, EstBillFormat, fid)
    n = db.query(EstBill).filter(EstBill.format_id == fid).count()
    if n and user.role != "admin":
        raise HTTPException(400, f"{n} bill(s) are made on this format - only an admin can remove it (and they go with it).")
    db.query(EstBill).filter(EstBill.format_id == fid).delete(synchronize_session=False)
    db.delete(f)
    db.commit()
    _MODEL_CACHE.pop(fid, None)
    E.M.log_action(db, user.id, "est_bill_format_removed", f"bill format #{fid} {f.filename}")
    return {"ok": True}


# ---------------------------------------------------------------------------------------------------- the bills

@router.post("/store/est/ipa/new")
def new_bill(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = E.VIEW):
    """Next month's bill: from the last bill on this format (or the format itself for the first one)."""
    pid = int(payload.get("project_id") or 0)
    E._project(db, pid)
    fid = int(payload.get("format_id") or 0)
    fmt = _get(db, EstBillFormat, fid) if fid else db.query(EstBillFormat).filter(EstBillFormat.project_id == pid).order_by(EstBillFormat.id.desc()).first()
    if not fmt or fmt.project_id != pid:
        raise HTTPException(400, "Upload the bill format for this project first.")
    model = _model(fmt)
    last = (db.query(EstBill).filter(EstBill.format_id == fmt.id).order_by(EstBill.seq.desc(), EstBill.id.desc()).first())
    prev_inputs = _inputs(last) if last else {}
    prev_values = BE.calculate(model, prev_inputs)
    inputs = BE.roll_over(model, prev_inputs, prev_values, E.today())
    inputs, values = _calc(model, inputs)
    seq = (db.query(func.max(EstBill.seq)).filter(EstBill.project_id == pid).scalar() or 0) + 1
    b = EstBill(project_id=pid, format_id=fmt.id, seq=seq, status="Draft", inputs=json.dumps(inputs), created_by=user.id, updated_by=user.id)
    _save_totals(b, model, values)
    db.add(b)
    db.commit()
    E.M.log_action(db, user.id, "est_bill_new", f"project #{pid}: bill {b.label} started")
    return {"id": b.id}


def _parse(v):
    if v is None or isinstance(v, (int, float, bool)):
        return v
    s = str(v)
    if s.startswith("="):
        BE.parse_formula(s[1:], "x")              # refused here if it cannot be read
        return s
    return s


@router.put("/store/est/ipa/bill/{bid}")
def save_bill(bid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = E.VIEW):
    """Typed cells changed: {"set": {sheet: {"r,c": value or null (back to the format's)}}, "notes": ...}."""
    b = _get(db, EstBill, bid)
    if b.status == "Paid" and user.role != "admin":
        raise HTTPException(400, "A paid bill cannot be changed.")
    fmt = _get(db, EstBillFormat, b.format_id)
    model = _model(fmt)
    inputs = _inputs(b)
    names = {s["name"]: s for s in model["sheets"]}
    for sh, cells in (payload.get("set") or {}).items():
        s = names.get(sh)
        if not s:
            raise HTTPException(400, f"No sheet called {sh}.")
        for k, v in (cells or {}).items():
            if not re.match(r"^\d+,\d+$", k):
                raise HTTPException(400, "Bad cell.")
            if not BR.editable(model, s, k, inputs):
                raise HTTPException(400, f"{sh} {k}: that figure is worked out by the sheet - change what it comes from.")
            if v is None:
                inputs.get(sh, {}).pop(k, None)
                continue
            try:
                inputs.setdefault(sh, {})[k] = _parse(v)
            except BE.BillError:
                raise HTTPException(400, f"That formula cannot be read: {v}")
    mp = model.get("map", {})
    if payload.get("issue_date") and mp.get("issue_date"):
        try:
            d = date.fromisoformat(str(payload["issue_date"])[:10])
        except ValueError:
            raise HTTPException(400, "Pick the issue date.")
        x = mp["issue_date"]
        inputs.setdefault(x["sheet"], {})[f"{x['r']},{x['c']}"] = BE.date_input(model, d)
    if payload.get("bill_no") not in (None, "") and mp.get("bill_no"):
        x = mp["bill_no"]
        v = str(payload["bill_no"]).strip()[:40]
        inputs.setdefault(x["sheet"], {})[f"{x['r']},{x['c']}"] = int(v) if v.isdigit() else v
    if "notes" in payload:
        b.notes = str(payload.get("notes") or "")[:2000]
    try:
        inputs, values = _calc(model, inputs)
    except HTTPException:
        raise
    except Exception as e:                                  # never a bare "Something went wrong": say what, keep the bill as it was
        import logging
        logging.getLogger("est_bills").exception("bill %s: could not work out", bid)
        raise HTTPException(400, f"That change could not be worked out on the consultant's sheet ({type(e).__name__}). Nothing was saved - please tell the office.")
    b.inputs = json.dumps(inputs)
    b.updated_by = user.id
    _save_totals(b, model, values)
    db.commit()
    users = {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}
    return _bill_out(b, fmt, model, values, inputs, users)


@router.post("/store/est/ipa/bill/{bid}/status")
def bill_status(bid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = E.VIEW):
    b = _get(db, EstBill, bid)
    st = str(payload.get("status") or "")
    if st not in STATUSES:
        raise HTTPException(400, "Pick a status.")
    b.status, b.updated_by = st, user.id
    db.commit()
    E.M.log_action(db, user.id, "est_bill_status", f"bill #{bid} {b.label}: {st}")
    return {"ok": True}


@router.delete("/store/est/ipa/bill/{bid}")
def delete_bill(bid: int, db: Session = Depends(get_db), user: models.User = E.VIEW):
    b = _get(db, EstBill, bid)
    if b.status != "Draft" and user.role != "admin":
        raise HTTPException(400, f"A {b.status.lower()} bill can only be removed by an admin.")
    later = db.query(EstBill).filter(EstBill.format_id == b.format_id, EstBill.seq > b.seq).count()
    if later and user.role != "admin":
        raise HTTPException(400, "A later bill was made from this one - remove the later one first.")
    db.delete(b)
    db.commit()
    E.M.log_action(db, user.id, "est_bill_removed", f"bill #{bid} {b.label}")
    return {"ok": True}


# ---------------------------------------------------------------------------------------------------- out

@router.get("/export/est/ipa/{bid}")
def export_bill(bid: int, token: str, format: str = "preview", embed: int = 0, db: Session = Depends(get_db)):
    u = auth.get_download_user_from_token(token, db)
    if E.RIGHT not in set(E.M.effective_permissions(u)) and u.role != "admin":
        raise HTTPException(403, "Estimation only.")
    b = _get(db, EstBill, bid)
    fmt = _get(db, EstBillFormat, b.format_id)
    model = _model(fmt)
    inputs = _inputs(b)
    values = BE.calculate(model, inputs)
    p = db.query(E.EstProject).get(b.project_id)
    code = p.code if p else ""
    label = b.label or str(b.seq)
    title = f"{code} - IPA {label}" + (f" - {b.issue_date:%d %b %Y}" if b.issue_date else "")
    fname = re.sub(r"[^A-Za-z0-9]+", "_", f"{code}_IPA_{label}").strip("_")
    if format == "excel":
        data = BE.write_xlsx(fmt.data, model, inputs, values)
        return StreamingResponse(io.BytesIO(data), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 headers={"Content-Disposition": f"attachment; filename={fname}.xlsx"})
    if format == "pdf":
        buf = BR.render_pdf(model, values, title, inputs, fname=fname + ".xlsx")
        return StreamingResponse(buf, media_type="application/pdf", headers={"Content-Disposition": f"inline; filename={fname}.pdf"})
    base = f"/export/est/ipa/{bid}?token={token}"
    return HTMLResponse(BR.preview_html(model, values, title, base + "&format=pdf", base + "&format=excel", inputs, embed=bool(embed), fname=fname + ".xlsx"))

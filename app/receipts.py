"""Accounts > Invoices > Receipts: money received from a client, tied to the tax invoices it pays.

A receipt is made from a tax invoice (Receive payment) or on its own. Picking the client's open tax
invoices fills the client, project and amount; what is received is set against each invoice (oldest
first by default) and anything over is kept as an advance. An invoice paid in full can carry the PAID
stamp automatically. Receipts are cancelled, never deleted, like invoices.
"""
import json
import re
from html import escape

from fastapi import Body, Depends, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Session

import auth
import main as M
import models
from database import Base, get_db
import accounts as A

router = A.router
MODES = ["Bank transfer", "Cheque", "Cash", "Card", "PDC"]


class Receipt(Base):
    __tablename__ = "receipts"
    id = Column(Integer, primary_key=True)
    number = Column(String, nullable=False, index=True)        # RC/26/914/01
    rc_date = Column(Date, nullable=False)
    company_id = Column(Integer, nullable=True)
    client = Column(String, default="")
    client_trn = Column(String, default="")
    client_address = Column(String, default="")
    project_no = Column(String, default="")
    project = Column(String, default="")
    location = Column(String, default="")
    mode = Column(String, default="Bank transfer")
    reference = Column(String, default="")      # transfer ref. / cheque no.
    bank = Column(String, default="")
    cheque_date = Column(Date, nullable=True)
    amount = Column(Float, default=0.0)
    allocations = Column(Text, default="[]")    # [{invoice_id, amount}]
    notes = Column(String, default="")
    status = Column(String, default="issued")   # issued | cancelled
    # The bank line (Accounts > Bank, Received from client) this receipt stands for - made from it
    # automatically, or matched to it. A cheque dated later counts as received on its cheque date;
    # its PAID stamp waits for that day (stamp_pending).
    bank_id = Column(Integer, nullable=True, index=True)
    stamp_pending = Column(Boolean, default=False)
    cancel_reason = Column(String, default="")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


def r2(v):
    return round(float(v or 0) + 1e-9, 2)


def _allocs(x):
    try:
        return [a for a in json.loads(x.allocations or "[]") if a.get("invoice_id")]
    except Exception:
        return []


CHEQUES = ("Cheque", "PDC")


def is_due(x, as_of=None):
    """Has the money come in? A cheque (or PDC) dated later counts only from its cheque date."""
    if x.mode in CHEQUES and x.cheque_date:
        return x.cheque_date <= (as_of or M._dubai_today())
    return True


def money_date(x):
    """The day the money counts as received: the cheque date for a cheque, else the receipt date."""
    return x.cheque_date if (x.mode in CHEQUES and x.cheque_date) else x.rc_date


def received_map(db, skip_id=None, everything=False, as_of=None):
    """invoice id -> money received on it (receipts not cancelled). A post-dated cheque counts only once its
    date has come; everything=True counts it already (what is set against an invoice, so it is not set twice)."""
    out = {}
    for x in db.query(Receipt).filter(Receipt.status != "cancelled").all():
        if skip_id and x.id == skip_id:
            continue
        if not everything and not is_due(x, as_of):
            continue
        for a in _allocs(x):
            out[int(a["invoice_id"])] = r2(out.get(int(a["invoice_id"]), 0) + float(a.get("amount") or 0))
    return out


def pending_map(db):
    """invoice id -> money on post-dated cheques not yet due."""
    out = {}
    for x in db.query(Receipt).filter(Receipt.status != "cancelled").all():
        if is_due(x):
            continue
        for a in _allocs(x):
            out[int(a["invoice_id"])] = r2(out.get(int(a["invoice_id"]), 0) + float(a.get("amount") or 0))
    return out


def _inv_row(i, got, pdc=0.0):
    return {"pdc": r2(pdc), "open": r2((i.total or 0) - got - pdc), "id": i.id, "number": i.number, "date": i.inv_date.isoformat(), "client": i.client or "", "client_trn": i.client_trn or "",
            "client_address": i.client_address or "", "project_no": i.project_no or "", "project": i.project or "", "location": i.location or "",
            "company_id": i.company_id, "total": r2(i.total), "received": r2(got), "balance": r2((i.total or 0) - got),
            "paid_stamp": bool(i.paid_stamp)}


def _dict(db, x, invs=None, users=None, banks=None):
    invs = invs if invs is not None else {}
    al = []
    for a in _allocs(x):
        i = invs.get(int(a["invoice_id"])) or db.get(A.Invoice, int(a["invoice_id"]))
        al.append({"invoice_id": int(a["invoice_id"]), "number": i.number if i else "?", "date": i.inv_date.isoformat() if i else "",
                   "total": r2(i.total) if i else 0.0, "amount": r2(a.get("amount"))})
    applied = r2(sum(a["amount"] for a in al))
    return {"id": x.id, "number": x.number, "date": x.rc_date.isoformat(), "company_id": x.company_id, "client": x.client or "",
            "client_trn": x.client_trn or "", "client_address": x.client_address or "", "project_no": x.project_no or "",
            "project": x.project or "", "location": x.location or "", "mode": x.mode or "", "reference": x.reference or "",
            "bank": x.bank or "", "cheque_date": x.cheque_date.isoformat() if x.cheque_date else "", "amount": r2(x.amount),
            "allocations": al, "applied": applied, "advance": r2((x.amount or 0) - applied), "notes": x.notes or "",
            "status": x.status, "cancel_reason": x.cancel_reason or "", "by": (users or {}).get(x.updated_by or x.created_by, ""),
            "due": is_due(x), "bank_id": x.bank_id, "bank_line": (banks or {}).get(x.bank_id)}


def next_number(db, project_no=""):
    """RC/26/914/01, RC/26/914/02 ... the receipts' own series, per project like the invoices."""
    yy = f"{M._dubai_today():%y}"
    pre = f"RC/{yy}/" + (f"{project_no.strip()}/" if project_no.strip() else "")
    best = 0
    for (n,) in db.query(Receipt.number).filter(Receipt.number.like(pre + "%")).all():
        rest = n[len(pre):]
        if not project_no.strip() and "/" in rest:
            continue
        m = re.match(r"^(\d+)$", rest)
        if m:
            best = max(best, int(m.group(1)))
    return pre + str(best + 1).zfill(2)


def _clean(db, p, keep_id=None):
    number = " ".join(str(p.get("number") or "").split())
    if not number:
        raise HTTPException(status_code=400, detail="Give the receipt a number.")
    clash = db.query(Receipt).filter(Receipt.number == number, Receipt.id != (keep_id or 0)).first()
    if clash:
        raise HTTPException(status_code=400, detail=f"{number} is already used (dated {clash.rc_date:%d %b %Y}).")
    d = M._as_date(p.get("date"))
    if not d:
        raise HTTPException(status_code=400, detail="Put the date the money was received.")
    client = " ".join(str(p.get("client") or "").split())
    if not client:
        raise HTTPException(status_code=400, detail="Who paid? Pick or type the client.")
    try:
        amount = r2(str(p.get("amount") or 0).replace(",", ""))
    except ValueError:
        raise HTTPException(status_code=400, detail="The amount is not a number.")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Type the amount received.")
    mode = str(p.get("mode") or "Bank transfer")
    if mode not in MODES:
        mode = "Bank transfer"
    got = received_map(db, skip_id=keep_id, everything=True)
    allocs, seen = [], set()
    for a in p.get("allocations") or []:
        try:
            iid, amt = int(a.get("invoice_id")), r2(str(a.get("amount") or 0).replace(",", ""))
        except (TypeError, ValueError):
            continue
        if amt <= 0 or iid in seen:
            continue
        inv = db.get(A.Invoice, iid)
        if not inv or inv.kind != "tax" or inv.status == "cancelled":
            raise HTTPException(status_code=400, detail="One of the invoices picked is not an open tax invoice any more.")
        bal = r2((inv.total or 0) - got.get(iid, 0))
        if amt > bal + 0.005:
            raise HTTPException(status_code=400, detail=f"{inv.number}: only AED {bal:,.2f} is still due on it - you set AED {amt:,.2f}.")
        seen.add(iid)
        allocs.append({"invoice_id": iid, "amount": amt})
    if r2(sum(a["amount"] for a in allocs)) > amount + 0.005:
        raise HTTPException(status_code=400, detail="The invoices take more than the amount received - lower them or raise the amount.")
    s = lambda k, n=200: " ".join(str(p.get(k) or "").split())[:n]
    return {"number": number[:60], "rc_date": d, "company_id": p.get("company_id") or None, "client": client[:200],
            "client_trn": s("client_trn", 30), "client_address": s("client_address"), "project_no": s("project_no", 30),
            "project": s("project"), "location": s("location"), "mode": mode, "reference": s("reference", 120),
            "bank": s("bank", 120), "cheque_date": M._as_date(p.get("cheque_date")) if mode in ("Cheque", "PDC") else None,
            "amount": amount, "allocations": json.dumps(allocs), "notes": s("notes", 500)}


def _stamp_paid(db, x, on_date, want):
    """Invoices this receipt pays in full get the PAID stamp (dated the day the money counts); an invoice no
    longer paid in full loses a stamp a receipt put on it. A post-dated cheque's stamp waits for its date."""
    x.stamp_pending = False
    if want and x.status != "cancelled" and not is_due(x):
        x.stamp_pending = True
        return
    on_date = money_date(x)
    got = received_map(db)
    for a in _allocs(x):
        inv = db.get(A.Invoice, int(a["invoice_id"]))
        if not inv:
            continue
        full = r2((inv.total or 0) - got.get(inv.id, 0)) <= 0.005
        if full and want and not inv.paid_stamp:
            inv.paid_stamp, inv.paid_on = True, on_date


def _unstamp_if_short(db, inv_ids, rc_date):
    """An invoice no longer paid in full loses a PAID stamp that a receipt put on it - whichever receipt it was
    (paid by two receipts, stamped on the second, the first cancelled: the stamp must go). A stamp put on by
    hand on a day no receipt is dated is the office's own word and stays."""
    got = received_map(db)
    for iid in inv_ids:
        inv = db.get(A.Invoice, iid)
        if not (inv and inv.paid_stamp) or r2((inv.total or 0) - got.get(iid, 0)) <= 0.005:
            continue
        mine = [r for r in db.query(Receipt).all() if any(int(a["invoice_id"]) == iid for a in _allocs(r))]
        dates = {rc_date} | {r.rc_date for r in mine} | {r.cheque_date for r in mine if r.cheque_date}
        if inv.paid_on in dates:
            inv.paid_stamp, inv.paid_on = False, None


def mature(db):
    """Post-dated cheques whose date has come: the PAID stamp they were waiting for goes on now."""
    due = [x for x in db.query(Receipt).filter(Receipt.stamp_pending == True, Receipt.status != "cancelled").all() if is_due(x)]  # noqa: E712
    for x in due:
        _stamp_paid(db, x, x.rc_date, True)
    if due:
        db.commit()


def _bank_lines(db):
    out = {}
    for b in db.query(models.BankEntry).filter(models.BankEntry.kind == "customer").all():
        out[b.id] = {"id": b.id, "date": b.on_date.isoformat(), "amount": r2(b.amount), "party": b.party or "",
                     "reference": b.reference or "", "zoho": b.zoho_status or ""}
    return out


@router.get("/employees/accounts/receipts")
def list_receipts(db: Session = Depends(get_db), user: models.User = A.INV):
    mature(db)
    users = {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}
    banks = _bank_lines(db)
    invs = {i.id: i for i in db.query(A.Invoice).filter(A.Invoice.kind == "tax").all()}
    rows = db.query(Receipt).order_by(Receipt.rc_date.desc(), Receipt.id.desc()).all()
    live = [r for r in rows if r.status != "cancelled"]
    got, pdc = received_map(db), pending_map(db)
    open_inv = [_inv_row(i, got.get(i.id, 0), pdc.get(i.id, 0)) for i in sorted(invs.values(), key=lambda i: (i.inv_date, i.id)) if i.status != "cancelled"]
    companies = [{"id": c.id, "name": c.name} for c in db.query(models.Company).filter(models.Company.active == True).all()]  # noqa: E712
    return {"rows": [_dict(db, r, invs, users, banks) for r in rows], "invoices": open_inv, "companies": companies, "modes": MODES,
            "clients": sorted({i.client for i in invs.values() if i.client} | {r.client for r in rows if r.client}),
            "totals": {"count": len(live), "amount": r2(sum(r.amount or 0 for r in live)),
                       "pdc": r2(sum(r.amount or 0 for r in live if not is_due(r)))},
            "next": next_number(db)}


@router.get("/employees/accounts/receipts/next")
def receipt_next(project_no: str = "", db: Session = Depends(get_db), user: models.User = A.INV):
    return {"number": next_number(db, project_no)}


@router.post("/employees/accounts/receipts")
def add_receipt(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = A.INV):
    x = Receipt(**_clean(db, payload), created_by=user.id)
    db.add(x)
    db.flush()
    _stamp_paid(db, x, x.rc_date, payload.get("stamp_paid", True))
    db.commit()
    M.log_action(db, user.id, "receipt_add", f"{x.number} {x.client}: AED {x.amount:,.2f}")
    return {"id": x.id, "number": x.number}


@router.put("/employees/accounts/receipts/{rid}")
def edit_receipt(rid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = A.INV):
    x = db.get(Receipt, rid)
    if not x:
        raise HTTPException(status_code=404, detail="That receipt is not on file.")
    if x.status == "cancelled":
        raise HTTPException(status_code=400, detail="A cancelled receipt cannot be changed.")
    before = [int(a["invoice_id"]) for a in _allocs(x)]
    old_date = x.rc_date
    for k, v in _clean(db, payload, keep_id=x.id).items():
        setattr(x, k, v)
    x.updated_by = user.id
    db.flush()
    _unstamp_if_short(db, before, old_date)
    _stamp_paid(db, x, x.rc_date, payload.get("stamp_paid", True))
    db.commit()
    M.log_action(db, user.id, "receipt_edit", f"{x.number} {x.client}: AED {x.amount:,.2f}")
    return {"ok": True}


@router.post("/employees/accounts/receipts/{rid}/cancel")
def cancel_receipt(rid: int, payload: dict = Body(default={}), db: Session = Depends(get_db), user: models.User = A.INV):
    x = db.get(Receipt, rid)
    if not x:
        raise HTTPException(status_code=404, detail="That receipt is not on file.")
    if x.status == "cancelled":
        return {"ok": True}
    x.status, x.cancel_reason, x.updated_by, x.stamp_pending = "cancelled", str(payload.get("reason") or "")[:200], user.id, False
    db.flush()
    _unstamp_if_short(db, [int(a["invoice_id"]) for a in _allocs(x)], x.rc_date)
    db.commit()
    M.log_action(db, user.id, "receipt_cancel", f"{x.number} {x.client}: AED {x.amount:,.2f}")
    return {"ok": True}


# ---- the bank line it stands for ---------------------------------------------------------------------
# Accounts > Bank, "Received from client": saving it makes the receipt here (or links one already made
# for the same money), and changing or removing it keeps the receipt in step. The receipt stays editable -
# client, project, invoices, notes are the office's; amount, date, mode and reference follow the bank line.

BANK_MODE = {"Bank Transfer": "Bank transfer", "Cheque": "Cheque", "Credit Card": "Card", "Cash": "Cash"}


def _norm_ref(v):
    return "".join(ch for ch in str(v or "").upper() if ch.isalnum()).lstrip("0")


def _bank_fields(b):
    today = M._dubai_today()
    mode = BANK_MODE.get(b.mode or "", "Bank transfer")
    if mode == "Cheque":
        later = b.on_date > today
        return {"mode": "PDC" if later else "Cheque", "rc_date": today if later else b.on_date, "cheque_date": b.on_date,
                "reference": (b.reference or "")[:120], "amount": r2(b.amount)}
    return {"mode": mode, "rc_date": b.on_date, "cheque_date": None, "reference": (b.reference or "")[:120], "amount": r2(b.amount)}


def _bank_invoices(db, b):
    """The app's tax invoices the bank line names (by number, or a held one by its id), with the amount set on each."""
    try:
        docs = json.loads(b.docs or "[]")
    except Exception:
        docs = []
    out = []
    for d in docs:
        inv = None
        if d.get("portal_id"):
            inv = db.get(A.Invoice, int(d["portal_id"]))
        if not inv and d.get("number"):
            inv = db.query(A.Invoice).filter(A.Invoice.kind == "tax", A.Invoice.number == str(d["number"]).strip()).first()
        if inv and inv.kind == "tax" and inv.status != "cancelled":
            out.append((inv, r2(d.get("amount"))))
    return out


def _fit_allocs(db, x, wanted):
    """Set the money against the invoices, never past what is still open on each nor past the amount."""
    got = received_map(db, skip_id=x.id, everything=True)
    left, allocs = r2(x.amount), []
    for inv, amt in wanted:
        a = r2(min(amt, (inv.total or 0) - got.get(inv.id, 0), left))
        if a > 0.005:
            allocs.append({"invoice_id": inv.id, "amount": a})
            got[inv.id] = r2(got.get(inv.id, 0) + a)
            left = r2(left - a)
    return allocs


def from_bank(db, b, user_id=None):
    """Keep the receipt in step with bank line b. Call after b is flushed; the caller commits."""
    linked = db.query(Receipt).filter(Receipt.bank_id == b.id).order_by(Receipt.id).all()
    live = next((r for r in linked if r.status != "cancelled"), None)
    if b.kind != "customer":
        if live:
            cancel_linked(db, b, "The bank line is no longer money received from a client.", user_id)
        return None
    if linked and not live:
        return None                      # the office cancelled its receipt on purpose - not made again
    f = _bank_fields(b)
    if not live:
        # A receipt typed in by hand for the same money: link it rather than make a second one.
        ref = _norm_ref(b.reference)
        for r in db.query(Receipt).filter(Receipt.bank_id.is_(None), Receipt.status != "cancelled").all():
            if abs(r2(r.amount) - f["amount"]) > 0.005 or abs((money_date(r) - b.on_date).days) > 15:
                continue
            if (ref and _norm_ref(r.reference) == ref) or (r.client or "").strip().lower() == (b.party or "").strip().lower():
                r.bank_id = b.id
                db.flush()
                return r
        wanted = _bank_invoices(db, b)
        inv = wanted[0][0] if wanted else None
        pno = (inv.project_no if inv else "") or ""
        if not pno and b.scope_id:
            import projectpay as pp
            sc = db.get(pp.ProjectScope, b.scope_id)
            pno = (sc.project if sc else "") or ""
        x = Receipt(number=next_number(db, pno), company_id=inv.company_id if inv else None, client=(b.party or "")[:200],
                    client_trn=(inv.client_trn if inv else "") or "", client_address=(inv.client_address if inv else "") or "",
                    project_no=pno[:30], project=(inv.project if inv else "") or "", location=(inv.location if inv else "") or "",
                    bank="ADCB" if f["mode"] != "Cash" else "", allocations="[]", notes=f"From bank line BK-{b.id}",
                    bank_id=b.id, created_by=user_id, **f)
        db.add(x)
        db.flush()
        x.allocations = json.dumps(_fit_allocs(db, x, wanted))
        db.flush()
        _stamp_paid(db, x, x.rc_date, True)
        db.flush()
        return x
    # Linked already: the money facts follow the bank line.
    before = [int(a["invoice_id"]) for a in _allocs(live)]
    old_date = live.rc_date
    changed = any(getattr(live, k) != v for k, v in f.items() if k != "rc_date") or (live.mode in CHEQUES and live.rc_date != f["rc_date"] and f["mode"] == "Cheque")
    if not changed and abs(r2(live.amount) - f["amount"]) <= 0.005:
        return live
    for k, v in f.items():
        if k == "rc_date" and live.mode == "PDC" and f["mode"] == "PDC":
            continue                     # still post-dated: the day it was received stays
        setattr(live, k, v)
    live.updated_by = user_id
    al, left = [], r2(live.amount)
    for a in _allocs(live):              # the invoices stay; trimmed only if the amount went down
        amt = r2(min(float(a.get("amount") or 0), left))
        if amt > 0.005:
            al.append({"invoice_id": int(a["invoice_id"]), "amount": amt})
            left = r2(left - amt)
    live.allocations = json.dumps(al)
    db.flush()
    _unstamp_if_short(db, before, old_date)
    _stamp_paid(db, live, live.rc_date, True)
    db.flush()
    return live


def cancel_linked(db, b, reason, user_id=None, unlink=False):
    """The bank line is no longer a client's payment (or is removed): its receipt is cancelled. Removed, the link
    goes too (the receipt's notes keep which line it was), so a new line never picks up an old receipt."""
    for x in db.query(Receipt).filter(Receipt.bank_id == b.id).all():
        if x.status != "cancelled":
            x.status, x.cancel_reason, x.updated_by, x.stamp_pending = "cancelled", reason[:200], user_id, False
            db.flush()
            _unstamp_if_short(db, [int(a["invoice_id"]) for a in _allocs(x)], x.rc_date)
        if unlink:
            x.bank_id = None
            if f"BK-{b.id}" not in (x.notes or ""):
                x.notes = ((x.notes or "") + f" (bank line BK-{b.id} removed)").strip()[:500]
    db.flush()


def backfill(db):
    """Once: a receipt for every client's payment already on Bank that has none."""
    for b in db.query(models.BankEntry).filter(models.BankEntry.kind == "customer").order_by(models.BankEntry.on_date, models.BankEntry.id).all():
        if not db.query(Receipt).filter(Receipt.bank_id == b.id).first():
            from_bank(db, b, b.created_by)
    db.commit()


def _pdf(db, x):
    import receipt_pdf
    d = _dict(db, x)
    got = received_map(db)
    # balance left on each invoice as at this receipt: invoice total - everything received on it
    # by receipts up to and including this one
    upto = {}
    for r in db.query(Receipt).filter(Receipt.status != "cancelled").order_by(Receipt.rc_date, Receipt.id).all():
        for a in _allocs(r):
            upto.setdefault(int(a["invoice_id"]), []).append((r.rc_date, r.id, float(a.get("amount") or 0)))
    for a in d["allocations"]:
        paid = sum(v for dt, i, v in upto.get(a["invoice_id"], []) if (dt, i) <= (x.rc_date, x.id)) if x.status != "cancelled" else got.get(a["invoice_id"], 0) + a["amount"]
        a["balance"] = r2(a["total"] - paid)
        a["date_text"] = M._as_date(a["date"]).strftime("%d %b %Y") if a["date"] else ""
    d["date_text"] = f"{x.rc_date:%d %B %Y}"
    d["cheque_date_text"] = f"{x.cheque_date:%d %b %Y}" if x.cheque_date else ""
    return receipt_pdf.build(d, company=A._company(db, x.company_id), signature=A.invoice_signature())


@router.get("/export/accounts/receipt/{rid}")
def export_receipt(rid: int, token: str, db: Session = Depends(get_db)):
    u = auth.get_download_user_from_token(token, db)
    if A.INV_RIGHT not in M.effective_permissions(u):
        raise HTTPException(status_code=403, detail="Receipts are for accounts only.")
    x = db.get(Receipt, rid)
    if not x:
        raise HTTPException(status_code=404, detail="That receipt is not on file.")
    name = "Receipt_" + x.number.replace("/", "-")
    return StreamingResponse(_pdf(db, x), media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}.pdf"'})


@router.get("/export/accounts/receipt/{rid}/view")
def view_receipt(rid: int, token: str, db: Session = Depends(get_db)):
    from urllib.parse import quote
    import export_web
    u = auth.get_download_user_from_token(token, db)
    if A.INV_RIGHT not in M.effective_permissions(u):
        raise HTTPException(status_code=403, detail="Receipts are for accounts only.")
    x = db.get(Receipt, rid)
    if not x:
        raise HTTPException(status_code=404, detail="That receipt is not on file.")
    t = quote(auth.create_view_token(u.username), safe="")
    pdf = f"/export/accounts/receipt/{rid}?token={t}"
    title = "Payment Receipt " + x.number
    sub = f"{x.client} - AED {x.amount or 0:,.2f}"
    return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8"><title>{escape(title)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{export_web.PREVIEW_BAR_CSS}
  body {{ margin:0; background:#F1EFEA; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }}
  .doc {{ width:min(210mm, calc(100% - 24px)); height:calc(100vh - 90px); margin:12px auto; background:white; box-shadow:0 1px 6px rgba(0,0,0,.14); }}
  .doc iframe {{ width:100%; height:100%; border:0; }}
  .phone {{ display:none; text-align:center; color:#666; font-size:14px; padding:30px 16px; }}
  @media (max-width: 700px) {{ .doc {{ display:none; }} .phone {{ display:block; }} }}
</style></head><body>
<div class="pvbar"><h1>{escape(title)}</h1><span class="who">{escape(sub)}</span><span class="sp"></span>
  <a class="btn dark" href="{escape(pdf)}" target="_blank">Download PDF</a>
  <a class="btn" href="{escape(pdf)}" target="_blank">Print</a>
  {export_web.share_button(pdf, title)}</div>
{export_web.SHARE_JS}
<div class="doc"><iframe src="{escape(pdf)}#view=FitH" title="{escape(title)}"></iframe></div>
<div class="phone">Tap <b>Share</b> to send it on WhatsApp or mail, or <b>Download PDF</b> to open it.</div>
</body></html>""")

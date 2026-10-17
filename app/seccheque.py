"""Expiry Reminder > Security cheques.

Cheques the company leaves with others as a guarantee - a client, a
landlord, an authority, a supplier - usually undated. Nothing is due on
them; the risk is forgetting they are out there. So each one can carry a
"collect it back after" date: a week before it the bell reminds, and on
the day and every day after, until it is marked collected back.

Who: the security_cheques right - admin, the PRO and the chief
accountant (given once at start-up, then ticked on Settings > Access).
"""
from datetime import date, datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import Column, Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Session

import main as M
import models, auth
from database import Base, get_db

RIGHT = "security_cheques"
router = APIRouter()
SC = Depends(M.require_screen(RIGHT))
STATUSES = {"held": "With them", "returned": "Collected back", "encashed": "Encashed", "cancelled": "Cancelled"}
PURPOSES = ["Tender / bid bond", "Performance guarantee", "Advance payment guarantee", "Tenancy / rent",
            "Authority / permit", "Supplier credit", "Other"]
REMIND_BEFORE = 7


class SecurityCheque(Base):
    __tablename__ = "security_cheques"
    id = Column(Integer, primary_key=True)
    party = Column(String, nullable=False)         # given to
    kind = Column(String, default="cheque")        # cheque | deposit (paid, refundable)
    purpose = Column(String, default="")
    project = Column(String, default="")
    bank = Column(String, default="")
    cheque_no = Column(String, default="")
    amount = Column(Float, default=0.0)
    cheque_date = Column(Date, nullable=True)       # usually undated
    given_on = Column(Date, nullable=True)
    remind_on = Column(Date, nullable=True)         # collect it back after
    status = Column(String, default="held")
    returned_on = Column(Date, nullable=True)
    notes = Column(Text, default="")
    created_by = Column(Integer, nullable=True)
    updated_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def _row(x, today):
    left = (x.remind_on - today).days if (x.remind_on and x.status == "held") else None
    return {"id": x.id, "kind": x.kind or "cheque", "party": x.party, "purpose": x.purpose or "", "project": x.project or "",
            "bank": x.bank or "", "cheque_no": x.cheque_no or "", "amount": round(x.amount or 0, 2),
            "cheque_date": x.cheque_date.isoformat() if x.cheque_date else "",
            "given_on": x.given_on.isoformat() if x.given_on else "",
            "remind_on": x.remind_on.isoformat() if x.remind_on else "",
            "status": x.status or "held", "status_label": STATUSES.get(x.status or "held", x.status),
            "returned_on": x.returned_on.isoformat() if x.returned_on else "",
            "notes": x.notes or "", "days_left": left}


def summary(db, today=None):
    today = today or M._dubai_today()
    held = db.query(SecurityCheque).filter(SecurityCheque.status == "held").all()
    due = [x for x in held if x.remind_on and x.remind_on <= today]
    soon = [x for x in held if x.remind_on and today < x.remind_on <= today + timedelta(days=30)]
    week = [x for x in held if x.remind_on and today < x.remind_on <= today + timedelta(days=REMIND_BEFORE)]
    s = lambda xs: round(sum(x.amount or 0 for x in xs), 2)
    return {"held": len(held), "held_amount": s(held), "due": len(due), "due_amount": s(due),
            "soon": len(soon), "soon_amount": s(soon), "week": len(week),
            "no_reminder": sum(1 for x in held if not x.remind_on),
            "first": sorted(due + week, key=lambda x: x.remind_on)}


@router.get("/employees/security-cheques")
def list_cheques(db: Session = Depends(get_db), user: models.User = SC):
    today = M._dubai_today()
    rows = db.query(SecurityCheque).all()
    rows.sort(key=lambda x: (x.status != "held", x.remind_on or date(9999, 1, 1), (x.party or "").lower()))
    sm = summary(db, today)
    sm.pop("first")
    return {"rows": [_row(x, today) for x in rows], "summary": sm, "purposes": PURPOSES, "statuses": STATUSES}


def _num(v):
    try:
        return round(float(str(v or 0).replace(",", "")), 2)
    except ValueError:
        raise HTTPException(status_code=400, detail="The amount must be a number.")


def _clean(p):
    party = (p.get("party") or "").strip()
    if not party:
        raise HTTPException(status_code=400, detail="Who is the cheque with?")
    amt = _num(p.get("amount"))
    if amt <= 0:
        raise HTTPException(status_code=400, detail="Enter the cheque amount.")
    st = p.get("status") if p.get("status") in STATUSES else "held"
    out = {"kind": "deposit" if p.get("kind") == "deposit" else "cheque", "party": party[:120], "purpose": (p.get("purpose") or "").strip()[:80], "project": (p.get("project") or "").strip()[:80],
           "bank": (p.get("bank") or "").strip()[:60], "cheque_no": (p.get("cheque_no") or "").strip()[:30], "amount": amt,
           "cheque_date": None if (p.get("undated") or p.get("kind") == "deposit") else M._as_date(p.get("cheque_date")),
           "given_on": M._as_date(p.get("given_on")) or M._dubai_today(),
           "remind_on": M._as_date(p.get("remind_on")), "status": st,
           "notes": (p.get("notes") or "").strip()[:500]}
    out["returned_on"] = (M._as_date(p.get("returned_on")) or M._dubai_today()) if st != "held" else None
    return out


def _what(x):
    return f"{x.party} - {x.bank} {x.cheque_no} AED {x.amount or 0:,.2f}".replace("  ", " ")


@router.post("/employees/security-cheques")
def add_cheque(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = SC):
    x = SecurityCheque(**_clean(payload), created_by=user.id, updated_by=user.id)
    db.add(x); db.commit()
    M.log_action(db, user.id, "seccheque_added", _what(x))
    return _row(x, M._dubai_today())


@router.put("/employees/security-cheques/{cid}")
def edit_cheque(cid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = SC):
    x = db.get(SecurityCheque, cid)
    if not x:
        raise HTTPException(status_code=404, detail="That cheque is no longer on file.")
    was = (round(x.amount or 0, 2), x.status, x.remind_on)
    for k, v in _clean(payload).items():
        setattr(x, k, v)
    x.updated_by = user.id
    db.commit()
    bits = []
    if was[0] != round(x.amount or 0, 2):
        bits.append(f"amount {was[0]:,.2f} -> {x.amount:,.2f}")
    if was[1] != x.status:
        bits.append(f"{STATUSES.get(was[1], was[1])} -> {STATUSES.get(x.status, x.status)}")
    if was[2] != x.remind_on:
        bits.append(f"reminder {was[2] or 'none'} -> {x.remind_on or 'none'}")
    M.log_action(db, user.id, "seccheque_changed", _what(x) + (": " + ", ".join(bits) if bits else ""))
    return _row(x, M._dubai_today())


@router.post("/employees/security-cheques/{cid}/returned")
def mark_returned(cid: int, db: Session = Depends(get_db), user: models.User = SC):
    x = db.get(SecurityCheque, cid)
    if not x:
        raise HTTPException(status_code=404, detail="That cheque is no longer on file.")
    x.status, x.returned_on, x.updated_by = "returned", M._dubai_today(), user.id
    db.commit()
    M.log_action(db, user.id, "seccheque_returned", _what(x))
    return _row(x, M._dubai_today())


@router.delete("/employees/security-cheques/{cid}")
def delete_cheque(cid: int, db: Session = Depends(get_db), user: models.User = SC):
    x = db.get(SecurityCheque, cid)
    if not x:
        raise HTTPException(status_code=404, detail="That cheque is no longer on file.")
    what = _what(x)
    db.delete(x); db.commit()
    M.log_action(db, user.id, "seccheque_deleted", what)
    return {"ok": True}


# ---- the register on paper ------------------------------------------------------------

MONEY = ["Amount"]


def _parts(db, show="held", q=""):
    today = M._dubai_today()
    rows = db.query(SecurityCheque).all()
    if show != "all":
        rows = [x for x in rows if x.status == "held"]
    # The screen's search box narrows the paper too.
    q = (q or "").strip()
    if q:
        rows = [x for x in rows if q.lower() in " ".join(v or "" for v in (x.party, x.purpose, x.project, x.bank,
                                                                         x.cheque_no, x.notes)).lower()]
    rows.sort(key=lambda x: (x.status != "held", x.remind_on or date(9999, 1, 1), (x.party or "").lower()))
    d = lambda v: f"{v:%d %b %Y}" if v else "-"
    out = []
    for i, x in enumerate(rows, 1):
        r = {"Sr.": i, "Type": "Deposit" if x.kind == "deposit" else "Cheque", "Given to": x.party, "Purpose": x.purpose or "-", "Project": x.project or "-",
             "Bank": x.bank or "-", "Cheque no": x.cheque_no or "-", "Amount": round(x.amount or 0, 2),
             "Cheque date": "-" if x.kind == "deposit" else (d(x.cheque_date) if x.cheque_date else "Undated"), "Given on": d(x.given_on),
             "Collect back after": d(x.remind_on), "Status": STATUSES.get(x.status, x.status)}
        if show == "all":
            r["Collected on"] = d(x.returned_on)
        out.append(r)
    total = sum(r["Amount"] for r in out)
    sub = (f"{len(out)} cheque{'s' if len(out) != 1 else ''} / deposit{'s' if len(out) != 1 else ''} {'still with others' if show != 'all' else 'in all'}"
           + (f'   |   matching "{q}"' if q else "") + f"   |   AED {total:,.2f}   |   As at {today:%d %b %Y}")
    return out, "Security Cheques & Deposits", sub


def _reader(token, db):
    u = auth.get_download_user_from_token(token, db)
    if RIGHT not in M.effective_permissions(u):
        raise HTTPException(status_code=403, detail="Not available to this login: Security cheques.")
    return u


@router.get("/export/security-cheques")
def export_cheques(token: str, format: str = "pdf", show: str = "held", q: str = "", db: Session = Depends(get_db)):
    _reader(token, db)
    rows, title, sub = _parts(db, show, q)
    return M._hr_file(title, rows, sub, format, MONEY, "Security_Cheques", totals=MONEY)


@router.get("/export/security-cheques/view")
def view_cheques(token: str, show: str = "held", q: str = "", db: Session = Depends(get_db)):
    u = _reader(token, db)
    t = quote(auth.create_view_token(u.username), safe="")
    rows, title, sub = _parts(db, show, q)
    url = f"/export/security-cheques?token={t}&show={quote(show)}&q={quote(q)}"
    return M._preview_page(title, sub, rows, url, url, money_cols=MONEY, total_cols=MONEY)


# ---- the bell -------------------------------------------------------------------------

def notification(db, today):
    """For logins with the right (the caller checks): a week before the
    collect-back date, on it and every day after while still not back."""
    s = summary(db, today)
    if not (s["due"] or s["week"]):
        return None
    bits = [f"{s['due']} due to collect back" if s["due"] else "", f"{s['week']} within 7 days" if s["week"] else ""]
    first = ", ".join(f"{x.party} AED {x.amount or 0:,.0f} ({x.remind_on:%d %b})" for x in s["first"][:3])
    more = len(s["first"]) - 3
    return {"id": f"secchq-{today}", "kind": "seccheque", "title": "Security cheques: " + ", ".join(b for b in bits if b),
            "detail": first + (f" and {more} more" if more > 0 else ""), "screen": "seccheque",
            "lines": [f"{x.remind_on:%d %b}  ·  AED {x.amount or 0:,.2f}  ·  {__import__('push').short_name(x.party)}" for x in s["first"]],
            "when": today.isoformat(), "count": s["due"] + s["week"], "level": "warn" if s["due"] else "info"}


def grant_once(db):
    """The PRO and the chief accountant roles (and their logins) get the
    tab, once. After that it is ticked on Settings > Access like any other."""
    if db.query(models.Setting).filter(models.Setting.key == "seccheque_granted").first():
        return
    try:
        import tabrights
        leaf = "expiry.expiry.security" if tabrights.is_leaf("expiry.expiry.security") else None
    except Exception:
        leaf = None
    names = []
    for r in db.query(models.AccessRole).all():
        if (r.name or "").strip().lower() not in ("pro", "chief accountant"):
            continue
        keys = [k for k in (r.screens or "").split(",") if k]
        add = [RIGHT] + ([leaf] if leaf and any("." in k for k in keys) else [])
        r.screens = ",".join(keys + [a for a in add if a not in keys])
        names.append(r.name)
        for u in db.query(models.User).filter(models.User.access_role_id == r.id).all():
            uk = [k for k in (u.permissions or "").split(",") if k]
            add = [RIGHT] + ([leaf] if leaf and any("." in k for k in uk) else [])
            u.permissions = ",".join(uk + [a for a in add if a not in uk])
    db.add(models.Setting(key="seccheque_granted", value="1"))
    db.commit()
    if names:
        print("Security cheques given to: " + ", ".join(names))

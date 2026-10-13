"""Send to Zoho - Accounts > Send to Zoho.

Petty cash is typed once, in the portal. The chief accountant sees every
line not yet in Zoho, checks the Zoho account the portal suggests (from
how the same supplier or kind of bill went before), and approves. An
approved line goes to Zoho once; it is never typed there again.

The accounts offered are the company's cost heads, as on the Project
Cost Centre (01. Preliminaries ... 21. Specialized & Other Items, with
their sub-heads), plus the office running costs and, for cash coming
in, where it came from. They can be changed later without touching a
line already approved.

Status of a line (petty_cash.zoho_status):
  ""        waiting for the chief accountant
  approved  approved, going to Zoho
  sent      in Zoho (zoho_ref holds the Zoho number)
  changed   edited after it went to Zoho - change it there too
  inzoho    was already typed in Zoho before the portal sent anything
  skip      not for Zoho (reason in zoho_ref)
"""
import re
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

import main as M
import models, auth, export_web
from database import get_db

router = APIRouter()
RIGHT = "accounts_zoho"
ZG = Depends(M.require_any_screen(RIGHT))
BOOKS = {"site": "Site", "pro": "PRO", "office": "Office", "naveen": "Naveen", "praveen": "Praveen"}
START_DEFAULT = "2026-10-01"

# ---- The accounts on offer ------------------------------------------------
# Project cost heads, as the Project Cost Centre lists them.
PROJECT_HEADS = [
    ("01. Preliminaries Including Mobilization", ["Authority Payments", "Service Charges for Property",
                                                  "Soil Investigation and Other Surveys"]),
    ("Design & Supervision Fee", []),
    ("Villa Interior & Landscape Design", []),
    ("Land Purchase", []),
    ("Agent Commission and Key Money", []),
    ("02. Substructure", ["2a. Earthworks", "2b. Piling & Shoring Works", "2c. Dewatering Works", "2d. Blinding Works",
                          "2e. Reinforced Concrete (SRC)", "2f. Steel Reinforcement", "2g. Substructure Waterproofing",
                          "2h. Underground Water Tank"]),
    ("03. Swimming Pool & Holding Tank", []),
    ("04. Superstructure", ["4a. Reinforced Concrete", "4b. Steel Reinforcement"]),
    ("05. Blockworks", []),
    ("06. Roof Waterproofing and Finishing", []),
    ("07. Plastering Works", []),
    ("08. Carpentry & Joinery", []),
    ("09. Metal, Aluminium & Glass Works", []),
    ("10. Painting Works & False Ceiling", []),
    ("11. Electrical, Low Current & LPG Works", []),
    ("12. Plumbing Works", []),
    ("13. Fire Fighting & Fire Alarm Works", []),
    ("14. Drainage Works", []),
    ("15. A/C Works", []),
    ("16. Lift & Elevators", []),
    ("17. Floors & Wall Tiles (Internal)", ["17a. Ceramic Tiles", "17b. Terrazzo Tiles", "17c. Marble Works"]),
    ("18. External Finishes", []),
    ("19. External Works", []),
    ("20. Boundary Wall", []),
    ("21. Specialized & Other Items", []),
]
# Office running costs - the accounts Zoho already uses for them.
OFFICE = ["Office Pantry Expenses", "Office Cleaning Expenses", "Office Supplies", "Staff Meals and Benefits",
          "Employee Benefit Expense", "Visa Expenses", "Legal, Licence & Professional Expense", "Fines and Penalties",
          "Salik Fee", "Parking Fees and Fines", "Automobile Expense", "Vehicle Repair and Maintenance Expenses",
          "Telephone Expenses", "Software Expenses", "Electricity & Water Charges", "Ads & Marketing Expenses",
          "Business Promotion", "Villa Care Taker Expenses", "Miscellaneous Expense"]
# Money that is not an expense: advances, and cash moving between boxes.
MOVES = ["Employee Advance (salary advance / loan)", "Transfer to Company Petty Cash", "Transfer to Jomon Petty Cash",
         "Transfer to Site Petty Cash"]
# Where cash coming in came from.
SOURCES = ["From ADCB (transfer / cheque cashed)", "From Cash", "From Company Petty Cash", "From Jomon Petty Cash",
           "From Site Petty Cash", "From Current Capital - Praveen", "From Current Capital - Naveen",
           "Client payment received in cash", "Staff advance / loan repaid"]


def _groups():
    proj = []
    for h, subs in PROJECT_HEADS:
        proj.append(h)
        proj += [f"{h} › {s}" for s in subs]
    return [{"group": "Project cost heads", "project": True, "accounts": proj},
            {"group": "Office & running costs", "project": False, "accounts": [f"Office › {a}" for a in OFFICE]},
            {"group": "Advances & transfers (paid out)", "project": False, "accounts": MOVES},
            {"group": "Cash received - from", "project": False, "accounts": SOURCES, "received": True}]


GROUPS = _groups()
PROJECT_ACCOUNTS = set(GROUPS[0]["accounts"])
PAID_ACCOUNTS = set(GROUPS[0]["accounts"] + GROUPS[1]["accounts"] + GROUPS[2]["accounts"])
RECEIVED_ACCOUNTS = set(SOURCES)
P01 = PROJECT_HEADS[0][0]

# ---- The suggestion -------------------------------------------------------
_RULES_SITE = [
    (r"\bdm\b|municipal|\brta\b|dewa|\bnoc\b|permit|mohre|gdrfa|\bdda\b|\bdld\b|trakhees|\bdcd\b|demarcation|approval fee|submission fee",
     f"{P01} › Authority Payments"),
    (r"service charge", f"{P01} › Service Charges for Property"),
    (r"soil|survey", f"{P01} › Soil Investigation and Other Surveys"),
    (r"tile|grout|adhesive|levell?ing|marble", "17. Floors & Wall Tiles (Internal)"),
    (r"paint|silicone|putty|gypsum|false ceiling", "10. Painting Works & False Ceiling"),
    (r"\bblock", "05. Blockworks"),
    (r"plaster", "07. Plastering Works"),
    (r"waterproof|membrane|bitumen", "06. Roof Waterproofing and Finishing"),
    (r"pipe|plumb|sanitary|ppr|upvc|valve", "12. Plumbing Works"),
    (r"cable|electric|switch|socket|conduit|\blight", "11. Electrical, Low Current & LPG Works"),
    (r"glass|alumin", "09. Metal, Aluminium & Glass Works"),
    (r"door|joinery|carpent", "08. Carpentry & Joinery"),
    (r"pool", "03. Swimming Pool & Holding Tank"),
    (r"drain|manhole", "14. Drainage Works"),
    (r"\ba/?c\b|duct", "15. A/C Works"),
]
_RULES_OFFICE = [
    (r"visa|emirates id|medical fitness|labour card|mohre|gdrfa|quota|amer|tasheel", "Office › Visa Expenses"),
    (r"fine|penalt", "Office › Fines and Penalties"),
    (r"salik|darb", "Office › Salik Fee"),
    (r"parkin|parking", "Office › Parking Fees and Fines"),
    (r"pantry|water|tea|coffee|sugar|grocery|refreshment", "Office › Office Pantry Expenses"),
    (r"clean|mop|detergent|toilet", "Office › Office Cleaning Expenses"),
    (r"lunch|food|meal|cake|birthday", "Office › Staff Meals and Benefits"),
    (r"hospital|clinic|medical|medicine|nmc|aster", "Office › Employee Benefit Expense"),
    (r"etisalat|\bdu\b|recharge|telephone|mobile", "Office › Telephone Expenses"),
    (r"software|subscription|licen[cs]e fee|d5", "Office › Software Expenses"),
    (r"stationer|printer|toner|air fresh|office suppl", "Office › Office Supplies"),
    (r"advt|advert|dubizzle|marketing", "Office › Ads & Marketing Expenses"),
    (r"registration renewal|rta|vehicle|tyre|battery|car wash|garage", "Office › Vehicle Repair and Maintenance Expenses"),
    (r"care ?taker", "Office › Villa Care Taker Expenses"),
    (r"trade licen|chamber|legal|attorney|notar", "Office › Legal, Licence & Professional Expense"),
]
_RULES_MOVE = [
    (r"salary advance|advance|loan", "Employee Advance (salary advance / loan)"),
    (r"company cash ?book|office petty|to shaf", "Transfer to Company Petty Cash"),
    (r"jomon|pro petty", "Transfer to Jomon Petty Cash"),
]
_RULES_SOURCE = [
    (r"jomon|pro petty", "From Jomon Petty Cash"),
    (r"site petty", "From Site Petty Cash"),
    (r"company petty|office petty|shaf", "From Company Petty Cash"),
    (r"praveen", "From Current Capital - Praveen"),
    (r"naveen", "From Current Capital - Naveen"),
    (r"emkaan|client|customer", "Client payment received in cash"),
    (r"loan|salary|recover|reimburs", "Staff advance / loan repaid"),
    (r"adcb|bank|transfer|cheque", "From ADCB (transfer / cheque cashed)"),
    (r"cash", "From Cash"),
]


def _match(rules, text):
    for pat, acc in rules:
        if re.search(pat, text, re.I):
            return acc
    return ""


def suggest(x, learned):
    """The account most likely right for this line: how the same supplier
    (or the same description) in the same book was approved before, else
    what the words on it say."""
    text = f"{x.description or ''} {x.supplier or ''}"
    key = (x.book or "site", M._supplier_key(x.supplier or ""), bool(x.received))
    dkey = (x.book or "site", (x.description or "").strip().lower(), bool(x.received))
    if dkey in learned:
        return learned[dkey]
    if key[1] and key in learned:
        return learned[key]
    if x.received:
        return _match(_RULES_SOURCE, text)
    move = _match(_RULES_MOVE, text)
    if move:
        return move
    if x.site or (x.book or "site") == "site":
        # The site box spends on projects; a line with no site is asked
        # for its project on the approval screen.
        return _match(_RULES_SITE, text) or P01
    return _match(_RULES_OFFICE, text)


def _learned(db):
    out = {}
    for x in (db.query(models.PettyCash).filter(models.PettyCash.zoho_account != "", models.PettyCash.zoho_account.isnot(None))
                .order_by(models.PettyCash.approved_at)):
        b = x.book or "site"
        if M._supplier_key(x.supplier or ""):
            out[(b, M._supplier_key(x.supplier or ""), bool(x.received))] = x.zoho_account
        out[(b, (x.description or "").strip().lower(), bool(x.received))] = x.zoho_account
    return out


def _start(db):
    return M._as_date(M.get_setting(db, "zoho_start") or START_DEFAULT)


def _flags(x, account):
    """What must be put right before the line can go."""
    out = []
    if not account:
        out.append("Pick account")
    elif x.received and account not in RECEIVED_ACCOUNTS:
        out.append("Pick where it came from")
    elif not x.received and account not in PAID_ACCOUNTS:
        out.append("Pick account")
    if account in PROJECT_ACCOUNTS and not (x.site or "").strip():
        out.append("Pick project")
    if x.vat and not (x.trn or "").strip():
        out.append("VAT without TRN")
    return out


def _waiting(db):
    q = (db.query(models.PettyCash)
           .filter(models.PettyCash.book.in_(list(BOOKS)), models.PettyCash.on_date >= _start(db))
           .filter((models.PettyCash.zoho_status == "") | (models.PettyCash.zoho_status.is_(None)) | (models.PettyCash.zoho_status == "changed"))
           .order_by(models.PettyCash.on_date, models.PettyCash.id))
    return q.all()


def _row(x, learned, users):
    acc = x.zoho_account if x.zoho_status == "changed" and x.zoho_account else suggest(x, learned)
    return {"id": x.id, "book": x.book or "site", "book_label": BOOKS.get(x.book or "site", x.book), "date": x.on_date.isoformat(),
            "description": x.description or "", "supplier": x.supplier or "", "site": x.site or "",
            "amount": round((x.paid or 0) or (x.received or 0), 2), "kind": "received" if x.received else "paid",
            "vat": bool(x.vat), "trn": x.trn or "", "account": acc, "flags": _flags(x, acc),
            "changed": x.zoho_status == "changed", "zoho_ref": x.zoho_ref or "",
            "by": users.get(x.updated_by or x.created_by, "")}


@router.get("/store/zoho/heads")
def heads(user: models.User = ZG):
    return {"groups": GROUPS}


@router.get("/store/zoho/queue")
def queue(db: Session = Depends(get_db), user: models.User = ZG):
    import zohoapi
    try:
        zohoapi.check_deleted(db)
    except Exception:
        db.rollback()
    learned = _learned(db)
    users = {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}
    rows = [_row(x, learned, users) for x in _waiting(db)]
    month_start = M._dubai_today().replace(day=1)
    sent = (db.query(models.PettyCash).filter(models.PettyCash.zoho_status.in_(["approved", "sent"]),
                                              models.PettyCash.approved_at.isnot(None)).all())
    sent_month = [x for x in sent if x.approved_at and x.approved_at.date() >= month_start]
    pend = (db.query(models.PettyCash).filter(models.PettyCash.zoho_status.in_(["approved", "cancelled"]))
              .order_by(models.PettyCash.on_date, models.PettyCash.id).all())
    pending = [{"id": x.id, "book_label": BOOKS.get(x.book or "site", x.book), "date": x.on_date.isoformat(),
                "description": x.description or "", "amount": round((x.paid or 0) or (x.received or 0), 2),
                "account": x.zoho_account or "", "status": x.zoho_status, "err": x.zoho_err or ""} for x in pend]
    return {"rows": rows, "groups": GROUPS, "start": _start(db).isoformat(), "pending": pending,
            "connected": zohoapi.connected(db),
            "waiting": len(rows), "waiting_total": round(sum(r["amount"] for r in rows), 2),
            "to_fix": sum(1 for r in rows if r["flags"]),
            "sent_month": len(sent_month)}


@router.post("/store/zoho/approve")
def approve(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = ZG):
    """Approve the ticked lines, each with the account chosen for it (and
    the project, where the chief accountant filled one in). A line still
    needing something is refused, the rest go."""
    lines = payload.get("lines") or []
    if not lines:
        raise HTTPException(status_code=400, detail="Tick the lines to send.")
    now = datetime.now(timezone.utc)
    done, refused = [], []
    for ln in lines:
        x = db.get(models.PettyCash, int(ln.get("id") or 0))
        if not x or (x.zoho_status or "") not in ("", "changed"):
            continue
        if "site" in ln and str(ln.get("site") or "").strip() and not (x.site or "").strip():
            x.site = str(ln["site"]).strip()[:40]
        t = "".join(ch for ch in str(ln.get("trn") or "") if ch.isdigit())
        if x.vat and not (x.trn or "").strip() and len(t) == 15:
            x.trn = t
        acc = str(ln.get("account") or "").strip()
        f = _flags(x, acc)
        if f:
            refused.append({"id": x.id, "why": ", ".join(f)})
            continue
        x.zoho_account = acc
        x.zoho_status = "approved"
        x.approved_by, x.approved_at = user.id, now
        done.append(x)
    db.commit()
    if done:
        M.log_action(db, user.id, "zoho_approve",
                     f"{len(done)} petty cash line(s) approved for Zoho, AED {sum((x.paid or 0) + (x.received or 0) for x in done):,.2f}")
    sent, failed = 0, []
    import zohoapi
    if done and zohoapi.connected(db):
        sent, failed = zohoapi.push_many(db, done, user)
    return {"ok": True, "approved": len(done), "refused": refused, "sent": sent, "failed": failed,
            "connected": zohoapi.connected(db)}


@router.post("/store/zoho/retry")
def retry(payload: dict = Body(default={}), db: Session = Depends(get_db), user: models.User = ZG):
    """Send again the approved lines Zoho has not taken yet."""
    import zohoapi
    if not zohoapi.connected(db):
        raise HTTPException(status_code=400, detail="Zoho is not connected yet - press Connect Zoho.")
    ids = [int(i) for i in (payload.get("ids") or [])]
    q = db.query(models.PettyCash).filter(models.PettyCash.zoho_status == "approved")
    rows = [x for x in q.all() if not ids or x.id in ids]
    sent, failed = zohoapi.push_many(db, rows, user)
    return {"ok": True, "sent": sent, "failed": failed}


@router.post("/store/zoho/skip")
def skip(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = ZG):
    """Not for Zoho - e.g. Prime Infinia's, or the receiving side of a
    transfer already sent from the paying book. The reason is kept."""
    why = str(payload.get("reason") or "").strip()
    if not why:
        raise HTTPException(status_code=400, detail="Say why it is not for Zoho.")
    n = 0
    for i in payload.get("ids") or []:
        x = db.get(models.PettyCash, int(i))
        if x and (x.zoho_status or "") in ("", "changed"):
            x.zoho_status, x.zoho_ref = "skip", why[:200]
            n += 1
    db.commit()
    if n:
        M.log_action(db, user.id, "zoho_skip", f"{n} petty cash line(s) marked not for Zoho: {why[:120]}")
    return {"ok": True, "skipped": n}


@router.post("/store/zoho/mark")
def mark(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = ZG):
    """Record what happened in Zoho: sent (with its Zoho number), already
    in Zoho, or back to waiting."""
    st = str(payload.get("status") or "").strip()
    if st not in ("sent", "inzoho", ""):
        raise HTTPException(status_code=400, detail="Status is sent, inzoho or empty.")
    n = 0
    for i in payload.get("ids") or []:
        x = db.get(models.PettyCash, int(i))
        if not x:
            continue
        x.zoho_status = st
        if "ref" in payload:
            x.zoho_ref = str(payload.get("ref") or "")[:200]
        n += 1
    db.commit()
    M.log_action(db, user.id, "zoho_mark", f"{n} petty cash line(s) marked '{st or 'waiting'}' for Zoho")
    return {"ok": True, "marked": n}


@router.get("/export/accounts/zoho")
def export_queue(token: str, format: str = "excel", book: str = "", db: Session = Depends(get_db)):
    """The waiting list as the standard report: Preview, PDF or Excel."""
    u = auth.get_download_user_from_token(token, db)
    if RIGHT not in M.effective_permissions(u):
        raise HTTPException(status_code=403, detail="Send to Zoho is for the chief accountant.")
    learned = _learned(db)
    users = {x.id: (x.full_name or x.username) for x in db.query(models.User).all()}
    rows = [_row(x, learned, users) for x in _waiting(db)]
    if book in BOOKS:
        rows = [r for r in rows if r["book"] == book]
    out = [{"Book": r["book_label"], "Date": M._as_date(r["date"]).strftime("%d-%b-%y"), "Description": r["description"],
            "Supplier": r["supplier"] or "-", "Project": r["site"] or "-", "Zoho account": r["account"] or "-",
            "VAT": ("Yes" + (f" ({r['trn']})" if r["trn"] else "")) if r["vat"] else "No",
            "Amount (AED)": r["amount"], "To fix": ", ".join(r["flags"]) or "-"} for r in rows]
    title = "Petty cash - waiting for Zoho"
    sub = (f"{len(rows)} line{'' if len(rows) == 1 else 's'}" + (f" | {BOOKS[book]} book" if book in BOOKS else " | all books")
           + f" | from {_start(db):%d %b %Y} | As at {M._dubai_today():%d %b %Y}")
    money = ["Amount (AED)"]
    if format == "view":
        url = f"/export/accounts/zoho?book={quote(book)}&token={quote(auth.create_view_token(u.username), safe='')}"
        return M._preview_page(title, sub, out, url, url, money_cols=money)
    name = "Petty_cash_for_Zoho"
    if format == "pdf":
        return StreamingResponse(export_web.build_store_report_pdf(title, out, sub, money_cols=money, orientation="landscape"),
                                 media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})
    return StreamingResponse(export_web.build_store_report_excel(title, out, sub, money_cols=money),
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename={name}.xlsx"})

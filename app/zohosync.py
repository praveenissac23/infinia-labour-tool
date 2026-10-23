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
import json
import re
from datetime import datetime, timezone, timedelta
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
# The books that go to Zoho. The directors' books (Naveen, Praveen) are kept
# in the portal only - the chief accountant makes those Zoho entries himself
# (his go-live answers, 14 Oct 2026).
ZOHO_BOOKS = ("site", "pro", "office")
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


def _db():
    from database import SessionLocal
    return SessionLocal()


def paid_ok(account, db=None):
    """A cost the money went on: one of the portal's heads, any Zoho account
    that is not a money box or income, or a transfer to a Zoho box."""
    import zohoapi
    if account in PAID_ACCOUNTS:
        return True
    if account in zohoapi.VENDOR_PAY:
        return True
    k = zohoapi.account_kind(db, account)
    if account.startswith("Transfer to "):
        return k in zohoapi.MONEY_BOXES
    if account.startswith("From "):
        return False
    return bool(k) and k not in zohoapi.MONEY_BOXES and k not in zohoapi.NOT_OFFERED


def received_ok(account, db=None):
    import zohoapi
    if account in RECEIVED_ACCOUNTS:
        return True
    if not account.startswith("From "):
        return False
    k = zohoapi.account_kind(db, account)
    return bool(k) and k not in zohoapi.NOT_OFFERED


def needs_project(x, account, db=None):
    """A project cost: one of the portal's cost heads. A Zoho account picked
    from the list takes a project when one is given, but does not demand one -
    the chief accountant uses some of them for costs no site carries (14 Oct)."""
    return account in PROJECT_ACCOUNTS


def modern(account):
    """A suggestion in the old office wording ("Office › Salik Fee") as the
    account is named in Zoho's list."""
    import zohoapi
    if not account.startswith("Office › "):
        return account
    leaf = account[len("Office › "):]
    want = zohoapi.ALIAS.get(zohoapi._norm(leaf), leaf)
    a = zohoapi.account_index(None).get(zohoapi._norm(want))
    return zoho_value(a) if a else account


def _flags(x, account):
    """What must be put right before the line can go."""
    out = []
    if (getattr(x, "zoho_kind", "") or "") == "payment" and not x.received:
        if not (getattr(x, "zoho_vendor_id", "") or "").strip():
            out.append("Pick the supplier")
        if x.vat and (x.vat_claim or "") not in ("claim", "zero"):
            out.append("Pick VAT: claim or not")
        return out
    if not account:
        out.append("Pick account")
    elif x.received and not received_ok(account):
        out.append("Pick where it came from")
    elif not x.received and not paid_ok(account):
        out.append("Pick account")
    if needs_project(x, account) and not (x.site or "").strip():
        out.append("Pick project")
    if x.vat and (x.vat_claim or "") not in ("claim", "zero"):
        out.append("Pick VAT: claim or not")
    if x.vat and x.vat_claim == "claim" and not (x.trn or "").strip():
        out.append("VAT claimed without TRN")
    parts = _parts(x)
    if parts is not None:
        total = round((x.paid or 0), 2)
        if len(parts) < 2 or any(not p.get("account") or not paid_ok(p["account"]) or p["account"].startswith("Transfer to ")
                                 or float(p.get("amount") or 0) <= 0 for p in parts):
            out.append("Split: each part needs an account and an amount")
        elif abs(round(sum(float(p["amount"]) for p in parts), 2) - total) > 0.005:
            out.append(f"Split parts must add up to {total:,.2f}")
        elif any(needs_project(x, p["account"]) for p in parts) and not (x.site or "").strip():
            out.append("Pick project")
    return out


def _parts(x):
    """The split of one receipt, or None when it is not split."""
    import json as _j
    try:
        v = _j.loads(x.splits or "null")
    except ValueError:
        return None
    return v if isinstance(v, list) and v else None


def _waiting(db):
    q = (db.query(models.PettyCash)
           .filter(models.PettyCash.book.in_(list(ZOHO_BOOKS)), models.PettyCash.on_date >= _start(db))
           .filter((models.PettyCash.zoho_status == "") | (models.PettyCash.zoho_status.is_(None)) | (models.PettyCash.zoho_status == "changed"))
           .order_by(models.PettyCash.on_date, models.PettyCash.id))
    return q.all()


def _row(x, learned, users):
    acc = x.zoho_account if x.zoho_status == "changed" and x.zoho_account else modern(suggest(x, learned))
    return {"id": x.id, "book": x.book or "site", "book_label": BOOKS.get(x.book or "site", x.book), "date": x.on_date.isoformat(),
            "description": x.description or "", "supplier": x.supplier or "", "site": x.site or "",
            "amount": round((x.paid or 0) or (x.received or 0), 2), "kind": "received" if x.received else "paid",
            "vat": bool(x.vat), "trn": x.trn or "", "vat_claim": x.vat_claim or "", "receipt_no": x.receipt_no or "",
            "splits": _parts(x) or [], "account": acc, "flags": _flags(x, acc),
            "zoho_kind": x.zoho_kind or "expense", "vendor_id": x.zoho_vendor_id or "", "vendor": x.zoho_vendor or "",
            "bill_id": x.zoho_bill_id or "", "bill_no": x.zoho_bill_no or "",
            "changed": x.zoho_status == "changed", "zoho_ref": x.zoho_ref or "",
            "by": users.get(x.updated_by or x.created_by, "")}


def _set_site(db, x, site, user):
    """The chief accountant puts the project on a line the person who typed
    it left blank (or got wrong). It is the petty cash line itself that
    changes, so the petty cash book shows it too, and Zoho gets it."""
    site = " ".join(str(site or "").split())[:40]
    if site and not db.query(models.Site).filter(models.Site.code == site).first():
        raise HTTPException(status_code=400, detail=f"No project {site}.")
    was = x.site or ""
    if site == was:
        return
    x.site = site
    x.updated_by = user.id
    M.log_action(db, user.id, "petty_site", f"petty cash #{x.id} {x.description}: project {was or 'none'} -> {site or 'none'} (Send to Zoho)")


@router.post("/store/zoho/site")
def set_site(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = ZG):
    x = db.get(models.PettyCash, int(payload.get("id") or 0))
    if not x:
        raise HTTPException(status_code=404, detail="That line is no longer there.")
    if (x.zoho_status or "") not in ("",):
        raise HTTPException(status_code=400, detail="It is already approved for Zoho - change it there.")
    _set_site(db, x, payload.get("site"), user)
    db.commit()
    return {"ok": True, "site": x.site or ""}


@router.get("/store/zoho/heads")
def heads(user: models.User = ZG):
    return {"groups": GROUPS}


# ---- The account list the chief accountant picks from ----------------------
# Zoho's own accounts, named and grouped as in Zoho - but only the ones he
# uses for petty cash (read from Zoho, 30 Mar-14 Oct 2026) plus the ones he
# asked for. More can be added to "offer" in zoho_accounts_seed.json.
TYPE_LABEL = [("cost_of_goods_sold", "Project costs"), ("expense", "Expenses"), ("other_expense", "Other expenses"),
              ("fixed_asset", "Machinery, tools & assets"), ("other_current_asset", "Advances & deposits"),
              ("other_asset", "Advances & deposits"), ("other_current_liability", "Salaries & payables"),
              ("non_current_liability", "Salaries & payables"), ("equity", "Partners' capital")]
BOX_SKIP = {"petty cash", "round off adj", "undeposited funds", "vendor customer adjustment account", "zoho payroll - bank account",
            # People no longer with the company (Praveen, 14 Oct 2026)
            "karthik petty cash", "tony petty cash"}


def zoho_value(a):
    """How a Zoho account is written on a line: "Parent › Name", as Zoho shows it."""
    return f"{a['parent']} › {a['name']}" if a.get("parent") else a["name"]


def account_lists(db):
    import zohoapi
    seed = zohoapi._seed()
    idx = zohoapi.account_index(db)
    offer = [idx[zohoapi._norm(n)] for n in seed.get("offer", []) if zohoapi._norm(n) in idx]
    labels = dict(TYPE_LABEL)
    groups = {}
    for a in offer:
        g = labels.get(a["type"], "Other")
        groups.setdefault(g, []).append({"v": zoho_value(a), "name": a["name"], "parent": a.get("parent") or "", "type": a["type"]})
    order = [l for _, l in TYPE_LABEL]
    paid = [{"group": g, "accounts": sorted(groups[g], key=lambda r: ((r["parent"] or r["name"]).lower(), bool(r["parent"]), r["name"].lower()))}
            for g in sorted(groups, key=lambda g: order.index(g) if g in order else 99)]
    # The cost heads, each followed by the Zoho accounts under it (his answer
    # A4, 14 Oct: both). A head is "Head"; an account under it "Head › Account".
    kids = {}
    for a in idx.values():
        if a.get("parent") and a["type"] in ("cost_of_goods_sold", "expense", "other_expense"):
            kids.setdefault(zohoapi._norm(a["parent"]), []).append(a)
    heads, seen = [], set()
    # An account the portal already offers under its own wording is not listed twice.
    same = {zohoapi._norm(zohoapi.ALIAS.get(zohoapi._norm(v.split(" › ")[-1]), v.split(" › ")[-1])) for v in GROUPS[0]["accounts"]}
    for v in GROUPS[0]["accounts"]:
        leaf = v.split(" › ")[-1]
        heads.append({"v": v, "name": leaf, "parent": v.split(" › ")[0] if " › " in v else "", "type": "cost_of_goods_sold"})
        target = zohoapi.ALIAS.get(zohoapi._norm(leaf), leaf)
        for a in sorted(kids.get(zohoapi._norm(target), []), key=lambda a: a["name"].lower()):
            if a["id"] in seen or zohoapi._norm(a["name"]) in same:
                continue
            seen.add(a["id"])
            heads.append({"v": f"{a['parent']} › {a['name']}", "name": a["name"], "parent": a["parent"], "type": a["type"], "sub": 1})
    under = {h["v"] for h in heads}
    for g in paid:
        g["accounts"] = [r for r in g["accounts"] if r["v"] not in under]
    paid = [g for g in paid if g["accounts"]]
    paid.insert(0, {"group": "Project cost heads", "project": True, "accounts": heads})
    boxes = sorted((a for a in idx.values() if a["type"] in zohoapi.MONEY_BOXES and a["name"].lower() not in BOX_SKIP),
                   key=lambda a: (a["type"] != "cash", a["name"].lower()))
    paid.append({"group": "Payments to companies (no bill)", "move": True,
                 "accounts": [{"v": k, "name": k, "parent": "", "type": "vendor"} for k in zohoapi.VENDOR_PAY]})
    paid.append({"group": "Transfers - money moved to another box", "move": True,
                 "accounts": [{"v": f"Transfer to {a['name']}", "name": f"Transfer to {a['name']}", "parent": "", "type": a["type"]} for a in boxes]})
    caps = [a for a in idx.values() if a["type"] == "equity" and a["name"].startswith("Current Capital - ")]
    received = [{"group": "Cash received - from", "accounts":
                 [{"v": f"From {a['name']}", "name": f"From {a['name']}", "parent": "", "type": a["type"]} for a in boxes + caps]
                 + [{"v": "Staff advance / loan repaid", "name": "Staff advance / loan repaid", "parent": "", "type": "other_current_asset"},
                    {"v": "Client payment received in cash", "name": "Client payment received in cash", "parent": "", "type": ""}]}]
    by_name = {r["name"]: r["v"] for g in paid for r in g["accounts"]}
    used = [by_name[n] for n in seed.get("used", []) if n in by_name]
    if "Transfer to Cash" in by_name:
        used.append("Transfer to Cash")
    return {"paid": paid, "received": received, "used": used,
            "legacy": GROUPS[0]["accounts"], "read_at": json.loads(zohoapi._get(db, "accfull") or "{}").get("at")}


@router.get("/store/zoho/accounts")
def accounts(db: Session = Depends(get_db), user: models.User = Depends(M.require_any_screen(RIGHT, "accounts_bank"))):
    return account_lists(db)


@router.post("/store/zoho/accounts/refresh")
def accounts_refresh(db: Session = Depends(get_db), user: models.User = ZG):
    """Read Zoho's account list again (a new account made in Zoho today)."""
    import zohoapi
    if not zohoapi.connected(db):
        raise HTTPException(status_code=400, detail="Zoho is not connected - the list from the last read is used.")
    try:
        zohoapi.chart_fresh(db)
    except zohoapi.ZohoError as e:
        raise HTTPException(status_code=400, detail=f"Zoho did not answer: {e.msg[:150]}")
    return account_lists(db)


@router.get("/store/zoho/vendors")
def vendors(fresh: int = 0, db: Session = Depends(get_db), user: models.User = ZG):
    """Every Zoho supplier, for "Paid to" on Send to Zoho."""
    import zohoapi
    if not zohoapi.connected(db):
        return {"vendors": []}
    try:
        return {"vendors": zohoapi.vendor_list(db, fresh=bool(fresh))}
    except Exception as e:
        return {"vendors": [], "error": str(e)[:200]}


@router.get("/store/zoho/bills")
def vendor_bills(vendor_id: str = "", db: Session = Depends(get_db), user: models.User = ZG):
    """The supplier's bills in Zoho still (partly) unpaid, newest first - for Payment Made."""
    import zohoapi
    if not vendor_id or not zohoapi.connected(db):
        return {"bills": []}
    try:
        d = zohoapi.call(db, "GET", "bills", {"vendor_id": vendor_id, "status": "unpaid", "per_page": 100, "sort_column": "date", "sort_order": "D"})
    except Exception as e:
        return {"bills": [], "error": str(e)[:200]}
    return {"bills": [{"id": b["bill_id"], "number": b.get("bill_number") or "", "date": b.get("date") or "", "due": b.get("due_date") or "",
                       "total": round(float(b.get("total") or 0), 2), "balance": round(float(b.get("balance") or 0), 2), "status": b.get("status") or ""}
                      for b in d.get("bills", []) if float(b.get("balance") or 0) > 0]}


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
    pend = (db.query(models.PettyCash).filter(models.PettyCash.zoho_status.in_(["approved", "sending", "cancelled"]))
              .order_by(models.PettyCash.on_date, models.PettyCash.id).all())
    pending = [{"id": x.id, "book_label": BOOKS.get(x.book or "site", x.book), "date": x.on_date.isoformat(),
                "description": x.description or "", "amount": round((x.paid or 0) or (x.received or 0), 2),
                "account": x.zoho_account or "", "status": x.zoho_status, "err": x.zoho_err or ""} for x in pend]
    return {"rows": rows, "groups": GROUPS, "start": _start(db).isoformat(), "pending": pending,
            "connected": zohoapi.connected(db),
            "waiting": len(rows), "waiting_total": round(sum(r["amount"] for r in rows), 2),
            "to_fix": sum(1 for r in rows if r["flags"]),
            "sent_month": len(sent_month), "todo": _todo(db)}


def _todo(db):
    """Sent without the supplier as a Zoho vendor - to add in Zoho."""
    out = [{"src": "petty", "id": x.id, "date": x.on_date.isoformat(), "who": x.supplier or "", "amount": round(x.paid or 0, 2),
            "what": x.description or "", "ref": x.zoho_ref or ""}
           for x in db.query(models.PettyCash).filter(models.PettyCash.zoho_todo == "supplier").order_by(models.PettyCash.on_date).all()]
    out += [{"src": "bank", "id": x.id, "date": x.on_date.isoformat(), "who": x.party or "", "amount": round(x.amount or 0, 2),
             "what": x.notes or x.reference or "", "ref": x.zoho_ref or ""}
            for x in db.query(models.BankEntry).filter(models.BankEntry.zoho_todo == "supplier").order_by(models.BankEntry.on_date).all()]
    return out


@router.post("/store/zoho/todo/done")
def todo_done(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = ZG):
    """The supplier has been added on the entry in Zoho."""
    model = models.BankEntry if payload.get("src") == "bank" else models.PettyCash
    x = db.get(model, int(payload.get("id") or 0))
    if x:
        x.zoho_todo = ""
        db.commit()
    return {"ok": True}


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
        if (x.book or "site") not in ZOHO_BOOKS:
            refused.append({"id": x.id, "why": f"{BOOKS.get(x.book, x.book)} book is kept in the portal only"})
            continue
        if x.zoho_status == "changed":
            # Already in Zoho once: never posted a second time. Only the
            # Corrected in Zoho button (corrected=true) clears it.
            if not ln.get("corrected"):
                refused.append({"id": x.id, "why": "Changed after Zoho - correct it in Zoho, then press Corrected in Zoho"})
                continue
            x.zoho_status = "sent" if (x.zoho_id or "") else "inzoho"
            x.zoho_ref = ((x.zoho_ref or "").split(" · corrected")[0] + f" · corrected in Zoho {now:%d %b}")[:200]
            x.approved_by, x.approved_at = user.id, now
            M.log_action(db, user.id, "zoho_corrected", f"petty cash #{x.id} {x.description} confirmed corrected in Zoho")
            continue
        if "site" in ln and str(ln.get("site") or "").strip() != (x.site or "").strip():
            _set_site(db, x, ln.get("site"), user)
        t = "".join(ch for ch in str(ln.get("trn") or "") if ch.isdigit())
        if x.vat and not (x.trn or "").strip() and len(t) == 15:
            x.trn = t
        acc = str(ln.get("account") or "").strip()
        vc = str(ln.get("vat_claim") or "")
        if vc == "none" and not x.received and x.vat:            # the chief accountant: the bill has no VAT - the whole amount is the cost
            M.log_action(db, user.id, "petty_vat", f"petty cash #{x.id} {x.description}: VAT taken off by the chief accountant")
            x.vat, x.vat_claim = False, ""
        elif vc in ("claim", "zero") and not x.received:
            if not x.vat:                                         # a bill entered without VAT that has it
                M.log_action(db, user.id, "petty_vat", f"petty cash #{x.id} {x.description}: VAT added by the chief accountant")
                x.vat = True
                if len(t) == 15 and not (x.trn or "").strip():
                    x.trn = t
            x.vat_claim = vc
        if not x.received:                                     # expense, or Payment Made to a supplier against his bill
            x.zoho_kind = "payment" if str(ln.get("zoho_kind") or "") == "payment" else "expense"
            x.zoho_vendor_id = str(ln.get("vendor_id") or "").strip()[:40] if x.zoho_kind == "payment" else ""
            x.zoho_vendor = str(ln.get("vendor") or "").strip()[:160] if x.zoho_vendor_id else ""
            x.zoho_bill_id = str(ln.get("bill_id") or "").strip()[:40] if x.zoho_vendor_id else ""
            x.zoho_bill_no = str(ln.get("bill_no") or "").strip()[:80] if x.zoho_bill_id else ""
        if "splits" in ln:
            parts = [{"account": str(p.get("account") or "").strip(), "amount": round(float(str(p.get("amount") or 0).replace(",", "") or 0), 2)}
                     for p in (ln.get("splits") or []) if str(p.get("account") or "").strip() or float(str(p.get("amount") or 0).replace(",", "") or 0)]
            import json as _j
            x.splits = _j.dumps(parts) if parts else ""
            if parts:
                acc = parts[0]["account"]
        if x.zoho_kind == "payment" and not acc:
            acc = f"Payment to {x.zoho_vendor}"
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
    q = db.query(models.PettyCash).filter(models.PettyCash.zoho_status.in_(["approved", "sending"]))
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
        if st == "" and ((x.zoho_id or "") and x.zoho_status in ("sent", "changed", "sending")):
            raise HTTPException(status_code=400, detail=f"PC-{x.id} is in Zoho - putting it back to waiting would send it twice.")
        x.zoho_status = st
        if st:
            x.zoho_err = ""
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
            "Paid (AED)": "" if r["kind"] == "received" else r["amount"],
            "Received (AED)": r["amount"] if r["kind"] == "received" else "",
            "To fix": ", ".join(r["flags"]) or "-"} for r in rows]
    title = "Petty cash - waiting for Zoho"
    sub = (f"{len(rows)} line{'' if len(rows) == 1 else 's'}" + (f" | {BOOKS[book]} book" if book in BOOKS else " | all books")
           + f" | from {_start(db):%d %b %Y} | As at {M._dubai_today():%d %b %Y}")
    money = ["Paid (AED)", "Received (AED)"]
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


# ---- staff loans and advances ---------------------------------------------------

def _loans_waiting(db):
    start = _start(db)
    return (db.query(models.StaffLoan).filter(models.StaffLoan.paid_from.in_(["ADCB", "Cash"]),
                                              models.StaffLoan.taken_on >= start)
              .filter((models.StaffLoan.zoho_status == "") | (models.StaffLoan.zoho_status.is_(None)) | (models.StaffLoan.zoho_status == "sending"))
              .order_by(models.StaffLoan.taken_on, models.StaffLoan.id).all())


@router.get("/store/zoho/loans")
def loans(db: Session = Depends(get_db), user: models.User = ZG):
    emps = {e.id: e for e in db.query(models.Employee).all()}
    rows = []
    for l in _loans_waiting(db):
        e = emps.get(l.employee_id)
        rows.append({"id": l.id, "date": l.taken_on.isoformat(), "who": f"{e.emp_no} {e.name}" if e else "", "amount": round(l.amount or 0, 2),
                     "paid_from": l.paid_from, "err": "" if (l.zoho_err or "").startswith("sending@") else (l.zoho_err or "")})
    return {"rows": rows}


@router.post("/store/zoho/loans/send")
def send_loans(payload: dict = Body(default={}), db: Session = Depends(get_db), user: models.User = ZG):
    import zohoapi
    if not zohoapi.connected(db):
        raise HTTPException(status_code=400, detail="Zoho is not connected yet - press Connect Zoho.")
    ids = {int(i) for i in (payload.get("ids") or [])}
    emps = {e.id: e for e in db.query(models.Employee).all()}
    sent, failed = 0, []
    for l in _loans_waiting(db):
        if ids and l.id not in ids:
            continue
        unsure = bool(l.zoho_err)
        if l.zoho_status is None:
            l.zoho_status = ""
            db.commit()
        if not zohoapi.claim(db, models.StaffLoan, l, ("",)):
            continue
        try:
            zid = zohoapi.find_existing(db, f"LN-{l.id}", [("journals", "journals", "journal_id", "reference_number")]) if unsure else ""
            if not zid:
                with zohoapi.about("loan", l.id, f"LN-{l.id}", user.id):
                    zid = zohoapi.push_loan(db, l, emps.get(l.employee_id))
            l.zoho_id = zid
            l.zoho_status, l.zoho_err = "sent", ""
            sent += 1
        except Exception as e:
            l.zoho_status = ""
            l.zoho_err = zohoapi.fail_text(e)
            failed.append({"id": l.id, "why": l.zoho_err})
        db.commit()
    if sent:
        M.log_action(db, user.id, "zoho_loans", f"{sent} staff loan(s) sent to Zoho")
    return {"ok": True, "sent": sent, "failed": failed}


# ---- October check: lines already typed into Zoho by hand ----------------------

CHANGEOVER = "2026-10-14"      # the last day the chief accountant typed into Zoho


def _zoho_entries(db, d0, d1):
    """Zoho's expenses, journals and transfers between two dates - a few
    large reads, kept for 15 minutes so the check costs Zoho little."""
    import zohoapi
    def fetch():
        out = []
        for path, key, idk in (("expenses", "expenses", "expense_id"), ("journals", "journals", "journal_id"),
                               ("banktransactions", "banktransactions", "transaction_id")):
            page = 1
            while page <= 5:
                d = zohoapi.call(db, "GET", path, {"date_start": d0, "date_end": d1, "per_page": 200, "page": page})
                for e in d.get(key, []):
                    amt = e.get("total") if path != "banktransactions" else e.get("amount")
                    if amt is None:
                        amt = e.get("amount")
                    out.append({"kind": path, "id": e.get(idk), "date": e.get("date") or e.get("journal_date") or "",
                                "amount": round(float(amt or 0), 2), "account": e.get("account_name") or "",
                                "paid_through": e.get("paid_through_account_name") or e.get("offset_account_name") or "",
                                "vendor": e.get("vendor_name") or "", "ref": e.get("reference_number") or "",
                                "desc": (e.get("description") or e.get("notes") or "")[:80],
                                "label": {"expenses": "Expense", "journals": "Journal " + str(e.get("entry_number") or ""),
                                          "banktransactions": "Transfer"}[path]})
                if not d.get("page_context", {}).get("has_more_page"):
                    break
                page += 1
        return out
    return zohoapi._cached(db, f"oct:{d0}:{d1}", fetch, ttl=900)


@router.get("/store/zoho/october")
def october(db: Session = Depends(get_db), user: models.User = ZG):
    """Portal lines from the start date to the changeover that look like
    they are in Zoho already (same date and amount; the same petty cash
    account where Zoho shows it). The chief accountant confirms each."""
    import zohoapi
    if not zohoapi.connected(db):
        raise HTTPException(status_code=400, detail="Zoho is not connected yet - press Connect Zoho.")
    d0, d1 = _start(db).isoformat(), (M.get_setting(db, "zoho_changeover") or CHANGEOVER)
    lines = (db.query(models.PettyCash).filter(models.PettyCash.on_date >= d0, models.PettyCash.on_date <= d1,
                                               models.PettyCash.book.in_(list(ZOHO_BOOKS)),
                                               models.PettyCash.zoho_status.in_(["", "approved"]))
               .order_by(models.PettyCash.on_date, models.PettyCash.id).all())
    try:
        z = _zoho_entries(db, d0, d1)
    except zohoapi.ZohoError as e:
        raise HTTPException(status_code=400, detail=f"Could not read Zoho now ({e.msg[:120]}) - try again in a few minutes.")
    used = set(x.zoho_ref.split("#")[-1] for x in db.query(models.PettyCash).filter(models.PettyCash.zoho_status == "inzoho",
                                                                                    models.PettyCash.zoho_ref.like("%#%")).all())
    def norm(s):
        return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in (s or "")).split())
    out, taken = [], set()
    for x in lines:
        amt = round((x.paid or 0) or (x.received or 0), 2)
        book_acc = norm(zohoapi.BOOK_ACCOUNT.get(x.book or "site", ""))
        cands = [e for e in z if e["date"] == x.on_date.isoformat() and abs(e["amount"] - amt) < 0.01
                 and f"{e['kind']}:{e['id']}" not in taken and str(e["id"]) not in used]
        # prefer the one paid from this book's account
        cands.sort(key=lambda e: (norm(e["paid_through"]) != book_acc, e["kind"] != "expenses"))
        m = cands[0] if cands else None
        if m:
            taken.add(f"{m['kind']}:{m['id']}")
        out.append({"id": x.id, "book_label": BOOKS.get(x.book or "site", x.book), "date": x.on_date.isoformat(),
                    "description": x.description or "", "supplier": x.supplier or "", "amount": amt,
                    "kind": "received" if x.received else "paid",
                    "match": m and {k: m[k] for k in ("label", "id", "kind", "account", "paid_through", "vendor", "ref", "desc")},
                    "sure": bool(m and norm(m["paid_through"]) == book_acc)})
    return {"from": d0, "to": d1, "rows": out, "zoho_count": len(z),
            "matched": sum(1 for r in out if r["match"]), "missing": sum(1 for r in out if not r["match"])}


@router.post("/store/zoho/october/confirm")
def october_confirm(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = ZG):
    """'Same' - the line is already in Zoho: never sent. Kept with the
    Zoho entry it matched."""
    n = 0
    for it in payload.get("items") or []:
        x = db.get(models.PettyCash, int(it.get("id") or 0))
        if not x or (x.zoho_status or "") not in ("", "approved"):
            continue
        x.zoho_status = "inzoho"
        x.zoho_ref = (f"{it.get('label') or 'In Zoho'} · typed by hand #{it.get('zid') or ''}")[:200]
        x.zoho_err = ""
        x.approved_by, x.approved_at = user.id, datetime.now(timezone.utc)
        n += 1
    db.commit()
    if n:
        M.log_action(db, user.id, "zoho_october", f"{n} October petty cash line(s) confirmed already in Zoho")
    return {"ok": True, "marked": n}


# ---- Nothing left out of Zoho: the 3-day reminder ------------------------------
OVERDUE_DAYS = 3


def overdue(db, today=None):
    """What is still not in Zoho OVERDUE_DAYS after its date: petty cash
    (waiting, approved-not-sent, changed, deleted in Zoho), bank lines,
    LPOs and staff loans - from the Zoho start date on."""
    today = today or M._dubai_today()
    cut, start = today - timedelta(days=OVERDUE_DAYS), _start(db)
    petty = (db.query(models.PettyCash).filter(models.PettyCash.book.in_(list(ZOHO_BOOKS)), models.PettyCash.on_date >= start, models.PettyCash.on_date <= cut)
               .filter((models.PettyCash.zoho_status.in_(["", "approved", "sending", "changed", "cancelled"])) | (models.PettyCash.zoho_status.is_(None))).count())
    bank = (db.query(models.BankEntry).filter(models.BankEntry.on_date <= cut)
              .filter((models.BankEntry.zoho_status.in_(["", "sending"])) | (models.BankEntry.zoho_status.is_(None))).count())
    lpo = (db.query(models.PurchaseOrder).filter(models.PurchaseOrder.order_date >= start, models.PurchaseOrder.order_date <= cut,
                                                 models.PurchaseOrder.status != "cancelled")
             .filter((models.PurchaseOrder.zoho_status.in_(["", "sending", "changed"])) | (models.PurchaseOrder.zoho_status.is_(None))).count())
    loans = sum(1 for l in _loans_waiting(db) if l.taken_on <= cut)
    return {"petty": petty, "bank": bank, "lpo": lpo, "loans": loans, "total": petty + bank + lpo + loans}


def overdue_notice(db, today=None):
    today = today or M._dubai_today()
    o = overdue(db, today)
    if not o["total"]:
        return None
    parts = [f"{o[k]} {lab}" for k, lab in (("petty", "petty cash"), ("bank", "bank"), ("lpo", "LPO" + ("s" if o["lpo"] != 1 else "")),
                                              ("loans", "staff loan" + ("s" if o["loans"] != 1 else ""))) if o[k]]
    return {"id": f"zoho-{today}-{o['total']}", "kind": "zoho",
            "title": f"{o['total']} line{'s' if o['total'] != 1 else ''} not in Zoho for over {OVERDUE_DAYS} days",
            "detail": ", ".join(parts) + " - Accounts > Send to Zoho", "lines": parts + ["Accounts > Send to Zoho"],
            "screen": "zoho", "when": today.isoformat(),
            "count": o["total"], "level": "warn"}


def golive_office_skip(db):
    """Go-live answers (14 Oct 2026): the 1-14 Oct Office lines not yet in
    Zoho are adjusted in Zoho by the chief accountant himself - marked
    'Not for Zoho' so the portal never sends them. Once."""
    if M.get_setting(db, "golive_office_skip"):
        return 0
    from datetime import date as _d
    rows = (db.query(models.PettyCash).filter(models.PettyCash.book == "office",
                                              models.PettyCash.on_date >= _d(2026, 10, 1), models.PettyCash.on_date <= _d(2026, 10, 14))
              .filter((models.PettyCash.zoho_status == "") | (models.PettyCash.zoho_status.is_(None))).all())
    for x in rows:
        x.zoho_status = "skip"
        x.zoho_ref = "Adjusted in Zoho by the chief accountant (go-live, 14 Oct)"
    M.put_setting(db, "golive_office_skip", str(len(rows)))
    db.commit()
    return len(rows)

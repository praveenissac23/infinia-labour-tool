"""The portal's own link to Zoho Books.

Connected once by the chief accountant: Accounts > Send to Zoho >
Connect Zoho. Zoho asks him to allow the portal, and gives back a
refresh token the server keeps locked (the same key file as the
Credentials tab - never in the database in plain text, never in git).
From then on an approved line goes to Zoho the moment it is approved.

What each petty cash line becomes in Zoho, the way it is entered today:
  bill paid, expense / cost head  -> Expense, paid through the book's account
                                     (Site / Jomon / Company Petty Cash, or the
                                     director's Current Capital), with project
  bill paid, transfer to a box    -> Transfer Fund (from this box to that one)
  bill paid, staff advance        -> Journal: Employee Advance / this box
  cash received from a bank/box   -> Transfer Fund (from there into this box)
  cash received, other            -> Journal: this box / where it came from
Every entry carries "PC-<line no>" as its reference, so it is found again.
"""
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Body, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

import main as M
import models
import auth
from database import get_db

router = APIRouter()
RIGHT = "accounts_zoho"
ZG = Depends(M.require_any_screen(RIGHT))
SCOPE = "ZohoBooks.fullaccess.all"
ORG_DEFAULT = "904498653"           # INFINIA CONTRACTING LLC
PUBLIC = "https://app.infinia.ae"
REDIRECT = PUBLIC + "/store/zoho/link/callback"

# The Zoho account each book pays through.
BOOK_ACCOUNT = {"site": "Site Petty Cash", "pro": "Jomon Petty Cash", "office": "Company Petty Cash",
                "naveen": "Current Capital - Naveen", "praveen": "Current Capital - Praveen"}
DIRECTOR = {"naveen", "praveen"}
TRANSFER_TO = {"Transfer to Company Petty Cash": "Company Petty Cash", "Transfer to Jomon Petty Cash": "Jomon Petty Cash",
               "Transfer to Site Petty Cash": "Site Petty Cash"}
SOURCE_ACC = {"From ADCB (transfer / cheque cashed)": "ADCB", "From Cash": "Cash",
              "From Company Petty Cash": "Company Petty Cash", "From Jomon Petty Cash": "Jomon Petty Cash",
              "From Site Petty Cash": "Site Petty Cash", "From Current Capital - Praveen": "Current Capital - Praveen",
              "From Current Capital - Naveen": "Current Capital - Naveen", "Staff advance / loan repaid": "Employee Advance"}
CASHLIKE = {"ADCB", "Cash", "Company Petty Cash", "Jomon Petty Cash", "Site Petty Cash"}
# A cost head or office account named a little differently in Zoho.
# Portal name (folded) -> the name it has in Zoho. Checked against Zoho on 14 Oct 2026.
ALIAS = {"authority payments": "Authority Payment",
         "parking fees and fines": "Parkin Fees and Fines",
         "soil investigation and other surveys": "Soil Investigation, Topo survey & Gate Level Survey",
         # Zoho's "Design & Supervision Fee" is an INCOME account - costs go here:
         "design & supervision fee": "Design and Supervision Charges",
         "agent commission and key money": "Agent Commission & Service Charges",
         "land purchase": "00. Land Expenses"}

_TOKEN = {"value": "", "until": 0.0}
_CACHE = {}


# ---- settings, locked ----------------------------------------------------

def _lock(t):
    import credentials
    return credentials.lock(t)


def _unlock(t):
    import credentials
    return credentials.unlock(t)


def _get(db, k, d=""):
    return M.get_setting(db, "zoho_" + k) or d


def _put(db, k, v):
    M.put_setting(db, "zoho_" + k, v)
    db.commit()


def connected(db):
    return bool(_get(db, "refresh"))


def _accounts_host(db):
    return _get(db, "accounts_host", "https://accounts.zoho.com")


def _api_host(db):
    return _get(db, "api_host", "https://www.zohoapis.com")


def org(db):
    return _get(db, "org", ORG_DEFAULT)


# ---- talking to Zoho -----------------------------------------------------

def _post_form(url, data):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode() or "{}")
        except Exception:
            return {"error": f"HTTP {e.code}"}


def _access(db):
    if _TOKEN["value"] and _TOKEN["until"] > time.time() + 60:
        return _TOKEN["value"]
    rt = _unlock(_get(db, "refresh"))
    if not rt:
        raise HTTPException(status_code=400, detail="Zoho is not connected yet - press Connect Zoho.")
    d = _post_form(_accounts_host(db) + "/oauth/v2/token",
                   {"refresh_token": rt, "client_id": _get(db, "client_id"), "client_secret": _unlock(_get(db, "client_secret")),
                    "grant_type": "refresh_token"})
    if not d.get("access_token"):
        raise HTTPException(status_code=502, detail=f"Zoho refused the link: {d.get('error') or d}. Connect Zoho again.")
    _TOKEN.update(value=d["access_token"], until=time.time() + int(d.get("expires_in") or 3600))
    return _TOKEN["value"]


import contextvars
from contextlib import contextmanager
# What the portal is sending right now (set by each Send loop), so every
# change made in Zoho is logged against its portal line - see zoholog.py.
ZCTX = contextvars.ContextVar("zoho_ctx", default=None)


@contextmanager
def about(source, item_id=None, ref="", user_id=None):
    tok = ZCTX.set({"source": source, "item_id": item_id, "ref": ref, "user_id": user_id})
    try:
        yield
    finally:
        ZCTX.reset(tok)


def call(db, method, path, params=None, body=None):
    """One Books API call. Returns Zoho's JSON; raises with Zoho's own
    message when it refuses. Every change (POST/PUT/DELETE) is logged."""
    if method == "GET":
        return _call(db, method, path, params, body)
    try:
        d = _call(db, method, path, params, body)
    except ZohoError as e:
        _record(db, method, path, body, None, e.msg)
        raise
    _record(db, method, path, body, d, "")
    return d


def _record(db, method, path, body, resp, err):
    try:
        import zoholog
        zoholog.record(db, method, path, body, resp, err, ZCTX.get() or {})
    except Exception:
        pass                                  # the log never stops a send


def _call(db, method, path, params=None, body=None):
    q = dict(params or {})
    q.setdefault("organization_id", org(db))
    url = f"{_api_host(db)}/books/v3/{path.lstrip('/')}?{urllib.parse.urlencode(q)}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": "Zoho-oauthtoken " + _access(db), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            d = json.loads(e.read().decode() or "{}")
        except Exception:
            d = {}
        raise ZohoError(e.code, d.get("message") or f"HTTP {e.code}")


class ZohoError(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code, self.msg = code, msg


# ---- names to Zoho ids -----------------------------------------------------

def _norm(s):
    return " ".join("".join(ch.lower() if ch.isalnum() or ch in "&." else " " for ch in (s or "")).split())


def _cached(db, key, fetch, ttl=3600):
    hit = _CACHE.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    v = fetch()
    _CACHE[key] = (time.time() + ttl, v)
    return v


def _take(out, rows, full=None):
    for a in rows:
        if a.get("is_active", True) and a.get("account_type") != "income":
            out.setdefault(_norm(a["account_name"]), a["account_id"])
            if full is not None and a.get("account_type") not in ("other_income",):
                full.setdefault(a["account_id"], {"id": a["account_id"], "name": (a.get("account_name") or "").strip(),
                                                  "type": a.get("account_type") or "",
                                                  "parent": (a.get("parent_account_name") or "").strip()})


# ---- Zoho's own account list, as the chief accountant sees it in Zoho ------
# Offered in the portal exactly as Zoho groups it: by type, each parent with
# its sub-accounts under it. Until Zoho is read the first time, the export of
# 14 Oct 2026 (app/zoho_accounts_seed.json) stands in.
# Paid out of a petty cash box to a sister company, with no bill: a
# vendor payment (it sits as their advance until bills come) - the chief
# accountant's answers D1-D4, 14 Oct 2026. Portal name -> Zoho vendor name.
VENDOR_PAY = {"Payment to Prime Infinia Technical Services": "Prime Infinia Technical Services L.LC",
              "Payment to EngiNova Technical Services": "EngiNova Technical Services L.L.C"}
NOT_OFFERED = {"income", "other_income", "accounts_receivable", "accounts_payable", "stock", "credit_card"}
MONEY_BOXES = {"cash", "bank"}


def _seed():
    import os
    p = os.path.join(os.path.dirname(__file__), "zoho_accounts_seed.json")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"accounts": [], "used": []}


def accounts_full(db):
    """Every active Zoho account [{id, name, type, parent}] - the last list
    read from Zoho, else the export."""
    hit = _CACHE.get("chart_full")
    if hit:
        return hit
    saved = json.loads(_get(db, "accfull") or "{}")
    rows = saved.get("rows") or _seed().get("accounts") or []
    _CACHE["chart_full"] = rows
    return rows


def account_index(db):
    """Folded name -> account, for checking what was picked."""
    rows = accounts_full(db)
    hit = _CACHE.get("chart_idx")
    if hit and hit[0] is rows:
        return hit[1]
    idx = {_norm(a["name"]): a for a in rows}
    _CACHE["chart_idx"] = (rows, idx)
    return idx


def leaf(value):
    return (value or "").split(" › ")[-1].strip()


def account_kind(db, value):
    """What a picked account is: its Zoho type, or "" if Zoho has no such
    account. "Transfer to X" / "From X" are read as the box X."""
    v = (value or "").strip()
    for pre in ("Transfer to ", "From "):
        if v.startswith(pre):
            v = v[len(pre):]
    a = account_index(db).get(_norm(leaf(v)))
    return a["type"] if a else ""


def chart(db):
    """Every Zoho account (not income) by its folded name. Zoho's plain list
    leaves out sub-accounts, but its search does not - so a few broad
    searches read them all. Kept in settings too, so a send never waits."""
    def fetch():
        out, full = {}, {}
        for kind in ("Asset", "Liability", "Equity", "Expense"):
            d = call(db, "GET", "chartofaccounts", {"per_page": 200, "filter_by": f"AccountType.{kind}"})
            _take(out, d.get("chartofaccounts", []), full)
        for letter in ("a", "e", "i", "o", "u"):
            page = 1
            while page <= 15:
                d = call(db, "GET", "chartofaccounts", {"search_text": letter, "per_page": 200, "page": page, "filter_by": "AccountType.Active"})
                _take(out, d.get("chartofaccounts", []), full)
                if not d.get("page_context", {}).get("has_more_page"):
                    break
                page += 1
        try:
            _put(db, "accmap", json.dumps({"at": time.time(), "map": out}))
            if len(full) > 50:                     # a whole read, not a half-answer
                rows = sorted(full.values(), key=lambda a: a["name"].lower())
                _put(db, "accfull", json.dumps({"at": time.time(), "rows": rows}))
                _CACHE["chart_full"] = rows
        except Exception:
            db.rollback()
        return out
    hit = _CACHE.get("chart")
    if hit and hit[0] > time.time():
        return hit[1]
    # Reading the whole chart is ~40 calls to Zoho - far too slow inside a
    # press of Send (nginx gives up after 60 s: the 504 of 14 Oct). When a
    # list read before is kept, use it now and read Zoho again in the
    # background; only a first-ever read waits.
    saved = json.loads(_get(db, "accmap") or "{}")
    if saved.get("map"):
        _CACHE["chart"] = (time.time() + 600, saved["map"])
        _refresh_chart_later()
        return saved["map"]
    try:
        return _cached(db, "chart", fetch)
    except ZohoError:
        raise


_CHART_BUSY = {"on": False}


def _refresh_chart_later():
    import threading
    if _CHART_BUSY["on"]:
        return
    _CHART_BUSY["on"] = True

    def run():
        from database import SessionLocal
        db2 = SessionLocal()
        try:
            _CACHE.pop("chart", None)
            chart_fresh(db2)
        except Exception as e:
            print("zoho chart refresh:", e)
        finally:
            db2.close()
            _CHART_BUSY["on"] = False
    threading.Thread(target=run, daemon=True).start()


def chart_fresh(db):
    """Read the whole chart from Zoho now (the Read again button, the background refresh)."""
    def fetch():
        out, full = {}, {}
        for kind in ("Asset", "Liability", "Equity", "Expense"):
            d = call(db, "GET", "chartofaccounts", {"per_page": 200, "filter_by": f"AccountType.{kind}"})
            _take(out, d.get("chartofaccounts", []), full)
        for letter in ("a", "e", "i", "o", "u"):
            page = 1
            while page <= 15:
                d = call(db, "GET", "chartofaccounts", {"search_text": letter, "per_page": 200, "page": page, "filter_by": "AccountType.Active"})
                _take(out, d.get("chartofaccounts", []), full)
                if not d.get("page_context", {}).get("has_more_page"):
                    break
                page += 1
        _put(db, "accmap", json.dumps({"at": time.time(), "map": out}))
        if len(full) > 50:
            rows = sorted(full.values(), key=lambda a: a["name"].lower())
            _put(db, "accfull", json.dumps({"at": time.time(), "rows": rows}))
            _CACHE["chart_full"] = rows
        return out
    out = fetch()
    _CACHE["chart"] = (time.time() + 3600, out)
    return out


def _search_account(db, name):
    """Zoho's list leaves out sub-accounts, so a name not in it is asked
    for directly - exact name first, then a search. Never an income account."""
    try:
        d = call(db, "GET", "chartofaccounts", {"account_name": name, "per_page": 50, "filter_by": "AccountType.Active"})
    except ZohoError as e:
        if e.code == 429 or "maximum number of requests" in e.msg:
            # Nothing has been posted yet - a plain "try again", not a doubt.
            raise ZohoError(400, "Zoho is busy (too many requests this minute) - press Send again in a minute")
        return ""
    for a in d.get("chartofaccounts", []):
        if _norm(a.get("account_name")) == _norm(name) and a.get("account_type") != "income":
            return a["account_id"]
    return ""


def projects(db):
    def fetch():
        d = call(db, "GET", "projects", {"per_page": 200, "filter_by": "Status.All"})
        return {(p.get("project_code") or "").strip(): (p["project_id"], p.get("customer_id") or "") for p in d.get("projects", [])}
    return _cached(db, "projects", fetch)


def vat_tax(db):
    def fetch():
        for t in call(db, "GET", "settings/taxes").get("taxes", []):
            if "standard" in (t.get("tax_name") or "").lower() and float(t.get("tax_percentage") or 0) == 5:
                return t["tax_id"]
        return ""
    return _cached(db, "vat", fetch)


VAT_MODES = ("hold", "zero", "claim")


def vat_mode(db):
    """How a bill ticked 'VAT on the receipt' goes to Zoho - the chief
    accountant's decision. Until he answers: held, nothing claimed."""
    m = _get(db, "vat_mode", "hold")
    return m if m in VAT_MODES else "hold"


def zero_tax(db):
    def fetch():
        for t in call(db, "GET", "settings/taxes").get("taxes", []):
            if float(t.get("tax_percentage") or 0) == 0 and "zero" in (t.get("tax_name") or "").lower():
                return t["tax_id"]
        return ""
    return _cached(db, "vat0", fetch)


def vat_fields(db, vat, trn, claim):
    """The tax fields of an expense, as the chief accountant enters them.
    A bill with VAT: he decides per bill - "claim" (5% Standard Rate) or
    "zero" (not claimable, e.g. the bill is in a person's name). Raises
    rather than guess."""
    if not vat:
        return {"tax_treatment": "vat_not_registered"}
    if claim not in ("claim", "zero"):
        raise ZohoError(400, "Bill with VAT: pick Claim 5% or Not claimable first - nothing sent")
    t = vat_tax(db) if claim == "claim" else zero_tax(db)
    if not t:
        raise ZohoError(400, f"Zoho has no {'5% Standard Rate' if claim == 'claim' else 'Zero Rate'} tax - nothing sent")
    out = {"tax_id": t, "tax_treatment": "vat_registered"}
    if trn:
        out["tax_reg_no"] = trn
    return out


@router.post("/store/zoho/vatmode")
def set_vat_mode(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    if (user.role or "") != "admin":
        raise HTTPException(status_code=403, detail="Only the admin sets how VAT is booked.")
    m = str(payload.get("mode") or "")
    if m not in VAT_MODES:
        raise HTTPException(status_code=400, detail="hold, zero or claim")
    _put(db, "vat_mode", m)
    M.log_action(db, user.id, "zoho_vat_mode", f"Bills with VAT: {m}")
    return {"ok": True, "mode": m}


def account_id(db, name):
    """The Zoho account for an account picked in the portal - the last
    part of "Head › Sub-head", or the office account's name."""
    leaf = name.split(" › ")[-1].strip()
    c = chart(db)
    k = _norm(leaf)
    if k in ALIAS:                      # a known different name in Zoho wins
        want = ALIAS[k]
        hit = c.get(_norm(want)) or _search_account(db, want)
    else:
        hit = c.get(k) or _search_account(db, leaf)
    if not hit and _get(db, "accfull"):
        # The full list last read from Zoho itself (never the export alone).
        known = account_index(db).get(k)
        hit = known["id"] if known else ""
    if hit:
        c[k] = hit
    return hit or ""


# ---- one line into Zoho ----------------------------------------------------

def push(db, x):
    """Send one approved petty cash line. Returns (zoho_id, label) - e.g.
    ("expense:7373...", "Expense") - or raises ZohoError / HTTPException."""
    book = x.book or "site"
    acc = x.zoho_account or ""
    ref = f"PC-{x.id}"
    rcpt = (getattr(x, "receipt_no", "") or "").strip()
    desc = ((f"Rcpt {rcpt} · " if rcpt else "") + (x.description or ""))[:100] + (f" · {x.supplier}"[:40] if x.supplier else "")
    date = x.on_date.isoformat()
    amt = round((x.paid or 0) or (x.received or 0), 2)
    box = account_id(db, BOOK_ACCOUNT[book])
    if not box:
        raise ZohoError(400, f"Zoho has no account named {BOOK_ACCOUNT[book]}")
    def need(n):
        i = account_id(db, n)
        if not i:
            raise ZohoError(400, f"Zoho has no account named {n.split(' › ')[-1]}")
        return i
    def journal(debit, credit):
        d = call(db, "POST", "journals", body={"journal_date": date, "reference_number": ref, "notes": desc,
                                                "line_items": [{"account_id": debit, "debit_or_credit": "debit", "amount": amt, "description": desc},
                                                               {"account_id": credit, "debit_or_credit": "credit", "amount": amt, "description": desc}]})
        return f"journal:{d['journal']['journal_id']}", "Journal " + str(d["journal"].get("entry_number") or "")
    def transfer(frm, to):
        d = call(db, "POST", "banktransactions", body={"transaction_type": "transfer_fund", "from_account_id": frm,
                                                        "to_account_id": to, "amount": amt, "date": date,
                                                        "reference_number": ref, "description": desc})
        return f"banktransaction:{d['banktransaction']['transaction_id']}", "Transfer"
    if x.received:
        src = SOURCE_ACC.get(acc)
        if not src and acc.startswith("From ") and account_kind(db, acc):
            src = acc[5:]                      # any Zoho box or account, as picked
        if not src:
            raise ZohoError(400, "Client cash is a customer payment - record it in Zoho against the invoice")
        sid = need(src)
        if book in DIRECTOR:
            # Repaid to the director: less owed to him, out of the bank/box.
            return journal(box, sid)
        if src in CASHLIKE or account_kind(db, src) in MONEY_BOXES:
            return transfer(sid, box)
        return journal(box, sid)
    if acc in TRANSFER_TO or (acc.startswith("Transfer to ") and account_kind(db, acc)):
        tname = TRANSFER_TO.get(acc) or acc[len("Transfer to "):]
        to = need(tname)
        if book in DIRECTOR or account_kind(db, tname) not in MONEY_BOXES:
            return journal(to, box)
        return transfer(box, to)
    if acc.startswith("Employee Advance"):
        return journal(need("Employee Advance"), box)
    if acc in VENDOR_PAY:
        vname = VENDOR_PAY[acc]
        c = call(db, "GET", "contacts", {"contact_name_contains": vname.split()[0], "contact_type": "vendor", "per_page": 50})
        hit = [k for k in c.get("contacts", []) if _norm(k.get("contact_name")) == _norm(vname)]
        if len(hit) != 1:
            raise ZohoError(400, f"Zoho has no single vendor named {vname} - nothing sent")
        d = call(db, "POST", "vendorpayments", body={"vendor_id": hit[0]["contact_id"], "payment_mode": "Cash", "amount": amt,
                                                     "date": date, "reference_number": ref, "paid_through_account_id": box,
                                                     "description": desc})
        v = d.get("vendorpayment") or d.get("vendor_payment") or {}
        return f"vendorpayment:{v.get('payment_id')}", f"Payment Made {v.get('payment_number') or ''}".strip()
    if account_kind(db, acc) == "equity":
        # Paid out to a partner's capital account: a journal, not an expense.
        return journal(need(acc), box)
    body = {"account_id": need(acc), "date": date, "amount": amt, "paid_through_account_id": box,
            "reference_number": ref, "description": desc, "is_inclusive_tax": True}
    if x.site:
        p = projects(db).get(x.site.strip())
        if p:
            body["project_id"], body["customer_id"] = p
    # Paid To: the supplier's Zoho vendor, as the accountant enters it.
    vendor = ""
    if (x.supplier or "").strip():
        key = M._supplier_key(x.supplier)
        sup = db.query(models.Supplier).filter(models.Supplier.name_key == key).first() if key else None
        vendor = (sup.zoho_id or "") if sup else ""
        if vendor:
            body["vendor_id"] = vendor
    tax = vat_fields(db, x.vat, x.trn, getattr(x, "vat_claim", "") or "")
    parts = _splits(x)
    if parts:
        # One receipt over several cost heads: one itemised expense, each
        # line to its own account. The parts were checked to add up.
        line_tax = {k: v for k, v in tax.items() if k == "tax_id"}
        body.pop("account_id"); body.pop("amount")
        body["is_itemized_expense"] = True
        body["line_items"] = [dict({"account_id": need(p["account"]), "amount": round(float(p["amount"]), 2),
                                    "description": desc, "item_order": i + 1}, **line_tax) for i, p in enumerate(parts)]
        tax = {k: v for k, v in tax.items() if k != "tax_id"}
    body.update(tax)
    d = call(db, "POST", "expenses", body=body)
    # Supplier typed but not a Zoho vendor yet: on the chief accountant's
    # list to add in Zoho (he chose to send without it).
    x.zoho_todo = "supplier" if (x.supplier or "").strip() and not vendor else ""
    return f"expense:{d['expense']['expense_id']}", "Expense" + (" (itemised)" if parts else "")


def _splits(x):
    import json as _j
    try:
        parts = _j.loads(getattr(x, "splits", "") or "[]")
    except ValueError:
        return []
    return parts if isinstance(parts, list) and len(parts) >= 2 else []


def claim(db, model, x, states):
    """Take a line for sending, so two presses (or two people) can never
    send it twice: only one request changes its status to 'sending'. A
    line left 'sending' by a request that died is taken again after five
    minutes - and Zoho is asked first whether it already has it."""
    now = time.time()
    q = db.query(model).filter(model.id == x.id)
    n = q.filter(model.zoho_status.in_(list(states))).update(
        {"zoho_status": "sending", "zoho_err": f"sending@{int(now)}"}, synchronize_session=False)
    if not n:
        cur = q.first()
        stamp = (cur.zoho_err or "") if cur else ""
        if cur and cur.zoho_status == "sending" and stamp.startswith("sending@") and now - float(stamp[8:] or 0) > 300:
            n = q.filter(model.zoho_err == stamp).update({"zoho_err": f"sending@{int(now)}!"}, synchronize_session=False)
    db.commit()
    db.refresh(x)
    return bool(n)


DOUBT = ("No answer", "Could not check")


def in_doubt(x):
    """The last send had no clear answer - Zoho may hold it. Nothing on
    the line may change until Send is pressed again and Zoho is asked."""
    return (x.zoho_status or "") == "sending" or (x.zoho_err or "").startswith(DOUBT)


def fail_text(e, again="press Send again"):
    """What to keep on a line after a failed send. Only a clear refusal
    (Zoho said no, 4xx) is plain; a server error, rate limit, timeout or
    garbled answer means Zoho may have saved it - kept in doubt."""
    if isinstance(e, ZohoError) and e.msg.startswith(DOUBT):
        return e.msg[:300]
    if isinstance(e, ZohoError) and (e.code >= 500 or e.code == 429):
        return f"No answer from Zoho ({e.code}) - {again}; Zoho is checked first. {e.msg}"[:300]
    if isinstance(e, ZohoError):
        return e.msg[:300]
    if isinstance(e, HTTPException):
        return str(e.detail)[:300]
    return f"No answer from Zoho ({type(e).__name__}) - {again}; Zoho is checked first"


def find_existing(db, token, places):
    """Does Zoho already hold an entry carrying this reference (PC-12 /
    BK-7)? Used before sending again a line whose last try had no clear
    answer - a timeout can come after Zoho has saved it."""
    for path, key, idk, field in places:
        try:
            d = call(db, "GET", path, {field: token, "per_page": 200})
        except ZohoError as e:
            # Not knowing is not "not there" - never send again blind.
            raise ZohoError(503, f"Could not check Zoho for {token} before sending again ({e.msg[:80]}) - press Send again later")
        for e in d.get(key, []):
            hay = " ".join(str(e.get(k) or "") for k in ("reference_number", "description", "notes"))
            if token in hay.split() or token in hay.replace("·", " ").split() or hay.strip().endswith(token):
                return f"{key[:-1] if key.endswith('s') else key}:{e.get(idk)}"
    return ""


PETTY_PLACES = [("expenses", "expenses", "expense_id", "reference_number"),
                ("journals", "journals", "journal_id", "reference_number"),
                ("banktransactions", "banktransactions", "transaction_id", "reference_number"),
                ("vendorpayments", "vendorpayments", "payment_id", "reference_number")]


def push_many(db, rows, user=None):
    """Send each approved line once; a refusal is kept on the line to retry."""
    sent, failed = 0, []
    for x in rows:
        unsure = (x.zoho_status == "sending") or bool(x.zoho_err)
        if not claim(db, models.PettyCash, x, ("approved",)):
            continue
        try:
            zid = find_existing(db, f"PC-{x.id}", PETTY_PLACES) if unsure else ""
            label = "Found in Zoho"
            if not zid:
                with about("petty", x.id, f"PC-{x.id}", getattr(user, "id", None)):
                    zid, label = push(db, x)
            x.zoho_status, x.zoho_id, x.zoho_ref, x.zoho_err = "sent", zid, f"{label} · PC-{x.id}", ""
            sent += 1
        except Exception as e:
            # A plain refusal after Zoho was checked is clear; anything unclear stays in doubt.
            x.zoho_status = "approved"
            x.zoho_err = fail_text(e)
            failed.append({"id": x.id, "why": x.zoho_err})
        db.commit()
    return sent, failed


def push_loan(db, l, emp):
    """A loan paid out of the bank or cash: Employee Advance up, the bank or cash down."""
    src = "ADCB" if l.paid_from == "ADCB" else "Cash"
    ea, frm = account_id(db, "Employee Advance"), account_id(db, src)
    if not ea or not frm:
        raise ZohoError(400, f"Zoho has no account named {'Employee Advance' if not ea else src}")
    ref = f"LN-{l.id}"
    who = f"{emp.emp_no} {emp.name}" if emp else ""
    amt = round(l.amount or 0, 2)
    desc = f"Staff loan / advance - {who}"[:100]
    d = call(db, "POST", "journals", body={"journal_date": l.taken_on.isoformat(), "reference_number": ref, "notes": desc,
                                            "line_items": [{"account_id": ea, "debit_or_credit": "debit", "amount": amt, "description": desc},
                                                           {"account_id": frm, "debit_or_credit": "credit", "amount": amt, "description": desc}]})
    return f"journal:{d['journal']['journal_id']}"


def check_deleted(db, force=False):
    """A line deleted in Zoho is cancelled in the portal, with the reason
    shown. Checked at most every 30 minutes."""
    if not connected(db):
        return 0
    last = float(_get(db, "last_check", "0") or 0)
    if not force and time.time() - last < 1800:
        return 0
    _put(db, "last_check", str(time.time()))
    n = 0
    lines = (list(db.query(models.PettyCash).filter(models.PettyCash.zoho_status == "sent", models.PettyCash.zoho_id != "").limit(400))
             + list(db.query(models.BankEntry).filter(models.BankEntry.zoho_status == "sent", models.BankEntry.zoho_id != "").limit(400)))
    for x in lines:
        kind, _, zid = (x.zoho_id or "").partition(":")
        path = {"expense": "expenses", "journal": "journals", "banktransaction": "banktransactions",
                "vendorpayment": "vendorpayments", "customerpayment": "customerpayments"}.get(kind)
        if not path:
            continue
        try:
            call(db, "GET", f"{path}/{zid}")
        except ZohoError as e:
            if e.code == 404 or "not exist" in e.msg.lower() or "does not" in e.msg.lower():
                x.zoho_status = "cancelled"
                x.zoho_err = f"Deleted in Zoho ({datetime.now(timezone.utc):%d %b %Y})"
                n += 1
        except Exception:
            break
    db.commit()
    return n


# ---- connect -------------------------------------------------------------

@router.get("/store/zoho/link/status")
def status(db: Session = Depends(get_db), user: models.User = ZG):
    out = {"connected": connected(db), "has_keys": bool(_get(db, "client_id") and _get(db, "client_secret")),
           "org": org(db), "org_name": _get(db, "org_name"), "by": _get(db, "connected_by"), "at": _get(db, "connected_at"),
           "redirect": REDIRECT, "home": PUBLIC}
    return out


@router.post("/store/zoho/link/keys")
def keys(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = ZG):
    """The Client ID and Secret from Zoho's API console (a Server-based
    Application with the portal's address as its redirect)."""
    cid, sec = str(payload.get("client_id") or "").strip(), str(payload.get("client_secret") or "").strip()
    if not cid.startswith("1000.") or len(sec) < 20:
        raise HTTPException(status_code=400, detail="Paste the Client ID (starts with 1000.) and the Client Secret from Zoho's API console.")
    _put(db, "client_id", cid)
    _put(db, "client_secret", _lock(sec))
    M.log_action(db, user.id, "zoho_keys", "Zoho API client saved")
    return {"ok": True}


@router.post("/store/zoho/link/start")
def start(db: Session = Depends(get_db), user: models.User = ZG):
    """The address of Zoho's 'allow the portal' page."""
    if not (_get(db, "client_id") and _get(db, "client_secret")):
        raise HTTPException(status_code=400, detail="Save the Client ID and Secret first.")
    state = secrets.token_urlsafe(24)
    _put(db, "oauth_state", f"{state}|{user.id}|{int(time.time())}")
    q = {"scope": SCOPE, "client_id": _get(db, "client_id"), "response_type": "code", "access_type": "offline",
         "prompt": "consent", "redirect_uri": REDIRECT, "state": state}
    return {"url": _accounts_host(db) + "/oauth/v2/auth?" + urllib.parse.urlencode(q)}


@router.get("/store/zoho/link/callback")
def callback(request: Request, code: str = "", state: str = "", error: str = "", db: Session = Depends(get_db)):
    back = PUBLIC + "/?p=accounts#zoho"
    saved = (_get(db, "oauth_state") or "||0").split("|")
    if error or not code or not state or state != saved[0] or time.time() - float(saved[2] or 0) > 900:
        return RedirectResponse(back + "&zoho=refused")
    host = request.query_params.get("accounts-server") or _accounts_host(db)
    if not host.startswith("https://accounts.zoho."):
        return RedirectResponse(back + "&zoho=refused")
    d = _post_form(host + "/oauth/v2/token", {"code": code, "client_id": _get(db, "client_id"),
                                             "client_secret": _unlock(_get(db, "client_secret")),
                                             "redirect_uri": REDIRECT, "grant_type": "authorization_code"})
    if not d.get("refresh_token"):
        return RedirectResponse(back + "&zoho=refused")
    _put(db, "accounts_host", host)
    _put(db, "api_host", d.get("api_domain") or "https://www.zohoapis.com")
    _put(db, "refresh", _lock(d["refresh_token"]))
    _put(db, "oauth_state", "")
    _TOKEN.update(value=d.get("access_token") or "", until=time.time() + int(d.get("expires_in") or 3600))
    _CACHE.clear()
    try:
        orgs = call(db, "GET", "organizations", {"organization_id": ""}).get("organizations", [])
        mine = next((o for o in orgs if str(o.get("organization_id")) == ORG_DEFAULT), None)   # never another org
        if mine:
            _put(db, "org", str(mine["organization_id"]))
            _put(db, "org_name", mine.get("name") or "")
    except Exception:
        pass
    uid = int(saved[1] or 0)
    u = db.get(models.User, uid) if uid else None
    _put(db, "connected_by", (u.full_name or u.username) if u else "")
    _put(db, "connected_at", datetime.now(timezone.utc).isoformat())
    if u:
        M.log_action(db, u.id, "zoho_connect", f"Zoho Books connected ({_get(db, 'org_name') or org(db)})")
    return RedirectResponse(back + "&zoho=connected")


@router.post("/store/zoho/link/disconnect")
def disconnect(db: Session = Depends(get_db), user: models.User = ZG):
    _put(db, "refresh", "")
    _TOKEN.update(value="", until=0)
    _CACHE.clear()
    M.log_action(db, user.id, "zoho_disconnect", "Zoho Books disconnected")
    return {"ok": True}


@router.get("/store/zoho/link/test")
def test(db: Session = Depends(get_db), user: models.User = ZG):
    """Reads the accounts the portal will post to - proves the link and
    shows any name Zoho does not have."""
    import zohosync
    hit = _CACHE.get("chart")                      # read Zoho fresh - but not twice a minute
    if hit and 3600 - (hit[0] - time.time()) > 120:
        _CACHE.pop("chart", None)
    try:
        chart(db)                                  # one read; if Zoho is busy, stop here
    except ZohoError as e:
        return {"ok": False, "busy": True, "why": e.msg[:200]}
    t0 = time.time()
    names = sorted(set(BOOK_ACCOUNT.values()) | set(TRANSFER_TO.values()) | {"ADCB", "Cash", "Employee Advance"})
    acc = [a for g in zohosync.GROUPS for a in g["accounts"] if a not in SOURCE_ACC and a not in TRANSFER_TO
           and not a.startswith("Employee Advance") and a != "Client payment received in cash"]
    missing, unknown, later = [], [], []
    for group, out in ((names, missing), (acc, unknown)):
        for n in group:
            if time.time() - t0 > 25:              # always answer; the rest next press
                later.append(n); continue
            try:
                if not account_id(db, n):
                    out.append(n)
            except ZohoError:
                later.append(n)                    # Zoho busy: not checked, not "missing"
    return {"ok": True, "missing_boxes": missing, "accounts_not_in_zoho": unknown, "not_checked": later,
            "found": len(names) + len(acc) - len(missing) - len(unknown) - len(later), "projects": len(projects(db))}

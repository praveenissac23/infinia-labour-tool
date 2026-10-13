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
ALIAS = {"authority payments": "authority payment", "parking fees and fines": "parkin fees and fines",
         "10. painting works & false ceiling": "10. painting works & false ceiling"}

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


def call(db, method, path, params=None, body=None):
    """One Books API call. Returns Zoho's JSON; raises with Zoho's own
    message when it refuses."""
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


def chart(db):
    """Every Zoho account by its folded name."""
    def fetch():
        out, page = {}, 1
        while page < 15:
            d = call(db, "GET", "chartofaccounts", {"page": page, "per_page": 200, "filter_by": "AccountType.Active"})
            for a in d.get("chartofaccounts", []):
                out.setdefault(_norm(a["account_name"]), a["account_id"])
            if not d.get("page_context", {}).get("has_more_page"):
                break
            page += 1
        return out
    return _cached(db, "chart", fetch)


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


def account_id(db, name):
    """The Zoho account for an account picked in the portal - the last
    part of "Head › Sub-head", or the office account's name."""
    leaf = name.split(" › ")[-1].strip()
    c = chart(db)
    k = _norm(leaf)
    return c.get(k) or c.get(ALIAS.get(k, "")) or ""


# ---- one line into Zoho ----------------------------------------------------

def push(db, x):
    """Send one approved petty cash line. Returns (zoho_id, label) - e.g.
    ("expense:7373...", "Expense") - or raises ZohoError / HTTPException."""
    book = x.book or "site"
    acc = x.zoho_account or ""
    ref = f"PC-{x.id}"
    desc = (x.description or "")[:90] + (f" · {x.supplier}"[:40] if x.supplier else "")
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
        if not src:
            raise ZohoError(400, "Client cash is a customer payment - record it in Zoho against the invoice")
        sid = need(src)
        if book in DIRECTOR:
            # Repaid to the director: less owed to him, out of the bank/box.
            return journal(box, sid)
        if src in CASHLIKE:
            return transfer(sid, box)
        return journal(box, sid)
    if acc in TRANSFER_TO:
        to = need(TRANSFER_TO[acc])
        return journal(to, box) if book in DIRECTOR else transfer(box, to)
    if acc.startswith("Employee Advance"):
        return journal(need("Employee Advance"), box)
    body = {"account_id": need(acc), "date": date, "amount": amt, "paid_through_account_id": box,
            "reference_number": ref, "description": desc, "is_inclusive_tax": True}
    if x.site:
        p = projects(db).get(x.site.strip())
        if p:
            body["project_id"], body["customer_id"] = p
    if x.vat:
        t = vat_tax(db)
        if t:
            body["tax_id"] = t
        body["tax_treatment"] = "vat_registered"
        if x.trn:
            body["tax_reg_no"] = x.trn
    d = call(db, "POST", "expenses", body=body)
    return f"expense:{d['expense']['expense_id']}", "Expense"


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
                ("banktransactions", "banktransactions", "transaction_id", "reference_number")]


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
    missing = [n for n in set(BOOK_ACCOUNT.values()) | set(TRANSFER_TO.values()) | {"ADCB", "Cash", "Employee Advance"}
               if not account_id(db, n)]
    acc = [a for g in zohosync.GROUPS for a in g["accounts"] if a not in SOURCE_ACC and a not in TRANSFER_TO
           and not a.startswith("Employee Advance") and a != "Client payment received in cash"]
    unknown = [a for a in acc if not account_id(db, a)]
    return {"ok": True, "missing_boxes": missing, "accounts_not_in_zoho": unknown, "projects": len(projects(db))}

"""Accounts > Credentials: the company's logins in one place.

Website or app, username and password - or only a PIN, or a note. The
password, PIN and notes are kept encrypted (Fernet, from the
`cryptography` package the server already has); the key is a file on the
server, not in the database, so a copy of the database or a backup alone
does not give the passwords away. Keep a copy of that key file somewhere
safe: without it the stored passwords cannot be read back.

The logo is fetched from the net once, when a login is saved, and kept
with it - nobody's browser goes out to look for it each time the page
opens.

Who: the accounts_credentials right - admin, the PRO and the chief
accountant. Every password shown or copied is in the activity log, and
when it is not the admin, the admin is told (watch.py).
"""
import base64
import os
import re
import secrets
import string
import urllib.request
from datetime import datetime
from html import unescape
from urllib.parse import urlparse, quote

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import Session

import main as M
import models, auth
from database import Base, get_db

RIGHT = "accounts_credentials"
router = APIRouter()
CR = Depends(M.require_screen(RIGHT))
CATEGORIES = ["Bank", "Government", "Utilities", "Suppliers", "Email & IT", "Other"]
KINDS = ("login", "pin", "note")


class Credential(Base):
    __tablename__ = "credentials"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    url = Column(String, default="")
    domain = Column(String, default="")
    kind = Column(String, default="login")
    category = Column(String, default="Other")
    username = Column(String, default="")
    secret = Column(Text, default="")        # encrypted
    notes = Column(Text, default="")         # encrypted
    logo = Column(Text, default="")          # data: URI, fetched once
    admin_only = Column(Boolean, default=False)   # hidden from everyone but an admin
    created_by = Column(Integer, nullable=True)
    updated_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---- the key and the lock ------------------------------------------------------

def _key_path():
    """data/credentials.key beside the app - never in git (data/ is ignored),
    never in the database or its backups."""
    p = os.environ.get("INFINIA_CRED_KEY_FILE")
    if p:
        return p
    d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "credentials.key")


def _fernet():
    from cryptography.fernet import Fernet
    p = _key_path()
    if not os.path.exists(p):
        k = Fernet.generate_key()
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(k)
    with open(p, "rb") as f:
        return Fernet(f.read().strip())


def lock(text):
    return _fernet().encrypt(text.encode()).decode() if text else ""


def unlock(token):
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except Exception:
        raise HTTPException(status_code=500, detail="This password cannot be read - the key file on the server is not the one it was saved with.")


# ---- the website: name and logo --------------------------------------------------

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"


def domain_of(url):
    u = (url or "").strip()
    if not u:
        return ""
    if "://" not in u:
        u = "https://" + u
    try:
        h = (urlparse(u).hostname or "").lower()
    except ValueError:
        return ""
    return h[4:] if h.startswith("www.") else h


def _get(url, limit=400_000, timeout=5):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(limit), (r.headers.get("Content-Type") or "").split(";")[0].strip()


def _image(data, ctype):
    if not data or len(data) < 100:
        return ""
    if not ctype.startswith("image/"):
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            ctype = "image/png"
        elif data[:4] == b"\x00\x00\x01\x00":
            ctype = "image/x-icon"
        elif data[:3] == b"\xff\xd8\xff":
            ctype = "image/jpeg"
        elif b"<svg" in data[:300]:
            ctype = "image/svg+xml"
        else:
            return ""
    return f"data:{ctype};base64," + base64.b64encode(data).decode()


def fetch_logo(domain):
    """The site's logo, as a data: URI. Tried in order: the icon services
    that keep a clean 128px icon for nearly every site, then the site's
    own icon. '' when nothing is found - the page shows a letter."""
    if not domain:
        return ""
    tries = [f"https://www.google.com/s2/favicons?domain={quote(domain)}&sz=128",
             f"https://icons.duckduckgo.com/ip3/{quote(domain)}.ico",
             f"https://{domain}/apple-touch-icon.png",
             f"https://{domain}/favicon.ico"]
    for u in tries:
        try:
            data, ctype = _get(u, limit=200_000, timeout=4)
        except Exception:
            continue
        # Google answers with a plain globe when it has nothing (a 16px
        # image, a few hundred bytes): not a logo.
        if "google.com/s2" in u and len(data) < 700:
            continue
        img = _image(data, ctype)
        if img:
            return img
    return ""


def fetch_title(url):
    try:
        u = url if "://" in url else "https://" + url
        data, _ = _get(u, limit=120_000, timeout=4)
    except Exception:
        return ""
    m = re.search(rb"<title[^>]*>(.*?)</title>", data, re.I | re.S)
    if not m:
        return ""
    t = unescape(m.group(1).decode("utf-8", "ignore")).strip()
    t = re.split(r"\s+[|\-–—:]\s+", t)[0].strip()
    return t[:60] if len(t) >= 2 and not re.match(r"(?i)^(log ?in|sign ?in|home|welcome)$", t) else ""


def name_from_domain(domain):
    if not domain:
        return ""
    parts = domain.split(".")
    core = parts[-3] if len(parts) >= 3 and parts[-2] in ("co", "gov", "com", "net", "org", "ac") else parts[-2] if len(parts) >= 2 else parts[0]
    return core.replace("-", " ").title()


# ---- endpoints -------------------------------------------------------------------

def _is_admin(user):
    return getattr(user, "role", "") == "admin"


def _visible(db, user):
    q = db.query(Credential)
    return q if _is_admin(user) else q.filter(Credential.admin_only != True)  # noqa: E712


def _get_or_404(db, cid, user):
    c = db.get(Credential, cid)
    if not c or (c.admin_only and not _is_admin(user)):
        raise HTTPException(status_code=404, detail="That login is no longer on file.")
    return c


def _row(c, user):
    return {"id": c.id, "name": c.name, "url": c.url, "domain": c.domain, "kind": c.kind,
            "category": c.category, "username": c.username, "has_secret": bool(c.secret),
            "has_notes": bool(c.notes), "logo": c.logo or "", "admin_only": bool(c.admin_only),
            "updated_at": (c.updated_at or c.created_at).isoformat() if (c.updated_at or c.created_at) else ""}


@router.get("/employees/accounts/credentials")
def list_credentials(db: Session = Depends(get_db), user: models.User = CR):
    rows = _visible(db, user).order_by(Credential.name).all()
    return {"rows": [_row(c, user) for c in rows], "categories": CATEGORIES, "admin": _is_admin(user)}


@router.get("/employees/accounts/credentials/lookup")
def lookup_site(url: str, user: models.User = CR):
    """Name and logo for a website being typed in - before it is saved."""
    d = domain_of(url)
    if not d:
        return {"domain": "", "name": "", "logo": ""}
    return {"domain": d, "name": fetch_title(url) or name_from_domain(d), "logo": fetch_logo(d)}


@router.get("/employees/accounts/credentials/generate")
def generate(user: models.User = CR):
    abc = string.ascii_letters + string.digits
    while True:
        p = "".join(secrets.choice(abc) for _ in range(12)) + secrets.choice("!@#$%&*?") + secrets.choice(string.digits)
        if any(c.isupper() for c in p) and any(c.islower() for c in p):
            return {"password": p}


def _clean(payload, c=None):
    name = (payload.get("name") or "").strip()
    url = (payload.get("url") or "").strip()
    d = domain_of(url)
    if not name:
        name = name_from_domain(d)
    if not name:
        raise HTTPException(status_code=400, detail="Give it a name (or the website).")
    kind = payload.get("kind") if payload.get("kind") in KINDS else "login"
    cat = payload.get("category") if payload.get("category") in CATEGORIES else "Other"
    return {"name": name[:80], "url": url[:300], "domain": d, "kind": kind, "category": cat,
            "username": (payload.get("username") or "").strip()[:200]}


@router.post("/employees/accounts/credentials")
def add_credential(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = CR):
    f = _clean(payload)
    c = Credential(**f, secret=lock(payload.get("secret") or ""), notes=lock((payload.get("notes") or "").strip()),
                   created_by=user.id, updated_by=user.id, admin_only=bool(payload.get("admin_only")) and _is_admin(user))
    c.logo = payload.get("logo") if str(payload.get("logo") or "").startswith("data:image/") else fetch_logo(c.domain)
    db.add(c); db.commit()
    M.log_action(db, user.id, "credential_added", f"{c.name} ({c.domain or c.kind})")
    return _row(c, user)


@router.put("/employees/accounts/credentials/{cid}")
def edit_credential(cid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = CR):
    c = _get_or_404(db, cid, user)
    old_domain = c.domain
    what = []
    for k, v in _clean(payload, c).items():
        if getattr(c, k) != v and k != "domain":
            what.append(k)
        setattr(c, k, v)
    if "secret" in payload and payload["secret"] is not None:
        if (payload.get("secret") or "") != unlock(c.secret):
            what.append("password")
        c.secret = lock(payload.get("secret") or "")
    if "notes" in payload and payload["notes"] is not None:
        c.notes = lock((payload.get("notes") or "").strip())
    if _is_admin(user) and "admin_only" in payload:
        c.admin_only = bool(payload.get("admin_only"))
    if str(payload.get("logo") or "").startswith("data:image/"):
        c.logo = payload["logo"]
    elif c.domain != old_domain or not c.logo:
        c.logo = fetch_logo(c.domain)
    c.updated_by = user.id
    db.commit()
    M.log_action(db, user.id, "credential_changed", f"{c.name}: {', '.join(what) or 'saved'}")
    return _row(c, user)


@router.delete("/employees/accounts/credentials/{cid}")
def delete_credential(cid: int, db: Session = Depends(get_db), user: models.User = CR):
    c = _get_or_404(db, cid, user)
    name = c.name
    db.delete(c); db.commit()
    M.log_action(db, user.id, "credential_deleted", name)
    return {"ok": True}


@router.post("/employees/accounts/credentials/{cid}/reveal")
def reveal(cid: int, payload: dict = Body(default={}), db: Session = Depends(get_db), user: models.User = CR):
    """The password (and notes) of one login - shown or copied. Logged."""
    c = _get_or_404(db, cid, user)
    how = "copied" if (payload or {}).get("how") == "copy" else "shown"
    M.log_action(db, user.id, "credential_shown", f"{c.name} - {'PIN' if c.kind == 'pin' else 'password'} {how}")
    return {"secret": unlock(c.secret), "notes": unlock(c.notes)}


# ---- the list on paper: never the passwords ----------------------------------------

def _parts(db, cat="", user=None):
    rows = _visible(db, user).order_by(Credential.category, Credential.name).all()
    if cat:
        rows = [c for c in rows if c.category == cat]
    out = [{"Sr.": i, "Name": c.name, "Category": c.category, "Website": c.url or c.domain or "-",
            "Type": {"login": "Login", "pin": "PIN", "note": "Note"}.get(c.kind, c.kind),
            "Username": c.username or "-", "Password / PIN": unlock(c.secret) or "-",
            "Notes": unlock(c.notes) or "", **({"Admin only": "Yes" if c.admin_only else ""} if _is_admin(user) else {})}
           for i, c in enumerate(rows, 1)]
    sub = (f"{len(out)} logins{(' - ' + cat) if cat else ''}   |   CONFIDENTIAL - contains passwords   |   "
           f"As at {M._dubai_today():%d %b %Y}")
    return out, "Credentials", sub


def _reader(token, db):
    u = auth.get_download_user_from_token(token, db)
    if RIGHT not in M.effective_permissions(u):
        raise HTTPException(status_code=403, detail="Credentials are for admin, the PRO and the chief accountant.")
    return u


@router.get("/export/accounts/credentials")
def export_credentials(token: str, format: str = "pdf", cat: str = "", db: Session = Depends(get_db)):
    u = _reader(token, db)
    rows, title, sub = _parts(db, cat, u)
    M.log_action(db, u.id, "credentials_exported", f"{len(rows)} logins with passwords - {'Excel' if format == 'excel' else 'PDF'}{(' - ' + cat) if cat else ''}")
    return M._hr_file(title, rows, sub, format, [], "Credentials", totals=[])


@router.get("/export/accounts/credentials/view")
def view_credentials(token: str, cat: str = "", db: Session = Depends(get_db)):
    u = _reader(token, db)
    t = quote(auth.create_view_token(u.username), safe="")
    rows, title, sub = _parts(db, cat, u)
    M.log_action(db, u.id, "credentials_exported", f"{len(rows)} logins with passwords - preview{(' - ' + cat) if cat else ''}")
    url = f"/export/accounts/credentials?token={t}&cat={quote(cat)}"
    return M._preview_page(title, sub, rows, url, url, money_cols=[], total_cols=[])


def grant_once(db):
    """The PRO and the chief accountant roles (and their logins) get the
    tab, once. After that it is ticked on Settings > Access like any other."""
    if db.query(models.Setting).filter(models.Setting.key == "credentials_granted").first():
        return
    try:
        import tabrights
        leaf = "accounts.credentials" if tabrights.is_leaf("accounts.credentials") else None
    except Exception:
        leaf = None
    names = []
    for r in db.query(models.AccessRole).all():
        if (r.name or "").strip().lower() not in ("pro", "chief accountant"):
            continue
        keys = [x for x in (r.screens or "").split(",") if x]
        add = [RIGHT] + ([leaf] if leaf and any("." in k for k in keys) else [])
        r.screens = ",".join(keys + [a for a in add if a not in keys])
        names.append(r.name)
        for u in db.query(models.User).filter(models.User.access_role_id == r.id).all():
            uk = [x for x in (u.permissions or "").split(",") if x]
            add = [RIGHT] + ([leaf] if leaf and any("." in k for k in uk) else [])
            u.permissions = ",".join(uk + [a for a in add if a not in uk])
    db.add(models.Setting(key="credentials_granted", value="1"))
    db.commit()
    if names:
        print("Credentials tab given to: " + ", ".join(names))

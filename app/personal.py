"""Personal space (24/11/2026, owner): a private "never forget" list - tasks, reminders with a phone notification,
calendar and notes - for an admin's own personal and work things. Phone first, opened from a Home Screen icon.

Who can open it
  * Admins only, and each one sees only their own items (user_id on every row) - nobody else's, not even another
    admin's.
  * At its own secret address: /portal/me.html?k=<slug>. The slug is made once per person (Settings > General >
    My personal space) and every call must carry it.
  * A new phone or computer signs in once with the person's own login and their PIN (set the first time); it then
    gets a device key of its own and stays signed in. Five wrong PINs lock it for 15 minutes. A device can be
    signed out from the page; the key is stored only as a hash.

Reminders
  * An item with remind_at is pushed to the devices turned on for the personal space (their own subscriptions, made
    by a service worker of the page's own, /portal/me-sw.js - so the work app's notifications and these never share
    one) at that minute, any hour - the person set it.
  * Several server processes may run the loop: the reminder is claimed with one UPDATE ... WHERE reminded_at IS
    NULL, so it goes once.

Times are Dubai time on the screen; stored as naive Dubai times (due_on + due_time, remind_at) - the server compares
with the Dubai clock (UTC + 4, no summer time).
"""
import calendar as _cal
import hashlib
import json
import os
import re
import secrets
import threading
import time
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import Boolean, Column, Date, DateTime, Integer, String, Text, update
from sqlalchemy.orm import Session

import auth
import models
from database import Base, get_db

router = APIRouter()

PIN_TRIES, PIN_LOCK_MIN = 5, 15
KINDS = ("task", "note", "event")
TAGS = ("personal", "work")
REPEATS = ("", "daily", "weekly", "monthly", "yearly")


def dubai_now() -> datetime:
    return datetime.utcnow() + timedelta(hours=4)


# ---- tables ----------------------------------------------------------------------------------------------------------

class PersonalSettings(Base):
    __tablename__ = "personal_settings"
    user_id = Column(Integer, primary_key=True)
    slug = Column(String, unique=True, nullable=False)
    pin_hash = Column(String, default="")
    pin_tries = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PersonalDevice(Base):
    __tablename__ = "personal_devices"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True, nullable=False)
    token_hash = Column(String, unique=True, nullable=False)
    label = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, nullable=True)
    revoked = Column(Boolean, default=False)


class PersonalItem(Base):
    __tablename__ = "personal_items"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True, nullable=False)
    kind = Column(String, default="task")          # task / note / event
    title = Column(Text, default="")
    body = Column(Text, default="")
    tag = Column(String, default="personal")       # personal / work
    due_on = Column(Date, nullable=True)
    due_time = Column(String, default="")          # "HH:MM", Dubai; empty = any time that day
    remind_at = Column(DateTime, nullable=True)    # Dubai time - the next ring
    remind_before = Column(Integer, nullable=True)  # minutes before the date/time; kept so a repeat rings every time
    base_day = Column(Integer, nullable=True)       # the day of the month it was set for (31st stays 31st after Feb)
    reminded_at = Column(DateTime, nullable=True)
    repeat = Column(String, default="")            # daily / weekly / monthly / yearly
    pinned = Column(Boolean, default=False)
    pos = Column(Integer, nullable=True)            # the place it was dragged to (25/11/2026); empty = in time order
    done_at = Column(DateTime, nullable=True)
    deleted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class PersonalPush(Base):
    __tablename__ = "personal_push"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True, nullable=False)
    endpoint = Column(Text, unique=True, nullable=False)
    device_id = Column(Integer, nullable=True, index=True)   # signed out = its notifications stop too
    p256dh = Column(Text, default="")
    auth = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    last_ok = Column(DateTime, nullable=True)


def create_tables(engine):
    for t in (PersonalSettings, PersonalDevice, PersonalItem, PersonalPush):
        t.__table__.create(bind=engine, checkfirst=True)
    # columns added after the tables were first made (personal_items.pos, 25/11/2026) - empty for every old row
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    for t in (PersonalItem,):
        have = {c["name"] for c in insp.get_columns(t.__tablename__)}
        for col in t.__table__.columns:
            if col.name not in have:
                with engine.begin() as cx:
                    cx.execute(text(f'ALTER TABLE {t.__tablename__} ADD COLUMN {col.name} {col.type.compile(engine.dialect)}'))


# ---- who is asking ---------------------------------------------------------------------------------------------------

def _h(token: str) -> str:
    return hashlib.sha256(("infinia-personal:" + (token or "")).encode()).hexdigest()


def _is_admin(user) -> bool:
    return bool(user) and (user.role or "") == "admin" and bool(getattr(user, "active", True))


def _settings_for_slug(db, k: str) -> PersonalSettings:
    s = db.query(PersonalSettings).filter(PersonalSettings.slug == (k or "")).first() if k else None
    if not s:
        raise HTTPException(404, "Not found.")       # nothing said about whether the address exists
    return s


def me(k: str = Query(""), x_personal_device: str = Header(""), db: Session = Depends(get_db)) -> PersonalSettings:
    """The owner of this secret address, when this device holds their key. (s.device_id = the device asking.)"""
    s = _settings_for_slug(db, k)
    d = db.query(PersonalDevice).filter(PersonalDevice.token_hash == _h(x_personal_device),
                                        PersonalDevice.revoked == False).first() if x_personal_device else None  # noqa: E712
    if not d or d.user_id != s.user_id:
        raise HTTPException(401, "Sign in on this device.")
    u = db.get(models.User, s.user_id)
    if not _is_admin(u):
        raise HTTPException(403, "Not available.")
    if not d.last_seen or datetime.utcnow() - d.last_seen > timedelta(minutes=10):
        d.last_seen = datetime.utcnow(); db.commit()
    s.device_id = d.id                       # not a column - who is asking, for this request only
    return s


# ---- set up, sign in once with the PIN -------------------------------------------------------------------------------

@router.post("/users/personal/setup")
def setup(db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    """From the work app (Settings > General): the person's own secret address, made the first time."""
    if not _is_admin(user):
        raise HTTPException(403, "The personal space is for admins.")
    s = db.get(PersonalSettings, user.id)
    if not s:
        s = PersonalSettings(user_id=user.id, slug=secrets.token_urlsafe(12))
        db.add(s); db.commit()
    return {"url": f"/portal/me.html?k={s.slug}", "has_pin": bool(s.pin_hash)}


@router.get("/users/personal/state")
def state(k: str = Query(""), x_personal_device: str = Header(""), db: Session = Depends(get_db)):
    """What the page must ask for: sign in, or nothing (ready)."""
    s = _settings_for_slug(db, k)
    d = db.query(PersonalDevice).filter(PersonalDevice.token_hash == _h(x_personal_device),
                                        PersonalDevice.revoked == False).first() if x_personal_device else None  # noqa: E712
    if d and d.user_id == s.user_id and _is_admin(db.get(models.User, s.user_id)):
        u = db.get(models.User, s.user_id)
        return {"ready": True, "name": (u.full_name or u.username or "").split(" ")[0], "has_pin": bool(s.pin_hash)}
    return {"ready": False, "has_pin": bool(s.pin_hash)}


@router.post("/users/personal/unlock")
def unlock(payload: dict = Body(...), k: str = Query(""), db: Session = Depends(get_db),
           user: models.User = Depends(auth.get_current_user)):
    """A new device: the owner's own login (Bearer) and the PIN - set here the first time. Gives this device its key."""
    s = _settings_for_slug(db, k)
    if user.id != s.user_id or not _is_admin(user):
        raise HTTPException(404, "Not found.")
    now = datetime.utcnow()
    pin = str(payload.get("pin") or "").strip()
    if not re.fullmatch(r"\d{4,6}", pin):
        raise HTTPException(400, "The PIN is 4 to 6 digits.")
    if s.pin_hash:
        # The try is counted before the PIN is checked, in one statement: forty guesses sent at once are forty tries.
        db.execute(update(PersonalSettings).where(PersonalSettings.user_id == s.user_id)
                   .values(pin_tries=PersonalSettings.pin_tries + 1))
        db.commit(); db.refresh(s)
        if s.locked_until and s.locked_until > now:
            mins = int((s.locked_until - now).total_seconds() // 60) + 1
            raise HTTPException(429, f"Too many wrong PINs - try again in {mins} min.")
        if (s.pin_tries or 0) > PIN_TRIES:
            s.locked_until = now + timedelta(minutes=PIN_LOCK_MIN); s.pin_tries = 0; db.commit()
            raise HTTPException(429, f"Too many wrong PINs - locked for {PIN_LOCK_MIN} min.")
        if not auth.verify_password(pin, s.pin_hash):
            left = PIN_TRIES - (s.pin_tries or 0)
            if left <= 0:
                s.locked_until = now + timedelta(minutes=PIN_LOCK_MIN); s.pin_tries = 0; db.commit()
                raise HTTPException(429, f"Too many wrong PINs - locked for {PIN_LOCK_MIN} min.")
            raise HTTPException(401, f"Wrong PIN - {left} tries left.")
    else:
        s.pin_hash = auth.hash_password(pin)
    s.pin_tries, s.locked_until = 0, None
    token = secrets.token_urlsafe(32)
    db.add(PersonalDevice(user_id=user.id, token_hash=_h(token), label=str(payload.get("label") or "")[:80], last_seen=now))
    db.commit()
    return {"device": token}


@router.post("/users/personal/forget-device")
def forget_device(x_personal_device: str = Header(""), s: PersonalSettings = Depends(me), db: Session = Depends(get_db)):
    d = db.query(PersonalDevice).filter(PersonalDevice.token_hash == _h(x_personal_device)).first()
    if d:
        d.revoked = True
        db.query(PersonalPush).filter(PersonalPush.device_id == d.id).delete()
        db.commit()
    return {"ok": True}


@router.get("/users/personal/devices")
def devices(s: PersonalSettings = Depends(me), db: Session = Depends(get_db)):
    rows = db.query(PersonalDevice).filter(PersonalDevice.user_id == s.user_id, PersonalDevice.revoked == False).all()  # noqa: E712
    return {"devices": [{"id": d.id, "label": d.label or "Device", "this": d.id == s.device_id,
                         "since": d.created_at.date().isoformat() if d.created_at else "",
                         "seen": d.last_seen.isoformat(timespec="minutes") if d.last_seen else ""} for d in rows]}


@router.post("/users/personal/sign-out-others")
def sign_out_others(s: PersonalSettings = Depends(me), db: Session = Depends(get_db)):
    """A lost phone: every other device is signed out and its notifications stop."""
    gone = [d.id for d in db.query(PersonalDevice).filter(PersonalDevice.user_id == s.user_id, PersonalDevice.revoked == False,  # noqa: E712
                                                           PersonalDevice.id != s.device_id).all()]
    if gone:
        db.query(PersonalDevice).filter(PersonalDevice.id.in_(gone)).update({"revoked": True}, synchronize_session=False)
        db.query(PersonalPush).filter(PersonalPush.user_id == s.user_id, PersonalPush.device_id.in_(gone)).delete(synchronize_session=False)
    db.query(PersonalPush).filter(PersonalPush.user_id == s.user_id, PersonalPush.device_id == None).delete(synchronize_session=False)  # noqa: E711
    db.commit()
    return {"signed_out": len(gone)}


@router.post("/users/personal/pin")
def change_pin(payload: dict = Body(...), s: PersonalSettings = Depends(me), db: Session = Depends(get_db)):
    old, new = str(payload.get("old") or ""), str(payload.get("new") or "")
    if not re.fullmatch(r"\d{4,6}", new):
        raise HTTPException(400, "The new PIN is 4 to 6 digits.")
    if not auth.verify_password(old, s.pin_hash or ""):
        raise HTTPException(401, "The current PIN is not right.")
    s.pin_hash = auth.hash_password(new); db.commit()
    return {"ok": True}


@router.get("/users/personal/manifest")
def manifest(k: str = Query(""), db: Session = Depends(get_db)):
    """The Home Screen icon opens straight at the secret address, as an app of its own (no browser bar)."""
    s = _settings_for_slug(db, k)
    u = db.get(models.User, s.user_id)
    first = ((u.full_name or u.username or "Me").split(" ")[0]) if u else "Me"
    m = {"name": "Planner", "short_name": "Planner", "id": f"/portal/me.html?k={s.slug}",
         "start_url": f"/portal/me.html?k={s.slug}", "scope": "/portal/", "display": "standalone",
         "background_color": "#F7F3F1", "theme_color": "#F7F3F1",
         "icons": [{"src": "/portal/me-icon-192.png", "sizes": "192x192", "type": "image/png"},
                   {"src": "/portal/me-icon-512.png", "sizes": "512x512", "type": "image/png"}]}
    return Response(json.dumps(m), media_type="application/manifest+json", headers={"Cache-Control": "no-store"})


# ---- quick add: "remind me thursday 10am to call the bank" -----------------------------------------------------------

_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_DAYS_SHORT = {d[:3]: i for i, d in enumerate(_DAYS)} | {"tues": 1, "wed": 2, "thur": 3, "thurs": 3}
_MONTHS = {m.lower(): i for i, m in enumerate(_cal.month_abbr) if m} | {m.lower(): i for i, m in enumerate(_cal.month_name) if m}
WORK_WORDS = r"\b(lpo|ipc|pc|invoice|payroll|site|client|subcontract|zoho|bank|pdc|boq|quotation|proposal|consultant|qs|meeting|tender|salary|labour|staff|project|villa|plot|approve|sign)\b"


# Where a spoken or typed line goes (24/11/2026): three kinds, said the way you would say it.
#   note   "add a note to follow up the BOQ", "note: ...", "follow up with ...", "... to my notes", or nothing timed
#   event  "add a meeting with the client Thursday 3pm", "... to my calendar", "calendar: ...", "meeting with ... <day>"
#   task   (a reminder) "remind me ...", "set a reminder ...", or anything with a day or a time
_P = r"^\s*(?:please\s+|can\s+you\s+|could\s+you\s+)?"
_NOTE_CMD = _P + r"(?:(?:put|add|save|write|keep)\s+(?:this|it|that)\s+(?:in|to|into|on)\s+(?:my\s+|the\s+)?notes?|(?:add|make|create|write|put|save|take|start)\s+(?:a\s+|an\s+|the\s+)?(?:new\s+)?notes?|new\s+note|notes?|ideas?|note\s+down|jot\s+down)\b\s*(?:(?:to|that|saying|says|about|for|on)\b|[:\-])?\s*"
_NOTE_END = r"\s+(?:to|in|on|into)\s+(?:my\s+|the\s+)?notes?\s*[.!]?\s*$"
_EVENT_CMD = _P + r"(?:(?:put|add|save|keep)\s+(?:this|it|that)\s+(?:in|to|into|on)\s+(?:my\s+|the\s+)?(?:calendar|diary)|(?:add|put|schedule|book|set\s+up|create|make)\s+(?:a\s+|an\s+)?(?:new\s+)?(?:calendar\s+)?(?:(event|entry)|(meeting|appointment|call|site\s+visit|visit|lunch|dinner|flight|birthday|anniversary))\b|calendar\b\s*[:\-]?)\s*(?:(?:for|on|called|:)\b|[:\-])?\s*"
_EVENT_END = r"\s+(?:to|in|on|into)\s+(?:my\s+|the\s+)?(?:calendar|diary|schedule)\s*[.!]?\s*$"
_EVENT_WORD = r"^\s*(meeting|appointment|site\s+visit|lunch\s+with|dinner\s+with|flight|interview)\b"
_REM_CMD = _P + r"(?:(?:add|set|create|make)\s+(?:a\s+|an\s+)?(?:new\s+)?reminder|reminder)\b\s*(?:(?:to|for|that|about|on)\b|[:\-])?\s*"


def parse(text: str, now: datetime = None, kind: str = None, here: str = None, day: date = None) -> dict:
    """Read a quick-add line into an item: note, calendar event or reminder; when, what time, repeat, personal or
    work. kind = the section it was said into (its own mic) - then it goes there whatever the words.
    here = the page it was typed or said on (Reminders / Calendar / Notes) - used when the words do not say (25/11/2026).
    day = the day picked on the Calendar when it was typed there - used when the words name no day (26/11/2026)."""
    now = now or dubai_now()
    today = now.date()
    raw = (text or "").strip()
    out = {"kind": "task", "tag": "", "due_on": None, "due_time": "", "repeat": "", "remind": False}
    said = None                                  # the kind the words asked for
    m = re.search(_NOTE_CMD, raw, re.I)
    if m and m.group(0).strip():
        said, raw = "note", raw[m.end():]
    elif re.search(_NOTE_END, raw, re.I):
        said, raw = "note", re.sub(_NOTE_END, "", raw, flags=re.I)
    elif re.match(_P + r"follow[\s-]*up\b", raw, re.I):
        said = "note"                            # "follow up with Anoop on the BOQ" - kept as said
    else:
        m = re.search(_EVENT_CMD, raw, re.I)
        if m and m.group(0).strip():
            noun = m.group(2)
            said, raw = "event", ((noun + " ") if noun else "") + raw[m.end():]
        elif re.search(_EVENT_END, raw, re.I):
            said, raw = "event", re.sub(_EVENT_END, "", raw, flags=re.I)
        else:
            m = re.search(_REM_CMD, raw, re.I)
            if m and m.group(0).strip():
                said, raw, out["remind"] = "task", raw[m.end():], True
    # Only two sections now (25/11/2026): Notes and Calendar. A reminder is a note with a time - so "task" (the old
    # Reminders) is read as a note, and a note that says a day or a time rings then.
    kind = "note" if kind == "task" else kind if kind in KINDS else None
    here = "note" if here == "task" else here if here in KINDS else None
    said = "note" if said == "task" else said
    t = " " + raw + " "

    def cut(pat, fn=None, flags=re.I):
        """Take the match out of the text - unless the reader turned it down (returns False): then the words stay."""
        nonlocal t
        m = re.search(pat, t, flags)
        if m:
            if fn and fn(m) is False:
                return None
            t = t[:m.start()] + " " + t[m.end():]
        return m

    if cut(r"^\s*(note|notes|idea)\s*[:\-]\s*"):
        out["kind"] = "note"                     # a note is kept as written - no dates read out of it
        body = re.sub(r"\s+", " ", t).strip()
        out["title"] = body[:80]
        out["tag"] = "work" if re.search(r"#(work|office)\b", body, re.I) else "personal"
        return out
    cut(r"#(work|office)\b", lambda m: out.update(tag="work"))
    cut(r"#(personal|home|me)\b", lambda m: out.update(tag="personal"))
    if cut(r"^\s*remind\s+me\s*(to\b|about\b|that\b)?"):
        out["remind"] = True
    # a repeat: "every week" anywhere, or "weekly" as the last word ("pay rent monthly") - never "weekly review"
    cut(r"\bevery\s+(day|week|month|year)\b|\b(daily|weekly|monthly|yearly)\b(?=[\s.!]*$)",
        lambda m: out.update(repeat={"day": "daily", "week": "weekly", "month": "monthly", "year": "yearly"}.get(m.group(1) or "", m.group(2) or "")))

    # relative: in 2 hours / in 30 min / in 3 days
    def rel(m):
        n, u = int(m.group(1)), m.group(2).lower()
        if u.startswith("min"):
            w = now + timedelta(minutes=n)
        elif u.startswith("h"):
            w = now + timedelta(hours=n)
        else:
            out["due_on"] = today + timedelta(days=n * (7 if u.startswith("w") else 1)); return
        out["due_on"], out["due_time"], out["remind"] = w.date(), w.strftime("%H:%M"), True
    cut(r"\bin\s+(\d{1,3})\s*(minutes?|mins?|hours?|hrs?|h|days?|weeks?)\b", rel)

    # time: 10am, 10:30, 5.30pm, at 17:00, noon, tonight
    def tm(m):
        h, mi, ap = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
        if ap.startswith("p") and h < 12:
            h += 12
        if ap.startswith("a") and h == 12:
            h = 0
        if not (0 <= h < 24 and 0 <= mi < 60):
            return False
        out["due_time"] = f"{h:02d}:{mi:02d}"
    if not out["due_time"]:
        cut(r"\b(?:at\s+)?(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)(?![a-z])", tm) or \
            cut(r"\b(?:at\s+)(\d{1,2})[:.](\d{2})()\b", tm) or cut(r"\b(\d{1,2}):(\d{2})()\b", tm)
    if cut(r"\bnoon\b|\bmidday\b"):
        out["due_time"] = "12:00"
    if cut(r"\btonight\b"):
        out["due_on"] = out["due_on"] or today
        out["due_time"] = out["due_time"] or "20:00"

    # day
    def wd(m):
        w = (m.group(2) or "").lower()
        i = _DAYS.index(w) if w in _DAYS else _DAYS_SHORT.get(w)
        if i is None:
            return False
        ahead = (i - today.weekday()) % 7
        if ahead == 0 or (m.group(1) or "").strip().lower() == "next":
            ahead = ahead or 7
        out["due_on"] = today + timedelta(days=ahead)
    if not out["due_on"]:
        if cut(r"\b(today)\b"):
            out["due_on"] = today
        elif cut(r"\b(yesterday)\b"):
            out["due_on"] = today - timedelta(days=1)
        elif cut(r"\b(tomorrow|tmrw|tmr)\b"):
            out["due_on"] = today + timedelta(days=1)
        elif cut(r"\bday after tomorrow\b"):
            out["due_on"] = today + timedelta(days=2)
        elif cut(r"\bnext\s+week\b"):
            out["due_on"] = today + timedelta(days=7 - today.weekday())
        elif cut(r"\b(?:on\s+)?(next\s+|this\s+)?(" + "|".join(_DAYS) + r")\b", wd) or \
                cut(r"\b(?:on\s+)?(next\s+|this\s+)?(" + "|".join(sorted(_DAYS_SHORT, key=len, reverse=True)) + r")\b(?=\s*$|\s*#|\s+\d|\s+at\b)", wd) or \
                cut(r"\b(on\s+|next\s+|this\s+)(" + "|".join(sorted(_DAYS_SHORT, key=len, reverse=True)) + r")\b", wd):
            pass        # a short day (sun, sat) only at the end, before a time, or after on/next/this - not "sun cream"
        else:
            def dmy(m):
                d, mo = int(m.group(1)), m.group(2)
                mo = int(mo) if mo.isdigit() else _MONTHS.get(mo.lower()[:3]) or _MONTHS.get(mo.lower())
                y = int(m.group(3)) if m.group(3) else today.year
                if y < 100:
                    y += 2000
                try:
                    dd = date(y, mo, d)
                except (TypeError, ValueError):
                    return False
                if not m.group(3) and dd < today:
                    dd = date(y + 1, mo, d)
                out["due_on"] = dd
            # 28/11 or 28/11/2026, 28-11-2026 - never 1.5 or 12.50 (amounts)
            cut(r"(?<![\d.,])\b(?:on\s+)?(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b(?![.,]\d)", dmy) or \
                cut(r"(?<![\d.,])\b(?:on\s+)?(\d{1,2})-(\d{1,2})-(\d{4})\b", dmy) or \
                cut(r"\b(?:on\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+(jan\w*|feb\w*|mar\w*|apr\w*|may|jun\w*|jul\w*|aug\w*|sep\w*|oct\w*|nov\w*|dec\w*)(?:\s+(\d{4}))?\b", dmy)
    if day and not out["due_on"]:
        out["due_on"] = day                      # "site walk 3pm" typed with Sunday picked = Sunday 15:00
    if out["due_time"] and not out["due_on"]:
        hh, mm = map(int, out["due_time"].split(":"))
        out["due_on"] = today if (hh, mm) > (now.hour, now.minute) else today + timedelta(days=1)
    if out["repeat"] and not out["due_on"]:
        out["due_on"] = today
    title = re.sub(r"\s+", " ", t).strip(" ,.-")
    title = re.sub(r"^(to|about|that|on|at)\s+", "", title, flags=re.I)
    title = re.sub(r"\s+(on|at|by|to)$", "", title, flags=re.I)
    out["title"] = (title[:1].upper() + title[1:]) if title else (text or "").strip()
    if not out["tag"]:
        out["tag"] = "work" if re.search(WORK_WORDS, text or "", re.I) else "personal"
    k = kind or said or here
    if not k:
        k = "event" if re.match(_EVENT_WORD, raw, re.I) and out["due_on"] else "note"   # "meeting with the client Thursday 3pm"
    out["kind"] = k
    if k == "event" and not out["due_on"]:
        out["due_on"] = today
    if out["due_time"] and k == "note":
        out["remind"] = True                     # a time given = ring at that time
    return out


# ---- items -----------------------------------------------------------------------------------------------------------

def _remind_time(due_on, due_time, before_min):
    if not due_on or before_min is None or before_min < 0:
        return None
    hh, mm = (map(int, due_time.split(":")) if due_time else (9, 0))     # all-day: 9 in the morning
    return datetime(due_on.year, due_on.month, due_on.day, hh, mm) - timedelta(minutes=before_min)


def _set_ring(i: PersonalItem):
    """The next ring from the date, time and 'minutes before' - never one already gone (it would ring at once).
    A repeat whose ring has gone rings at its next date instead."""
    new = _remind_time(i.due_on, i.due_time, i.remind_before) if i.remind_before is not None else None
    nowm = dubai_now().replace(second=0, microsecond=0)
    if new and new < nowm:
        if i.repeat and i.due_on:
            d = i.due_on
            for _ in range(800):
                d = _next(d, i.repeat, i.base_day)
                new = _remind_time(d, i.due_time, i.remind_before)
                if new >= nowm:
                    break
        else:
            new = None
    if new != i.remind_at:
        i.remind_at, i.reminded_at = new, None


def _dict(i: PersonalItem) -> dict:
    return {"id": i.id, "kind": i.kind, "title": i.title or "", "body": i.body or "", "tag": i.tag or "personal",
            "due_on": i.due_on.isoformat() if i.due_on else "", "due_time": i.due_time or "",
            "remind_at": i.remind_at.isoformat(timespec="minutes") if i.remind_at else "",
            "remind_before": i.remind_before if i.remind_before is not None else "",
            "reminded": bool(i.reminded_at), "repeat": i.repeat or "", "pinned": bool(i.pinned), "pos": i.pos,
            "done_at": i.done_at.isoformat(timespec="minutes") if i.done_at else "",
            "updated_at": i.updated_at.isoformat(timespec="seconds") if i.updated_at else ""}


def _apply(i: PersonalItem, p: dict):
    if "kind" in p and p["kind"] in KINDS:
        i.kind = p["kind"]
    if "title" in p:
        i.title = str(p["title"] or "").strip()[:500]
    if "body" in p:
        i.body = str(p["body"] or "")[:20000]
    if "tag" in p and p["tag"] in TAGS:
        i.tag = p["tag"]
    if "repeat" in p and (p["repeat"] or "") in REPEATS:
        i.repeat = p["repeat"] or ""
    if "pinned" in p:
        i.pinned = bool(p["pinned"])
    if "due_on" in p:
        try:
            i.due_on = date.fromisoformat(p["due_on"]) if p["due_on"] else None
        except ValueError:
            raise HTTPException(400, "The date is not right.")
        i.base_day = i.due_on.day if i.due_on else None
    if "due_time" in p:
        v = str(p["due_time"] or "")
        if v and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
            raise HTTPException(400, "The time is not right.")
        i.due_time = v
    if "remind_before" in p:                     # minutes before the time; None / "" = no reminder
        rb = p["remind_before"]
        i.remind_before = int(rb) if rb not in (None, "") else None
    if "remind_before" in p or "due_on" in p or "due_time" in p:
        _set_ring(i)
    i.updated_at = datetime.utcnow()
    if i.kind != "note" and not i.title:
        raise HTTPException(400, "Type what it is.")


def _mine(db, s, iid) -> PersonalItem:
    i = db.get(PersonalItem, iid)
    if not i or i.user_id != s.user_id or i.deleted:
        raise HTTPException(404, "Not there any more.")
    return i


@router.get("/users/personal/items")
def items(s: PersonalSettings = Depends(me), db: Session = Depends(get_db)):
    """Everything open, notes, and what was ticked off in the last 30 days."""
    since = datetime.utcnow() - timedelta(days=30)
    rows = db.query(PersonalItem).filter(PersonalItem.user_id == s.user_id, PersonalItem.deleted == False).all()  # noqa: E712
    rows = [r for r in rows if not r.done_at or r.done_at >= since]
    return {"items": [_dict(r) for r in rows], "now": dubai_now().isoformat(timespec="minutes")}


@router.post("/users/personal/quick")
def quick(payload: dict = Body(...), s: PersonalSettings = Depends(me), db: Session = Depends(get_db)):
    """The type-or-speak box: read the line and save it."""
    try:
        day = date.fromisoformat(str(payload.get("day") or "")[:10]) if payload.get("day") else None
    except ValueError:
        day = None
    p = parse(str(payload.get("text") or ""), kind=payload.get("kind") or None, here=payload.get("here") or None, day=day)
    if not p["title"]:
        raise HTTPException(400, "Say or type what it is.")
    i = PersonalItem(user_id=s.user_id)
    title, body = p["title"], ""
    if len(title) > 500:                         # a long note: the rest goes under it, nothing lost
        title, body = title[:500], title[500:]
    _apply(i, {"kind": p["kind"], "title": title, "body": body,
               "tag": p["tag"], "repeat": p["repeat"],
               "due_on": p["due_on"].isoformat() if p["due_on"] else "", "due_time": p["due_time"]})
    when = str(payload.get("due_on") or "")[:10]           # a time picked with one tap beside the box (26/11/2026):
    if when:                                              # it wins over anything the words said
        try:
            date.fromisoformat(when)
        except ValueError:
            raise HTTPException(400, "That date is not a date.")
        p["due_on"] = date.fromisoformat(when)
        p["due_time"] = str(payload.get("due_time") or "")[:5]
        _apply(i, {"due_on": when, "due_time": p["due_time"]})
    if p["due_on"] and p["kind"] in ("task", "note"):
        _apply(i, {"remind_before": 0})          # a note with a date rings then - at 9:00 that morning without a time
    elif p["due_on"] and p["kind"] == "event":
        _apply(i, {"remind_before": 15 if p["due_time"] else 0})   # a meeting rings 15 min before; all day at 9:00
    db.add(i); db.commit()
    return _dict(i)


@router.post("/users/personal/items")
def add_item(payload: dict = Body(...), s: PersonalSettings = Depends(me), db: Session = Depends(get_db)):
    i = PersonalItem(user_id=s.user_id)
    _apply(i, payload)
    db.add(i); db.commit()
    return _dict(i)


@router.put("/users/personal/items/{iid}")
def edit_item(iid: int, payload: dict = Body(...), s: PersonalSettings = Depends(me), db: Session = Depends(get_db)):
    i = _mine(db, s, iid)
    _apply(i, payload)
    db.commit()
    return _dict(i)


def _next(d: date, rep: str, base_day: int = None) -> date:
    """The next date of a repeat. Monthly and yearly keep the day it was set for: the 31st is the 28th in February
    and the 31st again in March."""
    day = base_day or d.day
    if rep == "daily":
        return d + timedelta(days=1)
    if rep == "weekly":
        return d + timedelta(days=7)
    if rep == "monthly":
        y, m = (d.year + (d.month // 12), d.month % 12 + 1)
        return date(y, m, min(day, _cal.monthrange(y, m)[1]))
    if rep == "yearly":
        return date(d.year + 1, d.month, min(day, _cal.monthrange(d.year + 1, d.month)[1]))
    return d


@router.post("/users/personal/items/{iid}/done")
def done(iid: int, s: PersonalSettings = Depends(me), db: Session = Depends(get_db)):
    """Ticked off. A repeating one moves on to its next date instead (its reminder with it)."""
    i = _mine(db, s, iid)
    if i.repeat and i.due_on:
        now = dubai_now()
        at = lambda d: _remind_time(d, i.due_time, 0)            # the date and time itself
        nxt = _next(i.due_on, i.repeat, i.base_day)
        for _ in range(800):                     # ticked late: straight to the next one still to come
            if at(nxt) > now:
                break
            nxt = _next(nxt, i.repeat, i.base_day)
        i.due_on = nxt
        _set_ring(i)
        db.add(PersonalItem(user_id=s.user_id, kind=i.kind, title=i.title, tag=i.tag, done_at=datetime.utcnow(),
                            body="(repeats - moved on)"))
    else:
        i.done_at = datetime.utcnow()
    i.updated_at = datetime.utcnow()
    db.commit()
    return _dict(i)


@router.post("/users/personal/items/{iid}/undone")
def undone(iid: int, s: PersonalSettings = Depends(me), db: Session = Depends(get_db)):
    i = _mine(db, s, iid)
    i.done_at, i.updated_at = None, datetime.utcnow()
    db.commit()
    return _dict(i)


@router.post("/users/personal/items/{iid}/snooze")
def snooze(iid: int, payload: dict = Body(...), s: PersonalSettings = Depends(me), db: Session = Depends(get_db)):
    """Later: +1 hour, this evening, tomorrow morning, next week - the date, time and reminder move together."""
    i = _mine(db, s, iid)
    now = dubai_now().replace(second=0, microsecond=0)
    how = payload.get("how") or "1h"
    # (a repeat keeps its own day and time - only this ring moves)
    if how == "1h":
        w = now + timedelta(hours=1)
    elif how == "evening":
        w = now.replace(hour=19, minute=0) if now.hour < 19 else now + timedelta(hours=1)
    elif how == "tomorrow":
        w = (now + timedelta(days=1)).replace(hour=9, minute=0)
    elif how == "week":
        w = (now + timedelta(days=7 - now.weekday())).replace(hour=9, minute=0)
    else:
        raise HTTPException(400, "Snooze how?")
    if not i.repeat:
        i.due_on, i.due_time = w.date(), w.strftime("%H:%M")
        i.base_day = i.due_on.day
        if i.remind_before is None:
            i.remind_before = 0
    i.remind_at, i.reminded_at, i.updated_at = w, None, datetime.utcnow()
    db.commit()
    return _dict(i)


@router.delete("/users/personal/items/{iid}")
def delete_item(iid: int, s: PersonalSettings = Depends(me), db: Session = Depends(get_db)):
    i = _mine(db, s, iid)
    i.deleted, i.updated_at = True, datetime.utcnow()
    db.commit()
    return {"ok": True}


# ---- move cards like Trello (25/11/2026): the new order of a group, and the day group it was dropped into ---------

@router.post("/users/personal/order")
def reorder(payload: dict = Body(...), s: PersonalSettings = Depends(me), db: Session = Depends(get_db)):
    """ids = the cards of one group in their new order. moved + to = a card dropped into another group:
    'today' / 'tomorrow' gives it that day (its time kept), 'anytime' takes its date and ring away."""
    ids = [int(x) for x in (payload.get("ids") or []) if str(x).isdigit()][:500]
    mine = {i.id: i for i in db.query(PersonalItem).filter(PersonalItem.user_id == s.user_id, PersonalItem.id.in_(ids or [0]),
                                                           PersonalItem.deleted == False).all()}  # noqa: E712
    for k, iid in enumerate(ids):
        if iid in mine:
            mine[iid].pos = k
    moved, to = payload.get("moved"), payload.get("to") or ""
    if moved is not None and to:
        i = mine.get(int(moved)) if str(moved).isdigit() else None
        if not i:
            raise HTTPException(404, "Not there any more.")
        today = dubai_now().date()
        if to == "anytime":
            _apply(i, {"due_on": "", "due_time": "", "repeat": "", "remind_before": ""})
        elif to in ("today", "tomorrow"):
            d = today if to == "today" else today + timedelta(days=1)
            p = {"due_on": d.isoformat(), "remind_before": i.remind_before if i.remind_before is not None else 0}
            if to == "today" and i.due_time and i.due_time <= dubai_now().strftime("%H:%M"):
                p["due_time"] = ""                   # its time has gone today - keep it today, not overdue again
            _apply(i, p)
        else:
            raise HTTPException(400, "Open it to pick a date.")
    db.commit()
    return {"items": [_dict(i) for i in mine.values()]}


# ---- the page's version: a Home Screen app keeps the old page; it asks this and reloads itself when newer ----------

ME_PAGE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "portal", "me.html")
_STAMP_RE = re.compile(r'(<meta name="me-build" content=")[^"]*(")')


def page_stamp(text: str) -> str:
    """Fingerprint of the page without its own stamp (deploy/build_temporary_pages.py writes it into the page)."""
    return hashlib.sha256(_STAMP_RE.sub(r"\1\2", text).encode("utf-8")).hexdigest()[:12]


@router.get("/users/personal/version")
def page_version():
    try:
        m = _STAMP_RE.search(open(ME_PAGE, encoding="utf-8").read())
    except OSError:
        m = None
    return Response(json.dumps({"v": m.group(0).split('content="')[1].rstrip('"') if m else ""}), media_type="application/json",
                    headers={"Cache-Control": "no-store"})


# ---- voice: the phone records, this server writes it out (voice_stt.py) --------------------------------------------

_VOICE_LOCK = threading.Lock()


@router.get("/users/personal/voice")
def voice_ready(s: PersonalSettings = Depends(me)):
    import voice_stt
    return {"ready": voice_stt.ready()}


_VW = {"p": None, "last": 0.0}            # the live speech worker (voice_stt.py --serve), started when first needed


def _worker():
    import subprocess, sys
    import voice_stt
    p = _VW["p"]
    if p is None or p.poll() is not None:
        p = subprocess.Popen([sys.executable, voice_stt.__file__, "--serve", voice_stt.model_dir()],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             env={**os.environ, "OMP_NUM_THREADS": "2"})
        _VW["p"] = p
        if not _read_line(p, 60).get("ready"):
            _stop_worker()
            raise HTTPException(500, "Voice could not start - try again.")
        threading.Thread(target=_reaper, daemon=True).start()
    return p


def _read_line(p, timeout) -> dict:
    import select
    r, _, _ = select.select([p.stdout], [], [], timeout)
    if not r:
        return {}
    line = p.stdout.readline()
    try:
        return json.loads(line or b"{}")
    except ValueError:
        return {}


def _stop_worker():
    p, _VW["p"] = _VW["p"], None
    if p and p.poll() is None:
        try:
            p.stdin.close(); p.wait(5)
        except Exception:
            p.kill()


def _reaper():
    """The model's memory is given back 90 s after the mic was last used."""
    me_p = _VW["p"]
    while _VW["p"] is me_p and me_p is not None:
        time.sleep(15)
        with _VOICE_LOCK:
            if _VW["p"] is me_p and time.time() - _VW["last"] > 90:
                _stop_worker()


def _transcribe(data: bytes, kind: str) -> str:
    import tempfile
    ext = ".webm" if "webm" in kind else ".ogg" if "ogg" in kind else ".wav" if "wav" in kind else ".m4a"
    with _VOICE_LOCK, tempfile.NamedTemporaryFile(suffix=ext) as f:      # one at a time - memory stays small
        f.write(data); f.flush()
        _VW["last"] = time.time()
        p = _worker()
        p.stdin.write((f.name + "\n").encode()); p.stdin.flush()
        out = _read_line(p, 45)
        _VW["last"] = time.time()
        if not out:
            _stop_worker()
            raise HTTPException(504, "That took too long - try again.")
    if "error" in out:
        raise HTTPException(500, "Could not read that recording - try again.")
    return (out.get("text") or "").strip()


@router.post("/users/personal/voice")
async def voice(request: Request, s: PersonalSettings = Depends(me)):
    import voice_stt
    from starlette.concurrency import run_in_threadpool
    if not voice_stt.ready():
        raise HTTPException(503, "voice-off")
    data = await request.body()
    if len(data) < 1000:
        return {"text": ""}
    if len(data) > 6_000_000:
        raise HTTPException(413, "Too long - keep it under 3 minutes.")
    text = await run_in_threadpool(_transcribe, data, request.headers.get("content-type", ""))
    return {"text": text[:500]}


# ---- phone notifications ---------------------------------------------------------------------------------------------

@router.get("/users/personal/push/key")
def push_key(s: PersonalSettings = Depends(me), db: Session = Depends(get_db)):
    import push
    if not push.available():
        raise HTTPException(503, "Notifications are not set up on the server.")
    _, pub = push.vapid_keys(db, models)
    return {"key": pub}


@router.post("/users/personal/push/subscribe")
def push_subscribe(payload: dict = Body(...), s: PersonalSettings = Depends(me), db: Session = Depends(get_db)):
    sub = payload.get("subscription") or {}
    ep, keys = sub.get("endpoint") or "", sub.get("keys") or {}
    if not ep.startswith("https://") or not keys.get("p256dh") or not keys.get("auth"):
        raise HTTPException(400, "That is not a notification address.")
    row = db.query(PersonalPush).filter(PersonalPush.endpoint == ep).first()
    if row and row.user_id != s.user_id:
        db.delete(row); db.flush(); row = None
    if not row:
        row = PersonalPush(user_id=s.user_id, endpoint=ep)
        db.add(row)
    row.p256dh, row.auth, row.device_id = keys["p256dh"], keys["auth"], s.device_id
    db.commit()
    return {"ok": True, "devices": db.query(PersonalPush).filter(PersonalPush.user_id == s.user_id).count()}


@router.post("/users/personal/push/test")
def push_test(s: PersonalSettings = Depends(me), db: Session = Depends(get_db)):
    n = _send(db, s.user_id, {"title": "Reminders are on", "body": "This is how a reminder arrives.",
                              "tag": "me-test", "url": f"/portal/me.html?k={s.slug}"})
    return {"sent": n}


def _send(db, uid, msg) -> int:
    import push
    if not push.available() or os.environ.get("INFINIA_NO_PUSH") == "1":     # the test copy never reaches a phone
        return 0
    key, pub = push.vapid_keys(db, models)
    sent = 0
    for sub in db.query(PersonalPush).filter(PersonalPush.user_id == uid).all():
        try:
            st = push.send(key, pub, sub, msg, ttl=6 * 3600)
        except Exception as e:                    # a broken address: dropped, the others still get it
            print("personal push:", e); db.delete(sub); continue
        if st in (200, 201, 202):
            sub.last_ok = datetime.utcnow(); sent += 1
        elif st in (404, 410):
            db.delete(sub)
    db.commit()
    return sent


def due_reminders(SessionLocal, now: datetime = None) -> int:
    """One round: every reminder whose minute has come and that has not gone yet - claimed, then pushed."""
    now = now or dubai_now()
    db = SessionLocal()
    sent = 0
    try:
        rows = db.query(PersonalItem).filter(PersonalItem.remind_at != None, PersonalItem.remind_at <= now,  # noqa: E711
                                             PersonalItem.reminded_at == None, PersonalItem.done_at == None,  # noqa: E711
                                             PersonalItem.deleted == False).all()  # noqa: E712
        for i in rows:
            r = db.execute(update(PersonalItem).where(PersonalItem.id == i.id, PersonalItem.reminded_at == None)  # noqa: E711
                           .values(reminded_at=now))
            db.commit()
            if r.rowcount != 1:
                continue                          # another server process has it
            if now - i.remind_at > timedelta(hours=12):
                continue                          # the server was off: not rung half a day late (it shows overdue)
            try:
                s = db.get(PersonalSettings, i.user_id)
                when = (i.due_time + " · ") if i.due_time else ""
                sent += _send(db, i.user_id, {"title": i.title or "Reminder", "body": when + ("Work" if i.tag == "work" else "Personal"),
                                              "tag": f"me-{i.id}", "url": f"/portal/me.html?k={s.slug}&open={i.id}" if s else "/"})
            except Exception as e:                # one item failing never holds up the others
                print("personal reminder:", e); db.rollback()
    finally:
        db.close()
    return sent


def start(SessionLocal):
    def run():
        time.sleep(20)
        while True:
            try:
                due_reminders(SessionLocal)
            except Exception as e:                # one bad round never stops the next
                print("personal reminders:", e)
            time.sleep(30)
    threading.Thread(target=run, daemon=True, name="personal-reminders").start()

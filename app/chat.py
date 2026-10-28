"""In-app chat: who is online, one room for everyone, and a private chat between any two people.

    Everyone      - the whole office sees it ("all")
    Private chat  - two people only ("dm:<lower id>-<higher id>")

@mentions: @username (the composer fills it in from the list), and @everyone in the Everyone room.
A private message or a mention also reaches the bell and the phone, like any other notification.

Presence: every open app asks /store/chat/state now and then (every few seconds while the chat is open,
about every 20 seconds otherwise); a person seen in the last 70 seconds is online.
"""
import hashlib
import hmac
import os
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Session

import auth
import models
from database import Base, get_db

router = APIRouter()
ONLINE_FOR = 70          # seconds since a person's app last asked, to count as online
EVERYONE = "all"
# Files, photos and voice messages are not kept: a file lives on the server only while the person who sent it
# has the portal open. When he signs out, closes the portal, or his computer / phone goes off (no word from his
# app for GONE_AFTER seconds), the server removes his files by itself - and in any case after KEEP_HOURS.
# The message stays, saying the file is no longer available.
KEEP_HOURS = int(os.environ.get("INFINIA_CHAT_KEEP_HOURS", "24"))
GONE_AFTER = 180
MAX_FILE = 25 * 1024 * 1024
MAX_VOICE_SECONDS = 300


def _dir():
    p = os.environ.get("INFINIA_CHAT_DIR") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "chat")
    os.makedirs(p, exist_ok=True)
    return p


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True)
    room = Column(String, index=True, nullable=False)
    user_id = Column(Integer, index=True, nullable=False)
    text = Column(Text, default="")
    mentions = Column(Text, default="")              # ",3,7," - the people named with @ (",*," = everyone)
    created_at = Column(DateTime, default=_now, index=True)
    edited_at = Column(DateTime, nullable=True)
    deleted = Column(Boolean, default=False)
    # a file, photo or voice message with it - kept on the server until expires_at, then removed
    file_kind = Column(String, default="")             # file | image | voice
    file_name = Column(String, default="")
    file_path = Column(String, default="")             # on disk, under _dir(); "" once removed
    file_mime = Column(String, default="")
    file_size = Column(Integer, default=0)
    duration = Column(Integer, default=0)              # voice: seconds
    expires_at = Column(DateTime, nullable=True)


class ChatRead(Base):
    """How far a person has read in a room. Room "*" is where everything stood when he first opened the chat
    (so he does not start with the whole history unread)."""
    __tablename__ = "chat_reads"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True, nullable=False)
    room = Column(String, index=True, nullable=False)
    last_id = Column(Integer, default=0)


class ChatSeen(Base):
    __tablename__ = "chat_seen"
    user_id = Column(Integer, primary_key=True)
    last_seen = Column(DateTime, default=_now)


TABLES = [ChatMessage, ChatRead, ChatSeen]


def create_tables(engine):
    for t in TABLES:
        t.__table__.create(bind=engine, checkfirst=True)
    # columns added after the tables were first made
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    for t in TABLES:
        have = {c["name"] for c in insp.get_columns(t.__tablename__)}
        for col in t.__table__.columns:
            if col.name not in have:
                typ = col.type.compile(engine.dialect)
                default = " DEFAULT ''" if typ.upper().startswith(("VARCHAR", "TEXT")) else (" DEFAULT 0" if typ.upper().startswith("INT") else "")
                with engine.begin() as cx:
                    cx.execute(text(f"ALTER TABLE {t.__tablename__} ADD COLUMN {col.name} {typ}{default}"))


# ---- helpers -----------------------------------------------------------------------------------------
def dm_room(a, b):
    a, b = sorted((int(a), int(b)))
    return f"dm:{a}-{b}"


def _in_room(room, uid):
    if room == EVERYONE:
        return True
    m = re.fullmatch(r"dm:(\d+)-(\d+)", room or "")
    return bool(m) and uid in (int(m[1]), int(m[2]))


def _other(room, uid):
    m = re.fullmatch(r"dm:(\d+)-(\d+)", room or "")
    if not m:
        return None
    a, b = int(m[1]), int(m[2])
    return b if a == uid else a


def _name(u):
    return (u.full_name or u.username or "").strip() if u else ""


def _initials(name):
    parts = [p for p in re.split(r"[\s._-]+", name or "") if p]
    return ((parts[0][0] + (parts[1][0] if len(parts) > 1 else "")) if parts else "?").upper()


def _people(db):
    return [u for u in db.query(models.User).filter(models.User.active == True).order_by(models.User.full_name).all()]  # noqa: E712


def _iso(d):
    return (d.replace(tzinfo=timezone.utc).isoformat() if d else None)


def _sig(mid, path):
    return hmac.new(auth.SECRET_KEY.encode(), f"chat:{mid}:{path}".encode(), hashlib.sha256).hexdigest()[:28]


def _msg(m, users):
    u = users.get(m.user_id)
    d = {"id": m.id, "room": m.room, "user_id": m.user_id, "name": _name(u) or "Someone", "initials": _initials(_name(u)),
         "text": "" if m.deleted else (m.text or ""), "deleted": bool(m.deleted), "at": _iso(m.created_at),
         "edited": bool(m.edited_at) and not m.file_kind, "mentions": [int(x) for x in (m.mentions or "").strip(",").split(",") if x.isdigit()],
         "everyone": ",*," in (m.mentions or "")}
    if m.file_kind and not m.deleted:
        # the link carries its own key, so a photo or a voice note plays without signing in again
        d["file"] = {"kind": m.file_kind, "name": m.file_name, "mime": m.file_mime, "size": m.file_size, "duration": m.duration,
                     "until": _iso(m.expires_at), "gone": not m.file_path,
                     "url": f"/store/chat/file/{m.id}/{_sig(m.id, m.file_path)}" if m.file_path else ""}
    return d


def _reads(db, uid):
    rows = {r.room: r for r in db.query(ChatRead).filter(ChatRead.user_id == uid).all()}
    if "*" not in rows:                               # first time: everything before now counts as read
        top = db.query(func.max(ChatMessage.id)).scalar() or 0
        r = ChatRead(user_id=uid, room="*", last_id=top)
        db.add(r); db.commit()
        rows["*"] = r
    return rows


def _unread(db, user, people):
    """{room: count} of messages from others not yet read, and how many of them name this person."""
    reads = _reads(db, user.id)
    base = reads["*"].last_id
    rooms = [EVERYONE] + [dm_room(user.id, p.id) for p in people if p.id != user.id]
    floor = min([reads[r].last_id if r in reads else base for r in rooms] or [base])
    rows = (db.query(ChatMessage.id, ChatMessage.room, ChatMessage.mentions)
              .filter(ChatMessage.id > floor, ChatMessage.room.in_(rooms), ChatMessage.user_id != user.id,
                      ChatMessage.deleted == False).all())  # noqa: E712
    out, mentions = {}, 0
    for mid, room, men in rows:
        if mid <= (reads[room].last_id if room in reads else base):
            continue
        out[room] = out.get(room, 0) + 1
        if room == EVERYONE and (f",{user.id}," in (men or "") or ",*," in (men or "")):
            mentions += 1
    return out, mentions


def _seen(db, user):
    """Note the person as here - written at most every 5 seconds (it is also what turns one tick into two)."""
    s = db.query(ChatSeen).filter(ChatSeen.user_id == user.id).first()
    now = _now()
    if not s:
        db.add(ChatSeen(user_id=user.id, last_seen=now)); db.commit()
    elif not s.last_seen or (now - s.last_seen).total_seconds() > 5:
        s.last_seen = now; db.commit()


# ---- the chat ------------------------------------------------------------------------------------------
@router.get("/store/chat/state")
def chat_state(room: str = "", after: int = 0, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    """Who is here, what is unread - and, for the room open on screen, the messages after `after`."""
    _seen(db, user)
    people = _people(db)
    seen = {s.user_id: s.last_seen for s in db.query(ChatSeen).all()}
    now = _now()
    unread, mentions = _unread(db, user, people)
    users = []
    for p in people:
        ls = seen.get(p.id)
        users.append({"id": p.id, "username": p.username, "name": _name(p), "initials": _initials(_name(p)),
                      "online": bool(ls and (now - ls).total_seconds() <= ONLINE_FOR) or p.id == user.id,
                      "last_seen": _iso(ls), "me": p.id == user.id,
                      "room": EVERYONE if p.id == user.id else dm_room(user.id, p.id)})
    # the last word in each private chat, so the list can be ordered by who spoke last
    last = {}
    dms = [u["room"] for u in users if not u["me"]]
    for r, mid in (db.query(ChatMessage.room, func.max(ChatMessage.id)).filter(ChatMessage.room.in_(dms + [EVERYONE]))
                     .group_by(ChatMessage.room).all()):
        last[r] = mid
    umap0 = {p.id: p for p in people}
    prev = {}
    if last:
        for m in db.query(ChatMessage).filter(ChatMessage.id.in_(list(last.values()))).all():
            prev[m.room] = {"id": m.id, "user_id": m.user_id, "name": _name(umap0.get(m.user_id)), "at": _iso(m.created_at), "deleted": bool(m.deleted),
                            "text": "" if m.deleted else (m.text or "")[:120], "kind": m.file_kind or ""}
    out = {"me": user.id, "users": users, "unread": unread, "mentions": mentions,
           "total": sum(unread.values()), "last": last, "previews": prev}
    if room:
        if not _in_room(room, user.id):
            raise HTTPException(status_code=403, detail="Not your conversation.")
        q = db.query(ChatMessage).filter(ChatMessage.room == room)
        if after:
            q = q.filter(ChatMessage.id > after)
            rows = q.order_by(ChatMessage.id).limit(200).all()
        else:
            rows = list(reversed(q.order_by(ChatMessage.id.desc()).limit(60).all()))
        umap = {p.id: p for p in db.query(models.User).all()}
        out["messages"] = [_msg(m, umap) for m in rows]
        # edits and deletions of messages already on screen
        if after:
            since = now - timedelta(minutes=10)
            out["changed"] = [_msg(m, umap) for m in db.query(ChatMessage).filter(ChatMessage.room == room, ChatMessage.id <= after,
                              ChatMessage.edited_at != None, ChatMessage.edited_at >= since).all()]  # noqa: E711
        out["more"] = (not after) and len(rows) == 60
        out["receipts"] = _receipts(db, room, user, seen)
    return out


def _receipts(db, room, user, seen):
    """For the ticks on my own messages: how far each other person in the room has read, and when his app last
    picked up messages. One tick = on the server; two grey = reached their phone or computer; two blue = read.
    In Everyone, the people counted are those who have opened the chat at least once."""
    other = _other(room, user.id)
    if other is not None:
        who = [other]
    else:
        who = [uid for (uid,) in db.query(ChatRead.user_id).filter(ChatRead.room == "*", ChatRead.user_id != user.id).all()]
        active = {u.id for u in _people(db)}
        who = [u for u in who if u in active]
    if not who:
        return []
    rows = db.query(ChatRead).filter(ChatRead.user_id.in_(who), ChatRead.room.in_([room, "*"])).all()
    read, base = {}, {}
    for r in rows:
        (base if r.room == "*" else read)[r.user_id] = r.last_id or 0
    return [{"user_id": u, "read": max(read.get(u, 0), base.get(u, 0)), "seen": _iso(seen.get(u))} for u in who]


@router.get("/store/chat/history")
def chat_history(room: str, before: int, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    if not _in_room(room, user.id):
        raise HTTPException(status_code=403, detail="Not your conversation.")
    rows = list(reversed(db.query(ChatMessage).filter(ChatMessage.room == room, ChatMessage.id < before)
                         .order_by(ChatMessage.id.desc()).limit(60).all()))
    umap = {p.id: p for p in db.query(models.User).all()}
    return {"messages": [_msg(m, umap) for m in rows], "more": len(rows) == 60}


@router.post("/store/chat/send")
def chat_send(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    room = str(payload.get("room") or "")
    text = str(payload.get("text") or "").strip()
    if not _in_room(room, user.id):
        raise HTTPException(status_code=403, detail="Not your conversation.")
    if not text:
        raise HTTPException(status_code=400, detail="Type a message first.")
    if len(text) > 4000:
        raise HTTPException(status_code=400, detail="That message is too long - split it in two.")
    other = _other(room, user.id)
    if other is not None and not db.query(models.User).filter(models.User.id == other, models.User.active == True).first():  # noqa: E712
        raise HTTPException(status_code=400, detail="That login is no longer active.")
    names = {u.username.lower(): u.id for u in _people(db)}
    men = set()
    for tag in re.findall(r"(?<![\w@])@([A-Za-z0-9][\w.\-]*)", text):
        t = tag.lower().rstrip(".-")
        if t in ("everyone", "all", "here") and room == EVERYONE:
            men.add("*")
        elif t in names and names[t] != user.id:
            men.add(str(names[t]))
    m = ChatMessage(room=room, user_id=user.id, text=text, mentions=("," + ",".join(sorted(men)) + ",") if men else "")
    db.add(m); db.commit()
    _mark(db, user.id, room, m.id)
    umap = {p.id: p for p in db.query(models.User).all()}
    return _msg(m, umap)


@router.post("/store/chat/upload")
async def chat_upload(room: str = Form(...), file: UploadFile = File(...), text: str = Form(""), kind: str = Form(""),
                      duration: int = Form(0), db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    """A file, a photo or a voice message - kept only while the sender has the portal open (see GONE_AFTER)."""
    if not _in_room(room, user.id):
        raise HTTPException(status_code=403, detail="Not your conversation.")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="That file is empty.")
    if len(data) > MAX_FILE:
        raise HTTPException(status_code=400, detail=f"That file is {len(data) / 1048576:.0f} MB - up to 25 MB can be sent.")
    mime = (file.content_type or "application/octet-stream").split(";")[0].strip().lower()
    name = os.path.basename(file.filename or "file").strip() or "file"
    if kind != "voice":
        kind = "image" if mime in ("image/jpeg", "image/png", "image/gif", "image/webp") else "file"
    ext = os.path.splitext(name)[1].lower()[:10] or {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".m4a", "audio/mpeg": ".mp3"}.get(mime, "")
    ext = re.sub(r"[^.\w]", "", ext)
    path = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(_dir(), path), "wb") as f:
        f.write(data)
    text = (text or "").strip()[:4000]
    names = {u.username.lower(): u.id for u in _people(db)}
    men = {str(names[t.lower()]) for t in re.findall(r"(?<![\w@])@([A-Za-z0-9][\w.\-]*)", text) if t.lower() in names and names[t.lower()] != user.id}
    m = ChatMessage(room=room, user_id=user.id, text=text, mentions=("," + ",".join(sorted(men)) + ",") if men else "",
                    file_kind=kind, file_name=name if kind != "voice" else "Voice message", file_path=path, file_mime=mime,
                    file_size=len(data), duration=max(0, min(int(duration or 0), MAX_VOICE_SECONDS)),
                    expires_at=_now() + timedelta(hours=KEEP_HOURS))
    db.add(m); db.commit()
    _mark(db, user.id, room, m.id)
    return _msg(m, {p.id: p for p in db.query(models.User).all()})


@router.post("/store/chat/bye")
def chat_bye(payload: dict = Body(default={}), db: Session = Depends(get_db)):
    """The portal is closing or signing out: his files go now, and he shows offline. Sent as the page closes
    (navigator.sendBeacon cannot carry a sign-in header, so the sign-in comes in the body)."""
    try:
        user = auth.get_current_user(token=str(payload.get("token") or ""), db=db)
    except Exception:
        return {"ok": False}
    s = db.query(ChatSeen).filter(ChatSeen.user_id == user.id).first()
    if s:
        s.last_seen = _now() - timedelta(seconds=ONLINE_FOR + 1)
        db.commit()
    remove_expired(db, only_user=user.id)
    return {"ok": True}


@router.get("/store/chat/file/{mid}/{sig}")
def chat_file(mid: int, sig: str, dl: int = 0, db: Session = Depends(get_db)):
    m = db.query(ChatMessage).filter(ChatMessage.id == mid).first()
    if not m or m.deleted or not m.file_path or not hmac.compare_digest(sig, _sig(m.id, m.file_path)):
        raise HTTPException(status_code=404, detail="This file is no longer kept.")
    full = os.path.join(_dir(), m.file_path)
    if not os.path.exists(full):
        raise HTTPException(status_code=404, detail="This file is no longer kept.")
    inline = not dl and (m.file_kind in ("image", "voice") or m.file_mime in ("application/pdf",))
    return FileResponse(full, media_type=m.file_mime or "application/octet-stream", filename=m.file_name,
                        content_disposition_type="inline" if inline else "attachment",
                        headers={"Cache-Control": "private, max-age=86400"})


def remove_expired(db, only_user=None):
    """Every file whose sender has left the portal (or whose time is up) comes off the disk; the message stays."""
    n = 0
    now = _now()
    seen = {s.user_id: s.last_seen for s in db.query(ChatSeen).all()}
    q = db.query(ChatMessage).filter(ChatMessage.file_path != "", ChatMessage.file_path.isnot(None))
    if only_user is not None:
        q = q.filter(ChatMessage.user_id == only_user)
    for m in q.all():
        ls = seen.get(m.user_id)
        left = only_user is not None or not ls or (now - ls).total_seconds() > GONE_AFTER
        if not (left or (m.expires_at and m.expires_at <= now)):
            continue
        try:
            os.remove(os.path.join(_dir(), m.file_path))
        except OSError:
            pass
        m.file_path = ""; n += 1
    if n:
        db.commit()
    return n


def start_cleaner(SessionLocal):
    """Runs on the server every 30 seconds - nobody has to have the app open."""
    def loop():
        while True:
            try:
                db = SessionLocal()
                try:
                    k = remove_expired(db)
                    if k:
                        print(f"chat: removed {k} expired file(s)")
                finally:
                    db.close()
            except Exception as e:
                print("chat cleaner:", e)
            time.sleep(30)
    threading.Thread(target=loop, daemon=True, name="chat-cleaner").start()


@router.put("/store/chat/messages/{mid}")
def chat_edit(mid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    m = db.query(ChatMessage).filter(ChatMessage.id == mid).first()
    if not m or m.deleted:
        raise HTTPException(status_code=404, detail="Message not found.")
    if m.user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the person who wrote it can change it.")
    text = str(payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="An empty message - delete it instead.")
    m.text = text[:4000]; m.edited_at = _now(); db.commit()
    return _msg(m, {p.id: p for p in db.query(models.User).all()})


@router.delete("/store/chat/messages/{mid}")
def chat_delete(mid: int, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    m = db.query(ChatMessage).filter(ChatMessage.id == mid).first()
    if not m:
        raise HTTPException(status_code=404, detail="Message not found.")
    if m.user_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Only the person who wrote it can delete it.")
    if m.file_path:
        try:
            os.remove(os.path.join(_dir(), m.file_path))
        except OSError:
            pass
        m.file_path = ""
    m.deleted = True; m.text = ""; m.edited_at = _now(); db.commit()
    return {"ok": True}


def _mark(db, uid, room, last_id):
    r = db.query(ChatRead).filter(ChatRead.user_id == uid, ChatRead.room == room).first()
    if not r:
        db.add(ChatRead(user_id=uid, room=room, last_id=last_id))
    elif (r.last_id or 0) < last_id:
        r.last_id = last_id
    db.commit()


@router.post("/store/chat/read")
def chat_read(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    room = str(payload.get("room") or "")
    if not _in_room(room, user.id):
        raise HTTPException(status_code=403, detail="Not your conversation.")
    _mark(db, user.id, room, int(payload.get("last_id") or 0))
    return {"ok": True}


# ---- the bell and the phone -----------------------------------------------------------------------------
def bell_items(db, user):
    """Unread private messages (one line a person) and mentions in Everyone, for the bell and the phone."""
    try:
        people = _people(db)
        reads = _reads(db, user.id)
    except Exception:
        return []
    base = reads["*"].last_id
    rooms = [EVERYONE] + [dm_room(user.id, p.id) for p in people if p.id != user.id]
    floor = min([reads[r].last_id if r in reads else base for r in rooms] or [base])
    rows = (db.query(ChatMessage).filter(ChatMessage.id > floor, ChatMessage.room.in_(rooms), ChatMessage.user_id != user.id,
                                         ChatMessage.deleted == False).order_by(ChatMessage.id).all())  # noqa: E712
    umap = {p.id: p for p in people}
    by_room = {}
    for m in rows:
        if m.id <= (reads[m.room].last_id if m.room in reads else base):
            continue
        if m.room == EVERYONE and not (f",{user.id}," in (m.mentions or "") or ",*," in (m.mentions or "")):
            continue
        by_room.setdefault(m.room, []).append(m)
    out = []
    for room, ms in by_room.items():
        last = ms[-1]
        who = _name(umap.get(last.user_id)) or "Someone"
        words = (last.text or "").replace("\n", " ") or {"voice": "Voice message", "image": "Photo"}.get(last.file_kind or "", f"File: {last.file_name}" if last.file_kind else "")
        if room == EVERYONE:
            title = f"{who} mentioned you in Everyone"
        else:
            title = f"{who} sent you {'a message' if len(ms) == 1 else f'{len(ms)} messages'}"
        out.append({"id": f"chat-{room}-{last.id}", "kind": "chat", "title": title, "detail": words[:160],
                    "screen": "chat", "target": room, "when": (last.created_at or _now()).date().isoformat(),
                    "level": "info", "who": who, "initials": _initials(who)})
    out.sort(key=lambda n: n["id"], reverse=True)
    return out

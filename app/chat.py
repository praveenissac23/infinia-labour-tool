"""In-app chat: who is online, one room for everyone, and a private chat between any two people.

    Everyone      - the whole office sees it ("all")
    Private chat  - two people only ("dm:<lower id>-<higher id>")

@mentions: @username (the composer fills it in from the list), and @everyone in the Everyone room.
A private message or a mention also reaches the bell and the phone, like any other notification.

Presence: every open app asks /store/chat/state now and then (every few seconds while the chat is open,
about every 20 seconds otherwise); a person seen in the last 70 seconds is online.
"""
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Session

import auth
import models
from database import Base, get_db

router = APIRouter()
ONLINE_FOR = 70          # seconds since a person's app last asked, to count as online
EVERYONE = "all"


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


def _msg(m, users):
    u = users.get(m.user_id)
    return {"id": m.id, "room": m.room, "user_id": m.user_id, "name": _name(u) or "Someone", "initials": _initials(_name(u)),
            "text": "" if m.deleted else (m.text or ""), "deleted": bool(m.deleted), "at": _iso(m.created_at),
            "edited": bool(m.edited_at), "mentions": [int(x) for x in (m.mentions or "").strip(",").split(",") if x.isdigit()],
            "everyone": ",*," in (m.mentions or "")}


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
    """Note the person as here - written at most every 15 seconds."""
    s = db.query(ChatSeen).filter(ChatSeen.user_id == user.id).first()
    now = _now()
    if not s:
        db.add(ChatSeen(user_id=user.id, last_seen=now)); db.commit()
    elif not s.last_seen or (now - s.last_seen).total_seconds() > 15:
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
    out = {"me": user.id, "users": users, "unread": unread, "mentions": mentions,
           "total": sum(unread.values()), "last": last}
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
    return out


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
        words = (last.text or "").replace("\n", " ")
        if room == EVERYONE:
            title = f"{who} mentioned you in Everyone"
        else:
            title = f"{who} sent you {'a message' if len(ms) == 1 else f'{len(ms)} messages'}"
        out.append({"id": f"chat-{room}-{last.id}", "kind": "chat", "title": title, "detail": words[:160],
                    "screen": "chat", "target": room, "when": (last.created_at or _now()).date().isoformat(),
                    "level": "info", "who": who, "initials": _initials(who)})
    out.sort(key=lambda n: n["id"], reverse=True)
    return out

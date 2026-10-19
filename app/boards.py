"""Estimation > Trello: the company's own Trello, with no seat limits.

Boards, lists and cards the way Trello has them - labels, members, start
and due dates, checklists, comments with @mentions, attachments and
covers, custom fields, card templates, archive, activity, automation
rules - for every login that has the Estimation > Trello tick. Nobody
pays per invite: everyone with a login can be put on a board.

Who sees a board:
    team     every login with the tick (the default, like a Workspace board)
    private  the board's members only
An app admin sees every board. On a board a person is an admin (members,
settings, delete), a member (edits everything) or an observer (reads and
comments).

Everything a board shows comes back in one call (GET /store/kb/boards/{id});
the page asks /version every few seconds and fetches again when someone
else changed something, so two people on one board see each other's moves.

Files are kept on disk beside the app (data/boards/), photos made no wider
than 2000 px with a small copy for covers, and are fetched through a link
signed for a day - never a public address.

All addresses are under /store/kb/ (nginx forwards /store/) and
/export/kb/ for the Preview / PDF / Excel of a board.
"""
import hashlib
import hmac
import io
import json
import os
import re
import time
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Session

import auth
import main as M
import models
from database import Base, get_db

RIGHT = "estimation_boards"
router = APIRouter()
VIEW = Depends(M.require_screen(RIGHT))

# Trello's own label colours (name -> bold colour) and backgrounds.
LABEL_COLORS = ["green", "yellow", "orange", "red", "purple", "blue", "sky", "lime", "pink", "black",
                "green_dark", "yellow_dark", "orange_dark", "red_dark", "purple_dark", "blue_dark", "sky_dark",
                "lime_dark", "pink_dark", "black_dark",
                "green_light", "yellow_light", "orange_light", "red_light", "purple_light", "blue_light",
                "sky_light", "lime_light", "pink_light", "black_light", ""]
BOARD_ROLES = ("admin", "member", "observer")
MAX_FILE = 25 * 1024 * 1024


def _now():
    return datetime.utcnow()


# ---- tables -------------------------------------------------------------------------

class KBoard(Base):
    __tablename__ = "kb_boards"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    desc = Column(Text, default="")
    bg = Column(String, default="blue")             # colour key, gradient key or "att:<id>" / "img:<url>"
    visibility = Column(String, default="team")     # team | private
    closed = Column(Boolean, default=False)
    is_template = Column(Boolean, default=False)
    next_no = Column(Integer, default=1)            # card numbers, #1 #2 ...
    version = Column(Integer, default=1)            # bumped on every change - the page polls it
    prefs = Column(Text, default="{}")              # covers on/off, card aging, comments: members|observers ...
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now)


class KMember(Base):
    __tablename__ = "kb_members"
    id = Column(Integer, primary_key=True)
    board_id = Column(Integer, index=True, nullable=False)
    user_id = Column(Integer, index=True, nullable=False)
    role = Column(String, default="member")
    added_at = Column(DateTime, default=_now)


class KStar(Base):
    __tablename__ = "kb_stars"
    id = Column(Integer, primary_key=True)
    board_id = Column(Integer, index=True)
    user_id = Column(Integer, index=True)


class KSeen(Base):
    """When each person last opened each board - 'Recently viewed'."""
    __tablename__ = "kb_seen"
    id = Column(Integer, primary_key=True)
    board_id = Column(Integer, index=True)
    user_id = Column(Integer, index=True)
    at = Column(DateTime, default=_now)


class KLabel(Base):
    __tablename__ = "kb_labels"
    id = Column(Integer, primary_key=True)
    board_id = Column(Integer, index=True)
    name = Column(String, default="")
    color = Column(String, default="green")
    pos = Column(Float, default=0)


class KList(Base):
    __tablename__ = "kb_lists"
    id = Column(Integer, primary_key=True)
    board_id = Column(Integer, index=True)
    title = Column(String, default="")
    pos = Column(Float, default=0)
    closed = Column(Boolean, default=False)
    color = Column(String, default="")               # Trello's list colours
    wip = Column(Integer, default=0)                 # limit of cards (0 = none) - shown red when over
    collapsed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_now)


class KCard(Base):
    __tablename__ = "kb_cards"
    id = Column(Integer, primary_key=True)
    board_id = Column(Integer, index=True)
    list_id = Column(Integer, index=True)
    no = Column(Integer, default=0)
    title = Column(Text, default="")
    desc = Column(Text, default="")
    pos = Column(Float, default=0)
    closed = Column(Boolean, default=False)
    start = Column(String, default="")               # YYYY-MM-DD
    due = Column(String, default="")                 # ISO date-time, Dubai wall clock (YYYY-MM-DDTHH:MM)
    due_complete = Column(Boolean, default=False)
    reminder = Column(Integer, default=-1)           # minutes before due, -1 none
    labels = Column(Text, default="[]")              # label ids
    members = Column(Text, default="[]")             # user ids
    watchers = Column(Text, default="[]")
    cover = Column(Text, default="{}")               # {"color":..} or {"att":id} + {"size": "normal"|"full", "text":"light|dark"}
    fields = Column(Text, default="{}")              # custom field values {field_id: value}
    is_template = Column(Boolean, default=False)
    location = Column(String, default="")
    votes = Column(Text, default="[]")               # Voting power-up: user ids
    priority = Column(String, default="")            # Jira-style: highest | high | medium | low | lowest
    points = Column(Float, nullable=True)            # story points
    estimate = Column(Float, nullable=True)          # hours (time tracking)
    mirror_of = Column(Integer, nullable=True)       # a mirror shows another card, on another board
    links = Column(Text, default="[]")               # related cards (ids)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now)


class KTime(Base):
    """Time tracking power-up: hours logged on a card."""
    __tablename__ = "kb_time"
    id = Column(Integer, primary_key=True)
    card_id = Column(Integer, index=True)
    board_id = Column(Integer, index=True)
    user_id = Column(Integer, nullable=True)
    hours = Column(Float, default=0)
    day = Column(String, default="")
    note = Column(String, default="")
    created_at = Column(DateTime, default=_now)


class KRepeat(Base):
    """Card Repeater power-up: a copy of the card made every day / week / month."""
    __tablename__ = "kb_repeats"
    id = Column(Integer, primary_key=True)
    card_id = Column(Integer, index=True)
    board_id = Column(Integer, index=True)
    list_id = Column(Integer)
    every = Column(String, default="week")            # day | weekday | week | month | year
    nth = Column(Integer, default=1)                  # every 2 weeks ...
    time = Column(String, default="09:00")
    next_on = Column(String, default="")              # YYYY-MM-DD of the next copy
    due_days = Column(Integer, default=-1)            # due date this many days after the copy (-1 none)
    enabled = Column(Boolean, default=True)
    made = Column(Integer, default=0)
    created_by = Column(Integer, nullable=True)


class KChecklist(Base):
    __tablename__ = "kb_checklists"
    id = Column(Integer, primary_key=True)
    card_id = Column(Integer, index=True)
    title = Column(String, default="Checklist")
    pos = Column(Float, default=0)
    hide_done = Column(Boolean, default=False)


class KItem(Base):
    __tablename__ = "kb_items"
    id = Column(Integer, primary_key=True)
    checklist_id = Column(Integer, index=True)
    text = Column(Text, default="")
    done = Column(Boolean, default=False)
    pos = Column(Float, default=0)
    due = Column(String, default="")
    member = Column(Integer, nullable=True)


class KComment(Base):
    __tablename__ = "kb_comments"
    id = Column(Integer, primary_key=True)
    card_id = Column(Integer, index=True)
    board_id = Column(Integer, index=True)
    user_id = Column(Integer, nullable=True)
    author = Column(String, default="")              # imported comments keep the Trello name
    text = Column(Text, default="")
    created_at = Column(DateTime, default=_now)
    edited_at = Column(DateTime, nullable=True)


class KAttachment(Base):
    __tablename__ = "kb_attachments"
    id = Column(Integer, primary_key=True)
    card_id = Column(Integer, index=True)
    board_id = Column(Integer, index=True)
    name = Column(String, default="")
    url = Column(Text, default="")                   # a link; empty for an uploaded file
    path = Column(String, default="")                # file on disk (relative to the store)
    thumb = Column(String, default="")
    mime = Column(String, default="")
    size = Column(Integer, default=0)
    width = Column(Integer, default=0)
    height = Column(Integer, default=0)
    edge = Column(String, default="")                # average colour, for the cover behind a photo
    user_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=_now)


class KActivity(Base):
    __tablename__ = "kb_activity"
    id = Column(Integer, primary_key=True)
    board_id = Column(Integer, index=True)
    card_id = Column(Integer, index=True, nullable=True)
    user_id = Column(Integer, nullable=True)
    kind = Column(String, default="")
    data = Column(Text, default="{}")
    created_at = Column(DateTime, default=_now, index=True)


class KRule(Base):
    """Automation, Trello's Butler: when <trigger> then <actions>."""
    __tablename__ = "kb_rules"
    id = Column(Integer, primary_key=True)
    board_id = Column(Integer, index=True)
    trigger = Column(Text, default="{}")
    actions = Column(Text, default="[]")
    enabled = Column(Boolean, default=True)
    runs = Column(Integer, default=0)
    last_run = Column(String, default="")            # scheduled rules: the period last run ("2026-10-19", "2026-W42", "2026-10")
    state = Column(Text, default="{}")               # due-date rules: cards already handled; cross-board: card -> card made
    log = Column(Text, default="[]")                 # the last runs, newest first
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=_now)


class KField(Base):
    """Custom fields (Trello's Custom Fields power-up, free here)."""
    __tablename__ = "kb_fields"
    id = Column(Integer, primary_key=True)
    board_id = Column(Integer, index=True)
    name = Column(String, default="")
    type = Column(String, default="text")            # text | number | date | checkbox | list
    options = Column(Text, default="[]")             # list: [{"id":..,"text":..,"color":..}]
    on_front = Column(Boolean, default=True)
    pos = Column(Float, default=0)


class KNote(Base):
    """What a person is told: put on a card, @mentioned, a comment on a card they follow."""
    __tablename__ = "kb_notes"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True)
    board_id = Column(Integer)
    card_id = Column(Integer, nullable=True)
    actor_id = Column(Integer, nullable=True)
    kind = Column(String, default="")
    text = Column(Text, default="")
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_now, index=True)


TABLES = [KBoard, KMember, KStar, KSeen, KLabel, KList, KCard, KChecklist, KItem, KComment, KAttachment,
          KActivity, KRule, KField, KNote, KTime, KRepeat]


def create_tables(engine):
    for t in TABLES:
        t.__table__.create(bind=engine, checkfirst=True)
    # Columns added after a table was first made.
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    for t in TABLES:
        have = {c["name"] for c in insp.get_columns(t.__tablename__)}
        for col in t.__table__.columns:
            if col.name not in have:
                typ = col.type.compile(engine.dialect)
                with engine.begin() as cx:
                    cx.execute(text(f'ALTER TABLE {t.__tablename__} ADD COLUMN {col.name} {typ}'))


# ---- small helpers ---------------------------------------------------------------------

def _j(s, default):
    try:
        v = json.loads(s or "")
        return v if v is not None else default
    except (TypeError, ValueError):
        return default


def _iso(d):
    return (d.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")) if d else None


def _uname(u):
    return (u.full_name or u.username or "").strip() if u else ""


def _initials(name):
    parts = [p for p in re.split(r"[\s._-]+", name or "") if p]
    return ((parts[0][0] + (parts[1][0] if len(parts) > 1 else "")) if parts else "?").upper()


def _user_out(u):
    n = _uname(u)
    return {"id": u.id, "name": n, "username": u.username, "initials": _initials(n), "role": u.role}


def _users(db, ids=None):
    q = db.query(models.User)
    if ids is not None:
        ids = [i for i in ids if i]
        if not ids:
            return {}
        q = q.filter(models.User.id.in_(ids))
    return {u.id: u for u in q.all()}


def _is_app_admin(user):
    return (user.role or "") == "admin"


def _role_on(db, board, user):
    """admin | member | observer | None (no access)."""
    ib = _j(board.prefs, {}).get("inbox_of")
    if ib:
        return "admin" if ib == user.id else None
    if _is_app_admin(user):
        return "admin"
    m = db.query(KMember).filter(KMember.board_id == board.id, KMember.user_id == user.id).first()
    if m:
        return m.role if m.role in BOARD_ROLES else "member"
    if board.visibility == "team":
        return "member"          # a Workspace-visible board: anyone with the tick may work on it
    return None


def _board(db, user, bid, need="view"):
    b = db.query(KBoard).filter(KBoard.id == bid).first()
    if not b:
        raise HTTPException(status_code=404, detail="That board is not there any more.")
    role = _role_on(db, b, user)
    if role is None:
        raise HTTPException(status_code=403, detail="This board is private. Ask one of its admins to add you.")
    if need == "edit" and role == "observer":
        raise HTTPException(status_code=403, detail="You are an observer on this board - you can read and comment only.")
    if need == "admin" and role != "admin":
        raise HTTPException(status_code=403, detail="Only an admin of this board can do that.")
    return b, role


def _ensure_member(db, board, user, role="member"):
    """Working on a team board puts you on it, as Trello does when you join."""
    if not db.query(KMember).filter(KMember.board_id == board.id, KMember.user_id == user.id).first():
        db.add(KMember(board_id=board.id, user_id=user.id, role=role))


def _touch(db, board):
    board.version = (board.version or 0) + 1
    board.updated_at = _now()
    # Boards that show mirrors of this board's cards see the change too.
    try:
        src_ids = db.query(KCard.id).filter(KCard.board_id == board.id)
        other = {x[0] for x in db.query(KCard.board_id).filter(KCard.mirror_of.in_(src_ids), KCard.board_id != board.id).distinct()}
        if other:
            db.query(KBoard).filter(KBoard.id.in_(other)).update({KBoard.version: KBoard.version + 1}, synchronize_session=False)
    except Exception as e:      # never let a refresh stop the change itself
        print("touch mirrors:", e)


def _act(db, board, user, kind, card=None, **data):
    db.add(KActivity(board_id=board.id, card_id=card.id if card else None, user_id=user.id if user else None,
                     kind=kind, data=json.dumps(data, default=str)))


def _source_of(db, c):
    """A mirror card is a window on its source: the source, if it is still there."""
    if c is not None and c.mirror_of:
        return db.query(KCard).filter(KCard.id == c.mirror_of).first()
    return None


def _card(db, user, cid, need="view", follow=True):
    """The card - and for a mirror, its source (as Trello's mirror cards do,
    whatever is done on a mirror is done on the card it shows)."""
    c = db.query(KCard).filter(KCard.id == cid).first()
    if not c:
        raise HTTPException(status_code=404, detail="That card is not there any more.")
    if follow:
        s = _source_of(db, c)
        if s is not None:
            c = s
    b, role = _board(db, user, c.board_id, need)
    return c, b, role


def _list(db, user, lid, need="edit"):
    l = db.query(KList).filter(KList.id == lid).first()
    if not l:
        raise HTTPException(status_code=404, detail="That list is not there any more.")
    b, role = _board(db, user, l.board_id, need)
    return l, b, role


def _end_pos(db, model, **flt):
    q = db.query(func.max(model.pos))
    for k, v in flt.items():
        q = q.filter(getattr(model, k) == v)
    m = q.scalar()
    return (m or 0) + 65536


def _top_pos(db, model, **flt):
    q = db.query(func.min(model.pos))
    for k, v in flt.items():
        q = q.filter(getattr(model, k) == v)
    m = q.scalar()
    return (m if m is not None else 65536) / 2


def _pos_from(payload, db, model, **flt):
    p = payload.get("pos")
    if p == "top":
        return _top_pos(db, model, **flt)
    if p in (None, "", "bottom"):
        return _end_pos(db, model, **flt)
    try:
        return float(p)
    except (TypeError, ValueError):
        return _end_pos(db, model, **flt)


def _renumber_if_tight(db, model, **flt):
    """Positions are halved as things are dropped between others; when two
    come too close, spread the whole run out again."""
    rows = db.query(model)
    for k, v in flt.items():
        rows = rows.filter(getattr(model, k) == v)
    rows = rows.order_by(model.pos, model.id).all()
    tight = any(abs((rows[i + 1].pos or 0) - (rows[i].pos or 0)) < 0.01 for i in range(len(rows) - 1))
    if tight:
        for i, r in enumerate(rows):
            r.pos = (i + 1) * 65536


# ---- files ----------------------------------------------------------------------------------

def _store_dir():
    p = os.environ.get("INFINIA_BOARDS_DIR")
    if not p:
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "boards")
    os.makedirs(p, exist_ok=True)
    return p


def _sign(aid, exp):
    return hmac.new(auth.SECRET_KEY.encode(), f"kb:{aid}:{exp}".encode(), hashlib.sha256).hexdigest()[:24]


def _file_url(a, thumb=False):
    if a.url and not a.path:
        return a.url
    exp = int(time.time() // 86400 + 2) * 86400        # good for a day or two; same all day so the browser caches
    name = re.sub(r"[^\w.\-]+", "_", a.name or "file")[:80] or "file"
    return f"/store/kb/f/{a.id}/{exp}/{_sign(a.id, exp)}/{'t' if thumb else 'o'}/{name}"


def _att_out(a, users=None):
    u = (users or {}).get(a.user_id)
    img = bool(a.path and (a.mime or "").startswith("image/"))
    return {"id": a.id, "card_id": a.card_id, "name": a.name, "url": _file_url(a), "link": bool(a.url and not a.path),
            "thumb": _file_url(a, True) if (img and a.thumb) else (_file_url(a) if img else ""),
            "image": img or bool(a.url and re.search(r"\.(png|jpe?g|gif|webp)(\?|$)", a.url, re.I)),
            "mime": a.mime, "size": a.size, "w": a.width, "h": a.height, "edge": a.edge,
            "by": _uname(u) if u else "", "at": _iso(a.created_at)}


# ---- what a card looks like on the board and in full -------------------------------------------

def _front(c, counts, atts, me_id):
    cov = _j(c.cover, {})
    if cov.get("att") and cov["att"] in atts:
        a = atts[cov["att"]]
        cov = {**cov, "url": a["thumb"] or a["url"], "full_url": a["url"], "edge": a.get("edge", ""), "w": a["w"], "h": a["h"]}
    elif cov.get("att"):
        cov = {k: v for k, v in cov.items() if k != "att"}
    cnt = counts.get(c.id, {})
    return {"id": c.id, "no": c.no, "list_id": c.list_id, "title": c.title, "pos": c.pos, "closed": c.closed,
            "start": c.start or "", "due": c.due or "", "due_complete": bool(c.due_complete), "reminder": c.reminder,
            "labels": _j(c.labels, []), "members": _j(c.members, []), "cover": cov, "fields": _j(c.fields, {}),
            "is_template": bool(c.is_template), "desc": bool((c.desc or "").strip()), "location": c.location or "",
            "watching": me_id in _j(c.watchers, []), "votes": _j(c.votes, []), "priority": c.priority or "",
            "points": c.points, "estimate": c.estimate, "logged": cnt.get("hours", 0), "mirror_of": c.mirror_of,
            "links": _j(c.links, []),
            "comments": cnt.get("comments", 0), "attachments": cnt.get("attachments", 0),
            "check": [cnt.get("done", 0), cnt.get("items", 0)],
            "updated": _iso(c.updated_at), "created": _iso(c.created_at)}


def _counts(db, card_ids):
    out = {}
    if not card_ids:
        return out
    for cid, n in db.query(KComment.card_id, func.count(KComment.id)).filter(KComment.card_id.in_(card_ids)).group_by(KComment.card_id):
        out.setdefault(cid, {})["comments"] = n
    for cid, n in db.query(KAttachment.card_id, func.count(KAttachment.id)).filter(KAttachment.card_id.in_(card_ids)).group_by(KAttachment.card_id):
        out.setdefault(cid, {})["attachments"] = n
    for cid, h in db.query(KTime.card_id, func.sum(KTime.hours)).filter(KTime.card_id.in_(card_ids)).group_by(KTime.card_id):
        out.setdefault(cid, {})["hours"] = round(h or 0, 2)
    rows = (db.query(KChecklist.card_id, KItem.done, func.count(KItem.id))
            .join(KItem, KItem.checklist_id == KChecklist.id)
            .filter(KChecklist.card_id.in_(card_ids)).group_by(KChecklist.card_id, KItem.done))
    for cid, done, n in rows:
        d = out.setdefault(cid, {})
        d["items"] = d.get("items", 0) + n
        if done:
            d["done"] = d.get("done", 0) + n
    return out


def _cover_atts(db, cards):
    ids = [(_j(c.cover, {}) or {}).get("att") for c in cards]
    ids = [i for i in ids if i]
    if not ids:
        return {}
    return {a.id: _att_out(a) for a in db.query(KAttachment).filter(KAttachment.id.in_(ids)).all()}


def _mirror_fill(db, fronts):
    """A mirror card shows its source: title, dates, badges and the source's labels by name and colour."""
    src_ids = [f["mirror_of"] for f in fronts if f.get("mirror_of")]
    if not src_ids:
        return
    src = {c.id: c for c in db.query(KCard).filter(KCard.id.in_(src_ids)).all()}
    counts = _counts(db, list(src))
    atts = _cover_atts(db, list(src.values()))
    labels = {l.id: {"name": l.name, "color": l.color} for l in db.query(KLabel).filter(KLabel.board_id.in_([c.board_id for c in src.values()] or [0])).all()}
    boards = {b.id: b.title for b in db.query(KBoard).filter(KBoard.id.in_([c.board_id for c in src.values()] or [0])).all()}
    list_titles = {l.id: l.title or "" for l in db.query(KList).filter(KList.id.in_([c.list_id for c in src.values()] or [0])).all()}
    for f in fronts:
        c = src.get(f.get("mirror_of"))
        if not c:
            f["mirror"] = {"gone": True}
            continue
        sf = _front(c, counts, atts, f.get("_me"))
        f["mirror"] = {"board": boards.get(c.board_id, ""), "board_id": c.board_id, "card_id": c.id, "closed": bool(c.closed),
                       "labels": [labels[x] for x in sf["labels"] if x in labels]}
        # A card named only by what it is ("Permits & NOCs") in a list named after its project
        # ("906 Jamal Khan Villa") shows on the other board with the project number in front.
        lt = list_titles.get(c.list_id, "")
        if not NUMBERED.match(sf["title"] or "") and NUMBERED.match(lt):
            sf["title"] = f'{NUMBERED.match(lt).group(0).strip()} - {sf["title"]}'
        for k in ("title", "due", "start", "due_complete", "cover", "comments", "attachments", "check", "desc", "members", "no"):
            f[k] = sf[k]


def _board_out(db, b, user, role, include_closed=False):
    try:
        _run_repeats(db, b)
    except Exception as e:
        print("repeats:", e)
    lists = db.query(KList).filter(KList.board_id == b.id, KList.closed == False).order_by(KList.pos, KList.id).all()  # noqa: E712
    list_ids = {l.id for l in lists}
    cq = db.query(KCard).filter(KCard.board_id == b.id, KCard.closed == False)  # noqa: E712
    cards = [c for c in cq.order_by(KCard.pos, KCard.id).all() if c.list_id in list_ids]
    counts = _counts(db, [c.id for c in cards])
    atts = _cover_atts(db, cards)
    mem = db.query(KMember).filter(KMember.board_id == b.id).all()
    users = _users(db)
    members = [{**_user_out(users[m.user_id]), "board_role": m.role} for m in mem if m.user_id in users]
    labels = db.query(KLabel).filter(KLabel.board_id == b.id).order_by(KLabel.pos, KLabel.id).all()
    fields = db.query(KField).filter(KField.board_id == b.id).order_by(KField.pos, KField.id).all()
    starred = bool(db.query(KStar).filter(KStar.board_id == b.id, KStar.user_id == user.id).first())
    bg = b.bg or "blue"
    bg_url = ""
    if bg.startswith("att:"):
        a = db.query(KAttachment).filter(KAttachment.id == int(bg[4:] or 0)).first()
        bg_url = _file_url(a) if a else ""
    return {"id": b.id, "title": b.title, "desc": b.desc or "", "bg": bg, "bg_url": bg_url, "visibility": b.visibility,
            "closed": b.closed, "is_template": bool(b.is_template), "version": b.version, "prefs": _j(b.prefs, {}),
            "starred": starred, "role": role, "me": user.id,
            "members": members, "people": [_user_out(u) for u in users.values()],
            "labels": [{"id": l.id, "name": l.name or "", "color": l.color or ""} for l in labels],
            "fields": [{"id": f.id, "name": f.name, "type": f.type, "options": _j(f.options, []), "on_front": bool(f.on_front)} for f in fields],
            "lists": [{"id": l.id, "title": l.title, "pos": l.pos, "color": l.color or "", "wip": l.wip or 0, "collapsed": bool(l.collapsed)} for l in lists],
            "cards": _fronts_with_mirrors(db, cards, counts, atts, user.id),
            "time": {str(k): round(v or 0, 2) for k, v in db.query(KTime.user_id, func.sum(KTime.hours)).filter(KTime.board_id == b.id).group_by(KTime.user_id)},
            "rules": db.query(func.count(KRule.id)).filter(KRule.board_id == b.id).scalar() or 0}


def _fronts_with_mirrors(db, cards, counts, atts, me):
    fr = [_front(c, counts, atts, me) for c in cards]
    for f in fr:
        f["_me"] = me
    _mirror_fill(db, fr)
    for f in fr:
        f.pop("_me", None)
    # A mirror whose card was archived leaves the board with it (it comes back when the card is restored).
    return [f for f in fr if not (f.get("mirror") or {}).get("closed")]


def _is_inbox(b):
    return bool(_j(b.prefs, {}).get("inbox_of"))


def _visible_boards(db, user, inbox=False):
    q = db.query(KBoard)
    allb = [b for b in q.all() if inbox or not _is_inbox(b)]
    if _is_app_admin(user):
        return allb
    mine = {m.board_id for m in db.query(KMember).filter(KMember.user_id == user.id).all()}
    return [b for b in allb if b.id in mine or b.visibility == "team"]


# ---- notes (what a person is told) ---------------------------------------------------------------

def _note(db, uid, actor, board, card, kind, text):
    if not uid or (actor and uid == actor.id):
        return
    db.add(KNote(user_id=uid, board_id=board.id, card_id=card.id if card else None,
                 actor_id=actor.id if actor else None, kind=kind, text=text[:400]))


def _mentions(db, text):
    names = set(m.lower() for m in re.findall(r"@([\w.\-]+)", text or ""))
    if not names:
        return []
    return [u for u in db.query(models.User).all() if (u.username or "").lower() in names]


# ---- automation (Butler) --------------------------------------------------------------------------

TRIGGERS = ("card_added", "card_moved", "card_complete", "checklist_done", "label_added", "member_added", "card_created",
            "card_archived", "due_set", "comment_added", "item_done", "schedule", "due_in", "card_titled")
ACTIONS = ("move", "complete", "incomplete", "add_label", "remove_label", "add_member", "remove_member",
           "set_due", "clear_due", "archive", "comment", "add_checklist", "join", "move_top", "set_cover",
           "move_board", "copy_board", "mirror_board", "notify", "sort_list", "remove_cover", "watch", "move_mirror")
EVENT_TRIGGERS = set(TRIGGERS) - {"schedule", "due_in"}


def _run_rules(db, board, card, user, event, depth=0, **ctx):
    if depth > 3 or card is None:
        return
    for r in db.query(KRule).filter(KRule.board_id == board.id, KRule.enabled == True).all():  # noqa: E712
        t = _j(r.trigger, {})
        if t.get("type") != event:
            continue
        if t.get("list_id") and int(t["list_id"]) != int(ctx.get("list_id") or card.list_id or 0):
            continue
        if t.get("label_id") and int(t["label_id"]) != int(ctx.get("label_id") or 0):
            continue
        if t.get("user_id") and int(t["user_id"]) != int(ctx.get("user_id") or 0):
            continue
        if t.get("type") == "card_titled":
            lst = db.query(KList).filter(KList.id == card.list_id).first()
            if not _title_matches(t, card.title, lst.title if lst else ""):
                continue
        _fire(db, r, board, card, user, depth)


NUMBERED = re.compile(r"^\s*(ic\s*/\s*)?\d{3}(?!\d)", re.I)


def _title_matches(t, title, list_title=""):
    """'When a card's title has any of these words' (plurals count: Bill matches Bills) - optionally only
    cards of a project: the title starts with its number (911 - ..., IC/911 ...)."""
    ttl = (title or "").lower()
    # (Only the title counts: the standard cards in a project's list - "Variations", "Permits & NOCs" -
    # are headings there, not items for Anoop's board.)
    if t.get("numbered") and not NUMBERED.match(ttl):
        return False
    words = [w.strip().lower() for w in (t.get("words") or []) if str(w).strip()]
    return any(re.search(r"(^|[^a-z0-9])" + re.escape(w), ttl) for w in words)


def _fire(db, r, board, card, user, depth=0):
    """Run one rule's actions on one card, count it and keep a short log."""
    r.runs = (r.runs or 0) + 1
    done = []
    for a in _j(r.actions, []):
        try:
            res = _do_action(db, board, card, user, a, depth, rule=r)
            done.append(res or a.get("type"))
        except HTTPException as e:
            done.append(f"skipped: {e.detail}")
    if card is not None:
        _act(db, board, user, "rule", card, rule=r.id, title=_rule_words(db, r))
    lg = _j(r.log, [])
    lg.insert(0, {"at": _iso(_now()), "card": card.title if card is not None else "", "card_id": card.id if card is not None else None,
                  "did": [str(x) for x in done][:6]})
    r.log = json.dumps(lg[:30])


def _do_action(db, board, card, user, a, depth, rule=None):
    k = a.get("type")
    if card is None and k != "sort_list":
        return None
    if k == "sort_list":
        lst = db.query(KList).filter(KList.id == int(a.get("list_id") or 0), KList.board_id == board.id).first()
        if lst:
            cards = db.query(KCard).filter(KCard.list_id == lst.id, KCard.closed == False).all()  # noqa: E712
            by = a.get("by") or "due"
            key = {"due": (lambda c: c.due or "9999", False), "name": (lambda c: (c.title or "").lower(), False),
                   "created_new": (lambda c: c.created_at or datetime.min, True), "created_old": (lambda c: c.created_at or datetime.min, False),
                   "votes": (lambda c: len(_j(c.votes, [])), True)}.get(by, (lambda c: c.due or "9999", False))
            for i, c in enumerate(sorted(cards, key=key[0], reverse=key[1])):
                c.pos = (i + 1) * 65536
        return f"sorted {lst.title if lst else '?'}"
    if k in ("move_board", "copy_board", "mirror_board"):
        tb = db.query(KBoard).filter(KBoard.id == int(a.get("board_id") or 0)).first()
        tl = tb and db.query(KList).filter(KList.id == int(a.get("list_id") or 0), KList.board_id == tb.id).first()
        if not tb or not tl or tb.closed:
            return "skipped: the other board or list is gone"
        st = _j(rule.state, {}) if rule else {}
        key = f"{k}:{card.id}:{tl.id}"
        if k != "move_board" and st.get(key) and db.query(KCard).filter(KCard.id == st[key], KCard.closed == False).first():  # noqa: E712
            return f"already on {tb.title}"
        if k == "mirror_board":
            src_id = card.mirror_of or card.id
            if db.query(KCard).filter(KCard.mirror_of == src_id, KCard.board_id == tb.id, KCard.closed == False).first():  # noqa: E712
                return f"already mirrored on {tb.title}"
        pos = _top_pos(db, KCard, list_id=tl.id) if a.get("where") == "top" else _end_pos(db, KCard, list_id=tl.id)
        if k == "move_board":
            if tb.id == board.id:
                card.list_id, card.pos = tl.id, pos
            else:
                old = {l.id: (l.name, l.color) for l in db.query(KLabel).filter(KLabel.board_id == board.id).all()}
                new = {(l.name, l.color): l.id for l in db.query(KLabel).filter(KLabel.board_id == tb.id).all()}
                card.labels = json.dumps([new[old[x]] for x in _j(card.labels, []) if x in old and old[x] in new])
                card.board_id, card.list_id, card.pos = tb.id, tl.id, pos
                card.no = tb.next_no or 1
                tb.next_no = card.no + 1
                for m in (KAttachment, KComment, KActivity):
                    db.query(m).filter(m.card_id == card.id).update({"board_id": tb.id}, synchronize_session=False)
                _act(db, tb, user, "card_moved_board", card, frm=board.title, title=card.title)
            _touch(db, tb)
            return f"moved to {tb.title} / {tl.title}"
        src = db.query(KCard).filter(KCard.id == card.mirror_of).first() if card.mirror_of else card
        src = src or card
        if k == "copy_board":
            old = {l.id: (l.name, l.color) for l in db.query(KLabel).filter(KLabel.board_id == src.board_id).all()}
            new = {(l.name, l.color): l.id for l in db.query(KLabel).filter(KLabel.board_id == tb.id).all()}
            nc = _clone_card(db, src, tb, tl.id, pos, lmap={x: new.get(v) for x, v in old.items()} if tb.id != src.board_id else None)
        else:
            nc = KCard(board_id=tb.id, list_id=tl.id, title=src.title, pos=pos, mirror_of=src.id, created_by=user.id if user else None)
            db.add(nc)
        nc.no = tb.next_no or 1
        tb.next_no = nc.no + 1
        db.flush()
        _act(db, tb, user, "card_mirrored" if k == "mirror_board" else "card_copied", nc, source=src.title, frm=board.title)
        if rule is not None:
            st[key] = nc.id
            rule.state = json.dumps(st)
        _touch(db, tb)
        return f"{'mirrored' if k == 'mirror_board' else 'copied'} to {tb.title} / {tl.title}"
    if k == "move_mirror":
        tb = db.query(KBoard).filter(KBoard.id == int(a.get("board_id") or 0)).first()
        tl = tb and db.query(KList).filter(KList.id == int(a.get("list_id") or 0), KList.board_id == tb.id).first()
        if not tl:
            return "skipped: the other board or list is gone"
        src_id = card.mirror_of or card.id
        n = 0
        for m in db.query(KCard).filter(KCard.mirror_of == src_id, KCard.board_id == tb.id, KCard.closed == False).all():  # noqa: E712
            if m.list_id != tl.id:
                m.list_id = tl.id
                m.pos = _top_pos(db, KCard, list_id=tl.id) if a.get("where") == "top" else _end_pos(db, KCard, list_id=tl.id)
                n += 1
        if n:
            _touch(db, tb)
        return f"moved {n} mirror(s) on {tb.title} to {tl.title}"
    if k == "notify":
        txt = (a.get("text") or "needs attention").strip()[:300]
        for uid in set(_j(card.members, [])) | set(_j(card.watchers, [])):
            db.add(KNote(user_id=uid, board_id=board.id, card_id=card.id, actor_id=None, kind="rule", text=f"{card.title}: {txt}"))
        return "notified members"
    if k == "remove_cover":
        card.cover = "{}"
        return "cover removed"
    if k == "watch":
        ws = _j(card.watchers, [])
        if user and user.id not in ws:
            card.watchers = json.dumps(ws + [user.id])
        return "watching"
    if k in ("move", "move_top"):
        lid = int(a.get("list_id") or 0)
        lst = db.query(KList).filter(KList.id == lid, KList.board_id == board.id).first()
        if lst and lst.id != card.list_id:
            old = card.list_id
            card.list_id = lst.id
            card.pos = _top_pos(db, KCard, list_id=lst.id) if (k == "move_top" or a.get("where") == "top") else _end_pos(db, KCard, list_id=lst.id)
            _run_rules(db, board, card, user, "card_moved", depth + 1, list_id=lst.id, from_list=old)
            _run_rules(db, board, card, user, "card_added", depth + 1, list_id=lst.id)
    elif k == "complete":
        if not card.due_complete:
            card.due_complete = True
    elif k == "incomplete":
        card.due_complete = False
    elif k in ("add_label", "remove_label"):
        ls = _j(card.labels, [])
        lid = int(a.get("label_id") or 0)
        if k == "add_label" and lid and lid not in ls:
            ls.append(lid)
        if k == "remove_label" and lid in ls:
            ls.remove(lid)
        card.labels = json.dumps(ls)
    elif k in ("add_member", "remove_member", "join"):
        ms = _j(card.members, [])
        uid = user.id if k == "join" else int(a.get("user_id") or 0)
        if k in ("add_member", "join") and uid and uid not in ms:
            ms.append(uid)
            _note(db, uid, user, board, card, "added", f"added you to the card {card.title}")
        if k == "remove_member" and uid in ms:
            ms.remove(uid)
        card.members = json.dumps(ms)
    elif k == "set_due":
        days = int(a.get("days") or 0)
        d = (datetime.utcnow() + timedelta(hours=4)).date() + timedelta(days=days)
        card.due = f"{d.isoformat()}T{a.get('time') or '17:00'}"
        card.due_complete = False
    elif k == "clear_due":
        card.due = ""
        card.due_complete = False
    elif k == "archive":
        card.closed = True
    elif k == "comment":
        txt = (a.get("text") or "").strip()
        if txt:
            db.add(KComment(card_id=card.id, board_id=board.id, user_id=user.id if user else None, text=txt))
    elif k == "add_checklist":
        cl = KChecklist(card_id=card.id, title=(a.get("title") or "Checklist")[:200], pos=_end_pos(db, KChecklist, card_id=card.id))
        db.add(cl)
        db.flush()
        for i, it in enumerate([x for x in (a.get("items") or []) if str(x).strip()]):
            db.add(KItem(checklist_id=cl.id, text=str(it)[:1000], pos=(i + 1) * 65536))
    elif k == "set_cover":
        card.cover = json.dumps({"color": a.get("color") or "green", "size": "normal"})
    card.updated_at = _now()
    return k


def _rule_words(db, r):
    t = _j(r.trigger, {})
    names = {l.id: l.title for l in db.query(KList).filter(KList.board_id == r.board_id).all()}
    w = {"card_added": "when a card is added to", "card_moved": "when a card is moved into",
         "card_complete": "when a card is marked complete", "checklist_done": "when all checklist items on a card are done",
         "label_added": "when a label is added", "member_added": "when a member is added",
         "card_created": "when a card is created", "card_archived": "when a card is archived",
         "due_set": "when a due date is set on a card", "comment_added": "when a comment is posted to a card",
         "item_done": "when a checklist item is checked",
         "card_titled": "when a card's title has " + " / ".join(f'"{w}"' for w in (t.get("words") or [])[:6]) + (" (titles starting with a project number)" if t.get("numbered") else "")}.get(t.get("type"), "when")
    if t.get("type") == "schedule":
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        w = {"day": "every day", "weekday": "every working day", "week": f"every {days[int(t.get('weekday') or 0) % 7]}",
             "month": f"on day {t.get('day') or 1} of every month"}.get(t.get("every"), "on a schedule") + f" at {t.get('time') or '09:00'}"
        w += f", for cards in \"{names.get(int(t['list_id']), '?')}\"" if t.get("list_id") else ""
    elif t.get("type") == "due_in":
        n = int(t.get("days") or 0)
        w = f"{abs(n)} day{'s' if abs(n) != 1 else ''} {'before' if n >= 0 else 'after'} a card is due" if n else "on the day a card is due"
    elif t.get("list_id"):
        w += f" list \"{names.get(int(t['list_id']), '?')}\""
    return w


# ---- boards -------------------------------------------------------------------------------------

DEFAULT_LABELS = [("green", ""), ("yellow", ""), ("orange", ""), ("red", ""), ("purple", ""), ("blue", "")]


@router.get("/store/kb/boards")
def list_boards(db: Session = Depends(get_db), user: models.User = VIEW):
    bs = _visible_boards(db, user)
    stars = {s.board_id for s in db.query(KStar).filter(KStar.user_id == user.id).all()}
    seen = {s.board_id: s.at for s in db.query(KSeen).filter(KSeen.user_id == user.id).all()}
    mine = {m.board_id: m.role for m in db.query(KMember).filter(KMember.user_id == user.id).all()}
    out = []
    for b in bs:
        bg_url = ""
        if (b.bg or "").startswith("att:"):
            a = db.query(KAttachment).filter(KAttachment.id == int(b.bg[4:] or 0)).first()
            bg_url = _file_url(a, True) if a else ""
        out.append({"id": b.id, "title": b.title, "bg": b.bg or "blue", "bg_url": bg_url, "visibility": b.visibility,
                    "closed": b.closed, "is_template": bool(b.is_template), "starred": b.id in stars,
                    "member": b.id in mine, "seen": _iso(seen.get(b.id)), "updated": _iso(b.updated_at)})
    out.sort(key=lambda x: (x["title"] or "").lower())
    return {"boards": out, "me": _user_out(user), "label_colors": LABEL_COLORS,
            "can_admin": _is_app_admin(user)}


@router.get("/store/kb/summary")
def summary(db: Session = Depends(get_db), user: models.User = VIEW):
    """Estimation > Overview: every open board with its counts, and my cards due in the next week."""
    now = datetime.utcnow() + timedelta(hours=4)
    today, week = now.strftime("%Y-%m-%dT%H:%M"), (now + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M")
    out, due = [], []
    for b in sorted([b for b in _visible_boards(db, user) if not b.closed and not b.is_template], key=lambda b: (b.title or "").lower()):
        lists = {l.id: l.title for l in db.query(KList).filter(KList.board_id == b.id, KList.closed == False).all()}  # noqa: E712
        cards = [c for c in db.query(KCard).filter(KCard.board_id == b.id, KCard.closed == False).all() if c.list_id in lists]  # noqa: E712
        out.append({"id": b.id, "title": b.title, "bg": b.bg or "blue", "lists": len(lists), "open": sum(1 for c in cards if not c.due_complete),
                    "overdue": sum(1 for c in cards if c.due and not c.due_complete and c.due[:16] < today),
                    "week": sum(1 for c in cards if c.due and not c.due_complete and today <= c.due[:16] <= week),
                    "done": sum(1 for c in cards if c.due_complete)})
        for c in cards:
            if c.due and not c.due_complete and c.due[:16] <= week and user.id in _j(c.members, []):
                due.append({"id": c.id, "board_id": b.id, "board": b.title, "list": lists.get(c.list_id, ""), "title": c.title,
                            "due": c.due, "due_text": _fmt_due(c.due), "overdue": c.due[:16] < today})
    return {"boards": out, "due": sorted(due, key=lambda x: x["due"])[:40]}


@router.post("/store/kb/boards")
def create_board(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    title = (payload.get("title") or "").strip()[:200]
    if not title:
        raise HTTPException(status_code=400, detail="Give the board a title.")
    src_id = payload.get("from_template")
    if src_id:
        src, _ = _board(db, user, int(src_id))
        b = _copy_board(db, src, user, title, keep_cards=payload.get("keep_cards", True))
        b.is_template = False
        if payload.get("bg"):
            b.bg = payload["bg"]
        db.commit()
        return {"id": b.id}
    b = KBoard(title=title, bg=(payload.get("bg") or "blue")[:300],
               visibility="private" if payload.get("visibility") == "private" else "team", created_by=user.id)
    db.add(b)
    db.flush()
    db.add(KMember(board_id=b.id, user_id=user.id, role="admin"))
    for i, (c, n) in enumerate(DEFAULT_LABELS):
        db.add(KLabel(board_id=b.id, color=c, name=n, pos=i + 1))
    for i, t in enumerate(payload.get("lists") or []):
        if str(t).strip():
            db.add(KList(board_id=b.id, title=str(t)[:200], pos=(i + 1) * 65536))
    _act(db, b, user, "board_created", title=title)
    db.commit()
    return {"id": b.id}


@router.get("/store/kb/boards/{bid}")
def get_board(bid: int, db: Session = Depends(get_db), user: models.User = VIEW):
    b, role = _board(db, user, bid)
    s = db.query(KSeen).filter(KSeen.board_id == b.id, KSeen.user_id == user.id).first()
    if s:
        s.at = _now()
    else:
        db.add(KSeen(board_id=b.id, user_id=user.id))
    db.commit()
    return _board_out(db, b, user, role)


@router.get("/store/kb/boards/{bid}/version")
def board_version(bid: int, db: Session = Depends(get_db), user: models.User = VIEW):
    b = db.query(KBoard).filter(KBoard.id == bid).first()
    if not b:
        raise HTTPException(status_code=404, detail="gone")
    unread = db.query(func.count(KNote.id)).filter(KNote.user_id == user.id, KNote.read == False).scalar()  # noqa: E712
    return {"version": b.version, "unread": unread}


@router.patch("/store/kb/boards/{bid}")
def update_board(bid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    b, role = _board(db, user, bid, "edit")
    if "title" in payload:
        t = (payload["title"] or "").strip()[:200]
        if not t:
            raise HTTPException(status_code=400, detail="A board needs a title.")
        if t != b.title:
            _act(db, b, user, "board_renamed", old=b.title, new=t)
        b.title = t
    if "desc" in payload:
        b.desc = (payload["desc"] or "")[:20000]
    if "bg" in payload:
        b.bg = (payload["bg"] or "blue")[:300]
    if "prefs" in payload and isinstance(payload["prefs"], dict):
        p = _j(b.prefs, {})
        p.update(payload["prefs"])
        b.prefs = json.dumps(p)
    for k in ("visibility", "closed", "is_template"):
        if k in payload:
            if role != "admin":
                raise HTTPException(status_code=403, detail="Only an admin of this board can change that.")
            if k == "visibility":
                b.visibility = "private" if payload[k] == "private" else "team"
            elif k == "closed":
                b.closed = bool(payload[k])
                _act(db, b, user, "board_closed" if b.closed else "board_reopened")
            else:
                b.is_template = bool(payload[k])
    _touch(db, b)
    db.commit()
    return {"ok": True}


@router.delete("/store/kb/boards/{bid}")
def delete_board(bid: int, db: Session = Depends(get_db), user: models.User = VIEW):
    b, role = _board(db, user, bid, "admin")
    if not b.closed:
        raise HTTPException(status_code=400, detail="Close the board first; a closed board can then be deleted for good.")
    cids = [c.id for c in db.query(KCard.id).filter(KCard.board_id == b.id).all()]
    _delete_cards(db, cids)
    for m in (KList, KLabel, KMember, KStar, KSeen, KActivity, KRule, KField):
        db.query(m).filter(m.board_id == b.id).delete(synchronize_session=False)
    db.query(KNote).filter(KNote.board_id == b.id).delete(synchronize_session=False)
    db.delete(b)
    db.commit()
    return {"ok": True}


def _delete_cards(db, cids):
    if not cids:
        return
    # A deleted card's mirrors on other boards go with it (their boards refresh).
    mirrors = db.query(KCard).filter(KCard.mirror_of.in_(cids), ~KCard.id.in_(cids)).all()
    if mirrors:
        bids = {m.board_id for m in mirrors}
        cids = list(cids) + [m.id for m in mirrors]
        db.query(KBoard).filter(KBoard.id.in_(bids)).update({KBoard.version: KBoard.version + 1}, synchronize_session=False)
    cl = [x.id for x in db.query(KChecklist.id).filter(KChecklist.card_id.in_(cids)).all()]
    if cl:
        db.query(KItem).filter(KItem.checklist_id.in_(cl)).delete(synchronize_session=False)
    db.query(KChecklist).filter(KChecklist.card_id.in_(cids)).delete(synchronize_session=False)
    db.query(KComment).filter(KComment.card_id.in_(cids)).delete(synchronize_session=False)
    for a in db.query(KAttachment).filter(KAttachment.card_id.in_(cids)).all():
        _remove_files(a)
        db.delete(a)
    db.query(KCard).filter(KCard.id.in_(cids)).delete(synchronize_session=False)


def _remove_files(a):
    for p in (a.path, a.thumb):
        if p:
            try:
                os.remove(os.path.join(_store_dir(), p))
            except OSError:
                pass


@router.post("/store/kb/boards/{bid}/star")
def star_board(bid: int, db: Session = Depends(get_db), user: models.User = VIEW):
    b, _ = _board(db, user, bid)
    s = db.query(KStar).filter(KStar.board_id == b.id, KStar.user_id == user.id).first()
    if s:
        db.delete(s)
    else:
        db.add(KStar(board_id=b.id, user_id=user.id))
    db.commit()
    return {"starred": not bool(s)}


def _copy_board(db, src, user, title, keep_cards=True):
    b = KBoard(title=title, desc=src.desc, bg=src.bg, visibility=src.visibility, prefs=src.prefs, created_by=user.id,
               is_template=False)
    db.add(b)
    db.flush()
    db.add(KMember(board_id=b.id, user_id=user.id, role="admin"))
    lmap, fmap = {}, {}
    for l in db.query(KLabel).filter(KLabel.board_id == src.id).all():
        n = KLabel(board_id=b.id, name=l.name, color=l.color, pos=l.pos)
        db.add(n)
        db.flush()
        lmap[l.id] = n.id
    for f in db.query(KField).filter(KField.board_id == src.id).all():
        n = KField(board_id=b.id, name=f.name, type=f.type, options=f.options, on_front=f.on_front, pos=f.pos)
        db.add(n)
        db.flush()
        fmap[f.id] = n.id
    no = 1
    for l in db.query(KList).filter(KList.board_id == src.id, KList.closed == False).order_by(KList.pos).all():  # noqa: E712
        nl = KList(board_id=b.id, title=l.title, pos=l.pos, color=l.color, wip=l.wip)
        db.add(nl)
        db.flush()
        if not keep_cards:
            continue
        for c in db.query(KCard).filter(KCard.list_id == l.id, KCard.closed == False).order_by(KCard.pos).all():  # noqa: E712
            nc = _clone_card(db, c, b, nl.id, c.pos, lmap, fmap, keep_members=False)
            nc.no = no
            no += 1
    b.next_no = no
    _act(db, b, user, "board_copied", source=src.title)
    return b


def _clone_card(db, c, board, list_id, pos, lmap=None, fmap=None, keep_members=True, keep_checklists=True,
                keep_comments=False, keep_atts=True, title=None):
    lab = [lmap.get(x) for x in _j(c.labels, [])] if lmap is not None else _j(c.labels, [])
    flds = _j(c.fields, {})
    if fmap is not None:
        flds = {str(fmap.get(int(k))): v for k, v in flds.items() if fmap.get(int(k))}
    nc = KCard(board_id=board.id, list_id=list_id, title=title if title is not None else c.title, desc=c.desc, pos=pos,
               start=c.start, due=c.due, due_complete=False if c.is_template else c.due_complete, reminder=c.reminder,
               labels=json.dumps([x for x in lab if x]), members=c.members if keep_members else "[]",
               cover=c.cover, fields=json.dumps(flds), location=c.location)
    db.add(nc)
    db.flush()
    amap = {}
    if keep_atts:
        for a in db.query(KAttachment).filter(KAttachment.card_id == c.id).all():
            na = KAttachment(card_id=nc.id, board_id=board.id, name=a.name, url=a.url, path=a.path, thumb=a.thumb,
                             mime=a.mime, size=a.size, width=a.width, height=a.height, edge=a.edge, user_id=a.user_id)
            db.add(na)
            db.flush()
            amap[a.id] = na.id
    cov = _j(c.cover, {})
    if cov.get("att"):
        if cov["att"] in amap:
            cov["att"] = amap[cov["att"]]
        else:
            cov.pop("att")
        nc.cover = json.dumps(cov)
    if keep_checklists:
        for cl in db.query(KChecklist).filter(KChecklist.card_id == c.id).order_by(KChecklist.pos).all():
            ncl = KChecklist(card_id=nc.id, title=cl.title, pos=cl.pos, hide_done=cl.hide_done)
            db.add(ncl)
            db.flush()
            for it in db.query(KItem).filter(KItem.checklist_id == cl.id).order_by(KItem.pos).all():
                db.add(KItem(checklist_id=ncl.id, text=it.text, done=False if c.is_template else it.done,
                             pos=it.pos, due=it.due, member=it.member if keep_members else None))
    if keep_comments:
        for cm in db.query(KComment).filter(KComment.card_id == c.id).all():
            db.add(KComment(card_id=nc.id, board_id=board.id, user_id=cm.user_id, author=cm.author, text=cm.text,
                            created_at=cm.created_at))
    return nc


@router.post("/store/kb/boards/{bid}/copy")
def copy_board(bid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    src, _ = _board(db, user, bid)
    title = (payload.get("title") or "").strip()[:200] or (src.title + " (copy)")
    b = _copy_board(db, src, user, title, keep_cards=bool(payload.get("keep_cards", True)))
    if payload.get("template"):
        b.is_template = True
    db.commit()
    return {"id": b.id}


# ---- members ------------------------------------------------------------------------------------

@router.post("/store/kb/boards/{bid}/members")
def add_member(bid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    b, role = _board(db, user, bid)
    if role != "admin" and b.visibility == "private":
        raise HTTPException(status_code=403, detail="Only an admin of this private board can add people.")
    ids = payload.get("user_ids") or ([payload["user_id"]] if payload.get("user_id") else [])
    r = payload.get("role") if payload.get("role") in BOARD_ROLES else "member"
    if r == "admin" and role != "admin":
        r = "member"
    users = _users(db, [int(i) for i in ids])
    added = []
    for uid, u in users.items():
        m = db.query(KMember).filter(KMember.board_id == b.id, KMember.user_id == uid).first()
        if m:
            continue
        db.add(KMember(board_id=b.id, user_id=uid, role=r))
        _note(db, uid, user, b, None, "board", f"added you to the board {b.title}")
        _act(db, b, user, "member_added", who=_uname(u))
        added.append(uid)
    _touch(db, b)
    db.commit()
    return {"added": added}


@router.patch("/store/kb/boards/{bid}/members/{uid}")
def member_role(bid: int, uid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    b, role = _board(db, user, bid, "admin")
    m = db.query(KMember).filter(KMember.board_id == b.id, KMember.user_id == uid).first()
    if not m:
        raise HTTPException(status_code=404, detail="Not on this board.")
    r = payload.get("role")
    if r not in BOARD_ROLES:
        raise HTTPException(status_code=400, detail="Admin, member or observer?")
    if m.role == "admin" and r != "admin":
        admins = db.query(KMember).filter(KMember.board_id == b.id, KMember.role == "admin").count()
        if admins <= 1:
            raise HTTPException(status_code=400, detail="A board needs at least one admin.")
    m.role = r
    _touch(db, b)
    db.commit()
    return {"ok": True}


@router.delete("/store/kb/boards/{bid}/members/{uid}")
def remove_member(bid: int, uid: int, db: Session = Depends(get_db), user: models.User = VIEW):
    b, role = _board(db, user, bid)
    if uid != user.id and role != "admin":
        raise HTTPException(status_code=403, detail="Only an admin of this board can remove people.")
    m = db.query(KMember).filter(KMember.board_id == b.id, KMember.user_id == uid).first()
    if not m:
        return {"ok": True}
    if m.role == "admin" and db.query(KMember).filter(KMember.board_id == b.id, KMember.role == "admin").count() <= 1:
        raise HTTPException(status_code=400, detail="A board needs at least one admin - make someone else admin first.")
    db.delete(m)
    for c in db.query(KCard).filter(KCard.board_id == b.id).all():
        ms = _j(c.members, [])
        if uid in ms:
            ms.remove(uid)
            c.members = json.dumps(ms)
    u = db.query(models.User).filter(models.User.id == uid).first()
    _act(db, b, user, "member_left" if uid == user.id else "member_removed", who=_uname(u))
    _touch(db, b)
    db.commit()
    return {"ok": True}


# ---- labels and custom fields -------------------------------------------------------------------

@router.post("/store/kb/boards/{bid}/labels")
def add_label(bid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    b, _ = _board(db, user, bid, "edit")
    color = payload.get("color") if payload.get("color") in LABEL_COLORS else "green"
    l = KLabel(board_id=b.id, name=(payload.get("name") or "")[:100], color=color, pos=_end_pos(db, KLabel, board_id=b.id))
    db.add(l)
    _touch(db, b)
    db.commit()
    return {"id": l.id}


@router.patch("/store/kb/labels/{lid}")
def edit_label(lid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    l = db.query(KLabel).filter(KLabel.id == lid).first()
    if not l:
        raise HTTPException(status_code=404, detail="Label gone.")
    b, _ = _board(db, user, l.board_id, "edit")
    if "name" in payload:
        l.name = (payload["name"] or "")[:100]
    if "color" in payload and payload["color"] in LABEL_COLORS:
        l.color = payload["color"]
    _touch(db, b)
    db.commit()
    return {"ok": True}


@router.delete("/store/kb/labels/{lid}")
def delete_label(lid: int, db: Session = Depends(get_db), user: models.User = VIEW):
    l = db.query(KLabel).filter(KLabel.id == lid).first()
    if not l:
        return {"ok": True}
    b, _ = _board(db, user, l.board_id, "edit")
    for c in db.query(KCard).filter(KCard.board_id == b.id).all():
        ls = _j(c.labels, [])
        if lid in ls:
            ls.remove(lid)
            c.labels = json.dumps(ls)
    db.delete(l)
    _touch(db, b)
    db.commit()
    return {"ok": True}


@router.post("/store/kb/boards/{bid}/fields")
def add_field(bid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    b, _ = _board(db, user, bid, "edit")
    t = payload.get("type") if payload.get("type") in ("text", "number", "date", "checkbox", "list") else "text"
    name = (payload.get("name") or "").strip()[:100]
    if not name:
        raise HTTPException(status_code=400, detail="Give the field a name.")
    opts = [{"id": uuid.uuid4().hex[:8], "text": str(o.get("text") if isinstance(o, dict) else o)[:100],
             "color": (o.get("color") if isinstance(o, dict) else "") or ""} for o in (payload.get("options") or []) if o]
    f = KField(board_id=b.id, name=name, type=t, options=json.dumps(opts), on_front=bool(payload.get("on_front", True)),
               pos=_end_pos(db, KField, board_id=b.id))
    db.add(f)
    _touch(db, b)
    db.commit()
    return {"id": f.id}


@router.patch("/store/kb/fields/{fid}")
def edit_field(fid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    f = db.query(KField).filter(KField.id == fid).first()
    if not f:
        raise HTTPException(status_code=404, detail="Field gone.")
    b, _ = _board(db, user, f.board_id, "edit")
    if "name" in payload:
        f.name = (payload["name"] or "").strip()[:100] or f.name
    if "on_front" in payload:
        f.on_front = bool(payload["on_front"])
    if "options" in payload:
        old = {o["id"]: o for o in _j(f.options, [])}
        new = []
        for o in payload["options"] or []:
            if not isinstance(o, dict) or not str(o.get("text", "")).strip():
                continue
            oid = o.get("id") if o.get("id") in old else uuid.uuid4().hex[:8]
            new.append({"id": oid, "text": str(o["text"])[:100], "color": o.get("color") or ""})
        f.options = json.dumps(new)
    _touch(db, b)
    db.commit()
    return {"ok": True}


@router.delete("/store/kb/fields/{fid}")
def delete_field(fid: int, db: Session = Depends(get_db), user: models.User = VIEW):
    f = db.query(KField).filter(KField.id == fid).first()
    if not f:
        return {"ok": True}
    b, _ = _board(db, user, f.board_id, "edit")
    for c in db.query(KCard).filter(KCard.board_id == b.id).all():
        v = _j(c.fields, {})
        if str(fid) in v:
            v.pop(str(fid))
            c.fields = json.dumps(v)
    db.delete(f)
    _touch(db, b)
    db.commit()
    return {"ok": True}


# ---- lists --------------------------------------------------------------------------------------

@router.post("/store/kb/boards/{bid}/lists")
def add_list(bid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    b, _ = _board(db, user, bid, "edit")
    t = (payload.get("title") or "").strip()[:200]
    if not t:
        raise HTTPException(status_code=400, detail="Enter a list title.")
    l = KList(board_id=b.id, title=t, pos=_pos_from(payload, db, KList, board_id=b.id, closed=False))
    db.add(l)
    _ensure_member(db, b, user)
    _act(db, b, user, "list_added", title=t)
    _touch(db, b)
    db.commit()
    return {"id": l.id, "pos": l.pos}


@router.patch("/store/kb/lists/{lid}")
def edit_list(lid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    l, b, _ = _list(db, user, lid)
    if "title" in payload:
        t = (payload["title"] or "").strip()[:200]
        if t and t != l.title:
            _act(db, b, user, "list_renamed", old=l.title, new=t)
            l.title = t
    if "pos" in payload:
        l.pos = float(payload["pos"])
        _renumber_if_tight(db, KList, board_id=b.id)
    if "board_id" in payload and int(payload["board_id"]) != b.id:
        nb, _ = _board(db, user, int(payload["board_id"]), "edit")
        l.board_id = nb.id
        l.pos = _end_pos(db, KList, board_id=nb.id)
        for c in db.query(KCard).filter(KCard.list_id == l.id).all():
            c.board_id = nb.id
            c.labels = "[]"
            c.no = nb.next_no or 1
            nb.next_no = c.no + 1
        _touch(db, nb)
    if "closed" in payload:
        l.closed = bool(payload["closed"])
        _act(db, b, user, "list_archived" if l.closed else "list_restored", title=l.title)
    for k in ("color", "wip", "collapsed"):
        if k in payload:
            setattr(l, k, (payload[k] or "")[:30] if k == "color" else (max(0, int(payload[k] or 0)) if k == "wip" else bool(payload[k])))
    _touch(db, b)
    db.commit()
    return {"ok": True}


@router.post("/store/kb/lists/{lid}/copy")
def copy_list(lid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    l, b, _ = _list(db, user, lid)
    nl = KList(board_id=b.id, title=(payload.get("title") or l.title)[:200], pos=l.pos + 0.5, color=l.color, wip=l.wip)
    db.add(nl)
    db.flush()
    for c in db.query(KCard).filter(KCard.list_id == l.id, KCard.closed == False).order_by(KCard.pos).all():  # noqa: E712
        nc = _clone_card(db, c, b, nl.id, c.pos)
        nc.no = b.next_no or 1
        b.next_no = nc.no + 1
    _renumber_if_tight(db, KList, board_id=b.id)
    _act(db, b, user, "list_copied", title=nl.title)
    _touch(db, b)
    db.commit()
    return {"id": nl.id}


@router.post("/store/kb/lists/{lid}/move-cards")
def move_all_cards(lid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    l, b, _ = _list(db, user, lid)
    to, _b2, _r = _list(db, user, int(payload.get("to") or 0))
    base = _end_pos(db, KCard, list_id=to.id)
    for i, c in enumerate(db.query(KCard).filter(KCard.list_id == l.id, KCard.closed == False).order_by(KCard.pos).all()):  # noqa: E712
        c.list_id = to.id
        c.board_id = to.board_id
        c.pos = base + i * 65536
        _run_rules(db, _b2, c, user, "card_moved", list_id=to.id)
        _run_rules(db, _b2, c, user, "card_added", list_id=to.id)
    _act(db, b, user, "list_moved_all", frm=l.title, to=to.title)
    _touch(db, b)
    if _b2.id != b.id:
        _touch(db, _b2)
    db.commit()
    return {"ok": True}


@router.post("/store/kb/lists/{lid}/archive-cards")
def archive_all_cards(lid: int, db: Session = Depends(get_db), user: models.User = VIEW):
    l, b, _ = _list(db, user, lid)
    n = 0
    for c in db.query(KCard).filter(KCard.list_id == l.id, KCard.closed == False).all():  # noqa: E712
        c.closed = True
        n += 1
    _act(db, b, user, "list_archived_cards", title=l.title, n=n)
    _touch(db, b)
    db.commit()
    return {"archived": n}


@router.post("/store/kb/lists/{lid}/sort")
def sort_list(lid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    l, b, _ = _list(db, user, lid)
    by = payload.get("by") or "created_new"
    cards = db.query(KCard).filter(KCard.list_id == l.id, KCard.closed == False).all()  # noqa: E712
    key = {"created_new": (lambda c: c.created_at or datetime.min, True),
           "created_old": (lambda c: c.created_at or datetime.min, False),
           "name": (lambda c: (c.title or "").lower(), False),
           "due": (lambda c: c.due or "9999", False)}.get(by, (lambda c: c.created_at or datetime.min, True))
    for i, c in enumerate(sorted(cards, key=key[0], reverse=key[1])):
        c.pos = (i + 1) * 65536
    _touch(db, b)
    db.commit()
    return {"ok": True}


# ---- cards --------------------------------------------------------------------------------------

@router.post("/store/kb/lists/{lid}/cards")
def add_card(lid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    l, b, _ = _list(db, user, lid)
    titles = payload.get("titles") or [payload.get("title")]
    titles = [str(t).strip()[:2000] for t in titles if t and str(t).strip()]
    if not titles:
        raise HTTPException(status_code=400, detail="Enter a title for this card.")
    tpl = None
    if payload.get("template_id"):
        tpl, tb, _r = _card(db, user, int(payload["template_id"]))
    pos = _pos_from(payload, db, KCard, list_id=l.id, closed=False)
    out = []
    for i, t in enumerate(titles):
        p = pos + i * 0.001 if payload.get("pos") not in (None, "", "bottom") else pos + i * 65536
        if tpl:
            c = _clone_card(db, tpl, b, l.id, p, lmap=None if tpl.board_id == b.id else {}, title=t,
                            keep_members=bool(payload.get("keep_members", True)))
            c.is_template = False
        else:
            c = KCard(board_id=b.id, list_id=l.id, title=t, pos=p, created_by=user.id,
                      labels=json.dumps([int(x) for x in payload.get("labels") or []]),
                      members=json.dumps([int(x) for x in payload.get("members") or []]))
            db.add(c)
        c.no = b.next_no or 1
        c.created_by = user.id
        b.next_no = c.no + 1
        db.flush()
        _act(db, b, user, "card_added", c, list=l.title, title=t)
        _run_rules(db, b, c, user, "card_created", list_id=l.id)
        _run_rules(db, b, c, user, "card_added", list_id=l.id)
        _run_rules(db, b, c, user, "card_titled", list_id=l.id)
        out.append(c.id)
    _renumber_if_tight(db, KCard, list_id=l.id)
    _ensure_member(db, b, user)
    _touch(db, b)
    db.commit()
    return {"ids": out, "id": out[0]}


def _card_full(db, c, b, user, role):
    counts = _counts(db, [c.id])
    atts_rows = db.query(KAttachment).filter(KAttachment.card_id == c.id).order_by(KAttachment.created_at.desc()).all()
    users = _users(db)
    atts = [_att_out(a, users) for a in atts_rows]
    front = _front(c, counts, {a["id"]: a for a in atts}, user.id)
    cls = []
    for cl in db.query(KChecklist).filter(KChecklist.card_id == c.id).order_by(KChecklist.pos, KChecklist.id).all():
        items = db.query(KItem).filter(KItem.checklist_id == cl.id).order_by(KItem.pos, KItem.id).all()
        cls.append({"id": cl.id, "title": cl.title, "hide_done": bool(cl.hide_done),
                    "items": [{"id": i.id, "text": i.text, "done": bool(i.done), "pos": i.pos, "due": i.due or "",
                               "member": i.member} for i in items]})
    comments = db.query(KComment).filter(KComment.card_id == c.id).order_by(KComment.created_at.desc()).all()
    acts = db.query(KActivity).filter(KActivity.card_id == c.id).order_by(KActivity.created_at.desc()).limit(200).all()
    lst = db.query(KList).filter(KList.id == c.list_id).first()
    return {**front, "desc": c.desc or "", "list_title": lst.title if lst else "", "board_id": b.id, "board_title": b.title,
            "role": role, "watchers": _j(c.watchers, []),
            "checklists": cls, "attachments": atts,
            "comments": [{"id": m.id, "user_id": m.user_id, "who": _uname(users.get(m.user_id)) or m.author or "Someone",
                          "initials": _initials(_uname(users.get(m.user_id)) or m.author), "text": m.text,
                          "at": _iso(m.created_at), "edited": bool(m.edited_at), "mine": m.user_id == user.id} for m in comments],
            "activity": [_act_out(a, users) for a in acts],
            "created_by": _uname(users.get(c.created_by)),
            "time_entries": [{"id": t.id, "hours": t.hours, "day": t.day, "note": t.note, "who": _uname(users.get(t.user_id)),
                              "mine": t.user_id == user.id}
                             for t in db.query(KTime).filter(KTime.card_id == c.id).order_by(KTime.day.desc(), KTime.id.desc()).all()],
            "repeat": next(({"id": r.id, "every": r.every, "nth": r.nth, "time": r.time, "next_on": r.next_on,
                             "list_id": r.list_id, "due_days": r.due_days, "enabled": bool(r.enabled), "made": r.made}
                            for r in db.query(KRepeat).filter(KRepeat.card_id == c.id).all()), None),
            "linked": _linked(db, user, _j(c.links, [])),
            "mirrors": [{"id": m.id, "board_id": m.board_id} for m in db.query(KCard).filter(KCard.mirror_of == c.id, KCard.closed == False).all()]}  # noqa: E712


def _linked(db, user, ids):
    out = []
    if not ids:
        return out
    boards = {b.id: b for b in _visible_boards(db, user)}
    lists = {}
    for c in db.query(KCard).filter(KCard.id.in_(ids)).all():
        if c.board_id not in boards:
            continue
        if c.list_id not in lists:
            l = db.query(KList).filter(KList.id == c.list_id).first()
            lists[c.list_id] = l.title if l else ""
        out.append({"id": c.id, "no": c.no, "title": c.title, "board_id": c.board_id, "board": boards[c.board_id].title,
                    "list": lists[c.list_id], "closed": c.closed, "due_complete": bool(c.due_complete)})
    return out


def _act_out(a, users):
    u = users.get(a.user_id)
    who = _uname(u) or "Automation"
    return {"id": a.id, "kind": a.kind, "who": who, "initials": _initials(who), "card_id": a.card_id,
            "data": _j(a.data, {}), "at": _iso(a.created_at)}


@router.get("/store/kb/cards/{cid}")
def get_card(cid: int, db: Session = Depends(get_db), user: models.User = VIEW):
    raw, rb, rrole = _card(db, user, cid, follow=False)
    src = _source_of(db, raw)
    if src is None:
        return _card_full(db, raw, rb, user, rrole)
    # A mirror opens as its source - its details, comments and checklists - but sits
    # where the mirror sits, so moving or archiving it moves the mirror, as in Trello.
    sb, srole = _board(db, user, src.board_id)
    out = _card_full(db, src, sb, user, srole if rrole != "observer" else rrole)
    out["labels"] = _map_labels(db, out.get("labels") or [], src.board_id, raw.board_id)
    db.commit()
    out.update({"id": raw.id, "board_id": raw.board_id, "list_id": raw.list_id, "closed": bool(raw.closed), "pos": raw.pos,
                "mirror_of": src.id, "mirror": {"board": sb.title, "board_id": sb.id, "card_id": src.id, "closed": bool(src.closed)}})
    return out


def _map_labels(db, ids, from_bid, to_bid):
    """Labels are a board's own: the same label on another board is the one with the
    same name and colour (made there if it is missing)."""
    if from_bid == to_bid:
        return [int(x) for x in ids]
    src = {l.id: l for l in db.query(KLabel).filter(KLabel.board_id == from_bid).all()}
    dst = {((l.name or ""), (l.color or "")): l.id for l in db.query(KLabel).filter(KLabel.board_id == to_bid).all()}
    out = []
    for x in ids:
        l = src.get(int(x))
        if not l:
            continue
        k = ((l.name or ""), (l.color or ""))
        if k not in dst:
            nl = KLabel(board_id=to_bid, name=l.name or "", color=l.color or "green", pos=_end_pos(db, KLabel, board_id=to_bid))
            db.add(nl)
            db.flush()
            dst[k] = nl.id
        out.append(dst[k])
    return out


MIRROR_OWN = ("list_id", "pos", "closed", "board_id")     # where a mirror sits is its own; the rest is the source's


@router.patch("/store/kb/cards/{cid}")
def edit_card(cid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    raw, rb, _r = _card(db, user, cid, "edit", follow=False)
    src = _source_of(db, raw)
    out = {}
    if src is not None:
        own = {k: payload[k] for k in MIRROR_OWN if k in payload}
        rest = {k: v for k, v in payload.items() if k not in MIRROR_OWN}
        if rest:
            sb, _sr = _board(db, user, src.board_id, "edit")
            if "labels" in rest:
                rest["labels"] = _map_labels(db, rest["labels"] or [], raw.board_id, src.board_id)
            _edit_card(db, user, src, sb, rest)
        if own:
            out = _edit_card(db, user, raw, rb, own)
        _touch(db, rb)
        db.commit()
        return {"ok": True, "pos": raw.pos, "list_id": raw.list_id, **({k: v for k, v in out.items() if k != "ok"})}
    out = _edit_card(db, user, raw, rb, payload)
    db.commit()
    return out


def _edit_card(db, user, c, b, payload):
    events = []
    if "title" in payload:
        t = (payload["title"] or "").strip()[:2000]
        if t and t != c.title:
            _act(db, b, user, "card_renamed", c, old=c.title, new=t)
            c.title = t
            events.append(("card_titled", {}))
    if "desc" in payload:
        if (payload["desc"] or "") != (c.desc or ""):
            _act(db, b, user, "card_desc", c)
        c.desc = (payload["desc"] or "")[:50000]
        for u in _mentions(db, c.desc):
            _note(db, u.id, user, b, c, "mention", f"mentioned you on the card {c.title}")
    target_board = b
    if "board_id" in payload and int(payload["board_id"]) != b.id:
        nb, _r = _board(db, user, int(payload["board_id"]), "edit")
        old_labels = {l.id: (l.name, l.color) for l in db.query(KLabel).filter(KLabel.board_id == b.id).all()}
        new_labels = {(l.name, l.color): l.id for l in db.query(KLabel).filter(KLabel.board_id == nb.id).all()}
        c.labels = json.dumps([new_labels[old_labels[x]] for x in _j(c.labels, []) if x in old_labels and old_labels[x] in new_labels])
        c.board_id = nb.id
        c.no = nb.next_no or 1
        nb.next_no = c.no + 1
        db.query(KAttachment).filter(KAttachment.card_id == c.id).update({"board_id": nb.id}, synchronize_session=False)
        db.query(KComment).filter(KComment.card_id == c.id).update({"board_id": nb.id}, synchronize_session=False)
        db.query(KActivity).filter(KActivity.card_id == c.id).update({"board_id": nb.id}, synchronize_session=False)
        _act(db, b, user, "card_moved_board", c, to=nb.title, title=c.title)
        target_board = nb
        if "list_id" not in payload:
            fl = db.query(KList).filter(KList.board_id == nb.id, KList.closed == False).order_by(KList.pos).first()  # noqa: E712
            if not fl:
                raise HTTPException(status_code=400, detail="That board has no list to put the card in.")
            payload["list_id"] = fl.id
    if "list_id" in payload and int(payload["list_id"]) != c.list_id:
        nl = db.query(KList).filter(KList.id == int(payload["list_id"]), KList.board_id == target_board.id).first()
        if not nl:
            raise HTTPException(status_code=400, detail="That list is not on this board.")
        ol = db.query(KList).filter(KList.id == c.list_id).first()
        c.list_id = nl.id
        _act(db, target_board, user, "card_moved", c, frm=ol.title if ol else "", to=nl.title, title=c.title)
        events.append(("card_moved", {"list_id": nl.id}))
        events.append(("card_added", {"list_id": nl.id}))
        if "pos" not in payload:
            c.pos = _end_pos(db, KCard, list_id=nl.id)
    if "pos" in payload:
        c.pos = _pos_from(payload, db, KCard, list_id=c.list_id, closed=False)
        _renumber_if_tight(db, KCard, list_id=c.list_id)
    for k in ("start", "due", "location"):
        if k in payload:
            v = (payload[k] or "")[:40 if k != "location" else 300]
            if k == "due" and v != (c.due or ""):
                _act(db, target_board, user, "card_due", c, due=v)
                if v:
                    events.append(("due_set", {}))
            setattr(c, k, v)
    if "reminder" in payload:
        c.reminder = int(payload["reminder"] if payload["reminder"] is not None else -1)
    if "due_complete" in payload:
        v = bool(payload["due_complete"])
        if v != bool(c.due_complete):
            _act(db, target_board, user, "card_complete" if v else "card_incomplete", c)
            if v:
                events.append(("card_complete", {}))
        c.due_complete = v
    if "labels" in payload:
        old = set(_j(c.labels, []))
        new = [int(x) for x in payload["labels"] or []]
        for x in set(new) - old:
            events.append(("label_added", {"label_id": x}))
        c.labels = json.dumps(new)
    if "members" in payload:
        old = set(_j(c.members, []))
        new = [int(x) for x in payload["members"] or []]
        users = _users(db, list(set(new) | old))
        for x in set(new) - old:
            events.append(("member_added", {"user_id": x}))
            _act(db, target_board, user, "card_member_added", c, who=_uname(users.get(x)))
            _note(db, x, user, target_board, c, "added", f"added you to the card {c.title}")
            ws = _j(c.watchers, [])
            if x not in ws:
                c.watchers = json.dumps(ws + [x])
        for x in old - set(new):
            _act(db, target_board, user, "card_member_removed", c, who=_uname(users.get(x)))
        c.members = json.dumps(new)
    if "watch" in payload:
        ws = _j(c.watchers, [])
        if payload["watch"] and user.id not in ws:
            ws.append(user.id)
        if not payload["watch"] and user.id in ws:
            ws.remove(user.id)
        c.watchers = json.dumps(ws)
    if "cover" in payload:
        cov = payload["cover"] or {}
        clean = {}
        if cov.get("color"):
            clean["color"] = str(cov["color"])[:30]
        if cov.get("att"):
            clean["att"] = int(cov["att"])
        if clean:
            clean["size"] = "full" if cov.get("size") == "full" else "normal"
            clean["text"] = "dark" if cov.get("text") == "dark" else "light"
        c.cover = json.dumps(clean)
    if "fields" in payload and isinstance(payload["fields"], dict):
        v = _j(c.fields, {})
        for k2, val in payload["fields"].items():
            if val in (None, "", False):
                v.pop(str(k2), None)
            else:
                v[str(k2)] = val
        c.fields = json.dumps(v)
    if "is_template" in payload:
        c.is_template = bool(payload["is_template"])
    if "vote" in payload:
        vs = _j(c.votes, [])
        if payload["vote"] and user.id not in vs:
            vs.append(user.id)
        if not payload["vote"] and user.id in vs:
            vs.remove(user.id)
        c.votes = json.dumps(vs)
    if "priority" in payload:
        c.priority = payload["priority"] if payload["priority"] in ("highest", "high", "medium", "low", "lowest") else ""
    for k in ("points", "estimate"):
        if k in payload:
            try:
                setattr(c, k, float(payload[k]) if payload[k] not in (None, "") else None)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="Enter a number.")
    if "links" in payload:
        c.links = json.dumps([int(x) for x in payload["links"] or [] if int(x) != c.id])
    if "closed" in payload:
        v = bool(payload["closed"])
        if v != bool(c.closed):
            _act(db, target_board, user, "card_archived" if v else "card_restored", c, title=c.title)
            if v:
                events.append(("card_archived", {}))
            if not v:
                lst = db.query(KList).filter(KList.id == c.list_id).first()
                if not lst or lst.closed:
                    fl = db.query(KList).filter(KList.board_id == target_board.id, KList.closed == False).order_by(KList.pos).first()  # noqa: E712
                    if fl:
                        c.list_id = fl.id
        c.closed = v
    c.updated_at = _now()
    for ev, ctx in events:
        _run_rules(db, target_board, c, user, ev, **ctx)
    _ensure_member(db, target_board, user)
    _touch(db, b)
    if target_board.id != b.id:
        _touch(db, target_board)
    return {"ok": True, "pos": c.pos, "list_id": c.list_id}


@router.post("/store/kb/cards/{cid}/copy")
def copy_card(cid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    c, b, _ = _card(db, user, cid)
    tb = b
    if payload.get("board_id") and int(payload["board_id"]) != b.id:
        tb, _r = _board(db, user, int(payload["board_id"]), "edit")
    lid = int(payload.get("list_id") or c.list_id)
    if not db.query(KList).filter(KList.id == lid, KList.board_id == tb.id).first():
        raise HTTPException(status_code=400, detail="Pick a list on that board.")
    keep = payload.get("keep") or {}
    lmap = None
    if tb.id != b.id:
        old = {l.id: (l.name, l.color) for l in db.query(KLabel).filter(KLabel.board_id == b.id).all()}
        new = {(l.name, l.color): l.id for l in db.query(KLabel).filter(KLabel.board_id == tb.id).all()}
        lmap = {k: new.get(v) for k, v in old.items()}
    pos = _pos_from(payload, db, KCard, list_id=lid, closed=False)
    nc = _clone_card(db, c, tb, lid, pos, lmap=lmap, keep_members=keep.get("members", True),
                     keep_checklists=keep.get("checklists", True), keep_comments=keep.get("comments", False),
                     keep_atts=keep.get("attachments", True), title=(payload.get("title") or c.title)[:2000])
    if not keep.get("labels", True):
        nc.labels = "[]"
    nc.no = tb.next_no or 1
    tb.next_no = nc.no + 1
    nc.created_by = user.id
    db.flush()
    _act(db, tb, user, "card_copied", nc, source=c.title)
    for ev in ("card_created", "card_added", "card_titled"):
        _run_rules(db, tb, nc, user, ev, list_id=lid)
    _renumber_if_tight(db, KCard, list_id=lid)
    _touch(db, tb)
    db.commit()
    return {"id": nc.id}


@router.delete("/store/kb/cards/{cid}")
def delete_card(cid: int, db: Session = Depends(get_db), user: models.User = VIEW):
    c, b, _ = _card(db, user, cid, "edit", follow=False)
    _act(db, b, user, "card_deleted", None, title=c.title, no=c.no)
    db.query(KActivity).filter(KActivity.card_id == c.id).delete(synchronize_session=False)
    _delete_cards(db, [c.id])
    _touch(db, b)
    db.commit()
    return {"ok": True}


# ---- checklists ------------------------------------------------------------------------------------

def _check_done_event(db, c, b, user):
    items = (db.query(KItem).join(KChecklist, KItem.checklist_id == KChecklist.id)
             .filter(KChecklist.card_id == c.id).all())
    if items and all(i.done for i in items):
        _run_rules(db, b, c, user, "checklist_done")


@router.post("/store/kb/cards/{cid}/checklists")
def add_checklist(cid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    c, b, _ = _card(db, user, cid, "edit")
    cl = KChecklist(card_id=c.id, title=(payload.get("title") or "Checklist").strip()[:200] or "Checklist",
                    pos=_end_pos(db, KChecklist, card_id=c.id))
    db.add(cl)
    db.flush()
    if payload.get("copy_from"):
        src = db.query(KChecklist).filter(KChecklist.id == int(payload["copy_from"])).first()
        if src:
            _card(db, user, src.card_id)
            for it in db.query(KItem).filter(KItem.checklist_id == src.id).order_by(KItem.pos).all():
                db.add(KItem(checklist_id=cl.id, text=it.text, pos=it.pos))
    for i, t in enumerate([x for x in payload.get("items") or [] if str(x).strip()]):
        db.add(KItem(checklist_id=cl.id, text=str(t)[:1000], pos=(i + 1) * 65536))
    _act(db, b, user, "checklist_added", c, title=cl.title)
    c.updated_at = _now()
    _touch(db, b)
    db.commit()
    return {"id": cl.id}


def _cl(db, user, clid):
    cl = db.query(KChecklist).filter(KChecklist.id == clid).first()
    if not cl:
        raise HTTPException(status_code=404, detail="Checklist gone.")
    c, b, _ = _card(db, user, cl.card_id, "edit")
    return cl, c, b


@router.patch("/store/kb/checklists/{clid}")
def edit_checklist(clid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    cl, c, b = _cl(db, user, clid)
    if "title" in payload:
        cl.title = (payload["title"] or "").strip()[:200] or cl.title
    if "hide_done" in payload:
        cl.hide_done = bool(payload["hide_done"])
    if "pos" in payload:
        cl.pos = float(payload["pos"])
    _touch(db, b)
    db.commit()
    return {"ok": True}


@router.delete("/store/kb/checklists/{clid}")
def delete_checklist(clid: int, db: Session = Depends(get_db), user: models.User = VIEW):
    cl, c, b = _cl(db, user, clid)
    db.query(KItem).filter(KItem.checklist_id == cl.id).delete(synchronize_session=False)
    _act(db, b, user, "checklist_removed", c, title=cl.title)
    db.delete(cl)
    _touch(db, b)
    db.commit()
    return {"ok": True}


@router.post("/store/kb/checklists/{clid}/items")
def add_item(clid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    cl, c, b = _cl(db, user, clid)
    texts = payload.get("texts") or [payload.get("text")]
    ids = []
    base = _end_pos(db, KItem, checklist_id=cl.id)
    for i, t in enumerate([str(x).strip() for x in texts if x and str(x).strip()]):
        it = KItem(checklist_id=cl.id, text=t[:1000], pos=base + i * 65536, due=(payload.get("due") or "")[:40],
                   member=int(payload["member"]) if payload.get("member") else None)
        db.add(it)
        db.flush()
        ids.append(it.id)
    if not ids:
        raise HTTPException(status_code=400, detail="Type the item first.")
    c.updated_at = _now()
    _touch(db, b)
    db.commit()
    return {"ids": ids, "id": ids[0]}


@router.patch("/store/kb/items/{iid}")
def edit_item(iid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    it = db.query(KItem).filter(KItem.id == iid).first()
    if not it:
        raise HTTPException(status_code=404, detail="Item gone.")
    cl, c, b = _cl(db, user, it.checklist_id)
    if "text" in payload:
        it.text = (payload["text"] or "").strip()[:1000] or it.text
    if "done" in payload:
        v = bool(payload["done"])
        if v != bool(it.done):
            _act(db, b, user, "item_done" if v else "item_undone", c, text=it.text)
        it.done = v
    if "due" in payload:
        it.due = (payload["due"] or "")[:40]
    if "member" in payload:
        it.member = int(payload["member"]) if payload["member"] else None
        if it.member:
            _note(db, it.member, user, b, c, "item", f"assigned you \"{it.text[:80]}\" on {c.title}")
    if "checklist_id" in payload and int(payload["checklist_id"]) != cl.id:
        ncl, _c2, _b2 = _cl(db, user, int(payload["checklist_id"]))
        it.checklist_id = ncl.id
    if "pos" in payload:
        it.pos = float(payload["pos"])
        _renumber_if_tight(db, KItem, checklist_id=it.checklist_id)
    c.updated_at = _now()
    db.flush()
    if payload.get("done"):
        _run_rules(db, b, c, user, "item_done")
        _check_done_event(db, c, b, user)
    _touch(db, b)
    db.commit()
    return {"ok": True}


@router.delete("/store/kb/items/{iid}")
def delete_item(iid: int, db: Session = Depends(get_db), user: models.User = VIEW):
    it = db.query(KItem).filter(KItem.id == iid).first()
    if not it:
        return {"ok": True}
    cl, c, b = _cl(db, user, it.checklist_id)
    db.delete(it)
    _touch(db, b)
    db.commit()
    return {"ok": True}


@router.post("/store/kb/items/{iid}/to-card")
def item_to_card(iid: int, db: Session = Depends(get_db), user: models.User = VIEW):
    """Convert a checklist item to a card - Trello's 'Convert to card'."""
    it = db.query(KItem).filter(KItem.id == iid).first()
    if not it:
        raise HTTPException(status_code=404, detail="Item gone.")
    cl, c, b = _cl(db, user, it.checklist_id)
    nc = KCard(board_id=b.id, list_id=c.list_id, title=it.text, pos=c.pos + 0.5, created_by=user.id,
               members=json.dumps([it.member] if it.member else []), due=it.due or "")
    nc.no = b.next_no or 1
    b.next_no = nc.no + 1
    db.add(nc)
    db.delete(it)
    db.flush()
    _act(db, b, user, "card_added", nc, list="", title=nc.title, from_item=c.title)
    _renumber_if_tight(db, KCard, list_id=c.list_id)
    _touch(db, b)
    db.commit()
    return {"id": nc.id}


# ---- comments ---------------------------------------------------------------------------------------

@router.post("/store/kb/cards/{cid}/comments")
def add_comment(cid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    c, b, role = _card(db, user, cid)
    if role == "observer" and _j(b.prefs, {}).get("comments") == "members":
        raise HTTPException(status_code=403, detail="Observers cannot comment on this board.")
    t = (payload.get("text") or "").strip()
    if not t:
        raise HTTPException(status_code=400, detail="Write a comment first.")
    m = KComment(card_id=c.id, board_id=b.id, user_id=user.id, text=t[:20000])
    db.add(m)
    told = set()
    for u in _mentions(db, t):
        _note(db, u.id, user, b, c, "mention", f"mentioned you on {c.title}: {t[:160]}")
        told.add(u.id)
    for uid in set(_j(c.watchers, [])) | set(_j(c.members, [])):
        if uid not in told:
            _note(db, uid, user, b, c, "comment", f"commented on {c.title}: {t[:160]}")
    c.updated_at = _now()
    db.flush()
    _run_rules(db, b, c, user, "comment_added")
    _touch(db, b)
    db.commit()
    return {"id": m.id}


@router.patch("/store/kb/comments/{mid}")
def edit_comment(mid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    m = db.query(KComment).filter(KComment.id == mid).first()
    if not m:
        raise HTTPException(status_code=404, detail="Comment gone.")
    c, b, role = _card(db, user, m.card_id)
    if m.user_id != user.id:
        raise HTTPException(status_code=403, detail="You can only edit your own comments.")
    t = (payload.get("text") or "").strip()
    if t:
        m.text = t[:20000]
        m.edited_at = _now()
    _touch(db, b)
    db.commit()
    return {"ok": True}


@router.delete("/store/kb/comments/{mid}")
def delete_comment(mid: int, db: Session = Depends(get_db), user: models.User = VIEW):
    m = db.query(KComment).filter(KComment.id == mid).first()
    if not m:
        return {"ok": True}
    c, b, role = _card(db, user, m.card_id)
    if m.user_id != user.id and role != "admin":
        raise HTTPException(status_code=403, detail="You can only delete your own comments.")
    db.delete(m)
    _touch(db, b)
    db.commit()
    return {"ok": True}


# ---- attachments ------------------------------------------------------------------------------------

def _save_image(data, base):
    """Photo -> no wider than 2000 px, plus a 600 px copy for covers.
    Returns (path, thumb, w, h, edge colour) or None if it is not a picture Pillow reads."""
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return None
    try:
        im = Image.open(io.BytesIO(data))
        im = ImageOps.exif_transpose(im)
    except Exception:
        return None
    fmt = "PNG" if (im.mode in ("RGBA", "LA", "P") and im.format == "PNG") else "JPEG"
    ext = "png" if fmt == "PNG" else "jpg"
    if fmt == "JPEG" and im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    big = im.copy()
    big.thumbnail((2000, 2000))
    d = _store_dir()
    path = f"{base}.{ext}"
    big.save(os.path.join(d, path), fmt, **({"quality": 85, "optimize": True} if fmt == "JPEG" else {"optimize": True}))
    th = im.copy()
    th.thumbnail((600, 600))
    tpath = f"{base}_t.{ext}"
    th.save(os.path.join(d, tpath), fmt, **({"quality": 80} if fmt == "JPEG" else {}))
    try:
        px = th.convert("RGB").resize((1, 1)).getpixel((0, 0))
        edge = "#%02x%02x%02x" % px
    except Exception:
        edge = ""
    return path, tpath, big.width, big.height, edge


@router.post("/store/kb/cards/{cid}/attachments")
async def add_attachment(cid: int, request: Request, file: UploadFile = File(None), url: str = Form(""), name: str = Form(""),
                         cover: str = Form(""), db: Session = Depends(get_db), user: models.User = VIEW):
    c, b, _ = _card(db, user, cid, "edit")
    if file is None and not url.strip():
        raise HTTPException(status_code=400, detail="Choose a file or paste a link.")
    a = KAttachment(card_id=c.id, board_id=b.id, user_id=user.id)
    if file is not None:
        data = await file.read()
        if len(data) > MAX_FILE:
            raise HTTPException(status_code=400, detail="That file is over 25 MB.")
        if not data:
            raise HTTPException(status_code=400, detail="That file is empty.")
        a.name = (name or file.filename or "file")[:200]
        a.mime = (file.content_type or "application/octet-stream")[:100]
        sub = f"{b.id}"
        os.makedirs(os.path.join(_store_dir(), sub), exist_ok=True)
        base = f"{sub}/{uuid.uuid4().hex}"
        saved = _save_image(data, base) if a.mime.startswith("image/") and "svg" not in a.mime else None
        if saved:
            a.path, a.thumb, a.width, a.height, a.edge = saved
            a.mime = "image/png" if a.path.endswith(".png") else "image/jpeg"
            a.size = os.path.getsize(os.path.join(_store_dir(), a.path))
        else:
            ext = os.path.splitext(a.name)[1][:10].lower()
            a.path = base + re.sub(r"[^.\w]", "", ext)
            with open(os.path.join(_store_dir(), a.path), "wb") as f:
                f.write(data)
            a.size = len(data)
    else:
        u = url.strip()[:2000]
        if not re.match(r"^https?://", u, re.I):
            u = "https://" + u
        a.url = u
        a.name = (name or u)[:200]
    db.add(a)
    db.flush()
    cov = _j(c.cover, {})
    if (cover == "1" or (_j(b.prefs, {}).get("auto_cover", True) and not cov)) and a.path and a.mime.startswith("image/"):
        c.cover = json.dumps({"att": a.id, "size": "normal"})
    _act(db, b, user, "attached", c, name=a.name)
    c.updated_at = _now()
    _touch(db, b)
    db.commit()
    return _att_out(a, _users(db, [user.id]))


@router.patch("/store/kb/attachments/{aid}")
def rename_attachment(aid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    a = db.query(KAttachment).filter(KAttachment.id == aid).first()
    if not a:
        raise HTTPException(status_code=404, detail="Attachment gone.")
    c, b, _ = _card(db, user, a.card_id, "edit")
    if payload.get("name"):
        a.name = payload["name"][:200]
    if "url" in payload and a.url and not a.path:
        a.url = payload["url"][:2000]
    _touch(db, b)
    db.commit()
    return {"ok": True}


@router.delete("/store/kb/attachments/{aid}")
def delete_attachment(aid: int, db: Session = Depends(get_db), user: models.User = VIEW):
    a = db.query(KAttachment).filter(KAttachment.id == aid).first()
    if not a:
        return {"ok": True}
    c, b, _ = _card(db, user, a.card_id, "edit")
    cov = _j(c.cover, {})
    if cov.get("att") == a.id:
        c.cover = "{}"
    if b.bg == f"att:{a.id}":
        b.bg = "blue"
    still = db.query(KAttachment).filter(KAttachment.path == a.path, KAttachment.id != a.id).count() if a.path else 0
    if not still:
        _remove_files(a)
    _act(db, b, user, "detached", c, name=a.name)
    db.delete(a)
    _touch(db, b)
    db.commit()
    return {"ok": True}


@router.get("/store/kb/f/{aid}/{exp}/{sig}/{kind}/{name}")
def get_file(aid: int, exp: int, sig: str, kind: str, name: str, db: Session = Depends(get_db)):
    if not hmac.compare_digest(sig, _sign(aid, exp)) or exp < time.time():
        raise HTTPException(status_code=403, detail="This link has run out - open the card again.")
    a = db.query(KAttachment).filter(KAttachment.id == aid).first()
    if not a or not a.path:
        raise HTTPException(status_code=404, detail="Gone.")
    p = os.path.join(_store_dir(), a.thumb if (kind == "t" and a.thumb) else a.path)
    if not os.path.exists(p):
        raise HTTPException(status_code=404, detail="The file is missing on the server.")
    inline = (a.mime or "").startswith(("image/", "video/", "audio/")) or a.mime == "application/pdf"
    fname = re.sub(r"[^\w. -]", "_", a.name or "file")[:120]
    disp = ("inline" if inline else "attachment") + '; filename="' + fname + '"'
    return FileResponse(p, media_type=a.mime or "application/octet-stream",
                        headers={"Cache-Control": "private, max-age=86400", "Content-Disposition": disp})


@router.post("/store/kb/boards/{bid}/background")
async def board_background(bid: int, file: UploadFile = File(...), db: Session = Depends(get_db), user: models.User = VIEW):
    """A photo of your own behind the board."""
    b, _ = _board(db, user, bid, "edit")
    data = await file.read()
    if len(data) > MAX_FILE:
        raise HTTPException(status_code=400, detail="That photo is over 25 MB.")
    os.makedirs(os.path.join(_store_dir(), str(b.id)), exist_ok=True)
    saved = _save_image(data, f"{b.id}/bg_{uuid.uuid4().hex}")
    if not saved:
        raise HTTPException(status_code=400, detail="That is not a photo.")
    a = KAttachment(card_id=0, board_id=b.id, name=file.filename or "background", user_id=user.id, mime="image/jpeg")
    a.path, a.thumb, a.width, a.height, a.edge = saved
    db.add(a)
    db.flush()
    b.bg = f"att:{a.id}"
    _touch(db, b)
    db.commit()
    return {"bg": b.bg, "url": _file_url(a)}


# ---- archive, activity, search ------------------------------------------------------------------------

@router.get("/store/kb/boards/{bid}/archived")
def archived(bid: int, db: Session = Depends(get_db), user: models.User = VIEW):
    b, role = _board(db, user, bid)
    lists = db.query(KList).filter(KList.board_id == b.id).all()
    names = {l.id: l.title for l in lists}
    cards = db.query(KCard).filter(KCard.board_id == b.id, KCard.closed == True).order_by(KCard.updated_at.desc()).all()  # noqa: E712
    counts = _counts(db, [c.id for c in cards])
    atts = _cover_atts(db, cards)
    return {"cards": [{**_front(c, counts, atts, user.id), "list_title": names.get(c.list_id, "")} for c in cards],
            "lists": [{"id": l.id, "title": l.title} for l in lists if l.closed]}


@router.get("/store/kb/boards/{bid}/activity")
def board_activity(bid: int, before: int = 0, only: str = "", db: Session = Depends(get_db), user: models.User = VIEW):
    b, _ = _board(db, user, bid)
    users = _users(db)
    q = db.query(KActivity).filter(KActivity.board_id == b.id)
    if before:
        q = q.filter(KActivity.id < before)
    acts = [_act_out(a, users) for a in q.order_by(KActivity.id.desc()).limit(60).all()]
    if only != "activity":
        cq = db.query(KComment).filter(KComment.board_id == b.id)
        cms = cq.order_by(KComment.id.desc()).limit(60).all()
        cards = {c.id: c.title for c in db.query(KCard).filter(KCard.id.in_([m.card_id for m in cms] or [0])).all()}
        for m in cms:
            who = _uname(users.get(m.user_id)) or m.author or "Someone"
            acts.append({"id": -m.id, "kind": "comment", "who": who, "initials": _initials(who), "card_id": m.card_id,
                         "data": {"text": m.text, "title": cards.get(m.card_id, "")}, "at": _iso(m.created_at)})
        acts.sort(key=lambda x: x["at"] or "", reverse=True)
    titles = {c.id: c.title for c in db.query(KCard.id, KCard.title).filter(KCard.board_id == b.id).all()}
    for a in acts:
        if a["card_id"] and "title" not in a["data"]:
            a["data"]["title"] = titles.get(a["card_id"], "")
    return {"activity": acts[:80], "more": len(acts) >= 60}


@router.get("/store/kb/search")
def search(q: str = "", db: Session = Depends(get_db), user: models.User = VIEW):
    q = (q or "").strip()
    if not q:
        return {"boards": [], "cards": []}
    bs = _visible_boards(db, user)
    bids = {b.id: b for b in bs}
    ql = q.lower()
    boards = [{"id": b.id, "title": b.title, "bg": b.bg} for b in bs if ql in (b.title or "").lower()][:8]
    like = f"%{q}%"
    cards = (db.query(KCard).filter(KCard.board_id.in_(list(bids) or [0]),
                                    (KCard.title.ilike(like)) | (KCard.desc.ilike(like)))
             .order_by(KCard.closed, KCard.updated_at.desc()).limit(40).all())
    num = re.fullmatch(r"#?(\d+)", q)
    if num:
        cards = db.query(KCard).filter(KCard.board_id.in_(list(bids) or [0]), KCard.no == int(num.group(1))).limit(20).all() + cards
    lists = {l.id: l.title for l in db.query(KList).filter(KList.id.in_([c.list_id for c in cards] or [0])).all()}
    seen, out = set(), []
    for c in cards:
        if c.id in seen:
            continue
        seen.add(c.id)
        out.append({"id": c.id, "no": c.no, "title": c.title, "board_id": c.board_id, "board": bids[c.board_id].title,
                    "list": lists.get(c.list_id, ""), "closed": c.closed, "labels": _j(c.labels, [])})
    return {"boards": boards, "cards": out[:30]}


# ---- rules (automation) -----------------------------------------------------------------------------

@router.get("/store/kb/boards/{bid}/rules")
def get_rules(bid: int, db: Session = Depends(get_db), user: models.User = VIEW):
    b, _ = _board(db, user, bid)
    rs = db.query(KRule).filter(KRule.board_id == b.id).order_by(KRule.id).all()
    return {"rules": [{"id": r.id, "trigger": _j(r.trigger, {}), "actions": _j(r.actions, []), "enabled": bool(r.enabled),
                       "runs": r.runs or 0, "log": _j(r.log, [])[:10], "last_run": r.last_run or "", "words": _rule_words(db, r)}
                      for r in rs], "triggers": TRIGGERS, "actions": ACTIONS}


def _clean_rule(payload, db=None, user=None):
    t = payload.get("trigger") or {}
    if t.get("type") not in TRIGGERS:
        raise HTTPException(status_code=400, detail="Pick when the rule should run.")
    if t["type"] == "schedule":
        if t.get("every") not in ("day", "weekday", "week", "month"):
            raise HTTPException(status_code=400, detail="Every day, week or month?")
        t["time"] = (t.get("time") or "09:00")[:5]
    if t["type"] == "card_titled" and not [w for w in (t.get("words") or []) if str(w).strip()]:
        raise HTTPException(status_code=400, detail="Type the words to look for in the card title.")
    if t["type"] == "due_in":
        try:
            t["days"] = int(t.get("days"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="How many days before the due date?")
    acts = [a for a in (payload.get("actions") or []) if isinstance(a, dict) and a.get("type") in ACTIONS]
    if not acts:
        raise HTTPException(status_code=400, detail="Add at least one thing for the rule to do.")
    for a in acts:
        if a["type"] in ("move_board", "copy_board", "mirror_board", "move_mirror"):
            if not a.get("board_id") or not a.get("list_id"):
                raise HTTPException(status_code=400, detail="Pick the board and list for the card.")
            if db is not None:
                _board(db, user, int(a["board_id"]), "edit")      # you must be able to work on the other board
    return json.dumps(t), json.dumps(acts)


@router.post("/store/kb/boards/{bid}/rules")
def add_rule(bid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    b, _ = _board(db, user, bid, "edit")
    t, a = _clean_rule(payload, db, user)
    r = KRule(board_id=b.id, trigger=t, actions=a, created_by=user.id)
    db.add(r)
    _touch(db, b)
    db.commit()
    return {"id": r.id}


@router.patch("/store/kb/rules/{rid}")
def edit_rule(rid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    r = db.query(KRule).filter(KRule.id == rid).first()
    if not r:
        raise HTTPException(status_code=404, detail="Rule gone.")
    b, _ = _board(db, user, r.board_id, "edit")
    if "enabled" in payload:
        r.enabled = bool(payload["enabled"])
    if "trigger" in payload or "actions" in payload:
        r.trigger, r.actions = _clean_rule({"trigger": payload.get("trigger") or _j(r.trigger, {}),
                                            "actions": payload.get("actions") or _j(r.actions, [])}, db, user)
    _touch(db, b)
    db.commit()
    return {"ok": True}


@router.delete("/store/kb/rules/{rid}")
def delete_rule(rid: int, db: Session = Depends(get_db), user: models.User = VIEW):
    r = db.query(KRule).filter(KRule.id == rid).first()
    if not r:
        return {"ok": True}
    b, _ = _board(db, user, r.board_id, "edit")
    db.delete(r)
    _touch(db, b)
    db.commit()
    return {"ok": True}


# ---- notes -------------------------------------------------------------------------------------------

@router.get("/store/kb/notes")
def get_notes(db: Session = Depends(get_db), user: models.User = VIEW):
    rows = db.query(KNote).filter(KNote.user_id == user.id).order_by(KNote.id.desc()).limit(60).all()
    users = _users(db)
    boards = {b.id: b.title for b in db.query(KBoard).all()}
    out = [{"id": n.id, "kind": n.kind, "text": n.text, "read": bool(n.read), "board_id": n.board_id,
            "board": boards.get(n.board_id, ""), "card_id": n.card_id, "who": _uname(users.get(n.actor_id)) or "Someone",
            "initials": _initials(_uname(users.get(n.actor_id))), "at": _iso(n.created_at)} for n in rows]
    # Due soon: cards of mine due in the next day, not done - worked out now, never stale.
    now = datetime.utcnow() + timedelta(hours=4)
    soon = []
    for c in db.query(KCard).filter(KCard.closed == False, KCard.due != "", KCard.due_complete == False).all():  # noqa: E712
        if user.id not in _j(c.members, []):
            continue
        try:
            d = datetime.fromisoformat(c.due[:16])
        except ValueError:
            continue
        if d - now <= timedelta(days=1):
            soon.append({"card_id": c.id, "board_id": c.board_id, "board": boards.get(c.board_id, ""), "title": c.title,
                         "due": c.due, "overdue": d < now})
    return {"notes": out, "due": sorted(soon, key=lambda x: x["due"])[:30],
            "unread": sum(1 for n in out if not n["read"])}


@router.post("/store/kb/notes/read")
def read_notes(payload: dict = Body(default={}), db: Session = Depends(get_db), user: models.User = VIEW):
    q = db.query(KNote).filter(KNote.user_id == user.id, KNote.read == False)  # noqa: E712
    if payload.get("ids"):
        q = q.filter(KNote.id.in_([int(i) for i in payload["ids"]]))
    q.update({"read": True}, synchronize_session=False)
    db.commit()
    return {"ok": True}


def bell_items(db, user):
    """For the app's own bell: the unread board notes of this login."""
    try:
        rows = db.query(KNote).filter(KNote.user_id == user.id, KNote.read == False).order_by(KNote.id.desc()).limit(10).all()  # noqa: E712
    except Exception:
        return []
    users = _users(db, [n.actor_id for n in rows])
    boards = {b.id: b.title for b in db.query(KBoard).filter(KBoard.id.in_([n.board_id for n in rows] or [0])).all()}
    return [{"id": f"kb-{n.id}", "kind": "board", "title": f"{_uname(users.get(n.actor_id)) or 'Someone'} {n.text}"[:140],
             "detail": f"Trello - {boards.get(n.board_id, '')}", "screen": "pgboards",
             "target": f"b{n.board_id}" + (f"c{n.card_id}" if n.card_id else ""),
             "when": (n.created_at + timedelta(hours=4)).date().isoformat(), "level": "info"} for n in rows]


# ---- power-ups: time tracking, repeater, buttons, mirror, inbox, planner -------------------------------

@router.post("/store/kb/cards/{cid}/time")
def log_time(cid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    c, b, _ = _card(db, user, cid, "edit")
    try:
        h = float(payload.get("hours") or 0)
    except (TypeError, ValueError):
        h = 0
    if not 0 < h <= 24 * 31:
        raise HTTPException(status_code=400, detail="How many hours?")
    day = (payload.get("day") or (datetime.utcnow() + timedelta(hours=4)).date().isoformat())[:10]
    t = KTime(card_id=c.id, board_id=b.id, user_id=user.id, hours=round(h, 2), day=day, note=(payload.get("note") or "")[:300])
    db.add(t)
    _act(db, b, user, "time_logged", c, hours=t.hours, note=t.note)
    c.updated_at = _now()
    _touch(db, b)
    db.commit()
    return {"id": t.id}


@router.delete("/store/kb/time/{tid}")
def delete_time(tid: int, db: Session = Depends(get_db), user: models.User = VIEW):
    t = db.query(KTime).filter(KTime.id == tid).first()
    if not t:
        return {"ok": True}
    c, b, role = _card(db, user, t.card_id, "edit")
    if t.user_id != user.id and role != "admin":
        raise HTTPException(status_code=403, detail="You can only remove your own time.")
    db.delete(t)
    _touch(db, b)
    db.commit()
    return {"ok": True}


def _dubai_today():
    return (datetime.utcnow() + timedelta(hours=4)).date()


def _next_date(d, every, nth):
    nth = max(1, int(nth or 1))
    if every == "day":
        return d + timedelta(days=nth)
    if every == "weekday":
        n = d + timedelta(days=1)
        while n.weekday() in (5, 6):      # Mon-Fri ... in the UAE Sat and Sun are the weekend
            n += timedelta(days=1)
        return n
    if every == "week":
        return d + timedelta(weeks=nth)
    if every == "year":
        try:
            return d.replace(year=d.year + nth)
        except ValueError:
            return d.replace(year=d.year + nth, day=28)
    m = d.month - 1 + nth
    y, m = d.year + m // 12, m % 12 + 1
    import calendar
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _run_repeats(db, b):
    """Make any repeated copies that have fallen due (checked whenever the board is opened)."""
    today = _dubai_today()
    now_t = (datetime.utcnow() + timedelta(hours=4)).strftime("%H:%M")
    made = False
    for r in db.query(KRepeat).filter(KRepeat.board_id == b.id, KRepeat.enabled == True).all():  # noqa: E712
        guard = 0
        while r.next_on and (r.next_on < today.isoformat() or (r.next_on == today.isoformat() and (r.time or "00:00") <= now_t)) and guard < 12:
            guard += 1
            src = db.query(KCard).filter(KCard.id == r.card_id).first()
            lst = db.query(KList).filter(KList.id == r.list_id, KList.closed == False).first()  # noqa: E712
            if not src or not lst:
                r.enabled = False
                break
            nc = _clone_card(db, src, b, lst.id, _top_pos(db, KCard, list_id=lst.id))
            nc.due_complete = False
            nc.no = b.next_no or 1
            b.next_no = nc.no + 1
            d = date.fromisoformat(r.next_on)
            if (r.due_days or -1) >= 0:
                nc.due = f"{(d + timedelta(days=r.due_days)).isoformat()}T17:00"
            db.flush()
            _act(db, b, None, "card_repeated", nc, source=src.title)
            r.made = (r.made or 0) + 1
            r.next_on = _next_date(d, r.every, r.nth).isoformat()
            made = True
    if made:
        _touch(db, b)
        db.commit()


def _period_key(t, now):
    """The period a scheduled rule last ran in - it runs once per period, from its time on."""
    e = t.get("every")
    if (t.get("time") or "00:00") > now.strftime("%H:%M"):
        return None
    if e == "day":
        return now.date().isoformat()
    if e == "weekday":
        return None if now.weekday() in (5, 6) else now.date().isoformat()
    if e == "week":
        return f"{now.isocalendar()[0]}-W{now.isocalendar()[1]}" if now.weekday() == int(t.get("weekday") or 0) % 7 else None
    if e == "month":
        return now.strftime("%Y-%m") if now.day == int(t.get("day") or 1) else None
    return None


def run_scheduled(db, now=None):
    """Scheduled and due-date rules, every board (called every minute; safe to call often)."""
    now = now or (datetime.utcnow() + timedelta(hours=4))
    ran = 0
    for r in db.query(KRule).filter(KRule.enabled == True).all():  # noqa: E712
        t = _j(r.trigger, {})
        if t.get("type") not in ("schedule", "due_in"):
            continue
        b = db.query(KBoard).filter(KBoard.id == r.board_id).first()
        if not b or b.closed:
            continue
        user = db.query(models.User).filter(models.User.id == r.created_by).first()
        if t["type"] == "schedule":
            key = _period_key(t, now)
            if not key or r.last_run == key:
                continue
            r.last_run = key
            q = db.query(KCard).filter(KCard.board_id == b.id, KCard.closed == False)  # noqa: E712
            if t.get("list_id"):
                q = q.filter(KCard.list_id == int(t["list_id"]))
            cards = q.all()
            which = t.get("cards") or "all"
            today = now.date().isoformat()
            if which == "complete":
                cards = [c for c in cards if c.due_complete]
            elif which == "incomplete":
                cards = [c for c in cards if not c.due_complete]
            elif which == "overdue":
                cards = [c for c in cards if c.due and c.due[:10] < today and not c.due_complete]
            elif which == "none":
                cards = []
            board_acts = [a for a in _j(r.actions, []) if a.get("type") == "sort_list"]
            for a in board_acts:
                _do_action(db, b, None, user, a, 0, rule=r)
            if any(a.get("type") != "sort_list" for a in _j(r.actions, [])):
                for c in cards:
                    _fire(db, r, b, c, user)
            elif board_acts:
                _fire(db, r, b, None, user)
            ran += 1
        else:
            st = _j(r.state, {})
            days = int(t.get("days") or 0)
            target = (now.date() + timedelta(days=days)).isoformat()
            for c in db.query(KCard).filter(KCard.board_id == b.id, KCard.closed == False, KCard.due_complete == False).all():  # noqa: E712
                if not c.due or c.due[:10] != target:
                    continue
                mark = f"due:{c.id}:{c.due}"
                if st.get(mark):
                    continue
                st[mark] = 1
                r.state = json.dumps(st)
                _fire(db, r, b, c, user)
                ran += 1
        _touch(db, b)
    if ran:
        db.commit()
    else:
        db.rollback()
    return ran


def _sched_loop():
    from database import SessionLocal
    time.sleep(20)
    while True:
        try:
            db = SessionLocal()
            try:
                run_scheduled(db)
            finally:
                db.close()
        except Exception as e:
            print("boards scheduler:", e)
        time.sleep(60)


def start_scheduler():
    import threading
    threading.Thread(target=_sched_loop, daemon=True, name="boards-rules").start()


@router.post("/store/kb/rules/{rid}/run")
def run_rule_now(rid: int, db: Session = Depends(get_db), user: models.User = VIEW):
    """Run a scheduled rule now (the Run now button)."""
    r = db.query(KRule).filter(KRule.id == rid).first()
    if not r:
        raise HTTPException(status_code=404, detail="Rule gone.")
    b, _ = _board(db, user, r.board_id, "edit")
    t = _j(r.trigger, {})
    if t.get("type") != "schedule":
        return _apply_rule_existing(db, r, b, t, user)
    q = db.query(KCard).filter(KCard.board_id == b.id, KCard.closed == False)  # noqa: E712
    if t.get("list_id"):
        q = q.filter(KCard.list_id == int(t["list_id"]))
    cards = q.all()
    today = _dubai_today().isoformat()
    which = t.get("cards") or "all"
    if which == "complete":
        cards = [c for c in cards if c.due_complete]
    elif which == "incomplete":
        cards = [c for c in cards if not c.due_complete]
    elif which == "overdue":
        cards = [c for c in cards if c.due and c.due[:10] < today and not c.due_complete]
    elif which == "none":
        cards = []
    for a in [a for a in _j(r.actions, []) if a.get("type") == "sort_list"]:
        _do_action(db, b, None, user, a, 0, rule=r)
    n = 0
    if any(a.get("type") != "sort_list" for a in _j(r.actions, [])):
        for c in cards:
            _fire(db, r, b, c, user)
            n += 1
    _touch(db, b)
    db.commit()
    return {"cards": n}


def _apply_rule_existing(db, r, b, t, user):
    """An event rule run by hand: every open card that already fits the rule
    (title words, the list it is in, complete, labels, members, due date)."""
    lists = {l.id: l for l in db.query(KList).filter(KList.board_id == b.id, KList.closed == False).all()}  # noqa: E712
    n = 0
    for c in db.query(KCard).filter(KCard.board_id == b.id, KCard.closed == False).order_by(KCard.pos).all():  # noqa: E712
        if c.list_id not in lists or c.is_template:
            continue
        ty = t.get("type")
        if t.get("list_id") and int(t["list_id"]) != c.list_id:
            continue
        ok = True
        if ty == "card_titled":
            ok = _title_matches(t, c.title, lists[c.list_id].title)
        elif ty == "card_complete":
            ok = bool(c.due_complete)
        elif ty == "label_added":
            ok = (not t.get("label_id")) or int(t["label_id"]) in _j(c.labels, [])
        elif ty == "member_added":
            ok = (not t.get("user_id")) or int(t["user_id"]) in _j(c.members, [])
        elif ty == "due_set":
            ok = bool(c.due)
        elif ty in ("comment_added", "item_done", "checklist_done", "card_archived"):
            ok = False
        if ok:
            _fire(db, r, b, c, user)
            n += 1
    _touch(db, b)
    db.commit()
    return {"cards": n}


@router.put("/store/kb/cards/{cid}/repeat")
def set_repeat(cid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    c, b, _ = _card(db, user, cid, "edit")
    r = db.query(KRepeat).filter(KRepeat.card_id == c.id).first()
    if payload.get("off"):
        if r:
            db.delete(r)
        _touch(db, b)
        db.commit()
        return {"ok": True}
    every = payload.get("every") if payload.get("every") in ("day", "weekday", "week", "month", "year") else "week"
    start = (payload.get("start") or "")[:10]
    try:
        first = date.fromisoformat(start) if start else _next_date(_dubai_today(), every, 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Pick the first date.")
    lid = int(payload.get("list_id") or c.list_id)
    if not db.query(KList).filter(KList.id == lid, KList.board_id == b.id).first():
        raise HTTPException(status_code=400, detail="Pick a list on this board.")
    if not r:
        r = KRepeat(card_id=c.id, board_id=b.id, created_by=user.id)
        db.add(r)
    r.every, r.nth, r.list_id = every, max(1, int(payload.get("nth") or 1)), lid
    r.time = (payload.get("time") or "09:00")[:5]
    r.next_on = first.isoformat()
    r.due_days = int(payload.get("due_days") if payload.get("due_days") not in (None, "") else -1)
    r.enabled = True
    _act(db, b, user, "repeat_set", c, every=every)
    _touch(db, b)
    db.commit()
    return {"ok": True, "next_on": r.next_on}


@router.post("/store/kb/cards/{cid}/button")
def press_card_button(cid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    """Card buttons (Butler): one click runs the button's actions on this card."""
    c, b, _ = _card(db, user, cid, "edit")
    btns = _j(b.prefs, {}).get("card_buttons") or []
    i = int(payload.get("index", -1))
    if not 0 <= i < len(btns):
        raise HTTPException(status_code=404, detail="That button is gone.")
    for a in btns[i].get("actions") or []:
        _do_action(db, b, c, user, a, 0)
    _act(db, b, user, "button", c, name=btns[i].get("name", ""))
    _touch(db, b)
    db.commit()
    return {"ok": True}


@router.post("/store/kb/boards/{bid}/button")
def press_board_button(bid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    """Board buttons: run the actions on every card of a list (or of the board)."""
    b, _ = _board(db, user, bid, "edit")
    btns = _j(b.prefs, {}).get("board_buttons") or []
    i = int(payload.get("index", -1))
    if not 0 <= i < len(btns):
        raise HTTPException(status_code=404, detail="That button is gone.")
    btn = btns[i]
    q = db.query(KCard).filter(KCard.board_id == b.id, KCard.closed == False)  # noqa: E712
    if btn.get("list_id"):
        q = q.filter(KCard.list_id == int(btn["list_id"]))
    if btn.get("only_complete"):
        q = q.filter(KCard.due_complete == True)  # noqa: E712
    n = 0
    for c in q.all():
        for a in btn.get("actions") or []:
            _do_action(db, b, c, user, a, 0)
        n += 1
    _act(db, b, user, "board_button", name=btn.get("name", ""), n=n)
    _touch(db, b)
    db.commit()
    return {"cards": n}


@router.post("/store/kb/cards/{cid}/mirror")
def mirror_card(cid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    """Show this card on another board as well (Trello's Mirror card). Changes are made once, on the source."""
    c, b, _ = _card(db, user, cid)
    tb, _r = _board(db, user, int(payload.get("board_id") or 0), "edit")
    lid = int(payload.get("list_id") or 0)
    if not db.query(KList).filter(KList.id == lid, KList.board_id == tb.id).first():
        raise HTTPException(status_code=400, detail="Pick a list on that board.")
    src = c.mirror_of and db.query(KCard).filter(KCard.id == c.mirror_of).first() or c
    m = KCard(board_id=tb.id, list_id=lid, title=src.title, pos=_pos_from(payload, db, KCard, list_id=lid, closed=False),
              mirror_of=src.id, created_by=user.id)
    m.no = tb.next_no or 1
    tb.next_no = m.no + 1
    db.add(m)
    db.flush()
    _act(db, tb, user, "card_mirrored", m, source=src.title, frm=b.title)
    _touch(db, tb)
    db.commit()
    return {"id": m.id}


@router.post("/store/kb/boards/{bid}/link-mirrors")
def link_mirrors(bid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    """Cards on this board that are copies of cards on the main board (same title) become mirrors of them,
    so from now on they show the main card - updated wherever it is changed. Each stays in its own list."""
    b, _ = _board(db, user, bid, "edit")
    src, _r = _board(db, user, int(payload.get("source_board_id") or 0))
    norm = lambda x: re.sub(r"\s+", " ", (x or "").strip().lower())
    by_title = {}
    for c in db.query(KCard).filter(KCard.board_id == src.id, KCard.mirror_of == None).order_by(KCard.closed, KCard.id).all():  # noqa: E711
        by_title.setdefault(norm(c.title), c)
    linked, missing = [], []
    for c in db.query(KCard).filter(KCard.board_id == b.id, KCard.closed == False, KCard.mirror_of == None).all():  # noqa: E711,E712
        s = by_title.get(norm(c.title))
        if not s:
            missing.append(c.title)
            continue
        if payload.get("dry_run"):
            linked.append(c.title)
            continue
        c.mirror_of = s.id
        linked.append(c.title)
        _act(db, b, user, "card_mirrored", c, source=s.title, frm=src.title)
    if not payload.get("dry_run"):
        _touch(db, b)
        db.commit()
    return {"linked": linked, "not_found": missing}


@router.get("/store/kb/inbox")
def inbox(db: Session = Depends(get_db), user: models.User = VIEW):
    """Inbox: a private place to jot cards down before they go on a board."""
    mine = [b for b in db.query(KBoard).all() if _j(b.prefs, {}).get("inbox_of") == user.id]
    if mine:
        b = mine[0]
    else:
        b = KBoard(title="Inbox", bg="sky", visibility="private", prefs=json.dumps({"inbox_of": user.id}), created_by=user.id)
        db.add(b)
        db.flush()
        db.add(KMember(board_id=b.id, user_id=user.id, role="admin"))
        db.add(KList(board_id=b.id, title="Inbox", pos=65536))
        db.commit()
    return _board_out(db, b, user, "admin")


@router.get("/store/kb/planner")
def planner(start: str = "", end: str = "", db: Session = Depends(get_db), user: models.User = VIEW):
    """Planner: every card I am on with a start or due date, across all boards."""
    boards = {b.id: b for b in _visible_boards(db, user, inbox=True)}
    out = []
    for c in db.query(KCard).filter(KCard.board_id.in_(list(boards) or [0]), KCard.closed == False).all():  # noqa: E712
        if not (c.due or c.start):
            continue
        if user.id not in _j(c.members, []) and boards[c.board_id].created_by != user.id and not _is_inbox(boards[c.board_id]):
            continue
        d = (c.due or c.start)[:10]
        if start and d < start or end and d > end:
            continue
        out.append({"id": c.id, "no": c.no, "title": c.title, "board_id": c.board_id, "board": boards[c.board_id].title,
                    "bg": boards[c.board_id].bg, "start": c.start, "due": c.due, "due_complete": bool(c.due_complete),
                    "labels": _j(c.labels, [])})
    return {"cards": sorted(out, key=lambda x: x["due"] or x["start"])}


# ---- Trello import -------------------------------------------------------------------------------------

TRELLO_BG = {"blue": "blue", "orange": "orange", "green": "green", "red": "red", "purple": "purple", "pink": "pink",
             "lime": "lime", "sky": "sky", "grey": "grey"}


def import_trello(db, data, user, title=None):
    """A Trello board export (board menu > Print, export and share > Export as JSON) becomes a board here:
    labels, lists, cards (with numbers, dates, covers), checklists, comments and links, in the same order."""
    if not isinstance(data, dict) or "lists" not in data or "cards" not in data:
        raise HTTPException(status_code=400, detail="That is not a Trello board export (JSON).")
    prefs = data.get("prefs") or {}
    bg = TRELLO_BG.get(prefs.get("background"), "") or (prefs.get("backgroundColor") and "c:" + prefs["backgroundColor"]) or "blue"
    if prefs.get("backgroundImage"):
        bg = "img:" + prefs["backgroundImage"]
    b = KBoard(title=(title or data.get("name") or "Imported board")[:200], desc=(data.get("desc") or "")[:20000], bg=bg,
               visibility="team", created_by=user.id)
    db.add(b)
    db.flush()
    db.add(KMember(board_id=b.id, user_id=user.id, role="admin"))
    users = list(db.query(models.User).all())

    def match(member):
        n = (member.get("fullName") or "").strip().lower()
        un = (member.get("username") or "").strip().lower()
        for u in users:
            if (u.username or "").lower() == un or (_uname(u).lower() == n and n):
                return u
        first = n.split(" ")[0] if n else ""
        cand = [u for u in users if first and _uname(u).lower().split(" ")[0] == first]
        return cand[0] if len(cand) == 1 else None

    mmap = {}
    for m in data.get("members") or []:
        u = match(m)
        if u:
            mmap[m["id"]] = u.id
            if u.id != user.id and not db.query(KMember).filter(KMember.board_id == b.id, KMember.user_id == u.id).first():
                db.add(KMember(board_id=b.id, user_id=u.id, role="member"))
    lmap = {}
    for i, l in enumerate(data.get("labels") or []):
        n = KLabel(board_id=b.id, name=(l.get("name") or "")[:100],
                   color=l.get("color") if l.get("color") in LABEL_COLORS else "", pos=i + 1)
        db.add(n)
        db.flush()
        lmap[l["id"]] = n.id
    fmap, omap = {}, {}
    for i, f in enumerate(data.get("customFields") or []):
        t = {"text": "text", "number": "number", "date": "date", "checkbox": "checkbox", "list": "list"}.get(f.get("type"), "text")
        opts = []
        for o in f.get("options") or []:
            oid = uuid.uuid4().hex[:8]
            omap[o["id"]] = oid
            opts.append({"id": oid, "text": ((o.get("value") or {}).get("text") or "")[:100], "color": o.get("color") or ""})
        n = KField(board_id=b.id, name=(f.get("name") or "")[:100], type=t, options=json.dumps(opts), pos=i + 1,
                   on_front=bool((f.get("display") or {}).get("cardFront", True)))
        db.add(n)
        db.flush()
        fmap[f["id"]] = n.id
    listmap = {}
    for l in sorted(data.get("lists") or [], key=lambda x: x.get("pos") or 0):
        n = KList(board_id=b.id, title=(l.get("name") or "")[:200], pos=float(l.get("pos") or 0), closed=bool(l.get("closed")),
                  color=(l.get("color") or "") if isinstance(l.get("color"), str) else "")
        db.add(n)
        db.flush()
        listmap[l["id"]] = n.id
    cardmap = {}
    cards = sorted(data.get("cards") or [], key=lambda x: (x.get("idShort") or 0))
    maxno = 0
    for c in cards:
        if c.get("idList") not in listmap:
            continue
        cov = {}
        co = c.get("cover") or {}
        if co.get("color"):
            cov = {"color": co["color"], "size": "full" if co.get("size") == "full" else "normal",
                   "text": "dark" if co.get("brightness") == "light" else "light"}
        due = (c.get("due") or "")
        if due:
            try:
                d = datetime.fromisoformat(due.replace("Z", "+00:00")) + timedelta(hours=4)
                due = d.strftime("%Y-%m-%dT%H:%M")
            except ValueError:
                due = due[:16]
        start = (c.get("start") or "")[:10]
        fv = {}
        for item in c.get("customFieldItems") or []:
            fid = fmap.get(item.get("idCustomField"))
            if not fid:
                continue
            v = item.get("value") or {}
            if item.get("idValue"):
                fv[str(fid)] = omap.get(item["idValue"], "")
            elif "text" in v:
                fv[str(fid)] = v["text"]
            elif "number" in v:
                fv[str(fid)] = v["number"]
            elif "date" in v:
                fv[str(fid)] = (v["date"] or "")[:10]
            elif "checked" in v:
                fv[str(fid)] = v["checked"] in (True, "true")
        no = int(c.get("idShort") or 0)
        maxno = max(maxno, no)
        n = KCard(board_id=b.id, list_id=listmap[c["idList"]], no=no, title=(c.get("name") or "")[:2000],
                  desc=(c.get("desc") or "")[:50000], pos=float(c.get("pos") or 0), closed=bool(c.get("closed")),
                  start=start, due=due, due_complete=bool(c.get("dueComplete")),
                  labels=json.dumps([lmap[x] for x in c.get("idLabels") or [] if x in lmap]),
                  members=json.dumps([mmap[x] for x in c.get("idMembers") or [] if x in mmap]),
                  cover=json.dumps(cov), fields=json.dumps(fv), is_template=bool(c.get("isTemplate")),
                  created_by=user.id)
        try:
            n.created_at = datetime.utcfromtimestamp(int(c["id"][:8], 16))
            n.updated_at = datetime.fromisoformat((c.get("dateLastActivity") or "").replace("Z", "")[:19]) if c.get("dateLastActivity") else n.created_at
        except (ValueError, KeyError, TypeError):
            pass
        db.add(n)
        db.flush()
        cardmap[c["id"]] = n.id
        for a in c.get("attachments") or []:
            if a.get("url"):
                db.add(KAttachment(card_id=n.id, board_id=b.id, name=(a.get("name") or a["url"])[:200], url=a["url"][:2000],
                                   mime=a.get("mimeType") or "", size=a.get("bytes") or 0, user_id=user.id))
    b.next_no = maxno + 1
    for cl in data.get("checklists") or []:
        cid = cardmap.get(cl.get("idCard"))
        if not cid:
            continue
        n = KChecklist(card_id=cid, title=(cl.get("name") or "Checklist")[:200], pos=float(cl.get("pos") or 0))
        db.add(n)
        db.flush()
        for it in cl.get("checkItems") or []:
            due = (it.get("due") or "")[:10]
            db.add(KItem(checklist_id=n.id, text=(it.get("name") or "")[:1000], done=it.get("state") == "complete",
                         pos=float(it.get("pos") or 0), due=due, member=mmap.get(it.get("idMember"))))
    names = {m["id"]: m.get("fullName") or m.get("username") or "" for m in data.get("members") or []}
    ncom = 0
    for a in data.get("actions") or []:
        if a.get("type") != "commentCard":
            continue
        cid = cardmap.get(((a.get("data") or {}).get("card") or {}).get("id"))
        if not cid:
            continue
        mc = a.get("memberCreator") or {}
        try:
            when = datetime.fromisoformat((a.get("date") or "").replace("Z", "")[:19])
        except ValueError:
            when = _now()
        db.add(KComment(card_id=cid, board_id=b.id, user_id=mmap.get(a.get("idMemberCreator")),
                        author=(mc.get("fullName") or names.get(a.get("idMemberCreator")) or "")[:100],
                        text=((a.get("data") or {}).get("text") or "")[:20000], created_at=when))
        ncom += 1
    _act(db, b, user, "board_imported", title=b.title, cards=len(cardmap), comments=ncom)
    return b, {"lists": len(listmap), "cards": len(cardmap), "labels": len(lmap), "comments": ncom,
               "checklists": len(data.get("checklists") or []), "members_matched": len(set(mmap.values()))}


@router.post("/store/kb/import")
async def import_board(file: UploadFile = File(...), title: str = Form(""), db: Session = Depends(get_db),
                       user: models.User = VIEW):
    raw = await file.read()
    if raw[:2] == b"\x1f\x8b":            # sent compressed (a big Trello board is 10 MB as text)
        import gzip
        try:
            raw = gzip.decompress(raw)
        except OSError:
            raise HTTPException(status_code=400, detail="That file could not be opened.")
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="That file is not a Trello JSON export.")
    b, stats = import_trello(db, data, user, title or None)
    db.commit()
    return {"id": b.id, **stats}


# ---- Preview / PDF / Excel of a board -------------------------------------------------------------------

def _fmt_due(s):
    if not s:
        return ""
    try:
        d = datetime.fromisoformat(s[:16])
        return d.strftime("%d-%b-%y") + ("" if s[11:16] in ("", "00:00") else d.strftime(" %H:%M"))
    except ValueError:
        return s


def _export_rows(db, b, list_id=0, label_id=0, member_id=0, q="", due=""):
    lists = {l.id: l for l in db.query(KList).filter(KList.board_id == b.id, KList.closed == False).all()}  # noqa: E712
    labels = {l.id: (l.name or l.color) for l in db.query(KLabel).filter(KLabel.board_id == b.id).all()}
    users = _users(db)
    cards = [c for c in db.query(KCard).filter(KCard.board_id == b.id, KCard.closed == False).all() if c.list_id in lists]  # noqa: E712
    counts = _counts(db, [c.id for c in cards])
    today = (datetime.utcnow() + timedelta(hours=4)).date().isoformat()
    rows = []
    for c in sorted(cards, key=lambda c: (lists[c.list_id].pos, c.pos)):
        ls, ms = _j(c.labels, []), _j(c.members, [])
        if list_id and c.list_id != list_id or label_id and label_id not in ls or member_id and member_id not in ms:
            continue
        if q and q.lower() not in (c.title or "").lower():
            continue
        if due == "overdue" and not (c.due and c.due[:10] < today and not c.due_complete):
            continue
        if due == "complete" and not c.due_complete:
            continue
        cnt = counts.get(c.id, {})
        rows.append({"List": lists[c.list_id].title, "#": c.no, "Card": c.title,
                     "Labels": ", ".join(labels.get(x, "") for x in ls if labels.get(x)),
                     "Members": ", ".join(_uname(users.get(x)) for x in ms if users.get(x)),
                     "Start": _fmt_due(c.start), "Due": _fmt_due(c.due),
                     "Status": "Complete" if c.due_complete else ("Overdue" if c.due and c.due[:10] < today else ""),
                     "Checklist": f"{cnt.get('done', 0)}/{cnt['items']}" if cnt.get("items") else "",
                     "Comments": cnt.get("comments", 0) or ""})
    return rows


@router.get("/export/kb/{bid}")
def export_board(bid: int, token: str, format: str = "excel", list_id: int = 0, label_id: int = 0, member_id: int = 0,
                 q: str = "", due: str = "", db: Session = Depends(get_db)):
    import export_web
    u = auth.get_download_user_from_token(token, db)
    if RIGHT not in M.effective_permissions(u):
        raise HTTPException(status_code=403, detail="Estimation > Trello only.")
    b, _ = _board(db, u, bid)
    rows = _export_rows(db, b, list_id, label_id, member_id, q, due)
    if not rows:
        rows = [{"List": "", "#": "", "Card": "No cards match", "Labels": "", "Members": "", "Start": "", "Due": "",
                 "Status": "", "Checklist": "", "Comments": ""}]
    title = f"{b.title} - Board"
    sub = f"{len(rows)} cards | As at {(datetime.utcnow() + timedelta(hours=4)):%d %b %Y}"
    if format == "preview":
        url = f"/export/kb/{bid}?token={token}&list_id={list_id}&label_id={label_id}&member_id={member_id}&q={q}&due={due}"
        return M._preview_page(title, sub, rows, url + "&format=pdf", url + "&format=excel", money_cols=[])
    safe = re.sub(r"[^\w]+", "_", b.title)[:40] or "board"
    if format == "pdf":
        return StreamingResponse(export_web.build_store_report_pdf(title, rows, sub, money_cols=[], orientation="landscape"),
                                 media_type="application/pdf", headers={"Content-Disposition": f"inline; filename={safe}.pdf"})
    return StreamingResponse(export_web.build_store_report_excel(title, rows, sub, money_cols=[]),
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename={safe}.xlsx"})


@router.get("/store/kb/boards/{bid}/json")
def board_json(bid: int, db: Session = Depends(get_db), user: models.User = VIEW):
    """The whole board as JSON (export), with every card in full."""
    b, role = _board(db, user, bid)
    out = _board_out(db, b, user, role)
    out["cards"] = [_card_full(db, db.query(KCard).get(c["id"]), b, user, role) for c in out["cards"]]
    return out

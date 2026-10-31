"""Labour accommodation - the camp's rooms and beds (Reports > Labour >
Accommodation).

Six beds a room. A bed is free, has a worker, a guest (someone not on the
staff list, typed by name), or is booked for a new joiner. Two things are
never typed here, so they cannot drift from the rest of the app:

* On vacation - read from leave records. The bed stays his while he is
  away and shows "On vacation - back <date>".
* Left - a worker terminated or made inactive on the staff list loses his
  bed by itself on the next look, and the move is kept in the history.

Anyone with Labour reports sees it; changing it needs the "camp" right
(the PRO, the chief accountant and the store keeper; admin always).
"""
from datetime import date, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

import auth
import export_web
import main as M
import models
from database import get_db

router = APIRouter()
RIGHT = "camp"
VIEW = Depends(M.require_any_screen("reports", RIGHT))

# The camp as on 9 Oct 2026 (Jomon's allocation sheet). Loaded once into
# an empty camp; after that the app is the record. None = free bed; an ID
# is matched to the staff list, a name alone is kept as a guest.
SEED = {
    "49": [None, "F757", "F715", None, None, None],
    "50": ["F707", "F716", "F775", "F781", "F794", "F796"],
    "51": ["F762", "F735", "F777", "F782", "F736", "F742"],
    "52": ["F724", "F723", "F726", "F743", "F753", "F752"],
    "53": ["F766", None, "F717", "F779", "F764", "F788"],
    "54": ["F004", "F728", "F791", "F758", "F776", "F799"],
    "55": ["@Sayed", "D01", None, "@Shaiju", "F801", "@Amal"],
    "56": [None, "F800", "F745", "F732", "F784", "F785"],
    "57": ["F002", "F751", "F755", None, "F760", "F773"],
    "58": ["F740", "F770", None, "F771", "F798", None],
    "59": ["F787", "F789", "F786", None, None, None],
    "60": ["F722", "F778", "F729", "F727", "F797", "F795"],
    "61": ["F793", "F754", "F759", "F756", None, "F790"],
    "62": ["F741", "F763", "F734", "F749", "F746", "F730"],
    "63": ["D02", "D03", "F712", "F780", None, None],
}


def _key(no):
    return "".join(ch for ch in str(no or "").upper() if ch.isalnum())


def working(e, today=None):
    """Still with the company today (a leaving date ahead still counts)."""
    today = today or M._dubai_today()
    return bool(e and e.active and not (e.terminated_on and e.terminated_on <= today))


def may_edit(user):
    return (user.role or "") == "admin" or RIGHT in M.effective_permissions(user)


def _editor(user: models.User = Depends(auth.get_current_user)):
    if not may_edit(user):
        raise HTTPException(status_code=403, detail="Only the PRO, the chief accountant and the store keeper change the camp list.")
    return user


EDIT = Depends(_editor)


def seed(db):
    """Load the 9 Oct sheet into an empty camp - once."""
    if db.query(models.CampRoom).count() or M.get_setting(db, "camp_seeded"):
        return 0
    emps = {_key(e.emp_no): e for e in db.query(models.Employee).all()}
    n = 0
    for i, (room, beds) in enumerate(SEED.items()):
        r = models.CampRoom(name=room, beds=6, sort=i)
        db.add(r); db.flush()
        for b, who in enumerate(beds, start=1):
            bed = models.CampBed(room_id=r.id, bed_no=b)
            if who and who.startswith("@"):
                bed.guest_name = who[1:]
            elif who:
                e = emps.get(_key(who))
                if working(e):
                    bed.employee_id = e.id
                else:
                    bed.guest_name = who        # kept, shown to be checked
            db.add(bed); n += 1
    M.put_setting(db, "camp_seeded", "1")
    db.commit()
    return n


def _beds(db, room):
    """The room's beds 1..room.beds, created as needed."""
    have = {b.bed_no: b for b in db.query(models.CampBed).filter(models.CampBed.room_id == room.id).all()}
    out = []
    for n in range(1, (room.beds or 0) + 1):
        if n not in have:
            have[n] = models.CampBed(room_id=room.id, bed_no=n)
            db.add(have[n])
        out.append(have[n])
    return out


def _log(db, user, kind, room="", bed=None, emp=None, name="", frm=("", None), reason=""):
    db.add(models.CampMove(employee_id=emp.id if emp else None, name=(emp.name if emp else name)[:120], kind=kind,
                           room=room, bed_no=bed, from_room=frm[0] or "", from_bed=frm[1], reason=reason[:200],
                           on_date=M._dubai_today(), by=user.id if user else None))


def release_leavers(db):
    """A worker who has left the company (terminated / inactive) gives
    his bed back by itself - on the termination date."""
    today = M._dubai_today()
    n = 0
    rooms = {r.id: r.name for r in db.query(models.CampRoom).all()}
    for b in db.query(models.CampBed).filter(models.CampBed.employee_id.isnot(None)).all():
        e = db.get(models.Employee, b.employee_id)
        gone = (not e) or (e.terminated_on and e.terminated_on <= today) or (not e.active and not e.terminated_on)
        if gone:
            _log(db, None, "out", rooms.get(b.room_id, ""), b.bed_no, emp=e,
                 reason=f"Left the company{(' ' + e.terminated_on.strftime('%d/%m/%Y')) if e and e.terminated_on else ''} - bed freed automatically")
            b.employee_id = None
            n += 1
    if n:
        db.commit()
    return n


def _leave_map(db):
    """Who is away now (bed kept) and who goes soon (next 30 days)."""
    today = M._dubai_today()
    away, soon = {}, {}
    for lr in db.query(models.LeaveRecord).filter(models.LeaveRecord.status.in_(["approved", "pending"]),
                                                   models.LeaveRecord.leave_on.isnot(None)).all():
        # still away until he is marked back - one past his return date is overdue on the leave register, not in his bed
        if lr.leave_on <= today and lr.status == "approved":
            away[lr.employee_id] = lr
        elif today < lr.leave_on <= today + timedelta(days=30):
            if lr.employee_id not in soon or lr.leave_on < soon[lr.employee_id].leave_on:
                soon[lr.employee_id] = lr
    return away, soon


def listing(db):
    release_leavers(db)
    today = M._dubai_today()
    away, soon = _leave_map(db)
    emps = {e.id: e for e in db.query(models.Employee).all()}
    rooms = db.query(models.CampRoom).order_by(models.CampRoom.sort, models.CampRoom.name).all()
    housed = set()
    tot = {"beds": 0, "in": 0, "vac": 0, "book": 0, "free": 0, "check": 0}
    out = []
    for r in rooms:
        beds = []
        for b in _beds(db, r):
            tot["beds"] += 1
            d = {"bed": b.bed_no, "kind": "free", "note": b.note or ""}
            e = emps.get(b.employee_id) if b.employee_id else None
            if e:
                housed.add(e.id)
                d.update(emp_id=e.id, no=e.emp_no, name=e.name, trade=e.trade or "", kind="in")
                if e.id in away:
                    lr = away[e.id]
                    d.update(kind="vac", back=lr.return_on.isoformat() if lr.return_on else "")
                    tot["vac"] += 1
                else:
                    tot["in"] += 1
                    if e.id in soon:
                        d["soon"] = soon[e.id].leave_on.isoformat()
            elif (b.guest_name or "").strip():
                d.update(kind="guest", name=b.guest_name)
                tot["in"] += 1; tot["check"] += 1
            elif (b.booked_name or "").strip():
                d.update(kind="book", name=b.booked_name, trade=b.booked_trade or "",
                         due=b.booked_on.isoformat() if b.booked_on else "",
                         late=bool(b.booked_on and b.booked_on < today))
                tot["book"] += 1
            else:
                tot["free"] += 1
            beds.append(d)
        out.append({"id": r.id, "name": r.name, "beds": beds, "free": sum(1 for x in beds if x["kind"] == "free")})
    db.commit()
    # Active labour with no bed - perhaps outside the camp, perhaps missed.
    nobed = [{"id": e.id, "no": e.emp_no, "name": e.name, "trade": e.trade or ""}
             for e in sorted(emps.values(), key=lambda x: _key(x.emp_no))
             if not e.staff and working(e, today) and e.id not in housed]
    return {"rooms": out, "totals": tot, "nobed": nobed, "today": today.isoformat()}


@router.get("/store/camp")
def get_camp(db: Session = Depends(get_db), user: models.User = VIEW):
    seed(db)
    d = listing(db)
    d["may_edit"] = may_edit(user)
    return d


@router.get("/store/camp/people")
def people(db: Session = Depends(get_db), user: models.User = EDIT):
    """Everyone who can be given a bed: active staff list, labour first,
    with the bed he has now (a move, not a second bed)."""
    rooms = {r.id: r.name for r in db.query(models.CampRoom).all()}
    where = {b.employee_id: f"{rooms.get(b.room_id, '')}/{b.bed_no}"
             for b in db.query(models.CampBed).filter(models.CampBed.employee_id.isnot(None)).all()}
    es = [e for e in db.query(models.Employee).all() if working(e)]
    es.sort(key=lambda e: (bool(e.staff), _key(e.emp_no)))
    return {"people": [{"id": e.id, "no": e.emp_no, "name": e.name, "trade": e.trade or "", "staff": bool(e.staff),
                        "bed": where.get(e.id, "")} for e in es]}


def _bed(db, room_id, bed_no):
    r = db.get(models.CampRoom, int(room_id or 0))
    if not r:
        raise HTTPException(status_code=404, detail="That room is not on the list.")
    n = int(bed_no or 0)
    if not 1 <= n <= (r.beds or 0):
        raise HTTPException(status_code=400, detail=f"Room {r.name} has beds 1 to {r.beds}.")
    b = next((x for x in _beds(db, r) if x.bed_no == n), None)
    return r, b


def _taken(b):
    return bool(b.employee_id or (b.guest_name or "").strip())


@router.post("/store/camp/assign")
def assign(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = EDIT):
    """Put a worker in a bed. If he has a bed already it is a move: his
    old bed is freed. A booked bed takes the man who arrived."""
    r, b = _bed(db, payload.get("room_id"), payload.get("bed"))
    e = db.get(models.Employee, int(payload.get("employee_id") or 0))
    if not working(e):
        raise HTTPException(status_code=400, detail="Pick someone on the staff list who is still working.")
    if _taken(b) and b.employee_id != e.id:
        raise HTTPException(status_code=400, detail=f"Room {r.name} bed {b.bed_no} is not free - free it or move that person first.")
    old = db.query(models.CampBed).filter(models.CampBed.employee_id == e.id).first()
    frm = ("", None)
    if old and old.id != b.id:
        orr = db.get(models.CampRoom, old.room_id)
        frm = (orr.name if orr else "", old.bed_no)
        old.employee_id = None
        db.flush()
    was_booked = (b.booked_name or "").strip()
    b.employee_id, b.guest_name, b.booked_name, b.booked_trade, b.booked_on = e.id, "", "", "", None
    b.updated_by = user.id
    _log(db, user, "move" if frm[0] else "in", r.name, b.bed_no, emp=e, frm=frm,
         reason=f"arrived - booking for {was_booked}" if was_booked else "")
    db.commit()
    M.log_action(db, user.id, "camp", f"{e.emp_no} {e.name} -> room {r.name} bed {b.bed_no}" + (f" (from {frm[0]}/{frm[1]})" if frm[0] else ""))
    return {"ok": True}


@router.post("/store/camp/guest")
def guest(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = EDIT):
    """Someone not on the staff list (a driver, a visitor) - by name."""
    r, b = _bed(db, payload.get("room_id"), payload.get("bed"))
    name = M.tidy_text(payload.get("name"))[:80]
    if not name:
        raise HTTPException(status_code=400, detail="Type the name.")
    if _taken(b):
        raise HTTPException(status_code=400, detail=f"Room {r.name} bed {b.bed_no} is not free.")
    b.guest_name, b.booked_name, b.booked_trade, b.booked_on, b.updated_by = name, "", "", None, user.id
    _log(db, user, "in", r.name, b.bed_no, name=name, reason="not on the staff list")
    db.commit()
    return {"ok": True}


@router.post("/store/camp/book")
def book(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = EDIT):
    """Keep a free bed for a new joiner who has not arrived."""
    r, b = _bed(db, payload.get("room_id"), payload.get("bed"))
    name = M.tidy_text(payload.get("name"))[:80]
    if not name:
        raise HTTPException(status_code=400, detail="Who is coming? Type the name.")
    if _taken(b):
        raise HTTPException(status_code=400, detail=f"Room {r.name} bed {b.bed_no} is not free.")
    when = M._as_date(payload.get("date")) if payload.get("date") else None
    b.booked_name, b.booked_trade, b.booked_on = name, M.tidy_text(payload.get("trade"))[:60], when
    b.updated_by = user.id
    _log(db, user, "book", r.name, b.bed_no, name=name, reason=f"arriving {when:%d/%m/%Y}" if when else "arriving")
    db.commit()
    return {"ok": True}


@router.post("/store/camp/free")
def free(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = EDIT):
    """Empty a bed: he moved out of the camp, or a booking is cancelled."""
    r, b = _bed(db, payload.get("room_id"), payload.get("bed"))
    why = M.tidy_text(payload.get("reason"))[:120]
    e = db.get(models.Employee, b.employee_id) if b.employee_id else None
    who = e.name if e else (b.guest_name or b.booked_name or "")
    if not who:
        return {"ok": True}
    kind = "unbook" if (b.booked_name and not _taken(b)) else "out"
    _log(db, user, kind, r.name, b.bed_no, emp=e, name=who, reason=why or ("booking cancelled" if kind == "unbook" else "moved out of the camp"))
    b.employee_id, b.guest_name, b.booked_name, b.booked_trade, b.booked_on, b.updated_by = None, "", "", "", None, user.id
    db.commit()
    M.log_action(db, user.id, "camp", f"room {r.name} bed {b.bed_no} freed ({who})")
    return {"ok": True}


@router.post("/store/camp/room")
def save_room(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = EDIT):
    """Add a room, or change how many beds one has (never below the beds
    in use)."""
    name = M.tidy_text(payload.get("name"))[:20]
    beds = int(payload.get("beds") or 6)
    if not name:
        raise HTTPException(status_code=400, detail="Give the room a number or name.")
    if not 1 <= beds <= 20:
        raise HTTPException(status_code=400, detail="Beds in a room: 1 to 20.")
    r = db.query(models.CampRoom).filter(models.CampRoom.name == name).first()
    if r:
        used = [b.bed_no for b in db.query(models.CampBed).filter(models.CampBed.room_id == r.id).all()
                if (_taken(b) or (b.booked_name or "").strip()) and b.bed_no > beds]
        if used:
            raise HTTPException(status_code=400, detail=f"Room {name} bed {max(used)} is in use - free it first.")
        for b in db.query(models.CampBed).filter(models.CampBed.room_id == r.id, models.CampBed.bed_no > beds).all():
            db.delete(b)
        r.beds = beds
    else:
        top = max([x.sort or 0 for x in db.query(models.CampRoom).all()] or [0])
        r = models.CampRoom(name=name, beds=beds, sort=top + 1)
        db.add(r)
    _log(db, user, "room", name, None, name=f"{beds} beds")
    db.commit()
    return {"ok": True, "id": r.id}


@router.get("/store/camp/history")
def history(employee_id: int = 0, room: str = "", db: Session = Depends(get_db), user: models.User = VIEW):
    q = db.query(models.CampMove)
    if employee_id:
        q = q.filter(models.CampMove.employee_id == employee_id)
    if room:
        q = q.filter((models.CampMove.room == room) | (models.CampMove.from_room == room))
    users = {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}
    return {"moves": [{"date": m.on_date.isoformat() if m.on_date else "", "kind": m.kind, "name": m.name, "room": m.room,
                       "bed": m.bed_no, "from": f"{m.from_room}/{m.from_bed}" if m.from_room else "", "reason": M.dmy_text(m.reason, m.on_date),
                       "by": users.get(m.by, "automatic")}
                      for m in q.order_by(models.CampMove.id.desc()).limit(200)]}


def _fmt(iso):
    return date.fromisoformat(iso).strftime("%d/%m/%Y") if iso else ""


@router.get("/export/reports/camp")
def export(token: str, format: str = "excel", db: Session = Depends(get_db)):
    u = auth.get_download_user_from_token(token, db)
    perms = M.effective_permissions(u)
    if (u.role or "") != "admin" and "reports" not in perms and RIGHT not in perms:
        raise HTTPException(status_code=403, detail="Labour reports only.")
    seed(db)
    d = listing(db)
    import camp_report as CR
    if format == "view":
        url = f"/export/reports/camp?token={quote(auth.create_view_token(u.username), safe='')}"
        return CR.preview(d, url + "&format=pdf", url + "&format=excel")
    name = f"Labour_Accommodation_{M._dubai_today():%d.%m.%Y}"
    if format == "pdf":
        return StreamingResponse(CR.pdf(d), media_type="application/pdf",
                                 headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})
    return StreamingResponse(CR.excel(d), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename={name}.xlsx"})

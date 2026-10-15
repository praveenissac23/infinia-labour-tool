"""Visa files (Accounts > Petty cash > PRO > Visa files).

Every visa process - a new visa, a renewal, a cancellation - is one file
for one person, with its stages (entry permit, medical, Emirates ID ...).
The PRO ties each petty cash payment to the file and the stage it paid
for, so all the costs of one visa, spread over weeks, add up in one place
and the stage moves on by itself. Stages can also be ticked by hand (a
step with no payment). Mark completed when done: it then drops off the
list the PRO picks from, and keeps its full cost history.
"""
import json
import re
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
RIGHT = "visa"
LOOK = Depends(M.require_any_screen(RIGHT, "petty_pro"))

# Each type starts from the PRO's own list of steps. A file's list can
# change as the case goes (add a step, take one off).
_WP = ["New labour contract", "Contract submission", "WPP insurance", "New work permit", "ILOE insurance"]
KINDS = {
    "new_out": ("New visa (outside UAE)", ["Quota modification", "New labour contract", "WPP insurance", "New work permit",
                                          "New entry permit", "Medical and EID", "Contract submission", "New ILOE insurance",
                                          "New residency stamping"]),
    "new": ("New visa (inside UAE)", ["Quota modification", "New labour contract", "WPP insurance", "New work permit",
                                      "New entry permit (inside)", "Change of status", "Medical and EID", "Contract submission",
                                      "New ILOE insurance", "New residency stamping"]),
    "renewal": ("Visa renewal", ["Labour contract renewal", "WPP insurance", "Work permit renewal and contract submission",
                                 "ILOE insurance renewal", "Medical and EID", "Residency renewal"]),
    "cancel": ("Cancellation (inside UAE)", ["Labour contract cancellation", "Work permit cancellation", "Visa cancellation"]),
    "work_permit": ("Work permit", list(_WP)),
    "national_wp": ("National work permit", list(_WP)),
    "other": ("Visa", []),            # opened from petty cash by typing a new name
}


def steps_master(db):
    """Every step the PRO picks from: the standard lists plus each step he
    has typed in himself (kept, so it is offered next time)."""
    base = []
    for _, (_, st) in KINDS.items():
        base += [x for x in st if x not in base]
    try:
        extra = json.loads(M.get_setting(db, "visa_steps_added") or "[]")
    except ValueError:
        extra = []
    return base + [x for x in extra if x not in base]


def add_step(db, name):
    name = " ".join(str(name or "").split())[:80]
    if not name or name in steps_master(db):
        return name
    try:
        extra = json.loads(M.get_setting(db, "visa_steps_added") or "[]")
    except ValueError:
        extra = []
    extra.append(name)
    M.put_setting(db, "visa_steps_added", json.dumps(extra))
    return name


SUPPLIER = "MOHRE & GDRFA"
# A PRO payment that says this must be on a visa file (from the day Visa
# files started; older lines are left as they are).
MUST = re.compile(r"\bvisa\b|emirates id|entry permit|change of status|labour card", re.I)
START = date(2026, 10, 15)


def must_have_file(x):
    return False      # the PRO answers "Visa related expense?" himself - no check on the words


def _old_must_have_file(x):
    # The description decides, not the supplier: GDRFA / MOHRE also sell
    # travel reports, fines and the like that are no visa.
    return bool(x.on_date and x.on_date >= START and MUST.search(x.description or ""))


LOOKS_VISA = re.compile(r"visa|emirates id|\beid\b|medical fitness|medical test|entry permit|labour card|mohre|gdrfa|\biloe\b|tasheel|\bamer\b|change of status", re.I)


def may_edit(user):
    p = M.effective_permissions(user)
    return (user.role or "") == "admin" or RIGHT in p or "petty_pro" in p


def _editor(user: models.User = Depends(auth.get_current_user)):
    if not may_edit(user):
        raise HTTPException(status_code=403, detail="Visa files are kept by the PRO and accounts.")
    return user


EDIT = Depends(_editor)


def _j(s):
    try:
        v = json.loads(s or "[]")
        return v if isinstance(v, list) else []
    except ValueError:
        return []


def kind_label(k):
    return KINDS.get(k, ("Visa", []))[0]


def _pays(db, ids=None):
    q = db.query(models.PettyCash).filter(models.PettyCash.visa_file_id.isnot(None))
    if ids is not None:
        q = q.filter(models.PettyCash.visa_file_id.in_(list(ids) or [-1]))
    out = {}
    for x in q.order_by(models.PettyCash.on_date, models.PettyCash.id):
        out.setdefault(x.visa_file_id, []).append(x)
    return out


def _dict(v, pays, users, emps=None):
    stages, done = _j(v.stages), set(_j(v.done))
    nxt = next((s for s in stages if s not in done and "(if needed)" not in s), "") or next((s for s in stages if s not in done), "")
    e = (emps or {}).get(v.employee_id)
    lines = [{"id": x.id, "date": x.on_date.isoformat(), "stage": x.visa_stage or "", "description": x.description or "",
              "supplier": x.supplier or "", "amount": round(x.paid or 0, 2), "book": x.book or "",
              "by": users.get(x.created_by, "")} for x in pays]
    return {"id": v.id, "person": v.person, "emp_no": v.emp_no or "", "employee_id": v.employee_id,
            "group": ("Office staff" if e.staff else "Labour") if e else "", "kind": v.kind, "kind_label": kind_label(v.kind),
            "stages": stages, "done": [s for s in stages if s in done], "n_done": sum(1 for s in stages if s in done),
            "next": nxt, "started": v.started_on.isoformat(), "status": v.status,
            "completed": v.completed_on.isoformat() if v.completed_on else "", "completed_by": users.get(v.completed_by, ""),
            "note": v.note or "", "payments": lines, "spent": round(sum(l["amount"] for l in lines), 2)}


def _users(db):
    return {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}


def _emps(db):
    return {e.id: e for e in db.query(models.Employee).all()}


def listing(db, status="ongoing"):
    q = db.query(models.VisaFile)
    allv = q.order_by(models.VisaFile.started_on.desc(), models.VisaFile.id.desc()).all()
    pays, users, emps = _pays(db), _users(db), _emps(db)
    rows = [_dict(v, pays.get(v.id, []), users, emps) for v in allv]
    y = M._dubai_today().year
    on = [r for r in rows if r["status"] == "ongoing"]
    comp_y = [r for r in rows if r["status"] == "completed" and r["completed"][:4] == str(y)]
    show = rows if status == "all" else [r for r in rows if r["status"] == ("completed" if status == "completed" else "ongoing")]
    return {"rows": show, "status": status,
            "tiles": {"ongoing": len(on), "spent_ongoing": round(sum(r["spent"] for r in on), 2),
                      "completed_year": len(comp_y), "spent_completed_year": round(sum(r["spent"] for r in comp_y), 2),
                      "n_completed": sum(1 for r in rows if r["status"] == "completed"), "n_all": len(rows)},
            "kinds": [{"id": k, "label": v[0], "stages": v[1]} for k, v in KINDS.items()]}


def _unlinked(db):
    """PRO petty cash payments of the last 6 months that look like a visa
    cost and are not on any file yet - to tie the costs paid before."""
    since = M._dubai_today() - timedelta(days=183)
    out = []
    for x in (db.query(models.PettyCash).filter(models.PettyCash.book == "pro", models.PettyCash.visa_file_id.is_(None),
                                                 models.PettyCash.paid > 0, models.PettyCash.on_date >= since)
                .order_by(models.PettyCash.on_date.desc(), models.PettyCash.id.desc()).limit(600)):
        if LOOKS_VISA.search(f"{x.description} {x.supplier}"):
            out.append({"id": x.id, "date": x.on_date.isoformat(), "description": x.description or "", "amount": round(x.paid or 0, 2)})
    return out[:200]


@router.get("/store/visa/files")
def get_files(status: str = "ongoing", db: Session = Depends(get_db), user: models.User = LOOK):
    d = listing(db, status if status in ("ongoing", "completed", "all") else "ongoing")
    d["may_edit"] = may_edit(user)
    d["may_pay"] = (user.role or "") == "admin" or "petty_pro" in M.effective_permissions(user)
    d["unlinked"] = _unlinked(db) if d["may_edit"] else []
    d["supplier"] = SUPPLIER
    d["today"] = M._dubai_today().isoformat()
    d["steps"] = steps_master(db)
    return d


@router.get("/store/visa/open")
def open_files(db: Session = Depends(get_db), user: models.User = LOOK):
    """The ongoing files, for the PRO petty cash form."""
    vs = db.query(models.VisaFile).filter(models.VisaFile.status == "ongoing").order_by(models.VisaFile.person).all()
    pays, users = _pays(db, [v.id for v in vs]), _users(db)
    return {"files": [_dict(v, pays.get(v.id, []), users) for v in vs],
            "kinds": [{"id": k, "label": v[0], "stages": v[1]} for k, v in KINDS.items()], "supplier": SUPPLIER,
            "steps": steps_master(db)}


@router.get("/store/visa/people")
def people(db: Session = Depends(get_db), user: models.User = EDIT):
    today = M._dubai_today()
    es = [e for e in db.query(models.Employee).all() if e.active or (e.terminated_on and e.terminated_on >= today - timedelta(days=90))]
    es.sort(key=lambda e: (bool(e.staff), (e.name or "").lower()))
    return {"people": [{"id": e.id, "no": e.emp_no, "name": e.name, "staff": bool(e.staff), "left": not e.active} for e in es]}


def _person(db, payload):
    eid = payload.get("employee_id")
    e = db.get(models.Employee, int(eid)) if str(eid or "").isdigit() else None
    name = " ".join(str(payload.get("person") or "").split())[:80]
    if e:
        return e.id, e.emp_no or "", " ".join((e.name or "").split()).title() if (e.name or "").isupper() else e.name
    if not name:
        raise HTTPException(status_code=400, detail="Whose visa is it? Pick the person.")
    return None, " ".join(str(payload.get("emp_no") or "").split())[:20], name


@router.post("/store/visa/files")
def create(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = EDIT):
    kind = payload.get("kind") or "new"
    if kind not in KINDS:
        raise HTTPException(status_code=400, detail="Pick the type: new visa, renewal or cancellation.")
    eid, no, name = _person(db, payload)
    d = M._as_date(payload.get("started")) or M._dubai_today()
    if d > M._dubai_today():
        raise HTTPException(status_code=400, detail="The start date is in the future.")
    same = db.query(models.VisaFile).filter(models.VisaFile.status == "ongoing", models.VisaFile.kind == kind)
    same = [v for v in same if (eid and v.employee_id == eid) or (not eid and v.person.lower() == name.lower())]
    if same:
        raise HTTPException(status_code=400, detail=f"{name} already has an ongoing {kind_label(kind).lower()} file - use that one.")
    v = models.VisaFile(employee_id=eid, emp_no=no, person=name, kind=kind, stages=json.dumps(KINDS[kind][1]), done="[]",
                        started_on=d, status="ongoing", note=" ".join(str(payload.get("note") or "").split())[:300], created_by=user.id)
    db.add(v); db.commit()
    M.log_action(db, user.id, "visa_file_add", f"Visa file: {name} - {kind_label(kind)}, started {d:%d %b %Y}")
    return _dict(v, [], _users(db), _emps(db))


def _get(db, vid):
    v = db.get(models.VisaFile, vid)
    if not v:
        raise HTTPException(status_code=404, detail="That visa file is no longer there.")
    return v


def _out(db, v):
    return _dict(v, _pays(db, [v.id]).get(v.id, []), _users(db), _emps(db))


@router.put("/store/visa/files/{vid}")
def edit(vid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = EDIT):
    v = _get(db, vid)
    if "note" in payload:
        v.note = "\n".join(" ".join(l.split()) for l in str(payload.get("note") or "").strip().splitlines())[:1500]
    if payload.get("started"):
        d = M._as_date(payload.get("started"))
        if not d or d > M._dubai_today():
            raise HTTPException(status_code=400, detail="Check the start date.")
        v.started_on = d
    db.commit()
    return _out(db, v)


def tick(v, stage, on=True):
    """A step done (or not). A step not on the file's list yet is added to
    it - the list follows the case."""
    stages = _j(v.stages)
    stage = " ".join(str(stage or "").split())[:80]
    if not stage:
        return
    if stage not in stages:
        if not on:
            return
        stages.append(stage); v.stages = json.dumps(stages)
    done = set(_j(v.done))
    done.add(stage) if on else done.discard(stage)
    v.done = json.dumps([s for s in stages if s in done])


@router.post("/store/visa/files/{vid}/stage")
def stage(vid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = EDIT):
    v = _get(db, vid)
    if v.status != "ongoing":
        raise HTTPException(status_code=400, detail="This file is completed - reopen it first.")
    st, on = str(payload.get("stage") or ""), bool(payload.get("done", True))
    tick(v, st, on)
    db.commit()
    M.log_action(db, user.id, "visa_stage", f"Visa file {v.person} ({kind_label(v.kind)}): {st} {'done' if on else 'not done'}")
    return _out(db, v)


@router.post("/store/visa/files/{vid}/steps")
def edit_steps(vid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = EDIT):
    """Add a step to this file's list (a new one joins the list offered next
    time) or take one off (not needed for this case)."""
    v = _get(db, vid)
    stages = _j(v.stages)
    if payload.get("add"):
        st = add_step(db, payload.get("add"))
        if st and st not in stages:
            stages.append(st)
        M.log_action(db, user.id, "visa_step_add", f"Visa file {v.person}: step added - {st}")
    elif payload.get("remove"):
        st = str(payload.get("remove"))
        stages = [x for x in stages if x != st]
        v.done = json.dumps([x for x in _j(v.done) if x != st])
        M.log_action(db, user.id, "visa_step_off", f"Visa file {v.person}: step not needed - {st}")
    v.stages = json.dumps(stages)
    db.commit()
    return _out(db, v)


def held_total(db, vid):
    return round(sum(p.amount or 0 for p in db.query(models.VisaPayment).filter(models.VisaPayment.visa_file_id == vid)), 2)


def post_completed(db, v, user_id):
    """Completed: the payments held for this visa go into PRO petty cash as
    one line - the person's name and the total - dated today, and from
    there to the chief accountant's approval for Zoho like any PRO bill."""
    total = held_total(db, v.id)
    v.status, v.completed_on, v.completed_by = "completed", M._dubai_today(), user_id
    if total > 0 and not v.posted_id:
        n = db.query(models.VisaPayment).filter(models.VisaPayment.visa_file_id == v.id).count()
        x = models.PettyCash(book="pro", on_date=M._dubai_today(), description=f"{v.person} - visa expenses ({n} payment{'' if n == 1 else 's'})",
                             supplier="", site="", received=0, paid=total, visa_file_id=v.id, visa_stage="",
                             created_by=user_id, updated_by=user_id)
        db.add(x); db.flush()
        v.posted_id = x.id
    db.commit()
    M.log_action(db, user_id, "visa_complete", f"Visa completed: {v.person}" + (f" - AED {total:,.2f} moved to PRO petty cash" if total > 0 else ""))
    return total


@router.post("/store/visa/files/{vid}/complete")
def complete(vid: int, db: Session = Depends(get_db), user: models.User = EDIT):
    v = _get(db, vid)
    if v.status != "ongoing":
        raise HTTPException(status_code=400, detail="This visa is already completed.")
    post_completed(db, v, user.id)
    return _out(db, v)


@router.post("/store/visa/files/{vid}/reopen")
def reopen(vid: int, db: Session = Depends(get_db), user: models.User = EDIT):
    """Back to ongoing: its petty cash line is taken out again - only while
    the chief accountant has not approved it for Zoho."""
    v = _get(db, vid)
    if v.posted_id:
        x = db.get(models.PettyCash, v.posted_id)
        if x and (x.zoho_status or ""):
            raise HTTPException(status_code=400, detail="Its petty cash line is already approved for Zoho - ask the chief accountant first.")
        if x:
            db.delete(x)
        v.posted_id = None
    v.status, v.completed_on, v.completed_by = "ongoing", None, None
    db.commit()
    M.log_action(db, user.id, "visa_reopen", f"Visa reopened: {v.person} (its petty cash line taken out)")
    return _out(db, v)


# ---- Visa tab: payments held until the visa is completed ------------------------

def _pay_dict(p, users):
    return {"id": p.id, "date": p.on_date.isoformat(), "step": p.step or "", "amount": round(p.amount or 0, 2), "supplier": p.supplier or "",
            "description": p.description or "", "receipt_no": p.receipt_no or "", "by": users.get(p.created_by, "")}


def held_listing(db):
    users = _users(db)
    pays = {}
    for p in db.query(models.VisaPayment).order_by(models.VisaPayment.on_date.desc(), models.VisaPayment.id.desc()):
        pays.setdefault(p.visa_file_id, []).append(_pay_dict(p, users))
    since = M._dubai_today() - timedelta(days=62)
    out_on, out_done = [], []
    for v in db.query(models.VisaFile).order_by(models.VisaFile.person).all():
        ps = pays.get(v.id, [])
        d = {"id": v.id, "person": v.person, "emp_no": v.emp_no or "", "started": v.started_on.isoformat(), "status": v.status,
             "payments": ps, "total": round(sum(x["amount"] for x in ps), 2), "steps": sorted({x["step"] for x in ps if x["step"]}),
             "completed": v.completed_on.isoformat() if v.completed_on else "", "posted_id": v.posted_id, "note": v.note or ""}
        if v.status == "ongoing":
            out_on.append(d)
        elif ps and v.completed_on and v.completed_on >= since:
            out_done.append(d)
    out_done.sort(key=lambda d: d["completed"], reverse=True)
    return {"ongoing": out_on, "completed": out_done, "held": round(sum(d["total"] for d in out_on), 2),
            "steps": steps_master(db), "today": M._dubai_today().isoformat()}


@router.get("/store/visa/held")
def get_held(db: Session = Depends(get_db), user: models.User = LOOK):
    return held_listing(db)


def _clean_pay(db, payload):
    d = M._as_date(payload.get("date")) or M._dubai_today()
    if d > M._dubai_today():
        raise HTTPException(status_code=400, detail="That date is in the future.")
    try:
        amt = round(float(str(payload.get("amount") or 0).replace(",", "")), 2)
    except ValueError:
        raise HTTPException(status_code=400, detail="The amount must be a number.")
    if amt <= 0:
        raise HTTPException(status_code=400, detail="Enter the amount paid.")
    clip = lambda k, n: " ".join(str(payload.get(k) or "").split())[:n]
    return {"on_date": d, "amount": amt, "step": add_step(db, payload.get("step") or ""), "supplier": clip("supplier", 120),
            "description": clip("description", 300), "receipt_no": clip("receipt_no", 40)}


@router.post("/store/visa/payments")
def add_payment(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = EDIT):
    who = " ".join(str(payload.get("person") or "").split())[:80]
    if not who:
        raise HTTPException(status_code=400, detail="Whose visa? Pick a name or type a new one.")
    c = _clean_pay(db, payload)
    v = file_for(db, who, user.id, c["on_date"])
    p = models.VisaPayment(visa_file_id=v.id, created_by=user.id, **c)
    db.add(p)
    if c["step"]:
        tick(v, c["step"])
    db.commit()
    M.log_action(db, user.id, "visa_payment", f"Visa {v.person}: {c['step'] or 'payment'} AED {c['amount']:,.2f} (held until completed)")
    if payload.get("complete"):
        post_completed(db, v, user.id)
    return {"ok": True, "file_id": v.id}


def _held_pay(db, pid):
    p = db.get(models.VisaPayment, pid)
    if not p:
        raise HTTPException(status_code=404, detail="That payment is no longer there.")
    v = db.get(models.VisaFile, p.visa_file_id)
    if not v or v.status != "ongoing":
        raise HTTPException(status_code=400, detail="This visa is completed - reopen it first.")
    return p, v


@router.put("/store/visa/payments/{pid}")
def edit_payment(pid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = EDIT):
    p, v = _held_pay(db, pid)
    for k, val in _clean_pay(db, payload).items():
        setattr(p, k, val)
    if p.step:
        tick(v, p.step)
    db.commit()
    M.log_action(db, user.id, "visa_payment_edit", f"Visa {v.person}: payment #{pid} now {p.step or 'payment'} AED {p.amount:,.2f}")
    return {"ok": True}


@router.delete("/store/visa/payments/{pid}")
def remove_payment(pid: int, db: Session = Depends(get_db), user: models.User = EDIT):
    p, v = _held_pay(db, pid)
    M.log_action(db, user.id, "visa_payment_delete", f"Visa {v.person}: payment {p.step or ''} AED {p.amount:,.2f} removed")
    db.delete(p); db.commit()
    return {"ok": True}


@router.get("/store/visa/files/{vid}/breakdown")
def breakdown(vid: int, db: Session = Depends(get_db), user: models.User = LOOK):
    """What a 'visa expenses' petty cash line is made of."""
    v = _get(db, vid)
    users = _users(db)
    ps = [_pay_dict(p, users) for p in db.query(models.VisaPayment).filter(models.VisaPayment.visa_file_id == vid)
          .order_by(models.VisaPayment.on_date, models.VisaPayment.id)]
    return {"person": v.person, "note": v.note or "", "completed": v.completed_on.isoformat() if v.completed_on else "", "payments": ps,
            "total": round(sum(x["amount"] for x in ps), 2)}


@router.delete("/store/visa/files/{vid}")
def remove(vid: int, db: Session = Depends(get_db), user: models.User = EDIT):
    v = _get(db, vid)
    if db.query(models.PettyCash).filter(models.PettyCash.visa_file_id == vid).count():
        raise HTTPException(status_code=400, detail="Payments are tied to this file - untie them first, or mark it completed.")
    M.log_action(db, user.id, "visa_file_delete", f"Visa file deleted: {v.person} - {kind_label(v.kind)}")
    db.delete(v); db.commit()
    return {"ok": True}


def file_for(db, who, user_id, on_date=None, keep_id=None):
    """The ongoing visa of this person - or a new one opened for him (the
    PRO typed a name not on the list). The line's own file, if completed
    since, is kept when it is edited."""
    key = who.strip().lower()
    for v in db.query(models.VisaFile).filter(models.VisaFile.status == "ongoing").all():
        if v.person.strip().lower() == key or (v.emp_no and v.emp_no.lower() == key):
            return v
    if keep_id:
        v = db.get(models.VisaFile, keep_id)
        if v and v.person.strip().lower() == key:
            return v
    e = next((e for e in db.query(models.Employee).all()
              if (e.name or "").strip().lower() == key or (e.emp_no or "").lower() == key), None)
    name = (" ".join((e.name or "").split()).title() if (e.name or "").isupper() else e.name) if e else who
    v = models.VisaFile(employee_id=e.id if e else None, emp_no=e.emp_no if e else "", person=name, kind="other",
                        stages="[]", done="[]", started_on=on_date or M._dubai_today(), status="ongoing", created_by=user_id)
    db.add(v); db.flush()
    M.log_action(db, user_id, "visa_file_add", f"Visa opened from PRO petty cash: {name}")
    return v


def check_link(db, vid, stage_name, keep_id=None):
    """For the petty cash form: the file must be ongoing (or the one the
    line is already on) and the stage one of its stages."""
    v = db.get(models.VisaFile, int(vid))
    if not v:
        raise HTTPException(status_code=400, detail="That visa file is no longer there.")
    if v.status != "ongoing" and v.id != keep_id:
        raise HTTPException(status_code=400, detail=f"{v.person}'s visa file is completed - reopen it on Visa files first.")
    return v


@router.post("/store/visa/files/{vid}/link")
def link(vid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = EDIT):
    """Tie a PRO payment made before to this file (and its stage)."""
    v = check_link(db, vid, str(payload.get("stage") or ""))
    x = db.get(models.PettyCash, int(payload.get("petty_id") or 0))
    if not x or (x.book or "") != "pro" or not (x.paid or 0):
        raise HTTPException(status_code=400, detail="Pick a payment from the PRO petty cash.")
    if x.visa_file_id and x.visa_file_id != v.id:
        raise HTTPException(status_code=400, detail="That payment is already on another visa file.")
    x.visa_file_id, x.visa_stage = v.id, add_step(db, payload.get("stage") or "")
    if x.visa_stage:
        tick(v, x.visa_stage)
    db.commit()
    M.log_action(db, user.id, "visa_link", f"Visa file {v.person}: tied {x.on_date:%d %b %Y} {x.description} {x.paid:,.2f}")
    return _out(db, v)


@router.post("/store/visa/files/{vid}/pay")
def pay(vid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = EDIT):
    """A stage paid now: the payment goes into PRO petty cash, tied to this
    file and stage (and on to Send to Zoho like any PRO bill)."""
    import pettycash as P
    v = check_link(db, vid, str(payload.get("stage") or ""))
    st = str(payload.get("stage") or "")
    if not st:
        raise HTTPException(status_code=400, detail="Which step is this payment for?")
    st = add_step(db, st)
    desc = " ".join(str(payload.get("description") or "").split()) or f"{v.person} - {kind_label(v.kind)} - {st}"
    P.add_petty_cash({"book": "pro", "date": payload.get("date"), "description": desc,
                      "supplier": payload.get("supplier") or "",
                      "paid": payload.get("amount"), "receipt_no": payload.get("receipt_no") or "",
                      "visa_file_id": v.id, "visa_stage": st}, db, user)
    db.refresh(v)
    return _out(db, v)


@router.post("/store/visa/files/{vid}/paystage")
def pay_stage(vid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = EDIT):
    """Say which stage a payment already on the file was for."""
    v = _get(db, vid)
    x = db.get(models.PettyCash, int(payload.get("petty_id") or 0))
    if not x or x.visa_file_id != v.id:
        raise HTTPException(status_code=400, detail="That payment is not on this file.")
    st = add_step(db, payload.get("stage") or "")
    x.visa_stage = st
    if st:
        tick(v, st)
    db.commit()
    M.log_action(db, user.id, "visa_paystage", f"Visa file {v.person}: {x.on_date:%d %b %Y} {x.paid:,.2f} was for {st or '-'}")
    return _out(db, v)


@router.post("/store/visa/files/{vid}/unlink")
def unlink(vid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = EDIT):
    v = _get(db, vid)
    x = db.get(models.PettyCash, int(payload.get("petty_id") or 0))
    if not x or x.visa_file_id != v.id:
        raise HTTPException(status_code=400, detail="That payment is not on this file.")
    x.visa_file_id, x.visa_stage = None, ""
    db.commit()
    M.log_action(db, user.id, "visa_unlink", f"Visa file {v.person}: untied {x.on_date:%d %b %Y} {x.description} {x.paid:,.2f}")
    return _out(db, v)


def _fmt(iso):
    return date.fromisoformat(iso).strftime("%d-%b-%y") if iso else ""


@router.get("/export/visa")
def export(token: str, format: str = "excel", status: str = "ongoing", db: Session = Depends(get_db)):
    u = auth.get_download_user_from_token(token, db)
    p = M.effective_permissions(u)
    if (u.role or "") != "admin" and RIGHT not in p and "petty_pro" not in p:
        raise HTTPException(status_code=403, detail="Visa files are for the PRO and accounts.")
    status = status if status in ("ongoing", "completed", "all") else "ongoing"
    d = listing(db, status)
    title = {"ongoing": "Visa Files - Ongoing", "completed": "Visa Files - Completed", "all": "Visa Files"}[status]
    rows = []
    for r in d["rows"]:
        rows.append({"Person": r["person"], "ID": r["emp_no"], "Type": r["kind_label"], "Started": _fmt(r["started"]),
                     "Stages": f"{r['n_done']} of {len(r['stages'])}" + (f" - next: {r['next']}" if r["next"] and r["status"] == "ongoing" else ""),
                     "Status": "Completed " + _fmt(r["completed"]) if r["status"] == "completed" else "Ongoing",
                     "Payments": "; ".join(f"{_fmt(l['date'])} {l['stage'] or l['description']} {l['amount']:,.2f}" for l in r["payments"]),
                     "Spent (AED)": r["spent"]})
    t = d["tiles"]
    total = round(sum(r["spent"] for r in d["rows"]), 2)
    sub = (f"{len(rows)} file(s) | spent AED {total:,.2f} | ongoing: {t['ongoing']} (AED {t['spent_ongoing']:,.2f})"
           f" | As at {M._dubai_today():%d %b %Y}")
    if format == "view":
        url = f"/export/visa?status={status}&token={quote(auth.create_view_token(u.username), safe='')}"
        return M._preview_page(title, sub, rows, url, url, money_cols=["Spent (AED)"])
    name = f"{title.replace(' ', '_').replace('_-_', '_')}_{M._dubai_today():%d.%m.%Y}"
    if format == "pdf":
        return StreamingResponse(export_web.build_store_report_pdf(title, rows, sub, money_cols=["Spent (AED)"], orientation="landscape"),
                                 media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})
    return StreamingResponse(export_web.build_store_report_excel(title, rows, sub, money_cols=["Spent (AED)"]),
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename={name}.xlsx"})


# The visas in progress when Visa files went live (PRO book, October 2026),
# agreed with Praveen: (petty cash id, amount, person, emp no, type).
SEED = [(2891, 4570.33, "Eric Mambo", "", "new"),
        (3050, 278.77, "Hebson Hondra", "", "new_out"),
        (3051, 76.14, "Ian Kiplayapy", "", "new_out"),
        (2897, 4724.85, "", "F-732", "renewal"),
        (2893, 5272.70, "", "F-727", "renewal"),
        (2894, 5272.70, "", "F-728", "renewal"),
        (2895, 5272.70, "", "F-729", "renewal"),
        (2896, 5272.70, "", "F-730", "renewal")]


def seed_existing(db):
    """Once: a file for each visa in progress, its payment tied to it. A
    line is tied only if it is still that PRO payment (same amount, not on
    a file) - anything else is left for the PRO to tie by hand."""
    if db.query(models.Setting).filter(models.Setting.key == "visa_seed_oct26").first():
        return 0
    key = lambda n: "".join(ch for ch in str(n or "").upper() if ch.isalnum())
    emps = {key(e.emp_no): e for e in db.query(models.Employee).all()}
    n = 0
    for pid, amt, name, no, kind in SEED:
        x = db.get(models.PettyCash, pid)
        if not x or (x.book or "") != "pro" or abs((x.paid or 0) - amt) > 0.005 or x.visa_file_id:
            continue
        e = emps.get(key(no)) if no else None
        person = (" ".join((e.name or "").split()).title() if e else name) or no
        v = models.VisaFile(employee_id=e.id if e else None, emp_no=e.emp_no if e else no, person=person, kind=kind,
                            stages=json.dumps(KINDS[kind][1]), done="[]", started_on=x.on_date, status="ongoing",
                            note="Opened when Visa files started - tick the stages already done")
        db.add(v); db.flush()
        x.visa_file_id, x.visa_stage = v.id, ""
        n += 1
    db.add(models.Setting(key="visa_seed_oct26", value=str(n)))
    db.commit()
    return n


def new_step_lists(db):
    """Once: files with no step ticked yet take the PRO's new step lists."""
    if db.query(models.Setting).filter(models.Setting.key == "visa_steps_v2").first():
        return 0
    n = 0
    for v in db.query(models.VisaFile).all():
        if not _j(v.done) and v.kind in KINDS:
            v.stages = json.dumps(KINDS[v.kind][1]); n += 1
    db.add(models.Setting(key="visa_steps_v2", value=str(n)))
    db.commit()
    return n


def drop_if_needed(db):
    """Once: the "(if needed)" tail taken off step names everywhere."""
    if db.query(models.Setting).filter(models.Setting.key == "visa_steps_ifneeded").first():
        return
    fix = lambda t: (t or "").replace(" (if needed)", "")
    for v in db.query(models.VisaFile).all():
        v.stages = json.dumps(list(dict.fromkeys(fix(x) for x in _j(v.stages))))
        v.done = json.dumps(list(dict.fromkeys(fix(x) for x in _j(v.done))))
    for x in db.query(models.PettyCash).filter(models.PettyCash.visa_stage.like("% (if needed)%")).all():
        x.visa_stage = fix(x.visa_stage)
    try:
        extra = json.loads(M.get_setting(db, "visa_steps_added") or "[]")
        M.put_setting(db, "visa_steps_added", json.dumps(list(dict.fromkeys(fix(x) for x in extra))))
    except ValueError:
        pass
    db.add(models.Setting(key="visa_steps_ifneeded", value="1"))
    db.commit()


# Agreed with Praveen (15 Oct): the October visa lines still in progress go
# from PRO petty cash to the Visa tab (held); the completed ones stay.
HOLD_MOVE = {2891: 4570.33, 3050: 278.77, 3051: 76.14, 2895: 5272.70, 2896: 5272.70}
DONE_KEEP = (2893, 2894, 2897)


def move_ongoing_to_held(db):
    """Once. A line is moved only if it is still that PRO payment, on an
    ongoing visa, and not approved for (or sent to) Zoho."""
    if db.query(models.Setting).filter(models.Setting.key == "visa_held_move_oct26").first():
        return []
    moved = []
    for pid, amt in HOLD_MOVE.items():
        x = db.get(models.PettyCash, pid)
        if not x or (x.book or "") != "pro" or abs((x.paid or 0) - amt) > 0.005 or (x.zoho_status or "") or not x.visa_file_id:
            continue
        v = db.get(models.VisaFile, x.visa_file_id)
        if not v or v.status != "ongoing":
            continue
        db.add(models.VisaPayment(visa_file_id=v.id, on_date=x.on_date, step=x.visa_stage or "", amount=round(x.paid, 2),
                                  supplier=x.supplier or "", description=x.description or "", receipt_no=x.receipt_no or "",
                                  created_by=x.created_by))
        moved.append(f"{v.person} {amt:,.2f}")
        db.delete(x)
    for pid in DONE_KEEP:
        x = db.get(models.PettyCash, pid)
        v = db.get(models.VisaFile, x.visa_file_id) if x and x.visa_file_id else None
        if v and v.status == "ongoing":
            v.status, v.completed_on = "completed", x.on_date
    db.add(models.Setting(key="visa_held_move_oct26", value="; ".join(moved)))
    db.commit()
    if moved:
        M.log_action(db, None, "visa_moved_held", "Ongoing visa lines moved from PRO petty cash to the Visa tab: " + ", ".join(moved))
    return moved


def tidy_oct15(db):
    """Once (agreed 15 Oct): Ian Kiplayapy's line (now 354.91) to the Visa
    tab like the other four; the two empty test visas removed."""
    if db.query(models.Setting).filter(models.Setting.key == "visa_tidy_oct15").first():
        return []
    done = []
    x = db.get(models.PettyCash, 3051)
    if x and (x.book or "") == "pro" and abs((x.paid or 0) - 354.91) <= 0.005 and not (x.zoho_status or "") and x.visa_file_id:
        v = db.get(models.VisaFile, x.visa_file_id)
        if v and v.status == "ongoing":
            db.add(models.VisaPayment(visa_file_id=v.id, on_date=x.on_date, step=x.visa_stage or "", amount=round(x.paid, 2),
                                      supplier=x.supplier or "", description=x.description or "", receipt_no=x.receipt_no or "",
                                      created_by=x.created_by))
            db.delete(x); done.append("Ian Kiplayapy 354.91 moved to the Visa tab")
    for name in ("Abdul Matin", "sreelakshmi new visa exp out side"):
        for v in db.query(models.VisaFile).filter(models.VisaFile.person == name).all():
            if not db.query(models.VisaPayment).filter(models.VisaPayment.visa_file_id == v.id).count() \
                    and not db.query(models.PettyCash).filter(models.PettyCash.visa_file_id == v.id).count():
                db.delete(v); done.append(f"empty visa '{name}' removed")
    db.add(models.Setting(key="visa_tidy_oct15", value="; ".join(done)))
    db.commit()
    if done:
        M.log_action(db, None, "visa_tidy", "; ".join(done))
    return done


# ---- the sheet the PRO hands to accounts ----------------------------------------

def sheet_pdf(v, pays):
    """'<Name> Visa Expenses': No / Item / Amount, the total, the PRO's note
    (e.g. a deduction from the worker's salary) and the signatures - on the
    company's letterhead, one page, signatures kept with the note."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT, TA_CENTER
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepTogether
    from html import escape
    import io
    R = colors.HexColor("#B7322A")
    base = ParagraphStyle("b", fontName="Helvetica", fontSize=9.5, leading=12.5)
    bold = ParagraphStyle("bb", parent=base, fontName="Helvetica-Bold")
    rt, rtb = ParagraphStyle("r", parent=base, alignment=TA_RIGHT), ParagraphStyle("rb", parent=bold, alignment=TA_RIGHT)
    cen = ParagraphStyle("c", parent=base, alignment=TA_CENTER)
    hd = ParagraphStyle("h", parent=bold, fontSize=8.5, textColor=colors.white)
    small = ParagraphStyle("s", parent=base, fontSize=8, leading=10, textColor=colors.HexColor("#777777"))
    P = lambda t, st=base: Paragraph(escape(str(t)).replace("\n", "<br/>"), st)
    buf = io.BytesIO()
    W = A4[0] - 32 * mm
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
                            title=f"{v.person} Visa Expenses")
    logo = export_web._logo_image(46)
    top = Table([[logo or P("INFINIA", bold), Paragraph("VISA EXPENSES", ParagraphStyle("t", parent=bold, fontSize=16, leading=20, textColor=R, alignment=TA_RIGHT))]],
                colWidths=[W / 2, W / 2])
    top.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("LINEBELOW", (0, 0), (-1, 0), 1.5, R),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    dmy = lambda d: d.strftime("%d-%m-%Y") if d else ""
    span = f"{dmy(min(p.on_date for p in pays))} to {dmy(max(p.on_date for p in pays))}" if pays else dmy(v.started_on)
    title = Paragraph(f"<b>{escape(v.person)} Visa Expenses</b>" + (f" &nbsp;<font color='#777777'>{escape(v.emp_no)}</font>" if v.emp_no else "")
                      + f" &nbsp;<font color='#777777'>( {span} )</font>", ParagraphStyle("tt", parent=base, fontSize=12, leading=16))
    st_txt = f"Completed {dmy(v.completed_on)}" if v.status == "completed" else "In progress"
    data = [[P("NO", hd), P("ITEM", hd), P("DATE", ParagraphStyle("hc", parent=hd, alignment=TA_CENTER)), P("AMOUNT (AED)", ParagraphStyle("hr", parent=hd, alignment=TA_RIGHT))]]
    for i, p in enumerate(pays, 1):
        item = p.step or p.description or "Payment"
        extra = " · ".join(x for x in ((p.description if p.step and p.description else ""), p.supplier or "", f"Rcpt {p.receipt_no}" if p.receipt_no else "") if x)
        data.append([P(i, cen), Paragraph(escape(item) + (f"<br/><font size='7.5' color='#777777'>{escape(extra)}</font>" if extra else ""), base),
                     P(dmy(p.on_date), cen), P(f"{p.amount or 0:,.2f}", rt)])
    total = round(sum(p.amount or 0 for p in pays), 2)
    data.append(["", P("Total", bold), "", P(f"{total:,.2f}", rtb)])
    t = Table(data, colWidths=[W * .08, W * .6, W * .14, W * .18], repeatRows=1)
    sty = [("BACKGROUND", (0, 0), (-1, 0), R), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
           ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#BBBBBB")), ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F3F1EF")),
           ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]
    t.setStyle(TableStyle(sty))
    tail = []
    if (v.note or "").strip():
        tail += [Spacer(1, 10), Paragraph(f"<b>Note:</b> {escape(v.note).replace(chr(10), '<br/>')}", ParagraphStyle("n", parent=base, fontSize=10, leading=14))]
    sign = Table([[P("Prepared by (PRO)", cen), "", P("Checked by (Accounts)", cen), "", P("Approved by", cen)]],
                 colWidths=[W * .28, W * .08, W * .28, W * .08, W * .28])
    sign.setStyle(TableStyle([("LINEABOVE", (0, 0), (0, 0), .8, colors.black), ("LINEABOVE", (2, 0), (2, 0), .8, colors.black),
                              ("LINEABOVE", (4, 0), (4, 0), .8, colors.black)]))
    tail += [Spacer(1, 46), sign, Spacer(1, 8), P(f"{st_txt} · {len(pays)} payment{'' if len(pays) == 1 else 's'} · printed {dmy(M._dubai_today())}", small)]
    doc.build([top, Spacer(1, 10), title, Spacer(1, 8), t, KeepTogether(tail)])
    buf.seek(0)
    return buf


@router.get("/export/visa/file/{vid}")
def export_sheet(vid: int, token: str, format: str = "view", dl: int = 0, db: Session = Depends(get_db)):
    from fastapi.responses import HTMLResponse
    from html import escape
    u = auth.get_download_user_from_token(token, db)
    pp = M.effective_permissions(u)
    if (u.role or "") != "admin" and RIGHT not in pp and "petty_pro" not in pp:
        raise HTTPException(status_code=403, detail="Visa expenses are for the PRO and accounts.")
    v = db.get(models.VisaFile, vid)
    if not v:
        raise HTTPException(status_code=404, detail="That visa is no longer there.")
    pays = (db.query(models.VisaPayment).filter(models.VisaPayment.visa_file_id == vid)
            .order_by(models.VisaPayment.on_date, models.VisaPayment.id).all())
    name = "".join(ch for ch in v.person if ch.isalnum() or ch in " -").strip().replace(" ", "_") + "_Visa_Expenses"
    if format == "view":
        vt = quote(auth.create_view_token(u.username), safe="")
        pdf, xl = f"/export/visa/file/{vid}?format=pdf&token={vt}", f"/export/visa/file/{vid}?format=excel&token={vt}"
        title = f"{v.person} Visa Expenses"
        return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><style>{export_web.PREVIEW_BAR_CSS}
body{{margin:0;background:#E9E6E2;font-family:Arial,Helvetica,sans-serif}} .pg{{max-width:900px;margin:18px auto 30px;padding:0 12px}}
.pg iframe{{width:100%;height:1180px;border:0;background:#fff;box-shadow:0 2px 14px rgba(0,0,0,.12);border-radius:3px}}</style></head><body>
<div class="pvbar"><h1>{escape(title)}</h1><span class="who">{len(pays)} payment(s) &middot; AED {sum(p.amount or 0 for p in pays):,.2f}</span><span class="sp"></span>
<a class="btn dark" href="{pdf}&dl=1">Download PDF</a><a class="btn" href="{xl}">Excel</a><a class="btn" href="{pdf}" target="_blank" rel="noopener">Print</a>{export_web.share_button(pdf, title)}</div>
<div class="pg"><iframe src="{pdf}#toolbar=0&view=FitH" title="{escape(title)}"></iframe></div>
{export_web.SHARE_JS}</body></html>""")
    if format == "excel":
        rows = [{"No": i, "Item": p.step or p.description or "Payment", "Details": " · ".join(x for x in ((p.description if p.step else ""), p.supplier or "", f"Rcpt {p.receipt_no}" if p.receipt_no else "") if x),
                 "Date": p.on_date.strftime("%d-%b-%y"), "Amount (AED)": round(p.amount or 0, 2)} for i, p in enumerate(pays, 1)]
        sub = f"{v.person}{' ' + v.emp_no if v.emp_no else ''} | {'Completed ' + v.completed_on.strftime('%d %b %Y') if v.completed_on else 'In progress'}" + (f" | Note: {v.note}" if v.note else "")
        return StreamingResponse(export_web.build_store_report_excel(f"{v.person} Visa Expenses", rows, sub, money_cols=["Amount (AED)"]),
                                 media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 headers={"Content-Disposition": f"attachment; filename={name}.xlsx"})
    return StreamingResponse(sheet_pdf(v, pays), media_type="application/pdf",
                             headers={"Content-Disposition": f'{"attachment" if dl else "inline"}; filename="{name}.pdf"'})

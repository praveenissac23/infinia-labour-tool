"""Visa files (Reports > Labour > Visa files).

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

KINDS = {
    "new": ("New visa", ["Entry permit", "Change of status", "Medical test", "Emirates ID", "Labour contract (MOHRE)",
                         "Insurance (ILOE / medical)", "Visa stamping", "EID collected"]),
    "new_out": ("New visa (outside UAE)", ["Entry permit", "Entry to UAE", "Medical test", "Emirates ID", "Labour contract (MOHRE)",
                                          "Insurance (ILOE / medical)", "Visa stamping", "EID collected"]),
    "renewal": ("Renewal", ["Medical test", "Emirates ID", "Labour contract (MOHRE)", "Insurance (ILOE / medical)",
                            "Visa stamping", "EID collected"]),
    "cancel": ("Cancellation", ["Labour card cancel", "Visa cancel", "File closed"]),
}
SUPPLIER = "MOHRE & GDRFA"
LOOKS_VISA = re.compile(r"visa|emirates id|\beid\b|medical|entry permit|labour card|mohre|gdrfa|ilo|insurance|tasheel|amer", re.I)


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
    nxt = next((s for s in stages if s not in done), "")
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
    d["unlinked"] = _unlinked(db) if d["may_edit"] else []
    return d


@router.get("/store/visa/open")
def open_files(db: Session = Depends(get_db), user: models.User = LOOK):
    """The ongoing files, for the PRO petty cash form."""
    vs = db.query(models.VisaFile).filter(models.VisaFile.status == "ongoing").order_by(models.VisaFile.person).all()
    pays, users = _pays(db, [v.id for v in vs]), _users(db)
    return {"files": [_dict(v, pays.get(v.id, []), users) for v in vs],
            "kinds": [{"id": k, "label": v[0], "stages": v[1]} for k, v in KINDS.items()], "supplier": SUPPLIER}


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
        v.note = " ".join(str(payload.get("note") or "").split())[:300]
    if payload.get("started"):
        d = M._as_date(payload.get("started"))
        if not d or d > M._dubai_today():
            raise HTTPException(status_code=400, detail="Check the start date.")
        v.started_on = d
    db.commit()
    return _out(db, v)


def tick(v, stage, on=True):
    stages = _j(v.stages)
    if stage not in stages:
        raise HTTPException(status_code=400, detail=f"'{stage}' is not a stage of this file.")
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


@router.post("/store/visa/files/{vid}/complete")
def complete(vid: int, db: Session = Depends(get_db), user: models.User = EDIT):
    v = _get(db, vid)
    v.status, v.completed_on, v.completed_by = "completed", M._dubai_today(), user.id
    db.commit()
    M.log_action(db, user.id, "visa_complete", f"Visa file completed: {v.person} - {kind_label(v.kind)}")
    return _out(db, v)


@router.post("/store/visa/files/{vid}/reopen")
def reopen(vid: int, db: Session = Depends(get_db), user: models.User = EDIT):
    v = _get(db, vid)
    v.status, v.completed_on, v.completed_by = "ongoing", None, None
    db.commit()
    M.log_action(db, user.id, "visa_reopen", f"Visa file reopened: {v.person} - {kind_label(v.kind)}")
    return _out(db, v)


@router.delete("/store/visa/files/{vid}")
def remove(vid: int, db: Session = Depends(get_db), user: models.User = EDIT):
    v = _get(db, vid)
    if db.query(models.PettyCash).filter(models.PettyCash.visa_file_id == vid).count():
        raise HTTPException(status_code=400, detail="Payments are tied to this file - untie them first, or mark it completed.")
    M.log_action(db, user.id, "visa_file_delete", f"Visa file deleted: {v.person} - {kind_label(v.kind)}")
    db.delete(v); db.commit()
    return {"ok": True}


def check_link(db, vid, stage_name, keep_id=None):
    """For the petty cash form: the file must be ongoing (or the one the
    line is already on) and the stage one of its stages."""
    v = db.get(models.VisaFile, int(vid))
    if not v:
        raise HTTPException(status_code=400, detail="That visa file is no longer there.")
    if v.status != "ongoing" and v.id != keep_id:
        raise HTTPException(status_code=400, detail=f"{v.person}'s visa file is completed - reopen it on Visa files first.")
    if stage_name and stage_name not in _j(v.stages):
        raise HTTPException(status_code=400, detail=f"'{stage_name}' is not a stage of this visa file.")
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
    x.visa_file_id, x.visa_stage = v.id, str(payload.get("stage") or "")
    if x.visa_stage:
        tick(v, x.visa_stage)
    db.commit()
    M.log_action(db, user.id, "visa_link", f"Visa file {v.person}: tied {x.on_date:%d %b %Y} {x.description} {x.paid:,.2f}")
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

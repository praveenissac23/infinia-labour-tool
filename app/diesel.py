"""Store > Diesel.

Diesel comes to site from a supplier (into jars, or straight into a
machine) and is used a little at a time - a generator at 09:13, a
compressor at 09:15. Every lot in and every fill out is booked here with
its time, so the diesel received and the diesel used can be set side by
side, site by site, and what should still be in the jars is known.

Kept in litres. The unit is the user's choice - litres, imperial gallons
or US gallons - both when typing and when reading.
"""
import re
from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

import main as M
import models
from database import get_db

router = APIRouter()
DG = Depends(M.require_any_screen("store", "storekeeper"))
UNITS = {"L": 1.0, "IG": 4.54609, "USG": 3.785411784}
UNIT_LABEL = {"L": "Litres", "IG": "Gallons (imperial)", "USG": "Gallons (US)"}
UNIT_SHORT = {"L": "L", "IG": "gal", "USG": "US gal"}


def _users(db):
    return {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}


def _row(e, users):
    return {"id": e.id, "site": e.site or "", "kind": e.kind, "date": e.on_date.isoformat(), "time": e.on_time or "",
            "litres": round(e.litres or 0, 3), "unit": e.unit or "L", "qty": e.qty or 0, "supplier": e.supplier or "",
            "dn_no": e.dn_no or "", "machine": e.machine or "", "note": e.note or "",
            "by": users.get(e.created_by, ""), "by_id": e.created_by}


def _sites(db):
    return [s.code for s in db.query(models.Site).filter(models.Site.active.isnot(False)).order_by(models.Site.code).all()
            if (s.code or "").strip().lower() not in ("office",)]


def _clean(p, db):
    kind = (p.get("kind") or "").strip()
    if kind not in ("in", "use"):
        raise HTTPException(400, "Pick Received or Used.")
    site = " ".join(str(p.get("site") or "").split())
    if not site:
        raise HTTPException(400, "Pick the site.")
    if site not in _sites(db) and not db.query(models.Site).filter(models.Site.code == site).first():
        raise HTTPException(400, f"Site {site} is not on the site list.")
    d = M._as_date(p.get("date")) if p.get("date") else None
    if not d:
        raise HTTPException(400, "Give the date.")
    if d > M._dubai_today():
        raise HTTPException(400, "The date is in the future.")
    t = (p.get("time") or "").strip()
    if t and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t):
        raise HTTPException(400, "Time as HH:MM, e.g. 09:13.")
    unit = p.get("unit") or "L"
    if unit not in UNITS:
        raise HTTPException(400, "Unknown unit.")
    try:
        qty = round(float(p.get("qty")), 3)
    except (TypeError, ValueError):
        raise HTTPException(400, "Give the quantity.")
    if qty <= 0:
        raise HTTPException(400, "The quantity must be more than 0.")
    machine = " ".join(str(p.get("machine") or "").split())
    if kind == "use" and not machine:
        raise HTTPException(400, "Which machine was it filled into?")
    return dict(kind=kind, site=site, on_date=d, on_time=t, unit=unit, qty=qty, litres=round(qty * UNITS[unit], 4),
                supplier=" ".join(str(p.get("supplier") or "").split()) if kind == "in" else "",
                dn_no=str(p.get("dn_no") or "").strip() if kind == "in" else "",
                machine=machine, note=str(p.get("note") or "").strip())


def _may_change(user, e):
    return (user.role or "") == "admin" or e.created_by == user.id


@router.get("/store/diesel")
def listing(db: Session = Depends(get_db), user: models.User = DG):
    users = _users(db)
    rows = [_row(e, users) for e in db.query(models.DieselEntry)
            .order_by(models.DieselEntry.on_date.desc(), models.DieselEntry.on_time.desc(), models.DieselEntry.id.desc()).limit(20000)]
    machines = sorted({r["machine"] for r in rows if r["machine"]}, key=str.lower)
    sups = {}
    for (n,) in db.query(models.Supplier.name).filter(models.Supplier.deleted_at.is_(None)).all():
        n = " ".join((n or "").split())
        if n:
            sups.setdefault(n.lower(), n)
    for r in rows:
        if r["supplier"]:
            sups.setdefault(r["supplier"].lower(), r["supplier"])
    return {"rows": rows, "sites": _sites(db), "machines": machines, "suppliers": sorted(sups.values(), key=str.lower),
            "units": [{"id": k, "label": UNIT_LABEL[k], "short": UNIT_SHORT[k], "litres": v} for k, v in UNITS.items()],
            "me": user.id, "admin": (user.role or "") == "admin"}


@router.post("/store/diesel")
def create(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = DG):
    e = models.DieselEntry(**_clean(payload, db), created_by=user.id)
    db.add(e)
    db.commit()
    db.refresh(e)
    M.log_action(db, user.id, "diesel_add", f"Diesel {'received' if e.kind == 'in' else 'used'} {e.qty:g} {e.unit} at {e.site} on {e.on_date:%d/%m/%Y}"
                 + (f" - {e.machine}" if e.machine else ""))
    return _row(e, _users(db))


@router.put("/store/diesel/{eid}")
def edit(eid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = DG):
    e = db.query(models.DieselEntry).get(eid)
    if not e:
        raise HTTPException(404, "Entry not found.")
    if not _may_change(user, e):
        raise HTTPException(403, "Only whoever booked it (or an admin) can change it.")
    for k, v in _clean(payload, db).items():
        setattr(e, k, v)
    db.commit()
    M.log_action(db, user.id, "diesel_edit", f"Diesel entry {eid} changed: {e.kind} {e.qty:g} {e.unit} at {e.site} on {e.on_date:%d/%m/%Y}")
    return _row(e, _users(db))


@router.delete("/store/diesel/{eid}")
def remove(eid: int, db: Session = Depends(get_db), user: models.User = DG):
    e = db.query(models.DieselEntry).get(eid)
    if not e:
        raise HTTPException(404, "Entry not found.")
    if not _may_change(user, e):
        raise HTTPException(403, "Only whoever booked it (or an admin) can remove it.")
    M.log_action(db, user.id, "diesel_delete", f"Diesel entry removed: {e.kind} {e.qty:g} {e.unit} at {e.site} on {e.on_date:%d/%m/%Y}")
    db.delete(e)
    db.commit()
    return {"ok": True}


def _fmt(v):
    return round(v + 0.0, 2)


@router.get("/export/store/diesel")
def export(token: str, format: str = "excel", site: str = "", date_from: str = "", date_to: str = "", unit: str = "IG",
           db: Session = Depends(get_db)):
    """The diesel log as filtered on screen: in, used and what should be left, line by line."""
    from urllib.parse import quote, urlencode
    import auth, export_web
    u = auth.get_download_user_from_token(token, db)
    perms = M.effective_permissions(u)
    if (u.role or "") != "admin" and not ({"store", "storekeeper"} & set(perms)):
        raise HTTPException(403, "Diesel is for the store.")
    unit = unit if unit in UNITS else "IG"
    f = UNITS[unit]
    sh = UNIT_SHORT[unit]
    df = M._as_date(date_from) if date_from else None
    dt_ = M._as_date(date_to) if date_to else None
    q = db.query(models.DieselEntry)
    if site:
        q = q.filter(models.DieselEntry.site == site)
    ents = q.order_by(models.DieselEntry.site, models.DieselEntry.on_date, models.DieselEntry.on_time, models.DieselEntry.id).all()
    users = _users(db)
    bal, out = {}, []
    tin = tuse = 0.0
    for e in ents:
        lin = e.litres if e.kind == "in" else 0.0
        luse = e.litres if (e.kind == "use" or (e.kind == "in" and e.machine)) else 0.0
        before = df and e.on_date < df
        bal[e.site] = bal.get(e.site, 0.0) + lin - luse
        if before or (dt_ and e.on_date > dt_):
            continue
        tin += lin
        tuse += luse
        what = ("Received straight into " + e.machine) if (e.kind == "in" and e.machine) else ("Received" if e.kind == "in" else "Used")
        out.append({"Date": e.on_date.strftime("%d/%m/%Y"), "Time": e.on_time or "", "Site": e.site, "What": what,
                    "Machine": e.machine if e.kind == "use" else (e.machine or ""),
                    "Supplier / DN": " - ".join(x for x in (e.supplier, e.dn_no and f"DN {e.dn_no}") if x),
                    f"In ({sh})": _fmt(lin / f) if lin else "", f"Used ({sh})": _fmt(luse / f) if luse else "",
                    f"Left ({sh})": _fmt(bal[e.site] / f), "Booked by": users.get(e.created_by, ""), "Note": e.note or ""})
    title = "Diesel - In and Used"
    span = (f"{df:%d/%m/%Y} to {dt_:%d/%m/%Y}" if df and dt_ else f"from {df:%d/%m/%Y}" if df else f"up to {dt_:%d/%m/%Y}" if dt_ else "all dates")
    sub = (f"{'Site ' + site if site else 'All sites'} | {span} | In {tin / f:,.2f} {sh}, used {tuse / f:,.2f} {sh} | "
           f"{UNIT_LABEL[unit]} | As at {M._dubai_today():%d/%m/%Y}")
    if format == "view":
        vt = quote(auth.create_view_token(u.username), safe="")
        url = f"/export/store/diesel?{urlencode({'site': site, 'date_from': date_from, 'date_to': date_to, 'unit': unit})}&token={vt}"
        return M._preview_page(title, sub, out, url, url, money_cols=[])
    name = "Diesel" + (f"_{site}" if site else "") + f"_{(df or M._dubai_today()):%d.%m.%Y}" + (f"_to_{dt_:%d.%m.%Y}" if dt_ else "")
    if format == "pdf":
        return StreamingResponse(export_web.build_store_report_pdf(title, out, sub, money_cols=[], orientation="landscape"),
                                 media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})
    return StreamingResponse(export_web.build_store_report_excel(title, out, sub, money_cols=[]),
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename={name}.xlsx"})

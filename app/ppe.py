"""PPE register (Reports > Labour > PPE): coveralls, safety shoes, helmets
and the like handed to workers - kept so they are not asked for again and
again.

Each item has a limit (e.g. safety shoes: 1 in 6 months). Giving one
sooner is allowed, but only with a reason, and it shows red everywhere.
"Eligible" lines (approved, not handed over yet) do not count until given.
"""
import json
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
RIGHT = "ppe"
VIEW = Depends(M.require_any_screen("reports", RIGHT))

# item -> (how many, in how many months)
LIMITS = {"Coverall": (2, 6), "Safety Shoes": (1, 6), "Safety Vest": (1, 6), "Helmet": (1, 12),
          "Jacket": (1, 12), "Driver T-Shirt": (2, 6), "Engineer Vest": (1, 6)}
SIZES = {"Coverall": ["S", "M", "L", "XL", "XXL", "XXXL"], "Safety Shoes": [str(n) for n in range(38, 47)],
         "Helmet": ["Blue", "White", "Yellow", "Red", "Green"], "Safety Vest": ["M", "L", "XL", "XXL"],
         "Jacket": ["M", "L", "XL", "XXL"], "Driver T-Shirt": ["S", "M", "L", "XL", "XXL"], "Engineer Vest": ["M", "L", "XL", "XXL"]}
NOT_GIVEN = ("Eligible",)


def _key(no):
    return "".join(ch for ch in str(no or "").upper() if ch.isalnum())


def may_edit(user):
    return (user.role or "") == "admin" or RIGHT in M.effective_permissions(user)


def _editor(user: models.User = Depends(auth.get_current_user)):
    if not may_edit(user):
        raise HTTPException(status_code=403, detail="Only the PRO, the store keeper and accounts record PPE.")
    return user


EDIT = Depends(_editor)


def limits(db):
    try:
        saved = json.loads(M.get_setting(db, "ppe_limits") or "{}")
    except ValueError:
        saved = {}
    out = dict(LIMITS)
    out.update({k: tuple(v) for k, v in saved.items() if isinstance(v, (list, tuple)) and len(v) == 2})
    return out


def _months_ago(d, months):
    y, m = d.year, d.month - months
    while m <= 0:
        m += 12; y -= 1
    day = min(d.day, [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return date(y, m, day)


def _months_after(d, months):
    y, m = d.year, d.month + months
    while m > 12:
        m -= 12; y += 1
    day = min(d.day, [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return date(y, m, day)


def seed(db):
    """The register kept in Excel until now - loaded once."""
    if db.query(models.PpeIssue).count() or M.get_setting(db, "ppe_seeded"):
        return 0
    import os
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ppe_seed.json")
    if not os.path.exists(p):
        return 0
    data = json.load(open(p))
    emps = {_key(e.emp_no): e for e in db.query(models.Employee).all()}
    n = 0
    for r in data.get("issues", []):
        e = emps.get(_key(r["id"]))
        db.add(models.PpeIssue(employee_id=e.id if e else None, emp_no=e.emp_no if e else r["id"],
                               name=(e.name if e else r["name"])[:120], issued_on=date.fromisoformat(r["d"]),
                               item=r["item"][:40], size=str(r.get("size") or "")[:20], qty=int(r.get("qty") or 1),
                               condition=(r.get("cond") or "Issued")[:20], site=(r.get("site") or "")[:40],
                               remarks=(r.get("rem") or "")[:300]))
        n += 1
    since = date.fromisoformat(data["stock_from"]) if data.get("stock_from") else None
    for item, s in (data.get("stock") or {}).items():
        db.add(models.PpeStock(item=item, counted=s.get("start"), counted_on=since if s.get("start") is not None else None,
                               reorder=int(s.get("reorder") or 5)))
    M.put_setting(db, "ppe_seeded", "1")
    db.commit()
    return n


def _given(rows):
    return [r for r in rows if (r.condition or "Issued") not in NOT_GIVEN]


def status(rows, item, lim, on_date, qty=1):
    """Can he have `qty` of `item` on `on_date`? rows = his given issues."""
    n, months = lim
    start = _months_ago(on_date, months)
    win = sorted([r for r in rows if r.item == item and start < r.issued_on <= on_date], key=lambda r: r.issued_on)
    used = sum(r.qty or 1 for r in win)
    last = max((r for r in rows if r.item == item and r.issued_on <= on_date), key=lambda r: (r.issued_on, r.id), default=None)
    too_soon = used + qty > n
    nxt = None
    if too_soon:
        # the day enough of the window has aged out for this one to fit
        need, freed = used + qty - n, 0
        for r in win:
            freed += r.qty or 1
            if freed >= need:
                nxt = _months_after(r.issued_on, months)
                break
    elif used:
        # the next one after this would be due when the oldest ages out
        nxt = _months_after(win[0].issued_on, months) if used + qty >= n else None
    return {"item": item, "used": used, "limit": n, "months": months, "too_soon": too_soon,
            "last": last.issued_on.isoformat() if last else "", "last_size": (last.size or "") if last else "",
            "last_qty": (last.qty or 1) if last else 0, "days_since": (on_date - last.issued_on).days if last else None,
            "next_due": nxt.isoformat() if nxt else ""}


def _people(db):
    """Workers on the register: active labour, and anyone who has been given PPE."""
    emps = db.query(models.Employee).all()
    by_id = {e.id: e for e in emps}
    issues = db.query(models.PpeIssue).order_by(models.PpeIssue.issued_on, models.PpeIssue.id).all()
    people = {}
    for e in emps:
        if not e.staff and e.active and not (e.terminated_on and e.terminated_on <= M._dubai_today()):
            people[_key(e.emp_no)] = {"key": _key(e.emp_no), "emp_id": e.id, "no": e.emp_no, "name": e.name, "trade": e.trade or "",
                                      "active": True, "rows": []}
    for r in issues:
        k = _key(by_id[r.employee_id].emp_no) if r.employee_id in by_id else _key(r.emp_no)
        if k not in people:
            e = by_id.get(r.employee_id)
            people[k] = {"key": k, "emp_id": r.employee_id, "no": e.emp_no if e else r.emp_no, "name": e.name if e else r.name,
                         "trade": (e.trade or "") if e else "", "active": bool(e and e.active and not e.terminated_on), "rows": []}
        people[k]["rows"].append(r)
    return people, issues


def _issue_dict(r, users):
    return {"id": r.id, "emp_id": r.employee_id, "no": r.emp_no, "name": r.name, "date": r.issued_on.isoformat(),
            "item": r.item, "size": r.size or "", "qty": r.qty or 1, "condition": r.condition or "Issued", "site": r.site or "",
            "instructed_by": r.instructed_by or "", "remarks": r.remarks or "", "early": r.early_reason or "",
            "by": users.get(r.created_by, "")}


def dashboard(db):
    seed(db)
    today = M._dubai_today()
    lim = limits(db)
    people, issues = _people(db)
    items = list(lim.keys())
    workers = []
    for p in people.values():
        given = _given(p["rows"])
        cells = {}
        for it in items:
            st = status(given, it, lim[it], today, qty=0)
            st["state"] = "none" if not st["last"] else ("full" if st["used"] >= st["limit"] else ("some" if st["used"] else "ok"))
            st["count_all"] = sum(r.qty or 1 for r in given if r.item == it)
            cells[it] = st
        pending = [r for r in p["rows"] if (r.condition or "") in NOT_GIVEN]
        early = sum(1 for r in given if r.early_reason and r.issued_on > today - timedelta(days=180))
        workers.append({"key": p["key"], "emp_id": p["emp_id"], "no": p["no"], "name": p["name"], "trade": p["trade"],
                        "active": p["active"], "cells": cells, "total_6m": sum(c["used"] for c in cells.values() if c["months"] == 6),
                        "total_all": sum(r.qty or 1 for r in given), "early": early, "pending": len(pending)})
    workers.sort(key=lambda w: _key(w["no"]))
    users = {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}
    given_all = _given(issues)
    month0 = today.replace(day=1)
    six = _months_ago(today, 6)
    by_item_6m = {it: sum(r.qty or 1 for r in given_all if r.item == it and r.issued_on > six) for it in items}
    # quick repeats: the same item to the same man within 30 days, in the last 6 months
    quick = []
    for p in people.values():
        g = sorted(_given(p["rows"]), key=lambda r: (r.item, r.issued_on))
        for a, b in zip(g, g[1:]):
            if a.item == b.item and (b.issued_on - a.issued_on).days <= 30 and b.issued_on > six:
                quick.append({"no": p["no"], "name": p["name"], "item": b.item, "first": a.issued_on.isoformat(),
                              "again": b.issued_on.isoformat(), "days": (b.issued_on - a.issued_on).days, "reason": b.early_reason or b.remarks or ""})
    quick.sort(key=lambda q: q["again"], reverse=True)
    stock = []
    for s in db.query(models.PpeStock).all():
        since = sum(r.qty or 1 for r in given_all if r.item == s.item and s.counted_on and r.issued_on >= s.counted_on)
        avail = (s.counted - since) if s.counted is not None else None
        stock.append({"item": s.item, "counted": s.counted, "counted_on": s.counted_on.isoformat() if s.counted_on else "",
                      "issued_since": since, "available": avail, "reorder": s.reorder or 0,
                      "low": avail is not None and avail <= (s.reorder or 0)})
    for it in items:
        if not any(x["item"] == it for x in stock):
            stock.append({"item": it, "counted": None, "counted_on": "", "issued_since": 0, "available": None, "reorder": 5, "low": False})
    stock.sort(key=lambda x: items.index(x["item"]) if x["item"] in items else 99)
    return {"today": today.isoformat(), "items": items, "limits": {k: list(v) for k, v in lim.items()}, "sizes": SIZES,
            "workers": workers,
            "recent": [_issue_dict(r, users) for r in sorted(issues, key=lambda r: (r.issued_on, r.id), reverse=True)[:80]],
            "tiles": {"month": sum(r.qty or 1 for r in given_all if r.issued_on >= month0),
                      "six": sum(by_item_6m.values()), "quick": len(quick),
                      "pending": sum(1 for r in issues if (r.condition or "") in NOT_GIVEN),
                      "low": sum(1 for s in stock if s["low"])},
            "by_item_6m": by_item_6m, "quick": quick[:60], "stock": stock}


@router.get("/store/ppe")
def get_ppe(db: Session = Depends(get_db), user: models.User = VIEW):
    d = dashboard(db)
    d["may_edit"] = may_edit(user)
    return d


def _rows_for(db, emp_id, emp_no):
    q = db.query(models.PpeIssue)
    if emp_id:
        e = db.get(models.Employee, emp_id)
        keys = {_key(e.emp_no)} if e else set()
        rows = [r for r in q.all() if r.employee_id == emp_id or (keys and _key(r.emp_no) in keys)]
    else:
        rows = [r for r in q.all() if _key(r.emp_no) == _key(emp_no)]
    return rows


@router.get("/store/ppe/people")
def people(db: Session = Depends(get_db), user: models.User = EDIT):
    """Who can be given PPE: everyone still working, labour first."""
    today = M._dubai_today()
    es = [e for e in db.query(models.Employee).all() if e.active and not (e.terminated_on and e.terminated_on <= today)]
    es.sort(key=lambda e: (bool(e.staff), _key(e.emp_no)))
    return {"people": [{"id": e.id, "no": e.emp_no, "name": e.name, "trade": e.trade or "", "staff": bool(e.staff)} for e in es]}


@router.get("/store/ppe/check")
def check(employee_id: int = 0, emp_no: str = "", item: str = "", qty: int = 1, on: str = "", exclude: int = 0,
          db: Session = Depends(get_db), user: models.User = VIEW):
    lim = limits(db)
    if item not in lim:
        return {"too_soon": False}
    d = M._as_date(on) or M._dubai_today()
    rows = [r for r in _given(_rows_for(db, employee_id, emp_no)) if r.id != exclude]
    return status(rows, item, lim[item], d, qty=max(1, int(qty or 1)))


def _clean(db, p):
    lim = limits(db)
    e = db.get(models.Employee, int(p.get("employee_id") or 0)) if p.get("employee_id") else None
    if not e:
        raise HTTPException(status_code=400, detail="Pick the worker from the staff list.")
    item = str(p.get("item") or "").strip()
    if item not in lim:
        raise HTTPException(status_code=400, detail="Pick the item (Coverall, Safety Shoes...).")
    d = M._as_date(p.get("date")) or M._dubai_today()
    if d > M._dubai_today():
        raise HTTPException(status_code=400, detail="The date is in the future.")
    try:
        qty = int(p.get("qty") or 1)
    except ValueError:
        qty = 0
    if not 1 <= qty <= 10:
        raise HTTPException(status_code=400, detail="How many? 1 to 10.")
    cond = str(p.get("condition") or "Issued")
    if cond not in ("Issued", "Replacement", "Eligible"):
        cond = "Issued"
    return e, {"employee_id": e.id, "emp_no": e.emp_no, "name": e.name, "issued_on": d, "item": item,
               "size": M.tidy_text(p.get("size"))[:20], "qty": qty, "condition": cond,
               "site": M.tidy_text(p.get("site"))[:40], "instructed_by": M.tidy_text(p.get("instructed_by"))[:80],
               "remarks": M.tidy_text(p.get("remarks"))[:300], "early_reason": M.tidy_text(p.get("early_reason"))[:200]}


def _guard(db, e, f, exclude=0):
    """Too soon: only with a reason."""
    if f["condition"] in NOT_GIVEN:
        return None
    lim = limits(db)
    rows = [r for r in _given(_rows_for(db, e.id, e.emp_no)) if r.id != exclude]
    st = status(rows, f["item"], lim[f["item"]], f["issued_on"], qty=f["qty"])
    if st["too_soon"] and not f["early_reason"]:
        last = date.fromisoformat(st["last"]).strftime("%d %b %Y") if st["last"] else ""
        raise HTTPException(status_code=400, detail=(
            f"Too soon: {e.name} was given {f['item']} on {last} ({st['days_since']} days ago). "
            f"Limit {st['limit']} in {st['months']} months"
            + (f" - next due {date.fromisoformat(st['next_due']).strftime('%d %b %Y')}" if st["next_due"] else "")
            + ". Write why it is given now."))
    if not st["too_soon"]:
        f["early_reason"] = ""
    return st


@router.post("/store/ppe")
def add(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = EDIT):
    e, f = _clean(db, payload)
    st = _guard(db, e, f)
    r = models.PpeIssue(**f, created_by=user.id)
    db.add(r); db.commit()
    M.log_action(db, user.id, "ppe", f"{e.emp_no} {e.name}: {f['qty']} x {f['item']} {f['size']} on {f['issued_on']}"
                 + (f" - EARLY: {f['early_reason']}" if f["early_reason"] else ""))
    return {"ok": True, "id": r.id, "early": bool(f["early_reason"])}


@router.put("/store/ppe/{iid}")
def edit(iid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = EDIT):
    r = db.get(models.PpeIssue, iid)
    if not r:
        raise HTTPException(status_code=404, detail="That entry is not on the register.")
    e, f = _clean(db, payload)
    _guard(db, e, f, exclude=iid)
    was = f"{r.qty} x {r.item} {r.issued_on}"
    for k, v in f.items():
        setattr(r, k, v)
    db.commit()
    M.log_action(db, user.id, "ppe", f"#{iid} {e.emp_no}: {was} -> {r.qty} x {r.item} {r.issued_on}")
    return {"ok": True}


@router.delete("/store/ppe/{iid}")
def delete(iid: int, db: Session = Depends(get_db), user: models.User = EDIT):
    r = db.get(models.PpeIssue, iid)
    if not r:
        raise HTTPException(status_code=404, detail="That entry is not on the register.")
    M.log_action(db, user.id, "ppe_removed", f"#{iid} {r.emp_no} {r.name}: {r.qty} x {r.item} on {r.issued_on} removed")
    db.delete(r); db.commit()
    return {"ok": True}


@router.post("/store/ppe/stock")
def set_stock(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = EDIT):
    item = str(payload.get("item") or "").strip()
    if item not in limits(db):
        raise HTTPException(status_code=400, detail="Pick the item.")
    try:
        counted = int(payload.get("counted"))
        reorder = int(payload.get("reorder") if payload.get("reorder") not in (None, "") else 5)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Type the number counted in the store.")
    if counted < 0 or reorder < 0:
        raise HTTPException(status_code=400, detail="Numbers cannot be below zero.")
    s = db.query(models.PpeStock).filter(models.PpeStock.item == item).first() or models.PpeStock(item=item)
    s.counted, s.counted_on, s.reorder = counted, M._dubai_today(), reorder
    db.add(s); db.commit()
    M.log_action(db, user.id, "ppe", f"stock counted: {item} {counted} (reorder at {reorder})")
    return {"ok": True}


@router.get("/store/ppe/history")
def history(employee_id: int = 0, emp_no: str = "", db: Session = Depends(get_db), user: models.User = VIEW):
    users = {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}
    rows = sorted(_rows_for(db, employee_id, emp_no), key=lambda r: (r.issued_on, r.id), reverse=True)
    return {"rows": [_issue_dict(r, users) for r in rows]}


# ---- exports ------------------------------------------------------------------

def _fmt(iso):
    return date.fromisoformat(iso).strftime("%d-%b-%y") if iso else ""


@router.get("/export/reports/ppe")
def export(token: str, format: str = "excel", view: str = "grid", db: Session = Depends(get_db)):
    u = auth.get_download_user_from_token(token, db)
    perms = M.effective_permissions(u)
    if (u.role or "") != "admin" and "reports" not in perms and RIGHT not in perms:
        raise HTTPException(status_code=403, detail="Labour reports only.")
    d = dashboard(db)
    if view == "log":
        title = "PPE Issue Register"
        rows = [{"Date": _fmt(r["date"]), "Employee ID": r["no"], "Name": r["name"], "Item": r["item"], "Size": r["size"],
                 "Qty": r["qty"], "Status": r["condition"], "Instructed by": r["instructed_by"],
                 "Remarks": (("EARLY - " + r["early"] + ". ") if r["early"] else "") + r["remarks"]}
                for r in sorted([*dashboard_all(db)], key=lambda r: (r["date"], r["no"]), reverse=True)]
    else:
        title = "PPE by Worker"
        rows = []
        for w in d["workers"]:
            row = {"Employee ID": w["no"], "Name": w["name"]}
            for it in d["items"]:
                c = w["cells"][it]
                row[it] = (f"{_fmt(c['last'])} ({c['used']}/{c['limit']})" if c["last"] else "-") + (" !" if c["state"] == "full" else "")
            row["Early (6m)"] = w["early"] or ""
            row["Total"] = w["total_all"]
            rows.append(row)
    t = d["tiles"]
    sub = (f"Last 6 months: {t['six']} items | this month: {t['month']} | quick repeats (30 days): {t['quick']}"
           f" | As at {M._dubai_today():%d %b %Y}" + ("" if view == "log" else " | (used/limit in the item's period, ! = at the limit)"))
    if format == "view":
        url = f"/export/reports/ppe?view={view}&token={quote(auth.create_view_token(u.username), safe='')}"
        return M._preview_page(title, sub, rows, url, url, money_cols=[])
    name = f"{title.replace(' ', '_')}_{M._dubai_today():%d.%m.%Y}"
    if format == "pdf":
        return StreamingResponse(export_web.build_store_report_pdf(title, rows, sub, money_cols=[], orientation="landscape"),
                                 media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})
    return StreamingResponse(export_web.build_store_report_excel(title, rows, sub, money_cols=[]),
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename={name}.xlsx"})


def dashboard_all(db):
    users = {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}
    return [_issue_dict(r, users) for r in db.query(models.PpeIssue).all()]

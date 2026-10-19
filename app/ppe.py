"""PPE register (Reports > Labour > PPE): coveralls, safety shoes, helmets
and the like handed to workers - kept so they are not asked for again and
again.

No limits and no due dates - it is a tracker: when was each item last
given to this man, and how long ago. Things given again within 30 days
stand out so a repeat request is seen at once.
"Eligible" lines (approved, not handed over yet) do not count until given.

Stock is kept at two places, the Store and the Office. Each place: last
count + deliveries received since - given from there since.
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

ITEMS = ["Coverall", "Coverall-Brown", "Safety Shoes", "Safety Vest", "Helmet", "Jacket", "Driver T-Shirt", "Engineer Vest"]
RECENT_DAYS = 30
PLACES = ("Store", "Office")       # two stocks: the site store and the office
SIZES = {"Coverall": ["S", "M", "L", "XL", "XXL", "XXXL"], "Coverall-Brown": ["S", "M", "L", "XL", "XXL", "XXXL"], "Safety Shoes": [str(n) for n in range(38, 47)],
         "Helmet": ["Blue", "White", "Yellow", "Red", "Green"], "Safety Vest": ["M", "L", "XL", "XXL"],
         "Jacket": ["M", "L", "XL", "XXL"], "Driver T-Shirt": ["S", "M", "L", "XL", "XXL"], "Engineer Vest": ["M", "L", "XL", "XXL"]}
NOT_GIVEN = ("Eligible",)
# Kept size by size: safety shoes and the uniforms (the helmet goes by colour, not size).
SIZED = ["Safety Shoes", "Coverall", "Coverall-Brown", "Safety Vest", "Jacket", "Driver T-Shirt", "Engineer Vest"]


def _sz(item, v):
    """A size as written on an issue ('xl ', '42.0') -> the size in the list, or '' if it is not one."""
    t = str(v or "").strip().upper().replace(" ", "")
    if t.endswith(".0"):
        t = t[:-2]
    t = {"2XL": "XXL", "3XL": "XXXL", "SMALL": "S", "MEDIUM": "M", "LARGE": "L"}.get(t, t)
    return t if t in SIZES.get(item, []) else ""


def _key(no):
    return "".join(ch for ch in str(no or "").upper() if ch.isalnum())


def may_edit(user):
    return (user.role or "") == "admin" or RIGHT in M.effective_permissions(user)


def _editor(user: models.User = Depends(auth.get_current_user)):
    if not may_edit(user):
        raise HTTPException(status_code=403, detail="Only the PRO, the store keeper and accounts record PPE.")
    return user


EDIT = Depends(_editor)


def items(db=None):
    return list(ITEMS)


def _months_ago(d, months):
    y, m = d.year, d.month - months
    while m <= 0:
        m += 12; y -= 1
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
        if s.get("start") is not None and since:
            db.add(models.PpeStockMove(item=item, location="Store", kind="count", qty=int(s["start"]), moved_on=since, after_issue=0,
                                       note="from the Excel register"))
    M.put_setting(db, "ppe_moves_migrated", "1")
    M.put_setting(db, "ppe_seeded", "1")
    db.commit()
    return n


def _src(r):
    return r.source if r.source in PLACES else "Store"


def migrate_stock(db):
    """Counts saved before there were two places become Store counts - once."""
    if M.get_setting(db, "ppe_moves_migrated"):
        return
    for st in db.query(models.PpeStock).all():
        if st.counted is not None and st.counted_on:
            db.add(models.PpeStockMove(item=st.item, location="Store", kind="count", qty=st.counted, moved_on=st.counted_on, after_issue=0))
    M.put_setting(db, "ppe_moves_migrated", "1")
    db.commit()


def stock(db, issues=None):
    """In hand at each place, per item."""
    issues = issues if issues is not None else db.query(models.PpeIssue).all()
    given = _given(issues)
    moves = [m for m in db.query(models.PpeStockMove).all() if not m.size]
    reorder = {x.item: (x.reorder if x.reorder is not None else 5) for x in db.query(models.PpeStock).all()}
    out = []
    for it in ITEMS:
        row = {"item": it, "reorder": reorder.get(it, 5)}
        total, known = 0, False
        for pl in PLACES:
            mv = [m for m in moves if m.item == it and m.location == pl]
            counts = [m for m in mv if m.kind == "count"]
            last = max(counts, key=lambda m: (m.moved_on, m.id), default=None)
            if last:
                base, d0, mid, after = last.qty, last.moved_on, last.id, last.after_issue or 0
            else:
                rec = [m for m in mv if m.kind == "received"]
                if not rec:
                    row[pl] = {"in_hand": None, "counted": None, "counted_on": "", "received": 0, "given": 0}
                    continue
                first = min(rec, key=lambda m: (m.moved_on, m.id))      # none in hand before the first delivery recorded
                base, d0, mid, after = 0, first.moved_on, first.id - 1, 0
            rec = sum(m.qty for m in mv if m.kind == "received" and m.moved_on >= d0 and m.id > mid)
            out_ = sum(r.qty or 1 for r in given if r.item == it and _src(r) == pl and r.issued_on >= d0 and r.id > after)
            n = base + rec - out_
            row[pl] = {"in_hand": n, "counted": last.qty if last else None, "counted_on": last.moved_on.isoformat() if last else "",
                       "received": rec, "given": out_, "since": d0.isoformat()}
            total += n; known = True
        row["total"] = total if known else None
        row["low"] = known and total <= row["reorder"]
        out.append(row)
    return out


def sized_stock(db, issues=None):
    """In hand size by size at each place, for safety shoes and uniforms:
    last size count + size received since - given in that size since."""
    issues = issues if issues is not None else db.query(models.PpeIssue).all()
    given = _given(issues)
    moves = [m for m in db.query(models.PpeStockMove).all() if m.size]
    out = []
    for it in SIZED:
        mine = [m for m in moves if m.item == it]
        row = {"item": it, "sizes": SIZES[it], "cells": {}, "tracked": bool(mine), "no_size": 0}
        for sz in SIZES[it]:
            cell, total, known = {}, 0, False
            for pl in PLACES:
                mv = [m for m in mine if m.location == pl and m.size == sz]
                counts = [m for m in mv if m.kind == "count"]
                last = max(counts, key=lambda m: (m.moved_on, m.id), default=None)
                if last:
                    base, d0, mid, after = last.qty, last.moved_on, last.id, last.after_issue or 0
                else:
                    rec = [m for m in mv if m.kind == "received"]
                    if not rec:
                        cell[pl] = None
                        continue
                    first = min(rec, key=lambda m: (m.moved_on, m.id))
                    base, d0, mid, after = 0, first.moved_on, first.id - 1, 0
                rec = sum(m.qty for m in mv if m.kind == "received" and m.moved_on >= d0 and m.id > mid)
                out_ = sum(r.qty or 1 for r in given if r.item == it and _src(r) == pl and _sz(it, r.size) == sz
                           and r.issued_on >= d0 and r.id > after)
                cell[pl] = base + rec - out_
                total += cell[pl]; known = True
            cell["total"] = total if known else None
            row["cells"][sz] = cell
        if mine:   # given since sizes were first kept, with no size (or an odd one) written down
            d0 = min(m.moved_on for m in mine)
            row["no_size"] = sum(r.qty or 1 for r in given if r.item == it and r.issued_on >= d0 and not _sz(it, r.size))
        out.append(row)
    return out


def _sizes_in(item, payload):
    """{size: n} from a count or delivery entered size by size (blank = 0); None when not given that way."""
    raw = payload.get("sizes")
    if not raw or item not in SIZED:
        return None
    out = {}
    for k, v in dict(raw).items():
        sz = _sz(item, k)
        if not sz:
            raise HTTPException(status_code=400, detail=f"{k} is not a size of {item}.")
        try:
            n = int(v) if str(v).strip() != "" else 0
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"Size {k}: type a whole number.")
        if n < 0:
            raise HTTPException(status_code=400, detail="Numbers cannot be below zero.")
        out[sz] = n
    return out


def _add_sized(db, item, pl, kind, sizes, moved_on, after_issue, note, user_id):
    """The whole-item entry plus one per size, tied by batch."""
    head = models.PpeStockMove(item=item, location=pl, kind=kind, qty=sum(sizes.values()), moved_on=moved_on,
                               after_issue=after_issue, note=note, size="", created_by=user_id)
    db.add(head); db.flush(); head.batch = head.id
    for sz, n in sizes.items():
        if kind == "received" and not n:
            continue
        db.add(models.PpeStockMove(item=item, location=pl, kind=kind, qty=n, moved_on=moved_on, after_issue=after_issue,
                                   note=note, size=sz, batch=head.id, created_by=user_id))
    return head


def _given(rows):
    return [r for r in rows if (r.condition or "Issued") not in NOT_GIVEN]


def status(rows, item, on_date):
    """When was `item` last given to him (rows = his given issues), how long ago, how many in all."""
    mine = [r for r in rows if r.item == item and r.issued_on <= on_date]
    last = max(mine, key=lambda r: (r.issued_on, r.id), default=None)
    days = (on_date - last.issued_on).days if last else None
    six = _months_ago(on_date, 6)
    return {"item": item, "last": last.issued_on.isoformat() if last else "", "last_size": (last.size or "") if last else "",
            "last_qty": (last.qty or 1) if last else 0, "days_since": days,
            "count_6m": sum(r.qty or 1 for r in mine if r.issued_on > six), "count_all": sum(r.qty or 1 for r in mine),
            "recent": days is not None and days <= RECENT_DAYS,
            "state": "none" if not last else ("recent" if days <= RECENT_DAYS else ("mid" if days <= 90 else "old"))}


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
            "instructed_by": r.instructed_by or "", "remarks": r.remarks or "", "source": _src(r),
            "by": users.get(r.created_by, "")}


def dashboard(db):
    seed(db)
    migrate_stock(db)
    today = M._dubai_today()
    people, issues = _people(db)
    items = ITEMS
    workers = []
    for p in people.values():
        given = _given(p["rows"])
        cells = {}
        for it in items:
            cells[it] = status(given, it, today)
        pending = [r for r in p["rows"] if (r.condition or "") in NOT_GIVEN]
        workers.append({"key": p["key"], "emp_id": p["emp_id"], "no": p["no"], "name": p["name"], "trade": p["trade"],
                        "active": p["active"], "cells": cells, "total_6m": sum(c["count_6m"] for c in cells.values()),
                        "total_all": sum(r.qty or 1 for r in given), "pending": len(pending)})
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
                              "again": b.issued_on.isoformat(), "days": (b.issued_on - a.issued_on).days, "reason": b.remarks or ""})
    quick.sort(key=lambda q: q["again"], reverse=True)
    stk = stock(db, issues)
    return {"today": today.isoformat(), "items": items, "sizes": SIZES, "recent_days": RECENT_DAYS, "places": list(PLACES),
            "sized_items": SIZED, "by_size": sized_stock(db, issues),
            "workers": workers,
            "recent": [_issue_dict(r, users) for r in sorted(issues, key=lambda r: (r.issued_on, r.id), reverse=True)[:80]],
            "tiles": {"month": sum(r.qty or 1 for r in given_all if r.issued_on >= month0),
                      "six": sum(by_item_6m.values()), "quick": len(quick),
                      "pending": sum(1 for r in issues if (r.condition or "") in NOT_GIVEN),
                      "low": sum(1 for x in stk if x["low"])},
            "by_item_6m": by_item_6m, "quick": quick[:60], "stock": stk}


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
def check(employee_id: int = 0, emp_no: str = "", item: str = "", on: str = "", exclude: int = 0,
          db: Session = Depends(get_db), user: models.User = VIEW):
    """For the Give PPE box: when he last had this item - shown, never blocks."""
    if item not in ITEMS:
        return {"last": ""}
    d = M._as_date(on) or M._dubai_today()
    rows = [r for r in _given(_rows_for(db, employee_id, emp_no)) if r.id != exclude]
    return status(rows, item, d)


def _clean(db, p):
    e = db.get(models.Employee, int(p.get("employee_id") or 0)) if p.get("employee_id") else None
    if not e:
        raise HTTPException(status_code=400, detail="Pick the worker from the staff list.")
    item = str(p.get("item") or "").strip()
    if item not in ITEMS:
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
    src = str(p.get("source") or "Store")
    if src not in PLACES:
        raise HTTPException(status_code=400, detail="Given from the Store or the Office?")
    cond = str(p.get("condition") or "Issued")
    if cond not in ("Issued", "Replacement", "Eligible"):
        cond = "Issued"
    return e, {"employee_id": e.id, "emp_no": e.emp_no, "name": e.name, "issued_on": d, "item": item,
               "size": M.tidy_text(p.get("size"))[:20], "qty": qty, "condition": cond,
               "site": M.tidy_text(p.get("site"))[:40], "instructed_by": M.tidy_text(p.get("instructed_by"))[:80],
               "remarks": M.tidy_text(p.get("remarks"))[:300], "source": src}


@router.post("/store/ppe")
def add(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = EDIT):
    e, f = _clean(db, payload)
    r = models.PpeIssue(**f, created_by=user.id)
    db.add(r); db.commit()
    M.log_action(db, user.id, "ppe", f"{e.emp_no} {e.name}: {f['qty']} x {f['item']} {f['size']} on {f['issued_on']} from the {f['source']}")
    return {"ok": True, "id": r.id}


@router.put("/store/ppe/{iid}")
def edit(iid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = EDIT):
    r = db.get(models.PpeIssue, iid)
    if not r:
        raise HTTPException(status_code=404, detail="That entry is not on the register.")
    e, f = _clean(db, payload)
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


def _place(p):
    pl = str(p.get("location") or "")
    if pl not in PLACES:
        raise HTTPException(status_code=400, detail="Store or Office?")
    return pl


@router.post("/store/ppe/stock")
def set_stock(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = EDIT):
    """A count at one place: what is there now. Items given after this come off it."""
    item = str(payload.get("item") or "").strip()
    if item not in ITEMS:
        raise HTTPException(status_code=400, detail="Pick the item.")
    pl = _place(payload)
    sizes = _sizes_in(item, payload)
    try:
        counted = sum(sizes.values()) if sizes is not None else int(payload.get("counted"))
        reorder = int(payload.get("reorder")) if payload.get("reorder") not in (None, "") else None
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Type the number counted.")
    if counted < 0 or (reorder is not None and reorder < 0):
        raise HTTPException(status_code=400, detail="Numbers cannot be below zero.")
    from sqlalchemy import func as F
    last_issue = db.query(F.max(models.PpeIssue.id)).scalar() or 0
    if sizes is not None:
        _add_sized(db, item, pl, "count", sizes, M._dubai_today(), last_issue, "", user.id)
    else:
        db.add(models.PpeStockMove(item=item, location=pl, kind="count", qty=counted, moved_on=M._dubai_today(), after_issue=last_issue,
                                   created_by=user.id))
    if reorder is not None:
        st = db.query(models.PpeStock).filter(models.PpeStock.item == item).first() or models.PpeStock(item=item)
        st.reorder = reorder
        db.add(st)
    db.commit()
    M.log_action(db, user.id, "ppe", f"stock counted: {item} at the {pl}: {counted}"
                 + (" (" + ", ".join(f"{k}: {v}" for k, v in sizes.items()) + ")" if sizes else ""))
    return {"ok": True}


@router.post("/store/ppe/received")
def received(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = EDIT):
    """New stock delivered to the Store or the Office."""
    item = str(payload.get("item") or "").strip()
    if item not in ITEMS:
        raise HTTPException(status_code=400, detail="Pick the item.")
    pl = _place(payload)
    sizes = _sizes_in(item, payload)
    try:
        qty = sum(sizes.values()) if sizes is not None else int(payload.get("qty"))
    except (TypeError, ValueError):
        qty = 0
    if not 1 <= qty <= 2000:
        raise HTTPException(status_code=400, detail="How many were received?")
    d = M._as_date(payload.get("date")) or M._dubai_today()
    if d > M._dubai_today():
        raise HTTPException(status_code=400, detail="The date is in the future.")
    note = M.tidy_text(payload.get("note"))[:120]
    if sizes is not None:
        m = _add_sized(db, item, pl, "received", sizes, d, 0, note, user.id)
    else:
        m = models.PpeStockMove(item=item, location=pl, kind="received", qty=qty, moved_on=d, note=note, created_by=user.id)
        db.add(m)
    db.commit()
    M.log_action(db, user.id, "ppe", f"stock received: {qty} x {item} at the {pl} on {d}"
                 + (" (" + ", ".join(f"{k}: {v}" for k, v in sizes.items() if v) + ")" if sizes else ""))
    return {"ok": True, "id": m.id}


@router.get("/store/ppe/stock/history")
def stock_history(item: str = "", db: Session = Depends(get_db), user: models.User = VIEW):
    users = {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}
    allmv = db.query(models.PpeStockMove).filter(models.PpeStockMove.item == item).all()
    mv = [m for m in allmv if not m.size]
    parts = {}
    for m in allmv:
        if m.size and m.batch:
            parts.setdefault(m.batch, {})[m.size] = m.qty
    gv = [r for r in _given(db.query(models.PpeIssue).filter(models.PpeIssue.item == item).all())]
    order = {sz: i for i, sz in enumerate(SIZES.get(item, []))}
    rows = [{"id": m.id, "date": m.moved_on.isoformat(), "place": m.location, "kind": m.kind, "qty": m.qty, "note": m.note or "",
             "sizes": dict(sorted(parts.get(m.batch, {}).items(), key=lambda kv: order.get(kv[0], 99))) if m.batch else {},
             "by": users.get(m.created_by, "")} for m in mv]
    rows.sort(key=lambda r: (r["date"], r["id"]), reverse=True)
    by_place = {pl: sum(r.qty or 1 for r in gv if _src(r) == pl) for pl in PLACES}
    return {"item": item, "moves": rows[:100], "given_all": by_place}


@router.delete("/store/ppe/stock/{mid}")
def delete_move(mid: int, db: Session = Depends(get_db), user: models.User = EDIT):
    m = db.get(models.PpeStockMove, mid)
    if not m:
        raise HTTPException(status_code=404, detail="That stock entry is not there.")
    M.log_action(db, user.id, "ppe_removed", f"stock {m.kind} removed: {m.qty} x {m.item} at the {m.location} on {m.moved_on}")
    if m.batch:   # the sizes go with it
        for x in db.query(models.PpeStockMove).filter(models.PpeStockMove.batch == m.batch).all():
            db.delete(x)
    else:
        db.delete(m)
    db.commit()
    return {"ok": True}


@router.get("/store/ppe/history")
def history(employee_id: int = 0, emp_no: str = "", db: Session = Depends(get_db), user: models.User = VIEW):
    users = {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}
    rows = sorted(_rows_for(db, employee_id, emp_no), key=lambda r: (r.issued_on, r.id), reverse=True)
    return {"rows": [_issue_dict(r, users) for r in rows]}


# ---- exports ------------------------------------------------------------------

def _ago(days):
    if days is None:
        return ""
    if days == 0:
        return "today"
    if days < 60:
        return f"{days} day{'s' if days != 1 else ''} ago"
    m = round(days / 30.44)
    if m < 12:
        return f"{m} months ago"
    y, m = divmod(m, 12)
    return f"{y} yr" + (f" {m} mo" if m else "") + " ago"


def _fmt(iso):
    return date.fromisoformat(iso).strftime("%d-%b-%y") if iso else ""


@router.get("/export/reports/ppe")
def export(token: str, format: str = "excel", view: str = "grid", db: Session = Depends(get_db)):
    u = auth.get_download_user_from_token(token, db)
    perms = M.effective_permissions(u)
    if (u.role or "") != "admin" and "reports" not in perms and RIGHT not in perms:
        raise HTTPException(status_code=403, detail="Labour reports only.")
    d = dashboard(db)
    if view == "sizes":
        title = "PPE Stock by Size"
        rows = []
        for x in d["by_size"]:
            if not x["tracked"]:
                continue
            for sz in x["sizes"]:
                c = x["cells"][sz]
                if c["total"] is None:
                    continue
                f = lambda v: "-" if v is None else v
                rows.append({"Item": x["item"], "Size": sz, "Store": f(c.get("Store")), "Office": f(c.get("Office")), "Total": c["total"]})
            if x["no_size"]:
                rows.append({"Item": x["item"], "Size": "Given, size not noted", "Store": "", "Office": "", "Total": -x["no_size"]})
    elif view == "log":
        title = "PPE Issue Register"
        rows = [{"Date": _fmt(r["date"]), "Employee ID": r["no"], "Name": r["name"], "Item": r["item"], "Size": r["size"],
                 "Qty": r["qty"], "From": r["source"], "Status": r["condition"], "Instructed by": r["instructed_by"],
                 "Remarks": r["remarks"]}
                for r in sorted([*dashboard_all(db)], key=lambda r: (r["date"], r["no"]), reverse=True)]
    else:
        title = "PPE by Worker"
        rows = []
        for w in d["workers"]:
            row = {"Employee ID": w["no"], "Name": w["name"]}
            for it in d["items"]:
                c = w["cells"][it]
                row[it] = f"{_fmt(c['last'])} ({_ago(c['days_since'])})" if c["last"] else "-"
            row["Total given"] = w["total_all"]
            rows.append(row)
    t = d["tiles"]
    sub = (f"Last 6 months: {t['six']} items | this month: {t['month']} | quick repeats (30 days): {t['quick']}"
           f" | As at {M._dubai_today():%d %b %Y}" + ("" if view in ("log", "sizes") else " | each item: last given (how long ago)"))
    if view == "sizes":
        sub = f"In hand size by size = last count + received - given from there | As at {M._dubai_today():%d %b %Y}"
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

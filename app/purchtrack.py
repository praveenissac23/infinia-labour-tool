"""The order tracker (2 Nov 2026): one screen for the purchaser, the store keeper and accounts.

Every open material request and LPO on one line, at the step it has reached:

    Requested -> Approved -> Ordered -> Arrived -> Bill checked -> Done

with who acts next, how late it is (past its needed-by / delivery date), what part delivery is still to come,
and the supplier's contact person and number. Nothing here keeps a status of its own: every step is read from
what the portal already holds (request lines, LPOs, deliveries, the bill check, Zoho) - so it can never disagree
with the other screens. Two small actions are new and change paperwork only, never stock or money:

    approve less   a request line approved for fewer than asked (the line then asks for that many - as a
                   part-closed LPO line already does); the reason is kept on the line
    close the rest an LPO's undelivered rest closed as not needed, without a delivery note (the same 'not
                   coming' record a delivery's 'rest not coming' tick makes - no stock moves)
"""
import json
from collections import defaultdict
from datetime import date, datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

import models
from database import get_db
import main as M
import purchasing as P

router = APIRouter()
EPS = 1e-9
STEPS = ["Requested", "Approved", "Ordered", "Arrived", "Bill checked", "Done"]
# Who acts is a department, never a person's name: people change and a department can have several (2 Nov 2026)
PEOPLE_DEFAULT = {"purchaser": "Purchase", "store": "Store", "accounts": "Accounts"}
# 'My turn' comes from the login's Access role (Settings > Access: Purchase Manager, Store Keeper, Chief Accountant...),
# never from its name - anyone given that role gets that department's turn
DEPT_WORDS = {"purchaser": ("purchas", "procure", "buyer"), "store": ("store",), "accounts": ("account", "finance")}
# who acts at each step
NEXT = {0: ("purchaser", "Approve"), 1: ("purchaser", "Raise LPO"), 2: ("store", "Book delivery"),
        3: ("purchaser", "Check bill"), 4: ("accounts", "Send to Zoho")}
SEE = M.require_any_screen("requests", "approvals", "store", "storekeeper", "accounts_zoho")


def people(db):
    return dict(PEOPLE_DEFAULT)


def _qty(x):
    return f"{float(x or 0):,.3f}".rstrip("0").rstrip(".")


def _clean(v):
    v = " ".join(str(v or "").split())
    return "" if v in ("0", "-", ".") else v


def _what(names):
    names = [n for n in names if n]
    if not names:
        return ""
    return ", ".join(names[:3]) + (f" +{len(names) - 3} more" if len(names) > 3 else "")


def _late(due, today, stage, part):
    if not due or not (stage <= 2 or part):
        return 0
    d = (today - due).days
    return d if d > 0 else 0


def _closed_lpo(o, p, sup, book, mr_of_line, why):
    refs = sorted({mr_of_line[i].ref for i in (p.get("related") or []) if mr_of_line.get(i)})
    return {"key": f"lpo{o.id}", "kind": "lpo", "id": o.id, "ref": o.ref, "requests": refs,
            "site": book.sites.key(o) if book.sites.key(o) != "STORE" else "Store",
            "what": _what([l.description for l in o.lines]), "supplier": o.supplier_name or (sup.name if sup else ""),
            "contact": _clean(o.supplier_contact), "phone": _clean(o.supplier_phone), "stage": 5, "part": False,
            "to_come": "", "due": "", "late": 0, "role": "", "who": "", "action": "",
            "date": o.order_date.isoformat() if o.order_date else "", "created": o.created_at.isoformat() if o.created_at else "",
            "bill_checked": bool(o.bill_checked),
            "zoho": o.zoho_status or "", "rental": False, "result": why, "cancelled": True}


def _closed_mr(mr, lines, name, word):
    why = word + (f": {mr.office_remark}" if (mr.office_remark or "").strip() and mr.status in ("closed", "rejected") else "")
    return {"key": f"mr{mr.id}", "kind": "mr", "id": mr.id, "ref": mr.ref, "requests": [mr.ref],
            "site": "Store" if (mr.site or "").upper() == "STORE" else (mr.site or ""),
            "what": _what([name(l) for l in lines]), "supplier": "", "contact": "", "phone": "", "stage": 5, "part": False,
            "to_come": "", "due": "", "late": 0, "role": "", "who": "", "action": "",
            "date": mr.requested_on.isoformat() if mr.requested_on else "", "created": mr.created_at.isoformat() if mr.created_at else "",
            "requested_by": mr.requested_by or "",
            "result": why, "untouched": False,
            "lines": [{"id": l.id, "name": name(l), "qty": float(l.qty_requested or 0), "unit": l.unit or "",
                       "purpose": l.purpose or "", "status": l.status or "pending"} for l in lines]}


def build(db):
    today = M._dubai_today()
    book = P.Book(db)
    try:
        import zohosync
        zoho_from = zohosync._start(db)
    except Exception:
        zoho_from = date(2026, 10, 1)
    sups = {s.id: s for s in db.query(models.Supplier).all()}
    who = people(db)
    try:
        freed = P.freed_lines(db)
    except Exception as e:                       # never lose the screen over this
        print("tracker freed lines:", e)
        freed = {}
    rows = []
    covered = set()
    mr_of_line = {l.id: book.req_by_id.get(l.request_id) for l in book.mr_lines}

    # ---- LPOs
    for o in book.orders:
        p = book.of(o)
        if not p:
            continue
        if p["status"] in ("cancelled", "superseded"):
            sup = sups.get(o.supplier_id)
            rows.append(_closed_lpo(o, p, sup, book, mr_of_line,
                                    f"Replaced by {o.superseded_by}" if p["status"] == "superseded"
                                    else "Cancelled" + (f": {o.cancel_reason}" if o.cancel_reason else "")))
            continue
        covered |= set(p["related"])
        lines = p["lines"]
        st = p["status"]
        part = st == "part"
        if st == "ordered":
            stage = 2
        elif part:
            stage = 3
        elif st == "closed" and not any(x["delivered"] > EPS for x in lines):
            stage = 5                            # nothing came and the rest was closed: nothing to bill
        elif not o.bill_checked:
            stage = 3
        elif (o.zoho_status or "") in ("sent", "changed", "skip") or (o.order_date and o.order_date < zoho_from):
            stage = 5                            # in Zoho - or from before Zoho started (never sent there)
        else:
            stage = 4
        refs = sorted({mr_of_line[i].ref for i in p["related"] if mr_of_line.get(i) and
                       not (mr_of_line[i].notes or "").startswith("Stock for the store, ordered on")})
        needs = [mr_of_line[i].needed_by for i in p["related"] if mr_of_line.get(i) and mr_of_line[i].needed_by]
        due = o.delivery_date or (min(needs) if needs else None)
        sup = sups.get(o.supplier_id)
        missing = [x for x in lines if x["remaining"] > EPS]
        to_come = "; ".join(f"{_qty(x['remaining'])} {x['unit'] or ''} {x['description']}".replace("  ", " ")
                            for x in missing[:2]) + (f" +{len(missing) - 2} more" if len(missing) > 2 else "")
        role, act = ("store", "Book delivery") if part else NEXT.get(stage, ("", ""))
        result = ""
        if stage == 5:
            came = any(x["delivered"] > EPS for x in lines)
            closed = any(x["closed"] > EPS for x in lines)
            result = ("Nothing came - closed" if not came else "Came" + (", rest closed" if closed else "") + ", bill checked")
        rows.append({
            "key": f"lpo{o.id}", "kind": "lpo", "id": o.id, "ref": o.ref, "requests": refs,
            "site": book.sites.key(o) if book.sites.key(o) != "STORE" else "Store",
            "what": _what([x["description"] for x in lines]),
            "supplier": o.supplier_name or (sup.name if sup else ""),
            "contact": _clean(o.supplier_contact) or _clean(sup.contact_person if sup else ""),
            "phone": _clean(o.supplier_phone) or _clean(sup.phone if sup else ""),
            "stage": stage, "part": part, "to_come": to_come if part else "",
            "due": due.isoformat() if due else "", "late": _late(due, today, stage, part),
            "role": role if stage < 5 else "", "who": who.get(role, "") if stage < 5 else "", "action": act if stage < 5 else "",
            "date": o.order_date.isoformat() if o.order_date else "",
            "created": o.created_at.isoformat() if o.created_at else "",
            "bill_checked": bool(o.bill_checked), "zoho": o.zoho_status or "", "rental": bool(p.get("rental")),
            "result": result, "part_why": (o.part_why or "") if (part or stage == 2) else "", "part_note": (o.part_note or "") if (part or stage == 2) else "",
        })

    # ---- material requests not (yet) on a live LPO
    with_lpo = {o.request_id for o in book.orders if o.request_id}
    name = lambda l: (book.items[l.item_id].name if l.item_id in book.items else "") or l.description or "(no name)"
    for mr in book.reqs:
        if (mr.notes or "").startswith(("Stock for the store, ordered on", "Ordered direct on")):
            continue                              # an LPO's own tracking request: the LPO's row says it all
        every = book.by_req.get(mr.id, [])
        if (mr.status or "pending") in ("rejected", "closed", "delivered"):
            if not any(l.id in covered for l in every):   # one an LPO stands for is on the LPO's row
                rows.append(_closed_mr(mr, every, name, M.MR_WORDS.get(mr.status, mr.status)))
            continue
        lines = [l for l in every if (l.status or "pending") != "rejected"]
        pending = [l for l in lines if (l.status or "pending") == "pending"]
        def out(l):
            return float(l.qty_approved or l.qty_requested or 0) - float(l.qty_received or 0)
        loose = [l for l in lines if (l.status or "") == "approved" and out(l) > EPS and l.id not in covered]
        to_order = [l for l in loose if not l.supplier_id or l.id in freed]
        no_lpo = [l for l in loose if l.supplier_id and l.id not in freed]
        if pending:
            stage, show = 0, pending
        elif to_order:
            stage, show = 1, to_order
        elif no_lpo:
            stage, show = 2, no_lpo
        else:
            continue
        sup = sups.get(show[0].supplier_id) if stage == 2 else None
        role, act = NEXT[stage]
        if stage == 2:
            act = "Mark arrived"                  # ordered on the request itself (no LPO): booked in on the request
        rows.append({
            "key": f"mr{mr.id}", "kind": "mr", "id": mr.id, "ref": mr.ref, "requests": [mr.ref],
            "site": "Store" if (mr.site or "").upper() == "STORE" else (mr.site or ""),
            "what": _what([name(l) for l in show]),
            "supplier": sup.name if sup else "", "contact": _clean(sup.contact_person) if sup else "",
            "phone": _clean(sup.phone) if sup else "",
            "stage": stage, "part": False, "to_come": "",
            "due": mr.needed_by.isoformat() if mr.needed_by else "", "late": _late(mr.needed_by, today, stage, False),
            "role": role, "who": who.get(role, ""), "action": act,
            "date": mr.requested_on.isoformat() if mr.requested_on else "",
            "created": mr.created_at.isoformat() if mr.created_at else "",
            "requested_by": mr.requested_by or "", "no_lpo": stage == 2, "result": "",
            "untouched": mr.id not in with_lpo and all((l.status or "pending") == "pending" and not (l.qty_received or 0)
                                                        and not l.supplier_id for l in every),
            "lines": [{"id": l.id, "name": name(l), "qty": float(l.qty_requested or 0), "unit": l.unit or "",
                       "purpose": l.purpose or "", "status": l.status or "pending"} for l in lines],
        })
    # the most recently raised first (4 Nov 2026) - an LPO or request made today is at the top, the oldest at the bottom
    rows.sort(key=lambda r: (r.get("created") or r.get("date") or "", r.get("date") or "", r["id"]), reverse=True)
    counts = [sum(1 for r in rows if r["stage"] == i) for i in range(6)]
    return {"rows": rows, "counts": counts, "steps": STEPS, "people": who, "today": today.isoformat()}


@router.get("/store/purchase/tracker")
def tracker(db: Session = Depends(get_db), user: models.User = Depends(SEE)):
    data = build(db)
    job = ""
    if (user.role or "") != "admin" and getattr(user, "access_role_id", None):
        r = db.get(models.AccessRole, user.access_role_id)
        job = (r.name or "").lower() if r else ""
    perms = set(M.effective_permissions(user)) if job else set()
    can = {"purchaser": "approvals" in perms, "store": bool({"storekeeper", "store"} & perms), "accounts": "accounts_zoho" in perms}
    data["my_roles"] = [k for k, words in DEPT_WORDS.items() if can[k] and any(w in job for w in words)]
    return data


@router.post("/store/request-lines/{line_id}/approve-less")
def approve_less(line_id: int, payload: dict = Body(...), db: Session = Depends(get_db),
                 user: models.User = Depends(M.require_screen("approvals"))):
    """Approve fewer than asked. The line then asks for that many (as a part-closed LPO line does), so every other
    screen - Approvals, the LPO queue, Order follow-up, the request's status - reads the approved quantity."""
    line = db.get(models.MaterialRequestLine, line_id)
    if not line:
        raise HTTPException(status_code=404, detail="Request line not found.")
    try:
        qty = float(str(payload.get("qty") or "").replace(",", ""))
    except ValueError:
        raise HTTPException(status_code=400, detail="Type how many are approved.")
    asked = float(line.qty_requested or 0)
    got = float(line.qty_received or 0)
    if qty <= EPS:
        raise HTTPException(status_code=400, detail="Approving none is a reject - use Reject.")
    if qty > asked + EPS:
        raise HTTPException(status_code=400, detail=f"More than asked for ({_qty(asked)}) - approve it in full instead.")
    if qty < got - EPS:
        raise HTTPException(status_code=400, detail=f"{_qty(got)} already arrived - cannot approve fewer than that.")
    if line.supplier_id and (line.status or "") == "approved" and abs(qty - asked) > EPS:
        raise HTTPException(status_code=400, detail="Already ordered from a supplier - change the LPO instead.")
    why = " ".join(str(payload.get("reason") or "").split())[:200]
    mr = line.request
    line.status = "approved"
    line.reject_reason = ""
    rest = None
    if abs(qty - asked) > EPS:
        line.qty_requested = line.qty_approved = qty
        note = f"Asked for {_qty(asked)}, approved {_qty(qty)}" + (f": {why}" if why else "")
        line.notes = ((line.notes or "") + (" | " if line.notes else "") + note)[:1000]
        # The rest is not turned down - it stays on the request, waiting on the office, until it is approved (to a
        # second supplier, say) or rejected (14/11/2026: 6 m3 sand asked, 3 approved first, the other 3 had gone).
        rest = rest_line(db, line, asked - qty)
    if mr.status in ("pending", "approved", "rejected"):
        states = [l.status or "pending" for l in mr.lines]
        mr.status = "approved" if any(s == "approved" for s in states) else "pending"
    db.commit()
    M.log_action(db, user.id, "request_line_decision",
                 f"{mr.ref} line {line_id} approved {_qty(qty)} of {_qty(asked)}" + (f" ({why})" if why else "")
                 + (f"; the other {_qty(rest.qty_requested)} waits on the office" if rest else ""))
    return M._mr_out(mr)


def rest_line(db, line, left):
    """A new line on the same request for what was not approved yet: same material, unit and purpose, waiting on the
    office. It keeps the name the store asked; its own 'asked' is the part still to decide."""
    if left <= EPS:
        return None
    r = models.MaterialRequestLine(request_id=line.request_id, item_id=line.item_id, description=line.description or "",
                                   qty_requested=left, qty_approved=0, unit=line.unit, purpose=line.purpose or "",
                                   status="pending", source="rest", asked_name=line.asked_name, asked_qty=left,
                                   notes=f"Rest of line {line.id}: {_qty(line.asked_qty if line.asked_qty is not None else line.qty_requested + left)} {line.unit or ''} asked, "
                                         f"{_qty(line.qty_requested)} approved first".replace("  ", " "))
    db.add(r)
    db.flush()
    return r


@router.post("/store/purchase/orders/{order_id}/close-rest")
def close_rest(order_id: int, payload: dict = Body(default={}), db: Session = Depends(get_db),
               user: models.User = Depends(M.require_any_screen("store", "storekeeper", "approvals"))):
    """Part came and the rest is not needed (the site's needs changed): the rest of every line is closed - recorded
    as 'not coming', no delivery note, no stock moved. The bill to expect is then what came."""
    o = db.get(models.PurchaseOrder, order_id)
    if not o:
        raise HTTPException(status_code=404, detail="Purchase order not found.")
    if (o.status or "") == "cancelled":
        raise HTTPException(status_code=400, detail=f"{o.ref} is cancelled.")
    why = " ".join(str(payload.get("reason") or "").split())[:200]
    if not why:
        raise HTTPException(status_code=400, detail="Say why the rest is not needed.")
    p = P.Book(db).of(o)
    left = [x for x in p["lines"] if x["remaining"] > EPS]
    if not left:
        raise HTTPException(status_code=400, detail=f"Nothing is still to come on {o.ref}.")
    done = P.book_delivery(db, o, [{"line_id": x["line_id"], "qty": 0, "close": True} for x in left], "", M._dubai_today(),
                           user_id=user.id, notes=f"Rest not needed: {why}", check=False)
    db.commit()
    M.log_action(db, user.id, "lpo_close_rest", f"{o.ref}: rest not needed ({why}) - " + "; ".join(done))
    b = P.Book(db)
    return {"ok": True, "done": done, "status": b.of(o)["status"]}


# ---- one request in full: its materials, where each stands, and the LPOs that stand for them ------------------
@router.get("/store/purchase/tracker/request/{req_id}")
def request_detail(req_id: int, db: Session = Depends(get_db), user: models.User = Depends(SEE)):
    mr = db.get(models.MaterialRequest, req_id)
    if not mr:
        raise HTTPException(status_code=404, detail="Request not found.")
    d = M._mr_out(mr)
    book = P.Book(db)
    lpos = defaultdict(list)
    for o in book.orders:
        p = book.of(o)
        if p and p["status"] not in ("cancelled", "superseded"):
            for i in p["related"]:
                lpos[i].append({"id": o.id, "ref": o.ref, "status": P.STATUS_WORDS.get(p["status"], p["status"])})
    for l in d["lines"]:
        l["lpos"] = lpos.get(l["id"], [])
    office = user.role == "admin" or "approvals" in M.effective_permissions(user)
    with_lpo = any(o.request_id == mr.id for o in book.orders)
    untouched = ((mr.status or "pending") == "pending" and not with_lpo
                 and all((l.status or "pending") == "pending" and not (l.qty_received or 0) and not l.supplier_id for l in mr.lines))
    d["can_edit"] = untouched and (office or not mr.created_by or mr.created_by == user.id)
    d["can_delete"] = d["can_edit"]
    d["mine"] = mr.created_by == user.id
    d["status_word"] = M.MR_WORDS.get(mr.status, mr.status)
    try:
        d["deliveries"] = M.request_deliveries(req_id, db=db, user=user)["rows"]
    except Exception:
        d["deliveries"] = []
    return d


# ---- Orders from before the current purchaser joined (Oct 2026) are not known: an old order is closed as it stands --------
def _close_lpo_old(db, o, how, why, bill, user):
    book = P.Book(db)
    p = book.of(o)
    left = [x for x in p["lines"] if x["remaining"] > EPS]
    done = []
    if left and how == "not_coming":
        done += P.book_delivery(db, o, [{"line_id": x["line_id"], "qty": 0, "close": True} for x in left], "",
                                M._dubai_today(), user_id=user.id, notes=f"Closed - not coming: {why}", check=False)
    elif left and how == "came":
        # it came before and was used: recorded against the LPO only - no stock is added now (it would count twice)
        lines = {l.id: l for l in o.lines}
        used = set()
        for x in left:
            l = lines.get(x["line_id"])
            it = book.items.get(l.item_id) if l else None
            mrl = P._mr_line_for(book, o, l, it, exclude=used) if l else None
            db.add(models.LpoReceipt(order_id=o.id, line_id=x["line_id"], item_id=l.item_id if l else None,
                                     line_key=P.plain(l.description) if l else "", kind="delivered", qty=x["remaining"],
                                     dn_no="", dn_date=M._dubai_today(), location=x["location"], tag="closed - came earlier",
                                     created_by=user.id, notes=f"Came earlier, not booked then - no stock added: {why}"[:300],
                                     request_line_id=mrl.id if mrl else None))
            if mrl:
                mrl.qty_received = min(float(mrl.qty_requested or 0), float(mrl.qty_received or 0) + x["remaining"])
                used.add(mrl.id)
                P._settle(mrl.request)
            done.append(f"{x['description']}: {_qty(x['remaining'])} {x['unit']} came earlier (no stock added)")
        db.flush()
        P.settle_tracking(db, o)
    if bill and not o.bill_checked:
        o.bill_checked, o.bill_checked_by, o.bill_checked_at = True, user.id, datetime.now(timezone.utc)
        o.bill_note = (f"Closed by {user.full_name or user.username} without a bill check: {why}")[:200]
        done.append("bill check closed")
    return done


@router.post("/store/purchase/orders/{order_id}/close-old")
def close_old_lpo(order_id: int, payload: dict = Body(...), db: Session = Depends(get_db),
                  user: models.User = Depends(M.require_screen("approvals"))):
    """Close an LPO as it stands: what is still to come either came earlier (recorded, no stock added - it was used)
    or is not coming (closed). Optionally the bill check too (the bill is with accounts already). Paperwork only."""
    o = db.get(models.PurchaseOrder, order_id)
    if not o or (o.status or "") == "cancelled":
        raise HTTPException(status_code=404, detail="Open purchase order not found.")
    how = str(payload.get("how") or "")
    why = " ".join(str(payload.get("reason") or "").split())[:200]
    if how not in ("came", "not_coming"):
        raise HTTPException(status_code=400, detail="Say whether it came earlier or is not coming.")
    if not why:
        raise HTTPException(status_code=400, detail="Give the reason.")
    done = _close_lpo_old(db, o, how, why, bool(payload.get("bill")), user)
    db.commit()
    M.log_action(db, user.id, "lpo_close_old", f"{o.ref}: closed as it stands ({why}) - " + ("; ".join(done) or "nothing left open"))
    return {"ok": True, "done": done}


@router.post("/store/requests/{req_id}/close-old")
def close_old_request(req_id: int, payload: dict = Body(...), db: Session = Depends(get_db),
                      user: models.User = Depends(M.require_screen("approvals"))):
    """Close a request as it stands: came earlier (its materials marked received - no stock added) or not needed."""
    mr = db.get(models.MaterialRequest, req_id)
    if not mr:
        raise HTTPException(status_code=404, detail="Request not found.")
    how = str(payload.get("how") or "")
    why = " ".join(str(payload.get("reason") or "").split())[:200]
    if how not in ("came", "not_coming"):
        raise HTTPException(status_code=400, detail="Say whether it came earlier or is not needed.")
    if not why:
        raise HTTPException(status_code=400, detail="Give the reason.")
    if how == "came":
        for l in mr.lines:
            if (l.status or "pending") == "rejected":
                continue
            if (l.status or "pending") == "pending":
                l.status = "approved"
            l.qty_received = max(float(l.qty_received or 0), float(l.qty_requested or 0))
        P._settle(mr)
        if mr.status != "delivered":
            mr.status, mr.closed_on = "delivered", M._dubai_today()
    else:
        mr.status, mr.closed_on = "closed", M._dubai_today()
    mr.office_remark = (("Came earlier - no stock added: " if how == "came" else "Not needed: ") + why)[:500]
    db.commit()
    M.log_action(db, user.id, "material_request_close_old", f"{mr.ref}: {mr.office_remark}")
    return {"ok": True, "status": mr.status}


# ---- Preview / PDF / Excel of what is on screen (the same filters) --------------------------------------------
@router.get("/export/store/tracker")
def export_tracker(token: str, format: str = "view", view: str = "open", site: str = "", q: str = "", step: str = "",
                   db: Session = Depends(get_db)):
    from urllib.parse import quote
    from fastapi.responses import StreamingResponse
    import auth
    import export_web
    u = auth.get_download_user_from_token(token, db)
    perms = M.effective_permissions(u)
    if (u.role or "") != "admin" and not ({"requests", "approvals", "store", "storekeeper", "accounts_zoho"} & set(perms)):
        raise HTTPException(status_code=403, detail="Not available to this login.")
    data = tracker(db=db, user=u)
    rows = [r for r in data["rows"] if (not site or r["site"] == site)]
    if q.strip():
        n = q.strip().lower()
        rows = [r for r in rows if n in " ".join([r["ref"], r["what"], r["supplier"], r["contact"], r["phone"], r["site"],
                                                  " ".join(r.get("requests") or []), r.get("requested_by") or ""]).lower()]
    if step.isdigit():
        rows = [r for r in rows if r["stage"] == int(step)]
        label = STEPS[int(step)]
    elif view == "mine":
        rows = [r for r in rows if r["stage"] < 5 and r["role"] in data["my_roles"]]
        label = "My turn"
    elif view == "late":
        rows = [r for r in rows if r["stage"] < 5 and r["late"] > 0]
        label = "Late"
    elif view == "done":
        rows = [r for r in rows if r["stage"] == 5]
        label = "Done and closed"
    else:
        rows = [r for r in rows if r["stage"] < 5]
        label = "All open"
    out = [{"Site": r["site"], "Item": r["what"], "LPO / request": " / ".join([r["ref"]] + [x for x in (r.get("requests") or []) if x != r["ref"]]),
            "Supplier": r["supplier"], "Contact": r["contact"], "Phone": r["phone"],
            "Where it is": ("Part arrived" if r["part"] else STEPS[r["stage"]]) + (f" - {r['result']}" if r.get("result") else ""),
            "Late (days)": r["late"] or "", "Still to come": r["to_come"],
            "Next": (f"{r['who']} - {r['action']}" if r["who"] else "")} for r in rows]
    title = "Order Tracker"
    sub = f"{label}" + (f" | site {site}" if site else "") + (f" | search '{q.strip()}'" if q.strip() else "") + \
          f" | {len(out)} order(s) | As at {M._dubai_today():%d/%m/%Y}"
    if format == "view":
        qs = f"view={view}&site={quote(site)}&q={quote(q)}&step={quote(step)}"
        url = f"/export/store/tracker?{qs}&token={quote(auth.create_view_token(u.username), safe='')}"
        return M._preview_page(title, sub, out, url, url, money_cols=[])
    name = f"Order_Tracker_{M._dubai_today():%d.%m.%Y}"
    if format == "pdf":
        return StreamingResponse(export_web.build_store_report_pdf(title, out, sub, money_cols=[], orientation="landscape"),
                                 media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})
    return StreamingResponse(export_web.build_store_report_excel(title, out, sub, money_cols=[]),
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename={name}.xlsx"})


# ---- one material of a request: not needed (the rest of the request goes on) --------------------------------------
@router.post("/store/request-lines/{line_id}/not-needed")
def line_not_needed(line_id: int, payload: dict = Body(...), db: Session = Depends(get_db),
                    user: models.User = Depends(M.require_screen("approvals"))):
    """Only this material is not needed - e.g. MR-0061 wants the solid blocks, not the hollow ones. Nothing arrived:
    it is rejected with the reason. Part arrived: it asks for what came, the rest is closed. Still on a live LPO: the
    LPO is changed instead (it would still be ordered). Paperwork only - no stock, no amount."""
    line = db.get(models.MaterialRequestLine, line_id)
    if not line:
        raise HTTPException(status_code=404, detail="Request line not found.")
    why = " ".join(str(payload.get("reason") or "").split())[:200]
    if not why:
        raise HTTPException(status_code=400, detail="Give the reason.")
    mr = line.request
    name = (line.item.name if line.item else "") or line.description or "this material"
    if (line.status or "pending") == "rejected":
        return M._mr_out(mr)
    book = P.Book(db)
    on = [o.ref for o in book.orders if book.of(o) and book.of(o)["status"] not in ("cancelled", "superseded", "delivered", "closed")
          and line_id in book.of(o)["related"] and any(_fits_line(book, o, line) for _ in [0])]
    if on:
        raise HTTPException(status_code=400, detail=f"{name} is on {', '.join(on)} - change the LPO (take it off or reduce it) instead.")
    got = float(line.qty_received or 0)
    if got > EPS:
        asked = float(line.qty_requested or 0)
        line.qty_requested = line.qty_approved = got
        line.notes = ((line.notes or "") + (" | " if line.notes else "") + f"Asked for {_qty(asked)}, {_qty(got)} came - rest not needed: {why}")[:1000]
    else:
        line.status, line.reject_reason = "rejected", f"Not needed: {why}"[:300]
    live = [l for l in mr.lines if (l.status or "pending") != "rejected"]
    if not live:
        mr.status, mr.closed_on = ("delivered" if any((l.qty_received or 0) > 0 for l in mr.lines) else "rejected"), M._dubai_today()
    elif mr.status in ("ordered", "partial", "delivered"):
        P._settle(mr)
    elif mr.status in ("pending", "approved"):
        mr.status = "approved" if any((l.status or "pending") == "approved" for l in live) else "pending"
    db.commit()
    M.log_action(db, user.id, "request_line_not_needed", f"{mr.ref}: {name} not needed ({why})")
    return M._mr_out(mr)


def _fits_line(book, o, mrl):
    """Is this request line still ordered on the LPO (a line of it is the same material)?"""
    mi = book.items.get(mrl.item_id)
    ticked = mrl.id in set(P._ids(o.request_line_ids))
    for l in o.lines:
        it = book.items.get(l.item_id)
        if P._fits(l, it, mrl, mi):
            return True
        if ticked and any(P._words_in(x, y) for x in (mrl.description or "", mi.name if mi else "") if x
                          for y in (l.description or "", it.name if it else "") if y):
            return True
    return False



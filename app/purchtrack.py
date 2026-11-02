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
PEOPLE_DEFAULT = {"purchaser": "Arun", "store": "Amal", "accounts": "Shafeeq"}
# their logins (the chief accountant signs in as 'shafiq'): whose turn is 'My turn'
LOGINS_DEFAULT = {"purchaser": ["arun"], "store": ["amal"], "accounts": ["shafiq", "shafeeq"]}
# who acts at each step
NEXT = {0: ("purchaser", "Approve"), 1: ("purchaser", "Raise LPO"), 2: ("store", "Book delivery"),
        3: ("purchaser", "Check bill"), 4: ("accounts", "Send to Zoho")}
SEE = M.require_any_screen("requests", "approvals", "store", "storekeeper", "accounts_zoho")


def people(db):
    raw = M.get_setting(db, "purchase_people")
    try:
        v = json.loads(raw) if raw else {}
    except ValueError:
        v = {}
    return {k: (str(v.get(k) or "").strip() or d) for k, d in PEOPLE_DEFAULT.items()}


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


def build(db):
    today = M._dubai_today()
    book = P.Book(db)
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
        if not p or p["status"] in ("cancelled", "superseded"):
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
        elif (o.zoho_status or "") in ("sent", "changed"):
            stage = 5
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
            "bill_checked": bool(o.bill_checked), "zoho": o.zoho_status or "", "rental": bool(p.get("rental")),
        })

    # ---- material requests not (yet) on a live LPO
    for mr in book.reqs:
        if (mr.status or "pending") in ("rejected", "closed", "delivered"):
            continue
        if (mr.notes or "").startswith("Stock for the store, ordered on"):
            continue                              # an LPO's own tracking request: the LPO's row says it all
        lines = [l for l in book.by_req.get(mr.id, []) if (l.status or "pending") != "rejected"]
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
        name = lambda l: (book.items[l.item_id].name if l.item_id in book.items else "") or l.description or "(no name)"
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
            "requested_by": mr.requested_by or "", "no_lpo": stage == 2,
            "lines": [{"id": l.id, "name": name(l), "qty": float(l.qty_requested or 0), "unit": l.unit or "",
                       "purpose": l.purpose or "", "status": l.status or "pending"} for l in lines],
        })
    rows.sort(key=lambda r: (r["stage"] == 5, -r["late"], r["stage"], r["date"] or "", r["ref"]))
    counts = [sum(1 for r in rows if r["stage"] == i) for i in range(6)]
    return {"rows": rows, "counts": counts, "steps": STEPS, "people": who, "today": today.isoformat()}


@router.get("/store/purchase/tracker")
def tracker(db: Session = Depends(get_db), user: models.User = Depends(SEE)):
    data = build(db)
    words = set(((user.full_name or "") + " " + (user.username or "")).lower().split())
    login = (user.username or "").strip().lower()
    data["my_roles"] = [k for k, v in data["people"].items()
                        if (v and v.lower() in words) or login in LOGINS_DEFAULT.get(k, [])]
    return data


@router.post("/store/purchase/people")
def set_people(payload: dict = Body(...), db: Session = Depends(get_db),
               user: models.User = Depends(M.require_screen("approvals"))):
    cur = people(db)
    for k in PEOPLE_DEFAULT:
        if k in payload and str(payload[k] or "").strip():
            cur[k] = str(payload[k]).strip()[:40]
    M.put_setting(db, "purchase_people", json.dumps(cur))
    M.log_action(db, user.id, "purchase_people", json.dumps(cur))
    return cur


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
    if abs(qty - asked) > EPS:
        line.qty_requested = line.qty_approved = qty
        note = f"Asked for {_qty(asked)}, approved {_qty(qty)}" + (f": {why}" if why else "")
        line.notes = ((line.notes or "") + (" | " if line.notes else "") + note)[:1000]
    if mr.status in ("pending", "approved", "rejected"):
        states = [l.status or "pending" for l in mr.lines]
        mr.status = "approved" if any(s == "approved" for s in states) else "pending"
    db.commit()
    M.log_action(db, user.id, "request_line_decision",
                 f"{mr.ref} line {line_id} approved {_qty(qty)} of {_qty(asked)}" + (f" ({why})" if why else ""))
    return M._mr_out(mr)


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

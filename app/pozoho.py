"""LPOs into Zoho as purchase orders, with the portal's own numbers
(IC/LPO/2026xxxx) - the chief accountant presses Send.

A purchase order posts nothing to the ledger, so what matters is that it
goes once, to the right vendor, with the right lines: the same send-once
claim as everything else, Zoho asked for the number before any resend, and
a PO changed or cancelled here after it went is flagged to be done in Zoho.
"""
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

import main as M
import models
from database import get_db

router = APIRouter()
ZG = Depends(M.require_any_screen("accounts_zoho"))
PLACES = [("purchaseorders", "purchaseorders", "purchaseorder_id", "purchaseorder_number")]


def _vendor(db, o):
    s = db.get(models.Supplier, o.supplier_id) if o.supplier_id else None
    if not s and (o.supplier_name or "").strip():
        key = M._supplier_key(o.supplier_name)
        s = db.query(models.Supplier).filter(models.Supplier.name_key == key).first() if key else None
    return (s.zoho_id or "") if s else ""


def _site(db, o):
    if o.request_id:
        r = db.get(models.MaterialRequest, o.request_id)
        if r and (r.site or "").strip():
            return r.site.strip()
    return ""


def push(db, o):
    import zohoapi as Z
    # Already in Zoho under this number (typed by hand, or a send whose
    # answer was lost)? Linked, not made twice.
    d = Z.call(db, "GET", "purchaseorders", {"purchaseorder_number": o.ref, "per_page": 25})
    for po in d.get("purchaseorders", []):
        if (po.get("purchaseorder_number") or "").strip() == o.ref:
            return po["purchaseorder_id"], "Found in Zoho"
    vendor = _vendor(db, o)
    if not vendor:
        raise Z.ZohoError(400, f"Link {o.supplier_name or 'the supplier'} to its Zoho vendor first (Suppliers in Zoho) - a PO needs one")
    v5, v0 = Z.vat_tax(db), Z.zero_tax(db)
    items = []
    for i, l in enumerate(o.lines):
        t = v5 if round(l.tax_pct or 0, 2) == 5 else v0
        if not t:
            raise Z.ZohoError(400, f"Zoho has no {'5% Standard Rate' if round(l.tax_pct or 0, 2) == 5 else 'Zero Rate'} tax - nothing sent")
        desc = " - ".join(x for x in ((l.description or "").strip(), (l.description2 or "").strip()) if x)[:2000]
        items.append({"description": desc or "Item", "quantity": round(l.qty or 0, 3), "rate": round(l.rate or 0, 2),
                      "unit": (l.unit or "")[:20], "tax_id": t, "item_order": i + 1})
    if not items:
        raise Z.ZohoError(400, "The LPO has no lines")
    site = _site(db, o)
    body = {"vendor_id": vendor, "purchaseorder_number": o.ref, "date": o.order_date.isoformat(),
            "reference_number": " · ".join(x for x in (site, (o.supplier_ref or "").strip()) if x)[:100],
            "line_items": items, "is_inclusive_tax": False,
            "notes": " - ".join(x for x in (o.job_scope, o.project_location, o.plot_no and f"Plot {o.plot_no}") if x)[:1000]}
    if o.delivery_date:
        body["delivery_date"] = o.delivery_date.isoformat()
    if (o.discount_pct or 0) > 0:
        body["discount"] = f"{round(o.discount_pct, 2)}%"
        body["is_discount_before_tax"] = True
    d = Z.call(db, "POST", "purchaseorders", {"ignore_auto_number_generation": "true"}, body=body)
    return d["purchaseorder"]["purchaseorder_id"], "Purchase order"


def _start(db):
    import zohosync
    return zohosync._start(db)


def _total(o):
    sub = sum((l.qty or 0) * (l.rate or 0) for l in o.lines)
    sub -= sub * (o.discount_pct or 0) / 100
    return round(sub + sum((l.qty or 0) * (l.rate or 0) * (1 - (o.discount_pct or 0) / 100) * (l.tax_pct or 0) / 100 for l in o.lines), 2)


@router.get("/store/zoho/pos")
def pos(db: Session = Depends(get_db), user: models.User = ZG):
    q = (db.query(models.PurchaseOrder).filter(models.PurchaseOrder.order_date >= _start(db))
           .order_by(models.PurchaseOrder.po_no).all())
    rows = []
    for o in q:
        st = o.zoho_status or ""
        if o.status == "cancelled" and st not in ("sent", "changed"):
            continue
        if st == "sent" and not (o.zoho_err or ""):
            continue
        rows.append({"id": o.id, "ref": o.ref, "date": o.order_date.isoformat(), "supplier": o.supplier_name or "",
                     "total": _total(o), "site": _site(db, o), "linked": bool(_vendor(db, o)), "status": st,
                     "cancelled": o.status == "cancelled",
                     "err": "" if (o.zoho_err or "").startswith("sending@") else (o.zoho_err or "")})
    return {"rows": rows}


@router.post("/store/zoho/pos/send")
def send(payload: dict = Body(default={}), db: Session = Depends(get_db), user: models.User = ZG):
    import zohoapi as Z
    if not Z.connected(db):
        raise HTTPException(status_code=400, detail="Zoho is not connected yet - press Connect Zoho.")
    ids = {int(i) for i in (payload.get("ids") or [])}
    start = _start(db)
    sent, failed = 0, []
    for o in db.query(models.PurchaseOrder).filter(models.PurchaseOrder.zoho_status.in_(["", "sending"]),
                                                   models.PurchaseOrder.status != "cancelled").all():
        if ids and o.id not in ids:
            continue
        if o.order_date < start:
            continue
        if o.zoho_status is None:
            o.zoho_status = ""; db.commit()
        if not Z.claim(db, models.PurchaseOrder, o, ("",)):
            continue
        try:
            zid, label = push(db, o)
            o.zoho_status, o.zoho_id, o.zoho_err = "sent", f"purchaseorder:{zid}", ""
            sent += 1
        except Exception as e:
            o.zoho_status = ""
            o.zoho_err = Z.fail_text(e)
            failed.append({"id": o.id, "ref": o.ref, "why": o.zoho_err})
        db.commit()
    if sent:
        M.log_action(db, user.id, "zoho_pos", f"{sent} LPO(s) sent to Zoho as purchase orders")
    return {"ok": True, "sent": sent, "failed": failed}


@router.post("/store/zoho/pos/corrected")
def corrected(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = ZG):
    """The change (or the cancellation) has been made in Zoho too."""
    o = db.get(models.PurchaseOrder, int(payload.get("id") or 0))
    if o and (o.zoho_status or "") in ("sent", "changed"):
        o.zoho_status, o.zoho_err = "sent", ""
        db.commit()
        M.log_action(db, user.id, "zoho_pos", f"{o.ref} confirmed matching in Zoho")
    return {"ok": True}

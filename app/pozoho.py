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


# Zoho's VAT treatments with no VAT on a purchase from them.
NOT_REGISTERED = ("vat_not_registered", "gcc_vat_not_registered", "dz_vat_not_registered", "non_gcc")


def _vendor_treatment(db, vendor_id):
    """The VAT treatment Zoho holds for the vendor ("" when Zoho cannot say)."""
    import zohoapi as Z
    try:
        c = (Z.call(db, "GET", f"contacts/{vendor_id}") or {}).get("contact") or {}
        return (c.get("tax_treatment") or c.get("vat_treatment") or "").strip()
    except Exception:
        return ""


def _trn(db, o):
    """The supplier's TRN from the portal - only a proper 15-digit one."""
    s = db.get(models.Supplier, o.supplier_id) if o.supplier_id else None
    if not s and (o.supplier_name or "").strip():
        key = M._supplier_key(o.supplier_name)
        s = db.query(models.Supplier).filter(models.Supplier.name_key == key).first() if key else None
    t = "".join(ch for ch in ((s.trn if s else "") or "") if ch.isdigit())
    return t if len(t) == 15 else ""


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
    body = _body(db, o)
    d = Z.call(db, "POST", "purchaseorders", {"ignore_auto_number_generation": "true"}, body=body)
    return d["purchaseorder"]["purchaseorder_id"], "Purchase order"


def _body(db, o):
    """The Zoho purchase order for this LPO - the same for a first send and for an update."""
    import zohoapi as Z
    vendor = _vendor(db, o)
    if not vendor:
        raise Z.ZohoError(400, f"Link {o.supplier_name or 'the supplier'} to its Zoho vendor first (Suppliers in Zoho) - a PO needs one")
    acc_id = Z.account_id(db, o.zoho_account or "") if (o.zoho_account or "").strip() else ""
    if not acc_id:
        raise Z.ZohoError(400, "Pick the Zoho account for this LPO (the bill takes it) - nothing sent")
    # VAT treatment. Zoho refuses any VAT rate - Zero Rate included - on a PO to a vendor it holds as
    # not VAT registered ("VAT or Exemption cannot be applied for this VAT Treatment", IC/LPO/20260157).
    # Such a vendor's 0% LPO goes with no tax on the lines; one with 5% goes as VAT registered with the
    # supplier's TRN. A vendor Zoho holds as registered (or one it cannot say) goes exactly as before.
    treat, extra = _vendor_treatment(db, vendor), {}
    any5 = any(round(l.tax_pct or 0, 2) == 5 for l in o.lines)
    no_vat = treat in NOT_REGISTERED and not any5
    if treat in NOT_REGISTERED and any5:
        trn = _trn(db, o)
        if not trn:
            raise Z.ZohoError(400, f"{o.supplier_name or 'The supplier'} charges 5% VAT on this LPO but is not VAT registered in Zoho and has no "
                                   "15-digit TRN in the portal - put its TRN on the supplier, then send again")
        extra = {"tax_treatment": "vat_registered", "tax_reg_no": trn}
    elif no_vat:
        extra = {"tax_treatment": treat}
    v5, v0 = Z.vat_tax(db), Z.zero_tax(db)
    items = []
    for i, l in enumerate(o.lines):
        t = "" if no_vat else (v5 if round(l.tax_pct or 0, 2) == 5 else v0)
        if not t and not no_vat:
            raise Z.ZohoError(400, f"Zoho has no {'5% Standard Rate' if round(l.tax_pct or 0, 2) == 5 else 'Zero Rate'} tax - nothing sent")
        desc = " - ".join(x for x in ((l.description or "").strip(), (l.description2 or "").strip()) if x)[:1900]
        if getattr(o, "combined", False) and (l.cost_to or "").strip():
            # combined LPO: whose cost each line is, for the chief accountant (not on the printed LPO)
            desc += f" | Cost to: {'Store' if l.cost_to.upper() == 'STORE' else l.cost_to}"
        # No catalogue item: Zoho needs the account on each line (as the
        # chief accountant enters them), else "non-purchase item".
        it = {"description": desc or "Item", "quantity": round(l.qty or 0, 3), "rate": round(l.rate or 0, 2),
              "unit": (l.unit or "")[:20], "item_order": i + 1, "account_id": acc_id}
        if t:
            it["tax_id"] = t
        items.append(it)
    if not items:
        raise Z.ZohoError(400, "The LPO has no lines")
    site = _site(db, o)
    if getattr(o, "combined", False):
        site = "Combined: " + ", ".join("Store" if k == "STORE" else k for k, _, _ in M.lpo_split(o))
    body = {"vendor_id": vendor, "purchaseorder_number": o.ref, "date": o.order_date.isoformat(),
            "reference_number": " · ".join(x for x in (site, (o.supplier_ref or "").strip()) if x)[:100],
            "line_items": items, "is_inclusive_tax": False, **extra,
            "notes": " - ".join(x for x in (o.job_scope, o.project_location, o.plot_no and f"Plot {o.plot_no}") if x)[:1000]}
    if o.delivery_date and o.delivery_date >= o.order_date:
        body["delivery_date"] = o.delivery_date.isoformat()      # Zoho refuses a delivery date before the PO date
    if (o.discount_pct or 0) > 0:
        # Zoho books a PO discount to an account; the chief accountant's own
        # POs use "Administration Fee" (IC/LPO/20260066).
        dname = M.get_setting(db, "zoho_po_discount_account") or "Administration Fee"
        dacc = Z.account_id(db, dname)
        if not dacc:
            raise Z.ZohoError(400, f"Zoho has no account named {dname} for the LPO discount - nothing sent")
        pct = float(o.discount_pct)
        if abs(pct - round(pct, 2)) > 1e-9:
            # A discount worked back from a round total (7.5811% so the LPO comes to 66,700.34): Zoho keeps a
            # percentage to 2 places only - "7.58%" made its PO 66,701.12. The discount goes as the amount the
            # portal takes off instead, so Zoho's PO totals the same as the LPO.
            gross = sum(float(l.qty or 0) * float(l.rate or 0) for l in o.lines)
            body["discount"] = f"{round(gross * pct / 100 + 1e-9, 2):.2f}"
        else:
            body["discount"] = f"{round(o.discount_pct, 2)}%"
        body["is_discount_before_tax"] = True
        body["discount_account_id"] = dacc
    return body


# ---- an LPO changed or cancelled here: Zoho kept in step, accounts told what changed ----------------------
def _zid(o):
    z = (o.zoho_id or "").strip()
    return z.split(":", 1)[1] if z.startswith("purchaseorder:") else ""


def note_of(o):
    import json
    try:
        d = json.loads(o.acc_note or "") if (o.acc_note or "").strip() else {}
    except Exception:
        d = {}
    return d if isinstance(d, dict) else {}


def add_note(db, o, kind, changes, zoho, who_name):
    """Kept until accounts press Seen: a second change before then is added under the first."""
    import json
    from datetime import datetime, timedelta, timezone
    d = note_of(o)
    items = [] if d.get("seen", True) else list(d.get("items") or [])
    now = datetime.now(timezone.utc) + timedelta(hours=4)          # Dubai
    items.append({"kind": kind, "when": now.strftime("%d/%m/%Y %H:%M"), "who": who_name, "changes": changes[:40], "zoho": zoho})
    d = {"items": items[-10:], "seen": False, "seq": int(d.get("seq") or 0) + 1}
    o.acc_note = json.dumps(d)


def zoho_edit(db, o):
    """An LPO already in Zoho was edited here: the PO in Zoho is updated to match.
    Returns what happened, said for accounts."""
    import zohoapi as Z
    zid = _zid(o)
    if not zid:
        return ""
    try:
        if not Z.connected(db):
            raise Z.ZohoError(400, "Zoho is not connected")
        with Z.about("lpo", o.id, o.ref, None):
            Z.call(db, "PUT", f"purchaseorders/{zid}", {"ignore_auto_number_generation": "true"}, body=_body(db, o))
        o.zoho_status, o.zoho_err = "sent", ""
        return "Updated in Zoho automatically"
    except Exception as e:
        why = Z.fail_text(e) if hasattr(Z, "fail_text") else str(e)
        o.zoho_status, o.zoho_err = "changed", f"Changed here after it went to Zoho - change the PO in Zoho ({why})"[:300]
        return f"Zoho could not be updated ({why}) - change the PO in Zoho by hand, then press Done"


def zoho_cancel(db, o):
    """An LPO already in Zoho was cancelled here: marked cancelled in Zoho too."""
    import zohoapi as Z
    zid = _zid(o)
    if not zid:
        return ""
    try:
        if not Z.connected(db):
            raise Z.ZohoError(400, "Zoho is not connected")
        with Z.about("lpo", o.id, o.ref, None):
            Z.call(db, "POST", f"purchaseorders/{zid}/status/cancelled")
        o.zoho_status, o.zoho_err = "sent", ""
        return "Cancelled in Zoho automatically"
    except Exception as e:
        why = Z.fail_text(e) if hasattr(Z, "fail_text") else str(e)
        o.zoho_err = f"Cancelled here - cancel the PO in Zoho too ({why})"[:300]
        return f"Zoho could not cancel it ({why}) - cancel the PO in Zoho by hand, then press Done"


def _start(db):
    import zohosync
    return zohosync._start(db)


def _total(o):
    sub = sum((l.qty or 0) * (l.rate or 0) for l in o.lines)
    sub -= sub * (o.discount_pct or 0) / 100
    return round(sub + sum((l.qty or 0) * (l.rate or 0) * (1 - (o.discount_pct or 0) / 100) * (l.tax_pct or 0) / 100 for l in o.lines), 2)


def _last_account(db, o):
    """The account this supplier's last LPO went to Zoho with."""
    if not o.supplier_id and not (o.supplier_name or "").strip():
        return ""
    q = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.id != o.id, models.PurchaseOrder.zoho_account != "",
                                              models.PurchaseOrder.zoho_account.isnot(None))
    q = q.filter(models.PurchaseOrder.supplier_id == o.supplier_id) if o.supplier_id else \
        q.filter(models.PurchaseOrder.supplier_name == o.supplier_name)
    p = q.order_by(models.PurchaseOrder.id.desc()).first()
    return p.zoho_account if p else ""


@router.post("/store/zoho/pos/{oid}/account")
def set_account(oid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = ZG):
    import zohosync, zohoapi
    o = db.get(models.PurchaseOrder, oid)
    if not o:
        raise HTTPException(status_code=404, detail="No such LPO.")
    if (o.zoho_status or "") not in ("",):
        raise HTTPException(status_code=400, detail="It is already in Zoho - change it there.")
    acc = str(payload.get("account") or "").strip()[:200]
    if acc and (not zohosync.paid_ok(acc, db) or acc.startswith(("Transfer to ", "From ")) or acc in zohoapi.VENDOR_PAY):
        raise HTTPException(status_code=400, detail="Pick a cost account.")
    o.zoho_account = acc
    db.commit()
    return {"ok": True, "account": acc}


@router.get("/store/zoho/pos")
def pos(db: Session = Depends(get_db), user: models.User = ZG):
    q = (db.query(models.PurchaseOrder).filter(models.PurchaseOrder.order_date >= _start(db))
           .order_by(models.PurchaseOrder.po_no).all())
    rows = []
    for o in q:
        st = o.zoho_status or ""
        nt = note_of(o)
        fresh = bool(nt.get("items")) and not nt.get("seen", True)
        if o.status == "cancelled" and st not in ("sent", "changed") and not fresh:
            continue
        if st == "sent" and not (o.zoho_err or "") and not fresh:
            continue
        if not (o.zoho_account or "") and not st and o.status != "cancelled":
            sug = _last_account(db, o)
            if sug:
                o.zoho_account = sug
                db.commit()
        rows.append({"id": o.id, "ref": o.ref, "date": o.order_date.isoformat(), "supplier": o.supplier_name or "",
                     "account": o.zoho_account or "",
                     "total": _total(o), "site": _site(db, o), "linked": bool(_vendor(db, o)), "status": st,
                     "cancelled": o.status == "cancelled", "cancel_reason": o.cancel_reason or "",
                     "note": nt.get("items") if fresh else [],
                     "split": [{"to": "Store" if k == "STORE" else k, "amount": round(n_ + v_, 2)} for k, n_, v_ in M.lpo_split(o)],
                     "err": "" if (o.zoho_err or "").startswith("sending@") else (o.zoho_err or "")})
    return {"rows": rows, "hint": not M.get_setting(db, f"hint_lpo_open:{user.id}"), "may_delete": (user.role or "") == "admin"}


def delete_lpo(db, o, who=None, why=""):
    """An LPO made by mistake, gone everywhere in the portal: its lines and
    the material request it was made with (when nothing else uses it and
    nothing was received on it). Never one still in Zoho."""
    if (o.zoho_id or "").strip():
        raise HTTPException(status_code=400, detail=f"{o.ref} is in Zoho - press Reverse on Sent to Zoho first (that deletes it in Zoho), then delete it here.")
    ref, sup = o.ref, o.supplier_name or ""
    mr = db.get(models.MaterialRequest, o.request_id) if o.request_id else None
    for l in list(o.lines):
        db.delete(l)
    db.delete(o); db.flush()
    mr_ref = ""
    if mr and not db.query(models.PurchaseOrder).filter(models.PurchaseOrder.request_id == mr.id).count() \
            and not db.query(models.StoreMovement).filter(models.StoreMovement.request_id == mr.id).count():
        mr_ref = mr.ref
        for l in db.query(models.MaterialRequestLine).filter(models.MaterialRequestLine.request_id == mr.id).all():
            db.delete(l)
        db.delete(mr)
    db.commit()
    M.log_action(db, who, "delete_lpo", f"{ref} ({sup}) deleted" + (f", with {mr_ref}" if mr_ref else "") + (f" - {why}" if why else ""))
    return ref


@router.post("/store/zoho/pos/{oid}/delete")
def delete(oid: int, payload: dict = Body(default={}), db: Session = Depends(get_db), user: models.User = ZG):
    if (user.role or "") != "admin":
        raise HTTPException(status_code=403, detail="Only the admin deletes an LPO.")
    o = db.get(models.PurchaseOrder, oid)
    if not o:
        raise HTTPException(status_code=404, detail="That LPO is no longer there.")
    why = " ".join(str(payload.get("reason") or "").split())[:200]
    if not why:
        raise HTTPException(status_code=400, detail="Say why it is deleted.")
    return {"ok": True, "ref": delete_lpo(db, o, user.id, why)}


@router.post("/store/zoho/pos/hint-seen")
def hint_seen(db: Session = Depends(get_db), user: models.User = ZG):
    """The one-time 'click the LPO number to open it' tip, once per login."""
    M.put_setting(db, f"hint_lpo_open:{user.id}", "1"); db.commit()
    return {"ok": True}


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
            with Z.about("lpo", o.id, o.ref, user.id):
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


def _seen(o):
    import json
    d = note_of(o)
    if d:
        d["seen"] = True; o.acc_note = json.dumps(d)


@router.post("/store/zoho/pos/corrected")
def corrected(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = ZG):
    """The change (or the cancellation) has been made in Zoho too."""
    o = db.get(models.PurchaseOrder, int(payload.get("id") or 0))
    if o and (o.zoho_status or "") in ("sent", "changed"):
        o.zoho_status, o.zoho_err = "sent", ""
        _seen(o)
        db.commit()
        M.log_action(db, user.id, "zoho_pos", f"{o.ref} confirmed matching in Zoho")
    return {"ok": True}


@router.post("/store/zoho/pos/{oid}/seen")
def note_seen(oid: int, db: Session = Depends(get_db), user: models.User = ZG):
    """Accounts have read what the purchaser changed (Zoho already matches, or it is not in Zoho yet)."""
    o = db.get(models.PurchaseOrder, oid)
    if not o:
        raise HTTPException(status_code=404, detail="No such LPO.")
    _seen(o); db.commit()
    M.log_action(db, user.id, "zoho_pos", f"{o.ref}: change noted by accounts")
    return {"ok": True}


def bell(db):
    """One notice per LPO changed or cancelled that accounts have not seen yet - new id for each change."""
    out = []
    for o in db.query(models.PurchaseOrder).filter(models.PurchaseOrder.acc_note != "", models.PurchaseOrder.acc_note.isnot(None)).all():
        d = note_of(o)
        if not d.get("items") or d.get("seen", True):
            continue
        last = d["items"][-1]
        cancel = last.get("kind") == "cancel"
        lines = [x for it in d["items"] for x in (it.get("changes") or [])][:8]
        if last.get("zoho"):
            lines.append(last["zoho"])
        hand = (o.zoho_status or "") == "changed" or (o.status == "cancelled" and bool(o.zoho_err))
        out.append({"id": f"lpochg-{o.id}-{d.get('seq', 1)}", "kind": "zoho", "screen": "zoho", "lpo_change": True,
                    "lpo_id": o.id, "ref": o.ref, "cancelled": cancel, "by_hand": hand,
                    "changes": [x for it in d["items"] for x in (it.get("changes") or [])][:30], "zoho_result": last.get("zoho") or "",
                    "title": f"{o.ref} {'cancelled' if cancel else 'edited'} by {last.get('who') or 'purchasing'}"
                             + (f" - {o.supplier_name}" if o.supplier_name else ""),
                    "detail": "; ".join(lines)[:300], "lines": lines,
                    "when": M._dubai_today().isoformat(), "level": "warn"})
    return out


# LPOs Praveen asked to delete everywhere (made on the admin login on
# 9 Oct, with the material requests made alongside them).
DROP = {"IC/LPO/20260125": "Abc International Tr LLC", "IC/LPO/20260126": "Absolute Royal Technologies"}


def drop_admin_lpos(db):
    """Each start until done: delete those LPOs, their lines and the
    material request each was made with. One still in Zoho is left until
    it is reversed on Sent to Zoho (that deletes it in Zoho)."""
    if db.query(models.Setting).filter(models.Setting.key == "drop_lpo_0125_0126").first():
        return []
    gone, wait = [], []
    for ref, sup in DROP.items():
        o = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.ref == ref).first()
        if not o:
            gone.append(ref); continue
        if (o.supplier_name or "") != sup:
            gone.append(ref); continue                     # not the order meant - never touch it
        if (o.zoho_id or "").strip():
            wait.append(ref); continue
        delete_lpo(db, o, None, "made by mistake on the admin login, deleted as asked")
        gone.append(ref)
    if not wait:
        db.add(models.Setting(key="drop_lpo_0125_0126", value="1")); db.commit()
    return wait

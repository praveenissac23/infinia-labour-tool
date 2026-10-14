"""Suppliers: the portal is the master list, Zoho gets a copy.

Each portal supplier is linked to one Zoho vendor. A name that matches a
Zoho vendor exactly (ignoring case, punctuation and LLC / Trading) is
linked by itself; anything else is linked to the right Zoho vendor by
the chief accountant, or created in Zoho - never guessed, so Zoho does
not fill up with near-duplicates. Once linked, a change made here (name,
TRN, address, phone, email) is copied to Zoho when it is saved.
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session

import main as M
import models
from database import get_db

router = APIRouter()
ZG = Depends(M.require_any_screen("accounts_zoho"))


def _vendors(db):
    import zohoapi as Z
    out, page = [], 1
    while page < 30:
        d = Z.call(db, "GET", "contacts", {"contact_type": "vendor", "per_page": 200, "page": page})
        out += [{"id": c["contact_id"], "name": c.get("contact_name") or ""} for c in d.get("contacts", [])]
        if not d.get("page_context", {}).get("has_more_page"):
            break
        page += 1
    return out


def _body(sup):
    b = {"contact_name": sup.name, "company_name": sup.name,
         "tax_treatment": "vat_registered" if (sup.trn or "").strip() else "vat_not_registered",
         "billing_address": {"address": (sup.address or "")[:500], "phone": sup.phone or ""}}
    trn = "".join(ch for ch in (sup.trn or "") if ch.isdigit())
    if len(trn) == 15:
        b["tax_reg_no"] = trn
    return b


def copy_to_zoho(db, sup):
    """Copy one linked supplier's details to Zoho. Errors are kept on the
    supplier, never raised into the supplier screen's own save."""
    import zohoapi as Z
    if not sup.zoho_id or not Z.connected(db):
        return False
    try:
        with Z.about("supplier", sup.id, sup.name or ""):
            Z.call(db, "PUT", f"contacts/{sup.zoho_id}", body=_body(sup))
        sup.zoho_err = ""
    except Exception as e:
        sup.zoho_err = (getattr(e, "msg", None) or str(e))[:300]
    db.commit()
    return not sup.zoho_err


@router.get("/store/zoho/suppliers")
def listing(match: int = 0, db: Session = Depends(get_db), user: models.User = ZG):
    """Every active supplier and where it stands in Zoho. With match=1
    the Zoho vendors are read and exact names are linked."""
    import zohoapi as Z
    sups = db.query(models.Supplier).filter(models.Supplier.active == True).order_by(models.Supplier.name).all()  # noqa: E712
    cands = {}
    if match and Z.connected(db):
        vend = _vendors(db)
        by_key = {}
        for v in vend:
            by_key.setdefault(M._supplier_key(v["name"]), []).append(v)
        taken = {s.zoho_id for s in sups if s.zoho_id}
        for s in sups:
            if s.zoho_id:
                continue
            hits = [v for v in by_key.get(s.name_key, []) if v["id"] not in taken]
            if len(hits) == 1:
                s.zoho_id = hits[0]["id"]; taken.add(s.zoho_id)
            else:
                words = [w for w in s.name_key.split() if len(w) > 2][:2]
                cands[s.id] = [v for v in vend if words and all(w in M._supplier_key(v["name"]) for w in words)][:6]
        db.commit()
    rows = [{"id": s.id, "name": s.name, "trn": s.trn or "", "zoho_id": s.zoho_id or "", "err": s.zoho_err or "",
             "candidates": cands.get(s.id, [])} for s in sups]
    return {"rows": rows, "linked": sum(1 for r in rows if r["zoho_id"]), "connected": Z.connected(db)}


@router.post("/store/zoho/suppliers/{sid}/link")
def link(sid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = ZG):
    sup = db.get(models.Supplier, sid)
    zid = str(payload.get("zoho_id") or "").strip()
    if not sup or not zid:
        raise HTTPException(status_code=400, detail="Pick the Zoho vendor to link.")
    if db.query(models.Supplier).filter(models.Supplier.zoho_id == zid, models.Supplier.id != sid).first():
        raise HTTPException(status_code=400, detail="That Zoho vendor is already linked to another supplier.")
    sup.zoho_id, sup.zoho_err = zid, ""
    db.commit()
    M.log_action(db, user.id, "zoho_supplier", f"{sup.name} linked to Zoho vendor {zid}")
    return {"ok": True, "copied": copy_to_zoho(db, sup)}


@router.post("/store/zoho/suppliers/{sid}/create")
def create(sid: int, db: Session = Depends(get_db), user: models.User = ZG):
    import zohoapi as Z
    sup = db.get(models.Supplier, sid)
    if not sup:
        raise HTTPException(status_code=404, detail="That supplier is no longer there.")
    if sup.zoho_id:
        raise HTTPException(status_code=400, detail="It is already linked to a Zoho vendor.")
    if not Z.connected(db):
        raise HTTPException(status_code=400, detail="Zoho is not connected yet.")
    body = _body(sup); body["contact_type"] = "vendor"
    if sup.email or sup.contact_person:
        body["contact_persons"] = [{"first_name": (sup.contact_person or sup.name)[:100], "email": sup.email or "",
                                    "phone": sup.phone or "", "is_primary_contact": True}]
    try:
        with Z.about("supplier", sup.id, sup.name or "", user.id):
            d = Z.call(db, "POST", "contacts", body=body)
    except Z.ZohoError as e:
        raise HTTPException(status_code=400, detail=f"Zoho refused: {e.msg}")
    sup.zoho_id, sup.zoho_err = d["contact"]["contact_id"], ""
    db.commit()
    M.log_action(db, user.id, "zoho_supplier", f"{sup.name} created in Zoho")
    return {"ok": True}


@router.post("/store/zoho/suppliers/{sid}/unlink")
def unlink(sid: int, db: Session = Depends(get_db), user: models.User = ZG):
    sup = db.get(models.Supplier, sid)
    if sup:
        sup.zoho_id, sup.zoho_err = "", ""
        db.commit()
    return {"ok": True}

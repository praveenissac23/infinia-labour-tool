"""Subcontractor payment certificates made inside the portal - no attachments.

    Item schedule  - set up once per subcontract (pasted from the agreement BOQ):
                     bill (B1 Electrical ...), item no., description, type/ref,
                     qty, unit, rate, amount, and how it is measured:
                       pct  - % done of the line amount (lump sum, MEP)
                       size - W x H measured, a deduction, then % done (aluminium)
                       qty  - quantity done x rate (re-measurable, manpower)
                     Approved variations are lines too (is_var, "Var 01" / LPO no.).
    Monthly sheet  - each certificate holds one line per item with the figures
                     TO DATE; a new certificate starts as a copy of the last one,
                     so only the lines that moved are touched.
    Deductions     - lines (material / manpower / plant / other) entered on the
                     certificate where they arise and counted on every later one
                     (the certificate works on figures to date).
    Sign-off       - prepared (QS), checked, reviewed (Accounts), approved, and
                     "verified at site": a click each, name and date printed.
    Print          - the certificate page, Appendix A (work & variations, the
                     bill summary), B (previous payments), C (deductions) and
                     the subcontractor's bill, made fresh each time - nothing stored.
"""
import io
import json
import re
from datetime import date

from fastapi import Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy import Boolean, Column, Date, Float, Integer, String, Text
from sqlalchemy.orm import Session

import auth
import estimation as E
import models
from database import Base, get_db

r2 = E.r2
router = E.router
VIEW = E.VIEW
PAYER = E.PAYER
MEASURES = ("pct", "size", "qty")
DED_CATS = ("Material", "Manpower", "Plant & Equipment", "Other")
INFINIA = ["M/s. INFINIA CONTRACTING LLC", "P.O Box: 85567", "Tel: 043996039", "Dubai, UAE", "TRN No.: 100602393900003"]


class EstSubItem(Base):
    """One line of a subcontract's schedule (Appendix A)."""
    __tablename__ = "est_sub_items"
    id = Column(Integer, primary_key=True)
    sub_id = Column(Integer, nullable=False, index=True)
    sort = Column(Integer, default=0)
    bill = Column(String, default="")           # B1 - kept short; the bill's name is bill_title
    bill_title = Column(String, default="")     # Electrical Works
    section = Column(String, default="")        # a heading inside the bill (SUPERSTRUCTURE WORKS)
    no = Column(String, default="")             # item no. as in the agreement
    description = Column(Text, default="")
    ref = Column(String, default="")            # type / mark: SD1, W3, Sky light
    qty = Column(Float, default=0.0)
    unit = Column(String, default="")
    rate = Column(Float, default=0.0)
    amount = Column(Float, default=0.0)         # qty x rate, or the lump sum
    measure = Column(String, default="pct")     # pct | size | qty
    is_var = Column(Boolean, default=False)     # a variation / additional scope
    var_ref = Column(String, default="")        # Var 01, IC/LPO/9103374
    locals().update(E._audit())


class EstPCLine(Base):
    """An item's figures TO DATE on one certificate."""
    __tablename__ = "est_pc_lines"
    id = Column(Integer, primary_key=True)
    pc_id = Column(Integer, nullable=False, index=True)
    item_id = Column(Integer, nullable=False, index=True)
    pct = Column(Float, default=0.0)            # % done to date (pct, size)
    qty = Column(Float, default=0.0)            # quantity done to date (qty)
    claimed_qty = Column(Float, default=0.0)    # what the subcontractor claimed (qty) - shown, not paid
    w = Column(Float, default=0.0)              # measured width / height (size)
    h = Column(Float, default=0.0)
    deduct = Column(Float, default=0.0)         # taken off the line (short size, damage ...)
    remark = Column(String, default="")


class EstPCDeduct(Base):
    """A deduction line (Appendix C), counted from its certificate onwards."""
    __tablename__ = "est_pc_deducts"
    id = Column(Integer, primary_key=True)
    sub_id = Column(Integer, nullable=False, index=True)
    pc_id = Column(Integer, nullable=False, index=True)
    cat = Column(String, default="Other")
    on_date = Column(Date, nullable=True)
    description = Column(String, default="")
    qty = Column(Float, default=0.0)
    unit = Column(String, default="")
    rate = Column(Float, default=0.0)
    amount = Column(Float, default=0.0)
    counted = Column(Boolean, default=True)     # False: shown on the certificate but not taken (management decision)
    note = Column(String, default="")


E.TABLES += [EstSubItem, EstPCLine, EstPCDeduct]


# ---- money ----------------------------------------------------------------------------------

def item_amount(it):
    """The line amount as the agreement prints it; qty x rate only when no amount is given
    (3 x 6,539.45 is 19,618.34 on the 910 agreement - its rate has more decimals)."""
    if it.amount:
        return r2(it.amount)
    return r2((it.qty or 0) * (it.rate or 0))


def line_amount(it, ln):
    """What a line is worth to date on a certificate."""
    if ln is None:
        return 0.0
    ded = ln.deduct or 0
    if it.measure == "qty":            # quantity x rate; a stage % (70% = first coat done) when given
        stage = (ln.pct or 0) / 100.0 if (ln.pct or 0) else 1.0
        return r2((ln.qty or 0) * (it.rate or 0) * stage - ded)
    return r2(((it.amount or 0) - ded) * (ln.pct or 0) / 100.0)


def _f(v, nd=4):
    try:
        return round(float(str(v).replace(",", "").replace("%", "").strip() or 0), nd)
    except (TypeError, ValueError):
        return 0.0


def _d(v):
    if not v:
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _pcs(db, sid):
    return sorted(db.query(E.EstSubPC).filter(E.EstSubPC.sub_id == sid).all(), key=lambda p: (p.seq or 0, p.id))


def _locked_upto(pcs):
    return max([i for i, p in enumerate(pcs) if (p.status or "") in E.LOCKED_STATUS] or [-1])


def refresh_sub(db, sid):
    """Work, variations and deductions to date on every open certificate, from
    their lines; then advance recovery / retention and the chain. A paid
    certificate (and the ones before it) never moves."""
    pcs = _pcs(db, sid)
    items = db.query(EstSubItem).filter(EstSubItem.sub_id == sid).all()
    deds = db.query(EstPCDeduct).filter(EstPCDeduct.sub_id == sid).all()
    if (items or deds) and pcs:
        by_item = {i.id: i for i in items}
        seq_of = {p.id: (p.seq or 0) for p in pcs}
        lines = {}
        for ln in db.query(EstPCLine).filter(EstPCLine.pc_id.in_([p.id for p in pcs])).all():
            lines.setdefault(ln.pc_id, []).append(ln)
        first_ded = min([seq_of.get(d.pc_id, 0) for d in deds] or [10 ** 9])
        for i, pc in enumerate(pcs):
            if i <= _locked_upto(pcs):
                continue
            mine = lines.get(pc.id)
            if mine:          # a certificate typed before the schedule was set up keeps its typed figures
                work = var = 0.0
                for ln in mine:
                    it = by_item.get(ln.item_id)
                    if not it:
                        continue
                    if it.is_var:
                        var += line_amount(it, ln)
                    else:
                        work += line_amount(it, ln)
                pc.work_cum, pc.var_cum = r2(work), r2(var)
            if deds and (pc.seq or 0) >= first_ded:
                pc.other_cum = r2(sum(d.amount or 0 for d in deds if d.counted and seq_of.get(d.pc_id, 10 ** 9) <= (pc.seq or 0)))
                pc.other_note = ""
        db.flush()
    E._refill_sub(db, sid)


def carry_over(db, pc):
    """A new certificate starts with the last one's lines (figures to date)."""
    prev = [p for p in _pcs(db, pc.sub_id) if p.id != pc.id and ((p.seq or 0), p.id) < ((pc.seq or 0), pc.id)]
    if not prev:
        return
    for ln in db.query(EstPCLine).filter(EstPCLine.pc_id == prev[-1].id).all():
        db.add(EstPCLine(pc_id=pc.id, item_id=ln.item_id, pct=ln.pct, qty=ln.qty, claimed_qty=ln.claimed_qty, w=ln.w, h=ln.h,
                         deduct=ln.deduct, remark=ln.remark))
    db.flush()
    refresh_sub(db, pc.sub_id)


def drop_pc(db, pc_id):
    db.query(EstPCLine).filter(EstPCLine.pc_id == pc_id).delete(synchronize_session=False)
    db.query(EstPCDeduct).filter(EstPCDeduct.pc_id == pc_id).delete(synchronize_session=False)


def drop_sub(db, sid):
    ids = [p.id for p in db.query(E.EstSubPC.id).filter(E.EstSubPC.sub_id == sid).all()]
    if ids:
        db.query(EstPCLine).filter(EstPCLine.pc_id.in_(ids)).delete(synchronize_session=False)
    db.query(EstPCDeduct).filter(EstPCDeduct.sub_id == sid).delete(synchronize_session=False)
    db.query(EstSubItem).filter(EstSubItem.sub_id == sid).delete(synchronize_session=False)


# ---- the item schedule -------------------------------------------------------------------------

def _item_out(it, used=False):
    return {"id": it.id, "sort": it.sort, "bill": it.bill or "", "bill_title": it.bill_title or "", "section": it.section or "",
            "no": it.no or "", "description": it.description or "", "ref": it.ref or "", "qty": it.qty or 0, "unit": it.unit or "",
            "rate": it.rate or 0, "amount": r2(it.amount), "measure": it.measure or "pct", "is_var": bool(it.is_var),
            "var_ref": it.var_ref or "", "used": used}


def _items(db, sid):
    return sorted(db.query(EstSubItem).filter(EstSubItem.sub_id == sid).all(), key=lambda i: (bool(i.is_var), i.sort or 0, i.id))


@router.get("/store/est/subs/{sid}/items")
def get_items(sid: int, db: Session = Depends(get_db), user: models.User = VIEW):
    s = E._sub_of(db, sid)
    items = _items(db, sid)
    used = {x.item_id for x in db.query(EstPCLine.item_id).filter(EstPCLine.item_id.in_([i.id for i in items])).all()} if items else set()
    return {"sub": {"id": s.id, "name": s.name, "scope": s.scope, "value": r2(s.value), "contract_type": s.contract_type or ""},
            "items": [_item_out(i, i.id in used) for i in items],
            "total": r2(sum(i.amount or 0 for i in items if not i.is_var)), "var_total": r2(sum(i.amount or 0 for i in items if i.is_var))}


UNITS = {"no", "nos", "no's", "no.", "nr", "m", "lm", "l.m", "rm", "m2", "sqm", "m²", "m3", "cum", "m³", "ls", "l.s", "item", "kg",
         "ton", "tons", "set", "sets", "day", "days", "month", "months", "hr", "hrs", "trip", "trips", "lot", "pcs", "pc", "unit", "units"}


def parse_items(text):
    """Lines copied from the agreement BOQ in Excel (tab-separated). Gives
    [{no, description, ref, qty, unit, rate, amount, section}]. A line with no
    figures in capitals is a heading; one in lower case continues the item above."""
    out, section = [], ""
    for raw in str(text or "").splitlines():
        cells = [c.strip() for c in raw.split("\t")]
        if not any(cells):
            continue
        nums = []
        for c in cells:
            s = c.replace(",", "").replace("AED", "").strip()
            if s.endswith("%"):
                nums.append("pct")
                continue
            try:
                nums.append(float(s) if s not in ("", "-") else None)
            except ValueError:
                nums.append(None)
        texts = [(len(c), i) for i, c in enumerate(cells) if c and nums[i] is None]
        if not texts:
            continue
        di = max(texts)[1]
        desc = cells[di]
        after = [nums[i] for i in range(di + 1, len(cells)) if isinstance(nums[i], float)]
        if not after:
            if desc.upper() == desc and len(desc) < 90:
                section = desc[:120]
            elif out:
                out[-1]["description"] = (out[-1]["description"] + "\n" + desc).strip()
            continue
        shorts = [cells[i] for i in range(di + 1, len(cells)) if cells[i] and nums[i] is None]
        unit = next((x for x in reversed(shorts) if x.lower().rstrip(".") in UNITS or x.lower() in UNITS), "")
        ref = next((x for x in shorts if x != unit), "")
        no = ""
        for i in range(0, di):
            if cells[i]:
                no = cells[i]
                break
        qty = rate = amount = 0.0
        if len(after) >= 3:
            qty, rate, amount = after[0], after[1], after[2]
        elif len(after) == 2:
            qty, rate = after
            amount = qty * rate
        else:
            amount = after[0]
            qty, unit = (1.0, unit or "LS")
            rate = amount
        out.append({"no": no[:20], "description": desc[:2000], "ref": ref[:40], "qty": round(qty, 4), "unit": unit[:12],
                    "rate": round(rate, 4), "amount": r2(amount), "section": section})
    return out


@router.post("/store/est/subs/{sid}/items/paste")
def paste_items(sid: int, data: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    E._sub_of(db, sid)
    rows = parse_items(data.get("text"))
    if not rows:
        raise HTTPException(400, "Nothing to add - copy the lines from Excel (item, description, qty, unit, rate, amount) and paste them here.")
    measure = data.get("measure") if data.get("measure") in MEASURES else "pct"
    is_var = bool(data.get("is_var"))
    base = max([i.sort or 0 for i in db.query(EstSubItem).filter(EstSubItem.sub_id == sid).all()] or [0])
    for n, x in enumerate(rows):
        it = EstSubItem(sub_id=sid, sort=base + n + 1, bill=str(data.get("bill") or "")[:20], bill_title=str(data.get("bill_title") or "")[:120],
                        measure=measure, is_var=is_var, var_ref=str(data.get("var_ref") or "")[:60], created_by=user.id, **x)
        it.amount = item_amount(it)
        db.add(it)
    db.flush()
    refresh_sub(db, sid)
    db.commit()
    return {"added": len(rows), "total": r2(sum(x["amount"] for x in rows))}


@router.post("/store/est/subs/{sid}/items/import")
async def import_items(sid: int, file: UploadFile = File(...), save: int = Form(0), mode: str = Form("replace"),
                       db: Session = Depends(get_db), user: models.User = VIEW):
    """The item schedule out of an Excel workbook - the agreement BOQ or any payment certificate
    (Appendix A / Bill sheets). Read in memory, never stored. The first call shows every line and
    checks each sheet against its own total row; save=1 puts the lines in (mode replace | add)."""
    import est_itemimport
    s = E._sub_of(db, sid)
    data = await file.read()
    if len(data) > E.MAX_FILE:
        raise HTTPException(413, "That file is over 25 MB.")
    if data[:2] != b"PK":
        raise HTTPException(400, "That is not an Excel workbook (.xlsx). Save it as .xlsx and upload it again.")
    try:
        r = est_itemimport.read_schedule(data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception:
        raise HTTPException(400, "That workbook could not be read. Upload the agreement BOQ or a payment certificate as .xlsx.")
    have = db.query(EstSubItem).filter(EstSubItem.sub_id == sid).order_by(EstSubItem.sort, EstSubItem.id).all()
    used = {x[0] for x in db.query(EstPCLine.item_id).filter(EstPCLine.item_id.in_([i.id for i in have] or [-1])).all()}
    out = {k: r[k] for k in ("sheets", "notes", "contract", "certified", "all_checked")}
    out.update({"lines": len(r["items"]), "existing": len(have), "used": len(used), "value": r2(s.value or 0), "file": file.filename or "",
                "items": [{k: x[k] for k in ("bill", "bill_title", "section", "no", "description", "qty", "unit", "rate", "amount", "measure",
                                            "words", "done_pct", "done_qty", "certified", "rate_missing")} for x in r["items"]]})
    if not save:
        return out
    if mode not in ("replace", "add"):
        raise HTTPException(400, "Replace or add?")
    if mode == "replace" and have:
        if used:
            raise HTTPException(400, f"{len(used)} line(s) of the present schedule are already on certificates - they can't be replaced. "
                                     "Add these lines instead, or change the schedule on Edit schedule.")
        for i in have:
            db.delete(i)
        db.flush()
        base = 0
    else:
        base = max([i.sort or 0 for i in have] or [0])
    for n, x in enumerate(r["items"], 1):
        it = EstSubItem(sub_id=sid, sort=base + n, bill=x["bill"][:20], bill_title=x["bill_title"][:120], section=x["section"][:200], no=x["no"][:20],
                        description=x["description"], ref=x["words"][:120], qty=x["qty"], unit=x["unit"][:20], rate=x["rate"], amount=x["amount"],
                        measure=x["measure"], is_var=False, created_by=user.id)
        db.add(it)
    db.flush()
    refresh_sub(db, sid)
    db.commit()
    out.update({"saved": len(r["items"]), "mode": mode})
    return out


@router.put("/store/est/subs/{sid}/items")
def save_items(sid: int, data: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    """The whole schedule as edited on screen: changed lines saved, new ones
    added, the ones left out removed (not when a paid certificate uses them)."""
    E._sub_of(db, sid)
    have = {i.id: i for i in db.query(EstSubItem).filter(EstSubItem.sub_id == sid).all()}
    keep = set()
    pcs = _pcs(db, sid)
    locked_ids = [p.id for i, p in enumerate(pcs) if i <= _locked_upto(pcs)]
    for n, x in enumerate(data.get("items") or []):
        it = have.get(x.get("id")) if x.get("id") else None
        if it is None:
            it = EstSubItem(sub_id=sid, created_by=user.id)
            db.add(it)
        it.sort = n + 1
        for k in ("bill", "bill_title", "section", "no", "description", "ref", "unit", "var_ref"):
            setattr(it, k, str(x.get(k) or "")[:2000 if k == "description" else 120])
        for k in ("qty", "rate", "amount"):
            setattr(it, k, _f(x.get(k)))
        it.measure = x.get("measure") if x.get("measure") in MEASURES else "pct"
        it.is_var = bool(x.get("is_var"))
        if not it.description.strip():
            raise HTTPException(400, f"Line {n + 1} has no description.")
        # A paid certificate keeps its stored work figure; a changed rate counts from the next open certificate.
        it.amount = item_amount(it)
        if it.id:
            keep.add(it.id)
    for iid, it in have.items():
        if iid in keep:
            continue
        if locked_ids and db.query(EstPCLine).filter(EstPCLine.item_id == iid, EstPCLine.pc_id.in_(locked_ids)).first() and user.role != "admin":
            raise HTTPException(400, f"'{(it.description or '')[:40]}' is on a paid certificate - it can't be removed.")
        db.query(EstPCLine).filter(EstPCLine.item_id == iid).delete(synchronize_session=False)
        db.delete(it)
    db.flush()
    refresh_sub(db, sid)
    db.commit()
    return get_items(sid, db, user)


# ---- the monthly sheet -------------------------------------------------------------------------

def _is_locked(pcs, pc):
    i = next(n for n, p in enumerate(pcs) if p.id == pc.id)
    return i <= _locked_upto(pcs)


def _who(user):
    return (user.full_name or user.username or "").strip()


def _can(user, role):
    perms = set(E.M.effective_permissions(user))
    if user.role == "admin":
        return True
    if role == "rev":
        return "accounts_bank" in perms
    if role == "app":
        return False
    return E.RIGHT in perms


def sheet(db, pc, user=None):
    s = E._sub_of(db, pc.sub_id)
    p = E._project(db, s.project_id)
    pcs = _pcs(db, s.id)
    items = _items(db, s.id)
    idx = next(n for n, x in enumerate(pcs) if x.id == pc.id)
    prev = pcs[idx - 1] if idx else None
    mine = {ln.item_id: ln for ln in db.query(EstPCLine).filter(EstPCLine.pc_id == pc.id).all()}
    before = {ln.item_id: ln for ln in db.query(EstPCLine).filter(EstPCLine.pc_id == prev.id).all()} if prev else {}
    seq_of = {x.id: x.seq for x in pcs}
    deds = [d for d in db.query(EstPCDeduct).filter(EstPCDeduct.sub_id == s.id).all() if (seq_of.get(d.pc_id) or 0) <= (pc.seq or 0)]
    vos = db.query(E.EstSubVO).filter(E.EstSubVO.sub_id == s.id).all()
    calc = {c["id"]: c for c in E.chain(pcs, s.adv_pct, s.ret_pct, s.vat_pct)}
    ln_out = lambda it, ln: None if ln is None else {"pct": ln.pct or 0, "qty": ln.qty or 0, "claimed_qty": ln.claimed_qty or 0, "w": ln.w or 0,
                                                       "h": ln.h or 0, "deduct": ln.deduct or 0, "remark": ln.remark or "", "amount": line_amount(it, ln)}
    sup = db.query(models.Supplier).get(s.supplier_id) if s.supplier_id else None
    out = {
        "pc": E._plain(pc, E.KINDS["subpcs"][2]), "calc": calc.get(pc.id), "prev_calc": calc.get(prev.id) if prev else None,
        "pcs": [dict(E._plain(x, E.KINDS["subpcs"][2]), **calc.get(x.id, {})) for x in pcs],
        "sub": dict(E._plain(s, E.KINDS["subs"][2]), revised=E.sub_revised(s, vos), vo_total=r2(sum(v.amount or 0 for v in vos)),
                    sup={"address": sup.address if sup else "", "phone": sup.phone if sup else "", "trn": sup.trn if sup else ""}),
        "project": {"code": p.code, "name": p.name, "client": p.client, "location": p.location},
        "items": [_item_out(i) for i in items],
        "lines": {i.id: ln_out(i, mine.get(i.id)) for i in items if i.id in mine},
        "prev": {i.id: ln_out(i, before.get(i.id)) for i in items if i.id in before},
        "deds": [{"id": d.id, "pc_id": d.pc_id, "pc_seq": seq_of.get(d.pc_id), "mine": d.pc_id == pc.id, "cat": d.cat,
                  "on_date": E._iso(d.on_date), "description": d.description, "qty": d.qty or 0, "unit": d.unit or "", "rate": d.rate or 0,
                  "amount": r2(d.amount), "counted": bool(d.counted), "note": d.note or ""} for d in sorted(deds, key=lambda d: (seq_of.get(d.pc_id) or 0, d.id))],
        "locked": _is_locked(pcs, pc),
    }
    if user is not None:
        out["me"] = {"name": _who(user), "admin": user.role == "admin", "can": {r: _can(user, r) for r in ("site", "prep", "chk", "rev", "app")}}
    return out


@router.get("/store/est/subpcs/{rid}/sheet")
def get_sheet(rid: int, db: Session = Depends(get_db), user: models.User = PAYER):
    pc = db.query(E.EstSubPC).get(rid)
    if not pc:
        raise HTTPException(404, "That certificate is not there any more.")
    return sheet(db, pc, user)


PC_FIELDS = {"measured_on": "d", "inv_ref": "s", "inv_date": "d", "inv_amount": "f", "received": "d", "remarks": "s", "mos_cum": "f",
             "adv_amount": "f", "ret_rel_cum": "f", "adv_auto": "b", "ret_auto": "b", "adv_rec_cum": "f", "ret_cum": "f", "pc_type": "s",
             "inv_lines": "j", "work_cum": "f", "var_cum": "f", "other_cum": "f", "other_note": "s"}


@router.put("/store/est/subpcs/{rid}/sheet")
def put_sheet(rid: int, data: dict = Body(...), db: Session = Depends(get_db), user: models.User = VIEW):
    pc = db.query(E.EstSubPC).get(rid)
    if not pc:
        raise HTTPException(404, "That certificate is not there any more.")
    s = E._sub_of(db, pc.sub_id)
    pcs = _pcs(db, s.id)
    if _is_locked(pcs, pc) and user.role != "admin":
        raise HTTPException(400, "This certificate is paid (or a later one is) - its figures are locked. Ask an admin if it must change.")
    items = {i.id: i for i in db.query(EstSubItem).filter(EstSubItem.sub_id == s.id).all()}
    f = dict(data.get("pc") or {})
    if items:                               # worked out from the lines - never typed
        f.pop("work_cum", None)
        f.pop("var_cum", None)
    if "adv_rec_cum" in f and "adv_auto" not in f:
        f["adv_auto"] = False
    if "ret_cum" in f and "ret_auto" not in f:
        f["ret_auto"] = False
    for k, t in PC_FIELDS.items():
        if k not in f:
            continue
        v = f[k]
        if t == "d":
            v = _d(v)
        elif t == "f":
            v = _f(v)
        elif t == "b":
            v = bool(v)
        elif t == "j":
            v = json.dumps([{"d": str(x.get("d") or "")[:300], "a": _f(x.get("a"))} for x in (v or []) if (x.get("d") or x.get("a"))]) if isinstance(v, list) else str(v or "")
        else:
            v = str(v or "")[:2000]
        setattr(pc, k, v)
    if "lines" in data:
        have = {ln.item_id: ln for ln in db.query(EstPCLine).filter(EstPCLine.pc_id == pc.id).all()}
        for x in data.get("lines") or []:
            iid = int(x.get("item_id") or 0)
            it = items.get(iid)
            if not it:
                continue
            ln = have.get(iid)
            if ln is None:
                ln = EstPCLine(pc_id=pc.id, item_id=iid)
                db.add(ln)
            ln.pct = max(0.0, min(_f(x.get("pct"), 6), 1000.0))
            ln.qty = _f(x.get("qty"))
            ln.claimed_qty = _f(x.get("claimed_qty"))
            ln.w, ln.h = _f(x.get("w")), _f(x.get("h"))
            ln.deduct = _f(x.get("deduct"))
            ln.remark = str(x.get("remark") or "")[:300]
            if ln.pct > 100 and it.measure != "qty":
                raise HTTPException(400, f"Item {it.no or ''} '{(it.description or '')[:40]}': more than 100% done.")
    if "deds" in data:
        db.query(EstPCDeduct).filter(EstPCDeduct.pc_id == pc.id).delete(synchronize_session=False)
        for x in data.get("deds") or []:
            desc = str(x.get("description") or "").strip()
            qty, rate, amt = _f(x.get("qty")), _f(x.get("rate")), _f(x.get("amount"))
            if qty and rate:
                amt = r2(qty * rate)
            if not desc and not amt:
                continue
            cat = x.get("cat") if x.get("cat") in DED_CATS else "Other"
            db.add(EstPCDeduct(sub_id=s.id, pc_id=pc.id, cat=cat, on_date=_d(x.get("on_date")), description=desc[:300], qty=qty,
                               unit=str(x.get("unit") or "")[:12], rate=rate, amount=r2(amt), counted=x.get("counted", True) is not False,
                               note=str(x.get("note") or "")[:300]))
    pc.updated_by = user.id
    db.flush()
    refresh_sub(db, s.id)
    E._check_pc(db, pc)
    db.commit()
    return sheet(db, pc, user)


SIGN = {"site": ("verified_by", "verified_on"), "prep": ("prep_by", "prep_on"), "chk": ("chk_by", "chk_on"),
        "rev": ("rev_by", "rev_on"), "app": ("app_by", "app_on")}


@router.post("/store/est/subpcs/{rid}/sign")
def sign(rid: int, data: dict = Body(...), db: Session = Depends(get_db), user: models.User = PAYER):
    """One click: prepared / checked / reviewed by Accounts / approved / verified
    at site - the name and today's date go on the certificate."""
    pc = db.query(E.EstSubPC).get(rid)
    if not pc:
        raise HTTPException(404, "That certificate is not there any more.")
    role = data.get("role")
    if role not in SIGN:
        raise HTTPException(400, "Unknown sign-off.")
    if not _can(user, role):
        raise HTTPException(403, {"rev": "Only Accounts can sign as reviewed.", "app": "Only the manager (admin) approves."}.get(role, "Not allowed."))
    by, on = SIGN[role]
    if data.get("undo"):
        if getattr(pc, by) and getattr(pc, by) != _who(user) and user.role != "admin":
            raise HTTPException(400, f"Signed by {getattr(pc, by)} - only they or an admin can take it off.")
        setattr(pc, by, "")
        setattr(pc, on, None)
    else:
        if role in ("chk", "rev", "app") and not pc.prep_by:
            raise HTTPException(400, "The QS signs it as prepared first.")
        setattr(pc, by, _who(user))
        setattr(pc, on, E.today())
    db.commit()
    return sheet(db, pc, user)


# ---- the certificate on paper --------------------------------------------------------------------

def _dt(d):
    return d.strftime("%d-%b-%Y") if d else ""


def _m(v, dash=True):
    v = r2(v)
    if not v and dash:
        return "-"
    return f"({abs(v):,.2f})" if v < 0 else f"{v:,.2f}"


def _pc_ref(p, s, pc):
    words = re.findall(r"[A-Za-z]+", s.scope or "") or re.findall(r"[A-Za-z]+", s.trade or "") or ["Works"]
    tag = words[0]                          # IC/910-PC05-Aluminium/26
    yy = (pc.issued or pc.certified_on or E.today()).strftime("%y")
    return f"IC/{p.code}-PC{(pc.seq or 0):02d}-{tag.title() if tag.islower() else tag}/{yy}"


def build_doc(db, pc):
    """Everything the certificate prints, worked out once for both the preview and the PDF."""
    sh = sheet(db, pc)
    s = E._sub_of(db, pc.sub_id)
    p = E._project(db, s.project_id)
    c = sh["calc"]
    pcs = _pcs(db, s.id)
    calc = {x["id"]: x for x in sh["pcs"]}
    prev = [x for x in pcs if ((x.seq or 0), x.id) < ((pc.seq or 0), pc.id)]
    adv_prev = r2(sum(calc[x.id]["this"] for x in prev if x.pc_type == "Advance"))
    rest = [x for x in prev if x.pc_type != "Advance"]
    rest_amt = r2(sum(calc[x.id]["this"] for x in rest))
    e_lines = []
    if adv_prev:
        a = next(x for x in prev if x.pc_type == "Advance")
        e_lines.append((f"Advance payment PC {(a.seq or 0):02d}", adv_prev))
    if rest:
        lo, hi = rest[0].seq or 0, rest[-1].seq or 0
        e_lines.append((f"IPC - {lo:02d}" if lo == hi else f"IPC - {lo:02d} to IPC - {hi:02d}", rest_amt))
    deds = [d for d in sh["deds"]]
    cats = {k: r2(sum(d["amount"] for d in deds if d["counted"] and d["cat"] == k)) for k in DED_CATS}
    typed_other = r2(pc.other_cum) if not deds else 0.0
    work, var = r2(c["work"]), r2(c["var"])
    total_exec = r2(work + var)
    adv_paid = r2(c["adv_paid_cum"])
    ded_total = r2((pc.adv_rec_cum or 0) + (pc.ret_cum or 0) + (sum(cats.values()) if deds else typed_other))
    items = sh["items"]
    lines, before = sh["lines"], sh["prev"]

    def rows_for(group):
        out = []
        for it in group:
            ln, pv = lines.get(it["id"]), before.get(it["id"])
            out.append({"it": it, "ln": ln or {}, "amount": (ln or {}).get("amount", 0.0), "prev": (pv or {}).get("amount", 0.0),
                        "chg": line_changes(ln, pv)})
        return out
    bills = []
    for it in items:
        key = (it["is_var"], it["bill"] if not it["is_var"] else "VAR")
        if not bills or bills[-1]["key"] != key:
            bills.append({"key": key, "bill": it["bill"], "title": ("Variations / additional scope of work" if it["is_var"] else it["bill_title"]), "var": it["is_var"], "items": []})
        bills[-1]["items"].append(it)
    for b in bills:
        b["rows"] = rows_for(b["items"])
        b["contract"] = r2(sum(i["amount"] for i in b["items"]))
        b["cum"] = r2(sum(r["amount"] for r in b["rows"]))
        b["prev"] = r2(sum(r["prev"] for r in b["rows"]))
    hist = []
    for x in prev:
        cx = calc[x.id]
        idx = pcs.index(x)
        before_ret = (pcs[idx - 1].ret_cum or 0) if idx else 0
        hist.append({"name": f"PC {(x.seq or 0):02d}" + (" - Advance" if x.pc_type == "Advance" else ""), "period": _dt(x.measured_on or x.inv_date or x.received) or "-",
                     "cert": _dt(x.issued or x.certified_on) or "-", "amount": cx["this"], "paid": r2(x.paid_amount), "vat": cx["vat"],
                     "ret": r2((x.ret_cum or 0) - before_ret)})
    sup = sh["sub"]["sup"]
    inv_lines = []
    try:
        inv_lines = json.loads(pc.inv_lines or "[]") or []
    except ValueError:
        inv_lines = []
    return {
        "ref": _pc_ref(p, s, pc), "title": "PAYMENT CERTIFICATE", "kind": pc.pc_type or "Interim",
        "head_l": [("Project Name", p.name or ""), ("Client", p.client or ""), ("Scope of work", s.scope or ""),
                   ("Agreement Ref.", (s.agreement or s.lpo or "") + (f"   Date: {_dt(s.agreement_date)}" if s.agreement_date else "")),
                   ("Commencement Date", _dt(s.start_date)),
                   ("Inv. Ref", (pc.inv_ref or "") + (f"   Date: {_dt(pc.inv_date)}" if pc.inv_date else ""))],
        "head_r": [("Project Code", p.code), ("Measurement Date", _dt(pc.measured_on)), ("IPC No.", f"{(pc.seq or 0):02d}"),
                   ("IPC Issued Date", _dt(pc.issued)), ("Inv. Received Date", _dt(pc.received))],
        "main": INFINIA,
        "subc": [f"M/s. {s.name}"] + [x.strip() for x in (sup["address"] or "").splitlines() if x.strip()] +
                ([f"Tel: {sup['phone']}"] if sup["phone"] else []) + ([f"TRN No.: {sup['trn']}"] if sup["trn"] else []),
        "contract": [("Contract Value", f"AED {_m(s.value, False)}" if s.value else (s.contract_type or "Re-measurable based on actual quantities executed")),
                     ("Approved variation", f"AED {_m(sh['sub']['vo_total'], False)}" if sh["sub"]["vo_total"] else "N/A"),
                     ("Rev. Contract Value", f"AED {_m(sh['sub']['revised'], False)}" if s.value else ""),
                     ("Certified Amount", f"AED {_m(total_exec, False)}"), ("Remarks (if any)", pc.remarks or "Nil")],
        "contract_type": s.contract_type or "", "pay_terms": s.pay_terms or "",
        "A": [("Value of Work Executed to Date", _dt(pc.measured_on), work), ("Value of Variations Executed to Date", _dt(pc.measured_on), var)],
        "A_total": total_exec,
        "B": [("Advance Payment", f"{s.adv_pct:g}%" if s.adv_pct else "%", adv_paid)],
        "C": [("Advance payment Recovery", f"{s.adv_pct:g}%" if s.adv_pct else "%", r2(pc.adv_rec_cum)),
              ("Retention", f"{s.ret_pct:g}%" if s.ret_pct else "%", r2(pc.ret_cum)),
              ("Material Supplied by the Main Contractor", "", cats["Material"]),
              ("Manpower Supplied by the Main Contractor", "", cats["Manpower"]),
              ("Plant & Equipment Supplied by the Main Contractor", "", cats["Plant & Equipment"]),
              ("Other deductions" + (f" - {pc.other_note}" if pc.other_note and not deds else ""), "", cats["Other"] if deds else typed_other)],
        "C_total": ded_total,
        "D": [("Retention Release", "", r2(pc.ret_rel_cum))], "mos": r2(pc.mos_cum),
        "E": e_lines, "E_total": r2(c["prev_net"]),
        "net": c["this"], "vat_pct": s.vat_pct or 0, "vat": c["vat"], "payable": c["payable"],
        "sign": [("Prepared By", pc.prep_by, pc.prep_on), ("Checked By", pc.chk_by, pc.chk_on), ("Reviewed By Accounts", pc.rev_by, pc.rev_on),
                 ("Approved By Manager", pc.app_by, pc.app_on), ("Subcontractor", "", None)],
        "verified": (pc.verified_by, pc.verified_on),
        "changed": sum(1 for b in bills for r in b["rows"] if r["chg"]),
        "changed_note": (lambda n: "" if not n else (f"Shaded: the {n} line{'s' if n > 1 else ''} claimed on this certificate (the first one)." if not prev else
                         f"Shaded: the {n} line{'s' if n > 1 else ''} changed since PC {(prev[-1].seq or 0):02d} - claimed by the subcontractor this time. The figure that moved is a shade deeper."))(
                         sum(1 for b in bills for r in b["rows"] if r["chg"])),
        "bills": bills, "multi_bill": len([b for b in bills if not b["var"]]) > 1,
        "hist": hist, "hist_total": {"amount": r2(sum(h["amount"] for h in hist)), "paid": r2(sum(h["paid"] for h in hist)),
                                     "vat": r2(sum(h["vat"] for h in hist)), "ret": r2(sum(h["ret"] for h in hist))},
        "deds": deds, "inv": {"ref": pc.inv_ref or "", "date": _dt(pc.inv_date), "amount": r2(pc.inv_amount), "received": _dt(pc.received), "lines": inv_lines},
        "sub_name": s.name, "pc_seq": pc.seq or 0, "date": _dt(pc.issued or pc.certified_on or E.today()),
    }


def line_changes(ln, pv):
    """What moved on a line since the previous certificate - what the subcontractor claimed this time.
    Empty when the line stands as it did. ("measure", "pct", "deduct", "remark", "amount")"""
    a, b = ln or {}, pv or {}
    g = lambda d, k: float(d.get(k) or 0)
    out = set()
    if any(abs(g(a, k) - g(b, k)) > 1e-9 for k in ("qty", "claimed_qty", "w", "h")):
        out.add("measure")
    if abs(g(a, "pct") - g(b, "pct")) > 1e-9:
        out.add("pct")
    if abs(g(a, "deduct") - g(b, "deduct")) > 1e-9:
        out.add("deduct")
    if (a.get("remark") or "").strip() != (b.get("remark") or "").strip():
        out.add("remark")
    if abs(g(a, "amount") - g(b, "amount")) > 0.004:
        out.add("amount")
    return out


def _cell_measure(r):
    it, ln = r["it"], r["ln"]
    if it["measure"] == "qty":
        return (f"{ln.get('claimed_qty', 0):g}" if ln.get("claimed_qty") else "", f"{ln.get('qty', 0):g}" if ln else "")
    if it["measure"] == "size":
        w, h = ln.get("w") or 0, ln.get("h") or 0
        if w and not h:                       # a length (handrail, skirting): the measure is the length itself
            return (f"{w:g} m", f"{w:g}")
        return (f"{w:g} x {h:g}" if (w or h) else "", f"{r2(w * h):g}" if (w and h) else "")
    return ("", "")


def _pct_txt(r):
    it, ln = r["it"], r["ln"]
    if it["measure"] == "qty":
        return f"{ln.get('pct'):g}%" if ln and ln.get("pct") else ""
    return f"{ln.get('pct', 0):g}%" if ln else "0%"


# -------------------- PDF --------------------

def render_pdf(doc):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, NextPageTemplate, PageBreak, PageTemplate, Paragraph,
                                    Spacer, Table, TableStyle)
    from xml.sax.saxutils import escape as X
    import export_web
    RED = colors.HexColor("#B7322A")
    HEAD = colors.HexColor("#F3F0EC")
    INK2 = colors.HexColor("#2E3238")
    LINE = colors.HexColor("#C9CDD2")
    TINT = colors.HexColor("#F7F2F1")
    MUT = colors.HexColor("#5F656B")
    st = ParagraphStyle("b", fontName="Helvetica", fontSize=7.6, leading=9.2)
    stb = ParagraphStyle("bb", parent=st, fontName="Helvetica-Bold")
    sts = ParagraphStyle("s", parent=st, fontSize=6.8, leading=8.2)
    str_ = ParagraphStyle("r", parent=st, alignment=TA_RIGHT)
    cap_st = ParagraphStyle("cap", parent=stb, keepWithNext=1, fontSize=8.4, leading=10.5)
    P = lambda t, s=st: Paragraph(X(str(t or "")).replace("\n", "<br/>"), s)
    buf = io.BytesIO()
    W, H = A4
    M = 12 * mm

    def deco(c, d):
        c.saveState()
        pw, ph = c._pagesize
        c.setFillColor(RED)
        c.rect(0, ph - 1.2 * mm, pw, 1.2 * mm, stroke=0, fill=1)
        try:
            img = export_web._logo_image(width_mm=34)
            img.drawOn(c, M, ph - 6 * mm - img.drawHeight)
        except Exception:
            pass
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(colors.HexColor("#22262A"))
        c.drawRightString(pw - M, ph - 9 * mm, doc["ref"])
        c.setFont("Helvetica", 7)
        c.setFillColor(MUT)
        c.drawRightString(pw - M, ph - 13 * mm, f"Payment Certificate No.: {doc['pc_seq']:02d}")
        c.setStrokeColor(LINE)
        c.line(M, 10 * mm, pw - M, 10 * mm)
        c.drawString(M, 6.5 * mm, "INFINIA CONTRACTING LLC  |  P.O Box 85567, Dubai, UAE  |  TRN 100602393900003")
        c.drawRightString(pw - M, 6.5 * mm, f"Page {c.getPageNumber()}")
        c.restoreState()
    top = 22 * mm
    d = BaseDocTemplate(buf, pagesize=A4, leftMargin=M, rightMargin=M, topMargin=top, bottomMargin=14 * mm,
                        title=f"{doc['ref']}", author="Infinia Contracting LLC")
    LW, LH = landscape(A4)
    d.addPageTemplates([PageTemplate(id="P", frames=[Frame(M, 14 * mm, W - 2 * M, H - top - 14 * mm, id="fp", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)], onPage=deco, pagesize=A4),
                        PageTemplate(id="L", frames=[Frame(M, 14 * mm, LW - 2 * M, LH - top - 14 * mm, id="fl", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)], onPage=deco, pagesize=landscape(A4))])
    tw = W - 2 * M
    el = []
    title = doc["title"] + ("" if doc["kind"] == "Interim" else f" ({doc['kind'].upper()})")
    el.append(Paragraph(f"<b>{X(title)}</b>", ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=13, alignment=1, spaceAfter=5)))
    # head
    hl, hr = doc["head_l"], doc["head_r"]
    rows = []
    for i in range(max(len(hl), len(hr))):
        a = hl[i] if i < len(hl) else ("", "")
        b = hr[i] if i < len(hr) else ("", "")
        rows.append([P(a[0], stb), P(": " + a[1] if a[0] else ""), P(b[0], stb), P(": " + b[1] if b[0] else "")])
    t = Table(rows, colWidths=[34 * mm, tw - 34 * mm - 32 * mm - 36 * mm, 32 * mm, 36 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5), ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                           ("BOX", (0, 0), (-1, -1), .5, LINE)]))
    el += [t, Spacer(1, 2 * mm)]
    t = Table([[P("Main Contractor Details", stb), P("Subcontractor Details", stb)],
               [P("\n".join(doc["main"])), P("\n".join(doc["subc"]))]], colWidths=[tw / 2, tw / 2])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), TINT), ("BOX", (0, 0), (-1, -1), .5, LINE), ("LINEBEFORE", (1, 0), (1, -1), .5, LINE),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    el += [t, Spacer(1, 2 * mm)]
    terms = ("Contract: " + doc["contract_type"] + "\n" if doc["contract_type"] else "") + (doc["pay_terms"] or "")
    crow = [[P(k, stb), P(v)] for k, v in doc["contract"] if k and v]
    ct = Table(crow, colWidths=[30 * mm, 52 * mm])
    ct.setStyle(TableStyle([("BOTTOMPADDING", (0, 0), (-1, -1), 1.5), ("TOPPADDING", (0, 0), (-1, -1), 1.5)]))
    t = Table([[ct, P("Payment Terms", stb), P(terms, sts)]], colWidths=[84 * mm, 22 * mm, tw - 106 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), .5, LINE), ("LINEBEFORE", (1, 0), (1, -1), .5, LINE)]))
    el += [t, Spacer(1, 2 * mm)]
    # A - E
    body, styles = [], [("FONTSIZE", (0, 0), (-1, -1), 7.6), ("BOX", (0, 0), (-1, -1), .5, LINE), ("ALIGN", (3, 0), (3, -1), "RIGHT"),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6), ("TOPPADDING", (0, 0), (-1, -1), 1.6)]

    def head(letter, txt):
        styles.append(("BACKGROUND", (0, len(body)), (-1, len(body)), TINT))
        styles.append(("FONTNAME", (0, len(body)), (-1, len(body)), "Helvetica-Bold"))
        body.append([letter, txt, "", ""])

    def line(txt, mid, amt, bold=False):
        if bold:
            styles.append(("FONTNAME", (0, len(body)), (-1, len(body)), "Helvetica-Bold"))
        body.append(["", P(txt, stb if bold else st), mid, _m(amt)])
    head("A", "ADD: VALUE OF WORK EXECUTED")
    for a, b, v in doc["A"]:
        line(a, b, v)
    if doc["mos"]:
        line("Material on Site", "", doc["mos"])
    line("Total Value of Work Executed", "", doc["A_total"] + doc["mos"], True)
    head("B", "ADD: ADVANCE PAYMENT")
    for a, b, v in doc["B"]:
        line(a, b, v)
    head("C", "LESS: DEDUCTIONS")
    for a, b, v in doc["C"]:
        line(a, b, v)
    line("Total Deductions", "", doc["C_total"], True)
    head("D", "ADD: ADDITIONS")
    for a, b, v in doc["D"]:
        line(a, b, v)
    head("E", "LESS: PREVIOUSLY CERTIFIED AMOUNT")
    for a, v in doc["E"] or [("Previously certified", 0)]:
        line(a, "", v)
    line("Total Previously Certified Amounts", "", doc["E_total"], True)
    n0 = len(body)
    body.append(["", P("Net Amount Due for Payment (A + B - C + D - E)", stb), "", _m(doc["net"], False)])
    body.append(["", P(f"VAT ({doc['vat_pct']:g}%)", stb), "", _m(doc["vat"], False)])
    body.append(["", P("Total Amount Due for Payment", stb), "", "AED " + _m(doc["payable"], False)])
    styles += [("FONTNAME", (0, n0), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, n0), (-1, n0), .8, colors.black),
               ("BACKGROUND", (0, len(body) - 1), (-1, len(body) - 1), colors.HexColor("#FDF0EE"))]
    t = Table(body, colWidths=[7 * mm, tw - 7 * mm - 30 * mm - 34 * mm, 30 * mm, 34 * mm])
    t.setStyle(TableStyle(styles))
    el += [t, Spacer(1, 3 * mm)]
    sig = [[P(a, stb) for a, _, _ in doc["sign"]],
           [P(("Name: " + n) if n else "Name:") for _, n, _ in doc["sign"]],
           [P(("Date: " + _dt(o)) if o else "Date:") for _, _, o in doc["sign"]],
           [P("signed in the portal" if n else "Sign:", sts) for _, n, _ in doc["sign"]]]
    t = Table(sig, colWidths=[tw / 5] * 5)
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), .5, LINE), ("INNERGRID", (0, 0), (-1, -1), .3, LINE), ("BACKGROUND", (0, 0), (-1, 0), TINT),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    el.append(KeepTogether([t]))
    # Appendix A
    if doc["bills"]:
        el += [NextPageTemplate("L"), PageBreak()]
        lw = LW - 2 * M
        el.append(Paragraph("<b>Appendix - A &nbsp; Value of Work done &amp; Variations</b>", ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=10, spaceAfter=4)))
        if doc["changed_note"]:
            el.append(Paragraph(f'<font backColor="#FDF1C7">&nbsp;&nbsp;&nbsp;</font>&nbsp; {X(doc["changed_note"])}',
                                ParagraphStyle("mv", fontName="Helvetica", fontSize=7.5, textColor=colors.HexColor("#6B5A1E"), spaceAfter=4)))
        if doc["multi_bill"]:
            sm = [["Bill", "Description", "Contract (AED)", "Previous %", "This %", "To date %", "Previous (AED)", "This (AED)", "To date (AED)"]]
            for b in [b for b in doc["bills"] if not b["var"]]:
                pc_ = lambda v: f"{(100 * v / b['contract']) if b['contract'] else 0:.2f}%"
                sm.append([b["bill"], P(b["title"]), _m(b["contract"]), pc_(b["prev"]), pc_(b["cum"] - b["prev"]), pc_(b["cum"]),
                           _m(b["prev"]), _m(b["cum"] - b["prev"]), _m(b["cum"])])
            bb = [b for b in doc["bills"] if not b["var"]]
            tc = sum(b["contract"] for b in bb)
            tp, tcum = sum(b["prev"] for b in bb), sum(b["cum"] for b in bb)
            sm.append(["", "TOTAL", _m(tc), f"{100 * tp / tc if tc else 0:.2f}%", f"{100 * (tcum - tp) / tc if tc else 0:.2f}%",
                       f"{100 * tcum / tc if tc else 0:.2f}%", _m(tp), _m(tcum - tp), _m(tcum)])
            t = Table(sm, colWidths=[14 * mm, lw - 14 * mm - 7 * 30 * mm] + [30 * mm] * 7, repeatRows=1)
            t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7.4), ("BACKGROUND", (0, 0), (-1, 0), HEAD), ("TEXTCOLOR", (0, 0), (-1, 0), INK2), ("LINEBELOW", (0, 0), (-1, 0), 1, RED),
                                   ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("GRID", (0, 0), (-1, -1), .3, LINE), ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
                                   ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
            el += [Paragraph("<b>Summary</b>", cap_st), t, Spacer(1, 4 * mm)]
        cols = ["No", "Description", "Type", "Qty", "Unit", "Rate", "Contract amt", "Measured", "Area/Qty", "Deduction", "% done",
                "Previous", "This PC", "Certified to date", "Remarks"]
        cw = [9, 0, 16, 11, 10, 17, 21, 17, 17, 17, 12, 20, 19, 22, 30]
        cw[1] = lw / mm - sum(cw)
        for b in doc["bills"]:
            data = [cols]
            sty = [("FONTSIZE", (0, 0), (-1, -1), 6.9), ("BACKGROUND", (0, 0), (-1, 0), HEAD), ("TEXTCOLOR", (0, 0), (-1, 0), INK2), ("LINEBELOW", (0, 0), (-1, 0), 1, RED),
                   ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("GRID", (0, 0), (-1, -1), .3, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                   ("ALIGN", (3, 1), (13, -1), "RIGHT"), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5), ("TOPPADDING", (0, 0), (-1, -1), 1.5)]
            sec = None
            for r in b["rows"]:
                it, ln = r["it"], r["ln"]
                if it["section"] and it["section"] != sec:
                    sec = it["section"]
                    sty.append(("SPAN", (1, len(data)), (-1, len(data))))
                    sty.append(("BACKGROUND", (0, len(data)), (-1, len(data)), TINT))
                    data.append(["", P(sec, stb)] + [""] * 13)
                meas, done = _cell_measure(r)
                if r["chg"]:                      # changed since the last certificate: a pale shade, the moved figure a little deeper
                    y = len(data)
                    sty.append(("BACKGROUND", (0, y), (-1, y), colors.HexColor("#FFFBEB")))
                    for f_, cs in (("measure", (7, 8)), ("deduct", (9,)), ("pct", (10,)), ("amount", (12,)), ("remark", (14,))):
                        if f_ in r["chg"]:
                            for c_ in cs:
                                sty.append(("BACKGROUND", (c_, y), (c_, y), colors.HexColor("#FDF1C7")))
                    sty.append(("LINEBEFORE", (0, y), (0, y), 2, colors.HexColor("#E0B84C")))
                data.append([it["no"], P(it["description"], sts), P(it["ref"] or it["var_ref"], sts), f"{it['qty']:g}" if it["qty"] else "", it["unit"],
                             _m(it["rate"]) if it["rate"] else "", _m(it["amount"]), meas, done, _m(-ln["deduct"]) if ln.get("deduct") else "-",
                             _pct_txt(r), _m(r["prev"]), _m(r["amount"] - r["prev"]), _m(r["amount"]), P(ln.get("remark", ""), sts)])
            data.append(["", P("Total", stb), "", "", "", "", _m(b["contract"]), "", "", "", "", _m(b["prev"]), _m(b["cum"] - b["prev"]), _m(b["cum"]), ""])
            sty += [("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#FDF0EE"))]
            t = Table(data, colWidths=[x * mm for x in cw], repeatRows=1)
            t.setStyle(TableStyle(sty))
            cap = (f"{b['bill']} - " if b["bill"] else "") + (b["title"] or ("Contract works" if not b["var"] else ""))
            el += [Paragraph(f"<b>{X(cap)}</b>", cap_st), t, Spacer(1, 4 * mm)]
        tot = sum(b["cum"] for b in doc["bills"])
        el.append(Paragraph(f"<b>Total to date carried over to the Certificate page: AED {_m(tot, False)}</b>", stb))
        el.append(Spacer(1, 6 * mm))
        tw = lw                     # B, C and the invoice carry on on the same wide pages - no half-empty page
    else:
        el += [PageBreak()]
    # Appendix B
    el.append(Paragraph("<b>Appendix - B &nbsp; Previous Payments</b>", ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=10, spaceAfter=4, keepWithNext=1)))
    hb = [["Sr", "Payment Certificate No.", "Period ending", "Certified on", "Certified (AED)", "Paid (AED)", "VAT (AED)", "Retention (AED)"]]
    for i, h in enumerate(doc["hist"], 1):
        hb.append([str(i), h["name"], h["period"], h["cert"], _m(h["amount"]), _m(h["paid"]), _m(h["vat"]), _m(h["ret"])])
    ht = doc["hist_total"]
    hb.append(["", "Total carried to the Certificate page", "", "", _m(ht["amount"]), _m(ht["paid"]), _m(ht["vat"]), _m(ht["ret"])])
    t = Table(hb, colWidths=[8 * mm, tw - 8 * mm - 6 * 22 * mm] + [22 * mm] * 6, repeatRows=1)
    t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7.4), ("BACKGROUND", (0, 0), (-1, 0), HEAD), ("TEXTCOLOR", (0, 0), (-1, 0), INK2), ("LINEBELOW", (0, 0), (-1, 0), 1, RED),
                           ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("GRID", (0, 0), (-1, -1), .3, LINE), ("ALIGN", (4, 0), (-1, -1), "RIGHT"),
                           ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")]))
    el += [t, Spacer(1, 6 * mm)]
    # Appendix C
    if doc["deds"]:
        el.append(Paragraph("<b>Appendix - C &nbsp; Deductions</b>", ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=10, spaceAfter=4, keepWithNext=1)))
        for cat in DED_CATS:
            ds = [x for x in doc["deds"] if x["cat"] == cat]
            if not ds:
                continue
            data = [["Sl", f"Deduction for {cat.lower()}", "PC", "Qty", "Unit", "Rate", "Total"]]
            for i, x in enumerate(ds, 1):
                desc = (f"{_dt(_d(x['on_date']))} - " if x["on_date"] else "") + x["description"] + (f"\n*{x['note']}" if x["note"] else "") + ("" if x["counted"] else "\n*Not deducted")
                data.append([str(i), P(desc, sts), f"{x['pc_seq']:02d}", f"{x['qty']:g}" if x["qty"] else "", x["unit"], _m(x["rate"]) if x["rate"] else "",
                             _m(x["amount"]) if x["counted"] else f"({_m(x['amount'], False)})*"])
            data.append(["", "", "", "", "", "Total", _m(sum(x["amount"] for x in ds if x["counted"]))])
            t = Table(data, colWidths=[8 * mm, tw - 96 * mm, 10 * mm, 16 * mm, 14 * mm, 22 * mm, 26 * mm], repeatRows=1)
            t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7.4), ("BACKGROUND", (0, 0), (-1, 0), TINT), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                                   ("GRID", (0, 0), (-1, -1), .3, LINE), ("ALIGN", (3, 0), (-1, -1), "RIGHT"), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            el += [t, Spacer(1, 3 * mm)]
        el.append(Paragraph(f"<b>Grand total: AED {_m(sum(x['amount'] for x in doc['deds'] if x['counted']), False)}</b>", stb))
        el.append(Spacer(1, 6 * mm))
    # the subcontractor's bill
    inv = doc["inv"]
    vb, vo = doc["verified"]
    if inv["ref"] or inv["lines"] or vb:
        el.append(Paragraph("<b>Subcontractor's Invoice</b>", ParagraphStyle("h4", fontName="Helvetica-Bold", fontSize=10, spaceAfter=4, keepWithNext=1)))
        data = [["Invoice no.", inv["ref"], "Invoice date", inv["date"], "Received", inv["received"], "Amount (AED)", _m(inv["amount"])]]
        for x in inv["lines"]:
            data.append([P(x.get("d", ""), sts), "", "", "", "", "", "", _m(x.get("a", 0))])
        fr = [.11, .17, .11, .13, .09, .13, .12, .14]
        t = Table(data, colWidths=[tw * f for f in fr])
        sty = [("FONTSIZE", (0, 0), (-1, -1), 7.4), ("GRID", (0, 0), (-1, -1), .3, LINE), ("BACKGROUND", (0, 0), (-1, 0), TINT), ("ALIGN", (-1, 0), (-1, -1), "RIGHT")]
        for i in range(1, len(data)):
            sty.append(("SPAN", (0, i), (-2, i)))
        t.setStyle(TableStyle(sty))
        el += [t, Spacer(1, 2 * mm)]
        el.append(Paragraph(f"Verified at site: <b>{X(vb)}</b> on {_dt(vo)}" if vb else "Verified at site: not yet", st))
    d.build(el)
    buf.seek(0)
    return buf


# -------------------- preview (HTML) --------------------

def render_html(doc, pdf_url):
    from html import escape as X
    import export_web
    e = lambda v: X(str(v or ""))
    rows = lambda pairs: "".join(f"<tr><th>{e(a)}</th><td>: {e(b)}</td></tr>" for a, b in pairs)
    ae = ""

    def sec(letter, title, lines, total=None, total_label=""):
        h = f"<tr class='sh'><td>{letter}</td><td colspan=3>{e(title)}</td></tr>"
        for x in lines:
            a, b, v = (x if len(x) == 3 else (x[0], "", x[1]))
            h += f"<tr><td></td><td>{e(a)}</td><td class=c>{e(b)}</td><td class=r>{_m(v)}</td></tr>"
        if total is not None:
            h += f"<tr class=b><td></td><td>{e(total_label)}</td><td></td><td class=r>{_m(total)}</td></tr>"
        return h
    a_lines = list(doc["A"]) + ([("Material on Site", "", doc["mos"])] if doc["mos"] else [])
    cert = (sec("A", "ADD: VALUE OF WORK EXECUTED", a_lines, doc["A_total"] + doc["mos"], "Total Value of Work Executed") +
            sec("B", "ADD: ADVANCE PAYMENT", doc["B"]) + sec("C", "LESS: DEDUCTIONS", doc["C"], doc["C_total"], "Total Deductions") +
            sec("D", "ADD: ADDITIONS", doc["D"]) + sec("E", "LESS: PREVIOUSLY CERTIFIED AMOUNT", doc["E"] or [("Previously certified", 0)], doc["E_total"], "Total Previously Certified Amounts") +
            f"<tr class='b netrow'><td></td><td colspan=2>Net Amount Due for Payment (A + B - C + D - E)</td><td class=r>{_m(doc['net'], False)}</td></tr>"
            f"<tr class=b><td></td><td colspan=2>VAT ({doc['vat_pct']:g}%)</td><td class=r>{_m(doc['vat'], False)}</td></tr>"
            f"<tr class='b pay'><td></td><td colspan=2>Total Amount Due for Payment</td><td class=r>AED {_m(doc['payable'], False)}</td></tr>")
    sig = "".join(f"<div><b>{e(a)}</b><br>Name: {e(n)}<br>Date: {_dt(o)}<br><span class=m>{'signed in the portal' if n else 'Sign:'}</span></div>" for a, n, o in doc["sign"])
    if doc["bills"]:
        ae = "<section class='pg wide'><h2>Appendix - A &nbsp; Value of Work done &amp; Variations</h2>"
        if doc["changed_note"]:
            ae += f"<div class=mvkey><i></i>{e(doc['changed_note'])}</div>"
        if doc["multi_bill"]:
            bb = [b for b in doc["bills"] if not b["var"]]
            pct = lambda v, c: f"{(100 * v / c) if c else 0:.2f}%"
            ae += "<h3>Summary</h3><table class=t><tr><th>Bill</th><th>Description</th><th>Contract</th><th>Previous %</th><th>This %</th><th>To date %</th><th>Previous</th><th>This</th><th>To date</th></tr>"
            for b in bb:
                ae += f"<tr><td>{e(b['bill'])}</td><td>{e(b['title'])}</td><td class=r>{_m(b['contract'])}</td><td class=r>{pct(b['prev'], b['contract'])}</td><td class=r>{pct(b['cum'] - b['prev'], b['contract'])}</td><td class=r>{pct(b['cum'], b['contract'])}</td><td class=r>{_m(b['prev'])}</td><td class=r>{_m(b['cum'] - b['prev'])}</td><td class=r>{_m(b['cum'])}</td></tr>"
            tc, tp, tcum = sum(b["contract"] for b in bb), sum(b["prev"] for b in bb), sum(b["cum"] for b in bb)
            ae += f"<tr class=b><td></td><td>TOTAL</td><td class=r>{_m(tc)}</td><td class=r>{pct(tp, tc)}</td><td class=r>{pct(tcum - tp, tc)}</td><td class=r>{pct(tcum, tc)}</td><td class=r>{_m(tp)}</td><td class=r>{_m(tcum - tp)}</td><td class=r>{_m(tcum)}</td></tr></table>"
        for b in doc["bills"]:
            cap = (f"{b['bill']} - " if b["bill"] else "") + (b["title"] or ("Contract works" if not b["var"] else ""))
            ae += f"<h3>{e(cap)}</h3><div class=tw><table class=t><tr><th>No</th><th>Description</th><th>Type</th><th>Qty</th><th>Unit</th><th>Rate</th><th>Contract amt</th><th>Measured</th><th>Area/Qty</th><th>Deduction</th><th>% done</th><th>Previous</th><th>This PC</th><th>Certified to date</th><th>Remarks</th></tr>"
            sec_ = None
            for r in b["rows"]:
                it, ln = r["it"], r["ln"]
                if it["section"] and it["section"] != sec_:
                    sec_ = it["section"]
                    ae += f"<tr class=sh><td></td><td colspan=14>{e(sec_)}</td></tr>"
                meas, done = _cell_measure(r)
                ch = r["chg"]
                k = lambda *f: " chg" if ch & set(f) else ""          # the figure that moved, a shade deeper
                ae += (f"<tr{' class=mv' if ch else ''}><td>{e(it['no'])}</td><td class=d>{e(it['description'])}</td><td>{e(it['ref'] or it['var_ref'])}</td><td class=r>{it['qty']:g}</td><td>{e(it['unit'])}</td>"
                       f"<td class=r>{_m(it['rate']) if it['rate'] else ''}</td><td class=r>{_m(it['amount'])}</td><td class='c{k('measure')}'>{meas}</td><td class='r{k('measure')}'>{done}</td>"
                       f"<td class='r{k('deduct')}'>{_m(-ln['deduct']) if ln.get('deduct') else '-'}</td><td class='r{k('pct')}'>{_pct_txt(r)}</td><td class=r>{_m(r['prev'])}</td>"
                       f"<td class='r{k('amount')}'>{_m(r['amount'] - r['prev'])}</td><td class=r><b>{_m(r['amount'])}</b></td><td class='s{k('remark')}'>{e(ln.get('remark', ''))}</td></tr>")
            ae += f"<tr class=b><td></td><td>Total</td><td></td><td></td><td></td><td></td><td class=r>{_m(b['contract'])}</td><td></td><td></td><td></td><td></td><td class=r>{_m(b['prev'])}</td><td class=r>{_m(b['cum'] - b['prev'])}</td><td class=r>{_m(b['cum'])}</td><td></td></tr></table></div>"
        ae += f"<p class=b>Total to date carried over to the Certificate page: AED {_m(sum(b['cum'] for b in doc['bills']), False)}</p>"
    hb = "".join(f"<tr><td>{i}</td><td>{e(h['name'])}</td><td>{e(h['period'])}</td><td>{e(h['cert'])}</td><td class=r>{_m(h['amount'])}</td><td class=r>{_m(h['paid'])}</td><td class=r>{_m(h['vat'])}</td><td class=r>{_m(h['ret'])}</td></tr>" for i, h in enumerate(doc["hist"], 1))
    ht = doc["hist_total"]
    appb = (f"<h2>Appendix - B &nbsp; Previous Payments</h2><table class=t><tr><th>Sr</th><th>Payment Certificate No.</th><th>Period ending</th><th>Certified on</th><th>Certified</th><th>Paid</th><th>VAT</th><th>Retention</th></tr>{hb}"
            f"<tr class=b><td></td><td>Total carried to the Certificate page</td><td></td><td></td><td class=r>{_m(ht['amount'])}</td><td class=r>{_m(ht['paid'])}</td><td class=r>{_m(ht['vat'])}</td><td class=r>{_m(ht['ret'])}</td></tr></table>")
    appc = ""
    if doc["deds"]:
        appc = "<h2>Appendix - C &nbsp; Deductions</h2>"
        for cat in DED_CATS:
            ds = [x for x in doc["deds"] if x["cat"] == cat]
            if not ds:
                continue
            appc += f"<table class=t><tr><th>Sl</th><th>Deduction for {e(cat.lower())}</th><th>PC</th><th>Qty</th><th>Unit</th><th>Rate</th><th>Total</th></tr>"
            for i, x in enumerate(ds, 1):
                desc = (f"{_dt(_d(x['on_date']))} - " if x["on_date"] else "") + x["description"]
                note = (f"<div class=m>*{e(x['note'])}</div>" if x["note"] else "") + ("" if x["counted"] else "<div class=m>*Not deducted</div>")
                appc += f"<tr><td>{i}</td><td>{e(desc)}{note}</td><td>{x['pc_seq']:02d}</td><td class=r>{x['qty']:g}</td><td>{e(x['unit'])}</td><td class=r>{_m(x['rate']) if x['rate'] else ''}</td><td class=r>{_m(x['amount']) if x['counted'] else '(' + _m(x['amount'], False) + ')*'}</td></tr>"
            appc += f"<tr class=b><td colspan=6 class=r>Total</td><td class=r>{_m(sum(x['amount'] for x in ds if x['counted']))}</td></tr></table>"
        appc += f"<p class=b>Grand total: AED {_m(sum(x['amount'] for x in doc['deds'] if x['counted']), False)}</p>"
    inv = doc["inv"]
    vb, vo = doc["verified"]
    appd = ""
    if inv["ref"] or inv["lines"] or vb:
        il = "".join(f"<tr><td colspan=7>{e(x.get('d'))}</td><td class=r>{_m(x.get('a', 0))}</td></tr>" for x in inv["lines"])
        appd = (f"<h2>Subcontractor's Invoice</h2><table class=kvt><tr><th>Invoice no.</th><td>{e(inv['ref'])}</td><th>Invoice date</th><td>{e(inv['date'])}</td><th>Received</th><td>{e(inv['received'])}</td><th>Amount</th><td class=r>{_m(inv['amount'])}</td></tr>{il}</table>"
                f"<p>Verified at site: {('<b>' + e(vb) + '</b> on ' + _dt(vo)) if vb else 'not yet'}</p>")
    logo = export_web.logo_data_uri()
    terms = (("Contract: " + doc["contract_type"] + "<br>") if doc["contract_type"] else "") + e(doc["pay_terms"]).replace("\n", "<br>")
    title = doc["title"] + ("" if doc["kind"] == "Interim" else f" ({doc['kind'].upper()})")
    fname = re.sub(r"[^A-Za-z0-9]+", "_", doc["ref"])
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(doc['ref'])}</title><style>
body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#ECEAE6;margin:0;color:#22262A;font-size:12px}}
.bar{{position:sticky;top:0;z-index:5;background:#22262A;color:#fff;padding:9px 14px;display:flex;gap:8px;align-items:center}}
.bar b{{flex:1;font-size:13px}} .bar a,.bar button{{background:#C0392B;color:#fff;border:0;border-radius:6px;padding:7px 12px;font-weight:600;text-decoration:none;font-size:13px;cursor:pointer}}
.pg{{background:#fff;max-width:800px;margin:14px auto;padding:22px 26px;box-shadow:0 2px 10px rgba(0,0,0,.08);border-top:3px solid #B7322A}}
.kvt{{border:1px solid #DDE0E3;margin-bottom:6px}} .kvt th{{background:#F7F5F3;text-align:left;padding:5px 8px;font-size:11px;color:#3E434A;white-space:nowrap}} .kvt td{{padding:5px 8px;border-left:1px solid #EEE}}
.pg.wide{{max-width:1180px}} .top{{display:flex;justify-content:space-between;align-items:flex-start}} .top img{{height:44px}}
.ref{{text-align:right;font-weight:700}} .ref span{{display:block;color:#6B7178;font-weight:400;font-size:11px}}
h1{{text-align:center;font-size:17px;margin:8px 0 10px;letter-spacing:.5px}} h2{{font-size:14px;margin:6px 0 8px}} h3{{font-size:12.5px;margin:12px 0 5px}}
table{{border-collapse:collapse;width:100%}} .hd{{border:1px solid #C9CDD2;margin-bottom:8px}} .hd th{{text-align:left;font-weight:700;padding:2px 6px;white-space:nowrap;width:1%}} .hd td{{padding:2px 6px}}
.two{{display:grid;grid-template-columns:1fr 1fr;border:1px solid #C9CDD2;margin-bottom:8px}} .two>div{{padding:6px 8px}} .two>div+div{{border-left:1px solid #C9CDD2}} .two b{{display:block;background:#F7F2F1;margin:-6px -8px 4px;padding:4px 8px}}
.ctr{{display:grid;grid-template-columns:300px 1fr;border:1px solid #C9CDD2;margin-bottom:8px}} .ctr>div{{padding:6px 8px}} .ctr>div+div{{border-left:1px solid #C9CDD2;font-size:11px}}
.ctr th{{text-align:left;padding:2px 8px 2px 0;white-space:nowrap}} .ctr td{{padding:2px 0}}
.ce{{border:1px solid #C9CDD2}} .ce td{{padding:3px 6px}} .ce .sh td{{background:#F7F2F1;font-weight:700}} .ce .b td{{font-weight:700}} .ce .netrow td{{border-top:1.5px solid #222}} .ce{{table-layout:fixed}} .ce .pay td{{background:#FDF0EE;font-size:13px}}
.r{{text-align:right;white-space:nowrap}} .c{{text-align:center;white-space:nowrap}}
.sig{{display:grid;grid-template-columns:repeat(5,1fr);border:1px solid #C9CDD2;margin-top:10px}} .sig div{{padding:6px;border-left:1px solid #C9CDD2;line-height:1.5}} .sig div:first-child{{border-left:0}}
.m{{color:#6B7178;font-size:10.5px}} .tw{{overflow-x:auto}}
.t tr.mv td{{background:#FFFBEB}} .t tr.mv td.chg{{background:#FDF1C7}} .t tr.mv td:first-child{{box-shadow:inset 3px 0 0 #E0B84C}} .mvkey{{font-size:10.5px;color:#6B5A1E;margin:-2px 0 6px}} .mvkey i{{display:inline-block;width:11px;height:11px;background:#FDF1C7;border:1px solid #E0B84C;vertical-align:-1px;margin-right:4px}}
@media print{{.t tr.mv td{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}}}
.t{{font-size:11px;margin-bottom:6px}} .t th{{background:#F7F5F3;color:#3E434A;padding:5px 6px;font-weight:700;font-size:10px;letter-spacing:.04em;text-transform:uppercase;text-align:left;white-space:nowrap;border-bottom:1.5px solid #B7322A}} .t td{{border:1px solid #DDE0E3;padding:3px 5px;vertical-align:top}}
.t .sh td{{background:#F7F2F1;font-weight:700}} .t .b td,p.b{{font-weight:700}} .t td.d{{min-width:220px}} .t td.s{{font-size:10px;color:#555;min-width:90px}}
@media print{{.bar{{display:none}} body{{background:#fff}} .pg{{box-shadow:none;margin:0;max-width:none;break-after:page}}}}
@media (max-width:700px){{.pg{{padding:12px}} .two,.ctr{{grid-template-columns:1fr}} .two>div+div,.ctr>div+div{{border-left:0;border-top:1px solid #C9CDD2}} .sig{{grid-template-columns:1fr 1fr}}}}
</style></head><body><div class="bar"><b>{e(doc['ref'])}</b><button onclick="print()">Print</button><a href="{pdf_url}">PDF</a><button onclick="shr()">Share</button></div>
<script>async function shr(){{try{{const r=await fetch("{pdf_url}");const b=await r.blob();const f=new File([b],"{fname}.pdf",{{type:"application/pdf"}});if(navigator.canShare&&navigator.canShare({{files:[f]}}))await navigator.share({{files:[f],title:"{e(doc['ref'])}"}});else{{const a=document.createElement("a");a.href=URL.createObjectURL(b);a.download=f.name;a.click();}}}}catch(e){{}}}}</script>
<section class="pg"><div class="top"><img src="{logo}"><div class="ref">{e(doc['ref'])}<span>Payment Certificate No.: {doc['pc_seq']:02d}</span></div></div>
<h1>{e(title)}</h1>
<table class="hd"><tr><td style="width:62%;vertical-align:top;padding:0"><table>{rows(doc['head_l'])}</table></td><td style="vertical-align:top;padding:0"><table>{rows(doc['head_r'])}</table></td></tr></table>
<div class="two"><div><b>Main Contractor Details</b>{'<br>'.join(e(x) for x in doc['main'])}</div><div><b>Subcontractor Details</b>{'<br>'.join(e(x) for x in doc['subc'])}</div></div>
<div class="ctr"><div><table>{''.join(f'<tr><th>{e(k)}</th><td>{e(v)}</td></tr>' for k, v in doc['contract'] if k and v)}</table></div><div><b>Payment Terms</b><br>{terms}</div></div>
<table class="ce"><colgroup><col style="width:30px"><col><col style="width:110px"><col style="width:140px"></colgroup>{cert}</table><div class="sig">{sig}</div></section>
{(ae + '<div style="height:14px"></div>' + appb + appc + appd + '</section>') if ae else ('<section class="pg">' + appb + appc + appd + '</section>')}</body></html>"""


@router.get("/export/est/pc/{pc_id}")
def pc_print(pc_id: int, token: str, format: str = "preview", db: Session = Depends(get_db)):
    u = auth.get_download_user_from_token(token, db)
    if not ({E.RIGHT, "accounts_bank"} & set(E.M.effective_permissions(u))):
        raise HTTPException(status_code=403, detail="Estimation only.")
    pc = db.query(E.EstSubPC).get(pc_id)
    if not pc:
        raise HTTPException(404, "That certificate is not there any more.")
    doc = build_doc(db, pc)
    if format == "pdf":
        buf = render_pdf(doc)
        name = re.sub(r"[^A-Za-z0-9]+", "_", doc["ref"]).strip("_")
        return StreamingResponse(buf, media_type="application/pdf", headers={"Content-Disposition": f"inline; filename={name}.pdf"})
    return HTMLResponse(render_html(doc, f"/export/est/pc/{pc_id}?token={token}&format=pdf"))

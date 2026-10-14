"""Accounts > Send to Zoho > Sent to Zoho.

Every change the portal makes in Zoho is written here as it happens (see
zohoapi.call): which portal line, what Zoho made of it (an expense, a
journal, a transfer ...), its Zoho number, and where the money went - from
which account to which account, with the project, supplier and VAT. The
chief accountant checks each against Zoho itself (Check reads the live Zoho
record and shows any difference) and can reverse one: it is deleted in
Zoho and the portal line goes back to waiting, to correct and send again.
"""
import json
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session

import main as M
import models
from database import get_db

router = APIRouter()
ZG = Depends(M.require_any_screen("accounts_zoho"))

# Zoho path -> (kind, response key, id field, number field)
KINDS = {
    "expenses": ("expense", "expense", "expense_id", "reference_number"),
    "journals": ("journal", "journal", "journal_id", "entry_number"),
    "banktransactions": ("banktransaction", "banktransaction", "transaction_id", "reference_number"),
    "vendorpayments": ("vendorpayment", "vendorpayment", "payment_id", "payment_number"),
    "customerpayments": ("customerpayment", "payment", "payment_id", "payment_number"),
    "purchaseorders": ("purchaseorder", "purchaseorder", "purchaseorder_id", "purchaseorder_number"),
    "invoices": ("invoice", "invoice", "invoice_id", "invoice_number"),
    "contacts": ("contact", "contact", "contact_id", "contact_name"),
}
LABEL = {"expense": "Expense", "journal": "Journal", "banktransaction": "Transfer", "vendorpayment": "Payment made",
         "customerpayment": "Payment received", "purchaseorder": "Purchase order", "invoice": "Invoice", "contact": "Supplier"}
# Where each kind opens in Zoho Books (web).
WEB = {"expense": "expenses", "journal": "accountant/journals", "banktransaction": "banking", "vendorpayment": "paymentsmade",
       "customerpayment": "paymentsreceived", "purchaseorder": "purchaseorders", "invoice": "invoices", "contact": "contacts"}
SOURCE_LABEL = {"petty": "Petty cash", "bank": "Bank", "lpo": "LPO", "loan": "Staff loan", "invoice": "Tax invoice",
                "supplier": "Supplier", "reverse": "Reversed", "other": "Other"}


def _acc_names(db):
    """Zoho account id -> "Parent › Name", from the list read from Zoho."""
    import zohoapi
    out = {}
    for a in zohoapi.accounts_full(db):
        out[a["id"]] = f"{a['parent']} › {a['name']}" if a.get("parent") else a["name"]
    for k, v in zohoapi.chart(db).items() if zohoapi._CACHE.get("chart") else []:
        out.setdefault(v, k)
    return out


def _vendor_name(db, vid):
    if not vid:
        return ""
    s = db.query(models.Supplier).filter(models.Supplier.zoho_id == vid).first()
    return s.name if s else ""


def _project(db, pid):
    if not pid:
        return ""
    import zohoapi
    try:
        for code, (i, _c) in (zohoapi._CACHE.get("projects") or (0, {}))[1].items():
            if i == pid:
                return code
    except Exception:
        pass
    return ""


def describe(db, path, body, resp):
    """What a change was, in the chief accountant's words: from -> to."""
    base = path.split("/")[0].split("?")[0]
    kind, key, idk, numk = KINDS.get(base, (base.rstrip("s"), base.rstrip("s"), "id", "number"))
    body = body or {}
    obj = (resp or {}).get(key) or {}
    names = _acc_names(db)
    nm = lambda i: names.get(i, i or "")
    d = {"kind": kind, "zoho_id": str(obj.get(idk) or (path.split("/")[1] if "/" in path else "")),
         "number": str(obj.get(numk) or obj.get("entry_number") or body.get(numk) or body.get("reference_number") or ""),
         "date": body.get("date") or body.get("journal_date") or "", "amount": 0.0, "from": "", "to": "", "detail": {}}
    det = d["detail"]
    if body.get("description") or body.get("notes"):
        det["description"] = (body.get("description") or body.get("notes") or "")[:160]
    if kind == "expense":
        d["from"] = nm(body.get("paid_through_account_id"))
        if body.get("line_items"):
            det["lines"] = [{"account": nm(l.get("account_id")), "amount": l.get("amount")} for l in body["line_items"]]
            d["to"] = " + ".join(dict.fromkeys(l["account"] for l in det["lines"]))
            d["amount"] = round(sum(float(l.get("amount") or 0) for l in body["line_items"]), 2)
        else:
            d["to"] = nm(body.get("account_id")); d["amount"] = float(body.get("amount") or 0)
        det["project"] = _project(db, body.get("project_id"))
        det["supplier"] = _vendor_name(db, body.get("vendor_id"))
        det["vat"] = "5% claimed" if body.get("tax_id") and body.get("tax_treatment") == "vat_registered" else (
            "Zero rate" if body.get("tax_treatment") == "vat_registered" else "No VAT")
    elif kind == "journal":
        lines = body.get("line_items") or []
        dr = [nm(l.get("account_id")) for l in lines if l.get("debit_or_credit") == "debit"]
        cr = [nm(l.get("account_id")) for l in lines if l.get("debit_or_credit") == "credit"]
        d["from"], d["to"] = " + ".join(cr), " + ".join(dr)
        d["amount"] = round(sum(float(l.get("amount") or 0) for l in lines if l.get("debit_or_credit") == "debit"), 2)
    elif kind == "banktransaction":
        d["from"], d["to"] = nm(body.get("from_account_id")), nm(body.get("to_account_id"))
        d["amount"] = float(body.get("amount") or 0)
    elif kind == "vendorpayment":
        d["from"] = nm(body.get("paid_through_account_id"))
        d["to"] = (obj.get("vendor_name") or _vendor_name(db, body.get("vendor_id")) or "Supplier") + " (supplier)"
        d["amount"] = float(body.get("amount") or 0)
        if body.get("bills"):
            det["bills"] = len(body["bills"])
    elif kind == "customerpayment":
        d["from"] = (obj.get("customer_name") or "Client") + " (client)"
        d["to"] = nm(body.get("account_id")); d["amount"] = float(body.get("amount") or 0)
    elif kind == "purchaseorder":
        d["from"] = "Purchase order - no money moves yet"
        d["to"] = (obj.get("vendor_name") or _vendor_name(db, body.get("vendor_id")) or "") + " (supplier)"
        d["amount"] = float(obj.get("total") or 0)
        det["project"] = _project(db, body.get("project_id"))
    elif kind == "invoice":
        d["from"] = (obj.get("customer_name") or "Client") + " (client)"
        acc = {nm(l.get("account_id")) for l in body.get("line_items") or [] if l.get("account_id")}
        d["to"] = " + ".join(sorted(acc)) or "Income"
        d["amount"] = float(obj.get("total") or 0)
    elif kind == "contact":
        d["from"] = "Portal supplier list"
        d["to"] = body.get("contact_name") or obj.get("contact_name") or "Zoho supplier"
        d["number"] = ""
    return d


def record(db, method, path, body, resp, err, ctx):
    action = {"POST": "create", "PUT": "update", "DELETE": "delete"}.get(method, method.lower())
    d = describe(db, path, body, resp)
    if action == "delete" and "/" in path:
        d["zoho_id"] = path.split("/")[1]
    db.add(models.ZohoLog(user_id=ctx.get("user_id"), source=ctx.get("source") or "other", item_id=ctx.get("item_id"),
                          ref=ctx.get("ref") or "", action=action, kind=d["kind"], zoho_id=d["zoho_id"], number=d["number"],
                          on_date=d["date"], amount=round(d["amount"] or 0, 2), from_acc=d["from"][:300], to_acc=d["to"][:300],
                          detail=json.dumps(d["detail"]), ok=not err, error=(err or "")[:300]))


# ---- the tab -----------------------------------------------------------------

def _web(db, kind, zid):
    import zohoapi
    if not zid or kind not in WEB:
        return ""
    page = WEB[kind]
    return f"https://books.zoho.com/app/{zohoapi.org(db)}#/{page}/{zid}" if page != "banking" else f"https://books.zoho.com/app/{zohoapi.org(db)}#/banking"


def _item(db, source, item_id):
    """The portal line behind a log row: (model object, short text)."""
    if not item_id:
        return None, ""
    if source == "petty":
        x = db.get(models.PettyCash, item_id)
        return x, (f"{(x.book or 'site').title()} · {x.description}" if x else "")
    if source == "bank":
        x = db.get(models.BankEntry, item_id)
        return x, (f"{x.kind.title()} · {x.party or x.notes or ''}" if x else "")
    if source == "lpo":
        x = db.get(models.PurchaseOrder, item_id)
        return x, (f"{x.ref} · {x.supplier}" if x else "")
    if source == "loan":
        x = db.get(models.StaffLoan, item_id)
        if not x:
            return None, ""
        e = db.get(models.Employee, x.employee_id)
        return x, f"Loan · {e.name if e else ''}"
    if source == "invoice":
        from accounts import Invoice
        x = db.get(Invoice, item_id)
        return x, (f"{x.number} · {x.client}" if x else "")
    if source == "supplier":
        x = db.get(models.Supplier, item_id)
        return x, (x.name if x else "")
    return None, ""


def _row(db, l, users):
    _x, text = _item(db, l.source, l.item_id)
    try:
        det = json.loads(l.detail or "{}")
    except ValueError:
        det = {}
    return {"id": l.id, "at": l.at.isoformat() if l.at else "", "by": users.get(l.user_id, ""), "source": l.source,
            "source_label": SOURCE_LABEL.get(l.source, l.source), "item_id": l.item_id, "item": text, "ref": l.ref,
            "action": l.action, "kind": l.kind, "kind_label": LABEL.get(l.kind, l.kind), "zoho_id": l.zoho_id,
            "number": l.number, "date": l.on_date, "amount": l.amount, "from": l.from_acc, "to": l.to_acc,
            "project": det.get("project", ""), "supplier": det.get("supplier", ""), "vat": det.get("vat", ""),
            "lines": det.get("lines", []), "description": det.get("description", ""), "ok": l.ok, "error": l.error,
            "reversed": bool(l.reversed_at), "reversed_at": l.reversed_at.isoformat() if l.reversed_at else "",
            "reversed_by": users.get(l.reversed_by, ""), "reverse_reason": l.reverse_reason,
            "can_reverse": l.ok and l.action == "create" and not l.reversed_at and l.source in REVERSIBLE and bool(l.zoho_id),
            "web": _web(db, l.kind, l.zoho_id)}


REVERSIBLE = {"petty", "bank", "lpo", "loan", "invoice"}


def _period(start, end):
    today = M._dubai_today()
    a = M._as_date(start) or today.replace(day=1)
    b = M._as_date(end) or today
    return a, b


@router.get("/store/zoho/sent")
def sent(start: str = "", end: str = "", source: str = "", all: int = 0,
         db: Session = Depends(get_db), user: models.User = ZG):
    a, b = _period(start, end)
    t0 = datetime.combine(a, datetime.min.time()) - timedelta(hours=4)        # Dubai day boundaries
    t1 = datetime.combine(b + timedelta(days=1), datetime.min.time()) - timedelta(hours=4)
    q = db.query(models.ZohoLog).filter(models.ZohoLog.at >= t0, models.ZohoLog.at < t1)
    if source:
        q = q.filter(models.ZohoLog.source == source)
    if not all:
        q = q.filter(models.ZohoLog.ok == True, models.ZohoLog.action == "create",   # noqa: E712
                     models.ZohoLog.source != "supplier")
    users = {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}
    rows = [_row(db, l, users) for l in q.order_by(models.ZohoLog.at.desc(), models.ZohoLog.id.desc()).limit(2000)]
    live = [r for r in rows if r["action"] == "create" and r["ok"] and not r["reversed"]]
    return {"start": a.isoformat(), "end": b.isoformat(), "rows": rows,
            "counts": {"sent": len(live), "amount": round(sum(r["amount"] for r in live if r["kind"] != "purchaseorder"), 2),
                       "reversed": sum(1 for r in rows if r["reversed"]), "failed": sum(1 for r in rows if not r["ok"])},
            "may_reverse": _may_reverse(user)}


def _may_reverse(user):
    return (user.role or "") == "admin" or "accounts_zoho" in M.effective_permissions(user)


def _live(db, kind, zid):
    """The Zoho record as it is now, in the same from -> to words."""
    import zohoapi
    path = {v[0]: k for k, v in KINDS.items()}.get(kind)
    key = KINDS[path][1]
    o = (zohoapi.call(db, "GET", f"{path}/{zid}") or {}).get(key) or {}
    out = {"amount": None, "from": "", "to": "", "project": o.get("project_name") or "", "supplier": o.get("vendor_name") or "",
           "number": str(o.get(KINDS[path][3]) or o.get("entry_number") or ""), "status": o.get("status") or ""}
    if kind == "expense":
        out["from"] = o.get("paid_through_account_name") or ""
        items = o.get("line_items") or []
        out["to"] = " + ".join(dict.fromkeys(i.get("account_name") or "" for i in items)) if len(items) > 1 else (
            (items[0].get("account_name") if items else "") or o.get("account_name") or "")
        out["amount"] = float(o.get("total") or o.get("amount") or 0)
    elif kind == "journal":
        items = o.get("line_items") or []
        out["to"] = " + ".join(i.get("account_name") or "" for i in items if i.get("debit_or_credit") == "debit")
        out["from"] = " + ".join(i.get("account_name") or "" for i in items if i.get("debit_or_credit") == "credit")
        out["amount"] = float(o.get("total") or 0)
    elif kind == "banktransaction":
        out["from"] = o.get("from_account_name") or o.get("account_name") or ""
        out["to"] = o.get("to_account_name") or o.get("offset_account_name") or ""
        out["amount"] = float(o.get("amount") or 0)
    elif kind == "vendorpayment":
        out["from"] = o.get("paid_through_account_name") or ""
        out["to"] = (o.get("vendor_name") or "") + " (supplier)"
        out["amount"] = float(o.get("amount") or 0)
    elif kind == "customerpayment":
        out["from"] = (o.get("customer_name") or "") + " (client)"
        out["to"] = o.get("account_name") or ""
        out["amount"] = float(o.get("amount") or 0)
    elif kind in ("purchaseorder", "invoice"):
        out["amount"] = float(o.get("total") or 0)
        out["to"] = (o.get("vendor_name") or o.get("customer_name") or "")
    return out


def _leaf(s):
    import zohoapi
    return " + ".join(sorted(zohoapi._norm(p.split(" › ")[-1].replace(" (supplier)", "").replace(" (client)", ""))
                             for p in (s or "").split(" + ") if p))


@router.get("/store/zoho/sent/{lid}/check")
def check(lid: int, db: Session = Depends(get_db), user: models.User = ZG):
    import zohoapi
    l = db.get(models.ZohoLog, lid)
    if not l or not l.zoho_id:
        raise HTTPException(status_code=404, detail="Nothing to check.")
    if not zohoapi.connected(db):
        raise HTTPException(status_code=400, detail="Zoho is not connected.")
    try:
        live = _live(db, l.kind, l.zoho_id)
    except zohoapi.ZohoError as e:
        if e.code == 404 or "not exist" in e.msg.lower() or "does not exist" in e.msg.lower():
            return {"exists": False, "diffs": ["Not in Zoho any more - deleted there"]}
        raise HTTPException(status_code=400, detail=f"Zoho did not answer: {e.msg[:150]}")
    diffs = []
    if live["amount"] is not None and l.kind != "purchaseorder" and abs((live["amount"] or 0) - (l.amount or 0)) > 0.005:
        diffs.append(f"Amount in Zoho {live['amount']:,.2f} - portal sent {l.amount:,.2f}")
    for k, lab in (("from", "From"), ("to", "To")):
        mine = getattr(l, k + "_acc")
        if live[k] and mine and l.kind not in ("purchaseorder", "invoice") and _leaf(live[k]) != _leaf(mine):
            diffs.append(f"{lab} in Zoho: {live[k]} - portal sent {mine}")
    return {"exists": True, "live": live, "diffs": diffs}


@router.post("/store/zoho/sent/{lid}/reverse")
def reverse(lid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = ZG):
    """Delete the entry in Zoho and put the portal line back to waiting."""
    import zohoapi
    if not _may_reverse(user):
        raise HTTPException(status_code=403, detail="Only the chief accountant or the admin can reverse.")
    reason = " ".join(str(payload.get("reason") or "").split())[:200]
    if len(reason) < 4:
        raise HTTPException(status_code=400, detail="Why is it reversed? Type the reason.")
    l = db.get(models.ZohoLog, lid)
    if not l or l.action != "create" or not l.ok or not l.zoho_id:
        raise HTTPException(status_code=404, detail="Nothing to reverse.")
    if l.reversed_at:
        raise HTTPException(status_code=400, detail="Already reversed.")
    if l.source not in REVERSIBLE:
        raise HTTPException(status_code=400, detail="This change cannot be reversed from here.")
    if not zohoapi.connected(db):
        raise HTTPException(status_code=400, detail="Zoho is not connected.")
    x, text = _item(db, l.source, l.item_id)
    path = {v[0]: k for k, v in KINDS.items()}.get(l.kind)
    gone = False
    with zohoapi.about("reverse", l.item_id, l.ref, user.id):
        try:
            zohoapi.call(db, "DELETE", f"{path}/{l.zoho_id}")
        except zohoapi.ZohoError as e:
            if e.code == 404 or "not exist" in e.msg.lower():
                gone = True                     # already deleted in Zoho
            else:
                db.commit()
                raise HTTPException(status_code=400, detail=f"Zoho refused to delete it: {e.msg[:200]}")
    now = datetime.now(timezone.utc)
    l.reversed_at, l.reversed_by, l.reverse_reason = now, user.id, reason
    if x is not None and (getattr(x, "zoho_id", "") or "").endswith(l.zoho_id):
        x.zoho_status, x.zoho_id, x.zoho_err = "", "", ""
        if hasattr(x, "zoho_ref"):
            x.zoho_ref = f"Reversed {now + timedelta(hours=4):%d %b %Y}: {reason}"[:200]
        for f in ("approved_by", "approved_at", "released_by", "released_at"):
            if hasattr(x, f):
                setattr(x, f, None)
    db.commit()
    M.log_action(db, user.id, "zoho_reverse",
                 f"{SOURCE_LABEL.get(l.source, l.source)} {text or l.ref} - Zoho {LABEL.get(l.kind, l.kind)} {l.number} "
                 f"AED {l.amount:,.2f} {'(already gone in Zoho) ' if gone else ''}reversed: {reason}")
    return {"ok": True, "gone": gone}


# ---- the paper ---------------------------------------------------------------

@router.get("/export/zoho/sent")
def export_sent(token: str, start: str = "", end: str = "", source: str = "", all: int = 0, format: str = "excel",
                db: Session = Depends(get_db)):
    from urllib.parse import quote
    from fastapi.responses import StreamingResponse
    import auth, export_web
    u = auth.get_download_user_from_token(token, db)
    if (u.role or "") != "admin" and "accounts_zoho" not in M.effective_permissions(u):
        raise HTTPException(status_code=403, detail="Send to Zoho is for the chief accountant.")
    d = sent(start, end, source, all, db, u)
    rows = [{"Sent": (datetime.fromisoformat(r["at"]) + timedelta(hours=4)).strftime("%d-%b-%y %H:%M") if r["at"] else "",
             "Portal": f"{r['source_label']} - {r['item'] or r['ref']}", "Zoho": f"{r['kind_label']} {r['number']}".strip()
             + (" (deleted)" if r["action"] == "delete" else "") + (" (updated)" if r["action"] == "update" else ""),
             "From": r["from"] or "-", "To": r["to"] or "-", "Project": r["project"] or "-", "Supplier": r["supplier"] or "-",
             "Amount (AED)": r["amount"] if r["action"] == "create" else "",
             "Status": ("Refused: " + r["error"]) if not r["ok"] else (f"Reversed {r['reversed_at'][:10]} - {r['reverse_reason']}" if r["reversed"] else "In Zoho"),
             "By": r["by"] or "-"} for r in d["rows"]]
    a, b = M._as_date(d["start"]), M._as_date(d["end"])
    title = "Sent to Zoho" if not all else "Changes made in Zoho"
    sub = f"{a:%d %b %Y} - {b:%d %b %Y} | {d['counts']['sent']} in Zoho, AED {d['counts']['amount']:,.2f} | reversed {d['counts']['reversed']}"
    money = ["Amount (AED)"]
    if format == "view":
        url = (f"/export/zoho/sent?start={d['start']}&end={d['end']}&source={quote(source)}&all={all}"
               f"&token={quote(auth.create_view_token(u.username), safe='')}")
        return M._preview_page(title, sub, rows, url, url, money_cols=money)
    name = f"Sent_to_Zoho_{d['start']}_to_{d['end']}"
    if format == "pdf":
        return StreamingResponse(export_web.build_store_report_pdf(title, rows, sub, money_cols=money, orientation="landscape"),
                                 media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})
    return StreamingResponse(export_web.build_store_report_excel(title, rows, sub, money_cols=money),
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename={name}.xlsx"})

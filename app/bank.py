"""Bank - Accounts > Bank.

Every movement on the company's bank account is entered here once and
goes to Zoho Books from here - nobody types it in Zoho again:

  Paid to supplier / subcontractor  -> Payment Made, against his open bills
  Paid - direct expense             -> Expense paid through ADCB, with project
  Received from client              -> Customer Payment, against his invoices
  Bank charge                       -> Expense: Bank Fees and Charges
  Transfer to petty cash / cash     -> Transfer Fund

The chief accountant's own entries go to Zoho as he saves them; anyone
else's wait on this screen for him to approve. A cheque carries the
cheque date and the cheque number as its reference, as Zoho is kept.

Statement check: the ADCB lines Zoho has from the bank statement that
are not yet entered are listed, each one a click from being entered.
"""
import json
from datetime import date, datetime, timezone, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

import main as M
import models, auth, export_web
from database import get_db

router = APIRouter()
RIGHT = "accounts_bank"
APPROVER = "accounts_zoho"
BK = Depends(M.require_any_screen(RIGHT))
KINDS = {"vendor": "Paid to supplier", "expense": "Paid - expense", "customer": "Received from client",
         "charge": "Bank charge", "transfer": "Transfer"}
MODES = ["Bank Transfer", "Cheque", "Credit Card", "Cash"]
TRANSFER_TO = ["Company Petty Cash", "Jomon Petty Cash", "Site Petty Cash", "Cash"]
BANK_ACC = {"ADCB": "ADCB"}


def _may_send(user):
    return APPROVER in M.effective_permissions(user)


def _docs(x):
    try:
        return json.loads(x.docs or "[]")
    except Exception:
        return []


def _row(x, users):
    return {"id": x.id, "date": x.on_date.isoformat(), "kind": x.kind, "kind_label": KINDS.get(x.kind, x.kind),
            "party": x.party or "", "party_id": x.party_id or "", "mode": x.mode or "", "reference": x.reference or "",
            "docs": _docs(x), "account": x.account or "", "site": x.site or "", "amount": round(x.amount or 0, 2),
            "out": x.kind != "customer", "vat": bool(x.vat), "trn": x.trn or "", "vat_claim": x.vat_claim or "", "notes": x.notes or "",
            "zoho": x.zoho_status or "", "zoho_ref": x.zoho_ref or "", "zoho_err": x.zoho_err or "",
            "scope_id": x.scope_id, "net_amount": round(x.net_amount or 0, 2), "pp_id": x.pp_id,
            "by": users.get(x.updated_by or x.created_by, "")}


def _month(month):
    try:
        y, m = (int(v) for v in str(month).split("-")[:2])
        a = date(y, m, 1)
    except Exception:
        a = M._dubai_today().replace(day=1)
    b = date(a.year + (a.month == 12), a.month % 12 + 1, 1) - timedelta(days=1)
    return a, b


def listing(db, month):
    a, b = _month(month)
    rows = (db.query(models.BankEntry).filter(models.BankEntry.on_date >= a, models.BankEntry.on_date <= b)
              .order_by(models.BankEntry.on_date, models.BankEntry.id).all())
    users = {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}
    out = [_row(x, users) for x in rows]
    return {"month": f"{a:%Y-%m}", "label": f"{a:%B %Y}", "rows": out,
            "paid": round(sum(r["amount"] for r in out if r["out"]), 2),
            "received": round(sum(r["amount"] for r in out if not r["out"]), 2),
            "waiting": sum(1 for r in out if r["zoho"] in ("", "sending")),
            "refused": sum(1 for r in out if r["zoho"] == "" and r["zoho_err"])}


@router.get("/store/bank")
def list_bank(month: str = "", db: Session = Depends(get_db), user: models.User = BK):
    import zohoapi, zohosync
    # Post-dated client cheques whose date has come go on Project payments now.
    for x in db.query(models.BankEntry).filter(models.BankEntry.kind == "customer", models.BankEntry.scope_id.isnot(None),
                                               models.BankEntry.pp_id.is_(None), models.BankEntry.on_date <= M._dubai_today()).all():
        try:
            link_receipt(db, x); db.commit()
        except HTTPException:
            db.rollback()
    d = listing(db, month)
    d.update(kinds=KINDS, modes=MODES, transfer_to=TRANSFER_TO, groups=zohosync.GROUPS[:2],
             may_send=_may_send(user), connected=zohoapi.connected(db))
    return d


def _clean(p):
    kind = str(p.get("kind") or "vendor")
    if kind not in KINDS:
        raise HTTPException(status_code=400, detail="Pick what kind of bank line it is.")
    d = M._as_date(p.get("date"))
    if not d:
        raise HTTPException(status_code=400, detail="Which date? (for a cheque, the cheque date)")
    try:
        amt = round(float(str(p.get("amount") or 0).replace(",", "")), 2)
    except ValueError:
        raise HTTPException(status_code=400, detail="The amount must be a number.")
    if amt <= 0:
        raise HTTPException(status_code=400, detail="Enter the amount.")
    party = str(p.get("party") or "").strip()[:160]
    if kind in ("vendor", "customer") and not party:
        raise HTTPException(status_code=400, detail="Who was it paid to / received from?")
    mode = str(p.get("mode") or "Bank Transfer")
    if mode not in MODES:
        mode = "Bank Transfer"
    ref = str(p.get("reference") or "").strip()[:80]
    if mode == "Cheque" and not ref:
        raise HTTPException(status_code=400, detail="Type the cheque number.")
    if mode != "Cheque" and d > M._dubai_today():
        raise HTTPException(status_code=400, detail="That date is in the future - only a cheque can carry a later date.")
    acc = str(p.get("account") or "").strip()[:200]
    if kind == "transfer" and acc not in TRANSFER_TO:
        raise HTTPException(status_code=400, detail="Transfer to which box?")
    docs = p.get("docs") or []
    docs = [{"id": str(x.get("id") or ""), "number": str(x.get("number") or "")[:60],
             "amount": round(float(x.get("amount") or 0), 2)} for x in docs if x and float(x.get("amount") or 0) > 0]
    if round(sum(x["amount"] for x in docs), 2) > amt + 0.005:
        raise HTTPException(status_code=400, detail="The bills / invoices add up to more than the amount.")
    vat = bool(p.get("vat")) and kind in ("expense", "charge")
    trn = "".join(ch for ch in str(p.get("trn") or "") if ch.isdigit())[:15] if vat else ""
    vat_claim = str(p.get("vat_claim") or "") if vat else ""
    if vat and vat_claim not in ("claim", "zero"):
        raise HTTPException(status_code=400, detail="VAT on the bill: pick Claim 5% or Not claimable.")
    if vat_claim == "claim" and len(trn) != 15:
        raise HTTPException(status_code=400, detail="To claim the VAT, type the supplier's TRN (15 digits).")
    if trn and len(trn) != 15:
        raise HTTPException(status_code=400, detail="A TRN has 15 digits.")
    scope_id, net = None, 0.0
    if kind == "customer" and p.get("scope_id"):
        import projectpay as pp
        scope_id = int(p.get("scope_id"))
        try:
            net = round(float(str(p.get("net_amount") or 0).replace(",", "")), 2)
        except ValueError:
            raise HTTPException(status_code=400, detail="The amount for Project payments must be a number.")
        if net <= 0 or net > amt + 0.005:
            raise HTTPException(status_code=400, detail="The amount for Project payments (excl. VAT) must be more than 0 and not more than the amount received.")
    return {"scope_id": scope_id, "net_amount": net, "kind": kind, "on_date": d, "party": party, "party_id": str(p.get("party_id") or "")[:40], "mode": mode,
            "reference": ref, "docs": json.dumps(docs), "account": acc, "site": str(p.get("site") or "").strip()[:40],
            "amount": amt, "vat": vat, "trn": trn, "vat_claim": vat_claim, "notes": str(p.get("notes") or "").strip()[:300]}


BANK_PLACES = [("vendorpayments", "vendorpayments", "payment_id", "description_contains"),
               ("customerpayments", "customerpayments", "payment_id", "search_text"),
               ("expenses", "expenses", "expense_id", "description_contains"),
               ("banktransactions", "banktransactions", "transaction_id", "search_text")]


def _send(db, rows, user):
    """Send each line once (see zohoapi.claim); refusals wait with Zoho's reason."""
    import zohoapi
    if not zohoapi.connected(db):
        return 0, []
    now = datetime.now(timezone.utc)
    sent, failed = 0, []
    import zohosync
    start = zohosync._start(db)
    for x in rows:
        if x.on_date and x.on_date < start:
            failed.append({"id": x.id, "why": f"Dated before {start:%d %b %Y}, when the portal starts sending to Zoho - enter it in Zoho by hand"})
            continue
        unsure = (x.zoho_status == "sending") or bool(x.zoho_err)
        was = ""
        if not zohoapi.claim(db, models.BankEntry, x, ("",)):
            continue
        try:
            zid = zohoapi.find_existing(db, f"[BK-{x.id}]", BANK_PLACES) if unsure else ""
            label = "Found in Zoho"
            if not zid:
                zid, label = push(db, x)
            x.zoho_status, x.zoho_id, x.zoho_ref, x.zoho_err = "sent", zid, label, ""
            x.approved_by, x.approved_at = user.id, now
            sent += 1
        except Exception as e:
            x.zoho_status = was
            x.zoho_err = zohoapi.fail_text(e)
            failed.append({"id": x.id, "why": x.zoho_err})
        db.commit()
    return sent, failed


def link_receipt(db, x):
    """Keep the Project payments line in step with a client's payment:
    made when a scope is picked, changed with it, removed with it."""
    import projectpay as pp
    line = db.get(pp.ProjectPayment, x.pp_id) if x.pp_id else None
    if not line:
        line = db.query(pp.ProjectPayment).filter(pp.ProjectPayment.source == f"bank:{x.id}").first()
    # A post-dated cheque goes on the tracker once its date comes.
    if x.kind != "customer" or not x.scope_id or x.on_date > M._dubai_today():
        if line:
            db.delete(line)
        x.pp_id = None
        db.flush()
        return
    sc = db.get(pp.ProjectScope, x.scope_id)
    if not sc:
        raise HTTPException(status_code=400, detail="That project scope is no longer on Project payments.")
    others = sum((p.amount or 0) for p in sc.payments if not line or p.id != line.id)
    if round(others + (x.net_amount or 0), 2) > round(sc.contract or 0, 2) + 0.005:
        raise HTTPException(status_code=400, detail=f"This takes {sc.project} - {sc.scope} past its contract value ({sc.contract:,.2f}). "
                                                    "Update the contract on Project payments first, or pick another scope.")
    note = " ".join(v for v in (", ".join(d["number"] for d in _docs(x) if d.get("number")), x.reference) if v)[:120]
    if not line:
        line = pp.ProjectPayment(scope_id=x.scope_id, on_date=x.on_date, amount=x.net_amount, note=note, source=f"bank:{x.id}")
        db.add(line); db.flush()
    else:
        line.scope_id, line.on_date, line.amount, line.note, line.source = x.scope_id, x.on_date, x.net_amount, note, f"bank:{x.id}"
    x.pp_id = line.id
    db.flush()


@router.get("/store/bank/scopes")
def scopes(db: Session = Depends(get_db), user: models.User = BK):
    """The project scopes on Project payments, for a client's payment."""
    import projectpay as pp
    rows = db.query(pp.ProjectScope).order_by(pp.ProjectScope.project, pp.ProjectScope.sort, pp.ProjectScope.id).all()
    return {"scopes": [{"id": r.id, "project": r.project, "scope": r.scope} for r in rows]}


@router.post("/store/bank")
def add(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = BK):
    x = models.BankEntry(**_clean(payload), bank="ADCB", created_by=user.id, updated_by=user.id)
    db.add(x); db.flush()
    try:
        link_receipt(db, x)
    except HTTPException:
        db.rollback(); raise
    db.commit()
    M.log_action(db, user.id, "bank_add", f"{KINDS[x.kind]} {x.party} {x.amount:,.2f} {x.reference}")
    sent, failed = _send(db, [x], user) if _may_send(user) else (0, [])
    return {"ok": True, "id": x.id, "sent": sent, "failed": failed}


@router.put("/store/bank/{bid}")
def edit(bid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = BK):
    x = db.get(models.BankEntry, bid)
    if not x:
        raise HTTPException(status_code=404, detail="That line is no longer there.")
    new = _clean(payload)
    import zohoapi
    if zohoapi.in_doubt(x):
        raise HTTPException(status_code=400, detail="Zoho did not answer when this line was sent. Press Send first "
                                                    "(Zoho is checked, nothing is sent twice) - then change it.")
    if x.zoho_status in ("sent", "sending"):
        # In Zoho: only where it sits on Project payments may change here.
        free = {"scope_id", "net_amount"}
        moved = [k for k, v in new.items() if k not in free and getattr(x, k) != v]
        if moved:
            raise HTTPException(status_code=400, detail="It is in Zoho already - change it in Zoho, or delete it there (it then shows cancelled here) and enter it again.")
    for k, v in new.items():
        setattr(x, k, v)
    x.updated_by, x.zoho_err = user.id, ""
    if x.zoho_status == "cancelled":
        x.zoho_status = ""
    try:
        link_receipt(db, x)
    except HTTPException:
        db.rollback(); raise
    db.commit()
    M.log_action(db, user.id, "bank_edit", f"#{bid} {KINDS[x.kind]} {x.party} {x.amount:,.2f}")
    sent, failed = _send(db, [x], user) if _may_send(user) else (0, [])
    return {"ok": True, "sent": sent, "failed": failed}


@router.delete("/store/bank/{bid}")
def delete(bid: int, db: Session = Depends(get_db), user: models.User = BK):
    x = db.get(models.BankEntry, bid)
    if not x:
        raise HTTPException(status_code=404, detail="That line is no longer there.")
    import zohoapi
    if x.zoho_status == "sent":
        raise HTTPException(status_code=400, detail="It is in Zoho - delete it in Zoho; it is then cancelled here.")
    if zohoapi.in_doubt(x):
        raise HTTPException(status_code=400, detail="Zoho did not answer when this line was sent - press Send first (Zoho is checked), then remove it if it is not there.")
    M.log_action(db, user.id, "bank_delete", f"#{bid} {KINDS[x.kind]} {x.party} {x.amount:,.2f}")
    import projectpay as pp
    for line in db.query(pp.ProjectPayment).filter(pp.ProjectPayment.source == f"bank:{x.id}").all():
        db.delete(line)
    db.delete(x); db.commit()
    return {"ok": True}


@router.post("/store/bank/send")
def send(payload: dict = Body(default={}), db: Session = Depends(get_db), user: models.User = BK):
    """Approve and send the waiting lines (all, or the ones ticked)."""
    import zohoapi
    if not _may_send(user):
        raise HTTPException(status_code=403, detail="Only the chief accountant sends bank lines to Zoho.")
    if not zohoapi.connected(db):
        raise HTTPException(status_code=400, detail="Zoho is not connected yet - Accounts > Send to Zoho > Connect Zoho.")
    ids = {int(i) for i in (payload.get("ids") or [])}
    # Waiting lines, and any left 'sending' by a request that died. A line
    # deleted in Zoho (cancelled) is not sent again unless it is edited.
    rows = [x for x in db.query(models.BankEntry).filter(models.BankEntry.zoho_status.in_(["", "sending"])).all()
            if not ids or x.id in ids]
    sent, failed = _send(db, rows, user)
    return {"ok": True, "sent": sent, "failed": failed}


# ---- Zoho look-ups (supplier / client, their open bills / invoices) -------

@router.get("/store/bank/contacts")
def contacts(q: str = "", kind: str = "vendor", db: Session = Depends(get_db), user: models.User = BK):
    import zohoapi
    if not zohoapi.connected(db) or len(q.strip()) < 2:
        return {"contacts": []}
    d = zohoapi.call(db, "GET", "contacts", {"contact_name_contains": q.strip(), "per_page": 20,
                                             "contact_type": "vendor" if kind == "vendor" else "customer"})
    return {"contacts": [{"id": c["contact_id"], "name": c["contact_name"]} for c in d.get("contacts", [])]}


@router.get("/store/bank/open")
def open_docs(contact_id: str, kind: str = "vendor", db: Session = Depends(get_db), user: models.User = BK):
    """The supplier's unpaid bills, or the client's unpaid invoices."""
    import zohoapi
    if not zohoapi.connected(db) or not contact_id:
        return {"docs": []}
    if kind == "vendor":
        d = zohoapi.call(db, "GET", "bills", {"vendor_id": contact_id, "status": "unpaid", "per_page": 100})
        docs = [{"id": b["bill_id"], "number": b.get("bill_number") or "", "date": b.get("date") or "",
                 "balance": b.get("balance") or 0, "total": b.get("total") or 0} for b in d.get("bills", [])]
    else:
        d = zohoapi.call(db, "GET", "invoices", {"customer_id": contact_id, "status": "unpaid", "per_page": 100})
        docs = [{"id": i["invoice_id"], "number": i.get("invoice_number") or "", "date": i.get("date") or "",
                 "balance": i.get("balance") or 0, "total": i.get("total") or 0} for i in d.get("invoices", [])]
    return {"docs": docs}


def _contact_id(db, name, kind):
    import zohoapi
    d = zohoapi.call(db, "GET", "contacts", {"contact_name_contains": name, "per_page": 20,
                                             "contact_type": "vendor" if kind == "vendor" else "customer"})
    hits = [c for c in d.get("contacts", []) if (c.get("contact_name") or "").strip().lower() == name.strip().lower()]
    if len(hits) == 1:
        return hits[0]["contact_id"]
    raise zohoapi.ZohoError(400, f"'{name}' is not one {'supplier' if kind == 'vendor' else 'client'} in Zoho - pick it from the list")


def push(db, x):
    import zohoapi as Z
    bank = Z.account_id(db, BANK_ACC.get(x.bank or "ADCB", "ADCB"))
    if not bank:
        raise Z.ZohoError(400, "Zoho has no account named ADCB")
    ref = x.reference or f"BK-{x.id}"
    desc = (f"[BK-{x.id}] " + (x.notes or x.party or KINDS.get(x.kind, "")))[:100]   # tag first, bracketed: never cut off, BK-1 never matches BK-10
    dt = x.on_date.isoformat()
    amt = round(x.amount or 0, 2)
    docs = _docs(x)
    if x.kind == "vendor":
        cid = x.party_id or _contact_id(db, x.party, "vendor")
        body = {"vendor_id": cid, "payment_mode": x.mode, "amount": amt, "date": dt, "reference_number": ref,
                "paid_through_account_id": bank, "description": desc,
                "bills": [{"bill_id": b["id"], "amount_applied": b["amount"]} for b in docs if b.get("id")]}
        d = Z.call(db, "POST", "vendorpayments", body=body)
        v = d.get("vendorpayment") or d.get("vendor_payment") or {}
        return f"vendorpayment:{v.get('payment_id')}", f"Payment Made {v.get('payment_number') or ''}".strip()
    if x.kind == "customer":
        cid = x.party_id or _contact_id(db, x.party, "customer")
        body = {"customer_id": cid, "payment_mode": x.mode, "amount": amt, "date": dt, "reference_number": ref,
                "account_id": bank, "description": desc,
                "invoices": [{"invoice_id": b["id"], "amount_applied": b["amount"]} for b in docs if b.get("id")]}
        d = Z.call(db, "POST", "customerpayments", body=body)
        v = d.get("payment") or {}
        return f"customerpayment:{v.get('payment_id')}", f"Customer Payment {v.get('payment_number') or ''}".strip()
    if x.kind == "transfer":
        to = Z.account_id(db, x.account)
        if not to:
            raise Z.ZohoError(400, f"Zoho has no account named {x.account}")
        d = Z.call(db, "POST", "banktransactions", body={"transaction_type": "transfer_fund", "from_account_id": bank,
                                                         "to_account_id": to, "amount": amt, "date": dt,
                                                         "reference_number": ref, "description": desc})
        return f"banktransaction:{d['banktransaction']['transaction_id']}", "Transfer"
    acc = Z.account_id(db, "Bank Fees and Charges") if x.kind == "charge" else Z.account_id(db, x.account)
    if not acc:
        raise Z.ZohoError(400, f"Zoho has no account named {('Bank Fees and Charges' if x.kind == 'charge' else x.account).split(' › ')[-1]}")
    body = {"account_id": acc, "date": dt, "amount": amt, "paid_through_account_id": bank, "reference_number": ref,
            "description": desc, "is_inclusive_tax": True}
    vendor = ""
    if x.party:
        try:
            vendor = x.party_id or _contact_id(db, x.party, "vendor")
            body["vendor_id"] = vendor
        except Z.ZohoError:
            vendor = ""                                 # sent without; on the chief accountant's list to add
    if x.site:
        p = Z.projects(db).get(x.site.strip())
        if p:
            body["project_id"], body["customer_id"] = p
    body.update(Z.vat_fields(db, x.vat, x.trn, x.vat_claim or ""))
    d = Z.call(db, "POST", "expenses", body=body)
    x.zoho_todo = "supplier" if (x.party or "").strip() and not vendor else ""
    return f"expense:{d['expense']['expense_id']}", "Expense"


# ---- statement check -------------------------------------------------------

@router.get("/store/bank/statement")
def statement(month: str = "", db: Session = Depends(get_db), user: models.User = BK):
    """ADCB statement lines Zoho has that nobody has entered yet."""
    import zohoapi as Z
    if not Z.connected(db):
        return {"connected": False, "lines": []}
    a, b = _month(month)
    bank = Z.account_id(db, "ADCB")
    d = Z.call(db, "GET", "banktransactions", {"account_id": bank, "date_start": a.isoformat(), "date_end": b.isoformat(),
                                               "filter_by": "Status.Uncategorized", "per_page": 200})
    lines = [{"date": t.get("date"), "amount": t.get("amount") or 0, "in": t.get("debit_or_credit") == "debit",
              "reference": t.get("reference_number") or "", "description": t.get("description") or t.get("payee") or ""}
             for t in d.get("banktransactions", [])]
    return {"connected": True, "lines": lines}


# ---- the paper ---------------------------------------------------------------

@router.get("/export/accounts/bank")
def export_bank(token: str, month: str = "", format: str = "excel", db: Session = Depends(get_db)):
    u = auth.get_download_user_from_token(token, db)
    if RIGHT not in M.effective_permissions(u):
        raise HTTPException(status_code=403, detail="Bank is for accounts only.")
    d = listing(db, month)
    st = {"sent": "In Zoho", "sending": "Sending", "cancelled": "Deleted in Zoho", "": "Waiting"}
    rows = [{"Date": M._as_date(r["date"]).strftime("%d-%b-%y"), "Type": r["kind_label"], "Party": r["party"] or "-",
             "Mode": r["mode"], "Reference": r["reference"] or "-",
             "Bills / invoices": ", ".join(x["number"] for x in r["docs"]) or "-", "Project": r["site"] or "-",
             "Paid out (AED)": r["amount"] if r["out"] else "", "Received (AED)": "" if r["out"] else r["amount"],
             "Zoho": st.get(r["zoho"], r["zoho"]) + (f" ({r['zoho_ref']})" if r["zoho_ref"] else "")} for r in d["rows"]]
    title = "Bank - ADCB"
    sub = f"{d['label']} | paid out {d['paid']:,.2f} | received {d['received']:,.2f} | As at {M._dubai_today():%d %b %Y}"
    money = ["Paid out (AED)", "Received (AED)"]
    if format == "view":
        url = f"/export/accounts/bank?month={quote(d['month'])}&token={quote(auth.create_view_token(u.username), safe='')}"
        return M._preview_page(title, sub, rows, url, url, money_cols=money)
    name = f"Bank_ADCB_{d['month']}"
    if format == "pdf":
        return StreamingResponse(export_web.build_store_report_pdf(title, rows, sub, money_cols=money, orientation="landscape"),
                                 media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})
    return StreamingResponse(export_web.build_store_report_excel(title, rows, sub, money_cols=money),
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename={name}.xlsx"})

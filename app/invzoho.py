"""Tax invoices to Zoho, on Release.

A tax invoice is made in the portal (its number, IC/26/913/IPA09, is the
one Zoho keeps) and held. It goes to Zoho only when admin or the chief
accountant presses Release - so which VAT quarter it falls in is a
decision, not an accident. Once released it is changed in Zoho; a
cancelled one is flagged to be voided there too.
"""
import json
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session

import main as M
import models
from database import get_db

router = APIRouter()
INCOME = ["Progressive Payments", "Progressive Payments - Phase 2", "MEP Work Payments", "Joinery Works Payments",
          "Landscape Work Payment", "SwimmingPool Progressive Payments", "Design & Supervision Fee", "Supervision Fee",
          "Mobilization Fee", "Excavation Works Fee", "Payment for Soil Investigation and Other Surveys",
          "Authority Payments", "Sales"]


def _may(user):
    return user.role == "admin" or "accounts_zoho" in M.effective_permissions(user)


def _user(user=Depends(__import__("auth").get_current_user)):
    if not _may(user):
        raise HTTPException(status_code=403, detail="Only admin and the chief accountant release invoices to Zoho.")
    return user


def income_accounts(db):
    import zohoapi as Z
    def fetch():
        d = Z.call(db, "GET", "chartofaccounts", {"filter_by": "AccountType.Income", "per_page": 200})
        return {Z._norm(a["account_name"]): a["account_id"] for a in d.get("chartofaccounts", [])}
    return Z._cached(db, "income", fetch)


def income_id(db, name):
    """The income account by name. Zoho's list can leave out sub-accounts
    (these sit under "Income"), so the exact name is asked for too."""
    import zohoapi as Z
    hit = income_accounts(db).get(Z._norm(name))
    if hit:
        return hit
    try:
        d = Z.call(db, "GET", "chartofaccounts", {"account_name": name, "per_page": 20, "filter_by": "AccountType.Active"})
    except Z.ZohoError:
        return ""
    for a in d.get("chartofaccounts", []):
        if Z._norm(a.get("account_name")) == Z._norm(name) and a.get("account_type") == "income":
            return a["account_id"]
    return ""


def zero_tax(db):
    import zohoapi as Z
    def fetch():
        for t in Z.call(db, "GET", "settings/taxes").get("taxes", []):
            if float(t.get("tax_percentage") or 0) == 0 and "zero" in (t.get("tax_name") or "").lower():
                return t["tax_id"]
        return ""
    return Z._cached(db, "zerotax", fetch)


def push_invoice(db, x, account):
    import zohoapi as Z
    # Already in Zoho under this number? Then it is linked, not made twice.
    d = Z.call(db, "GET", "invoices", {"invoice_number": x.number, "per_page": 25})
    for inv in d.get("invoices", []):
        if (inv.get("invoice_number") or "").strip() == x.number.strip():
            got = inv.get("total")
            same_total = got is None or abs(float(got) - round(x.total or 0, 2)) <= 0.01
            same_client = (inv.get("customer_name") or "").strip().lower() in ("", (x.client or "").strip().lower())
            if not (same_total and same_client):
                # Never link a different invoice that happens to carry the number.
                raise Z.ZohoError(400, f"{x.number} is already used in Zoho for {inv.get('customer_name') or 'another invoice'}"
                                       f" (AED {float(got or 0):,.2f}) - give this invoice the next number and release again")
            return inv["invoice_id"], "Found in Zoho"
    c = Z.call(db, "GET", "contacts", {"contact_name_contains": x.client, "contact_type": "customer", "per_page": 20})
    hits = [k for k in c.get("contacts", []) if (k.get("contact_name") or "").strip().lower() == (x.client or "").strip().lower()]
    if len(hits) != 1:
        raise Z.ZohoError(400, f"Client '{x.client}' is {'not' if not hits else 'more than once'} in Zoho under that exact name - "
                               "fix the name in Zoho (or on the invoice) and release again")
    acc = income_id(db, account)
    if not acc:
        raise Z.ZohoError(400, f"Zoho has no income account named {account}")
    vat5, vat0 = Z.vat_tax(db), zero_tax(db)
    items = []
    for l in json.loads(x.lines or "[]"):
        it = {"description": l["description"][:2000], "rate": round(l["amount"], 2), "quantity": 1, "account_id": acc}
        five = float(l.get("vat") or 0) == 5
        t = vat5 if five else vat0
        if not t:
            # Never post an invoice whose VAT Zoho would leave out.
            raise Z.ZohoError(400, f"Zoho has no {'5% Standard Rate' if five else 'Zero Rate'} tax - add it in Zoho settings, then release again")
        it["tax_id"] = t
        items.append(it)
    body = {"customer_id": hits[0]["contact_id"], "invoice_number": x.number, "date": x.inv_date.isoformat(),
            "reference_number": f"INV-{x.id}", "line_items": items, "is_inclusive_tax": False,
            "notes": " - ".join(v for v in (x.project_no, x.project, x.work) if v)[:500]}
    p = Z.projects(db).get((x.project_no or "").strip())
    if p:
        body["project_id"] = p[0]
    d = Z.call(db, "POST", "invoices", {"ignore_auto_number_generation": "true"}, body=body)
    inv = d["invoice"]
    got = inv.get("total")
    if got is not None and abs(float(got) - round(x.total or 0, 2)) > 0.01:
        # It is in Zoho, so it is linked - but the difference is shown.
        return inv["invoice_id"], f"Invoice - CHECK: Zoho total {float(got):,.2f} vs {x.total or 0:,.2f} here"
    return inv["invoice_id"], "Invoice"


@router.get("/store/zoho/invoice/accounts")
def accounts(db: Session = Depends(get_db), user: models.User = Depends(_user)):
    return {"accounts": INCOME, "default": "Progressive Payments"}


@router.post("/store/zoho/invoice/{iid}/release")
def release(iid: int, payload: dict = Body(default={}), db: Session = Depends(get_db), user: models.User = Depends(_user)):
    import zohoapi as Z
    from accounts import Invoice
    if not Z.connected(db):
        raise HTTPException(status_code=400, detail="Zoho is not connected yet - Accounts > Send to Zoho > Connect Zoho.")
    x = db.get(Invoice, iid)
    if not x or x.kind != "tax":
        raise HTTPException(status_code=404, detail="Only a tax invoice is released to Zoho.")
    if x.status == "cancelled":
        raise HTTPException(status_code=400, detail="A cancelled invoice is not released.")
    import zohosync
    start = zohosync._start(db)
    if x.inv_date and x.inv_date < start:
        raise HTTPException(status_code=400, detail=f"Dated before {start:%d/%m/%Y}, when the portal starts sending to Zoho - it is entered in Zoho by hand.")
    account = str(payload.get("account") or "Progressive Payments")
    if account not in INCOME:
        raise HTTPException(status_code=400, detail="Pick the income account.")
    if not Z.claim(db, Invoice, x, ("",)):
        raise HTTPException(status_code=400, detail="It is already released (or being released) to Zoho.")
    try:
        with Z.about("invoice", x.id, x.number or "", user.id):
            zid, label = push_invoice(db, x, account)
        x.zoho_status, x.zoho_id = "sent", f"invoice:{zid}"
        x.zoho_err = label if label.startswith("Invoice - CHECK") else ""
        x.released_by, x.released_at = user.id, datetime.now(timezone.utc)
        db.commit()
        M.log_action(db, user.id, "invoice_release", f"{x.number} {x.client} AED {x.total or 0:,.2f} released to Zoho ({label})")
        return {"ok": True, "label": label}
    except Exception as e:
        x.zoho_status = ""
        x.zoho_err = Z.fail_text(e, "release again")
        db.commit()
        raise HTTPException(status_code=400, detail=f"Not released: {x.zoho_err}")

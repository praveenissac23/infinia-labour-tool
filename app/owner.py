"""The owner's dashboard (10 Nov 2026): what the owner needs to know, from every department, on one screen -
money for the next 30 days, what is waiting for him, the projects and a light for each department. Only the admin
(the owner's login) gets it; everyone else keeps the dashboard they have.

Every figure comes from what the departments already keep in the app - nothing is typed for this page:
  coming in   = payment certificates sent to the clients and not paid yet - the amount due on each (Estimation >
                Projects > Client PCs: Submitted / Certified / Invoiced)
  going out   = pending cheques dated in the next 30 days or already past (Accounts > PDCs) + subcontractor invoices
                certified and not paid yet (Estimation > Subcontracts: Certified ... MD approved)
  collected   = payments received against the projects, month by month (Accounts > Project payments)
"""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import auth
import main as M
import models
from database import get_db

router = APIRouter()
r2 = lambda v: round(float(v or 0) + 0.0, 2)


def _owner(user: models.User = Depends(auth.get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "The owner's dashboard is for the admin login.")
    return user


def _safe(fn, default):
    try:
        return fn()
    except Exception as e:                              # one department's figure failing never blanks the page
        print("owner dashboard:", fn.__name__ if hasattr(fn, "__name__") else fn, repr(e))
        return default


@router.get("/permissions/owner")          # under /permissions/: a path the web server already sends to the app
def overview(db: Session = Depends(get_db), user: models.User = Depends(_owner)):
    import estimation as ES
    import est_bills as EB
    import expiry as EX
    import projectpay as PP
    t = M._dubai_today()
    out = {"today": t.isoformat(), "name": ((user.full_name or user.username or "").strip().split() or [""])[0].title()}

    # ---- projects (Estimation): one bundle a project, as the Estimation dashboard works them out ------------
    def bundles():
        rules = ES._rules(db)
        projects = db.query(ES.EstProject).filter(ES.EstProject.status != "Closed").order_by(ES.EstProject.code).all()
        pre = ES._preload(db, projects, with_files=False)
        return [(p, ES.project_bundle(db, p, rules, pre)) for p in projects]
    bl = _safe(bundles, [])
    coming, sub_due, revised, md_q, projs, client_open = 0.0, 0.0, 0.0, [], [], []
    for p, b in bl:
        s_ = b["summary"]
        revised += s_.get("revised") or 0
        # client: a payment certificate sent to the client and not paid yet - the amount due on it
        owed = 0.0
        for c in b.get("clientpcs") or []:
            if c.get("status") in ("Submitted", "Certified", "Invoiced") and (c.get("payable") or 0) > 0:
                owed += c["payable"]
                client_open.append({"code": p.code, "seq": c.get("seq"), "status": c["status"], "amount": r2(c["payable"]),
                                    "since": c.get("certified_on") or c.get("submitted")})
        coming += owed
        # subcontractors: invoices certified (on their way to payment) and not paid - the amount payable on each
        for sb in b.get("subs") or []:
            for pc in sb.get("pcs") or []:
                st = pc.get("status")
                if st in ("Certified", "Prepared", "CM approved", "Verified", "MD approved"):
                    sub_due += pc.get("payable") or 0
                if st in ("Prepared", "CM approved", "Verified"):
                    md_q.append(pc.get("payable") or 0)
        rev = s_.get("revised") or 0
        done = round(100.0 * (s_.get("client_work") or 0) / rev, 1) if rev else 0.0
        basis = "certified"
        if not done and rev and (s_.get("received") or 0) > 0:     # no certificates kept in the app: what was paid
            done, basis = round(min(100.0, 100.0 * s_["received"] / rev), 1), "paid"
        projs.append({"id": p.id, "code": p.code, "name": p.name or "", "revised": r2(rev), "done": done, "basis": basis,
                      "certified": r2(s_.get("client_certified")), "received": r2(s_.get("received")), "owed": r2(owed),
                      "paid_pct": round(min(100.0, 100.0 * (s_.get("received") or 0) / s_["client_certified"]), 1) if (s_.get("client_certified") or 0) > 0 else None})
    projs.sort(key=lambda x: -x["revised"])
    coming, sub_to_pay, revised = r2(coming), r2(sub_due), r2(revised)
    out["projects"] = projs
    out["contracts"] = {"count": len(projs), "value": revised}
    est = _safe(lambda: {"tenders": db.query(ES.EstTender).filter(ES.EstTender.status.in_(["Received", "Pricing"])).count()}, {"tenders": 0})

    # ---- cheques (Accounts > PDCs) ------------------------------------------------------------------
    pend = db.query(models.Pdc).filter(models.Pdc.status == "pending").all()
    in30 = [c for c in pend if c.cheque_date and c.cheque_date <= t + timedelta(days=30)]
    week = [c for c in pend if c.cheque_date and c.cheque_date <= t + timedelta(days=7)]
    pdc30 = r2(sum(c.amount or 0 for c in in30))
    going = r2(pdc30 + sub_to_pay)
    out["money"] = {"coming": coming, "going": going, "net": r2(coming - going), "pdc30": pdc30, "pdc30_n": len(in30),
                    "sub_to_pay": sub_to_pay, "client_open": client_open}

    # ---- collected per month (Accounts > Project payments) ------------------------------------------
    def months():
        start = (t.replace(day=1) - timedelta(days=330)).replace(day=1)
        rows = db.query(PP.ProjectPayment.on_date, PP.ProjectPayment.amount).filter(PP.ProjectPayment.on_date >= start).all()
        by = {}
        for d, a in rows:
            k = d.strftime("%Y-%m")
            by[k] = by.get(k, 0.0) + (a or 0)
        out_, m = [], start
        while m <= t:
            k = m.strftime("%Y-%m")
            out_.append({"month": k, "amount": r2(by.get(k, 0.0))})
            m = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
        return out_
    col = _safe(months, [])
    out["collected"] = col
    out["money"]["collected_month"] = col[-1]["amount"] if col else 0.0
    out["money"]["collected_prev"] = col[-2]["amount"] if len(col) > 1 else 0.0

    # ---- people: on site today, headcount -----------------------------------------------------------
    rows = db.query(models.DailyRow.employee_id, models.DailyRow.am, models.DailyRow.pm).filter(models.DailyRow.full_date == t).all()
    at_work = {r.employee_id for r in rows if "present" in ((r.am or "") + (r.pm or "")).lower()}
    labour = db.query(models.Employee).filter(models.Employee.active == True, models.Employee.staff == False).count()  # noqa: E712
    staff = db.query(models.Employee).filter(models.Employee.active == True, models.Employee.staff == True).count()  # noqa: E712
    out["people"] = {"on_site": len(at_work), "marked": bool(rows), "labour": labour, "staff": staff}

    # ---- what waits for the owner ---------------------------------------------------------------------
    needs = []
    for c in sorted(client_open, key=lambda c: -c["amount"])[:2]:
        days = (t - c["since"]).days if c.get("since") and hasattr(c["since"], "year") else None
        if isinstance(c.get("since"), str):
            try:
                from datetime import date as _d
                days = (t - _d.fromisoformat(c["since"][:10])).days
            except Exception:
                days = None
        needs.append({"lvl": "red" if (days or 0) > 30 else "amber",
                      "text": f"{c['code']} PC {c['seq']} · {c['status'].lower()}, not paid yet" + (f" · {days} days" if days else ""),
                      "amount": c["amount"], "go": ["estimation", "estproj"]})
    awaiting = db.query(EB.EstBill).filter(EB.EstBill.status == "Awaiting approval").all()
    if awaiting:
        needs.append({"lvl": "amber", "text": f"{len(awaiting)} client bill{'s' if len(awaiting) != 1 else ''} waiting for approval",
                      "amount": r2(sum(b.total_due or 0 for b in awaiting)), "go": ["estimation", "estproj"], "cta": "Approve"})
    if md_q:
        needs.append({"lvl": "amber", "text": f"{len(md_q)} subcontractor payment{'s' if len(md_q) != 1 else ''} for your approval",
                      "amount": r2(sum(md_q)), "go": ["estimation", "estdash"], "cta": "Approve"})
    if week:
        late = sum(1 for c in week if c.cheque_date < t)
        needs.append({"lvl": "red" if late else "amber",
                      "text": "Cheques clearing this week" + (f" · {late} past date" if late else ""),
                      "amount": r2(sum(c.amount or 0 for c in week)), "go": ["dq", "pdc"]})
    ex = _safe(lambda: EX.summary(db), {})
    n_ex = (ex.get("expired") or 0) + (ex.get("week") or 0) + (ex.get("month") or 0)
    if n_ex:
        needs.append({"lvl": "red" if ex.get("expired") else "amber",
                      "text": f"{n_ex} visas, IDs & licences expire in 30 days" + (f" · {ex['expired']} already expired" if ex.get("expired") else ""),
                      "go": ["dq", "expiry"], "cta": "View"})
    urgent = db.query(models.MaterialRequest).filter(models.MaterialRequest.status.in_(("pending", "approved", "arranging")),
                                                     models.MaterialRequest.needed_by != None, models.MaterialRequest.needed_by < t).count()  # noqa: E711
    if urgent:
        needs.append({"lvl": "amber", "text": f"{urgent} material request{'s' if urgent != 1 else ''} past the date site needed them",
                      "go": ["dq", "track"], "cta": "View"})
    out["needs"] = needs

    # ---- a light for each department ------------------------------------------------------------------
    open_mr = db.query(models.MaterialRequest).filter(models.MaterialRequest.status.in_(("pending", "approved", "arranging", "lpo_sent", "partial"))).count()
    tenders = est.get("tenders") or 0
    late_logs = sum(b["summary"].get("overdue") or 0 for _, b in bl)
    month0 = t.replace(day=1)
    bills_m = db.query(EB.EstBill).filter(EB.EstBill.created_at >= month0).count()
    att = round(100.0 * len(at_work) / labour) if labour and rows else None
    light = lambda red, amber: "red" if red else ("amber" if amber else "green")
    out["departments"] = [
        {"name": "Estimation / QS", "value": f"{bills_m} bill{'s' if bills_m != 1 else ''}", "note": f"this month · {tenders} tender{'s' if tenders != 1 else ''} pricing",
         "light": light(late_logs > 5, late_logs > 0 or awaiting), "go": ["estimation", "estdash"]},
        {"name": "Purchasing / Store", "value": f"{open_mr} open", "note": f"material requests · {urgent} past due",
         "light": light(urgent > 10, urgent > 0), "go": ["dq", "track"]},
        {"name": "Accounts", "value": _k(pdc30) + " PDC", "note": f"{len(in30)} cheques in 30 days",
         "light": light(any(c.cheque_date < t for c in in30), pdc30 > coming), "go": ["dq", "pdc"]},
        {"name": "HR / Payroll", "value": f"{labour + staff} people", "note": f"{labour} labour · {staff} office",
         "light": "green", "go": ["dq", "staff"]},
        {"name": "Site / Labour", "value": (f"{att}%" if att is not None else "not in"), "note": "attendance today" if att is not None else "today's attendance not marked yet",
         "light": light(att is not None and att < 60, att is None or att < 80), "go": ["dq", "att"]},
        {"name": "PRO / Visas", "value": f"{n_ex} expiring", "note": "in 30 days" + (f" · {ex.get('expired')} expired" if ex.get("expired") else ""),
         "light": light(bool(ex.get("expired")), n_ex > 0), "go": ["dq", "expiry"]},
    ]
    return out


def _k(v):
    v = float(v or 0)
    if abs(v) >= 1e6:
        return f"{v / 1e6:.2f}M"
    if abs(v) >= 1e3:
        return f"{v / 1e3:.0f}K"
    return f"{v:,.0f}"

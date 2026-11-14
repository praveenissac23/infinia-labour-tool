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
                client_open.append({"pid": p.id, "code": p.code, "seq": c.get("seq"), "status": c["status"], "amount": r2(c["payable"]),
                                    "since": c.get("certified_on") or c.get("submitted")})
        coming += owed
        # subcontractors: invoices certified (on their way to payment) and not paid - the amount payable on each
        for sb in b.get("subs") or []:
            for pc in sb.get("pcs") or []:
                st = pc.get("status")
                if st in ("Certified", "Prepared", "CM approved", "Verified", "MD approved"):
                    sub_due += pc.get("payable") or 0
                if ((pc.get("flow") or {}).get("turn")) == "md":            # at the Managing Director's desk
                    md_q.append((pc["id"], pc.get("payable") or 0))
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
                    "sub_to_pay": sub_to_pay, "client_open": client_open,
                    # Coming in opens the project the money is owed on (one project), else the Estimation dashboard
                    "coming_go": {"est": {"pid": client_open[0]["pid"], "group": "home", "sec": "dash"}} if len({c["pid"] for c in client_open}) == 1
                    else {"pg": ["estimation", "estdash"]}}

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
    # employed today: active, and no leaving date (or one still to come) - as the staff registers count them
    emp = db.query(models.Employee.staff, models.Employee.pay_group, models.Employee.terminated_on).filter(models.Employee.active == True).all()  # noqa: E712
    here = [e for e in emp if not e.terminated_on or e.terminated_on > t]
    labour = sum(1 for e in here if not e.staff)
    staff = sum(1 for e in here if e.staff and (e.pay_group or "staff") != "local")
    local = sum(1 for e in here if e.staff and (e.pay_group or "") == "local")
    out["people"] = {"on_site": len(at_work), "marked": bool(rows), "labour": labour, "staff": staff, "local": local}

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
                      "amount": c["amount"], "go": {"est": {"pid": c["pid"], "group": "home", "sec": "dash"}}})
    awaiting = db.query(EB.EstBill).filter(EB.EstBill.status == "Awaiting approval").all()
    if awaiting:
        needs.append({"lvl": "amber", "text": f"{len(awaiting)} client bill{'s' if len(awaiting) != 1 else ''} waiting for approval",
                      "amount": r2(sum(b.total_due or 0 for b in awaiting)), "cta": "Approve",
                      # one bill: that bill, open; several: the first one's project, its bills
                      "go": {"est": {"pid": awaiting[0].project_id, "group": "bills", "sec": "ipa", **({"bill": awaiting[0].id} if len(awaiting) == 1 else {})}}})
    if md_q:   # noqa
        needs.append({"lvl": "amber", "text": f"{len(md_q)} subcontractor payment{'s' if len(md_q) != 1 else ''} for your approval",
                      "amount": r2(sum(a for _, a in md_q)), "cta": "Approve",
                      "go": {"url": ES.approve_link([i for i, _ in md_q])}})        # the approval page, every one of them
    if week:
        late = sum(1 for c in week if c.cheque_date < t)
        needs.append({"lvl": "red" if late else "amber",
                      "text": "Cheques clearing this week" + (f" · {late} past date" if late else ""),
                      "amount": r2(sum(c.amount or 0 for c in week)), "go": {"dq": "pdc"}})
    ex = _safe(lambda: EX.summary(db), {})
    n_ex = (ex.get("expired") or 0) + (ex.get("week") or 0) + (ex.get("month") or 0)
    if n_ex:
        needs.append({"lvl": "red" if ex.get("expired") else "amber",
                      "text": f"{n_ex} visas, IDs & licences expire in 30 days" + (f" · {ex['expired']} already expired" if ex.get("expired") else ""),
                      "go": {"dq": "expiry"}, "cta": "View"})
    # open = not yet all delivered: waiting for the office, ordered, or part arrived (the order tracker's open ones)
    OPEN_MR = ("pending", "approved", "arranging", "ordered", "lpo_sent", "partial")
    urgent = db.query(models.MaterialRequest).filter(models.MaterialRequest.status.in_(OPEN_MR),
                                                     models.MaterialRequest.needed_by != None, models.MaterialRequest.needed_by < t).count()  # noqa: E711
    if urgent:
        needs.append({"lvl": "amber", "text": f"{urgent} material request{'s' if urgent != 1 else ''} not delivered by the date site needed {'them' if urgent != 1 else 'it'}",
                      "go": {"dq": "track"}, "cta": "View"})
    out["needs"] = needs

    # ---- a light for each department ------------------------------------------------------------------
    open_mr = db.query(models.MaterialRequest).filter(models.MaterialRequest.status.in_(OPEN_MR)).count()
    tenders = est.get("tenders") or 0
    late_logs = sum(b["summary"].get("overdue") or 0 for _, b in bl)
    month0 = t.replace(day=1)
    bills_m = db.query(EB.EstBill).filter(EB.EstBill.created_at >= month0).count()
    att = round(100.0 * len(at_work) / labour) if labour and rows else None
    light = lambda red, amber: "red" if red else ("amber" if amber else "green")
    out["departments"] = [
        {"name": "Estimation / QS", "value": f"{bills_m} bill{'s' if bills_m != 1 else ''}", "note": f"made this month · {tenders} tender{'s' if tenders != 1 else ''} pricing" + (f" · {late_logs} RFIs / submittals overdue" if late_logs else ""),
         "light": light(late_logs > 5, late_logs > 0 or awaiting), "go": {"pg": ["estimation", "estdash"]}},
        {"name": "Purchasing / Store", "value": f"{open_mr} open", "note": f"material requests not fully delivered · {urgent} late",
         "light": light(urgent > 10, urgent > 0), "go": {"dq": "track"}},
        {"name": "Accounts", "value": _k(pdc30) + " PDC", "note": f"{len(in30)} cheques in 30 days" + (f" · {sum(1 for c in in30 if c.cheque_date < t)} past date" if any(c.cheque_date < t for c in in30) else ""),
         "light": light(any(c.cheque_date < t for c in in30), pdc30 > coming), "go": {"dq": "pdc"}},
        {"name": "HR / Payroll", "value": f"{labour + staff + local} people", "note": f"{labour} labour · {staff} office staff · {local} local staff",
         "light": "green", "go": {"dq": "staff"}},
        {"name": "Site / Labour", "value": (f"{att}%" if att is not None else "not in"), "note": "attendance today" if att is not None else "today's attendance not marked yet",
         "light": light(att is not None and att < 60, att is None or att < 80), "go": {"dq": "att"}},
        {"name": "PRO / Visas", "value": f"{n_ex} expiring", "note": "in 30 days" + (f" · {ex.get('expired')} expired" if ex.get("expired") else ""),
         "light": light(bool(ex.get("expired")), n_ex > 0), "go": {"dq": "expiry"}},
    ]
    return out


# ---- the slower cards, loaded after the page shows (14 Nov 2026): project profit, spend this month, expiring ----
_EXTRA = {}                      # one copy for a few minutes - the figures come from all the payroll cycles and LPOs
_EXTRA_SECONDS = 300


def _prev_month_same_day(t):
    first = t.replace(day=1)
    pm_end = first - timedelta(days=1)
    return pm_end.replace(day=1), pm_end.replace(day=min(t.day, pm_end.day))


@router.get("/permissions/owner/more")
def overview_more(db: Session = Depends(get_db), user: models.User = Depends(_owner)):
    import time
    t = M._dubai_today()
    hit = _EXTRA.get(t)
    if hit and time.monotonic() - hit[0] < _EXTRA_SECONDS:
        return hit[1]
    out = {"today": t.isoformat()}
    import estimation as ES
    import projexpense as PX

    def bundles():
        rules = ES._rules(db)
        projects = db.query(ES.EstProject).filter(ES.EstProject.status != "Closed").order_by(ES.EstProject.code).all()
        pre = ES._preload(db, projects, with_files=False)
        return [(p, ES.project_bundle(db, p, rules, pre)) for p in projects]
    bl = _safe(bundles, [])
    m1 = t.replace(day=1)
    p1, p2 = _prev_month_same_day(t)

    # ---- project profit: work certified to the client vs what the project has cost so far -----------------
    # cost = Accounts > Project expense (labour, LPOs, store issues, petty cash) + subcontract work certified
    def profit():
        g = PX.gather(db)
        cost = {r["code"]: r for r in g["rows"]}
        rows = []
        for p, b in bl:
            s_ = b["summary"]
            subs = r2(sum(sb.get("work_done") or 0 for sb in b.get("subs") or [] if sb.get("status") != "Cancelled"))
            px = cost.get(str(p.code or "").strip(), {})
            spent = r2((px.get("total") or 0) + subs)
            work = r2(s_.get("client_work") or 0)
            if not work and not spent:
                continue
            rows.append({"id": p.id, "code": p.code, "name": p.name or "", "certified": work, "cost": spent,
                         "labour": r2(px.get("labour")), "materials": r2((px.get("lpo") or 0) + (px.get("store") or 0)),
                         "petty": r2(px.get("petty")), "subs": subs,
                         "margin": round(100.0 * (work - spent) / work, 1) if work else None})
        # losing first, then the biggest
        rows.sort(key=lambda r: (0 if r["margin"] is not None and r["margin"] < 0 else 1, -(r["certified"] or 0)))
        return rows
    out["profit"] = _safe(profit, [])

    # ---- spend this month (and last month to the same day) --------------------------------------------------
    def spend(d1, d2):
        g = PX.gather(db, d1.isoformat(), d2.isoformat())
        tt = g["totals"]
        sub = 0.0
        for p, b in bl:
            for sb in b.get("subs") or []:
                for pc in sb.get("pcs") or []:
                    on = str(pc.get("certified_on") or "")[:10]
                    if on and d1.isoformat() <= on <= d2.isoformat():
                        sub += pc.get("this") or 0
        top = max(g["rows"], key=lambda r: r["total"], default=None)
        return {"labour": r2(tt.get("labour")), "materials": r2((tt.get("lpo") or 0) + (tt.get("store") or 0)),
                "petty": r2(tt.get("petty")), "subs": r2(sub),
                "top": {"code": top["code"], "amount": r2(top["total"])} if top and top["total"] else None}
    now_ = _safe(lambda: spend(m1, t), None)
    was = _safe(lambda: spend(p1, p2), None)
    if now_:
        now_["total"] = r2(now_["labour"] + now_["materials"] + now_["petty"] + now_["subs"])
        if was:   # like for like without labour: this month's payroll is only in once it is run
            a = now_["materials"] + now_["petty"] + now_["subs"]
            b_ = was["materials"] + was["petty"] + was["subs"]
            now_["vs_prev_pct"] = round(100.0 * (a - b_) / b_, 0) if b_ else None
            now_["prev_label"] = p1.strftime("%B")
    out["spend"] = now_

    # ---- expiring in 30 days (HR > Expiry): company documents one by one, people's visas / IDs as a count -----
    def expiring():
        import expiry as EX
        marks = EX.started_keys(db)
        its = [i for i in EX._items(db) if not EX._held(i, marks) and i["days_left"] <= 30]
        comp = sorted([i for i in its if i["type"] == "company"], key=lambda i: i["days_left"])
        ppl = [i for i in its if i["type"] == "person"]
        return {"count": len(its), "expired": sum(1 for i in its if i["days_left"] < 0),
                "company": [{"what": f"{i['who']}" + (f" · {i['what']}" if i.get("what") and i["what"] not in i["who"] else ""),
                             "days": i["days_left"]} for i in comp[:4]],
                "people": len({i["who"] for i in ppl}), "people_first": min((i["days_left"] for i in ppl), default=None)}
    out["expiring"] = _safe(expiring, None)
    _EXTRA.clear()
    _EXTRA[t] = (time.monotonic(), out)
    return out


def _k(v):
    v = float(v or 0)
    if abs(v) >= 1e6:
        return f"{v / 1e6:.2f}M"
    if abs(v) >= 1e3:
        return f"{v / 1e3:.0f}K"
    return f"{v:,.0f}"

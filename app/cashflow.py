"""Accounts > Cash forecast (10 Nov 2026).

One page: what is in the bank, what goes out and what comes in, month by month - and the balance after each.
Everything the app already knows is collected by itself, so the chief accountant adds only what it cannot know:

  in the bank now   the last ADCB statement uploaded on Accounts > Bank (its closing balance), less / plus what was
                    entered on the Bank tab after the statement's last day (paid, not on a statement yet)
  going out         every PDC not cleared (cheques, salaries, rent ... as on the PDC register; past-date ones today)
                    payments entered on the Bank tab for a later date
                    subcontractor certificates certified and not paid (Estimation) - due after the subcontract's days
                    salaries for a month with no salary on the PDC register: the last payroll, office + labour
                    expected expenses typed here (CashExpected) - once or repeating
  coming in         payment certificates sent to clients and not paid (Estimation) - due 30 days after certified,
                    45 after submitted; money expected typed here
A line found by itself can be moved to another date or left out (CashMove); nothing is counted twice: a cheque
the forecast lines typed here (money in or out) stay here (nothing is sent to another page); a subcontractor certificate with a cheque already written is the PDC.
"""
import re
from datetime import date, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

import main as M
import models
from database import get_db

router = APIRouter()
ACC = Depends(M.require_any_screen("accounts_cash"))   # the chief accountant and admin
r2 = lambda v: round(float(v or 0) + 0.0, 2)
SAL = re.compile(r"\b(salary|salaries|payroll|wps)\b", re.I)


def _norm(s):
    return re.sub(r"\b(llc|l\.l\.c|fze|fzc|co|company|trading|est|establishment|the|and|&)\b", " ", (s or "").lower()).replace(".", " ").split()


def _same_party(a, b):
    x, y = set(_norm(a)), set(_norm(b))
    return bool(x and y) and (x <= y or y <= x or len(x & y) >= 2)


def _add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    y += d.year; m += 1
    import calendar
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _bank_now(db, today):
    """The balance on the last statement line, and the portal's Bank entries after it."""
    banks = [b for (b,) in db.query(models.BankStmtLine.bank).distinct().all()]
    out = {"balance": 0.0, "banks": [], "since": [], "as_of": None}
    for bk in banks:
        last = (db.query(models.BankStmtLine).filter(models.BankStmtLine.bank == bk, models.BankStmtLine.balance.isnot(None))
                .order_by(models.BankStmtLine.on_date.desc(), models.BankStmtLine.id.desc()).first())
        if not last:
            continue
        out["banks"].append({"bank": bk, "balance": r2(last.balance), "as_of": last.on_date.isoformat()})
        out["balance"] += last.balance or 0
        out["as_of"] = max(out["as_of"] or last.on_date, last.on_date)
    return out


def collect(db, months=3, with_in=True):
    t = M._dubai_today()
    end = _add_months(date(t.year, t.month, 1), months) - timedelta(days=1)
    bank = _bank_now(db, t)
    as_of = bank["as_of"] or t
    bank["as_of"] = bank["as_of"].isoformat() if bank["as_of"] else None
    moves = {m.key: m for m in db.query(models.CashMove).all()}
    items = []

    def add(key, on, what, typ, src, amount, direction="out", sure="sure", link=None, note="", fixed=False):
        mv = moves.get(key)
        if mv and mv.skip:
            return
        d0, a0, w0 = on, amount, what
        if mv:                                            # changed on the forecast: date, amount, wording, note
            on = mv.on_date or on
            amount = mv.amount if mv.amount is not None else amount
            what = mv.what or what
            note = mv.note or note
        late = on < t
        on = max(on, t)
        if on > end or not amount:
            return
        edited = bool(mv and (mv.on_date or mv.amount is not None or mv.what or mv.note))
        items.append({"key": key, "date": on.isoformat(), "was": d0.isoformat() if d0 != on else "", "late": late, "what": what, "type": typ,
                      "src": src, "in": r2(amount) if direction == "in" else 0.0, "out": r2(amount) if direction == "out" else 0.0,
                      "sure": sure, "link": link or {}, "note": note, "moved": edited, "edited": edited,
                      "orig": {"date": d0.isoformat(), "amount": r2(a0), "what": w0} if edited else None})

    # ---- PDCs not cleared: cheques, salaries, rent ... (past-date ones are counted today)
    pdcs = db.query(models.Pdc).filter(models.Pdc.status == "pending").all()
    for c in pdcs:
        nm = c.payee or "Cheque"
        typ = "salary" if SAL.search(nm) else "cheque"
        add(f"pdc:{c.id}", c.cheque_date, nm + (" - day to fix" if c.date_tbc else "") + (f" · cheque {c.cheque_no}" if c.cheque_no else ""),
            typ, "PDC register", c.amount or 0, link={"dq": "pdc"}, note=c.notes or "", fixed=True)
    pdc_sal_months = {(c.cheque_date.year, c.cheque_date.month) for c in pdcs if SAL.search(c.payee or "")}

    # ---- the Bank tab: entered after the statement's last day - paid (not on a statement yet) or for a later date
    ent = db.query(models.BankEntry).filter(models.BankEntry.on_date > as_of).all()
    pdc_nos = {(c.cheque_no or "").strip().lstrip("0") for c in pdcs if (c.cheque_no or "").strip()}
    paid_since = 0.0
    for e in ent:
        if e.kind == "transfer":
            continue
        if (e.reference or "").strip().lstrip("0") in pdc_nos:
            continue                                                # the PDC is the same cheque
        sign = 1 if e.kind == "customer" else -1
        if e.on_date <= t:
            paid_since += sign * (e.amount or 0)
            bank["since"].append({"date": e.on_date.isoformat(), "party": e.party or e.kind, "amount": r2(sign * (e.amount or 0))})
        else:
            add(f"bank:{e.id}", e.on_date, e.party or e.kind.title(), "cheque" if e.kind != "customer" else "client", "Bank tab",
                e.amount or 0, "in" if sign > 0 else "out", link={"pg": ["accounts", "bank"]}, fixed=True)
    bank["paid_since"] = r2(paid_since)
    bank["now"] = r2(bank["balance"] + paid_since)

    # ---- Estimation: client certificates not paid (in), subcontractor certificates certified and not paid (out)
    try:
        import estimation as ES
        rules = ES._rules(db)
        projects = db.query(ES.EstProject).filter(ES.EstProject.status != "Closed").all()
        pre = ES._preload(db, projects, with_files=False)
        for p in projects:
            b = ES.project_bundle(db, p, rules, pre)
            if with_in:
                for c in b.get("clientpcs") or []:
                    if c.get("status") in ("Submitted", "Certified", "Invoiced") and (c.get("payable") or 0) > 0:
                        base = c.get("certified_on") or c.get("submitted")
                        try:
                            d = date.fromisoformat(str(base)[:10]) + timedelta(days=30 if c.get("certified_on") else 45)
                        except ValueError:
                            d = t + timedelta(days=30)
                        add(f"client:{c.get('id')}", d, f"{p.code} - client certificate {c.get('seq')} ({c['status'].lower()})", "client", "Estimation",
                            c["payable"], "in", "likely", link={"est": {"pid": p.id, "group": "bills", "sec": "cpc"}})
            for sb in b.get("subs") or []:
                for pc in sb.get("pcs") or []:
                    if pc.get("status") not in ("Certified", "Prepared", "CM approved", "Verified", "MD approved") or not (pc.get("payable") or 0) > 0:
                        continue
                    nm = sb.get("name") or "Subcontractor"
                    if any(_same_party(nm, c.payee) and abs((c.amount or 0) - pc["payable"]) < 1.01 for c in pdcs):
                        continue                                  # its cheque is on the PDC register already
                    base = pc.get("to_accounts") or pc.get("certified_on") or pc.get("issued")
                    try:
                        d = date.fromisoformat(str(base)[:10]) + timedelta(days=int(sb.get("pay_days") or 0))
                    except (ValueError, TypeError):
                        d = t
                    add(f"sub:{pc.get('id')}", d, f"{p.code} - {nm} certificate {pc.get('seq') or ''} ({pc['status']})".replace("  ", " "), "sub", "Estimation",
                        pc["payable"], "out", "sure" if pc["status"] in ("MD approved", "Verified") else "likely",
                        link={"est": {"pid": p.id, "group": "subs", "sec": "inv"}})
    except Exception as e:
        print("cash forecast - estimation:", e)

    # ---- salaries for a month with none on the PDC register: the last payroll (office + labour)
    try:
        office = db.query(models.PayrollRun).order_by(models.PayrollRun.id.desc()).first()
        off_tot = 0.0
        if office:
            off_tot = sum(l.net_pay or 0 for l in db.query(models.PayrollLine).join(models.PayrollRun, models.PayrollLine.run_id == models.PayrollRun.id)
                          .filter(models.PayrollRun.month_year == office.month_year).all())
        lab = db.query(models.EmployeeSummary.month_year).order_by(models.EmployeeSummary.updated_at.desc()).first()
        lab_months = [m for (m,) in db.query(models.EmployeeSummary.month_year).distinct().all()]
        from datetime import datetime as _dt
        def mkey(s):
            try:
                return _dt.strptime(s, "%B %Y")
            except Exception:
                return _dt.min
        full = [m for m in sorted(lab_months, key=mkey) if mkey(m).date() < date(t.year, t.month, 1)]
        lab_tot = sum(x.final_salary or 0 for x in db.query(models.EmployeeSummary).filter(models.EmployeeSummary.month_year == full[-1]).all()) if full else 0.0
        est = r2(off_tot + lab_tot)
        d = date(t.year, t.month, 1)
        while d <= end:
            if (d.year, d.month) not in pdc_sal_months and est:
                add(f"sal:{d.year}-{d.month:02d}", date(d.year, d.month, 28), f"Salaries {d:%B %Y}",
                    "salary", "Payroll", est, "out", "likely", link={"pg": ["payroll"]}, note=f"as the last payroll: office {off_tot:,.0f} + labour {lab_tot:,.0f}")
            d = _add_months(d, 1)
    except Exception as e:
        print("cash forecast - payroll:", e)

    # ---- money in and out typed here by Accounts - on the forecast only
    exp = db.query(models.CashExpected).filter(models.CashExpected.status == "open").all()
    step = {"month": 1, "quarter": 3, "year": 12}
    for x in exp:
        if x.direction == "in" and not with_in:          # "Out only": no money in at all
            continue
        d, n = x.on_date, 0
        while d <= end and n < 240:
            if (not x.until or d <= x.until) and (x.repeat not in step or d >= t):   # a repeat started earlier counts from now on
                add(f"exp:{x.id}:{n}", d, x.what + (f" ({x.kind})" if x.kind and x.kind.lower() not in x.what.lower() else ""), "expected",
                    "Expected", x.amount or 0, x.direction or "out", x.sure or "sure", link={"exp": x.id}, note=x.note or "", fixed=True)
            if x.repeat not in step:
                break
            d = _add_months(x.on_date, step[x.repeat] * (n + 1)); n += 1
    items.sort(key=lambda x: (x["date"], -x["in"], x["out"]))
    bal = bank["now"]
    for it in items:
        bal += it["in"] - it["out"]
        it["after"] = r2(bal)
    # months
    keep = 500000.0
    s = db.query(models.Setting).filter(models.Setting.key == "cash_min_keep").first()
    if s:
        try:
            keep = float(s.value)
        except ValueError:
            pass
    mo, d, opening = [], date(t.year, t.month, 1), bank["now"]
    while d <= end:
        nxt = _add_months(d, 1)
        mine = [i for i in items if d.isoformat() <= i["date"] < nxt.isoformat()]
        by = {}
        for i in mine:
            k = i["type"]
            by.setdefault(k, 0.0)
            by[k] += i["in"] - i["out"]
        cin, cout = sum(i["in"] for i in mine), sum(i["out"] for i in mine)
        low = min([opening] + [i["after"] for i in mine])
        mo.append({"m": d.isoformat()[:7], "label": d.strftime("%B"), "from": max(d, t).isoformat(), "to": (nxt - timedelta(days=1)).isoformat(),
                   "opening": r2(opening), "in": r2(cin), "out": r2(cout), "closing": r2(opening + cin - cout), "low": r2(low), "by": {k: r2(v) for k, v in by.items()}})
        opening = opening + cin - cout
        d = nxt
    # the picture: the lowest point, the first day below the minimum, the biggest payments, what comes in
    low = min([{"date": t.isoformat(), "after": bank["now"], "what": "now"}] + items, key=lambda i: i["after"])
    below = next((i for i in items if i["after"] < keep), None)
    groups = {}
    for i in items:
        if not i["out"]:
            continue
        k = ("salary", "Salaries") if i["type"] == "salary" else ("sub", "Subcontractor certificates") if i["type"] == "sub" else (i["key"], i["what"].split(" · cheque")[0])
        g = groups.setdefault(k, {"what": k[1], "type": i["type"], "amount": 0.0, "dates": [], "n": 0, "late": False})
        g["amount"] += i["out"]; g["dates"].append(i["date"]); g["n"] += 1; g["late"] = g["late"] or i["late"]
    biggest = sorted(groups.values(), key=lambda g: -g["amount"])[:6]
    for g in biggest:
        g["amount"] = r2(g["amount"])
    coming = [i for i in items if i["in"]]
    tot_out = r2(sum(i["out"] for i in items))
    by_type = {}
    for i in items:
        if i["out"]:
            by_type[i["type"]] = r2(by_type.get(i["type"], 0) + i["out"])
    return {"today": t.isoformat(), "bank": bank, "items": items, "months": mo, "keep": keep,
            "low": {"date": low["date"], "amount": r2(low["after"]), "what": low["what"]},
            "below": {"date": below["date"], "what": below["what"], "amount": below["after"]} if below else None,
            "biggest": biggest, "coming": coming, "total_out": tot_out, "total_in": r2(sum(i["in"] for i in items)), "by_type": by_type}


@router.get("/store/cash/forecast")
def forecast(months: int = 3, with_in: int = 1, db: Session = Depends(get_db), user: models.User = ACC):
    out = collect(db, max(1, min(12, months)), bool(with_in))
    out["expected"] = [{"id": x.id, "what": x.what, "kind": x.kind, "amount": x.amount, "on_date": x.on_date.isoformat(), "sure": x.sure, "repeat": x.repeat,
                        "direction": x.direction, "note": x.note, "expiry_id": x.expiry_id}
                       for x in db.query(models.CashExpected).filter(models.CashExpected.status == "open").all()]
    out["kinds_in"] = ["Client payment", "Advance", "Retention release", "Loan / capital", "Deposit back / refund", "Cash in hand", "Other"]
    out["kinds"] = ["Supplier", "Subcontractor", "Insurance", "Licence / permit", "Visa / labour", "Rent", "Deposit / guarantee", "Vehicle", "Tax / VAT", "Loan / bank", "Other"]
    return out


def _clean(p):
    what = " ".join(str(p.get("what") or "").split())[:200]
    if not what:
        raise HTTPException(400, "What is it for?")
    try:
        amount = round(float(str(p.get("amount") or "").replace(",", "")), 2)
    except ValueError:
        raise HTTPException(400, "Give the amount.")
    if amount <= 0:
        raise HTTPException(400, "The amount must be more than 0.")
    d = M._as_date(p.get("on_date")) if p.get("on_date") else None
    if not d:
        raise HTTPException(400, "Give the date it is expected.")
    rep = p.get("repeat") if p.get("repeat") in ("once", "month", "quarter", "year") else "once"
    return dict(what=what, kind=str(p.get("kind") or "")[:60], amount=amount, on_date=d, sure=p.get("sure") if p.get("sure") in ("sure", "likely", "maybe") else "sure",
                repeat=rep, until=M._as_date(p.get("until")) if p.get("until") else None, direction="in" if p.get("direction") == "in" else "out",
                bank=str(p.get("bank") or "ADCB")[:40], note=str(p.get("note") or "")[:500], expiry_id=None)


@router.post("/store/cash/expected")
def add_expected(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = ACC):
    v = _clean(payload)
    if not payload.get("force") and v["direction"] == "out":   # already on the PDC register: it would count twice
        for c in db.query(models.Pdc).filter(models.Pdc.status == "pending").all():
            if _same_party(v["what"], c.payee) and abs((c.amount or 0) - v["amount"]) < 1.01:
                raise HTTPException(409, f"Already on the PDC register: {c.payee} - AED {c.amount:,.2f} on {c.cheque_date:%d/%m/%Y}"
                                         f"{' (cheque ' + c.cheque_no + ')' if c.cheque_no else ''}. It is counted from there - add it anyway?")
    x = models.CashExpected(**v, created_by=user.id, updated_by=user.id)
    db.add(x); db.commit()
    M.log_action(db, user.id, "cash_expected_add", f"Expected {'in' if x.direction == 'in' else 'expense'}: {x.what} AED {x.amount:,.2f} on {x.on_date:%d/%m/%Y} ({x.repeat})")
    return {"ok": True, "id": x.id}


@router.put("/store/cash/expected/{xid}")
def edit_expected(xid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = ACC):
    x = db.query(models.CashExpected).get(xid)
    if not x:
        raise HTTPException(404, "Not found.")
    if payload.get("status") in ("paid", "dropped", "open"):
        x.status = payload["status"]
    else:
        for k, v in _clean(payload).items():
            setattr(x, k, v)
    x.updated_by = user.id
    db.commit()
    M.log_action(db, user.id, "cash_expected_edit", f"Expected {x.what}: {x.status} AED {x.amount:,.2f} on {x.on_date:%d/%m/%Y}")
    return {"ok": True}


@router.post("/store/cash/move")
def move_line(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = ACC):
    """Any line the forecast found (PDC, Bank tab, client bill, subcontractor certificate, salaries) changed here only:
    {"key", "on_date", "amount", "what", "note"}; {"key", "skip": true} left out; {"key", "reset": true} back as found.
    The PDC register, the bills and the bank are not touched."""
    key = str(payload.get("key") or "")
    if not re.match(r"^(client|sub|sal|pdc|bank):[\w-]+$", key):
        raise HTTPException(400, "That line cannot be changed here.")
    m = db.query(models.CashMove).filter(models.CashMove.key == key).first()
    if payload.get("reset"):
        if m:
            db.delete(m)
        how = "back as found"
    else:
        if not m:
            m = models.CashMove(key=key); db.add(m)
        if payload.get("skip"):
            m.skip, how = True, "left out"
        else:
            m.skip = False
            if "on_date" in payload:
                m.on_date = M._as_date(payload["on_date"]) if payload.get("on_date") else None
            if "amount" in payload:
                a = str(payload.get("amount") or "").replace(",", "").strip()
                try:
                    m.amount = round(float(a), 2) if a else None
                except ValueError:
                    raise HTTPException(400, "Give the amount as a number.")
                if m.amount is not None and m.amount < 0:
                    raise HTTPException(400, "The amount cannot be below 0 (pick Coming in / Going out by the line).")
            if "what" in payload:
                m.what = " ".join(str(payload.get("what") or "").split())[:200] or None
            if "note" in payload:
                m.note = str(payload.get("note") or "")[:300]
            how = f"changed: {m.what or ''} {('AED ' + format(m.amount, ',.2f')) if m.amount is not None else ''} {m.on_date or ''}".strip()
        m.updated_by = user.id
    db.commit()
    M.log_action(db, user.id, "cash_move", f"{key}: {how}")
    return {"ok": True}


@router.post("/store/cash/keep")
def set_keep(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = ACC):
    try:
        v = round(float(str(payload.get("keep")).replace(",", "")), 2)
    except ValueError:
        raise HTTPException(400, "Give an amount.")
    s = db.query(models.Setting).filter(models.Setting.key == "cash_min_keep").first() or models.Setting(key="cash_min_keep")
    s.value = str(v); db.add(s); db.commit()
    return {"ok": True}


@router.get("/export/accounts/cash")
def export(token: str, format: str = "pdf", months: int = 3, with_in: int = 1, db: Session = Depends(get_db)):
    from urllib.parse import quote
    import auth, export_web
    u = auth.get_download_user_from_token(token, db)
    if u.role != "admin" and "accounts_cash" not in set(M.effective_permissions(u)):
        raise HTTPException(403, "Accounts only.")
    f = collect(db, max(1, min(12, months)), bool(with_in))
    TY = {"cheque": "Cheque", "salary": "Salaries", "sub": "Subcontractor", "client": "Client bill", "expected": "Expected"}
    rows = [{"Date": "/".join(reversed(i["date"].split("-"))), "What": i["what"] + (" (past date)" if i["late"] else ""), "Type": TY.get(i["type"], i["type"]),
             "From": i["src"], "In (AED)": i["in"] or "", "Out (AED)": i["out"] or "", "Balance after (AED)": i["after"]} for i in f["items"]]
    sub = (f"In the bank now AED {f['bank']['now']:,.2f} (statement of {'/'.join(reversed((f['bank']['as_of'] or '').split('-')))}) | "
           + " | ".join(f"{m['label']}: in {m['in']:,.0f}, out {m['out']:,.0f}, closing {m['closing']:,.0f}" for m in f["months"]))
    import cash_report as CR
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo
    stamp = _dt.now(ZoneInfo("Asia/Dubai")).strftime("%d/%m/%Y %H:%M")
    name = f"Cash_forecast_{M._dubai_today():%d.%m.%Y}"
    if format == "view":
        vt = quote(auth.create_view_token(u.username), safe="")
        base = f"/export/accounts/cash?months={months}&with_in={with_in}&token={vt}"
        from fastapi.responses import HTMLResponse
        return HTMLResponse(CR.report_html(f, base + "&format=pdf", base + "&format=excel", export_web.logo_data_uri(), stamp))
    if format == "excel":
        return StreamingResponse(export_web.build_store_report_excel("Cash forecast", rows, sub, money_cols=["In (AED)", "Out (AED)", "Balance after (AED)"]),
                                 media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename={name}.xlsx"})
    return StreamingResponse(CR.report_pdf(f, export_web.LOGO_PATH, stamp), media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})

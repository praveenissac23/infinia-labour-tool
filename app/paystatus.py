"""Paid status and payslips - office payroll (Payroll > Office payroll > Salary cycle & statements, both the one-company
sheet and All companies) and labour payroll (Payroll > Labour payroll > Salary cards), with one set of rules (29 Oct 2026).

  Mark paid      - any time, even while the office sheet is a draft (staff paid early, or leaving). Four kinds:
                     regular     salary to date (the rest stays as a balance until it is paid)
                     early_full  the whole month / cycle now
                     final       final settlement: salary to the last working day + gratuity, leave salary and notice
                                 (the existing Gratuity working), the whole loan balance off, then he is made inactive
                     custom      an amount typed
                   and a balance payment for what is still owed. Date, mode (WPS / bank / cash / cheque), reference, note.
  Lock           - once paid in full only that row is locked: an office row keeps the figures it was paid on; a change
                   to that month afterwards (an absence, an addition) is carried to next month's additions & deductions.
                   A labour card follows attendance, so its change after payment is carried the same way.
  Loans          - the month's instalment is taken when the row is paid in full; a final settlement takes the whole balance.
                   Approve & lock (office) and Pay full salary now (labour) leave paid rows alone.
  Payslips       - generated after payment, a new version each time, never written over; View / Download, a ZIP of all.
                   A final settlement gets the settlement slip. Internal only - nothing is emailed.
"""
import io
import json
import zipfile
from datetime import date, datetime, timedelta
from html import escape

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

import auth
import main as M
import models
import services
from database import get_db

router = APIRouter()
KINDS = ("office", "labour")
TYPES = {"regular": "Regular", "balance": "Balance", "early_full": "Early full month", "final": "Final settlement", "custom": "Custom"}
MODES = {"wps": "WPS", "bank": "Bank transfer", "cash": "Cash", "cheque": "Cheque"}
RIGHT = {"office": "hrpayroll", "labour": "combine"}


def _can(user, kind):
    if kind not in KINDS:
        raise HTTPException(status_code=400, detail="Office or labour?")
    if user.role != "admin" and RIGHT[kind] not in M.effective_permissions(user):
        raise HTTPException(status_code=403, detail="Payroll is not open to this login.")


def _r2(v):
    return round(float(v or 0) + 1e-9, 2)


def _next_month(label):
    d = datetime.strptime(f"1 {label}", "%d %B %Y").date()
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1).strftime("%B %Y")


def _payments(db, kind, employee_id, month_year):
    return (db.query(models.PayPayment).filter(models.PayPayment.kind == kind, models.PayPayment.employee_id == employee_id,
                                               models.PayPayment.month_year == month_year, models.PayPayment.void == False)  # noqa: E712
              .order_by(models.PayPayment.id).all())


def _cycle_closed(month_year):
    try:
        _cs, ce, _ = M.pcyc.cycle_bounds_for(datetime.strptime(f"25 {month_year}", "%d %B %Y").date())
    except ValueError:
        return True
    return M._dubai_today() > ce


# ---- the row: what is due, what is paid, whether it is locked -----------------------------------------------------
def _office_line(db, line_id):
    l = db.get(models.PayrollLine, line_id)
    if not l:
        raise HTTPException(status_code=404, detail="That row is no longer on the sheet - refresh the page.")
    return l


def office_to_date(db, r, l):
    """Salary to date for one office line, as the sheet shows it."""
    a, b = M._staff_month_bounds(r.month_year)
    today = M._dubai_today()
    days = (b - a).days + 1
    done = 0 if today < a else days if today > b else (today - a).days + 1
    full = M._line_full_month(db, r, l.employee_id)
    if full or done >= days:
        return _r2(l.net_pay)
    earned = (l.fixed_salary or 0) * done / days
    return _r2(earned - (l.deduction or 0) - (l.statutory or 0) + (l.other_allowance or 0) + (l.leave_salary or 0) + (l.air_ticket or 0))


def _card(db, e, month_year):
    return (db.query(models.EmployeeSummary).options(joinedload(models.EmployeeSummary.adjustments))
              .filter(models.EmployeeSummary.emp_no == e.emp_no, models.EmployeeSummary.month_year == month_year).first())


def row_state(db, kind, e, month_year, current_due, pays=None):
    """{state, paid, due, balance, locked, payments, carry} for one person's month."""
    pays = pays if pays is not None else _payments(db, kind, e.id, month_year)
    paid = _r2(sum(p.amount or 0 for p in pays))
    final = next((p for p in pays if p.pay_type == "final"), None)
    early = any(p.pay_type == "early_full" for p in pays)
    if final:
        due = _r2(final.due)
    elif kind == "office" and pays and _frozen(pays):
        due = _r2(pays[-1].due)                   # frozen on the figures it was paid on
    else:
        due = _r2(current_due)
    full = paid >= due - 0.01 and pays
    locked = bool(full and (kind == "office" or final or early or _cycle_closed(month_year)))
    if not pays:
        state = "none"
    elif final:
        state = "settled"
    elif locked:
        state = "paid"
    elif full and kind == "labour":
        state = "todate"                    # the card is paid up to today; it grows until the cycle ends
    else:
        state = "partial"
    carries = (db.query(models.PayCarry).filter(models.PayCarry.kind == kind, models.PayCarry.employee_id == e.id,
                                                models.PayCarry.from_month == month_year).all())
    return {"state": state, "paid": paid, "due": due, "balance": _r2(max(due - paid, 0)), "locked": locked,
            "carry": _r2(sum(c.amount or 0 for c in carries)), "carry_to": carries[0].to_month if carries else "",
            "payments": [_pay_dict(p) for p in pays]}


def _frozen(pays):
    """An office row is frozen on the figures it was paid on once it is paid in full."""
    paid = sum(p.amount or 0 for p in pays)
    due = pays[-1].due or 0
    return any(p.pay_type == "final" for p in pays) or paid >= due - 0.01


def _pay_dict(p):
    return {"id": p.id, "type": p.pay_type, "type_label": TYPES.get(p.pay_type, p.pay_type), "amount": _r2(p.amount),
            "due": _r2(p.due), "paid_on": p.paid_on.isoformat(), "paid_on_text": p.paid_on.strftime("%d/%m/%Y"),
            "mode": p.mode, "mode_label": MODES.get(p.mode, p.mode), "reference": p.reference or "", "note": p.note or "",
            "loan_repaid": _r2(p.loan_repaid)}


def _slips(db, payment_ids):
    out = {}
    if not payment_ids:
        return out
    for s in (db.query(models.Payslip).filter(models.Payslip.payment_id.in_(payment_ids))
                .order_by(models.Payslip.payment_id, models.Payslip.version).all()):
        out.setdefault(s.payment_id, []).append({"id": s.id, "version": s.version, "slip_no": s.slip_no, "type": s.slip_type,
                                                 "created": s.created_at.strftime("%d/%m/%Y %H:%M") if s.created_at else ""})
    return out


def office_rows(db, r):
    """Pay status for every line of an office run, keyed by line id - added to the sheet by main._run_dict."""
    out = {}
    pays = (db.query(models.PayPayment).filter(models.PayPayment.kind == "office", models.PayPayment.run_id == r.id,
                                               models.PayPayment.void == False).order_by(models.PayPayment.id).all())  # noqa: E712
    by = {}
    for p in pays:
        by.setdefault(p.source_id, []).append(p)
    slips = _slips(db, [p.id for p in pays])
    for l in r.lines:
        e = db.get(models.Employee, l.employee_id)
        st = row_state(db, "office", e, r.month_year, l.net_pay, by.get(l.id, []))
        st["slips"] = {str(p["id"]): slips.get(p["id"], []) for p in st["payments"]}
        st["to_date"] = office_to_date(db, r, l)
        out[l.id] = st
    return out


def paid_line_ids(db, r):
    """Office lines paid in full on this run - frozen on the figures they were paid on."""
    pays = (db.query(models.PayPayment).filter(models.PayPayment.kind == "office", models.PayPayment.run_id == r.id,
                                               models.PayPayment.void == False).order_by(models.PayPayment.id).all())  # noqa: E712
    by = {}
    for p in pays:
        by.setdefault(p.source_id, []).append(p)
    return {lid for lid, ps in by.items() if _frozen(ps)}


def labour_paid_emp_nos(db, month_year, emp_nos):
    """Workers among emp_nos already paid what their card is due for the cycle (paid in full, settled, or paid to date)."""
    out = set()
    for c in (db.query(models.EmployeeSummary).options(joinedload(models.EmployeeSummary.adjustments))
                .filter(models.EmployeeSummary.month_year == month_year, models.EmployeeSummary.emp_no.in_(list(emp_nos))).all()):
        e = db.query(models.Employee).filter(models.Employee.emp_no == c.emp_no).first()
        if not e:
            continue
        pays = _payments(db, "labour", e.id, month_year)
        if pays and row_state(db, "labour", e, month_year, services.adjusted_final_salary(c), pays)["state"] in ("paid", "settled", "todate"):
            out.add(c.emp_no)
    return out


# ---- carried to next month -------------------------------------------------------------------------------------------
def _set_carry(db, kind, e, payment, from_month, diff, why):
    """Keep one carry per payment, in step with the difference; nothing when there is none."""
    c = db.query(models.PayCarry).filter(models.PayCarry.payment_id == payment.id).first()
    diff = _r2(diff)
    if abs(diff) < 0.01:
        if c:
            _drop_target(db, c)
            db.delete(c)
        return
    if not e.active:
        return                                    # left: nothing to carry to - shown on the row as a difference
    to = _next_month(from_month)
    note = f"Carried from {from_month}: {why}"[:200]
    if kind == "office":
        it = db.get(models.PayItem, c.target_id) if c and c.target_id else None
        if it is None:
            it = models.PayItem(employee_id=e.id, month_year=to, category="carry", source=f"carry:{payment.id}",
                                on_date=M._dubai_today())
            db.add(it)
        it.direction, it.amount, it.notes, it.month_year = ("add" if diff > 0 else "deduct"), abs(diff), note, to
        db.flush()
        tid = it.id
    else:
        card = _card(db, e, to) or services.recalculate_summary(db, e, to)
        adj = db.get(models.SalaryAdjustment, c.target_id) if c and c.target_id else None
        if adj is None:
            adj = models.SalaryAdjustment(summary_id=card.id, description=note, amount=abs(diff), is_deduction=diff < 0)
            db.add(adj)
        adj.description, adj.amount, adj.is_deduction = note, abs(diff), diff < 0
        db.flush()
        tid = adj.id
    if c is None:
        c = models.PayCarry(kind=kind, employee_id=e.id, payment_id=payment.id, from_month=from_month)
        db.add(c)
    c.to_month, c.amount, c.target_id, c.note = to, diff, tid, note


def _drop_target(db, c):
    t = db.get(models.PayItem if c.kind == "office" else models.SalaryAdjustment, c.target_id) if c.target_id else None
    if t is not None:
        db.delete(t)


def office_carry(db, r, l, e, a, b):
    """A frozen (paid) office line: work the month out again from the registers, and carry any difference."""
    pays = _payments(db, "office", e.id, r.month_year)
    if not pays or any(p.pay_type == "final" for p in pays):
        return
    tmp = models.PayrollLine(employee_id=l.employee_id, loan_edited=True, remark_edited=True,
                             loan_deduction=l.loan_deduction, remarks=l.remarks)
    M._fill_line(db, tmp, e, r.month_year, a, b)
    diff = _r2(tmp.net_pay - (l.net_pay or 0))
    why = []
    if abs((tmp.deduction or 0) - (l.deduction or 0)) > 0.005:
        why.append(f"absence {_r2(tmp.deduction) - _r2(l.deduction):+,.2f}")
    if abs(((tmp.other_allowance or 0) + (tmp.leave_salary or 0) + (tmp.air_ticket or 0) - (tmp.statutory or 0))
           - ((l.other_allowance or 0) + (l.leave_salary or 0) + (l.air_ticket or 0) - (l.statutory or 0))) > 0.005:
        why.append("additions / deductions changed")
    _set_carry(db, "office", e, pays[-1], r.month_year, diff, "; ".join(why) or "changed after it was paid")


def labour_carry(db, e, month_year, card=None):
    """A labour card paid in full (early, or after the cycle closed) that has changed since: carried to next cycle."""
    pays = _payments(db, "labour", e.id, month_year)
    if not pays or any(p.pay_type == "final" for p in pays):
        return
    st = row_state(db, "labour", e, month_year, 0, pays)
    if not st["locked"]:
        return
    card = card or _card(db, e, month_year)
    if not card:
        return
    paid = sum(p.amount or 0 for p in pays)
    now = services.adjusted_final_salary(card)
    _set_carry(db, "labour", e, pays[-1], month_year, now - paid, "attendance / additions changed after it was paid")


# ---- the figures behind a payment (copied onto it) ---------------------------------------------------------------------
_BANKS = {"026": "Emirates NBD", "033": "Mashreq", "035": "First Abu Dhabi Bank", "030": "Abu Dhabi Commercial Bank",
          "003": "First Abu Dhabi Bank", "009": "Commercial Bank of Dubai", "020": "Dubai Islamic Bank", "023": "RAKBANK",
          "024": "Commercial Bank International", "050": "Abu Dhabi Islamic Bank", "040": "Emirates Islamic",
          "046": "Ajman Bank", "047": "Al Hilal Bank", "025": "United Arab Bank", "021": "National Bank of Fujairah",
          "037": "Sharjah Islamic Bank", "060": "Wio Bank"}


def _emp(db, e):
    c = db.get(models.Company, e.company_id) if getattr(e, "company_id", None) else None
    if c is None and (e.company or "").strip():
        c = (db.query(models.Company).filter((models.Company.short_name == e.company.strip()) | (models.Company.name == e.company.strip())).first())
    iban = (e.iban or "").replace(" ", "").upper()
    return {"emp_no": e.emp_no, "name": e.name, "designation": e.designation or e.trade or "",
            "joined_on": e.joined_on.strftime("%d/%m/%Y") if e.joined_on else "",
            "company": (c.name if c else "") or e.company or "INFINIA CONTRACTING L.L.C.",
            "company_address": (c.address if c else "") or "", "iban": iban,
            "bank": _BANKS.get(iban[4:7], "") if iban.startswith("AE") and len(iban) > 7 else "",
            "pay_route": (e.pay_route or "wps")}


def office_figures(db, r, l, e):
    items = M._items_for(db, e, r.month_year)
    earn = [("Basic Salary", l.basic), ("Allowance", l.allowance)]
    cats = {}
    for i in items:
        if i.direction == "add" and i.category not in ("leave_salary", "air_ticket"):
            k = "Carried from last month" if i.category == "carry" else (i.notes or i.category or "Other additions").strip()[:40] or "Other additions"
            cats[k] = cats.get(k, 0) + (i.amount or 0)
    if cats and abs(sum(cats.values()) - (l.other_allowance or 0)) < 0.01:
        earn += list(cats.items())
    elif l.other_allowance:
        earn.append(("Other additions", l.other_allowance))
    if l.leave_salary:
        earn.append(("Leave Salary", l.leave_salary))
    if l.air_ticket:
        earn.append(("Air Ticket", l.air_ticket))
    ded = [("Loss of Pay" + (f" ({l.deduction_note})" if l.deduction_note else ""), l.deduction),
           ("Salary Advance / Loan", l.loan_deduction), ("Other Deductions", l.statutory)]
    return {"period": r.month_year, "earnings": [(k, _r2(v)) for k, v in earn if v or k in ("Basic Salary", "Allowance")],
            "deductions": [(k, _r2(v)) for k, v in ded], "net": _r2(l.net_pay), "attendance": [],
            "remarks": l.remarks or ""}


def labour_figures(db, card):
    earn = [("Salary for days worked", card.total_salary_component)]
    if card.ot_amount:
        earn.append((f"Overtime ({card.ot_hours:g} h)", card.ot_amount))
    if card.bh_amount:
        earn.append((f"Holiday overtime ({card.bh_hours:g} h)", card.bh_amount))
    if card.allowances:
        earn.append(("Allowances", card.allowances))
    ded = [("Loss of Pay (absence)", card.deduction)]
    if card.other_deduction:
        ded.append(("Other Deductions", card.other_deduction))
    for a in card.adjustments:
        (ded if a.is_deduction else earn).append(((a.description or "Adjustment")[:40], a.amount))
    att = [("Monthly rate", f"{card.total_salary or 0:,.2f}"), ("Days present", f"{card.present_days or 0:g}"),
           ("Fridays / Sundays", f"{(card.friday_days or 0) + (card.sunday_days or 0):g}"), ("Holidays", f"{card.holiday_days or 0:g}"),
           ("Sick / medical", f"{(card.sick_days or 0) + (card.medical_days or 0):g}"), ("Leave", f"{card.leave_days or 0:g}"),
           ("Absent", f"{card.absent_days or 0:g}"), ("Overtime hours", f"{card.ot_hours or 0:g}")]
    return {"period": f"{card.month_year} cycle", "earnings": [(k, _r2(v)) for k, v in earn],
            "deductions": [(k, _r2(v)) for k, v in ded], "net": services.adjusted_final_salary(card), "attendance": att, "remarks": ""}


# ---- marking paid ------------------------------------------------------------------------------------------------------
def _take_loan(db, e, amount, month_year, paid_on, pid, all_of_it=False):
    """Instalments off the open loans, oldest first. Returns what was taken."""
    left, took = _r2(amount), 0.0
    for loan in (db.query(models.StaffLoan).options(joinedload(models.StaffLoan.repayments))
                   .filter(models.StaffLoan.employee_id == e.id, models.StaffLoan.closed == False)  # noqa: E712
                   .order_by(models.StaffLoan.taken_on).all()):
        owed = (loan.amount or 0) - sum(x.amount or 0 for x in loan.repayments)
        if owed <= 0.005:
            continue
        take = owed if all_of_it else min(left, owed)
        if take <= 0.005:
            break
        db.add(models.LoanRepayment(loan_id=loan.id, amount=_r2(take), paid_on=paid_on, month_year=month_year,
                                    source="payment", notes=f"payment #{pid}"))
        if take >= owed - 0.005:
            loan.closed = True
        took += take
        left -= take
        if not all_of_it and left <= 0.005:
            break
    return _r2(took)


def _resolve(db, kind, source_id):
    """(employee, month_year, run, line, card) for the row being paid."""
    if kind == "office":
        l = _office_line(db, source_id)
        r = db.get(models.PayrollRun, l.run_id)
        return db.get(models.Employee, l.employee_id), r.month_year, r, l, None
    card = db.get(models.EmployeeSummary, source_id)
    if not card:
        raise HTTPException(status_code=404, detail="That salary card is no longer on file - refresh the page.")
    e = db.get(models.Employee, card.employee_id) or db.query(models.Employee).filter(models.Employee.emp_no == card.emp_no).first()
    return e, card.month_year, None, None, card


def _settle_q(body):
    return {k: body.get(k) for k in ("last_day", "reason", "leave_days", "notice_required", "notice_served", "ticket",
                                    "other_add", "other_ded", "other_add_note", "other_ded_note") if body.get(k) not in (None, "")}


def work_out(db, kind, source_id, body, commit_side_effects=False):
    """What a payment of this type comes to, without paying it (the dialog's preview) - or, with
    commit_side_effects, the changes a payment makes first (an early cycle for one worker, the leaving date)."""
    import settlement as SET
    e, month, r, l, card = _resolve(db, kind, source_id)
    t = body.get("type") or "regular"
    if t not in TYPES:
        raise HTTPException(status_code=400, detail="Which kind of payment?")
    pays = _payments(db, kind, e.id, month)
    paid = _r2(sum(p.amount or 0 for p in pays))
    if pays and any(p.pay_type == "final" for p in pays):
        raise HTTPException(status_code=400, detail=f"{e.name} has had his final settlement for {month}.")
    if kind == "office" and r.status == "approved" and t in ("early_full",):
        t = "regular"
    out = {"type": t, "employee": e.name, "emp_no": e.emp_no, "month_year": month, "paid_before": paid}
    if t == "final":
        q = _settle_q(body)
        q.setdefault("last_day", (e.terminated_on or M._dubai_today()).isoformat())
        if kind == "labour":
            last = M._as_date(q["last_day"])
            # The settlement pays the wages of the card for the cycle his last day falls in, and the payment is
            # booked against the card it was taken from - they must be the same card. Taken from another cycle's
            # card, that card was marked settled with its own wages never paid (October's 1,472 dropped, say), and
            # the last cycle's card still showed its wages due although the settlement had paid them.
            last_cycle = M.pcyc.cycle_bounds_for(last)[2] if last else month
            if last_cycle != month:
                raise HTTPException(status_code=400, detail=(
                    f"The last working day {last:%d/%m/%Y} is in the {last_cycle} cycle - the final settlement pays "
                    f"that cycle's wages, so mark it on his {last_cycle} card. Pay this {month} card as a regular "
                    f"payment (or change the last working day)."))
            if commit_side_effects:
                e.terminated_on = last
                db.flush()
                services.recalculate_summary(db, e, M.pcyc.cycle_bounds_for(last)[2])
        s = SET.settlement(db, e.emp_no, q)
        net = _r2(s["net"])
        out.update({"amount": _r2(max(net - paid, 0)), "due": net, "settlement": s,
                    "lines": [(x["label"], x["amount"]) for x in s["payables"]] + [(f"less {x['label']}", -x["amount"]) for x in s["deductions"] if x["amount"]]})
        return out
    if kind == "office":
        due, td = _r2(l.net_pay), office_to_date(db, r, l)
        if t == "regular":
            # The running figure leaves the loan instalment out (it comes off at the month end), so it can pass
            # the month's net pay for someone repaying a loan - never more than the month's net is paid.
            amt = max(min(td, due) - paid, 0)
            if pays:
                t = "balance"
        elif t in ("balance", "early_full"):
            amt = max(due - paid, 0)
        else:
            amt = _r2(body.get("amount"))
        out.update({"type": t, "due": due, "amount": _r2(amt), "to_date": td})
        return out
    # labour
    if t == "early_full" and commit_side_effects:
        M.put_setting(db, f"{services.full_cycle_key(month)}:{e.emp_no}", M._dubai_today().isoformat())
        db.flush()
        card = services.recalculate_summary(db, e, month)
    now = services.adjusted_final_salary(card)
    if t == "early_full" and not commit_side_effects:
        now = _full_cycle_preview(db, e, month, card)
    if t == "custom":
        amt = _r2(body.get("amount"))
    else:
        amt = _r2(max(now - paid, 0))
        if t == "regular" and pays:
            t = "balance"
    out.update({"type": t, "due": _r2(now), "amount": amt})
    return out


def _full_cycle_preview(db, e, month, card):
    """What his card comes to once the days still to come count as worked - the same working the card itself
    uses (services.with_days_paid_in_advance), without saving anything."""
    import data_engine as de
    from types import SimpleNamespace
    rows = db.query(models.DailyRow).filter(models.DailyRow.emp_no == e.emp_no, models.DailyRow.month_year == month).all()
    cs, ce, _ = M.pcyc.cycle_bounds_for(datetime.strptime(f"25 {month}", "%d %B %Y").date())
    if e.terminated_on:
        t = e.terminated_on
        rows = [SimpleNamespace(full_date=r.full_date, am="Terminated", pm="Terminated", ot=0, bh=0, site="", engineer="",
                                comments="", emp_no=r.emp_no) if r.full_date > t else r for r in rows]
    marked = {r.full_date for r in rows if (r.am or "").strip() or (r.pm or "").strip()}
    start = max(M._dubai_today(), cs)
    rows = [r for r in rows if r.full_date in marked or r.full_date < start]
    d = start if not (e.joined_on and e.joined_on > start) else e.joined_on
    end = min(ce, e.terminated_on) if e.terminated_on else ce
    while d <= end:
        if d not in marked:
            st = "Sunday" if d.weekday() == 6 else "Present"
            rows.append(SimpleNamespace(full_date=d, am=st, pm=st, ot=0, bh=0, site="", engineer="", comments="", emp_no=e.emp_no))
        d += timedelta(days=1)
    comp = de.recalculate_from_daily_rows(rows, card.total_salary or e.total_salary, e.basic_salary,
                                          card.allowances or 0.0, card.other_deduction or 0.0,
                                          pay_type=(e.pay_type or "daily"), cycle_days=(ce - cs).days + 1)
    return _r2(comp["final_salary"] + sum((-a.amount if a.is_deduction else a.amount) for a in card.adjustments))


def mark_paid(db, user, kind, source_id, body):
    e, month, r, l, card = _resolve(db, kind, source_id)
    paid_on = M._as_date(body.get("paid_on")) or M._dubai_today()
    mode = body.get("mode") if body.get("mode") in MODES else (e.pay_route if e.pay_route in MODES else "wps")
    w = work_out(db, kind, source_id, body, commit_side_effects=True)
    t, amt = w["type"], _r2(w["amount"])
    if t == "custom" and amt <= 0:
        raise HTTPException(status_code=400, detail="Type the amount paid.")
    if amt <= 0 and t != "final":
        raise HTTPException(status_code=400, detail=f"Nothing is owed to {e.name} for {month} just now.")
    if kind == "labour":
        card = _card(db, e, month)
        figs = labour_figures(db, card)
        src = card.id
    else:
        figs = office_figures(db, r, l, e)
        src = l.id
    if t == "final":
        figs = {"period": month, "settlement": w["settlement"], "net": w["due"]}
    p = models.PayPayment(kind=kind, employee_id=e.id, month_year=month, source_id=src, run_id=r.id if r else None,
                          pay_type=t, amount=amt, due=w["due"], paid_on=paid_on, mode=mode,
                          reference=(body.get("reference") or "").strip()[:80], note=(body.get("note") or "").strip()[:500],
                          created_by=user.id)
    db.add(p); db.flush()
    figs["employee"] = _emp(db, e)
    # Loans: the month's instalment once the row is paid in full; the whole balance in a final settlement.
    pays = _payments(db, kind, e.id, month)
    total = _r2(sum(x.amount or 0 for x in pays))
    if t == "final":
        s = w["settlement"]
        figs["was"] = {"active": bool(e.active), "terminated_on": e.terminated_on.isoformat() if e.terminated_on else ""}
        p.loan_repaid = _take_loan(db, e, s["input"]["loan"], month, paid_on, p.id, all_of_it=True) if s["input"]["loan"] else 0.0
        e.terminated_on = M._as_date(s["input"]["last_day"])
        e.active = False
    elif kind == "office" and total >= _r2(w["due"]) - 0.01 and (l.loan_deduction or 0) > 0.005 and r.status != "approved":
        p.loan_repaid = _take_loan(db, e, l.loan_deduction, month, paid_on, p.id)
    p.figures = json.dumps(figs, default=str)
    db.commit()
    M.log_action(db, user.id, "salary_paid", f"{kind} {e.emp_no} {e.name} {month}: {TYPES[t]} {amt:,.2f} by {MODES[mode]}"
                 + (f" ref {p.reference}" if p.reference else "") + (f"; loan {p.loan_repaid:,.2f}" if p.loan_repaid else ""))
    return p


def void_payment(db, user, p, reason):
    """Undo a payment entered by mistake: its loan recoveries, its carry and (final) the leaving are put back.
    Its payslips stay on file, marked as belonging to a cancelled payment."""
    if p.void:
        return
    for rep in db.query(models.LoanRepayment).filter(models.LoanRepayment.notes == f"payment #{p.id}").all():
        loan = db.get(models.StaffLoan, rep.loan_id)
        if loan:
            loan.closed = False
        db.delete(rep)
    for c in db.query(models.PayCarry).filter(models.PayCarry.payment_id == p.id).all():
        _drop_target(db, c)
        db.delete(c)
    e = db.get(models.Employee, p.employee_id)
    if p.pay_type == "final":
        was = (json.loads(p.figures or "{}") or {}).get("was") or {}
        e.active = bool(was.get("active", True))
        e.terminated_on = M._as_date(was.get("terminated_on")) if was.get("terminated_on") else None
    if p.pay_type == "early_full" and p.kind == "labour":
        M.put_setting(db, f"{services.full_cycle_key(p.month_year)}:{e.emp_no}", "")
    p.void, p.void_reason = True, (reason or "")[:200]
    db.commit()
    if p.kind == "labour":
        services.recalculate_summary(db, e, p.month_year)
    M.log_action(db, user.id, "salary_payment_cancelled", f"{p.kind} {e.emp_no} {p.month_year}: {TYPES.get(p.pay_type)} {p.amount:,.2f} - {reason}")


# ---- payslips ----------------------------------------------------------------------------------------------------------
def make_payslip(db, user, p):
    if p.void:
        raise HTTPException(status_code=400, detail="That payment was cancelled.")
    figs = json.loads(p.figures or "{}")
    e = db.get(models.Employee, p.employee_id)
    v = (db.query(models.Payslip).filter(models.Payslip.payment_id == p.id).count()) + 1
    pays = [x for x in _payments(db, p.kind, p.employee_id, p.month_year) if x.id <= p.id]
    data = dict(figs)
    data.update({"kind": p.kind, "month_year": p.month_year, "employee": figs.get("employee") or _emp(db, e),
                 "payment": _pay_dict(p), "paid_total": _r2(sum(x.amount or 0 for x in pays)), "due": _r2(p.due),
                 "issued": M._dubai_today().strftime("%d/%m/%Y")})
    data["balance"] = _r2(max(data["due"] - data["paid_total"], 0))
    mon = datetime.strptime(f"1 {p.month_year}", "%d %B %Y").strftime("%Y-%m")
    s = models.Payslip(kind=p.kind, employee_id=p.employee_id, payment_id=p.id, month_year=p.month_year, version=v,
                       slip_no=f"PS-{e.emp_no.replace('/', '').replace(' ', '')}-{mon}-{p.id}-v{v}",
                       slip_type="settlement" if p.pay_type == "final" else "payslip", data=json.dumps(data, default=str),
                       created_by=user.id)
    db.add(s); db.commit(); db.refresh(s)
    return s


def payslip_pdf(s):
    data = json.loads(s.data or "{}")
    if s.slip_type == "settlement" and data.get("settlement"):
        import settlement as SET
        return SET._pdf(data["settlement"]).getvalue()
    return _payslip_pdf(data, s.slip_no)


def _payslip_pdf(d, slip_no):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT, TA_LEFT
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, KeepTogether
    import export_web
    from invoice_pdf import amount_in_words
    RED, DARK, GREY, SOFT, LINE = (colors.HexColor("#C0392B"), colors.HexColor("#2E3238"), colors.HexColor("#6B7280"),
                                   colors.HexColor("#F3F4F6"), colors.HexColor("#E5E7EB"))
    def P(t, size=8.6, bold=False, color=DARK, align=TA_LEFT, italic=False):
        f = "Helvetica-BoldOblique" if bold and italic else "Helvetica-Oblique" if italic else "Helvetica-Bold" if bold else "Helvetica"
        return Paragraph(escape(str(t if t is not None else "")), ParagraphStyle("p", fontName=f, fontSize=size, leading=size * 1.32,
                                                                                textColor=color, alignment=align))
    m = lambda v: f"{float(v or 0):,.2f}"
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=12 * mm, bottomMargin=16 * mm,
                            title=f"Payslip {d.get('employee', {}).get('name', '')} {d.get('month_year', '')}")
    W = doc.width
    emp, pay = d.get("employee", {}), d.get("payment", {})
    el = []
    rule = Table([[""]], colWidths=[W], rowHeights=[1.2])
    rule.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, -1), 1.4, RED)]))
    logo = export_web._logo_image(width_mm=56)
    co = (emp.get("company") or "INFINIA CONTRACTING L.L.C.")
    left = [logo, Spacer(1, 5)] if logo and "INFINIA" in co.upper() else [P(co, 12, True)]
    if co.strip().upper() in ("INFINIA", "INFINIA CONTRACTING"):
        co = "INFINIA CONTRACTING L.L.C."
    left += [P(emp.get("company_address") or "M09, Bin Bishr Building, Abu Hail, Dubai, UAE", 7.5, color=GREY), P("www.infinia.ae", 7.5, color=GREY)]
    title = "SETTLEMENT" if d.get("settlement") else "PAYSLIP"
    head = Table([[left, [P(title, 20, True, align=TA_RIGHT), P(d.get("month_year", "").upper(), 10, True, RED, TA_RIGHT),
                          P(slip_no, 7, color=GREY, align=TA_RIGHT)]]], colWidths=[W * 0.6, W * 0.4])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    el += [rule, Spacer(1, 6), head, Spacer(1, 10)]

    def section(t):
        el.append(P(t, 8.2, True, RED)); el.append(Spacer(1, 4))

    def kv(rows):
        data = [[P(a, 8.2, True, GREY), P(b, 8.6), P(c, 8.2, True, GREY), P(e_, 8.6)] for a, b, c, e_ in rows]
        t = Table(data, colWidths=[W * 0.18, W * 0.32, W * 0.18, W * 0.32])
        t.setStyle(TableStyle([("ROWBACKGROUNDS", (0, 0), (-1, -1), [SOFT, colors.white]), ("TOPPADDING", (0, 0), (-1, -1), 3.4),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 3.4), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        el.append(t); el.append(Spacer(1, 9))
    section("EMPLOYEE INFORMATION")
    kv([("Employee Name", emp.get("name", "").upper(), "Employee Code", emp.get("emp_no", "")),
        ("Designation", emp.get("designation", ""), "Date of Joining", emp.get("joined_on", "")),
        ("Salary Month", d.get("period") or d.get("month_year", ""), "Issue Date", d.get("issued", "")),
        ("Currency", "AED", "Payment Mode", pay.get("mode_label", ""))])
    section("BANK DETAILS")
    kv([("Bank Name", emp.get("bank") or "-", "Payment Mode", pay.get("mode_label", "")),
        ("IBAN", emp.get("iban") or "-", "Paid through", (emp.get("pay_route") or "wps").upper())])
    if d.get("attendance"):
        section("ATTENDANCE")
        a = d["attendance"]
        rows = [(a[i][0], a[i][1], a[i + 1][0] if i + 1 < len(a) else "", a[i + 1][1] if i + 1 < len(a) else "") for i in range(0, len(a), 2)]
        kv(rows)
    section("SALARY BREAKDOWN")
    E, D = d.get("earnings", []), d.get("deductions", [])
    n = max(len(E), len(D))
    rows = [[P("EARNINGS", 8.2, True, colors.white), P("AMOUNT (AED)", 8.2, True, colors.white, TA_RIGHT),
             P("DEDUCTIONS", 8.2, True, colors.white), P("AMOUNT (AED)", 8.2, True, colors.white, TA_RIGHT)]]
    for i in range(n):
        a = E[i] if i < len(E) else ("", None)
        b = D[i] if i < len(D) else ("", None)
        rows.append([P(a[0]), P(m(a[1]) if a[1] is not None else "", align=TA_RIGHT), P(b[0]), P(m(b[1]) if b[1] is not None else "", align=TA_RIGHT)])
    ge, td = sum(v for _, v in E), sum(v for _, v in D)
    rows.append([P("GROSS EARNINGS", 8.4, True), P(m(ge), 8.4, True, align=TA_RIGHT), P("TOTAL DEDUCTIONS", 8.4, True), P(m(td), 8.4, True, align=TA_RIGHT)])
    t = Table(rows, colWidths=[W * 0.32, W * 0.18, W * 0.32, W * 0.18])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), DARK), ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, SOFT]),
                           ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E5E7EB")), ("TOPPADDING", (0, 0), (-1, -1), 3.6),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 3.6), ("LINEAFTER", (1, 0), (1, -1), 0.6, colors.white)]))
    el += [t, Spacer(1, 9)]
    net = d.get("net", 0)
    nt = Table([[P("NET SALARY PAYABLE", 10, True), P(f"AED {m(net)}", 15, True, RED, TA_RIGHT)]], colWidths=[W * 0.55, W * 0.45])
    nt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SOFT), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    el += [nt, Spacer(1, 3), P(amount_in_words(net), 8, color=GREY, align=TA_RIGHT, italic=True), Spacer(1, 9)]
    section("PAYMENT DETAILS")
    prow = [("Payment Type", pay.get("type_label", ""), "Paid On", pay.get("paid_on_text", "")),
            ("Amount Paid", f"AED {m(pay.get('amount'))}", "Mode", pay.get("mode_label", "")),
            ("Reference No.", pay.get("reference") or "-", "Total Paid for the Month", f"AED {m(d.get('paid_total'))}")]
    if d.get("balance"):
        prow.append(("Balance Due", f"AED {m(d.get('balance'))}", "", ""))
    if pay.get("loan_repaid"):
        prow.append(("Loan Recovered", f"AED {m(pay.get('loan_repaid'))}", "", ""))
    if pay.get("note"):
        prow.append(("Note", pay.get("note"), "", ""))
    kv(prow)
    # a blank box for the company stamp and a line for the signatory
    sig = Table([[P("COMPANY STAMP", 7.6, True, GREY), "", P("FOR " + co.upper(), 7.6, True, GREY)],
                 ["", "", ""], ["", "", P("Authorized Signatory", 8, align=TA_RIGHT)]],
                colWidths=[W * 0.34, W * 0.24, W * 0.42], rowHeights=[14, 44, 14])
    sig.setStyle(TableStyle([("BOX", (0, 1), (0, 1), 0.8, colors.HexColor("#B8BCC4")), ("LINEBELOW", (2, 1), (2, 1), 0.8, GREY),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
    el.append(KeepTogether([sig]))

    def foot(c, _d):
        c.saveState(); c.setFont("Helvetica", 6.8); c.setFillColor(GREY)
        c.drawCentredString(A4[0] / 2, 9 * mm, f"{co.upper()}  |  CONFIDENTIAL PAYROLL DOCUMENT  |  INTERNAL  |  {slip_no}")
        c.restoreState()
    doc.build(el, onFirstPage=foot, onLaterPages=foot)
    return buf.getvalue()


# ---- API ---------------------------------------------------------------------------------------------------------------
def _user(db, token):
    return auth.get_download_user_from_token(token, db)


@router.post("/employees/pay/preview")
def preview(body: dict = Body(...), db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    kind = body.get("kind"); _can(user, kind)
    w = work_out(db, kind, int(body.get("source_id") or 0), body)
    db.rollback()
    w.pop("settlement", None) if body.get("brief") else None
    return w


@router.post("/employees/pay/mark")
def mark(body: dict = Body(...), db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    kind = body.get("kind"); _can(user, kind)
    p = mark_paid(db, user, kind, int(body.get("source_id") or 0), body)
    s = make_payslip(db, user, p) if body.get("payslip") else None
    return {"ok": True, "payment": _pay_dict(p), "payslip_id": s.id if s else None}


@router.post("/employees/pay/bulk")
def bulk(body: dict = Body(...), db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    """Mark selected as paid (regular / early full month), and / or generate their payslips."""
    kind = body.get("kind"); _can(user, kind)
    done, skipped, slips = [], [], []
    for sid in body.get("source_ids") or []:
        try:
            if body.get("action") == "payslips":
                e, month, *_ = _resolve(db, kind, int(sid))
                for p in _payments(db, kind, e.id, month):
                    if not db.query(models.Payslip).filter(models.Payslip.payment_id == p.id).first():
                        slips.append(make_payslip(db, user, p).id)
                continue
            p = mark_paid(db, user, kind, int(sid), {"type": body.get("type") or "regular", "paid_on": body.get("paid_on"),
                                                     "mode": body.get("mode"), "reference": body.get("reference"), "note": body.get("note")})
            done.append(p.id)
        except HTTPException as ex:
            db.rollback()
            skipped.append({"source_id": sid, "why": ex.detail})
    return {"ok": True, "paid": len(done), "payslips": len(slips), "skipped": skipped}


@router.post("/employees/pay/{pid}/payslip")
def generate(pid: int, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    p = db.get(models.PayPayment, pid)
    if not p:
        raise HTTPException(status_code=404, detail="Payment not found.")
    _can(user, p.kind)
    s = make_payslip(db, user, p)
    return {"ok": True, "id": s.id, "version": s.version, "slip_no": s.slip_no}


@router.post("/employees/pay/{pid}/cancel")
def cancel(pid: int, body: dict = Body(default={}), db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    p = db.get(models.PayPayment, pid)
    if not p:
        raise HTTPException(status_code=404, detail="Payment not found.")
    _can(user, p.kind)
    why = " ".join(str(body.get("reason") or "").split())
    if not why:
        raise HTTPException(status_code=400, detail="Say why the payment is cancelled.")
    void_payment(db, user, p, why)
    return {"ok": True}


@router.get("/employees/pay/labour")
def labour_rows(month_year: str, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    """Labour payroll > Salary cards: every card of the cycle with its paid status and payslips, by company."""
    _can(user, "labour")
    cards = (db.query(models.EmployeeSummary).options(joinedload(models.EmployeeSummary.adjustments))
               .filter(models.EmployeeSummary.month_year == month_year).order_by(models.EmployeeSummary.emp_no).all())
    emps = {e.id: e for e in db.query(models.Employee).filter(models.Employee.staff != True).all()}  # noqa: E712
    pays = (db.query(models.PayPayment).filter(models.PayPayment.kind == "labour", models.PayPayment.month_year == month_year,
                                               models.PayPayment.void == False).order_by(models.PayPayment.id).all())  # noqa: E712
    by = {}
    for p in pays:
        by.setdefault(p.employee_id, []).append(p)
    slips = _slips(db, [p.id for p in pays])
    groups = {}
    for c in cards:
        e = emps.get(c.employee_id)
        if not e:
            continue
        if by.get(e.id):
            labour_carry(db, e, month_year, c)
        net = services.adjusted_final_salary(c)
        st = row_state(db, "labour", e, month_year, net, by.get(e.id, []))
        st["slips"] = {str(p["id"]): slips.get(p["id"], []) for p in st["payments"]}
        adj = _r2(sum((-a.amount if a.is_deduction else a.amount) for a in c.adjustments))
        groups.setdefault(e.company or "Infinia", []).append({
            "source_id": c.id, "emp_no": e.emp_no, "name": e.name, "trade": e.trade or "", "active": bool(e.active),
            # the paid days the card's salary is for - sick and medical days are paid too (data_engine)
            "days": _r2((c.present_days or 0) + (c.friday_days or 0) + (c.sunday_days or 0) + (c.holiday_days or 0)
                        + (c.sick_days or 0) + (c.medical_days or 0)),
            "ot": _r2(c.ot_hours), "salary": _r2(c.final_salary), "adjust": adj, "net": net, "pay_route": e.pay_route or "wps",
            "pay": st})
    db.commit()
    full = services.full_cycle_from(db, month_year)
    return {"month_year": month_year, "closed": _cycle_closed(month_year), "full_cycle": bool(full),
            "groups": [{"company": k, "rows": v, "net": _r2(sum(x["net"] for x in v)),
                        "paid": _r2(sum(x["pay"]["paid"] for x in v))} for k, v in sorted(groups.items())]}


@router.get("/employees/pay/payslips")
def employee_payslips(emp_no: str, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    """A person's payslips, every version - the Payslips tab on his Staff profile."""
    e = db.query(models.Employee).filter(models.Employee.emp_no == emp_no).first()
    if not e:
        raise HTTPException(status_code=404, detail="Not on file.")
    _can(user, "labour" if not e.staff else "office")
    rows = []
    for s in (db.query(models.Payslip).filter(models.Payslip.employee_id == e.id).order_by(models.Payslip.id.desc()).all()):
        p = db.get(models.PayPayment, s.payment_id)
        rows.append({"id": s.id, "slip_no": s.slip_no, "version": s.version, "type": s.slip_type, "month_year": s.month_year,
                     "created": s.created_at.strftime("%d/%m/%Y %H:%M") if s.created_at else "",
                     "payment": _pay_dict(p) if p else {}, "cancelled": bool(p and p.void)})
    pays = [_pay_dict(p) | {"month_year": p.month_year, "cancelled": bool(p.void)}
            for p in db.query(models.PayPayment).filter(models.PayPayment.employee_id == e.id).order_by(models.PayPayment.id.desc()).all()]
    return {"emp_no": e.emp_no, "name": e.name, "payslips": rows, "payments": pays}


@router.get("/export/pay/payslip/{sid}")
def payslip_file(sid: int, token: str, inline: bool = True, db: Session = Depends(get_db)):
    user = _user(db, token)
    s = db.get(models.Payslip, sid)
    if not s:
        raise HTTPException(status_code=404, detail="Payslip not found.")
    _can(user, s.kind)
    e = db.get(models.Employee, s.employee_id)
    name = f"{s.slip_no}_{(e.name if e else '').replace(' ', '_')}.pdf"
    return StreamingResponse(io.BytesIO(payslip_pdf(s)), media_type="application/pdf",
                             headers={"Content-Disposition": f"{'inline' if inline else 'attachment'}; filename={name}"})


@router.get("/export/pay/payslips.zip")
def payslips_zip(token: str, kind: str, month_year: str, run_ids: str = "", company: str = "", db: Session = Depends(get_db)):
    """The latest version of every payslip for the month (office: the runs on screen; labour: the cycle)."""
    user = _user(db, token)
    _can(user, kind)
    q = db.query(models.PayPayment).filter(models.PayPayment.kind == kind, models.PayPayment.month_year == month_year,
                                           models.PayPayment.void == False)  # noqa: E712
    ids = [int(x) for x in run_ids.split(",") if x.strip().isdigit()]
    if ids:
        q = q.filter(models.PayPayment.run_id.in_(ids))
    buf = io.BytesIO()
    n = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in q.all():
            e = db.get(models.Employee, p.employee_id)
            if company and e and (e.company or "Infinia") != company:
                continue
            s = (db.query(models.Payslip).filter(models.Payslip.payment_id == p.id).order_by(models.Payslip.version.desc()).first())
            if not s:
                continue
            z.writestr(f"{s.slip_no}_{(e.name if e else '').replace(' ', '_')}.pdf", payslip_pdf(s)); n += 1
    if not n:
        raise HTTPException(status_code=400, detail="No payslips generated for that month yet - press Generate first.")
    buf.seek(0)
    tag = month_year.replace(" ", "_")
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f"attachment; filename=Payslips_{kind}_{tag}.zip"})

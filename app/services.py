"""
Service layer - bridges the database with data_engine.recalculate_from_daily_rows(),
the SAME function the desktop app uses. This is deliberately the ONLY
place that calls it, so there is exactly one path from "daily rows in
the database" to "payroll figures", matching the desktop app's own
design principle that there must only ever be one place these formulas
are written.
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_

import models
import data_engine as de
import payroll_cycle as pcyc


def validate_row(am, pm, site, engineer, bh, comments, ot=None):
    """
    Identical rules to daily_attendance.validate_row() in the desktop
    app - copied directly here rather than importing that module,
    since it also imports master_data.py (file-based JSON storage),
    which the web app deliberately does not use at all. This is the
    ONLY function actually needed from that module.

    Adds a sanity check the desktop version didn't have: OT/BH must
    not be negative and must fit inside a real day. Negative hours
    would silently SUBTRACT from a worker's pay (ot_amount is
    hours * hourly_rate, so -5 hours = -AED 66.67 off their salary)
    with nothing on screen explaining why the total looked wrong.
    """
    problems = []
    am = (am or "").strip()
    pm = (pm or "").strip()
    if not am or not pm:
        problems.append("A.M and P.M status must both be set.")
    is_present = am.lower() == "present" or pm.lower() == "present"
    if is_present and (not str(site).strip() or not str(engineer).strip()):
        problems.append("Present requires both Site and Engineer.")
    try:
        bh_val = float(bh) if bh not in (None, "") else 0.0
    except (TypeError, ValueError):
        bh_val = 0.0
    if bh_val > 2 and not (comments or "").strip():
        problems.append("BH over 2 hours requires a comment.")

    for label, raw in (("OT", ot), ("BH", bh)):
        if raw in (None, ""):
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            problems.append(f"{label} must be a number.")
            continue
        if val < 0:
            problems.append(f"{label} cannot be negative.")
        elif val > 24:
            problems.append(f"{label} cannot be more than 24 hours in a day.")
    return problems


def recalculate_summary(db: Session, employee: models.Employee, month_year: str) -> models.EmployeeSummary:
    """
    Recomputes one employee's EmployeeSummary row for one cycle from
    ALL their current daily_rows for that cycle - must be called after
    any daily_row insert/update/delete touching this (employee,
    month_year), so the summary always reflects the complete picture,
    never a stale partial one.
    """
    rows = (
        db.query(models.DailyRow)
        .filter(and_(models.DailyRow.emp_no == employee.emp_no,
                      models.DailyRow.month_year == month_year))
        .all()
    )

    summary = (
        db.query(models.EmployeeSummary)
        .filter(and_(models.EmployeeSummary.emp_no == employee.emp_no,
                      models.EmployeeSummary.month_year == month_year))
        .first()
    )
    if summary is None:
        summary = models.EmployeeSummary(
            employee_id=employee.id, emp_no=employee.emp_no,
            emp_name=employee.name, trade=employee.trade, month_year=month_year,
        )
        db.add(summary)
        db.flush()

    # THE actual calculation - identical function, identical formula,
    # as the desktop app. rows are SQLAlchemy DailyRow objects, which
    # already expose .am/.pm/.ot/.bh directly, so no translation layer
    # is needed between the database and this calculation.
    computed = de.recalculate_from_daily_rows(
        rows, employee.total_salary, employee.basic_salary,
        summary.allowances or 0.0, summary.other_deduction or 0.0,
    )

    summary.total_salary = employee.total_salary
    summary.present_days = computed["present_days"]
    summary.absent_days = computed["absent_days"]
    summary.sick_days = computed["sick_days"]
    summary.medical_days = computed["medical_days"]
    summary.friday_days = computed["friday_days"]
    summary.holiday_days = computed["holiday_days"]
    summary.leave_days = computed["leave_days"]
    summary.ot_hours = computed["ot_hours"]
    summary.bh_hours = computed["bh_hours"]
    summary.basic_pay_input = computed["basic_pay_input"]
    summary.total_salary_component = computed["total_salary_component"]
    summary.deduction = computed["deduction"]
    summary.ot_amount = computed["ot_amount"]
    summary.bh_amount = computed["bh_amount"]
    summary.final_salary = computed["final_salary"]

    db.commit()
    db.refresh(summary)
    return summary


def adjusted_final_salary(summary: models.EmployeeSummary) -> float:
    """Same convention as the desktop app: Final Salary plus/minus every
    itemized adjustment, additions positive, deductions negative."""
    total = summary.final_salary
    for adj in summary.adjustments:
        total += (-adj.amount if adj.is_deduction else adj.amount)
    return round(total, 2)


def upsert_daily_row(db: Session, employee: models.Employee, row_in) -> models.DailyRow:
    """
    Insert or update ONE worker's ONE day - same semantics as
    daily_attendance.upsert_daily_row() in the desktop app: a second
    save for the same (emp_no, date) overwrites the first rather than
    creating a duplicate, enforced here by the DB's own unique
    constraint plus an explicit look-up-then-update.
    """
    cycle_start, cycle_end, month_year = pcyc.cycle_bounds_for(row_in.full_date)

    existing = (
        db.query(models.DailyRow)
        .filter(and_(models.DailyRow.emp_no == employee.emp_no,
                      models.DailyRow.full_date == row_in.full_date))
        .first()
    )
    if existing is None:
        existing = models.DailyRow(employee_id=employee.id, emp_no=employee.emp_no)
        db.add(existing)

    existing.emp_name = employee.name
    existing.trade = employee.trade
    existing.month_year = month_year
    existing.full_date = row_in.full_date
    existing.day = row_in.full_date.day
    existing.am = row_in.am
    existing.pm = row_in.pm
    existing.ot = row_in.ot
    existing.bh = row_in.bh
    existing.site = row_in.site
    existing.engineer = row_in.engineer
    existing.comments = row_in.comments

    db.commit()
    db.refresh(existing)
    return existing


def delete_daily_row_if_blank(db: Session, emp_no: str, full_date) -> bool:
    """Same as the desktop app's delete_daily_row(): clearing a row back
    to blank and saving actually removes the previously-saved entry,
    rather than silently leaving stale data behind."""
    existing = (
        db.query(models.DailyRow)
        .filter(and_(models.DailyRow.emp_no == emp_no, models.DailyRow.full_date == full_date))
        .first()
    )
    if existing is None:
        return False
    db.delete(existing)
    db.commit()
    return True


def get_previous_day_site_engineer(db: Session, emp_no: str, target_date):
    """Same Holiday-specific rule as the desktop app: pulls Site/Engineer
    from that SAME worker's saved entry the day before, returns None if
    there isn't one (or it has no real site), so the caller can block
    the save and ask staff to fill that day in first."""
    from datetime import timedelta
    prev_date = target_date - timedelta(days=1)
    prev_row = (
        db.query(models.DailyRow)
        .filter(and_(models.DailyRow.emp_no == emp_no, models.DailyRow.full_date == prev_date))
        .first()
    )
    if prev_row is not None and (prev_row.site or "").strip():
        return prev_row.site, prev_row.engineer or ""
    return None


def auto_fill_sunday_from_saturday(db: Session, employee: models.Employee, saturday_row: models.DailyRow):
    """
    When a Saturday is saved with a real Site, the following Sunday gets
    that same Site/Engineer pre-filled automatically - A.M/P.M are left
    blank so staff still has to mark it (usually Holiday) themselves;
    the day only turns green on the calendar once they do.

    Only ever fires when Sunday has NO row at all yet - the moment a
    Sunday row exists in any form (even the auto-fill's own first pass,
    or staff manually setting just the Site with A.M/P.M still blank),
    it's left alone for good. Some sites genuinely work on a Sunday
    that's otherwise a rest day, so staff needs to be able to correct
    the Site by hand and have that stick - a later Saturday edit must
    never silently overwrite that choice back.
    """
    from datetime import timedelta
    if saturday_row.full_date.weekday() != 5:  # 5 = Saturday
        return
    site = (saturday_row.site or "").strip()
    if not site:
        return
    sunday_date = saturday_row.full_date + timedelta(days=1)
    # Never pre-fill a Sunday that hasn't arrived yet - saving a future
    # Saturday would otherwise silently create a row for a day even
    # further ahead, which then shows on the worker's card as if it
    # already happened.
    from datetime import date as _date
    if sunday_date > _date.today():
        return

    existing = (
        db.query(models.DailyRow)
        .filter(and_(models.DailyRow.emp_no == employee.emp_no, models.DailyRow.full_date == sunday_date))
        .first()
    )
    if existing is not None:
        return  # Sunday already has a row of its own - never touch it again

    cycle_start, cycle_end, month_year = pcyc.cycle_bounds_for(sunday_date)
    existing = models.DailyRow(employee_id=employee.id, emp_no=employee.emp_no)
    db.add(existing)

    existing.emp_name = employee.name
    existing.trade = employee.trade
    existing.month_year = month_year
    existing.full_date = sunday_date
    existing.day = sunday_date.day
    existing.am = ""
    existing.pm = ""
    existing.ot = 0
    existing.bh = 0
    existing.site = saturday_row.site
    existing.engineer = saturday_row.engineer
    existing.comments = existing.comments or ""
    db.commit()

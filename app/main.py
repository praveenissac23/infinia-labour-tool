"""
Infinia Labour Tool - Web Backend
====================================
FastAPI application. Reuses the desktop app's own calculation and
validation logic (data_engine.py, daily_attendance.py, payroll_cycle.py)
directly - the only thing that changed is the storage layer, from
pickled sessions/JSON files to a real multi-user database.
"""
from datetime import date, datetime
from typing import Optional
import io
import json

from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from database import get_db, engine, Base
import models
import schemas
import services
import auth
import payroll_cycle as pcyc
import reports as rp
import export_web

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Infinia Labour Tool API")


@app.on_event("startup")
def seed_on_startup():
    """
    Runs the same seeding logic as seed_data.py automatically on every
    startup - idempotent (upserts, never duplicates), so this is safe
    to run every single time the app boots. Needed specifically because
    Render's free tier has no shell access to run a one-off script
    manually; master_data.json (if bundled alongside this file) gets
    picked up automatically the first time the app starts.
    """
    import os
    import seed_data
    json_path = os.path.join(os.path.dirname(__file__), "master_data.json")
    seed_data.run(json_path if os.path.exists(json_path) else None)

# Locked down to specific origins in production - wide open here only
# for local dev/testing against a frontend running on a different port.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------
# AUTH
# ---------------------------------------------------------------------
def log_action(db: Session, user_id, action: str, details: str = ""):
    db.add(models.AuditLog(user_id=user_id, action=action, details=details))
    db.commit()


@app.post("/auth/login", response_model=schemas.TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not user.active or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
    token = auth.create_access_token({"sub": user.username})
    log_action(db, user.id, "login")
    maybe_create_auto_backup(db)
    return schemas.TokenResponse(access_token=token, role=user.role, full_name=user.full_name)


@app.get("/auth/me")
def read_me(user: models.User = Depends(auth.get_current_user)):
    return {"username": user.username, "full_name": user.full_name, "role": user.role}


@app.post("/auth/download-token")
def get_download_token(user: models.User = Depends(auth.get_current_user)):
    """
    Issues a 60-second, download-only token - requires the normal
    Authorization header (proper auth, not a URL param), then hands
    back a short-lived token that export/backup links can safely carry
    in their query string instead of the real session token.
    """
    return {"token": auth.create_download_token(user.username)}


@app.post("/auth/change-password")
def change_password(payload: schemas.ChangePasswordRequest, db: Session = Depends(get_db),
                     user: models.User = Depends(auth.get_current_user)):
    if not auth.verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters.")
    user.hashed_password = auth.hash_password(payload.new_password)
    db.commit()
    log_action(db, user.id, "change_password")
    return {"ok": True}


# ---------------------------------------------------------------------
# USER MANAGEMENT (admin only - lets staff have their own logins
# instead of everyone sharing the one admin account)
# ---------------------------------------------------------------------
@app.get("/users", response_model=list[schemas.UserOut])
def list_users(db: Session = Depends(get_db), user: models.User = Depends(auth.require_admin)):
    return db.query(models.User).order_by(models.User.username).all()


@app.post("/users", response_model=schemas.UserOut)
def create_user(payload: schemas.UserIn, db: Session = Depends(get_db),
                 user: models.User = Depends(auth.require_admin)):
    existing = db.query(models.User).filter(models.User.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="That username is already taken.")
    new_user = models.User(
        username=payload.username,
        hashed_password=auth.hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    log_action(db, user.id, "create_user", f"{payload.username} ({payload.role})")
    return new_user


@app.delete("/users/{user_id}")
def deactivate_user(user_id: int, db: Session = Depends(get_db),
                     user: models.User = Depends(auth.require_admin)):
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == user.id:
        raise HTTPException(status_code=400, detail="You can't deactivate your own account.")
    target.active = False
    db.commit()
    log_action(db, user.id, "deactivate_user", target.username)
    return {"ok": True}


@app.get("/audit-log")
def list_audit_log(limit: int = 200, db: Session = Depends(get_db),
                    user: models.User = Depends(auth.require_admin)):
    rows = (
        db.query(models.AuditLog, models.User.username, models.User.full_name)
        .outerjoin(models.User, models.AuditLog.user_id == models.User.id)
        .order_by(models.AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": log.id, "action": log.action, "details": log.details,
            "created_at": log.created_at.isoformat() if log.created_at else None,
            "username": username or "unknown", "full_name": full_name or "Unknown",
        }
        for log, username, full_name in rows
    ]


# ---------------------------------------------------------------------
# MASTER DATA - Employees
# ---------------------------------------------------------------------
@app.get("/employees", response_model=list[schemas.EmployeeOut])
def list_employees(active_only: bool = False, db: Session = Depends(get_db),
                    user: models.User = Depends(auth.get_current_user)):
    q = db.query(models.Employee)
    if active_only:
        q = q.filter(models.Employee.active == True)  # noqa: E712
    return q.order_by(models.Employee.emp_no).all()


@app.post("/employees", response_model=schemas.EmployeeOut)
def upsert_employee(emp: schemas.EmployeeIn, db: Session = Depends(get_db),
                     user: models.User = Depends(auth.require_admin)):
    existing = db.query(models.Employee).filter(models.Employee.emp_no == emp.emp_no).first()
    if existing:
        for field, value in emp.dict().items():
            setattr(existing, field, value)
    else:
        existing = models.Employee(**emp.dict())
        db.add(existing)
    db.commit()
    db.refresh(existing)
    log_action(db, user.id, "save_employee", f"{emp.emp_no} - {emp.name}")
    return existing


@app.delete("/employees/{emp_no}")
def deactivate_employee(emp_no: str, db: Session = Depends(get_db),
                         user: models.User = Depends(auth.require_admin)):
    emp = db.query(models.Employee).filter(models.Employee.emp_no == emp_no).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    emp.active = False
    db.commit()
    log_action(db, user.id, "deactivate_employee", emp_no)
    return {"ok": True}


EMPLOYEE_TEMPLATE_HEADERS = ["Emp No", "Name", "Trade", "Total Salary", "Basic Salary"]


@app.get("/employees/template")
def download_employee_template(token: str, db: Session = Depends(get_db)):
    """Blank spreadsheet with the exact columns /employees/import expects,
    so staff can fill it in offline and bring it back."""
    auth.get_download_user_from_token(token, db)
    wb = Workbook()
    ws = wb.active
    ws.title = "Employees"
    for i, h in enumerate(EMPLOYEE_TEMPLATE_HEADERS, start=1):
        c = ws.cell(row=1, column=i, value=h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="C0392B")
        ws.column_dimensions[get_column_letter(i)].width = 18
    ws.append(["D-99", "SAMPLE WORKER", "DRIVER", 2000, 900])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Infinia_Employee_Template.xlsx"},
    )


@app.post("/employees/import")
async def import_employees(file: UploadFile = File(...), db: Session = Depends(get_db),
                            user: models.User = Depends(auth.require_admin)):
    """
    Bulk create/update from the filled-in template - matches existing
    workers by Emp No (updates them) and creates anyone new, same rules
    as the one-at-a-time Add/Update Employee form.
    """
    contents = await file.read()
    try:
        wb = load_workbook(io.BytesIO(contents), data_only=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read that file - please upload the .xlsx template.")
    ws = wb.active

    header_row = [str(c.value).strip() if c.value else "" for c in ws[1]]
    expected = {h.lower(): i for i, h in enumerate(header_row)}
    required = ["emp no", "name"]
    if not all(r in expected for r in required):
        raise HTTPException(status_code=400, detail="Missing required columns 'Emp No' and 'Name' - please use the template.")

    created, updated, errors = 0, 0, []
    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not row or all(v is None or str(v).strip() == "" for v in row):
            continue

        def get(col_name, default=""):
            idx = expected.get(col_name)
            if idx is None or idx >= len(row):
                return default
            val = row[idx]
            return val if val is not None else default

        emp_no = str(get("emp no")).strip()
        name = str(get("name")).strip()
        if not emp_no or not name:
            errors.append(f"Row {row_idx}: missing Emp No or Name, skipped.")
            continue
        try:
            total_salary = float(get("total salary", 0) or 0)
            basic_salary = float(get("basic salary", 0) or 0)
        except (TypeError, ValueError):
            errors.append(f"Row {row_idx} ({emp_no}): Total/Basic Salary must be numbers, skipped.")
            continue
        trade = str(get("trade", "")).strip()

        existing = db.query(models.Employee).filter(models.Employee.emp_no == emp_no).first()
        if existing:
            existing.name, existing.trade = name, trade
            existing.total_salary, existing.basic_salary = total_salary, basic_salary
            existing.active = True
            updated += 1
        else:
            db.add(models.Employee(emp_no=emp_no, name=name, trade=trade,
                                    total_salary=total_salary, basic_salary=basic_salary, active=True))
            created += 1
    db.commit()
    log_action(db, user.id, "import_employees", f"{created} created, {updated} updated, {len(errors)} errors")
    return {"created": created, "updated": updated, "errors": errors}


# ---------------------------------------------------------------------
# MASTER DATA - Sites / Engineers
# ---------------------------------------------------------------------
@app.get("/sites", response_model=list[schemas.SiteOut])
def list_sites(db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    return db.query(models.Site).filter(models.Site.active == True).order_by(models.Site.code).all()  # noqa: E712


@app.post("/sites", response_model=schemas.SiteOut)
def add_site(site: schemas.SiteIn, db: Session = Depends(get_db), user: models.User = Depends(auth.require_admin)):
    existing = db.query(models.Site).filter(models.Site.code == site.code).first()
    if existing:
        existing.active = True
        db.commit()
        db.refresh(existing)
        return existing
    new_site = models.Site(**site.dict())
    db.add(new_site)
    db.commit()
    db.refresh(new_site)
    return new_site


@app.put("/sites/{site_id}", response_model=schemas.SiteOut)
def rename_site(site_id: int, site: schemas.SiteIn, db: Session = Depends(get_db),
                 user: models.User = Depends(auth.require_admin)):
    existing = db.query(models.Site).filter(models.Site.id == site_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Site not found")
    existing.code = site.code
    db.commit()
    db.refresh(existing)
    log_action(db, user.id, "rename_site", f"#{site_id} -> {site.code}")
    return existing


@app.delete("/sites/{site_id}")
def remove_site(site_id: int, db: Session = Depends(get_db), user: models.User = Depends(auth.require_admin)):
    existing = db.query(models.Site).filter(models.Site.id == site_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Site not found")
    existing.active = False
    db.commit()
    log_action(db, user.id, "remove_site", existing.code)
    return {"ok": True}


@app.get("/engineers", response_model=list[schemas.EngineerOut])
def list_engineers(db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    return db.query(models.Engineer).filter(models.Engineer.active == True).order_by(models.Engineer.name).all()  # noqa: E712


@app.post("/engineers", response_model=schemas.EngineerOut)
def add_engineer(eng: schemas.EngineerIn, db: Session = Depends(get_db),
                  user: models.User = Depends(auth.require_admin)):
    existing = db.query(models.Engineer).filter(models.Engineer.name == eng.name).first()
    if existing:
        existing.active = True
        db.commit()
        db.refresh(existing)
        return existing
    new_eng = models.Engineer(**eng.dict())
    db.add(new_eng)
    db.commit()
    db.refresh(new_eng)
    return new_eng


@app.put("/engineers/{engineer_id}", response_model=schemas.EngineerOut)
def rename_engineer(engineer_id: int, eng: schemas.EngineerIn, db: Session = Depends(get_db),
                     user: models.User = Depends(auth.require_admin)):
    existing = db.query(models.Engineer).filter(models.Engineer.id == engineer_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Engineer not found")
    existing.name = eng.name
    db.commit()
    db.refresh(existing)
    log_action(db, user.id, "rename_engineer", f"#{engineer_id} -> {eng.name}")
    return existing


@app.delete("/engineers/{engineer_id}")
def remove_engineer(engineer_id: int, db: Session = Depends(get_db), user: models.User = Depends(auth.require_admin)):
    existing = db.query(models.Engineer).filter(models.Engineer.id == engineer_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Engineer not found")
    existing.active = False
    db.commit()
    log_action(db, user.id, "remove_engineer", existing.name)
    return {"ok": True}


# ---------------------------------------------------------------------
# DAILY ATTENDANCE
# ---------------------------------------------------------------------
@app.get("/attendance/{target_date}", response_model=list[schemas.DailyRowOut])
def get_attendance_for_date(target_date: date, db: Session = Depends(get_db),
                             user: models.User = Depends(auth.get_current_user)):
    return db.query(models.DailyRow).filter(models.DailyRow.full_date == target_date).all()


@app.get("/attendance/completion/{month_year}")
def get_completion_status(month_year: str, db: Session = Depends(get_db),
                           user: models.User = Depends(auth.get_current_user)):
    """
    Per-day completion status for the whole cycle, for the dashboard
    calendar: a day is 'complete' when every currently-active employee
    has a saved attendance row for it. Mirrors the desktop app's own
    dashboard calendar (green = complete, red = incomplete).
    """
    from datetime import datetime as dt, timedelta as td
    try:
        parsed = dt.strptime(f"25 {month_year}", "%d %B %Y").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="month_year must look like 'August 2026'.")
    cycle_start, cycle_end, _ = pcyc.cycle_bounds_for(parsed)

    total_active = db.query(models.Employee).filter(models.Employee.active == True).count()  # noqa: E712
    rows = db.query(models.DailyRow.full_date, models.DailyRow.emp_no).filter(
        and_(models.DailyRow.full_date >= cycle_start, models.DailyRow.full_date <= cycle_end)
    ).all()
    counts_by_date = {}
    for full_date, emp_no in rows:
        counts_by_date.setdefault(full_date, set()).add(emp_no)

    days = []
    d = cycle_start
    while d <= cycle_end:
        entered = len(counts_by_date.get(d, set()))
        days.append({"date": d.isoformat(), "entered": entered, "total": total_active,
                      "complete": total_active > 0 and entered >= total_active})
        d += td(days=1)
    return {"cycle_start": cycle_start.isoformat(), "cycle_end": cycle_end.isoformat(),
            "total_active": total_active, "days": days}


@app.post("/attendance/save")
def save_attendance(payload: schemas.BulkSaveRequest, db: Session = Depends(get_db),
                     user: models.User = Depends(auth.get_current_user)):
    """
    Same validation and Holiday-previous-day rules as the desktop app's
    save_all(): every row is validated BEFORE anything is written, a
    row cleared back to blank deletes any existing saved entry instead
    of being silently skipped, and Holiday specifically requires
    Site/Engineer to come from that worker's own saved entry the day
    before - blocked with the exact missing date if that isn't there.
    """
    errors = []
    blocked = []
    to_process = []

    for row_in in payload.rows:
        employee = db.query(models.Employee).filter(models.Employee.emp_no == row_in.emp_no).first()
        if not employee:
            errors.append(f"{row_in.emp_no}: employee not found.")
            continue

        am, pm = (row_in.am or "").strip(), (row_in.pm or "").strip()
        if not am and not pm:
            # Cleared row - delete any existing saved entry for this day.
            services.delete_daily_row_if_blank(db, row_in.emp_no, row_in.full_date)
            to_process.append((employee, None))
            continue

        site, engineer = row_in.site, row_in.engineer
        if am == "Holiday" or pm == "Holiday":
            prev = services.get_previous_day_site_engineer(db, row_in.emp_no, row_in.full_date)
            if prev is None:
                from datetime import timedelta
                prev_date = row_in.full_date - timedelta(days=1)
                blocked.append(f"{row_in.emp_no} ({employee.name}) - needs {prev_date} filled in first")
                continue
            site, engineer = prev
            row_in.site, row_in.engineer = site, engineer

        problems = services.validate_row(am, pm, site, engineer, row_in.bh, row_in.comments)
        if problems:
            errors.append(f"{row_in.emp_no}: " + "; ".join(problems))
            continue

        to_process.append((employee, row_in))

    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    touched_cycles = set()
    for employee, row_in in to_process:
        if row_in is not None:
            services.upsert_daily_row(db, employee, row_in)
            _, _, month_year = pcyc.cycle_bounds_for(row_in.full_date)
        else:
            # a delete - recalc using whatever cycle the deleted date was in
            if payload.rows:
                _, _, month_year = pcyc.cycle_bounds_for(payload.rows[0].full_date)
            else:
                continue
        touched_cycles.add((employee.emp_no, month_year))

    for emp_no, month_year in touched_cycles:
        employee = db.query(models.Employee).filter(models.Employee.emp_no == emp_no).first()
        services.recalculate_summary(db, employee, month_year)

    saved_count = len([r for e, r in to_process if r is not None])
    if saved_count or blocked:
        the_date = payload.rows[0].full_date if payload.rows else ""
        log_action(db, user.id, "save_attendance", f"{the_date}: {saved_count} worker(s)")

    return {"saved": saved_count, "blocked": blocked}


# ---------------------------------------------------------------------
# EMPLOYEE SUMMARIES / SALARY ADJUSTMENTS
# ---------------------------------------------------------------------
@app.get("/summaries/{month_year}", response_model=list[schemas.EmployeeSummaryOut])
def list_summaries(month_year: str, db: Session = Depends(get_db),
                    user: models.User = Depends(auth.get_current_user)):
    summaries = (
        db.query(models.EmployeeSummary)
        .options(joinedload(models.EmployeeSummary.adjustments))
        .filter(models.EmployeeSummary.month_year == month_year)
        .order_by(models.EmployeeSummary.emp_no)
        .all()
    )
    # Site isn't a stored summary field - a worker can be at a different
    # site each day - so it's aggregated here as the distinct sites
    # worked during the cycle, not pulled from a column.
    site_rows = (
        db.query(models.DailyRow.emp_no, models.DailyRow.site)
        .filter(models.DailyRow.month_year == month_year, models.DailyRow.site != "")
        .distinct()
        .all()
    )
    sites_by_emp = {}
    for emp_no, site in site_rows:
        if site:
            sites_by_emp.setdefault(emp_no, []).append(site)

    out = []
    for s in summaries:
        item = schemas.EmployeeSummaryOut.from_orm(s)
        item.sites = ", ".join(sorted(set(sites_by_emp.get(s.emp_no, []))))
        out.append(item)
    return out


@app.get("/summaries/{month_year}/by-site")
def summaries_by_site(month_year: str, db: Session = Depends(get_db),
                       user: models.User = Depends(auth.get_current_user)):
    """
    One row per site: how many workers were there during the cycle and
    the sum of their Final Salary / Adjusted Final Salary. A worker who
    was at more than one site during the cycle counts in full toward
    each site they worked at (not split proportionally) - this answers
    'how much did we spend at site X this month', not an exact per-site
    salary breakdown.
    """
    summaries = (
        db.query(models.EmployeeSummary)
        .options(joinedload(models.EmployeeSummary.adjustments))
        .filter(models.EmployeeSummary.month_year == month_year)
        .all()
    )
    site_rows = (
        db.query(models.DailyRow.emp_no, models.DailyRow.site)
        .filter(models.DailyRow.month_year == month_year, models.DailyRow.site != "")
        .distinct().all()
    )
    sites_by_emp = {}
    for emp_no, site in site_rows:
        if site:
            sites_by_emp.setdefault(emp_no, set()).add(site)

    by_site = {}
    for s in summaries:
        adjusted = s.final_salary + sum(-a.amount if a.is_deduction else a.amount for a in s.adjustments)
        for site in sites_by_emp.get(s.emp_no, set()):
            entry = by_site.setdefault(site, {"site": site, "worker_count": 0, "workers": [],
                                               "total_final_salary": 0.0, "total_adjusted_final_salary": 0.0})
            entry["worker_count"] += 1
            entry["workers"].append(s.emp_no)
            entry["total_final_salary"] += s.final_salary
            entry["total_adjusted_final_salary"] += adjusted

    return sorted(by_site.values(), key=lambda x: x["site"])


@app.get("/live-card/{emp_no}/{month_year}")
def get_live_card(emp_no: str, month_year: str, db: Session = Depends(get_db),
                   user: models.User = Depends(auth.get_current_user)):
    """
    Everything needed to render one worker's card on screen: their
    summary totals for the cycle plus every daily row, keyed by day -
    mirrors the desktop app's Live Card view.
    """
    summary = (
        db.query(models.EmployeeSummary)
        .options(joinedload(models.EmployeeSummary.adjustments))
        .filter(and_(models.EmployeeSummary.emp_no == emp_no, models.EmployeeSummary.month_year == month_year))
        .first()
    )
    rows = (
        db.query(models.DailyRow)
        .filter(and_(models.DailyRow.emp_no == emp_no, models.DailyRow.month_year == month_year))
        .all()
    )
    rows_by_day = {r.day: schemas.DailyRowOut.from_orm(r) for r in rows}
    if summary:
        summary_out = schemas.EmployeeSummaryOut.from_orm(summary)
    else:
        emp = db.query(models.Employee).filter(models.Employee.emp_no == emp_no).first()
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found.")
        summary_out = None
    return {
        "emp_no": emp_no, "month_year": month_year,
        "summary": summary_out, "days": rows_by_day,
    }


@app.post("/summaries/{summary_id}/adjustments", response_model=schemas.SalaryAdjustmentOut)
def add_adjustment(summary_id: int, adj: schemas.SalaryAdjustmentIn, db: Session = Depends(get_db),
                    user: models.User = Depends(auth.get_current_user)):
    summary = db.query(models.EmployeeSummary).filter(models.EmployeeSummary.id == summary_id).first()
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")
    new_adj = models.SalaryAdjustment(summary_id=summary_id, created_by=user.id, **adj.dict())
    db.add(new_adj)
    db.commit()
    db.refresh(new_adj)
    log_action(db, user.id, "add_adjustment",
               f"{summary.emp_no} - {adj.description}: {'-' if adj.is_deduction else '+'}{adj.amount}")
    return new_adj


@app.delete("/adjustments/{adjustment_id}")
def remove_adjustment(adjustment_id: int, db: Session = Depends(get_db),
                       user: models.User = Depends(auth.get_current_user)):
    adj = db.query(models.SalaryAdjustment).filter(models.SalaryAdjustment.id == adjustment_id).first()
    if not adj:
        raise HTTPException(status_code=404, detail="Adjustment not found")
    summary = db.query(models.EmployeeSummary).filter(models.EmployeeSummary.id == adj.summary_id).first()
    detail = f"{summary.emp_no} - {adj.description}" if summary else adj.description
    db.delete(adj)
    db.commit()
    log_action(db, user.id, "remove_adjustment", detail)
    return {"ok": True}


@app.get("/")
def root():
    return {"service": "Infinia Labour Tool API", "status": "running",
            "docs": "See /health for a simple status check."}


@app.get("/error-check/{month_year}")
def error_check(month_year: str, db: Session = Depends(get_db),
                 user: models.User = Depends(auth.get_current_user)):
    """
    The desktop app's original three checks (missing AM/P.M, Present
    without Site/Engineer, BH without a comment) can never actually
    happen here - /attendance/save already enforces those exact same
    rules before a row is ever written, so this would always come back
    empty. What genuinely CAN go wrong in the web app instead: a day
    inside the cycle with no entry at all for an active worker, or an
    OT/BH value large enough to be worth a second look.
    """
    try:
        parsed = __import__("datetime").datetime.strptime(f"25 {month_year}", "%d %B %Y").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="month_year must look like 'August 2026'.")
    cycle_start, cycle_end, _ = pcyc.cycle_bounds_for(parsed)

    active_employees = db.query(models.Employee).filter(models.Employee.active == True).all()  # noqa: E712
    rows = db.query(models.DailyRow).filter(models.DailyRow.month_year == month_year).all()

    dates_by_emp = {}
    for r in rows:
        dates_by_emp.setdefault(r.emp_no, set()).add(r.full_date)

    from datetime import timedelta
    all_dates = []
    d = cycle_start
    while d <= cycle_end:
        all_dates.append(d)
        d += timedelta(days=1)

    out = []
    for emp in active_employees:
        entered = dates_by_emp.get(emp.emp_no, set())
        missing = [d for d in all_dates if d not in entered]
        if not entered:
            out.append({"emp_no": emp.emp_no, "name": emp.name, "date": "-", "site": "-",
                        "issue": f"No attendance entered at all for {month_year}."})
        elif missing:
            preview = ", ".join(d.strftime("%d %b") for d in missing[:5])
            more = f" (+{len(missing) - 5} more)" if len(missing) > 5 else ""
            out.append({"emp_no": emp.emp_no, "name": emp.name, "date": "-", "site": "-",
                        "issue": f"{len(missing)} day(s) missing: {preview}{more}"})

    for r in rows:
        if r.ot and r.ot > 12:
            out.append({"emp_no": r.emp_no, "name": r.emp_name, "date": str(r.full_date), "site": r.site,
                        "issue": f"OT of {r.ot} hours in one day looks unusually high."})
        if r.bh and r.bh > 8:
            out.append({"emp_no": r.emp_no, "name": r.emp_name, "date": str(r.full_date), "site": r.site,
                        "issue": f"BH of {r.bh} hours in one day looks unusually high."})

    out.sort(key=lambda x: (x["emp_no"], str(x["date"])))
    return {
        "title": "Check for Errors",
        "note": "Missing days in this cycle for active workers, plus unusually high single-day OT/BH values.",
        "rows": out,
    }


@app.get("/export/{month_year}/excel")
def export_excel(month_year: str, token: str, db: Session = Depends(get_db)):
    # Auth comes ONLY via the ?token= query param here, not the standard
    # Authorization header - this endpoint is meant to be hit by a plain
    # browser navigation (window.open(url)), which can't set custom
    # headers at all. That's also the actual fix for exports doing
    # nothing on mobile: the old fetch()+blob()+<a download> approach
    # loses the "real user tap" context by the time the async blob is
    # ready, so mobile browsers silently block the download. A direct,
    # synchronous navigation has no such problem.
    user = auth.get_download_user_from_token(token, db)
    summaries = (
        db.query(models.EmployeeSummary)
        .options(joinedload(models.EmployeeSummary.adjustments))
        .filter(models.EmployeeSummary.month_year == month_year)
        .order_by(models.EmployeeSummary.emp_no)
        .all()
    )
    if not summaries:
        raise HTTPException(status_code=404, detail="No data found for this cycle.")
    pairs = []
    for s in summaries:
        rows = db.query(models.DailyRow).filter(
            and_(models.DailyRow.emp_no == s.emp_no, models.DailyRow.month_year == month_year)
        ).all()
        pairs.append((s, rows))
    buf = export_web.build_combined_excel(pairs)
    safe_name = "".join(c if c.isalnum() else "_" for c in month_year)
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=Infinia_Cards_{safe_name}.xlsx"},
    )


@app.get("/export/{month_year}/pdf")
def export_pdf(month_year: str, token: str, db: Session = Depends(get_db)):
    user = auth.get_download_user_from_token(token, db)
    summaries = (
        db.query(models.EmployeeSummary)
        .options(joinedload(models.EmployeeSummary.adjustments))
        .filter(models.EmployeeSummary.month_year == month_year)
        .order_by(models.EmployeeSummary.emp_no)
        .all()
    )
    if not summaries:
        raise HTTPException(status_code=404, detail="No data found for this cycle.")
    pairs = []
    for s in summaries:
        rows = db.query(models.DailyRow).filter(
            and_(models.DailyRow.emp_no == s.emp_no, models.DailyRow.month_year == month_year)
        ).all()
        pairs.append((s, rows))
    buf = export_web.build_combined_pdf(pairs)
    safe_name = "".join(c if c.isalnum() else "_" for c in month_year)
    return StreamingResponse(
        buf, media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Infinia_Cards_{safe_name}.pdf"},
    )


def _get_summary_pairs(month_year: str, db: Session):
    summaries = (
        db.query(models.EmployeeSummary)
        .options(joinedload(models.EmployeeSummary.adjustments))
        .filter(models.EmployeeSummary.month_year == month_year)
        .order_by(models.EmployeeSummary.emp_no)
        .all()
    )
    if not summaries:
        raise HTTPException(status_code=404, detail="No data found for this cycle.")
    pairs = []
    for s in summaries:
        rows = db.query(models.DailyRow).filter(
            and_(models.DailyRow.emp_no == s.emp_no, models.DailyRow.month_year == month_year)
        ).all()
        pairs.append((s, rows))
    return pairs


@app.get("/export/{month_year}/report-table")
def export_report_table(month_year: str, token: str, columns: str, format: str, db: Session = Depends(get_db)):
    """
    Exports the Report Builder's own preview - whatever columns are
    currently ticked, in one row per worker plus a totals row - as
    opposed to Combine, which always exports the full individual salary
    cards regardless of column selection.
    """
    user = auth.get_download_user_from_token(token, db)
    column_keys = [c for c in columns.split(",") if c]
    if not column_keys:
        raise HTTPException(status_code=400, detail="No columns selected.")
    summaries = (
        db.query(models.EmployeeSummary)
        .options(joinedload(models.EmployeeSummary.adjustments))
        .filter(models.EmployeeSummary.month_year == month_year)
        .order_by(models.EmployeeSummary.emp_no)
        .all()
    )
    site_rows = (
        db.query(models.DailyRow.emp_no, models.DailyRow.site)
        .filter(models.DailyRow.month_year == month_year, models.DailyRow.site != "")
        .distinct().all()
    )
    sites_by_emp = {}
    for emp_no, site in site_rows:
        if site:
            sites_by_emp.setdefault(emp_no, []).append(site)
    items = []
    for s in summaries:
        item = schemas.EmployeeSummaryOut.from_orm(s)
        item.sites = ", ".join(sorted(set(sites_by_emp.get(s.emp_no, []))))
        items.append(item)
    if not items:
        raise HTTPException(status_code=404, detail="No data found for this cycle.")

    safe_name = "".join(c if c.isalnum() else "_" for c in month_year)
    if format == "excel":
        buf = export_web.build_report_table_excel(items, column_keys, month_year)
        return StreamingResponse(
            buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=Infinia_Report_{safe_name}.xlsx"},
        )
    elif format == "pdf":
        buf = export_web.build_report_table_pdf(items, column_keys, month_year)
        return StreamingResponse(
            buf, media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=Infinia_Report_{safe_name}.pdf"},
        )
    raise HTTPException(status_code=400, detail="format must be 'excel' or 'pdf'.")


@app.get("/export/{month_year}/excel-separate")
def export_excel_separate(month_year: str, token: str, db: Session = Depends(get_db)):
    """One .xlsx per worker, zipped together - the 'Separate Files' option next to Combine."""
    user = auth.get_download_user_from_token(token, db)
    pairs = _get_summary_pairs(month_year, db)
    files = export_web.build_separate_excel_files(pairs)
    buf = export_web.zip_files(files)
    safe_name = "".join(c if c.isalnum() else "_" for c in month_year)
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=Infinia_Cards_Separate_{safe_name}.zip"},
    )


@app.get("/export/{month_year}/pdf-separate")
def export_pdf_separate(month_year: str, token: str, db: Session = Depends(get_db)):
    """One .pdf per worker, zipped together - the 'Separate Files' option next to Combine."""
    user = auth.get_download_user_from_token(token, db)
    pairs = _get_summary_pairs(month_year, db)
    files = export_web.build_separate_pdf_files(pairs)
    buf = export_web.zip_files(files)
    safe_name = "".join(c if c.isalnum() else "_" for c in month_year)
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=Infinia_Cards_Separate_{safe_name}.zip"},
    )


def _row_to_dict(obj):
    d = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        d[col.name] = val.isoformat() if hasattr(val, "isoformat") else val
    return d


def build_backup_data(db: Session) -> dict:
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "employees": [_row_to_dict(e) for e in db.query(models.Employee).all()],
        "sites": [_row_to_dict(s) for s in db.query(models.Site).all()],
        "engineers": [_row_to_dict(e) for e in db.query(models.Engineer).all()],
        "daily_rows": [_row_to_dict(r) for r in db.query(models.DailyRow).all()],
        "summaries": [_row_to_dict(s) for s in db.query(models.EmployeeSummary).all()],
        "adjustments": [_row_to_dict(a) for a in db.query(models.SalaryAdjustment).all()],
    }


def maybe_create_auto_backup(db: Session):
    """Called on login: creates one 'auto' backup per calendar month if
    one doesn't already exist yet, so a snapshot always exists even if
    nobody remembers to take one manually."""
    month_start = date.today().replace(day=1)
    existing = (
        db.query(models.Backup)
        .filter(models.Backup.trigger == "auto", models.Backup.created_at >= month_start)
        .first()
    )
    if existing:
        return
    data = build_backup_data(db)
    db.add(models.Backup(created_by=None, trigger="auto", data=json.dumps(data, default=str)))
    db.commit()


@app.post("/backup/create")
def create_backup(db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    """Any signed-in user can take a backup - it's a data-safety net,
    not something that should be gated behind admin access."""
    data = build_backup_data(db)
    b = models.Backup(created_by=user.id, trigger="manual", data=json.dumps(data, default=str))
    db.add(b)
    db.commit()
    db.refresh(b)
    log_action(db, user.id, "create_backup")
    return {"id": b.id, "created_at": b.created_at.isoformat(), "trigger": b.trigger}


@app.get("/backup/list")
def list_backups(db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    rows = (
        db.query(models.Backup, models.User.username)
        .outerjoin(models.User, models.Backup.created_by == models.User.id)
        .order_by(models.Backup.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {"id": b.id, "created_at": b.created_at.isoformat(), "trigger": b.trigger,
         "created_by": username or ("automatic" if b.trigger == "auto" else "unknown")}
        for b, username in rows
    ]


@app.get("/backup/{backup_id}/download")
def download_backup(backup_id: int, token: str, db: Session = Depends(get_db)):
    user = auth.get_download_user_from_token(token, db)
    b = db.query(models.Backup).filter(models.Backup.id == backup_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Backup not found.")
    log_action(db, user.id, "download_backup", f"backup #{backup_id}")
    buf = io.BytesIO(b.data.encode("utf-8"))
    ts = b.created_at.date().isoformat()
    return StreamingResponse(
        buf, media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=Infinia_Backup_{ts}_{backup_id}.json"},
    )


@app.post("/backup/{backup_id}/restore")
def restore_backup(backup_id: int, db: Session = Depends(get_db), user: models.User = Depends(auth.require_admin)):
    """
    Admin only, unlike taking a backup - this overwrites current data,
    so it stays behind the higher bar. Replaces employees, sites,
    engineers, daily rows, summaries, and adjustments with exactly
    what's in the chosen snapshot.
    """
    b = db.query(models.Backup).filter(models.Backup.id == backup_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Backup not found.")
    data = json.loads(b.data)

    db.query(models.SalaryAdjustment).delete()
    db.query(models.DailyRow).delete()
    db.query(models.EmployeeSummary).delete()
    db.query(models.Employee).delete()
    db.query(models.Site).delete()
    db.query(models.Engineer).delete()
    db.flush()

    def restore_rows(model, rows, date_fields=(), datetime_fields=()):
        for r in rows:
            r = dict(r)
            for f in date_fields:
                if r.get(f):
                    r[f] = date.fromisoformat(r[f])
            for f in datetime_fields:
                if r.get(f):
                    r[f] = datetime.fromisoformat(r[f])
            db.add(model(**r))

    restore_rows(models.Employee, data.get("employees", []), datetime_fields=("created_at", "updated_at"))
    restore_rows(models.Site, data.get("sites", []), datetime_fields=("created_at",))
    restore_rows(models.Engineer, data.get("engineers", []), datetime_fields=("created_at",))
    restore_rows(models.DailyRow, data.get("daily_rows", []), date_fields=("full_date",), datetime_fields=("created_at", "updated_at"))
    restore_rows(models.EmployeeSummary, data.get("summaries", []), datetime_fields=("created_at", "updated_at"))
    db.commit()

    for a in data.get("adjustments", []):
        a = dict(a)
        if a.get("created_at"):
            a["created_at"] = datetime.fromisoformat(a["created_at"])
        db.add(models.SalaryAdjustment(**a))
    db.commit()

    log_action(db, user.id, "restore_backup", f"restored from backup #{backup_id}")
    return {"ok": True, "restored_from": backup_id}


@app.get("/health")
def health_check():
    return {"status": "ok"}

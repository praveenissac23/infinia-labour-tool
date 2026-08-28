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

from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, func
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from database import get_db, engine, Base, SessionLocal
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
    # Only seed from master_data.json when there are NO employees yet.
    # Re-running it on every boot meant the file was the permanent source
    # of truth: employees deleted in the app were silently re-inserted at
    # the next restart, which is what kept resurrecting the F793-F798
    # duplicates and eventually crashed startup against the unique index.
    # Once real data exists, the database is authoritative, not the file.
    # Add any newly-introduced columns to tables that already exist.
    # create_all() only creates missing TABLES, never missing columns, so
    # without this a new field works on a fresh database but breaks every
    # existing one - which is exactly what the store rental fields did.
    _add_missing_columns()

    db = SessionLocal()
    try:
        already_seeded = db.query(models.Employee).count() > 0
    finally:
        db.close()
    if already_seeded:
        seed_data.run(None)          # users/defaults only, no employee import
        return
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
def list_users(db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    return db.query(models.User).order_by(models.User.username).all()


@app.post("/users", response_model=schemas.UserOut)
def create_user(payload: schemas.UserIn, db: Session = Depends(get_db),
                 user: models.User = Depends(auth.get_current_user)):
    # Staff can add fellow staff, but only an admin can mint another
    # admin - otherwise any staff login could promote itself (or a new
    # account) to admin, which would make every admin-only restriction
    # meaningless, including the Activity Monitor.
    if payload.role != "staff" and user.role != "admin":
        raise HTTPException(status_code=403, detail="Only an admin can create an admin account.")
    existing = db.query(models.User).filter(models.User.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="That username is already taken.")
    new_user = models.User(
        username=payload.username,
        hashed_password=auth.hash_password(payload.password),
        # Full name is no longer collected when creating a login; fall
        # back to the username so the Activity Monitor and header still
        # have something readable to show.
        full_name=(payload.full_name or "").strip() or payload.username,
        role=payload.role,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    log_action(db, user.id, "create_user", f"{payload.username} ({payload.role})")
    return new_user


@app.delete("/users/{user_id}")
def deactivate_user(user_id: int, db: Session = Depends(get_db),
                     user: models.User = Depends(auth.get_current_user)):
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == user.id:
        raise HTTPException(status_code=400, detail="You can't deactivate your own account.")
    # Same reasoning as create_user - staff must not be able to lock the
    # real admin out of the system by deactivating the admin account.
    if target.role == "admin" and user.role != "admin":
        raise HTTPException(status_code=403, detail="Only an admin can deactivate an admin account.")
    target.active = False
    db.commit()
    log_action(db, user.id, "deactivate_user", target.username)
    return {"ok": True}


@app.post("/users/{user_id}/reset-password")
def reset_user_password(user_id: int, payload: schemas.ResetPasswordRequest,
                         db: Session = Depends(get_db),
                         user: models.User = Depends(auth.get_current_user)):
    """
    Set another user's password without knowing their current one - for
    when someone forgets theirs. Anyone can reset a staff account (staff
    manage staff), but only an admin can reset an admin's, matching the
    same rule that governs creating and deactivating admins.
    """
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.role == "admin" and user.role != "admin":
        raise HTTPException(status_code=403, detail="Only an admin can reset an admin's password.")
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters.")
    target.hashed_password = auth.hash_password(payload.new_password)
    db.commit()
    log_action(db, user.id, "reset_password", target.username)
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
                     user: models.User = Depends(auth.get_current_user)):
    existing = db.query(models.Employee).filter(models.Employee.emp_no == emp.emp_no).first()
    if existing:
        for field, value in emp.dict().items():
            setattr(existing, field, value)
    else:
        existing = models.Employee(**emp.dict())
        db.add(existing)
    db.commit()
    db.refresh(existing)

    # Salary figures live on the Employee record but are copied into every
    # EmployeeSummary when it's calculated, so editing Total/Basic Salary
    # has to recalculate this worker's existing summaries - otherwise the
    # cards, reports and payroll totals keep showing the OLD salary
    # indefinitely, with no indication they're stale.
    for (cycle,) in db.query(models.EmployeeSummary.month_year).filter(
        models.EmployeeSummary.emp_no == existing.emp_no
    ).distinct().all():
        services.recalculate_summary(db, existing, cycle)

    log_action(db, user.id, "save_employee", f"{emp.emp_no} - {emp.name}")
    return existing


@app.delete("/employees/{emp_no}")
def deactivate_employee(emp_no: str, db: Session = Depends(get_db),
                         user: models.User = Depends(auth.get_current_user)):
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


@app.get("/employees/export")
def export_employees(token: str, db: Session = Depends(get_db)):
    """
    Every active employee's master data, in the exact same column
    format /employees/import expects - export this, edit it, and
    re-import it straight back in without reshaping anything.
    """
    auth.get_download_user_from_token(token, db)
    employees = db.query(models.Employee).filter(models.Employee.active == True).order_by(models.Employee.emp_no).all()  # noqa: E712
    wb = Workbook()
    ws = wb.active
    ws.title = "Employees"
    for i, h in enumerate(EMPLOYEE_TEMPLATE_HEADERS, start=1):
        c = ws.cell(row=1, column=i, value=h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="C0392B")
        ws.column_dimensions[get_column_letter(i)].width = 18
    for emp in employees:
        ws.append([emp.emp_no, emp.name, emp.trade, emp.total_salary, emp.basic_salary])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Infinia_Employee_Export.xlsx"},
    )


@app.post("/employees/import")
async def import_employees(file: UploadFile = File(...), mode: str = Form("add_only"),
                            duplicate_handling: str = Form("skip"),
                            db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    """
    Bulk create from the filled-in template, with explicit control over
    two independent choices instead of always silently updating:

    mode: 'add_only' leaves every existing employee alone; 'replace'
    deactivates any active employee whose Emp No isn't in this file
    (soft-delete via the same 'active' flag the rest of the app uses -
    never a hard delete, since that would break their historical
    DailyRow/EmployeeSummary records).

    duplicate_handling: what to do when a row's Emp No already exists -
    'skip' leaves the existing record untouched, 'update' overwrites it
    with the file's data, 'add_new' creates a second, separate record
    under a modified Emp No (e.g. "D-01 (1)") so both exist side by side.
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

    def unique_suffixed_emp_no(base_emp_no):
        n = 1
        while True:
            candidate = f"{base_emp_no} ({n})"
            if not db.query(models.Employee).filter(models.Employee.emp_no == candidate).first():
                return candidate
            n += 1

    created, updated, skipped, added_as_new, errors = 0, 0, 0, 0, []
    updated_emp_nos = set()
    file_emp_nos = set()
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
        file_emp_nos.add(emp_no)

        existing = db.query(models.Employee).filter(models.Employee.emp_no == emp_no).first()
        if existing:
            if duplicate_handling == "skip":
                skipped += 1
            elif duplicate_handling == "add_new":
                new_emp_no = unique_suffixed_emp_no(emp_no)
                db.add(models.Employee(emp_no=new_emp_no, name=name, trade=trade,
                                        total_salary=total_salary, basic_salary=basic_salary, active=True))
                added_as_new += 1
            else:  # update
                existing.name, existing.trade = name, trade
                existing.total_salary, existing.basic_salary = total_salary, basic_salary
                existing.active = True
                updated += 1
                updated_emp_nos.add(emp_no)
        else:
            db.add(models.Employee(emp_no=emp_no, name=name, trade=trade,
                                    total_salary=total_salary, basic_salary=basic_salary, active=True))
            created += 1

    deactivated = 0
    if mode == "replace":
        active_not_in_file = (
            db.query(models.Employee)
            .filter(models.Employee.active == True, ~models.Employee.emp_no.in_(file_emp_nos))  # noqa: E712
            .all()
        )
        for emp in active_not_in_file:
            emp.active = False
            deactivated += 1

    db.commit()

    # Any employee whose salary figures were just overwritten needs their
    # existing summaries recalculated, same reason as upsert_employee -
    # otherwise cards and reports keep showing the pre-import salary.
    for emp_no in updated_emp_nos:
        emp_obj = db.query(models.Employee).filter(models.Employee.emp_no == emp_no).first()
        if not emp_obj:
            continue
        for (cycle,) in db.query(models.EmployeeSummary.month_year).filter(
            models.EmployeeSummary.emp_no == emp_no
        ).distinct().all():
            services.recalculate_summary(db, emp_obj, cycle)

    log_action(db, user.id, "import_employees",
               f"{created} created, {updated} updated, {skipped} skipped, "
               f"{added_as_new} added as new, {deactivated} deactivated, {len(errors)} errors")
    return {"created": created, "updated": updated, "skipped": skipped,
            "added_as_new": added_as_new, "deactivated": deactivated, "errors": errors}


# ---------------------------------------------------------------------
# MASTER DATA - Sites / Engineers
# ---------------------------------------------------------------------
@app.get("/sites", response_model=list[schemas.SiteOut])
def list_sites(db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    return db.query(models.Site).filter(models.Site.active == True).order_by(models.Site.code).all()  # noqa: E712


@app.post("/sites", response_model=schemas.SiteOut)
def add_site(site: schemas.SiteIn, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
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
                 user: models.User = Depends(auth.get_current_user)):
    existing = db.query(models.Site).filter(models.Site.id == site_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Site not found")
    existing.code = site.code
    db.commit()
    db.refresh(existing)
    log_action(db, user.id, "rename_site", f"#{site_id} -> {site.code}")
    return existing


@app.delete("/sites/{site_id}")
def remove_site(site_id: int, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
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
                  user: models.User = Depends(auth.get_current_user)):
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
                     user: models.User = Depends(auth.get_current_user)):
    existing = db.query(models.Engineer).filter(models.Engineer.id == engineer_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Engineer not found")
    existing.name = eng.name
    db.commit()
    db.refresh(existing)
    log_action(db, user.id, "rename_engineer", f"#{engineer_id} -> {eng.name}")
    return existing


@app.delete("/engineers/{engineer_id}")
def remove_engineer(engineer_id: int, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
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


@app.delete("/attendance/{target_date}")
def clear_attendance_for_date(target_date: date, db: Session = Depends(get_db),
                               user: models.User = Depends(auth.get_current_user)):
    """
    Deletes every worker's attendance row for one specific date - the
    'Clear Day' button's confirmed action. Admin-only, since this wipes
    every worker's entry for the day at once, not just one row.
    """
    count = (
        db.query(models.DailyRow)
        .filter(models.DailyRow.full_date == target_date)
        .delete(synchronize_session=False)
    )
    db.commit()
    log_action(db, user.id, "clear_day", f"{target_date}: {count} row(s) deleted")
    return {"deleted": count}


@app.get("/attendance/completion/{month_year}")
def get_completion_status(month_year: str, mode: str = "cycle",
                           db: Session = Depends(get_db),
                           user: models.User = Depends(auth.get_current_user)):
    """
    Per-day completion status for the calendar: a day is 'complete' when
    every currently-active employee has a saved attendance row for it
    (green = complete, red = incomplete).

    mode="cycle"    - the payroll cycle, 26th of the previous month to
                      the 25th of this one. Used where the view must
                      line up with payroll.
    mode="calendar" - the plain calendar month, 1st to last day. Used by
                      the dashboard/attendance calendars, because a
                      normal month is what people actually recognise
                      when scanning for a date.
    """
    from datetime import datetime as dt, timedelta as td
    import calendar as _cal
    try:
        parsed = dt.strptime(f"25 {month_year}", "%d %B %Y").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="month_year must look like 'August 2026'.")
    if mode == "calendar":
        cycle_start = parsed.replace(day=1)
        last = _cal.monthrange(parsed.year, parsed.month)[1]
        cycle_end = parsed.replace(day=last)
    else:
        cycle_start, cycle_end, _ = pcyc.cycle_bounds_for(parsed)

    total_active = db.query(models.Employee).filter(models.Employee.active == True).count()  # noqa: E712
    rows = db.query(models.DailyRow.full_date, models.DailyRow.emp_no).filter(
        and_(models.DailyRow.full_date >= cycle_start, models.DailyRow.full_date <= cycle_end,
             or_(models.DailyRow.am != "", models.DailyRow.pm != ""))
        # excludes rows that exist only because auto_fill_sunday_from_saturday
        # pre-filled Site/Engineer with A.M/P.M still blank - those aren't
        # "marked" yet, so they must not count toward the day being complete
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
    row cleared back to fully blank (no A.M/P.M and no Site) deletes
    any existing saved entry instead of being silently skipped, and
    Holiday specifically requires Site/Engineer to come from that
    worker's own saved entry the day before - blocked with the exact
    missing date if that isn't there.

    A row with blank A.M/P.M but a real Site (an auto-filled Sunday
    placeholder, or staff editing just the Site before marking
    A.M/P.M) is kept rather than deleted - every save resubmits ALL
    workers for the date, so treating that the same as a genuine clear
    would silently wipe out every other worker's still-unmarked
    placeholder too.
    """
    errors = []
    blocked = []
    to_process = []

    today = date.today()
    for row_in in payload.rows:
        # Attendance can't be recorded for a day that hasn't happened yet.
        # Without this the app accepted any date at all - a save for
        # 25 December went through months early - and those future days
        # count as worked in the payroll totals, inflating salaries.
        if row_in.full_date > today:
            errors.append(f"{row_in.emp_no}: {row_in.full_date} is in the future - attendance can only be entered up to today.")
            continue

        employee = db.query(models.Employee).filter(models.Employee.emp_no == row_in.emp_no).first()
        if not employee:
            errors.append(f"{row_in.emp_no}: employee not found.")
            continue

        am, pm = (row_in.am or "").strip(), (row_in.pm or "").strip()
        site_val = (row_in.site or "").strip()
        if not am and not pm:
            if not site_val:
                # Genuinely blank - delete any existing saved entry for this day.
                services.delete_daily_row_if_blank(db, row_in.emp_no, row_in.full_date)
                to_process.append((employee, None))
            else:
                # Blank A.M/P.M but a real Site - an auto-filled placeholder
                # (Saturday -> Sunday) staff hasn't marked yet, or staff
                # editing just the Site before marking A.M/P.M. Every save
                # resubmits ALL workers for the date, so treating this the
                # same as a genuine clear would silently wipe out every
                # other worker's still-unmarked placeholder too - keep/
                # update it instead, skip full validation since it isn't
                # a real attendance entry yet.
                row_in.am, row_in.pm = "", ""
                to_process.append((employee, row_in))
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

        problems = services.validate_row(am, pm, site, engineer, row_in.bh, row_in.comments, row_in.ot)
        if problems:
            errors.append(f"{row_in.emp_no}: " + "; ".join(problems))
            continue

        to_process.append((employee, row_in))

    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    touched_cycles = set()
    for employee, row_in in to_process:
        if row_in is not None:
            saved_row = services.upsert_daily_row(db, employee, row_in)
            services.auto_fill_sunday_from_saturday(db, employee, saved_row)
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
def list_summaries(month_year: str, as_of: str = None, db: Session = Depends(get_db),
                    user: models.User = Depends(auth.get_current_user)):
    """
    as_of (optional, YYYY-MM-DD): limits the Site column to that
    worker's most recent site on or before this date, instead of the
    latest site in the whole cycle - lets Reports answer 'who was
    where as of a given date', not just 'as of cycle end'.
    """
    summaries = (
        db.query(models.EmployeeSummary)
        .options(joinedload(models.EmployeeSummary.adjustments))
        .filter(models.EmployeeSummary.month_year == month_year)
        .order_by(models.EmployeeSummary.emp_no)
        .all()
    )
    # Site isn't a stored summary field - a worker can be at a different
    # site each day - so this picks their single MOST RECENT site in
    # the cycle (optionally as of a given date), not a list of every
    # site they were ever at.
    query = db.query(models.DailyRow.emp_no, models.DailyRow.site, models.DailyRow.full_date).filter(
        models.DailyRow.month_year == month_year, models.DailyRow.site != ""
    )
    if as_of:
        try:
            as_of_date = date.fromisoformat(as_of)
            query = query.filter(models.DailyRow.full_date <= as_of_date)
        except ValueError:
            pass
    latest_site_by_emp = {}
    for emp_no, site, full_date in query.all():
        if not site:
            continue
        current = latest_site_by_emp.get(emp_no)
        if current is None or full_date > current[1]:
            latest_site_by_emp[emp_no] = (site, full_date)

    out = []
    for s in summaries:
        item = schemas.EmployeeSummaryOut.from_orm(s)
        latest = latest_site_by_emp.get(s.emp_no)
        item.sites = latest[0] if latest else ""
        out.append(item)
    return out


@app.get("/summaries/{month_year}/by-site")
def summaries_by_site(month_year: str, date_from: str = None, date_to: str = None,
                       db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    """
    Site project cost for the cycle, based on actual attendance - reuses
    reports.site_cost_center() directly, the same logic the desktop app
    uses. Each worker's cost per day at a site is their own daily rate
    (total_salary / 30) plus OT/BH at their own hourly rate, summed by
    site - so a worker who was at two sites contributes only their
    actual days at each, never their full salary twice. With no date
    range, uses every date on file for the cycle; with one, costs only
    that exact window.
    """
    daily_rows = db.query(models.DailyRow).filter(models.DailyRow.month_year == month_year).all()
    summaries2 = db.query(models.EmployeeSummary).filter(models.EmployeeSummary.month_year == month_year).all()
    filters = {}
    if date_from:
        filters["date_from"] = datetime.strptime(date_from, "%Y-%m-%d").date()
    if date_to:
        filters["date_to"] = datetime.strptime(date_to, "%Y-%m-%d").date()
    result = rp.site_cost_center(daily_rows, summaries2, filters)
    return {"title": result.title, "note": result.note,
            "columns": [{"key": k, "label": label} for k, label in result.columns],
            "rows": result.rows, "totals": result.totals}


BUILDER_MEASURE_HINTS = {
    "worker_count": "How many distinct workers were at this group at least once - each worker only counts once, no matter how many days.",
    "record_count": "Total worker-days combined - 5 workers present 3 days each = 15 man-days.",
    "final_salary_cost": "Each worker's own daily rate, apportioned across every paid day in this group's window.",
    "ot_amount": "Each row's OT hours valued at that worker's own hourly rate (their monthly salary / 30 / 8).",
    "bh_amount": "Each row's BH hours valued at that worker's own hourly rate (their monthly salary / 30 / 8).",
}


@app.get("/reports/builder-catalog")
def builder_catalog(user: models.User = Depends(auth.get_current_user)):
    """
    What's available to pick from in the Report Builder, for both data
    sources - dimensions (things to group by / show as labels, never
    summed) and measures (things summed per group). Site is just one
    dimension among several, same as the desktop app - not a separate
    mode.
    """
    def with_hints(d):
        return [{"key": k, "label": v, "hint": BUILDER_MEASURE_HINTS.get(k)} for k, v in d.items()]

    return {
        "summary": {
            "dimensions": [{"key": k, "label": v} for k, v in rp.BUILDER_SUMMARY_DIMENSIONS.items()],
            "measures": with_hints(rp.BUILDER_SUMMARY_MEASURES),
        },
        "daily": {
            "dimensions": [{"key": k, "label": v} for k, v in rp.BUILDER_DAILY_DIMENSIONS.items()],
            "measures": with_hints(rp.BUILDER_DAILY_MEASURES),
        },
    }


def _report_source_rows(db: Session, month_year: str, date_from: str, date_to: str):
    """
    Picks the rows a report runs over.

    When a date range is given it is used DIRECTLY against full_date, so
    a report can span several cycles or any arbitrary window - previously
    the query was pinned to a single month_year and the range could only
    narrow within it, making a two-cycle report impossible.

    With no range, it falls back to the whole selected cycle.

    Summaries are per-worker-per-cycle, so for a range they are pulled
    for every cycle the range touches; measures that come from summaries
    (e.g. Final Salary Cost) are apportioned by the daily rows that fall
    inside the window, which is what build_custom_report already does.
    """
    filters = {}
    if date_from or date_to:
        q = db.query(models.DailyRow)
        if date_from:
            d1 = datetime.strptime(date_from, "%Y-%m-%d").date()
            q = q.filter(models.DailyRow.full_date >= d1)
            filters["date_from"] = d1
        if date_to:
            d2 = datetime.strptime(date_to, "%Y-%m-%d").date()
            q = q.filter(models.DailyRow.full_date <= d2)
            filters["date_to"] = d2
        daily_rows = q.all()
        cycles = {r.month_year for r in daily_rows} or {month_year}
        summaries2 = (db.query(models.EmployeeSummary)
                        .filter(models.EmployeeSummary.month_year.in_(cycles)).all())
        return daily_rows, summaries2, filters

    daily_rows = db.query(models.DailyRow).filter(models.DailyRow.month_year == month_year).all()
    summaries2 = db.query(models.EmployeeSummary).filter(models.EmployeeSummary.month_year == month_year).all()
    return daily_rows, summaries2, filters


@app.get("/reports/custom")
def custom_report(month_year: str, data_source: str = "daily", dimensions: str = "", measures: str = "",
                   date_from: str = None, date_to: str = None,
                   db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    """
    The Report Builder's own aggregation engine (reports.build_custom_report,
    the same one the desktop app used) - groups by whichever dimensions
    were picked and sums whichever measures were picked. No dimensions
    picked means one overall row; picking 'site' groups by site;
    picking 'emp_no'+'name' groups per worker - grouping is just a
    consequence of what's checked, not a separate toggle.

    data_source matters for accuracy: 'daily' uses each attendance row's
    OWN actual site/date/engineer (correct for a worker who was at
    different sites on different days). 'summary' is one row per worker
    per cycle, so a dimension like 'site' can only show that worker's
    single MOST FREQUENT site for the whole cycle - fine for a worker
    who stayed at one site, misleading for one who moved around, which
    is why 'daily' is the default here.
    """
    dims = [d for d in dimensions.split(",") if d]
    meas = [m for m in measures.split(",") if m]
    daily_rows, summaries2, filters = _report_source_rows(db, month_year, date_from, date_to)
    source = data_source if data_source in ("daily", "summary") else "daily"
    result = rp.build_custom_report(source, dims, meas, filters, daily_rows, summaries2)
    return {"title": result.title, "note": result.note,
            "columns": [{"key": k, "label": label} for k, label in result.columns],
            "rows": result.rows, "totals": result.totals}


@app.get("/export/{month_year}/custom-report")
def export_custom_report(month_year: str, token: str, data_source: str = "daily",
                          dimensions: str = "", measures: str = "",
                          date_from: str = None, date_to: str = None, format: str = "excel",
                          db: Session = Depends(get_db)):
    user = auth.get_download_user_from_token(token, db)
    dims = [d for d in dimensions.split(",") if d]
    meas = [m for m in measures.split(",") if m]
    daily_rows, summaries2, filters = _report_source_rows(db, month_year, date_from, date_to)
    source = data_source if data_source in ("daily", "summary") else "daily"
    result = rp.build_custom_report(source, dims, meas, filters, daily_rows, summaries2)
    result_dict = {"columns": [{"key": k, "label": label} for k, label in result.columns],
                    "rows": result.rows, "totals": result.totals}
    if not result.columns:
        raise HTTPException(status_code=400, detail="No columns selected.")

    safe_name = "".join(c if c.isalnum() else "_" for c in month_year)
    if format == "excel":
        buf = export_web.build_generic_result_excel(result_dict, month_year)
        return StreamingResponse(
            buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=Infinia_Report_{safe_name}.xlsx"},
        )
    elif format == "pdf":
        buf = export_web.build_generic_result_pdf(result_dict, month_year)
        return StreamingResponse(
            buf, media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=Infinia_Report_{safe_name}.pdf"},
        )
    raise HTTPException(status_code=400, detail="format must be 'excel' or 'pdf'.")


@app.get("/live-card/{emp_no}/{month_year}")
def get_live_card(emp_no: str, month_year: str, db: Session = Depends(get_db),
                   user: models.User = Depends(auth.get_current_user)):
    """
    Everything needed to render one worker's card on screen: their
    summary totals for the cycle plus every daily row, keyed by actual
    date (not calendar day-of-month) - the cycle runs 26th to 25th
    spanning two calendar months, so day-of-month alone would put late
    dates from the first month out of chronological order against the
    early dates of the second month.
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
    rows_by_date = {r.full_date.isoformat(): schemas.DailyRowOut.from_orm(r) for r in rows if r.full_date}
    if summary:
        summary_out = schemas.EmployeeSummaryOut.from_orm(summary)
    else:
        emp = db.query(models.Employee).filter(models.Employee.emp_no == emp_no).first()
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found.")
        summary_out = None

    try:
        parsed = datetime.strptime(f"25 {month_year}", "%d %B %Y").date()
        cycle_start, cycle_end, _ = pcyc.cycle_bounds_for(parsed)
    except ValueError:
        cycle_start, cycle_end = None, None

    return {
        "emp_no": emp_no, "month_year": month_year,
        "summary": summary_out, "days": rows_by_date,
        "cycle_start": cycle_start.isoformat() if cycle_start else None,
        "cycle_end": cycle_end.isoformat() if cycle_end else None,
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
    site_query = db.query(models.DailyRow.emp_no, models.DailyRow.site, models.DailyRow.full_date).filter(
        models.DailyRow.month_year == month_year, models.DailyRow.site != ""
    )
    latest_site_by_emp = {}
    for emp_no, site, full_date in site_query.all():
        if not site:
            continue
        current = latest_site_by_emp.get(emp_no)
        if current is None or full_date > current[1]:
            latest_site_by_emp[emp_no] = (site, full_date)
    items = []
    for s in summaries:
        item = schemas.EmployeeSummaryOut.from_orm(s)
        latest = latest_site_by_emp.get(s.emp_no)
        item.sites = latest[0] if latest else ""
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


def _add_missing_columns():
    """Lightweight migration: ALTER TABLE ADD COLUMN for anything the
    models declare but the live table doesn't have yet."""
    from sqlalchemy import inspect, text
    type_sql = {"VARCHAR": "VARCHAR", "FLOAT": "DOUBLE PRECISION", "DATE": "DATE",
                "INTEGER": "INTEGER", "BOOLEAN": "BOOLEAN", "TEXT": "TEXT"}
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                t = type_sql.get(str(col.type).split("(")[0].upper())
                if not t:
                    continue
                try:
                    conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {t}'))
                    print(f"Added column {table.name}.{col.name}")
                except Exception as e:
                    print(f"Could not add {table.name}.{col.name}: {e}")


AUTO_BACKUP_KEEP_DAYS = 40

def maybe_create_auto_backup(db: Session):
    """
    Creates one 'auto' backup per calendar DAY, then prunes automatic
    backups down to the most recent AUTO_BACKUP_KEEP_DAYS - a rolling
    40-day window where day 41 replaces day 1.

    Runs on login rather than a cron job: this app has no scheduler
    process of its own, and a backup is only useful if the data has
    actually been touched, which requires someone to be signed in
    anyway. If nobody logs in on a given day there is nothing new to
    snapshot, so no backup is the correct outcome, not a missed one.

    Manual backups are never pruned - only the automatic ones - so a
    snapshot someone deliberately took before a risky change is never
    silently deleted out from under them.
    """
    today = date.today()
    existing = (
        db.query(models.Backup)
        .filter(models.Backup.trigger == "auto",
                func.date(models.Backup.created_at) == today)
        .first()
    )
    if not existing:
        data = build_backup_data(db)
        db.add(models.Backup(created_by=None, trigger="auto", data=json.dumps(data, default=str)))
        db.commit()

    # Prune: keep only the newest N automatic backups.
    old_auto = (
        db.query(models.Backup)
        .filter(models.Backup.trigger == "auto")
        .order_by(models.Backup.created_at.desc())
        .offset(AUTO_BACKUP_KEEP_DAYS)
        .all()
    )
    if old_auto:
        for b in old_auto:
            db.delete(b)
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
        .limit(120)
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
def restore_backup(backup_id: int, db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
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


@app.delete("/backup/{backup_id}")
def delete_backup(backup_id: int, db: Session = Depends(get_db),
                   user: models.User = Depends(auth.get_current_user)):
    """
    Remove a single backup. Useful for clearing out snapshots taken
    before a known-bad state, so nobody restores one by mistake later -
    a real risk, since a backup's date alone doesn't say whether the
    data inside it was correct.
    """
    b = db.query(models.Backup).filter(models.Backup.id == backup_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Backup not found")
    when = b.created_at.isoformat() if b.created_at else str(backup_id)
    db.delete(b)
    db.commit()
    log_action(db, user.id, "delete_backup", f"#{backup_id} ({when})")
    return {"ok": True, "deleted": backup_id}


@app.get("/health")
def health_check():
    return {"status": "ok"}


# ---------------------------------------------------------------------
# STORE / INVENTORY
# ---------------------------------------------------------------------
CENTRAL = ""   # empty location string means the central store


def _stock_map(db: Session, upto: date = None):
    """
    Current quantity of every item at every location, derived from the
    movement ledger rather than stored - so a balance can never drift
    away from the history that produced it.

    Returns {(item_id, location): qty}. 'upto' gives the position as at
    a date, which is what makes stock-as-at reporting possible.
    """
    q = db.query(models.StoreMovement)
    if upto:
        q = q.filter(models.StoreMovement.moved_on <= upto)
    stock = {}
    for m in q.all():
        if m.kind == "in":
            stock[(m.item_id, m.location)] = stock.get((m.item_id, m.location), 0) + m.qty
        elif m.kind == "adjust":
            stock[(m.item_id, m.location)] = stock.get((m.item_id, m.location), 0) + m.qty
        elif m.kind in ("out", "return", "transfer"):
            stock[(m.item_id, m.from_location)] = stock.get((m.item_id, m.from_location), 0) - m.qty
            stock[(m.item_id, m.location)] = stock.get((m.item_id, m.location), 0) + m.qty
    return stock


@app.get("/store/items", response_model=list[schemas.StoreItemOut])
def list_store_items(active_only: bool = True, db: Session = Depends(get_db),
                      user: models.User = Depends(auth.get_current_user)):
    q = db.query(models.StoreItem)
    if active_only:
        q = q.filter(models.StoreItem.active == True)  # noqa: E712
    return q.order_by(models.StoreItem.code).all()


@app.post("/store/items", response_model=schemas.StoreItemOut)
def upsert_store_item(payload: schemas.StoreItemIn, db: Session = Depends(get_db),
                       user: models.User = Depends(auth.get_current_user)):
    # Validate on the server, not just in the browser - a blank code or
    # name creates an item that can't be identified in any report.
    code = (payload.code or "").strip()
    name = (payload.name or "").strip()
    if not code:
        # Auto-number new items ITM1, ITM2... The store keeper shouldn't
        # have to invent a code; existing items still keep whatever code
        # they were given, and an edit sends the code back unchanged.
        used = {i.code for i in db.query(models.StoreItem).all()}
        n = 1
        while f"ITM{n}" in used:
            n += 1
        code = f"ITM{n}"
    if not name:
        raise HTTPException(status_code=400, detail="Item needs a name.")
    if payload.item_type not in ("consumable", "returnable", "asset", "rental"):
        raise HTTPException(status_code=400, detail="Unknown item type.")
    if payload.reorder_level < 0:
        raise HTTPException(status_code=400, detail="Reorder level can't be negative.")
    payload.code, payload.name = code, name

    existing = db.query(models.StoreItem).filter(models.StoreItem.code == code).first()
    if existing:
        for k, v in payload.dict().items():
            setattr(existing, k, v)
        existing.active = True
    else:
        existing = models.StoreItem(**payload.dict())
        db.add(existing)
    db.commit()
    db.refresh(existing)
    log_action(db, user.id, "store_save_item", f"{payload.code} - {payload.name}")
    return existing


@app.delete("/store/items/{item_id}")
def deactivate_store_item(item_id: int, db: Session = Depends(get_db),
                           user: models.User = Depends(auth.get_current_user)):
    it = db.query(models.StoreItem).filter(models.StoreItem.id == item_id).first()
    if not it:
        raise HTTPException(status_code=404, detail="Item not found")
    # Deactivate rather than delete - its movement history must survive.
    it.active = False
    db.commit()
    log_action(db, user.id, "store_remove_item", it.code)
    return {"ok": True}


@app.get("/store/stock")
def store_stock(location: str = None, db: Session = Depends(get_db),
                 user: models.User = Depends(auth.get_current_user)):
    """
    Stock on hand. Without a location, one row per item showing the
    central-store quantity, how much is out at sites, and the total -
    plus a low flag when it has fallen to or below its reorder level.
    """
    items = db.query(models.StoreItem).filter(models.StoreItem.active == True).all()  # noqa: E712
    stock = _stock_map(db)
    rows = []
    for it in items:
        at_central = stock.get((it.id, CENTRAL), 0)
        out_total = sum(v for (iid, loc), v in stock.items() if iid == it.id and loc != CENTRAL)
        by_site = {loc: v for (iid, loc), v in stock.items() if iid == it.id and loc != CENTRAL and v}
        if location is not None:
            qty = stock.get((it.id, location), 0)
            rows.append({"item_id": it.id, "code": it.code, "name": it.name,
                          "category": it.category, "unit": it.unit, "item_type": it.item_type,
                          "qty": round(qty, 2), "reorder_level": it.reorder_level,
                          "low": qty <= it.reorder_level and it.reorder_level > 0})
        else:
            rows.append({"item_id": it.id, "code": it.code, "name": it.name,
                          "category": it.category, "unit": it.unit, "item_type": it.item_type,
                          "central": round(at_central, 2), "out_at_sites": round(out_total, 2),
                          "total": round(at_central + out_total, 2),
                          "by_site": {k: round(v, 2) for k, v in by_site.items()},
                          "reorder_level": it.reorder_level,
                          "low": at_central <= it.reorder_level and it.reorder_level > 0})
    return rows


@app.get("/store/movements", response_model=list[schemas.StoreMovementOut])
def list_store_movements(item_id: int = None, location: str = None, kind: str = None,
                          date_from: str = None, date_to: str = None, limit: int = 500,
                          db: Session = Depends(get_db),
                          user: models.User = Depends(auth.get_current_user)):
    q = db.query(models.StoreMovement)
    if item_id:
        q = q.filter(models.StoreMovement.item_id == item_id)
    if kind:
        q = q.filter(models.StoreMovement.kind == kind)
    if location:
        q = q.filter(or_(models.StoreMovement.location == location,
                          models.StoreMovement.from_location == location))
    if date_from:
        q = q.filter(models.StoreMovement.moved_on >= datetime.strptime(date_from, "%Y-%m-%d").date())
    if date_to:
        q = q.filter(models.StoreMovement.moved_on <= datetime.strptime(date_to, "%Y-%m-%d").date())
    rows = q.order_by(models.StoreMovement.moved_on.desc(), models.StoreMovement.id.desc()).limit(limit).all()
    out = []
    for m in rows:
        d = schemas.StoreMovementOut.model_validate(m).model_dump()
        d["item_code"] = m.item.code if m.item else ""
        d["item_name"] = m.item.name if m.item else ""
        d["unit"] = m.item.unit if m.item else ""
        out.append(d)
    return out


@app.post("/store/movements", response_model=schemas.StoreMovementOut)
def add_store_movement(payload: schemas.StoreMovementIn, db: Session = Depends(get_db),
                        user: models.User = Depends(auth.get_current_user)):
    item = db.query(models.StoreItem).filter(models.StoreItem.id == payload.item_id).first()
    if not item:
        raise HTTPException(status_code=400, detail="Item not found.")
    if payload.kind not in ("in", "out", "return", "adjust", "transfer"):
        raise HTTPException(status_code=400, detail="Unknown movement type.")
    if payload.qty <= 0 and payload.kind != "adjust":
        raise HTTPException(status_code=400, detail="Quantity must be more than zero.")
    if payload.moved_on > date.today():
        raise HTTPException(status_code=400, detail="Date is in the future.")

    # Don't allow issuing more than is actually held - a negative balance
    # means the ledger no longer describes anything real.
    if payload.kind in ("out", "return", "transfer"):
        have = _stock_map(db).get((item.id, payload.from_location), 0)
        if payload.qty > have + 1e-9:
            where = payload.from_location or "the central store"
            raise HTTPException(status_code=400,
                detail=f"Only {round(have, 2)} {item.unit} of {item.name} available at {where}.")

    m = models.StoreMovement(**payload.dict(), created_by=user.id)
    db.add(m)
    db.commit()
    db.refresh(m)
    log_action(db, user.id, "store_movement",
               f"{payload.kind} {payload.qty} {item.unit} {item.code}")
    d = schemas.StoreMovementOut.model_validate(m).model_dump()
    d["item_code"], d["item_name"], d["unit"] = item.code, item.name, item.unit
    return d


@app.delete("/store/movements/{movement_id}")
def delete_store_movement(movement_id: int, db: Session = Depends(get_db),
                           user: models.User = Depends(auth.get_current_user)):
    m = db.query(models.StoreMovement).filter(models.StoreMovement.id == movement_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Movement not found")
    db.delete(m)
    db.commit()
    log_action(db, user.id, "store_delete_movement", f"#{movement_id}")
    return {"ok": True}


@app.get("/store/report")
def store_report(kind: str = "stock", date_from: str = None, date_to: str = None,
                  db: Session = Depends(get_db),
                  user: models.User = Depends(auth.get_current_user)):
    # NOTE: also called directly by the export endpoint, which passes
    # user=None after verifying a download token instead.
    """
    kind='stock'     - current stock, central vs out at sites
        ='low'       - items at or below reorder level
        ='by_site'   - what each site currently holds
        ='purchases' - what was received, with cost, over a period
        ='usage'     - what was issued out, per item, over a period
        ='returnable'- returnable items currently out, and where
    """
    d1 = datetime.strptime(date_from, "%Y-%m-%d").date() if date_from else None
    d2 = datetime.strptime(date_to, "%Y-%m-%d").date() if date_to else None
    items = {i.id: i for i in db.query(models.StoreItem).all()}
    stock = _stock_map(db)

    def moves(kinds):
        q = db.query(models.StoreMovement).filter(models.StoreMovement.kind.in_(kinds))
        if d1: q = q.filter(models.StoreMovement.moved_on >= d1)
        if d2: q = q.filter(models.StoreMovement.moved_on <= d2)
        return q.all()

    if kind == "low":
        rows = []
        for i in items.values():
            if not i.active or not i.reorder_level: continue
            have = stock.get((i.id, CENTRAL), 0)
            if have <= i.reorder_level:
                rows.append({"code": i.code, "name": i.name, "unit": i.unit,
                              "in_store": round(have, 2), "reorder_level": i.reorder_level,
                              "shortfall": round(i.reorder_level - have, 2)})
        return {"title": "Items to reorder", "rows": sorted(rows, key=lambda r: -r["shortfall"])}

    if kind == "by_site":
        rows = []
        for (iid, loc), qty in stock.items():
            if loc == CENTRAL or not qty or iid not in items: continue
            i = items[iid]
            rows.append({"site": loc, "code": i.code, "name": i.name,
                          "unit": i.unit, "qty": round(qty, 2), "item_type": i.item_type})
        return {"title": "Stock held at sites", "rows": sorted(rows, key=lambda r: (r["site"], r["code"]))}

    if kind == "purchases":
        agg = {}
        for m in moves(["in"]):
            i = items.get(m.item_id)
            if not i: continue
            a = agg.setdefault(i.id, {"code": i.code, "name": i.name, "unit": i.unit,
                                       "qty": 0, "value": 0, "suppliers": set()})
            a["qty"] += m.qty
            a["value"] += m.qty * (m.unit_cost or 0)
            if m.supplier: a["suppliers"].add(m.supplier)
        rows = [{**v, "qty": round(v["qty"], 2), "value": round(v["value"], 2),
                  "suppliers": ", ".join(sorted(v["suppliers"]))} for v in agg.values()]
        return {"title": "Purchases received", "rows": sorted(rows, key=lambda r: -r["value"]),
                "total_value": round(sum(r["value"] for r in rows), 2)}

    if kind == "usage":
        agg = {}
        for m in moves(["out"]):
            i = items.get(m.item_id)
            if not i: continue
            key = (i.id, m.location)
            a = agg.setdefault(key, {"code": i.code, "name": i.name, "unit": i.unit,
                                      "site": m.location, "qty": 0})
            a["qty"] += m.qty
        rows = [{**v, "qty": round(v["qty"], 2)} for v in agg.values()]
        return {"title": "Materials issued", "rows": sorted(rows, key=lambda r: (r["site"], r["code"]))}

    if kind == "returnable":
        rows = []
        for (iid, loc), qty in stock.items():
            i = items.get(iid)
            if not i or i.item_type != "returnable" or loc == CENTRAL or qty <= 0: continue
            last = (db.query(models.StoreMovement)
                      .filter(models.StoreMovement.item_id == iid,
                               models.StoreMovement.location == loc,
                               models.StoreMovement.kind == "out")
                      .order_by(models.StoreMovement.moved_on.desc()).first())
            rows.append({"code": i.code, "name": i.name, "unit": i.unit, "site": loc,
                          "qty": round(qty, 2),
                          "incharge": last.incharge if last else "",
                          "since": last.moved_on.isoformat() if last else ""})
        return {"title": "Returnable items still out", "rows": sorted(rows, key=lambda r: r["site"])}

    if kind == "rentals":
        # Hired-in equipment: where it is, what it costs, and whether it
        # is overdue back to the supplier.
        today = date.today()
        rows = []
        for i in items.values():
            if not i.active or i.item_type != "rental": continue
            at = {loc: q for (iid, loc), q in stock.items() if iid == i.id and q}
            where = ", ".join(f"{loc or 'store'}: {round(q,2)}" for loc, q in sorted(at.items())) or "-"
            days = (today - i.rental_start).days if i.rental_start else None
            est = round(days * (i.rental_rate or 0), 2) if (days is not None and i.rental_period == "day") else None
            rows.append({"code": i.code, "name": i.name, "supplier": i.rental_supplier,
                          "rate": i.rental_rate, "period": i.rental_period,
                          "start": i.rental_start.isoformat() if i.rental_start else "",
                          "due": i.rental_due.isoformat() if i.rental_due else "",
                          "days_on_hire": days, "est_cost": est, "where": where,
                          "overdue": bool(i.rental_due and i.rental_due < today)})
        return {"title": "Rented equipment", "rows": sorted(rows, key=lambda r: (not r["overdue"], r["due"] or ""))}

    if kind == "assets":
        rows = []
        for i in items.values():
            if not i.active or i.item_type not in ("asset", "rental"): continue
            at = {loc: q for (iid, loc), q in stock.items() if iid == i.id and q}
            rows.append({"code": i.code, "name": i.name, "item_type": i.item_type,
                          "unit": i.unit, "total": round(sum(at.values()), 2),
                          "where": ", ".join(f"{loc or 'store'}: {round(q,2)}" for loc, q in sorted(at.items())) or "-"})
        return {"title": "Assets and equipment", "rows": sorted(rows, key=lambda r: r["code"])}

    # default: full stock position
    rows = []
    for i in items.values():
        if not i.active: continue
        c = stock.get((i.id, CENTRAL), 0)
        o = sum(v for (iid, loc), v in stock.items() if iid == i.id and loc != CENTRAL)
        rows.append({"code": i.code, "name": i.name, "category": i.category, "unit": i.unit,
                      "item_type": i.item_type, "in_store": round(c, 2),
                      "at_sites": round(o, 2), "total": round(c + o, 2),
                      "low": bool(i.reorder_level and c <= i.reorder_level)})
    return {"title": "Current stock", "rows": sorted(rows, key=lambda r: r["code"])}


# ---------------------------------------------------------------------
# MATERIAL REQUESTS (store keeper -> office)
# ---------------------------------------------------------------------
def _next_mr_ref(db: Session) -> str:
    last = db.query(models.MaterialRequest).order_by(models.MaterialRequest.id.desc()).first()
    n = (last.id + 1) if last else 1
    return f"MR-{n:04d}"


def _mr_out(mr: models.MaterialRequest) -> dict:
    d = schemas.MaterialRequestOut.model_validate(mr).model_dump()
    for i, ln in enumerate(mr.lines):
        d["lines"][i]["item_code"] = ln.item.code if ln.item else ""
        d["lines"][i]["item_name"] = ln.item.name if ln.item else (ln.description or "")
    return d


@app.get("/store/requests")
def list_material_requests(status: str = None, site: str = None,
                            date_from: str = None, date_to: str = None,
                            db: Session = Depends(get_db),
                            user: models.User = Depends(auth.get_current_user)):
    q = db.query(models.MaterialRequest)
    if status:
        q = q.filter(models.MaterialRequest.status == status)
    if site:
        q = q.filter(models.MaterialRequest.site == site)
    if date_from:
        q = q.filter(models.MaterialRequest.requested_on >= datetime.strptime(date_from, "%Y-%m-%d").date())
    if date_to:
        q = q.filter(models.MaterialRequest.requested_on <= datetime.strptime(date_to, "%Y-%m-%d").date())
    return [_mr_out(m) for m in q.order_by(models.MaterialRequest.id.desc()).all()]


@app.post("/store/requests")
def create_material_request(payload: schemas.MaterialRequestIn, db: Session = Depends(get_db),
                             user: models.User = Depends(auth.get_current_user)):
    lines = [l for l in payload.lines if l.qty_requested and l.qty_requested > 0]
    if not lines:
        raise HTTPException(status_code=400, detail="Add at least one material with a quantity.")
    for l in lines:
        if not l.item_id and not (l.description or "").strip():
            raise HTTPException(status_code=400, detail="Every line needs an item or a description.")
    mr = models.MaterialRequest(
        ref=_next_mr_ref(db), site=payload.site, requested_by=payload.requested_by,
        needed_by=payload.needed_by, urgency=payload.urgency, notes=payload.notes,
        requested_on=payload.requested_on or date.today(), created_by=user.id,
    )
    db.add(mr)
    db.flush()
    for l in lines:
        unit = l.unit
        if l.item_id:
            it = db.query(models.StoreItem).filter(models.StoreItem.id == l.item_id).first()
            if it:
                unit = it.unit
        db.add(models.MaterialRequestLine(request_id=mr.id, item_id=l.item_id,
                                           description=l.description, qty_requested=l.qty_requested,
                                           qty_approved=l.qty_approved or 0, unit=unit,
                                           est_cost=l.est_cost or 0, notes=l.notes))
    db.commit()
    db.refresh(mr)
    log_action(db, user.id, "material_request", f"{mr.ref} - {len(lines)} item(s)")
    return _mr_out(mr)


@app.post("/store/requests/{req_id}/status")
def set_material_request_status(req_id: int, payload: schemas.MaterialRequestStatusIn,
                                 db: Session = Depends(get_db),
                                 user: models.User = Depends(auth.get_current_user)):
    mr = db.query(models.MaterialRequest).filter(models.MaterialRequest.id == req_id).first()
    if not mr:
        raise HTTPException(status_code=404, detail="Request not found")
    allowed = ("pending", "approved", "rejected", "partial", "received", "closed")
    if payload.status not in allowed:
        raise HTTPException(status_code=400, detail=f"Status must be one of: {', '.join(allowed)}")
    mr.status = payload.status
    if payload.office_remark:
        mr.office_remark = payload.office_remark
    mr.closed_on = date.today() if payload.status in ("received", "closed", "rejected") else None
    db.commit()
    log_action(db, user.id, "material_request_status", f"{mr.ref} -> {payload.status}")
    return {"ok": True, "status": mr.status}


@app.delete("/store/requests/{req_id}")
def delete_material_request(req_id: int, db: Session = Depends(get_db),
                             user: models.User = Depends(auth.get_current_user)):
    mr = db.query(models.MaterialRequest).filter(models.MaterialRequest.id == req_id).first()
    if not mr:
        raise HTTPException(status_code=404, detail="Request not found")
    ref = mr.ref
    db.delete(mr)
    db.commit()
    log_action(db, user.id, "material_request_delete", ref)
    return {"ok": True}


@app.post("/store/requests/{req_id}/receive")
def receive_against_request(req_id: int, line_id: int, qty: float, supplier: str = "",
                             unit_cost: float = 0.0, reference: str = "",
                             db: Session = Depends(get_db),
                             user: models.User = Depends(auth.get_current_user)):
    """
    Record a delivery against one line of a request. This both files a
    normal 'in' stock movement AND advances the request, so outstanding
    quantities stay honest instead of the two drifting apart.
    """
    mr = db.query(models.MaterialRequest).filter(models.MaterialRequest.id == req_id).first()
    if not mr:
        raise HTTPException(status_code=404, detail="Request not found")
    line = db.query(models.MaterialRequestLine).filter(
        models.MaterialRequestLine.id == line_id,
        models.MaterialRequestLine.request_id == req_id).first()
    if not line:
        raise HTTPException(status_code=404, detail="Request line not found")
    if qty <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be more than zero.")
    outstanding = line.qty_requested - (line.qty_received or 0)
    if qty > outstanding + 1e-9:
        raise HTTPException(status_code=400,
            detail=f"Only {round(outstanding, 2)} {line.unit} still outstanding on this line.")
    if not line.item_id:
        raise HTTPException(status_code=400,
            detail="This line isn't linked to a store item, so it can't be received into stock. "
                   "Create the item first, then edit the request.")

    db.add(models.StoreMovement(item_id=line.item_id, kind="in", qty=qty, location="",
                                 supplier=supplier, unit_cost=unit_cost,
                                 reference=reference or mr.ref, moved_on=date.today(),
                                 notes=f"Against {mr.ref}", created_by=user.id))
    line.qty_received = (line.qty_received or 0) + qty
    all_done = all((l.qty_received or 0) >= l.qty_requested - 1e-9 for l in mr.lines)
    any_done = any((l.qty_received or 0) > 0 for l in mr.lines)
    mr.status = "received" if all_done else ("partial" if any_done else mr.status)
    if all_done:
        mr.closed_on = date.today()
    db.commit()
    log_action(db, user.id, "material_request_receive", f"{mr.ref} line {line_id}: {qty}")
    return {"ok": True, "status": mr.status, "qty_received": line.qty_received}


@app.get("/store/requests/report")
def material_request_report(kind: str = "open", db: Session = Depends(get_db),
                            user: models.User = Depends(auth.get_current_user)):
    # Also called directly by the export endpoint with user=None.
    """kind='open' | 'overdue' | 'outstanding' | 'history'"""
    today = date.today()
    reqs = db.query(models.MaterialRequest).order_by(models.MaterialRequest.id.desc()).all()

    if kind == "overdue":
        rows = [{"ref": m.ref, "site": m.site, "requested_on": m.requested_on.isoformat(),
                  "needed_by": m.needed_by.isoformat() if m.needed_by else "",
                  "days_late": (today - m.needed_by).days if m.needed_by else 0,
                  "status": m.status, "urgency": m.urgency, "items": len(m.lines)}
                 for m in reqs
                 if m.needed_by and m.needed_by < today and m.status not in ("received", "closed", "rejected")]
        return {"title": "Overdue material requests", "rows": sorted(rows, key=lambda r: -r["days_late"])}

    if kind == "outstanding":
        rows = []
        for m in reqs:
            if m.status in ("received", "closed", "rejected"):
                continue
            for l in m.lines:
                out = (l.qty_requested or 0) - (l.qty_received or 0)
                if out <= 0:
                    continue
                rows.append({"ref": m.ref, "site": m.site, "status": m.status,
                              "item": (l.item.code + " - " + l.item.name) if l.item else l.description,
                              "unit": l.unit, "requested": l.qty_requested,
                              "received": l.qty_received or 0, "outstanding": round(out, 2),
                              "needed_by": m.needed_by.isoformat() if m.needed_by else ""})
        return {"title": "Outstanding materials", "rows": rows}

    if kind == "history":
        rows = [{"ref": m.ref, "site": m.site, "requested_on": m.requested_on.isoformat(),
                  "requested_by": m.requested_by, "urgency": m.urgency, "status": m.status,
                  "items": len(m.lines),
                  # No estimated value: the store keeper doesn't price a
                  # request, the office does when it orders.
                  "closed_on": m.closed_on.isoformat() if m.closed_on else ""}
                for m in reqs]
        return {"title": "Material request history", "rows": rows}

    rows = [{"ref": m.ref, "site": m.site, "requested_on": m.requested_on.isoformat(),
              "needed_by": m.needed_by.isoformat() if m.needed_by else "",
              "urgency": m.urgency, "status": m.status, "items": len(m.lines),
              "requested_by": m.requested_by}
            for m in reqs if m.status in ("pending", "approved", "partial")]
    return {"title": "Open material requests", "rows": rows}


@app.get("/export/store/report")
def export_store_report(kind: str = "stock", format: str = "excel",
                         date_from: str = None, date_to: str = None,
                         token: str = None, db: Session = Depends(get_db)):
    auth.get_download_user_from_token(token, db)
    # Material-request reports live under a different builder to the
    # stock ones, but both export through the same formatter.
    if kind.startswith("mr_"):
        data = material_request_report(kind=kind[3:], db=db, user=None)
    else:
        data = store_report(kind=kind, date_from=date_from, date_to=date_to, db=db, user=None)
    sub = ""
    if date_from or date_to:
        sub = f"{date_from or 'start'} to {date_to or 'today'}"
    else:
        sub = f"As at {date.today().isoformat()}"
    if format == "pdf":
        buf = export_web.build_store_report_pdf(data["title"], data["rows"], sub)
        media, ext = "application/pdf", "pdf"
    else:
        buf = export_web.build_store_report_excel(data["title"], data["rows"], sub)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ext = "xlsx"
    name = f"{kind}_{date.today().isoformat()}.{ext}"
    return StreamingResponse(buf, media_type=media,
                              headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/export/store/request/{req_id}")
def export_material_request(req_id: int, token: str = None, db: Session = Depends(get_db)):
    auth.get_download_user_from_token(token, db)
    mr = db.query(models.MaterialRequest).filter(models.MaterialRequest.id == req_id).first()
    if not mr:
        raise HTTPException(status_code=404, detail="Request not found")
    buf = export_web.build_material_request_pdf(_mr_out(mr))
    return StreamingResponse(buf, media_type="application/pdf",
                              headers={"Content-Disposition": f'attachment; filename="{mr.ref}.pdf"'})

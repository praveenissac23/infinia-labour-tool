"""
Infinia Labour Tool - Web Backend
====================================
FastAPI application. Reuses the desktop app's own calculation and
validation logic (data_engine.py, daily_attendance.py, payroll_cycle.py)
directly - the only thing that changed is the storage layer, from
pickled sessions/JSON files to a real multi-user database.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Optional
import os
import re
import io
import json
from urllib.parse import quote

import base64, gzip
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import StreamingResponse, HTMLResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, func
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from database import get_db, engine, Base, SessionLocal
import models
import mailer
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
        _retire_staff_role(db)
        _grant_storekeeper_to_existing(db)
        _enforce_terminations(db)
        _recalculate_all_summaries(db)
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


@app.middleware("http")
async def never_cache_api(request, call_next):
    """Every answer from this API is live data and must be fetched fresh.

    With no Cache-Control header a browser is free to answer a repeat
    GET from its own cache, and Chromium does: the notification poll
    was firing every twenty seconds and reaching the server once,
    which is how a new request took five minutes to be seen. Stock,
    requests and the rest were exposed to the same thing.

    Downloads (PDF, Excel, zip) are left alone - they are one-shot and
    the browser has no reason to cache them either way.
    """
    response = await call_next(request)
    if not request.url.path.startswith("/export/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# ---------------------------------------------------------------------
# AUTH
# ---------------------------------------------------------------------
# ---------------------------------------------------------------------
# PER-USER SCREEN PERMISSIONS
# ---------------------------------------------------------------------
ALL_SCREENS = ["dashboard", "attendance", "masterdata", "reports", "combine",
               "adjustments", "livecard", "store", "requests", "approvals",
               "errorcheck", "settings", "activity",
               # Not a screen but a right: who may record a receipt, an
               # issue, a return or a write-off. It was decided by role,
               # which made the store keeper's own job depend on which
               # role his login happened to carry.
               "storekeeper"]

# What a role can see when no explicit permissions have been set, so
# existing accounts keep working exactly as before this was added.
def _dubai_today() -> date:
    """Today in Dubai, whatever clock the server keeps.

    The VPS runs on UTC, four hours behind. Between midnight and four in
    the morning Dubai time, date.today() on the server is still
    yesterday - so a foreman marking the day's attendance early would be
    told it is in the future, and a check for missing days would not
    yet count today. Every 'what day is it' in this file goes through
    here.
    """
    return (datetime.now(timezone.utc) + timedelta(hours=4)).date()


# Three roles, which is what the company actually has. "staff" was a
# catch-all that gave nearly everything away by default; anyone who
# needs an unusual mix gets it through their own permissions instead.
ROLE_DEFAULTS = {
    "admin": ALL_SCREENS,
    # The office approves and orders; a site raises requests and does
    # not approve its own.
    # Settings is on every role: it is where anyone changes their own
    # password and takes a backup. What sits inside it - staff logins,
    # restoring, clearing - is guarded on its own, not by hiding the
    # screen.
    # The office keeps the store, so it records stock in and out by
    # default - exactly what it could do before this became a permission.
    "office": ["dashboard", "store", "requests", "approvals", "reports", "errorcheck",
               "settings", "storekeeper"],
    "site": ["dashboard", "attendance", "store", "requests", "settings"],
}
ROLES = list(ROLE_DEFAULTS)


def _enforce_terminations(db):
    """Make every stored day after a man's leaving date read Terminated.

    The rewrite normally runs when the leaving date is saved. Anyone
    marked terminated before that existed - or by an older version -
    still has working days sitting after his last day, quietly being
    paid. Running this at startup settles them all, so a restart is
    enough and nobody has to re-save each leaver by hand.
    """
    fixed = 0
    for emp in db.query(models.Employee).filter(models.Employee.terminated_on.isnot(None)).all():
        rows = (db.query(models.DailyRow)
                  .filter(models.DailyRow.emp_no == emp.emp_no,
                          models.DailyRow.full_date > emp.terminated_on)
                  .all())
        touched = [r for r in rows if r.am != "Terminated" or r.pm != "Terminated"
                   or (r.site or "") or (r.ot or 0) or (r.bh or 0)]
        for r in touched:
            r.am = r.pm = "Terminated"
            r.site = ""
            r.engineer = ""
            r.ot = 0
            r.bh = 0
        fixed += len(touched)
    if fixed:
        db.commit()
        print(f"Corrected {fixed} day(s) recorded after a worker's leaving date")


def _recalculate_all_summaries(db):
    """Recompute every stored payroll summary from its daily rows.

    Summaries are stored figures, recomputed only when attendance is
    saved or a worker is edited. When the pay rule itself changes - a
    new pay type, a corrected formula - every card would keep showing
    the old arithmetic until someone happened to touch it. Running this
    at startup means a restart alone brings every card, total and
    report into line with the current rule. Deterministic, so running
    it on every restart is harmless; a few seconds for 74 workers."""
    pairs = (db.query(models.EmployeeSummary.emp_no, models.EmployeeSummary.month_year)
               .distinct().all())
    by_no = {e.emp_no: e for e in db.query(models.Employee).all()}
    done = 0
    for emp_no, month_year in pairs:
        emp = by_no.get(emp_no)
        if emp is None:
            continue
        try:
            services.recalculate_summary(db, emp, month_year)
            done += 1
        except Exception as e:
            print(f"Could not recalculate {emp_no} {month_year}: {e}")
    if done:
        db.commit()
        print(f"Recalculated {done} payroll summaries against the current pay rules")


def employed_during(emp, cycle_start, cycle_end):
    """Was this man on the books at any point in that cycle?

    He keeps his card for the cycle he left in - the days he worked
    still have to be paid - and disappears from the next one. Every
    past cycle still shows him, because what happened then did happen.
    """
    t = getattr(emp, "terminated_on", None)
    return t is None or t >= cycle_start


def _grant_storekeeper_to_existing(db):
    """Recording stock in and out used to be decided by role: anyone not
    on a site login could do it. It is a permission now, which is right
    - but a login whose permissions were saved before today has no such
    tick, and would lose a job it has been doing all along.

    So every existing non-site login that may open the store is given
    it, once. A login created afterwards gets it from its role's
    defaults or from whatever an admin ticks.
    """
    flag = db.query(models.Setting).filter(models.Setting.key == "storekeeper_backfilled").first()
    if flag:
        return
    granted = 0
    for u in db.query(models.User).all():
        raw = (u.permissions or "").strip()
        if not raw:
            continue                       # follows its role's defaults already
        perms = [p for p in raw.split(",") if p]
        if "store" in perms and "storekeeper" not in perms and u.role != "site":
            perms.append("storekeeper")
            u.permissions = ",".join(perms)
            granted += 1
    db.add(models.Setting(key="storekeeper_backfilled", value="1"))
    db.commit()
    if granted:
        print(f"Kept stock in/out for {granted} existing login(s)")


def _retire_staff_role(db):
    """Move anyone left on the old catch-all role onto 'office'.

    Their access must not change in the process: a staff account with no
    permissions of its own was relying on the old default, so that list
    is written into their permissions first. Someone who already had
    explicit permissions - the store keeper, for instance - keeps
    exactly those.
    """
    old_default = [s for s in ALL_SCREENS if s != "activity"]
    moved = 0
    for u in db.query(models.User).filter(models.User.role == "staff").all():
        if not (u.permissions or "").strip():
            u.permissions = ",".join(old_default)
        u.role = "office"
        moved += 1
    if moved:
        db.commit()
        print(f"Moved {moved} account(s) off the retired 'staff' role, access unchanged")


def effective_permissions(user: models.User) -> list:
    if user.role == "admin":
        return list(ALL_SCREENS)          # admin always has everything
    raw = (user.permissions or "").strip()
    if raw:
        return [s for s in raw.split(",") if s in ALL_SCREENS]
    # An unrecognised role - an old account, or one from a future version
    # - gets the narrowest access rather than the widest. Failing closed
    # is the only safe direction here.
    return list(ROLE_DEFAULTS.get(user.role, ROLE_DEFAULTS["site"]))


def require_screen(screen: str):
    """
    Dependency that blocks an endpoint unless the user may open the screen
    it belongs to. Hiding a menu item is presentation only - without this
    the endpoint is still reachable by anyone with a login.
    """
    def _check(user: models.User = Depends(auth.get_current_user)):
        if screen not in effective_permissions(user):
            raise HTTPException(status_code=403,
                detail=f"You don't have access to {screen}. Ask an admin to enable it.")
        return user
    return _check


def require_any_screen(*screens):
    """Some data belongs to two jobs at once: suppliers are used by the
    keeper (store screen) receiving deliveries and by the office
    (requests screen) placing orders. Either permission opens the door -
    demanding one specific screen was silently blanking the supplier
    list for whoever happened to hold the other."""
    def _check(user: models.User = Depends(auth.get_current_user)):
        perms = effective_permissions(user)
        if not any(s in perms for s in screens):
            raise HTTPException(status_code=403,
                detail=f"You don't have access to this. Ask an admin to enable {' or '.join(screens)}.")
        return user
    return _check


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
    return schemas.TokenResponse(access_token=token, username=user.username,
                                  role=user.role, full_name=user.full_name)


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
def list_users(db: Session = Depends(get_db),
                user: models.User = Depends(auth.require_admin)):
    """Who can log in, and what each may open, is administration - not
    something a store keeper or site engineer needs to read."""
    return db.query(models.User).order_by(models.User.username).all()


@app.post("/users", response_model=schemas.UserOut)
def create_user(payload: schemas.UserIn, db: Session = Depends(get_db),
                 user: models.User = Depends(auth.require_admin)):
    # Staff can add fellow staff, but only an admin can mint another
    # admin - otherwise any staff login could promote itself (or a new
    # account) to admin, which would make every admin-only restriction
    # meaningless, including the Activity Monitor.
    # office and site are both non-privileged; only an admin can mint
    # another admin, otherwise any login could promote itself.
    if payload.role not in ROLES:
        raise HTTPException(status_code=400, detail="Role must be office, site or admin.")
    if payload.role == "admin" and user.role != "admin":
        raise HTTPException(status_code=403, detail="Only an admin can create an admin account.")
    # A login is typed at a keyboard by somebody who is not the person
    # who made it, so the name is trimmed and lower-cased: "AKHIL " and
    # "akhil" were two different accounts, and a space in the middle is
    # a login nobody can get right twice.
    username = (payload.username or "").strip().lower()
    if not username:
        raise HTTPException(status_code=400, detail="Enter a username.")
    if " " in username:
        raise HTTPException(status_code=400, detail="A username cannot contain spaces.")
    # The change-password screen asks for six characters; making one for
    # somebody else was letting through anything at all, including '123'.
    if len(payload.password or "") < 6:
        raise HTTPException(status_code=400, detail="The password must be at least 6 characters.")
    existing = db.query(models.User).filter(func.lower(models.User.username) == username).first()
    if existing:
        raise HTTPException(status_code=400, detail="That username is already taken.")
    new_user = models.User(
        username=username,
        hashed_password=auth.hash_password(payload.password),
        # Full name is no longer collected when creating a login; fall
        # back to the username so the Activity Monitor and header still
        # have something readable to show.
        full_name=(payload.full_name or "").strip() or username,
        role=payload.role,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    log_action(db, user.id, "create_user", f"{payload.username} ({payload.role})")
    return new_user


@app.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db),
                 user: models.User = Depends(auth.require_admin)):
    """Remove a login for good. Admin only.

    Two things this must not allow: deleting your own account, which
    would sign you out of a system you administer, and removing the last
    admin, which would leave nobody able to restore a backup or add a
    login again.

    Backups, activity entries and adjustments record who made them. The
    login goes, but that history stays and simply no longer names a
    live account - deleting a person should not quietly rewrite what
    was done last month.
    """
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == user.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account.")
    if target.role == "admin":
        others = (db.query(models.User)
                    .filter(models.User.role == "admin", models.User.id != target.id).count())
        if others == 0:
            raise HTTPException(status_code=400,
                detail="This is the only admin account. Make someone else an admin first.")

    username = target.username
    # Detach the history before removing the row, or the database
    # refuses the delete for the sake of those references.
    for model, column in ((models.Backup, "created_by"),
                          (models.AuditLog, "user_id"),
                          (models.SalaryAdjustment, "created_by")):
        db.query(model).filter(getattr(model, column) == target.id) \
                       .update({column: None}, synchronize_session=False)
    db.delete(target)
    db.commit()
    log_action(db, user.id, "delete_user", username)
    return {"ok": True, "detail": f"{username} removed."}


@app.post("/users/{user_id}/reset-password")
def reset_user_password(user_id: int, payload: schemas.ResetPasswordRequest,
                         db: Session = Depends(get_db),
                         user: models.User = Depends(auth.require_admin)):
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


# Served from /users/audit-log, with the bare path kept for anything
# still asking for it.
#
# nginx forwards only the API path prefixes listed in its rule, and
# /audit-log was never one of them - so on the live server every request
# for it fell through to the frontend and came back 404, and the
# Activity screen has been empty there while working perfectly in
# testing. /users is on that list and this is a log of what users did,
# so it belongs there anyway.
@app.get("/users/audit-log")
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
def list_employees(active_only: bool = False, month_year: str = "", as_of: str = "",
                    db: Session = Depends(get_db),
                    user: models.User = Depends(auth.get_current_user)):
    """Every logged-in user may read the worker list - the store needs
    names to record who took material. Pay is another matter: only
    someone who can open Master Data or Salary Adjustments sees it, so a
    store keeper or site engineer can no longer read all 74 salaries."""
    perms = effective_permissions(user)
    may_see_pay = any(s in perms for s in ("masterdata", "adjustments", "livecard"))
    q = db.query(models.Employee)
    if active_only:
        q = q.filter(models.Employee.active == True)  # noqa: E712
    # Asked for a cycle, or for a date, the list is the workforce as it
    # stood then - a man who left in August is still on August's list
    # and gone from September's.
    bounds = None
    try:
        if month_year:
            bounds = pcyc.cycle_bounds_for(datetime.strptime(f"25 {month_year}", "%d %B %Y").date())[:2]
        elif as_of:
            bounds = pcyc.cycle_bounds_for(date.fromisoformat(as_of))[:2]
    except Exception:
        bounds = None
    rows = q.order_by(models.Employee.emp_no).all()
    if bounds:
        rows = [e for e in rows if employed_during(e, bounds[0], bounds[1])]
    if may_see_pay:
        return rows
    # terminated_on goes to everyone: it is not pay information, and the
    # attendance screen cannot mark a leaver correctly without it.
    return [{"id": e.id, "emp_no": e.emp_no, "name": e.name, "trade": e.trade or "",
             "active": e.active, "terminated_on": e.terminated_on,
             "company": e.company, "pay_type": e.pay_type,
             "total_salary": 0, "basic_salary": 0} for e in rows]


@app.post("/employees", response_model=schemas.EmployeeOut)
def upsert_employee(emp: schemas.EmployeeIn, db: Session = Depends(get_db),
                     user: models.User = Depends(require_screen("masterdata"))):
    # Worker names and trades are kept exactly as typed. The office
    # enters them in capitals on purpose, so they print large and clear
    # on the cards - only stray spaces are trimmed.
    emp.name = (emp.name or "").strip()
    emp.trade = (emp.trade or "").strip()
    emp.pay_type = "fixed" if (emp.pay_type or "").strip().lower() == "fixed" else "daily"
    existing = db.query(models.Employee).filter(models.Employee.emp_no == emp.emp_no).first()
    if existing:
        for field, value in emp.dict().items():
            setattr(existing, field, value)
    else:
        existing = models.Employee(**emp.dict())
        db.add(existing)
    db.commit()
    db.refresh(existing)

    # Setting a leaving date rewrites the days after it. Somebody marked
    # Present for the whole month, then found to have left on the 8th,
    # would otherwise keep being paid for a month he did not work - the
    # figure only corrects itself if the days themselves do. Days up to
    # and including his last day are left exactly as they were.
    if existing.terminated_on:
        after = (db.query(models.DailyRow)
                   .filter(models.DailyRow.emp_no == existing.emp_no,
                           models.DailyRow.full_date > existing.terminated_on)
                   .all())
        for r in after:
            r.am = r.pm = "Terminated"
            r.site = ""
            r.engineer = ""
            r.ot = 0
            r.bh = 0
        if after:
            db.commit()
            log_action(db, user.id, "terminate_employee",
                       f"{existing.emp_no} left {existing.terminated_on}, "
                       f"{len(after)} day(s) after it marked Terminated")

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
def remove_employee(emp_no: str, purge: bool = False, db: Session = Depends(get_db),
                     user: models.User = Depends(require_screen("masterdata"))):
    """Remove a worker, in the way that suits what has happened to them.

    Someone who has worked has attendance and salary behind them, and
    deleting the record would tear a hole in months of payroll. That
    person is marked inactive instead: they leave the daily list and
    every report still adds up.

    A record created by mistake - a typo, a duplicate, someone who never
    started - has nothing behind it, and is genuinely deleted.

    purge=true forces a real delete along with that person's history,
    for a duplicate that was already marked and paid against. It says
    what it is destroying before it does it.
    """
    emp = db.query(models.Employee).filter(models.Employee.emp_no == emp_no).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    rows = db.query(models.DailyRow).filter(models.DailyRow.emp_no == emp_no).count()
    sums = db.query(models.EmployeeSummary).filter(models.EmployeeSummary.emp_no == emp_no).count()
    sum_ids = [s.id for s in db.query(models.EmployeeSummary)
                                .filter(models.EmployeeSummary.emp_no == emp_no).all()]
    adjs = (db.query(models.SalaryAdjustment)
              .filter(models.SalaryAdjustment.summary_id.in_(sum_ids)).count() if sum_ids else 0)
    history = rows + sums + adjs

    if history and not purge:
        emp.active = False
        db.commit()
        log_action(db, user.id, "deactivate_employee", f"{emp_no} ({rows} attendance day(s))")
        return {"ok": True, "action": "deactivated", "attendance_days": rows,
                "adjustments": adjs,
                "detail": f"{emp.name} has {rows} day(s) of attendance behind them, so the record is "
                          f"kept and marked inactive. They no longer appear in the daily list."}

    if purge and history:
        db.query(models.DailyRow).filter(models.DailyRow.emp_no == emp_no).delete(synchronize_session=False)
        if sum_ids:
            (db.query(models.SalaryAdjustment)
               .filter(models.SalaryAdjustment.summary_id.in_(sum_ids))
               .delete(synchronize_session=False))
        (db.query(models.EmployeeSummary)
           .filter(models.EmployeeSummary.emp_no == emp_no).delete(synchronize_session=False))
    db.delete(emp)
    db.commit()
    log_action(db, user.id, "delete_employee", f"{emp_no} ({history} record(s) removed)")
    return {"ok": True, "action": "deleted", "removed_history": history,
            "detail": f"{emp.name} removed." + (f" {history} record(s) went with them." if history else "")}


EMPLOYEE_TEMPLATE_HEADERS = ["Emp No", "Name", "Trade", "Company", "Pay Type", "Total Salary", "Basic Salary"]


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
    ws.append(["D-99", "SAMPLE WORKER", "DRIVER", "Infinia", "Fixed", 2000, 900])
    ws.freeze_panes = "A2"
    buf = io.BytesIO()
    # No logo band on a template: it inserts rows at the top, which
    # pushed the column headings off row 1 - so the file this screen
    # hands out was refused by the import that sent people to it.
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
        ws.append([emp.emp_no, emp.name, emp.trade, emp.company or "Infinia",
                  "Fixed" if (emp.pay_type or "daily") == "fixed" else "Daily",
                  emp.total_salary, emp.basic_salary])
    buf = io.BytesIO()
    for _ws in wb.worksheets:
        export_web._excel_logo_header(_ws)
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
        # A blank Company cell means "not stated", not "make this
        # Infinia" - a sheet exported before this column existed, or
        # one where nobody filled it in for every row, must not silently
        # overwrite a Prime Infinia worker back to Infinia on re-import.
        # A cell that DOES say something is treated as a deliberate
        # choice and is honoured exactly.
        company_cell = str(get("company", "") or "").strip()
        company_stated = bool(company_cell)
        company = "Prime Infinia" if company_cell.lower().replace("-", " ") in ("prime infinia", "prime") else "Infinia"
        # Pay Type follows the same rule: blank means not stated, so a
        # sheet without the column cannot turn a foreman back into a
        # day labourer on re-import.
        pay_cell = str(get("pay type", "") or "").strip()
        pay_stated = bool(pay_cell)
        pay_type = "fixed" if pay_cell.lower() in ("fixed", "fixed monthly", "monthly") else "daily"
        file_emp_nos.add(emp_no)

        existing = db.query(models.Employee).filter(models.Employee.emp_no == emp_no).first()
        if existing:
            if duplicate_handling == "skip":
                skipped += 1
            elif duplicate_handling == "add_new":
                new_emp_no = unique_suffixed_emp_no(emp_no)
                db.add(models.Employee(emp_no=new_emp_no, name=name, trade=trade, company=company, pay_type=pay_type,
                                        total_salary=total_salary, basic_salary=basic_salary, active=True))
                added_as_new += 1
            else:  # update
                existing.name, existing.trade = name, trade
                if company_stated:
                    existing.company = company
                if pay_stated:
                    existing.pay_type = pay_type
                existing.total_salary, existing.basic_salary = total_salary, basic_salary
                existing.active = True
                updated += 1
                updated_emp_nos.add(emp_no)
        else:
            db.add(models.Employee(emp_no=emp_no, name=name, trade=trade, company=company, pay_type=pay_type,
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
        # Saving an existing site used to set nothing but active, so the
        # plot number and the engineer could never be corrected once
        # entered. Anything given is kept; anything left blank is left
        # alone, so a half-filled form cannot wipe what is on record.
        for field in ("plot_no", "project_name", "incharge", "incharge_mobile",
                      "address", "map_url"):
            v = (getattr(site, field, "") or "").strip()
            if v:
                setattr(existing, field, v)
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
        # A number given now is kept; a blank one leaves what is on
        # record, so saving a name again cannot wipe his mobile.
        if (eng.mobile or "").strip():
            existing.mobile = eng.mobile.strip()
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
@app.get("/attendance/last-sites/{target_date}")
def last_sites_before(target_date: str, db: Session = Depends(get_db),
                       user: models.User = Depends(require_screen("attendance"))):
    """Each worker's site and engineer from his last day at a site before
    the given date, looking back two weeks. The attendance screen uses
    this to fill Sunday and Holiday rows the moment the status is
    picked, from the last day actually worked - not just from
    yesterday, which is blank when yesterday was Absent.

    Declared before /attendance/{target_date}, or 'last-sites' would be
    read as a date."""
    try:
        target = date.fromisoformat(target_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date.")
    # Last day at a site, for filling site and engineer.
    sited = (db.query(models.DailyRow)
               .filter(models.DailyRow.full_date < target,
                       models.DailyRow.full_date >= target - timedelta(days=14),
                       models.DailyRow.site.isnot(None), models.DailyRow.site != "")
               .order_by(models.DailyRow.emp_no, models.DailyRow.full_date.desc())
               .all())
    out = {}
    for r in sited:
        if r.emp_no not in out:          # first seen is the latest, by the ordering
            out[r.emp_no] = {"site": r.site, "engineer": r.engineer or "", "on": r.full_date.isoformat()}

    # The most recent day marked at all, whatever the status. A man on
    # Leave stays on Leave until somebody marks him back - he is away,
    # and every day of his absence has to be recorded, not left blank
    # for the office to chase.
    latest = (db.query(models.DailyRow)
                .filter(models.DailyRow.full_date < target,
                        models.DailyRow.full_date >= target - timedelta(days=30))
                .order_by(models.DailyRow.emp_no, models.DailyRow.full_date.desc())
                .all())
    seen = set()
    for r in latest:
        if r.emp_no in seen:
            continue
        seen.add(r.emp_no)
        entry = out.setdefault(r.emp_no, {"site": "", "engineer": "", "on": r.full_date.isoformat()})
        entry["last_am"] = r.am or ""
        entry["last_pm"] = r.pm or ""
        entry["last_on"] = r.full_date.isoformat()
    return out


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

    today = _dubai_today()
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

        # He left. Nothing after that date is a working day, however it
        # arrives - a Sunday prefill, a bulk apply, an import, or a
        # stale page open since before he was marked. The company's own
        # leaving date decides, not what was sent.
        if employee.terminated_on and row_in.full_date > employee.terminated_on:
            am = pm = "Terminated"
            row_in.am = row_in.pm = "Terminated"
            row_in.site = row_in.engineer = ""
            row_in.ot = 0
            row_in.bh = 0
            row_in.comments = (row_in.comments or "")

        site, engineer = row_in.site, row_in.engineer
        # Holiday is paid whether or not a site is known, so a missing
        # site is a convenience gap, not a reason to refuse the day off.
        # A worker with no site anywhere on record - never worked, or
        # every day so far was Absent - saves with Holiday and no site,
        # exactly as marking him Absent or Leave already would.
        if (am in ("Holiday", "Sunday") or pm in ("Holiday", "Sunday")) and not (str(site).strip()):
            prev = services.get_previous_day_site_engineer(db, row_in.emp_no, row_in.full_date)
            if prev is not None:
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
    "adjustments": "Everything added or taken off by hand this cycle, signed and with its reason - \"+300 Site bonus\", \"-170 Parking fine\".",
    "total_salary": "The worker's monthly salary as entered in Master Data - basic plus fixed allowance. The same figure every cycle.",
    "total_salary_component": "The part of the salary earned for the days paid this cycle: paid days x (salary / 30). Final Salary = this + OT + BH - absence deduction.",
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
                   date_from: str = None, date_to: str = None, company: str = "",
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
    company_by_emp = {e.emp_no: (e.company or "Infinia") for e in db.query(models.Employee).all()}
    # Asking for one company narrows the report to that company's
    # workers, so Infinia and Prime Infinia can be reported separately.
    if company:
        keep = {n for n, c in company_by_emp.items() if c == company}
        daily_rows = [r for r in daily_rows if r.emp_no in keep]
        summaries2 = [s for s in summaries2 if s.emp_no in keep]
    result = rp.build_custom_report(source, dims, meas, filters, daily_rows, summaries2, company_by_emp)
    return {"title": result.title + (f" - {company}" if company else ""), "note": result.note,
            "columns": [{"key": k, "label": label} for k, label in result.columns],
            "rows": result.rows, "totals": result.totals}


# ---------------------------------------------------------------------
# MONTHLY REPORT - the one report management sees every month end
# ---------------------------------------------------------------------
# The report itself is the report builder with a fixed set of columns,
# so nothing here stores figures: the builder recomputes them for
# whichever cycle is chosen, which is what makes a two-month-old report
# come back on request. What does need keeping is the notes typed
# beside it - the explanation a manager reads before the numbers - and
# those live against the cycle, so an old cycle comes back with the
# notes that went to management with it.
#
# Under /reports/, which nginx forwards. A new prefix would not be.
def _monthly_notes_key(month_year: str) -> str:
    return f"monthly_notes:{month_year.strip()}"


def _load_monthly_notes(db, month_year: str) -> dict:
    """{emp_no: note} for the cycle - empty when nothing was ever written."""
    row = db.query(models.Setting).filter(models.Setting.key == _monthly_notes_key(month_year)).first()
    if not row or not row.value:
        return {}
    try:
        data = json.loads(row.value)
    except Exception:
        return {}
    notes = data.get("notes") if isinstance(data, dict) else None
    return {k: v for k, v in (notes or {}).items() if isinstance(v, str) and v.strip()} \
        if isinstance(notes, dict) else {}


@app.get("/reports/monthly-notes/{month_year}")
def get_monthly_notes(month_year: str, db: Session = Depends(get_db),
                      user: models.User = Depends(require_screen("reports"))):
    return {"month_year": month_year, "notes": _load_monthly_notes(db, month_year)}


@app.post("/reports/monthly-notes/{month_year}")
def save_monthly_note(month_year: str, payload: dict = Body(...), db: Session = Depends(get_db),
                      user: models.User = Depends(require_screen("reports"))):
    """One worker's note for one cycle. Saved the moment the box is
    left, so it is one worker at a time; an empty note removes his line."""
    payload = payload or {}
    if isinstance(payload.get("notes"), dict):
        # The whole page at once, from the Save button: what is sent is
        # what is kept, so a box emptied on screen is emptied here too.
        notes = {str(k).strip(): str(v).strip() for k, v in payload["notes"].items()
                 if str(k).strip() and str(v or "").strip()}
        what = f"{len(notes)} note(s)"
    else:
        emp_no = str(payload.get("emp_no") or "").strip()
        if not emp_no:
            raise HTTPException(status_code=400, detail="Which worker is the note for?")
        note = str(payload.get("note") or "").strip()
        notes = _load_monthly_notes(db, month_year)
        if note:
            notes[emp_no] = note
        else:
            notes.pop(emp_no, None)
        what = f"{emp_no}: {note[:60]}" if note else f"{emp_no}: cleared"
    key = _monthly_notes_key(month_year)
    row = db.query(models.Setting).filter(models.Setting.key == key).first()
    value = json.dumps({"notes": notes, "saved_by": user.full_name or user.username,
                        "saved_on": _dubai_today().isoformat()})
    if row:
        row.value = value
    else:
        db.add(models.Setting(key=key, value=value))
    db.commit()
    log_action(db, user.id, "monthly_note", f"{month_year} {what}")
    return {"ok": True, "month_year": month_year, "notes": notes}


@app.get("/export/{month_year}/custom-report")
def export_custom_report(month_year: str, token: str, data_source: str = "daily",
                          dimensions: str = "", measures: str = "",
                          date_from: str = None, date_to: str = None, format: str = "excel",
                          company: str = "", monthly: str = "", db: Session = Depends(get_db)):
    user = auth.get_download_user_from_token(token, db)
    dims = [d for d in dimensions.split(",") if d]
    meas = [m for m in measures.split(",") if m]
    daily_rows, summaries2, filters = _report_source_rows(db, month_year, date_from, date_to)
    source = data_source if data_source in ("daily", "summary") else "daily"
    # The download must match what was on screen, company filter and all.
    company_by_emp = {e.emp_no: (e.company or "Infinia") for e in db.query(models.Employee).all()}
    if company:
        keep = {n for n, c in company_by_emp.items() if c == company}
        daily_rows = [r for r in daily_rows if r.emp_no in keep]
        summaries2 = [s for s in summaries2 if s.emp_no in keep]
    result = rp.build_custom_report(source, dims, meas, filters, daily_rows, summaries2, company_by_emp)
    result_dict = {"columns": [{"key": k, "label": label} for k, label in result.columns],
                    "rows": result.rows, "totals": result.totals}
    if not result.columns:
        raise HTTPException(status_code=400, detail="No columns selected.")

    # The monthly report carries a note against each worker, matched by
    # the worker number in the first column. Added here, once, so the
    # Excel and the PDF both have it.
    if monthly:
        # One column for both, at the end: each adjustment on its own
        # line, then the note under it. Two text columns side by side
        # left the numbers with no room; one reads better and fits A4.
        notes = _load_monthly_notes(db, month_year)
        result_dict["columns"] = [c for c in result_dict["columns"] if c["key"] != "adjustments"]
        result_dict["columns"].append({"key": "adjustments_notes", "label": "Adjustments & Notes"})
        for row in result_dict["rows"]:
            adj = str(row.get("adjustments") or "").strip()
            lines = [a.strip() for a in adj.split(", ") if a.strip() and a.strip() != "-"]
            note = notes.get(str(row.get("dim_0", "")), "").strip()
            if note:
                lines.append("Note: " + note)
            row["adjustments_notes"] = "\n".join(lines) if lines else "-"

    safe_name = "".join(c if c.isalnum() else "_" for c in month_year)
    if format == "excel":
        buf = export_web.build_generic_result_excel(result_dict, month_year)
        return StreamingResponse(
            buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=Infinia_Report_{safe_name}.xlsx"},
        )
    elif format == "pdf":
        title = "Monthly Payroll Report" if monthly else None
        buf = export_web.build_generic_result_pdf(
            result_dict, month_year, title=title,
            subtitle=(company or "Infinia and Prime Infinia") if monthly else None)
        fname = f"Infinia_Monthly_Report_{safe_name}.pdf" if monthly else f"Infinia_Report_{safe_name}.pdf"
        return StreamingResponse(
            buf, media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={fname}"},
        )
    raise HTTPException(status_code=400, detail="format must be 'excel' or 'pdf'.")


@app.get("/live-card/{emp_no}/{month_year}")
def get_live_card(emp_no: str, month_year: str, db: Session = Depends(get_db),
                   user: models.User = Depends(require_screen("livecard"))):
    # A live card is a worker's full pay picture. The screen was hidden
    # from roles that must not see salaries, but the endpoint answered
    # anyone signed in - so a site engineer could read every wage by
    # calling it directly. Guarded like the screen now.
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
    emp = db.query(models.Employee).filter(models.Employee.emp_no == emp_no).first()
    if summary:
        summary_out = schemas.EmployeeSummaryOut.from_orm(summary)
        # The name on the card is read from the master record, not from
        # whatever was stored when the summary was first written. A card
        # headed with a different name than the man clicked in the list
        # beside it is the worst thing a pay screen can show, and it is
        # not worth depending on a recalculation having happened first.
        if emp:
            summary_out.emp_name = emp.name
            summary_out.trade = emp.trade
    else:
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
                    user: models.User = Depends(require_screen("adjustments"))):
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


# Under /summaries/ rather than its own /adjustments/ prefix: nginx only
# forwards the API path prefixes listed in its rule, and /adjustments/
# was never one of them, so every delete fell through to the frontend
# and came back 405. The add endpoint already lives under /summaries/
# and works; this now does too, without touching server config.
@app.delete("/summaries/{summary_id}/adjustments/{adjustment_id}")
def remove_adjustment(summary_id: int, adjustment_id: int, db: Session = Depends(get_db),
                       user: models.User = Depends(require_screen("adjustments"))):
    adj = db.query(models.SalaryAdjustment).filter(models.SalaryAdjustment.id == adjustment_id,
                                                     models.SalaryAdjustment.summary_id == summary_id).first()
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
                 user: models.User = Depends(require_screen("errorcheck"))):
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

    active_employees = [e for e in db.query(models.Employee)
                          .filter(models.Employee.active == True).all()   # noqa: E712
                        if employed_during(e, cycle_start, cycle_end)]
    rows = db.query(models.DailyRow).filter(models.DailyRow.month_year == month_year).all()

    # Every name on this screen comes from the master record. The name
    # copied onto a day's row is a snapshot of what the worker was
    # called when it was typed, so after a correction in Master Data
    # this screen went on naming the old one and sent the office looking
    # for the wrong man. The stored name is used only for someone no
    # longer in the list at all.
    name_now = {e.emp_no: e.name for e in db.query(models.Employee).all()}
    def who(r):
        return name_now.get(r.emp_no) or r.emp_name

    dates_by_emp = {}
    for r in rows:
        dates_by_emp.setdefault(r.emp_no, set()).add(r.full_date)

    from datetime import timedelta
    # Only days that have already happened can be missing. On the third
    # of the month the remaining twenty-two are not late, they are
    # simply not here yet - listing them made every worker look
    # twenty-nine days behind on day one.
    today = _dubai_today()
    # Today is not missing - it is not over. Attendance is entered as
    # the day goes on, so the check runs up to yesterday; otherwise
    # every morning the whole workforce reads one day short.
    last_day = min(cycle_end, today - timedelta(days=1))
    all_dates = []
    d = cycle_start
    while d <= last_day:
        all_dates.append(d)
        d += timedelta(days=1)
    cycle_days = (cycle_end - cycle_start).days + 1
    elapsed_days = len(all_dates)

    out = []
    for emp in active_employees:
        entered = dates_by_emp.get(emp.emp_no, set())
        # Nothing is owed for days after he left.
        upto = [d for d in all_dates
                if emp.terminated_on is None or d <= emp.terminated_on]
        missing = [d for d in upto if d not in entered]
        if not entered:
            out.append({"emp_no": emp.emp_no, "name": emp.name, "date": "-", "site": "-",
                        "issue": f"No attendance entered at all for {month_year}.",
                        "kind": "Nothing entered",
                        "detail": {"Cycle": f"{cycle_start} to {cycle_end}",
                                   "Days in cycle": str(len(all_dates)),
                                   "Days entered": "0", "Trade": emp.trade or "-"}})
        elif missing:
            preview = ", ".join(d.strftime("%d %b") for d in missing[:5])
            more = f" (+{len(missing) - 5} more)" if len(missing) > 5 else ""
            out.append({"emp_no": emp.emp_no, "name": emp.name, "date": "-", "site": "-",
                        "issue": f"{len(missing)} day(s) missing: {preview}{more}",
                        "kind": f"{len(missing)} day(s) missing",
                        "detail": {"Trade": emp.trade or "-",
                                   "Days in cycle": str(len(all_dates)),
                                   "Days entered": str(len(entered)),
                                   "Every missing day":
                                       ", ".join(d.strftime("%d %b") for d in missing)}})

    # Hours worked on a day nobody worked. Absent means the worker was
    # not there, so OT or BH against it is a contradiction - usually a
    # status picked in the wrong row, or hours typed on the wrong line.
    # Holiday is flagged too: a worker who genuinely worked a holiday
    # should be marked Present, not Holiday.
    for r in rows:
        flagged_statuses = {s for s in ((r.am or "").strip(), (r.pm or "").strip())
                            if s in ("Absent", "Holiday")}
        hours = []
        if r.ot and r.ot > 0:
            hours.append(f"{r.ot:g} OT")
        if r.bh and r.bh > 0:
            hours.append(f"{r.bh:g} BH")
        if flagged_statuses and hours:
            marked = " and ".join(sorted(flagged_statuses))
            out.append({
                "emp_no": r.emp_no, "name": who(r), "date": str(r.full_date), "site": r.site or "-",
                "issue": f"{' and '.join(hours)} hour(s) recorded on a day marked {marked}.",
                "kind": f"Hours on an {marked.lower()} day" if marked == "Absent" else f"Hours on a {marked.lower()} day",
                "severity": "contradiction",
                "detail": {
                    "Date": str(r.full_date),
                    "A.M": r.am or "-", "P.M": r.pm or "-",
                    "OT hours": f"{r.ot or 0:g}", "BH hours": f"{r.bh or 0:g}",
                    "Site": r.site or "-", "Engineer": r.engineer or "-",
                    "Comment": r.comments or "none",
                    "What to check": "Either the status is wrong, or the hours belong to another day "
                                     "or another worker. A worker who did work should be marked Present.",
                },
            })

    for r in rows:
        if r.ot and r.ot > 12:
            out.append({"emp_no": r.emp_no, "name": who(r), "date": str(r.full_date), "site": r.site,
                        "issue": f"OT of {r.ot} hours in one day looks unusually high.",
                        "kind": "High OT",
                        "detail": {"Date": str(r.full_date), "A.M": r.am or "-", "P.M": r.pm or "-",
                                   "Site": r.site or "-", "Engineer": r.engineer or "-",
                                   "OT hours": f"{r.ot:g}", "BH hours": f"{r.bh or 0:g}",
                                   "Comment": r.comments or "none"}})
        if r.bh and r.bh > 8:
            out.append({"emp_no": r.emp_no, "name": who(r), "date": str(r.full_date), "site": r.site,
                        "issue": f"BH of {r.bh} hours in one day looks unusually high.",
                        "kind": "High BH",
                        "detail": {"Date": str(r.full_date), "A.M": r.am or "-", "P.M": r.pm or "-",
                                   "Site": r.site or "-", "Engineer": r.engineer or "-",
                                   "OT hours": f"{r.ot or 0:g}", "BH hours": f"{r.bh:g}",
                                   "Comment": r.comments or "none"}})

    # UAE rule: a worker must take home at least 40% of their total
    # salary. Deductions and absences can eat past that without anyone
    # noticing until the pay run, so it is flagged here while there is
    # still time to look at it.
    summaries = (db.query(models.EmployeeSummary)
                   .filter(models.EmployeeSummary.month_year == month_year).all())
    entered_by_emp = {}
    for r in rows:
        entered_by_emp[r.emp_no] = entered_by_emp.get(r.emp_no, 0) + 1
    for s in summaries:
        total = s.total_salary or 0
        entered = entered_by_emp.get(s.emp_no, 0)
        if total <= 0 or entered <= 0:
            continue
        take_home = s.adjusted_final_salary()
        # Measured against the days actually entered for this worker,
        # not the days elapsed - a day nobody has marked yet is the
        # missing-days flag's business, not this one's. Three days in,
        # a man is judged on three days' pay; at the end of a full cycle
        # this is his whole salary and the rule is exactly the legal one.
        so_far = total * entered / cycle_days
        floor = so_far * 0.40
        if take_home < floor - 0.005:
            pct = (take_home / so_far * 100) if so_far else 0
            partial = entered < cycle_days
            adj = sum((-a.amount if a.is_deduction else a.amount) for a in s.adjustments)
            out.append({
                "emp_no": s.emp_no, "name": name_now.get(s.emp_no) or s.emp_name, "date": "-", "site": "-",
                "issue": (f"Final salary AED {take_home:,.0f} is {pct:.0f}% of the "
                          f"AED {so_far:,.0f} for the {entered} day(s) entered so far "
                          f"- below the 40% minimum (AED {floor:,.0f})."
                          if partial else
                          f"Final salary AED {take_home:,.0f} is {pct:.0f}% of the "
                          f"AED {total:,.0f} total - below the 40% minimum "
                          f"(AED {floor:,.0f})."),
                "kind": "Pay below 40%",
                "severity": "legal",
                "detail": {
                    "Total salary": f"AED {total:,.2f}",
                    **({"Pay for days entered": f"AED {so_far:,.2f} ({entered} of {cycle_days} days)"} if partial else {}),
                    "Minimum payable (40%)": f"AED {floor:,.2f}",
                    "Final salary now": f"AED {take_home:,.2f}",
                    "Short by": f"AED {floor - take_home:,.2f}",
                    "Days absent": f"{s.absent_days:g}",
                    "Absence deduction": f"AED {s.deduction:,.2f}",
                    "Adjustments": (f"AED {adj:,.2f}" if s.adjustments else "none"),
                    "What the adjustments were":
                        ", ".join(f"{a.description} {'-' if a.is_deduction else '+'}{a.amount:,.0f}"
                                  for a in s.adjustments) or "-",
                },
            })

    # Everything about one worker belongs together - chasing a man's
    # problems across three separate parts of the list is how one gets
    # missed. Workers with the most serious issue come first, and within
    # a worker the serious ones lead.
    # How many days each worker is short, whatever else is wrong with
    # him - a pay warning is often just the consequence of days not
    # entered yet, and the reminder sheet should still be offered.
    missing_by_emp = {}
    for emp in active_employees:
        entered = dates_by_emp.get(emp.emp_no, set())
        upto = [d for d in all_dates
                if emp.terminated_on is None or d <= emp.terminated_on]
        missing_by_emp[emp.emp_no] = len([d for d in upto if d not in entered])

    rank = {"legal": 0, "contradiction": 1}
    worst_by_emp, count_by_emp = {}, {}
    for x in out:
        r = rank.get(x.get("severity"), 2)
        worst_by_emp[x["emp_no"]] = min(worst_by_emp.get(x["emp_no"], 9), r)
        count_by_emp[x["emp_no"]] = count_by_emp.get(x["emp_no"], 0) + 1
    out.sort(key=lambda x: (worst_by_emp[x["emp_no"]], x["emp_no"],
                            rank.get(x.get("severity"), 2), str(x["date"])))
    for x in out:
        x["issue_count"] = count_by_emp[x["emp_no"]]
        x["days_missing"] = missing_by_emp.get(x["emp_no"], 0)
    return {
        "title": "Check for Errors",
        "note": "Workers paid below the 40% minimum, hours recorded on absent or holiday "
                "days, missing days in this cycle, and unusually high single-day OT/BH values.",
        "rows": out,
    }


@app.get("/export/{month_year}/excel")
def export_excel(month_year: str, token: str, emp_no: str = "", db: Session = Depends(get_db)):
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
    )
    # One worker's card on its own - for handing to him, or emailing
    # one man's payslip - rather than the whole company in a file.
    if emp_no.strip():
        summaries = summaries.filter(models.EmployeeSummary.emp_no == emp_no.strip())
    summaries = summaries.order_by(models.EmployeeSummary.emp_no).all()
    if not summaries:
        raise HTTPException(status_code=404, detail=("No data found for this worker in this cycle."
                                                     if emp_no.strip() else "No data found for this cycle."))
    pairs = []
    for s in summaries:
        rows = db.query(models.DailyRow).filter(
            and_(models.DailyRow.emp_no == s.emp_no, models.DailyRow.month_year == month_year)
        ).all()
        pairs.append((s, rows))
    buf = export_web.build_combined_excel(pairs)
    safe_name = "".join(c if c.isalnum() else "_" for c in month_year)
    fname = (f"Infinia_Card_{summaries[0].emp_no}_{safe_name}.xlsx" if emp_no.strip()
             else f"Infinia_Cards_{safe_name}.xlsx")
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


@app.get("/export/{month_year}/pdf")
def export_pdf(month_year: str, token: str, emp_no: str = "", db: Session = Depends(get_db)):
    user = auth.get_download_user_from_token(token, db)
    summaries = (
        db.query(models.EmployeeSummary)
        .options(joinedload(models.EmployeeSummary.adjustments))
        .filter(models.EmployeeSummary.month_year == month_year)
    )
    if emp_no.strip():
        summaries = summaries.filter(models.EmployeeSummary.emp_no == emp_no.strip())
    summaries = summaries.order_by(models.EmployeeSummary.emp_no).all()
    if not summaries:
        raise HTTPException(status_code=404, detail=("No data found for this worker in this cycle."
                                                     if emp_no.strip() else "No data found for this cycle."))
    pairs = []
    for s in summaries:
        rows = db.query(models.DailyRow).filter(
            and_(models.DailyRow.emp_no == s.emp_no, models.DailyRow.month_year == month_year)
        ).all()
        pairs.append((s, rows))
    buf = export_web.build_combined_pdf(pairs)
    safe_name = "".join(c if c.isalnum() else "_" for c in month_year)
    fname = (f"Infinia_Card_{summaries[0].emp_no}_{safe_name}.pdf" if emp_no.strip()
             else f"Infinia_Cards_{safe_name}.pdf")
    return StreamingResponse(
        buf, media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
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


# Daily snapshots older than this are cleared as new ones are taken.
BACKUP_KEEP_DAYS = 40


# The backup covers every table the application defines, found by
# walking the models rather than by a list kept here. A list has to be
# remembered: the store was added long after the backup was written and
# never joined it, so for months a snapshot held the payroll side while
# thousands of materials and every movement existed only on the live
# server. Purchase orders were captured but never restored. Settings
# were never captured at all. Each of those was a table somebody forgot.
#
# Walking the schema means a table added next year is in the backup the
# day it is created, with no one having to think about it, and
# tests/backup_completeness_test.py fails the build if this ever stops
# being true.
#
# Only the backups table itself is left out - a backup of backups grows
# on itself every time one is taken.
BACKUP_SKIP_TABLES = {"backups"}


def _backup_models():
    """Every mapped model except the ones deliberately skipped, in an
    order where a row never arrives before the rows it points at."""
    by_table = {}
    for mapper in Base.registry.mappers:
        by_table[mapper.class_.__tablename__] = mapper.class_
    out = []
    for table in Base.metadata.sorted_tables:      # parents before children
        if table.name in BACKUP_SKIP_TABLES:
            continue
        model = by_table.get(table.name)
        if model is not None:
            out.append((table.name, model))
    return out


# Files the app keeps on disk rather than in the database: the uploaded
# signature, the logo. Everything in the data directory is taken,
# whatever it is - the same reasoning as walking the schema, so an
# upload added next year is in the backup without anyone remembering.
#
# A cap per file, because that directory is writable and a backup is no
# place for somebody's stray video.
BACKUP_FILE_MAX_BYTES = 8 * 1024 * 1024


def _backup_file_sources():
    """(name, absolute path) for every file worth keeping."""
    out = []
    data_dir = getattr(export_web, "DATA_DIR", None)
    if data_dir and os.path.isdir(data_dir):
        for name in sorted(os.listdir(data_dir)):
            full = os.path.join(data_dir, name)
            if os.path.isfile(full) and not name.startswith("."):
                out.append((name, full))
    # The logo sits beside the code rather than in the data directory.
    logo = getattr(export_web, "LOGO_PATH", None)
    if logo and os.path.isfile(logo) and not any(n == "logo.png" for n, _ in out):
        out.append(("logo.png", logo))
    return out


def build_backup_files() -> dict:
    """Each file as base64, so the snapshot stays one JSON document that
    can be mailed, copied and read anywhere."""
    files = {}
    for name, path in _backup_file_sources():
        try:
            if os.path.getsize(path) > BACKUP_FILE_MAX_BYTES:
                continue
            with open(path, "rb") as f:
                files[name] = base64.b64encode(f.read()).decode("ascii")
        except Exception:
            continue          # a file we cannot read must not stop a backup
    return files


def restore_backup_files(files: dict) -> list:
    """Put the signature and anything beside it back where they live."""
    written = []
    data_dir = getattr(export_web, "DATA_DIR", None)
    if not data_dir or not files:
        return written
    for name, blob in (files or {}).items():
        # Only ever a plain filename, never a path - a backup must not
        # be able to write outside the directory it came from.
        safe = os.path.basename(str(name))
        if not safe or safe.startswith("."):
            continue
        target = export_web.LOGO_PATH if safe == "logo.png" and not os.path.isfile(
            os.path.join(data_dir, safe)) else os.path.join(data_dir, safe)
        try:
            with open(target, "wb") as f:
                f.write(base64.b64decode(blob))
            written.append(safe)
        except Exception:
            continue
    return written


def build_backup_data(db: Session) -> dict:
    """Everything the company would need to rebuild this system.

    Every table, including the activity log: what it costs in size is
    small next to being asked a year from now who changed a figure and
    having no answer because the server was rebuilt. Staff logins are
    included so people can sign in after a restore - passwords are
    stored hashed, never in the clear.
    """
    data = {
        "generated_at": datetime.utcnow().isoformat(),
        "format": 3,
        "tables": [name for name, _ in _backup_models()],
    }
    for name, model in _backup_models():
        data[name] = [_row_to_dict(r) for r in db.query(model).all()]
    # The uploaded signature and the logo - on disk, not in any table,
    # and gone for good if a snapshot skips them.
    data["files"] = build_backup_files()
    # Format 2 and earlier named four tables differently. Both spellings
    # are written, so a backup taken today can still be read by a server
    # running yesterday's code if a deploy has to be rolled back.
    for old, new in (("daily_rows", "daily_rows"), ("summaries", "employee_summaries"),
                     ("adjustments", "salary_adjustments"), ("users", "users")):
        if new in data and old != new:
            data[old] = data[new]
    return data


# Backups now carry every table, the activity log included, so they are
# stored compressed - a snapshot a day for forty days, each holding the
# whole company, is a lot of text to keep in a database on a small
# server. Plain JSON written by older versions still reads back, so
# nothing taken before today is lost.
_BACKUP_GZIP_PREFIX = "gz:"


def _backup_dump(data: dict) -> str:
    raw = json.dumps(data, default=str)
    packed = base64.b64encode(gzip.compress(raw.encode("utf-8"))).decode("ascii")
    # Only keep the compressed form if it is actually smaller.
    return _BACKUP_GZIP_PREFIX + packed if len(packed) < len(raw) else raw


def _backup_text(stored: str) -> str:
    """The snapshot as plain JSON, whatever form it was stored in."""
    if stored and stored.startswith(_BACKUP_GZIP_PREFIX):
        return gzip.decompress(base64.b64decode(stored[len(_BACKUP_GZIP_PREFIX):])).decode("utf-8")
    return stored


def _backup_json(b) -> dict:
    return json.loads(_backup_text(b.data))


def _coerce_row(model, row):
    """A JSON row back into the types its columns expect - dates and
    times come out of JSON as strings."""
    from sqlalchemy import Date, DateTime
    out = {}
    cols = {c.name: c for c in model.__table__.columns}
    for key, val in dict(row).items():
        col = cols.get(key)
        if col is None:
            continue                       # a column this version no longer has
        if isinstance(val, str) and val:
            if isinstance(col.type, DateTime):
                try:
                    out[key] = datetime.fromisoformat(val)
                    continue
                except ValueError:
                    pass
            elif isinstance(col.type, Date):
                try:
                    out[key] = date.fromisoformat(val)
                    continue
                except ValueError:
                    pass
        out[key] = val
    return out


def restore_backup_data(db: Session, data: dict, keep_usernames: set) -> dict:
    """Put a snapshot back, whole.

    Children are emptied before parents and parents refilled before
    children, both orders taken from the schema, so no row is ever
    written pointing at one that is not there yet.

    Staff logins are the one exception: an admin restoring a snapshot
    must not delete the account they are signed in with, so logins that
    exist now are left alone and only missing ones are put back.
    """
    models_in_order = _backup_models()
    # Anything the snapshot does not carry is left exactly as it is - an
    # older backup cannot wipe a table it never knew about.
    present = [(n, m) for n, m in models_in_order
               if n in data or n in ("employee_summaries", "salary_adjustments")]

    def rows_for(name):
        if name in data:
            return data[name]
        return data.get({"employee_summaries": "summaries",
                         "salary_adjustments": "adjustments"}.get(name, name), [])

    for name, model in reversed(present):          # children first
        if model is models.User:
            continue
        db.query(model).delete(synchronize_session=False)
    db.flush()

    counts = {}
    for name, model in present:                    # parents first
        rows = rows_for(name)
        if model is models.User:
            # Logins already here are left alone, so the admin running
            # the restore keeps the account they are signed in with.
            # A missing one comes back with its own id where that id is
            # free - which keeps "who recorded this" pointing at the
            # right person - and is renumbered when it is not, as it
            # will be on a rebuilt server where a rescue admin already
            # holds id 1. A collision there used to abort the whole
            # restore.
            taken = {u.id for u in db.query(models.User).all()}
            restored = 0
            for r in rows:
                r = _coerce_row(model, r)
                if r.get("username") in keep_usernames:
                    continue
                if r.get("id") in taken:
                    r.pop("id", None)
                else:
                    taken.add(r.get("id"))
                db.add(model(**r))
                db.flush()
                restored += 1
            counts[name] = restored
            db.commit()
            continue
        for r in rows:
            db.add(model(**_coerce_row(model, r)))
        counts[name] = len(rows)
        db.commit()
    db.commit()
    return counts


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
                    # A new column arrives empty on every existing row.
                    # Where the model declares a plain default, apply it
                    # to what is already there - otherwise hundreds of
                    # records sit with nothing in a field the app now
                    # expects to be filled.
                    d = getattr(col.default, "arg", None) if col.default is not None else None
                    if isinstance(d, (str, int, float, bool)):
                        val = f"'{d}'" if isinstance(d, str) else (
                            "TRUE" if d is True else "FALSE" if d is False else str(d))
                        conn.execute(text(
                            f'UPDATE {table.name} SET {col.name} = {val} WHERE {col.name} IS NULL'))
                        print(f"  backfilled {table.name}.{col.name} = {d}")
                except Exception as e:
                    print(f"Could not add {table.name}.{col.name}: {e}")


AUTO_BACKUP_KEEP_DAYS = 40

# Taken by the system as a matter of course, rather than by someone who
# meant to. Only one of these is kept per day, and they are the ones
# pruned; a manual backup, or the one taken before a store clearance,
# was deliberate and is never cleared out from under whoever took it.
ROUTINE_TRIGGERS = ("auto", "daily")


def _todays_routine_backup(db: Session):
    """Today's routine snapshot, if one has already been taken."""
    return (db.query(models.Backup)
              .filter(models.Backup.trigger.in_(ROUTINE_TRIGGERS),
                      func.date(models.Backup.created_at) == _dubai_today())
              .first())

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
    if not _todays_routine_backup(db):
        data = build_backup_data(db)
        db.add(models.Backup(created_by=None, trigger="auto", data=json.dumps(data, default=str)))
        db.commit()

    # Prune: keep only the newest N automatic backups.
    old_auto = (
        db.query(models.Backup)
        .filter(models.Backup.trigger.in_(ROUTINE_TRIGGERS))
        .order_by(models.Backup.created_at.desc())
        .offset(AUTO_BACKUP_KEEP_DAYS)
        .all()
    )
    if old_auto:
        for b in old_auto:
            db.delete(b)
        db.commit()


# Deliberately under /backup/ rather than a new /admin/ prefix: nginx
# only forwards the API paths listed in its rule, and anything else
# falls through to the frontend, where a POST comes back 405. Reusing a
# prefix that already works means no server config change to deploy
# this - and it belongs with the backups anyway, since it takes one.
@app.post("/backup/store-reset")
def store_reset(payload: dict = Body(...), db: Session = Depends(get_db),
                user: models.User = Depends(auth.require_admin)):
    """Empty the store before it goes live, and touch nothing else.

    The store was filled with practice entries while it was being built,
    at a time when attendance and payroll were already running on real
    data. So this clears the store side only - every stock movement,
    material request and purchase order - and the attendance tables are
    not even named here, let alone deleted from.

    Two things are kept unless explicitly asked for, because they are
    usually typed-up master lists rather than practice:
      the material list  - thousands of items, imported once
      the supplier list  - names, TRNs and payment terms

    Admin only, the exact words must be typed, and a full backup is
    taken first and kept on the server, so this can be undone.
    """
    payload = payload or {}
    if payload.get("confirm") != "CLEAR STORE":
        raise HTTPException(status_code=400,
            detail='Type CLEAR STORE exactly to confirm.')

    also_materials = bool(payload.get("clear_materials"))
    also_suppliers = bool(payload.get("clear_suppliers"))

    # A copy of everything first, so a mistake here costs a restore and
    # not the data.
    db.add(models.Backup(created_by=user.id, trigger="before-store-reset",
                         data=_backup_dump(build_backup_data(db))))
    db.commit()

    # Child rows first, so nothing is left pointing at a deleted parent.
    targets = [("order lines", models.PurchaseOrderLine),
               ("purchase orders", models.PurchaseOrder),
               ("request lines", models.MaterialRequestLine),
               ("material requests", models.MaterialRequest),
               ("stock movements", models.StoreMovement)]
    if also_suppliers:
        targets.append(("suppliers", models.Supplier))
    if also_materials:
        targets.append(("materials", models.StoreItem))

    cleared = {}
    for label, model in targets:
        cleared[label] = db.query(model).delete(synchronize_session=False)
    db.commit()

    log_action(db, user.id, "store_reset",
               ", ".join(f"{n} {k}" for k, n in cleared.items() if n) or "nothing to clear")

    kept = {
        "materials": db.query(models.StoreItem).count(),
        "suppliers": db.query(models.Supplier).count(),
        # Named in the reply on purpose: the one thing worth confirming
        # after a clearance is that the live side is still standing.
        "attendance days": db.query(models.DailyRow).count(),
        "workers": db.query(models.Employee).count(),
        "sites": db.query(models.Site).count(),
    }
    return {"ok": True, "cleared": cleared, "kept": kept,
            "detail": f"Store cleared. Attendance and payroll untouched - "
                      f"{kept['attendance days']} attendance days still on file. "
                      f"Requests start again at MR-0001 and orders at IC/LPO/{LPO_START_NO}. "
                      f"A backup taken just before this is at the top of the list below."}


@app.post("/backup/fresh-start")
def fresh_start(payload: dict = Body(...), db: Session = Depends(get_db),
                 user: models.User = Depends(auth.require_admin)):
    """Clear the test data before going live, keeping the master lists.

    Kept: workers with their company, sites, engineers, the material
    list and every staff login. Cleared: attendance, payroll summaries,
    salary adjustments, stock movements, requests, suppliers and the
    activity log.

    Admin only, and the exact words must be typed - this empties the
    company's records and there is no undo beyond the backup it takes
    first. That backup is kept on the server so it can be restored from
    the list below, whatever else happens.
    """
    if (payload or {}).get("confirm") != "CLEAR EVERYTHING":
        raise HTTPException(status_code=400,
            detail='Type CLEAR EVERYTHING exactly to confirm.')

    # A copy of everything first, kept as a normal backup so it can be
    # restored from Settings if today's figures turn out to be needed.
    db.add(models.Backup(created_by=user.id, trigger="before-fresh-start",
                         data=_backup_dump(build_backup_data(db))))
    db.commit()

    cleared = {}
    # Child-first, so nothing is left pointing at a deleted row.
    for label, model in (("order lines", models.PurchaseOrderLine),
                         ("purchase orders", models.PurchaseOrder),
                         ("request lines", models.MaterialRequestLine),
                         ("material requests", models.MaterialRequest),
                         ("stock movements", models.StoreMovement),
                         ("suppliers", models.Supplier),
                         ("salary adjustments", models.SalaryAdjustment),
                         ("payroll summaries", models.EmployeeSummary),
                         ("attendance days", models.DailyRow)):
        cleared[label] = db.query(model).delete(synchronize_session=False)
    db.commit()
    # The activity log goes last, so this clearance is itself recorded.
    db.query(models.AuditLog).delete(synchronize_session=False)
    db.commit()
    log_action(db, user.id, "fresh_start",
               ", ".join(f"{n} {k}" for k, n in cleared.items() if n))

    kept = {
        "workers": db.query(models.Employee).count(),
        "sites": db.query(models.Site).count(),
        "engineers": db.query(models.Engineer).count(),
        "materials": db.query(models.StoreItem).count(),
        "staff logins": db.query(models.User).count(),
    }
    return {"ok": True, "cleared": cleared, "kept": kept,
            "detail": "Cleared. A backup of what was removed is at the top of the "
                      "backup list, and request numbering starts again at MR-0001."}


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


@app.get("/backup/latest/download")
def download_latest_backup(token: str = None, db: Session = Depends(get_db)):
    """A complete copy of the system for whoever is signed in.

    The point is that the company's data ends up on several machines
    rather than only the one server, so anyone using the app can hold a
    copy. Every table is included, so any of these files can rebuild the
    business.

    Password hashes are the one thing removed. They are of no use in a
    restore - existing logins are kept and missing ones come back with
    their names, roles and permissions, needing a fresh password - and
    a file sitting in a Downloads folder should not carry them.
    """
    user = auth.get_download_user_from_token(token, db)
    # A full copy carries every worker's pay, so it goes only to the
    # machines that are allowed to see pay anyway. A site engineer or
    # store keeper holding a copy would undo the salary privacy the rest
    # of the app enforces.
    perms = effective_permissions(user)
    # Only someone who can already see pay in the app gets a file that
    # carries every salary. Approvals marks the office desk; the payroll
    # screens mark an admin. A site engineer, or a store keeper whose
    # login is office in name but store-only in permissions, is not
    # handed one.
    if not any(s in perms for s in ("approvals", "masterdata", "adjustments", "reports", "livecard")):
        raise HTTPException(status_code=403,
            detail="Only office and admin accounts can download a full backup.")
    data = build_backup_data(db)
    data["users"] = [{**u, "hashed_password": ""} for u in data.get("users", [])]
    data["downloaded_by"] = user.username
    body = json.dumps(data, default=str)
    # Keep one snapshot a day on the server as well, so the two copies
    # match and the list does not fill with one row per person per day.
    today = _dubai_today()
    # One routine snapshot a day, whatever prompted it. Signing in takes
    # one and downloading a copy took another, so a day with both held
    # two identical snapshots of the whole company - and a day that also
    # had a store clearance held three. Only the deliberate ones, taken
    # before something risky, are kept alongside.
    if not _todays_routine_backup(db):
        db.add(models.Backup(created_by=user.id, trigger="daily",
                             data=_backup_dump(build_backup_data(db))))
        # Each snapshot is several megabytes, so old ones are cleared as
        # new ones arrive - otherwise the database quietly grows by a
        # copy of itself every day. Manual backups are left alone: those
        # were taken deliberately, usually before something risky.
        cutoff = datetime.now(timezone.utc) - timedelta(days=BACKUP_KEEP_DAYS)
        old_ones = (db.query(models.Backup)
                      .filter(models.Backup.trigger.in_(ROUTINE_TRIGGERS),
                              models.Backup.created_at < cutoff).all())
        for b in old_ones:
            db.delete(b)
        db.commit()
    buf = io.BytesIO(body.encode("utf-8"))
    return StreamingResponse(
        buf, media_type="application/json",
        headers={"Content-Disposition":
                 f'attachment; filename=Infinia_Full_Backup_{today.isoformat()}.json'},
    )


@app.get("/backup/{backup_id}/download")
def download_backup(backup_id: int, token: str, db: Session = Depends(get_db)):
    user = auth.get_download_user_from_token(token, db)
    b = db.query(models.Backup).filter(models.Backup.id == backup_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Backup not found.")
    log_action(db, user.id, "download_backup", f"backup #{backup_id}")
    buf = io.BytesIO(_backup_text(b.data).encode("utf-8"))
    ts = b.created_at.date().isoformat()
    return StreamingResponse(
        buf, media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=Infinia_Backup_{ts}_{backup_id}.json"},
    )


@app.post("/backup/{backup_id}/restore")
def restore_backup(backup_id: int, db: Session = Depends(get_db),
                    user: models.User = Depends(auth.require_admin)):
    """
    Put the whole system back as it stood when the snapshot was taken.

    Admin only, unlike taking a backup - this overwrites current data,
    so it stays behind the higher bar. Every table the snapshot carries
    is replaced: workers, sites, engineers, attendance, payroll,
    adjustments, the store, purchase orders, settings and the activity
    log. Anything the snapshot does not carry is left alone, so an older
    backup cannot wipe a table it never knew about.

    Staff logins are the exception: those on the server now are kept, so
    the admin doing the restore cannot lock themselves out, and only
    missing ones are put back.
    """
    b = db.query(models.Backup).filter(models.Backup.id == backup_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Backup not found.")
    data = _backup_json(b)

    keep = {u.username for u in db.query(models.User).all()}
    counts = restore_backup_data(db, data, keep)
    files = restore_backup_files(data.get("files") or {})
    if files:
        counts["files"] = len(files)

    log_action(db, user.id, "restore_backup",
               f"restored from backup #{backup_id}: "
               + ", ".join(f"{n} {c}" for n, c in counts.items() if c))
    return {"ok": True, "restored_from": backup_id, "restored": counts,
            "detail": "Restored " + ", ".join(f"{c} {n.replace('_', ' ')}"
                                               for n, c in counts.items() if c) + "."}



@app.delete("/backup/{backup_id}")
def delete_backup(backup_id: int, db: Session = Depends(get_db),
                   user: models.User = Depends(auth.require_admin)):
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

# What a site can still be holding.
#
# A consumable is spent where it is used. Fifty bags of cement sent to
# 901 are in the wall within a day or two, so carrying them as stock at
# that site forever makes every site look like a warehouse and buries
# the few things that really are there - the drill that has to come
# back, the hired scaffolding somebody is paying for by the week.
#
# In the central store everything is stock, consumables included,
# because there it genuinely is sitting on a shelf. It is only at a site
# that a consumable stops being stock. What was sent is not lost: it
# stays in the ledger and shows as what was last sent there, which is
# the question a keeper actually asks before sending more.
HELD_AT_SITE = ("returnable", "asset", "rental")


def _held_at_site(item) -> bool:
    return (getattr(item, "item_type", "") or "consumable") in HELD_AT_SITE


def _ever_stocked(db) -> set:
    """Item ids the store has ever received. A material that has never
    come in is not "running low" - it is not stocked yet - and on the
    first morning of an empty store, saying otherwise put a warning
    against every material with a reorder level, before anything had
    happened at all."""
    M = models.StoreMovement
    return {iid for (iid,) in db.query(M.item_id).filter(M.kind == "in").distinct().all()}


def _stock_map(db: Session, upto: date = None, by_owner: bool = False):
    """
    Current quantity of every item at every location, derived from the
    movement ledger rather than stored - so a balance can never drift
    away from the history that produced it.

    Returns {(item_id, location): qty}. 'upto' gives the position as at
    a date, which is what makes stock-as-at reporting possible.

    by_owner returns {(item_id, location, owner_id): qty} instead, where
    owner_id None means ours and a supplier id means hired in from that
    trader. Every caller that does not ask for it gets exactly the
    figures it got before, summed across owners - the yard holding 240
    standards is still 240 whoever they belong to.

    Summed by the database, not in Python. The first version loaded
    every movement as an object and added them up one by one - fine
    with a few hundred, a noticeable wait with a couple of years of
    them, and every store screen asks for this several times over.
    Three grouped sums come back as a few hundred rows however long
    the ledger grows. The arithmetic is exactly what it was:
      in / adjust        -> +qty at location
      lost               -> -qty at from_location
      out/return/transfer -> -qty at from_location, +qty at location
    """
    M = models.StoreMovement
    cols = [M.item_id, M.kind, M.from_location, M.location]
    if by_owner:
        cols.append(M.owner_id)
    base = db.query(*cols, func.sum(M.qty))
    if upto:
        base = base.filter(M.moved_on <= upto)
    rows = base.group_by(*cols).all()
    stock = {}
    def add(key, q):
        stock[key] = stock.get(key, 0) + q
    for row in rows:
        if by_owner:
            item_id, kind, frm, loc, owner, total = row
            # Whose it is travels with the quantity, so a key is only
            # ever added to by movements of the same ownership - hired
            # stock cannot be issued out of the owned pile.
            here, there = (item_id, frm, owner), (item_id, loc, owner)
        else:
            item_id, kind, frm, loc, total = row
            here, there = (item_id, frm), (item_id, loc)
        total = float(total or 0)
        if kind in ("in", "adjust"):
            add(there, total)
        elif kind in ("lost", "hire_return"):
            # Both leave our books where they stood: one written off,
            # the other handed back to the trader who owns it.
            add(here, -total)
        elif kind in ("out", "return", "transfer"):
            add(here, -total)
            add(there, total)
    return stock


def _hire_positions(db: Session, supplier_id: int):
    """Where a trader's material actually stands: {(item_id, location): qty}.

    A hire does not sit in one place. Sixty standards arrive in the yard
    and fifty go up at a site, so settling the hire against the yard
    alone drives it to minus fifty while the site still shows the rest -
    the balance nets out and the ledger stops describing anything real.
    """
    return {(i, loc): q for (i, loc, owner), q in _stock_map(db, by_owner=True).items()
            if owner == supplier_id and q > 1e-9}


def _draw_from(positions, item_id, qty, prefer=""):
    """Take a quantity off a trader's material, from where it is.

    The place the lorry loaded from goes first, then anywhere else
    holding it, so the ledger records the return against the locations
    that really gave it up. Returns [(location, qty)], and shortens the
    positions it was given so several draws can run off one pool.
    """
    out = []
    here = sorted([(loc, q) for (i, loc), q in positions.items() if i == item_id and q > 1e-9],
                  key=lambda x: (x[0] != prefer, x[0]))
    left = qty
    for loc, have in here:
        if left <= 1e-9:
            break
        take = min(have, left)
        positions[(item_id, loc)] = have - take
        out.append((loc, take))
        left -= take
    return out, left


def _has_hired_stock(db: Session, item_id: int) -> bool:
    """Whether any of this material is standing on hire - used only to
    word a message, so a yard with nothing hired is never told its own
    stock is 'ours' as though there were another kind."""
    return db.query(models.StoreMovement.id).filter(
        models.StoreMovement.item_id == item_id,
        models.StoreMovement.owner_id.isnot(None)).first() is not None


def _on_hire(db: Session, supplier_id: int = None, upto: date = None):
    """What is standing on hire right now, and since when.

    Returns one entry per (item, supplier), carrying the quantity still
    out and the date it first came in - which is what turns "60
    standards" into "60 standards, out 34 days".
    """
    stock = _stock_map(db, upto=upto, by_owner=True)
    held = {}
    for (item_id, _loc, owner), qty in stock.items():
        if owner is None or abs(qty) < 1e-9:
            continue
        if supplier_id is not None and owner != supplier_id:
            continue
        held[(item_id, owner)] = held.get((item_id, owner), 0) + qty
    if not held:
        return []
    # When each hire started, taken as the first receipt of that
    # material from that trader - good enough to age a hire by, and it
    # needs no extra record kept in step with the ledger.
    # Any movement that first put the material under the trader's name
    # counts, not receipts alone: stock booked as ours by mistake and
    # corrected later arrives on hire by an adjustment, and a hire with
    # no date beside it is the one nobody chases.
    firsts = dict(
        ((i, o), d) for i, o, d in
        db.query(models.StoreMovement.item_id, models.StoreMovement.owner_id,
                 func.min(models.StoreMovement.moved_on))
          .filter(models.StoreMovement.kind.in_(("in", "adjust")),
                  models.StoreMovement.qty > 0,
                  models.StoreMovement.owner_id.isnot(None))
          .group_by(models.StoreMovement.item_id, models.StoreMovement.owner_id).all())
    items = {i.id: i for i in db.query(models.StoreItem).all()}
    sups = {s.id: s for s in db.query(models.Supplier).all()}
    today = _dubai_today()
    out = []
    for (item_id, owner), qty in held.items():
        it, sup = items.get(item_id), sups.get(owner)
        since = firsts.get((item_id, owner))
        out.append({
            "item_id": item_id,
            "code": it.code if it else "", "name": it.name if it else "(removed)",
            "unit": it.unit if it else "", "item_type": it.item_type if it else "",
            "supplier_id": owner, "supplier": sup.name if sup else "(removed)",
            "qty": round(qty, 2),
            "since": since.isoformat() if since else "",
            "days": (today - since).days if since else 0,
        })
    out.sort(key=lambda r: (r["supplier"].lower(), r["name"].lower()))
    return out


def _supplier_key(name: str) -> str:
    """Fold a supplier name to a comparison key: lower case, punctuation
    dropped, spacing collapsed, and the usual trading suffixes removed.
    "AL RAHA TRADING LLC", "Al-Raha Trading" and "al raha  trading llc."
    all land on "al raha", so one supplier is one record."""
    s = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower())
    s = " ".join(s.split())
    for suffix in (" llc", " l l c", " trading", " general trading", " co", " company",
                   " est", " establishment", " fzc", " fze", " ltd", " limited"):
        while s.endswith(suffix):
            s = s[: -len(suffix)].strip()
    return s


def _tidy_supplier_name(name: str) -> str:
    """Store the name the way it should be read: each word capitalised,
    but abbreviations people write in capitals (LLC, FZE, ADNOC) kept."""
    keep = {"llc", "fze", "fzc", "uae", "adnoc", "gi", "pvc", "upvc", "ppr", "opc"}
    out = []
    for w in " ".join((name or "").split()).split(" "):
        if not w:
            continue
        out.append(w.upper() if w.lower() in keep else w[0].upper() + w[1:].lower())
    return " ".join(out)


def _find_or_create_supplier(db, name, contact_person="", phone=""):
    """Look a supplier up by its folded key, creating it the first time.
    Contact details fill in as they are learned: a blank phone today is
    filled by tomorrow's delivery note, but an existing one is never
    overwritten with an empty box."""
    key = _supplier_key(name)
    if not key:
        return None
    sup = db.query(models.Supplier).filter(models.Supplier.name_key == key).first()
    if not sup:
        sup = models.Supplier(name=_tidy_supplier_name(name), name_key=key,
                              contact_person=_proper_name((contact_person or "").strip()),
                              phone=(phone or "").strip(), active=True)
        db.add(sup)
        db.flush()
        return sup
    if contact_person and contact_person.strip():
        sup.contact_person = _proper_name(contact_person.strip())
    if phone and phone.strip():
        sup.phone = phone.strip()
    return sup


@app.get("/store/suppliers")
def list_suppliers(db: Session = Depends(get_db),
                    user: models.User = Depends(require_any_screen("store", "requests", "approvals"))):
    # Everything a purchase order prints, so choosing a supplier on the
    # LPO screen fills the TRN, address and terms rather than asking for
    # them again.
    return [{"id": s.id, "name": s.name, "contact_person": s.contact_person or "",
             "phone": s.phone or "", "notes": s.notes or "",
             "trn": s.trn or "", "email": s.email or "",
             "payment_terms": s.payment_terms or ""}
            for s in db.query(models.Supplier).filter(models.Supplier.active == True)  # noqa: E712
                       .order_by(models.Supplier.name).all()]


# Everything a purchase order prints. A supplier saved from the master
# screen carries all of it or none of it: half a record is only found
# later, with an order already waiting to go out.
SUPPLIER_REQUIRED = (
    ("name", "the supplier's name"),
    ("contact_person", "a contact person"),
    ("phone", "a phone number"),
    ("trn", "the TRN"),
    ("email", "an email address"),
    ("payment_terms", "payment terms"),
)


def _check_supplier_complete(payload):
    missing = [label for field, label in SUPPLIER_REQUIRED
               if not (getattr(payload, field, "") or "").strip()]
    if missing:
        raise HTTPException(status_code=400, detail="Still needed: " + ", ".join(missing) + ".")


@app.post("/store/suppliers")
def save_supplier(payload: schemas.SupplierIn, db: Session = Depends(get_db),
                   user: models.User = Depends(require_any_screen("store", "requests", "approvals"))):
    _check_supplier_complete(payload)
    sup = _find_or_create_supplier(db, payload.name, payload.contact_person, payload.phone)
    if payload.notes:
        sup.notes = payload.notes
    # The details a purchase order needs, editable from the supplier
    # screen as well as learned from the orders themselves.
    for field in ("trn", "address", "email", "payment_terms"):
        v = (getattr(payload, field, "") or "").strip()
        if v:
            setattr(sup, field, v)
    db.commit()
    return {"id": sup.id, "name": sup.name, "contact_person": sup.contact_person or "",
            "phone": sup.phone or ""}


@app.put("/store/suppliers/{supplier_id}")
def update_supplier(supplier_id: int, payload: schemas.SupplierIn,
                     db: Session = Depends(get_db),
                     user: models.User = Depends(require_any_screen("store", "requests", "approvals"))):
    """Edit a supplier in place. Renaming recomputes the folded key and
    refuses a name that would collide with another supplier - two
    records silently becoming aliases of each other is how contact
    numbers get lost."""
    sup = db.query(models.Supplier).filter(models.Supplier.id == supplier_id).first()
    if not sup:
        raise HTTPException(status_code=404, detail="Supplier not found.")
    _check_supplier_complete(payload)
    name = _proper_name((payload.name or "").strip())
    key = _supplier_key(name)
    clash = db.query(models.Supplier).filter(models.Supplier.name_key == key,
                                              models.Supplier.id != supplier_id).first()
    if clash:
        raise HTTPException(status_code=400,
            detail=f'That name matches the existing supplier "{clash.name}".')
    sup.name = _tidy_supplier_name(name)
    sup.name_key = key
    sup.contact_person = _proper_name((payload.contact_person or "").strip())
    sup.phone = (payload.phone or "").strip()
    # These three were accepted and then dropped on the floor: an edit
    # that changed a TRN or the payment terms saved neither, and the old
    # value stayed on every order printed afterwards.
    sup.trn = (payload.trn or "").strip()
    sup.email = (payload.email or "").strip()
    sup.payment_terms = (payload.payment_terms or "").strip()
    if (payload.address or "").strip():
        sup.address = payload.address.strip()
    if payload.notes is not None:
        sup.notes = payload.notes
    db.commit()
    return {"id": sup.id, "name": sup.name, "contact_person": sup.contact_person,
            "phone": sup.phone}


@app.post("/store/request-lines/{line_id}/decision")
def decide_request_line(line_id: int, payload: schemas.LineDecisionIn,
                         db: Session = Depends(get_db),
                         user: models.User = Depends(require_screen("approvals"))):
    """Approve or reject one material without touching the rest.

    The office often wants nine of ten materials and not the tenth. The
    request itself then follows its lines: rejected outright only when
    every material is turned down, approved once anything is approved,
    and left waiting while decisions are still outstanding."""
    if payload.decision not in ("approved", "rejected", "pending"):
        raise HTTPException(status_code=400, detail="Decision must be approved, rejected or pending.")
    line = db.query(models.MaterialRequestLine).filter(
        models.MaterialRequestLine.id == line_id).first()
    if not line:
        raise HTTPException(status_code=404, detail="Request line not found.")
    if payload.decision == "rejected":
        if (line.qty_received or 0) > 0:
            raise HTTPException(status_code=400,
                detail="Some of this has already arrived, so it can't be rejected now.")
        if line.supplier_id:
            raise HTTPException(status_code=400,
                detail="This has already been ordered from a supplier, so it can't be rejected now.")
    line.status = payload.decision
    line.reject_reason = (payload.reason or "").strip() if payload.decision == "rejected" else ""

    mr = line.request
    states = [l.status or "pending" for l in mr.lines]
    if all(s == "rejected" for s in states):
        mr.status = "rejected"
    elif mr.status in ("pending", "approved", "rejected"):
        # Anything approved moves the request forward; otherwise it waits.
        mr.status = "approved" if any(s == "approved" for s in states) else "pending"
    db.commit()
    log_action(db, user.id, "request_line_decision",
               f"{mr.ref} line {line_id} {payload.decision}")
    return _mr_out(mr)


@app.post("/store/request-lines/{line_id}/link-item")
def link_line_item(line_id: int, payload: schemas.LinkLineItemIn,
                    db: Session = Depends(get_db),
                    user: models.User = Depends(require_any_screen("requests", "approvals"))):
    """Attach a store item to a line that was typed as free text.

    Someone asks for "Cushions", which isn't in the catalogue yet. The
    request is fine, but the delivery can't be received into stock
    because there's nothing to count it against. Rather than a dead end
    at the delivery modal, the keeper adds it to the item list from
    there and the line is linked to it."""
    line = db.query(models.MaterialRequestLine).filter(
        models.MaterialRequestLine.id == line_id).first()
    if not line:
        raise HTTPException(status_code=404, detail="Request line not found.")
    item = db.query(models.StoreItem).filter(models.StoreItem.id == payload.item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found.")
    line.item_id = item.id
    if not line.unit:
        line.unit = item.unit
    db.commit()
    return {"ok": True, "item_id": item.id, "code": item.code}


@app.get("/store/items", response_model=list[schemas.StoreItemOut])
def list_store_items(active_only: bool = True, db: Session = Depends(get_db),
                      user: models.User = Depends(require_screen("store"))):
    q = db.query(models.StoreItem)
    if active_only:
        q = q.filter(models.StoreItem.active == True)  # noqa: E712
    return q.order_by(models.StoreItem.code).all()


# Recognising a material from its name. Units follow UN/CEFACT Rec 20
# symbols (t, kg, m, m2, m3, L) plus Rec 21 packaging (bag, drum, roll).
# Rules run top to bottom, first match wins, so the specific ones
# (welding rod -> box) sit above the general ones (rod -> kg). A rule
# only fires on whole words, so "sanding disc" never matches "sand".
UNIT_RULES = [
    (("cement", "gypsum powder", "grout", "plaster", "mortar", "adhesive powder", "tile adhesive", "white cement", "putty"), "bag", "powders are bought by the bag"),
    (("rebar", "rebars", "reinforcement", "tor steel", "tmt"), "t", "rebar is bought by the tonne"),
    (("sand", "aggregate", "gravel", "sweet soil", "crush", "readymix", "ready mix", "concrete"), "m3", "loose material is measured in cubic metres"),
    (("nail", "nails", "screw", "screws", "binding wire"), "kg", "loose fixings are bought by weight"),
    (("cable", "wire", "conduit", "trunking", "hose", "rope", "chain", "gi pipe", "pvc pipe", "ppr pipe", "upvc", "duct", "tube pipe"), "m", "run material is measured by the metre"),
    (("paint", "primer", "thinner", "curing compound", "admixture", "bitumen", "sealer", "chemical", "diesel", "petrol", "oil", "waterproofing liquid"), "L", "liquids are measured in litres"),
    (("plywood", "gypsum board", "mdf", "gi sheet", "cement board", "shutter ply", "marine ply"), "sheet", "boards are counted in sheets"),
    (("mesh roll", "geotextile", "membrane", "felt", "polythene", "shade net", "hessian", "insulation roll"), "roll", "rolled goods are counted in rolls"),
    (("welding rod", "electrode", "welding electrodes"), "box", "welding rods come by the box"),
    (("silicone", "sealant cartridge", "pu foam", "gun foam"), "tube", "cartridges are counted in tubes"),
    (("glove", "gloves", "boot", "boots", "goggle", "goggles"), "pair", "safety wear comes in pairs"),
]


def _suggest_unit(name: str):
    words = " " + " ".join((name or "").lower().replace("/", " ").replace("-", " ").split()) + " "
    for keys, unit, reason in UNIT_RULES:
        for k in keys:
            if f" {k} " in words or (k.endswith(" ") and k in words):
                return unit, k, reason
    return None, None, None


@app.get("/store/items/suggest-units")
def suggest_units(db: Session = Depends(get_db),
                   user: models.User = Depends(require_screen("store"))):
    """Walk the whole catalogue and propose a standard unit for every
    material whose name identifies it - cement to bags, rebar to tonnes,
    cable to metres. Nothing is changed here: the keeper reviews the
    list and applies only the rows they agree with."""
    out = []
    for it in db.query(models.StoreItem).filter(models.StoreItem.active == True).all():  # noqa: E712
        unit, matched, reason = _suggest_unit(it.name)
        if unit and unit.lower() != (it.unit or "").lower().strip():
            out.append({"id": it.id, "code": it.code, "name": it.name,
                        "current": it.unit, "suggested": unit,
                        "matched": matched, "reason": reason})
    return {"suggestions": out}


@app.post("/store/items/apply-units")
def apply_units(payload: schemas.ApplyUnitsIn, db: Session = Depends(get_db),
                 user: models.User = Depends(require_screen("store"))):
    """Apply the unit changes the keeper ticked in the review."""
    done = 0
    for ch in payload.changes:
        it = db.query(models.StoreItem).filter(models.StoreItem.id == ch.id).first()
        if it and ch.unit and ch.unit.strip():
            it.unit = ch.unit.strip()
            done += 1
    db.commit()
    return {"updated": done}


def _next_item_code(db):
    """ITM1, ITM2... The keeper never invents a code; existing items keep
    whatever code they were given."""
    used = {i.code for i in db.query(models.StoreItem).all()}
    n = 1
    while f"ITM{n}" in used:
        n += 1
    return f"ITM{n}"


def _clean_export_qty(v):
    """400.0 -> 400, 7.5 -> 7.5 - counts never carry a fake decimal."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return str(int(f)) if f == int(f) else str(f)


def _person_name(s: str) -> str:
    """A person's name, tidied: "akhil", "AKHIL" and "Akhil" all become
    "Akhil", so the same person can't appear three ways in a list. Only
    fully-capitalised words are folded, so "Mohammed A K" keeps its
    initials."""
    out = []
    for w in " ".join((s or "").split()).split(" "):
        if not w:
            continue
        if len(w) > 1 and w == w.upper() and any(c.isalpha() for c in w):
            w = w.lower()
        out.append(w[0].upper() + w[1:])
    return " ".join(out)


def _proper_name(s: str) -> str:
    """First letter of each word up, the rest untouched, so "cushions"
    becomes "Cushions" while "cement OPC 42.5" keeps OPC as OPC. The
    server does this itself: names arrive from several paths and only
    some of them pass through the browser's tidying."""
    return " ".join(w[0].upper() + w[1:] if w else w
                    for w in " ".join((s or "").split()).split(" "))


def _find_or_create_item(db, name, unit, item_type):
    """Return the catalogue item for a typed-in material, creating it if
    it's genuinely new.

    A material asked for by name only ("Cushions") used to live as loose
    text on one request: it couldn't be received into stock, couldn't be
    given out, and the next person asking typed it slightly differently.
    Adding it to the list at request time means it has a code, a unit,
    and a history from the moment it is first asked for.
    """
    clean = " ".join((name or "").split())
    if not clean:
        return None
    existing = db.query(models.StoreItem).filter(
        func.lower(models.StoreItem.name) == clean.lower()).first()
    if existing:
        return existing
    it = models.StoreItem(code=_next_item_code(db), name=_proper_name(clean),
                          unit=(unit or "pcs").strip() or "pcs",
                          item_type=item_type if item_type in ("consumable", "asset", "rental") else "consumable",
                          category="", reorder_level=0, active=True)
    db.add(it)
    db.flush()
    return it


@app.post("/store/items", response_model=schemas.StoreItemOut)
def upsert_store_item(payload: schemas.StoreItemIn, db: Session = Depends(get_db),
                       user: models.User = Depends(require_screen("store"))):
    # Validate on the server, not just in the browser - a blank code or
    # name creates an item that can't be identified in any report.
    code = (payload.code or "").strip()
    name = _proper_name((payload.name or "").strip())
    if not name:
        raise HTTPException(status_code=400, detail="Item needs a name.")
    if not code:
        # Added by name with no code: if the store already knows a
        # material by that name, this is that material, not a twin.
        # Two "Cement OPC 50kg" rows split the stock between them and
        # every report showed half the truth. The request screen already
        # matched typed names this way; the material form now does too.
        twin = (db.query(models.StoreItem)
                  .filter(func.lower(func.trim(models.StoreItem.name)) == name.lower()).first())
        code = twin.code if twin else _next_item_code(db)
    if payload.item_type == "returnable":
        payload.item_type = "asset"        # retired type, folded into assets
    if payload.item_type not in ("consumable", "asset", "rental"):
        raise HTTPException(status_code=400, detail="Item type must be consumable, asset or rental.")
    if payload.reorder_level < 0:
        raise HTTPException(status_code=400, detail="Reorder level can't be negative.")
    payload.code, payload.name = code, name

    existing = db.query(models.StoreItem).filter(models.StoreItem.code == code).first()
    # Opening stock is not a column on the item - it is a receipt, so it
    # lands in the ledger like every other quantity and can be traced.
    opening = float(payload.opening_qty or 0)
    opening_where = (payload.opening_location or "").strip()
    fields = payload.dict()
    fields.pop("opening_qty", None)
    fields.pop("opening_location", None)

    is_new = existing is None
    if existing:
        for k, v in fields.items():
            setattr(existing, k, v)
        existing.active = True
    else:
        existing = models.StoreItem(**fields)
        db.add(existing)
    db.commit()
    db.refresh(existing)

    # "Already have" applies to a new material, and to one that is on
    # the list but has never been received - which is every material in
    # a store that started on paper. Once anything has come in, the box
    # is ignored: the count is for the start, not a way to top up.
    never_received = existing.id not in _ever_stocked(db)
    # A quantity typed here has no trader against it, so it can only be
    # ours. Letting it through for a material marked rental is what put
    # hired scaffolding into the owned pile and left the hire list
    # empty - the type says what kind of thing it is, never whose.
    if (is_new or never_received) and opening > 0 and existing.item_type == "rental":
        raise HTTPException(status_code=400,
            detail='This material is marked Rental (hired in), so a quantity here would be '
                   'recorded as ours and would not show on hire. Use "Add stock to the store '
                   'or a site" above, set "Whose is it" to hired, and name the trader - or '
                   'change the type to Asset if it is ours.')
    if (is_new or never_received) and opening > 0:
        db.add(models.StoreMovement(
            item_id=existing.id, kind="in", qty=opening,
            location=opening_where, from_location="",
            moved_on=_dubai_today(), supplier="", incharge="",
            reference="Opening stock", notes="Opening stock - already held when the material was added",
            created_by=user.id))
        db.commit()
        log_action(db, user.id, "store_movement",
                   f"opening {opening:g} {existing.unit} {existing.code}")

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
                 user: models.User = Depends(require_screen("store"))):
    """
    Stock on hand. Without a location, one row per item showing the
    central-store quantity, how much is out at sites, and the total -
    plus a low flag when it has fallen to or below its reorder level.
    """
    items = db.query(models.StoreItem).filter(models.StoreItem.active == True).all()  # noqa: E712
    stock = _stock_map(db)
    stocked = _ever_stocked(db)
    # Whose it is, alongside how much there is. Only built when anything
    # is actually on hire, so a store that never hires pays nothing for
    # the question and sees no column about it.
    owned_map = _stock_map(db, by_owner=True)
    hired_any = any(o is not None and abs(q) > 1e-9 for (_i, _l, o), q in owned_map.items())
    sup_names = ({s.id: s.name for s in db.query(models.Supplier).all()} if hired_any else {})
    rows = []
    for it in items:
        at_central = stock.get((it.id, CENTRAL), 0)
        # A consumable is never counted as standing at a site - see
        # HELD_AT_SITE. Its total is what is in the store, because what
        # went out to a site has been used.
        if _held_at_site(it):
            out_total = sum(v for (iid, loc), v in stock.items() if iid == it.id and loc != CENTRAL)
            by_site = {loc: v for (iid, loc), v in stock.items() if iid == it.id and loc != CENTRAL and v}
        else:
            out_total, by_site = 0, {}
        if location is not None:
            qty = stock.get((it.id, location), 0) if (location == CENTRAL or _held_at_site(it)) else 0
            rows.append({"item_id": it.id, "code": it.code, "name": it.name,
                          "category": it.category, "unit": it.unit, "item_type": it.item_type,
                          "qty": round(qty, 2), "reorder_level": it.reorder_level,
                          "low": qty <= it.reorder_level and it.reorder_level > 0 and it.id in stocked})
        else:
            row = {"item_id": it.id, "code": it.code, "name": it.name,
                   "category": it.category, "unit": it.unit, "item_type": it.item_type,
                   "central": round(at_central, 2), "out_at_sites": round(out_total, 2),
                   "total": round(at_central + out_total, 2),
                   "by_site": {k: round(v, 2) for k, v in by_site.items()},
                   "reorder_level": it.reorder_level,
                   "low": at_central <= it.reorder_level and it.reorder_level > 0 and it.id in stocked}
            if hired_any:
                # Split the same total by owner, so a row can never read
                # as 240 of ours when 60 of them belong to a trader.
                ours = hired = 0.0
                by_owner = {}
                for (iid, loc, owner), qty in owned_map.items():
                    if iid != it.id or abs(qty) < 1e-9:
                        continue
                    if not _held_at_site(it) and loc != CENTRAL:
                        continue
                    if owner is None:
                        ours += qty
                    else:
                        hired += qty
                        nm = sup_names.get(owner, "(removed)")
                        by_owner[nm] = round(by_owner.get(nm, 0) + qty, 2)
                row["owned"] = round(ours, 2)
                row["hired"] = round(hired, 2)
                row["hired_from"] = by_owner
            rows.append(row)
    return rows


@app.get("/store/hire")
def store_on_hire(supplier_id: int = None, db: Session = Depends(get_db),
                   user: models.User = Depends(require_any_screen("store", "approvals"))):
    """Everything standing on hire, grouped by the trader it belongs to.

    This is the exposure: what is out, from whom, and how long it has
    been out. A hire nobody has looked at for four months is the one
    that turns into an argument.
    """
    rows = _on_hire(db, supplier_id=supplier_id)
    by_sup = {}
    for r in rows:
        g = by_sup.setdefault(r["supplier_id"], {
            "supplier_id": r["supplier_id"], "supplier": r["supplier"],
            "items": [], "lines": 0, "total_qty": 0.0, "longest_days": 0})
        g["items"].append(r)
        g["lines"] += 1
        g["total_qty"] += r["qty"]
        g["longest_days"] = max(g["longest_days"], r["days"])
    groups = sorted(by_sup.values(), key=lambda g: -g["longest_days"])
    for g in groups:
        g["total_qty"] = round(g["total_qty"], 2)
    return {"suppliers": groups,
            "lines": sum(g["lines"] for g in groups),
            "any": bool(groups)}


@app.post("/store/hire/in")
def store_hire_in(payload: schemas.HireInIn, db: Session = Depends(get_db),
                   user: models.User = Depends(require_screen("store"))):
    """Book hired material in, from a delivery note or against an order.

    Hired stock arrives exactly like bought stock, at a location, on a
    date - the one difference being that it stays the trader's, so it
    is booked under his name and has to leave again under a return
    note. Both routes in end at the same ledger entry; an order number
    simply travels with it as the reference.
    """
    if "storekeeper" not in effective_permissions(user):
        raise HTTPException(status_code=403,
            detail="Only the store keeper records stock in and out.")
    sup = _find_or_create_supplier(db, payload.supplier_name)
    if not sup:
        raise HTTPException(status_code=400, detail="Name the trader it is hired from.")
    if not payload.lines:
        raise HTTPException(status_code=400, detail="Add at least one material.")
    if payload.received_on > _dubai_today():
        raise HTTPException(status_code=400, detail="Date is in the future.")
    reference = (payload.reference or "").strip()
    if payload.order_id:
        o = db.query(models.PurchaseOrder).filter(
            models.PurchaseOrder.id == payload.order_id).first()
        if not o:
            raise HTTPException(status_code=400, detail="That purchase order was not found.")
        reference = reference or o.ref
    booked = []
    for l in payload.lines:
        if (l.qty or 0) <= 0:
            continue
        item = db.query(models.StoreItem).filter(models.StoreItem.id == l.item_id).first()
        if not item:
            raise HTTPException(status_code=400, detail="One of those materials is not on file.")
        m = models.StoreMovement(
            item_id=item.id, kind="in", qty=l.qty,
            location=payload.location or CENTRAL,
            owner_id=sup.id, supplier=sup.name,
            incharge=_person_name(payload.incharge or ""),
            reference=reference, notes=(l.notes or payload.notes or ""),
            moved_on=payload.received_on, created_by=user.id)
        db.add(m)
        booked.append(f"{l.qty} {item.unit} {item.code}")
    if not booked:
        raise HTTPException(status_code=400, detail="Every line was blank.")
    db.commit()
    log_action(db, user.id, "hire_in",
               f"from {sup.name}: " + ", ".join(booked[:6])
               + (f" and {len(booked) - 6} more" if len(booked) > 6 else ""))
    return {"ok": True, "supplier": sup.name, "supplier_id": sup.id,
            "lines": len(booked),
            "detail": f"{len(booked)} material(s) booked in on hire from {sup.name}."}


SHORT_REASONS = ("lost", "damaged", "on site")


def _next_return_ref(db):
    """RN-0001 upward, read from the references themselves rather than
    from row ids - a cancelled note keeps its number and a cleared table
    starts again at one."""
    best = 0
    for (ref,) in db.query(models.HireReturn.ref).all():
        m = re.match(r"RN-(\d+)$", (ref or "").strip())
        if m:
            best = max(best, int(m.group(1)))
    return f"RN-{best + 1:04d}"


def _return_dict(r, db=None):
    return {
        "id": r.id, "ref": r.ref, "supplier_id": r.supplier_id,
        "supplier": r.supplier_name,
        "return_date": r.return_date.isoformat() if r.return_date else "",
        "from_location": r.from_location or "", "driver": r.driver or "",
        "vehicle": r.vehicle or "", "status": r.status, "notes": r.notes or "",
        "received_by": r.received_by or "",
        "confirmed_on": r.confirmed_on.isoformat() if r.confirmed_on else "",
        "lines": [{"id": l.id, "item_id": l.item_id, "description": l.description,
                   "unit": l.unit, "qty_on_hire": l.qty_on_hire,
                   "qty_returned": l.qty_returned, "qty_short": l.qty_short,
                   "short_reason": l.short_reason or "", "notes": l.notes or "",
                   "still_on_hire": round((l.qty_on_hire or 0) - (l.qty_returned or 0)
                                          - (l.qty_short or 0), 2)}
                  for l in r.lines],
        "total_returned": round(sum(l.qty_returned or 0 for l in r.lines), 2),
        "total_short": round(sum(l.qty_short or 0 for l in r.lines), 2),
    }


@app.get("/store/returns")
def list_hire_returns(status: str = "", db: Session = Depends(get_db),
                       user: models.User = Depends(require_any_screen("store", "approvals"))):
    """The return register - every note raised, newest first."""
    q = db.query(models.HireReturn).options(joinedload(models.HireReturn.lines))
    if status:
        q = q.filter(models.HireReturn.status == status)
    rows = q.order_by(models.HireReturn.id.desc()).limit(500).all()
    return [{"id": r.id, "ref": r.ref, "supplier": r.supplier_name,
             "return_date": r.return_date.isoformat() if r.return_date else "",
             "status": r.status, "driver": r.driver or "",
             "lines": len(r.lines),
             "total_returned": round(sum(l.qty_returned or 0 for l in r.lines), 2),
             "total_short": round(sum(l.qty_short or 0 for l in r.lines), 2),
             "received_by": r.received_by or "",
             "confirmed_on": r.confirmed_on.isoformat() if r.confirmed_on else ""}
            for r in rows]


@app.get("/store/returns/{return_id}")
def get_hire_return(return_id: int, db: Session = Depends(get_db),
                     user: models.User = Depends(require_any_screen("store", "approvals"))):
    r = db.query(models.HireReturn).filter(models.HireReturn.id == return_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Return note not found.")
    return _return_dict(r, db)


def _fill_return_lines(db, r, lines, supplier_id):
    """Replace a note's lines, refusing to send back more than is on
    hire. The quantity on hire is read here rather than trusted from the
    screen - the position may have moved since the note was opened."""
    held = {h["item_id"]: h["qty"] for h in _on_hire(db, supplier_id=supplier_id)}
    for l in list(r.lines):
        db.delete(l)
    db.flush()
    kept = 0
    for l in lines:
        going = (l.qty_returned or 0) + (l.qty_short or 0)
        if going <= 0:
            continue
        item = db.query(models.StoreItem).filter(
            models.StoreItem.id == l.item_id).first() if l.item_id else None
        on_hire = held.get(l.item_id, 0) if l.item_id else (l.qty_on_hire or 0)
        if l.item_id and going > on_hire + 1e-9:
            name = item.name if item else "that material"
            raise HTTPException(status_code=400,
                detail=f"{name}: only {round(on_hire, 2)} on hire, "
                       f"but the note accounts for {round(going, 2)}.")
        if (l.qty_short or 0) > 0 and (l.short_reason or "").strip().lower() not in SHORT_REASONS:
            name = item.name if item else "a material"
            raise HTTPException(status_code=400,
                detail=f"{name}: say why {round(l.qty_short, 2)} are short "
                       f"- lost, damaged, or on site.")
        db.add(models.HireReturnLine(
            return_id=r.id, item_id=l.item_id,
            description=(l.description or (item.name if item else "")).strip(),
            unit=(l.unit or (item.unit if item else "pcs")),
            qty_on_hire=on_hire, qty_returned=l.qty_returned or 0,
            qty_short=l.qty_short or 0,
            short_reason=(l.short_reason or "").strip().lower(),
            notes=(l.notes or "").strip()))
        kept += 1
    if not kept:
        raise HTTPException(status_code=400,
            detail="Nothing on the note - enter what is going back, or what is short.")


@app.post("/store/returns")
def create_hire_return(payload: schemas.HireReturnIn, db: Session = Depends(get_db),
                        user: models.User = Depends(require_any_screen("store", "approvals"))):
    """Open a return note for one trader's material.

    Nothing moves yet. The note is the paper that travels with the
    lorry; the stock comes off our books only when it comes back
    signed, because until then we are still holding it.
    """
    sup = None
    if payload.supplier_id:
        sup = db.query(models.Supplier).filter(
            models.Supplier.id == payload.supplier_id).first()
    if not sup and (payload.supplier_name or "").strip():
        sup = _find_or_create_supplier(db, payload.supplier_name)
    if not sup:
        raise HTTPException(status_code=400, detail="Which trader is it going back to?")
    r = models.HireReturn(
        ref=_next_return_ref(db), supplier_id=sup.id, supplier_name=sup.name,
        return_date=payload.return_date or _dubai_today(),
        from_location=payload.from_location or "", driver=(payload.driver or "").strip(),
        vehicle=(payload.vehicle or "").strip(), notes=(payload.notes or "").strip(),
        status="draft", created_by=user.id)
    db.add(r)
    db.flush()
    _fill_return_lines(db, r, payload.lines, sup.id)
    db.commit()
    db.refresh(r)
    log_action(db, user.id, "hire_return_raised",
               f"{r.ref} to {sup.name} ({len(r.lines)} line(s))")
    return _return_dict(r, db)


@app.put("/store/returns/{return_id}")
def update_hire_return(return_id: int, payload: schemas.HireReturnIn,
                        db: Session = Depends(get_db),
                        user: models.User = Depends(require_any_screen("store", "approvals"))):
    """Correct a note before it is signed off. Once confirmed it is the
    record of what both sides agreed, so it stops being editable."""
    r = db.query(models.HireReturn).filter(models.HireReturn.id == return_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Return note not found.")
    if r.status == "confirmed":
        raise HTTPException(status_code=400,
            detail="This note is signed and settled - raise a new one for anything further.")
    if r.status == "cancelled":
        raise HTTPException(status_code=400, detail="This note was cancelled.")
    if payload.return_date:
        r.return_date = payload.return_date
    r.from_location = payload.from_location or ""
    r.driver = (payload.driver or "").strip()
    r.vehicle = (payload.vehicle or "").strip()
    r.notes = (payload.notes or "").strip()
    _fill_return_lines(db, r, payload.lines, r.supplier_id)
    db.commit()
    db.refresh(r)
    log_action(db, user.id, "hire_return_edited", f"{r.ref} ({len(r.lines)} line(s))")
    return _return_dict(r, db)


@app.post("/store/returns/{return_id}/issue")
def issue_hire_return(return_id: int, db: Session = Depends(get_db),
                       user: models.User = Depends(require_any_screen("store", "approvals"))):
    """Printed and gone with the driver. Still nothing off the books."""
    r = db.query(models.HireReturn).filter(models.HireReturn.id == return_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Return note not found.")
    if r.status != "draft":
        raise HTTPException(status_code=400, detail=f"{r.ref} is already {r.status}.")
    r.status = "issued"
    db.commit()
    log_action(db, user.id, "hire_return_issued", r.ref)
    return {"ok": True, "detail": f"{r.ref} is out with the driver."}


@app.post("/store/returns/{return_id}/confirm")
def confirm_hire_return(return_id: int, payload: schemas.HireReturnConfirmIn,
                         db: Session = Depends(get_db),
                         user: models.User = Depends(require_any_screen("store", "approvals"))):
    """The signed copy is back: now the stock moves.

    What went back leaves under 'hire_return'; what is short and not
    coming back is written off under 'lost'. Both take the material off
    our books, and both say whose it was, so the trader's position
    closes at the figure his own man signed for.
    """
    r = (db.query(models.HireReturn).options(joinedload(models.HireReturn.lines))
           .filter(models.HireReturn.id == return_id).first())
    if not r:
        raise HTTPException(status_code=404, detail="Return note not found.")
    if r.status == "confirmed":
        raise HTTPException(status_code=400, detail=f"{r.ref} is already settled.")
    if r.status == "cancelled":
        raise HTTPException(status_code=400, detail="This note was cancelled.")
    when = payload.confirmed_on or _dubai_today()
    if when > _dubai_today():
        raise HTTPException(status_code=400, detail="Date is in the future.")
    # Check the whole note before writing any of it: half a return
    # posted is worse than none, because nobody can see which half.
    held = {h["item_id"]: h["qty"] for h in _on_hire(db, supplier_id=r.supplier_id)}
    for l in r.lines:
        if not l.item_id:
            continue
        going = (l.qty_returned or 0) + (l.qty_short or 0)
        if going > held.get(l.item_id, 0) + 1e-9:
            raise HTTPException(status_code=400,
                detail=f"{l.description}: only {round(held.get(l.item_id, 0), 2)} still on hire, "
                       f"but this note settles {round(going, 2)}. Edit the note first.")
    # Taken off where it actually stands - the place the lorry loaded
    # from first, then anywhere else holding it. One movement per
    # location, so no location is driven negative to make a total agree.
    positions = _hire_positions(db, r.supplier_id)
    prefer = r.from_location or CENTRAL
    for l in r.lines:
        if not l.item_id:
            continue
        for qty, kind in (((l.qty_returned or 0), "hire_return"),
                          ((l.qty_short or 0), "lost")):
            if qty <= 0:
                continue
            draws, unmet = _draw_from(positions, l.item_id, qty, prefer)
            if unmet > 1e-9:
                raise HTTPException(status_code=400,
                    detail=f"{l.description}: {round(unmet, 2)} cannot be accounted for - "
                           "the position has moved since this note was written. Edit it first.")
            for loc, took in draws:
                db.add(models.StoreMovement(
                    item_id=l.item_id, kind=kind, qty=took,
                    from_location=loc, location=loc,
                    owner_id=r.supplier_id, supplier=r.supplier_name,
                    incharge=_person_name(payload.received_by or r.driver or ""),
                    reference=r.ref,
                    notes=(f"{l.short_reason} on {r.ref}" if kind == "lost"
                           else f"returned on {r.ref}"),
                    moved_on=when, created_by=user.id))
    r.status = "confirmed"
    r.received_by = (payload.received_by or "").strip()
    r.confirmed_on = when
    if (payload.notes or "").strip():
        r.notes = ((r.notes or "") + "\n" + payload.notes.strip()).strip()
    db.commit()
    short = round(sum(l.qty_short or 0 for l in r.lines), 2)
    log_action(db, user.id, "hire_return_confirmed",
               f"{r.ref} to {r.supplier_name}: "
               f"{round(sum(l.qty_returned or 0 for l in r.lines), 2)} returned"
               + (f", {short} short" if short else ""))
    return {"ok": True, "detail": f"{r.ref} settled." +
            (f" {short} item(s) recorded short." if short else ""),
            "total_short": short}


@app.post("/store/returns/{return_id}/cancel")
def cancel_hire_return(return_id: int, db: Session = Depends(get_db),
                        user: models.User = Depends(require_any_screen("store", "approvals"))):
    """Cancelled, never deleted - the number stays used, like an order."""
    r = db.query(models.HireReturn).filter(models.HireReturn.id == return_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Return note not found.")
    if r.status == "confirmed":
        raise HTTPException(status_code=400,
            detail="This note is signed and settled - it cannot be cancelled.")
    r.status = "cancelled"
    db.commit()
    log_action(db, user.id, "hire_return_cancelled", r.ref)
    return {"ok": True, "detail": f"{r.ref} cancelled."}


@app.post("/store/hire/reassign")
def reassign_stock_owner(payload: dict = Body(...), db: Session = Depends(get_db),
                          user: models.User = Depends(require_screen("store"))):
    """Put stock under the right name when it went in under the wrong one.

    Material booked as ours that is really a trader's, or the reverse.
    Nothing physically moves, so nothing is received or issued: the
    quantity is taken off one name and put on the other at the same
    place, as two corrections that both say why. The ledger keeps the
    mistake and the fix rather than pretending neither happened.
    """
    if "storekeeper" not in effective_permissions(user) and user.role != "admin":
        raise HTTPException(status_code=403, detail="Only someone who records stock can do this.")
    try:
        item_id = int((payload or {}).get("item_id") or 0)
        qty = float((payload or {}).get("qty") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Check the material and quantity.")
    item = db.query(models.StoreItem).filter(models.StoreItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=400, detail="Pick a material.")
    if qty <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be more than zero.")

    where = ((payload or {}).get("location") or "").strip()
    if where:
        site = db.query(models.Site).filter(func.lower(models.Site.code) == where.lower()).first()
        if not site:
            raise HTTPException(status_code=400, detail=f'"{where}" is not a site on file.')
        where = site.code

    def _owner(key_id, key_name):
        oid = (payload or {}).get(key_id)
        if oid:
            o = db.query(models.Supplier).filter(models.Supplier.id == int(oid)).first()
            if not o:
                raise HTTPException(status_code=400, detail="That trader is not on file.")
            return o
        nm = ((payload or {}).get(key_name) or "").strip()
        return _find_or_create_supplier(db, nm) if nm else None

    frm = _owner("from_owner_id", "from_owner_name")     # None = ours
    to = _owner("to_owner_id", "to_owner_name")          # None = ours
    if (frm.id if frm else None) == (to.id if to else None):
        raise HTTPException(status_code=400, detail="It is already under that name.")

    have = _stock_map(db, by_owner=True).get((item.id, where, frm.id if frm else None), 0)
    if qty > have + 1e-9:
        whose = f"hired from {frm.name}" if frm else "ours"
        place = where or "the central store"
        raise HTTPException(status_code=400,
            detail=f"Only {round(have, 2)} {item.unit} of {item.name} ({whose}) at {place}.")

    was = frm.name if frm else "ours"
    now = to.name if to else "ours"
    note = f"Owner corrected: {was} -> {now}"
    for signed, owner in ((-qty, frm), (qty, to)):
        db.add(models.StoreMovement(
            item_id=item.id, kind="adjust", qty=signed,
            location=where, from_location=where,
            owner_id=owner.id if owner else None,
            supplier=owner.name if owner else "",
            incharge=user.full_name or user.username,
            reference="Owner correction", notes=note,
            moved_on=_dubai_today(), created_by=user.id))
    db.commit()
    log_action(db, user.id, "stock_owner_corrected",
               f"{qty:g} {item.unit} {item.code} at {where or 'central store'}: {was} -> {now}")
    return {"ok": True,
            "detail": f"{qty:g} {item.unit or ''} {item.name} is now "
                      + (f"on hire from {now}." if to else "recorded as ours.")}


@app.get("/store/movements", response_model=list[schemas.StoreMovementOut])
def list_store_movements(item_id: int = None, location: str = None, kind: str = None,
                          date_from: str = None, date_to: str = None, limit: int = 500,
                          db: Session = Depends(get_db),
                          user: models.User = Depends(require_screen("store"))):
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
                        user: models.User = Depends(require_screen("store"))):
    # Seeing stock and moving stock are different things. A site login
    # can look at what the store holds so it knows what to ask for, but
    # one central keeper records every receipt and issue - a site
    # engineer issuing to himself is exactly the record nobody can
    # later reconcile.
    if "storekeeper" not in effective_permissions(user):
        raise HTTPException(status_code=403,
            detail="Only the store keeper records stock in and out. "
                   "Ask an admin to tick 'Records stock in and out' on your login, "
                   "or raise a material request instead.")
    item = db.query(models.StoreItem).filter(models.StoreItem.id == payload.item_id).first()
    if not item:
        raise HTTPException(status_code=400, detail="Item not found.")
    if payload.kind not in ("in", "out", "return", "adjust", "transfer", "lost", "hire_return"):
        raise HTTPException(status_code=400, detail="Unknown movement type.")
    if payload.owner_id is not None:
        owner = db.query(models.Supplier).filter(models.Supplier.id == payload.owner_id).first()
        if not owner:
            raise HTTPException(status_code=400, detail="That hire supplier is not on file.")
    if payload.qty <= 0 and payload.kind != "adjust":
        raise HTTPException(status_code=400, detail="Quantity must be more than zero.")
    if payload.moved_on > date.today():
        raise HTTPException(status_code=400, detail="Date is in the future.")
    # Moving something from a place to the same place changes nothing but
    # leaves a confusing entry in the ledger, so reject it outright.
    if payload.kind in ("return", "transfer") and payload.from_location == payload.location:
        where = payload.location or "the central store"
        raise HTTPException(status_code=400,
            detail=f"'From' and 'To' are both {where} - pick different places.")

    # Don't allow issuing more than is actually held - a negative balance
    # means the ledger no longer describes anything real.
    if payload.kind in ("out", "return", "transfer", "lost", "hire_return"):
        # Asked of the owner's own pile, not the heap. Forty hired
        # standards standing beside two hundred of ours cannot be issued
        # as if there were two hundred and forty of the trader's - which
        # is precisely the confusion that loses hired kit.
        have = _stock_map(db, by_owner=True).get(
            (item.id, payload.from_location, payload.owner_id), 0)
        if payload.qty > have + 1e-9:
            where = payload.from_location or "the central store"
            whose = ""
            if payload.owner_id is not None:
                nm = db.query(models.Supplier).filter(
                    models.Supplier.id == payload.owner_id).first()
                whose = f" hired from {nm.name}" if nm else " hired"
            else:
                whose = " of ours" if _has_hired_stock(db, item.id) else ""
            raise HTTPException(status_code=400,
                detail=f"Only {round(have, 2)} {item.unit} of {item.name}{whose} "
                       f"available at {where}.")

    m = models.StoreMovement(**payload.dict(), created_by=user.id)
    # Names are tidied wherever they enter the system, not only on the
    # screen that happened to be used - people type AKHIL, akhil and
    # Akhil, and all three are the same man.
    m.incharge = _person_name(getattr(m, "incharge", "") or "")
    if payload.kind == "in" and (payload.supplier or "").strip():
        sup = _find_or_create_supplier(db, payload.supplier)
        if sup:
            m.supplier = sup.name
    db.add(m)
    db.commit()
    db.refresh(m)
    log_action(db, user.id, "store_movement",
               f"{payload.kind} {payload.qty} {item.unit} {item.code}")

    # Writing stock off and correcting a count are the two movements
    # that change the books without anything arriving or leaving, so
    # the office is told by mail as well as by the ledger.
    if payload.kind in ("lost", "adjust"):
        # Whatever happens in there, the movement stands. A stock
        # write-off failing because a mail server misbehaved would be a
        # far worse fault than a missing email.
        try:
            _email_stock_writeoff(db, user, m, item)
        except Exception as e:
            try:
                log_action(db, user.id, "stock_alert_email_failed",
                           f"{item.code}: {type(e).__name__}: {e}")
            except Exception:
                pass

    d = schemas.StoreMovementOut.model_validate(m).model_dump()
    d["item_code"], d["item_name"], d["unit"] = item.code, item.name, item.unit
    return d


STOCK_ALERT_TO = os.environ.get("STOCK_ALERT_TO", "info@infinia.ae")


def _email_stock_writeoff(db, user, m, item):
    """Tell the office a quantity changed with nothing moving.

    Sent quietly: if mail is not configured, or the server refuses, the
    movement still stands and the reason is recorded in the activity
    log. A write-off must never fail because of a mail server.
    """
    held = _stock_map(db).get((item.id, m.location or ""), 0)
    what = "written off as lost or damaged" if m.kind == "lost" else "corrected after a count"
    where = m.location or m.from_location or "the central store"
    body = (
        f"{item.name} ({item.code}) was {what}.\n\n"
        f"Quantity : {m.qty:g} {item.unit}\n"
        f"Where    : {where}\n"
        f"Date     : {m.moved_on.isoformat() if m.moved_on else ''}\n"
        f"Entered  : {user.full_name or user.username}\n"
        f"Reason   : {(m.notes or '').strip() or 'none given'}\n\n"
        f"Stock now held at {where}: {held:g} {item.unit}\n\n"
        f"This message was sent by the Infinia store system."
    )
    subject = (f"Stock {'write-off' if m.kind == 'lost' else 'correction'}: "
               f"{item.name} - {m.qty:g} {item.unit}")
    sent, why = mailer.send(STOCK_ALERT_TO, subject, body)
    if not sent:
        log_action(db, user.id, "stock_alert_email_failed", f"{item.code}: {why}")


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
                  user: models.User = Depends(require_screen("store"))):
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
        stocked = _ever_stocked(db)
        for i in items.values():
            if not i.active or not i.reorder_level or i.id not in stocked: continue
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
            # Consumables are used where they are sent, so they are not
            # held at a site - see HELD_AT_SITE.
            if not _held_at_site(i): continue
            rows.append({"site": loc, "code": i.code, "name": i.name,
                          "unit": i.unit, "qty": round(qty, 2), "item_type": i.item_type})
        return {"title": "Stock held at sites", "rows": sorted(rows, key=lambda r: (r["site"], r["code"]))}

    if kind == "purchases":
        agg = {}
        for m in moves(["in"]):
            i = items.get(m.item_id)
            if not i: continue
            a = agg.setdefault(i.id, {"code": i.code, "name": i.name, "unit": i.unit,
                                       "qty": 0, "deliveries": 0, "last_arrived": None,
                                       "suppliers": set()})
            a["qty"] += m.qty
            a["deliveries"] += 1
            if m.moved_on and (not a["last_arrived"] or m.moved_on > a["last_arrived"]):
                a["last_arrived"] = m.moved_on
            if m.supplier: a["suppliers"].add(m.supplier)
        rows = [{**v, "qty": round(v["qty"], 2),
                  "last_arrived": v["last_arrived"].isoformat() if v["last_arrived"] else "-",
                  "suppliers": ", ".join(sorted(v["suppliers"])) or "not recorded"}
                for v in agg.values()]
        return {"title": "Purchases received", "rows": sorted(rows, key=lambda r: -r["qty"])}

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
            if not i or i.item_type not in ("returnable", "asset") or loc == CENTRAL or qty <= 0: continue
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
        today = _dubai_today()
        rows = []
        for i in items.values():
            if not i.active or i.item_type != "rental": continue
            at = {loc: q for (iid, loc), q in stock.items() if iid == i.id and q}
            where = ", ".join(f"{loc or 'store'}: {q:g}" for loc, q in sorted(at.items())) or "-"
            days = (today - i.rental_start).days if i.rental_start else None
            est = round(days * (i.rental_rate or 0), 2) if (days is not None and i.rental_period == "day") else None
            rows.append({"code": i.code, "name": i.name, "supplier": i.rental_supplier,
                          "rate": i.rental_rate, "period": i.rental_period,
                          "start": i.rental_start.isoformat() if i.rental_start else "",
                          "due": i.rental_due.isoformat() if i.rental_due else "",
                          "days_on_hire": days, "est_cost": est, "where": where,
                          "overdue": bool(i.rental_due and i.rental_due < today)})
        return {"title": "Rented equipment", "rows": sorted(rows, key=lambda r: (not r["overdue"], r["due"] or ""))}

    def _lost_by_item(iid):
        return sum(m.qty for m in db.query(models.StoreMovement)
                    .filter(models.StoreMovement.item_id == iid,
                             models.StoreMovement.kind == "lost").all())

    if kind == "assets":
        # Owned only - hired equipment has its own register, so the two
        # never get added together and mistaken for company property.
        rows = []
        for i in items.values():
            if not i.active or i.item_type not in ("asset", "returnable"): continue
            at = {loc: q for (iid, loc), q in stock.items() if iid == i.id and q}
            lost = _lost_by_item(i.id)
            # A machine the company owns but has none of - never bought,
            # or all written off - is not a line on an asset register.
            if not at and not lost:
                continue
            # No "where" column: the store and site figures already say
            # where it is, and which site is the At Sites report's job.
            rows.append({"code": i.code, "name": i.name, "unit": i.unit,
                          "in_store": round(at.get("", 0), 2),
                          "at_sites": round(sum(q for loc, q in at.items() if loc), 2),
                          "total": round(sum(at.values()), 2),
                          "written_off": round(lost, 2) if lost else 0})
        return {"title": "Owned assets and equipment", "rows": sorted(rows, key=lambda r: r["code"])}

    if kind == "hired":
        # Everything currently on hire: what, from whom, where it is, and
        # anything already lost or damaged that the supplier will charge
        # for. Who it came from and when are read from the deliveries
        # themselves - the item's own rental fields are only filled in if
        # someone typed them, so relying on them left the columns empty
        # even though the store knew the answer.
        arrivals = (db.query(models.StoreMovement)
                      .filter(models.StoreMovement.kind == "in")
                      .order_by(models.StoreMovement.moved_on.asc()).all())
        first_in, last_supplier = {}, {}
        for m in arrivals:
            if m.item_id not in first_in and m.moved_on:
                first_in[m.item_id] = m.moved_on
            if (m.supplier or "").strip():
                last_supplier[m.item_id] = m.supplier.strip()
        rows = []
        for i in items.values():
            if not i.active or i.item_type != "rental": continue
            at = {loc: q for (iid, loc), q in stock.items() if iid == i.id and q}
            lost = _lost_by_item(i.id)
            on_hire = round(sum(at.values()), 2)
            if on_hire <= 0 and not lost: continue
            since = i.rental_start or first_in.get(i.id)
            rows.append({"code": i.code, "name": i.name, "unit": i.unit,
                          "hired_from": i.rental_supplier or last_supplier.get(i.id) or "not recorded",
                          "on_hire": on_hire,
                          "in_store": round(at.get("", 0), 2),
                          "by_site": {loc: round(q, 2) for loc, q in at.items() if loc},
                          "lost_damaged": round(lost, 2) if lost else 0,
                          "since": since.isoformat() if since else "-",
                          "due_back": i.rental_due.isoformat() if i.rental_due else "no date set",
                          "days_out": (date.today() - since).days if since else ""})
        return {"title": "Equipment on hire", "rows": sorted(rows, key=lambda r: (r["hired_from"], r["code"]))}

    if kind == "lost":
        rows = []
        q = db.query(models.StoreMovement).filter(models.StoreMovement.kind == "lost")
        if d1: q = q.filter(models.StoreMovement.moved_on >= d1)
        if d2: q = q.filter(models.StoreMovement.moved_on <= d2)
        for m in q.order_by(models.StoreMovement.moved_on.desc()).all():
            i = items.get(m.item_id)
            if not i: continue
            sup = ""
            if i.item_type == "rental":
                sup = i.rental_supplier or (db.query(models.StoreMovement)
                        .filter(models.StoreMovement.item_id == i.id,
                                models.StoreMovement.kind == "in",
                                models.StoreMovement.supplier != "")
                        .order_by(models.StoreMovement.moved_on.desc())
                        .with_entities(models.StoreMovement.supplier).scalar() or "")
            rows.append({"date": m.moved_on.isoformat(), "code": i.code, "name": i.name,
                          "type": i.item_type, "qty": round(m.qty, 2), "unit": i.unit,
                          "where": m.from_location or "central store",
                          "hired_from": sup or ("not recorded" if i.item_type == "rental" else "owned"),
                          "reason": m.notes or "not given"})
        return {"title": "Lost and damaged", "rows": rows}

    # default: full stock position
    # Only materials that actually hold stock, or that someone has set a
    if kind not in ("stock", "low", "by_site", "purchases", "usage", "assets",
                    "lost", "hired", "rentals"):
        raise HTTPException(status_code=400,
            detail=f"There is no report called '{kind}'.")
    # reorder level on (so a watched item shows even when it hits zero).
    # The catalogue can run to thousands of materials; listing every one
    # at zero makes the few real ones impossible to find.
    rows = []
    stocked = _ever_stocked(db)
    for i in items.values():
        if not i.active: continue
        c = stock.get((i.id, CENTRAL), 0)
        per_site = ({loc: round(v, 2) for (iid, loc), v in stock.items()
                     if iid == i.id and loc != CENTRAL and v}
                    if _held_at_site(i) else {})
        o = sum(per_site.values())
        if c == 0 and o == 0 and not i.reorder_level:
            continue
        rows.append({"code": i.code, "name": i.name, "unit": i.unit,
                      "item_type": i.item_type, "in_store": round(c, 2),
                      "at_sites": round(o, 2), "total": round(c + o, 2),
                      # Which site holds what, so a row can open into a
                      # proper breakdown instead of one crowded cell.
                      "by_site": per_site,
                      "low": bool(i.reorder_level and i.id in stocked and c <= i.reorder_level)})
    return {"title": "Current stock", "rows": sorted(rows, key=lambda r: r["code"])}


# ---------------------------------------------------------------------
# MATERIAL REQUESTS (store keeper -> office)
# ---------------------------------------------------------------------
def _next_mr_ref(db: Session) -> str:
    """MR-0001, MR-0002... counted from the highest reference already
    issued rather than from the row id.

    The database's own id counter does not go back when rows are
    deleted. Reading it would have numbered the first request after a
    store clearance MR-0001 and the very next one MR-0084. Reading the
    references themselves keeps them in step, and keeps numbering
    unbroken if a single request is ever deleted.
    """
    best = 0
    for (ref,) in db.query(models.MaterialRequest.ref).all():
        tail = (ref or "").rsplit("-", 1)[-1]
        if tail.isdigit():
            best = max(best, int(tail))
    return f"MR-{best + 1:04d}"


def _mr_out(mr: models.MaterialRequest) -> dict:
    d = schemas.MaterialRequestOut.model_validate(mr).model_dump()
    # Supplier travels with the request so the list can show who to
    # chase without a second call per row.
    sup = getattr(mr, "supplier", None)
    d["supplier"] = ({"id": sup.id, "name": sup.name,
                      "contact_person": sup.contact_person or "", "phone": sup.phone or ""}
                     if sup else None)
    d["expected_on"] = mr.expected_on.isoformat() if getattr(mr, "expected_on", None) else None
    for i, ln in enumerate(mr.lines):
        d["lines"][i]["item_code"] = ln.item.code if ln.item else ""
        d["lines"][i]["item_name"] = ln.item.name if ln.item else (ln.description or "")
        ls = ln.supplier
        d["lines"][i]["status"] = ln.status or "pending"
        d["lines"][i]["reject_reason"] = ln.reject_reason or ""
        d["lines"][i]["supplier"] = ({"id": ls.id, "name": ls.name,
                                       "contact_person": ls.contact_person or "",
                                       "phone": ls.phone or ""} if ls else None)
    return d


@app.get("/store/requests")
def list_material_requests(status: str = None, site: str = None,
                            date_from: str = None, date_to: str = None,
                            db: Session = Depends(get_db),
                            user: models.User = Depends(require_any_screen("requests", "approvals"))):
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
                             user: models.User = Depends(require_any_screen("requests", "approvals"))):
    lines = [l for l in payload.lines if l.qty_requested and l.qty_requested > 0]
    if not lines:
        raise HTTPException(status_code=400, detail="Add at least one material with a quantity.")
    for l in lines:
        if not l.item_id and not (l.description or "").strip():
            raise HTTPException(status_code=400, detail="Every line needs an item or a description.")

    # Repeat-click guard. A browser fault once let the save succeed while
    # the confirmation crashed, so the keeper kept clicking Send and one
    # request became thirty. If an identical request - same person, same
    # site, same materials and quantities - already exists from the last
    # few minutes, hand that one back instead of minting another.
    # Compared by what the material is called, not by its number: a
    # material typed by name has no number when the request is sent but
    # does once it is saved, so the second click of a double-click never
    # matched the first and one press still made two requests.
    item_names = {i.id: (i.name or "") for i in db.query(models.StoreItem).all()}
    def _line_key(item_id, description, qty):
        name = " ".join(((description or "") or item_names.get(item_id or 0, "")).lower().split())
        return (name, round(qty or 0, 3))
    sig = sorted(_line_key(l.item_id, l.description, l.qty_requested) for l in lines)
    recent = (db.query(models.MaterialRequest)
                .filter(models.MaterialRequest.requested_by == payload.requested_by,
                        models.MaterialRequest.site == (payload.site or ""),
                        models.MaterialRequest.status == "pending")
                .order_by(models.MaterialRequest.id.desc()).limit(5).all())
    now = datetime.now(timezone.utc)
    def _recent(ts):
        if not ts:
            return True   # a pending twin with no timestamp is still a twin
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (now - ts) <= timedelta(minutes=10)
    for prev in recent:
        if not _recent(prev.created_at):
            continue
        prev_sig = sorted(_line_key(pl.item_id, pl.description, pl.qty_requested) for pl in prev.lines)
        if prev_sig == sig:
            out = _mr_out(prev)
            out["duplicate_of"] = prev.ref
            return out

    mr = models.MaterialRequest(
        ref=_next_mr_ref(db), site=payload.site,
        requested_by=_person_name(payload.requested_by),
        needed_by=payload.needed_by, urgency=payload.urgency, notes=payload.notes,
        requested_on=payload.requested_on or date.today(), created_by=user.id,
    )
    db.add(mr)
    db.flush()
    created = []
    for l in lines:
        # The requester's own unit wins. Overwriting "tonne" with the
        # catalogue's "pcs" quietly changed what was being asked for -
        # the office read 25 pcs of rebar when 25 tonne was meant. The
        # catalogue unit is only a fallback for a line that has none.
        unit = (l.unit or "").strip()
        if not unit and l.item_id:
            it = db.query(models.StoreItem).filter(models.StoreItem.id == l.item_id).first()
            if it:
                unit = it.unit
        unit = unit or "pcs"
        item_id = l.item_id
        # A material typed by name joins the item list here and now, with
        # its own generated code, so it can be received into stock, given
        # out, reported on, and picked from the list next time.
        if not item_id:
            it = _find_or_create_item(db, l.description, unit, l.item_type)
            if it:
                item_id = it.id
                created.append(f"{it.code} - {it.name}")
        db.add(models.MaterialRequestLine(request_id=mr.id, item_id=item_id,
                                           description=_proper_name(l.description),
                                           qty_requested=l.qty_requested,
                                           qty_approved=l.qty_approved or 0, unit=unit,
                                           est_cost=l.est_cost or 0, notes=l.notes,
                                           purpose=l.purpose))
    db.commit()
    db.refresh(mr)
    log_action(db, user.id, "material_request", f"{mr.ref} - {len(lines)} item(s)")
    out = _mr_out(mr)
    if created:
        out["new_items"] = created
    return out


@app.post("/store/requests/{req_id}/status")
def set_material_request_status(req_id: int, payload: schemas.MaterialRequestStatusIn,
                                 db: Session = Depends(get_db),
                                 user: models.User = Depends(require_screen("approvals"))):
    mr = db.query(models.MaterialRequest).filter(models.MaterialRequest.id == req_id).first()
    if not mr:
        raise HTTPException(status_code=404, detail="Request not found")
    # Four steps, not six: "arranging" and "lpo_sent" both just meant
    # "the office is dealing with it", which made the screen busier
    # without telling anyone anything they could act on. Old values are
    # still accepted so existing requests keep working.
    allowed = ("pending", "approved", "ordered", "partial", "delivered",
               "closed", "rejected", "arranging", "lpo_sent", "received")
    if payload.status not in allowed:
        raise HTTPException(status_code=400, detail=f"Status must be one of: {', '.join(allowed)}")
    mr.status = payload.status
    # Approving or rejecting the request settles every material that is
    # still waiting - otherwise the request reads "approved" while its
    # materials are all still pending, and the screen keeps asking to
    # approve something it already approved.
    if payload.status == "approved":
        for l in mr.lines:
            if (l.status or "pending") == "pending":
                l.status = "approved"
    elif payload.status == "rejected":
        for l in mr.lines:
            if (l.status or "pending") == "pending" and not (l.qty_received or 0):
                l.status = "rejected"
                l.reject_reason = (payload.office_remark or "").strip()
    if payload.office_remark:
        mr.office_remark = payload.office_remark
    # Ordering is when the supplier becomes known. Capturing it here
    # gives the keeper a name and number to chase, instead of a request
    # that says "ordered" and nothing else.
    if getattr(payload, "supplier", None) and payload.supplier.strip():
        sup = _find_or_create_supplier(db, payload.supplier,
                                        getattr(payload, "contact_person", "") or "",
                                        getattr(payload, "phone", "") or "")
        if sup:
            # A request can be split across traders on price - cement
            # from one, rebar from another. If specific lines were named,
            # only those go to this supplier; otherwise the whole request
            # does. The request-level supplier is kept as a shortcut only
            # while every line agrees.
            line_ids = getattr(payload, "line_ids", None) or []
            targets = [l for l in mr.lines
                       if (not line_ids or l.id in line_ids)
                       and (l.status or "pending") != "rejected"]
            for l in targets:
                l.supplier_id = sup.id
                # Buying something is approving it. Leaving the line
                # "pending" made the screen contradict itself: ordered
                # from Newstar, yet still asking Approve or Reject.
                l.status = "approved"
            sup_ids = {l.supplier_id for l in mr.lines}
            mr.supplier_id = sup.id if len(sup_ids) == 1 and None not in sup_ids else None
    if getattr(payload, "expected_on", None):
        mr.expected_on = payload.expected_on
    mr.closed_on = date.today() if payload.status in ("delivered", "received", "closed", "rejected") else None
    db.commit()
    log_action(db, user.id, "material_request_status", f"{mr.ref} -> {payload.status}")
    return {"ok": True, "status": mr.status}


@app.delete("/store/requests/{req_id}")
def delete_material_request(req_id: int, db: Session = Depends(get_db),
                             user: models.User = Depends(require_screen("approvals"))):
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
                             user: models.User = Depends(require_any_screen("requests", "approvals"))):
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
    today = _dubai_today()
    reqs = db.query(models.MaterialRequest).order_by(models.MaterialRequest.id.desc()).all()

    if kind == "overdue":
        rows = [{"ref": m.ref, "site": m.site, "requested_on": m.requested_on.isoformat(),
                  "needed_by": m.needed_by.isoformat() if m.needed_by else "",
                  "days_late": (today - m.needed_by).days if m.needed_by else 0,
                  "status": m.status, "urgency": m.urgency, "items": len(m.lines)}
                 for m in reqs
                 if m.needed_by and m.needed_by < today and m.status not in ("delivered", "received", "closed", "rejected")]
        return {"title": "Overdue material requests", "rows": sorted(rows, key=lambda r: -r["days_late"])}

    if kind == "outstanding":
        rows = []
        for m in reqs:
            if m.status in ("delivered", "received", "closed", "rejected"):
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


@app.get("/export/{month_year}/attendance-needed")
def export_attendance_needed(month_year: str, token: str, emp_nos: str = "",
                              format: str = "pdf", note: str = "",
                              db: Session = Depends(get_db)):
    """A reminder sheet listing the workers whose cards are unfinished.

    Built from the same missing-day check the Error Check screen shows,
    narrowed to whichever workers were ticked, so a foreman gets one
    page naming only his men and the exact days each is short.

    Under /export/, a prefix nginx already forwards.
    """
    auth.get_download_user_from_token(token, db)
    wanted = {n.strip() for n in emp_nos.split(",") if n.strip()}

    cycle_start, cycle_end, _ = pcyc.cycle_bounds_for(
        datetime.strptime(f"25 {month_year}", "%d %B %Y").date())
    last_day = min(cycle_end, _dubai_today() - timedelta(days=1))
    all_dates = []
    d = cycle_start
    while d <= last_day:
        all_dates.append(d)
        d += timedelta(days=1)

    rows = db.query(models.DailyRow).filter(models.DailyRow.month_year == month_year).all()
    dates_by_emp = {}
    for r in rows:
        dates_by_emp.setdefault(r.emp_no, set()).add(r.full_date)

    employees = [e for e in db.query(models.Employee).filter(models.Employee.active == True).all()
                 if employed_during(e, cycle_start, cycle_end)]
    workers = []
    for emp in sorted(employees, key=lambda e: e.emp_no):
        if wanted and emp.emp_no not in wanted:
            continue
        entered_days = dates_by_emp.get(emp.emp_no, set())
        missing = [d for d in all_dates
                   if (emp.terminated_on is None or d <= emp.terminated_on) and d not in entered_days]
        if not missing:
            continue
        workers.append({"emp_no": emp.emp_no, "name": emp.name, "trade": emp.trade or "",
                        "days": ", ".join(d.strftime("%d %b") for d in missing)})
    if not workers:
        raise HTTPException(status_code=404, detail="Nothing missing for those workers.")

    cycle_label = f"{cycle_start.strftime('%d %b')} - {cycle_end.strftime('%d %b %Y')}"
    safe = "".join(c if c.isalnum() else "_" for c in month_year)
    if format == "excel":
        buf = export_web.build_error_check_excel(cycle_label, workers, note)
        return StreamingResponse(
            buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=Attendance_Needed_{safe}.xlsx"})
    buf = export_web.build_error_check_pdf(cycle_label, workers, note)
    return StreamingResponse(buf, media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Attendance_Needed_{safe}.pdf"})


# ---- Purchase orders -------------------------------------------------
LPO_START_NO = 20260100          # the first number this system issues

DEFAULT_LPO_TERMS = (
    "1. We reserve rights to terminate this order without prior notice and reject any items "
    "delivered based on this order\n"
    "2. The Purchase Order shall become invalid if the materials/ services are not supplied "
    "within the delivery date or if the supplier fails to comply with the Quantity and "
    "Specifications in this order."
)
# The set used for materials bought against a confirmed sample - the
# two clauses the newer sheets carry, ahead of the standard two.
MATERIAL_LPO_TERMS = (
    "1. Material should supply as per the sample confirmed by site engineer\n"
    "2. Any damage or broken of material due to quality issue need to be replaced by the "
    "supplier immediately\n"
    "3. We reserve rights to terminate this order without prior notice and reject any items "
    "delivered based on this order\n"
    "4. The Purchase Order shall become invalid if the materials/ services are not supplied "
    "within the delivery date or if the supplier fails to comply with the Quantity and "
    "Specifications in this order."
)

RENTAL_LPO_TERMS = DEFAULT_LPO_TERMS + (
    "\n3.Lost Price/Damage of materials will be calculated as per the Return Note confirmed "
    "by the Project Engineer\n"
    "4. Weekly release of Invoice Mandatory\n"
    "5. Mail confirmation on Returning of materials & closing of LPO from supplier side Mandatory"
)


def _next_lpo_no(db):
    """The next order number. Carries on from the highest already issued,
    so numbering is unbroken even if a record is deleted, and starts at
    the number the company asked for."""
    last = db.query(func.max(models.PurchaseOrder.po_no)).scalar()
    return max(int(last or 0) + 1, LPO_START_NO)


SUPPLIER_HEADERS = ["Name", "Contact Person", "Phone", "TRN", "Email", "Payment Terms", "Notes"]


# ---------------------------------------------------------------------
# OPENING STOCK - what the store already held on the day it went live
# ---------------------------------------------------------------------
# The store started on paper with shelves already full. Typing each
# material in through "Material arrived" would take a day and invite
# mistakes, so the whole count goes in from one sheet: every material
# listed, a quantity typed against each one held, imported once.
#
# Each quantity lands in the ledger as a receipt marked "Opening stock",
# so it is traceable like everything else. A material that has already
# been received is skipped - the count is for the day the store starts,
# and importing the sheet twice must not double it.
OPENING_HEADERS = ["Code", "Material", "Unit", "Type", "Quantity in store"]


@app.get("/export/store/opening-template")
def download_opening_template(token: str, db: Session = Depends(get_db)):
    auth.get_download_user_from_token(token, db)
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    items = (db.query(models.StoreItem).filter(models.StoreItem.active == True)  # noqa: E712
               .order_by(models.StoreItem.name).all())
    received = _ever_stocked(db)
    wb = Workbook(); ws = wb.active; ws.title = "Opening stock"
    ws.append(OPENING_HEADERS)
    for i, h in enumerate(OPENING_HEADERS, start=1):
        c = ws.cell(row=1, column=i)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=export_web.BRAND_RED)
        c.alignment = Alignment(horizontal="center")
    for it in items:
        # A material already received shows what it holds and is left
        # alone by the import; the column to fill is blank for the rest.
        ws.append([it.code, it.name, it.unit or "", (it.item_type or "consumable").title(),
                   None if it.id not in received else "already received"])
    for col, w in zip("ABCDE", (12, 48, 10, 14, 20)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="Opening_stock.xlsx"'})


@app.post("/store/items/opening")
def record_opening_stock(payload: dict = Body(...), db: Session = Depends(get_db),
                         user: models.User = Depends(require_screen("store"))):
    """A few materials put into the store by hand, any time.

    The shelves on day one, or something that came in without a delivery
    note. Each quantity is a receipt in the ledger like any delivery, so
    it is traceable. The type chosen on the line is saved on the
    material, so a hired generator added here does not sit among the
    consumables.

    It goes where it actually is - the yard or a site - and under whose
    name it actually stands. Marking a line 'rental' only says what kind
    of thing it is; it does not say whose, and without a trader named
    the quantity was quietly booked as ours and never appeared on hire.
    """
    if "storekeeper" not in effective_permissions(user) and user.role != "admin":
        raise HTTPException(status_code=403, detail="Only someone who records stock can count opening stock.")
    lines = (payload or {}).get("lines") or []
    if not lines:
        raise HTTPException(status_code=400, detail="Add at least one material with a quantity.")

    where = ((payload or {}).get("location") or "").strip()
    if where:
        site = db.query(models.Site).filter(
            func.lower(models.Site.code) == where.lower()).first()
        if not site:
            raise HTTPException(status_code=400,
                detail=f'"{where}" is not a site on file. Pick one from the list, or leave it '
                       "on the central store.")
        where = site.code

    owner = None
    owner_id = (payload or {}).get("owner_id")
    owner_name = ((payload or {}).get("owner_name") or "").strip()
    if owner_id:
        owner = db.query(models.Supplier).filter(models.Supplier.id == int(owner_id)).first()
        if not owner:
            raise HTTPException(status_code=400, detail="That hire supplier is not on file.")
    elif owner_name:
        owner = _find_or_create_supplier(db, owner_name)

    # The trap this closes: a line marked 'rental' with nobody named was
    # booked as ours, so 150 hired ledgers sat in the owned pile and the
    # hire list stayed empty - which is exactly what it was added to stop.
    if not owner and any((l.get("item_type") or "").strip() == "rental" for l in lines):
        raise HTTPException(status_code=400,
            detail="A line is marked Rental (hired in) but no trader is named. "
                   "Say who it is hired from, or set the type to Asset if it is ours.")

    today = _dubai_today()
    added, skipped = [], []
    for l in lines:
        try:
            item_id, qty = int(l.get("item_id") or 0), float(l.get("qty") or 0)
        except (TypeError, ValueError):
            continue
        if not item_id or qty <= 0:
            continue
        it = db.query(models.StoreItem).filter(models.StoreItem.id == item_id).first()
        if not it:
            continue
        kind = (l.get("item_type") or "").strip()
        if kind in ("consumable", "asset", "rental") and it.item_type != kind:
            it.item_type = kind
        # The unit picked on the line is the material's unit from here on.
        unit = (l.get("unit") or "").strip()
        if unit and unit != (it.unit or ""):
            it.unit = unit
        db.add(models.StoreMovement(item_id=it.id, kind="in", qty=qty,
                                    location=where or CENTRAL, from_location="",
                                    owner_id=owner.id if owner else None,
                                    moved_on=today, supplier=owner.name if owner else "",
                                    incharge=user.full_name or user.username,
                                    reference="Added by hand",
                                    notes=("Booked in on hire from the Materials panel" if owner
                                           else "Put into the store from the Materials panel"),
                                    created_by=user.id))
        added.append(f"{qty:g} {it.unit or ''} {it.name}".strip())
    db.commit()
    place = f"site {where}" if where else "the central store"
    log_action(db, user.id, "stock_added",
               f"at {place}" + (f", on hire from {owner.name}" if owner else "")
               + ": " + "; ".join(added)[:180])
    detail = ((f"Added to {place}" + (f", on hire from {owner.name}" if owner else "") + ": "
               + ", ".join(added[:6]) + (" ..." if len(added) > 6 else ""))
              if added else "Nothing added.")
    return {"added": added, "skipped": skipped, "detail": detail,
            "location": where, "owner": owner.name if owner else ""}


@app.post("/store/items/opening-import")
async def import_opening_stock(file: UploadFile = File(...), db: Session = Depends(get_db),
                               user: models.User = Depends(require_screen("store"))):
    from openpyxl import load_workbook
    if "storekeeper" not in effective_permissions(user) and user.role != "admin":
        raise HTTPException(status_code=403, detail="Only someone who records stock can import an opening count.")
    data = await file.read()
    try:
        ws = load_workbook(io.BytesIO(data), data_only=True).active
    except Exception:
        raise HTTPException(status_code=400, detail="That file could not be read as a spreadsheet.")
    rows = list(ws.iter_rows(values_only=True))
    head_i = next((i for i, r in enumerate(rows[:10])
                   if any(str(c or "").strip().lower() == "code" for c in r)), None)
    if head_i is None:
        raise HTTPException(status_code=400, detail="The sheet needs the Code column from the opening stock template.")
    header = [str(c or "").strip().lower() for c in rows[head_i]]
    def col(*names):
        for n in names:
            if n in header:
                return header.index(n)
        return None
    i_code, i_name, i_qty = col("code"), col("material", "name"), col("quantity in store", "quantity", "qty")
    if i_qty is None:
        raise HTTPException(status_code=400, detail="The sheet needs a 'Quantity in store' column.")
    by_code = {it.code.lower(): it for it in db.query(models.StoreItem).all()}
    by_name = {" ".join(it.name.lower().split()): it for it in by_code.values()}
    received = _ever_stocked(db)
    today = _dubai_today()
    added, skipped_received, unknown, blank = 0, [], [], 0
    for r in rows[head_i + 1:]:
        raw = r[i_qty] if i_qty < len(r) else None
        if raw in (None, "") or isinstance(raw, str) and not raw.strip().replace(".", "", 1).isdigit():
            blank += 1
            continue
        qty = float(raw)
        if qty <= 0:
            blank += 1
            continue
        code = str(r[i_code] or "").strip().lower() if i_code is not None and i_code < len(r) else ""
        name = " ".join(str(r[i_name] or "").lower().split()) if i_name is not None and i_name < len(r) else ""
        it = by_code.get(code) or by_name.get(name)
        if not it:
            unknown.append(code or name or "?")
            continue
        if it.id in received:
            skipped_received.append(it.code)
            continue
        db.add(models.StoreMovement(item_id=it.id, kind="in", qty=qty, location=CENTRAL, from_location="",
                                    moved_on=today, supplier="", incharge=user.full_name or user.username,
                                    reference="Opening stock", notes="Opening stock - held when the store went live",
                                    created_by=user.id))
        received.add(it.id)
        added += 1
    db.commit()
    log_action(db, user.id, "opening_stock", f"{added} material(s) counted in")
    parts = [f"{added} material(s) counted into the store."]
    if skipped_received:
        parts.append(f"{len(skipped_received)} skipped because they had already been received "
                     f"(record any extra through Material arrived): {', '.join(skipped_received[:8])}"
                     + (" ..." if len(skipped_received) > 8 else ""))
    if unknown:
        parts.append(f"{len(unknown)} not found in the material list: {', '.join(unknown[:8])}"
                     + (" ..." if len(unknown) > 8 else ""))
    return {"added": added, "skipped_received": skipped_received, "unknown": unknown,
            "blank": blank, "detail": " ".join(parts)}


@app.get("/export/store/suppliers/template")
def download_supplier_template(token: str, db: Session = Depends(get_db)):
    """Blank sheet with the columns the supplier import expects, and one
    sample row showing what goes where."""
    auth.get_download_user_from_token(token, db)
    from openpyxl import Workbook
    from openpyxl.styles import Font as F, PatternFill as PF, Alignment as A
    wb = Workbook(); ws = wb.active; ws.title = "Suppliers"
    for i, head in enumerate(SUPPLIER_HEADERS, start=1):
        c = ws.cell(row=1, column=i, value=head)
        c.font = F(bold=True, color="FFFFFF")
        c.fill = PF("solid", fgColor="7B1F1A")
        c.alignment = A(horizontal="center")
        ws.column_dimensions[chr(64 + i)].width = 30 if head == "Name" else 20
    ws.append(["SAMPLE TRADING LLC", "Contact name", "0501234567", "100000000000003",
               "sales@example.ae", "Net 60", "Delete this row before importing"])
    ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf); buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Infinia_Supplier_Template.xlsx"})


@app.get("/export/store/suppliers")
def export_suppliers(token: str, db: Session = Depends(get_db)):
    """The supplier list as a spreadsheet - the same columns the import
    expects, so it can be edited and brought back."""
    auth.get_download_user_from_token(token, db)
    from openpyxl import Workbook
    from openpyxl.styles import Font as F, PatternFill as PF, Alignment as A
    wb = Workbook(); ws = wb.active; ws.title = "Suppliers"
    for i, head in enumerate(SUPPLIER_HEADERS, start=1):
        c = ws.cell(row=1, column=i, value=head)
        c.font = F(bold=True, color="FFFFFF"); c.fill = PF("solid", fgColor="7B1F1A")
        c.alignment = A(horizontal="center")
        ws.column_dimensions[chr(64 + i)].width = 30 if head in ("Name", "Address") else 18
    for s in db.query(models.Supplier).order_by(models.Supplier.name).all():
        ws.append([s.name, s.contact_person or "", s.phone or "", s.trn or "",
                   s.email or "", s.payment_terms or "", s.notes or ""])
    ws.freeze_panes = "A2"
    buf = io.BytesIO()
    # No logo header here: it inserts rows at the top, which pushes the
    # column headings down - and this sheet is meant to be edited and
    # imported straight back, so the first row has to be the headings.
    wb.save(buf); buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Infinia_Suppliers.xlsx"})


@app.post("/store/suppliers/import")
async def import_suppliers(file: UploadFile = File(...), db: Session = Depends(get_db),
                            user: models.User = Depends(require_screen("approvals"))):
    """Bring a supplier list in from a spreadsheet.

    Matched on the name, so running it twice updates rather than
    duplicates. A blank cell leaves what is on record alone - the same
    rule as the worker import, so a partly-filled sheet cannot wipe a
    TRN somebody typed."""
    from openpyxl import load_workbook
    data = await file.read()
    try:
        ws = load_workbook(io.BytesIO(data), data_only=True).active
    except Exception:
        raise HTTPException(status_code=400, detail="That file could not be read as a spreadsheet.")
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise HTTPException(status_code=400, detail="The sheet is empty.")
    # Find the heading row rather than assuming it is the first: a sheet
    # that has been through Excel may carry a title or a logo above it.
    head_i = 0
    for i, row in enumerate(rows[:10]):
        if any(str(c or "").strip().lower() == "name" for c in row):
            head_i = i
            break
    header = [str(c or "").strip().lower() for c in rows[head_i]]
    def col(name):
        try:
            return header.index(name.lower())
        except ValueError:
            return None
    idx = {k: col(k) for k in ("name", "contact person", "phone", "trn", "email", "payment terms", "notes")}
    if idx["name"] is None:
        raise HTTPException(status_code=400, detail="The sheet needs a Name column.")
    created = updated = skipped = 0
    incomplete = []
    for r in rows[head_i + 1:]:
        def get(k):
            i = idx.get(k)
            return str(r[i]).strip() if i is not None and i < len(r) and r[i] not in (None, "") else ""
        name = get("name")
        if not name:
            skipped += 1
            continue
        # A sheet cannot put a half-filled trader on the master either -
        # the same rule the screen enforces, or the quickest way round
        # it would be to import the row instead of typing it.
        short = [label for column, label in (("contact person", "contact person"),
                                             ("phone", "phone"), ("trn", "TRN"),
                                             ("email", "email"), ("payment terms", "payment terms"))
                 if not get(column)]
        if short:
            incomplete.append(f"{name} (no {', '.join(short)})")
            skipped += 1
            continue
        # Whether this trader was already on file has to be asked BEFORE
        # the find-or-create, which gives a new record its id straight
        # away - so every import reported nothing added and everything
        # updated, even a sheet of names never seen before.
        key = _supplier_key(name)
        was_new = not db.query(models.Supplier).filter(models.Supplier.name_key == key).first()
        sup = _find_or_create_supplier(db, name, get("contact person"), get("phone"))
        if not sup:
            skipped += 1
            continue
        for field, key in (("trn", "trn"), ("email", "email"),
                           ("payment_terms", "payment terms"), ("notes", "notes"),
                           ("contact_person", "contact person"), ("phone", "phone")):
            v = get(key)
            if v:
                setattr(sup, field, v)
        created += 1 if was_new else 0
        updated += 0 if was_new else 1
    db.commit()
    log_action(db, user.id, "import_suppliers", f"{created} created, {updated} updated, {skipped} skipped")
    # Naming the rows that were left out, rather than only counting them,
    # so the sheet can be fixed without hunting for which ones fell short.
    note = ""
    if incomplete:
        note = " Left out, needing every column filled: " + "; ".join(incomplete[:8])
        if len(incomplete) > 8:
            note += f"; and {len(incomplete) - 8} more"
        note += "."
    return {"ok": True, "created": created, "updated": updated, "skipped": skipped,
            "incomplete": incomplete,
            "detail": f"{created} added, {updated} updated"
                      + (f", {skipped} row(s) skipped" if skipped else "") + "." + note}


@app.get("/store/requests/{request_id}/summary")
def request_summary(request_id: int, db: Session = Depends(get_db),
                     user: models.User = Depends(auth.get_current_user)):
    """Enough of a request to read it without opening the screen - what
    was asked for, how much, for where, by whom, and where it has got
    to. A notification that says only 'MR-0082 is now ordered' makes
    somebody go and look; this lets them read it where they are."""
    mr = (db.query(models.MaterialRequest)
            .options(joinedload(models.MaterialRequest.lines))
            .filter(models.MaterialRequest.id == request_id).first())
    if not mr:
        raise HTTPException(status_code=404, detail="Request not found.")
    items = {i.id: i for i in db.query(models.StoreItem).all()}
    sups = {s.id: s.name for s in db.query(models.Supplier).all()}
    lines = []
    for l in mr.lines:
        it = items.get(l.item_id)
        lines.append({
            "material": (it.name if it else "") or l.description or "",
            "qty": l.qty_approved or l.qty_requested or 0,
            "unit": l.unit or (it.unit if it else ""),
            "status": l.status or "pending",
            "purpose": l.purpose or "",
            "received": l.qty_received or 0,
            "supplier": sups.get(l.supplier_id, ""),
        })
    return {
        "id": mr.id, "ref": mr.ref, "site": mr.site or "",
        "requested_by": mr.requested_by or "", "status": mr.status or "",
        "urgency": mr.urgency or "normal",
        "needed_by": mr.needed_by.isoformat() if mr.needed_by else "",
        "expected_on": mr.expected_on.isoformat() if mr.expected_on else "",
        "notes": mr.notes or "", "lines": lines,
    }


@app.get("/store/at-site")
def stock_at_site(site: str, db: Session = Depends(get_db),
                   user: models.User = Depends(require_screen("store"))):
    """What a site is already holding.

    Asked when a site is chosen on the give-out screen, so the keeper
    can see what is already there before sending more - the commonest
    way a store ends up with forty bags at a site that needed ten.
    """
    loc = (site or "").strip()
    if not loc:
        return {"site": "", "rows": [], "recent": [], "total_lines": 0}
    stock = _stock_map(db)
    items = {i.id: i for i in db.query(models.StoreItem).all()}
    rows = []
    for (iid, where), qty in stock.items():
        if where != loc or not qty or iid not in items:
            continue
        i = items[iid]
        # Only the things that stay - see HELD_AT_SITE. A consumable
        # sent here has been used, and belongs in "recent" below.
        if not _held_at_site(i):
            continue
        rows.append({"item_id": i.id, "code": i.code, "name": i.name,
                     "unit": i.unit or "", "qty": round(qty, 2),
                     "item_type": i.item_type})
    rows.sort(key=lambda r: r["name"].lower())

    # When a consumable last came here, and how much of it. This is the
    # question the keeper is really asking before sending more cement to
    # 901 - not "how much is standing there", which is none, but "when
    # did they last get some, and how much". Newest first.
    M = models.StoreMovement
    sent = (db.query(M)
              .filter(M.location == loc, M.kind.in_(("in", "out", "transfer")))
              .order_by(M.moved_on.desc(), M.id.desc())
              .limit(600).all())
    recent, seen = [], set()
    for m in sent:
        i = items.get(m.item_id)
        if not i or _held_at_site(i) or i.id in seen or not m.qty:
            continue
        seen.add(i.id)
        recent.append({"item_id": i.id, "code": i.code, "name": i.name,
                       "unit": i.unit or "", "qty": round(m.qty, 2),
                       "on": m.moved_on.isoformat() if m.moved_on else None,
                       "item_type": i.item_type})
    return {"site": loc, "rows": rows, "recent": recent, "total_lines": len(rows)}


@app.get("/store/purchase/pending")
def lpo_pending_lines(db: Session = Depends(get_db),
                       user: models.User = Depends(require_screen("approvals"))):
    """Everything the office has approved and nobody has ordered yet.

    This is the purchase officer's queue: approved lines, still owed,
    with the site and job that asked for them, so an order is raised by
    ticking rather than by typing the whole thing again.
    """
    reqs = (db.query(models.MaterialRequest)
              .options(joinedload(models.MaterialRequest.lines))
              .filter(models.MaterialRequest.status.notin_(["rejected", "closed"]))
              .order_by(models.MaterialRequest.needed_by.asc()).all())
    items = {i.id: i for i in db.query(models.StoreItem).all()}
    # The site's own record carries the plot number and the man in
    # charge, so an order raised from a request needs neither typed.
    # The man who raised the request is the man the supplier should ring
    # about it, so his number travels with the line.
    eng_mobile = {e.name.strip().lower(): (e.mobile or "")
                  for e in db.query(models.Engineer).all()}
    site_info = {s.code: {"plot_no": s.plot_no or "", "project_name": s.project_name or "",
                          "incharge": s.incharge or "", "incharge_mobile": s.incharge_mobile or "",
                          "address": s.address or "", "map_url": s.map_url or ""}
                 for s in db.query(models.Site).all()}
    out = []
    for mr in reqs:
        for l in mr.lines:
            if (l.status or "pending") != "approved":
                continue
            if l.supplier_id:                       # already placed with somebody
                continue
            outstanding = (l.qty_approved or l.qty_requested or 0) - (l.qty_received or 0)
            if outstanding <= 0:
                continue
            it = items.get(l.item_id)
            out.append({
                "line_id": l.id, "request_id": mr.id, "ref": mr.ref,
                "site": mr.site or "", "requested_by": mr.requested_by or "",
            "plot_no": site_info.get(mr.site, {}).get("plot_no", ""),
            "project_name": site_info.get(mr.site, {}).get("project_name", ""),
            "incharge": site_info.get(mr.site, {}).get("incharge", ""),
            "incharge_mobile": site_info.get(mr.site, {}).get("incharge_mobile", ""),
            "address": site_info.get(mr.site, {}).get("address", ""),
            "map_url": site_info.get(mr.site, {}).get("map_url", ""),
            "requested_by_mobile": eng_mobile.get((mr.requested_by or "").strip().lower(), ""),
                "needed_by": mr.needed_by.isoformat() if mr.needed_by else "",
                "urgency": mr.urgency or "normal", "purpose": l.purpose or "",
                "item_id": l.item_id,
                "description": (it.name if it else "") or l.description or "",
                "qty": outstanding, "unit": l.unit or (it.unit if it else ""),
            })
    return out


def get_setting(db, key, default=""):
    row = db.query(models.Setting).filter(models.Setting.key == key).first()
    return (row.value if row else "") or default


def put_setting(db, key, value):
    row = db.query(models.Setting).filter(models.Setting.key == key).first()
    if row:
        row.value = value or ""
    else:
        db.add(models.Setting(key=key, value=value or ""))
    db.commit()


@app.get("/settings/company")
def read_company_settings(db: Session = Depends(get_db),
                           user: models.User = Depends(auth.get_current_user)):
    return {"store_incharge": get_setting(db, "store_incharge"),
            "store_incharge_mobile": get_setting(db, "store_incharge_mobile")}


@app.post("/settings/company")
def save_company_settings(payload: dict = Body(...), db: Session = Depends(get_db),
                           user: models.User = Depends(auth.require_admin)):
    for k in ("store_incharge", "store_incharge_mobile"):
        if k in payload:
            put_setting(db, k, str(payload.get(k) or "").strip())
    log_action(db, user.id, "save_company_settings", "")
    return read_company_settings(db=db, user=user)


@app.get("/store/purchase/next-no")
def next_lpo_number(db: Session = Depends(get_db),
                     user: models.User = Depends(require_screen("approvals"))):
    n = _next_lpo_no(db)
    return {"po_no": n, "ref": f"IC/LPO/{n}",
            "store_incharge": get_setting(db, "store_incharge"),
            "store_incharge_mobile": get_setting(db, "store_incharge_mobile"),
            "terms_default": DEFAULT_LPO_TERMS,
            "terms_rental": RENTAL_LPO_TERMS, "terms_material": MATERIAL_LPO_TERMS}


@app.get("/store/purchase/rate-history")
def lpo_rate_history(item_id: int = None, description: str = "", limit: int = 8,
                      db: Session = Depends(get_db),
                      user: models.User = Depends(require_screen("approvals"))):
    """What this material has cost before, most recent first.

    Matched on the catalogue item where there is one, otherwise on the
    printed description - so a free-text material still builds a
    history. The point is to see the last rate before typing a new one.
    """
    q = (db.query(models.PurchaseOrderLine, models.PurchaseOrder)
           .join(models.PurchaseOrder, models.PurchaseOrderLine.order_id == models.PurchaseOrder.id)
           .filter(models.PurchaseOrder.status != "cancelled"))
    # Match on the catalogue item OR the printed name, not one or the
    # other: the same material gets ordered once as a catalogue item and
    # once as free text, and either way it is the same thing being
    # bought. Matching on only one meant a material plainly ordered
    # before came back as "first time".
    conds = []
    if item_id:
        conds.append(models.PurchaseOrderLine.item_id == item_id)
    if description.strip():
        conds.append(func.lower(func.trim(models.PurchaseOrderLine.description))
                     == description.strip().lower())
    if not conds:
        return {"count": 0, "last": None, "history": []}
    q = q.filter(or_(*conds))
    rows = q.order_by(models.PurchaseOrder.order_date.desc(),
                      models.PurchaseOrder.po_no.desc()).all()
    history = [{"ref": o.ref, "date": o.order_date.isoformat(), "supplier": o.supplier_name,
                "qty": l.qty, "unit": l.unit, "rate": l.rate,
                "site": o.project_location} for l, o in rows[:limit]]
    return {"count": len(rows), "last": history[0] if history else None, "history": history}


@app.get("/store/purchase/orders")
def list_purchase_orders(q: str = "", limit: int = 200, db: Session = Depends(get_db),
                          user: models.User = Depends(require_screen("approvals"))):
    """The purchase register - every order raised, newest first."""
    query = db.query(models.PurchaseOrder).options(joinedload(models.PurchaseOrder.lines))
    rows = query.order_by(models.PurchaseOrder.po_no.desc()).limit(2000).all()
    needle = q.strip().lower()
    out = []
    for o in rows:
        total = sum((l.qty or 0) * (l.rate or 0) for l in o.lines)
        net = total * (1 - (o.discount_pct or 0) / 100.0)
        blob = " ".join([o.ref, o.supplier_name or "", o.project_location or "",
                         o.job_scope or "", o.supplier_ref or ""] +
                        [l.description or "" for l in o.lines]).lower()
        if needle and needle not in blob:
            continue
        out.append({"id": o.id, "ref": o.ref, "po_no": o.po_no,
                    "date": o.order_date.isoformat(),
                    "supplier": o.supplier_name, "site": o.project_location,
                    "job_scope": o.job_scope, "status": o.status,
                    "lines": len(o.lines),
                    "total": round(net * (1 + (o.tax_pct or 0) / 100.0), 2),
                    "request_id": o.request_id})
        if len(out) >= limit:
            break
    return out


LPO_GROUPS = {
    "order": "Each order", "supplier": "Supplier", "site": "Project location",
    "material": "Material", "month": "Month", "job": "Job scope",
}
LPO_MEASURES = {
    "orders": "Orders", "lines": "Materials", "qty": "Quantity",
    "sub_total": "Sub Total (AED)", "vat": "VAT (AED)", "total": "Total (AED)",
}


@app.get("/store/purchase/price-search")
def lpo_price_search(q: str = "", limit: int = 12, db: Session = Depends(get_db),
                      user: models.User = Depends(require_screen("approvals"))):
    """What a material has cost, every time it was bought.

    Typed a few letters at a time - 'cem', 'rebar 16' - and answered
    with one entry per material: how often it was bought, the lowest,
    highest and last rate paid, from whom and when, and the purchases
    themselves underneath. This is the question the purchase officer
    actually asks, and the register could only answer it by reading
    order after order.
    """
    needle = q.strip().lower()
    if len(needle) < 2:
        return {"query": q, "materials": []}
    rows = (db.query(models.PurchaseOrderLine, models.PurchaseOrder)
              .join(models.PurchaseOrder, models.PurchaseOrderLine.order_id == models.PurchaseOrder.id)
              .filter(models.PurchaseOrder.status != "cancelled")
              .filter(func.lower(models.PurchaseOrderLine.description).like(f"%{needle}%"))
              .order_by(models.PurchaseOrder.order_date.desc(),
                        models.PurchaseOrder.po_no.desc())
              .limit(600).all())

    grouped = {}
    for l, o in rows:
        key = (l.description or "").strip().lower()
        g = grouped.setdefault(key, {"material": (l.description or "").strip(),
                                     "unit": l.unit or "", "buys": []})
        if not g["unit"] and l.unit:
            g["unit"] = l.unit
        g["buys"].append({
            "ref": o.ref, "id": o.id,
            "date": o.order_date.isoformat() if o.order_date else "",
            "supplier": o.supplier_name or "", "site": o.project_location or "",
            "qty": l.qty or 0, "rate": l.rate or 0,
        })

    out = []
    for g in grouped.values():
        rates = [b["rate"] for b in g["buys"] if b["rate"]]
        if not rates:
            continue
        last = g["buys"][0]
        out.append({
            "material": g["material"], "unit": g["unit"],
            "times": len(g["buys"]),
            "last_rate": last["rate"], "last_date": last["date"],
            "last_supplier": last["supplier"],
            "low": min(rates), "high": max(rates),
            "average": round(sum(rates) / len(rates), 2),
            "total_qty": round(sum(b["qty"] for b in g["buys"]), 2),
            "buys": g["buys"][:10],
        })
    out.sort(key=lambda x: -x["times"])
    return {"query": q, "materials": out[:limit]}


@app.get("/store/purchase/report")
def lpo_report(group_by: str = "order", measures: str = "orders,sub_total,vat,total",
                date_from: str = "", date_to: str = "", supplier: str = "", site: str = "",
                material: str = "", status: str = "issued",
                db: Session = Depends(get_db),
                user: models.User = Depends(require_screen("approvals"))):
    """The purchase register, asked whatever question is put to it.

    One order per row, or totalled by supplier, site, material, month or
    job - with the same filters either way, so 'what did we spend with
    Metrabar this month' and 'every order for cement' are the same
    screen rather than two reports nobody built.
    """
    q = (db.query(models.PurchaseOrder)
           .options(joinedload(models.PurchaseOrder.lines)))
    if status and status != "all":
        q = q.filter(models.PurchaseOrder.status == status)
    try:
        if date_from:
            q = q.filter(models.PurchaseOrder.order_date >= date.fromisoformat(date_from))
        if date_to:
            q = q.filter(models.PurchaseOrder.order_date <= date.fromisoformat(date_to))
    except ValueError:
        raise HTTPException(status_code=400, detail="Check the dates.")
    orders = q.order_by(models.PurchaseOrder.po_no.desc()).all()

    sup_q, site_q, mat_q = supplier.strip().lower(), site.strip().lower(), material.strip().lower()
    wanted = [m for m in measures.split(",") if m in LPO_MEASURES] or ["total"]
    group_by = group_by if group_by in LPO_GROUPS else "order"

    rows = {}
    counted_orders = set()
    for o in orders:
        if sup_q and sup_q not in (o.supplier_name or "").lower():
            continue
        if site_q and site_q not in (o.project_location or "").lower():
            continue
        lines = o.lines
        if mat_q:
            lines = [l for l in lines if mat_q in (l.description or "").lower()]
            if not lines:
                continue
        for l in lines:
            counted_orders.add(o.po_no)
            amount = (l.qty or 0) * (l.rate or 0)
            vat = amount * (l.tax_pct or 0) / 100.0
            if o.discount_pct:
                amount *= (1 - o.discount_pct / 100.0)
                vat = amount * (o.tax_pct or 5) / 100.0
            key = {
                "order": o.ref,
                "supplier": o.supplier_name or "(not named)",
                "site": o.project_location or "(none given)",
                "material": l.description or "(none)",
                "month": o.order_date.strftime("%B %Y") if o.order_date else "-",
                "job": o.job_scope or "(none given)",
            }[group_by]
            r = rows.setdefault(key, {"label": key, "orders": set(), "lines": 0, "qty": 0.0,
                                      "sub_total": 0.0, "vat": 0.0, "total": 0.0,
                                      "date": o.order_date.isoformat() if o.order_date else "",
                                      "supplier": o.supplier_name or "", "site": o.project_location or "",
                                      "job": o.job_scope or "", "status": o.status, "id": o.id,
                                      # Corrected since it was first raised, so the
                                      # register shows the change on the order itself
                                      # rather than leaving it to look untouched.
                                      "edited": bool(o.updated_at),
                                      "edited_on": o.updated_at.strftime("%d %b %Y") if o.updated_at else ""})
            r["orders"].add(o.po_no)
            r["lines"] += 1
            r["qty"] += (l.qty or 0)
            r["sub_total"] += amount
            r["vat"] += vat
            r["total"] += amount + vat

    out = []
    for r in rows.values():
        r["orders"] = len(r["orders"])
        for k in ("qty", "sub_total", "vat", "total"):
            r[k] = round(r[k], 2)
        out.append(r)
    out.sort(key=lambda x: (-x["total"]) if group_by != "order" else x["label"], reverse=(group_by == "order"))

    totals = {m: round(sum(r[m] for r in out), 2) for m in wanted}
    if "orders" in totals:
        # Count the orders actually behind the rows shown. Counting every
        # order that passed the supplier filter ignored the rest of them,
        # so a report filtered to one material claimed more orders than
        # it listed.
        totals["orders"] = len(counted_orders)
    return {
        "group_by": group_by, "group_label": LPO_GROUPS[group_by],
        "measures": [{"key": m, "label": LPO_MEASURES[m]} for m in wanted],
        "rows": out, "totals": totals,
        "catalog": {"groups": [{"key": k, "label": v} for k, v in LPO_GROUPS.items()],
                    "measures": [{"key": k, "label": v} for k, v in LPO_MEASURES.items()]},
    }


@app.get("/export/store/purchase-report")
def export_lpo_report(token: str, format: str = "excel", group_by: str = "order",
                       measures: str = "orders,sub_total,vat,total",
                       date_from: str = "", date_to: str = "", supplier: str = "",
                       site: str = "", material: str = "", status: str = "issued",
                       db: Session = Depends(get_db)):
    auth.get_download_user_from_token(token, db)
    data = lpo_report(group_by=group_by, measures=measures, date_from=date_from, date_to=date_to,
                      supplier=supplier, site=site, material=material, status=status,
                      db=db, user=_SystemUser())
    rows = []
    for r in data["rows"]:
        row = {data["group_label"]: r["label"]}
        if group_by == "order":
            row["Date"] = r["date"]
            row["Supplier"] = r["supplier"]
            row["Project location"] = r["site"]
        for m in data["measures"]:
            row[m["label"]] = r[m["key"]]
        rows.append(row)
    bits = []
    if date_from or date_to:
        bits.append(f"{date_from or 'the start'} to {date_to or 'today'}")
    if supplier: bits.append(f"supplier: {supplier}")
    if site: bits.append(f"site: {site}")
    if material: bits.append(f"material: {material}")
    subtitle = " · ".join(bits)
    title = f"Purchase orders by {data['group_label'].lower()}"
    if format == "pdf":
        buf = export_web.build_store_report_pdf(title, rows, subtitle)
        return StreamingResponse(buf, media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=Purchase_Report.pdf"})
    buf = export_web.build_store_report_excel(title, rows, subtitle)
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Purchase_Report.xlsx"})


class _SystemUser:
    """Stands in for the signed-in user when one endpoint calls another
    that has already checked the caller's token."""
    id = None
    role = "admin"
    permissions = ""


@app.get("/store/purchase/orders/{order_id}")
def get_purchase_order(order_id: int, db: Session = Depends(get_db),
                        user: models.User = Depends(require_screen("approvals"))):
    o = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.id == order_id).first()
    if not o:
        raise HTTPException(status_code=404, detail="Purchase order not found.")
    return _lpo_dict(o)


def _lpo_dict(o):
    return {
        "id": o.id, "po_no": o.po_no, "ref": o.ref,
        "order_date": o.order_date.isoformat() if o.order_date else "",
        "terms": o.terms, "delivery_date": o.delivery_date.isoformat() if o.delivery_date else "",
        "supplier_ref": o.supplier_ref, "supplier_name": o.supplier_name,
        "supplier_address": o.supplier_address, "supplier_trn": o.supplier_trn,
        "request_id": o.request_id, "plot_no": o.plot_no, "contact_person": o.contact_person,
        "mobile": o.mobile, "email": o.email, "job_scope": o.job_scope,
        "project_location": o.project_location, "discount_pct": o.discount_pct,
        "tax_pct": o.tax_pct, "notes": o.notes, "terms_text": o.terms_text, "status": o.status,
        "lines": [{"id": l.id, "item_id": l.item_id, "description": l.description,
                   "description2": l.description2, "qty": l.qty, "unit": l.unit,
                   "rate": l.rate, "tax_pct": l.tax_pct} for l in o.lines],
    }


@app.post("/store/purchase/orders")
def create_purchase_order(payload: schemas.PurchaseOrderIn, db: Session = Depends(get_db),
                           user: models.User = Depends(require_screen("approvals"))):
    """Raise an order. From an approved request, or on its own."""
    if not (payload.supplier_name or "").strip():
        raise HTTPException(status_code=400, detail="Enter the supplier.")
    if not payload.lines:
        raise HTTPException(status_code=400, detail="An order needs at least one line.")

    # Contact Person and Mobile on the order are OURS - the man on site
    # the supplier should call. Passing them in here wrote them onto the
    # supplier's record, so his own contact was overwritten with ours
    # and the vendor block named the wrong person.
    supplier = _find_or_create_supplier(db, payload.supplier_name)
    # Anything typed here that the supplier record did not have is kept,
    # so the next order for the same trader needs none of it.
    if supplier:
        for field, value in (("trn", payload.supplier_trn), ("payment_terms", payload.terms)):
            if (value or "").strip() and not (getattr(supplier, field, "") or "").strip():
                setattr(supplier, field, value.strip())
    n = _next_lpo_no(db)
    o = models.PurchaseOrder(
        po_no=n, ref=f"IC/LPO/{n}",
        order_date=payload.order_date or _dubai_today(),
        terms=payload.terms or "Due on Receipt",
        delivery_date=payload.delivery_date,
        supplier_ref=payload.supplier_ref or "",
        supplier_id=supplier.id if supplier else None,
        supplier_name=(supplier.name if supplier else payload.supplier_name).strip(),
        supplier_address=payload.supplier_address or "",
        supplier_trn=payload.supplier_trn or "",
        request_id=payload.request_id,
        plot_no=payload.plot_no or "", contact_person=payload.contact_person or "",
        mobile=payload.mobile or "", email=payload.email or "purchase@infinia.ae",
        job_scope=payload.job_scope or "", project_location=payload.project_location or "",
        discount_pct=payload.discount_pct or 0.0,
        notes=payload.notes or "",
        terms_text=(payload.terms_text or DEFAULT_LPO_TERMS),
        created_by=user.id,
    )
    db.add(o)
    db.flush()
    for l in payload.lines:
        if not (l.description or "").strip() and not l.item_id:
            continue
        db.add(models.PurchaseOrderLine(
            order_id=o.id, item_id=l.item_id, description=(l.description or "").strip(),
            description2=(l.description2 or "").strip(), qty=l.qty or 0, unit=l.unit or "",
            rate=l.rate or 0, tax_pct=l.tax_pct if l.tax_pct is not None else 5.0))
    # Raising the order IS placing it. The request lines it came from are
    # marked ordered against this supplier, so the request moves on and
    # the keeper sees it on Order Follow-up - rather than the office
    # having to say "ordered" a second time somewhere else.
    placed = []
    if payload.request_line_ids:
        lines = (db.query(models.MaterialRequestLine)
                   .filter(models.MaterialRequestLine.id.in_(payload.request_line_ids)).all())
        for l in lines:
            l.supplier_id = supplier.id if supplier else None
            l.status = "approved"
            placed.append(l)
        for mr in {l.request for l in lines if l.request}:
            if payload.delivery_date:
                mr.expected_on = payload.delivery_date
            if mr.status in ("pending", "approved"):
                mr.status = "ordered"
            sup_ids = {x.supplier_id for x in mr.lines if (x.status or "") != "rejected"}
            mr.supplier_id = supplier.id if (supplier and sup_ids == {supplier.id}) else None
    db.commit()
    db.refresh(o)
    log_action(db, user.id, "create_lpo",
               f"{o.ref} to {o.supplier_name} ({len(o.lines)} line(s))"
               + (f", {len(placed)} request line(s) marked ordered" if placed else ""))
    return _lpo_dict(o)


@app.put("/store/purchase/orders/{order_id}")
def update_purchase_order(order_id: int, payload: schemas.PurchaseOrderIn, db: Session = Depends(get_db),
                           user: models.User = Depends(require_screen("approvals"))):
    """Correct an order already raised - a line missed, a rate wrong, a
    save made before it was ready. The number and the date first raised
    stay put; everything else is replaced, the way editing a document
    replaces its own content rather than starting a new one.

    A cancelled order keeps the paper it was cancelled with - reissue by
    raising a fresh one instead."""
    o = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.id == order_id).first()
    if not o:
        raise HTTPException(status_code=404, detail="Purchase order not found.")
    if o.status == "cancelled":
        raise HTTPException(status_code=400, detail="This order is cancelled - raise a new one instead.")
    if not (payload.supplier_name or "").strip():
        raise HTTPException(status_code=400, detail="Enter the supplier.")
    if not payload.lines:
        raise HTTPException(status_code=400, detail="An order needs at least one line.")

    supplier = _find_or_create_supplier(db, payload.supplier_name)
    if supplier:
        for field, value in (("trn", payload.supplier_trn), ("payment_terms", payload.terms)):
            if (value or "").strip() and not (getattr(supplier, field, "") or "").strip():
                setattr(supplier, field, value.strip())

    o.order_date = payload.order_date or o.order_date
    o.terms = payload.terms or "Due on Receipt"
    o.delivery_date = payload.delivery_date
    o.supplier_ref = payload.supplier_ref or ""
    o.supplier_id = supplier.id if supplier else None
    o.supplier_name = (supplier.name if supplier else payload.supplier_name).strip()
    o.supplier_address = payload.supplier_address or ""
    o.supplier_trn = payload.supplier_trn or ""
    o.plot_no = payload.plot_no or ""
    o.contact_person = payload.contact_person or ""
    o.mobile = payload.mobile or ""
    o.email = payload.email or "purchase@infinia.ae"
    o.job_scope = payload.job_scope or ""
    o.project_location = payload.project_location or ""
    o.discount_pct = payload.discount_pct or 0.0
    o.notes = payload.notes or ""
    o.terms_text = payload.terms_text or DEFAULT_LPO_TERMS

    # Lines are replaced wholesale rather than matched and patched - the
    # same as any other document correction, and simpler than reconciling
    # which of them the person meant to keep, change or drop.
    for l in list(o.lines):
        db.delete(l)
    db.flush()
    for l in payload.lines:
        if not (l.description or "").strip() and not l.item_id:
            continue
        db.add(models.PurchaseOrderLine(
            order_id=o.id, item_id=l.item_id, description=(l.description or "").strip(),
            description2=(l.description2 or "").strip(), qty=l.qty or 0, unit=l.unit or "",
            rate=l.rate or 0, tax_pct=l.tax_pct if l.tax_pct is not None else 5.0))
    db.commit()
    db.refresh(o)
    log_action(db, user.id, "edit_lpo", f"{o.ref} to {o.supplier_name} ({len(o.lines)} line(s))")
    return _lpo_dict(o)


@app.post("/store/purchase/orders/{order_id}/cancel")
def cancel_purchase_order(order_id: int, db: Session = Depends(get_db),
                           user: models.User = Depends(require_screen("approvals"))):
    """Cancelled, never deleted - the number stays used and the paper
    that went out is still on the register."""
    o = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.id == order_id).first()
    if not o:
        raise HTTPException(status_code=404, detail="Purchase order not found.")
    o.status = "cancelled"
    db.commit()
    log_action(db, user.id, "cancel_lpo", o.ref)
    return {"ok": True, "detail": f"{o.ref} cancelled."}


def db_session_site(code):
    """The site record behind an order's project location, if there is
    one - orders can name a location that was never added as a site."""
    from database import SessionLocal
    s = SessionLocal()
    try:
        return s.query(models.Site).filter(func.lower(models.Site.code) == code.lower()).first()
    except Exception:
        return None
    finally:
        s.close()


def _lpo_for_print(o):
    d = _lpo_dict(o)
    # The supplier's own contact details, from his record, so the order
    # says who to chase without anyone typing it again.
    sup = o.supplier
    d["supplier_email"] = (getattr(o, "supplier_email", "") or (sup.email if sup else "") or "")
    d["supplier_contact"] = (sup.contact_person if sup else "") or ""
    d["supplier_mobile"] = (sup.phone if sup else "") or ""
    # Where to deliver, from the site record.
    site = None
    if o.project_location:
        code = o.project_location.split(",")[0].strip()
        site = db_session_site(code)
    d["site_address"] = (site.address if site else "") or ""
    d["site_map"] = (site.map_url if site else "") or ""
    d["date_text"] = o.order_date.strftime("%d %b %Y") if o.order_date else ""
    d["delivery_text"] = o.delivery_date.strftime("%d %b %Y") if o.delivery_date else ""
    return d


# Under /export/, a prefix nginx already forwards. A new /view/ prefix
# fell through to the frontend, so clicking an order number loaded the
# app again instead of the order - the fourth time an invented prefix
# has cost a round trip.
@app.get("/export/purchase/{order_id}/view")
def view_purchase_order(order_id: int, token: str, db: Session = Depends(get_db)):
    """The order on screen, in its own tab, with the two downloads above
    it - so opening an LPO shows it rather than dropping a file in
    Downloads every time somebody checks a number."""
    user = auth.get_download_user_from_token(token, db)
    o = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.id == order_id).first()
    if not o:
        raise HTTPException(status_code=404, detail="Purchase order not found.")
    # A download token lasts a minute - long enough to fetch a file, far
    # too short for links on a page somebody is reading. The buttons
    # therefore go through /download, which checks this page's own token
    # and mints a fresh one, so they work for as long as the tab is
    # useful instead of dying sixty seconds after it opened.
    t = quote(auth.create_view_token(user.username), safe="")

    safe = o.ref.replace("/", "")
    _map = _site_field(o, "map_url")
    map_btn = (f'<a class="btn" href="{_map}" target="_blank" rel="noopener">Open the site on a map</a>'
               if _map.startswith("http") else "")
    page = f"""<!doctype html><html><head><meta charset="utf-8">
<title>{o.ref}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
         background:#F1EFEA; color:#1F2429; }}
  .bar {{ display:flex; align-items:center; gap:12px; flex-wrap:wrap;
          padding:10px 16px; background:white; border-bottom:1px solid #E2E0DC; }}
  .bar h1 {{ font-size:16px; margin:0 12px 0 0; }}
  .bar .who {{ font-size:13px; color:#666; }}
  a.btn {{ display:inline-block; text-decoration:none; font-size:13px; font-weight:600;
           padding:7px 14px; border-radius:6px; border:1px solid #D9B8B3;
           background:#FDF4F3; color:#8C2F26; }}
  a.btn.dark {{ background:#2E3238; border-color:#2E3238; color:white; }}
  a.btn.wa {{ background:#25D366; border-color:#1DA851; color:#06331A; }}
  .hint {{ font-size:11.5px; color:#888; padding:0 16px 8px; background:white;
           border-bottom:1px solid #E2E0DC; }}
  .cancelled {{ background:#FBE0DE; color:#C0392B; font-size:12px; font-weight:700;
                padding:3px 8px; border-radius:4px; }}
  .sheet {{ max-width:820px; margin:18px auto 40px; background:white; padding:22px 26px;
            border:1px solid #DDD; border-radius:6px; font-size:12.5px; }}
  .head {{ display:flex; justify-content:space-between; align-items:flex-start;
           border:1px solid #999; padding:10px 12px; }}
  .co {{ display:flex; align-items:center; gap:16px; }}
  .co .addr div {{ color:#444; font-size:11.5px; }}
  .po {{ font-size:21px; letter-spacing:.5px; }}
  .two {{ display:flex; gap:10px; margin-top:10px; align-items:stretch; }}
  .half {{ flex:1; border:1px solid #999; display:flex; flex-direction:column; }}
  .boxhead {{ background:#2E3238; color:white; font-size:11px; font-weight:700;
              letter-spacing:.3px; padding:4px 7px; }}
  .half table {{ width:100%; border-collapse:collapse; flex:1; }}
  .half td {{ vertical-align:top; }}
  .pairs td {{ padding:3px 8px; vertical-align:top; }}
  .pairs .k {{ color:#444; width:44%; }} .pairs .v {{ font-weight:600; }}
  table.lines {{ width:100%; border-collapse:collapse; margin-top:14px; }}
  table.lines th {{ background:#7B1F1A; color:white; padding:6px; font-size:11.5px; }}
  table.lines td {{ border:1px solid #B0B0B0; padding:6px; }}
  table.lines th.r, td.r {{ text-align:right; }} th.c, td.c {{ text-align:center; }}
  .sub {{ color:#666; font-size:11px; }}
  .foot {{ display:flex; gap:26px; margin-top:14px; }}
  .terms {{ flex:1.2; color:#333; font-size:11.5px; line-height:1.5; }}
  .lbl {{ color:#555; font-size:11px; margin-top:8px; }}
  table.money {{ width:100%; border-collapse:collapse; }}
  table.money td {{ padding:4px 6px; }}
  table.money .tot td {{ border-top:1px solid #999; font-size:14px; font-weight:700; }}
  .sig {{ border:1px solid #999; margin-top:10px; padding:8px; text-align:center;
          font-size:11.5px; color:#333; }}
  .sigbox {{ height:52px; }}
  @media print {{ .bar {{ display:none; }} .sheet {{ border:0; margin:0; max-width:none; }} }}
</style></head><body>
  <div class="bar">
    <h1>{o.ref}</h1>
    {'<span class="cancelled">CANCELLED</span>' if o.status == "cancelled" else ''}
    <span class="who">{o.supplier_name or ''}{' &middot; ' + o.project_location if o.project_location else ''}
      {' &middot; ' + o.order_date.strftime('%d %b %Y') if o.order_date else ''}</span>
    <span style="margin-left:auto;"></span>
    <a class="btn dark" href="/export/purchase/{o.id}?token={t}&amp;format=pdf">Download PDF</a>
    <a class="btn" href="/export/purchase/{o.id}?token={t}&amp;format=excel">Download Excel</a>
    <a class="btn wa" id="wa-share" href="https://web.whatsapp.com/" target="_blank" rel="noopener">Share on WhatsApp</a>
    {map_btn}
  </div>
  <div class="hint" id="wa-hint"></div>
  <div class="sheet">{_lpo_html(o)}</div>
<script>
  // Share the file itself. The browser's share sheet takes a PDF and
  // hands it straight to WhatsApp - no message to delete, just the
  // order as an attachment. Where the browser cannot do that, which
  // is most desktops, the file is downloaded and WhatsApp opened, so
  // there is one thing left to do rather than nothing working.
  var PDF_URL = "/export/purchase/{o.id}?token={t}&format=pdf";
  var FILE_NAME = "{safe}.pdf";
  var hint = document.getElementById("wa-hint");
  // Ask the browser properly: does it take FILES? Desktop Chrome has
  // navigator.canShare but refuses files, so checking only that the
  // function exists sent it down the sharing path, where it threw and
  // the fallback tab was pop-up blocked - the button did nothing at
  // all. Tested here with a real file, before anything is clicked.
  var canShareFiles = false;
  try {{
    var probe = new File([new Blob(["x"], {{ type: "application/pdf" }})],
                         "probe.pdf", {{ type: "application/pdf" }});
    canShareFiles = !!(navigator.canShare && navigator.share
                       && navigator.canShare({{ files: [probe] }}));
  }} catch (e) {{ canShareFiles = false; }}
  hint.textContent = canShareFiles
    ? "Opens your share sheet - choose WhatsApp, then the person to send it to."
    : "Opens WhatsApp Web and downloads the order - pick the chat there and attach it.";

  document.getElementById("wa-share").addEventListener("click", async function (ev) {{
    var btn = this;
    // Where the browser can hand a file to another app - a phone, and
    // desktop Safari - the share sheet takes the PDF itself and there
    // is nothing to open. Everywhere else the link does its ordinary
    // job of opening WhatsApp, and the file is downloaded to attach.
    if (!canShareFiles) {{
      var a = document.createElement("a");
      a.href = PDF_URL; a.download = FILE_NAME;
      document.body.appendChild(a); a.click(); a.remove();
      return;                      // the link opens WhatsApp by itself
    }}
    ev.preventDefault();
    var was = btn.textContent;
    btn.textContent = "Preparing...";
    try {{
      var res = await fetch(PDF_URL);
      if (!res.ok) throw new Error("could not fetch");
      var blob = await res.blob();
      var file = new File([blob], FILE_NAME, {{ type: "application/pdf" }});
      if (navigator.canShare({{ files: [file] }})) {{
        await navigator.share({{ files: [file] }});
      }} else {{
        throw new Error("no file sharing");
      }}
    }} catch (e) {{
      if (!e || e.name !== "AbortError") {{
        var a2 = document.createElement("a");
        a2.href = PDF_URL; a2.download = FILE_NAME;
        document.body.appendChild(a2); a2.click(); a2.remove();
        window.open("https://web.whatsapp.com/", "_blank", "noopener");
      }}
    }} finally {{
      btn.textContent = was;
    }}
  }});
</script>
</body></html>"""
    return HTMLResponse(page)


def _site_field(o, field):
    """A detail from the site behind this order's project location."""
    if not o.project_location:
        return ""
    s = db_session_site(o.project_location.split(",")[0].strip())
    return (getattr(s, field, "") if s else "") or ""


def _logo_img():
    """The company logo, inline, for the order shown on screen. The
    printed order has carried it all along; the preview had only the
    name in text."""
    try:
        if not os.path.exists(export_web.LOGO_PATH):
            return "<strong>INFINIA CONTRACTING LLC</strong>"
        import base64
        with open(export_web.LOGO_PATH, "rb") as f:
            data = base64.b64encode(f.read()).decode("ascii")
        return (f'<img src="data:image/png;base64,{data}" alt="Infinia Contracting" '
                f'style="height:40px; display:block; flex:none;">')
    except Exception:
        return "<strong>INFINIA CONTRACTING LLC</strong>"


def _sig_img():
    """The signature, inline, for the order shown on screen.

    The PDF embeds it; the preview was drawing an empty box, so an order
    looked unsigned until it was downloaded. Sent as data in the page
    itself rather than a second request, which would need its own token.
    """
    try:
        _sig = export_web.signature_file()
        if not _sig:
            return ""
        import base64
        with open(_sig, "rb") as f:
            data = base64.b64encode(f.read()).decode("ascii")
        kind = "jpeg" if _sig.lower().endswith((".jpg", ".jpeg")) else "png"
        return (f'<img src="data:image/{kind};base64,{data}" alt="" '
                f'style="max-height:48px; max-width:150px; display:block; margin:2px auto;">')
    except Exception:
        return ""


def _lpo_html(o):
    """The order drawn as a page, not an embedded PDF.

    A browser that has no PDF viewer - and a phone is often one - shows
    an empty grey frame instead of the order. Drawing it here means it
    is readable anywhere, and the two buttons above still give the real
    files.
    """
    def esc(v):
        return (str(v or "")
                .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    rows, sub, vat = [], 0.0, 0.0
    for i, l in enumerate(o.lines, start=1):
        amount = (l.qty or 0) * (l.rate or 0)
        tax = amount * (l.tax_pct or 0) / 100.0
        sub += amount
        vat += tax
        second = f'<div class="sub">{esc(l.description2)}</div>' if (l.description2 or "").strip() else ""
        rows.append(
            f'<tr><td class="c">{i}</td><td>{esc(l.description)}{second}</td>'
            f'<td class="r">{l.qty:,.2f}</td><td class="r">{l.rate:,.2f}</td>'
            f'<td class="r">{(l.tax_pct or 0):,.2f}</td><td class="r">{tax:,.2f}</td>'
            f'<td class="r">{amount:,.2f}</td></tr>')
    discount = sub * (o.discount_pct or 0) / 100.0
    net = sub - discount
    if o.discount_pct:
        vat = net * (o.tax_pct or 5) / 100.0
    total = net + vat

    money = [f'<tr><td>Sub Total</td><td class="r">{sub:,.2f}</td></tr>']
    if o.discount_pct:
        money.append(f'<tr><td>Discount({o.discount_pct:,.2f}%)</td>'
                     f'<td class="r">(-) {discount:,.2f}</td></tr>')
    money.append(f'<tr><td>Standard Rate ({(o.tax_pct or 5):g}%)</td><td class="r">{vat:,.2f}</td></tr>')
    money.append(f'<tr class="tot"><td>Total</td><td class="r">AED {total:,.2f}</td></tr>')

    def pair(k, v):
        # A padding row keeps the height without printing a stray colon.
        if not k:
            return '<tr><td class="k">&nbsp;</td><td class="v"></td></tr>'
        return f'<tr><td class="k">{k}</td><td class="v">: {esc(v)}</td></tr>'

    # The same two boxes the printed order has: ours on the left, the
    # vendor's on the right. The preview used to carry the older layout,
    # so what was on screen did not match what came out of the printer.
    sup = o.supplier
    def level(a, b):
        n = max(len(a), len(b))
        return a + [("", "")] * (n - len(a)), b + [("", "")] * (n - len(b))

    left_rows = [("Purchase Order No", o.ref),
                 ("Delivery Date", o.delivery_date.strftime("%d %b %Y") if o.delivery_date else ""),
                 ("Project Location", o.project_location),
                 ("Project &amp; Plot No", o.plot_no),
                 ("Delivery Address", _site_field(o, "address")),
                 ("Job Scope", o.job_scope),
                 ("Contact Person", o.contact_person),
                 ("Mobile", o.mobile)]
    right_rows = [("Supplier", o.supplier_name),
                  ("TRN", o.supplier_trn),
                  ("Email", getattr(o, "supplier_email", "") or (sup.email if sup else "")),
                  ("Contact Person", (sup.contact_person if sup else "")),
                  ("Mobile", (sup.phone if sup else "")),
                  ("Payment Terms", o.terms),
                  ("Date", o.order_date.strftime("%d %b %Y") if o.order_date else ""),
                  ("Reference No", o.supplier_ref)]
    left_rows, right_rows = level(left_rows, right_rows)
    left = "".join(pair(k, v) for k, v in left_rows)
    right = "".join(pair(k, v) for k, v in right_rows)
    addr = ""          # the address is no longer printed on an order
    terms = "".join(f"<div>{esc(x)}</div>" for x in (o.terms_text or "").splitlines() if x.strip())
    notes = ("".join(f"<div>{esc(x)}</div>" for x in (o.notes or "").splitlines() if x.strip()))

    return f"""
      <div class="head">
        <div class="co">{_logo_img()}
          <div class="addr"><div>M09 Bin Bishr Building</div>
            <div>Abu Hail,  Dubai , United Arab Emirates</div>
            <div>TRN 100602393900003</div></div></div>
        <div class="po">PURCHASE ORDER</div>
      </div>
      <div class="two">
        <div class="half"><div class="boxhead">PURCHASE ORDER DETAILS</div>
          <table class="pairs">{left}</table></div>
        <div class="half"><div class="boxhead">VENDOR DETAILS</div>
          <table class="pairs">{right}</table></div>
      </div>
      <table class="lines"><thead><tr><th class="c">#</th><th>Item &amp; Description</th>
        <th class="r">Qty</th><th class="r">Rate</th><th class="r">Tax %</th>
        <th class="r">Tax</th><th class="r">Amount</th></tr></thead>
        <tbody>{''.join(rows)}</tbody></table>
      <div class="foot">
        <div class="terms">
          {f'<div class="lbl">Notes</div>{notes}' if notes else ''}
          <div class="lbl">Terms &amp; Conditions</div>{terms}
        </div>
        <div>
          <table class="money">{''.join(money)}</table>
          <div class="sig">For Infinia Contracting LLC<div class="sigbox">{_sig_img()}</div>Authorized Signature</div>
        </div>
      </div>"""


@app.get("/export/store/return/{return_id}")
def export_hire_return(return_id: int, token: str, format: str = "pdf",
                        inline: bool = False, db: Session = Depends(get_db)):
    """The return note as paper. Kept under /export/store/ because the
    proxy forwards only prefixes it already knows - an invented one has
    cost a round trip more than once."""
    auth.get_download_user_from_token(token, db)
    r = (db.query(models.HireReturn).options(joinedload(models.HireReturn.lines))
           .filter(models.HireReturn.id == return_id).first())
    if not r:
        raise HTTPException(status_code=404, detail="Return note not found.")
    note = _return_dict(r, db)
    safe = r.ref.replace("/", "")
    if format == "excel":
        buf = export_web.build_hire_return_excel(note)
        return StreamingResponse(
            buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={safe}.xlsx"})
    buf = export_web.build_hire_return_pdf(note)
    disp = "inline" if inline else "attachment"
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": f"{disp}; filename={safe}.pdf"})


@app.get("/export/purchase/{order_id}")
def export_purchase_order(order_id: int, token: str, format: str = "pdf",
                           inline: bool = False, db: Session = Depends(get_db)):
    auth.get_download_user_from_token(token, db)
    o = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.id == order_id).first()
    if not o:
        raise HTTPException(status_code=404, detail="Purchase order not found.")
    d = _lpo_for_print(o)
    safe = o.ref.replace("/", "")
    if format == "excel":
        buf = export_web.build_lpo_excel(d)
        return StreamingResponse(
            buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={safe}.xlsx"})
    buf = export_web.build_lpo_pdf(d)
    # inline shows it in the browser instead of dropping a file in
    # Downloads - so an order can be read before deciding to keep it.
    how = "inline" if inline else "attachment"
    return StreamingResponse(buf, media_type="application/pdf",
        headers={"Content-Disposition": f"{how}; filename={safe}.pdf"})


# An order prints the signature at 34mm by 13mm. A phone photo of one
# runs to several megabytes and thirty times the pixels that size can
# show, and every PDF then pays to scale it down again - and it rides
# along in every backup. Brought to a size the paper can actually use.
SIGNATURE_MAX_PX = 800


def _tidy_signature(data: bytes, filename: str = "") -> tuple:
    """(bytes, extension) for a signature at a size the paper can use.

    Returns the original untouched if the imaging library is missing -
    an upload must never fail because a picture could not be shrunk.
    """
    fallback = "jpg" if (filename or "").lower().endswith((".jpg", ".jpeg")) else "png"
    try:
        from PIL import Image, ImageOps
    except Exception:
        return data, fallback
    try:
        img = Image.open(io.BytesIO(data))
        # A photo taken sideways carries its rotation as metadata that a
        # PDF ignores, so the signature printed on its side.
        img = ImageOps.exif_transpose(img)
        if max(img.size) > SIGNATURE_MAX_PX:
            img.thumbnail((SIGNATURE_MAX_PX, SIGNATURE_MAX_PX), Image.LANCZOS)
        transparent = img.mode in ("RGBA", "LA", "P") and (
            "transparency" in img.info or img.mode in ("RGBA", "LA"))
        out = io.BytesIO()
        if transparent:
            # A signature cut out of its background: the transparency is
            # the valuable part, so it stays a PNG.
            img.convert("RGBA").save(out, format="PNG", optimize=True)
            ext = "png"
        else:
            # A photograph of a signature on paper. Ink is grey on white,
            # so colour carries nothing, and JPEG holds a photograph in a
            # fraction of what a lossless format needs. Saved without the
            # camera's metadata, which also records where it was taken.
            img.convert("L").save(out, format="JPEG", quality=85, optimize=True)
            ext = "jpg"
        shrunk = out.getvalue()
        return (shrunk, ext) if len(shrunk) < len(data) else (data, fallback)
    except Exception:
        return data, fallback     # an unreadable image is the upload's problem


@app.post("/store/purchase/signature")
async def upload_signature(file: UploadFile = File(...), db: Session = Depends(get_db),
                            user: models.User = Depends(auth.require_admin)):
    """The authorised signature, printed on every order. Uploaded once."""
    data = await file.read()
    if len(data) > 8_000_000:
        raise HTTPException(status_code=400, detail="Signature image must be under 8 MB.")
    if not (file.filename or "").lower().endswith((".png", ".jpg", ".jpeg")):
        raise HTTPException(status_code=400, detail="Use a PNG or JPG image.")
    data, ext = _tidy_signature(data, file.filename or "")
    target = os.path.join(export_web.DATA_DIR, "signature." + ext)
    try:
        # Only one signature is ever held, so the other spelling goes.
        for other in export_web.SIG_PATHS:
            if other != target and os.path.exists(other):
                try:
                    os.remove(other)
                except OSError:
                    pass
        with open(target, "wb") as f:
            f.write(data)
    except Exception as e:
        # Said out loud rather than swallowed: an upload that fails
        # quietly means orders go out unsigned and nobody knows why.
        raise HTTPException(status_code=500,
                            detail=f"Could not save the signature to {target}: {e}")
    if not os.path.exists(target):
        raise HTTPException(status_code=500, detail="The signature did not save - check the server's disk.")
    log_action(db, user.id, "upload_signature",
               f"{file.filename or ''} -> {os.path.basename(target)}, {len(data)/1024:.0f} KB")
    return {"ok": True, "detail": "Signature saved - it prints on every purchase order.",
            "path": target, "bytes": len(data)}


@app.get("/store/purchase/signature-status")
def signature_status(user: models.User = Depends(require_screen("approvals"))):
    # The path comes back too, so where it went can be checked on the
    # server without guessing.
    path = export_web.signature_file()
    return {"present": bool(path), "path": path or export_web.SIG_PATH,
            "bytes": os.path.getsize(path) if path else 0}


@app.get("/export/store/report")
def export_store_report(kind: str = "stock", format: str = "excel",
                         date_from: str = None, date_to: str = None,
                         q: str = "", token: str = None, db: Session = Depends(get_db)):
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
    # On screen the site split opens as its own panel; on paper there is
    # nowhere to expand, so it becomes a readable column instead of a
    # raw mapping.
    rows = []
    for r in data["rows"]:
        r = {k: v for k, v in r.items() if k not in ("low", "overdue")}
        if isinstance(r.get("by_site"), dict):
            per = r.pop("by_site")
            # One site per line. Twenty sites on one line read as a
            # number soup; stacked, the cell reads top to bottom.
            r["at_which_sites"] = "\n".join(f"{loc}: {_clean_export_qty(q)}"
                                             for loc, q in sorted(per.items())) or "-"
        rows.append(r)
    # What was typed in "Search within this report" narrows the download
    # too. Typing "asset" and getting the whole store on paper was the
    # complaint; the file now holds what the screen showed.
    q = (q or "").strip().lower()
    if q:
        rows = [r for r in rows if q in " ".join(str(v) for v in r.values()).lower()]
        sub = f'{sub} · matching "{q}"'
    data = {**data, "rows": rows}
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


@app.get("/permissions/screens")
def list_screens(user: models.User = Depends(auth.get_current_user)):
    return {"screens": ALL_SCREENS, "role_defaults": ROLE_DEFAULTS}


@app.get("/permissions/me")
def my_permissions(user: models.User = Depends(auth.get_current_user)):
    return {"role": user.role, "screens": effective_permissions(user)}


@app.post("/users/{user_id}/permissions")
def set_permissions(user_id: int, payload: schemas.PermissionsIn,
                     db: Session = Depends(get_db),
                     user: models.User = Depends(auth.require_admin)):
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.role == "admin":
        raise HTTPException(status_code=400,
            detail="An admin always has access to everything - nothing to set.")
    wanted = [s.strip() for s in (payload.permissions or "").split(",") if s.strip()]
    bad = [s for s in wanted if s not in ALL_SCREENS]
    if bad:
        raise HTTPException(status_code=400, detail=f"Unknown screen(s): {', '.join(bad)}")
    target.permissions = ",".join(wanted)
    db.commit()
    log_action(db, user.id, "set_permissions", f"{target.username}: {target.permissions or '(role default)'}")
    return {"ok": True, "permissions": effective_permissions(target)}


# ---------------------------------------------------------------------
# NOTIFICATIONS
# ---------------------------------------------------------------------
# Plain words for a status, used when telling someone a request is late.
MR_STATUS_WORDS = {
    "pending": "waiting on the office",
    "approved": "approved, not yet ordered",
    "ordered": "on order",
    "arranging": "on order",
    "lpo_sent": "on order",
    "partial": "partly delivered",
}


@app.get("/notifications")
def get_notifications(db: Session = Depends(get_db),
                       user: models.User = Depends(auth.get_current_user)):
    """
    Notifications the way people expect them: each event goes to the
    role that has to act on it, and clicking one lands on the exact
    item. Derived from live data, so nothing can go stale.

      office (approvals)  <- a new request arrives; a request is late
      site (requests)     <- their request was approved, ordered,
                             delivered or rejected
      keeper (store)      <- stock is low; a rental is overdue back
      attendance          <- yesterday's sheet is missing or incomplete
    """
    today = _dubai_today()
    allowed = effective_permissions(user)
    out = []
    recent_cutoff = today - timedelta(days=7)

    def _mr_lines(m):
        n = len(m.lines)
        return f"{n} material{'s' if n != 1 else ''}"

    reqs = db.query(models.MaterialRequest).all() if ("approvals" in allowed or "requests" in allowed) else []

    # ---- Office: things to act on -----------------------------------
    if "approvals" in allowed:
        for m in reqs:
            if m.status == "pending":
                out.append({"id": f"new-req-{m.id}", "kind": "request", "request_id": m.id,
                             "title": f"New material request {m.ref}",
                             "detail": f"{_person_name(m.requested_by) or 'Someone'} asked for {_mr_lines(m)}"
                                       + (f" for site {m.site}" if m.site else " for the central store")
                                       + (f", needed by {m.needed_by.isoformat()}" if m.needed_by else ""),
                             "screen": "approvals", "target": m.ref,
                             "when": m.requested_on.isoformat(), "level": "info"})
            if (m.needed_by and m.needed_by < today
                    and m.status not in ("delivered", "received", "closed", "rejected")):
                out.append({"id": f"late-{m.id}-{m.needed_by}", "kind": "late", "request_id": m.id,
                             "title": f"{m.ref} is late",
                             "detail": f"Needed by {m.needed_by.isoformat()}, still "
                                       f"{MR_STATUS_WORDS.get(m.status, m.status)}",
                             "screen": "approvals", "target": m.ref,
                             "when": m.needed_by.isoformat(), "level": "warn"})

    # ---- Site staff: what happened to their requests -----------------
    if "requests" in allowed:
        for m in reqs:
            upd = m.updated_at.date() if m.updated_at else None
            if not upd or upd < recent_cutoff:
                continue
            if m.status == "approved":
                title, detail, lvl = f"{m.ref} approved", "The office has approved it and will order", "ok"
            elif m.status in ("ordered", "arranging", "lpo_sent"):
                sups = sorted({l.supplier.name for l in m.lines if l.supplier})
                title = f"{m.ref} ordered"
                detail = ("From " + ", ".join(sups) if sups else "Ordered by the office") \
                         + (f", expected {m.expected_on.isoformat()}" if m.expected_on else "")
                lvl = "ok"
            elif m.status == "partial":
                got = sum(l.qty_received or 0 for l in m.lines)
                asked = sum(l.qty_requested or 0 for l in m.lines)
                title, detail, lvl = f"{m.ref} partly delivered", f"{got:g} of {asked:g} arrived so far", "info"
            elif m.status in ("delivered", "received"):
                title, detail, lvl = f"{m.ref} delivered", "Everything has arrived at the store", "ok"
            elif m.status == "rejected":
                title, detail, lvl = f"{m.ref} rejected", (m.office_remark or "The office turned it down"), "warn"
            else:
                continue
            out.append({"id": f"status-{m.id}-{m.status}-{upd}", "kind": "status", "request_id": m.id,
                         "title": title, "detail": detail,
                         "screen": "followup" if m.status not in ("delivered", "received", "rejected") else "requests",
                         "target": m.ref, "when": upd.isoformat(), "level": lvl})

    # ---- Keeper: the store itself ------------------------------------
    if "store" in allowed:
        items = {i.id: i for i in db.query(models.StoreItem).filter(models.StoreItem.active == True).all()}  # noqa: E712
        stock = _stock_map(db)
        stocked = _ever_stocked(db)
        low = [(i, stock.get((i.id, CENTRAL), 0)) for i in items.values()
               if i.reorder_level and i.id in stocked and stock.get((i.id, CENTRAL), 0) <= i.reorder_level]
        for i, have in low[:20]:
            out.append({"id": f"low-{i.id}-{have}", "kind": "low",
                         "title": f"{i.name} is running low",
                         "detail": f"{have:g} {i.unit} left, warn level is {i.reorder_level:g}",
                         "screen": "store", "target": i.code, "when": today.isoformat(), "level": "warn"})
        for i in items.values():
            if i.item_type == "rental" and i.rental_due and i.rental_due < today:
                out.append({"id": f"rent-{i.id}-{i.rental_due}", "kind": "rental",
                             "title": f"{i.name} is overdue back to {i.rental_supplier or 'the supplier'}",
                             "detail": f"Was due {i.rental_due.isoformat()}",
                             "screen": "store", "target": i.code, "when": i.rental_due.isoformat(), "level": "warn"})

    # ---- Attendance -------------------------------------------------
    if "attendance" in allowed:
        y = today - timedelta(days=1)
        marked = (db.query(models.DailyRow)
                    .filter(models.DailyRow.full_date == y,
                             or_(models.DailyRow.am != "", models.DailyRow.pm != ""))
                    .count())
        active = db.query(models.Employee).filter(models.Employee.active == True).count()  # noqa: E712
        if active and marked == 0:
            out.append({"id": f"att-none-{y}", "kind": "attendance",
                         "title": "No attendance saved for yesterday",
                         "detail": y.strftime("%A, %d %B %Y"),
                         "screen": "attendance", "when": y.isoformat(), "level": "warn"})
        elif active and marked < active:
            out.append({"id": f"att-part-{y}-{marked}", "kind": "attendance",
                         "title": "Yesterday's attendance is incomplete",
                         "detail": f"{marked} of {active} workers marked",
                         "screen": "attendance", "when": y.isoformat(), "level": "info"})

    # Newest first within each urgency band
    order = {"warn": 0, "info": 1, "ok": 2}
    out.sort(key=lambda n: (order.get(n["level"], 3), n["when"]), reverse=False)
    out.sort(key=lambda n: n["when"], reverse=True)
    out.sort(key=lambda n: order.get(n["level"], 3))
    return {"notifications": out[:60], "count": len(out)}


@app.post("/store/requests/{req_id}/receive-bulk")
def receive_request_bulk(req_id: int, payload: schemas.ReceiveRequestIn,
                          db: Session = Depends(get_db),
                          user: models.User = Depends(require_any_screen("store", "approvals"))):
    """
    Record a whole delivery against a request in one go.

    The store keeper opens the request, adjusts the quantities that
    actually turned up (a supplier often sends less than was ordered) and
    saves. Each line files its own 'in' stock movement, so the ledger
    stays the single source of truth, and the request advances to
    'partial' or 'delivered' by itself based on what is still owed.
    """
    mr = db.query(models.MaterialRequest).filter(models.MaterialRequest.id == req_id).first()
    if not mr:
        raise HTTPException(status_code=404, detail="Request not found")

    # Where the load went. Every delivery used to be booked into the
    # central store, so material dropped straight at a site showed as
    # sitting in a store it never reached, and had to be issued out
    # again to correct it. The request's own site is the default now,
    # and the keeper can say otherwise.
    where = payload.deliver_to if payload.deliver_to is not None else (mr.site or "")
    where = (where or "").strip()
    if where and where != CENTRAL:
        # Spelled as the site list spells it, so 904 and 904 are one
        # place rather than two columns in the stock report. A site not
        # on the list is still accepted as typed: requests are raised
        # for sites before anyone gets round to adding them, and
        # refusing the delivery would leave real material unrecorded.
        known = db.query(models.Site).filter(func.lower(models.Site.code) == where.lower()).first()
        if known:
            where = known.code

    when = payload.received_on or date.today()
    # Deliveries are often written up a few days late, and sometimes
    # booked a day or two ahead for a load already on its way. Both are
    # real, so only a date far in the future is refused - that is a
    # typed year or month slip, not a delivery.
    if when > date.today() + timedelta(days=30):
        raise HTTPException(status_code=400,
            detail="Delivery date is more than a month ahead - check the date.")

    wanted = [l for l in payload.lines if l.qty and l.qty > 0]
    if not wanted:
        raise HTTPException(status_code=400, detail="Enter how much arrived for at least one material.")

    # Learn the supplier as the delivery is recorded: the name is tidied
    # to one spelling, and the request keeps a link to it so the keeper
    # can chase the next order without asking who sold it to us.
    sup = _find_or_create_supplier(db, payload.supplier) if (payload.supplier or "").strip() else None
    sup_name = sup.name if sup else ""

    errors, done = [], 0
    for w in wanted:
        line = db.query(models.MaterialRequestLine).filter(
            models.MaterialRequestLine.id == w.line_id,
            models.MaterialRequestLine.request_id == req_id).first()
        if not line:
            errors.append(f"Line {w.line_id} is not on this request."); continue
        if not line.item_id:
            errors.append(f"'{line.description}' isn't a store item yet, so it can't be received into stock.")
            continue
        if (line.status or "pending") == "rejected":
            name = line.item.name if line.item else line.description
            errors.append(f"{name}: the office rejected this material.")
            continue
        outstanding = (line.qty_requested or 0) - (line.qty_received or 0)
        if w.qty > outstanding + 1e-9:
            name = line.item.name if line.item else line.description
            errors.append(f"{name}: only {round(outstanding, 2)} {line.unit} still due.")
            continue
        # Supplier, in order of authority: what was typed against this
        # material, then the trader it was ordered from, then whoever
        # the delivery header names.
        own = (getattr(w, "supplier", "") or "").strip()
        if own:
            own_sup = _find_or_create_supplier(db, own)
            if own_sup and not line.supplier_id:
                line.supplier_id = own_sup.id
            line_sup = own_sup.name if own_sup else own
        else:
            line_sup = (line.supplier.name if line.supplier else "") or sup_name
        db.add(models.StoreMovement(
            item_id=line.item_id, kind="in", qty=w.qty, location=where,
            supplier=line_sup, reference=payload.reference or mr.ref,
            notes=(payload.notes or f"Against {mr.ref}"), moved_on=when, created_by=user.id))
        line.qty_received = (line.qty_received or 0) + w.qty
        # The trader on the delivery note is who this line was bought
        # from - learn it on lines that never got a supplier at ordering.
        if sup and not line.supplier_id:
            line.supplier_id = sup.id
        done += 1

    # The request-level supplier is a shortcut kept only while every
    # line agrees; recompute rather than overwrite.
    sup_ids = {l.supplier_id for l in mr.lines}
    mr.supplier_id = list(sup_ids)[0] if len(sup_ids) == 1 and None not in sup_ids else None

    if errors and not done:
        raise HTTPException(status_code=400, detail={"errors": errors})

    # A rejected line is never coming, so it must not hold the request
    # open. Judged on the lines that were actually wanted; otherwise a
    # request with one line turned down sits on the chase list forever
    # with nothing left to chase.
    wanted = [l for l in mr.lines if (l.status or "pending") != "rejected"]
    all_done = bool(wanted) and all((l.qty_received or 0) >= (l.qty_requested or 0) - 1e-9 for l in wanted)
    any_done = any((l.qty_received or 0) > 0 for l in wanted)
    mr.status = "delivered" if all_done else ("partial" if any_done else mr.status)
    if all_done:
        mr.closed_on = when
    db.commit()
    log_action(db, user.id, "material_request_receive",
               f"{mr.ref}: {done} line(s) received on {when}")
    return {"ok": True, "received_lines": done, "status": mr.status, "warnings": errors}

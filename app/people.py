"""People - the HR register, built beside the app so it can be tried first.

Served at /temporary/Infinia/people.html (and the access page beside it)
behind two rights of their own, `people` and `access`, that only admin
has until they are handed out. Everything here reads and writes the
same employee rows the rest of the app uses; what the app never kept
about a person goes in people_profiles, keyed to his employee id. So
the day this moves into the main app there is nothing to migrate - a
menu entry changes and a redirect is left behind.

Every path is under a prefix nginx already forwards: /employees/,
/export/, /permissions/, /users.
"""
from datetime import date, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session, joinedload

import main as M
import models, auth
from database import get_db

router = APIRouter()
PEOPLE_RIGHTS = {"labour": "people_labour", "office": "people_office",
                 "local": "people_local"}
PEOPLE = Depends(M.require_any_screen(*PEOPLE_RIGHTS.values()))
ACCESS = Depends(auth.require_admin)   # roles and logins: admin only


def allowed_groups(user):
    """The registers this login may see. Office salaries are on the office
    register; a login without that right never gets those rows, on any
    list, file or report."""
    if user is None or user.role == "admin":
        return set(PEOPLE_RIGHTS)
    perms = M.effective_permissions(user)
    return {g for g, r in PEOPLE_RIGHTS.items() if r in perms}


def _may(user, group):
    if group not in allowed_groups(user):
        raise HTTPException(status_code=403, detail=f"Not available to this login: the {GROUPS.get(group, group)} register.")

# Household staff (maids, house drivers) are office staff: same register,
# same right, same payroll.
GROUPS = {"labour": "Labour", "office": "Office staff", "local": "Local staff"}
# Annual leave: labour 60 calendar days after every two years of
# service; everyone else 30 days after each year.
LEAVE_RULES = {"labour": (60.0, 24), "office": (30.0, 12), "local": (30.0, 12)}


# ---- Who is on which register -------------------------------------------

def _profile(db, e, create=False):
    p = db.query(models.PeopleProfile).filter(models.PeopleProfile.employee_id == e.id).first()
    if not p and create:
        p = models.PeopleProfile(employee_id=e.id)
        db.add(p); db.flush()
    return p


def group_of(e, p=None):
    if p and p.group in GROUPS:
        return p.group
    if not e.staff:
        return "labour"
    if (e.pay_group or "staff") == "local":
        return "local"
    return "office"


@router.get("/employees/people/birthdays")
def birthdays_today(db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    """Whose birthday it is today (Dubai), by the date of birth on the
    staff file - the one from the passport. Labour, office and local
    staff still working; each login sees the registers it may open (a
    login without any sees none). 29 February birthdays are wished on
    28 February in other years."""
    today = M._dubai_today()
    groups = allowed_groups(user)
    if not groups:
        return {"date": today.isoformat(), "people": []}
    leap = today.year % 4 == 0 and (today.year % 100 != 0 or today.year % 400 == 0)
    out = []
    rows = (db.query(models.PeopleProfile, models.Employee)
              .join(models.Employee, models.Employee.id == models.PeopleProfile.employee_id)
              .filter(models.PeopleProfile.date_of_birth.isnot(None)).all())
    for p, e in rows:
        d = p.date_of_birth
        if not e.active or (e.terminated_on and e.terminated_on <= today):
            continue
        if not ((d.month, d.day) == (today.month, today.day) or
                (not leap and (d.month, d.day) == (2, 29) and (today.month, today.day) == (2, 28))):
            continue
        g = group_of(e, p)
        if g == "household":
            g = "office"
        if g not in groups:
            continue
        out.append({"emp_no": e.emp_no, "name": e.name, "group": g, "group_label": GROUPS.get(g, g),
                    "role": e.designation or e.trade or "", "age": today.year - d.year, "staff": bool(e.staff)})
    out.sort(key=lambda x: (x["group"] != "office", x["name"]))
    return {"date": today.isoformat(), "people": out}


def _next_birthday(d, today):
    """The next time this date of birth comes round, today included
    (29 February: 28 February in other years)."""
    def on(y):
        try:
            return date(y, d.month, d.day)
        except ValueError:
            return date(y, 2, 28)
    n = on(today.year)
    return n if n >= today else on(today.year + 1)


@router.get("/employees/people/birthdays/upcoming")
def birthdays_upcoming(group: str = "", db: Session = Depends(get_db), user: models.User = PEOPLE):
    """Everyone still working, next birthday first, counted from today.
    Also how many have no date of birth on their file yet."""
    today = M._dubai_today()
    groups = allowed_groups(user)
    if group:
        _may(user, group)
        groups = {group}
    out, missing = [], 0
    rows = (db.query(models.Employee, models.PeopleProfile)
              .outerjoin(models.PeopleProfile, models.PeopleProfile.employee_id == models.Employee.id)
              .filter(models.Employee.active == True).all())  # noqa: E712
    for e, p in rows:
        if e.terminated_on and e.terminated_on <= today:
            continue
        g = group_of(e, p)
        g = "office" if g == "household" else g
        if g not in groups:
            continue
        if not p or not p.date_of_birth:
            missing += 1
            continue
        nxt = _next_birthday(p.date_of_birth, today)
        out.append({"emp_no": e.emp_no, "name": e.name, "group": g, "group_label": GROUPS.get(g, g),
                    "role": e.designation or e.trade or "", "dob": p.date_of_birth.isoformat(),
                    "next": nxt.isoformat(), "days": (nxt - today).days, "turns": nxt.year - p.date_of_birth.year})
    out.sort(key=lambda x: (x["days"], x["name"]))
    return {"date": today.isoformat(), "rows": out, "missing": missing}


def _by_code(db, emp_no):
    e = db.query(models.Employee).filter(models.Employee.emp_no == str(emp_no).strip()).first()
    if not e:
        raise HTTPException(status_code=404, detail=f"No one on file with code {emp_no}.")
    return e


def _d(v):
    return v.isoformat() if v else ""


def _add_months(d, n):
    y, m = d.year + (d.month - 1 + n) // 12, (d.month - 1 + n) % 12 + 1
    last = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)).day
    return date(y, m, min(d.day, last))


def _months_between(a, b):
    """Whole months from a to b, the day of the month having come round."""
    if b < a:
        return 0
    n = (b.year - a.year) * 12 + (b.month - a.month)
    if b.day < a.day:
        n -= 1
    return max(n, 0)


def _service_text(e, upto=None):
    if not e.joined_on:
        return ""
    end = upto or M._dubai_today()
    if e.terminated_on and e.terminated_on < end:
        end = e.terminated_on
    months = _months_between(e.joined_on, end)
    days = (end - _add_months(e.joined_on, months)).days
    y, m = divmod(months, 12)
    bits = [f"{y} yr" if y else "", f"{m} m" if m else "", f"{days} d" if not y and days else ""]
    return " ".join(b for b in bits if b) or "0 d"


# ---- Leave ---------------------------------------------------------------

def leave_state(db, e, p, group, today=None):
    today = today or M._dubai_today()
    rule_days, rule_months = LEAVE_RULES.get(group, (30.0, 12))
    days = p.leave_days if (p and p.leave_days) else rule_days
    months = p.leave_months if (p and p.leave_months) else rule_months
    opening = (p.leave_opening or 0.0) if p else 0.0
    start = (p.leave_opening_on if (p and p.leave_opening_on) else None) or e.joined_on
    out = {"rule": f"{days:g} days / {months} months" if months != 12 else f"{days:g} days a year",
           "rule_days": days, "rule_months": months, "opening": opening,
           "counted_from": _d(start), "accrued": 0.0, "taken": 0.0, "balance": 0.0,
           "next_due": "", "due_state": "", "last_vacation": "", "vacations": [],
           "sick_this_year": 0.0, "why": ""}
    if not start:
        out["why"] = "No joining date on file"
        return out
    end = today
    if e.terminated_on and e.terminated_on < end:
        end = e.terminated_on
    served = _months_between(start, end)
    out["accrued"] = round(opening + days * served / months, 1)

    # Days taken: the Absence register for anyone paid monthly, the
    # attendance grid (a day marked Leave) for labour.
    vac = []
    if e.staff:
        rows = (db.query(models.StaffLeave)
                  .filter(models.StaffLeave.employee_id == e.id,
                          models.StaffLeave.on_date >= start, models.StaffLeave.on_date <= end)
                  .order_by(models.StaffLeave.on_date).all())
        for r in rows:
            if M._leave_kind(r) == "vacation":
                vac.append((r.on_date, r.portion or 1.0))
            if M._leave_kind(r) == "sick" and r.on_date.year == today.year:
                out["sick_this_year"] += r.portion or 1.0
    else:
        rows = (db.query(models.DailyRow)
                  .filter(models.DailyRow.emp_no == e.emp_no,
                          models.DailyRow.full_date >= start, models.DailyRow.full_date <= end)
                  .order_by(models.DailyRow.full_date).all())
        for r in rows:
            portion = (0.5 if r.am == "Leave" else 0) + (0.5 if r.pm == "Leave" else 0)
            if portion:
                vac.append((r.full_date, portion))
            if r.full_date.year == today.year:
                out["sick_this_year"] += (0.5 if r.am in ("Sick", "Medical") else 0) + \
                                         (0.5 if r.pm in ("Sick", "Medical") else 0)
    # Annual leave entered on Staff > Leave (approved or returned) counts
    # too: from the date of leave to the day before the date of return
    # (or for the days approved), up to today. A day already marked on
    # the attendance grid or the absence register is not counted twice.
    have = {d0 for d0, _ in vac}
    from_register = 0
    for r in (db.query(models.LeaveRecord)
                .filter(models.LeaveRecord.employee_id == e.id, models.LeaveRecord.leave_type == "annual",
                        models.LeaveRecord.status.in_(("approved", "returned")),
                        models.LeaveRecord.leave_on.isnot(None)).all()):
        if r.return_on:
            last = r.return_on - timedelta(days=1)
        elif r.approved_days:
            last = r.leave_on + timedelta(days=int(r.approved_days) - 1)
        else:
            last = end                   # gone, no return date yet: up to today
        d0 = max(r.leave_on, start)
        while d0 <= min(last, end):
            if d0 not in have:
                vac.append((d0, 1.0)); have.add(d0); from_register += 1
            d0 += timedelta(days=1)
    vac.sort(key=lambda t: t[0])
    out["from_register"] = from_register
    taken = round(sum(pn for _, pn in vac), 1)
    out["taken"] = taken
    out["balance"] = round(out["accrued"] - taken, 1)
    # Vacations as spells, most recent first.
    spells = []
    for d0, pn in vac:
        if spells and (d0 - spells[-1][1]).days <= 1:
            spells[-1][1] = d0; spells[-1][2] += pn
        else:
            spells.append([d0, d0, pn])
    out["vacations"] = [{"from": _d(a), "to": _d(b), "days": round(n, 1)} for a, b, n in reversed(spells)]
    if spells:
        a, b, n = spells[-1]
        out["last_vacation"] = f"{a:%d %b %Y} - {b:%d %b %Y} ({n:g} d)" if a != b else f"{a:%d %b %Y} ({n:g} d)"
    # The next block of leave falls due when its period completes.
    blocks_used = int(max(taken - opening, 0) // days)
    due = _add_months(start, months * (blocks_used + 1))
    out["next_due"] = _d(due)
    out["due_state"] = "due" if due <= today else "ahead"
    out["sick_this_year"] = round(out["sick_this_year"], 1)
    return out


# ---- One person, as a dictionary ----------------------------------------

def _row(db, e, p, docs_by_emp, today):
    g = group_of(e, p)
    docs = docs_by_emp.get(e.id, [])
    soonest = min((d.expires_on for d in docs if d.expires_on), default=None)
    lv = leave_state(db, e, p, g, today)
    return {
        "id": e.id, "emp_no": e.emp_no, "name": e.name, "group": g, "group_label": GROUPS[g],
        "designation": e.designation or e.trade or "", "trade": e.trade or "",
        "company": e.company or "", "company_id": e.company_id,
        "department": (p.department if p else "") or "",
        "joined_on": _d(e.joined_on), "service": _service_text(e),
        "terminated_on": _d(e.terminated_on), "active": bool(e.active),
        "pay_type": e.pay_type or "daily",
        "basic": round(e.basic_salary or 0, 2),
        "allowance": round(e.allowance or 0, 2) if e.staff else round((e.total_salary or 0) - (e.basic_salary or 0), 2),
        "gross": M._gross(e) if e.staff else round(e.total_salary or 0, 2),
        "pay_route": e.pay_route or "wps", "pay_group": e.pay_group or "staff",
        "nationality": (p.nationality if p else "") or "",
        "mobile": (p.mobile if p else "") or "",
        "soonest_expiry": _d(soonest),
        "soonest_days": (soonest - today).days if soonest else None,
        "leave_balance": lv["balance"], "leave_due": lv["next_due"], "leave_due_state": lv["due_state"],
    }


def _profile_dict(p):
    if not p:
        p = models.PeopleProfile()
    out = {}
    for c in models.PeopleProfile.__table__.columns:
        if c.name in ("id", "employee_id", "created_at", "updated_at"):
            continue
        v = getattr(p, c.name)
        out[c.name] = v.isoformat() if isinstance(v, date) else ("" if v is None else v)
    return out


PROFILE_DATES = {"date_of_birth", "contract_expiry", "leave_opening_on", "last_ticket_on"}
PROFILE_NUMBERS = {"leave_days", "leave_months", "leave_opening", "ticket_every_years"}


# ---- Leave register: spells of leave ----------------------------------------

LEAVE_TYPES = {"annual": "Annual leave", "sick": "Sick leave", "emergency": "Emergency leave",
               "unpaid": "Unpaid leave", "other": "Other"}
LEAVE_STATUS = {"pending": "Pending", "approved": "Approved", "returned": "Returned", "cancelled": "Cancelled"}


def _due_back(r):
    """The day he is due back: the return date written down, else the
    leave date plus the days approved."""
    if r.return_on:
        return r.return_on
    if r.leave_on and r.approved_days:
        return r.leave_on + timedelta(days=int(r.approved_days))
    return None


def _standing(r, today):
    """Where the spell stands today. Approved leave reads On leave from
    the day he goes, and Overdue once the day he was due back has passed
    without his return being marked."""
    st = r.status or "pending"
    if st in ("pending", "returned", "cancelled"):
        return LEAVE_STATUS[st], 0
    if r.leave_on and r.leave_on > today:
        return "Approved", 0
    due = _due_back(r)
    if due and due < today:
        return "Overdue", (today - due).days
    return "On leave", 0


def _leave_dict(r, e, p, today):
    g = group_of(e, p)
    g = "office" if g == "household" else g
    standing, late = _standing(r, today)
    due = _due_back(r)
    return {"id": r.id, "emp_no": e.emp_no, "name": e.name, "group": g, "group_label": GROUPS.get(g, g),
            "designation": e.designation or e.trade or "",
            "leave_type": r.leave_type or "annual", "leave_type_label": LEAVE_TYPES.get(r.leave_type or "annual", r.leave_type),
            "leave_on": _d(r.leave_on), "return_on": _d(r.return_on), "approved_days": r.approved_days,
            "due_back": _d(due), "status": r.status or "pending", "standing": standing, "days_late": late,
            "approved_by": r.approved_by or "", "home_phone": (p.home_phone if p else "") or "",
            "remark": r.remark or ""}


STANDING_ORDER = {"Overdue": 0, "On leave": 1, "Pending": 2, "Approved": 3, "Returned": 4, "Cancelled": 5}


@router.get("/employees/people/leave-register")
def leave_register(group: str = "", show: str = "", db: Session = Depends(get_db), user: models.User = PEOPLE):
    """Every spell of leave on file, those away now first. show: "" all,
    away (on leave or overdue), pending, upcoming (approved, not gone
    yet), returned."""
    today = M._dubai_today()
    groups = allowed_groups(user)
    if group:
        _may(user, group)
        groups = {group}
    rows = (db.query(models.LeaveRecord, models.Employee, models.PeopleProfile)
              .join(models.Employee, models.Employee.id == models.LeaveRecord.employee_id)
              .outerjoin(models.PeopleProfile, models.PeopleProfile.employee_id == models.Employee.id).all())
    out = []
    for r, e, p in rows:
        d = _leave_dict(r, e, p, today)
        if d["group"] not in groups:
            continue
        out.append(d)
    want = {"away": ("On leave", "Overdue"), "pending": ("Pending",), "upcoming": ("Approved",),
            "returned": ("Returned",)}.get(show)
    counts = {k: sum(1 for d in out if d["standing"] in v) for k, v in
              {"away": ("On leave", "Overdue"), "pending": ("Pending",), "upcoming": ("Approved",), "returned": ("Returned",)}.items()}
    if want:
        out = [d for d in out if d["standing"] in want]
    # Away now first, then waiting, then coming up, then the history (latest first).
    out.sort(key=lambda d: (STANDING_ORDER.get(d["standing"], 9),
                            d["leave_on"] if d["standing"] in ("Approved",) else "",
                            "".join(chr(255 - ord(c)) for c in (d["leave_on"] or "")), d["name"]))
    return {"date": today.isoformat(), "rows": out, "counts": counts, "total": sum(counts.values())}


def _leave_fields(r, payload):
    if "leave_type" in payload:
        t = (payload.get("leave_type") or "annual").strip().lower()
        if t not in LEAVE_TYPES:
            raise HTTPException(status_code=400, detail="Pick the leave type.")
        r.leave_type = t
    if "status" in payload:
        st = (payload.get("status") or "pending").strip().lower()
        if st not in LEAVE_STATUS:
            raise HTTPException(status_code=400, detail="Pick the status.")
        r.status = st
    for f in ("leave_on", "return_on"):
        if f in payload:
            setattr(r, f, M._as_date(payload.get(f)))
    if "approved_days" in payload:
        v = payload.get("approved_days")
        try:
            r.approved_days = int(float(v)) if v not in (None, "") else None
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Approved days must be a number.")
        if r.approved_days is not None and r.approved_days < 0:
            raise HTTPException(status_code=400, detail="Approved days cannot be negative.")
    for f in ("approved_by", "remark"):
        if f in payload:
            setattr(r, f, (payload.get(f) or "").strip())
    if not r.leave_on:
        raise HTTPException(status_code=400, detail="Enter the date of leave.")
    if r.return_on and r.return_on < r.leave_on:
        raise HTTPException(status_code=400, detail="The date of return is before the date of leave.")


def _save_home_phone(db, e, payload):
    """The home-country number lives on the staff file; the leave form
    only shows it and can fill it in."""
    if "home_phone" in payload:
        v = (payload.get("home_phone") or "").strip()
        p = _profile(db, e, create=bool(v))
        if p and (p.home_phone or "") != v:
            p.home_phone = v


@router.post("/employees/people/leave-register")
def add_leave_record(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = PEOPLE):
    e = _by_code(db, payload.get("emp_no") or "")
    _may(user, group_of(e, _profile(db, e)))
    r = models.LeaveRecord(employee_id=e.id, created_by=user.id, leave_type="annual", status="pending")
    _leave_fields(r, payload)
    db.add(r)
    _save_home_phone(db, e, payload)
    db.commit()
    M.log_action(db, user.id, "leave_added", f"{e.emp_no}: {LEAVE_TYPES[r.leave_type]} from {r.leave_on}")
    return _leave_dict(r, e, _profile(db, e), M._dubai_today())


@router.put("/employees/people/leave-register/{rec_id}")
def save_leave_record(rec_id: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = PEOPLE):
    r = db.query(models.LeaveRecord).filter(models.LeaveRecord.id == rec_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="That leave is not on file.")
    e = r.employee
    _may(user, group_of(e, _profile(db, e)))
    _leave_fields(r, payload)
    _save_home_phone(db, e, payload)
    db.commit()
    M.log_action(db, user.id, "leave_saved", f"{e.emp_no}: {LEAVE_STATUS[r.status]} {r.leave_on}")
    return _leave_dict(r, e, _profile(db, e), M._dubai_today())


@router.delete("/employees/people/leave-register/{rec_id}")
def delete_leave_record(rec_id: int, db: Session = Depends(get_db), user: models.User = PEOPLE):
    r = db.query(models.LeaveRecord).filter(models.LeaveRecord.id == rec_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="That leave is not on file.")
    e = r.employee
    _may(user, group_of(e, _profile(db, e)))
    db.delete(r); db.commit()
    M.log_action(db, user.id, "leave_deleted", f"{e.emp_no}: {r.leave_on}")
    return {"ok": True}


@router.get("/employees/people")
def list_people(group: str = "", include_left: bool = False, q: str = "",
                company_id: int = None, db: Session = Depends(get_db), user: models.User = PEOPLE):
    today = M._dubai_today()
    profs = {p.employee_id: p for p in db.query(models.PeopleProfile).all()}
    docs = {}
    for d in db.query(models.EmployeeDocument).all():
        docs.setdefault(d.employee_id, []).append(d)
    rows, counts = [], {k: 0 for k in GROUPS}
    counts["left"] = 0
    mine = allowed_groups(user)
    for e in db.query(models.Employee).order_by(models.Employee.emp_no).all():
        p = profs.get(e.id)
        g = group_of(e, p)
        if g not in mine:
            continue
        left = not e.active or (e.terminated_on and e.terminated_on <= today)
        if left:
            counts["left"] += 1
        else:
            counts[g] += 1
        if group == "left":
            if not left:
                continue
        elif group:
            if g != group or (left and not include_left):
                continue
        elif left and not include_left:
            continue
        if company_id and e.company_id != company_id:
            continue
        if q.strip() and q.strip().lower() not in f"{e.emp_no} {e.name} {e.designation or ''} {e.trade or ''}".lower():
            continue
        rows.append(_row(db, e, p, docs, today))
    return {"rows": rows, "counts": counts, "groups": GROUPS, "allowed": sorted(mine)}


@router.get("/employees/people/documents-due")
def documents_due(days: int = 90, group: str = "", db: Session = Depends(get_db),
                  user: models.User = PEOPLE):
    today = M._dubai_today()
    profs = {p.employee_id: p for p in db.query(models.PeopleProfile).all()}
    rows = []
    for d in db.query(models.EmployeeDocument).options(joinedload(models.EmployeeDocument.employee)).all():
        e = d.employee
        if not M.doc_tracked(e, today) or not d.expires_on:
            continue
        g = group_of(e, profs.get(e.id))
        if (group and g != group) or g not in allowed_groups(user):
            continue
        left = (d.expires_on - today).days
        if left > days:
            continue
        r = M._doc_dict(d, e)
        r["group"] = g; r["group_label"] = GROUPS[g]
        rows.append(r)
    rows.sort(key=lambda r: r["days_left"])
    return {"rows": rows, "days": days}


@router.get("/employees/people/leave-balances")
def leave_balances(group: str = "labour", db: Session = Depends(get_db), user: models.User = PEOPLE):
    today = M._dubai_today()
    profs = {p.employee_id: p for p in db.query(models.PeopleProfile).all()}
    rows = []
    for e in db.query(models.Employee).filter(models.Employee.active == True).order_by(models.Employee.emp_no).all():  # noqa: E712
        p = profs.get(e.id)
        g = group_of(e, p)
        if (group and g != group) or g not in allowed_groups(user):
            continue
        lv = leave_state(db, e, p, g, today)
        rows.append({"emp_no": e.emp_no, "name": e.name, "designation": e.designation or e.trade or "",
                     "company": e.company or "", "joined_on": _d(e.joined_on),
                     "service": _service_text(e), **lv})
    return {"rows": rows, "group": group, "rule": LEAVE_RULES.get(group, (30.0, 12))}


@router.get("/employees/people/{emp_no}")
def person_file(emp_no: str, db: Session = Depends(get_db), user: models.User = PEOPLE):
    e = _by_code(db, emp_no)
    p = _profile(db, e)
    g = group_of(e, p)
    _may(user, g)
    today = M._dubai_today()
    docs = {}
    for d in db.query(models.EmployeeDocument).filter(models.EmployeeDocument.employee_id == e.id).all():
        docs.setdefault(e.id, []).append(d)
    out = {"person": _row(db, e, p, docs, today), "profile": _profile_dict(p),
           "employee": {"iban": e.iban or "", "scheme": e.scheme or "gratuity",
                        "pension": round(e.pension or 0, 2), "contract_basic": round(e.contract_basic or 0, 2),
                        "probation_end": _d(e.probation_end), "notice_days": e.notice_days or 30,
                        "total_salary": round(e.total_salary or 0, 2)},
           "documents": sorted((M._doc_dict(d, e) for d in docs.get(e.id, [])),
                               key=lambda r: r["expires_on"] or "9999"),
           "document_kinds": M.DOC_KINDS,
           "leave": leave_state(db, e, p, g, today),
           "leave_spells": sorted((_leave_dict(r, e, p, today) for r in db.query(models.LeaveRecord)
                                   .filter(models.LeaveRecord.employee_id == e.id).all()),
                                  key=lambda x: x["leave_on"] or "", reverse=True),
           "assets": [_asset_dict(a) for a in db.query(models.PeopleAsset)
                      .filter(models.PeopleAsset.employee_id == e.id).order_by(models.PeopleAsset.id).all()],
           "gratuity": M.gratuity_detail(e, db) if e.staff else
                       {"amount": 0, "entitled": False, "why": "Labour gratuity is worked out on leaving"},
           "history": [], "loans": [], "salary_history": [], "cycles": [], "absence": []}
    if e.staff:
        out["loans"] = [l for l in M.list_loans(db=db, user=user)["rows"] if l["emp_no"] == e.emp_no]
        out["salary_history"] = sorted(M.list_increments(emp_no=e.emp_no, db=db, user=user)["rows"],
                                       key=lambda r: r["effective_on"], reverse=True)
        out["absence"] = M.list_leave(month_year="", emp_no=e.emp_no, db=db, user=user)["rows"]
        lines = (db.query(models.PayrollLine).options(joinedload(models.PayrollLine.run))
                   .filter(models.PayrollLine.employee_id == e.id).all())
        for l in sorted(lines, key=lambda l: M._staff_month_bounds(l.run.month_year)[0], reverse=True):
            out["cycles"].append({
                "month_year": l.run.month_year, "status": l.run.status,
                "gross": round(l.fixed_salary or 0, 2),
                "adjust": round((l.other_allowance or 0) + (l.leave_salary or 0) + (l.air_ticket or 0) - (l.statutory or 0), 2),
                "absent": round(l.deduction or 0, 2), "loan": round(l.loan_deduction or 0, 2),
                "net": round(l.net_pay or 0, 2), "held": bool(l.held), "remarks": l.remarks or ""})
    else:
        out["salary_history"] = [
            {"effective_on": _d(h.effective_on), "kind": "rate" if h.kind == "rate" else "opening",
             "basic": round(h.basic or 0, 2), "allowance": round(h.allowance or 0, 2),
             "gross": round((h.basic or 0) + (h.allowance or 0), 2), "amount": round(h.amount or 0, 2),
             "reason": h.reason or ""}
            for h in (db.query(models.SalaryChange)
                        .filter(models.SalaryChange.employee_id == e.id,
                                models.SalaryChange.kind.in_(("rate", "opening")))
                        .order_by(models.SalaryChange.effective_on.desc(), models.SalaryChange.id.desc()).all())]
        for s in (db.query(models.EmployeeSummary).filter(models.EmployeeSummary.employee_id == e.id).all()):
            out["cycles"].append({"month_year": s.month_year, "status": "card",
                                  "present": s.present_days, "absent_days": s.absent_days,
                                  "leave_days": s.leave_days, "ot": s.ot_hours,
                                  "net": round(s.final_salary or 0, 2)})
        out["cycles"].sort(key=lambda c: M._staff_month_bounds(c["month_year"])[0] if c["month_year"] else date.min, reverse=True)
    # What changed, for this person: the app's own log filtered by his code.
    logs = (db.query(models.AuditLog).filter(models.AuditLog.details.like(f"%{e.emp_no}%"))
              .order_by(models.AuditLog.id.desc()).limit(60).all())
    users = {u.id: u.full_name or u.username for u in db.query(models.User).all()}
    out["history"] = [{"when": l.created_at.isoformat() if getattr(l, "created_at", None) else "",
                       "who": users.get(l.user_id, "system"), "action": l.action, "what": l.details}
                      for l in logs]
    return out


def _asset_dict(a):
    return {"id": a.id, "item": a.item, "tag": a.tag or "", "issued_on": _d(a.issued_on),
            "returned_on": _d(a.returned_on), "condition": a.condition or "", "notes": a.notes or ""}


# ---- Writing ---------------------------------------------------------------

@router.post("/employees/people")
def add_person(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = PEOPLE):
    """Someone new on the books. Labour goes on the same list Master Data
    keeps; anyone paid monthly goes through the staff record, so both
    pages see the same person the moment he is added."""
    g = (payload.get("group") or "").strip().lower()
    if g not in GROUPS:
        raise HTTPException(status_code=400, detail="Which register - labour, office or local?")
    _may(user, g)
    emp_no = M.norm_emp_no(payload.get("emp_no"))
    name = str(payload.get("name") or "").strip().upper()
    if not emp_no or not name:
        raise HTTPException(status_code=400, detail="A code and a full name are both needed.")
    if M.find_by_code(db, emp_no):
        raise HTTPException(status_code=400, detail=f"{emp_no} is already in use. Pick the next free code.")
    joined = M._as_date(payload.get("joined_on"))
    if not joined:
        raise HTTPException(status_code=400, detail="A joining date is needed - service and leave run from it.")
    if g == "labour":
        basic = float(payload.get("basic") or 0)
        gross = float(payload.get("gross") or 0) or round(basic + float(payload.get("allowance") or 0), 2)
        e = models.Employee(emp_no=emp_no, name=name, trade=(payload.get("trade") or payload.get("designation") or "").strip(),
                            company=(payload.get("company") or "Infinia"),
                            pay_type="fixed" if payload.get("pay_type") == "fixed" else "daily",
                            total_salary=gross, basic_salary=basic, staff=False, active=True,
                            joined_on=joined)
        if payload.get("company_id"):
            c = M._hr_company(db, company_id=payload["company_id"])
            if c:
                e.company_id = c.id; e.company = c.short_name or c.name
        db.add(e); db.commit()
    else:
        payload = dict(payload)
        payload["pay_group"] = "local" if g == "local" else "staff"
        M.add_staff(payload, db=db, user=user)
        e = _by_code(db, emp_no)
    p = _profile(db, e, create=True)
    p.group = g
    db.commit()
    M.log_action(db, user.id, "person_added", f"{e.emp_no} {e.name} ({GROUPS[g]}) joined {joined}")
    return person_file(emp_no, db=db, user=user)


EMPLOYEE_TEXT = ("designation", "pay_route", "iban", "scheme")
EMPLOYEE_DATES = (("joined_on", "joined_on"), ("terminated_on", "terminated_on"), ("probation_end", "probation_end"))


@router.put("/employees/people/{emp_no}")
def save_person(emp_no: str, payload: dict = Body(...), db: Session = Depends(get_db),
                user: models.User = PEOPLE):
    """The person's file. Employee fields go to the employee row - the
    one Master Data and the Staff Register show - and the HR fields to
    his profile. Salary is not changed here: for staff it goes through
    Increments, for labour through Master Data, so a figure never
    changes without the record of why."""
    e = _by_code(db, emp_no)
    p = _profile(db, e, create=True)
    before = group_of(e, p)
    _may(user, before)
    prof = payload.get("profile") or {}
    emp = payload.get("employee") or {}
    # Register tab.
    g = (payload.get("group") or "").strip().lower()
    if g and g not in GROUPS:
        raise HTTPException(status_code=400, detail="Which register - office or local? (Household staff are on the office register.)")
    if g and g != before:
        if (g == "labour") != (before == "labour"):
            raise HTTPException(status_code=400,
                detail="Labour and monthly-paid staff are paid differently. A person cannot be moved "
                       "between the labour register and the others here.")
        _may(user, g)
        if g == "local" and (e.scheme or "gratuity") != "pension":
            raise HTTPException(status_code=400, detail="Local staff are UAE nationals on GPSSA pension. "
                                "Household and other staff stay on the office register.")
        p.group = g
        e.pay_group = "local" if g == "local" else "staff"
    if "name" in emp and str(emp["name"]).strip():
        e.name = str(emp["name"]).strip().upper()
    for f in EMPLOYEE_TEXT:
        if f in emp:
            setattr(e, f, (emp.get(f) or "").strip())
            if f == "designation" and not e.staff:
                e.trade = e.designation
    if emp.get("company_id"):
        c = M._hr_company(db, company_id=emp["company_id"])
        if c:
            e.company_id = c.id; e.company = c.short_name or c.name
    for f, col in EMPLOYEE_DATES:
        if f in emp:
            setattr(e, col, M._as_date(emp.get(f)))
    # A labourer's rate, changed from his file: the same record Master Data
    # edits, dated and kept as history, and his cards worked out again.
    rate_changed = False
    if not e.staff and any(k in emp for k in ("basic", "allowance", "gross")):
        if not (user.role == "admin" or "masterdata" in M.effective_permissions(user)):
            raise HTTPException(status_code=403, detail="Changing a labourer's rate needs the Master Data right.")
        nb = float(emp["basic"]) if emp.get("basic") not in (None, "") else float(e.basic_salary or 0)
        if emp.get("gross") not in (None, ""):
            nt = float(emp["gross"])
        elif emp.get("allowance") not in (None, ""):
            nt = nb + float(emp["allowance"])
        else:
            nt = float(e.total_salary or 0)
        if nb < 0 or nt < nb:
            raise HTTPException(status_code=400, detail="The monthly salary cannot be less than the basic.")
        when = M._as_date(emp.get("effective_on")) or M._dubai_today()
        if when > M._dubai_today():
            raise HTTPException(status_code=400, detail="A new rate starts today or earlier - enter it when it starts.")
        rate_changed = M._record_labour_rate(db, e, nb, nt, when, emp.get("reason") or "Changed on the staff file", user.id)
        e.basic_salary, e.total_salary = round(nb, 2), round(nt, 2)
    if "pension" in emp and e.staff:
        e.pension = float(emp.get("pension") or 0)
    if "notice_days" in emp:
        e.notice_days = int(emp.get("notice_days") or 30)
    if e.terminated_on and e.terminated_on <= M._dubai_today():
        e.active = False
    elif "active" in emp:
        e.active = bool(emp["active"])
    for c in models.PeopleProfile.__table__.columns:
        k = c.name
        if k in ("id", "employee_id", "group", "created_at", "updated_at") or k not in prof:
            continue
        v = prof.get(k)
        if k in PROFILE_DATES:
            v = M._as_date(v)
        elif k in PROFILE_NUMBERS:
            v = float(v) if v not in (None, "") else None
            if k == "leave_opening":
                v = v or 0.0
            if k in ("leave_months", "ticket_every_years") and v is not None:
                v = int(v)
        else:
            v = (v or "").strip() if isinstance(v, str) else v
        setattr(p, k, v)
    db.commit()
    # A leaving date set here has the same effect as on Master Data: the
    # days after it on the attendance grid read Terminated.
    if not e.staff and e.terminated_on:
        after = (db.query(models.DailyRow).filter(models.DailyRow.emp_no == e.emp_no,
                                                    models.DailyRow.full_date > e.terminated_on).all())
        for r in after:
            r.am = r.pm = "Terminated"; r.site = ""; r.engineer = ""; r.ot = 0; r.bh = 0
        if after:
            db.commit()
        # His cards follow at once, and a later cycle's empty card goes.
        import services
        for (cycle,) in (db.query(models.EmployeeSummary.month_year)
                           .filter(models.EmployeeSummary.emp_no == e.emp_no).distinct().all()):
            services.recalculate_summary(db, e, cycle)
        M.drop_leaver_cards(db)
    if rate_changed:
        import services
        for (cycle,) in (db.query(models.EmployeeSummary.month_year)
                           .filter(models.EmployeeSummary.emp_no == e.emp_no).distinct().all()):
            services.recalculate_summary(db, e, cycle)
        db.commit()
        M.log_action(db, user.id, "labour_rate", f"{e.emp_no} {e.name}: rate {e.basic_salary:,.2f} basic, {e.total_salary:,.2f} a month")
    M.log_action(db, user.id, "person_saved", f"{e.emp_no} {e.name}: file updated")
    return person_file(emp_no, db=db, user=user)


@router.delete("/employees/people/{emp_no}")
def remove_person(emp_no: str, db: Session = Depends(get_db), user: models.User = PEOPLE):
    """A record added by mistake. Only while nothing hangs off it: once a
    person has attendance, a salary card, a cycle or a loan he is part of
    the books and is marked as left instead of removed."""
    e = _by_code(db, emp_no)
    _may(user, group_of(e, _profile(db, e)))
    ties = []
    if db.query(models.DailyRow).filter(models.DailyRow.employee_id == e.id).first():
        ties.append("attendance")
    if db.query(models.EmployeeSummary).filter(models.EmployeeSummary.employee_id == e.id).first():
        ties.append("salary cards")
    if db.query(models.PayrollLine).filter(models.PayrollLine.employee_id == e.id).first():
        ties.append("salary cycles")
    if db.query(models.StaffLoan).filter(models.StaffLoan.employee_id == e.id).first():
        ties.append("loans")
    if ties:
        raise HTTPException(status_code=400,
            detail=f"{e.name} has {', '.join(ties)} on file, so the record stays. Give a leaving date instead.")
    for model in (models.PeopleProfile, models.PeopleAsset, models.EmployeeDocument,
                  models.SalaryChange, models.StaffLeave):
        db.query(model).filter(model.employee_id == e.id).delete()
    name = e.name
    db.delete(e); db.commit()
    M.log_action(db, user.id, "person_removed", f"{emp_no} {name} (added by mistake)")
    return {"ok": True}


@router.post("/employees/people/{emp_no}/assets")
def add_asset(emp_no: str, payload: dict = Body(...), db: Session = Depends(get_db),
              user: models.User = PEOPLE):
    e = _by_code(db, emp_no)
    _may(user, group_of(e, _profile(db, e)))
    item = (payload.get("item") or "").strip()
    if not item:
        raise HTTPException(status_code=400, detail="What was issued?")
    a = models.PeopleAsset(employee_id=e.id, item=item, tag=(payload.get("tag") or "").strip(),
                           issued_on=M._as_date(payload.get("issued_on")) or M._dubai_today(),
                           condition=(payload.get("condition") or "").strip(),
                           notes=(payload.get("notes") or "").strip())
    db.add(a); db.commit()
    M.log_action(db, user.id, "asset_issued", f"{e.emp_no}: {item} {a.tag}".strip())
    return _asset_dict(a)


@router.put("/employees/people/assets/{asset_id}")
def save_asset(asset_id: int, payload: dict = Body(...), db: Session = Depends(get_db),
               user: models.User = PEOPLE):
    a = db.query(models.PeopleAsset).filter(models.PeopleAsset.id == asset_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="That item is not on file.")
    for f in ("item", "tag", "condition", "notes"):
        if f in payload:
            setattr(a, f, (payload.get(f) or "").strip())
    for f in ("issued_on", "returned_on"):
        if f in payload:
            setattr(a, f, M._as_date(payload.get(f)))
    if not a.item:
        raise HTTPException(status_code=400, detail="What was issued?")
    db.commit()
    return _asset_dict(a)


@router.delete("/employees/people/assets/{asset_id}")
def delete_asset(asset_id: int, db: Session = Depends(get_db), user: models.User = PEOPLE):
    a = db.query(models.PeopleAsset).filter(models.PeopleAsset.id == asset_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="That item is not on file.")
    db.delete(a); db.commit()
    return {"ok": True}


def seed_leave_records(SessionLocal):
    """The labour leave sheet as it stood (LABOURS_LEAVE_DETAILS.xlsx),
    put in once and matched on the employee code. Never again after that,
    so nothing typed in the app is overwritten."""
    import json, os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "deploy", "leave_records.json")
    db = SessionLocal()
    try:
        if db.query(models.Setting).filter(models.Setting.key == "leave_records_seeded").first():
            return
        added, missing = 0, []
        if os.path.exists(path):
            for x in json.load(open(path)):
                e = db.query(models.Employee).filter(models.Employee.emp_no == x["emp_no"]).first()
                if not e:
                    missing.append(x["emp_no"]); continue
                db.add(models.LeaveRecord(employee_id=e.id, leave_type=x["leave_type"], status=x["status"],
                                          leave_on=M._as_date(x["leave_on"]), return_on=M._as_date(x.get("return_on")),
                                          approved_days=x.get("approved_days"), approved_by=x.get("approved_by", ""),
                                          remark=x.get("remark", "")))
                added += 1
        db.add(models.Setting(key="leave_records_seeded", value="1"))
        db.commit()
        print(f"Leave register: {added} spell(s) loaded from the sheet" + (f"; not on file: {', '.join(missing)}" if missing else ""))
    except Exception as ex:                       # a failed seed must never stop the app
        db.rollback()
        print(f"Leave register seed skipped: {ex}")
    finally:
        db.close()


# ---- Reports ---------------------------------------------------------------

REGISTER_MONEY = ["Basic", "Allowance", "Gross"]


def _register_parts(db, group, company_id=None, user=None):
    d = list_people(group=group, include_left=(group == "left"), company_id=company_id, db=db, user=user)
    rows = [{"Code": r["emp_no"], "Name": r["name"], "Designation": r["designation"] or "-",
             "Company": r["company"], "Nationality": r["nationality"] or "-",
             "Joined": M._dmy(M._as_date(r["joined_on"])) if r["joined_on"] else "-",
             "Service": r["service"] or "-", "Basic": r["basic"], "Allowance": r["allowance"],
             "Gross": r["gross"], "Paid By": r["pay_route"].upper(),
             "Next Expiry": M._dmy(M._as_date(r["soonest_expiry"])) if r["soonest_expiry"] else "-",
             "Leave Bal.": f"{r['leave_balance']:g}"} for r in d["rows"]]
    label = GROUPS.get(group, "Left / archived" if group == "left" else "Everyone")
    sub = f"{len(rows)} on the register   |   As at {M._dubai_today():%d %b %Y}"
    return rows, f"{label} Register", sub


def _file_parts(db, emp_no, user):
    f = person_file(emp_no, db=db, user=user)
    p, pr, lv = f["person"], f["profile"], f["leave"]
    rows = []
    def put(section, k, v):
        rows.append({"Section": section, "Item": k, "Detail": v if v not in ("", None) else "-"})
    put("Identity", "Full name", p["name"]); put("Identity", "Code", p["emp_no"])
    put("Identity", "Date of birth", M._dmy(M._as_date(pr["date_of_birth"])) if pr["date_of_birth"] else "")
    for k, lbl in (("gender", "Gender"), ("nationality", "Nationality"), ("marital_status", "Marital status"),
                   ("religion", "Religion"), ("blood_group", "Blood group"), ("mobile", "Mobile"),
                   ("personal_email", "Personal email"), ("work_email", "Work email"),
                   ("uae_address", "UAE address"), ("home_address", "Home-country address"),
                   ("home_phone", "Home-country phone")):
        put("Identity", lbl, pr[k])
    put("Identity", "Emergency contact", " · ".join(x for x in (pr["emergency_name"], pr["emergency_relation"], pr["emergency_phone"]) if x))
    put("Employment", "Register", p["group_label"]); put("Employment", "Company", p["company"])
    put("Employment", "Designation", p["designation"]); put("Employment", "Department", pr["department"])
    put("Employment", "Joined", M._dmy(M._as_date(p["joined_on"])) if p["joined_on"] else "")
    put("Employment", "Service", p["service"]); put("Employment", "Reports to", pr["reports_to"])
    put("Employment", "Employment type", pr["employment_type"]); put("Employment", "Contract no.", pr["contract_no"])
    put("Employment", "Contract expiry", M._dmy(M._as_date(pr["contract_expiry"])) if pr["contract_expiry"] else "")
    put("Employment", "MOHRE no.", pr["mohre_no"])
    put("Employment", "Status", "Active" if p["active"] else f"Left {M._dmy(M._as_date(p['terminated_on'])) if p['terminated_on'] else ''}")
    put("Pay", "Basic", f"{p['basic']:,.2f}"); put("Pay", "Allowance", f"{p['allowance']:,.2f}")
    put("Pay", "Gross", f"{p['gross']:,.2f}"); put("Pay", "Paid by", p["pay_route"].upper())
    put("Pay", "Bank", pr["bank_name"]); put("Pay", "IBAN", f["employee"]["iban"])
    put("Pay", "End of service", {"gratuity": "Gratuity", "pension": "GPSSA pension", "none": "Not entitled"}.get(f["employee"]["scheme"], ""))
    if f["gratuity"].get("entitled"):
        put("Pay", "Gratuity to date", f"{f['gratuity']['amount']:,.2f}")
    put("Pay", "ILOE", pr["iloe"])
    for d in f["documents"]:
        put("Documents", d["kind_label"], f"{d['number'] or '-'}   expires {M._dmy(M._as_date(d['expires_on']))}"
            + (f"   ({d['days_left']} days)" if d["days_left"] is not None else ""))
    put("Leave", "Rule", lv["rule"]); put("Leave", "Accrued", f"{lv['accrued']:g} days")
    put("Leave", "Taken", f"{lv['taken']:g} days"); put("Leave", "Balance", f"{lv['balance']:g} days")
    put("Leave", "Next due", M._dmy(M._as_date(lv["next_due"])) if lv["next_due"] else "")
    put("Leave", "Last vacation", lv["last_vacation"])
    for l in f["loans"]:
        put("Loans", f"Taken {M._dmy(M._as_date(l['taken_on'])) if l.get('taken_on') else ''}",
            f"{l['amount']:,.2f}   balance {l['balance']:,.2f}")
    put("Housing", "Accommodation", pr["accommodation"]); put("Housing", "Room", pr["room"])
    put("Housing", "Transport", pr["transport"])
    for a in f["assets"]:
        put("Assets", a["item"], f"{a['tag'] or ''} issued {M._dmy(M._as_date(a['issued_on'])) if a['issued_on'] else '-'}"
            + (f", returned {M._dmy(M._as_date(a['returned_on']))}" if a["returned_on"] else ""))
    if pr["notes"]:
        put("Notes", "Notes", pr["notes"])
    return rows, f"Personal File - {p['emp_no']} {p['name']}", f"{p['designation']} · {p['company']} · As at {M._dubai_today():%d %b %Y}"


def _due_parts(db, days, group, user=None):
    d = documents_due(days=days, group=group, db=db, user=user)
    rows = [{"Register": r["group_label"], "Code": r["emp_no"], "Name": r["name"], "Document": r["kind_label"],
             "Number": r["number"] or "-", "Expires": M._dmy(M._as_date(r["expires_on"])),
             "Days Left": ("expired %dd" % -r["days_left"]) if r["days_left"] is not None and r["days_left"] < 0
                          else ("today" if r["days_left"] == 0 else r["days_left"]),
             "Company": r["company"]} for r in d["rows"]]
    return rows, f"Documents Due Within {days} Days", f"{len(rows)} document(s)   |   As at {M._dubai_today():%d %b %Y}"


def _leave_parts(db, group, user=None):
    d = leave_balances(group=group, db=db, user=user)
    rows = [{"Code": r["emp_no"], "Name": r["name"], "Designation": r["designation"] or "-",
             "Joined": M._dmy(M._as_date(r["joined_on"])) if r["joined_on"] else "-", "Service": r["service"] or "-",
             "Rule": r["rule"], "Accrued": f"{r['accrued']:g}", "Taken": f"{r['taken']:g}",
             "Balance": f"{r['balance']:g}",
             "Next Due": M._dmy(M._as_date(r["next_due"])) if r["next_due"] else "-",
             "Last Vacation": r["last_vacation"] or "-"} for r in d["rows"]]
    return rows, f"Leave Balances - {GROUPS.get(group, 'Everyone')}", f"{len(rows)} people   |   As at {M._dubai_today():%d %b %Y}"


def _bday_parts(db, group, user=None):
    d = birthdays_upcoming(group=group, db=db, user=user)
    rows = [{"Birthday": M._as_date(r["next"]).strftime("%a %d %b"),
             "In": "Today" if r["days"] == 0 else ("Tomorrow" if r["days"] == 1 else f"{r['days']} days"),
             "Code": r["emp_no"], "Name": r["name"], "Register": r["group_label"], "Designation": r["role"] or "-",
             "Date of Birth": M._dmy(M._as_date(r["dob"])), "Turns": r["turns"]} for r in d["rows"]]
    sub = f"{len(rows)} people, next birthday first   |   From {M._dubai_today():%d %b %Y}"
    if d["missing"]:
        sub += f"   |   {d['missing']} without a date of birth on file"
    return rows, f"Birthdays - {GROUPS.get(group, 'Everyone')}", sub


def _leave_reg_parts(db, group, show, user=None):
    d = leave_register(group=group, show=show, db=db, user=user)
    dm = lambda v: M._dmy(M._as_date(v)) if v else ""
    rows = [{"Staff": r["name"], "Employee Code": r["emp_no"], "Designation": r["designation"],
             "Leave Type": r["leave_type_label"], "Date of Leave": dm(r["leave_on"]),
             "Date of Return": dm(r["return_on"]) or (f"due {dm(r['due_back'])}" if r["due_back"] else ""),
             "Approved Days": r["approved_days"] if r["approved_days"] is not None else "",
             "Status": r["standing"] + (f" {r['days_late']} d" if r["days_late"] else ""),
             "Approved By": r["approved_by"], "Contact - Home Country": r["home_phone"],
             "Remark": r["remark"]} for r in d["rows"]]
    # A column nobody has filled in yet is left off, not printed empty.
    keep = [k for k in (rows[0] if rows else {}) if any(str(x[k]).strip() for x in rows)]
    rows = [{k: x[k] or "-" for k in keep} for x in rows]
    c = d["counts"]
    label = {"labour": "Labour", "office": "Office Staff", "local": "Local Staff"}.get(group, "All Staff")
    what = {"away": "on leave now", "pending": "pending", "upcoming": "approved, not yet gone", "returned": "returned"}.get(show)
    sub = (f"{len(rows)} {what}" if what else
           f"{c['away']} on leave   |   {c['pending']} pending   |   {c['upcoming']} approved, not yet gone   |   {c['returned']} returned")
    sub += f"   |   As at {M._dubai_today():%d %b %Y}"
    return rows, f"{label} - Leave Details", sub


def _reader(token, db):
    user = auth.get_download_user_from_token(token, db)
    if not allowed_groups(user):
        raise HTTPException(status_code=403, detail="Not available to this login.")
    return user


def _report(kind, db, user, group="", emp_no="", days=90, company_id=None, show=""):
    if kind == "register":
        if group in GROUPS:
            _may(user, group)
        return _register_parts(db, group, company_id, user), REGISTER_MONEY
    if kind == "file":
        return _file_parts(db, emp_no, user), []
    if kind == "documents-due":
        if group:
            _may(user, group)
        return _due_parts(db, days, group, user), []
    if kind == "leave":
        _may(user, group)
        return _leave_parts(db, group, user), []
    if kind == "birthdays":
        return _bday_parts(db, group, user), []
    if kind == "leave-register":
        return _leave_reg_parts(db, group, show, user), []
    raise HTTPException(status_code=404, detail="No such report.")


@router.get("/export/people/{kind}")
def export_people(kind: str, token: str, format: str = "pdf", group: str = "", emp_no: str = "",
                  days: int = 90, company_id: int = None, show: str = "", db: Session = Depends(get_db)):
    user = _reader(token, db)
    (rows, title, sub), money = _report(kind, db, user, group, emp_no, days, company_id, show)
    return M._hr_file(title, rows, sub, format, money, "People_" + kind.replace("-", "_").title())


@router.get("/export/people/{kind}/view")
def view_people(kind: str, token: str, group: str = "", emp_no: str = "", days: int = 90,
                company_id: int = None, show: str = "", db: Session = Depends(get_db)):
    user = _reader(token, db)
    (rows, title, sub), money = _report(kind, db, user, group, emp_no, days, company_id, show)
    t = quote(auth.create_view_token(user.username), safe="")
    url = (f"/export/people/{kind}?token={t}&group={quote(group)}&emp_no={quote(emp_no)}&days={days}&show={quote(show)}"
           + (f"&company_id={company_id}" if company_id else ""))
    return M._preview_page(title, sub, rows, url + "&format=pdf", url + "&format=excel",
                           money_cols=money, total_cols=money or None)


# ---- Access: named roles ---------------------------------------------------

def _role_dict(r, db):
    members = db.query(models.User).filter(models.User.access_role_id == r.id).all()
    return {"id": r.id, "name": r.name, "notes": r.notes or "",
            "screens": [s for s in (r.screens or "").split(",") if s],
            "members": [{"id": u.id, "username": u.username, "full_name": u.full_name, "active": u.active}
                        for u in members]}


@router.get("/permissions/roles")
def list_roles(db: Session = Depends(get_db), user: models.User = ACCESS):
    return {"rows": [_role_dict(r, db) for r in db.query(models.AccessRole).order_by(models.AccessRole.name).all()],
            "screens": M.ALL_SCREENS, "role_defaults": M.ROLE_DEFAULTS,
            "labels": SCREEN_LABELS, "pages": RIGHT_PAGES}


SCREEN_LABELS = {
    "dashboard": "Dashboard", "attendance": "Daily attendance", "masterdata": "Labour master data",
    "reports": "Labour reports", "combine": "Salary cards", "adjustments": "Salary adjustments",
    "livecard": "Live card", "store": "Store / inventory", "requests": "Material requests",
    "approvals": "Approvals, orders, LPO register, suppliers", "errorcheck": "Check before you pay",
    "settings": "Settings", "activity": "Activity monitor", "hrpayroll": "Office HR & Payroll (office salaries)",
    "storekeeper": "Record stock in / out", "people_labour": "Labour register",
    "people_office": "Office staff register incl. household (office salaries)", "people_local": "Local staff register",
    "expiry": "Expiry reminder - documents, NOCs, permits, licences (no salaries)",
    "pdc": "PDC tracker - post-dated cheques (admin and chief accountant)",
    "petty_site": "Site petty cash", "petty_pro": "PRO petty cash", "petty_office": "Office petty cash",
    "petty_naveen": "Naveen petty cash (admin and chief accountant)", "petty_praveen": "Praveen petty cash (admin and chief accountant)",
    "accounts_invoices": "Tax & proforma invoices",
    "accounts_register": "Cash register (opens with its own password)",
    "accounts_projects": "Project payment tracker (admin and chief accountant)",
}
# The rights as the pages and tabs show them, so a role is ticked the
# way the app is laid out.
RIGHT_PAGES = [
    ("Dashboard", ["dashboard"]),
    ("Attendance", ["attendance", "livecard", "masterdata"]),
    ("Staff", ["people_labour", "people_office", "people_local"]),
    ("Payroll", ["combine", "adjustments", "errorcheck", "hrpayroll"]),
    ("Store & Purchasing", ["store", "storekeeper", "requests", "approvals"]),
    ("Expiry Reminder", ["expiry", "pdc"]),
    ("Accounts", ["accounts_invoices", "petty_site", "petty_pro", "petty_office", "petty_naveen", "petty_praveen", "accounts_projects", "accounts_register"]),
    ("Reports", ["reports"]),
    ("Settings", ["settings"]),
    ("Activity Monitor", ["activity"]),
]


def _apply_role(db, u, r):
    u.access_role_id = r.id
    u.permissions = r.screens or ""


@router.post("/permissions/roles")
def save_role(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = ACCESS):
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="The role needs a name.")
    screens = [s.strip() for s in (payload.get("screens") or []) if s.strip()]
    bad = [s for s in screens if s not in M.ALL_SCREENS]
    if bad:
        raise HTTPException(status_code=400, detail=f"Unknown screen(s): {', '.join(bad)}")
    if "settings" not in screens:
        screens.append("settings")   # everyone changes their own password there
    r = None
    if payload.get("id"):
        r = db.query(models.AccessRole).filter(models.AccessRole.id == payload["id"]).first()
    clash = db.query(models.AccessRole).filter(models.AccessRole.name == name).first()
    if clash and (not r or clash.id != r.id):
        raise HTTPException(status_code=400, detail=f"There is already a role called {name}.")
    if not r:
        r = models.AccessRole(name=name)
        db.add(r)
    r.name = name; r.screens = ",".join(screens); r.notes = (payload.get("notes") or "").strip()
    db.flush()
    # Everyone carrying the role gets its new rights, straight away.
    for u in db.query(models.User).filter(models.User.access_role_id == r.id).all():
        _apply_role(db, u, r)
    db.commit()
    M.log_action(db, user.id, "role_saved", f"{name}: {r.screens}")
    return _role_dict(r, db)


@router.delete("/permissions/roles/{role_id}")
def delete_role(role_id: int, db: Session = Depends(get_db), user: models.User = ACCESS):
    r = db.query(models.AccessRole).filter(models.AccessRole.id == role_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="That role is not on file.")
    # The logins keep the rights they have; they just stop following the role.
    for u in db.query(models.User).filter(models.User.access_role_id == r.id).all():
        u.access_role_id = None
    db.delete(r); db.commit()
    M.log_action(db, user.id, "role_deleted", r.name)
    return {"ok": True}


@router.get("/permissions/roles/users")
def users_with_roles(db: Session = Depends(get_db), user: models.User = ACCESS):
    roles = {r.id: r.name for r in db.query(models.AccessRole).all()}
    out = []
    for u in db.query(models.User).order_by(models.User.username).all():
        out.append({"id": u.id, "username": u.username, "full_name": u.full_name, "role": u.role,
                    "active": u.active, "access_role_id": u.access_role_id,
                    "access_role": roles.get(u.access_role_id, ""),
                    "screens": M.effective_permissions(u)})
    return {"rows": out}


@router.post("/permissions/roles/assign")
def assign_role(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = ACCESS):
    u = db.query(models.User).filter(models.User.id == payload.get("user_id")).first()
    if not u:
        raise HTTPException(status_code=404, detail="That login is not on file.")
    rid = payload.get("role_id")
    # Make an existing login an admin - or take admin away - here, so a
    # person never needs a second login to be promoted. The last admin
    # can never be demoted, and nobody demotes himself.
    if rid == "admin":
        if u.role != "admin":
            u.role = "admin"
            u.access_role_id = None
            db.commit()
            M.log_action(db, user.id, "made_admin", f"{u.username} is now an admin")
        return {"ok": True, "screens": M.effective_permissions(u)}
    if u.role == "admin":
        if u.id == user.id:
            raise HTTPException(status_code=400, detail="You cannot take admin away from your own login.")
        if db.query(models.User).filter(models.User.role == "admin", models.User.id != u.id).count() == 0:
            raise HTTPException(status_code=400, detail="This is the only admin. Make someone else an admin first.")
        if not rid:
            raise HTTPException(status_code=400, detail="Pick the role he should have instead of admin.")
        u.role = "office"
    if not rid:
        u.access_role_id = None
        db.commit()
        return {"ok": True, "screens": M.effective_permissions(u)}
    r = db.query(models.AccessRole).filter(models.AccessRole.id == rid).first()
    if not r:
        raise HTTPException(status_code=404, detail="That role is not on file.")
    _apply_role(db, u, r)
    db.commit()
    M.log_action(db, user.id, "role_assigned", f"{u.username} -> {r.name}")
    return {"ok": True, "screens": M.effective_permissions(u)}


@router.post("/permissions/roles/new-user")
def new_user_with_role(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = ACCESS):
    """A login made from a role: the role's rights from the first sign-in."""
    username = (payload.get("username") or "").strip().lower()
    password = payload.get("password") or ""
    full_name = (payload.get("full_name") or "").strip()
    if not username or not full_name:
        raise HTTPException(status_code=400, detail="A username and a full name are both needed.")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="A password of at least six characters.")
    if db.query(models.User).filter(models.User.username == username).first():
        raise HTTPException(status_code=400, detail=f"{username} is already a login.")
    r = db.query(models.AccessRole).filter(models.AccessRole.id == payload.get("role_id")).first()
    if not r:
        raise HTTPException(status_code=400, detail="Pick the role first.")
    base = "site" if (payload.get("base") or "") == "site" else "office"
    u = models.User(username=username, hashed_password=auth.hash_password(password),
                    full_name=full_name, role=base, active=True)
    db.add(u); db.flush()
    _apply_role(db, u, r)
    db.commit()
    M.log_action(db, user.id, "user_created", f"{username} ({r.name})")
    return {"ok": True, "id": u.id, "screens": M.effective_permissions(u)}

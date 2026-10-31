"""Watch: changes that could hide a loss, told to the admin only.

Anything a member of staff does that takes stock, money or a record away
quietly - a stock line deleted, a loan lowered, a repayment entered, a
paid cycle reopened, a backup taken home - is written here as an alert.
The admin sees it on the bell and on the phone; nobody else sees it,
and what an admin does himself is not reported back to him.

Most alerts come straight from the activity log (log_action calls
`from_log`); a few need a check first (a past cycle, a back-dated line,
a run of wrong passwords, a new device) and are raised where that is
known, with `alert`.
"""
from datetime import datetime, timedelta

from sqlalchemy import Column, Integer, String, Text, DateTime

from database import Base


# Switched off on 12 Oct 2026 at the owner's request (too many alerts).
# Nothing is raised and the bell shows none while this is False; the
# code stays so it can be turned back on with one change.
ENABLED = False


class WatchAlert(Base):
    __tablename__ = "watch_alerts"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=True, index=True)
    who = Column(String, default="")
    action = Column(String, default="", index=True)
    title = Column(String, default="")
    detail = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


# action -> title. Raised for anyone but an admin.
FROM_LOG = {
    # Store and stock
    "store_remove_item": "Stock item deleted",
    "store_delete_movement": "Stock movement deleted",
    "opening_stock": "Stock counted in by hand",
    "stock_owner_corrected": "Stock moved to another owner / site (correction)",
    "material_request_delete": "Material request deleted",
    "hire_return_edited": "Hire return edited",
    "hire_return_cancelled": "Hire return cancelled",
    "store_reset": "Store reset",
    # Purchasing and accounts
    "edit_lpo": "LPO edited",
    "cancel_lpo": "LPO cancelled",
    "delete_supplier": "Supplier deleted",
    "merge_supplier": "Supplier merged into another (duplicate)",
    "invoice_edit": "Invoice edited",
    "invoice_cancel": "Invoice cancelled",
    "credential_shown": "Password shown / copied (Credentials)",
    "credentials_exported": "Credentials list with passwords opened / downloaded",
    "credential_changed": "Saved login changed (Credentials)",
    "credential_deleted": "Saved login deleted (Credentials)",
    "seccheque_changed": "Security cheque changed",
    "seccheque_deleted": "Security cheque deleted",
    "pdc_edit": "PDC changed",
    "pdc_delete": "PDC deleted",
    "petty_cash_edit": "Petty cash line changed",
    "petty_cash_delete": "Petty cash line deleted",
    "register_wrong_password": "Wrong password on the cash register",
    # Payroll and HR
    "loan_changed": "Loan changed",
    "loan_removed": "Loan removed",
    "loan_repaid": "Loan repayment entered",
    "repayment_changed": "Loan repayment changed",
    "repayment_removed": "Loan repayment removed",
    "pay_item_changed": "Addition / deduction changed",
    "pay_item_removed": "Addition / deduction removed",
    "payroll_reopened": "Approved payroll reopened",
    "salary_history_changed": "Salary history changed",
    "salary_history_removed": "Salary history line removed",
    "labour_rate_corrected": "Labour rate history corrected",
    "remove_adjustment": "Labour addition / deduction removed",
    "clear_day": "A whole attendance day cleared",
    "leave_changed": "Absence / leave changed",
    "leave_removed": "Absence / leave removed",
    "leave_deleted": "Leave register entry deleted",
    "delete_employee": "Employee deleted",
    # Access and security
    "made_admin": "Someone made admin",
    "set_permissions": "Permissions changed",
    "role_saved": "Access role changed",
    "role_deleted": "Access role deleted",
    "role_assigned": "Access role given to a login",
    "create_user": "Login created",
    "user_created": "Login created",
    "delete_user": "Login deleted",
    "reset_password": "Password reset for another login",
    "restore_backup": "Backup restored",
    "download_backup": "Backup downloaded",
    "delete_backup": "Backup deleted",
}
# Logged for routine work too: only these wordings are alerts.
ONLY_IF = {
    "project_payment": (("changed", "removed"), "Project payment changed / removed"),
    "register_entry": (("changed", "removed"), "Cash register entry changed / removed"),
    "store_movement": (("lost ", "adjust "), "Stock written off / count corrected"),
}

# Every action this can raise, for the Activity Monitor and the tests.
ALL = set(FROM_LOG) | set(ONLY_IF) | {"attendance_past", "rejoined", "rate_changed", "staff_pay_changed",
                                     "iban_changed", "petty_backdated", "login_burst", "login_new_device"}


def _user(db, models, uid):
    return db.query(models.User).filter(models.User.id == uid).first() if uid else None


def alert(db, models, user, action, title, detail="", admin_too=False):
    """Write one alert. Not for an admin's own work, unless admin_too
    (a sign-in matter, where the admin is the one to be told)."""
    if not ENABLED or user is None or (user.role == "admin" and not admin_too):
        return None
    a = WatchAlert(user_id=user.id, who=user.full_name or user.username, action=action,
                   title=title, detail=(detail or "")[:500])
    db.add(a)
    db.commit()
    return a


def from_log(db, models, user_id, action, details):
    """Called by log_action for every entry: raise the ones that matter."""
    title = FROM_LOG.get(action)
    if not title and action in ONLY_IF:
        words, t = ONLY_IF[action]
        d = (details or "").lower()
        if any(w in d for w in words):
            title = t
    if not title:
        return None
    u = _user(db, models, user_id)
    if action == "reset_password" and u and (details or "").strip() == u.username:
        return None                      # his own password
    return alert(db, models, u, action, title, details)


def login_failed(db, models, user, where=""):
    """Five wrong passwords on one login inside ten minutes: one alert."""
    since = datetime.utcnow() - timedelta(minutes=10)
    n = (db.query(models.AuditLog).filter(models.AuditLog.user_id == user.id,
                                          models.AuditLog.action == "login_failed").all())
    recent = [x for x in n if x.created_at and x.created_at.replace(tzinfo=None) >= since]
    if len(recent) < 5:
        return None
    if db.query(WatchAlert).filter(WatchAlert.user_id == user.id, WatchAlert.action == "login_burst",
                                   WatchAlert.created_at >= since).first():
        return None
    return alert(db, models, user, "login_burst", f"{len(recent)} wrong passwords in 10 minutes",
                 f"Login {user.username} {where}".strip(), admin_too=True)


def _device(where):
    # "from 37.245.1.2 - Chrome on Windows" -> "Chrome on Windows"
    w = (where or "").split(" - kept signed in")[0]
    return w.split(" - ", 1)[1].strip() if " - " in w else ""


def login_new_device(db, models, user, where):
    """Signed in from a browser and computer this login has never used."""
    dev = _device(where)
    if not dev:
        return None
    before = (db.query(models.AuditLog.details).filter(models.AuditLog.user_id == user.id,
                                                       models.AuditLog.action == "login").all())
    # The login just made is already in the log - one sighting is new.
    if sum(1 for (d,) in before if _device(d) == dev) > 1 or len(before) <= 1:
        return None
    return alert(db, models, user, "login_new_device", f"{user.username} signed in from a new device",
                 f"{dev} ({where.split(' - ')[0].replace('from ', '')})" if where else dev, admin_too=True)


def notifications(db, models, days=14, limit=40):
    """The bell lines - for the admin only (the caller checks)."""
    if not ENABLED:
        return []
    since = datetime.utcnow() - timedelta(days=days)
    rows = (db.query(WatchAlert).filter(WatchAlert.created_at >= since)
              .order_by(WatchAlert.id.desc()).limit(limit).all())
    out = []
    for a in rows:
        when = (a.created_at + timedelta(hours=4)) if a.created_at else datetime.utcnow()
        out.append({"id": f"watch-{a.id}", "kind": "watch", "title": f"{a.who}: {a.title}",
                    "detail": f"{a.detail}  -  {when:%d/%m/%Y %H:%M}".strip(" -"),
                    "screen": "activity", "target": "", "when": when.date().isoformat(), "level": "warn"})
    return out

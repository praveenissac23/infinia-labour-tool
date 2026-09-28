"""Who can see office salaries - read only, changes nothing.

    cd ~/infinia-labour-tool && venv/bin/python deploy/who_sees_pay.py

Lists every login and whether it can see:
  * office payroll  (Office HR & Payroll - statements, loans, increments, gratuity, exports)
  * office register (Staff > Office staff register, with salaries)
  * local staff and household registers (their salaries)
  * labour pay      (Master data / live card / salary adjustments - labourers' wages)
and where the right comes from (admin, the login's own ticks, or its role).
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, HERE)
from clear_test_returns import _find_database_url

url = _find_database_url()
if not url:
    sys.exit("Could not find DATABASE_URL.")
os.environ["DATABASE_URL"] = url
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import models
from main import effective_permissions

db = sessionmaker(bind=create_engine(url))()
roles = {r.id: r for r in db.query(models.AccessRole).all()} if hasattr(models, "AccessRole") else {}
COLS = [("hrpayroll", "OFFICE PAYROLL"), ("people_office", "OFFICE REGISTER"),
        ("people_local", "LOCAL STAFF"), ("people_household", "HOUSEHOLD")]
LABOUR = ("masterdata", "adjustments", "livecard")

rows = []
for u in db.query(models.User).order_by(models.User.username).all():
    perms = set(effective_permissions(u))
    admin = u.role == "admin"
    role = roles.get(getattr(u, "access_role_id", None))
    own = set(x.strip() for x in (u.permissions or "").split(",") if x.strip())
    def src(r):
        if admin: return "admin"
        if r not in perms: return ""
        if role and r in set(x.strip() for x in (role.screens or "").split(",")): return f"role {role.name}"
        return "own ticks" if r in own else "yes"
    rows.append((u, admin, [src(r) for r, _ in COLS], "yes" if admin or perms & set(LABOUR) else "", role))

w = max(10, max(len(u.username) for u, *_ in rows) + 2)
print(f"\n{'LOGIN':<{w}}{'NAME':<22}{'TYPE':<8}{'ACTIVE':<8}" + "".join(f"{h:<18}" for _, h in COLS) + "LABOUR PAY")
print("-" * (w + 38 + 18 * len(COLS) + 10))
for u, admin, srcs, lab, role in rows:
    print(f"{u.username:<{w}}{(u.full_name or '')[:20]:<22}{u.role:<8}{'yes' if u.active else 'NO':<8}" +
          "".join(f"{(s or '-'):<18}" for s in srcs) + (lab or "-"))

see = [u.username for u, admin, srcs, *_ in rows if u.active and (srcs[0] or srcs[1])]
print(f"\nCAN SEE OFFICE SALARIES NOW ({len(see)}): {', '.join(see) or 'nobody'}")
print("To remove a right: Settings > Access (change the role) or Settings > Logins > Change role.")

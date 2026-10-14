"""Not in Zoho after 3 days: counted per kind, from the Zoho start date,
in the bell for whoever sends to Zoho - and nobody else."""
import os, sys, tempfile
from datetime import date, timedelta
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as M, models, zohosync as Z
from database import SessionLocal, engine
models.Base.metadata.create_all(bind=engine); M._add_missing_columns()
s = SessionLocal(); fails = 0
def ok(c, m):
    global fails
    print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1
today = date(2026, 10, 20)
P = lambda d, st="", book="site": models.PettyCash(on_date=d, description="x", paid=10, book=book, zoho_status=st)
s.add_all([P(date(2026, 10, 16)), P(date(2026, 10, 17)),                 # 4 and 3 days old: counted
           P(date(2026, 10, 18)),                                       # 2 days: not yet
           P(date(2026, 10, 15), "inzoho"), P(date(2026, 10, 15), "sent"), P(date(2026, 10, 15), "skip"),  # done
           P(date(2026, 10, 16), "approved"), P(date(2026, 10, 16), "changed"),   # still not right in Zoho: counted
           P(date(2026, 9, 20))])                                       # before the start: not counted
s.add_all([models.BankEntry(kind="vendor", on_date=date(2026, 10, 10), amount=5, zoho_status=""),
           models.BankEntry(kind="vendor", on_date=date(2026, 10, 10), amount=5, zoho_status="sent")])
s.commit()
o = Z.overdue(s, today)
ok(o["petty"] == 4, f"petty: 2 waiting + approved-not-sent + changed, over 3 days, from the start date ({o['petty']})")
ok(o["bank"] == 1 and o["total"] == 5, f"bank 1, total 5 ({o})")
n = Z.overdue_notice(s, today)
ok(n and n["kind"] == "zoho" and n["count"] == 5 and "4 petty cash" in n["detail"] and "1 bank" in n["detail"], f"notice: {n}")
ok(Z.overdue_notice(s, date(2026, 10, 1)) is None, "nothing overdue - no notice")
chief = models.User(username="c", full_name="C", hashed_password="x", role="office", permissions="accounts_zoho")
keeper = models.User(username="k", full_name="K", hashed_password="x", role="site", permissions="store,petty_site")
s.add_all([chief, keeper]); s.commit()
import unittest.mock as um
with um.patch.object(M, "_dubai_today", return_value=today):
    nc = [x for x in M.get_notifications(db=s, user=chief)["notifications"] if x.get("kind") == "zoho"] if isinstance(M.get_notifications(db=s, user=chief), dict) else []
    nk = [x for x in M.get_notifications(db=s, user=keeper)["notifications"] if x.get("kind") == "zoho"] if isinstance(M.get_notifications(db=s, user=keeper), dict) else []
ok(len(nc) == 1, "the chief accountant's bell has it")
ok(not nk, "the store keeper's bell does not")
print("fails=", fails)

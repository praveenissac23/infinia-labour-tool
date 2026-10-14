"""Shafeeq's go-live answers (14 Oct 2026): 1-14 Oct Office lines not in
Zoho become Not for Zoho (he adjusts them); the directors' books are
portal only - not queued, not approvable, not in the reminder; Site and
PRO go through his approval as before."""
import os, sys, tempfile
from datetime import date
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as M, models, zohosync as Z
from database import SessionLocal, engine
models.Base.metadata.create_all(bind=engine); M._add_missing_columns()
s = SessionLocal(); fails = 0
def ok(c, m):
    global fails
    print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1
P = lambda book, d, st="": models.PettyCash(on_date=d, description=f"{book} {d}", paid=10, book=book, zoho_status=st)
s.add_all([P("office", date(2026, 10, 3)), P("office", date(2026, 10, 14)), P("office", date(2026, 10, 2), "inzoho"),
           P("office", date(2026, 10, 15)),                                   # after go-live: stays for the portal
           P("site", date(2026, 10, 5)), P("pro", date(2026, 10, 6)),
           P("naveen", date(2026, 10, 7)), P("praveen", date(2026, 10, 8))])
s.commit()
n = Z.golive_office_skip(s)
ok(n == 2, f"2 Office lines of 1-14 Oct marked Not for Zoho ({n})")
ok(Z.golive_office_skip(s) == 0, "once only")
st = {x.description: x.zoho_status for x in s.query(models.PettyCash).all()}
ok(st["office 2026-10-02"] == "inzoho" and st["office 2026-10-15"] == "", "already-in-Zoho line and the 15 Oct line untouched")
q = {r.book for r in Z._waiting(s)}
ok(q == {"site", "pro", "office"} and not ({"naveen", "praveen"} & q), f"queue: Site, PRO, Office (15 Oct) - no director books ({q})")
u = models.User(username="c", full_name="C", hashed_password="x", role="office", permissions="accounts_zoho"); s.add(u); s.commit()
nv = s.query(models.PettyCash).filter_by(book="naveen").first()
d = Z.approve({"lines": [{"id": nv.id, "account": "Office › Telephone"}]}, s, u)
ok(any("portal only" in r["why"] for r in d["refused"]) and s.get(models.PettyCash, nv.id).zoho_status == "", "a director's line cannot be approved for Zoho")
o = Z.overdue(s, date(2026, 10, 20))
ok(o["petty"] == 3, f"reminder counts Site, PRO and the 15 Oct Office line only ({o['petty']})")
print("fails=", fails)

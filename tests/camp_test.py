"""Labour accommodation: seeded from the 9 Oct sheet, vacation from leave
records, leavers freed by themselves, one bed a man, bookings, rights."""
import os, sys, tempfile, asyncio, io
from datetime import date, timedelta
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main as M, models, camp, auth
from database import SessionLocal, engine
from fastapi import HTTPException
models.Base.metadata.create_all(bind=engine); M._add_missing_columns()
s = SessionLocal(); fails = 0
def ok(c, m):
    global fails
    print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1
def refused(fn, *a):
    try:
        fn(*a); return ""
    except HTTPException as e:
        return e.detail or "refused"

today = M._dubai_today()
# staff list: every ID on the sheet, written the app's way (F-757)
ids = {x for beds in camp.SEED.values() for x in beds if x and not x.startswith("@")}
for i in sorted(ids):
    s.add(models.Employee(emp_no=f"{i[0]}-{i[1:]}", name=f"Worker {i}", trade="Helper", active=True, staff=False))
s.add(models.Employee(emp_no="F-792", name="Shailendra", active=True, staff=False))      # not on the sheet
s.add(models.Employee(emp_no="IC-001", name="Office Man", active=True, staff=True))
s.commit()
E = {e.emp_no: e for e in s.query(models.Employee).all()}
admin = models.User(username="adm", full_name="Admin", hashed_password="x", role="admin")
jomon = models.User(username="jomon", full_name="Jomon", hashed_password="x", role="office", permissions="reports,camp")
viewer = models.User(username="muh", full_name="Muhsina", hashed_password="x", role="office", permissions="reports")
s.add_all([admin, jomon, viewer]); s.commit()

# leave: F-716 away now, F-726 goes in 20 days, F-754 came back yesterday
s.add(models.LeaveRecord(employee_id=E["F-716"].id, leave_on=today - timedelta(days=40), return_on=today + timedelta(days=50), status="approved"))
s.add(models.LeaveRecord(employee_id=E["F-726"].id, leave_on=today + timedelta(days=20), status="pending"))
s.add(models.LeaveRecord(employee_id=E["F-754"].id, leave_on=today - timedelta(days=30), return_on=today - timedelta(days=1), status="approved"))
s.commit()

n = camp.seed(s)
ok(n == 90, f"9 Oct sheet loaded: 15 rooms x 6 = 90 beds ({n})")
ok(camp.seed(s) == 0, "loaded once only")
d = camp.get_camp(s, admin)
t = d["totals"]
ok(t["beds"] == 90 and t["free"] == 16, f"16 free beds, as the sheet says ({t})")
ok(t["vac"] == 1 and t["in"] == 73 and t["check"] == 3, "1 on vacation, 73 in camp incl. 3 guests to check (Sayed, Shaiju, Amal)")
B = {(r["name"], b["bed"]): b for r in d["rooms"] for b in r["beds"]}
ok(B[("50", 2)]["kind"] == "vac" and B[("50", 2)]["back"] == (today + timedelta(days=50)).isoformat(), "Avinas (F716): On vacation, back date shown, bed kept")
ok(B[("52", 3)]["kind"] == "in" and B[("52", 3)].get("soon"), "leave in 20 days: still in camp, 'leave <date>' shown")
ok(B[("61", 2)]["kind"] == "in" and not B[("61", 2)].get("soon"), "came back yesterday: in camp again")
ok(B[("55", 1)]["kind"] == "guest" and B[("55", 1)]["name"] == "Sayed", "name without ID kept as guest, to check")
ok([p["no"] for p in d["nobed"]] == ["F-792"], "active labour with no bed listed (office staff not counted)")
ok(d["may_edit"] is True and camp.get_camp(s, viewer)["may_edit"] is False, "admin can change; Labour reports alone can only look")

# rights
ok(refused(camp._editor, viewer), "viewer cannot change the camp")
ok(camp._editor(jomon) is jomon, "PRO (camp right) can change it")

R = {r.name: r for r in s.query(models.CampRoom).all()}
# assign into a free bed
camp.assign({"room_id": R["49"].id, "bed": 1, "employee_id": E["F-792"].id}, s, jomon)
d = camp.get_camp(s, jomon); B = {(r["name"], b["bed"]): b for r in d["rooms"] for b in r["beds"]}
ok(B[("49", 1)]["no"] == "F-792" and d["totals"]["free"] == 15 and not d["nobed"], "put Shailendra in room 49 bed 1")
# a taken bed refuses
ok("not free" in refused(camp.assign, {"room_id": R["49"].id, "bed": 2, "employee_id": E["IC-001"].id}, s, jomon), "an occupied bed is refused")
# move: one bed a man
camp.assign({"room_id": R["59"].id, "bed": 6, "employee_id": E["F-792"].id}, s, jomon)
d = camp.get_camp(s, jomon); B = {(r["name"], b["bed"]): b for r in d["rooms"] for b in r["beds"]}
ok(B[("49", 1)]["kind"] == "free" and B[("59", 6)]["no"] == "F-792" and d["totals"]["free"] == 15, "moving frees his old bed - never two beds")
ok(s.query(models.CampBed).filter(models.CampBed.employee_id == E["F-792"].id).count() == 1, "database holds him in one bed")
# booking, then arrival
camp.book({"room_id": R["49"].id, "bed": 1, "name": "Rakesh Kumar", "trade": "Mason", "date": (today + timedelta(days=6)).isoformat()}, s, jomon)
d = camp.get_camp(s, jomon); B = {(r["name"], b["bed"]): b for r in d["rooms"] for b in r["beds"]}
ok(B[("49", 1)]["kind"] == "book" and d["totals"]["book"] == 1 and d["totals"]["free"] == 14, "bed booked for a new joiner")
ok("not free" in refused(camp.book, {"room_id": R["49"].id, "bed": 2, "name": "X"}, s, jomon), "cannot book an occupied bed")
s.add(models.Employee(emp_no="F-802", name="Rakesh Kumar", active=True, staff=False)); s.commit()
rk = s.query(models.Employee).filter_by(emp_no="F-802").first()
camp.assign({"room_id": R["49"].id, "bed": 1, "employee_id": rk.id}, s, jomon)
b = s.query(models.CampBed).filter_by(room_id=R["49"].id, bed_no=1).first()
ok(b.employee_id == rk.id and not b.booked_name, "arrived: booking becomes his bed")
# a late booking shows 'was due'
camp.book({"room_id": R["49"].id, "bed": 4, "name": "Late Man", "date": (today - timedelta(days=2)).isoformat()}, s, jomon)
d = camp.get_camp(s, jomon); B = {(r["name"], b["bed"]): b for r in d["rooms"] for b in r["beds"]}
ok(B[("49", 4)]["late"] is True, "a booking past its date is flagged")

# termination frees the bed by itself
E["F-757"].terminated_on = today; E["F-757"].active = False; s.commit()
d = camp.get_camp(s, viewer); B = {(r["name"], b["bed"]): b for r in d["rooms"] for b in r["beds"]}
ok(B[("49", 2)]["kind"] == "free", "terminated today -> bed free automatically")
mv = s.query(models.CampMove).filter_by(employee_id=E["F-757"].id, kind="out").first()
ok(mv is not None and "automatically" in mv.reason and mv.by is None, "the automatic release is in the history")
E["F-757"].terminated_on = today + timedelta(days=10); E["F-757"].active = True; s.commit()
camp.assign({"room_id": R["49"].id, "bed": 2, "employee_id": E["F-757"].id}, s, jomon)
camp.get_camp(s, viewer)
ok(s.query(models.CampBed).filter_by(employee_id=E["F-757"].id).count() == 1, "leaving next week: bed kept until that date")
ok("still working" in refused(camp.assign, {"room_id": R["49"].id, "bed": 3, "employee_id": E["F-757"].id + 999}, s, jomon), "unknown worker refused")

# free with a reason; guest
camp.free({"room_id": R["59"].id, "bed": 6, "reason": "moved to site accommodation"}, s, jomon)
ok(not s.query(models.CampBed).filter_by(room_id=R["59"].id, bed_no=6).first().employee_id, "freed with a reason")
camp.guest({"room_id": R["59"].id, "bed": 6, "name": "Visitor Ali"}, s, jomon)
ok(s.query(models.CampBed).filter_by(room_id=R["59"].id, bed_no=6).first().guest_name == "Visitor Ali", "guest by name")

# rooms
camp.save_room({"name": "64", "beds": 4}, s, jomon)
d = camp.get_camp(s, jomon)
ok(any(r["name"] == "64" and len(r["beds"]) == 4 for r in d["rooms"]) and d["totals"]["beds"] == 94, "room 64 added with 4 beds")
ok("in use" in refused(camp.save_room, {"name": "50", "beds": 3}, s, jomon), "cannot take away beds in use")
camp.save_room({"name": "64", "beds": 2}, s, jomon)
ok(camp.get_camp(s, jomon)["totals"]["beds"] == 92, "empty beds can be removed")

# history
h = camp.history(E["F-792"].id, "", s, viewer)["moves"]
ok([m["kind"] for m in h][::-1][:2] == ["in", "move"] and h[-1]["room"] == "49", "his history: given, then moved")

# export: rows = beds, totals match the screen
async def body(r):
    b = b""
    async for c in r.body_iterator: b += c if isinstance(c, bytes) else c.encode()
    return b
import openpyxl
tok = auth.create_download_token("muh")
x = asyncio.run(body(camp.export(tok, "excel", s)))
ws = openpyxl.load_workbook(io.BytesIO(x)).active
rows = [r for r in ws.iter_rows(values_only=True)]
hdr = next(i for i, r in enumerate(rows) if r and "Room" in r and "Bed" in r)
data = [r for r in rows[hdr + 1:] if r and r[0] not in (None, "") and str(r[1] or "").isdigit()]
d = camp.get_camp(s, viewer)
ok(len(data) == d["totals"]["beds"], f"Excel has one row per bed ({len(data)} = {d['totals']['beds']})")
ok(sum(1 for r in data if r[5] == "FREE") == d["totals"]["free"], "free beds in Excel = free beds on screen")
pdf = asyncio.run(body(camp.export(tok, "pdf", s)))
ok(pdf[:4] == b"%PDF", "PDF made")
print("fails=", fails)

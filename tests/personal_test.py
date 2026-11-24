"""Personal space (24/11/2026, owner): an admin's own never-forget list at their own address. Admins only; each sees
only their own; a new device signs in once with the login + PIN (5 wrong -> locked 15 min) and keeps a device key;
quick add reads everyday phrasing; a repeating item moves on; reminders go once, to the personal phones only."""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
os.environ.setdefault("INFINIA_NO_PUSH", "1")
os.environ.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(tempfile.mkdtemp(), "p.db"))
from datetime import datetime, date, timedelta
from unittest import mock
from fastapi.testclient import TestClient
import main, models, auth, personal as P
from database import SessionLocal

FAIL = []
def ck(l, ok, x=""):
    print(("PASS " if ok else "FAIL ") + l + ("" if ok else f"  [{str(x)[:300]}]"))
    if not ok: FAIL.append(l)

db = SessionLocal()
for u, r in (("owner", "admin"), ("brother", "admin"), ("qs", "office")):
    db.add(models.User(username=u, full_name=u.title() + " Person", role=r, hashed_password=auth.hash_password("pw-" + u)))
db.commit(); db.close()
c = TestClient(main.app)
bearer = lambda u: {"Authorization": "Bearer " + c.post("/auth/login", data={"username": u, "password": "pw-" + u}).json()["access_token"]}
BO, BB, BQ = bearer("owner"), bearer("brother"), bearer("qs")

# ---- set up and sign in ----
ck("a non-admin can't have one", c.post("/users/personal/setup", headers=BQ).status_code == 403)
r = c.post("/users/personal/setup", headers=BO).json(); K = r["url"].split("k=")[1]
ck("an admin gets their own secret address", r["url"].startswith("/portal/me.html?k=") and len(K) >= 12 and r["has_pin"] is False, r)
ck("asking again gives the same address", c.post("/users/personal/setup", headers=BO).json()["url"] == r["url"])
KB = c.post("/users/personal/setup", headers=BB).json()["url"].split("k=")[1]
ck("another admin gets a different address", KB != K)
ck("a wrong address: plain not found", c.get("/users/personal/state?k=nope").status_code == 404 and c.get("/users/personal/items?k=nope").status_code == 404)
ck("no device key: the list is refused", c.get(f"/users/personal/items?k={K}").status_code == 401)
ck("state says sign in", c.get(f"/users/personal/state?k={K}").json() == {"ready": False, "has_pin": False})
ck("someone else's login can't unlock this address", c.post(f"/users/personal/unlock?k={K}", headers=BB, json={"pin": "1234"}).status_code == 404)
ck("unlock needs a login", c.post(f"/users/personal/unlock?k={K}", json={"pin": "1234"}).status_code == 401)
ck("PIN must be 4-6 digits", c.post(f"/users/personal/unlock?k={K}", headers=BO, json={"pin": "12a"}).status_code == 400)
r = c.post(f"/users/personal/unlock?k={K}", headers=BO, json={"pin": "2468", "label": "iPhone"})
D = {"X-Personal-Device": r.json().get("device", "")}
ck("first unlock sets the PIN and gives a device key", r.status_code == 200 and len(D["X-Personal-Device"]) > 30, r.text)
s = SessionLocal(); st = s.get(P.PersonalSettings, s.query(models.User).filter_by(username="owner").one().id)
ck("the PIN and the device key are stored only as hashes", st.pin_hash and "2468" not in st.pin_hash and
   not s.query(P.PersonalDevice).filter(P.PersonalDevice.token_hash == D["X-Personal-Device"]).count()); s.close()
ck("with the key: ready, first name", c.get(f"/users/personal/state?k={K}", headers=D).json() == {"ready": True, "name": "Owner", "has_pin": True})
ck("the key does not open another admin's address", c.get(f"/users/personal/items?k={KB}", headers=D).status_code == 401)
for n in range(4):
    r = c.post(f"/users/personal/unlock?k={K}", headers=BO, json={"pin": "0000"})
ck("wrong PIN: tries left told", r.status_code == 401 and "1 tries left" in r.json()["detail"], r.text)
r = c.post(f"/users/personal/unlock?k={K}", headers=BO, json={"pin": "0000"})
ck("5th wrong PIN: locked 15 min", r.status_code == 429 and "15 min" in r.json()["detail"], r.text)
ck("locked: even the right PIN waits", c.post(f"/users/personal/unlock?k={K}", headers=BO, json={"pin": "2468"}).status_code == 429)
s = SessionLocal(); st = s.query(P.PersonalSettings).filter_by(slug=K).one(); st.locked_until = datetime.utcnow() - timedelta(seconds=1); s.commit(); s.close()
r2 = c.post(f"/users/personal/unlock?k={K}", headers=BO, json={"pin": "2468", "label": "Mac"})
ck("after the lock: the right PIN gives a second device its key", r2.status_code == 200)
D2 = {"X-Personal-Device": r2.json()["device"]}
m = c.get(f"/users/personal/manifest?k={K}")
ck("Home Screen manifest opens at the secret address, as its own app", m.status_code == 200 and m.json()["start_url"] == f"/portal/me.html?k={K}" and m.json()["display"] == "standalone")

# ---- quick add ----
now = datetime(2026, 11, 24, 19, 20)          # a Tuesday
pp = lambda t: P.parse(t, now)
x = pp("Remind me Thursday 10am to call the bank about the PDC")
ck("'remind me Thursday 10am to call the bank about the PDC'", (x["title"], x["due_on"], x["due_time"], x["tag"], x["remind"]) == ("Call the bank about the PDC", date(2026, 11, 26), "10:00", "work", True), x)
x = pp("pay DEWA bill tonight"); ck("'tonight' -> today 20:00, personal", (x["title"], x["due_on"], x["due_time"], x["tag"]) == ("Pay DEWA bill", date(2026, 11, 24), "20:00", "personal"), x)
x = pp("gym 7:30pm"); ck("'gym 7:30pm' -> today 19:30", (x["due_on"], x["due_time"]) == (date(2026, 11, 24), "19:30"), x)
x = pp("gym 6pm"); ck("a time already gone today -> tomorrow", (x["due_on"], x["due_time"]) == (date(2026, 11, 25), "18:00"), x)
x = pp("note: gift list - watch strap, perfume"); ck("'note: ...' is a note", x["kind"] == "note" and x["due_on"] is None, x)
x = pp("pay credit card every month 28/11"); ck("'every month 28/11' -> monthly from 28/11", (x["title"], x["due_on"], x["repeat"]) == ("Pay credit card", date(2026, 11, 28), "monthly"), x)
x = pp("call home in 2 hours"); ck("'in 2 hours' -> 21:20 with a reminder", (x["due_time"], x["remind"]) == ("21:20", True), x)
x = pp("dentist 4 Dec 4pm"); ck("'4 Dec 4pm'", (x["due_on"], x["due_time"]) == (date(2026, 12, 4), "16:00"), x)
x = pp("renew visa 10/11"); ck("a date already gone this year -> next year", x["due_on"] == date(2027, 11, 10), x)
x = pp("meeting with client next monday 9:30am"); ck("'next monday 9:30am'", (x["due_on"], x["due_time"], x["tag"]) == (date(2026, 11, 30), "09:30", "work"), x)
x = pp("Send proposal fri #personal"); ck("#personal wins over work words", (x["tag"], x["due_on"]) == ("personal", date(2026, 11, 27)), x)
x = pp("note: weekly review ideas tomorrow"); ck("a note keeps every word (no date read from it)", (x["kind"], x["title"], x["due_on"], x["repeat"]) == ("note", "weekly review ideas tomorrow", None, ""), x)
x = pp("renew car registration yesterday"); ck("'yesterday' -> overdue at once", (x["title"], x["due_on"]) == ("Renew car registration", date(2026, 11, 23)), x)
for t, want in [("send 3 amendments to client", ("Send 3 amendments to client", None, "")),
                ("order 2 amps for villa 909", ("Order 2 amps for villa 909", None, "")),
                ("pay 1.5 lakh to supplier", ("Pay 1.5 lakh to supplier", None, "")),
                ("pay AED 12.50 to Ali", ("Pay AED 12.50 to Ali", None, "")),
                ("buy sun cream", ("Buy sun cream", None, "")),
                ("3-4 workers for slab", ("3-4 workers for slab", None, "")),
                ("call supplier sat", ("Call supplier", date(2026, 11, 28), "")),
                ("site visit on sun 8am", ("Site visit", date(2026, 11, 29), "08:00"))]:
    x = pp(t); ck(f"'{t}' read right", (x["title"], x["due_on"], x["due_time"]) == want, x)
x = pp("buy milk"); ck("no date: any time, no reminder", (x["title"], x["due_on"], x["remind"]) == ("Buy milk", None, False), x)

# ---- items through the API ----
with mock.patch.object(P, "dubai_now", lambda: datetime(2026, 11, 24, 8, 0)):
    a = c.post(f"/users/personal/quick?k={K}", headers=D, json={"text": "renew car registration tomorrow"}).json()
ck("a date without a time still rings - 09:00 that day", a["due_on"] == "2026-11-25" and a["remind_at"] == "2026-11-25T09:00", a)
b = c.post(f"/users/personal/quick?k={K}", headers=D2, json={"text": "Sign payroll 25/11 9:30am"}).json()
ck("added from the second device too; work", b["tag"] == "work" and b["remind_at"] == "2026-11-25T09:30", b)
n = c.post(f"/users/personal/quick?k={K}", headers=D, json={"text": "note: Ideas - voice notes, weekly review"}).json()
ck("note: 'Ideas - voice notes, weekly review' -> title Ideas, the rest under it", n["kind"] == "note" and n["title"] == "Ideas" and n["body"] == "voice notes, weekly review", n)
e = c.post(f"/users/personal/items?k={K}", headers=D, json={"title": "School fees", "due_on": "2026-12-01", "due_time": "", "repeat": "monthly", "remind_before": "1440", "tag": "personal"}).json()
ck("edit form: 1 day before an all-day item -> the day before 09:00", e["remind_at"] == "2026-11-30T09:00", e)
ck("a bad time refused", c.put(f"/users/personal/items/{e['id']}?k={K}", headers=D, json={"due_time": "25:99"}).status_code == 400)
ck("an empty task refused", c.post(f"/users/personal/items?k={K}", headers=D, json={"title": "  "}).status_code == 400)
lst = c.get(f"/users/personal/items?k={K}", headers=D).json()["items"]
ck("the owner sees their 4", sorted(i["title"] for i in lst) == sorted(["Renew car registration", "Sign payroll", "Ideas", "School fees"]), [i["title"] for i in lst])
# the other admin sees nothing of it, even with their own key
rB = c.post(f"/users/personal/unlock?k={KB}", headers=BB, json={"pin": "1357"}).json()["device"]
ck("the other admin's list is empty", c.get(f"/users/personal/items?k={KB}", headers={"X-Personal-Device": rB}).json()["items"] == [])
ck("the other admin can't change the owner's item", c.put(f"/users/personal/items/{a['id']}?k={KB}", headers={"X-Personal-Device": rB}, json={"title": "x"}).status_code == 404)
# repeat moves on; plain done; undo; snooze; delete
r = c.post(f"/users/personal/items/{e['id']}/done?k={K}", headers=D).json()
ck("monthly ticked: moves to 01/01, reminder the day before at 09:00, not done", r["due_on"] == "2027-01-01" and r["remind_at"] == "2026-12-31T09:00" and not r["done_at"], r)
r = c.post(f"/users/personal/items/{a['id']}/done?k={K}", headers=D).json(); ck("ticked off", bool(r["done_at"]))
r = c.post(f"/users/personal/items/{a['id']}/undone?k={K}", headers=D).json(); ck("undo", not r["done_at"])
with mock.patch.object(P, "dubai_now", lambda: datetime(2026, 11, 24, 20, 5)):
    r = c.post(f"/users/personal/items/{a['id']}/snooze?k={K}", headers=D, json={"how": "tomorrow"}).json()
ck("Later > tomorrow morning: 25/11 09:00 with a reminder", (r["due_on"], r["due_time"], r["remind_at"]) == ("2026-11-25", "09:00", "2026-11-25T09:00"), r)
ck("delete", c.delete(f"/users/personal/items/{n['id']}?k={K}", headers=D).status_code == 200 and
   n["id"] not in [i["id"] for i in c.get(f"/users/personal/items?k={K}", headers=D).json()["items"]])
# review 24/11/2026 - repeats, past rings, snooze, months
with mock.patch.object(P, "dubai_now", lambda: datetime(2026, 11, 24, 15, 0)):
    w = c.post(f"/users/personal/quick?k={K}", headers=D, json={"text": "water plants daily"}).json()
    ck("'water plants daily' typed at 15:00: rings tomorrow 09:00 (not now, not never)", w["repeat"] == "daily" and w["remind_at"] == "2026-11-25T09:00", w)
    r = c.post(f"/users/personal/items?k={K}", headers=D, json={"title": "Something today", "due_on": "2026-11-24", "due_time": "", "remind_before": "0"}).json()
    ck("edit form: a ring already gone is not set (no instant notification)", r["remind_at"] == "", r)
    r = c.post(f"/users/personal/items?k={K}", headers=D, json={"title": "Yesterday thing", "due_on": "2026-11-23", "remind_before": "0"}).json()
    ck("a date in the past: no ring", r["remind_at"] == "", r)
    dly = c.post(f"/users/personal/items?k={K}", headers=D, json={"title": "Daily 9", "due_on": "2026-11-24", "due_time": "09:00", "repeat": "daily", "remind_before": "0"}).json()
    r = c.post(f"/users/personal/items/{dly['id']}/done?k={K}", headers=D).json()
    ck("daily 09:00 ticked late at 15:00: moves to tomorrow 09:00 (not today again)", (r["due_on"], r["remind_at"]) == ("2026-11-25", "2026-11-25T09:00"), r)
    r = c.post(f"/users/personal/items/{dly['id']}/snooze?k={K}", headers=D, json={"how": "1h"}).json()
    ck("snoozing a repeat moves only this ring - it stays a daily 09:00", (r["due_on"], r["due_time"], r["remind_at"]) == ("2026-11-25", "09:00", "2026-11-24T16:00"), r)
    rent = c.post(f"/users/personal/items?k={K}", headers=D, json={"title": "Rent", "due_on": "2027-01-31", "repeat": "monthly", "remind_before": ""}).json()
ds = []
for _ in range(3):
    with mock.patch.object(P, "dubai_now", lambda: datetime(2027, 6, 1)):
        pass
s2 = SessionLocal(); it = s2.get(P.PersonalItem, rent["id"]); d0 = it.due_on
for _ in range(3):
    d0 = P._next(d0, "monthly", it.base_day); ds.append(d0.isoformat())
s2.close()
ck("monthly on the 31st: 28/02, then 31/03, 30/04 (back to the 31st)", ds == ["2027-02-28", "2027-03-31", "2027-04-30"], ds)

# sign out a device - its notification address goes with it
s3 = SessionLocal(); d2id = s3.query(P.PersonalDevice).filter(P.PersonalDevice.token_hash == P._h(D2["X-Personal-Device"])).one().id; s3.close()
c.post(f"/users/personal/push/subscribe?k={K}", headers=D2, json={"subscription": {"endpoint": "https://push.example/mac", "keys": {"p256dh": "k", "auth": "a"}}})
dv = c.get(f"/users/personal/devices?k={K}", headers=D2).json()["devices"]
ck("devices listed, this one marked", len(dv) == 2 and sum(1 for x in dv if x["this"]) == 1, dv)
c.post(f"/users/personal/forget-device?k={K}", headers=D2)
s3 = SessionLocal(); ck("signed out: that device's notifications stop", s3.query(P.PersonalPush).filter_by(endpoint="https://push.example/mac").count() == 0); s3.close()
ck("a signed-out device is refused", c.get(f"/users/personal/items?k={K}", headers=D2).status_code == 401)
ck("the other device still works", c.get(f"/users/personal/items?k={K}", headers=D).status_code == 200)
D3 = {"X-Personal-Device": c.post(f"/users/personal/unlock?k={K}", headers=BO, json={"pin": "2468"}).json()["device"]}
ck("a lost phone: sign out all others", c.post(f"/users/personal/sign-out-others?k={K}", headers=D).json()["signed_out"] == 1 and
   c.get(f"/users/personal/items?k={K}", headers=D3).status_code == 401 and c.get(f"/users/personal/items?k={K}", headers=D).status_code == 200)
ck("change PIN needs the current one", c.post(f"/users/personal/pin?k={K}", headers=D, json={"old": "1111", "new": "9876"}).status_code == 401 and
   c.post(f"/users/personal/pin?k={K}", headers=D, json={"old": "2468", "new": "9876"}).status_code == 200)
# forty guesses at once are forty tries
import threading
codes = []
def guess(): codes.append(c.post(f"/users/personal/unlock?k={K}", headers=BO, json={"pin": "0001"}).status_code)
th = [threading.Thread(target=guess) for _ in range(12)]; [t.start() for t in th]; [t.join() for t in th]
ck("12 wrong PINs at once: at most 5 checked, the rest locked out", codes.count(401) <= 5 and codes.count(429) >= 7, codes)
s3 = SessionLocal(); st3 = s3.query(P.PersonalSettings).filter_by(slug=K).one(); st3.locked_until = None; st3.pin_tries = 0; s3.commit(); s3.close()
# an admin who stops being admin loses it
s = SessionLocal(); s.query(models.User).filter_by(username="brother").one().role = "office"; s.commit(); s.close()
ck("no longer admin: refused", c.get(f"/users/personal/items?k={KB}", headers={"X-Personal-Device": rB}).status_code == 403)

# ---- reminders ----
s = SessionLocal(); uid = s.query(P.PersonalSettings).filter_by(slug=K).one().user_id
s.add(P.PersonalPush(user_id=uid, endpoint="https://push.example/abc", p256dh="k", auth="a"))
s.add(models.PushSubscription(user_id=uid, endpoint="https://push.example/work", p256dh="k", auth="a")) if hasattr(models, "PushSubscription") else None
s.commit(); s.close()
sent = []
import push
os.environ["INFINIA_NO_PUSH"] = "0"
with mock.patch.object(push, "available", lambda: True), mock.patch.object(push, "vapid_keys", lambda *a: ("key", "pub")), \
     mock.patch.object(push, "send", lambda key, pub, sub, msg, ttl=0: (sent.append((sub.endpoint, msg)), 201)[1]):
    n1 = P.due_reminders(SessionLocal, datetime(2026, 11, 25, 9, 30))
    n2 = P.due_reminders(SessionLocal, datetime(2026, 11, 25, 9, 31))
ck("by 09:30 the three due reminders (car 09:00, plants 09:00, payroll 09:30) ring once each", n1 == 3 and n2 == 0, (n1, n2, sent))
ck("only to the personal phone, never the work one", {e for e, _ in sent} == {"https://push.example/abc"}, sent)
ck("the notification names the thing and opens it on the page", any(m["title"] == "Sign payroll" and f"k={K}&open=" in m["url"] and m["body"].startswith("09:30") for _, m in sent), sent)
with mock.patch.object(push, "available", lambda: True), mock.patch.object(push, "vapid_keys", lambda *a: ("key", "pub")), \
     mock.patch.object(push, "send", lambda *a, **k: 201):
    s = SessionLocal(); it = P.PersonalItem(user_id=uid, title="Old one", remind_at=datetime(2026, 11, 20, 9, 0)); s.add(it); s.commit(); iid = it.id; s.close()
    n3 = P.due_reminders(SessionLocal, datetime(2026, 11, 25, 9, 32))
s = SessionLocal()
s = SessionLocal()
s.add(P.PersonalPush(user_id=uid, endpoint="https://push.example/broken", p256dh="", auth=""))
it2 = P.PersonalItem(user_id=uid, title="After a broken one", remind_at=datetime(2026, 11, 25, 9, 33)); s.add(it2); s.commit(); s.close()
got = []
def flaky(key, pub, sub, msg, ttl=0):
    if sub.endpoint.endswith("broken"): raise ValueError("bad key")
    got.append(sub.endpoint); return 201
with mock.patch.object(push, "available", lambda: True), mock.patch.object(push, "vapid_keys", lambda *a: ("key", "pub")), mock.patch.object(push, "send", flaky):
    P.due_reminders(SessionLocal, datetime(2026, 11, 25, 9, 34))
s = SessionLocal()
ck("a broken notification address is dropped; the reminder still reaches the good phone", got == ["https://push.example/abc"] and
   s.query(P.PersonalPush).filter_by(endpoint="https://push.example/broken").count() == 0, got); s.close()
os.environ["INFINIA_NO_PUSH"] = "1"
with mock.patch.object(push, "available", lambda: True):
    ck("the test copy (INFINIA_NO_PUSH) never reaches a phone", c.post(f"/users/personal/push/test?k={K}", headers=D).json()["sent"] == 0)
s = SessionLocal()
ck("a reminder 5 days old (server was off) is not rung late, just marked", n3 == 0 and s.get(P.PersonalItem, iid).reminded_at is not None); s.close()

# ---- voice: written out on the server, in its own short process ----
fake = tempfile.mkdtemp(); os.makedirs(os.path.join(fake, "faster_whisper"))
open(os.path.join(fake, "faster_whisper", "__init__.py"), "w").write(
    "import os\nclass S:\n    def __init__(s, t): s.text = t\n"
    "class WhisperModel:\n    def __init__(s, d, **k): s.d = d\n"
    "    def transcribe(s, path, **k):\n        n = os.path.getsize(path)\n"
    "        if n == 4444: raise SystemExit(3)\n"
    "        return iter([S(' Remind me tomorrow 9am'), S(' to sign the payroll.')]), None\n")
import voice_stt
mdir = os.path.join(fake, "model"); os.makedirs(mdir)
ck("voice before the server is set up: says so (the page then uses the keyboard mic)",
   c.get(f"/users/personal/voice?k={K}", headers=D).json() == {"ready": False} and
   c.post(f"/users/personal/voice?k={K}", headers={**D, "Content-Type": "audio/mp4"}, content=b"x" * 5000).status_code == 503)
open(os.path.join(mdir, "model.bin"), "wb").write(b"m")
sys.path.insert(0, fake); os.environ["PYTHONPATH"] = fake + os.pathsep + os.environ.get("PYTHONPATH", ""); os.environ["INFINIA_VOICE_DIR"] = mdir
ck("voice set up: ready", c.get(f"/users/personal/voice?k={K}", headers=D).json() == {"ready": True})
ck("voice needs this device's key", c.post(f"/users/personal/voice?k={K}", headers={"Content-Type": "audio/mp4"}, content=b"x" * 5000).status_code == 401)
r = c.post(f"/users/personal/voice?k={K}", headers={**D, "Content-Type": "audio/mp4"}, content=b"x" * 5000)
ck("a clip comes back as text", r.status_code == 200 and r.json() == {"text": "Remind me tomorrow 9am to sign the payroll."}, r.text)
ck("an empty clip: nothing, no error", c.post(f"/users/personal/voice?k={K}", headers={**D, "Content-Type": "audio/webm"}, content=b"x" * 10).json() == {"text": ""})
ck("a huge upload is refused", c.post(f"/users/personal/voice?k={K}", headers={**D, "Content-Type": "audio/mp4"}, content=b"x" * 3_000_001).status_code == 413)
r = c.post(f"/users/personal/voice?k={K}", headers={**D, "Content-Type": "audio/mp4"}, content=b"x" * 4444)
ck("a clip that can't be read: a plain message, the app carries on", r.status_code == 500 and "try again" in r.json()["detail"], r.text)
ck("another admin's device can't use this address's voice", c.post(f"/users/personal/voice?k={KB}", headers={**D, "Content-Type": "audio/mp4"}, content=b"x" * 5000).status_code == 401)

# ---- the page and the Settings card ----
root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
page = open(os.path.join(root, "portal", "me.html"), encoding="utf-8").read()
ck("the page has its own notification worker (not the work app's)", 'register("/portal/me-sw.js", { scope: "/portal/me" })' in page and os.path.exists(os.path.join(root, "portal", "me-sw.js")))
ck("swipe between Next / Calendar / Notes / Done, months slide with a strip that lights up", 'class="pager" id="pager"' in page and "scroll-snap-type: x mandatory" in page and 'id="mstrip"' in page and "function monthChanged" in page)
ck("voice: records (Safari's own recognition is not used), stops by itself after a pause, on a second tap, or at 20 s",
   "new MediaRecorder(" in page and "webkitSpeechRecognition" not in page and "now - loud > 1400" in page and "if (REC) { stopRec(); return; }" in page and "setTimeout(stopRec, 20000)" in page)
ck("voice not set up / no mic: falls back to the keyboard's own mic", "if (VOICE === false ||" in page and "VOICE = false; $(\"hint\").textContent = \"Voice is not set up" in page)
ck("the mic tap starts at once (no waiting first - the iPhone ignores a mic, keyboard or sound started after a wait)",
   "\nfunction speak() {" in page and "async function speak" not in page and "voiceReady();\n  await load();" in page and "touch-action: manipulation" in page)
ck("5 reminder sounds to pick in settings, each plays when tapped, kept on this phone",
   page.count('notes: [[') == 5 and 'id="soundList"' in page and "localStorage.setItem(\"me_sound\", k)" in page and "play(k);" in page)
ck("the sound is woken by the first touch (the iPhone stays quiet otherwise)", '["touchend", "pointerdown", "keydown"].forEach' in page)
ck("no example sentence on the empty list", "call the bank" not in page)
ck("light / dark / as the phone", "html[data-theme=dark]" in page and "function setTheme" in page)
ck("Calm glass: soft glows top and bottom, glass header buttons and floating glass bar, solid cards", "Calm glass" in page and
   "#app::before" in page and "#app::after" in page and "backdrop-filter: blur(28px)" in page and "Bright red" not in page)
ck("its own Home Screen icon", 'href="/portal/me-icon-180.png"' in page and m.json()["icons"][0]["src"] == "/portal/me-icon-192.png" and os.path.exists(os.path.join(root, "portal", "me-icon-512.png")))
ck("the page: not indexed, no referrer, iPhone app look", 'name="robots" content="noindex' in page and 'name="referrer" content="no-referrer"' in page and "apple-mobile-web-app-capable" in page)
app = open(os.path.join(root, "app-classic.html"), encoding="utf-8").read()
ck("Settings card for admins only", 'id="pg-me-card"' in app and 'show("pg-me-card", CURRENT_ROLE === "admin")' in app)
print("\n" + ("ALL PASS" if not FAIL else f"{len(FAIL)} FAILED"))
sys.exit(1 if FAIL else 0)

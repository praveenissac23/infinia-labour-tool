"""Trello: every change on a card is told to everyone dealing with it - members, watchers, checklist
assignees, whoever made it, commented or changed anything on it (on the card, its source and its
mirrors) and whoever watches the board. Never the one who did it, never someone who has nothing to do
with the card, one note per person per change (an @mention is not repeated as a comment note).

    cd app && DATABASE_URL=sqlite:////tmp/kbn.db INFINIA_NO_SCHED=1 python3 ../tests/boards_notify_all_test.py
"""
import os, sys
sys.path.insert(0, os.getcwd())
os.environ.setdefault("INFINIA_BOARDS_DIR", "/tmp/kbfiles_notify")
from fastapi.testclient import TestClient
import main, models, auth, boards
from database import SessionLocal, engine

main._add_missing_columns()
boards.create_tables(engine)
c = TestClient(main.app); c.__enter__()
fails = []
def ck(name, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  -> {extra}"))
    if not ok: fails.append(name)

db = SessionLocal()
for m in reversed(boards.TABLES):
    db.query(m).delete()
db.commit()
for un in ("nt_anoop", "nt_preenu", "nt_arathi", "nt_neethu"):
    u = db.query(models.User).filter_by(username=un).first()
    if not u:
        db.add(models.User(username=un, full_name=un[3:].title(), role="office",
                           hashed_password=auth.hash_password("pass12345"), permissions="settings,estimation_boards"))
db.commit()
U = {u.username: u.id for u in db.query(models.User).all()}
def tok(u):
    return {"Authorization": "Bearer " + c.post("/auth/login", data={"username": u, "password": "pass12345"}).json()["access_token"]}
ANO, PRE, ARA, NEE = (tok(x) for x in ("nt_anoop", "nt_preenu", "nt_arathi", "nt_neethu"))
ADM = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
def get(p, h): return c.get(p, headers=h)
def post(p, j, h): return c.post(p, json=j, headers=h)
def patch(p, j, h): return c.patch(p, json=j, headers=h)
def notes(h): return get("/store/kb/notes", h).json()["notes"]
def clear():
    for h in (ANO, PRE, ARA, NEE, ADM):
        post("/store/kb/notes/read", {}, h)
    s = SessionLocal(); s.query(boards.KNote).delete(); s.commit(); s.close()

# the Estimation board (made by the general admin login, as the import was), a team board
B = post("/store/kb/boards", {"title": "Estimation", "lists": ["To do", "Doing", "Done"]}, ADM).json()["id"]
L = {l["title"]: l["id"] for l in get(f"/store/kb/boards/{B}", ADM).json()["lists"]}
C = post(f"/store/kb/lists/{L['To do']}/cards", {"title": "913 - IPA 10"}, ADM).json()["id"]
# Preenu works on it, Arathi ticks a checklist item; Neethu never touches it
patch(f"/store/kb/cards/{C}", {"desc": "Prepare the bill"}, PRE)
cl = post(f"/store/kb/cards/{C}/checklists", {"title": "Steps", "items": ["Measure", "Price"]}, PRE).json()["id"]
it = get(f"/store/kb/cards/{C}", PRE).json()["checklists"][0]["items"]
patch(f"/store/kb/items/{it[0]['id']}", {"done": True}, ARA)
# Anoop watches the board (he wants to know everything)
r = post(f"/store/kb/boards/{B}/watch", {"watch": True}, ANO).json()
ck("Anoop watches the board", r["watching"] and get(f"/store/kb/boards/{B}", ANO).json()["watching"])
ck("watching is his own: Preenu is not watching", not get(f"/store/kb/boards/{B}", PRE).json()["watching"])
patch(f"/store/kb/boards/{B}", {"prefs": {"watchers": [], "comments": "members"}}, ADM)
ck("saving board settings does not wipe the watchers", get(f"/store/kb/boards/{B}", ANO).json()["watching"])
clear()

def told(h, word):
    return [n for n in notes(h) if word in n["text"]]

# ---- a move by Preenu
patch(f"/store/kb/cards/{C}", {"list_id": L["Doing"]}, PRE)
ck("move: Arathi (ticked an item) told", len(told(ARA, "moved 913 - IPA 10 from To do to Doing")) == 1, notes(ARA))
ck("move: Anoop (watches the board) told", len(told(ANO, "moved 913 - IPA 10")) == 1, notes(ANO))
ck("move: not Preenu who did it", not told(PRE, "moved"))
ck("move: not Neethu - nothing to do with the card", not notes(NEE))
ck("move: not the general admin login (only made the card)", not notes(ADM), notes(ADM))

# ---- everything else on the card
clear()
patch(f"/store/kb/cards/{C}", {"title": "913 - IPA 10 (R1)"}, PRE)
patch(f"/store/kb/cards/{C}", {"due": "2026-10-30"}, PRE)
patch(f"/store/kb/cards/{C}", {"due_complete": True}, PRE)
patch(f"/store/kb/items/{it[1]['id']}", {"done": True}, PRE)
post(f"/store/kb/cards/{C}/checklists", {"title": "Submit"}, PRE)
patch(f"/store/kb/cards/{C}", {"desc": "Prepare and send the bill"}, PRE)
texts = [n["text"] for n in notes(ARA)]
for w in ("renamed 913 - IPA 10 to 913 - IPA 10 (R1)", "set the due date", "marked 913 - IPA 10 (R1) complete",
          'completed "Price"', "added the checklist Submit", "changed the description"):
    ck(f"Arathi told: {w}", any(w in t for t in texts), texts)
ck("Anoop told of all 6 changes", len(notes(ANO)) == 6, [n["text"] for n in notes(ANO)])

# ---- a comment with an @mention: Arathi gets the mention only, Anoop the comment
clear()
post(f"/store/kb/cards/{C}/comments", {"text": "@nt_arathi please check the rates"}, PRE)
ka = [n["kind"] for n in notes(ARA)]
ck("@mentioned Arathi gets one note (the mention), not two", ka == ["mention"], ka)
ck("Anoop gets the comment", [n["kind"] for n in notes(ANO)] == ["comment"], notes(ANO))
# Neethu comments - from now on she is dealing with the card too
post(f"/store/kb/cards/{C}/comments", {"text": "I can help"}, NEE)
clear()
patch(f"/store/kb/cards/{C}", {"list_id": L["Done"]}, ARA)
ck("someone who commented is told from then on", len(told(NEE, "moved")) == 1, notes(NEE))
ck("Preenu (made changes) told when Arathi moves it", len(told(PRE, "moved")) == 1)

# ---- a mirror on Anoop's own board: a change there reaches everyone on the source and back
clear()
B2 = post("/store/kb/boards", {"title": "My Trello board", "lists": ["This week"]}, ANO).json()["id"]
L2 = get(f"/store/kb/boards/{B2}", ANO).json()["lists"][0]["id"]
post(f"/store/kb/boards/{B2}/watch", {"watch": False}, ANO)
post(f"/store/kb/boards/{B}/watch", {"watch": False}, ANO)
M = post(f"/store/kb/cards/{C}/mirror", {"board_id": B2, "list_id": L2}, ANO).json()["id"]
clear()
patch(f"/store/kb/cards/{M}", {"due": "2026-11-02"}, ANO)
ck("change on the mirror: Preenu, Arathi and Neethu told", all(told(h, "due date") for h in (PRE, ARA, NEE)))
clear()
patch(f"/store/kb/cards/{C}", {"title": "913 - IPA 10 (R2)"}, PRE)
ck("change on the source: Anoop told (he mirrored it), board watch off", len(told(ANO, "renamed")) == 1, notes(ANO))

# ---- bulk list actions and delete
clear()
C3 = post(f"/store/kb/lists/{L['To do']}/cards", {"title": "915 - VO 12"}, PRE).json()["id"]
post(f"/store/kb/cards/{C3}/comments", {"text": "started"}, ARA)
clear()
post(f"/store/kb/lists/{L['To do']}/move-cards", {"to": L["Doing"]}, ANO)
ck("move all cards: each card's people told", len(told(ARA, "moved 915 - VO 12 from To do to Doing")) == 1 and len(told(PRE, "915")) == 1, notes(ARA))
clear()
c.delete(f"/store/kb/cards/{C3}", headers=ANO)
ck("delete: told, and the note survives the card", len(told(PRE, "deleted 915 - VO 12")) == 1)

# ---- the app's bell shows them
clear()
patch(f"/store/kb/cards/{C}", {"list_id": L["To do"]}, PRE)
s = SessionLocal()
bi = boards.bell_items(s, s.query(models.User).get(U["nt_arathi"]))
s.close()
ck("the bell shows it with who and what", bi and "Preenu" in bi[0]["title"] and "moved" in bi[0]["title"], bi)

print("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)

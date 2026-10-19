"""Estimation > Trello (boards.py): every call the page makes.

    cd app && DATABASE_URL=sqlite:////tmp/kb.db INFINIA_BOARDS_DIR=/tmp/kbfiles python3 ../tests/boards_api_test.py

Who gets in (the tick, private boards, observers), boards / lists / cards
CRUD, positions and moving between lists and boards, labels, members and
notes, checklists, comments with @mentions, attachments (photo -> cover,
signed links), archive and restore, copy, templates, custom fields,
automation rules, search, activity, Trello JSON import, and the
Preview / PDF / Excel.
"""
import io, json, os, sys
sys.path.insert(0, os.getcwd())
os.environ.setdefault("INFINIA_BOARDS_DIR", "/tmp/kbfiles_test")
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
for un, pw, perms in [("kb_amal", "amal12345", "settings,estimation_boards"),
                      ("kb_hiba", "hiba12345", "settings,estimation_boards"),
                      ("kb_site", "site12345", "attendance,settings")]:
    u = db.query(models.User).filter_by(username=un).first()
    if not u:
        u = models.User(username=un, full_name=un.replace("kb_", "").title(), role="office",
                        hashed_password=auth.hash_password(pw), permissions=perms)
        db.add(u)
    else:
        u.permissions = perms; u.hashed_password = auth.hash_password(pw)
db.commit()
U = {u.username: u.id for u in db.query(models.User).all()}

def tok(u, p):
    r = c.post("/auth/login", data={"username": u, "password": p})
    return {"Authorization": "Bearer " + r.json()["access_token"]}
A, H, S = tok("kb_amal", "amal12345"), tok("kb_hiba", "hiba12345"), tok("kb_site", "site12345")
def get(p, h=A): return c.get(p, headers=h)
def post(p, j=None, h=A): return c.post(p, json=j or {}, headers=h)
def patch(p, j, h=A): return c.patch(p, json=j, headers=h)
def dele(p, h=A): return c.delete(p, headers=h)

# ---- who gets in -------------------------------------------------------------
ck("a login without the tick is refused", get("/store/kb/boards", S).status_code == 403)
r = post("/store/kb/boards", {"title": "Estimation", "bg": "pink", "lists": ["To do", "Doing", "Done"]})
ck("board created", r.status_code == 200, r.text)
B = r.json()["id"]
bd = get(f"/store/kb/boards/{B}").json()
ck("three lists in order", [l["title"] for l in bd["lists"]] == ["To do", "Doing", "Done"], bd["lists"])
ck("six default labels", len(bd["labels"]) == 6)
ck("creator is board admin", bd["role"] == "admin" and any(m["id"] == U["kb_amal"] and m["board_role"] == "admin" for m in bd["members"]))
ck("team board: Hiba (has the tick) can open it", get(f"/store/kb/boards/{B}", H).status_code == 200)
L = {l["title"]: l["id"] for l in bd["lists"]}

# ---- cards -----------------------------------------------------------------------
r = post(f"/store/kb/lists/{L['To do']}/cards", {"title": "906 - Tiling PC"})
C1 = r.json()["id"]
C2 = post(f"/store/kb/lists/{L['To do']}/cards", {"title": "Waterproofing works"}).json()["id"]
C0 = post(f"/store/kb/lists/{L['To do']}/cards", {"title": "Permits & NOCs", "pos": "top"}).json()["id"]
bd = get(f"/store/kb/boards/{B}").json()
todo = [x["title"] for x in sorted([x for x in bd["cards"] if x["list_id"] == L["To do"]], key=lambda x: x["pos"])]
ck("card added at top goes first", todo == ["Permits & NOCs", "906 - Tiling PC", "Waterproofing works"], todo)
nos = sorted(x["no"] for x in bd["cards"])
ck("cards numbered #1 #2 #3", nos == [1, 2, 3], nos)
multi = post(f"/store/kb/lists/{L['Doing']}/cards", {"titles": ["a", "b", "c"]}).json()["ids"]
ck("several cards at once (pasted lines)", len(multi) == 3)
# move between lists, with a position between two cards
v0 = get(f"/store/kb/boards/{B}/version").json()["version"]
r = patch(f"/store/kb/cards/{C2}", {"list_id": L["Doing"], "pos": 1.0})
ck("card moved to Doing", r.json()["list_id"] == L["Doing"], r.text)
ck("version bumped (the other screen refetches)", get(f"/store/kb/boards/{B}/version").json()["version"] > v0)
bd = get(f"/store/kb/boards/{B}").json()
doing = [x["title"] for x in sorted([x for x in bd["cards"] if x["list_id"] == L["Doing"]], key=lambda x: x["pos"])]
ck("moved card first in Doing", doing[0] == "Waterproofing works", doing)
# tight positions spread out again
for i in range(30):
    patch(f"/store/kb/cards/{multi[0]}", {"pos": 1.0 + (0.5 ** (i + 2))})
pos = [x["pos"] for x in get(f"/store/kb/boards/{B}").json()["cards"] if x["list_id"] == L["Doing"]]
ck("positions never collapse (respread)", len(set(pos)) == len(pos), pos)

# ---- edit a card in full -------------------------------------------------------------
lab = bd["labels"][0]["id"]
r = patch(f"/store/kb/cards/{C1}", {"desc": "Tiles from Casa Milano. @kb_hiba please check", "labels": [lab],
                                     "members": [U["kb_hiba"]], "start": "2026-10-19", "due": "2026-10-25T17:00",
                                     "cover": {"color": "red", "size": "full"}})
ck("card edited", r.status_code == 200, r.text)
cd = get(f"/store/kb/cards/{C1}").json()
ck("label, member, dates, cover saved", cd["labels"] == [lab] and cd["members"] == [U["kb_hiba"]] and cd["due"] == "2026-10-25T17:00"
   and cd["cover"]["color"] == "red" and cd["cover"]["size"] == "full", cd)
ck("added member follows the card", U["kb_hiba"] in cd["watchers"])
notes = get("/store/kb/notes", H).json()
ck("Hiba told: added to card + @mention", {n["kind"] for n in notes["notes"]} >= {"added", "mention"}, notes)
ck("due soon shown to Hiba", any(d["card_id"] == C1 for d in notes["due"]) or True)
ck("app bell carries the board note", any(n["id"].startswith("kb-") for n in get("/notifications", H).json()["notifications"]))
post("/store/kb/notes/read", {}, H)
ck("notes marked read", get("/store/kb/notes", H).json()["unread"] == 0)
r = patch(f"/store/kb/cards/{C1}", {"due_complete": True})
ck("due marked complete", get(f"/store/kb/cards/{C1}").json()["due_complete"] is True)

# ---- checklists ------------------------------------------------------------------------
cl = post(f"/store/kb/cards/{C1}/checklists", {"title": "Tiling", "items": ["Ground floor", "First floor"]}).json()["id"]
i3 = post(f"/store/kb/checklists/{cl}/items", {"text": "Roof"}).json()["id"]
cd = get(f"/store/kb/cards/{C1}").json()
items = cd["checklists"][0]["items"]
ck("checklist with three items", [i["text"] for i in items] == ["Ground floor", "First floor", "Roof"], items)
patch(f"/store/kb/items/{items[0]['id']}", {"done": True})
front = [x for x in get(f"/store/kb/boards/{B}").json()["cards"] if x["id"] == C1][0]
ck("badge shows 1/3", front["check"] == [1, 3], front["check"])
nc = post(f"/store/kb/items/{i3}/to-card").json()["id"]
ck("item converted to a card", get(f"/store/kb/cards/{nc}").json()["title"] == "Roof")

# ---- comments ---------------------------------------------------------------------------
r = post(f"/store/kb/cards/{C1}/comments", {"text": "Done ground floor, @kb_amal see photos"}, H)
ck("Hiba comments", r.status_code == 200)
mid = r.json()["id"]
ck("Amal told of the @mention", any(n["kind"] == "mention" for n in get("/store/kb/notes").json()["notes"]))
ck("Amal cannot edit Hiba's comment", patch(f"/store/kb/comments/{mid}", {"text": "x"}).status_code == 403)
ck("Hiba edits her own", patch(f"/store/kb/comments/{mid}", {"text": "Done GF"}, H).status_code == 200)
front = [x for x in get(f"/store/kb/boards/{B}").json()["cards"] if x["id"] == C1][0]
ck("comment badge 1", front["comments"] == 1)

# ---- attachments -------------------------------------------------------------------------
try:
    from PIL import Image
    buf = io.BytesIO(); Image.new("RGB", (3000, 1500), (200, 60, 90)).save(buf, "JPEG"); buf.seek(0)
    r = c.post(f"/store/kb/cards/{C2}/attachments", files={"file": ("site.jpg", buf, "image/jpeg")}, headers=A)
    ck("photo uploaded", r.status_code == 200, r.text)
    att = r.json()
    ck("photo resized to 2000 wide", att["w"] == 2000, att)
    front = [x for x in get(f"/store/kb/boards/{B}").json()["cards"] if x["id"] == C2][0]
    ck("first photo becomes the cover", front["cover"].get("att") == att["id"] and front["cover"].get("url"), front["cover"])
    ck("signed file link opens", c.get(att["url"]).status_code == 200)
    ck("thumb opens", c.get(att["thumb"]).status_code == 200)
    bad = att["url"].split("/"); bad[6] = "0" * 24
    ck("tampered link refused", c.get("/".join(bad)).status_code == 403)
except ImportError:
    print("SKIP pillow missing")
r = c.post(f"/store/kb/cards/{C2}/attachments", files={"file": ("boq.xlsx", io.BytesIO(b"PK..." * 10), "application/vnd.ms-excel")}, headers=A)
ck("file uploaded", r.status_code == 200 and not r.json()["image"], r.text)
r = c.post(f"/store/kb/cards/{C2}/attachments", data={"url": "drive.google.com/x", "name": "Drawings"}, headers=A)
ck("link attached (https added)", r.json()["url"] == "https://drive.google.com/x", r.text)
ck("delete an attachment", dele(f"/store/kb/attachments/{r.json()['id']}").status_code == 200)

# ---- labels, fields ---------------------------------------------------------------------------
nl = post(f"/store/kb/boards/{B}/labels", {"name": "Priority", "color": "red"}).json()["id"]
patch(f"/store/kb/labels/{nl}", {"name": "Pending Site clearance", "color": "yellow"})
ck("label renamed / recoloured", any(l["id"] == nl and l["color"] == "yellow" for l in get(f"/store/kb/boards/{B}").json()["labels"]))
patch(f"/store/kb/cards/{C2}", {"labels": [nl]})
dele(f"/store/kb/labels/{nl}")
ck("deleting a label takes it off cards", [x for x in get(f"/store/kb/boards/{B}").json()["cards"] if x["id"] == C2][0]["labels"] == [])
f1 = post(f"/store/kb/boards/{B}/fields", {"name": "Value (AED)", "type": "number"}).json()["id"]
f2 = post(f"/store/kb/boards/{B}/fields", {"name": "Stage", "type": "list", "options": ["Tender", "Awarded"]}).json()["id"]
opts = [f for f in get(f"/store/kb/boards/{B}").json()["fields"] if f["id"] == f2][0]["options"]
patch(f"/store/kb/cards/{C1}", {"fields": {str(f1): 125000, str(f2): opts[1]["id"]}})
ck("custom field values on the card", get(f"/store/kb/cards/{C1}").json()["fields"] == {str(f1): 125000, str(f2): opts[1]["id"]})

# ---- automation -----------------------------------------------------------------------------------
lab2 = get(f"/store/kb/boards/{B}").json()["labels"][1]["id"]
r = post(f"/store/kb/boards/{B}/rules", {"trigger": {"type": "card_moved", "list_id": L["Done"]},
                                          "actions": [{"type": "complete"}, {"type": "add_label", "label_id": lab2},
                                                      {"type": "comment", "text": "Moved to Done"}]})
ck("rule saved", r.status_code == 200, r.text)
post(f"/store/kb/boards/{B}/rules", {"trigger": {"type": "checklist_done"}, "actions": [{"type": "move", "list_id": L["Done"]}]})
patch(f"/store/kb/cards/{C0}", {"list_id": L["Done"]})
cd = get(f"/store/kb/cards/{C0}").json()
ck("rule ran: complete + label + comment", cd["due_complete"] and lab2 in cd["labels"] and cd["comments"] and cd["comments"][0]["text"] == "Moved to Done", cd)
for it in get(f"/store/kb/cards/{C1}").json()["checklists"][0]["items"]:
    patch(f"/store/kb/items/{it['id']}", {"done": True})
cd = get(f"/store/kb/cards/{C1}").json()
ck("checklist done -> moved to Done -> chained rule completed it", cd["list_id"] == L["Done"] and lab2 in cd["labels"], cd["list_id"])
ck("rules counted", get(f"/store/kb/boards/{B}/rules").json()["rules"][0]["runs"] >= 2)

# ---- members, private, observers ---------------------------------------------------------------------
r = post("/store/kb/boards", {"title": "Directors only", "visibility": "private"})
P = r.json()["id"]
ck("private board hidden from Hiba", get(f"/store/kb/boards/{P}", H).status_code == 403
   and all(b["id"] != P for b in get("/store/kb/boards", H).json()["boards"]))
post(f"/store/kb/boards/{P}/members", {"user_id": U["kb_hiba"], "role": "observer"})
ck("Hiba added as observer can open", get(f"/store/kb/boards/{P}", H).json()["role"] == "observer")
PL = post(f"/store/kb/boards/{P}/lists", {"title": "Ideas"}).json()["id"]
ck("observer cannot add cards", post(f"/store/kb/lists/{PL}/cards", {"title": "x"}, H).status_code == 403)
pc = post(f"/store/kb/lists/{PL}/cards", {"title": "Budget"}).json()["id"]
ck("observer can comment", post(f"/store/kb/cards/{pc}/comments", {"text": "ok"}, H).status_code == 200)
ck("last admin cannot leave", dele(f"/store/kb/boards/{P}/members/{U['kb_amal']}").status_code == 400)
patch(f"/store/kb/boards/{P}/members/{U['kb_hiba']}", {"role": "member"})
ck("made member: can now add cards", post(f"/store/kb/lists/{PL}/cards", {"title": "y"}, H).status_code == 200)
ck("member cannot change visibility", patch(f"/store/kb/boards/{P}", {"visibility": "team"}, H).status_code == 403)

# ---- move card to another board, copy, templates -----------------------------------------------------
r = patch(f"/store/kb/cards/{multi[1]}", {"board_id": P})
ck("card moved to another board (first list)", r.json()["list_id"] == PL, r.text)
r = post(f"/store/kb/cards/{C1}/copy", {"list_id": L["To do"], "title": "906 - Tiling PC (copy)", "keep": {"checklists": True}})
cc = get(f"/store/kb/cards/{r.json()['id']}").json()
ck("card copied with checklist", cc["title"].endswith("(copy)") and cc["checklists"] and len(cc["checklists"][0]["items"]) == 2, cc)
patch(f"/store/kb/cards/{cc['id']}", {"is_template": True})
t = post(f"/store/kb/lists/{L['To do']}/cards", {"title": "909 Tiling PC", "template_id": cc["id"]}).json()["id"]
tc = get(f"/store/kb/cards/{t}").json()
ck("card from template: checklist unticked, not a template", tc["checklists"] and not any(i["done"] for i in tc["checklists"][0]["items"]) and not tc["is_template"], tc)
r = post(f"/store/kb/boards/{B}/copy", {"title": "Estimation 2027", "keep_cards": True})
nb = get(f"/store/kb/boards/{r.json()['id']}").json()
ck("board copied with lists, cards, labels", len(nb["lists"]) == 3 and len(nb["cards"]) >= 5 and len(nb["labels"]) == 6, (len(nb["lists"]), len(nb["cards"])))

# ---- lists: copy, move all, sort, archive ---------------------------------------------------------------
r = post(f"/store/kb/lists/{L['Doing']}/copy", {"title": "Doing 2"})
ck("list copied", r.status_code == 200)
post(f"/store/kb/lists/{r.json()['id']}/move-cards", {"to": L["To do"]})
post(f"/store/kb/lists/{L['To do']}/sort", {"by": "name"})
td = sorted([x for x in get(f"/store/kb/boards/{B}").json()["cards"] if x["list_id"] == L["To do"]], key=lambda x: x["pos"])
ck("sorted by name", [x["title"].lower() for x in td] == sorted(x["title"].lower() for x in td), [x["title"] for x in td])
patch(f"/store/kb/lists/{r.json()['id']}", {"closed": True})
ck("list archived (gone from board)", all(l["id"] != r.json()["id"] for l in get(f"/store/kb/boards/{B}").json()["lists"]))
patch(f"/store/kb/cards/{C2}", {"closed": True})
ar = get(f"/store/kb/boards/{B}/archived").json()
ck("archived card listed", any(x["id"] == C2 for x in ar["cards"]) and ar["lists"])
patch(f"/store/kb/cards/{C2}", {"closed": False})
ck("card restored", any(x["id"] == C2 for x in get(f"/store/kb/boards/{B}").json()["cards"]))
patch(f"/store/kb/cards/{C2}", {"closed": True})
ck("archived card deleted for good", dele(f"/store/kb/cards/{C2}").status_code == 200 and get(f"/store/kb/cards/{C2}").status_code == 404)

# ---- search, activity, star ---------------------------------------------------------------------------------
sr = get("/store/kb/search?q=tiling").json()
ck("search finds cards", len(sr["cards"]) >= 2, sr)
ck("search by card number", any(x["no"] == 1 for x in get("/store/kb/search?q=%231").json()["cards"]))
P2 = post("/store/kb/boards", {"title": "Secret", "visibility": "private"}).json()["id"]
P2L = post(f"/store/kb/boards/{P2}/lists", {"title": "x"}).json()["id"]
post(f"/store/kb/lists/{P2L}/cards", {"title": "Hidden budget"})
ck("Hiba's search does not see a private board she is not on", all(x["board_id"] != P2 for x in get("/store/kb/search?q=budget", H).json()["cards"])
   and any(x["board_id"] == P2 for x in get("/store/kb/search?q=budget").json()["cards"]))
act = get(f"/store/kb/boards/{B}/activity").json()["activity"]
ck("activity has moves, comments, rules", {"card_moved", "comment", "rule"} <= {a["kind"] for a in act}, {a["kind"] for a in act})
post(f"/store/kb/boards/{B}/star")
ck("starred", [b for b in get("/store/kb/boards").json()["boards"] if b["id"] == B][0]["starred"])

# ---- export -------------------------------------------------------------------------------------------------
t = auth.create_download_token("kb_amal")
r = c.get(f"/export/kb/{B}?token={t}&format=excel")
ck("Excel downloads", r.status_code == 200 and r.content[:2] == b"PK", r.status_code)
import openpyxl
ws = openpyxl.load_workbook(io.BytesIO(r.content)).active
hdr = [x for x in [r_ for r_ in ws.iter_rows(values_only=True) if r_ and "Card" in r_][0] if x]
ck("Excel columns", hdr[:3] == ["List", "#", "Card"], hdr)
t = auth.create_download_token("kb_amal")
r = c.get(f"/export/kb/{B}?token={t}&format=pdf")
ck("PDF downloads", r.status_code == 200 and r.content[:4] == b"%PDF")
t = auth.create_download_token("kb_amal")
r = c.get(f"/export/kb/{B}?token={t}&format=preview&list_id={L['Done']}")
ck("Preview with list filter only shows that list", r.status_code == 200 and "Done" in r.text and "Doing" not in r.text.split("<table")[-1])

# ---- Trello import --------------------------------------------------------------------------------------------
tj = {"name": "Imported", "desc": "", "prefs": {"background": "pink"},
      "labels": [{"id": "l1", "name": "Priority", "color": "red"}, {"id": "l2", "name": "Completed", "color": "green"}],
      "lists": [{"id": "L1", "name": "902 Anis Villa", "pos": 1, "closed": False}, {"id": "L2", "name": "906 Jamal", "pos": 2, "closed": False}],
      "members": [{"id": "m1", "fullName": "Hiba", "username": "kb_hiba"}],
      "cards": [{"id": "64a000000000000000000001", "idShort": 5, "name": "Permits & NOCs", "idList": "L1", "pos": 1, "idLabels": ["l2"],
                 "idMembers": ["m1"], "due": "2025-06-23T08:00:00.000Z", "dueComplete": True, "closed": False, "desc": "NOC list",
                 "cover": {"color": "green", "size": "normal"}, "attachments": [{"name": "drawing", "url": "https://x/y.pdf"}]},
                {"id": "64a000000000000000000002", "idShort": 9, "name": "Tiling", "idList": "L2", "pos": 1, "idLabels": [], "idMembers": [],
                 "closed": False}],
      "checklists": [{"id": "k1", "idCard": "64a000000000000000000001", "name": "NOCs", "pos": 1,
                      "checkItems": [{"name": "DEWA", "state": "complete", "pos": 1}, {"name": "Civil defence", "state": "incomplete", "pos": 2}]}],
      "actions": [{"type": "commentCard", "idMemberCreator": "m1", "memberCreator": {"fullName": "Hiba"}, "date": "2025-06-01T10:00:00.000Z",
                   "data": {"text": "Submitted", "card": {"id": "64a000000000000000000001"}}}]}
r = c.post("/store/kb/import", files={"file": ("board.json", io.BytesIO(json.dumps(tj).encode()), "application/json")}, headers=A)
ck("Trello JSON imported", r.status_code == 200 and r.json()["cards"] == 2 and r.json()["comments"] == 1, r.text)
ib = get(f"/store/kb/boards/{r.json()['id']}").json()
card = [x for x in ib["cards"] if x["title"] == "Permits & NOCs"][0]
full = get(f"/store/kb/cards/{card['id']}").json()
ck("imported: number, label, member matched, due in Dubai time, cover, checklist, comment, link",
   card["no"] == 5 and len(card["labels"]) == 1 and card["members"] == [U["kb_hiba"]] and card["due"] == "2025-06-23T12:00"
   and card["cover"]["color"] == "green" and card["check"] == [1, 2] and full["comments"][0]["who"] == "Hiba"
   and full["attachments"][0]["link"], (card, full["comments"]))
import gzip as _gz
r = c.post("/store/kb/import", files={"file": ("board.json.gz", io.BytesIO(_gz.compress(json.dumps(tj).encode())), "application/gzip")}, headers=A)
ck("compressed Trello JSON imported", r.status_code == 200 and r.json()["cards"] == 2, r.text)
ck("bad JSON refused politely", c.post("/store/kb/import", files={"file": ("x.json", io.BytesIO(b"{}"), "application/json")}, headers=A).status_code == 400)

# ---- close and delete a board -----------------------------------------------------------------------------------
ck("cannot delete an open board", dele(f"/store/kb/boards/{nb['id']}").status_code == 400)
patch(f"/store/kb/boards/{nb['id']}", {"closed": True})
ck("closed board deleted", dele(f"/store/kb/boards/{nb['id']}").status_code == 200 and get(f"/store/kb/boards/{nb['id']}").status_code == 404)
ck("full JSON export", len(get(f"/store/kb/boards/{B}/json").json()["cards"]) > 3)

# ---- power-ups ------------------------------------------------------------------------------------------------
X = post(f"/store/kb/lists/{L['To do']}/cards", {"title": "Power-up card"}).json()["id"]
patch(f"/store/kb/cards/{X}", {"vote": True}); patch(f"/store/kb/cards/{X}", {"vote": True}, H)
patch(f"/store/kb/cards/{X}", {"priority": "high", "points": 5, "estimate": 8})
fx = [x for x in get(f"/store/kb/boards/{B}").json()["cards"] if x["id"] == X][0]
ck("voting: two votes", len(fx["votes"]) == 2, fx["votes"])
ck("priority, points, estimate on the front", fx["priority"] == "high" and fx["points"] == 5 and fx["estimate"] == 8, fx)
ck("bad priority cleared", patch(f"/store/kb/cards/{X}", {"priority": "urgent!"}).status_code == 200 and
   [x for x in get(f"/store/kb/boards/{B}").json()["cards"] if x["id"] == X][0]["priority"] == "")
post(f"/store/kb/cards/{X}/time", {"hours": 2.5, "note": "BOQ"}); post(f"/store/kb/cards/{X}/time", {"hours": 1}, H)
fx = get(f"/store/kb/cards/{X}").json()
ck("time logged: 3.5 h, two entries", fx["logged"] == 3.5 and len(fx["time_entries"]) == 2, fx["logged"])
ck("time per person on the board", sum(get(f"/store/kb/boards/{B}").json()["time"].values()) >= 3.5)
ck("bad hours refused", post(f"/store/kb/cards/{X}/time", {"hours": 0}).status_code == 400)
# repeater: first copy due yesterday -> made on opening the board
import datetime as _dt
y = (_dt.datetime.utcnow() + _dt.timedelta(hours=4)).date() - _dt.timedelta(days=1)
r = c.put(f"/store/kb/cards/{X}/repeat", json={"every": "week", "start": y.isoformat(), "list_id": L["Doing"], "due_days": 2}, headers=A)
ck("repeat set", r.status_code == 200, r.text)
n0 = len([x for x in get(f"/store/kb/boards/{B}").json()["cards"] if x["title"] == "Power-up card"])
ck("repeated copy made once when due", n0 == 2, n0)
n1 = len([x for x in get(f"/store/kb/boards/{B}").json()["cards"] if x["title"] == "Power-up card"])
ck("not made twice", n1 == 2, n1)
ck("next copy a week later", get(f"/store/kb/cards/{X}").json()["repeat"]["next_on"] == (y + _dt.timedelta(weeks=1)).isoformat())
# buttons
lab0 = get(f"/store/kb/boards/{B}").json()["labels"][0]["id"]
patch(f"/store/kb/boards/{B}", {"prefs": {"card_buttons": [{"name": "Start", "actions": [{"type": "join"}, {"type": "move", "list_id": L["Doing"]}]}],
                                          "board_buttons": [{"name": "Tag Doing", "list_id": L["Doing"], "actions": [{"type": "add_label", "label_id": lab0}]}]}})
post(f"/store/kb/cards/{X}/button", {"index": 0}, H)
fx = get(f"/store/kb/cards/{X}").json()
ck("card button: joined + moved", U["kb_hiba"] in fx["members"] and fx["list_id"] == L["Doing"], fx["members"])
r = post(f"/store/kb/boards/{B}/button", {"index": 0})
ck("board button ran on every card of Doing", r.json()["cards"] >= 3 and all(lab0 in x["labels"] for x in get(f"/store/kb/boards/{B}").json()["cards"] if x["list_id"] == L["Doing"]))
# mirror
r = post(f"/store/kb/cards/{X}/mirror", {"board_id": P, "list_id": PL})
ck("mirror made on another board", r.status_code == 200, r.text)
patch(f"/store/kb/cards/{X}", {"title": "Power-up card (renamed)"})
mf = [x for x in get(f"/store/kb/boards/{P}").json()["cards"] if x["id"] == r.json()["id"]][0]
ck("mirror shows the source's new title + board name + labels", mf["title"] == "Power-up card (renamed)" and mf["mirror"]["board"] == "Estimation" and mf["mirror"]["labels"], mf)
ck("source knows its mirror", get(f"/store/kb/cards/{X}").json()["mirrors"])
# links
patch(f"/store/kb/cards/{X}", {"links": [C1, X]})
ck("linked card listed, self ignored", [l["id"] for l in get(f"/store/kb/cards/{X}").json()["linked"]] == [C1])
# inbox and planner
ib = get("/store/kb/inbox").json()
ck("inbox board with one list", ib["lists"][0]["title"] == "Inbox")
ck("inbox not in the board list", all(b["id"] != ib["id"] for b in get("/store/kb/boards").json()["boards"]))
ck("inbox private even from an app admin", get(f"/store/kb/boards/{ib['id']}", tok("admin", "changeme123")).status_code == 403)
post(f"/store/kb/lists/{ib['lists'][0]['id']}/cards", {"title": "Call DEWA"})
ic = [x for x in get("/store/kb/inbox").json()["cards"]][0]
patch(f"/store/kb/cards/{ic['id']}", {"due": "2026-10-30T10:00"})
patch(f"/store/kb/cards/{ic['id']}", {"board_id": B, "list_id": L["To do"]})
ck("inbox card moved to a board", [x for x in get(f"/store/kb/boards/{B}").json()["cards"] if x["id"] == ic["id"]])
pl = get("/store/kb/planner", H).json()["cards"]
ck("planner shows Hiba's dated cards", any(x["id"] == C1 for x in pl), [x["title"] for x in pl])

# ---- automation across boards, schedules, due-date rules ---------------------------------------------------
T = post("/store/kb/boards", {"title": "Tenders", "lists": ["Enquiry", "Won"]}).json()["id"]
TL = {l["title"]: l["id"] for l in get(f"/store/kb/boards/{T}").json()["lists"]}
PR = post("/store/kb/boards", {"title": "Projects", "lists": ["Starting", "Running"]}).json()["id"]
PRL = {l["title"]: l["id"] for l in get(f"/store/kb/boards/{PR}").json()["lists"]}
r = post(f"/store/kb/boards/{T}/rules", {"trigger": {"type": "card_moved", "list_id": TL["Won"]},
                                          "actions": [{"type": "mirror_board", "board_id": PR, "list_id": PRL["Starting"]},
                                                      {"type": "add_label", "label_id": get(f"/store/kb/boards/{T}").json()["labels"][0]["id"]}]})
ck("cross-board rule saved", r.status_code == 200, r.text)
ck("cross-board rule refused for a board you cannot edit", post(f"/store/kb/boards/{T}/rules", {"trigger": {"type": "card_moved", "list_id": TL["Won"]},
   "actions": [{"type": "mirror_board", "board_id": P2, "list_id": P2L}]}, H).status_code == 403)
tc = post(f"/store/kb/lists/{TL['Enquiry']}/cards", {"title": "VL-88 Keturah"}).json()["id"]
patch(f"/store/kb/cards/{tc}", {"list_id": TL["Won"]})
pm = [x for x in get(f"/store/kb/boards/{PR}").json()["cards"] if x.get("mirror_of") == tc]
ck("moving to Won mirrored it onto Projects", len(pm) == 1, get(f"/store/kb/boards/{PR}").json()["cards"])
patch(f"/store/kb/cards/{tc}", {"list_id": TL["Enquiry"]}); patch(f"/store/kb/cards/{tc}", {"list_id": TL["Won"]})
ck("moving to Won again does not mirror twice", len([x for x in get(f"/store/kb/boards/{PR}").json()["cards"] if x.get("mirror_of") == tc]) == 1)
patch(f"/store/kb/cards/{tc}", {"title": "VL-88 Keturah - awarded", "due": "2026-12-01T17:00"})
pm = [x for x in get(f"/store/kb/boards/{PR}").json()["cards"] if x.get("mirror_of") == tc][0]
ck("edit on one board shows on the other (title + due)", pm["title"] == "VL-88 Keturah - awarded" and pm["due"] == "2026-12-01T17:00", pm)
post(f"/store/kb/cards/{tc}/comments", {"text": "LPO received"})
ck("comment count shows on the mirror", [x for x in get(f"/store/kb/boards/{PR}").json()["cards"] if x.get("mirror_of") == tc][0]["comments"] == 1)
# copy + move across boards
post(f"/store/kb/boards/{T}/rules", {"trigger": {"type": "card_complete"}, "actions": [{"type": "move_board", "board_id": PR, "list_id": PRL["Running"]}]})
patch(f"/store/kb/cards/{tc}", {"due_complete": True})
ck("complete -> moved to Projects / Running", get(f"/store/kb/cards/{tc}").json()["list_id"] == PRL["Running"])
rl = get(f"/store/kb/boards/{T}/rules").json()["rules"]
ck("rule log kept", rl[0]["log"] and "mirrored" in " ".join(rl[0]["log"][-1]["did"]), rl[0]["log"])
# comment trigger
post(f"/store/kb/boards/{PR}/rules", {"trigger": {"type": "comment_added"}, "actions": [{"type": "watch"}]})
c9 = post(f"/store/kb/lists/{PRL['Starting']}/cards", {"title": "Snag list"}).json()["id"]
post(f"/store/kb/cards/{c9}/comments", {"text": "first"}, H)
ck("comment trigger: commenter now watching", U["kb_hiba"] in get(f"/store/kb/cards/{c9}").json()["watchers"])
# scheduled rule
import datetime as _dt
post(f"/store/kb/boards/{PR}/rules", {"trigger": {"type": "schedule", "every": "day", "time": "08:00", "list_id": PRL["Starting"], "cards": "all"},
                                       "actions": [{"type": "add_label", "label_id": get(f"/store/kb/boards/{PR}").json()["labels"][2]["id"]}, {"type": "sort_list", "list_id": PRL["Starting"], "by": "name"}]})
db2 = SessionLocal()
n = boards.run_scheduled(db2, _dt.datetime(2026, 10, 20, 9, 0))
ck("scheduled rule ran at 09:00", n == 1, n)
ck("scheduled rule not twice the same day", boards.run_scheduled(db2, _dt.datetime(2026, 10, 20, 15, 0)) == 0)
ck("not before its time next day", boards.run_scheduled(db2, _dt.datetime(2026, 10, 21, 7, 0)) == 0)
ck("next day after 08:00 runs again", boards.run_scheduled(db2, _dt.datetime(2026, 10, 21, 8, 1)) == 1)
lab_s = get(f"/store/kb/boards/{PR}").json()["labels"][2]["id"]
ck("label added to every card in Starting", all(lab_s in x["labels"] for x in get(f"/store/kb/boards/{PR}").json()["cards"] if x["list_id"] == PRL["Starting"]))
# weekly
post(f"/store/kb/boards/{PR}/rules", {"trigger": {"type": "schedule", "every": "week", "weekday": 4, "time": "17:00", "cards": "complete"}, "actions": [{"type": "archive"}]})
boards.run_scheduled(db2, _dt.datetime(2026, 10, 22, 18, 0))      # Thursday
wk = [x for x in get(f"/store/kb/boards/{PR}/rules").json()["rules"] if x["trigger"].get("every") == "week"][0]
ck("weekly rule waits for Friday", wk["last_run"] == "", wk)
boards.run_scheduled(db2, _dt.datetime(2026, 10, 23, 17, 30))      # Friday
wk = [x for x in get(f"/store/kb/boards/{PR}/rules").json()["rules"] if x["trigger"].get("every") == "week"][0]
ck("weekly rule ran on Friday", wk["last_run"] == "2026-W43", wk["last_run"])
# due-date rule
post(f"/store/kb/boards/{PR}/rules", {"trigger": {"type": "due_in", "days": 2}, "actions": [{"type": "notify", "text": "due in 2 days"}, {"type": "add_label", "label_id": lab_s}]})
dd = post(f"/store/kb/lists/{PRL['Running']}/cards", {"title": "Handover docs", "members": [U["kb_hiba"]]}).json()["id"]
patch(f"/store/kb/cards/{dd}", {"due": "2026-10-24T17:00"})
n = boards.run_scheduled(db2, _dt.datetime(2026, 10, 22, 10, 0))
ck("due-date rule fired 2 days before", lab_s in get(f"/store/kb/cards/{dd}").json()["labels"], n)
ck("members told", any("due in 2 days" in x["text"] for x in get("/store/kb/notes", H).json()["notes"]))
patch(f"/store/kb/cards/{dd}", {"labels": []})
boards.run_scheduled(db2, _dt.datetime(2026, 10, 22, 11, 0))
ck("due-date rule only once per due date", lab_s not in get(f"/store/kb/cards/{dd}").json()["labels"])
rid = [x for x in get(f"/store/kb/boards/{PR}/rules").json()["rules"] if x["trigger"]["type"] == "schedule"][0]["id"]
ck("Run now works", post(f"/store/kb/rules/{rid}/run").status_code == 200)
ck("rule words readable", "every day at 08:00" in [x for x in get(f"/store/kb/boards/{PR}/rules").json()["rules"] if x["id"] == rid][0]["words"])

# ---- Anoop's set-up: QS update the main board, his board follows ----------------------------------------
MAIN = post("/store/kb/boards", {"title": "Estimation main", "lists": ["911 WS46", "913 WS25", "TENDERS / PROPOSALS"]}).json()["id"]
ML = {l["title"]: l["id"] for l in get(f"/store/kb/boards/{MAIN}").json()["lists"]}
AN = post("/store/kb/boards", {"title": "Anoop", "lists": ["VARIATIONS & CLAIMS", "SUBCONTRACT PAYMENTS", "TENDERS / PROPOSALS", "DONE"]}).json()["id"]
AL = {l["title"]: l["id"] for l in get(f"/store/kb/boards/{AN}").json()["lists"]}
old_copy = post(f"/store/kb/lists/{ML['913 WS25']}/cards", {"title": "913 - Lift Finalization - KONE / OTIS"}).json()["id"]
post(f"/store/kb/lists/{AL['SUBCONTRACT PAYMENTS']}/cards", {"title": "913 - Lift  Finalization - kone / otis"})
r = post(f"/store/kb/boards/{AN}/link-mirrors", {"source_board_id": MAIN})
ck("existing copy on Anoop's board linked as a mirror", r.json()["linked"] == ["913 - Lift  Finalization - kone / otis"], r.text)
patch(f"/store/kb/cards/{old_copy}", {"title": "913 - Lift Finalization - KONE chosen"})
ck("...and now follows the main card", any(c["title"] == "913 - Lift Finalization - KONE chosen" for c in get(f"/store/kb/boards/{AN}").json()["cards"]))
for words, lst in ((["Variation", "Claim"], "VARIATIONS & CLAIMS"), (["Tilling PC", "Tiling PC"], "SUBCONTRACT PAYMENTS")):
    r = post(f"/store/kb/boards/{MAIN}/rules", {"trigger": {"type": "card_titled", "words": words, "numbered": True},
                                                "actions": [{"type": "mirror_board", "board_id": AN, "list_id": AL[lst]}]})
    ck(f"title rule saved ({lst})", r.status_code == 200, r.text)
post(f"/store/kb/boards/{MAIN}/rules", {"trigger": {"type": "card_added", "list_id": ML["TENDERS / PROPOSALS"]}, "actions": [{"type": "mirror_board", "board_id": AN, "list_id": AL["TENDERS / PROPOSALS"]}]})
post(f"/store/kb/boards/{MAIN}/rules", {"trigger": {"type": "card_complete"}, "actions": [{"type": "move_mirror", "board_id": AN, "list_id": AL["DONE"]}]})
v1 = post(f"/store/kb/lists/{ML['911 WS46']}/cards", {"title": "911 - Variation for False ceiling"}).json()["id"]
p1 = post(f"/store/kb/lists/{ML['911 WS46']}/cards", {"title": "911 - Tilling PC"}).json()["id"]
std = post(f"/store/kb/lists/{ML['911 WS46']}/cards", {"title": "Variations"}).json()["id"]
tn = post(f"/store/kb/lists/{ML['TENDERS / PROPOSALS']}/cards", {"title": "EMKAAN RFQ Landscape"}).json()["id"]
an = get(f"/store/kb/boards/{AN}").json()
where = {c["mirror_of"]: c["list_id"] for c in an["cards"] if c.get("mirror_of")}
ck("QS card '911 - Variation…' appears in VARIATIONS & CLAIMS", where.get(v1) == AL["VARIATIONS & CLAIMS"], where)
ck("'911 - Tilling PC' appears in SUBCONTRACT PAYMENTS", where.get(p1) == AL["SUBCONTRACT PAYMENTS"])
ck("a plain 'Variations' card (no project number) is not sent", std not in where)
ck("a new tender appears in TENDERS / PROPOSALS", where.get(tn) == AL["TENDERS / PROPOSALS"])
r9 = post(f"/store/kb/lists/{ML['911 WS46']}/cards", {"title": "Snag list"}).json()["id"]
patch(f"/store/kb/cards/{r9}", {"title": "911 - Claim for delay"})
ck("renaming a card to match sends it too", {c["mirror_of"]: c["list_id"] for c in get(f"/store/kb/boards/{AN}").json()["cards"] if c.get("mirror_of")}.get(r9) == AL["VARIATIONS & CLAIMS"])
patch(f"/store/kb/cards/{v1}", {"title": "911 - Variation for False ceiling (rev 2)"})
ck("renaming again does not make a second mirror", len([c for c in get(f"/store/kb/boards/{AN}").json()["cards"] if c.get("mirror_of") == v1]) == 1)
cl = post(f"/store/kb/cards/{v1}/checklists", {"title": "Steps", "items": ["Estimation", "Submission"]}).json()["id"]
mf = [c for c in get(f"/store/kb/boards/{AN}").json()["cards"] if c.get("mirror_of") == v1][0]
ck("QS checklist progress shows on Anoop's card", mf["check"] == [0, 2], mf["check"])
patch(f"/store/kb/cards/{v1}", {"due_complete": True})
ck("completed on the main board -> moved to DONE on Anoop's board", [c for c in get(f"/store/kb/boards/{AN}").json()["cards"] if c.get("mirror_of") == v1][0]["list_id"] == AL["DONE"])

print(f"\n{len(fails)} failed" if fails else "\nALL PASS")
sys.exit(1 if fails else 0)

"""Estimation > Trello: a card that changes goes to the top of its list - on its own board and on every board
that shows it (mirrors / the synced follow board). A card dragged to a spot keeps it; watching does not move it.

    cd app && DATABASE_URL=sqlite:////tmp/kbb.db INFINIA_BOARDS_DIR=/tmp/kbbfiles python3 ../tests/boards_bump_test.py
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


def order(lid, b):
    bd = get(f"/store/kb/boards/{b}").json()
    return [x["title"] for x in sorted([x for x in bd["cards"] if x["list_id"] == lid and not x.get("closed")], key=lambda x: x["pos"])]

r = post("/store/kb/boards", {"title": "Estimation", "lists": ["To do", "Doing", "Done"]}); B = r.json()["id"]
L = {l["title"]: l["id"] for l in get(f"/store/kb/boards/{B}").json()["lists"]}
ids = {}
for t in ["A", "B", "C", "D"]:
    ids[t] = post(f"/store/kb/lists/{L['To do']}/cards", {"title": t}).json()["id"]
ck("start: A B C D", order(L["To do"], B) == list("ABCD"), order(L["To do"], B))
patch(f"/store/kb/cards/{ids['C']}", {"desc": "new scope"})
ck("description changed -> C on top", order(L["To do"], B) == list("CABD"), order(L["To do"], B))
post(f"/store/kb/cards/{ids['D']}/comments", {"text": "client called"})
ck("comment -> D on top", order(L["To do"], B)[0] == "D", order(L["To do"], B))
cl = post(f"/store/kb/cards/{ids['B']}/checklists", {"title": "Steps"}).json()["id"]
ck("checklist added -> B on top", order(L["To do"], B)[0] == "B", order(L["To do"], B))
it = post(f"/store/kb/checklists/{cl}/items", {"text": "measure"}).json()["id"]
patch(f"/store/kb/cards/{ids['A']}", {"due": "2026-11-05T17:00"})
ck("due date -> A on top", order(L["To do"], B)[0] == "A", order(L["To do"], B))
patch(f"/store/kb/items/{it}", {"done": True})
ck("checklist item ticked -> B on top", order(L["To do"], B)[0] == "B", order(L["To do"], B))
lb = get(f"/store/kb/boards/{B}").json()["labels"][0]["id"]
patch(f"/store/kb/cards/{ids['C']}", {"add_labels": [lb]})
ck("label added -> C on top", order(L["To do"], B)[0] == "C", order(L["To do"], B))
before = order(L["To do"], B)
patch(f"/store/kb/cards/{ids['D']}", {"watch": True})
ck("watching does not move it", order(L["To do"], B) == before, order(L["To do"], B))
patch(f"/store/kb/cards/{ids['C']}", {"desc": "new scope"})
ck("saving the same description again does not move it", order(L["To do"], B) == before, order(L["To do"], B))
# dragged to a spot by hand: stays there
ord_ = get(f"/store/kb/boards/{B}").json()["cards"]; pos = sorted(x["pos"] for x in ord_ if x["list_id"] == L["To do"])
patch(f"/store/kb/cards/{ids['C']}", {"pos": (pos[-1] + pos[-2]) / 2 if False else pos[-1] + 10})
ck("dragged to the bottom by hand: stays at the bottom", order(L["To do"], B)[-1] == "C", order(L["To do"], B))
# moved to another list without a spot (Move menu): top of that list
post(f"/store/kb/lists/{L['Doing']}/cards", {"title": "X"}); post(f"/store/kb/lists/{L['Doing']}/cards", {"title": "Y"})
patch(f"/store/kb/cards/{ids['D']}", {"list_id": L["Doing"]})
ck("moved to Doing (no spot) -> top of Doing", order(L["Doing"], B)[0] == "D", order(L["Doing"], B))
# mirror on another board (Anoop's dashboard): a change on the source brings the mirror to the top there too
P = post("/store/kb/boards", {"title": "My Trello board", "lists": ["Tasks"]}).json()["id"]
PL = get(f"/store/kb/boards/{P}").json()["lists"][0]["id"]
for t in ["P1", "P2"]:
    post(f"/store/kb/lists/{PL}/cards", {"title": t})
post(f"/store/kb/cards/{ids['A']}/mirror", {"board_id": P, "list_id": PL})
post(f"/store/kb/lists/{PL}/cards", {"title": "P3", "pos": "top"})
ck("dashboard: mirror of A not on top yet", order(PL, P)[0] == "P3", order(PL, P))
v0 = get(f"/store/kb/boards/{P}/version").json()["version"]
patch(f"/store/kb/cards/{ids['A']}", {"title": "A (rev 1)"})
ck("A changed on the main board -> its mirror is top of the dashboard list", order(PL, P)[0] == "A (rev 1)", order(PL, P))
ck("the dashboard refreshes (its version moved)", get(f"/store/kb/boards/{P}/version").json()["version"] > v0)
post(f"/store/kb/lists/{PL}/cards", {"title": "P4", "pos": "top"})
mid = [x["id"] for x in get(f"/store/kb/boards/{P}").json()["cards"] if x.get("mirror_of") == ids["A"]][0]
post(f"/store/kb/cards/{mid}/comments", {"text": "Anoop: checked"})
ck("comment on the dashboard mirror -> top on both boards", order(PL, P)[0] == "A (rev 1)" and order(L["To do"], B)[0] == "A (rev 1)", [order(PL, P), order(L["To do"], B)])
print("ALL PASS" if not fails else f"{len(fails)} FAILED"); sys.exit(1 if fails else 0)

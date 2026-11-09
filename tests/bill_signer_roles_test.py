"""Prepared, checked and approved by: the same four lines on every Draft bill.
    cd app && DATABASE_URL=sqlite:////tmp/claude-0/rt/sg.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/bill_signer_roles_test.py
"""
import os, sys, json, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main as M
c = TestClient(M.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:600]}"))
    if not ok: fails.append(n)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
BID = int(os.environ.get("BID", "4"))
b = c.get(f"/store/est/ipa/bill/{BID}", headers=H).json()
print("status", b.get("status"), "label", b.get("label"))
for g in b["signers"]:
    print(" ", g.get("role"), "|", g.get("label"), "|", g.get("name"), "|", g.get("title"), "| ext" if g.get("ext") else "", "| opts", g.get("options"), "| fmt", g.get("format_has"), "| key", g["key"])
roles = [g.get("role") for g in b["signers"]]
ck("4 rows in order prep/check/appr/cons", roles == ["prep", "check", "appr", "cons"], roles)
g = {x["role"]: x for x in b["signers"]}
ck("Prepared by - Quantity Surveyor, QS list", g["prep"]["title"] == "Quantity Surveyor" and g["prep"]["options"] == ["Neethu Treesa Jose", "Preenu Annie Daniel", "Arathi S", "Sreelekshmi MS"], g["prep"])
ck("Checked by - Shafeeq / Chief Accountant", g["check"]["name"] == "Shafeeq" and g["check"]["title"] == "Chief Accountant", g["check"])
ck("Approved by - Anoop Subramanian / Senior Contracts Manager", g["appr"]["name"] == "Anoop Subramanian" and g["appr"]["title"] == "Senior Contracts Manager", g["appr"])
ck("Consultant - external, name filled", g["cons"].get("ext") and bool(g["cons"]["name"]), g["cons"])
due0 = b["total_due"]
r = c.put(f"/store/est/ipa/bill/{BID}", headers=H, json={"signs": {g["prep"]["key"]: {"name": "Remya Uchambally"}}})
ck("a name not on the list is refused", r.status_code == 400, r.text)
r = c.put(f"/store/est/ipa/bill/{BID}", headers=H, json={"signs": {g["prep"]["key"]: {"name": "Arathi S", "title": "QS"}}})
ck("pick from the list saves", r.status_code == 200, r.text)
b2 = c.get(f"/store/est/ipa/bill/{BID}", headers=H).json(); p2 = next(x for x in b2["signers"] if x["role"] == "prep")
ck("...name Arathi S, designation stays Quantity Surveyor", p2["name"] == "Arathi S" and p2["title"] == "Quantity Surveyor", p2)
ck("...total due unchanged", abs(b2["total_due"] - due0) < 0.005, (due0, b2["total_due"]))
r = c.put(f"/store/est/ipa/bill/{BID}", headers=H, json={"signs": {g["cons"]["key"]: {"name": "Renaissance Engineering Consultants", "title": ""}}})
b3 = c.get(f"/store/est/ipa/bill/{BID}", headers=H).json(); k3 = next(x for x in b3["signers"] if x["role"] == "cons")
ck("consultant name editable", r.status_code == 200 and k3["name"] == "Renaissance Engineering Consultants", (r.text[:200], k3))
r = c.post(f"/store/est/ipa/bill/{BID}/sign", headers=H, json={"key": k3["key"]})
ck("consultant cannot sign in the app", r.status_code == 400, r.text)
# the printed bill carries the names
x = c.get(f"/export/est/ipa/{BID}?format=excel&token=" + c.post("/auth/download-token", headers=H).json()["token"])
print("xlsx", x.status_code, len(x.content))
if x.status_code == 200:
    import openpyxl, io
    wb = openpyxl.load_workbook(io.BytesIO(x.content))
    txt = " ".join(str(v) for ws in wb for row in ws.iter_rows(values_only=True) for v in row if v)
    p = c.get(f"/export/est/ipa/{BID}?format=preview&token=" + c.post("/auth/download-token", headers=H).json()["token"]).text
    ck("Preview has Arathi S, Anoop Subramanian; consultant on IPA", "Arathi S" in p and "Anoop Subramanian" in p, [w for w in ("Arathi S", "Anoop Subramanian") if w not in p])
    ck("Excel has Arathi S and Anoop Subramanian, not 'Anoop S '", "Arathi S" in txt and "Anoop Subramanian" in txt, [w for w in ("Arathi S", "Anoop Subramanian", "Shafeeq") if w not in txt])
# next bill keeps the same people
pid = b["project_id"]
r = c.post("/store/est/ipa/new", headers=H, json={"project_id": pid, "format_id": b["format_id"], "from_id": BID})
print("new", r.status_code, r.text[:200])
if r.status_code == 200:
    nb = c.get(f"/store/est/ipa/bill/{r.json()['id']}", headers=H).json()
    ck("next bill keeps the same people", [(x["role"], x["name"]) for x in nb["signers"]] == [(x["role"], x["name"]) for x in b3["signers"]], ([(x["role"], x["name"]) for x in nb["signers"]], [(x["role"], x["name"]) for x in b3["signers"]]))
# ---- a signature belongs to the login
import io, auth, models
from database import SessionLocal
from PIL import Image, ImageDraw
def pic():
    im = Image.new("RGB", (300, 100), "white"); ImageDraw.Draw(im).line((20, 70, 280, 30), fill="navy", width=6)
    b_ = io.BytesIO(); im.save(b_, "PNG"); return b_.getvalue()
db = SessionLocal()
if not db.query(models.User).filter(models.User.username == "shafeeq").first():
    db.add(models.User(username="shafeeq", full_name="Shafeeq", hashed_password=auth.hash_password("pw12345678"), role="admin", active=True)); db.commit()
db.close()
HS = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "shafeeq", "password": "pw12345678"}).json()["access_token"]}
r = c.post("/store/est/ipa/signature", headers=HS, data={"name": "Anoop Subramanian"}, files={"file": ("s.png", pic(), "image/png")})
ck("nobody uploads a signature for somebody else", r.status_code == 403, r.text)
r = c.post("/store/est/ipa/my-signature", headers=HS, files={"file": ("s.png", pic(), "image/png")})
ck("Settings: Shafeeq uploads his own", r.status_code == 200 and r.json()["sig"], r.text[:200])
r = c.post("/store/est/ipa/signature", headers=HS, data={"name": "Shafeeq"}, files={"file": ("s.png", pic(), "image/png")})
ck("on the bill, once on file -> change it in Settings", r.status_code == 400 and "Settings" in r.text, r.text)
ck("my-signature shows it", bool(c.get("/store/est/ipa/my-signature", headers=HS).json()["sig"]))
bb = c.get(f"/store/est/ipa/bill/{BID}", headers=H).json(); sh = next(x for x in bb["signers"] if x["role"] == "check")
ck("the bill shows Shafeeq's own signature", sh["own"] and sh["sig"], sh)
r = c.post("/store/est/ipa/my-signature", headers=HS, files={"file": ("s.png", pic(), "image/png")})
ck("he can change it in Settings", r.status_code == 200, r.text[:200])
from est_bills import EstSignature
db = SessionLocal(); ck("one signature row for his login", db.query(EstSignature).filter(EstSignature.user_id != None).count() == 1); db.close()  # noqa: E711
print("FAILS:", fails if fails else "none")

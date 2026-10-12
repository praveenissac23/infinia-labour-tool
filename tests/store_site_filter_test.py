"""At Sites with one site picked: screen, preview, PDF and Excel all hold
only that site's lines."""
import os, sys, io
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
os.environ.setdefault("INFINIA_NO_PUSH", "1")
from datetime import date
from fastapi.testclient import TestClient
import main, models, auth
from database import SessionLocal
FAIL = []
def ck(l, ok, x=""):
    print(("PASS " if ok else "FAIL ") + l + ("" if ok else f"  [{x}]"))
    if not ok: FAIL.append(l)
db = SessionLocal()
db.add(models.User(username="a", hashed_password=auth.hash_password("p"), full_name="A", role="admin"))
db.commit(); db.close()
c = TestClient(main.app)
h = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "a", "password": "p"}).json()["access_token"]}
for code in ("912", "905"):
    c.post("/store/locations", headers=h, json={"code": code, "name": "Site " + code})
s = SessionLocal()
a = models.StoreItem(code="HAM", name="Hammer", unit="pcs", item_type="asset", active=True)
b = models.StoreItem(code="FAN", name="Stand Fan", unit="pcs", item_type="asset", active=True)
s.add_all([a, b]); s.commit(); ia, ib = a.id, b.id; s.close()
today = date.today().isoformat()
for iid in (ia, ib):
    c.post("/store/movements", headers=h, json={"item_id": iid, "kind": "in", "qty": 10, "moved_on": today})
r1 = c.post("/store/movements", headers=h, json={"item_id": ia, "kind": "out", "qty": 2, "location": "912", "incharge": "X", "moved_on": today})
r2 = c.post("/store/movements", headers=h, json={"item_id": ib, "kind": "out", "qty": 3, "location": "905", "incharge": "X", "moved_on": today})
ck("moves saved", r1.status_code == 200 and r2.status_code == 200, (r1.text[:200], r2.text[:200]))
all_ = c.get("/store/report?kind=by_site", headers=h).json()
ck("all sites: both", {r["site"] for r in all_["rows"]} == {"912", "905"}, all_)
one = c.get("/store/report?kind=by_site&site=912", headers=h).json()
ck("screen: only 912", [r["code"] for r in one["rows"]] == ["HAM"] and one["title"] == "What site 912 is holding", one)
tok = c.post("/auth/download-token", headers=h).json().get("token") or c.get("/auth/download-token", headers=h).json().get("token")
v = c.get(f"/export/store/report/view?kind=by_site&site=912&token={tok}")
ck("preview: only 912", v.status_code == 200 and "Hammer" in v.text and "Stand Fan" not in v.text and "What site 912" in v.text, v.text[:300])
x = c.get(f"/export/store/report?kind=by_site&site=912&format=excel&token={tok}")
import openpyxl
wb = openpyxl.load_workbook(io.BytesIO(x.content)); txt = " ".join(str(cl.value) for row in wb.active.iter_rows() for cl in row if cl.value)
ck("excel: only 912", "Hammer" in txt and "Stand Fan" not in txt, txt[:300])
p = c.get(f"/export/store/report?kind=by_site&site=912&format=pdf&token={tok}")
ck("pdf made", p.status_code == 200 and p.content[:4] == b"%PDF")
print("\nALL PASS" if not FAIL else f"\n{len(FAIL)} FAILED: {FAIL}")

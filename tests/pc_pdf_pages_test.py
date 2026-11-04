"""Payment certificate PDF uses its pages properly (4 Nov 2026): no page carrying only a run-over line or two, and no
table jumping whole to the next page leaving the page before half empty - whatever the number of lines.
    cd app && DATABASE_URL=sqlite:////tmp/pp.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/pc_pdf_pages_test.py
"""
import copy, os, subprocess, sys, tempfile
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main as M
import estimation as E
import est_pcsheet as S
from database import SessionLocal
c = TestClient(M.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:300]}"))
    if not ok: fails.append(n)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
pid = next(p for p in c.get("/store/est/meta", headers=H).json()["projects"] if p["code"] == "912")["id"]
sid = c.post("/store/est/subs", headers=H, json={"project_id": pid, "name": "Pages Test Manpower", "value": 0, "vat_pct": 5}).json()["id"]
items = [{"bill": "1", "section": "A MANPOWER SUPPLY", "no": str(n), "description": f"Manpower supply for item {n} - steel & shutter works", "qty": 10 * n,
          "unit": "M3", "rate": 150, "measure": "qty"} for n in range(1, 10)]
c.put(f"/store/est/subs/{sid}/items", headers=H, json={"items": items})
pc = c.post("/store/est/subpcs", headers=H, json={"sub_id": sid, "inv_ref": "PG/1", "inv_amount": 1000, "received": "2026-10-01"}).json()["id"]
sh = c.get(f"/store/est/subpcs/{pc}/sheet", headers=H).json()
c.put(f"/store/est/subpcs/{pc}/sheet", headers=H, json={"lines": [{"item_id": x["id"], "qty": 5} for x in sh["items"]],
      "deds": [{"cat": "Manpower", "on_date": "2026-09-30", "description": "Manpower supplied", "qty": 3, "unit": "No", "rate": 90}]})
db = SessionLocal()
p_ = db.get(E.EstSubPC, pc)
base = S.build_doc(db, p_); base["hide"] = {"A": [3, 5]}


def lines(buf):
    f = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False); f.write(buf); f.close()
    t = subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True).stdout.split("\f")
    return [len([l for l in x.splitlines() if l.strip()]) for x in t if x.strip()]


short, seen_fix = [], 0
for n in range(0, 90, 2):
    doc = copy.deepcopy(base)
    b = doc["bills"][0]
    b["rows"] = b["rows"] + [copy.deepcopy(b["rows"][-1]) for _ in range(n)]
    L = lines(S.render_pdf(doc).getvalue())
    if S._render_pdf(doc, 1.0)[1]:
        seen_fix += 1                      # this one had a near-empty page at full size: fixed by tightening
    if any(x <= 6 for x in L[1:]):         # header + footer are 3 lines: <= 6 = 3 lines or fewer of content
        short.append((n, L))
ck(f"no PDF page with only a few run-over lines, from 9 to 99 Appendix A lines ({seen_fix} needed tightening)", not short, short[:5])
# a table that does not fit the rest of a page runs on - it does not jump whole to the next page
doc = copy.deepcopy(base); b = doc["bills"][0]; b["rows"] = b["rows"] + [copy.deepcopy(b["rows"][-1]) for _ in range(25)]
L = lines(S.render_pdf(doc).getvalue())
ck(f"Appendix A table runs on across the page (lines per page {L})", L[1] >= 25, L)
db.close()
print("ALL PASS" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)

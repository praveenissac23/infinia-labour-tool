"""Payment certificate, Appendix A (3 Nov 2026): Int. Qty and Contract amt are internal. Order: Int. Qty, Unit,
Contract amt, Rate, Measured ... Shown while the certificate is worked on; hidden once the Contracts manager approves it
(the copy that goes to the subcontractor) - and either way can be asked for: preview, PDF and Share follow.
    cd app && DATABASE_URL=sqlite:////tmp/ic.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/pc_internal_cols_test.py
"""
import os, re, subprocess, sys, tempfile
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main as M
c = TestClient(M.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:500]}"))
    if not ok: fails.append(n)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
tok = lambda: c.post("/auth/download-token", headers=H).json()["token"]
pid = next(p for p in c.get("/store/est/meta", headers=H).json()["projects"] if p["code"] == "912")["id"]
sid = c.post("/store/est/subs", headers=H, json={"project_id": pid, "name": "Int Cols Manpower", "value": 0, "vat_pct": 5}).json()["id"]
items = [{"bill": "1", "section": "A MANPOWER SUPPLY", "no": "2", "description": "Manpower supply for Raft - steel & shutter", "qty": 286, "unit": "M3", "rate": 150, "measure": "qty"},
         {"bill": "1", "section": "A MANPOWER SUPPLY", "no": "3", "description": "Manpower supply for Retaining wall", "qty": 86, "unit": "M3", "rate": 250, "measure": "qty"}]
r = c.put(f"/store/est/subs/{sid}/items", headers=H, json={"items": items})
ck("schedule saved", r.status_code == 200, r.text)
pc = c.post("/store/est/subpcs", headers=H, json={"sub_id": sid, "inv_ref": "IC/1", "inv_amount": 1000, "received": "2026-10-01"}).json()["id"]
sh = c.get(f"/store/est/subpcs/{pc}/sheet", headers=H).json()
lines = [{"item_id": x["id"], "qty": 195 if x["no"] == "2" else 68} for x in sh["items"]]
r = c.put(f"/store/est/subpcs/{pc}/sheet", headers=H, json={"lines": lines})
ck(f"measured filled: work to date {r.json()['pc']['work_cum']:,.2f} (195x150 + 68x250 = 46,250.00)", r.status_code == 200 and abs(r.json()["pc"]["work_cum"] - 46250) < 0.01, r.text[:300])

def prev(q=""):
    return c.get(f"/export/est/pc/{pc}?token={tok()}&format=preview{q}").text
def pdf_txt(q=""):
    b = c.get(f"/export/est/pc/{pc}?token={tok()}&format=pdf{q}").content
    f = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False); f.write(b); f.close()
    return subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True).stdout
def heads(h):
    m = re.search(r"<th>No</th><th>Description</th><th>Type</th>(.*?)</tr>", h)
    return ["No", "Description", "Type"] + re.findall(r"<th[^>]*>(.*?)</th>", m.group(1)) if m else []

# ---- before the CM approves: shown
h = prev()
hd = heads(h)
ck(f"order: Int. Qty, Unit, Contract amt, Rate, Measured ({hd[3:8]})", [re.sub("<[^>]+>", "", x) for x in hd[3:8]] == ["Int. Qty", "Unit", "Contract amt", "Rate", "Measured"], hd)
ck("before CM approval: nothing hidden, button 'Hide columns'", "window.PC_HIDE={}" in h and ">Hide columns<" in h, h[:300])
t = pdf_txt()
ck("PDF before approval: Int. Qty and Contract amt there", "Int. Qty" in t and "Contract amt" in t and "42,900.00" in t, t[:1500])
ck("PDF row: 286 M3 42,900.00 150.00 (Int. Qty, Unit, Contract amt, Rate)", re.search(r"286\s+M3\s+42,900\.00\s+150\.00", t) is not None, t[:3000])

# ---- after the CM approves: Int. Qty and Contract amt left off by default
for st in ("Certified", "Prepared", "CM approved"):
    r = c.post(f"/store/est/subpcs/{pc}/step", headers=H, json={"step": st})
ck("CM approved", r.status_code == 200 and r.json()["status"] == "CM approved", r.text)
h = prev()
# 7 Nov 2026 (Anoop): the subcontractor's copy shows the quantity and the contract amount too
ck("after CM approval: nothing hidden by default (Int. Qty and Contract amt stay)", 'window.PC_HIDE={}' in h and "Hide columns (" not in h, re.findall(r"PC_HIDE=[^;]*", h))
t = pdf_txt()
ck("PDF after approval: Int. Qty and Contract amt printed (42,900.00 / 21,500.00)", "Int. Qty" in t and "Contract amt" in t and "42,900.00" in t and "21,500.00" in t, t[:2500])
ck("... but Unit, Rate, Measured and the amounts are there (195 x 150 = 29,250.00)", re.search(r"M3\s+[\d,.]+\s+150\.00", t) is not None and "29,250.00" in t, t[:3000])
# chosen on the preview: show them again, leave Remarks and Rate off instead; Appendix B's Retention off
sv = c.post(f"/export/est/pc/{pc}/cols?token={tok()}", json={"hide": {"A": [6, 14], "B": [7], "X": [1], "C": [99]}})
ck("the choice is saved on the certificate (unknown table / column ignored)", sv.status_code == 200 and sv.json()["hide"] == {"A": [6, 14], "B": [7], "C": []}, sv.text)
t = pdf_txt()
ck("PDF follows the choice: Int. Qty and Contract amt back, Rate gone", "Int. Qty" in t and "42,900.00" in t and not re.search(r"\bRate\b", t.split("Appendix - A")[1].split("Appendix - B")[0]), t[:2000])
ck("... Appendix B without Retention", "Retention" not in t.split("Appendix - B")[1][:600], t.split("Appendix - B")[1][:600] if "Appendix - B" in t else t[-1500:])
h = prev()
ck("preview shows the saved choice, 3 hidden", 'window.PC_HIDE={"A": [6, 14], "B": [7], "C": []}' in h and "Hide columns (3 hidden)" in h)
sv = c.post(f"/export/est/pc/{pc}/cols?token={tok()}", json={"hide": {}})
ck("everything shown again", "Int. Qty" in pdf_txt() and "Hide columns<" in prev())
print("ALL PASS" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)

"""Export Excel = the PDF (9 Nov 2026): one worksheet per printed sheet in the PDF's order, every figure the app's to
the fils, every formula a real formula with the app's figure saved, and LibreOffice working the file out again gets
the same figures; the export changes nothing in the bill.
    for g in 913 914; do python3 tests/make_ipa_like_$g.py /tmp/claude-0/bills/$g-like.xlsx; done; python3 tests/make_ipa_like_915_div.py /tmp/claude-0/bills/915-div.xlsx
    cp /tmp/claude-0/bn.db /tmp/claude-0/rt/xe.db && cd app && DATABASE_URL=sqlite:////tmp/claude-0/rt/xe.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/bill_excel_export_test.py
"""
import os, sys, re, io, json, zipfile, shutil, subprocess, tempfile, warnings
warnings.filterwarnings("ignore"); sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main as M, est_bills as EB, est_bills_engine as BE, est_bills_render as BR, est_bills_xlsx as BX
from database import SessionLocal
c = TestClient(M.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:500]}")); ok or fails.append(n)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
DL = lambda: c.post("/auth/download-token", headers=H).json()["token"]
pid = c.get("/store/est/meta", headers=H).json()["projects"][0]["id"]
LO_PROFILE = "/tmp/claude-0/lo"
os.makedirs(LO_PROFILE + "/user", exist_ok=True)
open(LO_PROFILE + "/user/registrymodifications.xcu", "w").write('<?xml version="1.0" encoding="UTF-8"?><oor:items xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><item oor:path="/org.openoffice.Office.Calc/Formula/Load"><prop oor:name="OOXMLRecalcMode" oor:op="fuse"><value>0</value></prop></item></oor:items>')

def lo_recalc(data):
    td = tempfile.mkdtemp(); src = os.path.join(td, "in.xlsx"); open(src, "wb").write(data); od = os.path.join(td, "o")
    subprocess.run([BE._soffice(), f"-env:UserInstallation=file://{LO_PROFILE}", "--headless", "--convert-to", "xlsx", "--outdir", od, src], capture_output=True, timeout=300)
    out = open(os.path.join(od, "in.xlsx"), "rb").read(); shutil.rmtree(td); return out

def formula_figures(data):
    """{(sheet, A1): (has formula, saved figure)}"""
    out = {}
    for nm, vis, cells in BX._read_back(data):
        pass
    z = zipfile.ZipFile(io.BytesIO(data))
    wbx = z.read("xl/workbook.xml").decode(); rels = z.read("xl/_rels/workbook.xml.rels").decode()
    tgt = {re.search(r'Id="([^"]+)"', a).group(1): re.search(r'Target="([^"]+)"', a).group(1) for a in re.findall(r"<Relationship\b([^>]*)/>", rels)}
    for m in re.finditer(r"<sheet\b([^>]*)/>", wbx):
        a = m.group(1); nm = BE._unesc(re.search(r'name="([^"]*)"', a).group(1)); p = tgt[re.search(r'r:id="([^"]+)"', a).group(1)].lstrip("/")
        p = p if p.startswith("xl/") else "xl/" + p
        for cm in re.finditer(r"<c\b([^>]*?)(?:/>|>(.*?)</c>)", z.read(p).decode(), re.S):
            body = cm.group(2) or ""
            if "<f" not in body: continue
            ref = re.search(r'\br="([A-Z]+\d+)"', cm.group(1)).group(1)
            t = (re.search(r'\bt="([^"]+)"', cm.group(1)) or [None, "n"])[1]
            v = re.search(r"<v>(.*?)</v>", body, re.S)
            out[(nm, ref)] = (float(v.group(1)) if v and t == "n" else (BE._unesc(v.group(1)) if v else None))
    return out

def run(tag, bid):
    db = SessionLocal(); b = db.get(EB.EstBill, bid); before = (b.inputs, b.total_due, b.signs, str(b.updated_at)); db.close()
    r = c.get(f"/export/est/ipa/{bid}?token={DL()}&format=excel")
    ck(f"{tag}: Excel downloads", r.status_code == 200 and r.content[:2] == b"PK", r.text[:300])
    if r.status_code != 200: return
    cd = r.headers.get("content-disposition", "")
    ck(f"{tag}: named '<project> - Interim Bill <no> - DD-MM-YYYY.xlsx'", re.search(r"filename\*=UTF-8''[\w%.-]+%20-%20Interim%20Bill%20[\w%-]+%20-%20\d\d-\d\d-\d{4}\.xlsx", cd), cd)
    db = SessionLocal(); b = db.get(EB.EstBill, bid)
    ck(f"{tag}: the export changed nothing in the bill", before == (b.inputs, b.total_due, b.signs, str(b.updated_at)))
    fmt = db.get(EB.EstBillFormat, b.format_id); inputs = EB._inputs(b); model = EB._bill_model(fmt, inputs); values = BE.calculate(model, inputs)
    db.close()
    back = BX._read_back(r.content)
    printed = [s["name"] for s in BR.printed_sheets(model)]
    ck(f"{tag}: one worksheet per PDF sheet, same order", [n for n, v, _ in back if v] == printed, ([n for n, v, _ in back if v], printed))
    # every figure the app's, stored whole (not rounded)
    cells = {n: cl for n, v, cl in back}
    miss = []
    nform_app = nform_x = 0
    for s in BR.printed_sheets(model):
        typed = {k for k in (inputs.get(s["name"]) or {}) if not k.startswith("_")}
        for k, cell in s["cells"].items():
            if cell.get("f") and k not in typed:
                nform_app += 1
                if "f" in (cells[s["name"]].get(k) or {}): nform_x += 1
                else: miss.append(f"{s['name']} {k} ={cell['f']}")
    ck(f"{tag}: every formula of the bill is a formula in Excel ({nform_x}/{nform_app})", not miss, miss[:5])
    saved = formula_figures(r.content)
    wrong = []
    for (sh, ref), v in saved.items():
        rr = int(re.sub(r"[A-Z]", "", ref)); cc = BX.get_column_letter and __import__("openpyxl").utils.column_index_from_string(re.sub(r"\d", "", ref))
        app = values.get(sh, {}).get(f"{rr},{cc}")
        if isinstance(app, (int, float)) and not isinstance(app, bool) and (not isinstance(v, float) or abs(v - app) > 1e-9):
            wrong.append((sh, ref, v, app))
    ck(f"{tag}: the saved figure of every formula is the app's, unrounded", not wrong, wrong[:5])
    # LibreOffice works the file out again: the same figures
    after = formula_figures(lo_recalc(r.content))
    diff = [(k, v, after.get(k)) for k, v in saved.items() if isinstance(v, float) and (not isinstance(after.get(k), float) or abs(after[k] - v) > 0.005)]
    ck(f"{tag}: recalculated by LibreOffice - every one of {len(saved)} formulas gives the app's figure", not diff, diff[:6])
    return r.content

# the real 914 MEP format already in the copy? else the generated workbooks
for tag, path in (("913-like", "/tmp/claude-0/bills/913-like.xlsx"), ("914-like", "/tmp/claude-0/bills/914-like.xlsx"), ("915 divisions", "/tmp/claude-0/bills/915-div.xlsx")):
    if not os.path.exists(path):
        print("skip", tag); continue
    r = c.post("/store/est/ipa/format", headers=H, data={"project_id": str(pid)}, files={"file": (os.path.basename(path), open(path, "rb").read(), "application/octet-stream")})
    if r.status_code != 200:
        print("upload", tag, r.status_code, r.text[:200]); continue
    nb = c.post("/store/est/ipa/new", headers=H, json={"project_id": pid, "format_id": r.json()["id"]}).json()
    bid = nb["id"]
    b0 = c.get(f"/store/est/ipa/bill/{bid}", headers=H).json()
    # some work done this month, so the totals move
    for t in b0.get("progress") or []:
        ls = [l for l in t["lines"] if l.get("tot_key")][:3]
        if ls:
            c.put(f"/store/est/ipa/bill/{bid}", headers=H, json={"set": {t["sheet"]: {l["tot_key"]: 0.37 for l in ls}}})
    if tag == "914-like":                                  # lines added, a formula typed, a page copied, bold, a hidden row
        D, C = "Division 03-Concrete Works", "APP C"
        r1 = c.post(f"/store/est/ipa/bill/{bid}/line", headers=H, json={"sheet": D, "after": 12, "values": {"item": "3.2.2.3", "desc": "Additional lintel beams", "unit": "M3", "c5": 4, "c6": 2000}})
        ln = next((l for l in next(t for t in r1.json()["progress"] if t["sheet"] == D)["lines"] if l["r"] == 13), None)
        c.put(f"/store/est/ipa/bill/{bid}", headers=H, json={"set": {D: {ln["tot_key"]: 0.5569}}})
        r2 = c.post(f"/store/est/ipa/bill/{bid}/line", headers=H, json={"sheet": C, "after": 10, "values": {"item": "V07", "desc": "Extra skylight", "amount": "=12000*1.0"}})
        r3 = c.post(f"/store/est/ipa/bill/{bid}/pages", headers=H, json={"from": D, "name": "Division 03 (2)"})
        c.post(f"/store/est/ipa/bill/{bid}/fmt", headers=H, json={"sheet": D, "cells": [[9, 3]], "set": {"b": True}})
        print("  added:", r1.status_code, r2.status_code, r3.status_code)
    run(tag, bid)
if os.path.exists("/tmp/claude-0/bills/914 MEP IPA02 - R2.xls"):                 # the real 914 MEP bill (.xls)
    r = c.post("/store/est/ipa/format", headers=H, data={"project_id": str(pid)}, files={"file": ("914 MEP IPA02 - R2.xls", open("/tmp/claude-0/bills/914 MEP IPA02 - R2.xls", "rb").read(), "application/octet-stream")})
    print("  914 MEP upload", r.status_code, r.text[:150] if r.status_code != 200 else "")
    if r.status_code == 200:
        bid = c.post("/store/est/ipa/new", headers=H, json={"project_id": pid, "format_id": r.json()["id"]}).json()["id"]
        run("914 MEP (real)", bid)
if os.environ.get("BIDS"):
    for bid in [int(x) for x in os.environ["BIDS"].split(",")]:
        run(f"bill {bid}", bid)
print("FAILS:", fails or "none")

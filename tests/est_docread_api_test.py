"""Estimation uploads read on the server from the file itself (app/est_fileread.py + app/docread), through the API:
previous bills / PCs and the client-PC / project forms (/store/est/read/<kind>, multipart), a big file in pieces, the
variation import (PDF log, the team's own Excel log, save from the confirm screen's lines, nothing added twice),
the agreement header with the schedule check, and the server without its PDF / OCR packages (501 + a clear message,
Excel still read; the browser's text still read).
    cp /tmp/claude-0/full.db /tmp/edr.db && cd app && DATABASE_URL=sqlite:////tmp/edr.db INFINIA_NO_SCHED=1 python3 ../tests/est_docread_api_test.py
"""
import json, os, subprocess, sys, tempfile
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main
import est_fileread as F

HERE = os.path.dirname(os.path.abspath(__file__))
c = TestClient(main.app); c.__enter__()
fails = []


def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:500]}"))
    if not ok:
        fails.append(n)


H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
D = os.environ.get("CORPUS") or os.path.join(tempfile.gettempdir(), "edr_corpus")
if not os.path.exists(os.path.join(D, "truth.json")):
    subprocess.run([sys.executable, os.path.join(HERE, "docread", "synth.py"), D, "--n", "4", "--seed", "2026", "--scans", "0.5", "--vo", "3", "--contracts", "1"],
                   check=True, capture_output=True)
T = {x["file"]: x for x in json.load(open(os.path.join(D, "truth.json")))}
meta = c.get("/store/est/meta", headers=H).json()
P = next(p["id"] for p in meta["projects"] if p["code"] == "902")


def up(url, fname, **form):
    with open(os.path.join(D, fname), "rb") as fh:
        return c.post(url, files={"file": (fname, fh.read())}, data={k: (v if isinstance(v, str) else json.dumps(v)) for k, v in form.items()}, headers=H)


def same(f, want):
    bad = {k: (f.get(k), v) for k, v in want.items() if not (abs((f.get(k) or 0) - v) < 0.006 if isinstance(v, float) else f.get(k) == v)}
    return not bad, bad


print("DOCREAD_PARALLEL default:", os.environ.get("DOCREAD_PARALLEL"))
ck("scanned pages one at a time by default (1 GB server)", os.environ.get("DOCREAD_PARALLEL") == "1")

# ---- bills and PCs from the file ---------------------------------------------------------------------------
for fname, kind in (("ipa_00_single.pdf", "ipa"), ("ipa_00_single.xlsx", "ipa"), ("ipa_01_three_scan.pdf", "ipa"), ("subpc_01_three.xlsx", "subpc"),
                    ("subpc_02_kv_scan.pdf", "subpc"), ("ipa_02_kv.pdf", "clientpc")):
    r = up(f"/store/est/read/{kind}", fname, subs=[])
    ck(f"{fname} ({kind}): read from the file", r.status_code == 200, r.text[:300])
    if r.status_code != 200:
        continue
    j = r.json()
    want = {k: v for k, v in T[fname]["truth"].items() if k in ("seq", "claimed_cum", "ret_cum", "adv_rec_cum", "vat", "total", "work_cum", "var_cum", "prev_cert", "net")}
    ok, bad = same(j["fields"], want)
    ck(f"...every figure as on the document", ok, bad)
    ck("...each field with a status and a place", all(d.get("status") in ("ok", "check", "derived") for d in j["detail"].values()) and any(d.get("where") for d in j["detail"].values()), j["detail"])
    ck("...the sums all agree", j["sums"] and all(s["ok"] for s in j["sums"]), [s for s in j["sums"] if not s["ok"]])
    ck("...pages for the preview", j.get("pages") and (j["pages"][0]["w"] > 0 or j["pages"][0]["kind"] == "sheet"), j.get("pages"))
    ck("...read from the file on the server", j.get("source") == "file")

# a big file in pieces (the web server takes about 1 MB a request)
data = open(os.path.join(D, "ipa_00_single.pdf"), "rb").read()
uid = "ab" * 10
half = len(data) // 2
for i, part in enumerate((data[:half], data[half:])):
    c.post("/store/est/ipa/format/part", files={"file": ("part", part)}, data={"upload_id": uid, "index": str(i)}, headers=H)
r = c.post("/store/est/read/ipa", data={"upload_id": uid, "parts": "2", "filename": "ipa_00_single.pdf", "subs": "[]"}, headers=H)
ck("a file sent in pieces is read the same", r.status_code == 200 and r.json()["fields"].get("claimed_cum") == T["ipa_00_single.pdf"]["truth"]["claimed_cum"], r.text[:200])

# the browser's text still read (the fallback), with statuses
from docread.legacy import browser_lines
lines = browser_lines(open(os.path.join(D, "ipa_00_single.pdf"), "rb").read(), "ipa_00_single.pdf")
r = c.post("/store/est/read/ipa", json={"lines": lines, "subs": []}, headers=H)
ck("the browser's text of a bill: the same figures, with statuses", r.status_code == 200 and same(r.json()["fields"], {"claimed_cum": T["ipa_00_single.pdf"]["truth"]["claimed_cum"]})[0] and r.json().get("detail"), r.text[:300])
r = c.post("/store/est/read/tender", json={"lines": lines}, headers=H)
ck("the other forms still read the browser's text", r.status_code == 200 and "fields" in r.json(), r.text[:200])

# ---- the project form: a letter of award ------------------------------------------------------------------
r = up("/store/est/read/project", "contract_00.pdf")
t = T["contract_00.pdf"]["truth"]
ck("letter of award (project form) read from the file", r.status_code == 200 and same(r.json()["fields"], {k: t[k] for k in ("contract_value", "ret_pct", "start_date")})[0], r.text[:400])
ck("...its amount in words agrees (words over two lines)", r.status_code == 200 and all(s["ok"] for s in r.json()["sums"]), r.json().get("sums"))

# ---- variations ---------------------------------------------------------------------------------------------
before = len(c.get(f"/store/est/projects/{P}", headers=H).json()["variations"])
r = up(f"/store/est/projects/{P}/variations/import", "vo_01.pdf")
j = r.json()
truth = T["vo_01.pdf"]["truth"]
ck("variation log PDF: every line read", r.status_code == 200 and j["rows"] == len(truth), r.text[:300])
ck("...with the lines to save back, a place for each, the column sums", len(j.get("rows_read") or []) == len(truth) and len(j.get("detail") or []) == len(truth) and j.get("sums"), j.get("sums"))
r2 = c.post(f"/store/est/projects/{P}/variations/import", data={"rows": json.dumps(j["rows_read"]), "save": "1", "contract_id": ""}, headers=H)
b = c.get(f"/store/est/projects/{P}", headers=H).json()
ck("...saved from the confirm screen's lines (the file not sent again)", r2.status_code == 200 and r2.json().get("added") == len(truth) and len(b["variations"]) == before + len(truth), r2.text[:300])
added = b["variations"][before:]
ck("...amounts as on the log", abs(sum(v["submitted_amount"] for v in added) - sum(x["submitted_amount"] for x in truth)) < 0.01)
r3 = c.post(f"/store/est/projects/{P}/variations/import", data={"rows": json.dumps(j["rows_read"]), "save": "1", "contract_id": ""}, headers=H)
ck("...brought in again: nothing added twice", r3.status_code == 200 and r3.json().get("added") == 0 and r3.json().get("skipped") == len(truth), r3.text[:200])
r = up(f"/store/est/projects/{P}/variations/import", "teamvo_909.xlsx")
ck("the team's own Excel log: read by its own reader (OHP sheet kept)", r.status_code == 200 and r.json().get("engine") == "team log" and r.json()["rows"] == len(T["teamvo_909.xlsx"]["truth"]), (r.json().get("engine"), r.json().get("rows"), len(T["teamvo_909.xlsx"]["truth"])))
r = c.post(f"/store/est/projects/{P}/variations/import", data={"rows": json.dumps([{"title": "x", "submitted_amount": "abc"}]), "save": "1"}, headers=H)
ck("bad lines sent back are refused", r.status_code == 400, r.text[:200])

# ---- the agreement: header + schedule check -----------------------------------------------------------------
r = up("/store/est/subs/agreement/read", "contract_00.docx", trades=[])
j = r.json()
ck("agreement read from the file: value, %, the sums list", r.status_code == 200 and j["fields"].get("value") == t["contract_value"] and j["fields"].get("ret_pct") == t["ret_pct"] and isinstance(j.get("sums"), list) and isinstance(j.get("checks"), dict), r.text[:400])
ck("...each field with a status", all(d.get("status") in ("ok", "check", "derived") for d in j["detail"].values()), j.get("detail"))
r = c.post("/store/est/subs/agreement/read", json={"lines": browser_lines(open(os.path.join(D, "contract_00.pdf"), "rb").read(), "c.pdf"), "trades": []}, headers=H)
ck("agreement from the browser's text still read", r.status_code == 200 and r.json()["fields"].get("value") == t["contract_value"], r.text[:300])

# ---- a server without the PDF / OCR packages ----------------------------------------------------------------
real = F.caps()
F._CAPS = dict(real, ocr=False)
r = up("/store/est/read/ipa", "ipa_01_three_scan.pdf")
ck("no OCR package: a scan answers 501 'scanned files need the OCR package installed'", r.status_code == 501 and "OCR package installed" in r.json()["detail"], r.text[:200])
r = up("/store/est/read/ipa", "ipa_00_single.xlsx")
ck("...Excel still read", r.status_code == 200 and r.json()["fields"].get("claimed_cum") == T["ipa_00_single.xlsx"]["truth"]["claimed_cum"], r.text[:200])
r = up("/store/est/read/ipa", "ipa_00_single.pdf")
ck("...a typed PDF still read (no OCR needed)", r.status_code == 200, r.text[:200])
r = up(f"/store/est/projects/{P}/variations/import", "vo_00_scan.pdf")
ck("...a scanned variation log: 501 (the browser reads it instead)", r.status_code == 501, r.text[:200])
F._CAPS = dict(real, pdf=False, ocr=False)
r = up("/store/est/read/ipa", "ipa_00_single.pdf")
ck("no PDF package: a PDF answers 501 with the reason", r.status_code == 501 and "pdfplumber" in r.json()["detail"], r.text[:200])
r = up("/store/est/subs/agreement/read", "contract_00.docx", trades=[])
ck("...Word still read", r.status_code == 200, r.text[:200])
F._CAPS = None

print(f"\n{len(fails)} FAILED" if fails else "\nALL PASS")
sys.exit(1 if fails else 0)

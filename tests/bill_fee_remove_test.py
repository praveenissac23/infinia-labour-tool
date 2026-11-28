"""Authority fees (APP B): the x removes the line, empty lines never print, SN is the app's (28/11/2026).

Reported: the x on an Authority fees line did not delete it - it only emptied the cells, and the empty rows (the
format's spare rows above the sub-total and the empty line the app puts in for a new bill) printed on APP B between
"DM inspection fee" and "Sub - Total from Current Bill". Checked here the way the office will (Anoop's a-e):
 a) IPA 11: one fee + 2 empty lines, x on both empty lines: only the fee is left
 b) opened again (F5): still only the fee
 c) Sheets / preview: "IPA 11", "1 DM inspection fee ... 260.00", "Sub - Total from Current Bill 260.00", no blank row
 d) 3 filled lines, the 2nd removed: SN 1, 2; sub-total, cover and total due right; Undo brings it back
 e) PDF and Excel match the screen
and the same on Payments received (a line removed: off the summary, numbers closed up, not printed blank).
    python3 tests/make_ipa_fee_spares.py /tmp/claude-0/bills/fee-spares.xlsx
    python3 tests/run_all.py bill_fee_remove
"""
import os, sys, io, re, subprocess, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.getcwd())
X = "/tmp/claude-0/bills/fee-spares.xlsx"
if not os.path.exists(X):
    os.makedirs(os.path.dirname(X), exist_ok=True)
    subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "make_ipa_fee_spares.py"), X], check=True, capture_output=True)
import openpyxl
import database, models, auth
models.Base.metadata.create_all(database.engine)
from fastapi.testclient import TestClient
import main as M
import est_bills as EB, est_bills_engine as BE
db = database.SessionLocal()
if not db.query(models.User).filter_by(username="admin").first():
    db.add(models.User(username="admin", hashed_password=auth.hash_password("changeme123"), full_name="Administrator", role="admin")); db.commit()
c = TestClient(M.app); c.__enter__()
FAIL = []


def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:600]}"))
    if not ok:
        FAIL.append(n)


H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
meta = c.get("/store/est/meta", headers=H).json()
if not meta.get("projects"):
    c.post("/store/est/projects", headers=H, json={"code": "913", "name": "Asif Akbar villa", "client": "Asif Akbar"})
    meta = c.get("/store/est/meta", headers=H).json()
pid = meta["projects"][-1]["id"]
r = c.post("/store/est/ipa/format", headers=H, data={"project_id": str(pid)}, files={"file": ("fee-spares.xlsx", open(X, "rb").read(), "application/octet-stream")})
ck("the workbook is taken", r.status_code == 200, r.text)
fid = r.json()["id"]
bid = c.post("/store/est/ipa/new", headers=H, json={"project_id": pid, "format_id": fid}).json()["id"]
U = f"/store/est/ipa/bill/{bid}"
tok = lambda: c.post("/auth/download-token", headers=H).json()["token"]


def fees():
    return c.get(U, headers=H).json()["fees"][0]


fe = fees()
SH = fe["sheet"]
ck("the new bill: IPA 11 heading and an empty line ready; the IPA 10 heading with no fee not shown as an earlier group",
   fe["rows"][0]["head"] and fe["rows"][0]["desc"]["value"] == "IPA 11" and not any(e.get("desc") == "IPA 10" for e in fe["earlier"]),
   ([(x["r"], x["desc"]["value"]) for x in fe["rows"]], fe["earlier"]))
ln = next(x for x in fe["rows"] if not x["head"])
r = c.put(U, headers=H, json={"set": {SH: {ln["desc"]["key"]: "DM inspection fee", ln["ref"]["key"]: "WIFBP2044806 dtd. 23/11/2026", ln["amount"]["key"]: 260}}})
fe = r.json()["fees"][0]
blank = [x for x in fe["rows"] if not x["head"] and not (x["desc"]["value"] or x["ref"]["value"] or x["amount"]["value"])]
if len(blank) < 2:                                   # as Anoop had it: two empty lines under the fee
    for _ in range(2 - len(blank)):
        last = [x for x in fe["rows"] if not x["head"]][-1]
        fe = c.post(f"{U}/rows", headers=H, json={"sheet": SH, "at": last["r"] + 1, "n": 1, "like": last["r"]}).json()["fees"][0]
    blank = [x for x in fe["rows"] if not x["head"] and not (x["desc"]["value"] or x["ref"]["value"] or x["amount"]["value"])]
ck("set-up: IPA 11, the DM fee (SN 1) and 2 empty lines", len(blank) == 2 and fe["total"] == 260 and next(x for x in fe["rows"] if x["desc"]["value"] == "DM inspection fee")["sn"]["value"] == 1,
   [(x["r"], x["sn"]["value"], x["desc"]["value"], x["amount"]["value"]) for x in fe["rows"]])

# a) x on both empty lines
for x in blank:
    rr = c.post(f"{U}/fee/remove", headers=H, json={"sheet": SH, "r": x["r"]})
    ck(f"a) x on empty line (row {x['r']}): removed", rr.status_code == 200, rr.text[:300])
fe = rr.json()["fees"][0]
ck("a) only the DM fee is left under IPA 11", [x["desc"]["value"] for x in fe["rows"]] == ["IPA 11", "DM inspection fee"] and fe["total"] == 260,
   [(x["r"], x["desc"]["value"]) for x in fe["rows"]])
# b) opened again
fe = fees()
ck("b) after a refresh: still only the DM fee", [x["desc"]["value"] for x in fe["rows"]] == ["IPA 11", "DM inspection fee"], [(x["r"], x["desc"]["value"]) for x in fe["rows"]])


def printed_appb(fmt):
    """APP B as printed: the visible rows from the heading of the table to the sub-total, as text."""
    if fmt == "excel":
        wb = openpyxl.load_workbook(io.BytesIO(c.get(f"/export/est/ipa/{bid}?token={tok()}&format=excel").content))
        ws = wb[SH]
        out = []
        for rr in range(5, ws.max_row + 1):
            if ws.row_dimensions[rr].hidden:
                continue
            out.append(tuple(ws.cell(rr, cc).value for cc in range(1, 5)))
            if "sub - total" in str(ws.cell(rr, 2).value or "").lower():
                break
        return out
    i = next(s["i"] for s in c.get(U, headers=H).json()["sheets"] if s["name"] == SH)
    html = c.get(f"{U}/sheet/{i}", headers=H).json()["html"] if fmt == "sheet" else c.get(f"/export/est/ipa/{bid}?token={tok()}&format=preview").text
    if fmt != "sheet":
        html = html[html.find("APPENDIX - B"):]
    trs = re.findall(r"<tr\b[^>]*>(.*?)</tr>", html, re.S)
    out = []
    for t in trs:
        cells = [re.sub(r"<[^>]+>", "", x).replace("&nbsp;", " ").strip() for x in re.findall(r"<td\b[^>]*>(.*?)</td>", t, re.S)]
        cells = [x for x in cells if x]
        if out or any("IPA 11" in x for x in cells):
            out.append(cells)
        if any("sub - total" in x.lower() for x in cells):
            break
    return out


# c) the Sheets view and the preview
for fmt in ("sheet", "preview"):
    rows = printed_appb(fmt)
    ok = len(rows) == 3 and "IPA 11" in rows[0] and rows[1][:2] == ["1", "DM inspection fee"] and "260.00" in rows[1] and "260.00" in rows[2] and "Sub - Total from Current Bill" in rows[2]
    ck(f"c) {fmt}: IPA 11 / 1 DM inspection fee 260.00 / Sub - Total 260.00, no blank row between", ok, rows)
xr = printed_appb("excel")
ck("e) Excel: the same three rows, nothing blank between", len(xr) == 3 and xr[0][1] == "IPA 11" and xr[1][:2] == (1, "DM inspection fee") and xr[2][1] == "Sub - Total from Current Bill"
   and not any(x[1] in (None, "") for x in xr), xr)
pdf = c.get(f"/export/est/ipa/{bid}?token={tok()}&format=pdf")
ck("e) PDF made", pdf.status_code == 200 and pdf.content[:4] == b"%PDF", pdf.status_code)

# d) three filled lines, the 2nd removed
fe = fees()
last = fe["rows"][-1]
for d, ref, a in (("DEWA meter fee", "DEWA/M/5521", 410.25), ("Trakhees permit renewal for the boundary wall and gate", "TRK-2026-7781", 1150)):
    fe = c.post(f"{U}/rows", headers=H, json={"sheet": SH, "at": last["r"] + 1, "n": 1, "like": last["r"]}).json()["fees"][0]
    nr = next(x for x in fe["rows"] if x["r"] == last["r"] + 1)
    fe = c.put(U, headers=H, json={"set": {SH: {nr["desc"]["key"]: d, nr["ref"]["key"]: ref, nr["amount"]["key"]: a}}}).json()["fees"][0]
    last = next(x for x in fe["rows"] if x["r"] == nr["r"])
lines = [x for x in fe["rows"] if not x["head"]]
ck("d) 3 lines typed: SN 1, 2, 3 and sub-total 1,820.25", [x["sn"]["value"] for x in lines] == [1, 2, 3] and round(fe["total"], 2) == 1820.25,
   [(x["sn"]["value"], x["desc"]["value"], x["amount"]["value"]) for x in lines])
db.expire_all()
_b = db.get(EB.EstBill, bid); _f = db.get(EB.EstBillFormat, _b.format_id); _i = EB._inputs(_b)
due_before = BE.calculate(EB._bill_model(_f, _i), _i).get("IPA", {}).get("10,2")
rr = c.post(f"{U}/fee/remove", headers=H, json={"sheet": SH, "r": lines[1]["r"]})
b = rr.json(); fe = b["fees"][0]
lines = [x for x in fe["rows"] if not x["head"]]
db.expire_all()
_b = db.get(EB.EstBill, bid); _f = db.get(EB.EstBillFormat, _b.format_id); _i = EB._inputs(_b)
_v = BE.calculate(EB._bill_model(_f, _i), _i)
cov = _v.get("IPA", {}).get("8,2")                  # "Add: Payment paid to Authorities in Current Bill (Appendix B)"
due = _v.get("IPA", {}).get("10,2")
ck("d) the 2nd removed: SN 1, 2; sub-total 1,410.00; the cover line follows",
   [x["sn"]["value"] for x in lines] == [1, 2] and [x["desc"]["value"] for x in lines] == ["DM inspection fee", "Trakhees permit renewal for the boundary wall and gate"]
   and round(fe["total"], 2) == 1410 and isinstance(cov, (int, float)) and round(cov, 2) == 1410, ([(x["sn"]["value"], x["desc"]["value"]) for x in lines], fe["total"], cov))
ck("d) total due this bill includes the 1,410.00 (and moves by exactly the 410.25 removed)", isinstance(due, (int, float)) and round(due_before - due, 2) == 410.25, (due_before, due))
xr = printed_appb("excel")
ck("e) Excel after the delete: IPA 11, 1 DM, 2 Trakhees, sub-total - nothing blank", [x[0] for x in xr[1:3]] == [1, 2] and len(xr) == 4 and "Sub - Total" in str(xr[3][1]), xr)
rows = printed_appb("preview")
ck("e) preview after the delete: the same", len(rows) == 4 and rows[1][0] == "1" and rows[2][0] == "2" and "1,410.00" in rows[3], rows)
u = c.post(f"{U}/undo", headers=H, json={})
fe = u.json()["fees"][0]
lines = [x for x in fe["rows"] if not x["head"]]
ck("Undo: the line is back (SN 1, 2, 3, 1,820.25)", u.status_code == 200 and [x["sn"]["value"] for x in lines] == [1, 2, 3] and round(fe["total"], 2) == 1820.25,
   (u.status_code, u.text[:200] if u.status_code != 200 else [(x["sn"]["value"], x["desc"]["value"]) for x in lines]))
c.post(f"{U}/undo", headers=H, json={"redo": True})
fe = fees()
ck("Redo, then a refresh: removed again, 2 lines", len([x for x in fe["rows"] if not x["head"]]) == 2 and round(fe["total"], 2) == 1410)

# an empty line left (not x'd) never prints; opened again it is taken off
last = fe["rows"][-1]
c.post(f"{U}/rows", headers=H, json={"sheet": SH, "at": last["r"] + 1, "n": 1, "like": last["r"]})
fe = c.get(U, headers=H).json()["fees"][0]
xr = printed_appb("excel")
ck("an empty line added and left: not printed, and gone when the bill is opened again", len(xr) == 4 and len(fe["rows"]) == 3, (xr, [(x["r"], x["desc"]["value"]) for x in fe["rows"]]))

# a carried line cannot be taken off here
r = c.post(f"{U}/fee/remove", headers=H, json={"sheet": SH, "r": 999})
ck("a row outside the table: refused with a plain message", r.status_code == 400 and "refresh" in r.json()["detail"], r.text)

# Payments received: a line removed - off the summary and out of the total, numbers closed up, not printed blank
bb = c.get(U, headers=H).json()
p = bb["payments"][0]
rows_ = [x for x in p["rows"] if x["desc"]["value"]]
victim = next(x for x in rows_ if x["desc"]["value"] == "Payment Application No 7")
before = p["total"]
st = {victim[k]["key"]: "" for k in p["cols"] if victim.get(k)}
r = c.put(U, headers=H, json={"set": {p["sheet"]: st}, "why": {"label": "Line removed", "page": "pay"}})
p2 = r.json()["payments"][0]
ck("Payments: the line comes off and out of the total", r.status_code == 200 and round(before - p2["total"], 2) == 30000, (before, p2["total"]))
wb = openpyxl.load_workbook(io.BytesIO(c.get(f"/export/est/ipa/{bid}?token={tok()}&format=excel").content))
ws = wb[p["sheet"]]
vis = [(rr, ws.cell(rr, 1).value, ws.cell(rr, 2).value) for rr in range(5, 23) if not ws.row_dimensions[rr].hidden]
ck("Payments: Excel prints no blank line where it was, and the numbers close up", all(v[2] for v in vis) and victim["r"] not in [v[0] for v in vis]
   and [v[1] for v in vis if v[1] not in (None, "")] == list(range(1, len([v for v in vis if v[1] not in (None, "")]) + 1)), vis)

# a bill saved before the change (no "_blank" stored): prints without its empty lines too
bl = db.get(EB.EstBill, bid)
db.refresh(bl)
inp = EB._inputs(bl)
for v in inp.values():
    if isinstance(v, dict):
        v.pop("_blank", None)
bl.inputs = __import__("json").dumps(inp); db.commit()
xr = printed_appb("excel")
ck("an older bill (nothing worked out yet) prints without the empty lines", len(xr) == 4, xr)

# ---- review findings (28/11/2026) ---------------------------------------------------------------------------
import json as _j
fe = fees()
head_r = fe["rows"][0]["r"]
hidden_earlier = min(r for r in range(5, head_r))          # an earlier bill's line, hidden on this bill
r = c.post(f"{U}/fee/remove", headers=H, json={"sheet": SH, "r": hidden_earlier})
ck("review 2: an earlier bill's hidden line cannot be removed (stale tab)", r.status_code == 400, r.text[:200])
r = c.post(f"{U}/fee/remove", headers=H, json={"sheet": SH, "r": head_r})
ck("review 2: the heading cannot be removed with x", r.status_code == 400, r.text[:200])
# 1: an empty line taken off on opening while another tab still shows it - typed into: it comes back, printed and counted
last = fe["rows"][-1]
c.post(f"{U}/rows", headers=H, json={"sheet": SH, "at": last["r"] + 1, "n": 1, "like": last["r"]})
stale_r = last["r"] + 1
c.get(U, headers=H)                                           # opened elsewhere: the empty line is taken off
db.expire_all()
ck("review 1 set-up: the empty line was taken off on opening", stale_r in _j.loads(db.get(EB.EstBill, bid).inputs)[SH].get("_hide", []))
r = c.put(U, headers=H, json={"set": {SH: {f"{stale_r},2": "DEWA meter", f"{stale_r},4": 410.25}}})
fe = r.json()["fees"][0]
xr = printed_appb("excel")
ck("review 1: typed into it from the stale tab - shown again, printed, and the sub-total matches the printed lines",
   any(x["desc"]["value"] == "DEWA meter" for x in fe["rows"]) and any(x[1] == "DEWA meter" for x in xr)
   and round(sum(x[3] for x in xr if isinstance(x[3], (int, float))), 2) == round(fe["total"], 2), (xr, fe["total"]))
# 5: "Bill of entry" is a line, not a heading
fe = fees(); last = fe["rows"][-1]
fe = c.post(f"{U}/rows", headers=H, json={"sheet": SH, "at": last["r"] + 1, "n": 1, "like": last["r"]}).json()["fees"][0]
nr = next(x for x in fe["rows"] if x["r"] == last["r"] + 1)
fe = c.put(U, headers=H, json={"set": {SH: {nr["desc"]["key"]: "Bill of entry - customs clearance"}}}).json()["fees"][0]
xr = printed_appb("excel")
ck("review 5: 'Bill of entry - customs clearance' typed before its amount is a line (numbered, printed), the heading stays",
   not next(x for x in fe["rows"] if x["r"] == nr["r"])["head"] and any(x[1] == "Bill of entry - customs clearance" and isinstance(x[0], int) for x in xr) and xr[0][1] == "IPA 11", xr)
# 4: "=0" on an empty line is an empty line
fe = c.put(U, headers=H, json={"set": {SH: {nr["desc"]["key"]: None, nr["amount"]["key"]: "=0"}}}).json()["fees"][0]
xr = printed_appb("excel")
ck("review 4: an empty line with =0 in the amount is not printed or numbered", not any(x[1] in (None, "") and x[0] not in (None, "") for x in xr), xr)
# 3: a bill already sent keeps the fee numbers it went out with
db.expire_all(); bl = db.get(EB.EstBill, bid)
inp = _j.loads(bl.inputs); fl = [x for x in fees()["rows"] if not x["head"] and x["desc"]["value"]]
inp[SH][fl[0]["sn"]["key"]] = 4
bl.inputs = _j.dumps(inp); bl.status = "Submitted"; db.commit()
xr = printed_appb("excel")
ck("review 3: a Submitted bill re-downloaded keeps SN 4 as it went out", any(x[0] == 4 and x[1] == fl[0]["desc"]["value"] for x in xr), xr)
bl.status = "Draft"; db.commit()
xr = printed_appb("excel")
ck("...a Draft bill is numbered by the app again", any(x[0] == 1 and x[1] == fl[0]["desc"]["value"] for x in xr), xr)

# A: the roll-over's own heading when the bill number cell is text ("IPA 10" -> "IPA IPA 11"): still a heading
fe = fees(); hd = fe["rows"][0]
fe = c.put(U, headers=H, json={"set": {SH: {hd["desc"]["key"]: "IPA IPA 11"}}}).json()["fees"][0]
xr = printed_appb("excel")
ln_ = [x for x in fe["rows"] if not x["head"]]
ck("review A: 'IPA IPA 11' stays the heading - not numbered, printed as a heading, its lines 1, 2",
   fe["rows"][0]["head"] and xr[0][0] in (None, "") and xr[0][1] == "IPA IPA 11" and [x["sn"]["value"] for x in ln_][:2] == [1, 2], (xr, [(x["r"], x["sn"]["value"], x["desc"]["value"]) for x in fe["rows"]]))
r = c.post(f"{U}/fee/remove", headers=H, json={"sheet": SH, "r": ln_[-1]["r"]})
ck("review A: x works under that heading", r.status_code == 200, r.text[:200])
# B: a bill with no fee heading at all (first bill from a format with an empty APP B): x works, a stale typed line comes back
c.put(U, headers=H, json={"set": {SH: {hd["desc"]["key"]: ""}}})
fe = fees()
ck("review B set-up: no heading on this bill's fees", not any(x["head"] for x in fe["rows"]), [(x["r"], x["desc"]["value"]) for x in fe["rows"]])
ln_ = [x for x in fe["rows"] if x["desc"]["value"] and not x.get("carry")]
r = c.post(f"{U}/fee/remove", headers=H, json={"sheet": SH, "r": ln_[-1]["r"]})
ck("review B: x works on a bill with no heading", r.status_code == 200, r.text[:200])
gone = ln_[-1]["r"]
r = c.put(U, headers=H, json={"set": {SH: {f"{gone},2": "Typed in a stale tab", f"{gone},4": 99}}})
fe = r.json()["fees"][0]
xr = printed_appb_any = None
ck("review B: typing into that taken-off line from a stale tab brings it back (counted and shown)",
   any(x["desc"]["value"] == "Typed in a stale tab" for x in fe["rows"]), [(x["r"], x["desc"]["value"]) for x in fe["rows"]])

c.__exit__(None, None, None)
print("\n" + ("ALL PASS" if not FAIL else f"{len(FAIL)} FAILED: " + "; ".join(FAIL)))
sys.exit(1 if FAIL else 0)

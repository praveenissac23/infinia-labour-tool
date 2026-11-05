"""Internal BOQ workbook -> Overview > BOQ & budget.

    cd app && DATABASE_URL=sqlite:////tmp/boqimp.db INFINIA_NO_SCHED=1 python3 ../tests/est_boqimport_test.py [internal_boq.xlsx ...]

A small workbook in the internal BOQ's layout is made here; any real internal BOQ files given on the
command line are read too and must add up to their own summary sheet to the fils.
"""
import io, os, sys
sys.path.insert(0, os.getcwd())
import openpyxl
from fastapi.testclient import TestClient
import main, estimation as E, est_boqimport as B
from database import SessionLocal, engine

main._add_missing_columns()
E.create_tables(engine)
c = TestClient(main.app); c.__enter__()
fails = []
def ck(name, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  -> {extra}"))
    if not ok: fails.append(name)


def book(extra_line=False, elec_summary=None):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "COVER PAGE"
    p = wb.create_sheet("1.PRELIM")
    for r in [["1. PRELIMINARIES INCLUDING MOBILIZATION"], ["S/NO.", "ITEMS", "LUMPSUM AMOUNT"], [1, "Insurance", 6000],
              [2, "Municipality permit", "Authority payment"], [3, "Allowance for site administrator", None],
              [None, "1 Engineer (part time)", 145000], [None, "1 Foreman", 60000], [4, "Watchman", None], [None, "TOTAL", 211000]]:
        p.append(r)
    s = wb.create_sheet("2.SUBSTR")
    rows = [["2. SUBSTRUCTURE"], ["A. EARTHWORKS"], ["S/NO.", "ITEMS", "CONS. QTY", "IC QTY", "UNIT", "RATE", "LUMPSUM AMOUNT"],
            [1, "Excavation", None, 100, "m3", 30, 3000], [2, "Imported fill", None, 10.5, "m3", 25, 262.5],
            [3, "Others", None, None, "m2", None, 0], [None, "TOTAL", 3262.5], [],
            ["B. DEWATERING WORKS"], ["S/NO.", "ITEMS", "CONS. QTY", "IC QTY", "UNIT", "RATE", "LUMPSUM AMOUNT"],
            [4, "Dewatering", None, 30, "Days", 3200, 96000], [None, "TOTAL", "EXCLUDED"], [],
            ["C. CONCRETE"], ["S/NO.", "ITEMS", "CONS. QTY", "IC QTY", "UNIT", "RATE", "LUMPSUM AMOUNT"],
            [5, "Raft C40", None, 597, "m3", 1050, 626850], [6, "Curved column shutter", None, 5, "m3", "LS", 8000],
            [7, "Pool walls", None, 0, "m3", 1100, "Included in beams"]]
    if extra_line:
        rows.append([8, "Extra item added by the QS", None, 2, "No.", 500, 1000])
    rows += [[None, "TOTAL", 634850], [], ["SUMMARY"], ["A.", "EARTHWORKS", 3262.5], ["B.", "DEWATERING WORKS", "Excluded"],
             ["C.", "CONCRETE", 634850 + (1000 if extra_line else 0)], [None, "SUBSTRUCTURE TOTAL", 0]]
    for r in rows:
        s.append(r)
    j = wb.create_sheet("7. JOINERY")
    for r in [["7. CARPENTRY AND JOINERY"], ["A. DOORS"], ["S/NO.", "ITEM", "SIZE", None, "AREA", "TYPE", "CONS QTY", "IC QTY", "UNIT", "RATE", "AMOUNT"],
              [None, None, "L (m)", "H (m)"], [None, "Supply and fixing of all wooden doors"], [1, "D1", 1.2, 2.2, 2.64, "Single", None, 3, "No.", 2000, 6000]]:
        j.append(r)
    e = wb.create_sheet("10. ELEC.")
    for r in [["10. ELECTRICAL WORKS"], ["S/NO.", "ITEMS", "CONS. QTY", "IC QTY", "UNIT", "RATE", "AMOUNT"], [1, "Builders work", None, 1, "LS", 25000, 25000],
              [2, "OHP", None, None, 0.1, None, None], [None, "ELECTRICAL TOTAL", 25000], [], ["PRICE COMPARISON - ELECTRICAL"],
              ["SL.NO", "Item Description", "Subcon 1"], [None, "Electrical", 175000]]:
        e.append(r)
    m = wb.create_sheet("SUMMARY")
    sub = 3262.5 + 634850 + (1000 if extra_line else 0)
    elec = 25000 if elec_summary is None else elec_summary
    for r in [["TOTAL SUMMARY"], ["S/NO.", "DESCRIPTION", "AMOUNT", "DISCOUNT"], ["01.", "Preliminaries", 211000], ["02.", "Sub structure", sub],
              ["07.", "Carpentry & Joinery", "Phase 02"], ["10.", "Electrical", elec, "Yet to Confirm" if elec_summary else None],
              [None, "TOTAL", 211000 + sub + elec - 100]]:
        m.append(r)
    bio = io.BytesIO(); wb.save(bio); return bio.getvalue()


# ---- reading: only priced lines in the priced scope come in; the rest is listed ----
r = B.read_internal_boq(book())
L = {x["description"]: x for x in r["lines"]}
ck("prelim lump sums come in as 1 LS x amount", L["Insurance"]["qty"] == 1 and L["Insurance"]["unit"] == "LS" and L["Insurance"]["amount"] == 6000)
ck("a line with an amount in words and no money is NOT brought in (counted as unpriced)", "Municipality permit" not in L and r["unpriced"] >= 2, r["unpriced"])
ck("sub-items carry their lead-in line", "Allowance for site administrator - 1 Engineer (part time)" in L and L["Allowance for site administrator - 1 Engineer (part time)"]["amount"] == 145000)
ck("unpriced template rows and OHP / Others left out", "Watchman" not in L and "Others" not in L and not any(d.startswith("OHP") for d in L))
ck("bill named as the SUMMARY has it, section from the heading", L["Excavation"]["bill"] == "02. Sub Structure" and L["Excavation"]["section"] == "A. EARTHWORKS", (L["Excavation"]["bill"], L["Excavation"]["section"]))
ck("decimals kept (10.5 m3 x 25 = 262.50)", L["Imported fill"]["qty"] == 10.5 and L["Imported fill"]["amount"] == 262.5)
ck("a section the sheet's summary excludes is NOT brought in, and is listed", "Dewatering" not in L and any(s["why"] == "Excluded" and s["amount"] == 96000 for b in r["bills"] for s in b["sections_out"]))
ck("a lump sum whose rate is 'LS' keeps its amount", L["Curved column shutter"]["amount"] == 8000 and L["Curved column shutter"]["rate"] == 0)
ck("a bill the summary marks Phase 02 is NOT brought in, and is listed", not any(x["bill"].startswith("07") for x in r["lines"]) and any(x["why"] == "Phase 02" for x in r["skipped"]), r["skipped"])
ck("price comparison tables are not BOQ lines", "Electrical" not in L)
ck("total = summary total, the summary's own discount added as one line", abs(r["total"] - r["summary_total"]) < 0.005 and any(x["description"].startswith("Discount") and x["amount"] == -100 for x in r["lines"]), (r["total"], r["summary_total"]))
ck("every bill tallies with the summary", r["tally_ok"] and all(b["ok"] for b in r["bills"]), [(b["bill"], b["diff"]) for b in r["bills"]])
rk = B.read_internal_boq(book(), keep_unpriced=True, keep_out=True)
Lk = {x["description"]: x for x in rk["lines"]}
ck("asked for: unpriced lines come in at 0 with their words", Lk["Municipality permit"]["amount"] == 0 and Lk["Municipality permit"]["remark"] == "Authority payment")
ck("asked for: left-out section / bill come in, kept aside (not counted)", Lk["Dewatering"]["scope"] == "Excluded" and any(x["scope"] == "Phase 02" for x in rk["lines"]) and abs(rk["total"] - r["total"]) < 0.005)
r2 = B.read_internal_boq(book(extra_line=True))
ck("an extra line added in the workbook comes in", any(x["description"] == "Extra item added by the QS" and x["amount"] == 1000 for x in r2["lines"]))
r3 = B.read_internal_boq(book(elec_summary=650000))
e3 = next(b for b in r3["bills"] if b["bill"].startswith("10"))
ck("a bill whose summary figure differs: the difference is SHOWN, never put in as a line", not any(x["description"].startswith("Difference") for x in r3["lines"]) and e3["diff"] == -625000 and not e3["ok"] and not r3["tally_ok"]
   and any("625,000.00 less" in n for n in r3["notes"]), (e3, r3["notes"]))
# a sheet with no number in its name, between numbered ones, numbered as the summary has it (WS-25 R10)
def book2():
    wb = openpyxl.Workbook(); wb.active.title = "COVER PAGE"
    a = wb.create_sheet("1.PRELIM")
    for r_ in [["1. PRELIMINARIES"], ["S/NO.", "ITEMS", "LUMPSUM AMOUNT"], [1, "Insurance", 4000], [None, "TOTAL", 4000]]: a.append(r_)
    sp = wb.create_sheet("SWIMMING POOL")
    for r_ in [["J. SWIMMING POOL"], ["S/NO.", "ITEMS", "CONS. QTY", "IC QTY", "UNIT", "RATE", "LUMPSUM AMOUNT"], [45, "Excavation", None, 119, "m3", 25, 2975],
               [None, "TOTAL", None, 1, "Item", "LS", "exclude"], [], ["L. POOL UNDERGROUND WATER TANK & BALANCING TANK"],
               ["S/NO.", "ITEMS", "CONS. QTY", "IC QTY", "UNIT", "RATE", "LUMPSUM AMOUNT"], [170, "Excavation", None, 54, "m3", 25, 1350],
               [171, "Backfilling", None, 32, "m3", 20, 640], [None, "TOTAL", 1990], [],
               ["B. PUMP ROOM FOR POOL 4.3m L x 2.2m W", None, None, None, "(From 907 Int.BOQ)"],
               ["S/NO.", "ITEMS", "CONS. QTY", "IC QTY", "UNIT", "RATE", "LUMPSUM AMOUNT"], [22, "Excavation", None, 58, "m3", 25, 1450],
               [None, "TOTAL", None, None, None, None, "exclude"]]: sp.append(r_)
    s3 = wb.create_sheet("3.SUPERSTR")
    for r_ in [["3. SUPERSTRUCTURE"], ["A. REINFORCED CONCRETE"], ["S/NO.", "ITEMS", "CONS. QTY", "IC QTY", "UNIT", "RATE", "LUMPSUM AMOUNT"],
               [1, "Columns", None, 10, "m3", 800, 8000], [None, "TOTAL", 8000], [], [None, "UNDERGROUND WATER TANK"],
               ["S/NO.", "ITEMS", "CONS. QTY", "IC QTY", "UNIT", "RATE", "LUMPSUM AMOUNT"], [1, "RCC Wall", None, 2, "m3", 700, 1400], [None, "TOTAL", 1400]]: s3.append(r_)
    m_ = wb.create_sheet("SUMMARY")
    for r_ in [["TOTAL SUMMARY"], ["S/NO.", "DESCRIPTION", "AMOUNT"], [1, "Preliminaries", 4000], [2, "Swimming pool & holding tank", 1990],
               [3, "Super structure", 9400], [None, "TOTAL", 15390]]: m_.append(r_)
    bio = io.BytesIO(); wb.save(bio); return bio.getvalue()
w = B.read_internal_boq(book2())
bn = {b["bill"]: b for b in w["bills"]}
ck("an unnumbered sheet (SWIMMING POOL) is read, numbered as the summary has it", "02. Swimming Pool & Holding Tank" in bn and bn["02. Swimming Pool & Holding Tank"]["counted"] == 1990 and bn["02. Swimming Pool & Holding Tank"]["ok"], list(bn))
ck("... and the sheet after it ('3.SUPERSTR') is bill 03 Super Structure, tallying", "03. Super Structure" in bn and bn["03. Super Structure"]["ok"], list(bn))
ck("sections marked 'exclude' on their TOTAL row are left out (pool, pump room with a note beside its heading)",
   not any(x["section"].startswith(("J.", "B. PUMP")) for x in w["lines"]) and {s["name"][:7] for s in bn["02. Swimming Pool & Holding Tank"]["sections_out"]} == {"J. SWIM", "B. PUMP"}, bn["02. Swimming Pool & Holding Tank"]["sections_out"])
ck("an unlettered heading is its own section", any(x["section"] == "UNDERGROUND WATER TANK" and x["description"] == "RCC Wall" for x in w["lines"]))
ck("the whole workbook tallies (15,390.00)", w["tally_ok"] and w["total"] == 15390, (w["total"], w["notes"]))
# ---- the real workbooks, if given: every one adds up to its own summary ----
for f in sys.argv[1:]:
    rr = B.read_internal_boq(open(f, "rb").read())
    ck(f"{os.path.basename(f)}: {len(rr['lines'])} lines, {rr['total']:,.2f} = summary {rr['summary_total']:,.2f}, every bill tallies", rr["summary_total"] is not None and abs(rr["total"] - rr["summary_total"]) < 0.015 and rr["tally_ok"], [(b["bill"], b["diff"]) for b in rr["bills"] if not b["ok"]])

# ---- through the app ----
tok = c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]
H = {"Authorization": "Bearer " + tok}
db = SessionLocal()
p = db.query(E.EstProject).filter_by(code="BOQT").first() or E.EstProject(code="BOQT", name="BOQ test")
db.add(p); db.commit(); pid = p.id
db.query(E.EstBoq).filter_by(project_id=pid).delete(); db.commit()
db.add(E.EstBoq(project_id=pid, section="OLD", code="1", description="Excavation", unit="m3", qty=90, rate=30, cost_rate=22, done_pct=40)); db.commit()
up = lambda data, **kw: c.post(f"/store/est/projects/{pid}/boq-import", files={"file": ("922 Internal BOQ.xlsx", data)}, data={k: str(v) for k, v in kw.items()}, headers=H)
x = up(book())
ck("preview reads, saves nothing", x.status_code == 200 and x.json()["existing"] == 1 and db.query(E.EstBoq).filter_by(project_id=pid).count() == 1, x.text[:200])
x = up(book(), save=1, mode="replace").json()
db.expire_all()
rows = db.query(E.EstBoq).filter_by(project_id=pid).all()
ck("replace: lines in, the old one out", len(rows) == x["saved"] and not any(b.section == "OLD" for b in rows))
ex = next(b for b in rows if b.description == "Excavation")
ck("replace: cost rate and done % typed before stay on the line that came back", ex.cost_rate == 22 and ex.done_pct == 40 and x["kept_budget"] == 1)
bq = c.get(f"/store/est/projects/{pid}", headers=H).json()
ck("BOQ value counts only the awarded scope, to the fils", bq["summary"]["boq_value"] == r["total"], (bq["summary"]["boq_value"], r["total"]))
ck("budget cost from the cost rate (100 x 22)", bq["summary"]["boq_cost"] == 2200)
line = next(b for b in bq["boq"] if b["description"] == "Curved column shutter")
ck("a given amount is shown as given", line["amount"] == 8000 and line["given"])
c.patch(f"/store/est/boq/{line['id']}", json={"qty": 6, "rate": 1500}, headers=H)
line = next(b for b in c.get(f"/store/est/projects/{pid}", headers=H).json()["boq"] if b["id"] == line["id"])
ck("typing qty / rate works the amount out again", line["amount"] == 9000 and not line["given"])
ck("the workbook's summary is kept on the project, to tally against", bq["boq_tally"] and bq["boq_tally"]["sheet"] == "SUMMARY" and bq["boq_tally"]["bills"].get("02. Sub Structure") == 3262.5 + 634850, bq.get("boq_tally"))
# taken out together: ticked ids, then every unpriced line
ids = [b["id"] for b in bq["boq"] if b["section"] == "A. EARTHWORKS"]
d = c.post(f"/store/est/projects/{pid}/boq-delete", json={"ids": ids}, headers=H).json()
ck(f"several lines deleted in one go ({d})", d["deleted"] == len(ids) == 2 and d["amount"] == 3262.5, d)
up(book(), save=1, mode="replace", keep_unpriced=1)
nun = sum(1 for b in c.get(f"/store/est/projects/{pid}", headers=H).json()["boq"] if not b["amount"])
d = c.post(f"/store/est/projects/{pid}/boq-delete", json={"unpriced": True}, headers=H).json()
ck(f"every unpriced line out in one go ({nun})", nun >= 2 and d["deleted"] == nun and d["amount"] == 0 and not any(not b["amount"] for b in c.get(f"/store/est/projects/{pid}", headers=H).json()["boq"]), d)
ck("nothing ticked: refused with a message", c.post(f"/store/est/projects/{pid}/boq-delete", json={"ids": []}, headers=H).status_code == 400)
n0 = db.query(E.EstBoq).filter_by(project_id=pid).count()
up(book(extra_line=True), save=1, mode="add")
ck("add: lines go after the ones there", db.query(E.EstBoq).filter_by(project_id=pid).count() > n0)
ck("not a workbook is refused", up(b"hello").status_code == 400)
t = c.post("/auth/download-token", headers=H).json()["token"]
ck("BOQ exports with the bill and remarks", c.get(f"/export/est/boq?pid={pid}&token={t}&format=xlsx").status_code == 200)
ck("no file kept", not any(f.kind == "boq" for f in db.query(E.EstFile).filter_by(project_id=pid)) if hasattr(E.EstFile, "kind") else True)
db.query(E.EstBoq).filter_by(project_id=pid).delete(); db.delete(db.get(E.EstProject, pid)); db.commit()
# ---- items priced together as ONE lump sum (a bracket in the BOQ - 5 Nov 2026) ----
def bracket_internal():
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "11.PLUMBING"
    rows = [["11. PLUMBING WORKS"], ["S/NO.", "ITEMS", "CONS. QTY", "IC QTY", "UNIT", "RATE", "AMOUNT"],
            [None, "Sanitary Fittings & Accessories"], [None, "Clean Out, CO", None, None, "No", None, 10800], [None, "Catch Basin, CB", None, None, "No"],
            [None, "Floor drain, FD", None, None, "No"],
            [None, "Hot Water Pipes"], [None, "15mm diameter", None, None, "m"], [None, None, None, None, None, None, 2500], [None, "20mm diameter", None, None, "m"],
            [1, "Manholes", None, 5, "No", 900, 4500],
            [2, "Electrical Works", None, 1, "LS", 135000, "N.A."], [3, "CCTV", None, 1, "LS", 8300, None],
            [4, "Fire Alarm Works", None, None, "LS"], [5, "Builders works", None, 1, "LS", 3500, 3500],
            [None, "TOTAL", None, None, None, None, 20800]]
    for r_ in rows:
        ws.append(r_)
    ws.merge_cells("G4:G6")                                   # the bracket: the lump sum merged down its items
    ws.merge_cells("G12:G13")                                 # a merged NOTE over lines with their own rates - not a group
    bio = io.BytesIO(); wb.save(bio); return bio.getvalue()


bi = B.read_internal_boq(bracket_internal(), keep_unpriced=True)
BL = bi["lines"]
sg = next((x for x in BL if x.get("grp") == "head" and x["description"] == "Sanitary Fittings & Accessories"), None)
ck("internal BOQ: a merged lump sum is one group line, its items under it at nil", sg and sg["amount"] == 10800 and
   [(x["description"], x["grp"], x["amount"]) for x in BL[BL.index(sg) + 1:BL.index(sg) + 4]] ==
   [("Clean Out, CO", "in", 0.0), ("Catch Basin, CB", "in", 0.0), ("Floor drain, FD", "in", 0.0)], BL[:6])
hg = next((x for x in BL if x.get("grp") == "head" and x["amount"] == 2500), None)
ck("internal BOQ: a price on a row of its own prices the items around it", hg and hg["description"] == "Hot Water Pipes" and
   [x["description"] for x in BL[BL.index(hg) + 1:BL.index(hg) + 3]] == ["15mm diameter", "20mm diameter"], hg)
ck("internal BOQ: a merged note ('N.A.') is not a group - the lines stay as they are", not any(x.get("grp") and "Electrical" in x["description"] for x in BL)
   and any(x["description"] == "Electrical Works" and x["remark"] == "N.A." for x in BL), [x for x in BL if "Elec" in x["description"]])
ck("internal BOQ: numbered items stay items of their own", any(x["description"] == "Builders works" and x["amount"] == 3500 and not x.get("grp") for x in BL)
   and any(x["description"] == "Fire Alarm Works" and not x.get("grp") for x in BL))
ck("internal BOQ: the group counted once - 10,800 + 2,500 + 4,500 + 3,500 = 21,300", bi["total"] == 21300, bi["total"])
ck("internal BOQ: a line with a rate and no amount is listed (not left out unsaid)", any(x["description"] == "CCTV" for x in BL), [x["description"] for x in BL])
print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL PASS")
sys.exit(1 if fails else 0)

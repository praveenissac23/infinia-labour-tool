"""A priced BOQ that is only a PDF - read as fully as the Excel (5 Nov 2026).

    cd app && DATABASE_URL=sqlite:////tmp/pdfboq.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/est_pdfboq_test.py [boq.xlsx ...]

1. A two-page BOQ given as the PDF's text lines (where each word sits): items priced together as one lump sum - the
   lump sum printed half-way down its items, again at the foot of the page and at the top of the next where the
   bracket runs over the page - a long item with its figures half-way down its words, figures run together in one
   piece, the page footer. Every line, group and total must come out as from the Excel.
2. With LibreOffice on this machine: each workbook given (or one made here) is printed to PDF and the PDF read must
   equal the Excel read - lines, groups, every bill's total; and the upload of the PDF on the schedule screen.
"""
import io, os, shutil, subprocess, sys, tempfile
sys.path.insert(0, os.getcwd())
import openpyxl
import est_pdfboq as P, est_itemimport as I

fails = []
def ck(name, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  -> {extra}"))
    if not ok: fails.append(name)


def L(p, y, *cells, h=10.0):
    return {"p": p, "y": y, "h": h, "c": [c for _, _, c in cells], "x": [x for x, _, _ in cells], "xe": [xe for _, xe, _ in cells]}


def head(p):
    return [L(p, 44, (755, 790, "boq.xlsx")), L(p, 67, (471, 700, "Project: Private Villa")),
            L(p, 148, (579, 638, "UNIT RATE"), (673, 722, "AMOUNT")),
            L(p, 160, (102, 126, "ITEM"), (251, 353, "WORK DESCRIPTION"), (490, 513, "UNIT"), (537, 557, "QTY")),
            L(p, 173, (592, 625, "(AED)"), (681, 714, "(AED)"))]


lines = head(1) + [
    L(1, 199, (131, 260, "PLUMBING SYSTEMS:")),
    L(1, 223, (107, 121, "A)"), (131, 240, "Waste, Soil & Vent Pipes")),
    L(1, 244, (131, 476, "Supply, Install, Testing uPVC pipe work of any kind including all supports and")),
    L(1, 256, (131, 280, "accessories as per drawings")),
    L(1, 280, (131, 194, "32mm diameter"), (498, 505, "m")),
    L(1, 296, (131, 194, "40mm diameter"), (498, 505, "m")),
    L(1, 304, (603, 614, "LS"), (652, 743, "21,000.00")),          # the lump sum, half-way down its items
    L(1, 312, (131, 194, "50mm diameter"), (498, 505, "m")),
    L(1, 336, (131, 218, "For FAHU and FCU"), (492, 511, "Item"), (541, 553, "LS"), (567, 743, "5,400.00 5,400.00")),
    L(1, 360, (131, 406, "Sanitary Fittings & Accessories")),
    L(1, 384, (131, 196, "Clean Out, CO"), (541, 553, "No")),
    L(1, 406, (131, 204, "Catch Basin, CB"), (541, 553, "No")),
    L(1, 558, (390, 452, "Page 1 of 2")),
    L(1, 563, (603, 614, "LS"), (652, 743, "12,000.00")),          # printed at the foot of the page ...
] + head(2) + [
    L(2, 153, (603, 614, "LS"), (652, 743, "12,000.00")),          # ... and again on the next
    L(2, 195, (131, 197, "Floor drain, FD"), (541, 553, "No")),
    L(2, 220, (131, 244, "Rain Water Outlet (RWO)"), (541, 553, "No")),
    L(2, 260, (131, 476, "Acoustic lagging to horizontal uPVC soil & waste pipes complete in accordance")),
    L(2, 271, (131, 293, "with the drawings and specifications.")),
    L(2, 276, (499, 504, "1"), (537, 557, "Item"), (603, 614, "LS"), (652, 743, "7,500.00")),   # half-way down its words
    L(2, 282, (131, 380, "Acoustic Lagging (insulation) as specified")),
    L(2, 320, (334, 470, "TOTAL CARRIED TO COLLECTION"), (652, 743, "45,900.00")),
    L(2, 558, (390, 452, "Page 2 of 2")),
]
r = P.read(lines)
ck("a BOQ table is found in the PDF", bool(r and r["items"]), r)
items = r["items"]
groups = {}
h = None
for x in items:
    if x["grp"] == "head":
        h = x["description"]; groups[h] = (x["amount"], [])
    elif x["grp"] == "in":
        groups[h][1].append(x["description"])
ck("total 45,900 = the page's own total", r["contract"] == 45900 and r["all_checked"], (r["contract"], [s["check"] for s in r["sheets"]]))
ck("two groups: pipes 21,000 and sanitary 12,000 (the lump sum printed twice over the page counted once)",
   sorted(a for a, _ in groups.values()) == [12000, 21000], groups)
pipe = next(v for k, v in groups.items() if v[0] == 21000)
san = next(v for k, v in groups.items() if v[0] == 12000)
ck("... the pipes' three sizes under it", pipe[1] == ["32mm diameter", "40mm diameter", "50mm diameter"], pipe)
ck("... the sanitary items under it, over the page", san[1] == ["Clean Out, CO", "Catch Basin, CB", "Floor drain, FD", "Rain Water Outlet (RWO)"], san)
ac = [x for x in items if x["description"].startswith("Acoustic lagging")]
ck("a long item: its words one line, its figures with it", len(ac) == 1 and ac[0]["amount"] == 7500 and ac[0]["grp"] == ""
   and ac[0]["description"].endswith("Acoustic Lagging (insulation) as specified"), ac)
fa = [x for x in items if x["description"] == "For FAHU and FCU"]
ck("figures run together in one piece read apart", len(fa) == 1 and fa[0]["amount"] == 5400, fa)
ck("page footers and the heading block left out", not any(("Page " in x["description"]) or "boq.xlsx" in x["description"] or "Project:" in x["description"] for x in items))
ck("nothing left at nil for review", not r["review"], r["review"])
ck("a PDF with no BOQ table -> None", P.read([L(1, 100, (100, 300, "Dear Sir,")), L(1, 120, (100, 400, "Please find attached our offer."))]) is None)


# ---- 2. Excel printed to PDF: the same reading -----------------------------------------------------------------
soffice = shutil.which("soffice") or shutil.which("libreoffice")


def made_book(path):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "PLUMBING"
    ws.append(["ITEM", "WORK DESCRIPTION", "UNIT", "QTY", "UNIT RATE (AED)", "AMOUNT (AED)"])
    rows = [[None, "PLUMBING SYSTEMS"], ["A", "Sanitary fittings"], [None, "Clean out", "No"], [None, "Catch basin", "No"],
            [None, "Floor drain", "No"], [None, "Gully trap", "No"], ["B", "Manholes", "No", 5, 900, 4500],
            ["C", "Water connection to DEWA line", "Item", 1, 7500, 7500], [None, "TOTAL CARRIED TO COLLECTION", None, None, None, 24000]]
    for r_ in rows:
        ws.append(r_)
    ws["E4"], ws["F4"] = "LS", 12000
    ws.merge_cells("E4:E7"); ws.merge_cells("F4:F7")
    ws.column_dimensions["B"].width = 60
    ws.sheet_properties.pageSetUpPr.fitToPage = True              # one page wide, as a BOQ is printed
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    wb.save(path)


def summ(x):
    return (len(x["items"]), sum(1 for i in x["items"] if i["grp"] == "head"), sum(1 for i in x["items"] if i["grp"] == "in"),
            {s["bill"] if s["bill"] and not s["bill"].startswith("Sheet") else "?": s["contract"] for s in x["sheets"]}, x["contract"])


if soffice:
    import est_fileread as F
    books = sys.argv[1:]
    tmp = tempfile.mkdtemp()
    if not books:
        made_book(os.path.join(tmp, "made.xlsx")); books = [os.path.join(tmp, "made.xlsx")]
    for b in books:
        subprocess.run([soffice, "--headless", "--convert-to", "pdf", b, "--outdir", tmp], capture_output=True, timeout=240)
        pdf = os.path.join(tmp, os.path.splitext(os.path.basename(b))[0] + ".pdf")
        data = open(pdf, "rb").read()
        xd = open(b, "rb").read()
        if xd[:4] == b"\xd0\xcf\x11\xe0":
            import est_bills_engine as BE
            xd = BE.xls_to_xlsx(xd)
        x = I.read_schedule(xd)
        p = I.read_schedule(P.workbook_of(data, "x.pdf"))
        a, e = summ(p), summ(x)
        pr = lambda r: [(i["bill"], round(i["amount"], 2)) for i in r["items"] if i["amount"]]
        ck(f"{os.path.basename(b)}: the PDF reads as the Excel - every priced line and its amount, the groups, the total "
           f"({len(pr(x))} priced lines, {e[1]} groups, {e[4]:,.2f})",
           sorted(pr(p)) == sorted(pr(x)) and a[1] == e[1] and a[4] == e[4] and p["all_checked"] == x["all_checked"], (a, e))
        # a PDF has no cell edges: words with no price may come apart or together a little differently - never lost
        ck(f"{os.path.basename(b)}: the lines at nil within 3 of the Excel's ({e[0] - len(pr(x))})", abs(a[0] - e[0]) <= 3, (a[0], e[0]))
        ck(f"{os.path.basename(b)}: every bill's total as in the Excel", sorted(s["contract"] for s in p["sheets"]) == sorted(s["contract"] for s in x["sheets"]),
           ([s["contract"] for s in p["sheets"]], [s["contract"] for s in x["sheets"]]))
    # the upload on the schedule screen takes the PDF
    from fastapi.testclient import TestClient
    import main, estimation as E
    from database import SessionLocal, engine
    main._add_missing_columns(); E.create_tables(engine)
    c = TestClient(main.app); c.__enter__()
    tok = c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json().get("access_token")
    H = {"Authorization": f"Bearer {tok}"}
    db = SessionLocal()
    pr = E.EstProject(code="PDF1", name="PDF BOQ test"); db.add(pr); db.flush()
    s = E.EstSub(project_id=pr.id, name="PDF MEP", value=24000.0); db.add(s); db.commit()
    made_book(os.path.join(tmp, "up.xlsx"))
    subprocess.run([soffice, "--headless", "--convert-to", "pdf", os.path.join(tmp, "up.xlsx"), "--outdir", tmp], capture_output=True, timeout=240)
    resp = c.post(f"/store/est/subs/{s.id}/items/import", headers=H, files={"file": ("up.pdf", open(os.path.join(tmp, "up.pdf"), "rb"), "application/pdf")}, data={"save": "0"})
    j = resp.json() if resp.status_code == 200 else {}
    ck("upload a PDF BOQ on the schedule screen: read like the Excel (24,000, one group of 4)", resp.status_code == 200 and j.get("contract") == 24000
       and j.get("groups") == 1 and j.get("members") == 4 and j.get("value_diff") == 0, (resp.status_code, resp.text[:300]))
    resp = c.post(f"/store/est/subs/{s.id}/items/import", headers=H, files={"file": ("up.pdf", open(os.path.join(tmp, "up.pdf"), "rb"), "application/pdf")}, data={"save": "1", "mode": "replace"})
    ck("... and brought in", resp.status_code == 200, resp.text[:300])
    it = c.get(f"/store/est/subs/{s.id}/items", headers=H).json()["items"]
    ck("... the group's items saved at nil under it", [x["grp"] for x in it if x["grp"]] == ["head", "in", "in", "in", "in"] and sum(x["amount"] for x in it) == 24000,
       [(x["description"], x["grp"], x["amount"]) for x in it])
    letter = os.path.join(tmp, "letter.xlsx"); wb = openpyxl.Workbook(); wb.active.append(["Dear Sir, please find attached our offer."]); wb.save(letter)
    subprocess.run([soffice, "--headless", "--convert-to", "pdf", letter, "--outdir", tmp], capture_output=True, timeout=240)
    resp = c.post(f"/store/est/subs/{s.id}/items/import", headers=H, files={"file": ("letter.pdf", open(os.path.join(tmp, "letter.pdf"), "rb"), "application/pdf")}, data={"save": "0"})
    ck("a PDF with no BOQ table: 422 (the screen then reads it as an agreement)", resp.status_code == 422, (resp.status_code, resp.text[:200]))
    db.close()
else:
    print("(LibreOffice not here - the Excel-printed-to-PDF checks skipped)")

print("\n" + (f"{len(fails)} FAILED: {fails}" if fails else "ALL PASS"))
sys.exit(1 if fails else 0)

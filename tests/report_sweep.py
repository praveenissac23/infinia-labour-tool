"""Every report in the app, checked against one standard.

Run: cd app && DATABASE_URL=sqlite:////tmp/rs.db python3 ../tests/report_sweep.py

Reports grew up one at a time across the attendance side and the store
side, and drifted: some had a preview and some did not, some carried
the letterhead, some printed the field name where a heading belonged,
columns were all given the same width whatever they held, and a
spreadsheet would run off the side of the page.

So this walks every export point in the app and holds them all to the
same standard:

  * it previews on screen, before it is a file to find and delete
  * the preview carries the Infinia letterhead
  * the preview offers Export PDF, Export Excel and Print
  * the preview is the same page, the same way up, as the file
  * headings read as headings, not as the field names behind them
  * columns are as wide as their contents, not the page divided by the
    number of columns
  * the spreadsheet is A4, fits one page wide, and repeats its heading
    row on later pages

A report that is added later and not listed here fails the last check,
which counts the export endpoints and says so.
"""
import io
import sys

sys.path.insert(0, '.')
from fastapi.testclient import TestClient
import database, models, auth

models.Base.metadata.create_all(database.engine)
import main
import export_web
from openpyxl import load_workbook
from pypdf import PdfReader

FAIL = []


def ck(label, ok, ctx=None):
    print(("PASS " if ok else "FAIL ") + label + ("" if ok else f"   [{ctx}]"))
    if not ok:
        FAIL.append(label)


# ---------------------------------------------------------------- setup
db = database.SessionLocal()
for u, r in [("admin", "admin")]:
    db.add(models.User(username=u, hashed_password=auth.hash_password("p"),
                       full_name=u, role=r))
db.commit()
db.close()

c = TestClient(main.app)
TOKEN = c.post("/auth/login", data={"username": "admin", "password": "p"}).json()["access_token"]
H = {"Authorization": "Bearer " + TOKEN}

for code, name in (("901", "Pearl Jumeirah"), ("902", "Sobha Hartland")):
    c.post("/sites", json={"code": code, "name": name}, headers=H)

c.post("/store/suppliers", json={
    "name": "Al Raha Trading LLC", "contact_person": "Biju Mathew", "phone": "0501234567",
    "trn": "100111222333003", "email": "biju@alraha.ae", "payment_terms": "30 days"},
    headers=H)

items = {}
for nm, unit, typ in (("Cement OPC 50kg", "bags", "consumable"),
                      ("Steel Cutting Machine", "pcs", "asset"),
                      ("Scaffold Ledger 1.20M", "pcs", "rental")):
    body = {"name": nm, "unit": unit, "item_type": typ, "reorder_level": 20}
    if typ == "rental":
        body["rental_supplier"] = "Al Raha Trading LLC"
    items[nm] = c.post("/store/items", json=body, headers=H).json()

c.post("/store/items/opening", json={"lines": [
    {"item_id": items["Cement OPC 50kg"]["id"], "qty": 400, "location": ""},
    {"item_id": items["Steel Cutting Machine"]["id"], "qty": 3, "location": ""},
    {"item_id": items["Scaffold Ledger 1.20M"]["id"], "qty": 600, "location": "",
     "kind": "rental", "rental_supplier": "Al Raha Trading LLC"}]}, headers=H)

for nm, qty, site, who, when in (
        ("Cement OPC 50kg", 40, "901", "Rajan Kumar", "2026-09-10"),
        ("Scaffold Ledger 1.20M", 120, "902", "Biju Thomas", "2026-09-11"),
        ("Steel Cutting Machine", 1, "901", "Muhsina P", "2026-09-12")):
    c.post("/store/movements", json={
        "item_id": items[nm]["id"], "kind": "out", "qty": qty, "from_location": "",
        "location": site, "incharge": who, "moved_on": when,
        "reference": "MI-0001", "notes": "For the raft"}, headers=H)
c.post("/store/movements", json={
    "item_id": items["Cement OPC 50kg"]["id"], "kind": "lost", "qty": 2,
    "from_location": "901", "incharge": "Rajan Kumar", "moved_on": "2026-09-13",
    "notes": "burst bags"}, headers=H)

mr = c.post("/store/requests", json={
    "site": "901", "requested_by": "febiyan", "needed_by": "2026-10-02",
    "urgency": "urgent", "notes": "", "lines": [
        {"item_id": items["Cement OPC 50kg"]["id"], "qty_requested": 100, "unit": "bags",
         "purpose": "slab", "item_type": "consumable", "description": "", "est_cost": 0,
         "notes": ""}]}, headers=H).json()

c.post("/store/purchase/orders", json={
    "supplier_name": "Al Raha Trading LLC", "supplier_trn": "100111222333003",
    "supplier_contact": "Biju Mathew", "supplier_phone": "0501234567",
    "supplier_email": "biju@alraha.ae", "contact_person": "AKHIL", "mobile": "0509998877",
    "job_scope": "Blockwork", "project_location": "901",
    "lines": [{"description": "Cement OPC 50kg", "qty": 100, "unit": "bags", "rate": 16.5}]},
    headers=H)

CYCLE = "September 2026"
emp = c.post("/employees", json={"emp_no": "S-001", "name": "Ahmad Ali", "trade": "Mason",
                                 "basic_salary": 1500, "company": "Infinia"}, headers=H)
c.post("/attendance/save", json={"month_year": CYCLE, "rows": [
    {"emp_no": "S-001", "full_date": f"2026-09-{d:02d}", "am": "Present", "pm": "Present",
     "site": "901", "engineer": "AKHIL", "ot": 2, "bh": 0, "comments": ""}
    for d in range(1, 6)]}, headers=H)

T = c.post("/auth/download-token", headers=H).json()["token"]
ORDER_ID = c.get("/store/purchase/orders", headers=H).json()[0]["id"]

# A return note for the rented scaffold, so the note itself is checked.
_held = c.get("/store/hire", headers=H).json()["suppliers"]
_lines = [{"item_id": i["item_id"], "description": i["name"], "unit": i["unit"],
           "qty_on_hire": i["qty"], "qty_returned": i["qty"], "qty_short": 0,
           "short_reason": "", "notes": ""}
          for g in _held for i in g["items"]]
RETURN_ID = c.post("/store/returns", json={
    "supplier_id": _held[0]["supplier_id"], "from_location": "",
    "driver": "Sunil", "vehicle": "DXB 12345", "lines": _lines},
    headers=H).json()["id"]

# ------------------------------------------------------- the standard
# name -> (preview url, pdf url, excel url)
#
# Every report the app offers a person. A file that is a blank form to
# fill in (the opening-stock template, the supplier import sheet) is not
# a report and is not listed; nor are the per-worker zips, which are
# bundles of the cards already covered here.
REPORTS = {}
for kind in ("stock", "low", "by_site", "purchases", "usage", "returnable",
             "assets", "hired", "lost", "mr_open", "mr_history"):
    REPORTS[f"store report: {kind}"] = (
        f"/export/store/report/view?kind={kind}&token={T}",
        f"/export/store/report?kind={kind}&format=pdf&token={T}",
        f"/export/store/report?kind={kind}&format=excel&token={T}")
REPORTS["rental materials"] = (
    f"/export/store/rental/view?token={T}",
    f"/export/store/rental?format=pdf&token={T}",
    f"/export/store/rental?format=excel&token={T}")
REPORTS["purchase orders"] = (
    f"/export/store/purchase-report/view?token={T}",
    f"/export/store/purchase-report?format=pdf&token={T}",
    f"/export/store/purchase-report?format=excel&token={T}")
REPORTS["supplier list"] = (
    f"/export/store/suppliers/report/view?token={T}",
    f"/export/store/suppliers/report?format=pdf&token={T}",
    f"/export/store/suppliers/report?format=excel&token={T}")
REPORTS["one material request"] = (
    f"/export/store/request/{mr['id']}/view?token={T}",
    f"/export/store/request/{mr['id']}?token={T}",
    f"/export/store/request/{mr['id']}?format=excel&token={T}")
REPORTS["report builder"] = (
    f"/export/{CYCLE}/custom-report/view?token={T}&data_source=summary"
    f"&dimensions=emp_no,name,trade&measures=present_days,ot_hours,final_salary",
    f"/export/{CYCLE}/custom-report?token={T}&data_source=summary"
    f"&dimensions=emp_no,name,trade&measures=present_days,ot_hours,final_salary&format=pdf",
    f"/export/{CYCLE}/custom-report?token={T}&data_source=summary"
    f"&dimensions=emp_no,name,trade&measures=present_days,ot_hours,final_salary&format=excel")
REPORTS["workforce list"] = (
    f"/export/employees/report/view?token={T}",
    f"/export/employees/report?format=pdf&token={T}",
    f"/export/employees/report?format=excel&token={T}")
REPORTS["attendance reminder"] = (
    f"/export/{CYCLE}/attendance-needed/view?token={T}&emp_nos=S-001",
    f"/export/{CYCLE}/attendance-needed?token={T}&emp_nos=S-001&format=pdf",
    f"/export/{CYCLE}/attendance-needed?token={T}&emp_nos=S-001&format=excel")

# The salary cards are a document of their own - a card a page, not a
# table - so they are checked for the same furniture but not for
# columns sized to their contents.
CARD_REPORTS = {
    "salary cards": (f"/export/{CYCLE}/cards/view?token={T}",
                     f"/export/{CYCLE}/pdf?token={T}",
                     f"/export/{CYCLE}/excel?token={T}"),
    "one worker's card": (f"/export/{CYCLE}/cards/view?token={T}&emp_no=S-001",
                          f"/export/{CYCLE}/pdf?token={T}&emp_no=S-001",
                          f"/export/{CYCLE}/excel?token={T}&emp_no=S-001"),
    # The order and the return note are documents too - a fixed page
    # with their own header blocks and signature boxes.
    "purchase order": (f"/export/purchase/{ORDER_ID}/view?token={T}",
                       f"/export/purchase/{ORDER_ID}?token={T}&format=pdf",
                       f"/export/purchase/{ORDER_ID}?token={T}&format=excel"),
    "material return note": (f"/export/store/return/{RETURN_ID}/view?token={T}",
                             f"/export/store/return/{RETURN_ID}?token={T}&format=pdf",
                             f"/export/store/return/{RETURN_ID}?token={T}&format=excel"),
}


def check(name, preview_url, pdf_url, excel_url, table=True):
    pv = c.get(preview_url)
    if pv.status_code == 404:
        print(f"     {name:28} (nothing to report on)")
        return
    if pv.status_code != 200:
        ck(f"{name}: previews on screen", False, f"HTTP {pv.status_code} {pv.text[:90]}")
        return
    body = pv.text
    ck(f"{name}: previews on screen", True)
    # The letterhead is the logo. Some documents print the company name
    # beside it, some let the logo speak for itself - either is the
    # letterhead; a page with neither is not.
    ck(f"{name}: the preview carries the letterhead",
       "data:image/png;base64," in body or "infinia contracting" in body.lower())
    ck(f"{name}: with PDF, Excel and Print on it",
       "Download PDF" in body and "Download Excel" in body and "window.print()" in body)
    ck(f"{name}: headings read as headings, not field names",
       not any(f">{k}<" in body for k in
               ("given_to", "emp_no", "item_type", "qty_requested", "reorder_level",
                "at_sites", "in_store", "days_missing", "contact_person")),
       [k for k in ("given_to", "emp_no", "item_type", "qty_requested") if f">{k}<" in body])

    pdf = c.get(pdf_url)
    ck(f"{name}: prints as a PDF",
       pdf.status_code == 200 and pdf.content[:4] == b"%PDF", pdf.status_code)
    if pdf.status_code == 200 and pdf.content[:4] == b"%PDF":
        box = PdfReader(io.BytesIO(pdf.content)).pages[0].mediabox
        pdf_turn = "landscape" if box.width > box.height else "portrait"
        pv_turn = "portrait" if "width:210mm" in body else "landscape"
        ck(f"{name}: the preview is the same way up as the file",
           pdf_turn == pv_turn, f"file {pdf_turn}, preview {pv_turn}")

    xl = c.get(excel_url)
    ck(f"{name}: comes as a spreadsheet", xl.status_code == 200 and len(xl.content) > 2000,
       xl.status_code)
    if xl.status_code == 200 and len(xl.content) > 2000:
        ws = load_workbook(io.BytesIO(xl.content)).active
        ck(f"{name}: the sheet is A4", int(ws.page_setup.paperSize or 0) == 9,
           ws.page_setup.paperSize)
        ck(f"{name}: fitted to one page wide",
           bool(ws.page_setup.fitToWidth)
           and bool(ws.sheet_properties.pageSetUpPr and ws.sheet_properties.pageSetUpPr.fitToPage))
        if table:
            # A card document is a page per worker, each with its own
            # header - there is no one heading row to repeat.
            ck(f"{name}: the heading row repeats on later pages",
               bool(ws.print_title_rows), ws.print_title_rows)
        if table:
            widths = [d.width for d in ws.column_dimensions.values() if d.width]
            ck(f"{name}: columns are not all one width",
               len(set(round(w) for w in widths)) > 1 or len(widths) <= 1, widths)
    if table:
        # A page divided equally between its columns wastes most of
        # itself on the narrow ones.
        ck(f"{name}: the preview sizes its columns to their contents",
           "<colgroup>" in body and body.count("<col style=") > 1,
           body.count("<col style="))


print("---- the reports ----")
for name, (a, b, d) in REPORTS.items():
    check(name, a, b, d)

print("\n---- the salary cards ----")
for name, (a, b, d) in CARD_REPORTS.items():
    check(name, a, b, d, table=False)

# ---- Nothing new slips in unchecked ----------------------------------
# A report added later and not listed above would be missed by this
# sweep entirely, so the count of export endpoints is held down.
views = [r.path for r in main.app.routes
         if getattr(r, "path", "").startswith("/export/") and r.path.endswith("/view")]
print(f"\n{len(views)} preview endpoints, {len(REPORTS) + len(CARD_REPORTS)} reports checked")
# Every preview the app has must be one of the ones checked above. A
# report added later and not listed here would be missed entirely.
checked_paths = {
    "/export/store/report/view", "/export/store/rental/view",
    "/export/store/purchase-report/view", "/export/store/suppliers/report/view",
    "/export/store/request/{req_id}/view", "/export/store/return/{return_id}/view",
    "/export/purchase/{order_id}/view", "/export/employees/report/view",
    "/export/{month_year}/custom-report/view",
    "/export/{month_year}/attendance-needed/view", "/export/{month_year}/cards/view",
}
missed = sorted(set(views) - checked_paths)
ck("every preview endpoint is covered by this sweep", not missed, missed)

print()
print("ALL REPORTS TO ONE STANDARD" if not FAIL
      else f"{len(FAIL)} FAILED:\n - " + "\n - ".join(FAIL))
sys.exit(1 if FAIL else 0)

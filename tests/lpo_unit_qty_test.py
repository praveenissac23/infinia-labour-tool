"""LPO print (3 Nov 2026, purchase): a Unit column in place of the Tax amount column, and the quantity exactly as
typed - 9.091 TON is printed 9.091, not 9.09 (qty x rate on the page must give the amount on the page).
Checked on the on-screen preview, the PDF and the Excel (recalculated by LibreOffice: the same total as the app).
    cd app && DATABASE_URL=sqlite:////tmp/lu.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/lpo_unit_qty_test.py
"""
import io, os, re, subprocess, sys, tempfile
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main, export_web, database, models
c = TestClient(main.app); c.__enter__()
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:400]}"))
    if not ok: fails.append(n)
H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
# the five steel lines from the purchaser's screenshot, with the quantity as typed (3 decimals)
L = [("Steel 20MM (Jindal)", 9.091, "TON", 2840), ("Steel 10MM (Jindal)", 0.963, "TON", 2860), ("Steel 32MM (Jindal)", 2.616, "TON", 2840),
     ("Steel 25MM (Jindal)", 0.572, "TON", 2840), ("Steel 16MM (Jindal)", 1.924, "TON", 2840), ("Binding wire", 3, "ROLL", 25.5)]
b = {"supplier_name": "Ghantoot Building Materials", "order_date": "2026-11-03", "project_location": "913",
     "lines": [{"description": d, "qty": q, "unit": u, "rate": r, "tax_pct": 5} for d, q, u, r in L]}
r = c.post("/store/purchase/orders", json=b, headers=H)
ck("LPO raised", r.status_code == 200, r.text[:300])
oid = r.json()["id"]
db = database.SessionLocal(); o = db.get(models.PurchaseOrder, oid)
ck("quantities saved exactly as typed", [l.qty for l in o.lines] == [x[1] for x in L], [l.qty for l in o.lines])
total = main.lpo_total(o)
want = round(sum(q * r for _, q, _, r in L) * 1.05, 2)
ck(f"the app's total {total:,.2f} = qty x rate + 5% VAT ({want:,.2f})", abs(total - want) < 0.006, (total, want))

# ---- on-screen preview
h = main._lpo_html(o)
head = re.search(r"<thead>(.*?)</thead>", h, re.S).group(1)
cols = re.findall(r"<th[^>]*>(.*?)</th>", head)
ck(f"preview columns: {cols}", cols == ["#", "Item &amp; Description", "Qty", "Unit", "Rate", "Tax %", "Amount"], cols)
ck("preview: 9.091 / 0.963 / 2.616 / 0.572 / 1.924 as typed, 3 shown as 3.00", all(f">{q}<" in h for q in ("9.091", "0.963", "2.616", "0.572", "1.924", "3.00")), h[:200])
ck("preview: the units (TON, ROLL) and no tax-amount figure for line 1 (1,290.92)", ">TON<" in h and ">ROLL<" in h and "1,290.92" not in h and "1,291.18" not in h)
ck("preview: line 1 amount 25,818.44 (9.091 x 2,840)", ">25,818.44<" in h)
ck(f"preview: total AED {total:,.2f}", f"AED {total:,.2f}" in h)

# ---- PDF
pdf = export_web.build_lpo_pdf(main._lpo_for_print(o)).getvalue()
with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
    f.write(pdf); pp = f.name
txt = subprocess.run(["pdftotext", "-layout", pp, "-"], capture_output=True, text=True).stdout
ck("PDF: Unit heading, no Tax amount heading", re.search(r"Qty\s+Unit\s+Rate\s+Tax %\s+Amount", txt) is not None, txt[:1500])
ck("PDF: 9.091 TON 2,840.00 5.00 25,818.44 on one line", re.search(r"9\.091\s+TON\s+2,840\.00\s+5\.00\s+25,818\.44", txt) is not None, txt[:2000])
ck("PDF: 0.963 TON (not 0.96)", re.search(r"0\.963\s+TON", txt) is not None)
ck(f"PDF: total {total:,.2f}", f"{total:,.2f}" in txt, txt[-800:])

# ---- Excel, recalculated by LibreOffice
from openpyxl import load_workbook
xb = export_web.build_lpo_excel(main._lpo_for_print(o)).getvalue()
d = tempfile.mkdtemp()
src = os.path.join(d, "lpo.xlsx"); open(src, "wb").write(xb)
subprocess.run(["soffice", "--headless", "--convert-to", "xlsx:Calc MS Excel 2007 XML", "--outdir", os.path.join(d, "out"), src], capture_output=True, timeout=120)
wb = load_workbook(os.path.join(d, "out", "lpo.xlsx"), data_only=True); ws = wb.active
rows = [[c_.value for c_ in row] for row in ws.iter_rows()]
hdr = next(r_ for r_ in rows if r_[:3] == ["#", "Item & Description", "Qty"])
ck(f"Excel columns: {hdr[:7]}", hdr[:7] == ["#", "Item & Description", "Qty", "Unit", "Rate", "Tax %", "Amount"], hdr)
first = next(r_ for r_ in rows if r_[1] == "Steel 20MM (Jindal)")
ck(f"Excel line 1: {first[:7]}", first[2] == 9.091 and first[3] == "TON" and abs(first[6] - 25818.44) < 0.006, first)
wb2 = load_workbook(src); ws2 = wb2.active
fmt = next(ws2.cell(row=i, column=3).number_format for i in range(1, ws2.max_row + 1) if ws2.cell(row=i, column=2).value == "Steel 20MM (Jindal)")
ck(f"Excel shows the qty with 3 decimals ({fmt})", fmt.endswith(".000"), fmt)
tot = next((r_[6] for r_ in rows if r_[4] == "Total"), None)
ck(f"Excel total {tot} = the app's {total:,.2f}", tot is not None and abs(tot - total) < 0.006, rows[-12:])
vat = next((r_[6] for r_ in rows if r_[4] and str(r_[4]).startswith("Standard Rate")), None)
ck(f"Excel VAT {vat} = the app's {main._lpo_net_vat(o)[1]:,.2f}", vat is not None and abs(vat - round(main._lpo_net_vat(o)[1], 2)) < 0.006, vat)
db.close()
print("ALL PASS" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)

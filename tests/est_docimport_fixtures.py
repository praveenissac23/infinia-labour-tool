"""A BOQ and a variation log as PDFs (and the log scanned) for the Estimation imports.
    python3 tests/est_docimport_fixtures.py /tmp/estdocs -> JSON {name: {file, expect}}"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, Spacer, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/estdocs"
os.makedirs(out, exist_ok=True)
import importlib.util
spec = importlib.util.spec_from_file_location("adf_scan", os.path.join(os.path.dirname(__file__), "app_docread_fixtures.py"))
st = getSampleStyleSheet(); P = lambda t, s="Normal": Paragraph(t, st[s])
GRID = TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey)])
res = {}
boq = [["Item", "Description", "Unit", "Qty", "Rate", "Amount"],
       ["", "BILL A - SUBSTRUCTURE", "", "", "", ""],
       ["A1", "Excavation in any material", "m3", "420", "18.00", "7,560.00"],
       ["A2", "Blinding concrete 50mm", "m2", "310", "22.50", "6,975.00"],
       ["A3", "Raft foundation C40", "m3", "96", "640.00", "61,440.00"],
       ["", "Total Bill A", "", "", "", "75,975.00"],
       ["", "BILL B - SUPERSTRUCTURE", "", "", "", ""],
       ["B1", "Columns C40", "m3", "38", "720.00", "27,360.00"],
       ["B2", "Slabs C35", "m3", "145", "610.00", "88,450.00"],
       ["", "Total Bill B", "", "", "", "115,810.00"],
       ["", "Grand Total", "", "", "", "191,785.00"]]
f = os.path.join(out, "931 BOQ.pdf")
SimpleDocTemplate(f, pagesize=A4).build([P("BILL OF QUANTITIES - VILLA 931", "Title"), Spacer(1, 8), Table(boq, style=GRID)])
res["boq"] = {"file": f, "expect": {"lines": 5, "total": 191785}}
log = [["Ref. No", "Description", "Date of Submission", "Submitted Amount (AED)", "Approved Amount (AED)", "Remarks"],
       ["V01", "Additional pergola at roof terrace", "02/10/2026", "48,750.00", "45,000.00", "Approved"],
       ["V02", "Change of floor tiles to marble in", "08/10/2026", "126,400.00", "", "Under review"],
       ["", "majlis and entrance lobby", "", "", "", ""],
       ["V03", "Omission of garden pavilion", "12/10/2026", "-32,000.00", "-32,000.00", "Approved"]]
f = os.path.join(out, "931 variation log.pdf")
SimpleDocTemplate(f, pagesize=landscape(A4)).build([P("VARIATION LOG - VILLA 931", "Title"), Spacer(1, 8), Table(log, style=GRID)])
res["volog"] = {"file": f, "expect": {"rows": 3, "submitted": 143150, "titles": ["Additional pergola at roof terrace", "Change of floor tiles to marble in majlis and entrance lobby", "Omission of garden pavilion"]}}
print(json.dumps(res))

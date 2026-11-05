"""Difficult BOQ / schedule / certificate workbooks with the true answer kept beside each (5 Nov 2026).

Made to be HARDER than the documents the readers were written from - no template shared with any reader:

  * heading words of every kind (Description / Particulars / Scope of Work / Item Description; Qty / Quantity / Qty. ;
    Unit / U/M / UOM; Rate / Unit Rate / Unit Price / Rate (AED); Amount / Total / Total Price / Amount in AED ...),
    columns in any order, blank spacer columns, a remarks / make column, a hidden internal column with figures,
    one or two heading rows (merged "QUANTITY" over Qty | Unit, "RATE (AED)" over Supply | Install | Total),
    the heading anywhere from row 1 to row 14 under a merged title block;
  * bills one per sheet or many on one sheet (A, B, C with sub-totals), a cover sheet, a preambles sheet, a
    summary sheet first or last (bill totals, Sub-total, Contingency / Discount, VAT 5%, Grand total);
  * page totals ("Carried forward" / "Total carried to collection") and "Brought forward" at the top of the next
    page (never to be counted twice), a collection page listing the page totals;
  * items numbered 1.01 / A / a) / (i) / 2.3.1 / none; descriptions wrapped over two or three rows (figures on the
    first or the last row), merged description cells, long specifications;
  * figures as numbers, as text ("1,250.50", "AED 3,500.00", "(250.00)"), as formulas (=qty*rate, with Excel's
    saved values from LibreOffice), qty with its unit ("25 m2"), the unit typed in the qty column, LS items;
  * items priced together as one lump sum (merged rate / amount cells over 2-12 items, across a page break);
    "Included" / "Excluded" / "N.A." / "By others" / "Rate only" items; provisional sums.

    python3 tests/stress/boq_gen.py OUT_DIR [--n 40] [--seed 3] [--pc]       (PC: certificates with % columns)

Each OUT_DIR/boq_NN.xlsx has OUT_DIR/boq_NN.json:
  {"contract": total of the priced lines, "bills": {bill: total}, "lines": [{bill, no, desc, qty, unit, rate, amount,
   grp: ""|"head"|"in", pct, certified}], "unpriced": [descriptions brought in at nil or for review], "features": [...]}
"""
import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile

import openpyxl
from openpyxl.styles import Alignment, Font

R2 = lambda x: round(x + 1e-9, 2)

TRADES = ["PRELIMINARIES", "SUBSTRUCTURE", "SUPERSTRUCTURE", "BLOCKWORK", "PLASTERING", "WATERPROOFING", "FLOOR FINISHES",
          "WALL FINISHES", "CEILINGS", "JOINERY", "DOORS & WINDOWS", "ALUMINIUM & GLAZING", "PAINTING", "HVAC", "PLUMBING",
          "DRAINAGE", "ELECTRICAL", "LIGHTING", "FIRE FIGHTING", "FIRE ALARM", "LOW CURRENT", "EXTERNAL WORKS", "LANDSCAPING",
          "SWIMMING POOL", "HOME AUTOMATION"]
NOUNS = ["Concrete", "Blockwork", "Plaster", "Ceramic tiles", "Porcelain tiles", "Gypsum board", "Paint", "Waterproofing membrane",
         "uPVC pipe", "PPR pipe", "Copper pipe", "Cable tray", "Conduit", "LED downlight", "Socket outlet", "Switch",
         "Distribution board", "Fan coil unit", "Duct", "Grille", "Diffuser", "Valve", "Pump", "Manhole", "Gully trap",
         "Door", "Window", "Handrail", "Skirting", "Threshold", "Marble", "Granite", "Screed", "Insulation", "Sealant"]
QUAL = ["50mm", "75mm", "100mm", "150mm", "200mm", "20mm", "25mm", "32mm", "2.5mm2", "4mm2", "6mm2", "600x600", "1200x600",
        "Class A", "Grade 40", "fire rated", "moisture resistant", "external", "internal", "approved make", "type B"]
UNITS = ["m2", "m", "m3", "No", "Nos", "kg", "LS", "Item", "Set", "lm", "Sqm", "Rm", "Pair", "Lot", "ton"]
LONG = ("Supply, install, test and commission the following complete with all fixings, supports, accessories, "
        "sleeves, labels, testing and commissioning as per the specifications, drawings and the Engineer's approval, "
        "including all builder's work, making good and protection until handover")

HEAD = {
    "no": ["Item", "Item No", "S.No", "Sr. No.", "Ref", "Bill No", "No.", "SL No", "Item Ref", "Code", "S/N"],
    "desc": ["Description", "DESCRIPTION OF WORK", "Particulars", "Item Description", "Scope of Work", "Description of Works",
             "WORK DESCRIPTION", "Details", "Description of Items"],
    "qty": ["Qty", "Quantity", "QTY.", "Qty (Approx.)", "Estimated Qty", "Est. Quantity", "Quantities"],
    "unit": ["Unit", "UOM", "U/M", "Units", "UNIT"],
    "rate": ["Rate", "Unit Rate", "Unit Price", "Rate (AED)", "Unit Rate (AED)", "RATE AED", "Price"],
    "amount": ["Amount", "Total", "Total Price", "Amount (AED)", "Amount in AED", "TOTAL (AED)", "Total Amount", "Value (AED)",
               "Price (AED)"],
    "remark": ["Remarks", "Make / Brand", "Notes", "Comments", "Approved Make"],
    "internal": ["Cost", "Int. Rate", "Our cost", "Budget"],
}


def ritem(rng):
    q = rng.choice(QUAL)
    return rng.choice([f"{rng.choice(NOUNS)} {q}", f"{q} {rng.choice(NOUNS).lower()}", f"{rng.choice(NOUNS)}, {q}, {rng.choice(QUAL)}"])


def money_text(rng, v):
    return rng.choice([f"{v:,.2f}", f"AED {v:,.2f}", f"{v:,.2f} ", f"{v:.2f}"])


class Book:
    """One workbook and its truth."""

    def __init__(self, rng, pc=False):
        self.rng, self.pc = rng, pc
        self.wb = openpyxl.Workbook()
        self.wb.remove(self.wb.active)
        self.lines, self.unpriced, self.features = [], [], set()
        self.bills = {}

    def feat(self, f):
        self.features.add(f)

    # ---------------------------------------------------------------------------------------------------- layout
    def plan_columns(self):
        rng = self.rng
        order = rng.choice([["no", "desc", "unit", "qty", "rate", "amount"], ["no", "desc", "qty", "unit", "rate", "amount"],
                            ["no", "desc", "qty", "unit", "rate", "amount", "remark"], ["desc", "unit", "qty", "rate", "amount"],
                            ["no", "desc", "unit", "qty", "rate", "amount", "remark"], ["no", "desc", "qty", "rate", "amount"]])
        if "unit" not in order:
            self.feat("qty with its unit in one cell")
        cols = []
        for k in order:
            cols.append(k)
            if rng.random() < 0.12 and k in ("desc", "qty", "rate"):
                cols.append("blank")
                self.feat("blank spacer column")
        if rng.random() < 0.2:
            cols.insert(cols.index("amount") + 1, "internal")
            self.feat("hidden internal column")
        self.split_rate = "rate" in cols and rng.random() < 0.18          # Supply | Install | Total rate
        if self.split_rate:
            i = cols.index("rate")
            cols[i:i + 1] = ["supply", "install", "rate"]
            self.feat("rate split supply / install")
        self.desc_merge = rng.random() < 0.15                            # description merged over two columns
        if self.desc_merge:
            cols.insert(cols.index("desc") + 1, "desc2")
            self.feat("description merged over two columns")
        self.two_row = rng.random() < 0.3 or self.split_rate
        if self.two_row:
            self.feat("two heading rows")
        if self.pc:
            cols += ["prev_pct", "cur_pct", "pct", "cert"]
        self.cols = cols
        self.heads = {k: rng.choice(HEAD[k]) for k in HEAD}
        self.numbering = rng.choice(["dec", "letter", "num", "paren", "deep", "none", "letter_paren"])
        self.fig_style = rng.choice(["num", "num", "num", "text", "formula", "formula", "mixed"])
        self.feat(f"figures as {self.fig_style}")
        self.feat(f"numbering {self.numbering}")

    def item_no(self, k, sec):
        n = self.numbering
        return {"dec": f"{sec}.{k:02d}", "letter": "ABCDEFGHJKLMNPQRSTUVWXYZ"[(k - 1) % 24] + ("" if k <= 24 else str(k // 24)),
                "num": str(k), "paren": f"({'abcdefghijklmnopqrstuvwxyz'[(k - 1) % 26]})", "deep": f"{sec}.{(k - 1) // 6 + 1}.{(k - 1) % 6 + 1}",
                "none": "", "letter_paren": "abcdefghijklmnopqrstuvwxyz"[(k - 1) % 26] + ")"}[n]

    def header_rows(self, ws, r):
        c = self.cols
        lab = {"no": self.heads["no"], "desc": self.heads["desc"], "unit": self.heads["unit"], "qty": self.heads["qty"],
               "rate": self.heads["rate"], "amount": self.heads["amount"], "remark": self.heads["remark"], "internal": self.heads["internal"],
               "supply": "Supply", "install": "Install", "prev_pct": "Previous %", "cur_pct": "Current %", "pct": "Total % Work Done",
               "cert": "Certified Amount"}
        if self.two_row:
            for i, k in enumerate(c, 1):
                if k in ("blank", "desc2"):
                    continue
                if k in ("qty", "unit") and "qty" in c and "unit" in c and abs(c.index("qty") - c.index("unit")) == 1:
                    a = min(c.index("qty"), c.index("unit")) + 1
                    ws.cell(r, a, "QUANTITY")
                    if not any(str(m) == f"{openpyxl.utils.get_column_letter(a)}{r}:{openpyxl.utils.get_column_letter(a + 1)}{r}" for m in ws.merged_cells.ranges):
                        ws.merge_cells(start_row=r, start_column=a, end_row=r, end_column=a + 1)
                    ws.cell(r + 1, i, lab[k])
                elif k in ("supply", "install", "rate") and self.split_rate:
                    a = c.index("supply") + 1
                    if ws.cell(r, a).value is None:
                        ws.cell(r, a, "RATE (AED)")
                        ws.merge_cells(start_row=r, start_column=a, end_row=r, end_column=a + 2)
                    ws.cell(r + 1, i, {"supply": "Supply", "install": "Install", "rate": "Total"}[k])
                else:
                    ws.cell(r, i, lab[k])
                    ws.merge_cells(start_row=r, start_column=i, end_row=r + 1, end_column=i)
            if self.desc_merge:
                d = c.index("desc") + 1
                ws.unmerge_cells(start_row=r, start_column=d, end_row=r + 1, end_column=d)
                ws.merge_cells(start_row=r, start_column=d, end_row=r + 1, end_column=d + 1)
            return r + 2
        for i, k in enumerate(c, 1):
            if k in ("blank", "desc2"):
                continue
            ws.cell(r, i, lab[k]).font = Font(bold=True)
        if self.desc_merge:
            d = c.index("desc") + 1
            ws.merge_cells(start_row=r, start_column=d, end_row=r, end_column=d + 1)
        return r + 1

    def put(self, ws, r, k, v):
        if k not in self.cols or v is None:
            return
        ws.cell(r, self.cols.index(k) + 1, v)

    def fig(self, ws, r, k, v, qty_rate=None):
        """A figure as this book writes figures."""
        rng, st = self.rng, self.fig_style
        if st == "mixed":
            st = rng.choice(["num", "text"])                 # (a formula over a text rate would be #VALUE! - no BOQ ships that)
            if k == "rate":
                self._rate_text = st == "text"
        if k == "amount" and st == "formula" and qty_rate and "qty" in self.cols and "unit" in self.cols and "rate" in self.cols \
                and isinstance(qty_rate[0], (int, float)):
            q = openpyxl.utils.get_column_letter(self.cols.index("qty") + 1)
            ra = openpyxl.utils.get_column_letter(self.cols.index("rate") + 1)
            self.put(ws, r, k, f"=ROUND({q}{r}*{ra}{r},2)")
            return
        if st == "text" and k in ("amount", "rate"):
            self.put(ws, r, k, money_text(rng, v))
            return
        self.put(ws, r, k, v)

    # ---------------------------------------------------------------------------------------------------- content
    def items(self, bill, n):
        """The bill's items: [(kind, data)] kind = item | heading | bracket | words."""
        rng = self.rng
        out, k = [], 0
        while len(out) < n:
            x = rng.random()
            if x < 0.07:
                out.append(("heading", rng.choice(["General", "Supply and installation", f"{rng.choice(NOUNS)} works", "Sundries",
                                                   f"{bill.title()} - {rng.choice(['Ground floor', 'First floor', 'Roof', 'Basement', 'External'])}"])))
                continue
            k += 1
            if x < 0.13:
                m = rng.randint(2, 12)
                amt = float(rng.randrange(20, 900) * 100)
                out.append(("bracket", {"no": k, "head": f"{rng.choice(NOUNS)} - complete system", "members":
                                        [ritem(rng) for _ in range(m)], "amount": amt, "rate_word": rng.choice(["LS", "LS", None]),
                                        "unit": rng.choice(["No", "m", "Set", "Nos"])}))
                self.feat("lump-sum bracket")
                continue
            if x < 0.17:
                out.append(("words", {"no": k, "desc": ritem(rng), "word": rng.choice(["Included", "Excluded", "N.A.", "By others", "Rate only", "Incl."]),
                                      "unit": rng.choice(UNITS)}))
                self.feat("words in place of a price")
                continue
            unit = rng.choice(UNITS)
            if unit in ("LS", "Item", "Lot"):
                qty, rate = 1.0, float(rng.randrange(5, 400) * 50)
            else:
                qty = rng.choice([float(rng.randrange(1, 60)), R2(rng.uniform(1, 900)), float(rng.randrange(10, 2000))])
                rate = rng.choice([float(rng.randrange(5, 900)), R2(rng.uniform(2, 2500))])
            desc = ritem(rng)
            wrap = rng.random() < 0.15
            if rng.random() < 0.06:
                desc = "Provisional sum for " + rng.choice(["authority fees", "testing", "temporary works", "client's specialist"])
                unit, qty, rate = "PS", 1.0, float(rng.randrange(10, 200) * 500)
                self.feat("provisional sum")
            out.append(("item", {"no": k, "desc": desc, "qty": qty, "unit": unit, "rate": rate, "amount": R2(qty * rate), "wrap": wrap,
                                 "intro": LONG if rng.random() < 0.08 else None}))
        return out

    def sheet(self, title, bills_here, one_sheet):
        """A sheet holding one or more bills; returns the bill totals written."""
        rng = self.rng
        ws = self.wb.create_sheet(title[:31])
        r = 1
        top = rng.randint(0, 12)
        if top:
            ws.cell(1, 1, rng.choice(["PROPOSED G+1 PRIVATE VILLA - PLOT 347-4803", "SOBHA HARTLAND - VILLA VE-208", "BILL OF QUANTITIES",
                                      "SUBCONTRACT AGREEMENT - APPENDIX A"])).font = Font(bold=True, size=14)
            ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(self.cols))
            for i in range(2, top + 1):
                if rng.random() < 0.6:
                    ws.cell(i, 1, rng.choice(["Client: Emkaan Design", "Consultant: Renaissance Engineering", "Date: 05/11/2026",
                                              "Rev: R2", "Tender ref: IC/TND/931/26", "Page 1 of 9",
                                              "Notes: rates include all overheads"]))
            r = top + 2
            self.feat("title block above the heading")
        r = self.header_rows(ws, r)
        page_len = rng.choice([None, None, 18, 25, 32])
        if page_len:
            self.feat("page totals carried forward")
        bf = page_len and rng.random() < 0.6
        if bf:
            self.feat("brought forward rows")
        totals = {}
        amt_col = self.cols.index("amount") + 1
        for bi, (bill, items) in enumerate(bills_here):
            if one_sheet or rng.random() < 0.7:
                ws.cell(r, self.cols.index("desc") + 1, f"BILL NO. {bi + 1} - {bill}" if one_sheet else bill).font = Font(bold=True)
                r += 1
            tot, page_tot, rows_on_page, pages = 0.0, 0.0, 0, []
            for kind, d in items:
                if page_len and rows_on_page >= page_len:
                    ws.cell(r, self.cols.index("desc") + 1, rng.choice(["Carried forward", "CARRIED TO COLLECTION", "Total carried forward", "Page total c/f"]))
                    ws.cell(r, amt_col, R2(page_tot))
                    pages.append(R2(page_tot))
                    r += 1
                    if bf:
                        ws.cell(r, self.cols.index("desc") + 1, rng.choice(["Brought forward", "B/F from previous page", "Brought forward from page " + str(len(pages))]))
                        ws.cell(r, amt_col, R2(page_tot) if rng.random() < 0.5 else R2(sum(pages)))
                        r += 1
                    page_tot, rows_on_page = (0.0 if True else page_tot), 0
                if kind == "heading":
                    ws.cell(r, self.cols.index("desc") + 1, d).font = Font(bold=True, underline="single")
                    r += 1
                    rows_on_page += 1
                    continue
                no = self.item_no(d["no"], bi + 1)
                if kind == "words":
                    self.put(ws, r, "no", no)
                    ws.cell(r, self.cols.index("desc") + 1, d["desc"])
                    self.put(ws, r, "unit", d["unit"])
                    if d["word"] == "Rate only":
                        self.fig(ws, r, "rate", float(rng.randrange(10, 500)))
                        self.put(ws, r, "amount", "Rate only")
                    else:
                        self.put(ws, r, "amount", d["word"])
                    self.unpriced.append({"bill": bill, "desc": d["desc"]})
                    r += 1
                    rows_on_page += 1
                    continue
                if kind == "bracket":
                    self.put(ws, r, "no", no)
                    ws.cell(r, self.cols.index("desc") + 1, d["head"]).font = Font(bold=True)
                    r += 1
                    first = r
                    for m in d["members"]:
                        ws.cell(r, self.cols.index("desc") + 1, m)
                        self.put(ws, r, "unit", d["unit"]) if "unit" in self.cols else self.put(ws, r, "qty", d["unit"])
                        r += 1
                        rows_on_page += 1
                    last = r - 1
                    if d["rate_word"] and "rate" in self.cols:
                        ws.cell(first, self.cols.index("rate") + 1, d["rate_word"])
                        if last > first:
                            ws.merge_cells(start_row=first, start_column=self.cols.index("rate") + 1, end_row=last, end_column=self.cols.index("rate") + 1)
                    ws.cell(first, amt_col, d["amount"] if self.fig_style != "text" else money_text(rng, d["amount"]))
                    if last > first:
                        ws.merge_cells(start_row=first, start_column=amt_col, end_row=last, end_column=amt_col)
                        ws.cell(first, amt_col).alignment = Alignment(vertical="center")
                    self.lines.append({"bill": bill, "no": no, "desc": d["head"], "amount": d["amount"], "grp": "head", "members": list(d["members"])})
                    tot += d["amount"]
                    page_tot += d["amount"]
                    continue
                # an item
                if d.get("intro"):
                    ws.cell(r, self.cols.index("desc") + 1, d["intro"])
                    ws.cell(r, self.cols.index("desc") + 1).alignment = Alignment(wrap_text=True)
                    r += 1
                    rows_on_page += 1
                    self.feat("long specification paragraph")
                desc_rows = [d["desc"]]
                if d["wrap"]:
                    words = (d["desc"] + " " + rng.choice(["complete with fixings and accessories", "as per drawing A-201 and specification section 09",
                                                           "including testing and commissioning", "to the approval of the Engineer"])).split()
                    cut = len(words) // 2
                    desc_rows = [" ".join(words[:cut]), " ".join(words[cut:])]
                    self.feat("description wrapped over rows")
                fig_row = r if (not d["wrap"] or rng.random() < 0.5) else r + len(desc_rows) - 1
                for j, t in enumerate(desc_rows):
                    ws.cell(r + j, self.cols.index("desc") + 1, t)
                self.put(ws, r, "no", no)
                swapped = False
                if "unit" in self.cols:
                    self.put(ws, fig_row, "unit", d["unit"])
                    if rng.random() < 0.03 and "qty" in self.cols:
                        swapped = True
                        self.put(ws, fig_row, "qty", d["unit"])           # the unit typed in the qty column ...
                        self.put(ws, fig_row, "unit", d["qty"])           # ... and the qty in the unit column
                        self.feat("unit and qty swapped")
                    else:
                        self.fig(ws, fig_row, "qty", d["qty"])
                else:
                    self.put(ws, fig_row, "qty", f"{d['qty']:g} {d['unit']}")
                if self.split_rate:
                    sup = R2(d["rate"] * 0.6)
                    self.put(ws, fig_row, "supply", sup)
                    self.put(ws, fig_row, "install", R2(d["rate"] - sup))
                self.fig(ws, fig_row, "rate", d["rate"])
                self.fig(ws, fig_row, "amount", d["amount"], None if swapped else (d["qty"], d["rate"]))
                if "internal" in self.cols:
                    self.put(ws, fig_row, "internal", R2(d["amount"] * 0.7))
                if "remark" in self.cols and rng.random() < 0.3:
                    self.put(ws, fig_row, "remark", rng.choice(["Approved make", "As per spec", "Excl. supply", "Ref. SK-12", "Option 2"]))
                line = {"bill": bill, "no": no, "desc": " ".join(desc_rows), "qty": d["qty"], "unit": d["unit"], "rate": d["rate"],
                        "amount": d["amount"], "grp": ""}
                if self.pc:
                    pp = rng.choice([0, 0, 10, 25, 40, 50, 100])
                    cp = rng.choice([0, 0, 0, 10, 20, 30]) if pp < 100 else 0
                    tp = min(100, pp + cp)
                    self.put(ws, fig_row, "prev_pct", pp / 100.0)
                    self.put(ws, fig_row, "cur_pct", (tp - pp) / 100.0)
                    self.put(ws, fig_row, "pct", tp / 100.0)
                    self.put(ws, fig_row, "cert", R2(d["amount"] * tp / 100.0))
                    line["pct"], line["certified"] = tp, R2(d["amount"] * tp / 100.0)
                self.lines.append(line)
                tot += d["amount"]
                page_tot += d["amount"]
                r += len(desc_rows)
                rows_on_page += len(desc_rows)
            if page_len and pages:
                ws.cell(r, self.cols.index("desc") + 1, "Carried forward")
                ws.cell(r, amt_col, R2(page_tot))
                pages.append(R2(page_tot))
                r += 2
                ws.cell(r, self.cols.index("desc") + 1, "COLLECTION").font = Font(bold=True)
                r += 1
                for pi, pv in enumerate(pages, 1):
                    ws.cell(r, self.cols.index("desc") + 1, f"Page {pi}")
                    ws.cell(r, amt_col, pv)
                    r += 1
                self.feat("collection page")
            ws.cell(r, self.cols.index("desc") + 1, rng.choice([f"TOTAL - {bill}", f"Sub-total Bill No. {bi + 1}", "TOTAL CARRIED TO SUMMARY",
                                                                f"Total of {bill.title()}", "Bill total"])).font = Font(bold=True)
            ws.cell(r, amt_col, R2(tot))
            totals[bill] = R2(tot)
            r += 2
        if self.cols.count("internal"):
            ws.column_dimensions[openpyxl.utils.get_column_letter(self.cols.index("internal") + 1)].hidden = True
        widths = {"no": 9, "desc": 55, "desc2": 12, "unit": 8, "qty": 12, "rate": 14, "amount": 17, "remark": 18, "internal": 12,
                  "supply": 11, "install": 11, "prev_pct": 10, "cur_pct": 10, "pct": 11, "cert": 16, "blank": 3}
        for i, k in enumerate(self.cols, 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = widths.get(k, 12)
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
        return totals

    def build(self, nbills, per_bill):
        rng = self.rng
        self.plan_columns()
        bills = rng.sample(TRADES, nbills)
        if rng.random() < 0.25:
            ws = self.wb.create_sheet("Cover")
            ws["B3"] = "BILL OF QUANTITIES"
            ws["B5"] = "Project: Private villa, Sobha Hartland"
            ws["B7"] = "Prepared by Infinia Contracting LLC"
            self.feat("cover sheet")
        if rng.random() < 0.2:
            ws = self.wb.create_sheet("Preambles")
            for i in range(3, 40):
                ws.cell(i, 2, rng.choice(["All rates shall include for ...", "The contractor shall allow for ...", "Measurement shall be net as fixed",
                                          LONG]))
            self.feat("preambles sheet")
        summary_first = rng.random() < 0.5
        one_sheet = nbills > 1 and rng.random() < 0.3
        if one_sheet:
            self.feat("many bills on one sheet")
        summary = None
        if nbills > 1 and rng.random() < 0.75:
            summary = self.wb.create_sheet("SUMMARY" if rng.random() < 0.5 else "General Summary")
            self.feat("summary sheet")
        content = [(b, self.items(b, per_bill + rng.randint(-per_bill // 3, per_bill // 3))) for b in bills]
        if one_sheet:
            self.bills.update(self.sheet("BOQ", content, True))
        else:
            for b, it in content:
                self.bills.update(self.sheet(rng.choice([b, b.title(), f"Bill {bills.index(b) + 1}", f"{bills.index(b) + 1}.{b[:10]}"]), [(b, it)], False))
        if summary is not None:
            ws = summary
            ws["A1"] = "GENERAL SUMMARY"
            ws.column_dimensions["A"].width, ws.column_dimensions["B"].width, ws.column_dimensions["C"].width = 9, 45, 18
            ws["A3"], ws["B3"], ws["C3"] = "Bill No", "Description", "Amount (AED)"
            r = 4
            for i, b in enumerate(bills, 1):
                ws.cell(r, 1, i), ws.cell(r, 2, b), ws.cell(r, 3, self.bills[b])
                r += 1
            sub = R2(sum(self.bills.values()))
            ws.cell(r, 2, "Sub-total"), ws.cell(r, 3, sub)
            r += 1
            if rng.random() < 0.3:
                ws.cell(r, 2, "Contingency 5%"), ws.cell(r, 3, R2(sub * 0.05))
                r += 1
                self.feat("contingency on the summary")
            ws.cell(r, 2, "VAT 5%"), ws.cell(r, 3, R2(sub * 0.05))
            ws.cell(r + 1, 2, "GRAND TOTAL INCLUDING VAT"), ws.cell(r + 1, 3, R2(sub * 1.05))
            if not summary_first:
                self.wb.move_sheet(ws, offset=len(self.wb.sheetnames))
            else:
                self.wb.move_sheet(ws, offset=-len(self.wb.sheetnames) + 1)

    def truth(self):
        return {"contract": R2(sum(l["amount"] for l in self.lines)), "bills": self.bills, "lines": self.lines,
                "unpriced": self.unpriced, "features": sorted(self.features), "pc": self.pc}


def recalc(path):
    """Excel's saved values for the formulas: LibreOffice opens and saves the workbook (as Excel itself would)."""
    d = tempfile.mkdtemp()
    subprocess.run(["soffice", "--headless", "--calc", "--convert-to", "xlsx:Calc MS Excel 2007 XML", "--outdir", d, path],
                   capture_output=True, timeout=240)
    out = os.path.join(d, os.path.basename(path))
    if os.path.exists(out):
        shutil.move(out, path)
    shutil.rmtree(d, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--pc", action="store_true")
    ap.add_argument("--big", action="store_true", help="every book long: 8-14 bills of 40-70 items")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for i in range(a.n):
        rng = random.Random(a.seed * 1000 + i)
        b = Book(rng, pc=a.pc)
        if a.big or rng.random() < 0.25:
            nb, per = rng.randint(6, 14), rng.randint(30, 70)
            b.feat("long book")
        else:
            nb, per = rng.randint(1, 5), rng.randint(8, 30)
        b.build(nb, per)
        name = f"{'pc' if a.pc else 'boq'}_{i:02d}"
        p = os.path.join(a.out, name + ".xlsx")
        b.wb.save(p)
        if "figures as formula" in b.features or "figures as mixed" in b.features:
            recalc(p)
        json.dump(b.truth(), open(os.path.join(a.out, name + ".json"), "w"), indent=1)
        print(name, len(b.lines), "lines", R2(sum(l["amount"] for l in b.lines)), "|", ", ".join(sorted(b.features)))


if __name__ == "__main__":
    main()

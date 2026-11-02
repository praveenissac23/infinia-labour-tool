"""Purchasing clean-up form (2 Nov 2026): every order still open on the Order tracker, as a fillable PDF for the
purchaser and the store keeper - one click per line, a remarks box on each - so the months before Arun joined can
be closed once, correctly, and everyone starts from zero.

Built from the tracker itself (purchtrack.build), so it lists exactly what the portal shows as open today:
    A  LPOs still to come (Ordered / part arrived)  - All came / Still coming / Rest not coming / Cancel LPO / Ignore
    B  LPOs arrived, bill not checked               - Bill OK / Bill not received yet / Ignore
    C  Requests with no LPO                          - Still needed / Already came / Not needed / Ignore
Field names carry the order ("LPO 84", "MR 156"), so the filled form is read back and applied line by line.
"""
import io
import os
import re

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (Flowable, Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

RED, DARK, MAROON, GREY, LIGHT = (colors.HexColor("#C0392B"), colors.HexColor("#2E3238"), colors.HexColor("#7B1F1A"),
                                  colors.HexColor("#6B6B6B"), colors.HexColor("#F6F1EF"))
LOGO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")

A_OPTS = [("came", "All came"), ("coming", "Still coming"), ("not_coming", "Rest not coming"), ("cancel", "Cancel LPO"), ("ignore", "Ignore - close")]
B_OPTS = [("bill_ok", "Bill OK"), ("no_bill", "Bill not yet"), ("ignore", "Ignore - close")]
C_OPTS = [("needed", "Still needed"), ("came", "Already came"), ("not_needed", "Not needed"), ("ignore", "Ignore - close")]


def _s(size=8, bold=False, color=DARK, align=0, lead=None):
    return ParagraphStyle("x", fontName="Helvetica-Bold" if bold else "Helvetica", fontSize=size,
                          leading=lead or size * 1.25, textColor=color, alignment=align)


def P(t, **k):
    return Paragraph(t, _s(**k))


def esc(t):
    return (str(t or "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Radio(Flowable):
    """One square radio button (a group allows one choice). Square with a dot reads well on every phone."""
    def __init__(self, group, value, size=9):
        super().__init__()
        self.group, self.value, self.size = group, value, size
        self.width = self.height = size

    def draw(self):
        x, y = self.canv.absolutePosition(0, 0)
        self.canv.acroForm.radio(name=self.group, value=self.value, selected=False, x=x, y=y, size=self.size,
                                 buttonStyle="circle", shape="square", borderWidth=0.8, borderColor=MAROON,
                                 fillColor=colors.white, textColor=RED, forceBorder=True, tooltip=self.value)


class Field(Flowable):
    def __init__(self, name, width, height=12):
        super().__init__()
        self.name, self.width, self.height = name, width, height

    def draw(self):
        x, y = self.canv.absolutePosition(0, 0)
        self.canv.acroForm.textfield(name=self.name, x=x, y=y, width=self.width, height=self.height,
                                     fontName="Helvetica", fontSize=7.5, borderStyle="underlined",
                                     borderColor=colors.HexColor("#B9AEA9"), fillColor=colors.HexColor("#FBF8F6"),
                                     textColor=DARK, borderWidth=0.6, forceBorder=True, tooltip=self.name)


def _cell_radio(group, value):
    t = Table([[Radio(group, value)]], colWidths=[9])
    t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return t


def _late(r):
    return f"{r['late']} days late" if r.get("late") else ""


def build_pdf(data, today, made_by=""):
    rows = [r for r in data["rows"] if r["stage"] < 5]
    A = [r for r in rows if r["kind"] == "lpo" and (r["stage"] == 2 or r["part"])]
    B = [r for r in rows if r["kind"] == "lpo" and r["stage"] in (3, 4) and not r["part"]]
    C = [r for r in rows if r["kind"] == "mr"]
    buf = io.BytesIO()
    page = landscape(A4)
    doc = SimpleDocTemplate(buf, pagesize=page, leftMargin=10 * mm, rightMargin=10 * mm, topMargin=9 * mm,
                            bottomMargin=11 * mm, title="Purchasing clean-up", author="Infinia Contracting L.L.C.")
    W = doc.width
    el = []

    def footer(c, d):
        c.saveState(); c.setFont("Helvetica", 7); c.setFillColor(GREY)
        c.drawString(10 * mm, 6 * mm, f"Infinia Contracting L.L.C. - Purchasing clean-up - open on the Order tracker on {today:%d/%m/%Y}")
        c.drawRightString(page[0] - 10 * mm, 6 * mm, f"Page {d.page}")
        c.restoreState()

    logo = Image(LOGO, width=46 * mm, height=46 * mm * 0.27) if os.path.exists(LOGO) else P("<b>INFINIA</b>", size=14)
    head = Table([[logo, [P("PURCHASING CLEAN-UP", size=15, bold=True, color=MAROON, align=2),
                          P(f"Every order still open in the portal on {today:%d/%m/%Y} - one click each", size=9, color=MAROON, bold=True, align=2)]]],
                 colWidths=[W * 0.4, W * 0.6])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, 0), 1.2, RED),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    el += [head, Spacer(1, 5)]
    el.append(Table([[P("<b>For</b>  Arun (purchaser) and Amal (store keeper)", size=8.5),
                      P("<b>From</b>  Praveen Isaac Shaji", size=8.5),
                      P(f"<b>Open</b>  {len(A)} LPOs to come  |  {len(B)} bills to check  |  {len(C)} requests", size=8.5)]],
                    colWidths=[W * 0.34, W * 0.24, W * 0.42],
                    style=[("BACKGROUND", (0, 0), (-1, -1), LIGHT), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    el.append(Spacer(1, 5))
    el.append(P("Many of these are from before Arun joined, so the portal may not match what really happened - that is expected. "
                "For each line <b>click one box</b>. If you do not know, click <b>Ignore - close</b> and write what you think in Remarks. "
                "Nothing here moves stock or changes an amount by itself: your answers close the paperwork, and anything that needs stock or "
                "money is checked with you first. When it comes back, everything answered is closed and the tracker starts from zero.",
                size=8.5, lead=11.5))
    el.append(Spacer(1, 3))

    def section(title, meaning):
        s = Table([[P(title, size=10, bold=True, color=colors.white), P(meaning, size=7.5, color=colors.white, align=2)]],
                  colWidths=[W * 0.45, W * 0.55])
        s.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), MAROON), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5)]))
        return s

    def table(rows_, opts, cols, cells, key):
        ow = 15 * mm
        fixed = sum(cols) + ow * len(opts)
        rem_w = max(30 * mm, W - fixed)
        widths = cols + [ow] * len(opts) + [rem_w]
        hdr = [P(f"<b>{h}</b>", size=7, color=colors.white) for h in cells[0]] + \
              [P(f"<b>{l}</b>", size=6.6, color=colors.white, align=1) for _, l in opts] + [P("<b>Remarks</b>", size=7, color=colors.white)]
        body = [hdr]
        for r in rows_:
            g = f"{'LPO' if r['kind'] == 'lpo' else 'MR'} {r['id']} {re.sub(r'[^A-Za-z0-9-]+', '-', r['ref'])}"
            body.append(cells[1](r) + [_cell_radio(g, v) for v, _ in opts] + [Field(f"{g} remarks", rem_w - 4 * mm)])
        t = Table(body, colWidths=widths, repeatRows=1)
        n0 = len(cols)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), MAROON), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("ALIGN", (n0, 1), (n0 + len(opts) - 1, -1), "CENTER"),
                               ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CFC6C2")),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
                               ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
                               ("LEFTPADDING", (0, 0), (-1, -1), 2.5), ("RIGHTPADDING", (0, 0), (-1, -1), 2.5)]))
        return t

    lpo_cols = [24 * mm, 14 * mm, 38 * mm, 52 * mm, 44 * mm]
    def lpo_cells(r):
        come = esc(r.get("to_come") or "everything")
        tag = {"site": "site asked to hold", "supplier": "supplier sent less"}.get(r.get("part_why") or "", "")
        return [P(f"<b>{esc(r['ref'])}</b><br/>{r['date'][8:10]}/{r['date'][5:7]}/{r['date'][:4]}" if r.get("date") else f"<b>{esc(r['ref'])}</b>", size=7),
                P(esc(r["site"]), size=7.2),
                P(f"<b>{esc(r['supplier'])}</b>" + (f"<br/>{esc(r['contact'])} {esc(r['phone'])}" if r.get("contact") or r.get("phone") else ""), size=6.8),
                P(esc(r["what"]) + (f"<br/><font color='#888888'>{esc(', '.join(x for x in (r.get('requests') or []) if x != r['ref']))}</font>" if r.get("requests") else ""), size=6.8),
                P(("<font color='#B26A00'><b>Part came.</b></font> " if r["part"] else "<b>Nothing booked yet.</b> ") + f"To come: {come}"
                  + (f" ({tag})" if tag else "") + (f"<br/><font color='#C0392B'>{_late(r)}</font>" if r.get("late") else ""), size=6.8)]
    if A:
        el.append(Spacer(1, 4))
        el.append(section(f"A.  LPOs still to come ({len(A)})", "All came = it arrived, nothing more | Still coming = keep open | Rest not coming = close the rest | Cancel LPO = nothing came / wrong order"))
        el.append(Spacer(1, 2))
        el.append(table(A, A_OPTS, lpo_cols, (["LPO / date", "Site", "Supplier", "What", "As per the portal"], lpo_cells), "A"))

    bill_cols = [24 * mm, 14 * mm, 44 * mm, 70 * mm, 30 * mm]
    def bill_cells(r):
        return [P(f"<b>{esc(r['ref'])}</b>", size=7), P(esc(r["site"]), size=7.2),
                P(f"<b>{esc(r['supplier'])}</b>", size=6.8), P(esc(r["what"]), size=6.8),
                P("Arrived - bill not checked" if r["stage"] == 3 else "Bill checked - not in Zoho", size=6.8)]
    if B:
        el.append(Spacer(1, 6))
        el.append(section(f"B.  Arrived - bill check open ({len(B)})", "Bill OK = the supplier's bill is with accounts and correct | Bill not yet = keep open for the bill"))
        el.append(Spacer(1, 2))
        el.append(table(B, B_OPTS, bill_cols, (["LPO", "Site", "Supplier", "What", "As per the portal"], bill_cells), "B"))

    mr_cols = [22 * mm, 14 * mm, 82 * mm, 50 * mm]
    def mr_cells(r):
        st = {0: "Waiting for approval", 1: "Approved - no LPO yet", 2: "Ordered without an LPO"}.get(r["stage"], "")
        return [P(f"<b>{esc(r['ref'])}</b>", size=7), P(esc(r["site"]), size=7.2),
                P(esc(r["what"]) + (f"<br/><font color='#888888'>by {esc(r.get('requested_by'))}</font>" if r.get("requested_by") else ""), size=6.8),
                P(st + (f"<br/><font color='#C0392B'>{_late(r)}</font>" if r.get("late") else ""), size=6.8)]
    if C:
        el.append(Spacer(1, 6))
        el.append(section(f"C.  Requests not on an LPO ({len(C)})", "Still needed = keep open | Already came = it arrived (petty cash, store, site) | Not needed = close"))
        el.append(Spacer(1, 2))
        el.append(table(C, C_OPTS, mr_cols, (["Request", "Site", "What", "As per the portal"], mr_cells), "C"))

    el.append(Spacer(1, 10))
    sig = Table([[P("Answered by (Arun / Amal) - name and date", size=8), P("Checked by", size=8)],
                 [Field("Answered by", 80 * mm, 14), P("<br/>_______________________<br/>Praveen Isaac Shaji, Managing Partner", size=8)]],
                colWidths=[W / 2, W / 2])
    el.append(KeepTogether([sig]))
    doc.build(el, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue(), {"A": len(A), "B": len(B), "C": len(C)}

"""A payment receipt on paper, in the same family as the tax invoice (invoice_pdf.py): slim red
top line, logo and company top left, PAYMENT RECEIPT top right with its red rule, Received From and
Project panels, the amount received in a band with the amount in words, how it was paid, the tax
invoices it settles (invoice total, received now, balance left), notes, signature, quiet footer."""
import io
import os

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from invoice_pdf import CHAR, DEFAULT_COMPANY, INK, LOGO, MUTED, RED, RULE, TINT, ZEBRA, amount_in_words
from reportlab.lib import colors

GREEN = colors.HexColor("#2E7D32")


def build(r, company=None, signature=None):
    """r: number, date_text, client, client_trn, client_address, project_no, project, location, mode,
    reference, bank, cheque_date_text, amount, allocations [{number, date_text, total, amount, balance}],
    advance (amount not against an invoice), notes, status. Returns a BytesIO holding the PDF."""
    company = {**DEFAULT_COMPANY, **{k: v for k, v in (company or {}).items() if v}}
    buf = io.BytesIO()
    W, H = A4
    M = 16 * mm
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Payment Receipt {r.get('number', '')}")
    c.setAuthor(company["name"])
    money = lambda v: f"{float(v or 0):,.2f}"

    def text(x, y, s, size=9, font="Helvetica", col=INK, align="left", spacing=0):
        s = str(s)
        w = stringWidth(s, font, size) + spacing * max(len(s) - 1, 0)
        x0 = x - (w if align == "right" else w / 2 if align == "center" else 0)
        t = c.beginText(); t.setFont(font, size); t.setCharSpace(spacing); t.setFillColor(col)
        t.setTextOrigin(x0, y); t.textOut(s); c.drawText(t)
        return w

    def label(x, y, s, align="left", col=MUTED):
        text(x, y, s.upper(), 7, "Helvetica-Bold", col, align, spacing=0.8)

    # ---- chrome ------------------------------------------------------------------------------
    c.setFillColor(RED); c.rect(0, H - 1.0 * mm, W, 1.0 * mm, stroke=0, fill=1)
    c.setStrokeColor(RED); c.setLineWidth(0.4); c.line(M, 14 * mm, W - M, 14 * mm)
    text(M, 9.2 * mm, company["name"], 7.8, "Helvetica-Bold", CHAR, spacing=0.8)
    text(M, 5.4 * mm, f"{company['address']}   |   TRN {company['trn']}   |   {company['web']}", 7.2, col=MUTED)
    text(W - M, 7.2 * mm, f"Payment Receipt {r.get('number', '')}", 7.2, col=MUTED, align="right")
    if r.get("status") == "cancelled":
        c.saveState(); c.translate(W / 2, H / 2); c.rotate(32)
        c.setFillColor(RED); c.setFillAlpha(0.13)
        c.setFont("Helvetica-Bold", 96); c.drawCentredString(0, 0, "CANCELLED"); c.restoreState()

    top = H - 17 * mm
    lw = 70 * mm; lh = lw * 168 / 995
    if os.path.exists(LOGO):
        c.drawImage(ImageReader(LOGO), M, top - lh, width=lw, height=lh, mask="auto")
    y = top - lh - 7 * mm
    for i, s in enumerate([company["address"], f"TRN {company['trn']}   |   {company['web']}"]):
        text(M, y - i * 11, s, 8.5, col=MUTED)
    text(W - M, top - 9 * mm, "PAYMENT RECEIPT", 22, "Helvetica-Bold", CHAR, "right", spacing=1.2)
    c.setFillColor(RED); c.rect(W - M - 30 * mm, top - 12.5 * mm, 30 * mm, 0.5 * mm, stroke=0, fill=1)
    meta = [("Receipt No.", r.get("number", "")), ("Date", r.get("date_text", ""))]
    my = top - 20 * mm
    vw = max(stringWidth(str(v), "Helvetica-Bold", 9) for _, v in meta)
    lx = W - M - vw - 6 * mm - max(stringWidth(k, "Helvetica", 8.5) for k, _ in meta)
    for k, v in meta:
        text(lx, my, k, 8.5, col=MUTED)
        text(W - M, my, v, 9, "Helvetica-Bold", INK, "right")
        my -= 12

    # ---- Received From / Project panels -----------------------------------------------------
    py = H - 57 * mm
    bw = (W - 2 * M - 8 * mm) / 2
    frm = [(r.get("client", ""), True)]
    if r.get("client_trn"):
        frm.append((f"TRN {r['client_trn']}", False))
    if r.get("client_address"):
        frm.append((r["client_address"], False))
    proj_head = " - ".join(x for x in ((r.get("project_no") or "").strip(), (r.get("project") or "").strip()) if x)
    proj = [(proj_head or "-", True), (r.get("location", ""), False)]

    def wrapped(rows):
        out = []
        for s, bold in rows:
            if s:
                f, sz = ("Helvetica-Bold", 10) if bold else ("Helvetica", 8.8)
                out += [(ln, bold) for ln in simpleSplit(s, f, sz, bw - 10 * mm)]
        return out
    panels = [("Received From", wrapped(frm)), ("Project", wrapped(proj))]
    step = lambda bold: 12.5 if bold else 11
    need = max(sum(step(b) for _, b in rows) for _, rows in panels)
    ph = max(24 * mm, 13.5 * mm + need - 12.5 + 6 * mm)
    for i, (head, rows) in enumerate(panels):
        x = M + i * (bw + 8 * mm)
        c.setFillColor(TINT); c.roundRect(x, py - ph, bw, ph, 2.2 * mm, stroke=0, fill=1)
        c.setFillColor(RED); c.rect(x, py - ph, 0.6 * mm, ph, stroke=0, fill=1)
        label(x + 6 * mm, py - 7 * mm, head)
        ly = py - 13.5 * mm
        for s, bold in rows:
            text(x + 6 * mm, ly, s, 10 if bold else 8.8, "Helvetica-Bold" if bold else "Helvetica", INK if bold else MUTED)
            ly -= step(bold)
    y = py - ph - 8 * mm

    # ---- the amount received ------------------------------------------------------------------
    bh = 24 * mm
    c.setFillColor(TINT); c.rect(M, y - bh, W - 2 * M, bh, stroke=0, fill=1)
    c.setFillColor(RED); c.rect(M, y - bh, 0.8 * mm, bh, stroke=0, fill=1)
    label(M + 6 * mm, y - 7 * mm, "Amount received")
    text(M + 6 * mm, y - 17 * mm, f"AED {money(r.get('amount'))}", 21, "Helvetica-Bold", CHAR)
    wx = M + 92 * mm
    label(wx, y - 7 * mm, "Amount in words")
    pw = Paragraph(amount_in_words(float(r.get("amount") or 0)),
                   ParagraphStyle("w", fontName="Helvetica-BoldOblique", fontSize=9.2, leading=12, textColor=INK))
    c._charSpace = 0
    _, pwh = pw.wrap(W - M - 8 * mm - wx, bh - 10 * mm)
    text(wx, y - 9.5 * mm, "", 9, spacing=0)      # letter spacing back to normal for the paragraph
    c._charSpace = 0
    pw.drawOn(c, wx, y - 9.5 * mm - pwh)
    y -= bh + 9 * mm

    # ---- how it was paid ------------------------------------------------------------------------
    label(M, y, "Payment details")
    y -= 3 * mm
    rows = [("Payment mode", r.get("mode") or "-"), ("Reference / cheque no.", r.get("reference") or "-")]
    if r.get("bank"):
        rows.append(("Bank", r["bank"]))
    if r.get("cheque_date_text"):
        rows.append(("Cheque date", r["cheque_date_text"]))
    cw = (W - 2 * M) / 2
    for i, (k, v) in enumerate(rows):
        x = M + (i % 2) * cw
        yy = y - (i // 2) * 11 * mm
        text(x, yy - 5 * mm, k, 8.3, col=MUTED)
        text(x, yy - 9.6 * mm, v, 10, "Helvetica-Bold", INK)
        c.setStrokeColor(RULE); c.setLineWidth(0.6); c.line(x, yy - 11.5 * mm, x + cw - 6 * mm, yy - 11.5 * mm)
    y -= ((len(rows) + 1) // 2) * 11 * mm + 9 * mm

    # ---- the invoices it settles ------------------------------------------------------------------
    allocs = r.get("allocations") or []
    adv = float(r.get("advance") or 0)
    if allocs or adv:
        label(M, y, "Received against")
        y -= 3 * mm
        cols = [("Tax invoice", 0, "left"), ("Invoice date", 28 * mm, "left"), ("Invoice total", 32 * mm, "right"),
                ("Received now", 32 * mm, "right"), ("Balance due", 30 * mm, "right")]
        tw = W - 2 * M
        cols[0] = ("Tax invoice", tw - sum(w for _, w, _ in cols), "left")
        xs = [M]
        for _, w, _ in cols:
            xs.append(xs[-1] + w)
        hh = 8.5 * mm
        c.setFillColor(TINT); c.rect(M, y - hh, tw, hh, stroke=0, fill=1)
        c.setFillColor(RED); c.rect(M, y - hh, tw, 0.35 * mm, stroke=0, fill=1)
        for (name, w, al), x0 in zip(cols, xs):
            tx = x0 + 3 * mm if al == "left" else x0 + w - 3 * mm
            text(tx, y - hh + 3.3 * mm, name.upper(), 7.3, "Helvetica-Bold", CHAR, al, spacing=0.6)
        y -= hh
        lines = [(a.get("number", ""), a.get("date_text", ""), money(a.get("total")), money(a.get("amount")),
                  money(a.get("balance")) if float(a.get("balance") or 0) > 0.004 else "Paid in full") for a in allocs]
        if adv > 0.004:
            lines.append(("Advance / not against an invoice", "", "", money(adv), ""))
        for i, cells in enumerate(lines):
            rh = 7.6 * mm
            if i % 2 == 1:
                c.setFillColor(ZEBRA); c.rect(M, y - rh, tw, rh, stroke=0, fill=1)
            for k, ((name, w, al), x0, s) in enumerate(zip(cols, xs, cells)):
                tx = x0 + 3 * mm if al == "left" else x0 + w - 3 * mm
                bold = k in (0, 3)
                col = GREEN if s == "Paid in full" else INK
                text(tx, y - 4.9 * mm, s, 8.8, "Helvetica-Bold" if bold or s == "Paid in full" else "Helvetica", col, al)
            c.setStrokeColor(RULE); c.setLineWidth(0.6); c.line(M, y - rh, M + tw, y - rh)
            y -= rh
        c.setStrokeColor(CHAR); c.setLineWidth(1.0); c.line(M, y, M + tw, y)
        text(xs[3] - 3 * mm, y - 5 * mm, "Total received", 8.5, "Helvetica-Bold", MUTED, "right")
        text(xs[4] - 3 * mm, y - 5 * mm, money(r.get("amount")), 9.5, "Helvetica-Bold", CHAR, "right")
        y -= 12 * mm

    # ---- notes ---------------------------------------------------------------------------------------
    notes = [n for n in [r.get("notes") or ""] if n.strip()]
    if (r.get("mode") or "").lower().startswith("cheque"):
        notes.append("This receipt is valid subject to the cheque being honoured by the bank.")
    if notes:
        label(M, y, "Notes")
        y -= 5 * mm
        for n in notes:
            for ln in simpleSplit(n, "Helvetica-Oblique", 8.8, W - 2 * M):
                text(M, y, ln, 8.8, "Helvetica-Oblique", INK)
                y -= 11
            y -= 2

    # ---- signatures at the foot ------------------------------------------------------------------------
    by = 46 * mm
    c.setStrokeColor(RULE); c.setLineWidth(0.6); c.line(M, by + 18 * mm, W - M, by + 18 * mm)
    label(M, by + 13 * mm, "Received with thanks")
    text(M, by + 8 * mm, f"AED {money(r.get('amount'))} from {r.get('client', '')}"[:95], 8.6, col=MUTED)
    sx = W - M - 70 * mm
    label(sx, by + 13 * mm, f"For {company['name']}")
    if signature and os.path.exists(signature):
        try:
            from PIL import Image
            iw, ih = Image.open(signature).size
            sh = 16 * mm
            c.drawImage(ImageReader(signature), sx, by - 4 * mm, width=sh * iw / ih, height=sh, mask="auto")
        except Exception:
            pass
    c.setStrokeColor(CHAR); c.setLineWidth(0.6); c.line(sx, by - 6 * mm, W - M, by - 6 * mm)
    text(sx, by - 10.5 * mm, "Authorised Signatory", 8, "Helvetica-Bold", INK)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf

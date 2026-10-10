"""Tax and proforma invoices on paper - the professional layout agreed for
IC/26/906/PHASE2-10: logo top left, the title top right with its red
rule, Bill To and Project panels, the line table (net, VAT %, VAT,
total), subtotal / VAT / TOTAL DUE, amount in words, payment details,
signature and stamp, a dark footer.

A long invoice runs onto further pages with the table heading repeated;
the totals, payment details and signature always sit together on the
last page.
"""
import io
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

HERE = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(HERE, "logo.png")

RED = colors.HexColor("#C0392B")
INK = colors.HexColor("#1F2429")
CHAR = colors.HexColor("#2E3238")
MUTED = colors.HexColor("#6B7178")
RULE = colors.HexColor("#E3E0DC")
TINT = colors.HexColor("#F7F5F3")
ZEBRA = colors.HexColor("#FAF9F8")

DEFAULT_COMPANY = {"name": "INFINIA CONTRACTING L.L.C.",
                   "address": "M09, Bin Bishr Building, Abu Hail, Dubai, UAE",
                   "trn": "100602393900003", "web": "www.infinia.ae"}
DEFAULT_BANK = [("Bank", "Abu Dhabi Commercial Bank"), ("Account Name", "Infinia Contracting LLC"),
                ("Account No.", "12526725920002"), ("IBAN", "AE10 0030 0125 2672 5920 002"),
                ("SWIFT", "ADCBAEAA"), ("Branch", "Al Riggah")]

_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven",
         "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _words(n):
    n = int(n)
    if n == 0:
        return "Zero"
    out = []
    for value, name in ((10 ** 9, "Billion"), (10 ** 6, "Million"), (1000, "Thousand"), (1, "")):
        if n >= value:
            chunk, n = divmod(n, value)
            h, r = divmod(chunk, 100)
            part = []
            if h:
                part.append(_ONES[h] + " Hundred")
            if r:
                part.append(_ONES[r] if r < 20 else _TENS[r // 10] + ("-" + _ONES[r % 10] if r % 10 else ""))
            out.append(" ".join(part) + (" " + name if name else ""))
    return " ".join(out)


def amount_in_words(v):
    """70293.95 -> 'UAE Dirhams Seventy Thousand Two Hundred Ninety-Three
    and Fils Ninety-Five Only'."""
    v = round(float(v) + 1e-9, 2)
    dh = int(v)
    fils = int(round((v - dh) * 100))
    s = f"UAE Dirhams {_words(dh)}"
    if fils:
        s += f" and Fils {_words(fils)}"
    return s + " Only"


def totals(lines):
    sub = vat = 0.0
    for l in lines:
        a = round(float(l.get("amount") or 0), 2)
        sub += a
        vat += round(a * float(l.get("vat") or 0) / 100, 2)
    sub, vat = round(sub, 2), round(vat, 2)
    return sub, vat, round(sub + vat, 2)


def build(inv, company=None, bank=None, signature=None):
    """inv: kind ('tax'|'proforma'), number, date_text, client, client_trn,
    client_address, project, plot, location, work, lines [{description,
    amount, vat}], status. Returns a BytesIO holding the PDF."""
    company = {**DEFAULT_COMPANY, **{k: v for k, v in (company or {}).items() if v}}
    bank = bank or DEFAULT_BANK
    proforma = inv.get("kind") == "proforma"
    title = "PROFORMA INVOICE" if proforma else "TAX INVOICE"
    lines = [l for l in (inv.get("lines") or []) if (l.get("description") or "").strip() or l.get("amount")]
    sub, vat, total = totals(lines)

    buf = io.BytesIO()
    W, H = A4
    M = 16 * mm
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"{title.title()} {inv.get('number', '')}")
    c.setAuthor(company["name"])
    money = lambda v: f"{v:,.2f}"

    def text(x, y, s, size=9, font="Helvetica", col=INK, align="left", spacing=0):
        s = str(s)
        w = stringWidth(s, font, size) + spacing * max(len(s) - 1, 0)
        x0 = x - (w if align == "right" else w / 2 if align == "center" else 0)
        t = c.beginText(); t.setFont(font, size); t.setCharSpace(spacing); t.setFillColor(col)
        t.setTextOrigin(x0, y); t.textOut(s); c.drawText(t)
        return w

    def label(x, y, s, align="left"):
        text(x, y, s.upper(), 7, "Helvetica-Bold", MUTED, align, spacing=0.8)

    pages = [0]

    def chrome(first):
        """Accent bar, footer and - on page one - the full header."""
        # Light touches only: a slim red line across the top, and the
        # footer as quiet grey text over a hairline - no dark bands.
        c.setFillColor(RED); c.rect(0, H - 1.0 * mm, W, 1.0 * mm, stroke=0, fill=1)
        c.setStrokeColor(RED); c.setLineWidth(0.4); c.line(M, 14 * mm, W - M, 14 * mm)
        text(M, 9.2 * mm, company["name"], 7.8, "Helvetica-Bold", CHAR, spacing=0.8)
        text(M, 5.4 * mm, f"{company['address']}   |   TRN {company['trn']}   |   {company['web']}", 7.2, col=MUTED)
        foot = "Not a tax invoice" if proforma else f"{title.title()} {inv.get('number', '')}"
        text(W - M, 7.2 * mm, foot, 7.2, col=MUTED, align="right")
        if inv.get("status") == "cancelled":
            c.saveState(); c.translate(W / 2, H / 2); c.rotate(32)
            c.setFillColor(colors.HexColor("#C0392B")); c.setFillAlpha(0.13)
            c.setFont("Helvetica-Bold", 96); c.drawCentredString(0, 0, "CANCELLED"); c.restoreState()
        top = H - 17 * mm
        if not first:
            lw = 42 * mm; lh = lw * 168 / 995
            if os.path.exists(LOGO):
                c.drawImage(ImageReader(LOGO), M, top - lh, width=lw, height=lh, mask="auto")
            text(W - M, top - 5 * mm, f"{title}  {inv.get('number', '')}  (continued)", 10, "Helvetica-Bold", CHAR, "right")
            return top - lh - 8 * mm
        lw = 70 * mm; lh = lw * 168 / 995
        if os.path.exists(LOGO):
            c.drawImage(ImageReader(LOGO), M, top - lh, width=lw, height=lh, mask="auto")
        y = top - lh - 7 * mm
        for i, s in enumerate([company["address"], f"TRN {company['trn']}   |   {company['web']}"]):
            text(M, y - i * 11, s, 8.5, col=MUTED)
        text(W - M, top - 9 * mm, title, 25 if not proforma else 22, "Helvetica-Bold", CHAR, "right", spacing=1.2)
        c.setFillColor(RED); c.rect(W - M - 30 * mm, top - 12.5 * mm, 30 * mm, 0.5 * mm, stroke=0, fill=1)
        meta = [("Proforma No." if proforma else "Invoice No.", inv.get("number", "")),
                ("Date" if proforma else "Invoice Date", inv.get("date_text", ""))]
        my = top - 20 * mm
        for k, v in meta:
            text(W - M - 62 * mm, my, k, 8.5, col=MUTED)
            text(W - M, my, v, 9, "Helvetica-Bold", INK, "right")
            my -= 12
        # Bill To and Project panels
        py = H - 57 * mm
        bw = (W - 2 * M - 8 * mm) / 2
        bill = [(inv.get("client", ""), True)]
        if inv.get("client_trn"):
            bill.append((f"TRN {inv['client_trn']}", False))
        if inv.get("client_address"):
            bill.append((inv["client_address"], False))
        proj_head = "  -  ".join(x for x in ((inv.get("project", "") or "").strip().rstrip("-").strip(),
                                             (f"Plot No. {inv['plot']}" if inv.get("plot") else "")) if x)
        proj = [(proj_head, True), (inv.get("location", ""), False), (inv.get("work", ""), False)]
        for i, (head, rows) in enumerate((("Bill To", bill), ("Project", proj))):
            x = M + i * (bw + 8 * mm)
            c.setFillColor(TINT); c.roundRect(x, py - 24 * mm, bw, 24 * mm, 2.2 * mm, stroke=0, fill=1)
            c.setFillColor(RED); c.rect(x, py - 24 * mm, 0.6 * mm, 24 * mm, stroke=0, fill=1)
            label(x + 6 * mm, py - 7 * mm, head)
            ly = py - 13.5 * mm
            for s, bold in rows[:3]:
                if s:
                    s = simpleSplit(s, "Helvetica-Bold" if bold else "Helvetica", 10 if bold else 8.8, bw - 10 * mm)[0]
                    text(x + 6 * mm, ly, s, 10 if bold else 8.8, "Helvetica-Bold" if bold else "Helvetica", INK if bold else MUTED)
                ly -= 12.5
        return py - 31 * mm

    # ---- the line table, page by page ------------------------------------------
    cols = [("#", 8 * mm, "center"), ("Description", 0, "left"), ("Net Amount", 27 * mm, "right"),
            ("VAT %", 14 * mm, "right"), ("VAT", 22 * mm, "right"), ("Total (AED)", 28 * mm, "right")]
    tw = W - 2 * M
    cols[1] = ("Description", tw - sum(w for _, w, _ in cols), "left")
    xs = [M]
    for _, w, _ in cols:
        xs.append(xs[-1] + w)

    def col_rules(top, bot):
        """The table stays open - no column lines; it only runs down to
        the closing block so every invoice sits the same on the page."""
        return

    def head_row(ty):
        hh = 9 * mm
        c.setFillColor(TINT); c.rect(M, ty - hh, tw, hh, stroke=0, fill=1)
        c.setFillColor(RED); c.rect(M, ty - hh, tw, 0.35 * mm, stroke=0, fill=1)
        for (name, w, al), x0 in zip(cols, xs):
            tx = x0 + 3 * mm if al == "left" else x0 + w - 3 * mm if al == "right" else x0 + w / 2
            text(tx, ty - hh + 3.6 * mm, name.upper(), 7.5, "Helvetica-Bold", CHAR, al, spacing=0.6)
        return ty - hh

    FOOT_ROOM = 22 * mm           # above the footer band
    # The closing block - totals, amount in words, payment details and the
    # signature - measured before anything is drawn, so the line table can
    # run down to meet it: one line or twenty, every invoice fills its A4
    # page the same way an LPO does.
    tx0 = W - M - 78 * mm
    lwid = tx0 - M - 10 * mm
    pw = Paragraph(amount_in_words(total), ParagraphStyle("w", fontName="Helvetica-BoldOblique", fontSize=9.2,
                                                          leading=12.5, textColor=INK))
    _, ph = pw.wrap(lwid, 40 * mm)
    sig_wh = None
    if signature and os.path.exists(signature):
        try:
            from PIL import Image
            iw, ih = Image.open(signature).size
            sh_ = min(54 * mm * ih / iw, 34 * mm)
            sig_wh = (sh_ * iw / ih, sh_)
        except Exception:
            sig_wh = None
    sh = sig_wh[1] if sig_wh else 30 * mm
    bhgt = 9 * mm + 13 + len(bank) * 11 + 3
    totals_drop = 8 * mm + 26 + 2 + 13 * mm - 5
    head_drop = max(totals_drop, 11 * mm + ph) + 9 * mm
    END_ROOM = head_drop + max(bhgt, 11.5 * mm + sh + 4) + 6 * mm
    ry = head_row(chrome(True))
    table_top = ry
    for i, l in enumerate(lines, 1):
        d = str(l.get("description") or "")
        wrapped = simpleSplit(d, "Helvetica", 8.8, cols[1][1] - 6 * mm) or [""]
        rh = max(7.8 * mm, (len(wrapped) * 11) + 4.6 * mm)
        need_after = END_ROOM if i == len(lines) else 0
        if ry - rh < FOOT_ROOM + need_after:
            col_rules(table_top, ry)
            c.showPage(); pages[0] += 1
            ry = head_row(chrome(False)); table_top = ry
        a = round(float(l.get("amount") or 0), 2)
        pc = float(l.get("vat") or 0)
        v = round(a * pc / 100, 2)
        if i % 2 == 0:
            c.setFillColor(ZEBRA); c.rect(M, ry - rh, tw, rh, stroke=0, fill=1)
        base = ry - 4.7 * mm
        pct = f"{pc:g}%"
        cells = [str(i), None, money(a), pct, money(v), money(a + v)]
        for k, ((name, w, al), x0, s) in enumerate(zip(cols, xs, cells)):
            tx = x0 + 3 * mm if al == "left" else x0 + w - 3 * mm if al == "right" else x0 + w / 2
            if k == 1:
                for j, ln in enumerate(wrapped):
                    text(tx, base - j * 11, ln, 8.8)
            else:
                text(tx, base, s, 8.8, "Helvetica-Bold" if k == 5 else "Helvetica", MUTED if k == 0 else INK, al)
        c.setStrokeColor(RULE); c.setLineWidth(0.6); c.line(M, ry - rh, M + tw, ry - rh)
        ry -= rh
    if not lines:
        text(M + 4 * mm, ry - 6 * mm, "No lines.", 9, col=MUTED); ry -= 9 * mm
    if ry < FOOT_ROOM + END_ROOM:
        col_rules(table_top, ry)
        c.showPage(); pages[0] += 1
        ry = chrome(False); table_top = None
    # The table runs on down to the closing block.
    bottom = FOOT_ROOM + END_ROOM
    if table_top is not None and ry > bottom:
        ry = bottom
    if table_top is not None:
        col_rules(table_top, ry)
    c.setStrokeColor(CHAR); c.setLineWidth(1.2); c.line(M, ry, M + tw, ry)

    # ---- totals ----------------------------------------------------------------
    yy = ry - 8 * mm
    for k, v in (("Subtotal (excl. VAT)", money(sub)), ("VAT", money(vat))):
        text(tx0 + 4 * mm, yy, k, 8.8, col=MUTED)
        text(W - M - 4 * mm, yy, v, 9, "Helvetica", INK, "right")
        yy -= 13
    yy -= 2
    bh = 13 * mm
    c.setStrokeColor(CHAR); c.setLineWidth(1.2); c.line(tx0, yy + 6, W - M, yy + 6)
    c.setFillColor(TINT); c.rect(tx0, yy - bh + 5, 78 * mm, bh, stroke=0, fill=1)
    c.setFillColor(RED); c.rect(tx0, yy - bh + 5, 0.6 * mm, bh, stroke=0, fill=1)
    text(tx0 + 5 * mm, yy - bh / 2 + 3, "TOTAL" if proforma else "TOTAL DUE", 8, "Helvetica-Bold", MUTED, spacing=1)
    text(W - M - 4 * mm, yy - bh / 2 + 0.5, f"AED {money(total)}", 15, "Helvetica-Bold", CHAR, "right")
    totals_bottom = yy - bh + 5

    # ---- amount in words -------------------------------------------------------
    label(M, ry - 8 * mm, "Amount in words")
    text(M, ry - 11 * mm, "", 9, spacing=0)      # letter spacing back to normal for the paragraph
    c._charSpace = 0
    pw.drawOn(c, M, ry - 11 * mm - ph)

    # ---- payment details + signature ---------------------------------------------
    by = min(totals_bottom, ry - 11 * mm - ph) - 9 * mm
    bwid = 96 * mm
    c.setFillColor(TINT); c.roundRect(M, by - bhgt, bwid, bhgt, 2 * mm, stroke=0, fill=1)
    c.setFillColor(RED); c.rect(M, by - bhgt, 0.6 * mm, bhgt, stroke=0, fill=1)
    text(M + 5 * mm, by - 6 * mm, "PAYMENT DETAILS", 7.5, "Helvetica-Bold", RED, spacing=0.8)
    yb = by - 9 * mm - 13
    for k, v in bank:
        text(M + 5 * mm, yb, k, 8.3, col=MUTED)
        text(M + 32 * mm, yb, v, 8.6, "Helvetica-Bold", INK)
        yb -= 11
    sx = W - M - 70 * mm
    label(sx, by - 2 * mm, f"For {company['name']}")
    if sig_wh:
        try:
            c.drawImage(ImageReader(signature), sx, by - 5 * mm - sh, width=sig_wh[0], height=sh, mask="auto")
        except Exception:
            pass
    c.setStrokeColor(CHAR); c.setLineWidth(0.6); c.line(sx, by - 7 * mm - sh, W - M, by - 7 * mm - sh)
    text(sx, by - 11.5 * mm - sh, "Authorised Signatory", 8, "Helvetica-Bold", INK)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf

"""Admin > Forms: the company's blank HR forms, one A4 page each, drawn in
the same style as the invoices - logo top left, title top right with its
red rule, quiet footer. Only what is needed on each form: boxes to write
in, tick boxes, an office-use panel and the signatures together at the
foot of the page.
"""
import io
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

HERE = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(HERE, "logo.png")
HINDI = os.path.join(HERE, "form_hindi.png")

RED = colors.HexColor("#C0392B")
INK = colors.HexColor("#1F2429")
CHAR = colors.HexColor("#2E3238")
MUTED = colors.HexColor("#6B7178")
RULE = colors.HexColor("#D9D5D0")
TINT = colors.HexColor("#F7F5F3")

COMPANY = {"name": "INFINIA CONTRACTING L.L.C.", "address": "M09, Bin Bishr Building, Abu Hail, Dubai, UAE",
           "trn": "100602393900003", "web": "www.infinia.ae"}

EMP = lambda place="Department": [[("Full name", 3), ("Employee code", 1.2)], [("Job title", 2), (place, 2)]]

# key -> the form. Rows: list of (label, width weight) boxes, or a dict:
#   {"check": label, "opts": [...]}  tick boxes in one box
#   {"tall": label}                  a box with room for a sentence
#   {"say": text}                    a line of print (declarations)
FORMS = {
    "leave_office": {
        "no": "IC/HR/F01", "title": "LEAVE APPLICATION", "tag": "Office staff",
        "intro": "Hand in at least 30 days before the leave. Do not book tickets until this form is approved.",
        "sections": [
            ("Employee", False, EMP("Department")),
            ("Leave requested", False, [
                [{"check": "Type of leave", "opts": ["Annual", "Emergency", "Sick", "Unpaid", "Other"]}],
                [("From", 1), ("To", 1), ("No. of days", 0.7), ("Contact number during leave", 1.6)],
                [{"tall": "Reason (for emergency / other leave)"}],
                [("Work handed over to", 1)]]),
            ("Travel", False, [
                [{"check": "Air ticket", "opts": ["Paid by company", "Own ticket", "Not travelling"]}],
                [("Departure date", 1), ("Return date", 1), ("Destination", 1.4)]]),
            ("Office use", True, [
                [("Date joined", 1), ("Last leave taken", 1), ("Leave balance (days)", 1), ("Approved days", 1)],
                [("Returned to work on", 1), ("Remarks", 3)]]),
        ],
        "sign": ["Employee", "HR Manager", "Managing Director"],
    },
    "leave_site": {
        "no": "IC/HR/F02", "title": "LEAVE APPLICATION", "tag": "Site staff",
        "intro": "Hand in at least 30 days before the leave. Do not book tickets until this form is approved.",
        "sections": [
            ("Employee", False, EMP("Site / project")),
            ("Leave requested", False, [
                [{"check": "Type of leave", "opts": ["Annual", "Emergency", "Other"]}],
                [("From", 1), ("To", 1), ("No. of days", 0.7), ("Contact number during leave", 1.6)],
                [{"tall": "Reason (for emergency / other leave)"}]]),
            ("Travel", False, [
                [{"check": "Air ticket", "opts": ["Paid by company", "Own ticket", "Not travelling"]}],
                [("Departure date", 1), ("Return date", 1), ("Destination", 1.4)]]),
            ("Office use", True, [
                [("Date joined", 1), ("Last leave taken", 1), ("Leave balance (days)", 1), ("Approved days", 1)],
                [("Returned to work on", 1), ("Remarks", 3)]]),
        ],
        "sign": ["Employee", "Site Engineer", "PRO", "HR Manager"],
    },
    "passport_release": {
        "no": "IC/HR/F03", "title": "PASSPORT RELEASE", "tag": "Passport given to the employee",
        "intro": "Filled in when a passport kept by the office is handed to the employee.",
        "sections": [
            ("Employee", False, EMP("Site / department")),
            ("Release", False, [
                [("Passport no.", 1.2), ("Passport expiry", 1), ("Date given", 1), ("To be returned by", 1)],
                [{"check": "Purpose", "opts": ["Vacation", "Visa / Emirates ID", "Bank", "Travel", "Other"]}]]),
            ("Returned to office", True, [
                [("Date returned", 1), ("Received by (HR)", 1.6), ("Signature", 1.2)]]),
        ],
        "note": "The employee is responsible for the passport while it is with him and returns it to HR as soon as the purpose is complete.",
        "sign": ["Employee (received)", "HR Manager (released)"],
    },
    "passport_submit": {
        "no": "IC/HR/F04", "title": "PASSPORT SUBMISSION", "tag": "Passport handed to the office",
        "intro": "Filled in when an employee hands his passport to the office for safekeeping.",
        "sections": [
            ("Employee", False, EMP("Site / department")),
            ("Passport", False, [
                [("Passport no.", 1.2), ("Nationality", 1), ("Expiry date", 1), ("Date handed in", 1)]]),
            ("Declaration", False, [
                [{"say": "I hand over my passport to Infinia Contracting L.L.C. for safekeeping, of my own free will. "
                         "I can ask for it back at any time by filling in a Passport Release form."}]]),
        ],
        "sign": ["Employee", "HR Manager (received)"],
    },
    "visa_renewal": {
        "no": "IC/HR/F05", "title": "VISA RENEWAL CONFIRMATION", "tag": "Labour",
        "intro": "Filled in before a labour visa is renewed. Salary is filled in by the office.",
        "sections": [
            ("Employee", False, [[("Full name", 3), ("Employee code", 1.2)], [("Job title", 2), ("Site / project", 2)],
                                 [("Joining date", 1), ("Emirates ID no.", 1.5), ("Labour card no.", 1.5)]]),
            ("Salary (office use)", True, [[("Current salary (AED)", 1), ("Increment (AED)", 1), ("New salary (AED)", 1)]]),
            ("Declaration", False, [
                [{"say": "I confirm the salary shown above is correct and I agree to the renewal of my visa."}],
                [{"hindi": True}]]),
        ],
        "sign": ["Employee", "Site Engineer", "Project Manager", "PRO"],
    },
}
FORMS["transmittal"] = {
    "no": "IC/AD/F06", "title": "DOCUMENT TRANSMITTAL", "tag": "Site to office",
    "intro": "Delivery notes and site documents sent to the office. One line per document.",
    "sections": [
        ("Details", False, [[("Transmittal no.", 1), ("Date", 1), ("From site / project", 2.2)]]),
        ("Documents", False, [[{"table": [("No.", 0.45), ("Description", 3.0), ("Delivery note no.", 1.45),
                                          ("Site", 0.8), ("Date", 0.95), ("Remarks", 1.55)]}]]),
        ("Declaration", False, [[{"say": "I confirm the documents listed above are handed over to the office for further action."}]]),
    ],
    "sign": ["Site Accountant (sent)", "Office Admin (received)"],
}
ORDER = ["leave_office", "leave_site", "passport_release", "passport_submit", "visa_renewal", "transmittal"]
REV = "Rev. 01"


def title_of(key):
    f = FORMS[key]
    return f"{f['title'].title()} - {f['tag']}"


def build(key, company=None):
    f = FORMS[key]
    co = {**COMPANY, **{k: v for k, v in (company or {}).items() if v}}
    buf = io.BytesIO()
    W, H = A4
    M = 16 * mm
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(title_of(key)); c.setAuthor(co["name"])

    def text(x, y, s, size=9, font="Helvetica", col=INK, align="left", spacing=0):
        s = str(s)
        w = stringWidth(s, font, size) + spacing * max(len(s) - 1, 0)
        x0 = x - (w if align == "right" else w / 2 if align == "center" else 0)
        t = c.beginText(); t.setFont(font, size); t.setCharSpace(spacing); t.setFillColor(col)
        t.setTextOrigin(x0, y); t.textOut(s); c.drawText(t)
        return w

    # ---- header and footer -------------------------------------------------
    c.setFillColor(RED); c.rect(0, H - 1.0 * mm, W, 1.0 * mm, stroke=0, fill=1)
    top = H - 15 * mm
    lw = 62 * mm; lh = lw * 168 / 995
    if os.path.exists(LOGO):
        c.drawImage(ImageReader(LOGO), M, top - lh, width=lw, height=lh, mask="auto")
    size = 19 if len(f["title"]) < 20 else 16
    text(W - M, top - 6.5 * mm, f["title"], size, "Helvetica-Bold", CHAR, "right", spacing=1.0)
    c.setFillColor(RED); c.rect(W - M - 26 * mm, top - 9.6 * mm, 26 * mm, 0.5 * mm, stroke=0, fill=1)
    text(W - M, top - 15 * mm, f["tag"], 9.5, "Helvetica", MUTED, "right")
    text(M, top - lh - 5.5 * mm, f"Doc No. {f['no']}   |   {REV}", 7.6, "Helvetica", MUTED)
    c.setStrokeColor(RED); c.setLineWidth(0.4); c.line(M, 14 * mm, W - M, 14 * mm)
    text(M, 9.2 * mm, co["name"], 7.8, "Helvetica-Bold", CHAR, spacing=0.8)
    text(M, 5.4 * mm, f"{co['address']}   |   TRN {co['trn']}   |   {co['web']}", 7.2, col=MUTED)
    text(W - M, 7.2 * mm, f"{f['no']}  {REV}", 7.2, col=MUTED, align="right")

    BODY_TOP = top - 25 * mm
    TABLE = [0]
    FOOT_TOP = 14 * mm
    SIG_H = 34 * mm          # the signature block: heading, room to sign, names

    def layout(draw, grow, gap_add):
        """Draw (or just measure) the body. grow = extra height for each
        writing box, gap_add = extra space after each section."""
        st = {"y": BODY_TOP, "rows": TABLE[0]}
        GAP = 3.2 * mm
        BOX = 12.5 * mm + grow

        def T(*a, **k):
            return text(*a, **k) if draw else stringWidth(str(a[2]), k.get("font", a[4] if len(a) > 4 else "Helvetica"), k.get("size", a[3] if len(a) > 3 else 9))

        def section(title):
            y = st["y"]
            if draw:
                c.setFillColor(RED); c.rect(M, y - 0.4 * mm, 2.2 * mm, 2.2 * mm, stroke=0, fill=1)
                w = text(M + 4.2 * mm, y, title.upper(), 8, "Helvetica-Bold", CHAR, spacing=1.0)
                c.setStrokeColor(RULE); c.setLineWidth(0.5)
                c.line(M + 6.5 * mm + w, y + 1.0 * mm, W - M, y + 1.0 * mm)
            st["y"] -= 5 * mm

        def box(x, w, h, label, office):
            if not draw:
                return
            y = st["y"]
            c.setLineWidth(0.6); c.setStrokeColor(RULE)
            c.setFillColor(TINT if office else colors.white)
            c.roundRect(x, y - h, w, h, 1.6 * mm, stroke=1, fill=1)
            text(x + 2.6 * mm, y - 3.6 * mm, label.upper(), 6.4, "Helvetica-Bold", MUTED, spacing=0.5)

        def row(r, office):
            tw = W - 2 * M
            if isinstance(r[0], dict):
                d = r[0]
                if "check" in d:
                    h = 10.5 * mm
                    box(M, tw, h, d["check"], office)
                    if draw:
                        y = st["y"]
                        x = max(M + 2.6 * mm + stringWidth(d["check"].upper(), "Helvetica-Bold", 6.4) + 0.5 * len(d["check"]) + 7 * mm, M + 30 * mm)
                        for o in d["opts"]:
                            c.setStrokeColor(CHAR); c.setLineWidth(0.7); c.setFillColor(colors.white)
                            c.roundRect(x, y - 7.3 * mm, 3.6 * mm, 3.6 * mm, 0.6 * mm, stroke=1, fill=1)
                            ow = text(x + 5.4 * mm, y - 6.6 * mm, o, 9, "Helvetica", INK)
                            if o == "Other":
                                end = min(x + 6.4 * mm + ow + 30 * mm, M + tw - 4 * mm)
                                c.setStrokeColor(RULE); c.setLineWidth(0.6)
                                c.line(x + 6.4 * mm + ow, y - 7.0 * mm, end, y - 7.0 * mm)
                            x += 5.4 * mm + ow + 8 * mm
                    st["y"] -= h + GAP
                elif "tall" in d:
                    h = 17 * mm + grow * 1.5
                    box(M, tw, h, d["tall"], office); st["y"] -= h + GAP
                elif "say" in d:
                    lines = simpleSplit(d["say"], "Helvetica", 9.4, tw - 4 * mm)
                    if draw:
                        for k, s in enumerate(lines):
                            text(M + 2 * mm, st["y"] - 3.4 * mm - k * 4.6 * mm, s, 9.4, "Helvetica", INK)
                    st["y"] -= 3.4 * mm + len(lines) * 4.6 * mm + 1.5 * mm
                elif "table" in d:
                    cols = d["table"]; tot = sum(wt for _, wt in cols)
                    HH, RH = 7 * mm, 7.4 * mm
                    n = st.get("rows", 0)
                    h = HH + n * RH
                    if draw:
                        y = st["y"]
                        c.setFillColor(CHAR); c.roundRect(M, y - HH, tw, HH, 1.4 * mm, stroke=0, fill=1)
                        c.rect(M, y - HH, tw, HH / 2, stroke=0, fill=1)
                        xs = [M]
                        for label, wt in cols:
                            xs.append(xs[-1] + tw * wt / tot)
                        for k, (label, wt) in enumerate(cols):
                            text(xs[k] + 2.2 * mm, y - 4.6 * mm, label.upper(), 6.6, "Helvetica-Bold", colors.white, spacing=0.4)
                        for i in range(n):
                            yt = y - HH - i * RH
                            if i % 2:
                                c.setFillColor(TINT); c.rect(M, yt - RH, tw, RH, stroke=0, fill=1)
                            text(xs[0] + 2.2 * mm, yt - 4.9 * mm, str(i + 1), 8, "Helvetica", MUTED)
                        c.setStrokeColor(RULE); c.setLineWidth(0.5)
                        for i in range(n + 1):
                            c.line(M, y - HH - i * RH, M + tw, y - HH - i * RH)
                        for xx in xs[1:-1]:
                            c.line(xx, y - HH, xx, y - h)
                        c.setLineWidth(0.6); c.rect(M, y - h, tw, h - HH, stroke=1, fill=0)
                    st["y"] -= h + GAP
                elif "hindi" in d:
                    iw, ih = 1489, 209
                    w = 112 * mm; h = w * ih / iw
                    if draw and os.path.exists(HINDI):
                        c.drawImage(ImageReader(HINDI), M + 2 * mm, st["y"] - h - 1 * mm, width=w, height=h, mask="auto")
                    st["y"] -= h + 4 * mm
                return
            tot = sum(wt for _, wt in r)
            avail = tw - GAP * (len(r) - 1)
            x = M
            for label, wt in r:
                w = avail * wt / tot
                box(x, w, BOX, label, office)
                x += w + GAP
            st["y"] -= BOX + GAP

        # intro line on a soft band
        if draw:
            y = st["y"]
            c.setFillColor(TINT); c.roundRect(M, y - 7.5 * mm, W - 2 * M, 9.5 * mm, 1.8 * mm, stroke=0, fill=1)
            c.setFillColor(RED); c.rect(M, y - 7.5 * mm, 0.6 * mm, 9.5 * mm, stroke=0, fill=1)
            text(M + 5 * mm, y - 3.9 * mm, f["intro"], 8.6, "Helvetica", CHAR)
        st["y"] -= 15 * mm + gap_add
        for title, office, rows in f["sections"]:
            section(title)
            for r in rows:
                row(r, office)
            st["y"] -= 2.5 * mm + gap_add
        if f.get("note"):
            lines = simpleSplit("Note: " + f["note"], "Helvetica-Oblique", 8.4, W - 2 * M)
            if draw:
                for k, s in enumerate(lines):
                    text(M, st["y"] - k * 4 * mm, s, 8.4, "Helvetica-Oblique", MUTED)
            st["y"] -= len(lines) * 4 * mm + 3 * mm
        return st["y"]

    # Measure, then let the boxes and the spacing take up the free room, so
    # a short form is not half empty and a long one still fits one page.
    floor = FOOT_TOP + 6 * mm + SIG_H
    TABLE[0] = 0
    if any("table" in r[0] for _, _, rows in f["sections"] for r in rows if isinstance(r[0], dict)):
        # A list form: as many lines as fit; the rest of the page is not stretched.
        TABLE[0] = max(5, int((layout(False, 0, 0) - floor - 2 * mm) // (7.4 * mm)))
        end = layout(True, 0, 0)
        return _sign(c, f, end, buf, text, W, M, FOOT_TOP, SIG_H)
    free = layout(False, 0, 0) - floor
    nbox = sum(1 for _, _, rows in f["sections"] for r in rows if not isinstance(r[0], dict) or "tall" in r[0])
    nsec = len(f["sections"]) + 1
    grow = max(0, min(7 * mm, free * 0.6 / max(nbox, 1)))
    gap_add = 0
    left = layout(False, grow, 0) - floor
    if left > 0:
        gap_add = min(9 * mm, left * 0.75 / nsec)
    end = layout(True, grow, gap_add)

    return _sign(c, f, end, buf, text, W, M, FOOT_TOP, SIG_H)


def _sign(c, f, end, buf, text, W, M, FOOT_TOP, SIG_H):
    # ---- signatures, together at the foot of the page --------------------------
    sig_y = FOOT_TOP + 14 * mm
    n = len(f["sign"])
    hy = min(end - 4 * mm, sig_y + SIG_H - 8 * mm)
    c.setFillColor(RED); c.rect(M, hy - 0.4 * mm, 2.2 * mm, 2.2 * mm, stroke=0, fill=1)
    w = text(M + 4.2 * mm, hy, "SIGNATURES", 8, "Helvetica-Bold", CHAR, spacing=1.0)
    c.setStrokeColor(RULE); c.setLineWidth(0.5); c.line(M + 6.5 * mm + w, hy + 1.0 * mm, W - M, hy + 1.0 * mm)
    gap = 8 * mm
    sw = (W - 2 * M - gap * (n - 1)) / n
    for i, role in enumerate(f["sign"]):
        x = M + i * (sw + gap)
        c.setStrokeColor(CHAR); c.setLineWidth(0.7); c.line(x, sig_y, x + sw, sig_y)
        text(x, sig_y - 4.4 * mm, role, 8.8, "Helvetica-Bold", CHAR)
        text(x, sig_y - 8.6 * mm, "Date   ____ / ____ / ________", 7.4, "Helvetica", MUTED)
    c.showPage(); c.save(); buf.seek(0)
    return buf

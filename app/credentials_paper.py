"""The Credentials register on paper - screen, PDF and Excel alike.

Not the plain grid every other list uses: logins grouped by category,
each with its logo, the name and the full web address under it, the
username and the password set in a typewriter face so 0/O and 1/l read
apart, and the notes beside them. Every page says it is confidential.
"""
import base64
import io
from datetime import datetime
from html import escape

import export_web

RED = "#" + export_web.BRAND_RED
PALETTE = ["#00843D", "#B8860B", "#0B6E4F", "#0078D4", "#E2231A", "#6A4C93", "#1C4E80", "#C0392B", "#2E7D32", "#5B6167"]


def _tile_colour(name):
    h = 0
    for ch in name or "?":
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return PALETTE[h % len(PALETTE)]


def _letter(e):
    return "#" if e["kind"] == "pin" else "N" if e["kind"] == "note" else (e["name"] or "?").strip()[:1].upper()


def groups(entries):
    out = {}
    for e in entries:
        out.setdefault(e["category"], []).append(e)
    return list(out.items())


# ---- on screen ----------------------------------------------------------------------

def html(entries, title, sub, pdf_url, excel_url, who=""):
    logo = export_web.logo_data_uri()
    body = []
    for cat, es in groups(entries):
        body.append(f'<tr class="cat"><td colspan="5"><span>{escape(cat)}</span><em>{len(es)}</em></td></tr>')
        for e in es:
            tile = (f'<img src="{escape(e["logo"])}" alt="">' if e["logo"]
                    else f'<b style="background:{_tile_colour(e["name"])}">{escape(_letter(e))}</b>')
            lock = '<i class="lock">&#128274; Admin only</i>' if e["admin_only"] else ""
            site = escape(e["url"] or e["domain"] or ("PIN" if e["kind"] == "pin" else "Note" if e["kind"] == "note" else ""))
            secret = escape(e["secret"]) if e["secret"] else '<span class="nil">-</span>'
            body.append(
                f'<tr><td class="lg">{tile}</td>'
                f'<td class="nm"><div>{escape(e["name"])}{lock}</div><small>{site}</small></td>'
                f'<td class="mono">{escape(e["username"]) or "<span class=nil>-</span>"}</td>'
                f'<td class="mono pw"><span>{secret}</span></td>'
                f'<td class="nt">{escape(e["notes"]).replace(chr(10), "<br>") or ""}</td></tr>')
    table = ("".join(body) if entries else '<tr><td colspan="5" class="none">No logins saved.</td></tr>')
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{escape(title)}</title>
<meta name="viewport" content="width=820, minimum-scale=0.3, maximum-scale=4, user-scalable=yes">
<style>
 body{{margin:0;background:#F1EFEA;color:#1F2429;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif}}
 .page{{width:210mm;max-width:calc(100% - 24px);margin:16px auto;background:#fff;padding:12mm 11mm 14mm;box-sizing:border-box;box-shadow:0 1px 6px rgba(0,0,0,.14)}}
 .top{{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:1.2px solid {RED};padding-bottom:9px}}
 .top img{{width:42mm;display:block}}
 .top .r{{text-align:right}}
 .top .co{{font-size:11.5pt;font-weight:bold}}
 .top .ti{{font-size:15pt;font-weight:bold;margin-top:4px;letter-spacing:.2px}}
 .conf{{display:inline-block;margin-top:5px;font-size:7.5pt;font-weight:bold;letter-spacing:1.2px;color:{RED};border:1px solid {RED};border-radius:3px;padding:1px 6px}}
 .meta{{font-size:8pt;color:#777;margin:7px 0 2px}}
 table{{width:100%;border-collapse:collapse;table-layout:fixed;font-size:8.6pt}}
 col.lg{{width:9mm}} col.nm{{width:34%}} col.us{{width:22%}} col.pw{{width:17%}}
 th{{text-align:left;font-size:7pt;letter-spacing:.8px;text-transform:uppercase;color:#8A8178;font-weight:bold;padding:9px 6px 5px;border-bottom:1px solid #E6E1DA}}
 tr.cat td{{padding:12px 6px 5px;border-bottom:1.2px solid #1F2429}}
 tr.cat span{{font-size:8.5pt;font-weight:bold;letter-spacing:.9px;text-transform:uppercase}}
 tr.cat em{{font-style:normal;font-size:7.5pt;color:#8A8178;margin-left:6px}}
 td{{padding:7px 6px;border-bottom:.6px solid #ECE7E0;vertical-align:middle}}
 td.lg img,td.lg b{{width:7mm;height:7mm;border-radius:5px;display:flex;align-items:center;justify-content:center;object-fit:contain;color:#fff;font-size:9pt}}
 td.lg img{{box-shadow:inset 0 0 0 1px rgba(0,0,0,.06)}}
 td.nm div{{font-weight:bold;font-size:9.2pt}}
 td.nm small{{display:block;color:#8A8178;font-size:7.4pt;margin-top:1px;overflow-wrap:anywhere}}
 .lock{{font-style:normal;font-size:6.6pt;font-weight:bold;color:{RED};background:#FBE9E7;border-radius:3px;padding:1px 4px;margin-left:5px;vertical-align:1px;white-space:nowrap}}
 td.mono{{font-family:"SF Mono",Menlo,Consolas,"Courier New",monospace;font-size:8.4pt;overflow-wrap:anywhere}}
 td.pw span{{background:#F6F1EA;border-radius:4px;padding:2px 5px;box-decoration-break:clone;-webkit-box-decoration-break:clone}}
 td.nt{{font-size:7.6pt;color:#5B6167;overflow-wrap:anywhere}}
 .nil{{color:#BBB}}
 .none{{text-align:center;color:#888;padding:24px}}
 .foot{{margin-top:14px;font-size:7pt;color:#999;display:flex;justify-content:space-between}}
 @media print{{body{{background:#fff}} .pvbar{{display:none}} .page{{width:auto;margin:0;padding:0;box-shadow:none}} @page{{size:A4 portrait;margin:11mm}}
   tr{{page-break-inside:avoid}} td.pw span{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}}}
</style></head><body>
{export_web.preview_bar(title, sub, pdf_url, excel_url)}
<div class="page">
 <div class="top"><div>{f'<img src="{logo}" alt="Infinia">' if logo else ''}</div>
  <div class="r"><div class="co">INFINIA CONTRACTING LLC</div><div class="ti">Credentials Register</div><div class="conf">CONFIDENTIAL</div></div></div>
 <div class="meta">{escape(sub)}</div>
 <table><colgroup><col class="lg"><col class="nm"><col class="us"><col class="pw"><col></colgroup>
  <thead><tr><th></th><th>Login</th><th>Username</th><th>Password / PIN</th><th>Notes</th></tr></thead>
  <tbody>{table}</tbody></table>
 <div class="foot"><span>Confidential - for authorised staff only. Do not forward.</span><span>{escape(who)}</span></div>
</div></body></html>"""


# ---- PDF ----------------------------------------------------------------------------

def _img_flowable(data_uri, size):
    from reportlab.platypus import Image as RLImage
    try:
        raw = base64.b64decode(data_uri.split(",", 1)[1])
        try:
            from PIL import Image as PImage      # icons may be .ico or .svg-less PNG
            im = PImage.open(io.BytesIO(raw)).convert("RGBA")
            bg = PImage.new("RGBA", im.size, (255, 255, 255, 255))
            bg.alpha_composite(im)
            buf = io.BytesIO(); bg.convert("RGB").save(buf, "PNG"); buf.seek(0)
        except Exception:
            buf = io.BytesIO(raw)
        return RLImage(buf, width=size, height=size)
    except Exception:
        return None


def _tile_flowable(e, size):
    from reportlab.graphics.shapes import Drawing, Rect, String
    from reportlab.lib import colors
    d = Drawing(size, size)
    d.add(Rect(0, 0, size, size, rx=3, ry=3, fillColor=colors.HexColor(_tile_colour(e["name"])), strokeColor=None))
    d.add(String(size / 2, size / 2 - 3.2, _letter(e), fontName="Helvetica-Bold", fontSize=9, fillColor=colors.white, textAnchor="middle"))
    return d


def pdf(entries, title, sub, who=""):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    red = colors.HexColor(RED)
    grey = colors.HexColor("#8A8178")
    buf = io.BytesIO()
    W, H = A4
    M = 12 * mm
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=M, rightMargin=M, topMargin=34 * mm, bottomMargin=16 * mm,
                            title="Credentials Register", author="Infinia Contracting LLC")
    st = lambda **k: ParagraphStyle("x", fontName=k.pop("font", "Helvetica"), **k)
    s_name = st(font="Helvetica-Bold", fontSize=9, leading=11)
    s_site = st(fontSize=7, leading=8.6, textColor=grey, wordWrap="CJK")
    s_mono = st(font="Courier", fontSize=8.4, leading=10, wordWrap="CJK")
    s_pw = st(font="Courier-Bold", fontSize=8.6, leading=10.4, wordWrap="CJK")
    s_note = st(fontSize=7.4, leading=9, textColor=colors.HexColor("#5B6167"))
    s_head = st(font="Helvetica-Bold", fontSize=6.6, leading=8, textColor=grey)
    s_cat = st(font="Helvetica-Bold", fontSize=8.4, leading=10)

    def p(t, s):
        return Paragraph(escape(t or "").replace("\n", "<br/>") or "-", s)

    def wrap_any(t):
        # long addresses and user names break at / . @ rather than overflow
        return escape(t or "")

    widths = [10 * mm, 63 * mm, 42 * mm, 33 * mm, None]
    widths[-1] = W - 2 * M - sum(w for w in widths[:-1])
    data = [["", p("LOGIN", s_head), p("USERNAME", s_head), p("PASSWORD / PIN", s_head), p("NOTES", s_head)]]
    style = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor("#E6E1DA")),
             ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
             ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
    for cat, es in groups(entries):
        r = len(data)
        data.append([Paragraph(f'{escape(cat.upper())} <font color="#8A8178" size="7">&nbsp;{len(es)}</font>', s_cat), "", "", "", ""])
        style += [("SPAN", (0, r), (-1, r)), ("LINEBELOW", (0, r), (-1, r), 1, colors.HexColor("#1F2429")), ("TOPPADDING", (0, r), (-1, r), 10)]
        for e in es:
            size = 7 * mm
            tile = (_img_flowable(e["logo"], size) if e["logo"] else None) or _tile_flowable(e, size)
            lock = ' <font color="#C0392B" size="6.5"><b>ADMIN ONLY</b></font>' if e["admin_only"] else ""
            site = e["url"] or e["domain"] or ("PIN" if e["kind"] == "pin" else "Note" if e["kind"] == "note" else "")
            name = [Paragraph(escape(e["name"]) + lock, s_name), Paragraph(wrap_any(site), s_site)]
            r = len(data)
            data.append([tile, name, Paragraph(wrap_any(e["username"]) or "-", s_mono),
                         Paragraph(wrap_any(e["secret"]) or "-", s_pw), p(e["notes"], s_note) if e["notes"] else ""])
            style += [("LINEBELOW", (0, r), (-1, r), 0.4, colors.HexColor("#ECE7E0")),
                      ("BACKGROUND", (3, r), (3, r), colors.HexColor("#F6F1EA"))]
    if not entries:
        data.append(["", p("No logins saved.", s_note), "", "", ""])
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle(style))

    printed = datetime.utcnow()

    def page(c, d):
        c.saveState()
        logo = export_web.LOGO_PATH
        try:
            c.drawImage(logo, M, H - 20 * mm, width=42 * mm, height=7.1 * mm, mask="auto")
        except Exception:
            pass
        c.setFont("Helvetica-Bold", 10.5); c.setFillColor(colors.black)
        c.drawRightString(W - M, H - 15 * mm, "INFINIA CONTRACTING LLC")
        c.setFont("Helvetica-Bold", 14); c.drawRightString(W - M, H - 21.5 * mm, "Credentials Register")
        c.setFont("Helvetica-Bold", 6.8); c.setFillColor(red)
        tw = c.stringWidth("CONFIDENTIAL", "Helvetica-Bold", 6.8)
        c.roundRect(W - M - tw - 8, H - 27.6 * mm, tw + 8, 9, 2, stroke=1, fill=0)
        c.setStrokeColor(red); c.drawRightString(W - M - 4, H - 27.6 * mm + 2.6, "CONFIDENTIAL")
        c.setLineWidth(1.1); c.line(M, H - 30 * mm, W - M, H - 30 * mm)
        c.setFont("Helvetica", 7); c.setFillColor(grey)
        c.drawString(M, H - 33.2 * mm, sub)
        c.drawString(M, 9 * mm, "Confidential - for authorised staff only. Do not forward.")
        c.drawRightString(W - M, 9 * mm, f"{who}   |   Page {d.page}")
        c.restoreState()

    doc.build([t], onFirstPage=page, onLaterPages=page)
    return buf.getvalue()


# ---- Excel --------------------------------------------------------------------------

def excel(entries, title, sub):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    wb = Workbook(); ws = wb.active; ws.title = "Credentials"
    ws.sheet_view.showGridLines = False
    ws["A1"] = "INFINIA CONTRACTING LLC"; ws["A1"].font = Font(bold=True, size=12)
    ws["A2"] = "Credentials Register"; ws["A2"].font = Font(bold=True, size=15)
    ws["A3"] = "CONFIDENTIAL   |   " + sub; ws["A3"].font = Font(size=9, color=export_web.BRAND_RED, bold=True)
    heads = ["Category", "Name", "Website", "Username", "Password / PIN", "Notes", "Admin only"]
    widths = [14, 30, 40, 30, 22, 36, 11]
    thin = Side(style="thin", color="E6E1DA")
    for i, (h, w) in enumerate(zip(heads, widths), 1):
        c = ws.cell(row=5, column=i, value=h)
        c.font = Font(bold=True, color="FFFFFF", size=10)
        c.fill = PatternFill("solid", fgColor=export_web.BRAND_RED)
        c.alignment = Alignment(vertical="center")
        ws.column_dimensions[c.column_letter].width = w
    ws.row_dimensions[5].height = 20
    r = 6
    for cat, es in groups(entries):
        for e in es:
            vals = [cat, e["name"], e["url"] or e["domain"], e["username"], e["secret"], e["notes"], "Yes" if e["admin_only"] else ""]
            for i, v in enumerate(vals, 1):
                c = ws.cell(row=r, column=i, value=v or "")
                c.alignment = Alignment(vertical="center", wrap_text=True)
                c.border = Border(bottom=thin)
                if i in (4, 5):
                    c.font = Font(name="Consolas", size=10, bold=(i == 5))
                if i == 2:
                    c.font = Font(bold=True)
            r += 1
    ws.freeze_panes = "A6"
    ws.auto_filter.ref = f"A5:G{max(r - 1, 5)}"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4; ws.print_title_rows = "5:5"
    ws.page_setup.orientation = "landscape"; ws.page_setup.fitToWidth = 1; ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.oddHeader.right.text = "CONFIDENTIAL"
    out = io.BytesIO(); wb.save(out)
    return out.getvalue()

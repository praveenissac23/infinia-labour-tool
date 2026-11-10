"""Accounts > Cash forecast - the report (Preview and PDF), one design (10 Nov 2026).

Page 1, the picture: in the bank now and each month's closing (red when below the minimum), the month-by-month
waterfall (balance, money in, money out), where the money goes by type, the biggest payments and what comes in, and
the day it goes below the minimum. Page 2 on: every line with the balance after it.
"""
import html as _h
import io
from datetime import date

RED, GREEN, INK = "#C0392B", "#1E8449", "#2B2622"
TYPES = [("cheque", "Cheques (PDC)", "#3B5998"), ("salary", "Salaries", "#6B3FA0"), ("sub", "Subcontractors", "#8A5A00"), ("expected", "Forecast (Accounts)", "#B03A2E")]
TYPE_WORD = {"cheque": "Cheque", "salary": "Salaries", "sub": "Subcontractor", "client": "Client bill", "expected": "Forecast"}
e = lambda s: _h.escape(str(s if s is not None else ""))
m0 = lambda v: f"{float(v or 0):,.0f}"
m2 = lambda v: f"{float(v or 0):,.2f}"
dmy = lambda s: "/".join(reversed(str(s)[:10].split("-"))) if s else ""


def short(v):
    v = float(v or 0)
    return f"{v / 1e6:.2f}M" if abs(v) >= 1e6 else f"{v / 1e3:.0f}k"


def _bars(f):
    """The waterfall: [(kind, label, y_from, y_to, text)] - kind bal / in / out."""
    out = [("bal", "Now", 0, f["bank"]["now"], short(f["bank"]["now"]))]
    for m in f["months"]:
        top = m["opening"] + m["in"]
        if m["in"]:
            out.append(("in", "", m["opening"], top, "+" + short(m["in"])))
        if m["out"]:
            out.append(("out", "", top - m["out"], top, "-" + short(m["out"])))
        out.append(("bal", m["label"][:3], 0, m["closing"], short(m["closing"])))
    return out


def waterfall_svg(f, W=560, H=240):
    bars = _bars(f)
    keep = f["keep"]
    hi = max([b[3] for b in bars] + [keep]) * 1.08 or 1
    lo = min([b[2] for b in bars] + [0])
    top, bot = 14, H - 26
    Y = lambda v: top + (bot - top) * (hi - v) / ((hi - lo) or 1)
    n = len(bars); slot = (W - 40) / max(1, n); bw = min(48, slot * .72)
    g = []
    for k in range(4):
        v = lo + (hi - lo) * k / 3
        g.append(f'<line x1="36" x2="{W}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="#f0ebe6"/><text x="0" y="{Y(v) + 3:.1f}" font-size="9" fill="#999">{short(v)}</text>')
    g.append(f'<line x1="36" x2="{W}" y1="{Y(keep):.1f}" y2="{Y(keep):.1f}" stroke="#E6B8B1" stroke-width="2" stroke-dasharray="5 4"/>')
    if lo < 0:
        g.append(f'<line x1="36" x2="{W}" y1="{Y(0):.1f}" y2="{Y(0):.1f}" stroke="#999"/>')
    for i, (k, lab, a, b, txt) in enumerate(bars):
        x = 40 + slot * i + (slot - bw) / 2
        y1, y2 = Y(max(a, b)), Y(min(a, b))
        col = "#2ECC71" if k == "in" else "#E74C3C" if k == "out" else (RED if b < keep else ("#3A3330" if i == 0 else "#5A4E48"))
        g.append(f'<rect x="{x:.1f}" y="{y1:.1f}" width="{bw:.1f}" height="{max(1.5, y2 - y1):.1f}" rx="3" fill="{col}"/>')
        tc = GREEN if k == "in" else RED if (k == "out" or b < keep) else INK
        ty = y1 - 4 if k != "out" else y2 + 10
        g.append(f'<text x="{x + bw / 2:.1f}" y="{ty:.1f}" font-size="8.5" text-anchor="middle" font-weight="700" fill="{tc}">{e(txt)}</text>')
        if lab:
            g.append(f'<text x="{x + bw / 2:.1f}" y="{H - 8}" font-size="9" text-anchor="middle" fill="#666">{e(lab)}</text>')
    return f'<svg viewBox="0 0 {W} {H}" width="100%" height="{H}">{"".join(g)}</svg>'


def _period(f):
    if not f["months"]:
        return ""
    a, b = f["months"][0], f["months"][-1]
    da, db_ = date.fromisoformat(a["from"]), date.fromisoformat(b["to"])
    return f"{da:%B %Y} – {db_:%B %Y}" if (da.year, da.month) != (db_.year, db_.month) else f"{da:%B %Y}"


def report_html(f, pdf_url="", excel_url="", logo="", stamp=""):
    keep = f["keep"]
    bank = f["bank"]
    stmt = " · ".join(f"{b['bank']} statement {dmy(b['as_of'])}" for b in bank["banks"]) or "no statement uploaded"
    kp = [f'<div class="k dark"><div class="l">In the bank now</div><div class="v">AED {m0(bank["now"])}</div><div class="s">{e(stmt)}</div></div>']
    for m in f["months"][:3]:
        bad = m["closing"] < keep
        kp.append(f'<div class="k{" bad" if bad else ""}"><div class="l">End of {e(m["label"])}</div><div class="v{" r" if bad else ""}">{m0(m["closing"])}</div>'
                  f'<div class="s"><span class="g">+{m0(m["in"])}</span> in · <span class="r">−{m0(m["out"])}</span> out</div></div>')
    mos = f["months"]
    rows = []
    for key, lab, col in TYPES:
        vals = [-(m["by"].get(key) or 0) for m in mos]
        if any(vals):
            rows.append(f'<tr><td><span class="dot" style="background:{col}"></span>{lab}</td>' + "".join(f'<td class="n">{m0(v) if v else "-"}</td>' for v in vals) + f'<td class="n">{m0(sum(vals))}</td></tr>')
    rows.append('<tr class="t"><td>Going out</td>' + "".join(f'<td class="n r">{m0(m["out"])}</td>' for m in mos) + f'<td class="n r">{m0(f["total_out"])}</td></tr>')
    rows.append('<tr><td><span class="dot" style="background:#1E8449"></span>Coming in</td>' + "".join(f'<td class="n g">{m0(m["in"]) if m["in"] else "-"}</td>' for m in mos) + f'<td class="n g">{m0(f["total_in"])}</td></tr>')
    tot = f["total_out"] or 1
    strip = "".join(f'<div style="width:{100 * (f["by_type"].get(k) or 0) / tot:.2f}%;background:{c}"></div>' for k, _, c in TYPES if f["by_type"].get(k))
    biggest_t = max(((f["by_type"].get(k) or 0, l) for k, l, _ in TYPES), default=(0, ""))
    big = "".join(f'<tr><td>{"past date" if g["late"] else " · ".join(dmy(d)[:5] for d in g["dates"][:3])}</td><td>{e(g["what"])}{(" (" + str(g["n"]) + ")") if g["n"] > 1 and g["type"] == "sub" else ""}</td>'
                  f'<td>{TYPE_WORD.get(g["type"], "")}</td><td class="n r">{m0(g["amount"])}</td></tr>' for g in f["biggest"][:5])
    cin = "".join(f'<tr><td>{dmy(i["date"])[:5]}</td><td>{e(i["what"])}</td><td class="n g">{m0(i["in"])}</td></tr>' for i in f["coming"][:6])
    watch = (f'<b>Watch:</b> the bank goes below AED {m0(keep)} on {dmy(f["below"]["date"])} ({e(f["below"]["what"])}).' if f.get("below")
             else f'The bank stays above AED {m0(keep)} - lowest {m0(f["low"]["amount"])} on {dmy(f["low"]["date"])}.')
    # page 2+: every line
    lines, last = [], ""
    for i in f["items"]:
        mk = i["date"][:7]
        if mk != last:
            lines.append(f'<tr class="mh"><td colspan="6">{date.fromisoformat(i["date"]):%B %Y}</td></tr>'); last = mk
        lines.append(f'<tr><td>{dmy(i["date"])}{" <span class=lt>past</span>" if i["late"] else ""}</td><td>{e(i["what"])}</td><td>{TYPE_WORD.get(i["type"], i["type"])}</td>'
                     f'<td class="n g">{m2(i["in"]) if i["in"] else ""}</td><td class="n r">{m2(i["out"]) if i["out"] else ""}</td><td class="n{" r" if i["after"] < keep else ""}">{m2(i["after"])}</td></tr>')
    css = """
@page{size:A4 landscape;margin:0}*{box-sizing:border-box}body{margin:0;font-family:Inter,Arial,sans-serif;color:#2B2622;font-size:10.5pt;background:#E9E5E1}
.bar{position:sticky;top:0;z-index:5;background:#2E2A27;color:#fff;display:flex;gap:10px;align-items:center;padding:10px 16px}.bar b{flex:1}
.bar a{background:#FBEFED;color:#A93226;border:1px solid #E6B8B1;border-radius:8px;padding:7px 14px;text-decoration:none;font-weight:600;font-size:13px}
.pg{width:297mm;min-height:210mm;padding:12mm 14mm 14mm;margin:14px auto;background:#fff;position:relative;box-shadow:0 2px 14px rgba(0,0,0,.12)}
.hd{display:flex;justify-content:space-between;align-items:center;border-bottom:3px solid #C0392B;padding-bottom:6px}.hd img{height:34px}.hd .t{text-align:right}.hd .t b{font-size:15pt;color:#C0392B}.hd .t div{font-size:8.5pt;color:#777}
.band{display:grid;grid-template-columns:1.2fr repeat(3,1fr);gap:10px;margin-top:10px}
.k{border-radius:12px;padding:10px 12px;border:1px solid #eee}.k .l{font-size:7.5pt;letter-spacing:.1em;text-transform:uppercase;color:#888}.k .v{font-size:17pt;font-weight:800;margin-top:2px}.k .s{font-size:8pt;color:#777}
.k.dark{background:#2E2A27;color:#fff;border:0}.k.dark .l,.k.dark .s{color:#d8cfc8}.k.bad{background:#FDECEA;border-color:#F1B9B2}
.g{color:#1E8449}.r{color:#B03A2E}.row{display:grid;grid-template-columns:1.45fr 1fr;gap:12px;margin-top:10px}.row2{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:10px}
.box{border:1px solid #eee;border-radius:12px;padding:10px 12px}.box h4{margin:0 0 4px;font-size:10.5pt}
table{width:100%;border-collapse:collapse;font-size:8.8pt}th{background:#C0392B;color:#fff;text-align:left;padding:4px 6px;font-weight:600}td{padding:4px 6px;border-bottom:1px solid #eee}td.n,th.n{text-align:right;white-space:nowrap}
tr.t td{font-weight:800;border-top:1.5px solid #222}tr.mh td{background:#F6F2EE;font-weight:800}.lt{background:#FDECEA;color:#B03A2E;border-radius:6px;padding:0 5px;font-size:7.5pt}
.strip{display:flex;height:14px;border-radius:4px;overflow:hidden;margin-top:8px}.dot{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:5px}
.watch{margin-top:8px;border-radius:8px;padding:6px 10px;font-size:8.5pt}.ft{position:absolute;bottom:6mm;left:14mm;right:14mm;display:flex;justify-content:space-between;font-size:7.5pt;color:#999}
@media print{body{background:#fff}.bar{display:none}.pg{margin:0;box-shadow:none;page-break-after:always}}"""
    head = f'<div class="hd">{f"<img src={chr(34)}{logo}{chr(34)}>" if logo else "<b>INFINIA</b>"}<div class="t"><b>Cash Forecast</b><div>{e(_period(f))} · prepared {e(stamp)} · Accounts</div></div></div>'
    p1 = f"""<div class="pg">{head}<div class="band">{"".join(kp)}</div>
<div class="row"><div class="box"><h4>Month by month</h4>{waterfall_svg(f)}
<div style="font-size:8pt;color:#777"><span class="dot" style="background:#2ECC71"></span>money in <span class="dot" style="background:#E74C3C;margin-left:8px"></span>money out <span class="dot" style="background:#5A4E48;margin-left:8px"></span>balance at month end <span style="margin-left:8px;color:#C0392B">┅ keep at least {m0(keep)}</span></div></div>
<div class="box"><h4>Where the money goes</h4><table><tr><th></th>{"".join(f'<th class="n">{e(m["label"][:3])}</th>' for m in mos)}<th class="n">Total</th></tr>{"".join(rows)}</table>
<div class="strip">{strip}</div><div style="font-size:8pt;color:#777;margin-top:4px">{e(biggest_t[1])} are {100 * biggest_t[0] / tot:.0f}% of what goes out.</div></div></div>
<div class="row2"><div class="box"><h4>Biggest payments coming</h4><table><tr><th>Date</th><th>To</th><th>Type</th><th class="n">AED</th></tr>{big or '<tr><td colspan="4">Nothing going out.</td></tr>'}</table></div>
<div class="box"><h4>Coming in</h4><table><tr><th>Expected</th><th>From</th><th class="n">AED</th></tr>{cin or '<tr><td colspan="3">Nothing expected in.</td></tr>'}
<tr class="t"><td colspan="2">Total</td><td class="n g">{m0(f["total_in"])}</td></tr></table>
<div class="watch" style="background:{"#FDECEA;color:#8E1F16" if f.get("below") else "#E8F6EE;color:#1E8449"}">{watch}</div></div></div>
<div class="ft"><span>Infinia Contracting LLC · Cash forecast · from the app: bank statement, PDC register, Estimation, payroll and Accounts' forecast</span><span>Page 1</span></div></div>"""
    p2 = f"""<div class="pg">{head}<h4 style="margin:10px 0 6px">Every payment and receipt</h4><table><tr><th>Date</th><th>What</th><th>Type</th><th class="n">In (AED)</th><th class="n">Out (AED)</th><th class="n">Balance after</th></tr>
<tr><td>{dmy(f["today"])}</td><td><b>In the bank now</b></td><td></td><td></td><td></td><td class="n"><b>{m2(bank["now"])}</b></td></tr>{"".join(lines)}</table></div>"""
    bar = (f'<div class="bar"><b>Cash forecast - {e(_period(f))}</b>{f"<a href={chr(34)}{pdf_url}{chr(34)}>Export PDF</a>" if pdf_url else ""}'
           f'{f"<a href={chr(34)}{excel_url}{chr(34)}>Export Excel</a>" if excel_url else ""}</div>') if (pdf_url or excel_url) else ""
    return f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Cash forecast</title><style>{css}</style></head><body>{bar}{p1}{p2}</body></html>'


# ---------------------------------------------------------------------------------------------------- PDF
def report_pdf(f, logo_path="", stamp=""):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import HexColor
    W, H = landscape(A4)
    buf = io.BytesIO()
    cv = canvas.Canvas(buf, pagesize=(W, H))
    M = 40
    keep = f["keep"]
    C = HexColor
    def txt(x, y, s, size=9, col=INK, bold=False, right=False, center=False):
        cv.setFont("Helvetica-Bold" if bold else "Helvetica", size); cv.setFillColor(C(col))
        (cv.drawRightString if right else cv.drawCentredString if center else cv.drawString)(x, y, str(s))
    def rrect(x, y, w, h, fill=None, stroke=None, r=8):
        cv.setFillColor(C(fill or "#FFFFFF")); cv.setStrokeColor(C(stroke or fill or "#EEEEEE"))
        cv.roundRect(x, y, w, h, r, stroke=1 if stroke else 0, fill=1 if fill else 0)
    def header(pno):
        if logo_path:
            try:
                cv.drawImage(logo_path, M, H - 62, height=30, width=110, preserveAspectRatio=True, anchor="w", mask="auto")
            except Exception:
                txt(M, H - 50, "INFINIA", 16, RED, True)
        txt(W - M, H - 44, "Cash Forecast", 16, RED, True, right=True)
        txt(W - M, H - 58, f"{_period(f)} · prepared {stamp} · Accounts", 8, "#777777", right=True)
        cv.setStrokeColor(C(RED)); cv.setLineWidth(2.5); cv.line(M, H - 68, W - M, H - 68); cv.setLineWidth(1)
        txt(M, 18, "Infinia Contracting LLC · Cash forecast · from the app: bank statement, PDC register, Estimation, payroll and Accounts' forecast", 7, "#999999")
        txt(W - M, 18, f"Page {pno}", 7, "#999999", right=True)
    header(1)
    # KPI band
    y = H - 140; bw = (W - 2 * M - 30) / 4.2
    xs = [M, M + bw * 1.2 + 10]
    for i in range(2, 4):
        xs.append(xs[-1] + bw + 10)
    bank = f["bank"]
    rrect(M, y, bw * 1.2, 62, "#2E2A27")
    txt(M + 10, y + 46, "IN THE BANK NOW", 7, "#D8CFC8"); txt(M + 10, y + 24, f"AED {m0(bank['now'])}", 17, "#FFFFFF", True)
    txt(M + 10, y + 10, " · ".join(f"{b['bank']} statement {dmy(b['as_of'])}" for b in bank["banks"]) or "no statement", 7.5, "#D8CFC8")
    for x, m in zip(xs[1:], f["months"][:3]):
        bad = m["closing"] < keep
        rrect(x, y, bw, 62, "#FDECEA" if bad else "#FFFFFF", "#F1B9B2" if bad else "#EEEEEE")
        txt(x + 10, y + 46, f"END OF {m['label'].upper()}", 7, "#888888"); txt(x + 10, y + 24, m0(m["closing"]), 17, RED if bad else INK, True)
        txt(x + 10, y + 10, f"+{m0(m['in'])} in", 7.5, GREEN); txt(x + 10 + 70, y + 10, f"-{m0(m['out'])} out", 7.5, RED)
    # waterfall
    bx, by, bwid, bh = M, 205, (W - 2 * M - 12) * .58, 180
    rrect(bx, by, bwid, bh, None, "#EEEEEE"); txt(bx + 10, by + bh - 16, "Month by month", 10.5, INK, True)
    bars = _bars(f); hi = max([b[3] for b in bars] + [keep]) * 1.08 or 1; lo = min([b[2] for b in bars] + [0])
    gx, gy, gw, gh = bx + 34, by + 26, bwid - 46, bh - 58
    Y = lambda v: gy + gh * (v - lo) / ((hi - lo) or 1)
    for k in range(4):
        v = lo + (hi - lo) * k / 3
        cv.setStrokeColor(C("#F0EBE6")); cv.line(gx, Y(v), gx + gw, Y(v)); txt(bx + 6, Y(v) - 3, short(v), 7, "#999999")
    cv.setStrokeColor(C("#E6B8B1")); cv.setDash(4, 3); cv.setLineWidth(1.5); cv.line(gx, Y(keep), gx + gw, Y(keep)); cv.setDash(); cv.setLineWidth(1)
    slot = gw / max(1, len(bars)); bwd = min(36, slot * .72)
    for i, (k, lab, a, b, t_) in enumerate(bars):
        x = gx + slot * i + (slot - bwd) / 2
        col = "#2ECC71" if k == "in" else "#E74C3C" if k == "out" else (RED if b < keep else ("#3A3330" if i == 0 else "#5A4E48"))
        cv.setFillColor(C(col)); cv.roundRect(x, Y(min(a, b)), bwd, max(1.5, Y(max(a, b)) - Y(min(a, b))), 2.5, stroke=0, fill=1)
        tc = GREEN if k == "in" else RED if (k == "out" or b < keep) else INK
        txt(x + bwd / 2, (Y(max(a, b)) + 3) if k != "out" else (Y(min(a, b)) - 9), t_, 7, tc, True, center=True)
        if lab:
            txt(x + bwd / 2, gy - 12, lab, 7.5, "#666666", center=True)
    # where the money goes
    tx, tw = bx + bwid + 12, W - M - (bx + bwid + 12)
    rrect(tx, by, tw, bh, None, "#EEEEEE"); txt(tx + 10, by + bh - 16, "Where the money goes", 10.5, INK, True)
    mos = f["months"]; ncol = len(mos) + 1
    cw = (tw - 20 - 92) / ncol; yy = by + bh - 36
    rrect(tx + 8, yy - 4, tw - 16, 15, RED, r=2)
    for j, m in enumerate(mos):
        txt(tx + 100 + cw * (j + 1), yy, m["label"][:3], 7.5, "#FFFFFF", True, right=True)
    txt(tx + 100 + cw * ncol, yy, "Total", 7.5, "#FFFFFF", True, right=True)
    yy -= 15
    lines_ = [(l, c, [-(m["by"].get(k) or 0) for m in mos]) for k, l, c in TYPES if any(m["by"].get(k) for m in mos)]
    for l, c, vals in lines_:
        cv.setFillColor(C(c)); cv.rect(tx + 12, yy - 1, 6, 6, stroke=0, fill=1); txt(tx + 22, yy, l, 7.8)
        for j, v in enumerate(vals):
            txt(tx + 100 + cw * (j + 1), yy, m0(v) if v else "-", 7.8, right=True)
        txt(tx + 100 + cw * ncol, yy, m0(sum(vals)), 7.8, right=True); yy -= 14
    cv.setStrokeColor(C(INK)); cv.line(tx + 10, yy + 10, tx + tw - 10, yy + 10)
    txt(tx + 12, yy, "Going out", 8, INK, True)
    for j, m in enumerate(mos):
        txt(tx + 100 + cw * (j + 1), yy, m0(m["out"]), 8, RED, True, right=True)
    txt(tx + 100 + cw * ncol, yy, m0(f["total_out"]), 8, RED, True, right=True); yy -= 14
    txt(tx + 22, yy, "Coming in", 7.8, GREEN)
    for j, m in enumerate(mos):
        txt(tx + 100 + cw * (j + 1), yy, m0(m["in"]) if m["in"] else "-", 7.8, GREEN, right=True)
    txt(tx + 100 + cw * ncol, yy, m0(f["total_in"]), 7.8, GREEN, right=True)
    sx, sw = tx + 12, tw - 24; tot = f["total_out"] or 1
    for k, _, c in TYPES:
        v = f["by_type"].get(k) or 0
        if v:
            w_ = sw * v / tot; cv.setFillColor(C(c)); cv.rect(sx, by + 16, w_, 10, stroke=0, fill=1); sx += w_
    # biggest + coming in
    hx, hw, hy, hh = M, (W - 2 * M - 12) / 2, 40, 150
    for col_i, (title, heads, rows_, foot) in enumerate([
            ("Biggest payments coming", ["Date", "To", "Type", "AED"],
             [("past date" if g["late"] else " · ".join(dmy(d)[:5] for d in g["dates"][:3]), g["what"][:44], TYPE_WORD.get(g["type"], ""), m0(g["amount"])) for g in f["biggest"][:5]], None),
            ("Coming in", ["Expected", "From", "", "AED"], [(dmy(i["date"])[:5], i["what"][:52], "", m0(i["in"])) for i in f["coming"][:5]], True)]):
        x0 = hx + col_i * (hw + 12)
        rrect(x0, hy, hw, hh, None, "#EEEEEE"); txt(x0 + 10, hy + hh - 16, title, 10.5, INK, True)
        yy = hy + hh - 36; rrect(x0 + 8, yy - 4, hw - 16, 15, RED, r=2)
        cx = [x0 + 12, x0 + 90, x0 + hw - 150, x0 + hw - 12]
        for j, hd in enumerate(heads):
            txt(cx[j], yy, hd, 7.5, "#FFFFFF", True, right=(j == 3))
        yy -= 15
        for r_ in rows_ or [("", "Nothing", "", "")]:
            for j, v in enumerate(r_):
                txt(cx[j], yy, v, 7.8, (GREEN if col_i else RED) if j == 3 else INK, right=(j == 3))
            yy -= 13
        if foot:
            below = f.get("below")
            msg = (f"Watch: the bank goes below AED {m0(keep)} on {dmy(below['date'])} ({below['what'][:40]})." if below
                   else f"The bank stays above AED {m0(keep)} - lowest {m0(f['low']['amount'])} on {dmy(f['low']['date'])}.")
            rrect(x0 + 8, hy + 8, hw - 16, 20, "#FDECEA" if below else "#E8F6EE", r=5)
            txt(x0 + 14, hy + 15, msg, 7.8, "#8E1F16" if below else GREEN, True)
    cv.showPage()
    # page 2+: every line
    pno = 2; header(pno)
    cols = [M + 4, M + 70, W - M - 330, W - M - 220, W - M - 110, W - M - 4]
    def thead(yy):
        rrect(M, yy - 4, W - 2 * M, 15, RED, r=2)
        for j, h_ in enumerate(["Date", "What", "Type", "In (AED)", "Out (AED)", "Balance after"]):
            txt(cols[j], yy, h_, 7.5, "#FFFFFF", True, right=j >= 3)
        return yy - 15
    yy = thead(H - 90)
    txt(cols[0], yy, dmy(f["today"]), 7.8); txt(cols[1], yy, "In the bank now", 7.8, INK, True); txt(cols[5], yy, m2(bank["now"]), 7.8, INK, True, right=True); yy -= 13
    last = ""
    for i in f["items"]:
        if yy < 40:
            cv.showPage(); pno += 1; header(pno); yy = thead(H - 90)
        mk = i["date"][:7]
        if mk != last:
            cv.setFillColor(C("#F6F2EE")); cv.rect(M, yy - 3, W - 2 * M, 13, stroke=0, fill=1)
            txt(cols[0], yy, date.fromisoformat(i["date"]).strftime("%B %Y"), 7.8, INK, True); yy -= 13; last = mk
        txt(cols[0], yy, dmy(i["date"]) + (" past" if i["late"] else ""), 7.8, RED if i["late"] else INK)
        txt(cols[1], yy, i["what"][:95], 7.8); txt(cols[2], yy, TYPE_WORD.get(i["type"], i["type"]), 7.8, "#666666")
        if i["in"]:
            txt(cols[3], yy, m2(i["in"]), 7.8, GREEN, right=True)
        if i["out"]:
            txt(cols[4], yy, m2(i["out"]), 7.8, RED, right=True)
        txt(cols[5], yy, m2(i["after"]), 7.8, RED if i["after"] < keep else INK, right=True)
        cv.setStrokeColor(C("#EEEEEE")); cv.line(M, yy - 4, W - M, yy - 4); yy -= 13
    cv.showPage(); cv.save(); buf.seek(0)
    return buf

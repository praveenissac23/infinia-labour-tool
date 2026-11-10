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


def tank_colour(c, keep):
    return "#E74C3C" if c < keep else "#F5B041" if c < keep * 2 else "#2ECC71"


def tank_fill(f):
    """One full ring = the most the bank holds over the period (at least twice the minimum)."""
    mos = f["months"]
    return max([f["bank"]["now"], f["keep"] * 2] + [m["opening"] for m in mos] + [m["closing"] for m in mos]) or 1


def tank_word(m, keep):
    c = m["closing"]
    return "below zero" if c < 0 else f"below {short(keep)}" if c < keep else f"dips to {short(m['low'])}" if m["low"] < keep else f"end of {m['label']}"


def weeks(f):
    """The weeks ahead, as on the page: [(start, in, out, bank at the end)] - a week for 3 months, two weeks for 6, four for 12."""
    from datetime import timedelta
    mos = f["months"]
    if not mos:
        return 7, []
    step = 28 if len(mos) >= 12 else 14 if len(mos) >= 6 else 7
    t0, t1 = date.fromisoformat(f["today"]), date.fromisoformat(mos[-1]["to"])
    n = max(1, -(-((t1 - t0).days + 1) // step))
    out, bal = [], f["bank"]["now"]
    for k in range(n):
        a = t0 + timedelta(days=k * step); z = a + timedelta(days=step)
        mine = [i for i in f["items"] if a.isoformat() <= i["date"] < z.isoformat()]
        cin, cout = sum(i["in"] for i in mine), sum(i["out"] for i in mine); bal += cin - cout
        out.append((a, cin, cout, bal))
    return step, out


def _ring_svg(m, keep, full, size):
    import math
    C = 2 * math.pi * 108; c = m["closing"]; fr = max(0, min(1, c / full)); col = tank_colour(c, keep)
    arc = f'<circle cx="130" cy="130" r="108" stroke="{col}" stroke-width="22" fill="none" stroke-dasharray="{C * fr:.1f} {C:.1f}" transform="rotate(-90 130 130)" stroke-linecap="round"/>' if fr > 0 else ""
    return (f'<svg viewBox="0 0 260 260" width="{size}" height="{size}"><circle cx="130" cy="130" r="108" stroke="#EAE4DE" stroke-width="22" fill="none"/>{arc}'
            f'<text x="130" y="130" text-anchor="middle" font-size="42" font-weight="800" fill="{"#C0392B" if c < keep else "#2B2622"}">{"−" if c < 0 else ""}{short(abs(c))}</text>'
            f'<text x="130" y="162" text-anchor="middle" font-size="16" fill="#7A7069">{e(tank_word(m, keep))}</text></svg>')


def weeks_svg(f, W=1000, H=210):
    step, wk = weeks(f)
    if not wk:
        return ""
    keep = f["keep"]; n = len(wk); colW = (W - 50) / n; bw = min(26, colW * .32)
    maxF = max([1] + [max(w[1], w[2]) for w in wk]); balTop, balH, base, barH = 22, H * .28, H * .6, H * .2
    bals = [w[3] for w in wk] + [f["bank"]["now"], keep]; hi, lo = max(bals), min(bals)
    Yb = lambda v: balTop + balH * (hi - v) / ((hi - lo) or 1)
    g = [f'<line x1="20" x2="{W}" y1="{base}" y2="{base}" stroke="#DDD6CF"/><line x1="20" x2="{W}" y1="{Yb(keep):.1f}" y2="{Yb(keep):.1f}" stroke="#C0392B" stroke-dasharray="4 4" opacity=".6"/>'
         f'<text x="{W}" y="{Yb(keep) - 4:.1f}" text-anchor="end" font-size="10" fill="#C0392B">{short(keep)}</text>']
    pts = []
    for k, (a, cin, cout, bal) in enumerate(wk):
        cx = 40 + colW * k + colW / 2; hIn = barH * cin / maxF; hOut = barH * cout / maxF
        if cin:
            g.append(f'<rect x="{cx - bw - 2:.1f}" y="{base - hIn:.1f}" width="{bw:.1f}" height="{max(2, hIn):.1f}" rx="3" fill="#2ECC71"/><text x="{cx - 2 - bw / 2:.1f}" y="{base - hIn - 4:.1f}" text-anchor="middle" font-size="9" fill="#1E8449">{short(cin)}</text>')
        if cout:
            g.append(f'<rect x="{cx + 2:.1f}" y="{base}" width="{bw:.1f}" height="{max(2, hOut):.1f}" rx="3" fill="#E74C3C"/>')
            if hOut > 12:
                g.append(f'<text x="{cx + 2 + bw / 2:.1f}" y="{base + hOut + 11:.1f}" text-anchor="middle" font-size="9" fill="#C0392B">{short(cout)}</text>')
        if n <= 20 or k % 2 == 0:
            g.append(f'<text x="{cx:.1f}" y="{H - 4}" text-anchor="middle" font-size="10" fill="#7A7069">{a.day} {a:%b}</text>')
        pts.append((cx, Yb(bal), bal))
    g.append('<polyline fill="none" stroke="#2B2622" stroke-width="1.8" opacity=".85" points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in pts) + '"/>')
    for k, (x, y, v) in enumerate(pts):
        c = "#C0392B" if v < keep else "#2B2622"
        g.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.8" fill="{c}"/>' + (f'<text x="{x:.1f}" y="{y - 7:.1f}" text-anchor="middle" font-size="9.5" fill="{c}">{short(v)}</text>' if n <= 14 or k % 2 == 0 else ""))
    return f'<svg viewBox="0 0 {W} {H}" width="100%" height="{H}">{"".join(g)}</svg>'


def report_html(f, pdf_url="", excel_url="", logo="", stamp=""):
    keep = f["keep"]
    bank = f["bank"]
    mos = f["months"]
    stmt = " · ".join(f"{b['bank']} statement {dmy(b['as_of'])}" for b in bank["banks"]) or "no statement uploaded"
    full = tank_fill(f); shown = mos[:6]; many = len(shown) > 3; rs = 116 if not many else 68
    tanks = "".join(f'<div class="tk">{_ring_svg(m, keep, full, rs)}<div class="tt">{e(m["label"])}</div><div class="ts"><span class="g">+{m0(m["in"])}</span> · <span class="r">−{m0(m["out"])}</span></div></div>' for m in shown)
    bg = f["biggest"][0] if f["biggest"] else None
    below = f.get("below")
    tiles = (f'<div><span>Going out · {len(mos)} months</span><b>{m0(f["total_out"])}</b></div><div><span>Coming in</span><b class="g">{m0(f["total_in"])}</b></div>'
             f'<div><span>Biggest</span><b>{e(bg["what"].split(" · ")[0][:24]) + " " + short(bg["amount"]) if bg else "-"}</b></div>'
             f'<div class="{"warn" if below else "safe"}"><span>{"Watch" if below else "Safe"} · keep at least {short(keep)}</span><b class="{"r" if below else "g"}">{dmy(below["date"]) + " · below " + short(keep) if below else "lowest " + m0(f["low"]["amount"])}</b></div>')
    ico = {"cheque": ("C", "#EEF2FA", "#3B5998"), "salary": ("S", "#F3EEFA", "#6B3FA0"), "sub": ("S", "#FFF1D6", "#8A5A00"), "expected": ("F", "#FDECEA", "#C0392B"), "client": ("B", "#E8F6EE", "#1E8449")}
    def li(t, what, sub, amt, cls):
        i_, b_, c_ = ico.get(t, ("·", "#333", "#2B2622"))
        return f'<div class="li"><i style="background:{b_};color:{c_}">{i_}</i><div class="w"><b>{e(what)}</b><small>{e(sub)}</small></div><div class="a {cls}">{amt}</div></div>'
    big = "".join(li(g["type"], g["what"] + (f' ({g["n"]})' if g["n"] > 1 and g["type"] == "sub" else ""), ("date passed" if g["late"] else " · ".join(dmy(d)[:5] for d in g["dates"][:3])) + (" · forecast" if g["type"] == "expected" else " · cheque" if g["type"] == "cheque" else ""), m0(g["amount"]), "r") for g in f["biggest"][:5]) or '<div class="sub">Nothing going out.</div>'
    cin = "".join(li("client", i["what"].split(" · ")[0], "expected " + dmy(i["date"])[:5], m0(i["in"]), "g") for i in f["coming"][:4]) or '<div class="sub">No client bill waiting for payment.</div>'
    last_in = f["coming"][-1]["date"] if f["coming"] else None
    quiet = (date.fromisoformat(mos[-1]["to"]) - date.fromisoformat(last_in)).days if (last_in and mos) else None
    note = (f'<div class="note"><b class="r">{"Nothing expected in after " + dmy(last_in) + "." if last_in else "Nothing expected in."}</b><div>{"The bank goes below " + m0(keep) + " on " + dmy(below["date"]) + " - a client payment before then keeps it above." if below else "Payments still go out every month."}</div></div>'
            if (not f["coming"] or quiet > 30) else f'<div class="note ok"><b class="g">Client money keeps coming in.</b><div>{len(f["coming"])} payment(s) expected in the period.</div></div>')
    step, _ = weeks(f)
    # page 2+: every line
    lines, last = [], ""
    for i in f["items"]:
        mk = i["date"][:7]
        if mk != last:
            lines.append(f'<tr class="mh"><td colspan="6">{date.fromisoformat(i["date"]):%B %Y}</td></tr>'); last = mk
        lines.append(f'<tr><td>{dmy(i["date"])}{" <span class=lt>past</span>" if i["late"] else ""}</td><td>{e(i["what"])}</td><td>{TYPE_WORD.get(i["type"], i["type"])}</td>'
                     f'<td class="n g">{m2(i["in"]) if i["in"] else ""}</td><td class="n r">{m2(i["out"]) if i["out"] else ""}</td><td class="n{" r" if i["after"] < keep else ""}">{m2(i["after"])}</td></tr>')
    css = """
@page{size:A4 landscape;margin:0}*{box-sizing:border-box;-webkit-print-color-adjust:exact;print-color-adjust:exact}body{margin:0;font-family:Inter,Arial,sans-serif;color:#2B2622;font-size:10.5pt;background:#E9E5E1}
.bar{position:sticky;top:0;z-index:5;background:#2E2A27;color:#fff;display:flex;gap:10px;align-items:center;padding:10px 16px}.bar b{flex:1}
.bar a{background:#FBEFED;color:#A93226;border:1px solid #E6B8B1;border-radius:8px;padding:7px 14px;text-decoration:none;font-weight:600;font-size:13px}
.pg{width:297mm;min-height:210mm;padding:12mm 14mm 14mm;margin:14px auto;background:#fff;position:relative;box-shadow:0 2px 14px rgba(0,0,0,.12)}
.hd{display:flex;justify-content:space-between;align-items:center;border-bottom:3px solid #C0392B;padding-bottom:6px}.hd img{height:34px}.hd .t{text-align:right}.hd .t b{font-size:15pt;color:#C0392B}.hd .t div{font-size:8.5pt;color:#777}
.g{color:#1E8449}.r{color:#B03A2E}
table{width:100%;border-collapse:collapse;font-size:8.8pt}th{background:#C0392B;color:#fff;text-align:left;padding:4px 6px;font-weight:600}td{padding:4px 6px;border-bottom:1px solid #eee}td.n,th.n{text-align:right;white-space:nowrap}
tr.mh td{background:#F6F2EE;font-weight:800}.lt{background:#FDECEA;color:#B03A2E;border-radius:6px;padding:0 5px;font-size:7.5pt}
.ft{position:absolute;bottom:6mm;left:14mm;right:14mm;display:flex;justify-content:space-between;font-size:7.5pt;color:#999}
.dk{background:#FFFFFF;color:#2B2622;padding:7mm 12mm 11mm;height:210mm;overflow:hidden}.dk .g{color:#1E8449}.dk .r{color:#C0392B}.dk .sub{color:#7A7069;font-size:8pt}
.top{display:flex;justify-content:space-between;gap:8mm;align-items:center}.logo{background:#fff;border-radius:9px;padding:5px 10px;display:inline-block}.logo img{height:26px;display:block}
.kk{font-size:7.5pt;letter-spacing:.16em;text-transform:uppercase;color:#7A7069;margin-top:9px}.now{font-size:30pt;font-weight:800;letter-spacing:-1px;line-height:1.05;margin:2px 0}.now small{font-size:10pt;color:#7A7069;font-weight:500;letter-spacing:0}
.tanks{display:flex;gap:4mm}.tanks.wide{margin-top:3mm}.tanks.wide .tk{flex:1}.tk{background:#F7F4F1;border-radius:14px;padding:6px 8px 7px;text-align:center}.tt{font-weight:700;font-size:10pt}.ts{font-size:7.5pt;color:#7A7069}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:4mm;margin-top:3mm}.tiles div{background:#F7F4F1;border-radius:11px;padding:6px 11px}.tiles span{font-size:6.8pt;color:#7A7069;text-transform:uppercase;letter-spacing:.12em}.tiles b{display:block;font-size:13pt;margin-top:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tiles .warn{background:#FDECEA}.tiles .safe{background:#E8F6EE}
.pn{background:#F7F4F1;border:1px solid #EEE8E3;border-radius:14px;padding:7px 12px;margin-top:3mm}.pn h4{margin:0;font-size:10.5pt;color:#2B2622}.two{display:grid;grid-template-columns:1fr 1fr;gap:4mm}
.li{display:flex;align-items:center;gap:8px;padding:2.5px 0;border-bottom:1px solid #EAE4DE}.li:last-child{border:0}.li i{font-style:normal;width:22px;height:22px;border-radius:7px;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:8pt;flex:none}
.li .w{flex:1;min-width:0}.li .w b{display:block;font-size:8.6pt;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.li .w small{color:#7A7069;font-size:7pt}.li .a{font-weight:800;font-size:9.5pt;white-space:nowrap}
.note{margin-top:6px;border-radius:9px;padding:6px 10px;background:#FDECEA;font-size:7.8pt;color:#8E1F16}.note.ok{background:#E8F6EE;color:#1E6B3A}.note b{display:block;font-size:8.6pt}
.dk .ft{color:#999999}
@media print{body{background:#fff}.bar{display:none}.pg{margin:0;box-shadow:none;page-break-after:always}}"""
    head = f'<div class="hd">{f"<img src={chr(34)}{logo}{chr(34)}>" if logo else "<b>INFINIA</b>"}<div class="t"><b>Cash Forecast</b><div>{e(_period(f))} · prepared {e(stamp)} · Accounts</div></div></div>'
    p1 = f"""<div class="pg dk ink-keep"><div class="top"><div><div class="logo">{f"<img src={chr(34)}{logo}{chr(34)}>" if logo else "<b style='color:#C0392B'>INFINIA</b>"}</div>
<div class="kk">Cash forecast · {e(_period(f))} · prepared {e(stamp)}</div><div class="now">AED {m0(bank["now"])} <small>in the bank today</small></div><div class="sub">{e(stmt)}</div></div>
{"" if many else f'<div class="tanks">{tanks}</div>'}</div>{f'<div class="tanks wide">{tanks}</div>' if many else ""}
<div class="tiles">{tiles}</div>
<div class="pn"><div style="display:flex;justify-content:space-between"><h4>The weeks ahead</h4><div class="sub"><span class="g">■</span> in &nbsp;<span class="r">■</span> out &nbsp;<span style="color:#2B2622">●</span> bank at the end of each {"week" if step == 7 else "two weeks" if step == 14 else "four weeks"} &nbsp;<span class="r">┅</span> keep at least {short(keep)}</div></div>{weeks_svg(f, H=136 if many else 180)}</div>
<div class="two"><div class="pn"><h4>Biggest payments coming</h4>{big}</div><div class="pn"><h4>Coming in</h4>{cin}{note}</div></div>
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
    # page 1 - the Tanks, the same page as the screen and the Preview
    bank = f["bank"]; mos = f["months"]; shown = mos[:6]; many = len(shown) > 3; full = tank_fill(f)
    BG, PN, MUT = "#FFFFFF", "#F7F4F1", "#7A7069"
    G2, R2 = "#1E8449", "#C0392B"
    cv.setFillColor(C(BG)); cv.rect(0, 0, W, H, stroke=0, fill=1)
    rrect(M, H - 62, 118, 32, "#FFFFFF", r=7)
    drawn = False
    if logo_path:
        try:
            cv.drawImage(logo_path, M + 8, H - 58, height=24, width=102, preserveAspectRatio=True, anchor="w", mask="auto"); drawn = True
        except Exception:
            pass
    if not drawn:
        txt(M + 10, H - 51, "INFINIA", 14, RED, True)
    txt(M, H - 80, f"CASH FORECAST · {_period(f).upper()} · PREPARED {stamp}", 7, MUT)
    txt(M, H - 110, f"AED {m0(bank['now'])}", 27, "#2B2622", True)
    cv.setFont("Helvetica-Bold", 27); nw = cv.stringWidth(f"AED {m0(bank['now'])}", "Helvetica-Bold", 27)
    txt(M + nw + 8, H - 110, "in the bank today", 9.5, MUT)
    txt(M, H - 124, " · ".join(f"{b['bank']} statement {dmy(b['as_of'])}" for b in bank["banks"]) or "no statement uploaded", 7.5, MUT)
    import math
    def ring(cx, cy, r, sw, m):
        c = m["closing"]; fr = max(0, min(1, c / full))
        cv.setLineWidth(sw); cv.setStrokeColor(C("#EAE4DE")); cv.circle(cx, cy, r, stroke=1, fill=0)
        if fr > 0:
            cv.setStrokeColor(C(tank_colour(c, keep))); cv.setLineCap(1)
            pth = cv.beginPath(); pth.arc(cx - r, cy - r, cx + r, cy + r, startAng=90, extent=-359.9 * fr); cv.drawPath(pth, stroke=1, fill=0); cv.setLineCap(0)
        cv.setLineWidth(1)
        txt(cx, cy + 1, ("-" if c < 0 else "") + short(abs(c)), r * .42, R2 if c < keep else "#2B2622", True, center=True)
        txt(cx, cy - r * .3, tank_word(m, keep), max(5, r * .15), MUT, center=True)
    def tank_box(x, y, w, h, r, sw, m):
        rrect(x, y, w, h, PN, r=10)
        ring(x + w / 2, y + h - 10 - r - sw / 2, r, sw, m)
        txt(x + w / 2, y + 20, m["label"], 9.5 if not many else 8.5, "#2B2622", True, center=True)
        cv.setFont("Helvetica", 6.8); s1, s2 = f"+{m0(m['in'])}", f" · -{m0(m['out'])}"
        w1, w2 = cv.stringWidth(s1, "Helvetica", 6.8), cv.stringWidth(s2, "Helvetica", 6.8); x0 = x + w / 2 - (w1 + w2) / 2
        txt(x0, y + 9, s1, 6.8, G2); txt(x0 + w1, y + 9, s2, 6.8, R2)
    if not many:
        bw_, bh_, gap = 112, 130, 8
        x = W - M - len(shown) * bw_ - (len(shown) - 1) * gap
        for k, m in enumerate(shown):
            tank_box(x + k * (bw_ + gap), H - 32 - bh_, bw_, bh_, 38, 9, m)
        top = H - 32 - bh_ - 10
    else:
        gap = 8; bw_ = (W - 2 * M - gap * (len(shown) - 1)) / len(shown); bh_ = 94
        for k, m in enumerate(shown):
            tank_box(M + k * (bw_ + gap), H - 136 - bh_, bw_, bh_, 26, 7, m)
        top = H - 136 - bh_ - 10
    # four tiles
    bg = f["biggest"][0] if f["biggest"] else None; below = f.get("below")
    tiles = [(f"GOING OUT · {len(mos)} MONTHS", m0(f["total_out"]), "#2B2622", PN), ("COMING IN", m0(f["total_in"]), G2, PN),
             ("BIGGEST", (bg["what"].split(" · ")[0][:22] + " " + short(bg["amount"])) if bg else "-", "#2B2622", PN),
             ((f"WATCH · KEEP AT LEAST {short(keep)}", f"{dmy(below['date'])} · below {short(keep)}", R2, "#FDECEA") if below
              else (f"SAFE · KEEP AT LEAST {short(keep)}", f"lowest {m0(f['low']['amount'])}", G2, "#E8F6EE"))]
    tw_ = (W - 2 * M - 3 * 8) / 4; th = 38
    for k, (l, v, col, fill) in enumerate(tiles):
        x = M + k * (tw_ + 8); rrect(x, top - th, tw_, th, fill, r=9)
        txt(x + 10, top - 13, l, 6.3, MUT); txt(x + 10, top - 30, v, 12.5, col, True)
    top -= th + 10
    # the weeks ahead
    step, wk = weeks(f); ph = 128 if many else 150
    rrect(M, top - ph, W - 2 * M, ph, PN, r=12)
    txt(M + 12, top - 16, "The weeks ahead", 10, "#2B2622", True)
    txt(W - M - 12, top - 16, f"green in · red out · black: the bank at the end of each {'week' if step == 7 else 'two weeks' if step == 14 else 'four weeks'} · dashed: keep at least {short(keep)}", 6.8, MUT, right=True)
    if wk:
        gx0, gx1 = M + 20, W - M - 20; n = len(wk); colW = (gx1 - gx0) / n; bwd = min(16, colW * .3)
        base = top - ph * .62; barH = ph * .2; balTop = top - 30; balH = ph * .22
        maxF = max([1] + [max(w_[1], w_[2]) for w_ in wk])
        bals = [w_[3] for w_ in wk] + [bank["now"], keep]; hi, lo = max(bals), min(bals)
        Yb = lambda v: balTop - balH * (hi - v) / ((hi - lo) or 1)
        cv.setStrokeColor(C("#DDD6CF")); cv.line(gx0, base, gx1, base)
        cv.setStrokeColor(C(R2)); cv.setDash(3, 3); cv.line(gx0, Yb(keep), gx1, Yb(keep)); cv.setDash(); txt(gx1, Yb(keep) + 3, short(keep), 6.5, R2, right=True)
        pts = []
        for k, (a_, cin, cout, bal) in enumerate(wk):
            cx = gx0 + colW * k + colW / 2
            if cin:
                h_ = barH * cin / maxF; cv.setFillColor(C("#2ECC71")); cv.roundRect(cx - bwd - 1, base, bwd, max(1.5, h_), 2, stroke=0, fill=1); txt(cx - 1 - bwd / 2, base + h_ + 3, short(cin), 6, G2, center=True)
            if cout:
                h_ = barH * cout / maxF; cv.setFillColor(C("#E74C3C")); cv.roundRect(cx + 1, base - h_, bwd, max(1.5, h_), 2, stroke=0, fill=1)
                if h_ > 8:
                    txt(cx + 1 + bwd / 2, base - h_ - 8, short(cout), 6, R2, center=True)
            if n <= 20 or k % 2 == 0:
                txt(cx, top - ph + 8, f"{a_.day} {a_:%b}", 6.5, MUT, center=True)
            pts.append((cx, Yb(bal), bal))
        cv.setStrokeColor(C("#2B2622")); cv.setLineWidth(1.3)
        for (x1, y1, _), (x2, y2, _) in zip(pts, pts[1:]):
            cv.line(x1, y1, x2, y2)
        cv.setLineWidth(1)
        for k, (x_, y_, v) in enumerate(pts):
            col = R2 if v < keep else "#2B2622"; cv.setFillColor(C(col)); cv.circle(x_, y_, 2.6, stroke=0, fill=1)
            if n <= 14 or k % 2 == 0:
                txt(x_, y_ + 5, short(v), 6.3, col, center=True)
    top -= ph + 10
    # biggest payments | coming in
    hw = (W - 2 * M - 10) / 2; hh = top - 30
    ico = {"cheque": ("C", "#EEF2FA", "#3B5998"), "salary": ("S", "#F3EEFA", "#6B3FA0"), "sub": ("S", "#FFF1D6", "#8A5A00"), "expected": ("F", "#FDECEA", "#C0392B"), "client": ("B", "#E8F6EE", "#1E8449")}
    def lines_box(x, title, rows_, amt_col):
        rrect(x, 30, hw, hh, PN, r=12); txt(x + 12, top - 16, title, 10, "#2B2622", True)
        yy = top - 34; rowh = 21 if not many else 18
        for t_, what, sub, amt in rows_:
            if yy < 30 + 8:
                break
            if t_:
                i_, b_, c_ = ico.get(t_, ("·", "#333333", "#2B2622"))
                rrect(x + 12, yy - 7, 15, 15, b_, r=4); txt(x + 19.5, yy - 3, i_, 7, c_, True, center=True)
            txt(x + 33, yy + 1, what[:52], 8, "#2B2622", True); txt(x + 33, yy - 7, sub[:70], 6.3, MUT)
            txt(x + hw - 12, yy - 3, amt, 9, amt_col, True, right=True)
            cv.setStrokeColor(C("#EAE4DE")); cv.line(x + 12, yy - 11, x + hw - 12, yy - 11); yy -= rowh
        return yy
    lines_box(M, "Biggest payments coming", [(g["type"], g["what"] + (f" ({g['n']})" if g["n"] > 1 and g["type"] == "sub" else ""),
              ("date passed" if g["late"] else " · ".join(dmy(d)[:5] for d in g["dates"][:3])) + (" · forecast" if g["type"] == "expected" else " · cheque" if g["type"] == "cheque" else ""), m0(g["amount"])) for g in f["biggest"][:5]] or [("", "Nothing going out", "", "")], R2)
    x2 = M + hw + 10
    yy = lines_box(x2, "Coming in", [("client", i["what"].split(" · ")[0], "expected " + dmy(i["date"])[:5], m0(i["in"])) for i in f["coming"][:3]] or [("", "No client bill waiting for payment", "", "")], G2)
    last_in = f["coming"][-1]["date"] if f["coming"] else None
    quiet = (date.fromisoformat(mos[-1]["to"]) - date.fromisoformat(last_in)).days if (last_in and mos) else None
    bad_ = not f["coming"] or quiet > 30
    rrect(x2 + 10, 38, hw - 20, 30, "#FDECEA" if bad_ else "#E8F6EE", r=7)
    txt(x2 + 18, 56, ("Nothing expected in after " + dmy(last_in) + "." if last_in else "Nothing expected in.") if bad_ else "Client money keeps coming in.", 8, R2 if bad_ else G2, True)
    txt(x2 + 18, 45, (f"The bank goes below {m0(keep)} on {dmy(below['date'])} - a client payment before then keeps it above." if below else "Payments still go out every month.") if bad_ else f"{len(f['coming'])} payment(s) expected in the period.", 6.8, "#8E1F16" if bad_ else "#1E6B3A")
    txt(M, 14, "Infinia Contracting LLC · Cash forecast · from the app: bank statement, PDC register, Estimation, payroll and Accounts' forecast", 6.5, "#999999")
    txt(W - M, 14, "Page 1", 6.5, "#999999", right=True)
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

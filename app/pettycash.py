"""Petty cash register - Store & Purchasing > Petty cash.

The store keeper enters each bill from site as he pays it, and each
sum of cash he is given; the office sees the running balance the same
day instead of a folder of receipts at month end. The paper follows
the company's own register: date, description, supplier / contact,
site, received, paid, balance, then Prepared / Checked / Approved.

A month shows the balance brought forward from everything before it,
so each month's sheet stands alone and the months chain together.
"""
import io
from datetime import date, timedelta
from html import escape
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session

import main as M
import models, auth, export_web
from database import get_db

router = APIRouter()
RIGHTS = ("store", "storekeeper", "approvals")
PC = Depends(M.require_any_screen(*RIGHTS))
COMPANY = "INFINIA CONTRACTING L.L.C."


def _may(user):
    if not any(r in M.effective_permissions(user) for r in RIGHTS):
        raise HTTPException(status_code=403, detail="Petty cash is for the store and the office.")


def _month_bounds(month):
    """'2026-09' -> first and last day of that month."""
    try:
        y, m = (int(x) for x in str(month).split("-")[:2])
        a = date(y, m, 1)
    except Exception:
        t = M._dubai_today()
        a = t.replace(day=1)
    b = date(a.year + (a.month == 12), a.month % 12 + 1, 1) - timedelta(days=1)
    return a, b


def _money(v):
    return f"{v:,.2f}"


def register(db, month):
    a, b = _month_bounds(month)
    before = db.query(models.PettyCash).filter(models.PettyCash.on_date < a).all()
    opening = round(sum((x.received or 0) - (x.paid or 0) for x in before), 2)
    rows = (db.query(models.PettyCash)
              .filter(models.PettyCash.on_date >= a, models.PettyCash.on_date <= b)
              .order_by(models.PettyCash.on_date, models.PettyCash.id).all())
    users = {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}
    bal, out = opening, []
    for x in rows:
        bal = round(bal + (x.received or 0) - (x.paid or 0), 2)
        out.append({"id": x.id, "date": x.on_date.isoformat(), "description": x.description or "",
                    "supplier": x.supplier or "", "site": x.site or "",
                    "received": round(x.received or 0, 2), "paid": round(x.paid or 0, 2), "balance": bal,
                    "by": users.get(x.updated_by or x.created_by, "")})
    rec = round(sum(r["received"] for r in out), 2)
    paid = round(sum(r["paid"] for r in out), 2)
    by_site = {}
    for r in out:
        if r["paid"]:
            k = r["site"] or "Office / general"
            by_site[k] = round(by_site.get(k, 0) + r["paid"], 2)
    return {"month": f"{a:%Y-%m}", "label": f"{a:%B %Y}", "from": a.isoformat(), "to": b.isoformat(),
            "opening": opening, "rows": out, "received": rec, "paid": paid,
            "closing": round(opening + rec - paid, 2),
            "by_site": [{"site": k, "paid": v} for k, v in sorted(by_site.items(), key=lambda kv: -kv[1])]}


@router.get("/store/petty-cash")
def list_petty_cash(month: str = "", db: Session = Depends(get_db), user: models.User = PC):
    return register(db, month)


def _clean(payload):
    d = M._as_date(payload.get("date"))
    if not d:
        raise HTTPException(status_code=400, detail="Which date is the bill?")
    if d > M._dubai_today():
        raise HTTPException(status_code=400, detail="That date is in the future.")
    desc = str(payload.get("description") or "").strip()
    if not desc:
        raise HTTPException(status_code=400, detail="What was it for? Type a description.")
    def num(k):
        try:
            v = float(str(payload.get(k) or 0).replace(",", ""))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"{k.title()} must be a number.")
        if v < 0:
            raise HTTPException(status_code=400, detail=f"{k.title()} cannot be negative.")
        return round(v, 2)
    rec, paid = num("received"), num("paid")
    if not rec and not paid:
        raise HTTPException(status_code=400, detail="Enter the amount paid (or the cash received).")
    if rec and paid:
        raise HTTPException(status_code=400, detail="One line is either cash received or a bill paid - not both.")
    return {"on_date": d, "description": desc[:200], "supplier": str(payload.get("supplier") or "").strip()[:120],
            "site": str(payload.get("site") or "").strip()[:40], "received": rec, "paid": paid}


@router.post("/store/petty-cash")
def add_petty_cash(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = PC):
    x = models.PettyCash(**_clean(payload), created_by=user.id, updated_by=user.id)
    db.add(x); db.commit()
    M.log_action(db, user.id, "petty_cash_add",
                 f"{x.on_date} {x.description} {'+' + _money(x.received) if x.received else '-' + _money(x.paid)}")
    return {"ok": True, "id": x.id}


@router.put("/store/petty-cash/{pid}")
def edit_petty_cash(pid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = PC):
    x = db.get(models.PettyCash, pid)
    if not x:
        raise HTTPException(status_code=404, detail="That line is no longer there.")
    for k, v in _clean(payload).items():
        setattr(x, k, v)
    x.updated_by = user.id
    db.commit()
    M.log_action(db, user.id, "petty_cash_edit", f"#{pid} {x.on_date} {x.description}")
    return {"ok": True}


@router.delete("/store/petty-cash/{pid}")
def delete_petty_cash(pid: int, db: Session = Depends(get_db), user: models.User = PC):
    x = db.get(models.PettyCash, pid)
    if not x:
        raise HTTPException(status_code=404, detail="That line is no longer there.")
    M.log_action(db, user.id, "petty_cash_delete", f"#{pid} {x.on_date} {x.description} {x.received or -x.paid}")
    db.delete(x); db.commit()
    return {"ok": True}


# ---- The paper -----------------------------------------------------------

RED = "#B7322A"
COLS = ("Date", "Description", "Supplier / Contact", "Site", "Received (AED)", "Paid (AED)", "Balance (AED)")


def _dmy(iso):
    d = M._as_date(iso)
    return d.strftime("%d-%b-%y") if d else ""


def _lines(r):
    """Every line of the sheet, the brought-forward first."""
    out = [("", "Balance brought forward", "", "", "", "", r["opening"], "bf")]
    for x in r["rows"]:
        out.append((_dmy(x["date"]), x["description"], x["supplier"], x["site"],
                    x["received"] or "", x["paid"] or "", x["balance"], ""))
    return out


def _html(r, pdf_url, excel_url):
    logo = export_web.logo_data_uri()
    m = lambda v: _money(v) if v not in ("", None) else ""
    body = "".join(
        f"<tr class='{k}'><td>{escape(d)}</td><td class='l'>{escape(ds)}</td><td class='l'>{escape(s)}</td><td>{escape(str(st))}</td>"
        f"<td class='n'>{m(rc)}</td><td class='n'>{m(pd)}</td><td class='n b{' neg' if bal < 0 else ''}'>{m(bal)}</td></tr>"
        for d, ds, s, st, rc, pd, bal, k in _lines(r))
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Petty Cash - {escape(r['label'])}</title><style>
*{{box-sizing:border-box}} body{{margin:0;background:#ECEEF1;font:12.5px/1.4 Arial,Helvetica,sans-serif;color:#1d1d1d}}
.bar{{position:sticky;top:0;background:#fff;border-bottom:1px solid #ddd;padding:10px 16px;display:flex;gap:8px;justify-content:flex-end}}
.bar a,.bar button{{font:600 13px Arial;padding:8px 14px;border-radius:6px;border:1px solid #ddd;background:#fff;color:#222;text-decoration:none;cursor:pointer}}
.bar .p{{background:{RED};border-color:{RED};color:#fff}}
.page{{max-width:1000px;margin:18px auto;background:#fff;padding:30px 36px;box-shadow:0 2px 10px rgba(0,0,0,.08)}}
.top{{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:2px solid {RED};padding-bottom:10px}}
.top img{{height:30px}} h1{{margin:0;font-size:18px;letter-spacing:.08em;color:{RED};text-align:right}}
.meta{{display:flex;justify-content:space-between;gap:20px;margin:12px 0;font-size:12.5px}} .meta span{{color:#777}} .meta b{{margin-left:6px}}
.wrap{{overflow-x:auto}} table{{width:100%;border-collapse:collapse;min-width:720px}}
th{{background:{RED};color:#fff;font-size:11px;letter-spacing:.04em;padding:7px 8px;text-align:center}}
td{{padding:6px 8px;border-bottom:1px solid #e3e3e3;text-align:center}} td.l{{text-align:left}} td.n{{text-align:right;font-variant-numeric:tabular-nums}}
td.b{{font-weight:600}} td.neg{{color:{RED}}} tr.bf td{{background:#FBF6F4;font-style:italic}}
tbody tr:nth-child(even):not(.bf) td{{background:#FAFAFA}}
tfoot td{{font-weight:700;background:#F3F1EF;border-top:1.5px solid #222;border-bottom:none}}
.sum{{display:flex;gap:14px;margin-top:14px;flex-wrap:wrap}} .sum div{{flex:1;min-width:150px;border:1px solid #e3e3e3;border-radius:6px;padding:8px 12px}}
.sum span{{display:block;font-size:11px;color:#777;text-transform:uppercase;letter-spacing:.05em}} .sum b{{font-size:15px}}
.sign{{display:grid;grid-template-columns:repeat(3,1fr);gap:40px;margin-top:56px}} .sign div{{border-top:1px solid #222;padding-top:6px;text-align:center;font-size:12px}}
@media print{{.bar{{display:none}} body{{background:#fff}} .page{{box-shadow:none;margin:0;max-width:none;padding:0}}}}
@media(max-width:640px){{.page{{padding:16px;margin:0}} .sign{{gap:14px}}}}
</style></head><body>
<div class="bar"><button onclick="print()">Print</button><a href="{escape(excel_url)}">Excel</a><a class="p" href="{escape(pdf_url)}">Download PDF</a></div>
<div class="page">
 <div class="top"><div>{f'<img src="{logo}" alt="">' if logo else '<b>INFINIA</b>'}</div><h1>PETTY CASH REGISTER</h1></div>
 <div class="meta"><div><span>Company</span><b>{COMPANY}</b></div><div><span>Month / Period</span><b>{escape(r['label'])}</b></div></div>
 <div class="wrap"><table><thead><tr>{''.join(f'<th>{c}</th>' for c in COLS)}</tr></thead><tbody>{body}</tbody>
 <tfoot><tr><td colspan="4" class="l">TOTAL</td><td class="n">{_money(r['received'])}</td><td class="n">{_money(r['paid'])}</td><td class="n">{_money(r['closing'])}</td></tr></tfoot></table></div>
 <div class="sum"><div><span>Brought forward</span><b>{_money(r['opening'])}</b></div><div><span>Received</span><b>{_money(r['received'])}</b></div>
  <div><span>Paid</span><b>{_money(r['paid'])}</b></div><div><span>Balance in hand</span><b>{_money(r['closing'])}</b></div></div>
 <div class="sign"><div>Prepared By</div><div>Checked By</div><div>Approved By</div></div>
</div></body></html>"""


def _pdf(r):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT, TA_CENTER
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepTogether
    R = colors.HexColor(RED)
    base = ParagraphStyle("b", fontName="Helvetica", fontSize=8.5, leading=10.5)
    bold = ParagraphStyle("bb", parent=base, fontName="Helvetica-Bold")
    cen = ParagraphStyle("c", parent=base, alignment=TA_CENTER)
    rt = ParagraphStyle("r", parent=base, alignment=TA_RIGHT)
    rtb = ParagraphStyle("rb", parent=bold, alignment=TA_RIGHT)
    hd = ParagraphStyle("h", parent=bold, fontSize=8, textColor=colors.white, alignment=TA_CENTER)
    P = lambda t, st=base: Paragraph(escape(str(t)), st)
    page = landscape(A4)
    W = page[0] - 24 * mm
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=page, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=10 * mm, bottomMargin=10 * mm,
                            title=f"Petty Cash - {r['label']}")
    logo = export_web._logo_image(42)
    top = Table([[logo or P("INFINIA", bold), Paragraph("PETTY CASH REGISTER", ParagraphStyle("t", parent=bold, fontSize=15, leading=19, textColor=R, alignment=TA_RIGHT))]],
                colWidths=[W / 2, W / 2])
    top.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("LINEBELOW", (0, 0), (-1, 0), 1.5, R),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    meta = Table([[Paragraph(f"<font color='#777777'>Company</font>&nbsp;&nbsp;<b>{COMPANY}</b>", base),
                   Paragraph(f"<font color='#777777'>Month / Period</font>&nbsp;&nbsp;<b>{escape(r['label'])}</b>", rt)]], colWidths=[W / 2, W / 2])
    meta.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 6)]))
    m = lambda v: _money(v) if v not in ("", None) else ""
    data = [[P(c.upper(), hd) for c in COLS]]
    for d, ds, s, st, rc, pd, bal, k in _lines(r):
        data.append([P(d, cen), P(ds), P(s), P(st, cen), P(m(rc), rt), P(m(pd), rt), P(m(bal), rtb)])
    data.append([P("TOTAL", bold), "", "", "", P(_money(r["received"]), rtb), P(_money(r["paid"]), rtb), P(_money(r["closing"]), rtb)])
    widths = [W * f for f in (.09, .29, .20, .08, .11, .11, .12)]
    t = Table(data, colWidths=widths, repeatRows=1)
    st = [("BACKGROUND", (0, 0), (-1, 0), R), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("LINEBELOW", (0, 1), (-1, -2), .3, colors.HexColor("#DDDDDD")),
          ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#FBF6F4")),
          ("SPAN", (0, -1), (3, -1)), ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F3F1EF")),
          ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black)]
    for i in range(3, len(data) - 1, 2):
        st.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FAFAFA")))
    t.setStyle(TableStyle(st))
    sign = Table([[P("Prepared By", cen), "", P("Checked By", cen), "", P("Approved By", cen)]],
                 colWidths=[W * .26, W * .11, W * .26, W * .11, W * .26])
    sign.setStyle(TableStyle([("LINEABOVE", (0, 0), (0, 0), .8, colors.black), ("LINEABOVE", (2, 0), (2, 0), .8, colors.black),
                              ("LINEABOVE", (4, 0), (4, 0), .8, colors.black)]))
    doc.build([top, meta, Spacer(1, 6), t, KeepTogether([Spacer(1, 40), sign])])
    buf.seek(0)
    return buf


def _excel(r):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    wb = Workbook(); ws = wb.active; ws.title = "Petty Cash"
    R = RED.lstrip("#")
    fill = PatternFill("solid", fgColor=R)
    thin = Side(style="thin", color="DDDDDD")
    for col, w in zip("ABCDEFG", (12, 38, 28, 10, 16, 16, 16)):
        ws.column_dimensions[col].width = w
    ws.merge_cells("A1:G1")
    ws["A1"] = "PETTY CASH REGISTER"; ws["A1"].font = Font(bold=True, size=15, color=R)
    ws.row_dimensions[1].height = 34
    try:
        from openpyxl.drawing.image import Image as XLImage
        import os
        if os.path.exists(export_web.LOGO_PATH):
            img = XLImage(export_web.LOGO_PATH); img.height = 28; img.width = int(28 * 995 / 168)
            ws.add_image(img, "A1")
    except Exception:
        pass
    ws["A1"].alignment = Alignment(horizontal="right", vertical="center")
    ws["A2"] = "Company"; ws["A2"].font = Font(color="777777"); ws["B2"] = COMPANY; ws["B2"].font = Font(bold=True)
    ws["E2"] = "Month / Period"; ws["E2"].font = Font(color="777777"); ws["F2"] = r["label"]; ws["F2"].font = Font(bold=True)
    for i, c in enumerate(COLS, 1):
        cell = ws.cell(4, i, c.upper()); cell.font = Font(bold=True, color="FFFFFF"); cell.fill = fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[4].height = 22
    row = 5
    first = row
    ws.cell(row, 2, "Balance brought forward"); ws.cell(row, 7, r["opening"]).number_format = "#,##0.00"
    for c in range(1, 8):
        ws.cell(row, c).font = Font(italic=True, bold=(c == 7)); ws.cell(row, c).fill = PatternFill("solid", fgColor="FBF6F4")
        ws.cell(row, c).border = Border(bottom=thin)
    row += 1
    for x in r["rows"]:
        ws.cell(row, 1, M._as_date(x["date"])).number_format = "dd-mmm-yy"
        ws.cell(row, 2, x["description"]); ws.cell(row, 3, x["supplier"]); ws.cell(row, 4, x["site"])
        if x["received"]: ws.cell(row, 5, x["received"])
        if x["paid"]: ws.cell(row, 6, x["paid"])
        # The balance is a formula, as on the office's own sheet.
        ws.cell(row, 7, f"=G{row - 1}+E{row}-F{row}").font = Font(bold=True)
        for c in (5, 6, 7):
            ws.cell(row, c).number_format = "#,##0.00"
        ws.cell(row, 1).alignment = Alignment(horizontal="center"); ws.cell(row, 4).alignment = Alignment(horizontal="center")
        for c in range(1, 8):
            ws.cell(row, c).border = Border(bottom=thin)
        row += 1
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
    ws.cell(row, 1, "TOTAL").font = Font(bold=True)
    ws.cell(row, 5, f"=SUM(E{first + 1}:E{row - 1})"); ws.cell(row, 6, f"=SUM(F{first + 1}:F{row - 1})")
    ws.cell(row, 7, f"=G{first}+E{row}-F{row}")
    for c in range(1, 8):
        cell = ws.cell(row, c); cell.fill = PatternFill("solid", fgColor="F3F1EF")
        cell.border = Border(top=Side(style="medium", color="000000"))
        if c >= 5: cell.number_format = "#,##0.00"; cell.font = Font(bold=True)
    row += 4
    for a, b, t in (("A", "B", "Prepared By"), ("D", "E", "Checked By"), ("F", "G", "Approved By")):
        ws.merge_cells(f"{a}{row}:{b}{row}")
        c = ws[f"{a}{row}"]; c.value = t; c.alignment = Alignment(horizontal="center")
        c.border = Border(top=Side(style="thin", color="000000"))
    ws.freeze_panes = "A5"
    ws.page_setup.orientation = "landscape"; ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1; ws.page_setup.fitToHeight = 0
    ws.print_title_rows = "4:4"
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return buf


@router.get("/export/store/petty-cash")
def export_petty_cash(token: str, month: str = "", format: str = "pdf", db: Session = Depends(get_db)):
    _may(auth.get_download_user_from_token(token, db))
    r = register(db, month)
    name = f"Petty_Cash_{r['month']}"
    if format == "excel":
        return StreamingResponse(_excel(r), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 headers={"Content-Disposition": f"attachment; filename={name}.xlsx"})
    return StreamingResponse(_pdf(r), media_type="application/pdf",
                             headers={"Content-Disposition": f"attachment; filename={name}.pdf"})


@router.get("/export/store/petty-cash/view", response_class=HTMLResponse)
def view_petty_cash(token: str, month: str = "", db: Session = Depends(get_db)):
    user = auth.get_download_user_from_token(token, db)
    _may(user)
    r = register(db, month)
    t = auth.create_view_token(user.username)
    base = "/export/store/petty-cash?" + urlencode({"month": r["month"], "token": t})
    return HTMLResponse(_html(r, base + "&format=pdf", base + "&format=excel"))

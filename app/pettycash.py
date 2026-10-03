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
# Three cash boxes, each behind its own right (ticked on Settings >
# Access): the site box the store keeper runs, the PRO's, and the
# office's. A login sees only the boxes it is given - the site never
# sees the PRO's, only the chief accountant sees the office's.
BOOKS = {"site": ("Site petty cash", "petty_site"),
         "pro": ("PRO petty cash", "petty_pro"),
         "office": ("Office petty cash", "petty_office"),
         "naveen": ("Naveen petty cash", "petty_naveen"),
         "praveen": ("Praveen petty cash", "petty_praveen")}
# The directors' books are kept the other way round, as on their own
# sheets: DR is what the director paid for the company (what it owes
# him goes up), CR what was paid back to him. A bill he paid is kept
# under "paid", so spending by project reads the same in every book.
DIRECTORS = {"naveen": "Naveen", "praveen": "Praveen"}


def terms(book):
    """The words and the sign a book is kept with."""
    n = DIRECTORS.get(book)
    if n:
        return {"director": True, "sign": -1, "out": f"Paid by {n}", "in": f"Repaid to {n}",
                "out_col": "DR - Paid by " + n, "in_col": "CR - Repaid to " + n,
                "balance": f"Due to {n}", "balance_col": "Balance due", "supplier": "", "site": "Project"}
    return {"director": False, "sign": 1, "out": "Paid", "in": "Received", "out_col": "Paid", "in_col": "Received",
            "balance": "Balance in hand", "balance_col": "Balance", "supplier": "Supplier / Contact", "site": "Site"}
RIGHTS = tuple(r for _, r in BOOKS.values())
PC = Depends(M.require_any_screen(*RIGHTS))
COMPANY = "INFINIA CONTRACTING L.L.C."


def _book(user, book):
    """The box asked for, if this login may open it."""
    book = (book or "site").strip().lower()
    if book not in BOOKS:
        raise HTTPException(status_code=400, detail="No such petty cash.")
    if BOOKS[book][1] not in M.effective_permissions(user):
        raise HTTPException(status_code=403, detail=f"You do not have access to {BOOKS[book][0]}.")
    return book


def _may(user, book="site"):
    return _book(user, book)


def _of_book(q, book):
    col = models.PettyCash.book
    return q.filter((col == book) | (col.is_(None)) | (col == "")) if book == "site" else q.filter(col == book)


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


def register(db, month, book="site"):
    """One month's register - or, for month "all", every line from the
    first entry (the full history, as the directors' sheets read)."""
    whole = str(month or "").strip().lower() == "all"
    a, b = (date(2000, 1, 1), date(2099, 12, 31)) if whole else _month_bounds(month)
    t = terms(book)
    sg = t["sign"]
    before = _of_book(db.query(models.PettyCash), book).filter(models.PettyCash.on_date < a).all()
    opening = round(sg * sum((x.received or 0) - (x.paid or 0) for x in before), 2)
    rows = (_of_book(db.query(models.PettyCash), book)
              .filter(models.PettyCash.on_date >= a, models.PettyCash.on_date <= b)
              .order_by(models.PettyCash.on_date, models.PettyCash.id).all())
    users = {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}
    bal, out = opening, []
    for x in rows:
        bal = round(bal + sg * ((x.received or 0) - (x.paid or 0)), 2)
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
    first = rows[0].on_date if rows else a
    label = (f"Full history - {first:%d %b %Y} to {M._dubai_today():%d %b %Y}" if whole else f"{a:%B %Y}")
    return {"book": book, "book_label": BOOKS[book][0], "terms": t, "month": "all" if whole else f"{a:%Y-%m}", "label": label,
            "from": a.isoformat(), "to": b.isoformat(), "all": whole,
            "opening": opening, "rows": out, "received": rec, "paid": paid,
            "closing": round(opening + sg * (rec - paid), 2),
            "by_site": [{"site": k, "paid": v} for k, v in sorted(by_site.items(), key=lambda kv: -kv[1])]}


@router.get("/store/petty-cash")
def list_petty_cash(month: str = "", book: str = "site", db: Session = Depends(get_db), user: models.User = PC):
    return register(db, month, _book(user, book))


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
    return {"on_date": d, "description": desc[:400], "supplier": str(payload.get("supplier") or "").strip()[:120],
            "site": str(payload.get("site") or "").strip()[:40], "received": rec, "paid": paid}


@router.post("/store/petty-cash")
def add_petty_cash(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = PC):
    book = _book(user, payload.get("book"))
    x = models.PettyCash(**_clean(payload), book=book, created_by=user.id, updated_by=user.id)
    db.add(x); db.commit()
    M.log_action(db, user.id, "petty_cash_add",
                 f"{BOOKS[book][0]}: {x.on_date} {x.description} {'+' + _money(x.received) if x.received else '-' + _money(x.paid)}")
    return {"ok": True, "id": x.id}


@router.put("/store/petty-cash/{pid}")
def edit_petty_cash(pid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = PC):
    x = db.get(models.PettyCash, pid)
    if not x:
        raise HTTPException(status_code=404, detail="That line is no longer there.")
    _book(user, x.book or "site")
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
    _book(user, x.book or "site")
    M.log_action(db, user.id, "petty_cash_delete", f"#{pid} {x.on_date} {x.description} {x.received or -x.paid}")
    db.delete(x); db.commit()
    return {"ok": True}


# ---- The paper -----------------------------------------------------------

RED = "#B7322A"


def _spec(r):
    """The paper's columns. A director's book shows DR before CR, as his
    own sheet does; a column with nothing in it for the period (no
    supplier, no site written on any line) is left off the paper rather
    than printed empty."""
    t = r["terms"]
    pair = (t["out_col"], t["in_col"]) if t["director"] else (t["in_col"], t["out_col"])
    cols = [("date", "Date", 9, 12), ("desc", "Description", 0, 0)]
    if t["supplier"] and any(x["supplier"] for x in r["rows"]):
        cols.append(("sup", t["supplier"], 20, 28))
    if any(x["site"] for x in r["rows"]):
        cols.append(("site", t["site"], 8, 10))
    cols += [("a1", pair[0] + " (AED)", 11, 16), ("a2", pair[1] + " (AED)", 11, 16), ("bal", t["balance_col"] + " (AED)", 12, 16)]
    rest = 100 - sum(w for _, _, w, _ in cols)
    xrest = max(46, 140 - sum(x for _, _, _, x in cols))
    return [{"key": k, "label": lab, "w": (w or rest) / 100, "xw": x or xrest} for k, lab, w, x in cols]


def _pair(r, received, paid):
    return (paid, received) if r["terms"]["director"] else (received, paid)


def _dmy(iso):
    d = M._as_date(iso)
    return d.strftime("%d-%b-%y") if d else ""


def _lines(r):
    """Every line of the sheet as {column: value}, the brought-forward first."""
    out = [{"date": "", "desc": "Balance brought forward", "sup": "", "site": "", "a1": "", "a2": "", "bal": r["opening"], "bf": True}]
    for x in r["rows"]:
        a1, a2 = _pair(r, x["received"] or "", x["paid"] or "")
        out.append({"date": _dmy(x["date"]), "iso": x["date"], "desc": x["description"], "sup": x["supplier"], "site": x["site"],
                    "a1": a1, "a2": a2, "bal": x["balance"], "bf": False})
    return out


def _sum_boxes(r):
    t = r["terms"]
    boxes = [(t["in"], r["received"]), (t["out"], r["paid"])]
    if t["director"]:
        boxes.reverse()
    return "".join(f"<div><span>{escape(k)}</span><b>{_money(v)}</b></div>" for k, v in boxes)


NUM = ("a1", "a2", "bal")


def _html(r, pdf_url, excel_url):
    logo = export_web.logo_data_uri()
    m = lambda v: _money(v) if v not in ("", None) else ""
    spec = _spec(r)
    def cell(c, ln):
        k = c["key"]
        if k in NUM:
            neg = " neg" if k == "bal" and ln["bal"] < 0 else ""
            return f"<td class='n{' b' if k == 'bal' else ''}{neg}'>{m(ln[k])}</td>"
        cls = "l" if k in ("desc", "sup") else ""
        return f"<td class='{cls}'>{escape(str(ln[k]))}</td>"
    body = "".join(f"<tr class='{'bf' if ln['bf'] else ''}'>" + "".join(cell(c, ln) for c in spec) + "</tr>" for ln in _lines(r))
    ntext = len(spec) - 3
    head = "".join(f'<th class="{"n" if c["key"] in NUM else ("l" if c["key"] in ("desc", "sup") else "")}">{escape(c["label"])}</th>' for c in spec)
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(r['book_label'])} - {escape(r['label'])}</title><style>
*{{box-sizing:border-box}} body{{margin:0;background:#ECEEF1;font:12.5px/1.4 Arial,Helvetica,sans-serif;color:#1d1d1d}}
.page{{max-width:1000px;margin:18px auto;background:#fff;padding:30px 36px;box-shadow:0 2px 10px rgba(0,0,0,.08)}}
.top{{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:2px solid {RED};padding-bottom:10px}}
.top img{{height:30px}} h1{{margin:0;font-size:18px;letter-spacing:.08em;color:{RED};text-align:right}}
.meta{{display:flex;justify-content:space-between;gap:20px;margin:12px 0;font-size:12.5px}} .meta span{{color:#777}} .meta b{{margin-left:6px}}
.wrap{{overflow-x:auto}} table{{width:100%;border-collapse:collapse;min-width:640px}}
th{{background:{RED};color:#fff;font-size:11px;letter-spacing:.04em;padding:7px 8px;text-align:center}} th.l{{text-align:left}} th.n{{text-align:right}}
td{{padding:6px 8px;border-bottom:1px solid #e3e3e3;text-align:center}} td.l{{text-align:left}} td.n{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
td:first-child,th:first-child{{white-space:nowrap;width:80px}}
td.b{{font-weight:600}} td.neg{{color:{RED}}} tr.bf td{{background:#FBF6F4;font-style:italic}}
tbody tr:nth-child(even):not(.bf) td{{background:#FAFAFA}}
tfoot td{{font-weight:700;background:#F3F1EF;border-top:1.5px solid #222;border-bottom:none}}
.sum{{display:flex;gap:14px;margin-top:14px;flex-wrap:wrap}} .sum div{{flex:1;min-width:150px;border:1px solid #e3e3e3;border-radius:6px;padding:8px 12px}}
.sum span{{display:block;font-size:11px;color:#777;text-transform:uppercase;letter-spacing:.05em}} .sum b{{font-size:15px}}
.sign{{display:grid;grid-template-columns:repeat(3,1fr);gap:40px;margin-top:56px}} .sign div{{border-top:1px solid #222;padding-top:6px;text-align:center;font-size:12px}}
@media print{{body{{background:#fff}} .page{{box-shadow:none;margin:0;max-width:none;padding:0}}}}
@media(max-width:640px){{.page{{padding:16px;margin:0}} .sign{{gap:14px}}}}
</style></head><body>
{export_web.preview_bar(r['book_label'] + " register", r['label'], pdf_url, excel_url)}
<div class="page">
 <div class="top"><div>{f'<img src="{logo}" alt="">' if logo else '<b>INFINIA</b>'}</div><h1>{escape(r['book_label'].upper())} REGISTER</h1></div>
 <div class="meta"><div><span>Company</span><b>{COMPANY}</b></div><div><span>Month / Period</span><b>{escape(r['label'])}</b></div></div>
 <div class="wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody>
 <tfoot><tr><td colspan="{ntext}" class="l">TOTAL</td>{''.join(f'<td class="n">{_money(v)}</td>' for v in _pair(r, r['received'], r['paid']))}<td class="n">{_money(r['closing'])}</td></tr></tfoot></table></div>
 <div class="sum"><div><span>Brought forward</span><b>{_money(r['opening'])}</b></div>{_sum_boxes(r)}
  <div><span>{escape(r['terms']['balance'])}</span><b>{_money(r['closing'])}</b></div></div>
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
    ital = ParagraphStyle("i", parent=base, fontName="Helvetica-Oblique")
    cen = ParagraphStyle("c", parent=base, alignment=TA_CENTER)
    rt = ParagraphStyle("r", parent=base, alignment=TA_RIGHT)
    rtb = ParagraphStyle("rb", parent=bold, alignment=TA_RIGHT)
    hd = ParagraphStyle("h", parent=bold, fontSize=8, textColor=colors.white, alignment=TA_CENTER)
    hdl = ParagraphStyle("hl", parent=hd, alignment=0)
    hdr = ParagraphStyle("hr", parent=hd, alignment=TA_RIGHT)
    P = lambda t, st=base: Paragraph(escape(str(t)), st)
    page = landscape(A4)
    W = page[0] - 24 * mm
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=page, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=10 * mm, bottomMargin=10 * mm,
                            title=f"{r['book_label']} - {r['label']}")
    logo = export_web._logo_image(42)
    top = Table([[logo or P("INFINIA", bold), Paragraph(escape(r["book_label"].upper() + " REGISTER"), ParagraphStyle("t", parent=bold, fontSize=15, leading=19, textColor=R, alignment=TA_RIGHT))]],
                colWidths=[W / 2, W / 2])
    top.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("LINEBELOW", (0, 0), (-1, 0), 1.5, R),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    meta = Table([[Paragraph(f"<font color='#777777'>Company</font>&nbsp;&nbsp;<b>{COMPANY}</b>", base),
                   Paragraph(f"<font color='#777777'>Month / Period</font>&nbsp;&nbsp;<b>{escape(r['label'])}</b>", rt)]], colWidths=[W / 2, W / 2])
    meta.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 6)]))
    m = lambda v: _money(v) if v not in ("", None) else ""
    spec = _spec(r)
    hstyle = lambda k: hdr if k in NUM else (hdl if k in ("desc", "sup") else hd)
    data = [[P(c["label"].upper(), hstyle(c["key"])) for c in spec]]
    for ln in _lines(r):
        row = []
        for c in spec:
            k = c["key"]
            if k in NUM:
                row.append(P(m(ln[k]), rtb if k == "bal" else rt))
            elif k == "desc":
                row.append(P(ln[k], ital if ln["bf"] else base))
            elif k == "sup":
                row.append(P(ln[k]))
            else:
                row.append(P(ln[k], cen))
        data.append(row)
    ntext = len(spec) - 3
    data.append([P("TOTAL", bold)] + [""] * (ntext - 1) + [*(P(_money(v), rtb) for v in _pair(r, r["received"], r["paid"])), P(_money(r["closing"]), rtb)])
    t = Table(data, colWidths=[W * c["w"] for c in spec], repeatRows=1)
    st = [("BACKGROUND", (0, 0), (-1, 0), R), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("LINEBELOW", (0, 1), (-1, -2), .3, colors.HexColor("#DDDDDD")),
          ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#FBF6F4")),
          ("SPAN", (0, -1), (ntext - 1, -1)), ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F3F1EF")),
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
    from openpyxl.utils import get_column_letter as L
    wb = Workbook(); ws = wb.active; ws.title = "Petty Cash"
    R = RED.lstrip("#")
    fill = PatternFill("solid", fgColor=R)
    thin = Side(style="thin", color="DDDDDD")
    spec = _spec(r)
    N = len(spec)
    cE, cF, cG = N - 2, N - 1, N        # the two amount columns and the balance
    E, F, G = L(cE), L(cF), L(cG)
    ntext = N - 3
    for i, c in enumerate(spec, 1):
        ws.column_dimensions[L(i)].width = c["xw"]
    ws.merge_cells(f"A1:{G}1")
    ws["A1"] = r["book_label"].upper() + " REGISTER"; ws["A1"].font = Font(bold=True, size=15, color=R)
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
    ws[f"{E}2"] = "Month / Period"; ws[f"{E}2"].font = Font(color="777777"); ws[f"{F}2"] = r["label"]; ws[f"{F}2"].font = Font(bold=True)
    for i, c in enumerate(spec, 1):
        cell = ws.cell(4, i, c["label"].upper()); cell.font = Font(bold=True, color="FFFFFF"); cell.fill = fill
        cell.alignment = Alignment(horizontal="right" if c["key"] in NUM else ("left" if c["key"] in ("desc", "sup") else "center"),
                                   vertical="center", wrap_text=True)
    ws.row_dimensions[4].height = 30
    row = 5
    first = row
    ws.cell(row, 2, "Balance brought forward"); ws.cell(row, cG, r["opening"]).number_format = "#,##0.00"
    for c in range(1, N + 1):
        ws.cell(row, c).font = Font(italic=True, bold=(c == cG)); ws.cell(row, c).fill = PatternFill("solid", fgColor="FBF6F4")
        ws.cell(row, c).border = Border(bottom=thin)
    row += 1
    for ln in _lines(r)[1:]:
        for i, c in enumerate(spec, 1):
            k = c["key"]
            if k == "date":
                ws.cell(row, i, M._as_date(ln["iso"])).number_format = "dd-mmm-yy"
                ws.cell(row, i).alignment = Alignment(horizontal="center", vertical="center")
            elif k in ("a1", "a2"):
                if ln[k]:
                    ws.cell(row, i, ln[k])
                ws.cell(row, i).number_format = "#,##0.00"
                ws.cell(row, i).alignment = Alignment(vertical="center")
            elif k == "bal":
                # The balance is a formula, as on the office's own sheet (the first
                # amount column adds: cash received, or for a director what he paid).
                ws.cell(row, i, f"={G}{row - 1}+{E}{row}-{F}{row}").font = Font(bold=True)
                ws.cell(row, i).number_format = "#,##0.00"
                ws.cell(row, i).alignment = Alignment(vertical="center")
            else:
                ws.cell(row, i, ln[k])
                ws.cell(row, i).alignment = (Alignment(horizontal="center", vertical="center") if k == "site"
                                             else Alignment(wrap_text=True, vertical="center"))      # long details wrap, never cut off
            ws.cell(row, i).border = Border(bottom=thin)
        row += 1
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=ntext)
    ws.cell(row, 1, "TOTAL").font = Font(bold=True)
    ws.cell(row, cE, f"=SUM({E}{first + 1}:{E}{row - 1})"); ws.cell(row, cF, f"=SUM({F}{first + 1}:{F}{row - 1})")
    ws.cell(row, cG, f"={G}{first}+{E}{row}-{F}{row}")
    for c in range(1, N + 1):
        cell = ws.cell(row, c); cell.fill = PatternFill("solid", fgColor="F3F1EF")
        cell.border = Border(top=Side(style="medium", color="000000"))
        if c >= cE: cell.number_format = "#,##0.00"; cell.font = Font(bold=True)
    row += 4
    third = max(1, N // 3)
    signs = ((1, third, "Prepared By"), (third + 1, 2 * third, "Checked By"), (2 * third + 1, N, "Approved By"))
    for a, b, t in signs:
        if b > a:
            ws.merge_cells(start_row=row, start_column=a, end_row=row, end_column=b)
        c = ws.cell(row, a); c.value = t; c.alignment = Alignment(horizontal="center")
        for col in range(a, b + 1):
            ws.cell(row, col).border = Border(top=Side(style="thin", color="000000"))
    ws.freeze_panes = "A5"
    ws.page_setup.orientation = "landscape"; ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1; ws.page_setup.fitToHeight = 0
    ws.print_title_rows = "4:4"
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return buf


@router.get("/export/store/petty-cash")
def export_petty_cash(token: str, month: str = "", format: str = "pdf", book: str = "site", db: Session = Depends(get_db)):
    book = _may(auth.get_download_user_from_token(token, db), book)
    r = register(db, month, book)
    name = f"{r['book_label'].replace(' ', '_')}_{r['month']}"
    if format == "excel":
        return StreamingResponse(_excel(r), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 headers={"Content-Disposition": f"attachment; filename={name}.xlsx"})
    return StreamingResponse(_pdf(r), media_type="application/pdf",
                             headers={"Content-Disposition": f"attachment; filename={name}.pdf"})


@router.get("/export/store/petty-cash/view", response_class=HTMLResponse)
def view_petty_cash(token: str, month: str = "", book: str = "site", db: Session = Depends(get_db)):
    user = auth.get_download_user_from_token(token, db)
    book = _may(user, book)
    r = register(db, month, book)
    t = auth.create_view_token(user.username)
    base = "/export/store/petty-cash?" + urlencode({"month": r["month"], "book": book, "token": t})
    return HTMLResponse(_html(r, base + "&format=pdf", base + "&format=excel"))

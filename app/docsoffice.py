"""Admin > Docs to office.

The store keeper sends delivery notes and other papers from site to the
office with a transmittal: numbered by itself (DOF:005 on, following the
paper forms), dated, one line per paper (supplier picked from the list, delivery note no.). In the office the assistant accountant ticks each paper as it
arrives and marks the transmittal received. It prints on the company's
form (Preview / PDF / Excel / Share).
"""
import io
import json
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

import main as M
import models
from database import get_db

router = APIRouter()
SEND, VERIFY = "docs_send", "docs_verify"
DG = Depends(M.require_any_screen(SEND, VERIFY))
FIRST_NO = 5                      # the paper forms reached DOF:004


def ref(no):
    return f"DOF:{no:03d}"


def _may(user, right):
    return (user.role or "") == "admin" or right in M.effective_permissions(user)


def _users(db):
    return {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}


def _dict(x, users):
    lines = [{"id": l.id, "sl": l.sl, "description": l.description or "", "dn_no": l.dn_no or "", "site": l.site or "",
              "date": l.on_date.isoformat() if l.on_date else "", "remarks": l.remarks or "", "movement_id": l.movement_id,
              "received": l.received} for l in x.lines]
    return {"id": x.id, "no": x.no, "ref": ref(x.no), "date": x.on_date.isoformat(), "from_site": x.from_site or "",
            "note": x.note or "", "status": x.status, "lines": lines,
            "sent_by": users.get(x.sent_by, ""), "sent_by_id": x.sent_by, "sent_at": x.sent_at.isoformat() if x.sent_at else "",
            "received_by": users.get(x.received_by, ""), "received_at": x.received_at.isoformat() if x.received_at else "",
            "received_note": x.received_note or "",
            "n_received": sum(1 for l in lines if l["received"]), "n_missing": sum(1 for l in lines if l["received"] is False)}


def _next_no(db):
    last = db.query(models.DocTransmittal).order_by(models.DocTransmittal.no.desc()).first()
    return max(FIRST_NO, (last.no + 1) if last else FIRST_NO)


def _supplier_names(db):
    """The supplier list for the Supplier box: the supplier register plus
    names used on transmittals before."""
    names = {}
    for (n,) in db.query(models.Supplier.name).all():
        n = " ".join((n or "").split())
        if n:
            names.setdefault(n.lower(), n)
    for (n,) in db.query(models.DocTransmittalLine.description).distinct().limit(2000):
        n = " ".join((n or "").split())
        if n:
            names.setdefault(n.lower(), n)
    return sorted(names.values(), key=str.lower)


@router.get("/store/docs")
def listing(db: Session = Depends(get_db), user: models.User = DG):
    users = _users(db)
    rows = [_dict(x, users) for x in db.query(models.DocTransmittal).order_by(models.DocTransmittal.no.desc()).limit(5000)]
    sites = [s.code for s in db.query(models.Site).order_by(models.Site.code).all()]
    return {"rows": rows, "next_ref": ref(_next_no(db)), "sites": sites,
            "may_send": _may(user, SEND), "may_verify": _may(user, VERIFY),
            "suppliers": _supplier_names(db) if _may(user, SEND) else [],
            "waiting": sum(1 for r in rows if r["status"] == "sent")}


def _clean(payload):
    d = M._as_date(payload.get("date"))
    if not d:
        raise HTTPException(status_code=400, detail="Pick the date.")
    if d > M._dubai_today():
        raise HTTPException(status_code=400, detail="That date is in the future.")
    lines = []
    for l in payload.get("lines") or []:
        desc = " ".join(str(l.get("description") or "").split())[:200]
        dn = " ".join(str(l.get("dn_no") or "").split())[:60]
        if not desc and not dn:
            continue                                   # an empty row is just left out
        ld = M._as_date(l.get("date")) if l.get("date") else None
        if ld and ld > M._dubai_today():
            raise HTTPException(status_code=400, detail=f"Line {len(lines) + 1}: that date is in the future.")
        mid = l.get("movement_id")
        if not desc:
            raise HTTPException(status_code=400, detail=f"Line {len(lines) + 1}: pick the supplier.")
        lines.append({"description": desc, "dn_no": dn, "site": " ".join(str(l.get("site") or "").split())[:40],
                      "on_date": ld, "remarks": " ".join(str(l.get("remarks") or "").split())[:200],
                      "movement_id": int(mid) if str(mid or "").isdigit() else None})
    if not lines:
        raise HTTPException(status_code=400, detail="Add at least one document.")
    return d, lines, " ".join(str(payload.get("from_site") or "").split())[:40], " ".join(str(payload.get("note") or "").split())[:300]


@router.post("/store/docs")
def create(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = DG):
    if not _may(user, SEND):
        raise HTTPException(status_code=403, detail="Only the store keeper sends documents to the office.")
    d, lines, site, note = _clean(payload)
    for _ in range(3):                                  # two people pressing at once: the next number
        no = _next_no(db)
        x = models.DocTransmittal(no=no, on_date=d, from_site=site, note=note, sent_by=user.id, status="sent")
        for i, l in enumerate(lines):
            x.lines.append(models.DocTransmittalLine(sl=i + 1, **l))
        db.add(x)
        try:
            db.commit()
            break
        except Exception:
            db.rollback()
    else:
        raise HTTPException(status_code=409, detail="Could not number it - press Send again.")
    M.log_action(db, user.id, "docs_sent", f"{ref(x.no)}: {len(lines)} document(s) sent to the office")
    return _dict(x, _users(db))


@router.put("/store/docs/{tid}")
def edit(tid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = DG):
    x = db.get(models.DocTransmittal, tid)
    if not x:
        raise HTTPException(status_code=404, detail="Not found.")
    if not _may(user, SEND):
        raise HTTPException(status_code=403, detail="Only the store keeper changes it.")
    if x.status != "sent" or any(l.received is not None for l in x.lines):
        raise HTTPException(status_code=400, detail="The office has started checking it - it cannot be changed now.")
    d, lines, site, note = _clean(payload)
    x.on_date, x.from_site, x.note = d, site, note
    x.lines.clear(); db.flush()
    for i, l in enumerate(lines):
        x.lines.append(models.DocTransmittalLine(sl=i + 1, **l))
    db.commit()
    M.log_action(db, user.id, "docs_changed", f"{ref(x.no)} changed: {len(lines)} document(s)")
    return _dict(x, _users(db))


@router.delete("/store/docs/{tid}")
def remove(tid: int, db: Session = Depends(get_db), user: models.User = DG):
    x = db.get(models.DocTransmittal, tid)
    if not x:
        raise HTTPException(status_code=404, detail="Not found.")
    if not _may(user, SEND) or x.status != "sent" or any(l.received is not None for l in x.lines):
        raise HTTPException(status_code=400, detail="Only a transmittal the office has not started checking can be deleted.")
    no = x.no
    db.delete(x); db.commit()
    M.log_action(db, user.id, "docs_deleted", f"{ref(no)} deleted before the office checked it")
    return {"ok": True}


@router.post("/store/docs/{tid}/receive")
def receive(tid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = DG):
    """The office ticks each paper: received, or not received."""
    if not _may(user, VERIFY):
        raise HTTPException(status_code=403, detail="Only the office (assistant accountant) checks documents in.")
    x = db.get(models.DocTransmittal, tid)
    if not x:
        raise HTTPException(status_code=404, detail="Not found.")
    marks = {int(m.get("id")): bool(m.get("received")) for m in payload.get("lines") or [] if str(m.get("id") or "").isdigit()}
    if any(l.id not in marks and l.received is None for l in x.lines):
        raise HTTPException(status_code=400, detail="Tick every document: received or not received.")
    for l in x.lines:
        if l.id in marks:
            l.received = marks[l.id]
    got = sum(1 for l in x.lines if l.received)
    x.status = "received" if got == len(x.lines) else "partial"
    x.received_by, x.received_at = user.id, datetime.now(timezone.utc)
    x.received_note = " ".join(str(payload.get("note") or "").split())[:300]
    db.commit()
    M.log_action(db, user.id, "docs_received",
                 f"{ref(x.no)}: {got} of {len(x.lines)} document(s) received" + (f" - {x.received_note}" if x.received_note else ""))
    return _dict(x, _users(db))


@router.post("/store/docs/{tid}/reopen")
def reopen(tid: int, db: Session = Depends(get_db), user: models.User = DG):
    if not _may(user, VERIFY):
        raise HTTPException(status_code=403, detail="Only the office reopens it.")
    x = db.get(models.DocTransmittal, tid)
    if not x:
        raise HTTPException(status_code=404, detail="Not found.")
    x.status, x.received_by, x.received_at = "sent", None, None
    for l in x.lines:
        l.received = None
    db.commit()
    M.log_action(db, user.id, "docs_reopened", f"{ref(x.no)} reopened for checking again")
    return _dict(x, _users(db))


# ---- the paper -----------------------------------------------------------------

def build_pdf(x, users, co=None):
    """The transmittal on the company's form: logo, title, the table of
    papers (more pages when needed, header repeated), the declaration and
    both signatures kept together at the end."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepTogether
    from reportlab.lib.utils import ImageReader
    import forms_pdf as F
    co = {**F.COMPANY, **(co or {})}
    buf = io.BytesIO()
    W, H = A4
    Mg = 16 * mm
    title = "DOCUMENT TRANSMITTAL"

    def page(c, doc):
        c.saveState()
        c.setFillColor(F.RED); c.rect(0, H - 1.0 * mm, W, 1.0 * mm, stroke=0, fill=1)
        top = H - 15 * mm
        lw = 62 * mm; lh = lw * 168 / 995
        try:
            c.drawImage(ImageReader(F.LOGO), Mg, top - lh, width=lw, height=lh, mask="auto")
        except Exception:
            pass
        c.setFont("Helvetica-Bold", 18); c.setFillColor(F.CHAR)
        c.drawRightString(W - Mg, top - 6.5 * mm, title)
        c.setFillColor(F.RED); c.rect(W - Mg - 26 * mm, top - 9.6 * mm, 26 * mm, 0.5 * mm, stroke=0, fill=1)
        c.setFont("Helvetica", 9.5); c.setFillColor(F.MUTED); c.drawRightString(W - Mg, top - 15 * mm, "Site to office")
        c.setFont("Helvetica", 7.6); c.drawString(Mg, top - lh - 5.5 * mm, f"Doc No. IC/AD/F06   |   {F.REV}   |   Page {doc.page}")
        c.setStrokeColor(F.RED); c.setLineWidth(0.4); c.line(Mg, 14 * mm, W - Mg, 14 * mm)
        c.setFont("Helvetica-Bold", 7.8); c.setFillColor(F.CHAR); c.drawString(Mg, 9.2 * mm, co["name"])
        c.setFont("Helvetica", 7.2); c.setFillColor(F.MUTED)
        c.drawString(Mg, 5.4 * mm, f"{co['address']}   |   TRN {co['trn']}   |   {co['web']}")
        c.drawRightString(W - Mg, 7.2 * mm, f"{ref(x.no)}")
        c.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=Mg, rightMargin=Mg, topMargin=46 * mm, bottomMargin=20 * mm,
                            title=f"Document Transmittal {ref(x.no)}", author=co["name"])
    lab = ParagraphStyle("lab", fontName="Helvetica-Bold", fontSize=6.6, textColor=F.MUTED, leading=8)
    val = ParagraphStyle("val", fontName="Helvetica-Bold", fontSize=11, textColor=F.INK, leading=13)
    cell = ParagraphStyle("cell", fontName="Helvetica", fontSize=8.6, textColor=F.INK, leading=10.4)
    hd = ParagraphStyle("hd", fontName="Helvetica-Bold", fontSize=6.8, textColor=colors.white, leading=8)
    say = ParagraphStyle("say", fontName="Helvetica", fontSize=9.2, textColor=F.INK, leading=12)
    tw = W - 2 * Mg
    dmy = lambda d: d.strftime("%d/%m/%Y") if d else ""
    head = Table([[Paragraph("TRANSMITTAL NO.", lab), Paragraph("DATE", lab), Paragraph("FROM SITE / PROJECT", lab), Paragraph("DOCUMENTS", lab)],
                  [Paragraph(ref(x.no), val), Paragraph(dmy(x.on_date), val), Paragraph(x.from_site or "-", val), Paragraph(str(len(x.lines)), val)]],
                 colWidths=[tw * 0.24, tw * 0.22, tw * 0.36, tw * 0.18])
    head.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, F.RULE), ("LINEAFTER", (0, 0), (-2, -1), 0.6, F.RULE),
                              ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 1), (-1, 1), 7), ("LEFTPADDING", (0, 0), (-1, -1), 7)]))
    cols = [("NO.", 0.06), ("SUPPLIER", 0.36), ("DELIVERY NOTE NO.", 0.16), ("SITE", 0.09), ("DATE", 0.12), ("REMARKS", 0.21)]
    show_rec = x.status in ("received", "partial")
    if show_rec:
        cols = [("NO.", 0.06), ("SUPPLIER", 0.32), ("DELIVERY NOTE NO.", 0.15), ("SITE", 0.08), ("DATE", 0.11), ("REMARKS", 0.17), ("RECEIVED", 0.11)]
    data = [[Paragraph(c, hd) for c, _ in cols]]
    for l in x.lines:
        r = [Paragraph(str(l.sl), cell), Paragraph(l.description or "", cell), Paragraph(l.dn_no or "", cell), Paragraph(l.site or "", cell),
             Paragraph(dmy(l.on_date), cell), Paragraph(l.remarks or "", cell)]
        if show_rec:
            r.append(Paragraph("<font color='#2E7D32'><b>Yes</b></font>" if l.received else "<font color='#B03A2E'><b>No</b></font>", cell))
        data.append(r)
    t = Table(data, colWidths=[tw * w for _, w in cols], repeatRows=1)
    st = [("BACKGROUND", (0, 0), (-1, 0), F.CHAR), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("TOPPADDING", (0, 0), (-1, -1), 4.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
          ("LINEBELOW", (0, 1), (-1, -1), 0.5, F.RULE), ("BOX", (0, 0), (-1, -1), 0.6, F.RULE),
          ("LINEAFTER", (0, 1), (-2, -1), 0.4, F.RULE)]
    for i in range(2, len(data), 2):
        st.append(("BACKGROUND", (0, i), (-1, i), F.TINT))
    t.setStyle(TableStyle(st))
    sent = users.get(x.sent_by, "")
    recv = users.get(x.received_by, "")
    rat = (x.received_at + timedelta(hours=4)).strftime("%d/%m/%Y") if x.received_at else "____ / ____ / ________"
    sat = dmy(x.on_date)
    sig_name = ParagraphStyle("sn", fontName="Helvetica-Bold", fontSize=8.8, textColor=F.CHAR, leading=11)
    sig_sub = ParagraphStyle("ss", fontName="Helvetica", fontSize=7.6, textColor=F.MUTED, leading=10)
    sigs = Table([[Paragraph("", cell), "", Paragraph("", cell)],
                  [Paragraph(f"Site Accountant / Store (sent){': ' + sent if sent else ''}", sig_name), "",
                   Paragraph(f"Office Admin (received){': ' + recv if recv else ''}", sig_name)],
                  [Paragraph(f"Date   {sat}", sig_sub), "", Paragraph(f"Date   {rat}", sig_sub)]],
                 colWidths=[tw * 0.42, tw * 0.16, tw * 0.42], rowHeights=[16 * mm, None, None])
    sigs.setStyle(TableStyle([("LINEBELOW", (0, 0), (0, 0), 0.7, F.CHAR), ("LINEBELOW", (2, 0), (2, 0), 0.7, F.CHAR),
                              ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    decl = "I confirm the documents listed above are handed over to the office for further action."
    tail = [Spacer(1, 6 * mm), Paragraph(decl, say)]
    if x.note:
        tail += [Spacer(1, 2 * mm), Paragraph(f"<b>Note:</b> {x.note}", say)]
    if x.status in ("received", "partial"):
        miss = [str(l.sl) for l in x.lines if not l.received]
        txt = (f"<b>Office check:</b> {len(x.lines) - len(miss)} of {len(x.lines)} received"
               + (f" - not received: line {', '.join(miss)}" if miss else " - all received") + (f". {x.received_note}" if x.received_note else ""))
        tail += [Spacer(1, 2 * mm), Paragraph(txt, say)]
    tail += [Spacer(1, 4 * mm), sigs]
    story = [head, Spacer(1, 6 * mm), t, KeepTogether(tail)]
    doc.build(story, onFirstPage=page, onLaterPages=page)
    buf.seek(0)
    return buf


@router.get("/export/store/docs")
def export_register(token: str, format: str = "excel", status: str = "", date_from: str = "", date_to: str = "", q: str = "",
                    db: Session = Depends(get_db)):
    """The history of transmittals, as filtered on screen."""
    from urllib.parse import quote, urlencode
    import auth, export_web
    u = auth.get_download_user_from_token(token, db)
    if not (_may(u, SEND) or _may(u, VERIFY)):
        raise HTTPException(status_code=403, detail="Docs to office is for the store keeper and the office.")
    users = _users(db)
    rows = [_dict(x, users) for x in db.query(models.DocTransmittal).order_by(models.DocTransmittal.no.desc()).all()]
    k = q.strip().lower()
    df, dt_ = (M._as_date(date_from) if date_from else None), (M._as_date(date_to) if date_to else None)
    rows = [r for r in rows if (not status or r["status"] == status) and (not df or r["date"] >= df.isoformat())
            and (not dt_ or r["date"] <= dt_.isoformat()) and
            (not k or k in " ".join([r["ref"], r["ref"].replace(":", ""), r["from_site"], r["sent_by"], r["received_by"], r["note"]]
                                     + [f"{l['description']} {l['dn_no']} {l['site']} {l['remarks']}" for l in r["lines"]]).lower())]
    st = {"sent": "Waiting", "received": "Received", "partial": "Something missing"}
    out = []
    for r in rows:
        for l in r["lines"]:
            out.append({"No.": r["ref"], "Date": M._as_date(r["date"]).strftime("%d/%m/%Y"), "Line": l["sl"], "Supplier": l["description"],
                        "Delivery note no.": l["dn_no"], "Site": l["site"] or r["from_site"], "Remarks": l["remarks"],
                        "Sent by": r["sent_by"], "Status": st.get(r["status"], r["status"]),
                        "Received": "" if l["received"] is None else ("Yes" if l["received"] else "No"),
                        "Checked by": r["received_by"]})
    title = "Docs to Office - History"
    span = (f"{df:%d/%m/%Y} to {dt_:%d/%m/%Y}" if df and dt_ else f"from {df:%d/%m/%Y}" if df else f"up to {dt_:%d/%m/%Y}" if dt_ else "all dates")
    sub = (f"{len(rows)} transmittal(s), {len(out)} document(s) | {span}" + (f" | {st.get(status)}" if status else "")
           + (f" | '{q.strip()}'" if k else "") + f" | As at {M._dubai_today():%d/%m/%Y}")
    if format == "view":
        vt = quote(auth.create_view_token(u.username), safe="")
        url = f"/export/store/docs?{urlencode({'status': status, 'date_from': date_from, 'date_to': date_to, 'q': q})}&token={vt}"
        return M._preview_page(title, sub, out, url, url, money_cols=[])
    name = f"Docs_to_Office_{(df or M._dubai_today()):%d.%m.%Y}" + (f"_to_{dt_:%d.%m.%Y}" if dt_ else "")
    if format == "pdf":
        return StreamingResponse(export_web.build_store_report_pdf(title, out, sub, money_cols=[], orientation="landscape"),
                                 media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})
    return StreamingResponse(export_web.build_store_report_excel(title, out, sub, money_cols=[]),
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename={name}.xlsx"})


@router.get("/export/store/docs/{tid}")
def export_one(tid: int, token: str, format: str = "pdf", dl: int = 0, db: Session = Depends(get_db)):
    from urllib.parse import quote
    from fastapi.responses import HTMLResponse
    from html import escape
    import auth, export_web
    u = auth.get_download_user_from_token(token, db)
    if not (_may(u, SEND) or _may(u, VERIFY)):
        raise HTTPException(status_code=403, detail="Docs to office is for the store keeper and the office.")
    x = db.get(models.DocTransmittal, tid)
    if not x:
        raise HTTPException(status_code=404, detail="Not found.")
    users = _users(db)
    name = f"Document_Transmittal_{ref(x.no).replace(':', '-')}"
    if format == "view":
        vt = quote(auth.create_view_token(u.username), safe="")
        pdf = f"/export/store/docs/{tid}?format=pdf&token={vt}"
        xl = f"/export/store/docs/{tid}?format=excel&token={vt}"
        title = f"Document Transmittal {ref(x.no)}"
        return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><style>{export_web.PREVIEW_BAR_CSS}
body{{margin:0;background:#E9E6E2;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif}} .pg{{max-width:900px;margin:18px auto 30px;padding:0 12px}}
.pg iframe{{width:100%;height:1180px;border:0;background:#fff;box-shadow:0 2px 14px rgba(0,0,0,.12);border-radius:3px}}</style></head><body>
<div class="pvbar"><h1>{escape(title)}</h1><span class="who">{len(x.lines)} document(s) &middot; {escape(x.on_date.strftime('%d/%m/%Y'))}</span><span class="sp"></span>
<a class="btn dark" href="{pdf}&dl=1">Download PDF</a><a class="btn" href="{xl}">Excel</a><a class="btn" href="{pdf}" target="_blank" rel="noopener">Print</a>{export_web.share_button(pdf, title)}</div>
<div class="pg pvwide"><iframe src="{pdf}#toolbar=0&view=FitH" title="{escape(title)}"></iframe></div>
{export_web.phone_pages(pdf)}
{export_web.SHARE_JS}</body></html>""")
    if format == "excel":
        d = _dict(x, users)
        rows = [{"No.": l["sl"], "Supplier": l["description"], "Delivery note no.": l["dn_no"], "Site": l["site"],
                 "Date": M._as_date(l["date"]).strftime("%d/%m/%Y") if l["date"] else "", "Remarks": l["remarks"],
                 **({"Received": "Yes" if l["received"] else "No"} if x.status != "sent" else {})} for l in d["lines"]]
        sub = f"{ref(x.no)} | {x.on_date:%d/%m/%Y} | from {x.from_site or '-'} | sent by {d['sent_by']}" + (
            f" | received by {d['received_by']}" if d["received_by"] else "")
        return StreamingResponse(export_web.build_store_report_excel("Document transmittal", rows, sub),
                                 media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 headers={"Content-Disposition": f"attachment; filename={name}.xlsx"})
    disp = "attachment" if dl else "inline"
    return StreamingResponse(build_pdf(x, users), media_type="application/pdf",
                             headers={"Content-Disposition": f'{disp}; filename="{name}.pdf"'})

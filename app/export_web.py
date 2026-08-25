"""
Export logic for the web app - generates Excel and PDF salary cards
directly from EmployeeSummary + DailyRow database records. Unlike the
desktop app's export_engine.py, this does NOT try to preserve an
originally-uploaded Excel template, since every record in the web app
is entered directly through the API - there is no "source file" to
borrow formatting from. Structure mirrors the desktop app's own
regenerated-card layout (Employee info fields, full 1-31 day grid,
Total Days block, Salary Summary block, Final Salary box) so a card
produced here reads the same way a desktop-generated one does.
"""
import io
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER

BRAND_RED = "C0392B"
BRAND_BLACK = "2E3238"
GREEN_FILL = "C6EFCE"
GREY_FILL = "D8D8D8"

DAILY_HEADERS = ["Date", "A.M", "P.M", "Site", "Engineer", "OT", "BH", "Comments"]

TOTAL_DAYS_FIELDS = [
    ("Present", "present_days"), ("Absent", "absent_days"), ("Sick", "sick_days"),
    ("Medical", "medical_days"), ("Friday", "friday_days"), ("Holiday", "holiday_days"),
    ("Leave", "leave_days"), ("OT", "ot_hours"), ("BH", "bh_hours"),
]

SUMMARY_FIELDS = [
    ("Basic Pay", "basic_pay_input", None),
    ("Total Salary", "total_salary_component", None),
    ("Absence or Leave", "deduction", "-"),
    ("OT Amount", "ot_amount", "+"),
    ("BH Amount", "bh_amount", "+"),
]


def _adjusted_final_salary(summary):
    total = summary.final_salary
    for adj in summary.adjustments:
        total += (-adj.amount if adj.is_deduction else adj.amount)
    return round(total, 2)


def _rows_by_day(daily_rows):
    return {r.day: r for r in daily_rows if r.day}


def _write_worker_sheet(ws, summary, rows, border):
    ws.column_dimensions["A"].width = 16
    for col in "BCDEFGH":
        ws.column_dimensions[col].width = 14
    ws.column_dimensions["H"].width = 30
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True

    # Employee info block
    info = [
        ("Employee Name:", summary.emp_name), ("Employee No:", summary.emp_no),
        ("Trade:", summary.trade), ("Month & Year:", summary.month_year),
        ("Salary:", summary.total_salary),
    ]
    r = 1
    for label, value in info:
        ws.cell(row=r, column=1, value=label).font = Font(bold=True)
        cell = ws.cell(row=r, column=2, value=value)
        cell.fill = PatternFill("solid", fgColor=GREY_FILL)
        r += 1
    r += 1

    # Daily grid header
    header_row = r
    for i, h in enumerate(DAILY_HEADERS, start=1):
        c = ws.cell(row=header_row, column=i, value=h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=BRAND_RED)
        c.alignment = Alignment(horizontal="center")
        c.border = border
    r += 1

    by_day = _rows_by_day(rows)
    for day in range(1, 32):
        row = by_day.get(day)
        vals = [day, row.am if row else "", row.pm if row else "", row.site if row else "",
                row.engineer if row else "", row.ot if row and row.ot else "",
                row.bh if row and row.bh else "", row.comments if row else ""]
        for i, v in enumerate(vals, start=1):
            c = ws.cell(row=r, column=i, value=v)
            c.alignment = Alignment(horizontal="center")
            c.border = border
        r += 1
    r += 1

    # OFFICE USE ONLY bar
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
    office_cell = ws.cell(row=r, column=1, value="OFFICE USE ONLY")
    office_cell.font = Font(bold=True)
    office_cell.fill = PatternFill("solid", fgColor="BFBFBF")
    office_cell.alignment = Alignment(horizontal="center")
    r += 2

    block_start = r
    # Total Days (columns A-B)
    for label, attr in TOTAL_DAYS_FIELDS:
        val = getattr(summary, attr, 0) or 0
        ws.cell(row=r, column=1, value=label).font = Font(bold=True)
        ws.cell(row=r, column=1).fill = PatternFill("solid", fgColor=GREY_FILL)
        vcell = ws.cell(row=r, column=2, value=round(val, 2) if val else 0)
        vcell.fill = PatternFill("solid", fgColor=GREY_FILL)
        vcell.alignment = Alignment(horizontal="center")
        r += 1

    # Salary Summary (columns D-E), same starting row
    r = block_start
    for label, attr, sign in SUMMARY_FIELDS:
        val = getattr(summary, attr, 0) or 0
        prefix = f"{sign} " if sign else ""
        ws.cell(row=r, column=4, value=label).font = Font(bold=True)
        ws.cell(row=r, column=4).fill = PatternFill("solid", fgColor=GREY_FILL)
        vcell = ws.cell(row=r, column=5, value=f"{prefix}AED {val:,.2f}")
        vcell.fill = PatternFill("solid", fgColor=GREY_FILL)
        vcell.alignment = Alignment(horizontal="center")
        r += 1
    for adj in summary.adjustments:
        sign = "-" if adj.is_deduction else "+"
        ws.cell(row=r, column=4, value=adj.description).font = Font(bold=True)
        ws.cell(row=r, column=4).fill = PatternFill("solid", fgColor=GREY_FILL)
        vcell = ws.cell(row=r, column=5, value=f"{sign} AED {adj.amount:,.2f}")
        vcell.fill = PatternFill("solid", fgColor=GREY_FILL)
        vcell.alignment = Alignment(horizontal="center")
        r += 1

    # Final Salary to Process - its own box (columns G-H)
    ws.cell(row=block_start, column=7, value="FINAL SALARY TO PROCESS").font = Font(bold=True, color="FFFFFF")
    ws.cell(row=block_start, column=7).fill = PatternFill("solid", fgColor=BRAND_BLACK)
    ws.merge_cells(start_row=block_start, start_column=7, end_row=block_start, end_column=8)
    ws.cell(row=block_start, column=7).alignment = Alignment(horizontal="center")

    final_cell = ws.cell(row=block_start + 1, column=7, value=f"AED {_adjusted_final_salary(summary):,.2f}")
    final_cell.fill = PatternFill("solid", fgColor=GREEN_FILL)
    final_cell.font = Font(bold=True)
    final_cell.alignment = Alignment(horizontal="center")
    ws.merge_cells(start_row=block_start + 1, start_column=7, end_row=block_start + 1, end_column=8)


def build_combined_excel(summaries_with_rows):
    """
    summaries_with_rows: list of (EmployeeSummary, [DailyRow]) tuples.
    One sheet per worker, same layout as the desktop app's regenerated
    cards.
    """
    wb = Workbook()
    wb.remove(wb.active)
    thin = Side(style="thin", color="DDDDDD")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    for summary, rows in summaries_with_rows:
        safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in str(summary.emp_no))[:28] or "card"
        ws = wb.create_sheet(title=safe_name)
        _write_worker_sheet(ws, summary, rows, border)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def build_separate_excel_files(summaries_with_rows):
    """
    One standalone .xlsx per worker instead of one workbook with many
    sheets - returns [(filename, BytesIO), ...] for the caller to zip.
    """
    thin = Side(style="thin", color="DDDDDD")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    files = []
    for summary, rows in summaries_with_rows:
        wb = Workbook()
        ws = wb.active
        ws.title = "Card"
        _write_worker_sheet(ws, summary, rows, border)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in str(summary.emp_no))
        files.append((f"{safe_name}.xlsx", buf))
    return files


def _build_pdf_card_elements(summary, rows, doc_width, styles):
    label_style = ParagraphStyle("InfoLabel", parent=styles["Normal"], fontSize=9, fontName="Helvetica-Bold")
    value_style = ParagraphStyle("InfoValue", parent=styles["Normal"], fontSize=9)
    grey = colors.HexColor(f"#{GREY_FILL}")
    elements = []

    info_rows = [
        [Paragraph("Employee Name:", label_style), Paragraph(summary.emp_name or "", value_style)],
        [Paragraph("Employee No:", label_style), Paragraph(summary.emp_no or "", value_style)],
        [Paragraph("Trade:", label_style), Paragraph(summary.trade or "", value_style)],
        [Paragraph("Month & Year:", label_style), Paragraph(summary.month_year or "", value_style)],
        [Paragraph("Salary:", label_style), Paragraph(f"{summary.total_salary:,.0f}", value_style)],
    ]
    info_tbl = Table(info_rows, colWidths=[doc_width * 0.22, doc_width * 0.40])
    info_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), grey),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    elements.append(info_tbl)
    elements.append(Spacer(1, 6))

    cell_style = ParagraphStyle("CardCell", parent=styles["Normal"], fontSize=6.5, leading=8)
    head_style = ParagraphStyle("CardHead", parent=styles["Normal"], fontSize=6.5, leading=8,
                                 textColor=colors.white, fontName="Helvetica-Bold")
    headers = ["Date", "A.M", "P.M", "OT", "BH", "Site", "Engineer", "Comments"]
    by_day = _rows_by_day(rows)
    data = [[Paragraph(h, head_style) for h in headers]]
    for day in range(1, 32):
        row = by_day.get(day)
        if row is not None:
            vals = [str(day), row.am, row.pm, str(row.ot or ""), str(row.bh or ""), row.site, row.engineer, row.comments]
        else:
            vals = [str(day), "", "", "", "", "", "", ""]
        data.append([Paragraph(v or "", cell_style) for v in vals])

    col_widths = [doc_width * w for w in (0.06, 0.10, 0.10, 0.06, 0.06, 0.10, 0.14, 0.38)]
    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(f"#{BRAND_RED}")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.5),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D0D0D0")),
        ("TOPPADDING", (0, 0), (-1, -1), 1.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2),
    ]))
    elements.append(tbl)
    elements.append(Spacer(1, 4))

    office_tbl = Table([[Paragraph("OFFICE USE ONLY", ParagraphStyle(
        "OfficeUse", parent=styles["Normal"], fontSize=9, fontName="Helvetica-Bold", alignment=TA_CENTER))]],
        colWidths=[doc_width])
    office_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#BFBFBF")),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(office_tbl)
    elements.append(Spacer(1, 6))

    days_data = [[Paragraph(label, label_style), Paragraph(f"{(getattr(summary, attr, 0) or 0):g}", value_style)]
                 for label, attr in TOTAL_DAYS_FIELDS]
    days_tbl = Table(days_data, colWidths=[doc_width * 0.16, doc_width * 0.09])
    days_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), grey),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    summary_rows = []
    for label, attr, sign in SUMMARY_FIELDS:
        val = getattr(summary, attr, 0) or 0
        prefix = f"{sign} " if sign else ""
        summary_rows.append([Paragraph(label, label_style), Paragraph(f"{prefix}AED {val:,.2f}", value_style)])
    for adj in summary.adjustments:
        sign = "-" if adj.is_deduction else "+"
        summary_rows.append([Paragraph(adj.description, label_style),
                              Paragraph(f"{sign} AED {adj.amount:,.2f}", value_style)])
    summary_tbl = Table(summary_rows, colWidths=[doc_width * 0.20, doc_width * 0.16])
    summary_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), grey),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    final_header = Paragraph("FINAL SALARY TO PROCESS", ParagraphStyle(
        "FinalHeader", parent=styles["Normal"], fontSize=8, fontName="Helvetica-Bold",
        textColor=colors.white, alignment=TA_CENTER))
    final_value = Paragraph(f"AED {_adjusted_final_salary(summary):,.2f}", ParagraphStyle(
        "FinalValue", parent=styles["Normal"], fontSize=10, fontName="Helvetica-Bold", alignment=TA_CENTER))
    final_tbl = Table([[final_header], [final_value]], colWidths=[doc_width * 0.20])
    final_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor(f"#{BRAND_BLACK}")),
        ("BACKGROUND", (0, 1), (0, 1), colors.HexColor(f"#{GREEN_FILL}")),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.white),
    ]))

    side_by_side = Table([[days_tbl, summary_tbl, final_tbl]],
                          colWidths=[doc_width * 0.27, doc_width * 0.38, doc_width * 0.22])
    side_by_side.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(side_by_side)
    return elements


def build_combined_pdf(summaries_with_rows):
    from reportlab.platypus import PageBreak
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=8 * mm, bottomMargin=8 * mm,
                             leftMargin=8 * mm, rightMargin=8 * mm)
    styles = getSampleStyleSheet()
    elements = []
    for idx, (summary, rows) in enumerate(summaries_with_rows):
        elements.extend(_build_pdf_card_elements(summary, rows, doc.width, styles))
        if idx < len(summaries_with_rows) - 1:
            elements.append(PageBreak())
    doc.build(elements)
    buf.seek(0)
    return buf


def build_separate_pdf_files(summaries_with_rows):
    """One standalone .pdf per worker instead of one combined document."""
    styles = getSampleStyleSheet()
    files = []
    for summary, rows in summaries_with_rows:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=8 * mm, bottomMargin=8 * mm,
                                 leftMargin=8 * mm, rightMargin=8 * mm)
        elements = _build_pdf_card_elements(summary, rows, doc.width, styles)
        doc.build(elements)
        buf.seek(0)
        safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in str(summary.emp_no))
        files.append((f"{safe_name}.pdf", buf))
    return files


def zip_files(files):
    """files: [(filename, BytesIO), ...] -> a single zip file as BytesIO."""
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, filebuf in files:
            zf.writestr(filename, filebuf.getvalue())
    buf.seek(0)
    return buf

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
import base64
import io
import os
import tempfile
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
import payroll_cycle as pcyc

BRAND_RED = "C0392B"
BRAND_BLACK = "2E3238"
GREEN_FILL = "C6EFCE"

# A colour per attendance status. Pale enough to print legibly and to
# read black text on: green means the day was worked, red means it cost
# the worker money, the rest are calm - sick and medical are not faults
# and a rest day is normal.
STATUS_FILLS = {
    "Present": "E3F4E4", "Absent": "FBE0DE", "Sick": "FFF2D6",
    "Medical": "FDE8D7", "Sunday": "E4EDFA", "Friday": "E4EDFA",
    "Holiday": "E9E4F7", "Leave": "EFEFEF",
}
GREY_FILL = "D8D8D8"

def _fit_box(path, max_w_mm, max_h_mm):
    """The largest width and height inside the box that keep the
    picture's own proportions."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            w, h = im.size
        if w and h:
            scale = min(max_w_mm / w, max_h_mm / h)
            return w * scale, h * scale
    except Exception:
        pass
    return max_w_mm, max_h_mm


# ---- The company logo, on every file that leaves the app --------------
# One PNG beside this module; the same image the app shows top-left.
LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
LOGO_W_MM, LOGO_H_MM = 42, 7.1          # 995x168 px, scaled to a neat header


def logo_data_uri():
    """The same logo, inline, for a preview drawn as a web page.

    A preview is meant to be the paper on screen, so it carries the
    letterhead too. Inlined rather than linked because the preview
    opens on its own tab with no session behind it."""
    try:
        with open(LOGO_PATH, "rb") as fh:
            return "data:image/png;base64," + base64.b64encode(fh.read()).decode()
    except Exception:
        return ""


def _logo_image(width_mm=None):
    """A ReportLab Image of the logo, or None if the file is missing - a
    missing logo must never stop a payroll file. The width can be asked
    for; the height follows the picture's own proportions."""
    try:
        from reportlab.platypus import Image as RLImage
        if not os.path.exists(LOGO_PATH):
            return None
        w = width_mm or LOGO_W_MM
        h = w * (LOGO_H_MM / LOGO_W_MM)
        return RLImage(LOGO_PATH, width=w * mm, height=h * mm)
    except Exception:
        return None


def _draw_logo_on_page(canvas, doc):
    """Page callback for SimpleDocTemplate: the logo top-left of every
    page, so a multi-page file carries it on each sheet, not only the
    first. Column width is unaffected because it sits in the margin."""
    try:
        if not os.path.exists(LOGO_PATH):
            return
        w, h = LOGO_W_MM * mm, LOGO_H_MM * mm
        x = doc.leftMargin
        y = doc.pagesize[1] - h - 4 * mm
        canvas.drawImage(LOGO_PATH, x, y, width=w, height=h, mask="auto")
    except Exception:
        pass


def _excel_logo_header(ws, rows_to_reserve=4):
    """Adds the logo above a sheet that has already been written.

    Called last, after the builder has laid out its rows, so none of
    the row arithmetic in a dozen builders has to change: the finished
    content is pushed down and the picture goes in the space made."""
    try:
        from openpyxl.drawing.image import Image as XLImage
        if not os.path.exists(LOGO_PATH):
            return
        # Merged ranges and frozen panes are anchored to row numbers;
        # move them by hand, since insert_rows leaves them behind.
        merges = [str(m) for m in list(ws.merged_cells.ranges)]
        for m in merges:
            ws.unmerge_cells(m)
        ws.insert_rows(1, amount=rows_to_reserve)
        from openpyxl.utils.cell import range_boundaries, get_column_letter
        for m in merges:
            c1, r1, c2, r2 = range_boundaries(m)
            ws.merge_cells(start_row=r1 + rows_to_reserve, start_column=c1,
                           end_row=r2 + rows_to_reserve, end_column=c2)
        if ws.freeze_panes:
            fp = ws.freeze_panes
            col = "".join(ch for ch in fp if ch.isalpha()); row = int("".join(ch for ch in fp if ch.isdigit()))
            ws.freeze_panes = f"{col}{row + rows_to_reserve}" if row > 1 else None
        # The print set-up is anchored to row numbers as well. Left
        # behind, the print area stopped four rows short - the totals
        # line never printed - and the "repeat these rows" pointed at
        # the logo instead of the heading.
        if ws.print_area:
            from openpyxl.utils.cell import range_boundaries as _rb
            c1, r1, c2, r2 = _rb(str(ws.print_area).split("!")[-1].replace("$", ""))
            ws.print_area = (f"{get_column_letter(c1)}{r1}:"
                             f"{get_column_letter(c2)}{r2 + rows_to_reserve}")
        if ws.print_title_rows:
            lo, hi = str(ws.print_title_rows).replace("$", "").split(":")
            ws.print_title_rows = f"{lo}:{int(hi) + rows_to_reserve}"
        # Row heights were set for the old numbering; shift them too.
        heights = {r: ws.row_dimensions[r].height for r in list(ws.row_dimensions.keys())
                   if ws.row_dimensions[r].height}
        for r in sorted(heights, reverse=True):
            ws.row_dimensions[r + rows_to_reserve].height = heights[r]
            ws.row_dimensions[r].height = None
        img = XLImage(LOGO_PATH)
        img.width, img.height = 200, 34
        ws.add_image(img, "A1")
        for r in range(1, rows_to_reserve + 1):
            ws.row_dimensions[r].height = 13
    except Exception:
        pass


def _excel_logo(ws, anchor="A1", rows_to_reserve=4):
    """Puts the logo at the top-left of a worksheet and returns the first
    free row beneath it. Rows are given a fixed height so the picture
    never overlaps the table, whatever the caller writes next."""
    try:
        from openpyxl.drawing.image import Image as XLImage
        if not os.path.exists(LOGO_PATH):
            return 1
        img = XLImage(LOGO_PATH)
        img.width, img.height = 200, 34           # px, same aspect as the file
        ws.add_image(img, anchor)
        for r in range(1, rows_to_reserve):
            ws.row_dimensions[r].height = 13
        return rows_to_reserve + 1
    except Exception:
        return 1


DAILY_HEADERS = ["Date", "A.M", "P.M", "Site", "Engineer", "OT", "BH", "Comments"]

TOTAL_DAYS_FIELDS = [
    ("Present", "present_days"), ("Absent", "absent_days"), ("Sick", "sick_days"),
    ("Medical", "medical_days"), ("Friday", "friday_days"), ("Sunday", "sunday_days"),
    ("Holiday", "holiday_days"),
    ("Leave", "leave_days"), ("OT", "ot_hours"), ("BH", "bh_hours"),
]


def _total_days_fields(summary):
    """The day rows worth printing for this worker.

    Friday was the paid rest day before Sunday replaced it. Cycles
    recorded back then still hold Friday days and must still print them,
    but a card for a recent cycle should not carry a Friday row that
    will always read zero."""
    return [(label, attr) for label, attr in TOTAL_DAYS_FIELDS
            if attr != "friday_days" or (getattr(summary, attr, 0) or 0)]

SUMMARY_FIELDS = [
    ("Basic Pay", "basic_pay_input", None),
    # The salary earned for the days paid this cycle. It was printed as
    # "Total Salary", the same words Master Data uses for the worker's
    # full monthly salary, and the two figures rarely agree - so the card
    # looked wrong to anyone who knew the man's pay.
    ("Payable Salary", "total_salary_component", None),
    ("Absence or Leave", "deduction", "-"),
    ("OT Amount", "ot_amount", "+"),
    ("BH Amount", "bh_amount", "+"),
]


def _adjusted_final_salary(summary):
    total = summary.final_salary
    for adj in summary.adjustments:
        total += (-adj.amount if adj.is_deduction else adj.amount)
    return round(total, 2)


def _rows_by_date(daily_rows):
    return {r.full_date: r for r in daily_rows if r.full_date}


def _num(v):
    """2.0 -> '2', 2.5 -> '2.5', whole numbers show clean with no trailing
    .0. Zero/blank/None all show as blank, matching the original 'row.ot
    or ""' convention - a day with attendance but no overtime shouldn't
    show a distracting '0' in every single row."""
    if not v:
        return ""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    return str(int(f)) if f == int(f) else str(f)


# The web app and the exports must speak the same language: the column is
# called "In central store" on screen, so the Excel and PDF say the same,
# not a machine-ish "In Store". One map, used by every store export.
STORE_LABELS = {
    "in_store": "In central store", "at_sites": "Out at sites", "total": "Total held",
    "by_site": "Where at sites", "item_type": "Type", "reorder_level": "Warn under",
    "hired_from": "Hired from", "on_hire": "On hire", "due_back": "Due back",
    "lost_damaged": "Lost / damaged", "written_off": "Written off",
    "qty": "Qty", "name": "Material", "code": "Code", "item": "Material",
    "ref": "Request", "requested_on": "Asked on", "needed_by": "Needed by",
    "days_late": "Days late", "outstanding": "Still to come",
    "total_salary": "Salary (AED)", "pay_type": "Paid", "company": "Company",
    "joined": "Joined",
    "material": "Material", "qty_requested": "Asked for",
    "qty_approved": "Approved", "qty_received": "Received",
    "purpose": "What for",
    "contact_person": "Contact person", "phone": "Mobile", "trn": "TRN",
    "payment_terms": "Payment terms", "email": "Email",
    "emp_no": "Worker No", "days_missing": "Days missing",
    "which_days": "Which days", "trade": "Trade",
    "given_to": "Given to", "date": "Date", "from": "From", "to": "To",
    "at_which_sites": "Where at sites", "reported_by": "Reported by",
    "where": "Where", "reason": "Reason", "type": "Type",
    "reference": "Ref", "notes": "Remarks", "incharge": "Given to",
    "last_arrived": "Last arrived", "since": "Out since",
}


def _store_label(k):
    """The heading for a column key.

    A key that is already a heading - "Basic Pay", "OT Hours" - is left
    exactly as it is. Title-casing it turned "Total (AED)" into
    "Total (Aed)" and "OT Hours" into "Ot Hours"."""
    if k in STORE_LABELS:
        return STORE_LABELS[k]
    if " " in k or (k != k.lower() and "_" not in k):
        return k
    return k.replace("_", " ").title()


def _clean_qty(v):
    """380.0 -> '380', 7.5 -> '7.5'. Counts of things never show a fake
    decimal - 400 bags, not 400.0 - and genuinely fractional values keep
    only the decimals they actually have."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return f"{int(f):,}" if f == int(f) else f"{f:,.2f}".rstrip("0").rstrip(".")


def _is_texty(k):
    """Columns that read as words, so they sit flush left like prose;
    numbers go flush right so digits line up down the column."""
    return any(w in k.lower() for w in
               ("name", "item", "category", "note", "description", "supplier",
                "purpose", "site", "status", "urgency", "hired", "person"))


def _is_money(k):
    return any(w in k.lower() for w in ("cost", "value", "amount", "rate", "price"))


def col_align(key, rows):
    """How a whole column sits - heading and every cell in it alike.

    The heading used to be centred on every column while the cells under
    it went left or right by type, so a report read as though it had
    been laid out twice by two different people. Centred now, heading
    and contents together, matching the tables on the screen the
    figures were checked on.

    Kept as one function so there is one place to change it, rather than
    the rule being spelled out again in the PDF, the spreadsheet and the
    preview and drifting apart between them.
    """
    return "C"


# ---- A4, the way round that fits ------------------------------------
# A report is printed and handed to somebody, so it has to come off the
# printer whole. Few columns stand up on a portrait page and waste less
# paper; many columns need the page on its side or the text is squeezed
# to nothing. Rather than every report having to declare which, the
# shape of the data decides.
# Characters of text a portrait A4 holds across at the size these
# reports print. Past this the page turns on its side.
PORTRAIT_MAX_WIDTH = 96


def choose_orientation(rows, cols=None):
    """"portrait" or "landscape", from the shape of the report."""
    cols = list(cols if cols is not None else (list(rows[0].keys()) if rows else []))
    if not cols:
        return "portrait"
    # How wide the table actually wants to be, not how many columns it
    # has. Eight short columns - a code, a unit, four counts - fit a
    # portrait page comfortably and waste far less paper than turning
    # the page sideways for them; four columns carrying material names
    # and remarks do not. Headings wrap, so they are measured by their
    # longest word, the same way the column widths are.
    width = 0
    for c in cols:
        seen = [str(r.get(c)) for r in rows if r.get(c) not in (None, "")]
        longest = max((len(x) for x in seen), default=0)
        head = max((len(w) for w in _store_label(c).split()), default=4)
        width += max(min(longest, 46), min(head, 12), 4) + 2   # +2 for the padding
    return "landscape" if width > PORTRAIT_MAX_WIDTH else "portrait"


def _page_size(orientation):
    return landscape(A4) if orientation == "landscape" else A4


def col_fractions(rows, cols, money_cols=None, total_cols=None):
    """What share of the page each column should take.

    Every column used to be given the same width - the page divided by
    the number of columns - so "Unit" holding the word "pcs" was handed
    as much paper as "Material", and a long material name wrapped onto
    three lines beside an inch of white space. On a ten-column report
    most of the sheet was margin.

    Each column is measured instead: the longer of its heading and its
    widest value, with a floor so a heading is never squeezed and a
    ceiling so one long remark cannot eat the page. Whatever is left
    over goes to the widest columns, which are the ones that wrap.

    Returns a list of fractions summing to 1.
    """
    if not cols:
        return []
    money_like = ((lambda k: k in set(money_cols)) if money_cols is not None else _is_money)
    # The totals line is part of the table and has to be measured with
    # it. A column of figures none of which reaches a thousand still
    # adds up to one that does, and the sum was the cell that broke: the
    # deductions came to 1,099.00 under a column sized for 400.00. The
    # word TOTAL in the first column is measured for the same reason -
    # it was appearing as "TOT" over "AL" above a two-character Sr.
    totals_row = {}
    if rows:
        adding = set(total_cols) if total_cols is not None else {c for c in cols if money_like(c)}
        for c in cols:
            if c not in adding:
                continue
            s = sum(r.get(c) or 0 for r in rows if isinstance(r.get(c), (int, float)))
            totals_row[c] = f"{s:,.2f}" if money_like(c) else _clean_qty(s)
        if totals_row and cols[0] not in totals_row:
            # Bold, and with padding either side, so it needs more room
            # than its five letters suggest - otherwise the first column
            # of a wide sheet shows "TOT" above "AL".
            totals_row[cols[0]] = "TOTAL  "
    want = []
    for c in cols:
        widest = len(totals_row.get(c, ""))
        for r in rows:
            v = r.get(c)
            if v in (None, ""):
                continue
            # Measured as it will be PRINTED, not as it is held. A net
            # pay of 14000.0 is six characters in the row and nine on
            # the page - "14,000.00" - and measuring the short one gave
            # the column too little room, so the figure broke across two
            # lines as "14,000.0" and a lonely "0". Any column whose
            # numbers are formatted has to be measured formatted.
            if isinstance(v, bool):
                text = "Yes" if v else ""
            elif isinstance(v, (int, float)):
                text = f"{v:,.2f}" if money_like(c) else _clean_qty(v)
            elif isinstance(v, dict):
                text = ", ".join(f"{a}: {_clean_qty(b)}" for a, b in v.items())
            else:
                text = str(v)
            if not text:
                continue
            # A cell of several lines is as wide as its longest line.
            widest = max(widest, max(len(x) for x in text.split("\n")))
        # A heading wraps over two or three lines happily enough, so the
        # column only has to be as wide as the heading's longest WORD.
        # Measuring the whole heading gave a column holding the number
        # 360 a sixteen-character width because it is called "In central
        # store" - most of the page went to headings, not to figures.
        head = max((len(w) for w in _store_label(c).split()), default=4)
        # Plus the cell padding, which is the same few points on every
        # column however narrow it is. Sharing the page out purely by
        # character count ignored that fixed cost, and on a wide sheet
        # it was the narrow columns that paid: a five-character staff
        # code came out as "IC00" over "1". Two characters' worth of
        # padding per column, then the rest shared by content.
        want.append(max(min(widest, 46), min(head, 12), 4) + 2)
    total = float(sum(want)) or 1.0
    return [w / total for w in want]


def print_ready(ws, orientation="landscape", header_row=None, last_col=None,
                last_row=None, title=None):
    """Set a sheet up so Ctrl-P gives the report, not a mess.

    A spreadsheet that prints across nine pages with the headings only
    on the first is not a report anybody can hand over. Every sheet the
    app produces is therefore set to A4, fitted to the width of one
    page, centred on it, with a margin to hold and the heading row
    repeated at the top of every page.
    """
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.orientation = ("landscape" if orientation == "landscape" else "portrait")
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    if ws.sheet_properties.pageSetUpPr is None:
        from openpyxl.worksheet.properties import PageSetupProperties
        ws.sheet_properties.pageSetUpPr = PageSetupProperties()
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_options.horizontalCentered = True
    ws.page_margins.left = ws.page_margins.right = 0.3
    ws.page_margins.top = 0.5
    ws.page_margins.bottom = 0.4
    ws.page_margins.header = ws.page_margins.footer = 0.2
    # The heading row again at the top of page two and page nine, or a
    # long report becomes columns of unlabelled numbers.
    if header_row:
        ws.print_title_rows = f"1:{header_row}"
    if last_col and last_row:
        ws.print_area = f"A1:{get_column_letter(last_col)}{last_row}"
    # Which report this is, and which page of it, on every sheet.
    ws.oddFooter.center.text = (title or ws.title) + "  -  Page &P of &N"
    ws.oddFooter.center.size = 8
    ws.oddFooter.center.color = "808080"
    return ws


def _cycle_dates(month_year):
    """
    Every actual calendar date in this cycle, in order - 26th of the
    prior month through the 25th of this one, matching how the cycle
    genuinely runs. Falls back to a plain 1-31 range only if month_year
    can't be parsed (shouldn't normally happen).
    """
    try:
        parsed = datetime.strptime(f"25 {month_year}", "%d %B %Y").date()
        start, end, _ = pcyc.cycle_bounds_for(parsed)
        dates = []
        cur = start
        while cur <= end:
            dates.append(cur)
            cur = cur.fromordinal(cur.toordinal() + 1)
        return dates
    except ValueError:
        return list(range(1, 32))


def _write_worker_card(ws, summary, rows, border, start_row):
    """
    Writes one worker's full card starting at start_row and returns the
    row number right after it (before the blank separator row) - lets
    the caller stack many cards in one worksheet, one blank row apart,
    instead of one sheet per worker.
    """
    thin_grey = Side(style="thin", color="BFBFBF")
    box_border = Border(left=thin_grey, right=thin_grey, top=thin_grey, bottom=thin_grey)
    r = start_row

    # Employee info block - a modest-width panel (columns C-G) centered
    # within the 8-column grid below it, with blank margin columns on
    # both sides - not stretched edge-to-edge, which just left a big
    # bare grey band with no content in most of it.
    info = [
        ("Employee Name:", summary.emp_name), ("Employee No:", summary.emp_no),
        ("Trade:", summary.trade), ("Month & Year:", summary.month_year),
        ("Salary (AED):", summary.total_salary),
    ]
    for label, value in info:
        ws.row_dimensions[r].height = 15
        lbl = ws.cell(row=r, column=3, value=label)
        lbl.font = Font(bold=True, size=10.5)
        lbl.border = box_border
        lbl.alignment = Alignment(horizontal="right", vertical="center")
        ws.merge_cells(start_row=r, start_column=4, end_row=r, end_column=7)
        val = ws.cell(row=r, column=4, value=value)
        val.fill = PatternFill("solid", fgColor=GREY_FILL)
        val.font = Font(size=10.5)
        val.alignment = Alignment(horizontal="center", vertical="center")
        val.border = box_border
        for col in (5, 6, 7):
            ws.cell(row=r, column=col).border = box_border
            ws.cell(row=r, column=col).fill = PatternFill("solid", fgColor=GREY_FILL)
        r += 1

    # Daily grid header
    header_row = r
    ws.row_dimensions[header_row].height = 13
    for i, h in enumerate(DAILY_HEADERS, start=1):
        c = ws.cell(row=header_row, column=i, value=h)
        c.font = Font(bold=True, color="FFFFFF", size=11)
        c.fill = PatternFill("solid", fgColor=BRAND_RED)
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = border
    r += 1

    by_date = _rows_by_date(rows)
    cycle_dates = _cycle_dates(summary.month_year)
    for idx, d in enumerate(cycle_dates):
        row = by_date.get(d)
        label = d.strftime("%d %b") if hasattr(d, "strftime") else d
        vals = [label, row.am if row else "", row.pm if row else "", row.site if row else "",
                row.engineer if row else "", (_num(row.ot) if row else ""),
                (_num(row.bh) if row else ""), (row.comments if row else "")]
        stripe = "F7F7F7" if idx % 2 == 0 else "FFFFFF"
        ws.row_dimensions[r].height = 15.5
        for i, v in enumerate(vals, start=1):
            c = ws.cell(row=r, column=i, value=v)
            c.alignment = Alignment(horizontal="center", vertical="center")
            c.border = border
            # A.M and P.M carry their status colour; the rest of the row
            # keeps the plain stripe so the colour draws the eye.
            fill = STATUS_FILLS.get(v) if i in (2, 3) else None
            c.fill = PatternFill("solid", fgColor=fill or stripe)
            c.font = Font(size=11.5)
            if i == 4:  # Site column - values like "704" look numeric but
                c.number_format = "@"  # aren't; "@" stops Excel's green
                # triangle "number stored as text" warning on them.
        r += 1

    # OFFICE USE ONLY bar
    ws.row_dimensions[r].height = 14
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
    office_cell = ws.cell(row=r, column=1, value="OFFICE USE ONLY")
    office_cell.font = Font(bold=True, size=9.5)
    office_cell.fill = PatternFill("solid", fgColor="BFBFBF")
    office_cell.alignment = Alignment(horizontal="center", vertical="center")
    office_cell.border = box_border
    r += 1

    block_start = r
    # Total Days (columns A-B), Salary Summary (columns D-E), Final
    # Salary box (columns G-H) - C and F are left as narrow, unbordered
    # spacer columns so the three blocks read as distinct panels rather
    # than one continuous, cluttered table.
    for label, attr in _total_days_fields(summary):
        ws.row_dimensions[r].height = 13
        status_fill = STATUS_FILLS.get(label)
        val = getattr(summary, attr, 0) or 0
        lbl = ws.cell(row=r, column=1, value=label)
        lbl.font = Font(bold=True, size=11)
        lbl.fill = PatternFill("solid", fgColor=status_fill or GREY_FILL)
        lbl.border = box_border
        lbl.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        vcell = ws.cell(row=r, column=2, value=round(val, 2) if val else 0)
        vcell.fill = PatternFill("solid", fgColor=status_fill or GREY_FILL)
        vcell.border = box_border
        vcell.alignment = Alignment(horizontal="center", vertical="center")
        vcell.font = Font(size=11)
        r += 1
    total_days_end = r

    r = block_start
    for label, attr, sign in SUMMARY_FIELDS:
        val = getattr(summary, attr, 0) or 0
        prefix = f"{sign} " if sign else ""
        lbl = ws.cell(row=r, column=4, value=label)
        lbl.font = Font(bold=True, size=11)
        lbl.fill = PatternFill("solid", fgColor=GREY_FILL)
        lbl.border = box_border
        lbl.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        vcell = ws.cell(row=r, column=5, value=f"{prefix}AED {val:,.2f}")
        vcell.fill = PatternFill("solid", fgColor=GREY_FILL)
        vcell.border = box_border
        vcell.alignment = Alignment(horizontal="right", vertical="center", indent=1)
        vcell.font = Font(size=11)
        r += 1
    for adj in summary.adjustments:
        sign = "-" if adj.is_deduction else "+"
        lbl = ws.cell(row=r, column=4, value=adj.description)
        lbl.font = Font(bold=True, size=11)
        lbl.fill = PatternFill("solid", fgColor=GREY_FILL)
        lbl.border = box_border
        lbl.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        vcell = ws.cell(row=r, column=5, value=f"{sign} AED {adj.amount:,.2f}")
        vcell.fill = PatternFill("solid", fgColor=GREY_FILL)
        vcell.border = box_border
        vcell.alignment = Alignment(horizontal="right", vertical="center", indent=1)
        vcell.font = Font(size=8.5, color="C0392B" if adj.is_deduction else "2E7D32")
        r += 1
    summary_end = r

    # Final Salary to Process - its own box (columns G-H)
    head = ws.cell(row=block_start, column=7, value="FINAL SALARY TO PROCESS")
    head.font = Font(bold=True, color="FFFFFF", size=8.5)
    head.fill = PatternFill("solid", fgColor=BRAND_BLACK)
    head.border = box_border
    head.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.merge_cells(start_row=block_start, start_column=7, end_row=block_start, end_column=8)
    ws.cell(row=block_start, column=8).border = box_border

    final_cell = ws.cell(row=block_start + 1, column=7, value=f"AED {_adjusted_final_salary(summary):,.2f}")
    # Green means money going out. When deductions exceed pay the
    # figure is negative, and that deserves the absent-red, not green.
    final_cell.fill = PatternFill("solid", fgColor=STATUS_FILLS["Absent"] if _adjusted_final_salary(summary) < 0 else GREEN_FILL)
    final_cell.font = Font(bold=True, size=13)
    final_cell.border = box_border
    final_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.merge_cells(start_row=block_start + 1, start_column=7, end_row=block_start + 1, end_column=8)
    ws.cell(row=block_start + 1, column=8).border = box_border

    card_end = max(total_days_end, summary_end, block_start + 2)

    # A card gets signed and handed over, so it needs somewhere to write
    # who checked it, the worker's signature, and anything said about it.
    # Printed boxes with room to write in, not data fields.
    sign_row = card_end + 1
    for col, label, width in ((1, "VERIFIED BY", 3), (4, "EMPLOYEE SIGNATURE", 2), (6, "REMARKS", 3)):
        head = ws.cell(row=sign_row, column=col, value=label)
        head.font = Font(bold=True, size=7.5, color="5B6167")
        head.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws.merge_cells(start_row=sign_row, start_column=col,
                       end_row=sign_row, end_column=col + width - 1)
        # A tall empty box underneath, ruled on all sides so it reads as
        # somewhere to sign rather than a gap in the sheet.
        for c in range(col, col + width):
            ws.cell(row=sign_row, column=c).border = box_border
            ws.cell(row=sign_row + 1, column=c).border = box_border
        ws.merge_cells(start_row=sign_row + 1, start_column=col,
                       end_row=sign_row + 1, end_column=col + width - 1)
    ws.row_dimensions[sign_row].height = 14
    ws.row_dimensions[sign_row + 1].height = 34

    return sign_row + 1


def build_combined_excel(summaries_with_rows):
    """
    summaries_with_rows: list of (EmployeeSummary, [DailyRow]) tuples.
    All workers stacked in ONE worksheet, one blank row between each
    card. Each card gets an explicit page break right after it so
    printing gives exactly one worker per physical page - the full
    31-day cycle (26th to 25th) is always shown, so every card is a
    consistent height that fits one page cleanly.
    """
    from openpyxl.worksheet.pagebreak import Break

    wb = Workbook()
    ws = wb.active
    ws.title = "Combined Cards"
    ws.column_dimensions["A"].width = 15
    ws.column_dimensions["B"].width = 10
    ws.column_dimensions["C"].width = 10
    ws.column_dimensions["D"].width = 17
    ws.column_dimensions["E"].width = 13
    ws.column_dimensions["F"].width = 7
    ws.column_dimensions["G"].width = 7
    ws.column_dimensions["H"].width = 26
    ws.page_setup.orientation = "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins.left = 0.25
    ws.page_margins.right = 0.25
    ws.page_margins.top = 0.3
    ws.page_margins.bottom = 0.3
    ws.print_options.horizontalCentered = True
    ws.print_options.verticalCentered = True
    ws.freeze_panes = "A1"

    thin = Side(style="thin", color="DDDDDD")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    row = 1
    last_row = 1
    for idx, (summary, rows) in enumerate(summaries_with_rows):
        next_row = _write_worker_card(ws, summary, rows, border, row)
        last_row = next_row
        if idx < len(summaries_with_rows) - 1:
            ws.row_breaks.append(Break(id=next_row))
        row = next_row + 1  # one blank row between cards

    ws.print_area = f"A1:H{last_row}"

    buf = io.BytesIO()
    for _ws in wb.worksheets:
        _excel_logo_header(_ws)
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
        ws.column_dimensions["A"].width = 17
        ws.column_dimensions["B"].width = 12
        ws.column_dimensions["C"].width = 12
        ws.column_dimensions["D"].width = 19
        ws.column_dimensions["E"].width = 15
        ws.column_dimensions["F"].width = 8
        ws.column_dimensions["G"].width = 8
        ws.column_dimensions["H"].width = 30
        ws.page_setup.orientation = "portrait"
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.print_options.horizontalCentered = True
        ws.print_options.verticalCentered = True
        _write_worker_card(ws, summary, rows, border, 1)
        buf = io.BytesIO()
        for _ws in wb.worksheets:
            _excel_logo_header(_ws)
        wb.save(buf)
        buf.seek(0)
        safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in str(summary.emp_no))
        files.append((f"{safe_name}.xlsx", buf))
    return files


def _build_pdf_card_elements(summary, rows, doc_width, styles):
    label_style = ParagraphStyle("InfoLabel", parent=styles["Normal"], fontSize=11.5, fontName="Helvetica-Bold", alignment=TA_LEFT)
    value_style = ParagraphStyle("InfoValue", parent=styles["Normal"], fontSize=11.5, alignment=TA_LEFT)
    grey = colors.HexColor(f"#{GREY_FILL}")
    grid_color = colors.HexColor("#B0B0B0")
    elements = []

    info_rows = [
        [Paragraph("Employee Name:", label_style), Paragraph(summary.emp_name or "", value_style)],
        [Paragraph("Employee No:", label_style), Paragraph(summary.emp_no or "", value_style)],
        [Paragraph("Trade:", label_style), Paragraph(summary.trade or "", value_style)],
        [Paragraph("Month & Year:", label_style), Paragraph(summary.month_year or "", value_style)],
        [Paragraph("Salary (AED):", label_style), Paragraph(f"{summary.total_salary:,.0f}", value_style)],
    ]
    info_tbl = Table(info_rows, colWidths=[doc_width * 0.24, doc_width * 0.40])
    info_tbl.hAlign = "CENTER"
    info_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), grey),
        ("GRID", (0, 0), (-1, -1), 0.5, grid_color),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.append(info_tbl)
    elements.append(Spacer(1, 6))

    cell_style = ParagraphStyle("CardCell", parent=styles["Normal"], fontSize=9, leading=10.3, alignment=TA_CENTER)
    head_style = ParagraphStyle("CardHead", parent=styles["Normal"], fontSize=9, leading=10.3,
                                 textColor=colors.white, fontName="Helvetica-Bold", alignment=TA_CENTER)
    headers = ["Date", "A.M", "P.M", "OT", "BH", "Site", "Engineer", "Comments"]
    by_date = _rows_by_date(rows)
    cycle_dates = _cycle_dates(summary.month_year)
    data = [[Paragraph(h, head_style) for h in headers]]
    status_cells = []
    for d in cycle_dates:
        row = by_date.get(d)
        label = d.strftime("%d %b") if hasattr(d, "strftime") else str(d)
        if row is not None:
            vals = [label, row.am, row.pm, _num(row.ot), _num(row.bh), row.site, row.engineer, row.comments]
        else:
            vals = [label, "", "", "", "", "", "", ""]
        data.append([Paragraph(v or "", cell_style) for v in vals])
        # Remember which status each half-day carried, so the A.M and
        # P.M cells can be tinted once the table is built.
        status_cells.append((len(data) - 1, vals[1], vals[2]))

    col_widths = [doc_width * w for w in (0.10, 0.10, 0.10, 0.06, 0.06, 0.10, 0.14, 0.34)]
    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    row_bg_cmds = [("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F7F7F7")) for i in range(2, len(data), 2)]
    # Status colours go on after the stripes so they win.
    for ri, am, pm in status_cells:
        if STATUS_FILLS.get(am):
            row_bg_cmds.append(("BACKGROUND", (1, ri), (1, ri), colors.HexColor("#" + STATUS_FILLS[am])))
        if STATUS_FILLS.get(pm):
            row_bg_cmds.append(("BACKGROUND", (2, ri), (2, ri), colors.HexColor("#" + STATUS_FILLS[pm])))
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(f"#{BRAND_RED}")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.4, grid_color),
        ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ] + row_bg_cmds))
    elements.append(tbl)
    elements.append(Spacer(1, 4))

    office_tbl = Table([[Paragraph("OFFICE USE ONLY", ParagraphStyle(
        "OfficeUse", parent=styles["Normal"], fontSize=10.5, fontName="Helvetica-Bold", alignment=TA_CENTER))]],
        colWidths=[doc_width])
    office_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#BFBFBF")),
        ("GRID", (0, 0), (-1, -1), 0.5, grid_color),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(office_tbl)
    elements.append(Spacer(1, 6))

    value_right_style = ParagraphStyle("ValueRight", parent=styles["Normal"], fontSize=10.5, alignment=TA_RIGHT)
    day_fields = _total_days_fields(summary)
    days_data = [[Paragraph(label, label_style), Paragraph(f"{(getattr(summary, attr, 0) or 0):g}", value_right_style)]
                 for label, attr in day_fields]
    days_tbl = Table(days_data, colWidths=[doc_width * 0.16, doc_width * 0.09])
    days_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), grey),
        # Each day-status row takes its own colour, matching the grid
        # above and the app on screen.
        *[("BACKGROUND", (0, i), (-1, i), colors.HexColor("#" + STATUS_FILLS[label]))
          for i, (label, _) in enumerate(day_fields) if label in STATUS_FILLS],
        ("GRID", (0, 0), (-1, -1), 0.5, grid_color),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    summary_rows = []
    summary_row_colors = []
    for label, attr, sign in SUMMARY_FIELDS:
        val = getattr(summary, attr, 0) or 0
        prefix = f"{sign} " if sign else ""
        summary_rows.append([Paragraph(label, label_style), Paragraph(f"{prefix}AED {val:,.2f}", value_right_style)])
        summary_row_colors.append(None)
    for adj in summary.adjustments:
        sign = "-" if adj.is_deduction else "+"
        adj_value_style = ParagraphStyle("AdjValue", parent=value_right_style,
                                          textColor=colors.HexColor("#C0392B") if adj.is_deduction else colors.HexColor("#2E7D32"))
        summary_rows.append([Paragraph(adj.description, label_style),
                              Paragraph(f"{sign} AED {adj.amount:,.2f}", adj_value_style)])
    summary_tbl = Table(summary_rows, colWidths=[doc_width * 0.20, doc_width * 0.16])
    summary_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), grey),
        ("GRID", (0, 0), (-1, -1), 0.5, grid_color),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    final_header = Paragraph("FINAL SALARY TO PROCESS", ParagraphStyle(
        "FinalHeader", parent=styles["Normal"], fontSize=8, fontName="Helvetica-Bold",
        textColor=colors.white, alignment=TA_CENTER))
    final_value = Paragraph(f"AED {_adjusted_final_salary(summary):,.2f}", ParagraphStyle(
        "FinalValue", parent=styles["Normal"], fontSize=13.5, fontName="Helvetica-Bold", alignment=TA_CENTER))
    final_tbl = Table([[final_header], [final_value]], colWidths=[doc_width * 0.20])
    final_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor(f"#{BRAND_BLACK}")),
        ("BACKGROUND", (0, 1), (0, 1), colors.HexColor("#" + (STATUS_FILLS["Absent"] if _adjusted_final_salary(summary) < 0 else GREEN_FILL))),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("BOX", (0, 0), (-1, -1), 0.5, grid_color),
        ("LINEBELOW", (0, 0), (0, 0), 0.5, grid_color),
    ]))

    side_by_side = Table([[days_tbl, summary_tbl, final_tbl]],
                          colWidths=[doc_width * 0.27, doc_width * 0.38, doc_width * 0.22])
    side_by_side.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(side_by_side)

    # Somewhere to sign. A printed card is checked by someone, signed by
    # the worker, and often carries a note - without ruled boxes those
    # end up scrawled across the figures.
    label = ParagraphStyle("signlabel", parent=styles["Normal"], fontSize=6.5,
                            textColor=colors.HexColor("#5B6167"), spaceAfter=0, leading=8)
    sign_tbl = Table(
        [[Paragraph("VERIFIED BY", label), Paragraph("EMPLOYEE SIGNATURE", label),
          Paragraph("REMARKS", label)],
         ["", "", ""]],
        colWidths=[doc_width * 0.28, doc_width * 0.28, doc_width * 0.44],
        rowHeights=[10, 34])
    sign_tbl.setStyle(TableStyle([
        ("BOX", (0, 0), (0, 1), 0.5, grid_color),
        ("BOX", (1, 0), (1, 1), 0.5, grid_color),
        ("BOX", (2, 0), (2, 1), 0.5, grid_color),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, 0), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    elements.append(Spacer(1, 8))
    elements.append(sign_tbl)
    return elements


def salary_card_html(summary, rows):
    """One worker's card as HTML - the same document the PDF prints.

    Written out rather than showing the PDF in a frame: a phone and a
    browser with no PDF plugin both show a blank box, and a preview that
    shows nothing is worse than none. Kept beside the PDF builder so the
    two are changed together.
    """
    from html import escape as esc

    def cell(v):
        return esc("" if v in (None, "") else str(v))

    by_date = _rows_by_date(rows)
    info = [("Employee Name", summary.emp_name or ""), ("Employee No", summary.emp_no or ""),
            ("Trade", summary.trade or ""), ("Month & Year", summary.month_year or ""),
            ("Salary (AED)", f"{summary.total_salary:,.0f}")]
    info_html = "".join(f"<tr><th>{esc(k)}:</th><td>{cell(v)}</td></tr>" for k, v in info)

    body = []
    for d in _cycle_dates(summary.month_year):
        r = by_date.get(d)
        label = d.strftime("%d %b") if hasattr(d, "strftime") else str(d)
        vals = ([label, r.am, r.pm, _num(r.ot), _num(r.bh), r.site, r.engineer, r.comments]
                if r is not None else [label, "", "", "", "", "", "", ""])
        def tint(status):
            fill = STATUS_FILLS.get(status)
            return ' style="background:#' + fill + '"' if fill else ""
        body.append(
            "<tr>" + f"<td>{cell(vals[0])}</td>"
            + "<td" + tint(vals[1]) + ">" + cell(vals[1]) + "</td>"
            + "<td" + tint(vals[2]) + ">" + cell(vals[2]) + "</td>"
            + "".join(f"<td>{cell(v)}</td>" for v in vals[3:]) + "</tr>")

    def day_row(label, attr):
        fill = STATUS_FILLS.get(label)
        style = ' style="background:#' + fill + '"' if fill else ""
        val = getattr(summary, attr, 0) or 0
        return f"<tr{style}><th>{esc(label)}</th><td>{val:g}</td></tr>"
    days = "".join(day_row(label, attr) for label, attr in _total_days_fields(summary))

    money = "".join(
        f"<tr><th>{esc(label)}</th><td>{(f'{sign} ' if sign else '')}"
        f"AED {(getattr(summary, attr, 0) or 0):,.2f}</td></tr>"
        for label, attr, sign in SUMMARY_FIELDS)
    for adj in summary.adjustments:
        colour = "#C0392B" if adj.is_deduction else "#2E7D32"
        money += (f"<tr><th>{esc(adj.description)}</th>"
                  f'<td style="color:{colour}">{"-" if adj.is_deduction else "+"} '
                  f"AED {adj.amount:,.2f}</td></tr>")

    final = _adjusted_final_salary(summary)
    final_bg = STATUS_FILLS["Absent"] if final < 0 else GREEN_FILL
    return f"""
  <div class="card">
    <table class="info">{info_html}</table>
    <table class="grid">
      <thead><tr><th>Date</th><th>A.M</th><th>P.M</th><th>OT</th><th>BH</th>
        <th>Site</th><th>Engineer</th><th>Comments</th></tr></thead>
      <tbody>{''.join(body)}</tbody>
    </table>
    <div class="office">OFFICE USE ONLY</div>
    <div class="foot">
      <table class="days">{days}</table>
      <table class="money">{money}</table>
      <table class="final">
        <tr><th>FINAL SALARY TO PROCESS</th></tr>
        <tr><td style="background:#{final_bg}">AED {final:,.2f}</td></tr>
      </table>
    </div>
    <table class="sign"><tr><th style="width:38%">VERIFIED BY</th><th style="width:27%">EMPLOYEE SIGNATURE</th><th>REMARKS</th></tr>
      <tr><td></td><td></td><td></td></tr></table>
  </div>"""


def build_combined_pdf(summaries_with_rows):
    """
    Each worker's full 31-day cycle card gets its own page - one card
    per page keeps a consistent, predictable layout for a card sized
    to always show the full 26th-25th cycle.
    """
    from reportlab.platypus import PageBreak
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20 * mm, bottomMargin=8 * mm,
                             leftMargin=8 * mm, rightMargin=8 * mm)
    styles = getSampleStyleSheet()
    elements = []
    for idx, (summary, rows) in enumerate(summaries_with_rows):
        elements.extend(_build_pdf_card_elements(summary, rows, doc.width, styles))
        if idx < len(summaries_with_rows) - 1:
            elements.append(PageBreak())
    doc.build(elements, onFirstPage=_draw_logo_on_page, onLaterPages=_draw_logo_on_page)
    buf.seek(0)
    return buf


def build_separate_pdf_files(summaries_with_rows):
    """One standalone .pdf per worker instead of one combined document."""
    styles = getSampleStyleSheet()
    files = []
    for summary, rows in summaries_with_rows:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20 * mm, bottomMargin=8 * mm,
                                 leftMargin=8 * mm, rightMargin=8 * mm)
        elements = _build_pdf_card_elements(summary, rows, doc.width, styles)
        doc.build(elements, onFirstPage=_draw_logo_on_page, onLaterPages=_draw_logo_on_page)
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


REPORT_COLUMNS_META = {
    "emp_no": ("Emp No", "text"), "emp_name": ("Name", "text"), "trade": ("Trade", "text"),
    "sites": ("Site", "text"), "total_salary": ("Total Salary", "money"),
    "present_days": ("Present", "num"), "absent_days": ("Absent", "num"), "sick_days": ("Sick", "num"),
    "medical_days": ("Medical", "num"), "friday_days": ("Friday", "num"),
    "sunday_days": ("Sunday", "num"), "holiday_days": ("Holiday", "num"),
    "leave_days": ("Leave", "num"), "ot_hours": ("OT Hours", "num"), "bh_hours": ("BH Hours", "num"),
    "basic_pay_input": ("Basic Pay", "money"), "deduction": ("Absence/Leave Deduction", "money"),
    "ot_amount": ("OT Amount", "money"), "bh_amount": ("BH Amount", "money"),
    "final_salary": ("Final Salary", "money"), "adjustments": ("Adjustments", "text"),
    "adjusted_final_salary": ("Adjusted Final Salary", "money"),
}


def _report_row_value(item, key):
    if key == "adjusted_final_salary":
        return item.final_salary + sum(-a.amount if a.is_deduction else a.amount for a in item.adjustments)
    if key == "adjustments":
        return "; ".join(f"{a.description}: {'-' if a.is_deduction else '+'}{a.amount}" for a in item.adjustments) or "-"
    return getattr(item, key, "")


def report_table_rows(items, column_keys):
    """The Report Builder's picked columns as plain rows.

    Turned into ordinary rows so the builder's report goes through the
    same PDF, spreadsheet and preview as every other report in the app,
    rather than through a layout of its own that drifts away from them.

    Returns the rows and the names of the money columns, which are the
    ones worth a total at the foot.
    """
    cols = [(k, *REPORT_COLUMNS_META.get(k, (k, "text")))
            for k in column_keys if k in REPORT_COLUMNS_META]
    rows = []
    for item in items:
        row = {}
        for key, label, kind in cols:
            v = _report_row_value(item, key)
            if kind in ("money", "num"):
                row[label] = float(v or 0)
            else:
                row[label] = str(v) if v not in (None, "") else "-"
        rows.append(row)
    return rows, [label for _, label, kind in cols if kind == "money"]


def build_report_table_excel(items, column_keys, cycle_label):
    wb = Workbook()
    ws = wb.active
    ws.title = "Report"
    cols = [(k, *REPORT_COLUMNS_META.get(k, (k, "text"))) for k in column_keys if k in REPORT_COLUMNS_META]
    thin = Side(style="thin", color="DDDDDD")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    for i, (key, label, kind) in enumerate(cols, start=1):
        c = ws.cell(row=1, column=i, value=label)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=BRAND_RED)
        c.alignment = Alignment(horizontal="center")
        c.border = border
        ws.column_dimensions[get_column_letter(i)].width = 22 if kind == "text" else 16

    r = 2
    totals = {key: 0.0 for key, _, kind in cols if kind in ("money", "num")}
    for item in items:
        for i, (key, label, kind) in enumerate(cols, start=1):
            val = _report_row_value(item, key)
            if kind == "money":
                val_num = val or 0
                totals[key] += val_num
                display = f"AED {val_num:,.2f}"
            elif kind == "num":
                val_num = val or 0
                totals[key] += val_num
                display = val_num
            else:
                display = val
            c = ws.cell(row=r, column=i, value=display)
            c.alignment = Alignment(horizontal="center")
            c.border = border
        r += 1

    # Totals row
    for i, (key, label, kind) in enumerate(cols, start=1):
        if i == 1:
            c = ws.cell(row=r, column=i, value="TOTAL")
            c.font = Font(bold=True)
        elif kind == "money":
            c = ws.cell(row=r, column=i, value=f"AED {totals[key]:,.2f}")
            c.font = Font(bold=True)
        elif kind == "num":
            c = ws.cell(row=r, column=i, value=round(totals[key], 2))
            c.font = Font(bold=True)
        else:
            c = ws.cell(row=r, column=i, value="")
        c.fill = PatternFill("solid", fgColor=GREEN_FILL)
        c.alignment = Alignment(horizontal="center")
        c.border = border

    buf = io.BytesIO()
    for _ws in wb.worksheets:
        _excel_logo_header(_ws)
    wb.save(buf)
    buf.seek(0)
    return buf


def build_report_table_pdf(items, column_keys, cycle_label):
    cols = [(k, *REPORT_COLUMNS_META.get(k, (k, "text"))) for k in column_keys if k in REPORT_COLUMNS_META]
    styles = getSampleStyleSheet()
    cell_style = ParagraphStyle("TblCell", parent=styles["Normal"], fontSize=7, leading=9)
    head_style = ParagraphStyle("TblHead", parent=styles["Normal"], fontSize=7.5, leading=9,
                                 textColor=colors.white, fontName="Helvetica-Bold")
    bold_style = ParagraphStyle("TblBold", parent=styles["Normal"], fontSize=7.5, leading=9, fontName="Helvetica-Bold")

    data = [[Paragraph(label, head_style) for _, label, _ in cols]]
    totals = {key: 0.0 for key, _, kind in cols if kind in ("money", "num")}
    for item in items:
        row = []
        for key, label, kind in cols:
            val = _report_row_value(item, key)
            if kind == "money":
                val_num = val or 0
                totals[key] += val_num
                row.append(Paragraph(f"AED {val_num:,.2f}", cell_style))
            elif kind == "num":
                val_num = val or 0
                totals[key] += val_num
                row.append(Paragraph(str(val_num), cell_style))
            else:
                row.append(Paragraph(str(val) if val else "-", cell_style))
        data.append(row)

    total_row = []
    for i, (key, label, kind) in enumerate(cols):
        if i == 0:
            total_row.append(Paragraph("TOTAL", bold_style))
        elif kind == "money":
            total_row.append(Paragraph(f"AED {totals[key]:,.2f}", bold_style))
        elif kind == "num":
            total_row.append(Paragraph(str(round(totals[key], 2)), bold_style))
        else:
            total_row.append(Paragraph("", bold_style))
    data.append(total_row)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=22 * mm, bottomMargin=10 * mm,
                             leftMargin=8 * mm, rightMargin=8 * mm)
    col_width = doc.width / max(len(cols), 1)
    tbl = Table(data, colWidths=[col_width] * len(cols), repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(f"#{BRAND_RED}")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D0D0D0")),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor(f"#{GREEN_FILL}")),
    ]
    tbl.setStyle(TableStyle(style_cmds))

    title = Paragraph(f"Report - {cycle_label}", ParagraphStyle(
        "Title", parent=styles["Normal"], fontSize=13, fontName="Helvetica-Bold", spaceAfter=8))
    doc.build([title, tbl], onFirstPage=_draw_logo_on_page, onLaterPages=_draw_logo_on_page)
    buf.seek(0)
    return buf


def build_generic_result_excel(result_dict, cycle_label):
    """
    Exports an already-computed report result (columns/rows/totals, the
    shape build_custom_report or site_cost_center return) directly - no
    re-aggregation needed, just formatting what's already there.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Report"
    cols = result_dict["columns"]
    thin = Side(style="thin", color="DDDDDD")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    for i, c in enumerate(cols, start=1):
        cell = ws.cell(row=1, column=i, value=c["label"])
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=BRAND_RED)
        cell.alignment = Alignment(horizontal="center")
        cell.border = border
        ws.column_dimensions[get_column_letter(i)].width = 22

    # Money columns get Excel's thousands-separator format so a figure
    # like 21344.92 reads as 21,344.92 rather than a wall of digits.
    # Applied as a cell number_format (not a pre-formatted string) so the
    # value stays a real number Excel can still sum and chart.
    MONEY_FMT = '#,##0.00'
    COUNT_FMT = '#,##0.##'   # separators, but no forced decimals
    def is_money(key):
        k = key.lower()
        return "cost" in k or "amount" in k or "salary" in k or "pay" in k

    r = 2
    for row in result_dict["rows"]:
        for i, c in enumerate(cols, start=1):
            v = row.get(c["key"], "")
            cell = ws.cell(row=r, column=i, value=v)
            cell.alignment = Alignment(horizontal="center")
            cell.border = border
            if isinstance(v, (int, float)):
                cell.number_format = MONEY_FMT if is_money(c["key"]) else COUNT_FMT
            elif isinstance(v, str) and "\n" in v:
                # Lines stay lines - an adjustment and the note under it.
                cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
                ws.column_dimensions[get_column_letter(i)].width = 46
        r += 1

    totals = result_dict.get("totals") or {}
    if totals:
        for i, c in enumerate(cols, start=1):
            v = totals.get(c["key"])
            cell = ws.cell(row=r, column=i, value="TOTAL" if i == 1 else (v if v is not None else ""))
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", fgColor=GREEN_FILL)
            cell.alignment = Alignment(horizontal="center")
            cell.border = border
            if i > 1 and isinstance(v, (int, float)):
                cell.number_format = MONEY_FMT if is_money(c["key"]) else COUNT_FMT

    buf = io.BytesIO()
    for _ws in wb.worksheets:
        _excel_logo_header(_ws)
    wb.save(buf)
    buf.seek(0)
    return buf


def _column_widths(cols, avail):
    """Column widths in points, for a table that has to read on A4.

    Every column used to get an equal share, so "OT Hours" was as wide
    as "Adjustments" - the numbers swam in space while "-170 Parking
    fine for D38023, +50 Extra Allowance" broke into five lines. Then,
    with a Notes column beside it, sharing by weight squeezed "Employee
    No" into "Employ / ee No".

    So the columns that hold a number or a code get a fixed width they
    can always print in, and whatever is left is split between the
    columns that hold sentences - those are the ones meant to wrap.
    """
    def kind(c):
        k, l = c["key"].lower(), c["label"].lower()
        if k in ("adjustments", "notes", "adjustments_notes") or "reason" in k or "note" in k:
            return "text"
        if k == "dim_1" or "name" in l:
            return "name"
        if k == "dim_0" or "employee no" in l or "emp" in l:
            return "id"
        if k.startswith("dim_"):
            return "label"
        if "hours" in l or "days" in l or "headcount" in l or "man-days" in l:
            return "count"
        return "money"
    fixed = {"id": 48, "name": 96, "label": 70, "count": 38, "money": 64}
    kinds = [kind(c) for c in cols]
    widths = [fixed.get(k, 0) for k in kinds]
    n_text = kinds.count("text")
    if n_text:
        left = max(avail - sum(widths), 90 * n_text)
        share = left / n_text
        widths = [share if k == "text" else w for k, w in zip(kinds, widths)]
    else:
        # No sentence columns: let the fixed ones grow to fill the page.
        scale = avail / max(sum(widths), 1)
        widths = [w * scale for w in widths]
    return widths


def generic_result_rows(result_dict):
    """A built report's columns and rows as plain rows keyed by heading.

    So the Report Builder's output goes through the same PDF,
    spreadsheet and preview as everything else, instead of a third
    layout that drifts away from the other two.

    Returns the rows and the names of the money columns.
    """
    cols = result_dict.get("columns") or []
    def money(key, label=""):
        # A column the app labels in dirhams is money whatever its key
        # is called: "Absence Deduction (AED)" was being totalled as a
        # count because its key is "deduction".
        k = key.lower()
        return ("(aed)" in label.lower() or "cost" in k or "amount" in k
                or "salary" in k or "pay" in k or "deduction" in k)
    def numeric(key):
        k = key.lower()
        return not (k.startswith("dim_")
                    or k in ("adjustments", "notes", "adjustments_notes")
                    or "reason" in k)
    rows = []
    for r in result_dict.get("rows") or []:
        row = {}
        for cdef in cols:
            key, label = cdef["key"], cdef["label"]
            v = r.get(key)
            if numeric(key) and isinstance(v, (int, float)) and not isinstance(v, bool):
                row[label] = float(v)
            else:
                row[label] = str(v) if v not in (None, "") else "-"
        rows.append(row)
    money_cols = [cdef["label"] for cdef in cols if money(cdef["key"], cdef["label"])]
    # Every numeric column gets a total, as the report always had: days
    # and hours as well as dirhams. The payroll clerk reads the OT hours
    # total off the foot of the sheet.
    total_cols = [cdef["label"] for cdef in cols
                  if rows and all(isinstance(r.get(cdef["label"]), (int, float))
                                  for r in rows)]
    return rows, money_cols, total_cols


def build_generic_result_pdf(result_dict, cycle_label, title=None, notes=None, subtitle=None):
    cols = result_dict["columns"]
    styles = getSampleStyleSheet()
    cell_style = ParagraphStyle("TblCell", parent=styles["Normal"], fontSize=7, leading=9)
    num_style = ParagraphStyle("TblNum", parent=cell_style, alignment=2)          # right
    head_style = ParagraphStyle("TblHead", parent=styles["Normal"], fontSize=7.5, leading=9,
                                 textColor=colors.white, fontName="Helvetica-Bold")
    bold_style = ParagraphStyle("TblBold", parent=styles["Normal"], fontSize=7.5, leading=9, fontName="Helvetica-Bold")
    bold_num = ParagraphStyle("TblBoldNum", parent=bold_style, alignment=2)

    def is_money(key):
        k = key.lower()
        return "cost" in k or "amount" in k or "salary" in k or "pay" in k

    def is_numeric(key):
        k = key.lower()
        return not (k.startswith("dim_") or k in ("adjustments", "notes", "adjustments_notes") or "reason" in k)

    def fmt(key, v):
        """Money gets 2 decimals (21,344.92); other numbers get thousands
        separators but keep their natural precision (1,776 stays whole,
        12.5 stays 12.5)."""
        if v is None or v == "":
            return ""
        if isinstance(v, (int, float)):
            if is_money(key):
                return f"{v:,.2f}"
            return f"{v:,.10g}" if v != int(v) else f"{int(v):,}"
        return str(v)

    def cell(c, v, bold=False):
        text = fmt(c["key"], v)
        if is_numeric(c["key"]):
            return Paragraph(text, bold_num if bold else num_style)
        # Every adjustment on its own line, so a man with three reads as
        # three and not as one run-on sentence.
        if c["key"] == "adjustments" and text:
            text = "<br/>".join(_esc(p.strip()) for p in text.split(", ") if p.strip())
        elif c["key"] == "adjustments_notes" and text:
            # Adjustments as they are; the note beneath in quiet italic,
            # so the figure and the explanation are told apart at a glance.
            parts = []
            for line in text.split("\n"):
                line = line.strip()
                if not line:
                    continue
                # The note reads in the same black as the adjustments -
                # a faded grey looked like an afterthought on paper.
                parts.append(_esc(line[6:] if line.startswith("Note: ") else line))
            text = "<br/>".join(parts)
        else:
            text = _esc(text)
        return Paragraph(text, bold_style if bold else cell_style)

    data = [[Paragraph(c["label"], head_style) for c in cols]]
    for row in result_dict["rows"]:
        data.append([cell(c, row.get(c["key"], "")) for c in cols])

    totals = result_dict.get("totals") or {}
    if totals:
        trow = []
        for i, c in enumerate(cols):
            v = totals.get(c["key"])
            trow.append(Paragraph("TOTAL", bold_style) if i == 0 else cell(c, v, bold=True))
        data.append(trow)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=22 * mm, bottomMargin=12 * mm,
                             leftMargin=10 * mm, rightMargin=10 * mm)
    tbl = Table(data, colWidths=_column_widths(cols, doc.width), repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(f"#{BRAND_RED}")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D0D0D0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2 if totals else -1),
         [colors.white, colors.HexColor("#FAF7F5")]),
    ]
    if totals:
        style_cmds.append(("BACKGROUND", (0, -1), (-1, -1), colors.HexColor(f"#{GREEN_FILL}")))
    tbl.setStyle(TableStyle(style_cmds))

    story = [Paragraph(f"{title or 'Report'} - {cycle_label}", ParagraphStyle(
        "Title", parent=styles["Normal"], fontSize=13, fontName="Helvetica-Bold",
        spaceAfter=2 if subtitle else 8))]
    if subtitle:
        story.append(Paragraph(subtitle, ParagraphStyle(
            "Sub", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#666666"),
            spaceAfter=8)))
    if notes:
        # The notes go above the figures: they are what management is
        # meant to read first, and a page of numbers is easy to stop at.
        note_style = ParagraphStyle("Note", parent=styles["Normal"], fontSize=8.5, leading=12)
        note_head = ParagraphStyle("NoteHead", parent=styles["Normal"], fontSize=8,
                                   fontName="Helvetica-Bold", textColor=colors.HexColor(f"#{BRAND_RED}"),
                                   spaceAfter=2)
        body = "<br/>".join(_esc(line) for line in str(notes).splitlines())
        box = Table([[Paragraph("NOTES", note_head)], [Paragraph(body, note_style)]],
                    colWidths=[doc.width])
        box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FBF6F4")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E7CEC9")),
            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, 0), 6), ("BOTTOMPADDING", (0, -1), (-1, -1), 6),
        ]))
        story += [box, Spacer(1, 8)]
    story.append(tbl)
    doc.build(story, onFirstPage=_draw_logo_on_page, onLaterPages=_draw_logo_on_page)
    buf.seek(0)
    return buf


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ---------------------------------------------------------------------
# STORE / INVENTORY EXPORTS
# ---------------------------------------------------------------------
def build_store_report_excel(title, rows, subtitle="", orientation=None, money_cols=None,
                             total_cols=None):
    """
    Any store report as a formatted sheet: company header, report title,
    the period it covers, bordered auto-width columns, and a totals row
    for numeric money columns. Column set is taken from the data, so one
    function serves every report rather than one per report drifting apart.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Report"
    thin = Side(style="thin", color="DDDDDD")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(2, len(rows[0]) if rows else 2))
    h = ws.cell(row=1, column=1, value="INFINIA CONTRACTING LLC")
    h.font = Font(bold=True, size=13)
    h.alignment = Alignment(horizontal="center")
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=max(2, len(rows[0]) if rows else 2))
    t = ws.cell(row=2, column=1, value=title)
    t.font = Font(bold=True, size=11)
    t.alignment = Alignment(horizontal="center")
    if subtitle:
        ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=max(2, len(rows[0]) if rows else 2))
        s = ws.cell(row=3, column=1, value=subtitle)
        s.font = Font(size=9, italic=True, color="777777")
        s.alignment = Alignment(horizontal="center")

    r = 5
    if not rows:
        ws.cell(row=r, column=1, value="Nothing to show.").font = Font(italic=True, color="999999")
        buf = io.BytesIO()
        for _ws in wb.worksheets:
            _excel_logo_header(_ws)
        wb.save(buf); buf.seek(0); return buf

    cols = list(rows[0].keys())
    money_like = ((lambda k: k in set(money_cols)) if money_cols is not None else _is_money)
    # The same one alignment per column the PDF uses, heading included.
    aligns = {k: col_align(k, rows) for k in cols}
    excel_align = {"L": "left", "C": "center", "R": "right"}
    header_row = r
    for i, k in enumerate(cols, start=1):
        c = ws.cell(row=r, column=i, value=_store_label(k))
        c.font = Font(bold=True, color="FFFFFF", size=10)
        c.fill = PatternFill("solid", fgColor=BRAND_RED)
        c.alignment = Alignment(horizontal=excel_align[aligns[k]], vertical="center",
                                wrap_text=True)
        c.border = border
    r += 1

    numeric_totals = {k: 0 for k in cols
                      if (k in set(total_cols) if total_cols is not None else money_like(k))}
    for row in rows:
        for i, k in enumerate(cols, start=1):
            v = row.get(k, "")
            if isinstance(v, dict):
                # Site breakdowns are counts: "704: 380", never "704: 380.0".
                v = ", ".join(f"{a}: {_clean_qty(b)}" for a, b in v.items()) or "-"
            elif isinstance(v, bool):
                v = "Yes" if v else ""
            elif k == "item_type" and v:
                v = str(v).title()
            c = ws.cell(row=r, column=i, value=v)
            c.border = border
            c.font = Font(size=10)
            if isinstance(v, (int, float)):
                # Counts keep no fake decimals; money always shows two.
                # Alignment follows the column, like every other cell.
                c.number_format = '#,##0.00' if money_like(k) else '#,##0.##'
                c.alignment = Alignment(horizontal=excel_align[aligns[k]], vertical="center")
                if k in numeric_totals:
                    numeric_totals[k] += v
            elif isinstance(v, str) and "\n" in v:
                # One site per line, and the row grows to hold them.
                c.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
            else:
                c.alignment = Alignment(horizontal=excel_align[aligns[k]], vertical="center")
        r += 1

    if numeric_totals:
        for i, k in enumerate(cols, start=1):
            v = round(numeric_totals[k], 2) if k in numeric_totals else ("TOTAL" if i == 1 else "")
            c = ws.cell(row=r, column=i, value=v)
            c.font = Font(bold=True)
            c.fill = PatternFill("solid", fgColor=GREEN_FILL)
            c.alignment = Alignment(horizontal=excel_align[aligns[k]], vertical="center")
            c.border = border
            if isinstance(v, (int, float)):
                c.number_format = '#,##0.00' if money_like(k) else '#,##0.##'

    # Long reports stay usable: headers stay put while scrolling, and the
    # filter arrows let the office slice by site or type right in Excel.
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
    ws.auto_filter.ref = f"A{header_row}:{get_column_letter(len(cols))}{header_row + len(rows)}"

    # Each column as wide as it needs, not as wide as the widest - a
    # "Unit" column holding "pcs" took the same eleven characters as a
    # material name, and the sheet ran off the side of the page for no
    # reason. Multi-line cells are measured by their longest line.
    for i, k in enumerate(cols, start=1):
        widest = 0
        for row in rows:
            v = row.get(k, "")
            if v in (None, ""):
                continue
            widest = max(widest, max(len(x) for x in str(v).split("\n")))
        width = max(len(str(_store_label(k))) + 2, widest + 2)
        ws.column_dimensions[get_column_letter(i)].width = min(max(width, 6), 46)
    # r is the totals row when there is one, else one past the last row.
    print_ready(ws, orientation or choose_orientation(rows, cols),
                header_row=header_row, last_col=len(cols),
                last_row=r if numeric_totals else r - 1, title=title)

    buf = io.BytesIO()
    for _ws in wb.worksheets:
        _excel_logo_header(_ws)
    wb.save(buf); buf.seek(0); return buf


def build_store_report_pdf(title, rows, subtitle="", orientation=None, money_cols=None,
                           total_cols=None):
    """A report as paper.

    The page stands up or lies on its side to suit the report: a short
    one wastes less paper upright, a wide one is unreadable that way.
    Callers may force it; left alone, the data decides.
    """
    buf = io.BytesIO()
    orientation = orientation or choose_orientation(rows)
    doc = SimpleDocTemplate(buf, pagesize=_page_size(orientation),
                             topMargin=22 * mm, bottomMargin=10 * mm,
                             leftMargin=8 * mm, rightMargin=8 * mm)
    styles = getSampleStyleSheet()
    head = ParagraphStyle("H", parent=styles["Normal"], fontSize=8, leading=10,
                           textColor=colors.white, fontName="Helvetica-Bold", alignment=TA_CENTER)
    cell = ParagraphStyle("C", parent=styles["Normal"], fontSize=8, leading=10, alignment=TA_CENTER)
    el = [Paragraph("<b>INFINIA CONTRACTING LLC</b>",
                     ParagraphStyle("T", parent=styles["Normal"], fontSize=13, alignment=TA_CENTER)),
          Spacer(1, 3),
          Paragraph(f"<b>{title}</b>",
                     ParagraphStyle("S", parent=styles["Normal"], fontSize=10, alignment=TA_CENTER))]
    if subtitle:
        el += [Spacer(1, 2), Paragraph(subtitle,
                ParagraphStyle("Sub", parent=styles["Normal"], fontSize=8,
                                textColor=colors.HexColor("#777777"), alignment=TA_CENTER))]
    el.append(Spacer(1, 8))

    if not rows:
        el.append(Paragraph("Nothing to show.", cell))
        doc.build(el, onFirstPage=_draw_logo_on_page, onLaterPages=_draw_logo_on_page); buf.seek(0); return buf

    cols = list(rows[0].keys())
    # A caller that knows which of its columns are money says so; the
    # rest are guessed from the column name. A payroll column called
    # "Net Pay" is money and no amount of guessing from the word will
    # say so.
    money_like = ((lambda k: k in set(money_cols)) if money_cols is not None else _is_money)
    # One alignment per column, and the heading takes the same one, so a
    # centred heading never sits over a left-hand column again.
    aligns = {k: col_align(k, rows) for k in cols}
    cellL = ParagraphStyle("CL", parent=cell, alignment=TA_LEFT)
    cellR = ParagraphStyle("CR", parent=cell, alignment=TA_RIGHT)
    headL = ParagraphStyle("HL", parent=head, alignment=TA_LEFT)
    headR = ParagraphStyle("HR", parent=head, alignment=TA_RIGHT)
    pick = {"L": cellL, "C": cell, "R": cellR}
    pickh = {"L": headL, "C": head, "R": headR}
    # Totals sit under their own column, centred with it.
    data = [[Paragraph(_store_label(k), pickh[aligns[k]]) for k in cols]]
    # Which columns add up at the foot: the money ones unless the caller
    # says otherwise (a payroll report totals its days and hours too).
    totals = {k: 0 for k in cols if (k in set(total_cols) if total_cols is not None else money_like(k))}
    for row in rows:
        line = []
        for k in cols:
            v = row.get(k, "")
            sty = pick[aligns[k]]
            if isinstance(v, dict):
                # Site breakdowns are counts: "704: 380", never "704: 380.0".
                v = ", ".join(f"{a}: {_clean_qty(b)}" for a, b in v.items()) or "-"
            elif isinstance(v, bool):
                v = "Yes" if v else ""
            elif isinstance(v, (int, float)):
                if k in totals: totals[k] += v
                v = f"{v:,.2f}" if money_like(k) else _clean_qty(v)
            elif k == "item_type" and v:
                v = str(v).title()
            elif isinstance(v, str) and _looks_like_date(v):
                v = _day(v)
            text = str(v) if v not in (None, "") else "-"
            # A cell holding lines - one site per line - keeps them.
            text = "<br/>".join(_esc(t) for t in text.split("\n")) if "\n" in text else _esc(text)
            line.append(Paragraph(text, sty))
        data.append(line)
    if totals:
        def tot(k):
            return f"{totals[k]:,.2f}" if money_like(k) else _clean_qty(totals[k])
        data.append([Paragraph(f"<b>{tot(k) if k in totals else ('TOTAL' if i == 0 else '')}</b>",
                               pick[aligns[k]])
                     for i, k in enumerate(cols)])

    tbl = Table(data, repeatRows=1,
                colWidths=[doc.width * f for f in col_fractions(rows, cols, money_cols, total_cols)])
    style = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#" + BRAND_RED)),
             ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
             ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
             ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
             ("ROWBACKGROUNDS", (0, 1), (-1, -2 if totals else -1),
              [colors.white, colors.HexColor("#F7F7F7")])]
    if totals:
        style.append(("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#" + GREEN_FILL)))
    tbl.setStyle(TableStyle(style))
    el.append(tbl)
    doc.build(el, onFirstPage=_draw_logo_on_page, onLaterPages=_draw_logo_on_page); buf.seek(0); return buf


# The signature lives outside the code folder, in a data directory
# beside it. Kept inside the repo it would be wiped by the next git
# pull - a deploy would silently start printing orders unsigned.
# INFINIA_DATA_DIR overrides it where the deployment prefers elsewhere.
def _pick_data_dir():
    """The first directory we can actually write a file into.

    Creating a directory is not the same as being able to write in it -
    under systemd the service user may own neither. Each candidate is
    tested by writing a file and deleting it again, so a signature
    upload cannot fail silently later.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.environ.get("INFINIA_DATA_DIR"),
        os.path.join(os.path.dirname(here), "data"),
        os.path.join(os.path.expanduser("~"), ".infinia"),
        os.path.join(tempfile.gettempdir(), "infinia-data"),
    ]
    for d in [c for c in candidates if c]:
        try:
            os.makedirs(d, exist_ok=True)
            probe = os.path.join(d, ".write-test")
            with open(probe, "wb") as f:
                f.write(b"x")
            os.remove(probe)
            return d
        except Exception:
            continue
    return here


DATA_DIR = _pick_data_dir()
SIG_PATH = os.path.join(DATA_DIR, "signature.png")
# A signature photographed on a phone is a photograph, and a photograph
# in PNG is several hundred kilobytes that a lossy format holds in
# twenty. So whichever suits the picture is written - JPEG for a photo,
# PNG where there is transparency to keep - and every reader asks for
# whichever one is actually there rather than assuming the extension.
SIG_PATHS = [os.path.join(DATA_DIR, "signature." + e) for e in ("png", "jpg")]


def signature_file():
    """The signature currently on this server, or None."""
    found = [p for p in SIG_PATHS if os.path.exists(p)]
    if not found:
        return None
    return max(found, key=os.path.getmtime)

# A signature uploaded before this moved is still in the old place;
# carry it across once rather than making somebody upload it again.
_OLD_SIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "signature.png")
try:
    if os.path.exists(_OLD_SIG) and not os.path.exists(SIG_PATH):
        import shutil
        shutil.move(_OLD_SIG, SIG_PATH)
except Exception:
    pass


def build_lpo_pdf(po: dict):
    """A purchase order on one A4 page, laid out as the company's own.

    Header block left and right, vendor, priced lines, totals stacked at
    the right with notes and terms beside them, and the signature. Built
    to print: fixed margins, nothing that reflows off the page, and the
    line table repeating its header if a long order runs over.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=10 * mm, bottomMargin=12 * mm,
                             leftMargin=12 * mm, rightMargin=12 * mm, title=po.get("ref", "LPO"))
    W = doc.width
    styles = getSampleStyleSheet()
    grid = colors.HexColor("#8C8C8C")
    dark = colors.HexColor("#7B1F1A")

    def P(t, size=8.5, bold=False, align=TA_LEFT, colour="#1F2429", leading=None):
        return Paragraph(str(t if t is not None else ""), ParagraphStyle(
            f"s{size}{bold}{align}", parent=styles["Normal"], fontSize=size,
            leading=leading or size + 2.6, alignment=align,
            fontName="Helvetica-Bold" if bold else "Helvetica",
            textColor=colors.HexColor(colour)))

    el = []

    # ---- Company band: logo, address, the words PURCHASE ORDER
    # The logo carries the name, so printing it again beside it was the
    # same words twice. The room goes to the logo instead.
    logo = _logo_image(width_mm=58)
    company = [P("M09 Bin Bishr Building", 8),
               P("Abu Hail,  Dubai , United Arab Emirates", 8),
               P("TRN 100602393900003", 8)]
    band = Table([[logo or "", company, P("PURCHASE ORDER", 16, align=TA_RIGHT)]],
                 colWidths=[W * 0.31, W * 0.37, W * 0.32])
    band.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, 0), 4), ("RIGHTPADDING", (0, 0), (0, 0), 12),
        ("LEFTPADDING", (1, 0), (-1, -1), 8), ("RIGHTPADDING", (1, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("BOX", (0, 0), (-1, -1), 0.6, grid),
    ]))
    el.append(band)

    # ---- The two header columns
    def pairs(rows):
        data = [[P(k, 8, colour="#3B3F44"), P(f": {v}" if v not in ("", None) else ":", 8, bold=True)]
                for k, v in rows]
        t = Table(data, colWidths=[W * 0.155, W * 0.325])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 1.8), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.8),
        ]))
        return t

    # Delivery Date was printed in both columns and Email ID showed our
    # own address, which the supplier already has. The room that frees
    # goes to what the order was missing: the project, the plot, and who
    # to call about it.
    def box(title, rows, wide_label=0.40):
        head = Table([[P(title, 8, bold=True, colour="#FFFFFF")]], colWidths=[W * 0.495])
        head.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#2E3238")),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 6),
                                  ("TOPPADDING", (0, 0), (-1, -1), 3),
                                  ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        body = [[P(k, 8, colour="#3B3F44"),
                 P("" if not k else (v if v not in ("", None) else "-"), 8, bold=True)]
                for k, v in rows]
        t = Table(body, colWidths=[W * 0.495 * wide_label, W * 0.495 * (1 - wide_label)])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 1.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6),
        ]))
        return head, t

    # Ours on the left, theirs on the right. The vendor used to have a
    # full-width band of its own, which cost a third of the header for
    # three lines of text.
    def level(a, b):
        """Both boxes end at the same line. One side having three rows
        fewer left a step down the middle of the page."""
        n = max(len(a), len(b))
        return (a + [("", "")] * (n - len(a)), b + [("", "")] * (n - len(b)))

    # Eight lines each side. The order's own date and the supplier's
    # quote reference sit with the vendor, which evens the two columns
    # and puts the reference beside the trader it belongs to.
    ours_rows = [
        ("Purchase Order No", po.get("ref", "")),
        ("Delivery Date", po.get("delivery_text", "")),
        ("Project Location", po.get("project_location", "")),
        ("Project &amp; Plot No", po.get("plot_no", "")),
        ("Delivery Address", po.get("site_address", "")),
        ("Job Scope", po.get("job_scope", "")),
        ("Contact Person", po.get("contact_person", "")),
        ("Mobile", po.get("mobile", "")),
    ]
    theirs_rows = [
        ("Supplier", po.get("supplier_name", "")),
        ("TRN", po.get("supplier_trn", "")),
        ("Email", po.get("supplier_email", "")),
        ("Contact Person", po.get("supplier_contact", "")),
        ("Mobile", po.get("supplier_mobile", "")),
        ("Payment Terms", po.get("terms", "")),
        ("Date", po.get("date_text", "")),
        ("Reference No", po.get("supplier_ref", "")),
    ]
    ours_rows, theirs_rows = level(ours_rows, theirs_rows)
    oh, ob = box("PURCHASE ORDER DETAILS", ours_rows)
    th, tb = box("VENDOR DETAILS", theirs_rows)
    # Titles on one row, bodies on the next, in a single table: a shared
    # row is exactly as tall as its taller cell, so both boxes close on
    # the same line however much text is in either.
    head = Table([[oh, th], [ob, tb]], colWidths=[W * 0.495, W * 0.495], hAlign="LEFT")
    head.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (0, -1), 0.6, grid),
        ("BOX", (1, 0), (1, -1), 0.6, grid),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, -1), 9), ("RIGHTPADDING", (1, 0), (1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 0), ("BOTTOMPADDING", (0, 1), (-1, 1), 4),
    ]))
    el.append(head)
    el.append(Spacer(1, 6))

    # ---- Priced lines
    hd = lambda t, a=TA_CENTER: Paragraph(f"<b>{t}</b>", ParagraphStyle(
        "hd", parent=styles["Normal"], fontSize=8.5, leading=11,
        textColor=colors.white, alignment=a, fontName="Helvetica-Bold"))
    data = [[hd("#"), hd("Item &amp; Description", TA_LEFT), hd("Qty", TA_RIGHT),
             hd("Rate", TA_RIGHT), hd("Tax %", TA_RIGHT), hd("Tax", TA_RIGHT), hd("Amount", TA_RIGHT)]]
    sub = 0.0
    for i, l in enumerate(po.get("lines", []), start=1):
        qty = float(l.get("qty") or 0)
        rate = float(l.get("rate") or 0)
        amount = qty * rate
        taxpc = float(l.get("tax_pct") or 0)
        sub += amount
        desc = [P(l.get("description", ""), 8.5)]
        if (l.get("description2") or "").strip():
            desc.append(P(l["description2"].strip(), 7.5, colour="#555555"))
        data.append([P(i, 8.5, align=TA_CENTER), desc,
                     P(f"{qty:,.2f}", 8.5, align=TA_RIGHT),
                     P(f"{rate:,.2f}", 8.5, align=TA_RIGHT),
                     P(f"{taxpc:,.2f}", 8.5, align=TA_RIGHT),
                     P(f"{amount * taxpc / 100:,.2f}", 8.5, align=TA_RIGHT),
                     P(f"{amount:,.2f}", 8.5, align=TA_RIGHT)])
    widths = [W * x for x in (0.05, 0.40, 0.09, 0.11, 0.08, 0.11, 0.16)]
    lt = Table(data, colWidths=widths, repeatRows=1)
    lt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), dark),
        ("GRID", (0, 0), (-1, -1), 0.5, grid),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    el.append(lt)

    # ---- Notes and terms on the left, money on the right
    disc = float(po.get("discount_pct") or 0)
    discount = sub * disc / 100.0
    net = sub - discount
    vat = sum(float(l.get("qty") or 0) * float(l.get("rate") or 0) *
              float(l.get("tax_pct") or 0) / 100.0 for l in po.get("lines", []))
    if disc:
        vat = net * (float(po.get("tax_pct") or 5)) / 100.0
    total = net + vat

    money = [[P("Sub Total", 8.5, align=TA_RIGHT), P(f"{sub:,.2f}", 8.5, align=TA_RIGHT)]]
    if disc:
        money.append([P(f"Discount({disc:,.2f}%)", 8.5, align=TA_RIGHT),
                      P(f"(-) {discount:,.2f}", 8.5, align=TA_RIGHT)])
    money.append([P(f"Standard Rate ({po.get('tax_pct', 5):g}%)", 8.5, align=TA_RIGHT),
                  P(f"{vat:,.2f}", 8.5, align=TA_RIGHT)])
    money.append([P("<b>Total</b>", 10, align=TA_RIGHT), P(f"<b>AED {total:,.2f}</b>", 10, align=TA_RIGHT)])
    mt = Table(money, colWidths=[W * 0.24, W * 0.20])
    mt.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, len(money) - 2), (-1, len(money) - 2), 0.5, grid),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))

    sig_cell = [P("For Infinia Contracting LLC", 8.5, align=TA_CENTER)]
    _sig = signature_file()
    if _sig:
        try:
            from reportlab.platypus import Image as RLImage
            sig_cell.append(Spacer(1, 2))
            # Fitted inside the space rather than forced to fill it: a
            # signature is not the shape of the box it prints in, and
            # stretching one to fit is the sort of thing a supplier
            # notices on paper.
            _w, _h = _fit_box(_sig, 34, 13)
            sig_cell.append(RLImage(_sig, width=_w * mm, height=_h * mm))
        except Exception:
            sig_cell.append(Spacer(1, 13 * mm))
    else:
        sig_cell.append(Spacer(1, 13 * mm))
    sig_cell.append(P("Authorized Signature", 8.5, align=TA_CENTER))
    sigt = Table([[sig_cell]], colWidths=[W * 0.44])
    sigt.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, grid),
                              ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                              ("TOPPADDING", (0, 0), (-1, -1), 5),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))

    notes_cell = []
    if (po.get("notes") or "").strip():
        notes_cell.append(P("Notes", 8, colour="#3B3F44"))
        for ln in po["notes"].splitlines():
            notes_cell.append(P(ln, 8.5))
        notes_cell.append(Spacer(1, 6))
    notes_cell.append(P("Terms &amp; Conditions", 8, colour="#3B3F44"))
    for ln in (po.get("terms_text") or "").splitlines():
        if ln.strip():
            notes_cell.append(P(ln.strip(), 8, leading=10.5))

    foot = Table([[notes_cell, [mt, Spacer(1, 5), sigt]]], colWidths=[W * 0.54, W * 0.46])
    foot.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, 0), 2), ("RIGHTPADDING", (0, 0), (0, 0), 10),
        ("LEFTPADDING", (1, 0), (1, 0), 0), ("RIGHTPADDING", (1, 0), (1, 0), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    el.append(foot)

    doc.build(el)
    buf.seek(0)
    return buf


def build_lpo_excel(po: dict):
    """The same order as a spreadsheet, set up to print on one A4 page.

    Same layout as the PDF so the two are recognisably one document, and
    every figure is a real number rather than text, so he can change a
    rate and the totals follow."""
    wb = Workbook()
    ws = wb.active
    ws.title = "LPO"
    widths = [5, 30, 12, 12, 8, 11, 14]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    thin = Side(style="thin", color="8C8C8C")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    L, R, C = (Alignment(horizontal="left", vertical="center", wrap_text=True),
               Alignment(horizontal="right", vertical="center"),
               Alignment(horizontal="center", vertical="center", wrap_text=True))

    ws.row_dimensions[1].height = 26          # room for the logo
    ws.merge_cells("B2:E2"); ws["B2"] = "INFINIA CONTRACTING LLC"; ws["B2"].font = Font(bold=True, size=14)
    ws.merge_cells("F2:G2"); ws["F2"] = "PURCHASE ORDER"
    ws["F2"].font = Font(bold=True, size=14); ws["F2"].alignment = R
    ws.merge_cells("B3:E3"); ws["B3"] = "M09 Bin Bishr Building"
    ws.merge_cells("B4:E4"); ws["B4"] = "Abu Hail,  Dubai , United Arab Emirates"
    ws.merge_cells("B5:E5"); ws["B5"] = "TRN 100602393900003"
    for r in (3, 4, 5):
        ws[f"B{r}"].font = Font(size=9)

    def pair(row, k1, v1, k2, v2):
        ws.cell(row=row, column=1, value=k1).font = Font(size=9, color="3B3F44")
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=2)
        c = ws.cell(row=row, column=3, value=v1); c.font = Font(size=9, bold=True); c.alignment = L
        ws.cell(row=row, column=4, value=k2).font = Font(size=9, color="3B3F44")
        c2 = ws.cell(row=row, column=6, value=v2); c2.font = Font(size=9, bold=True); c2.alignment = L
        ws.merge_cells(start_row=row, start_column=4, end_row=row, end_column=5)
        ws.merge_cells(start_row=row, start_column=6, end_row=row, end_column=7)

    pair(6, "Purchase Order No", po.get("ref", ""), "Plot No", po.get("plot_no", ""))
    pair(7, "Date", po.get("date_text", ""), "Contact Person", po.get("contact_person", ""))
    pair(8, "Terms", po.get("terms", ""), "Mobile No", po.get("mobile", ""))
    pair(9, "Delivery Date", po.get("delivery_text", ""), "Delivery Date", po.get("delivery_text", ""))
    pair(10, "Ref#", po.get("supplier_ref", ""), "Email ID", po.get("email", ""))
    pair(11, "", "", "Job Scope", po.get("job_scope", ""))
    pair(12, "", "", "Project Location Name", po.get("project_location", ""))
    for r in range(6, 13):
        for col in range(1, 8):
            ws.cell(row=r, column=col).border = box

    r = 14
    ws.cell(row=r, column=1, value="Vendor Address").font = Font(size=9, color="3B3F44")
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=7)
    for col in range(1, 8):
        ws.cell(row=r, column=col).fill = PatternFill("solid", fgColor="F0F0F0")
        ws.cell(row=r, column=col).border = box
    r += 1
    ws.cell(row=r, column=1, value=po.get("supplier_name", "")).font = Font(bold=True, size=10)
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=7)
    for col in range(1, 8):
        ws.cell(row=r, column=col).border = box
    for ln in ([f"TRN {po['supplier_trn']}"] if po.get("supplier_trn") else []):
        r += 1
        ws.cell(row=r, column=1, value=ln).font = Font(size=9)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=7)
        for col in range(1, 8):
            ws.cell(row=r, column=col).border = box

    r += 2
    head_row = r
    for i, label in enumerate(["#", "Item & Description", "Qty", "Rate", "Tax %", "Tax", "Amount"], start=1):
        c = ws.cell(row=r, column=i, value=label)
        c.font = Font(bold=True, color="FFFFFF", size=9.5)
        c.fill = PatternFill("solid", fgColor="7B1F1A")
        c.alignment = C if i != 2 else Alignment(horizontal="left", vertical="center")
        c.border = box
    ws.row_dimensions[r].height = 18
    first_line = r + 1
    for i, l in enumerate(po.get("lines", []), start=1):
        r += 1
        qty = float(l.get("qty") or 0); rate = float(l.get("rate") or 0)
        taxpc = float(l.get("tax_pct") or 0)
        desc = l.get("description", "")
        if (l.get("description2") or "").strip():
            desc += "\n" + l["description2"].strip()
        vals = [i, desc, qty, rate, taxpc, None, None]
        for col, v in enumerate(vals, start=1):
            c = ws.cell(row=r, column=col, value=v)
            c.border = box
            c.alignment = L if col == 2 else (C if col == 1 else R)
            c.font = Font(size=9.5)
        ws.cell(row=r, column=6).value = f"=ROUND(C{r}*D{r}*E{r}/100,2)"
        ws.cell(row=r, column=7).value = f"=ROUND(C{r}*D{r},2)"
        for col in (3, 4, 6, 7):
            ws.cell(row=r, column=col).number_format = "#,##0.00"
        ws.row_dimensions[r].height = 26 if (l.get("description2") or "").strip() else 17
    last_line = r

    r += 2
    money_start = r
    def money(label, formula, bold=False, size=9.5):
        nonlocal r
        c1 = ws.cell(row=r, column=5, value=label)
        c1.alignment = R; c1.font = Font(bold=bold, size=size)
        ws.merge_cells(start_row=r, start_column=5, end_row=r, end_column=6)
        c2 = ws.cell(row=r, column=7, value=formula)
        c2.alignment = R; c2.font = Font(bold=bold, size=size)
        c2.number_format = '"AED" #,##0.00' if bold else "#,##0.00"
        r += 1
    money("Sub Total", f"=SUM(G{first_line}:G{last_line})")
    disc = float(po.get("discount_pct") or 0)
    if disc:
        money(f"Discount({disc:g}%)", f"=-SUM(G{first_line}:G{last_line})*{disc}/100")
    money(f"Standard Rate ({po.get('tax_pct', 5):g}%)",
          f"=SUM(F{first_line}:F{last_line})" if not disc
          else f"=(SUM(G{first_line}:G{last_line})*(1-{disc}/100))*{po.get('tax_pct',5)}/100")
    money("Total", f"=SUM(G{money_start}:G{r-1})", bold=True, size=11)

    nr = money_start
    if (po.get("notes") or "").strip():
        ws.cell(row=nr, column=1, value="Notes").font = Font(size=9, color="3B3F44")
        nr += 1
        import textwrap as _tw
        for ln in po["notes"].splitlines():
            for piece in _tw.wrap(ln, width=70) or [""]:
                ws.cell(row=nr, column=1, value=piece).font = Font(size=9)
                ws.merge_cells(start_row=nr, start_column=1, end_row=nr, end_column=4)
                nr += 1
        nr += 1
    ws.cell(row=nr, column=1, value="Terms & Conditions").font = Font(size=9, color="3B3F44")
    nr += 1
    import textwrap
    for ln in (po.get("terms_text") or "").splitlines():
        if not ln.strip():
            continue
        # Wrapped by hand: a merged cell does not auto-fit its height, so
        # a long clause would otherwise be cut off at the column edge.
        for piece in textwrap.wrap(ln.strip(), width=78) or [""]:
            c = ws.cell(row=nr, column=1, value=piece)
            c.font = Font(size=8)
            c.alignment = Alignment(horizontal="left", vertical="top")
            ws.merge_cells(start_row=nr, start_column=1, end_row=nr, end_column=4)
            ws.row_dimensions[nr].height = 11
            nr += 1

    sr = max(r + 1, nr + 1)          # below both the money and the terms
    ws.cell(row=sr, column=5, value="For Infinia Contracting LLC").alignment = C
    ws.merge_cells(start_row=sr, start_column=5, end_row=sr, end_column=7)
    ws.cell(row=sr + 3, column=5, value="Authorized Signature").alignment = C
    ws.merge_cells(start_row=sr + 3, start_column=5, end_row=sr + 3, end_column=7)
    # One outer frame, not a grid - the inner lines made it look like an
    # empty table rather than a place to sign.
    edge = Side(style="thin", color="8C8C8C")
    for col in range(5, 8):
        top = ws.cell(row=sr, column=col)
        bot = ws.cell(row=sr + 3, column=col)
        top.border = Border(top=edge, bottom=None,
                            left=edge if col == 5 else None, right=edge if col == 7 else None)
        bot.border = Border(bottom=edge, top=None,
                            left=edge if col == 5 else None, right=edge if col == 7 else None)
        for rr in (sr + 1, sr + 2):
            ws.cell(row=rr, column=col).border = Border(
                left=edge if col == 5 else None, right=edge if col == 7 else None)
    ws.row_dimensions[sr + 1].height = 22
    ws.row_dimensions[sr + 2].height = 22
    try:
        if signature_file():
            from openpyxl.drawing.image import Image as XLImage
            sig = XLImage(signature_file())
            sig.width, sig.height = 110, 48
            ws.add_image(sig, f"F{sr + 1}")
    except Exception:
        pass

    ws.print_area = f"A1:G{max(sr + 4, nr + 1)}"
    ws.page_setup.orientation = "portrait"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins.left = ws.page_margins.right = 0.4
    ws.page_margins.top = ws.page_margins.bottom = 0.4

    # The logo goes in here, not through _excel_logo_header: that helper
    # inserts rows into a finished sheet, which moves every cell while
    # the formulas keep pointing at the old row numbers - totals came
    # out as zero. The layout below already starts at row 1 with the
    # company block, so the picture simply sits on top of it.
    try:
        if os.path.exists(LOGO_PATH):
            from openpyxl.drawing.image import Image as XLImage
            img = XLImage(LOGO_PATH)
            img.width, img.height = 150, 25
            ws.add_image(img, "A1")
    except Exception:
        pass

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def build_error_check_pdf(cycle_label, workers, note=""):
    """A reminder sheet for a site: the workers whose cards are not
    finished, with the exact days each one is short.

    Written to be handed to a foreman and worked through - one line per
    worker, the dates spelled out, and a column for him to write what
    the man actually did."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=22 * mm, bottomMargin=12 * mm,
                             leftMargin=10 * mm, rightMargin=10 * mm)
    styles = getSampleStyleSheet()
    head = ParagraphStyle("H", parent=styles["Normal"], fontSize=8.5, leading=11,
                           textColor=colors.white, fontName="Helvetica-Bold", alignment=TA_CENTER)
    cell = ParagraphStyle("C", parent=styles["Normal"], fontSize=9, leading=12, alignment=TA_LEFT)
    ctr = ParagraphStyle("CC", parent=styles["Normal"], fontSize=9, leading=12, alignment=TA_CENTER)

    el = [Paragraph("<b>INFINIA CONTRACTING LLC</b>",
                     ParagraphStyle("T", parent=styles["Normal"], fontSize=13, alignment=TA_CENTER)),
          Spacer(1, 3),
          Paragraph("<b>Attendance still needed</b>",
                     ParagraphStyle("S", parent=styles["Normal"], fontSize=11, alignment=TA_CENTER)),
          Spacer(1, 2),
          Paragraph(cycle_label,
                     ParagraphStyle("D", parent=styles["Normal"], fontSize=9,
                                    textColor=colors.HexColor("#666666"), alignment=TA_CENTER)),
          Spacer(1, 9)]
    if note:
        el.append(Paragraph(note, ParagraphStyle("N", parent=styles["Normal"], fontSize=9,
                                                  textColor=colors.HexColor("#444444"))))
        el.append(Spacer(1, 8))

    data = [[Paragraph("Emp No", head), Paragraph("Name", head), Paragraph("Trade", head),
             Paragraph("Days needed", head), Paragraph("What he did on those days", head)]]
    for w in workers:
        data.append([Paragraph(w.get("emp_no", ""), ctr),
                     Paragraph(w.get("name", ""), cell),
                     Paragraph(w.get("trade", "") or "-", cell),
                     Paragraph(w.get("days", "") or "-", cell),
                     Paragraph("", cell)])

    tbl = Table(data, colWidths=[doc.width * x for x in (0.11, 0.24, 0.15, 0.24, 0.26)], repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#B23A2E")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#B0B0B0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 1), (-1, -1), 7), ("BOTTOMPADDING", (0, 1), (-1, -1), 7),
        *[("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F7F7F7"))
          for i in range(2, len(data), 2)],
    ]))
    el.append(tbl)
    el.append(Spacer(1, 14))
    el.append(Paragraph("Filled in by ____________________          Date ____________________",
                        ParagraphStyle("F", parent=styles["Normal"], fontSize=9,
                                       textColor=colors.HexColor("#555555"))))
    doc.build(el, onFirstPage=_draw_logo_on_page, onLaterPages=_draw_logo_on_page)
    buf.seek(0)
    return buf


def build_error_check_excel(cycle_label, workers, note=""):
    """The same reminder as a spreadsheet, for sending on."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Attendance needed"
    widths = [12, 26, 16, 34, 30]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    thin = Side(style="thin", color="B0B0B0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=5)
    t = ws.cell(row=1, column=1, value="Attendance still needed")
    t.font = Font(bold=True, size=13)
    t.alignment = Alignment(horizontal="center")
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=5)
    s = ws.cell(row=2, column=1, value=cycle_label)
    s.font = Font(size=10, color="666666")
    s.alignment = Alignment(horizontal="center")
    r = 4
    if note:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
        n = ws.cell(row=r, column=1, value=note)
        n.font = Font(size=10, color="444444")
        r += 2
    for i, label in enumerate(["Emp No", "Name", "Trade", "Days needed",
                               "What he did on those days"], start=1):
        c = ws.cell(row=r, column=i, value=label)
        c.font = Font(bold=True, color="FFFFFF", size=10)
        c.fill = PatternFill("solid", fgColor="B23A2E")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = border
    ws.row_dimensions[r].height = 22
    r += 1
    for w in workers:
        for i, v in enumerate([w.get("emp_no", ""), w.get("name", ""), w.get("trade", "") or "-",
                               w.get("days", "") or "-", ""], start=1):
            c = ws.cell(row=r, column=i, value=v)
            c.border = border
            c.alignment = Alignment(vertical="center", wrap_text=(i in (4, 5)),
                                    horizontal="center" if i == 1 else "left")
        ws.row_dimensions[r].height = 20
        r += 1
    buf = io.BytesIO()
    for _ws in wb.worksheets:
        _excel_logo_header(_ws)
    wb.save(buf)
    buf.seek(0)
    return buf


def build_material_request_pdf(mr: dict):
    """The request itself as a document the store keeper can send to the office."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=26 * mm, bottomMargin=14 * mm,
                             leftMargin=14 * mm, rightMargin=14 * mm)
    styles = getSampleStyleSheet()
    cen = lambda s, sz, b=False: Paragraph(
        (f"<b>{s}</b>" if b else s),
        ParagraphStyle("x", parent=styles["Normal"], fontSize=sz, alignment=TA_CENTER))
    cell = ParagraphStyle("c", parent=styles["Normal"], fontSize=9, leading=11)
    head = ParagraphStyle("h", parent=styles["Normal"], fontSize=9, leading=11,
                           textColor=colors.white, fontName="Helvetica-Bold", alignment=TA_CENTER)

    el = [cen("INFINIA CONTRACTING LLC", 14, True), Spacer(1, 5),
          cen("MATERIAL REQUEST", 11, True), Spacer(1, 12)]

    cellR = ParagraphStyle("cr", parent=cell, alignment=TA_RIGHT)
    urg = mr["urgency"]
    urg_p = (Paragraph('<font color="#B26A00"><b>Urgent</b></font>', cell)
             if urg == "urgent" else Paragraph(str(urg).title(), cell))
    info = [["Request No:", mr["ref"], "Date:", mr["requested_on"]],
            ["Site:", mr["site"] or "-", "Needed by:", mr.get("needed_by") or "-"],
            ["Requested by:", mr["requested_by"] or "-", "Urgency:", urg_p],
            ["Status:", mr["status"].title(), "", ""]]
    t = Table([[Paragraph(f"<b>{a}</b>", cell),
                b if isinstance(b, Paragraph) else Paragraph(str(b), cell),
                Paragraph(f"<b>{c}</b>", cell),
                d if isinstance(d, Paragraph) else Paragraph(str(d), cell)] for a, b, c, d in info],
              colWidths=[doc.width * 0.16, doc.width * 0.34, doc.width * 0.16, doc.width * 0.34])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DDDDDD")),
                            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F4F5F7")),
                            ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#F4F5F7")),
                            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    el += [t, Spacer(1, 12)]

    # "What it is for" travels with the request - it's the one thing the
    # office needs to judge whether to order, so the printed copy carries
    # it just like the screen does.
    lhead = ParagraphStyle("lh", parent=head, fontSize=8)
    data = [[Paragraph(h, lhead) for h in
             ["#", "Material", "Unit", "Requested", "Approved", "Received", "Still due", "What it is for", "Notes"]]]
    for i, ln in enumerate(mr["lines"], start=1):
        out = (ln["qty_requested"] or 0) - (ln["qty_received"] or 0)
        name = (f'{ln.get("item_code")} - {ln.get("item_name")}' if ln.get("item_code") else
                (ln.get("item_name") or ln.get("description") or "-"))
        data.append([Paragraph(str(i), cell), Paragraph(name, cell), Paragraph(ln["unit"], cell),
                     Paragraph(_clean_qty(ln["qty_requested"]), cellR),
                     Paragraph(_clean_qty(ln["qty_approved"]) if ln["qty_approved"] else "-", cellR),
                     Paragraph(_clean_qty(ln["qty_received"]) if ln["qty_received"] else "-", cellR),
                     Paragraph(_clean_qty(out) if out > 0 else "-", cellR),
                     Paragraph(ln.get("purpose") or "-", cell),
                     Paragraph(ln.get("notes") or "-", cell)])
    w = doc.width
    tbl = Table(data, colWidths=[w*.03, w*.22, w*.08, w*.11, w*.11, w*.10, w*.10, w*.14, w*.11], repeatRows=1)
    tbl.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#" + BRAND_RED)),
                              ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
                              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                              ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F7F7")])]))
    el += [tbl, Spacer(1, 12)]

    if mr.get("notes"):
        el += [Paragraph(f"<b>Notes:</b> {mr['notes']}", cell), Spacer(1, 6)]
    if mr.get("office_remark"):
        el += [Paragraph(f"<b>Office remark:</b> {mr['office_remark']}", cell), Spacer(1, 6)]

    el += [Spacer(1, 26),
           Table([[Paragraph("Requested by", cell), Paragraph("Approved by", cell), Paragraph("Received by", cell)]],
                 colWidths=[w/3]*3,
                 style=TableStyle([("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.HexColor("#999999")),
                                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                                    ("ALIGN", (0, 0), (-1, -1), "CENTER")]))]
    doc.build(el, onFirstPage=_draw_logo_on_page, onLaterPages=_draw_logo_on_page); buf.seek(0); return buf


# ---- Hire return note ------------------------------------------------
# The paper that settles a hire at the trader's gate. Three quantities
# per line - on hire, going back, short - because that is what an
# argument needs, and a signature block for each side, because a figure
# nobody signed is only ever one party's word.

def _return_rows(note: dict):
    rows = []
    for i, l in enumerate(note.get("lines") or [], 1):
        short = float(l.get("qty_short") or 0)
        rows.append({
            "no": i,
            "description": l.get("description") or "",
            "unit": l.get("unit") or "",
            "on_hire": float(l.get("qty_on_hire") or 0),
            "returned": float(l.get("qty_returned") or 0),
            "short": short,
            "reason": (l.get("short_reason") or "") if short else "",
            "notes": l.get("notes") or "",
        })
    return rows


def _looks_like_date(v):
    """An ISO date the app stored, so a report can print it the way it
    is read aloud rather than as 2026-09-24."""
    v = str(v or "")
    if len(v) != 10 or v[4] != "-" or v[7] != "-":
        return False
    try:
        datetime.strptime(v, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _day(v):
    """A date the way it is read out loud: 24 Sep 2026, not 2026-09-24.

    Stored ISO, printed plainly - and the same on the screen preview, so
    the sheet that is checked is the sheet that comes out."""
    s = str(v or "")
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").strftime("%d %b %Y")
    except Exception:
        return s


def _n(v):
    """A quantity as people write it: 12 not 12.0, 12.5 kept."""
    v = float(v or 0)
    return str(int(v)) if abs(v - int(v)) < 1e-9 else f"{v:,.2f}"


def build_hire_return_pdf(note: dict):
    """The return note on one A4 page, for the driver to carry."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=10 * mm, bottomMargin=12 * mm,
                            leftMargin=12 * mm, rightMargin=12 * mm,
                            title=note.get("ref", "Return Note"))
    W = doc.width
    styles = getSampleStyleSheet()
    grid = colors.HexColor("#8C8C8C")

    def P(t, size=8.5, bold=False, align=TA_LEFT, colour="#1F2429", leading=None):
        return Paragraph(str(t if t is not None else ""), ParagraphStyle(
            f"r{size}{bold}{align}{colour}", parent=styles["Normal"], fontSize=size,
            leading=leading or size + 2.6, alignment=align,
            fontName="Helvetica-Bold" if bold else "Helvetica",
            textColor=colors.HexColor(colour)))

    el = []
    logo = _logo_image(width_mm=58)
    company = [P("M09 Bin Bishr Building", 8),
               P("Abu Hail,  Dubai , United Arab Emirates", 8),
               P("TRN 100602393900003", 8)]
    # The logo prints at 58mm, so its column must not be narrower than
    # that or it runs over the address beside it.
    band = Table([[logo or "", company, P("MATERIAL RETURN NOTE", 13, align=TA_RIGHT)]],
                 colWidths=[W * 0.32, W * 0.30, W * 0.38])
    band.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, 0), 4), ("RIGHTPADDING", (0, 0), (0, 0), 12),
        ("LEFTPADDING", (1, 0), (-1, -1), 8), ("RIGHTPADDING", (1, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("BOX", (0, 0), (-1, -1), 0.6, grid),
    ]))
    el.append(band)
    el.append(Spacer(1, 7))

    def box(title, rows):
        head = Table([[P(title, 8, bold=True, colour="#FFFFFF")]], colWidths=[W * 0.495])
        head.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#2E3238")),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 6),
                                  ("TOPPADDING", (0, 0), (-1, -1), 3),
                                  ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        body = [[P(k, 8, colour="#3B3F44"), P(v if v not in ("", None) else "-", 8, bold=True)]
                for k, v in rows]
        bt = Table(body, colWidths=[W * 0.175, W * 0.32])
        bt.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("BOX", (0, 0), (-1, -1), 0.5, grid),
        ]))
        return [head, bt]

    left = box("RETURNED TO", [("Supplier", note.get("supplier")),
                               ("Attention", note.get("received_by") or ""),
                               ("Returned from", note.get("from_location") or "Central store")])
    right = box("RETURN DETAILS", [("Note No", note.get("ref")),
                                   ("Date", _day(note.get("return_date"))),
                                   ("Driver", note.get("driver")),
                                   ("Vehicle", note.get("vehicle"))])
    hdr = Table([[left, right]], colWidths=[W * 0.5, W * 0.5])
    hdr.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                             ("LEFTPADDING", (0, 0), (0, 0), 0), ("RIGHTPADDING", (0, 0), (0, 0), 6),
                             ("LEFTPADDING", (1, 0), (1, 0), 6), ("RIGHTPADDING", (1, 0), (1, 0), 0)]))
    el.append(hdr)
    el.append(Spacer(1, 9))

    rows = _return_rows(note)
    # Balance is spelled out rather than left to subtraction: without it
    # a partial return reads as though the rest went missing, which is
    # the argument this document exists to prevent.
    nums = ("On hire", "Returned", "Short", "Still on hire")
    head = ["#", "Material", "Unit", "On hire", "Returned", "Short", "Still on hire",
            "Reason / remarks"]
    data = [[P(h, 7.5, bold=True, colour="#FFFFFF",
               align=TA_RIGHT if h in nums else TA_LEFT)
             for h in head]]
    for r in rows:
        remark = " / ".join(x for x in (r["reason"].title() if r["reason"] else "", r["notes"]) if x)
        bal = r["on_hire"] - r["returned"] - r["short"]
        data.append([
            P(r["no"], 8), P(r["description"], 8.5),
            P(r["unit"], 8),
            P(_n(r["on_hire"]), 8.5, align=TA_RIGHT),
            P(_n(r["returned"]), 8.5, bold=True, align=TA_RIGHT),
            P(_n(r["short"]) if r["short"] else "-", 8.5, bold=bool(r["short"]),
              align=TA_RIGHT, colour="#C0392B" if r["short"] else "#1F2429"),
            P(_n(bal) if bal > 1e-9 else "-", 8.5, align=TA_RIGHT,
              colour="#3B3F44" if bal > 1e-9 else "#1F2429"),
            P(remark, 8, colour="#3B3F44"),
        ])
    tot_hire = sum(r["on_hire"] for r in rows)
    tot_ret = sum(r["returned"] for r in rows)
    tot_short = sum(r["short"] for r in rows)
    tot_bal = tot_hire - tot_ret - tot_short
    data.append([P(""), P("TOTAL", 9, bold=True), P(""),
                 P(_n(tot_hire), 9, bold=True, align=TA_RIGHT),
                 P(_n(tot_ret), 9, bold=True, align=TA_RIGHT),
                 P(_n(tot_short) if tot_short else "-", 9, bold=True, align=TA_RIGHT,
                   colour="#C0392B" if tot_short else "#1F2429"),
                 P(_n(tot_bal) if tot_bal > 1e-9 else "-", 9, bold=True, align=TA_RIGHT),
                 P("")])
    widths = [W * 0.035, W * 0.27, W * 0.055, W * 0.085, W * 0.09, W * 0.075,
              W * 0.10, W * 0.29]
    lt = Table(data, colWidths=widths, repeatRows=1)
    lt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E3238")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, grid),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EFEBE6")),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]))
    el.append(lt)
    el.append(Spacer(1, 6))

    if tot_short:
        el.append(P(f"{_n(tot_short)} item(s) recorded as not returned. "
                    "Signing below confirms this quantity as agreed by both parties.",
                    8.5, bold=True, colour="#C0392B"))
        el.append(Spacer(1, 4))
    if tot_bal > 1e-9:
        el.append(P(f"{_n(tot_bal)} item(s) remain on hire and are not part of this return.",
                    8.5, colour="#3B3F44"))
        el.append(Spacer(1, 4))
    if tot_short or tot_bal > 1e-9:
        el.append(Spacer(1, 2))
    if (note.get("notes") or "").strip():
        el.append(P("Notes", 8, colour="#3B3F44"))
        for ln in str(note["notes"]).splitlines():
            if ln.strip():
                el.append(P(ln.strip(), 8.5))
        el.append(Spacer(1, 6))

    # Two signatures: ours on the way out, theirs on receipt. The
    # trader's box is the whole point of the document.
    # No stored signature here, unlike a purchase order. A return note
    # is printed, carried to the supplier's gate and signed by hand on
    # both sides - a signature already on the paper is one nobody
    # watched being given.
    ours = [P("For Infinia Contracting LLC", 8.5, align=TA_CENTER),
            Spacer(1, 15 * mm),
            P("Name, signature &amp; date", 8, align=TA_CENTER, colour="#3B3F44")]

    theirs = [P(f"For {note.get('supplier') or 'the supplier'}", 8.5, align=TA_CENTER),
              Spacer(1, 15 * mm),
              P("Name, signature &amp; stamp", 8, align=TA_CENTER, colour="#3B3F44"),
              P("Date: ______________", 8, align=TA_CENTER, colour="#3B3F44")]

    sig = Table([[ours, theirs]], colWidths=[W * 0.48, W * 0.48])
    sig.setStyle(TableStyle([
        ("BOX", (0, 0), (0, 0), 0.5, grid), ("BOX", (1, 0), (1, 0), 0.5, grid),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    el.append(Spacer(1, 4))
    el.append(sig)
    doc.build(el)
    buf.seek(0)
    return buf


def build_hire_return_excel(note: dict):
    """The same note as a spreadsheet, set to print on one A4 page."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    wb = Workbook()
    ws = wb.active
    ws.title = "Return Note"
    thin = Side(style="thin", color="8C8C8C")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    head_fill = PatternFill("solid", fgColor="2E3238")
    tot_fill = PatternFill("solid", fgColor="EFEBE6")

    ws.merge_cells("A1:G1")
    ws["A1"] = "INFINIA CONTRACTING L.L.C  -  MATERIAL RETURN NOTE"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A1"].alignment = Alignment(horizontal="center")

    pairs = [("Note No", note.get("ref", "")), ("Date", _day(note.get("return_date"))),
             ("Supplier", note.get("supplier", "")),
             ("Returned from", note.get("from_location") or "Central store"),
             ("Driver", note.get("driver", "")), ("Vehicle", note.get("vehicle", ""))]
    r = 3
    for i, (k, v) in enumerate(pairs):
        c = 1 if i % 2 == 0 else 4
        ws.cell(row=r + i // 2, column=c, value=k).font = Font(bold=True, size=9)
        ws.cell(row=r + i // 2, column=c + 1, value=v).font = Font(size=9)
    r += (len(pairs) + 1) // 2 + 1

    nums = ("On hire", "Returned", "Short", "Still on hire")
    head = ["#", "Material", "Unit", "On hire", "Returned", "Short", "Still on hire",
            "Reason / remarks"]
    for i, h in enumerate(head, 1):
        c = ws.cell(row=r, column=i, value=h)
        c.font = Font(bold=True, color="FFFFFF", size=9)
        c.fill = head_fill
        c.border = box
        c.alignment = Alignment(horizontal="right" if h in nums else "left", wrap_text=True)
    rows = _return_rows(note)
    for j, row in enumerate(rows, 1):
        remark = " / ".join(x for x in (row["reason"].title() if row["reason"] else "", row["notes"]) if x)
        bal = row["on_hire"] - row["returned"] - row["short"]
        for i, v in enumerate([row["no"], row["description"], row["unit"], row["on_hire"],
                               row["returned"], row["short"] or "", bal or "", remark], 1):
            c = ws.cell(row=r + j, column=i, value=v)
            c.border = box
            c.font = Font(size=9, bold=(i == 6 and bool(row["short"])),
                          color="C0392B" if (i == 6 and row["short"]) else "000000")
            c.alignment = Alignment(horizontal="right" if i in (4, 5, 6, 7) else "left",
                                    wrap_text=(i == 8))
    last = r + len(rows) + 1
    ws.cell(row=last, column=2, value="TOTAL").font = Font(bold=True, size=10)
    ws.cell(row=last, column=4, value=sum(x["on_hire"] for x in rows)).font = Font(bold=True, size=10)
    ws.cell(row=last, column=5, value=sum(x["returned"] for x in rows)).font = Font(bold=True, size=10)
    short_total = sum(x["short"] for x in rows)
    ws.cell(row=last, column=6, value=short_total or "").font = Font(bold=True, size=10, color="C0392B")
    bal_total = sum(x["on_hire"] - x["returned"] - x["short"] for x in rows)
    ws.cell(row=last, column=7, value=bal_total or "").font = Font(bold=True, size=10)
    for i in range(1, 9):
        ws.cell(row=last, column=i).fill = tot_fill
        ws.cell(row=last, column=i).border = box

    sr = last + 2
    if short_total:
        ws.merge_cells(start_row=sr, start_column=1, end_row=sr, end_column=8)
        ws.cell(row=sr, column=1,
                value=f"{_n(short_total)} item(s) recorded as not returned. "
                      "Signing below confirms this quantity as agreed by both parties.")
        ws.cell(row=sr, column=1).font = Font(bold=True, size=9, color="C0392B")
        sr += 2
    if bal_total:
        ws.merge_cells(start_row=sr, start_column=1, end_row=sr, end_column=8)
        ws.cell(row=sr, column=1,
                value=f"{_n(bal_total)} item(s) remain on hire and are not part of this return.")
        ws.cell(row=sr, column=1).font = Font(size=9)
        sr += 2
    ws.cell(row=sr, column=1, value="For Infinia Contracting L.L.C").font = Font(bold=True, size=9)
    ws.cell(row=sr, column=5, value=f"For {note.get('supplier') or 'the supplier'}").font = Font(bold=True, size=9)
    ws.cell(row=sr + 3, column=1, value="Name, signature & date").font = Font(size=9)
    ws.cell(row=sr + 3, column=5, value="Name, signature & stamp").font = Font(size=9)
    ws.cell(row=sr + 4, column=5, value="Date: ______________").font = Font(size=9)

    for col, w in zip("ABCDEFGH", (5, 34, 8, 10, 10, 9, 11, 28)):
        ws.column_dimensions[col].width = w
    ws.print_area = f"A1:H{sr + 5}"
    print_ready(ws, "portrait", title="Material Return Note")
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf

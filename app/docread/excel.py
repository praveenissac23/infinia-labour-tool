"""Excel into the layout model: the cells as Excel holds them - its own numbers (cached values), the formula behind
each, the number format (brackets = minus, % = a percentage), merged cells as one cell spanning its columns.
Hidden sheets, rows and columns are left out (they are not on the printed bill).

.xls (Excel 97-2003) is read with xlrd; if xlrd cannot, it is converted with LibreOffice (as est_bills_engine does).
"""
import io
import os
import re
import subprocess
import tempfile
from datetime import date, datetime

from .model import Cell, Doc, Region, Row
from .numparse import excel_date

try:
    from openpyxl.utils import get_column_letter
except Exception:          # pragma: no cover
    def get_column_letter(n):
        s = ""
        while n:
            n, r = divmod(n - 1, 26)
            s = chr(65 + r) + s
        return s


def display(v, fmt=""):
    """The value as Excel would show it - enough for reading: 1,234.50 / (1,234.50) / 12.50% / 06/10/2026."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, datetime):
        return v.strftime("%d/%m/%Y") if not (v.hour or v.minute) else v.strftime("%d/%m/%Y %H:%M")
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, (int, float)):
        f = (fmt or "").lower()
        if "%" in f:
            return f"{v * 100:.2f}%"
        if re.search(r"[dmy]{2}", f) and "#" not in f and excel_date(v):
            return excel_date(v).strftime("%d/%m/%Y")
        whole = float(v).is_integer()
        if whole and f in ("", "general", "0", "@") and abs(v) < 10000:
            return str(int(v))
        s = f"{abs(int(v)):,}" if whole and ".0" not in f else f"{abs(v):,.2f}"
        if v < 0:
            s = f"({s})" if "(" in f else "-" + s
        return s
    return re.sub(r"[ \t\r\n]+", " ", str(v)).strip()


# ---- a small formula evaluator: for cells with a formula but no saved value (a file saved by a program, not Excel)

_REF = re.compile(r"(?:'([^']+)'|([A-Za-z0-9_]+))?!?\$?([A-Z]{1,3})\$?(\d+)")


def _col_num(letters):
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


class _Eval:
    def __init__(self, values, formulas):
        self.v, self.f, self.busy = values, formulas, set()

    def cell(self, sheet, col, row):
        key = (sheet, col, row)
        x = self.v.get(key)
        if x is not None or key not in self.f:
            return x
        if key in self.busy:
            return None
        self.busy.add(key)
        try:
            x = self.formula(sheet, self.f[key])
        finally:
            self.busy.discard(key)
        if x is not None:
            self.v[key] = x
        return x

    def rng(self, sheet, a, b):
        sa, ca, ra = a
        sb, cb, rb = b
        out = []
        for c in range(min(ca, cb), max(ca, cb) + 1):
            for r in range(min(ra, rb), max(ra, rb) + 1):
                x = self.cell(sa or sheet, c, r)
                if isinstance(x, (int, float)) and not isinstance(x, bool):
                    out.append(float(x))
        return out

    def formula(self, sheet, f):
        if not isinstance(f, str) or not f.startswith("="):
            return None
        expr = f[1:]
        ref = r"(?:'[^']+'!|[A-Za-z0-9_]+!)?\$?[A-Z]{1,3}\$?\d+"

        def parse_ref(t):
            m = re.match(r"(?:'([^']+)'!|([A-Za-z0-9_]+)!)?\$?([A-Z]{1,3})\$?(\d+)", t)
            sh = m.group(1) or m.group(2)
            return (sh, _col_num(m.group(3)), int(m.group(4)))

        def fn(m):
            name, args = m.group(1).upper(), m.group(2)
            vals = []
            for part in args.split(","):
                part = part.strip()
                if ":" in part:
                    a, b = part.split(":")
                    vals += self.rng(sheet, parse_ref(a), parse_ref(b if "!" in b else (a.split("!")[0] + "!" + b if "!" in a else b)))
                elif re.fullmatch(ref, part):
                    x = self.cell(parse_ref(part)[0] or sheet, *parse_ref(part)[1:])
                    if isinstance(x, (int, float)):
                        vals.append(float(x))
                else:
                    try:
                        vals.append(float(eval(part, {"__builtins__": {}}, {})))   # noqa: S307 - digits and + - * / only (checked below)
                    except Exception:
                        return "0"
            if name == "SUM":
                return repr(sum(vals))
            if name == "ROUND" and vals:
                return repr(round(vals[0], int(vals[1]) if len(vals) > 1 else 0))
            if name == "ABS" and vals:
                return repr(abs(vals[0]))
            if name in ("MAX", "MIN") and vals:
                return repr(max(vals) if name == "MAX" else min(vals))
            return "0"
        for _ in range(4):
            new = re.sub(r"\b(SUM|ROUND|ABS|MAX|MIN)\(([^()]*)\)", fn, expr, flags=re.I)
            if new == expr:
                break
            expr = new

        def rf(m):
            sh, c, r = parse_ref(m.group(0))
            x = self.cell(sh or sheet, c, r)
            return repr(float(x)) if isinstance(x, (int, float)) and not isinstance(x, bool) else "0"
        expr = re.sub(ref, rf, expr)
        if not re.fullmatch(r"[\d\s.+\-*/()eE]+", expr):
            return None
        try:
            return float(eval(expr, {"__builtins__": {}}, {}))  # noqa: S307 - arithmetic on numbers only
        except Exception:
            return None


def read_xlsx(data, name=""):
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    try:
        wf = openpyxl.load_workbook(io.BytesIO(data), data_only=False, read_only=True)
    except Exception:
        wf = None
    formulas = {}
    values = {}
    if wf is not None:
        for ws in wf.worksheets:
            try:
                for row in ws.iter_rows():
                    for c in row:
                        if isinstance(c.value, str) and c.value.startswith("="):
                            formulas[(ws.title, c.column, c.row)] = c.value
            except Exception:
                pass
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if c.value is not None:
                    values[(ws.title, c.column, c.row)] = c.value
    ev = _Eval(values, formulas)
    regions = []
    for si, ws in enumerate(wb.worksheets):
        if ws.sheet_state != "visible":
            continue
        hidden_rows = {r for r, d in ws.row_dimensions.items() if d.hidden}
        hidden_cols = set()
        for k, d in ws.column_dimensions.items():
            if d.hidden:
                lo, hi = (d.min or _col_num(k)), (d.max or _col_num(k))
                hidden_cols.update(range(lo, hi + 1))
        merged = {}
        inside = set()
        for rng in ws.merged_cells.ranges:
            merged[(rng.min_row, rng.min_col)] = (rng.max_row, rng.max_col)
            for r in range(rng.min_row, rng.max_row + 1):
                for c in range(rng.min_col, rng.max_col + 1):
                    if (r, c) != (rng.min_row, rng.min_col):
                        inside.add((r, c))
        rows = {}
        for row in ws.iter_rows():
            for c in row:
                if c.row in hidden_rows or c.column in hidden_cols or (c.row, c.column) in inside:
                    continue
                v = c.value
                f = formulas.get((ws.title, c.column, c.row), "")
                if v is None and f:
                    v = ev.cell(ws.title, c.column, c.row)
                if v is None or (isinstance(v, str) and not v.strip()):
                    continue
                fmt = c.number_format or ""
                r1, c1 = merged.get((c.row, c.column), (c.row, c.column))
                num = float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
                cell = Cell(text=display(v, fmt), x0=c.column - 1, x1=c1, y0=c.row - 1, y1=r1, page=len(regions) + 1,
                            src=f"{ws.title}!{get_column_letter(c.column)}{c.row}", num=num, fmt=fmt, formula=f, col=c.column,
                            is_date=isinstance(v, (date, datetime)))
                rows.setdefault(c.row, []).append(cell)
        out = []
        for r in sorted(rows):
            cs = sorted(rows[r], key=lambda x: x.x0)
            out.append(Row(cells=cs, page=len(regions) + 1, y=r))
        regions.append(Region(name=ws.title, page=len(regions) + 1, rows=out, kind="sheet"))
    return Doc(regions=regions, kind="xlsx", name=name)


def read_xls(data, name=""):
    try:
        import xlrd
        bk = xlrd.open_workbook(file_contents=data, formatting_info=True)
    except Exception:
        return read_xlsx(xls_to_xlsx(data), name)
    regions = []
    for sh in bk.sheets():
        if sh.visibility:
            continue
        hidden_rows = {r for r, ri in sh.rowinfo_map.items() if ri.hidden}
        hidden_cols = {c for c, ci in sh.colinfo_map.items() if ci.hidden}
        merged, inside = {}, set()
        for r0, r1, c0, c1 in sh.merged_cells:
            merged[(r0, c0)] = (r1, c1)
            for r in range(r0, r1):
                for c in range(c0, c1):
                    if (r, c) != (r0, c0):
                        inside.add((r, c))
        out = []
        page = len(regions) + 1
        for r in range(sh.nrows):
            if r in hidden_rows:
                continue
            cells = []
            for c in range(sh.ncols):
                if c in hidden_cols or (r, c) in inside:
                    continue
                x = sh.cell(r, c)
                if x.ctype in (0, 6) or (x.ctype == 1 and not str(x.value).strip()):
                    continue
                fmt = ""
                try:
                    fmt = bk.format_map[bk.xf_list[x.xf_index].format_key].format_str
                except Exception:
                    pass
                v = x.value
                is_date = False
                if x.ctype == 3:
                    try:
                        v = xlrd.xldate.xldate_as_datetime(x.value, bk.datemode)
                        is_date = True
                    except Exception:
                        pass
                elif x.ctype == 4:
                    v = bool(v)
                elif x.ctype == 5:
                    continue
                r1, c1 = merged.get((r, c), (r + 1, c + 1))
                num = float(x.value) if x.ctype == 2 else None
                cells.append(Cell(text=display(v, fmt), x0=c, x1=c1, y0=r, y1=r1, page=page,
                                  src=f"{sh.name}!{get_column_letter(c + 1)}{r + 1}", num=num, fmt=fmt, col=c + 1, is_date=is_date))
            if cells:
                out.append(Row(cells=cells, page=page, y=r + 1))
        regions.append(Region(name=sh.name, page=page, rows=out, kind="sheet"))
    return Doc(regions=regions, kind="xls", name=name)


def xls_to_xlsx(data):
    """LibreOffice converts an old .xls (the same way est_bills_engine.xls_to_xlsx does)."""
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "in.xls")
        with open(src, "wb") as fh:
            fh.write(data)
        subprocess.run(["soffice", "--headless", "--norestore", f"-env:UserInstallation=file://{d}/lo", "--convert-to", "xlsx",
                        "--outdir", d, src], capture_output=True, timeout=120)
        with open(os.path.join(d, "in.xlsx"), "rb") as fh:
            return fh.read()

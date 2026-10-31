"""Figures, percentages and dates out of cell text - including what a scan does to them.

  "AED 1,234.50"  "Dhs. 1,234.50"  "1,234.50 AED"  "(1,234.50)"  "-1,234.50"  "1,234.50-"  "1 234 567.89" (scan)
  "1.234.567,89" (European)  "12.5%"  "O"/"o" read for 0, "l"/"I"/"|" for 1, "S" for 5 inside a figure (scan only)

Dates, years, phone numbers, TRNs (15 digits) and item numbers are not money.
"""
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


@dataclass
class Num:
    value: float          # signed
    text: str
    start: int            # span in the cell text
    end: int
    pct: bool = False     # a percentage (value is in %, e.g. 10.0 for 10%)
    neg: bool = False
    money_like: bool = True   # has a thousands comma, decimals or a currency mark (not a bare small integer)
    fixed: bool = False   # letters read as digits were put right (a scan)
    raw: bool = False     # Excel's own number


CUR = r"(?:AED|A\.E\.D\.?|Dhs?\.?|DHS|Dirhams?|د\.إ)"
# a figure: optional sign / bracket / currency, digits with separators, optional decimals, optional trailing minus
def _num_rx(sep):
    return re.compile(
        r"(?P<pre>\(\s*|-\s*|−\s*|–\s*)?(?P<cur1>" + CUR + r"\s*)?(?P<pre2>\(\s*|-\s*)?"
        r"(?P<n>\d{1,3}(?:" + sep + r"\d{3})+(?:\.\d+)?|\d{1,3}(?:\.\d{3})+,\d{1,2}|\d+(?:\.\d+)?|\.\d+)"
        r"(?P<post>\s*\)|-(?![\d.]))?(?P<cur2>\s*" + CUR + r")?(?P<pct>\s*%)?", re.I)


NUM_RX = _num_rx(",")              # typed text: only commas group thousands
NUM_RX_OCR = _num_rx(r"(?:,|\s)")  # a scan: "1 234 567.89" too
DATE_RX = re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b|\b\d{4}-\d{1,2}-\d{1,2}\b|\b\d{1,2}[-\s][A-Za-z]{3,9}[-\s,]+\d{2,4}\b|"
                     r"\b[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4}\b")
OCR_MAP = str.maketrans({"O": "0", "o": "0", "D": "0", "Q": "0", "l": "1", "I": "1", "|": "1", "i": "1", "!": "1",
                         "S": "5", "s": "5", "B": "8", "Z": "2", "z": "2", "G": "6", "g": "9", "q": "9"})


def ocr_fix(text):
    """Inside a token that is mostly digits, letters a scan confuses with digits are put back: '1O,5OO.0O' -> '10,500.00'.
    Only tokens with at least two real digits and digit-like letters, never words."""
    def fix(m):
        t = m.group(0)
        digits = sum(ch.isdigit() for ch in t)
        if digits < 2 or not any(ch.isalpha() or ch == "|" for ch in t):
            return t
        u = t.translate(OCR_MAP)
        # only when the result reads as a money figure: 10,500.00 / 35471.07 / 1,234
        if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+\.\d{2}|\d{1,3}(?:,\d{3})+", u.rstrip(".,")):
            return u
        return t
    return re.sub(r"(?<![A-Za-z])[\dOoIlSB|][\dOoIlSB|,.]{2,}(?![A-Za-z]{2})", fix, text)


def _to_float(n):
    """'1,234,567.89' / '1 234 567.89' / '1.234.567,89' -> float."""
    s = n.strip()
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+,\d{1,2}", s):        # European
        return float(s.replace(".", "").replace(",", "."))
    s = re.sub(r"[,\s]", "", s)
    return float(s)


def numbers(text, ocr=False):
    """Every number in a cell's text, with its sign, whether it is a percentage, and where it is."""
    t = text or ""
    fixed = False
    if ocr:
        t2 = ocr_fix(t)
        fixed = t2 != t
        t = t2
        # a scan reads 1,234.50 as "1,234,50" or "1.234.50": the last separator with two digits after it is the decimal point
        t = re.sub(r"(\d{1,3}(?:[,.]\d{3})+)[,.](\d{2})(?!\d)", lambda m: m.group(1).replace(".", ",") + "." + m.group(2), t)
    blocked = []
    for m in DATE_RX.finditer(t):
        blocked.append((m.start(), m.end()))
    out = []
    for m in (NUM_RX_OCR if ocr else NUM_RX).finditer(t):
        if any(a <= m.start("n") < b for a, b in blocked):
            continue
        n = m.group("n")
        # a space-grouped figure is only one figure when the groups are three digits each ("1 234 567.89")
        try:
            v = _to_float(n)
        except ValueError:
            continue
        pre = (m.group("pre") or "") + (m.group("pre2") or "")
        post = m.group("post") or ""
        neg = ("(" in pre and ")" in post) or pre.strip() in ("-", "−", "–") or post.strip() == "-" or \
              ("(" in pre and m.group("cur1") is not None)
        pct = bool(m.group("pct"))
        cur = bool(m.group("cur1") or m.group("cur2"))
        digits = re.sub(r"\D", "", n)
        money_like = cur or "," in n or "." in n or (" " in n.strip()) or len(digits) >= 4
        # a lone 4-digit year, a 15-digit TRN, a phone number are not money
        if not cur and not pct and "." not in n and "," not in n:
            if len(digits) == 4 and 1990 <= int(digits) <= 2100:
                money_like = False
            if len(digits) >= 9:
                continue
        if len(digits) > 13:
            continue
        out.append(Num(-v if neg else v, m.group(0), m.start(), m.end(), pct=pct, neg=neg, money_like=money_like, fixed=fixed))
    return out


def a_date(s, dayfirst=True):
    """22 October 2026 / 22nd day of October, 2026 / October 22, 2026 / 22/10/2026 / 22.10.2026 / 2026-10-22 / 22-Oct-26
    -> date, else None. Day first (the UAE way)."""
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, date):
        return s
    s = (s or "").replace(",", " ")
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s*(?:day\s+of\s+)?[-\s]?([A-Za-z]{3,9})\.?[-\s]+(\d{2,4})\b", s)
    if m and m.group(2)[:3].lower() in MONTHS:
        y = int(m.group(3))
        y = y + 2000 if y < 100 else y
        try:
            return date(y, MONTHS[m.group(2)[:3].lower()], int(m.group(1)))
        except ValueError:
            pass
    m = re.search(r"([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?\s+(\d{4})", s)
    if m and m.group(1)[:3].lower() in MONTHS:
        try:
            return date(int(m.group(3)), MONTHS[m.group(1)[:3].lower()], int(m.group(2)))
        except ValueError:
            pass
    m = re.search(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b", s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = y + 2000 if y < 100 else y
        d, mo = (a, b) if dayfirst else (b, a)
        if mo > 12 and d <= 12:
            d, mo = mo, d
        try:
            return date(y, mo, d)
        except ValueError:
            pass
    return None


def excel_date(v):
    """An Excel serial number (46301) -> date."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if 30000 < f < 80000:
        return date(1899, 12, 30) + timedelta(days=int(f))
    return None


def money_text(v):
    return f"{v:,.2f}"


def digit_edit_close(a, b):
    """True when two figures differ by what a scan does: one digit read wrong, one dropped or one added
    (compared on their digits, decimals included)."""
    sa, sb = f"{abs(a):.2f}".replace(".", ""), f"{abs(b):.2f}".replace(".", "")
    if sa == sb:
        return True
    if len(sa) == len(sb):
        return sum(x != y for x, y in zip(sa, sb)) == 1
    if abs(len(sa) - len(sb)) == 1:
        s, l = (sa, sb) if len(sa) < len(sb) else (sb, sa)
        return any(l[:i] + l[i + 1:] == s for i in range(len(l)))
    return False

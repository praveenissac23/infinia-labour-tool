"""Dates inside stored text, shown as dd/mm/yyyy.

Some text was saved before every date read dd/mm/yyyy - activity-log lines
("Passport -> 2027-07-12"), vacation notes ("Vacation 5 Oct - 18 Oct"),
absence notes ("Sick 9 Sep"), store notes ("Opening count 01-Sep-2026").
The rows stay as they were; dmy_text() only changes how they read on the
way out:

    2026-10-05 / 2026-10-05T14:03:22      -> 05/10/2026 / 05/10/2026 14:03
    01-Sep-2026, 28 Oct 2026, Oct 5, 2026 -> 01/09/2026, 28/10/2026, 05/10/2026
    30 Oct, 2:05 PM                       -> 30/10/2026 14:05
    5-18 Oct                              -> 05/10/2026 - 18/10/2026
    9 Sep (no year)                       -> 09/09/2026, the year nearest `ref`

A date with no year is only turned when there is something to take the year
from - `ref` (the date the row is about) or a full date in the same text;
otherwise it is left as written. Month-only words ("October 2026"), file
names (report_2026-10-05.xlsx) and anything that is not a real date are
left alone.
"""
import re
from datetime import date, datetime

_MON = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
_M = (r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?"
      r"|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?")
_TIME = r"(?:,?\s+(\d{1,2}):(\d{2})(?::\d{2})?\s*([AaPp][Mm])?)?"

_ISO = re.compile(r"(?<![\w/.:-])(\d{4})-(\d{2})-(\d{2})"
                  r"(?:[T ](\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?(?![\w-])")
# 5-18 Oct [2026]  (a run of days in one month)
_RUN = re.compile(r"(?<![\w/-])(\d{1,2})\s*-\s*(\d{1,2})[ -]" + _M + r"(?:[ ,]+(\d{4}))?(?![\w/-])", re.I)
# 01-Sep-2026, 28 Oct 2026, 5 Oct, 30 Oct, 2:05 PM
_DMON = re.compile(r"(?<![\w/-])(\d{1,2})(?:st|nd|rd|th)?[ -]" + _M + r"(?:[ ,-]+(\d{4})|-(\d{2})(?![\d:]))?"
                   + _TIME + r"(?![\w/])", re.I)
# Oct 5, 2026 / October 5 2026 (a year is required for this order)
_MOND = re.compile(r"(?<![\w/-])" + _M + r" (\d{1,2})(?:st|nd|rd|th)?,? (\d{4})" + _TIME + r"(?![\w/])", re.I)


def _mon(word):
    return _MON.get(word[:3].lower())


def _mk(y, m, d):
    try:
        return date(int(y), int(m), int(d))
    except (TypeError, ValueError):
        return None


def _year(y):
    if not y:
        return None
    y = int(y)
    return y + 2000 if y < 100 else y


def _guess(m, d, ref):
    """The day/month with the year that puts it nearest `ref`."""
    best = None
    for y in (ref.year - 1, ref.year, ref.year + 1):
        x = _mk(y, m, d)
        if x and (best is None or abs((x - ref).days) < abs((best - ref).days)):
            best = x
    return best


def _hm(h, mi, ap):
    if h is None:
        return ""
    h, mi = int(h), int(mi)
    if ap:
        h = h % 12 + (12 if ap.lower() == "pm" else 0)
    if h > 23 or mi > 59:
        return None
    return f" {h:02d}:{mi:02d}"


def _as_ref(ref):
    if ref is None or ref == "":
        return None
    if isinstance(ref, datetime):
        return ref.date()
    if isinstance(ref, date):
        return ref
    s = str(ref).strip()
    for f in ("%Y-%m-%d", "%B %Y", "%b %Y"):
        try:
            return datetime.strptime(s[:10] if f == "%Y-%m-%d" else s, f).date()
        except ValueError:
            pass
    return None


def dmy_text(text, ref=None):
    """`text` with the dates in it written dd/mm/yyyy (see the module note)."""
    if not text or not isinstance(text, str) or not re.search(r"\d", text):
        return text
    ref = _as_ref(ref)

    def iso(m):
        d = _mk(m.group(1), m.group(2), m.group(3))
        if not d:
            return m.group(0)
        t = f" {m.group(4)}:{m.group(5)}" if m.group(4) else ""
        return f"{d:%d/%m/%Y}{t}"

    out = _ISO.sub(iso, text)

    def mond(m):
        mo = _mon(m.group(1))
        d, t = _mk(m.group(3), mo, m.group(2)), _hm(m.group(4), m.group(5), m.group(6))
        return f"{d:%d/%m/%Y}{t}" if d and t is not None else m.group(0)

    out = _MOND.sub(mond, out)

    # A date with no year takes it from `ref`, else from a full date in the same text.
    near = ref
    if near is None:
        full = re.search(r"\b(\d{2})/(\d{2})/(\d{4})\b", out)
        f2 = None if full else next((x for x in _DMON.finditer(out) if x.group(3)), None)
        if full:
            near = _mk(full.group(3), full.group(2), full.group(1))
        elif f2:
            near = _mk(f2.group(3), _mon(f2.group(2)), f2.group(1))

    def day(dd, mo, yy):
        if yy:
            return _mk(_year(yy), mo, dd)
        return _guess(mo, int(dd), near) if near else None

    def _plain_ok(word):
        # Without a year a month in small letters counts only on a row with a date of its own
        # ("Joined 12 oct" on a payroll line), and never "may" / "mar" ("500 may ...").
        return word[0].isupper() or (ref is not None and word.lower().rstrip(".") not in ("may", "mar", "march"))

    def run(m):
        if not m.group(4) and not _plain_ok(m.group(3)):
            return m.group(0)
        mo = _mon(m.group(3))
        a, b = day(m.group(1), mo, m.group(4)), day(m.group(2), mo, m.group(4))
        if not a or not b or b < a:
            return m.group(0)
        return f"{a:%d/%m/%Y} - {b:%d/%m/%Y}"

    out = _RUN.sub(run, out)

    def dmon(m):
        word, yy = m.group(2), m.group(3) or m.group(4)
        if not yy and not _plain_ok(word):
            return m.group(0)
        d, t = day(m.group(1), _mon(word), yy), _hm(m.group(5), m.group(6), m.group(7))
        if not d or t is None:
            return m.group(0)
        return f"{d:%d/%m/%Y}{t}"

    return _DMON.sub(dmon, out)

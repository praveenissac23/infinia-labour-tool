"""Label -> value pairs for the words on a document (bill no., dates, references, names): the value written after
the label in its own cell ("Date: 06/10/2026"), else the next cell on the right, else the cell just below it."""
import re

from .numparse import a_date

LABELISH = re.compile(r"^(date|measurement\s+date|project(\s+code)?|ipc\b|ipa\b|inv\.?|invoice|commencement|agreement|scope|client|"
                      r"issue\s+date|interim\s+bill|contractor|sub-?contractor|consultant|location|period|ref|subject|to\b|from\b|"
                      r"payment\s+certificate|certificate|bill\s+no|employer|trn)\b", re.I)


def _texts(row):
    return [c.text for c in row.cells]


def find_all(rows, pat):
    """(row, cell index, match) of each cell that STARTS with the label."""
    rx = re.compile(r"^\s*(?:" + pat + r")", re.I)
    for r in rows:
        for j, c in enumerate(r.cells):
            m = rx.match(c.text)
            if m:
                yield r, j, m


def value_after(rows, r, j, m, below=True):
    """(text, cell) written after a label."""
    cells = r.cells
    inline = cells[j].text[m.end():].strip(" :.-\t")
    if inline:
        return inline, cells[j]
    for c in cells[j + 1:j + 4]:
        x = c.text.strip()
        if not x or x in (":", "-"):
            continue
        x = x.lstrip(": ").strip()
        if not x or LABELISH.match(x):
            return "", None
        return x, c
    if below:
        # the cell just under the label (a form laid out label-over-value)
        lab = cells[j]
        idx = rows.index(r) if r in rows else -1
        for nr in rows[idx + 1: idx + 3]:
            if nr.page != r.page:
                break
            for c in nr.cells:
                ov = min(c.x1, lab.x1) - max(c.x0, lab.x0)
                if ov > 0 and c.text.strip() and not LABELISH.match(c.text):
                    return c.text.strip(), c
    return "", None


def text_field(rows, pat, maxlen=80, below=True):
    for r, j, m in find_all(rows, pat):
        v, c = value_after(rows, r, j, m, below)
        if v:
            return v[:maxlen], c
    return "", None


def date_field(rows, pat):
    for r, j, m in find_all(rows, pat):
        v, c = value_after(rows, r, j, m)
        d = a_date(v) if v else None
        if d and 1990 < d.year < 2100:
            return d.isoformat(), c
    return "", None


def seq_of(label):
    """A bill / certificate number from its label: the last number once the revision and a year are taken off -
    "VE207/IPA/03 R1" -> 3, "914-IPA-07" -> 7, "IPA 07/2026" -> 7, "IPC 12" -> 12, "2-R2" -> 2."""
    t = re.sub(r"[\s\-/(]*\b(R|Rev\.?|Revision)\s*\.?\s*\d+\s*\)?\s*$", "", label or "", flags=re.I)
    nums = [n for n in re.findall(r"\d+", t) if not (len(n) == 4 and 1990 <= int(n) <= 2100)]
    return int(nums[-1]) if nums else None


_ONES = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
                                     "seventeen eighteen nineteen".split())}
_TENS = {w: 10 * (i + 2) for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split())}
_TYPO = {"eigtheen": "eighteen", "eighten": "eighteen", "fourty": "forty", "ninty": "ninety", "thousands": "thousand", "hundreds": "hundred",
         "lakh": "lac", "lakhs": "lac", "lacs": "lac", "millions": "million"}


def words_amount(text):
    """'Eight Thousand Five Hundred Twenty-Two and Fifty Fils Only' -> 8522.50, or None."""
    toks = [_TYPO.get(t, t) for t in re.findall(r"[a-z]+", (text or "").lower())]
    NUMW = set(_ONES) | set(_TENS) | {"hundred", "thousand", "lac", "million"}

    def num(ws):
        total = cur = 0
        for w in ws:
            if w in _ONES:
                cur += _ONES[w]
            elif w in _TENS:
                cur += _TENS[w]
            elif w == "hundred":
                cur = (cur or 1) * 100
            elif w == "thousand":
                total += (cur or 1) * 1000
                cur = 0
            elif w == "lac":
                total += (cur or 1) * 100000
                cur = 0
            elif w == "million":
                total += (cur or 1) * 1000000
                cur = 0
        return total + cur
    runs, cur = [], []
    for k, t in enumerate(toks):
        if t in NUMW or (t == "and" and cur and k + 1 < len(toks) and toks[k + 1] in NUMW):
            cur.append((k, t))
        else:
            if cur:
                runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    runs = [r for r in runs if any(t in NUMW for _, t in r)]
    if not runs:
        return None

    def after(r):
        return toks[r[-1][0] + 1] if r[-1][0] + 1 < len(toks) else ""
    big = [r for r in runs if {"thousand", "hundred", "lac", "million"} & {t for _, t in r} or after(r) in ("dirham", "dirhams", "only", "aed")]
    if not big:
        return None
    dh = max(big, key=lambda r: num([t for _, t in r if t != "and"]))
    ws = [t for _, t in dh]
    fils = 0
    if after(dh) == "fils" and "and" in ws:
        cut = len(ws) - 1 - ws[::-1].index("and")
        fils = num([t for t in ws[cut + 1:] if t != "and"])
        ws = ws[:cut]
    else:
        nxt = [r for r in runs if r[0][0] > dh[-1][0] and after(r) == "fils"]
        if nxt:
            fils = num([t for _, t in nxt[0] if t != "and"])
    v = num([t for t in ws if t != "and"])
    if not v or fils >= 100:
        return None
    return round(v + fils / 100, 2)

"""The words offices use - row labels and column headings mapped to what they mean.

Every pattern runs on normalised text (lower case, punctuation as spaces, common misspellings and scan errors put
right), and gives a score: a label can mean two things ("Total value of work executed" is the work or the work plus
variations) and the bill's own arithmetic decides between them later.
"""
import difflib
import re
from functools import lru_cache

# words a label is built from: a misspelt or misread one is put right when it is close to one of these
KEYWORDS = ["retention", "advance", "recovery", "previous", "previously", "cumulative", "variation", "variations", "payable",
            "certified", "certificate", "payment", "deduction", "deductions", "release", "released", "material", "materials",
            "manpower", "equipment", "amount", "contract", "executed", "valuation", "progressive", "interim", "application",
            "submitted", "submission", "approved", "accepted", "absorbed", "revised", "description", "remarks", "status",
            "current", "present", "period", "value", "total", "gross", "net", "work", "works", "done", "date", "less", "add",
            "authorities", "authority", "mobilization", "mobilisation", "charges", "contra", "omission", "addition"]
TYPO = {"retension": "retention", "retentions": "retention", "recovry": "recovery", "recoverd": "recovered", "prev": "previous",
        "previuos": "previous", "privious": "previous", "cummulative": "cumulative", "cumm": "cumulative", "cum": "cumulative",
        "cumulatve": "cumulative", "todate": "to date", "uptodate": "up to date", "upto": "up to", "amt": "amount",
        "vo": "variation", "vos": "variations", "v o": "variation", "adv": "advance", "rec": "recovery", "ret": "retention",
        "cert": "certified", "certd": "certified", "qty": "quantity", "desc": "description", "w d": "work done",
        "mobilisation": "mobilization", "valuation": "valuation", "deducted": "deduction", "inclusive": "including",
        "incl": "including", "excl": "excluding", "exclusive": "excluding", "inc": "including", "exc": "excluding",
        "tot": "total", "pymt": "payment", "pmt": "payment", "paymt": "payment", "dhs": "aed", "dh": "aed"}


@lru_cache(maxsize=20000)
def _fix_word(w):
    close = difflib.get_close_matches(w, KEYWORDS, n=1, cutoff=0.84)
    return close[0] if close else w


@lru_cache(maxsize=20000)
def norm(text):
    t = (text or "").lower()
    t = t.replace("&", " and ").replace("%", " % ").replace("+", " + ")
    t = re.sub(r"[^a-z0-9%+؀-ۿ]+", " ", t)
    words = []
    for w in t.split():
        w = TYPO.get(w, w)
        if len(w) >= 6 and w.isalpha() and w not in KEYWORDS:
            w = _fix_word(w)
        words.append(w)
    return " " + " ".join(words) + " "


def _c(p):
    return re.compile(p)


# ---- rows of a payment summary (a bill, an IPA, a payment certificate) ------------------------------------
# concept: [(pattern, score, avoid-pattern or None, role hint or None)]
ROW = {
    "work": [
        (r" (value|amount) of (the )?(original )?(contract )?works? (done|executed|completed|carried out|performed)", 0.95, r" variation| \( ?a ?\+ ?b", None),
        (r" total (value|amount) of (the )?(original )?(contract )?works? (done|executed|completed|carried out|performed)", 0.78, r" variation| \( ?a ?\+ ?b", None),
        (r" works? (done|executed|completed) (to date|up to date|cumulative)", 0.9, r" variation", None),
        (r" gross (value|amount|valuation) of (the )?works?", 0.85, None, None),
        (r" (total )?works? (done|executed|completed)", 0.75, r" variation| previous| this period", None),
        (r" (original |main )?contract works?", 0.7, None, None),
        (r" measured works?", 0.75, None, None),
        (r" valuation of works?| (gross )?valuation", 0.6, None, None),
        (r" progress (value|to date)", 0.6, None, None),
        (r" (boq|contract) items?", 0.5, None, None),
    ],
    "var": [
        (r" (value of )?(approved |accepted )?variations?( orders?)?( executed| approved| done)?", 0.85, r" excluding variation| without variation| including variation| incl variation| work done and variation| total value of works? executed", None),
        (r" change orders?", 0.8, None, None),
        (r" additional works?| extra works?", 0.55, None, None),
    ],
    "gross": [
        (r" total value of works? executed", 0.8, None, None),
        (r" gross (value|amount|total|valuation)( to date)?( certified)?", 0.8, r" of (the )?works?", None),
        (r" total (gross )?(value )?(of )?works? (done |executed )?(including|and|plus|with) (variation|vo)", 0.95, None, None),
        (r" total (works? )?(executed|done) ?\( ?a ?\+ ?b ?\)| total \( ?a ?\+ ?b ?\)| \( ?a ?\+ ?b ?\)", 0.9, None, None),
        (r" sub ?total", 0.45, r" deduction", None),
        (r" total (amount|value) (to date|certified to date)", 0.5, None, None),
    ],
    "mos": [(r" materials? (delivered )?(on|at) site| mos ", 0.9, None, None)],
    "ret": [
        (r" retention( money| amount| held| deducted| @| at)?", 0.9, r" release| released| refund| return", None),
        (r" retained", 0.6, r" release", None),
    ],
    "rel": [(r" retention (money )?(release|released|refund|returned)| release of retention| released retention", 0.95, None, None)],
    "adv": [
        (r" (recovery|recoupment|repayment) (of )?(the )?(mobilization )?advance", 0.95, None, None),
        (r" advance (payment )?(recovery|recovered|recoupment|repayment|deduction|adjustment)", 0.95, None, None),
        (r" less (mobilization )?advance", 0.75, None, None),
        (r" advance rec", 0.85, None, None),
    ],
    "advpay": [
        (r" (mobilization )?advance (payment|paid|amount)?", 0.6, r" recover| recoup| repay| deduct| adjust| less advance| rec ", None),
    ],
    "contra": [
        (r" contra (charges?|deductions?)| back ?charges?| set ?off| debit notes?", 0.9, None, None),
        (r" (other |misc\w* )?deductions?", 0.7, r" total deduction| retention| advance", None),
        (r" materials? (supplied|issued|provided)( by (main )?contractor| by infinia)?", 0.85, None, None),
        (r" manpower (supplied|provided)", 0.85, None, None),
        (r" plant (and )?equipment (supplied|provided)", 0.85, None, None),
        (r" penalt(y|ies)| liquidated damages| \bld\b| delay damages", 0.85, None, None),
        (r" less ([a-z]+ ){0,3}charges?", 0.7, None, None),
    ],
    "prev": [
        (r" (less )?(total )?previous(ly)? (progressive )?(payments?|certified|paid|certificates?|bills?|ipas?|ipcs?|pcs?|applications?|amounts? (paid|certified)|net)", 0.95, None, None),
        (r" (less )?(amount|total) (previously )?(paid|certified) (up to|till|until) (last|previous)", 0.9, None, None),
        (r" less previous", 0.85, None, None),
        (r" previous(ly)? (certified|paid)", 0.9, None, None),
        (r" (amount )?paid to date", 0.6, None, None),
    ],
    "net": [
        (r" net (amount|value|sum)?( certified)?( due| payable)?( for (this|current) (period|month|certificate|payment))", 0.9, None, "t"),
        (r" net (amount|value)? ?(certified )?(to date|cumulative)", 0.85, None, "c"),
        (r" (total )?(amount|value) certified (to date|cumulative)", 0.75, None, "c"),
        (r" (net )?(amount|sum) (due|payable)( for (this|current) (period|bill|certificate))? (excluding|before|without) (vat|tax)", 0.95, None, "t"),
        (r" net (amount )?(due|payable)", 0.9, r" including vat| inc vat", "t"),
        (r" net (amount|value|certified|valuation)", 0.75, r" including vat", None),
        (r" (amount|value) (certified|due) (for|this) (period|month|certificate|bill)", 0.8, r" including vat", "t"),
        (r" (total )?amount (excluding|before|without|exclusive of) (vat|tax)", 0.8, None, "t"),
        (r" amount (due|payable)", 0.45, r" including vat| total amount", "t"),
        (r" total certified", 0.6, None, "c"),
        (r" (total )?(this|current) (period|bill|certificate|payment|claim)", 0.55, None, "t"),
    ],
    "vat": [
        (r" (add )?(\d+ % )?(vat|value added tax)( @ ?\d+ ?%| at \d+ ?%)?( \d+ %)?", 0.9, r" excluding vat| before vat| without vat| including vat| trn| registration| exclusive of vat|amount excluding|total amount including", None),
        (r" (\d+ % )?tax( payment)?( @ ?\d+ ?%)?", 0.6, r" trn| registration| excluding| before| invoice", None),
    ],
    "total": [
        (r" total (amount )?(due|payable)( for payment)?( including vat)?", 0.9, r" excluding vat| before vat| net amount due", None),
        (r" amount (due|payable) for payment", 0.9, None, None),
        (r" (net |total )?(amount )?(due|payable)? ?(including|with|plus) (vat|tax)", 0.9, r" excluding", None),
        (r" (total |net )?amount payable", 0.75, r" excluding| before vat", None),
        (r" grand total", 0.6, None, None),
        (r" total (payable|due)", 0.85, None, None),
        (r" (amount|sum) (certified )?for payment", 0.8, None, None),
        (r" (total )?amount (due|payable)", 0.5, r" excluding| before vat", None),
    ],
    "auth": [(r" (payments? (paid )?to |add )?authorit(y|ies)( fees?| payments?)?| dewa fees| municipality fees", 0.9, None, None)],
    "contract": [(r" (original |revised |total |adjusted )?(sub )?contract (value|sum|amount|price)", 0.9, r" work| variation", None)],
    "extra": [(r"^ (add|less)\b", 0.5, None, None)],
}
ROW = {k: [(_c(p), s, _c(a) if a else None, h) for p, s, a, h in v] for k, v in ROW.items()}

# what each concept is: money added (+) or taken off (-) in the bill's sum; how its figure is read (magnitude)
DEDUCT = {"ret", "adv", "contra", "prev"}
ADD = {"work", "var", "mos", "rel", "advpay", "vat", "auth"}

# ---- column headings ------------------------------------------------------------------------------------
COL = {
    "p": [(r" previous( certified| amount| value| claim| bill| paid| total| cumulative)?", 0.95), (r" up to (last|previous)", 0.95),
          (r" last (cumulative|certificate|bill|ipa|month)", 0.9), (r" previously (paid|certified)", 0.95), (r" prior", 0.7),
          (r" opening", 0.5), (r" السابق", 0.9)],
    "t": [(r" this (period|bill|month|certificate|ipa|ipc|pc|claim|payment|application|valuation)", 0.95), (r" current( period| bill| month| claim| certificate)?", 0.9),
          (r" present( bill| period)?", 0.9), (r" during (this|the) (period|month)", 0.9), (r" for the (period|month)", 0.7), (r" الحالي", 0.9)],
    "c": [(r" cumulative( to date| total| value)?", 0.95), (r" (up )?to date", 0.9), (r" gross certified", 0.85), (r" total to date", 0.95),
          (r" till date", 0.9), (r" total( value| amount| work done)? $", 0.55), (r" التراكمي| الإجمالي", 0.9)],
    "pct": [(r" %| percent(age)?| progress", 0.9)],
    "amount": [(r" amount( aed)?| value( aed)?| aed| dhs| sum", 0.6), (r" المبلغ| القيمة", 0.6)],
    "contract": [(r" (contract|boq|original|budget(ed)?|tender) (value|amount|sum)?", 0.8)],
    "qty": [(r" (quantity|qty|nos)", 0.9)], "rate": [(r" (unit )?rate|unit price", 0.9)], "unit": [(r"^ (unit|uom)\s*$", 0.9)],
    "desc": [(r" description|particulars|details|item description|scope| البيان| الوصف", 0.9)],
    "claimed": [(r" claimed|contractor('?s)? (claim|application)|submitted|applied", 0.85)],
    "certified": [(r" certified|approved|consultant('?s)?|engineer('?s)?", 0.6)],
    "remarks": [(r" remarks?|notes?|comments?", 0.9)],
}
COL = {k: [(_c(p), s) for p, s in v] for k, v in COL.items()}


@lru_cache(maxsize=20000)
def row_concepts(label):
    """[(concept, score, role hint)] a row label may mean, best first."""
    n = norm(label)
    out = {}
    for k, pats in ROW.items():
        for rx, s, avoid, hint in pats:
            if rx.search(n) and not (avoid and avoid.search(n)):
                if k not in out or s > out[k][0]:
                    out[k] = (s, hint)
    # a label that is mostly something else ("Retention release" also matches retention): the stronger, more
    # specific concept wins
    if "rel" in out and "ret" in out:
        out.pop("ret")
    if "adv" in out and "advpay" in out:
        out.pop("advpay")
    if "net" in out and "total" in out:
        if re.search(r" (excluding|before|without|exclusive of) (vat|tax)", n):
            out.pop("total")
        elif re.search(r" including (vat|tax)| inc vat| with vat", n):
            out.pop("net")
    if "auth" in out:
        out.pop("net", None)
    if "net" in out and "total" in out and re.search(r" net ", n):
        out.pop("total")
    if "prev" in out:
        for k in ("net", "total", "work", "gross", "advpay"):
            out.pop(k, None)
    if "var" in out and ("work" in out or "gross" in out):
        if out["var"][0] >= 0.85 and not re.search(r" (and|including|plus|with) variation", n):
            out.pop("work", None)
        else:
            out.pop("var")
    if "vat" in out and ("total" in out or "net" in out):
        if re.search(r" (amount|total|due|payable).*(including|with|plus) (vat|tax)", n):
            out.pop("vat")
    if "extra" in out and len(out) > 1:
        out.pop("extra")
    return tuple(sorted(((k, s, h) for k, (s, h) in out.items()), key=lambda x: -x[1]))


def col_roles(text):
    return dict(_col_roles(text))


@lru_cache(maxsize=20000)
def _col_roles(text):
    """{role: score} for a column heading."""
    n = norm(text)
    out = {}
    for k, pats in COL.items():
        for rx, s in pats:
            if rx.search(n):
                out[k] = max(out.get(k, 0), s)
    if "p" in out and "c" in out and re.search(r" previous", n):
        out.pop("c")                      # "Previous cumulative", "Previous total" are the previous column
    if "t" in out and "c" in out and re.search(r" (this|current)", n) and not re.search(r" to date| cumulative", n):
        out.pop("c")
    return tuple(out.items())


def is_header_text(text):
    r = col_roles(text)
    return bool(r) and max(r.values()) >= 0.55

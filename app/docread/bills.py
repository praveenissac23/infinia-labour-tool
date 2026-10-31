"""Client bills (IPA / interim payment certificates) and subcontractor payment certificates, any layout.

One model covers both. The figures of a bill, each possibly in three columns (p = previous, t = this period,
c = cumulative / to date):

  work      value of work done           var     variations          mos   material on site
  gross     work + variations (+ MOS)    ret     retention           rel   retention released
  adv       advance recovered            advpay  advance paid (a sub PC adds it)
  contra@n  other deductions (back charges, material / manpower supplied ...), one per line
  net       net certified: net_c to date, net_p previously certified, net_t due this time
  vat       VAT on net_t                 auth    authority fees passed on    total  amount due (net_t + VAT + fees)

and the document's own sums decide which printed figure is which.
"""
import re
import time
from collections import defaultdict

from . import kv
from .numparse import digit_edit_close
from .solve import Cand, Rel, evaluate, solve, statuses
from .tables import analyse, assign_roles
from .vocab import row_concepts

FLOW = ("work", "var", "gross", "mos", "ret", "rel", "adv", "advpay", "ded")
SIGNED = ("net", "extra", "vat", "total")


def _labels_for(infos, i):
    """[(label, weight)]: the row's own label; for a row of figures only, the lines with words just above and
    below (nearest first, a little less sure)."""
    ri = infos[i]
    if ri.label:
        return [(ri.label, 1.0)]
    out = []
    for j in range(max(0, i - 3), min(len(infos), i + 4)):
        if j == i:
            continue
        o = infos[j]
        if o.row.page != ri.row.page or not o.label or o.header is not None:
            continue
        if any(not t.pct and t.money_like for t in o.toks):
            continue
        d = abs(o.row.y - ri.row.y)
        lim = 1.5 if ri.grid else 16
        if d <= lim:
            out.append((d, o.label))
    out.sort()
    return [(lab, 0.95 if k == 0 else 0.45) for k, (d, lab) in enumerate(out[:2])]


def _label_for(infos, i):
    """The words a row's figures belong to: its own label, else (a scan, a wrapped label) the line just above or
    just below with words and no figures."""
    ri = infos[i]
    if ri.label:
        return ri.label
    best = None
    for j in (i - 1, i + 1, i - 2):
        if 0 <= j < len(infos):
            o = infos[j]
            if o.row.page != ri.row.page or not o.label or o.header is not None:
                continue
            if any(not t.pct and t.money_like for t in o.toks):
                continue
            d = abs(o.row.y - ri.row.y)
            lim = 1.5 if ri.grid else 16
            if d <= lim and (best is None or d < best[0]):
                best = (d, o.label)
    return best[1] if best else ""


KEY = {"work", "gross", "ret", "adv", "prev", "net", "vat", "total", "var", "rel", "contra", "auth", "advpay", "mos"}


def _summary_zone(infos, span=40):
    """The payment summary: the stretch of rows (within one sheet / page) holding the most different bill
    lines (work, retention, advance, previous, net, VAT, total ...). Figures there are the bill's; the same
    words in a breakdown sheet further on are less likely to be."""
    marks = []
    for i, ri in enumerate(infos):
        if ri.header is not None or not ri.label:
            continue
        if not any(not t.pct and (t.money_like or t.raw) for t in ri.toks):
            continue
        cs = [c for c, s, h in row_concepts(ri.label) if c in KEY and s >= 0.6]
        if cs:
            marks.append((i, ri.row.page, cs[0]))
    best, best_n = set(), 0
    for a in range(len(marks)):
        seen, last = set(), a
        for b in range(a, len(marks)):
            if marks[b][1] != marks[a][1] or marks[b][0] - marks[a][0] > span:
                break
            seen.add(marks[b][2])
            last = b
        if len(seen) > best_n:
            best_n = len(seen)
            lo, hi = marks[a][0], marks[last][0]
            best = set(range(max(0, lo - 3), hi + 4))
    return best if best_n >= 3 else set(range(len(infos)))


def _vars_for(concept, role, hint, i, label):
    """[(field, weight)] a figure of this concept in this column can be."""
    r = role if role in ("p", "t", "c") else "s"
    if concept in FLOW:
        return [(f"{concept}_{'c' if r == 's' else r}", 1.0)]
    if concept == "contra":
        return [(f"contra@{i}_{'c' if r == 's' else r}", 1.0)]
    if concept == "extra":
        return [(f"extra@{i}", 1.0)] if r in ("s", "t") else []
    if concept == "pitem":
        return [(f"pitem@{i}", 1.0)] if r in ("s", "c") else []
    if concept == "net":
        if r != "s":
            return [(f"net_{r}", 1.0)]
        if hint == "t":
            return [("net_t", 1.0), ("net_c", 0.45)]
        if hint == "c":
            return [("net_c", 1.0), ("net_t", 0.45)]
        return [("net_t", 0.8), ("net_c", 0.7)]
    if concept == "prev":
        return [("net_p", 1.0)] if r in ("s", "c", "p") else []
    if concept in ("vat", "total", "auth"):
        if r in ("s", "t"):
            return [(concept, 1.0)]
        return [(f"{concept}_{r}", 1.0)]
    if concept == "contract":
        return [("contract", 1.0)]
    return []


def candidates(doc):
    infos = assign_roles(analyse(doc))
    dom = defaultdict(list)
    multi = {}                     # contra@i / extra@i -> label
    words_total = []
    zone = _summary_zone(infos)
    section = None
    for i, ri in enumerate(infos):
        if ri.header is not None:
            continue
        txt = ri.row.text
        if re.search(r"dirhams?|only", txt, re.I) and re.search(r"thousand|hundred|million", txt, re.I):
            w = kv.words_amount(txt)
            if w:
                words_total.append(w)
        labs = _labels_for(infos, i)
        concepts, label = [], ""
        for lab, lw in labs:
            cs_ = row_concepts(lab)
            if cs_:
                concepts = [(c, s * lw, h) for c, s, h in cs_]
                label = lab
                break
        has_fig = any(not t.pct and (t.money_like or t.raw) for t in ri.toks)
        top = concepts[0][0] if concepts else None
        # "LESS: PREVIOUSLY CERTIFIED" opens a list of earlier certificates; each line is a previous payment,
        # not an advance or a deduction, until the net / VAT / total lines
        if top == "prev" and not has_fig:
            section = ("prev", ri.row.page)
            continue
        if section and (top in ("net", "total", "vat", "work", "gross", "ret") or (section[1] != ri.row.page)):
            section = None
        if section and top != "prev" and has_fig:
            concepts = [("pitem", 0.8, None)]
            label = label or ri.label or ri.row.text[:40]
        if not concepts:
            continue
        money = [t for t in ri.toks if not t.pct and t.role not in ("pct", "qty", "rate") and (t.money_like or t.raw)]
        pcts = [t for t in ri.toks if t.pct or t.role == "pct"]
        # three figures with no headings where one is the sum of the other two: previous, this, cumulative
        if money and not any(t.role in ("p", "t", "c") for t in money) and len(money) >= 3:
            for a in range(len(money) - 2):
                x, y, z = money[a:a + 3]
                if abs(abs(x.value) + abs(y.value) - abs(z.value)) <= 0.05 and abs(z.value) > 0:
                    x.role, y.role, z.role = "p", "t", "c"
                    x.role_score = y.role_score = z.role_score = 0.8
                    break
        headed = any(t.role for t in money)
        conf_row = 1.0
        page_f = 1.0 if i in zone else 0.62
        less = bool(re.match(r"\s*(less|deduct)", label, re.I))
        for concept, cs, hint in concepts:
            if concept in ("ret", "adv", "vat"):
                for t in pcts:
                    if t.pct and 0 < t.value <= 100:
                        dom[f"{concept}_pct"].append(Cand(f"{concept}_pct", t.value, cs * 0.9, t, label))
            plain = [t for t in money if t.role in ("", "amount", "certified", "claimed")]
            for t in money:
                if t.role in ("p", "t", "c"):
                    role, rs = t.role, t.role_score
                elif t.role == "contract":
                    if concept == "contract":
                        role, rs = "s", 1.0
                    else:
                        continue
                else:
                    k = plain.index(t)
                    rs = (1.0, 0.65, 0.5, 0.4)[min(k, 3)]
                    if headed and not t.role:
                        rs *= 0.55                   # a figure beside the table, under no heading
                    if t.role == "claimed":
                        rs *= 0.7
                    role = "s"
                conf = min(1.0, t.cell.conf + 0.15) if ri.row.ocr else 1.0
                for var, w in _vars_for(concept, role, hint, i, label):
                    v = t.value
                    if concept not in SIGNED:
                        v = abs(v)
                    elif concept == "extra":
                        v = -abs(v) if less else abs(v)
                    prior = cs * rs * w * conf * page_f
                    if var.endswith(("_p", "_t")) and not var.startswith("net"):
                        prior *= 0.35                # previous / this-period figures are not reported - they only check
                    dom[var].append(Cand(var, round(v, 2), round(prior, 4), t, label))
                    if "@" in var:
                        multi[var] = label
                    if concept == "pitem":
                        dom[var][-1].value = abs(dom[var][-1].value)
    return dom, multi, words_total, infos


# ---- relations ------------------------------------------------------------------------------------------

def relations(dom, multi, vat_rate=5.0):
    contra = sorted({v.split("_")[0] for v in multi if v.startswith("contra@")})
    extras = sorted(v for v in multi if v.startswith("extra@"))
    rels = []

    def G(get, k):
        g = get(f"gross_{k}")
        if g is not None:
            return g
        w = get(f"work_{k}")
        if w is None:
            return None
        return w + (get(f"var_{k}") or 0) + (get(f"mos_{k}") or 0)

    def ded(get, k):
        t = get(f"ded_{k}")
        if t is not None:
            return t - (get(f"rel_{k}") or 0) - ((get("advpay_c") or 0) if k == "c" else 0)
        d = (get(f"ret_{k}") or 0) + (get(f"adv_{k}") or 0) + sum(get(f"{c}_{k}") or 0 for c in contra) - (get(f"rel_{k}") or 0)
        if k == "c":
            d -= get("advpay_c") or 0
        return d

    def gvars(k):
        return [f"gross_{k}", f"work_{k}", f"var_{k}", f"mos_{k}"]

    def dvars(k):
        return [f"ded_{k}", f"ret_{k}", f"adv_{k}", f"rel_{k}"] + [f"{c}_{k}" for c in contra] + (["advpay_c"] if k == "c" else [])

    for X in list(FLOW) + ["net"] + contra:
        def col(get, X=X):
            a, b, c = get(f"{X}_p"), get(f"{X}_t"), get(f"{X}_c")
            if a is None or b is None or c is None:
                return None
            return a + b, c
        rels.append(Rel(f"col:{X}", [f"{X}_p", f"{X}_t", f"{X}_c"], col, tol=0.06, w=0.8, text=f"{X}: previous + this period = to date"))
    for k in ("p", "t", "c"):
        def gross(get, k=k):
            g, w = get(f"gross_{k}"), get(f"work_{k}")
            if g is None or w is None:
                return None
            return w + (get(f"var_{k}") or 0) + (get(f"mos_{k}") or 0), g
        rels.append(Rel(f"gross:{k}", gvars(k), gross, tol=0.06, w=1.5, text="work + variations = total work"))

        def net(get, k=k):
            n, g = get(f"net_{k}"), G(get, k)
            if n is None or g is None:
                return None
            return g - ded(get, k), n
        rels.append(Rel(f"net:{k}", gvars(k) + dvars(k) + [f"net_{k}"], net, tol=0.06, w=3.0, text="work - deductions = net"))

    for k in ("p", "t", "c"):
        def dedsum(get, k=k):
            t = get(f"ded_{k}")
            if t is None:
                return None
            parts = [get(f"ret_{k}"), get(f"adv_{k}")] + [get(f"{c}_{k}") for c in contra]
            if all(p is None for p in parts):
                return None
            return sum(p or 0 for p in parts), t
        rels.append(Rel(f"ded:{k}", [f"ded_{k}", f"ret_{k}", f"adv_{k}"] + [f"{c}_{k}" for c in contra], dedsum, tol=0.06, w=2.0,
                        text="the deductions add up to the total deductions"))

    pitems = sorted(v for v in multi if v.startswith("pitem@"))
    if pitems:
        def prevsum(get):
            p = get("net_p")
            xs = [get(v) for v in pitems]
            if p is None or all(x is None for x in xs):
                return None
            return sum(x or 0 for x in xs), p
        rels.append(Rel("prevsum", ["net_p"] + pitems, prevsum, tol=0.06, w=1.5, text="the earlier certificates add up to the previously certified"))

    def due(get):
        n, p, g = get("net_t"), get("net_p"), G(get, "c")
        if n is None or p is None or g is None:
            return None
        return g - ded(get, "c") - p, n
    rels.append(Rel("due", gvars("c") + dvars("c") + ["net_p", "net_t"], due, tol=0.06, w=3.0,
                    text="work to date - deductions - previously certified = net due"))

    def vat(get):
        v, n = get("vat"), get("net_t")
        if v is None or n is None:
            return None
        r = get("vat_pct") or vat_rate
        return n * r / 100.0, v
    rels.append(Rel("vat", ["vat", "net_t", "vat_pct"], vat, tol=0.06, rel_tol=0.0, w=2.0, text="VAT = 5% of the net due"))

    def total(get):
        t, n = get("total"), get("net_t")
        if t is None or n is None:
            return None
        rest = (get("auth") or 0) + sum(get(e) or 0 for e in extras)
        if get("vat") is None:
            # VAT not read (or not charged): the total is the net, or the net plus VAT
            r = (get("vat_pct") or vat_rate) / 100.0
            a, b = n + rest, n * (1 + r) + rest
            return (a if abs(a - t) <= abs(b - t) else b), t
        return n + get("vat") + rest, t
    rels.append(Rel("total", ["total", "net_t", "vat", "auth"] + extras, total, tol=1.0, w=2.0, text="net + VAT = amount due"))

    def total2(get):
        t, g, p = get("total"), G(get, "c"), get("net_p")
        if t is None or g is None or p is None or get("net_t") is not None:
            return None
        return g - ded(get, "c") - p + (get("vat") or 0) + (get("auth") or 0) + sum(get(e) or 0 for e in extras), t
    rels.append(Rel("total2", ["total", "net_p", "vat", "auth", "net_t"] + gvars("c") + dvars("c") + extras, total2, tol=1.0, w=3.0,
                    text="work to date - deductions - previously paid + VAT = amount due"))

    def vat_on(get):
        # VAT on the bill worked out from the bill's own lines (no net line printed)
        v, g, p = get("vat"), G(get, "c"), get("net_p")
        if v is None or g is None or p is None or get("net_t") is not None:
            return None
        r = get("vat_pct") or vat_rate
        return (g - ded(get, "c") - p + sum(get(e) or 0 for e in extras)) * r / 100.0, v
    rels.append(Rel("vat2", ["vat", "net_p", "net_t", "vat_pct"] + gvars("c") + dvars("c") + extras, vat_on, tol=0.06, w=2.0,
                    text="VAT = 5% of (work to date - deductions - previously paid)"))

    def retpct(get):
        p, r = get("ret_pct"), get("ret_c")
        g = G(get, "c")
        if p is None or r is None or g is None:
            return None
        w = get("work_c")
        a = g * p / 100.0
        if w is not None and abs(w * p / 100.0 - r) < abs(a - r):
            a = w * p / 100.0
        return a, r
    rels.append(Rel("retpct", ["ret_pct", "ret_c"] + gvars("c"), retpct, tol=1.0, w=1.0, text="retention = its % of the work"))

    def advpct(get):
        p, a = get("adv_pct"), get("adv_c")
        g = G(get, "c")
        if p is None or a is None or g is None:
            return None
        w = get("work_c")
        x = (w if w is not None else g) * p / 100.0
        return x, a
    rels.append(Rel("advpct", ["adv_pct", "adv_c"] + gvars("c"), advpct, tol=1.0, w=0.7, text="advance recovered = its % of the work"))
    return rels


CHECK_NAMES = {
    "due": "Work to date - deductions - previously certified = the net amount due",
    "net:c": "Work to date - deductions = net certified to date",
    "net:t": "This period's work - deductions = this period's net",
    "net:p": "Previous work - deductions = previously certified",
    "vat": "VAT is 5% of the net",
    "vat2": "VAT is 5% of the net",
    "total": "Net + VAT = total amount due",
    "total2": "The lines add up to the amount due",
    "gross:c": "Work + variations = total work executed",
    "prevsum": "The earlier certificates add up to the previously certified",
    "ded:c": "The deductions add up to the total deductions",
    "retpct": "Retention is its % of the work",
    "advpct": "Advance recovered is its % of the work",
}


def _optional(v):
    """Lines a bill may or may not have - left out when the sum says they are not the bill's."""
    return v.split("_")[0] in ("var", "mos", "rel", "advpay", "auth", "adv", "ret", "ded") or v.startswith(("contra@", "extra@", "pitem@"))


def run(doc, vat_rate=5.0, beam=150, kind="subpc"):
    t0 = time.perf_counter()
    dom, multi, words_total, infos = candidates(doc)
    if kind == "ipa":
        # a client bill never adds the advance paid back into the amount due (it is paid on its own)
        for k in [k for k in dom if k.startswith("advpay")]:
            dom.pop(k)
    # the amount in words supports the total figure it spells
    for w in words_total:
        for c in dom.get("total", []):
            if abs(c.value - w) <= 0.5:
                c.prior = min(1.2, c.prior + 0.3)
                c.note = "the amount in words agrees"
    rels = relations(dom, multi, vat_rate)
    asg, score = solve(dom, rels, beam=beam, optional=_optional)
    asg = {k: v for k, v in asg.items() if v is not None}
    notes = []
    # a scan: a figure the sums say is one digit out is put right (and said)
    if doc.ocr:
        asg, rep = _repair(asg, rels, dom)
        notes += rep
    derived = _derive(asg, rels)
    st = statuses(asg, rels)
    return {"asg": asg, "rels": rels, "status": st, "derived": derived, "notes": notes, "words_total": words_total,
            "dom": dom, "multi": multi, "ms": round((time.perf_counter() - t0) * 1000, 1)}


def _implied(rel, asg, var):
    """The value `var` must have for the relation to hold (the relations are linear in each field): found from
    two evaluations."""
    def make(x):
        def get(v):
            if v == var:
                return x
            c = asg.get(v)
            return None if c is None else c.value
        return get
    r0 = rel.fn(make(0.0))
    r1 = rel.fn(make(1.0))
    if r0 is None or r1 is None:
        return None
    d0 = r0[0] - r0[1]
    d1 = r1[0] - r1[1]
    slope = d1 - d0
    if abs(slope) < 1e-9:
        return None
    return round(-d0 / slope, 2)


def _repair(asg, rels, dom):
    notes = []
    for _ in range(2):
        bad = [(r, lhs, rhs) for r, ok, lhs, rhs in statuses(asg, rels) if not ok]
        if not bad:
            break
        fixed = False
        for r, lhs, rhs in bad:
            opts = []
            for v in r.vars:
                c = asg.get(v)
                if c is None or c.tok is None or not c.tok.cell.conf < 1.0:
                    continue
                x = _implied(r, asg, v)
                if x is None or x < 0 and v not in ("net_t", "net_c", "net_p"):
                    continue
                if digit_edit_close(c.value, x) and abs(c.value - x) > 0.005:
                    # the corrected figure must not break a relation that held
                    trial = dict(asg)
                    trial[v] = Cand(v, x, c.prior, c.tok, c.label, note="corrected by the document's sums")
                    before = sum(1 for _r, ok, *_ in statuses(asg, rels) if ok)
                    after = sum(1 for _r, ok, *_ in statuses(trial, rels) if ok)
                    if after > before:
                        opts.append((after, v, x, trial))
            if len(opts) >= 1:
                opts.sort(key=lambda o: -o[0])
                after, v, x, trial = opts[0]
                if len(opts) == 1 or opts[0][0] > opts[1][0]:
                    notes.append(f"{asg[v].label or v}: the scan read {asg[v].value:,.2f}; the document's own sums say {x:,.2f} - check it.")
                    asg = trial
                    fixed = True
                    break
        if not fixed:
            break
    return asg, notes


DERIVABLE = ("net_p", "net_t", "net_c", "vat", "total", "gross_c", "work_c")


def _derive(asg, rels):
    """A figure not printed (or not read) that the other figures fix exactly - worked out, and marked so."""
    out = {}
    for _ in range(2):
        for r in rels:
            missing = [v for v in r.vars if v not in asg and v in DERIVABLE and not (v == "gross_c" and "work_c" in asg)
                       and not (v == "work_c" and "gross_c" in asg)]
            if len(missing) != 1:
                continue
            v = missing[0]
            if r.name.startswith(("retpct", "advpct", "vat")) and v != "vat":
                continue
            if r.name.startswith("gross") and v == "work_c" and not asg.get("var_c"):
                continue
            if (v == "gross_c" and "work_c" in asg) or (v == "work_c" and "gross_c" in asg):
                continue
            x = _implied(r, asg, v)
            if x is None or x < -0.005 and not v.startswith("net"):
                continue
            # needs the relation's real terms present (not a sum of nothing)
            present = [u for u in r.vars if u in asg]
            if len(present) < (1 if r.name == "prevsum" else 2):
                continue
            asg[v] = Cand(v, x, 0.5, None, note=f"worked out: {CHECK_NAMES.get(r.name, r.text)}")
            out[v] = r.name
    return out


# ---- the reports ----------------------------------------------------------------------------------------

MAIN = ("due", "net:c", "net:t", "total", "total2", "vat", "vat2", "ded:c", "prevsum", "gross:c")


def _conf(var, c, st, derived):
    """0-1. A figure is sure when one of the bill's own sums that ties it to the amount due holds; a figure no
    such sum checks stays below 0.8 (shown for checking), however well its label matched."""
    if var in derived:
        return 0.55
    if c.note.startswith("corrected"):
        return 0.6
    ok = sum(1 for r, good, *_ in st if good and var in r.vars and r.name in MAIN and _involved(r, var))
    weak = sum(1 for r, good, *_ in st if good and var in r.vars and r.name not in MAIN)
    bad = sum(1 for r, good, *_ in st if not good and var in r.vars and _involved(r, var))
    base = 0.45 + 0.3 * min(1.0, c.prior)
    conf = base + 0.2 * min(ok, 2) + 0.04 * min(weak, 1) - 0.45 * bad
    if not ok:
        conf = min(conf, 0.75)
    if c.tok is not None and c.tok.cell.conf < 1.0:
        conf *= 0.75 + 0.25 * c.tok.cell.conf
        if ok:
            conf = max(conf, 0.85)
    return round(max(0.05, min(0.99, conf)), 2)


def _involved(r, var):
    return True


def _detail(var, c, st, derived):
    conf = _conf(var, c, st, derived)
    d = {"value": c.value, "confidence": conf, "status": "ok" if conf >= 0.8 else "check", "label": c.label, "where": c.where()}
    if var in derived:
        d["status"] = "derived"
        d["note"] = c.note
    elif c.note:
        d["note"] = c.note
    return d


def _checks(st):
    out, seen = [], set()
    for r, ok, lhs, rhs in st:
        if r.name.startswith("col:"):
            name = f"Previous + this period = to date ({r.name[4:].split('@')[0]})"
        else:
            name = CHECK_NAMES.get(r.name, r.text)
        if (name, ok) in seen:
            continue
        seen.add((name, ok))
        diff = abs(lhs - rhs)
        out.append({"name": name, "ok": bool(ok), "detail": f"{lhs:,.2f} worked out, {rhs:,.2f} on the document" +
                    (" (rounded to the dirham)" if ok and 0.005 < diff <= 1.0 else "")})
    return out


def _out(fields, detail, found_names, notes, checks, doc, ms, extra=None):
    f = {k: v for k, v in fields.items() if v not in (None, "")}
    low = [found for k, found in found_names if k in detail and detail[k]["status"] != "ok"]
    r = {"fields": f, "found": [n for k, n in found_names if f.get(k) not in (None, "")], "notes": notes, "checks": checks,
         "detail": detail, "flagged": low, "engine": "docread",
         "source": {"kind": doc.kind, "pages": len(doc.regions), "ocr_pages": doc.ocr_pages},
         "timing": dict(doc.timing, solve_ms=ms)}
    if extra:
        r.update(extra)
    return r


def _sum_contra(asg, k="c"):
    xs = [c for v, c in asg.items() if v.startswith("contra@") and v.endswith("_" + k)]
    return xs


def read_ipa(doc):
    """A client bill / interim payment application -> the fields est_prevread.read_ipa gives, plus detail."""
    t0 = time.perf_counter()
    R = run(doc, kind="ipa")
    asg, st, derived = R["asg"], R["status"], R["derived"]
    rows = doc.rows()
    f, detail, notes = {}, {}, list(R["notes"])

    def put(key, var, val=None):
        c = asg.get(var)
        if c is None:
            return
        f[key] = round(c.value if val is None else val, 2)
        detail[key] = _detail(var, c, st, derived)
        if val is not None:
            detail[key]["value"] = f[key]
    bill, cell = kv.text_field(rows, r"(interim\s+bill|payment\s+application|interim\s+payment\s+(?:certificate|application)|ipa|ipc|"
                                     r"certificate|bill|application|valuation)\s*(no\.?|number|#|ref\.?)\s*:?", 30)
    if bill:
        f["bill_label"] = bill
        n = kv.seq_of(bill)
        if n is not None:
            f["seq"] = n
            detail["seq"] = {"value": n, "confidence": 0.9, "status": "ok", "label": "bill no.", "where": cell.where() if cell else None}
        elif re.search(r"final", bill, re.I):
            f["pc_type"] = "Final"
    if "seq" not in f and re.search(r"\bfinal\s+(bill|account|payment|certificate)|pre[\s-]*final", doc.text()[:3000], re.I):
        f["pc_type"] = "Final"
    d, cell = kv.date_field(rows, r"(issue|submission|bill|application|certificate|valuation)\s*date\s*:?")
    if not d:
        d, cell = kv.date_field(rows, r"date\s*(of\s+(issue|submission|application))?\s*:?")
    if d:
        f["submitted"] = f["period_to"] = d
        detail["submitted"] = {"value": d, "confidence": 0.85, "status": "ok", "label": "date", "where": cell.where() if cell else None}
    # figures
    g = asg.get("gross_c")
    w = asg.get("work_c")
    v = asg.get("var_c")
    mos = asg.get("mos_c")
    if g is not None:
        put("claimed_cum", "gross_c")
    elif w is not None:
        put("claimed_cum", "work_c", w.value + (v.value if v else 0) + (mos.value if mos else 0))
    if w is not None and v is not None:
        put("work", "work_c")
        put("variation", "var_c")
    elif g is not None and v is not None:
        put("variation", "var_c")
        f["work"] = round(g.value - v.value, 2)
    put("adv_rec_cum", "adv_c")
    put("ret_cum", "ret_c")
    put("ret_rel_cum", "rel_c")
    put("previous", "net_p")
    put("vat", "vat")
    put("authority", "auth")
    put("total", "total")
    put("net", "net_t")
    put("certified_cum", "net_c")
    cs = _sum_contra(asg)
    if cs:
        f["other_cum"] = round(sum(c.value for c in cs), 2)
        detail["other_cum"] = {"value": f["other_cum"], "confidence": min(_conf(c.var, c, st, derived) for c in cs), "status": "ok",
                               "label": "; ".join(c.label for c in cs)[:120], "where": cs[0].where()}
        detail["other_cum"]["status"] = "ok" if detail["other_cum"]["confidence"] >= 0.8 else "check"
    ex = [c for k, c in asg.items() if k.startswith("extra@")]
    if ex:
        f["extra"] = [{"label": c.label[:60], "v": c.value} for c in ex]
    if "claimed_cum" not in f:
        notes.append("The total value of work done was not found - type it from the bill.")
    for k, dd in detail.items():
        if dd.get("status") == "derived":
            notes.append(f"{k}: not printed / not read - {dd.get('note', 'worked out')}: {dd['value']:,.2f}")
    checks = _checks(st)
    if R["words_total"] and f.get("total") is not None:
        w0 = min(R["words_total"], key=lambda x: abs(x - f["total"]))
        checks.append({"name": "The amount in words says the same", "ok": abs(w0 - f["total"]) <= 0.5, "detail": f"words: {w0:,.2f}"})
    found = [("seq", "Bill no."), ("submitted", "Issue date"), ("claimed_cum", "Work done to date"), ("adv_rec_cum", "Advance recovered"),
             ("ret_cum", "Retention"), ("previous", "Previous payments"), ("vat", "VAT"), ("total", "Amount due")]
    return _out(f, detail, found, notes, checks, doc, round((time.perf_counter() - t0) * 1000, 1))


INFINIA_TRN = "100602393900003"
_SUFFIX = r"\b(llc|l\.l\.c\.?|fze|fzc|fzco|est\.?|establishment|co\.?|company|trading|contracting|technical|services|general|ms|m/s|the)\b"


def _sub_key(name):
    return re.sub(r"[^a-z0-9]", "", re.sub(_SUFFIX, " ", (name or "").lower()))


def match_sub(issuer, subs):
    """The subcontractor whose name is the issuer's (ignoring LLC, EST, TRADING ...), or None."""
    import difflib
    want = _sub_key(issuer)
    if len(want) < 3:
        return None
    best = None
    for s in subs or []:
        key = _sub_key(s.get("name"))
        if len(key) < 3:
            continue
        close = difflib.SequenceMatcher(None, key, want).ratio()
        if key == want or (len(key) >= 5 and (key in want or want in key)) or (min(len(key), len(want)) >= 6 and close >= 0.85):
            score = 1000 if key == want else (len(key) if (key in want or want in key) else close * 100)
            if best is None or score > best[1]:
                best = (s["id"], score)
    return best[0] if best else None


def read_subpc(doc, subs=None):
    """A subcontractor payment certificate -> the fields est_prevread.read_subpc gives, plus detail."""
    t0 = time.perf_counter()
    R = run(doc)
    asg, st, derived = R["asg"], R["status"], R["derived"]
    rows = doc.rows()
    f, detail, notes = {}, {}, list(R["notes"])

    def put(key, var, val=None):
        c = asg.get(var)
        if c is None:
            return
        f[key] = round(c.value if val is None else val, 2)
        detail[key] = _detail(var, c, st, derived)
        if val is not None:
            detail[key]["value"] = f[key]
    no, cell = kv.text_field(rows, r"\b(IPC|interim\s+payment\s+certificate|payment\s+certificate|PC|certificate)\s*(no\.?|number|#)\s*:?", 16)
    n = kv.seq_of(no or "")
    if n is not None:
        f["seq"] = n
        detail["seq"] = {"value": n, "confidence": 0.9, "status": "ok", "label": "PC no.", "where": cell.where() if cell else None}
    inv, cell = kv.text_field(rows, r"\binv(oice)?\.?\s*(ref|no|number)\.?\s*:?", 60)
    if inv:
        f["inv_ref"] = inv
    for r, j, m in kv.find_all(rows, r"inv(oice)?\.?\s*(ref|no)\b"):
        for k in range(j + 1, len(r.cells)):
            mm = re.match(r"^\s*date\s*:?", r.cells[k].text, re.I)
            if mm:
                v, _c = kv.value_after(rows, r, k, mm, below=False)
                from .numparse import a_date
                dd = a_date(v)
                if dd:
                    f["inv_date"] = dd.isoformat()
                break
        break
    for key, pat in (("received", r"inv(oice)?\.?\s*received\s*(date|on)\s*:?"), ("issued", r"(IPC|certificate|PC)\s*issued\s*(date|on)\s*:?"),
                     ("measured_on", r"measurement\s*date\s*:?")):
        d, _c = kv.date_field(rows, pat)
        if d:
            f[key] = d
    if "issued" not in f:
        d, _c = kv.date_field(rows, r"(date\s+of\s+(issue|certificate)|issue\s+date|certificate\s+date)\s*:?")
        if d:
            f["issued"] = d
    a, _c = kv.text_field(rows, r"agreement\s*(ref|no)\.?\s*:?", 60)
    if a:
        f["agreement"] = a
    s, _c = kv.text_field(rows, r"scope\s+of\s+works?\s*:?", 90)
    if s:
        f["scope_hint"] = s
    # the subcontractor: an "M/s." that is not Infinia, else the label "Subcontractor:"
    name = ""
    for r in rows:
        for c in r.cells:
            mm = re.match(r"^\s*M\s*/\s*S\.?\s*(.+)", c.text, re.I)
            if mm and "infinia" not in mm.group(1).lower():
                name = re.split(r"\s+(?:P\.?\s*O\.?\s*Box|Office|Tel|Mob|TRN|Dubai|,)", mm.group(1), maxsplit=1, flags=re.I)[0].strip(" .,")
                break
        if name:
            break
    if not name:
        v, _c = kv.text_field(rows, r"(sub-?\s*contractor|vendor|supplier)(\s+name)?\s*:", 80)
        if v and "infinia" not in v.lower():
            name = re.sub(r"^M\s*/\s*S\.?\s*", "", v, flags=re.I).strip(" .,")
    trns = [t for t in re.findall(r"TRN\s*(?:No\.?)?\s*:?\s*(\d{15})", doc.text(), re.I) if t != INFINIA_TRN]
    if trns:
        f["trn"] = trns[0]
    if name:
        f["sub_name"] = name
        best = match_sub(name, subs or [])
        if best is not None:
            f["sub_id"] = best
        else:
            f["new_sub"] = name.title().replace("Llc", "LLC") if name.isupper() else name
            notes.append(f"{f['new_sub']} is not a subcontractor on this project yet - add it as a new one below.")
    w, v, g = asg.get("work_c"), asg.get("var_c"), asg.get("gross_c")
    if w is not None:
        put("work_cum", "work_c")
    elif g is not None:
        put("work_cum", "gross_c", g.value - (v.value if v else 0))
    put("var_cum", "var_c")
    put("total_work", "gross_c")
    put("adv_cum", "advpay_c")
    put("adv_rec_cum", "adv_c")
    put("ret_cum", "ret_c")
    put("ret_rel_cum", "rel_c")
    put("prev_cert", "net_p")
    put("net", "net_t")
    put("vat", "vat")
    put("total", "total")
    cs = _sum_contra(asg)
    if cs:
        f["other_cum"] = round(sum(c.value for c in cs), 2)
        confs = [_conf(c.var, c, st, derived) for c in cs]
        detail["other_cum"] = {"value": f["other_cum"], "confidence": min(confs), "status": "ok" if min(confs) >= 0.8 else "check",
                               "label": "; ".join(c.label for c in cs)[:120], "where": cs[0].where()}
        f["other_note"] = "; ".join(f"{re.sub(r'^(less|other deductions?)[:\s-]*', '', c.label, flags=re.I).strip() or 'Deduction'} {c.value:,.2f}"
                                    for c in cs)[:200]
    if f.get("work_cum") is None:
        notes.append("The value of work executed to date was not found - type it from the certificate.")
    for k, dd in detail.items():
        if dd.get("status") == "derived":
            notes.append(f"{k}: not printed / not read - {dd.get('note', 'worked out')}: {dd['value']:,.2f}")
    checks = _checks(st)
    found = [("sub_id", "Subcontractor"), ("seq", "PC no."), ("inv_ref", "Invoice no."), ("issued", "Issued on"), ("work_cum", "Work to date"),
             ("var_cum", "Variations to date"), ("adv_cum", "Advance paid"), ("adv_rec_cum", "Advance recovered"), ("ret_cum", "Retention"),
             ("other_cum", "Deductions"), ("ret_rel_cum", "Retention released"), ("prev_cert", "Previously certified"), ("net", "Net due"), ("total", "Total due")]
    return _out(f, detail, found, notes, checks, doc, round((time.perf_counter() - t0) * 1000, 1))

"""Choosing figures by the document's own arithmetic.

Every field has a few candidate figures (from rows whose words mean that field, under the right column heading),
each with a prior score (how well its label and heading match). A relation is an equation the document must keep
(previous + this = cumulative; gross - deductions = net; VAT = 5% of net; net + VAT = total ...). The search picks
one candidate (or none) per field so that the sum of priors plus a reward for every relation kept, minus a penalty
for every relation broken, is highest - a beam search, as the fields are few.
"""
from dataclasses import dataclass, field
from typing import Callable, List, Optional


@dataclass
class Cand:
    var: str
    value: float
    prior: float
    tok: object = None          # tables.Tok (None for a derived figure)
    label: str = ""
    note: str = ""

    @property
    def key(self):
        return self.tok.key if self.tok is not None else None

    def where(self):
        if self.tok is None:
            return None
        w = self.tok.cell.where()
        if "bbox" in w and self.tok.x0 is not None and not self.tok.raw and self.tok.cell.words:
            c = self.tok.cell
            w["bbox"] = [round(self.tok.x0, 1), round(c.y0, 1), round(self.tok.x1, 1), round(c.y1, 1)]
        return w


@dataclass
class Rel:
    name: str
    vars: List[str]                       # every field the relation reads (optional ones included)
    fn: Callable                          # get -> (lhs, rhs) or None when it cannot be checked
    tol: float = 0.05
    w: float = 2.0
    text: str = ""                        # how it reads to a person
    rel_tol: float = 0.0


def evaluate(rel, get):
    try:
        r = rel.fn(get)
    except TypeError:
        return None, None, None
    if r is None:
        return None, None, None
    lhs, rhs = r
    tol = max(rel.tol, abs(rhs) * rel.rel_tol)
    ok = abs(lhs - rhs) <= tol + 1e-9
    return ok, lhs, rhs


def solve(domains, rels, beam=150, max_cands=6, optional=None):
    """domains: {var: [Cand]} -> ({var: Cand or None}, score)."""
    doms = {}
    for v, cs in domains.items():
        cs = sorted(cs, key=lambda c: -c.prior)
        seen, keep = set(), []
        for c in cs:
            k = (round(c.value, 2), c.key)
            if k in seen:
                continue
            seen.add(k)
            keep.append(c)
            if len(keep) >= max_cands:
                break
        doms[v] = keep
    rels = [r for r in rels if any(v in doms for v in r.vars)]
    count = {v: sum(v in r.vars for r in rels) for v in doms}
    # order the fields so that relations are complete (and judged) as early as possible
    order, left = [], set(doms)
    need = [set(v for v in r.vars if v in doms) for r in rels]
    while left:
        def gain(v):
            done = sum(1 for n in need if v in n and n - set(order) - {v} == set())
            return (done, count[v], -len(doms[v]), v)
        v = max(left, key=gain)
        order.append(v)
        left.discard(v)
    pos = {v: i for i, v in enumerate(order)}
    done_at = {}
    for r in rels:
        vs = [v for v in r.vars if v in pos]
        last = max(pos[v] for v in vs)
        done_at.setdefault(last, []).append(r)
    # relations whose fields have no candidates at all are judged with what is there, once at the start
    states = [(0.0, {}, frozenset())]
    for i, v in enumerate(order):
        new = []
        for score, asg, used in states:
            for c in doms[v] + [None]:
                if c is not None and c.key is not None and c.key in used:
                    continue
                a2 = dict(asg)
                a2[v] = c
                s2 = score + (c.prior if c is not None else 0.0)
                get = _getter(a2)
                for r in done_at.get(i, []):
                    ok, lhs, rhs = evaluate(r, get)
                    if ok is None:
                        continue
                    if ok and abs(lhs) < 0.005 and abs(rhs) < 0.005:
                        continue                      # all zeros proves nothing
                    s2 += r.w if ok else -1.25 * r.w
                u2 = used | {c.key} if c is not None and c.key is not None else used
                new.append((s2, a2, u2))
        new.sort(key=lambda x: -x[0])
        states = new[:beam]
    best = dict(states[0][1]) if states else {}
    for v in doms:
        best.setdefault(v, None)
    # local search: change one field at a time while the whole score improves (a beam can drop the right
    # combination when many fields compete; this puts it back). Then whole families of fields (a figure's
    # previous / this / to-date) are tried left out together, as a table elsewhere in the file can look like
    # part of the bill.
    best, cur = _climb(best, score_of(best, rels), order, doms, rels)
    fams = {}
    for v in order:
        fams.setdefault(v.rsplit("_", 1)[0], []).append(v)
    for fam, vs in fams.items():
        if len(vs) < 2 or not any(best.get(v) is not None for v in vs):
            continue
        trial = dict(best)
        for v in vs:
            trial[v] = None
        t2, s2 = _climb(trial, score_of(trial, rels), order, doms, rels, passes=3, frozen=set(vs))
        if s2 > cur + 1e-9:
            best, cur = _climb(t2, s2, order, doms, rels)
    if optional is not None:
        best, cur = _explain(best, cur, order, doms, rels, optional)
    return best, cur


def _explain(best, cur, order, doms, rels, optional, rounds=4):
    """A broken sum is often a line that is not part of it (a breakdown table's figure taken for a bill line):
    the sum is tried with up to three of its optional lines left out - after adding a strong figure that was
    held back because the sum broke."""
    from itertools import combinations
    for _ in range(rounds):
        trials = [(best, None)]
        for v in order:
            if best.get(v) is None and doms[v]:
                c = max(doms[v], key=lambda c: c.prior)
                used = {x.key for x in best.values() if x is not None}
                if c.prior >= 0.55 and (c.key is None or c.key not in used):
                    t = dict(best)
                    t[v] = c
                    trials.append((t, v))
        top, top_s = None, cur
        for t, added in trials:
            get = _getter(t)
            for r in rels:
                ok, lhs, rhs = evaluate(r, get)
                if ok is not False:
                    continue
                opt = [u for u in r.vars if t.get(u) is not None and u != added and optional(u)]
                # one field of the sum may also take another of its candidates (the right retention is in the
                # summary, the one chosen came from a breakdown table)
                switches = [(None, None)]
                for u in r.vars:
                    if u == added or u not in doms:
                        continue
                    for c in doms[u]:
                        if c is not t.get(u):
                            switches.append((u, c))
                for k in (0, 1, 2, 3):
                    for sub in combinations(opt, k):
                        for su, sc in (switches if k <= 2 else [(None, None)]):
                            if k == 0 and su is None:
                                continue
                            if su in sub:
                                continue
                            t2 = dict(t)
                            for u in sub:
                                t2[u] = None
                            if su is not None:
                                used = {x.key for v_, x in t2.items() if x is not None and v_ != su}
                                if sc.key is not None and sc.key in used:
                                    continue
                                t2[su] = sc
                            ok2, _, _ = evaluate(r, _getter(t2))
                            if not ok2:
                                continue
                            frozen = set(sub) | ({added} if added else set()) | ({su} if su else set())
                            t2, s2 = _climb(t2, score_of(t2, rels), order, doms, rels, passes=2, frozen=frozen)
                            if s2 > top_s + 1e-9:
                                top, top_s = t2, s2
        if top is None:
            break
        best, cur = _climb(top, top_s, order, doms, rels, passes=3)
    return best, cur


def _climb(best, cur, order, doms, rels, passes=6, frozen=()):
    for _ in range(passes):
        improved = False
        for v in order:
            if v in frozen:
                continue
            used = {c.key for u, c in best.items() if c is not None and u != v and c.key is not None}
            for c in doms[v] + [None]:
                if c is best.get(v) or (c is not None and c.key in used):
                    continue
                trial = dict(best)
                trial[v] = c
                s2 = score_of(trial, rels)
                if s2 > cur + 1e-9:
                    best, cur, improved = trial, s2, True
        if not improved:
            break
    return best, cur


def score_of(asg, rels):
    s = sum(c.prior for c in asg.values() if c is not None)
    get = _getter(asg)
    for r in rels:
        ok, lhs, rhs = evaluate(r, get)
        if ok is None:
            continue
        if ok and abs(lhs) < 0.005 and abs(rhs) < 0.005:
            continue
        s += r.w if ok else -1.25 * r.w
    return s


def _getter(asg):
    def get(v):
        c = asg.get(v)
        return None if c is None else c.value
    return get


def statuses(asg, rels):
    """[(rel, ok, lhs, rhs)] for every relation that could be checked."""
    get = _getter(asg)
    out = []
    for r in rels:
        ok, lhs, rhs = evaluate(r, get)
        if ok is None:
            continue
        out.append((r, ok, lhs, rhs))
    return out

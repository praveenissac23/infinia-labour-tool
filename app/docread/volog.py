"""Variation logs in any layout (Excel, PDF, scan, Word): the table is found by its headings, each heading is
mapped to what it means with the synonym list below (fuzzy, several rows deep), and every row becomes one
variation in the shape est_voimport.read_log gives. A column whose heading is unclear ("Submitted") is decided by
what is in it (dates or amounts). The totals row, when the log has one, checks every money column.
"""
import re
import time

from .numparse import a_date, excel_date
from .tables import cell_numbers
from .vocab import norm

H = {
    "ref": [(r" (ref|reference)( no| number| #)?\b", 0.9), (r" (vo|variation|v o|cp|cvi|si|vi|change order|co|rfv)( ref)? ?(no|number|#)\b", 0.95),
            (r"^ (no|#)\s*$", 0.5), (r" var(iation)? ?(ref|id)\b", 0.9), (r" رقم", 0.6)],
    "title": [(r" description\b", 0.95), (r"^ (item|items|details|particulars|subject|scope|title|work description|variation description)\s*$", 0.85),
              (r" description of (the )?(work|variation|change)", 0.95), (r" الوصف| البيان", 0.9)],
    "submitted_amount": [(r" (submitted|claimed|proposed|quoted|requested|contractor'?s?)( amount| value| cost| price)?( aed)?\s*$", 0.8),
                         (r" (amount|value|cost) (submitted|claimed|proposed|quoted)", 0.95), (r" submitted (amount|value|cost)", 0.95),
                         (r" (original|initial) (amount|value|quote)", 0.7), (r" المقدم", 0.8)],
    "revised_amount": [(r" revised( amount| value| cost| submission)?", 0.9), (r" (amount|value) revised", 0.9), (r" resubmitted", 0.8)],
    "approved_amount": [(r" (accepted|approved|certified|agreed|consultant|engineer|final|awarded)( amount| value| cost)?( aed)?\s*$", 0.85),
                        (r" (amount|value) (accepted|approved|certified|agreed)", 0.95), (r" (accepted|approved|agreed) (amount|value)", 0.95),
                        (r" المعتمد", 0.8)],
    "absorbed_amount": [(r" absorbed( amount| value)?", 0.95)],
    "submitted": [(r" (date of |)submission( date)?\b", 0.9), (r" submitted (on|date)", 0.95), (r" date submitted", 0.95), (r" (sent|issued) (on|date)", 0.8)],
    "approved_on": [(r" date of (acceptance|approval)", 0.95), (r" (approved|accepted|approval|acceptance) (on|date)", 0.95), (r" date (approved|accepted)", 0.95)],
    "pc_ref": [(r" claimed in (pc|ipa|ipc|bill)", 0.95), (r" (pc|ipa|ipc|bill) (ref|no)", 0.7), (r" billed in", 0.9), (r" included in (pc|ipa|bill)", 0.9)],
    "remarks": [(r" remarks?| comments?| notes?| ملاحظات", 0.9)],
    "ohp_status": [(r"^ status\s*$", 0.9), (r" (vo|variation) status", 0.9)],
    "claimed_pct": [(r" claimed %| % claimed", 0.95)],
    "phase": [(r"^ phase\s*$", 0.9)],
    "date": [(r"^ date\s*$", 0.7)],
    "amount": [(r"^ (amount|value|cost)( aed| dhs)?\s*$", 0.6), (r" amount \(?aed\)?", 0.6)],
}
H = {k: [(re.compile(p), s) for p, s in v] for k, v in H.items()}
MONEY = ("submitted_amount", "revised_amount", "approved_amount", "absorbed_amount")


def head_roles(text):
    n = norm(text)
    out = {}
    for k, pats in H.items():
        for rx, s in pats:
            if rx.search(n):
                out[k] = max(out.get(k, 0), s)
    if "submitted" in out and "submitted_amount" in out:
        if re.search(r" date| on\b", n):
            out.pop("submitted_amount")
        elif re.search(r" amount| value| cost| aed", n):
            out.pop("submitted")
    if "approved_on" in out and "approved_amount" in out:
        out.pop("approved_amount")
    if "ref" in out and ("pc_ref" in out):
        out.pop("ref")
    return out


def _is_header(row):
    roles = [head_roles(c.text) for c in row.cells if len(c.text) <= 60]
    keys = {k for r in roles for k in r}
    nums = sum(1 for c in row.cells if c.num is not None and not c.is_date)
    return len(keys) >= 3 and ("title" in keys or "ref" in keys) and nums <= 1


def _columns(header_rows, rows_below):
    """[(x0, x1, role, heading text)] for the heading block (one, two or three rows deep)."""
    cols = []
    base = max(header_rows, key=lambda r: len(r.cells))
    # every distinct column edge from all heading rows
    cells = [c for r in header_rows for c in r.cells if c.text.strip()]
    spans = sorted({(round(c.x0, 1), round(c.x1, 1)) for c in cells})
    # the leaf columns: heading cells that contain no other (narrower) heading cell
    leaves = [s for s in spans if not any(o != s and o[0] >= s[0] - 0.01 and o[1] <= s[1] + 0.01 for o in spans)]
    for x0, x1 in leaves:
        texts = [c.text for c in cells if min(c.x1, x1) - max(c.x0, x0) > 0.3 * min(x1 - x0, c.x1 - c.x0)]
        joined = " ".join(texts)
        roles = head_roles(joined)
        leaf = head_roles(texts[-1]) if texts else {}
        role = None
        if leaf:
            role = max(leaf, key=leaf.get)
        if roles and (role is None or role in ("amount", "date")):
            role = max(roles, key=roles.get) if role is None else role
            if role == "amount" and any(k in roles for k in MONEY):
                role = max((k for k in roles if k in MONEY), key=roles.get)
        cols.append([x0, x1, role, joined])
    # a column called just "Amount" / "Date" / "Submitted": decided by what it holds and its neighbours
    for c in cols:
        if c[2] in ("amount", None, "date"):
            kinds = _content(c, rows_below)
            if c[2] == "date" or kinds == "date":
                taken = {x[2] for x in cols}
                c[2] = "submitted" if "submitted" not in taken else ("approved_on" if "approved_on" not in taken else None)
            elif c[2] == "amount" and kinds == "money":
                taken = {x[2] for x in cols}
                c[2] = next((k for k in MONEY if k not in taken), None)
    # "Submitted" heading over a date column is the submission date, over figures the amount
    for c in cols:
        if c[2] in ("submitted", "submitted_amount", "approved_on", "approved_amount"):
            kinds = _content(c, rows_below)
            if kinds == "date" and c[2].endswith("amount"):
                c[2] = "submitted" if c[2] == "submitted_amount" else "approved_on"
            elif kinds == "money" and c[2] in ("submitted", "approved_on"):
                c[2] = "submitted_amount" if c[2] == "submitted" else "approved_amount"
    # one column per meaning: the first
    seen = set()
    for c in cols:
        if c[2] in seen:
            c[2] = None
        elif c[2]:
            seen.add(c[2])
    return cols


def _content(col, rows):
    d = m = 0
    for r in rows[:25]:
        for c in r.cells:
            if min(c.x1, col[1]) - max(c.x0, col[0]) <= 0:
                continue
            if c.is_date or (re.search(r"\d", c.text) and a_date(c.text) and not re.fullmatch(r"[\d,.\s()-]+", c.text.strip().replace("/", "x"))):
                d += 1
            elif c.num is not None or re.fullmatch(r"\(?-?\s*(AED|Dhs?\.?)?\s*[\d,]+(\.\d+)?\s*\)?-?", c.text.strip(), re.I):
                if c.num is not None and "/" in (c.fmt or "") or (c.num is not None and re.search(r"[dmy]{2}", (c.fmt or "").lower()) and excel_date(c.num)):
                    d += 1
                else:
                    m += 1
    if d > m and d >= 1:
        return "date"
    if m > d and m >= 1:
        return "money"
    return None


def _cell_for(row, col):
    best, bo = None, 0.0
    for c in row.cells:
        ov = min(c.x1, col[1]) - max(c.x0, col[0])
        if ov > bo:
            best, bo = c, ov
    if best is None:
        for c in row.cells:
            d = abs(c.xc - (col[0] + col[1]) / 2)
            if d < 12 and not row.cells[0] is c:
                best = c
    return best


def _money(c, ocr=False):
    if c is None:
        return None, ""
    t = c.text.strip()
    if not t or t in ("-", "–", "—"):
        return None, ""
    ns = [n for n in cell_numbers(c, ocr) if not n[1]]
    if len(ns) == 1 and (ns[0][4] or re.fullmatch(r"[\s(\-]*(AED|Dhs?\.?)?\s*[\d,]+(\.\d+)?\s*\)?-?\s*(AED)?\*?", t.replace("*", ""), re.I)):
        return round(ns[0][0], 2), ""
    if ns and re.fullmatch(r"\*?[\s(\-]*(AED|Dhs?\.?)?\s*[\d,]+(\.\d+)?\s*\)?-?\*?", t, re.I):
        return round(ns[0][0], 2), ""
    return None, t


def _date(c):
    if c is None:
        return None
    if c.is_date:
        from datetime import datetime
        try:
            return datetime.strptime(c.text[:10], "%d/%m/%Y").date()
        except ValueError:
            return a_date(c.text)
    if c.num is not None and excel_date(c.num) and re.search(r"[dmy]", (c.fmt or "").lower()):
        return excel_date(c.num)
    return a_date(c.text)


def _status(row):
    rem = (row.get("remarks") or "").lower()
    acc, absd = row.get("approved_amount") or 0, row.get("absorbed_amount") or 0
    if "reject" in rem or "not accepted" in rem:
        return "Rejected"
    if absd and not acc:
        return "Absorbed"
    if "absorbed" in rem and not acc:
        return "Absorbed"
    if acc:
        return "Approved"
    if re.search(r"accept|approved", rem) and row.get("approved_on"):
        return "Approved"
    if row.get("submitted_amount") or row.get("submitted") or row.get("revised_amount"):
        return "Submitted"
    return "Identified"


STATUS_WORDS = [("Rejected", r"reject|not accepted|declined"), ("Absorbed", r"absorb"), ("Approved", r"approv|accept|agreed|certif"),
                ("Submitted", r"submit|pending|under review|awaiting"), ("Identified", r"identif|to be submitted|draft")]


def read_log(doc):
    """doc -> {"rows": [...same shape as est_voimport.read_log...], "checks": [...], "detail": [...], "notes": [...]}"""
    t0 = time.perf_counter()
    all_rows = doc.rows()
    out, checks, notes, detail = [], [], [], []
    i = 0
    cols, hdr_idx = None, None
    section, parent = "", None
    totals = []
    while i < len(all_rows):
        r = all_rows[i]
        if _is_header(r):
            block = [r]
            j = i + 1
            while j < len(all_rows) and all_rows[j].page == r.page and len(block) < 3:
                nx = all_rows[j]
                roles = [head_roles(c.text) for c in nx.cells]
                if any(roles) and not any(c.num is not None and not c.is_date for c in nx.cells) and \
                        not any(_money(c)[0] is not None for c in nx.cells if re.search(r"\d", c.text)):
                    block.append(nx)
                    j += 1
                else:
                    break
            cols = _columns(block, all_rows[j:j + 25])
            hdr_idx = i
            i = j
            continue
        i += 1
        if cols is None:
            continue
        get = {}
        for c in cols:
            if c[2]:
                get[c[2]] = _cell_for(r, c)
        tcell = get.get("title")
        title = tcell.text.strip() if tcell is not None else ""
        ref = get["ref"].text.strip() if get.get("ref") is not None else ""
        if ref and tcell is get.get("ref"):
            ref = ""
        if not title and not ref:
            # a row with no description: a totals row with figures only, or nothing
            if any(_money(get.get(k), r.ocr)[0] is not None for k in MONEY):
                totals.append({k: _money(get.get(k), r.ocr)[0] for k in MONEY})
            continue
        low = title.lower()
        if re.match(r"^(grand\s+)?total|^sub[\s-]*total|^net\s+total|^الإجمالي", low) or (re.match(r"^total", ref.lower())):
            totals.append({k: _money(get.get(k), r.ocr)[0] for k in MONEY})
            continue
        if title.lower() == "description" or ref.lower().startswith(("ref", "s.no", "sl")):
            continue
        money, text_money = {}, {}
        for k in MONEY:
            v, t = _money(get.get(k), r.ocr)
            money[k] = v
            if t and t not in ("-",):
                text_money[k] = t
        sub, acc = _date(get.get("submitted")), _date(get.get("approved_on"))
        if sub is None and get.get("date") is not None:
            sub = _date(get.get("date"))
        rem = get["remarks"].text.strip() if get.get("remarks") is not None else ""
        st_txt = get["ohp_status"].text.strip() if get.get("ohp_status") is not None else ""
        has = any(v is not None for v in money.values()) or text_money or sub or acc
        if not has and not ref and re.search(r"absorbed", title, re.I):
            section, parent = "absorbed", None
            continue
        if not has and not ref and len(title) < 60 and (title.isupper() or re.match(r"^[A-Z][\w &/-]{0,40}$", title)) and not st_txt:
            if re.search(r"omission|omitted|deduct", title, re.I):
                section = "omission"
            continue                                   # a heading inside the log ("CIVIL", "MEP WORKS")
        if not has:
            nxt = all_rows[i] if i < len(all_rows) else None
            if ref and nxt is not None:
                g2 = {c[2]: _cell_for(nxt, c) for c in cols if c[2]}
                nref = g2["ref"].text.strip() if g2.get("ref") is not None else ""
                ntitle = g2["title"].text.strip() if g2.get("title") is not None else ""
                if not nref and ntitle and section != "absorbed":
                    parent = (ref, title)
                    continue
            if out and not ref and not st_txt:
                out[-1]["notes"] = (out[-1]["notes"] + "\n" if out[-1]["notes"] else "") + title   # a description run on
                continue
        if ref:
            if parent and parent[0] != ref:
                parent = None
        elif parent:
            ref, title = parent[0], f"{parent[1]} - {title}"
        phase = get["phase"].text.strip() if get.get("phase") is not None else ""
        nts = []
        if phase and phase != "-":
            nts.append(f"Phase {phase}")
        for k, label in (("submitted_amount", "Submitted"), ("revised_amount", "Revised"), ("approved_amount", "Accepted"), ("absorbed_amount", "Absorbed")):
            if k in text_money:
                nts.append(f"{label}: {text_money[k]}")
        if rem:
            nts.append(rem)
        pc = get["pc_ref"].text.strip() if get.get("pc_ref") is not None else ""
        row = {"ref": (ref if ref != "-" else "")[:40], "title": title[:1000], "submitted": sub, "approved_on": acc,
               "pc_ref": "" if pc in ("", "-", "0") else pc[:60], "remarks": (rem + " " + st_txt).strip(),
               "kind": "Addition", "source": "Design change" if re.search(r"design", title, re.I) else "Client instruction"}
        for k in MONEY:
            row[k] = money[k] or 0.0
        if section == "absorbed":
            row["status"] = "Absorbed"
        else:
            row["status"] = _status(row)
            if st_txt and not any(row[k] for k in MONEY[1:]):
                for s, rx in STATUS_WORDS:
                    if re.search(rx, st_txt, re.I):
                        row["status"] = s
                        break
        neg = [row[k] for k in MONEY if row[k]]
        if (neg and all(v < 0 for v in neg)) or section == "omission":
            row["kind"] = "Omission"
        row["notes"] = "\n".join(nts)
        row.pop("remarks", None)
        detail.append({"page": r.page, "where": (get.get("title") or r.cells[0]).where(),
                       "cells": {k: (c.where() if c is not None else None) for k, c in get.items()}, "conf": min(c.conf for c in r.cells)})
        out.append(row)
    for k, x in enumerate(out):
        x["seq"] = k + 1
    # the totals row checks each money column
    if totals:
        tot = totals[-1]
        for k in MONEY:
            if tot.get(k) is None:
                continue
            s = round(sum(x[k] for x in out if not (k == "approved_amount" and x["status"] == "Absorbed" and False)), 2)
            checks.append({"name": f"The {k.replace('_amount', '')} column adds up to the log's total", "ok": abs(s - tot[k]) <= 0.05 * max(1, len(out)) / 10 + 0.05,
                           "detail": f"{s:,.2f} added up, {tot[k]:,.2f} on the log"})
    if not out:
        notes.append("No variation log found - no table with a description and amount headings.")
    return {"rows": out, "checks": checks, "notes": notes, "detail": detail, "engine": "docread",
            "timing": dict(doc.timing, solve_ms=round((time.perf_counter() - t0) * 1000, 1))}

"""Estimation > Bills: the monthly bill (interim payment application) to the client / consultant, in their own format.

A project's format is uploaded once - the last bill as the consultant wants it, as an Excel workbook. Each month
"New bill" starts from the last one: Previous % takes last month's Total %, the bill no. moves on, the issue date
is today, last bill goes onto the previous payments to be completed when the money comes in. Staff type the
month's Total % on each line (and anything else typed on the sheets - payments, authority fees); every formula is
worked out as Excel does. The bill goes out as the same workbook (Excel), or printed / PDF.
"""
import io
import json
import os
import tempfile
import re
from datetime import date, datetime

from fastapi import Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy import Column, Date, DateTime, Float, Integer, LargeBinary, String, Text, func
from sqlalchemy.orm import Session, deferred

import auth
import models
from database import Base, get_db
import estimation as E
import est_bills_engine as BE
import est_bills_render as BR

router = E.router
STATUSES = ["Draft", "Awaiting approval", "Approved", "Submitted", "Certified", "Paid"]


class EstBillFormat(Base):
    __tablename__ = "est_bill_formats"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, nullable=False, index=True)
    contract_id = Column(Integer, nullable=True, index=True)   # which of the project's contracts (only when it has several)
    name = Column(String, default="")              # "IPA - Emkaan format"
    filename = Column(String, default="")
    # both big (megabytes): loaded only when used - not on every list or bill request
    data = deferred(Column(LargeBinary))           # the workbook as uploaded (the bill comes out as this file)
    model = deferred(Column(Text, default=""))     # read once: cells, formulas, look, where the month's figures go
    checked = Column(Text, default="")             # how many formulas give Excel's own figures
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class EstBill(Base):
    __tablename__ = "est_bills"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, nullable=False, index=True)
    format_id = Column(Integer, nullable=False, index=True)
    contract_id = Column(Integer, nullable=True, index=True)   # the format's contract
    seq = Column(Integer, default=1)
    label = Column(String, default="")             # the bill no. as on the bill (9, 7-R2 ...)
    issue_date = Column(Date, nullable=True)
    status = Column(String, default="Draft")
    inputs = Column(Text, default="{}")            # {sheet: {"r,c": value}} - what was typed this month
    total_due = Column(Float, default=0.0)
    work_done = Column(Float, default=0.0)
    notes = Column(Text, default="")
    signs = Column(Text, default="")               # who signs: {group: {"name", "title"}} (the person's signature from est_signatures)
    created_by = Column(Integer, nullable=True)
    updated_by = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class EstSignature(Base):
    """A person's signature for the bills (uploaded once, used on every bill they prepare / check)."""
    __tablename__ = "est_signatures"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, index=True)
    title = Column(String, default="")
    png = deferred(Column(LargeBinary))            # cleaned: white made see-through, cropped
    updated_by = Column(Integer, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


def create_tables(engine):
    from sqlalchemy import inspect, text
    for t in (EstBillFormat, EstBill, EstSignature):
        t.__table__.create(bind=engine, checkfirst=True)
    for tb, col, typ in (("est_bills", "signs", "TEXT"), ("est_bills", "contract_id", "INTEGER"), ("est_bill_formats", "contract_id", "INTEGER")):
        try:                                       # columns added after the tables were made
            have = {c["name"] for c in inspect(engine).get_columns(tb)}
            if col not in have:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {tb} ADD COLUMN {col} {typ}"))
        except Exception as e:
            print(f"{tb}.{col}:", e)


_MODEL_CACHE = {}
_LIST_CACHE = {}


def _model(fmt):
    hit = _MODEL_CACHE.get(fmt.id)
    if hit is None:
        hit = json.loads(fmt.model or "{}")
        if hit.get("sheets") and hit.get("mv") != BE.MODEL_VERSION and fmt.data:
            try:                                          # read before the latest reading rules: read the kept workbook again,
                hit = BE.read_format(fmt.data, fmt.filename or "")
                from sqlalchemy.orm import object_session   # and keep it, so this happens once - not on every visit
                ses = object_session(fmt)
                if ses is not None:
                    fmt.model = json.dumps(hit)
                    ses.commit()
            except Exception:
                pass
        if hit.get("sheets") and (hit.get("map") or {}).get("v") != BE.MAP_VERSION:
            hit["map"] = BE.find_inputs(hit)             # a format read before the latest reading rules
        _MODEL_CACHE[fmt.id] = hit
        if len(_MODEL_CACHE) > 12:
            _MODEL_CACHE.pop(next(iter(_MODEL_CACHE)))
    return hit


_EXP_CACHE = {}


def _bill_model(fmt, b_or_inputs):
    """The format with this bill's inserted rows applied (lines the office added to a table)."""
    inputs = b_or_inputs if isinstance(b_or_inputs, dict) else _inputs(b_or_inputs)
    model = _model(fmt)
    rows = tuple((sh, json.dumps(inp.get("_rows"))) for sh, inp in sorted(inputs.items()) if isinstance(inp, dict) and inp.get("_rows"))
    pages = json.dumps(BE.pages_of(inputs))
    if not rows and pages == "[]":
        return model
    key = (fmt.id, rows, pages)
    hit = _EXP_CACHE.get(key)
    if hit is None:
        hit = BE.expand(BE.add_pages(model, inputs), inputs)
        _EXP_CACHE[key] = hit
        if len(_EXP_CACHE) > 24:
            _EXP_CACHE.pop(next(iter(_EXP_CACHE)))
    return hit


def _inputs(b):
    try:
        return json.loads(b.inputs or "{}")
    except ValueError:
        return {}


def _get(db, model, i):
    x = db.query(model).get(i)
    if not x:
        raise HTTPException(404, "That bill is not there any more." if model is EstBill else "That format is not there any more.")
    return x


def _date_of(v):
    if isinstance(v, (int, float)) and 20000 < v < 80000:
        return (BE.EPOCH.date() + __import__("datetime").timedelta(days=int(v)))
    if isinstance(v, str):
        m = re.match(r"^\s*(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\s*$", v)
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            try:
                return date(y + 2000 if y < 100 else y, mo, d)
            except ValueError:
                return None
    return None


def _facts(model, values):
    """Bill no., issue date, total due and work done to date, read from the worked-out sheets."""
    mp = model.get("map", {})
    g = lambda ref: values.get(ref["sheet"], {}).get(f"{ref['r']},{ref['c']}") if ref else None
    bno = g(mp.get("bill_no"))
    label = BE.general(bno) if bno is not None else ""
    total = g(mp.get("total_due"))
    work = 0.0
    for t in mp.get("progress", []):
        pass
    return {"label": label, "issue_date": _date_of(g(mp.get("issue_date"))), "total_due": float(total) if isinstance(total, (int, float)) else 0.0}


def _progress(model, values, inputs):
    """The lines staff update each month, sheet by sheet: description, amount, Previous %, Total %, this month."""
    out = []
    for t in model.get("map", {}).get("progress", []):
        sh = t["sheet"]
        vals = values.get(sh, {})
        lines = []
        for ln in t["lines"]:
            r = ln["r"]
            amt = vals.get(f"{r},{t['amount_c']}") if t.get("amount_c") else None
            prev = vals.get(f"{r},{t['prev_c']}")
            tot = vals.get(f"{r},{t['tot_c']}")
            how = ln.get("how", "tot" if ln["typed_total"] else None)
            cur = vals.get(f"{r},{t['cur_c']}") if t.get("cur_c") else None
            tx = lambda c, dflt: (BE.general(vals.get(f"{r},{c}")).strip() if vals.get(f"{r},{c}") not in (None, "") else "") if c else dflt
            lines.append({"r": r, "item": tx(t.get("item_c"), ln["item"]), "desc": tx(t.get("desc_c"), ln["desc"])[:300] or ln["desc"] if t.get("desc_c") else ln["desc"],
                          "unit": tx(t.get("unit_c"), ln.get("unit", "")),
                          "amount": amt if isinstance(amt, (int, float)) else None, "amount_text": amt if isinstance(amt, str) else "",
                          "prev": prev if isinstance(prev, (int, float)) else None, "total": tot if isinstance(tot, (int, float)) else None,
                          "cur": cur if isinstance(cur, (int, float)) else None,
                          "tot_key": f"{r},{t['tot_c']}", "prev_key": f"{r},{t['prev_c']}", "cur_key": f"{r},{t['cur_c']}" if t.get("cur_c") else None,
                          "how": how, "follows": ln.get("follows", ""),
                          "tot_typed": how == "tot", "prev_typed": ln["typed_prev"],
                          "changed": isinstance(tot, (int, float)) and isinstance(prev, (int, float)) and abs(tot - prev) > 1e-9})
        sd = next((x for x in model["sheets"] if x["name"] == sh), None)
        vis = sd["visible"] if sd else True
        added = BE.added_rows(inputs, sh)
        inp = inputs.get(sh) or {}
        if sd:
            for ln in lines:
                ln["fields"] = _line_fields(model, sd, t, ln["r"], vals, inputs)
                a = added.get(ln["r"])
                ln["added"] = bool(a)
                ln["can_remove"] = bool(a) and not (ln["prev"] or 0)        # never billed: may be taken out again
        out.append({"sheet": sh, "lines": lines, "hidden": not vis, "heads": _heads(model, sd, t, vals, inputs, added) if sd else [],
                    "editable": bool(sd) and bool(t.get("item_c") or t.get("desc_c"))})
    out.sort(key=lambda t: t["hidden"])                  # sheets the consultant hid (not printed) go last
    return out


def _head_text(s, t, c):
    return " ".join(filter(None, [BE._text(s, t["head_row"], c), BE._text(s, t["head_row"] + 1, c)])).replace("\n", " ").strip()


def _nice_head(h):
    """RATE (AED) -> Rate (AED), QTY stays QTY: a column heading as a form label."""
    return " ".join(w if (w.startswith("(") or (len(w) <= 3 and w.isupper())) else w.capitalize() for w in (h or "").split())


def _line_fields(model, s, t, r, vals, inputs):
    """What can be typed about a line itself: item, description, unit and its amount - or, where the amount is
    worked out (QTY x RATE), the figures it is worked out from. [{"f", "k", "label", "value", "num", "edit"}]."""
    out = []
    def add(f, c, label, num):
        if not c:
            return
        k = f"{r},{c}"
        v = vals.get(k)
        out.append({"f": f, "k": k, "label": label, "value": v if v is not None else "", "num": num,
                    "edit": BR.editable(model, s, k, inputs)})
    add("item", t.get("item_c"), "Item / ref.", False)
    if t.get("desc_c") and t.get("desc_c") != t.get("item_c"):
        add("desc", t["desc_c"], "Description", False)
    add("unit", t.get("unit_c"), "Unit", False)
    ac = t.get("amount_c")
    if ac:
        k = f"{r},{ac}"
        if BR.editable(model, s, k, inputs):
            add("amount", ac, "Amount", True)
        else:                                           # worked out: the figures on the same line it comes from
            cell = s["cells"].get(k) or {}
            f = (inputs.get(s["name"]) or {}).get(k)
            f = f[1:] if isinstance(f, str) and f.startswith("=") else cell.get("f", "")
            cols = []
            for m in BE.REF_RE.finditer(f or ""):
                if not m.group(1) and int(m.group(5)) == r:
                    c = BE.column_index_from_string(m.group(3))
                    if c not in cols and c != ac:
                        cols.append(c)
            for c in sorted(cols):
                add(f"c{c}", c, _nice_head(_head_text(s, t, c)) or BE.get_column_letter(c), True)
            add("amount", ac, "Amount", True)
    return out


def _heads(model, s, t, vals, inputs, added):
    """The heading over each run of lines (3.1.1 Concrete (PCC/Blinding C20), Back Fill (with excavated soil)) and
    the sections put in on the bill. Only the nearest real heading above a run of lines: never the column headings
    and title the sheet repeats on every printed page, an item priced as "Included", or a specification paragraph."""
    if not t["lines"]:
        return []
    line_rows = sorted(ln["r"] for ln in t["lines"])
    mine = set(int(x) for x in ((inputs.get(s["name"]) or {}).get("_heads") or []))
    ic, dc, ac, uc = t.get("item_c"), t.get("desc_c"), t.get("amount_c"), t.get("unit_c")
    styles = model.get("styles") or []
    norm = lambda x: re.sub(r"[^a-z0-9]+", "", str(x or "").lower())
    # what the sheet prints at the top of each page: its title rows and column headings
    top = set()
    for r in range(1, t["head_row"] + 3):
        for c in range(1, (t.get("last_c") or s["maxc"]) + 1):
            v = (s["cells"].get(f"{r},{c}") or {}).get("v")
            if isinstance(v, str) and v.strip():
                top.add(norm(v))
    top.discard("")

    def head(r):
        if r in mine:
            return True
        cell = lambda c: (s["cells"].get(f"{r},{c}") or {}) if c else {}
        g = lambda c: vals.get(f"{r},{c}") if c else None
        item, desc = g(ic), g(dc)
        item = BE.general(item).strip() if item not in (None, "") else ""
        desc = desc.strip() if isinstance(desc, str) else ""
        if not (item or desc) or len(desc) > 120:
            return False
        if g(ac) not in (None, "") or (uc and g(uc) not in (None, "")):
            return False                                  # an item with a quantity or "Included": not a heading
        if "f" in cell(dc) or "f" in cell(ic) or re.search(r"cont'?d|continued", desc, re.I):
            return False                                  # the page title repeated: =$C$6&" (CONT'D)"
        if norm(desc) in top or norm(item) in top:
            return False                                  # the column headings repeated on the page
        if re.search(r"\b(total|carried|brought\s+forward|collection|sub\s*-?\s*total)\b", desc, re.I):
            return False
        st = cell(dc).get("s")
        bold = isinstance(st, int) and st < len(styles) and (styles[st] or {}).get("b")
        return bool(item) or bool(bold) or len(desc) <= 60
    out, prev = [], (t.get("start") or t["head_row"] + 1) - 1
    for lr in line_rows + [max(line_rows + list(mine)) + 1]:
        gap = [r for r in range(prev + 1, lr) if r not in line_rows]
        mine_here = [r for r in gap if r in mine]
        near = next((r for r in reversed(gap) if r not in mine and head(r)), None) if lr <= line_rows[-1] else None
        for r in sorted(set(mine_here + ([near] if near else []))):
            g = lambda c: vals.get(f"{r},{c}") if c else None
            it = g(ic); it = BE.general(it).strip() if it not in (None, "") else ""
            ds = g(dc); ds = ds.strip() if isinstance(ds, str) else ""
            out.append({"r": r, "item": it, "desc": ds, "added": r in mine, "can_remove": bool(added.get(r)),
                        "fields": [x for x in _line_fields(model, s, t, r, vals, inputs) if x["f"] in ("item", "desc")]})
        prev = lr
    return out


def _payments(model, values, inputs):
    mp = model.get("map", {})
    out = []
    for p in mp.get("payments", []):
        sh, cols = p["sheet"], p["cols"]
        vals = values.get(sh, {})
        s = next(x for x in model["sheets"] if x["name"] == sh)
        rows = []
        for r in range(p["head_row"] + 1, p["total_row"]):
            row = {"r": r}
            for k, c in cols.items():
                key = f"{r},{c}"
                raw = inputs.get(sh, {}).get(key)
                cell = s["cells"].get(key) or {}
                if raw is None:
                    raw = cell.get("v") if "v" in cell else (("=" + cell["f"]) if "f" in cell else None)
                row[k] = {"key": key, "value": vals.get(key), "raw": raw, "nf": model["styles"][cell.get("s", 0)].get("nf", "General")}
            rows.append(row)
        total = vals.get(f"{p['total_row']},{cols['amount']}")
        out.append({"sheet": sh, "cols": list(cols.keys()), "rows": rows, "total": total if isinstance(total, (int, float)) else None})
    return out


def _cover(model, values):
    """The payment summary on the cover, as the consultant set it out: each line's words and amount, the total due
    and the amount in words - shown on the bill's first step."""
    mp = model.get("map", {})
    td = mp.get("total_due")
    if not td:
        return None
    s = next((x for x in model["sheets"] if x["name"] == td["sheet"]), None)
    if not s:
        return None
    vals = values.get(s["name"], {})
    g = lambda r, c: vals.get(f"{r},{c}") if f"{r},{c}" in vals else (s["cells"].get(f"{r},{c}") or {}).get("v")
    top = td["r"]
    for r in range(td["r"] - 1, max(1, td["r"] - 30), -1):
        if any(isinstance(g(r, c), str) and re.fullmatch(r"\s*description\s*", g(r, c), re.I) for c in range(1, td["c"])):
            top = r
            break
    rows = []
    for r in range(top + 1, td["r"] + 1):
        if r in set(s.get("hidden_rows") or []):
            continue
        texts = [g(r, c) for c in range(1, td["c"]) if isinstance(g(r, c), str) and g(r, c).strip()]
        amt = g(r, td["c"])
        if not texts and not isinstance(amt, (int, float)):
            continue
        rows.append({"label": texts[0].strip() if texts else "", "detail": BR.tidy_text(" ".join(t.strip() for t in texts[1:])) if len(texts) > 1 else "",
                     "amount": amt if isinstance(amt, (int, float)) else None, "total": r == td["r"]})
    words = ""
    for w in mp.get("words", []):
        x = values.get(w["sheet"], {}).get(f"{w['r']},{w['c']}")
        if isinstance(x, str):
            words = x.strip()
    # the cover's own facts: "Project", "Location", "Client" ... with the value beside or under the label
    facts = {}
    want = {"project": r"project(\s+name)?", "location": r"location|site", "client": r"client|employer", "consultant": r"consultant|engineer"}
    for r in range(1, top):
        for c in range(1, s["maxc"] + 1):
            x = g(r, c)
            if not isinstance(x, str):
                continue
            t = x.strip().rstrip(":").strip()
            for k, pat in want.items():
                if k in facts:
                    continue
                m = re.match(rf"^({pat})\s*:\s*(.+)$", t, re.I | re.S)
                if m:                                          # "PROJECT NAME: PROPOSED ..." in one cell
                    facts[k] = m.group(m.lastindex).strip(); continue
                if re.fullmatch(pat, t, re.I):
                    right = next((g(r, cc) for cc in range(c + 1, min(c + 6, s["maxc"] + 1)) if isinstance(g(r, cc), str) and g(r, cc).strip()), None)
                    below = next((g(rr, c) for rr in range(r + 1, min(r + 4, top)) if isinstance(g(rr, c), str) and g(rr, c).strip()), None)
                    # Client / Consultant are usually headings with the name under them; Project / Location have it beside
                    v = (below or right) if k in ("client", "consultant") else (right or below)
                    if v and not re.fullmatch(r"(client|consultant|contractor|project|location)\s*:?", v.strip(), re.I):
                        facts[k] = v.strip()
    if "project" not in facts:                          # a title line across the top with no label
        for r in range(1, min(top, 4)):
            for c in range(1, s["maxc"] + 1):
                x = g(r, c)
                if isinstance(x, str) and len(x.strip()) > 25 and not re.search(r"payment application|interim", x, re.I):
                    facts["project"] = x.strip(); break
            if "project" in facts:
                break
    return {"rows": rows, "words": words, "facts": facts}


def _key(name):
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def _signs(b):
    try:
        return json.loads(b.signs or "{}") or {}
    except ValueError:
        return {}


def _sig_store(db):
    return {_key(x.name): x for x in db.query(EstSignature).all()}


def _groups(model):
    """Signing places grouped by the person the format names (the same person signs the cover and an appendix)."""
    out = {}
    for i, g in enumerate(model.get("map", {}).get("signs", [])):
        k = _key(g["name"]["orig"])
        x = out.setdefault(k, {"key": k, "orig": g["name"]["orig"], "orig_title": (g["title"] or {}).get("orig", ""), "places": [], "labels": []})
        x["places"].append(i)
        lab = g["label"] if g["label"].lower() != "signature" else "Signature"
        if lab not in x["labels"]:
            x["labels"].append(lab)
        x.setdefault("sheets", [])
        if g["sheet"] not in x["sheets"]:
            x["sheets"].append(g["sheet"])
    return list(out.values())


def _png_url(data):
    import base64 as _b
    return "data:image/png;base64," + _b.b64encode(data).decode() if data else ""


def signed_model(model, signs, store):
    """The format with this bill's signatures in place: a person's own signature where the format has one (or
    beside the name where it has none); a picture of someone no longer signing is taken off."""
    import copy, base64 as _b
    plan = sign_images(model, signs, store)
    if not plan:
        return model
    m = dict(model); m["sheets"] = list(model["sheets"])
    for si, sh in enumerate(m["sheets"]):
        mine = [p for p in plan if p["sheet"] == sh["name"]]
        if not mine:
            continue
        sh = dict(sh); ims = [dict(x) for x in sh.get("images", [])]
        drop = set()
        for p in mine:
            if p["img"] is not None:
                if p["png"] is None:
                    drop.add(p["img"])
                else:
                    base = {k: v for k, v in ims[p["img"]].items() if not (p.get("box") and k in ("c2", "r2", "dx2", "dy2"))}
                    box = {k: v for k, v in (p.get("box") or {}).items() if k in ("cx", "cy")}
                    base.pop("_stamp", None)
                    ims[p["img"]] = dict(base, data=_b.b64encode(p["png"]).decode(), ext="png", sig=True, **box)
            elif p["png"] is not None:
                ims.append(dict(p["place"], data=_b.b64encode(p["png"]).decode(), ext="png", sig=True))
        sh["images"] = [x for i, x in enumerate(ims) if i not in drop]
        m["sheets"][si] = sh
    return m


def sign_images(model, signs, store):
    """What changes on the pictures: [{sheet, img (index or None), png (bytes or None = take off), place}]."""
    out = []
    places = model.get("map", {}).get("signs", [])
    for g in _groups(model):
        want = (signs or {}).get(g["key"]) or {}
        name = (want.get("name") or "").strip() or g["orig"]
        signed = bool(want.get("signed_at"))
        sig = _sig_for(store, name)
        same = same_person(name, g["orig"])
        if not signed:
            png = None                                  # not signed yet: no signature on the bill, not even the format's
        elif same and not sig:
            continue                                    # signed, no signature uploaded: the format's own picture stays
        else:
            png = sig.png if sig else None
        for pi in g["places"]:
            p = places[pi]
            sh = next(x for x in model["sheets"] if x["name"] == p["sheet"])
            if p["img"] is not None:
                box = {}
                if png:                                 # keep the new signature's own shape inside the old picture's place
                    box = _fit_box(sh, sh["images"][p["img"]], png)
                out.append({"sheet": p["sheet"], "img": p["img"], "png": png, "box": box})
            elif png:
                out.append({"sheet": p["sheet"], "img": None, "png": png, "place": _new_place(sh, p, png)})
    return out


def _fit_box(sh, im, png):
    """A one-cell anchor at the old picture's top-left, sized to the old picture's height, the new one's shape."""
    try:
        from PIL import Image
        w, h = Image.open(io.BytesIO(png)).size
    except Exception:
        return {}
    if "cx" in im:
        hh = im.get("cy", 0) or 381000
    else:
        rows = range(im["r"] + 1, im.get("r2", im["r"]) + 1)
        hh = sum(int((sh["rowh"].get(str(r), sh["rowh"].get(r)) or sh.get("drh", 15)) * 12700) for r in rows) - im.get("dy", 0) + im.get("dy2", 0)
        hh = max(hh, 254000)
    hh = min(hh, 571500)                                # at most ~45 pt tall
    cx = int(hh * w / max(1, h))
    if cx > 1714500:                                    # and at most ~135 pt wide: a long scrawl is made smaller, not wider
        hh, cx = int(hh * 1714500 / cx), 1714500
    return {"cx": cx, "cy": int(hh)}


def _new_place(sh, p, png):
    """Where a signature goes on a format that had none: above the name, right of the label."""
    try:
        from PIL import Image
        w, h = Image.open(io.BytesIO(png)).size
    except Exception:
        w, h = 3, 1
    hh = 381000                                         # 30 pt tall
    col = p["c"]                                        # 1-based label column
    cw = (sh["colw"].get(str(col), sh["colw"].get(col)) or sh.get("dcw", 8.43)) * 7 + 5
    cx = int(hh * w / max(1, h))
    if cx > 1714500:
        hh, cx = int(hh * 1714500 / cx), 1714500
    return {"r": max(0, p["name"]["r"] - 3), "c": col - 1, "dx": int(cw * 9525 * 0.45), "dy": 0, "cx": cx, "cy": hh}


def _fees(model, values, inputs):
    """Payments to authorities this bill: the lines above the total (history rows hidden), each typed."""
    out = []
    for t in model.get("map", {}).get("fees", []):
        sh, cols = t["sheet"], t["cols"]
        s = next(x for x in model["sheets"] if x["name"] == sh)
        vals = values.get(sh, {})
        inp = inputs.get(sh, {})
        hid = set(s.get("hidden_rows") or []) | BE.hidden_extra(inputs, sh)
        rows = []
        for r in range(t["head_row"] + 1, t["total_row"]):
            if r in hid:
                continue
            row = {"r": r}
            for k, c in cols.items():
                key = f"{r},{c}"
                cell = s["cells"].get(key) or {}
                raw = inp.get(key)
                if raw is None:
                    raw = cell.get("v") if "v" in cell else (("=" + cell["f"]) if "f" in cell else None)
                row[k] = {"key": key, "value": vals.get(key), "raw": raw}
            d = row["desc"]["value"]
            row["head"] = bool(isinstance(d, str) and re.match(r"^\s*(ipa|bill|interim|payment (application|certificate)|this bill)\b", d, re.I)) and row["amount"]["value"] in (None, "", 0)
            rows.append(row)
        # the lines of this bill: from its heading ("IPA 10") on; the spacer rows above are left alone
        last_head = max((i for i, x in enumerate(rows) if x["head"]), default=None)
        if last_head is not None:
            rows = rows[last_head:]
        total = vals.get(f"{t['total_row']},{cols['amount']}")
        out.append({"sheet": sh, "cols": list(cols.keys()), "rows": rows, "total": total if isinstance(total, (int, float)) else None,
                    "total_row": t["total_row"], "hidden": len([r for r in range(t["head_row"] + 1, t["total_row"]) if r in hid])})
    return out


def _bill_out(b, fmt, model, values, inputs, users=None, store=None):
    f = _facts(model, values)
    return {"id": b.id, "project_id": b.project_id, "format_id": b.format_id, "format": fmt.name or fmt.filename, "seq": b.seq,
            "label": f["label"] or b.label, "issue_date": (f["issue_date"] or b.issue_date).isoformat() if (f["issue_date"] or b.issue_date) else "",
            "status": b.status, "total_due": f["total_due"], "notes": b.notes or "",
            "by": (users or {}).get(b.updated_by or b.created_by, ""),
            "sheets": [{"i": i, "name": s["name"], "added": bool(s.get("page_of")), "of": s.get("page_of") or "",
                        "hidden": len((inputs.get(s["name"]) or {}).get("_hide") or [])} for i, s in enumerate(model["sheets"]) if s["visible"]],
            "progress": _progress(model, values, inputs), "payments": _payments(model, values, inputs), "fees": _fees(model, values, inputs), "cover": _cover(model, values),
            "bill_no_raw": BE.general(values.get(model["map"]["bill_no"]["sheet"], {}).get(f"{model['map']['bill_no']['r']},{model['map']['bill_no']['c']}")) if model.get("map", {}).get("bill_no") else "",
            "has_date": bool(model.get("map", {}).get("issue_date")), "has_no": bool(model.get("map", {}).get("bill_no")),
            "changed": sum(len(v) for v in inputs.values()),
            "signers": _signers_out(b, model, store or {})}


def _signers_out(b, model, store):
    sg = _signs(b)
    out = []
    import base64 as _b
    places = model.get("map", {}).get("signs", [])
    for g in _groups(model):
        want = sg.get(g["key"]) or {}
        name = want.get("name") or g["orig"]
        title = want.get("title") if want.get("title") is not None else g["orig_title"]
        sig = _sig_for(store, name)
        fimg = None
        for pi in g["places"]:
            p = places[pi]
            if p["img"] is not None:
                sh = next(x for x in model["sheets"] if x["name"] == p["sheet"])
                im = sh["images"][p["img"]]
                fimg = f"data:image/{'jpeg' if im['ext'] in ('jpg', 'jpeg') else im['ext']};base64,{im['data']}"
                break
        shown = _png_url(sig.png) if sig else (fimg if same_person(name, g["orig"]) else "")
        out.append({"key": g["key"], "labels": g["labels"], "sheets": g["sheets"], "orig": g["orig"], "orig_title": g["orig_title"],
                    "name": name, "title": title, "sig": shown, "own": bool(sig), "format_has": bool(fimg),
                    "step": _step_of(g["labels"]), "signed_at": want.get("signed_at") or "", "signed_by": want.get("signed_by") or ""})
    out.sort(key=lambda x: x["step"])
    # who signs next: the first unsigned in order (prepared -> checked -> approved); the rest wait
    nxt = next((x for x in out if not x["signed_at"]), None)
    for x in out:
        x["turn"] = x is nxt
    return out


STEP_ORDER = (("prepar", 0), ("submit", 0), ("review", 1), ("check", 1), ("verif", 1), ("certif", 2), ("approv", 3))


def _step_of(labels):
    """Where a signer stands in the chain: Prepared by 0, Checked / Reviewed by 1, Approved by 3; a bare 'Signature'
    is placed by where it sits on the sheet (left first), as 9 + nothing - the sort below keeps their sheet order."""
    best = None
    for lab in labels:
        l = lab.lower()
        for word, n in STEP_ORDER:
            if word in l:
                best = n if best is None else min(best, n)
    return best if best is not None else 1


_TITLES = {"mr", "mrs", "ms", "miss", "dr", "eng", "engr", "m/s"}


def _toks(name):
    return [t for t in re.split(r"[^a-z]+", (name or "").lower()) if t and t not in _TITLES]


def _skel(t):
    """A word with its vowels and doubled letters taken out: Shafiq / Shafeeq / Shafik -> shfq."""
    t = t.replace("k", "q").replace("ph", "f")
    out = t[0] + "".join(ch for ch in t[1:] if ch not in "aeiouy")
    return re.sub(r"(.)\1+", r"\1", out)


def same_person(a, b):
    """The same person written two ways: "Anoop S" / "ANOOP SUBRAMANIAN" / login "anoop"; "Shafeeq" / "MOHAMED
    SHAFEEQ" / login "Shafiq". Every word of the shorter name must be in the longer one - whole, as its initial,
    or spelt a little differently - and at least one word must be whole (not just initials)."""
    ta, tb = _toks(a), _toks(b)
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    whole = False
    pool = list(long_)
    for t in short:
        hit = None
        for i, u in enumerate(pool):
            if t == u or (len(t) > 2 and len(u) > 2 and _skel(t) == _skel(u)):
                hit = i; whole = True; break
            if (len(t) == 1 and u.startswith(t)) or (len(u) == 1 and t.startswith(u)):
                hit = i; break
        if hit is None:
            return False
        pool.pop(hit)
    return whole


def can_sign(user, signer):
    """The person named signs (their login: full name or username, as the staff register has them), or an admin
    on their behalf."""
    if user.role == "admin":
        return True
    return same_person(user.full_name or "", signer["name"]) or same_person(user.username or "", signer["name"])


def _user_for(db, name):
    for u in db.query(models.User).filter(models.User.active == True).all():  # noqa: E712
        if same_person(u.full_name or "", name) or same_person(u.username or "", name):
            return u
    return None


def _sig_for(store, name):
    """The saved signature of this person, whichever way the name is written."""
    hit = store.get(_key(name))
    if hit:
        return hit
    for k, v in store.items():
        if same_person(v.name, name):
            return v
    return None


def staff_people(db):
    """Office staff from the staff register (QS, contracts manager, accounts ...) for picking who signs a bill."""
    out = []
    try:
        rows = db.query(models.Employee).filter(models.Employee.staff == True, models.Employee.active == True).all()  # noqa: E712
    except Exception:
        return out
    for e in rows:
        if getattr(e, "terminated_on", None):
            continue
        nm = " ".join(w.capitalize() if not re.match(r"^[A-Z]\.?$", w) else w for w in (e.name or "").split())
        out.append({"name": nm, "designation": _full_title(e.designation or ""), "short": e.designation or ""})
    out.sort(key=lambda x: x["name"])
    return out


def _full_title(d):
    t = (d or "").strip()
    m = {"qs": "Quantity Surveyor", "senior qs": "Senior Quantity Surveyor", "sr qs": "Senior Quantity Surveyor", "sr. qs": "Senior Quantity Surveyor",
         "accounts": "Accountant", "pm": "Project Manager", "pe": "Project Engineer"}
    return m.get(t.lower(), t)


def bell_items(db, user):
    """For the app's bell (asked every few seconds by every login): bills waiting for this person to check or
    approve. Read from what each bill has saved about its chain - no workbook is opened here."""
    out = []
    try:
        bills = db.query(EstBill.id, EstBill.project_id, EstBill.label, EstBill.seq, EstBill.total_due, EstBill.signs,
                         EstBill.updated_at, EstBill.created_at).filter(EstBill.status == "Awaiting approval").order_by(EstBill.id.desc()).limit(40).all()
        if not bills:
            return out
        projects = {p.id: p for p in db.query(E.EstProject).filter(E.EstProject.id.in_({x.project_id for x in bills})).all()}
        for b in bills:
            try:
                sg = json.loads(b.signs or "{}") or {}
            except ValueError:
                continue
            chain = sorted(((v.get("step", 1), k, v) for k, v in sg.items() if isinstance(v, dict) and v.get("name")), key=lambda x: (x[2].get("ord", 99), x[0]))
            nxt = next((x for x in chain if not x[2].get("signed_at")), None)
            if not nxt or nxt[0] == 0:
                continue
            name = nxt[2]["name"]
            if not (same_person(user.full_name or "", name) or same_person(user.username or "", name)):
                continue
            p = projects.get(b.project_id)
            word = {1: "check", 2: "certify", 3: "approve"}.get(nxt[0], "sign")
            when = b.updated_at or b.created_at
            out.append({"id": f"ipa-{b.id}-{nxt[1]}", "kind": "bill", "title": f"Bill {b.label or b.seq} of {p.code if p else ''} waits for you to {word} and sign",
                        "detail": f"{p.name if p else ''} - AED {b.total_due or 0:,.2f}", "screen": "pgestproj", "target": f"ipa{b.id}",
                        "pid": b.project_id, "bill": b.id, "when": when.date().isoformat() if when else "", "level": "info"})
    except Exception as e:
        print("bills bell:", e)
    return out


def _waits(b):
    """Who the bill waits for, from what is saved (no workbook read): the first unsigned in the chain."""
    sg = _signs(b)
    if not sg:
        return ""
    rows = sorted(sg.values(), key=lambda v: v.get("step", 1))
    nxt = next((v for v in rows if not v.get("signed_at")), None)
    return (nxt.get("name") or "") if nxt else ""


def _save_totals(b, model, values):
    f = _facts(model, values)
    b.total_due = f["total_due"]
    try:                                           # work done to date: every % line's amount x its Total % (as the Work done step adds it up)
        b.work_done = round(sum((l["amount"] or 0) * (l["total"] or 0) for t in _progress(model, values, {}) for l in t["lines"]), 2)
    except Exception:
        pass
    b.label = f["label"] or b.label
    b.issue_date = f["issue_date"] or b.issue_date


def _calc(model, inputs):
    inputs = BE.with_words(model, inputs)
    return inputs, BE.calculate(model, inputs)


# ---------------------------------------------------------------------------------------------------- reading

@router.get("/store/est/ipa/list")
def list_bills(project_id: int, db: Session = Depends(get_db), user: models.User = E.VIEW):
    users = {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}
    fmts = db.query(EstBillFormat).filter(EstBillFormat.project_id == project_id).order_by(EstBillFormat.id).all()
    bills = db.query(EstBill).filter(EstBill.project_id == project_id).order_by(EstBill.seq.desc(), EstBill.id.desc()).all()
    out_f = []
    for f in fmts:
        try:
            chk = json.loads(f.checked or "{}")
        except ValueError:
            chk = {}
        m = _MODEL_CACHE.get(f.id) or _LIST_CACHE.get(f.id)   # the list only needs names and counts: never re-reads a workbook
        if m is None:
            try:
                full = json.loads(f.model or "{}")
            except ValueError:
                full = {}
            m = {"sheets": [{"name": x["name"], "visible": x["visible"]} for x in full.get("sheets", [])],
                 "map": {k: full.get("map", {}).get(k) for k in ("progress", "bill_no", "issue_date", "total_due")},
                 "no": _fmt_no(full, f.filename)}
            _LIST_CACHE[f.id] = m
        mp = m.get("map", {})
        no = m["no"] if "no" in m else _fmt_no(m, f.filename)      # m is the full workbook when it was in use already
        out_f.append({"id": f.id, "no": no or [0, ""], "contract_id": f.contract_id, "name": f.name or f.filename, "filename": f.filename, "on": f.created_at.date().isoformat() if f.created_at else "",
                      "by": users.get(f.created_by, ""), "formulas": chk.get("formulas", 0), "same": chk.get("same", 0),
                      "sheets": [s["name"] for s in m.get("sheets", []) if s["visible"]],
                      "lines": sum(len(t["lines"]) for t in mp.get("progress", [])), "bill_no": bool(mp.get("bill_no")),
                      "issue_date": bool(mp.get("issue_date")), "total_due": bool(mp.get("total_due")),
                      "bills": sum(1 for b in bills if b.format_id == f.id)})
    # The format of a contract = the uploaded workbook with the highest bill no.; the others are previous bills
    cur = {}
    for x in out_f:
        k = x["contract_id"] or 0
        if k not in cur or (x["no"][0], x["id"]) > (cur[k]["no"][0], cur[k]["id"]):
            cur[k] = x
    for x in out_f:
        x["current"] = cur.get(x["contract_id"] or 0) is x
    nxt = {}
    for k in cur:
        f_, last = next_source(db, project_id, k or None)
        nxt[str(k)] = ({"kind": "bill", "id": last.id, "label": last.label or str(last.seq), "status": last.status} if last else
                       {"kind": "format", "id": f_.id if f_ else None, "label": (cur[k]["no"][1] or str(cur[k]["no"][0])) if f_ else ""})
    return {"formats": out_f, "statuses": STATUSES, "next_from": nxt,
            "bills": [{"id": b.id, "seq": b.seq, "label": b.label, "issue_date": b.issue_date.isoformat() if b.issue_date else "",
                       "status": b.status, "total_due": round(b.total_due or 0, 2), "work_done": round(b.work_done or 0, 2), "format_id": b.format_id,
                       "contract_id": b.contract_id, "waits": _waits(b),
                       "by": users.get(b.updated_by or b.created_by, ""), "updated": (b.updated_at or b.created_at).isoformat() if (b.updated_at or b.created_at) else ""}
                      for b in bills]}


def _fmt_no(full, filename=""):
    """The bill no. of an uploaded workbook - from its bill no. cell ('7-R2' -> 7), else the file name
    ('914 - IPA - 07 - R2.xlsx' -> 7): [number, as written]."""
    raw = ""
    try:
        b = (full or {}).get("map", {}).get("bill_no")
        if b:
            sh = next((x for x in full["sheets"] if x["name"] == b["sheet"]), None)
            cell = (sh or {}).get("cells", {}).get(f"{b['r']},{b['c']}") or {}
            raw = cell.get("v")
    except Exception:
        raw = ""
    def num(t):
        t = re.sub(r"\s*[-/ ]?\s*R\d+\s*$", "", str(t or "").strip(), flags=re.I)
        m_ = re.search(r"(\d+)(?!.*\d)", t)
        return int(m_.group(1)) if m_ else 0
    if isinstance(raw, (int, float)) and raw:
        return [int(raw), str(int(raw))]
    n = num(raw)
    if not n:
        stem = re.sub(r"\.xls[xm]?$", "", filename or "", flags=re.I)
        m_ = re.search(r"IPA\D*(\d+)", stem, re.I)
        n = int(m_.group(1)) if m_ else num(stem)
        raw = raw or (str(n) if n else "")
    return [n, str(raw or "")]


def _bill_num(label):
    t = re.sub(r"\s*[-/ ]?\s*R\d+\s*$", "", str(label or "").strip(), flags=re.I)
    m_ = re.search(r"(\d+)(?!.*\d)", t)
    return int(m_.group(1)) if m_ else 0


def next_source(db, pid, cid=None):
    """What the next bill is made from: the latest bill - the last bill made in the app (with every line, section
    and page added on it), or an uploaded workbook only when its bill no. is higher. -> (format, last bill or None)."""
    fmt = _current_format(db, pid, cid)
    q = db.query(EstBill).filter(EstBill.project_id == pid)
    if cid:
        q = q.filter(EstBill.contract_id == int(cid))
    last = q.order_by(EstBill.seq.desc(), EstBill.id.desc()).first()
    if last is not None:
        fno = None
        if fmt is not None:
            fno = (_LIST_CACHE.get(fmt.id) or {}).get("no") or _fmt_no(None, fmt.filename)
        if fmt is None or _bill_num(last.label or last.seq) >= (fno or [0])[0] or fmt.id == last.format_id:
            return db.get(EstBillFormat, last.format_id), last
    return fmt, None


def _current_format(db, pid, cid=None):
    """The format a new bill is made from: the workbook with the highest bill no. (not the one uploaded last)."""
    q = db.query(EstBillFormat).filter(EstBillFormat.project_id == pid)
    if cid:
        q = q.filter(EstBillFormat.contract_id == int(cid))
    best = None
    for f in q.all():
        n = (_LIST_CACHE.get(f.id) or {}).get("no")
        if n is None:
            try:
                n = _fmt_no(json.loads(f.model or "{}"), f.filename)
            except ValueError:
                n = _fmt_no(None, f.filename)
        if best is None or (n[0], f.id) > best[0]:
            best = ((n[0], f.id), f)
    return best[1] if best else None


@router.get("/store/est/ipa/format/{fid}/sheet/{i}")
def format_sheet(fid: int, i: int, db: Session = Depends(get_db), user: models.User = E.VIEW):
    """A previous bill as uploaded, one sheet at a time, to read - nothing typed in."""
    fmt = _get(db, EstBillFormat, fid)
    model = _model(fmt)
    shown = [k for k, x in enumerate(model["sheets"]) if x.get("visible", True)]
    if not shown:
        raise HTTPException(404, "This workbook has no sheets to show.")
    i = i if i in shown else shown[0]
    values = BE.calculate(model, {})
    html, w, h = BR.sheet_html(model, model["sheets"][i], values, {}, edit=False)
    return {"html": html, "width": w, "height": h, "name": model["sheets"][i]["name"], "i": i, "css": BR.SHEET_CSS,
            "sheets": [{"i": k, "name": model["sheets"][k]["name"]} for k in shown], "file": fmt.filename, "no": _fmt_no(model, fmt.filename)}


@router.get("/store/est/ipa/bill/{bid}")
def get_bill(bid: int, db: Session = Depends(get_db), user: models.User = E.VIEW):
    b = _get(db, EstBill, bid)
    fmt = _get(db, EstBillFormat, b.format_id)
    inputs = _inputs(b)
    model = _bill_model(fmt, inputs)
    values = BE.calculate(model, inputs)
    users = {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}
    return _bill_out(b, fmt, model, values, inputs, users, _sig_store(db))


@router.get("/store/est/ipa/bill/{bid}/sheet/{i}")
def bill_sheet(bid: int, i: int, db: Session = Depends(get_db), user: models.User = E.VIEW):
    """One sheet of the bill as laid out by the consultant, the cells staff may type in marked."""
    b = _get(db, EstBill, bid)
    fmt = _get(db, EstBillFormat, b.format_id)
    inputs = _inputs(b)
    model = _bill_model(fmt, inputs)
    if not (0 <= i < len(model["sheets"])):
        raise HTTPException(404, "No such sheet.")
    values = BE.calculate(model, inputs)
    s = model["sheets"][i]
    mark = {}
    for t in model.get("map", {}).get("progress", []):
        if t["sheet"] == s["name"]:
            for ln in t["lines"]:
                mark[f"{ln['r']},{t['tot_c']}"] = "tot"
    sm = signed_model(model, _signs(b), _sig_store(db))
    html, w, h = BR.sheet_html(sm, sm["sheets"][i], values, inputs, edit=b.status not in ("Paid",), mark=mark)
    return {"html": html, "width": w, "height": h, "name": s["name"], "css": BR.SHEET_CSS}


# ---------------------------------------------------------------------------------------------------- the format

_PARTS = os.path.join(tempfile.gettempdir(), "infinia_ipa_parts")


@router.post("/store/est/ipa/format/part")
async def upload_part(upload_id: str = Form(...), index: int = Form(...), file: UploadFile = File(...), user: models.User = E.VIEW):
    """A big workbook comes in pieces (the web server takes about 1 MB per request); put together by upload_format."""
    if not re.fullmatch(r"[a-f0-9]{16,40}", upload_id) or not (0 <= index < 60):
        raise HTTPException(400, "Bad upload.")
    os.makedirs(_PARTS, exist_ok=True)
    data = await file.read()
    with open(os.path.join(_PARTS, f"{user.id}_{upload_id}_{index:02d}"), "wb") as f:
        f.write(data)
    return {"ok": True, "bytes": len(data)}


def _joined(user_id, upload_id, parts):
    if not re.fullmatch(r"[a-f0-9]{16,40}", upload_id) or not (1 <= parts <= 60):
        raise HTTPException(400, "Bad upload.")
    out = b""
    for i in range(parts):
        fp = os.path.join(_PARTS, f"{user_id}_{upload_id}_{i:02d}")
        if not os.path.exists(fp):
            raise HTTPException(400, "Part of the file did not arrive - please upload it again.")
        with open(fp, "rb") as f:
            out += f.read()
        os.remove(fp)
    return out


@router.get("/store/est/ipa/xls-check")
def xls_check(user: models.User = E.VIEW):
    """Read-only: can this server turn an old .xls bill into .xlsx? Runs LibreOffice on a two-cell sheet made
    on the spot (nothing saved) and says what happened - which program, how long, and any error it printed."""
    import getpass, shutil, subprocess, time
    exe = shutil.which("soffice") or shutil.which("libreoffice")
    out = {"soffice": exe or "", "user": getpass.getuser(), "path": os.environ.get("PATH", "")}
    if not exe:
        out["ok"] = False; out["why"] = "LibreOffice is not installed on the server"
        return out
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "t.csv")
        with open(src, "w") as f:
            f.write("a,b\n1,2\n")
        t = time.time()
        try:
            r = subprocess.run([exe, "--headless", "--norestore", f"-env:UserInstallation=file://{d}/lo", "--convert-to", "xlsx",
                                "--outdir", d, src], capture_output=True, timeout=150, env={**os.environ, "HOME": d})
            out.update({"rc": r.returncode, "stdout": r.stdout.decode(errors="ignore")[-400:], "stderr": r.stderr.decode(errors="ignore")[-600:]})
        except Exception as ex:
            out["error"] = f"{type(ex).__name__}: {ex}"
        out["seconds"] = round(time.time() - t, 1)
        out["ok"] = os.path.exists(os.path.join(d, "t.xlsx"))
    return out


@router.post("/store/est/ipa/format")
async def upload_format(project_id: int = Form(...), name: str = Form(""), file: UploadFile = File(None), contract_id: str = Form(""),
                        upload_id: str = Form(""), parts: int = Form(0), filename: str = Form(""),
                        db: Session = Depends(get_db), user: models.User = E.VIEW):
    E._project(db, project_id)
    cid = E._contract_ok(db, project_id, int(contract_id) if str(contract_id).strip().isdigit() else None)
    if file is None:
        if not upload_id:
            raise HTTPException(400, "Pick the Excel bill.")
        data = _joined(user.id, upload_id, parts)

        class _F:                                         # the pieces put back together, named as picked
            pass
        file = _F(); file.filename = filename or "bill.xlsx"
    else:
        data = await file.read()
    if not data:
        raise HTTPException(400, "That file is empty.")
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(400, "That workbook is over 25 MB - remove pictures it does not need and upload it again.")
    try:
        if (file.filename or "").lower().endswith(".xls") or data[:4] == b"\xd0\xcf\x11\xe0":   # old Excel: converted here, kept as .xlsx
            data = BE.xls_to_xlsx(data)
            file.filename = re.sub(r"\.xls$", "", file.filename or "bill", flags=re.I) + ".xlsx"
        model = BE.read_format(data, file.filename or "")
    except BE.BillError as e:
        raise HTTPException(400, str(e))
    chk = BE.check_against_excel(model)
    mp = model["map"]
    if not mp.get("progress"):
        raise HTTPException(400, "No lines with Previous % / Total % were found in this workbook. Upload the bill as sent to the consultant "
                                 "(the sheets with the % of work done).")
    f = EstBillFormat(project_id=project_id, contract_id=cid, name=(name or "").strip()[:120] or re.sub(r"\.xlsx?$", "", file.filename or "Bill format", flags=re.I)[:120],
                      filename=(file.filename or "")[:200], data=data, model=json.dumps(model), checked=json.dumps(chk), created_by=user.id)
    db.add(f)
    db.commit()
    E.M.log_action(db, user.id, "est_bill_format", f"project #{project_id}: bill format {f.filename} ({chk['same']}/{chk['formulas']} formulas as Excel)")
    return {"id": f.id, "formulas": chk["formulas"], "same": chk["same"], "different": chk["different"][:10],
            "lines": sum(len(t["lines"]) for t in mp["progress"]), "sheets": [t["sheet"] for t in mp["progress"]],
            "bill_no": bool(mp.get("bill_no")), "issue_date": bool(mp.get("issue_date")), "total_due": bool(mp.get("total_due")),
            "payments": bool(mp.get("payments"))}


@router.patch("/store/est/ipa/format/{fid}")
def move_format(fid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = E.VIEW):
    """Which contract a bill format (and the bills made on it) belongs to."""
    f = _get(db, EstBillFormat, fid)
    cid = E._contract_ok(db, f.project_id, payload.get("contract_id"))
    f.contract_id = cid
    db.query(EstBill).filter(EstBill.format_id == fid).update({"contract_id": cid}, synchronize_session=False)
    db.commit()
    E.M.log_action(db, user.id, "est_bill_format_moved", f"bill format #{fid} {f.filename} -> contract #{cid}")
    return {"ok": True}


@router.delete("/store/est/ipa/format/{fid}")
def delete_format(fid: int, db: Session = Depends(get_db), user: models.User = E.VIEW):
    f = _get(db, EstBillFormat, fid)
    n = db.query(EstBill).filter(EstBill.format_id == fid).count()
    if n and user.role != "admin":
        raise HTTPException(400, f"{n} bill(s) are made on this format - only an admin can remove it (and they go with it).")
    db.query(EstBill).filter(EstBill.format_id == fid).delete(synchronize_session=False)
    db.delete(f)
    db.commit()
    _MODEL_CACHE.pop(fid, None); _LIST_CACHE.pop(fid, None)
    E.M.log_action(db, user.id, "est_bill_format_removed", f"bill format #{fid} {f.filename}")
    return {"ok": True}


# ---------------------------------------------------------------------------------------------------- the bills

@router.post("/store/est/ipa/new")
def new_bill(payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = E.VIEW):
    """Next month's bill: from the last bill on this format (or the format itself for the first one)."""
    pid = int(payload.get("project_id") or 0)
    E._project(db, pid)
    fid = int(payload.get("format_id") or 0)
    cid = payload.get("contract_id")
    q = db.query(EstBillFormat).filter(EstBillFormat.project_id == pid)
    if cid:
        q = q.filter(EstBillFormat.contract_id == int(cid))
    if fid:
        fmt = _get(db, EstBillFormat, fid)
        last = (db.query(EstBill).filter(EstBill.format_id == fmt.id).order_by(EstBill.seq.desc(), EstBill.id.desc()).first())
    else:
        fmt, last = next_source(db, pid, cid)      # the latest bill - with whatever was added on it
    if not fmt or fmt.project_id != pid:
        raise HTTPException(400, "Upload the bill format for this " + ("contract" if cid else "project") + " first.")
    prev_inputs = _inputs(last) if last else {}
    model = _bill_model(fmt, prev_inputs)
    prev_values = BE.calculate(model, prev_inputs)
    inputs = BE.roll_over(model, prev_inputs, prev_values, E.today())
    model = _bill_model(fmt, inputs)                       # rows the roll-over put in (a heading for this bill's fees)
    inputs, values = _calc(model, inputs)
    seq = (db.query(func.max(EstBill.seq)).filter(EstBill.project_id == pid, *([EstBill.contract_id == fmt.contract_id] if fmt.contract_id else [])).scalar() or 0) + 1
    carried = {}
    for k, v in (_signs(last) if last else {}).items():     # the same people sign next month - each signs afresh
        carried[k] = {"name": v.get("name"), "title": v.get("title"), "step": v.get("step", 1)}
    b = EstBill(project_id=pid, format_id=fmt.id, contract_id=fmt.contract_id, seq=seq, status="Draft", inputs=json.dumps(inputs), created_by=user.id, updated_by=user.id,
                signs=json.dumps(carried) if carried else "")
    _save_totals(b, model, values)
    db.add(b)
    db.commit()
    E.M.log_action(db, user.id, "est_bill_new", f"project #{pid}: bill {b.label} started")
    return {"id": b.id}


def _parse(v):
    if v is None or isinstance(v, (int, float, bool)):
        return v
    s = str(v)
    if s.startswith("="):
        BE.parse_formula(s[1:], "x")              # refused here if it cannot be read
        return s
    return s


@router.put("/store/est/ipa/bill/{bid}")
def save_bill(bid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = E.VIEW):
    """Typed cells changed: {"set": {sheet: {"r,c": value or null (back to the format's)}}, "notes": ...}."""
    b = _get(db, EstBill, bid)
    if b.status == "Paid" and user.role != "admin":
        raise HTTPException(400, "A paid bill cannot be changed.")
    fmt = _get(db, EstBillFormat, b.format_id)
    inputs = _inputs(b)
    model = _bill_model(fmt, inputs)
    names = {s["name"]: s for s in model["sheets"]}
    for sh, cells in (payload.get("set") or {}).items():
        s = names.get(sh)
        if not s:
            raise HTTPException(400, f"No sheet called {sh}.")
        for k, v in (cells or {}).items():
            if not re.match(r"^\d+,\d+$", k):
                raise HTTPException(400, "Bad cell.")
            if not BR.editable(model, s, k, inputs):
                raise HTTPException(400, f"{sh} {k}: that figure is worked out by the sheet - change what it comes from.")
            if v is None:
                inputs.get(sh, {}).pop(k, None)
                continue
            try:
                inputs.setdefault(sh, {})[k] = _parse(v)
            except BE.BillError:
                raise HTTPException(400, f"That formula cannot be read: {v}")
    mp = model.get("map", {})
    if payload.get("issue_date") and mp.get("issue_date"):
        try:
            d = date.fromisoformat(str(payload["issue_date"])[:10])
        except ValueError:
            raise HTTPException(400, "Pick the issue date.")
        x = mp["issue_date"]
        inputs.setdefault(x["sheet"], {})[f"{x['r']},{x['c']}"] = BE.date_input(model, d)
    if payload.get("bill_no") not in (None, "") and mp.get("bill_no"):
        x = mp["bill_no"]
        v = str(payload["bill_no"]).strip()[:40]
        inputs.setdefault(x["sheet"], {})[f"{x['r']},{x['c']}"] = int(v) if v.isdigit() else v
    if isinstance(payload.get("signs"), dict):
        sg = _signs(b)
        places = mp.get("signs", [])
        groups = {g["key"]: g for g in _groups(model)}
        for k, want in payload["signs"].items():
            g = groups.get(k)
            if not g or not isinstance(want, dict):
                continue
            name = str(want.get("name") or "").strip()[:80] or g["orig"]
            title = str(want.get("title") if want.get("title") is not None else g["orig_title"]).strip()[:80]
            prev = sg.get(k) or {}
            if not same_person(prev.get("name") or g["orig"], name):
                prev = {}                                  # another person: they sign afresh
            sg[k] = dict(prev, name=name, title=title, step=_step_of(g["labels"]))
            for pi in g["places"]:                       # the name and designation printed where the format has them
                p = places[pi]
                inputs.setdefault(p["sheet"], {})[f"{p['name']['r']},{p['name']['c']}"] = (p["name"]["prefix"] or "") + name
                if p.get("title") and title:
                    inputs[p["sheet"]][f"{p['title']['r']},{p['title']['c']}"] = title
        b.signs = json.dumps(sg)
    if "notes" in payload:
        b.notes = str(payload.get("notes") or "")[:2000]
    try:
        inputs, values = _calc(model, inputs)
    except HTTPException:
        raise
    except Exception as e:                                  # never a bare "Something went wrong": say what, keep the bill as it was
        import logging
        logging.getLogger("est_bills").exception("bill %s: could not work out", bid)
        raise HTTPException(400, f"That change could not be worked out on the consultant's sheet ({type(e).__name__}). Nothing was saved - please tell the office.")
    b.inputs = json.dumps(inputs)
    b.updated_by = user.id
    _save_totals(b, model, values)
    db.commit()
    users = {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}
    return _bill_out(b, fmt, model, values, inputs, users, _sig_store(db))


@router.post("/store/est/ipa/bill/{bid}/status")
def bill_status(bid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = E.VIEW):
    b = _get(db, EstBill, bid)
    st = str(payload.get("status") or "")
    if st not in STATUSES:
        raise HTTPException(400, "Pick a status.")
    b.status, b.updated_by = st, user.id
    db.commit()
    E.M.log_action(db, user.id, "est_bill_status", f"bill #{bid} {b.label}: {st}")
    return {"ok": True}


@router.delete("/store/est/ipa/bill/{bid}")
def delete_bill(bid: int, db: Session = Depends(get_db), user: models.User = E.VIEW):
    b = _get(db, EstBill, bid)
    if b.status != "Draft" and user.role != "admin":
        raise HTTPException(400, f"A {b.status.lower()} bill can only be removed by an admin.")
    later = db.query(EstBill).filter(EstBill.format_id == b.format_id, EstBill.seq > b.seq).count()
    if later and user.role != "admin":
        raise HTTPException(400, "A later bill was made from this one - remove the later one first.")
    db.delete(b)
    db.commit()
    E.M.log_action(db, user.id, "est_bill_removed", f"bill #{bid} {b.label}")
    return {"ok": True}


@router.post("/store/est/ipa/bill/{bid}/rows")
def add_rows(bid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = E.VIEW):
    """Lines put into a table of the bill, as the office would insert rows in Excel: {"sheet", "at": row, "n": 1}.
    Everything below moves down and every formula follows; the new rows have the ruled look of the row at `at`."""
    b = _get(db, EstBill, bid)
    if b.status == "Paid" and user.role != "admin":
        raise HTTPException(400, "A paid bill cannot be changed.")
    fmt = _get(db, EstBillFormat, b.format_id)
    inputs = _inputs(b)
    model = _bill_model(fmt, inputs)
    sh = str(payload.get("sheet") or "")
    s = next((x for x in model["sheets"] if x["name"] == sh), None)
    at, n = int(payload.get("at") or 0), max(1, min(20, int(payload.get("n") or 1)))
    if not s or not (1 <= at <= s["maxr"] + 1):
        raise HTTPException(400, "Pick where the line goes.")
    like = payload.get("like")
    like = [int(x) for x in like] if isinstance(like, list) else ([int(like)] if like else [])   # the look of each new row
    moved = BE.shift_inputs(inputs.get(sh) or {}, sh, at, n)
    moved.setdefault("_rows", []).append([at, n] + ([like] if like else []))
    inputs[sh] = moved
    # a sub-total typed for this bill's lines grows to take the new rows in
    for t in model["map"].get("fees", []):
        if t["sheet"] == sh and t["head_row"] < at <= t["total_row"]:
            tr, ac = t["total_row"] + n, t["cols"]["amount"]
            k = f"{tr},{ac}"
            if isinstance(moved.get(k), str) and moved[k].upper().startswith("=SUM("):
                m_ = re.match(r"=SUM\(([A-Z]+)(\d+):([A-Z]+)(\d+)\)$", moved[k], re.I)
                if m_:
                    moved[k] = f"=SUM({m_.group(1)}{m_.group(2)}:{m_.group(3)}{tr - 1})"
    model = _bill_model(fmt, inputs)
    inputs, values = _calc(model, inputs)
    b.inputs = json.dumps(inputs); b.updated_by = user.id
    _save_totals(b, model, values)
    db.commit()
    users = {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}
    return _bill_out(b, fmt, model, values, inputs, users, _sig_store(db))


def _table(model, sh):
    t = next((x for x in model.get("map", {}).get("progress", []) if x["sheet"] == sh), None)
    if not t:
        raise HTTPException(400, f"{sh} has no table of lines.")
    return t


def _num_in(v, label):
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return v
    t = str(v).replace(",", "").strip()
    if t.startswith("="):
        try:
            BE.parse_formula(t[1:], "x")
        except BE.BillError:
            raise HTTPException(400, f"{label}: that formula cannot be read.")
        return t
    try:
        return float(t)
    except ValueError:
        raise HTTPException(400, f"{label}: type a number.")


@router.post("/store/est/ipa/bill/{bid}/line")
def add_line(bid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = E.VIEW):
    """A line (a new item, a variation) or a section heading put in to a sheet's table, after row `after`:
    {"sheet", "after", "kind": "line"|"head", "values": {"item", "desc", "unit", "amount", "c5": qty, ...}}.
    A new line takes the row-by-row formulas of the line it is modelled on (Amount = QTY x RATE, this month = Total -
    Previous, the amounts), starts at 0%, and the section's totals take it in. The next bill keeps it."""
    b = _get(db, EstBill, bid)
    if b.status == "Paid" and user.role != "admin":
        raise HTTPException(400, "A paid bill cannot be changed.")
    fmt = _get(db, EstBillFormat, b.format_id)
    inputs = _inputs(b)
    model = _bill_model(fmt, inputs)
    sh = str(payload.get("sheet") or "")
    s = next((x for x in model["sheets"] if x["name"] == sh), None)
    if not s:
        raise HTTPException(400, f"No sheet called {sh}.")
    t = _table(model, sh)
    kind = "head" if payload.get("kind") == "head" else "line"
    vals_in = payload.get("values") or {}
    desc = str(vals_in.get("desc") or "").strip()
    item = str(vals_in.get("item") or "").strip()
    if not (desc or item):
        raise HTTPException(400, "Type the description." if kind == "line" else "Type the section's name.")
    lines = [ln["r"] for ln in t["lines"]]
    after = int(payload.get("after") or (max(lines) if lines else t["head_row"] + 1))
    if not (t["head_row"] <= after <= s["maxr"]):
        raise HTTPException(400, "Pick where it goes.")
    at = after + 1
    if kind == "line":                 # modelled on the nearest line above (or below, at the top of the table)
        above = [r for r in lines if r <= after]
        like = above[-1] if above else (lines[0] if lines else None)
        if like is None:
            raise HTTPException(400, "This table has no line to model the new one on.")
        zero = [c for c in (t["prev_c"], t.get("cur_c"), t["tot_c"]) if c]
        opts = {"kind": "line", "last_c": t.get("last_c") or s["maxc"], "zero": zero}
    else:                              # a heading: the look of the nearest heading above, else of a line
        vals0 = BE.calculate(model, inputs).get(sh, {})
        hs = [h["r"] for h in _heads(model, s, t, vals0, inputs, {}) if h["r"] <= after]
        like = hs[-1] if hs else (max([r for r in lines if r <= after] or lines[:1] or [after]))
        opts = {"kind": "head"}
    moved = BE.shift_inputs(inputs.get(sh) or {}, sh, at, 1)
    moved.setdefault("_rows", []).append([at, 1, [like], opts])
    if kind == "head":
        moved["_heads"] = sorted(set(moved.get("_heads") or []) | {at})
    inputs[sh] = moved
    for osh, inp in list(inputs.items()):             # sub-totals typed for the bill take the new line in too
        if kind != "line" or osh.startswith("_") or not isinstance(inp, dict):
            continue
        for k, v in list(inp.items()):
            if isinstance(v, str) and v.startswith("=") and not k.startswith("_"):
                inp[k] = "=" + BE.grow_ranges(v[1:], osh, sh, at, 1)
    model = _bill_model(fmt, inputs)
    t = _table(model, sh)
    cell = lambda c: f"{at},{c}"
    put = inputs[sh]
    if item and t.get("item_c"):
        put[cell(t["item_c"])] = int(item) if item.isdigit() else item
    if desc and t.get("desc_c"):
        put[cell(t["desc_c"])] = desc
    elif desc and not t.get("desc_c") and t.get("item_c"):
        put[cell(t["item_c"])] = (item + " " + desc).strip()
    if kind == "line":
        unit = str(vals_in.get("unit") or "").strip()
        if unit and t.get("unit_c"):
            put[cell(t["unit_c"])] = unit
        for k, v in vals_in.items():
            m_ = re.fullmatch(r"c(\d+)", str(k))
            c = int(m_.group(1)) if m_ else (t.get("amount_c") if k == "amount" else None)
            if not c:
                continue
            n = _num_in(v, "Amount" if k == "amount" else "The figure")
            if n is None:
                continue
            if not BR.editable(model, next(x for x in model["sheets"] if x["name"] == sh), cell(c), inputs):
                continue                               # worked out by the line's own formula
            put[cell(c)] = n
    inputs, values = _calc(model, inputs)
    b.inputs = json.dumps(inputs); b.updated_by = user.id
    _save_totals(b, model, values)
    db.commit()
    E.M.log_action(db, user.id, "est_bill_line", f"bill #{bid}: {'section' if kind == 'head' else 'line'} added on {sh} row {at} - {(item + ' ' + desc).strip()[:80]}")
    users = {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}
    out = _bill_out(b, fmt, model, values, inputs, users, _sig_store(db))
    out["added_row"] = at
    return out


@router.post("/store/est/ipa/bill/{bid}/line/remove")
def remove_line(bid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = E.VIEW):
    """A line or heading put in on a bill taken out again: {"sheet", "r"}. Not a line billed before (Previous % > 0)."""
    b = _get(db, EstBill, bid)
    if b.status == "Paid" and user.role != "admin":
        raise HTTPException(400, "A paid bill cannot be changed.")
    fmt = _get(db, EstBillFormat, b.format_id)
    inputs = _inputs(b)
    model = _bill_model(fmt, inputs)
    sh, r = str(payload.get("sheet") or ""), int(payload.get("r") or 0)
    values = BE.calculate(model, inputs)
    t = _table(model, sh)
    if any(ln["r"] == r for ln in t["lines"]):
        pv = values.get(sh, {}).get(f"{r},{t['prev_c']}")
        if isinstance(pv, (int, float)) and pv:
            raise HTTPException(400, "This line was billed on an earlier bill - it cannot be taken out. Type 0 or hide it on Sheets.")
    new = BE.drop_added(inputs, sh, r)
    if new is None:
        raise HTTPException(400, "Only a line or section added on the bill can be taken out - the consultant's own lines stay.")
    inputs = new
    model = _bill_model(fmt, inputs)
    inputs, values = _calc(model, inputs)
    b.inputs = json.dumps(inputs); b.updated_by = user.id
    _save_totals(b, model, values)
    db.commit()
    E.M.log_action(db, user.id, "est_bill_line", f"bill #{bid}: row {r} of {sh} taken out")
    users = {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}
    return _bill_out(b, fmt, model, values, inputs, users, _sig_store(db))


@router.post("/store/est/ipa/bill/{bid}/pages")
def bill_pages(bid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = E.VIEW):
    """A page added to the bill - a copy of one of its sheets ({"from", "name"}) - or taken off ({"remove": name}).
    The copy is added after the last sheet; its lines and figures are typed like any sheet's; the next bill keeps it."""
    b = _get(db, EstBill, bid)
    if b.status == "Paid" and user.role != "admin":
        raise HTTPException(400, "A paid bill cannot be changed.")
    fmt = _get(db, EstBillFormat, b.format_id)
    inputs = _inputs(b)
    pages = BE.pages_of(inputs)
    if payload.get("remove"):
        nm = str(payload["remove"])
        if not any(x["name"] == nm for x in pages):
            raise HTTPException(400, "Only a page added on the bill can be taken off.")
        pages = [x for x in pages if x["name"] != nm]
        inputs.pop(nm, None)
        what = f"page {nm} taken off"
    else:
        model = _bill_model(fmt, inputs)
        src = str(payload.get("from") or "")
        if not any(x["name"] == src for x in model["sheets"]):
            raise HTTPException(400, "Pick the sheet to copy.")
        src = next((x.get("page_of") or x["name"]) for x in model["sheets"] if x["name"] == src)   # a copy of a copy: of the sheet itself
        nm = " ".join(str(payload.get("name") or "").split())[:31]
        if not nm:
            raise HTTPException(400, "Give the new page a name.")
        if BE.PAGE_BAD.search(nm) or nm.startswith("'") or nm.endswith("'"):
            raise HTTPException(400, "A page name cannot have [ ] : * ? / \\ in it.")
        if any(x["name"].lower() == nm.lower() for x in model["sheets"]):
            raise HTTPException(400, f"There is a page called {nm} already.")
        pages.append({"name": nm, "from": src})
        what = f"page {nm} added (a copy of {src})"
    inputs["_pages"] = {"list": pages}
    if not pages:
        inputs.pop("_pages", None)
    model = _bill_model(fmt, inputs)
    inputs, values = _calc(model, inputs)
    b.inputs = json.dumps(inputs); b.updated_by = user.id
    _save_totals(b, model, values)
    db.commit()
    E.M.log_action(db, user.id, "est_bill_page", f"bill #{bid}: {what}")
    users = {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}
    return _bill_out(b, fmt, model, values, inputs, users, _sig_store(db))


@router.post("/store/est/ipa/bill/{bid}/hide")
def hide_rows(bid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = E.VIEW):
    """Rows of a table hidden on this bill (kept in the file, not printed) or shown again: {"sheet", "rows": [..], "show": bool}."""
    b = _get(db, EstBill, bid)
    fmt = _get(db, EstBillFormat, b.format_id)
    inputs = _inputs(b)
    sh = str(payload.get("sheet") or "")
    inp = inputs.setdefault(sh, {})
    cur = set(int(x) for x in inp.get("_hide") or [])
    rows = set(int(x) for x in payload.get("rows") or [])
    inp["_hide"] = [] if (payload.get("show") and payload.get("all")) else sorted((cur - rows) if payload.get("show") else (cur | rows))
    model = _bill_model(fmt, inputs)
    inputs, values = _calc(model, inputs)
    b.inputs = json.dumps(inputs); b.updated_by = user.id
    _save_totals(b, model, values)
    db.commit()
    users = {u.id: (u.full_name or u.username) for u in db.query(models.User).all()}
    return _bill_out(b, fmt, model, values, inputs, users, _sig_store(db))


# ---------------------------------------------------------------------------------------------------- the chain of approval

@router.post("/store/est/ipa/bill/{bid}/sign")
def sign_bill(bid: int, payload: dict = Body(...), db: Session = Depends(get_db), user: models.User = E.VIEW):
    """The person whose turn it is signs: Prepared by first, then Checked by, then Approved by. Only then does their
    signature print. {"key": signer key, "undo": true to take a signing back}."""
    b = _get(db, EstBill, bid)
    fmt = _get(db, EstBillFormat, b.format_id)
    model = _bill_model(fmt, b)
    store = _sig_store(db)
    signers = _signers_out(b, model, store)
    x = next((y for y in signers if y["key"] == payload.get("key")), None)
    if not x:
        raise HTTPException(400, "Pick who is signing.")
    sg = _signs(b)
    cur = dict(sg.get(x["key"]) or {})
    cur.setdefault("name", x["name"]); cur.setdefault("title", x["title"]); cur["step"] = x["step"]
    if payload.get("undo"):
        if not (user.role == "admin" or same_person(cur.get("signed_by_name") or "", user.full_name or "") or can_sign(user, x)):
            raise HTTPException(403, "Only the person who signed (or an admin) can take it back.")
        cur.pop("signed_at", None); cur.pop("signed_by", None); cur.pop("signed_by_name", None)
        later = [y for y in signers if y["step"] > x["step"] and y["signed_at"]]
        for y in later:                                   # the ones after them sign again
            c2 = dict(sg.get(y["key"]) or {}); c2.pop("signed_at", None); c2.pop("signed_by", None); c2.pop("signed_by_name", None); sg[y["key"]] = c2
        sg[x["key"]] = cur
        b.signs = json.dumps(sg)
        b.status = "Draft" if not any((sg.get(y["key"]) or {}).get("signed_at") for y in signers if y["step"] > 0) else "Awaiting approval"
        db.commit()
        E.M.log_action(db, user.id, "est_bill_unsign", f"bill #{bid} {b.label}: {x['labels'][0]} {x['name']} taken back")
        return get_bill(bid, db, user)
    if x["signed_at"]:
        raise HTTPException(400, f"{x['name']} has already signed.")
    if not x["turn"]:
        waiting = next((y for y in signers if not y["signed_at"]), None)
        raise HTTPException(400, f"Not yet - {waiting['name']} ({waiting['labels'][0]}) signs first." if waiting else "Nothing to sign.")
    if not can_sign(user, x):
        raise HTTPException(403, f"Only {x['name']} can sign here (the login's full name must match), or an admin.")
    cur.update({"signed_at": E.today().isoformat(), "signed_by": user.id, "signed_by_name": user.full_name or user.username})
    sg[x["key"]] = cur
    for i, y in enumerate(signers):                       # everyone in the chain kept with the bill, in order (for the bell)
        d = dict(sg.get(y["key"]) or {})
        d.setdefault("name", y["name"]); d.setdefault("title", y["title"]); d["step"] = y["step"]; d["ord"] = i
        sg[y["key"]] = d
    b.signs = json.dumps(sg)
    b.updated_by = user.id
    rest = [y for y in signers if y["key"] != x["key"] and not y["signed_at"]]
    if not rest:
        b.status = "Approved" if b.status in ("Draft", "Awaiting approval") else b.status
    elif b.status == "Draft":
        b.status = "Awaiting approval"
    db.commit()
    E.M.log_action(db, user.id, "est_bill_sign", f"bill #{bid} {b.label}: {x['labels'][0]} {x['name']}")
    out = get_bill(bid, db, user)
    nxt = next((y for y in out["signers"] if y["turn"]), None)
    out["next"] = {"name": nxt["name"], "label": nxt["labels"][0], "has_login": bool(_user_for(db, nxt["name"]))} if nxt else None
    out["warn"] = "" if (x["sig"] or x["format_has"]) else f"No signature picture for {x['name']} on file - the name prints without one until it is uploaded (Cover & details)."
    return out


# ---------------------------------------------------------------------------------------------------- signatures

@router.get("/store/est/ipa/people")
def bill_people(db: Session = Depends(get_db), user: models.User = E.VIEW):
    """Who can sign a bill: the office staff in the staff register, with their designation, and whether they have a
    login (so the bill can reach their bell) and a signature on file."""
    store = _sig_store(db)
    logins = db.query(models.User).filter(models.User.active == True).all()  # noqa: E712
    out = []
    for p in staff_people(db):
        u = next((x for x in logins if same_person(x.full_name or "", p["name"]) or same_person(x.username or "", p["name"])), None)
        out.append(dict(p, login=u.username if u else "", has_sig=bool(_sig_for(store, p["name"]))))
    return {"people": out}


@router.get("/store/est/ipa/signatures")
def list_signatures(db: Session = Depends(get_db), user: models.User = E.VIEW):
    return {"people": [{"id": x.id, "name": x.name, "title": x.title or "", "sig": _png_url(x.png)}
                       for x in db.query(EstSignature).order_by(EstSignature.name).all()]}


def clean_signature(data):
    """A photo or scan of a signature -> a PNG with the paper made see-through, cropped to the ink."""
    from PIL import Image, ImageOps
    try:
        im = Image.open(io.BytesIO(data))
        im = ImageOps.exif_transpose(im).convert("RGBA")
    except Exception:
        raise HTTPException(400, "That is not a picture - upload a photo or scan of the signature (PNG or JPG).")
    im.thumbnail((1400, 1400))
    px = im.load()
    W, H = im.size
    # paper: anything light and grey-ish goes; ink (dark or coloured) stays
    for y in range(H):
        for x in range(W):
            r, g, b_, a = px[x, y]
            light = (r + g + b_) / 3
            sat = max(r, g, b_) - min(r, g, b_)
            if a < 30 or (light > 175 and sat < 60):
                px[x, y] = (255, 255, 255, 0)
    box = im.getbbox()
    if not box:
        raise HTTPException(400, "No signature could be seen in that picture - sign on white paper, dark pen, and try again.")
    im = im.crop(box)
    pad = 6
    out = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (255, 255, 255, 0))
    out.paste(im, (pad, pad), im)
    if out.height > 220:
        out = out.resize((int(out.width * 220 / out.height), 220))
    buf = io.BytesIO()
    out.save(buf, "PNG", optimize=True)
    return buf.getvalue()


@router.post("/store/est/ipa/signature")
async def upload_signature(name: str = Form(...), title: str = Form(""), file: UploadFile = File(...),
                           db: Session = Depends(get_db), user: models.User = E.VIEW):
    name = (name or "").strip()[:80]
    if not name:
        raise HTTPException(400, "Type the person's full name.")
    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(400, "That picture is over 8 MB.")
    png = clean_signature(data)
    x = next((y for y in db.query(EstSignature).all() if same_person(y.name, name)), None)
    if not x:
        x = EstSignature(name=name)
        db.add(x)
    x.name, x.png, x.updated_by = name, png, user.id
    if title.strip():
        x.title = title.strip()[:80]
    db.commit()
    E.M.log_action(db, user.id, "est_signature", f"signature for {name}")
    return {"id": x.id, "name": x.name, "title": x.title or "", "sig": _png_url(png)}


@router.delete("/store/est/ipa/signature/{sid}")
def delete_signature(sid: int, db: Session = Depends(get_db), user: models.User = E.VIEW):
    x = db.query(EstSignature).get(sid)
    if not x:
        raise HTTPException(404, "Not there any more.")
    db.delete(x); db.commit()
    E.M.log_action(db, user.id, "est_signature_removed", f"signature for {x.name}")
    return {"ok": True}


# ---------------------------------------------------------------------------------------------------- out

@router.get("/export/est/ipa/format/{fid}")
def export_format(fid: int, token: str, format: str = "preview", embed: int = 0, db: Session = Depends(get_db)):
    """A previous bill as uploaded: the workbook itself (Excel), printed as a bill (PDF), or the preview."""
    u = auth.get_download_user_from_token(token, db)
    if E.RIGHT not in set(E.M.effective_permissions(u)) and u.role != "admin":
        raise HTTPException(403, "Estimation only.")
    fmt = _get(db, EstBillFormat, fid)
    p = db.query(E.EstProject).get(fmt.project_id)
    no = _fmt_no(None, fmt.filename)
    stem = re.sub(r"\.xls[xm]?$", "", fmt.filename or "", flags=re.I) or f"{p.code if p else ''}_IPA_{no[1] or no[0]}"
    fname = re.sub(r"[^A-Za-z0-9]+", "_", stem).strip("_")
    if format == "excel":
        return StreamingResponse(io.BytesIO(fmt.data or b""), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 headers={"Content-Disposition": f"attachment; filename={fname}.xlsx"})
    model = _model(fmt)
    values = BE.calculate(model, {})
    title = f"{p.code if p else ''} - {stem}"
    if format == "pdf":
        buf = BR.render_pdf(model, values, title, {}, fname=fname + ".xlsx")
        return StreamingResponse(buf, media_type="application/pdf", headers={"Content-Disposition": f"inline; filename={fname}.pdf"})
    base = f"/export/est/ipa/format/{fid}?token={token}"
    return HTMLResponse(BR.preview_html(model, values, title, base + "&format=pdf", base + "&format=excel", {}, embed=bool(embed), fname=fname + ".xlsx"))


@router.get("/export/est/ipa/{bid}")
def export_bill(bid: int, token: str, format: str = "preview", embed: int = 0, db: Session = Depends(get_db)):
    u = auth.get_download_user_from_token(token, db)
    if E.RIGHT not in set(E.M.effective_permissions(u)) and u.role != "admin":
        raise HTTPException(403, "Estimation only.")
    b = _get(db, EstBill, bid)
    fmt = _get(db, EstBillFormat, b.format_id)
    inputs = _inputs(b)
    model = _bill_model(fmt, inputs)
    values = BE.calculate(model, inputs)
    p = db.query(E.EstProject).get(b.project_id)
    code = p.code if p else ""
    label = b.label or str(b.seq)
    title = f"{code} - IPA {label}" + (f" - {b.issue_date:%d %b %Y}" if b.issue_date else "")
    fname = re.sub(r"[^A-Za-z0-9]+", "_", f"{code}_IPA_{label}").strip("_")
    store = _sig_store(db)
    if format == "excel":
        data = BE.write_xlsx(BE.add_pages_xlsx(fmt.data, inputs), model, inputs, values, sign_images(model, _signs(b), store))
        return StreamingResponse(io.BytesIO(data), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 headers={"Content-Disposition": f"attachment; filename={fname}.xlsx"})
    if format == "pdf":
        buf = BR.render_pdf(signed_model(model, _signs(b), store), values, title, inputs, fname=fname + ".xlsx")
        return StreamingResponse(buf, media_type="application/pdf", headers={"Content-Disposition": f"inline; filename={fname}.pdf"})
    base = f"/export/est/ipa/{bid}?token={token}"
    return HTMLResponse(BR.preview_html(signed_model(model, _signs(b), store), values, title, base + "&format=pdf", base + "&format=excel", inputs, embed=bool(embed), fname=fname + ".xlsx"))

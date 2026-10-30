"""Read a subcontractor's item schedule out of an Excel workbook - the agreement BOQ or any of
its payment certificates (Appendix A / the Bill sheets) - into schedule lines.

The file is read in memory and never kept. Every sheet with a heading row that has a
Description column and an amount / rate column is read:

  * 908 / 909 MEP:  "Bill No | Description | Approx. Qty | Unit | Rate | Amount | Previous % |
                     Current % | Total % Work Done | Certified Amount | Remarks"   (one sheet per bill)
  * 915 civil:      "Bill No | Description | Estimated Quantity | Quantity Claimed | Quantity of
                     Work Done at Site | Unit | Rate | Certified Amount | Remarks"
  * 911 finishes:   "Bill No | Description | Estimated Quantity | SC Claimed Qty | Certified Qty |
                     % of work completed | Unit | SC Rate | Certified Amount ..."

Lump sums (Rate "LS", an Amount) are measured by % done; lines with a quantity and a rate and a
certified quantity are measured by quantity. An amount written in words ("Included", "Excluded",
"NA") is kept on the line with no money. A line in capitals with no figures is a heading; a
sentence with no figures introduces the lettered lines under it ("a. M.D.B ...").

Every sheet is checked against its own total row ("Total To-date carried over ..."): the contract
amount and, where the file is a certificate, the certified amount to date.
"""
import io
import re

import openpyxl


def _s(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return re.sub(r"\s+", " ", str(v)).strip()


def _n(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).replace(",", "").replace("AED", "").strip()
    if t.endswith("%"):
        try:
            return float(t[:-1]) / 100.0
        except ValueError:
            return None
    try:
        return float(t)
    except ValueError:
        return None


def _key(t):
    return re.sub(r"[^a-z% ]", "", _s(t).lower().replace("\n", " ")).strip()


def _header(row):
    """Column positions from a heading row, or None if this row is not one."""
    cols = {}
    for i, v in enumerate(row):
        k = _key(v)
        if not k:
            continue
        if "description" in k and "desc" not in cols:
            cols["desc"] = i
        elif k in ("bill no", "item", "item no", "sr no", "sno", "sl no", "no", "ref", "bill") and "no" not in cols:
            cols["no"] = i
        elif ("certified amount" in k or "amount certified" in k) and "cert_amt" not in cols:
            cols["cert_amt"] = i
        elif "claimed from client" in k or "received from client" in k or "amount claimed" in k:
            continue
        elif k in ("amount", "amount aed", "total amount", "contract amount") and "amount" not in cols:
            cols["amount"] = i
        elif "rate" in k and "rate" not in cols:
            cols["rate"] = i
        elif k == "unit" and "unit" not in cols:
            cols["unit"] = i
        elif ("certified qty" in k or "work done at" in k or "quantity done" in k) and "cert_qty" not in cols:
            cols["cert_qty"] = i
        elif "claimed" in k and ("qty" in k or "quantity" in k) and "claim_qty" not in cols:
            cols["claim_qty"] = i
        elif ("estimated" in k or "approx" in k or k in ("qty", "quantity")) and "qty" not in cols:
            cols["qty"] = i
        elif "previous" in k and "%" in k:
            cols["prev_pct"] = i
        elif "current" in k and "%" in k:
            cols["cur_pct"] = i
        elif ("% work done" in k or "% of work" in k or "total %" in k) and "pct" not in cols:
            cols["pct"] = i
        elif "remark" in k and "remark" not in cols:
            cols["remark"] = i
        elif k == "appendix":
            cols["appendix"] = i
    if "desc" not in cols or not ({"amount", "rate"} & set(cols)):
        return None
    if "appendix" in cols:          # a summary of the bills (909 Appendix A), not a schedule
        return None
    return cols


LETTERED = re.compile(r"^\(?([a-z]|[ivx]{1,5})[.)]\s+", re.I)
WORDS_ZERO = ("-", "--", "0", "nil")


def read_schedule(data: bytes):
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    items, sheets, notes = [], [], []
    for ws in wb.worksheets:
        if ws.sheet_state != "visible":
            continue
        rows = [list(r) + [None] * 6 for r in ws.iter_rows(values_only=True)]
        hi, cols = None, None
        for i, r in enumerate(rows[:40]):
            c = _header(r)
            if c:
                hi, cols = i, c
                break
        if cols is None:
            continue
        # the % column is read one way for the whole column: written as whole numbers (if any figure is over 1:
        # 1 = 1%, 50 = 50%) or as fractions (0.5 = 50%) - never 1 = 100% in one row and 50 = 50% in the next
        pct_whole = "pct" in cols and any((_n(r[cols["pct"]]) or 0) > 1.0000001 for r in rows[hi + 1:])
        as_pct = lambda p_: p_ if pct_whole else p_ * 100
        # bill: "Appendix - B1" above the heading, its title the text line after it
        bill, title = "", ""
        for r in rows[:hi]:
            for v in r:
                t = _s(v)
                m = re.match(r"^appendix\s*-?\s*([A-Z]\d*)$", t, re.I)
                if m:
                    bill = m.group(1).upper()
                elif t and not title and bill and not re.match(r"^(value of work|payment certificate|date)", t, re.I) and len(t) < 80:
                    title = t.title() if t.isupper() else t
        if not bill:
            m = re.match(r"^bill\s*(\d+)\s*-?\s*(.*)$", ws.title, re.I)
            if m:
                bill, title = "B" + m.group(1), title or m.group(2).strip()
        top, section, parent, mine, skipped = "", "", "", [], 0
        NUMBERED = re.compile(r"^\(?\d{1,2}\s*[.)]\s+")
        total_row = None
        is_qty = "cert_qty" in cols
        for r in rows[hi + 1:]:
            no = _s(r[cols["no"]]) if "no" in cols else ""
            desc = _s(r[cols["desc"]])
            rowtext = " ".join(_s(x) for x in r[:12]).lower()
            if re.search(r"\btotal\b", rowtext) and not (desc and _n(r[cols["rate"]]) if "rate" in cols else False):
                if any(_n(r[cols[k]]) for k in ("amount", "cert_amt") if k in cols):
                    total_row = r
                if mine:
                    parent = ""
                continue
            if re.match(r"^(m/?s\.?\s*)?(sub ?-?contractor|contractor)\s*:|^date\s*:", rowtext.strip()):
                break                                   # the signature block
            if not desc and total_row is None and mine and any(_n(r[cols[k]]) for k in ("amount", "cert_amt") if k in cols) \
                    and not any(_s(r[cols[k]]) for k in ("no", "unit", "rate", "qty") if k in cols):
                total_row = r                           # a total with no words beside it (911)
                continue
            if not desc:
                continue
            qty = _n(r[cols["qty"]]) if "qty" in cols else None
            unit = _s(r[cols["unit"]]) if "unit" in cols else ""
            rate_raw = r[cols["rate"]] if "rate" in cols else None
            rate = _n(rate_raw)
            amt_raw = r[cols["amount"]] if "amount" in cols else None
            amt = _n(amt_raw)
            words = "" if amt is not None or amt_raw is None else _s(amt_raw)
            if words.lower() in WORDS_ZERO:
                words = ""
            cert_qty = _n(r[cols["cert_qty"]]) if "cert_qty" in cols else None
            pct = _n(r[cols["pct"]]) if "pct" in cols else None
            cert_amt = _n(r[cols["cert_amt"]]) if "cert_amt" in cols else None
            remark = _s(r[cols["remark"]]) if "remark" in cols else ""
            priced = bool(amt) or bool(qty and rate) or (is_qty and bool(qty or rate))
            if not priced and not words:
                if not (qty or rate or unit or cert_amt):
                    head = f"{no} {desc}".strip() if no and len(no) <= 3 else desc
                    if NUMBERED.match(desc) and len(desc) <= 60:
                        section, parent = head, ""             # "10) TELEPHONE SYSTEM:", "17) Any Other Items"
                    elif desc.upper() == desc and len(desc) < 120:
                        top = section = head                   # "9 ELECTRICAL WORKS", "BOOSTER SET"
                        parent = ""
                    else:
                        parent = desc
                else:
                    skipped += 1
                continue
            if NUMBERED.match(desc) and section != top:
                section = top                                  # "11) ..." is back at the bill's own level
            if parent and LETTERED.match(desc):
                p = parent if len(parent) <= 90 else parent[:87].rsplit(" ", 1)[0] + "..."
                desc = f"{p} - {desc}"
            elif not LETTERED.match(desc):
                parent = ""
            ls = isinstance(rate_raw, str) and rate_raw.strip().upper() in ("LS", "L.S", "L.S.", "LUMPSUM", "LUMP SUM")
            measure = "qty" if (is_qty and (rate or qty) and not ls and not amt) else "pct"
            amount = round(amt, 2) if amt else (round((qty or 0) * (rate or 0), 2) if (qty and rate) else 0.0)
            done_pct = None
            if measure == "pct":
                if pct is not None:
                    done_pct = round(as_pct(pct), 4)
                elif cert_amt is not None and amount:
                    done_pct = round(100 * cert_amt / amount, 4)
            mine.append({"bill": bill, "bill_title": title[:120], "section": section[:200], "no": no[:20], "description": desc[:2000],
                         "qty": round(qty or 0, 4) if not (isinstance(r[cols["qty"]], str) if "qty" in cols else False) else 0.0,
                         "unit": ("LS" if ls and not unit else unit)[:20], "rate": round(rate or 0, 4), "amount": amount,
                         "measure": measure, "words": words[:60], "remark": remark[:200],
                         "done_pct": done_pct, "done_qty": round(cert_qty, 4) if (measure == "qty" and cert_qty is not None) else None,
                         "claimed_qty": round(_n(r[cols["claim_qty"]]) or 0, 4) if "claim_qty" in cols else None,
                         "certified": round(cert_amt, 2) if cert_amt is not None else None,
                         "stage_pct": round(as_pct(pct), 4) if (measure == "qty" and pct) else None,
                         "rate_missing": bool(qty) and not rate and not amt and not words})
        if not mine:
            continue
        contract = round(sum(x["amount"] for x in mine), 2)
        certified = round(sum(x["certified"] or 0 for x in mine), 2)
        chk = {}
        if total_row is not None:
            t_amt = _n(total_row[cols["amount"]]) if "amount" in cols else None
            t_cert = _n(total_row[cols["cert_amt"]]) if "cert_amt" in cols else None
            if t_amt is not None:
                chk["contract"] = (round(t_amt, 2), abs(round(t_amt, 2) - contract) < 0.01)
            if t_cert is not None:
                chk["certified"] = (round(t_cert, 2), abs(round(t_cert, 2) - certified) < 0.01)
        for k, (v, ok) in chk.items():
            if not ok:
                notes.append(f"{ws.title}: lines add up to {contract if k == 'contract' else certified:,.2f}, the sheet's total row says {v:,.2f} ({k})")
        # every line: its % / quantity done x its amount / rate must give the certified figure printed beside it
        off = []
        for x in mine:
            if x["certified"] is None:
                continue
            calc = (x["amount"] * (x["done_pct"] or 0) / 100.0) if x["measure"] == "pct" else \
                ((x["done_qty"] or 0) * x["rate"] * ((x["stage_pct"] / 100.0) if x.get("stage_pct") else 1.0))
            if abs(round(calc, 2) - x["certified"]) > 0.01:
                off.append(f"{x['no'] or x['description'][:30]} ({calc:,.2f} v {x['certified']:,.2f})")
        if off:
            notes.append(f"{ws.title}: {len(off)} line(s) where done x amount is not the certified figure: {', '.join(off[:4])}")
            chk["lines"] = (len(off), False)
        missing = [x["description"][:50] for x in mine if x["rate_missing"]]
        if missing:
            notes.append(f"{ws.title}: {len(missing)} line(s) have a quantity but no rate - type the rate after bringing them in ({', '.join(missing[:4])}{'...' if len(missing) > 4 else ''})")
        sheets.append({"sheet": ws.title, "bill": bill, "title": title, "lines": len(mine), "contract": contract, "certified": certified,
                       "check": {k: {"sheet": v, "ok": ok} for k, (v, ok) in chk.items()}, "unpriced": skipped})
        items += mine
    if not items:
        raise ValueError("No schedule lines found. Upload the agreement BOQ or a payment certificate with its Appendix / Bill sheets "
                         "(a heading row with Description and Amount or Rate).")
    # one sheet per bill (908) or one sheet only (915, 911): a single unnamed bill needs no bill code
    if len({x["bill"] for x in items}) == 1 and len(sheets) == 1:
        for x in items:
            x["bill"] = x["bill"] if x["bill"] not in ("A",) else ""
    return {"items": items, "sheets": sheets, "notes": notes,
            "contract": round(sum(x["amount"] for x in items), 2),
            "certified": round(sum(x["certified"] or 0 for x in items), 2),
            "all_checked": all(c["ok"] for s in sheets for c in s["check"].values()) and all(s["check"] for s in sheets)}

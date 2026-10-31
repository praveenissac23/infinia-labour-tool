"""Estimation uploads read on the server, from the file itself (app/docread: no AI, nothing downloaded, nothing kept).

The browser sends the file (in pieces when it is big - the same pieces as the bill formats, estimation.upload_data);
it is read in memory here and dropped. Every reading comes back with, per field, its value, a status for the
confirm screen - ok (tied to the document's own sums) / check (look at it) / derived (worked out from the others) -
and where it was found (Sheet!E14, or page + box), plus the document's sums, passed or failed.

The older readers (est_prevread, est_docread, est_agreement, est_voimport) still run beside it, on the same text:
whatever they find that the new reader did not is added for checking, and where the two readings differ the field is
marked check with the other reading in its note. When the server has no PDF / OCR packages, the file is read on the
computer instead (the browser's text, as before) - the reply says so with a clear message (Unavailable).

Memory: the server has about 1 GB, so one file is read at a time (DOCREAD_JOBS) and scanned pages one at a time
(DOCREAD_PARALLEL, default 1).
"""
import os
import re
import shutil
import threading
from datetime import date

from fastapi import HTTPException

os.environ.setdefault("DOCREAD_PARALLEL", "1")

OCR_MSG = "Scanned files need the OCR package installed on the server (tesseract-ocr) - this one is read on this computer instead."
PDF_MSG = "PDF files need the PDF package installed on the server (pdfplumber) - this one is read on this computer instead."
DOCX_MSG = "Word files need the Word package installed on the server (python-docx) - this one is read on this computer instead."

_JOBS = threading.BoundedSemaphore(max(1, int(os.environ.get("DOCREAD_JOBS", "1") or 1)))
_CAPS = None


class Unavailable(Exception):
    """This server cannot read this file itself (a package is missing) - the browser reads it instead."""


def caps(refresh=False):
    """What this server can read: pdf (pdfplumber), docx (python-docx), ocr (tesseract + numpy + Pillow)."""
    global _CAPS
    if _CAPS is not None and not refresh:
        return _CAPS
    c = {}
    try:
        import pdfplumber  # noqa: F401
        c["pdf"] = True
    except Exception:
        c["pdf"] = False
    try:
        import docx  # noqa: F401
        c["docx"] = True
    except Exception:
        c["docx"] = False
    try:
        import numpy  # noqa: F401
        from PIL import Image  # noqa: F401
        c["ocr"] = shutil.which(os.environ.get("DOCREAD_TESSERACT", "tesseract")) is not None
    except Exception:
        c["ocr"] = False
    c["render"] = shutil.which("pdftoppm") is not None
    _CAPS = c
    return c


def load_doc(data, name):
    """The file -> docread's layout model, or Unavailable when a package it needs is missing here."""
    from docread.load import load, sniff
    k = sniff(data, name)
    c = caps()
    if k == "pdf" and not c["pdf"]:
        raise Unavailable(PDF_MSG)
    if k == "image" and not c["ocr"]:
        raise Unavailable(OCR_MSG)
    if k == "docx" and not c["docx"]:
        raise Unavailable(DOCX_MSG)
    if k not in ("pdf", "xls", "xlsx", "xlsm", "docx", "image"):
        if k == "doc":
            raise HTTPException(400, "Old .doc files cannot be read - save it as .docx (Word: File > Save As) or PDF.")
        raise HTTPException(400, "Choose a PDF, Word (.docx), Excel file or a photo.")
    with _JOBS:
        try:
            doc = load(data, name, ocr=c["ocr"])
        except (Unavailable, HTTPException):
            raise
        except ImportError as e:
            raise Unavailable(OCR_MSG if any(x in str(e) for x in ("numpy", "PIL")) else PDF_MSG)
        except Exception as e:
            raise HTTPException(400, f"That file could not be opened ({str(e)[:120] or 'unreadable'}).")
    if k == "pdf" and not c["ocr"] and any(r.kind == "scan" and not r.rows for r in doc.regions):
        raise Unavailable(OCR_MSG)
    return doc


def pages_of(doc):
    """Each page / sheet: its size in the units of the boxes (points), for the confirm screen's highlight."""
    return [{"page": r.page, "name": r.name, "kind": r.kind, "w": round(r.width or 0, 1), "h": round(r.height or 0, 1)} for r in doc.regions]


# ---- the older readers, run on the same text --------------------------------------------------------------------

def old_read(kind, lines, subs=None):
    """The reading est_docread's /store/est/read/<kind> has always given for these lines (the browser's text)."""
    import est_agreement as A
    import est_docread as R
    if kind in ("ipa", "subpc"):
        import est_prevread as P
        lines = P._join_ocr(lines)
    cl = A.clean_lines(lines)
    flat = R._flat(cl)
    if kind == "subpc":
        return R.READERS["subpc"](cl, flat, subs or [])
    if kind == "invoice":
        return R.read_invoice(cl, flat, subs or [])
    return R.READERS[kind](cl, flat)


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _same(a, b):
    if _num(a) and _num(b):
        return abs(float(a) - float(b)) <= 0.011
    return re.sub(r"[^a-z0-9]", "", str(a).lower()) == re.sub(r"[^a-z0-9]", "", str(b).lower())


def _fmt(v):
    if _num(v):
        return f"{float(v):,.2f}"
    if isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        return f"{v[8:10]}/{v[5:7]}/{v[:4]}"
    return str(v)


def _failed(r):
    cs = r.get("checks")
    return sum(1 for c in cs if not c.get("ok")) if isinstance(cs, list) else 0


def combine(new, old, prefer_old_text=False):
    """The new reading, with the older reader's findings: a field only the old one found is added for checking;
    where they differ the field is marked check and its note gives the other reading. Text fields keep the older
    reader's value when prefer_old_text (the agreement's name, terms ... as the team's own reader gives them)."""
    if not old:
        return new
    f, det = new.setdefault("fields", {}), new.setdefault("detail", {})
    found = new.setdefault("found", [])
    for k, v in (old.get("fields") or {}).items():
        if v in (None, "") or isinstance(v, (list, dict)):
            continue
        mine = f.get(k)
        if mine in (None, ""):
            f[k] = v
            det[k] = {"value": v, "confidence": 0.5, "status": "check", "where": None, "note": "found by the older reader only - not tied to the document's sums"}
            continue
        if isinstance(mine, (list, dict)) or _same(mine, v):
            continue
        d = det.get(k) or {}
        if _num(mine) and d.get("status") in ("ok", "derived"):
            d.setdefault("note", f"the older reader read {_fmt(v)}")
            det[k] = d
            continue
        if prefer_old_text and not _num(mine):
            f[k] = v
            det[k] = {"value": v, "confidence": 0.5, "status": "check", "where": d.get("where"), "note": f"the two readings differ - also read as {_fmt(mine)}"}
            continue
        det[k] = dict(d, value=mine, status="check", confidence=min(0.5, d.get("confidence", 0.5)), note=f"the two readings differ - also read as {_fmt(v)}")
    for n in old.get("found") or []:
        if n not in found:
            found.append(n)
    # the older reader's notes are about what IT could not find - not repeated beside the new reading
    return new


def finish(r, doc=None):
    """Every field read gets a detail (no detail: check); the list of fields to look at; pages for the preview."""
    f, det = r.setdefault("fields", {}), r.setdefault("detail", {})
    for k, v in f.items():
        if v in (None, "") or isinstance(v, (list, dict)):
            continue
        if k not in det or not isinstance(det[k], dict):
            det[k] = {"value": v, "confidence": 0.6, "status": "check", "where": None}
    for k in list(det):
        if k not in f or det[k] is None:
            det.pop(k, None)
    r["flagged"] = sorted(k for k, d in det.items() if d.get("status") == "check")
    cs = r.get("checks")
    r["sums"] = [{"name": c.get("name", ""), "ok": bool(c.get("ok")), "detail": c.get("detail", "")} for c in cs] if isinstance(cs, list) else r.get("sums", [])
    if doc is not None:
        r["pages"] = pages_of(doc)
        r["doc_kind"] = doc.kind
    return r


def _best(new, old):
    """The older reader as the main reading when the new one keeps fewer of the document's sums (or found nothing)."""
    nf = sum(1 for v in (new.get("fields") or {}).values() if v not in (None, ""))
    of = sum(1 for v in (old.get("fields") or {}).values() if v not in (None, "")) if old else 0
    if old and (nf == 0 or (_failed(new) > _failed(old) and of >= nf)):
        main = dict(old)
        main["detail"] = {}
        main["engine"] = "older reader"
        return combine(main, {"fields": new.get("fields"), "found": new.get("found"), "notes": new.get("notes")})
    return combine(new, old)


# ---- the readings -----------------------------------------------------------------------------------------------

def old_lines(data, name, doc):
    """The text the older readers are used to: the browser's own lines for Excel, Word and a typed PDF (emulated
    exactly, cheap); for a scan or photo the server's recognised lines (never recognised twice)."""
    from docread.legacy import browser_lines, to_lines
    if doc.kind in ("xlsx", "xls", "docx") or (doc.kind == "pdf" and not doc.ocr_pages):
        try:
            return browser_lines(data, name)
        except Exception:
            pass
    return to_lines(doc)


DOC_KINDS = ("ipa", "subpc", "clientpc", "project")


def read_doc_kind(kind, data=None, name="", lines=None, subs=None):
    """A bill / certificate / contract: the file (data, name) or the browser's lines -> one reading for the form."""
    from docread import read_doc
    from docread.other import from_lines
    doc = None
    if data is not None:
        doc = load_doc(data, name)
        lines = old_lines(data, name, doc)
    else:
        doc = from_lines(lines or [], name)
    try:
        new = read_doc(doc, kind, subs)
    except Exception:
        new = {"fields": {}, "found": [], "notes": [], "checks": [], "detail": {}}
    try:
        old = old_read(kind, lines, subs) if lines else None
    except Exception:
        old = None
    r = _best(new, old)
    if doc.notes:
        r.setdefault("notes", [])
        r["notes"] = [n for n in doc.notes if n not in r["notes"]] + r["notes"]
    r["source"] = "file" if data is not None else "text"
    return finish(r, doc if data is not None else None)


def read_agreement_doc(data=None, name="", lines=None, trades=None):
    """A subcontract agreement / LPO: the header (subcontractor, numbers, value, %, dates) by the new reader with
    the team's reader beside it; the priced schedule by the team's reader (est_agreement), checked against the value."""
    import est_agreement as A
    from docread.contract import read_contract
    from docread.other import from_lines
    doc = None
    if data is not None:
        doc = load_doc(data, name)
        lines = old_lines(data, name, doc)
    old = A.read(lines or [], trades=trades or [])
    try:
        new = read_contract(doc if doc is not None else from_lines(lines or []), "agreement")
    except Exception:
        new = {"fields": {}, "found": [], "notes": [], "checks": [], "detail": {}}
    nf = new.get("fields") or {}
    # the header: the new reading, the team's reader's own fields kept where it is the one that knows them
    r = dict(old)
    r["fields"] = dict(old.get("fields") or {})
    r["detail"] = {}
    for k, v in nf.items():
        if k in ("project", "client", "consultant", "location", "duration", "sub_name", "end_date"):
            continue
        d = (new.get("detail") or {}).get(k) or {}
        mine = r["fields"].get(k)
        if mine in (None, ""):
            r["fields"][k] = v
            r["detail"][k] = dict(d, value=v) if d else {"value": v, "confidence": 0.6, "status": "check", "where": None}
        elif _same(mine, v):
            dd = dict({"confidence": 0.8, "where": None}, **d)
            dd.update(value=mine, status=d.get("status") or "ok", note="both readings agree")
            r["detail"][k] = dd
        elif _num(v) and d.get("status") == "ok":
            r["fields"][k] = v
            r["detail"][k] = dict(d, value=v, note=f"the agreement's figures agree on {_fmt(v)} - the other reading was {_fmt(mine)}")
        else:
            r["detail"][k] = {"value": mine, "confidence": 0.5, "status": "check", "where": d.get("where"), "note": f"the two readings differ - also read as {_fmt(v)}"}
    # the schedule against the contract value as now read
    c = r.get("checks") if isinstance(r.get("checks"), dict) else {}
    items = r.get("items") or []
    val = r["fields"].get("value")
    sums = []
    if items:
        tot = round(sum(x.get("amount") or 0 for x in items), 2)
        c = dict(c, items_total=tot, contract_value=val, match=val is not None and abs(tot - val) <= 1.0)
        sums.append({"name": "The priced schedule adds up to the contract value", "ok": bool(c["match"]),
                     "detail": f"{tot:,.2f} on the schedule" + (f", contract value {val:,.2f}" if val is not None else ", no contract value found")})
        for s in c.get("sections") or []:
            sums.append({"name": f"{s.get('bill', 'Bill')} adds up to its total", "ok": bool(s.get("ok")), "detail": f"{(s.get('total') or 0):,.2f} added, {(s.get('in_doc') or 0):,.2f} on the agreement"})
        if val is not None and "value" in r["detail"] and r["detail"]["value"].get("status") == "check" and c["match"]:
            r["detail"]["value"] = dict(r["detail"]["value"], status="ok", note="the priced schedule adds up to it")
    for x in new.get("checks") or []:
        if not x.get("name", "").startswith("The priced schedule"):
            sums.append({"name": x.get("name", ""), "ok": bool(x.get("ok")), "detail": x.get("detail", "")})
    r["checks"] = c
    for n in new.get("notes") or []:
        r.setdefault("notes", [])
        if n not in r["notes"]:
            r["notes"].append(n)
    r["found"] = list(dict.fromkeys(list(r.get("found") or []) + [n for n in (new.get("found") or []) if n not in ("Project name", "Client", "Consultant", "Location", "Completion")]))
    r["engine"] = "docread"
    r["source"] = "file" if data is not None else "text"
    finish(r, doc)
    r["checks"] = c
    r["sums"] = sums
    return r


def _row_json(x):
    out = {}
    for k, v in x.items():
        out[k] = v.isoformat() if isinstance(v, date) else v
    return out


VO_MONEY = ("submitted_amount", "revised_amount", "approved_amount", "absorbed_amount")


def read_vo_file(data, name):
    """The variation log: the team's own Excel log (with the OHP sheet) by est_voimport when it reads it fully;
    any other layout, PDF or scan by docread. -> (rows, info for the confirm screen)"""
    import est_voimport
    from docread.load import sniff
    k = sniff(data, name)
    old = None
    if k in ("xlsx", "xlsm"):
        try:
            old = est_voimport.read_log(data)
        except Exception:
            old = None
    new, doc, why = None, None, ""
    try:
        doc = load_doc(data, name)
        from docread.volog import read_log
        new = read_log(doc)
    except Unavailable:
        if not old:
            raise
        why = "unavailable"
    except HTTPException:
        if not old:
            raise
    nrows = (new or {}).get("rows") or []
    info = {"engine": "docread", "checks": (new or {}).get("checks") or [], "notes": list((new or {}).get("notes") or []),
            "pages": pages_of(doc) if doc is not None else [], "doc_kind": doc.kind if doc is not None else k}

    def tot(rows, key):
        return round(sum(r.get(key) or 0 for r in rows if r.get("kind") != "Coordination"), 2)
    if old:
        main = [r for r in old if r.get("kind") != "Coordination"]
        full = not nrows or (len(main) >= len(nrows) and all(abs(tot(main, m) - tot(nrows, m)) <= 1.0 for m in VO_MONEY))
        if full:
            info.update(engine="team log", checks=info["checks"] if nrows else [], notes=[] if why else info["notes"])
            info["detail"] = [None] * len(old)
            return [_row_json(r) for r in old], info
        # the new reading, with the OHP sheet's coordination lines the team's reader found
        coord = [r for r in old if r.get("kind") == "Coordination"]
        rows = [_row_json(r) for r in nrows] + [_row_json(r) for r in coord]
        info["detail"] = list(new.get("detail") or []) + [None] * len(coord)
        if coord:
            info["notes"].append(f"{len(coord)} coordination line(s) from the OHP sheet added as the team's log has them.")
        return _renumber(rows), info
    if not nrows:
        raise HTTPException(400, "No variation log found - the table needs headings like Ref. No, Description and an amount column.")
    info["detail"] = list(new.get("detail") or [])
    return [_row_json(r) for r in nrows], info


def _renumber(rows):
    for i, r in enumerate(rows):
        r["seq"] = i + 1
    return rows


def vo_rows_from_json(rows):
    """Rows sent back from the confirm screen (as read, perhaps corrected) -> rows for the import (whitelisted)."""
    keep = ("ref", "title", "kind", "source", "pc_ref", "status", "notes", "submitted", "approved_on") + VO_MONEY
    out = []
    if not isinstance(rows, list) or len(rows) > 2000:
        raise HTTPException(400, "Bad variation lines.")
    for x in rows:
        if not isinstance(x, dict):
            continue
        r = {}
        for k in keep:
            v = x.get(k)
            if k in VO_MONEY:
                try:
                    r[k] = round(float(str(v).replace(",", "")), 2) if v not in (None, "") else 0.0
                except ValueError:
                    raise HTTPException(400, f"'{v}' is not an amount.")
            elif k in ("submitted", "approved_on"):
                s = str(v or "")[:10]
                r[k] = s if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s) else None
            else:
                r[k] = str(v or "")[:1000]
        if r["status"] not in ("Identified", "Submitted", "Approved", "Rejected", "Absorbed", "Claimed", "Cancelled"):
            r["status"] = "Identified"
        if r["kind"] not in ("Addition", "Omission", "Coordination"):
            r["kind"] = "Addition"
        if not r["title"].strip():
            continue
        out.append(r)
    return out

"""docread - an offline, model-free reader for Estimation uploads (bills / IPAs, subcontractor PCs, variation
logs, contracts and agreements). See README.md.

    from docread import read_file
    r = read_file(data, "914 IPA 07.xlsx", "ipa")          # kind: ipa | subpc | vo | project | agreement
    r["fields"]   -> same keys as the existing readers (est_prevread.read_ipa / read_subpc, est_docread.read_project ...)
    r["detail"]   -> per field: value, confidence 0-1, status ok / check / derived, where (page + bbox, or Sheet!E14)
    r["checks"]   -> the document's own sums, each passed or failed

Nothing is kept: the file is read in memory and dropped.
"""
from .load import load
from .model import Doc
from .other import from_lines


def read_doc(doc, kind, subs=None):
    if kind in ("ipa", "clientpc"):
        from .bills import read_ipa
        return read_ipa(doc)
    if kind == "subpc":
        from .bills import read_subpc
        return read_subpc(doc, subs or [])
    if kind in ("vo", "volog", "variations"):
        from .volog import read_log
        return read_log(doc)
    if kind in ("project", "contract"):
        from .contract import read_contract
        return read_contract(doc, "project")
    if kind == "agreement":
        from .contract import read_contract
        return read_contract(doc, "agreement")
    raise ValueError(f"Nothing reads '{kind}' documents.")


def read_file(data: bytes, name: str, kind: str, subs=None, ocr=True):
    """Bytes of an uploaded file -> the reading. kind: ipa | subpc | vo | project | agreement."""
    doc = load(data, name, ocr=ocr)
    r = read_doc(doc, kind, subs)
    if doc.notes:
        r.setdefault("notes", [])
        r["notes"] = list(doc.notes) + list(r["notes"])
    return r


def read_lines(lines, kind, subs=None):
    """The browser's lines (what /store/est/read/<kind> receives today) -> the same reading."""
    return read_doc(from_lines(lines), kind, subs)


__all__ = ["read_file", "read_lines", "read_doc", "load", "from_lines", "Doc"]

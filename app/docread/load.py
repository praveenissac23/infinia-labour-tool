"""Any file -> the layout model, by what the file is (its first bytes), not only its name."""
import os
import time

from .model import Doc


def sniff(data, name=""):
    ext = os.path.splitext(name or "")[1].lower()
    head = data[:8]
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return "xls"
    if head.startswith(b"PK"):
        if ext == ".docx" or b"word/" in data[:4000]:
            return "docx"
        return "xlsx"
    if head[:3] == b"\xff\xd8\xff" or head.startswith(b"\x89PNG") or head[:4] in (b"II*\x00", b"MM\x00*") or head[:4] == b"RIFF" or ext in (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".bmp"):
        return "image"
    return ext.lstrip(".") or "unknown"


def load(data, name="", ocr=True, dpi=300) -> Doc:
    t0 = time.perf_counter()
    kind = sniff(data, name)
    if kind == "pdf":
        from .pdf import read_pdf
        doc = read_pdf(data, name, ocr=ocr, dpi=dpi)
    elif kind == "xls":
        from .excel import read_xls
        doc = read_xls(data, name)
    elif kind in ("xlsx", "xlsm"):
        from .excel import read_xlsx
        doc = read_xlsx(data, name)
    elif kind == "docx":
        from .other import read_docx
        doc = read_docx(data, name)
    elif kind == "image":
        from .ocr import read_image
        doc = read_image(data, name)
    else:
        raise ValueError(f"Can't read that kind of file ({kind}).")
    doc.timing["load"] = round(time.perf_counter() - t0, 3)
    doc.timing["pages"] = len(doc.regions)
    return doc

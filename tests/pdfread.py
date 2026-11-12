"""PdfReader for the tests: pypdf when it is installed, otherwise the same few calls on pdfminer (installed with
pdfplumber, which the app itself uses), so the tests need no package the app does not have."""
try:
    from pypdf import PdfReader  # noqa: F401
except ImportError:
    import io
    import pdfplumber
    from pdfminer.high_level import extract_text as _text

    class _Box:
        def __init__(self, p):
            self.width, self.height = float(p.width), float(p.height)

    class _Page:
        def __init__(self, data, i, p):
            self._data, self._i = data, i
            self.mediabox = _Box(p)

        def extract_text(self):          # text box by text box, like pypdf - columns are not interleaved
            return _text(io.BytesIO(self._data), page_numbers=[self._i]) or ""

    class PdfReader:
        def __init__(self, stream):
            data = stream.read() if hasattr(stream, "read") else open(stream, "rb").read()
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                self.pages = [_Page(data, i, p) for i, p in enumerate(pdf.pages)]

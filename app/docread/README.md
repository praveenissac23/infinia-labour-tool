# docread — offline document reader for Estimation uploads

Reads previous bills / IPAs, subcontractor payment certificates, variation logs, contracts / letters of award and
subcontract agreements in **any layout** — Excel (.xlsx/.xls), typed PDF, scanned PDF / photos, Word (.docx) — on the
portal's own server. No AI model, no paid API, nothing downloaded except Tesseract's classic English data. Nothing is
stored: the file is read in memory and dropped.

## How it reads

1. **One layout model** (`model.py`). Every file becomes regions (sheet / page) → rows → cells, each cell with its
   place: `Sheet!E14` for Excel, page + box for PDFs and scans.
   * Excel (`excel.py`): Excel's own numbers (cached values; a formula without a saved value is worked out), number
     formats (brackets = minus, % = percentage, dates), merged cells as one cell, hidden sheets / rows / columns left
     out. `.xls` read directly with xlrd (LibreOffice conversion only as a fallback).
   * Typed PDF (`pdf.py`): pdfplumber word boxes → lines → cells (word gaps + the table's vertical rules); wrapped
     cells joined between the table's horizontal rules (`merge_bands`). A page with no text layer goes to OCR.
   * Scans / photos (`ocr.py`): the scan's own JPEG taken out of the PDF (else pdftoppm at 300 dpi), straightened,
     table rules found and painted out (their positions still split cells), Tesseract (TSV word boxes + confidence),
     unsure figures re-read enlarged with digits only. Two pages at a time.
   * Word (`other.py`): paragraphs and table rows. The browser's existing lines (`from_lines`) work too.
2. **Table understanding** (`tables.py`, `vocab.py`): heading rows (one to three deep, merged) found and validated
   (figures must stand under them); every figure gets its column meaning — previous / this period / cumulative /
   contract / % / qty / rate — from the heading above it. Row labels and headings are matched to meanings with a
   synonym list, fuzzy for misspellings and scan errors ("Retension", "PREVIOULSY"), English and Arabic.
   "Label: value" cells, labels on the line above/below a figure (scans), and a heading run together with the next
   are handled.
3. **Arithmetic, not position** (`solve.py`, `bills.py`). Each field gets candidate figures with a score; the
   choice is the one that best keeps the document's own sums:
   previous + this = to date · work + variations = total · total − retention − advance − deductions = net ·
   to date − previously certified = due · VAT = 5% × due · due + VAT (+ authority fees) = total payable ·
   deductions add up to "total deductions" · earlier certificates add up to "previously certified" ·
   retention = its % of work · the amount in words. A beam search plus repair moves (leave out a breakdown table's
   line, switch to another candidate) does the choosing. A figure not printed but fixed by the others is worked out
   and marked **derived**; a scan's figure one digit off what the sums need is corrected and marked.
4. **Never silently guessed.** Every field comes with `confidence` (0–1), `status` (`ok` only when one of the bill's
   own sums ties it to the amount due; otherwise `check`; `derived` when worked out) and `where` (sheet!cell or
   page + box) for the confirm screen. `checks` lists each sum, passed or failed.

## Use

```python
from docread import read_file, read_lines
r = read_file(data, "914 IPA 07.xlsx", "ipa")   # ipa | clientpc | subpc | vo | project | agreement
r["fields"]   # same keys as est_prevread.read_ipa / read_subpc, est_docread.read_project / read_clientpc,
              # est_agreement.read (fields), est_voimport.read_log (r["rows"] for "vo")
r["detail"]   # {"total": {"value": 8522.0, "confidence": 0.99, "status": "ok", "label": "Total Amount due for Payment",
              #            "where": {"page": 1, "ref": "IPA!E22"}}, ...}
r["checks"]   # [{"name": "VAT is 5% of the net", "ok": True, "detail": "405.82 worked out, 405.82 on the document"}, ...]
r["flagged"]  # names of fields to look at before saving
read_lines(lines, "subpc", subs)   # the browser's lines (what /store/est/read/<kind> receives today)
```

`docread.legacy.to_lines(doc)` turns a server-read file into the browser's line format, so the existing readers can
be run on it side by side during roll-out.

## Server needs

```
sudo apt-get install -y tesseract-ocr tesseract-ocr-eng poppler-utils
pip install "pdfplumber==0.11.*" "numpy>=1.26" "Pillow>=10" "python-docx>=1.1"   # openpyxl, xlrd already in requirements
```
(LibreOffice only for an `.xls` xlrd cannot open.) No GPU, no models, no network.

## Tests and measuring

```
python3 tests/docread/test_docread.py                       # unit + real-file tests (plain asserts; pytest works too)
python3 tests/docread/synth.py /tmp/corpus --n 30 --seed 2026 --scans 0.4
python3 tests/docread/bench.py /tmp/corpus --out results.json # new vs existing readers, field by field, per format
```
The harness runs the existing readers on what the portal gives them today (browser extraction emulated:
SheetJS cells, pdf.js items, Tesseract page mode 3) and the new reader on the file itself.

## Known limits

* Scans: Tesseract misreads (O/0, a column rule read as a letter) remain in text fields (refs, titles); figures are
  protected by the sums, text is not — those cells carry a `check` flag (low recognition confidence).
* Handwriting, stamps over figures and photos at an angle > 4° are not read reliably.
* A certificate that shows only one period's column and no "previous" line cannot be told apart from a cumulative
  one by arithmetic; the column heading decides, and without one the figure is marked `check`.
* Contracts: parties / dates / % are found from labels and common sentence patterns, the value by agreement between
  its mentions (label, sentence, schedule total, words, with/without VAT); unusual wording may be missed (left empty,
  never invented).

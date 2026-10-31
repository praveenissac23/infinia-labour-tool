"""Tests for app/docread (the offline document reader). Plain asserts - run either way:

    python3 tests/docread/test_docread.py          (prints PASS / FAIL per test)
    python3 -m pytest tests/docread/test_docread.py

The OCR test needs tesseract and poppler-utils (pdftoppm) and is skipped without them.
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "app"))
sys.path.insert(0, HERE)

from docread import read_file, read_lines  # noqa: E402
from docread.numparse import a_date, digit_edit_close, numbers  # noqa: E402
from docread.vocab import col_roles, row_concepts  # noqa: E402

FX = os.path.join(HERE, "..", "fixtures", "prev")


def close(a, b):
    return a is not None and abs(a - b) < 0.005


# ---- numbers, words ---------------------------------------------------------------------------------------

def test_numbers():
    v = lambda t, ocr=False: [n.value for n in numbers(t, ocr)]
    assert v("AED 1,234.50") == [1234.5]
    assert v("(1,234.50)") == [-1234.5]
    assert v("-291,990.93") == [-291990.93]
    assert v("1,234.50-") == [-1234.5]
    assert v("Dhs. (5,000)") == [-5000.0]
    assert v("1.234.567,89") == [1234567.89]
    assert v("Retention held - 30,777.63") == [30777.63]          # a dash between label and figure is not a minus
    assert v("06.10.2026") == [] and v("TRN 100602393900003") == []
    assert [n.pct for n in numbers("Retention 10% 4,290.50")] == [True, False]
    assert v("1O,5OO.0O", ocr=True) == [10500.0]                  # a scan's O for 0
    assert v("4,798,952,78", ocr=True) == [4798952.78]            # a scan's comma for the decimal point
    assert v("1 234 567.89", ocr=True) == [1234567.89]


def test_dates():
    assert a_date("06.10.2026").isoformat() == "2026-10-06"
    assert a_date("22nd day of October, 2026").isoformat() == "2026-10-22"
    assert a_date("Oct 5, 2026").isoformat() == "2026-10-05"
    assert a_date("5-Oct-26").isoformat() == "2026-10-05"


def test_digit_edit():
    assert digit_edit_close(1118.18, 11118.18) and digit_edit_close(10588.75, 10688.75) and not digit_edit_close(100, 250)


def test_vocab():
    first = lambda t: row_concepts(t)[0][0]
    assert first("Less: Advance Recovery") == "adv"
    assert first("Less Previous Progressive Payments (Appendix A)") == "prev"
    assert first("Retension @ 10%") == "ret"                      # misspelt
    assert first("TOTAL PREVIOULSY CERTIFIED") == "prev"          # misspelt
    assert first("Net payable incl. VAT") == "total"
    assert first("Amount due excl. VAT") == "net"
    assert first("RETENTION RELEASE") == "rel"
    assert col_roles("Upto Last") == {"p": 0.95} and "t" in col_roles("Present") and "c" in col_roles("To Date")
    assert "p" in col_roles("Previous / السابق")
    assert col_roles("Main-Contractor") == {}                     # not a "Contract value" column


# ---- the real certificates (as the browser read them) -----------------------------------------------------

def _expectations():
    import re
    src = open(os.path.join(HERE, "..", "est_prevread_test.py")).read()
    ipa = eval(re.search(r"^IPA = (\{.*?^\})", src, re.S | re.M).group(1))
    pc = eval(re.search(r"^PC = (\{.*?^\})", src, re.S | re.M).group(1))
    raida = eval(re.search(r"^RAIDA = (\[.*?\])", src, re.S | re.M).group(1))
    return ipa, pc, raida


def test_real_certificates():
    ipa, pc, raida = _expectations()
    bad = []
    for kind, S in (("ipa", ipa), ("subpc", pc)):
        for name, want in S.items():
            r = read_lines(json.load(open(os.path.join(FX, name)))["lines"], kind, raida)
            for k, v in want.items():
                g = r["fields"].get(k)
                if not ((isinstance(v, float) and close(g, v)) or g == v):
                    bad.append((name, k, v, g))
            assert all(c["ok"] for c in r["checks"]), (name, [c for c in r["checks"] if not c["ok"]])
    assert not bad, bad


def test_misread_is_caught():
    """A scan that read 10,588.75 as 10,688.75: the certificate's own sums catch it and the figure is not 'ok'."""
    lines = json.load(open(os.path.join(FX, "915-RoyalEverest-PC12_-_For_review.pdf.json")))["lines"]
    for l in lines:
        if "Retention" in l.get("t", "") and "10,588.75" in l.get("t", "") and "Release" not in l.get("t", ""):
            l["c"] = [x.replace("10,588.75", "10,688.75") for x in l["c"]]
            l["t"] = l["t"].replace("10,588.75", "10,688.75")
            break
    r = read_lines(lines, "subpc", [])
    f = r["fields"]
    # either the wrong figure is left out / flagged, or (as a scan) put right - never silently accepted
    if close(f.get("ret_cum"), 10688.75):
        assert r["detail"]["ret_cum"]["status"] != "ok"
    assert close(f.get("net"), 9738.75) and close(f.get("total"), 10226.0)


def test_real_xls():
    p = "/mnt/user-data/attachments/ba2fc83b-b38d-51d2-82fb-8cc96aef91bb/58f6f950-914_MEP_IPA02_-_R2.xls"
    if not os.path.exists(p):
        return
    r = read_file(open(p, "rb").read(), "914 MEP IPA02 R2.xls", "ipa")
    f = r["fields"]
    assert f["seq"] == 2 and f["submitted"] == "2026-10-06"
    for k, v in {"claimed_cum": 35471.07, "adv_rec_cum": 7094.21, "previous": 16713.33, "ret_cum": 3547.11, "vat": 405.82, "total": 8522.0}.items():
        assert close(f.get(k), v), (k, f.get(k))
        assert r["detail"][k]["status"] == "ok" and r["detail"][k]["where"]["ref"].startswith("IPA!E")
    assert r["detail"]["total"]["where"]["ref"] == "IPA!E22"


# ---- the synthetic corpus, every format --------------------------------------------------------------------

def _corpus(scans):
    import synth
    d = tempfile.mkdtemp(prefix="docread_t_")
    synth.build(d, n=6, seed=101, scans=scans, vo_n=3, contract_n=3)
    return d, json.load(open(os.path.join(d, "truth.json")))


def test_synthetic_typed():
    import bench
    d, corpus = _corpus(0.0)
    try:
        tot = ok = 0
        for c in corpus:
            if c["format"] == "scan":
                continue
            data = open(os.path.join(d, c["file"]), "rb").read()
            r = read_file(data, c["file"], c["kind"], [{"id": 1, "name": c["sub"]}] if c.get("sub") else None)
            if c["kind"] == "vo":
                fs, _ = bench.score_vo(c["truth"], r["rows"])
            else:
                fs = bench.score_fields(c["truth"], r["fields"], r.get("detail"))
                # nothing wrong may be marked sure
                for f in fs:
                    assert f["ok"] or f["missing"] or f.get("flagged") is not False or f["field"] in ("seq", "submitted"), (c["file"], f)
            tot += len(fs)
            ok += sum(f["ok"] for f in fs)
        assert ok / tot >= 0.95, ok / tot
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_scan_ocr():
    if not shutil.which("tesseract") or not shutil.which("pdftoppm"):
        return
    import random
    import synth
    d = tempfile.mkdtemp(prefix="docread_s_")
    try:
        rng = random.Random(5)
        F = synth.bill_figures(rng, sub=True)
        F["_st"] = {"cur": "", "neg": "()", "dec": True, "sep": True}
        pages, _ = synth.layout_atoe(rng, F, "subpc")
        pdf = os.path.join(d, "pc.pdf")
        synth.render_pdf(pages, pdf, F["_st"])
        synth.scan_pdf(pdf, os.path.join(d, "pc_scan.pdf"), rng, dpi=200)
        r = read_file(open(os.path.join(d, "pc_scan.pdf"), "rb").read(), "pc_scan.pdf", "subpc")
        assert r["source"]["ocr_pages"] == [1]
        f = r["fields"]
        assert close(f.get("net"), F["net_t"]) and close(f.get("total"), F["total"]) and close(f.get("work_cum"), F["work_c"]), f
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_vo_log_layouts():
    """A log with a two-row heading ('Amount' over Claimed / Revised / Agreed), the heading words not the team's."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["VARIATION ORDER REGISTER"])
    ws.append(["VO Ref", "Particulars", "Amount (AED)", None, None, "Date of Submission", "Approved On", "Comments"])
    ws.merge_cells("C2:E2")
    ws.append([None, None, "Claimed", "Revised", "Agreed", None, None, None])
    ws.append(["VO-01", "Extra power points", 12500, None, 11000, "05/02/2026", "20/02/2026", "Accepted"])
    ws.append(["VO-02", "Omission of pergola", -8000, None, None, "06/03/2026", None, "Under review"])
    ws.append(["VO-03", "Smart home wiring", None, None, None, None, None, "To be submitted"])
    ws.append([None, "TOTAL", 4500, 0, 11000])
    p = os.path.join(tempfile.mkdtemp(), "vo.xlsx")
    wb.save(p)
    r = read_file(open(p, "rb").read(), "vo.xlsx", "vo")
    rows = r["rows"]
    assert [x["ref"] for x in rows] == ["VO-01", "VO-02", "VO-03"], rows
    assert rows[0]["submitted_amount"] == 12500 and rows[0]["approved_amount"] == 11000 and rows[0]["status"] == "Approved"
    assert rows[0]["submitted"].isoformat() == "2026-02-05" and rows[0]["approved_on"].isoformat() == "2026-02-20"
    assert rows[1]["kind"] == "Omission" and rows[1]["status"] == "Submitted"
    assert rows[2]["status"] == "Identified"
    assert r["checks"] and all(c["ok"] for c in r["checks"]), r["checks"]


if __name__ == "__main__":
    fails = []
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:                      # noqa: BLE001
                import traceback
                print("FAIL", name, "->", repr(e)[:300])
                traceback.print_exc(limit=2)
                fails.append(name)
    print("\nALL PASS" if not fails else f"\n{len(fails)} FAILED: {fails}")
    sys.exit(1 if fails else 0)

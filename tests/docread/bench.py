"""Scoring harness: the new reader (app/docread) against the existing readers, field by field, on

  * the real certificates already in tests/fixtures/prev (as the browser read them - lines JSON) with the figures
    typed from the files (the same expectations as tests/est_prevread_test.py);
  * the real 914 MEP IPA 02 R2 .xls (if present on this machine);
  * a synthetic corpus (tests/docread/synth.py): bills, PCs, variation logs and contracts in many layouts, as Excel,
    typed PDF, scanned PDF and Word.

The OLD readers are given what the portal gives them today: the browser's lines, emulated on the server
(docread.legacy.browser_lines - SheetJS cells, pdf.js items, Tesseract page mode 3).

    python3 tests/docread/bench.py CORPUS_DIR [--out results.json] [--only ipa,subpc] [--no-old] [--limit N]
"""
import argparse
import json
import os
import re
import sys
import tempfile
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, "..", "..", "app"))
sys.path.insert(0, APP)
os.environ.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(tempfile.gettempdir(), "docread_bench.db"))
os.environ.setdefault("INFINIA_NO_SCHED", "1")

from docread import read_file, read_lines  # noqa: E402
from docread.legacy import browser_lines  # noqa: E402

_OLD = {}


def old_modules():
    if not _OLD:
        cwd = os.getcwd()
        os.chdir(APP)
        try:
            import main  # noqa: F401 - the app first (the est_* modules import each other through it)
            import est_agreement as A
            import est_docread as R
            import est_prevread as P
            import est_voimport as V
        finally:
            os.chdir(cwd)
        _OLD.update(A=A, R=R, P=P, V=V)
    return _OLD


def old_read(kind, lines, data=None, subs=None):
    M = old_modules()
    A, R, P = M["A"], M["R"], M["P"]
    if kind == "vo":
        if data is None or not (data[:2] == b"PK"):
            return None                      # the existing import takes Excel only
        try:
            return {"rows": M["V"].read_log(data)}
        except Exception:
            return {"rows": []}
    if kind in ("ipa", "subpc"):
        lines = P._join_ocr(lines)
    lines = A.clean_lines(lines)
    flat = R._flat(lines)
    if kind == "subpc":
        return R.READERS["subpc"](lines, flat, subs or [])
    if kind == "agreement":
        return A.read(lines)
    return R.READERS[kind](lines, flat)


# ---- comparing ----------------------------------------------------------------------------------------------

def same(field, want, got):
    if got is None or got == "":
        return False
    if isinstance(want, (int, float)) and not isinstance(want, bool):
        try:
            return abs(float(got) - float(want)) <= 0.011
        except (TypeError, ValueError):
            return False
    w, g = str(want).lower(), str(got).lower()
    if re.fullmatch(r"\d{4}-\d\d-\d\d", w):
        return w == g[:10]
    sq = lambda s: re.sub(r"[^a-z0-9]", "", re.sub(r"^m\s*/\s*s\.?\s*|\b(mr|ms|mrs)\.?\s+", "", s))
    a, b = sq(w), sq(g)
    return bool(a) and (a == b or (len(b) >= 0.7 * len(a) and (a in b or b in a)))


def score_fields(truth, fields, detail=None):
    out = []
    for k, v in truth.items():
        g = (fields or {}).get(k)
        ok = same(k, v, g)
        flagged = None
        if detail is not None and k in detail:
            flagged = detail[k].get("status") != "ok"
        out.append({"field": k, "want": v, "got": g, "ok": ok, "missing": g in (None, ""), "flagged": flagged})
    return out


VO_FIELDS = ("ref", "title", "submitted_amount", "revised_amount", "approved_amount", "absorbed_amount", "submitted", "approved_on", "status")


def score_vo(truth, rows):
    out = []
    norm = lambda s: re.sub(r"[^a-z0-9]", "", str(s or "").lower())
    by_ref = {}
    for r in rows or []:
        by_ref.setdefault(norm(r.get("ref")), []).append(r)
    for t in truth:
        cand = by_ref.get(norm(t["ref"])) or []
        g = cand.pop(0) if cand else None
        for k in VO_FIELDS:
            want = t.get(k)
            if want is None:
                want = ""
            got = (g or {}).get(k)
            if hasattr(got, "isoformat"):
                got = got.isoformat()
            if k.endswith("amount"):
                ok = g is not None and abs(float(got or 0) - float(want or 0)) <= 0.011
            elif want == "":
                ok = g is not None and not got
            else:
                ok = g is not None and same(k, want, got)
            out.append({"field": k, "want": want, "got": got, "ok": ok, "missing": g is None})
    extra = sum(len(v) for v in by_ref.values())
    return out, extra


# ---- real fixtures ----------------------------------------------------------------------------------------

REAL = None


def real_cases():
    sys.path.insert(0, os.path.join(HERE, ".."))
    src = open(os.path.join(HERE, "..", "est_prevread_test.py")).read()
    ipa = eval(re.search(r"^IPA = (\{.*?^\})", src, re.S | re.M).group(1))
    pc = eval(re.search(r"^PC = (\{.*?^\})", src, re.S | re.M).group(1))
    raida = eval(re.search(r"^RAIDA = (\[.*?\])", src, re.S | re.M).group(1))
    out = []
    for kind, S in (("ipa", ipa), ("subpc", pc)):
        for n, want in S.items():
            fmt = "scan" if n.startswith("scan") else ("xlsx" if ".xlsx" in n else "pdf")
            out.append({"file": n, "kind": kind, "format": fmt, "truth": want, "subs": raida, "real": True})
    return out


# ---- the run -----------------------------------------------------------------------------------------------

def run(corpus_dir, only=None, old=True, limit=None, real=True):
    results = []
    cases = []
    if real:
        cases += real_cases()
        xls = "/mnt/user-data/attachments/ba2fc83b-b38d-51d2-82fb-8cc96aef91bb/58f6f950-914_MEP_IPA02_-_R2.xls"
        if os.path.exists(xls):
            cases.append({"file": xls, "kind": "ipa", "format": "xls", "real": True, "path": xls,
                          "truth": {"seq": 2, "submitted": "2026-10-06", "claimed_cum": 35471.07, "adv_rec_cum": 7094.21, "previous": 16713.33,
                                    "ret_cum": 3547.11, "vat": 405.82, "authority": 0.0, "total": 8522.0}})
    if corpus_dir:
        for c in json.load(open(os.path.join(corpus_dir, "truth.json"))):
            c["path"] = os.path.join(corpus_dir, c["file"])
            if c.get("sub"):
                c["subs"] = [{"id": 99, "name": c["sub"]}]
            cases.append(c)
    if only:
        cases = [c for c in cases if c["kind"] in only]
    if limit:
        cases = cases[:limit]
    fx = os.path.join(HERE, "..", "fixtures", "prev")
    for k, c in enumerate(cases):
        rec = {k2: c.get(k2) for k2 in ("file", "kind", "format", "layout", "real", "dpi")}
        try:
            if c.get("real") and "path" not in c:
                lines = json.load(open(os.path.join(fx, c["file"])))["lines"]
                t0 = time.perf_counter()
                new = read_lines(lines, c["kind"], c.get("subs"))
                rec["new_s"] = time.perf_counter() - t0
                rec["pages"] = len({l.get("p", 1) for l in lines})
                oldr = old_read(c["kind"], lines, None, c.get("subs")) if old else None
                rec["old_s"] = None
            else:
                data = open(c["path"], "rb").read()
                t0 = time.perf_counter()
                new = read_file(data, os.path.basename(c["path"]), c["kind"], c.get("subs"))
                rec["new_s"] = time.perf_counter() - t0
                rec["pages"] = new.get("timing", {}).get("pages") or new.get("source", {}).get("pages")
                oldr = None
                if old:
                    t1 = time.perf_counter()
                    try:
                        lines = browser_lines(data, c["path"])
                        oldr = old_read(c["kind"], lines, data, c.get("subs"))
                    except Exception as e:
                        oldr = {"fields": {}, "error": str(e)[:200]}
                    rec["old_s"] = time.perf_counter() - t1
            if c["kind"] == "vo":
                rec["new_fields"], rec["new_extra"] = score_vo(c["truth"], new.get("rows"))
                if oldr is not None:
                    rec["old_fields"], rec["old_extra"] = score_vo(c["truth"], oldr.get("rows"))
                else:
                    rec["old_fields"] = [dict(f, ok=False, missing=True) for f in score_vo(c["truth"], [])[0]]
                    rec["old_unsupported"] = True
            else:
                rec["new_fields"] = score_fields(c["truth"], new.get("fields"), new.get("detail"))
                rec["old_fields"] = score_fields(c["truth"], (oldr or {}).get("fields")) if oldr is not None else None
                rec["checks_failed"] = [x["name"] for x in new.get("checks", []) if not x["ok"]]
        except Exception as e:
            rec["error"] = traceback.format_exc()[-800:]
        results.append(rec)
        n_ok = sum(f["ok"] for f in rec.get("new_fields", []))
        n = len(rec.get("new_fields", []))
        o_ok = sum(f["ok"] for f in (rec.get("old_fields") or []))
        print(f"[{k + 1}/{len(cases)}] {c['file'][-48:]:48s} new {n_ok}/{n}  old {o_ok}/{n}  {rec.get('new_s', 0):.2f}s"
              + ("  ERROR" if "error" in rec else ""), flush=True)
    return results


def summary(results):
    groups = {}
    for r in results:
        key = (("real " if r.get("real") else "") + r["kind"], r["format"])
        g = groups.setdefault(key, {"docs": 0, "n": 0, "new": 0, "old": 0, "new_wrong": 0, "new_wrong_flagged": 0, "new_missing": 0,
                                    "old_wrong": 0, "new_s": 0.0, "pages": 0, "docs_all_new": 0, "docs_all_old": 0, "old_s": 0.0, "old_n": 0})
        if "error" in r:
            g["errors"] = g.get("errors", 0) + 1
            continue
        g["docs"] += 1
        nf, of = r.get("new_fields", []), r.get("old_fields") or []
        g["n"] += len(nf)
        g["new"] += sum(f["ok"] for f in nf)
        g["old"] += sum(f["ok"] for f in of)
        g["new_missing"] += sum(1 for f in nf if not f["ok"] and f["missing"])
        wrong = [f for f in nf if not f["ok"] and not f["missing"]]
        g["new_wrong"] += len(wrong)
        g["new_wrong_flagged"] += sum(1 for f in wrong if f.get("flagged"))
        g["old_wrong"] += sum(1 for f in of if not f["ok"] and not f["missing"])
        g["docs_all_new"] += int(all(f["ok"] for f in nf))
        g["docs_all_old"] += int(bool(of) and all(f["ok"] for f in of))
        g["new_s"] += r.get("new_s") or 0
        g["pages"] += r.get("pages") or 1
        if r.get("old_s") is not None:
            g["old_s"] += r["old_s"]
            g["old_n"] += 1
    rows = []
    for (kind, fmt), g in sorted(groups.items()):
        if not g["n"]:
            continue
        rows.append({"type": kind, "format": fmt, "docs": g["docs"], "fields": g["n"],
                     "old_pct": round(100 * g["old"] / g["n"], 1), "new_pct": round(100 * g["new"] / g["n"], 1),
                     "old_docs_perfect": g["docs_all_old"], "new_docs_perfect": g["docs_all_new"],
                     "new_wrong": g["new_wrong"], "new_wrong_flagged": g["new_wrong_flagged"], "new_missing": g["new_missing"], "old_wrong": g["old_wrong"],
                     "new_s_per_doc": round(g["new_s"] / max(1, g["docs"]), 2), "new_s_per_page": round(g["new_s"] / max(1, g["pages"]), 2),
                     "old_extract_s_per_doc": round(g["old_s"] / g["old_n"], 2) if g["old_n"] else None, "errors": g.get("errors", 0)})
    return rows


def print_table(rows):
    h = ["type", "format", "docs", "fields", "old_pct", "new_pct", "old_docs_perfect", "new_docs_perfect", "new_wrong", "new_wrong_flagged",
         "new_missing", "new_s_per_doc", "new_s_per_page"]
    print(" | ".join(h))
    for r in rows:
        print(" | ".join(str(r.get(k)) for k in h))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--only")
    ap.add_argument("--no-old", action="store_true")
    ap.add_argument("--no-real", action="store_true")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    res = run(a.corpus, a.only.split(",") if a.only else None, not a.no_old, a.limit, not a.no_real)
    rows = summary(res)
    print()
    print_table(rows)
    if a.out:
        with open(a.out, "w") as fh:
            json.dump({"summary": rows, "results": res}, fh, indent=1, default=str)

"""Score the BOQ / schedule readers on the difficult books of boq_gen.py (5 Nov 2026).

For every book: the Excel read (est_itemimport.read_schedule), the same book printed to PDF and read
(est_pdfboq), and the agreement reader on both (est_fileread.read_agreement_doc). Each reading is compared with the
truth:
  money   - every priced line found with its amount (in order, matched by amount and description), nothing extra
            priced (no page total, brought forward, collection, summary, VAT counted as a line), the total = contract
  groups  - each lump-sum bracket one line with its items under it
  kept    - every unpriced item ("Included", "Rate only" ...) brought in at nil or listed for review, not dropped
  desc    - the description read whole (wrapped rows joined)

    python3 tests/stress/boq_score.py DIR [--only xlsx,pdf,agr] [--book boq_03] [-v]
"""
import argparse
import difflib
import json
import os
import re
import subprocess
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, "..", "..", "app"))
sys.path.insert(0, APP)
os.environ.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(tempfile.gettempdir(), "boq_stress.db"))
os.environ.setdefault("INFINIA_NO_SCHED", "1")
os.environ.setdefault("INFINIA_NO_PUSH", "1")
os.chdir(APP)
import main  # noqa: F401,E402
import est_itemimport as I  # noqa: E402
import est_pdfboq as P  # noqa: E402
import est_fileread as F  # noqa: E402

norm = lambda t: re.sub(r"[^a-z0-9]+", " ", str(t or "").lower()).strip()


def to_pdf(xlsx):
    pdf = xlsx[:-5] + ".pdf"
    if not os.path.exists(pdf) or os.path.getmtime(pdf) < os.path.getmtime(xlsx):
        d = tempfile.mkdtemp()
        subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", d, xlsx], capture_output=True, timeout=300)
        os.replace(os.path.join(d, os.path.basename(pdf)), pdf)
    return pdf


def score(truth, items, contract):
    """-> dict of scores and the differences."""
    want = [l for l in truth["lines"]]
    got = [x for x in items if (x.get("amount") or 0) != 0 and x.get("grp") != "in"]
    # align by amount, then description
    wa = [f"{l['amount']:.2f}" for l in want]
    ga = [f"{(x.get('amount') or 0):.2f}" for x in got]
    sm = difflib.SequenceMatcher(a=wa, b=ga, autojunk=False)
    ok, miss, extra, pairs = 0, [], [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            ok += i2 - i1
            pairs += list(zip(range(i1, i2), range(j1, j2)))
        else:
            miss += [want[i] for i in range(i1, i2)]
            extra += [got[j] for j in range(j1, j2)]
    # descriptions of matched lines
    dbad = []
    for i, j in pairs:
        w, g = norm(want[i]["desc"]), norm(got[j].get("description"))
        if w not in g and not (len(g) > 8 and g in w):
            dbad.append((want[i]["desc"][:60], (got[j].get("description") or "")[:80]))
    # a certificate: each line's % done and certified figure
    pbad = []
    if truth.get("pc"):
        for i, j in pairs:
            w, g = want[i], got[j]
            if "pct" in w and (abs((g.get("done_pct") or 0) - w["pct"]) > 0.001 or abs((g.get("certified") or 0) - w["certified"]) > 0.011):
                pbad.append((w["desc"][:40], w["pct"], g.get("done_pct"), w["certified"], g.get("certified")))
    # groups
    gbad = []
    for i, j in pairs:
        if want[i]["grp"] == "head":
            k = items.index(got[j])
            mem = []
            for x in items[k + 1:]:
                if x.get("grp") != "in":
                    break
                mem.append(norm(x.get("description")))
            wm = [norm(m) for m in want[i]["members"]]
            if got[j].get("grp") != "head" or len(mem) != len(wm) or any(a not in b for a, b in zip(wm, mem)):
                gbad.append((want[i]["desc"][:40], len(wm), got[j].get("grp"), len(mem)))
    # unpriced kept
    alltext = [norm(x.get("description")) for x in items]
    lost = [u["desc"] for u in truth["unpriced"] if not any(norm(u["desc"]) in t for t in alltext)]
    return {"pbad": pbad, "lines": len(want), "ok": ok, "miss": miss, "extra": extra, "dbad": dbad, "gbad": gbad, "lost": lost,
            "contract_ok": abs((contract or 0) - truth["contract"]) < 0.01, "contract": contract, "want": truth["contract"]}


def run_reader(kind, path):
    if kind == "xlsx":
        r = I.read_schedule(open(path, "rb").read())
        return r["items"], r["contract"], r
    if kind == "pdf":
        pdf = to_pdf(path)
        wb = P.workbook_of(open(pdf, "rb").read(), os.path.basename(pdf))
        r = I.read_schedule(wb)
        return r["items"], r["contract"], r
    if kind in ("agr", "agrpdf"):
        p = path if kind == "agr" else to_pdf(path)
        r = F.read_agreement_doc(open(p, "rb").read(), os.path.basename(p))
        v = (r.get("fields") or {}).get("value")
        if isinstance(v, dict):
            v = v.get("value")
        return r.get("items") or [], v, r
    raise ValueError(kind)


def main_():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--only", default="xlsx,pdf,agr,agrpdf")
    ap.add_argument("--book")
    ap.add_argument("-v", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()
    books = sorted(f[:-5] for f in os.listdir(a.dir) if f.endswith(".json") and (not a.book or f.startswith(a.book)))
    kinds = a.only.split(",")
    tot = {k: {"books": 0, "perfect": 0, "lines": 0, "ok": 0, "contract_ok": 0, "groups_bad": 0, "lost": 0, "extra": 0, "desc_bad": 0, "crash": 0, "alarms": 0}
           for k in kinds}
    fails = {}
    for b in books:
        truth = json.load(open(os.path.join(a.dir, b + ".json")))
        path = os.path.join(a.dir, b + ".xlsx")
        row = [b]
        for k in kinds:
            t = tot[k]
            t["books"] += 1
            try:
                items, contract, raw = run_reader(k, path)
                s = score(truth, items, contract)
            except Exception as e:
                t["crash"] += 1
                row.append(f"{k}:CRASH {e}")
                fails.setdefault(b, {})[k] = traceback.format_exc()[-800:]
                continue
            t["lines"] += s["lines"]
            t["ok"] += s["ok"]
            t["contract_ok"] += s["contract_ok"]
            t["groups_bad"] += len(s["gbad"])
            t["lost"] += len(s["lost"])
            t["extra"] += len(s["extra"])
            t["desc_bad"] += len(s["dbad"])
            perfect = s["ok"] == s["lines"] and not s["extra"] and s["contract_ok"] and not s["gbad"] and not s["lost"] and not s["pbad"]
            t["perfect"] += perfect
            alarms = [n for n in ((raw.get("notes") or []) if isinstance(raw, dict) else []) if re.search(r" says |add up to|not the|no page of its own|listed twice|numbered|accounted for", n)]
            t["alarms"] += len(alarms)
            if alarms:
                fails.setdefault(b, {}).setdefault(k + "_alarms", alarms[:6])
            row.append(f"{k}:{'OK ' if perfect else 'BAD'} {s['ok']}/{s['lines']}" + ("" if s["contract_ok"] else f" total {s['contract']} vs {s['want']}")
                       + (f" extra {len(s['extra'])}" if s["extra"] else "") + (f" grp {len(s['gbad'])}" if s["gbad"] else "")
                       + (f" lost {len(s['lost'])}" if s["lost"] else "") + (f" desc {len(s['dbad'])}" if s["dbad"] else "") + (f" alarms {len(alarms)}" if alarms else "") + (f" pct {len(s['pbad'])}" if s["pbad"] else ""))
            if not perfect or s["dbad"]:
                fails.setdefault(b, {})[k] = {"miss": [(m["bill"], m["desc"][:50], m["amount"]) for m in s["miss"][:8]],
                                               "extra": [(x.get("bill"), (x.get("description") or "")[:50], x.get("amount")) for x in s["extra"][:8]],
                                               "gbad": s["gbad"][:5], "pbad": s["pbad"][:5], "lost": s["lost"][:5], "dbad": s["dbad"][:5],
                                               "notes": (raw.get("notes") or [])[:6] if isinstance(raw, dict) else []}
        print("  ".join(row), "|", ", ".join(truth["features"])[:160] if a.v else "")
    print()
    for k, t in tot.items():
        pct = 100.0 * t["ok"] / max(t["lines"], 1)
        print(f"{k:7s} books {t['books']:3d}  perfect {t['perfect']:3d}  lines {t['ok']}/{t['lines']} ({pct:.1f}%)  total right {t['contract_ok']}  "
              f"extra {t['extra']}  groups wrong {t['groups_bad']}  unpriced lost {t['lost']}  desc cut {t['desc_bad']}  crashed {t['crash']}  false alarms {t['alarms']}")
    if a.out:
        json.dump({"tot": tot, "fails": fails}, open(a.out, "w"), indent=1, default=str)


if __name__ == "__main__":
    main_()

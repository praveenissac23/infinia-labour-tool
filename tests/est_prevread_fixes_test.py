"""Previous records reader - the cases found in the 30 Oct 2026 audit:
a fraction (0.0358) before the amount is not the work done; a whole-dirham total (8522) is read so the
certificate's own sums still check; the bill no. is the last number after the revision ("VE207/IPA/03 R1" -> 3).

    cd app && DATABASE_URL=sqlite:////tmp/prf.db INFINIA_NO_SCHED=1 python3 ../tests/est_prevread_fixes_test.py
"""
import os, sys
sys.path.insert(0, os.getcwd())
import main  # noqa: F401  (loads the app modules in order)
import est_prevread as P
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {x}"))
    if not ok: fails.append(n)
ck("bill no. from labels", [P._seq(x) for x in ("VE207/IPA/03 R1", "914-IPA-07", "914/IPC/03", "IPA 07/2026", "IPC 12", "2-R2", "IPA 07 Rev 2")] == [3, 7, 3, 7, 12, 2, 7])
ck("a year alone is not money, 8522 is (loose)", P._amounts("Date 2026", loose=True) == [] and P._amounts("8522", loose=True) == [8522.0] and P._amounts("8522") == [])
lines = [{"c": ["Interim Bill No.", "VE207/IPA/03 R1"]}, {"c": ["Date", "06/10/2026"]}, {"c": ["Total Value of Work done", "0.0358", "", "35471.07"]},
         {"c": ["Less advance recovery", "(7,094.21)"]}, {"c": ["Less retention", "(3,547.11)"]}, {"c": ["Less previous payments", "(16,713.33)"]},
         {"c": ["VAT 5%", "405.82"]}, {"c": ["Total amount due", "8522"]}]
r = P.read_ipa(lines, "")
f = r["fields"]
ck("seq 3, date 06/10/2026, work 35,471.07, total 8,522", (f.get("seq"), f.get("submitted"), f.get("claimed_cum"), f.get("total")) == (3, "2026-10-06", 35471.07, 8522.0), f)
ck("the certificate's own sums are checked and agree", len(r.get("checks", [])) >= 2 and all(c["ok"] for c in r["checks"]), r.get("checks"))
print("ALL PASS" if not fails else f"{len(fails)} FAILED"); sys.exit(1 if fails else 0)

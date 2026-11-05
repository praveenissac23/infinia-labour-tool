"""The bill engine against Excel on consultant-style bills built with every formula a QS uses (5 Nov 2026).

Each workbook: a Measurement sheet (qty, rate, amount, previous / this / cumulative %, certified to date), a Summary
sheet (per-bill sums with cross-sheet references, SUMIF by bill, retention, advance recovery, previous payments,
VAT, rounding) and a Cover sheet (bill no., period dates, text built from figures). LibreOffice works the formulas
out and saves the figures (as Excel would); est_bills_engine.check_against_excel then compares each formula's
figure. Anything the engine does not know or works out differently is listed.

    python3 tests/stress/bill_formulas.py OUT_DIR [--n 12] [--seed 5]
"""
import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from datetime import date

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, "..", "..", "app"))

# formulas over the Measurement sheet (rows 6..N): {r} = the row
LINE_F = [
    "=ROUND(C{r}*D{r},2)", "=C{r}*D{r}", "=IF(C{r}=\"\",0,ROUND(C{r}*D{r},2))", "=IFERROR(C{r}*D{r},0)",
    "=ROUNDUP(C{r}*D{r},2)", "=ROUNDDOWN(C{r}*D{r},2)", "=PRODUCT(C{r},D{r})", "=TRUNC(C{r}*D{r},2)",
]
TODATE_F = ["=F{r}+G{r}", "=SUM(F{r}:G{r})", "=MIN(1,F{r}+G{r})", "=IF(F{r}+G{r}>1,1,F{r}+G{r})", "=MAX(0,MIN(1,F{r}+G{r}))"]
CERT_F = ["=ROUND(E{r}*H{r},2)", "=E{r}*H{r}", "=IF(H{r}=0,0,ROUND(E{r}*H{r},2))", "=IFERROR(ROUND(E{r}*H{r},2),0)",
          "=MROUND(E{r}*H{r},0.01)", "=ROUND(E{r}*H{r}/1,2)"]
THIS_F = ["=I{r}-ROUND(E{r}*F{r},2)", "=ROUND(E{r}*G{r},2)", "=I{r}-E{r}*F{r}"]

SUMMARY_F = [
    ("Work done to date", "=SUM(Measurement!I{a}:I{b})"),
    ("Work done to date (by bills)", "=SUMIF(Measurement!A{a}:A{b},\"B*\",Measurement!I{a}:I{b})+SUMIF(Measurement!A{a}:A{b},\"<>B*\",Measurement!I{a}:I{b})"),
    ("Work done (SUMPRODUCT)", "=ROUND(SUMPRODUCT(Measurement!E{a}:E{b},Measurement!H{a}:H{b}),2)"),
    ("Contract sum", "=SUM(Measurement!E:E)"),
    ("% complete", "=IFERROR(ROUND(C4/C7,4),0)"),
    ("Retention 10%", "=ROUND(C4*10%,2)"),
    ("Retention capped 5% of contract", "=MIN(ROUND(C4*0.1,2),ROUND(C7*0.05,2))"),
    ("Advance recovery", "=IF(C4>0,ROUND(C4*0.1,2),0)"),
    ("Net to date", "=C4-C10-C11"),
    ("Previous payments", "=Cover!C8"),
    ("Due this bill", "=ROUND(C12-C13,2)"),
    ("VAT 5%", "=ROUND(C14*5%,2)"),
    ("Total due", "=C14+C15"),
    ("Rounded total", "=ROUND(C16,0)"),
    ("Floor to 100", "=FLOOR(C16,100)"),
    ("Ceiling to 100", "=CEILING(C16,100)"),
    ("Lines done", "=COUNTIF(Measurement!H{a}:H{b},\">0\")"),
    ("Lines finished", "=COUNTIFS(Measurement!H{a}:H{b},\">=1\",Measurement!E{a}:E{b},\">0\")"),
    ("Lines", "=COUNT(Measurement!E{a}:E{b})"),
    ("Text lines", "=COUNTA(Measurement!B{a}:B{b})"),
    ("Empty rates", "=COUNTBLANK(Measurement!D{a}:D{b})"),
    ("Biggest line", "=MAX(Measurement!E{a}:E{b})"),
    ("Second biggest", "=LARGE(Measurement!E{a}:E{b},2)"),
    ("Smallest line", "=SMALL(Measurement!E{a}:E{b},1)"),
    ("Average line", "=ROUND(AVERAGE(Measurement!E{a}:E{b}),2)"),
    ("Average of done lines", "=ROUND(AVERAGEIF(Measurement!H{a}:H{b},\">0\",Measurement!E{a}:E{b}),2)"),
    ("Look up line 3", "=VLOOKUP(Measurement!A{a3},Measurement!A{a}:I{b},9,FALSE)"),
    ("Index / match", "=INDEX(Measurement!E{a}:E{b},MATCH(Measurement!A{a3},Measurement!A{a}:A{b},0))"),
    ("Subtotal", "=SUBTOTAL(9,Measurement!I{a}:I{b})"),
    ("Subtotal visible", "=SUBTOTAL(109,Measurement!I{a}:I{b})"),
    ("Mod check", "=MOD(ROUND(C4*100,0),7)"),
    ("Sign", "=SIGN(C14)"),
    ("Abs", "=ABS(C14-C13)"),
    ("Power", "=ROUND(POWER(1.05,2)*C14,2)"),
    ("Sqrt", "=ROUND(SQRT(ABS(C14)),4)"),
    ("Int", "=INT(C16)"),
    ("Not / and / or", "=IF(AND(C4>0,NOT(C14<0),OR(C15>0,C15=0)),1,0)"),
    ("Choose", "=CHOOSE(2,C10,C11,C12)"),
    ("Is number", "=IF(ISNUMBER(C14),\"yes\",\"no\")"),
    ("Is blank", "=IF(ISBLANK(Cover!D20),\"blank\",\"filled\")"),
    ("Is error", "=IF(ISERROR(1/0),\"err\",\"ok\")"),
    ("Text of total", "=TEXT(C16,\"#,##0.00\")"),
    ("Words prefix", "=\"AED \"&TEXT(C16,\"#,##0.00\")&\" only\""),
    ("Upper", "=UPPER(Cover!C3)"),
    ("Lower", "=LOWER(Cover!C3)"),
    ("Proper", "=PROPER(Cover!C3)"),
    ("Left", "=LEFT(Cover!C3,4)"),
    ("Right", "=RIGHT(Cover!C3,3)"),
    ("Mid", "=MID(Cover!C3,3,5)"),
    ("Len", "=LEN(Cover!C3)"),
    ("Trim", "=TRIM(\"  a  b \")"),
    ("Concatenate", "=CONCATENATE(\"IPA \",Cover!C4)"),
    ("Value", "=VALUE(\"1250.50\")+1"),
    ("N", "=N(C14)"),
    ("Rows", "=ROWS(Measurement!E{a}:E{b})"),
    ("Columns", "=COLUMNS(Measurement!A{a}:I{a})"),
    ("Bill no. next", "=Cover!C4+1"),
    ("Hlookup", "=HLOOKUP(\"Rate\",Measurement!A5:I{b},3,FALSE)"),
    ("Nested if", "=IF(C6>0.9,\"Final\",IF(C6>0.5,\"Interim - advanced\",\"Interim\"))"),
    ("Compare text", "=IF(Cover!C3=\"VILLA 914\",1,0)"),
    ("Ifs", "=IFS(C6>0.9,3,C6>0.5,2,TRUE,1)"),
    ("Sumifs", "=SUMIFS(Measurement!I{a}:I{b},Measurement!H{a}:H{b},\">0\",Measurement!E{a}:E{b},\">=0\")"),
]
COVER_F = [
    ("Period from", "=DATE(2026,10,1)"),
    ("Period to", "=EOMONTH(C5,0)"),
    ("Next period", "=EDATE(C5,1)"),
    ("Year", "=YEAR(C6)"),
    ("Month", "=MONTH(C6)"),
    ("Day", "=DAY(C6)"),
    ("Days", "=C6-C5+1"),
    ("Days fn", "=DAYS(C6,C5)"),
    ("Working days", "=NETWORKDAYS(C5,C6)"),
    ("Period text", "=TEXT(C5,\"dd/mm/yyyy\")&\" to \"&TEXT(C6,\"dd/mm/yyyy\")"),
    ("Month name", "=TEXT(C6,\"mmmm yyyy\")"),
    ("Weekday", "=WEEKDAY(C6)"),
]


def build(rng, path):
    wb = openpyxl.Workbook()
    cover = wb.active
    cover.title = "Cover"
    cover["B3"], cover["C3"] = "Project", rng.choice(["VILLA 914", "Villa 915 Sobha Hartland", "PRIVATE VILLA - PLOT 347"])
    cover["B4"], cover["C4"] = "Bill no.", rng.randint(1, 12)
    cover["B5"], cover["C5"] = "Period from", date(2026, 10, 1)
    cover["B6"], cover["C6"] = "Period to", date(2026, 10, 31)
    cover["B8"], cover["C8"] = "Previous payments", round(rng.uniform(10000, 400000), 2)
    m = wb.create_sheet("Measurement")
    m.append(["", "", "", "", "", "", "", "", ""])
    m.append(["INTERIM PAYMENT APPLICATION"])
    m.append([])
    m.append([])
    m.append(["Bill", "Description", "Qty", "Rate", "Amount", "Previous %", "This %", "To date %", "Certified to date", "This bill"])
    a = 6
    n = rng.randint(12, 60)
    for i in range(n):
        r = a + i
        q = rng.choice([1, round(rng.uniform(1, 900), 2), rng.randint(2, 300)])
        rt = rng.choice([round(rng.uniform(5, 3000), 2), rng.randint(10, 5000)])
        prev = rng.choice([0, 0.1, 0.25, 0.4, 0.5, 0.75, 1])
        this = 0 if prev >= 1 else rng.choice([0, 0.05, 0.1, 0.2, 0.33, 0.125])
        m.cell(r, 1, rng.choice(["B1", "B2", "B3", "C1"]) + f".{i + 1:02d}")
        m.cell(r, 2, f"Item {i + 1} supply and install")
        m.cell(r, 3, q)
        m.cell(r, 4, rt if rng.random() > 0.05 else None)
        m.cell(r, 5, rng.choice(LINE_F).format(r=r))
        m.cell(r, 6, prev)
        m.cell(r, 7, this)
        m.cell(r, 8, rng.choice(TODATE_F).format(r=r))
        m.cell(r, 9, rng.choice(CERT_F).format(r=r))
        m.cell(r, 10, rng.choice(THIS_F).format(r=r))
    b = a + n - 1
    s = wb.create_sheet("Summary")
    s["B2"] = "SUMMARY"
    for k, (lab, f) in enumerate(SUMMARY_F, 4):
        s.cell(k, 2, lab)
        s.cell(k, 3, f.format(a=a, b=b, a3=a + 2))
    for k, (lab, f) in enumerate(COVER_F, 10):
        cover.cell(k, 2, lab)
        cover.cell(k, 3, f)
    wb.save(path)
    d = tempfile.mkdtemp()
    subprocess.run(["soffice", "--headless", "--calc", "--convert-to", "xlsx:Calc MS Excel 2007 XML", "--outdir", d, path], capture_output=True, timeout=240)
    out = os.path.join(d, os.path.basename(path))
    if os.path.exists(out):
        shutil.move(out, path)
    shutil.rmtree(d, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--seed", type=int, default=5)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    sys.path.insert(0, APP)
    import est_bills_engine as BE
    tot = same = 0
    bad = {}
    for i in range(a.n):
        p = os.path.join(a.out, f"bill_{i:02d}.xlsx")
        build(random.Random(a.seed * 100 + i), p)
        mdl = BE.read_format(open(p, "rb").read(), os.path.basename(p))
        c = BE.check_against_excel(mdl)
        tot += c["formulas"]
        same += c["same"]
        for d in c["different"]:
            key = d["formula"].split("(")[0] if "(" in d["formula"] else d["formula"][:20]
            bad.setdefault(key, d)
        print(f"bill_{i:02d}: {c['same']}/{c['formulas']} formulas give Excel's figure, {c['mismatch']} differ")
    print(f"\nALL: {same}/{tot} ({100.0 * same / max(tot, 1):.2f}%)")
    for k, d in sorted(bad.items()):
        print(f"  {d['sheet']}!{d['cell']}  {d['formula']}  Excel {d['excel']!r}  here {d['here']}")
    json.dump(bad, open(os.path.join(a.out, "bad.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main()

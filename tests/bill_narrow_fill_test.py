"""919's Percentage breakdown: a narrow portrait sheet whose own page break kept it at 60-70% of the page width.
It must print across the page width, on no more pages than before, each page ending between two items.
    cd app && python3 ../tests/bill_narrow_fill_test.py
"""
import os, sys, warnings
warnings.filterwarnings("ignore"); sys.path.insert(0, os.getcwd())
import est_bills_render as BR, est_bills_engine as EN
rowh = {1: 39.75, 2: 21.0, 3: 37.5, 4: 12.75, 5: 12.75, 6: 12.75}
for t in ("7:15.75 8:15 9:15 10:15 11:15 12:15 13:15 14:15 15:12.75 16:15 17:15 18:15 19:15 20:12.75 21:15 22:15 23:12.75 24:15 25:15 "
          "26:15 27:15 28:12.75 29:15 30:15 31:12.75 32:15.75 33:15 34:15 35:15 36:15 37:12.75 38:15 39:15 40:11.25 41:15 42:15 43:15 "
          "44:15 45:12.75 46:15 47:15 48:11.25 49:15 50:15 51:15 52:15 53:12.75 54:15 55:15 56:15").split():
    a, b = t.split(":"); rowh[int(a)] = float(b)
rowh.update({i: 15.0 for i in range(57, 75)})
blank = {5, 6, 15, 23, 31, 40, 48, 56, 63, 69}
cells = {f"{r},{c}": ({"s": 0, "v": "x"} if c == 3 and r not in blank else {"s": 0}) for r in range(1, 75) for c in range(1, 6)}
sh = {"name": "Percentage breakdown", "visible": True, "print_area": [1, 1, 74, 5], "maxr": 74, "maxc": 5, "cells": cells,
      "colw": {"1": 6.25, "2": 7.62, "3": 52.38, "4": 5.12, "5": 8.25}, "rowh": {str(k): v for k, v in rowh.items()},
      "hidden_rows": [], "dcw": 7.5, "drh": 14.25, "merges": [], "fit": True, "landscape": False, "images": [],
      "print": {"paper": 9, "landscape": False, "fit": True, "fw": None, "fh": 0, "scale": 81, "m": [.7, .7, .75, .75, .3, .3],
                "hc": False, "vc": False, "titles": [1, 5], "breaks": [56], "hf": {}}}
model = EN.a4_pages({"sheets": [sh], "map": {"signs": []}, "styles": [{}]})
pl = BR.page_plan(model, model["sheets"][0], {}, None)
used = sum(pl["cw"][c] for c in pl["cols"]) * 0.75 * pl["sc"] / (pl["pw"] - pl["ml"] - pl["mr"])
fails = []
def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {x}")); ok or fails.append(n)
ck("uses at least 90% of the page width", used >= 0.9, round(used, 2))
ck("still 2 pages", len(pl["pages"]) == 2, len(pl["pages"]))
ck("page 1 ends on a blank row (between items)", pl["pages"][0][1][-1] in blank, pl["pages"][0][1][-1])
ck("page 2 repeats the heading rows", pl["pages"][1][0][:5] == [1, 2, 3, 4, 5], pl["pages"][1][0][:6])
ck("Excel gets the same page break", pl.get("soft") == [pl["pages"][0][1][-1]], pl.get("soft"))
print("FAILS:", fails or "none")

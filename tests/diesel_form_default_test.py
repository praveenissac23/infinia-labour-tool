"""Diesel form (13/11/2026): Received comes first and is picked, and 'Straight into a machine' comes before 'Jars / tank'
and is picked - the usual entry for the store keeper. Back to that after each save."""
import os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAIL = []
for page in ("app-classic.html",):   # the script lives here; app.html is built around it
    s = open(os.path.join(ROOT, page), encoding="utf-8").read()
    ok = lambda name, cond: (print(("ok   " if cond else "FAIL ") + page + ": " + name), cond or FAIL.append(name))
    ok("starts on Received, straight into a machine", 'DS_KIND = "in", DS_EDIT = null, DS_DIRECT = true;' in s)
    f = s[s.index("function dsFormDraw()"):s.index("function dsFormDraw()") + 3000]
    ok("Received button before Used", 0 < f.index(">Received</button>") < f.index(">Used</button>"))
    ok("Straight into a machine before Jars / tank", 0 < f.index(">Straight into a machine</button>") < f.index(">Jars / tank</button>"))
    ok("back to the defaults after a save", 'DS_EDIT = null; DS_KIND = "in"; DS_DIRECT = true;' in s)
sys.exit(1 if FAIL else 0)

"""Printed bills: every "TOTAL CARRIED TO COLLECTION / TO COLLECTION / CARRIED FORWARD" row is the last row of its A4
page (never pushed to the next page, never followed by the next page's heading row) - on every sheet of every bill,
the consultant's breaks or not. Runs on the engine directly, no server.
    python3 tests/make_ipa_like_915_div.py /tmp/claude-0/bills/div3.xlsx
    cd app && python3 ../tests/bill_carried_pages_test.py /tmp/claude-0/bills/div3.xlsx"""
import os, sys, re
sys.path.insert(0, os.getcwd())
import est_bills_engine as BE, est_bills_render as BR
f = sys.argv[1] if len(sys.argv) > 1 else "/tmp/claude-0/bills/div3.xlsx"
model = BE.read_format(open(f, "rb").read(), os.path.basename(f))
model = model[0] if isinstance(model, tuple) else model
model = model.get("model", model) if isinstance(model, dict) and "sheets" not in model else model
m = BE.a4_pages(model, {})
CAR = re.compile(r"^\s*(total\s+)?(carried\s+(to|forward|over)|to\s+collection)", re.I)
bad, checked = [], 0
for s in m["sheets"]:
    words = {}
    for k, c in sorted(s["cells"].items(), key=lambda kv: tuple(int(x) for x in kv[0].split(","))):
        v = c.get("v")
        if isinstance(v, str) and v.strip() and not v.startswith("="):
            words.setdefault(int(k.split(",")[0]), v.strip())
    car = {r for r, t in words.items() if CAR.match(t)}
    if not car:
        continue
    pl = BR.page_plan(m, s, {}, None)
    for n, (rows, own) in enumerate(pl["pages"], 1):
        for r in own:
            if r in car:
                checked += 1
                if r != own[-1]:
                    bad.append(f"{s['name']} page {n}: row {r} (carried) has {len(own) - own.index(r) - 1} rows after it")
print(f"{checked} carried rows checked")
for b in bad:
    print("FAIL", b)
print("PASS every carried row ends its page" if not bad and checked else "FAILED")
sys.exit(1 if bad or not checked else 0)

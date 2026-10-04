"""List the materials that went out to sites (issued, moved between
sites, delivered direct) but have no price anywhere in the app - no LPO
line and no cost on a receipt - so a market price can be found for them.

    cd ~/infinia-labour-tool && venv/bin/python deploy/unpriced_items.py

Prints one line per material and writes the same to unpriced_items.csv
in the repo folder. Reads only; changes nothing.
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from clear_test_returns import _find_database_url
from sqlalchemy import create_engine, text

url = _find_database_url()
if not url:
    sys.exit("Could not find DATABASE_URL.")
with create_engine(url).connect() as c:
    items = {r.id: r for r in c.execute(text("SELECT id, code, name, unit, item_type FROM store_items"))}
    by_name = {}
    for i in items.values():
        by_name.setdefault((i.name or "").strip().lower(), i.id)
    priced = set()
    for r in c.execute(text("SELECT l.item_id, l.description, o.status FROM purchase_order_lines l "
                            "JOIN purchase_orders o ON o.id = l.order_id WHERE l.rate > 0")):
        if (r.status or "issued") == "cancelled":
            continue
        iid = r.item_id or by_name.get((r.description or "").strip().lower())
        if iid:
            priced.add(iid)
    priced |= {r[0] for r in c.execute(text("SELECT DISTINCT item_id FROM store_movements WHERE kind = 'in' AND unit_cost > 0"))}
    moved = {}
    for r in c.execute(text("SELECT item_id, qty, unit_cost, kind FROM store_movements WHERE kind IN ('out', 'transfer', 'direct')")):
        if r.item_id in priced or (r.kind == "direct" and (r.unit_cost or 0) > 0):
            continue
        a = moved.setdefault(r.item_id, [0, 0.0])
        a[0] += 1
        a[1] += float(r.qty or 0)
rows = sorted(((items[i].code, items[i].name, items[i].unit, items[i].item_type, n, q)
               for i, (n, q) in moved.items() if i in items), key=lambda t: t[1].lower())
out = os.path.join(HERE, "..", "unpriced_items.csv")
with open(out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["code", "name", "unit", "type", "lines", "qty_moved"])
    w.writerows(rows)
for r in rows:
    print(" | ".join(str(x) for x in r))
print(f"\n{len(rows)} material(s) moved with no price. Saved to {os.path.abspath(out)}")

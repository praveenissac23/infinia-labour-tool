"""Put rough market prices on materials that were never bought through
an LPO, so what went to the sites can be costed.

    cd ~/infinia-labour-tool && venv/bin/python deploy/load_est_prices.py

Prices are in deploy/est_prices.json, found on UAE suppliers' websites
for the exact material (size, make, grade), in AED excluding VAT, per
the material's unit in the app. A price is only put on a material when
both its code and its name are exactly as in the file - a renamed or
re-coded material is skipped and listed, never guessed. Reports show
these as "Estimate"; any real LPO or receipt price always wins.
Running it twice changes nothing more.
"""
import json
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from clear_test_returns import _find_database_url
from sqlalchemy import create_engine, inspect, text

data = json.load(open(os.path.join(HERE, "est_prices.json")))
url = _find_database_url()
if not url:
    sys.exit("Could not find DATABASE_URL.")
engine = create_engine(url)
if "est_price" not in {c["name"] for c in inspect(engine).get_columns("store_items")}:
    sys.exit("The store table is older than this code - restart the app first (sudo systemctl restart infinia).")

norm = lambda s: " ".join(str(s or "").split()).lower()
done, skipped = 0, []
with engine.begin() as c:
    for x in data:
        row = c.execute(text("SELECT id, name, unit FROM store_items WHERE code = :c"), {"c": x["code"]}).first()
        if not row or norm(row.name) != norm(x["name"]):
            skipped.append(f'{x["code"]} {x["name"]}' + (f'  (in the app: {row.name})' if row else "  (no such code)"))
            continue
        c.execute(text("UPDATE store_items SET est_price = :p, est_source = :s, est_on = :d WHERE id = :i"),
                  {"p": float(x["price"]), "s": x.get("source", "")[:300], "d": date.today(), "i": row.id})
        done += 1
print(f"DONE {done} material(s) given an estimated price.")
if skipped:
    print(f"{len(skipped)} skipped - code or name not the same as in the app:")
    for s in skipped:
        print("  ", s)

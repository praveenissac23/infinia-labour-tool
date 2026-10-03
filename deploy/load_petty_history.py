"""Load the petty cash history kept outside the app into
Accounts > Petty cash > Site / PRO / Office.

    cd ~/infinia-labour-tool && venv/bin/python deploy/load_petty_history.py

The lines are in deploy/petty_books_history.json, made by
deploy/parse_petty_history.py from:
  Site    site petty cash till 7th Sept 2026          balance  1,199.95
  Office  Tally company cash book 2025 + company 2026 balance  1,856.64
  PRO     Jomon's petty cash 2025 - Aug 2026, and his
          September 2026 sheet                         balance 23,572.68
Each book is checked against those balances before anything is saved.

Lines already in the app are kept. A line from the files is skipped when
the book already holds one with the same date, side and amount (as many
times as the files have it), so anything typed into the app by hand for
the same days is not doubled, and running this twice adds nothing.
"""
import json
import os
import sys
from collections import Counter
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, HERE)
from clear_test_returns import _find_database_url

FILES = {"site": 1199.95, "office": 1856.64, "pro": 23572.68}
NAMES = {"site": "Site", "office": "Office", "pro": "PRO"}

data = json.load(open(os.path.join(HERE, "petty_books_history.json")))
for book, want in FILES.items():
    bal = round(sum(x["received"] - x["paid"] for x in data[book]), 2)
    print(f"  {NAMES[book]:<7} {len(data[book]):>5} lines in the files, balance {bal:>11,.2f} (expected {want:,.2f})")
    if abs(bal - want) > .005:
        sys.exit("The lines do not come to the files' balance - nothing saved.")

url = _find_database_url()
if not url:
    sys.exit("Could not find DATABASE_URL.")
from sqlalchemy import create_engine, inspect, text

engine = create_engine(url)
if "book" not in {c["name"] for c in inspect(engine).get_columns("petty_cash")}:
    sys.exit("The petty cash table is older than this code - restart the app first (sudo systemctl restart infinia).")

key = lambda d, r, p: (str(d), round(float(r or 0), 2), round(float(p or 0), 2))
book_sql = {"site": "(book = 'site' OR book IS NULL OR book = '')", "office": "book = 'office'", "pro": "book = 'pro'"}
with engine.begin() as c:
    for book in FILES:
        where = book_sql[book]
        have = Counter(key(*r) for r in c.execute(text(f"SELECT on_date, received, paid FROM petty_cash WHERE {where}")))
        before = c.execute(text(f"SELECT COALESCE(SUM(received - paid), 0), COUNT(*) FROM petty_cash WHERE {where}")).one()
        rows, skipped = [], 0
        for x in data[book]:
            k = key(x["date"], x["received"], x["paid"])
            if have[k] > 0:
                have[k] -= 1
                skipped += 1
                continue
            rows.append({"b": book, "d": date.fromisoformat(x["date"]), "s": x["description"], "sup": x["supplier"],
                         "site": x["site"], "r": x["received"], "p": x["paid"]})
        if rows:
            c.execute(text("INSERT INTO petty_cash (book, on_date, description, supplier, site, received, paid) "
                           "VALUES (:b, :d, :s, :sup, :site, :r, :p)"), rows)
        after = c.execute(text(f"SELECT COALESCE(SUM(received - paid), 0), COUNT(*) FROM petty_cash WHERE {where}")).one()
        print(f"DONE {NAMES[book]:<7} had {before[1]} lines ({before[0]:,.2f}); added {len(rows)}, skipped {skipped} already there;"
              f" now {after[1]} lines, balance in hand {after[0]:,.2f}")

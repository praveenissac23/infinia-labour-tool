"""Load Naveen's and Praveen's petty cash sheets into
Accounts > Petty cash > Naveen / Praveen.

    cd ~/infinia-labour-tool && venv/bin/python deploy/load_director_petty_cash.py

Run it after the app has been restarted on the new code. The lines are
in deploy/director_petty_cash.json (made from the two sheets by
deploy/parse_director_petty_cash.py). Before anything is saved, each
book's lines are added up and must come to the balance on the sheet:
Naveen 20,253.65 (17-Sep-26), Praveen 95,302.06 (28-Sep-26).

Safe to run more than once: a book that already has lines is left alone.
"""
import json
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, HERE)
from clear_test_returns import _find_database_url

SHEET = {"naveen": 20253.65, "praveen": 95302.06}

data = json.load(open(os.path.join(HERE, "director_petty_cash.json")))
for book, want in SHEET.items():
    lines = data[book]["lines"]
    bal = round(sum(x["paid"] - x["received"] for x in lines), 2)
    print(f"  {book:<8} {len(lines):>4} lines   balance due {bal:>12,.2f}   sheet {want:>12,.2f}")
    if abs(bal - want) > .005:
        sys.exit("The lines do not come to the sheet's balance - nothing saved.")

url = _find_database_url()
if not url:
    sys.exit("Could not find DATABASE_URL.")
from sqlalchemy import create_engine, inspect, text

engine = create_engine(url)
if "book" not in {c["name"] for c in inspect(engine).get_columns("petty_cash")}:
    sys.exit("The petty cash table is older than this code - restart the app first (sudo systemctl restart infinia), then run this again.")
with engine.begin() as c:
    for book in SHEET:
        have = c.execute(text("SELECT COUNT(*) FROM petty_cash WHERE book=:b"), {"b": book}).scalar()
        if have:
            print(f"  {book}: already has {have} lines - left as it is.")
            continue
        for x in data[book]["lines"]:
            c.execute(text("INSERT INTO petty_cash (book, on_date, description, supplier, site, received, paid) "
                           "VALUES (:b, :d, :s, '', :site, :r, :p)"),
                      {"b": book, "d": date.fromisoformat(x["date"]), "s": x["description"], "site": x["site"],
                       "r": x["received"], "p": x["paid"]})
        print(f"  {book}: {len(data[book]['lines'])} lines added.")
    for book in SHEET:
        bal = c.execute(text("SELECT COALESCE(SUM(paid - received), 0) FROM petty_cash WHERE book=:b"), {"b": book}).scalar()
        print(f"DONE {book}: due to {book.title()} AED {bal:,.2f} (sheet {SHEET[book]:,.2f})")

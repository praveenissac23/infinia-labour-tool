"""Load Shafiq's site petty cash sheet, 8 Sep - 2 Oct 2026, into
Accounts > Petty cash > Site - and the matching AED 1,000 "To Shaiju"
into Jomon's PRO book (11 Sep), which was missing there.

    cd ~/infinia-labour-tool && venv/bin/python deploy/load_petty_site_sep_oct.py

The lines are in deploy/petty_site_sep_oct.json (from SITE PETTY CASH.xlsx).
September "Labour's Salaries & Wages" lines carry the revised head,
"Labour's Benefit for Additional Work", as agreed with accounts.

Site book must stand at 1,199.95 (7 Sep) before loading and 3,477.76 after.
A line already in the app with the same book, date, side and amount is
skipped, so running this twice adds nothing, and anything Amal typed for
the same days is not doubled.
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

data = json.load(open(os.path.join(HERE, "petty_site_sep_oct.json")))
EXPECT_BEFORE, EXPECT_AFTER = 1199.95, 3477.76
url = _find_database_url()
if not url:
    sys.exit("Could not find DATABASE_URL.")
from sqlalchemy import create_engine, text

engine = create_engine(url)
key = lambda d, r, p: (str(d), round(float(r or 0), 2), round(float(p or 0), 2))
book_sql = {"site": "(book = 'site' OR book IS NULL OR book = '')", "pro": "book = 'pro'"}
with engine.begin() as c:
    site_before = c.execute(text(f"SELECT COALESCE(SUM(received - paid), 0) FROM petty_cash WHERE {book_sql['site']} AND on_date <= '2026-09-07'")).scalar()
    print(f"Site book up to 7 Sep: {site_before:,.2f} (expected {EXPECT_BEFORE:,.2f})")
    if abs(float(site_before) - EXPECT_BEFORE) > .005:
        sys.exit("The site book does not stand where the sheet starts - nothing saved. Check with accounts first.")
    for book, lines in data.items():
        where = book_sql[book]
        have = Counter(key(*r) for r in c.execute(text(f"SELECT on_date, received, paid FROM petty_cash WHERE {where}")))
        rows, skipped = [], 0
        for x in lines:
            k = key(x["date"], x["received"], x["paid"])
            if have[k] > 0:
                have[k] -= 1; skipped += 1; continue
            rows.append({"b": book, "d": date.fromisoformat(x["date"]), "s": x["description"], "sup": x["supplier"],
                         "site": x["site"], "r": x["received"], "p": x["paid"]})
        if rows:
            c.execute(text("INSERT INTO petty_cash (book, on_date, description, supplier, site, received, paid) "
                           "VALUES (:b, :d, :s, :sup, :site, :r, :p)"), rows)
        bal = c.execute(text(f"SELECT COALESCE(SUM(received - paid), 0) FROM petty_cash WHERE {where} AND on_date <= '2026-10-02'")).scalar()
        print(f"DONE {book:<5} added {len(rows)}, skipped {skipped} already there; balance to 2 Oct {float(bal):,.2f}"
              + (f" (expected {EXPECT_AFTER:,.2f})" if book == "site" else ""))

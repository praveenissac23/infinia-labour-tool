"""Load the office cash file (920 CASH SOA, balance as on 28.09.26) into
Accounts > Register.

    cd ~/infinia-labour-tool && venv/bin/python deploy/load_cash_register.py

Run it after the app has been restarted on the new code (the restart
makes the register's table). Both sides are checked against the sheet's
own totals before anything is saved, and the balance is printed.

Safe to run more than once: a line already there (same side, date,
description and amount) is skipped.
"""
import os, sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, HERE)
from clear_test_returns import _find_database_url

url = _find_database_url()
if not url:
    sys.exit("Could not find DATABASE_URL.")
from sqlalchemy import create_engine, inspect, text

D = lambda s: date(2000 + int(s[6:8]), int(s[3:5]), int(s[0:2]))     # "11.08.26"
RECEIVED = [
    ("10.08.26", "Receipt from Mr. Yogen Chetan (Advance)", 560000),
    ("04.09.26", "Emkaan 914-915-919 Collection", 474335),
    ("09.09.26", "Receipt from Mr. Gourav 912 Villa (Shaji Sir)", 392000),
    ("12.09.26", "Receipt from 103 Project", 175000),
    ("28.09.26", "Receipt from 103 Project", 50000),
]
PAID = [
    ("11.08.26", "Business Promotion Expenses", 60000, ""),
    ("11.08.26", "Jomon Petty Cash", 15000, ""),
    ("19.08.26", "Ghantoot Payments", 172130, "Cheques"),
    ("19.08.26", "Jomon Petty Cash", 17870, "Paid 190K"),
    ("19.08.26", "Loan Given to John Naduthalakalayil", 200000, "Returned"),
    ("21.08.26", "Supervisor PettyCash (Shyju)", 5000, ""),
    ("21.08.26", "Company Pettycash", 5000, ""),
    ("24.08.26", "AL RAIDA - 911-PC08 Paid", 85000, ""),
    ("09.09.26", "Jomon Petty Cash", 20000, ""),
    ("10.09.26", "Company Pettycash", 10000, ""),
    ("10.09.26", "Paid to Cordoba for 103 project", 155000, ""),
    ("11.09.26", "Paid to Metrabar for Steel Purchase", 153000, ""),
    ("11.09.26", "Company Pettycash", 7000, ""),
    ("11.09.26", "Supervisor PettyCash (Shyju)", 5000, ""),
    ("17.09.26", "Naveen Sir Cash book", 1500, ""),
    ("17.09.26", "Supervisor PettyCash (Shyju)", 5000, ""),
    ("17.09.26", "Jomon Petty Cash", 1500, ""),
    ("17.09.26", "Deposit to ADCB", 469000, ""),
    ("28.09.26", "Paid to Al Raida - 905", 75000, ""),
    ("28.09.26", "Jomon Petty Cash", 15000, ""),
]
SHEET_RECEIVED, SHEET_PAID = 1651335.00, 1477000.00

tr, tp = sum(x[2] for x in RECEIVED), sum(x[2] for x in PAID)
print(f"  received {tr:>14,.2f}   sheet {SHEET_RECEIVED:>14,.2f}")
print(f"  paid out {tp:>14,.2f}   sheet {SHEET_PAID:>14,.2f}")
if abs(tr - SHEET_RECEIVED) > .005 or abs(tp - SHEET_PAID) > .005:
    sys.exit("The lines do not add up to the sheet's totals - nothing saved.")

engine = create_engine(url)
if "cash_register" not in inspect(engine).get_table_names():
    sys.exit("The register's table is not there yet - restart the app first (sudo systemctl restart infinia), then run this again.")
added = skipped = 0
with engine.begin() as c:
    for kind, rows in (("received", [r + ("",) for r in RECEIVED]), ("paid", PAID)):
        for d, desc, amt, rem in rows:
            have = c.execute(text("SELECT COUNT(*) FROM cash_register WHERE kind=:k AND on_date=:d AND description=:s AND ABS(amount-:a) < 0.005"),
                             {"k": kind, "d": D(d), "s": desc, "a": amt}).scalar()
            if have:
                skipped += 1
                continue
            c.execute(text("INSERT INTO cash_register (kind, on_date, description, amount, remarks) VALUES (:k, :d, :s, :a, :r)"),
                      {"k": kind, "d": D(d), "s": desc, "a": amt, "r": rem})
            added += 1
    bal = c.execute(text("SELECT COALESCE(SUM(CASE WHEN kind='received' THEN amount ELSE -amount END), 0) FROM cash_register")).scalar()
print(f"\nDONE: {added} added, {skipped} already there. Register balance now AED {bal:,.2f} "
      f"(sheet: balance as on 28.09.26 = {SHEET_RECEIVED - SHEET_PAID:,.2f}).")

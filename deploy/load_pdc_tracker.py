"""Load the accountant's Supplier Tracker (Oct 2026 - Jan 2027) into
Expiry Reminder > PDCs.

    cd ~/infinia-labour-tool && venv/bin/python deploy/load_pdc_tracker.py

Each amount goes in under its month. Only three days are written on the
sheet - Bin Bishr rent 1 Dec, the labour camp 5 Dec, SEOMAA's October
cheque 19/10/26 - so those get their date; every other line is marked
"date to fill" (the screens say so, and the bell asks for them) until
the accountant opens it and puts the cheque date in.

Safe to run more than once: a line already loaded (same payee, month and
amount) is skipped. The month totals are checked against the sheet's own
TOTAL line before anything is saved.
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
os.environ["DATABASE_URL"] = url
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
import models

OCT, NOV, DEC, JAN = date(2026, 10, 1), date(2026, 11, 1), date(2026, 12, 1), date(2027, 1, 1)
# payee, note, [(month, amount, exact day or None)]
SHEET = [
    ("Office Rent - Bin Bishr", "Office rent", [(DEC, 16590.00, 1)]),
    ("New Labour Camp", "6 month rental", [(DEC, 324000.00, 5)]),
    ("Pergola UAE", "905, 906", [(OCT, 124246.50, None)]),
    ("Uni Mix Block", "", [(OCT, 3880.80, None), (NOV, 26384.40, None)]),
    ("Al Raha International", "2nd week", [(OCT, 14001.75, None)]),
    ("Gemini Building Materials", "First week", [(OCT, 5646.64, None)]),
    ("Rashidco", "", [(NOV, 3360.00, None)]),
    ("High Life Trading", "", [(NOV, 6982.50, None)]),
    ("Desarch Scaffolding", "", [(OCT, 24810.63, None), (NOV, 28080.51, None)]),
    ("SEOMAA Building", "", [(OCT, 48596.10, 19), (NOV, 3977.40, None)]),
    ("Al Refada Alum", "2% final", [(OCT, 443.00, None)]),
    ("Vital Technologies", "50% - 906", [(OCT, 24465.00, None)]),
    ("Bin Dasmal Doors", "Final 30% payment", [(OCT, 4882.50, None)]),
    ("Zain Sports", "906-PC03", [(OCT, 9121.00, None)]),
    ("Salary (approx.)", "Monthly salaries - approximate", [(OCT, 380000.00, None), (NOV, 380000.00, None),
                                                            (DEC, 380000.00, None), (JAN, 380000.00, None)]),
]
SHEET_TOTALS = {OCT: 640093.92, NOV: 448784.81, DEC: 720590.00, JAN: 380000.00}

got = {}
for _, _, lines in SHEET:
    for m, amt, _ in lines:
        got[m] = round(got.get(m, 0) + amt, 2)
for m, want in SHEET_TOTALS.items():
    flag = "ok" if abs(got.get(m, 0) - want) < 0.01 else "DIFFERENT"
    print(f"  {m:%b-%y}: lines add to {got.get(m, 0):>12,.2f}   sheet total {want:>12,.2f}   {flag}")
if any(abs(got.get(m, 0) - w) >= 0.01 for m, w in SHEET_TOTALS.items()):
    sys.exit("The lines do not add up to the sheet's totals - nothing saved.")

engine = create_engine(url)
models.Pdc.__table__.create(bind=engine, checkfirst=True)
if "date_tbc" not in {c["name"] for c in inspect(engine).get_columns("pdcs")}:
    with engine.begin() as c:
        c.execute(text("ALTER TABLE pdcs ADD COLUMN date_tbc BOOLEAN"))
        c.execute(text("UPDATE pdcs SET date_tbc = FALSE WHERE date_tbc IS NULL"))
db = sessionmaker(bind=engine)()
added = skipped = 0
for payee, note, lines in SHEET:
    for m, amt, day in lines:
        d = m.replace(day=day) if day else m
        have = [x for x in db.query(models.Pdc).filter(models.Pdc.payee == payee).all()
                if x.cheque_date.year == m.year and x.cheque_date.month == m.month and abs((x.amount or 0) - amt) < 0.01]
        if have:
            skipped += 1
            continue
        db.add(models.Pdc(payee=payee, cheque_date=d, date_tbc=not day, amount=amt, notes=note, status="pending"))
        added += 1
        print(f"  added  {payee:28} {m:%b-%y} {amt:>12,.2f}   {d:%d-%b-%y}" if day else
              f"  added  {payee:28} {m:%b-%y} {amt:>12,.2f}   date to fill")
db.commit()
print(f"\nDONE: {added} added, {skipped} already there. Open Expiry Reminder > PDCs - "
      f"the 'Date to fill' box lists the cheques waiting for their date.")

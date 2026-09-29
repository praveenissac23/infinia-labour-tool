"""Load the company vehicles' expiries (04.Expiry_Tracker-Vehicles.xlsx)
into Expiry Reminder > Company & other documents.

    cd ~/infinia-labour-tool && venv/bin/python deploy/load_vehicle_expiries.py

Safe to run more than once: a vehicle's document already on file is
updated to the date below, never added twice. Nothing else is touched.
Mulkiya, insurance and advertising permit for each vehicle; blanks in
the sheet (no advertising permit) are left out.
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
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import models

D = date
# vehicle, plate, mulkiya, insurance, advertising permit (spelling of the
# makes corrected: MISTUBISHI -> Mitsubishi, RANGER (R)OVER -> Range Rover)
VEHICLES = [
    ("Nissan Sentra", "48522", D(2027, 9, 7), D(2027, 10, 7), None),
    ("Mitsubishi Fuso", "Z 18382", D(2026, 12, 28), D(2027, 1, 28), D(2026, 10, 2)),
    ("Mitsubishi Rosa", "G 30341", D(2027, 5, 5), D(2027, 6, 5), D(2027, 6, 5)),
    ("Mitsubishi L200", "D 38023", D(2027, 7, 24), D(2027, 8, 24), D(2026, 10, 2)),
    ("Mitsubishi Fuso 2", "M 28679", D(2027, 5, 24), D(2027, 6, 24), D(2026, 10, 2)),
    ("Ashok Leyland Falcon", "D 22075", D(2027, 7, 6), D(2027, 8, 6), D(2027, 7, 24)),
    ("Range Rover", "L 8394", D(2026, 10, 6), D(2026, 11, 6), None),
    ("Toyota Prado", "FF 70844", D(2027, 2, 11), D(2027, 3, 11), None),
    ("MG HS", "V 35075", D(2027, 4, 7), D(2027, 5, 7), None),
    ("Range Rover Sport", "F 17037", D(2027, 4, 7), D(2027, 5, 7), None),
    ("BMW", "Y 70420", D(2027, 9, 6), D(2027, 10, 6), None),
]
KINDS = ("Registration (Mulkiya)", "Insurance", "Advertising permit")

engine = create_engine(url)
# The table arrives with the app update; made here too if the app has not restarted yet.
models.CompanyExpiry.__table__.create(bind=engine, checkfirst=True)
db = sessionmaker(bind=engine)()
added = updated = same = 0
for name, plate, *dates in VEHICLES:
    item = f"{name} - {plate}"
    for kind, when in zip(KINDS, dates):
        if not when:
            continue
        x = (db.query(models.CompanyExpiry)
               .filter(models.CompanyExpiry.item == item, models.CompanyExpiry.kind == kind).first())
        if x and x.expires_on == when:
            same += 1
            continue
        if x:
            print(f"  updated  {item:34} {kind:24} {x.expires_on} -> {when}")
            x.expires_on = when
            updated += 1
        else:
            db.add(models.CompanyExpiry(category="Vehicle", item=item, kind=kind,
                                        number=plate, expires_on=when, notes=""))
            print(f"  added    {item:34} {kind:24} {when:%d %b %Y}")
            added += 1
db.commit()
print(f"\nDONE: {added} added, {updated} updated, {same} already on file - "
      f"{len(VEHICLES)} vehicles. See Expiry Reminder > Company & other documents.")

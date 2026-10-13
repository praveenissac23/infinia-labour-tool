"""Send to Zoho, 13 Oct 2026: October lines that are already in Zoho.

Before the portal sent anything, the chief accountant had typed most of
October's office petty cash, the site book's 2 Oct lines and two PRO
top-ups into Zoho by hand. Those lines are marked "already in Zoho" so
they never go a second time. Each is checked by its amount first; a line
changed since 13 Oct is left waiting for the chief accountant to look at.

    cd ~/infinia-labour-tool && venv/bin/python deploy/zoho_mark_existing_oct13.py
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, HERE)
from clear_test_returns import _find_database_url

url = os.environ.get("DATABASE_URL") or _find_database_url()
if not url:
    sys.exit("Could not find DATABASE_URL.")
os.environ["DATABASE_URL"] = url
os.environ.setdefault("INFINIA_NO_PUSH", "1")
import main as M          # noqa: E402
import models             # noqa: E402
from database import SessionLocal  # noqa: E402

M._add_missing_columns()

# id: (amount, note shown on the line)
IN_ZOHO = {
    # Office petty cash -> Zoho "Company Petty Cash" (expenses / payments made)
    434: (120, ""), 2880: (76, ""), 2881: (151.35, ""), 2905: (613.2, ""), 435: (120, ""), 436: (140, ""),
    437: (120, ""), 2871: (120, ""), 2882: (56.25, ""), 2890: (6867, ""), 2906: (262.5, ""), 2884: (900, ""),
    2888: (674.5, ""), 2889: (5800, ""), 2899: (105.84, ""), 2900: (1121.67, ""), 2901: (233, ""), 2902: (143.08, ""),
    2911: (200, ""), 2907: (2500, ""), 2903: (210, ""), 2904: (90, ""), 2908: (450, ""), 2909: (270, ""),
    2914: (5320, ""), 2915: (500, ""), 2929: (120, ""), 2989: (120, ""), 3008: (140, ""), 3012: (65.9, ""),
    3010: (619.5, ""), 3013: (86.39, ""), 3014: (66.05, ""), 3015: (600, ""), 3018: (40, ""), 3020: (19.5, ""),
    3032: (260, ""),
    2898: (188.62, "In Zoho as 168.62 - check"),
    3009: (200, "In Zoho as paid from ADCB - check"),
    # Site petty cash 2 Oct -> Zoho "Site Petty Cash" (itemized, 7 lines)
    2967: (20, ""), 2968: (50, ""), 2969: (91, ""), 2970: (140, ""), 2971: (268, ""), 2972: (724.75, ""), 2973: (126, ""),
    # PRO petty cash top-ups -> Zoho "Jomon Petty Cash"
    3021: (15000, "Transfer Fund PHUB732297071"),
    2875: (5000, "Journal 01-10-26-JOMON"),
}

db = SessionLocal()
done, left = 0, []
for pid, (amt, note) in IN_ZOHO.items():
    x = db.get(models.PettyCash, pid)
    if not x:
        left.append(f"#{pid} not found")
        continue
    if (x.zoho_status or "") != "":
        continue
    if abs(((x.paid or 0) or (x.received or 0)) - amt) > 0.005:
        left.append(f"#{pid} {x.description[:40]} is now {(x.paid or 0) or (x.received or 0):,.2f} (was {amt:,.2f}) - left waiting")
        continue
    x.zoho_status = "inzoho"
    x.zoho_ref = note or "Typed in Zoho before the link"
    done += 1
db.commit()
print(f"Marked already in Zoho: {done}.")
for m in left:
    print("  " + m)

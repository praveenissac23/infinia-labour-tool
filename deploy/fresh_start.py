"""Clear the test data before going live, keeping the master lists.

    cd ~/infinia-labour-tool/app
    python3 ../deploy/fresh_start.py            # show what would go
    python3 ../deploy/fresh_start.py --confirm  # actually do it

KEPT   workers (with their company), sites, engineers, the material
       list, and every staff login.
GONE   attendance, payroll summaries, salary adjustments, stock
       movements, material requests and their lines, suppliers, the
       activity log, and old backups.

A full backup is written to a file first, so today's test data can be
put back if something was needed after all. This is deliberately a
script rather than a button: clearing the company's records should take
a decision at the keyboard, not a stray click.
"""
import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/../app")
sys.path.insert(0, ".")

import database
import models
import main

CONFIRM = "--confirm" in sys.argv
KEEP_SUPPLIERS = "--keep-suppliers" in sys.argv

# Cleared child-first, so nothing is left pointing at a deleted row.
TO_CLEAR = [
    ("material_request_lines", models.MaterialRequestLine, "request lines"),
    ("material_requests",      models.MaterialRequest,     "material requests"),
    ("store_movements",        models.StoreMovement,       "stock movements"),
    ("salary_adjustments",     models.SalaryAdjustment,    "salary adjustments"),
    ("employee_summaries",     models.EmployeeSummary,     "payroll summaries"),
    ("daily_rows",             models.DailyRow,            "attendance days"),
    ("audit_log",              models.AuditLog,            "activity log entries"),
    ("backups",                models.Backup,              "stored backups"),
]
if not KEEP_SUPPLIERS:
    TO_CLEAR.insert(3, ("suppliers", models.Supplier, "suppliers"))

KEPT = [
    (models.Employee,  "workers"),
    (models.Site,      "sites"),
    (models.Engineer,  "engineers"),
    (models.StoreItem, "materials in the item list"),
    (models.User,      "staff logins"),
]

db = database.SessionLocal()
try:
    print("\nWHAT WILL BE KEPT")
    for model, label in KEPT:
        print(f"   {db.query(model).count():>7,}  {label}")
    if KEEP_SUPPLIERS:
        print(f"   {db.query(models.Supplier).count():>7,}  suppliers")

    print("\nWHAT WILL BE CLEARED")
    total = 0
    for _, model, label in TO_CLEAR:
        n = db.query(model).count()
        total += n
        print(f"   {n:>7,}  {label}")
    print(f"   {total:>7,}  rows in total")

    if not CONFIRM:
        print("\nNothing has been changed. Run again with --confirm to clear it:")
        print("   python3 ../deploy/fresh_start.py --confirm\n")
        raise SystemExit(0)

    # A copy of everything first. Going live tomorrow is exactly when
    # someone remembers they needed one of today's figures.
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    path = os.path.abspath(f"../before_fresh_start_{stamp}.json")
    with open(path, "w") as f:
        json.dump(main.build_backup_data(db), f, default=str)
    print(f"\nBackup written to {path} ({os.path.getsize(path):,} bytes)")

    for _, model, label in TO_CLEAR:
        n = db.query(model).delete(synchronize_session=False)
        print(f"   cleared {n:>7,}  {label}")
    db.commit()

    print("\nDONE. What is left:")
    for model, label in KEPT:
        print(f"   {db.query(model).count():>7,}  {label}")
    if KEEP_SUPPLIERS:
        print(f"   {db.query(models.Supplier).count():>7,}  suppliers")
    print("\nMaterial request numbering starts again at MR-0001.")
    print("Take a fresh backup once real data is in.\n")
finally:
    db.close()

"""Test fixture for petty_directors_test.js - never run against the live database.

    python3 tests/fixtures_directors_petty.py /tmp/run_js.db

Puts the browser test's copy of the database in the state the test is written for, whatever copy it is:
the directors' books hold exactly their two sheets (deploy/director_petty_cash.json, loaded by
deploy/load_director_petty_cash.py - Naveen 20,253.65, Praveen 95,302.06), and the chief accountant's
login has the Office, Naveen and Praveen boxes (not the site's or the PRO's), as the upgrade gave him.
"""
import os
import sqlite3
import subprocess
import sys

db = sys.argv[1] if len(sys.argv) > 1 else "/tmp/run_js.db"
if not db.startswith("/tmp/"):
    sys.exit("A test fixture: only a database under /tmp is changed.")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cx = sqlite3.connect(db)
cx.execute("DELETE FROM petty_cash WHERE book IN ('naveen', 'praveen')")
row = cx.execute("SELECT id, permissions FROM users WHERE username = 'chiefacc'").fetchone()
if row:
    keep = [k for k in (row[1] or "").split(",") if k and k not in ("petty_site", "petty_pro")]
    keep += [k for k in ("petty_office", "petty_naveen", "petty_praveen") if k not in keep]
    cx.execute("UPDATE users SET permissions = ? WHERE id = ?", (",".join(keep), row[0]))
cx.commit(); cx.close()
subprocess.run([sys.executable, os.path.join(ROOT, "deploy", "load_director_petty_cash.py")], check=True,
               env={**os.environ, "DATABASE_URL": "sqlite:///" + db}, cwd=ROOT)

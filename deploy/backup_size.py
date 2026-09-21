"""What the backups actually take up on this server, and what is in them.

Run on the server:
    cd ~/infinia-labour-tool/app && ../venv/bin/python ../deploy/backup_size.py

Finds the database the live service uses by itself - the connection
settings live in the systemd unit, not in a shell, so running this by
hand would otherwise fall back to a default that has no password.
"""
import os, re, subprocess, sys


def _find_database_url():
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    # What the running service was actually started with.
    for unit in ("infinia", "infinia.service"):
        try:
            out = subprocess.run(["systemctl", "show", unit, "-p", "Environment", "--value"],
                                 capture_output=True, text=True, timeout=10).stdout
            m = re.search(r"DATABASE_URL=(\S+)", out or "")
            if m:
                return m.group(1)
            out = subprocess.run(["systemctl", "show", unit, "-p", "EnvironmentFiles", "--value"],
                                 capture_output=True, text=True, timeout=10).stdout
            for path in re.findall(r"(/\S+?)(?:\s|$)", out or ""):
                path = path.rstrip("()").lstrip("-")
                if os.path.exists(path):
                    for line in open(path):
                        if line.strip().startswith("DATABASE_URL="):
                            return line.split("=", 1)[1].strip().strip("'\"")
        except Exception:
            pass
    # A .env beside the code, if one is used instead.
    here = os.path.dirname(os.path.abspath(__file__))
    for env in (os.path.join(here, "..", ".env"), os.path.join(here, "..", "app", ".env")):
        if os.path.exists(env):
            for line in open(env):
                if line.strip().startswith("DATABASE_URL="):
                    return line.split("=", 1)[1].strip().strip("'\"")
    return None


_url = _find_database_url()
if not _url:
    sys.exit("Could not find DATABASE_URL. Run:  sudo systemctl show infinia -p Environment\n"
             "then run this again with it in front:  DATABASE_URL='...' ../venv/bin/python ../deploy/backup_size.py")
os.environ["DATABASE_URL"] = _url
print(f"Reading the live database ({_url.split('@')[-1] if '@' in _url else _url})\n")

import sys; sys.path.insert(0, '.')
import database, models, main
from sqlalchemy import func
d = database.SessionLocal()
rows = d.query(models.Backup.id, models.Backup.trigger, models.Backup.created_at,
               func.length(models.Backup.data)).order_by(models.Backup.created_at.desc()).all()
total = sum(r[3] or 0 for r in rows)
auto = [r for r in rows if r[1] == 'auto']
print(f"Backups held: {len(rows)}  ({len(auto)} automatic, {len(rows)-len(auto)} manual or pre-change)")
print(f"Space they take: {total/1e6:.1f} MB")
if rows:
    newest = rows[0]
    print(f"Newest: #{newest[0]} {newest[1]} {newest[2]:%d %b %Y}  -  {(newest[3] or 0)/1e6:.2f} MB stored")
    print(f"Average: {total/len(rows)/1e6:.2f} MB each")
print("\nLast 10:")
for r in rows[:10]:
    print(f"  #{r[0]:<5} {r[1]:<8} {r[2]:%d %b %Y}   {(r[3] or 0)/1e6:>7.2f} MB")
counts = [(m.__tablename__, d.query(m).count()) for _, m in main._backup_models()]
print("\nRows in the live data:")
for name, n in sorted(counts, key=lambda x: -x[1]):
    if n: print(f"  {name:<24} {n:>9,}")
print(f"  {'TOTAL':<24} {sum(n for _, n in counts):>9,}")
d.close()

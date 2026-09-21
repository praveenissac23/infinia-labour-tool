"""What the backups actually take up on this server, and what is in them.

Run on the server:
    cd ~/infinia-labour-tool/app && python3 ../deploy/backup_size.py

Uses the application's own database settings, so there are no passwords
to type and nothing to configure.
"""
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

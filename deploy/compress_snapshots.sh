#!/bin/bash
# One-time (14/11/2026): the automatic daily snapshots were stored uncompressed - ~400 MB each, 7 of them 2.8 GB of
# text. This packs each one (gzip, the same way the app now stores them - it reads both), one at a time, then gives
# the freed space back to the disk. Nothing is deleted; every snapshot still restores the same.
#   sudo bash ~/infinia-labour-tool/deploy/compress_snapshots.sh
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PID="$(systemctl show infinia -p MainPID --value)"
DB_URL="$(tr '\0' '\n' < /proc/$PID/environ 2>/dev/null | grep '^DATABASE_URL=' | cut -d= -f2-)"
[ -n "$DB_URL" ] || { echo "Could not find the app's DATABASE_URL - nothing changed."; exit 1; }
PY="$(dirname "$(systemctl show infinia -p ExecStart --value | grep -o '/[^ ]*/bin/[^ ;]*' | head -1)")/python"
[ -x "$PY" ] || PY=python3
DATABASE_URL="$DB_URL" "$PY" - <<'PYEOF'
import base64, gc, gzip, os
from sqlalchemy import create_engine, text
PREFIX = "gz:"
e = create_engine(os.environ["DATABASE_URL"].replace("postgresql+psycopg2://", "postgresql://", 1)
                  if os.environ["DATABASE_URL"].startswith("postgresql+psycopg2://") else os.environ["DATABASE_URL"])
with e.connect() as c:
    ids = [r[0] for r in c.execute(text("select id from backups where left(data, 3) <> :p order by id"), {"p": PREFIX})]
print(f"{len(ids)} snapshot(s) to pack")
for i in ids:
    with e.begin() as c:
        raw = c.execute(text("select data from backups where id = :i"), {"i": i}).scalar()
        packed = PREFIX + base64.b64encode(gzip.compress(raw.encode("utf-8"), 6)).decode("ascii")
        if len(packed) < len(raw):
            c.execute(text("update backups set data = :d where id = :i"), {"d": packed, "i": i})
            print(f"  #{i}: {len(raw)/1e6:.0f} MB -> {len(packed)/1e6:.0f} MB")
    raw = packed = None; gc.collect()
PYEOF
DB_NAME="$(echo "$DB_URL" | sed -E 's#.*/([^/?]+)(\?.*)?$#\1#')"
sudo -u postgres psql -d "$DB_NAME" -At -c "vacuum full backups;" -c "select 'snapshots now ' || pg_size_pretty(pg_total_relation_size('backups'));"
df -h / | tail -1

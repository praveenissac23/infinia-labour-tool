#!/bin/bash
# Nightly copy of the whole database into one file, made just before the
# Acronis backup (12 AM Dubai), so every Acronis backup holds a clean,
# restorable copy of all app data.
#
# Run by the infinia-dbdump systemd timer (11:30 PM Dubai). Install once:
#   sudo bash ~/infinia-labour-tool/deploy/install-db-dump.sh
# Run by hand any time:
#   sudo bash ~/infinia-labour-tool/deploy/nightly_db_dump.sh
#
# Reads the database only - nothing in the app or database is changed.
# Keeps the newest 2 files in /var/backups/infinia-db (Acronis keeps the
# history), so it uses very little disk.
set -uo pipefail

DEST=/var/backups/infinia-db
KEEP=2
DAY="$(TZ=Asia/Dubai date +%Y-%m-%d)"
OUT="$DEST/infinia-$DAY.dump"
fail() { echo "DB DUMP FAILED: $*"; rm -f "$OUT.part"; exit 1; }

# ---- find the database the app uses (same place the app reads it) ---------
DB_URL="${DATABASE_URL:-}"
if [ -z "$DB_URL" ]; then
  PID="$(systemctl show infinia -p MainPID --value 2>/dev/null)"
  [ -n "$PID" ] && [ "$PID" != "0" ] && \
    DB_URL="$(tr '\0' '\n' < /proc/$PID/environ 2>/dev/null | grep '^DATABASE_URL=' | cut -d= -f2-)"
fi
if [ -z "$DB_URL" ]; then
  DB_URL="$(systemctl show infinia -p Environment --value 2>/dev/null | grep -o 'DATABASE_URL=[^ ]*' | cut -d= -f2-)"
fi
if [ -z "$DB_URL" ]; then
  for f in $(systemctl show infinia -p EnvironmentFiles --value 2>/dev/null | grep -o '/[^ ]*'); do
    [ -f "$f" ] && DB_URL="$(grep -m1 '^DATABASE_URL=' "$f" | cut -d= -f2- | tr -d "\"'")"
    [ -n "$DB_URL" ] && break
  done
fi
[ -n "$DB_URL" ] || fail "could not find the app's DATABASE_URL"
case "$DB_URL" in postgresql+psycopg2://*) DB_URL="postgresql://${DB_URL#postgresql+psycopg2://}";; esac

# ---- dump, check it reads back, then swap in ------------------------------
mkdir -p "$DEST" && chmod 700 "$DEST"
pg_dump "$DB_URL" -Fc -f "$OUT.part" 2>/tmp/infinia-dbdump.err || fail "$(cat /tmp/infinia-dbdump.err)"
N=$(pg_restore --list "$OUT.part" 2>/dev/null | grep -c "TABLE DATA")
[ "$N" -gt 5 ] || fail "dump looks empty ($N tables)"
mv -f "$OUT.part" "$OUT" && chmod 600 "$OUT"
rm -f /tmp/infinia-dbdump.err

# ---- keep only the newest $KEEP files --------------------------------------
ls -1 "$DEST"/infinia-*.dump 2>/dev/null | sort -r | tail -n +$((KEEP + 1)) | xargs -r rm -f

echo "DB dump OK: $OUT  $(du -h "$OUT" | cut -f1)  ($N tables)"

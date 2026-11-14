#!/bin/bash
# One-time clean-up so the Acronis backup fits its 20 GB (14/11/2026). Run on the VPS:
#   sudo bash ~/infinia-labour-tool/deploy/shrink_disk.sh
#
# What it does - nothing the app or its users need is touched:
#   1. In-app daily snapshots: keeps the newest 7 automatic ones (manual ones are never removed), then gives the freed
#      space back to the disk (Postgres keeps it otherwise).
#   2. System logs: trimmed to 100 MB and kept at that size.
#   3. Nightly database copy: made again without the in-app snapshots (much smaller); older copies removed.
#   4. Test copy (staging): refreshed without the in-app snapshots.
#   5. Downloaded package files: cleared.
# Shows the disk before and after.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
say() { echo; echo "== $*"; }

# the app's database, found the same way as the nightly dump does
DB_URL="$(systemctl show infinia -p MainPID --value 2>/dev/null | xargs -I{} sh -c 'tr "\0" "\n" < /proc/{}/environ 2>/dev/null' | grep '^DATABASE_URL=' | cut -d= -f2-)"
if [ -z "$DB_URL" ]; then
  for f in $(systemctl show infinia -p EnvironmentFiles --value 2>/dev/null | grep -o '/[^ ]*'); do
    [ -f "$f" ] && DB_URL="$(grep -m1 '^DATABASE_URL=' "$f" | cut -d= -f2- | tr -d "\"'")"; [ -n "$DB_URL" ] && break
  done
fi
[ -n "$DB_URL" ] || { echo "Could not find the app's DATABASE_URL - nothing changed."; exit 1; }
case "$DB_URL" in postgresql+psycopg2://*) DB_URL="postgresql://${DB_URL#postgresql+psycopg2://}";; esac
DB_NAME="$(echo "$DB_URL" | sed -E 's#.*/([^/?]+)(\?.*)?$#\1#')"
psql_db() { sudo -u postgres psql -d "$DB_NAME" -At "$@"; }

say "Before"
df -h / | tail -1
sudo -u postgres psql -At -c "select datname, pg_size_pretty(pg_database_size(datname)) from pg_database where datname not like 'template%' order by 2 desc;"
psql_db -c "select 'in-app snapshots: ' || count(*) || ' (' || pg_size_pretty(pg_total_relation_size('backups')) || ')' from backups;"

say "1. In-app snapshots: keep the newest 7 automatic ones (manual ones stay)"
psql_db -c "delete from backups where trigger in ('auto','daily') and id not in (select id from backups where trigger in ('auto','daily') order by created_at desc limit 7);"
psql_db -c "vacuum full backups;" && echo "space given back"
psql_db -c "select 'now: ' || count(*) || ' snapshots (' || pg_size_pretty(pg_total_relation_size('backups')) || ')' from backups;"

say "2. System logs: 100 MB"
mkdir -p /etc/systemd/journald.conf.d
printf '[Journal]\nSystemMaxUse=100M\n' > /etc/systemd/journald.conf.d/size.conf
systemctl restart systemd-journald
journalctl --vacuum-size=100M 2>&1 | tail -1

say "3. Nightly database copy, without the snapshots"
if bash "$REPO/deploy/nightly_db_dump.sh"; then
  ls -1t /var/backups/infinia-db/infinia-*.dump 2>/dev/null | tail -n +2 | xargs -r rm -f
  ls -lh /var/backups/infinia-db/
fi

say "4. Test copy (staging), without the snapshots"
if [ -f "$REPO/deploy/staging_refresh.sh" ] && systemctl list-unit-files | grep -q infinia-staging; then
  bash "$REPO/deploy/staging_refresh.sh" 2>&1 | tail -2
fi

say "5. Downloaded package files"
apt-get clean

say "After"
df -h / | tail -1
sudo -u postgres psql -At -c "select datname, pg_size_pretty(pg_database_size(datname)) from pg_database where datname not like 'template%' order by 2 desc;"
du -sh /var/backups/* 2>/dev/null | sort -rh | head -5
echo
echo "Done. In Acronis (BigRock panel > Server backups > Manage) also exclude /swapfile and set retention to 15 days."

#!/bin/bash
# Test copy of the app ("staging"): refresh its database from live, then restart it.
# Run by the infinia-staging-refresh timer at 4:00 AM Dubai, or by hand any time:
#   sudo bash ~/infinia-labour-tool/deploy/staging_refresh.sh
#
# Live is only READ (pg_dump). The copy goes into the separate database infinia_staging, and then:
#   - Zoho is disconnected on the copy, so nothing on the test copy can reach Zoho Books;
#   - the test copy runs with no mail server, no phone notifications and no scheduled jobs (see the service).
set -uo pipefail
STAGE_DB=infinia_staging
fail() { echo "STAGING REFRESH FAILED: $*"; exit 1; }

LIVE_URL="$(tr '\0' '\n' < /proc/$(systemctl show infinia -p MainPID --value)/environ 2>/dev/null | grep '^DATABASE_URL=' | cut -d= -f2-)"
[ -n "$LIVE_URL" ] || LIVE_URL="$(systemctl show infinia -p Environment --value | grep -o 'DATABASE_URL=[^ ]*' | cut -d= -f2-)"
[ -n "$LIVE_URL" ] || fail "could not find the live DATABASE_URL (is the infinia service running?)"
case "$LIVE_URL" in postgresql+psycopg2://*) LIVE_URL="postgresql://${LIVE_URL#postgresql+psycopg2://}";; esac
LIVE_DB="${LIVE_URL##*/}"; LIVE_DB="${LIVE_DB%%\?*}"
[ "$LIVE_DB" != "$STAGE_DB" ] || fail "live and staging are the same database"
OWNER="$(echo "$LIVE_URL" | sed -E 's#^[a-z]+://([^:@/]+).*#\1#')"

TMP=/tmp/infinia-staging.dump
pg_dump "$LIVE_URL" -Fc -f "$TMP" 2>/tmp/infinia-staging.err || fail "pg_dump: $(cat /tmp/infinia-staging.err)"
systemctl stop infinia-staging 2>/dev/null || true
sudo -u postgres psql -q -c "DROP DATABASE IF EXISTS $STAGE_DB;" -c "CREATE DATABASE $STAGE_DB OWNER \"$OWNER\";" || fail "could not recreate $STAGE_DB"
STAGE_URL="${LIVE_URL%/*}/$STAGE_DB"
pg_restore --no-owner --role="$OWNER" -d "$STAGE_URL" "$TMP" 2>/tmp/infinia-staging.err
N=$(psql "$STAGE_URL" -tAc "select count(*) from information_schema.tables where table_schema='public'")
[ "${N:-0}" -gt 20 ] || fail "the copy looks empty ($N tables): $(tail -3 /tmp/infinia-staging.err)"
# cut the copy off from Zoho - its passwords are also unreadable there (different key file)
psql "$STAGE_URL" -q -c "DELETE FROM settings WHERE key IN ('zoho_refresh','zoho_client_secret');" 2>/dev/null
rm -f "$TMP" /tmp/infinia-staging.err
systemctl start infinia-staging
echo "$(TZ=Asia/Dubai date '+%d/%m/%Y %H:%M') staging refreshed from live ($N tables) - https://app.infinia.ae:8443"

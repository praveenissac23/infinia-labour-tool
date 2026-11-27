#!/bin/bash
# Faster opening of app.infinia.ae (27/11/2026). Run once on the VPS:
#   sudo bash ~/infinia-labour-tool/deploy/speed_fix.sh
#
# From the speed report of 27/11/2026: only the page itself was compressed - the scripts (guides.js 150 KB,
# heads.js 125 KB and 20 more) went out at full size; every file was checked again on every open, one trip each;
# and the connection was the old one-file-at-a-time kind (HTTP 1.1). This changes nginx only:
#   1. compress scripts, styles and data too (gzip_types)
#   2. scripts, styles and pictures whose address carries their content stamp (?v=<stamp>, logo-<stamp>.png) are kept -
#      a changed file gets a new stamp, so a new address; everything else is still checked on every open
#   3. HTTP/2 on the secure addresses: many files over one connection at the same time
# A copy of each file is kept first; nginx checks the new settings before reloading, and if the check fails the
# copies are put back and nothing changes. Reload only - nobody is signed out. Running it twice changes nothing more.
# Also tidies the database's own counts and hands back the space of the kept answers the app clears at its start
# (so run this AFTER the deploy command, not before).
set -e
[ "$(id -u)" = 0 ] || { echo "Run with sudo."; exit 1; }
LIVE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SITE="$(grep -lE 'server_name +app\.infinia\.ae' /etc/nginx/sites-enabled/* 2>/dev/null | grep -v staging | head -1)"   # live's own file; the test copy (8443) has the same name in it
[ -n "$SITE" ] || { echo "Could not find the nginx file for app.infinia.ae - nothing changed."; exit 1; }
SITE="$(readlink -f "$SITE")"
CONF=/etc/nginx/conf.d/infinia-speed.conf
STAMP="$(date +%Y%m%d-%H%M%S)"
cp -a "$SITE" "$SITE.before-speed-$STAMP"
[ -f "$CONF" ] && cp -a "$CONF" "/root/infinia-speed.conf.before-$STAMP"
echo "nginx file: $SITE (copy kept: $SITE.before-speed-$STAMP)"
put_back() {
  cp -a "$SITE.before-speed-$STAMP" "$SITE"
  if [ -f "/root/infinia-speed.conf.before-$STAMP" ]; then cp -a "/root/infinia-speed.conf.before-$STAMP" "$CONF"; else rm -f "$CONF"; fi
}
trap 'put_back; echo "Stopped part-way - put back as it was, nothing changed. Send this screen to Claude."' ERR

# 1 + 2: the http-level settings, each only if nginx.conf does not set it already
MAIN="$(nginx -T 2>/dev/null | sed -n '/# configuration file \/etc\/nginx\/nginx.conf:/,/# configuration file /p' | grep -v '^\s*#' || true)"
{
  echo "# Added by infinia-labour-tool/deploy/speed_fix.sh ($STAMP)"
  echo "$MAIN" | grep -qE '^\s*gzip_types'      || echo "gzip_types text/css text/plain text/xml application/javascript text/javascript application/json application/manifest+json application/xml image/svg+xml font/ttf;"
  echo "$MAIN" | grep -qE '^\s*gzip_vary'       || echo "gzip_vary on;"
  echo "$MAIN" | grep -qE '^\s*gzip_proxied'    || echo "gzip_proxied any;"
  echo "$MAIN" | grep -qE '^\s*gzip_comp_level' || echo "gzip_comp_level 5;"
  echo "$MAIN" | grep -qE '^\s*gzip_min_length' || echo "gzip_min_length 1024;"
  echo 'map $request_uri $infinia_cache {'
  echo '    default                                          "no-cache, must-revalidate";'
  echo '    "~^[^?]+\.(js|css|png|webp|jpg|svg|woff2?|ttf)\?(.*&)?v=[0-9a-f]{10,}(&|$)"   "public, max-age=31536000, immutable";'
  echo '    "~^/portal/logo-[0-9a-f]{8}\.(png|webp|jpg)$"     "public, max-age=31536000, immutable";'
  echo '}'
} > "$CONF"

# 2 + 3: in the app's own file - the cache line follows the stamp; the secure listen lines get http2
python3 - "$SITE" <<'PY'
import re, sys
p = sys.argv[1]; s = open(p, encoding="utf-8").read(); n0 = s
s = s.replace('add_header Cache-Control "no-cache, must-revalidate";', 'add_header Cache-Control $infinia_cache;')
s = re.sub(r'(?m)^(\s*listen\s+[^;#\n]*\bssl\b)(?![^;#\n]*\bhttp2\b)([^;#\n]*;)', lambda m: m.group(1) + " http2" + m.group(2), s)
if s != n0:
    open(p, "w", encoding="utf-8").write(s)
print("  cache lines now following the stamp:", s.count("add_header Cache-Control $infinia_cache;"))
print("  secure listen lines with http2:", len(re.findall(r'(?m)^\s*listen\s+[^;#\n]*\bssl\b[^;#\n]*\bhttp2\b', s)))
PY

if nginx -t 2>/tmp/speed_fix_check.txt; then
  systemctl reload nginx; sleep 2                       # the new settings take over from the old ones
  trap - ERR
  echo "nginx checked and reloaded."
else
  cat /tmp/speed_fix_check.txt
  trap - ERR; put_back
  nginx -t >/dev/null 2>&1 && echo "nginx did not accept the change - put back as it was, nothing changed. Send this screen to Claude."
  exit 1
fi

echo; echo "--- The database's own counts"
DBURL="$(systemctl show infinia -p Environment --value 2>/dev/null | tr ' ' '\n' | grep '^DATABASE_URL=' | cut -d= -f2-)"
[ -z "$DBURL" ] && for F in $(systemctl show infinia -p EnvironmentFiles --value 2>/dev/null | awk '{print $1}'); do DBURL="$(grep '^DATABASE_URL=' "$F" 2>/dev/null | cut -d= -f2- | tr -d '"'"'")"; done
if [ -n "$DBURL" ] && command -v psql >/dev/null; then
  psql "${DBURL/postgresql+psycopg2/postgresql}" -q -c "VACUUM (FULL, ANALYZE) offline_requests;" -c "ANALYZE;" && echo "  updated."
else echo "  (database address not found - skipped, nothing else affected)"; fi

echo; echo "--- Check"
V="$(grep -o '/portal/help/guides.js?v=[0-9a-f]*' "$LIVE_DIR/app.html" | head -1)"
for U in "/" "$V" "/portal/help/heads.js"; do
  curl -s -o /dev/null -D /tmp/sf.h -H 'Accept-Encoding: gzip' -w "$U  HTTP %{http_version}  sent %{size_download} bytes\n" "https://app.infinia.ae$U"
  tr -d '\r' < /tmp/sf.h | grep -iE '^(content-encoding|cache-control):' | sed 's/^/    /'
done
rm -f /tmp/sf.h /tmp/speed_fix_check.txt
echo; echo "Done. To undo:  sudo cp -a $SITE.before-speed-$STAMP $SITE && sudo rm -f $CONF && sudo systemctl reload nginx"

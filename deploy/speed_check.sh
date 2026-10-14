#!/bin/bash
# Speed check for app.infinia.ae - safe to run any time.
#
#   bash deploy/speed_check.sh          only looks and reports, changes nothing
#   bash deploy/speed_check.sh --apply  turns on compression (gzip) in nginx
#                                       if it is off: backs the file up first,
#                                       tests the new setting, and puts the
#                                       old file back by itself if the test fails
#
# Why: the app page is about 1.3 MB. Compressed it is about a quarter of
# that, so every first open and every refresh is several times quicker.
set -u
HOST="${HOST:-https://app.infinia.ae}"
CONF="/etc/nginx/conf.d/infinia-speed.conf"

say() { printf '%s\n' "$*"; }
size() { curl -s -o /dev/null -w '%{size_download}' -H "Accept-Encoding: $2" "$HOST/$1"; }
enc()  { curl -s -D - -o /dev/null -H 'Accept-Encoding: gzip' "$HOST/$1" | tr -d '\r' | awk -F': ' 'tolower($1)=="content-encoding"{print $2}'; }

say "Checking $HOST ..."
plain=$(size app.html identity); zipped=$(size app.html gzip); e=$(enc app.html)
say "  app.html  plain $((plain/1024)) KB   as sent to a browser $((zipped/1024)) KB   compression: ${e:-none}"
t=$(curl -s -o /dev/null -w '%{time_total}' "$HOST/health"); say "  server answers in ${t}s"

if [ -n "$e" ]; then say "Compression is already on - nothing to do."; exit 0; fi
if [ "${1:-}" != "--apply" ]; then
  say "Compression is OFF. Run again with --apply to turn it on (safe: backed up and tested)."; exit 0
fi

[ -f "$CONF" ] && sudo cp -a "$CONF" "$CONF.bak.$(date +%s)"
sudo tee "$CONF" >/dev/null <<'NGX'
# Infinia: send pages, scripts and data compressed.
gzip on;
gzip_comp_level 5;
gzip_min_length 1024;
gzip_proxied any;
gzip_vary on;
gzip_types text/plain text/css text/javascript application/javascript application/json application/xml image/svg+xml;
NGX
if sudo nginx -t 2>/tmp/nginx_test.log; then
  sudo systemctl reload nginx
  sleep 1
  say "  now sent as $(( $(size app.html gzip) / 1024 )) KB, compression: $(enc app.html)"
  say "Done."
else
  say "nginx did not accept it - putting things back:"; cat /tmp/nginx_test.log
  sudo rm -f "$CONF"; ls "$CONF".bak.* >/dev/null 2>&1 && sudo cp -a "$(ls -t "$CONF".bak.* | head -1)" "$CONF"
  sudo nginx -t && sudo systemctl reload nginx
  say "Nothing changed."
fi

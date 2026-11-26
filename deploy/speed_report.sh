#!/bin/bash
# Speed report for app.infinia.ae (26/11/2026). ONLY LOOKS - changes nothing, restarts nothing. Run on the VPS:
#   sudo bash ~/infinia-labour-tool/deploy/speed_report.sh
# and send the whole output to Claude. It shows how pages and scripts reach the browser (compressed? kept by the
# browser or downloaded again every time?), how loaded the server is, and which requests were slow.
HOST="${HOST:-https://app.infinia.ae}"
LIVE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
echo "=== Speed report $(date '+%d/%m/%Y %H:%M') ==="

echo; echo "--- 1. How each file reaches the browser"
V="$(grep -o '/portal/help/guides.js?v=[0-9a-f]*' "$LIVE_DIR/app.html" | head -1)"
LOGO="$(grep -o '/portal/logo-[0-9a-f]*\.png' "$LIVE_DIR/app.html" | head -1)"
for U in "/" "/app-version.json" "${V:-/portal/help/guides.js}" "/portal/help/heads.js" "${LOGO:-/portal/icon-192.png}" "/portal/me.html" "/sw.js" "/health"; do
  curl -s -o /dev/null -D /tmp/sr.h -H 'Accept-Encoding: gzip, br' \
    -w "$U\n    HTTP %{http_version}  status %{http_code}  sent %{size_download} bytes  first byte %{time_starttransfer}s  total %{time_total}s\n" "$HOST$U"
  tr -d '\r' < /tmp/sr.h | grep -iE '^(content-encoding|cache-control|etag|last-modified|expires|content-type):' | sed 's/^/    /'
done
echo "  app.html on disk: $(stat -c %s "$LIVE_DIR/app.html") bytes"
echo "  second open of the same connection (5 x /health): $(for i in 1 2 3 4 5; do curl -s -o /dev/null -w '%{time_total} ' "$HOST/health"; done)"
rm -f /tmp/sr.h

echo; echo "--- 2. nginx settings that matter"
nginx -v 2>&1 | sed 's/^/  /'
nginx -T 2>/dev/null | grep -nE '^\s*(gzip|gzip_[a-z_]+|brotli[a-z_]*|listen|http2|expires|add_header|etag|if_modified_since|keepalive[a-z_]*|worker_processes|worker_connections|sendfile|tcp_no[a-z]+|open_file_cache[a-z_]*|proxy_buffering|proxy_buffers?|proxy_buffer_size|proxy_http_version|proxy_cache[a-z_]*|proxy_read_timeout|ssl_session_[a-z]+|ssl_protocols|location|root|alias|try_files|server_name|upstream|server )\b' | grep -v '#' | sed 's/^/  /' | head -150

echo; echo "--- 3. The server"
echo "  processors: $(nproc)   load (1, 5, 15 min): $(cut -d' ' -f1-3 /proc/loadavg)"
free -m | sed 's/^/  /'
df -h / | tail -1 | sed 's/^/  disk: /'
echo "  app memory now / highest: $(systemctl show infinia -p MemoryCurrent --value 2>/dev/null) / $(systemctl show infinia -p MemoryPeak --value 2>/dev/null) bytes; limit $(systemctl show infinia -p MemoryMax --value 2>/dev/null)"
echo "  app started: $(systemctl show infinia -p ActiveEnterTimestamp --value 2>/dev/null)"
systemctl cat infinia 2>/dev/null | grep -E '^ExecStart=.+' | sed -E 's/(postgres(ql)?:\/\/)[^ ]*/\1.../' | sed 's/^/  /'
ps -eo pid,pcpu,pmem,rss,etimes,comm --sort=-pcpu | head -8 | sed 's/^/  /'

echo; echo "--- 4. Requests that took over 4 seconds, last 7 days (how many, which)"
journalctl -u infinia --since "-7 days" --no-pager 2>/dev/null | grep -o 'SLOW .*' | sed -E 's/SLOW [0-9.]+s //; s/[0-9]+/#/g' | sort | uniq -c | sort -rn | head -25 | sed 's/^/  /'
echo "  the 10 longest:"; journalctl -u infinia --since "-7 days" --no-pager 2>/dev/null | grep -o 'SLOW .*' | sort -t' ' -k2 -rn | head -10 | sed 's/^/    /'

echo; echo "--- 5. Where the time goes, hour by hour (kind of request, calls, average ms, longest ms, over 1 s) - last 12 lines"
journalctl -u infinia --since "-2 days" --no-pager 2>/dev/null | grep -o 'TIMES .*' | tail -12 | sed 's/^/  /'
[ -z "$(journalctl -u infinia --since '-2 days' --no-pager 2>/dev/null | grep -m1 TIMES)" ] && echo "  (none yet - they start an hour after the next deploy; run this again tomorrow)"

echo; echo "--- 6. Database"
DBURL="$(systemctl show infinia -p Environment --value 2>/dev/null | tr ' ' '\n' | grep '^DATABASE_URL=' | cut -d= -f2-)"
[ -z "$DBURL" ] && for F in $(systemctl show infinia -p EnvironmentFiles --value 2>/dev/null | awk '{print $1}'); do DBURL="$(grep '^DATABASE_URL=' "$F" 2>/dev/null | cut -d= -f2- | tr -d '"'"'")"; done
if [ -n "$DBURL" ] && command -v psql >/dev/null; then
  psql "${DBURL/postgresql+psycopg2/postgresql}" -At -c "select 'size '||pg_size_pretty(pg_database_size(current_database()))" \
    -c "select relname||'  rows '||n_live_tup||'  '||pg_size_pretty(pg_total_relation_size(relid))||'  read whole '||seq_scan||'x  dead rows '||n_dead_tup from pg_stat_user_tables order by pg_total_relation_size(relid) desc limit 15" 2>&1 | sed 's/^/  /'
else echo "  (could not read the database address - skipped)"; fi
echo; echo "=== end - send everything above to Claude ==="

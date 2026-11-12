#!/bin/bash
# One-time setup of the test copy ("staging") on the VPS:
#   sudo bash ~/infinia-labour-tool/deploy/install-staging.sh
#
# What it makes:
#   ~/infinia-staging        a second copy of the code; it follows GitHub main by itself every 2 minutes
#   infinia_staging          a second database, refreshed from live every night at 4:00 AM Dubai
#   infinia-staging service  the test app on 127.0.0.1:8100 - no mail, no phone notifications, no scheduled
#                            jobs, no Zoho - so nothing done there reaches anybody
#   https://app.infinia.ae:8443   where you open it (same certificate as the live site)
# Live (the infinia service, its database, its code folder) is not changed - only read.
set -e
LIVE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OWNER_USER="$(stat -c %U "$LIVE_DIR")"
STAGE_DIR="$(dirname "$LIVE_DIR")/infinia-staging"
PORT=8100

UNIT="$(systemctl cat infinia 2>/dev/null)" || { echo "The live service 'infinia' was not found."; exit 1; }
EXEC="$(echo "$UNIT" | grep -m1 '^ExecStart=' | cut -d= -f2-)"
SVC_USER="$(echo "$UNIT" | grep -m1 '^User=' | cut -d= -f2-)"; SVC_USER="${SVC_USER:-$OWNER_USER}"
echo "$EXEC" | grep -q -- '--port' || { echo "Live ExecStart has no --port, set staging up by hand: $EXEC"; exit 1; }
STAGE_EXEC="$(echo "$EXEC" | sed -E "s#$LIVE_DIR#$STAGE_DIR#g; s#--port[ =][0-9]+#--port $PORT#; s#--host[ =][^ ]+#--host 127.0.0.1#")"
# a virtualenv inside the live folder is shared, not copied
VENV="$(echo "$EXEC" | grep -o "$LIVE_DIR/[^ ]*/bin/" | head -1)"
[ -n "$VENV" ] && STAGE_EXEC="$(echo "$STAGE_EXEC" | sed "s#$STAGE_DIR/${VENV#$LIVE_DIR/}#$VENV#")"
WORKDIR="$(echo "$UNIT" | grep -m1 '^WorkingDirectory=' | cut -d= -f2- | sed "s#$LIVE_DIR#$STAGE_DIR#")"

# 1. the code
if [ ! -d "$STAGE_DIR/.git" ]; then
  sudo -u "$OWNER_USER" git clone -q "$(git -C "$LIVE_DIR" remote get-url origin)" "$STAGE_DIR"
fi
sudo -u "$OWNER_USER" git -C "$STAGE_DIR" pull -q --ff-only

# 2. the service (no SMTP_*, no key file of live, scheduler and push off)
LIVE_URL="$(systemctl show infinia -p Environment --value | grep -o 'DATABASE_URL=[^ ]*' | cut -d= -f2-)"
if [ -z "$LIVE_URL" ]; then
  PID="$(systemctl show infinia -p MainPID --value)"; LIVE_URL="$(tr '\0' '\n' < /proc/$PID/environ | grep '^DATABASE_URL=' | cut -d= -f2-)"
fi
[ -n "$LIVE_URL" ] || { echo "Could not read live DATABASE_URL"; exit 1; }
STAGE_URL="${LIVE_URL%/*}/infinia_staging"
cat > /etc/systemd/system/infinia-staging.service <<UNIT
[Unit]
Description=Infinia app - TEST COPY (staging), port $PORT
After=network.target postgresql.service

[Service]
User=$SVC_USER
WorkingDirectory=${WORKDIR:-$STAGE_DIR/app}
Environment=DATABASE_URL=$STAGE_URL
Environment=INFINIA_NO_SCHED=1
Environment=INFINIA_NO_PUSH=1
Environment=INFINIA_STAGING=1
Environment=INFINIA_CRED_KEY_FILE=$STAGE_DIR/data/credentials.key
ExecStart=$STAGE_EXEC
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT

# 3. follow GitHub every 2 minutes; refresh the data every night 4:00 AM Dubai
cat > /etc/systemd/system/infinia-staging-pull.service <<UNIT
[Unit]
Description=Infinia staging - take the newest code from GitHub
[Service]
Type=oneshot
ExecStart=/bin/bash -c 'cd $STAGE_DIR && OLD=\$(git rev-parse HEAD) && sudo -u $OWNER_USER git pull -q --ff-only && [ "\$OLD" != "\$(git rev-parse HEAD)" ] && systemctl restart infinia-staging || true'
UNIT
cat > /etc/systemd/system/infinia-staging-pull.timer <<UNIT
[Unit]
Description=Infinia staging follows GitHub every 2 minutes
[Timer]
OnBootSec=2min
OnUnitActiveSec=2min
[Install]
WantedBy=timers.target
UNIT
cat > /etc/systemd/system/infinia-staging-refresh.service <<UNIT
[Unit]
Description=Infinia staging - fresh copy of the live data
After=postgresql.service
[Service]
Type=oneshot
Nice=10
ExecStart=/bin/bash $STAGE_DIR/deploy/staging_refresh.sh
UNIT
cat > /etc/systemd/system/infinia-staging-refresh.timer <<UNIT
[Unit]
Description=Infinia staging data refreshed from live every night 4:00 AM Dubai
[Timer]
OnCalendar=*-*-* 04:00:00 Asia/Dubai
Persistent=true
[Install]
WantedBy=timers.target
UNIT

# 4. https://app.infinia.ae:8443 -> the test copy: a copy of live's own nginx server block (same certificate, same
#    static files rule and API paths), pointed at the staging folder and port, with a "TEST COPY" bar on every page.
LIVE_PORT="$(echo "$EXEC" | grep -oE -- '--port[ =][0-9]+' | grep -oE '[0-9]+')"
LIVE_CONF="$(grep -rlE 'server_name[^;]*app\.infinia\.ae' /etc/nginx/sites-enabled/ | head -1)"
if [ -n "$LIVE_CONF" ]; then
python3 - "$LIVE_CONF" "$LIVE_DIR" "$STAGE_DIR" "$LIVE_PORT" "$PORT" <<'PY'
import re, sys
conf, live_dir, stage_dir, live_port, port = sys.argv[1:]
txt = open(conf).read()
blocks, i = [], 0
while True:                                  # every top-level server { ... } block
    m = re.search(r'\bserver\s*\{', txt[i:])
    if not m: break
    st = i + m.start(); j = i + m.end(); depth = 1
    while depth and j < len(txt):
        depth += {'{': 1, '}': -1}.get(txt[j], 0); j += 1
    blocks.append(txt[st:j]); i = j
ssl = [b for b in blocks if re.search(r'listen\s+[^;]*443', b) and 'app.infinia.ae' in b]
if not ssl:
    sys.exit("no 443 server block for app.infinia.ae in " + conf)
b = ssl[0]
b = re.sub(r'listen\s+\[::\]:443[^;]*;\s*', '', b)
b = re.sub(r'listen\s+[^;]*443[^;]*;', 'listen 8443 ssl;', b, count=1)
b = b.replace(live_dir, stage_dir)
if live_port:
    b = re.sub(r'(127\.0\.0\.1|localhost):' + live_port + r'\b', r'\g<1>:' + port, b)
bar = ('<div style=\\"position:fixed;left:0;right:0;bottom:0;z-index:2147483647;background:#B9770E;color:#fff;'
       'font:600 12px/24px Arial,sans-serif;text-align:center;pointer-events:none\\">TEST COPY - data copied from live, '
       'nothing here reaches Zoho, email or phones</div></body>')
b = b.rstrip()[:-1] + f'    sub_filter "</body>" "{bar}";\n    sub_filter_once on;\n    proxy_set_header Accept-Encoding "";\n}}\n'
open('/etc/nginx/sites-available/infinia-staging', 'w').write('# TEST COPY of the app - made by deploy/install-staging.sh from ' + conf + '\n' + b)
print("nginx: staging block written from", conf)
PY
  ln -sf /etc/nginx/sites-available/infinia-staging /etc/nginx/sites-enabled/infinia-staging
  if nginx -t 2>/tmp/ngx.err; then systemctl reload nginx; else
    echo "nginx did not accept the staging block - taken off again, live untouched:"; cat /tmp/ngx.err
    rm -f /etc/nginx/sites-enabled/infinia-staging; fi
  command -v ufw >/dev/null && ufw status | grep -q active && ufw allow 8443/tcp >/dev/null || true
else
  echo "Could not find live's nginx block for app.infinia.ae - the test copy is on 127.0.0.1:$PORT only."
fi

systemctl daemon-reload
systemctl enable -q infinia-staging infinia-staging-pull.timer infinia-staging-refresh.timer
systemctl start infinia-staging-pull.timer infinia-staging-refresh.timer
echo "Copying the live data now (a minute or two)..."
bash "$STAGE_DIR/deploy/staging_refresh.sh"
echo "Done. Test copy: https://app.infinia.ae:8443  (same logins as live, data as of now)"

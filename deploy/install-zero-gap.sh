#!/bin/bash
# Updates without a gap (14/11/2026). Run once on the VPS:
#   sudo bash ~/infinia-labour-tool/deploy/install-zero-gap.sh
#
# The app is run by gunicorn with ONE worker (same memory as now). An update then RELOADS instead of restarting:
# the new copy starts, takes over, and only then the old one stops - nobody sees the app go away. For a few
# seconds during an update two copies exist; the rest of the time just one.
# It also keeps the app restarting by itself within seconds if it ever crashes, and caps its memory (2.5 GB) so
# it can never freeze the whole server again.
# If anything fails, the old way is put back and the app restarted as before.
set -e
LIVE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
UNIT="$(systemctl cat infinia 2>/dev/null)" || { echo "The service 'infinia' was not found."; exit 1; }
EXEC="$(echo "$UNIT" | grep '^ExecStart=' | grep -v '^ExecStart=$' | head -1 | cut -d= -f2-)"
BIN="$(echo "$EXEC" | awk '{print $1}')"; VENV_BIN="$(dirname "$BIN")"
PORT="$(echo "$EXEC" | grep -oE -- '--port[ =][0-9]+' | grep -oE '[0-9]+' | head -1)"; PORT="${PORT:-8000}"
HOST="$(echo "$EXEC" | grep -oE -- '--host[ =][^ ]+' | awk -F'[ =]' '{print $2}' | head -1)"; HOST="${HOST:-127.0.0.1}"
TARGET="$(echo "$EXEC" | grep -oE '[A-Za-z_][A-Za-z0-9_.]*:app' | head -1)"; TARGET="${TARGET:-main:app}"
echo "Now:   $EXEC"
[ -x "$VENV_BIN/pip" ] || { echo "No pip next to $BIN - set this up by hand."; exit 1; }

echo "Installing gunicorn into $VENV_BIN ..."
"$VENV_BIN/pip" install -q "gunicorn==23.0.0" "uvicorn-worker==0.4.0"

mkdir -p /etc/systemd/system/infinia.service.d
cat > /etc/systemd/system/infinia.service.d/zero-gap.conf <<CONF
[Service]
ExecStart=
ExecStart=$VENV_BIN/gunicorn $TARGET -k uvicorn_worker.UvicornWorker -w 1 -b $HOST:$PORT --graceful-timeout 30 --timeout 300 --forwarded-allow-ips=127.0.0.1
ExecReload=/bin/kill -HUP \$MAINPID
Restart=always
RestartSec=2
MemoryMax=2500M
MemorySwapMax=0
CONF
systemctl daemon-reload
systemctl restart infinia
echo "Waiting for the app ..."
for i in $(seq 1 60); do
  if curl -fs -o /dev/null "http://127.0.0.1:$PORT/health"; then
    echo "OK - the app answers (after ${i}s). Updates now reload without a gap:"
    echo "  cd ~/infinia-labour-tool && git pull && sudo systemctl reload-or-restart infinia"
    exit 0
  fi
  sleep 1
done
echo "The app did not answer - putting the old way back."
rm -f /etc/systemd/system/infinia.service.d/zero-gap.conf
systemctl daemon-reload; systemctl restart infinia
journalctl -u infinia -n 30 --no-pager
exit 1

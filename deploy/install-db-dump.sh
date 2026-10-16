#!/bin/bash
# One-time setup, run once with sudo on the VPS:
#   sudo bash ~/infinia-labour-tool/deploy/install-db-dump.sh
# Makes a fresh database file every night at 11:30 PM Dubai, half an hour
# before the Acronis backup (12 AM Dubai), and makes the first one now.
set -e
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
chmod +x "$REPO_DIR/deploy/nightly_db_dump.sh"

cat > /etc/systemd/system/infinia-dbdump.service <<EOF
[Unit]
Description=Nightly Infinia database file for the Acronis backup
After=postgresql.service

[Service]
Type=oneshot
Nice=10
IOSchedulingClass=idle
ExecStart=/bin/bash $REPO_DIR/deploy/nightly_db_dump.sh
EOF

cat > /etc/systemd/system/infinia-dbdump.timer <<EOF
[Unit]
Description=Infinia database file every night 11:30 PM Dubai

[Timer]
OnCalendar=*-*-* 23:30:00 Asia/Dubai
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now infinia-dbdump.timer
echo "Making the first database file now..."
systemctl start infinia-dbdump.service
journalctl -u infinia-dbdump.service -n 3 --no-pager -o cat
echo
systemctl list-timers infinia-dbdump.timer --no-pager | head -2

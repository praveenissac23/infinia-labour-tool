#!/bin/bash
# One-time setup, run once with sudo on the VPS:
#   sudo bash ~/infinia-labour-tool/deploy/install-autodeploy.sh
# After this, every push to GitHub goes live within about two minutes -
# no more manual SSH deploys.
set -e
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
chmod +x "$REPO_DIR/deploy/autodeploy.sh"

cat > /etc/systemd/system/infinia-autodeploy.service <<EOF
[Unit]
Description=Pull latest Infinia Labour Tool from GitHub and restart if changed

[Service]
Type=oneshot
ExecStart=/bin/bash $REPO_DIR/deploy/autodeploy.sh
EOF

cat > /etc/systemd/system/infinia-autodeploy.timer <<EOF
[Unit]
Description=Check GitHub for Infinia updates every 2 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=2min

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now infinia-autodeploy.timer
echo "Auto-deploy installed and running."
echo "Check it any time with: systemctl status infinia-autodeploy.timer"
echo "See deploy history with: journalctl -u infinia-autodeploy.service -n 20"

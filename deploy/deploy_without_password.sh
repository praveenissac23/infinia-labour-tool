#!/bin/bash
# One-time (16/11/2026): let the deploy command restart the app without asking for the password every time.
#   sudo bash ~/infinia-labour-tool/deploy/deploy_without_password.sh
# Only these exact commands are allowed without a password - nothing else changes for sudo.
set -euo pipefail
U="${SUDO_USER:-$(whoami)}"
SC="$(command -v systemctl)"
TMP="$(mktemp)"
cat > "$TMP" <<RULES
# Infinia app deploy: restart / reload the app without a password (deploy/deploy_without_password.sh)
$U ALL=(root) NOPASSWD: $SC reload-or-restart infinia, $SC restart infinia, $SC reload infinia, $SC status infinia, $SC reload-or-restart infinia-staging, $SC restart infinia-staging
RULES
if visudo -cf "$TMP" >/dev/null; then
  install -m 440 -o root -g root "$TMP" /etc/sudoers.d/infinia-deploy
  rm -f "$TMP"
  echo "OK - '$U' can now run the deploy command without a password."
else
  rm -f "$TMP"; echo "Not changed - the rule did not check out."; exit 1
fi

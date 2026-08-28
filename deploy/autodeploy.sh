#!/bin/bash
# Checks GitHub for new commits and, only if something changed, pulls and
# restarts the app. Run by the infinia-autodeploy systemd timer every two
# minutes, so a push to GitHub goes live on app.infinia.ae hands-free.
set -e
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

git fetch origin main --quiet
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" != "$REMOTE" ]; then
    echo "$(date '+%F %T') new commit $REMOTE - deploying"
    git pull --ff-only --quiet
    systemctl restart infinia
    echo "$(date '+%F %T') deployed and restarted"
fi

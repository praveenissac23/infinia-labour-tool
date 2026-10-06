#!/bin/bash
# Retakes every Help picture and rewrites the screen-by-screen guides, then
# rebuilds the app. Run before every push that changes a screen:
#   deploy/refresh_help.sh /path/to/a/test.db
# It works on a COPY of the database given - never the live one - and stops
# (exit 1) if a written guide points at a button that is no longer there.
set -e
cd "$(dirname "$0")/.."
SRC_DB=${1:?give a test database to copy (one with salary cards and store data)}
cp "$SRC_DB" /tmp/help_refresh.db
DATABASE_URL=sqlite:////tmp/help_refresh.db nohup python3 tests/serve_like_nginx.py > /tmp/help_refresh.log 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null; pkill -P $SRV 2>/dev/null; true' EXIT
sleep 9
node tests/help_screens.js
python3 deploy/build_temporary_pages.py

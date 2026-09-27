#!/bin/bash
# Full backup of the live app before the new app goes live.
#
#   cd ~/infinia-labour-tool && bash deploy/backup_before_go_live.sh
#
# Saves, into ~/backups/before-new-app-<date-time>/ :
#   database.dump      the whole PostgreSQL database (pg_dump custom format)
#   database.sql.gz    the same again as plain SQL, a second independent copy
#   row-counts.txt     exact number of rows in every table (to compare later)
#   code.tgz           the app folder as it is now (without venv/node_modules)
#   code-version.txt   the exact code version (git commit) running now
#   server-config/     nginx site, systemd service and env files
# and checks each file can be read back before saying it is done.
# Nothing in the app or the database is changed.
set -uo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
STAMP="$(date +%Y%m%d-%H%M)"
DEST="$HOME/backups/before-new-app-$STAMP"
PY="$APP_DIR/venv/bin/python"; [ -x "$PY" ] || PY=python3
mkdir -p "$DEST/server-config"
ok()   { echo "  OK   $*"; }
fail() { echo "  FAILED: $*"; echo; echo "Backup NOT complete - do not continue. Send this output to Claude."; exit 1; }

echo "Backing up into $DEST"
echo

# ---- 1. find the database the app uses -----------------------------------
DB_URL="$("$PY" - <<'EOF'
import os, re, subprocess
def find():
    if os.environ.get("DATABASE_URL"): return os.environ["DATABASE_URL"]
    for unit in ("infinia", "infinia.service"):
        try:
            out = subprocess.run(["systemctl", "show", unit, "-p", "Environment", "--value"], capture_output=True, text=True).stdout
            m = re.search(r"DATABASE_URL=(\S+)", out or "")
            if m: return m.group(1)
            out = subprocess.run(["systemctl", "show", unit, "-p", "EnvironmentFiles", "--value"], capture_output=True, text=True).stdout
            for path in re.findall(r"(/\S+?)(?:\s|$)", out or ""):
                path = path.rstrip("()").lstrip("-")
                if os.path.exists(path):
                    for line in open(path):
                        if line.strip().startswith("DATABASE_URL="):
                            return line.split("=", 1)[1].strip().strip("'\"")
        except Exception:
            pass
    for env in ("/home/infinia/infinia-labour-tool/.env", "/home/infinia/infinia-labour-tool/app/.env"):
        if os.path.exists(env):
            for line in open(env):
                if line.strip().startswith("DATABASE_URL="):
                    return line.split("=", 1)[1].strip().strip("'\"")
    return ""
print(find())
EOF
)"
[ -n "$DB_URL" ] || DB_URL="$(sudo cat /proc/$(systemctl show infinia -p MainPID --value)/environ 2>/dev/null | tr '\0' '\n' | grep '^DATABASE_URL=' | cut -d= -f2-)"
[ -n "$DB_URL" ] || fail "could not find the app's DATABASE_URL"
case "$DB_URL" in postgresql+psycopg2://*) DB_URL="postgresql://${DB_URL#postgresql+psycopg2://}";; esac
ok "database found: $(echo "$DB_URL" | sed -E 's#://([^:@/]+):[^@]*@#://\1:***@#')"

# ---- 2. database, twice ----------------------------------------------------
pg_dump "$DB_URL" -Fc -f "$DEST/database.dump" 2>"$DEST/pg_dump.err" || fail "pg_dump (custom): $(cat "$DEST/pg_dump.err")"
N=$(pg_restore --list "$DEST/database.dump" 2>/dev/null | grep -c "TABLE DATA")
[ "$N" -gt 5 ] || fail "database.dump looks empty ($N tables)"
ok "database.dump  $(du -h "$DEST/database.dump" | cut -f1)  - $N tables, readable"

pg_dump "$DB_URL" 2>>"$DEST/pg_dump.err" | gzip > "$DEST/database.sql.gz" || fail "pg_dump (plain)"
gzip -t "$DEST/database.sql.gz" || fail "database.sql.gz is damaged"
grep -q "PostgreSQL database dump complete" <(gunzip -c "$DEST/database.sql.gz" | tail -5) || fail "database.sql.gz is incomplete"
ok "database.sql.gz  $(du -h "$DEST/database.sql.gz" | cut -f1)  - complete"
rm -f "$DEST/pg_dump.err"

# ---- 3. exact row counts ---------------------------------------------------
DATABASE_URL="$DB_URL" "$PY" - > "$DEST/row-counts.txt" <<'EOF' || fail "could not count rows"
import os
from sqlalchemy import create_engine, inspect, text
e = create_engine(os.environ["DATABASE_URL"])
with e.connect() as c:
    for t in sorted(inspect(e).get_table_names()):
        q = 'SELECT COUNT(*) FROM "' + t + '"'
        print(t.ljust(40), c.execute(text(q)).scalar())
EOF
ok "row-counts.txt  - $(wc -l < "$DEST/row-counts.txt") tables counted"

# ---- 4. code ---------------------------------------------------------------
cd "$APP_DIR"
{ git rev-parse HEAD; git log --oneline -1; } > "$DEST/code-version.txt"
git tag -f before-new-app >/dev/null 2>&1
tar czf "$DEST/code.tgz" --exclude=./venv --exclude=./node_modules --exclude=./backups -C "$APP_DIR" . 2>/dev/null || fail "could not archive the code"
tar tzf "$DEST/code.tgz" >/dev/null || fail "code.tgz is damaged"
ok "code.tgz  $(du -h "$DEST/code.tgz" | cut -f1)  - version $(git log --oneline -1 | cut -c1-60)"

# ---- 5. server settings ------------------------------------------------------
sudo cp -a /etc/nginx/sites-available "$DEST/server-config/nginx-sites-available" 2>/dev/null && ok "nginx settings" || echo "  note: nginx settings not copied"
for u in infinia infinia-autodeploy; do
  f=$(systemctl show "$u" -p FragmentPath --value 2>/dev/null); [ -n "$f" ] && sudo cp "$f" "$DEST/server-config/" 2>/dev/null
done
ok "systemd service files"
for f in $(systemctl show infinia -p EnvironmentFiles --value 2>/dev/null | grep -o '/[^ ]*' | tr -d '()'); do
  [ -f "$f" ] && sudo cp "$f" "$DEST/server-config/" 2>/dev/null
done
sudo chown -R "$(id -u):$(id -g)" "$DEST" 2>/dev/null
chmod -R go-rwx "$DEST"
ok "env files (kept private to your login)"

echo
echo "BACKUP COMPLETE: $DEST  ($(du -sh "$DEST" | cut -f1))"
echo "Keep a copy off the server too - on your laptop run:"
echo "  scp -r infinia@66.116.254.8:$DEST ~/Downloads/"

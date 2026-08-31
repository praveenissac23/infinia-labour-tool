#!/bin/bash
# Pull a full backup of app.infinia.ae onto this Mac.
#
# Backups that live only on the VPS are not backups: if BigRock's disk
# dies, they die with it. This takes a fresh snapshot on the server,
# downloads it here, checks it is real data before keeping it, and
# throws away copies older than the retention below.
#
# Set up once:
#   chmod +x backup-to-mac.sh
#   security add-generic-password -a infinia-backup -s infinia-backup -w 'YOUR-PASSWORD'
#   ./backup-to-mac.sh          # prove it works before scheduling

set -uo pipefail

SITE="https://app.infinia.ae"
USERNAME="admin"                       # the login it signs in with
DEST="$HOME/Downloads/Portal Backup"
KEEP_DAYS=60                           # older copies are deleted
LOG="$DEST/backup-log.txt"

mkdir -p "$DEST"
say() { echo "$(date '+%Y-%m-%d %H:%M:%S')  $*" | tee -a "$LOG"; }
fail() { say "FAILED: $*"; osascript -e "display notification \"$*\" with title \"Infinia backup failed\"" 2>/dev/null; exit 1; }

# The password lives in the macOS keychain, not in this file.
PASSWORD="$(security find-generic-password -a infinia-backup -s infinia-backup -w 2>/dev/null)"
[ -n "$PASSWORD" ] || fail "No password in the keychain. Run: security add-generic-password -a infinia-backup -s infinia-backup -w 'YOUR-PASSWORD'"

say "Starting backup from $SITE"

# 1. Sign in
TOKEN=$(curl -sS --max-time 60 -X POST "$SITE/auth/login" \
  -d "username=$USERNAME&password=$PASSWORD" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin).get("access_token",""))' 2>/dev/null)
[ -n "$TOKEN" ] || fail "Could not sign in as $USERNAME - check the password in the keychain."

# 2. Take a fresh snapshot on the server
BID=$(curl -sS --max-time 300 -X POST "$SITE/backup/create" -H "Authorization: Bearer $TOKEN" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin).get("id",""))' 2>/dev/null)
[ -n "$BID" ] || fail "The server would not create a backup."

# 3. A download link needs its own short-lived token
DL=$(curl -sS --max-time 60 -X POST "$SITE/auth/download-token" -H "Authorization: Bearer $TOKEN" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin).get("token",""))' 2>/dev/null)
[ -n "$DL" ] || fail "Could not get a download token."

# 4. Download it
STAMP=$(date '+%Y-%m-%d')
TMP="$DEST/.partial-$STAMP.json"
OUT="$DEST/Infinia_Backup_$STAMP.json"
curl -sS --max-time 600 -o "$TMP" "$SITE/backup/$BID/download?token=$DL" || fail "Download failed."

# 5. Only keep it if it is genuinely a full backup. A truncated file or
#    an error page must never overwrite yesterday's good copy.
CHECK=$(python3 - "$TMP" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception as e:
    print(f"NOT JSON: {e}"); raise SystemExit
need = ["employees", "daily_rows", "store_items", "store_movements",
        "material_requests", "material_request_lines", "suppliers", "users"]
missing = [k for k in need if k not in d]
if missing:
    print("INCOMPLETE: missing " + ", ".join(missing)); raise SystemExit
counts = {k: len(v) for k, v in d.items() if isinstance(v, list)}
print("OK " + ", ".join(f"{k}={n}" for k, n in sorted(counts.items()) if n))
PY
)
case "$CHECK" in
  OK*) ;;
  *) rm -f "$TMP"; fail "The downloaded file is not a usable backup - $CHECK" ;;
esac

mv -f "$TMP" "$OUT"
SIZE=$(du -h "$OUT" | cut -f1)
say "Saved $OUT ($SIZE)"
say "  contents: ${CHECK#OK }"

# 6. Housekeeping
find "$DEST" -name 'Infinia_Backup_*.json' -type f -mtime +$KEEP_DAYS -delete 2>/dev/null
COUNT=$(ls -1 "$DEST"/Infinia_Backup_*.json 2>/dev/null | wc -l | tr -d ' ')
say "Done. $COUNT backup(s) kept in this folder."

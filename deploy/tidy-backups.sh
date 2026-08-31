#!/bin/bash
# Keep the backup folder tidy: delete downloaded backups older than 40
# days. A web page cannot touch files on your computer - browsers
# forbid it - so this small job does it instead.
#
# It only ever deletes files named Infinia_Full_Backup_*.json or
# Infinia_Backup_*.json in that one folder. Nothing else is touched.
#
# Set up once:
#   chmod +x tidy-backups.sh
#   ./tidy-backups.sh          # see what it would remove
#
# Then schedule it with com.infinia.tidy.plist, or leave it manual.

set -uo pipefail

DEST="$HOME/Downloads/Portal Backup"
KEEP_DAYS=40
LOG="$DEST/backup-log.txt"

[ -d "$DEST" ] || { echo "No backup folder at $DEST - nothing to tidy."; exit 0; }

say() { echo "$(date '+%Y-%m-%d %H:%M:%S')  $*" | tee -a "$LOG"; }

# Chrome saves a second copy of the same day as "... (1).json"; those
# are duplicates of a file already kept, so they go whatever their age.
DUPES=$(find "$DEST" -maxdepth 1 -name 'Infinia_*Backup*(*).json' -type f 2>/dev/null | wc -l | tr -d ' ')
[ "$DUPES" -gt 0 ] && find "$DEST" -maxdepth 1 -name 'Infinia_*Backup*(*).json' -type f -delete 2>/dev/null

OLD=$(find "$DEST" -maxdepth 1 \( -name 'Infinia_Full_Backup_*.json' -o -name 'Infinia_Backup_*.json' \) \
        -type f -mtime +$KEEP_DAYS 2>/dev/null)
COUNT=$(echo "$OLD" | grep -c . || true)

if [ "$COUNT" -gt 0 ]; then
  echo "$OLD" | while read -r f; do [ -n "$f" ] && rm -f "$f"; done
  say "Tidied: removed $COUNT backup(s) older than $KEEP_DAYS days" \
      "${DUPES:+and $DUPES duplicate(s)}"
else
  say "Tidied: nothing older than $KEEP_DAYS days${DUPES:+, removed $DUPES duplicate(s)}"
fi

KEPT=$(ls -1 "$DEST"/Infinia_*Backup*.json 2>/dev/null | wc -l | tr -d ' ')
SIZE=$(du -sh "$DEST" 2>/dev/null | cut -f1)
say "  $KEPT backup(s) kept, folder is $SIZE"

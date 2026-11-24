#!/bin/bash
# Voice for the personal space (24/11/2026). Run once on the VPS:
#   sudo bash ~/infinia-labour-tool/deploy/install-voice.sh
#
# Puts faster-whisper into the app's Python and downloads the English speech model (~140 MB) next to the app folder
# (../infinia-voice/base.en). Nothing restarts and nothing else changes; the mic in the personal space starts
# working at once. The model only runs for a few seconds while a clip is written out, then its memory is freed.
set -e
LIVE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
UNIT="$(systemctl cat infinia 2>/dev/null)" || { echo "The service 'infinia' was not found."; exit 1; }
EXEC="$(echo "$UNIT" | grep '^ExecStart=' | grep -v '^ExecStart=$' | tail -1 | cut -d= -f2-)"
VENV_BIN="$(dirname "$(echo "$EXEC" | awk '{print $1}')")"
[ -x "$VENV_BIN/pip" ] || { echo "No pip next to $VENV_BIN - set this up by hand."; exit 1; }
DEST="$(dirname "$LIVE_DIR")/infinia-voice/base.en"

echo "Installing faster-whisper into $VENV_BIN ..."
"$VENV_BIN/pip" install -q "faster-whisper==1.1.1"
echo "Downloading the speech model to $DEST ..."
mkdir -p "$DEST"
"$VENV_BIN/python" -c "from faster_whisper import download_model; download_model('base.en', output_dir='$DEST')"
chmod -R a+rX "$(dirname "$DEST")"
[ -f "$DEST/model.bin" ] || { echo "The model did not download - check the internet on the server and run again."; exit 1; }
echo "Checking it works ..."
cd "$LIVE_DIR/app" && "$VENV_BIN/python" -c "import voice_stt; print('Voice ready:', voice_stt.ready())"

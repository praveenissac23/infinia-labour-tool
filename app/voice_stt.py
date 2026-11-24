"""Speech to text for the personal space (24/11/2026).

Safari's own speech recognition does not work in an iPhone Home Screen app, so the page records the voice and
sends the clip here. It is turned into text on this server with faster-whisper - no outside service, nothing leaves.

Runs as its own process so the model's memory (~300 MB) never sits inside the app (2.5 GB cap):
  python3 voice_stt.py <model dir> <audio file>   one clip, prints the text (used by install-voice.sh to check)
  python3 voice_stt.py --serve <model dir>        live mode: model loaded once; reads an audio path per line, answers
                                                  one JSON line {"text": ...}. The app stops it after 90 s unused.
Set up once with deploy/install-voice.sh.
"""
import os
import sys


def model_dir() -> str:
    """Where install-voice.sh puts the model: next to the app folder, or INFINIA_VOICE_DIR."""
    d = os.environ.get("INFINIA_VOICE_DIR")
    if d:
        return d
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(os.path.dirname(here)), "infinia-voice", "base.en")


def ready() -> bool:
    """Set up on this server? (checked without loading anything)"""
    import importlib.util
    return importlib.util.find_spec("faster_whisper") is not None and os.path.isfile(os.path.join(model_dir(), "model.bin"))


def _text(m, path: str) -> str:
    segs, _ = m.transcribe(path, language="en", beam_size=1, vad_filter=True,
                           initial_prompt="Infinia, DEWA, LPO, payroll, Zoho, site.")   # words it should spell right
    return " ".join(s.text.strip() for s in segs).strip()


def _model(mdir: str):
    from faster_whisper import WhisperModel
    return WhisperModel(mdir, device="cpu", compute_type="int8", cpu_threads=2)


def main(mdir: str, path: str) -> None:
    sys.stdout.write(_text(_model(mdir), path))


def serve(mdir: str) -> None:
    import json
    m = _model(mdir)
    sys.stdout.write(json.dumps({"ready": True}) + "\n"); sys.stdout.flush()
    for line in sys.stdin:
        path = line.strip()
        if not path:
            continue
        try:
            out = {"text": _text(m, path)}
        except Exception as e:                      # a broken clip never stops the live mode
            out = {"error": str(e)[:200]}
        sys.stdout.write(json.dumps(out) + "\n"); sys.stdout.flush()


if __name__ == "__main__":
    if sys.argv[1] == "--serve":
        serve(sys.argv[2])
    else:
        main(sys.argv[1], sys.argv[2])

"""Speech to text for the personal space (24/11/2026).

Safari's own speech recognition does not work in an iPhone Home Screen app, so the page records the voice and
sends the clip here. It is turned into text on this server with faster-whisper - no outside service, nothing leaves.

Run as its own short process (python3 voice_stt.py <model dir> <audio file>) so the model's memory (~300 MB) is
given back the moment the text is out - the app itself stays inside its 2.5 GB cap. Prints the text, nothing else.
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


def main(mdir: str, path: str) -> None:
    from faster_whisper import WhisperModel
    m = WhisperModel(mdir, device="cpu", compute_type="int8", cpu_threads=2)
    segs, _ = m.transcribe(path, language="en", beam_size=1, vad_filter=True,
                           initial_prompt="Infinia, DEWA, LPO, payroll, Zoho, site.")   # words it should spell right
    sys.stdout.write(" ".join(s.text.strip() for s in segs).strip())


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

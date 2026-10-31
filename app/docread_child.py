"""A scan read in its own process (est_fileread.run_scan): the web process never holds the OCR's memory.

    python3 docread_child.py <in file> <name> <out file> <max pages>

Reads the file with docread (OCR on), writes the layout model pickled to <out file>. The parent sets the memory cap
(RLIMIT_AS, inherited by tesseract), the time limit and kills the whole process group on overrun.
"""
import os
import pickle
import sys

os.environ.setdefault("OMP_THREAD_LIMIT", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")


def main():
    src, name, out, maxp = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4] or 0)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from docread.load import load
    with open(src, "rb") as fh:
        data = fh.read()
    doc = load(data, name, ocr=True, max_pages=maxp or None)
    with open(out + ".part", "wb") as fh:
        pickle.dump(doc, fh, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(out + ".part", out)


if __name__ == "__main__":
    try:
        main()
    except MemoryError:
        sys.exit(3)

"""Run every test, each on its own fresh empty database, several at a time.

    python3 tests/run_all.py            # all tests
    python3 tests/run_all.py lpo bill   # only tests whose name has 'lpo' or 'bill'

A test passes when it exits 0 and prints no FAIL line. Tests listed in tests/needs_data.txt need a copy of real data
(the audit database) and are skipped unless INFINIA_TEST_DATA points at one; tests in tests/known_failing.txt are
run but do not fail the run (each has a reason there) - the list should only ever get shorter.
Exit code 0 = everything that must pass passed. Run before every push; GitHub runs it on every push too."""
import os, re, sys, shutil, subprocess, tempfile, time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")
APP = os.path.join(ROOT, "app")


def _list(name):
    p = os.path.join(TESTS, name)
    if not os.path.exists(p):
        return {}
    out = {}
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#"):
            k, _, why = line.partition(" ")
            out[k] = why.strip(" -")
    return out


def run_one(name, data):
    tmp = tempfile.mkdtemp(prefix="it_")
    db = os.path.join(tmp, "t.db")
    if data:
        shutil.copy(data, db)
    env = dict(os.environ, DATABASE_URL=f"sqlite:///{db}", INFINIA_NO_SCHED="1", INFINIA_NO_PUSH="1", INFINIA_NO_MAIL="1",
               INFINIA_DATA_DIR=os.path.join(tmp, "data"), INFINIA_BOARDS_DIR=os.path.join(tmp, "boards"),
               INFINIA_CHAT_DIR=os.path.join(tmp, "chat"), PYTHONDONTWRITEBYTECODE="1")
    t0 = time.time()
    try:
        r = subprocess.run([sys.executable, os.path.join(TESTS, name)], cwd=APP, env=env, capture_output=True, text=True, timeout=600)
        out = (r.stdout or "") + (r.stderr or "")
        bad = r.returncode != 0 or re.search(r"^\s*FAIL\b|\bFAILED\b|^Traceback", out, re.M)
        tail = "\n".join([l for l in out.splitlines() if re.search(r"FAIL|Error|Traceback", l)][:6]) or out.strip().splitlines()[-1:] and out.strip().splitlines()[-1] or ""
    except subprocess.TimeoutExpired:
        bad, tail = True, "timed out after 600s"
    shutil.rmtree(tmp, ignore_errors=True)
    return name, not bad, round(time.time() - t0, 1), tail


def main():
    want = [a.lower() for a in sys.argv[1:]]
    needs, known = _list("needs_data.txt"), _list("known_failing.txt")
    data = os.environ.get("INFINIA_TEST_DATA")
    names = sorted(f for f in os.listdir(TESTS) if f.endswith("_test.py") and (not want or any(w in f.lower() for w in want)))
    skipped = [n for n in names if n in needs and not data]
    names = [n for n in names if n not in skipped]
    jobs = int(os.environ.get("INFINIA_TEST_JOBS") or max(2, (os.cpu_count() or 2)))
    print(f"Running {len(names)} tests ({len(skipped)} skipped - need real data), {jobs} at a time", flush=True)
    res = []
    with ThreadPoolExecutor(jobs) as ex:
        for name, ok, secs, tail in ex.map(lambda n: run_one(n, data if n in needs else None), names):
            res.append((name, ok, secs, tail))
            mark = "ok  " if ok else ("known" if name in known else "FAIL")
            print(f"{mark} {name} ({secs}s)" + ("" if ok else "\n      " + tail.replace("\n", "\n      ")), flush=True)
    failed = [r for r in res if not r[1] and r[0] not in known]
    fixed = [r[0] for r in res if r[1] and r[0] in known]
    print(f"\n{sum(r[1] for r in res)} passed, {len(failed)} failed, {sum(1 for r in res if not r[1] and r[0] in known)} known failing, {len(skipped)} skipped")
    if fixed:
        print("Now passing - take off tests/known_failing.txt: " + ", ".join(fixed))
    if failed:
        print("FAILED: " + ", ".join(r[0] for r in failed))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

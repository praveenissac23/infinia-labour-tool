"""The server's limits on reading scans (est_fileread.run_scan): a scan is read in its own process with a memory cap, a
time limit and a page cap, one at a time across every worker, and only when memory is free - otherwise the reply is
501 + a clear message and the browser reads the file itself (as when the OCR package is missing). Excel / Word / typed
PDFs are read in the web process with their own time limit. The web process always survives.
    cp /tmp/claude-0/full.db /tmp/edl.db && cd app && DATABASE_URL=sqlite:////tmp/edl.db INFINIA_NO_SCHED=1 python3 ../tests/est_docread_limits_test.py
Starts one real server on DOCREAD_TEST_PORT (default 8785) for the "app process survives" check.
"""
import fcntl, json, os, signal, subprocess, sys, tempfile, time, urllib.request
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main
import est_fileread as F

HERE = os.path.dirname(os.path.abspath(__file__))
c = TestClient(main.app); c.__enter__()
fails = []


def ck(n, ok, x=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -> {str(x)[:400]}"))
    if not ok:
        fails.append(n)


H = {"Authorization": "Bearer " + c.post("/auth/login", data={"username": "admin", "password": "changeme123"}).json()["access_token"]}
D = os.environ.get("CORPUS") or os.path.join(tempfile.gettempdir(), "edr_corpus")
if not os.path.exists(os.path.join(D, "truth.json")):
    subprocess.run([sys.executable, os.path.join(HERE, "docread", "synth.py"), D, "--n", "4", "--seed", "2026", "--scans", "0.5", "--vo", "3", "--contracts", "1"], check=True, capture_output=True)
SCAN = os.path.join(D, "ipa_01_three_scan.pdf")
TRUTH = {x["file"]: x for x in json.load(open(os.path.join(D, "truth.json")))}["ipa_01_three_scan.pdf"]["truth"]


def post(fname, path=None):
    with open(path or os.path.join(D, fname), "rb") as fh:
        return c.post("/store/est/read/ipa", files={"file": (fname, fh.read())}, data={"subs": "[]"}, headers=H)


def children():
    out = subprocess.run(["ps", "-eo", "pid,ppid,args"], capture_output=True, text=True).stdout
    return [l for l in out.splitlines() if "docread_child.py" in l and str(os.getpid()) in l.split()[1:2]]


def reset():
    for k in ("DOCREAD_MEM_MB", "DOCREAD_TIMEOUT", "DOCREAD_MAX_PAGES", "DOCREAD_LIGHT_TIMEOUT"):
        os.environ.pop(k, None)


# 0. a scan read normally, in its own process
reset()
r = post("ipa_01_three_scan.pdf")
ck("a scan is read in its own process: figures as on the bill", r.status_code == 200 and r.json()["fields"].get("claimed_cum") == TRUTH["claimed_cum"], r.text[:300])
ck("...no reading process left behind", not children(), children())

# 1. the memory cap exceeded -> the child is stopped, 501 busy, this process carries on
os.environ["DOCREAD_MEM_MB"] = "120"
t = time.time(); r = post("ipa_01_three_scan.pdf")
ck("memory cap exceeded: 501 'Server busy ... read on this computer instead'", r.status_code == 501 and "read on this computer" in r.json()["detail"], r.text[:300])
ck("...the web process carries on (next request answered)", c.get("/health").status_code == 200 and post("ipa_00_single.xlsx").status_code == 200)
reset()

# 2. not enough memory free to start -> 501 busy at once, nothing started
os.environ["DOCREAD_MEM_MB"] = str(10 ** 6)
t = time.time(); r = post("ipa_01_three_scan.pdf")
ck("memory not free (MemAvailable < cap + 150 MB): 501 busy at once", r.status_code == 501 and "Server busy" in r.json()["detail"] and time.time() - t < 3, [r.status_code, r.text[:200], time.time() - t])
reset()

# 3. another scan being read (the lock held) -> 501 busy at once, no queueing
lf = open(F.LOCK_FILE, "a+"); fcntl.flock(lf, fcntl.LOCK_EX)
t = time.time(); r = post("ipa_01_three_scan.pdf")
ck("lock held by another worker: 501 'Server busy reading another scan' at once", r.status_code == 501 and "Server busy reading another scan" in r.json()["detail"] and time.time() - t < 3, [r.status_code, r.text[:200], time.time() - t])
r = post("ipa_00_single.xlsx")
ck("...Excel is still read meanwhile (not a scan)", r.status_code == 200, r.text[:200])
fcntl.flock(lf, fcntl.LOCK_UN); lf.close()

# 4. too slow -> the child killed, 501
os.environ["DOCREAD_TIMEOUT"] = "1"
t = time.time(); r = post("ipa_01_three_scan.pdf")
ck("time limit passed: 501 'took too long ... read on this computer instead'", r.status_code == 501 and "too long" in r.json()["detail"] and time.time() - t < 10, [r.status_code, r.text[:200], time.time() - t])
time.sleep(0.5)
ck("...the reading process (and its tesseract) killed", not children(), children())
reset()

# 5. more pages than the cap -> the first N read, said at the top as a sum not agreeing
d = tempfile.mkdtemp()
three = os.path.join(d, "three pages scan.pdf")
subprocess.run(["pdfunite", SCAN, SCAN, SCAN, three], check=True)
os.environ["DOCREAD_MAX_PAGES"] = "1"
r = post("three pages scan.pdf", three)
j = r.json() if r.status_code == 200 else {}
ck("page cap: only the first page read, marked at the top (amber / cross)", r.status_code == 200 and j.get("partial") == [1, 3] and j["sums"][0]["ok"] is False and "first 1 of 3" in j["sums"][0]["name"] and len(j["pages"]) == 1, r.text[:300])
ck("...that page's figures still read", j.get("fields", {}).get("claimed_cum") == TRUTH["claimed_cum"], j.get("fields"))
reset()

# 6. Excel / Word / typed PDF: in the web process, with their own time limit
import docread.load  # noqa: F401
DL = sys.modules["docread.load"]
real = DL.load
DL.load = lambda *a, **k: (time.sleep(3), real(*a, **k))[1]
os.environ["DOCREAD_LIGHT_TIMEOUT"] = "1"
t = time.time(); r = post("ipa_00_single.xlsx")
ck("Excel over its time limit: 501 'took too long', answered in time", r.status_code == 501 and "too long" in r.json()["detail"] and time.time() - t < 3, [r.status_code, r.text[:200], time.time() - t])
DL.load = real
reset()
r = post("ipa_00_single.pdf")
ck("typed PDF read in the web process (no child)", r.status_code == 200 and not children())

# 7. a real server: the cap exceeded, the server process survives and goes on answering
port = int(os.environ.get("DOCREAD_TEST_PORT", "8785"))
env = dict(os.environ, DOCREAD_MEM_MB="120")
srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--port", str(port), "--log-level", "warning"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(90):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2); break
        except Exception:
            time.sleep(1)
    tok = json.loads(urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/auth/login", data=b"username=admin&password=changeme123")).read())["access_token"]
    boundary = "----edl"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"scan.pdf\"\r\nContent-Type: application/pdf\r\n\r\n").encode() + open(SCAN, "rb").read() + \
        f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"subs\"\r\n\r\n[]\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/store/est/read/ipa", data=body, headers={"Authorization": "Bearer " + tok, "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        urllib.request.urlopen(req, timeout=120); code = 200
    except urllib.error.HTTPError as e:
        code = e.code
    alive = srv.poll() is None
    ok2 = urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5).status == 200
    ck("real server, scan over the memory cap: 501 to the browser, the server process alive and answering", code == 501 and alive and ok2, [code, alive, ok2])
finally:
    srv.send_signal(signal.SIGTERM)
    try:
        srv.wait(10)
    except Exception:
        srv.kill()

print(f"\n{len(fails)} FAILED" if fails else "\nALL PASS")
sys.exit(1 if fails else 0)

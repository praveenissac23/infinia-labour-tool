"""'The app has been updated' bar (23/11/2026): it would not go away. It compared the server's build with a note
kept in the phone's storage; when that note was stale the bar came back after every refresh. Now the page carries
its own build and the server reports the same fingerprint, so a current page never shows the bar."""
import os, sys, json, subprocess, time, tempfile, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))
os.environ.setdefault("INFINIA_NO_PUSH", "1")
os.environ.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(tempfile.mkdtemp(), "u.db"))
FAIL = []
def ck(l, ok, x=""):
    print(("PASS " if ok else "FAIL ") + l + ("" if ok else f"  [{x}]"))
    if not ok: FAIL.append(l)

import main
want = json.load(open(os.path.join(ROOT, "app-version.json")))["build"]
html = open(os.path.join(ROOT, "app.html"), encoding="utf-8").read()
ck("server reports the fingerprint in app-version.json", str(main._app_build()) == want, (main._app_build(), want))
ck("the built page carries the same fingerprint", f'window.__PAGE_BUILD="{want}"' in html)
src = open(os.path.join(ROOT, "app-classic.html"), encoding="utf-8").read()
ck("the bar has a close button", 'class=\\"bb-x\\"' in src and "infinia_refreshed_for" in src)

try:
    import playwright  # noqa
    have_pw = subprocess.run(["node", "-e", "require('playwright')"], capture_output=True).returncode == 0
except Exception:
    have_pw = subprocess.run(["node", "-e", "require('playwright')"], capture_output=True).returncode == 0
if not have_pw:
    print("SKIP browser part (no playwright)")
else:
    port = "8061"
    env = dict(os.environ, DATABASE_URL="sqlite:///" + os.path.join(tempfile.mkdtemp(), "t.db"), SRV_PORT=port, SRV_API_PORT="8062")
    srv = subprocess.Popen([sys.executable, os.path.join(ROOT, "tests", "serve_like_nginx.py")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try: urllib.request.urlopen(f"http://localhost:{port}/health", timeout=2); break
            except Exception: time.sleep(1)
        js = r"""
const { chromium, devices } = require('playwright');
(async () => {
  const b = await chromium.launch(); const ctx = await b.newContext({...devices['iPhone 13']}); const p = await ctx.newPage();
  const out = {};
  await p.goto('http://localhost:PORT/'); await p.waitForTimeout(3500);
  // a stale note on the phone, page is current: no bar
  await p.evaluate(() => { localStorage.setItem('infinia_build', 'old-note'); checkBuild(); }); await p.waitForTimeout(1200);
  out.staleNote = !!(await p.$('#build-bar'));
  // the page really is old: bar shows
  await p.evaluate(() => { window.__PAGE_BUILD = 'older'; checkBuild(); }); await p.waitForTimeout(1200);
  out.oldPage = !!(await p.$('#build-bar'));
  await p.click('#build-bar .bb-x'); await p.waitForTimeout(300);
  out.closed = !(await p.$('#build-bar'));
  await p.evaluate(() => checkBuild()); await p.waitForTimeout(1200);
  out.staysClosed = !(await p.$('#build-bar'));
  // after Refresh now the current page loads: no bar
  await p.evaluate(() => sessionStorage.removeItem('infinia_refreshed_for'));
  await p.evaluate(() => checkBuild()); await p.waitForTimeout(1200);
  await p.click('#build-bar button'); await p.waitForTimeout(5000);
  await p.evaluate(() => checkBuild()); await p.waitForTimeout(1500);
  out.afterRefresh = !(await p.$('#build-bar'));
  console.log(JSON.stringify(out)); await b.close();
})();""".replace("PORT", port)
        f = os.path.join(tempfile.mkdtemp(), "bar.js"); open(f, "w").write(js)
        r = subprocess.run(["node", f], capture_output=True, text=True, timeout=120, cwd=os.path.dirname(f))
        o = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {}
        ck("current page + stale note on the phone: no bar", o.get("staleNote") is False, r.stdout + r.stderr[-300:])
        ck("page really older than the server: bar shows", o.get("oldPage") is True, o)
        ck("x hides it", o.get("closed") is True, o)
        ck("hidden stays hidden for that update", o.get("staysClosed") is True, o)
        ck("Refresh now: the fresh page shows no bar", o.get("afterRefresh") is True, o)
    finally:
        srv.terminate()
print("\n" + ("ALL PASS" if not FAIL else f"{len(FAIL)} FAILED"))
sys.exit(1 if FAIL else 0)

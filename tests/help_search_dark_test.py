"""The "What do you want to do?" search list on the dark dashboards (24/11/2026, owner's screenshot): the dark top bar
turned every span white, so the result titles in the white list could not be read. The list keeps its own colours."""
import os, sys, socket, subprocess, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/../app")
import database, models, auth, main  # noqa: F401
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("SKIP - no browser here (playwright not installed)"); sys.exit(0)

FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  {x}'))
    if not ok: FAIL.append(l)

models.Base.metadata.create_all(bind=database.engine)
db = database.SessionLocal()
db.add(models.User(username="boss", full_name="Boss", role="admin", hashed_password=auth.hash_password("p")))
db.add(models.User(username="keeper", full_name="Store keeper", role="office", permissions="dashboard,store,storekeeper,requests,petty_site",
                   hashed_password=auth.hash_password("p")))
db.commit(); db.close()

def free():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p
port, api = free(), free()
srv = subprocess.Popen([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "serve_like_nginx.py")],
                       env=dict(os.environ, SRV_PORT=str(port), SRV_API_PORT=str(api)), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
B = f"http://127.0.0.1:{port}"
dark = lambda rgb: sum(int(x) for x in rgb.strip("rgba() ").split(",")[:3]) < 3 * 160
try:
    import urllib.request
    for _ in range(80):
        try: urllib.request.urlopen(B + "/health", timeout=1); break
        except Exception: time.sleep(0.5)
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        for who in ("boss", "keeper"):
            p = br.new_page(viewport={"width": 1280, "height": 800})
            tok = p.request.post(B + "/auth/login", form={"username": who, "password": "p"}).json()["access_token"]
            p.goto(B + "/"); p.evaluate("t => sessionStorage.setItem('infinia_token', t)", tok); p.goto(B + "/"); p.wait_for_timeout(4000)
            p.type("#help-search", "cash", delay=30); p.wait_for_timeout(1000)
            c = p.evaluate("""() => { const r = document.querySelector('#help-results .help-r'); if (!r) return null;
                return { on: !!document.querySelector('#screen-dashboard.active'), title: getComputedStyle(r).color,
                         tag: getComputedStyle(r.querySelector('.help-area')).color, bg: getComputedStyle(document.getElementById('help-results')).backgroundColor }; }""")
            ck(f"{who}: dashboard showing, search list open", bool(c and c["on"]), c)
            ck(f"{who}: result titles dark on the white list (readable)", bool(c) and dark(c["title"]) and not dark(c["bg"]), c)
            ck(f"{who}: the Go to / Task tag keeps its colour", bool(c) and dark(c["tag"]), c)
            p.close()
        br.close()
finally:
    srv.terminate()
print("\n" + ("ALL PASS" if not FAIL else f"{len(FAIL)} FAILED"))
sys.exit(1 if FAIL else 0)

"""Settings > Access: "Notifications this role may receive" sits in the left column under the role list (the empty
space there), so the page/tab ticks on the right start straight under the role name. Ticking there still saves,
switching roles shows that role's own notifications, and on a phone they come after the tick list (17/11/2026)."""
import os, sys, socket, subprocess, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/../app")
import database, models, auth, main  # noqa: F401  (main makes the tables)
from playwright.sync_api import sync_playwright

FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  {x}'))
    if not ok: FAIL.append(l)

models.Base.metadata.create_all(bind=database.engine)
db = database.SessionLocal()
db.add(models.User(username="boss", full_name="Boss", role="admin", hashed_password=auth.hash_password("p")))
store_tabs = ["store.store.home", "store.store.give", "store.requests.requests", "store.requests.approvals"]
r1 = models.AccessRole(name="Store Keeper with a rather long role name", notes="", screens=",".join(["settings"] + store_tabs), notif=None)
r2 = models.AccessRole(name="Quantity Surveyor", notes="", screens="settings,estimation.estproj", notif="requests")
db.add_all([r1, r2]); db.commit()
rid1, rid2 = r1.id, r2.id
n_groups = len([g for g in main.NOTIF_GROUPS if g[0] != "watch"])
db.close()

def free():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p
port, api = free(), free()
srv = subprocess.Popen([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "serve_like_nginx.py")],
                       env=dict(os.environ, SRV_PORT=str(port), SRV_API_PORT=str(api)), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
B = f"http://127.0.0.1:{port}"
try:
    import urllib.request
    for _ in range(80):
        try: urllib.request.urlopen(B + "/health", timeout=1); break
        except Exception: time.sleep(0.5)
    shots = os.environ.get("SHOTS")
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        p = b.new_page(viewport={"width": 1366, "height": 800})
        errs = []; p.on("pageerror", lambda e: errs.append(str(e)))
        p.goto(B + "/portal/access.html?view=roles")
        p.fill("#login-username", "boss"); p.fill("#login-password", "p"); p.evaluate("doLogin()")
        p.wait_for_selector("#role-edit .ed-top", timeout=15000); p.wait_for_timeout(800)
        p.click("#role-list .rl:has-text('Store Keeper')"); p.wait_for_timeout(400)
        left = p.locator("#role-notif .nf-r input")
        ck("notifications are in the left column", left.count() == n_groups, left.count())
        ck("not repeated on the right", "Notifications" not in p.inner_text("#role-edit"))
        ck("a role never set up gets every group ticked", p.locator("#role-notif .nf-r input:checked").count() == n_groups)
        box = p.locator("#role-notif").bounding_box(); lst = p.locator("#role-list").bounding_box()
        ck("under the role list, inside the left column", box and lst and box["y"] >= lst["y"] + lst["height"] - 1 and box["x"] < 300, (box, lst))
        tree = p.locator("#tree").bounding_box(); top = p.locator("#role-edit .ed-top").bounding_box()
        ck("page ticks start close under the role name", tree["y"] - (top["y"] + top["height"]) < 120, (tree, top))
        if shots: p.screenshot(path=shots + "/access_left.png")
        # untick one, save, read back
        left.nth(0).uncheck(); p.wait_for_timeout(200)
        ck("count updates", f"{n_groups - 1} of {n_groups}" in p.inner_text("#role-notif .nf-h"))
        ck("marked not saved", "Not saved" in p.inner_text("#ed-hint"))
        p.click("#role-edit button:has-text('Save')"); p.wait_for_timeout(1200)
        db = database.SessionLocal(); saved = db.get(models.AccessRole, rid1).notif; db.close()
        ck("saved from the left column", saved is not None and len([x for x in saved.split(",") if x]) == n_groups - 1, saved)
        # switch role
        p.click("#role-list .rl:has-text('Quantity Surveyor')"); p.wait_for_timeout(500)
        ck("other role shows its own notifications", p.locator("#role-notif .nf-r input:checked").count() < n_groups - 1
           and p.locator("#role-notif .nf-r input").nth(0).is_checked(), p.locator("#role-notif .nf-r input:checked").count())
        # new role: notifications show for it too
        p.evaluate("newRole()"); p.wait_for_timeout(300)
        ck("new role: every group ticked", p.locator("#role-notif .nf-r input:checked").count() == n_groups)
        ck("no page errors", not errs, errs)
        # phone
        m = b.new_page(viewport={"width": 390, "height": 844})
        m.goto(B + "/portal/access.html?view=roles"); m.wait_for_timeout(300)
        m.fill("#login-username", "boss"); m.fill("#login-password", "p"); m.evaluate("doLogin()")
        m.wait_for_selector("#role-edit .ed-top", timeout=15000); m.wait_for_timeout(600)
        ck("phone: notifications still shown", m.locator("#role-notif .nf-r input").count() == n_groups)
        ck("phone: the tick list comes first, notifications after it", m.evaluate("document.getElementById('role-notif').getBoundingClientRect().top > document.getElementById('tree').getBoundingClientRect().bottom - 1"))
        if shots: m.screenshot(path=shots + "/access_phone.png", full_page=True)
        b.close()
finally:
    srv.terminate()
print('\n' + ('ALL PASS' if not FAIL else f'{len(FAIL)} FAILED'))
sys.exit(1 if FAIL else 0)

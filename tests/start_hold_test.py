"""No page flashes at the start (26/11/2026).

Reported: "sometimes restricted dashboard and pages shows first for seconds and goes". Found two ways it happened:
  * signing in drew the staff dashboard with the whole menu, then swapped to this login's own dashboard / first page
    and trimmed the menu - nothing covered it (a reload was covered, a sign-in was not);
  * on a slow line the cover of a reload was taken away after 1.6 s whatever the state - before the first page had
    even been chosen - so the half-built page showed until the answers came.
Now: sign-in is covered like a reload; the cover stays until the first page is chosen and quiet (15 s is only a
safety net); a small ring shows while waiting; and everything the start needs is asked for in one go.

Run: python3 tests/run_all.py start_hold
"""
import re, sys
FAIL = []


def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{x}]'))
    if not ok:
        FAIL.append(l)


src = open('../app-classic.html', encoding='utf-8').read()
app = open('../app.html', encoding='utf-8').read()
bld = open('../deploy/build_temporary_pages.py', encoding='utf-8').read()

i = src.index('async function doLogin()'); login = src[i:src.index('function doLogout()', i)]
ck('sign-in is covered before the app is shown', login.index('pgHoldStart()') < login.index('getElementById("app-screen").style.display = "block"'))
ck('...and uncovered once the start has run', login.index('await initApp();') < login.index('pgUnhold()'))
ck('...also when the start fails (the error must be seen)', 'catch (e) {\n    if (typeof pgHoldEnd === "function") pgHoldEnd();' in login)
ck('the cover is never dropped at 1.6 s any more', '}, 1600);' not in bld[bld.index('EARLY = '):bld.index('HUB_HTML = ')])
ck('...15 s is only the safety net, for reload and sign-in', bld.count('}, 15000);') == 1 and 'setTimeout(pgHoldEnd, 15000);' in bld)
ck('...once the first page is chosen it shows when quiet, 4 s at most', 'now - start > 4000) { mo.disconnect(); pgHoldEnd(); return; }' in bld)
ck('a refused sign-in shows the sign-in box without the ring', 'if (el) el.remove(); pgHoldEnd(); }' in bld)
ck('a ring shows while the page is held, only after 0.4 s', 'html.pg-wait::after' in bld and 'pgspinin .25s .4s both' in bld)
ck('a tab is held until its data is in (2.5 s at most) with a line on top after a quarter second',
   'now - start > 2500) {' in bld and 'bar.classList.add("on"); }, 250);' in bld and '#pg-busy.on { opacity: 1; }' in bld)
ck('the built page carries all of it (run python3 deploy/build_temporary_pages.py)', all(x in app for x in ('pgHoldStart', 'pg-wait', 'pg-busy', 'startWarm')))

# one trip for the whole start: the paths asked early must be exactly the ones the start asks for later
i = src.index('function startWarm()'); warm = src[i:src.index('async function initApp()', i)]
init = src[src.index('async function initApp()'):src.index('async function initApp()') + 4000]
load = src[src.index('async function loadDate('):src.index('async function loadDate(') + 1500]
for path in ('"/permissions/me"', '"/employees?active_only=true"', '"/sites"', '"/engineers"'):
    ck(f'the start asks early for {path}, the same address it uses later', path in warm and path in init)
for path, later in (('`/attendance/${d}`', '`/attendance/${dateStr}`'), ('`/attendance/last-sites/${d}`', '`/attendance/last-sites/${dateStr}`'),
                    ('`/employees?active_only=true&as_of=${d}`', '`/employees?active_only=true&as_of=${dateStr}`')):
    ck(f'...and for today\'s {later}', path in warm and later in load)
ck('it runs first thing at sign-in and before "who am I" on a reload', 'async function initApp() {\n  startWarm();' in src and 'startWarm();\n    apiCall("/auth/me")' in src)
ck('a refused early read never shows as an error', '.forEach(u => { try { apiCall(u).catch(() => {}); } catch (e) {} });' in warm)
ck('the percent sign is not used in the added script (the page builder would trip on it)', '%' not in bld[bld.index('function pgHoldStart'):bld.index('function pgSettleActive')])

print("\nALL PASS" if not FAIL else f"\n{len(FAIL)} FAILED")
sys.exit(1 if FAIL else 0)

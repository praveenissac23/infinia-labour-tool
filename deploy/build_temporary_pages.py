"""Build the temporary pages from app.html.

    python3 deploy/build_temporary_pages.py

Each page under temporary/Infinia/ is the app itself - the same markup,
the same script, the same server - with a menu of nine entries in place
of seventeen and the old pages arranged as tabs. Nothing is rewritten:
a page is app.html with its sidebar swapped, a few blocks moved, and a
short script added at the end, so what is entered on a temporary page
is entered in the app, and the day the layout moves into app.html
there is nothing to carry across.

Run again after every change to app.html; the pages are generated, not
edited by hand. `git diff` shows only what app.html changed.
"""
import os, re, html, json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "app.html")
OUT = os.path.join(ROOT, "temporary", "Infinia")


def tab(id, screen, label, right=None, show=None):
    return {"id": id, "screen": screen, "label": label, "right": right or screen, "show": show or []}


# page key -> (title, tabs)
PAGES = {
    "dashboard": ("Dashboard", [tab("dashboard", "dashboard", "Overview")]),
    "attendance": ("Attendance", [
        tab("attendance", "attendance", "Daily attendance"),
        tab("livecard", "livecard", "Live card"),
        tab("masterdata", "masterdata", "Labour master data")]),
    "payroll": ("Payroll", [
        tab("combine", "combine", "Salary cards"),
        tab("errorcheck", "errorcheck", "Check before you pay"),
        tab("hrpayroll", "hrpayroll", "Office HR & Payroll")]),
    "store": ("Store & Purchasing", [
        tab("store", "store", "Store / inventory"),
        tab("requests", "requests", "Material requests"),
        tab("approvals", "approvals", "Approvals"),
        tab("purchase", "purchase", "Purchase orders", "approvals"),
        tab("followup", "followup", "Order follow-up", "requests"),
        tab("lporegister", "lporegister", "LPO register", "approvals"),
        tab("suppliers", "suppliers", "Suppliers", "approvals")]),
    "reports": ("Reports", [
        tab("labour", "pgreports", "Labour", ["reports", "combine", "errorcheck", "livecard"], ["#pgrep-labour"]),
        tab("office", "pgreports", "Office payroll", "hrpayroll", ["#pgrep-office"]),
        tab("people", "pgreports", "People", ["people_labour", "people_office", "people_local", "people_household"], ["#pgrep-people"]),
        tab("storerep", "pgreports", "Store & purchasing", ["store", "approvals", "requests"], ["#pgrep-store"]),
        tab("builder", "reports", "Report builder", "reports")]),
    "settings": ("Settings", [
        tab("general", "settings", "General", "settings",
            ["#pg-password-card", "#company-card", "#signature-card", "#store-reset-card"]),
        tab("companies", "settings", "Companies", "settings", ["#companies-card"]),
        tab("sites", "settings", "Sites & engineers", "settings", ["#pg-sites-block"]),
        tab("logins", "settings", "Logins", "settings", ["#user-mgmt-card", "#pg-roles-card"]),
        tab("backup", "settings", "Backup", "settings", ["#pg-backup-card"])]),
    "activity": ("Activity Monitor", [tab("activity", "activity", "Activity monitor")]),
}
# Screens without a tab of their own, reached from inside another.
EXTRA = {"monthly": "reports"}
ORDER = ["dashboard", "attendance", "people", "payroll", "store", "reports", "settings", "activity", "access"]
# The file each page is served as. nginx sends any address containing
# "reports" to the API (its rule is not anchored), so that page cannot be
# called reports.html.
FILE = {"reports": "reporting"}
def fname(key): return FILE.get(key, key) + ".html"
STANDALONE = {"people": ("People", ["people_labour", "people_office", "people_local", "people_household"]),
              "access": ("Access", "access")}
LABELS = {"dashboard": "Dashboard", "attendance": "Attendance", "payroll": "Payroll", "store": "Store & Purchasing",
          "reports": "Reports", "settings": "Settings", "activity": "Activity Monitor"}

CSS = """
<style>
  /* ---- temporary pages: one menu, tabs in place of pages ---- */
  #legacy-sidebar { display: none !important; }
  .pg-hide { display: none !important; }
  .pg-side { width: 220px; background: var(--black); flex-shrink: 0; padding: 0 0 20px; }
  .pg-side .brand { padding: 14px 16px 18px; border-bottom: 1px solid var(--darkgray); margin-bottom: 10px; text-align: center; }
  .pg-side .brand img { max-width: 100%; height: auto; background: white; border-radius: 6px; padding: 8px 10px; }
  .pg-side .pg-item { color: var(--silver); padding: 11px 20px; font-size: 13.5px; font-weight: bold; cursor: pointer; }
  .pg-side .pg-item:hover { background: var(--darkgray); color: white; }
  .pg-side .pg-item.active { background: var(--red); color: white; }
  .pg-side .pg-group { padding: 12px 20px 6px; font-size: 11px; letter-spacing: 1px; font-weight: 800; color: #F4BFB8; background: rgba(192,57,43,.28); margin-top: 8px; }
  .pg-side .pg-small { color: #8E939A; padding: 8px 20px; font-size: 12px; cursor: pointer; }
  .pg-side .pg-small:hover { color: white; }
  .pg-tabs { display: flex; gap: 6px; padding: 10px 24px 0; background: white; border-bottom: 1px solid #eee; flex-wrap: wrap; }
  .pg-tab { padding: 8px 15px; font-size: 13px; font-weight: 600; cursor: pointer; border-radius: 7px 7px 0 0; color: #8A6560; background: #FDF6F5; border: 1px solid #E7CEC9; border-bottom: none; }
  .pg-tab:hover { background: #FAEBE8; }
  .pg-tab.active { background: var(--red); color: white; border-color: var(--red); }
  .pg-tabs:empty { display: none; }
  /* One font across the pages, the one the office's own machines use. */
  body, button, input, select, textarea { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
  body { font-size: 14px; line-height: 1.45; -webkit-font-smoothing: antialiased; }
  /* The reports hub: one list a tab, a report a row */
  #screen-pgreports .card { max-width: 980px; }
  #screen-pgreports .card h2 { font-size: 17px; margin-bottom: 2px; }
  .pg-rep { display: flex; align-items: center; gap: 10px; padding: 12px 0; border-bottom: 1px solid #F0EDE8; flex-wrap: wrap; }
  .pg-rep:last-child { border-bottom: 0; }
  .pg-rep .t { flex: 1; min-width: 200px; font-weight: 600; font-size: 14px; }
  .pg-rep .t small { display: block; font-weight: normal; color: #888; font-size: 12px; margin-top: 1px; }
  .pg-rep select, .pg-rep input[type=month], .pg-rep input[type=number] { height: 32px; padding: 0 8px; border: 1px solid #D5D9DE; border-radius: 6px; font-size: 12.5px; width: auto; max-width: 330px; flex: 0 0 auto; margin: 0; }
  .pg-rep .btn { padding: 6px 12px; font-size: 12.5px; min-width: 64px; }
  .pg-seg { display: inline-flex; border: 1px solid #E4DCD2; border-radius: 7px; overflow: hidden; background: #FBF8F4; }
  .pg-seg button { border: 0; background: transparent; padding: 6px 10px; font-size: 12px; font-weight: 600; color: #6A5C55; border-right: 1px solid #E4DCD2; cursor: pointer; }
  .pg-seg button:last-child { border-right: 0; } .pg-seg button.on { background: var(--red); color: white; }
  @media (max-width: 900px) { .pg-side { width: 100%; padding-bottom: 6px; } .pg-side .pg-item { display: inline-block; padding: 9px 12px; } .pg-side .pg-group, .pg-side .brand { display: none; } }
</style>
"""

# Shown before the app's own script runs: a page that is resuming a
# sign-in never flashes the sign-in box, and the screen it will land on
# is the only one drawn from the first paint.
EARLY = """
<script>
(function () {
  try {
    if (!sessionStorage.getItem("infinia_token")) return;
    var want = (location.hash || "").slice(1).split(":")[0] || "%(first)s";
    var tabs = %(tabmap)s;
    var screen = tabs[want] || want;
    var css = "#login-screen{display:none!important}#app-screen{display:block!important}" +
              ".screen{display:none!important}#screen-" + screen + "{display:block!important}";
    // The menu as this login last saw it, so it never draws in full and
    // then trims itself once the server answers.
    var menu = null;
    try { menu = JSON.parse(localStorage.getItem("infinia_menu") || "null"); } catch (e) {}
    if (menu && menu.user === (sessionStorage.getItem("infinia_user") || "")) {
      css += ".pg-side .pg-item[data-page]{display:none}" + menu.pages.map(function (pg) { return ".pg-side .pg-item[data-page='" + pg + "']{display:block}"; }).join("");
    } else {
      css += ".pg-side .pg-item[data-page]{visibility:hidden}";
    }
    var st = document.createElement("style"); st.id = "pg-early"; st.textContent = css;
    document.head.appendChild(st);
  } catch (e) {}
})();
</script>
"""

HUB_HTML = """
        <!-- ============ REPORTS HUB (temporary pages) ============ -->
        <div class="screen" id="screen-pgreports">
          <div class="status-msg" id="pgrep-status"></div>
            <div class="card" id="pgrep-labour">
              <h2>Labour - attendance &amp; salary</h2>
              <p style="font-size:12px; color:#888; margin:0 0 8px;">The 26th-to-25th cycle: attendance, salary cards and the checks before paying.</p>
              <div class="pg-rep"><span class="t">Cycle report builder<small>Any columns, any cycle, by company</small></span><button class="btn btn-dark" onclick="switchScreen('reports')">Open</button></div>
              <div class="pg-rep"><span class="t">Salary cards<small>Per worker, for the cycle</small></span><button class="btn btn-dark" onclick="switchScreen('combine')">Open</button></div>
              <div class="pg-rep"><span class="t">Check before you pay<small>Missing days, pay rule, odd hours</small></span><button class="btn btn-dark" onclick="switchScreen('errorcheck')">Open</button></div>
              <div class="pg-rep"><span class="t">Live card<small>The cycle so far, per worker</small></span><button class="btn btn-dark" onclick="switchScreen('livecard')">Open</button></div>
            </div>
            <div class="card" id="pgrep-office">
              <h2>Office payroll</h2>
              <p style="font-size:12px; color:#888; margin:0 0 8px;">Monthly statements and the registers behind them.</p>
              <div class="pg-rep"><span class="t">Salary statement<small>One cycle, as signed</small></span><select id="pgrep-run" class="hr-dd"></select><span id="pgrep-run-btns"></span></div>
              <div class="pg-rep"><span class="t">Consolidated statement<small>Every company, one month</small></span><select id="pgrep-month" class="hr-dd"></select><span id="pgrep-cons-btns"></span></div>
              <div class="pg-rep"><span class="t">Absence register</span><input type="month" id="pgrep-leave-month"><span data-hr="leave"></span></div>
              <div class="pg-rep"><span class="t">Additions &amp; deductions</span><input type="month" id="pgrep-items-month"><span data-hr="items"></span></div>
              <div class="pg-rep"><span class="t">Loans register</span><span data-hr="loans"></span></div>
              <div class="pg-rep"><span class="t">Increments &amp; salary history</span><span data-hr="increments"></span></div>
              <div class="pg-rep"><span class="t">Office staff register</span><span data-hr="staff"></span></div>
              <div class="pg-rep"><span class="t">Office document tracker<small>Expiring within</small></span><input type="number" id="pgrep-doc-within" value="90" style="width:70px;"> days <span data-hr="documents"></span></div>
            </div>
            <div class="card" id="pgrep-people">
              <h2>People</h2>
              <p style="font-size:12px; color:#888; margin:0 0 8px;">Everyone on the books - labour, office, local, household.</p>
              <div class="pg-rep"><span class="t">Register</span><span class="pg-seg" id="pgrep-reg-group"><button class="on" data-v="labour">Labour</button><button data-v="office">Office</button><button data-v="local">Local</button><button data-v="household">Household</button><button data-v="left">Left</button></span><span data-people="register"></span></div>
              <div class="pg-rep"><span class="t">Documents due<small>Across every register</small></span><span class="pg-seg" id="pgrep-due-days"><button data-v="30">30 d</button><button class="on" data-v="90">90 d</button><button data-v="180">180 d</button></span><span data-people="documents-due"></span></div>
              <div class="pg-rep"><span class="t">Leave balances</span><span class="pg-seg" id="pgrep-lv-group"><button class="on" data-v="labour">Labour</button><button data-v="office">Office</button><button data-v="local">Local</button><button data-v="household">Household</button></span><span data-people="leave"></span></div>
            </div>
            <div class="card" id="pgrep-store">
              <h2>Store &amp; purchasing</h2>
              <p style="font-size:12px; color:#888; margin:0 0 8px;">Stock, movements, requests and orders.</p>
              <div class="pg-rep"><span class="t">Store reports<small>Stock, purchases, usage, requests</small></span><button class="btn btn-dark" onclick="dashStoreGo('reports')">Open</button></div>
              <div class="pg-rep"><span class="t">LPO register<small>Every purchase order raised</small></span><button class="btn btn-dark" onclick="switchScreen('lporegister')">Open</button></div>
              <div class="pg-rep"><span class="t">Order follow-up<small>What is coming, from whom</small></span><button class="btn btn-dark" onclick="switchScreen('followup')">Open</button></div>
            </div>
        </div>
"""

ROLES_CARD = """
          <div class="card" id="pg-roles-card">
            <h2>Roles &amp; access</h2>
            <p style="font-size:12px; color:#888; margin:0 0 10px;">Named sets of rights - Assistant Accountant, Store Keeper, Purchase Manager - and the logins that follow them. Give a login a role and it gets exactly those screens.</p>
            <button class="btn btn-primary" onclick="location.href='access.html'">Open roles &amp; access</button>
          </div>
"""

SCRIPT = """
<script>
// ---- temporary page: %(key)s ---------------------------------------------
// Which screens live on this page, which page every other screen lives
// on, and the tabs. The app's own switchScreen does the work; this only
// decides whether the screen is here or on another page.
const PAGE = %(page_json)s;
const PAGE_OF = %(page_of_json)s;
const RIGHT_OF = %(right_of_json)s;
SCREEN_TITLES.pgreports = "Reports";
const PAGE_FILE = %(file_json)s;
function pgUrl(screen) { const k = PAGE_OF[screen] || "dashboard"; return (PAGE_FILE[k] || k) + ".html"; }
function pgHas(r) { return CURRENT_ROLE === "admin" || (Array.isArray(r) ? r.some(x => MY_SCREENS.includes(x)) : MY_SCREENS.includes(r)); }
function pgAllowed(screen) { return pgHas(RIGHT_OF[screen] || screen); }
function pgTabOk(t) { return pgHas(t.right); }
function pgTabFor(id) { return PAGE.tabs.find(t => t.id === id) || PAGE.tabs.find(t => t.screen === id); }
let PG_TAB = null;

const _switchScreen = switchScreen;
switchScreen = function (name) {
  if (!PAGE.screens.includes(name)) { location.href = pgUrl(name) + "#" + name; return; }
  _switchScreen(name);
  const early = document.getElementById("pg-early"); if (early) early.remove();
  if (!PG_TAB || PG_TAB.screen !== name) PG_TAB = PAGE.tabs.find(t => t.screen === name) || null;
  pgApplyTab(); pgRenderTabs();
  if (name === "pgreports") pgHubLoad();
};
function pgTab(id) {
  const t = pgTabFor(id); if (!t) return;
  const same = PG_TAB && PG_TAB.screen === t.screen && document.getElementById("screen-" + t.screen).classList.contains("active");
  PG_TAB = t;
  if (t.id !== t.screen) location.hash = t.id;
  // Two tabs of one screen: only the part shown changes, nothing reloads.
  if (same) { pgApplyTab(); pgRenderTabs(); return; }
  switchScreen(t.screen);
}
// A sign-in that does not resume shows the sign-in box after all.
if (sessionStorage.getItem("infinia_token"))
  apiCall("/auth/me").catch(() => { const e = document.getElementById("pg-early"); if (e) e.remove(); });
// A tab that shows part of a screen hides the rest of it.
function pgApplyTab() {
  const t = PG_TAB; if (!t) return;
  const screen = document.getElementById("screen-" + t.screen); if (!screen) return;
  const parts = [...screen.children].filter(el => !el.classList.contains("status-msg"));
  if (!t.show.length) { parts.forEach(el => el.classList.remove("pg-hide")); return; }
  const keep = new Set(t.show.flatMap(sel => [...screen.querySelectorAll(sel)]));
  parts.forEach(el => el.classList.toggle("pg-hide", !keep.has(el) && ![...keep].some(k => el.contains(k))));
}
const _doLogout = doLogout;
doLogout = function () { try { sessionStorage.removeItem("infinia_user"); } catch (e) {} return _doLogout.apply(this, arguments); };
const _dashStoreGo = dashStoreGo;
dashStoreGo = function (panel) {
  if (!PAGE.screens.includes("store")) { location.href = "store.html#store:" + panel; return; }
  _dashStoreGo(panel);
};
// Where to land: the tab in the address, else the first tab this login
// may open. A login with nothing on this page goes to the first page
// it has.
firstScreenFor = function () {
  const [want, extra] = (location.hash || "").slice(1).split(":");
  const t = want ? pgTabFor(want) : null;
  if (t && pgTabOk(t)) {
    PG_TAB = t;
    if (t.screen === "store" && extra) setTimeout(() => storeGo(extra), 120);
    return t.screen;
  }
  for (const tb of PAGE.tabs) if (pgTabOk(tb)) { PG_TAB = tb; return tb.screen; }
  const pages = %(order_json)s;
  for (const pg of pages) {
    if (pg === PAGE.key) continue;
    if ((PAGE.pages[pg] || []).some(s => pgAllowed(s))) { location.href = (PAGE_FILE[pg] || pg) + ".html"; return PAGE.tabs[0].screen; }
  }
  return PAGE.tabs[0].screen;
};
function pgRenderTabs() {
  const bar = document.getElementById("pg-tabs");
  const tabs = PAGE.tabs.filter(pgTabOk);
  bar.innerHTML = tabs.length > 1 ? tabs.map(t =>
    `<span class="pg-tab ${PG_TAB && PG_TAB.id === t.id ? "active" : ""}" data-tab="${t.id}" onclick="pgTab('${t.id}')">${t.label}</span>`).join("") : "";
  const shown = [];
  document.querySelectorAll(".pg-side .pg-item[data-page]").forEach(el => {
    const ok = (PAGE.pages[el.dataset.page] || []).some(s => pgAllowed(s));
    el.style.display = ok ? "block" : "none";
    el.style.visibility = "visible";
    if (ok) shown.push(el.dataset.page);
  });
  // Remembered per login, for the next page's first frame.
  try {
    sessionStorage.setItem("infinia_user", CURRENT_USERNAME || "");
    localStorage.setItem("infinia_menu", JSON.stringify({ user: CURRENT_USERNAME || "", pages: shown }));
  } catch (e) {}
  if (!tabs.length) {
    document.querySelectorAll(".screen").forEach(el => el.classList.remove("active"));
    document.getElementById("screen-title").textContent = "Not available to this login";
  }
}
const _applyScreenPermissions = applyScreenPermissions;
applyScreenPermissions = async function () { await _applyScreenPermissions(); pgRenderTabs(); };
window.addEventListener("hashchange", () => {
  const want = (location.hash || "").slice(1).split(":")[0];
  const t = want ? pgTabFor(want) : null;
  if (t && !(PG_TAB && PG_TAB.id === t.id)) { PG_TAB = t; switchScreen(t.screen); }
});

// ---- Only the work this page needs at start-up --------------------------
// The app loads today's attendance grid, the dashboard calendar and the
// live-card list before showing anything. On a page without those
// screens that is a wait for nothing, so they are skipped here.
const pgOn = s => PAGE.screens.includes(s);
if (!pgOn("attendance")) { loadDate = async () => {}; }
if (!pgOn("dashboard")) { loadDashboardCalendar = () => {}; startDashboardClock = () => {}; }
if (!pgOn("livecard")) { renderLiveCardWorkerList = () => {}; }
if (!pgOn("masterdata") && !pgOn("settings")) { renderMasterDataLists = () => {}; }

// ---- The reports hub -------------------------------------------------------
function pgBtns(preview, dl) {
  return `<button class="btn btn-dark" onclick="${preview}">Preview</button><button class="btn btn-gray" onclick="${dl.replace("FMT", "pdf")}">PDF</button><button class="btn btn-gray" onclick="${dl.replace("FMT", "excel")}">Excel</button>`;
}
function pgSeg(id) { const b = document.querySelector("#" + id + " button.on"); return b ? b.dataset.v : ""; }
document.querySelectorAll("#screen-pgreports .pg-seg").forEach(seg => seg.querySelectorAll("button").forEach(b =>
  b.onclick = () => seg.querySelectorAll("button").forEach(x => x.classList.toggle("on", x === b))));
async function pgOpen(url, format) {
  const t = await hrToken();
  const sep = url.includes("?") ? "&" : "?";
  if (format === "view") { const [path, q] = url.split("?"); window.open(`${API}${path}/view?${q ? q + "&" : ""}token=${t}`, "_blank"); }
  else window.open(`${API}${url}${sep}token=${t}&format=${format}`, "_blank");
}
function pgHrUrl(which) {
  const m = v => encodeURIComponent(hrCycleName(v));
  if (which === "leave") return `/export/payroll/leave?month_year=${m(document.getElementById("pgrep-leave-month").value)}`;
  if (which === "items") return `/export/payroll/items?month_year=${m(document.getElementById("pgrep-items-month").value)}`;
  if (which === "increments") return `/export/payroll/increments?emp_no=`;
  if (which === "documents") return `/export/payroll/documents?within=${document.getElementById("pgrep-doc-within").value || 90}`;
  return `/export/payroll/${which}`;
}
function pgPeopleUrl(kind) {
  if (kind === "register") return `/export/people/register?group=${pgSeg("pgrep-reg-group")}`;
  if (kind === "documents-due") return `/export/people/documents-due?days=${pgSeg("pgrep-due-days")}&group=`;
  return `/export/people/leave?group=${pgSeg("pgrep-lv-group")}`;
}
let PG_HUB_DONE = false;
async function pgHubLoad() {
  refreshDownloadToken();
  if (PG_HUB_DONE) return;
  PG_HUB_DONE = true;
  const ym = new Date().toISOString().slice(0, 7);
  document.getElementById("pgrep-leave-month").value = ym; document.getElementById("pgrep-items-month").value = ym;
  document.querySelectorAll("#pgrep-office [data-hr]").forEach(el => { const w = el.dataset.hr;
    el.innerHTML = pgBtns(`pgOpen(pgHrUrl('${w}'),'view')`, `pgOpen(pgHrUrl('${w}'),'FMT')`); });
  document.querySelectorAll("#pgrep-people [data-people]").forEach(el => { const w = el.dataset.people;
    el.innerHTML = pgBtns(`pgOpen(pgPeopleUrl('${w}'),'view')`, `pgOpen(pgPeopleUrl('${w}'),'FMT')`); });
  if (pgHas("hrpayroll")) {
    try {
      const runs = (await apiCall("/employees/payroll/runs")).rows || [];
      const sel = document.getElementById("pgrep-run");
      sel.innerHTML = runs.map(r => `<option value="${r.id}">${escapeHtml(r.company)} - ${escapeHtml(r.month_year)} (${r.status === "approved" ? "approved" : "draft"})</option>`).join("") || "<option value=''>No cycles yet</option>";
      const none = '<span class="muted" style="font-size:12px;">No cycles yet</span>';
      document.getElementById("pgrep-run-btns").innerHTML = !runs.length ? none : pgBtns(`pgOpen('/export/payroll/statement?run_id='+document.getElementById('pgrep-run').value,'view')`, `pgOpen('/export/payroll/statement?run_id='+document.getElementById('pgrep-run').value,'FMT')`);
      const months = [...new Set(runs.map(r => r.month_year))];
      document.getElementById("pgrep-month").innerHTML = months.map(m => `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`).join("") || "<option value=''>No cycles yet</option>";
      document.getElementById("pgrep-cons-btns").innerHTML = !runs.length ? none : pgBtns(`pgOpen('/export/payroll/consolidated?month_year='+encodeURIComponent(document.getElementById('pgrep-month').value),'view')`, `pgOpen('/export/payroll/consolidated?month_year='+encodeURIComponent(document.getElementById('pgrep-month').value),'FMT')`);
    } catch (e) { showStatus("pgrep-status", "err", "Could not list the office cycles: " + errText(e)); }
  }
}
</script>
"""


def build():
    src = open(SRC, encoding="utf-8").read()
    m = re.search(r'<div class="sidebar">\n(\s*<div class="brand">.*?</div>)\n', src)
    if not m:
        raise SystemExit("app.html: sidebar not found where expected")
    brand = m.group(1).strip()
    src = src.replace('<div class="sidebar">\n', '<div class="sidebar" id="legacy-sidebar">\n', 1)
    src = src.replace("</head>", CSS + "</head>", 1)
    src = src.replace('<div class="content">\n', '<div class="pg-tabs" id="pg-tabs"></div>\n      <div class="content">\n', 1)

    # Settings, in parts: the cards get ids so a tab can show one part.
    src = src.replace('<div class="card">\n            <h2>Change Your Password</h2>',
                      '<div class="card" id="pg-password-card">\n            <h2>Change Your Password</h2>', 1)
    src = src.replace('<div class="card">\n            <h2>Backup</h2>',
                      '<div class="card" id="pg-backup-card">\n            <h2>Backup</h2>', 1)
    # Sites and engineers move from Master Data to Settings.
    start = src.index('          <div style="display:flex; gap:14px;">\n            <div class="card" style="flex:1;">\n              <h2>Add Site</h2>')
    end = src.index('\n        </div>\n', start)
    block = src[start:end]
    src = src[:start] + src[end + 1:]
    block = block.replace('<div style="display:flex; gap:14px;">', '<div style="display:flex; gap:14px;" id="pg-sites-block">', 1)
    s_start = src.index('id="screen-settings"')
    s_end = src.index('id="screen-activity"')
    close = src.rindex('\n        </div>\n', s_start, s_end)
    src = src[:close] + "\n" + block + "\n" + ROLES_CARD + src[close:]
    # The reports hub, a screen of its own.
    src = src.replace('        <div class="screen" id="screen-activity">', HUB_HTML + '        <div class="screen" id="screen-activity">', 1)

    page_of, pages_screens, right_of = {}, {}, {}
    for key, (_, tabs) in PAGES.items():
        pages_screens[key] = sorted({t["screen"] for t in tabs})
        for t in tabs:
            page_of[t["screen"]] = key
            rights = t["right"] if isinstance(t["right"], list) else [t["right"]]
            have = right_of.get(t["screen"], [])
            right_of[t["screen"]] = sorted(set((have if isinstance(have, list) else [have]) + rights))
    for screen, key in EXTRA.items():
        page_of[screen] = key
        right_of[screen] = key
    for key, (_, right) in STANDALONE.items():
        pages_screens[key] = right if isinstance(right, list) else [key]
        for r in (right if isinstance(right, list) else [right]):
            right_of[r] = r

    for key, (title, tabs) in PAGES.items():
        side = ['<div class="pg-side">', brand]
        for pg in ORDER:
            label = LABELS.get(pg) or STANDALONE[pg][0]
            side.append(f'<div class="pg-item {"active" if pg == key else ""}" data-page="{pg}" onclick="location.href=\'{fname(pg)}\'">{html.escape(label)}</div>')
        side.append('<div class="pg-group">TEMPORARY BUILD</div>')
        side.append('<div class="pg-small" onclick="location.href=\'/app.html\'">&larr; Back to the classic app</div>')
        side.append("</div>")
        page = src.replace('<div class="sidebar" id="legacy-sidebar">', "\n".join(side) + '\n    <div class="sidebar" id="legacy-sidebar">', 1)
        page = page.replace("<title>", f"<title>{html.escape(title)} - ", 1)
        screens = sorted({t["screen"] for t in tabs} | {s for s, k in EXTRA.items() if k == key})
        cfg = {"key": key, "title": title, "screens": screens, "tabs": tabs, "pages": pages_screens}
        tabmap = {t["id"]: t["screen"] for t in tabs}
        early = EARLY % {"first": tabs[0]["id"], "tabmap": json.dumps(tabmap)}
        page = page.replace("</head>", early + "</head>", 1)
        script = SCRIPT % {"key": key, "page_json": json.dumps(cfg), "page_of_json": json.dumps(page_of),
                           "right_of_json": json.dumps(right_of), "order_json": json.dumps(ORDER),
                           "file_json": json.dumps(FILE)}
        page = page.replace("</body>", script + "</body>", 1)
        with open(os.path.join(OUT, fname(key)), "w", encoding="utf-8") as f:
            f.write(page)
        print(f"wrote temporary/Infinia/{fname(key)}  ({len(page) // 1024} KB)")


if __name__ == "__main__":
    build()

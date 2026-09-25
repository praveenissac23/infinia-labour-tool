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


def tab(id, screen, label, right=None, show=None, subs=None):
    return {"id": id, "screen": screen, "label": label, "right": right or screen, "show": show or [], "subs": subs or []}


def sub(id, label, screen=None, right=None, go=None, people=None, opts=None):
    """A second-level tab: the working screen itself. screen = the app
    screen to show, go = what to run once it is up (its own tab, its
    report panel), people = a People list drawn on the hub with its
    options (opts: group, days)."""
    return {"id": id, "label": label, "screen": screen or ("pgreports" if people else ""), "right": right or screen or "reports",
            "go": go or "", "people": people or "", "opts": opts or ""}


PEOPLE_RIGHTS = ["people_labour", "people_office", "people_local", "people_household"]
STORE_RIGHTS = ["store", "approvals", "requests"]


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
        tab("labour", "pgreports", "Labour", ["reports", "combine", "errorcheck", "livecard"], subs=[
            sub("builder", "Cycle report builder", screen="reports"),
            sub("cards", "Salary cards", screen="combine"),
            sub("check", "Check before you pay", screen="errorcheck"),
            sub("live", "Live card", screen="livecard")]),
        tab("office", "hrpayroll", "Office payroll", "hrpayroll", subs=[
            sub("cycle", "Salary cycle & statements", screen="hrpayroll", go="hrTab('payroll')"),
            sub("leave", "Absence", screen="hrpayroll", go="hrTab('leave')"),
            sub("items", "Additions & deductions", screen="hrpayroll", go="hrTab('items')"),
            sub("loans", "Loans", screen="hrpayroll", go="hrTab('loans')"),
            sub("staff", "Staff register", screen="hrpayroll", go="hrTab('staff')"),
            sub("increments", "Increments", screen="hrpayroll", go="hrTab('increments')"),
            sub("docs", "Documents", screen="hrpayroll", go="hrTab('docs')"),
            sub("gratuity", "Gratuity", screen="hrpayroll", go="hrTab('gratuity')")]),
        tab("people", "pgreports", "Staff", PEOPLE_RIGHTS, subs=[
            sub("register", "Register", right=PEOPLE_RIGHTS, people="register", opts="group"),
            sub("due", "Documents due", right=PEOPLE_RIGHTS, people="documents-due", opts="days")]),
        tab("storerep", "store", "Store & purchasing", STORE_RIGHTS, subs=[
            sub("stock", "Current stock", screen="store", right=STORE_RIGHTS, go="pgStoreReport('stock')"),
            sub("by_site", "At sites", screen="store", right=STORE_RIGHTS, go="pgStoreReport('by_site')"),
            sub("usage", "Consumption", screen="store", right=STORE_RIGHTS, go="pgStoreReport('usage')"),
            sub("assets", "Assets", screen="store", right=STORE_RIGHTS, go="pgStoreReport('assets')"),
            sub("issues", "Issue & return register", screen="store", right=STORE_RIGHTS, go="pgStoreReport('issues')"),
            sub("lost", "Lost / damaged", screen="store", right=STORE_RIGHTS, go="pgStoreReport('lost')"),
            sub("hired", "On rent now", screen="store", right=STORE_RIGHTS, go="pgStoreReport('hired')"),
            sub("mr_open", "Open requests", screen="store", right=STORE_RIGHTS, go="pgStoreReport('mr_open')"),
            sub("mr_history", "Request history", screen="store", right=STORE_RIGHTS, go="pgStoreReport('mr_history')"),
            sub("suppliers", "Suppliers", screen="suppliers", right="approvals"),
            sub("lpo", "LPO register", screen="lporegister", right="approvals"),
            sub("followup", "Order follow-up", screen="followup", right="requests")])]),
    "settings": ("Settings", [
        tab("general", "settings", "General", "settings",
            ["#pg-password-card", "#company-card", "#signature-card", "#store-reset-card"]),
        tab("companies", "settings", "Companies", "settings", ["#companies-card"]),
        tab("sites", "settings", "Sites & engineers", "settings", ["#pg-sites-block"]),
        tab("logins", "settings", "Logins", "settings", ["#user-mgmt-card", "#pg-roles-card"]),
        tab("backup", "settings", "Backup", "settings", ["#pg-backup-card"]),
        tab("activity", "activity", "Activity monitor", "activity"),
        tab("access", "settings", "Access", "__admin__", ["#pg-roles-card"])]),
}
# Screens without a tab of their own, reached from inside another.
EXTRA = {"monthly": "reports"}
ORDER = ["dashboard", "attendance", "people", "payroll", "store", "reports", "settings"]
# The file each page is served as. nginx sends any address containing
# "reports" to the API (its rule is not anchored), so that page cannot be
# called reports.html.
FILE = {"reports": "reporting"}
def fname(key): return FILE.get(key, key) + ".html"
STANDALONE = {"people": ("Staff", ["people_labour", "people_office", "people_local", "people_household"]),
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
  /* The reports hub: tabs inside tabs, the preview underneath */
  .pg-sub { display: flex; gap: 4px; flex-wrap: wrap; padding: 8px 26px 0; background: white; border-bottom: 1px solid #E7E1DA; }
  .pg-sub:empty { display: none; }
  .pg-subtab { padding: 6px 12px; margin-bottom: 8px; font-size: 12.5px; font-weight: 600; color: #6A5C55; background: #F7F3EE; border: 1px solid #E4DCD2; border-radius: 6px; cursor: pointer; white-space: nowrap; }
  .pg-subtab:hover { background: #F1EAE3; }
  .pg-subtab.active { background: #2C2C2C; color: white; border-color: #2C2C2C; }
  /* Under a sub-tab the screen's own tab row and report picker are the sub-tabs, so they go. */
  body.pg-subview #screen-hrpayroll .hr-tabs { display: none; }
  body.pg-subview #store-reports > button, body.pg-subview #store-reports > .card:first-of-type { display: none; }
  body.pg-subview #store-report-result { margin-top: 0; }
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
    var full = (location.hash || "").slice(1);
    var want = full.split(":")[0] || "%(first)s";
    var tabs = %(tabmap)s;
    var screen = tabs[full] || tabs[want] || want;
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
    // The tab strip as this login last saw it on this page, drawn before
    // the app's script runs, so the strip never appears empty and fills.
    var tabs = null;
    try { tabs = JSON.parse(localStorage.getItem("infinia_tabs:%(key)s") || "null"); } catch (e) {}
    if (tabs && tabs.user === (sessionStorage.getItem("infinia_user") || "") && tabs.tabs.length > 1) {
      document.addEventListener("DOMContentLoaded", function () {
        var bar = document.getElementById("pg-tabs");
        if (bar && !bar.children.length) bar.innerHTML = tabs.tabs.map(function (t) {
          return '<span class="pg-tab ' + (t.id === want ? "active" : "") + '" data-tab="' + t.id + '">' + t.label + "</span>";
        }).join("");
      });
    }
  } catch (e) {}
})();
</script>
"""

HUB_HTML = """
        <!-- ============ PEOPLE LISTS (reports page, temporary pages) ============ -->
        <div class="screen" id="screen-pgreports">
          <div class="status-msg" id="pgrep-status"></div>
          <div class="card">
            <div class="form-row" style="gap:10px; align-items:center; flex-wrap:wrap;">
              <h2 id="pg-people-title" style="margin:0 12px 0 0;"></h2>
              <span id="pg-people-opts"></span>
              <div class="hr-cb-spacer"></div>
              <button class="btn btn-dark" onclick="pgRepOpen()">Preview</button>
              <button class="btn btn-gray" onclick="pgRepDownload('pdf')">Export to PDF</button>
              <button class="btn btn-gray" onclick="pgRepDownload('excel')">Export to Excel</button>
              <span id="pg-people-count" style="font-size:12px; color:#888;"></span>
            </div>
            <p id="pg-people-sub" style="font-size:12px; color:#888; margin:6px 0 0;"></p>
            <div class="grid-wrap" style="max-height:64vh; margin-top:10px;">
              <table class="hr-grid"><thead id="pg-people-head"></thead><tbody id="pg-people-body"></tbody></table>
            </div>
          </div>
        </div>
"""

ROLES_CARD = """
          <div class="card" id="pg-roles-card">
            <h2>Roles &amp; access</h2>
            <p style="font-size:12px; color:#888; margin:0 0 10px;">Named sets of rights - Assistant Accountant, Store Keeper, Purchase Manager - and the logins that follow them. Give a login a role and it gets exactly those screens.</p>
            <button class="btn btn-primary" onclick="location.href='access.html'">Open roles &amp; access</button>
            <p style="font-size:12px; color:#888; margin:10px 0 0;">Admin only - roles cannot carry this tab.</p>
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
SCREEN_TITLES.lporegister = SCREEN_TITLES.lporegister || "LPO Register";
SCREEN_TITLES.followup = SCREEN_TITLES.followup || "Order Follow-up";
SCREEN_TITLES.suppliers = SCREEN_TITLES.suppliers || "Suppliers";
const PAGE_FILE = %(file_json)s;
function pgUrl(screen) { const k = PAGE_OF[screen] || "dashboard"; return (PAGE_FILE[k] || k) + ".html"; }
function pgHas(r) { return CURRENT_ROLE === "admin" || (Array.isArray(r) ? r.some(x => MY_SCREENS.includes(x)) : (r !== "__admin__" && MY_SCREENS.includes(r))); }
function pgAllowed(screen) { return pgHas(RIGHT_OF[screen] || screen); }
function pgTabOk(t) { return pgHas(t.right); }
function pgTabFor(id) { return PAGE.tabs.find(t => t.id === id) || PAGE.tabs.find(t => t.screen === id); }
let PG_TAB = null, PG_SUB = null;

const _switchScreen = switchScreen;
switchScreen = function (name) {
  if (!PAGE.screens.includes(name)) { location.href = pgUrl(name) + "#" + name; return; }
  // A login without the right is on its way to another page; nothing
  // here should start loading (and being refused) in the meantime.
  if (MY_SCREENS.length && !pgAllowed(name)) return;
  _switchScreen(name);
  const early = document.getElementById("pg-early"); if (early) early.remove();
  const inSubs = PG_TAB && PG_TAB.subs.some(sb => sb.screen === name);
  if (!inSubs && (!PG_TAB || PG_TAB.screen !== name))
    PG_TAB = PAGE.tabs.find(t => t.screen === name) || PAGE.tabs.find(t => t.subs.some(sb => sb.screen === name)) || null;
  if (PG_TAB && PG_TAB.subs.length && !(PG_SUB && PG_TAB.subs.includes(PG_SUB) && (PG_SUB.screen || "pgreports") === name))
    PG_SUB = PG_TAB.subs.find(sb => pgHas(sb.right) && (sb.screen || "pgreports") === name) || PG_SUB;
  pgApplyTab(); pgRenderTabs();
  if (name === "pgreports") pgHubLoad();
  else if (PG_SUB && (PG_SUB.screen || "") === name && PG_TAB && PG_TAB.subs.includes(PG_SUB)) pgSubGo();
  else document.body.classList.remove("pg-subview");
};
function pgTab(id) {
  const t = pgTabFor(id); if (!t) return;
  if (t.id === "access" && PAGE.key === "settings") { location.href = "access.html"; return; }
  if (t.subs.length) { PG_TAB = t; const first = t.subs.find(sb => pgHas(sb.right)); if (first) { pgSub(first.id); return; } }
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
    if (t.subs.length) {
      PG_SUB = t.subs.find(sb => sb.id === extra && pgHas(sb.right)) || t.subs.find(sb => pgHas(sb.right)) || null;
      return PG_SUB ? (PG_SUB.screen || "pgreports") : t.screen;
    }
    if (t.screen === "store" && extra) setTimeout(() => storeGo(extra), 120);
    return t.screen;
  }
  for (const tb of PAGE.tabs) if (pgTabOk(tb)) {
    PG_TAB = tb;
    if (tb.subs.length) { PG_SUB = tb.subs.find(sb => pgHas(sb.right)) || null; return PG_SUB ? (PG_SUB.screen || "pgreports") : tb.screen; }
    return tb.screen;
  }
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
  try { localStorage.setItem("infinia_tabs:" + PAGE.key, JSON.stringify({ user: CURRENT_USERNAME || "", tabs: tabs.map(t => ({ id: t.id, label: t.label })) })); } catch (e) {}
  bar.innerHTML = tabs.length > 1 ? tabs.map(t =>
    `<span class="pg-tab ${PG_TAB && PG_TAB.id === t.id ? "active" : ""}" data-tab="${t.id}" onclick="pgTab('${t.id}')">${t.label}</span>`).join("") : "";
  const sub = document.getElementById("pg-sub");
  const subs = PG_TAB ? PG_TAB.subs.filter(sb => pgHas(sb.right)) : [];
  sub.innerHTML = subs.map(sb =>
    `<span class="pg-subtab ${PG_SUB && PG_SUB.id === sb.id ? "active" : ""}" data-sub="${sb.id}" onclick="pgSub('${sb.id}')">${sb.label}</span>`).join("");
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
  const [want, extra] = (location.hash || "").slice(1).split(":");
  const t = want ? pgTabFor(want) : null;
  if (!t) return;
  if (t.subs.length) { const sb = t.subs.find(x => x.id === extra); if (sb && !(PG_SUB && PG_SUB.id === sb.id)) { PG_TAB = t; pgSub(sb.id); } return; }
  if (!(PG_TAB && PG_TAB.id === t.id)) { PG_TAB = t; switchScreen(t.screen); }
});

// ---- Only the work this page needs at start-up --------------------------
// The app loads today's attendance grid, the dashboard calendar and the
// live-card list before showing anything. On a page without those
// screens that is a wait for nothing, so they are skipped here.
const pgOn = s => PAGE.screens.includes(s);
if (!pgOn("attendance")) { loadDate = async () => {}; }
if (!pgOn("dashboard")) { startDashboardClock = () => {}; }
if (!pgOn("dashboard") && !pgOn("attendance")) { loadDashboardCalendar = () => {}; }
if (!pgOn("livecard")) { renderLiveCardWorkerList = () => {}; }
if (!pgOn("masterdata") && !pgOn("settings")) { renderMasterDataLists = () => {}; }

// ---- The reports page: tabs inside tabs, the working screen underneath ------
function pgSub(id) {
  const t = PG_TAB; if (!t) return;
  const sb = t.subs.find(x => x.id === id); if (!sb || !pgHas(sb.right)) return;
  PG_SUB = sb;
  location.hash = t.id + ":" + sb.id;
  const screen = sb.screen || "pgreports";
  const active = document.getElementById("screen-" + screen);
  if (!(active && active.classList.contains("active"))) { switchScreen(screen); return; }
  pgRenderTabs();
  pgSubGo();
}
// What a sub-tab does once its screen is up: its own tab, its report.
function pgSubGo() {
  const sb = PG_SUB; if (!sb) return;
  document.body.classList.toggle("pg-subview", !!(PG_TAB && PG_TAB.subs.includes(sb) && (sb.go || sb.people)));
  if (sb.people) { pgPeopleShow(); return; }
  if (sb.go) setTimeout(() => { try { new Function(sb.go)(); } catch (e) { console.error(e); } }, 30);
}
function pgStoreReport(kind) {
  STORE_REPORT_WANT = kind;
  storeGo("reports");
}
function pgSeg(id) { const b = document.querySelector("#" + id + " button.on"); return b ? b.dataset.v : ""; }
function pgSegHtml(id, choices, on) {
  return `<span class="pg-seg" id="${id}">` + choices.map(([v, l]) => `<button data-v="${v}" class="${v === on ? "on" : ""}" onclick="pgSegPick(this)">${l}</button>`).join("") + `</span>`;
}
function pgSegPick(b) { b.parentNode.querySelectorAll("button").forEach(x => x.classList.toggle("on", x === b)); pgPeopleShow(); }
function pgHubLoad() { refreshDownloadToken(); pgPeopleShow(); }

// ---- People lists on the reports page ----------------------------------------
const PG_GROUPS = [["labour", "Labour"], ["office", "Office"], ["local", "Local"], ["household", "Household"]];
const pgCanGroup = g => CURRENT_ROLE === "admin" || MY_SCREENS.includes("people_" + g[0]);
let PG_PEOPLE_DRAWN = "";
function pgPeopleOpts(sb) {
  if (sb.opts === "days") return pgSegHtml("pg-opt-days", [["30", "30 days"], ["90", "90 days"], ["180", "180 days"]], "90");
  const g = PG_GROUPS.filter(pgCanGroup); if (sb.people === "register") g.push(["left", "Left"]);
  return g.length ? pgSegHtml("pg-opt-group", g, g[0][0]) : "";
}
function pgPeopleQuery(sb) {
  if (sb.opts === "days") return `days=${pgSeg("pg-opt-days")}&group=`;
  return `group=${pgSeg("pg-opt-group")}`;
}
const PG_COLS = {
  register: [["emp_no", "Code"], ["name", "Name", "txt"], ["designation", "Designation", "txt"], ["company", "Company", "txt"], ["nationality", "Nationality", "txt"],
             ["joined_on", "Joined"], ["service", "Service"], ["basic", "Basic", "num"], ["allowance", "Allowance", "num"], ["gross", "Gross", "num"],
             ["pay_route", "Paid by"], ["soonest_expiry", "Next expiry"], ["leave_balance", "Leave bal.", "num"]],
  "documents-due": [["emp_no", "Code"], ["name", "Name", "txt"], ["group_label", "Register", "txt"], ["kind_label", "Document", "txt"], ["number", "Number"],
             ["issued_on", "Issued"], ["expires_on", "Expires"], ["days_left", "Days left", "num"], ["status", "Standing"]],
  leave: [["emp_no", "Code"], ["name", "Name", "txt"], ["designation", "Designation", "txt"], ["company", "Company", "txt"], ["joined_on", "Joined"], ["service", "Service"],
          ["rule", "Entitlement", "txt"], ["accrued", "Accrued", "num"], ["taken", "Taken", "num"], ["balance", "Balance", "num"], ["next_due", "Next due"], ["due_state", "Standing"]],
};
const PG_PATHS = { register: "/employees/people", "documents-due": "/employees/people/documents-due", leave: "/employees/people/leave-balances" };
async function pgPeopleShow() {
  const sb = PG_SUB; if (!sb || !sb.people) return;
  document.getElementById("pg-people-title").textContent = sb.label;
  if (PG_PEOPLE_DRAWN !== sb.id) { document.getElementById("pg-people-opts").innerHTML = pgPeopleOpts(sb); PG_PEOPLE_DRAWN = sb.id; }
  const cols = PG_COLS[sb.people];
  const head = document.getElementById("pg-people-head"), body = document.getElementById("pg-people-body");
  head.innerHTML = "<tr>" + cols.map(c => `<th class="${c[2] || ""}">${c[1]}</th>`).join("") + "</tr>";
  body.innerHTML = `<tr><td colspan="${cols.length}" class="empty-note">Loading…</td></tr>`;
  const q = pgPeopleQuery(sb);
  let d;
  try { d = await apiCall(`${PG_PATHS[sb.people]}?${q}`); }
  catch (e) { body.innerHTML = `<tr><td colspan="${cols.length}" class="empty-note">Could not load: ${escapeHtml(errText(e))}</td></tr>`; return; }
  const rows = d.rows || [];
  document.getElementById("pg-people-count").textContent = rows.length ? `${rows.length} row(s)` : "";
  document.getElementById("pg-people-sub").textContent =
    sb.people === "leave" && d.rule ? `Entitlement: ${d.rule[0]} days every ${d.rule[1]} months, as at ${isoLocal(new Date())}` :
    sb.people === "documents-due" ? `Everything expiring within ${d.days} days, soonest first` : `As at ${isoLocal(new Date())}`;
  const cell = (r, c) => { const v = r[c[0]]; if (v === null || v === undefined || v === "") return "-";
    return c[2] === "num" && typeof v === "number" ? num(v) : escapeHtml(String(v)); };
  body.innerHTML = rows.length
    ? rows.map(r => "<tr>" + cols.map(c => `<td class="${c[2] || ""}">${cell(r, c)}</td>`).join("") + "</tr>").join("")
    : `<tr><td colspan="${cols.length}" class="empty-note">Nothing to show.</td></tr>`;
}
async function pgRepUrl(format) {
  const sb = PG_SUB; if (!sb || !sb.people) return null;
  const t = await hrToken(); const path = `/export/people/${sb.people}`; const q = pgPeopleQuery(sb);
  return format === "view" ? `${API}${path}/view?${q}&token=${t}` : `${API}${path}?${q}&token=${t}&format=${format}`;
}
async function pgRepOpen() { const u = await pgRepUrl("view"); if (u) window.open(u, "_blank"); }
async function pgRepDownload(fmt) { const u = await pgRepUrl(fmt); if (u) window.open(u, "_blank"); }
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
    src = src.replace('<div class="content">\n', '<div class="pg-tabs" id="pg-tabs"></div>\n      <div class="pg-sub" id="pg-sub"></div>\n      <div class="content">\n', 1)

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
            for sb in t["subs"]:
                if sb["screen"]:
                    page_of.setdefault(sb["screen"], key)
                    right_of.setdefault(sb["screen"], sb["right"])
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
        screens = sorted({t["screen"] for t in tabs} | {sb["screen"] for t in tabs for sb in t["subs"] if sb["screen"]}
                         | {s for s, k in EXTRA.items() if k == key})
        cfg = {"key": key, "title": title, "screens": screens, "tabs": tabs, "pages": pages_screens}
        tabmap = {t["id"]: (next((sb["screen"] or "pgreports" for sb in t["subs"]), t["screen"]) if t["subs"] else t["screen"]) for t in tabs}
        for t in tabs:
            for sb in t["subs"]:
                tabmap[t["id"] + ":" + sb["id"]] = sb["screen"] or "pgreports"
        early = EARLY % {"first": tabs[0]["id"], "tabmap": json.dumps(tabmap), "key": key}
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

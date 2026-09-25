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


def sub(id, label, screen=None, right=None, report=None, opts=None):
    """A second-level tab. Either a screen of the app, or a report whose
    preview loads underneath the strip (report = export path, opts = the
    inputs it takes: run, month, cycle, within, group, days, dates)."""
    return {"id": id, "label": label, "screen": screen or "", "right": right or screen or "reports",
            "report": report or "", "opts": opts or ""}


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
        tab("office", "pgreports", "Office payroll", "hrpayroll", subs=[
            sub("statement", "Salary statement", right="hrpayroll", report="/export/payroll/statement", opts="run"),
            sub("consolidated", "Consolidated statement", right="hrpayroll", report="/export/payroll/consolidated", opts="month"),
            sub("leave", "Absence register", right="hrpayroll", report="/export/payroll/leave", opts="cycle"),
            sub("items", "Additions & deductions", right="hrpayroll", report="/export/payroll/items", opts="cycle"),
            sub("loans", "Loans register", right="hrpayroll", report="/export/payroll/loans"),
            sub("increments", "Increments & salary history", right="hrpayroll", report="/export/payroll/increments"),
            sub("staff", "Office staff register", right="hrpayroll", report="/export/payroll/staff"),
            sub("gratuity", "Gratuity", right="hrpayroll", report="/export/payroll/gratuity"),
            sub("documents", "Office document tracker", right="hrpayroll", report="/export/payroll/documents", opts="within")]),
        tab("people", "pgreports", "People", PEOPLE_RIGHTS, subs=[
            sub("register", "Register", right=PEOPLE_RIGHTS, report="/export/people/register", opts="group"),
            sub("due", "Documents due", right=PEOPLE_RIGHTS, report="/export/people/documents-due", opts="days"),
            sub("balances", "Leave balances", right=PEOPLE_RIGHTS, report="/export/people/leave", opts="group")]),
        tab("storerep", "pgreports", "Store & purchasing", STORE_RIGHTS, subs=[
            sub("stock", "Current stock", right=STORE_RIGHTS, report="/export/store/report?kind=stock"),
            sub("by_site", "At sites", right=STORE_RIGHTS, report="/export/store/report?kind=by_site"),
            sub("usage", "Consumption", right=STORE_RIGHTS, report="/export/store/report?kind=usage", opts="dates"),
            sub("assets", "Assets", right=STORE_RIGHTS, report="/export/store/report?kind=assets"),
            sub("issues", "Issue & return register", right=STORE_RIGHTS, report="/export/store/report?kind=issues", opts="dates"),
            sub("lost", "Lost / damaged", right=STORE_RIGHTS, report="/export/store/report?kind=lost", opts="dates"),
            sub("hired", "On rent now", right=STORE_RIGHTS, report="/export/store/report?kind=hired"),
            sub("mr_open", "Open requests", right=STORE_RIGHTS, report="/export/store/report?kind=mr_open"),
            sub("mr_history", "Request history", right=STORE_RIGHTS, report="/export/store/report?kind=mr_history"),
            sub("suppliers", "Suppliers", right="approvals", report="/export/store/suppliers/report"),
            sub("lpo", "LPO register", screen="lporegister", right="approvals"),
            sub("followup", "Order follow-up", screen="followup", right="requests")])]),
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
  /* The reports hub: tabs inside tabs, the preview underneath */
  .pg-sub { display: flex; gap: 4px; flex-wrap: wrap; padding: 8px 26px 0; background: white; border-bottom: 1px solid #E7E1DA; }
  .pg-sub:empty { display: none; }
  .pg-subtab { padding: 6px 12px; margin-bottom: 8px; font-size: 12.5px; font-weight: 600; color: #6A5C55; background: #F7F3EE; border: 1px solid #E4DCD2; border-radius: 6px; cursor: pointer; white-space: nowrap; }
  .pg-subtab:hover { background: #F1EAE3; }
  .pg-subtab.active { background: #2C2C2C; color: white; border-color: #2C2C2C; }
  .pg-hub { display: flex; flex-direction: column; height: calc(100vh - 150px); min-height: 420px; }
  .pg-repbar { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; padding: 10px 14px; background: white; border: 1px solid #E7E1DA; border-bottom: 0; border-radius: 8px 8px 0 0; }
  .pg-repname { display: flex; flex-direction: column; min-width: 190px; }
  .pg-repname strong { font-size: 14.5px; } .pg-repname small { color: #888; font-size: 12px; }
  .pg-repopts { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; flex: 1; }
  .pg-repopts label { font-size: 12px; font-weight: 600; color: #666; }
  .pg-repopts select, .pg-repopts input { height: 32px; padding: 0 8px; border: 1px solid #D5D9DE; border-radius: 6px; font-size: 12.5px; width: auto; max-width: 330px; margin: 0; }
  .pg-repacts { display: flex; gap: 6px; }
  .pg-repacts .btn { padding: 6px 12px; font-size: 12.5px; }
  .pg-frame { position: relative; flex: 1; border: 1px solid #E7E1DA; border-radius: 0 0 8px 8px; background: white; overflow: hidden; }
  .pg-frame iframe { width: 100%; height: 100%; border: 0; display: block; background: white; }
  .pg-frame-note { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: #888; font-size: 13px; background: white; pointer-events: none; }
  .pg-frame-note:empty { display: none; }
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
        <!-- ============ REPORTS HUB (temporary pages) ============ -->
        <div class="screen" id="screen-pgreports">
          <div class="status-msg" id="pgrep-status"></div>
          <div class="pg-hub">
            <div class="pg-repbar">
              <div class="pg-repname"><strong id="pg-rep-title"></strong><small id="pg-rep-sub"></small></div>
              <div class="pg-repopts" id="pg-repopts"></div>
              <div class="pg-repacts">
                <button class="btn btn-gray" onclick="pgRepPrint()">Print</button>
                <button class="btn btn-gray" onclick="pgRepDownload('pdf')">PDF</button>
                <button class="btn btn-gray" onclick="pgRepDownload('excel')">Excel</button>
                <button class="btn btn-dark" onclick="pgRepOpen()">Open in new tab</button>
              </div>
            </div>
            <div class="pg-frame"><iframe id="pg-preview" title="Report preview"></iframe><div class="pg-frame-note" id="pg-frame-note">Loading the preview&hellip;</div></div>
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
SCREEN_TITLES.lporegister = SCREEN_TITLES.lporegister || "LPO Register";
SCREEN_TITLES.followup = SCREEN_TITLES.followup || "Order Follow-up";
SCREEN_TITLES.suppliers = SCREEN_TITLES.suppliers || "Suppliers";
const PAGE_FILE = %(file_json)s;
function pgUrl(screen) { const k = PAGE_OF[screen] || "dashboard"; return (PAGE_FILE[k] || k) + ".html"; }
function pgHas(r) { return CURRENT_ROLE === "admin" || (Array.isArray(r) ? r.some(x => MY_SCREENS.includes(x)) : MY_SCREENS.includes(r)); }
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
};
function pgTab(id) {
  const t = pgTabFor(id); if (!t) return;
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

// ---- The reports hub: tabs inside tabs, the preview underneath ---------------
function pgSub(id) {
  const t = PG_TAB; if (!t) return;
  const sb = t.subs.find(x => x.id === id); if (!sb || !pgHas(sb.right)) return;
  PG_SUB = sb;
  location.hash = t.id + ":" + sb.id;
  const screen = sb.screen || "pgreports";
  const active = document.getElementById("screen-" + screen);
  if (active && active.classList.contains("active")) { pgRenderTabs(); if (!sb.screen) pgRepShow(); return; }
  switchScreen(screen);
}
function pgSeg(id) { const b = document.querySelector("#" + id + " button.on"); return b ? b.dataset.v : ""; }
function pgSegHtml(id, choices, on) {
  return `<span class="pg-seg" id="${id}">` + choices.map(([v, l]) => `<button data-v="${v}" class="${v === on ? "on" : ""}" onclick="pgSegPick(this)">${l}</button>`).join("") + `</span>`;
}
function pgSegPick(b) { b.parentNode.querySelectorAll("button").forEach(x => x.classList.toggle("on", x === b)); pgRepShow(); }
const PG_RUNS = { rows: null };
async function pgHubLoad() {
  refreshDownloadToken();
  if (PG_RUNS.rows === null && pgHas("hrpayroll")) {
    PG_RUNS.rows = [];
    try { PG_RUNS.rows = (await apiCall("/employees/payroll/runs")).rows || []; }
    catch (e) { showStatus("pgrep-status", "err", "Could not list the office cycles: " + errText(e)); }
  }
  pgRepShow();
}
// The options a report takes, drawn once per report; a change reloads it.
function pgRepOptions(sb) {
  const ym = new Date().toISOString().slice(0, 7);
  const runs = PG_RUNS.rows || [];
  const groups = [["labour", "Labour"], ["office", "Office"], ["local", "Local"], ["household", "Household"]];
  const can = g => CURRENT_ROLE === "admin" || MY_SCREENS.includes("people_" + g[0]);
  switch (sb.opts) {
    case "run": return runs.length
      ? `<label>Cycle</label><select id="pg-opt-run" onchange="pgRepShow()">${runs.map(r => `<option value="${r.id}">${escapeHtml(r.company)} - ${escapeHtml(r.month_year)} (${r.status === "approved" ? "approved" : "draft"})</option>`).join("")}</select>`
      : `<span class="muted" style="font-size:12px;">No office cycles yet</span>`;
    case "month": { const months = [...new Set(runs.map(r => r.month_year))]; return months.length
      ? `<label>Month</label><select id="pg-opt-month" onchange="pgRepShow()">${months.map(m => `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`).join("")}</select>`
      : `<span class="muted" style="font-size:12px;">No office cycles yet</span>`; }
    case "cycle": return `<label>Month</label><input type="month" id="pg-opt-cycle" value="${ym}" onchange="pgRepShow()">`;
    case "within": return `<label>Expiring within</label><input type="number" id="pg-opt-within" value="90" style="width:70px;" onchange="pgRepShow()"> days`;
    case "group": { const g = groups.filter(can); if (sb.id === "register") g.push(["left", "Left"]); return g.length ? pgSegHtml("pg-opt-group", g, g[0][0]) : ""; }
    case "days": return pgSegHtml("pg-opt-days", [["30", "30 days"], ["90", "90 days"], ["180", "180 days"]], "90");
    case "dates": return `<label>From</label><input type="date" id="pg-opt-from" onchange="pgRepShow()"><label>To</label><input type="date" id="pg-opt-to" onchange="pgRepShow()"><small class="muted" style="font-size:11.5px;">blank = everything</small>`;
  }
  return "";
}
function pgRepQuery(sb) {
  const v = id => (document.getElementById(id) || {}).value || "";
  const q = [];
  switch (sb.opts) {
    case "run": if (!v("pg-opt-run")) return null; q.push("run_id=" + v("pg-opt-run")); break;
    case "month": if (!v("pg-opt-month")) return null; q.push("month_year=" + encodeURIComponent(v("pg-opt-month"))); break;
    case "cycle": q.push("month_year=" + encodeURIComponent(hrCycleName(v("pg-opt-cycle")))); break;
    case "within": q.push("within=" + (v("pg-opt-within") || 90)); break;
    case "group": q.push("group=" + pgSeg("pg-opt-group")); break;
    case "days": q.push("days=" + pgSeg("pg-opt-days") + "&group="); break;
    case "dates": if (v("pg-opt-from")) q.push("date_from=" + v("pg-opt-from")); if (v("pg-opt-to")) q.push("date_to=" + v("pg-opt-to")); break;
  }
  if (sb.id === "increments") q.push("emp_no=");
  return q.join("&");
}
let PG_REP_DRAWN = "";
async function pgRepShow() {
  const sb = PG_SUB; if (!sb || sb.screen) return;
  const [path, fixed] = sb.report.split("?");
  document.getElementById("pg-rep-title").textContent = sb.label;
  document.getElementById("pg-rep-sub").textContent = PG_TAB.label;
  if (PG_REP_DRAWN !== sb.id) { document.getElementById("pg-repopts").innerHTML = pgRepOptions(sb); PG_REP_DRAWN = sb.id; }
  const q = pgRepQuery(sb);
  const note = document.getElementById("pg-frame-note"), frame = document.getElementById("pg-preview");
  if (q === null) { frame.removeAttribute("src"); note.textContent = "Nothing to show yet - no office cycle has been opened."; return; }
  note.textContent = "Loading the preview…";
  const t = await hrToken();
  const url = `${API}${path}/view?${[fixed, q].filter(Boolean).join("&")}${fixed || q ? "&" : ""}token=${t}`;
  // The report's own button bar is not needed in here - the bar above
  // does that - so it is hidden once the page is in.
  frame.onload = () => {
    note.textContent = "";
    try { const d = frame.contentDocument; const st = d.createElement("style"); st.textContent = ".bar{display:none!important} body{background:white!important;padding-top:0!important}"; d.head.appendChild(st); } catch (e) {}
  };
  frame.src = url;
}
async function pgRepUrl(format) {
  const sb = PG_SUB; const [path, fixed] = sb.report.split("?"); const q = pgRepQuery(sb); if (q === null) return null;
  const t = await hrToken(); const qs = [fixed, q].filter(Boolean).join("&");
  return format === "view" ? `${API}${path}/view?${qs}${qs ? "&" : ""}token=${t}` : `${API}${path}?${qs}${qs ? "&" : ""}token=${t}&format=${format}`;
}
async function pgRepOpen() { const u = await pgRepUrl("view"); if (u) window.open(u, "_blank"); }
async function pgRepDownload(fmt) { const u = await pgRepUrl(fmt); if (u) window.open(u, "_blank"); }
function pgRepPrint() { const f = document.getElementById("pg-preview"); try { f.contentWindow.focus(); f.contentWindow.print(); } catch (e) { pgRepOpen(); } }
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

"""Build the temporary pages from app.html.

    python3 deploy/build_temporary_pages.py

Each page under temporary/Infinia/ is the app itself - the same markup,
the same script, the same server - with a menu of eight entries in place
of seventeen and the old pages arranged as tabs. Nothing is rewritten:
a page is app.html with its sidebar swapped and a short script added at
the end, so what is entered on a temporary page is entered in the app,
and the day the layout moves into app.html there is nothing to carry
across.

Run again after every change to app.html; the pages are generated, not
edited by hand. `git diff` shows only what app.html changed.
"""
import os, re, html

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "app.html")
OUT = os.path.join(ROOT, "temporary", "Infinia")

# page key -> (title, sidebar label, tabs). A tab is (screen, label, right).
PAGES = {
    "dashboard": ("Dashboard", "Dashboard", [("dashboard", "Overview", "dashboard")]),
    "attendance": ("Attendance", "Attendance", [
        ("attendance", "Daily attendance", "attendance"),
        ("livecard", "Live card", "livecard"),
        ("masterdata", "Labour master data", "masterdata")]),
    "payroll": ("Payroll", "Payroll", [
        ("combine", "Salary cards", "combine"),
        ("errorcheck", "Check before you pay", "errorcheck"),
        ("hrpayroll", "Office HR & Payroll", "hrpayroll")]),
    "store": ("Store & Purchasing", "Store & Purchasing", [
        ("store", "Store / inventory", "store"),
        ("requests", "Material requests", "requests"),
        ("approvals", "Approvals", "approvals"),
        ("purchase", "Purchase orders", "approvals"),
        ("followup", "Order follow-up", "requests"),
        ("lporegister", "LPO register", "approvals"),
        ("suppliers", "Suppliers", "approvals")]),
    "reports": ("Reports", "Reports", [("reports", "Reports / summaries", "reports")]),
    "settings": ("Settings", "Settings", [("settings", "Settings", "settings")]),
    "activity": ("Activity Monitor", "Activity Monitor", [("activity", "Activity monitor", "activity")]),
}
# Screens without a tab of their own, reached from inside another.
EXTRA = {"monthly": "reports"}
ORDER = ["dashboard", "attendance", "people", "payroll", "store", "reports", "settings", "activity", "access"]
STANDALONE = {"people": ("People", "people"), "access": ("Access", "access")}

CSS = """
<style>
  /* ---- temporary pages: one menu, tabs in place of pages ---- */
  #legacy-sidebar { display: none !important; }
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
  @media (max-width: 900px) { .pg-side { width: 100%; padding-bottom: 6px; } .pg-side .pg-item { display: inline-block; padding: 9px 12px; } .pg-side .pg-group, .pg-side .brand { display: none; } }
</style>
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
function pgUrl(screen) { return (PAGE_OF[screen] || "dashboard") + ".html"; }
function pgAllowed(screen) { return CURRENT_ROLE === "admin" || MY_SCREENS.includes(RIGHT_OF[screen] || screen); }

const _switchScreen = switchScreen;
switchScreen = function (name) {
  if (!PAGE.screens.includes(name)) { location.href = pgUrl(name) + "#" + name; return; }
  _switchScreen(name);
  pgRenderTabs(name);
};
const _dashStoreGo = dashStoreGo;
dashStoreGo = function (panel) {
  if (!PAGE.screens.includes("store")) { location.href = "store.html#store:" + panel; return; }
  _dashStoreGo(panel);
};
// Where to land: the screen in the address, else the first tab this
// login may open. A login with nothing on this page goes to the first
// page it has.
firstScreenFor = function () {
  const [want, extra] = (location.hash || "").slice(1).split(":");
  if (want && PAGE.screens.includes(want) && pgAllowed(want)) {
    if (want === "store" && extra) setTimeout(() => storeGo(extra), 120);
    return want;
  }
  for (const t of PAGE.tabs) if (pgAllowed(t.screen)) return t.screen;
  const pages = %(order_json)s;
  for (const pg of pages) {
    if (pg === PAGE.key) continue;
    const any = (PAGE.pages[pg] || []).some(s => pgAllowed(s));
    if (any) { location.href = pg + ".html"; return PAGE.tabs[0].screen; }
  }
  return PAGE.tabs[0].screen;
};
function pgRenderTabs(active) {
  const bar = document.getElementById("pg-tabs");
  const tabs = PAGE.tabs.filter(t => pgAllowed(t.screen));
  bar.innerHTML = tabs.length > 1 ? tabs.map(t =>
    `<span class="pg-tab ${(active === "monthly" ? "reports" : active) === t.screen ? "active" : ""}" data-tab="${t.screen}" onclick="switchScreen('${t.screen}')">${t.label}</span>`).join("") : "";
  document.querySelectorAll(".pg-side .pg-item[data-page]").forEach(el => {
    const pg = el.dataset.page;
    const any = (PAGE.pages[pg] || []).some(s => pgAllowed(s));
    el.style.display = any ? "" : "none";
  });
  if (!tabs.length) {
    document.querySelectorAll(".screen").forEach(el => el.classList.remove("active"));
    document.getElementById("screen-title").textContent = "Not available to this login";
  }
}
// The tab strip and the menu follow the permissions once they arrive.
const _applyScreenPermissions = applyScreenPermissions;
applyScreenPermissions = async function () {
  await _applyScreenPermissions();
  pgRenderTabs((location.hash || "").slice(1).split(":")[0] || PAGE.tabs[0].screen);
};
// Legacy links inside the app that name the old sidebar still work: a
// screen opened by name goes to its page.
window.addEventListener("hashchange", () => {
  const want = (location.hash || "").slice(1).split(":")[0];
  if (want && PAGE.screens.includes(want)) switchScreen(want);
});
</script>
"""


def build():
    src = open(SRC, encoding="utf-8").read()
    # The old sidebar stays in the page, hidden: the script reads its
    # items to know what a login may open.
    m = re.search(r'<div class="sidebar">\n(\s*<div class="brand">.*?</div>)\n', src)
    if not m:
        raise SystemExit("app.html: sidebar not found where expected")
    brand = m.group(1).strip()
    src = src.replace('<div class="sidebar">\n', '<div class="sidebar" id="legacy-sidebar">\n', 1)
    src = src.replace("</head>", CSS + "</head>", 1)
    src = src.replace('<div class="content">\n', '<div class="pg-tabs" id="pg-tabs"></div>\n      <div class="content">\n', 1)

    page_of = {}
    pages_screens = {}
    right_of = {}
    for key, (_, _, tabs) in PAGES.items():
        pages_screens[key] = [t[0] for t in tabs]
        for screen, _, right in tabs:
            page_of[screen] = key
            right_of[screen] = right
    for screen, key in EXTRA.items():
        page_of[screen] = key
        right_of[screen] = key
    for key, (_, right) in STANDALONE.items():
        pages_screens[key] = [key]
        right_of[key] = right

    import json
    for key, (title, label, tabs) in PAGES.items():
        side = ['<div class="pg-side">', brand]
        for pg in ORDER:
            if pg in PAGES:
                side.append(f'<div class="pg-item {"active" if pg == key else ""}" data-page="{pg}" onclick="location.href=\'{pg}.html\'">{html.escape(PAGES[pg][1])}</div>')
            else:
                side.append(f'<div class="pg-item" data-page="{pg}" onclick="location.href=\'{pg}.html\'">{STANDALONE[pg][0]}</div>')
        side.append('<div class="pg-group">TEMPORARY BUILD</div>')
        side.append('<div class="pg-small" onclick="location.href=\'/app.html\'">&larr; Back to the classic app</div>')
        side.append("</div>")
        page = src.replace('<div class="sidebar" id="legacy-sidebar">', "\n".join(side) + '\n    <div class="sidebar" id="legacy-sidebar">', 1)
        page = page.replace("<title>", f"<title>{html.escape(title)} - ", 1) if "<title>" in page else page
        screens = [t[0] for t in tabs] + [s for s, k in EXTRA.items() if k == key]
        cfg = {"key": key, "title": title, "screens": screens,
               "tabs": [{"screen": s, "label": l} for s, l, _ in tabs], "pages": pages_screens}
        script = SCRIPT % {"key": key, "page_json": json.dumps(cfg), "page_of_json": json.dumps(page_of),
                           "right_of_json": json.dumps(right_of), "order_json": json.dumps(ORDER)}
        page = page.replace("</body>", script + "</body>", 1)
        with open(os.path.join(OUT, key + ".html"), "w", encoding="utf-8") as f:
            f.write(page)
        print(f"wrote temporary/Infinia/{key}.html  ({len(page) // 1024} KB)")


if __name__ == "__main__":
    build()

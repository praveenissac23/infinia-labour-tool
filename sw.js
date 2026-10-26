/* Working offline (service worker for app.infinia.ae).

   When the server can't be reached - an update restarting it, an outage at the hosting company, the office
   internet down - the app keeps working:
     - pages open from the copy kept on this computer (network first; the kept copy only when the server
       does not answer);
     - lists show what they showed the last time they were opened here;
     - a save is kept in this computer's own storage (IndexedDB - it survives closing the browser and switching
       the computer off) and is sent to the server, in order, as soon as it answers again;
     - anything that needs the server there and then (a new LPO / invoice / PC number, sending to Zoho,
       signing in) is refused with a plain message instead.
   Every save carries its own id (X-Req-Id): if the first try did reach the server before the line dropped, the
   server knows the id and answers it again instead of saving it twice (app/offline_once.py). */
const VER = "off-1";
const SHELL = "infinia-off-shell", DATA = "infinia-off-data";
const PAGES = ["/", "/portal/est-app.html", "/portal/boards.html", "/portal/people.html", "/portal/access.html"];

// Saves that need the server there and then: a number it gives, money sent to Zoho, sign-in, backups, files it reads.
const NEEDS_SERVER = [
  /^\/auth\//, /^\/backup\//, /^\/users/, /^\/permissions\//, /^\/settings\//, /\/zoho\//, /^\/notifications\/push\//,
  /^\/employees\/accounts\/(invoices|receipts|credentials|register)/, /^\/employees\/payroll\//, /^\/employees\/import/, /^\/employees\/expiry\/mail/,
  /^\/store\/purchase\/orders/, /^\/store\/returns/, /^\/store\/docs(\/|$)/, /^\/store\/est\/ipa\//, /^\/store\/est\/(subpcs|clientpcs)(\/|$)/,
  /\/read(\/|$)/, /^\/store\/docread\//, /import/, /-text$/, /\/paste$/, /\/upload/, /\/stmt\//, /\/files\/upload/, /^\/store\/kb\/import/, /\/sync\/run/,
];
const NEED_MSG = {
  "/store/purchase/orders": "A new LPO gets its number from the server",
  "/employees/accounts/invoices": "An invoice gets its number from the server",
  "/employees/accounts/receipts": "A receipt gets its number from the server",
  "/store/returns": "A return note gets its number from the server",
  "/zoho/": "Sending to Zoho needs the server",
  "/auth/": "Signing in needs the server",
};

// ------------------------------------------------------------------ the queue (IndexedDB)
function db() {
  return new Promise((res, rej) => {
    const r = indexedDB.open("infinia-offline", 1);
    r.onupgradeneeded = () => { const d = r.result; if (!d.objectStoreNames.contains("q")) d.createObjectStore("q", { keyPath: "n", autoIncrement: true }); if (!d.objectStoreNames.contains("map")) d.createObjectStore("map"); };
    r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error);
  });
}
async function tx(store, mode, fn) {
  const d = await db();
  return new Promise((res, rej) => { const t = d.transaction(store, mode); const s = t.objectStore(store); let out; Promise.resolve(fn(s)).then(v => out = v); t.oncomplete = () => res(out); t.onerror = () => rej(t.error); });
}
const req2p = r => new Promise((res, rej) => { r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); });
const allItems = () => tx("q", "readonly", s => req2p(s.getAll()));
const putItem = it => tx("q", "readwrite", s => req2p(s.put(it)));
const delItem = n => tx("q", "readwrite", s => req2p(s.delete(n)));

let OFFLINE = false, SYNCING = false, LAST_UP = 0;
async function state(extra = {}) {
  const items = await allItems().catch(() => []);
  const msg = Object.assign({ type: "offline-state", offline: OFFLINE, syncing: SYNCING, pending: items.filter(i => i.st !== "failed").length,
    failed: items.filter(i => i.st === "failed").length, uploaded: LAST_UP,
    items: items.map(i => ({ n: i.n, label: i.label, where: i.where, at: i.at, st: i.st, err: i.err || "" })) }, extra);
  for (const c of await self.clients.matchAll({ includeUncontrolled: true })) c.postMessage(msg);
}
function setOffline(v) { if (OFFLINE !== v) { OFFLINE = v; state(); } }

// What a save was, in words for the list ("Petty cash", "Store: material moved" ...).
const WHERE = [[/^\/attendance\//, "Daily attendance"], [/^\/store\/petty-cash/, "Petty cash"], [/^\/store\/movements/, "Store: material moved"], [/^\/store\/requests/, "Material request"],
  [/^\/store\/bank/, "Bank entry"], [/^\/store\/est\/logs/, "Site & technical log"], [/^\/store\/est\/variations/, "Variation"], [/^\/store\/est\//, "Estimation"], [/^\/store\/kb\//, "Trello"],
  [/^\/store\/ppe/, "PPE"], [/^\/store\/camp/, "Labour camp"], [/^\/store\/visa/, "Visa file"], [/^\/store\/items/, "Store items"], [/^\/store\/hire/, "Rentals"], [/^\/store\//, "Store"],
  [/^\/employees\/leave|staff-leave/, "Leave"], [/^\/employees\/pdc/, "PDC"], [/^\/employees\//, "Staff / accounts"], [/^\/adjustments|^\/summaries/, "Salary adjustment"]];
function whereOf(path) { const w = WHERE.find(([re]) => re.test(path)); return w ? w[1] : "Saved change"; }
function labelOf(method, path, body) {
  let what = "";
  try { const j = JSON.parse(body); what = j.title || j.description || j.name || j.item_name || j.details || j.notes || j.note || j.status || j.date || ""; if (typeof what !== "string") what = ""; } catch (e) {}
  const verb = method === "DELETE" ? "Removed" : method === "POST" ? "Added" : "Changed";
  return (verb + (what ? " - " + what : "")).slice(0, 90);
}

// ------------------------------------------------------------------ sending what is waiting
const TEMP = /^-\d{6,}$/;
async function replay() {
  if (SYNCING) return; SYNCING = true; let up = 0;
  try {
    const items = (await allItems()).filter(i => i.st !== "failed").sort((a, b) => a.n - b.n);
    if (items.length) state();
    const map = await tx("map", "readonly", s => new Promise(res => { const out = {}; const c = s.openCursor(); c.onsuccess = () => { const k = c.result; if (k) { out[k.key] = k.value; k.continue(); } else res(out); }; }));
    for (const it of items) {
      // a record made offline and then changed offline: its number is the one the server gave it
      let url = it.url.replace(/\/(-\d{6,})(?=\/|\?|$)/g, (m, t) => map[t] ? "/" + map[t] : m);
      let body = it.body;
      if (body && typeof body === "string" && it.ctype && it.ctype.includes("json")) {
        try { body = JSON.stringify(JSON.parse(body, (k, v) => (typeof v === "number" && map[String(v)]) ? map[String(v)] : v)); } catch (e) {}
      }
      let r;
      try { r = await fetch(url, { method: it.method, headers: it.headers, body: it.method === "GET" ? undefined : body }); }
      catch (e) { setOffline(true); break; }
      if (r.status === 502 || r.status === 503 || r.status === 504) { setOffline(true); break; }
      setOffline(false);
      if (r.ok) {
        try { const j = await r.clone().json(); if (it.temp && j && j.id) await tx("map", "readwrite", s => req2p(s.put(j.id, String(it.temp)))); if (it.temp && j && j.id) map[String(it.temp)] = j.id; } catch (e) {}
        await delItem(it.n); up++;
      } else {
        let err = "The server refused it";
        try { const j = await r.json(); if (typeof j.detail === "string") err = j.detail; } catch (e) {}
        if (r.status === 401) err = "Signed out - sign in again and redo this";
        it.st = "failed"; it.err = err; await putItem(it);
      }
    }
  } finally {
    SYNCING = false; if (up) LAST_UP = up; await state(up ? { justUploaded: up } : {});
  }
}

// ------------------------------------------------------------------ fetch
const isStatic = p => /^\/portal\//.test(p) || /\.(js|css|png|jpe?g|webp|svg|gif|ico|woff2?|ttf|json|html|mp3|wasm|traineddata)$/i.test(p) || p === "/sw.js";
function withTimeout(p, ms) { return new Promise((res, rej) => { const t = setTimeout(() => rej(new Error("timeout")), ms); p.then(v => { clearTimeout(t); res(v); }, e => { clearTimeout(t); rej(e); }); }); }
const jsonResp = (o, status = 200) => new Response(JSON.stringify(o), { status, headers: { "Content-Type": "application/json", "X-Offline": "1" } });

self.addEventListener("install", e => {
  self.skipWaiting();
  e.waitUntil((async () => {          // the pages and what they load, kept for the first outage
    const c = await caches.open(SHELL);
    for (const pg of PAGES) {
      try {
        const r = await fetch(pg, { cache: "no-store" }); if (!r.ok) continue;
        await c.put(pg, r.clone());
        const html = await r.text();
        const urls = [...html.matchAll(/(?:src|href)="(\/portal\/[^"]+)"/g)].map(m => m[1]).filter(u => !/\.html/.test(u));
        await Promise.all(urls.slice(0, 120).map(u => fetch(u).then(x => x.ok && c.put(u, x)).catch(() => {})));
      } catch (er) {}
    }
  })());
});
self.addEventListener("activate", e => e.waitUntil(self.clients.claim().then(() => state())));
self.addEventListener("message", e => {
  const d = e.data || {};
  if (d.type === "offline-hello") state();
  else if (d.type === "offline-replay") replay();
  else if (d.type === "offline-up") { setOffline(false); replay(); }
  else if (d.type === "offline-clear-data") caches.delete(DATA);             // signed out: this person's lists are not kept
  else if (d.type === "offline-drop") delItem(d.n).then(() => state());
});
self.addEventListener("sync", e => { if (e.tag === "infinia-q") e.waitUntil(replay()); });

self.addEventListener("fetch", e => {
  const req = e.request, url = new URL(req.url);
  if (url.origin !== location.origin) return;
  const path = url.pathname;
  if (path === "/health" || path.startsWith("/export/")) return;            // live check / downloads: straight to the server
  const dest = req.destination;
  if (req.mode === "navigate" || dest === "document" || dest === "iframe") {
    if (path.startsWith("/export/") || path.startsWith("/api/")) return;
    e.respondWith((async () => {
      try {
        const r = await withTimeout(fetch(req), 9000);
        if (r.status >= 502 && r.status <= 504) throw new Error("down");
        if (r.ok) { const c = await caches.open(SHELL); c.put(path === "/" || path === "/app.html" ? "/" : path, r.clone()); }
        setOffline(false); return r;
      } catch (er) {
        setOffline(true);
        const c = await caches.open(SHELL);
        return (await c.match(path === "/app.html" ? "/" : path, { ignoreSearch: true })) || (await c.match("/")) || new Response("<h2>The server can't be reached, and this page has not been opened on this computer before.</h2>", { status: 503, headers: { "Content-Type": "text/html" } });
      }
    })());
    return;
  }
  if (isStatic(path) || (dest && dest !== "")) {                             // scripts, styles, pictures
    e.respondWith((async () => {
      const c = await caches.open(SHELL);
      if (url.search.includes("v=")) { const hit = await c.match(req); if (hit) return hit; }
      try {
        const r = await fetch(req);
        if (r.ok && req.method === "GET") {
          if (url.search.includes("v=")) (await c.keys()).forEach(k => { const ku = new URL(k.url); if (ku.pathname === path && ku.search !== url.search) c.delete(k); });   // an older version of the same file is let go
          c.put(req, r.clone());
        }
        return r;
      }
      catch (er) { return (await c.match(req)) || (await c.match(req, { ignoreSearch: true })) || Response.error(); }
    })());
    return;
  }
  // ---- the app's data
  if (req.method === "GET") {
    e.respondWith((async () => {
      try {
        const r = await withTimeout(fetch(req), 15000);
        if (r.status >= 502 && r.status <= 504) throw new Error("down");
        setOffline(false);
        if (r.ok && (r.headers.get("Content-Type") || "").includes("json")) { const c = await caches.open(DATA); c.put(req, r.clone()); }
        return r;
      } catch (er) {
        setOffline(true);
        const hit = await (await caches.open(DATA)).match(req);
        if (hit) { const h = new Headers(hit.headers); h.set("X-Offline", "1"); return new Response(await hit.blob(), { status: 200, headers: h }); }
        return jsonResp({ detail: "Working offline - this list has not been opened on this computer before. It shows again when the server is back." }, 503);
      }
    })());
    return;
  }
  // a save
  e.respondWith((async () => {
    const id = req.headers.get("X-Req-Id") || (Date.now().toString(36) + Math.random().toString(36).slice(2, 10));
    const headers = {}; req.headers.forEach((v, k) => { headers[k] = v; }); headers["x-req-id"] = id;
    const ctype = req.headers.get("Content-Type") || "";
    const body = req.method === "GET" || req.method === "HEAD" ? undefined : (ctype.includes("multipart") ? await req.clone().arrayBuffer() : await req.clone().text());
    const needs = NEEDS_SERVER.some(re => re.test(path));
    try {
      if (OFFLINE && !needs) throw new Error("offline");                     // known to be down: don't wait for a time-out
      const r = await fetch(req.url, { method: req.method, headers, body });
      if (r.status >= 502 && r.status <= 504) throw new Error("down");        // the app behind the web server is not answering
      if (r.status < 500) setOffline(false);
      return r;
    } catch (er) {
      setOffline(true);
      if (needs) {
        const k = Object.keys(NEED_MSG).find(x => path.includes(x));
        return jsonResp({ detail: `${k ? NEED_MSG[k] : "This needs the server"} - it works again as soon as the server is back (usually a few minutes). Your other work is being kept on this computer.` }, 503);
      }
      const temp = req.method === "POST" ? -((Date.now() % 1e11) * 10 + Math.floor(Math.random() * 10)) : null;   // a stand-in id until the server gives the real one
      await putItem({ url: req.url, method: req.method, headers, body, ctype, at: Date.now(), st: "pending", temp,
                      where: whereOf(path), label: labelOf(req.method, path, typeof body === "string" ? body : "") });
      try { await self.registration.sync.register("infinia-q"); } catch (x) {}
      state({ justQueued: true });
      return jsonResp({ ok: true, queued: true, offline: true, id: temp || undefined, detail: "Saved on this computer - it uploads when the server is back" });
    }
  })());
});

// ------------------------------------------------------------------ phone notifications (as before)
self.addEventListener("push", e => {
  let m = {};
  try { m = e.data ? e.data.json() : {}; } catch (x) { m = { title: "Infinia", body: e.data ? e.data.text() : "" }; }
  e.waitUntil(self.registration.showNotification(m.title || "Infinia", {
    body: m.body || "", tag: m.tag || undefined, renotify: !!m.tag,
    icon: "/portal/icon-192.png", badge: "/portal/icon-192.png",
    data: { url: m.url || "/" }
  }).then(() => self.navigator && self.navigator.setAppBadge ? self.registration.getNotifications()
      .then(list => self.navigator.setAppBadge(list.length)).catch(() => {}) : null));
});

self.addEventListener("notificationclick", e => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/";
  e.waitUntil((async () => {
    const all = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const c of all) {
      if (new URL(c.url).origin === self.location.origin) {
        await c.focus();
        c.postMessage({ type: "infinia-open", url });
        return;
      }
    }
    await self.clients.openWindow(url);
  })());
});

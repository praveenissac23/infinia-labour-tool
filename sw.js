/* Infinia phone app: shows the notifications the server pushes, and opens
   the app on the item when one is tapped. Screens and figures always come
   live from the server; only the fixed files that carry their version in
   the address (help scripts, pictures) are kept on the phone, so a page
   opens without fetching them again. */
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));

const STATIC = "infinia-static-1";
self.addEventListener("fetch", e => {
  const r = e.request;
  if (r.method !== "GET") return;
  const u = new URL(r.url);
  if (u.origin !== self.location.origin || !u.pathname.startsWith("/portal/")) return;
  const fixed = /[?&]v=[0-9a-f]{6,}/.test(u.search) || /\/portal\/(logo-[0-9a-f]{8}\.png|infi-[\w-]+\.webp|icon-\d+\.png)$/.test(u.pathname);
  if (!fixed) return;
  e.respondWith((async () => {
    const c = await caches.open(STATIC);
    const hit = await c.match(r);
    if (hit) return hit;
    const res = await fetch(r);
    if (res.ok) {
      // an older version of the same file is let go
      (await c.keys()).forEach(k => { const ku = new URL(k.url); if (ku.pathname === u.pathname && ku.search !== u.search) c.delete(k); });
      c.put(r, res.clone());
    }
    return res;
  })().catch(() => fetch(r)));
});

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

/* Infinia phone app: shows the notifications the server pushes, and opens
   the app on the item when one is tapped. It caches nothing - every screen
   is always the live one. */
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));

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

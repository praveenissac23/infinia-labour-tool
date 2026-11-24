// The personal space's own service worker (24/11/2026). Scope /portal/me only: its notification subscription is
// separate from the work app's (/sw.js), so turning one off never stops the other. No caching here - the page always
// asks the server, and nothing personal is kept in the browser's cache.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("push", e => {
  let m = {};
  try { m = e.data ? e.data.json() : {}; } catch (x) { m = { title: "Reminder", body: e.data ? e.data.text() : "" }; }
  e.waitUntil(self.registration.showNotification(m.title || "Reminder", {
    body: m.body || "", tag: m.tag || undefined, renotify: !!m.tag, requireInteraction: true,
    icon: "/portal/me-icon-192.png", badge: "/portal/me-icon-192.png", data: { url: m.url || "/portal/me.html" }
  }));
});
self.addEventListener("notificationclick", e => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/portal/me.html";
  e.waitUntil((async () => {
    const all = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const c of all) { if (new URL(c.url).pathname === "/portal/me.html") { await c.focus(); try { await c.navigate(url); } catch (x) {} return; } }
    await self.clients.openWindow(url);
  })());
});

// Shell + chart cached for offline use; plan is network-first with cache fallback.
const VERSION = "mvderby-v3";
const SHELL = ["/", "/styles.css", "/app.js", "/chart.webp", "/chart.json", "/manifest.webmanifest", "/icon.svg"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname === "/api/plan") {
    e.respondWith(fetch(e.request).then((r) => {
      if (r.ok) { const copy = r.clone(); caches.open(VERSION).then((c) => c.put("/api/plan", copy)); }
      return r;
    }).catch(() => caches.match("/api/plan")));
    return;
  }
  if (url.pathname === "/" || url.pathname.endsWith(".js") || url.pathname.endsWith(".css")) {
    // stale-while-revalidate so deploys show up on the next open
    e.respondWith(caches.match(e.request).then((hit) => {
      const net = fetch(e.request).then((r) => { if (r.ok) { const copy = r.clone(); caches.open(VERSION).then((c) => c.put(e.request, copy)); } return r; }).catch(() => hit);
      return hit || net;
    }));
    return;
  }
  e.respondWith(caches.match(e.request).then((hit) => hit || fetch(e.request)));
});

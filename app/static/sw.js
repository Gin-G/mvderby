// Shell + chart cached for offline use; plan is network-first with cache fallback.
const VERSION = "mvderby-v6";
const TILES = "mvderby-tiles";  // saved chart tiles survive app updates
const SHELL = ["/chart.webp", "/chart.json", "/manifest.webmanifest", "/icon.svg"];

// The page links CSS/JS as /file.css?v=<build>; precache exactly those URLs, fresh from the server.
async function precache() {
  const c = await caches.open(VERSION);
  const page = await fetch("/", { cache: "reload" });
  const html = await page.clone().text();
  await c.put("/", page);
  const assets = [...html.matchAll(/(?:href|src)="(\/[^"]+\.(?:css|js)\?v=[^"]+)"/g)].map((m) => m[1]);
  await Promise.all([...assets, ...SHELL].map((u) => fetch(u, { cache: "reload" }).then((r) => r.ok && c.put(u, r))));
}

self.addEventListener("install", (e) => {
  e.waitUntil(precache().then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== VERSION && k !== TILES).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/tiles/")) {
    // cache-first: saved tiles work with no signal; new ones are kept as you browse
    e.respondWith(caches.open(TILES).then((c) => c.match(e.request).then((hit) => hit || fetch(e.request).then((r) => {
      if (r.ok) c.put(e.request, r.clone());
      return r;
    }))));
    return;
  }
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

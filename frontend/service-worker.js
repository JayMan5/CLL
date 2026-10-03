/* COURTLOG PWA shell only. Authenticated API data and all POSTs are never cached. */
const CACHE_NAME = "courtlog-shell-v6";
const SHELL_ASSETS = [
  "/static/tailwind.css",
  "/static/index.css",
  "/static/vendor/fonts/outfit/wght.css",
  "/static/vendor/fonts/outfit/files/outfit-latin-wght-normal.woff2",
  "/static/vendor/fonts/outfit/files/outfit-latin-ext-wght-normal.woff2",
  "/static/vendor/fonts/plus-jakarta-sans/wght.css",
  "/static/vendor/fonts/plus-jakarta-sans/files/plus-jakarta-sans-latin-wght-normal.woff2",
  "/static/vendor/fonts/plus-jakarta-sans/files/plus-jakarta-sans-latin-ext-wght-normal.woff2",
  "/static/vendor/fontawesome/css/all.min.css",
  "/static/vendor/fontawesome/webfonts/fa-brands-400.woff2",
  "/static/vendor/fontawesome/webfonts/fa-regular-400.woff2",
  "/static/vendor/fontawesome/webfonts/fa-solid-900.woff2",
  "/static/vendor/fontawesome/webfonts/fa-v4compatibility.woff2",
  "/static/chart.bundle.js",
  "/static/app.js",
  "/static/c2-pwa.bundle.js",
  "/static/manifest.webmanifest",
  "/static/offline.html",
  "/static/icons/courtlog-192.png",
  "/static/icons/courtlog-512.png"
];

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(SHELL_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", event => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names.filter(name => name.startsWith("courtlog-shell-") && name !== CACHE_NAME)
      .map(name => caches.delete(name)));
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", event => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;

  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(async () => {
      const cached = await caches.match("/static/offline.html");
      return cached || new Response(
        "Offline. CourtLOG does not queue custody scans. Reconnect before submitting a check-in.",
        { status: 503, headers: { "Content-Type": "text/plain; charset=utf-8" } }
      );
    }));
    return;
  }

  if (SHELL_ASSETS.includes(url.pathname)) {
    event.respondWith((async () => {
      const cache = await caches.open(CACHE_NAME);
      const cached = await cache.match(request);
      try {
        const response = await fetch(request);
        if (response.ok) await cache.put(request, response.clone());
        return response;
      } catch (error) {
        if (cached) return cached;
        throw error;
      }
    })());
  }
});

// Inko service worker. App files: network first (so updates show right away), with the
// cached copy as the offline fallback. Fonts, icons, and images: cache first.
// Analysis and account requests always go to the network and are never cached.
const CACHE = "inko-v5";   // bump when app files change shape (v2: analysis backend results; v3: whole-page flag; v4: maths panel; v5: Jev removed)
const SHELL = [
  "/", "/index.html", "/manifest.json", "/css/styles.css", "/js/app.js",
  "/fonts/figtree.woff2", "/fonts/figtree-italic.woff2",
  "/img/logo-mark.png", "/img/wordmark.png", "/img/example.jpg",
  "/icons/icon-192.png", "/icons/icon-512.png", "/icons/apple-touch-icon.png", "/icons/favicon-32.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname === "/analyze") return;

  const cacheFirst = /^\/(fonts|icons|img)\//.test(url.pathname);
  if (cacheFirst) {
    event.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((res) => {
        if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); }
        return res;
      })),
    );
    return;
  }

  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); }
        return res;
      })
      .catch(() => caches.match(req).then((hit) => hit || (req.mode === "navigate" ? caches.match("/index.html") : Response.error()))),
  );
});

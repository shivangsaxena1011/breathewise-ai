// Low-internet mode: cache the app shell (HTML + built JS/CSS) so the app opens offline.
// API calls are never answered from this cache: when offline they fail, and the app falls back to the
// last reading it saved itself and shows an "offline — data from <time>" banner, so old AQI never looks live.
const SHELL = "bw-shell-v4";

async function precache() {
  const cache = await caches.open(SHELL);
  const res = await fetch("/", { cache: "no-store" });
  if (!res.ok) return;
  const html = await res.clone().text();
  await cache.put("/", res);
  const assets = [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map((m) => m[1]);
  await cache.addAll(["/logo.svg", "/manifest.webmanifest", ...assets]);
}

self.addEventListener("install", (e) => {
  e.waitUntil(precache().catch(() => {}));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== SHELL).map((k) => caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/")) return;
  if (e.request.mode === "navigate") {
    // HTML: network first so new releases show at once; cached shell when offline
    e.respondWith(
      fetch(e.request)
        .then((res) => {
          const copy = res.clone();
          if (res.ok) caches.open(SHELL).then((c) => c.put("/", copy));
          return res;
        })
        .catch(() => caches.match("/").then((hit) => hit || Response.error()))
    );
    return;
  }
  // Hashed assets never change, so cache-first is safe; lazily loaded page chunks are cached on first use.
  e.respondWith(
    caches.match(e.request).then((hit) => hit || fetch(e.request).then((res) => {
      const copy = res.clone();
      if (res.ok) caches.open(SHELL).then((c) => c.put(e.request, copy));
      return res;
    }).catch(() => Response.error()))
  );
});

/* Buddilio service worker — app shell + offline fallback. */
const VERSION = "buddilio-v1";
const SHELL = `${VERSION}-shell`;
const MEDIA = `${VERSION}-media`;
const OFFLINE_URL = "/offline.html";
const PRECACHE = ["/", OFFLINE_URL, "/manifest.json", "/icons/icon-192.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => !k.startsWith(VERSION)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("message", (event) => {
  if (event.data === "skip-waiting") self.skipWaiting();
});

const isMedia = (request, url) =>
  request.destination === "image" ||
  request.destination === "font" ||
  url.pathname.startsWith("/api/files/");

async function networkFirst(request, cacheName, fallback) {
  try {
    const fresh = await fetch(request);
    if (fresh && fresh.ok && request.method === "GET") {
      const cache = await caches.open(cacheName);
      cache.put(request, fresh.clone());
    }
    return fresh;
  } catch (err) {
    const cached = await caches.match(request);
    if (cached) return cached;
    if (fallback) {
      const shell = await caches.match(fallback);
      if (shell) return shell;
    }
    throw err;
  }
}

async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) {
    fetch(request).then((fresh) => {
      if (fresh && (fresh.ok || fresh.type === "opaque")) {
        caches.open(cacheName).then((cache) => cache.put(request, fresh));
      }
    }).catch(() => {});
    return cached;
  }
  const fresh = await fetch(request);
  if (fresh && (fresh.ok || fresh.type === "opaque")) {
    const cache = await caches.open(cacheName);
    cache.put(request, fresh.clone());
  }
  return fresh;
}

self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) { data = {}; }
  const url = new URL(data.url || "/dashboard", self.location.origin).href;
  event.waitUntil(self.registration.showNotification(data.title || "Buddilio", {
    body: data.body || "",
    icon: data.icon || "/icons/icon-192.png",
    badge: data.badge || "/icons/icon-192.png",
    tag: data.tag || undefined,
    data: { url },
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || "/dashboard";
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const client of windows) {
      if ("focus" in client) {
        await client.focus();
        if ("navigate" in client) await client.navigate(target);
        return;
      }
    }
    if (self.clients.openWindow) await self.clients.openWindow(target);
  })());
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (!url.protocol.startsWith("http")) return;
  if (url.pathname.startsWith("/api/") && !url.pathname.startsWith("/api/files/")) return;
  if (url.pathname.startsWith("/ws") || request.headers.get("upgrade") === "websocket") return;

  if (request.mode === "navigate") {
    event.respondWith(networkFirst(request, SHELL, OFFLINE_URL));
    return;
  }
  if (isMedia(request, url)) {
    event.respondWith(cacheFirst(request, MEDIA).catch(() => caches.match(OFFLINE_URL)));
    return;
  }
  if (url.origin === self.location.origin) {
    event.respondWith(networkFirst(request, SHELL));
  }
});

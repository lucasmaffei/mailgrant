// mailgrant service worker: app shell cache, push notifications, badge.
// Mail itself is never cached here: /app/api always goes to the network.

const SHELL = "mailgrant-shell-v2";
const ASSETS = [
  "/app/",
  "/app/static/app.css",
  "/app/static/app.js",
  "/app/static/fonts/inter.woff2",
  "/app/static/fonts/inter-tight.woff2",
  "/app/static/fonts/geist-mono.woff2",
  "/app/static/icons/icon-192.png",
  "/app/manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SHELL).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== SHELL).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/app/api")) return;
  // Network first so a deploy shows up at once; the cache only covers offline starts.
  event.respondWith(
    fetch(event.request)
      .then((res) => {
        if (res.ok && ASSETS.includes(url.pathname)) {
          const copy = res.clone();
          caches.open(SHELL).then((c) => c.put(event.request, copy));
        }
        return res;
      })
      .catch(() => caches.match(event.request).then((hit) => hit || caches.match("/app/"))),
  );
});

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (_) {
    data = { title: "mailgrant", body: event.data ? event.data.text() : "" };
  }
  const tasks = [
    self.registration.showNotification(data.title || "mailgrant", {
      body: data.body || "",
      tag: data.tag,
      icon: "/app/static/icons/icon-192.png",
      badge: "/app/static/icons/badge-72.png",
      data: { url: data.url || "/app/" },
    }),
  ];
  if (typeof data.badge === "number" && "setAppBadge" in self.navigator) {
    tasks.push(data.badge ? self.navigator.setAppBadge(data.badge) : self.navigator.clearAppBadge());
  }
  event.waitUntil(Promise.all(tasks));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL(event.notification.data?.url || "/app/", location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((wins) => {
      const open = wins.find((w) => new URL(w.url).pathname.startsWith("/app"));
      if (open) return open.focus().then((w) => w.navigate(target));
      return self.clients.openWindow(target);
    }),
  );
});

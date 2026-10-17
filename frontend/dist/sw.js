// P1-22: CACHE_NAME 应在每次发布时更新（或通过构建期注入版本号）
// FIX: [2026-07-18] 白屏修复：升级缓存版本号强制清除旧缓存。
// FIX: [2026-07-21 P0] 修复 "Failed to fetch dynamically imported module" 错误：
//   1. 升级 CACHE_VERSION → 1.2.0，activate 时清除所有旧版本缓存（包括 1.1.x 缓存的
//      旧 JS chunk）。
//   2. JS/CSS chunk 从 cache-first 改为 network-first：旧策略缓存了已删除的
//      chunk（hash 文件名），新版本发布后路由切换仍返回旧缓存 → 旧 HTML 引用
//      旧 chunk 但 SW 返回过时副本或 404 → 白屏/动态导入失败。
//      network-first 确保每次路由切换都获取最新 chunk，网络失败时回退缓存。
//   3. index.html 加入 STATIC_ASSETS 但导航请求已用 network-first，确保 HTML
//      总是最新。
const CACHE_VERSION = '1.2.0';
const CACHE_NAME = `pygbsentry-${CACHE_VERSION}`;
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/icons/icon.svg',
];

// Install: cache static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS);
    }).then(() => self.skipWaiting())
  );
});

// Activate: clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch: network-only for API, network-first for navigation & JS/CSS, cache-first for other static
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET and cross-origin requests
  if (request.method !== 'GET') return;
  if (url.origin !== self.location.origin) return;

  // P1-22: API 请求不缓存 — 防止敏感数据/陈旧响应被缓存到 SW
  // API 请求直接透传到网络，不经过 SW 缓存
  if (url.pathname.startsWith('/api/')) {
    return;
  }

  // FIX: [2026-07-16 P0] 导航请求（HTML）使用 network-first 策略。
  // 原实现对所有非 API 请求使用 cache-first，导致发布新版本后
  // 旧的 index.html 被缓存返回，引用已删除的 JS chunk（带 hash 文件名）
  // 返回 404 → 白屏。network-first 确保用户总是拿到最新 HTML，
  // 网络失败时回退缓存保证离线可用。
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          }
          return response;
        })
        .catch(() => {
          return caches.match(request).then((cached) => {
            return cached || caches.match('/index.html');
          });
        })
    );
    return;
  }

  // FIX: [2026-07-21 P0] JS/CSS 模块（带 hash 的 chunk）使用 network-first 策略。
  // 原策略 cache-first 会在发布新版本后返回已缓存的旧 chunk（或旧 HTML 引用的
  // 已删除 hash 文件），导致 "Failed to fetch dynamically imported module"。
  // network-first 确保路由懒加载总是获取最新 chunk，网络失败时回退缓存。
  const isJsModule = request.destination === 'script' ||
    request.destination === 'style' ||
    url.pathname.startsWith('/assets/') ||
    url.pathname.startsWith('/js/') ||
    url.pathname.startsWith('/css/');
  if (isJsModule) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          }
          return response;
        })
        .catch(() => {
          return caches.match(request).then((cached) => cached || Response.error());
        })
    );
    return;
  }

  // Other static assets: cache-first (icons, fonts, etc. — no hash versioning issues)
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request).then((response) => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
        }
        return response;
      });
    })
  );
});

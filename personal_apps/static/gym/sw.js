self.addEventListener('install', (event) => {
    self.skipWaiting();
});

// Hashed bundles only. Their filenames carry the content hash, so a cached
// entry can never go stale -- a rebuild changes the URL, not the bytes. The
// server says the same thing (Cache-Control: immutable, app.py); this makes
// repeat loads instant even before the HTTP cache warms, and survives it
// being evicted. Everything else (pages, gym.css, this file) stays
// network-only: those DO change in place.
const ASSET_CACHE = 'gym-hashed-assets-v1';
const HASHED_PREFIX = '/static/gym/dist/assets/';

self.addEventListener('activate', (event) => {
    event.waitUntil((async () => {
        // Old bundles accumulate one set per deploy visited. The cache is
        // authoritative for nothing (any miss just hits the network), so
        // dropping it wholesale when it grows is safe and simpler than LRU.
        const cache = await caches.open(ASSET_CACHE);
        if ((await cache.keys()).length > 60) {
            await caches.delete(ASSET_CACHE);
        }
        await self.clients.claim();
    })());
});

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);
    if (url.origin !== self.location.origin || !url.pathname.startsWith(HASHED_PREFIX)) {
        return; // fall through to the network untouched
    }
    event.respondWith((async () => {
        const cache = await caches.open(ASSET_CACHE);
        const hit = await cache.match(event.request);
        if (hit) return hit;
        const response = await fetch(event.request);
        if (response.ok) {
            cache.put(event.request, response.clone());
        }
        return response;
    })());
});

self.addEventListener('push', (event) => {
    let data = { title: 'Gym Tracker', body: 'Time for your next set.' };
    if (event.data) {
        try {
            data = event.data.json();
        } catch (e) {
            data.body = event.data.text();
        }
    }
    event.waitUntil(
        self.registration.showNotification(data.title || 'Gym Tracker', {
            body: data.body || '',
            icon: '/static/gym/icons/icon-192.png',
            badge: '/static/gym/icons/icon-192.png',
        })
    );
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    event.waitUntil(
        self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
            for (const client of clientList) {
                if (client.url.includes('/gym') && 'focus' in client) {
                    return client.focus();
                }
            }
            if (self.clients.openWindow) {
                return self.clients.openWindow('/gym');
            }
        })
    );
});

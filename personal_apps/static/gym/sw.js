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

// The browser replacing this device's endpoint, which is the moment a
// duplicate row is born: the server has no way to tell the new endpoint from
// a second device, and the old one stays valid at the push service, so both
// keep delivering to the same phone. `replaces` is what lets the server
// retire the row instead of guessing.
//
// Belt and braces with the daily pruning on the server: this event is not
// reliably delivered on every platform, and a rotation that happens while the
// worker is asleep is simply never reported. Pruning catches what this misses;
// this spares the user up to a month of double buzzing when it does fire.
self.addEventListener('pushsubscriptionchange', (event) => {
    event.waitUntil((async () => {
        const previous = event.oldSubscription || null;
        // Re-subscribe with the SAME key the old subscription carried rather
        // than a hardcoded one: the worker has no access to the page's VAPID
        // config, and the key is the one thing the expiring subscription can
        // still tell us.
        const key = previous && previous.options && previous.options.applicationServerKey;
        const fresh = event.newSubscription || (key
            ? await self.registration.pushManager.subscribe({
                userVisibleOnly: true, applicationServerKey: key,
            })
            : null);
        if (!fresh) return;
        const body = fresh.toJSON();
        if (previous) body.replaces = previous.endpoint;
        await fetch('/gym/push/subscribe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
    })());
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

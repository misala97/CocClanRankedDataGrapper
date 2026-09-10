"""Task S8 step 3: a real browser against the real page, through the store.

python-playwright, headless chromium, one script, one process. The session
cookie is MINTED here with the app's own signing serializer; no owner
credential is used and no password is typed anywhere.

`now` is the real wall clock in this task, not the fixed instant the other
tasks pin, because the server takes `utcnow()` per request and the store's
ages have to line up with it. The fixture carries buckets to 2026-09-15, so
the real clock is inside its data.

Run from `personal_apps/`:
    python ../radar-design/perf2-spike/run_s8_browser.py
"""
import datetime as dt
import json
import os
import subprocess
import sys
import time
import urllib.request

import sqlalchemy as sa

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from env_check import bootstrap  # noqa: E402
bootstrap()

import keys                                            # noqa: E402
import producer                                        # noqa: E402
import selections                                      # noqa: E402
import store                                           # noqa: E402
from env_check import APP_DIR, SPIKE_DIR               # noqa: E402
from env_check import fixture_sources, preflight       # noqa: E402

PORT = 5001
SHOTS = os.path.join(SPIKE_DIR, 'shots')
ROW = 'a.row span.tk'          # list/TickerRow.tsx
VIEWPORT = {'width': 1440, 'height': 900}


def mint_cookie(app, user_id):
    from flask.sessions import SecureCookieSessionInterface
    serializer = SecureCookieSessionInterface().get_signing_serializer(app)
    return serializer.dumps({'user_id': user_id})


def wait_for_server(url, timeout=90):
    began = time.perf_counter()
    while time.perf_counter() - began < timeout:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except Exception:                               # noqa: BLE001
            time.sleep(0.3)
    return False


def main():
    from app import app
    with app.app_context():
        from extensions import db
        from features.radar.routes.api import Query
        preflight(db, 'S8 step 3 -- a real browser')
        engine = db.engine
        sources = fixture_sources(db)
        src = ','.join(sources)
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        user_id = db.session.execute(sa.text(
            'SELECT id FROM app_user ORDER BY id LIMIT 1')).scalar()
        cookie = mint_cookie(app, user_id)
        print('minted a session cookie for user %d (no password used)'
              % user_id)
        os.makedirs(SHOTS, exist_ok=True)

        store.drop_table(engine)
        store.create_table(engine)

        warm = Query(sources=list(sources), segments=[], window=24, limit=50,
                     min_venues=1, market='us', sort=None, direction='desc')
        stale = Query(sources=list(sources), segments=[], window=12, limit=50,
                      min_venues=1, market='us', sort=None, direction='desc')
        cases = []
        for query, label in ((warm, 'warm'), (stale, 'stale')):
            key_hash, key_json = keys.canonical(query)
            store.enqueue(engine, key_hash, key_json, now, warm=True)
            producer.serve_once(engine, 'browser-setup', now,
                                key_hash=key_hash, query_cls=Query)
            assert store.read(engine, key_hash, now).state == 'ready'
            cases.append((label, query, key_hash))
        # Age the stale one past MAX_AGE.
        with engine.begin() as conn:
            conn.execute(sa.text(
                'UPDATE radar_board_results'
                ' SET as_of = as_of - INTERVAL :s SECOND WHERE key_hash = :k'),
                {'s': store.MAX_AGE + 120, 'k': cases[1][2]})
        print('warm key ready; stale key aged %ds past MAX_AGE=%ds'
              % (120, store.MAX_AGE))

    server = subprocess.Popen(
        [sys.executable, os.path.join(SPIKE_DIR, 'serve_store_app.py'),
         '--port', str(PORT)],
        cwd=APP_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        base = 'http://127.0.0.1:%d' % PORT
        assert wait_for_server(base + '/radar/'), 'server never came up'
        print('server up on %s' % base)
        results = measure(base, cookie, src)
    finally:
        server.kill()
        out, err = server.communicate()

    print('\n--- Step 3: time to a first contentful board ---')
    print('  %-10s %-38s %10s %10s %10s  %s'
          % ('case', 'url', 'response', 'rows in', 'age', 'what rendered'))
    for row in results:
        print('  %-10s %-38s %9.0fms %9s %10s  %s'
              % (row['case'], row['path'][:38], row['response_ms'],
                 ('%.0fms' % row['rows_ms']) if row['rows_ms'] else '--',
                 ('%.0fs' % row['age']) if row['age'] is not None else '--',
                 row['verdict']))
    print('\n  a `pending` render is reported as PENDING, not as a board.')
    print('  the browser target is 3000 ms to a usable board.')
    for row in results:
        if row['rows_ms']:
            verdict = 'MET' if row['rows_ms'] <= 3000 else 'MISSED'
            print('    %-10s %.0f ms -> %s' % (row['case'], row['rows_ms'],
                                               verdict))
        else:
            print('    %-10s no board rendered at all -> MISSED' % row['case'])
    print('  screenshots in radar-design/perf2-spike/shots/')


def measure(base, cookie, src):
    from playwright.sync_api import sync_playwright

    cases = [
        ('warm', '/radar/?window=24&segment=&market=us&sources=%s' % src),
        ('unwarmed', '/radar/?window=4&segment=&market=de&venues=2'
                     '&sort=ratio&sources=%s' % src),
        ('stale', '/radar/?window=12&segment=&market=us&sources=%s' % src),
    ]
    out = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport=VIEWPORT)
        context.add_cookies([{'name': 'session', 'value': cookie,
                              'domain': '127.0.0.1', 'path': '/'}])
        page = context.new_page()
        for label, path in cases:
            url = base + path
            began = time.perf_counter()
            response = page.goto(url, wait_until='commit')
            response_ms = (time.perf_counter() - began) * 1000
            assert response.status == 200, (label, response.status)
            rows_ms = None
            try:
                page.wait_for_selector(ROW, timeout=8000)
                rows_ms = (time.perf_counter() - began) * 1000
            except Exception:                           # noqa: BLE001
                pass
            payload = page.evaluate(
                "() => { const el = document.getElementById('radar-data');"
                " try { return el ? JSON.parse(el.textContent) : null; }"
                ' catch (e) { return null; } }')
            rows = page.locator(ROW).count()
            pending = bool(payload and payload.get('pending'))
            is_stale = bool(payload and payload.get('stale'))
            age = payload.get('age_seconds') if payload else None
            verdict = ('PENDING -- not a board' if pending
                       else 'STALE board, %d rows' % rows if is_stale
                       else 'board, %d rows' % rows)
            page.screenshot(path=os.path.join(SHOTS, 's8-%s.png' % label),
                            full_page=False)
            out.append({'case': label, 'path': path.split('&sources=')[0],
                        'response_ms': response_ms, 'rows_ms': rows_ms,
                        'rows': rows, 'pending': pending, 'stale': is_stale,
                        'age': age, 'verdict': verdict})
        browser.close()
    return out


if __name__ == '__main__':
    main()

"""The read path: `build_payload` with the build taken out of it.

Part I.4. A web worker only ever READS. There is no fallback branch that
builds -- not on a miss, not on a stale result, not on an exhausted retry.
That is the property Codex's ruling requires and the property the in-process
single-flight did not have.

STATE IS QUEUE STATE; THE PAYLOAD IS THE RESULT. The disposition below is
decided from the payload, its version and its real age, never from `state`,
so a key that is queued for refresh (`pending`) or that has been failing
(`failed`) keeps serving its last good board, truthfully marked stale.

Runnable as a subprocess, which is how Task S2 proves two independent OS
processes reuse one published result:

    python reader.py --now 2026-09-10T12:00:00 --window 24 --segments '' \
        --market us --user 1
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from env_check import bootstrap  # noqa: E402
bootstrap()

import keys                                            # noqa: E402
import store                                           # noqa: E402

# What the build path costs in the spike, for contrast only. Never called.
NEVER_BUILDS = True


def disposition(result, now):
    """(kind, age_seconds) from a stored row. Pure; no I/O.

    kind is one of: 'missing', 'ready', 'stale'.
    """
    if result is None or result.payload is None:
        return 'missing', None
    if result.payload_version != store.PAYLOAD_VERSION:
        # Deployment invalidation: the running code serializes a different
        # shape than the one stored.
        return 'missing', None
    age = (now - result.as_of).total_seconds()
    if age > store.HARD_MAX_AGE:
        # A board an hour old misdescribes a rolling window.
        return 'missing', age
    if age > store.MAX_AGE:
        return 'stale', age
    return 'ready', age


def read_payload(engine, args, now, user_id, *, parse=None, query_cls=None,
                 board_mod=None, api_mod=None, watch_mod=None):
    """The store's answer for one request. NEVER builds.

    Returns the serialized board with the freshness contract of Part I.5 on
    top of it, or a `pending`/`busy` envelope that is explicitly NOT a board.
    """
    if parse is None:
        from features.radar.routes.api import parse_query as parse
    if board_mod is None:
        from features.radar import board as board_mod
    if api_mod is None:
        from features.radar.routes import api as api_mod
    if watch_mod is None:
        from features.radar import watch as watch_mod

    query = parse(args, now=now)
    key_hash, key_json = keys.canonical(query)
    result = store.read(engine, key_hash, now)
    kind, age = disposition(result, now)

    if kind == 'missing':
        state = store.enqueue(engine, key_hash, key_json, now)
        return {'pending': state != 'busy',
                'busy': state == 'busy',
                'stale': False,
                'as_of': None, 'built_at': None, 'age_seconds': None,
                'max_age_seconds': store.MAX_AGE,
                'key_hash': key_hash,
                'rows': None}

    if kind == 'stale':
        # Served, marked stale, with its TRUE age -- and a refresh queued.
        store.enqueue(engine, key_hash, key_json, now)

    payload = json.loads(store.decompress(result.payload))
    payload['as_of'] = result.as_of.isoformat() + 'Z'
    payload['built_at'] = result.built_at.isoformat() + 'Z'
    payload['age_seconds'] = age
    payload['stale'] = kind == 'stale'
    payload['pending'] = False
    payload['busy'] = False
    payload['max_age_seconds'] = store.MAX_AGE
    payload['key_hash'] = key_hash

    # Per account, added on top, exactly as `build_payload` does today.
    watching = watch_mod.tickers_for(user_id) if user_id is not None else []
    payload['watching'] = watching
    payload['watch_rows'] = [
        api_mod._row(entry) for entry in board_mod.build_pinned_rows(
            watching, query.sources, now, window_hours=query.window,
            market=query.market)] if watching else []
    return payload


def digest(payload):
    """The response hashed, minus the fields that are read-time by design."""
    volatile = ('age_seconds', 'built_at', 'stale', 'pending', 'busy',
                'max_age_seconds', 'key_hash', 'as_of')
    stripped = {k: v for k, v in payload.items() if k not in volatile}
    return hashlib.sha256(json.dumps(stripped, sort_keys=True,
                                     default=str).encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--now', required=True)
    ap.add_argument('--window', default='24')
    ap.add_argument('--segments', default='')
    ap.add_argument('--market', default='us')
    ap.add_argument('--sources', default=None)
    ap.add_argument('--fixture-sources', action='store_true',
                    help="resolve `sources` from the fixture's own DISTINCT "
                         'source list -- see selections.py for why the root '
                         '`reddit` must not be used against this fixture')
    ap.add_argument('--limit', default=None)
    ap.add_argument('--venues', default=None)
    ap.add_argument('--sort', default=None)
    ap.add_argument('--dir', default=None)
    ap.add_argument('--user', type=int, default=None)
    ap.add_argument('--repeat', type=int, default=1)
    ap.add_argument('--at', default=None,
                    help='wall-clock ISO instant to start at (S2 step 4)')
    args = ap.parse_args()

    query_args = {'window': args.window, 'segment': args.segments,
                  'market': args.market}
    for name, value in (('sources', args.sources), ('limit', args.limit),
                        ('venues', args.venues), ('sort', args.sort),
                        ('dir', args.dir)):
        if value is not None:
            query_args[name] = value

    now = dt.datetime.fromisoformat(args.now)
    from app import app
    with app.app_context():
        from extensions import db
        engine = db.engine
        if args.fixture_sources:
            from env_check import fixture_sources
            query_args['sources'] = ','.join(fixture_sources(db))
        if args.at:
            target = dt.datetime.fromisoformat(args.at)
            while dt.datetime.now() < target:
                time.sleep(0.001)
        out = []
        for _ in range(args.repeat):
            wall = dt.datetime.now().isoformat()
            began = time.perf_counter()
            payload = read_payload(engine, query_args, now, args.user)
            took = time.perf_counter() - began
            out.append({'seconds': took, 'started_at': wall,
                        'pending': bool(payload.get('pending')),
                        'busy': bool(payload.get('busy')),
                        'stale': bool(payload.get('stale')),
                        'age_seconds': payload.get('age_seconds'),
                        'rows': (len(payload['rows'])
                                 if payload.get('rows') is not None else None),
                        'watching': payload.get('watching'),
                        'digest': (digest(payload)
                                   if payload.get('rows') is not None
                                   else None),
                        'key_hash': payload.get('key_hash')})
        print('RESULT ' + json.dumps(out), flush=True)


if __name__ == '__main__':
    main()

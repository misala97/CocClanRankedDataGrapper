"""The producer: claim under a fenced lease, build, publish atomically.

Part I.3. Concurrency 1. Runs OUTSIDE the web request path -- in the spike
that means its own OS process, started by the run_* scripts with
`subprocess.Popen`, because two threads in one process is precisely the shape
PERF1 had to retract.

Also runnable directly:

    python producer.py --owner p1 --now 2026-09-10T12:00:00 --loops 1
    python producer.py --owner p1 --now ... --warm        (queue the warm set)
"""
import argparse
import datetime as dt
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from env_check import bootstrap  # noqa: E402
bootstrap()

import keys                                            # noqa: E402
import selections                                      # noqa: E402
import store                                           # noqa: E402


def _app():
    from app import app
    return app


def build_and_serialize(query, now, *, board_mod=None, api_mod=None):
    """The board a producer publishes, and what it cost.

    This is `build_payload` with the per-account half removed: the same build,
    the same rooting of `board.sources`, the same `serialize`. The account's
    `watching` and `watch_rows` are added by the READER, per request, and
    never enter the stored blob (Part I.4, and Task S5 proves it).
    """
    if board_mod is None:
        from features.radar import board as board_mod
    if api_mod is None:
        from features.radar.routes import api as api_mod
    from features.radar.config import source_root

    began = time.perf_counter()
    board = board_mod.build(query.sources, now,
                            window_hours=query.window,
                            segments=query.segments, limit=query.limit,
                            min_venues=query.min_venues, market=query.market,
                            sort=query.sort, direction=query.direction)
    board.sources = sorted({source_root(s) for s in query.sources})
    payload = api_mod.serialize(board)
    build_ms = int(round((time.perf_counter() - began) * 1000))
    return payload, build_ms


def payload_bytes(payload):
    """The stored bytes. `default=str` matches what `perf1-bench` hashed and
    what Flask's encoder would do with anything left non-JSON-native."""
    return json.dumps(payload, sort_keys=True, default=str).encode('utf-8')


def serve_once(engine, owner, now, *, key_hash=None, query_cls=None,
               fail_with=None, pause_before_publish=0.0,
               revision=None):
    """Claim one key, build it, publish it. Returns the key, or None.

    `fail_with` and `pause_before_publish` exist for Task S6 and are not part
    of the design; nothing else passes them.
    """
    if query_cls is None:
        from features.radar.routes.api import Query as query_cls

    claim = store.claim(engine, owner, now, key_hash=key_hash)
    if claim is None:
        return None

    query = keys.query_from_json(claim.key_json, query_cls)
    try:
        if fail_with:
            raise RuntimeError(fail_with)
        as_of = now
        payload, build_ms = build_and_serialize(query, as_of)
        blob = store.compress(payload_bytes(payload))
    except Exception as exc:                            # noqa: BLE001
        store.fail(engine, claim, '%s: %s' % (type(exc).__name__, exc),
                   dt.datetime.utcnow())
        return claim.key_hash

    if pause_before_publish:
        time.sleep(pause_before_publish)

    published = store.publish(engine, claim, blob, as_of,
                              dt.datetime.utcnow(), build_ms,
                              producer_revision=revision)
    if not published:
        # Overtaken while we built. Their result is newer than ours.
        print('DISCARDED %s: fence %d no longer ours'
              % (claim.key_hash[:12], claim.fence), flush=True)
    return claim.key_hash


def sweep(engine, owner, now, queries, *, verbose=True):
    """Queue the warm set and build every one of it, concurrency 1.

    Returns [(label, key_hash, build_ms)] and the wall seconds of the sweep.
    """
    from features.radar.routes.api import Query
    for query in queries:
        key_hash, key_json = keys.canonical(query)
        store.enqueue(engine, key_hash, key_json, now, warm=True)

    built = []
    began = time.perf_counter()
    while True:
        before = time.perf_counter()
        key_hash = serve_once(engine, owner, now, query_cls=Query)
        if key_hash is None:
            break
        took = time.perf_counter() - before
        result = store.read(engine, key_hash, now)
        built.append((key_hash, result.build_ms, took))
        if verbose:
            print('    %s  build %6d ms   claim+publish %6.0f ms'
                  % (key_hash[:12], result.build_ms or -1, took * 1000),
                  flush=True)
    return built, time.perf_counter() - began


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--owner', default='producer')
    ap.add_argument('--now', required=True)
    ap.add_argument('--loops', type=int, default=1)
    ap.add_argument('--warm', action='store_true')
    ap.add_argument('--key')
    ap.add_argument('--fail-with')
    ap.add_argument('--pause-before-publish', type=float, default=0.0)
    ap.add_argument('--hang', type=float, default=0.0,
                    help='sleep after claiming, before building (S6)')
    ap.add_argument('--poll', type=float, default=0.0,
                    help='run as a daemon loop for this many seconds, '
                         'claiming whatever is queued -- the shape the real '
                         'producer has, and the shape that keeps process '
                         'startup out of the enqueue-to-ready measurement')
    ap.add_argument('--poll-interval', type=float, default=0.25)
    args = ap.parse_args()

    now = dt.datetime.fromisoformat(args.now)
    app = _app()
    with app.app_context():
        from extensions import db
        from features.radar.routes.api import Query
        engine = db.engine

        if args.warm:
            from env_check import fixture_sources
            sources = fixture_sources(db)
            for query in selections.warm_set(Query, sources):
                key_hash, key_json = keys.canonical(query)
                store.enqueue(engine, key_hash, key_json, now, warm=True)
            print('warm set queued', flush=True)

        if args.poll:
            # READY is printed once the app and the pool are up, so the
            # caller can enqueue AFTER startup and measure only the queue
            # latency plus the build.
            print('READY', flush=True)
            until = time.perf_counter() + args.poll
            while time.perf_counter() < until:
                key_hash = serve_once(engine, args.owner, now,
                                      query_cls=Query,
                                      fail_with=args.fail_with,
                                      pause_before_publish=(
                                          args.pause_before_publish))
                if key_hash is None:
                    time.sleep(args.poll_interval)
                else:
                    print('SERVED %s' % key_hash, flush=True)
            return

        if args.hang:
            claim = store.claim(engine, args.owner, now, key_hash=args.key)
            print('CLAIMED %s fence %d' % (claim.key_hash[:12], claim.fence),
                  flush=True)
            time.sleep(args.hang)
            return

        for _ in range(max(args.loops, 0)):
            key_hash = serve_once(engine, args.owner, now, key_hash=args.key,
                                  query_cls=Query, fail_with=args.fail_with,
                                  pause_before_publish=args.pause_before_publish)
            if key_hash is None:
                print('nothing claimable', flush=True)
                break
            print('SERVED %s' % key_hash, flush=True)


if __name__ == '__main__':
    main()

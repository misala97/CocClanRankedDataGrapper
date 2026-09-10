"""Task S1: the store exists, and a board payload is weighed.

Steps 2, 3 and 4 of Task S1. Step 1 is `store.py` and `keys.py` themselves,
and this script proves them by round-tripping a real payload through the
table: create, enqueue, claim, build, publish, read back, decompress, compare.

Run from `personal_apps/`:
    python ../radar-design/perf2-spike/run_s1_payload.py
"""
import datetime as dt
import json
import os
import statistics
import sys
import time
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from env_check import bootstrap  # noqa: E402
bootstrap()

import keys                                            # noqa: E402
import producer                                        # noqa: E402
import selections                                      # noqa: E402
import store                                           # noqa: E402
from env_check import fixture_sources, preflight       # noqa: E402


def weigh(payload):
    raw = producer.payload_bytes(payload)
    began = time.perf_counter()
    blob = zlib.compress(raw, store.COMPRESS_LEVEL)
    comp_ms = (time.perf_counter() - began) * 1000
    began = time.perf_counter()
    back = zlib.decompress(blob)
    decomp_ms = (time.perf_counter() - began) * 1000
    assert back == raw
    began = time.perf_counter()
    json.loads(back)
    parse_ms = (time.perf_counter() - began) * 1000
    return len(raw), len(blob), comp_ms, decomp_ms, parse_ms


def main():
    from app import app
    with app.app_context():
        from extensions import db
        from features.radar import llm_sentiment, market_data, spend
        from features.radar.routes.api import Query
        preflight(db, 'S1 -- the store, and what a payload weighs')
        engine = db.engine
        sources = fixture_sources(db)
        now = selections.fixed_now()
        print('fixed now: %s' % now.isoformat())
        print('sources:   %d fixture names, rooted to %s'
              % (len(sources), sorted({s.split(':')[0] for s in sources})))

        # ---- Step 1 proven by round-trip ---------------------------------
        store.drop_table(engine)
        store.create_table(engine)
        print('\n--- Step 1: the table and the key ---')
        probe = Query(sources=list(sources), segments=[], window=24, limit=50,
                      min_venues=1, market='us', sort=None, direction='desc')
        key_hash, key_json = keys.canonical(probe)
        print('key_hash: %s' % key_hash)
        print('key_json: %d chars (column is VARCHAR(2048))' % len(key_json))

        # The WORST CASE key_json against production's real source names, not
        # the fixture's short placeholders. Part I.2 specified VARCHAR(1024).
        from features.radar.config import REDDIT_SUBS, SOURCES
        worst = Query(sources=list(SOURCES) + ['reddit:%s' % s
                                               for s in REDDIT_SUBS],
                      segments=list(('large', 'mid', 'micro', 'unknown',
                                     'recent_ipo', 'fund', 'discover',
                                     'small')),
                      window=24, limit=100, min_venues=2, market='us',
                      sort='divergence', direction='asc')
        _, worst_json = keys.canonical(worst)
        print('worst-case key_json, PRODUCTION source names: %d chars'
              % len(worst_json))
        if len(worst_json) > 1024:
            print('  >>> Part I.2 says VARCHAR(1024). It does not fit.'
                  ' Widened to VARCHAR(2048) in store.py.')
        else:
            print('  fits VARCHAR(1024) with %d chars to spare'
                  % (1024 - len(worst_json)))

        state = store.enqueue(engine, key_hash, key_json, now)
        assert state == 'pending', state
        claim = store.claim(engine, 's1', now)
        assert claim is not None and claim.key_hash == key_hash
        assert claim.fence == 1, claim.fence
        payload, build_ms = producer.build_and_serialize(probe, now)
        blob = store.compress(producer.payload_bytes(payload))
        assert store.publish(engine, claim, blob, now, dt.datetime.utcnow(),
                             build_ms)
        back = store.read(engine, key_hash, now)
        assert back.state == 'ready'
        assert json.loads(store.decompress(back.payload)) == json.loads(
            producer.payload_bytes(payload))
        print('round-trip: enqueue -> claim(fence 1) -> build %d ms ->'
              ' publish -> read -> decompress: IDENTICAL' % build_ms)

        # ---- Step 2: measure payloads ------------------------------------
        print('\n--- Step 2: what a payload weighs ---')
        print('%-34s %10s %10s %6s %8s %8s %8s'
              % ('selection', 'json B', 'zlib6 B', 'ratio', 'comp ms',
                 'dec ms', 'parse ms'))
        cases = []
        for window in (1, 4, 12, 24):
            cases.append(('%dh All companies US' % window,
                          Query(sources=list(sources), segments=[],
                                window=window, limit=50, min_venues=1,
                                market='us', sort=None, direction='desc')))
        cases.append(('24h default 4 segments US',
                      Query(sources=list(sources),
                            segments=['discover', 'mid', 'micro', 'unknown'],
                            window=24, limit=50, min_venues=1, market='us',
                            sort=None, direction='desc')))
        cases.append(('24h All companies US limit=100',
                      Query(sources=list(sources), segments=[], window=24,
                            limit=100, min_venues=1, market='us', sort=None,
                            direction='desc')))
        # Each selection is built TWICE. The first pass pays for pages this
        # process has not touched yet and is reported separately rather than
        # averaged in -- PERF1's whole retraction was a warm/cold confusion.
        weights = []
        for label, query in cases:
            payload, first_ms = producer.build_and_serialize(query, now)
            payload, second_ms = producer.build_and_serialize(query, now)
            raw, comp, cms, dms, pms = weigh(payload)
            weights.append((label, raw, comp, first_ms, second_ms,
                            len(payload['rows'])))
            print('%-34s %10s %10s %5.1fx %8.1f %8.1f %8.1f'
                  % (label, format(raw, ','), format(comp, ','), raw / comp,
                     cms, dms, pms))
        print('\n  build cost, first pass vs second in the same process:')
        for label, raw, comp, first_ms, second_ms, rows in weights:
            print('  %-34s %6d ms -> %6d ms, %d rows'
                  % (label, first_ms, second_ms, rows))

        # ---- Step 3: what serialize costs beyond the board ---------------
        print('\n--- Step 3: the three ops summaries inside serialize ---')
        # market_data.ops_summary carries its OWN 60-second memo keyed on
        # `now`. With `now` fixed, timing it repeatedly measures a dict
        # lookup, so the memo is cleared before every sample; the memoised
        # cost is reported beside it because that is what a second reader in
        # the same process actually pays.
        def sample(call, clear=None):
            took = []
            value = None
            for _ in range(7):
                if clear:
                    clear()
                began = time.perf_counter()
                value = call()
                took.append((time.perf_counter() - began) * 1000)
            return value, took

        probes = (('spend.summary()', lambda: spend.summary(), None),
                  ('llm_sentiment.ops_summary()',
                   lambda: llm_sentiment.ops_summary(), None),
                  ('market_data.ops_summary(now)',
                   lambda: market_data.ops_summary(now),
                   market_data.clear_ops_memo))
        total = 0.0
        for name, call, clear in probes:
            value, took = sample(call, clear)
            body = json.dumps(value, default=str)
            total += statistics.median(took)
            print('  %-30s median %7.1f ms   min %7.1f   max %7.1f'
                  '   %d bytes%s'
                  % (name, statistics.median(took), min(took), max(took),
                     len(body), '   (memo cleared each sample)' if clear
                     else ''))
        _, memoised = sample(lambda: market_data.ops_summary(now))
        print('  %-30s median %7.1f ms   (its own 60 s memo, hit)'
              % ('market_data, memo hit', statistics.median(memoised)))
        print('  the three together: %.1f ms per serialize' % total)

        # ---- Step 4: the storage bound -----------------------------------
        print('\n--- Step 4: the storage bound ---')
        biggest = max(comp for _, _, comp, _, _, _ in weights)
        warm_n = len(selections.warm_set(Query, sources))
        total = (warm_n + store.MAX_ON_DEMAND_KEYS) * biggest
        print('  largest measured compressed payload: %s bytes'
              % format(biggest, ','))
        print('  warm keys %d + MAX_ON_DEMAND_KEYS %d = %d rows'
              % (warm_n, store.MAX_ON_DEMAND_KEYS,
                 warm_n + store.MAX_ON_DEMAND_KEYS))
        print('  storage bound: %.1f MB' % (total / 1048576.0))
        print('\nS1 done. The table is left in place for S2.')


if __name__ == '__main__':
    main()

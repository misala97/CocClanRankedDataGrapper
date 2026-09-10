"""Task S8 steps 1 and 2: rapid filter switching through the store.

The seven selections are `perf1-bench/acceptance.py`'s `churn` list, unchanged,
so the two numbers this reports are comparable with the two PERF1 reported for
the deployed synchronous path: **34.54 s total, 5.41 s worst single**.

Four of the seven are in the warm set of Part I.6 and three are not, which is
what makes step 2 the honest case rather than a second best case.

Run from `personal_apps/`:
    python ../radar-design/perf2-spike/run_s8_switching.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from env_check import bootstrap  # noqa: E402
bootstrap()

import keys                                            # noqa: E402
import producer                                        # noqa: E402
import reader                                          # noqa: E402
import selections                                      # noqa: E402
import store                                           # noqa: E402
from env_check import fixture_sources, preflight       # noqa: E402

PERF1_TOTAL = 34.54
PERF1_WORST = 5.41


def churn_steps(src):
    """acceptance.py's churn list, as request dictionaries."""
    base = {'segment': '', 'market': 'us', 'sources': src}
    return [
        ('24h all', dict(base, window='24')),
        # CORRECTION to acceptance.py's list. It spelled this step
        # `sort='mention_z'` and passed it straight into `board_mod.build`,
        # bypassing `parse_query`. `mention_z` is not in `board.SORT_KEYS`,
        # and `sort_rows` returns the list unchanged for a key it does not
        # know -- so PERF1's second churn step built the SAME board as its
        # first, and the API would answer that URL with a 400. `divergence`
        # is a real sort key and a genuinely different board.
        ('24h by divergence', dict(base, window='24', sort='divergence')),
        ('12h all', dict(base, window='12')),
        ('12h discover', dict(base, window='12', segment='discover')),
        ('24h all, German board', dict(base, window='24', market='de')),
        ('4h all', dict(base, window='4')),
        ('24h venues>=2', dict(base, window='24', venues='2')),
    ]


def main():
    from app import app
    with app.app_context():
        from extensions import db
        from features.radar.routes import api as api_mod
        from features.radar.routes.api import Query
        preflight(db, 'S8 -- rapid filter switching through the store')
        engine = db.engine
        sources = fixture_sources(db)
        src = ','.join(sources)
        now = selections.fixed_now()
        steps = churn_steps(src)

        warm_hashes = set()
        for query in selections.warm_set(Query, sources):
            warm_hashes.add(keys.canonical(query)[0])
        print('warm set: %d keys' % len(warm_hashes))
        in_warm = []
        for label, request in steps:
            key_hash = keys.canonical(
                api_mod.parse_query(dict(request), now=now))[0]
            in_warm.append(key_hash in warm_hashes)
        print('of the seven churn selections, %d are in the warm set and'
              ' %d are not' % (sum(in_warm), len(in_warm) - sum(in_warm)))

        def run(label):
            began = time.perf_counter()
            worst = 0.0
            pendings = 0
            for (name, request), warm in zip(steps, in_warm):
                t0 = time.perf_counter()
                served = reader.read_payload(engine, dict(request), now, None)
                took = time.perf_counter() - t0
                worst = max(worst, took)
                if served['pending']:
                    pendings += 1
                print('    %-22s %7.1f ms   %s%s'
                      % (name, took * 1000,
                         'PENDING -- not a board' if served['pending']
                         else '%d rows' % len(served['rows']),
                         '' if warm else '   (unwarmed)'))
            total = time.perf_counter() - began
            print('  %s: %.2f s total, %.2f s worst single, %d of 7 were'
                  ' `pending`' % (label, total, worst, pendings))
            return total, worst, pendings

        # ---- Step 1: everything warm -------------------------------------
        print('\n--- Step 1: all seven selections already in the store ---')
        store.drop_table(engine)
        store.create_table(engine)
        for label, request in steps:
            query = api_mod.parse_query(dict(request), now=now)
            key_hash, key_json = keys.canonical(query)
            store.enqueue(engine, key_hash, key_json, now, warm=True)
            producer.serve_once(engine, 'setup', now, key_hash=key_hash,
                                query_cls=Query)
        warm_total, warm_worst, warm_pending = run('ALL WARM')
        assert warm_pending == 0

        # ---- Step 2: the honest case -------------------------------------
        print('\n--- Step 2: only the warm set is warm ---')
        store.drop_table(engine)
        store.create_table(engine)
        for (label, request), warm in zip(steps, in_warm):
            if not warm:
                continue
            query = api_mod.parse_query(dict(request), now=now)
            key_hash, key_json = keys.canonical(query)
            store.enqueue(engine, key_hash, key_json, now, warm=True)
            producer.serve_once(engine, 'setup', now, key_hash=key_hash,
                                query_cls=Query)
        honest_total, honest_worst, honest_pending = run('HONEST')
        assert honest_pending == len(in_warm) - sum(in_warm)

        # ...and what it costs to actually SEE those three boards.
        print('\n  the three `pending` answers are not boards. What it costs'
              ' to turn them into boards, one producer at concurrency 1:')
        began = time.perf_counter()
        built = 0
        while True:
            key_hash = producer.serve_once(engine, 'catchup', now,
                                           query_cls=Query)
            if key_hash is None:
                break
            built += 1
        catchup = time.perf_counter() - began
        print('    %d builds, %.2f s' % (built, catchup))
        began = time.perf_counter()
        for name, request in steps:
            served = reader.read_payload(engine, dict(request), now, None)
            assert served['rows'], name
        reread = time.perf_counter() - began
        print('    re-reading all seven as boards: %.2f s' % reread)
        print('    HONEST END TO END, first request to seven boards: %.2f s'
              % (honest_total + catchup + reread))

        # ---- The comparison ----------------------------------------------
        print('\n--- against PERF1 on the deployed synchronous path ---')
        print('  %-46s %8s %8s' % ('', 'total', 'worst'))
        print('  %-46s %7.2fs %7.2fs'
              % ('PERF1, deployed code, every selection built', PERF1_TOTAL,
                 PERF1_WORST))
        print('  %-46s %7.2fs %7.2fs'
              % ('store, all seven warm', warm_total, warm_worst))
        print('  %-46s %7.2fs %7.2fs'
              % ('store, three unwarmed (3 of 7 are `pending`)',
                 honest_total, honest_worst))
        print('  %-46s %7.2fs %7s'
              % ('store, three unwarmed, until all seven are BOARDS',
                 honest_total + catchup + reread, '--'))
        print('\n  the 100 ms local-interaction target applies to sort and'
              ' mode changes the client can do without a new server result;'
              ' every row above is a new server result.')


if __name__ == '__main__':
    main()

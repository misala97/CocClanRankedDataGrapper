"""Task S4: the semantics do not move.

Everything here runs at ONE fixed `now`. A moving `now` makes parity
untestable: `board.build` uses `now - timedelta(hours=window)` unfloored, so
two builds a second apart read two different windows.

Step 0 is not in the plan and had to be added: before the store can be
compared against a direct build, the direct build has to be compared against
ITSELF, because `serialize` embeds three health blocks and one of them reads
the wall clock rather than the board's `now`.

Run from `personal_apps/`:
    python ../radar-design/perf2-spike/run_s4_parity.py
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from env_check import bootstrap  # noqa: E402
bootstrap()

import keys                                            # noqa: E402
import producer                                        # noqa: E402
import reader                                          # noqa: E402
import selections                                      # noqa: E402
import store                                           # noqa: E402
from env_check import fixture_sources, preflight       # noqa: E402

# Added at read time by the freshness contract; not part of the board.
READ_TIME = ('as_of', 'built_at', 'age_seconds', 'stale', 'pending', 'busy',
             'max_age_seconds', 'key_hash')
# The three health blocks `serialize` embeds. Step 0 rules on these.
OPS = ('spend', 'sentiment_ops', 'market_data_ops')


def sha(payload, drop=()):
    body = {k: v for k, v in payload.items() if k not in drop}
    return hashlib.sha256(json.dumps(body, sort_keys=True,
                                     default=str).encode()).hexdigest()


def differing_keys(left, right):
    return sorted(k for k in set(left) | set(right)
                  if left.get(k, '<<absent>>') != right.get(k, '<<absent>>'))


def main():
    from app import app
    with app.app_context():
        from extensions import db
        from features.radar.routes.api import Query, build_payload
        preflight(db, 'S4 -- the semantics do not move')
        engine = db.engine
        sources = fixture_sources(db)
        src = ','.join(sources)
        now = selections.fixed_now()
        print('Step 1: `now` is pinned at %s for every comparison below.'
              % now.isoformat())
        store.drop_table(engine)
        store.create_table(engine)

        # ---- Step 0: is a direct build even deterministic? ---------------
        print('\n--- Step 0 (added): two direct builds of ONE selection ---')
        args = {'window': '24', 'segment': '', 'market': 'us', 'sources': src}
        first = build_payload(dict(args), now=now, user_id=None)
        # Defeat api.board_cache so the second build is a real second build.
        from features.radar.routes import api as api_mod
        api_mod.board_cache.clear()
        from features.radar import market_data
        market_data.clear_ops_memo()
        second = build_payload(dict(args), now=now, user_id=None)
        drifted = differing_keys(first, second)
        if drifted:
            print('  TWO IDENTICAL REQUESTS AT ONE `now` DIFFER IN: %s'
                  % ', '.join(drifted))
            for field in drifted:
                print('    %-18s %s' % (field, json.dumps(
                    first.get(field), default=str)[:110]))
                print('    %-18s %s' % ('', json.dumps(
                    second.get(field), default=str)[:110]))
        else:
            print('  identical ON THIS FIXTURE -- but see the probe below')
        print('  board digest ignoring the ops blocks: %s vs %s -> %s'
              % (sha(first, OPS)[:16], sha(second, OPS)[:16],
                 'SAME' if sha(first, OPS) == sha(second, OPS)
                 else 'DIFFERENT'))

        # Why "on this fixture" and not "deterministic". `serialize` calls
        # `llm_sentiment.ops_summary()` with NO argument, so it uses the wall
        # clock rather than the board's `now`, and derives
        # `p95_age_minutes` from it. That field moves between two builds of
        # the same board wherever a backlog exists.
        from features.radar import llm_sentiment
        ops_a = llm_sentiment.ops_summary()
        ops_b = llm_sentiment.ops_summary()
        print('  probe: llm_sentiment.ops_summary() reads the WALL CLOCK,'
              ' not the board\'s now')
        print('    pending backlog on this fixture: %s   p95_age_minutes: %s'
              % (ops_a['pending'], ops_a['p95_age_minutes']))
        print('    two calls agree here: %s%s'
              % (ops_a == ops_b,
                 '   (because the backlog is empty, so p95 is None --'
                 ' on a box with a backlog it would not be)'
                 if ops_a['pending'] == 0 else ''))

        # ---- Step 2: store against direct build, twelve selections -------
        print('\n--- Step 2: the store against a direct build ---')
        cases = [
            ('12h All US', {'window': '12', 'segment': '', 'market': 'us'}),
            ('24h All US', {'window': '24', 'segment': '', 'market': 'us'}),
            ('24h All DE', {'window': '24', 'segment': '', 'market': 'de'}),
            ('12h default segments US',
             {'window': '12', 'segment': 'discover,mid,micro,unknown',
              'market': 'us'}),
            ('1h All US', {'window': '1', 'segment': '', 'market': 'us'}),
            ('4h All US', {'window': '4', 'segment': '', 'market': 'us'}),
            ('24h venues=2 US',
             {'window': '24', 'segment': '', 'market': 'us', 'venues': '2'}),
            ('24h limit=100 US',
             {'window': '24', 'segment': '', 'market': 'us', 'limit': '100'}),
            ('24h sort=lean desc US',
             {'window': '24', 'segment': '', 'market': 'us', 'sort': 'lean',
              'dir': 'desc'}),
            ('24h sort=mentions asc US',
             {'window': '24', 'segment': '', 'market': 'us',
              'sort': 'mentions', 'dir': 'asc'}),
            ('sources=reddit 24h US',
             {'window': '24', 'segment': '', 'market': 'us',
              'sources': 'reddit'}),
            ('sources=reddit:wallstreetbets 24h US',
             {'window': '24', 'segment': '', 'market': 'us',
              'sources': 'reddit:wallstreetbets'}),
        ]
        print('  %-38s %-18s %-18s %s'
              % ('selection', 'direct', 'through store', 'verdict'))
        failures = []
        full_agree = []
        row_order = {}
        for label, raw in cases:
            request = dict(raw)
            request.setdefault('sources', src)
            api_mod.board_cache.clear()
            direct = build_payload(dict(request), now=now, user_id=None)
            query = api_mod.parse_query(dict(request), now=now)
            key_hash, key_json = keys.canonical(query)
            store.enqueue(engine, key_hash, key_json, now)
            produced = producer.serve_once(engine, 's4', now,
                                           key_hash=key_hash,
                                           query_cls=Query)
            assert produced == key_hash, produced
            served = reader.read_payload(engine, dict(request), now, None)
            assert not served.get('pending'), 'the store answered pending'
            a, b = sha(direct, OPS), sha(served, READ_TIME + OPS)
            same = a == b
            # The FULL payload, ops blocks included, reported beside it: on
            # this fixture they agree too, and saying so is stronger than
            # only reporting the narrowed comparison.
            full_same = sha(direct) == sha(served, READ_TIME)
            full_agree.append(full_same)
            if not same:
                failures.append((label, differing_keys(
                    {k: v for k, v in direct.items() if k not in OPS},
                    {k: v for k, v in served.items()
                     if k not in READ_TIME + OPS})))
            row_order[label] = ([r['ticker'] for r in direct['rows']],
                                [r['ticker'] for r in served['rows']],
                                served['venue_counts']['any'])
            print('  %-38s %-18s %-18s %s   %d rows'
                  % (label, a[:16], b[:16], 'IDENTICAL' if same else 'DIFFERS',
                     len(served['rows'])))
        if failures:
            print('\n  PARITY FAILURES:')
            for label, fields in failures:
                print('    %-38s differs in: %s' % (label, ', '.join(fields)))
        else:
            print('\n  ALL TWELVE IDENTICAL (ops blocks excluded per Step 0)')
        print('  the FULL payload, the three ops blocks included, also agrees'
              ' in %d of %d cases on this fixture'
              % (sum(full_agree), len(full_agree)))

        # ---- Step 3: rule on each normalization candidate ----------------
        print('\n--- Step 3: the normalization candidates, ruled by digest ---')
        base = {'window': '24', 'segment': 'mid,micro', 'market': 'us',
                'sources': src}

        def payload_for(request):
            api_mod.board_cache.clear()
            return build_payload(dict(request), now=now, user_id=None)

        dup_sources = ','.join(list(sources) + [sources[0]])
        candidates = [
            ('dedupe `sources`',
             dict(base, sources=dup_sources), dict(base, sources=src)),
            ('sort `sources`',
             dict(base, sources=','.join(reversed(sources))),
             dict(base, sources=src)),
            ('dedupe `segments`',
             dict(base, segment='mid,micro,mid'), dict(base, segment='mid,micro')),
            ('sort `segments`',
             dict(base, segment='micro,mid'), dict(base, segment='mid,micro')),
            ("force dir='desc' when sort is None",
             dict(base, dir='asc'), dict(base, dir='desc')),
        ]
        print('  %-36s %-10s %s' % ('candidate', 'verdict', 'what differs'))
        verdicts = {}
        for label, left_req, right_req in candidates:
            left, right = payload_for(left_req), payload_for(right_req)
            fields = differing_keys(
                {k: v for k, v in left.items() if k not in OPS},
                {k: v for k, v in right.items() if k not in OPS})
            adopt = not fields
            verdicts[label] = adopt
            print('  %-36s %-10s %s'
                  % (label, 'ADOPT' if adopt else 'REJECT',
                     ', '.join(fields) if fields else '-- byte-identical'))

        # ---- Step 4: sort before limit -----------------------------------
        print('\n--- Step 4: sort before limit, at limit=50 ---')
        direct_rows, store_rows, candidates_n = row_order[
            '24h sort=lean desc US']
        assert direct_rows == store_rows, 'ORDER MOVED THROUGH THE STORE'
        print('  sort=lean limit=50: %d rows, IDENTICAL ORDER through the'
              ' store' % len(store_rows))
        print('  first five: %s' % ', '.join(store_rows[:5]))
        unsorted_rows, _, _ = row_order['24h All US']
        overlap = len(set(store_rows) & set(unsorted_rows))
        print('  candidates before the limit on this fixture: %d, limit 50'
              ' -- so only %d rows can be swapped in or out by a sort'
              % (candidates_n, candidates_n - 50))
        print('  membership: %d of 50 shared with the default top 50'
              % overlap)

        # NEGATIVE RESULT, recorded rather than asserted past. On this
        # fixture the lean sort cannot reorder anything: nothing has been
        # judged, so every row's tone is empty, `_lean_value` returns None
        # for all of them, they all sort to the same bucket and Python's
        # stable sort leaves the default ranking exactly as it was.
        lean_moved = store_rows != unsorted_rows
        toned = sum(1 for r in served['rows']
                    if (r['tone']['bullish'] + r['tone']['neutral']
                        + r['tone']['bearish']) > 0)
        print('  lean sort reordered anything: %s' % lean_moved)
        if not lean_moved:
            print('    WHY: %d of %d rows carry any tone at all on this'
                  ' fixture, so every lean is None and a stable sort is a'
                  ' no-op. THE LEAN CASE CANNOT TEST SORT-BEFORE-LIMIT HERE.'
                  % (toned, len(served['rows'])))

        # So the contract is proven on a sort this fixture CAN move.
        for probe_label in ('24h sort=mentions asc US',):
            probe_direct, probe_store, probe_candidates = row_order[
                probe_label]
            assert probe_direct == probe_store, 'ORDER MOVED THROUGH STORE'
            moved = probe_store != unsorted_rows
            swapped = 50 - len(set(probe_store) & set(unsorted_rows))
            print('  %s: order differs from default: %s, membership differs'
                  ' by %d of 50 rows (from %d candidates)'
                  % (probe_label, moved, swapped, probe_candidates))
            assert moved, 'this sort did not move either'
            print('    -> the sort reordered the WHOLE candidate pool and'
                  ' THEN cut it. A limit applied first could not change'
                  ' membership at all, and it changed by %d.' % swapped)

        # TEETH. An order assertion that would pass on a shuffled list is not
        # an assertion. Put the defect in and confirm it fails.
        mutated = list(store_rows)
        mutated[0], mutated[1] = mutated[1], mutated[0]
        caught = mutated != direct_rows
        print('  mutation check: swap the top two rows of the stored board ->'
              ' the assertion %s' % ('FAILS, as it must' if caught
                                     else 'STILL PASSES -- it has no teeth'))
        assert caught
        # And the same for a set-only comparison, which is what a weaker
        # test would have used: it does NOT catch the swap.
        print('  a set comparison would NOT catch that swap: %s'
              % (set(mutated) == set(direct_rows)))

        print('\nS4 done.')
        return not failures


if __name__ == '__main__':
    sys.exit(0 if main() else 1)

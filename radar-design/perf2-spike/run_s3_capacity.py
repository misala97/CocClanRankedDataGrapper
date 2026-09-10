"""Task S3: can one producer at concurrency 1 keep sixteen keys fresh.

The producer sweeps in-process here, deliberately: the real producer is a
long-lived loop, so its module-level memos (notably `market_data`'s 60-second
ops memo, measured at 91 ms in S1) are warm between builds exactly as they are
here. Spawning a fresh interpreter per key would measure interpreter start.

`now` ADVANCES with the sweep rather than being pinned, because a producer
builds at the instant it builds and the rolling window has to slide with it.
Parity is S4's job and it pins `now` there.

Run from `personal_apps/`:
    python ../radar-design/perf2-spike/run_s3_capacity.py
"""
import datetime as dt
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from env_check import bootstrap  # noqa: E402
bootstrap()

import keys                                            # noqa: E402
import producer                                        # noqa: E402
import selections                                      # noqa: E402
import store                                           # noqa: E402
from env_check import fixture_sources, preflight       # noqa: E402

SWEEPS = 4                  # one cold sweep for Step 1, three more for Step 2
MARGIN = 1.30               # a cadence with no margin is a cadence that slips


def sweep(engine, queries, labels, now, query_cls):
    """One pass over the warm set, concurrency 1. Returns per-key results.

    `now` ADVANCES PER KEY, not per sweep. That is what a real producer does
    -- it takes `utcnow()` when it claims -- and it is the difference between
    a warm key whose worst age is the cadence plus a few seconds of drift and
    one whose worst age is the cadence plus the whole sweep. Pinning `now` for
    a whole sweep would publish the last key of the sweep already a minute
    stale, and the spike measured that difference rather than assuming it.
    """
    for query in queries:
        key_hash, key_json = keys.canonical(query)
        store.enqueue(engine, key_hash, key_json, now, warm=True)
    built = []
    began = time.perf_counter()
    while True:
        offset = time.perf_counter() - began
        key_now = now + dt.timedelta(seconds=offset)
        key_hash = producer.serve_once(engine, 'sweeper', key_now,
                                       query_cls=query_cls)
        if key_hash is None:
            break
        row = store.read(engine, key_hash, key_now)
        built.append((labels[key_hash], row.build_ms,
                      time.perf_counter() - began, row.as_of))
    return built, time.perf_counter() - began


def main():
    from app import app
    with app.app_context():
        from extensions import db
        from features.radar.routes.api import Query
        preflight(db, 'S3 -- can one producer keep sixteen keys fresh')
        engine = db.engine
        sources = fixture_sources(db)
        base = selections.fixed_now()

        warm = selections.warm_set(Query, sources)
        labels = {}
        for query in warm:
            key_hash, _ = keys.canonical(query)
            labels[key_hash] = selections.label(query)
        print('warm set: %d keys' % len(warm))

        store.drop_table(engine)
        store.create_table(engine)

        totals = []
        per_key = {}
        as_ofs = {}
        for index in range(SWEEPS):
            now = base + dt.timedelta(seconds=int(sum(totals)))
            tag = 'COLD (Step 1)' if index == 0 else 'sweep %d' % index
            print('\n--- %s, now=%s ---' % (tag, now.isoformat()))
            built, total = sweep(engine, warm, labels, now, Query)
            assert len(built) == len(warm), (
                'sweep built %d of %d keys' % (len(built), len(warm)))
            for label, build_ms, offset, as_of in built:
                print('  %-42s %6d ms   done at +%6.1f s   as_of %s'
                      % (label, build_ms, offset, as_of.time()))
                per_key.setdefault(label, []).append(build_ms)
                as_ofs.setdefault(label, []).append((offset, as_of))
            print('  SWEEP TOTAL: %.1f s   (%d keys, concurrency 1)'
                  % (total, len(built)))
            totals.append(total)

        cold, warm_sweeps = totals[0], totals[1:]
        median_sweep = statistics.median(warm_sweeps)
        print('\n--- Step 2: three warm sweeps ---')
        print('  cold first sweep : %.1f s' % cold)
        print('  warm sweeps      : %s'
              % ', '.join('%.1f s' % t for t in warm_sweeps))
        print('  MEDIAN SWEEP     : %.1f s' % median_sweep)
        print('  worst sweep      : %.1f s' % max(warm_sweeps))
        print('  per-key build, median across the warm sweeps:')
        for label in sorted(per_key):
            samples = per_key[label][1:]
            print('    %-42s %6d ms  (cold first pass %6d ms)'
                  % (label, statistics.median(samples), per_key[label][0]))

        print('\n--- Step 3: the sustainable cadence ---')
        worst = max(warm_sweeps)
        needed = worst * MARGIN
        print('  a sweep must FINISH inside the cadence, with margin.')
        print('  worst warm sweep %.1f s x %.2f margin = %.1f s needed'
              % (worst, MARGIN, needed))
        cadence = int(30 * round((needed + 29) / 30))
        cadence = max(cadence, 30)
        print('  SUSTAINABLE REFRESH_EVERY: %d s' % cadence)
        print('  duty cycle at %d s: %.0f%% of one producer process'
              % (cadence, 100.0 * median_sweep / cadence))
        fits_120 = needed <= 120
        print('  does the proposed 120 s fit?  %s'
              % ('YES' if fits_120 else 'NO'))
        if not fits_120:
            # How many keys WOULD fit in 120 s with the same margin.
            ordered = sorted(
                (statistics.median(per_key[label][1:]) / 1000.0, label)
                for label in per_key)
            budget = 120.0 / MARGIN
            spent = 0.0
            room = 0
            for seconds, _label in ordered:
                if spent + seconds > budget:
                    break
                spent += seconds
                room += 1
            print('  for 120 s to fit, the warm set would have to shrink to'
                  ' about %d keys (cheapest first, %.1f s of a %.1f s budget)'
                  % (room, spent, budget))
            print('  at 120 s with all %d keys the producer would be %.0f%%'
                  ' over its own cadence -- sweeps would overlap and ages'
                  ' would grow without bound'
                  % (len(warm), 100.0 * (median_sweep / 120.0 - 1)))

        print('\n--- Step 4: the worst age a warm key reaches ---')
        # MEASURED, not reasoned: the interval between one key's consecutive
        # `as_of` stamps IS its refresh interval. The sweeps above ran
        # back to back, so these intervals are what a producer running with
        # NO idle time delivers -- the floor.
        intervals = []
        for label, samples in as_ofs.items():
            stamps = [as_of for _offset, as_of in samples[1:]]
            for older, newer in zip(stamps, stamps[1:]):
                intervals.append(((newer - older).total_seconds(), label))
        worst_interval, worst_label = max(intervals)
        best_interval, _ = min(intervals)
        print('  back-to-back sweeping, per-key as_of interval:'
              ' %.1f s best, %.1f s worst (%s)'
              % (best_interval, worst_interval, worst_label.strip()))
        drift = worst_interval - median_sweep
        print('  drift beyond the median sweep: %.1f s' % drift)
        print('  WORST WARM-KEY AGE at %d s cadence: about %.0f s'
              % (cadence, cadence + max(drift, 0.0)))
        print('  (a reader arriving just before a key is rebuilt sees the'
              ' cadence plus that key\'s own drift; `as_of` is stamped when'
              ' the producer CLAIMS, so the sweep length is not added)')
        print('\n  => MAX_AGE cannot honestly be shorter than that. The plan'
              ' proposed MAX_AGE=300 s.')
        print('  MariaDB 10.11.14 is the target; this is MySQL 8.0.46.'
              ' The seconds do not transfer, the shape does.')


if __name__ == '__main__':
    main()

"""Step 3 / decision 7: the per-account half of a board read, at scale.

A stored board is viewer-invariant; the reader's own marks are added per
request by `routes.api.account_fields` -- `watch.tickers_for` and
`board.build_pinned_rows` over the watched tickers -- and no cache removes
that half. This times it for accounts watching 0, 3, 10 and 25 tickers,
n = 20 each after one discarded warm-up call, on the US 12h and 24h boards and
the DE 24h board. The ORM session is removed after every call (outside the
timer), so each call checks a connection out and pings it, as a request does.

THE RULE (the brief's): if the 25-ticker median exceeds 150 ms -- on ANY of
the three boards, the strictest reading of "the 25-mark case", which the
brief does not tie to one board -- implement the bounded memo -- a per-process memo of
`build_pinned_rows` keyed on (user_id, tuple(watching), key_hash, as_of), at
most 64 entries, in board_shared.py -- with a test, and re-measure. Otherwise
record that it was not needed and why.

The watched tickers are the ones a reader would star: the rows of the US 24h
All board in board order, read from the store when the producer has built it,
otherwise built once here, directly.

    cd personal_apps
    <python 3.12> scratchpad/perf3/profile_watch_perf3.py [--n 20] [--out DIR]
"""
import argparse
import json
import time
import zlib

import sqlalchemy as sa

import scale_env

app = scale_env.bind()

from extensions import db                                  # noqa: E402
from features.radar import board_shared, board_store       # noqa: E402
from features.radar.config import expand_sources           # noqa: E402
from features.radar.routes import api                      # noqa: E402
import perf3_common as common                              # noqa: E402

COUNTS = (0, 3, 10, 25)
CASES = (('us', 12), ('us', 24), ('de', 24))
LIMIT_MS = 150.0


def board_tickers(engine, now, want):
    """`want` tickers a reader would star, and where they came from."""
    args = {'market': 'us', 'segment': '', 'window': '24'}
    key_hash, _ = common.key_of(args, now)
    stored = board_store.read(engine, scale_env.namespace(), key_hash)
    if stored is not None and stored.payload is not None:
        payload = json.loads(zlib.decompress(stored.payload))
        origin = f'the stored US 24h All board (as_of {stored.as_of})'
    else:
        payload = api.build_payload_direct(args, now=now)
        db.session.remove()
        origin = 'the US 24h All board, built directly (none stored)'
    tickers = [row['ticker'] for row in payload['rows']][:want]
    if len(tickers) < want:
        names = expand_sources(['bluesky', 'fourchan', 'reddit'])
        with engine.connect() as c:
            extra = c.execute(sa.text(
                'SELECT ticker FROM radar_bucket_sources'
                ' WHERE bucket_start >= :since AND bucket_start < :now'
                ' AND source IN :names GROUP BY ticker'
                ' ORDER BY SUM(mention_count) DESC LIMIT :n').bindparams(
                    sa.bindparam('names', expanding=True)),
                {'since': now - common.dt.timedelta(hours=24), 'now': now,
                 'names': names, 'n': want * 2}).scalars().all()
        tickers += [t for t in extra if t not in tickers][:want - len(tickers)]
        origin += ', topped up by 24h mentions'
    return tickers, origin


def time_account(query, user_id, n):
    api.account_fields(query, common.utcnow(), user_id)       # warm-up
    db.session.remove()
    took = []
    fields = None
    for _ in range(n):
        now = common.utcnow()
        began = time.perf_counter()
        fields = api.account_fields(query, now, user_id)
        took.append(time.perf_counter() - began)
        db.session.remove()
    return took, fields


def time_read(engine, args, user_id, n):
    """The whole read_payload for this account, when the board is stored.

    Checked in the store first: a read of a missing board would ADMIT it,
    leaving a pending on-demand row behind in the real namespace.
    """
    # A stale board's read also admits a refresh -- a write -- so it is not a
    # ready read. With the producer running, wait for a board young enough
    # (under 60 s) that all the reads land well inside the fresh bound: the
    # producer refreshes it once it is 120 s old. The first real run skipped
    # this series with a stricter "skip if over 90 s" guard; it now waits.
    key_hash = common.key_of(args)[0]
    deadline = time.perf_counter() + 240
    while True:
        stored = board_store.read(engine, scale_env.namespace(), key_hash)
        if stored is None or stored.payload is None or stored.as_of is None:
            return None, ['not stored'], None
        age = (common.utcnow() - stored.as_of).total_seconds()
        if age <= 60:
            break
        if time.perf_counter() > deadline:
            return None, [f'{age:.0f} s old after waiting'], None
        time.sleep(1.0)
    # One read outside the n, reported: the first read with watched tickers
    # in a process fills its coverage cache with a full scan -- the restart
    # cost measure_perf3.py (c) measures, not a steady read.
    began = time.perf_counter()
    board_shared.read_payload(engine, args, common.utcnow(), user_id)
    first_ms = round((time.perf_counter() - began) * 1000, 1)
    db.session.remove()
    took = []
    kinds = []
    for _ in range(n):
        began = time.perf_counter()
        payload = board_shared.read_payload(engine, args, common.utcnow(),
                                            user_id)
        took.append(time.perf_counter() - began)
        db.session.remove()
        if not common.is_board(payload):
            return None, ['pending'], first_ms
        kinds.append('stale' if payload['stale'] else 'ready')
    return took, kinds, first_ms


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--n', type=int, default=20)
    parser.add_argument('--out')
    parser.add_argument('--label', default='profile_watch_perf3 (Step 3)')
    parser.add_argument('--no-producer', action='store_true',
                        help='skip the whole-read timing and its producer')
    args = parser.parse_args()

    import env_check
    env_check.preflight(args.label)
    out = common.out_dir(args.out)
    engine = scale_env.engine()
    ns = scale_env.namespace()
    record = {'n': args.n, 'cases': []}
    producer = None
    with app.app_context():
        if not args.no_producer:
            # Its own producer, so the whole reads below meet fresh boards
            # whatever the previous script left in the store. It is stopped
            # before the per-account timings, which run on a quiet database.
            producer = common.start_producer(out, name='producer-profile')
            if producer.namespace != ns:
                raise SystemExit('producer namespace differs')
            common.wait_ready_idle(engine, ns, timeout=900)
        now = common.utcnow()
        tickers, origin = board_tickers(engine, now, max(COUNTS))
        print(f'watched tickers: {len(tickers)} from {origin}')
        print(f'  {tickers}')
        spec = {f'perf3_w{count:02d}': tickers[:count] for count in COUNTS}
        ids = common.create_accounts(engine, spec)
        record.update(tickers=tickers, origin=origin, accounts=ids)
        try:
            # First, while the stored board may still be fresh: a whole read
            # of a stale board also writes, and would not be a ready read.
            print('\n  the whole read_payload, US 24h All (a fresh stored board):')
            read_args = {'market': 'us', 'segment': '', 'window': '24'}
            record['reads'] = []
            for count in COUNTS:
                took, kinds, first_ms = time_read(
                    engine, read_args, ids[f'perf3_w{count:02d}'], args.n)
                if took is None:
                    print(f'    watching {count:2d}: skipped ({kinds[0]}; a'
                          ' read would not be a ready read)')
                    continue
                record['reads'].append({'watching': count,
                                        'ms': common.triple(took),
                                        'first_ms': first_ms,
                                        'kinds': kinds})
                print(f'    watching {count:2d}: {common.fmt(took)}'
                      f"   ({kinds.count('ready')} ready,"
                      f" {kinds.count('stale')} stale; first read, outside"
                      f' the n: {first_ms} ms)')
            if producer is not None:
                common.wait_ready_idle(engine, ns, timeout=900)
                producer.kill()
                producer = None
                print('  (producer stopped while idle: the per-account'
                      ' timings below run on a quiet database)')
            print(f"\n  {'case':10s} {'watching':>8s}  account_fields"
                  '                                  watch rows')
            for market, window in CASES:
                query = api.parse_query({'market': market, 'segment': '',
                                         'window': str(window)}, now=now)
                for count in COUNTS:
                    user_id = ids[f'perf3_w{count:02d}']
                    took, fields = time_account(query, user_id, args.n)
                    rows = len(fields['watch_rows'])
                    record['cases'].append({
                        'market': market, 'window': window, 'watching': count,
                        'ms': common.triple(took), 'watch_rows': rows,
                        'raw_ms': [round(v * 1000, 2) for v in took]})
                    print(f'  {market}/{window:2d}h     {count:>8d}  '
                          f'{common.fmt(took)}   {rows}')
        finally:
            if producer is not None:
                producer.kill()
            removed = common.delete_accounts(engine, list(spec))
            db.session.remove()
            print(f'\naccounts removed: {removed}')

    # The brief names "the 25-mark case" without naming a board, so the
    # strictest reading governs: the worst 25-ticker median of the three.
    governing = max((case for case in record['cases']
                     if case['watching'] == 25),
                    key=lambda case: case['ms'][0])
    median = governing['ms'][0]
    triggered = median > LIMIT_MS
    where = f"{governing['market'].upper()} {governing['window']}h"
    record['verdict'] = {'governing_median_ms': median, 'governing_case': where,
                         'limit_ms': LIMIT_MS, 'triggered': triggered}
    print(f'\nVERDICT: the worst 25-ticker median ({where}) is {median:.1f} ms'
          f" against {LIMIT_MS:.0f} ms -> {'TRIGGERED: implement the memo' if triggered else 'NOT TRIGGERED: the memo is not needed'}")
    common.save(out, 'profile_watch.json', record)


if __name__ == '__main__':
    main()

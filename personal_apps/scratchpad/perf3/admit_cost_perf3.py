"""Decision 6: what the control-row write costs every admission.

Every admission -- polls included -- moves `last_seen_at` on the generation's
control row (`board_store._under_lock`: `GREATEST(last_seen_at, :now)`). The
Task 2 review carried it here to be measured: 1,000 admissions and 1,000 polls
through `board_store.admit` with that UPDATE and without it (the `without` arm
replaces `_under_lock` with a copy minus the one statement, for the comparison
only), in one process and in two OS processes admitting at once, p50/p95/max,
and the InnoDB row-lock waits of each arm.

THE RULE, fixed before the first run. Gate the write to minute resolution if
(a) it adds more than 5 ms at p95 in any arm, or (b) it shows lock waits of
its own: any row-lock wait in the single-process arm with the UPDATE (a lone
process has nobody to wait for), or, with two processes, more waits or more
wait time with the UPDATE than without it by over 20% and at least 10 waits,
in every round. Two processes always wait for each other on the control row's
`SELECT ... FOR UPDATE`; waits both arms show belong to the lock the design
chose, not to this statement, which runs on a row its transaction already
holds.

A dedicated bench namespace (no producer claims it; the real one is not
touched) holds 16 on-demand keys admitted once, so every timed call takes the
already-queued path; the queue never fills, so no call is refused. The bench
rows are deleted afterwards.

    cd personal_apps
    <python 3.12> scratchpad/perf3/admit_cost_perf3.py [--n 1000] [--rounds 2] [--out DIR]
"""
import argparse
import hashlib
import json
import pathlib
import time

import sqlalchemy as sa

import scale_env

app = scale_env.bind()

from features.radar import board_namespace, board_store  # noqa: E402
import perf3_common as common                           # noqa: E402

KEYS = 16
ORIGINAL = board_store._under_lock


def _under_lock_without_touch(engine, ns, now, work):
    """`board_store._under_lock` minus the `last_seen_at` UPDATE. Bench only."""
    for _ in range(2):
        with engine.begin() as connection:
            if connection.execute(sa.text(
                    f'SELECT namespace FROM {board_store.NAMESPACES}'
                    ' WHERE namespace = :ns FOR UPDATE'),
                    {'ns': ns}).first() is not None:
                return work(connection)
        board_store._adopt(engine, ns, now)
    raise RuntimeError('no control row could be held')


def use(mode):
    board_store._under_lock = (ORIGINAL if mode == 'with'
                               else _under_lock_without_touch)


def bench_keys():
    return [(hashlib.sha256(f'perf3-admit-bench-{i}'.encode()).hexdigest(),
             json.dumps({'perf3_admit_bench': i})) for i in range(KEYS)]


def run_batch(engine, ns, n, *, poll):
    keys = bench_keys()
    took = []
    for i in range(n):
        key_hash, key_json = keys[i % KEYS]
        now = common.utcnow()
        began = time.perf_counter()
        state = board_store.admit(engine, ns, key_hash, key_json, now,
                                  poll=poll)
        took.append(time.perf_counter() - began)
        if state != 'pending':
            raise RuntimeError(f'bench key answered {state!r}, not pending')
    return took


def setup(engine, ns):
    now = common.utcnow()
    board_store.ensure_namespace(engine, ns, now, revision=scale_env.REVISION,
                                 payload_version=board_namespace.PAYLOAD_VERSION)
    use('with')
    for key_hash, key_json in bench_keys():
        board_store.admit(engine, ns, key_hash, key_json, now)


def cleanup(engine, ns):
    with engine.begin() as c:
        rows = c.execute(sa.text(
            'DELETE FROM radar_board_results WHERE namespace = :ns'),
            {'ns': ns}).rowcount
        c.execute(sa.text(
            'DELETE FROM radar_board_namespaces WHERE namespace = :ns'),
            {'ns': ns})
    return rows


def child(args):
    """One of the two concurrent admitters."""
    engine = scale_env.engine()
    use(args.mode)
    delay = args.start_at - time.time()
    if delay > 0:
        time.sleep(delay)
    admits = run_batch(engine, args.ns, args.n, poll=False)
    polls = run_batch(engine, args.ns, args.n, poll=True)
    pathlib.Path(args.child_out).write_text(json.dumps(
        {'admit': admits, 'poll': polls}), encoding='utf-8')
    print('CHILD-DONE', flush=True)


def row(label, values):
    return f'  {label:34s} ' + common.fmt(values, digits=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--n', type=int, default=1000)
    parser.add_argument('--rounds', type=int, default=2)
    parser.add_argument('--out')
    parser.add_argument('--child', action='store_true')
    parser.add_argument('--ns')
    parser.add_argument('--mode')
    parser.add_argument('--start-at', type=float)
    parser.add_argument('--child-out')
    args = parser.parse_args()
    if args.child:
        return child(args)

    import env_check
    env_check.preflight('admit_cost_perf3 (decision 6)')
    out = common.out_dir(args.out)
    engine = scale_env.engine()
    ns = hashlib.sha256(f'perf3-admit-bench:{time.time()}'.encode()).hexdigest()
    print(f'bench namespace {ns[:16]}... ({KEYS} on-demand keys, no producer)')
    record = {'n': args.n, 'rounds': args.rounds, 'single': [], 'pair': []}
    setup(engine, ns)
    try:
        use('with')
        run_batch(engine, ns, 100, poll=False)            # warm-up, discarded

        print('\n--- one process ---')
        for round_no in range(args.rounds):
            order = ('with', 'without') if round_no % 2 == 0 else (
                'without', 'with')
            for mode in order:
                use(mode)
                before = common.lock_status(engine)
                admits = run_batch(engine, ns, args.n, poll=False)
                polls = run_batch(engine, ns, args.n, poll=True)
                locks = common.lock_delta(before, common.lock_status(engine))
                use('with')
                record['single'].append({'round': round_no, 'mode': mode,
                                         'admit': admits, 'poll': polls,
                                         'locks': locks})
                print(row(f'round {round_no} {mode:7s} admissions', admits))
                print(row(f'round {round_no} {mode:7s} polls', polls)
                      + f"   lock waits {locks['waits']}"
                      f" ({locks['time_ms']} ms)")

        print('\n--- two OS processes at once ---')
        for round_no in range(args.rounds):
            order = ('with', 'without') if round_no % 2 == 0 else (
                'without', 'with')
            for mode in order:
                start_at = time.time() + 15
                kids = [common.Child(
                    f'admit-{mode}-{round_no}-{i}', __file__,
                    ['--child', '--ns', ns, '--mode', mode, '--n', args.n,
                     '--start-at', start_at, '--child-out',
                     out / f'admit-{mode}-{round_no}-{i}.json'],
                    out / f'admit-{mode}-{round_no}-{i}.log',
                    common.child_env()) for i in range(2)]
                try:
                    time.sleep(max(0.0, start_at - time.time() - 1))
                    before = common.lock_status(engine)
                    for kid in kids:
                        kid.wait_line('CHILD-DONE', timeout=600)
                    locks = common.lock_delta(before,
                                              common.lock_status(engine))
                finally:
                    common.stop_all(kids)
                results = [json.loads((out / f'admit-{mode}-{round_no}-{i}'
                                       '.json').read_text()) for i in range(2)]
                admits = results[0]['admit'] + results[1]['admit']
                polls = results[0]['poll'] + results[1]['poll']
                record['pair'].append({'round': round_no, 'mode': mode,
                                       'admit': admits, 'poll': polls,
                                       'locks': locks})
                print(row(f'round {round_no} {mode:7s} admissions x2', admits))
                print(row(f'round {round_no} {mode:7s} polls x2', polls)
                      + f"   lock waits {locks['waits']}"
                      f" ({locks['time_ms']} ms)")
    finally:
        use('with')
        removed = cleanup(engine, ns)
        print(f'\nbench namespace removed ({removed} rows)')

    verdict = judge(record)
    record['verdict'] = verdict
    common.save(out, 'admit_cost.json', record)


def judge(record):
    """Apply the rule in the module docstring; print and return it."""
    print('\n--- the rule ---')
    reasons = []
    summary = {}
    for arm in ('single', 'pair'):
        for kind in ('admit', 'poll'):
            pooled = {mode: [v for entry in record[arm]
                             if entry['mode'] == mode for v in entry[kind]]
                      for mode in ('with', 'without')}
            p95 = {mode: common.summary(values)[2]
                   for mode, values in pooled.items()}
            p50 = {mode: common.summary(values)[1]
                   for mode, values in pooled.items()}
            delta = (p95['with'] - p95['without']) * 1000
            summary[f'{arm}_{kind}'] = {
                'p50_with_ms': round(p50['with'] * 1000, 2),
                'p50_without_ms': round(p50['without'] * 1000, 2),
                'p95_with_ms': round(p95['with'] * 1000, 2),
                'p95_without_ms': round(p95['without'] * 1000, 2),
                'p95_delta_ms': round(delta, 2)}
            print(f'  {arm:6s} {kind:5s} p50 {p50["with"] * 1000:6.2f} vs'
                  f' {p50["without"] * 1000:6.2f} ms   p95'
                  f' {p95["with"] * 1000:6.2f} vs {p95["without"] * 1000:6.2f}'
                  f' ms   p95 delta {delta:+.2f} ms')
            if delta > 5:
                reasons.append(f'{arm} {kind} p95 +{delta:.2f} ms > 5 ms')
    single_waits = sum(entry['locks']['waits'] for entry in record['single']
                       if entry['mode'] == 'with')
    if single_waits:
        reasons.append(f'{single_waits} lock waits in the single-process arm'
                       ' with the UPDATE')
    rounds = sorted({entry['round'] for entry in record['pair']})
    worse_every_round = bool(rounds)
    for round_no in rounds:
        by_mode = {entry['mode']: entry['locks'] for entry in record['pair']
                   if entry['round'] == round_no}
        w, wo = by_mode['with'], by_mode['without']
        print(f'  pair round {round_no}: lock waits {w["waits"]} with /'
              f' {wo["waits"]} without; wait time {w["time_ms"]} /'
              f' {wo["time_ms"]} ms')
        more = ((w['waits'] > 1.2 * wo['waits']
                 and w['waits'] - wo['waits'] >= 10)
                or (w['time_ms'] > 1.2 * wo['time_ms']
                    and w['waits'] - wo['waits'] >= 10))
        worse_every_round = worse_every_round and more
    if worse_every_round:
        reasons.append('two processes wait more with the UPDATE in every'
                       ' round')
    triggered = bool(reasons)
    print(f"  VERDICT: {'TRIGGERED -- ' + '; '.join(reasons) if triggered else 'NOT TRIGGERED'}")
    return {'triggered': triggered, 'reasons': reasons, 'summary': summary}


if __name__ == '__main__':
    main()

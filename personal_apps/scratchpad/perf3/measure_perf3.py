"""Step 1 of Task 8: the shared board path, measured at production scale.

Phases, each printing its own table and saving its JSON (`--phase` takes a
comma list; `all` runs them in this order):

  ready       (a) ready reads through `read_payload`, an account watching three
                  tickers, 12h and 24h -- and the same reads over HTTP
  memory      (e) working sets of the producer and both web-model processes,
                  at rest and after 100 reads each
  restart     (c) kill and restart a web-model process n times; its first read
  cold        (d) cold on-demand selections (sort=lean 24h, then limit=100 24h),
                  n cold each, then limit=100 repeated
  empty       (b) empty store: TRUNCATE both tables, the first request's pending
                  answer, the time to publish, the time until a reader sees it
  queue       (f) ten minutes of the warm keys on their 120 s refresh and one
                  on-demand request every 10 s, the table sampled every 5 s
  contention  (g) the write alone, then (f) again while write_cost.py's bulk
                  UPDATE runs three times

Topology -- a MODEL, not gunicorn: the real `run_radar_board_producer.py` as
one subprocess, two web-model processes (`serve_perf3.py`, the real WSGI app,
one request thread each, flag on) as two more, all bound by scale_env. This
process is every client and reads the table directly. A `pending` answer is
never counted as a board: every cold number below is the time until a real
board was in hand.

    cd personal_apps
    <python 3.12> scratchpad/perf3/measure_perf3.py --phase all [--n 20] [--out DIR]
"""
import argparse
import datetime as dt
import json
import threading
import time
import zlib

import scale_env

app = scale_env.bind()

from extensions import db                                   # noqa: E402
from features.radar import board_shared, board_store        # noqa: E402
import perf3_common as common                               # noqa: E402

PORTS = (5081, 5082)
READY_TARGET_MS = 500.0     # the ruling's ready-response p95 target
COLD_GOAL_S = 2.0           # the ruling's UNMET first-missing-result goal
FRESH_S = 120.0
EXPIRY_S = 600.0


class Harness:
    """The producer, two web-model workers, one reader account."""

    def __init__(self, out, n):
        self.out = out
        self.n = n
        self.engine = scale_env.engine()
        self.ns = scale_env.namespace()
        self.producer = None
        self.webs = []
        self.children = []
        self.user_id = None
        self.cookie = None
        self.tickers = []
        self.started = {}

    def start_producer(self, name=None):
        name = name or f'producer-{len(self.children)}'
        began = time.perf_counter()
        producer = common.start_producer(self.out, name=name)
        if producer.namespace != self.ns:
            raise SystemExit(f'producer namespace {producer.namespace} != '
                             f'{self.ns}')
        self.producer = producer
        self.children.append(producer)
        self.started[name] = time.perf_counter() - began
        return producer

    def stop_producer(self):
        """Stop it while idle, so no lease is left to expire."""
        common.wait_ready_idle(self.engine, self.ns, timeout=900)
        self.producer.kill()

    def start_webs(self):
        for port in PORTS:
            web = common.start_web(self.out, port)
            if web.namespace != self.ns:
                raise SystemExit(f'web namespace {web.namespace} != {self.ns}')
            self.webs.append(web)
            self.children.append(web)

    def web(self, index):
        return self.webs[index % len(self.webs)]

    def account(self):
        """Four disposable accounts spanning the demanded watch cardinalities."""
        args = {'market': 'us', 'segment': '', 'window': '24'}
        key_hash, _ = common.key_of(args)
        stored = board_store.read(self.engine, self.ns, key_hash)
        rows = json.loads(zlib.decompress(stored.payload))['rows']
        all_tickers = [row['ticker'] for row in rows[:25]]
        self.tickers = all_tickers[:3]
        spec = {f'perf3_m{count:02d}': all_tickers[:count]
                for count in (0, 3, 10, 25)}
        ids = common.create_accounts(self.engine, spec)
        self.accounts = {count: ids[f'perf3_m{count:02d}']
                         for count in (0, 3, 10, 25)}
        self.cookies = {count: common.mint_cookie(app, user_id)
                        for count, user_id in self.accounts.items()}
        self.user_id = ids['perf3_m03']
        self.cookie = common.mint_cookie(app, self.user_id)

    def close(self):
        common.stop_all(self.children)
        removed = common.delete_accounts(
            self.engine, [f'perf3_m{count:02d}' for count in (0, 3, 10, 25)])
        rows, others = common.delete_on_demand(self.engine, self.ns)
        print(f'\ncleanup: {removed} account(s), {rows} on-demand board(s),'
              f' {others} rows of other namespaces removed; warm boards kept')


# --- one cold request, from the first answer to a board in hand -------------

def cold_request(h, args, key_hash, port, *, watch=False, timeout=600):
    """Ask once, then poll as the client does, until a real board arrives.

    `watch=True` also polls the ROW every 50 ms from this process and, the
    moment a payload is there, issues one fresh read -- "a reader asking at
    the instant of publication" -- beside the client's own poll cadence.
    """
    wall0 = common.utcnow()
    t0 = time.perf_counter()
    first_s, status, payload = common.board(port, args, h.cookie)
    rep = {'args': args, 'port': port, 'first_ms': round(first_s * 1000, 1),
           'first_status': status}
    if common.is_board(payload):
        rep['first_was_board'] = True
        return rep
    rep.update(first_was_board=False,
               first_pending=bool(payload and payload.get('pending')),
               first_busy=bool(payload and payload.get('busy')),
               first_rows_null=payload is not None and payload.get('rows') is None,
               first_generated_at=payload.get('generated_at') if payload else None,
               first_retry_ms=payload.get('retry_after_ms') if payload else None)
    watched = {}
    stop = threading.Event()

    def watcher():
        while not stop.is_set():
            row = common.key_row(h.engine, h.ns, key_hash)
            if row and row['has_payload']:
                watched['detected_s'] = time.perf_counter() - t0
                took, _, answer = common.board(port, args, h.cookie)
                watched['read_ms'] = round(took * 1000, 1)
                watched['read_is_board'] = common.is_board(answer)
                return
            time.sleep(0.05)

    thread = threading.Thread(target=watcher, daemon=True) if watch else None
    if thread:
        thread.start()
    retry = (payload or {}).get('retry_after_ms') or 1000
    polls = 0
    seen = None
    while time.perf_counter() - t0 < timeout:
        time.sleep(retry / 1000.0)
        took, status, payload = common.board(port, args, h.cookie, poll=True)
        polls += 1
        if common.is_board(payload):
            seen = time.perf_counter() - t0
            rep['seen_stale'] = bool(payload.get('stale'))
            break
        retry = (payload or {}).get('retry_after_ms') or 1000
    stop.set()
    if thread:
        thread.join(timeout=30)
    row = common.key_row(h.engine, h.ns, key_hash) or {}
    rep.update(polls=polls, seen_s=None if seen is None else round(seen, 3),
               **watched)
    if row.get('as_of') and row.get('enqueued_at'):
        rep.update(
            queue_wait_s=round((row['as_of'] - row['enqueued_at'])
                               .total_seconds(), 3),
            enqueue_after_s=round((row['enqueued_at'] - wall0)
                                  .total_seconds(), 3),
            build_ms=row['build_ms'],
            as_of_after_s=round((row['as_of'] - wall0).total_seconds(), 3),
            built_after_s=round((row['built_at'] - wall0).total_seconds(), 3))
        if seen is not None:
            rep['build_to_usable_s'] = round(seen - rep['as_of_after_s'], 3)
    return rep


# --- (a) ready reads ------------------------------------------------------------

def phase_ready(h):
    print('\n=== (a) loaded ready reads: US/DE x 12/24h x 0/3/10/25 watches ===')
    record = {'watch_tickers': h.tickers, 'cases': {}}
    # One read per path and window first, OUTSIDE the n. The first board read
    # in a process fills that process's coverage cache with a full scan (and
    # its sigma cache), which is the restart cost (c) measures -- not a steady
    # ready read. Reported here, never dropped silently.
    first = {}
    from features.radar.config import DEFAULT_SEGMENT
    for market in ('us', 'de'):
        for window in (12, 24):
            args = {'market': market, 'segment': DEFAULT_SEGMENT,
                    'window': str(window)}
            for web in h.webs:
                took, _, _ = common.board(web.port, args, h.cookies[0])
                second, _, _ = common.board(web.port, args, h.cookies[0])
                first[f'{web.name} {market}/{window}h first'] = round(
                    took * 1000, 1)
                first[f'{web.name} {market}/{window}h subsequent'] = round(
                    second * 1000, 1)
    record['first_reads_ms'] = first
    print('    first read per process and window, outside the n (cache fill): '
          + ', '.join(f'{key} {value} ms' for key, value in first.items()))
    # Keep the real producer busy with ordinary admitted builds, and overlap
    # one ingest-shaped 20k-row update/restore with the HTTP matrix.
    for limit in range(60, 82):
        common.board(h.web(limit).port,
                     {'market': 'us' if limit % 2 else 'de', 'segment': '',
                      'window': '24', 'limit': str(limit)}, h.cookies[0])
    build_mark = len(h.producer.text())
    writer = common.Child(
        'writer-ready', common.HERE / 'write_contention_perf3.py',
        ['--offsets', '0', '--out', h.out / 'writes-ready.json'],
        h.out / 'writer-ready.log', common.child_env())
    h.children.append(writer)
    writer.wait_line('WRITE-PLAN', timeout=120)
    for market in ('us', 'de'):
        for window in (12, 24):
            for watches in (0, 3, 10, 25):
                args = {'market': market, 'segment': DEFAULT_SEGMENT,
                        'window': str(window)}
                values, ages, accounts, outcomes = [], [], [], []
                for i in range(h.n):
                    web = h.web(i)
                    before = len(common.parse_reads(web.text()))
                    took, status, answer = common.board(
                        web.port, args, h.cookies[watches])
                    reads = common.parse_reads(web.text())
                    metric = reads[-1] if len(reads) > before else None
                    if (status != 200 or not common.is_board(answer)
                            or metric is None):
                        raise RuntimeError(
                            f'HTTP loaded ready read: {status}, metric={metric}')
                    values.append(took)
                    ages.append(metric['cache_age'])
                    accounts.append(metric['account_ms'])
                    outcomes.append(metric['outcome'])
                name = f'{market}-{window}h-watch{watches}'
                record['cases'][name] = {
                    'http_ms': common.summary([v * 1000 for v in values]),
                    'cache_age_s': common.summary(ages),
                    'account_ms': common.summary(accounts),
                    'outcomes': {kind: outcomes.count(kind)
                                 for kind in set(outcomes)},
                    'raw_http_ms': [round(v * 1000, 2) for v in values]}
                print(f'  {name:22s} {common.fmt(values)} account '
                      f'{common.fmt([v / 1000 for v in accounts])} cache-age '
                      f'{common.fmt(ages, scale=1, unit="s", digits=2)}')
    writer.wait_line('WRITE-DONE', timeout=900)
    writer.kill()
    record['representative_write'] = json.loads(
        (h.out / 'writes-ready.json').read_text())
    record['producer_builds_during_matrix'] = common.parse_builds(
        h.producer.text()[build_mark:])
    if not record['producer_builds_during_matrix']:
        raise RuntimeError('producer completed no build during loaded matrix')
    return record


# --- (e) memory -------------------------------------------------------------------

def phase_memory(h):
    print('\n=== (e) memory: Windows working set (the local analogue of RSS) ===')
    procs = [h.producer] + h.webs
    rest = {child.name: common.working_set(child.pid) for child in procs}
    warm = common.warm_args()
    reads = {}
    for web in h.webs:
        took = []
        for i in range(100):
            seconds, status, answer = common.board(web.port, warm[i % 8],
                                                   h.cookie)
            if status != 200 or not common.is_board(answer):
                raise RuntimeError(f'read {i} on {web.name}: {status}')
            took.append(seconds)
        reads[web.name] = common.triple(took)
    after = {child.name: common.working_set(child.pid) for child in procs}
    start = getattr(h, 'memory_at_start', {})
    print(f"  {'process':16s} {'started':>10s} {'at rest':>10s}"
          f" {'+100 reads':>11s} {'peak':>9s} {'private':>9s}")
    for child in procs:
        first = start.get(child.name, {}).get('ws_mb', float('nan'))
        before, now = rest[child.name], after[child.name]
        print(f"  {child.name:16s} {first:>7.1f} MB {before['ws_mb']:>7.1f} MB"
              f" {now['ws_mb']:>8.1f} MB {now['peak_ws_mb']:>6.1f} MB"
              f" {now['private_mb']:>6.1f} MB")
    print('  started = right after the prewarm, before any read; at rest ='
          ' idle after phase (a); the producer does no reads, so its later'
          ' columns are simply later')
    for name, trio in reads.items():
        print(f'  {name}: the 100 reads took median {trio[0]} ms, p95'
              f' {trio[1]} ms, max {trio[2]} ms (8 warm keys in turn)')
    return {'started': start, 'at_rest': rest, 'after_100_reads': after,
            'read_ms': reads}


# --- (c) restart ------------------------------------------------------------------

def phase_restart(h):
    print('\n=== (c) restart: kill a web-model process, start it, read ===')
    args = {'market': 'us', 'segment': '', 'window': '24'}
    reps = []
    for i in range(h.n):
        old = h.webs[0]
        old.kill()
        began = time.perf_counter()
        new = common.start_web(h.out, old.port, name=f'web{old.port}-r{i:02d}')
        startup = time.perf_counter() - began
        first_s, status, first = common.board(new.port, args, h.cookie)
        second_s, _, second = common.board(new.port, args, h.cookie)
        if new.namespace != h.ns:
            raise SystemExit('restarted worker resolved another namespace')
        h.webs[0] = new
        h.children.append(new)
        reps.append({'startup_s': round(startup, 3),
                     'first_ms': round(first_s * 1000, 1),
                     'second_ms': round(second_s * 1000, 1),
                     'first_is_board': common.is_board(first),
                     'first_stale': bool(first and first.get('stale')),
                     'first_age_s': first.get('age_seconds') if first else None})
    first = [r['first_ms'] / 1000 for r in reps]
    print(f'  first read after restart  {common.fmt(first)}')
    print('  second read               '
          f"{common.fmt([r['second_ms'] / 1000 for r in reps])}")
    print('  spawn -> listening        '
          f"{common.fmt([r['startup_s'] for r in reps], scale=1.0, unit='s', digits=2)}"
          '  (bind + app import + preflight query, not counted above)')
    boards = sum(r['first_is_board'] for r in reps)
    print(f"  first read was a board in {boards} of {len(reps)}"
          f" ({sum(r['first_stale'] for r in reps)} of them stale)")
    if boards != len(reps):
        print('  FAILED: a first read after restart was not a board')
    return {'reps': reps}


# --- cold summaries -----------------------------------------------------------

def _line(title, values, *, seconds=True):
    if not values:
        return f'  {title:44s} n=0'
    if seconds:
        return f'  {title:44s} ' + common.fmt(values, scale=1.0, unit='s',
                                               digits=2)
    return f'  {title:44s} ' + common.fmt(values)


def summarize_cold(title, reps):
    got = [r for r in reps if r.get('seen_s') is not None
           and not r.get('first_was_board')]
    print(f'\n  {title}: {len(got)} of {len(reps)} delivered a board'
          + (f"; {sum(1 for r in reps if r.get('first_was_board'))} were not"
             ' cold' if any(r.get('first_was_board') for r in reps) else ''))
    print(_line('first answer: pending, rows null (NOT a board)',
                [r['first_ms'] / 1000 for r in got], seconds=False))
    print(_line('queue wait (enqueued_at -> as_of)',
                [r['queue_wait_s'] for r in got if 'queue_wait_s' in r]))
    print(_line('build (producer build_ms)',
                [r['build_ms'] / 1000 for r in got if r.get('build_ms')]))
    if any('detected_s' in r for r in got):
        print(_line('request -> publish detected (50 ms poll)',
                    [r['detected_s'] for r in got if 'detected_s' in r]))
        print(_line('a read issued at publication',
                    [r['read_ms'] / 1000 for r in got if 'read_ms' in r],
                    seconds=False))
        print(_line('COLD, read at publication (UNMET <= 2 s goal)',
                    [r['detected_s'] + r['read_ms'] / 1000 for r in got
                     if 'read_ms' in r]))
    print(_line('build-to-usable (as_of -> board in hand)',
                [r['build_to_usable_s'] for r in got
                 if 'build_to_usable_s' in r]))
    print(_line('COLD, as the client polls (UNMET <= 2 s goal)',
                [r['seen_s'] for r in got]))
    within = sum(1 for r in got if r['seen_s'] <= COLD_GOAL_S)
    print(f'  first missing result within {COLD_GOAL_S:.0f} s: {within} of'
          f' {len(got)} -- the goal stays UNMET, reported, never a pass')


def wait_not_building(h, key_hash, timeout=600):
    began = time.perf_counter()
    while time.perf_counter() - began < timeout:
        row = common.key_row(h.engine, h.ns, key_hash)
        if row is None or row['queue_state'] != 'building':
            return
        time.sleep(0.2)
    raise TimeoutError('key stayed building')


# --- (d) cold on-demand selections --------------------------------------------

COLD = (('sort=lean 24h', {'market': 'us', 'segment': '', 'window': '24',
                           'sort': 'lean'}),
        ('limit=100 24h', {'market': 'us', 'segment': '', 'window': '24',
                           'limit': '100'}))


def phase_cold(h):
    print('\n=== (d) cold on-demand selections, the producer running ===')
    print('    each rep deletes the key first, so it is genuinely missing;'
          ' lean does no tone work here (no radar_posts): a lower bound')
    record = {}
    for name, args in COLD:
        key_hash, _ = common.key_of(args)
        reps = []
        for i in range(h.n):
            wait_not_building(h, key_hash)
            common.delete_key(h.engine, h.ns, key_hash)
            reps.append(cold_request(h, args, key_hash, h.web(i).port,
                                     watch=True))
            time.sleep(2)
        record[name] = reps
        summarize_cold(name, reps)
    name, args = COLD[1]
    took, kinds = [], []
    for i in range(h.n):
        seconds, status, answer = common.board(h.web(i).port, args, h.cookie)
        if not common.is_board(answer):
            raise RuntimeError('a repeated limit=100 read was not a board')
        took.append(seconds)
        kinds.append('stale' if answer['stale'] else 'ready')
    record['limit=100 repeated'] = {'ms': common.triple(took),
                                    'ready': kinds.count('ready'),
                                    'rows': len(answer['rows'])}
    print(f"\n  limit=100 repeated (ready reads)   {common.fmt(took)}"
          f"   {kinds.count('ready')} ready; {len(answer['rows'])} rows")
    return record


# --- (b) empty store ----------------------------------------------------------------

def phase_empty(h):
    print('\n=== (b) empty store: TRUNCATE both tables, then one request ===')
    print('    the eight warm selections in turn; each rep starts with the'
          ' producer idle and every warm board fresh')
    warm = common.warm_args()
    reps = []
    for i in range(h.n):
        args = warm[i % len(warm)]
        key_hash, _ = common.key_of(args)
        common.wait_ready_idle(h.engine, h.ns, timeout=900)
        common.truncate_store(h.engine)
        rep = cold_request(h, args, key_hash, h.web(i).port, watch=True)
        sweep = common.wait_ready_idle(h.engine, h.ns, timeout=900)
        order = sorted((r for r in common.ns_rows(h.engine, h.ns) if r['warm']),
                       key=lambda r: r['as_of'])
        rep['built_position'] = 1 + [r['key_hash'] for r in order].index(
            key_hash)
        rep['label'] = common.label(args)
        rep['rest_of_sweep_s'] = round(sweep, 1)
        reps.append(rep)
        print(f"  {i + 1:2d} {rep['label']:20s} pending {rep['first_ms']:6.1f} ms"
              f"  built {rep['built_position']}/8  published"
              f" {rep.get('detected_s', float('nan')):6.2f} s  read"
              f" {rep.get('read_ms', float('nan')):6.1f} ms  client saw it"
              f" {rep.get('seen_s') or float('nan'):6.2f} s", flush=True)
    summarize_cold('empty store', reps)
    return {'reps': reps}


# --- (f) and (g): queue age under steady demand ----------------------------------

VARIANTS = (
    {'sort': 'mentions'}, {'sort': 'divergence'}, {'sort': 'ratio'},
    {'sort': 'move'}, {'sort': 'ticker', 'dir': 'asc'}, {'limit': '100'},
    {'venues': '2'}, {'segment': 'large'}, {'segment': 'fund'},
    {'segment': 'mid,micro'}, {'sort': 'mentions', 'dir': 'asc'},
    {'segment': 'recent_ipo'}, {'limit': '25'}, {'sort': 'move', 'dir': 'asc'},
    {'venues': '2', 'limit': '100'},
)


def on_demand(index):
    """The index-th on-demand selection: every window, both markets, fifteen
    variants -- 120 distinct keys, none of them warm."""
    args = {'market': ('us', 'de')[(index // 4) % 2], 'segment': '',
            'window': str((1, 4, 12, 24)[index % 4])}
    args.update(VARIANTS[(index // 8) % len(VARIANTS)])
    return args


def _sampler(h, samples, stop, period=5.0):
    due = time.perf_counter()
    while not stop.is_set():
        samples.append((common.utcnow(), common.ns_rows(h.engine, h.ns)))
        due += period
        stop.wait(max(0.0, due - time.perf_counter()))


def analyse(samples, results, builds, duration):
    warm_ages, demand_waiting, stale, expired = [], [], 0, 0
    pairs = {}
    for at, rows in samples:
        for row in rows:
            if row['warm'] and row['as_of'] is not None:
                age = (at - row['as_of']).total_seconds()
                warm_ages.append(age)
                stale += age > FRESH_S
                expired += age > EXPIRY_S
                pairs.setdefault(row['key_hash'], set()).add(
                    (row['as_of'], row['built_at']))
            elif (not row['warm'] and row['queue_state'] in
                  ('pending', 'building') and row['enqueued_at']):
                demand_waiting.append((at - row['enqueued_at'])
                                      .total_seconds())
    replaced_at, intervals = [], []
    for seen in pairs.values():
        ordered = sorted(seen)
        for (old_as_of, _), (new_as_of, new_built) in zip(ordered,
                                                          ordered[1:]):
            replaced_at.append((new_built - old_as_of).total_seconds())
            intervals.append((new_as_of - old_as_of).total_seconds())
    got = [r for r in results if r.get('seen_s') is not None]
    warm_ms = [b['build_ms'] for b in builds if b['cls'] == 'warm']
    demand_ms = [b['build_ms'] for b in builds if b['cls'] == 'ondemand']
    return {
        'samples': len(samples),
        'warm_age_sampled_max_s': round(max(warm_ages), 1) if warm_ages else None,
        'warm_samples': len(warm_ages), 'warm_samples_stale': stale,
        'warm_samples_expired': expired,
        'warm_age_when_replaced_s': [round(v, 1) for v in sorted(replaced_at)],
        'warm_refresh_interval_s': [round(v, 1) for v in sorted(intervals)],
        'demand_requests': len(results), 'demand_delivered': len(got),
        'demand_seen_s': [r['seen_s'] for r in got],
        'demand_queue_wait_s': [r['queue_wait_s'] for r in got
                                if 'queue_wait_s' in r],
        'demand_first_ms': [r['first_ms'] for r in results],
        'demand_sampled_waiting_max_s': (round(max(demand_waiting), 1)
                                         if demand_waiting else 0.0),
        'builds_warm': len(warm_ms), 'builds_ondemand': len(demand_ms),
        'build_s_warm': common.triple([v / 1000 for v in warm_ms], scale=1.0),
        'build_s_ondemand': common.triple([v / 1000 for v in demand_ms],
                                          scale=1.0),
        'build_s_ondemand_by_window': {
            window: common.triple(
                [r['build_ms'] / 1000 for r in results
                 if r.get('build_ms') is not None
                 and r['args'].get('window') == window], scale=1.0)
            for window in sorted({r['args'].get('window') for r in results
                                  if r.get('build_ms') is not None},
                                 key=int)},
        'slowest_ondemand': sorted(
            ({'label': r['label'], 'build_ms': r['build_ms']} for r in results
             if r.get('build_ms') is not None),
            key=lambda item: -item['build_ms'])[:5],
        'producer_busy_share': round(sum(warm_ms + demand_ms) / 1000
                                     / duration, 3),
        'results': results,
    }


def report_queue(tag, a):
    print(f'\n  {tag}: {a["samples"]} table samples; {a["builds_warm"]} warm and'
          f' {a["builds_ondemand"]} on-demand builds; producer busy'
          f' {100 * a["producer_busy_share"]:.0f}% of the window')
    print(f"  warm board age, sampled every 5 s: max {a['warm_age_sampled_max_s']}"
          f" s; {a['warm_samples_stale']} of {a['warm_samples']} samples past"
          f" {FRESH_S:.0f} s, {a['warm_samples_expired']} past {EXPIRY_S:.0f} s")
    print(_line('warm board age when its refresh landed',
                a['warm_age_when_replaced_s']))
    print(_line('warm refresh interval (as_of to as_of)',
                a['warm_refresh_interval_s']))
    print(_line('on-demand wait, request -> board in hand', a['demand_seen_s']))
    print(_line('on-demand queue wait (enqueued -> as_of)',
                a['demand_queue_wait_s']))
    print(f"  on-demand delivered {a['demand_delivered']} of"
          f" {a['demand_requests']}; the longest a key sat queued in a sample:"
          f" {a['demand_sampled_waiting_max_s']} s")
    print(f"  build seconds: warm {a['build_s_warm']}, on-demand"
          f" {a['build_s_ondemand']} (median, p95, max)")
    print('  on-demand build seconds by window (median, p95, max): ' + '; '.join(
        f'{window}h {values}' for window, values in
        a['build_s_ondemand_by_window'].items()))
    print('  (busy share counts every build whose log line landed in the'
          ' window, so a build begun just before it is included)')
    print('  slowest on-demand builds: ' + '; '.join(
        f"{item['label']} {item['build_ms'] / 1000:.1f} s"
        for item in a['slowest_ondemand']))
    replaced = a['warm_age_when_replaced_s']
    sampled = a['warm_age_sampled_max_s'] or 0.0
    worst = max(replaced + [sampled])
    if not replaced:
        print('  the 120 s bound: NO warm refresh landed inside the window, so'
              ' no replacement age exists; sampled max'
              f' {sampled:.1f} s')
    print(f'  the 120 s bound: the worst warm board age seen was {worst:.1f} s'
          f" -> fresh {FRESH_S:.0f} s {'HELD' if worst <= FRESH_S else 'EXCEEDED'};"
          f" hard expiry {EXPIRY_S:.0f} s "
          f"{'HELD' if worst <= EXPIRY_S else 'EXCEEDED'}; "
          f"{a['warm_samples_stale']} of {a['warm_samples']} warm samples were"
          ' served stale')


def phase_queue(h, args, *, tag='queue', first_index=0, writer=None):
    duration, interval = args.duration, args.interval
    print(f'\n=== ({"g" if writer else "f"}) queue age: {duration:.0f} s, one'
          f' on-demand request every {interval:.0f} s, warm keys on their'
          f' 120 s refresh ===')
    samples, results, viewers = [], [], []
    stop = threading.Event()
    sampler = threading.Thread(target=_sampler, args=(h, samples, stop),
                               daemon=True)
    mark = len(h.producer.text())
    locks = common.lock_status(h.engine)
    writer_child = None
    sampler.start()
    if writer:
        writer_child = common.Child(
            f'writer-{tag}', common.HERE / 'write_contention_perf3.py',
            ['--offsets', writer, '--out', h.out / f'writes-{tag}.json'],
            h.out / f'writer-{tag}.log', common.child_env())
        h.children.append(writer_child)
    began = time.perf_counter()
    for i in range(int(duration // interval)):
        delay = began + i * interval - time.perf_counter()
        if delay > 0:
            time.sleep(delay)
        request = on_demand(first_index + i)
        key_hash, _ = common.key_of(request)
        common.delete_key(h.engine, h.ns, key_hash)
        slot = {'i': i, 'label': common.label(request),
                'sent_after_s': round(time.perf_counter() - began, 2)}

        def run(slot=slot, request=request, key_hash=key_hash,
                port=h.web(i).port):
            slot.update(cold_request(h, request, key_hash, port, timeout=900))

        viewer = threading.Thread(target=run, daemon=True)
        viewer.start()
        viewers.append(viewer)
        results.append(slot)
    rest = began + duration - time.perf_counter()
    if rest > 0:
        time.sleep(rest)
    stop.set()
    sampler.join(timeout=30)
    for viewer in viewers:
        viewer.join(timeout=900)
    record = analyse(samples, results, common.parse_builds(
        h.producer.text()[mark:]), duration)
    record['locks'] = common.lock_delta(locks, common.lock_status(h.engine))
    if writer_child:
        writer_child.wait_line('WRITE-DONE', timeout=900)
        record['writes'] = json.loads((h.out / f'writes-{tag}.json')
                                      .read_text())
        writer_child.kill()
    report_queue(tag, record)
    return record


def phase_contention(h, args):
    print('\n=== (g) the write alone, then the sweep under the write ===')
    h.stop_producer()
    alone = common.Child('writer-alone', common.HERE / 'write_contention_perf3.py',
                         ['--offsets', '0,0,0', '--out',
                          h.out / 'writes-alone.json'],
                         h.out / 'writer-alone.log', common.child_env())
    h.children.append(alone)
    alone.wait_line('WRITE-DONE', timeout=900)
    alone.kill()
    writes_alone = json.loads((h.out / 'writes-alone.json').read_text())
    h.start_producer(name='producer-g')
    common.wait_ready_idle(h.engine, h.ns, timeout=900)
    # 10%, 40% and 70% into the window: 60, 240 and 420 s of ten minutes.
    offsets = ','.join(f'{args.duration * share:.0f}'
                       for share in (0.1, 0.4, 0.7))
    record = phase_queue(h, args, tag='contention', first_index=60,
                         writer=offsets)
    record['writes_alone'] = writes_alone
    live = writes_alone['live_hour']
    print(f'\n  the write: {writes_alone["runs"][0]["rows"]:,} rows of the'
          f' live hour {live}, write_cost.py\'s UPDATE, committed')
    for side, runs in (('alone', writes_alone['runs']),
                       ('under the sweep', record['writes']['runs'])):
        print(f'    {side:16s} update ' + ', '.join(
            f"{r['update_s']:.2f} s" for r in runs) + '   restore ' + ', '.join(
            f"{r['restore_s']:.2f} s" for r in runs))
    return record


PHASES = {
    'ready': lambda h, a: phase_ready(h),
    'memory': lambda h, a: phase_memory(h),
    'restart': lambda h, a: phase_restart(h),
    'cold': lambda h, a: phase_cold(h),
    'empty': lambda h, a: phase_empty(h),
    'queue': lambda h, a: phase_queue(h, a),
    'contention': phase_contention,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', default='all')
    parser.add_argument('--n', type=int, default=20)
    parser.add_argument('--out')
    parser.add_argument('--duration', type=float, default=600.0)
    parser.add_argument('--interval', type=float, default=10.0)
    args = parser.parse_args()
    phases = list(PHASES) if args.phase == 'all' else args.phase.split(',')
    unknown = [p for p in phases if p not in PHASES]
    if unknown:
        raise SystemExit(f'unknown phase(s) {unknown}')

    import env_check
    env_check.preflight('measure_perf3 (Step 1): ' + ','.join(phases))
    out = common.out_dir(args.out)
    h = Harness(out, args.n)
    record = {'phases': phases, 'n': args.n}
    with app.app_context():
        try:
            common.truncate_store(h.engine)
            began = time.perf_counter()
            h.start_producer(name='producer')
            h.start_webs()
            common.wait_ready_idle(h.engine, h.ns, timeout=900)
            record['prewarm_s'] = round(time.perf_counter() - began, 1)
            # Before any read: the web processes have only been started.
            h.memory_at_start = {child.name: common.working_set(child.pid)
                                 for child in [h.producer] + h.webs}
            record['memory_at_start'] = h.memory_at_start
            first = common.parse_builds(h.producer.text())
            record['prewarm_builds_ms'] = [b['build_ms'] for b in first]
            record['web_ready_s'] = [round(w.ready_s, 2) for w in h.webs]
            print(f"\nprewarm from an empty store: {record['prewarm_s']} s"
                  f' (producer start -> 8 warm boards fresh); builds'
                  f" {record['prewarm_builds_ms']} ms")
            h.account()
            for phase in phases:
                result = PHASES[phase](h, args)
                record[phase] = result
                common.save(out, f'measure-{phase}.json', result)
            record['producer_end'] = common.working_set(h.producer.pid)
            print(f"\nproducer at the end: {record['producer_end']}")
        finally:
            h.close()
            db.session.remove()
    common.save(out, 'measure.json', {k: v for k, v in record.items()
                                      if k not in PHASES})


if __name__ == '__main__':
    main()

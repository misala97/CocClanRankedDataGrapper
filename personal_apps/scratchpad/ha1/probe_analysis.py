"""HA1 bounded-reader measurement (PLAN C13/C14) on an authorized HA1 target.

    py -3.12 scratchpad/ha1/probe_analysis.py

CORRECTION-1 (2026-09-15): rewritten for REVIEW-1 P1-1/P1-2/R3; NOT executed
(no authorized HA1 target; DB/preview execution held).

Gated exactly as local_runtime.py (RADAR_HA1_TARGET + RADAR_HA1_REGISTRY,
checked before the app is imported). Then, inside one app context:

- The admin id is read as a scalar while the session is live.
- Owned fixtures: run-unique symbols, refused before any write if any exists,
  every row recorded by exact key, removed in the fixture block's exit
  whatever happens (including the overflow sentinel). No module constant is
  mutated, so nothing needs restoring.
- Zero, typical and max (7 x 96 x 64 = 43,008 rows / 64 sources) fixtures:
  one cold and twenty warm authenticated HTTP requests each, with the data
  statement count per request; latency is measured WITHOUT tracemalloc.
- Separately, incremental reader allocation: tracemalloc around
  analysis.read_company itself (materialization and reduction included),
  baseline taken immediately before, peak minus baseline.
- EXPLAIN of the reader's own named SQL with the exact binds it sends
  (analysis.data_statements), never re-wrapped driver SQL.
- Two separate refusals: 65 sources in 65 rows, and the 43,009th row with
  still 64 sources (an off-grid sentinel), then the sentinel removed and the
  max fixture read again.
- Statement timeout on ONE physical connection: SLEEP and a CPU-bound
  statement through the production SqlStore, connection id and session
  max_statement_time before/after; an uncancelled statement is a failure.

CORRECTION-2 (2026-09-15, harness only; still NOT executed):
- U5: the timeout probe adds a CPU-bound statement under the 0.250 s limit
  ReaderBudget computes (requested/effective limit, rendered prefix, elapsed,
  overshoot, post-hoc budget check, same-connection recovery).
- Deadline ruling: five seconds is the reader/resolver budget, excluding
  pre-reader authentication and pool wait; it is NOT a hard full-HTTP
  cancellation guarantee. Measured SEPARATELY here: statement interruption
  delay (timeout probes), reader elapsed time and overshoot on a read whose
  statements consume the limits the reader hands them, and full-request
  duration of the same exhaustion over HTTP (with the time before the first
  reader statement recorded). A budget-exhausted read must never succeed; the
  overshoot numbers are returned for a Mastermind ruling, never self-approved.
  Normal reads also record reader-only elapsed time next to full-request
  latency.
- U7: the report keeps the original failure AND the fixture cleanup outcome
  with any owned identities still present; the process exits nonzero.
- U8: the source/build fingerprint is recorded at start and end; drift during
  the run is a failure.
- U10: the timeout dialect is recorded only after the admin lookup has
  connected and initialized the engine dialect.

Every budget is asserted (ha1_harness.budget_failures etc.). The JSON report
is written to radar-design/artifacts/ha1/runtime/probe_analysis.json whatever
happens, and the process exits 1 on any failure. Synthetic data only.
"""
import datetime as dt
import gc
import json
import platform
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import ha1_harness as harness  # noqa: E402
import local_runtime  # noqa: E402

host, port, database, target, registry = local_runtime.gate()
app = local_runtime.bind(host, port, database, target, registry)

import sqlalchemy as sa  # noqa: E402
from sqlalchemy import event  # noqa: E402

import ha1_fixtures as fx  # noqa: E402
from extensions import db  # noqa: E402
from features.radar import analysis as analysis_mod  # noqa: E402
from features.radar.analysis_contract import ContractError  # noqa: E402
from models import AppUser  # noqa: E402

OUT = local_runtime.RUNTIME_DIR
FROM, TO = dt.date(2026, 9, 7), dt.date(2026, 9, 13)
DAYS = [FROM + dt.timedelta(days=n) for n in range(7)]
LIMIT_S = 1.0
URL = '/radar/api/analysis/company/{company}?instrument_id={instrument}&from={start}&to={end}'
TABLES = ('radar_ticker_universe', 'radar_instruments', 'radar_daily_closes', 'radar_bucket_sources')
READER_METHODS = ('company_by_id', 'instrument_by_id', 'daily_closes', 'bucket_sources')
#: The deadline probe spends the limit each of these statements is handed
#: (without being interrupted), so the budget runs out inside the read.
CONSUMING_METHODS = ('company_by_id', 'instrument_by_id', 'daily_closes')
SLEEP_SQL = 'SELECT SLEEP(:seconds) AS value'
SLEEP_MARGIN_S = 0.05
READER_ELAPSED_RUNS = 5


class CountingStore(analysis_mod.SqlStore):
    """The production store, recording rows and distinct sources per read."""

    def __init__(self, statement_floor_s=None):
        super().__init__()
        self.reads = []
        self.statement_floor_s = statement_floor_s

    def _rows(self, sql, timeout_s, **params):
        sent = timeout_s if self.statement_floor_s is None else max(timeout_s, self.statement_floor_s)
        rows = super()._rows(sql, sent, **params)
        table = next((name for name in TABLES if name in sql), 'other')
        self.reads.append({
            'table': table, 'rows': len(rows), 'timeout_s': timeout_s, 'sent_limit_s': sent,
            'sources': (len({row.get('source') for row in rows})
                        if table == 'radar_bucket_sources' else None)})
        return rows


def url(company, instrument):
    return URL.format(company=company, instrument=instrument, start=FROM, end=TO)


def seed(owned, symbols):
    session = db.session
    ids = {}
    for role in ('Z', 'T', 'M', 'S'):
        symbol = symbols[role]
        company = fx.add_company(owned, session, symbol)
        instrument = fx.add_instrument(owned, session, symbol)
        rows = 0
        if role == 'T':
            for day in DAYS[1:5]:
                fx.add_close(owned, session, symbol, day)
            for day in DAYS:
                for source in ('bluesky', 'fourchan', 'reddit:wallstreetbets'):
                    rows += fx.add_buckets(owned, session, fx.bucket_rows(symbol, day, source))
        elif role == 'M':
            for day in DAYS:
                fx.add_close(owned, session, symbol, day)
                for n in range(harness.MAX_SOURCES):
                    rows += fx.add_buckets(owned, session,
                                           fx.bucket_rows(symbol, day, f'zqsrc{n:02d}', count=n % 3))
        elif role == 'S':
            for n in range(harness.MAX_SOURCES + 1):
                rows += fx.add_buckets(owned, session,
                                       fx.bucket_rows(symbol, FROM, f'zqsrc{n:02d}', slots=range(1)))
        ids[role] = (company, instrument, rows)
    session.commit()
    return ids


def http_latency(client, company, instrument):
    current = []

    def before(conn, cursor, statement, parameters, context, executemany):
        if 'radar_' in statement and '@@' not in statement:
            current.append(statement)
    event.listen(db.engine, 'before_cursor_execute', before)
    timings, statuses, sizes, counts = [], [], [], []
    try:
        for _ in range(1 + harness.WARM_REQUESTS):
            current.clear()
            started = time.perf_counter()
            response = client.get(url(company, instrument))
            body = response.get_data()
            timings.append((time.perf_counter() - started) * 1000)
            statuses.append(response.status_code)
            sizes.append(len(body))
            counts.append(len(current))
    finally:
        event.remove(db.engine, 'before_cursor_execute', before)
    warm = [round(value, 2) for value in timings[1:]]
    return {'cold_ms': round(timings[0], 2), 'warm_ms': warm,
            'warm_median_ms': round(sorted(warm)[len(warm) // 2], 2),
            'warm_p95_ms': harness.nearest_rank_p95(warm),
            'statuses': statuses, 'response_bytes': max(sizes),
            'max_data_statements': max(counts)}


def reader_elapsed(company, instrument):
    """Reader-only duration (no HTTP, no auth, no tracemalloc), recorded next
    to the full-request latency so the two are never conflated."""
    runs = []
    for _ in range(READER_ELAPSED_RUNS):
        started = time.perf_counter()
        analysis_mod.read_company(company, instrument, FROM, TO,
                                  dt.datetime.now(dt.timezone.utc), store=analysis_mod.SqlStore())
        runs.append(round((time.perf_counter() - started) * 1000, 2))
    db.session.rollback()
    return {'reader_elapsed_ms': runs, 'reader_elapsed_max_ms': max(runs)}


def reader_allocation(company, instrument):
    runs = []
    tracemalloc.start()
    try:
        for _ in range(3):
            # Traced reads only: see ha1_harness.TRACED_STATEMENT_LIMIT_S.
            store = CountingStore(statement_floor_s=harness.TRACED_STATEMENT_LIMIT_S)
            gc.collect()
            baseline = tracemalloc.get_traced_memory()[0]
            tracemalloc.reset_peak()
            payload = analysis_mod.read_company(company, instrument, FROM, TO,
                                                dt.datetime.now(dt.timezone.utc), store=store)
            peak = tracemalloc.get_traced_memory()[1]
            runs.append((peak - baseline, store.reads))
            del payload
    finally:
        tracemalloc.stop()
    reads = runs[-1][1]
    buckets = next(read for read in reads if read['table'] == 'radar_bucket_sources')
    return {'reader_alloc_bytes': max(run[0] for run in runs),
            'reader_alloc_runs_bytes': [run[0] for run in runs],
            'bucket_rows': buckets['rows'], 'distinct_sources': buckets['sources'],
            'reads': reads}


def explain(company, instrument, symbol):
    plans, failures = [], []
    read_start = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    for name, sql, params in analysis_mod.data_statements(company, instrument, symbol, 'XNYS',
                                                          FROM, TO, read_start):
        rows = [dict(row) for row in
                db.session.execute(sa.text('EXPLAIN ' + sql), params).mappings().all()]
        plans.append({'statement': name, 'plan': rows})
        failures += harness.plan_failures(name, rows)
    db.session.rollback()
    return plans, failures


def refusal(client, company, instrument):
    response = client.get(url(company, instrument))
    body = response.get_json(silent=True) or {}
    return response.status_code, body.get('code')


# --- the five-second reader budget ------------------------------------------------

def _exhausting(name, original, calls, clock):
    def method(self, *args, timeout_s, **kwargs):
        calls.append({'method': name, 'handed_timeout_s': timeout_s,
                      'issued_at_s': round(time.perf_counter() - clock[0], 4)})
        if name in CONSUMING_METHODS:
            self._rows(SLEEP_SQL, timeout_s, seconds=max(0.0, timeout_s - SLEEP_MARGIN_S))
        return original(self, *args, timeout_s=timeout_s, **kwargs)
    return method


def deadline_reader(company, instrument):
    """read_company with a store whose identity and closes statements first
    spend (almost) the whole limit the reader handed them. The reader's own
    budget arithmetic decides every limit; nothing in the product is changed."""
    calls, clock = [], [0.0]
    store_class = type('DeadlineStore', (analysis_mod.SqlStore,), {
        name: _exhausting(name, getattr(analysis_mod.SqlStore, name), calls, clock)
        for name in READER_METHODS})
    status, code = 200, None
    clock[0] = time.perf_counter()
    try:
        analysis_mod.read_company(company, instrument, FROM, TO,
                                  dt.datetime.now(dt.timezone.utc), store=store_class())
    except ContractError as error:
        status, code = error.status, error.code
    elapsed = time.perf_counter() - clock[0]
    db.session.rollback()
    return {'status': status, 'code': code, 'elapsed_s': round(elapsed, 3),
            'overshoot_s': round(elapsed - harness.READER_BUDGET_S, 3), 'calls': calls,
            'handed_timeouts_s': [call['handed_timeout_s'] for call in calls]}


def deadline_http(client, company, instrument):
    """The same exhaustion through the authenticated route, so full-request
    duration is measured separately from the reader's. The store methods are
    wrapped for this one request and restored in `finally`."""
    calls, clock = [], [0.0]
    originals = {name: getattr(analysis_mod.SqlStore, name) for name in READER_METHODS}
    for name, original in originals.items():
        setattr(analysis_mod.SqlStore, name, _exhausting(name, original, calls, clock))
    try:
        clock[0] = time.perf_counter()
        response = client.get(url(company, instrument))
        full = time.perf_counter() - clock[0]
    finally:
        for name, original in originals.items():
            setattr(analysis_mod.SqlStore, name, original)
    body = response.get_json(silent=True) or {}
    first = calls[0]['issued_at_s'] if calls else None
    return {'status': response.status_code, 'code': body.get('code'),
            'full_request_ms': round(full * 1000, 1), 'elapsed_s': round(full, 3),
            'overshoot_s': round(full - harness.READER_BUDGET_S, 3),
            'before_first_reader_statement_s': first, 'calls': calls,
            'handed_timeouts_s': [call['handed_timeout_s'] for call in calls]}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    token = harness.run_token()
    symbols = {role: harness.owned_symbol(role, token) for role in ('Z', 'T', 'M', 'S')}
    report = {
        'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'target': target, 'synthetic': True, 'symbols': symbols,
        'hardware': {'machine': platform.machine(), 'processor': platform.processor(),
                     'python': platform.python_version()},
        'fingerprint_start': None, 'fixtures': {}, 'failures': [],
    }
    failures = report['failures']
    fingerprint = harness.source_fingerprint(local_runtime.CANDIDATE)
    report['fingerprint_start'] = {'digest': fingerprint['digest'], 'files': len(fingerprint['files'])}
    app.config['TESTING'] = True
    owned = None
    original = None
    try:
        with app.app_context():
            report['engine'] = f'{db.engine.dialect.name} {db.engine.dialect.server_version_info}'
            admin_id = db.session.execute(
                sa.select(AppUser.id).where(AppUser.is_admin.is_(True))
                .order_by(AppUser.id).limit(1)).scalar()
            db.session.rollback()
            # U10: only now has a connection initialized the dialect.
            report['dialect'] = harness.dialect_record(db.engine.dialect,
                                                       analysis_mod.SqlStore().timeout_dialect)
            report['engine'] = f'{db.engine.dialect.name} {db.engine.dialect.server_version_info}'
            if report['dialect']['failure']:
                failures.append(report['dialect']['failure'])
            if admin_id is None:
                raise SystemExit('the disposable target needs an admin account; nothing was seeded')
            admin_id = int(admin_id)
            owned = harness.OwnedFixtures(fx.SqlFixtureStore(db.session), symbols.values())
            with owned:
                ids = seed(owned, symbols)
                with app.test_client() as client:
                    with client.session_transaction() as flask_session:
                        flask_session['user_id'] = admin_id
                    for role, label in (('Z', 'zero'), ('T', 'typical'), ('M', 'max')):
                        company, instrument, seeded_rows = ids[role]
                        entry = http_latency(client, company, instrument)
                        entry.update(reader_elapsed(company, instrument))
                        entry.update(reader_allocation(company, instrument))
                        entry['bucket_rows_seeded'] = seeded_rows
                        entry['plans'], plan_problems = explain(company, instrument, symbols[role])
                        entry['failures'] = harness.budget_failures(label, entry) + plan_problems
                        if entry['bucket_rows'] != seeded_rows:
                            entry['failures'].append(
                                f'{label}: read {entry["bucket_rows"]} bucket rows, seeded {seeded_rows}')
                        failures.extend(entry['failures'])
                        report['fixtures'][label] = entry
                    if ids['M'][2] != harness.BUCKET_ROW_CAP:
                        failures.append(f'max fixture seeded {ids["M"][2]} rows, not {harness.BUCKET_ROW_CAP}')

                    # Refusal 1: 65 sources in only 65 rows.
                    company, instrument, rows = ids['S']
                    status, code = refusal(client, company, instrument)
                    report['source_limit'] = {'rows': rows, 'sources': harness.MAX_SOURCES + 1,
                                              'status': status, 'code': code}
                    if (status, code) != (503, 'analysis_limit') or rows != harness.MAX_SOURCES + 1:
                        failures.append(f'source limit: {report["source_limit"]}')

                    # Refusal 2: the 43,009th row, still 64 sources.
                    company, instrument, _ = ids['M']
                    sentinel = {'ticker': symbols['M'], 'source': 'zqsrc00', 'mention_count': 1,
                                'status': 'ok', 'source_config_version': 'cfgA',
                                'bucket_start': harness.off_grid_sentinel(FROM)}
                    fx.add_buckets(owned, db.session, [sentinel])
                    db.session.commit()
                    status, code = refusal(client, company, instrument)
                    report['row_limit'] = {'rows': harness.BUCKET_ROW_SENTINEL,
                                           'sources': harness.MAX_SOURCES,
                                           'status': status, 'code': code}
                    if (status, code) != (503, 'analysis_limit'):
                        failures.append(f'row limit: {report["row_limit"]}')
                    owned.delete_now('bucket', {'ticker': sentinel['ticker'],
                                                'bucket_start': sentinel['bucket_start'],
                                                'source': sentinel['source']})
                    restored = client.get(url(company, instrument)).status_code
                    report['row_limit']['status_after_sentinel_removed'] = restored
                    if restored != 200:
                        failures.append(f'row limit: max fixture answered {restored} after the sentinel was removed')

                    # Statement timeout, sub-second limit and hygiene on one physical connection.
                    report['timeout'] = fx.timeout_probe(db.engine, LIMIT_S)
                    failures.extend(harness.timeout_failures(report['timeout'], LIMIT_S))
                    company, instrument, _ = ids['T']
                    report['after_timeout_status'] = client.get(url(company, instrument)).status_code
                    if report['after_timeout_status'] != 200:
                        failures.append(f'the request after the timeout probe answered {report["after_timeout_status"]}')

                    # The five-second reader budget, measured three ways (ruling 2026-09-15).
                    company, instrument, _ = ids['M']
                    probes = report['timeout'].get('probes') or {}
                    report['deadline'] = {
                        'scope': 'reader/resolver budget excluding pre-reader auth and pool wait; '
                                 'not a hard full-HTTP cancellation guarantee',
                        'statement_interruption_delay_s': {
                            'cpu': (round(probes['cpu']['elapsed_s'] - LIMIT_S, 3) if probes.get('cpu') else None),
                            'cpu_subsecond': (probes.get('cpu_subsecond') or {}).get('overshoot_s')},
                        'reader': deadline_reader(company, instrument),
                        'http': deadline_http(client, company, instrument),
                        'acceptance': harness.DEADLINE_ACCEPTANCE,
                    }
                    failures.extend(harness.deadline_failures(report['deadline']))
                    report['after_deadline_status'] = client.get(url(company, instrument)).status_code
                    if report['after_deadline_status'] != 200:
                        failures.append(f'the request after the deadline probe answered {report["after_deadline_status"]}')
    except BaseException as exc:  # noqa: BLE001 -- recorded with the cleanup outcome, then re-raised
        original = exc
        raise
    finally:
        outcome = harness.run_failure_report(original, owned)
        report['original_failure'] = outcome['original_failure']
        report['cleanup'] = outcome['cleanup']
        failures.extend(outcome['failures'])
        end = harness.source_fingerprint(local_runtime.CANDIDATE)
        report['fingerprint_end'] = {'digest': end['digest'], 'files': len(end['files'])}
        if end['digest'] != fingerprint['digest']:
            changed = sorted(name for name in set(fingerprint['files']) | set(end['files'])
                             if fingerprint['files'].get(name) != end['files'].get(name))
            failures.append(f'source/build drift during the probe ({", ".join(changed[:12])}); '
                            'the measurement does not describe one candidate')
        report['finished_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
        (OUT / 'probe_analysis.json').write_text(json.dumps(report, indent=2, default=str),
                                                 encoding='utf-8')
        print(json.dumps({key: value for key, value in report.items() if key != 'fixtures'},
                         indent=2, default=str))
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

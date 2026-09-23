"""LOCAL-QA diagnosis: why the max fixture's traced allocation read hit the limit.

    py -3.12 ../radar-design/artifacts/ha1/local-qa/diag_max_read.py   (cwd personal_apps)

Gated like the harness. Seeds ONE owned max fixture (7 x 96 x 64 = 43,008
bucket rows, 64 sources, 7 closes) through ha1_harness.OwnedFixtures, then:
- five untraced read_company calls, per statement: handed limit and elapsed;
- the bucket SELECT alone through SqlStore._rows with tracemalloc on/off
  (server-side execution vs client fetch time is what max_statement_time sees);
- one traced read_company, recording where it fails.
Cleans exactly its owned rows. No product change, no secret printed.
"""
import datetime as dt
import gc
import json
import os
import sys
import time
import tracemalloc
from pathlib import Path

PERSONAL = Path(__file__).resolve().parents[4] / 'personal_apps'
sys.path.insert(0, str(PERSONAL))
sys.path.insert(0, str(PERSONAL / 'scratchpad' / 'ha1'))
os.chdir(PERSONAL)

import local_runtime  # noqa: E402

host, port, database, target, registry = local_runtime.gate()
app = local_runtime.bind(host, port, database, target, registry)

import ha1_fixtures as fx  # noqa: E402
import ha1_harness as harness  # noqa: E402
from extensions import db  # noqa: E402
from features.radar import analysis as analysis_mod  # noqa: E402
from features.radar.analysis_contract import ContractError  # noqa: E402

FROM, TO = dt.date(2026, 9, 7), dt.date(2026, 9, 13)
DAYS = [FROM + dt.timedelta(days=n) for n in range(7)]


class TimedStore(analysis_mod.SqlStore):
    def __init__(self):
        super().__init__()
        self.calls = []

    def _rows(self, sql, timeout_s, **params):
        started = time.perf_counter()
        error = None
        try:
            rows = super()._rows(sql, timeout_s, **params)
            return rows
        except ContractError as exc:
            error = f'{exc.code}: {exc}'
            raise
        finally:
            table = next((t for t in ('radar_ticker_universe', 'radar_instruments', 'radar_daily_closes',
                                      'radar_bucket_sources') if t in sql), 'other')
            self.calls.append({'table': table, 'handed_s': timeout_s,
                               'elapsed_s': round(time.perf_counter() - started, 3), 'error': error})


def read(traced):
    store = TimedStore()
    outcome = 'ok'
    if traced:
        tracemalloc.start()
        gc.collect()
        baseline = tracemalloc.get_traced_memory()[0]
        tracemalloc.reset_peak()
    started = time.perf_counter()
    try:
        analysis_mod.read_company(ids[0], ids[1], FROM, TO, dt.datetime.now(dt.timezone.utc), store=store)
    except ContractError as exc:
        outcome = f'{exc.status} {exc.code}'
    elapsed = round(time.perf_counter() - started, 3)
    peak = None
    if traced:
        peak = tracemalloc.get_traced_memory()[1] - baseline
        tracemalloc.stop()
    db.session.rollback()
    return {'traced': traced, 'outcome': outcome, 'elapsed_s': elapsed, 'alloc_peak_bytes': peak,
            'calls': store.calls}


out = {'target': target, 'synthetic': True}
token = harness.run_token()
symbol = harness.owned_symbol('D', token)
with app.app_context():
    owned = harness.OwnedFixtures(fx.SqlFixtureStore(db.session), [symbol])
    with owned:
        company = fx.add_company(owned, db.session, symbol)
        instrument = fx.add_instrument(owned, db.session, symbol)
        rows = 0
        for day in DAYS:
            fx.add_close(owned, db.session, symbol, day)
            for n in range(harness.MAX_SOURCES):
                rows += fx.add_buckets(owned, db.session, fx.bucket_rows(symbol, day, f'zqsrc{n:02d}', count=n % 3))
        db.session.commit()
        ids = (company, instrument)
        out['seeded_bucket_rows'] = rows
        out['untraced'] = [read(False) for _ in range(5)]
        bucket_alone = {}
        for traced in (False, True):
            store = analysis_mod.SqlStore()
            if traced:
                tracemalloc.start()
            started = time.perf_counter()
            try:
                got = len(store._rows(analysis_mod.BUCKET_SOURCES, 30.0,
                                      **analysis_mod.buckets_params(symbol, FROM, TO)))
                error = None
            except ContractError as exc:
                got, error = None, exc.code
            bucket_alone['traced' if traced else 'untraced'] = {
                'limit_s': 30.0, 'rows': got, 'error': error,
                'elapsed_s': round(time.perf_counter() - started, 3)}
            if traced:
                tracemalloc.stop()
            db.session.rollback()
        out['bucket_select_alone_30s_limit'] = bucket_alone
        out['traced'] = [read(True) for _ in range(2)]
    out['cleanup'] = owned.cleanup_report()
print(json.dumps(out, indent=2, default=str))

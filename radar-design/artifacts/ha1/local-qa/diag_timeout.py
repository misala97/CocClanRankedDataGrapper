"""LOCAL-QA diagnosis: full timeout_probe result plus raw engine behaviour.

Gated exactly like the harness. Prints the complete ha1_fixtures.timeout_probe
result (the API test's assertion message truncates it) and times the CPU
statement with and without `SET STATEMENT max_statement_time` directly on the
engine, so an uninterruptible statement is distinguished from a fast one.
Read-only SELECTs; no fixture rows. No secret printed.
"""
import json
import os
import sys
import time
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

out = {'target': target}
with app.app_context():
    out['probe'] = fx.timeout_probe(db.engine, 1.0)
    out['probe_failures'] = harness.timeout_failures(out['probe'], 1.0)
    raw = {}
    with db.engine.connect() as conn:
        for label, sql in (
                ('benchmark_5M_unlimited', 'SELECT BENCHMARK(5000000, SHA2("ha1", 512))'),
                ('benchmark_50M_limit_1s', 'SET STATEMENT max_statement_time=1 FOR SELECT BENCHMARK(50000000, SHA2("ha1", 512))'),
                ('sleep_3_limit_1s', 'SET STATEMENT max_statement_time=1 FOR SELECT SLEEP(3)'),
                ('seq_sum_limit_1s', 'SET STATEMENT max_statement_time=1 FOR SELECT COUNT(*) FROM seq_1_to_100000000'),
                ('cross_join_limit_1s', 'SET STATEMENT max_statement_time=1 FOR SELECT COUNT(*) FROM '
                                        'information_schema.COLLATIONS a, information_schema.COLLATIONS b, '
                                        'information_schema.COLLATIONS c')):
            started = time.perf_counter()
            try:
                value = conn.exec_driver_sql(sql).scalar()
                error = None
            except Exception as exc:  # noqa: BLE001 -- recorded
                value, error = None, f'{type(exc).__name__}: {getattr(exc, "orig", exc)}'
                conn.rollback()
            raw[label] = {'value': str(value), 'error': error,
                          'elapsed_s': round(time.perf_counter() - started, 3)}
        out['raw'] = raw
print(json.dumps(out, indent=2, default=str))

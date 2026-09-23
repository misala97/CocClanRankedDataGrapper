"""HA1-US-DAILY-EXPLORE-REVIEW-1: DB-free partial estimate for the C13 budgets.

    cd personal_apps && py -3.12 ../radar-design/artifacts/ha1/review/reducer_budget_estimate.py

Builds 43,008 plain bucket mappings (7 days x 96 slots x 64 sources) the way
SqlStore._rows hands them over (one dict per row), runs the pure chatter
reducer and serialises the chatter object. Measures Python allocation with
tracemalloc and the JSON byte size. This EXCLUDES the driver, SQLAlchemy
Row/RowMapping objects, Flask and the price series, so it is a lower bound on
the reader's incremental allocation and NOT a C13 pass. No app, DB or network.
"""
import datetime as dt
import json
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4] / 'personal_apps'
sys.path.insert(0, str(ROOT))

from features.radar import analysis_contract as ac  # noqa: E402

START, END = dt.date(2026, 9, 7), dt.date(2026, 9, 13)
SOURCES = [f'zqsrc{n}' for n in range(64)]

tracemalloc.start()
base, _ = tracemalloc.get_traced_memory()
started = time.perf_counter()
rows = []
for n in range(7):
    day = dt.datetime.combine(START + dt.timedelta(days=n), dt.time())
    for source in SOURCES:
        for slot in range(96):
            rows.append({'bucket_start': day + dt.timedelta(minutes=15 * slot),
                         'source': str(source), 'mention_count': slot % 3,
                         'status': 'ok', 'source_config_version': 'cfgA'})
after_rows, _ = tracemalloc.get_traced_memory()
chatter = ac.chatter_days(rows, START, END, dt.datetime(2026, 1, 1))
current, peak = tracemalloc.get_traced_memory()
body = json.dumps({'chatter': chatter}, separators=(',', ':')).encode()
elapsed = time.perf_counter() - started
tracemalloc.stop()

print(json.dumps({
    'rows': len(rows),
    'row_dicts_mib': round((after_rows - base) / 2**20, 2),
    'peak_including_rows_and_reducer_mib': round((peak - base) / 2**20, 2),
    'chatter_json_bytes': len(body),
    'reducer_plus_build_seconds_under_tracemalloc': round(elapsed, 2),
    'budget_reference': {'incremental_allocation_mib': 32, 'response_bytes': 2**20},
    'excluded': ['pymysql/SQLAlchemy result rows', 'Flask/jsonify', 'price series'],
}, indent=2))

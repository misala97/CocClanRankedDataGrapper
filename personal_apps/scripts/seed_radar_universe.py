# personal_apps/scripts/seed_radar_universe.py
"""Seed radar_ticker_universe from a symbol listing file.

Run against a downloaded listing rather than an API so it works offline and so
re-seeding is deterministic. Expects a CSV with at least `symbol` and `name`
columns; nasdaqtrader.com publishes pipe-delimited files in this shape.

    python scripts/seed_radar_universe.py path/to/symbols.csv

Re-running is safe: upsert_symbols is idempotent and only resets a baseline
when a symbol genuinely changed hands (features/radar/universe.py).
"""
import csv
import datetime as dt
import sys

sys.path.insert(0, '.')

from app import app                       # noqa: E402
from features.radar import universe       # noqa: E402


def load_rows(path):
    with open(path, newline='', encoding='utf-8') as handle:
        sample = handle.read(4096)
        handle.seek(0)
        delimiter = '|' if '|' in sample.splitlines()[0] else ','
        for row in csv.DictReader(handle, delimiter=delimiter):
            symbol = (row.get('symbol') or row.get('Symbol') or '').strip()
            name = (row.get('name') or row.get('Security Name') or '').strip()
            exchange = (row.get('exchange') or row.get('Listing Exchange') or '').strip()
            if not symbol or not symbol.isalpha() or len(symbol) > 5:
                continue
            yield {'symbol': symbol, 'name': name, 'exchange': exchange}


def main():
    if len(sys.argv) != 2:
        print('usage: seed_radar_universe.py <symbols.csv>')
        return 1

    rows = list(load_rows(sys.argv[1]))
    with app.app_context():
        counts = universe.upsert_symbols(rows, dt.datetime.utcnow())
    print('universe: %d added, %d updated, %d reassigned (from %d rows)'
          % (counts['added'], counts['updated'], counts['reassigned'], len(rows)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

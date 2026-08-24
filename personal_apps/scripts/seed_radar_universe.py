# personal_apps/scripts/seed_radar_universe.py
"""Seed radar_ticker_universe from Nasdaq Trader symbol directory files.

Run against downloaded listings rather than an API so it works offline and so
re-seeding is deterministic:

    python scripts/seed_radar_universe.py nasdaqlisted.txt otherlisted.txt

Both files are pipe-delimited and published at
https://www.nasdaqtrader.com/dynamic/symdir/ . They disagree about their own
column names -- nasdaqlisted.txt calls the symbol `Symbol` while
otherlisted.txt calls it `ACT Symbol` -- and both end with a `File Creation
Time` line that is not a row. Handled below rather than by hand-editing the
files, because they are meant to be re-downloaded weekly.

Re-running is safe: upsert_symbols is idempotent and only resets a baseline
when a symbol genuinely changed hands (features/radar/universe.py).
"""
import csv
import datetime as dt
import sys

sys.path.insert(0, '.')

from app import app                       # noqa: E402
from features.radar import universe       # noqa: E402

# Column aliases, in preference order. The two Nasdaq files use different
# names for the same field.
_SYMBOL_KEYS = ('Symbol', 'ACT Symbol', 'NASDAQ Symbol', 'symbol')
_NAME_KEYS = ('Security Name', 'name')
_EXCHANGE_KEYS = ('Exchange', 'Listing Exchange', 'Market Category', 'exchange')
# Both files carry it, both spell it the same, and it is the only
# authoritative statement anywhere that a listing is a fund.
_ETF_KEYS = ('ETF', 'etf')


def _first(row, keys):
    for key in keys:
        value = row.get(key)
        if value:
            return value.strip()
    return ''


def load_rows(path):
    """Yield universe rows, skipping everything that is not a tradable symbol."""
    with open(path, newline='', encoding='utf-8') as handle:
        first_line = handle.readline()
        handle.seek(0)
        delimiter = '|' if '|' in first_line else ','

        for row in csv.DictReader(handle, delimiter=delimiter):
            symbol = _first(row, _SYMBOL_KEYS)

            # Trailing "File Creation Time: ..." line parses as a row whose
            # first field holds that text. It has no security name.
            if not symbol or symbol.startswith('File Creation Time'):
                continue

            # Test issues are Nasdaq's own dummy listings. They are never
            # discussed anywhere and would only add false-positive surface.
            if (row.get('Test Issue') or '').strip().upper() == 'Y':
                continue

            # Class/warrant/unit suffixes arrive as GOOG.A or GOOGpA. Only
            # plain alphabetic symbols are matchable by the extractor, which
            # works on word-boundary tokens.
            if not symbol.isalpha() or len(symbol) > 5:
                continue

            # 'Y', 'N', or absent. Absent stays None rather than becoming
            # False: a file that does not carry the column has not told us
            # this is a stock.
            etf = _first(row, _ETF_KEYS).upper()

            yield {
                'symbol': symbol,
                'name': _first(row, _NAME_KEYS),
                'exchange': _first(row, _EXCHANGE_KEYS),
                'is_etf': {'Y': True, 'N': False}.get(etf),
            }


def main():
    if len(sys.argv) < 2:
        print('usage: seed_radar_universe.py <listing.txt> [<listing.txt> ...]')
        return 1

    rows = []
    seen = set()
    for path in sys.argv[1:]:
        added = 0
        for row in load_rows(path):
            # The two files overlap on dual-listed symbols; first file wins.
            if row['symbol'] in seen:
                continue
            seen.add(row['symbol'])
            rows.append(row)
            added += 1
        print('%s: %d usable symbols' % (path, added))

    with app.app_context():
        counts = universe.upsert_symbols(rows, dt.datetime.utcnow())
    print('universe: %d added, %d updated, %d reassigned (from %d rows)'
          % (counts['added'], counts['updated'], counts['reassigned'], len(rows)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

# personal_apps/scripts/seed_radar_universe.py
"""Seed radar_ticker_universe from Nasdaq Trader symbol directory files.

Run against downloaded listings rather than an API so it works offline and so
re-seeding is deterministic:

    python scripts/seed_radar_universe.py nasdaqlisted.txt otherlisted.txt

Both files are pipe-delimited and published at
https://www.nasdaqtrader.com/dynamic/symdir/ . They disagree about their own
column names -- nasdaqlisted.txt calls the symbol `Symbol` while
otherlisted.txt calls it `ACT Symbol` -- and both end with a `File Creation
Time` line that is not a row.

Each argument is bound by basename to exactly one of those two documented
files, and parsing is delegated to features.radar.universe_directory, which
knows which column carries the listing code in each. The parser used to
resolve the code from the first non-empty of four aliases, one of which was an
undocumented listing-exchange column belonging to nasdaqtraded.txt -- a file
Nasdaq publishes no field definitions for at all, so there was no
authoritative meaning available for the letters it would have supplied.

Exactly one file of each kind is required, and the pair is parsed and
validated as a pair before the application is imported. A symbol listed in
both files is refused rather than settled by argument order.

Re-running is safe: upsert_symbols is idempotent and only resets a baseline
when a symbol genuinely changed hands (features/radar/universe.py).
"""
import datetime as dt
import sys

sys.path.insert(0, '.')

from features.radar.universe_directory import (  # noqa: E402,F401
    HEADERS, DirectoryValidationError, parse_directory, source_kind_for,
    validate_pair,
)


def load_rows(path, source_kind):
    """Yield universe rows for one validated directory file.

    Validation is fail-closed and happens before the first row is yielded, so
    a malformed publication cannot half-seed the universe.
    """
    yield from _rows(parse_directory(path, source_kind))


def _rows(snapshot):
    for row in snapshot.rows:
        yield {
            'symbol': row.symbol,
            'name': row.name,
            'exchange': row.exchange_code,
            'is_etf': row.is_etf,
        }


def read_pair(paths):
    """Bind, parse and validate the complete pair, or refuse it whole.

    One file of each documented kind, no more and no fewer, each parsed and
    then checked against the other. Returns the snapshots by source kind.
    """
    bound, problems = {}, []
    for path in paths:
        kind = source_kind_for(path)
        if kind in bound:
            problems.append(f'{kind}.txt was supplied twice: {bound[kind]} '
                            f'and {path}')
            continue
        bound[kind] = path
    for kind in sorted(set(HEADERS) - set(bound)):
        problems.append(f'{kind}.txt is missing; the pair is validated as a '
                        f'pair or not at all')
    if problems:
        raise DirectoryValidationError('<pair>', problems)

    snapshots = {kind: parse_directory(path, kind)
                 for kind, path in bound.items()}
    validate_pair(snapshots['nasdaqlisted'], snapshots['otherlisted'])
    return snapshots


def main():
    if len(sys.argv) < 2:
        print('usage: seed_radar_universe.py nasdaqlisted.txt otherlisted.txt')
        return 1

    paths = sys.argv[1:]
    # Everything that can refuse the input runs here, before the application
    # is imported: a refused pair never reaches an app context or an upsert.
    snapshots = read_pair(paths)

    rows = []
    for path in paths:
        added = list(_rows(snapshots[source_kind_for(path)]))
        rows.extend(added)
        print('%s: %d usable symbols' % (path, len(added)))

    from app import app
    from features.radar import universe

    with app.app_context():
        counts = universe.upsert_symbols(rows, dt.datetime.utcnow())
    print('universe: %d added, %d updated, %d reassigned, %d fund flags set '
          '(from %d rows)'
          % (counts['added'], counts['updated'], counts['reassigned'],
             counts['flagged'], len(rows)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Which plan every radar_bucket_sources read gets, with and without the index.

The independent review's SUSPECTED finding: four other queries filter
`ticker IN (small list) AND source IN (...) AND bucket_start range` and select
columns the new index now carries, so the optimizer could abandon PRIMARY's
tiny ref lookup for a covering scan of 400k rows -- a regression the
whole-board timings would not necessarily surface.

No query is hand-written here. A `before_cursor_execute` listener records what
the real code paths actually send, and each recorded statement is EXPLAINed
with its own parameters. That is the rule this workstream broke twice: no
query gets reported unless its shape came from the code.
"""
import datetime as dt
import sys

import sqlalchemy as sa
from sqlalchemy import event

from app import app
from extensions import db
from features.radar import board as board_mod
from features.radar import detail as detail_mod
from features.radar import leaderboard
from features.radar.routes import api as api_mod

DB = 'personal_apps_radar_perf1'
TABLE = 'radar_bucket_sources'

seen = []


def record(conn, cursor, statement, parameters, context, executemany):
    if TABLE in statement and statement.lstrip().upper().startswith('SELECT'):
        seen.append((statement, parameters))


def explain(statement, parameters):
    # Through the raw DBAPI cursor: the recorded statement carries pymysql's
    # own %s placeholders, which sa.text() will not parse. Sending it back the
    # way it was sent keeps the shape byte-identical to production's.
    raw = db.session.connection().connection
    cursor = raw.cursor()
    try:
        cursor.execute('EXPLAIN ' + statement, parameters)
        names = [c[0] for c in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]
    finally:
        cursor.close()


def sweep(label, sources, now):
    print('\n=== %s ===' % label, flush=True)
    seen.clear()

    query = api_mod.parse_query({}, now=now)
    board_mod.build(sources, now, window_hours=24, segments=query.segments,
                    limit=query.limit, market=query.market)
    tickers = [r.rank.ticker for r in board_mod.build(
        sources, now, window_hours=4, segments=query.segments, limit=5,
        market=query.market).rows][:5]
    if tickers:
        # The watched-rows path and the detail panel, which no timing in this
        # workstream has ever exercised.
        leaderboard.build_pinned(tickers, sources, now, window_hours=24)
        detail_mod.daily_counts(tickers, sources,
                                now - dt.timedelta(days=30), now)
    print('recorded %d distinct reads of %s' % (len(seen), TABLE))

    reported = set()
    for statement, parameters in seen:
        shape = ' '.join(statement.split())[:70]
        if shape in reported:
            continue
        reported.add(shape)
        try:
            for row in explain(statement, parameters):
                print('  %-70s' % shape)
                print('     partitions=%s type=%s key=%s rows=%s extra=%s'
                      % (row.get('partitions'), row.get('type'),
                         row.get('key'), row.get('rows'), row.get('Extra')))
        except Exception as exc:
            print('  %-70s  EXPLAIN failed: %s' % (shape, str(exc)[:60]))
    return reported


def main():
    event.listen(sa.engine.Engine, 'before_cursor_execute', record)
    with app.app_context():
        assert db.engine.url.database == DB, db.engine.url.database
        sources = [r[0] for r in db.session.execute(sa.text(
            'SELECT DISTINCT source FROM radar_bucket_sources')).fetchall()]
        now = dt.datetime.utcnow().replace(microsecond=0)
        present = db.session.execute(sa.text(
            'SELECT COUNT(*) FROM information_schema.STATISTICS'
            " WHERE TABLE_SCHEMA=:s AND TABLE_NAME=:t"
            " AND INDEX_NAME='ix_radar_bucket_sources_agg'"),
            {'s': DB, 't': TABLE}).scalar() > 0
        sweep('index present' if present else 'index absent', sources, now)


if __name__ == '__main__':
    sys.exit(main())

"""Structural profile of the board build, locally.

Query COUNTS and the stage split are volume-independent: an N+1 is an N+1 at
any table size. The TIMINGS here are NOT production scale and are not
presented as such -- this database holds a fraction of the target's rows.
"""
import collections
import datetime as dt
import time

import sqlalchemy as sa
from sqlalchemy import event

from app import app
from extensions import db
from features.radar import board as board_mod
from features.radar import leaderboard as leaderboard_mod


class Trace:
    def __init__(self):
        self.rows = []
        self._t0 = {}

    def before(self, conn, cursor, statement, params, context, many):
        self._t0[id(context)] = time.perf_counter()

    def after(self, conn, cursor, statement, params, context, many):
        began = self._t0.pop(id(context), None)
        if began is None:
            return
        self.rows.append((time.perf_counter() - began,
                          ' '.join(statement.split())))

    def reset(self):
        self.rows = []

    @property
    def n(self):
        return len(self.rows)

    @property
    def seconds(self):
        return sum(t for t, _ in self.rows)

    def by_shape(self, top=6):
        """Group by the statement's leading shape, to expose repetition."""
        groups = collections.defaultdict(lambda: [0, 0.0])
        for took, sql in self.rows:
            key = sql[:110]
            groups[key][0] += 1
            groups[key][1] += took
        return sorted(groups.items(), key=lambda kv: -kv[1][1])[:top]


def main():
    with app.app_context():
        name = db.engine.url.database
        print('database:', name)
        assert 'radar' in name and 'perf1' not in name.replace('radar_perf1', ''), name
        print('engine:', db.session.execute(sa.text('SELECT VERSION()')).scalar())
        counts = db.session.execute(sa.text(
            'SELECT (SELECT COUNT(*) FROM radar_bucket_sources),'
            ' (SELECT COUNT(*) FROM radar_mention_events),'
            ' (SELECT COUNT(*) FROM radar_quotes)')).first()
        print('local rows: bucket_sources=%s mention_events=%s quotes=%s'
              % tuple(counts))
        print('NOT production scale. Target: 9,333,403 / 1,153,330 / 110,742.')

        trace = Trace()
        event.listen(db.engine, 'before_cursor_execute', trace.before)
        event.listen(db.engine, 'after_cursor_execute', trace.after)

        now = dt.datetime.utcnow().replace(microsecond=0)
        sources = ['bluesky', 'fourchan', 'reddit']

        for hours in (4, 12, 24):
            db.session.expire_all()
            trace.reset()
            began = time.perf_counter()
            survivors, excluded, grouped, _ = leaderboard_mod._chatter_survivors(
                sources, now, hours)
            one_wall, one_n, one_sql = (time.perf_counter() - began,
                                        trace.n, trace.seconds)

            db.session.expire_all()
            trace.reset()
            began = time.perf_counter()
            ranking = leaderboard_mod.build_rows(
                sources, now, window_hours=hours, segments=(), limit=None,
                market='us')
            rank_wall, rank_n, rank_sql = (time.perf_counter() - began,
                                           trace.n, trace.seconds)

            db.session.expire_all()
            trace.reset()
            began = time.perf_counter()
            built = board_mod.build(sources, now, window_hours=hours,
                                    segments=(), limit=50, market='us')
            all_wall, all_n, all_sql = (time.perf_counter() - began,
                                        trace.n, trace.seconds)
            shapes = trace.by_shape()

            print('')
            print(f'=== {hours}h, All companies, limit 50 ===')
            print(f'  tickers with a scored bucket : {len(grouped)}')
            print(f'  survivors (clear the floor)  : {len(survivors)}')
            print(f'  ranked rows before the limit : {len(ranking.rows)}')
            print(f'  rows returned                : {len(built.rows)}')
            print(f'  pass one   : {one_n:4d} queries, {one_sql:6.3f}s sql, {one_wall:6.3f}s wall')
            print(f'  build_rows : {rank_n:4d} queries, {rank_sql:6.3f}s sql, {rank_wall:6.3f}s wall')
            print(f'  board.build: {all_n:4d} queries, {all_sql:6.3f}s sql, {all_wall:6.3f}s wall')
            print(f'  _entries share: {all_n - rank_n} queries,'
                  f' {all_sql - rank_sql:6.3f}s sql')
            print(f'  python (wall - sql): {all_wall - all_sql:6.3f}s')
            print('  most expensive statement shapes:')
            for sql, (n, secs) in shapes:
                print(f'    x{n:<4d} {secs:6.3f}s  {sql}')


if __name__ == '__main__':
    main()

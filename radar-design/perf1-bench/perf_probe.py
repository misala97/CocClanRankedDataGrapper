"""Read-only profile of the board build, run against production data.

Reads only. No writes, no DDL, no service action, no cache flush, no
authentication. Each case runs ONCE -- this is a bounded diagnostic on a live
machine, not a load test. Nothing is written to the target filesystem: this
arrives on stdin.

Prints no post content and no credentials.
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
from features.radar.config import source_config_version


class Counter:
    """SQL statements and their cumulative time, per logical stage."""

    def __init__(self):
        self.n = 0
        self.seconds = 0.0
        self.worst = 0.0
        self.worst_sql = ''
        self._start = {}

    def before(self, conn, cursor, statement, params, context, many):
        self._start[id(context)] = time.perf_counter()

    def after(self, conn, cursor, statement, params, context, many):
        began = self._start.pop(id(context), None)
        if began is None:
            return
        took = time.perf_counter() - began
        self.n += 1
        self.seconds += took
        if took > self.worst:
            self.worst = took
            self.worst_sql = ' '.join(statement.split())[:180]

    def reset(self):
        self.n = 0
        self.seconds = 0.0
        self.worst = 0.0
        self.worst_sql = ''


def main():
    with app.app_context():
        print('database:', db.engine.url.database)
        print('engine:', db.session.execute(sa.text('SELECT VERSION()')).scalar())
        print('source_config_version:', source_config_version())

        counter = Counter()
        event.listen(db.engine, 'before_cursor_execute', counter.before)
        event.listen(db.engine, 'after_cursor_execute', counter.after)

        now = dt.datetime.utcnow().replace(microsecond=0)
        print('now (fixed for every case):', now.isoformat())

        sources = ['bluesky', 'fourchan', 'reddit']

        for hours in (4, 12, 24):
            # PASS ONE only: the chatter judgement, no quotes or history.
            db.session.expire_all()
            counter.reset()
            began = time.perf_counter()
            survivors, excluded, grouped, channels = (
                leaderboard_mod._chatter_survivors(sources, now, hours))
            pass_one = time.perf_counter() - began
            pass_one_sql, pass_one_n = counter.seconds, counter.n

            # PASS TWO: the whole ranking, limit=None, exactly as board.build
            # calls it.
            db.session.expire_all()
            counter.reset()
            began = time.perf_counter()
            ranking = leaderboard_mod.build_rows(
                sources, now, window_hours=hours, segments=(), limit=None,
                market='us')
            ranking_wall = time.perf_counter() - began
            ranking_sql, ranking_n = counter.seconds, counter.n

            # The whole board, All companies, ordinary limit.
            db.session.expire_all()
            counter.reset()
            began = time.perf_counter()
            built = board_mod.build(sources, now, window_hours=hours,
                                    segments=(), limit=50, market='us')
            board_wall = time.perf_counter() - began
            board_sql, board_n = counter.seconds, counter.n
            worst, worst_sql = counter.worst, counter.worst_sql

            print('')
            print(f'--- window {hours}h, All companies, limit 50 ---')
            print(f'  survivors (candidates after the floor): {len(survivors)}')
            print(f'  ranked rows before limit              : {len(ranking.rows)}')
            print(f'  rows returned                         : {len(built.rows)}')
            print(f'  pass one  wall {pass_one:7.3f}s   sql {pass_one_sql:7.3f}s  n={pass_one_n}')
            print(f'  build_rows wall {ranking_wall:7.3f}s   sql {ranking_sql:7.3f}s  n={ranking_n}')
            print(f'  board.build wall {board_wall:7.3f}s   sql {board_sql:7.3f}s  n={board_n}')
            print(f'  python (board wall - sql)             : {board_wall - board_sql:7.3f}s')
            print(f'  worst single statement                : {worst:7.3f}s')
            print(f'  worst sql                             : {worst_sql}')

        # What the limit actually costs: the same board at the maximum the API
        # supports, to separate segment selection from row limit.
        db.session.expire_all()
        counter.reset()
        began = time.perf_counter()
        wide = board_mod.build(sources, now, window_hours=24, segments=(),
                               limit=200, market='us')
        print('')
        print(f'--- 24h, All companies, limit 200 ---')
        print(f'  rows {len(wide.rows)}  wall {time.perf_counter() - began:7.3f}s'
              f'  sql {counter.seconds:7.3f}s  n={counter.n}')


if __name__ == '__main__':
    main()

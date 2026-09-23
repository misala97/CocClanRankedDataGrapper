"""Task S7: restart, empty, expired, redeployed.

The in-process dict this replaces lost everything at every worker restart and
had no notion of a version at all. These four steps are the cases that
distinguishes.

Run from `personal_apps/`:
    python ../radar-design/perf2-spike/run_s7_lifecycle.py
"""
import datetime as dt
import json
import os
import subprocess
import sys
import time

import sqlalchemy as sa

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from env_check import bootstrap  # noqa: E402
bootstrap()

import keys                                            # noqa: E402
import producer                                        # noqa: E402
import reader                                          # noqa: E402
import selections                                      # noqa: E402
import store                                           # noqa: E402
from env_check import APP_DIR, SPIKE_DIR               # noqa: E402
from env_check import fixture_sources, preflight       # noqa: E402


def read_in_own_process(now, repeat=3):
    proc = subprocess.Popen(
        [sys.executable, os.path.join(SPIKE_DIR, 'reader.py'),
         '--now', now.isoformat(), '--window', '24', '--segments', '',
         '--market', 'us', '--fixture-sources', '--repeat', str(repeat)],
        cwd=APP_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = proc.communicate(timeout=600)
    line = [x for x in out.splitlines() if x.startswith('RESULT ')]
    assert line, (out, err)
    return json.loads(line[0][len('RESULT '):])


def main():
    from app import app
    with app.app_context():
        from extensions import db
        from features.radar.routes.api import Query
        preflight(db, 'S7 -- restart, empty, expired')
        engine = db.engine
        sources = fixture_sources(db)
        src = ','.join(sources)
        now = selections.fixed_now()
        request = {'window': '24', 'segment': '', 'market': 'us',
                   'sources': src}
        store.drop_table(engine)
        store.create_table(engine)
        query = Query(sources=list(sources), segments=[], window=24, limit=50,
                      min_venues=1, market='us', sort=None, direction='desc')
        key_hash, key_json = keys.canonical(query)

        # ---- Step 1: web-worker restart ----------------------------------
        print('\n--- Step 1: the result outlives the process that read it ---')
        store.enqueue(engine, key_hash, key_json, now, warm=True)
        producer.serve_once(engine, 's7', now, key_hash=key_hash,
                            query_cls=Query)
        first = read_in_own_process(now)
        print('  worker A (fresh process): %s'
              % '  '.join('%.0f ms%s' % (r['seconds'] * 1000,
                                         ' pending' if r['pending'] else '')
                          for r in first))
        second = read_in_own_process(now)
        print('  worker B (a DIFFERENT fresh process, A already exited): %s'
              % '  '.join('%.0f ms%s' % (r['seconds'] * 1000,
                                         ' pending' if r['pending'] else '')
                          for r in second))
        assert not any(r['pending'] for r in first + second)
        assert first[0]['digest'] == second[0]['digest']
        print('  identical digests, no build in either: the RESULT survived'
              ' the process. An in-process dict never did.')
        print('  first read in a fresh process %.0f ms, steady-state %.0f ms'
              ' -- the first one is pool creation and lazy imports, paid once'
              ' per worker boot, not per request'
              % (second[0]['seconds'] * 1000, second[-1]['seconds'] * 1000))

        # ---- Step 2: a fully empty store ---------------------------------
        print('\n--- Step 2: a completely empty store ---')
        store.truncate(engine)
        with engine.connect() as conn:
            assert conn.execute(sa.text(
                'SELECT COUNT(*) FROM radar_board_results')).scalar() == 0
        began = time.perf_counter()
        answer = reader.read_payload(engine, dict(request), now, None)
        pending_ms = (time.perf_counter() - began) * 1000
        print('  the first request against an empty store: %s in %.1f ms'
              % ('pending' if answer['pending'] else 'a board', pending_ms))
        assert answer['pending'] and answer['rows'] is None
        print('  THAT IS NOT A BOARD. It is an acknowledgement.')
        began = time.perf_counter()
        producer.serve_once(engine, 's7', now, query_cls=Query)
        build_s = time.perf_counter() - began
        began = time.perf_counter()
        board = reader.read_payload(engine, dict(request), now, None)
        read_ms = (time.perf_counter() - began) * 1000
        assert board['rows']
        print('  producer built it in %.1f s; the next read is a board in'
              ' %.1f ms' % (build_s, read_ms))
        print('  EMPTY-STORE COLD: %.1f s from the first request to a board'
              % (pending_ms / 1000 + build_s + read_ms / 1000))

        # ---- Step 3: expired data ----------------------------------------
        print('\n--- Step 3: the three age behaviours ---')
        as_of = store.read(engine, key_hash, now).as_of
        print('  MAX_AGE=%ds  HARD_MAX_AGE=%ds' % (store.MAX_AGE,
                                                   store.HARD_MAX_AGE))
        print('  %-9s %-14s %-9s %-8s %s'
              % ('age', 'answer', 'reported', 'error', 'rows'))
        for age in (0, store.MAX_AGE - 1, store.MAX_AGE + 1,
                    store.HARD_MAX_AGE - 1, store.HARD_MAX_AGE + 1):
            at = as_of + dt.timedelta(seconds=age)
            # Re-publish so a refresh queued by a stale read cannot change
            # what the next case sees.
            with engine.begin() as conn:
                conn.execute(sa.text(
                    "UPDATE radar_board_results SET state='ready',"
                    ' as_of=:a WHERE key_hash=:k'),
                    {'a': as_of, 'k': key_hash})
            served = reader.read_payload(engine, dict(request), at, None)
            answer = ('pending' if served['pending']
                      else 'stale board' if served['stale'] else 'fresh board')
            reported = served['age_seconds']
            error = ('n/a' if reported is None
                     else '%+.3fs' % (reported - age))
            print('  %6ds    %-14s %-9s %-8s %s'
                  % (age, answer, '%.0fs' % reported if reported is not None
                     else '--', error,
                     len(served['rows']) if served['rows'] else 0))
            if age <= store.MAX_AGE - 1:
                assert answer == 'fresh board'
                assert abs(reported - age) < 0.001
            elif age <= store.HARD_MAX_AGE - 1:
                assert answer == 'stale board', answer
                assert abs(reported - age) < 0.001
                assert served['rows'], 'a stale board must still be a board'
            else:
                assert answer == 'pending', answer
        print('  serve / serve-stale / treat-as-missing, and the reported age'
              ' is the REAL age to the millisecond in every served case')
        # A stale read must also have QUEUED a refresh.
        with engine.begin() as conn:
            conn.execute(sa.text(
                "UPDATE radar_board_results SET state='ready', as_of=:a"
                ' WHERE key_hash=:k'),
                {'a': as_of, 'k': key_hash})
        reader.read_payload(engine, dict(request),
                            as_of + dt.timedelta(seconds=store.MAX_AGE + 5),
                            None)
        with engine.connect() as conn:
            queued = conn.execute(sa.text(
                'SELECT state FROM radar_board_results WHERE key_hash=:k'),
                {'k': key_hash}).scalar()
        print('  and the stale read queued a refresh: state=%s' % queued)
        assert queued == 'pending'

        # ---- Step 4: deployment invalidation -----------------------------
        print('\n--- Step 4: deployment invalidation ---')
        with engine.begin() as conn:
            conn.execute(sa.text(
                "UPDATE radar_board_results SET state='ready',"
                ' payload_version=:v, as_of=:a WHERE key_hash=:k'),
                {'v': store.PAYLOAD_VERSION, 'a': now, 'k': key_hash})
        before = reader.read_payload(engine, dict(request), now, None)
        print('  stored at PAYLOAD_VERSION=%d, code at %d: %s'
              % (store.PAYLOAD_VERSION, store.PAYLOAD_VERSION,
                 'a board' if before['rows'] else 'pending'))
        assert before['rows'], 'the matching case must be served, or step 4'\
                               ' proves nothing'
        with engine.begin() as conn:
            conn.execute(sa.text(
                "UPDATE radar_board_results SET state='ready',"
                ' payload_version=:v WHERE key_hash=:k'),
                {'v': store.PAYLOAD_VERSION - 1, 'k': key_hash})
        after = reader.read_payload(engine, dict(request), now, None)
        print('  stored at PAYLOAD_VERSION=%d, code at %d: %s'
              % (store.PAYLOAD_VERSION - 1, store.PAYLOAD_VERSION,
                 'a board -- THE OLD SHAPE WAS SERVED' if after['rows']
                 else 'pending, treated as missing'))
        assert after['pending'] and after['rows'] is None
        with engine.connect() as conn:
            requeued = conn.execute(sa.text(
                'SELECT state, payload_version FROM radar_board_results'
                ' WHERE key_hash=:k'), {'k': key_hash}).first()
        print('  and it was re-queued for rebuild: state=%s, with'
              ' payload_version still %d' % (requeued[0], requeued[1]))
        assert requeued[0] == 'pending'
        # `payload_version` describes the BLOB, not the request. It stays at
        # the old version while the old blob is still in the row -- writing
        # the running version there before the rebuild lands would be a lie
        # about bytes nobody has replaced yet. `publish` sets it.
        assert requeued[1] == store.PAYLOAD_VERSION - 1
        producer.serve_once(engine, 's7', now, key_hash=key_hash,
                            query_cls=Query)
        with engine.connect() as conn:
            rebuilt = conn.execute(sa.text(
                'SELECT state, payload_version FROM radar_board_results'
                ' WHERE key_hash=:k'), {'k': key_hash}).first()
        served = reader.read_payload(engine, dict(request), now, None)
        print('  after the rebuild: state=%s payload_version=%d, and the'
              ' reader gets a board again (%d rows)'
              % (rebuilt[0], rebuilt[1], len(served['rows'])))
        assert rebuilt[1] == store.PAYLOAD_VERSION and served['rows']

        print('\nS7 done.')


if __name__ == '__main__':
    main()

"""Task S6: failure is bounded.

Codex named two defects in the in-process single-flight: its exhausted-retry
path builds unclaimed, and a timed-out old builder can still publish later.
Steps 1 and 2 are those two, put back as experiments rather than argued about.

The lease is 120 s in `store.py` and a test cannot wait for it, so steps 1 and
2 run with a SHORT lease passed to the producer. The mechanism is the same
statement either way; only the number changes, and the ledger says which.

Run from `personal_apps/`:
    python ../radar-design/perf2-spike/run_s6_failure.py
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

SHORT_LEASE = 20.0
NL = chr(10)
# 30 minutes, not 60: the board being served is already MAX_AGE+60 old
# when the window opens, and past HARD_MAX_AGE it is correctly treated as
# missing -- which would end the run for the right reason and prove nothing
# about backoff.
WINDOW_MIN = 30


def spawn(*args):
    return subprocess.Popen(
        [sys.executable, os.path.join(SPIKE_DIR, 'producer.py')] + list(args),
        cwd=APP_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def row_of(engine, key_hash):
    with engine.connect() as conn:
        return conn.execute(sa.text(
            'SELECT state, lease_owner, lease_expires_at, fence, attempts,'
            ' next_attempt_at, last_error, as_of, payload_bytes'
            ' FROM radar_board_results WHERE key_hash = :k'),
            {'k': key_hash}).mappings().first()


def age_backwards(engine, key_hash, seconds):
    with engine.begin() as conn:
        conn.execute(sa.text(
            'UPDATE radar_board_results'
            ' SET as_of = as_of - INTERVAL :s SECOND WHERE key_hash = :k'),
            {'s': int(seconds), 'k': key_hash})


class BuildWatch:
    """Fails loudly if the READ PATH ever builds. Not a claim; a tripwire."""

    def __init__(self):
        self.calls = 0

    def __enter__(self):
        from features.radar import board as board_mod
        from features.radar import leaderboard
        self._board, self._rows = board_mod.build, leaderboard.build_rows

        def trip(*a, **k):
            self.calls += 1
            raise AssertionError('THE READ PATH BUILT A BOARD')

        board_mod.build = trip
        leaderboard.build_rows = trip
        return self

    def __exit__(self, *exc):
        from features.radar import board as board_mod
        from features.radar import leaderboard
        board_mod.build, leaderboard.build_rows = self._board, self._rows
        return False


def instrument(engine):
    """Every transaction on this engine, timed, with its first statement."""
    seen = []
    live = {}

    @sa.event.listens_for(engine, 'begin')
    def _begin(conn):
        live[id(conn)] = [time.perf_counter(), None]

    @sa.event.listens_for(engine, 'before_cursor_execute')
    def _stmt(conn, cursor, statement, params, context, many):
        entry = live.get(id(conn))
        if entry is not None and entry[1] is None:
            entry[1] = ' '.join(statement.split())[:70]

    def _close(conn, how):
        entry = live.pop(id(conn), None)
        if entry is not None:
            seen.append((time.perf_counter() - entry[0], how,
                         entry[1] or '<no statement>'))

    sa.event.listen(engine, 'commit', lambda c: _close(c, 'commit'))
    sa.event.listen(engine, 'rollback', lambda c: _close(c, 'rollback'))
    return seen


def main():
    from app import app
    with app.app_context():
        from extensions import db
        from features.radar.routes.api import Query
        preflight(db, 'S6 -- failure is bounded')
        engine = db.engine
        sources = fixture_sources(db)
        src = ','.join(sources)
        base = selections.fixed_now()
        wall_base = dt.datetime.now()

        def clock():
            return base + (dt.datetime.now() - wall_base)

        def child_now():
            """--now/--wall pair anchoring a child's simulated clock to the
            parent's, so a short lease means the same thing in both."""
            return ['--now', clock().isoformat(),
                    '--wall', dt.datetime.now().isoformat(), '--advance']

        store.drop_table(engine)
        store.create_table(engine)
        query = Query(sources=list(sources), segments=[], window=24, limit=50,
                      min_venues=1, market='us', sort=None, direction='desc')
        key_hash, key_json = keys.canonical(query)
        request = {'window': '24', 'segment': '', 'market': 'us',
                   'sources': src}

        # ---- Step 1: kill a producer mid-build ---------------------------
        print('\n--- Step 1: kill a producer mid-build (lease %.0fs) ---'
              % SHORT_LEASE)
        store.enqueue(engine, key_hash, key_json, clock(), warm=True)
        victim = spawn('--owner', 'victim', '--key', key_hash,
                       '--loops', '1', '--lease', str(SHORT_LEASE),
                       *child_now())
        # Wait until it has actually claimed, then kill it inside the build.
        while row_of(engine, key_hash)['state'] != 'building':
            time.sleep(0.05)
        claimed_at = time.perf_counter()
        time.sleep(1.0)
        victim.kill()
        victim.communicate()
        killed_at = time.perf_counter()
        after_kill = row_of(engine, key_hash)
        print('  producer killed %.1fs into its build' % (killed_at -
                                                          claimed_at))
        print('  state now: %s, lease_owner %s, fence %d'
              % (after_kill['state'], after_kill['lease_owner'],
                 after_kill['fence']))
        assert after_kill['state'] == 'building'

        store.LEASE_SECONDS = SHORT_LEASE
        blocked = store.claim(engine, 'rescuer', clock())
        print('  a second producer trying to claim BEFORE the lease expires:'
              ' %s' % ('blocked, correctly' if blocked is None
                       else 'CLAIMED IT -- the lease does not hold'))
        assert blocked is None

        # And a reader is not stuck: it gets a truthful `pending`.
        with BuildWatch() as watch:
            answer = reader.read_payload(engine, dict(request), clock(), None)
        assert answer['pending'] and watch.calls == 0
        print('  meanwhile a reader gets `pending` and builds nothing')

        # Watch the lease expire WITHOUT consuming it -- a probe claim would
        # take the lease itself and leave the rescuer nothing to find.
        while row_of(engine, key_hash)['lease_expires_at'] > clock():
            time.sleep(0.1)
        expired_at = time.perf_counter()
        print('  lease expired and was reclaimable %.1fs after the kill'
              % (expired_at - killed_at))
        rescuer = spawn('--owner', 'rescuer', '--key', key_hash,
                        '--loops', '1', '--lease', str(SHORT_LEASE),
                        *child_now())
        out, err = rescuer.communicate(timeout=900)
        recovered = row_of(engine, key_hash)
        print('  rescuer: %s' % out.strip().splitlines()[-1])
        print('  RECOVERY: state=%s, fence=%d, %d payload bytes,'
              ' %.1fs from kill to a ready board'
              % (recovered['state'], recovered['fence'],
                 recovered['payload_bytes'] or 0,
                 time.perf_counter() - killed_at))
        assert recovered['state'] == 'ready'
        print('  -> a hung builder CANNOT poison its key: the lease expires'
              ' and the reclaim increments the fence past it (fence %d)'
              % recovered['fence'])

        # ---- Step 2: fence an overtaken builder --------------------------
        print('\n--- Step 2: an overtaken builder cannot publish ---')
        store.enqueue(engine, key_hash, key_json, clock(), warm=True)
        slow = spawn('--owner', 'slow', '--key', key_hash,
                     '--hang', str(SHORT_LEASE + 12),
                     '--lease', str(SHORT_LEASE), *child_now())
        first = slow.stdout.readline()
        print('  producer 1: %s' % first.strip())
        slow_fence = int(first.split('fence')[1])
        # Wait out producer 1's lease WITHOUT consuming it.
        while row_of(engine, key_hash)['lease_expires_at'] > clock():
            time.sleep(0.1)
        fast = spawn('--owner', 'fast', '--key', key_hash, '--loops', '1',
                     '--lease', str(SHORT_LEASE), *child_now())
        fast_out, _ = fast.communicate(timeout=900)
        published_by_two = row_of(engine, key_hash)
        print('  producer 2 published: state=%s fence=%d'
              % (published_by_two['state'], published_by_two['fence']))
        newer_as_of = published_by_two['as_of']
        slow_out, slow_err = slow.communicate(timeout=900)
        tail = [x for x in slow_out.splitlines() if x.startswith('PUBLISHED')
                or x.startswith('DISCARDED')]
        final = row_of(engine, key_hash)
        print('  producer 1 finally tried to publish: %s' % ' | '.join(tail))
        assert 'PUBLISHED False' in slow_out, slow_out
        assert final['as_of'] == newer_as_of, 'the OLDER result overwrote it'
        print('  its UPDATE matched ZERO rows (fence %d was no longer its'
              ' own) and the newer result stands: as_of %s, fence %d'
              % (slow_fence, final['as_of'], final['fence']))

        # ---- Step 3: a build that always raises --------------------------
        print(NL + '--- Step 3: a build that always raises ---')

        def broken_run(label, minutes, poll_seconds, resets):
            """Simulate `minutes` of a permanently broken key with a reader
            polling every `poll_seconds`, and count the BUILDS it caused."""
            store.ENQUEUE_RESETS_ATTEMPTS = resets
            with engine.begin() as conn:
                conn.execute(sa.text(
                    "UPDATE radar_board_results SET state='ready',"
                    ' attempts=0, next_attempt_at=NULL WHERE key_hash=:k'),
                    {'k': key_hash})
            at = clock()
            with engine.begin() as conn:
                conn.execute(sa.text(
                    'UPDATE radar_board_results SET as_of=:a WHERE key_hash=:k'
                    ), {'a': at - dt.timedelta(seconds=store.MAX_AGE + 60),
                        'k': key_hash})
            builds, schedule, polls = 0, [], 0
            end_at = at + dt.timedelta(minutes=minutes)
            while at < end_at:
                # The island polling. Every poll is a read, and a read of a
                # stale key enqueues a refresh.
                with BuildWatch() as watch:
                    served = reader.read_payload(engine, dict(request), at,
                                                 None)
                polls += 1
                assert watch.calls == 0, 'THE READ PATH BUILT'
                assert served['rows'], 'the last good payload stopped'
                assert served['stale'], 'a stale board was not marked stale'
                key = producer.serve_once(engine, 'broken', at,
                                          key_hash=key_hash, query_cls=Query,
                                          fail_with='boom')
                if key is not None:
                    builds += 1
                    row = row_of(engine, key_hash)
                    schedule.append(
                        (row['attempts'],
                         (row['next_attempt_at'] - at).total_seconds()))
                at = at + dt.timedelta(seconds=poll_seconds)
            print('  %-28s %4d reader polls -> %3d build attempts'
                  % (label, polls, builds))
            print('    backoff schedule (attempts, next retry in): %s'
                  % ', '.join('%d/%.0fs' % x for x in schedule[:9]))
            store.ENQUEUE_RESETS_ATTEMPTS = False
            return builds, schedule, polls

        # Part I.3 as literally written: a reader asking again resets
        # `attempts`. Readers ask constantly.
        bad_builds, bad_schedule, polls = broken_run(
            "Part I.3's reset rule", WINDOW_MIN, 5, True)
        good_builds, good_schedule, _ = broken_run(
            'the park timer', WINDOW_MIN, 5, False)
        print("  -> Part I.3's rule retries %d times in %d minutes -- once"
              ' per poll, with no backoff at all. The park timer retries %d.'
              % (bad_builds, WINDOW_MIN, good_builds))
        assert bad_builds > good_builds * 5, (
            'the reset rule was not actually worse; this proves nothing')
        assert good_builds <= store.MAX_ATTEMPTS + 4, (
            'the fixed schedule is not bounded either: %d builds'
            % good_builds)
        gaps = [gap for _a, gap in good_schedule]
        print('  the fixed backoff GROWS: %s'
              % ', '.join('%.0fs' % g for g in gaps))
        assert gaps == sorted(gaps), 'the backoff does not grow'
        row = row_of(engine, key_hash)
        assert row['attempts'] <= store.MAX_ATTEMPTS, 'attempts unbounded'
        print('  attempts is clamped at MAX_ATTEMPTS=%d (now %d) and the key'
              ' is parked for %ds at a time'
              % (store.MAX_ATTEMPTS, row['attempts'], store.PARK_SECONDS))
        # No unclaimed retry: inside a backoff, claim returns None.
        blocked_now = producer.serve_once(engine, 'broken', clock(),
                                          key_hash=key_hash, query_cls=Query,
                                          fail_with='boom')
        print('  inside the backoff, does anything build unclaimed? %s'
              % ('no -- claim returns None' if blocked_now is None
                 else 'YES, IT DOES'))
        assert blocked_now is None
        with BuildWatch() as watch:
            served = reader.read_payload(engine, dict(request), clock(), None)
        print('  throughout, the reader got the last good board: %d rows,'
              ' %.0fs old, stale=%s, zero builds on the read path'
              % (len(served['rows']), served['age_seconds'],
                 served['stale']))

        # ---- Step 4: producer outage -------------------------------------
        print('\n--- Step 4: the producer is gone for longer than MAX_AGE ---')
        # Test setup, not a product behaviour: step 3 left the key parked
        # 900 simulated seconds out, so clear the failure before starting a
        # clean outage.
        with engine.begin() as conn:
            conn.execute(sa.text(
                "UPDATE radar_board_results SET state='pending', attempts=0,"
                ' next_attempt_at=NULL, last_error=NULL WHERE key_hash=:k'),
                {'k': key_hash})
        producer.serve_once(engine, 'ok', clock(), key_hash=key_hash,
                            query_cls=Query)
        assert row_of(engine, key_hash)['state'] == 'ready'
        # The baseline is the board's OWN as_of, not the wall clock: the age
        # the reader reports has to be checked against the thing it is the
        # age of.
        outage = row_of(engine, key_hash)['as_of']
        for elapsed in (60, store.MAX_AGE + 60, store.HARD_MAX_AGE - 60,
                        store.HARD_MAX_AGE + 60):
            at = outage + dt.timedelta(seconds=elapsed)
            with BuildWatch() as watch:
                served = reader.read_payload(engine, dict(request), at, None)
            assert watch.calls == 0, 'THE READ PATH BUILT'
            kind = ('pending' if served['pending'] else
                    'stale board' if served['stale'] else 'fresh board')
            print('  %5ds into the outage: %-12s age reported %s   rows %s'
                  % (elapsed, kind,
                     ('%.0fs' % served['age_seconds']
                      if served['age_seconds'] is not None else 'n/a'),
                     len(served['rows']) if served['rows'] else 0))
            if served['age_seconds'] is not None:
                assert abs(served['age_seconds'] - elapsed) < 2, (
                    'the reported age is not the real age')
        print('  every reported age is the REAL age, and no web-path build'
              ' was started at any point (the tripwire would have raised)')
        back = producer.serve_once(engine, 'ok', clock(), key_hash=key_hash,
                                   query_cls=Query)
        print('  producer comes back: %s, state=%s -- no manual step'
              % (back[:12], row_of(engine, key_hash)['state']))
        assert row_of(engine, key_hash)['state'] == 'ready'

        # ---- Step 5: no long transactions --------------------------------
        print('\n--- Step 5: is a transaction held across the build? ---')
        seen = instrument(engine)
        db.session.remove()
        store.enqueue(engine, key_hash, key_json, clock(), warm=True)
        producer.serve_once(engine, 'timed', clock(), key_hash=key_hash,
                            query_cls=Query)
        db.session.remove()
        seen.sort(reverse=True)
        print('  every transaction on the engine during one produce cycle,'
              ' longest first:')
        for duration, how, statement in seen[:6]:
            print('    %7.3fs  %-8s %s' % (duration, how, statement))
        store_txns = [s for s in seen if 'radar_board_results' in s[2]]
        longest_store = max(s[0] for s in store_txns) if store_txns else 0.0
        longest_any = max(s[0] for s in seen) if seen else 0.0
        print('  longest transaction touching radar_board_results: %.3fs'
              % longest_store)
        print('  longest transaction of ANY kind: %.3fs' % longest_any)
        assert longest_store < 1.0, (
            'the claim or publish transaction spans the build')
        print('  -> the claim commits before the build and the publish opens'
              ' its own transaction after it. NOTHING holds a transaction'
              ' across `board.build`.')
        print('  BUT the build itself is one long READ transaction: the ORM'
              ' session opens on its first SELECT and does not close until'
              ' the session does. That is the %.3fs above and it is a real'
              ' cost on the target, where it pins a read view for that long.'
              % longest_any)

        print('\nS6 done.')


if __name__ == '__main__':
    main()

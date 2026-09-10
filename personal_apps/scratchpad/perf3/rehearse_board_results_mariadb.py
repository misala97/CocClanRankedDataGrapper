"""Rehearse the board-result migration, and the store itself, on MariaDB.

The production target is MariaDB 10.11.14; local development is MySQL 8.0.46.
A green MySQL suite is not evidence about MariaDB, and this migration and this
store lean on several things the two engines are entitled to disagree about:

  * whether a TEXT column really holds a 4,000-character key under a permissive
    `sql_mode` instead of truncating it with a warning nobody reads,
  * whether `rowcount` after a fenced UPDATE counts matched rows or changed
    rows -- the whole fence answers False if that differs, and every publish
    would be discarded as overtaken,
  * `ON DUPLICATE KEY UPDATE` evaluating its assignments left to right, which
    is what lets `enqueued_at` read `queue_state` before `queue_state` is
    reassigned in the same statement,
  * `SELECT ... FOR UPDATE`, `GREATEST` over a BOOLEAN column, `SUM(condition)`
    and a bound `LIMIT`, all of which the store issues as raw SQL.

    PYTHONPATH=. py -3.12 scratchpad/perf3/rehearse_board_results_mariadb.py

It needs a disposable MariaDB at REHEARSAL_URL and refuses to touch anything
else: loopback only, MariaDB only, and never one of the real schema names. It
builds its own Flask app rather than importing `app`, because app.py points at
port 3306 where MySQL is listening; nothing in the application is modified to
run this, and the whole schema is dropped and rebuilt on every run.
"""
import datetime as dt
import os
import sys
import zlib

sys.path.insert(0, '.')

import sqlalchemy as sa                                       # noqa: E402
from flask import Flask                                       # noqa: E402
from flask_migrate import Migrate, downgrade, stamp, upgrade   # noqa: E402

from extensions import db                                      # noqa: E402
import models                                                  # noqa: E402,F401
from features.radar import board_keys, board_namespace, board_store  # noqa: E402

# The revision that creates radar_board_observations, so the neighbour table
# the downgrade must leave alone is really there. Stamping a7c31f0b52d4 onto an
# empty schema would leave nothing for that check to be about.
BASE_REVISION = 'b3d9e1f5a274'
PREVIOUS = 'a7c31f0b52d4'
REVISION = 'b7e3f9c1a2d4'

NEW_TABLES = {'radar_board_namespaces', 'radar_board_results'}
NEW_INDEXES = {'ix_radar_board_results_queue',
               'ix_radar_board_results_warm',
               'ix_radar_board_results_demand'}

HOST = os.getenv('REHEARSAL_HOST', '127.0.0.1')
PORT = os.getenv('REHEARSAL_PORT', '3399')
USER = os.getenv('REHEARSAL_USER', 'root')
PASSWORD = os.getenv('REHEARSAL_PASSWORD', '')
SCHEMA = os.getenv('REHEARSAL_SCHEMA', 'radar_perf3_rehearsal')

SERVER_URL = f'mysql+pymysql://{USER}:{PASSWORD}@{HOST}:{PORT}/'
REHEARSAL_URL = SERVER_URL + SCHEMA

NOW = dt.datetime(2026, 9, 10, 12, 0, 0)
REVISION_STAMP = 'a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0'

# A stand-in key body for the synthetic keys the bound and eviction checks
# need. Bound as a parameter rather than written into the SQL: `sa.text`
# reads `:2` inside a literal as a bind parameter named `2`.
KEY_JSON = '{"v":2,"rehearsal":true}'

# Every byte value, so a column or a driver that decided this was text shows
# itself rather than passing on the well-behaved half of the range.
BLOB = bytes(range(256)) * 48

FAILURES = []
COUNT = 0


def check(label, condition, detail=''):
    global COUNT
    COUNT += 1
    mark = 'PASS' if condition else 'FAIL'
    print(f'  {COUNT:2d}. {mark}  {label}' + (f' -- {detail}' if detail else ''))
    if not condition:
        FAILURES.append(f'{COUNT}. {label}')


def seconds(count):
    return dt.timedelta(seconds=count)


def make_app():
    application = Flask('radar-perf3-rehearsal')
    application.config['SQLALCHEMY_DATABASE_URI'] = REHEARSAL_URL
    application.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(application)
    Migrate(application, db, directory='migrations')
    return application


def recreate_schema():
    """A fresh, empty database every run, behind three guards.

    The host must be loopback, so no remote server is reachable whatever the
    environment says. The schema must not be one of the real names. And the
    server must be MariaDB, checked BEFORE anything is dropped -- substituting
    MySQL here would produce a green run that is not evidence about the target,
    which is the one failure mode this whole script exists to prevent.
    """
    if HOST not in ('127.0.0.1', 'localhost', '::1'):
        raise SystemExit(
            f'refusing to run against host {HOST!r}: this rehearsal drops and '
            f'recreates its schema and must only reach a disposable server on '
            f'this machine')
    if SCHEMA in ('personal_apps', 'coc_stats') or SCHEMA.startswith(
            'personal_apps_radar_perf'):
        raise SystemExit(f'refusing to use schema {SCHEMA!r}')

    engine = sa.create_engine(SERVER_URL, isolation_level='AUTOCOMMIT')
    with engine.connect() as connection:
        version = connection.execute(sa.text('select version()')).scalar()
        if 'mariadb' not in version.lower():
            raise SystemExit(
                f'refusing to rehearse against {version!r}: the target is '
                f'MariaDB and a MySQL result would not be evidence about it')
        strict = connection.execute(sa.text('select @@sql_mode')).scalar()
        connection.execute(sa.text(f'drop database if exists `{SCHEMA}`'))
        connection.execute(sa.text(
            f'create database `{SCHEMA}` character set utf8mb4'))
    engine.dispose()
    return version, strict


def tables():
    with db.engine.connect() as connection:
        return {row[0] for row in connection.execute(sa.text('show tables'))}


def indexes(table):
    with db.engine.connect() as connection:
        return {row[0] for row in connection.execute(sa.text(
            'select index_name from information_schema.statistics'
            ' where table_schema = :schema and table_name = :table'),
            {'schema': SCHEMA, 'table': table})}


def columns(table):
    with db.engine.connect() as connection:
        return {row[0]: (row[1], row[2]) for row in connection.execute(sa.text(
            'select column_name, column_type, is_nullable'
            ' from information_schema.columns'
            ' where table_schema = :schema and table_name = :table'),
            {'schema': SCHEMA, 'table': table})}


def stamped():
    with db.engine.connect() as connection:
        return connection.execute(
            sa.text('select version_num from alembic_version')).scalar()


def long_key():
    """A legal key at the width the column has to survive: 37 sources of
    long-but-legal names, canonicalised by the real key writer."""
    from features.radar.routes.api import Query

    names = ['reddit:' + ('x' * 100) + str(index) for index in range(37)]
    return board_keys.canonical(Query(
        sources=names, segments=['mid', 'micro', 'mid'], window=24, limit=100,
        min_venues=2, market='de', sort='lean', direction='asc'))


def store_the_wide_row(mode, key_hash, key_json):
    """Insert the widest legal row under one `sql_mode`, and report warnings."""
    with db.engine.begin() as connection:
        connection.execute(sa.text('set session sql_mode = :mode'),
                           {'mode': mode})
        connection.execute(sa.text(
            'insert into radar_board_results'
            ' (namespace, key_hash, key_json, payload_version, queue_state,'
            '  warm, payload, payload_bytes, requested_at, request_count,'
            '  attempts) values'
            ' (:ns, :key, :json, 1, :state, 0, :blob, :size, :now, 1, 0)'
        ).bindparams(sa.bindparam('blob', type_=sa.LargeBinary)),
            {'ns': 'widths', 'key': key_hash, 'json': key_json,
             'state': 'idle', 'blob': BLOB, 'size': len(BLOB), 'now': NOW})
        warnings = connection.execute(sa.text('show warnings')).fetchall()

    with db.engine.connect() as connection:
        stored = connection.execute(sa.text(
            'select key_json, payload, payload_bytes from radar_board_results'
            ' where namespace = :ns and key_hash = :key'),
            {'ns': 'widths', 'key': key_hash}).one()
    with db.engine.begin() as connection:
        connection.execute(sa.text(
            'delete from radar_board_results where namespace = :ns'),
            {'ns': 'widths'})
    return stored, warnings


def main():
    version, strict = recreate_schema()
    print(f'engine: {version}  schema: {SCHEMA}  port: {PORT}')
    print(f'strict sql_mode here: {strict}')
    print(f'target of record: MariaDB 10.11.14 (VPS)\n')

    application = make_app()
    with application.app_context():
        engine = db.engine

        # --- 1. the schema, brought to the revision below the new one -------
        print('1. the schema, at the revision this migration follows')
        stamp(revision=BASE_REVISION)
        upgrade(revision=PREVIOUS)
        check('the previous revision is stamped', stamped() == PREVIOUS,
              stamped())
        before = tables()
        check('the neighbour table this must not disturb exists',
              'radar_board_observations' in before)
        check('neither new table exists yet', not (NEW_TABLES & before),
              f'found {sorted(NEW_TABLES & before)}' if NEW_TABLES & before
              else '')

        # --- 2. the upgrade -------------------------------------------------
        print('\n2. the upgrade, on MariaDB')
        upgrade(revision=REVISION)
        after = tables()
        check('the new revision is stamped', stamped() == REVISION, stamped())
        check('the upgrade created exactly its two tables',
              after - before == NEW_TABLES, f'{sorted(after - before)}')
        found = indexes('radar_board_results')
        check('all three indexes exist', NEW_INDEXES <= found,
              f'{sorted(NEW_INDEXES - found)} missing'
              if NEW_INDEXES - found else '')
        check('the primary key is (namespace, key_hash)', 'PRIMARY' in found)
        shape = columns('radar_board_results')
        check('key_json is TEXT', shape['key_json'][0] == 'text',
              shape['key_json'][0])
        check('payload is MEDIUMBLOB', shape['payload'][0] == 'mediumblob',
              shape['payload'][0])
        check('lease_token is varchar(32)',
              shape['lease_token'][0] == 'varchar(32)', shape['lease_token'][0])
        check('timestamps keep microsecond precision',
              shape['as_of'][0] == 'datetime(6)', shape['as_of'][0])
        control = columns('radar_board_namespaces')
        check('the control row carries the producer fields',
              {'producer_owner', 'producer_seen_at', 'producer_success_at',
               'producer_error'} <= set(control))

        # --- 3. the widths, under both sql_modes ----------------------------
        print('\n3. the widest legal row, under both sql_modes')
        key_hash, key_json = long_key()
        check('the fixture key is the width the column was chosen for',
              len(key_json) > 3500, f'{len(key_json)} characters')
        for label, mode in (('permissive', ''), ('strict', strict)):
            stored, warnings = store_the_wide_row(mode, key_hash, key_json)
            check(f'the 4,000-character key survives sql_mode={label}',
                  stored.key_json == key_json,
                  f'{len(stored.key_json)} of {len(key_json)} characters')
            check(f'the stored key still hashes to its own name ({label})',
                  board_keys.round_trips(key_hash, stored.key_json))
            check(f'the 12 KB payload is byte-identical ({label})',
                  stored.payload == BLOB and stored.payload_bytes == len(BLOB))
            check(f'the insert raised no warning ({label})', not warnings,
                  '; '.join(str(w) for w in warnings))

        # --- 4. the store itself, against this engine -----------------------
        print('\n4. the store, on MariaDB')
        namespace = 'rehearsal-' + REVISION_STAMP[:20]
        board_store.ensure_namespace(engine, namespace, NOW,
                                     revision=REVISION_STAMP,
                                     payload_version=1)
        check('ensure_namespace wrote a control row',
              board_store.health(engine, namespace).get('producer_revision')
              == REVISION_STAMP)

        state = board_store.admit(engine, namespace, key_hash, key_json, NOW)
        check('admit queues a cold key', state == 'pending', state)
        repeat = board_store.admit(engine, namespace, key_hash, key_json,
                                   NOW + seconds(30))
        row = board_store.read(engine, namespace, key_hash)
        check('a repeat admission deduplicates rather than duplicating',
              repeat == 'pending' and row.request_count == 2,
              f'{repeat}, count={row.request_count}')
        check('ON DUPLICATE KEY UPDATE kept the queue position here too',
              row.enqueued_at == NOW and row.requested_at == NOW + seconds(30),
              f'enqueued {row.enqueued_at}, requested {row.requested_at}')
        board_store.admit(engine, namespace, key_hash, key_json,
                          NOW + seconds(60), poll=True)
        check('a poll records no request',
              board_store.read(engine, namespace,
                               key_hash).request_count == 2)

        claim = board_store.claim(engine, namespace, 'rehearsal:1', NOW,
                                  prefer='demand')
        check('claim takes a 32-hex fenced lease',
              claim is not None and len(claim.token) == 32
              and claim.key_json == key_json,
              '' if claim else 'nothing claimable')
        blob = zlib.compress(BLOB, 6)
        published = board_store.publish(
            engine, namespace, claim, blob, as_of=NOW + seconds(1),
            built_at=NOW + seconds(4), build_ms=3210,
            producer_revision=REVISION_STAMP)
        check('publish under the live token succeeds', published is True,
              'rowcount semantics differ on this engine' if not published
              else '')
        result = board_store.read(engine, namespace, key_hash)
        check('the payload round-trips through the store',
              result.payload == blob
              and zlib.decompress(result.payload) == BLOB)
        check('publish recorded the build',
              result.queue_state == 'idle' and result.build_ms == 3210
              and result.as_of == NOW + seconds(1)
              and result.built_at == NOW + seconds(4),
              f'{result.queue_state}, {result.as_of}, {result.built_at}')
        check('the payload version is the running one',
              result.payload_version == board_namespace.PAYLOAD_VERSION)

        # The fence, which is the check most likely to differ between engines:
        # a stale token must match nothing at all.
        again = board_store.admit(engine, namespace, key_hash, key_json,
                                  NOW + seconds(300))
        second = board_store.claim(engine, namespace, 'rehearsal:2',
                                   NOW + seconds(300), prefer='demand')
        check('a reclaim mints a different token',
              second is not None and second.token != claim.token)
        check('the overtaken builder cannot publish',
              board_store.publish(engine, namespace, claim, b'stale',
                                  as_of=NOW, built_at=NOW, build_ms=1,
                                  producer_revision=REVISION_STAMP) is False,
              f'(re-admitted as {again})')
        check('the overtaken builder cannot fail the row either',
              board_store.fail(engine, namespace, claim, 'RuntimeError',
                               NOW + seconds(300)) is False)
        check('the row still carries the newer lease',
              board_store.read(engine, namespace,
                               key_hash).queue_state == 'building')

        failed = board_store.fail(engine, namespace, second, 'RuntimeError',
                                  NOW + seconds(300))
        row = board_store.read(engine, namespace, key_hash)
        check('fail backs the key off and keeps the published board',
              failed is True and row.queue_state == 'failed'
              and row.next_attempt_at == NOW + seconds(330)
              and row.payload == blob,
              f'{row.queue_state}, next {row.next_attempt_at}')
        parked = board_store.admit(engine, namespace, key_hash, key_json,
                                   NOW + seconds(310))
        check('a reader cannot shorten a backoff', parked == 'parked', parked)

        # The bound, and the lock it is enforced under. One key is already
        # `failed` and past its backoff, and that counts as an admitted job,
        # so the cap is reached one short of `max_queue` fresh admissions.
        limits = board_store.limits()
        answers = [board_store.admit(engine, namespace, f'1{index:063x}',
                                     KEY_JSON, NOW + seconds(400))
                   for index in range(limits.max_queue)]
        accepted = answers.count('pending')
        check('the queue cap counts the failed-due key among the admitted',
              accepted == limits.max_queue - 1 and 'busy' in answers,
              f'{accepted} admitted beside one key waiting to be retried')
        refused = board_store.admit(engine, namespace, 'f' * 64, KEY_JSON,
                                    NOW + seconds(400))
        check('the queue cap refuses past its bound', refused == 'busy',
              refused)
        check('a refused admission wrote nothing',
              board_store.read(engine, namespace, 'f' * 64) is None)
        warm_state = board_store.admit(engine, namespace, 'e' * 64, KEY_JSON,
                                       NOW + seconds(400), warm=True)
        check('warm work is never refused', warm_state == 'pending',
              warm_state)

        summary = board_store.queue_summary(engine, namespace,
                                            NOW + seconds(400))
        check('queue_summary counts on this engine',
              summary == {'pending': accepted + 1, 'building': 0,
                          'failed_due': 1, 'on_demand_rows': accepted + 1,
                          'warm_ready': 0},
              str(summary))

        moved = board_store.refresh_warm(
            engine, namespace, [('a' * 64, KEY_JSON)], NOW + seconds(400))
        due = board_store.due_warm(engine, namespace, NOW + seconds(400))
        check('the warm sweep adopts and enqueues a never-built key',
              moved == 1 and 'a' * 64 in due, f'moved={moved}, due={len(due)}')

        seeded = limits.max_on_demand + 20
        with engine.begin() as connection:
            connection.execute(sa.text(
                'insert into radar_board_results'
                ' (namespace, key_hash, key_json, payload_version,'
                '  queue_state, warm, requested_at, request_count, attempts)'
                " values (:ns, :key, :json, 1, 'idle', 0, :at, 1, 0)"),
                [{'ns': namespace, 'key': f'2{index:063x}', 'json': KEY_JSON,
                  'at': NOW - seconds(seeded - index)}
                 for index in range(seeded)])
        removed = board_store.evict(engine, namespace, NOW + seconds(500))
        with engine.connect() as connection:
            remaining = connection.execute(sa.text(
                'select count(*) from radar_board_results'
                ' where namespace = :ns and warm = 0'), {'ns': namespace}
            ).scalar()
        check('eviction brings the on-demand rows back inside the bound',
              remaining == limits.max_on_demand,
              f'removed {removed}, {remaining} left')

        board_store.heartbeat(engine, namespace, 'rehearsal:1',
                              NOW + seconds(600), error='RuntimeError')
        board_store.heartbeat(engine, namespace, 'rehearsal:1',
                              NOW + seconds(660), success_at=NOW + seconds(659))
        reported = board_store.health(engine, namespace)
        check('the producer fields round-trip',
              reported['producer_owner'] == 'rehearsal:1'
              and reported['producer_success_at'] == NOW + seconds(659)
              and reported['producer_error'] is None,
              f"error still {reported['producer_error']!r}"
              if reported['producer_error'] else '')

        # Both generations are introduced and admitted at the same long-ago
        # moment; the only difference is that one of them is still being read.
        # An admission moves `last_seen_at` under the control-row lock, so
        # admitting into the stale one at NOW would keep it alive and this
        # check would be about nothing.
        long_ago = NOW - seconds(limits.retire_seconds + 60)
        for forgotten in ('rehearsal-stale', 'rehearsal-watched'):
            board_store.ensure_namespace(engine, forgotten, long_ago,
                                         revision=REVISION_STAMP,
                                         payload_version=1)
            board_store.admit(engine, forgotten, 'b' * 64, KEY_JSON, long_ago)
        board_store.admit(engine, 'rehearsal-watched', 'b' * 64, KEY_JSON, NOW,
                          poll=True)
        retired = board_store.retire_namespaces(engine, namespace, NOW)
        check('a generation nothing has touched is retired whole',
              retired == 1
              and board_store.health(engine, 'rehearsal-stale') == {}
              and board_store.read(engine, 'rehearsal-stale',
                                   'b' * 64) is None,
              f'retired {retired}')
        check('a reader alone keeps a generation alive on this engine too',
              bool(board_store.health(engine, 'rehearsal-watched'))
              and board_store.read(engine, 'rehearsal-watched',
                                   'b' * 64) is not None,
              'GREATEST(last_seen_at, :now) under the lock')
        check("the caller's own generation survived retirement",
              bool(board_store.health(engine, namespace)))

        # --- 5. the downgrade, and back up ----------------------------------
        print('\n5. the downgrade and the re-upgrade')
        with db.engine.connect() as connection:
            archive = connection.execute(sa.text(
                'select count(*) from radar_board_observations')).scalar()
        downgrade(revision=PREVIOUS)
        rolled_back = tables()
        check('the downgrade dropped exactly the two tables',
              not (NEW_TABLES & rolled_back)
              and rolled_back == before,
              f'differs by {sorted(rolled_back ^ before)}'
              if rolled_back ^ before else '')
        check('the downgrade left the neighbour table intact',
              'radar_board_observations' in rolled_back)
        with db.engine.connect() as connection:
            check('the neighbour table kept its rows',
                  connection.execute(sa.text(
                      'select count(*) from radar_board_observations')).scalar()
                  == archive)
        check('the downgrade left the previous revision stamped',
              stamped() == PREVIOUS, stamped())

        upgrade(revision=REVISION)
        check('a second upgrade rebuilds the same shape',
              tables() == after
              and columns('radar_board_results') == shape
              and NEW_INDEXES <= indexes('radar_board_results'))
        check('the second upgrade leaves the new revision stamped',
              stamped() == REVISION, stamped())

    print(f'\n{"FAILURES: " + ", ".join(FAILURES) if FAILURES else "all %d checks passed" % COUNT}')
    return 1 if FAILURES else 0


if __name__ == '__main__':
    raise SystemExit(main())

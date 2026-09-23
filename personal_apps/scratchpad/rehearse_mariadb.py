"""P1: rehearse both radar migrations, and their failure recovery, on MariaDB.

The production target is MariaDB 10.11.14; local development is MySQL 8.0.46.
They differ exactly where these two migrations are most delicate -- MariaDB
stores `JSON` as an alias for `LONGTEXT`, and its DDL auto-commits so no
surrounding transaction can undo a half-applied `ALTER` -- so a MySQL result is
not evidence about the target and this script exists to stop anyone pretending
it is.

    PYTHONPATH=. py -3.12 scratchpad/rehearse_mariadb.py

It needs a disposable MariaDB reachable at REHEARSAL_URL and it refuses to touch
anything else. It builds its own Flask app rather than importing `app`, because
app.py hard-codes port 3306 where MySQL already listens; nothing in the
application is modified to run this.

What it rehearses, per Codex's P1:

  1. A clean upgrade of both revisions over pre-existing rows, checking the
     backfill's projections and that no envelope changed.
  2. Interruption after only SOME columns exist -- the state a failing sequence
     of ALTER TABLE statements leaves, since each one commits on its own.
  3. Interruption partway through the backfill, which leaves every column
     present, the revision unstamped and the projection half-written.
  4. Recovery from both, by the documented drop-derived-columns route, followed
     by a clean upgrade -- and the result compared column by column against the
     clean upgrade of step 1.
  5. The normal downgrade/upgrade round trip on this engine.

Nothing here writes to any database but the rehearsal one, and the whole
database is dropped and rebuilt at the start of every run.
"""
import datetime as dt
import json
import os
import sys

sys.path.insert(0, '.')

import sqlalchemy as sa                                     # noqa: E402
from flask import Flask                                    # noqa: E402
from flask_migrate import Migrate, downgrade, stamp, upgrade  # noqa: E402

from extensions import db                                   # noqa: E402
import models                                               # noqa: E402,F401
from features.radar import activity                         # noqa: E402

# The revision the target is already at: everything below the two under test.
BASE_REVISION = 'b3d9e1f5a274'
OBSERVATIONS = 'd82f9afb5898'
PROJECTION = 'a7c31f0b52d4'

PROJECTION_COLUMNS = ('summary_schema_version', 'summary_countable',
                      'posts_seen', 'posts_new', 'mentions', 'buckets_written')

HOST = os.getenv('REHEARSAL_HOST', '127.0.0.1')
PORT = os.getenv('REHEARSAL_PORT', '3399')
USER = os.getenv('REHEARSAL_USER', 'root')
PASSWORD = os.getenv('REHEARSAL_PASSWORD', '')
SCHEMA = os.getenv('REHEARSAL_SCHEMA', 'radar_rehearsal')

SERVER_URL = f'mysql+pymysql://{USER}:{PASSWORD}@{HOST}:{PORT}/'
REHEARSAL_URL = SERVER_URL + SCHEMA

BASE = dt.datetime(2019, 7, 3, 9, 0)

# One row of every shape the projection has to classify, written the way the
# PREVIOUS revision wrote them: an envelope and nothing else.
FIXTURES = [
    ('00-valid', 'ok', {'schema_version': 1,
                        'summary': {'posts_seen': 11, 'posts_new': 4,
                                    'mentions': 2, 'buckets_written': 1}}),
    ('01-zero', 'ok', {'schema_version': 1,
                       'summary': {'posts_seen': 0, 'posts_new': 0,
                                   'mentions': 0, 'buckets_written': 0}}),
    ('02-partial', 'ok', {'schema_version': 1, 'summary': {'posts_seen': 7}}),
    ('03-null-counter', 'ok', {'schema_version': 1,
                               'summary': {'posts_seen': None,
                                           'posts_new': 1}}),
    ('04-off-version', 'ok', {'schema_version': 99,
                              'summary': {'posts_seen': 5}}),
    ('05-float-version', 'ok', {'schema_version': 1.0,
                                'summary': {'posts_seen': 5}}),
    ('06-unversioned', 'ok', {'summary': {'posts_seen': 5}}),
    ('07-bad-summary', 'ok', {'schema_version': 1, 'summary': 'nope'}),
    ('08-not-a-mapping', 'ok', 'not an envelope at all'),
    ('09-no-envelope', 'ok', None),
    ('10-running', 'running', None),
    ('11-error', 'error', None),
]


def make_app():
    application = Flask('radar-rehearsal')
    application.config['SQLALCHEMY_DATABASE_URI'] = REHEARSAL_URL
    application.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(application)
    Migrate(application, db, directory='migrations')
    return application


def recreate_schema():
    """A fresh, empty database every run.

    Three guards, and it is worth being exact about what each one does rather
    than claiming they add up to more than they do. The host must be loopback,
    so no remote server can be reached whatever the environment says. The
    schema must not be one of the two real names. And the server must be
    MariaDB, checked BEFORE anything is dropped -- a MySQL result would not be
    evidence about the target, and the point is to make substituting one
    impossible rather than merely discouraged.

    What they do NOT do is protect an arbitrary schema name on a loopback
    MariaDB: any other name is dropped and recreated.
    """
    if HOST not in ('127.0.0.1', 'localhost', '::1'):
        raise SystemExit(
            f'refusing to run against host {HOST!r}: this rehearsal drops and '
            f'recreates its schema, and must only ever reach a disposable '
            f'server on this machine')
    if SCHEMA in ('personal_apps', 'coc_stats'):
        raise SystemExit(f'refusing to use schema {SCHEMA!r}')
    engine = sa.create_engine(SERVER_URL, isolation_level='AUTOCOMMIT')
    with engine.connect() as connection:
        version = connection.execute(sa.text('select version()')).scalar()
        if 'mariadb' not in version.lower():
            raise SystemExit(
                f'refusing to rehearse against {version!r}: P1 requires '
                f'MariaDB, and a MySQL result would not be evidence about the '
                f'target')
        connection.execute(sa.text(f'drop database if exists `{SCHEMA}`'))
        connection.execute(sa.text(
            f'create database `{SCHEMA}` character set utf8mb4'))
    engine.dispose()
    return version


def seed_envelopes():
    """Rows as the revision below PROJECTION would have written them."""
    with db.engine.begin() as connection:
        for index, (run_id, status, envelope) in enumerate(FIXTURES):
            connection.execute(
                sa.text('insert into radar_ingest_runs '
                        '(id, started_at, finished_at, status, summary_json, '
                        ' error_code) values '
                        '(:id, :started, :finished, :status, :body, :code)'),
                {'id': run_id, 'started': BASE + dt.timedelta(minutes=index),
                 'finished': BASE + dt.timedelta(minutes=index, seconds=30),
                 'status': status,
                 'body': None if envelope is None else json.dumps(envelope),
                 'code': 'ingest_failed' if status == 'error' else None})


def columns():
    with db.engine.connect() as connection:
        return {row[0] for row in connection.execute(
            sa.text('show columns from radar_ingest_runs'))}


def stamped():
    with db.engine.connect() as connection:
        return connection.execute(
            sa.text('select version_num from alembic_version')).scalar()


def envelopes():
    """The source data, which every path must leave untouched."""
    with db.engine.connect() as connection:
        return [tuple(row) for row in connection.execute(sa.text(
            'select id, status, summary_json, started_at, finished_at, '
            'error_code from radar_ingest_runs order by id'))]


def projection():
    with db.engine.connect() as connection:
        return [tuple(row) for row in connection.execute(sa.text(
            'select id, summary_schema_version, summary_countable, '
            'posts_seen, posts_new, mentions, buckets_written '
            'from radar_ingest_runs order by id'))]


def drop_projection_columns(present):
    """The documented recovery. Only columns confirmed present are dropped --
    a failure partway through the ALTER sequence leaves fewer than six, and the
    literal statement in the migration docstring would itself fail."""
    with db.engine.begin() as connection:
        for name in PROJECTION_COLUMNS:
            if name in present:
                connection.execute(sa.text(
                    f'alter table radar_ingest_runs drop column {name}'))


def raw_upgrade(revision):
    """Alembic's own upgrade, so an exception from inside a migration reaches
    the caller. `flask_migrate.upgrade` wraps commands in a handler that logs
    and calls sys.exit, which a rehearsal cannot inspect."""
    from alembic import command as alembic_command
    from alembic.config import Config
    config = Config('migrations/alembic.ini')
    config.set_main_option('script_location', 'migrations')
    alembic_command.upgrade(config, revision)


def check(label, condition, detail=''):
    mark = 'PASS' if condition else 'FAIL'
    print(f'  {mark}  {label}' + (f' -- {detail}' if detail else ''))
    if not condition:
        FAILURES.append(label)


FAILURES = []


def main():
    version = recreate_schema()
    print(f'engine: {version}  schema: {SCHEMA}  port: {PORT}')
    print(f'target of record: MariaDB 10.11.14 (VPS)\n')

    application = make_app()
    with application.app_context():
        # --- 1. clean upgrade over pre-existing rows ----------------------
        print('1. clean upgrade of both revisions, over rows that already exist')
        stamp(revision=BASE_REVISION)
        upgrade(revision=OBSERVATIONS)
        check('d82f9afb5898 applied', stamped() == OBSERVATIONS, stamped())
        seed_envelopes()
        source_before = envelopes()
        check('fixtures seeded', len(source_before) == len(FIXTURES),
              f'{len(source_before)} rows')

        upgrade(revision=PROJECTION)
        check('a7c31f0b52d4 applied', stamped() == PROJECTION, stamped())
        check('all six columns present',
              set(PROJECTION_COLUMNS) <= columns())
        check('every envelope unchanged by the upgrade',
              envelopes() == source_before)

        clean = projection()
        # The backfill must reproduce exactly what the live writer would store.
        mismatches = []
        for row in clean:
            stored = dict(zip(('id', 'version', 'countable', 'posts_seen',
                               'posts_new', 'mentions', 'buckets_written'),
                              row))
            body = next(envelope for name, _, envelope in FIXTURES
                        if name == stored['id'])
            want_version, want_countable, want_counters = activity.project(body)
            if (stored['version'] != want_version
                    or bool(stored['countable']) != want_countable
                    or any(stored[name] != want_counters[name]
                           for name in activity.COUNTERS)):
                mismatches.append(stored['id'])
        check('backfill equals the live projection for every shape',
              not mismatches, f'mismatched: {mismatches}' if mismatches else '')

        by_id = {row[0]: row for row in clean}
        check('a float schema_version is not countable',
              by_id['05-float-version'][2] == 0,
              'MariaDB stores JSON as LONGTEXT; 1.0 must not become 1')
        check('a measured zero survives', by_id['01-zero'][3] == 0)
        check('an omitted counter stays null',
              by_id['02-partial'][4] is None)
        check('an off-version row is countable but its version differs',
              by_id['04-off-version'][2] == 1
              and by_id['04-off-version'][1] == 99)

        # --- 5. downgrade / upgrade round trip ----------------------------
        print('\n2. downgrade and re-upgrade on this engine')
        downgrade(revision=OBSERVATIONS)
        check('downgrade removed every projection column',
              not (set(PROJECTION_COLUMNS) & columns()))
        check('downgrade preserved every envelope',
              envelopes() == source_before)
        upgrade(revision=PROJECTION)
        check('re-upgrade rebuilds the identical projection',
              projection() == clean)

        # BOTH downgrades, not just the projection's. The runbook's rollback
        # command names b3d9e1f5a274, which unwinds d82f9afb5898 as well, and
        # an untested drop_table is not something to discover during a
        # rollback. It runs last in this block because it destroys the rows
        # every earlier step depends on.
        with db.engine.connect() as connection:
            tables_before = {row[0] for row in connection.execute(
                sa.text('show tables'))}
        downgrade(revision=BASE_REVISION)
        with db.engine.connect() as connection:
            tables_after = {row[0] for row in connection.execute(
                sa.text('show tables'))}
        check('the full downgrade drops exactly the two tables it created',
              tables_before - tables_after
              == {'radar_ingest_runs', 'radar_board_observations'},
              f'removed: {sorted(tables_before - tables_after)}')
        check('the full downgrade adds nothing',
              not (tables_after - tables_before))
        check('the full downgrade leaves the base revision stamped',
              stamped() == BASE_REVISION, stamped())

        # Back up, and reseed, so the interruption steps below have rows.
        upgrade(revision=OBSERVATIONS)
        seed_envelopes()
        upgrade(revision=PROJECTION)
        check('a full re-upgrade reproduces the clean projection',
              projection() == clean)
        check('a full re-upgrade reproduces the source rows',
              envelopes() == source_before)

        # --- 2. interruption after only some columns exist ----------------
        print('\n3. interrupted after only some columns exist')
        downgrade(revision=OBSERVATIONS)
        with db.engine.begin() as connection:
            for name in PROJECTION_COLUMNS[:3]:
                kind = ('int' if name == 'summary_schema_version'
                        else 'tinyint(1) not null default 0'
                        if name == 'summary_countable' else 'bigint')
                connection.execute(sa.text(
                    f'alter table radar_ingest_runs add column {name} {kind}'))
        partial = columns() & set(PROJECTION_COLUMNS)
        check('three of six columns exist, revision unstamped',
              len(partial) == 3 and stamped() == OBSERVATIONS,
              f'{sorted(partial)} at {stamped()}')
        check('source data survived the partial DDL',
              envelopes() == source_before)
        # Re-running the upgrade here is what an operator would try first.
        try:
            upgrade(revision=PROJECTION)
            check('a blind re-upgrade over partial columns fails', False,
                  'it succeeded, which the runbook does not expect')
        except Exception as problem:                         # noqa: BLE001
            check('a blind re-upgrade over partial columns fails loudly',
                  'uplicate column' in str(problem),
                  type(problem).__name__)
        drop_projection_columns(columns() & set(PROJECTION_COLUMNS))
        check('recovery dropped only what was there',
              not (set(PROJECTION_COLUMNS) & columns()))
        upgrade(revision=PROJECTION)
        check('recovery then upgrade reproduces the clean projection',
              projection() == clean)
        check('recovery preserved every envelope',
              envelopes() == source_before)

        # --- 3. interruption partway through the backfill -----------------
        print('\n4. interrupted partway through the backfill')
        downgrade(revision=OBSERVATIONS)
        with db.engine.begin() as connection:
            for name in PROJECTION_COLUMNS:
                kind = ('int' if name == 'summary_schema_version'
                        else 'tinyint(1) not null default 0'
                        if name == 'summary_countable' else 'bigint')
                connection.execute(sa.text(
                    f'alter table radar_ingest_runs add column {name} {kind}'))
            # Half the rows projected, the rest still default -- what a killed
            # backfill leaves behind.
            for run_id, _, body in FIXTURES[:5]:
                version, countable, counters = activity.project(body)
                connection.execute(
                    sa.text('update radar_ingest_runs set '
                            'summary_schema_version=:v, summary_countable=:c, '
                            'posts_seen=:a, posts_new=:b, mentions=:m, '
                            'buckets_written=:w where id=:id'),
                    {'v': version, 'c': countable,
                     'a': counters['posts_seen'], 'b': counters['posts_new'],
                     'm': counters['mentions'],
                     'w': counters['buckets_written'], 'id': run_id})
        check('all six columns exist, half projected, revision unstamped',
              set(PROJECTION_COLUMNS) <= columns()
              and stamped() == OBSERVATIONS)
        check('source data survived the partial backfill',
              envelopes() == source_before)
        half = projection()
        check('the half-written projection is NOT the clean one',
              half != clean, 'otherwise this step proves nothing')

        drop_projection_columns(columns() & set(PROJECTION_COLUMNS))
        upgrade(revision=PROJECTION)
        check('recovery then upgrade reproduces the clean projection',
              projection() == clean)
        check('recovery preserved every envelope',
              envelopes() == source_before)
        check('row count never moved',
              len(envelopes()) == len(FIXTURES))

        # --- the refusal path, on this engine ------------------------------
        print('\n5. the pre-DDL domain refusal, on MariaDB')
        downgrade(revision=OBSERVATIONS)
        with db.engine.begin() as connection:
            connection.execute(
                sa.text('insert into radar_ingest_runs '
                        '(id, started_at, status, summary_json) values '
                        '(:id, :started, :status, :body)'),
                {'id': '12-negative', 'started': BASE + dt.timedelta(hours=1),
                 'status': 'ok',
                 'body': json.dumps({'schema_version': 1,
                                     'summary': {'posts_seen': -4}})})
        # Alembic directly, not flask_migrate: its command wrapper logs the
        # error and calls sys.exit, which would end this script before the
        # refusal could be inspected.
        try:
            raw_upgrade(PROJECTION)
            check('the migration refuses an out-of-domain counter', False,
                  'it applied instead')
        except Exception as problem:                         # noqa: BLE001
            message = str(problem)
            check('the migration refuses an out-of-domain counter',
                  'outside the accepted domain' in message)
            check('the refusal names the row and the shape, not the value',
                  '12-negative' in message and 'out of range' in message
                  and '-4' not in message)
        check('the refusal added no column',
              not (set(PROJECTION_COLUMNS) & columns()),
              'the schema must be untouched, so a retry is clean')
        check('the refusal left the revision unstamped',
              stamped() == OBSERVATIONS)
        with db.engine.begin() as connection:
            connection.execute(sa.text(
                'delete from radar_ingest_runs where id = :id'),
                {'id': '12-negative'})
        upgrade(revision=PROJECTION)
        check('after the offending row is removed, the upgrade is clean',
              stamped() == PROJECTION and projection() == clean)

        # --- the application's own path, on this engine --------------------
        # The migration passing does not prove the code that runs afterwards
        # works here. MariaDB stores JSON as LONGTEXT, so the writer's envelope
        # round trip and the reader's scalar fold are both worth exercising
        # before a rollout rather than after one.
        print('\n6. the writer and reader themselves, on MariaDB')
        moment = dt.datetime(2019, 7, 10, 11, 30)
        run_id = activity.start_run(moment)
        activity.finish_run(run_id, moment + dt.timedelta(seconds=40),
                            summary={'posts_seen': 12, 'posts_new': 5,
                                     'mentions': 3, 'buckets_written': 2},
                            error_code=None)
        with db.engine.connect() as connection:
            stored = connection.execute(sa.text(
                'select summary_json, summary_schema_version, '
                'summary_countable, posts_seen from radar_ingest_runs '
                'where id = :id'), {'id': run_id}).one()
        body = stored[0] if isinstance(stored[0], dict) else json.loads(stored[0])
        check('finish_run stored a readable envelope',
              body['summary']['posts_seen'] == 12)
        check('finish_run stored the projection beside it',
              stored[1] == activity.SCHEMA_VERSION and stored[2] == 1
              and stored[3] == 12)

        day = activity.summary(moment, 1)['days'][-1]
        check('summary() reads the projection on MariaDB',
              day['posts_seen'] == 12 and day['counted_runs'] == 1,
              f'posts_seen={day["posts_seen"]} counted={day["counted_runs"]}')
        # The streaming read: yield_per needs a server-side cursor here too.
        statements = []
        listener = lambda c, cur, s, p, ctx, many: statements.append(s)  # noqa: E731
        sa.event.listen(db.engine, 'before_cursor_execute', listener)
        try:
            activity.summary(moment, 30)
        finally:
            sa.event.remove(db.engine, 'before_cursor_execute', listener)
        check('the read never selects summary_json on MariaDB',
              not any('summary_json' in s.lower() for s in statements),
              f'{len(statements)} statements')

    print(f'\n{"FAILURES: " + ", ".join(FAILURES) if FAILURES else "all checks passed"}')
    return 1 if FAILURES else 0


if __name__ == '__main__':
    raise SystemExit(main())

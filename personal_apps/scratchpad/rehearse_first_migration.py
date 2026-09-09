"""P2 item 6: recovering an interrupted FIRST migration, on MariaDB.

P1 rehearsed a failure inside `a7c31f0b52d4` -- stamp `d82f9afb5898`, some
projection columns present -- and its recovery is to drop the columns that are
actually there and upgrade again. That does not cover a failure inside
`d82f9afb5898` itself, which leaves a different state and needs different
handling, and assuming one recipe fixes both is how an operator drops something
they should not.

`d82f9afb5898.upgrade` performs four DDL statements, each auto-committing on
MariaDB:

    1. create_table  radar_ingest_runs
    2. create_index  ix_radar_ingest_runs_started
    3. create_table  radar_board_observations
    4. create_index  ix_radar_board_observations_observed

A process killed between any two leaves the revision UNSTAMPED at
`b3d9e1f5a274` with part of that list applied. This script builds each of those
three partial states and rehearses recovery from it.

    PYTHONPATH=. py -3.12 scratchpad/rehearse_first_migration.py

The recovery is INSPECTION-BASED and refuses to be a recipe:

  * It reads what is actually present rather than assuming.
  * It COUNTS ROWS in every partial table and refuses to drop a non-empty one.
    At a first deployment they cannot hold rows -- the deployed code has no
    model for them -- but a second attempt after a partial rollout could, and
    a blanket DROP would destroy recorded runs.
  * It never stamps a revision to skip work.

Same guards as the P1 harness: loopback only, never the real schema names,
MariaDB only.
"""
import datetime as dt
import os
import sys

sys.path.insert(0, '.')

import sqlalchemy as sa                                     # noqa: E402
from flask import Flask                                    # noqa: E402
from flask_migrate import Migrate, stamp, upgrade           # noqa: E402

from extensions import db                                   # noqa: E402
import models                                               # noqa: E402,F401

BASE_REVISION = 'b3d9e1f5a274'
OBSERVATIONS = 'd82f9afb5898'
PROJECTION = 'a7c31f0b52d4'

NEW_TABLES = ('radar_ingest_runs', 'radar_board_observations')

HOST = os.getenv('REHEARSAL_HOST', '127.0.0.1')
PORT = os.getenv('REHEARSAL_PORT', '3399')
USER = os.getenv('REHEARSAL_USER', 'root')
PASSWORD = os.getenv('REHEARSAL_PASSWORD', '')
SCHEMA = os.getenv('REHEARSAL_SCHEMA', 'radar_first_migration')

SERVER_URL = f'mysql+pymysql://{USER}:{PASSWORD}@{HOST}:{PORT}/'

# The four statements, in the order the migration issues them. Interrupting
# "after N" means the first N were committed.
STEPS = (
    ('table', 'radar_ingest_runs'),
    ('index', 'ix_radar_ingest_runs_started'),
    ('table', 'radar_board_observations'),
    ('index', 'ix_radar_board_observations_observed'),
)

FAILURES = []


def check(label, condition, detail=''):
    mark = 'PASS' if condition else 'FAIL'
    print(f'  {mark}  {label}' + (f' -- {detail}' if detail else ''))
    if not condition:
        FAILURES.append(label)


def make_app():
    application = Flask('radar-first-migration-rehearsal')
    application.config['SQLALCHEMY_DATABASE_URI'] = SERVER_URL + SCHEMA
    application.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(application)
    Migrate(application, db, directory='migrations')
    return application


def recreate_schema():
    if HOST not in ('127.0.0.1', 'localhost', '::1'):
        raise SystemExit(f'refusing to run against host {HOST!r}')
    if SCHEMA in ('personal_apps', 'coc_stats'):
        raise SystemExit(f'refusing to use schema {SCHEMA!r}')
    engine = sa.create_engine(SERVER_URL, isolation_level='AUTOCOMMIT')
    with engine.connect() as connection:
        version = connection.execute(sa.text('select version()')).scalar()
        if 'mariadb' not in version.lower():
            raise SystemExit(f'refusing to rehearse against {version!r}')
        connection.execute(sa.text(f'drop database if exists `{SCHEMA}`'))
        connection.execute(sa.text(
            f'create database `{SCHEMA}` character set utf8mb4'))
    engine.dispose()
    return version


def tables():
    with db.engine.connect() as connection:
        return {row[0] for row in connection.execute(sa.text('show tables'))}


def indexes(table):
    with db.engine.connect() as connection:
        try:
            rows = connection.execute(sa.text(f'show index from `{table}`'))
        except Exception:
            return set()
        return {row[2] for row in rows}


def stamped():
    with db.engine.connect() as connection:
        try:
            return connection.execute(
                sa.text('select version_num from alembic_version')).scalar()
        except Exception:
            return None


def build_partial(after):
    """Reproduce the state left by a kill after `after` of the four statements.

    Issued as the migration issues them, so the resulting shapes are the
    migration's own rather than an approximation.
    """
    ddl = {
        'radar_ingest_runs': """
            create table radar_ingest_runs (
                id varchar(36) not null,
                started_at datetime(6) not null,
                finished_at datetime(6) null,
                status varchar(8) not null,
                summary_json longtext null
                    check (json_valid(summary_json)),
                error_code varchar(48) null,
                primary key (id),
                constraint ck_radar_ingest_run_status
                    check (status in ('running','ok','error'))
            ) default charset=utf8mb4""",
        'ix_radar_ingest_runs_started':
            'create index ix_radar_ingest_runs_started '
            'on radar_ingest_runs (started_at)',
        'radar_board_observations': """
            create table radar_board_observations (
                id varchar(36) not null,
                slot_start datetime(6) not null,
                observed_at datetime(6) not null,
                schema_version int not null,
                producer_revision varchar(64) null,
                selections_json longtext not null
                    check (json_valid(selections_json)),
                payload_json longtext not null
                    check (json_valid(payload_json)),
                primary key (id),
                constraint uq_radar_board_observation_slot unique (slot_start)
            ) default charset=utf8mb4""",
        'ix_radar_board_observations_observed':
            'create index ix_radar_board_observations_observed '
            'on radar_board_observations (observed_at)',
    }
    with db.engine.begin() as connection:
        for _, name in STEPS[:after]:
            connection.execute(sa.text(ddl[name]))


def inspect():
    """What an operator must establish before touching anything.

    Deliberately returns facts rather than a decision: the point of the
    procedure is that the operator looks, and that the looking is recorded.
    """
    present = tables() & set(NEW_TABLES)
    report = {}
    for name in sorted(present):
        with db.engine.connect() as connection:
            rows = connection.execute(
                sa.text(f'select count(*) from `{name}`')).scalar()
        report[name] = {'rows': rows, 'indexes': indexes(name)}
    return {'stamp': stamped(), 'present': report,
            'absent': sorted(set(NEW_TABLES) - present)}


def recover(report):
    """Drop only what this failed, unstamped revision created, and only when it
    holds nothing.

    Refuses on any row. A first deployment cannot have produced one -- the
    deployed code declares no model for these tables -- so a row here means the
    assumption behind the whole procedure is wrong, and the operator has to
    stop rather than let a script decide.
    """
    if report['stamp'] != BASE_REVISION:
        raise SystemExit(
            f'refusing: this procedure is for an UNSTAMPED first migration, '
            f'and the stamp is {report["stamp"]!r}. A stamp of '
            f'{OBSERVATIONS!r} means the first migration completed and the '
            f'projection-column procedure applies instead.')
    populated = {name: facts['rows'] for name, facts in report['present'].items()
                 if facts['rows']}
    if populated:
        raise SystemExit(
            f'refusing to drop tables that hold records: {populated}. Back '
            f'them up and obtain explicit approval; a partial first migration '
            f'should not contain rows, so this state needs diagnosis rather '
            f'than a recipe.')
    with db.engine.begin() as connection:
        # Reverse creation order: observations first, as the downgrade does.
        for name in reversed(NEW_TABLES):
            if name in report['present']:
                connection.execute(sa.text(f'drop table `{name}`'))
    return sorted(report['present'])


def main():
    version = recreate_schema()
    print(f'engine: {version}  schema: {SCHEMA}  port: {PORT}')
    print('rehearsing recovery from an interrupted FIRST migration '
          f'({OBSERVATIONS})\n')

    application = make_app()
    with application.app_context():
        stamp(revision=BASE_REVISION)
        upgrade(revision=PROJECTION)
        with db.engine.connect() as connection:
            complete = {name: tuple(connection.execute(
                sa.text(f'show create table `{name}`')).one())[1]
                for name in NEW_TABLES}
        check('a clean run of both revisions is the baseline',
              stamped() == PROJECTION and set(NEW_TABLES) <= tables())

        for after in (1, 2, 3):
            what = STEPS[after - 1][1]
            print(f'\ninterrupted after statement {after} of 4 ({what})')
            recreate_schema()
            db.engine.dispose()
            stamp(revision=BASE_REVISION)
            build_partial(after)

            report = inspect()
            check('the revision is unstamped at the base',
                  report['stamp'] == BASE_REVISION, report['stamp'])
            check('inspection sees exactly what was created',
                  len(report['present']) == (1 if after < 3 else 2),
                  f'present={sorted(report["present"])} '
                  f'absent={report["absent"]}')
            if after == 1:
                check('the index is correctly seen as missing',
                      'ix_radar_ingest_runs_started'
                      not in report['present']['radar_ingest_runs']['indexes'])
            if after == 2:
                check('the index is correctly seen as present',
                      'ix_radar_ingest_runs_started'
                      in report['present']['radar_ingest_runs']['indexes'])

            # A blind re-run is what an operator tries first. It must fail
            # rather than silently produce a half-built schema.
            try:
                upgrade(revision=PROJECTION)
                check('a blind re-run of the upgrade fails', False,
                      'it succeeded, which the runbook does not expect')
            except Exception as problem:                     # noqa: BLE001
                check('a blind re-run of the upgrade fails loudly',
                      'already exists' in str(problem).lower(),
                      type(problem).__name__)

            dropped = recover(inspect())
            check('recovery dropped only the partial tables',
                  not (tables() & set(NEW_TABLES)), f'dropped {dropped}')

            upgrade(revision=PROJECTION)
            check('recovery then upgrade completes both revisions',
                  stamped() == PROJECTION)
            with db.engine.connect() as connection:
                rebuilt = {name: tuple(connection.execute(
                    sa.text(f'show create table `{name}`')).one())[1]
                    for name in NEW_TABLES}
            check('the rebuilt schema is identical to a clean run',
                  rebuilt == complete,
                  'byte-for-byte on both SHOW CREATE TABLE')

        # The guard that matters most: a partial table holding records.
        print('\na partial table that holds records')
        recreate_schema()
        db.engine.dispose()
        stamp(revision=BASE_REVISION)
        build_partial(2)
        with db.engine.begin() as connection:
            connection.execute(
                sa.text('insert into radar_ingest_runs '
                        '(id, started_at, status) values (:i, :s, :st)'),
                {'i': 'a-real-run', 's': dt.datetime(2019, 8, 1, 9, 0),
                 'st': 'ok'})
        try:
            recover(inspect())
            check('recovery refuses to drop a table holding records', False,
                  'it dropped it')
        except SystemExit as refusal:
            check('recovery refuses to drop a table holding records',
                  'hold records' in str(refusal))
            check('the refusal names the count, so the operator can judge',
                  "'radar_ingest_runs': 1" in str(refusal), str(refusal)[:80])
        check('the row is still there after the refusal',
              tables() & {'radar_ingest_runs'} == {'radar_ingest_runs'})

        # And the wrong-procedure guard.
        print('\nthe wrong procedure, refused')
        recreate_schema()
        db.engine.dispose()
        stamp(revision=BASE_REVISION)
        upgrade(revision=OBSERVATIONS)
        try:
            recover(inspect())
            check('recovery refuses when the first migration completed', False,
                  'it proceeded')
        except SystemExit as refusal:
            check('recovery refuses when the first migration completed',
                  'projection-column procedure applies instead'
                  in str(refusal))

    print(f'\n{"FAILURES: " + ", ".join(FAILURES) if FAILURES else "all checks passed"}')
    return 1 if FAILURES else 0


if __name__ == '__main__':
    raise SystemExit(main())

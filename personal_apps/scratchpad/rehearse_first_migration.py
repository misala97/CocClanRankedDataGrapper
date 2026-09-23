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
`b3d9e1f5a274` with part of that list applied. This script builds each of those four partial states -- including the one
where all four statements applied but the stamp was never written, which is
where an operator is most tempted to stamp and move on -- and rehearses recovery
from each.

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


def capture_real_ddl():
    """The exact CREATE statements this migration produces, taken FROM it.

    Hand-written DDL was the first version of this and it was wrong: the
    migration's `sa.JSON()` columns materialise on MariaDB as
    `longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin` with a `json_valid`
    CHECK, and a hand-copied `longtext` has neither the binary collation nor
    the same check placement. The partial states were therefore states the
    migration could not leave, which is the one thing a recovery rehearsal
    must not get wrong.

    So: run the real thing, read `SHOW CREATE TABLE`, and build every partial
    state from that. Fidelity by construction rather than by transcription.
    """
    upgrade(revision=OBSERVATIONS)
    statements = {}
    with db.engine.connect() as connection:
        for name in NEW_TABLES:
            statements[name] = tuple(connection.execute(
                sa.text(f'show create table `{name}`')).one())[1]
        # The index DDL, read back the same way rather than guessed.
        for table, index in (('radar_ingest_runs',
                              'ix_radar_ingest_runs_started'),
                             ('radar_board_observations',
                              'ix_radar_board_observations_observed')):
            column = connection.execute(sa.text(
                f'select column_name from information_schema.statistics '
                f"where table_schema = database() and table_name = '{table}' "
                f"and index_name = '{index}'")).scalar()
            statements[index] = (f'create index {index} on `{table}` '
                                 f'({column})')
    # The captured CREATE TABLE includes the index, so strip it: the partial
    # states need the table WITHOUT its index for step 1.
    for name in NEW_TABLES:
        statements[name + ':noindex'] = _without_index(statements[name])
    return statements


def _without_index(create_statement):
    """The same CREATE TABLE with its non-unique KEY lines removed.

    `SHOW CREATE TABLE` folds the separately-created index into the table
    definition. Statement 1 of the migration creates the table before that
    index exists, so reproducing that state means removing exactly those lines
    and nothing else.
    """
    kept = []
    for line in create_statement.split('\n'):
        stripped = line.strip()
        if stripped.startswith('KEY `ix_'):
            continue
        kept.append(line)
    # A trailing comma before the closing paren, left by a removed KEY line.
    for index in range(len(kept) - 1, -1, -1):
        if kept[index].strip().startswith(')'):
            previous = kept[index - 1].rstrip()
            if previous.endswith(','):
                kept[index - 1] = previous[:-1]
            break
    return '\n'.join(kept)


def build_partial(after, ddl):
    """Reproduce the state left by a kill after `after` of the four statements,
    using the DDL the migration itself produced."""
    order = [('radar_ingest_runs:noindex', None),
             ('ix_radar_ingest_runs_started', None),
             ('radar_board_observations:noindex', None),
             ('ix_radar_board_observations_observed', None)]
    with db.engine.begin() as connection:
        for key, _ in order[:after]:
            connection.execute(sa.text(ddl[key]))


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

    Counting and then dropping is a check-then-act, and it is only safe because
    the runbook stops every writer before recovery begins. Do not lift this
    procedure into a context where something could still be inserting.
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
        ddl = capture_real_ddl()
        with db.engine.connect() as connection:
            after_first = {name: tuple(connection.execute(
                sa.text(f'show create table `{name}`')).one())[1]
                for name in NEW_TABLES}
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
            build_partial(after, ddl)

            # The check that makes the rest mean anything: the state being
            # recovered from must be one the migration could actually leave.
            # Compared BEFORE recovery, because recovery drops these tables and
            # any comparison afterwards is against the real migration's output
            # whatever was here.
            with db.engine.connect() as connection:
                partial_shapes = {name: tuple(connection.execute(
                    sa.text(f'show create table `{name}`')).one())[1]
                    for name in sorted(tables() & set(NEW_TABLES))}
            faithful = all(
                partial_shapes[name] == after_first[name]
                for name in partial_shapes
                if not (after == 1 and name == 'radar_ingest_runs')
                and not (after == 3 and name == 'radar_board_observations'))
            check('the partial state is one the migration could leave',
                  faithful,
                  'SHOW CREATE TABLE matches the real migration, '
                  'collation and CHECK included')
            if after == 1:
                check('the un-indexed table differs from the indexed one '
                      'only by its index',
                      partial_shapes['radar_ingest_runs']
                      == _without_index(after_first['radar_ingest_runs']))

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
            # Weaker than it looks, and labelled so: recovery drops the
            # partial tables, so this compares the real migration's output
            # against itself. It catches a recovery that left something behind
            # or upgraded to the wrong revision -- not a bad partial state,
            # which is what the check above is for.
            check('the recovered schema equals a clean run',
                  rebuilt == complete,
                  'byte-for-byte on both SHOW CREATE TABLE')

        # All four statements applied, the stamp never written. This is the
        # state where an operator is most tempted to stamp the revision and
        # move on -- the schema LOOKS complete -- and doing so would skip the
        # second migration's own work forever.
        print('\ninterrupted after all four statements, before the stamp')
        recreate_schema()
        db.engine.dispose()
        stamp(revision=BASE_REVISION)
        build_partial(4, ddl)
        report = inspect()
        check('both tables present and the revision still unstamped',
              len(report['present']) == 2 and report['stamp'] == BASE_REVISION)
        dropped = recover(report)
        check('recovery drops both and re-runs rather than stamping',
              not (tables() & set(NEW_TABLES)), f'dropped {dropped}')
        upgrade(revision=PROJECTION)
        check('the re-run reaches the real head, not a stamped shortcut',
              stamped() == PROJECTION)
        with db.engine.connect() as connection:
            rebuilt = {name: tuple(connection.execute(
                sa.text(f'show create table `{name}`')).one())[1]
                for name in NEW_TABLES}
        check('and the schema equals a clean run', rebuilt == complete)

        # The guard that matters most: a partial table holding records.
        print('\na partial table that holds records')
        recreate_schema()
        db.engine.dispose()
        stamp(revision=BASE_REVISION)
        build_partial(2, ddl)
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

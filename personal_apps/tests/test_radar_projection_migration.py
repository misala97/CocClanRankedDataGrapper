"""The projection migration, against a table that is not empty.

An empty-table round trip proves the DDL parses. It does not prove the backfill
projects anything, that envelopes survive, or that a downgrade leaves the
record intact -- and those are the parts a rollout depends on. Every test here
seeds real rows first: valid, incomplete, malformed, off-version, running and
error.

These tests run alembic in-process against the disposable database and are slow
by nature. They are the only place the migration is exercised end to end.
"""
import datetime as dt
import json
import logging

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from app import app as flask_app
from extensions import db
from features.radar import activity

REVISION = 'a7c31f0b52d4'
PREVIOUS = 'd82f9afb5898'
DISPOSABLE = 'personal_apps_radar_wt'

# Before Radar existed. The suite's other modules blanket-delete this range.
BASE = dt.datetime(2019, 7, 3, 9, 0)

NEW_COLUMNS = ('summary_schema_version', 'summary_countable', 'posts_seen',
               'posts_new', 'mentions', 'buckets_written')

# One of each shape a stored row can have, with the id fixed so assertions can
# name them. The ids also exercise the backfill's keyset paging order.
FIXTURES = [
    ('00-valid', 'ok', {'schema_version': 1,
                        'summary': {'posts_seen': 11, 'posts_new': 4,
                                    'mentions': 2, 'buckets_written': 1}}),
    ('01-valid-zero', 'ok', {'schema_version': 1,
                             'summary': {'posts_seen': 0, 'posts_new': 0,
                                         'mentions': 0, 'buckets_written': 0}}),
    ('02-incomplete-counters', 'ok', {'schema_version': 1,
                                      'summary': {'posts_seen': 7}}),
    ('03-null-counter', 'ok', {'schema_version': 1,
                               'summary': {'posts_seen': None,
                                           'posts_new': 1}}),
    ('04-off-version', 'ok', {'schema_version': 99,
                              'summary': {'posts_seen': 5}}),
    ('05-unversioned', 'ok', {'summary': {'posts_seen': 5}}),
    ('06-malformed-summary', 'ok', {'schema_version': 1, 'summary': 'nope'}),
    ('07-not-a-mapping', 'ok', 'not an envelope at all'),
    ('08-no-envelope', 'ok', None),
    ('09-running', 'running', None),
    ('10-error', 'error', None),
]


def _alembic() -> Config:
    config = Config('migrations/alembic.ini')
    config.set_main_option('script_location', 'migrations')
    config.attributes['configure_logger'] = False
    return config


@pytest.fixture
def disposable():
    """Refuses to touch anything but the disposable clone. A migration test
    that ran against the shared dev database would be a very expensive way to
    learn that the guard was missing."""
    with flask_app.app_context():
        if db.engine.url.database != DISPOSABLE:
            pytest.skip(f'not the disposable database: {db.engine.url.database}')
        _clear()
        yield
        # Back to the head the branch expects, whatever the test did.
        _at_revision(REVISION)
        _clear()


def _clear():
    with db.engine.begin() as connection:
        if _columns(connection):
            connection.execute(sa.text(
                'delete from radar_ingest_runs where started_at < :cutoff'),
                {'cutoff': dt.datetime(2020, 1, 1)})


def _columns(connection) -> set:
    rows = connection.execute(sa.text('show columns from radar_ingest_runs'))
    return {row[0] for row in rows}


def _at_revision(revision):
    """Alembic's in-process run calls fileConfig, which disables every existing
    logger. F1 hit this: three unrelated caplog assertions in the daemon suite
    started failing. Restore what was on before."""
    disabled = {name: logging.getLogger(name).disabled
                for name in list(logging.root.manager.loggerDict)}
    try:
        command.upgrade(_alembic(), revision)
    finally:
        for name, was in disabled.items():
            logging.getLogger(name).disabled = was


def _downgrade(revision):
    disabled = {name: logging.getLogger(name).disabled
                for name in list(logging.root.manager.loggerDict)}
    try:
        command.downgrade(_alembic(), revision)
    finally:
        for name, was in disabled.items():
            logging.getLogger(name).disabled = was


def _seed_envelopes_only():
    """Rows as the PREVIOUS revision would have written them: envelope, status
    and timestamps, with no projection. This is what the backfill must read."""
    with db.engine.begin() as connection:
        for index, (name, status, envelope) in enumerate(FIXTURES):
            connection.execute(
                sa.text('insert into radar_ingest_runs '
                        '(id, started_at, finished_at, status, summary_json, '
                        ' error_code) values '
                        '(:id, :started, :finished, :status, :body, :code)'),
                {'id': name, 'started': BASE + dt.timedelta(minutes=index),
                 'finished': BASE + dt.timedelta(minutes=index, seconds=30),
                 'status': status,
                 'body': None if envelope is None else sa.JSON().bind_processor(
                     db.engine.dialect)(envelope),
                 'code': 'ingest_failed' if status == 'error' else None})


def _fingerprint(connection):
    """Every table's column shape, so a migration that touched something else
    is visible rather than assumed absent."""
    tables = connection.execute(sa.text('show tables')).scalars().all()
    return {table: tuple(connection.execute(
        sa.text(f'show columns from `{table}`')).fetchall())
        for table in tables}


def _decoded(stored):
    """What the row actually holds. MySQL returns a JSON column as text under
    an untyped SELECT; `null` in the column and SQL NULL both arrive as
    something that must not be confused with a mapping."""
    if stored is None:
        return None
    if isinstance(stored, (str, bytes)):
        return json.loads(stored)
    return stored


def _envelopes(connection):
    rows = connection.execute(sa.text(
        'select id, status, summary_json, started_at, finished_at, error_code '
        'from radar_ingest_runs where started_at < :cutoff order by id'),
        {'cutoff': dt.datetime(2020, 1, 1)}).fetchall()
    return [tuple(row) for row in rows]


def test_the_backfill_projects_exactly_what_the_writer_would_have(disposable):
    """The claim the whole migration rests on: a row backfilled from its
    envelope is indistinguishable from one the new writer produced."""
    _downgrade(PREVIOUS)
    _seed_envelopes_only()
    _at_revision(REVISION)

    with db.engine.connect() as connection:
        rows = connection.execute(sa.text(
            'select id, summary_json, summary_schema_version, '
            'summary_countable, posts_seen, posts_new, mentions, '
            'buckets_written from radar_ingest_runs '
            'where started_at < :cutoff order by id'),
            {'cutoff': dt.datetime(2020, 1, 1)}).fetchall()

    assert len(rows) == len(FIXTURES), 'the backfill lost or added rows'
    for row in rows:
        # A raw textual SELECT carries no type, so the driver hands the JSON
        # back as a string. Decode before projecting -- comparing a str against
        # the projection would make every row look uncountable and the test
        # would pass for the wrong reason.
        version, countable, counters = activity.project(
            _decoded(row.summary_json))
        assert row.summary_schema_version == version, row.id
        assert bool(row.summary_countable) == countable, row.id
        for name in activity.COUNTERS:
            assert getattr(row, name) == counters[name], f'{row.id}.{name}'


def test_the_backfill_marks_each_shape_as_expected(disposable):
    """Named, so a change of behaviour reads as a change of behaviour rather
    than as a comparison against a function that changed with it."""
    _downgrade(PREVIOUS)
    _seed_envelopes_only()
    _at_revision(REVISION)

    with db.engine.connect() as connection:
        rows = {row.id: row for row in connection.execute(sa.text(
            'select id, summary_countable, summary_schema_version, posts_seen,'
            ' posts_new from radar_ingest_runs where started_at < :cutoff'),
            {'cutoff': dt.datetime(2020, 1, 1)}).fetchall()}

    assert bool(rows['00-valid'].summary_countable) is True
    assert rows['00-valid'].posts_seen == 11
    assert rows['01-valid-zero'].posts_seen == 0, 'a measured zero became null'
    # Countable, but one counter absent: the row still participates and the
    # day's other counters are unaffected.
    assert bool(rows['02-incomplete-counters'].summary_countable) is True
    assert rows['02-incomplete-counters'].posts_new is None
    assert rows['03-null-counter'].posts_seen is None
    assert rows['03-null-counter'].posts_new == 1
    # Structurally valid but a version this reader will not add to its own.
    assert bool(rows['04-off-version'].summary_countable) is True
    assert rows['04-off-version'].summary_schema_version == 99
    # Never countable, whatever else is true of them.
    for name in ('05-unversioned', '06-malformed-summary', '07-not-a-mapping',
                 '08-no-envelope', '09-running', '10-error'):
        assert bool(rows[name].summary_countable) is False, name
        assert rows[name].posts_seen is None, name


def test_upgrade_downgrade_upgrade_preserves_every_envelope(disposable):
    """The round trip, with the envelopes and the rest of the schema checked
    either side rather than assumed untouched."""
    _downgrade(PREVIOUS)
    _seed_envelopes_only()

    with db.engine.connect() as connection:
        before_shape = _fingerprint(connection)
        before_rows = _envelopes(connection)
        assert not _columns(connection) & set(NEW_COLUMNS)

    _at_revision(REVISION)
    with db.engine.connect() as connection:
        assert set(NEW_COLUMNS) <= _columns(connection)
        assert _envelopes(connection) == before_rows, 'the upgrade changed a row'

    _downgrade(PREVIOUS)
    with db.engine.connect() as connection:
        after_shape = _fingerprint(connection)
        assert not _columns(connection) & set(NEW_COLUMNS), (
            'the downgrade left a projection column behind')
        assert _envelopes(connection) == before_rows, (
            'the downgrade altered the record it was supposed to preserve')
        assert after_shape == before_shape, (
            'the downgrade is not the exact inverse of the upgrade')

    _at_revision(REVISION)
    with db.engine.connect() as connection:
        assert _envelopes(connection) == before_rows
        # And the projection is rebuilt, which is why losing it on downgrade is
        # a cost rather than a loss.
        rebuilt = connection.execute(sa.text(
            'select posts_seen from radar_ingest_runs where id = :id'),
            {'id': '00-valid'}).scalar()
        assert rebuilt == 11, 'the second upgrade did not rebuild the projection'


def test_unrelated_tables_and_rows_are_untouched(disposable):
    """The disposable database is a full clone, so there is real unrelated data
    to leave alone."""
    with db.engine.connect() as connection:
        counts_before = {
            table: connection.execute(
                sa.text(f'select count(*) from `{table}`')).scalar()
            for table in ('radar_buckets', 'radar_watch', 'app_user')}

    _downgrade(PREVIOUS)
    _at_revision(REVISION)

    with db.engine.connect() as connection:
        counts_after = {
            table: connection.execute(
                sa.text(f'select count(*) from `{table}`')).scalar()
            for table in counts_before}
    assert counts_after == counts_before


def test_the_backfill_refuses_a_counter_outside_the_accepted_domain(
        disposable):
    """Reported, not repaired, and nothing written before the refusal.

    Turning a negative into a null would rewrite what history says happened;
    that is a compatibility decision for the schema owner. MySQL commits
    implicitly on DDL, so the scan has to precede the writes rather than rely
    on a rollback that would not come.
    """
    _downgrade(PREVIOUS)
    _seed_envelopes_only()
    with db.engine.begin() as connection:
        connection.execute(
            sa.text('insert into radar_ingest_runs '
                    '(id, started_at, status, summary_json) values '
                    '(:id, :started, :status, :body)'),
            {'id': '11-negative', 'started': BASE + dt.timedelta(hours=1),
             'status': 'ok',
             'body': sa.JSON().bind_processor(db.engine.dialect)(
                 {'schema_version': 1, 'summary': {'posts_seen': -4}})})

    with pytest.raises(Exception) as raised:
        _at_revision(REVISION)
    message = str(raised.value)
    assert 'outside the accepted domain' in message
    assert '11-negative' in message, 'the report did not name the row'
    assert 'out of range' in message, 'the report did not name the shape'
    assert '-4' not in message, 'the report leaked a stored value'

    # The schema is untouched. This is the property the error message
    # promises -- "No column has been added" -- and the reason a fixed database
    # can simply be upgraded again rather than needing the columns dropped
    # first. Asserted unconditionally: guarding it on the columns existing
    # would make it pass under the very ordering it exists to rule out.
    with db.engine.connect() as connection:
        assert not _columns(connection) & set(NEW_COLUMNS), (
            'the refused migration added its columns before refusing')

    with db.engine.begin() as connection:
        connection.execute(sa.text(
            'delete from radar_ingest_runs where id = :id'),
            {'id': '11-negative'})

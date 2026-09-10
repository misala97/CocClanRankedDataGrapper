"""The board-result tables' migration, end to end on a real MySQL database.

An in-memory round trip proves the DDL parses. It does not prove that the
columns can hold what the store will put in them, and that is the part this
migration is delicate about: `key_json` is TEXT because a legal selection of 37
long source names is about 4,000 characters, and a column too narrow for it
would truncate silently the moment anything ran under a permissive `sql_mode`.
A truncated key still has a name -- the hash it was stored under -- and no
longer means what that name says. So the round trip is exercised here at the
real width, against both `sql_mode` settings, with a payload that contains
every byte value including NUL.

These tests run alembic in-process against the disposable database and are slow
by nature. They refuse to run anywhere else, and they leave the database at the
revision they were asked to prove.
"""
import logging

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app import app as flask_app
from extensions import db
from features.radar import board_keys

REVISION = 'b7e3f9c1a2d4'
PREVIOUS = 'a7c31f0b52d4'
DISPOSABLE = 'personal_apps_radar_perf3'

NEW_TABLES = {'radar_board_namespaces', 'radar_board_results'}
NEW_INDEXES = {'ix_radar_board_results_queue',
               'ix_radar_board_results_warm',
               'ix_radar_board_results_demand'}

# Every byte value, so a column or a driver that decided this was text shows
# itself rather than passing on the well-behaved half of the range. 12 KB is
# the top of the measured payload band (6-13 KB compressed).
BLOB = bytes(range(256)) * 48


def _alembic() -> Config:
    config = Config('migrations/alembic.ini')
    config.set_main_option('script_location', 'migrations')
    config.attributes['configure_logger'] = False
    return config


def _at_revision(revision):
    """Alembic's in-process run calls fileConfig, which disables every existing
    logger. Restore what was on before, or unrelated caplog assertions
    elsewhere in the suite start failing for reasons no one can find."""
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


@pytest.fixture
def disposable():
    """Refuses to touch anything but the disposable clone, and puts the
    revision back whatever the test did to it."""
    with flask_app.app_context():
        if db.engine.url.database != DISPOSABLE:
            pytest.skip(f'not the disposable database: {db.engine.url.database}')
        _at_revision(REVISION)
        yield
        _at_revision(REVISION)


def _tables(connection):
    return {row[0] for row in connection.execute(sa.text('show tables'))}


def _indexes(connection, table):
    rows = connection.execute(sa.text(f'show index from `{table}`'))
    return {row._mapping['Key_name'] for row in rows}


def _columns(connection, table):
    rows = connection.execute(sa.text(f'show columns from `{table}`'))
    return {row[0]: row[1] for row in rows}


def _fingerprint(connection):
    """Every table's column shape, so a migration that touched something it did
    not create is visible rather than assumed absent."""
    return {table: tuple(connection.execute(
        sa.text(f'show columns from `{table}`')).fetchall())
        for table in _tables(connection)}


def _long_key():
    """A legal key at the width the column has to survive: 37 sources of
    long-but-legal names, canonicalised by the real key writer."""
    from features.radar.routes.api import Query

    names = ['reddit:' + ('x' * 100) + str(index) for index in range(37)]
    query = Query(sources=names, segments=[], window=12, limit=50,
                  min_venues=1, market='us', sort=None, direction='desc')
    return board_keys.canonical(query)


def test_the_upgrade_creates_exactly_the_two_tables_and_three_indexes(
        disposable):
    _downgrade(PREVIOUS)
    with db.engine.connect() as connection:
        before = _fingerprint(connection)
    assert not (NEW_TABLES & set(before)), 'the downgrade left a table behind'

    _at_revision(REVISION)
    with db.engine.connect() as connection:
        after = _fingerprint(connection)
        indexes = _indexes(connection, 'radar_board_results')
        results = _columns(connection, 'radar_board_results')
        namespaces = _columns(connection, 'radar_board_namespaces')

    assert set(after) - set(before) == NEW_TABLES
    assert {table: shape for table, shape in after.items()
            if table not in NEW_TABLES} == before, (
        'the upgrade altered a table it did not create')
    assert NEW_INDEXES <= indexes
    # The exact widths the store depends on, named rather than assumed: TEXT
    # for the key, MEDIUMBLOB for the payload, 32 characters for the token.
    assert results['key_json'] == 'text'
    assert results['payload'] == 'mediumblob'
    assert results['lease_token'] == 'varchar(32)'
    assert results['namespace'] == 'varchar(64)'
    assert namespaces['namespace'] == 'varchar(64)'


def test_the_downgrade_removes_exactly_them_and_leaves_the_archive_alone(
        disposable):
    """The observations table is the nearest neighbour by name and the one a
    careless DROP would take with it."""
    with db.engine.connect() as connection:
        archive_before = connection.execute(sa.text(
            'select count(*) from radar_board_observations')).scalar()
        before = _fingerprint(connection)
    assert NEW_TABLES <= set(before)

    _downgrade(PREVIOUS)

    with db.engine.connect() as connection:
        after = _fingerprint(connection)
        archive_after = connection.execute(sa.text(
            'select count(*) from radar_board_observations')).scalar()
    assert set(before) - set(after) == NEW_TABLES
    assert not (set(after) - set(before)), 'the downgrade created something'
    assert after == {table: shape for table, shape in before.items()
                     if table not in NEW_TABLES}
    assert archive_after == archive_before


def test_a_second_upgrade_after_a_downgrade_is_clean(disposable):
    """MySQL commits DDL as it goes, so a migration that is not its own inverse
    strands a half-built table that neither direction will touch again."""
    with db.engine.connect() as connection:
        first = _fingerprint(connection)

    _downgrade(PREVIOUS)
    _at_revision(REVISION)

    with db.engine.connect() as connection:
        second = _fingerprint(connection)
        indexes = _indexes(connection, 'radar_board_results')
    assert second == first
    assert NEW_INDEXES <= indexes


def test_the_revision_chain_still_has_one_head():
    """Two heads is a migration that silently never runs on the target."""
    heads = ScriptDirectory.from_config(_alembic()).get_heads()
    assert list(heads) == [REVISION], f'heads: {heads}'


def test_the_new_revision_follows_the_projection(disposable):
    script = ScriptDirectory.from_config(_alembic())
    assert script.get_revision(REVISION).down_revision == PREVIOUS
    with db.engine.connect() as connection:
        stamped = connection.execute(
            sa.text('select version_num from alembic_version')).scalar()
    assert stamped == REVISION


@pytest.mark.parametrize('sql_mode', ['', None],
                         ids=['permissive', 'strict-default'])
def test_a_four_thousand_character_key_and_a_twelve_kilobyte_blob_round_trip(
        disposable, sql_mode):
    """The claim TEXT is here for. Under `sql_mode=''` a too-narrow column
    truncates and warns instead of failing, which is how a corrupted key would
    reach production without anything raising."""
    key_hash, key_json = _long_key()
    assert len(key_json) > 3500, f'the fixture key is only {len(key_json)}'
    assert board_keys.round_trips(key_hash, key_json)

    with db.engine.begin() as connection:
        if sql_mode is not None:
            connection.execute(sa.text('set session sql_mode = :mode'),
                               {'mode': sql_mode})
        connection.execute(sa.text(
            'insert into radar_board_results '
            '(namespace, key_hash, key_json, payload_version, queue_state, '
            ' warm, payload, payload_bytes, requested_at, request_count, '
            ' attempts) values '
            '(:ns, :k, :j, 1, :state, 0, :blob, :n, :now, 1, 0)'
        ).bindparams(sa.bindparam('blob', type_=sa.LargeBinary)),
            {'ns': 'roundtrip-' + (sql_mode or 'default'), 'k': key_hash,
             'j': key_json, 'state': 'idle', 'blob': BLOB, 'n': len(BLOB),
             'now': sa.func.now(6)})

    try:
        with db.engine.connect() as connection:
            stored = connection.execute(sa.text(
                'select key_json, payload, payload_bytes '
                'from radar_board_results where key_hash = :k'),
                {'k': key_hash}).one()
        assert stored.key_json == key_json, (
            f'stored {len(stored.key_json)} of {len(key_json)} characters')
        assert board_keys.round_trips(key_hash, stored.key_json), (
            'the stored key no longer hashes to the name it is stored under')
        assert stored.payload == BLOB
        assert stored.payload_bytes == len(BLOB)
    finally:
        with db.engine.begin() as connection:
            connection.execute(sa.text(
                'delete from radar_board_results where key_hash = :k'),
                {'k': key_hash})


def _ddl(direction, revision):
    """The DDL statements one direction actually issues on this engine."""
    seen = []

    def record(connection, cursor, statement, parameters, context, many):
        head = statement.lstrip().split('(')[0].upper()
        if head.startswith(('CREATE TABLE', 'CREATE INDEX', 'DROP TABLE',
                            'DROP INDEX', 'ALTER TABLE')):
            seen.append(' '.join(statement.split())[:120])

    sa.event.listen(db.engine, 'before_cursor_execute', record)
    try:
        direction(revision)
    finally:
        sa.event.remove(db.engine, 'before_cursor_execute', record)
    return seen


def test_one_create_table_per_table_and_no_alter_in_either_direction(
        disposable):
    """MySQL and MariaDB commit each DDL statement on its own, so a direction
    that needs several statements per table can be interrupted into a state
    neither direction will fix. One CREATE per table, one DROP per table, and
    no ALTER at all."""
    down = _ddl(_downgrade, PREVIOUS)
    assert [s for s in down if s.startswith('DROP TABLE')] == down, down
    assert len(down) == 2
    # Results first: it is the table a reader addresses, and the namespaces it
    # belongs to outlive it by one statement rather than the other way round.
    assert 'radar_board_results' in down[0]
    assert 'radar_board_namespaces' in down[1]

    up = _ddl(_at_revision, REVISION)
    creates = [s for s in up if s.startswith('CREATE TABLE')]
    indexes = [s for s in up if s.startswith('CREATE INDEX')]
    assert len(creates) == 2, up
    assert len(indexes) == 3, up
    assert len(up) == 5, 'the upgrade issued DDL beyond its own five statements'

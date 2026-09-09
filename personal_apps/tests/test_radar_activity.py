"""What a recorded ingest run is allowed to claim.

The point of this table is honesty about operations, so most of these tests
are about what must NOT appear in it: a failed cycle must not leave zeros that
read like a quiet minute, a finished run must not have its totals rewritten,
and a recorder that cannot reach the database must not take ingest down with
it. Counting correctly matters less here than never counting something that
was not measured.

Every row these tests write is owned by them -- ids are collected as they are
created and deleted afterwards -- because the suite runs against a database
that holds real recorded runs alongside them.

`_reload` rolls back before reading. InnoDB's REPEATABLE READ would otherwise
serve this session the snapshot it opened BEFORE the recorder's own
transaction committed, and every assertion here is about what another
transaction wrote.
"""
import contextlib
import datetime as dt
import uuid

import pytest
import sqlalchemy as sa

from app import app as flask_app
from extensions import db
from features.radar import activity
from models import RadarBoardObservation, RadarIngestRun

# The revision before radar_ingest_runs and radar_board_observations existed.
# Named, so this file keeps testing the same thing however many revisions are
# later stacked above d82f9afb5898.
BEFORE_THESE_TABLES = 'b3d9e1f5a274'


@pytest.fixture()
def app_context():
    with flask_app.app_context():
        yield


@pytest.fixture()
def owned_runs(app_context):
    """Ids this test created, deleted afterwards and nothing else."""
    ids = []
    yield ids
    db.session.rollback()
    if ids:
        RadarIngestRun.query.filter(RadarIngestRun.id.in_(ids)).delete(
            synchronize_session=False)
        db.session.commit()


def _reload(run_id):
    db.session.rollback()
    return db.session.get(RadarIngestRun, run_id)


def _summary(**over):
    """The shape ingest.run_cycle returns -- its keys, and its vocabulary.

    `per_source` is a source-to-health map and not a count: the value is 'ok',
    'missing' or 'truncated', which is exactly the kind of field a reader could
    mistake for a number and sum. There is deliberately no 'status' key; that
    one belongs to tick's error return, which is never stored.
    """
    base = {'posts_seen': 12, 'posts_new': 4, 'mentions': 7,
            'buckets_written': 3, 'per_source': {'bluesky': 'ok'},
            'aggregate_status': {'bluesky': 'ok'}, 'catchup_depth': {},
            'intake_reasons': {'bluesky': {'no_ticker': 8, 'low_confidence': 3}}}
    base.update(over)
    return base


def test_the_fixture_matches_what_ingest_actually_returns(app_context):
    """Pins the fixture above to the real producer, by calling it.

    Without this the module could agree with itself about an envelope
    production never writes -- which it did, until a review caught a 'status'
    key run_cycle has never returned and a `per_source` value typed as a count
    when it is a health string. A cycle with no fetchers stores nothing.
    """
    from features.radar import ingest

    real = ingest.run_cycle(dt.datetime(2019, 6, 1, 12), {})
    assert set(real) == set(_summary())


def _broken_session(*args, **kwargs):
    raise sa.exc.OperationalError('select 1', {}, Exception('no database'))


def _recording_start(owned):
    """The real start_run, with the id it minted collected for cleanup."""
    real = activity.start_run

    def wrapper(now):
        run_id = real(now)
        owned.append(run_id)
        return run_id
    return wrapper


def test_a_started_run_is_recorded_before_it_can_finish(owned_runs):
    """The start marker is the whole point: a process that dies mid-cycle has
    to leave evidence that it ran, and only a row written first can."""
    run_id = activity.start_run(dt.datetime(2026, 9, 9, 12))
    owned_runs.append(run_id)

    run = _reload(run_id)
    assert run is not None
    assert run.status == 'running'
    assert run.finished_at is None
    assert run.summary_json is None
    assert uuid.UUID(run_id)


def test_success_stores_the_summary_exactly(owned_runs):
    """Stored verbatim inside a versioned envelope. A reader a year from now
    needs to know which vocabulary these counters were written in."""
    summary = _summary()
    run_id = activity.start_run(dt.datetime(2026, 9, 9, 12))
    owned_runs.append(run_id)
    activity.finish_run(run_id, dt.datetime(2026, 9, 9, 12, 0, 30),
                        summary=summary, error_code=None)

    run = _reload(run_id)
    assert run.status == 'ok'
    assert run.finished_at == dt.datetime(2026, 9, 9, 12, 0, 30)
    assert run.error_code is None
    assert run.summary_json['schema_version'] == 1
    assert run.summary_json['summary'] == summary


def test_error_has_no_manufactured_counts(owned_runs):
    """tick's exception branch returns a dict of zeros so its caller keeps a
    stable shape. Storing those zeros would turn a cycle that measured
    nothing into a cycle that measured nothing HAPPENING."""
    run_id = activity.start_run(dt.datetime(2026, 9, 9, 12))
    owned_runs.append(run_id)
    activity.finish_run(run_id, dt.datetime(2026, 9, 9, 12, 1),
                        summary=None, error_code='ingest_failed')

    run = _reload(run_id)
    assert run.status == 'error'
    assert run.summary_json is None
    assert run.error_code == 'ingest_failed'


def test_a_finished_run_cannot_be_rewritten(owned_runs):
    """Terminal update is idempotent. A retry, a duplicated scheduler job or a
    late callback must not restate totals that were already recorded."""
    run_id = activity.start_run(dt.datetime(2026, 9, 9, 12))
    owned_runs.append(run_id)
    first = _summary()
    activity.finish_run(run_id, dt.datetime(2026, 9, 9, 12, 0, 30),
                        summary=first, error_code=None)
    activity.finish_run(run_id, dt.datetime(2026, 9, 9, 12, 5),
                        summary=_summary(posts_seen=9999), error_code=None)

    run = _reload(run_id)
    assert run.summary_json['summary'] == first
    assert run.finished_at == dt.datetime(2026, 9, 9, 12, 0, 30)


def test_an_error_cannot_overwrite_a_completed_run(owned_runs):
    """The same rule in the other direction."""
    run_id = activity.start_run(dt.datetime(2026, 9, 9, 12))
    owned_runs.append(run_id)
    activity.finish_run(run_id, dt.datetime(2026, 9, 9, 12, 0, 30),
                        summary=_summary(), error_code=None)
    activity.finish_run(run_id, dt.datetime(2026, 9, 9, 12, 9),
                        summary=None, error_code='ingest_failed')

    run = _reload(run_id)
    assert run.status == 'ok'
    assert run.error_code is None


def test_finishing_an_unknown_run_is_survivable(app_context):
    """Nothing to update is not a crash. The recorder is instrumentation and
    may never become a reason a cycle fails."""
    activity.finish_run(str(uuid.uuid4()), dt.datetime(2026, 9, 9, 12),
                        summary=_summary(), error_code=None)


def test_start_returns_an_id_even_when_the_database_refuses(app_context, monkeypatch):
    """Ingest is about to run either way; it needs an id to report against."""
    monkeypatch.setattr(activity, '_session', _broken_session)
    run_id = activity.start_run(dt.datetime(2026, 9, 9, 12))
    assert uuid.UUID(run_id)


def test_finish_survives_a_database_failure(app_context, monkeypatch):
    monkeypatch.setattr(activity, '_session', _broken_session)
    activity.finish_run(str(uuid.uuid4()), dt.datetime(2026, 9, 9, 12),
                        summary=_summary(), error_code=None)


def test_the_recorder_holds_its_own_transaction(owned_runs):
    """It must not commit whatever the caller left pending.

    A run marker written from inside the ingest cycle would otherwise flush
    half-built buckets as a side effect of instrumentation.
    """
    pending_id = str(uuid.uuid4())
    db.session.add(RadarIngestRun(id=pending_id,
                                  started_at=dt.datetime(2026, 9, 9, 11),
                                  status='running'))

    run_id = activity.start_run(dt.datetime(2026, 9, 9, 12))
    owned_runs.append(run_id)

    with db.engine.connect() as outside:
        seen = outside.execute(
            sa.text('select count(*) from radar_ingest_runs where id = :i'),
            {'i': pending_id}).scalar()
    db.session.rollback()
    assert seen == 0, "the recorder committed the caller's pending work"
    assert _reload(run_id) is not None


# --- the runner ------------------------------------------------------------

def test_tick_records_a_completed_cycle(app_context, monkeypatch, owned_runs):
    import run_radar_ingest as runner

    summary = _summary()
    monkeypatch.setattr(runner.ingest, 'run_cycle', lambda now, fetchers: summary)
    monkeypatch.setattr(activity, 'start_run', _recording_start(owned_runs))

    result = runner.tick(dt.datetime(2026, 9, 9, 12, tzinfo=dt.timezone.utc), {})

    assert result == summary
    run = _reload(owned_runs[-1])
    assert run.status == 'ok'
    assert run.summary_json['summary'] == summary
    assert run.finished_at is not None
    assert run.started_at == dt.datetime(2026, 9, 9, 12)


def test_tick_records_a_failed_cycle_without_its_placeholder_zeros(
        app_context, monkeypatch, owned_runs):
    import run_radar_ingest as runner

    def fail(now, fetchers):
        raise RuntimeError('source exploded')

    monkeypatch.setattr(runner.ingest, 'run_cycle', fail)
    monkeypatch.setattr(activity, 'start_run', _recording_start(owned_runs))

    result = runner.tick(dt.datetime(2026, 9, 9, 12, tzinfo=dt.timezone.utc), {})

    assert result['status'] == 'error'      # the caller's shape is unchanged
    run = _reload(owned_runs[-1])
    assert run.status == 'error'
    assert run.summary_json is None
    assert run.error_code == 'ingest_failed'


def test_a_broken_recorder_still_lets_the_cycle_run(app_context, monkeypatch):
    """Instrumentation failure is not an ingest failure."""
    import run_radar_ingest as runner

    calls = []
    monkeypatch.setattr(runner.ingest, 'run_cycle',
                        lambda now, fetchers: calls.append(now) or _summary())
    monkeypatch.setattr(activity, '_session', _broken_session)

    result = runner.tick(dt.datetime(2026, 9, 9, 12, tzinfo=dt.timezone.utc), {})

    assert len(calls) == 1
    assert result['posts_seen'] == 12


def test_a_broken_recorder_does_not_roll_back_committed_intake(
        app_context, monkeypatch):
    """The stronger half of the same rule.

    The previous test only proves tick returns. This one has the cycle commit
    a real row through db.session -- the way run_cycle does -- and then breaks
    the recorder on both sides of it, so a recorder that shared or rolled back
    the caller's transaction would take that row with it.
    """
    import run_radar_ingest as runner

    marker_id = str(uuid.uuid4())

    def cycle_that_commits(now, fetchers):
        db.session.add(RadarIngestRun(id=marker_id, started_at=now,
                                      status='running'))
        db.session.commit()
        return _summary()

    monkeypatch.setattr(runner.ingest, 'run_cycle', cycle_that_commits)
    monkeypatch.setattr(activity, '_session', _broken_session)
    try:
        runner.tick(dt.datetime(2026, 9, 9, 12, tzinfo=dt.timezone.utc), {})

        db.session.rollback()
        with db.engine.connect() as outside:
            survived = outside.execute(
                sa.text('select count(*) from radar_ingest_runs where id = :i'),
                {'i': marker_id}).scalar()
        assert survived == 1, 'the recorder discarded work the cycle committed'
    finally:
        db.session.rollback()
        RadarIngestRun.query.filter_by(id=marker_id).delete(
            synchronize_session=False)
        db.session.commit()


def test_a_lost_start_marker_is_not_reported_as_a_repeat(
        app_context, monkeypatch, caplog):
    """Two different situations reach the same code path and must not read the
    same in the log: a run closed twice is by design, a run whose start marker
    was never stored means a cycle went unrecorded."""
    import logging

    with caplog.at_level(logging.INFO, logger='features.radar.activity'):
        activity.finish_run(str(uuid.uuid4()), dt.datetime(2026, 9, 9, 12),
                            summary=_summary(), error_code=None)
    assert any(record.levelno == logging.WARNING and 'unrecorded' in record.message
               for record in caplog.records), caplog.records


# --- schema ----------------------------------------------------------------

def test_the_two_recording_tables_exist_with_their_constraints(app_context):
    """Both tables ship in one additive migration; neither touches an
    existing table."""
    inspector = sa.inspect(db.engine)
    columns = {c['name']: c for c in inspector.get_columns('radar_ingest_runs')}
    assert columns['summary_json']['nullable'] is True
    assert columns['error_code']['nullable'] is True
    assert columns['finished_at']['nullable'] is True
    assert columns['started_at']['nullable'] is False
    assert inspector.get_pk_constraint('radar_ingest_runs')['constrained_columns'] == ['id']

    observation = {c['name']: c for c in
                   inspector.get_columns('radar_board_observations')}
    assert observation['producer_revision']['nullable'] is True
    assert observation['slot_start']['nullable'] is False
    unique = inspector.get_unique_constraints('radar_board_observations')
    assert any(u['column_names'] == ['slot_start'] for u in unique), unique


def test_the_status_vocabulary_is_enforced_by_the_database(app_context):
    """A CHECK is only a comment until the server enforces it.

    MySQL parsed and silently ignored CHECK before 8.0.16, MariaDB before
    10.2, and production is MariaDB -- so the constraint's existence in the
    migration proves nothing about the database the rows actually land in.
    This writes a status the vocabulary forbids and insists on a rejection.
    """
    run_id = str(uuid.uuid4())
    try:
        db.session.add(RadarIngestRun(id=run_id,
                                      started_at=dt.datetime(2019, 1, 1),
                                      status='banana'))
        with pytest.raises((sa.exc.IntegrityError, sa.exc.OperationalError,
                            sa.exc.DataError)):
            db.session.commit()
    finally:
        db.session.rollback()
        RadarIngestRun.query.filter_by(id=run_id).delete(
            synchronize_session=False)
        db.session.commit()


def test_the_migration_adds_and_removes_only_its_own_two_tables(app_context):
    """Upgrade, downgrade, upgrade -- against the disposable database.

    The claim being pinned is not that the tables appear, but that nothing
    else moves when they do. A column-shape fingerprint of every table is
    taken before and after, and a pre-existing row is counted, so a migration
    that quietly rebuilt or emptied a neighbour would be caught.

    The target is named rather than left as "one step back". Once another
    revision was stacked on top of this one, a bare downgrade() stopped
    reaching the point where these tables do not exist, and the test began
    asserting something it was no longer doing.
    """
    from flask_migrate import downgrade, upgrade

    before = _schema_fingerprint()
    watches_before = db.session.execute(
        sa.text('select count(*) from radar_watch')).scalar()
    assert 'radar_ingest_runs' in before

    with _logging_preserved():
        downgrade(revision=BEFORE_THESE_TABLES)
    after_down = _schema_fingerprint()
    try:
        assert set(before) - set(after_down) == {
            'radar_ingest_runs', 'radar_board_observations'}
        assert set(after_down) - set(before) == set()
        assert {t: f for t, f in before.items() if t in after_down} == after_down
    finally:
        with _logging_preserved():
            upgrade()          # to head, whatever is stacked above

    assert _schema_fingerprint() == before
    assert db.session.execute(
        sa.text('select count(*) from radar_watch')).scalar() == watches_before


@contextlib.contextmanager
def _logging_preserved():
    """Undo what running alembic in-process does to logging.

    migrations/env.py calls `fileConfig(config.config_file_name)`, and
    logging.config.fileConfig disables every logger it does not name. Running a
    migration inside the suite therefore silences `features.radar.*` and the
    daemon's loggers for every test that comes after -- which showed up as
    three unrelated caplog assertions in tests/test_radar_daemon.py finding an
    empty log, only when this module ran first.
    """
    import logging

    manager = logging.root.manager
    before = {name: logger.disabled
              for name, logger in manager.loggerDict.items()
              if isinstance(logger, logging.Logger)}
    root_level = logging.root.level
    try:
        yield
    finally:
        for name, was_disabled in before.items():
            logger = manager.loggerDict.get(name)
            if isinstance(logger, logging.Logger):
                logger.disabled = was_disabled
        logging.root.setLevel(root_level)


def _schema_fingerprint():
    """Every table's column shape, as a dict the test can diff.

    The rollback is load-bearing. MySQL 8's information_schema is served from
    the transactional data dictionary, so a session that read it once keeps
    showing the pre-migration catalogue under REPEATABLE READ -- the tables
    looked like they survived their own downgrade.
    """
    db.session.rollback()
    rows = db.session.execute(sa.text(
        'select table_name, column_name, column_type, is_nullable'
        ' from information_schema.columns where table_schema = database()'
        ' order by table_name, ordinal_position')).fetchall()
    shape: dict[str, list] = {}
    for table, column, ctype, nullable in rows:
        shape.setdefault(table, []).append((column, ctype, nullable))
    return shape


def test_a_slot_cannot_be_recorded_twice(app_context):
    """The archive's immutability is enforced in SQL, not only in Python."""
    slot = dt.datetime(2019, 1, 1, 0, 0)     # far outside any real capture
    # Left behind if an earlier run of this test died between its commit and
    # its cleanup; without this the first insert below would be the conflict.
    RadarBoardObservation.query.filter_by(slot_start=slot).delete(
        synchronize_session=False)
    db.session.commit()
    try:
        db.session.add(RadarBoardObservation(
            id=str(uuid.uuid4()), slot_start=slot,
            observed_at=dt.datetime(2019, 1, 1, 0, 1), schema_version=1,
            producer_revision='test', selections_json={}, payload_json={}))
        db.session.commit()
        db.session.add(RadarBoardObservation(
            id=str(uuid.uuid4()), slot_start=slot,
            observed_at=dt.datetime(2019, 1, 1, 0, 2), schema_version=1,
            producer_revision='test', selections_json={}, payload_json={}))
        with pytest.raises(sa.exc.IntegrityError):
            db.session.commit()
    finally:
        db.session.rollback()
        RadarBoardObservation.query.filter_by(slot_start=slot).delete(
            synchronize_session=False)
        db.session.commit()

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
import datetime as dt
import uuid

import pytest
import sqlalchemy as sa

from app import app as flask_app
from extensions import db
from features.radar import activity
from models import RadarBoardObservation, RadarIngestRun


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
    """The shape ingest.run_cycle actually returns."""
    base = {'status': 'ok', 'posts_seen': 12, 'posts_new': 4, 'mentions': 7,
            'buckets_written': 3, 'per_source': {'bluesky': 12},
            'aggregate_status': {}, 'catchup_depth': {},
            'intake_reasons': {'bluesky': {'no_ticker': 8}}}
    base.update(over)
    return base


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


def test_a_slot_cannot_be_recorded_twice(app_context):
    """The archive's immutability is enforced in SQL, not only in Python."""
    slot = dt.datetime(2019, 1, 1, 0, 0)     # far outside any real capture
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

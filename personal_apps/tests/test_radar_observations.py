"""What the board archive is allowed to keep, and what it must refuse.

The archive is a bounded observation history: two fixed, viewer-independent
board selections, captured on a quarter-hour and never rewritten. Most of what
follows guards the boundaries rather than the happy path -- no account state,
no operational counters, no manufactured historical time, and no second
version of a slot that was already recorded.

Every row is written under dates far outside any real capture window and is
deleted afterwards, because this suite runs against a database that will also
hold genuine observations.
"""
import datetime as dt

import pytest
import sqlalchemy as sa

from app import app as flask_app
from extensions import db
from features.radar import observations
from features.radar.config import SOURCES
from models import RadarBoardObservation

# 2019 is before Radar existed; nothing real can collide with it.
BASE = dt.datetime(2019, 3, 4, 10, 0)


@pytest.fixture()
def app_context():
    with flask_app.app_context():
        yield


@pytest.fixture(autouse=True)
def only_test_slots(app_context):
    """Remove every observation this module could have written.

    Before as well as after: a run killed mid-suite would otherwise leave a
    slot behind, and the next run would fail at `capture(...) is True` with a
    confusing "already recorded" instead of a clean start.
    """
    _clear_test_slots()
    yield
    _clear_test_slots()


def _clear_test_slots():
    db.session.rollback()
    RadarBoardObservation.query.filter(
        RadarBoardObservation.slot_start < dt.datetime(2020, 1, 1)).delete(
            synchronize_session=False)
    db.session.commit()


def fake_payload(args, **kwargs):
    """Enough of a board to tell the markets apart, plus the private and
    operational fields the archive must strip."""
    return {
        'market': args['market'],
        'generated_at': '2019-03-04T09:59:00Z',
        'rows': [{'ticker': 'AAA'}],
        'excluded': {'floor': 2},
        'watching': ['PRIVATE'],
        'watch_rows': [{'ticker': 'PRIVATE'}],
        'spend': {'today_usd': 1.0},
        'sentiment_ops': {'pending': 3},
        'market_data_ops': {'cycles': 1},
    }


def _stored(slot):
    db.session.rollback()
    return RadarBoardObservation.query.filter_by(slot_start=slot).one_or_none()


def test_the_slot_is_the_quarter_hour_the_capture_fell_in(app_context, monkeypatch):
    monkeypatch.setattr(observations, 'build_payload', fake_payload)
    assert observations.capture(BASE.replace(minute=37, second=51),
                                producer_revision='test') is True

    row = _stored(BASE.replace(minute=30))
    assert row is not None
    assert row.observed_at == BASE.replace(minute=37, second=51)


def test_slot_is_immutable(app_context, monkeypatch):
    """The first capture of a quarter-hour is the one that stands."""
    monkeypatch.setattr(observations, 'build_payload', fake_payload)
    now = BASE.replace(minute=1)
    assert observations.capture(now, producer_revision='test') is True
    assert observations.capture(now, producer_revision='changed') is False

    row = _stored(BASE)
    assert row.producer_revision == 'test'
    assert 'watching' not in row.payload_json['us']


def test_a_later_slot_is_a_second_observation(app_context, monkeypatch):
    monkeypatch.setattr(observations, 'build_payload', fake_payload)
    assert observations.capture(BASE.replace(minute=1)) is True
    assert observations.capture(BASE.replace(minute=16)) is True

    db.session.rollback()
    assert RadarBoardObservation.query.filter(
        RadarBoardObservation.slot_start.in_(
            [BASE, BASE.replace(minute=15)])).count() == 2


def test_a_late_capture_keeps_the_time_it_actually_ran(app_context, monkeypatch):
    """observed_at is the caller's instant, not the slot it was filed under.

    Half of what makes it evidence; the other half is
    test_the_scheduled_job_captures_the_wall_clock, which pins that the one
    production caller's instant is the clock's.
    """
    monkeypatch.setattr(observations, 'build_payload', fake_payload)
    late = BASE.replace(minute=14, second=59)
    observations.capture(late)

    assert _stored(BASE).observed_at == late


def test_account_state_and_operational_counters_never_enter_the_archive(
        app_context, monkeypatch):
    """The serializer reads spend and the ops summaries as a side effect of
    building any board. Those are live health, not research evidence, and a
    watching list is somebody's private mark."""
    monkeypatch.setattr(observations, 'build_payload', fake_payload)
    observations.capture(BASE.replace(minute=2))

    for market in ('us', 'de'):
        stored = _stored(BASE).payload_json[market]
        for forbidden in ('watching', 'watch_rows', 'spend', 'sentiment_ops',
                          'market_data_ops'):
            assert forbidden not in stored, forbidden
        assert stored['rows'] == [{'ticker': 'AAA'}]
        assert stored['excluded'] == {'floor': 2}


def test_the_board_is_never_asked_for_a_caller(app_context, monkeypatch):
    """user_id=None is what makes the pair viewer-independent."""
    seen = []

    def spy(args, **kwargs):
        seen.append((dict(args), kwargs))
        return fake_payload(args)

    monkeypatch.setattr(observations, 'build_payload', spy)
    now = BASE.replace(minute=3)
    observations.capture(now)

    assert [call[1]['user_id'] for call in seen] == [None, None]
    # The build is handed the real instant, not the slot boundary: passing the
    # boundary would date the board's own reads to a time that never happened.
    assert [call[1]['now'] for call in seen] == [now, now]


def test_the_captured_queries_are_the_fixed_pair(app_context, monkeypatch):
    """Recorded beside the answer, so no later reader has to assume which
    selection produced these rows."""
    monkeypatch.setattr(observations, 'build_payload', fake_payload)
    observations.capture(BASE.replace(minute=4))

    selections = _stored(BASE).selections_json
    assert set(selections['queries']) == {'us', 'de'}
    for market, query in selections['queries'].items():
        assert query == {'market': market, 'sources': ','.join(SOURCES),
                         'segment': '', 'window': '24', 'venues': '1',
                         'limit': '50'}


def test_the_searched_subreddits_are_recoverable(app_context, monkeypatch):
    """`reddit` expands to whatever REDDIT_SUBS held at capture time, and that
    list changes. A row's own sources say which subs contributed, never which
    were searched."""
    from features.radar.config import expand_sources

    monkeypatch.setattr(observations, 'build_payload', fake_payload)
    observations.capture(BASE.replace(minute=9))

    expanded = _stored(BASE).selections_json['sources_expanded']
    assert expanded == sorted(expand_sources(SOURCES))
    assert len(expanded) > len(SOURCES), 'the roots were stored unexpanded'


def test_one_missing_market_records_nothing(app_context, monkeypatch):
    """A pair is the unit. Half of one would be an observation of a board
    nobody selected."""
    def half(args, **kwargs):
        if args['market'] == 'de':
            raise RuntimeError('the German board could not be built')
        return fake_payload(args)

    monkeypatch.setattr(observations, 'build_payload', half)
    with pytest.raises(RuntimeError):
        observations.capture(BASE.replace(minute=5))

    assert _stored(BASE) is None


def test_a_database_failure_that_is_not_the_slot_conflict_stays_an_error(
        app_context, monkeypatch):
    """Only the unique-slot conflict means 'already recorded'. Swallowing
    anything else would turn an outage into a silent gap."""
    monkeypatch.setattr(observations, 'build_payload', fake_payload)

    def explode(*args, **kwargs):
        raise sa.exc.OperationalError('insert', {}, Exception('no database'))

    monkeypatch.setattr(observations, '_session', explode)
    with pytest.raises(sa.exc.OperationalError):
        observations.capture(BASE.replace(minute=6))


def test_an_integrity_error_that_left_no_slot_is_re_raised(
        app_context, monkeypatch):
    """An IntegrityError is not automatically a duplicate.

    Production is MariaDB, which materialises a JSON column with its own
    json_valid CHECK -- a payload that could not be serialised arrives in the
    same except clause. Reported as a benign duplicate it would leave the slot
    empty and say so at INFO. The branch asks what actually happened, and this
    forces the answer to be no.
    """
    monkeypatch.setattr(observations, 'build_payload', fake_payload)
    now = BASE.replace(minute=11)
    assert observations.capture(now) is True

    # A real conflict, with the existence check told the slot is not there.
    monkeypatch.setattr(observations, '_slot_exists', lambda slot: False)
    with pytest.raises(sa.exc.IntegrityError):
        observations.capture(now)


def test_an_unknown_producer_revision_is_recorded_as_unknown(
        app_context, monkeypatch):
    """NULL is honest. A deployment that did not say which revision it is
    must not be given one."""
    monkeypatch.setattr(observations, 'build_payload', fake_payload)
    observations.capture(BASE.replace(minute=7), producer_revision=None)

    assert _stored(BASE).producer_revision is None
    assert _stored(BASE).schema_version == 1


def test_the_revision_comes_from_configuration_not_a_subprocess(monkeypatch):
    """Read per cycle, so a redeploy is visible without a restart -- but from
    the environment, never by shelling out to Git on the ingest host."""
    monkeypatch.delenv('RADAR_PRODUCER_REVISION', raising=False)
    assert observations.producer_revision() is None
    monkeypatch.setenv('RADAR_PRODUCER_REVISION', 'abc1234')
    assert observations.producer_revision() == 'abc1234'


def test_capture_is_disabled_until_someone_turns_it_on(monkeypatch):
    """Default off until the migration and a staging pass have run."""
    monkeypatch.delenv('RADAR_OBSERVATION_CAPTURE_ENABLED', raising=False)
    assert observations.capture_enabled() is False
    monkeypatch.setenv('RADAR_OBSERVATION_CAPTURE_ENABLED', 'true')
    assert observations.capture_enabled() is True
    monkeypatch.setenv('RADAR_OBSERVATION_CAPTURE_ENABLED', 'no')
    assert observations.capture_enabled() is False


def test_latest_observed_at_reads_only_the_database(app_context, monkeypatch):
    """The admin surface asks how old the archive is. That question must not
    build a board or reach a provider."""
    def forbidden(*args, **kwargs):
        raise AssertionError('latest_observed_at built a board')

    monkeypatch.setattr(observations, 'build_payload', fake_payload)
    observations.capture(BASE.replace(minute=8))
    monkeypatch.setattr(observations, 'build_payload', forbidden)

    # Compared against this module's own rows. A plain `>= BASE` would be
    # satisfied by any genuine 2026 observation the database happens to hold,
    # whether or not the capture above wrote anything.
    db.session.rollback()
    ours = db.session.query(sa.func.max(RadarBoardObservation.observed_at)).filter(
        RadarBoardObservation.slot_start < dt.datetime(2020, 1, 1)).scalar()
    assert ours == BASE.replace(minute=8)
    assert observations.latest_observed_at() >= ours


# --- the scheduled job -----------------------------------------------------

def test_the_scheduled_job_contains_its_own_failures(app_context, monkeypatch):
    """A capture that raises must not take the ingest daemon's scheduler with
    it, and must leave no half-written row."""
    import run_radar_ingest as runner

    called = []

    def explode_after_being_called(now, **kwargs):
        called.append(now)
        raise RuntimeError('capture exploded')

    monkeypatch.setenv('RADAR_OBSERVATION_CAPTURE_ENABLED', 'true')
    monkeypatch.setattr(runner.observations, 'capture', explode_after_being_called)
    runner._scheduled_observations()          # must not raise

    assert len(called) == 1, 'the job never reached capture'
    # The slot the job would really have written, not a 2019 one no
    # implementation could have produced.
    db.session.rollback()
    assert RadarBoardObservation.query.filter_by(
        slot_start=observations._slot(called[0])).one_or_none() is None


def test_the_scheduled_job_does_nothing_while_capture_is_disabled(
        app_context, monkeypatch):
    import run_radar_ingest as runner

    calls = []
    monkeypatch.setattr(runner.observations, 'capture',
                        lambda now, **kw: calls.append(now))
    monkeypatch.setattr(runner.observations, 'capture_enabled', lambda: False)
    runner._scheduled_observations()
    assert calls == []

    monkeypatch.setattr(runner.observations, 'capture_enabled', lambda: True)
    runner._scheduled_observations()
    assert len(calls) == 1


def test_the_scheduled_job_captures_the_wall_clock(app_context, monkeypatch):
    """The whole real-time guarantee lives here.

    `capture(now)` cannot enforce that its instant is the wall clock -- `now`
    is an injected clock and the parameter exists so the tests are
    deterministic. What makes an observation evidence of a moment is that the
    ONE production caller passes `_utcnow()`, so that is what this pins.
    Without it, `_scheduled_observations` could pass the slot boundary,
    `_next_quarter_hour(...)` or a local time and every other test would still
    be green.
    """
    import run_radar_ingest as runner

    sentinel = dt.datetime(2019, 4, 2, 9, 37, 12, 5)
    calls = []
    monkeypatch.setenv('RADAR_OBSERVATION_CAPTURE_ENABLED', 'true')
    monkeypatch.setattr(runner, '_utcnow', lambda: sentinel)
    monkeypatch.setattr(runner.observations, 'capture',
                        lambda now, **kw: calls.append(now))
    runner._scheduled_observations()

    assert calls == [sentinel], (
        'the capture job must file the observation under the instant the clock '
        'reported, unrounded and unadjusted')


def test_the_job_is_registered_on_the_quarter_hour(monkeypatch):
    """A job that ships unscheduled records nothing and says nothing.

    The daemon suite added this shape of test after the profile job shipped
    unregistered and no test noticed.
    """
    import datetime as _dt

    from test_radar_daemon import _captured_jobs

    job = _captured_jobs(monkeypatch)['radar_board_observations']
    function, trigger, kwargs = job
    assert function is not None
    assert trigger == 'interval'
    assert kwargs['minutes'] == 15
    assert kwargs['max_instances'] == 1
    assert kwargs['coalesce'] is True
    # Aligned, so which part of a slot gets sampled is a property of the
    # design rather than of the last restart.
    first = kwargs['next_run_time']
    assert first.minute in (0, 15, 30, 45)
    assert first.second == 0 and first.microsecond == 0
    assert first > _dt.datetime.now(_dt.timezone.utc)


def test_a_failed_capture_does_not_stop_the_next_ingest_cycle(
        app_context, monkeypatch):
    """The two jobs are independent, and the archive is the one allowed to
    have gaps."""
    import run_radar_ingest as runner

    monkeypatch.setenv('RADAR_OBSERVATION_CAPTURE_ENABLED', 'true')
    monkeypatch.setattr(runner.observations, 'capture',
                        lambda now, **kw: (_ for _ in ()).throw(
                            RuntimeError('capture exploded')))
    runner._scheduled_observations()

    cycles = []
    monkeypatch.setattr(runner.ingest, 'run_cycle',
                        lambda now, fetchers: cycles.append(now) or {
                            'posts_seen': 0, 'posts_new': 0, 'mentions': 0,
                            'buckets_written': 0, 'per_source': {},
                            'aggregate_status': {}, 'catchup_depth': {},
                            'intake_reasons': {}})
    try:
        runner.tick(dt.datetime(2019, 3, 4, 12, tzinfo=dt.timezone.utc), {})
        assert len(cycles) == 1
    finally:
        # tick records a real run. Remove the one this test caused, and only
        # that one -- it is dated 2019 like every other row here.
        from models import RadarIngestRun
        db.session.rollback()
        RadarIngestRun.query.filter(
            RadarIngestRun.started_at < dt.datetime(2020, 1, 1)).delete(
                synchronize_session=False)
        db.session.commit()


# --- against the real serializer -------------------------------------------

def test_the_strip_list_still_matches_the_board_the_server_builds(app_context):
    """Every other test here replaces build_payload with a fake, so nothing
    else notices when the serializer changes underneath EXCLUDED.

    If a new account-scoped or operational key appears, or one of the five is
    renamed, this fails rather than letting the field into the archive.
    """
    built = observations.build_payload(
        observations._queries()['us'],
        now=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
        user_id=None)

    assert observations.EXCLUDED <= set(built), (
        'a field the archive strips no longer exists to be stripped: '
        f'{observations.EXCLUDED - set(built)}')
    kept = set(built) - observations.EXCLUDED
    assert 'rows' in kept and 'excluded' in kept and 'generated_at' in kept
    for private in ('watching', 'watch_rows', 'spend', 'sentiment_ops',
                    'market_data_ops'):
        assert private not in kept


def test_a_real_board_row_carries_no_post_text(app_context):
    """The board is rows and counts; the posts live behind the detail
    endpoint. Nothing that would put source prose in the archive."""
    built = observations.build_payload(
        observations._queries()['us'],
        now=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
        user_id=None)

    for row in built['rows']:
        assert 'posts' not in row and 'body' not in row and 'text' not in row
        # The one prose-shaped field is the server's own phrasing, generated
        # from counts. It never quotes a source.
        assert all(set(clause) == {'kind', 'text'} for clause in row['clauses'])

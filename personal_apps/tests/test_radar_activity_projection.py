"""The typed counter projection, against the envelope reducer it replaces.

Three things are under test here and they are separate questions.

Parity: the new read must return exactly what the old envelope-based reducer
returned, for every shape of stored data. The old reducer lives in this file as
`reference_day` -- an oracle, deliberately not a production fallback. If
production kept a JSON path to fall back to, the read would still be able to
fetch envelopes, which is the cost this whole change exists to remove.

Provenance: the migration's frozen projection and the live `activity.project`
must agree. They are separate code on purpose -- a migration cannot import a
service that will keep changing -- so something has to pin them together.

Honesty: a null counter and a measured zero are different facts, and no
arrangement of missing, malformed, off-version or still-running rows may turn
one into the other.
"""
import datetime as dt
import importlib.util
import pathlib
import uuid

import pytest
import sqlalchemy as sa

from app import app as flask_app
from extensions import db
from features.radar import activity
from models import RadarIngestRun

# A window nothing else occupies. The backend suite anchors fixtures in 2019
# and several of its modules blanket-delete `started_at < 2020-01-01`; this
# module cleans up after itself for the same reason.
BASE = dt.datetime(2019, 3, 12, 10, 0)


@pytest.fixture
def app_context():
    with flask_app.app_context():
        _wipe()
        yield
        _wipe()


def _wipe():
    db.session.rollback()
    RadarIngestRun.query.filter(
        RadarIngestRun.started_at < dt.datetime(2020, 1, 1)).delete(
            synchronize_session=False)
    db.session.commit()


def store(started_at, status='ok', envelope=..., **overrides):
    """One row, projected exactly as `finish_run` would project it."""
    if envelope is ...:
        envelope = {'schema_version': activity.SCHEMA_VERSION,
                    'summary': {name: 1 for name in activity.COUNTERS}}
    version, countable, counters = activity.project(envelope)
    row = RadarIngestRun(id=str(uuid.uuid4()), started_at=started_at,
                         finished_at=started_at + dt.timedelta(seconds=30),
                         status=status, summary_json=envelope,
                         summary_schema_version=version,
                         summary_countable=countable, **counters)
    for name, value in overrides.items():
        setattr(row, name, value)
    db.session.add(row)
    db.session.commit()
    return row


def envelope(version=activity.SCHEMA_VERSION, **counters):
    return {'schema_version': version, 'summary': dict(counters)}


# --- the oracle ------------------------------------------------------------

def reference_day(rows) -> dict:
    """The reducer this change replaced, verbatim in behaviour.

    Reads `summary_json` and nothing else, exactly as `activity._counted` and
    `activity._counters` did before the projection existed. Kept here so parity
    is a claim a test can fail, and kept OUT of production so the read has no
    envelope path left to take.
    """
    completed = [row for row in rows if row.status == 'ok']
    summaries = [row.summary_json['summary'] for row in completed
                 if isinstance(row.summary_json, dict)
                 and row.summary_json.get('schema_version')
                 == activity.SCHEMA_VERSION
                 and isinstance(row.summary_json.get('summary'), dict)]
    if not summaries:
        counters = {name: None for name in activity.COUNTERS}
    else:
        counters = {}
        for name in activity.COUNTERS:
            values = [summary.get(name) for summary in summaries]
            counters[name] = (None if any(value is None for value in values)
                              else sum(values))
    return {
        **counters,
        'completed_runs': len(completed),
        'counted_runs': len(summaries),
        'incomplete_runs': sum(1 for row in rows if row.status == 'running'),
        'error_runs': sum(1 for row in rows if row.status == 'error'),
        'completeness': 'partial' if completed else 'unknown',
    }


def compared(now=None):
    """One day, both ways. Returns (from the projection, from the oracle)."""
    now = now or BASE
    produced = activity.summary(now, 1)['days'][-1]
    day_from, day_to = activity._day_bounds(activity._berlin_date(now))
    rows = RadarIngestRun.query.filter(
        RadarIngestRun.started_at >= day_from,
        RadarIngestRun.started_at < day_to).all()
    expected = reference_day(rows)
    return {key: value for key, value in produced.items()
            if key != 'date'}, expected


# --- differential parity ---------------------------------------------------

def test_an_empty_day_reads_the_same_both_ways(app_context):
    produced, expected = compared()
    assert produced == expected
    assert all(produced[name] is None for name in activity.COUNTERS)
    assert produced['completeness'] == 'unknown'


def test_a_genuine_zero_survives_as_zero(app_context):
    """The distinction the whole module exists for. A cycle that ran and
    measured nothing is not a cycle that never reported."""
    store(BASE, envelope=envelope(**{name: 0 for name in activity.COUNTERS}))
    produced, expected = compared()
    assert produced == expected
    assert produced['posts_seen'] == 0, 'a measured zero became absent'
    assert produced['counted_runs'] == 1


def test_a_missing_counter_nulls_that_counter_and_no_other(app_context):
    store(BASE, envelope=envelope(posts_seen=5, posts_new=2, mentions=1,
                                  buckets_written=1))
    store(BASE + dt.timedelta(hours=1),
          envelope=envelope(posts_seen=7, posts_new=3, mentions=2))
    produced, expected = compared()
    assert produced == expected
    assert produced['buckets_written'] is None, 'absence became a total'
    assert produced['posts_seen'] == 12
    assert produced['counted_runs'] == 2, 'an omitted counter cost the row'


def test_an_explicit_null_counter_is_the_same_as_an_absent_one(app_context):
    store(BASE, envelope=envelope(posts_seen=5, posts_new=None, mentions=1,
                                  buckets_written=1))
    produced, expected = compared()
    assert produced == expected
    assert produced['posts_new'] is None


@pytest.mark.parametrize('body', [
    None,
    'not a mapping',
    {'summary': {'posts_seen': 3}},                       # unversioned
    {'schema_version': activity.SCHEMA_VERSION},          # no summary
    {'schema_version': activity.SCHEMA_VERSION, 'summary': 'not a mapping'},
])
def test_a_malformed_envelope_is_completed_but_never_counted(app_context, body):
    store(BASE, envelope=body)
    produced, expected = compared()
    assert produced == expected
    assert produced['completed_runs'] == 1
    assert produced['counted_runs'] == 0
    assert all(produced[name] is None for name in activity.COUNTERS)


def test_an_off_version_run_neither_adds_nor_poisons(app_context):
    """The version exists because a counter's MEANING changed. An older run
    must not be added to a current one -- and must not null the day either,
    because it was never a participant."""
    store(BASE, envelope=envelope(posts_seen=4, posts_new=1, mentions=1,
                                  buckets_written=1))
    store(BASE + dt.timedelta(hours=1),
          envelope=envelope(version=activity.SCHEMA_VERSION + 1,
                            posts_seen=1000))
    store(BASE + dt.timedelta(hours=2),
          envelope=envelope(version=activity.SCHEMA_VERSION - 1))
    produced, expected = compared()
    assert produced == expected
    assert produced['posts_seen'] == 4, 'an off-version run was added in'
    assert produced['completed_runs'] == 3
    assert produced['counted_runs'] == 1


def test_running_and_error_runs_contribute_no_counters(app_context):
    store(BASE, envelope=envelope(posts_seen=6, posts_new=2, mentions=1,
                                  buckets_written=1))
    store(BASE + dt.timedelta(hours=1), status='running', envelope=None)
    store(BASE + dt.timedelta(hours=2), status='error', envelope=None)
    # A row that is somehow both an error and carrying a full envelope still
    # contributes nothing: status decides participation, not the payload.
    store(BASE + dt.timedelta(hours=3), status='error',
          envelope=envelope(posts_seen=999, posts_new=999, mentions=999,
                            buckets_written=999))
    produced, expected = compared()
    assert produced == expected
    assert produced['posts_seen'] == 6
    assert produced['incomplete_runs'] == 1
    assert produced['error_runs'] == 2
    assert produced['completed_runs'] == 1


def test_many_independent_sources_over_a_mixed_day(app_context):
    """Everything at once, which is what a real day looks like."""
    store(BASE, envelope=envelope(posts_seen=10, posts_new=4, mentions=3,
                                  buckets_written=2))
    store(BASE + dt.timedelta(minutes=5),
          envelope=envelope(posts_seen=0, posts_new=0, mentions=0,
                            buckets_written=0))
    store(BASE + dt.timedelta(minutes=10),
          envelope=envelope(posts_seen=7, posts_new=1, mentions=1,
                            buckets_written=1))
    store(BASE + dt.timedelta(minutes=15), status='running', envelope=None)
    store(BASE + dt.timedelta(minutes=20), status='error', envelope=None)
    store(BASE + dt.timedelta(minutes=25), envelope={'nonsense': True})
    store(BASE + dt.timedelta(minutes=30),
          envelope=envelope(version=99, posts_seen=1))
    produced, expected = compared()
    assert produced == expected
    assert produced['posts_seen'] == 17
    assert produced['counted_runs'] == 3
    assert produced['completed_runs'] == 5


# --- no day is frozen by its date ------------------------------------------

def test_a_run_crossing_midnight_changes_the_earlier_day_when_it_closes(
        app_context):
    """The reason nothing here may be memoised by date.

    A run is filed under the Berlin day it STARTED in, but `finish_run` closes
    it later. A cycle that starts at 23:59 and finishes after midnight rewrites
    the previous day's totals after that day has ended.
    """
    from features.radar import activity as module

    # 23:59 Berlin on 2019-03-12 is 22:59 UTC.
    late = dt.datetime(2019, 3, 12, 22, 59)
    next_day = dt.datetime(2019, 3, 13, 12, 0)
    run_id = module.start_run(late)

    before = module.summary(next_day, 7)
    day = [entry for entry in before['days']
           if entry['date'] == '2019-03-12'][0]
    assert day['incomplete_runs'] == 1
    assert day['completed_runs'] == 0
    assert day['posts_seen'] is None

    # Closed after midnight, and the counters land on the EARLIER day.
    module.finish_run(run_id, dt.datetime(2019, 3, 12, 23, 3),
                      summary={name: 3 for name in module.COUNTERS},
                      error_code=None)

    # The recorder commits in a session of its own, so this one is still
    # holding the REPEATABLE READ snapshot its first read opened. A request
    # ends its session; this test has to say so out loud rather than read
    # twice inside one transaction and call the stale answer a frozen day.
    db.session.rollback()

    after = module.summary(next_day, 7)
    day = [entry for entry in after['days']
           if entry['date'] == '2019-03-12'][0]
    assert day['incomplete_runs'] == 0, 'the closed run stayed incomplete'
    assert day['completed_runs'] == 1
    assert day['counted_runs'] == 1
    assert day['posts_seen'] == 3, 'a day was frozen by its date'


def test_a_run_that_stays_running_is_never_counted(app_context):
    from features.radar import activity as module

    module.start_run(BASE)
    produced, expected = compared()
    assert produced == expected
    assert produced['incomplete_runs'] == 1
    assert produced['completed_runs'] == 0
    assert produced['counted_runs'] == 0
    assert all(produced[name] is None for name in activity.COUNTERS)


def test_a_terminal_retry_does_not_restate_the_projection(app_context):
    """finish_run is idempotent, and the projection has to be too -- otherwise
    a late callback could double a day's totals."""
    from features.radar import activity as module

    run_id = module.start_run(BASE)
    module.finish_run(run_id, BASE + dt.timedelta(seconds=30),
                      summary={name: 4 for name in module.COUNTERS},
                      error_code=None)
    module.finish_run(run_id, BASE + dt.timedelta(seconds=60),
                      summary={name: 100 for name in module.COUNTERS},
                      error_code=None)

    produced, expected = compared()
    assert produced == expected
    assert produced['posts_seen'] == 4, 'a retry restated the totals'
    assert produced['counted_runs'] == 1


def test_an_error_run_stores_no_projection(app_context):
    from features.radar import activity as module

    run_id = module.start_run(BASE)
    module.finish_run(run_id, BASE + dt.timedelta(seconds=30), summary=None,
                      error_code='ingest_failed')

    db.session.rollback()
    row = db.session.get(RadarIngestRun, run_id)
    assert row.status == 'error'
    assert row.summary_countable is False
    assert row.summary_schema_version is None
    assert all(getattr(row, name) is None for name in module.COUNTERS)


@pytest.mark.parametrize('start,label', [
    (dt.datetime(2019, 3, 30, 22, 30), 'the 23-hour spring day'),
    (dt.datetime(2019, 10, 26, 22, 30), 'the 25-hour autumn day'),
])
def test_dst_days_group_by_the_berlin_day_that_was_lived(app_context, start,
                                                         label):
    """Built from two Berlin midnights, so a 23- or 25-hour day still holds
    exactly the runs that happened inside it."""
    store(start, envelope=envelope(posts_seen=1, posts_new=1, mentions=1,
                                   buckets_written=1))
    expected_date = activity._berlin_date(start)
    result = activity.summary(start + dt.timedelta(days=1), 7)
    matching = [entry for entry in result['days']
                if entry['date'] == expected_date.isoformat()]
    assert matching, f'{label}: {expected_date} missing from the window'
    assert matching[0]['completed_runs'] == 1, label
    assert matching[0]['posts_seen'] == 1, label


# --- the read must not fetch summary_json ----------------------------------

def test_the_activity_read_never_fetches_the_envelope(app_context):
    """The whole point of the projection, asserted at the query level.

    Not by shrinking the fixtures: this listens to what SQLAlchemy actually
    emits and fails if `summary_json` is named in any statement the read
    issues. A lazy ORM load would appear here too.
    """
    for offset in range(5):
        store(BASE + dt.timedelta(minutes=offset),
              envelope=envelope(posts_seen=1, posts_new=1, mentions=1,
                                buckets_written=1))

    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    sa.event.listen(db.engine, 'before_cursor_execute', record)
    try:
        activity.summary(BASE, 30)
    finally:
        sa.event.remove(db.engine, 'before_cursor_execute', record)

    assert statements, 'the read issued no statement at all'
    offenders = [statement for statement in statements
                 if 'summary_json' in statement.lower()]
    assert not offenders, (
        f'the activity read fetched the envelope: {offenders}')


def test_the_read_selects_the_projection_columns(app_context):
    """The positive control for the test above -- otherwise a read that had
    stopped querying runs entirely would also pass it."""
    store(BASE, envelope=envelope(posts_seen=1, posts_new=1, mentions=1,
                                  buckets_written=1))
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    sa.event.listen(db.engine, 'before_cursor_execute', record)
    try:
        activity.summary(BASE, 1)
    finally:
        sa.event.remove(db.engine, 'before_cursor_execute', record)

    joined = ' '.join(statements).lower()
    for column in ('summary_countable', 'summary_schema_version', 'posts_seen',
                   'buckets_written'):
        assert column in joined, f'the read never selected {column}'


# --- the migration's frozen rules match the live ones ----------------------

def _frozen_module():
    path = (pathlib.Path(__file__).resolve().parents[1] / 'migrations'
            / 'versions' / 'a7c31f0b52d4_add_radar_run_counter_projection.py')
    spec = importlib.util.spec_from_file_location('r3_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('body', [
    None,
    'not a mapping',
    42,
    {},
    {'schema_version': 1},
    {'schema_version': 1, 'summary': 'not a mapping'},
    {'schema_version': None, 'summary': {'posts_seen': 1}},
    {'schema_version': True, 'summary': {'posts_seen': 1}},
    {'summary': {'posts_seen': 1}},
    {'schema_version': 1, 'summary': {}},
    {'schema_version': 1, 'summary': {'posts_seen': 0, 'posts_new': 0,
                                      'mentions': 0, 'buckets_written': 0}},
    {'schema_version': 1, 'summary': {'posts_seen': 5}},
    {'schema_version': 1, 'summary': {'posts_seen': None}},
    {'schema_version': 99, 'summary': {'posts_seen': 5}},
    {'schema_version': 1, 'summary': {'posts_seen': -1}},
    {'schema_version': 1, 'summary': {'posts_seen': '5'}},
    {'schema_version': 1, 'summary': {'posts_seen': 1.5}},
    {'schema_version': 1, 'summary': {'posts_seen': True}},
    {'schema_version': 1, 'summary': {'posts_seen': 2 ** 63}},
    {'schema_version': 1, 'summary': {'posts_seen': 2 ** 63 - 1}},
])
def test_the_migration_projects_exactly_as_the_live_rules_do(body):
    """A migration cannot import a service that keeps changing, so the rules
    are duplicated on purpose. This is what stops the copy drifting."""
    assert _frozen_module()._frozen_project(body) == activity.project(body)


def test_the_frozen_domain_check_names_shapes_and_not_values():
    frozen = _frozen_module()
    bad = frozen._out_of_domain(
        {'schema_version': 1, 'summary': {'posts_seen': -3,
                                          'posts_new': 'seventeen',
                                          'mentions': 4}})
    assert sorted(bad) == [('posts_new', 'str'), ('posts_seen', 'out of range')]
    assert frozen._out_of_domain(
        {'schema_version': 1, 'summary': {'posts_seen': 4}}) == []


# --- the accepted counter domain -------------------------------------------

@pytest.mark.parametrize('value', [-1, '5', 1.5, True, 2 ** 63])
def test_a_counter_outside_the_domain_is_refused_not_coerced(app_context,
                                                             value):
    """Refused as absent, which nulls the day. Never clamped to a bound,
    rounded, parsed, or turned into a zero -- each of those would invent a
    measurement that was never taken."""
    version, countable, counters = activity.project(
        {'schema_version': activity.SCHEMA_VERSION,
         'summary': {'posts_seen': value, 'posts_new': 1, 'mentions': 1,
                     'buckets_written': 1}})
    assert countable is True, 'one bad counter cost the whole summary'
    assert counters['posts_seen'] is None
    assert counters['posts_new'] == 1


def test_the_largest_representable_counter_is_kept(app_context):
    counters = activity.project(
        {'schema_version': activity.SCHEMA_VERSION,
         'summary': {'posts_seen': 2 ** 63 - 1}})[2]
    assert counters['posts_seen'] == 2 ** 63 - 1

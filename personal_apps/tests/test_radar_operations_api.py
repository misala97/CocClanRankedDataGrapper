"""The two read-only operational endpoints.

`/radar/api/activity` answers what was recorded, and its hardest requirement is
what it must refuse to say. A day nobody recorded reads null, not zero. A day
whose only runs crashed or are still open reads null too, with the incomplete
and error counts beside it, because a run that never reported its totals is not
a run that measured nothing. Nothing here is ever labelled complete: successful
runs prove partial coverage and no more.

`/radar/api/ops` is a read of summaries the application already computes, behind
admin authorisation, with no control actions and no new provider requests.

Berlin days are real calendar days. The window is built from
`zoneinfo.ZoneInfo('Europe/Berlin')` midnights, so the day Germany changes clock
is 23 or 25 hours long and never 86,400 seconds.
"""
import datetime as dt
import uuid
from zoneinfo import ZoneInfo

import pytest

from app import app as flask_app
from extensions import db
from features.radar import activity
from models import AppUser, RadarIngestRun

BERLIN = ZoneInfo('Europe/Berlin')
# 2019, so no real recorded run can ever fall inside the tested window.
QUIET = dt.datetime(2019, 5, 15, 12, 0)


@pytest.fixture()
def app_context():
    with flask_app.app_context():
        yield


@pytest.fixture()
def owned_runs(app_context):
    ids = []
    yield ids
    db.session.rollback()
    if ids:
        RadarIngestRun.query.filter(RadarIngestRun.id.in_(ids)).delete(
            synchronize_session=False)
        db.session.commit()


@pytest.fixture()
def plain_user():
    """A logged-in account that is not an admin, removed afterwards."""
    from werkzeug.security import generate_password_hash

    with flask_app.app_context():
        user = AppUser(username='pytest radar ops nonadmin',
                       password_hash=generate_password_hash('x'),
                       is_admin=False)
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    flask_app.config['TESTING'] = True
    with flask_app.test_client() as test_client:
        with test_client.session_transaction() as flask_session:
            flask_session['user_id'] = user_id
        yield test_client

    with flask_app.app_context():
        db.session.delete(db.session.get(AppUser, user_id))
        db.session.commit()


def _run(ids, started, *, status, summary=None, error_code=None):
    """A test-owned run row, written directly so the day it lands in is exact."""
    run_id = str(uuid.uuid4())
    ids.append(run_id)
    db.session.add(RadarIngestRun(
        id=run_id, started_at=started,
        finished_at=None if status == 'running' else started + dt.timedelta(seconds=40),
        status=status,
        summary_json=None if summary is None
        else {'schema_version': 1, 'summary': summary},
        error_code=error_code))
    db.session.commit()
    return run_id


def _counts(**over):
    base = {'posts_seen': 0, 'posts_new': 0, 'mentions': 0, 'buckets_written': 0}
    base.update(over)
    return base


def _day(payload, date_str):
    return next(d for d in payload['days'] if d['date'] == date_str)


# --- what a day is ---------------------------------------------------------

def test_a_day_nobody_recorded_is_unobserved(app_context):
    """Null, not zero. The distinction is the entire point of the table."""
    payload = activity.summary(QUIET, 1)
    day = payload['days'][0]
    assert day['posts_seen'] is None
    assert day['posts_new'] is None
    assert day['mentions'] is None
    assert day['buckets_written'] is None
    assert day['completed_runs'] == 0
    assert day['completeness'] == 'unknown'


def test_a_recorded_zero_is_a_zero(app_context, owned_runs):
    """A cycle that ran and found nothing measured zero, and says so."""
    _run(owned_runs, QUIET, status='ok', summary=_counts())
    day = activity.summary(QUIET, 1)['days'][0]

    assert day['posts_seen'] == 0
    assert day['buckets_written'] == 0
    assert day['completed_runs'] == 1
    assert day['completeness'] == 'partial'


def test_crashed_and_failed_runs_add_no_counters(app_context, owned_runs):
    """A run that never reported its totals is incomplete, not empty."""
    _run(owned_runs, QUIET, status='error', error_code='ingest_failed')
    _run(owned_runs, QUIET.replace(hour=13), status='running')
    day = activity.summary(QUIET, 1)['days'][0]

    assert day['posts_seen'] is None
    assert day['completed_runs'] == 0
    assert day['error_runs'] == 1
    assert day['incomplete_runs'] == 1
    assert day['completeness'] == 'unknown'


def test_completed_runs_are_summed_and_still_only_partial(app_context, owned_runs):
    _run(owned_runs, QUIET, status='ok', summary=_counts(posts_seen=10, mentions=3))
    _run(owned_runs, QUIET.replace(hour=14), status='ok',
         summary=_counts(posts_seen=5, mentions=1, buckets_written=2))
    _run(owned_runs, QUIET.replace(hour=15), status='error',
         error_code='ingest_failed')
    day = activity.summary(QUIET, 1)['days'][0]

    assert day['posts_seen'] == 15
    assert day['mentions'] == 4
    assert day['buckets_written'] == 2
    assert day['completed_runs'] == 2
    assert day['error_runs'] == 1
    # Never 'complete'. Successful runs prove some coverage, never all of it.
    assert day['completeness'] == 'partial'


def test_a_run_belongs_to_the_berlin_day_it_started_in(app_context, owned_runs):
    """23:30 UTC in May is 01:30 the next morning in Berlin."""
    _run(owned_runs, dt.datetime(2019, 5, 14, 23, 30), status='ok',
         summary=_counts(posts_seen=7))
    payload = activity.summary(QUIET, 7)

    assert _day(payload, '2019-05-15')['posts_seen'] == 7
    assert _day(payload, '2019-05-14')['posts_seen'] is None


# --- the window ------------------------------------------------------------

def test_the_window_covers_the_requested_number_of_berlin_days(app_context):
    payload = activity.summary(QUIET, 7)
    assert len(payload['days']) == 7
    assert payload['days'][0]['date'] == '2019-05-09'
    assert payload['days'][-1]['date'] == '2019-05-15'


def test_the_spring_forward_day_is_twenty_three_hours(app_context):
    """Germany loses an hour on 2026-03-29. Subtracting 86,400 seconds would
    put the boundary in the wrong day and silently move runs between days."""
    payload = activity.summary(dt.datetime(2026, 3, 29, 12), 1)
    span = _parse(payload['to']) - _parse(payload['from'])
    assert span == dt.timedelta(hours=23)


def test_the_autumn_day_is_twenty_five_hours(app_context):
    payload = activity.summary(dt.datetime(2026, 10, 25, 12), 1)
    span = _parse(payload['to']) - _parse(payload['from'])
    assert span == dt.timedelta(hours=25)


def test_the_bounds_are_berlin_midnights_expressed_in_utc(app_context):
    payload = activity.summary(QUIET, 1)
    start = _parse(payload['from'])
    assert start.astimezone(BERLIN).hour == 0
    assert start.astimezone(BERLIN).date() == dt.date(2019, 5, 15)


def test_recording_start_is_reported_so_a_gap_can_be_read(app_context, owned_runs):
    """Days before the first recorded run are not missing measurements; there
    was nothing recording yet, and the surface has to be able to say which."""
    _run(owned_runs, QUIET, status='ok', summary=_counts())
    payload = activity.summary(QUIET, 1)
    assert payload['recording_started_at'] is not None
    assert payload['generated_at'].endswith('Z')
    assert payload['from'].endswith('Z') and payload['to'].endswith('Z')


def _parse(value):
    assert value.endswith('Z'), value
    return dt.datetime.fromisoformat(value[:-1]).replace(tzinfo=dt.timezone.utc)


# --- the endpoints ---------------------------------------------------------

def test_activity_rejects_unsupported_window(client):
    assert client.get('/radar/api/activity?days=2').status_code == 400
    assert client.get('/radar/api/activity?days=nonsense').status_code == 400
    assert client.get('/radar/api/activity?days=0').status_code == 400


def test_activity_accepts_only_the_three_windows(client):
    for days in (1, 7, 30):
        response = client.get(f'/radar/api/activity?days={days}')
        assert response.status_code == 200
        assert len(response.get_json()['days']) == days


def test_activity_defaults_to_a_week(client):
    assert len(client.get('/radar/api/activity').get_json()['days']) == 7


def test_activity_needs_a_session(anon_client):
    assert anon_client.get('/radar/api/activity?days=1').status_code in (302, 401, 403)


def test_ops_is_refused_to_a_signed_in_stranger(plain_user):
    """403, and distinguishable from an expired session: this reader IS signed
    in, and reloading will not help them."""
    assert plain_user.get('/radar/api/ops').status_code == 403


def test_ops_needs_a_session(anon_client):
    assert anon_client.get('/radar/api/ops').status_code in (302, 401, 403)


def test_ops_answers_the_admin_with_the_existing_summaries(client):
    payload = client.get('/radar/api/ops').get_json()
    assert set(payload) == {'generated_at', 'spend', 'sentiment', 'market_data',
                            'capture'}
    assert payload['generated_at'].endswith('Z')
    # Present as a key even before the first capture, so the surface renders an
    # age of "never" rather than treating the field as missing.
    assert 'latest_observed_at' in payload['capture']


def test_ops_makes_no_provider_requests(client, monkeypatch):
    """Visibility, not traffic. Reading the health page must not go and fetch
    a quote, and must not be able to start anything."""
    import features.radar.market_data as market_data

    def forbidden(*args, **kwargs):
        raise AssertionError('the ops endpoint reached a provider')

    for name in ('fetch_snapshot', 'fetch_quotes'):
        if hasattr(market_data, name):
            monkeypatch.setattr(market_data, name, forbidden)
    assert client.get('/radar/api/ops').status_code == 200


def test_activity_payload_carries_its_own_provenance(client):
    payload = client.get('/radar/api/activity?days=1').get_json()
    assert set(payload) >= {'from', 'to', 'generated_at', 'recording_started_at',
                            'days'}
    day = payload['days'][0]
    assert set(day) == {'date', 'posts_seen', 'posts_new', 'mentions',
                        'buckets_written', 'completed_runs', 'incomplete_runs',
                        'error_runs', 'completeness'}
    assert day['completeness'] in ('partial', 'unknown')

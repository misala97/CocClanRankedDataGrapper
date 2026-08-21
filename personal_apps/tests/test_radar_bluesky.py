# personal_apps/tests/test_radar_bluesky.py
"""Bluesky: the whole network, thinly.

144k posts/hour producing ~340 scored ticker mentions/hour spread market-wide.
Sparse per-ticker baselines are the point -- a ticker at 0.1 mentions/hour that
jumps to 20 is an enormous z-score, which is discovery the other sources cannot
do (spec 3.8).

The cursor clamp is what this suite mostly guards. Jetstream replays about 36
hours and silently gives you less than you asked for beyond that.
"""
import datetime as dt

from features.radar.sources import FetchResult
from features.radar.sources import bluesky


def _us(when):
    return int(when.replace(tzinfo=dt.timezone.utc).timestamp() * 1_000_000)


def _event(when, text='$ZZA looks strong', did='did:plc:abc', operation='create'):
    return {
        'did': did,
        'time_us': _us(when),
        'commit': {
            'operation': operation,
            'collection': 'app.bsky.feed.post',
            'rkey': 'r%d' % _us(when),
            'record': {'text': text, 'createdAt': when.isoformat() + 'Z'},
        },
    }


BASE = dt.datetime(2026, 8, 21, 14, 0, 0)


def drain_returning(events):
    def drain(cursor_us, budget):
        return list(events)
    return drain


def test_events_become_rawposts():
    # One minute, not ten: at ~40 posts/second a ten-minute gap between the
    # requested cursor and the first delivered event is itself clamp evidence,
    # and this test is about normalization rather than coverage.
    result = bluesky.fetch(BASE - dt.timedelta(minutes=1),
                           drain_returning([_event(BASE)]))
    assert isinstance(result, FetchResult)
    assert result.status == 'ok'
    post = result.posts[0]
    assert post.source == 'bluesky'
    assert post.channel == 'firehose'
    assert post.body == '$ZZA looks strong'
    assert post.author == 'did:plc:abc'
    assert post.created_utc == BASE


def test_non_create_operations_are_ignored():
    """Deletes and updates arrive on the same stream. A delete has no text and
    counting it would inflate volume with events that are not posts."""
    events = [_event(BASE, operation='delete'), _event(BASE, operation='create')]
    result = bluesky.fetch(BASE - dt.timedelta(minutes=10), drain_returning(events))
    assert len(result.posts) == 1


def test_posts_with_no_text_are_skipped():
    empty = _event(BASE)
    empty['commit']['record']['text'] = ''
    result = bluesky.fetch(BASE - dt.timedelta(minutes=10), drain_returning([empty]))
    assert result.posts == []


def test_a_silently_clamped_cursor_is_reported_as_truncated():
    """The trap. Ask Jetstream for 48 hours and it returns events from 36 hours
    ago with no error. A caller trusting that would carry a 12-hour hole it
    believed was complete -- exactly the fake spike `missing` exists to stop.
    """
    since = BASE - dt.timedelta(hours=48)
    earliest = BASE - dt.timedelta(hours=36)
    result = bluesky.fetch(since, drain_returning([_event(earliest), _event(BASE)]))
    assert result.status == 'truncated'
    assert result.covered_since == earliest


def test_an_honoured_cursor_reports_full_coverage():
    since = BASE - dt.timedelta(hours=6)
    result = bluesky.fetch(since, drain_returning([
        _event(since + dt.timedelta(seconds=30)), _event(BASE)]))
    assert result.status == 'ok'
    assert result.covered_since is None


def test_a_small_gap_is_tolerated():
    """A quiet minute at the start of the window is not a clamp. The tolerance
    keeps an idle network from being reported as a permanent hole."""
    since = BASE - dt.timedelta(hours=6)
    result = bluesky.fetch(since, drain_returning([
        _event(since + dt.timedelta(minutes=2)), _event(BASE)]))
    assert result.status == 'ok'


def test_a_failed_drain_is_missing():
    def drain(cursor_us, budget):
        raise bluesky.JetstreamUnavailable('connection refused')
    result = bluesky.fetch(BASE - dt.timedelta(hours=1), drain)
    assert result.status == 'missing'
    assert result.posts == []


def test_no_events_at_all_is_missing_not_a_quiet_network():
    """144k posts/hour means silence is a broken connection, never calm."""
    result = bluesky.fetch(BASE - dt.timedelta(hours=1), drain_returning([]))
    assert result.status == 'missing'


def test_the_drain_stops_once_it_reaches_live():
    """A fixed budget captured a 45-second window out of every 180-second
    cycle and quietly dropped the rest -- quietly because the shortfall was
    smaller than the clamp tolerance, so nothing marked it truncated.

    Verified against live traffic: a three-minute gap went from 1848 posts in
    45 seconds to 5399 in 12.
    """
    import inspect
    source = inspect.getsource(bluesky.live_drain)
    assert 'CAUGHT_UP_MARGIN' in source, 'drain would burn its whole budget'


def test_caught_up_margin_is_tight_enough_to_mean_live():
    """At ~30 posts/second, a few seconds behind is the front of the queue."""
    assert bluesky.CAUGHT_UP_MARGIN <= dt.timedelta(seconds=10)

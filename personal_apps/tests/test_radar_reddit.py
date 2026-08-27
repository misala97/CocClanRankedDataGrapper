# personal_apps/tests/test_radar_reddit.py
"""Reddit ingest over the published Atom feeds.

The feed holds 25 comments and has no cursor, which makes coverage a property
of poll frequency rather than of the code. Most of what is asserted here is
about saying so honestly: a cycle that missed comments must not produce buckets
claiming to be complete, and a cycle that read nothing must not look like a
quiet period.
"""
import datetime as dt

import pytest

from features.radar.sources import reddit

NOW = dt.datetime(2026, 8, 24, 12, 0, 0)


def entry(ident, minutes_ago, author='someone', body='talk about AAPL',
          title='a comment'):
    when = (NOW - dt.timedelta(minutes=minutes_ago)).strftime('%Y-%m-%dT%H:%M:%S+00:00')
    return f"""
      <entry>
        <id>{ident}</id>
        <author><name>/u/{author}</name></author>
        <updated>{when}</updated>
        <title>{title}</title>
        <link href="https://www.reddit.com/r/x/comments/{ident}/"/>
        <content type="html">&lt;div&gt;{body}&lt;/div&gt;</content>
      </entry>"""


def feed(entries):
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<feed xmlns="http://www.w3.org/2005/Atom">'
            + ''.join(entries) + '</feed>')


class FakeClient:
    """Serves a canned feed per subreddit, or raises what it is told to."""

    def __init__(self, feeds):
        self.feeds = feeds
        self.asked = []

    def get_feed(self, sub):
        self.asked.append(sub)
        answer = self.feeds[sub]
        if isinstance(answer, Exception):
            raise answer
        return answer


def test_a_comment_becomes_a_post_with_its_subreddit_on_it():
    """The subreddit rides on both the stored source name and channel.

    The concrete source is what gives each subreddit its own coverage status;
    channel remains the original venue label carried by the stored comment.
    """
    client = FakeClient({'pennystocks': feed([entry('t1_aaa', 5)])})

    posts, status, _rate = reddit.fetch_one('pennystocks', NOW - dt.timedelta(hours=1), client)

    assert len(posts) == 1
    post = posts[0]
    assert post.source == 'reddit:pennystocks'
    assert post.channel == 'pennystocks'
    assert post.external_id == 't1_aaa'
    assert post.author == '/u/someone'
    assert 'AAPL' in post.body
    assert status == 'ok'


def test_html_is_stripped_from_the_body():
    """The extractor reads text. Left as markup, `<b>AAPL</b>` is not a
    word-boundary match and the mention is silently lost."""
    client = FakeClient({'x': feed([
        entry('t1_b', 5, body='&lt;b&gt;AAPL&lt;/b&gt; to the moon')])})

    posts, _status, _rate = reddit.fetch_one('x', NOW - dt.timedelta(hours=1), client)

    assert posts[0].body == 'AAPL to the moon'


def test_a_short_feed_is_quiet_rather_than_incomplete():
    """A feed with room to spare returned everything there was.

    Marking it truncated would exclude it from baselines forever, so a quiet
    subreddit would gather data indefinitely and never become scoreable --
    which is the failure the 4chan module documents for pruned threads.
    """
    client = FakeClient({'Vitards': feed([entry('t1_only', 5)])})

    _posts, status, _rate = reddit.fetch_one(
        'Vitards', NOW - dt.timedelta(hours=6), client)

    assert status == 'ok'


def test_a_feed_that_rolled_past_the_cursor_is_truncated():
    """The regression this whole module has to get right.

    Twenty-five entries and no paging: if the OLDEST comment in the feed is
    newer than where we last read, comments happened in between that nobody
    saw. Reporting `ok` would let baselines treat an eighth of
    r/wallstreetbets as the whole of it.
    """
    client = FakeClient({'wallstreetbets': feed(
        [entry(f't1_{n}', n * 0.05) for n in range(reddit.FEED_LIMIT)])})

    _posts, status, _rate = reddit.fetch_one(
        'wallstreetbets', NOW - dt.timedelta(hours=2), client)

    assert status == 'truncated'


def test_a_feed_that_reaches_back_past_the_cursor_is_complete():
    """Teeth for the test above: if everything were truncated the assertion
    would pass without the comparison meaning anything."""
    client = FakeClient({'pennystocks': feed(
        [entry(f't1_{n}', n * 4) for n in range(reddit.FEED_LIMIT)])})

    _posts, status, _rate = reddit.fetch_one(
        'pennystocks', NOW - dt.timedelta(minutes=60), client)

    assert status == 'ok'


def test_only_comments_newer_than_the_cursor_are_returned():
    client = FakeClient({'x': feed([
        entry('t1_new', 5), entry('t1_old', 200)])})

    posts, _status, _rate = reddit.fetch_one('x', NOW - dt.timedelta(minutes=60), client)

    assert [p.external_id for p in posts] == ['t1_new']


def test_a_throttle_stops_the_cycle_instead_of_asking_again():
    """429 is per-IP and asking again immediately deepens the penalty.

    The subs already read are still returned -- those comments were really
    observed -- but nothing after the refusal is attempted.
    """
    client = FakeClient({
        'a': feed([entry('t1_a', 5)]),
        'b': reddit.RedditThrottled('r/b: 429'),
        'c': feed([entry('t1_c', 5)]),
    })

    since = NOW - dt.timedelta(hours=1)
    result = reddit.fetch({'a': since, 'b': since, 'c': since}, client, pause=0)

    assert client.asked == ['a', 'b']
    assert [p.external_id for p in result.posts] == ['t1_a']
    assert result.per_source_status == {
        'reddit:a': 'ok', 'reddit:b': 'missing'}

    # 'c' was never requested, so it must not be scheduled as though it had
    # been -- it would lose its turn to whatever happened to sort earlier.
    assert 'c' not in result.rates


def test_a_throttled_subreddit_keeps_its_place_rather_than_being_backed_off():
    """Reversed 2026-08-25, after measuring what the 429s actually were.

    This used to report a throttled sub at rate 0.0 -- a deliberate lie,
    reasoned as: recorded honestly it would be the most overdue entry next
    cycle, get tried first, throttle again, and break the cycle before
    anything else was read. Backing it off kept the rotation moving.

    That reasoning assumed the throttle was OUR fault, earned by asking too
    fast. The response headers say otherwise: `x-ratelimit-remaining` is 0.0
    after a single request, so the budget is one feed per window and every
    request after the first in a window is refused no matter how long the
    pause. Whichever subreddit happened to go second was refused -- two runs
    in a row blamed a different sub purely on ordering.

    So a 429 says nothing about the subreddit, and a sub that was refused was
    never read. Backing it off punishes it for its position in a queue, and
    with one request per cycle there is no longer any rotation to protect.
    """
    client = FakeClient({'b': reddit.RedditThrottled('r/b: 429')})

    result = reddit.fetch({'b': NOW - dt.timedelta(hours=1)}, client, pause=0)

    assert 'b' not in result.rates
    # Still `missing`, not `ok`: nothing was observed, and a zero count here
    # would be indistinguishable from a genuinely silent quarter-hour.
    assert result.status == 'missing'


def test_one_feed_per_cycle_because_that_is_the_whole_budget():
    """Measured on the VPS 2026-08-25 against the live endpoint.

    Successes landed at t=0, t=78 and t=198 seconds and refusals at t=19 and
    t=138, alternating regardless of which subreddit was asked. Roughly one
    feed per 90-120s is the sustainable rate, so a cycle asking for three got
    one answer and two 429s -- and the 429 then broke the cycle, which is why
    Reddit ran at about a third of even this budget.
    """
    from features.radar.config import (REDDIT_INTERVAL_SECONDS,
                                       REDDIT_SUBS_PER_CYCLE)

    assert REDDIT_SUBS_PER_CYCLE == 1
    assert REDDIT_INTERVAL_SECONDS >= 90


def test_one_unreachable_sub_does_not_cost_the_others():
    """Unlike a throttle: a single 500 says nothing about the next subreddit,
    so the cycle carries on."""
    client = FakeClient({
        'a': reddit.RedditUnavailable('r/a: HTTP 500'),
        'b': feed([entry('t1_b', 5)]),
    })

    since = NOW - dt.timedelta(hours=1)
    result = reddit.fetch({'a': since, 'b': since}, client, pause=0)

    assert client.asked == ['a', 'b']
    assert [p.external_id for p in result.posts] == ['t1_b']
    assert result.per_source_status == {
        'reddit:a': 'missing', 'reddit:b': 'ok'}
    # Attempted and told nothing. Unknown, not zero -- a 500 says nothing
    # about whether the next request will work, so it is retried soon.
    assert result.rates['a'] is None


def test_a_cycle_that_read_nothing_is_missing_not_ok():
    """`ok` with no posts means a genuinely quiet period, and the rollup
    writes zero counts for it. A cycle where every request failed observed
    nothing at all, which is a different fact."""
    client = FakeClient({'a': reddit.RedditUnavailable('down')})

    result = reddit.fetch({'a': NOW - dt.timedelta(hours=1)}, client, pause=0)

    assert result.status == 'missing'


@pytest.mark.parametrize('statuses,expected', [
    (['ok', 'ok'], 'ok'),
    (['ok', 'truncated'], 'truncated'),
    (['ok', 'missing'], 'truncated'),
    (['missing', 'missing'], 'missing'),
    ([], 'missing'),
])
def test_the_cycle_reports_its_least_complete_contributor(statuses, expected):
    assert reddit._roll_up(statuses) == expected


def test_the_observed_rate_comes_from_the_feed():
    """Feeds the poll scheduler, so a quiet sub falls to a slow cadence and
    hands its share of the request budget to a busy one."""
    client = FakeClient({'x': feed([
        entry('t1_1', 0), entry('t1_2', 30), entry('t1_3', 60)])})

    _posts, _status, rate = reddit.fetch_one('x', NOW - dt.timedelta(days=1), client)

    # Three comments across one hour.
    assert rate == pytest.approx(3.0, abs=0.1)


def test_an_empty_feed_is_quiet_rather_than_broken():
    client = FakeClient({'x': feed([])})

    posts, status, rate = reddit.fetch_one('x', NOW - dt.timedelta(hours=1), client)

    assert posts == [] and status == 'ok' and rate is None


def test_an_unparseable_feed_is_unknown_to_the_scheduler():
    """A bad response was attempted but supplied no rate measurement."""
    client = FakeClient({'x': '<not atom'})

    result = reddit.fetch({'x': NOW - dt.timedelta(hours=1)}, client, pause=0)

    assert result.status == 'missing'
    assert result.rates['x'] is None


def test_every_configured_subreddit_fits_the_column_it_is_stored_in():
    """The bug this suite did not catch, 2026-08-24.

    Reddit reuses the same poll scheduler every polled source shares, with the
    SUBREDDIT as the polled unit, and `radar_poll_state.symbol` was String(12)
    because everything it had ever held was a ticker. Six of the eighteen names are
    longer -- `RobinHoodPennyStocks` is 20 -- so `ensure_tracked` failed the
    whole batch insert on the daemon's first cycle and the source silently
    produced nothing at all.

    Asserted against the column rather than a literal, so widening the column
    moves this test with it and adding a longer subreddit fails here instead
    of in a log at 23:41.
    """
    from features.radar.config import REDDIT_SUBS
    from models import RadarPollState

    limit = RadarPollState.__table__.c.symbol.type.length
    worst = max(REDDIT_SUBS, key=len)

    assert len(worst) <= limit, (
        f'r/{worst} is {len(worst)} chars and the column holds {limit}')


def test_the_channel_column_holds_the_longest_subreddit_too():
    """The other end of the same mistake: the subreddit is also written to
    radar_posts.channel on every single comment."""
    from features.radar.config import REDDIT_SUBS
    from models import RadarPost

    limit = RadarPost.__table__.c.channel.type.length
    worst = max(REDDIT_SUBS, key=len)

    assert len(worst) <= limit, (
        f'r/{worst} is {len(worst)} chars and channel holds {limit}')


def test_each_subreddit_is_read_from_its_own_cursor():
    """The regression, measured live 2026-08-25: six of eight cycles returned
    nothing.

    One cursor per SOURCE is advanced to the newest comment seen across the
    batch, so a busy subreddit moves it to seconds ago and every quieter one
    polled afterwards has its whole feed filtered out as already-seen. Quiet
    subs could never contribute anything, permanently.

    Here r/busy has just posted and r/quiet last spoke an hour ago. Under a
    shared cursor set by r/busy, r/quiet yields nothing.
    """
    client = FakeClient({
        'busy': feed([entry('t1_busy', 1)]),
        'quiet': feed([entry('t1_quiet', 55)]),
    })

    result = reddit.fetch({
        'busy': NOW - dt.timedelta(minutes=5),      # read 5 minutes ago
        'quiet': NOW - dt.timedelta(minutes=90),    # last read 90 minutes ago
    }, client, pause=0)

    got = {p.external_id for p in result.posts}
    assert got == {'t1_busy', 't1_quiet'}, (
        "the quiet subreddit was filtered out by another sub cursor")


def test_all_three_prefixed_source_columns_are_wide_in_model_and_database():
    """The longest configured Reddit name must survive the durable boundary."""
    import sqlalchemy as sa

    from app import app as flask_app
    from extensions import db
    from features.radar.config import REDDIT_SUBS
    from models import RadarBucketSource, RadarPollState, RadarPost

    concrete = max(('reddit:%s' % sub for sub in REDDIT_SUBS), key=len)
    models = (RadarPost, RadarBucketSource, RadarPollState)
    assert {model.__tablename__: model.__table__.c.source.type.length
            for model in models} == {
                'radar_posts': 48,
                'radar_bucket_sources': 48,
                'radar_poll_state': 48,
            }

    external_id = 'zz-task9-longest-source'
    channel = 'zz_task9_source_width'
    with flask_app.app_context():
        inspector = sa.inspect(db.engine)
        live = {
            model.__tablename__: next(
                column['type'].length
                for column in inspector.get_columns(model.__tablename__)
                if column['name'] == 'source')
            for model in models
        }
        assert live == {
            'radar_posts': 48,
            'radar_bucket_sources': 48,
            'radar_poll_state': 48,
        }

        def wipe_owned_post():
            RadarPost.query.filter_by(
                external_id=external_id, channel=channel).delete(
                    synchronize_session=False)
            db.session.commit()

        wipe_owned_post()
        try:
            stamp = dt.datetime(2026, 8, 24, 12, 0, 0)
            db.session.add(RadarPost(
                source=concrete, external_id=external_id, channel=channel,
                author='zz-task9', created_utc=stamp, title=None, body='$AAPL',
                score=0, num_comments=0, url='', simhash=1,
                first_seen=stamp, last_seen=stamp))
            db.session.commit()
            assert RadarPost.query.filter_by(
                source=concrete, external_id=external_id).one().source == concrete
        finally:
            db.session.rollback()
            wipe_owned_post()

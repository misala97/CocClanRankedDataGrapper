# personal_apps/tests/test_radar_detail.py
"""One ticker's panel: the surface that answers "is this real".

The board can honestly say three venues are talking. Only this can show what
each venue said, and what the stock was doing for the three years before
anyone said anything -- which is the part that decides whether a spike is
worth acting on.

The chart tests below moved here from test_radar_board.py on 2026-08-23 when
the chart left the board payload. They are unchanged in substance: price and
chatter share one calendar axis, and the two kinds of gap in them mean
different things.
"""
import datetime as dt
import decimal

import pytest

from app import app as flask_app
from extensions import db
from features.radar import detail, detail_panel
from features.radar.config import source_config_version
from models import (RadarBucketSource, RadarDailyClose, TickerUniverse)

NOW = dt.datetime(2026, 3, 12, 15, 0, 0)
PREFIX = 'DT'
SPAN = detail.SPAN_DAYS['1Y']


@pytest.fixture()
def clean():
    def wipe():
        for model in (RadarBucketSource, RadarDailyClose):
            model.query.filter(model.ticker.like(f'{PREFIX}%')).delete(
                synchronize_session=False)
        TickerUniverse.query.filter(
            TickerUniverse.symbol.like(f'{PREFIX}%')).delete(
                synchronize_session=False)
        db.session.commit()

    with flask_app.app_context():
        wipe()
        yield
        wipe()


def bucket(ticker, minutes_ago=30, mentions=10, source='bluesky'):
    db.session.add(RadarBucketSource(
        ticker=ticker, bucket_start=NOW - dt.timedelta(minutes=minutes_ago),
        source=source, mention_count=mentions, high_confidence_count=mentions,
        low_count=0, distinct_authors=6, distinct_text_ratio=0.9,
        engagement_weighted_count=float(mentions), status='ok',
        source_config_version=source_config_version(),
        expected=1.0, variance=2.0, mention_z=5.0, baseline_days=30))


def close_on(ticker, days_ago, price='10'):
    db.session.add(RadarDailyClose(
        ticker=ticker, close_date=NOW.date() - dt.timedelta(days=days_ago),
        close=decimal.Decimal(price), fetched_at=NOW))


def chart_for(ticker, days=SPAN):
    """Build one chart the way the panel will, from the pieces under test."""
    start = NOW.date() - dt.timedelta(days=days - 1)
    from_dt = dt.datetime.combine(start, dt.time.min)
    stored = {row.close_date: row.close for row in
              RadarDailyClose.query.filter_by(ticker=ticker).all()}
    counts = detail.daily_counts([ticker], ['bluesky'], from_dt, NOW)
    watched = detail.first_watched_day(['bluesky'], from_dt, NOW)
    return detail.chart_for(ticker, start, days, stored, counts, watched)


# ------------------------------------------------------------------ chart ---
#
# Price and chatter on one calendar axis. The alignment is the whole reason
# they are one structure: a year holds ~252 trading days and 365 calendar
# days, so positioning each by its own index would drift them over a hundred
# days apart by December.

def test_the_chart_aligns_price_and_chatter_on_calendar_days(clean):
    bucket(f'{PREFIX}A')
    for offset in (0, 1, 2):
        close_on(f'{PREFIX}A', offset, str(10 + offset))
    db.session.commit()

    chart = chart_for(f'{PREFIX}A')

    assert len(chart.closes) == len(chart.chatter) == SPAN
    assert (NOW.date() - chart.start).days == SPAN - 1
    # Today is the last index of both arrays, so the two line up by date.
    assert float(chart.closes[-1]) == 10.0
    assert chart.chatter[-1] == 10


def test_a_day_the_market_did_not_trade_is_null_not_carried_forward(clean):
    """Null means no trade happened. The client draws the line across it;
    repeating the previous close here would invent a print."""
    bucket(f'{PREFIX}A')
    close_on(f'{PREFIX}A', 3)
    db.session.commit()

    chart = chart_for(f'{PREFIX}A')

    assert chart.closes[-1] is None
    assert float(chart.closes[-4]) == 10.0


def test_days_before_ingest_began_have_no_chatter_at_all(clean):
    """Not zero. We were not watching, and a zero bar would claim a silence we
    never observed -- the same rule the hourly series already follows."""
    bucket(f'{PREFIX}A')
    close_on(f'{PREFIX}A', 0)
    db.session.commit()

    chart = chart_for(f'{PREFIX}A')

    assert chart.chatter[0] is None
    assert chart.chatter[-1] == 10


def test_the_chart_reports_where_watching_began(clean):
    """The panel draws a boundary at this date. Without it, three years of
    price beside three days of chatter reads as three years of silence."""
    bucket(f'{PREFIX}A')
    close_on(f'{PREFIX}A', 0)
    db.session.commit()

    assert chart_for(f'{PREFIX}A').watched_from == NOW.date()


# ------------------------------------------------------------------- spans ---

def test_every_span_is_a_whole_number_of_calendar_days():
    """Indexed by calendar day, never trading day. A year holds ~252 of one
    and 365 of the other."""
    assert detail.SPAN_DAYS == {'1M': 30, '6M': 182, '1Y': 365, '3Y': 1095}


def test_the_longest_span_fits_inside_what_is_stored():
    """3Y draws 1095 calendar days, which is about 780 trading days. Asking
    for more than the store holds would render a truncated year as a complete
    one."""
    from features.radar import history

    assert history.HISTORY_DAYS >= detail.SPAN_DAYS['3Y'] * 252 / 365


def test_a_span_shorter_than_a_year_takes_the_recent_end(clean):
    bucket(f'{PREFIX}A')
    close_on(f'{PREFIX}A', 0, '99')
    close_on(f'{PREFIX}A', 200, '5')
    db.session.commit()

    month = chart_for(f'{PREFIX}A', detail.SPAN_DAYS['1M'])

    assert len(month.closes) == 30
    assert float(month.closes[-1]) == 99.0
    assert all(c is None for c in month.closes[:-1])


# --------------------------------------------------------------- the panel ---

def post_for(ticker, minutes_ago, author, text, source='bluesky', ext=None):
    """One post carrying one scored mention of `ticker`."""
    from models import RadarMention, RadarPost

    when = NOW - dt.timedelta(minutes=minutes_ago)
    post = RadarPost(
        source=source, external_id=ext or f'{PREFIX}-{author}-{minutes_ago}',
        channel='feed', author=author, created_utc=when, title=None,
        body=text, score=0, num_comments=0,
        url=f'https://example.invalid/{author}/{minutes_ago}',
        simhash=abs(hash(text)) % (2 ** 63), first_seen=when, last_seen=when)
    db.session.add(post)
    db.session.flush()
    db.session.add(RadarMention(
        post_id=post.id, ticker=ticker, confidence='high',
        lexicon_sentiment=0.4 if 'moon' in text else 0.0))


@pytest.fixture()
def panel_ticker(clean):
    from models import RadarMention, RadarPost

    RadarMention.query.filter(RadarMention.ticker.like(f'{PREFIX}%')).delete(
        synchronize_session=False)
    RadarPost.query.filter(
        RadarPost.external_id.like(f'{PREFIX}%')).delete(
            synchronize_session=False)
    db.session.add(TickerUniverse(
        symbol=f'{PREFIX}A', name='Detail Corp - Common Stock',
        exchange='NASDAQ', first_seen=dt.datetime(2020, 1, 1),
        market_cap=decimal.Decimal('110000000')))
    bucket(f'{PREFIX}A')
    close_on(f'{PREFIX}A', 0, '12.34')
    for minutes, who, text in ((10, 'alice', 'to the moon'),
                               (20, 'bob', 'looks weak here'),
                               (30, 'alice', 'still holding')):
        post_for(f'{PREFIX}A', minutes, who, text)
    db.session.commit()
    yield
    RadarMention.query.filter(RadarMention.ticker.like(f'{PREFIX}%')).delete(
        synchronize_session=False)
    RadarPost.query.filter(
        RadarPost.external_id.like(f'{PREFIX}%')).delete(
            synchronize_session=False)
    db.session.commit()


def test_an_unknown_ticker_raises_rather_than_inventing_a_panel(clean):
    with pytest.raises(detail.UnknownTicker):
        detail_panel.build(f'{PREFIX}NOPE', ['bluesky'], NOW)


def test_a_bad_span_is_refused(panel_ticker):
    with pytest.raises(ValueError):
        detail_panel.build(f'{PREFIX}A', ['bluesky'], NOW, span='5Y')


def test_the_panel_counts_voices_not_posts(panel_ticker):
    """Three posts from two people is two voices. Counting posts would make
    one determined account look like a crowd -- which is the whole thing the
    breakdown exists to expose."""
    built = detail_panel.build(f'{PREFIX}A', ['bluesky'], NOW)

    assert built.breakdown.mentions == 3
    assert built.breakdown.voices == 2


def test_the_panel_exposes_how_concentrated_the_talk_is(panel_ticker):
    """Alice posted two of three. No other figure on the surface shows that."""
    built = detail_panel.build(f'{PREFIX}A', ['bluesky'], NOW)

    assert abs(built.breakdown.top_author_share - 2 / 3) < 0.01


def test_the_panel_returns_the_posts_themselves(panel_ticker):
    """Newest first, with the link out. This is the zone that lets a reader
    form their own view instead of trusting the score."""
    built = detail_panel.build(f'{PREFIX}A', ['bluesky'], NOW)

    assert built.post_total == 3
    assert built.posts[0].body == 'to the moon'
    assert built.posts[0].url


def test_the_panel_describes_a_ticker_the_board_filtered_out(clean):
    """Reachable by URL for anything in the universe. Refusing to describe a
    ticker because it did not rank is the wrong answer to "tell me about
    this"."""
    db.session.add(TickerUniverse(
        symbol=f'{PREFIX}Q', name='Quiet Corp', exchange='NASDAQ',
        first_seen=dt.datetime(2020, 1, 1)))
    db.session.commit()

    built = detail_panel.build(f'{PREFIX}Q', ['bluesky'], NOW)

    assert built.ticker == f'{PREFIX}Q'
    assert built.breakdown.mentions == 0
    assert built.posts == []


def test_neutral_is_everything_the_lexicon_did_not_score(panel_ticker):
    """Most mentions carry no sentiment word at all. Folding them into one
    percentage would turn a handful of scored posts into a confident-looking
    reading."""
    b = detail_panel.build(f'{PREFIX}A', ['bluesky'], NOW).breakdown

    assert b.bullish + b.neutral + b.bearish == b.mentions
    assert b.neutral == 2


@pytest.fixture()
def panel_live(clean):
    """The same ticker, but anchored to real wall-clock time.

    The route reads `now` from the clock, deliberately -- a time parameter on
    a production endpoint is a way to ask the server for a board that never
    existed. So the fixed-NOW fixture above cannot reach it, and the HTTP
    tests get posts placed minutes before the actual present instead.
    """
    from models import RadarMention, RadarPost

    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    def wipe():
        RadarMention.query.filter(
            RadarMention.ticker.like(f'{PREFIX}%')).delete(
                synchronize_session=False)
        RadarPost.query.filter(
            RadarPost.external_id.like(f'{PREFIX}%')).delete(
                synchronize_session=False)
        for model in (RadarBucketSource, RadarDailyClose):
            model.query.filter(model.ticker.like(f'{PREFIX}%')).delete(
                synchronize_session=False)
        TickerUniverse.query.filter(
            TickerUniverse.symbol.like(f'{PREFIX}%')).delete(
                synchronize_session=False)
        db.session.commit()

    wipe()
    db.session.add(TickerUniverse(
        symbol=f'{PREFIX}A', name='Detail Corp - Common Stock',
        exchange='NASDAQ', first_seen=dt.datetime(2020, 1, 1),
        market_cap=decimal.Decimal('110000000')))
    db.session.add(RadarBucketSource(
        ticker=f'{PREFIX}A', bucket_start=now - dt.timedelta(minutes=30),
        source='bluesky', mention_count=3, high_confidence_count=3,
        low_count=0, distinct_authors=2, distinct_text_ratio=0.9,
        engagement_weighted_count=3.0, status='ok',
        source_config_version=source_config_version(),
        expected=1.0, variance=2.0, mention_z=5.0, baseline_days=30))
    db.session.add(RadarDailyClose(
        ticker=f'{PREFIX}A', close_date=now.date(),
        close=decimal.Decimal('12.34'), fetched_at=now))
    for minutes, who, text in ((10, 'alice', 'to the moon'),
                               (20, 'bob', 'looks weak here'),
                               (30, 'alice', 'still holding')):
        when = now - dt.timedelta(minutes=minutes)
        post = RadarPost(
            source='bluesky', external_id=f'{PREFIX}-live-{minutes}',
            channel='feed', author=who, created_utc=when, title=None,
            body=text, score=0, num_comments=0,
            url=f'https://example.invalid/{who}/{minutes}',
            simhash=abs(hash(text)) % (2 ** 63), first_seen=when,
            last_seen=when)
        db.session.add(post)
        db.session.flush()
        db.session.add(RadarMention(
            post_id=post.id, ticker=f'{PREFIX}A', confidence='high',
            lexicon_sentiment=0.4 if 'moon' in text else 0.0))
    db.session.commit()
    yield
    wipe()


# ------------------------------------------------------------ the endpoint ---

def test_the_endpoint_requires_login(anon_client):
    assert anon_client.get('/radar/api/ticker/AAPL').status_code in (302, 401, 403)


def test_the_endpoint_404s_on_a_ticker_that_does_not_exist(client):
    """A URL can name anything. That is a 404, not a 500."""
    assert client.get(f'/radar/api/ticker/{PREFIX}NOPE').status_code == 404


def test_a_bad_span_is_rejected(client, panel_live):
    assert client.get(
        f'/radar/api/ticker/{PREFIX}A?span=nonsense').status_code == 400


def test_the_endpoint_answers_with_every_zone(client, panel_live):
    """Five zones. A missing key here is a blank section of the panel rather
    than an error, which is how the board's chart serializer went missing for
    a day without a single test noticing."""
    import json

    body = json.loads(client.get(f'/radar/api/ticker/{PREFIX}A').data)

    for key in ('identity', 'read', 'chart', 'breakdown', 'posts',
                'post_total'):
        assert key in body, key
    assert body['identity']['ticker'] == f'{PREFIX}A'
    assert body['read'], 'the written read is empty'
    assert all({'kind', 'text'} == set(c) for c in body['read'])
    assert len(body['chart']['closes']) == len(body['chart']['chatter'])
    assert body['posts'][0]['url']


def test_the_span_reaches_the_chart_through_the_url(client, panel_live):
    import json

    month = json.loads(
        client.get(f'/radar/api/ticker/{PREFIX}A?span=1M').data)
    longest = json.loads(
        client.get(f'/radar/api/ticker/{PREFIX}A?span=3Y').data)

    assert len(month['chart']['closes']) == detail.SPAN_DAYS['1M']
    assert len(longest['chart']['closes']) == detail.SPAN_DAYS['3Y']


def test_the_ticker_is_matched_case_insensitively(client, panel_live):
    """A bookmarked ?t=howl should not 404 because of its case."""
    assert client.get(
        f'/radar/api/ticker/{PREFIX.lower()}a').status_code == 200

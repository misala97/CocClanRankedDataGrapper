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
from models import (RadarBucketSource, RadarDailyClose, RadarInstrument,
                    RadarQuote, TickerUniverse)

NOW = dt.datetime(2026, 3, 12, 15, 0, 0)
PREFIX = 'DT'


class _Quote:
    """Only the four fields the chart reads off a quote view.

    intraday_chart_for takes the whole quote since 2026-09-05: the week's
    price line comes from whichever of the ticker's listings has depth, and
    a (market, mic) pair cannot answer that question.
    """

    def __init__(self, market='us', mic=None, venue='NYSE', currency='USD'):
        self.market = market
        self.mic = mic
        self.venue = venue
        self.currency = currency


US_QUOTE = _Quote()
SPAN = detail.SPAN_DAYS['1Y']


@pytest.fixture()
def clean():
    def wipe():
        for model in (RadarBucketSource, RadarDailyClose, RadarQuote,
                      RadarInstrument):
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

def post_for(ticker, minutes_ago, author, text, source='bluesky', ext=None,
             llm_sentiment=None, attitude=None, relevance=None, origin=None):
    """One post carrying one scored mention of `ticker`.

    `llm_sentiment` defaults to None (no verdict yet, the common case);
    passing 'bullish'/'bearish'/'unclear' lets a test drive the legacy side
    of `_tone_of` against a real row. The v2 fields (attitude, relevance,
    origin) mark the mention as judged when any is given.
    """
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
    judged = attitude is not None or relevance is not None or origin is not None
    db.session.add(RadarMention(
        post_id=post.id, ticker=ticker, confidence='high',
        lexicon_sentiment=0.4 if 'moon' in text else 0.0,
        llm_sentiment=llm_sentiment,
        sentiment_attitude=attitude,
        sentiment_relevance=relevance or ('relevant' if judged else None),
        sentiment_content_origin=origin or ('human_chatter' if judged else None),
        sentiment_judged_at=when if judged else None))


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
    post, tone, _judged_by = built.posts[0]
    assert post.body == 'to the moon'
    assert post.url
    # The fixture's newest post carries a locally-bullish float and no
    # judgment: the per-post tone mirrors the tallies' read.
    assert tone == 'bullish'


def test_each_post_carries_the_tone_the_tallies_use(panel_ticker):
    post_for(f'{PREFIX}A', 1, 'nils', 'to the moon',
             ext=f'{PREFIX}-tone-neg', attitude='negative')
    post_for(f'{PREFIX}A', 2, 'olaf', 'to the moon',
             ext=f'{PREFIX}-tone-none', attitude='none')
    db.session.commit()

    built = detail_panel.build(f'{PREFIX}A', ['bluesky'], NOW)
    tones = {post.external_id: tone for post, tone, _judged_by in built.posts}

    assert tones[f'{PREFIX}-tone-neg'] == 'bearish'    # attitude beats local
    assert tones[f'{PREFIX}-tone-none'] == 'neutral'   # decided, undirected


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


def test_the_breakdown_counts_real_disagreements_not_just_the_tone_helper(
        panel_ticker):
    """`test_the_breakdown_prefers_the_model_verdict_over_the_lexicon` above
    only drives `_tone_of` directly -- the pure function. Nothing before this
    test ran the counting LOOP in `breakdown_for` (the thing Task 14 actually
    built) against real rows with a genuine lexicon/model disagreement:
    replacing that loop's condition with `if False:` left all 69 tests in
    this file and test_radar_api.py green (fix-round-1 review, finding I2).

    Three rows, one real disagreement:
      - 'to the moon' (lexicon bullish) scored 'bearish' by the model: the
        model outranks and reverses the read -> counted.
      - 'to the moon' (lexicon bullish) scored 'bullish': they agree -> not
        counted.
      - 'still holding' (lexicon carried no directional word) scored
        'bullish': the lexicon never took a side, so there is nothing to
        disagree WITH -> not counted, even though the model's tone differs
        from the row's final tone.
    """
    post_for(f'{PREFIX}A', 5, 'frank', 'to the moon',
             ext=f'{PREFIX}-disagree-reversed', llm_sentiment='bearish')
    post_for(f'{PREFIX}A', 6, 'grace', 'to the moon',
             ext=f'{PREFIX}-disagree-agrees', llm_sentiment='bullish')
    post_for(f'{PREFIX}A', 7, 'heidi', 'still holding',
             ext=f'{PREFIX}-disagree-no-lexicon-side', llm_sentiment='bullish')
    db.session.commit()

    b = detail_panel.build(f'{PREFIX}A', ['bluesky'], NOW).breakdown

    assert b.disagreements == 1


def test_confirmed_non_chatter_leaves_the_breakdown_and_the_post_list(
        panel_ticker):
    """Spec §7.2 on the panel: a confirmed irrelevant or broadcast mention
    vanishes from the tallies AND from the sample-post list -- calling it
    neutral would fix the color while leaving the spike false. `uncertain`
    stays provisional and visible."""
    post_for(f'{PREFIX}A', 5, 'ivan', 'to the moon',
             ext=f'{PREFIX}-elig-keep', attitude='positive')
    post_for(f'{PREFIX}A', 6, 'judy', 'to the moon',
             ext=f'{PREFIX}-elig-irrelevant', attitude='none',
             relevance='irrelevant')
    post_for(f'{PREFIX}A', 7, 'karl', 'price feed says up',
             ext=f'{PREFIX}-elig-broadcast', attitude='positive',
             origin='broadcast_or_automated')
    post_for(f'{PREFIX}A', 8, 'lena', 'to the moon',
             ext=f'{PREFIX}-elig-uncertain', attitude='positive',
             relevance='uncertain')
    db.session.commit()

    panel = detail_panel.build(f'{PREFIX}A', ['bluesky'], NOW)
    b = panel.breakdown

    # panel_ticker seeds 3 posts (one locally bullish); on top of those,
    # keep + uncertain count while the two excluded rows vanish.
    assert b.mentions == 5
    assert b.bullish == 3
    posts = {p.external_id for p, _tone, _judged_by in panel.posts}
    assert f'{PREFIX}-elig-keep' in posts
    assert f'{PREFIX}-elig-uncertain' in posts
    assert f'{PREFIX}-elig-irrelevant' not in posts
    assert f'{PREFIX}-elig-broadcast' not in posts


def test_a_v2_attitude_drives_the_breakdown_tone(panel_ticker):
    post_for(f'{PREFIX}A', 5, 'mia', 'to the moon',
             ext=f'{PREFIX}-att-neg', llm_sentiment='bullish',
             attitude='negative')
    db.session.commit()

    b = detail_panel.build(f'{PREFIX}A', ['bluesky'], NOW).breakdown

    # The fixture's own locally-bullish post is the 1; the new row's
    # legacy 'bullish' is overridden by attitude='negative'.
    assert (b.bullish, b.bearish) == (1, 1)


# ------------------------------------------------- pre-split root history ---
#
# Before 2026-08-26 every Reddit observation was stored under the bare name
# `reddit`. This chart's default span is 1Y and buckets are retained forever,
# so most of what it draws for Reddit is under that older name.


def test_window_figures_exclude_pre_split_root_reddit_scores():
    ticker = 'ZZM2DETAIL'

    def clear():
        RadarBucketSource.query.filter_by(ticker=ticker).delete(
            synchronize_session=False)
        db.session.commit()

    with flask_app.app_context():
        clear()
        try:
            when = NOW - dt.timedelta(minutes=30)
            for source, mentions, expected, baseline_days, version in (
                    ('reddit:pennystocks', 5, 1.0, 12.0,
                     source_config_version()),
                    ('reddit', 1001, 901.0, 1.0, '8106787f1fa72179')):
                db.session.add(RadarBucketSource(
                    ticker=ticker, bucket_start=when, source=source,
                    mention_count=mentions, high_confidence_count=mentions,
                    low_count=0, distinct_authors=5,
                    distinct_text_ratio=1.0,
                    engagement_weighted_count=float(mentions), status='ok',
                    source_config_version=version, expected=expected,
                    variance=4.0, mention_z=2.0,
                    baseline_days=baseline_days))
            db.session.commit()

            figures = detail_panel.window_figures(
                ticker, ['reddit'], NOW - dt.timedelta(hours=1), NOW)

            assert figures == (5, 1.0, 12.0)
        finally:
            clear()

def _old_root_bucket(ticker, days_ago, mentions):
    """A bucket row exactly as production wrote it before the split."""
    db.session.add(RadarBucketSource(
        ticker=ticker,
        bucket_start=dt.datetime.combine(
            NOW.date() - dt.timedelta(days=days_ago), dt.time(12, 0)),
        source='reddit', mention_count=mentions,
        high_confidence_count=mentions, low_count=0, distinct_authors=6,
        distinct_text_ratio=0.9, engagement_weighted_count=float(mentions),
        # The real pre-split stamp, 16 hex characters -- which is also the
        # column's whole width, so a descriptive placeholder does not fit.
        status='ok', source_config_version='8106787f1fa72179',
        expected=1.0, variance=2.0, mention_z=9.9, baseline_days=30))


def test_the_chart_still_draws_the_pre_split_reddit_history(clean):
    """A 1Y span reaches back past the subreddit split.

    Dropping those rows would not draw a gap: `first_watched_day` is
    satisfied by the days after the split, so the earlier days are marked
    watched and drawn as zeroes -- an absence rendered as a measurement.
    """
    db.session.add(TickerUniverse(
        symbol=f'{PREFIX}H', name='History Corp', exchange='NASDAQ',
        first_seen=dt.datetime(2020, 1, 1)))
    _old_root_bucket(f'{PREFIX}H', days_ago=200, mentions=7)
    db.session.commit()

    start = NOW.date() - dt.timedelta(days=SPAN - 1)
    from_dt = dt.datetime.combine(start, dt.time.min)
    counts = detail.daily_counts([f'{PREFIX}H'], ['reddit'], from_dt, NOW)
    watched = detail.first_watched_day(['reddit'], from_dt, NOW)

    assert counts[(f'{PREFIX}H', NOW.date() - dt.timedelta(days=200))] == 7
    assert watched == NOW.date() - dt.timedelta(days=200)


def test_the_breakdown_still_shows_one_reddit_row(panel_ticker):
    """Task 9 changed the POPULATION, not the presentation.

    Splitting the source name is how one sub's feed rollover stops marking
    every other sub truncated. It is not a decision to put subreddits on the
    surface -- so the venue table keeps the single pooled `Reddit` row it had
    before, with one voices count and one share of mentions, and the
    pre-split root rows pool into it as well. Fragmenting it into eight rows
    would be its own product call, worth making deliberately rather than
    inheriting from a storage change.
    """
    post_for(f'{PREFIX}A', 40, 'carol', 'wsb says moon',
             source='reddit:wallstreetbets')
    post_for(f'{PREFIX}A', 50, 'dave', 'penny says moon',
             source='reddit:pennystocks')
    post_for(f'{PREFIX}A', 60, 'erin', 'older reddit view', source='reddit')
    db.session.commit()

    b = detail_panel.build(f'{PREFIX}A', ['bluesky', 'reddit'], NOW).breakdown
    venues = {v.source: (v.mentions, v.voices) for v in b.venues}

    assert set(venues) == {'bluesky', 'reddit'}
    assert venues['reddit'] == (3, 3)


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


# --- Intraday spans, added 2026-08-25 ---------------------------------------
#
# 1D and 1W cannot be more entries in SPAN_DAYS. That chart is indexed by
# CALENDAR DAY, so a one-day span is a single point and a week is seven -- a
# chart with nothing in it. They need their own granularity: slots of minutes
# rather than days, priced from radar_quotes rather than radar_daily_closes.

def quote(ticker, minutes_ago, price):
    from models import RadarQuote
    db.session.add(RadarQuote(
        ticker=ticker, fetched_at=NOW - dt.timedelta(minutes=minutes_ago),
        quote_ts=NOW - dt.timedelta(minutes=minutes_ago),
        price=decimal.Decimal(str(price))))


@pytest.fixture()
def clean_intraday(clean):
    from models import RadarQuote
    with flask_app.app_context():
        RadarQuote.query.filter(
            RadarQuote.ticker.like(f'{PREFIX}%')).delete(
                synchronize_session=False)
        db.session.commit()
        yield
        RadarQuote.query.filter(
            RadarQuote.ticker.like(f'{PREFIX}%')).delete(
                synchronize_session=False)
        db.session.commit()


def test_the_intraday_spans_are_slots_of_minutes_not_days():
    slots, step = detail.INTRADAY_SPANS['1D']
    assert slots * step == 24 * 60

    slots, step = detail.INTRADAY_SPANS['1W']
    assert slots * step == 7 * 24 * 60


def test_a_days_chart_has_one_slot_per_bucket():
    """15 minutes, matching the bucket grain exactly.

    Anything coarser would re-aggregate what the rollup already decided;
    anything finer would invent resolution the chatter does not have.
    """
    from features.radar.config import BUCKET_MINUTES

    _slots, step = detail.INTRADAY_SPANS['1D']
    assert step == BUCKET_MINUTES


def test_price_comes_from_quotes_not_daily_closes(clean_intraday):
    """A daily close is one point a day. An intraday line needs the 5-minute
    snapshots, which is the only intraday price this system stores."""
    with flask_app.app_context():
        quote(f'{PREFIX}A', minutes_ago=10, price=4.25)
        db.session.commit()

        chart = detail.intraday_chart_for(f'{PREFIX}A', ['bluesky'], NOW, '1D', quote=US_QUOTE)

        assert any(c is not None for c in chart.closes)
        assert chart.closes[-1] == pytest.approx(4.25)


def test_one_quote_in_the_day_falls_back_to_daily_closes(clean_intraday):
    """A single quote cannot draw a 1D line, but daily anchors can."""
    from features.radar import detail as detail_mod

    assert detail_mod.MIN_INTRADAY_POINTS == 2
    ticker = f'{PREFIX}THIN'
    with flask_app.app_context():
        quote(ticker, minutes_ago=10, price=4.25)
        close_on(ticker, 1, '4.00')
        close_on(ticker, 2, '3.75')
        db.session.commit()

        chart = detail.intraday_chart_for(
            ticker, ['bluesky'], NOW, '1D', quote=US_QUOTE)

        assert chart.priced_from == 'daily'
        assert 4.00 in [price for price in chart.closes if price is not None]
        assert len([price for price in chart.closes if price is not None]) >= 2


def test_rejected_daily_anchors_keep_intraday_quote_provenance(clean_intraday):
    """A thin foreign basis must not relabel the surviving native quote."""
    ticker = f'{PREFIX}REJECT'
    quote_view = _Quote('de', 'XGAT', 'Tradegate BSX', 'EUR')
    with flask_app.app_context():
        db.session.add_all([
            RadarInstrument(
                ticker=ticker, market='de', venue='Tradegate BSX',
                mic='XGAT', provider_symbol='ZZTG', currency='EUR',
                isin='DE000ZZTST06', is_primary=True,
                mapping_status='mapped', mapped_at=NOW),
            RadarInstrument(
                ticker=ticker, market='de', venue='Xetra', mic='XETR',
                provider_symbol='ZZXE', currency='EUR',
                isin='DE000ZZTST06', is_primary=False,
                mapping_status='mapped', mapped_at=NOW),
            RadarQuote(
                ticker=ticker, market='de', mic='XGAT', currency='EUR',
                fetched_at=NOW - dt.timedelta(minutes=10),
                quote_ts=NOW - dt.timedelta(minutes=10),
                price=decimal.Decimal('99.00')),
        ])
        for back, price in ((1, '42.50'), (2, '41.00')):
            db.session.add(RadarDailyClose(
                ticker=ticker, market='de', mic='XETR', currency='EUR',
                close_date=NOW.date() - dt.timedelta(days=back),
                close=decimal.Decimal(price), fetched_at=NOW,
                source='yahoo_chart', adjustment_basis='split',
                is_shadow=False))
        db.session.commit()

        chart = detail.intraday_chart_for(
            ticker, ['bluesky'], NOW, '1D', quote=quote_view)

        assert chart.priced_from == 'intraday'
        assert 99.0 in [price for price in chart.closes if price is not None]
        assert chart.basis_venue == 'Tradegate BSX'
        assert chart.converted_from is None


def test_the_1d_chart_reports_where_its_line_came_from(client, panel_live):
    """The panel's 1D provenance makes a sparse line honest to its reader."""
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    with flask_app.app_context():
        for minutes_ago, price in ((10, '12.50'), (30, '12.00')):
            db.session.add(RadarQuote(
                ticker=f'{PREFIX}A', fetched_at=now - dt.timedelta(minutes=minutes_ago),
                quote_ts=now - dt.timedelta(minutes=minutes_ago),
                price=decimal.Decimal(price)))
        db.session.commit()

    response = client.get(f'/radar/api/ticker/{PREFIX}A?span=1D')

    assert response.status_code == 200
    chart = response.get_json()['chart']
    real = [close for close in chart['closes'] if close is not None]
    assert chart['priced_from'] == 'intraday'
    assert len(real) >= 2


def test_a_german_intraday_chart_never_splices_usd_quote_history(clean_intraday):
    """Germany with no Xetra print is not a USD chart with a German label."""
    from models import RadarQuote

    with flask_app.app_context():
        db.session.add(RadarQuote(
            ticker=f'{PREFIX}A', market='us', mic='XNAS', currency='USD',
            fetched_at=NOW - dt.timedelta(minutes=10),
            quote_ts=NOW - dt.timedelta(minutes=10),
            price=decimal.Decimal('4.25')))
        db.session.commit()

        chart = detail.intraday_chart_for(
            f'{PREFIX}A', ['bluesky'], NOW, '1D',
            quote=_Quote('de', 'XETR', 'Xetra', 'EUR'))

        assert all(price is None for price in chart.closes)


def test_germany_detail_marks_us_fallback_and_uses_its_us_history(clean):
    """A fallback has a US quote and history, never an empty EUR-labelled splice."""
    ticker = f'{PREFIX}FALLBACK'
    with flask_app.app_context():
        db.session.add(TickerUniverse(
            symbol=ticker, name='Fallback Corp', exchange='Nasdaq',
            first_seen=NOW, market_cap=decimal.Decimal('100000000')))
        db.session.add(RadarQuote(
            ticker=ticker, market='us', mic='XNAS', currency='USD',
            fetched_at=NOW - dt.timedelta(minutes=5),
            quote_ts=NOW - dt.timedelta(minutes=5),
            price=decimal.Decimal('4.25'), prev_close=decimal.Decimal('4.00')))
        # Two closes: a single stored close is a dot, and the basis refuses
        # to draw a dot as a price line (history.MIN_BASIS_CLOSES).
        for back, price in ((0, '4.25'), (1, '4.10')):
            db.session.add(RadarDailyClose(
                ticker=ticker, market='us', mic='XNAS', currency='USD',
                close_date=NOW.date() - dt.timedelta(days=back),
                close=decimal.Decimal(price), fetched_at=NOW))
        db.session.commit()

        built = detail_panel.build(ticker, ['bluesky'], NOW, span='1M', market='de')

        assert built.market == 'de'
        assert built.quote.is_fallback is True
        assert built.quote.currency == 'USD'
        assert built.chart.closes[-1] == decimal.Decimal('4.25')
        # A US-fallback quote is USD, so its history is USD too -- never
        # converted, and never labelled as anything but its own venue.
        assert built.chart.currency == 'USD'
        assert built.chart.converted_from is None


def test_a_slot_with_no_quote_is_none_rather_than_the_last_price(clean_intraday):
    """Carrying the previous price forward would draw a flat line through a
    stretch nobody priced, which is the same lie as a zero for chatter nobody
    observed. The renderer already spans price gaps; it must be told they ARE
    gaps."""
    with flask_app.app_context():
        quote(f'{PREFIX}A', minutes_ago=10, price=4.25)
        db.session.commit()

        chart = detail.intraday_chart_for(f'{PREFIX}A', ['bluesky'], NOW, '1D', quote=US_QUOTE)

        assert chart.closes[0] is None


def test_the_last_quote_in_a_slot_wins(clean_intraday):
    """Quotes land every five minutes and a slot is fifteen. The slot's price
    is where it ended, the same convention a daily close follows."""
    with flask_app.app_context():
        quote(f'{PREFIX}A', minutes_ago=14, price=4.00)
        quote(f'{PREFIX}A', minutes_ago=6, price=4.50)
        db.session.commit()

        chart = detail.intraday_chart_for(f'{PREFIX}A', ['bluesky'], NOW, '1D', quote=US_QUOTE)

        assert chart.closes[-1] == pytest.approx(4.50)


def test_chatter_is_summed_into_its_slot(clean_intraday):
    with flask_app.app_context():
        bucket(f'{PREFIX}A', minutes_ago=10, mentions=7)
        db.session.commit()

        chart = detail.intraday_chart_for(f'{PREFIX}A', ['bluesky'], NOW, '1D', quote=US_QUOTE)

        assert chart.chatter[-1] == 7


def test_a_week_pools_several_buckets_into_one_slot(clean_intraday):
    """1W slots are an hour, and buckets are fifteen minutes. Four of them
    land in one slot and must add up rather than overwrite."""
    with flask_app.app_context():
        for minutes in (5, 20, 35, 50):
            bucket(f'{PREFIX}A', minutes_ago=minutes, mentions=3)
        db.session.commit()

        chart = detail.intraday_chart_for(f'{PREFIX}A', ['bluesky'], NOW, '1W', quote=US_QUOTE)

        assert chart.chatter[-1] == 12


def test_a_week_uses_native_quote_prints_without_a_daily_basis(
        clean_intraday):
    """Native prints still draw a week when no daily line qualifies."""
    ticker = f'{PREFIX}WPRINT'
    with flask_app.app_context():
        quote(ticker, minutes_ago=24 * 60, price=4.25)
        db.session.commit()

        chart = detail.intraday_chart_for(
            ticker, ['bluesky'], NOW, '1W', quote=US_QUOTE)

        assert 4.25 in [price for price in chart.closes
                        if price is not None]


def test_a_week_anchors_an_xgat_primary_from_its_verified_xetra_sibling(
        clean_intraday):
    """The week chart consumes the same basis the month chart does.

    It used to consume the exact-ISIN Xetra SEAM, which filled only the days
    before the first native Tradegate close. There is no seam now: the
    sibling wins the basis whole when it has the depth, and the chart says
    which venue that was.
    """
    ticker = f'{PREFIX}WPROXY'
    with flask_app.app_context():
        db.session.add_all([
            RadarInstrument(
                ticker=ticker, market='de', venue='Tradegate BSX',
                mic='XGAT', provider_symbol='ZZTG', currency='EUR',
                isin='DE000ZZTST05', is_primary=True,
                mapping_status='mapped', mapped_at=NOW),
            RadarInstrument(
                ticker=ticker, market='de', venue='Xetra', mic='XETR',
                provider_symbol='ZZXE', currency='EUR',
                isin='DE000ZZTST05', is_primary=False,
                mapping_status='mapped', mapped_at=NOW),
        ])
        # Two closes, not one: one stored close is a dot, and the basis
        # refuses to call a dot a price line (history.MIN_BASIS_CLOSES).
        for back, price in ((1, '42.50'), (2, '41.00')):
            db.session.add(RadarDailyClose(
                ticker=ticker, market='de', mic='XETR', currency='EUR',
                close_date=NOW.date() - dt.timedelta(days=back),
                close=decimal.Decimal(price), fetched_at=NOW,
                source='yahoo_chart', adjustment_basis='split',
                is_shadow=False))
        # A real Tradegate print must not leak into a chart whose selected
        # basis is Xetra. The chart's venue label and prices stay one claim.
        db.session.add(RadarQuote(
            ticker=ticker, market='de', mic='XGAT', currency='EUR',
            fetched_at=NOW - dt.timedelta(days=1, hours=3),
            quote_ts=NOW - dt.timedelta(days=1, hours=3),
            price=decimal.Decimal('99.00')))
        db.session.commit()

        chart = detail.intraday_chart_for(
            ticker, ['bluesky'], NOW, '1W',
            quote=_Quote('de', 'XGAT', 'Tradegate BSX', 'EUR'))

        prices = [price for price in chart.closes if price is not None]
        assert 42.5 in prices
        assert 41.0 in prices
        assert 99.0 not in prices
        assert chart.basis_venue == 'Xetra'
        assert chart.currency == 'EUR'
        assert chart.converted_from is None


def test_a_slot_before_observation_began_is_unknown_not_zero(clean_intraday):
    """The rule the daily chart already follows, and the reason chatter is
    nullable at all: a slot nobody was watching is not a slot with no
    mentions."""
    with flask_app.app_context():
        bucket(f'{PREFIX}A', minutes_ago=10, mentions=7)
        db.session.commit()

        chart = detail.intraday_chart_for(f'{PREFIX}A', ['bluesky'], NOW, '1D', quote=US_QUOTE)

        assert chart.chatter[0] is None


@pytest.fixture()
def clean_intraday_gap():
    """Own only the rows used to prove an interior coverage gap."""
    ticker = 'DTGAP12'

    def wipe():
        RadarBucketSource.query.filter_by(ticker=ticker).delete(
            synchronize_session=False)
        db.session.commit()

    with flask_app.app_context():
        wipe()
        yield ticker
        wipe()


def test_an_outage_in_the_middle_of_the_window_is_not_drawn_as_quiet(
        clean_intraday_gap):
    """Coverage is per slot, so a resumed daemon cannot fill a gap with zero."""
    now = dt.datetime(2026, 4, 15, 16, 0, 0)
    first = dt.datetime(2026, 4, 15, 14, 0, 0)
    last = dt.datetime(2026, 4, 15, 15, 0, 0)
    db.session.add_all([
        RadarBucketSource(
            ticker=clean_intraday_gap, bucket_start=first, source='bluesky',
            mention_count=3, high_confidence_count=3, low_count=0,
            distinct_authors=3, distinct_text_ratio=1.0,
            engagement_weighted_count=3.0, status='ok',
            source_config_version=source_config_version()),
        RadarBucketSource(
            ticker=clean_intraday_gap, bucket_start=last, source='bluesky',
            mention_count=0, high_confidence_count=0, low_count=0,
            distinct_authors=0, distinct_text_ratio=0.0,
            engagement_weighted_count=0.0, status='truncated',
            source_config_version=source_config_version()),
    ])
    db.session.commit()

    chart = detail.intraday_chart_for(
        clean_intraday_gap, ['bluesky'], now, '1D', quote=US_QUOTE)
    first_index = detail._slot_index(first, chart.start, chart.step_minutes,
                                     len(chart.chatter))
    last_index = detail._slot_index(last, chart.start, chart.step_minutes,
                                    len(chart.chatter))

    assert chart.chatter[first_index] == 3
    assert chart.chatter[last_index] == 0
    assert all(value is None for value in chart.chatter[first_index + 1:last_index])
    assert chart.watched_from == first


def test_the_chart_reports_its_own_granularity(clean_intraday):
    """The renderer draws evenly spaced slots and cannot tell minutes from
    days. Without this it would label a 24-hour chart with month names."""
    with flask_app.app_context():
        db.session.commit()

        day = detail.intraday_chart_for(f'{PREFIX}A', ['bluesky'], NOW, '1D', quote=US_QUOTE)
        week = detail.intraday_chart_for(f'{PREFIX}A', ['bluesky'], NOW, '1W', quote=US_QUOTE)

        assert day.step_minutes == 15
        assert week.step_minutes == 60


def test_a_daily_chart_still_reports_a_days_step(clean):
    """Same field on both, so the renderer has one rule rather than a special
    case keyed on the span name."""
    with flask_app.app_context():
        chart = detail.chart_for(f'{PREFIX}A', NOW.date(), 3, {}, {}, None)

        assert chart.step_minutes == 1440


def test_the_breakdown_tone_precedence_is_attitude_legacy_local():
    """Spec §7.1: attitude first, the legacy projection next, the local
    float last -- and every decided non-directional read blocks the
    fallbacks below it."""
    from features.radar import detail_panel

    # attitude outranks everything, including a contradicting legacy verdict
    assert detail_panel._tone_of(0.8, 'bullish', 'negative') == 'bearish'
    assert detail_panel._tone_of(-0.8, None, 'positive') == 'bullish'
    # decided mixed/none blocks legacy AND local
    assert detail_panel._tone_of(0.8, 'bullish', 'none') is None
    assert detail_panel._tone_of(0.8, 'bullish', 'mixed') is None
    # NULL attitude falls back to the legacy projection
    assert detail_panel._tone_of(0.8, 'bearish', None) == 'bearish'
    assert detail_panel._tone_of(0.8, 'unclear', None) is None
    # NULL both falls back to the local float
    assert detail_panel._tone_of(0.8, None, None) == 'bullish'
    assert detail_panel._tone_of(None, None, None) is None


# --- [A3] 1D chart slots by provider event time (plan Task 8 Step 8c) --------

def _stale_repeat(ticker, event_age_hours, poll_minutes):
    """One old print re-stored by several later polls with fresh fetch times."""
    from models import RadarQuote
    event_ts = NOW - dt.timedelta(hours=event_age_hours)
    for minutes_ago in poll_minutes:
        db.session.add(RadarQuote(
            ticker=ticker, fetched_at=NOW - dt.timedelta(minutes=minutes_ago),
            quote_ts=event_ts, price=decimal.Decimal('7.77')))


def test_an_out_of_span_print_refetched_all_day_draws_zero_slots(
        clean_intraday):
    """The stale-repeat disease: a 46-hour-old print re-fetched every five
    minutes used to draw as a fresh flat line, because slots were keyed by
    fetch receipt. Slotting by event time makes the truth visible: the
    event predates the 1D span, so nothing is drawn."""
    with flask_app.app_context():
        _stale_repeat(f'{PREFIX}STL', event_age_hours=46,
                      poll_minutes=(50, 40, 30, 20, 10))
        db.session.commit()
        chart = detail.intraday_chart_for(f'{PREFIX}STL', ['bluesky'], NOW,
                                          '1D', quote=US_QUOTE)
        assert all(c is None for c in chart.closes)


def test_an_in_span_print_refetched_occupies_exactly_one_slot(clean_intraday):
    with flask_app.app_context():
        _stale_repeat(f'{PREFIX}ONE', event_age_hours=2,
                      poll_minutes=(50, 40, 30))
        db.session.commit()
        chart = detail.intraday_chart_for(f'{PREFIX}ONE', ['bluesky'], NOW,
                                          '1D', quote=US_QUOTE)
        populated = [index for index, c in enumerate(chart.closes)
                     if c is not None]
        assert len(populated) == 1
        slots, step = detail.INTRADAY_SPANS['1D']
        # Window is [now-24h, now); an event 2h before now sits at
        # (22h * 60) / step from the window start.
        expected_index = (22 * 60) // step
        assert populated == [expected_index]


def test_equal_prices_at_distinct_event_times_remain_distinct(clean_intraday):
    from models import RadarQuote
    with flask_app.app_context():
        for hours_ago in (3, 1):
            db.session.add(RadarQuote(
                ticker=f'{PREFIX}EQ',
                fetched_at=NOW - dt.timedelta(minutes=5),
                quote_ts=NOW - dt.timedelta(hours=hours_ago),
                price=decimal.Decimal('5.55')))
        db.session.commit()
        chart = detail.intraday_chart_for(f'{PREFIX}EQ', ['bluesky'], NOW,
                                          '1D', quote=US_QUOTE)
        populated = [c for c in chart.closes if c is not None]
        assert len(populated) == 2


def test_a_quote_without_provider_time_never_reaches_the_1d_chart(
        clean_intraday):
    from models import RadarQuote
    with flask_app.app_context():
        db.session.add(RadarQuote(
            ticker=f'{PREFIX}NOTS',
            fetched_at=NOW - dt.timedelta(minutes=5),
            quote_ts=None, price=decimal.Decimal('9.99')))
        db.session.commit()
        chart = detail.intraday_chart_for(f'{PREFIX}NOTS', ['bluesky'], NOW,
                                          '1D', quote=US_QUOTE)
        assert all(c is None for c in chart.closes)


def test_each_post_says_who_judged_it(clean):
    """The label follows the same precedence as the tone, so it can never
    disagree with the colour: model for a v2 attitude or a legacy label
    (a decided neutral included), lexicon for the local float alone, and
    nothing when nothing has scored the mention."""
    from features.radar import detail_panel
    from models import RadarMention, RadarPost
    ticker = f'{PREFIX}J'
    post_for(ticker, 10, 'ann', 'to the moon', attitude='positive')           # model, bullish
    post_for(ticker, 20, 'bob', 'meh', attitude='none')                        # model, neutral
    post_for(ticker, 30, 'cy', 'looks weak', llm_sentiment='bearish')          # model (legacy)
    post_for(ticker, 40, 'dee', 'to the moon again')                           # lexicon, bullish
    post_for(ticker, 50, 'eve', 'nothing has scored this yet')                 # nothing at all
    unscored = (db.session.query(RadarMention)
                .join(RadarPost, RadarPost.id == RadarMention.post_id)
                .filter(RadarMention.ticker == ticker, RadarPost.author == 'eve').one())
    unscored.lexicon_sentiment = None      # post_for always scores; undo that here
    db.session.commit()

    posts, total = detail_panel._posts(ticker, ['bluesky'], NOW - dt.timedelta(hours=2), NOW)

    assert total == 5
    by_author = {post.author: (tone, judged_by) for post, tone, judged_by in posts}
    assert by_author['ann'] == ('bullish', 'model')
    assert by_author['bob'] == ('neutral', 'model')
    assert by_author['cy'] == ('bearish', 'model')
    assert by_author['dee'] == ('bullish', 'lexicon')
    assert by_author['eve'] == ('neutral', None)


def test_chart_carries_its_basis_not_the_quotes_venue():
    """A chart drawn from a converted US series says so on the chart itself.

    The header keeps saying Tradegate: that is where the headline price is
    from. The chart is a different statement and carries its own.
    """
    chart = detail.Chart(start=dt.date(2026, 9, 1), closes=[1.0, 2.0],
                         chatter=[None, None], watched_from=None)

    assert chart.currency is None
    assert chart.basis_venue is None
    assert chart.converted_from is None
    assert chart.priced_from == 'daily'
    assert not hasattr(chart, 'history_proxy')


def test_a_print_stamped_at_the_bell_is_an_anchor():
    """`opens <= ts < closes` dropped every print stamped exactly at 20:00Z.

    Measured on production 2026-09-04: all 54 of RZLV's prints for 2026-08-28
    carried exactly that timestamp, so its week line had nothing to draw.
    """
    from features.radar import detail as detail_mod
    from features.radar.market_calendars import session_bounds

    day = dt.datetime(2026, 9, 3, 12, 0, tzinfo=dt.timezone.utc)
    bounds = session_bounds('us', day)
    bell = bounds.regular_closes_at.astimezone(
        dt.timezone.utc).replace(tzinfo=None)

    kept = detail_mod._session_prints(
        [(bell, 10.0)], bounds)

    assert kept == [(bell, 10.0)]


def test_extended_hours_prints_anchor_when_the_session_had_none():
    """Tradegate's whole poll window is its late session.

    Its regular window is 09:00-17:30 Berlin and every stored XGAT quote_ts
    on production falls after it, so a regular-only filter kept zero of them.
    """
    from features.radar import detail as detail_mod
    from features.radar.market_calendars import session_bounds

    day = dt.datetime(2026, 9, 3, 12, 0, tzinfo=dt.timezone.utc)
    bounds = session_bounds('de', day, mic='XGAT')
    late = bounds.regular_closes_at.astimezone(
        dt.timezone.utc).replace(tzinfo=None) + dt.timedelta(minutes=30)

    kept = detail_mod._session_prints([(late, 10.0)], bounds)

    assert kept == [(late, 10.0)]


def test_a_print_outside_the_extended_session_is_not_an_anchor():
    from features.radar import detail as detail_mod
    from features.radar.market_calendars import session_bounds

    day = dt.datetime(2026, 9, 3, 12, 0, tzinfo=dt.timezone.utc)
    bounds = session_bounds('us', day)
    stray = bounds.opens_at.astimezone(
        dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(hours=2)

    assert detail_mod._session_prints([(stray, 10.0)], bounds) == []

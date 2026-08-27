# personal_apps/tests/test_radar_ingest.py
"""End-to-end through the pipeline with the network replaced by a callable.

The deleted-post case is the one worth reading twice: the text goes, the counts
stay. Removing the mention rows would rewrite history every time a user deleted
a post, and the aggregate fact that a ticker was discussed is not what needs
forgetting (spec 4.1).
"""
import datetime as dt
import logging

import pytest

from app import app as flask_app
from extensions import db
from models import (RadarBucket, RadarMention, RadarMentionEvent, RadarPost,
                    RadarSourceCursor, TickerUniverse)
from features.radar import ingest
from features.radar.sources import FetchResult, RawPost

NOW = dt.datetime(2026, 4, 15, 14, 20, 0)
TEST_CHANNEL = 'zz_task7_ingest'
TEST_SOURCES = ('bluesky', 'reddit', 'reddit:wallstreetbets')
TEST_TICKER = 'ZZG'


def _wipe():
    from models import RadarBucketSource
    RadarPost.query.filter(RadarPost.channel == TEST_CHANNEL).delete(
        synchronize_session=False)
    RadarBucketSource.query.filter_by(ticker=TEST_TICKER).delete(
        synchronize_session=False)
    RadarBucket.query.filter_by(ticker=TEST_TICKER).delete(
        synchronize_session=False)
    # roll_up now rebuilds from the journal rather than from one cycle's rows
    # (Task 2), so a ZZG event this suite never cleans up outlives the test
    # that wrote it and inflates every later test's rebuild of the same
    # (ticker, bucket_start) -- caught live: leftover rows from earlier tests
    # in this file made mention_count read 4, 4 and 7 where fresh runs read
    # 1, 0 and 2.
    RadarMentionEvent.query.filter_by(ticker=TEST_TICKER).delete(
        synchronize_session=False)
    TickerUniverse.query.filter_by(symbol=TEST_TICKER).delete(
        synchronize_session=False)
    RadarSourceCursor.query.filter(
        RadarSourceCursor.source.in_(TEST_SOURCES)).delete(
            synchronize_session=False)


@pytest.fixture()
def seeded(clean_radar):
    with flask_app.app_context():
        db.session.add(TickerUniverse(symbol=TEST_TICKER, name='Zulu Games Corp',
                                      exchange='NYSE',
                                      first_seen=dt.datetime(2026, 1, 1)))
        db.session.commit()
        yield


@pytest.fixture()
def clean_radar():
    with flask_app.app_context():
        _wipe()
        db.session.commit()
        yield
        _wipe()
        db.session.commit()


def post(ident='t3_1', body='$ZZG is ripping', score=5, author='u1',
         minute=10, title=None, source='bluesky'):
    return RawPost(source=source, external_id=ident, channel=TEST_CHANNEL,
                   author=author,
                   created_utc=dt.datetime(2026, 4, 15, 14, minute, 0),
                   title=title, body=body, score=score, num_comments=0,
                   url='https://example.invalid/%s' % ident)


def fetcher_for(result, source='bluesky'):
    def fetcher(since):
        return result
    return {source: fetcher}


def test_a_post_becomes_a_mention_and_a_bucket(seeded):
    result = ingest.run_cycle(
        NOW, fetcher_for(FetchResult(posts=[post()], status='ok')))

    assert result['posts_new'] == 1
    assert result['mentions'] == 1
    assert result['buckets_written'] == 1

    with flask_app.app_context():
        stored = RadarPost.query.filter_by(external_id='t3_1').one()
        assert stored.simhash != 0
        mention = RadarMention.query.filter_by(post_id=stored.id).one()
        assert mention.ticker == 'ZZG'
        assert mention.confidence == 'high'
        assert mention.lexicon_sentiment is not None
        bucket = RadarBucket.query.filter_by(ticker='ZZG').one()
        assert bucket.mention_count == 1


def test_reseeing_a_post_updates_its_score_without_duplicating(seeded):
    ingest.run_cycle(NOW, fetcher_for(FetchResult(posts=[post(score=5)], status='ok')))
    result = ingest.run_cycle(
        NOW, fetcher_for(FetchResult(posts=[post(score=900)], status='ok')))

    assert result['posts_new'] == 0
    with flask_app.app_context():
        assert RadarPost.query.filter_by(external_id='t3_1').count() == 1
        assert RadarPost.query.filter_by(external_id='t3_1').one().score == 900


def test_a_deleted_post_loses_its_text_but_keeps_its_counts(seeded):
    ingest.run_cycle(NOW, fetcher_for(FetchResult(posts=[post()], status='ok')))
    ingest.run_cycle(
        NOW,
        fetcher_for(FetchResult(posts=[post(body='', author=None)], status='ok')))

    with flask_app.app_context():
        stored = RadarPost.query.filter_by(external_id='t3_1').one()
        assert stored.body == ''
        assert RadarMention.query.filter_by(post_id=stored.id).count() == 1
        assert RadarBucket.query.filter_by(ticker='ZZG').one().mention_count == 1


def test_a_missing_source_writes_nothing_at_all(seeded):
    result = ingest.run_cycle(
        NOW, fetcher_for(FetchResult(posts=[], status='missing')))

    assert result['per_source'] == {'bluesky': 'missing'}
    assert result['buckets_written'] == 0
    with flask_app.app_context():
        assert RadarBucket.query.filter_by(ticker=TEST_TICKER).count() == 0


def test_an_empty_healthy_source_stays_ok_without_database_artifacts(seeded):
    """No work due is current coverage, not a source outage or a zero row."""
    result = ingest.run_cycle(
        NOW, fetcher_for(FetchResult(posts=[], status='ok')))

    assert result['per_source'] == {'bluesky': 'ok'}
    assert result['buckets_written'] == 0
    with flask_app.app_context():
        from models import RadarBucketSource
        assert RadarPost.query.filter_by(channel=TEST_CHANNEL).count() == 0
        assert RadarMention.query.filter_by(ticker=TEST_TICKER).count() == 0
        assert RadarBucket.query.filter_by(ticker=TEST_TICKER).count() == 0
        assert RadarBucketSource.query.filter_by(ticker=TEST_TICKER).count() == 0
        assert RadarMentionEvent.query.filter_by(ticker=TEST_TICKER).count() == 0
        assert RadarSourceCursor.query.filter_by(source='bluesky').count() == 0


def test_a_truncated_cycle_still_stores_its_mentions(seeded):
    result = ingest.run_cycle(
        NOW, fetcher_for(FetchResult(posts=[post()], status='truncated',
                                     catchup_depth=10)))

    assert result['per_source'] == {'bluesky': 'truncated'}
    assert result['catchup_depth'] == {'bluesky': 10}
    with flask_app.app_context():
        bucket = RadarBucket.query.filter_by(ticker='ZZG').one()
        assert bucket.mention_count == 1
        from models import RadarBucketSource
        assert RadarBucketSource.query.filter_by(
            ticker='ZZG', source='bluesky').one().status == 'truncated'


def test_posts_with_no_recognizable_ticker_are_not_stored_at_all(seeded):
    """Bluesky is 144k posts/hour and almost none are about stocks. Storing
    everything and extracting later would be 100 million rows a month to find
    the quarter-million that matter, so extraction runs first and a post that
    mentions nothing is never written."""
    result = ingest.run_cycle(
        NOW,
        fetcher_for(FetchResult(posts=[post(body='market feels weird today')],
                                status='ok')))

    assert result['posts_seen'] == 1
    assert result['posts_new'] == 0
    assert result['mentions'] == 0
    with flask_app.app_context():
        assert RadarPost.query.filter_by(channel='testsub').count() == 0


def test_the_cursor_advances_even_when_nothing_was_stored(seeded):
    """The cursor tracks what was SEEN, not what was KEPT. Inferring it from
    stored rows would rewind every cycle and refetch the same window forever."""
    ingest.run_cycle(
        NOW,
        fetcher_for(FetchResult(posts=[post(body='no tickers here', minute=12)],
                                status='ok')))
    with flask_app.app_context():
        cursor = RadarSourceCursor.query.filter_by(source='bluesky').one()
        assert cursor.cursor_utc == dt.datetime(2026, 4, 15, 14, 12, 0)


def test_since_advances_to_the_newest_post_seen(seeded):
    captured = {}

    def fetcher(since):
        captured['since'] = since
        return FetchResult(posts=[post(minute=10)], status='ok')

    ingest.run_cycle(NOW, {'bluesky': fetcher})
    ingest.run_cycle(NOW, {'bluesky': fetcher})
    assert captured['since'] == dt.datetime(2026, 4, 15, 14, 10, 0)


def test_two_sources_ingest_in_one_cycle(seeded):
    def rd(since):
        return FetchResult(
            posts=[post(ident='st1', body='$ZZG up', source='reddit')],
            status='ok')

    def bs(since):
        p = post(ident='bs1', body='$ZZG up')
        p.source = 'bluesky'
        return FetchResult(posts=[p], status='ok')

    result = ingest.run_cycle(NOW, {'reddit': rd, 'bluesky': bs})
    assert result['posts_new'] == 2
    assert result['per_source'] == {'reddit': 'ok', 'bluesky': 'ok'}
    with flask_app.app_context():
        from models import RadarBucketSource
        sources = {r.source for r in
                   RadarBucketSource.query.filter_by(ticker='ZZG').all()}
        assert sources == {'reddit', 'bluesky'}


def test_reddit_subreddits_write_only_their_own_status_rows(seeded):
    """One rolled-over feed must not mark a quieter subreddit truncated."""
    wallstreetbets = post(
        ident='task9-wsb', body='$ZZG from wsb', author='task9-wsb',
        source='reddit:wallstreetbets')
    pennystocks = post(
        ident='task9-penny', body='$ZZG from pennies', author='task9-penny',
        source='reddit:pennystocks')
    result = ingest.run_cycle(
        NOW,
        fetcher_for(FetchResult(
            posts=[wallstreetbets, pennystocks], status='truncated',
            per_source_status={
                'reddit:wallstreetbets': 'truncated',
                'reddit:pennystocks': 'ok',
            }), source='reddit'))

    assert result['per_source'] == {
        'reddit:wallstreetbets': 'truncated',
        'reddit:pennystocks': 'ok',
    }
    with flask_app.app_context():
        from models import RadarBucketSource
        rows = {row.source: row.status for row in
                RadarBucketSource.query.filter_by(ticker=TEST_TICKER).all()}
        assert rows == {
            'reddit:wallstreetbets': 'truncated',
            'reddit:pennystocks': 'ok',
        }
        assert RadarBucketSource.query.filter_by(
            ticker=TEST_TICKER, source='reddit').count() == 0


def test_tick_reports_reddit_aggregate_without_root_rollup(
        seeded, monkeypatch, caplog):
    """Operational root health is separate from concrete storage status."""
    import run_radar_ingest as daemon

    seen_rollup_statuses = []
    real_roll_up = ingest.buckets.roll_up

    def recording_roll_up(rows, statuses, touched):
        seen_rollup_statuses.append(dict(statuses))
        return real_roll_up(rows, statuses, touched)

    monkeypatch.setattr(ingest.buckets, 'roll_up', recording_roll_up)
    successful = post(
        ident='i3-partial', body='$ZZG survived', author='i3-partial',
        source='reddit:pennystocks')
    fetchers = fetcher_for(FetchResult(
        posts=[successful], status='truncated', catchup_depth=4,
        per_source_status={
            'reddit:pennystocks': 'ok',
            'reddit:wallstreetbets': 'missing',
        }), source='reddit')

    with caplog.at_level(logging.INFO, logger=daemon.logger.name):
        summary = daemon.tick(NOW.replace(tzinfo=dt.timezone.utc), fetchers)

    assert seen_rollup_statuses == [{
        'reddit:pennystocks': 'ok',
        'reddit:wallstreetbets': 'missing',
    }]
    assert 'reddit' not in seen_rollup_statuses[0]
    assert summary['aggregate_status'] == {'reddit': 'truncated'}
    assert 'aggregate=reddit=truncated' in caplog.text
    assert 'catchup_depth=reddit=4' in caplog.text
    with flask_app.app_context():
        from models import RadarBucketSource
        stored_sources = {row.source for row in
                          RadarBucketSource.query.filter_by(
                              ticker=TEST_TICKER).all()}
        assert stored_sources == {'reddit:pennystocks'}
        assert 'reddit' not in stored_sources


def test_a_successful_subreddit_survives_a_missing_aggregate_status(seeded):
    """A later refusal cannot discard comments already fetched this cycle."""
    successful = post(
        ident='task9-partial', body='$ZZG survived', author='task9-partial',
        source='reddit:pennystocks')
    result = ingest.run_cycle(
        NOW,
        fetcher_for(FetchResult(
            posts=[successful], status='missing',
            per_source_status={
                'reddit:pennystocks': 'ok',
                'reddit:wallstreetbets': 'missing',
            }), source='reddit'))

    assert result['posts_new'] == 1
    assert result['mentions'] == 1
    with flask_app.app_context():
        from models import RadarBucketSource
        rows = {row.source: row.status for row in
                RadarBucketSource.query.filter_by(ticker=TEST_TICKER).all()}
        assert rows == {'reddit:pennystocks': 'ok'}
        assert RadarPost.query.filter_by(external_id='task9-partial').count() == 1


def test_a_source_that_observed_nothing_writes_no_row_at_all(seeded):
    """An explicitly empty per-source map records NOTHING for that source.

    Reddit's "nothing due" branch is the common path -- six of eight cycles
    have no subreddit due -- and on it Reddit is not read at all. That is an
    absence: no fetch was made, so there is no observation. It is not an `ok`
    zero (a bucket child claiming coverage nothing produced, which also
    inflates RadarBucket.sources_ok) and it is not a `missing` (which means we
    tried and failed).

    So the map is empty rather than absent, and ingest must tell the two
    apart: `None` means "this fetcher does not report per-source status" and
    falls back to the aggregate verdict; `{}` means "no source was observed"
    and must not.
    """
    fetchers = fetcher_for(FetchResult(
        posts=[post(ident='task9-quiet', body='$ZZG moving',
                    author='task9-quiet')], status='ok'))
    fetchers.update(fetcher_for(
        FetchResult(posts=[], status='ok', per_source_status={}),
        source='reddit'))

    result = ingest.run_cycle(NOW, fetchers)

    assert result['per_source'] == {'bluesky': 'ok'}
    with flask_app.app_context():
        from models import RadarBucket, RadarBucketSource
        rows = {row.source: (row.status, row.mention_count) for row in
                RadarBucketSource.query.filter_by(ticker=TEST_TICKER).all()}
        assert rows == {'bluesky': ('ok', 1)}
        assert RadarBucketSource.query.filter_by(
            ticker=TEST_TICKER, source='reddit').count() == 0
        # And the bucket does not claim two sources were ok.
        assert {b.sources_ok for b in
                RadarBucket.query.filter_by(ticker=TEST_TICKER).all()} == {1}


def test_one_source_failing_does_not_stop_the_other(seeded):
    """The entire reason status is per source. A dead Bluesky must not cost a
    healthy Reddit cycle, and must not write a zero for itself."""
    def rd(since):
        return FetchResult(
            posts=[post(ident='st1', body='$ZZG up', source='reddit')],
            status='ok')

    def bs(since):
        return FetchResult(posts=[], status='missing')

    result = ingest.run_cycle(NOW, {'reddit': rd, 'bluesky': bs})
    assert result['per_source'] == {'reddit': 'ok', 'bluesky': 'missing'}
    with flask_app.app_context():
        from models import RadarBucketSource
        rows = {r.source: r.status for r in
                RadarBucketSource.query.filter_by(ticker='ZZG').all()}
        assert rows == {'reddit': 'ok'}


def test_each_source_keeps_its_own_cursor(seeded):
    """One source catching up must not drag the others back over ground they
    already covered."""
    def rd(since):
        return FetchResult(
            posts=[post(ident='st1', body='$ZZG', minute=10,
                        source='reddit:wallstreetbets')],
            status='ok')

    def bs(since):
        p = post(ident='bs1', body='$ZZG', minute=18)
        p.source = 'bluesky'
        return FetchResult(posts=[p], status='ok')

    ingest.run_cycle(NOW, {'reddit': rd, 'bluesky': bs})
    with flask_app.app_context():
        cursors = {c.source: c.cursor_utc for c in RadarSourceCursor.query.all()}
    assert cursors['reddit'] == dt.datetime(2026, 4, 15, 14, 10, 0)
    assert cursors['bluesky'] == dt.datetime(2026, 4, 15, 14, 18, 0)
    assert 'reddit:wallstreetbets' not in cursors


def test_the_same_post_twice_in_one_batch_is_stored_once(seeded):
    """A StockTwits message tagged $ZZG and $OTHER is returned by both symbol
    streams, so one cycle sees the same external_id twice. Found in live data,
    not in tests -- every fixture until now used distinct ids."""
    duplicate = [post(ident='dup1', body='$ZZG and more'),
                 post(ident='dup1', body='$ZZG and more')]
    result = ingest.run_cycle(
        NOW, fetcher_for(FetchResult(posts=duplicate, status='ok')))

    assert result['posts_new'] == 1
    assert result['mentions'] == 1
    with flask_app.app_context():
        assert RadarPost.query.filter_by(external_id='dup1').count() == 1
        assert RadarBucket.query.filter_by(ticker='ZZG').one().mention_count == 1


def test_a_duplicate_external_id_is_extracted_once_and_refreshes_engagement(
        seeded, monkeypatch):
    """One identity means one extraction decision, even when it appears twice."""
    calls = []
    extract = ingest._extract_for

    def counted(raw, lookup):
        calls.append(raw.external_id)
        return extract(raw, lookup)

    monkeypatch.setattr(ingest, '_extract_for', counted)
    duplicate = [post(ident='dup-extract', score=5),
                 post(ident='dup-extract', score=900)]

    result = ingest.run_cycle(
        NOW, fetcher_for(FetchResult(posts=duplicate, status='ok')))

    assert calls == ['dup-extract']
    assert result['posts_new'] == 1
    assert result['mentions'] == 1
    with flask_app.app_context():
        stored = RadarPost.query.filter_by(external_id='dup-extract').one()
        assert stored.score == 900
        assert RadarBucket.query.filter_by(ticker='ZZG').one().mention_count == 1


def test_a_low_only_post_is_counted_but_never_stored(seeded):
    """ROM in "dinosaur fossils at the ROM" is a real ticker and a real bare
    match, and about 12000 an hour of its kind cross the firehose. It is
    counted so the extractor's false-positive rate stays measurable, but the
    text is never kept -- seven million rows a month for posts the leaderboard
    can never surface."""
    result = ingest.run_cycle(
        NOW,
        fetcher_for(FetchResult(posts=[post(ident='low1', body='ZZG rumours')],
                                status='ok')))

    assert result['posts_new'] == 0
    assert result['mentions'] == 1
    with flask_app.app_context():
        assert RadarPost.query.filter_by(external_id='low1').count() == 0
        bucket = RadarBucket.query.filter_by(ticker='ZZG').one()
        assert bucket.mention_count == 0
        assert bucket.low_count == 1


def test_a_low_is_still_promoted_by_a_stored_high(seeded):
    """Promotion happens in memory before storage, so an unstored low can still
    be vouched for by a stored high from another author."""
    bare = post(ident='bare1', body='ZZG rumours', author='u1')
    tagged = post(ident='tag1', body='$ZZG confirmed', author='u2')
    result = ingest.run_cycle(
        NOW, fetcher_for(FetchResult(posts=[bare, tagged], status='ok')))

    assert result['posts_new'] == 1          # only the cashtagged one stored
    with flask_app.app_context():
        bucket = RadarBucket.query.filter_by(ticker='ZZG').one()
        assert bucket.mention_count == 2     # both scored
        assert bucket.low_count == 0


def test_an_unexpected_source_error_does_not_kill_the_cycle(seeded):
    """A missing dependency once took down a whole live cycle -- StockTwits and
    4chan included -- because ModuleNotFoundError is not the exception type the
    Bluesky module declares. Sources fail in ways they never anticipated, so
    the isolation has to be broad."""
    def exploding(since):
        raise ModuleNotFoundError("No module named 'websockets'")

    def healthy(since):
        return FetchResult(
            posts=[post(ident='ok1', body='$ZZG up', source='reddit')],
            status='ok')

    result = ingest.run_cycle(NOW, {'bluesky': exploding, 'reddit': healthy})

    assert result['per_source'] == {'bluesky': 'missing', 'reddit': 'ok'}
    assert result['mentions'] == 1
    with flask_app.app_context():
        from models import RadarBucketSource
        rows = {r.source for r in RadarBucketSource.query.filter_by(ticker='ZZG')}
        assert rows == {'reddit'}   # no bluesky row, and no zero


def test_a_failed_fetch_reports_no_catchup_depth(seeded):
    """Depth zero says the source reached back nowhere; failure reached nothing."""
    def explode(since):
        raise RuntimeError('nope')

    summary = ingest.run_cycle(NOW, {'bluesky': explode})

    assert summary['per_source']['bluesky'] == 'missing'
    assert summary['catchup_depth']['bluesky'] is None


def test_tick_visibly_logs_failed_fetch_depth_as_unknown(seeded, caplog):
    import run_radar_ingest as daemon

    def explode(since):
        raise RuntimeError('nope')

    with caplog.at_level(logging.INFO, logger=daemon.logger.name):
        summary = daemon.tick(
            NOW.replace(tzinfo=dt.timezone.utc), {'bluesky': explode})

    assert summary['aggregate_status'] == {'bluesky': 'missing'}
    assert summary['catchup_depth'] == {'bluesky': None}
    assert 'aggregate=bluesky=missing' in caplog.text
    assert 'catchup_depth=bluesky=unknown' in caplog.text
    assert 'catchup_depth=bluesky=0' not in caplog.text


def test_a_coin_collision_is_dropped_on_a_general_source(seeded, monkeypatch):
    """$BCH on Bluesky means Bitcoin Cash, not Banco de Chile.

    ZZG stands in for a coin-shaped symbol so the test does not depend on
    which real tickers happen to collide this year.
    """
    from features.radar import config
    monkeypatch.setattr(config, 'COIN_COLLISION_SYMBOLS', frozenset({'ZZG'}))

    p = post(ident='bs_coin', body='$ZZG pumping')
    p.source = 'bluesky'
    result = ingest.run_cycle(
        NOW, {'bluesky': lambda s: FetchResult(posts=[p], status='ok')})
    assert result['mentions'] == 0


def test_a_source_can_opt_into_reading_coin_symbols_as_companies(monkeypatch):
    """The extension point, kept alive with no live source using it.

    StockTwits was the only population where $LINK meant Interlink. It is
    retired; this pins that a future finance-native source can still opt in,
    rather than the map quietly becoming a constant nobody can override.
    """
    from features.radar import config, ingest

    monkeypatch.setattr(config, 'COIN_COLLISION_SYMBOLS', frozenset({'LINK'}))
    monkeypatch.setitem(config.COIN_SYMBOLS_MEAN_STOCKS, 'bluesky', True)
    lookup = {'LINK': {'name': 'Interlink Electronics Inc.', 'exchange': 'NASDAQ',
                       'distinctive': set()}}
    raw = post(ident='coin-link', body='$LINK is breaking out', source='bluesky')

    assert ingest._extract_for(raw, lookup) == [('LINK', 'high')]


# --- Automated feeds, wired in 2026-08-25 -----------------------------------
#
# config.looks_like_bot_feed (was looks_like_exchange_bot) had been defined
# since 2026-08-22 and hashed into source_config_version, and called by
# NOTHING. The pattern was written and then never reached the pipeline, which
# is a defect shaped like an absence: the board looked normal, it just counted
# machines.

def test_a_bot_feed_post_contributes_no_mentions():
    """The post is not a person discussing anything.

    Dropped whole rather than symbol by symbol -- a machine restating the same
    template every few seconds is one publisher, however many tickers it
    names, and per-symbol rules would have to enumerate a list that changes
    weekly.
    """
    from features.radar import ingest, universe

    lookup = universe.annotate_distinctive({
        'GOLD': {'name': 'Barrick Mining Corporation', 'exchange': 'NYSE'},
        'FIP': {'name': 'FTAI Infrastructure Inc.', 'exchange': 'NASDAQ'},
    })
    raw = post(body='FIP GOLD BELGRADE  Qualifying - Male - 1  '
                    'B. Levchuk/Z. Meireles def Z. Schmidt-Bohn/M. Csereszny 7/6 7/6')

    assert ingest._extract_for(raw, lookup) == []


def test_a_person_naming_the_same_tickers_still_counts():
    """Teeth. If the filter swallowed the tickers rather than the feed, the
    assertion above would pass while Barrick became untrackable."""
    from features.radar import ingest, universe

    lookup = universe.annotate_distinctive({
        'GOLD': {'name': 'Barrick Mining Corporation', 'exchange': 'NYSE'},
    })
    raw = post(body='$GOLD breaking out, miners finally waking up')

    assert ingest._extract_for(raw, lookup) == [('GOLD', 'high')]


def test_a_single_letter_cashtag_is_refused_on_a_general_network():
    """`$M` on Bluesky is money shorthand, not Macy's.

    Measured on live Bluesky: 119 of 3302 cashtag matches were single letters
    and essentially all were prose -- "Tax @60% for over a $M", "make $B's".
    config.SINGLE_LETTER_CASHTAGS has said so since it was written; nothing
    passed it to the extractor until now, and 353 such mentions reached the
    production corpus, 3.0% of the whole high-confidence set.
    """
    from features.radar import ingest

    lookup = {'B': {'name': 'Barnes Group Inc.', 'exchange': 'NYSE',
                    'distinctive': set()}}
    general = post(ident='zz-single', body='make $B and youre set',
                   source='bluesky')

    assert ingest._extract_for(general, lookup) == []


def test_a_source_can_opt_into_single_letter_cashtags(monkeypatch):
    """The extension point, kept alive with no live source using it.

    StockTwits was the only population where a bare `$B` was worth reading as
    Barnes Group rather than money shorthand. It is retired; this pins that a
    future finance-native source can still opt in, rather than the map
    quietly becoming a constant nobody can override.
    """
    from features.radar import config, ingest

    monkeypatch.setitem(config.SINGLE_LETTER_CASHTAGS, 'bluesky', True)
    lookup = {'B': {'name': 'Barnes Group Inc.', 'exchange': 'NYSE',
                    'distinctive': set()}}
    finance = post(ident='zz-single-2', body='make $B and youre set',
                   source='bluesky')

    assert ingest._extract_for(finance, lookup) == [('B', 'high')]

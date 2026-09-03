# personal_apps/tests/test_radar_journal.py
"""The journal is what makes a bucket rebuildable.

roll_up used to recompute a bucket from one cycle's in-memory mentions and
overwrite the result. Every source advances a cursor, so each cycle carries
only a slice, and a bucket touched by several cycles kept the last slice.
Measured in production 2026-08-26: 43% of the 10+ mention buckets lost.
"""
import datetime as dt

import pytest
import sqlalchemy as sa

from app import app as flask_app
from extensions import db
from models import RadarMention, RadarMentionEvent, RadarPost

_OWNED_EVENT_IDENTITIES = (
    ('bluesky', 'zz-a', 'ZZA'),
    ('bluesky', 'zz-b', 'ZZA'),
    ('bluesky', 'zz-low', 'ZZA'),
    ('bluesky', 'zz-high', 'ZZA'),
    ('bluesky', 'zz-voucher', 'ZZA'),
    ('bluesky', 'zz-bare-0', 'ZZA'),
    ('bluesky', 'zz-bare-1', 'ZZA'),
    ('bluesky', 'zz-bare-2', 'ZZA'),
    ('bluesky', 'zz-bare-3', 'ZZA'),
    ('bluesky', 'zz-bare-over-cap', 'ZZA'),
    ('reddit', 'zz-down', 'ZZA'),
    ('bluesky', 'zz-bootstrap-high', 'ZZH'),
    ('bluesky', 'zz-bootstrap-low', 'ZZL'),
    ('bluesky', 'zz-bootstrap-pre', 'ZZA'),
    ('bluesky', 'zz-bootstrap-post', 'ZZA'),
    ('bluesky', 'zz-1', 'ZZA'),
    ('bluesky', 'zz-dup', 'ZZB'),
)
_OWNED_BUCKET_TICKERS = ('ZZA',)
_OWNED_RETAINED_POST_IDS = (
    'zz-bootstrap-high', 'zz-bootstrap-low', 'zz-bootstrap-pre',
)


def _clear_owned_events():
    predicates = [
        sa.and_(RadarMentionEvent.source == source,
                RadarMentionEvent.external_id == external_id,
                RadarMentionEvent.ticker == ticker)
        for source, external_id, ticker in _OWNED_EVENT_IDENTITIES
    ]
    RadarMentionEvent.query.filter(sa.or_(*predicates)).delete(
        synchronize_session=False)
    db.session.commit()


@pytest.fixture()
def clean_events():
    with flask_app.app_context():
        _clear_owned_events()
        yield
        _clear_owned_events()


@pytest.fixture()
def clean_retained_mentions():
    def clear():
        ids = [post.id for post in RadarPost.query.filter(
            RadarPost.source == 'bluesky',
            RadarPost.external_id.in_(_OWNED_RETAINED_POST_IDS)).all()]
        if ids:
            RadarMention.query.filter(RadarMention.post_id.in_(ids)).delete(
                synchronize_session=False)
            RadarPost.query.filter(RadarPost.id.in_(ids)).delete(
                synchronize_session=False)
        db.session.commit()

    with flask_app.app_context():
        clear()
        yield
        clear()


@pytest.fixture()
def clean_buckets():
    from models import RadarBucket, RadarBucketSource
    with flask_app.app_context():
        for model in (RadarBucketSource, RadarBucket):
            model.query.filter(model.ticker.in_(_OWNED_BUCKET_TICKERS)).delete(
                synchronize_session=False)
        db.session.commit()
        yield
        for model in (RadarBucketSource, RadarBucket):
            model.query.filter(model.ticker.in_(_OWNED_BUCKET_TICKERS)).delete(
                synchronize_session=False)
        db.session.commit()


_ALL_OK = {'bluesky': 'ok'}


def _row(external_id, ticker='ZZA', minute=3, source='bluesky', author='u1',
         simhash=111, confidence='high', sentiment=0.5, engagement=10.0,
         channel='c', created_utc=None):
    from features.radar import buckets
    return buckets.MentionRow(
        ticker=ticker, external_id=external_id,
        created_utc=created_utc or dt.datetime(2026, 4, 15, 14, minute, 0),
        source=source, channel=channel, author=author, simhash=simhash,
        confidence=confidence, sentiment=sentiment, engagement=engagement)


def _retained_post(external_id, ticker, confidence, created_utc, *, author,
                   simhash, sentiment, score, comments):
    post = RadarPost(
        source='bluesky', external_id=external_id, channel='radar-test',
        author=author, created_utc=created_utc, title='title', body='body',
        score=score, num_comments=comments, url='https://example.test/post',
        simhash=simhash, first_seen=created_utc, last_seen=created_utc)
    post.mentions.append(RadarMention(
        ticker=ticker, confidence=confidence,
        lexicon_sentiment=sentiment))
    db.session.add(post)
    return post


def test_a_second_poll_inside_one_bucket_does_not_erase_the_first(clean_buckets,
                                                                  clean_events):
    """The production shape, which the old regression test never modelled.

    tests/test_radar_buckets.py fed its second roll_up call a SUPERSET of the
    first, modelling a full re-read of the window. No source does that: every
    one advances a cursor, so cycle N+1 carries a DISJOINT tail. The assertion
    encoded the assumption instead of testing it, and passed for months while
    production lost 43% of its busiest buckets.
    """
    from features.radar import buckets
    from models import RadarBucket

    start = {dt.datetime(2026, 4, 15, 14, 0, 0)}
    buckets.roll_up([_row(external_id='zz-a', author='u1', simhash=1, minute=1)],
                    _ALL_OK, start)
    buckets.roll_up([_row(external_id='zz-b', author='u2', simhash=2, minute=4)],
                    _ALL_OK, start)

    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.mention_count == 2
    assert bucket.distinct_authors == 2


def test_confidence_is_frozen_at_first_sight(clean_buckets, clean_events):
    """record()'s own docstring: everything but engagement is decided once.

    The reviewer's mutation widened `on_duplicate_key_update` to also refresh
    confidence (and sentiment/author/simhash) on a duplicate key, and the
    whole suite -- including the test this one replaces, which only ever sent
    an identical row twice -- stayed green. A row that arrives again with a
    DIFFERENT confidence is the case that actually exercises the freeze: if a
    universe or extraction-rule change made the same post look more credible
    on a later cycle, re-deciding would rewrite a bucket that was already
    counted under the old rule.
    """
    from features.radar import buckets
    from models import RadarBucket, RadarMentionEvent

    start = {dt.datetime(2026, 4, 15, 14, 0, 0)}
    buckets.roll_up([_row(external_id='zz-a', author='u1', simhash=1,
                          confidence='low')], _ALL_OK, start)
    buckets.roll_up([_row(external_id='zz-a', author='u1', simhash=1,
                          confidence='high')], _ALL_OK, start)

    event = RadarMentionEvent.query.filter_by(
        source='bluesky', external_id='zz-a', ticker='ZZA').one()
    assert event.confidence == 'low'

    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.mention_count == 0
    assert bucket.low_count == 1


def test_a_cashtag_vouches_across_cycle_boundaries(clean_buckets, clean_events):
    """Promotion is a property of the QUARTER-HOUR, not of one cycle's slice.

    _promote's own docstring says the window is the bucket. It could not be,
    while the only rows it saw were the ones this cycle happened to fetch.
    """
    from features.radar import buckets
    from models import RadarBucket

    start = {dt.datetime(2026, 4, 15, 14, 0, 0)}
    buckets.roll_up([_row(external_id='zz-low', author='u1', simhash=1,
                          confidence='low', minute=1)], _ALL_OK, start)
    buckets.roll_up([_row(external_id='zz-high', author='u2', simhash=2,
                          confidence='high', minute=9)], _ALL_OK, start)

    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    # The low was promoted to medium by the later cycle's cashtag.
    assert bucket.mention_count == 2
    assert bucket.high_confidence_count == 1
    assert bucket.low_count == 0


def test_a_fifth_bare_mention_revokes_the_buckets_prior_promotions(
        clean_buckets, clean_events):
    """Promotion is the current bucket verdict, never an historical badge.

    One cashtag can vouch for exactly MAX_BARE_PER_VOUCHER bare mentions. A
    fifth is evidence the token is too ambiguous, so the complete recompute
    must revoke the four earlier promotions as well as reject the newcomer.
    """
    from features.radar import buckets, journal
    from features.radar.config import MAX_BARE_PER_VOUCHER
    from models import RadarBucket

    start = {dt.datetime(2026, 4, 15, 14, 0, 0)}
    voucher = _row(external_id='zz-voucher', author='voucher', simhash=99,
                   confidence='high')
    bare = [_row(external_id='zz-bare-%d' % number, author='u%d' % number,
                 simhash=number, confidence='low', minute=number + 1)
            for number in range(MAX_BARE_PER_VOUCHER)]
    buckets.roll_up([voucher, *bare], _ALL_OK, start)

    initially_promoted = RadarMentionEvent.query.filter_by(
        ticker='ZZA', confidence='low').all()
    assert len(initially_promoted) == MAX_BARE_PER_VOUCHER
    assert all(event.promoted for event in initially_promoted)

    buckets.roll_up([
        _row(external_id='zz-bare-over-cap', author='u-over-cap', simhash=10,
             confidence='low', minute=9),
    ], _ALL_OK, start)

    bare_events = RadarMentionEvent.query.filter_by(
        ticker='ZZA', confidence='low').all()
    assert len(bare_events) == MAX_BARE_PER_VOUCHER + 1
    assert all(not event.promoted for event in bare_events)

    voices = journal.distinct_voices(
        ['ZZA'], ['bluesky'], dt.datetime(2026, 4, 15, 13, 0, 0),
        dt.datetime(2026, 4, 15, 15, 0, 0), 'author')
    assert voices['ZZA'] == 1
    assert RadarBucket.query.filter_by(ticker='ZZA').one().mention_count == 1


def test_a_down_sources_mentions_never_reach_the_journal(clean_buckets, clean_events):
    """The corollary of 'an absence is never a zero' (buckets.py's module
    docstring): a fabricated count from a source that was actually down would
    poison that source's own baseline the moment it recovers.

    roll_up must journal only `usable` (this cycle's rows filtered to
    countable sources), never `rows` (everything handed to it, missing
    sources included). Reviewer's mutation swapped one for the other: a cycle
    reporting `{'bluesky': 'ok', 'reddit': 'missing'}` still journalled
    the reddit row, and the NEXT cycle -- once reddit reports 'ok'
    again -- rebuilds from the journal and folds that leaked row into a brand
    new RadarBucketSource stamped status='ok', exactly as if reddit had
    been up the whole time.
    """
    from features.radar import buckets
    from models import RadarBucketSource

    start = {dt.datetime(2026, 4, 15, 14, 0, 0)}

    # Cycle 1: reddit is down but still handed roll_up a row (a fetch
    # that parsed a post before the failure was detected, or a source whose
    # cursor moved before its client raised). bluesky is up, so `countable`
    # is non-empty and roll_up does not return 0 before reaching journal.record.
    buckets.roll_up(
        [_row(external_id='zz-down', source='reddit', author='u1',
             simhash=1, minute=3),
         _row(external_id='zz-a', source='bluesky', author='u2',
             simhash=2, minute=3)],
        {'bluesky': 'ok', 'reddit': 'missing'}, start)

    # Cycle 2: reddit has recovered and contributes nothing new itself.
    # bluesky activity in the same window still forces a full rebuild of it,
    # which re-reads everything the journal is holding for (ZZA, 14:00).
    buckets.roll_up(
        [_row(external_id='zz-b', source='bluesky', author='u3',
             simhash=3, minute=5)],
        {'bluesky': 'ok', 'reddit': 'ok'}, start)

    reddit_row = RadarBucketSource.query.filter_by(
        ticker='ZZA', source='reddit').one()
    assert reddit_row.mention_count == 0


def test_bootstrap_recovers_retained_mentions_with_field_fidelity(
        clean_events, clean_retained_mentions):
    """bootstrap_from_mentions carries no ticker filter -- production has to
    recover EVERY retained decision in the window, not one ticker's -- so
    unlike the rest of this file it cannot lean on ZZ-namespacing alone for
    isolation. The dev database seeds 1432 real RadarPost x RadarMention rows
    dated before this test's 2027-06-01 window. This future window stays clear
    of all real and seeded rows while preserving the same bootstrap behaviour.
    """
    from features.radar import journal

    since = dt.datetime(2027, 6, 1, 13, 0, 0)
    _retained_post('zz-bootstrap-high', 'ZZH', 'high',
                   dt.datetime(2027, 6, 1, 14, 2, 0), author='high-author',
                   simhash=101, sentiment=0.75, score=7, comments=4)
    _retained_post('zz-bootstrap-low', 'ZZL', 'low',
                   dt.datetime(2027, 6, 1, 14, 7, 0), author='low-author',
                   simhash=202, sentiment=-0.25, score=-2, comments=5)
    db.session.commit()

    assert journal.bootstrap_from_mentions(since) == 2
    assert journal.bootstrap_from_mentions(since) == 2

    events = {event.ticker: event for event in
              RadarMentionEvent.query.filter(
                  RadarMentionEvent.ticker.in_(['ZZH', 'ZZL'])).all()}
    assert set(events) == {'ZZH', 'ZZL'}
    assert RadarMentionEvent.query.filter(
        RadarMentionEvent.ticker.in_(['ZZH', 'ZZL'])).count() == 2
    high = events['ZZH']
    assert (high.source, high.external_id, high.channel, high.author) == (
        'bluesky', 'zz-bootstrap-high', 'radar-test', 'high-author')
    assert high.created_utc == dt.datetime(2027, 6, 1, 14, 2, 0)
    assert high.bucket_start == dt.datetime(2027, 6, 1, 14, 0, 0)
    assert (high.simhash, high.confidence, high.sentiment, high.engagement) == (
        101, 'high', 0.75, 11.0)
    low = events['ZZL']
    assert (low.confidence, low.sentiment, low.engagement) == ('low', -0.25, 3.0)


def test_deploy_bootstrap_preserves_the_complete_open_bucket(
        clean_buckets, clean_events, clean_retained_mentions):
    """Same real-data constraint as the fidelity test above:
    _prepare_rollup_generation's bootstrap call and its legacy-evidence check
    both scan unbounded by ticker, so this test uses a 2027-06-01 window,
    beyond real and seeded rows, instead of this file's usual 2026-04-15.
    """
    import run_radar_ingest as daemon
    from features.radar import buckets
    from features.radar.config import source_config_version
    from models import RadarBucket, RadarBucketSource

    pre_deploy = dt.datetime(2027, 6, 1, 14, 2, 0)
    post_deploy = dt.datetime(2027, 6, 1, 14, 9, 0)
    start = {dt.datetime(2027, 6, 1, 14, 0, 0)}
    before = _row('zz-bootstrap-pre', author='predeploy', simhash=301,
                 created_utc=pre_deploy)
    buckets.roll_up([before], _ALL_OK, start)
    RadarMentionEvent.query.filter_by(
        source='bluesky', external_id='zz-bootstrap-pre', ticker='ZZA').delete()
    _retained_post('zz-bootstrap-pre', 'ZZA', 'high', before.created_utc,
                   author=before.author, simhash=before.simhash,
                   sentiment=before.sentiment, score=6, comments=4)
    source = RadarBucketSource.query.filter_by(
        ticker='ZZA', source='bluesky').one()
    source.source_config_version = 'old-generation'
    source.expected = 1.0
    source.variance = 2.0
    source.mention_z = 4.2
    source.baseline_days = 9
    db.session.commit()

    recovered, invalidated = daemon._prepare_rollup_generation(
        dt.datetime(2027, 6, 1, 16, 0, 0))
    buckets.roll_up([
        _row('zz-bootstrap-post', author='postdeploy', simhash=302,
            created_utc=post_deploy),
    ], _ALL_OK, start)

    db.session.expire_all()
    source = RadarBucketSource.query.filter_by(
        ticker='ZZA', source='bluesky').one()
    assert recovered == 1
    assert invalidated == 1
    assert RadarBucket.query.filter_by(ticker='ZZA').one().mention_count == 2
    assert source.mention_count == 2
    assert source.source_config_version == source_config_version()
    assert source.expected is None
    assert source.variance is None
    assert source.mention_z is None
    assert source.baseline_days is None


def test_the_table_accepts_one_event(clean_events):
    db.session.add(RadarMentionEvent(
        source='bluesky', external_id='zz-1', ticker='ZZA', channel='c',
        created_utc=dt.datetime(2026, 4, 15, 14, 3, 0),
        bucket_start=dt.datetime(2026, 4, 15, 14, 0, 0),
        author='u1', simhash=111, confidence='high',
        sentiment=0.5, engagement=10.0))
    db.session.commit()

    row = RadarMentionEvent.query.filter_by(ticker='ZZA').one()
    assert row.confidence == 'high'
    assert row.bucket_start == dt.datetime(2026, 4, 15, 14, 0, 0)


def test_the_same_mention_cannot_be_stored_twice(clean_events):
    """(source, external_id, ticker) is the identity of a mention.

    A post returned by two overlapping cycles is one mention, not two, and the
    unique key is what stops a rebuild from double-counting it.
    """
    import sqlalchemy as sa

    for _ in range(2):
        db.session.add(RadarMentionEvent(
            source='bluesky', external_id='zz-dup', ticker='ZZB', channel='c',
            created_utc=dt.datetime(2026, 4, 15, 14, 3, 0),
            bucket_start=dt.datetime(2026, 4, 15, 14, 0, 0),
            author='u1', simhash=222, confidence='high',
            sentiment=None, engagement=0.0))
    with pytest.raises(sa.exc.IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_the_voice_count_forces_the_index_built_for_it():
    """The planner stopped choosing ix_radar_mention_events_ticker_time once
    Arctic Shift grew the journal to ~700k rows, and picked the (ticker,
    bucket_start) index instead -- which can only use `ticker` and then
    tests created_utc against the heap. 7.53s against 0.17s on prod
    (2026-09-04), which put the 12h and 24h boards past the island's 8s
    timeout. ANALYZE TABLE did not change its mind, so the hint is load
    bearing rather than decorative."""
    from features.radar import journal

    with flask_app.app_context():
        query = journal._voice_count_query(
            ['ZZVOICE'], ['bluesky'],
            dt.datetime(2026, 9, 4), dt.datetime(2026, 9, 5))
        statement = str(query.statement.compile(
            dialect=sa.dialects.mysql.dialect()))

    assert 'FORCE INDEX (ix_radar_mention_events_ticker_time)' in statement

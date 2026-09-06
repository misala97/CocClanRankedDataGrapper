# personal_apps/tests/test_radar_buckets.py
"""The rollup is where per-source status becomes durable.

`truncated` is the subtle case: those counts are real but incomplete, so they
must be visible on the live leaderboard while being barred from any baseline.
Plan 2 enforces the second half; this suite pins that the status reaches the
row at all, because a bucket written `ok` when it was truncated is
indistinguishable from a genuine quiet period forever after.
"""
import datetime as dt
import uuid

import pytest

from app import app as flask_app
from extensions import db
from models import RadarBucket, RadarBucketSource, RadarMentionEvent
from features.radar import buckets
from features.radar.config import source_config_version

_OWNED_TICKERS = ('ZZA',)


def _clear_owned_rows():
    RadarBucketSource.query.filter(
        RadarBucketSource.ticker.in_(_OWNED_TICKERS)).delete(
        synchronize_session=False)
    RadarMentionEvent.query.filter(
        RadarMentionEvent.ticker.in_(_OWNED_TICKERS)).delete(
        synchronize_session=False)
    RadarBucket.query.filter(RadarBucket.ticker.in_(_OWNED_TICKERS)).delete(
        synchronize_session=False)
    db.session.commit()


@pytest.fixture()
def clean_buckets():
    with flask_app.app_context():
        _clear_owned_rows()
        yield
        _clear_owned_rows()


def row(ticker='ZZA', minute=3, source='bluesky', author='u1', simhash=111,
        confidence='high', sentiment=0.5, engagement=10.0, external_id=None,
        channel='c'):
    return buckets.MentionRow(
        ticker=ticker,
        external_id=external_id or ('zz-%s-%s-%s' % (ticker, author, minute)),
        created_utc=dt.datetime(2026, 4, 15, 14, minute, 0),
        source=source, channel=channel, author=author, simhash=simhash,
        confidence=confidence, sentiment=sentiment, engagement=engagement)


ALL_OK = {'bluesky': 'ok'}


def test_clean_buckets_preserves_an_unowned_zz_sentinel():
    """Fixture setup and teardown may delete only this file's identities."""
    sentinel = 'ZZ' + uuid.uuid4().hex[:10].upper()
    fixture = None

    with flask_app.app_context():
        db.session.add(RadarBucketSource(
            ticker=sentinel,
            bucket_start=dt.datetime(2027, 6, 1, 0, 0, 0),
            source='sentinel',
            mention_count=1,
            high_confidence_count=1,
            low_count=0,
            distinct_authors=1,
            distinct_text_ratio=1.0,
            engagement_weighted_count=1.0,
            status='ok',
            source_config_version='sentinel'))
        db.session.commit()

    try:
        fixture = clean_buckets.__wrapped__()
        next(fixture)
        assert RadarBucketSource.query.filter_by(ticker=sentinel).count() == 1

        with pytest.raises(StopIteration):
            next(fixture)
        fixture = None
        with flask_app.app_context():
            assert RadarBucketSource.query.filter_by(ticker=sentinel).count() == 1
    finally:
        if fixture is not None:
            fixture.close()
        with flask_app.app_context():
            RadarBucketSource.query.filter_by(ticker=sentinel).delete(
                synchronize_session=False)
            db.session.commit()


def test_bucket_start_floors_to_fifteen_minutes():
    assert buckets.bucket_start_for(dt.datetime(2026, 4, 15, 14, 3, 59)) == \
        dt.datetime(2026, 4, 15, 14, 0, 0)
    assert buckets.bucket_start_for(dt.datetime(2026, 4, 15, 14, 44, 0)) == \
        dt.datetime(2026, 4, 15, 14, 30, 0)


def test_counts_are_written(clean_buckets):
    buckets.roll_up([row(author='u1', simhash=1), row(author='u2', simhash=2)],
                    ALL_OK, {dt.datetime(2026, 4, 15, 14, 0, 0)})
    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.mention_count == 2
    assert bucket.distinct_authors == 2
    assert RadarBucketSource.query.filter_by(
        ticker='ZZA', source='bluesky').one().mention_count == 2
    assert bucket.high_confidence_count == 2


def test_distinct_text_ratio_catches_a_copy_paste_brigade(clean_buckets):
    """Fifty accounts posting one thing. distinct_authors sees nothing wrong;
    this is the column that does."""
    rows = [row(author='u%d' % i, simhash=999) for i in range(4)]
    buckets.roll_up(rows, ALL_OK, {dt.datetime(2026, 4, 15, 14, 0, 0)})
    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.distinct_authors == 4
    assert bucket.distinct_text_ratio == pytest.approx(0.25)


def test_per_source_status_is_stored_separately(clean_buckets):
    from models import RadarBucketSource
    buckets.roll_up([row()], {'bluesky': 'ok', 'reddit': 'missing'},
                    {dt.datetime(2026, 4, 15, 14, 0, 0)})
    assert RadarBucket.query.filter_by(ticker='ZZA').one().sources_ok == 1
    rows = {r.source: r.status for r in
            RadarBucketSource.query.filter_by(ticker='ZZA').all()}
    # A `missing` source writes no row at all -- that is the rule.
    assert rows == {'bluesky': 'ok'}


def test_truncated_counts_are_kept_and_marked(clean_buckets):
    from models import RadarBucketSource
    buckets.roll_up([row()], {'bluesky': 'truncated'},
                    {dt.datetime(2026, 4, 15, 14, 0, 0)})
    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.mention_count == 1
    assert bucket.sources_ok == 0
    assert RadarBucketSource.query.filter_by(
        ticker='ZZA', source='bluesky').one().status == 'truncated'


def test_a_missing_source_writes_no_bucket_rather_than_a_zero(clean_buckets):
    """The single most important rule in the ingest layer. A zero here would
    poison the baseline and manufacture a spike when ingest resumes."""
    written = buckets.roll_up([], {'reddit': 'missing', 'bluesky': 'missing'},
                              {dt.datetime(2026, 4, 15, 14, 0, 0)})
    assert written == 0
    assert RadarBucket.query.filter_by(ticker='ZZA').count() == 0


def test_a_re_read_of_the_same_window_does_not_double(clean_buckets):
    """A cycle that re-reads a window it already read must not add to it.

    This is the overlap case, and it is the only one the old version of this
    test covered -- it fed the second call a SUPERSET, which no source
    produces. The disjoint case, which every source produces, lives in
    tests/test_radar_journal.py and used to fail.
    """
    start = {dt.datetime(2026, 4, 15, 14, 0, 0)}
    buckets.roll_up([row(author='u1', simhash=1)], ALL_OK, start)
    buckets.roll_up([row(author='u1', simhash=1), row(author='u2', simhash=2)],
                    ALL_OK, start)
    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.mention_count == 2


def test_mentions_split_across_bucket_boundaries(clean_buckets):
    touched = {dt.datetime(2026, 4, 15, 14, 0, 0),
               dt.datetime(2026, 4, 15, 14, 15, 0)}
    buckets.roll_up([row(minute=3), row(minute=20)], ALL_OK, touched)
    assert RadarBucket.query.filter_by(ticker='ZZA').count() == 2


def test_config_version_is_stamped(clean_buckets):
    buckets.roll_up([row()], ALL_OK, {dt.datetime(2026, 4, 15, 14, 0, 0)})
    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.source_config_version == source_config_version()


def test_sentiment_mean_is_averaged(clean_buckets):
    buckets.roll_up([row(sentiment=1.0, author='u1', simhash=1),
                     row(sentiment=0.0, author='u2', simhash=2)],
                    ALL_OK, {dt.datetime(2026, 4, 15, 14, 0, 0)})
    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.sentiment_mean == pytest.approx(0.5)


def test_scoring_columns_are_left_untouched(clean_buckets):
    """Pinned on RadarBucketSource, not RadarBucket.

    Until 2026-08-26 this asserted on `bucket.mention_z_reddit` -- a column
    the per-source-rows refactor deleted (see
    test_the_parent_bucket_no_longer_has_per_source_columns above).
    SQLAlchemy lets you set an unmapped attribute on an instance with no
    error, and db.session.expire() only reloads mapped columns, so that
    attribute was never written to the database and the assertion could not
    fail no matter what roll_up did to any real column. It passed vacuously
    for as long as the refactor has existed.

    The property still matters: expected/variance/mention_z/baseline_days
    live on RadarBucketSource now, written by scoring.score_source, and a
    rollup must not clobber them while status and generation remain scoreable.
    The complementary policy is pinned in test_radar_bucket_sources.py:
    current-generation `truncated` also preserves a score, while an
    unscoreable status or incompatible generation clears it.
    """
    buckets.roll_up([row()], ALL_OK, {dt.datetime(2026, 4, 15, 14, 0, 0)})
    source = RadarBucketSource.query.filter_by(
        ticker='ZZA', source='bluesky').one()
    source.expected = 1.0
    source.variance = 2.0
    source.mention_z = 4.2
    source.baseline_days = 9
    db.session.commit()

    buckets.roll_up([row(), row(author='u2', simhash=2)], ALL_OK,
                    {dt.datetime(2026, 4, 15, 14, 0, 0)})
    db.session.expire(source)
    assert source.status == 'ok'
    assert source.expected == 1.0
    assert source.variance == 2.0
    assert source.mention_z == 4.2
    assert source.baseline_days == 9


@pytest.mark.parametrize('previous_version', [None, 'old-generation'])
def test_a_generation_restamp_clears_every_stale_score(clean_buckets,
                                                        previous_version):
    """A restamp cannot make an old score look current."""
    start = {dt.datetime(2026, 4, 15, 14, 0, 0)}
    buckets.roll_up([row()], ALL_OK, start)
    source = RadarBucketSource.query.filter_by(
        ticker='ZZA', source='bluesky').one()
    source.source_config_version = previous_version
    source.expected = 1.0
    source.variance = 2.0
    source.mention_z = 4.2
    source.baseline_days = 9
    db.session.commit()

    buckets.roll_up([row()], ALL_OK, start)

    db.session.expire(source)
    assert source.source_config_version == source_config_version()
    assert source.expected is None
    assert source.variance is None
    assert source.mention_z is None
    assert source.baseline_days is None


def test_per_source_rows_are_written(clean_buckets):
    rows = [row(source='reddit', author='u1', simhash=1),
            row(source='bluesky', author='u2', simhash=2)]
    buckets.roll_up(rows, {'reddit': 'ok', 'bluesky': 'ok'},
                    {dt.datetime(2026, 4, 15, 14, 0, 0)})
    per_source = {r.source: r.mention_count for r in
                  RadarBucketSource.query.filter_by(ticker='ZZA').all()}
    assert per_source == {'reddit': 1, 'bluesky': 1}
    assert RadarBucket.query.filter_by(ticker='ZZA').one().mention_count == 2


def test_an_unknown_source_name_needs_no_schema_change(clean_buckets):
    """The point of the child table. A source nobody has heard of writes a row
    like any other -- no migration, no column, no code that knows its name."""
    buckets.roll_up([row(source='some_new_source')], {'some_new_source': 'ok'},
                    {dt.datetime(2026, 4, 15, 14, 0, 0)})
    assert RadarBucketSource.query.filter_by(
        ticker='ZZA', source='some_new_source').one().mention_count == 1


def test_a_low_mention_is_promoted_by_another_authors_cashtag(clean_buckets):
    """Someone writing $ZZA vouches for someone else writing bare ZZA in the
    same window, so the bare one becomes scored."""
    rows = [row(confidence='low', author='u1', simhash=1),
            row(confidence='high', author='u2', simhash=2)]
    buckets.roll_up(rows, ALL_OK, {dt.datetime(2026, 4, 15, 14, 0, 0)})
    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.mention_count == 2
    assert bucket.low_count == 0


def test_the_same_author_cannot_corroborate_themselves(clean_buckets):
    """One person writing both ZZA and $ZZA is one opinion, not two.

    Two distinct posts, so distinct external_ids -- row()'s default collapses
    to one (ticker, author, minute) tuple and this is the one case in this
    suite where the same author genuinely posts twice in the same window.
    """
    rows = [row(confidence='low', author='u1', simhash=1, external_id='zz-bare'),
            row(confidence='high', author='u1', simhash=2, external_id='zz-cash')]
    buckets.roll_up(rows, ALL_OK, {dt.datetime(2026, 4, 15, 14, 0, 0)})
    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.mention_count == 1
    assert bucket.low_count == 1


def test_uncorroborated_lows_are_stored_but_not_scored(clean_buckets):
    rows = [row(confidence='low', author='u%d' % i, simhash=i) for i in range(4)]
    buckets.roll_up(rows, ALL_OK, {dt.datetime(2026, 4, 15, 14, 0, 0)})
    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.mention_count == 0
    assert bucket.low_count == 4


def test_a_bucket_with_only_lows_still_records_its_source_status(clean_buckets):
    """The source was healthy and saw nothing scorable. That is a real zero and
    must stay distinguishable from the source being down."""
    buckets.roll_up([row(confidence='low')], ALL_OK,
                    {dt.datetime(2026, 4, 15, 14, 0, 0)})
    assert RadarBucketSource.query.filter_by(
        ticker='ZZA', source='bluesky').one().status == 'ok'


def test_the_config_version_is_stamped_on_each_source_row(clean_buckets):
    """Baselines exclude history from before a config change, and that
    exclusion is per (ticker, source). Reading it off the parent bucket would
    mean joining a table the baseline query has no other reason to touch."""
    from features.radar.config import source_config_version
    buckets.roll_up([row(source='reddit'), row(source='bluesky')],
                    {'reddit': 'ok', 'bluesky': 'ok'},
                    {dt.datetime(2026, 4, 15, 14, 0, 0)})
    versions = {r.source: r.source_config_version for r in
                RadarBucketSource.query.filter_by(ticker='ZZA').all()}
    assert len(versions) == 2
    assert set(versions.values()) == {source_config_version()}


# --- The promotion leak, measured on live data 2026-08-25 -------------------
#
# ICE 315, IA 393, MAGA 256 and GOP 210 sat in the SCORED set over seven days,
# and the top thirty tickers by volume were timezones, country codes and news
# agencies rather than companies. Both facts trace to _promote, which had two
# separate faults: it vouched across bucket boundaries, and it put no ceiling
# on how many bare mentions one cashtag could carry.


def test_a_cashtag_cannot_vouch_across_bucket_boundaries(clean_buckets):
    """The docstring said "in the same window"; the code did not.

    Vouchers were keyed by ticker alone and _promote ran over the whole
    cycle's rows before they were grouped, so one $ZZA at 14:03 corroborated a
    bare ZZA at 14:47 -- and on catch-up a cycle spans hours, which makes the
    window unbounded in practice.
    """
    rows = [row(confidence='high', author='u2', minute=3, simhash=2),
            row(confidence='low', author='u1', minute=47, simhash=1)]
    buckets.roll_up(rows, ALL_OK, {dt.datetime(2026, 4, 15, 14, 0, 0),
                                   dt.datetime(2026, 4, 15, 14, 45, 0)})

    later = RadarBucket.query.filter_by(
        ticker='ZZA', bucket_start=dt.datetime(2026, 4, 15, 14, 45, 0)).one()
    assert later.mention_count == 0
    assert later.low_count == 1


def test_one_cashtag_does_not_vouch_for_a_crowd(clean_buckets):
    """A cashtag is one person's act of notation, and the confidence it lends
    does not scale with how many strangers typed the same three letters.

    This is the ICE case exactly: one $ICE from someone discussing the
    exchange, beside a quarter-hour of unrelated posts about immigration
    raids. Promoting all of them turns a news cycle into a stock signal.
    """
    rows = ([row(confidence='low', author='u%d' % i, simhash=i)
             for i in range(50)]
            + [row(confidence='high', author='voucher', simhash=999)])
    buckets.roll_up(rows, ALL_OK, {dt.datetime(2026, 4, 15, 14, 0, 0)})

    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.mention_count == 1        # the cashtag, and nothing else
    assert bucket.low_count == 50


def test_a_credible_ratio_still_promotes(clean_buckets):
    """Teeth for the test above.

    If the cap rejected every promotion the assertion there would pass without
    the ratio meaning anything, and corroboration -- the mechanism that makes
    bare tokens usable at all -- would be silently dead.
    """
    rows = ([row(confidence='low', author='u%d' % i, simhash=i)
             for i in range(3)]
            + [row(confidence='high', author='voucher', simhash=999)])
    buckets.roll_up(rows, ALL_OK, {dt.datetime(2026, 4, 15, 14, 0, 0)})

    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.mention_count == 4
    assert bucket.low_count == 0


def test_more_vouchers_carry_more_bare_mentions(clean_buckets):
    """The ceiling is a ratio, not a fixed number.

    Ten people cashtagging ZZA in one quarter-hour is a real conversation and
    should vouch for more bare mentions than one person can. A flat cap would
    throttle exactly the busy windows the board exists to surface.
    """
    rows = ([row(confidence='low', author='u%d' % i, simhash=i)
             for i in range(9)]
            + [row(confidence='high', author='v%d' % i, simhash=900 + i)
               for i in range(3)])
    buckets.roll_up(rows, ALL_OK, {dt.datetime(2026, 4, 15, 14, 0, 0)})

    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.mention_count == 12
    assert bucket.low_count == 0


def test_the_promotion_ceiling_is_hashed_into_the_config_version():
    """It changes which mentions get counted, so it belongs in the stamp.

    Retuning it without a new stamp would mix populations scored under two
    different corroboration rules inside one baseline -- the exact failure the
    stamp exists to prevent, and the one the extraction rules already caused
    once before 2026-08-22.
    """
    from unittest import mock
    from features.radar import config

    before = config.source_config_version()
    with mock.patch.object(config, 'MAX_BARE_PER_VOUCHER',
                           config.MAX_BARE_PER_VOUCHER + 1):
        assert config.source_config_version() != before


# --- deadlock retry (production 2026-09-03) ---------------------------------

def test_a_deadlocked_rollup_is_retried_whole(monkeypatch):
    """InnoDB rolls a losing transaction back entirely. The cycle above has
    already committed its posts and advanced its cursors, so giving up here
    would leave those mentions journalled and never counted."""
    import sqlalchemy.exc

    from features.radar import buckets as buckets_module

    calls = []

    def flaky(rows, statuses, touched, *, preserve_parent=False):
        calls.append(1)
        if len(calls) < 3:
            raise sqlalchemy.exc.OperationalError(
                'UPDATE radar_bucket_sources', {},
                Exception(1213, 'Deadlock found when trying to get lock'))
        return 7

    monkeypatch.setattr(buckets_module, '_roll_up_once', flaky)
    monkeypatch.setattr(buckets_module.time, 'sleep', lambda _s: None)

    with flask_app.app_context():          # the retry rolls the session back
        assert buckets_module.roll_up([], {}, set()) == 7
    assert len(calls) == 3


def test_a_non_deadlock_database_error_is_not_retried(monkeypatch):
    """Retrying a bad column name three times only delays the traceback."""
    import sqlalchemy.exc

    from features.radar import buckets as buckets_module

    calls = []

    def broken(rows, statuses, touched, *, preserve_parent=False):
        calls.append(1)
        raise sqlalchemy.exc.OperationalError(
            'SELECT', {}, Exception(1054, "Unknown column 'nope'"))

    monkeypatch.setattr(buckets_module, '_roll_up_once', broken)
    monkeypatch.setattr(buckets_module.time, 'sleep', lambda _s: None)

    with flask_app.app_context():
        with pytest.raises(sqlalchemy.exc.OperationalError):
            buckets_module.roll_up([], {}, set())
    assert len(calls) == 1


# --- one write lock for every bucket writer (production, evening of 2026-09-03)

def test_two_rollups_never_write_at_the_same_time(monkeypatch):
    """Four writers share the bucket tables in one process; any two
    interleaving deadlocked InnoDB, and the retry cannot outlast a flush
    that holds row locks for a minute. The lock lives with the table."""
    import threading

    from features.radar import buckets as buckets_module

    started = threading.Event()
    release = threading.Event()
    trace = []

    def slow(rows, statuses, touched, *, preserve_parent=False):
        started.set()
        trace.append('in')
        release.wait(timeout=5)
        trace.append('out')
        return 1

    monkeypatch.setattr(buckets_module, '_roll_up_once', slow)

    def roll_up_in_context():
        # Its own app context: the guard now takes a database lock too, and
        # a thread does not inherit one.
        with flask_app.app_context():
            buckets_module.roll_up([], {}, set())

    first = threading.Thread(target=roll_up_in_context)
    first.start()
    assert started.wait(timeout=5)
    second = threading.Thread(target=roll_up_in_context)
    second.start()
    second.join(timeout=0.5)
    assert second.is_alive(), 'the second rollup wrote while the first held the lock'

    release.set()
    first.join(timeout=5)
    second.join(timeout=5)
    assert trace == ['in', 'out', 'in', 'out']


def test_the_chatter_rebuild_takes_the_same_lock(monkeypatch):
    """rebuild_windows is the fourth writer -- the sentiment path's
    correction of a window -- and it writes the same rows."""
    import datetime as dt

    from features.radar import buckets as buckets_module

    held = []

    def record(windows, commit=True):
        held.append(buckets_module.BUCKET_WRITE_LOCK.locked())
        return 0

    monkeypatch.setattr(buckets_module, '_rebuild_windows_locked', record)
    with flask_app.app_context():
        buckets_module.rebuild_windows({('ZZLOCK', dt.datetime(2027, 1, 4, 12, 0))})
    assert held == [True]
    assert not buckets_module.BUCKET_WRITE_LOCK.locked()

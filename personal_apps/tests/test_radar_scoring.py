# personal_apps/tests/test_radar_scoring.py
"""Turning counts into surprise.

Everything here reads radar_bucket_sources and writes back onto the same rows.
No prices and no divergence -- those need a market feed and are Plan 3.
"""
import datetime as dt
import uuid

import pytest

from app import app as flask_app
from extensions import db
from models import RadarBucketSource
from features.radar import buckets, scoring
from features.radar.config import source_config_version
from test_radar_buckets import clean_buckets  # noqa: F401

MONDAY = dt.datetime(2026, 8, 17, 0, 0, 0)
# A concrete stored Reddit source name. Since 2026-08-26 every Reddit
# observation is written under `reddit:<sub>`; the bare root is a SELECTION,
# and pooled_z expands it to all eight configured subs.
REDDIT = 'reddit:pennystocks'
NOW = MONDAY + dt.timedelta(days=35)
_OWNED_TICKERS = (
    'SSA', 'SSB', 'SSNEW', 'SSOLD', 'SSNULL',
    'ZZGEN', 'ZZSCORED', 'ZZSCOPE', 'ZZUNSCORED', 'ZZTRUNCATED',
    'ZZMISSING', 'ZZM2POOL', 'ZZM2WINDOW',
)


def _clear_owned_rows():
    RadarBucketSource.query.filter(
        RadarBucketSource.ticker.in_(_OWNED_TICKERS)).delete(
            synchronize_session=False)
    db.session.commit()


@pytest.fixture()
def rows():
    with flask_app.app_context():
        _clear_owned_rows()
        yield
        _clear_owned_rows()


def add(when, count, ticker='SSA', source='bluesky', status='ok',
        version=None):
    db.session.add(RadarBucketSource(
        ticker=ticker, bucket_start=when, source=source,
        mention_count=count, high_confidence_count=count, low_count=0,
        distinct_authors=count, distinct_text_ratio=1.0,
        engagement_weighted_count=float(count), status=status,
        source_config_version=version or source_config_version()))


def steady_history(ticker='SSA', per_bucket=2, days=30, source='bluesky'):
    """A boringly consistent ticker, so anything unusual is the test's doing.

    2880 rows at 15-minute grain. Added to the session and committed once by
    the caller -- committing per row makes this suite take minutes.
    """
    for step in range(days * 96):
        add(MONDAY + dt.timedelta(minutes=15 * step), per_bucket,
            ticker=ticker, source=source)


def test_row_cleanup_preserves_an_unowned_zz_sentinel():
    """This file's shared-DB cleanup must never claim another ZZ namespace."""
    sentinel = 'ZZX' + uuid.uuid4().hex[:9].upper()
    with flask_app.app_context():
        db.session.add(RadarBucketSource(
            ticker=sentinel, bucket_start=NOW, source='sentinel',
            mention_count=1, high_confidence_count=1, low_count=0,
            distinct_authors=1, distinct_text_ratio=1.0,
            engagement_weighted_count=1.0, status='ok',
            source_config_version='sentinel'))
        db.session.commit()
        try:
            _clear_owned_rows()
            assert RadarBucketSource.query.filter_by(ticker=sentinel).count() == 1
        finally:
            RadarBucketSource.query.filter_by(ticker=sentinel).delete(
                synchronize_session=False)
            db.session.commit()


def test_a_normal_bucket_scores_near_zero(rows):
    steady_history()
    db.session.commit()
    scoring.score_source('bluesky', NOW)

    row = RadarBucketSource.query.filter_by(
        ticker='SSA', bucket_start=MONDAY + dt.timedelta(days=10)).one()
    assert row.mention_z is not None
    assert abs(row.mention_z) < 2


def test_a_spike_scores_high(rows):
    steady_history()
    loud = MONDAY + dt.timedelta(days=20)
    db.session.commit()
    RadarBucketSource.query.filter_by(ticker='SSA', bucket_start=loud).update(
        {'mention_count': 60})
    db.session.commit()

    scoring.score_source('bluesky', NOW)
    assert RadarBucketSource.query.filter_by(
        ticker='SSA', bucket_start=loud).one().mention_z > 5


def test_expected_and_variance_are_stored_too(rows):
    """Pooling a user-selected subset means summing components, so the parts
    have to survive, not just the z (spec 6.2)."""
    steady_history()
    db.session.commit()
    scoring.score_source('bluesky', NOW)

    row = RadarBucketSource.query.filter_by(
        ticker='SSA', bucket_start=MONDAY + dt.timedelta(days=10)).one()
    assert row.expected > 0
    assert row.variance >= row.expected


def test_missing_buckets_are_never_scored(rows):
    """A source that was down has nothing to be surprised about."""
    steady_history()
    gap = MONDAY + dt.timedelta(days=12)
    db.session.commit()
    RadarBucketSource.query.filter_by(ticker='SSA', bucket_start=gap).update(
        {'status': 'missing', 'mention_count': 0})
    db.session.commit()

    scoring.score_source('bluesky', NOW)
    assert RadarBucketSource.query.filter_by(
        ticker='SSA', bucket_start=gap).one().mention_z is None


def test_a_truncated_bucket_is_scored_from_ok_baselines(rows):
    """Known undercounts remain rankable against an `ok`-only normal."""
    steady_history(ticker='ZZTRUNCATED')
    truncated_at = NOW - dt.timedelta(minutes=15)
    add(truncated_at, 3, ticker='ZZTRUNCATED', status='truncated')
    db.session.commit()

    scoring.score_source('bluesky', NOW)

    truncated = RadarBucketSource.query.filter_by(
        ticker='ZZTRUNCATED', source='bluesky',
        bucket_start=truncated_at).one()
    assert truncated.status == 'truncated'
    assert truncated.expected is not None
    assert truncated.variance is not None
    assert truncated.mention_z is not None
    assert truncated.baseline_days is not None


def test_scoreable_statuses_exclude_missing():
    """The scoring eligibility contract admits incomplete observations only."""
    assert scoring.SCOREABLE_STATUSES == frozenset({'ok', 'truncated'})


def test_a_current_generation_missing_bucket_keeps_all_scores_null(rows):
    """A source outage is an absence, even when its `ok` history is scoreable."""
    steady_history(ticker='ZZMISSING')
    missing_at = NOW - dt.timedelta(minutes=15)
    add(missing_at, 0, ticker='ZZMISSING', status='missing')
    db.session.commit()

    scoring.score_source('bluesky', NOW)

    missing = RadarBucketSource.query.filter_by(
        ticker='ZZMISSING', source='bluesky', bucket_start=missing_at).one()
    assert missing.status == 'missing'
    assert missing.expected is None
    assert missing.variance is None
    assert missing.mention_z is None
    assert missing.baseline_days is None


def test_a_gap_does_not_depress_the_baseline(rows):
    """The observed-mass property, end to end. A week of outage must not make
    the ticker look like it went quiet, or everything after would spike."""
    steady_history()
    db.session.commit()
    scoring.score_source('bluesky', NOW)
    reference = RadarBucketSource.query.filter_by(
        ticker='SSA', bucket_start=MONDAY + dt.timedelta(days=25)).one().mention_z

    outage_start = MONDAY + dt.timedelta(days=5)
    RadarBucketSource.query.filter(
        RadarBucketSource.ticker == 'SSA',
        RadarBucketSource.bucket_start >= outage_start,
        RadarBucketSource.bucket_start < outage_start + dt.timedelta(days=7)
    ).update({'status': 'missing', 'mention_count': 0}, synchronize_session=False)
    db.session.commit()

    scoring.score_source('bluesky', NOW)
    after = RadarBucketSource.query.filter_by(
        ticker='SSA', bucket_start=MONDAY + dt.timedelta(days=25)).one().mention_z
    assert after == pytest.approx(reference, abs=0.5)


def test_baseline_days_is_recorded(rows):
    steady_history(days=30)
    db.session.commit()
    scoring.score_source('bluesky', NOW)
    row = RadarBucketSource.query.filter_by(
        ticker='SSA', bucket_start=MONDAY + dt.timedelta(days=10)).one()
    assert row.baseline_days >= 14


def test_a_brand_new_ticker_is_provisional(rows):
    """Two days of history cannot support a z-score anyone should act on."""
    for step in range(2 * 96):
        add(NOW - dt.timedelta(days=2) + dt.timedelta(minutes=15 * step), 3,
            ticker='SSNEW')
    db.session.commit()
    scoring.score_source('bluesky', NOW)

    row = (RadarBucketSource.query.filter_by(ticker='SSNEW')
           .order_by(RadarBucketSource.bucket_start.desc()).first())
    assert row.baseline_days < 14


def test_scoring_only_touches_its_own_source(rows):
    steady_history(source='bluesky')
    steady_history(ticker='SSB', source='reddit')
    db.session.commit()
    scoring.score_source('bluesky', NOW)

    assert RadarBucketSource.query.filter_by(
        ticker='SSB', source='reddit').first().mention_z is None


def test_scoring_passes_the_current_generation_to_the_profile(rows,
                                                               monkeypatch):
    steady_history()
    db.session.commit()
    seen = {}
    real_build_profile = scoring.profile.build_profile

    def watched_build_profile(source, until, config_version, **kwargs):
        seen['version'] = config_version
        return real_build_profile(source, until, config_version, **kwargs)

    monkeypatch.setattr(scoring.profile, 'build_profile', watched_build_profile)

    scoring.score_source('bluesky', NOW)

    assert seen['version'] == source_config_version()


def test_scoring_clears_old_and_sql_null_scores_inside_its_lookback(rows):
    steady_history()
    scored_at = NOW - dt.timedelta(days=1)
    for ticker, version in (('SSOLD', 'old-generation'), ('SSNULL', None)):
        db.session.add(RadarBucketSource(
            ticker=ticker, bucket_start=scored_at, source='bluesky',
            mention_count=9, high_confidence_count=9, low_count=0,
            distinct_authors=9, distinct_text_ratio=1.0,
            engagement_weighted_count=9.0, status='ok',
            source_config_version=version, expected=3.0, variance=4.0,
            mention_z=3.0, baseline_days=20))
    db.session.commit()

    scoring.score_source('bluesky', NOW)

    incompatible = (RadarBucketSource.query
                    .filter(RadarBucketSource.ticker.in_(['SSOLD', 'SSNULL']))
                    .order_by(RadarBucketSource.ticker).all())
    assert len(incompatible) == 2
    for row in incompatible:
        assert row.expected is None
        assert row.variance is None
        assert row.mention_z is None
        assert row.baseline_days is None


def test_scoring_never_rescores_an_old_generation_row_mixed_with_current_history(rows):
    """A current baseline must not make an incompatible row look current."""
    steady_history(ticker='ZZGEN')
    old_at = NOW - dt.timedelta(minutes=15)
    add(old_at, 500, ticker='ZZGEN', version='old-generation')
    db.session.commit()

    scoring.score_source('bluesky', NOW)

    old = RadarBucketSource.query.filter_by(
        ticker='ZZGEN', bucket_start=old_at, source='bluesky').one()
    assert old.mention_z is None


def test_invalidation_skips_an_already_unscored_incompatible_row(rows):
    since = NOW - dt.timedelta(days=1)
    for ticker, score in (('ZZSCORED', 3.0), ('ZZUNSCORED', None)):
        db.session.add(RadarBucketSource(
            ticker=ticker, bucket_start=NOW - dt.timedelta(hours=1),
            source='bluesky', mention_count=5, high_confidence_count=5,
            low_count=0, distinct_authors=5, distinct_text_ratio=1.0,
            engagement_weighted_count=5.0, status='ok',
            source_config_version='old-generation', expected=2.0 if score else None,
            variance=3.0 if score else None, mention_z=score,
            baseline_days=10 if score else None))
    db.session.commit()

    cleared = scoring.invalidate_incompatible_scores(
        source_config_version(), since)

    assert cleared == 1
    assert RadarBucketSource.query.filter_by(ticker='ZZUNSCORED').one().mention_z is None


def test_scoring_invalidates_only_its_active_source(rows):
    since = NOW - dt.timedelta(hours=1)
    for source in ('reddit', 'bluesky'):
        db.session.add(RadarBucketSource(
            ticker='ZZSCOPE', bucket_start=NOW - dt.timedelta(minutes=15),
            source=source, mention_count=5, high_confidence_count=5,
            low_count=0, distinct_authors=5, distinct_text_ratio=1.0,
            engagement_weighted_count=5.0, status='ok',
            source_config_version='old-generation', expected=2.0, variance=3.0,
            mention_z=3.0, baseline_days=10))
    db.session.commit()

    scoring.score_source('reddit', NOW)

    assert RadarBucketSource.query.filter_by(
        ticker='ZZSCOPE', source='reddit').one().mention_z is None
    assert RadarBucketSource.query.filter_by(
        ticker='ZZSCOPE', source='bluesky').one().mention_z == 3.0


def test_pooling_sums_components_not_z_scores(rows):
    """A weighted mean of z-scores is not a z-score. Two sources each two
    sigma over is stronger evidence than either alone, and averaging would
    report the same two.

    The second source is a CONCRETE subreddit name. pooled_z takes a viewer
    selection and expands it strictly, so the bare `reddit` would now expand
    to the eight configured subs and match nothing these fixtures wrote."""
    for source in (REDDIT, 'bluesky'):
        steady_history(source=source)
    loud = MONDAY + dt.timedelta(days=20)
    db.session.commit()
    RadarBucketSource.query.filter_by(ticker='SSA', bucket_start=loud).update(
        {'mention_count': 12})
    db.session.commit()

    for source in (REDDIT, 'bluesky'):
        scoring.score_source(source, NOW)

    single, n_single = scoring.pooled_z('SSA', loud, [REDDIT])
    both, n_both = scoring.pooled_z('SSA', loud, [REDDIT, 'bluesky'])
    assert n_single == 1 and n_both == 2
    assert both > single


def test_pooling_ignores_unselected_sources(rows):
    for source in (REDDIT, 'bluesky'):
        steady_history(source=source)
    when = MONDAY + dt.timedelta(days=10)
    db.session.commit()
    for source in (REDDIT, 'bluesky'):
        scoring.score_source(source, NOW)

    _, n = scoring.pooled_z('SSA', when, ['bluesky'])
    assert n == 1


def test_a_missing_source_drops_out_rather_than_contributing_zero(rows):
    """The rule, at read time. A source that was down must not drag the pooled
    reading towards nothing."""
    for source in (REDDIT, 'bluesky'):
        steady_history(source=source)
    when = MONDAY + dt.timedelta(days=10)
    db.session.commit()
    RadarBucketSource.query.filter_by(
        ticker='SSA', bucket_start=when, source='bluesky').update(
        {'status': 'missing', 'mention_count': 0})
    db.session.commit()
    for source in (REDDIT, 'bluesky'):
        scoring.score_source(source, NOW)

    pooled, n = scoring.pooled_z('SSA', when, [REDDIT, 'bluesky'])
    only, _ = scoring.pooled_z('SSA', when, [REDDIT])
    assert n == 1
    assert pooled == pytest.approx(only)


def test_pooling_nothing_returns_none(rows):
    assert scoring.pooled_z('SSNOPE', MONDAY, ['bluesky']) == (None, 0)


def test_pooled_z_excludes_pre_split_root_reddit_scores(rows):
    when = MONDAY + dt.timedelta(days=10)
    for source, mentions, expected, variance, authors, version in (
            (REDDIT, 5, 1.0, 4.0, 3, source_config_version()),
            ('reddit', 1001, 1.0, 1.0, 99, '8106787f1fa72179')):
        db.session.add(RadarBucketSource(
            ticker='ZZM2POOL', bucket_start=when, source=source,
            mention_count=mentions, high_confidence_count=mentions,
            low_count=0, distinct_authors=authors,
            distinct_text_ratio=0.8,
            engagement_weighted_count=float(mentions), status='ok',
            source_config_version=version, expected=expected,
            variance=variance, mention_z=2.0, baseline_days=12))
    db.session.commit()

    pooled, contributing = scoring.pooled_z('ZZM2POOL', when, ['reddit'])

    assert pooled == 2.0
    assert contributing == 1


def _forum(mentions=10, voices=6, text_ratio=0.9):
    return {'forum': scoring.Contribution(mentions, voices, text_ratio)}


def _broadcast(mentions=10, voices=2, text_ratio=0.9):
    return {'broadcast': scoring.Contribution(mentions, voices, text_ratio)}


def test_a_forum_ticker_needs_three_voices():
    assert scoring.is_eligible(_forum(voices=6)) is True
    assert scoring.is_eligible(_forum(voices=2)) is False


def test_volume_alone_is_never_enough():
    """One determined account can supply any volume."""
    assert scoring.is_eligible(_forum(mentions=50, voices=1)) is False


def test_copy_paste_is_never_enough():
    """Fifty accounts pasting one message defeat the voice gate completely."""
    assert scoring.is_eligible(_forum(mentions=50, voices=50, text_ratio=0.02)) is False


def test_too_few_mentions_is_never_enough():
    assert scoring.is_eligible(_forum(mentions=2, voices=2)) is False


def test_a_broadcast_ticker_qualifies_on_two_channels():
    """The whole reason this changed. A Telegram channel has one author by
    construction, so under the author gate a broadcast-only ticker could never
    reach the board however loud it got."""
    assert scoring.is_eligible(_broadcast(voices=2)) is True
    assert scoring.is_eligible(_broadcast(voices=1)) is False


def test_a_broadcast_ticker_still_needs_distinct_wording():
    """One channel's forty reposts must not become forty mentions, and two
    channels reposting each other must not become corroboration."""
    assert scoring.is_eligible(_broadcast(voices=2, text_ratio=0.02)) is False


def test_either_kind_can_carry_a_ticker_alone():
    """A union, not an intersection: the ticker qualifies on whichever kind
    can vouch for it, and a kind that cannot does not veto the one that can."""
    mixed = {**_forum(voices=6), **_broadcast(voices=1)}
    assert scoring.is_eligible(mixed) is True

    other = {**_forum(voices=1), **_broadcast(voices=3)}
    assert scoring.is_eligible(other) is True


def test_nothing_at_all_is_not_eligible():
    assert scoring.is_eligible({}) is False


def test_an_unknown_kind_is_judged_as_a_forum():
    unknown = {'something-new': scoring.Contribution(10, 2, 0.9)}
    assert scoring.is_eligible(unknown) is False


def test_a_window_aggregates_its_buckets(rows):
    steady_history()
    db.session.commit()
    scoring.score_source('bluesky', NOW)
    end = MONDAY + dt.timedelta(days=20)

    _, parts_1h = scoring.window_z('SSA', ['bluesky'], end, hours=1)
    _, parts_4h = scoring.window_z('SSA', ['bluesky'], end, hours=4)
    assert parts_4h['mentions'] > parts_1h['mentions']
    assert parts_4h['expected'] > parts_1h['expected']


def test_a_window_with_no_scored_buckets_is_none(rows):
    assert scoring.window_z('SSNOPE', ['bluesky'], NOW, hours=1) == (None, {})


def test_window_z_excludes_pre_split_root_reddit_scores(rows):
    end = MONDAY + dt.timedelta(days=10, hours=1)
    when = end - dt.timedelta(minutes=15)
    for source, mentions, expected, variance, authors, ratio, version in (
            (REDDIT, 5, 1.0, 4.0, 3, 0.8, source_config_version()),
            ('reddit', 1001, 1.0, 1.0, 99, 0.1, '8106787f1fa72179')):
        db.session.add(RadarBucketSource(
            ticker='ZZM2WINDOW', bucket_start=when, source=source,
            mention_count=mentions, high_confidence_count=mentions,
            low_count=0, distinct_authors=authors,
            distinct_text_ratio=ratio,
            engagement_weighted_count=float(mentions), status='ok',
            source_config_version=version, expected=expected,
            variance=variance, mention_z=2.0, baseline_days=12))
    db.session.commit()

    score, parts = scoring.window_z(
        'ZZM2WINDOW', ['reddit'], end, hours=1)

    assert score == 2.0
    assert parts == {
        'mentions': 5,
        'expected': 1.0,
        'variance': 4.0,
        'authors': 3,
        'text_ratio': pytest.approx(0.8),
        'buckets': 1,
    }


def test_sustained_needs_several_non_overlapping_hours(rows):
    """1h, 4h and 24h are nested, so one loud hour lifts all three and
    "elevated in all three" would just restate it. Sustained is measured over
    consecutive separate hours instead (spec 6.9)."""
    steady_history()
    end = MONDAY + dt.timedelta(days=20)
    db.session.commit()

    for step in range(4):                      # one loud hour only
        RadarBucketSource.query.filter_by(
            ticker='SSA',
            bucket_start=end - dt.timedelta(minutes=15 * (step + 1))).update(
            {'mention_count': 40})
    db.session.commit()
    scoring.score_source('bluesky', NOW)
    assert scoring.is_sustained('SSA', ['bluesky'], end) is False

    for step in range(12):                     # three of the last four hours
        RadarBucketSource.query.filter_by(
            ticker='SSA',
            bucket_start=end - dt.timedelta(minutes=15 * (step + 1))).update(
            {'mention_count': 40})
    db.session.commit()
    scoring.score_source('bluesky', NOW)
    assert scoring.is_sustained('SSA', ['bluesky'], end) is True


def row(external_id, minute=0, hour=14, ticker='ZZA', source='bluesky'):
    """A MentionRow for the fractional-baseline test below.

    test_radar_buckets.row() (whose clean_buckets fixture is reused above)
    hardcodes hour=14, which would collapse all three of that test's
    roll_up calls onto the same 14:00 bucket -- span would be zero and the
    assertion the test exists to make would never pass, before or after the
    fix. This local row() takes `hour` explicitly so the three calls land in
    three separate buckets, the way the scenario needs.
    """
    return buckets.MentionRow(
        ticker=ticker, external_id=external_id,
        created_utc=dt.datetime(2026, 4, 15, hour, minute, 0),
        source=source, channel='c', author='u1', simhash=111,
        confidence='high', sentiment=0.5, engagement=10.0)


def test_a_baseline_shorter_than_a_day_is_not_reported_as_zero_days(clean_buckets):
    """span.days truncates. Twenty-three hours of history is not no history,
    and reporting it as zero put every row on the board permanently
    provisional -- 147,228 of 147,429 in production."""
    import datetime as dt

    from features.radar import buckets, scoring
    from models import RadarBucketSource

    now = dt.datetime(2026, 4, 16, 14, 0, 0)
    for hour in (14, 20, 23):
        start = dt.datetime(2026, 4, 15, hour, 0, 0)
        buckets.roll_up([row(external_id='zz-%d' % hour, minute=0, hour=hour)],
                        {'bluesky': 'ok'}, {start})

    scoring.score_source('bluesky', now)

    scored = RadarBucketSource.query.filter_by(
        ticker='ZZA', source='bluesky').first()
    assert 0 < scored.baseline_days < 1


# --- pass cost (measured 2026-09-03) ----------------------------------------

def test_each_ticker_is_screened_once_per_pass(rows, monkeypatch):
    """Both passes over the tickers ask usable() the same question of the
    same rows. Building the observations twice was most of a 28-minute
    pass once the Arctic Shift backfill filled every source's 30-day
    window: 4,839 tickers on r/wallstreetbets alone, times 36 sources.

    The two weekly_rate calls are NOT redundant -- the second carries the
    prior -- so this pins the screening only.
    """
    steady_history(ticker='SSA', source=REDDIT)
    steady_history(ticker='SSB', source=REDDIT)
    db.session.commit()

    screened = []
    original = scoring.baselines.usable

    def counted(observations, config_version, excluded):
        screened.append(len(observations))
        return original(observations, config_version, excluded)

    monkeypatch.setattr(scoring.baselines, 'usable', counted)
    scoring.score_source(REDDIT, NOW)

    assert len(screened) == 2, f'{len(screened)} screenings for 2 tickers'
    assert all(count > 0 for count in screened)


def test_the_scores_survive_screening_once(rows):
    """The refactor must not move a single number: same rows, same z."""
    steady_history(ticker='SSA', source=REDDIT)
    loud = MONDAY + dt.timedelta(days=20)
    db.session.commit()
    RadarBucketSource.query.filter_by(
        ticker='SSA', bucket_start=loud, source=REDDIT).update({'mention_count': 60})
    db.session.commit()

    scoring.score_source(REDDIT, NOW)
    row = RadarBucketSource.query.filter_by(
        ticker='SSA', bucket_start=loud, source=REDDIT).one()

    assert row.mention_z > 5
    assert row.expected is not None and row.variance is not None
    assert row.baseline_days > 14


# --- the write tolerance (measured 2026-09-03) ------------------------------

class _Stored:
    def __init__(self, expected, variance, mention_z, baseline_days):
        self.expected, self.variance = expected, variance
        self.mention_z, self.baseline_days = mention_z, baseline_days


def test_a_recompute_within_tolerance_is_not_written():
    """Every value drifts ~0.1% per pass because the profile is normalised
    over the whole window; rewriting 4.5M rows for that was 15 minutes of
    a 28-minute pass. Inside tolerance the stored row stands."""
    row = _Stored(expected=2.000, variance=4.000, mention_z=1.500, baseline_days=29.90)
    assert scoring._worth_writing(row, 2.002, 4.004, 1.505, 29.95) is False


def test_a_real_move_is_written():
    row = _Stored(expected=2.000, variance=4.000, mention_z=1.500, baseline_days=29.90)
    assert scoring._worth_writing(row, 2.10, 4.000, 1.500, 29.90) is True      # expected +5%
    assert scoring._worth_writing(row, 2.000, 4.000, 1.60, 29.90) is True      # z +0.1
    assert scoring._worth_writing(row, 2.000, 4.000, 1.500, 30.50) is True     # days +0.6


def test_crossing_a_threshold_always_writes_however_small_the_move():
    """The board compares against ELEVATED_Z and the mark against
    PROVISIONAL_BASELINE_DAYS. A crossing must never be seen late, so it
    writes even when the move is inside the tolerance."""
    from features.radar.config import ELEVATED_Z, PROVISIONAL_BASELINE_DAYS
    row = _Stored(expected=2.0, variance=4.0, mention_z=ELEVATED_Z - 0.005,
                  baseline_days=PROVISIONAL_BASELINE_DAYS - 0.05)
    assert scoring._worth_writing(row, 2.0, 4.0, ELEVATED_Z + 0.005, row.baseline_days) is True
    assert scoring._worth_writing(row, 2.0, 4.0, row.mention_z, PROVISIONAL_BASELINE_DAYS + 0.05) is True
    # ...and the same tiny moves that cross nothing are left alone.
    assert scoring._worth_writing(row, 2.0, 4.0, row.mention_z - 0.005, row.baseline_days - 0.05) is False


def test_a_never_scored_row_is_always_written():
    row = _Stored(expected=None, variance=None, mention_z=None, baseline_days=None)
    assert scoring._worth_writing(row, 0.0, 0.0, 0.0, 0.0) is True


def test_scoring_the_same_rows_twice_writes_nothing_the_second_time(rows):
    """The end-to-end form of the tolerance: identical inputs, identical
    outputs, zero rows rewritten -- and the stored values are the same
    scores the first pass produced."""
    steady_history(source=REDDIT)
    db.session.commit()
    first = scoring.score_source(REDDIT, NOW)
    assert first > 0
    before = {(r.ticker, r.bucket_start): (r.expected, r.variance, r.mention_z, r.baseline_days)
              for r in RadarBucketSource.query.filter_by(source=REDDIT).all()}
    second = scoring.score_source(REDDIT, NOW)
    after = {(r.ticker, r.bucket_start): (r.expected, r.variance, r.mention_z, r.baseline_days)
             for r in RadarBucketSource.query.filter_by(source=REDDIT).all()}
    assert second == 0
    assert after == before


def test_scoring_writes_only_under_the_bucket_write_lock(rows, monkeypatch):
    """The scoring pass is the third writer of radar_bucket_sources. Its
    flush held row locks for up to a minute per source, and a cycle's
    roll_up deadlocked against it once per pass (11 of 11 Reddit cycles,
    evening of 2026-09-03). Both of its writes -- the invalidation UPDATE
    and the score flush -- go through buckets.BUCKET_WRITE_LOCK, and the
    reads and arithmetic between them do not."""
    entries = []

    class Lock:
        def __enter__(self):
            entries.append('enter')

        def __exit__(self, *exc):
            entries.append('exit')
            return False

    steady_history(source=REDDIT)
    db.session.commit()
    monkeypatch.setattr(scoring.buckets, 'BUCKET_WRITE_LOCK', Lock())
    written = scoring.score_source(REDDIT, NOW)

    assert written > 0
    assert entries == ['enter', 'exit', 'enter', 'exit'], entries

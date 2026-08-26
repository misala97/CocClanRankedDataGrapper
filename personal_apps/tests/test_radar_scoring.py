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
from features.radar import scoring
from features.radar.config import source_config_version

MONDAY = dt.datetime(2026, 8, 17, 0, 0, 0)
NOW = MONDAY + dt.timedelta(days=35)
_OWNED_TICKERS = (
    'SSA', 'SSB', 'SSNEW', 'SSOLD', 'SSNULL',
    'ZZGEN', 'ZZSCORED', 'ZZSCOPE', 'ZZUNSCORED',
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


def add(when, count, ticker='SSA', source='stocktwits', status='ok',
        version=None):
    db.session.add(RadarBucketSource(
        ticker=ticker, bucket_start=when, source=source,
        mention_count=count, high_confidence_count=count, low_count=0,
        distinct_authors=count, distinct_text_ratio=1.0,
        engagement_weighted_count=float(count), status=status,
        source_config_version=version or source_config_version()))


def steady_history(ticker='SSA', per_bucket=2, days=30, source='stocktwits'):
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
    scoring.score_source('stocktwits', NOW)

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

    scoring.score_source('stocktwits', NOW)
    assert RadarBucketSource.query.filter_by(
        ticker='SSA', bucket_start=loud).one().mention_z > 5


def test_expected_and_variance_are_stored_too(rows):
    """Pooling a user-selected subset means summing components, so the parts
    have to survive, not just the z (spec 6.2)."""
    steady_history()
    db.session.commit()
    scoring.score_source('stocktwits', NOW)

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

    scoring.score_source('stocktwits', NOW)
    assert RadarBucketSource.query.filter_by(
        ticker='SSA', bucket_start=gap).one().mention_z is None


def test_a_gap_does_not_depress_the_baseline(rows):
    """The observed-mass property, end to end. A week of outage must not make
    the ticker look like it went quiet, or everything after would spike."""
    steady_history()
    db.session.commit()
    scoring.score_source('stocktwits', NOW)
    reference = RadarBucketSource.query.filter_by(
        ticker='SSA', bucket_start=MONDAY + dt.timedelta(days=25)).one().mention_z

    outage_start = MONDAY + dt.timedelta(days=5)
    RadarBucketSource.query.filter(
        RadarBucketSource.ticker == 'SSA',
        RadarBucketSource.bucket_start >= outage_start,
        RadarBucketSource.bucket_start < outage_start + dt.timedelta(days=7)
    ).update({'status': 'missing', 'mention_count': 0}, synchronize_session=False)
    db.session.commit()

    scoring.score_source('stocktwits', NOW)
    after = RadarBucketSource.query.filter_by(
        ticker='SSA', bucket_start=MONDAY + dt.timedelta(days=25)).one().mention_z
    assert after == pytest.approx(reference, abs=0.5)


def test_baseline_days_is_recorded(rows):
    steady_history(days=30)
    db.session.commit()
    scoring.score_source('stocktwits', NOW)
    row = RadarBucketSource.query.filter_by(
        ticker='SSA', bucket_start=MONDAY + dt.timedelta(days=10)).one()
    assert row.baseline_days >= 14


def test_a_brand_new_ticker_is_provisional(rows):
    """Two days of history cannot support a z-score anyone should act on."""
    for step in range(2 * 96):
        add(NOW - dt.timedelta(days=2) + dt.timedelta(minutes=15 * step), 3,
            ticker='SSNEW')
    db.session.commit()
    scoring.score_source('stocktwits', NOW)

    row = (RadarBucketSource.query.filter_by(ticker='SSNEW')
           .order_by(RadarBucketSource.bucket_start.desc()).first())
    assert row.baseline_days < 14


def test_scoring_only_touches_its_own_source(rows):
    steady_history(source='stocktwits')
    steady_history(ticker='SSB', source='bluesky')
    db.session.commit()
    scoring.score_source('stocktwits', NOW)

    assert RadarBucketSource.query.filter_by(
        ticker='SSB', source='bluesky').first().mention_z is None


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

    scoring.score_source('stocktwits', NOW)

    assert seen['version'] == source_config_version()


def test_scoring_clears_old_and_sql_null_scores_inside_its_lookback(rows):
    steady_history()
    scored_at = NOW - dt.timedelta(days=1)
    for ticker, version in (('SSOLD', 'old-generation'), ('SSNULL', None)):
        db.session.add(RadarBucketSource(
            ticker=ticker, bucket_start=scored_at, source='stocktwits',
            mention_count=9, high_confidence_count=9, low_count=0,
            distinct_authors=9, distinct_text_ratio=1.0,
            engagement_weighted_count=9.0, status='ok',
            source_config_version=version, expected=3.0, variance=4.0,
            mention_z=3.0, baseline_days=20))
    db.session.commit()

    scoring.score_source('stocktwits', NOW)

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

    scoring.score_source('stocktwits', NOW)

    old = RadarBucketSource.query.filter_by(
        ticker='ZZGEN', bucket_start=old_at, source='stocktwits').one()
    assert old.mention_z is None


def test_invalidation_skips_an_already_unscored_incompatible_row(rows):
    since = NOW - dt.timedelta(days=1)
    for ticker, score in (('ZZSCORED', 3.0), ('ZZUNSCORED', None)):
        db.session.add(RadarBucketSource(
            ticker=ticker, bucket_start=NOW - dt.timedelta(hours=1),
            source='stocktwits', mention_count=5, high_confidence_count=5,
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
    for source in ('stocktwits', 'bluesky'):
        db.session.add(RadarBucketSource(
            ticker='ZZSCOPE', bucket_start=NOW - dt.timedelta(minutes=15),
            source=source, mention_count=5, high_confidence_count=5,
            low_count=0, distinct_authors=5, distinct_text_ratio=1.0,
            engagement_weighted_count=5.0, status='ok',
            source_config_version='old-generation', expected=2.0, variance=3.0,
            mention_z=3.0, baseline_days=10))
    db.session.commit()

    scoring.score_source('stocktwits', NOW)

    assert RadarBucketSource.query.filter_by(
        ticker='ZZSCOPE', source='stocktwits').one().mention_z is None
    assert RadarBucketSource.query.filter_by(
        ticker='ZZSCOPE', source='bluesky').one().mention_z == 3.0


def test_pooling_sums_components_not_z_scores(rows):
    """A weighted mean of z-scores is not a z-score. Two sources each two
    sigma over is stronger evidence than either alone, and averaging would
    report the same two."""
    for source in ('stocktwits', 'bluesky'):
        steady_history(source=source)
    loud = MONDAY + dt.timedelta(days=20)
    db.session.commit()
    RadarBucketSource.query.filter_by(ticker='SSA', bucket_start=loud).update(
        {'mention_count': 12})
    db.session.commit()

    for source in ('stocktwits', 'bluesky'):
        scoring.score_source(source, NOW)

    single, n_single = scoring.pooled_z('SSA', loud, ['stocktwits'])
    both, n_both = scoring.pooled_z('SSA', loud, ['stocktwits', 'bluesky'])
    assert n_single == 1 and n_both == 2
    assert both > single


def test_pooling_ignores_unselected_sources(rows):
    for source in ('stocktwits', 'bluesky'):
        steady_history(source=source)
    when = MONDAY + dt.timedelta(days=10)
    db.session.commit()
    for source in ('stocktwits', 'bluesky'):
        scoring.score_source(source, NOW)

    _, n = scoring.pooled_z('SSA', when, ['bluesky'])
    assert n == 1


def test_a_missing_source_drops_out_rather_than_contributing_zero(rows):
    """The rule, at read time. A source that was down must not drag the pooled
    reading towards nothing."""
    for source in ('stocktwits', 'bluesky'):
        steady_history(source=source)
    when = MONDAY + dt.timedelta(days=10)
    db.session.commit()
    RadarBucketSource.query.filter_by(
        ticker='SSA', bucket_start=when, source='bluesky').update(
        {'status': 'missing', 'mention_count': 0})
    db.session.commit()
    for source in ('stocktwits', 'bluesky'):
        scoring.score_source(source, NOW)

    pooled, n = scoring.pooled_z('SSA', when, ['stocktwits', 'bluesky'])
    only, _ = scoring.pooled_z('SSA', when, ['stocktwits'])
    assert n == 1
    assert pooled == pytest.approx(only)


def test_pooling_nothing_returns_none(rows):
    assert scoring.pooled_z('SSNOPE', MONDAY, ['stocktwits']) == (None, 0)


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
    scoring.score_source('stocktwits', NOW)
    end = MONDAY + dt.timedelta(days=20)

    _, parts_1h = scoring.window_z('SSA', ['stocktwits'], end, hours=1)
    _, parts_4h = scoring.window_z('SSA', ['stocktwits'], end, hours=4)
    assert parts_4h['mentions'] > parts_1h['mentions']
    assert parts_4h['expected'] > parts_1h['expected']


def test_a_window_with_no_scored_buckets_is_none(rows):
    assert scoring.window_z('SSNOPE', ['stocktwits'], NOW, hours=1) == (None, {})


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
    scoring.score_source('stocktwits', NOW)
    assert scoring.is_sustained('SSA', ['stocktwits'], end) is False

    for step in range(12):                     # three of the last four hours
        RadarBucketSource.query.filter_by(
            ticker='SSA',
            bucket_start=end - dt.timedelta(minutes=15 * (step + 1))).update(
            {'mention_count': 40})
    db.session.commit()
    scoring.score_source('stocktwits', NOW)
    assert scoring.is_sustained('SSA', ['stocktwits'], end) is True

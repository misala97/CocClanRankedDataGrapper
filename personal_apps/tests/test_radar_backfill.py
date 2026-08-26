# personal_apps/tests/test_radar_backfill.py
"""One-shot repair for the buckets the pre-2026-08-26 rollup truncated.

roll_up rebuilt each bucket from one cycle's cursor slice and overwrote, so a
quarter-hour touched by several cycles kept only the last one. This suite
pins scripts.backfill_radar_buckets.repair(): it must recover the retained
`high` lower bound from radar_posts x radar_mentions, never regress a column,
never restamp a partially-repaired row onto the current rollup generation,
and clear a stale score off any row whose status is no longer `ok` -- keyed
on ANY of the four scoring columns, not just mention_z.

All fixtures live under the ZZBF ticker namespace and channel
'zzbf-backfill-test', cleaned up by exact identity (never a broad LIKE 'ZZ%'
sweep, which would reach other suites' and the user's real data) both before
and after every test. Every call into repair() passes ticker_prefix='ZZBF' so
a bug here cannot touch the live board's rows.
"""
import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from models import RadarBucketSource, RadarMention, RadarPost
from scripts import backfill_radar_buckets as backfill

BS = dt.datetime(2026, 4, 15, 14, 0, 0)
CHANNEL = 'zzbf-backfill-test'
TICKERS = ('ZZBF1', 'ZZBF2', 'ZZBF3', 'ZZBF4', 'ZZBF5')


def _wipe():
    RadarBucketSource.query.filter(
        RadarBucketSource.ticker.in_(TICKERS)).delete(synchronize_session=False)
    # ondelete='CASCADE' on radar_mentions.post_id (see models.py / migration
    # 7883c6e08708) takes radar_mentions with it -- no separate delete needed.
    RadarPost.query.filter(RadarPost.channel == CHANNEL).delete(
        synchronize_session=False)
    db.session.commit()


@pytest.fixture()
def clean():
    with flask_app.app_context():
        _wipe()
        yield
        _wipe()


def _source_row(ticker, source='bluesky', bucket_start=BS, **overrides):
    fields = dict(
        ticker=ticker, bucket_start=bucket_start, source=source,
        mention_count=1, high_confidence_count=1, low_count=0,
        distinct_authors=1, distinct_text_ratio=1.0,
        engagement_weighted_count=1.0, sentiment_mean=None,
        sentiment_stdev=None, status='ok', source_config_version=None,
        expected=None, variance=None, mention_z=None, baseline_days=None)
    fields.update(overrides)
    row = RadarBucketSource(**fields)
    db.session.add(row)
    return row


_seq = [0]


def _post(ticker, author, simhash, score=0, num_comments=0, source='bluesky',
          minute=5, confidence='high'):
    """A stored high-confidence post + its mention -- exactly the population
    _TRUTH recovers. created_utc lands inside BS's quarter-hour by default."""
    _seq[0] += 1
    when = BS + dt.timedelta(minutes=minute)
    external_id = 'zzbf-%d' % _seq[0]
    post = RadarPost(source=source, external_id=external_id, channel=CHANNEL,
                     author=author, created_utc=when, title=None, body='x',
                     score=score, num_comments=num_comments,
                     url='https://example.invalid/', simhash=simhash,
                     first_seen=when, last_seen=when)
    db.session.add(post)
    db.session.flush()
    db.session.add(RadarMention(post_id=post.id, ticker=ticker,
                                confidence=confidence, lexicon_sentiment=0.0))


def _reread(ticker, source='bluesky'):
    """A genuinely fresh read, not just an in-memory one.

    expire_all() alone clears this session's Python-side identity-map cache,
    but repair() commits through its OWN nested app_context session (Flask-
    SQLAlchemy scopes db.session per app-context id). If THIS session's own
    transaction is still open from an earlier read -- MySQL's default
    REPEATABLE READ fixes a snapshot at that read -- expire_all() forces a
    requery but that requery runs inside the SAME frozen snapshot, so it can
    still miss a commit repair() made from its own session in the meantime.
    rollback() ends this session's transaction so the requery below opens a
    new one and actually observes it.
    """
    db.session.rollback()
    db.session.expire_all()
    return RadarBucketSource.query.filter_by(
        ticker=ticker, bucket_start=BS, source=source).one()


# --- 1. Dry-run reports but never writes -------------------------------------

def test_dry_run_reports_an_understated_row_but_writes_nothing(clean):
    _source_row('ZZBF1', high_confidence_count=1, mention_count=1,
               distinct_authors=1, distinct_text_ratio=1.0,
               engagement_weighted_count=1.0, status='ok',
               source_config_version='old-gen-1')
    db.session.commit()
    # Truth: 2 posts, 2 authors, 1 shared simhash (a copy-paste pair), engagement 6.
    _post('ZZBF1', 'u1', simhash=999, score=3, num_comments=2)
    _post('ZZBF1', 'u2', simhash=999, score=1, num_comments=0)
    db.session.commit()

    report = backfill.repair(apply=False, ticker_prefix='ZZBF')
    assert report['examined'] == 1
    assert report['repaired'] == 1
    assert report['stale_scores'] == 0

    row = _reread('ZZBF1')
    assert row.high_confidence_count == 1
    assert row.mention_count == 1
    assert row.distinct_authors == 1
    assert row.distinct_text_ratio == 1.0
    assert row.engagement_weighted_count == 1.0
    assert row.status == 'ok'
    assert row.source_config_version == 'old-gen-1'
    assert row.expected is None
    assert row.variance is None
    assert row.mention_z is None
    assert row.baseline_days is None


# --- 2. Apply repairs, converts Decimal, clears scores, preserves identity,
#        never restamps the generation, and a second apply is a no-op --------

def test_apply_repairs_clears_scores_preserves_generation_and_is_idempotent(clean):
    _source_row('ZZBF2', high_confidence_count=1, mention_count=1,
               distinct_authors=1, distinct_text_ratio=1.0,
               engagement_weighted_count=1.0, status='ok',
               source_config_version='old-gen-2',
               expected=2.0, variance=0.5, mention_z=9.9, baseline_days=10)
    db.session.commit()
    # Truth: 3 posts / 3 authors, two share a simhash -> 2 distinct hashes,
    # engagement (score+num_comments) 8 + 3 + 1 = 12.
    _post('ZZBF2', 'u1', simhash=111, score=5, num_comments=3)
    _post('ZZBF2', 'u2', simhash=111, score=2, num_comments=1)
    _post('ZZBF2', 'u3', simhash=222, score=0, num_comments=1)
    db.session.commit()

    report = backfill.repair(apply=True, ticker_prefix='ZZBF')
    assert report['examined'] == 1
    assert report['repaired'] == 1

    row = _reread('ZZBF2')
    assert row.high_confidence_count == 3
    assert row.mention_count == 3
    assert row.distinct_authors == 3
    assert row.distinct_text_ratio == pytest.approx(2 / 3)
    assert row.engagement_weighted_count == pytest.approx(12.0)
    # Identity preserved: apply repairs counts, it does not re-judge status,
    # and a partial repair must never look like current-generation data.
    assert row.status == 'ok'
    assert row.source_config_version == 'old-gen-2'
    # The score was computed off the understated count and must not survive.
    assert row.expected is None
    assert row.variance is None
    assert row.mention_z is None
    assert row.baseline_days is None

    second = backfill.repair(apply=True, ticker_prefix='ZZBF')
    assert second['repaired'] == 0


# --- 3. Equality on one column must not short-circuit the others ------------

def test_equal_high_confidence_count_does_not_block_other_repairs(clean):
    _source_row('ZZBF3', high_confidence_count=2, mention_count=2,
               distinct_authors=1, distinct_text_ratio=1.0,
               engagement_weighted_count=1.0, status='ok',
               source_config_version='old-gen-3')
    db.session.commit()
    # Truth: exactly 2 high mentions (matches high_confidence_count/mention_count
    # already on the row) but 2 authors and a shared simhash and real engagement
    # -- retained posts can refresh those columns after the bucket was written.
    _post('ZZBF3', 'u1', simhash=555, score=4, num_comments=1)
    _post('ZZBF3', 'u2', simhash=555, score=3, num_comments=2)
    db.session.commit()

    report = backfill.repair(apply=True, ticker_prefix='ZZBF')
    assert report['repaired'] == 1

    row = _reread('ZZBF3')
    assert row.high_confidence_count == 2      # unchanged: already equal
    assert row.mention_count == 2               # unchanged: already equal
    assert row.distinct_authors == 2            # still repaired
    assert row.distinct_text_ratio == pytest.approx(0.5)  # still repaired
    assert row.engagement_weighted_count == pytest.approx(10.0)  # still repaired


# --- 4. Stale scores clear on ANY non-NULL scoring column, keyed off status,
#        and never on dry-run or on a row that is still `ok` ----------------

def test_stale_scores_clear_on_any_column_and_only_for_non_ok_status(clean):
    # No retained high mentions at all -- this row is reachable only through
    # the second, status-driven pass, exactly the case the pre-existing
    # rollup fix (Task 3) could never revisit.
    _source_row('ZZBF4', status='truncated', source_config_version='old-gen-4',
               expected=None, variance=None, mention_z=None, baseline_days=7)
    # Control: still `ok`, so its (legitimately earned) score must survive.
    _source_row('ZZBF5', status='ok', source_config_version='old-gen-5',
               expected=1.1, variance=2.2, mention_z=3.3, baseline_days=14)
    db.session.commit()

    dry = backfill.repair(apply=False, ticker_prefix='ZZBF')
    assert dry['stale_scores'] == 1

    stale = _reread('ZZBF4')
    assert stale.baseline_days == 7            # untouched on dry-run
    assert stale.status == 'truncated'
    ok_row = _reread('ZZBF5')
    assert ok_row.mention_z == 3.3              # untouched on dry-run

    applied = backfill.repair(apply=True, ticker_prefix='ZZBF')
    assert applied['stale_scores'] == 1

    stale = _reread('ZZBF4')
    assert stale.expected is None
    assert stale.variance is None
    assert stale.mention_z is None
    assert stale.baseline_days is None          # cleared though never set itself
    assert stale.status == 'truncated'           # status is read, not rewritten
    assert stale.source_config_version == 'old-gen-4'  # never restamped

    ok_row = _reread('ZZBF5')
    assert ok_row.mention_z == 3.3               # an `ok` row keeps its score
    assert ok_row.expected == 1.1
    assert ok_row.variance == 2.2
    assert ok_row.baseline_days == 14

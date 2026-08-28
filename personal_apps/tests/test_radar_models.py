# personal_apps/tests/test_radar_models.py
"""Schema guards for the MariaDB specifics in spec 5.4.

These assert against the live dev database rather than the model metadata,
because the failures they guard against -- a rejected 4-byte insert, a
truncated body, a case-insensitive symbol match -- happen in the database and
not in SQLAlchemy.
"""
import datetime as dt

import pytest
import sqlalchemy as sa

from app import app as flask_app
from extensions import db
import models
from models import RadarBucket, RadarMention, RadarPost, TickerUniverse


@pytest.fixture()
def ctx():
    with flask_app.app_context():
        yield


def _make_post(**overrides):
    fields = dict(
        source='reddit',
        external_id='t3_test_%s' % dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).timestamp(),
        channel='wallstreetbets',
        author='someone',
        created_utc=dt.datetime(2026, 4, 15, 14, 0, 0),
        title='title',
        body='body',
        score=1,
        num_comments=0,
        url='https://example.invalid/x',
        simhash=0,
        first_seen=dt.datetime(2026, 4, 15, 14, 1, 0),
        last_seen=dt.datetime(2026, 4, 15, 14, 1, 0),
    )
    fields.update(overrides)
    return RadarPost(**fields)


def test_four_byte_characters_round_trip(ctx):
    """MariaDB's utf8 alias is utf8mb3 and would reject this. WSB posts are
    full of emoji, and a rejected insert is a silently dropped mention."""
    body = 'to the moon \U0001F680\U0001F4C8 diamond hands \U0001F48E\U0001F64C'
    post = _make_post(body=body)
    db.session.add(post)
    db.session.commit()
    db.session.expire(post)
    assert post.body == body
    db.session.delete(post)
    db.session.commit()


def test_body_holds_more_than_the_text_limit(ctx):
    """Reddit self-posts run to 40k characters, which exceeds TEXT under
    utf8mb4. MEDIUMTEXT or the tail is silently cut."""
    body = 'x' * 40000
    post = _make_post(body=body)
    db.session.add(post)
    db.session.commit()
    db.session.expire(post)
    assert len(post.body) == 40000
    db.session.delete(post)
    db.session.commit()


def test_symbol_lookup_is_case_sensitive(ctx):
    """utf8mb4_bin is what stops 'it' matching ticker IT. The cost is that
    extraction must uppercase before it looks anything up."""
    db.session.add(TickerUniverse(symbol='ZZTOP', name='Test Corp',
                                  exchange='TEST',
                                  first_seen=dt.datetime(2026, 1, 1)))
    db.session.commit()
    assert TickerUniverse.query.filter_by(symbol='ZZTOP').count() == 1
    assert TickerUniverse.query.filter_by(symbol='zztop').count() == 0
    TickerUniverse.query.filter_by(symbol='ZZTOP').delete()
    db.session.commit()


def test_bucket_unique_key_rejects_a_duplicate(ctx):
    start = dt.datetime(2026, 4, 15, 14, 0, 0)
    first = RadarBucket(ticker='ZZTOP', bucket_start=start, mention_count=1,
                        high_confidence_count=1, distinct_authors=1,
                        distinct_text_ratio=1.0, engagement_weighted_count=1.0,
        sources_ok=1, source_config_version='deadbeefdeadbeef')
    db.session.add(first)
    db.session.commit()

    duplicate = RadarBucket(ticker='ZZTOP', bucket_start=start, mention_count=2,
                            high_confidence_count=2, distinct_authors=2,
                            distinct_text_ratio=1.0,
                            engagement_weighted_count=2.0,
        sources_ok=1, source_config_version='deadbeefdeadbeef')
    db.session.add(duplicate)
    with pytest.raises(sa.exc.IntegrityError):
        db.session.commit()
    db.session.rollback()

    RadarBucket.query.filter_by(ticker='ZZTOP').delete()
    db.session.commit()


def test_scoring_columns_start_null(ctx):
    """Plan 1 writes no scores. These columns exist so Plan 2 does not need a
    second migration, and they must be nullable until then."""
    start = dt.datetime(2026, 4, 15, 15, 0, 0)
    bucket = RadarBucket(ticker='ZZTOP', bucket_start=start, mention_count=1,
                         high_confidence_count=1, distinct_authors=1,
                         distinct_text_ratio=1.0, engagement_weighted_count=1.0,
        sources_ok=1, source_config_version='deadbeefdeadbeef')
    db.session.add(bucket)
    db.session.commit()
    db.session.expire(bucket)
    # Per-source scoring columns live on RadarBucketSource now; the parent
    # keeps only the all-sources totals.
    assert bucket.low_count == 0
    assert not hasattr(bucket, 'mention_z_reddit')
    db.session.delete(bucket)
    db.session.commit()


def test_mention_cascades_when_its_post_is_deleted(ctx):
    post = _make_post()
    db.session.add(post)
    db.session.commit()
    db.session.add(RadarMention(post_id=post.id, ticker='ZZTOP',
                                confidence='high', lexicon_sentiment=0.5))
    db.session.commit()
    post_id = post.id
    db.session.delete(post)
    db.session.commit()
    assert RadarMention.query.filter_by(post_id=post_id).count() == 0


def test_a_full_range_simhash_round_trips(ctx):
    """simhash64() fills all 64 bits. A signed BIGINT stops at 2**63-1, so a
    post whose text happens to hash high is rejected outright -- roughly half
    of them, decided purely by wording, which presents as an intermittent
    fault rather than the systematic one it is."""
    big = 2 ** 64 - 1
    post = _make_post(simhash=big)
    db.session.add(post)
    db.session.commit()
    db.session.expire(post)
    assert post.simhash == big
    db.session.delete(post)
    db.session.commit()


def test_the_low_confidence_tier_is_storable(ctx):
    """Extraction emits `low` for an uncorroborated bare token. Every mention
    fixture elsewhere uses cashtags, which resolve to `high`, so nothing else
    in the suite would notice the enum missing this value -- and under
    STRICT_TRANS_TABLES the first real bare mention would fail its insert."""
    post = _make_post()
    db.session.add(post)
    db.session.commit()
    for tier in ('high', 'medium', 'low'):
        db.session.add(RadarMention(post_id=post.id, ticker='ZZT',
                                    confidence=tier, lexicon_sentiment=0.0))
    db.session.commit()
    assert RadarMention.query.filter_by(post_id=post.id).count() == 3
    db.session.delete(post)
    db.session.commit()


def test_a_daily_close_is_unique_per_ticker_and_date():
    """One close per ticker per trading day. A second write for the same day
    replaces it rather than accumulating -- the provider restates recent bars,
    and duplicates would silently double the history a sparkline draws."""
    import datetime as dt
    import decimal
    from app import app as flask_app
    from extensions import db
    from models import RadarDailyClose

    with flask_app.app_context():
        RadarDailyClose.query.filter(
            RadarDailyClose.ticker == 'MDLZZ').delete(synchronize_session=False)
        db.session.commit()

        db.session.add(RadarDailyClose(
            ticker='MDLZZ', close_date=dt.date(2026, 8, 21),
            close=decimal.Decimal('12.3400'), fetched_at=dt.datetime(2026, 8, 22)))
        db.session.commit()

        stored = RadarDailyClose.query.filter_by(ticker='MDLZZ').one()
        assert stored.close_date == dt.date(2026, 8, 21)
        assert float(stored.close) == 12.34

        RadarDailyClose.query.filter(
            RadarDailyClose.ticker == 'MDLZZ').delete(synchronize_session=False)
        db.session.commit()


def test_market_models_expand_without_breaking_legacy_price_keys():
    """The expand stage adds context without requiring old writers to know it.

    Removing nullable=True would break the still-deployed ticker-only daemon;
    changing the legacy keys here would let Task 1 create two price rows that
    old readers cannot distinguish.
    """
    instrument = models.RadarInstrument(
        ticker='AAPL', market='de', venue='Xetra', mic='XETR',
        provider_symbol='APC', currency='EUR', isin='US0378331005',
        is_primary=True, mapping_status='mapped',
        mapping_source='twelvedata', mapped_at=dt.datetime(2026, 8, 28))
    quote = models.RadarQuote(
        ticker='AAPL', market='de', mic='XETR', currency='EUR',
        provider_symbol='APC', fetched_at=dt.datetime(2026, 8, 28),
        quote_ts=dt.datetime(2026, 8, 28), price=194.20)

    assert instrument.market == quote.market == 'de'
    assert instrument.currency == quote.currency == 'EUR'
    assert instrument.mic == quote.mic == 'XETR'

    quote_columns = models.RadarQuote.__table__.c
    close_columns = models.RadarDailyClose.__table__.c
    assert all(quote_columns[name].nullable for name in (
        'market', 'mic', 'currency', 'provider_symbol'))
    assert all(close_columns[name].nullable for name in (
        'market', 'mic', 'currency'))

    quote_unique = next(
        constraint for constraint in models.RadarQuote.__table__.constraints
        if isinstance(constraint, sa.UniqueConstraint))
    assert tuple(column.name for column in quote_unique.columns) == (
        'ticker', 'fetched_at')
    assert tuple(column.name for column in
                 models.RadarDailyClose.__table__.primary_key.columns) == (
        'ticker', 'close_date')

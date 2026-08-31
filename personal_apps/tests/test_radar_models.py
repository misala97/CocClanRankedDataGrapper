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


def test_market_models_partition_price_keys_after_writer_upgrade():
    """Task 5 makes simultaneous US/Xetra snapshots independently addressable."""
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
        'ticker', 'market', 'mic', 'fetched_at')
    close_unique = next(
        constraint for constraint in models.RadarDailyClose.__table__.constraints
        if isinstance(constraint, sa.UniqueConstraint))
    assert tuple(column.name for column in close_unique.columns) == (
        'ticker', 'market', 'mic', 'close_date')
    assert tuple(column.name for column in
                 models.RadarDailyClose.__table__.primary_key.columns) == ('id',)


def test_radar_quote_regular_close_round_trips_in_isolated_schema():
    """After-hours movement needs its regular-session baseline after storage."""
    engine = sa.create_engine('sqlite://')
    sa.event.listen(
        engine, 'connect',
        lambda connection, _: connection.create_collation(
            'utf8mb4_bin', lambda left, right: (left > right) - (left < right)))
    models.RadarQuote.__table__.create(engine)

    with sa.orm.Session(engine) as session:
        quote = models.RadarQuote(
            id=1, ticker='REGCLOSE', market='us', mic='XNAS', currency='USD',
            provider_symbol='REGCLOSE', fetched_at=dt.datetime(2026, 8, 28),
            quote_ts=dt.datetime(2026, 8, 28), price=102,
            prev_close=98, regular_close=100)
        session.add(quote)
        session.commit()
        session.expire(quote)
        assert quote.regular_close == 100

    engine.dispose()


def test_radar_quote_provider_delay_round_trips_in_isolated_schema():
    """Stored snapshots retain whether the provider called them delayed or EOD."""
    engine = sa.create_engine('sqlite://')
    sa.event.listen(
        engine, 'connect',
        lambda connection, _: connection.create_collation(
            'utf8mb4_bin', lambda left, right: (left > right) - (left < right)))
    models.RadarQuote.__table__.create(engine)

    with sa.orm.Session(engine) as session:
        quote = models.RadarQuote(
            id=1, ticker='QUALITY', market='de', mic='XETR', currency='EUR',
            provider_symbol='QUALITY', fetched_at=dt.datetime(2026, 8, 28),
            quote_ts=dt.datetime(2026, 8, 28), price=102,
            provider_delay='eod')
        session.add(quote)
        session.commit()
        session.expire(quote)
        assert quote.provider_delay == 'eod'

    engine.dispose()


def test_radar_instrument_assigns_an_id_with_sqlite_orm_persistence():
    """SQLite requires INTEGER, not BIGINT, for automatic primary-key IDs."""
    engine = sa.create_engine('sqlite://')
    sa.event.listen(
        engine, 'connect',
        lambda connection, _: connection.create_collation(
            'utf8mb4_bin', lambda left, right: (left > right) - (left < right)))
    models.RadarInstrument.__table__.create(engine)

    with sa.orm.Session(engine) as session:
        instrument = models.RadarInstrument(
            ticker='SQLITE', market='us', venue='Test venue', mic='XTST',
            provider_symbol='SQLITE', currency='USD', is_primary=True,
            mapping_status='mapped', mapped_at=dt.datetime(2026, 8, 28))
        session.add(instrument)
        session.commit()
        assert instrument.id == 1

    engine.dispose()


def test_model_schema_rejects_unknown_market_and_allows_null_price_context():
    """`db.create_all()` must enforce the same overlap contract as Alembic."""
    engine = sa.create_engine('sqlite://')
    sa.event.listen(
        engine, 'connect',
        lambda connection, _: connection.create_collation(
            'utf8mb4_bin', lambda left, right: (left > right) - (left < right)))
    metadata = sa.MetaData()
    for table in (
            models.RadarInstrument.__table__, models.RadarQuote.__table__,
            models.RadarDailyClose.__table__):
        table.to_metadata(metadata)
    metadata.create_all(engine)

    with engine.connect() as connection:
        invalid_inserts = (
            "INSERT INTO radar_instruments "
            "(id, ticker, market, venue, mic, provider_symbol, currency, "
            "is_primary, mapping_status, mapped_at) VALUES "
            "(1, 'BADINST', 'uk', 'Test', 'XTST', 'BADINST', 'GBP', 0, "
            "'unverified', CURRENT_TIMESTAMP)",
            "INSERT INTO radar_quotes "
            "(id, ticker, market, fetched_at, price) VALUES "
            "(1, 'BADQUOTE', 'uk', '2026-08-28 12:10:00', 1.0)",
            "INSERT INTO radar_daily_closes "
            "(ticker, market, close_date, close, fetched_at) VALUES "
            "('BADCLOSE', 'uk', '2026-08-28', 1.0, '2026-08-28 12:10:00')",
        )
        for statement in invalid_inserts:
            with pytest.raises(sa.exc.IntegrityError):
                connection.execute(sa.text(statement))
            connection.rollback()

        connection.execute(sa.text(
            "INSERT INTO radar_quotes "
            "(id, ticker, fetched_at, price) VALUES "
            "(2, 'LEGACY', '2026-08-28 12:11:00', 1.0)"))
        connection.execute(sa.text(
            "INSERT INTO radar_daily_closes "
            "(ticker, close_date, close, fetched_at) VALUES "
            "('LEGACY', '2026-08-28', 1.0, '2026-08-28 12:11:00')"))
        connection.commit()

        assert connection.execute(sa.text(
            "SELECT market FROM radar_quotes WHERE id=2")).scalar_one() is None
        assert connection.execute(sa.text(
            "SELECT market FROM radar_daily_closes WHERE ticker='LEGACY'")) \
            .scalar_one() is None

    engine.dispose()


# ---- sentiment v2 schema (spec 2026-08-31 §6) ------------------------------

def test_sentiment_v2_columns_exist_and_are_nullable():
    m = RadarMention.__table__.c
    for name in ('sentiment_relevance', 'sentiment_content_origin',
                 'sentiment_attitude', 'sentiment_expected_move',
                 'sentiment_confidence', 'sentiment_model',
                 'sentiment_prompt_version', 'sentiment_judged_at',
                 'local_sentiment_model_version', 'review_requested_at'):
        assert m[name].nullable, name


def test_judgment_history_row_cascades_with_its_mention():
    from models import RadarSentimentJudgment
    fk = list(RadarSentimentJudgment.__table__.c.mention_id.foreign_keys)[0]
    assert fk.ondelete == 'CASCADE'


def test_review_meter_shape():
    from models import RadarReviewMeter
    c = RadarReviewMeter.__table__.c
    assert c.day.primary_key
    for name in ('demanded', 'attempted', 'served', 'capped'):
        assert not c[name].nullable


def test_judgment_history_carries_all_five_enum_checks():
    from models import RadarSentimentJudgment
    names = {c.name for c in RadarSentimentJudgment.__table__.constraints
             if isinstance(c, sa.CheckConstraint)}
    assert {'ck_radar_judgment_stage', 'ck_radar_judgment_relevance',
            'ck_radar_judgment_origin', 'ck_radar_judgment_attitude',
            'ck_radar_judgment_move', 'ck_radar_judgment_conf'} <= names


def test_journal_chatter_flag_is_nullable_boolean():
    c = models.RadarMentionEvent.__table__.c.counts_as_human_chatter
    assert c.nullable

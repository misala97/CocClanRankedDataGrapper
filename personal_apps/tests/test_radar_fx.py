"""The euro reference rates a converted price line is drawn through.

The ECB publishes on TARGET business days only, so the interesting rules
here are all about the days it does NOT publish: a close on a Saturday is
converted at Friday's rate, and a close older than the whole stored series
is dropped rather than converted at the oldest rate we happen to hold.
"""
import datetime as dt
import decimal

import pytest

from app import app as flask_app
from extensions import db
from features.radar import fx
from models import RadarFxRate

NOW = dt.datetime(2026, 9, 5, 18, 0, 0)


@pytest.fixture()
def clean():
    def wipe():
        RadarFxRate.query.filter(RadarFxRate.source == 'test-fx').delete(
            synchronize_session=False)
        db.session.commit()

    with flask_app.app_context():
        wipe()
        yield
        wipe()


def seed(pairs):
    fx.record_rates(pairs, NOW, source='test-fx')


def test_record_rates_writes_one_row_per_day(clean):
    written = fx.record_rates(
        [(dt.date(2026, 9, 1), decimal.Decimal('1.1600')),
         (dt.date(2026, 9, 2), decimal.Decimal('1.1615'))],
        NOW, source='test-fx')

    assert written == 2
    assert RadarFxRate.query.filter_by(source='test-fx').count() == 2


def test_record_rates_restates_an_existing_day(clean):
    seed([(dt.date(2026, 9, 1), decimal.Decimal('1.1600'))])

    fx.record_rates([(dt.date(2026, 9, 1), decimal.Decimal('1.1700'))],
                    NOW, source='test-fx')

    rows = RadarFxRate.query.filter_by(source='test-fx').all()
    assert len(rows) == 1
    assert rows[0].rate == decimal.Decimal('1.17000000')


def test_rate_series_returns_published_days_only(clean):
    seed([(dt.date(2026, 9, 1), decimal.Decimal('1.1600')),
          (dt.date(2026, 9, 4), decimal.Decimal('1.1615'))])

    series = fx.rate_series(dt.date(2026, 9, 1), dt.date(2026, 9, 4))

    assert sorted(series) == [dt.date(2026, 9, 1), dt.date(2026, 9, 4)]


def test_rate_on_carries_the_last_published_rate_forward(clean):
    seed([(dt.date(2026, 9, 4), decimal.Decimal('1.1615'))])
    series = fx.rate_series(dt.date(2026, 9, 1), dt.date(2026, 9, 7))

    # 5 Sept is a Saturday: the ECB published nothing, so Friday stands.
    assert fx.rate_on(series, dt.date(2026, 9, 5)) == decimal.Decimal('1.1615')


def test_rate_on_refuses_a_day_before_the_series(clean):
    seed([(dt.date(2026, 9, 4), decimal.Decimal('1.1615'))])
    series = fx.rate_series(dt.date(2026, 9, 1), dt.date(2026, 9, 7))

    assert fx.rate_on(series, dt.date(2026, 9, 3)) is None


def test_convert_usd_to_eur_divides_by_the_days_rate(clean):
    seed([(dt.date(2026, 9, 4), decimal.Decimal('2.0000'))])
    series = fx.rate_series(dt.date(2026, 9, 1), dt.date(2026, 9, 7))

    converted = fx.convert_usd_to_eur(
        [(dt.date(2026, 9, 4), decimal.Decimal('10.00'))], series)

    assert converted == ((dt.date(2026, 9, 4), decimal.Decimal('5.00')),)


def test_convert_usd_to_eur_drops_a_close_with_no_usable_rate(clean):
    seed([(dt.date(2026, 9, 4), decimal.Decimal('2.0000'))])
    series = fx.rate_series(dt.date(2026, 9, 1), dt.date(2026, 9, 7))

    converted = fx.convert_usd_to_eur(
        [(dt.date(2026, 9, 3), decimal.Decimal('10.00')),
         (dt.date(2026, 9, 4), decimal.Decimal('10.00'))], series)

    assert [day for day, _ in converted] == [dt.date(2026, 9, 4)]

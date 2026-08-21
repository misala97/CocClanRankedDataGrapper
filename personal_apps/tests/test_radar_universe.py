# personal_apps/tests/test_radar_universe.py
"""The universe is what bare-token extraction matches against.

The reassignment case is rare and silent when it happens: a delisted symbol
given to a different company would otherwise inherit the old company's
baseline, and every spike against that baseline would be wrong with no error
anywhere (spec 4.2).
"""
import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from models import TickerUniverse
from features.radar import universe


@pytest.fixture()
def clean_universe():
    with flask_app.app_context():
        TickerUniverse.query.filter(TickerUniverse.symbol.like('ZZ%')).delete(
            synchronize_session=False)
        db.session.commit()
        yield
        TickerUniverse.query.filter(TickerUniverse.symbol.like('ZZ%')).delete(
            synchronize_session=False)
        db.session.commit()


NOW = dt.datetime(2026, 4, 15, 12, 0, 0)


def test_upsert_adds_new_symbols(clean_universe):
    result = universe.upsert_symbols(
        [{'symbol': 'ZZA', 'name': 'Alpha Corp', 'exchange': 'NASDAQ'}], NOW)
    assert result['added'] == 1
    row = TickerUniverse.query.filter_by(symbol='ZZA').one()
    assert row.name == 'Alpha Corp'
    assert row.first_seen == NOW


def test_upsert_is_idempotent(clean_universe):
    rows = [{'symbol': 'ZZA', 'name': 'Alpha Corp', 'exchange': 'NASDAQ'}]
    universe.upsert_symbols(rows, NOW)
    second = universe.upsert_symbols(rows, NOW + dt.timedelta(days=7))
    assert second['added'] == 0
    assert TickerUniverse.query.filter_by(symbol='ZZA').count() == 1


def test_symbols_are_stored_uppercase(clean_universe):
    universe.upsert_symbols(
        [{'symbol': 'zzb', 'name': 'Beta Corp', 'exchange': 'NASDAQ'}], NOW)
    assert TickerUniverse.query.filter_by(symbol='ZZB').count() == 1


def test_reassignment_resets_first_seen(clean_universe):
    """Same symbol, different company, after a delisting. first_seen moving is
    what tells Plan 2's baseline to start over rather than continue."""
    universe.upsert_symbols(
        [{'symbol': 'ZZC', 'name': 'Old Company', 'exchange': 'NYSE'}], NOW)
    universe.mark_delisted(['ZZC'], NOW + dt.timedelta(days=30))

    later = NOW + dt.timedelta(days=200)
    result = universe.upsert_symbols(
        [{'symbol': 'ZZC', 'name': 'Totally Different Inc', 'exchange': 'NYSE'}],
        later)

    assert result['reassigned'] == 1
    row = TickerUniverse.query.filter_by(symbol='ZZC').one()
    assert row.name == 'Totally Different Inc'
    assert row.first_seen == later
    assert row.delisted_at is None


def test_a_rename_is_not_a_reassignment(clean_universe):
    """A live company changing its name keeps its history. Only a name change
    across a delisting is a reassignment."""
    universe.upsert_symbols(
        [{'symbol': 'ZZD', 'name': 'Acme Inc', 'exchange': 'NYSE'}], NOW)
    later = NOW + dt.timedelta(days=100)
    result = universe.upsert_symbols(
        [{'symbol': 'ZZD', 'name': 'Acme Holdings Inc', 'exchange': 'NYSE'}],
        later)

    assert result['reassigned'] == 0
    row = TickerUniverse.query.filter_by(symbol='ZZD').one()
    assert row.first_seen == NOW


def test_lookup_is_keyed_by_uppercase_symbol(clean_universe):
    universe.upsert_symbols(
        [{'symbol': 'ZZE', 'name': 'Echo Corp', 'exchange': 'NASDAQ'}], NOW)
    lookup = universe.load_lookup()
    assert 'ZZE' in lookup
    assert lookup['ZZE']['name'] == 'Echo Corp'
    assert 'zze' not in lookup


def test_delisted_symbols_stay_in_the_lookup(clean_universe):
    """A delisted ticker still gets talked about, and dropping it from the
    lookup would turn those mentions into silent misses."""
    universe.upsert_symbols(
        [{'symbol': 'ZZF', 'name': 'Foxtrot Corp', 'exchange': 'NYSE'}], NOW)
    universe.mark_delisted(['ZZF'], NOW + dt.timedelta(days=1))
    assert 'ZZF' in universe.load_lookup()


def test_crypto_funds_are_excluded_from_the_lookup(clean_universe):
    """Crypto is excluded entirely (spec 3.7). On StockTwits an
    instrument_class field makes that easy; everywhere else the fund's own
    name is the giveaway."""
    universe.upsert_symbols([
        {'symbol': 'ZZBT', 'name': 'Grayscale Bitcoin Mini Trust', 'exchange': 'NYSE'},
        {'symbol': 'ZZET', 'name': 'Grayscale Ethereum Staking ETF Shares', 'exchange': 'NYSE'},
        {'symbol': 'ZZXR', 'name': 'Bitwise XRP ETF', 'exchange': 'NYSE'},
    ], NOW)
    lookup = universe.load_lookup()
    assert 'ZZBT' not in lookup
    assert 'ZZET' not in lookup
    assert 'ZZXR' not in lookup


def test_a_real_company_whose_ticker_spells_a_coin_is_kept(clean_universe):
    """BCH is Banco de Chile and LINK is Interlink Electronics. Deleting real
    companies to resolve an ambiguity that only exists on crypto-heavy sources
    would cost genuine coverage."""
    universe.upsert_symbols([
        {'symbol': 'ZZBC', 'name': 'Banco De Chile ADS', 'exchange': 'NYSE'},
        {'symbol': 'ZZLK', 'name': 'Interlink Electronics, Inc.', 'exchange': 'NASDAQ'},
    ], NOW)
    lookup = universe.load_lookup()
    assert 'ZZBC' in lookup
    assert 'ZZLK' in lookup


def test_the_crypto_rule_reads_names_not_symbols(clean_universe):
    assert universe.is_crypto_name('Grayscale Bitcoin Mini Trust') is True
    assert universe.is_crypto_name('iShares Bitcoin Trust ETF') is True
    assert universe.is_crypto_name('Banco De Chile ADS') is False
    assert universe.is_crypto_name(None) is False


import decimal


def test_segments_split_on_market_cap():
    big = decimal.Decimal('50000000000')
    mid = decimal.Decimal('2000000000')
    small = decimal.Decimal('100000000')
    today = dt.date(2026, 8, 21)
    assert universe.segment_for(big, None, None, today) == 'large'
    assert universe.segment_for(mid, None, None, today) == 'mid'
    assert universe.segment_for(small, None, None, today) == 'micro'


def test_a_cheap_share_price_is_micro_whatever_the_cap():
    """Penny stocks behave like micro caps regardless of what the cap says,
    and a stale or wrong cap should not put one in Large."""
    assert universe.segment_for(decimal.Decimal('20000000000'), None,
                                decimal.Decimal('3.00'),
                                dt.date(2026, 8, 21)) == 'micro'


def test_a_recent_listing_is_its_own_segment():
    """Recent IPOs have no baseline worth the name, which is a property of the
    data rather than of the company's size."""
    assert universe.segment_for(decimal.Decimal('5000000000'),
                                dt.date(2026, 3, 1), None,
                                dt.date(2026, 8, 21)) == 'recent_ipo'


def test_an_old_listing_is_not_recent():
    assert universe.segment_for(decimal.Decimal('5000000000'),
                                dt.date(2010, 3, 1), None,
                                dt.date(2026, 8, 21)) == 'mid'


def test_no_market_cap_is_unknown_not_micro():
    """Unknown is a first-class tab, and the most interesting one. Defaulting
    it to micro would bury exactly the names worth surfacing among genuinely
    tiny companies."""
    assert universe.segment_for(None, None, None, dt.date(2026, 8, 21)) == 'unknown'


def test_refresh_profiles_stores_what_the_provider_returns(clean_universe):
    from features.radar.prices import Profile

    class FakeProvider:
        def profile(self, symbol):
            return Profile(ticker=symbol,
                           market_cap=decimal.Decimal('7500000000'),
                           ipo_date=dt.date(2015, 5, 5), exchange='NASDAQ')

    universe.upsert_symbols(
        [{'symbol': 'ZZP', 'name': 'Profile Corp', 'exchange': 'NASDAQ'}], NOW)
    assert universe.refresh_profiles(FakeProvider(), ['ZZP'], NOW) == 1

    row = TickerUniverse.query.filter_by(symbol='ZZP').one()
    assert row.market_cap == decimal.Decimal('7500000000')
    assert row.ipo_date == dt.date(2015, 5, 5)
    assert row.profile_refreshed_at == NOW


def test_a_provider_returning_nothing_leaves_the_row_alone(clean_universe):
    """A failed lookup must not erase a cap we already had -- that would move
    the ticker into Unknown until the next refresh."""
    class Empty:
        def profile(self, symbol):
            return None

    universe.upsert_symbols(
        [{'symbol': 'ZZQ', 'name': 'Quiet Corp', 'exchange': 'NYSE'}], NOW)
    TickerUniverse.query.filter_by(symbol='ZZQ').update(
        {'market_cap': decimal.Decimal('1000000000')})
    db.session.commit()

    universe.refresh_profiles(Empty(), ['ZZQ'], NOW)
    assert TickerUniverse.query.filter_by(symbol='ZZQ').one().market_cap == \
        decimal.Decimal('1000000000')

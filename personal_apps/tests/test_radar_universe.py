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

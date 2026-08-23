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


# Distinctiveness counts ISSUERS, not listings. Counting listings made a
# company compete with its own derivatives.

def test_a_company_and_its_own_etfs_count_once():
    """`tesla` had a document frequency of 4 against a ceiling of 3 -- Tesla
    plus three leveraged ETFs tracking it -- so a bare TSLA mention could
    never be promoted. Measured on the live 12,359-symbol universe."""
    lookup = universe.annotate_distinctive({
        'TSLA': {'name': 'Tesla, Inc. - Common Stock'},
        'TSLL': {'name': 'Direxion Daily TSLA Bull 2X Shares'},
        'TSLQ': {'name': 'T-Rex 2X Inverse Tesla Daily Target ETF'},
        'TSLR': {'name': 'T-Rex 2X Long Tesla Daily Target ETF'},
    })

    assert 'tesla' in lookup['TSLA']['distinctive']


def test_share_classes_of_one_issuer_count_once():
    lookup = universe.annotate_distinctive({
        'GOOGL': {'name': 'Alphabet Inc. - Class A Common Stock'},
        'GOOG': {'name': 'Alphabet Inc. - Class C Capital Stock'},
        'GOOGP': {'name': 'Alphabet Inc. - Depositary Shares Series A'},
        'GOOGQ': {'name': 'Alphabet Inc. - Depositary Shares Series B'},
    })

    assert 'alphabet' in lookup['GOOGL']['distinctive']


def test_a_spac_listing_four_ways_counts_once():
    """The small-cap version of the same bug, and the one that matters here:
    a recent IPO lists as Common Stock plus Units plus Warrants plus Rights."""
    lookup = universe.annotate_distinctive({
        'IPEX': {'name': 'Inflection Point Acquisition Corp. - Common Stock'},
        'IPEXU': {'name': 'Inflection Point Acquisition Corp. - Unit'},
        'IPEXW': {'name': 'Inflection Point Acquisition Corp. - Warrant'},
        'IPEXR': {'name': 'Inflection Point Acquisition Corp. - Right'},
    })

    assert 'inflection' in lookup['IPEX']['distinctive']


def test_boilerplate_is_still_not_distinctive():
    """The guard on the whole change. Four DIFFERENT issuers sharing a word
    means the word is common, and no amount of deduping should rescue it."""
    lookup = universe.annotate_distinctive({
        'AAA': {'name': 'Alpha Bancorp Inc. - Common Stock'},
        'BBB': {'name': 'Beta Bancorp Inc. - Common Stock'},
        'CCC': {'name': 'Gamma Bancorp Inc. - Common Stock'},
        'DDD': {'name': 'Delta Bancorp Inc. - Common Stock'},
    })

    for symbol in lookup:
        assert 'bancorp' not in lookup[symbol]['distinctive']
        assert 'common' not in lookup[symbol]['distinctive']


def test_an_ordinary_word_can_become_distinctive_and_that_is_accepted():
    """The known cost of counting issuers. `peace` goes from 4 listings to 1
    issuer because three of the four are Peace Acquisition's warrant, unit and
    right -- so an ordinary English word qualifies.

    Recorded rather than fixed. Promotion still needs the BARE TICKER in the
    same post, so this only misfires on a post containing both PEACE and the
    word "peace". If that trade ever stops being worth it, this test is where
    the decision was made.
    """
    lookup = universe.annotate_distinctive({
        'PECE': {'name': 'Peace Acquisition Corp - Common Stock'},
        'PECEU': {'name': 'Peace Acquisition Corp - Unit'},
        'PECEW': {'name': 'Peace Acquisition Corp - Warrant'},
    })

    assert 'peace' in lookup['PECE']['distinctive']


# A fund's own name cannot promote its ticker. Added 2026-08-23 after the live
# board's entire small-cap section was MAGA and GOP.

def test_a_thematic_fund_cannot_promote_itself_from_its_own_name():
    """The live failure. `Subversive Congressional Republicans Trading ETF`
    handed GOP the token `republicans`, so any Bluesky post containing both
    the word GOP and the word republicans -- which is most posts about
    American politics -- promoted itself into a scored stock mention.

    A thematic fund is named after a discourse, so its name tokens are the
    most common words IN that discourse. The corroboration is backwards: for
    `tesla` the word is evidence the post is about the company, for
    `republicans` the word is evidence the post is NOT about the fund.
    """
    lookup = universe.annotate_distinctive({
        'GOP': {'name': 'Subversive Congressional Republicans Trading ETF'},
        'MAGA': {'name': 'Truth Social America First ETF'},
    })

    assert lookup['GOP']['distinctive'] == set()
    assert lookup['MAGA']['distinctive'] == set()


def test_an_operating_company_still_promotes_from_its_name():
    """The guard. Bare-token reach into small caps is the whole point of the
    mechanism; this narrows it to issuers, not funds."""
    lookup = universe.annotate_distinctive({
        'SBFM': {'name': 'Sunshine Biopharma Inc. - Common Stock'},
        'GRML': {'name': 'Greenland Acquisition Holdings - Common Stock'},
    })

    assert 'sunshine' in lookup['SBFM']['distinctive']
    assert 'greenland' in lookup['GRML']['distinctive']


def test_a_fund_is_still_reachable_by_cashtag():
    """Not a silent delisting. Dropping the tokens removes one PROMOTION path
    for a bare mention; `$MAGA` is a cashtag and scores directly, which is the
    right reading -- a person typing the dollar sign means the fund."""
    from features.radar import extraction

    found = extraction.extract_tickers(
        None, '$MAGA looks overbought',
        {'MAGA': {'name': 'Truth Social America First ETF',
                  'distinctive': set()}})

    assert found == [('MAGA', 'high')]


def test_an_adr_keeps_its_tokens():
    """The reason the two predicates had to split. An ADR is a real foreign
    operating company listing in the US, and Chinese and Israeli small caps
    list that way constantly -- silencing them cuts exactly the stocks the
    board exists to find. 1302 listings on the live universe."""
    lookup = universe.annotate_distinctive({
        'AACG': {'name': 'ATA Creativity Global - American Depositary Shares'},
    })

    assert 'creativity' in lookup['AACG']['distinctive']


def test_a_trust_that_is_an_operating_company_keeps_its_tokens():
    """`trust` is deliberately absent from POOLED_VEHICLE_PATTERN. Most
    REITs are named this way, and so is Adamas Trust -- which issues common
    stock and senior notes, not units of a strategy."""
    lookup = universe.annotate_distinctive({
        'ADMS': {'name': 'Adamas Trust, Inc. - Common Stock'},
    })

    assert 'adamas' in lookup['ADMS']['distinctive']


def test_a_leveraged_product_loses_them():
    lookup = universe.annotate_distinctive({
        'TSLL': {'name': 'Direxion Daily TSLA Bull 2X Shares ETF'},
    })

    assert lookup['TSLL']['distinctive'] == set()


def test_a_warrant_keeps_tokens_but_still_does_not_pad_the_issuer_count():
    """Both halves in one place. The warrant may vouch for itself, and it must
    not make its own parent's name look common."""
    lookup = universe.annotate_distinctive({
        'IPEX': {'name': 'Inflection Point Acquisition Corp. - Common Stock'},
        'IPEXU': {'name': 'Inflection Point Acquisition Corp. - Unit'},
        'IPEXW': {'name': 'Inflection Point Acquisition Corp. - Warrant'},
        'IPEXR': {'name': 'Inflection Point Acquisition Corp. - Right'},
    })

    assert 'inflection' in lookup['IPEXW']['distinctive']
    assert 'inflection' in lookup['IPEX']['distinctive']


def test_note_listings_without_a_separator_collapse_to_one_issuer():
    """Sachem Capital's four note lines carry no comma and no dash -- the
    coupon rate is the only boundary. Without it one small-cap lender counted
    as five issuers and `sachem` stopped being distinctive, which is the exact
    shape of bug this whole rule exists to prevent.

    Asserted on _issuer_of rather than through annotate_distinctive: the
    ceiling scales with the lookup, so a five-symbol universe allows one
    issuer per token and any second key fails regardless of the split.
    """
    keys = {universe._issuer_of(name) for name in (
        'Sachem Capital Corp. 6.00% Notes due 2026',
        'Sachem Capital Corp. 6.00% Notes due 2027',
        'Sachem Capital Corp. 7.125% Notes due 2027',
        'Sachem Capital Corp. 8.00% Notes due 2027',
    )}

    assert keys == {'sachem capital corp.'}


def test_the_coupon_split_leaves_ordinary_names_alone():
    assert universe._issuer_of('Tesla, Inc. - Common Stock') == 'tesla'
    assert universe._issuer_of('NVIDIA Corp') == 'nvidia corp'

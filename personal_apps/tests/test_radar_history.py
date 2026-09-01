"""Daily closes: the price context a first-time ticker is judged against.

The rules being pinned are about spending a scarce budget well. The provider
allows eight requests a minute, so which tickers get asked about, and how
often, is the whole design -- a job that re-asks for Friday's close all
weekend never gets to the ticker that appeared an hour ago.
"""
import datetime as dt
import decimal

import pytest

from app import app as flask_app
from extensions import db
from features.radar import history
from models import RadarDailyClose

TODAY = dt.date(2026, 8, 21)
NOW = dt.datetime(2026, 8, 21, 20, 0, 0)
PREFIX = 'HS'


@pytest.fixture()
def clean():
    def wipe():
        RadarDailyClose.query.filter(
            RadarDailyClose.ticker.like(f'{PREFIX}%')).delete(
                synchronize_session=False)
        db.session.commit()

    with flask_app.app_context():
        wipe()
        yield
        wipe()


def store(ticker, days_back, price='10.00'):
    db.session.add(RadarDailyClose(
        ticker=ticker, close_date=TODAY - dt.timedelta(days=days_back),
        close=decimal.Decimal(price), fetched_at=NOW))


class FakeProvider:
    """Records what it was asked for; answers from a fixed script."""

    def __init__(self, script):
        self.script = script
        self.asked = []

    def daily_closes(self, symbol, days):
        self.asked.append((symbol, days))
        return self.script.get(symbol, [])


def test_closes_are_returned_oldest_first(clean):
    store(f'{PREFIX}A', 2, '11.00')
    store(f'{PREFIX}A', 1, '12.00')
    store(f'{PREFIX}A', 0, '13.00')
    db.session.commit()

    series = history.closes_for([f'{PREFIX}A'], today=TODAY)[f'{PREFIX}A']

    assert [float(close) for _, close in series] == [11.0, 12.0, 13.0]


def test_only_the_requested_span_comes_back(clean):
    store(f'{PREFIX}A', 400, '1.00')
    store(f'{PREFIX}A', 5, '2.00')
    db.session.commit()

    series = history.closes_for([f'{PREFIX}A'], days=30, today=TODAY)[f'{PREFIX}A']

    assert [float(close) for _, close in series] == [2.0]


def test_a_ticker_with_nothing_stored_is_absent_not_empty(clean):
    """Absent and empty are different facts downstream: one becomes a null
    payload that draws a dashed rule, the other would draw a flat line."""
    assert history.closes_for([f'{PREFIX}A'], today=TODAY) == {}


def test_a_ticker_with_no_history_is_asked_about_first(clean):
    store(f'{PREFIX}B', 0)
    db.session.commit()

    due = history.tickers_needing_history(
        [f'{PREFIX}B', f'{PREFIX}A'], today=TODAY)

    assert due[0] == f'{PREFIX}A'


def test_fridays_close_is_not_stale_on_monday(clean):
    """Two days, not one. The provider has nothing newer to give over a
    weekend, so a one-day rule would spend every Monday-morning cycle
    re-fetching rows that cannot have changed.

    Stored deep on purpose. This asserts an empty result, and since 2026-08-23
    that depends on the depth rule as well as the staleness one -- with a
    single row the ticker is legitimately due, and the test would be measuring
    the wrong rule while still reading as if it measured this one.
    """
    for n in range(2, history.HISTORY_DAYS + 2):
        store(f'{PREFIX}A', n)
    db.session.commit()

    assert history.tickers_needing_history([f'{PREFIX}A'], today=TODAY) == []


def test_a_genuinely_old_series_is_refreshed(clean):
    store(f'{PREFIX}A', 9)
    db.session.commit()

    assert history.tickers_needing_history(
        [f'{PREFIX}A'], today=TODAY) == [f'{PREFIX}A']


def test_fetching_replaces_a_day_rather_than_duplicating_it(clean):
    """Providers restate recent bars. Appending would double every point the
    sparkline draws for the overlapping days."""
    store(f'{PREFIX}A', 0, '10.00')
    db.session.commit()

    provider = FakeProvider({f'{PREFIX}A': [(TODAY, decimal.Decimal('99.00'))]})
    history.fetch_into_store(provider, [f'{PREFIX}A'], NOW)

    rows = RadarDailyClose.query.filter_by(ticker=f'{PREFIX}A').all()
    assert len(rows) == 1
    assert float(rows[0].close) == 99.0


def test_a_provider_returning_nothing_leaves_what_we_had(clean):
    """Erasing a year of history because one call failed would blank the
    column for a ticker until the next cycle."""
    store(f'{PREFIX}A', 1, '10.00')
    db.session.commit()

    history.fetch_into_store(FakeProvider({}), [f'{PREFIX}A'], NOW)

    assert RadarDailyClose.query.filter_by(ticker=f'{PREFIX}A').count() == 1


def test_a_full_year_is_requested(clean):
    provider = FakeProvider({})
    history.fetch_into_store(provider, [f'{PREFIX}A'], NOW)

    assert provider.asked == [(f'{PREFIX}A', history.HISTORY_DAYS)]
    assert history.HISTORY_DAYS >= 252


# Three years, added 2026-08-23 for the detail panel's 3Y span.

def test_three_years_are_requested():
    """The panel offers 1M/6M/1Y/3Y and the longest span is the one that
    answers "has this stock done this before"."""
    assert history.HISTORY_DAYS >= 780


def test_a_ticker_stored_shallow_is_refetched(clean):
    """Raising HISTORY_DAYS does nothing on its own. Every stored ticker has a
    current newest close, so the staleness rule never fires and the store
    would stay one year deep forever."""
    for n in range(40):
        store(f'{PREFIX}SHALLOW', n)
    db.session.commit()

    assert f'{PREFIX}SHALLOW' in history.tickers_needing_history(
        [f'{PREFIX}SHALLOW'], TODAY)


def test_a_ticker_stored_deep_is_left_alone(clean):
    for n in range(history.HISTORY_DAYS):
        store(f'{PREFIX}DEEP', n)
    db.session.commit()

    assert f'{PREFIX}DEEP' not in history.tickers_needing_history(
        [f'{PREFIX}DEEP'], TODAY)


def test_a_recent_ipo_is_not_refetched_forever(clean):
    """A listing younger than the window has less history than we ask for and
    always will. Refetching it every cycle would spend the whole rate limit on
    the tickers that can never satisfy it."""
    for n in range(int(history.HISTORY_DAYS * history.MIN_STORED_RATIO) + 5):
        store(f'{PREFIX}IPO', n)
    db.session.commit()

    assert f'{PREFIX}IPO' not in history.tickers_needing_history(
        [f'{PREFIX}IPO'], TODAY)


def test_daily_history_stays_with_its_market_and_mic(clean):
    """EUR/Xetra bars cannot overwrite or appear as US history."""
    history.record_closes(
        f'{PREFIX}DUAL', [(TODAY, decimal.Decimal('220.00'))], NOW,
        market='us', mic='XNAS', currency='USD')
    history.record_closes(
        f'{PREFIX}DUAL', [(TODAY, decimal.Decimal('194.00'))], NOW,
        market='de', mic='XETR', currency='EUR')

    de = history.closes_for(
        [f'{PREFIX}DUAL'], today=TODAY, market='de', mic='XETR')
    us = history.closes_for(
        [f'{PREFIX}DUAL'], today=TODAY, market='us', mic='XNAS')

    assert de[f'{PREFIX}DUAL'] == [(TODAY, decimal.Decimal('194.0000'))]
    assert us[f'{PREFIX}DUAL'] == [(TODAY, decimal.Decimal('220.0000'))]


def test_primary_mic_us_history_reads_the_null_legacy_identity(clean):
    """The old history writer had no market or MIC columns to populate."""
    db.session.add(RadarDailyClose(
        ticker=f'{PREFIX}LEGACY', market=None, mic=None, close_date=TODAY,
        close=decimal.Decimal('100.00'), fetched_at=NOW))
    db.session.commit()

    assert history.closes_for(
        [f'{PREFIX}LEGACY'], today=TODAY, market='us', mic='XNAS') == {
            f'{PREFIX}LEGACY': [(TODAY, decimal.Decimal('100.0000'))]}


def test_german_history_uses_the_verified_mic_and_keeps_old_rows_on_error(clean):
    class MicProvider:
        def __init__(self):
            self.asked = []

        def daily_closes(self, symbol, days, mic_code=None):
            self.asked.append((symbol, days, mic_code))
            return []  # Twelve Data's non-ok status normalizes to no history.

    history.record_closes(
        f'{PREFIX}ERR', [(TODAY, decimal.Decimal('194.00'))], NOW,
        market='de', mic='XETR', currency='EUR')
    provider = MicProvider()

    assert history.fetch_into_store(
        provider, [f'{PREFIX}ERR'], NOW, market='de', mic='XETR',
        currency='EUR', provider_symbols={f'{PREFIX}ERR': 'APC'}) == 0
    assert provider.asked == [('APC', history.HISTORY_DAYS, 'XETR')]
    assert history.closes_for(
        [f'{PREFIX}ERR'], today=TODAY, market='de', mic='XETR')[
            f'{PREFIX}ERR'] == [(TODAY, decimal.Decimal('194.0000'))]


# --- Market data v2 (plan Task 8): priority, shadow, proxy seam --------------

DAY = TODAY


def add_close(ticker, day, price, *, market='de', mic='XETR', currency='EUR',
              source=None, price_basis=None, adjustment_basis=None,
              is_shadow=False):
    db.session.add(RadarDailyClose(
        ticker=ticker, market=market, mic=mic, currency=currency,
        close_date=day, close=decimal.Decimal(price), fetched_at=NOW,
        source=source, price_basis=price_basis,
        adjustment_basis=adjustment_basis, is_shadow=is_shadow))


def test_native_close_cannot_be_overwritten_by_yahoo(clean):
    ticker = f'{PREFIX}NAT'
    history.record_closes(
        ticker, [(DAY, decimal.Decimal('100.00'))], NOW, market='de',
        mic='XETR', currency='EUR', source='deutsche_boerse_delayed',
        adjustment_basis='split')
    history.record_closes(
        ticker, [(DAY, decimal.Decimal('99.00'))],
        NOW + dt.timedelta(hours=1), market='de', mic='XETR',
        currency='EUR', source='yahoo_chart', adjustment_basis='split')
    row = RadarDailyClose.query.filter_by(
        ticker=ticker, market='de', mic='XETR', close_date=DAY).one()
    assert (row.close, row.source) == (
        decimal.Decimal('100.0000'), 'deutsche_boerse_delayed')


def test_equal_priority_permits_provider_restatement(clean):
    ticker = f'{PREFIX}RST'
    history.record_closes(
        ticker, [(DAY, decimal.Decimal('100.00'))], NOW, market='us',
        mic='XNAS', currency='USD', source='yahoo_chart',
        adjustment_basis='split')
    history.record_closes(
        ticker, [(DAY, decimal.Decimal('101.00'))],
        NOW + dt.timedelta(hours=1), market='us', mic='XNAS',
        currency='USD', source='yahoo_chart', adjustment_basis='split')
    row = RadarDailyClose.query.filter_by(ticker=ticker, close_date=DAY).one()
    assert row.close == decimal.Decimal('101.0000')


def test_massive_overwrites_the_incumbent_twelvedata_row(clean):
    ticker = f'{PREFIX}MSV'
    history.record_closes(
        ticker, [(DAY, decimal.Decimal('100.00'))], NOW, market='us',
        mic='XNAS', currency='USD', source='twelvedata',
        adjustment_basis='split')
    history.record_closes(
        ticker, [(DAY, decimal.Decimal('100.10'))],
        NOW + dt.timedelta(hours=1), market='us', mic='XNAS',
        currency='USD', source='massive_grouped', adjustment_basis='split')
    row = RadarDailyClose.query.filter_by(ticker=ticker, close_date=DAY).one()
    assert (row.close, row.source) == (
        decimal.Decimal('100.1000'), 'massive_grouped')


def test_live_history_reader_excludes_newer_shadow_close(clean):
    ticker = f'{PREFIX}SHD'
    add_close(ticker, DAY, '100', is_shadow=False)
    add_close(ticker, DAY + dt.timedelta(days=1), '101', is_shadow=True)
    db.session.commit()
    stored = history.closes_for([ticker], today=DAY + dt.timedelta(days=2),
                                market='de', mic='XETR')
    assert stored[ticker] == [(DAY, decimal.Decimal('100.0000'))]


def test_shadow_and_live_write_lanes_do_not_collide(clean):
    ticker = f'{PREFIX}LNE'
    history.record_closes(
        ticker, [(DAY, decimal.Decimal('55.00'))], NOW, market='us',
        mic='XNAS', currency='USD', source='twelvedata',
        adjustment_basis='split')
    history.record_closes(
        ticker, [(DAY, decimal.Decimal('55.10'))], NOW, market='us',
        mic='XNAS', currency='USD', source='massive_grouped',
        adjustment_basis='split', is_shadow=True)
    rows = RadarDailyClose.query.filter_by(
        ticker=ticker, close_date=DAY).all()
    lanes = {row.is_shadow: row.close for row in rows}
    assert lanes == {False: decimal.Decimal('55.0000'),
                     True: decimal.Decimal('55.1000')}


def test_series_for_composes_one_xetra_proxy_seam(clean):
    from models import RadarInstrument
    ticker = f'{PREFIX}SEAM'
    RadarInstrument.query.filter_by(ticker=ticker).delete(
        synchronize_session=False)
    db.session.add_all([
        RadarInstrument(ticker=ticker, market='de', venue='Tradegate BSX',
                        mic='XGAT', provider_symbol=ticker + 'G',
                        currency='EUR', isin='DE000ZZTST05',
                        is_primary=True, mapping_status='mapped',
                        mapped_at=NOW),
        RadarInstrument(ticker=ticker, market='de', venue='Xetra',
                        mic='XETR', provider_symbol=ticker + 'X',
                        currency='EUR', isin='DE000ZZTST05',
                        is_primary=False, mapping_status='mapped',
                        mapped_at=NOW),
    ])
    for offset in (5, 4, 3, 2, 1):
        add_close(ticker, DAY - dt.timedelta(days=offset), '10.00',
                  mic='XETR', source='yahoo_chart', price_basis='close')
    for offset in (2, 1, 0):
        add_close(ticker, DAY - dt.timedelta(days=offset), '11.00',
                  mic='XGAT', source='deutsche_boerse_delayed',
                  price_basis='close')
    db.session.commit()

    series = history.series_for(ticker, 'de', 'XGAT', 30, DAY)
    by_day = dict(series.closes)
    # Proxy strictly before the first native date; native from there on.
    assert by_day[DAY - dt.timedelta(days=3)] == decimal.Decimal('10.0000')
    assert by_day[DAY - dt.timedelta(days=2)] == decimal.Decimal('11.0000')
    assert series.history_proxy is True
    assert (series.proxy_mic, series.native_mic) == ('XETR', 'XGAT')
    assert series.native_from == DAY - dt.timedelta(days=2)

    # A missing native date after the seam stays missing, never patched.
    RadarDailyClose.query.filter_by(
        ticker=ticker, mic='XGAT',
        close_date=DAY - dt.timedelta(days=1)).delete(
        synchronize_session=False)
    db.session.commit()
    series = history.series_for(ticker, 'de', 'XGAT', 30, DAY)
    days = {day for day, _ in series.closes}
    assert DAY - dt.timedelta(days=1) not in days

    # ISIN mismatch removes the proxy entirely.
    RadarInstrument.query.filter_by(ticker=ticker, mic='XETR').update(
        {RadarInstrument.isin: 'DE000ZZTST06'}, synchronize_session=False)
    db.session.commit()
    series = history.series_for(ticker, 'de', 'XGAT', 30, DAY)
    assert series.history_proxy is False
    assert all(close == decimal.Decimal('11.0000')
               for _, close in series.closes)
    RadarInstrument.query.filter_by(ticker=ticker).delete(
        synchronize_session=False)
    db.session.commit()


def test_a_source_basis_conflict_is_refused_not_overwritten(clean):
    ticker = f'{PREFIX}CNF'
    history.record_closes(
        ticker, [(DAY, decimal.Decimal('100.00'))], NOW, market='us',
        mic='XNAS', currency='USD', source='massive_grouped',
        adjustment_basis='split')
    with pytest.raises(ValueError):
        history.record_closes(
            ticker, [(DAY, decimal.Decimal('100.00'))], NOW, market='us',
            mic='XNAS', currency='USD', source='massive_grouped',
            adjustment_basis=None)

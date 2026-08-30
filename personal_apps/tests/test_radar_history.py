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

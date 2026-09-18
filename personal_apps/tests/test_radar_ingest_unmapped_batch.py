# personal_apps/tests/test_radar_ingest_unmapped_batch.py
"""A US quote cycle whose due batch has no mapped instrument asks nobody.

D8 in the ingest loop. An identity without a mapped US primary has no venue
anyone verified, so it is not quoted at all: no provider request, no quote
stored under a stand-in MIC, and no cycle error for what is ordinary unmapped
input. Every seam that would reach the database or a provider is replaced
here; the application's database is never touched.
"""
import datetime as dt
import decimal
import logging
from types import SimpleNamespace

import pytest

import run_radar_ingest as daemon
from features.radar.prices import Quote

NOW = dt.datetime(2026, 9, 17, 15, 0, tzinfo=dt.timezone.utc)

MAPPED = SimpleNamespace(ticker='MAPD', market='us',
                         venue='Nasdaq Global Market', mic='XNMS',
                         provider_symbol='MAPD', currency='USD')


@pytest.fixture()
def cycle(monkeypatch):
    """`_run_us_price_cycle` with its database and provider seams recorded."""
    from features.radar import market_data, scheduling
    from features.radar.prices import yahoo as yahoo_provider

    seen = SimpleNamespace(provider=[], recorded=[], stamped=[], due=[],
                           mapped=[])

    class Provider:
        """Answers as Finnhub's /quote does: a price and no listing MIC."""

        def __init__(self, http):
            seen.provider.append('constructed')

        def quotes(self, symbols):
            seen.provider.append(('quotes', list(symbols)))
            return {symbol: Quote(symbol, decimal.Decimal('10'), mic=None,
                                  source='finnhub')
                    for symbol in symbols}

    def record_quotes(found, now, **kwargs):
        seen.recorded.append(dict(found))
        if any(quote.mic is None for quote in found.values()):
            # What the real writer does with a snapshot that has no venue.
            raise ValueError('an unmapped identity is not quoted')
        return len(found)

    def transport():
        seen.provider.append('transport')

    monkeypatch.setattr(daemon, '_us_session_gate',
                        lambda now_aware: ('open', None))
    monkeypatch.setattr(market_data, 'active_price_tickers',
                        lambda now: list(seen.due))
    monkeypatch.setattr(scheduling, 'ensure_tracked',
                        lambda source, symbols, now: 0)
    monkeypatch.setattr(scheduling, 'due_symbols_from',
                        lambda source, symbols, now, limit: list(seen.due))
    monkeypatch.setattr(
        scheduling, 'record_fixed_poll',
        lambda source, symbol, now, interval: seen.stamped.append(symbol))
    monkeypatch.setattr(
        daemon, '_market_instruments',
        lambda tickers, market: [row for row in seen.mapped
                                 if row.ticker in tickers])
    monkeypatch.setattr(daemon.finnhub_provider, 'FinnhubHttp', transport)
    monkeypatch.setattr(daemon.finnhub_provider, 'FinnhubProvider', Provider)
    monkeypatch.setattr(yahoo_provider, 'YahooHttp', transport)
    monkeypatch.setattr(yahoo_provider, 'YahooProvider', Provider)
    monkeypatch.setattr(daemon.quotes, 'record_quotes', record_quotes)

    def run(due, mapped=(), provider='finnhub'):
        seen.due[:] = due
        seen.mapped[:] = mapped
        with daemon.app.app_context():
            return daemon._run_us_price_cycle(provider, NOW)

    run.seen = seen
    return run


@pytest.mark.parametrize('provider', ['finnhub', 'yahoo'])
def test_an_all_unmapped_due_batch_asks_no_provider_and_stores_nothing(
        cycle, caplog, provider):
    caplog.set_level(logging.INFO, logger='radar.ingest')

    result = cycle(['UNMA', 'UNMB'], provider=provider)

    assert result == {'skipped': 'no_mapped_instruments', 'stored': 0,
                      'error': False}
    assert cycle.seen.provider == []
    assert cycle.seen.recorded == []
    assert not any(record.levelno >= logging.WARNING
                   for record in caplog.records)


def test_an_all_unmapped_batch_still_takes_its_turn(cycle):
    """Fairness: success and failure stamp alike, and so does a skip. Left
    due, an unmapped batch would head every following cycle and starve the
    mapped symbols behind it."""
    cycle(['UNMA', 'UNMB'])
    assert cycle.seen.stamped == ['UNMA', 'UNMB']


def test_a_mixed_batch_still_quotes_only_its_mapped_instruments(cycle,
                                                                caplog):
    caplog.set_level(logging.INFO, logger='radar.ingest')

    result = cycle(['MAPD', 'UNMA'], [MAPPED])

    assert result == {'skipped': None, 'stored': 1, 'error': False,
                      'attempted': 2}
    assert cycle.seen.provider == ['transport', 'constructed',
                                   ('quotes', ['MAPD'])]
    [written] = cycle.seen.recorded
    assert [(quote.ticker, quote.market, quote.mic, quote.venue)
            for quote in written.values()] == [
        ('MAPD', 'us', 'XNMS', 'Nasdaq Global Market')]
    assert cycle.seen.stamped == ['MAPD', 'UNMA']
    assert not any(record.levelno >= logging.WARNING
                   for record in caplog.records)

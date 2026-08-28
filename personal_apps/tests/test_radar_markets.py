import datetime as dt
import decimal

from features.radar.markets import select_quote
from features.radar.prices import Quote


NOW = dt.datetime(2026, 8, 28, 12, 0)


def snapshot(*, ticker='AAPL', market='us', venue='NASDAQ', mic='XNAS',
             currency='USD', price='100', previous_close='98',
             regular_close='100', quote_ts=NOW, provider_delay='live'):
    """A complete provider-neutral quote; literals make threshold bugs visible."""
    return Quote(
        ticker=ticker, market=market, venue=venue, mic=mic,
        provider_symbol=ticker, currency=currency,
        price=decimal.Decimal(price),
        previous_close=decimal.Decimal(previous_close),
        regular_close=decimal.Decimal(regular_close), quote_ts=quote_ts,
        volume=100, provider_delay=provider_delay,
    )


def quote_view(*, now=NOW, **changes):
    quote = snapshot(**changes)
    return select_quote(quote.ticker, quote.market, {quote.market: quote}, now)


def test_delayed_quote_is_eligible_at_exactly_thirty_minutes():
    view = quote_view(
        quote_ts=NOW - dt.timedelta(minutes=30), provider_delay='delayed')
    assert view.score_eligible is True


def test_delayed_quote_becomes_stale_after_thirty_minutes():
    view = quote_view(quote_ts=NOW - dt.timedelta(minutes=30, seconds=1),
                      provider_delay='delayed')
    assert view.quality == 'stale'
    assert view.score_eligible is False


def test_frozen_tape_status_blocks_an_otherwise_live_quote_from_scoring():
    """A no-print verdict belongs to quote history, not to market selection."""
    view = select_quote('AAPL', 'us', {'us': snapshot()}, NOW,
                        tape_status='stale')
    assert view.quality == 'live'
    assert view.score_eligible is False


def test_afterhours_move_uses_same_day_regular_close():
    afterhours = dt.datetime(2026, 8, 28, 21, 0)
    view = quote_view(now=afterhours, price='102', previous_close='98',
                      regular_close='100', quote_ts=afterhours)
    assert view.regular_move == decimal.Decimal('0.040816326530612244897959184')
    assert view.extended_move == decimal.Decimal('0.02')


def test_missing_de_quote_selects_marked_us_fallback():
    selected = select_quote('AAPL', 'de', {'us': snapshot()}, NOW)
    assert (selected.market, selected.currency, selected.is_fallback) == (
        'us', 'USD', True)


def test_timestamp_less_de_snapshot_does_not_block_marked_us_fallback():
    selected = select_quote('AAPL', 'de', {
        'de': snapshot(market='de', venue='Xetra', mic='XETR', currency='EUR',
                       quote_ts=None),
        'us': snapshot(),
    }, NOW)
    assert (selected.market, selected.currency, selected.is_fallback) == (
        'us', 'USD', True)


def test_de_prefers_retained_xetra_snapshot_to_fresh_us_fallback():
    selected = select_quote('AAPL', 'de', {
        'de': snapshot(market='de', venue='Xetra', mic='XETR', currency='EUR',
                       quote_ts=NOW - dt.timedelta(minutes=31),
                       provider_delay='delayed'),
        'us': snapshot(),
    }, NOW)
    assert (selected.market, selected.mic, selected.is_fallback) == (
        'de', 'XETR', False)


def test_us_does_not_fall_back_to_germany():
    selected = select_quote('AAPL', 'us', {
        'de': snapshot(market='de', venue='Xetra', mic='XETR', currency='EUR'),
    }, NOW)
    assert selected.quality == 'unavailable'
    assert selected.is_fallback is False


def test_currency_mismatched_snapshot_is_not_selected_for_live_divergence():
    selected = select_quote('AAPL', 'de', {
        'de': snapshot(market='de', venue='Xetra', mic='XETR', currency='USD'),
    }, NOW)
    assert selected.quality == 'unavailable'

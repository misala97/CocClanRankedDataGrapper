import datetime as dt
import decimal

import pytest

from features.radar.markets import select_quote
from features.radar.prices import Quote


NOW = dt.datetime(2026, 8, 28, 12, 0)


def snapshot(*, ticker='AAPL', market='us', venue='NASDAQ', mic='XNAS',
             currency='USD', price='100', previous_close='98',
             regular_close='100', quote_ts=NOW, provider_delay='live',
             source='legacy', price_basis='trade', bid=None, ask=None):
    """A complete provider-neutral quote; literals make threshold bugs visible."""
    return Quote(
        ticker=ticker, market=market, venue=venue, mic=mic,
        provider_symbol=ticker, currency=currency,
        price=decimal.Decimal(price) if price is not None else None,
        previous_close=decimal.Decimal(previous_close),
        regular_close=decimal.Decimal(regular_close), quote_ts=quote_ts,
        volume=100, provider_delay=provider_delay,
        source=source, price_basis=price_basis,
        bid=decimal.Decimal(bid) if bid is not None else None,
        ask=decimal.Decimal(ask) if ask is not None else None,
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


@pytest.mark.parametrize('provider_delay', ['live', 'delayed'])
@pytest.mark.parametrize('tape_status', ['closed', 'unknown'])
def test_non_ok_tape_status_blocks_a_fresh_quote_from_scoring(
        provider_delay, tape_status):
    """Only a verified open tape can contribute price divergence."""
    view = select_quote('AAPL', 'us', {
        'us': snapshot(provider_delay=provider_delay),
    }, NOW, tape_status=tape_status)
    assert view.quality == provider_delay
    assert view.score_eligible is False


def test_afterhours_move_uses_same_day_regular_close():
    afterhours = dt.datetime(2026, 8, 28, 21, 0)
    view = quote_view(now=afterhours, price='102', previous_close='98',
                      regular_close='100', quote_ts=afterhours)
    assert view.regular_move == decimal.Decimal('0.040816326530612244897959184')
    assert view.extended_move == decimal.Decimal('0.02')


def test_quote_timestamp_decides_premarket_session_and_close_baseline():
    """A later poll cannot relabel an early print as regular-session trading."""
    premarket_print = dt.datetime(2026, 8, 28, 11, 0)
    viewed_during_regular = dt.datetime(2026, 8, 28, 15, 0)

    view = quote_view(now=viewed_during_regular, price='102',
                      previous_close='100', regular_close='999',
                      quote_ts=premarket_print)

    assert view.session == 'premarket'
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


# --- Market data v2 (plan Task 3) --------------------------------------------

def test_midpoint_is_visible_but_never_score_eligible():
    from features.radar.markets import QuoteView
    quote = snapshot(
        market='de', mic='XGAT', venue='Tradegate BSX', currency='EUR',
        source='deutsche_boerse_delayed', price_basis='midpoint',
        price=None, bid='99.90', ask='100.10', provider_delay='delayed')
    view = QuoteView.from_snapshot(quote, NOW)
    assert view.price == decimal.Decimal('100.00')
    assert view.price_basis == 'midpoint'
    assert view.score_eligible is False


def test_verified_german_mapping_does_not_fallback_during_feed_failure():
    selected = select_quote('AAPL', 'de', {'us': snapshot()}, NOW,
                            allow_us_fallback=False)
    assert selected.quality == 'unavailable'
    assert selected.is_fallback is False


def test_us_fallback_in_germany_mode_is_never_score_eligible():
    selected = select_quote('AAPL', 'de', {'us': snapshot()}, NOW)
    assert selected.is_fallback is True
    assert selected.score_eligible is False
    assert selected.score_term == 'chatter'


def test_quote_validation_rejects_dishonest_values():
    with pytest.raises(ValueError):
        snapshot(price='0')
    with pytest.raises(ValueError):
        snapshot(price='-1')
    with pytest.raises(ValueError):
        snapshot(price=None, price_basis='midpoint',
                 bid='100.10', ask='99.90')  # crossed book
    with pytest.raises(ValueError):
        snapshot(price=None, price_basis='midpoint', bid='99.90')  # one-sided
    with pytest.raises(ValueError):
        snapshot(source='made_up_source')
    with pytest.raises(ValueError):
        snapshot(price_basis='made_up_basis')
    with pytest.raises(ValueError):
        snapshot(source='massive_grouped', price_basis='close')


def test_trade_price_never_derives_from_its_book():
    quote = snapshot(price='100.55', price_basis='trade',
                     bid='99.00', ask='101.00')
    assert quote.price == decimal.Decimal('100.55')


def test_missing_provider_time_is_unavailable_not_fetch_time_fresh():
    quote = snapshot(quote_ts=None)
    from features.radar.markets import QuoteView
    view = QuoteView.from_snapshot(
        dataclasses_replace_fetched(quote, NOW), NOW)
    assert view.quality == 'unavailable'
    assert view.score_eligible is False


def test_xgat_late_quote_without_regular_close_has_no_extended_move():
    """Plan Task 3 Step 7: no official/last-trade 17:30 value means NO
    extended move -- never a midpoint- or Xetra-derived number."""
    from features.radar.markets import QuoteView
    late = dt.datetime(2026, 8, 31, 18, 0)  # 20:00 Berlin, afterhours
    quote = Quote(
        ticker='AAPL', market='de', venue='Tradegate BSX', mic='XGAT',
        provider_symbol='APC', currency='EUR',
        price=decimal.Decimal('100'), previous_close=decimal.Decimal('98'),
        regular_close=None, quote_ts=late, volume=None,
        provider_delay='delayed', source='deutsche_boerse_delayed',
        price_basis='trade')
    view = QuoteView.from_snapshot(quote, late)
    assert view.session == 'afterhours'
    assert view.extended_move is None


def dataclasses_replace_fetched(quote, fetched_at):
    """A copy with fetched_at set; Quote is frozen with a custom __init__."""
    return Quote(
        ticker=quote.ticker, market=quote.market, venue=quote.venue,
        mic=quote.mic, provider_symbol=quote.provider_symbol,
        currency=quote.currency, price=quote.price,
        previous_close=quote.previous_close,
        regular_close=quote.regular_close, quote_ts=quote.quote_ts,
        volume=quote.volume, provider_delay=quote.provider_delay,
        fetched_at=fetched_at, source=quote.source,
        price_basis=quote.price_basis, bid=quote.bid, ask=quote.ask)

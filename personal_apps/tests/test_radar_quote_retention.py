# personal_apps/tests/test_radar_quote_retention.py
"""Rolling deletion of price snapshots.

`retention.py` covered posts and mentions and never touched radar_quotes, so
that table grew without bound -- and since 2026-08-24 it is read on every board
load by `statuses_for` and `moves_for`, which makes it the one table most
likely to undo the work that made the board fast.

The constraint that shapes this: `price_status` decides from a ticker's most
recent STALE_QUOTE_POLLS snapshots WHENEVER THEY WERE TAKEN. Quotes are only
fetched for tickers the board is currently watching, so a name that went quiet
weeks ago still has three real snapshots and still answers 'ok' or 'stale'. An
age-only delete would take those away and flip it to 'unknown' -- which is a
statement about the stock rather than about our polling, and the distinction
those four statuses exist to preserve.
"""
import datetime as dt
import decimal

import pytest

from app import app as flask_app
from extensions import db
from features.radar import quotes as quotes_mod
from features.radar import retention
from features.radar.config import QUOTE_RETENTION_DAYS, STALE_QUOTE_POLLS
from models import RadarQuote

NOW = dt.datetime(2026, 8, 24, 12, 0, 0)
PREFIX = 'QR'


@pytest.fixture()
def ctx():
    def wipe():
        RadarQuote.query.filter(RadarQuote.ticker.like(f'{PREFIX}%')).delete(
            synchronize_session=False)
        db.session.commit()

    with flask_app.app_context():
        wipe()
        yield
        wipe()


def add(ticker, days_ago, price='10.00', quote_ts=None, minutes=0):
    when = NOW - dt.timedelta(days=days_ago, minutes=minutes)
    db.session.add(RadarQuote(
        ticker=ticker, fetched_at=when, quote_ts=quote_ts or when,
        price=decimal.Decimal(price), prev_close=decimal.Decimal('9.00')))
    return when


def surviving(ticker):
    return RadarQuote.query.filter_by(ticker=ticker).count()


OLD = QUOTE_RETENTION_DAYS + 5


def test_snapshots_past_the_window_are_deleted(ctx):
    for minutes in range(20):
        add(f'{PREFIX}BUSY', OLD, minutes=minutes)
    db.session.commit()

    retention.prune_quotes(NOW)

    assert surviving(f'{PREFIX}BUSY') == STALE_QUOTE_POLLS


def test_a_quiet_ticker_keeps_the_polls_its_status_is_read_from(ctx):
    """The whole reason this is not a plain age filter.

    Every snapshot is far outside the window, and all of them say the same
    thing -- a frozen tape. Delete them and the ticker stops being 'stale' and
    becomes 'unknown', which says the board never quoted it.
    """
    frozen = NOW - dt.timedelta(days=OLD, hours=1)
    for minutes in range(STALE_QUOTE_POLLS):
        add(f'{PREFIX}QUIET', OLD, minutes=minutes, quote_ts=frozen)
    db.session.commit()
    before = quotes_mod.price_status(f'{PREFIX}QUIET', NOW, session='regular')

    retention.prune_quotes(NOW)

    assert surviving(f'{PREFIX}QUIET') == STALE_QUOTE_POLLS
    assert quotes_mod.price_status(
        f'{PREFIX}QUIET', NOW, session='regular') == before
    assert before == 'stale', 'fixture must actually be a frozen tape'


def test_a_ticker_with_fewer_snapshots_than_the_rule_keeps_all_of_them(ctx):
    add(f'{PREFIX}THIN', OLD)
    db.session.commit()

    retention.prune_quotes(NOW)

    assert surviving(f'{PREFIX}THIN') == 1
    assert quotes_mod.price_status(f'{PREFIX}THIN', NOW) != 'unknown'


def test_snapshots_inside_the_window_are_untouched(ctx):
    """`move_since` reads across the window, so nothing in it may be dropped
    even where a ticker has hundreds of them."""
    for minutes in range(30):
        add(f'{PREFIX}FRESH', 0, minutes=minutes)
    db.session.commit()

    retention.prune_quotes(NOW)

    assert surviving(f'{PREFIX}FRESH') == 30


def test_the_move_across_the_window_survives_a_prune(ctx):
    """Teeth for the test above: counting rows would pass even if the prune
    kept the wrong thirty."""
    for minutes in range(30):
        add(f'{PREFIX}MOVE', 0, price=str(10 + minutes), minutes=minutes)
    db.session.commit()
    before = quotes_mod.move_since(f'{PREFIX}MOVE', hours=24, now=NOW)

    retention.prune_quotes(NOW)

    assert quotes_mod.move_since(f'{PREFIX}MOVE', hours=24, now=NOW) == before
    assert before is not None and before != 0


def test_it_reports_what_it_deleted(ctx):
    for minutes in range(10):
        add(f'{PREFIX}COUNT', OLD, minutes=minutes)
    db.session.commit()

    assert retention.prune_quotes(NOW) == 10 - STALE_QUOTE_POLLS


def test_a_second_run_finds_nothing_left(ctx):
    for minutes in range(10):
        add(f'{PREFIX}TWICE', OLD, minutes=minutes)
    db.session.commit()

    retention.prune_quotes(NOW)
    assert retention.prune_quotes(NOW) == 0


def test_chunking_does_not_change_the_outcome(ctx):
    """The chunk size is a courtesy to the daemon's other jobs, not a filter."""
    for minutes in range(25):
        add(f'{PREFIX}CHUNK', OLD, minutes=minutes)
    db.session.commit()

    deleted = retention.prune_quotes(NOW, chunk_size=4, pause=0)

    assert deleted == 25 - STALE_QUOTE_POLLS
    assert surviving(f'{PREFIX}CHUNK') == STALE_QUOTE_POLLS


def test_retention_keeps_the_required_snapshots_for_each_market(ctx):
    """A busy US tape must not age Xetra's no-print evidence out."""
    for market, mic, currency in (('us', 'XNAS', 'USD'), ('de', 'XETR', 'EUR')):
        for minutes in range(8):
            when = NOW - dt.timedelta(days=OLD, minutes=minutes)
            db.session.add(RadarQuote(
                ticker=f'{PREFIX}DUAL', market=market, mic=mic,
                currency=currency, provider_symbol=f'{PREFIX}DUAL',
                fetched_at=when, quote_ts=when,
                price=decimal.Decimal('10.00'),
                prev_close=decimal.Decimal('9.00')))
    db.session.commit()

    retention.prune_quotes(NOW)

    assert RadarQuote.query.filter_by(
        ticker=f'{PREFIX}DUAL', market='us', mic='XNAS').count() == STALE_QUOTE_POLLS
    assert RadarQuote.query.filter_by(
        ticker=f'{PREFIX}DUAL', market='de', mic='XETR').count() == STALE_QUOTE_POLLS

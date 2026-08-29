# personal_apps/tests/test_radar_quotes_batch.py
"""The batched quote lookups, against the per-ticker ones they replace.

`leaderboard.build_rows` called `price_status` and `move_since` once per
ticker, inside a loop over every eligible ticker. Measured 2026-08-24: 2.93
`radar_quotes` queries per ticker, and on the live board that was ~1200 round
trips for one page load -- 1.58s of the document's TTFB against 30ms for the
detail endpoint, which does the same three lookups for a single ticker.

Every test here asserts the batch equals the loop it replaces rather than
asserting a hand-written expectation. Two implementations of one judgement is
the failure this codebase keeps designing against, and a batch that quietly
disagrees about 'stale' versus 'ok' would put a no-print mark on the wrong
rows.
"""
import datetime as dt
import decimal

import pytest

from app import app as flask_app
from extensions import db
from features.radar import quotes as quotes_mod
from features.radar.config import STALE_QUOTE_POLLS
from models import RadarQuote

NOW = dt.datetime(2026, 8, 21, 14, 0, 0)
PREFIX = 'QB'


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


def add(ticker, minutes_ago, price, quote_ts=None, volume=None):
    when = NOW - dt.timedelta(minutes=minutes_ago)
    db.session.add(RadarQuote(
        ticker=ticker, fetched_at=when, quote_ts=quote_ts or when,
        price=decimal.Decimal(str(price)),
        prev_close=decimal.Decimal('100.000000'), volume=volume))


def build_a_board_of_every_shape():
    """One ticker per case the status rules distinguish."""
    # A live, moving tape: three polls, three distinct quote_ts.
    for n, minutes in enumerate((0, 5, 10)):
        add(f'{PREFIX}OK', minutes, 10 + n)

    # A frozen tape: three polls that all carry the same quote_ts.
    frozen = NOW - dt.timedelta(minutes=30)
    for minutes in (0, 5, 10):
        add(f'{PREFIX}STALE', minutes, 10, quote_ts=frozen)

    # Fewer polls than the rule needs to call anything stale.
    add(f'{PREFIX}THIN', 0, 10)

    # Quoted, but every snapshot is older than any window asked about.
    add(f'{PREFIX}OLD', 60 * 40, 10)
    add(f'{PREFIX}OLD', 60 * 41, 11)

    # A price that moved, and one that did not.
    add(f'{PREFIX}MOVE', 1, 12)
    add(f'{PREFIX}MOVE', 50, 10)
    add(f'{PREFIX}FLAT', 1, 10)
    add(f'{PREFIX}FLAT', 50, 10)

    db.session.commit()
    # QBNONE is never written: a ticker with no quote at all has to survive
    # the batch as 'unknown' rather than falling out of the mapping.
    return [f'{PREFIX}{name}' for name in
            ('OK', 'STALE', 'THIN', 'OLD', 'MOVE', 'FLAT', 'NONE')]


@pytest.mark.parametrize('session', [None, 'regular', 'closed'])
def test_batched_status_matches_the_per_ticker_answer(ctx, session):
    tickers = build_a_board_of_every_shape()

    batched = quotes_mod.statuses_for(tickers, NOW, session=session)
    for ticker in tickers:
        expected = quotes_mod.price_status(ticker, NOW, session=session)
        assert batched[ticker][0] == expected, ticker


def test_the_shapes_are_actually_different(ctx):
    """Teeth. Without this the comparison above passes on a board where every
    ticker happens to answer 'ok', which proves nothing about the rules."""
    tickers = build_a_board_of_every_shape()

    answers = {quotes_mod.statuses_for(tickers, NOW, session='regular')[t][0]
               for t in tickers}
    assert answers == {'ok', 'stale', 'unknown'}
    assert STALE_QUOTE_POLLS == 3, 'fixtures are written for three polls'


def test_the_batch_carries_each_latest_snapshot(ctx):
    """The third query the loop made. `latest` is the newest row at or before
    `now`, and it is None exactly where the status is unknown."""
    tickers = build_a_board_of_every_shape()

    batched = quotes_mod.statuses_for(tickers, NOW, session='regular')
    for ticker in tickers:
        status, latest = batched[ticker]
        if status == 'unknown':
            assert latest is None, ticker
            continue
        newest = (RadarQuote.query
                  .filter(RadarQuote.ticker == ticker,
                          RadarQuote.fetched_at <= NOW)
                  .order_by(RadarQuote.fetched_at.desc()).first())
        assert latest.fetched_at == newest.fetched_at, ticker
        assert latest.price == newest.price, ticker


@pytest.mark.parametrize('hours', [1, 4, 24])
def test_batched_move_matches_the_per_ticker_answer(ctx, hours):
    tickers = build_a_board_of_every_shape()

    batched = quotes_mod.moves_for(tickers, hours, NOW)
    for ticker in tickers:
        assert batched.get(ticker) == quotes_mod.move_since(
            ticker, hours=hours, now=NOW), ticker


def test_moves_distinguishes_no_move_from_no_data(ctx):
    """Teeth. Both are None to a caller, so the comparison above cannot tell
    them apart on its own -- and they are different facts."""
    build_a_board_of_every_shape()

    moved = quotes_mod.moves_for([f'{PREFIX}MOVE'], 4, NOW)[f'{PREFIX}MOVE']
    flat = quotes_mod.moves_for([f'{PREFIX}FLAT'], 4, NOW)[f'{PREFIX}FLAT']
    absent = quotes_mod.moves_for([f'{PREFIX}NONE'], 4, NOW).get(f'{PREFIX}NONE')

    assert moved is not None and moved > 0
    assert flat == 0
    assert absent is None


def test_an_empty_ticker_list_asks_the_database_nothing(ctx):
    assert quotes_mod.statuses_for([], NOW, session='regular') == {}
    assert quotes_mod.moves_for([], 4, NOW) == {}


def test_explicit_market_windows_never_read_another_venue(ctx):
    """A shared social ticker has independent US and Xetra tapes."""
    for market, mic, price in (('us', 'XNAS', '220'), ('de', 'XETR', '194')):
        for minutes in (10, 5, 0):
            when = NOW - dt.timedelta(minutes=minutes)
            db.session.add(RadarQuote(
                ticker=f'{PREFIX}DUAL', market=market, mic=mic,
                currency='USD' if market == 'us' else 'EUR',
                provider_symbol=f'{PREFIX}DUAL', fetched_at=when,
                quote_ts=when, price=decimal.Decimal(price),
                prev_close=decimal.Decimal('100.000000')))
    db.session.commit()

    status, latest = quotes_mod.statuses_for(
        [(f'{PREFIX}DUAL', 'de', 'XETR')], NOW, session='regular')[
            (f'{PREFIX}DUAL', 'de')]
    move = quotes_mod.moves_for(
        [(f'{PREFIX}DUAL', 'de', 'XETR')], 1, NOW)[(f'{PREFIX}DUAL', 'de')]

    assert status == 'ok'
    assert latest.mic == 'XETR'
    assert latest.price == decimal.Decimal('194')
    assert move == 0

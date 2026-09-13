"""Sorting the board: seven keys, missing values last, and the sort happening
BEFORE the row limit -- which is the whole point of doing it server-side."""
import dataclasses
import datetime as dt
import math

import pytest

from features.radar import board


def row(ticker, mentions=10, expected=5.0, divergence=None, price_move=None,
        mention_z=None, segment='large', venues=1, price=10,
        direction='up', price_status='ok'):
    """A stand-in for leaderboard.Row carrying only the sorted fields.

    sort_rows reads only the sort attributes and a tones map; it never touches the
    quote, the marks or the series, so a namespace is a truthful fixture
    and keeps this suite independent of the DB.
    """
    return dataclasses.make_dataclass(
        'R', ['ticker', 'mentions', 'expected', 'divergence', 'price_move',
              'mention_z', 'segment', 'venues', 'price', 'direction',
              'price_status'])(ticker, mentions, expected, divergence, price_move,
                               mention_z, segment, venues, price, direction,
                               price_status)


def tickers(rows):
    return [r.ticker for r in rows]


def test_the_sort_keys_are_the_wire_format():
    assert board.SORT_KEYS == ('ticker', 'mentions', 'divergence', 'ratio',
                               'move', 'lean', 'chatter')


def test_chatter_orders_finite_surprise_then_mentions_then_ticker():
    rows = [row('PRICEFIRST', mentions=4, divergence=99, mention_z=2),
            row('HIGH', mentions=12, divergence=None, mention_z=2),
            row('ALPHA', mentions=12, divergence=-5, mention_z=2),
            row('ZERO', mentions=100, mention_z=0),
            row('NEG', mentions=100, mention_z=-1),
            row('NONE', mentions=999, mention_z=None),
            row('NAN', mentions=999, mention_z=math.nan),
            row('INF', mentions=999, mention_z=math.inf)]
    assert tickers(board.sort_rows(rows, 'chatter', 'desc', {})) == [
        'ALPHA', 'HIGH', 'PRICEFIRST', 'ZERO', 'NEG', 'INF', 'NAN', 'NONE']


def test_chatter_selection_happens_before_limit_and_ignores_price_only_changes(
        monkeypatch):
    """A high-surprise row must enter even when price-derived divergence would
    have kept it outside the legacy top-N.  Changing only quote observations
    (including their derived divergence) cannot change this selection."""
    original = [
        row('PRICEFIRST', mentions=20, mention_z=1, divergence=99,
            price_move=0.40, price=80, direction='up', price_status='ok'),
        row('PRICESECOND', mentions=19, mention_z=2, divergence=98,
            price_move=-0.30, price=5, direction='down', price_status='stale'),
        row('SURPRISE', mentions=8, mention_z=8, divergence=None,
            price_move=None, price=None, direction='flat', price_status='closed'),
    ]
    changed_quotes = [
        row('PRICEFIRST', mentions=20, mention_z=1, divergence=-99,
            price_move=None, price=None, direction='flat', price_status='stale'),
        row('PRICESECOND', mentions=19, mention_z=2, divergence=None,
            price_move=0.70, price=500, direction='up', price_status='ok'),
        row('SURPRISE', mentions=8, mention_z=8, divergence=1,
            price_move=-0.80, price=1, direction='down', price_status='closed'),
    ]
    active = original

    def rows_for_board(*_args, **_kwargs):
        return board.leaderboard.Ranking(rows=list(active), excluded={})

    monkeypatch.setattr(board.leaderboard, 'build_rows', rows_for_board)
    monkeypatch.setattr(board, 'session_state', lambda *_args, **_kwargs: 'regular')
    monkeypatch.setattr(board, '_next_boundary',
                        lambda _market, now, _session, **_kwargs: ('closes', now))
    monkeypatch.setattr(board, '_entries', lambda ranked, *_args: list(ranked))

    legacy = board.sort_rows(original, 'divergence', 'desc', {})[:2]
    assert 'SURPRISE' not in tickers(legacy)

    first = board.build(['bluesky'], now=dt.datetime(2026, 1, 1),
                        sort='chatter', direction='desc', limit=2)
    active = changed_quotes
    second = board.build(['bluesky'], now=dt.datetime(2026, 1, 1),
                         sort='chatter', direction='desc', limit=2)

    assert tickers(first.rows) == ['SURPRISE', 'PRICESECOND']
    assert tickers(second.rows) == tickers(first.rows)


def test_mentions_sorts_loudest_first_then_reverses():
    rows = [row('AAA', mentions=5), row('BBB', mentions=50),
            row('CCC', mentions=20)]

    assert tickers(board.sort_rows(rows, 'mentions', 'desc', {})) == [
        'BBB', 'CCC', 'AAA']
    assert tickers(board.sort_rows(rows, 'mentions', 'asc', {})) == [
        'AAA', 'CCC', 'BBB']


def test_ticker_sorts_case_insensitively():
    rows = [row('bbb'), row('AAA'), row('Ccc')]

    assert tickers(board.sort_rows(rows, 'ticker', 'asc', {})) == [
        'AAA', 'bbb', 'Ccc']
    assert tickers(board.sort_rows(rows, 'ticker', 'desc', {})) == [
        'Ccc', 'bbb', 'AAA']


def test_a_missing_value_sorts_last_in_BOTH_directions():
    """The trap: reverse=True would lift every unpriced row to the top, so
    reversing a price sort would answer with a wall of dashes."""
    rows = [row('AAA', divergence=0.5), row('GONE', divergence=None),
            row('BBB', divergence=0.1)]

    assert tickers(board.sort_rows(rows, 'divergence', 'desc', {})) == [
        'AAA', 'BBB', 'GONE']
    assert tickers(board.sort_rows(rows, 'divergence', 'asc', {})) == [
        'BBB', 'AAA', 'GONE']


def test_ratio_is_mentions_against_its_own_expected():
    """Not raw volume: a 5-mention ticker that normally sees 0.5 is louder
    against itself than a 50-mention ticker that normally sees 100."""
    rows = [row('LOUD', mentions=50, expected=100.0),
            row('ODD', mentions=5, expected=0.5)]

    assert tickers(board.sort_rows(rows, 'ratio', 'desc', {})) == ['ODD', 'LOUD']


def test_lean_ranks_by_net_bullish_COUNT_not_share():
    """The loudest positive talk goes to the top. A share instead put a
    single bullish post at 1.000 above nine bullish posts with two
    neutrals -- decided by a `neutral` count the row never displays."""
    rows = [row('LOUD'), row('THIN'), row('BEAR'), row('QUIET')]
    # Real Tone dataclasses -- what _tones actually hands sort_rows.
    leans = {'LOUD': board.Tone(bullish=9, neutral=2, bearish=0),   # net +9
             'THIN': board.Tone(bullish=1, neutral=0, bearish=0),   # net +1
             'BEAR': board.Tone(bullish=0, neutral=2, bearish=8),   # net -8
             'QUIET': board.Tone(bullish=0, neutral=0, bearish=0)}  # no tone

    # THIN would be FIRST under a share: 1/1 is a perfect 1.000.
    assert tickers(board.sort_rows(rows, 'lean', 'desc', leans)) == [
        'LOUD', 'THIN', 'BEAR', 'QUIET']
    assert tickers(board.sort_rows(rows, 'lean', 'asc', leans)) == [
        'BEAR', 'THIN', 'LOUD', 'QUIET']


def test_a_neutrally_discussed_ticker_keeps_its_place_at_zero():
    """Talked about with no lean either way is a real reading of zero --
    unlike a ticker nobody used a sentiment word about, which has none."""
    rows = [row('UP'), row('FLAT'), row('DOWN')]
    leans = {'UP': board.Tone(bullish=3, neutral=0, bearish=0),
             'FLAT': board.Tone(bullish=0, neutral=6, bearish=0),
             'DOWN': board.Tone(bullish=0, neutral=0, bearish=3)}

    assert tickers(board.sort_rows(rows, 'lean', 'desc', leans)) == [
        'UP', 'FLAT', 'DOWN']


def test_an_unknown_key_leaves_the_order_alone():
    """sort_rows is not the validator -- the route is. Given something it
    does not know it must not invent an order."""
    rows = [row('AAA', mentions=1), row('BBB', mentions=99)]

    assert tickers(board.sort_rows(rows, 'nonsense', 'desc', {})) == ['AAA', 'BBB']
    assert tickers(board.sort_rows(rows, None, 'desc', {})) == ['AAA', 'BBB']

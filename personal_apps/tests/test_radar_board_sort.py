"""Sorting the board: six keys, missing values last, and the sort happening
BEFORE the row limit -- which is the whole point of doing it server-side."""
import dataclasses

import pytest

from features.radar import board


def row(ticker, mentions=10, expected=5.0, divergence=None, price_move=None):
    """A stand-in for leaderboard.Row carrying only the sorted fields.

    sort_rows reads five attributes and a tones map; it never touches the
    quote, the marks or the series, so a namespace is a truthful fixture
    and keeps this suite independent of the DB.
    """
    return dataclasses.make_dataclass(
        'R', ['ticker', 'mentions', 'expected', 'divergence', 'price_move'])(
        ticker, mentions, expected, divergence, price_move)


def tickers(rows):
    return [r.ticker for r in rows]


def test_the_six_keys_are_the_wire_format():
    assert board.SORT_KEYS == ('ticker', 'mentions', 'divergence', 'ratio',
                               'move', 'lean')


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

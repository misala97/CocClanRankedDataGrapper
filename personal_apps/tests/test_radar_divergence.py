# personal_apps/tests/test_radar_divergence.py
"""The metric the product exists for.

Chatter far above normal while the price has not moved. Two corrections to the
naive mention_z minus price_move_z are what make it work at all -- see the
docstrings on each test.
"""
import pytest

from features.radar import divergence as div


def test_loud_and_unmoved_beats_loud_and_already_up():
    """The whole product in one assertion."""
    unmoved = div.divergence(mention_z=8.0, price_move_z=0.1)
    already_ran = div.divergence(mention_z=8.0, price_move_z=4.0)
    assert unmoved > already_ran


def test_the_mention_term_cannot_swamp_the_price_term():
    """Mention counts are heavy-tailed and reach z in the teens; volatility-
    normalized price moves rarely pass 4 sigma. Subtracting them raw makes
    divergence a slightly-adjusted mention_z, and the price side stops
    mattering."""
    huge = div.divergence(mention_z=40.0, price_move_z=4.0)
    modest = div.divergence(mention_z=6.0, price_move_z=0.0)
    assert modest > huge


def test_a_falling_price_does_not_score_as_unmoved():
    """With a signed term, a stock down four sigma scores HIGHER than a flat
    one, and the top of the board fills with things already dumping. "The
    price has not reflected it yet" is a claim about magnitude."""
    dumping = div.divergence(mention_z=8.0, price_move_z=-4.0)
    flat = div.divergence(mention_z=8.0, price_move_z=0.0)
    assert dumping < flat


def test_a_rising_and_falling_move_are_penalised_equally():
    assert div.divergence(8.0, 3.0) == pytest.approx(div.divergence(8.0, -3.0))


def test_divergence_is_bounded():
    assert -1.0 <= div.divergence(1000.0, 0.0) <= 1.0
    assert -1.0 <= div.divergence(0.0, 1000.0) <= 1.0


def test_quiet_and_moving_scores_low():
    """A price move nobody is discussing is not this tool's job."""
    assert div.divergence(mention_z=0.0, price_move_z=4.0) < 0


def test_price_move_z_normalizes_by_volatility():
    """Five percent on a penny stock is noise; five percent on a mega cap is an
    event. Ranking on raw percent would mark every small cap as already moved
    and hide real large-cap divergence."""
    calm = div.price_move_z(move=0.05, sigma=0.01)
    wild = div.price_move_z(move=0.05, sigma=0.20)
    assert calm > wild
    assert calm > 4


def test_price_move_z_is_none_without_a_sigma():
    """No volatility estimate means no opinion, which is different from an
    opinion of zero."""
    assert div.price_move_z(move=0.05, sigma=None) is None


def test_a_zero_sigma_does_not_divide_by_zero():
    assert div.price_move_z(move=0.05, sigma=0.0) is not None


def test_direction_reports_the_sign_separately():
    """Kept as its own column so loud-and-dumping is visible at a glance
    instead of inferred from a magnitude."""
    assert div.direction(0.05) == 'up'
    assert div.direction(-0.05) == 'down'
    assert div.direction(0.0001) == 'flat'

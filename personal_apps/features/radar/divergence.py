# personal_apps/features/radar/divergence.py
"""Chatter far above normal, against a price that has not moved.

Two corrections to the naive `mention_z - price_move_z`, both of which the
first draft got wrong:

Mention counts are heavy-tailed and reach z-scores in the teens, while
volatility-normalized price moves rarely pass 4 sigma. Subtracting them raw
leaves divergence as a slightly-adjusted mention_z, with the price side barely
able to influence the ranking at all. Both terms go through a bounded
transform first.

And price enters as MAGNITUDE. With a signed term a stock down four sigma
scores higher than a flat one, so the top of the board fills with things
already collapsing -- while "the price has not reflected it yet" is plainly a
claim about magnitude. The sign is kept, as its own column, so loud-and-dumping
is visible rather than inferred.
"""
import math

from .config import (DIVERGENCE_K_MENTION, DIVERGENCE_K_PRICE, FLAT_MOVE,
                     MIN_SIGMA)


def price_move_z(move, sigma):
    """How many sigma this move is, or None when volatility is unknown.

    None rather than zero: no volatility estimate means no opinion about
    whether the move was large, which is a different thing from an opinion
    that it was not.
    """
    if move is None or sigma is None:
        return None
    return float(move) / max(sigma, MIN_SIGMA)


def divergence(mention_z, price_move_z):
    """Bounded in (-1, 1). Higher means louder relative to how far it moved."""
    mention = math.tanh(mention_z / DIVERGENCE_K_MENTION)
    price = math.tanh(abs(price_move_z) / DIVERGENCE_K_PRICE)
    return mention - price


def direction(move):
    """'up', 'down' or 'flat' -- the sign divergence deliberately discards."""
    if move is None:
        return 'flat'
    if float(move) > FLAT_MOVE:
        return 'up'
    if float(move) < -FLAT_MOVE:
        return 'down'
    return 'flat'

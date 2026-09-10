"""The cache key for one board: every dimension its payload echoes back.

A shared cache answers one viewer with a board another viewer asked for the
moment two different questions hash the same. The PERF2 spike collapsed
duplicated segments -- `mid,micro,mid` and `mid,micro` keyed identically --
and the payload echoes the selection verbatim, so those two boards are not
interchangeable. Each dimension is pinned by its own test here, so widening
the key's normalization later means arguing with a named test rather than
quietly re-opening the collision.

Sources are the one deliberate normalization, and it has its own test saying
so. No database: a key is a pure function of an already-parsed query.
"""
import json

import pytest

from features.radar import board_keys
from features.radar.routes.api import Query


def q(**over):
    base = dict(sources=['bluesky', 'fourchan', 'reddit'], segments=[],
                window=12, limit=50, min_venues=1, market='us', sort=None,
                direction='desc')
    base.update(over)
    return Query(**base)


def test_duplicated_segments_are_a_different_key():
    """Codex reproduced the spike collapsing these. The payload echoes
    segments verbatim, so the key must too."""
    a, _ = board_keys.canonical(q(segments=['mid', 'micro', 'mid']))
    b, _ = board_keys.canonical(q(segments=['mid', 'micro']))
    assert a != b


def test_segment_order_is_a_different_key():
    assert board_keys.canonical(q(segments=['mid', 'micro']))[0] != \
        board_keys.canonical(q(segments=['micro', 'mid']))[0]


def test_direction_is_kept_even_without_a_sort():
    assert board_keys.canonical(q(direction='asc'))[0] != \
        board_keys.canonical(q(direction='desc'))[0]


def test_sources_are_deduplicated_and_sorted():
    """Task 7 proves the payload is byte-identical either way; this pins
    the normalization that proof licenses."""
    a, ja = board_keys.canonical(q(sources=['reddit', 'bluesky', 'reddit']))
    b, jb = board_keys.canonical(q(sources=['bluesky', 'reddit']))
    assert a == b and ja == jb


def test_market_must_be_resolved():
    with pytest.raises(AssertionError):
        board_keys.canonical(q(market='moon'))


def test_the_json_is_the_exact_inverse():
    query = q(segments=['mid', 'mid'], sort='lean', direction='asc',
              limit=100, min_venues=2, market='de',
              sources=['reddit:wallstreetbets', 'bluesky'])
    key_hash, key_json = board_keys.canonical(query)
    back = board_keys.query_from_json(key_json)
    assert board_keys.canonical(back) == (key_hash, key_json)
    assert back.segments == ['mid', 'mid'] and back.direction == 'asc'


def test_a_long_legal_key_round_trips():
    """37 sources of long-but-legal names: ~4,000 characters."""
    names = ['reddit:' + ('x' * 100) + str(i) for i in range(37)]
    key_hash, key_json = board_keys.canonical(q(sources=names))
    assert len(key_json) > 3500
    assert board_keys.round_trips(key_hash, key_json)
    assert not board_keys.round_trips(key_hash, key_json[:-1])


def test_the_key_version_is_two():
    assert json.loads(board_keys.canonical(q())[1])['v'] == 2

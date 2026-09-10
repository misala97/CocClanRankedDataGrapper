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
import hashlib
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


def _key_json(**over):
    """A raw key payload, json-encoded exactly like canonical() writes it,
    for tests that need to hand round_trips/query_from_json a shape no
    Query can produce on its own."""
    fields = dict(v=2, sources=['bluesky', 'reddit'], segments=[], window=12,
                  limit=50, venues=1, market='us', sort=None, dir='desc')
    fields.update(over)
    return json.dumps(fields, sort_keys=True, separators=(',', ':'))


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
    with pytest.raises(board_keys.BadKey):
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


def test_round_trips_catches_a_hash_match_that_cannot_reproduce():
    """round_trips has two checks because they fail differently. The first
    only confirms key_json wasn't corrupted in transit -- it says nothing
    about whether THIS build would still write that text. A row whose
    sources were stored unsorted hashes fine against itself, but canonical()
    sorts sources, so re-canonicalising the decoded query never gets back
    to the same bytes."""
    key_hash, key_json = board_keys.canonical(q(sources=['reddit', 'bluesky']))
    assert board_keys.round_trips(key_hash, key_json)

    fields = json.loads(key_json)
    key_json2 = json.dumps({**fields, 'sources': ['reddit', 'bluesky']},
                           sort_keys=True, separators=(',', ':'))
    key_hash2 = hashlib.sha256(key_json2.encode('utf-8')).hexdigest()

    assert not board_keys.round_trips(key_hash2, key_json2)


def test_an_unhashable_sources_element_is_refused_not_raised_through_round_trips():
    """query_from_json only ever required sources to be iterable, so a
    decoded Query could carry a nested list among its sources. canonical()'s
    `sorted(set(query.sources))` then raised a bare TypeError instead of
    BadKey, and round_trips -- which catches only BadKey -- let that
    TypeError escape to its caller instead of answering False. A corrupt
    stored row must make round_trips fail the row, not crash the producer."""
    key_json = _key_json(sources=[[1, 2], 'a'])
    key_hash = hashlib.sha256(key_json.encode('utf-8')).hexdigest()
    assert board_keys.round_trips(key_hash, key_json) is False


def test_an_int_among_segments_is_a_bad_key():
    key_json = _key_json(segments=['mid', 7])
    with pytest.raises(board_keys.BadKey):
        board_keys.query_from_json(key_json)


def test_a_string_window_is_a_bad_key():
    key_json = _key_json(window='12')
    with pytest.raises(board_keys.BadKey):
        board_keys.query_from_json(key_json)


def test_a_bool_limit_is_a_bad_key():
    """bool is a subclass of int in Python, so isinstance(True, int) is
    True -- a naive int check would silently accept a limit of True/False."""
    key_json = _key_json(limit=True)
    with pytest.raises(board_keys.BadKey):
        board_keys.query_from_json(key_json)


def test_a_list_sort_is_a_bad_key():
    key_json = _key_json(sort=['lean'])
    with pytest.raises(board_keys.BadKey):
        board_keys.query_from_json(key_json)


def test_an_unknown_extra_field_is_ignored_not_rejected():
    """The hash comparison already catches a payload that doesn't match its
    hash; query_from_json must not itself reject a forward-compatible extra
    field."""
    key_json = _key_json(extra='whatever')
    board_keys.query_from_json(key_json)  # must not raise


def test_canonical_rejects_non_string_sources_from_a_hand_built_query():
    """query_from_json now validates shapes on the way in, so this is belt
    and braces for a caller that builds a Query directly."""
    with pytest.raises(board_keys.BadKey):
        board_keys.canonical(q(sources=[['nested'], 'reddit']))


def test_canonical_rejects_non_string_segments_from_a_hand_built_query():
    with pytest.raises(board_keys.BadKey):
        board_keys.canonical(q(segments=['mid', 3]))

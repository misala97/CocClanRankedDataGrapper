"""The shared board key: the eight fields `_build_board` already keys on.

Part I.1 of PERF2-PLAN. The key is the canonical JSON of those eight fields;
its SHA-256 is the primary key and the JSON is stored beside it so a key is
readable without a decoder.

`canonical` applies ONLY dedupe by default. Sorting `sources`, sorting
`segments` and collapsing `dir` when `sort is None` are CANDIDATES that Task
S4 rules on by measuring payload digests; the flags exist so S4 can build both
orderings, and nothing else passes them. A larger key space is cheaper than a
wrong board.
"""
import hashlib
import json

KEY_VERSION = 1
MARKETS = ('us', 'de')


def _dedupe(values):
    """Order-preserving dedupe. Order is preserved because sorting is a
    candidate S4 has to prove, not a given."""
    seen = set()
    out = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def canonical(query, *, sort_sources=False, sort_segments=False,
              collapse_dir=False):
    """(key_hash, key_json) for a parsed `Query`.

    `query.market` must already be resolved. `parse_query` resolves an omitted
    market through `default_market(now)`, which flips between `de` and `us`
    with the session -- a key that carried the unresolved default would name a
    different board every few hours under the same hash.
    """
    assert query.market in MARKETS, 'market must be resolved: %r' % (
        query.market,)

    sources = _dedupe(query.sources)
    segments = _dedupe(query.segments)
    if sort_sources:
        sources = sorted(sources)
    if sort_segments:
        segments = sorted(segments)

    direction = query.direction
    if collapse_dir and query.sort is None:
        direction = 'desc'

    fields = {
        'v': KEY_VERSION,
        'sources': list(sources),
        'segments': list(segments),
        'window': query.window,
        'limit': query.limit,
        'venues': query.min_venues,
        'market': query.market,
        'sort': query.sort,
        'dir': direction,
    }
    key_json = json.dumps(fields, sort_keys=True, separators=(',', ':'))
    key_hash = hashlib.sha256(key_json.encode('utf-8')).hexdigest()
    return key_hash, key_json


def query_from_json(key_json, query_cls):
    """The `Query` a stored key names.

    The producer reads this out of the table rather than being handed a
    request: it is not on the request path, and the key JSON stored beside the
    hash is exactly so a key is actionable without a decoder.
    """
    fields = json.loads(key_json)
    assert fields['v'] == KEY_VERSION, 'key version %r' % (fields['v'],)
    return query_cls(sources=list(fields['sources']),
                     segments=list(fields['segments']),
                     window=fields['window'], limit=fields['limit'],
                     min_venues=fields['venues'], market=fields['market'],
                     sort=fields['sort'], direction=fields['dir'])

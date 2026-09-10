"""The cache key for one board: the question, canonically written down.

A stored board is addressed by (namespace, key_hash). The namespace says
which build answered; this module says what was asked. The rule the key has
to obey is simple and easy to get wrong: it must keep every dimension the
answer depends on, and the payload is the honest list of those dimensions,
because it echoes the selection straight back to the island. Two questions
that hash the same but echo differently is one viewer being handed another
viewer's board.

A PERF2 spike learned that the expensive way. It normalized segments the way
a tidy-minded reader would -- deduplicated and sorted -- and `mid,micro,mid`
started keying the same as `mid,micro`, two boards whose payloads differ in
the field the surface reads back to draw its chips. So segments are kept
verbatim, order and duplicates included, and so is the sort direction, which
means something even when no sort is named because the default ranking
reverses too.

Sources are the one normalization, deduplicated and sorted, because the
board's SQL turns them into an IN (...) whose result cannot depend on order
or repetition. That is an argument, not an assumption, and task 7 makes it
byte-for-byte against the payload.

The json half of the key is not decoration: it is the key in readable form,
so a stored row can say what it was for, and it is invertible, so a row can
be re-canonicalised and asked whether this build still agrees with it.
"""
import hashlib
import json

# Bumped when the fields, their names or their normalization change -- an
# old key must never be mistaken for a current one that happens to hash the
# same way. Version 1 was the spike's; nothing stored it.
KEY_VERSION = 2


def canonical(query):
    """(key_hash, key_json) for a parsed query.

    The json is compact and sorted by field name so the same question always
    produces the same bytes: the hash is over exactly this text, and the two
    halves of the key are only trustworthy together if the text is stable.

    The market is asserted rather than validated. parse_query resolves it to
    us|de before a Query exists, so a third value here is a caller that built
    a Query by hand -- a bug to stop where it happened, not a viewer's typo
    to answer politely.
    """
    assert query.market in ('us', 'de'), \
        f'the market must be resolved before keying: {query.market!r}'
    fields = {
        'v': KEY_VERSION,
        'sources': sorted(set(query.sources)),
        'segments': list(query.segments),
        'window': query.window,
        'limit': query.limit,
        'venues': query.min_venues,
        'market': query.market,
        'sort': query.sort,
        'dir': query.direction,
    }
    key_json = json.dumps(fields, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(key_json.encode('utf-8')).hexdigest(), key_json


def query_from_json(key_json):
    """The Query a key_json was written from -- the exact inverse of canonical.

    `Query` is imported at call time rather than at module load. It lives in
    the route module, which imports this one to key its own cache; importing
    it back at load time would close that circle. Rebuilding a query is also
    the rarer path -- writing a key does not need the class at all.
    """
    from .routes.api import Query

    fields = json.loads(key_json)
    assert fields.get('v') == KEY_VERSION, \
        f"not a v{KEY_VERSION} key: {fields.get('v')!r}"
    return Query(sources=list(fields['sources']),
                 segments=list(fields['segments']),
                 window=fields['window'],
                 limit=fields['limit'],
                 min_venues=fields['venues'],
                 market=fields['market'],
                 sort=fields['sort'],
                 direction=fields['dir'])


def round_trips(key_hash, key_json):
    """Does a stored pair still mean what it says?

    Two checks, because they fail differently. The hash catches a key_json
    that was truncated or edited on its way into or out of the row. Decoding
    it and canonicalising it again catches the subtler one: text that hashes
    correctly but is not what THIS build would write for that question -- a
    field renamed, a normalization widened, a key left behind by a version
    whose canonical() no longer exists. Both are answered False rather than
    raised, because the only sane response to either is to build the board
    again.
    """
    if hashlib.sha256(key_json.encode('utf-8')).hexdigest() != key_hash:
        return False
    try:
        return canonical(query_from_json(key_json)) == (key_hash, key_json)
    except (ValueError, TypeError, KeyError, AssertionError):
        return False

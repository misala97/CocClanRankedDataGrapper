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


class BadKey(ValueError):
    """A Query or a key_json does not describe a real board.

    Raised rather than asserted, because `python -O` strips `assert` and
    round_trips must be able to turn a corrupt or outdated key into a quiet
    False without depending on a guard that a deploy flag can remove. A
    ValueError subclass because that is already what json.loads raises for
    the same shape of mistake -- a caller only has one exception to catch.
    """


def canonical(query):
    """(key_hash, key_json) for a parsed query.

    The json is compact and sorted by field name so the same question always
    produces the same bytes: the hash is over exactly this text, and the two
    halves of the key are only trustworthy together if the text is stable.

    The market is checked rather than trusted. parse_query resolves it to
    us|de before a Query exists, so a third value here is a caller that built
    a Query by hand -- a bug to stop where it happened, not a viewer's typo
    to answer politely.

    sources and segments are checked the same way, and checked before the
    `sorted(set(...))` below rather than left for it to discover: a caller
    that hand-builds a Query with a nested list among its sources would
    otherwise hit a bare TypeError there instead of BadKey.
    query_from_json validates every field it decodes, so this is belt and
    braces for a Query no round-trip built.
    """
    if query.market not in ('us', 'de'):
        raise BadKey(f'market must be resolved: {query.market!r}')
    if not all(isinstance(item, str) for item in query.sources):
        raise BadKey(f'sources must all be str: {query.sources!r}')
    if not all(isinstance(item, str) for item in query.segments):
        raise BadKey(f'segments must all be str: {query.segments!r}')
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


def _is_str_list(value):
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _is_plain_int(value):
    # bool is a subclass of int, and isinstance(True, int) is True -- a
    # stored `"limit": true` must not silently pass as a limit of 1.
    return isinstance(value, int) and not isinstance(value, bool)


def query_from_json(key_json):
    """The Query a key_json was written from -- the exact inverse of canonical.

    `Query` is imported at call time rather than at module load. It lives in
    the route module, which imports this one to key its own cache; importing
    it back at load time would close that circle. Rebuilding a query is also
    the rarer path -- writing a key does not need the class at all.

    Every way this can fail -- text that isn't json, json that isn't an
    object, a version that isn't current, a field that's missing or the
    wrong shape -- is raised as BadKey. round_trips catches one exception,
    not whatever stdlib type happened to notice the corruption first.

    "Wrong shape" is checked field by field, not left for construction or
    canonical() to discover: json only promises sources/segments are
    iterable, an int is only promised to not be a string, and so on, so a
    decoded field can carry a shape canonical() cannot digest -- a nested
    list among sources is valid json and iterable, but unhashable, and
    `canonical()`'s `sorted(set(...))` would otherwise raise a bare
    TypeError past this function's contract. An unknown extra field in the
    payload is ignored, not rejected: the hash comparison in round_trips
    already catches a key_json that does not match what this build would
    have written.
    """
    from .routes.api import Query

    try:
        fields = json.loads(key_json)
    except json.JSONDecodeError as exc:
        raise BadKey(f'not valid json: {exc}') from exc

    if not isinstance(fields, dict):
        raise BadKey(f'not a key payload: {fields!r}')
    if fields.get('v') != KEY_VERSION:
        raise BadKey(f"key version {fields.get('v')!r} is not v{KEY_VERSION}")

    try:
        sources, segments = fields['sources'], fields['segments']
        window, limit, venues = fields['window'], fields['limit'], fields['venues']
        market, sort, direction = fields['market'], fields['sort'], fields['dir']
    except KeyError as exc:
        raise BadKey(f'missing field: {exc}') from exc

    if not _is_str_list(sources):
        raise BadKey(f'sources must be a list of str: {sources!r}')
    if not _is_str_list(segments):
        raise BadKey(f'segments must be a list of str: {segments!r}')
    if not _is_plain_int(window):
        raise BadKey(f'window must be an int: {window!r}')
    if not _is_plain_int(limit):
        raise BadKey(f'limit must be an int: {limit!r}')
    if not _is_plain_int(venues):
        raise BadKey(f'venues must be an int: {venues!r}')
    if not isinstance(market, str):
        raise BadKey(f'market must be a str: {market!r}')
    if sort is not None and not isinstance(sort, str):
        raise BadKey(f'sort must be a str or None: {sort!r}')
    if not isinstance(direction, str):
        raise BadKey(f'dir must be a str: {direction!r}')

    return Query(sources=sources, segments=segments, window=window,
                 limit=limit, min_venues=venues, market=market, sort=sort,
                 direction=direction)


def round_trips(key_hash, key_json):
    """Does a stored pair still mean what it says?

    Two checks, because they fail differently. The hash catches a key_json
    that was truncated or edited on its way into or out of the row. Decoding
    it and canonicalising it again catches the subtler one: text that hashes
    correctly but is not what THIS build would write for that question -- a
    field renamed, a normalization widened, a key left behind by a version
    whose canonical() no longer exists. Both are answered False rather than
    raised, because the only sane response to either is to build the board
    again. query_from_json and canonical raise nothing but BadKey, so that
    is the only exception this needs to catch.
    """
    if hashlib.sha256(key_json.encode('utf-8')).hexdigest() != key_hash:
        return False
    try:
        return canonical(query_from_json(key_json)) == (key_hash, key_json)
    except BadKey:
        return False

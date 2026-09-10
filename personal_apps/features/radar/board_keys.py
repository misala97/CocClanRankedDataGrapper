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
    """
    if query.market not in ('us', 'de'):
        raise BadKey(f'market must be resolved: {query.market!r}')
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

    Every way this can fail -- text that isn't json, json that isn't an
    object, a version that isn't current, a field that's missing or the
    wrong shape -- is raised as BadKey. round_trips catches one exception,
    not whatever stdlib type happened to notice the corruption first.
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
        return Query(sources=list(fields['sources']),
                     segments=list(fields['segments']),
                     window=fields['window'],
                     limit=fields['limit'],
                     min_venues=fields['venues'],
                     market=fields['market'],
                     sort=fields['sort'],
                     direction=fields['dir'])
    except (KeyError, TypeError) as exc:
        raise BadKey(f'missing or malformed field: {exc}') from exc


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

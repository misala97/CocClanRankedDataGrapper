"""One line per board read and per board build, with nobody's name in it.

Two lines, both on `radar.board`, both a fixed sequence of `field=value`
pairs. They are what tells an operator whether the shared path is working:
how often a reader is handed a board that was already there, how long a
viewer waits when it was not, and how much of a request is the board versus
the per-account half that can never be cached.

The identifier rule is not a convention here, it is the shape. Every value a
line can carry comes from a closed vocabulary, a twelve-character hex prefix
or a number, and anything else is refused rather than printed. That is
stricter than checking for the absence of a user id and it is stricter for a
reason: these lines describe requests made by named people about chosen
tickers, and the query string, the URL and the account are all one careless
`%s` away. A vocabulary cannot be careless.

Twelve hex characters of the key, not the whole 64: enough to follow one
board across a read, a build and a publish in the same log, and not enough to
be a handle on anything. The `key_json` -- which IS the query, in readable
form -- never appears at all.
"""
import logging
import re

logger = logging.getLogger('radar.board')

# The closed vocabularies. `class` is warm|ondemand rather than the store's
# warm|demand: the store is naming which QUEUE to look in, and these lines are
# naming what kind of board this was, which is how the read path spells it too.
_DEMAND = ('initial', 'poll')
_CLASS = ('warm', 'ondemand')
_OUTCOME = ('ready', 'stale', 'pending', 'busy', 'failed')
_RESULT = ('published', 'overtaken', 'failed')

_KEY = re.compile(r'^[0-9a-f]{12,64}$')

# How much of the key goes in a line.
KEY_WIDTH = 12


def log_read(*, demand, cls, key, outcome, cache_age, queue_age, read_ms,
             account_ms):
    """One board read, from the reader's side.

    `cls` rather than `class`, which is a keyword; it is written `class=` on
    the line. `cache_age` is how old the board served was, `queue_age` how
    long the key has been waiting -- each is `-` when the state has no such
    number, never a zero, because a zero there would read as "instantly" for
    a board that does not exist.
    """
    logger.info(
        'board read demand=%s class=%s key=%s outcome=%s cache_age=%s '
        'queue_age=%s read_ms=%s account_ms=%s',
        _word('demand', demand, _DEMAND), _word('class', cls, _CLASS),
        _key(key), _word('outcome', outcome, _OUTCOME),
        _seconds(cache_age), _seconds(queue_age),
        _count(read_ms), _count(account_ms))


def log_build(*, key, cls, queue_wait, build_ms, payload_bytes, result):
    """One board build, from the producer's side.

    `queue_wait` is how long the key sat in `pending` before this producer
    claimed it, which is the number a viewer actually experiences; `build_ms`
    is elapsed time by `perf_counter`, not a difference of wall clocks.
    `result=overtaken` is not a failure -- it is a build whose lease had
    expired and whose board was therefore older than the one already stored.
    """
    logger.info(
        'board build key=%s class=%s queue_wait=%s build_ms=%s '
        'payload_bytes=%s result=%s',
        _key(key), _word('class', cls, _CLASS), _seconds(queue_wait),
        _count(build_ms), _count(payload_bytes),
        _word('result', result, _RESULT))


def _word(field, value, vocabulary):
    if value not in vocabulary:
        raise ValueError(
            f'{field} must be one of {"|".join(vocabulary)}, not {value!r}')
    return value


def _key(value):
    """The first twelve hex characters, or a refusal.

    Checked rather than truncated blindly: `key[:12]` of a query string is
    twelve characters of a query string, and it would look like a key hash in
    the log for as long as nobody read it closely.
    """
    if not isinstance(value, str) or not _KEY.match(value):
        raise ValueError(f'key must be a hex key hash, not {value!r}')
    return value[:KEY_WIDTH]


def _seconds(value):
    """A duration to one decimal, or `-` for a state that has none.

    Clamped at zero. Every duration on these lines is a difference between two
    WALL clocks -- `cache_age` is now minus a stored `as_of`, `queue_age` is
    now minus an `enqueued_at` -- and the two readings need not have come from
    the same machine or from a machine whose clock never stepped sideways.
    `cache_age=-0.5` is a board built half a second into the future, which is
    not a thing an operator can act on and not a thing a dashboard parsing
    `\\d+\\.\\d` can even read.
    """
    return '-' if value is None else f'{max(0.0, float(value)):.1f}'


def _count(value):
    """A whole number. Milliseconds and bytes are never fractional here."""
    return str(int(value))

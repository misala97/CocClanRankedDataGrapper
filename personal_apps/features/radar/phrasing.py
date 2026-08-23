# personal_apps/features/radar/phrasing.py
"""Why a row is on the list, and what the panel found, in words.

Server-side because deciding which phrase a row deserves is judgement about
data, and it belongs where the data is and where pytest can reach it.

Typed clauses rather than a finished sentence because the client styles the
parts differently -- a ratio is not a warning is not a price move -- and a
client that re-derived the wording from raw numbers would be a second
implementation of the same judgement, free to disagree with this one.
"""
import dataclasses

from .config import PROVISIONAL_BASELINE_DAYS

# Below this, "n x its normal" is arithmetic on noise wearing the clothes of a
# finding. An expected of 0.2 mentions makes forty of them "200x normal",
# which is true and useless.
MIN_RATIO_BASELINE = 0.5

# Fewer independent voices than this is the shape of a pump, and it gets SAID
# rather than counted. "1 venue, 2 people" in the same grammar as a broad row
# buries the only thing worth knowing about it.
NARROW_VOICES = 3

# Below this the price did not really move. Printing "+0%" invites the reader
# to treat a rounding artifact as a finding.
FLAT_PERCENT = 0.5


@dataclasses.dataclass(frozen=True)
class Clause:
    """One styled fragment of a phrase.

    `kind` is the contract with the client: it styles by kind and never parses
    `text`. Adding a kind means adding a style, which is the intended friction
    -- it stops the vocabulary growing by accident.
    """
    kind: str
    text: str


def ratio_value(mentions, expected):
    """How many times its own normal this is, or None when there is no normal.

    The number behind the `ratio` clause, for a client that wants to DRAW it
    rather than read it -- the board's rows carry a bar of how far above
    normal they are. It shares this guard with the wording rather than
    repeating the threshold in TypeScript, so the bar and the words cannot
    come to different conclusions about whether a row is measurable at all.
    """
    if not expected or expected < MIN_RATIO_BASELINE:
        return None
    return mentions / expected


def _ratio(mentions, expected):
    """`40x` rather than `40.0x`, `3.5x` rather than `4x` at the low end.

    A tenth matters at 3.5 and is noise at 40, and trailing `.0` on a headline
    number reads as spurious precision.
    """
    value = mentions / expected
    if value >= 10:
        return f'{value:.0f}×'
    return f'{value:.1f}×'.replace('.0×', '×')


def row_clauses(row, session):
    """The phrase for one leaderboard row, in reading order.

    `session` is the exchange state. With the market shut there is no price
    clause at all -- the page says "market closed" once, and a mark carried by
    every row is not a mark.
    """
    clauses = []

    # An expected of zero is not "we expected none", it is "no baseline".
    if ratio_value(row.mentions, row.expected) is None:
        clauses.append(Clause('new', 'new here'))
        clauses.append(Clause(
            'ratio',
            f'{row.mentions} mentions, nothing to compare against yet'))
    else:
        clauses.append(Clause(
            'ratio', f'{_ratio(row.mentions, row.expected)} its normal'))

    clauses.extend(_breadth_clauses(row))
    clauses.extend(_price_clauses(row, session))
    return clauses


def _breadth_clauses(row):
    """How many independent things are saying it -- or, when too few are, one
    warning instead of two counts.

    Deliberately asymmetric. A broad row gets venues and people as separate
    facts because both are reassuring on their own; a narrow one gets a single
    warning, because "1 venue · 2 people" in the counting grammar reads as two
    small numbers rather than as the one thing that should stop you.
    """
    venues = len(row.sources)
    narrow = []
    if venues < 2:
        narrow.append('one venue only')
    if row.authors < NARROW_VOICES:
        narrow.append(f'{row.authors} voices')

    if narrow:
        return [Clause('warn', ', '.join(narrow))]
    return [Clause('venues', f'{venues} venues'),
            Clause('people', f'{row.authors} people')]


def _price_clauses(row, session):
    """Nothing at all when there is no price fact to state.

    Three different silences and only one of them is about the stock: the
    exchange is shut, which says nothing about this ticker; the tape froze,
    which says something and is a warning; or there is no quote at all.
    """
    if session == 'closed' or row.price_status == 'closed':
        return []
    if row.price_status == 'stale':
        return [Clause('warn', 'tape has not printed')]
    if row.price_move is None:
        return []

    pct = row.price_move * 100
    if abs(pct) < FLAT_PERCENT:
        return [Clause('price-flat', 'price flat')]
    kind = 'price-up' if pct > 0 else 'price-down'
    return [Clause(kind, f'price {pct:+.0f}%')]


def read_clauses(detail, mentions, expected, voices, session,
                 baseline_days=None, venues=0):
    """The panel's written read: two or three sentences of finding.

    Confined to facts the pipeline computes. It does NOT paraphrase what the
    posts say -- the page cannot summarise content it never understood, and
    the posts sit directly beneath it. An earlier draft wrote "the talk is
    about a shelf registration", which the page had no way to know; it was cut
    during mockup review and should stay cut.
    """
    out = []

    if ratio_value(mentions, expected) is None:
        out.append(Clause('plain',
                          f'{mentions} mentions in this window. This ticker '
                          f'has no baseline yet, so there is nothing to say '
                          f'how unusual that is.'))
    else:
        out.append(Clause('plain',
                          f'{mentions} mentions in this window, about '
                          f'{_ratio(mentions, expected)} the normal for this '
                          f'ticker, which is {expected:.0f}.'))

    if voices >= NARROW_VOICES:
        where = f' across {venues} venues' if venues > 1 else ''
        out.append(Clause('plain',
                          f'{voices} distinct voices{where}, so this is not '
                          f'one account repeating itself.'))
    else:
        out.append(Clause('warn',
                          f'Only {voices} distinct voices — one account can '
                          f'produce this much on its own.'))

    out.extend(_read_price(detail, session))

    if baseline_days is not None and baseline_days < PROVISIONAL_BASELINE_DAYS:
        days = 'day' if baseline_days == 1 else 'days'
        out.append(Clause('warn',
                          f'The baseline is {baseline_days} {days} old, not '
                          f'30, so this rests on very little history.'))
    return out


def _read_price(detail, session):
    """What the tape did, or why there is nothing to say about it."""
    if session == 'closed' or detail.price_status == 'closed':
        return [Clause('plain',
                       'The market is shut, so there is no price move to '
                       'compare this against — divergence needs a live tape '
                       'and returns with one.')]
    if detail.price_status == 'stale':
        return [Clause('warn',
                       'The tape has not printed in this window, so the price '
                       'cannot be taken at face value.')]
    if detail.price_move is None:
        return []

    pct = detail.price_move * 100
    verb = ('the talk and the tape agree' if abs(pct) >= 1
            else 'the talk has moved and the price has not')
    return [Clause('plain',
                   f'The price moved {pct:+.1f}% over the same window, so '
                   f'{verb}.')]

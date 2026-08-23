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
    if not row.expected or row.expected < MIN_RATIO_BASELINE:
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


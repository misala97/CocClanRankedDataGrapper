# personal_apps/tests/test_radar_phrasing.py
"""The row phrase is the answer to "why is this on the list".

The live board's failure was not that the numbers were wrong. It was that the
biggest number on the page belonged to the row that scored nothing, and
nothing said why. Michi's words on 2026-08-23: "i have no real idea why and
what is worth looking at."

So the wording IS the feature, and these pin it.
"""
import dataclasses

from features.radar import phrasing


@dataclasses.dataclass
class FakeRow:
    ticker: str = 'ZZZ'
    mentions: int = 40
    expected: float = 1.0
    authors: int = 11
    sources: tuple = ('bluesky', 'fourchan')
    price_move: float | None = 0.182
    price_status: str = 'ok'
    baseline_days: int | None = 30
    mention_z: float | None = 4.1


def kinds(clauses):
    return [c.kind for c in clauses]


def text(clauses):
    return ' '.join(c.text for c in clauses)


def test_a_measurable_row_says_how_unusual_how_broad_and_what_price_did():
    clauses = phrasing.row_clauses(FakeRow(), session='regular')

    assert kinds(clauses) == ['ratio', 'venues', 'people', 'price-up']
    assert '40x its normal' in text(clauses).replace('×', 'x')
    assert '2 venues' in text(clauses)
    assert '11 people' in text(clauses)


def test_no_baseline_is_not_a_ratio_against_zero():
    """The live page printed "209 mentions in 4h against 0 typical" and then
    scored it with an em-dash. An expected of zero does not mean we expected
    none; it means there is no baseline. Rendering it as a quantity is the
    absence-as-zero mistake the project exists to avoid."""
    clauses = phrasing.row_clauses(
        FakeRow(mentions=209, expected=0.0, mention_z=None), session='regular')

    assert kinds(clauses)[0] == 'new'
    assert '209 mentions' in text(clauses)
    assert 'nothing to compare against yet' in text(clauses)
    assert '0 typical' not in text(clauses)


def test_a_thin_baseline_is_treated_as_no_baseline():
    """An expected of 0.2 is not a baseline either -- "200x its normal" off
    one mention a week is arithmetic on noise wearing the clothes of a
    finding."""
    clauses = phrasing.row_clauses(
        FakeRow(mentions=40, expected=0.2), session='regular')

    assert kinds(clauses)[0] == 'new'


def test_a_narrow_row_says_so_instead_of_counting_venues():
    """One venue and two voices is the shape of a pump. Saying "1 venue,
    2 people" in the same grammar as a broad row buries the one fact that
    matters about it."""
    clauses = phrasing.row_clauses(
        FakeRow(sources=('bluesky',), authors=2), session='regular')

    assert 'warn' in kinds(clauses)
    assert 'one venue only' in text(clauses)
    assert '2 voices' in text(clauses)
    assert 'venues' not in kinds(clauses)


def test_a_broad_row_is_not_warned_about():
    clauses = phrasing.row_clauses(FakeRow(), session='regular')

    assert 'warn' not in kinds(clauses)


def test_a_closed_market_carries_no_price_clause():
    """The page says "market closed" once. Repeating it on every row makes it
    noise -- the same rule that removed `provisional` from every row in
    August -- and printing 0.00% asserts the price held steady when nothing
    traded."""
    clauses = phrasing.row_clauses(
        FakeRow(price_status='closed', price_move=None), session='closed')

    assert not any(k.startswith('price') for k in kinds(clauses))


def test_a_frozen_tape_is_not_a_flat_price():
    """A tape that has not printed is a fact about the stock and earns a mark.
    A closed exchange is not, and earns nothing."""
    clauses = phrasing.row_clauses(
        FakeRow(price_status='stale', price_move=None), session='regular')

    assert 'price-flat' not in kinds(clauses)
    assert 'warn' in kinds(clauses)
    assert 'not printed' in text(clauses)


def test_a_price_that_barely_moved_says_flat():
    clauses = phrasing.row_clauses(
        FakeRow(price_move=0.001), session='regular')

    assert 'price-flat' in kinds(clauses)


def test_a_falling_price_is_its_own_kind():
    """The client styles by kind, and green and red mean price direction and
    nothing else on this surface. A single `price` kind would force the client
    to parse the text for a minus sign."""
    clauses = phrasing.row_clauses(
        FakeRow(price_move=-0.07), session='regular')

    assert 'price-down' in kinds(clauses)
    assert '-7%' in text(clauses).replace('−', '-')


# ---------------------------------------------------------------- the read ---

class FakeChart:
    closes = [1.0, 2.0]
    watched_from = None


@dataclasses.dataclass
class FakeDetail:
    ticker: str = 'ZZZ'
    price_move: float | None = 0.182
    price_status: str = 'ok'
    chart: object = dataclasses.field(default_factory=FakeChart)


def test_the_read_leads_with_the_finding():
    clauses = phrasing.read_clauses(
        FakeDetail(), mentions=284, expected=7.0, voices=11,
        session='regular')

    assert '284' in clauses[0].text


def test_the_read_names_its_own_weak_baseline():
    """A 40x reading off two days of history is not the same claim as one off
    thirty, and the page has to say which claim it is making."""
    clauses = phrasing.read_clauses(
        FakeDetail(), mentions=284, expected=7.0, voices=11,
        session='regular', baseline_days=2)

    assert any(c.kind == 'warn' and 'baseline' in c.text for c in clauses)


def test_a_full_baseline_earns_no_caveat():
    clauses = phrasing.read_clauses(
        FakeDetail(), mentions=284, expected=7.0, voices=11,
        session='regular', baseline_days=30)

    assert not any('baseline' in c.text for c in clauses)


def test_the_read_does_not_paraphrase_what_people_said():
    """Cut during mockup review. The page cannot summarise content it never
    understood, and the posts are directly below it."""
    joined = ' '.join(c.text for c in phrasing.read_clauses(
        FakeDetail(), mentions=284, expected=7.0, voices=11,
        session='regular')).lower()

    for word in ('filing', 'squeeze', 'announced', 'news about'):
        assert word not in joined


def test_a_closed_market_says_there_is_nothing_to_compare_against():
    clauses = phrasing.read_clauses(
        FakeDetail(price_status='closed', price_move=None), mentions=26,
        expected=3.0, voices=6, session='closed')

    joined = ' '.join(c.text for c in clauses)
    assert 'market is shut' in joined
    assert 'divergence' in joined


def test_the_read_warns_when_too_few_voices_carry_it():
    clauses = phrasing.read_clauses(
        FakeDetail(), mentions=284, expected=7.0, voices=2, session='regular')

    assert any(c.kind == 'warn' and 'one account' in c.text for c in clauses)


def test_the_read_has_no_baseline_sentence_when_there_is_no_baseline():
    """Same rule as the row phrase: an expected of zero is not a ratio."""
    joined = ' '.join(c.text for c in phrasing.read_clauses(
        FakeDetail(), mentions=209, expected=0.0, voices=7, session='regular'))

    assert 'no baseline yet' in joined
    assert '0 typical' not in joined

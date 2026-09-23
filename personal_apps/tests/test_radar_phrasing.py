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
from features.radar.config import source_root


@dataclasses.dataclass
class FakeRow:
    ticker: str = 'ZZZ'
    mentions: int = 40
    expected: float = 1.0
    authors: int = 11
    sources: tuple = ('bluesky', 'fourchan')
    price_move: float | None = 0.182
    price_status: str = 'ok'
    baseline_days: float | None = 30
    mention_z: float | None = 4.1

    @property
    def venues(self):
        """Derived rather than a field, so the fake cannot claim a breadth
        its own source list does not support. One venue per ROOT: two
        subreddits are one venue, which is what the real Row.venues counts."""
        return len({source_root(name) for name in self.sources})


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
class FakeQuote:
    """Only the quote fact the price clause reads."""
    price_basis: str | None = 'trade'


@dataclasses.dataclass
class FakeDetail:
    ticker: str = 'ZZZ'
    price_move: float | None = 0.182
    price_status: str = 'ok'
    chart: object = dataclasses.field(default_factory=FakeChart)
    quote: object = None


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


def test_a_fractional_baseline_reads_as_words_not_a_raw_float():
    """Task 16 made `baseline_days` a fraction of a day, not a truncated int.
    An hour-old baseline is `0.041666666666666664` -- interpolated straight
    into the sentence, that read "The baseline is 0.041666666666666664 days
    old", which is exactly the population 'warming-up' exists to describe
    correctly. The sentence must not leak the float."""
    clauses = phrasing.read_clauses(
        FakeDetail(), mentions=284, expected=7.0, voices=11,
        session='regular', baseline_days=1 / 24)

    warn = next(c for c in clauses if c.kind == 'warn' and 'baseline' in c.text)
    assert warn.text == ('The baseline is under a day old, not 30, so this '
                         'rests on very little history.')


def test_a_multi_day_fractional_baseline_rounds_to_a_whole_day():
    """A span like 2.7 days must round for display, not truncate (`.days`
    truncation is the exact bug Task 16 fixed) and must not print the
    fraction either."""
    clauses = phrasing.read_clauses(
        FakeDetail(), mentions=284, expected=7.0, voices=11,
        session='regular', baseline_days=2.7)

    warn = next(c for c in clauses if c.kind == 'warn' and 'baseline' in c.text)
    assert '3 days' in warn.text
    assert '2.7' not in warn.text


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


def test_a_row_under_the_floor_says_why_instead_of_a_ratio():
    from features.radar import leaderboard
    from features.radar.phrasing import row_clauses

    def quiet(reason, mentions=0, authors=0):
        return leaderboard.Row(
            ticker='LBQ', name='Q', segment='micro', divergence=None,
            mention_z=None, mentions=mentions, expected=0.0, authors=authors,
            text_ratio=1.0, sources=[], venues=0, price=None, price_move=None,
            direction='flat', price_status='unknown', quote=None,
            baseline_days=None, marks=[], eligible=False, floor_reason=reason)

    def words(reason, mentions=0, authors=0):
        clauses = row_clauses(quiet(reason, mentions, authors), 'closed', 4)
        assert [c.kind for c in clauses] == ['warn']
        return clauses[0].text

    assert words('no_mentions') == 'no mentions in 4h'
    assert words('too_few_mentions', 2, 1) == '2 mentions in 4h, under the floor'
    assert words('too_few_mentions', 1, 1) == '1 mention in 4h, under the floor'
    assert words('too_few_voices', 6, 1) == 'one voice only, under the floor'
    assert words('too_few_voices', 6, 2) == '2 voices, under the floor'
    assert words('repeated_text', 9, 4) == 'repeated text, under the floor'
    # The window is the selection's, not a constant.
    assert row_clauses(quiet('no_mentions'), 'closed', 24)[0].text == 'no mentions in 24h'


# --- the price clause is descriptive (Codex B1 ruling, 2026-09-10, item 3) --


def _read(detail, session='regular'):
    return phrasing.read_clauses(detail, mentions=284, expected=7.0,
                                 voices=11, session=session)


def _price_text(detail, session='regular'):
    """Only the sentences the price clause produced, joined."""
    clauses = _read(detail, session)
    # The first two clauses are the finding and the breadth; everything the
    # price path says follows them, before any baseline caveat.
    return ' '.join(c.text for c in clauses[2:]
                    if 'baseline' not in c.text).replace('−', '-')


def test_a_falling_move_is_stated_as_a_measurement_and_nothing_more():
    """The exact clause the ruling gives as its example. No agreement, no
    causation: the panel never tested which way the talk leaned, so it has
    no business saying the tape agrees with it."""
    joined = _price_text(FakeDetail(price_move=-0.023))

    assert 'The price moved -2.3% over the measured window.' in joined
    assert 'agree' not in joined
    assert 'talk' not in joined
    assert 'has not' not in joined


def test_a_rising_move_is_stated_the_same_way():
    joined = _price_text(FakeDetail(price_move=0.182))

    assert 'The price moved +18.2% over the measured window.' in joined
    assert 'agree' not in joined


def test_a_move_under_one_percent_is_still_just_the_number():
    """The old wording turned anything under 1% into "the talk has moved and
    the price has not" -- a claim about the talk from a fact about the
    price. Now it is the number, and only the number."""
    joined = _price_text(FakeDetail(price_move=0.004))

    assert 'The price moved +0.4% over the measured window.' in joined
    assert 'has not' not in joined
    assert 'agree' not in joined


def test_an_absent_move_is_absent_not_zero():
    """`move_since` returns None when there were fewer than two snapshots to
    measure between. That is nothing to say, not a 0.0% move."""
    joined = _price_text(FakeDetail(price_move=None))

    assert 'price moved' not in joined
    assert '0.0%' not in joined
    assert joined == ''


def test_a_shut_market_keeps_a_measured_move_and_says_it_is_historical():
    """The B1 defect: the candidate rail printed +4.6% while the panel beside
    it said the market being shut meant there was no price move. The move
    exists; the session is what limits it."""
    joined = _price_text(FakeDetail(price_move=0.046, price_status='closed'),
                         session='closed')

    assert 'The price moved +4.6% over the measured window.' in joined
    assert 'Market closed; this is a historical window move.' in joined
    assert 'no price move' not in joined
    assert 'agree' not in joined


def test_a_shut_market_with_nothing_measured_still_says_so():
    """The pre-existing sentence for the case with NO measured move stays:
    it is the one that is true there, and its own test above pins it."""
    joined = _price_text(FakeDetail(price_move=None, price_status='closed'),
                         session='closed')

    assert 'market is shut' in joined
    assert 'divergence' in joined


def test_a_frozen_tape_keeps_the_measured_move_and_its_warning():
    clauses = _read(FakeDetail(price_move=-0.031, price_status='stale'))
    joined = ' '.join(c.text for c in clauses).replace('−', '-')

    assert 'The price moved -3.1% over the measured window.' in joined
    assert 'has not printed' in joined
    assert any(c.kind == 'warn' and 'not printed' in c.text for c in clauses)
    assert 'agree' not in joined


def test_a_frozen_tape_with_nothing_measured_keeps_only_the_warning():
    clauses = _read(FakeDetail(price_move=None, price_status='stale'))

    assert any(c.kind == 'warn' and 'not printed' in c.text for c in clauses)
    assert not any('price moved' in c.text for c in clauses)


def test_a_non_trade_basis_keeps_the_move_and_names_the_basis():
    """The population the detail panel's gate removal newly reaches: a
    closing price as the latest quote. The move was measured between real
    trades; the CURRENT quote is what is not scorable, and the clause says
    which of those two things is true."""
    clauses = _read(FakeDetail(price_move=0.005,
                               quote=FakeQuote(price_basis='close')))
    joined = ' '.join(c.text for c in clauses)

    assert 'The price moved +0.5% over the measured window.' in joined
    assert 'closing price, not an executed trade' in joined
    assert 'scored signal' in joined
    assert 'agree' not in joined
    assert not any(c.kind == 'warn' for c in clauses), (
        'a non-trade basis is a limitation, not a caution')


def test_a_midpoint_basis_is_named_as_one():
    joined = _price_text(FakeDetail(price_move=0.02,
                                    quote=FakeQuote(price_basis='midpoint')))

    assert 'bid/ask midpoint, not an executed trade' in joined


def test_no_clause_speaks_of_another_listing():
    """Radar quotes US listings only; there is no other listing to name."""
    clauses = _read(FakeDetail(price_move=0.02, quote=FakeQuote()))
    joined = ' '.join(c.text for c in clauses)

    assert 'The price moved +2.0% over the measured window.' in joined
    assert 'listing' not in joined
    assert not any(c.kind == 'warn' for c in clauses)


def test_a_trade_basis_native_listing_adds_no_limitation():
    joined = _price_text(FakeDetail(price_move=0.02, quote=FakeQuote()))

    assert joined == 'The price moved +2.0% over the measured window.'


def test_the_row_phrase_is_untouched_by_the_panel_correction():
    """The ROW clause was never the problem and is not what the ruling
    corrects: `price +18%` stays exactly as it was."""
    clauses = phrasing.row_clauses(FakeRow(price_move=0.182), session='regular')

    assert 'price +18%' in text(clauses)
    assert 'price-up' in kinds(clauses)

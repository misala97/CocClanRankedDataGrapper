"""Turning the relevance labels we already have into span supervision.

The extraction model answers a question the judge cannot: WHICH words in a
post name a company. Every labelled row already carries that, because the
candidate files record the `evidence` token that produced the row, and it
is locatable in the text for 4,474 of 4,500 wave rows.

The labels give BOTH sides of the same surface form, which is what makes
this worth doing without new labelling: `Apple` judged relevant is a
company mention, `apple` judged irrelevant is not, and `internet` is never
one. A tagger trained on positives alone would learn a word list; trained
on both it learns context.
"""
from scratchpad.label_export import span_dataset as sd


def _row(text, evidence, relevance='relevant', ticker='GPRO'):
    return {'author_text': text, 'evidence': evidence, 'relevance': relevance,
            'ticker': ticker, 'mention_id': -1}


def test_a_relevant_candidate_marks_its_span():
    spans = sd.spans_for(_row('my GoPro broke yesterday', 'GoPro'))
    assert spans == [(3, 8, 'GPRO')]


def test_an_irrelevant_candidate_marks_nothing_but_is_still_a_row():
    """The post is a NEGATIVE example: the token is there and is not a
    company. Dropping it would teach the tagger a word list."""
    spans = sd.spans_for(_row('the internet is down', 'internet',
                              relevance='irrelevant', ticker='INTZ'))
    assert spans == []


def test_an_uncertain_candidate_is_excluded_entirely():
    """Neither a span nor a clean negative -- training on it as either
    would be inventing an answer the teacher refused to give."""
    assert sd.spans_for(_row('gme', 'gme', relevance='uncertain')) is None


def test_the_match_is_case_insensitive_but_the_offsets_are_exact():
    spans = sd.spans_for(_row('do not buy moderna today', 'Moderna', ticker='MRNA'))
    assert spans == [(11, 18, 'MRNA')]


def test_only_whole_words_count():
    """`app` must not mark the first three letters of `apple`.

    Unfindable means DROPPED (None), not an empty span list: an empty list
    asserts "the token is here and names nothing", and we cannot claim that
    about a token we could not locate."""
    assert sd.spans_for(_row('i ate an apple', 'app', ticker='APP')) is None
    assert sd.spans_for(_row('the app crashed', 'app', ticker='APP')) == [(4, 7, 'APP')]


def test_every_occurrence_of_the_token_is_marked():
    spans = sd.spans_for(_row('GoPro up, GoPro down', 'GoPro'))
    assert spans == [(0, 5, 'GPRO'), (10, 15, 'GPRO')]


def test_a_cashtag_span_includes_the_dollar_sign():
    spans = sd.spans_for(_row('loading $GME calls', '$GME', ticker='GME'))
    assert spans == [(8, 12, 'GME')]


def test_a_row_whose_evidence_is_not_in_the_text_is_dropped_not_guessed():
    assert sd.spans_for(_row('nothing here', 'GoPro')) is None


def test_rows_for_one_post_are_merged_into_a_single_example():
    """A post mentioning two companies is ONE training example with two
    spans, not two examples that each call the other's span background."""
    rows = [_row('NVDA and GoPro', 'NVDA', ticker='NVDA'),
            _row('NVDA and GoPro', 'GoPro', ticker='GPRO')]
    [example] = sd.examples_from(rows, key=lambda r: r['author_text'])
    assert example['text'] == 'NVDA and GoPro'
    assert sorted(example['spans']) == [(0, 4, 'NVDA'), (9, 14, 'GPRO')]


def test_a_post_with_only_irrelevant_rows_is_kept_as_a_pure_negative():
    rows = [_row('the internet is down', 'internet', relevance='irrelevant',
                 ticker='INTZ')]
    [example] = sd.examples_from(rows, key=lambda r: r['author_text'])
    assert example['spans'] == []
    assert example['negatives'] == ['internet']


def test_a_post_whose_every_row_was_uncertain_is_dropped():
    rows = [_row('gme', 'gme', relevance='uncertain')]
    assert sd.examples_from(rows, key=lambda r: r['author_text']) == []


# ---- v2: filling what a mention-sampled wave never labelled ------------------

NAMES = {'nvidia', 'google', 'nike'}
SYMBOLS = {'NVDA', 'AI', 'SPY', 'GOOGL'}


def test_augment_fills_unlabelled_names_as_silver_and_masks_symbols():
    ex = {'text': 'NVDA up, Google flat, AI hype, $spy down', 'spans': [[0, 4, 'NVDA']],
          'negatives': []}
    got = sd.augment(ex, NAMES, SYMBOLS)
    assert got['silver'] == [(9, 15)]            # Google, a name -> positive
    assert got['ignore'] == [(22, 24), (31, 35)]  # AI and $spy -> masked
    assert got['spans'] == ex['spans']            # gold untouched


def test_augment_never_touches_gold_or_judged_negatives():
    # 'nvidia' is gold here and 'google' was judged irrelevant: both stay as
    # they are, silver fills nothing on top of them.
    ex = {'text': 'nvidia and google and nike', 'spans': [[0, 6, 'NVDA']],
          'negatives': ['google']}
    got = sd.augment(ex, NAMES, SYMBOLS)
    assert got['silver'] == [(22, 26)]           # only nike


def test_augment_is_whole_word_and_case_insensitive():
    ex = {'text': 'Nikes and NIKE and snike', 'spans': [], 'negatives': []}
    assert sd.augment(ex, NAMES, SYMBOLS)['silver'] == [(10, 14)]


def test_augment_masks_only_symbols_written_as_symbols():
    # 'spy' lowercase is not a symbol mention; 'SPY' and '$SPY' are.
    ex = {'text': 'spy SPY $SPY', 'spans': [], 'negatives': []}
    assert sd.augment(ex, NAMES, SYMBOLS)['ignore'] == [(4, 7), (8, 12)]


def test_augment_ignore_never_overlaps_silver():
    ex = {'text': 'GOOGL Google', 'spans': [], 'negatives': []}
    got = sd.augment(ex, {'google'}, {'GOOGL'})
    assert got['silver'] == [(6, 12)] and got['ignore'] == [(0, 5)]


def test_vouching_counts_only_the_examples_it_is_given():
    # A name gold-confirmed only in a held-out row must not be vouched when
    # vouching runs over the training rows alone.
    from scratchpad.label_export import build_spans_v2 as b2
    train = [{'text': 'nvidia rocks', 'spans': [[0, 6, 'NVDA']]}] * 3
    held = [{'text': 'korea power', 'spans': [[0, 5, 'KEP']]}] * 3
    candidates = {'nvidia', 'korea'}
    assert b2.vouched_names(train, candidates, {}, 3) == {'nvidia'}
    assert b2.vouched_names(train + held, candidates, {}, 3) == {'nvidia', 'korea'}
    assert b2.vouched_names(train, candidates, {'google': 'GOOGL'}, 3) == {'nvidia', 'google'}

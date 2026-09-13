import datetime as dt

from features.radar import chatter_tone


def test_recorded_tone_prefers_model_verdict_over_lexical_score():
    assert chatter_tone.classify_recorded_tone(
        attitude='negative', llm_sentiment=None, lexicon_sentiment=0.9,
    ) == 'bearish'


def test_lexical_score_without_recorded_verdict_is_unjudged():
    assert chatter_tone.classify_recorded_tone(
        attitude=None, llm_sentiment=None, lexicon_sentiment=0.9,
    ) == 'unjudged'


def test_explicit_mixed_and_none_are_neutral():
    assert chatter_tone.classify_recorded_tone(
        attitude='mixed', llm_sentiment=None, lexicon_sentiment=-0.9,
    ) == 'neutral'
    assert chatter_tone.classify_recorded_tone(
        attitude='none', llm_sentiment=None, lexicon_sentiment=None,
    ) == 'neutral'


def test_legacy_directional_and_neutral_verdicts_remain_usable():
    assert chatter_tone.classify_recorded_tone(
        attitude=None, llm_sentiment='bullish', lexicon_sentiment=None,
    ) == 'bullish'
    assert chatter_tone.classify_recorded_tone(
        attitude=None, llm_sentiment='neutral', lexicon_sentiment=-0.2,
    ) == 'neutral'
    assert chatter_tone.classify_recorded_tone(
        attitude=None, llm_sentiment='unclear', lexicon_sentiment=None,
    ) == 'unjudged'


def test_reconcile_slot_is_exhaustive_and_total_denominator_is_authoritative():
    slot = chatter_tone.reconcile_slot(
        total=10,
        source_bins=[
            {'total': 10, 'bullish': 4, 'bearish': 2, 'neutral': 1,
             'unjudged': 3, 'unavailable': 0},
        ],
    )
    assert slot == {
        'bullish': 4, 'bearish': 2, 'neutral': 1, 'unjudged': 3,
        'unavailable': 0, 'status': 'complete',
    }


def test_reconcile_old_or_pruned_evidence_is_unavailable_not_neutral():
    assert chatter_tone.reconcile_slot(
        total=10,
        source_bins=[
            {'total': 10, 'bullish': 0, 'bearish': 0, 'neutral': 0,
             'unjudged': 0, 'unavailable': 10},
        ],
    )['status'] == 'unavailable'


def test_reconcile_zero_and_null_totals_are_distinct():
    assert chatter_tone.reconcile_slot(total=0, source_bins=[]) == {
        'bullish': 0, 'bearish': 0, 'neutral': 0, 'unjudged': 0,
        'unavailable': 0, 'status': 'complete',
    }
    assert chatter_tone.reconcile_slot(total=None, source_bins=[]) is None


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


def test_mismatched_source_does_not_erase_other_sources():
    slot = chatter_tone.reconcile_slot(total=10, source_bins=[
        {'total': 4, 'bullish': 3},
        {'total': 6, 'bearish': 6},
    ])
    assert slot == dict(bullish=0, bearish=6, neutral=0, unjudged=0,
                        unavailable=4, status='partial')

def test_guarded_real_sql_source_reconciliation_and_retention():
    """Opt-in integration; uses only reserved rollback-only fixture rows."""
    import importlib.util
    import os
    import pathlib
    import pytest
    if os.environ.get('RADAR_DESTRUCTIVE_TEST_TARGET') != 'localhost:3306/personal_apps_radar_b1c':
        pytest.skip('requires independently registered disposable B1C target')
    path = pathlib.Path(__file__).parents[1] / 'scratchpad/b1c/probe_tone.py'
    spec = importlib.util.spec_from_file_location('b1c_tone_probe', path)
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    with probe.app.app_context():
        assert probe.require(probe.db.engine.url) == 'localhost:3306/personal_apps_radar_b1c'
        for model in [probe.RadarMentionEvent, probe.RadarMention, probe.RadarBucketSource]:
            assert probe.db.session.query(model).filter(model.ticker == 'B1CTEST').first() is None
        try:
            assert len(probe.correctness()) == 6
        finally:
            probe.db.session.rollback()
        assert probe.db.session.query(probe.RadarMentionEvent).filter_by(ticker='B1CTEST').first() is None

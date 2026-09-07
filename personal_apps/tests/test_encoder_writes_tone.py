"""The encoder publishes tone, because the incumbent is worse.

The flag was set False on the reasoning that a wrong arrow is worse than
no arrow. Measured 2026-09-07 on the 5,583 labelled rows where the author
clearly took a side, that reasoning had the wrong comparison: blank was
never the alternative, because the board falls back to the lexicon and
publishes THAT.

  lexicon (shipping today)   silent on 59.7%, and of the calls it does
                             make, 29.8% are the wrong side
  encoder (this model)       11.8% of directional rows reversed

And a board aggregates. At a 12% per-mention reversal rate a ticker
showing 7 bullish against 1 bearish reads the wrong net direction 3.6% of
the time; under the lexicon's rate, 28%.
"""
from features.radar import judge_backends as jb


def test_the_encoder_publishes_tone():
    assert jb.EncoderBackend.writes_tone is True


def test_a_stored_row_is_judged_by_what_it_CARRIES_not_by_its_model_id():
    """The encoder wrote tone-less rows before 2026-09-07 and tone-bearing
    rows after, under the same model id. An id cannot tell them apart, so
    the question 'can this row be trusted whole' has to ask the row."""
    import types
    tone_less = types.SimpleNamespace(
        sentiment_model=jb.ENCODER_MODEL_ID, sentiment_relevance='relevant',
        sentiment_content_origin='human_chatter', sentiment_attitude=None,
        sentiment_expected_move=None, sentiment_confidence=None)
    complete = types.SimpleNamespace(
        sentiment_model=jb.ENCODER_MODEL_ID, sentiment_relevance='relevant',
        sentiment_content_origin='human_chatter', sentiment_attitude='positive',
        sentiment_expected_move='up', sentiment_confidence='high')
    assert jb.stored_row_carries_tone(tone_less) is False
    assert jb.stored_row_carries_tone(complete) is True


def test_a_backend_that_declares_no_tone_policy_raises():
    """A new backend forgetting the flag must fail loudly, not acquire the
    permissive default and start writing what readers see."""
    import types
    try:
        jb.writes_tone(types.SimpleNamespace(id='mystery'))
    except ValueError as exc:
        assert 'tone policy' in str(exc)
    else:
        raise AssertionError('a missing tone policy must raise')


def test_a_post_card_names_the_encoder_rather_than_saying_model():
    """Michi asked for this the moment tone went on: a reader seeing an
    arrow should know a local encoder decided it, not Claude and not an
    anonymous 'model'."""
    assert jb.backend_label(jb.ENCODER_MODEL_ID) == 'Encoder'
    assert jb.backend_label('radar-encoder-v2') == 'Encoder'


def test_anthropic_ids_still_say_claude_and_unknowns_still_say_model():
    assert jb.backend_label('claude-haiku-4-5') == 'Claude'
    assert jb.backend_label('some-future-thing') == 'model'
    assert jb.backend_label(None) == 'model'

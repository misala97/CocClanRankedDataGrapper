# personal_apps/tests/test_radar_text.py
"""Distinct authors defeats one account posting fifty times. Distinct text
ratio is what defeats fifty accounts posting the same thing, which is the
actual shape of a brigade (spec 6.7).

The scope claim is deliberately narrow: exact-hash matching catches copy-paste
and low-effort templating. It does not catch paraphrase, and test_paraphrase_
is_not_caught pins that so nobody later describes this as a bot detector.
"""
from features.radar import fingerprint, sentiment


def test_identical_text_has_an_identical_hash():
    assert fingerprint.simhash64('GME to the moon') == fingerprint.simhash64('GME to the moon')


def test_hash_is_64_bit_unsigned():
    value = fingerprint.simhash64('some ordinary post body')
    assert 0 <= value < 2 ** 64


def test_copy_paste_survives_whitespace_and_case():
    a = fingerprint.simhash64('BUY GME NOW!!!   Squeeze  is coming')
    b = fingerprint.simhash64('buy gme now!!! squeeze is coming')
    assert a == b


def test_urls_are_stripped_so_referral_spam_collapses():
    a = fingerprint.simhash64('same pitch https://example.invalid/aaa')
    b = fingerprint.simhash64('same pitch https://example.invalid/bbb')
    assert a == b


def test_paraphrase_is_not_caught():
    """Documented limit, not a defect."""
    a = fingerprint.simhash64('GME is going to squeeze hard this week')
    b = fingerprint.simhash64('this week GME will see a serious short squeeze')
    assert a != b


def test_empty_text_is_stable():
    assert fingerprint.simhash64('') == fingerprint.simhash64('   ')


def test_bullish_text_scores_positive():
    assert sentiment.lexicon_score('this is a great buy, huge upside, bullish') > 0


def test_bearish_text_scores_negative():
    assert sentiment.lexicon_score('terrible earnings, this dumps, bearish crash') < 0


def test_neutral_text_scores_zero():
    assert sentiment.lexicon_score('the ticker was mentioned in a filing') == 0.0


def test_negation_flips_the_sign():
    assert sentiment.lexicon_score('not bullish at all') < 0


def test_score_is_bounded():
    shouting = 'bullish ' * 200
    assert -1.0 <= sentiment.lexicon_score(shouting) <= 1.0

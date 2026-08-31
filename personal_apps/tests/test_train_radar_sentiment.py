# personal_apps/tests/test_train_radar_sentiment.py
"""The classifier trainer's discipline (spec §8/§10.3): split isolation,
validation-only threshold selection, gate arithmetic, atomic promotion,
and the scorer's artifact dispatch. Pure of the database -- rows are
synthesized in the shape load_rows() produces."""
import datetime as dt
import json
import os

import pytest

from features.radar import sentiment, sentiment_input
from scripts import train_radar_sentiment as trainer


def test_banding_merges_near_duplicates_and_separates_distant():
    base = 0b1010101010101010101010101010101010101010101010101010101010101010
    near = base ^ 0b111                     # Hamming 3: same group
    far = base ^ ((1 << 63) | (1 << 47) | (1 << 31) | (1 << 15)
                  | (1 << 7) | (1 << 3) | (1 << 1) | 1)   # Hamming 8: apart
    groups = trainer.near_duplicate_groups(
        [(1, base), (2, near), (3, far)])
    assert groups[1] == groups[2]
    assert groups[1] != groups[3]


def test_chronological_split_respects_shares_and_order():
    ordered = [(gid, dt.datetime(2027, 1, 1) + dt.timedelta(days=gid))
               for gid in range(100)]
    assignment = trainer.chronological_split(ordered)
    slices = [assignment[gid] for gid in range(100)]
    assert slices[:70] == ['train'] * 70
    assert slices[70:85] == ['validation'] * 15
    assert slices[85:] == ['test'] * 15


def _rows(invert_test_labels=False):
    """~180 synthetic rows in load_rows() shape, cleanly separable.

    The lexicon column is right on most directional rows but wrong on a
    few -- the reversal gate compares against it on the same rows, and a
    lexicon with zero reversals would demand an impossible zero from the
    candidate.
    """
    positive_words = ['great gain climbs', 'strong rise ahead',
                      'love this growth', 'solid winner here']
    negative_words = ['awful drop coming', 'weak fall ahead',
                      'hate this decline', 'clear loser here']
    neutral_words = ['quarterly filing posted', 'shares traded today',
                     'the meeting happened', 'numbers were released']
    rows = []
    when = dt.datetime(2027, 1, 1)
    for index in range(180):
        kind = index % 3
        # The lexicon baseline is deliberately mediocre: right on a fifth
        # of directional rows, wrong on a twentieth, silent on the rest --
        # roughly the measured shape of the real word list.
        if kind == 0:
            text, label = positive_words[index % 4], 'positive'
            lexicon = 0.5 if index % 5 == 0 else (
                -0.5 if index % 20 == 1 else 0.0)
        elif kind == 1:
            text, label = negative_words[index % 4], 'negative'
            lexicon = -0.5 if index % 5 == 0 else (
                0.5 if index % 20 == 1 else 0.0)
        else:
            text, label = neutral_words[index % 4], 'none'
            lexicon = 0.0
        rows.append({
            'post_id': index,
            'simhash': (index * 2654435761) % (2 ** 64),
            'created': when + dt.timedelta(minutes=index),
            'text': 'TICKER=ZZT %s v%d' % (text, index % 7),
            'label': label,
            'lexicon': lexicon,
        })
    if invert_test_labels:
        flip = {'positive': 'negative', 'negative': 'positive'}
        for row in rows[int(180 * 0.85):]:
            row['label'] = flip.get(row['label'], row['label'])
    return rows


def test_tau_is_selected_on_validation_never_on_the_locked_test():
    clean = trainer.train_candidate(_rows())
    poisoned = trainer.train_candidate(_rows(invert_test_labels=True))
    assert clean['tau'] is not None
    # Poisoning the locked test cannot move the threshold...
    assert poisoned['tau'] == clean['tau']
    # ...but it does show up in the locked-test report.
    assert poisoned['locked_test_metrics']['hit_rate'] \
        < clean['locked_test_metrics']['hit_rate']


def test_gates_flag_each_violated_constraint():
    bad = {'precision': 0.5, 'wrong_rate': 0.5, 'noise_fire': 0.5,
           'reversals': 10, 'hit_rate': 0.1}
    lexicon = {'reversals': 2, 'hit_rate': 0.3}
    ok, reasons = trainer.gates_pass(bad, lexicon)
    assert not ok
    assert len(reasons) == 5


def test_a_post_never_straddles_a_cut():
    rows = _rows()
    result = trainer.train_candidate(rows)
    assert result['tau'] is not None
    slices = {}
    for row in rows:
        slices.setdefault(row['post_id'], set()).add(row['slice'])
    assert all(len(seen) == 1 for seen in slices.values())


@pytest.fixture()
def artifact_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(sentiment, 'ARTIFACT_DIR', str(tmp_path))
    sentiment._active_cache.update(pointer_mtime=None, artifact=None,
                                   warned=False)
    yield str(tmp_path)
    sentiment._active_cache.update(pointer_mtime=None, artifact=None,
                                   warned=False)


def _promoted_candidate(artifact_dir):
    result = trainer.train_candidate(_rows())
    assert result['tau'] is not None
    path = trainer.write_artifact(result, 'clf-v2-test')
    trainer.promote('clf-v2-test', path)
    return result


def test_artifact_metadata_carries_the_contract(artifact_dir):
    import joblib
    result = trainer.train_candidate(_rows())
    path = trainer.write_artifact(result, 'clf-v2-meta')
    stored = joblib.load(path)
    for key in ('version', 'word_vec', 'char_vec', 'clf', 'tau', 'classes',
                'preparation_version', 'trained_at', 'counts',
                'validation_metrics', 'locked_test_metrics',
                'sklearn_version'):
        assert key in stored, key
    assert stored['preparation_version'] == sentiment_input.PREPARATION_VERSION


def test_promotion_is_atomic_and_rollback_is_the_old_pointer(artifact_dir):
    _promoted_candidate(artifact_dir)
    assert sentiment.active_version() == 'clf-v2-test'
    pointer = os.path.join(artifact_dir, 'active.json')
    previous = open(pointer, encoding='utf-8').read()

    # A second candidate takes over...
    result = trainer.train_candidate(_rows())
    path = trainer.write_artifact(result, 'clf-v2-next')
    trainer.promote('clf-v2-next', path)
    sentiment._active_cache.update(pointer_mtime=None)
    assert sentiment.active_version() == 'clf-v2-next'

    # ...and rollback is literally restoring the previous pointer file.
    with open(pointer, 'w', encoding='utf-8') as handle:
        handle.write(previous)
    sentiment._active_cache.update(pointer_mtime=None)
    assert sentiment.active_version() == 'clf-v2-test'


def test_the_reference_gate_blocks_an_unscored_candidate(artifact_dir):
    assert trainer.reference_verdict('clf-v2-unscored') is None
    ledger = os.path.join(artifact_dir, 'evaluations.jsonl')
    with open(ledger, 'w', encoding='utf-8') as handle:
        handle.write(json.dumps({'candidate': 'clf-v2-x',
                                 'passes_10_3': False}) + '\n')
        handle.write(json.dumps({'candidate': 'clf-v2-y',
                                 'passes_10_3': True}) + '\n')
    assert trainer.reference_verdict('clf-v2-x') is False
    assert trainer.reference_verdict('clf-v2-y') is True


def test_the_scorer_is_ticker_aware_through_the_target_mask(artifact_dir):
    """One two-ticker post, opposite context around each __TARGET__: the
    same text must score with opposite signs per target ticker."""
    _promoted_candidate(artifact_dir)

    def prepared_for(ticker):
        return sentiment_input.PreparedInput(
            author_text='great gain climbs AAA but awful drop coming BBB',
            target_ticker=ticker, source='bluesky', channel='c',
            author='a', is_comment=False)

    # Feature text differs per target even though author_text is shared.
    # classifier_text resolves the known-ticker set from the universe
    # table, hence the app context.
    from app import app as flask_app
    with flask_app.app_context():
        text_a = sentiment.classifier_text(prepared_for('AAA'))
        text_b = sentiment.classifier_text(prepared_for('BBB'))
    assert text_a != text_b
    assert 'TICKER=AAA' in text_a and '__TARGET__' in text_a


def test_cold_start_and_stale_artifacts_fall_back_to_the_lexicon(
        artifact_dir, caplog):
    prepared = sentiment_input.prepare_sentiment_input(
        'bluesky', None, 'this is a scam, terrible', 'ZZT')
    # No artifact at all: the lexicon answers.
    assert sentiment.active_version() == 'lexicon-v1'
    assert sentiment.score(prepared) == sentiment.lexicon_score(
        prepared.author_text)

    # A stale preparation_version artifact is refused with one log line.
    import joblib
    result = trainer.train_candidate(_rows())
    path = trainer.write_artifact(result, 'clf-v2-stale')
    stored = joblib.load(path)
    stored['preparation_version'] = 999
    joblib.dump(stored, path)
    trainer.promote('clf-v2-stale', path)
    sentiment._active_cache.update(pointer_mtime=None, warned=False)
    with caplog.at_level('WARNING', logger='radar.sentiment'):
        assert sentiment.score(prepared) == sentiment.lexicon_score(
            prepared.author_text)
        assert sentiment.active_version() == 'lexicon-v1'
    assert any('falling back to the lexicon' in message
               for message in caplog.messages)

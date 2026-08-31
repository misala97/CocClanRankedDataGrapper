# personal_apps/scripts/score_sentiment_reference.py
"""Score a candidate against the frozen reference set. Zero API calls.

Reproduces the spec §10.2/§10.3 acceptance tables purely from the frozen
key plus stored predictions, so acceptance reruns are free and
deterministic. Refuses to run when any reference file's sha256 disagrees
with the manifest (the freeze is enforced, not remembered), and refuses
to re-evaluate an unchanged candidate identity against the locked set --
an identity already in evaluations.jsonl gets its stored result
reprinted, never a fresh roll.

Candidates:

    python -m scripts.score_sentiment_reference --pipeline
        # the live routed result: materialized judgments read from the DB
    python -m scripts.score_sentiment_reference --classifier artifacts/radar_sentiment/clf-v2-X.joblib
    python -m scripts.score_sentiment_reference --lexicon
"""
import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, '.')  # noqa: E402

from features.radar import llm_sentiment, sentiment, sentiment_input  # noqa: E402
from scripts.build_sentiment_reference import (  # noqa: E402
    LABEL_FIELDS, REFERENCE_DIR, _path, sha256_of)
from scripts.train_radar_sentiment import GATES, evaluate, gates_pass  # noqa: E402

# Spec §10.2 gates for the routed LLM result.
LLM_GATES = {
    'attitude_exact_min': 0.80,
    'directional_agreement_min': 0.84,
    'reversal_rate_max': 0.02,
    'relevance_f1_min': 0.90,
    'origin_f1_min': 0.90,
    'removal_precision_min': 0.95,
    'per_source_attitude_min': 0.75,
}


def verify_manifest():
    manifest = json.load(open(_path('reference-manifest.json'),
                              encoding='utf-8'))
    for name, expected in manifest['files'].items():
        actual = sha256_of(_path(name))
        if actual != expected:
            raise SystemExit('FROZEN FILE CHANGED: %s (sha256 %s != %s) -- '
                             'the reference set is burned, rebuild and '
                             're-freeze' % (name, actual, expected))
    return manifest


def macro_f1(pairs, classes):
    """Macro F1 over (predicted, truth) label pairs."""
    scores = []
    for cls in classes:
        tp = sum(1 for p, t in pairs if p == cls and t == cls)
        fp = sum(1 for p, t in pairs if p == cls and t != cls)
        fn = sum(1 for p, t in pairs if p != cls and t == cls)
        precision = tp / ((tp + fp) or 1)
        recall = tp / ((tp + fn) or 1)
        scores.append(2 * precision * recall / ((precision + recall) or 1))
    return sum(scores) / len(scores)


def removal_precision(pairs):
    """Precision of the REMOVAL decision: predicted irrelevant/broadcast."""
    def removed(labels):
        return (labels['relevance'] == 'irrelevant'
                or labels['content_origin'] == 'broadcast_or_automated')
    predicted_removed = [(p, t) for p, t in pairs if removed(p)]
    if not predicted_removed:
        return None
    correct = sum(1 for p, t in predicted_removed if removed(t))
    return correct / len(predicted_removed)


def attitude_tables(rows):
    """rows: [{'truth': {...}, 'predicted': {...} or None, 'source_root',
    'tags'}] -> the §10.2 numbers."""
    judged = [row for row in rows if row['predicted'] is not None]
    exact = sum(1 for row in judged
                if row['predicted']['attitude'] == row['truth']['attitude'])
    directional = [row for row in judged
                   if row['truth']['attitude'] in ('positive', 'negative')]

    def collapse(labels):
        return labels if labels in ('positive', 'negative') else 'other'
    directional_hits = sum(
        1 for row in judged
        if collapse(row['predicted']['attitude'])
        == collapse(row['truth']['attitude']))
    reversals = sum(
        1 for row in directional
        if row['predicted']['attitude'] in ('positive', 'negative')
        and row['predicted']['attitude'] != row['truth']['attitude'])

    per_source = {}
    for root in sorted({row['source_root'] for row in judged}):
        rows_of = [row for row in judged if row['source_root'] == root]
        per_source[root] = sum(
            1 for row in rows_of
            if row['predicted']['attitude'] == row['truth']['attitude']) \
            / (len(rows_of) or 1)

    per_tag = {}
    for tag in sorted({tag for row in judged for tag in row['tags']}):
        rows_of = [row for row in judged if tag in row['tags']]
        per_tag[tag] = sum(
            1 for row in rows_of
            if row['predicted']['attitude'] == row['truth']['attitude']) \
            / (len(rows_of) or 1)

    label_pairs = [(row['predicted'], row['truth']) for row in judged]
    return {
        'judged': len(judged), 'total': len(rows),
        'attitude_exact': exact / (len(judged) or 1),
        'directional_agreement': directional_hits / (len(judged) or 1),
        'reversal_rate': reversals / (len(directional) or 1),
        'relevance_f1': macro_f1(
            [(p['relevance'], t['relevance']) for p, t in label_pairs],
            llm_sentiment.RELEVANCE),
        'origin_f1': macro_f1(
            [(p['content_origin'], t['content_origin'])
             for p, t in label_pairs], llm_sentiment.CONTENT_ORIGIN),
        'removal_precision': removal_precision(label_pairs),
        'per_source_attitude': per_source,
        'per_tag_attitude': per_tag,
    }


def llm_gates_pass(tables):
    reasons = []
    if tables['attitude_exact'] < LLM_GATES['attitude_exact_min']:
        reasons.append('attitude exact %.3f < %.2f'
                       % (tables['attitude_exact'],
                          LLM_GATES['attitude_exact_min']))
    if tables['directional_agreement'] \
            < LLM_GATES['directional_agreement_min']:
        reasons.append('directional %.3f < %.2f'
                       % (tables['directional_agreement'],
                          LLM_GATES['directional_agreement_min']))
    if tables['reversal_rate'] > LLM_GATES['reversal_rate_max']:
        reasons.append('reversals %.3f > %.2f'
                       % (tables['reversal_rate'],
                          LLM_GATES['reversal_rate_max']))
    if tables['relevance_f1'] < LLM_GATES['relevance_f1_min']:
        reasons.append('relevance F1 %.3f < %.2f'
                       % (tables['relevance_f1'],
                          LLM_GATES['relevance_f1_min']))
    if tables['origin_f1'] < LLM_GATES['origin_f1_min']:
        reasons.append('origin F1 %.3f < %.2f'
                       % (tables['origin_f1'], LLM_GATES['origin_f1_min']))
    if (tables['removal_precision'] is not None
            and tables['removal_precision']
            < LLM_GATES['removal_precision_min']):
        reasons.append('removal precision %.3f < %.2f'
                       % (tables['removal_precision'],
                          LLM_GATES['removal_precision_min']))
    for root, share in tables['per_source_attitude'].items():
        if share < LLM_GATES['per_source_attitude_min']:
            reasons.append('%s attitude %.3f < %.2f'
                           % (root, share,
                              LLM_GATES['per_source_attitude_min']))
    return (not reasons), reasons


def ledger_lookup(candidate):
    path = os.path.join(sentiment.ARTIFACT_DIR, 'evaluations.jsonl')
    if not os.path.exists(path):
        return None
    stored = None
    for row in map(json.loads, open(path, encoding='utf-8')):
        if row.get('candidate') == candidate:
            stored = row
    return stored


def ledger_append(entry):
    os.makedirs(sentiment.ARTIFACT_DIR, exist_ok=True)
    path = os.path.join(sentiment.ARTIFACT_DIR, 'evaluations.jsonl')
    with open(path, 'a', encoding='utf-8') as out:
        out.write(json.dumps(entry) + '\n')


def load_reference():
    truth = {row['n']: row for row in
             json.load(open(_path('reference-key.json'), encoding='utf-8'))}
    blind = {row['n']: row for row in
             map(json.loads,
                 open(_path('reference-blind.jsonl'), encoding='utf-8'))}
    return truth, blind


def prediction_hash(predictions):
    canon = json.dumps(predictions, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canon.encode('utf-8')).hexdigest()


def classifier_predictions(artifact_path, blind):
    import joblib
    artifact = joblib.load(artifact_path)
    out = {}
    for n, row in blind.items():
        prepared = sentiment_input.PreparedInput(
            author_text=row['author_text'], target_ticker=row['ticker'],
            source=row['source'], channel=row['channel'] or '',
            author=row['author'], is_comment=row['is_comment'])
        text = 'TICKER=%s %s' % (
            prepared.target_ticker,
            sentiment_input.mask_tickers(prepared.author_text,
                                         prepared.target_ticker, set()))
        from scipy.sparse import hstack
        features = hstack([artifact['word_vec'].transform([text]),
                           artifact['char_vec'].transform([text])])
        proba = dict(zip(artifact['clf'].classes_,
                         artifact['clf'].predict_proba(features)[0]))
        p_pos = float(proba.get('positive', 0.0))
        p_neg = float(proba.get('negative', 0.0))
        top = max(p_pos, p_neg)
        if top < artifact['tau'] or top <= (1.0 - p_pos - p_neg):
            out[n] = 0.0
        else:
            out[n] = p_pos - p_neg
    return artifact['version'], out


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--pipeline', action='store_true')
    group.add_argument('--classifier')
    group.add_argument('--lexicon', action='store_true')
    args = parser.parse_args()

    manifest = verify_manifest()
    truth, blind = load_reference()

    if args.pipeline:
        from app import app
        from extensions import db
        from models import RadarMention
        skeleton = {row['n']: row for row in
                    json.load(open(_path('reference-key-skeleton.json'),
                                   encoding='utf-8'))}
        predictions = {}
        with app.app_context():
            for n, meta in skeleton.items():
                mention = db.session.get(RadarMention, meta['mention_id'])
                if mention is None or mention.sentiment_judged_at is None:
                    predictions[n] = None
                    continue
                predictions[n] = {
                    'relevance': mention.sentiment_relevance,
                    'content_origin': mention.sentiment_content_origin,
                    'attitude': mention.sentiment_attitude,
                    'expected_move': mention.sentiment_expected_move,
                    'confidence': mention.sentiment_confidence,
                }
        candidate = 'pipeline@%s' % llm_sentiment.PROMPT_VERSION
        rows = [{'truth': {field: truth[n][field]
                           for field in LABEL_FIELDS},
                 'predicted': predictions.get(n),
                 'source_root': blind[n]['source_root'],
                 'tags': blind[n]['tags']} for n in truth]
        identity = '%s#%s' % (candidate, prediction_hash(predictions))
        stored = ledger_lookup(identity)
        if stored is not None:
            print('already evaluated (stored result follows) -- an '
                  'unchanged candidate is never re-rolled')
            print(json.dumps(stored, indent=2))
            return 0
        tables = attitude_tables(rows)
        ok, reasons = llm_gates_pass(tables)
        print(json.dumps(tables, indent=2))
        print('§10.2: %s' % ('PASS' if ok else '; '.join(reasons)))
        ledger_append({'candidate': identity, 'kind': 'pipeline',
                       'tables': tables, 'passes_10_2': ok})
        return 0

    # Local scorers judge direction only -> the §10.3 shape.
    if args.classifier:
        version, scores = classifier_predictions(args.classifier, blind)
        candidate = version
    else:
        scores = {n: sentiment.lexicon_score(blind[n]['author_text'])
                  for n in blind}
        candidate = 'lexicon-v1'
    identity = '%s#%s' % (candidate, prediction_hash(scores))
    stored = ledger_lookup(identity)
    if stored is not None:
        print('already evaluated (stored result follows)')
        print(json.dumps(stored, indent=2))
        return 0
    pairs = [(scores[n], truth[n]['attitude']) for n in truth
             if truth[n]['relevance'] == 'relevant'
             and truth[n]['content_origin'] == 'human_chatter']
    lexicon_pairs = [(sentiment.lexicon_score(blind[n]['author_text']),
                      truth[n]['attitude']) for n in truth
                     if truth[n]['relevance'] == 'relevant'
                     and truth[n]['content_origin'] == 'human_chatter']
    metrics = evaluate(pairs)
    lexicon_metrics = evaluate(lexicon_pairs)
    ok, reasons = gates_pass(metrics, lexicon_metrics)
    print(json.dumps({'metrics': metrics,
                      'lexicon_baseline': lexicon_metrics}, indent=2))
    print('§10.3: %s' % ('PASS' if ok else '; '.join(reasons)))
    ledger_append({'candidate': candidate, 'kind': 'local',
                   'identity': identity, 'metrics': metrics,
                   'passes_10_3': ok})
    return 0


if __name__ == '__main__':
    sys.exit(main())

# personal_apps/scripts/score_sentiment_reference.py
"""Score a candidate against the frozen reference set. Zero API calls.

Reproduces the spec §10.2/§10.3 acceptance tables purely from the frozen
key plus stored predictions. Refuses to run when any reference file's
sha256 disagrees with the manifest (the freeze is enforced, not
remembered), and refuses to re-evaluate an unchanged candidate identity
against the locked set -- an identity already in evaluations.jsonl gets
its stored result reprinted, never a fresh roll.

Candidates:

    python -m scripts.score_sentiment_reference --pipeline --stage routed
        # the final routed result: materialized judgments from the DB
    python -m scripts.score_sentiment_reference --pipeline --stage primary
        # Haiku-only: the latest stage='primary' history row per mention
    python -m scripts.score_sentiment_reference --sonnet-gate
        # compares the two ledgered pipeline runs: routed must beat
        # primary by >= 2 points exact attitude for Sonnet to earn its
        # place (spec §5.3)
    python -m scripts.score_sentiment_reference --classifier artifacts/radar_sentiment/clf-v2-X.joblib
    python -m scripts.score_sentiment_reference --lexicon

Unjudged reference items count as MISSES in every §10.2 denominator --
coverage is part of the grade, not a footnote -- and both balanced
(equal weight per attitude class) and production-weighted tables are
reported; the gates read the production-weighted one. Hard-slice
categories are compared against the previous ledgered run of the same
kind: a drop of more than two points on any category fails unless an
explicit ruling is recorded with --accept-hard-slice-regression.
"""
import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, '.')  # noqa: E402

from features.radar import llm_sentiment, sentiment  # noqa: E402
from scripts.build_sentiment_reference import (  # noqa: E402
    LABEL_FIELDS, _path, sha256_of)
from scripts.train_radar_sentiment import evaluate, gates_pass  # noqa: E402

# Spec §10.2 gates for the routed LLM result, on production-weighted
# figures with unjudged-as-miss denominators.
LLM_GATES = {
    'attitude_exact_min': 0.80,
    'directional_agreement_min': 0.84,
    'reversal_rate_max': 0.02,
    'relevance_f1_min': 0.90,
    'origin_f1_min': 0.90,
    'removal_precision_min': 0.95,
    'per_source_attitude_min': 0.75,
}
HARD_SLICE_REGRESSION_LIMIT = 0.02
SONNET_GATE_POINTS = 0.02


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
    """Macro F1 over (predicted, truth) label pairs; a None prediction is
    a wrong prediction for every class."""
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
        return (labels is not None
                and (labels['relevance'] == 'irrelevant'
                     or labels['content_origin'] == 'broadcast_or_automated'))
    predicted_removed = [(p, t) for p, t in pairs if removed(p)]
    if not predicted_removed:
        return None
    correct = sum(1 for p, t in predicted_removed if removed(t))
    return correct / len(predicted_removed)


def schema_valid(predicted):
    if predicted is None:
        return True                     # absent, not invalid
    checks = (('relevance', llm_sentiment.RELEVANCE),
              ('content_origin', llm_sentiment.CONTENT_ORIGIN),
              ('attitude', llm_sentiment.ATTITUDE),
              ('expected_move', llm_sentiment.EXPECTED_MOVE),
              ('confidence', llm_sentiment.CONFIDENCE))
    return all(predicted.get(field) in allowed for field, allowed in checks)


def attitude_tables(rows):
    """rows: [{'truth', 'predicted' (dict or None), 'source_root', 'tags'}].

    Every rate uses the TOTAL denominator: an unjudged item is a miss
    (Codex review, blocker 4). `coverage` and `schema_invalid` are
    reported beside the rates.
    """
    total = len(rows) or 1
    judged = [row for row in rows if row['predicted'] is not None]
    invalid = sum(1 for row in judged if not schema_valid(row['predicted']))

    def att(row):
        return row['predicted']['attitude'] if row['predicted'] else None

    exact = sum(1 for row in rows
                if att(row) == row['truth']['attitude'])
    directional_truth = [row for row in rows
                         if row['truth']['attitude']
                         in ('positive', 'negative')]

    def collapse(label):
        return label if label in ('positive', 'negative') else 'other'
    directional_hits = sum(1 for row in rows
                           if att(row) is not None
                           and collapse(att(row))
                           == collapse(row['truth']['attitude']))
    reversals = sum(1 for row in directional_truth
                    if att(row) in ('positive', 'negative')
                    and att(row) != row['truth']['attitude'])

    # Balanced: equal weight per truth attitude class (spec §10.2 wants
    # both views; a class-skewed sample must not hide a broken class).
    balanced_parts = []
    for cls in llm_sentiment.ATTITUDE:
        rows_of = [row for row in rows if row['truth']['attitude'] == cls]
        if rows_of:
            balanced_parts.append(
                sum(1 for row in rows_of if att(row) == cls)
                / len(rows_of))
    balanced_exact = (sum(balanced_parts) / len(balanced_parts)
                      if balanced_parts else 0.0)

    per_source = {}
    for root in sorted({row['source_root'] for row in rows}):
        rows_of = [row for row in rows if row['source_root'] == root]
        per_source[root] = sum(
            1 for row in rows_of
            if att(row) == row['truth']['attitude']) / (len(rows_of) or 1)

    per_tag = {}
    for tag in sorted({tag for row in rows for tag in row['tags']}):
        rows_of = [row for row in rows if tag in row['tags']]
        per_tag[tag] = sum(
            1 for row in rows_of
            if att(row) == row['truth']['attitude']) / (len(rows_of) or 1)

    label_pairs = [(row['predicted'], row['truth']) for row in rows]
    return {
        'total': len(rows), 'judged': len(judged),
        'coverage': len(judged) / total,
        'schema_invalid': invalid,
        'attitude_exact': exact / total,
        'attitude_exact_balanced': balanced_exact,
        'directional_agreement': directional_hits / total,
        'reversal_rate': reversals / (len(directional_truth) or 1),
        'relevance_f1': macro_f1(
            [((p or {}).get('relevance'), t['relevance'])
             for p, t in label_pairs], llm_sentiment.RELEVANCE),
        'origin_f1': macro_f1(
            [((p or {}).get('content_origin'), t['content_origin'])
             for p, t in label_pairs], llm_sentiment.CONTENT_ORIGIN),
        'removal_precision': removal_precision(label_pairs),
        'per_source_attitude': per_source,
        'per_tag_attitude': per_tag,
    }


def llm_gates_pass(tables):
    reasons = []
    if tables['schema_invalid']:
        reasons.append('%d schema-invalid stored answers'
                       % tables['schema_invalid'])
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


def hard_slice_regressions(tables, previous_tables):
    """Categories that dropped more than the allowed two points against
    the previous ledgered run of the same kind (spec §10.2)."""
    if not previous_tables:
        return []
    drops = []
    before = previous_tables.get('per_tag_attitude', {})
    for tag, share in tables.get('per_tag_attitude', {}).items():
        if tag in before and share < before[tag] - HARD_SLICE_REGRESSION_LIMIT:
            drops.append('%s %.3f -> %.3f' % (tag, before[tag], share))
    return drops


def _ledger_path():
    return os.path.join(sentiment.ARTIFACT_DIR, 'evaluations.jsonl')


def ledger_rows():
    path = _ledger_path()
    if not os.path.exists(path):
        return []
    return [json.loads(line) for line in open(path, encoding='utf-8')]


def ledger_lookup_identity(identity):
    stored = None
    for row in ledger_rows():
        if row.get('identity') == identity:
            stored = row
    return stored


def previous_of_kind(kind, stage=None):
    previous = None
    for row in ledger_rows():
        if row.get('kind') == kind and (stage is None
                                        or row.get('stage') == stage):
            previous = row
    return previous


def ledger_append(entry):
    os.makedirs(sentiment.ARTIFACT_DIR, exist_ok=True)
    with open(_ledger_path(), 'a', encoding='utf-8') as out:
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
    """Directional floats from an artifact, over the FROZEN masked_text --
    the same masking as training, not an empty ticker set (blocker 5)."""
    import joblib
    from scipy.sparse import hstack
    artifact = joblib.load(artifact_path)
    out = {}
    for n, row in blind.items():
        text = row['masked_text']
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


def pipeline_predictions(stage):
    """Stored five-field predictions per reference item, from the DB.

    stage 'routed' reads the materialized final fields (Sonnet overrides
    included); 'primary' reads the latest stage='primary' history row, so
    the two can be compared for the §5.3 Sonnet gate.
    """
    from app import app
    from extensions import db
    from models import RadarMention, RadarSentimentJudgment
    skeleton = {row['n']: row for row in
                json.load(open(_path('reference-key-skeleton.json'),
                               encoding='utf-8'))}
    predictions = {}
    with app.app_context():
        for n, meta in skeleton.items():
            if stage == 'routed':
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
            else:
                row = (db.session.query(RadarSentimentJudgment)
                       .filter_by(mention_id=meta['mention_id'],
                                  stage='primary')
                       .order_by(RadarSentimentJudgment.id.desc())
                       .first())
                predictions[n] = None if row is None else {
                    'relevance': row.relevance,
                    'content_origin': row.content_origin,
                    'attitude': row.attitude,
                    'expected_move': row.expected_move,
                    'confidence': row.confidence,
                }
    return predictions


def cmd_sonnet_gate():
    """Spec §5.3: the review tier ships only on >= 2 points of exact
    attitude over the primary alone, read from the two ledgered runs."""
    routed = previous_of_kind('pipeline', stage='routed')
    primary = previous_of_kind('pipeline', stage='primary')
    if routed is None or primary is None:
        print('score both --pipeline --stage routed and --stage primary '
              'first')
        return 1
    gain = (routed['tables']['attitude_exact']
            - primary['tables']['attitude_exact'])
    verdict = gain >= SONNET_GATE_POINTS
    print('routed %.3f vs primary %.3f: %+.3f -> Sonnet %s'
          % (routed['tables']['attitude_exact'],
             primary['tables']['attitude_exact'], gain,
             'EARNS ITS PLACE' if verdict else 'stays disabled'))
    return 0 if verdict else 1


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--pipeline', action='store_true')
    group.add_argument('--classifier')
    group.add_argument('--lexicon', action='store_true')
    group.add_argument('--sonnet-gate', action='store_true')
    parser.add_argument('--stage', choices=('routed', 'primary'),
                        default='routed')
    parser.add_argument('--accept-hard-slice-regression', default=None,
                        help='recorded ruling accepting a >2pt hard-slice '
                             'drop against the previous run')
    args = parser.parse_args()

    if args.sonnet_gate:
        return cmd_sonnet_gate()

    verify_manifest()
    truth, blind = load_reference()

    if args.pipeline:
        predictions = pipeline_predictions(args.stage)
        candidate = 'pipeline-%s@%s' % (args.stage,
                                        llm_sentiment.PROMPT_VERSION)
        identity = '%s#%s' % (candidate, prediction_hash(predictions))
        stored = ledger_lookup_identity(identity)
        if stored is not None:
            print('already evaluated (stored result follows) -- an '
                  'unchanged candidate is never re-rolled')
            print(json.dumps(stored, indent=2))
            return 0
        rows = [{'truth': {field: truth[n][field]
                           for field in LABEL_FIELDS},
                 'predicted': predictions.get(n),
                 'source_root': blind[n]['source_root'],
                 'tags': blind[n]['tags']} for n in truth]
        tables = attitude_tables(rows)
        ok, reasons = llm_gates_pass(tables)
        drops = hard_slice_regressions(
            tables, (previous_of_kind('pipeline', stage=args.stage)
                     or {}).get('tables'))
        if drops:
            if args.accept_hard_slice_regression:
                print('hard-slice regressions ACCEPTED with ruling: %s (%s)'
                      % (args.accept_hard_slice_regression,
                         '; '.join(drops)))
            else:
                ok = False
                reasons.append('hard-slice regression: %s'
                               % '; '.join(drops))
        print(json.dumps(tables, indent=2))
        print('§10.2: %s' % ('PASS' if ok else '; '.join(reasons)))
        ledger_append({'candidate': candidate, 'identity': identity,
                       'kind': 'pipeline', 'stage': args.stage,
                       'tables': tables, 'passes_10_2': ok,
                       'hard_slice_ruling':
                           args.accept_hard_slice_regression})
        return 0

    # Local scorers judge direction only -> the §10.3 shape, evaluated on
    # the relevant human-chatter slice of the reference.
    if args.classifier:
        version, scores = classifier_predictions(args.classifier, blind)
        candidate = version
        from scripts.train_radar_sentiment import artifact_sha256
        bound_sha = artifact_sha256(args.classifier)
    else:
        bound_sha = None
        scores = {n: sentiment.lexicon_score(blind[n]['author_text'])
                  for n in blind}
        candidate = 'lexicon-v1'
    identity = '%s#%s' % (candidate, prediction_hash(scores))
    stored = ledger_lookup_identity(identity)
    if stored is not None:
        print('already evaluated (stored result follows)')
        print(json.dumps(stored, indent=2))
        return 0
    eligible = [n for n in truth
                if truth[n]['relevance'] == 'relevant'
                and truth[n]['content_origin'] == 'human_chatter']
    pairs = [(scores[n], truth[n]['attitude']) for n in eligible]
    lexicon_pairs = [(sentiment.lexicon_score(blind[n]['author_text']),
                      truth[n]['attitude']) for n in eligible]
    metrics = evaluate(pairs)
    lexicon_metrics = evaluate(lexicon_pairs)
    ok, reasons = gates_pass(metrics, lexicon_metrics)
    print(json.dumps({'metrics': metrics,
                      'lexicon_baseline': lexicon_metrics}, indent=2))
    print('§10.3: %s' % ('PASS' if ok else '; '.join(reasons)))
    ledger_append({'candidate': candidate, 'identity': identity,
                   'artifact_sha256': bound_sha,
                   'kind': 'local', 'metrics': metrics, 'passes_10_3': ok})
    return 0


if __name__ == '__main__':
    sys.exit(main())

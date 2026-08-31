# personal_apps/scripts/train_radar_sentiment.py
"""Train, gate, and (on --promote) atomically promote the local classifier.

Training data is finalized v2 judgments ONLY (spec §8): relevant,
human-chatter, medium-or-high-confidence mentions with a materialized
attitude. Old four-way Haiku labels are bootstrap material for
experiments, never production truth, and never enter this script.

The discipline that makes the numbers mean something:

- groups: one post never crosses a data partition, and near-duplicate
  posts (simhash Hamming distance <= 3, found via 4x16-bit banding) are
  unioned into one group first, so a repost cannot leak across cuts;
- split: groups ordered chronologically, cut 70/15/15 into
  train / validation / locked test;
- vectorizers and the classifier fit on train only;
- tau is selected on validation only, under the spec §10.3 constraints,
  against the cleaned-input lexicon as the baseline on the same rows;
- the locked test slice is scored ONCE per candidate and reported;
- --promote succeeds only when ALL of: every §10.3 constraint passed on
  validation, the locked-test report violates none of them, and the
  frozen adjudicated reference set (score_sentiment_reference.py) has
  passed this candidate. Teacher agreement alone never promotes.

Run from personal_apps/:

    python -m scripts.train_radar_sentiment              # train + report
    python -m scripts.train_radar_sentiment --promote    # gate + promote
"""
import argparse
import collections
import datetime as dt
import json
import os
import sys

sys.path.insert(0, '.')  # noqa: E402

from app import app  # noqa: E402
from extensions import db  # noqa: E402
from features.radar import llm_sentiment, sentiment, sentiment_input  # noqa: E402
from models import RadarMention, RadarPost  # noqa: E402

TRAIN_SHARE, VALIDATION_SHARE = 0.70, 0.15
TAU_GRID = [round(0.35 + 0.05 * step, 2) for step in range(10)]  # 0.35..0.80
HAMMING_LIMIT = 3

# Spec §10.3, verbatim thresholds.
GATES = {
    'directional_precision_min': 0.85,
    'wrong_direction_max': 0.06,
    'noise_fire_max': 0.15,
}


def hamming(a, b):
    return bin(a ^ b).count('1')


def near_duplicate_groups(post_hashes):
    """{post_id: group_id} unioning posts within Hamming <= 3.

    Banding: 4 x 16-bit slices of the simhash nominate candidate pairs
    (any near-duplicate within 3 bit flips shares at least one intact
    band); the Hamming check confirms. Union-find keeps it near-linear.
    """
    parent = {post_id: post_id for post_id, _ in post_hashes}

    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(a, b):
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[root_b] = root_a

    bands = collections.defaultdict(list)
    for post_id, simhash in post_hashes:
        for band in range(4):
            key = (band, (simhash >> (band * 16)) & 0xFFFF)
            bands[key].append((post_id, simhash))
    for members in bands.values():
        # EVERY nominated pair, not members-vs-first-anchor: an unrelated
        # anchor sharing the band obscured genuine near-duplicates behind
        # it (Codex review, blocker 6). Buckets are tiny in practice; a
        # pathological bucket is capped rather than allowed to go
        # quadratic on the whole corpus.
        if len(members) > 200:
            members = members[:200]
        for left in range(len(members)):
            left_id, left_hash = members[left]
            for right in range(left + 1, len(members)):
                right_id, right_hash = members[right]
                if hamming(left_hash, right_hash) <= HAMMING_LIMIT:
                    union(left_id, right_id)
    return {post_id: find(post_id) for post_id, _ in post_hashes}


def chronological_split(ordered_groups):
    """[(group_id, first_seen)] sorted -> {group_id: 'train'|'validation'|'test'}."""
    total = len(ordered_groups)
    train_cut = int(total * TRAIN_SHARE)
    validation_cut = int(total * (TRAIN_SHARE + VALIDATION_SHARE))
    assignment = {}
    for index, (group_id, _when) in enumerate(ordered_groups):
        if index < train_cut:
            assignment[group_id] = 'train'
        elif index < validation_cut:
            assignment[group_id] = 'validation'
        else:
            assignment[group_id] = 'test'
    return assignment


def evaluate(pairs):
    """Metrics over (score, label) pairs; labels are attitude classes.

    Directional refs = positive/negative labels; noise refs = mixed/none.
    A 'reversal' and a wrong-direction call are the same event here: the
    scorer fired the opposite direction on a directional reference.
    """
    directional = [(score, label) for score, label in pairs
                   if label in ('positive', 'negative')]
    noise = [(score, label) for score, label in pairs
             if label in ('mixed', 'none')]
    hit = sum(1 for score, label in directional
              if score != 0.0 and (score > 0) == (label == 'positive'))
    wrong = sum(1 for score, label in directional
                if score != 0.0 and (score > 0) != (label == 'positive'))
    fired_noise = sum(1 for score, _label in noise if score != 0.0)
    d = len(directional) or 1
    return {
        'directional': len(directional),
        'noise': len(noise),
        'hit_rate': hit / d,
        'wrong_rate': wrong / d,
        'precision': hit / ((hit + wrong) or 1),
        'noise_fire': fired_noise / (len(noise) or 1),
        'reversals': wrong,
    }


def gates_pass(metrics, lexicon_metrics):
    """(ok, reasons) against spec §10.3, lexicon compared on the same rows."""
    reasons = []
    if metrics['precision'] < GATES['directional_precision_min']:
        reasons.append('precision %.3f < %.2f'
                       % (metrics['precision'],
                          GATES['directional_precision_min']))
    if metrics['wrong_rate'] > GATES['wrong_direction_max']:
        reasons.append('wrong-direction %.3f > %.2f'
                       % (metrics['wrong_rate'],
                          GATES['wrong_direction_max']))
    if metrics['noise_fire'] > GATES['noise_fire_max']:
        reasons.append('noise-fire %.3f > %.2f'
                       % (metrics['noise_fire'], GATES['noise_fire_max']))
    if metrics['reversals'] > lexicon_metrics['reversals']:
        reasons.append('reversals %d worse than the lexicon %d'
                       % (metrics['reversals'], lexicon_metrics['reversals']))
    if metrics['hit_rate'] <= lexicon_metrics['hit_rate']:
        reasons.append('hit %.3f not above the lexicon %.3f'
                       % (metrics['hit_rate'], lexicon_metrics['hit_rate']))
    return (not reasons), reasons


# Committed to the repo, small and public: the posts burned by the design
# process (the 160-item audit set, prompt-development samples). Training
# and reference sampling both exclude anything within HAMMING_LIMIT of
# these, so the burn is enforced by code rather than remembered by people.
BURNED_MANIFEST = os.path.join(os.path.dirname(__file__),
                               'burned_sentiment_posts.json')


def exclusion_hashes():
    """Simhashes no training run may learn from: the committed burned set
    plus the frozen reference sample, when one exists (Codex blocker 3)."""
    hashes = []
    if os.path.exists(BURNED_MANIFEST):
        data = json.load(open(BURNED_MANIFEST, encoding='utf-8'))
        hashes.extend(int(h) for h in data.get('simhashes', []))
    skeleton = os.path.join(sentiment.ARTIFACT_DIR, '..', 'reference',
                            'reference-key-skeleton.json')
    if os.path.exists(skeleton):
        for row in json.load(open(skeleton, encoding='utf-8')):
            hashes.append(int(row['simhash']))
    return hashes


def apply_exclusions(rows, hashes):
    """Drop rows near-duplicate to any excluded simhash. Returns (kept, n)."""
    if not hashes:
        return rows, 0
    kept = [row for row in rows
            if not any(hamming(row['simhash'], burnt) <= HAMMING_LIMIT
                       for burnt in hashes)]
    return kept, len(rows) - len(kept)


def load_rows():
    """Finalized v2 training rows: (post_id, simhash, created, text, label, local)."""
    rows = (db.session.query(RadarMention, RadarPost)
            .join(RadarPost, RadarPost.id == RadarMention.post_id)
            .filter(RadarMention.sentiment_relevance == 'relevant',
                    RadarMention.sentiment_content_origin == 'human_chatter',
                    RadarMention.sentiment_confidence.in_(('medium', 'high')),
                    RadarMention.sentiment_attitude.isnot(None)).all())
    out = []
    for mention, post in rows:
        prepared = sentiment_input.prepare_sentiment_input(
            post.source, post.title, post.body, mention.ticker,
            author=post.author, channel=post.channel)
        out.append({
            'post_id': post.id,
            'simhash': int(post.simhash or 0),
            'created': post.created_utc,
            'text': sentiment.classifier_text(prepared),
            'label': mention.sentiment_attitude,
            'lexicon': sentiment.lexicon_score(prepared.author_text),
        })
    return out


def drop_contradictions(rows):
    """Training rule 6: identical prepared inputs with ANY unresolved label
    disagreement teach noise -- not only positive-vs-negative clashes
    (Codex review, blocker 6)."""
    by_text = collections.defaultdict(set)
    for row in rows:
        by_text[row['text']].add(row['label'])
    contradictory = {text for text, labels in by_text.items()
                     if len(labels) > 1}
    kept = [row for row in rows if row['text'] not in contradictory]
    return kept, len(rows) - len(kept)


def scores_for(clf, word_vec, char_vec, tau, texts):
    from scipy.sparse import hstack
    if not texts:
        return []
    features = hstack([word_vec.transform(texts), char_vec.transform(texts)])
    probas = clf.predict_proba(features)
    classes = list(clf.classes_)
    i_pos = classes.index('positive') if 'positive' in classes else None
    i_neg = classes.index('negative') if 'negative' in classes else None
    out = []
    for row in probas:
        p_pos = float(row[i_pos]) if i_pos is not None else 0.0
        p_neg = float(row[i_neg]) if i_neg is not None else 0.0
        top = max(p_pos, p_neg)
        if top < tau or top <= (1.0 - p_pos - p_neg):
            out.append(0.0)
        else:
            out.append(p_pos - p_neg)
    return out


def train_candidate(rows):
    """The whole training pipeline on already-loaded rows. Pure of the DB."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from scipy.sparse import hstack

    groups = near_duplicate_groups(
        [(row['post_id'], row['simhash']) for row in rows])
    first_seen = {}
    for row in rows:
        group = groups[row['post_id']]
        when = first_seen.get(group)
        if when is None or row['created'] < when:
            first_seen[group] = row['created']
    assignment = chronological_split(sorted(first_seen.items(),
                                            key=lambda kv: kv[1]))
    for row in rows:
        row['slice'] = assignment[groups[row['post_id']]]

    train_rows = [row for row in rows if row['slice'] == 'train']
    train_rows, dropped = drop_contradictions(train_rows)
    validation = [row for row in rows if row['slice'] == 'validation']
    test = [row for row in rows if row['slice'] == 'test']

    word_vec = TfidfVectorizer(ngram_range=(1, 2), min_df=3,
                               sublinear_tf=True)
    char_vec = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5),
                               min_df=3, max_features=200000,
                               sublinear_tf=True)
    texts = [row['text'] for row in train_rows]
    labels = [row['label'] for row in train_rows]
    features = hstack([word_vec.fit_transform(texts),
                       char_vec.fit_transform(texts)]).tocsr()
    clf = LogisticRegression(max_iter=2000, C=4.0)
    clf.fit(features, labels)

    validation_texts = [row['text'] for row in validation]
    validation_labels = [row['label'] for row in validation]
    lexicon_validation = evaluate(list(zip(
        [row['lexicon'] for row in validation], validation_labels)))

    sweep = []
    chosen = None
    for tau in TAU_GRID:
        scores = scores_for(clf, word_vec, char_vec, tau, validation_texts)
        metrics = evaluate(list(zip(scores, validation_labels)))
        ok, reasons = gates_pass(metrics, lexicon_validation)
        sweep.append({'tau': tau, 'metrics': metrics, 'passes': ok,
                      'reasons': reasons})
        # Widest coverage among passing points: the grid is ascending, so
        # the FIRST passing tau has the most hits.
        if ok and chosen is None:
            chosen = tau

    result = {
        'counts': {'rows': len(rows), 'train': len(train_rows),
                   'dropped_contradictory': dropped,
                   'validation': len(validation), 'test': len(test)},
        'word_vec': word_vec, 'char_vec': char_vec, 'clf': clf,
        'sweep': sweep, 'tau': chosen,
        'lexicon_validation': lexicon_validation,
        'training_cutoff': max(row['created'] for row in train_rows)
        .isoformat() if train_rows else None,
    }
    if chosen is not None:
        # The locked test is scored ONCE, here, for this candidate.
        test_scores = scores_for(clf, word_vec, char_vec, chosen,
                                 [row['text'] for row in test])
        test_labels = [row['label'] for row in test]
        result['validation_metrics'] = next(
            entry['metrics'] for entry in sweep if entry['tau'] == chosen)
        result['locked_test_metrics'] = evaluate(
            list(zip(test_scores, test_labels)))
        result['lexicon_test'] = evaluate(list(zip(
            [row['lexicon'] for row in test], test_labels)))
    return result


def reference_verdict(version):
    """The frozen-reference gate for this candidate, or None if unscored.

    score_sentiment_reference.py appends {'candidate', 'passes_10_3': bool}
    entries to evaluations.jsonl; promotion requires a passing entry for
    exactly this artifact version.
    """
    path = os.path.join(sentiment.ARTIFACT_DIR, 'evaluations.jsonl')
    if not os.path.exists(path):
        return None
    verdict = None
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            entry = json.loads(line)
            if entry.get('candidate') == version:
                verdict = bool(entry.get('passes_10_3'))
    return verdict


def write_artifact(result, version):
    import joblib
    import sklearn
    os.makedirs(sentiment.ARTIFACT_DIR, exist_ok=True)
    path = os.path.join(sentiment.ARTIFACT_DIR, '%s.joblib' % version)
    joblib.dump({
        'version': version,
        'word_vec': result['word_vec'], 'char_vec': result['char_vec'],
        'clf': result['clf'], 'tau': result['tau'],
        'classes': list(result['clf'].classes_),
        'preparation_version': sentiment_input.PREPARATION_VERSION,
        'trained_at': dt.datetime.utcnow().isoformat(),
        'training_cutoff': result.get('training_cutoff'),
        'counts': result['counts'],
        'validation_metrics': result.get('validation_metrics'),
        'locked_test_metrics': result.get('locked_test_metrics'),
        'lexicon_test': result.get('lexicon_test'),
        'sklearn_version': sklearn.__version__,
    }, path)
    return path


def promote(version, path):
    """Atomically point active.json at this artifact."""
    pointer = os.path.join(sentiment.ARTIFACT_DIR, 'active.json')
    staging = pointer + '.tmp'
    with open(staging, 'w', encoding='utf-8') as handle:
        json.dump({'version': version, 'path': os.path.basename(path)},
                  handle)
    os.replace(staging, pointer)


def cmd_train():
    """Train a candidate, report every gate, write the artifact. Never
    promotes -- score it against the frozen reference first, then run
    `promote --artifact <path>` on the SAME file (Codex blocker 5: the old
    single-command flow minted a fresh version at promote time, which the
    reference ledger could never have scored)."""
    with app.app_context():
        rows = load_rows()
    excluded_hashes = exclusion_hashes()
    rows, excluded = apply_exclusions(rows, excluded_hashes)
    if excluded:
        print('excluded %d rows near the burned/reference sets' % excluded)
    if len(rows) < 500:
        print('only %d finalized v2 training rows -- not enough to bother'
              % len(rows))
        return 1

    result = train_candidate(rows)
    print('rows %(rows)d  train %(train)d (dropped %(dropped_contradictory)d '
          'contradictory)  validation %(validation)d  test %(test)d'
          % result['counts'])
    for entry in result['sweep']:
        metrics = entry['metrics']
        print('tau %.2f  hit %.3f wrong %.3f precision %.3f noise %.3f  %s'
              % (entry['tau'], metrics['hit_rate'], metrics['wrong_rate'],
                 metrics['precision'], metrics['noise_fire'],
                 'PASS' if entry['passes']
                 else '; '.join(entry['reasons'])))
    if result['tau'] is None:
        print('no tau satisfies every constraint -- keeping the lexicon, '
              'collect more finalized v2 labels')
        return 1

    print('chosen tau %.2f' % result['tau'])
    print('locked test: %r' % result['locked_test_metrics'])
    version = 'clf-v2-%s' % dt.datetime.utcnow().strftime('%Y%m%d%H%M%S')
    path = write_artifact(result, version)
    print('candidate written: %s' % path)
    print('next: python -m scripts.score_sentiment_reference --classifier '
          '%s, then python -m scripts.train_radar_sentiment promote '
          '--artifact %s' % (path, path))
    return 0


def cmd_promote(artifact_path):
    """Gate and promote an EXISTING artifact. All three gates, spec §10.3:
    validation constraints (already enforced at training -- a tau exists),
    the teacher locked test, and the frozen adjudicated reference set."""
    import joblib
    stored = joblib.load(artifact_path)
    version = stored['version']
    if stored.get('tau') is None:
        print('PROMOTION BLOCKED: artifact carries no passing tau')
        return 1
    test_ok, test_reasons = gates_pass(stored['locked_test_metrics'],
                                       stored['lexicon_test'])
    if not test_ok:
        print('PROMOTION BLOCKED by the locked test: %s'
              % '; '.join(test_reasons))
        return 1
    ref = reference_verdict(version)
    if ref is not True:
        print('PROMOTION BLOCKED: the frozen reference set has not passed '
              '%s (score it with score_sentiment_reference.py --classifier '
              '%s first)' % (version, artifact_path))
        return 1
    promote(version, artifact_path)
    print('promoted %s' % version)
    return 0


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command')
    sub.add_parser('train')
    promote_cmd = sub.add_parser('promote')
    promote_cmd.add_argument('--artifact', required=True,
                             help='path to an already-scored candidate')
    args = parser.parse_args()
    if args.command == 'promote':
        return cmd_promote(args.artifact)
    return cmd_train()


if __name__ == '__main__':
    sys.exit(main())

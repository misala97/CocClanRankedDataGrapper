# personal_apps/scripts/sample_new_shape_mentions.py
"""The labelling wave on the NEW mention population.

Since 2026-09-08 15:35 UTC the extractor counts a Title-case symbol
(`Nvda`), a lowercase symbol (`lulu`), a name alone (`Nvidia`) and an
alias (`google`). The judge was never trained on those shapes in these
proportions. This draws a stratified sample of such mentions from
production so a labelling wave can be sized and run on them.

READ-ONLY. Runs on the VPS (cd /root/coc-stats/personal_apps, venv python,
PYTHONPATH=.), never writes to the database. The extraction REASON is not
a column -- it lives in the ingest log's intake counters -- so it is
re-derived here by running the production extractor over the stored post,
exactly as ingest does (prepare_extraction_input + extract with the
source's bare-token policy). The wave is written in the label harness's
export shape with each mention's REAL id, so `label_harness.py render
--export <file>` renders it unchanged and the labels land on the row they
were made for.

    # how big is the population, by reason?
    python -m scripts.sample_new_shape_mentions --since 2026-09-08T15:35:00 --count

    # the wave itself, once Michi has named N
    python -m scripts.sample_new_shape_mentions --since 2026-09-08T15:35:00 \\
        --n 1200 --out /root/trial-audit/candidates-newshape-2026-09-09.jsonl

No model is called and nothing is spent.
"""
import argparse
import collections
import datetime as dt
import json
import sys

from features.radar import extraction
from features.radar.config import (bare_token_confidence, bare_tokens_allowed,
                                   is_automated_author, looks_like_bot_feed,
                                   single_letter_cashtags_allowed)
from scripts import select_recall_candidates as sel

NEW_REASONS = ('titlecase_symbol', 'lowercase_symbol', 'name_only', 'alias')
DEFAULT_CAP_SHARE = 0.03            # no symbol may take more than 3% of the wave
TEXT_MAX = 2000                     # what the labeller reads (label_harness.MAX_CHARS)


def _prepared(post):
    return extraction.prepare_extraction_input(
        post.source, post.title, post.body or '', author=post.author,
        channel=post.channel)


def reasons_for(post, lookup):
    """{ticker: reason} exactly as production extraction assigns them."""
    if is_automated_author(post.source, post.author):
        return {}
    prepared = _prepared(post)
    if looks_like_bot_feed('%s %s' % (prepared.author_text, prepared.thread_context)):
        return {}
    matches = extraction.extract(
        prepared, lookup,
        allow_bare=bare_tokens_allowed(post.source),
        allow_single_letter=single_letter_cashtags_allowed(post.source),
        bare_confidence=bare_token_confidence(post.source))
    return {m.ticker: m.reason for m in matches}


def candidates_for(post, mentions, lookup):
    """The post's stored mentions whose reason is one of the new shapes."""
    reasons = reasons_for(post, lookup)
    prepared = _prepared(post)
    out = []
    for mention in mentions:
        reason = reasons.get(mention.ticker)
        if reason not in NEW_REASONS:
            continue
        out.append({
            'mention_id': mention.id, 'symbol': mention.ticker, 'cause': reason,
            'evidence': None, 'confidence': mention.confidence, 'stored_today': True,
            'sentiment_judged_at': getattr(mention, 'sentiment_judged_at', None),
            'post_id': post.id, 'source': post.source, 'external_id': post.external_id,
            'channel': post.channel, 'author': post.author,
            'created_utc': _iso(post.created_utc), 'title': post.title,
            'simhash': post.simhash, 'is_comment': prepared.is_comment,
            'author_text': (prepared.author_text or '')[:TEXT_MAX],
        })
    return out


def _iso(value):
    return value.isoformat() if hasattr(value, 'isoformat') else value


def export_row(candidate):
    """The label harness's export shape, carrying the production ids."""
    source = candidate['source']
    return {
        'mention_id': candidate['mention_id'],
        'ticker': candidate['symbol'],
        'confidence': candidate.get('confidence'),
        'lexicon_sentiment': None,
        'sentiment_relevance': None, 'sentiment_content_origin': None,
        'sentiment_attitude': None, 'sentiment_expected_move': None,
        'sentiment_confidence': None, 'sentiment_model': None,
        'sentiment_prompt_version': None,
        'sentiment_judged_at': _iso(candidate.get('sentiment_judged_at')),
        'post_id': candidate['post_id'],
        'source': source,
        'external_id': candidate['external_id'],
        'channel': candidate.get('channel') or (source.split(':', 1)[1] if ':' in source else ''),
        'author': candidate.get('author'),
        'created_utc': candidate['created_utc'],
        'title': candidate.get('title'),
        'body': None,
        'score': None, 'num_comments': None,
        'simhash': candidate.get('simhash'),
        'author_text': candidate['author_text'],
        'is_comment': bool(candidate.get('is_comment')),
        'preparation_version': 1,
        'stratum': 'new:%s' % candidate['cause'],
        'text_len': len(candidate['author_text']),
        'candidate': {'cause': candidate['cause'], 'evidence': candidate.get('evidence'),
                      'stored_today': True, 'external_id': candidate['external_id']},
    }


def pick(pool, n, seed, cap_share=DEFAULT_CAP_SHARE):
    """Equal shares per new reason, a cap per symbol, slack to the others."""
    quotas = {reason: 1.0 / len(NEW_REASONS) for reason in NEW_REASONS}
    return sel.pick(pool, n, quotas, cap_share, seed, cap_key='symbol')


# ---- the database side, VPS only ---------------------------------------------------

def _iter_posts_with_mentions(since, batch=2000):
    from extensions import db  # noqa: E402  (app import is the caller's)
    from models import RadarMention, RadarPost  # noqa: E402
    last = 0
    while True:
        posts = (db.session.query(RadarPost)
                 .filter(RadarPost.first_seen >= since, RadarPost.id > last)
                 .order_by(RadarPost.id).limit(batch).all())
        if not posts:
            return
        ids = [p.id for p in posts]
        mentions = collections.defaultdict(list)
        for m in (db.session.query(RadarMention)
                  .filter(RadarMention.post_id.in_(ids),
                          RadarMention.confidence == 'high').all()):
            mentions[m.post_id].append(m)
        for post in posts:
            yield post, mentions.get(post.id, [])
        last = ids[-1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--since', required=True,
                        help='UTC, e.g. 2026-09-08T15:35:00 (radar_posts.first_seen)')
    parser.add_argument('--count', action='store_true',
                        help='tally the population by reason and stop')
    parser.add_argument('--n', type=int, default=0)
    parser.add_argument('--out', default=None)
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--cap-share', type=float, default=DEFAULT_CAP_SHARE)
    args = parser.parse_args(argv)
    if not args.count and not (args.n and args.out):
        parser.error('pass --count, or --n and --out')
    since = dt.datetime.fromisoformat(args.since)

    from app import app  # noqa: E402
    from features.radar import universe  # noqa: E402
    with app.app_context():
        lookup = universe.load_lookup()
        by_reason = collections.Counter()
        by_source = collections.Counter()
        posts = 0
        pool = []
        for post, mentions in _iter_posts_with_mentions(since):
            posts += 1
            reasons = reasons_for(post, lookup)
            for m in mentions:
                by_reason[reasons.get(m.ticker, '(not reproduced)')] += 1
            if not args.count:
                for cand in candidates_for(post, mentions, lookup):
                    by_source[post.source.split(':')[0]] += 1
                    pool.append(cand)
    print('posts since %s: %d; high mentions by reason:' % (args.since, posts), file=sys.stderr)
    for reason, n in by_reason.most_common():
        print('  %-20s %7d' % (reason, n), file=sys.stderr)
    if args.count:
        return 0
    picked = pick(pool, args.n, args.seed, args.cap_share)
    with open(args.out, 'w', encoding='utf-8') as handle:
        for cand in picked:
            handle.write(json.dumps(export_row(cand), ensure_ascii=False) + '\n')
    print('pool %d new-shape mentions -> wave %d -> %s' % (len(pool), len(picked), args.out),
          file=sys.stderr)
    for cause, n in sorted(collections.Counter(c['cause'] for c in picked).items()):
        print('  %-20s %5d' % (cause, n), file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())

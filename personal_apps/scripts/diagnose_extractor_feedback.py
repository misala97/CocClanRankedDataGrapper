# personal_apps/scripts/diagnose_extractor_feedback.py
"""Read-only extraction feedback from finalized sentiment-v2 judgments.

Extractor-feedback spec §7. Makes no model calls and performs no inserts,
updates, deletes, bucket rebuilds, configuration changes, or artifact
promotions -- and that is ENFORCED, not promised: the whole run executes
inside a server-side READ ONLY transaction with a statement listener that
aborts on anything that is not a read.

The report always prints population and coverage; RECOMMENDATIONS are
marked not actionable until a prompt/model cohort has at least seven
consecutive live days of finalized judgments AND the compared slice holds
at least fifty of them. v1 verdicts are never used as truth anywhere.

Population: exactly one row per retained mention in the CURRENT-POLICY
cohort (posts first seen at or after EXTRACTION_POLICY_ACTIVATED_AT),
left-joined to its materialized final judgment -- an unjudged mention is
the report's missing/unjudged row, in every denominator it belongs to.
Rows from before the policy activation are the LEGACY-POLICY cohort:
reported separately, never ranked, because re-running today's extractor
over yesterday's admission rules measures the policy change, not the
text. `text_changed_or_absent` is reserved for current-cohort rows whose
retained text no longer yields the ticker.

Run from personal_apps/:

    python -m scripts.diagnose_extractor_feedback
    python -m scripts.diagnose_extractor_feedback --combine-prompt-versions
"""
import argparse
import collections
import datetime as dt
import hashlib
import re
import sys

sys.path.insert(0, '.')  # noqa: E402

import sqlalchemy as sa  # noqa: E402
from sqlalchemy import event  # noqa: E402

from app import app  # noqa: E402
from extensions import db  # noqa: E402
from features.radar import extraction, universe  # noqa: E402
from features.radar.config import (  # noqa: E402
    bare_token_confidence, bare_tokens_allowed,
    single_letter_cashtags_allowed, source_root)
from models import RadarMention, RadarPost, RadarSentimentJudgment  # noqa: E402

# The PRECISE UTC deployment instant of the hygiene release, settable at
# rollout without a code edit (Codex final review, finding 12):
#   RADAR_EXTRACTION_ACTIVATED_AT=2026-09-01T18:45:00
# Until it is set to the real moment, the conservative default keeps
# boundary admissions in the legacy cohort -- misclassified toward
# non-actionable, never toward false rankings.
import os
EXTRACTION_POLICY_ACTIVATED_AT = dt.datetime.fromisoformat(
    os.getenv('RADAR_EXTRACTION_ACTIVATED_AT', '2026-09-01T00:00:00'))

MIN_CONSECUTIVE_DAYS = 7
MIN_SLICE = 50

RELEVANCE_KEYS = ('relevant', 'irrelevant', 'uncertain')
ORIGIN_KEYS = ('human_chatter', 'broadcast_or_automated', 'uncertain')
TEXT_CHANGED = 'text_changed_or_absent'

_TEMPLATE_CASHTAG_RE = re.compile(r'\$[A-Z]{1,5}\b')
_TEMPLATE_NUMBER_RE = re.compile(r'[+-]?\d[\d.,]*%?')
_WS_RE = re.compile(r'\s+')


def wilson_low(successes, n, z=1.96):
    """95% lower bound; the ranking key, so one bad answer on a tiny
    ticker cannot outrank a measured failure (spec §7.3)."""
    if not n:
        return 0.0
    phat = successes / n
    denom = 1 + z * z / n
    center = phat + z * z / (2 * n)
    margin = z * ((phat * (1 - phat) + z * z / (4 * n)) / n) ** 0.5
    return max(0.0, (center - margin) / denom)


def consecutive_days(dates):
    """Longest run of UTC dates with no gap larger than one day."""
    ordered = sorted(set(dates))
    if not ordered:
        return 0
    best = run = 1
    for previous, current in zip(ordered, ordered[1:]):
        if (current - previous).days <= 1:
            run += 1
            best = max(best, run)
        else:
            run = 1
    return best


def readiness(judgment_dates, slice_n):
    """(actionable, reasons) per spec §7.1."""
    reasons = []
    days = consecutive_days(judgment_dates)
    if days < MIN_CONSECUTIVE_DAYS:
        reasons.append('%d consecutive judged days < %d'
                       % (days, MIN_CONSECUTIVE_DAYS))
    if slice_n < MIN_SLICE:
        reasons.append('%d finalized judgments < %d' % (slice_n, MIN_SLICE))
    return (not reasons), reasons


_TEMPLATE_BARE_RE = re.compile(r'(?<![$A-Za-z0-9])([A-Z]{2,5})')


def template_fingerprint(text, symbols=frozenset()):
    """Deterministic fingerprint that survives per-post variation.

    Exact simhash equality only finds verbatim duplicates; an automated
    template swaps its tickers and numbers per post. Cashtags AND
    recognized bare ticker tokens collapse to $T (a bare-GME and a
    bare-TSLA template are one template; Codex final review, finding 7),
    numbers to #, whitespace to one space.
    """
    normalized = _TEMPLATE_CASHTAG_RE.sub('$T', text or '')
    if symbols:
        normalized = _TEMPLATE_BARE_RE.sub(
            lambda match: '$T' if match.group(1) in symbols
            else match.group(0), normalized)
    normalized = _TEMPLATE_NUMBER_RE.sub('#', normalized)
    normalized = _WS_RE.sub(' ', normalized).strip().lower()
    return hashlib.sha1(normalized.encode('utf-8')).hexdigest()[:12]


def provenance_for(mention, post, lookup):
    """(reason, in_author_text, in_thread_context) or the changed marker.

    The SAME pure functions live ingest uses -- never a second regex
    (spec §11.3).
    """
    prepared = extraction.prepare_extraction_input(
        post.source, post.title, post.body, author=post.author,
        channel=post.channel)
    matches = extraction.extract(
        prepared, lookup,
        allow_bare=bare_tokens_allowed(post.source),
        allow_single_letter=single_letter_cashtags_allowed(post.source),
        bare_confidence=bare_token_confidence(post.source))
    for match in matches:
        if match.ticker == mention.ticker:
            return match.reason, match.in_author_text, match.in_thread_context
    return TEXT_CHANGED, False, False


def label_rates(rows, field, keys):
    """Counts for one judgment field over population rows, with the
    missing/unjudged bucket its own line. `uncertain` is NEVER merged
    into irrelevant or broadcast -- only explicit final answers support
    exclusion, and a test breaks if this ever changes."""
    counts = collections.Counter()
    for row in rows:
        value = row[field]
        counts[value if value is not None else 'missing_unjudged'] += 1
    ordered = list(keys) + ['missing_unjudged']
    return {key: counts.get(key, 0) for key in ordered}


def build_population(combine_prompt_versions=False):
    """One dict per retained mention, split into policy cohorts."""
    lookup = universe.load_lookup()
    symbol_set = frozenset(lookup)
    latest_primary = {}
    for row in (db.session.query(RadarSentimentJudgment)
                .filter(RadarSentimentJudgment.stage == 'primary')
                .order_by(RadarSentimentJudgment.id).all()):
        latest_primary[row.mention_id] = row     # last write wins = MAX(id)

    current, legacy = [], []
    query = (db.session.query(RadarMention, RadarPost)
             .join(RadarPost, RadarPost.id == RadarMention.post_id))
    for mention, post in query.all():
        reason, in_author, in_context = provenance_for(mention, post, lookup)
        primary = latest_primary.get(mention.id)
        cohort_version = ('ALL-VERSIONS-COMBINED'
                          if combine_prompt_versions
                          else mention.sentiment_prompt_version)
        row = {
            'source': post.source,
            'source_root': source_root(post.source),
            'ticker': mention.ticker,
            'confidence': mention.confidence,
            'reason': reason,
            'in_author_text': in_author,
            'in_thread_context': in_context,
            'judged': mention.sentiment_judged_at is not None,
            'judged_date': (mention.sentiment_judged_at.date()
                            if mention.sentiment_judged_at else None),
            'relevance': mention.sentiment_relevance,
            'content_origin': mention.sentiment_content_origin,
            'attitude': mention.sentiment_attitude,
            'judgment_confidence': mention.sentiment_confidence,
            'model': mention.sentiment_model,
            'prompt_version': cohort_version,
            'primary_attitude': primary.attitude if primary else None,
            'author': post.author,
            'post_id': post.id,
            'template': template_fingerprint(
                '%s %s' % (post.title or '', post.body or ''),
                symbols=symbol_set),
            'simhash': int(post.simhash or 0),
        }
        if post.first_seen >= EXTRACTION_POLICY_ACTIVATED_AT:
            current.append(row)
        else:
            legacy.append(row)
    return current, legacy


def cohorts_of(rows):
    grouped = collections.defaultdict(list)
    for row in rows:
        if row['judged']:
            grouped[(row['model'], row['prompt_version'])].append(row)
    return grouped


def reconciled(name, mapping, total):
    """Print one stratum table ONLY if it sums to the population --
    every row appears in every table, TEXT_CHANGED rows included (the
    old scope table silently dropped 1,953 of them while claiming
    reconciliation; Codex final review, blocker 5)."""
    if sum(mapping.values()) != total:
        raise AssertionError('%s sums to %d, population is %d'
                             % (name, sum(mapping.values()), total))
    print('  by %s: %s' % (name, mapping))


def scope_of(row):
    if row['reason'] == TEXT_CHANGED:
        return 'text_changed'
    return (('author' if row['in_author_text'] else '')
            + ('+context' if row['in_thread_context'] else '')) or 'none'


def top_table(rows, field, keep=12):
    counter = collections.Counter(row[field] for row in rows)
    table = dict(counter.most_common(keep))
    rest = sum(counter.values()) - sum(table.values())
    if rest:
        table['(other)'] = rest
    return table


def print_strata(rows, heading):
    print('\n== %s ==' % heading)
    total = len(rows)
    judged = sum(1 for row in rows if row['judged'])
    print('population %d, judged %d (%.1f%% coverage)'
          % (total, judged, 100.0 * judged / (total or 1)))
    for stratum in ('source_root', 'source', 'reason', 'confidence'):
        reconciled(stratum, top_table(rows, stratum), total)
    reconciled('scope', dict(collections.Counter(
        scope_of(row) for row in rows)), total)
    reconciled('ticker', top_table(rows, 'ticker'), total)
    reconciled('relevance',
               label_rates(rows, 'relevance', RELEVANCE_KEYS), total)
    reconciled('origin',
               label_rates(rows, 'content_origin', ORIGIN_KEYS), total)
    reconciled('attitude', label_rates(
        rows, 'attitude', ('positive', 'negative', 'mixed', 'none')), total)
    reconciled('judgment confidence', label_rates(
        rows, 'judgment_confidence', ('high', 'medium', 'low')), total)

    def review_state(row):
        if not row['judged'] or row['primary_attitude'] is None:
            return 'no_primary_history'
        if row['attitude'] != row['primary_attitude']:
            return 'review_flipped'
        return 'primary_stands'
    reconciled('primary-vs-final', dict(collections.Counter(
        review_state(row) for row in rows)), total)
    print('  reconciliation: every table above sums to %d OK' % total)


def ranked_slices(rows, exclusion_field, exclusion_value):
    """Ticker/source/form slices ranked by the Wilson lower bound of the
    exclusion share. Slices under MIN_SLICE go to the appendix."""
    grouped = collections.defaultdict(list)
    for row in rows:
        if row['judged']:
            # CONCRETE source, not the root: pooling every subreddit
            # hides source-specific pollution and cannot support the
            # specified ticker/source/form decision (Codex final review,
            # finding 6).
            grouped[(row['ticker'], row['source'],
                     row['reason'])].append(row)
    ranked, appendix = [], []
    for key, members in grouped.items():
        n = len(members)
        k = sum(1 for row in members
                if row[exclusion_field] == exclusion_value)
        entry = (wilson_low(k, n), k, n, key)
        (ranked if n >= MIN_SLICE else appendix).append(entry)
    ranked.sort(reverse=True)
    appendix.sort(reverse=True)
    return ranked, appendix


def print_rankings(rows, actionable):
    for field, value, label in (
            ('relevance', 'irrelevant', 'irrelevant share'),
            ('content_origin', 'broadcast_or_automated', 'broadcast share')):
        ranked, appendix = ranked_slices(rows, field, value)
        print('\n-- ranked by Wilson-low %s%s --'
              % (label, '' if actionable else '  [NOT ACTIONABLE]'))
        for low, k, n, key in ranked[:15]:
            print('  %-6s %-22s %-18s %3d/%3d  wilson_low=%.3f'
                  % (key[0], key[1], key[2], k, n, low))
        if appendix:
            print('  appendix (n<%d, unranked): %d slices'
                  % (MIN_SLICE, len(appendix)))
        roots = collections.defaultdict(lambda: [0, 0])
        for row in rows:
            if row['judged']:
                entry = roots[row['source_root']]
                entry[1] += 1
                if row[field] == value:
                    entry[0] += 1
        print('  root rollup: %s'
              % {root: '%d/%d' % (k, n)
                 for root, (k, n) in sorted(roots.items())})


def print_origin_feedback(rows, actionable):
    print('\n-- bluesky origin feedback%s --'
          % ('' if actionable else '  [NOT ACTIONABLE]'))
    bluesky = [row for row in rows if row['source_root'] == 'bluesky']
    for group_field, label in (('author', 'author'),
                               ('template', 'template')):
        grouped = collections.defaultdict(list)
        for row in bluesky:
            grouped[row[group_field]].append(row)
        top = sorted(grouped.items(), key=lambda kv: -len(kv[1]))[:8]
        print('  by %s:' % label)
        for key, members in top:
            judged = [row for row in members if row['judged']]
            origin = collections.Counter(row['content_origin']
                                         for row in judged)
            # Duplication is a fact about POSTS: multi-ticker posts carry
            # several mention rows and inflated the old per-mention ratio
            # (Codex final review, finding 7).
            posts = {row['post_id'] for row in members}
            hashes = {row['simhash'] for row in members}
            print('    %-24s mentions=%4d posts=%4d dup_ratio=%.2f '
                  'origin=%s'
                  % (str(key)[:24], len(members), len(posts),
                     1 - len(hashes) / (len(posts) or 1),
                     dict(origin)))
    print('  No automatic author block is proposed. Any future suppression '
          'rule needs its own approved design: source/form scoping, cashtag '
          'protection, minimum samples with conservative intervals, expiry, '
          'an exploration path, a config-version bump, and rollback '
          '(spec §7.3/§7.4).')


_read_statements = []


def _read_guard(conn, cursor, statement, parameters, context, executemany):
    head = statement.lstrip().split(None, 1)[0].upper()
    _read_statements.append(head)
    if head not in ('SELECT', 'SHOW', 'SET'):
        raise RuntimeError('diagnostic attempted a non-read statement: %s'
                           % statement[:120])


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--combine-prompt-versions', action='store_true')
    args = parser.parse_args(argv)

    with app.app_context():
        event.listen(db.engine, 'before_cursor_execute', _read_guard)
        try:
            with db.session.no_autoflush:
                # Server-side enforcement: the transaction itself refuses
                # writes, whatever this code does.
                db.session.execute(sa.text('SET TRANSACTION READ ONLY'))
                current, legacy = build_population(
                    args.combine_prompt_versions)

                if args.combine_prompt_versions:
                    print('!! PROMPT/MODEL VERSIONS COMBINED -- rates mix '
                          'semantic prompt generations. Explicitly requested.')

                print_strata(current, 'CURRENT-POLICY cohort (first_seen >= '
                             '%s)' % EXTRACTION_POLICY_ACTIVATED_AT.date())
                any_actionable = False
                for (model, version), members in sorted(
                        cohorts_of(current).items(),
                        key=lambda kv: -len(kv[1])):
                    dates = [row['judged_date'] for row in members]
                    actionable, reasons = readiness(dates, len(members))
                    any_actionable = any_actionable or actionable
                    print('\ncohort model=%s prompt=%s judged=%d: %s'
                          % (model, version, len(members),
                             'ACTIONABLE' if actionable
                             else 'NOT ACTIONABLE (%s)' % '; '.join(reasons)))
                    print_rankings(members, actionable)
                    print_origin_feedback(members, actionable)

                if legacy:
                    print_strata(legacy, 'LEGACY-POLICY cohort (pre-'
                                 'activation admissions; NEVER ranked)')
                if not any_actionable:
                    print('\nNO RECOMMENDATIONS: no cohort passes the '
                          'readiness gates.')
        finally:
            event.remove(db.engine, 'before_cursor_execute', _read_guard)
            db.session.rollback()
    return 0


if __name__ == '__main__':
    sys.exit(main())

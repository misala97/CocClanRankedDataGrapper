# personal_apps/scripts/measure_extractor_population.py
"""The extractor's two populations, from a raw capture, with their text.

Reads what scripts/capture_arctic_raw.py wrote and runs the PRODUCTION
extractor (ingest._extract_matches, gates included) over every post. Then
a deliberately loose pass over the author's text, keeping only what the
production rules rejected, each candidate tagged with the rule that
rejected it. No model is called; this is the measurement that makes the
labelling wave possible, and the numbers the sampling plan is sized from.

    cd personal_apps && PYTHONPATH=. python -m scripts.measure_extractor_population \\
        --raw C:/Users/michi/Desktop/radar_labels/raw/reddit \\
        --out C:/Users/michi/Desktop/radar_labels/raw/population \\
        --labels C:/Users/michi/Desktop/radar_labels/labels-sonnet5.jsonl \\
        --export C:/Users/michi/Desktop/radar_labels/export-2026-09-05.jsonl

REJECTION CAUSES (one row per post x symbol in rejected-candidates.jsonl)
    stopword                   bare token in the universe, blocked by STOPWORDS
                               and not reprieved by its company name
    lowercase_symbol           `nvda`, `soxl`: a universe symbol written in
                               lowercase, and NOT an ordinary word of the corpus
    name_only                  the company named, Capitalised as written
                               (Nvidia, GoPro), with no symbol anywhere
    cashtag_not_in_universe    `$SKHY`, `$BTC`: explicit notation for a symbol
                               the universe does not hold
    single_letter_cashtag      `$F` on a source that refuses one-letter cashtags
    bare_not_allowed           a bare token on a source with bare matching off
    bare_other / cashtag_other anything else the extractor dropped (coin
                               collisions, single-letter bare tokens)

ORDINARY WORDS come from the corpus itself, not a dictionary: a token the
stream writes mostly in lowercase (`app`, `time`, `people`) is a word, one
it writes mostly Capitalised or in caps (`nvda`, `Nvidia`, `soxl`) is a
name. Frequency alone cannot do this -- `nvidia` is as frequent as many
words -- and a dictionary would call Apple, Meta and Snap words. Measured
on the same stream it is applied to, with a floor of `min_posts` so a
token seen twice proves nothing either way.

Gated posts -- AutoModerator, bot feeds -- are counted and carry no
candidates: the gate dropped the whole post, and a candidate inside it is
not a recall question.
"""
import argparse
import collections
import glob
import json
import os
import re
import sys
import types

sys.path.insert(0, '.')  # noqa: E402

from features.radar import extraction, ingest  # noqa: E402
from features.radar.config import (  # noqa: E402
    BARE_PATTERN, CASHTAG_PATTERN, STOPWORDS, bare_tokens_allowed,
    is_automated_author, looks_like_bot_feed, single_letter_cashtags_allowed)

DEFAULT_MIN_POSTS = 10          # below this a token's casing proves nothing
DEFAULT_LOWER_SHARE = 0.5       # written lowercase at least this often = an ordinary word
TEXT_MAX = 2000                 # what the label harness shows a labeller

_CASHTAG_RE = re.compile(CASHTAG_PATTERN)
_BARE_RE = re.compile(BARE_PATTERN)
_LOWER_RE = re.compile(r'(?<![$A-Za-z0-9])([a-z]{3,5})\b')
_WRITTEN_RE = re.compile(r"(?<![A-Za-z])([A-Z][A-Za-z']{3,})(?![A-Za-z])")
_TOKEN_RE = re.compile(r"(?<![A-Za-z])([A-Za-z][A-Za-z']{1,14})(?![A-Za-z])")


# ---- reading -----------------------------------------------------------------

def iter_raw(raw_dir):
    """Every captured line, as a dict, day by day, sub by sub."""
    for path in sorted(glob.glob(os.path.join(str(raw_dir), '*', '*.jsonl'))):
        with open(path, encoding='utf-8') as handle:
            for line in handle:
                if line.strip():
                    yield json.loads(line)


def _raw_post(line):
    return types.SimpleNamespace(
        source=line['source'], external_id=line['external_id'],
        channel=line['channel'], author=line.get('author'),
        created_utc=line['created_utc'], title=line.get('title'),
        body=line.get('body') or '')


def common_words(raw_dir, min_posts=DEFAULT_MIN_POSTS, lower_share=DEFAULT_LOWER_SHARE):
    """Tokens the captured stream writes mostly in lowercase.

    Per token (case-folded): the posts writing it lowercase over the posts
    writing it at all. `app` and `people` are near 1.0; `nvda`, `Nvidia`
    and `soxl` are well under 0.5. Tokens seen in fewer than `min_posts`
    posts are left out -- unknown, not ordinary."""
    lower = collections.Counter()
    total = collections.Counter()
    for line in iter_raw(raw_dir):
        prepared = extraction.prepare_extraction_input(
            line['source'], line.get('title'), line.get('body'),
            author=line.get('author'), channel=line.get('channel'))
        seen_lower, seen_any = set(), set()
        for written in _TOKEN_RE.findall(prepared.author_text):
            folded = written.lower()
            seen_any.add(folded)
            if written == folded:
                seen_lower.add(folded)
        lower.update(seen_lower)
        total.update(seen_any)
    return {token for token, n in total.items()
            if n >= min_posts and lower[token] / n >= lower_share}


# ---- one post ----------------------------------------------------------------

def _name_index(lookup):
    """distinctive token -> symbol, for tokens naming exactly ONE symbol."""
    index = collections.defaultdict(set)
    for symbol, entry in lookup.items():
        for token in entry.get('distinctive') or ():
            index[token].add(symbol)
    return {token: next(iter(symbols)) for token, symbols in index.items()
            if len(symbols) == 1}


_NAME_INDEX_CACHE = {}


def _names_for(lookup):
    key = id(lookup)
    if key not in _NAME_INDEX_CACHE:
        _NAME_INDEX_CACHE.clear()
        _NAME_INDEX_CACHE[key] = _name_index(lookup)
    return _NAME_INDEX_CACHE[key]


def classify(line, lookup, is_common):
    """Production extraction plus the loose pass, for one captured post."""
    raw = _raw_post(line)
    source = raw.source
    prepared = extraction.prepare_extraction_input(
        source, raw.title, raw.body, author=raw.author, channel=raw.channel)
    text = prepared.author_text
    row = {'external_id': raw.external_id, 'source': source, 'kind': line.get('kind'),
           'created_utc': raw.created_utc, 'author_text': text,
           'title': raw.title, 'gate': None, 'accepted': [], 'rejected': []}

    if is_automated_author(source, raw.author):
        row['gate'] = 'automated_author'
    elif looks_like_bot_feed('%s %s' % (text, prepared.thread_context)):
        row['gate'] = 'bot_feed'
    if row['gate']:
        row['stored_today'] = False
        return row

    matches = ingest._extract_matches(raw, lookup)
    row['accepted'] = [{'ticker': m.ticker, 'confidence': m.confidence, 'reason': m.reason,
                        'in_author_text': m.in_author_text,
                        'in_thread_context': m.in_thread_context} for m in matches]
    row['stored_today'] = any(m.confidence == 'high' for m in matches)
    accepted = {m.ticker for m in matches}

    seen = set()

    def reject(symbol, cause, evidence):
        if symbol in accepted or symbol in seen:
            return
        seen.add(symbol)
        row['rejected'].append({'symbol': symbol, 'cause': cause, 'evidence': evidence})

    # Names as written: Capitalised distinctive tokens. Collected first so a
    # lowercase-symbol candidate can carry the name evidence with it.
    names = _names_for(lookup)
    named = {}
    for written in _WRITTEN_RE.findall(text):
        token = written.lower()
        symbol = names.get(token)
        if symbol and not is_common(token):
            named.setdefault(symbol, written)

    for tag in _CASHTAG_RE.findall(text):
        if len(tag) == 1:
            if tag in lookup and not single_letter_cashtags_allowed(source):
                reject(tag, 'single_letter_cashtag', '$' + tag)
            continue
        if tag not in lookup:
            reject(tag, 'cashtag_not_in_universe', '$' + tag)
        else:
            reject(tag, 'cashtag_other', '$' + tag)

    for token in _BARE_RE.findall(text):
        if token not in lookup:
            continue
        if token in STOPWORDS:
            reject(token, 'stopword', token)
        elif not bare_tokens_allowed(source):
            reject(token, 'bare_not_allowed', token)
        else:
            reject(token, 'bare_other', token)

    for word in _LOWER_RE.findall(text):
        symbol = word.upper()
        if symbol not in lookup or symbol in STOPWORDS or is_common(word):
            continue
        evidence = word if symbol not in named else '%s + %s' % (word, named[symbol])
        reject(symbol, 'lowercase_symbol', evidence)

    for symbol, written in named.items():
        reject(symbol, 'name_only', written)

    return row


# ---- the run -----------------------------------------------------------------

def run(raw_dir, lookup, out_dir, *, common_words):
    """Classify every captured post; write the rejected candidates and the
    population summary; return the summary."""
    os.makedirs(str(out_dir), exist_ok=True)
    is_common = common_words.__contains__
    summary = {'posts': 0, 'stored_today': 0, 'invisible': 0, 'gated': 0,
               'by_kind': collections.Counter(), 'by_sub': collections.Counter(),
               'by_reason': collections.Counter(),
               'rejected_by_cause': collections.Counter(),
               'rejected_by_cause_invisible': collections.Counter(),
               'top_accepted': collections.Counter(),
               'top_rejected': collections.defaultdict(collections.Counter)}
    external_ids = set()
    with open(os.path.join(str(out_dir), 'rejected-candidates.jsonl'), 'w',
              encoding='utf-8') as handle:
        for line in iter_raw(raw_dir):
            row = classify(line, lookup, is_common)
            external_ids.add(row['external_id'])
            summary['posts'] += 1
            summary['by_kind'][row['kind']] += 1
            summary['by_sub'][row['source']] += 1
            if row['gate']:
                summary['gated'] += 1
                continue
            if row['stored_today']:
                summary['stored_today'] += 1
            else:
                summary['invisible'] += 1
            for match in row['accepted']:
                summary['by_reason'][match['reason']] += 1
                if match['confidence'] == 'high':
                    summary['top_accepted'][match['ticker']] += 1
            for cand in row['rejected']:
                summary['rejected_by_cause'][cand['cause']] += 1
                if not row['stored_today']:
                    summary['rejected_by_cause_invisible'][cand['cause']] += 1
                summary['top_rejected'][cand['cause']][cand['symbol']] += 1
                handle.write(json.dumps({
                    'external_id': row['external_id'], 'source': row['source'],
                    'kind': row['kind'], 'created_utc': row['created_utc'],
                    'stored_today': row['stored_today'],
                    'accepted': [m['ticker'] for m in row['accepted']],
                    'symbol': cand['symbol'], 'cause': cand['cause'],
                    'evidence': cand['evidence'],
                    'title': row['title'], 'author_text': row['author_text'][:TEXT_MAX],
                    'truncated': len(row['author_text']) > TEXT_MAX,
                }, ensure_ascii=False) + '\n')
    for key in ('by_kind', 'by_sub', 'by_reason', 'rejected_by_cause',
                'rejected_by_cause_invisible'):
        summary[key] = dict(summary[key])
    summary['top_accepted'] = summary['top_accepted'].most_common(40)
    summary['top_rejected'] = {cause: counter.most_common(40)
                               for cause, counter in summary['top_rejected'].items()}
    summary['external_ids'] = len(external_ids)
    with open(os.path.join(str(out_dir), 'population.json'), 'w', encoding='utf-8') as handle:
        json.dump(summary, handle, indent=1)
    with open(os.path.join(str(out_dir), 'external-ids.txt'), 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(sorted(external_ids)))
    return summary


def join_labels(external_ids, label_rows, export_rows):
    """Labelled mention rows whose post is in the capture. Returns
    (joined rows, count of labelled rows whose post is NOT captured)."""
    by_mention = {row['mention_id']: row['external_id'] for row in export_rows}
    joined, missing = [], 0
    for label in label_rows:
        external_id = by_mention.get(label['mention_id'])
        if external_id in external_ids:
            joined.append(dict(label, external_id=external_id))
        else:
            missing += 1
    return joined, missing


def _read_jsonl(path):
    with open(path, encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--raw', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--labels', default=None)
    parser.add_argument('--export', default=None)
    parser.add_argument('--min-posts', type=int, default=DEFAULT_MIN_POSTS)
    parser.add_argument('--lower-share', type=float, default=DEFAULT_LOWER_SHARE)
    args = parser.parse_args(argv)

    from app import app
    from features.radar import universe
    with app.app_context():
        lookup = universe.load_lookup()

    words = common_words(args.raw, args.min_posts, args.lower_share)
    print('ordinary words: %d (min_posts %d, lower_share %.2f)'
          % (len(words), args.min_posts, args.lower_share), flush=True)
    summary = run(args.raw, lookup, args.out, common_words=words)
    print(json.dumps({k: v for k, v in summary.items() if k != 'top_rejected'}, indent=1))
    for cause, top in summary['top_rejected'].items():
        print('\n%s top symbols: %s' % (cause, top[:25]))

    if args.labels and args.export:
        with open(os.path.join(args.out, 'external-ids.txt'), encoding='utf-8') as handle:
            captured = set(handle.read().split())
        joined, missing = join_labels(captured, _read_jsonl(args.labels), _read_jsonl(args.export))
        with open(os.path.join(args.out, 'labelled-join.jsonl'), 'w', encoding='utf-8') as handle:
            for row in joined:
                handle.write(json.dumps(row) + '\n')
        by_rel = collections.Counter(row['relevance'] for row in joined)
        print('\nlabelled rows inside the capture: %d  (not captured: %d)  %s'
              % (len(joined), missing, dict(by_rel)))


if __name__ == '__main__':
    main()

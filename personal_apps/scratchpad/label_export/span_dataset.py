# personal_apps/scratchpad/label_export/span_dataset.py
"""Span supervision for the extraction model, from labels we already have.

THE SECOND MODEL. The judge answers "is this text about ticker X" but
cannot find X itself, so a rule still has to propose candidates. The
extraction model answers the other half: WHICH words in a post name a
company. A token classifier can tag `Nvidea`, `the iPhone maker` or a
German phrasing that no lookup holds; a static lookup then maps the span
to one of the ~12,500 symbols, because that many classes cannot be learned
from ~20,000 examples.

WHY THIS NEEDS NO NEW LABELLING. Every labelled row carries the `evidence`
token that produced it, locatable in the text for 4,474 of 4,500 wave rows
(99%). And the labels give BOTH sides of the same surface form: `Apple`
judged relevant is a company mention, `apple` judged irrelevant is not,
`internet` never is. A tagger trained on positives alone learns a word
list. Trained on both, it learns context -- which is the whole reason to
replace the word list.

THREE LABEL STATES, and the third is the one that matters:
  relevant    -> a span, at every occurrence of the token
  irrelevant  -> NO span, and the post is kept as a negative example
  uncertain   -> the row is DROPPED, both the span and the post's use as a
                 negative. The teacher refused to decide; training on it
                 either way invents an answer.

Torch-free: this is a decision about data.
"""
import collections
import re

DROP = 'uncertain'


def _occurrences(text, token):
    """Whole-word, case-insensitive character spans of `token` in `text`.

    A cashtag keeps its `$`, which is part of the notation the model should
    learn to see. Word boundaries stop `app` marking the first letters of
    `apple`.
    """
    if not token:
        return []
    body = re.escape(token.lstrip('$'))
    lead = r'\$' if token.startswith('$') else ''
    pattern = r'(?<![A-Za-z0-9])%s%s(?![A-Za-z0-9])' % (lead, body)
    return [(m.start(), m.end()) for m in re.finditer(pattern, text, re.IGNORECASE)]


def spans_for(row):
    """Character spans this row contributes, or None if the row is unusable.

    None means "drop this row": the teacher was uncertain, or the evidence
    token cannot be found in the text and guessing where it was would be
    fabrication. An empty list is a real answer -- the token is present and
    names no company.
    """
    if row['relevance'] == DROP:
        return None
    found = _occurrences(row['author_text'] or '', row['evidence'])
    if not found:
        return None
    if row['relevance'] != 'relevant':
        return []
    return [(start, end, row['ticker']) for start, end in found]


def examples_from(rows, key):
    """One example per post, spans merged across its rows.

    Grouping matters: a post naming two companies must be ONE example with
    two spans. Two examples would each treat the other's span as background
    and teach the tagger to miss it.
    """
    grouped = collections.OrderedDict()
    for row in rows:
        grouped.setdefault(key(row), []).append(row)

    examples = []
    for group_key, group in grouped.items():
        spans, negatives, usable = [], [], False
        for row in group:
            got = spans_for(row)
            if got is None:
                continue
            usable = True
            if got:
                spans.extend(got)
            else:
                negatives.append(row['evidence'])
        if not usable:
            continue          # every row was uncertain or unlocatable
        examples.append({
            'text': group[0]['author_text'],
            'spans': sorted(set(spans)),
            'negatives': negatives,
            'mention_ids': [r['mention_id'] for r in group],
            'key': group_key,
        })
    return examples


# ---- v2: the labels a mention-sampled wave never wrote ---------------------
#
# Waves sampled MENTIONS, not posts. A post labelled for NVDA that also
# names Google has no row for Google, and examples_from() -- correctly, from
# what it was given -- leaves Google as background. Measured 2026-09-08 over
# the 14,323 examples: Google appears unlabelled in 244 posts against 29
# gold spans, Nvidia 198 against 82, Nike 87 against 126. A tagger trained
# on that learns the names are usually NOT spans, and the held-out misses
# were exactly those names. Not label noise from the teacher; labels that
# were never asked for.
#
# Two repairs, both from instruments that already exist:
#   silver  -- an unlabelled occurrence of a universe NAME token the corpus
#              writes like a name (distinctive listing token AND name-shaped)
#              becomes a positive span. Nike, Google, Microsoft: a company
#              reference whatever the post is about, which is the finder's
#              question; relevance stays the encoder's.
#   ignore  -- an unlabelled occurrence of a universe SYMBOL written as one
#              (ALLCAPS or cashtag) is masked: AI, SPY, RSI, FCF are listed
#              symbols and ordinary words at once, and nothing in the labels
#              says which this post meant. Masked pieces carry no loss.
# Gold and judged negatives are never touched; silver and ignore fill only
# the gaps between them.

_BARE_SYMBOL_RE = re.compile(r'(?<![$A-Za-z0-9])([A-Z]{2,5})\b')
_CASHTAG_RE = re.compile(r'(?<![A-Za-z0-9])\$([A-Za-z]{1,5})\b')


def _overlaps(start, end, regions):
    return any(start < e and end > s for s, e in regions)


def augment(example, name_tokens, symbols):
    """The example plus `silver` and `ignore` regions. Pure."""
    text = example['text'] or ''
    taken = [(s, e) for s, e, _ in example['spans']]
    for token in example.get('negatives') or ():
        taken.extend(_occurrences(text, token))

    silver = []
    for match in re.finditer(r"[A-Za-z][A-Za-z']*", text):
        word = match.group(0).lower()
        if word in name_tokens and not _overlaps(match.start(), match.end(), taken):
            silver.append((match.start(), match.end()))
    taken_now = taken + silver

    ignore = []
    for pattern in (_BARE_SYMBOL_RE, _CASHTAG_RE):
        for match in pattern.finditer(text):
            if (match.group(1).upper() in symbols
                    and not _overlaps(match.start(), match.end(), taken_now)):
                ignore.append((match.start(), match.end()))
    return {**example, 'silver': sorted(set(silver)), 'ignore': sorted(set(ignore))}

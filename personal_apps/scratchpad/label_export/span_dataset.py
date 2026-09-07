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

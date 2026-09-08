# personal_apps/scratchpad/label_export/ask_encoder.py
"""Ask the encoder judge about your own text, from a terminal.

A toy, deliberately. It loads the SAME artifact the VPS serves and feeds it
the SAME (ticker, text) pair the daemon does, so what it prints is what
production would decide -- but it is standalone: no Flask, no database, no
`judge_backends`. That is the point. The daemon's copy latches load
failures, batches, and records provenance, none of which belongs in a
thing you poke at by hand.

WHAT IT CANNOT DO. The judge does not find tickers. It answers "is this
text about the ticker I gave you", so you always supply both. Finding the
ticker is the extraction model's job and that model does not exist yet.

    python scratchpad/label_export/ask_encoder.py NVDA "nvidia is cooked"
    python scratchpad/label_export/ask_encoder.py            # interactive

Probabilities are shown because the argmax alone hides the interesting
part: a 0.41/0.39 coin flip and a 0.99 both print as one word otherwise.
"""
import argparse
import json
import os
import sys

# The artifact lives in a gitignored directory inside a stale worktree. That
# is the only copy (2026-09-08); see TRIAL-RETIREMENT-PLAN.md step 0a.
DEFAULT_ARTIFACT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    '..', '..', '..', '..',
    'CodingStuff-worktrees', 'radar-encoder-judge', 'personal_apps',
    'artifacts', 'judge')

# What each head's answer means, in words. The class lists come from the
# artifact so a reordered head cannot silently relabel anything; these are
# only the glosses.
GLOSS = {
    'relevance': 'is the post actually about this company',
    'content_origin': 'a person talking, or a bot/newsfeed',
    'attitude': 'how the author feels about it',
    'expected_move': 'where the author thinks the price goes',
    'confidence': "the model's own certainty",
}


def load(artifact_dir):
    """The session, the tokenizer and the head classes.

    Reads `active.json` rather than a hardcoded version directory, the same
    indirection the daemon uses -- so pointing this at a different artifact
    is a one-file edit and never a code change.
    """
    import numpy
    import onnxruntime
    from tokenizers import Tokenizer

    with open(os.path.join(artifact_dir, 'active.json'), encoding='utf-8') as fh:
        pointer = json.load(fh)
    version_dir = os.path.join(artifact_dir, pointer['path'])
    with open(os.path.join(version_dir, 'config.json'), encoding='utf-8') as fh:
        config = json.load(fh)

    session = onnxruntime.InferenceSession(
        os.path.join(version_dir, 'model.onnx'),
        providers=['CPUExecutionProvider'])
    tokenizer = Tokenizer.from_file(os.path.join(version_dir, 'tokenizer.json'))
    tokenizer.enable_truncation(config['max_len'])
    tokenizer.enable_padding(length=config['max_len'])
    return numpy, session, tokenizer, config


def judge(numpy, session, tokenizer, config, pairs):
    """One verdict per (ticker, text), with per-class probabilities.

    The tokenizer takes the ticker and the text as a SENTENCE PAIR, not as
    one concatenated string: the model was trained with the ticker in
    segment A, and gluing them together would put every token in segment B
    and quietly change what it reads.
    """
    encoded = tokenizer.encode_batch(list(pairs))
    feed = {
        'input_ids': numpy.array([e.ids for e in encoded], dtype=numpy.int64),
        'attention_mask': numpy.array([e.attention_mask for e in encoded],
                                      dtype=numpy.int64),
    }
    if 'token_type_ids' in {i.name for i in session.get_inputs()}:
        feed['token_type_ids'] = numpy.array([e.type_ids for e in encoded],
                                             dtype=numpy.int64)
    outputs = session.run(None, feed)
    names = [o.name for o in session.get_outputs()]

    verdicts = []
    for position in range(len(encoded)):
        row = {}
        for index, head in enumerate(names):
            logits = outputs[index][position]
            shifted = numpy.exp(logits - logits.max())
            probabilities = shifted / shifted.sum()
            classes = config['heads'][head]
            best = int(probabilities.argmax())
            row[head] = (classes[best], float(probabilities[best]),
                         dict(zip(classes, (round(float(p), 3)
                                            for p in probabilities))))
        verdicts.append(row)
    return verdicts


def render(ticker, text, verdict, show_all):
    print()
    print('  %s  <-  %s' % (ticker, text if len(text) <= 90 else text[:87] + '...'))
    print('  ' + '-' * 68)
    for head, (answer, probability, distribution) in verdict.items():
        bar = '#' * int(round(probability * 20))
        print('  %-16s %-24s %5.1f%%  %s'
              % (head, answer, probability * 100, bar))
        if show_all:
            print('  %-16s %s' % ('', distribution))
    # The board's own rule, so the toy and the product cannot disagree about
    # what a verdict does: an irrelevant or automated mention leaves every
    # surface, whatever tone it carries.
    relevance = verdict['relevance'][0]
    origin = verdict['content_origin'][0]
    if relevance == 'irrelevant' or origin == 'broadcast_or_automated':
        print('  => the board would DROP this mention')
    elif relevance == 'uncertain':
        print('  => kept (uncertain is not a removal)')
    else:
        print('  => kept')
    print('  ' + GLOSS['relevance'] + ' / ' + GLOSS['attitude'])


def main():
    parser = argparse.ArgumentParser(
        description='Ask the radar encoder judge about your own text.')
    parser.add_argument('ticker', nargs='?', help='e.g. NVDA. Uppercase.')
    parser.add_argument('text', nargs='?', help='the post. Quote it.')
    parser.add_argument('--artifact-dir', default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument('--all', action='store_true',
                        help='print every class probability, not just the winner')
    args = parser.parse_args()

    if not os.path.isfile(os.path.join(args.artifact_dir, 'active.json')):
        sys.exit('no artifact at %s\n(pass --artifact-dir)'
                 % os.path.abspath(args.artifact_dir))

    print('loading the encoder (~570 MB, a few seconds)...', file=sys.stderr)
    numpy, session, tokenizer, config = load(args.artifact_dir)
    print('%s, max_len %d, trained on %d rows'
          % (config['base'], config['max_len'],
             config['manifest']['train_rows']), file=sys.stderr)

    if args.ticker and args.text:
        verdict = judge(numpy, session, tokenizer, config,
                        [(args.ticker.upper(), args.text)])[0]
        render(args.ticker.upper(), args.text, verdict, args.all)
        return

    print('\nTICKER then text. Blank ticker quits.\n')
    while True:
        try:
            ticker = input('ticker> ').strip().upper()
            if not ticker:
                return
            text = input('text  > ').strip()
        except (EOFError, KeyboardInterrupt):
            return
        if not text:
            continue
        verdict = judge(numpy, session, tokenizer, config,
                        [(ticker, text)])[0]
        render(ticker, text, verdict, args.all)
        print()


if __name__ == '__main__':
    main()

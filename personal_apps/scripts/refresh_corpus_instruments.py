# personal_apps/scripts/refresh_corpus_instruments.py
"""Regenerate the two corpus-derived word lists extraction reads.

    python scripts/refresh_corpus_instruments.py --raw C:/.../radar_labels/raw/reddit

Writes features/radar/data/ordinary_words.txt and name_shapes.txt, one
token per line, sorted, from a captured raw week (capture_arctic_raw.py).

WHY THESE EXIST. Whether a word names a company is not a property of the
word; `apple` the fruit and `Apple` the company are one string. What tells
them apart is how the corpus writes it: a token written in lowercase at
least half the time is an ordinary word, and a token capitalised
mid-sentence often enough is a name. Both measurements come from the same
raw week the extractor's recall was measured on, so the extractor's rules
and the numbers that justified them see the same corpus.

Both files are hashed into source_config_version(): regenerating them
changes which mentions get counted, and the stamp must move with them.
"""
import argparse
import os
import sys

sys.path.insert(0, '.')

from scripts import measure_extractor_population as pop   # noqa: E402

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        '..', 'features', 'radar', 'data')


def write(name, tokens):
    path = os.path.join(DATA_DIR, name)
    with open(path, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write('\n'.join(sorted(tokens)) + '\n')
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--raw', required=True)
    args = ap.parse_args(argv)
    ordinary = pop.common_words(args.raw)
    shapes = pop.name_shapes(args.raw)
    print('%d ordinary words -> %s' % (len(ordinary), write('ordinary_words.txt', ordinary)))
    print('%d name shapes   -> %s' % (len(shapes), write('name_shapes.txt', shapes)))


if __name__ == '__main__':
    main()

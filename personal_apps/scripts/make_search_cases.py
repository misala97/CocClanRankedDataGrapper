"""Write static/gym/src/__fixtures__/search-cases.json: how library.fold
folds some texts, every list entry's search text, some Verlauf rows, and what
some queries find in each by library.find -- the answers
static/gym/src/search.ts has to give as well (search.test.ts).

Run it after changing the list or the search:

    python scripts/make_search_cases.py

tests/test_gym_search_cases.py fails until the file says what the Python
says now.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from features.gym import library  # noqa: E402

FILE = ROOT / 'static' / 'gym' / 'src' / '__fixtures__' / 'search-cases.json'

FOLDS = (
    'Bankdrücken (Kurzhantel)', 'Bankdruecken KH', 'MAßE Straße', 'T-Bar-Rudern',
    "Farmer's Walk", '45° Beinpresse', '  Übungen,  Überzüge ', 'ÄÖÜ äöü', '-', '',
)

# Exact words, fragments, aliases, the movement aliases, typos of each kind,
# words too short to be typos, and nothing at all.
QUERIES = (
    'bench', 'decline bench', 'Bankdrüken', 'Bankdrückken', 'bankdruken kurzhantel',
    'kniebeu', 'kniebeigen', 'lat raise', 'lat pulldwon', 'legpress', 'rowing', 'romanian',
    'curls kabel', 'fliegnede', 'bnak', 'zzz', 'T Bar', 'aussenrotation', 'ueberzuege',
    'Schulterdrücken stehend', 'squat', 'bench press', 'press bench',
)

# Verlauf rows: a workout's name and date words as routes/reports.py folds
# them apart, and its exercises by list key. HistoryPage searches each by
# those and its exercises' list texts, apart as well.
HISTORY = (
    ('Push 2', '31.07.2026 Juli 2026', ('barbell_bench_press', 'dumbbell_lateral_raise')),
    ('Push', '23.09.2026 September 2026', ('dumbbell_bench_press',)),
    ('Push', '01.07.2026 Juli 2026', ('barbell_bench_press', 'dumbbell_lateral_raise')),
    ('Beine', '13.07.2026 Juli 2026', ('barbell_squat',)),
    ('Pull', '31.08.2026 August 2026', ('cable_lat_pulldown',)),
)

# A date, and one a typo from four others; a workout's name against its date;
# an exercise's whole name against a Gerät another exercise of the day has.
HISTORY_QUERIES = (
    '31.07', '30.07', 'juli', 'push 2', 'Push 23.09', 'Bankdrücken Kurzhantel',
    'bankdrucken seitheben', 'Bankdrüken', 'kurzhantel',
)


def _found(texts, queries):
    keys = list(texts)
    found = []
    for query in queries:
        hits, tier = library.find(list(texts.values()), query)
        found.append({'query': query, 'tier': tier, 'hits': [keys[i] for i in hits]})
    return found


def cases():
    texts = {entry.key: entry.search_text for entry in library.LIBRARY}
    history = {
        f'{name} {day[:10]}': {'search': library.fold_apart((name, day)), 'exercises': list(keys)}
        for name, day, keys in HISTORY
    }
    history_texts = {
        row: '\n'.join((fields['search'], *(texts[key] for key in fields['exercises'])))
        for row, fields in history.items()
    }
    return {
        'fuzzy_from': library.FUZZY_FROM,
        'fold': [[text, library.fold(text)] for text in FOLDS],
        'library': texts,
        'queries': _found(texts, QUERIES),
        'history': history,
        'history_queries': _found(history_texts, HISTORY_QUERIES),
    }


def dumps(data):
    return json.dumps(data, ensure_ascii=False, indent=1) + '\n'


if __name__ == '__main__':
    FILE.parent.mkdir(exist_ok=True)
    FILE.write_text(dumps(cases()), encoding='utf-8')
    print(f'wrote {FILE.relative_to(ROOT)}')

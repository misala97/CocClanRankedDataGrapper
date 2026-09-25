"""The search cases search.ts is held to are what library.py says now.

static/gym/src/__fixtures__/search-cases.json holds the list's search texts
and what some queries find in them; search.test.ts checks the TypeScript
gives the same answers. This checks the file has not gone stale behind a
change to the list or the search (walkthrough G-145).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

import make_search_cases  # noqa: E402


def test_the_search_cases_are_what_the_python_says():
    on_disk = make_search_cases.FILE.read_text(encoding='utf-8')
    assert on_disk == make_search_cases.dumps(make_search_cases.cases()), (
        'stale: run python scripts/make_search_cases.py')


def test_the_cases_cover_every_tier_and_nothing_found():
    cases = make_search_cases.cases()
    for queries in (cases['queries'], cases['history_queries']):
        assert {q['tier'] for q in queries} == {'phrase', 'words', 'typos'}
        assert any(not q['hits'] for q in queries)

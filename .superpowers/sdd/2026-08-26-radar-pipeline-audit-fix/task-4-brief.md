## Task 4: Wire `single_letter_cashtags_allowed`

**Files:**
- Modify: `personal_apps/features/radar/ingest.py:66-84` (`_extract_for`)
- Modify: `personal_apps/tests/test_radar_ingest.py`

**Interfaces:**
- Consumes: `config.single_letter_cashtags_allowed(source)` — already exists, called by nothing.
- Produces: no new names.

`SINGLE_LETTER_CASHTAGS` is hashed into `source_config_version`, so the stamp claims it is policy. `extract_tickers` defaults `allow_single_letter=True` and `_extract_for` never overrides it. Live cost: 353 single-letter mentions, 3.0% of the entire high-confidence corpus, on a source where the config says to reject them.

**Bumps `source_config_version`** — correctly, because it changes which mentions count.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_ingest.py`:

First give the file's existing `post()` helper (`tests/test_radar_ingest.py:56`) a
`source` parameter, since every test in the file needs one after Task 7 anyway:

```python
def post(ident='t3_1', body='$ZZG is ripping', score=5, author='u1',
         minute=10, title=None, source='stocktwits'):
    return RawPost(source=source, external_id=ident, channel='testsub',
                   author=author,
                   created_utc=dt.datetime(2026, 4, 15, 14, minute, 0),
                   title=title, body=body, score=score, num_comments=0,
                   url='https://example.invalid/%s' % ident)
```

Then append the test:

```python
def test_a_single_letter_cashtag_is_refused_on_a_general_network():
    """`$M` on Bluesky is money shorthand, not Macy's.

    Measured on live Bluesky: 119 of 3302 cashtag matches were single letters
    and essentially all were prose -- "Tax @60% for over a $M", "make $B's".
    config.SINGLE_LETTER_CASHTAGS has said so since it was written; nothing
    passed it to the extractor until now, and 353 such mentions reached the
    production corpus, 3.0% of the whole high-confidence set.
    """
    from features.radar import ingest

    lookup = {'B': {'name': 'Barnes Group Inc.', 'exchange': 'NYSE',
                    'distinctive': set()}}
    general = post(ident='zz-single', body='make $B and youre set',
                   source='bluesky')
    finance = post(ident='zz-single-2', body='make $B and youre set',
                   source='stocktwits')

    assert ingest._extract_for(general, lookup) == []
    # The same text on a finance-native population still yields the company.
    assert ingest._extract_for(finance, lookup) == [('B', 'high')]
```

After Task 7 retires StockTwits the second assertion has no source to use;
that task's Step 7 replaces it with the monkeypatched extension-point test in
the same shape as the coin-collision one.

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_radar_ingest.py::test_a_single_letter_cashtag_is_refused_on_a_general_network -v
```

Expected: `AssertionError: assert [('B', 'high')] == []`.

- [ ] **Step 3: Pass the flag**

In `personal_apps/features/radar/ingest.py`, change the import and the call:

```python
from .config import (
    BUCKET_MINUTES, bare_token_confidence, bare_tokens_allowed,
    coin_collision_dropped, looks_like_bot_feed,
    single_letter_cashtags_allowed)
```

```python
    tickers = extraction.extract_tickers(
        raw.title, raw.body, lookup,
        allow_bare=bare_tokens_allowed(raw.source),
        allow_single_letter=single_letter_cashtags_allowed(raw.source),
        bare_confidence=bare_token_confidence(raw.source))
```

Update `_extract_for`'s docstring — it says "Three per-source judgements"; there are four.

- [ ] **Step 4: Run it to verify it passes**

```bash
python -m pytest tests/test_radar_ingest.py tests/test_radar_extraction.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/ingest.py personal_apps/tests/test_radar_ingest.py
git commit -m "fix(radar): the single-letter cashtag rule was hashed but never called"
```

---


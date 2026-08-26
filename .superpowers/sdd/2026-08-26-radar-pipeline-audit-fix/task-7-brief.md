## Task 7: Retire StockTwits

**Files:**
- Delete: `personal_apps/features/radar/sources/stocktwits.py`, `personal_apps/tests/test_radar_stocktwits.py`
- Modify: `personal_apps/features/radar/config.py`
- Modify: `personal_apps/run_radar_ingest.py`
- Modify: `personal_apps/features/radar/scheduling.py` (docstrings only)
- Modify: `personal_apps/tests/test_radar_buckets.py`, `test_radar_bucket_sources.py`, `test_radar_config.py`, `test_radar_daemon.py`, `test_radar_ingest.py`, `test_radar_profile.py`, `test_radar_scoring.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `config.SOURCES == ('bluesky', 'fourchan', 'reddit')`.

Diagnosed 2026-08-26: `cf-mitigated: challenge`, `server: cloudflare`, `<title>Just a moment...</title>` — every endpoint, every user agent including none, identical from the VPS and from a home connection. StockTwits placed its whole API behind bot management. Reaching it means defeating a bot challenge, which is out of scope on principle. Zero posts, zero poll rows, no cursor, in five days of production.

**Bumps `source_config_version`.**

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_config.py`:

```python
def test_stocktwits_is_retired():
    """Cloudflare bot management, diagnosed 2026-08-26.

    403 on every endpoint with every user agent, from two networks. It reported
    `missing` honestly for five days and produced nothing, while remaining a
    selectable venue in the UI -- an invitation to filter on a source that has
    never returned a row.
    """
    from features.radar import config

    assert 'stocktwits' not in config.SOURCES
    assert 'stocktwits' not in config.BARE_TOKENS_ALLOWED
    assert 'stocktwits' not in config.SINGLE_LETTER_CASHTAGS
    assert 'stocktwits' not in config.SOURCE_KIND
    assert not hasattr(config, 'STOCKTWITS_REQUESTS_PER_HOUR')


def test_no_source_reads_a_coin_symbol_as_a_company():
    """A consequence of the retirement, named so it is not rediscovered.

    StockTwits was the only population where $LINK meant Interlink rather than
    Chainlink. With it gone, COIN_COLLISION_SYMBOLS are dropped everywhere --
    49 real tickers lose their mentions on every live source. The map stays a
    map rather than collapsing to a constant, because Telegram will need its
    own entry and the extension point is the point.
    """
    from features.radar import config

    assert not any(config.COIN_SYMBOLS_MEAN_STOCKS.values())
    assert config.coin_collision_dropped('bluesky', 'LINK') is True
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_radar_config.py -v -k "stocktwits_is_retired or coin_symbol_as_a_company"
```

Expected: `AssertionError: assert 'stocktwits' not in ('stocktwits', 'bluesky', 'fourchan', 'reddit')`.

- [ ] **Step 3: Strip StockTwits from config**

In `personal_apps/features/radar/config.py`:

```python
SOURCES = ('bluesky', 'fourchan', 'reddit')
```

Remove the `'stocktwits'` entry and its comment from `BARE_TOKENS_ALLOWED`, `COIN_SYMBOLS_MEAN_STOCKS`, `SINGLE_LETTER_CASHTAGS` and `SOURCE_KIND`. Delete `STOCKTWITS_REQUESTS_PER_HOUR` and its comment.

Add above `COIN_SYMBOLS_MEAN_STOCKS`:

```python
# Sources where a coin-shaped symbol should be read as the coin, not the
# company. Finance-native populations are the exception -- and since StockTwits
# was retired 2026-08-26 there are none, so every symbol in
# COIN_COLLISION_SYMBOLS is now dropped on every live source. That costs 49
# real tickers their mentions, which is the price of not putting Chainlink
# chatter under Interlink Electronics.
#
# Kept as a map rather than collapsed to a constant: Telegram is the next
# source and will need its own entry, and the extension point is the point.
```

- [ ] **Step 4: Delete the module and its suite**

```bash
git rm personal_apps/features/radar/sources/stocktwits.py personal_apps/tests/test_radar_stocktwits.py
```

- [ ] **Step 5: Strip StockTwits from the daemon**

In `personal_apps/run_radar_ingest.py`: delete `_stocktwits_fetcher` entirely; remove `stocktwits` from the `from features.radar.sources import ...` line; remove `STOCKTWITS_REQUESTS_PER_HOUR` from the config import; delete `_CYCLES_PER_HOUR` and `SYMBOL_BUDGET_PER_CYCLE`; remove `st_client` and the `'stocktwits'` entry from `build_fetchers`.

Update the module docstring — it says "Three sources run behind one contract."

- [ ] **Step 6: Re-document the scheduler's orphaned reasons**

In `personal_apps/features/radar/scheduling.py`, `MIN_INTERVAL` / `MAX_INTERVAL` are documented as StockTwits-shaped and every remaining caller overrides them. Re-document as generic defaults. In `retire_untracked`, the prohibition names StockTwits as its example; restate it as the property:

```python
    ONLY for a source whose configured list is the COMPLETE set -- Reddit,
    where REDDIT_SUBS is exhaustive. A source whose tracked set is a rolling
    window must never call this: a symbol falling out of the window is
    temporary, and deleting the row throws away a real observed_rate that took
    hours to learn.
```

- [ ] **Step 7: Move the test suites off `'stocktwits'`**

In each of `test_radar_buckets.py`, `test_radar_bucket_sources.py`, `test_radar_daemon.py`, `test_radar_ingest.py`, `test_radar_profile.py`, `test_radar_scoring.py`, replace `'stocktwits'` with `'bluesky'` as the default source, including `ALL_OK` and any `fetcher_for(..., source=...)` default.

Two tests need more than a rename:

- `test_radar_ingest.py::test_a_coin_collision_is_dropped_on_a_general_source` still passes — `bluesky` is `False` in the map.
- `test_radar_ingest.py::test_the_same_symbol_still_counts_on_a_finance_source` has no finance source left. Replace it with a test that pins the monkeypatched extension point, so the mechanism stays covered:

```python
def test_a_source_can_opt_into_reading_coin_symbols_as_companies(seeded, monkeypatch):
    """The extension point, kept alive with no live source using it.

    StockTwits was the only population where $LINK meant Interlink. It is
    retired; this pins that a future finance-native source can still opt in,
    rather than the map quietly becoming a constant nobody can override.
    """
    from features.radar import config

    monkeypatch.setitem(config.COIN_SYMBOLS_MEAN_STOCKS, 'bluesky', True)
    assert config.coin_collision_dropped('bluesky', 'LINK') is False
```

- [ ] **Step 8: Run the whole radar suite**

```bash
python -m pytest tests/ -k radar -v
```

Expected: all pass, and `test_radar_stocktwits.py` is gone from collection.

- [ ] **Step 9: Commit**

```bash
git add -A personal_apps
git commit -m "fix(radar): retire StockTwits, which Cloudflare has refused since launch"
```

---


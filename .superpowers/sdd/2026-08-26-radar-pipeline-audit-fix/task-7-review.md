### Spec Compliance

- ❌ The production retirement is implemented correctly, but the package needs fixes because two explicitly required regression mechanisms lack teeth; see Important issues 1 and 2.
- ✅ The live source set is exactly `('bluesky', 'fourchan', 'reddit')` (`personal_apps/features/radar/config.py:17`), and `build_fetchers()` exposes exactly those three keys (`personal_apps/run_radar_ingest.py:163-172`). The StockTwits module, fetcher, client, request budget, and per-cycle budget are absent from `945c9d7`.
- ✅ The source configuration stamp changed from `fc1a0ee4cab51d65` at `73981db` to `8106787f1fa72179` at `945c9d7`; the source and extraction-policy inputs are included at `personal_apps/features/radar/config.py:534-563`.
- ✅ StockTwits is absent from the UI label map (`personal_apps/static/radar/src/format.ts:55-58`), while the selector is populated from `list(SOURCES)` (`personal_apps/features/radar/routes/api.py:105`). Focused frontend verification passed: 2 files, 29 tests.
- ✅ Generic future-source and broadcast behavior remains: unknown source labels fall back to their key (`personal_apps/static/radar/src/format.ts:64`), and source-kind dispatch/defaults remain generic (`personal_apps/features/radar/config.py:103-118`).
- ✅ A tracked-file grep at `945c9d7` found no live StockTwits path or symbol. Surviving names are historical evidence or explicit retirement tests. In particular, the real historical columns remain unchanged in migrations (`personal_apps/migrations/versions/7883c6e08708_add_radar_tables.py:33-41`, `personal_apps/migrations/versions/01da83522036_add_radar_bucket_sources.py:46-52`) and are accurately discussed at `personal_apps/models.py:658-660` and asserted at `personal_apps/tests/test_radar_bucket_sources.py:114-116`.
- ✅ The beyond-brief prose edits consistently replace present-tense live-path claims with generic or surviving-source wording. Preserved StockTwits prose is historical measurement, incident context, retirement rationale, or a genuine historical schema name; no prose edit misstates StockTwits as a live source.
- ⚠️ No unverifiable task item. Per review instructions, the broad suite and the two known manifest-dependent API failures were not rerun.

### Strengths

- The implementation cleanly removes the retired source instead of weakening errors, adding challenge workarounds, or leaving a dormant fetcher.
- The package preserves the open fetcher contract and broadcast scoring extension points while removing only StockTwits-specific code.
- Source-list, fetcher-key, config-version, historical-reference, and frontend checks all agree with the supplied diff. `git diff --check 73981db..945c9d7` is clean.
- The request-budget test was correctly deleted with its only production subject; `_stocktwits_fetcher`, `SYMBOL_BUDGET_PER_CYCLE`, and the StockTwits client no longer exist.
- Focused unmutated checks passed: 2/2 status-sensitive ingest tests, 3/3 extension tests, 5/5 retirement/fetcher/broadcast checks, and 29/29 frontend tests. Runtime DB evidence was namespaced to exact `ZZG`/`ZZTASK7` rows and cleanup was verified at zero remaining rows.

### Issues

#### Critical

- None.

#### Important

- `personal_apps/tests/test_radar_ingest.py:122-129,209-226`: 🟡 risk: the surviving tests cover only `missing -> ok`, not the other half of the deleted missing-vs-ok distinction. A runtime mutation that rewrote every empty healthy `FetchResult(posts=[], status='ok')` to `missing` left all four status-sensitive `run_cycle` tests passing. This matters now: Reddit has a live no-work-due branch that returns empty `ok` (`personal_apps/run_radar_ingest.py:129-134`), but no test pins it. Add an explicit empty-healthy `run_cycle` case and preferably adapt the deleted daemon no-due test to `_reddit_fetcher`.
- `personal_apps/tests/test_radar_ingest.py:339-350`: 🟡 risk: `test_a_source_can_opt_into_reading_coin_symbols_as_companies` never enters ingest; it only mutates the config map and calls the same config helper already covered at `personal_apps/tests/test_radar_config.py:104-114`. Mutating the actual ingest consumer at `personal_apps/features/radar/ingest.py:86-87` to ignore the opt-in left this test passing, while a direct `_extract_for` probe incorrectly dropped `$LINK`. Make this an ingest-level assertion through `_extract_for` or `run_cycle`; the currently declared `seeded` fixture otherwise has no purpose.

#### Minor

- `personal_apps/tests/test_radar_config.py:278-306`: 🔵 nit: the retirement pin checks three policy maps but omits `COIN_SYMBOLS_MEAN_STOCKS`. Adding `'stocktwits': False` to that map left both retirement tests passing because `not any(values)` checks values, not key absence. Add `assert 'stocktwits' not in config.COIN_SYMBOLS_MEAN_STOCKS`.

### Teeth Evidence

Teeth score: **4/6** required absence/extension checks killed their targeted mutant.

1. **Missing-only source:** rewrote returned `missing` to `ok` before `run_cycle`. `test_a_missing_source_writes_nothing_at_all` failed at `personal_apps/tests/test_radar_ingest.py:126` with `{'bluesky': 'ok'}` instead of `missing`. **Killed.**
2. **One source missing beside one healthy source:** the same mutation made `test_one_source_failing_does_not_stop_the_other` fail at `personal_apps/tests/test_radar_ingest.py:221`; Bluesky became `ok`. **Killed.**
3. **Healthy source with no work/posts:** rewrote empty `ok` to `missing`. The four surviving status-sensitive ingest tests all passed (4/4), and no current ingest test supplies an empty healthy result. A focused `_reddit_fetcher` probe confirmed the live branch currently returns `ok`, so this is a real uncovered distinction. **Survived.**
4. **Config coin-symbol opt-in:** changed `config.coin_collision_dropped` to ignore `COIN_SYMBOLS_MEAN_STOCKS`. `test_a_finance_native_source_can_opt_into_coin_symbols` failed at `personal_apps/tests/test_radar_config.py:113` (`True is False`). **Killed.**
5. **Ingest coin-symbol opt-in:** changed `ingest.coin_collision_dropped` to ignore the map while leaving the config helper intact. `test_a_source_can_opt_into_reading_coin_symbols_as_companies` still passed (1/1); a behavioral `_extract_for` probe returned `[]` instead of `[('LINK', 'high')]`. **Survived.**
6. **Single-letter cashtag opt-in:** changed `ingest.single_letter_cashtags_allowed` to always return `False`. `test_a_source_can_opt_into_single_letter_cashtags` failed at `personal_apps/tests/test_radar_ingest.py:429` with `[]` instead of `[('B', 'high')]`. **Killed.**

Additional retirement-pin mutation: adding a false-valued StockTwits coin-policy key left both retirement tests passing (2/2), supporting the Minor issue above.

### Assessment

Task quality: Needs fixes.

The production removal is disciplined and spec-aligned, but the exceptional review explicitly requires regression teeth. Restore the healthy-empty distinction and make the ingest coin opt-in test exercise ingest before approval.

# Task 7 report: Retire StockTwits

Commit: `945c9d71c318b2d646416f9528ebddfa4f2350ed` on `codex/radar-pipeline-audit`

```
fix(radar): retire StockTwits, which Cloudflare has refused since launch
20 files changed, 252 insertions(+), 598 deletions(-)
delete mode 100644 personal_apps/features/radar/sources/stocktwits.py
delete mode 100644 personal_apps/tests/test_radar_stocktwits.py
```

## Step 2 red run (verbatim)

```
collecting ... collected 30 items / 28 deselected / 2 selected

tests/test_radar_config.py::test_stocktwits_is_retired FAILED            [ 50%]
tests/test_radar_config.py::test_no_source_reads_a_coin_symbol_as_a_company FAILED [100%]

================================== FAILURES ===================================
_________________________ test_stocktwits_is_retired __________________________

    def test_stocktwits_is_retired():
        """Cloudflare bot management, diagnosed 2026-08-26. ..."""
        from features.radar import config

>       assert 'stocktwits' not in config.SOURCES
E       AssertionError: assert 'stocktwits' not in ('stocktwits', 'bluesky', 'fourchan', 'reddit')
E        +  where ('stocktwits', 'bluesky', 'fourchan', 'reddit') = <module 'features.radar.config' ...>.SOURCES

tests\test_radar_config.py:283: AssertionError
_______________ test_no_source_reads_a_coin_symbol_as_a_company _______________

    def test_no_source_reads_a_coin_symbol_as_a_company():
        """A consequence of the retirement, named so it is not rediscovered. ..."""
        from features.radar import config

>       assert not any(config.COIN_SYMBOLS_MEAN_STOCKS.values())
E       AssertionError: assert not True
E        +  where True = any(dict_values([True, False, False]))
E        +    where dict_values([True, False, False]) = {'bluesky': False, 'fourchan': False, 'stocktwits': True}.values

tests\test_radar_config.py:301: AssertionError
====================== 2 failed, 28 deselected in 1.86s =======================
```

Both failures are exactly the documented ones (`assert 'stocktwits' not in (...)`). Implementation followed only after this was observed.

## `source_config_version()` before/after

```
BEFORE: fc1a0ee4cab51d65
AFTER:  8106787f1fa72179
```
Confirmed different, with no manual edit to `source_config_version()` -- the hash moved automatically because it inputs `sorted(SOURCES)` and the two `COIN_*` maps, exactly as expected.

## What changed, per file

### Backend

- **`personal_apps/features/radar/config.py`** -- `SOURCES` drops `'stocktwits'` (now `('bluesky', 'fourchan', 'reddit')`). Removed the `'stocktwits'` entry (and its comment) from `BARE_TOKENS_ALLOWED`, `COIN_SYMBOLS_MEAN_STOCKS`, `SINGLE_LETTER_CASHTAGS`, `SOURCE_KIND`. Deleted `STOCKTWITS_REQUESTS_PER_HOUR`. Replaced the comment above `COIN_SYMBOLS_MEAN_STOCKS` with the brief's exact retirement text. Also generalized three comments the brief's file list didn't name but which broke or went stale as a direct consequence (see "Beyond the brief" below): the bare-tokens rationale for `reddit`, the `looks_like_bot_feed` docstring, and the `REDDIT_MIN_POLL`/`REDDIT_MAX_POLL` comment (was "StockTwits-shaped").
- **`personal_apps/features/radar/sources/stocktwits.py`** -- deleted (`git rm`).
- **`personal_apps/run_radar_ingest.py`** -- deleted `_stocktwits_fetcher` entirely; removed `stocktwits` from the sources import and `STOCKTWITS_REQUESTS_PER_HOUR` from the config import; deleted `_CYCLES_PER_HOUR` and `SYMBOL_BUDGET_PER_CYCLE`; removed `st_client` and the `'stocktwits'` entry from `build_fetchers`. Rewrote the module docstring (it previously hardcoded "Three sources," which was already stale once before when Reddit shipped without updating it -- reworded to not name a count, plus a one-line retirement note). Also generalized two comments inside `_reddit_fetcher`/`record_poll` that explicitly named "the StockTwits path" as a currently-shared mechanism (now false, since nothing shares it).
- **`personal_apps/features/radar/scheduling.py`** -- `interval_for_rate`'s docstring and `retire_untracked`'s docstring re-documented per the brief's exact replacement text.
- **`personal_apps/features/radar/sources/reddit.py`** -- one docstring line ("the scheduler that the StockTwits path already uses") restated generically, since that path no longer exists to share it.
- **`personal_apps/features/radar/profile.py`** -- module docstring's illustrative source list ("StockTwits follows US market hours") swapped to "Reddit follows US market hours" -- it's a still-live illustration of the same design point (per-source diurnal profiles), not a historical citation, so it needed a real, live source.
- **`personal_apps/models.py`** -- one docstring hypothetical ("StockTwits dropping while Reddit keeps working...") swapped to "Bluesky dropping while Reddit..." for the same reason as profile.py: it's describing a live design property using a still-real pair of sources, not a historical fact. Line 660 (`count_stocktwits cannot participate in that`) was judged and left -- see resolution 4 below.

### Tests

- **`personal_apps/tests/test_radar_config.py`** -- appended the brief's two Step-1 tests verbatim. Also fixed two *pre-existing* tests that the config change would otherwise break (not called out in the brief, found by running the file): `test_finance_native_sources_allow_bare_tokens` dropped its `stocktwits` assertion (fourchan only remains); `test_finance_native_sources_keep_them` had no live subject left, so it became `test_a_finance_native_source_can_opt_into_coin_symbols` (monkeypatch-based, mirrors the brief's own extension-point pattern); `test_ordinary_tickers_are_untouched_everywhere`'s source loop swapped `stocktwits` for `reddit`.
- **`personal_apps/tests/test_radar_stocktwits.py`** -- deleted (`git rm`, 11 tests).
- **`personal_apps/tests/test_radar_buckets.py`, `test_radar_bucket_sources.py`, `test_radar_profile.py`, `test_radar_scoring.py`** -- straight data renames (`RadarBucketSource.source` is a free string, no config coupling). Solo/default usages became `'bluesky'`; wherever a test paired two distinct sources and `bluesky` was already the other one, the second role became `'reddit'` (chosen because it's a surviving source, keeping every affected test's story -- two distinct sources, or one "own" vs one "other" -- exactly as before). `test_radar_bucket_sources.py`'s `test_the_parent_bucket_no_longer_has_per_source_columns` (the `count_stocktwits`-is-gone check) was left untouched -- those are genuine historical column names from migrations `7883c6e08708` and `01da83522036`, confirmed by grepping the migrations themselves, not live config. `test_radar_profile.py`'s module docstring got the same Reddit-for-StockTwits swap as `profile.py` itself, for the same reason.
- **`personal_apps/tests/test_radar_daemon.py`** -- two solo `fetchers={'stocktwits': ...}` stubs renamed to `'bluesky'`. Deleted three tests that no longer had a subject: `test_the_request_budget_is_a_sane_fraction_of_the_hourly_one` (tested the deleted `SYMBOL_BUDGET_PER_CYCLE`), `test_a_blocked_source_reports_missing_not_ok` and `test_nothing_due_on_a_healthy_source_is_still_ok` (both tested `daemon._stocktwits_fetcher`'s discovery-failure branch directly -- a mechanism unique to StockTwits' trending-based discovery that no surviving fetcher has an analog of; the general "missing vs ok" distinction they were guarding stays covered at the `ingest.run_cycle` level by the renamed tests in `test_radar_ingest.py`). Also removed the now-dead `_stub_scheduling` helper those two tests were the only callers of. `test_one_source_failing_to_score_does_not_stop_the_others`'s `result['stocktwits']` assertion became `result['fourchan']`.
- **`personal_apps/tests/test_radar_ingest.py`** -- `post()` and `fetcher_for()` default source became `'bluesky'`. Every two-source test (`test_two_sources_ingest_in_one_cycle`, `test_one_source_failing_does_not_stop_the_other`, `test_each_source_keeps_its_own_cursor`, `test_an_unexpected_source_error_does_not_kill_the_cycle`) moved its `stocktwits` role to `'reddit'` (explicit `source='reddit'` on the post, since the default is now `bluesky` and that name was already taken by the paired fixture). `test_the_same_symbol_still_counts_on_a_finance_source` replaced with the brief's exact `test_a_source_can_opt_into_reading_coin_symbols_as_companies`. Beyond the brief: `test_a_single_letter_cashtag_is_refused_on_a_general_network` asserted a finance-native population still reads `$B` as Barnes Group -- with `stocktwits` gone, `SINGLE_LETTER_CASHTAGS` has no source left with `True`, so that half of the test would fail. Split it: the general-network-refuses half stays, and a new `test_a_source_can_opt_into_single_letter_cashtags` (monkeypatch, same shape as the brief's own coin-symbol extension-point test) replaces the finance-population half.
- **`personal_apps/tests/test_radar_journal.py`** -- `test_a_down_sources_mentions_never_reach_the_journal` moved from `stocktwits` to `reddit`, prose and all, exactly as instructed (resolution 3).
- **`personal_apps/tests/test_radar_reddit.py`, `test_radar_scheduling.py`** -- one docstring each restated generically (StockTwits named as a still-shared/still-live mechanism, which is now false): "Reddit reuses the StockTwits poll scheduler" -> "the same poll scheduler every polled source shares"; "must not reach into StockTwits' state" -> "another source's state"; "and StockTwits, whose hot set legitimately empties, never does" -> "a source whose tracked set is a rolling window ... must never call it."

### Frontend

- **`personal_apps/static/radar/src/format.ts`** -- removed `stocktwits: 'StockTwits'` from `SOURCE_LABELS` (resolution 1).
- **`personal_apps/static/radar/src/board/BoardPage.test.tsx`** -- fixture `sources`/`all_sources` moved from `['stocktwits', 'bluesky', 'fourchan']` to `['bluesky', 'fourchan', 'reddit']`. The multi-source URL-encoding test (deselecting 4chan from that array) now asserts `sources=bluesky%2Creddit` instead of `sources=stocktwits%2Cbluesky` -- still a genuine two-source selection, still exercising `%2C` encoding (resolution 2).

## My six resolutions

1. **`format.ts` StockTwits label** -- removed, as instructed.
2. **`BoardPage.test.tsx` fixtures/URL assertions** -- moved to `bluesky`/`fourchan`/`reddit`, multi-source encoding assertion preserved.
3. **`test_radar_journal.py`** -- `stocktwits` -> `reddit`, prose included, behavior unchanged (verified: 9/9 pass).
4. **`models.py:660`** -- judged and **left**. `count_stocktwits` there is a real historical column name (confirmed against migrations `7883c6e08708_add_radar_tables.py` and `01da83522036_add_radar_bucket_sources.py`, which really do add/drop a column with that exact name) explaining why the per-source-rows refactor happened -- not a claim that StockTwits is live. By contrast I found and fixed one nearby case in the *same file* that the brief didn't flag: `models.py:616`'s `RadarBucket` docstring used "StockTwits dropping while Reddit keeps working" as a live illustrative hypothetical (present-tense, not a historical citation) for why status is per-source -- that one I changed to "Bluesky dropping while Reddit keeps working," since it was naming a retired source as if it could still misbehave today.
5. **`source_config_version()`** -- confirmed it moved with no manual edit (`fc1a0ee4cab51d65` -> `8106787f1fa72179`), per the before/after section above.
6. **Staging** -- committed by explicit file name (20 files: 18 modified + 2 deletions), never `git add -A`. Verified `git status` before committing showed exactly those 20 paths and nothing from `discover_telegram_sources.py`, `telegram_candidates.json`, or `reddit_candidates.json`.

## Beyond the brief's file list

The brief's own file list undercounted in three ways I found by grepping more broadly than it did (`grep -rniI stocktwits ... -l` across `*.py *.ts *.tsx *.html`, then re-run case-sensitively for `StockTwits`/`STOCKTWITS` to catch what a lowercase-only pass misses -- which is how `models.py:616` surfaced only on the *second* pass):

- **Pre-existing tests that would break, not just tests that needed renaming.** `test_radar_config.py` had two tests (`test_finance_native_sources_allow_bare_tokens`, `test_finance_native_sources_keep_them`) and `test_radar_ingest.py` had one (`test_a_single_letter_cashtag_is_refused_on_a_general_network`) whose passing state depended on a source with `BARE_TOKENS_ALLOWED`/`COIN_SYMBOLS_MEAN_STOCKS`/`SINGLE_LETTER_CASHTAGS` set `True` -- and after retiring StockTwits, no surviving source has any of those `True` anymore. All three would have failed post-retirement had I only done literal renames. Fixed by monkeypatch-based extension-point tests matching the brief's own pattern for the analogous `test_radar_ingest.py` case.
- **`test_radar_daemon.py` tested the deleted code directly**, not just used `'stocktwits'` as a data string: `test_a_blocked_source_reports_missing_not_ok` and `test_nothing_due_on_a_healthy_source_is_still_ok` called `daemon._stocktwits_fetcher(...)` and referenced `daemon.stocktwits.StockTwitsUnavailable`, both gone after Step 5. `test_the_request_budget_is_a_sane_fraction_of_the_hourly_one` asserted on `daemon.SYMBOL_BUDGET_PER_CYCLE`, also gone. These three were deleted rather than renamed; a plain rename was not available since the functions being tested no longer exist anywhere in the codebase.
- **Stray present-tense prose citing StockTwits as a still-live or still-shared mechanism**, found across files the brief never listed: `config.py` (three spots: the reddit bare-tokens comment, `looks_like_bot_feed`'s docstring, and the `REDDIT_MIN_POLL`/`MAX_POLL` comment -- all said something was "StockTwits-shaped" or "posts to StockTwits" in the present tense), `run_radar_ingest.py` (`_reddit_fetcher`'s docstring and its `record_poll` comment), `features/radar/sources/reddit.py`, `features/radar/profile.py`, `tests/test_radar_reddit.py`, `tests/test_radar_scheduling.py` (two spots), and `models.py:616`. Each of these was restated generically because it made a claim about current pipeline behavior that is now false (a scheduler still being "shared" with a source that no longer exists, bounds still being shaped by a source that's gone, an isolation guarantee stated against a specific still-live rival).

## Left as deliberate historical prose (survivors of the final grep, other than migrations)

These name StockTwits only to describe something that already happened -- a measurement, an incident, or a design trade-off that remains true independent of whether StockTwits currently exists -- and reads correctly as history:

- `config.py:21` -- "Measured on live data ... StockTwits' top mentions were MRNA, DJT, AVGO, IOVA."
- `config.py:64` -- "On StockTwits, $LINK means Interlink" (COIN_COLLISION_SYMBOLS docstring, explains why the frozenset exists; the brief's Step 3 only replaces the comment above `COIN_SYMBOLS_MEAN_STOCKS`, not this one above `COIN_COLLISION_SYMBOLS`).
- `config.py:621` -- `prefer_ipv4_if_configured`'s docstring, "Forcing IPv4 took a StockTwits call from 42.6s to 0.53s" (a specific measured incident).
- `ingest.py:235` / `test_radar_ingest.py:250,301` -- "a missing dependency once took down a whole cycle -- StockTwits and 4chan included" and the duplicate-post story ("A StockTwits message tagged $ZZG and $OTHER..."), both past-tense incident citations.
- `universe.py:29` / `test_radar_universe.py:110` -- "the exclusion has to work on every source rather than only on StockTwits, where an instrument_class field makes it easy" -- explains why name-matching was chosen over a per-source metadata field; the rationale holds regardless of whether StockTwits exists.
- `test_radar_extraction.py:261` -- "the same extractor on StockTwits returned MRNA, DJT and AVGO" (measured, past tense).
- `discover_reddit_sources.py:91` -- a standalone measurement script (same category as the protected `discover_telegram_sources.py`), not part of the live ingest pipeline; its "the way /biz/ and StockTwits are" is a historical analogy baked into that one-off script's own hardcoded policy, not a claim about `features/radar`.
- `models.py:660`, `test_radar_bucket_sources.py:114-116` -- genuine historical column names (`count_stocktwits` etc.), confirmed against the migrations.
- `test_radar_config.py:107,278,288-292,298` and `test_radar_ingest.py:343,416` -- these are the retirement-pin test and the new extension-point tests themselves; naming StockTwits is the entire point (pinning that it's gone, or that the mechanism it used to exercise is still reachable by a future source).
- `run_radar_ingest.py:14` -- my own added sentence, explicitly says "StockTwits was one of these until 2026-08-26."

Never touched: `personal_apps/migrations/versions/01da83522036_add_radar_bucket_sources.py` and `7883c6e08708_add_radar_tables.py` (17 lines of real historical DDL).

## Final grep (verbatim)

```
grep -rn "stocktwits\|StockTwits\|STOCKTWITS" personal_apps/ --include=*.py --include=*.ts --include=*.tsx --include=*.html
```

Produced only: the two migration files, and the deliberate survivors enumerated above. No fetcher, client, budget constant, or source-key reference to StockTwits survives in any live code path or live test assertion. (Also checked `--include=*.md` for completeness beyond the required gate: zero hits.)

## Verification gates

1. **Step 2 red run** -- see above, verbatim, both failures exactly as documented.
2. **`python -m pytest tests/ -k radar -q`** (from `personal_apps/`):
   ```
   2 failed, 594 passed, 2 skipped, 646 deselected, 2 warnings in ~65s
   FAILED tests/test_radar_api.py::test_the_page_embeds_the_board_it_would_otherwise_have_to_fetch
   FAILED tests/test_radar_api.py::test_the_page_falls_back_to_the_default_board_on_a_bad_query
   ```
   Both failures are the documented `ViteManifestError` (no `personal_apps/static/radar/dist/.vite/manifest.json`) -- confirmed by reading the traceback, which names exactly that path. Not fixed, per instruction. The 2 skips are `test_vite_assets.py`'s own skip-if-no-build guards, same root cause, not a new problem. Reran this gate three times across the session (after the config/daemon/ingest fixes, after the stray-comment fixes, and after removing a locally-built `dist/` -- see gate 3) and got the identical `2 failed, 594 passed, 2 skipped` every time. `test_radar_stocktwits.py` confirmed gone from collection (file not found; the only `stocktwits` hit in collection output is the new `test_stocktwits_is_retired`, which is supposed to be there). The brief's "~605 passed" estimate doesn't match 594 exactly: net test-count change is -11 (deleted `test_radar_stocktwits.py`) -3 (three `test_radar_daemon.py` tests with no surviving subject) +2 (Step 1's new config tests) +2 (net from splitting/replacing coin-collision and single-letter-cashtag tests) = -10 versus whatever the brief's author counted at authoring time; not investigated further since the instruction was to confirm *exactly two failures*, which holds.
3. **Frontend.** `npx tsc --version` failed at first (`node_modules` didn't exist at all -- `npm run build` was genuinely unavailable, confirmed rather than assumed). Ran `npm install` (177 packages, 7s, 0 vulnerabilities) to get a real toolchain rather than reporting "unverified." With that: `npx tsc --noEmit` -- clean, no output. `npx vitest run -c vite.radar.config.ts` -- **9 test files, 78 tests, all passed**, including `BoardPage.test.tsx`. Also ran the full `npm run build` (tsc + both vite builds) -- succeeded, producing `static/gym/dist/` and `static/radar/dist/`. Since those `dist/` outputs are gitignored *and* their absence is what gate 2 depends on to reproduce its documented "2 expected failures," I deleted both generated `dist/` directories afterward and reran gate 2 to confirm it still reproduces the documented 2 failures (it does -- see above). `node_modules/` was left in place (harmless, gitignored, doesn't affect `git status` or any Python test).
4. **Circular-import check**, fresh processes from `personal_apps/`: `from features.radar import buckets` / `journal` / `ingest`, plus `import run_radar_ingest as daemon; daemon.build_fetchers()` -- all clean, fetchers keyed exactly `['bluesky', 'fourchan', 'reddit']`.
5. **Final grep** -- see above.

## Concerns

- The brief's own coverage gaps (three broken pre-existing tests, three dead daemon tests, six stray present-tense comments across files it never listed) suggest the brief was written from a narrower grep than this task needed. I applied the same "restate if live, leave if historical" judgment throughout, consistently, but that judgment call is inherently a matter of degree in a couple of spots (`config.py:64`, `universe.py:29` / `test_radar_universe.py:110`) -- reasonable reviewers could prefer those swapped to a live source too. None of them affect behavior; they're all comments/docstrings.
- `npm install` populated `personal_apps/node_modules/` on this machine as a side effect of getting real (not assumed) frontend verification. It's gitignored and `git status` shows nothing, but it's a filesystem change outside the commit; flagging it in case a later task expects a pristine `node_modules`-free checkout.

## Task 7 fix round 1/5

Commit: `3b74f32c1a7e6bc8612a53cb3f7fdd598ab2b94e` on
`codex/radar-pipeline-audit`

### Scope

- `personal_apps/tests/test_radar_ingest.py` adds the missing healthy-empty
  `run_cycle` regression: `FetchResult(posts=[], status='ok')` stays `ok` and
  creates no post, mention, bucket, bucket-source, mention-event, or cursor
  artifact.
- The suite now owns the exact `ZZG`, `zz_task7_ingest`, `bluesky`, and
  `reddit` fixtures; cleanup no longer deletes broad `ZZ%` rows or every
  source cursor.
- The coin-symbol opt-in regression now drives `ingest._extract_for` with
  `$LINK`, a complete lookup entry, and a monkeypatched source opt-in. It
  asserts `[('LINK', 'high')]`, so it exercises ingest's consumer rather than
  the config helper directly.
- No production code changed. The review's Minor retirement-map assertion was
  intentionally deferred as required by this round's scope.

### Required teeth evidence

1. Temporarily mutated `ingest.run_cycle` so an empty `ok` result was recorded
   as `missing`, then ran:

   ```
   python -m pytest tests/test_radar_ingest.py -v -k "empty_healthy_source_stays_ok or source_can_opt_into_reading_coin_symbols"
   ```

   `test_an_empty_healthy_source_stays_ok_without_database_artifacts` failed
   exactly at the status assertion: `{'bluesky': 'missing'}` rather than
   `{'bluesky': 'ok'}`.

2. In the same temporary mutation pass, changed ingest's coin filter to ignore
   the raw post source and use the non-opted-in `fourchan` policy. The focused
   test `test_a_source_can_opt_into_reading_coin_symbols_as_companies` failed
   exactly at the extraction assertion: `[]` rather than `[('LINK', 'high')]`.

Both production mutations were restored before the final verification and
before committing.

### Verification

```text
python -m pytest tests/test_radar_ingest.py tests/test_radar_daemon.py -q
59 passed in 15.43s
```

After the run, exact owned-artifact checks returned `0` for
`zz_task7_ingest` posts, `ZZG` buckets and mention events, and `bluesky`/
`reddit` cursors. `git diff --check` was clean. The two known manifest API
failures were not run or changed.

### Commit contents

Only `personal_apps/tests/test_radar_ingest.py` was staged and committed:

```text
3b74f32 test(radar): pin healthy empty source results
1 file changed, 41 insertions(+), 15 deletions(-)
```

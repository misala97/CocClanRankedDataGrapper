# Task 9 independent review — per-subreddit source names

Reviewer: independent (did not write this code)
Worktree: `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-pipeline-audit`
Branch: `codex/radar-pipeline-audit`, HEAD `dedc90b`
Review package: `.superpowers/sdd/review-cf15344..dedc90b.diff`
Date: 2026-08-27

**VERDICT: NOT APPROVED** — 2 Critical, 2 Important, 6 Minor.

The mechanical work is good and the teeth are real: I re-verified all ten of the
implementer's claimed mutations myself and every one of them failed exactly as
reported. What the implementation does *inside* a cycle is correct. What it
does at the two edges of the split — the cycle where Reddit is not read at all,
and the history written under the old name — is not.

---

## Spec compliance

### Brief steps

| # | Requirement | Verdict |
|---|---|---|
| 1 | `test_a_prefixed_source_inherits_its_roots_policy` appended to `test_radar_config.py` | ✅ present verbatim (`tests/test_radar_config.py:207`) |
| 2 | RED evidence before implementation | ✅ documented in the WIP report; not independently re-observable post-commit |
| 3 | `config.source_root` + all five per-source helpers routed through it | ✅ `config.py:112,135,277,282,288,313` — all five re-verified by mutation |
| 4 | Widen `RadarBucketSource.source` and `RadarPollState.source` to 48; migration | ✅ plus `RadarPost.source` per hardening #2 |
| 5 | Reddit emits `source='reddit:<sub>'`; `FetchResult.per_source_status` | ✅ `sources/reddit.py:132,254`; `sources/__init__.py:42` |
| 6 | Poll state stays keyed by root `reddit` + the note | ✅ `run_radar_ingest.py:113-118,119` |
| 7 | API accepts prefixed roots, expands board/detail, restores viewer selection | ✅ `routes/api.py:58,168,174,276` |
| 8 | Suites run | ✅ `2 failed, 606 passed, 2 skipped` — only the two known Vite-manifest failures |
| 9 | Commit by exact path | ✅ `dedc90b`, 13 files, protected files untouched |

### Controller hardening corrections

| # | Requirement | Verdict |
|---|---|---|
| 1 | Chain from `1d26ac48e744`, single head | ✅ `down_revision = '1d26ac48e744'`; `flask db heads` = one head |
| 2 | Widen all three durable writers; downgrade normalizes `radar_posts`; report states the semantic rollback limit | ✅ for the columns and the report. ⚠️ the *migration file itself* claims only the collision safety and says nothing about what it cannot restore (Minor 8); the `radar_bucket_sources` narrowing has an undocumented width dependency (Minor 7) |
| 3 | **Never write an aggregate zero child named `reddit`** | ❌ **VIOLATED** — see Critical 1. The path that does it is not the one the brief warned about (`statuses[source] = result.status` in ingest, which was correctly avoided); it is the Reddit fetcher's own "nothing due" branch, which returns no `per_source_status` at all and so lands on ingest's root fallback |
| 4 | One shared expansion helper used by both API and daemon scoring; fetcher keys and cursors rooted | ✅ `config.expand_sources` is the single source of truth; cursor rooting re-verified |
| 5 | Real config-version bump via a documented name-generation input | ✅ `SOURCE_NAME_GENERATION = 2` (`config.py:183`), stamp is `705b043693b533db` and moves with the generation (verified live) |

### Required behavioral tests

| Requirement | Verdict |
|---|---|
| Two subs, one `ok` one `truncated`, own rows only, no root child | ✅ `test_reddit_subreddits_write_only_their_own_status_rows` |
| One successful + one missing/throttled, successful posts survive | ✅ `test_a_successful_subreddit_survives_a_missing_aggregate_status`, and re-proved end-to-end through a real `reddit.fetch` |
| Longest prefixed name insertable; model + live widths 48 ×3 | ✅ `test_all_three_prefixed_source_columns_are_wide_in_model_and_database` |
| Root expands for board + detail, serializes the root; concrete accepted, unknown root rejected | ✅ four tests in `test_radar_api.py` |
| Daemon scoring calls concrete names, never the root | ✅ `test_scoring_covers_every_configured_source` (`assert 'reddit' not in seen`) |
| Source-name generation changes `source_config_version()` | ✅ |
| Poll state and cursor stay rooted | ✅ `test_reddit_poll_state_stays_keyed_to_the_root_source`; cursor via `assert 'reddit:wallstreetbets' not in cursors` |
| Every absence-shaped assertion observed failing under mutation | ✅ 10 of 10 re-verified by me (table below) |
| Exact `ZZ`-owned fixtures, no broad prefix deletion | ✅ for every fixture this diff adds or touches |

### Anything extra the brief did not ask for

Nothing gratuitous. `expand_sources` came from the brief, `SOURCE_NAME_GENERATION`
from hardening #5, the extra
`test_every_policy_lookup_uses_the_prefixed_sources_root` is justified coverage
for the three helpers the brief's single test could not distinguish.

**But** two *behavioral* consequences ship that the brief never asked for and no
test constrains: the meaning of a "venue" and the labels the detail panel
renders (Important 3 and Important 4).

---

## Risk-area audit

### 1. Historical root-`reddit` rows — **LOST**

What I did: read `config.expand_sources` and every read path that consumes it,
then ran a probe against the real dev MySQL database with an owned `ZZR9`
fixture, inserting a bucket-source row with `source='reddit'` (exactly the shape
production already holds — the brief itself cites 4372 truncated + 478 ok root
Reddit bucket rows in production) and asking the board's own helpers whether
they can see it.

```
expand_sources(['reddit']) = ['reddit:wallstreetbets', ... 8 names ...]
root 'reddit' in expansion: False
hour visible under expansion       : False
hour visible when root is included : True
bucket rows matched by expansion   : 0
bucket rows matched incl. root     : 1
hourly counts under expansion      : {}
```

The expansion does **not** include the root. Every stored Reddit observation
written before this deploy becomes invisible to:

- `leaderboard.build_rows` → `bucket.source.in_(sources)` (`leaderboard.py:141`)
- `board._covered_hours`, `_hourly_counts`, `_triplets` (`board.py:128,145,187`)
- `board._tones` → `RadarPost.source.in_(sources)` (`board.py:251`)
- `detail.daily_counts`, `first_watched_day`, `intraday_counts`,
  `_watched_from_index` (`detail.py:91,111,177,200`)
- `detail_panel.window_figures`, `_posts`, `breakdown_for`
  (`detail_panel.py:95,109,130`)
- `journal.distinct_voices` (`journal.py:198`)
- `run_radar_ingest.score_all` (by design, per hardening #4)

Verdict: **regression, Critical.** Two distinct harms, and the second is the one
that breaks the standing rule:

1. **Reddit-only selection.** All pre-deploy Reddit history disappears. It reads
   as null rather than zero (`_covered_hours` and `first_watched_day` are also
   filtered), so it is *honest* — but it is a permanent, silent erasure of data
   that is still sitting in the table, across chart spans up to 3Y, on a table
   the code documents as "retained forever ... what lets the chart's long spans
   fill in over time".
2. **Any mixed selection, including the default.** Bluesky and 4chan satisfy
   `_covered_hours` and `first_watched_day` for the same hours and days, so the
   hour/day is marked *measured* and the pooled count is rendered as a real
   number with Reddit's contribution simply absent from the sum. That is an
   unobserved population presented as a measured total — an absence rendered as
   a zero, in the exact shape this audit exists to eliminate. On the 1Y detail
   chart it is permanent, not transitional.

I do not think the fix is simply to append the root to `expand_sources`: the
old root rows carry the old `source_config_version`, and re-admitting them to
the *scored* paths (`leaderboard`, `_triplets`, `pooled_z`) would mix baseline
populations, which is what the stamp bump exists to prevent. The two families of
read need to be told apart:

- **raw-count reads** (`daily_counts`, `intraday_counts`, `_hourly_counts`,
  `_tones`, `breakdown_for`, `_posts`, `distinct_voices`) have no stamp
  dependency and should see the historical root rows;
- **scored reads** should keep excluding them, and `score_all` should still call
  `invalidate_incompatible_scores` for the root population so those rows' stale
  `mention_z` is NULLed rather than left indefinitely readable (Minor 10).

Either way this is a decision that must be made explicitly and written down, not
arrived at by an expansion helper that silently omits the root.

### 2. Partial success preservation — **correct**

What I did: (a) re-read `ingest.run_cycle`; (b) mutated the gate back to
`if result.status == 'missing': continue` and watched the covering test fail;
(c) mutated `statuses[source] = result.status` back in beside the concrete
statuses and watched the no-root-row test fail; (d) built an end-to-end probe
that drives a **real** `reddit.fetch` with sub A succeeding and sub B raising
`RedditUnavailable`, then feeds the genuine `FetchResult` through
`ingest.run_cycle` into `buckets.roll_up` against the live database.

```
asked              : ['pennystocks', 'wallstreetbets']
aggregate status   : truncated
per_source_status  : {'reddit:pennystocks': 'ok', 'reddit:wallstreetbets': 'missing'}
posts              : ['reddit:pennystocks']
cycle per_source   : {'reddit:pennystocks': 'ok', 'reddit:wallstreetbets': 'missing'}
posts_new          : 1 mentions 1
bucket child rows  : {'reddit:pennystocks': ('ok', 1)}
root 'reddit' child: False
stored post source : ['reddit:pennystocks']
```

The earlier sub's post survives, its status is `ok`, the failing sub records
`missing` — no row at all rather than a zero — and no aggregate root key is
injected. `_roll_up` still reports `truncated` for the cycle and that aggregate
is correctly kept out of the status map handed to the rollup.

`result.per_source_status or {source: result.status}` is the right fallback for
genuinely single-name sources (bluesky, fourchan). Verdict: **correct** —
except that the same fallback is what Critical 1 rides in on.

### 3. The migration — **mostly sound, two documentation/robustness gaps**

- **Is 48 sufficient?** Computed, not trusted. Longest configured sub is
  `smallstreetbets` (15), so the longest name is `reddit:smallstreetbets` = **22
  characters**. 48 leaves 26 characters of headroom — enough for the 20-character
  `RobinHoodPennyStocks` the `RadarPollState.symbol` comment cites (27 total).
  ✅
- **Model/migration agreement.** `RadarPost.source` 16→48, `RadarBucketSource.source`
  24→48, `RadarPollState.source` 24→48 in both. ✅ `radar_source_cursors.source`
  correctly left at 24 (root-only). `radar_mention_events.source` was already 48.
- **Live DB.** Verified via `information_schema`:
  `radar_posts` 48, `radar_bucket_sources` 48, `radar_poll_state` 48, all
  `NOT NULL`, all `utf8mb4 / utf8mb4_general_ci` — i.e. the `MODIFY COLUMN`
  did **not** silently drop a collation (it matches the untouched
  `radar_source_cursors.source`). ✅
- **MySQL 8 / MariaDB.** Three plain `MODIFY COLUMN ... VARCHAR(n) NOT NULL`
  and one plain `UPDATE ... WHERE source LIKE 'reddit:%'`. No `CAST(... AS JSON)`,
  no MySQL-8-only syntax. Both engines accept every statement. ✅
- **DDL-commits-on-partial-failure.** `upgrade()` is three independent widenings
  and is **idempotent**: a retry re-issues `MODIFY VARCHAR(48)` on an
  already-48 column, which is a no-op, so a half-applied upgrade retries
  cleanly. `downgrade()` is likewise re-runnable — the `UPDATE` is idempotent
  and each narrowing re-narrows harmlessly. ✅ Judged safe against the hazard.
- **Downgrade normalization.** The `UPDATE radar_posts SET source='reddit'`
  cannot collide on `uq_radar_post_source_ext`. The migration justifies this
  with "Atom comment IDs are globally unique"; the *actual* guarantee is
  stronger and lives in `ingest._store_mentioning_posts:113`, which dedups on
  `external_id` **alone**, so the same comment can never exist under two source
  names in the first place. Conclusion holds. ✅
- **Downgrade honesty.** ❌ Minor. The migration narrows
  `radar_bucket_sources.source` 48→24 with no normalization; it succeeds today
  only because 22 ≤ 24, an undocumented dependency on `REDDIT_SUBS` membership
  (Minor 7). And the file says nothing about the per-subreddit bucket history it
  cannot re-aggregate — a reader of the migration alone would think the
  rollback lossless (Minor 8). The *report* states this correctly; the artifact
  an operator actually reads at 03:00 does not.
- **DB end state.** `flask db current` = `flask db heads` = `08316d3e4d77 (head)`,
  single head, all three widths 48. I ran **no** downgrade. ✅

### 4. Root vs concrete boundaries — **drawn consistently**

Rooted (verified): `RadarSourceCursor` via `_since_for(source)` / `_advance_cursor(source, ...)`
with the fetcher key `'reddit'`; `RadarPollState` via `ensure_tracked('reddit', ...)`,
`retire_untracked('reddit', ...)`, `due_symbols('reddit', ...)`,
`record_poll('reddit', sub, ...)`; the fetcher dict key itself; `all_sources`
in the payload; `SOURCES` membership validation.

Concrete (verified): `RawPost.source`, `RadarMentionEvent.source`,
`RadarBucketSource.source`, the status map into `buckets.roll_up`, daemon
scoring, board/detail query expansion.

I mutated `record_poll('reddit', ...)` → `record_poll('reddit:%s' % sub, ...)`
and the poll-state test failed with an extra `('reddit:zz_task9_sub', ...)` row,
so the rooting is genuinely pinned. No place mixes the two. ✅

The only leak of the root into the concrete side is Critical 1.

### 5. `source_config_version()` — **correct call, correctly implemented**

Verified live rather than from the report:

```
stamp now   : 705b043693b533db      (matches the claim)
stamp gen=1 : 1b93049ef4bd6f30      (moves with SOURCE_NAME_GENERATION)
back        : 705b043693b533db
```

`SOURCES` and `REDDIT_SUBS` membership are genuinely unchanged, so without the
new input the stamp would not have moved. It is the right call under the stated
rule: the stamp moves for changes to *which* mentions get counted, and a bucket
counted as "all of Reddit" and a bucket counted as "r/pennystocks" are different
populations that must not share one baseline. It is a population change, not a
scoring change. The comment on the `reddit_subs` input was correctly rewritten
rather than left saying something now false. `ROLLUP_GENERATION` was not
overloaded. ✅

### 6. Policy rooting — **5 of 5 re-verified, not taken on trust**

Every one of the five was mutated by me to consult the raw prefixed name, the
covering test watched failing, and reverted. Full table in the Teeth audit
below. The choice to root rather than split is correct and the docstring argues
it well: an unlisted sub inheriting `low` bare-token confidence would silently
disable the one signal Reddit depends on. ✅

### 7. API surface — **safe, with two rough edges**

- **Injection.** `parse_query` validates `source_root(s) in SOURCES`, then the
  value flows into SQLAlchemy `.in_(...)`, which binds parameters. No string
  interpolation anywhere on the path. Not injectable. ✅
- **Unvalidated string into a query.** An attacker-shaped
  `?sources=reddit:<anything>` *does* reach the query as a literal — but only as
  a bound parameter that matches nothing. Harmless in itself. What is new is
  that the *count* of accepted sources is no longer bounded by `len(SOURCES)`
  (Minor 5).
- **Malformed input.** `?sources=` → falls to the default; `?sources=,,,` →
  stripped to empty → default; `?sources=:` → `source_root(':') == ''` → rejected
  400; `?sources=notreddit:wsb` → rejected 400 (test-covered). ✅
- **Root restoration.** `board.sources = list(query.sources)` runs *before*
  `serialize(board)`; I removed it and the covering test failed with eight
  concrete names in the payload. ✅
- **Concrete names still reaching the response.** `payload.rows[].sources`,
  `payload.breakdown.venues[].source` and `payload.posts[].source` all carry
  concrete names. Rows' `sources` is only counted, never displayed — but the
  detail panel's venue table and post badges render theirs through
  `sourceLabel()`, which falls back to the raw key (Important 4).

---

## Teeth audit

All ten applied by me, failure observed, reverted immediately, and
`git status --short` confirmed clean after each.

| # | Assertion under test | Mutation | Exact failure | Reverted |
|---|---|---|---|---|
| 1 | `bare_tokens_allowed('reddit:wallstreetbets') is True` | `BARE_TOKENS_ALLOWED.get(source, False)` | `AssertionError: assert False is True` — `bare_tokens_allowed('reddit:wallstreetbets')` | ✓ |
| 2 | `source_kind('reddit:wallstreetbets') == 'broadcast'` | `SOURCE_KIND.get(source, 'forum')` | `AssertionError` at `test_radar_config.py:239`, got `forum` | ✓ |
| 3 | `coin_collision_dropped('reddit:wallstreetbets','LINK') is False` | `COIN_SYMBOLS_MEAN_STOCKS.get(source, False)` | `AssertionError` at `test_radar_config.py:242` | ✓ |
| 4 | `single_letter_cashtags_allowed('reddit:wallstreetbets') is True` | `SINGLE_LETTER_CASHTAGS.get(source, False)` | `AssertionError` at `test_radar_config.py:240` | ✓ |
| 5 | `bare_token_confidence('reddit:pennystocks') == 'high'` | `BARE_TOKEN_CONFIDENCE.get(source, 'low')` | `AssertionError` at `test_radar_config.py:228` | ✓ |
| 6 | **absence-shaped** — successful sub not discarded by a `missing` aggregate | gate reverted to `if result.status == 'missing': continue` | `assert 0 == 1` on `result['posts_new']` | ✓ |
| 7 | **absence-shaped** — no root `reddit` child row | `statuses[source] = result.status` re-added after `statuses.update(...)` | `Left contains 1 more item: {'reddit': 'truncated'}` | ✓ |
| 8 | **absence-shaped** — daemon never scores the root | `for source in SOURCES:` | expected concrete names absent, root present | ✓ |
| 9 | viewer's root selection restored before serialization | `board.sources = list(query.sources)` removed | `payload['sources']` was eight concrete names | ✓ |
| 10 | poll state stays rooted | `record_poll('reddit:%s' % sub, ...)` | `Left contains one more item: ('reddit:zz_task9_sub', 'zz_task9_sub')` | ✓ |

Every one of the implementer's ten claims reproduced. No claimed teeth turned
out to be toothless.

---

## Gates

| Gate | Command | Result |
|---|---|---|
| Full radar suite | `python -m pytest tests/ -k radar -q` (from `personal_apps/`) | `2 failed, 606 passed, 2 skipped, 646 deselected, 2 warnings in 59.32s` — the two failures are exactly `test_the_page_embeds_the_board_it_would_otherwise_have_to_fetch` and `test_the_page_falls_back_to_the_default_board_on_a_bad_query`, both `ViteManifestError: No Vite manifest at ...\static\radar\dist\.vite\manifest.json`. **No third failure.** Not fixed, per instruction. ✅ |
| Alembic current | `python -m flask db current` | `08316d3e4d77 (head)` ✅ |
| Alembic heads | `python -m flask db heads` | `08316d3e4d77 (head)` — single head ✅ |
| Live widths | `information_schema.COLUMNS` | `radar_posts` 48, `radar_bucket_sources` 48, `radar_poll_state` 48, all NOT NULL, utf8mb4/utf8mb4_general_ci ✅ |
| Fresh-process imports | 4 separate `python -c` runs from `personal_apps/` | `from features.radar import buckets` OK; `... journal` OK; `... ingest` OK; `from run_radar_ingest import build_fetchers` OK. The deliberate `buckets`↔`journal` circular import is undisturbed ✅ |

Other checks:

- **Naive UTC.** No `utcnow()` introduced; every new datetime literal is naive. ✅
- **`int()`/`float()` at the query boundary.** The diff adds no aggregate query,
  so no new `Decimal` reaches float maths or `jsonify`. ✅
- **SQL NULL vs Python None.** The only new SQL predicate is
  `WHERE source LIKE 'reddit:%'` on a `NOT NULL` column. ✅
- **Protected files.** `git show --stat dedc90b` contains no
  `discover_telegram_sources.py`, no `telegram_candidates.json`, no
  `reddit_candidates.json`. ✅
- **Shared-DB isolation, new/touched fixtures.** All exact-identity:
  `test_radar_reddit.py` deletes on `(external_id='zz-task9-longest-source',
  channel='zz_task9_source_width')`; `test_radar_daemon.py` deletes on
  `source IN ('reddit','reddit:zz_task9_sub') AND symbol='zz_task9_sub'` and —
  importantly — stubs `scheduling.retire_untracked` to `0`, without which
  `retire_untracked('reddit', ('zz_task9_sub',))` would have deleted all 18 real
  poll-state rows from the shared database; `test_radar_ingest.TEST_SOURCES` was
  correctly widened so cursor cleanup still covers the new name. **No broad
  `LIKE 'ZZ%'` teardown is added by this diff** (verified against
  `git diff cf15344..dedc90b`). ✅

---

## Findings

### CRITICAL 1 — a Reddit cycle with nothing due writes a zero-count root `reddit` bucket row

`personal_apps/run_radar_ingest.py:138`

```python
        subs = scheduling.due_symbols('reddit', now, limit=REDDIT_SUBS_PER_CYCLE)
        if not subs:
            return FetchResult(posts=[], status='ok')       # no per_source_status
```

With no `per_source_status`, `ingest.run_cycle:246` falls back to
`{source: result.status}` = `{'reddit': 'ok'}`, `'ok'` is in
`buckets._COUNTABLE`, and `buckets.roll_up:196` writes a child row for **every**
countable source in every touched bucket — including sources that contributed
nothing.

Proved against the live database with an owned `ZZPRB` fixture, driving
`ingest.run_cycle` with exactly the `FetchResult` this branch returns:

```
per_source : {'bluesky': 'ok', 'reddit': 'ok'}
bucket child rows (source -> status, mentions, authors):
    bluesky -> ('ok', 1, 1)
    reddit  -> ('ok', 0, 0)          <-- root, zero, status 'ok'
ROOT 'reddit' zero child written: True
bucket.sources_ok : 2                <-- claims two sources observed; one did
```

This is hardening requirement #3 violated verbatim ("Never write an aggregate
zero child named `reddit`"), and it is the standing rule violated: Reddit was
not read at all this cycle and a zero observation is recorded under a name no
fetch produced. It is not an edge case — the code's own comment three lines
above says the "nothing due" branch is the common path ("six of eight cycles
returned nothing at all"), so in production this fires on most cycles and
writes a zero root child into every bucket any source touched. Those rows are
then invisible to the board (Critical 2 excludes the root from every read),
never scored, never invalidated: pure durable pollution that also inflates
`RadarBucket.sources_ok`.

**Fix.** The not-due branch must report concrete names or none at all. The
closest-to-old-semantics form is

```python
        if not subs:
            return FetchResult(
                posts=[], status='ok',
                per_source_status={'reddit:%s' % sub: 'ok' for sub in REDDIT_SUBS})
```

but note this writes eight zero children per bucket instead of one, and it
claims coverage for subs whose own poll interval may not actually span the
bucket. The more honest form restricts the map to the subs whose
`last_polled_at` covers the touched window. Either is acceptable; leaving the
root fallback in place is not. Add a regression that runs `run_cycle` with a
`FetchResult(posts=[], status='ok', per_source_status={})` under the key
`'reddit'` alongside a producing source and asserts no `source='reddit'` child
row exists — and mutate it to confirm it has teeth.

### CRITICAL 2 — `expand_sources` drops the root, so every pre-deploy Reddit row disappears from the board and the charts

`personal_apps/features/radar/config.py:372-384`

```python
    for name in names:
        if name == 'reddit':
            out.extend('reddit:%s' % sub for sub in REDDIT_SUBS)   # root not included
```

Evidence and the full list of affected read paths are in Risk-area 1 above. The
harm that makes this Critical rather than a documented discontinuity is the
mixed-selection case: `_covered_hours` (`board.py:128`) and `first_watched_day`
(`detail.py:111`) are satisfied by Bluesky/4chan for the same hours and days, so
those slots are marked *measured* and the pooled count is drawn as a real number
with Reddit's real, still-stored contribution silently missing from the sum. On
the detail chart (`DEFAULT_SPAN = '1Y'`, buckets "retained forever") that is
permanent, not a 24-hour transition.

**Fix.** Decide explicitly and write it down. My recommendation: split the
expansion into two helpers with different jobs —

```python
def expand_sources(names):            # scored reads + daemon scoring: concrete only
    ...

def expand_sources_for_history(names):  # raw-count reads: concrete PLUS the root
    out = expand_sources(names)
    return out + ['reddit'] if 'reddit' in names else out
```

and use the history form in `detail.daily_counts` / `intraday_counts` /
`first_watched_day` / `_watched_from_index`, `board._hourly_counts` /
`_covered_hours` / `_tones`, `detail_panel.breakdown_for` / `_posts`, and
`journal.distinct_voices`; keep the strict form in `leaderboard.build_rows`,
`board._triplets`, `scoring.pooled_z` / `window_z`, and `score_all`. Whatever is
chosen, it needs a test that inserts an owned root-`reddit` bucket row and
asserts what each family of read does with it — with the assertion observed
failing under mutation, because "the historical row is visible" is an
absence-shaped claim.

If the ruling instead is that the loss is accepted, that must be stated in the
report as a deliberate data-visibility cut with its scope (1Y detail chart, 24h
board series, tone, breakdown, post list, distinct voices) rather than left as
an unremarked property of a helper.

### IMPORTANT 3 — two subreddits now read as two independent venues

`personal_apps/features/radar/leaderboard.py:231,263,285`,
`personal_apps/features/radar/board.py:289,296`,
`personal_apps/features/radar/phrasing.py:102`

`contributing = sorted({part.source for part in parts})` is now per-subreddit, so
`len(row.sources)` counts subreddits. Consequences, none of them requested by the
brief and none covered by a test:

- the **min-venues breadth filter** (`min_venues=2`, the reader's "more than one
  venue is talking" control) now passes a ticker mentioned in r/wallstreetbets
  and r/pennystocks and nowhere else;
- `venue_counts['multi']` — the number on that control's label — inflates the
  same way;
- the **`single-source` mark** inverts: with a Reddit-only chip selection,
  `len(sources)` used to be `1` so the mark was suppressed; it is now `8`, so a
  ticker from one subreddit is marked "Only one of the selected sources
  contributed" (`format.ts:98-100`);
- `phrasing` prints "3 venues" and "across N venues" counting subreddits.

The UI copy the mark carries — "The same reading from two independent sources is
much stronger evidence" — is now false for the Reddit case. Two subreddits share
a platform, a user population and a rate-limit budget; they are not two
independent venues in the sense the corroboration signal means.

**Fix.** Count venues by root: `len({source_root(s) for s in row.sources})` at
`board.py:289,296`, `leaderboard.py:263,285` and `phrasing.py:102`, or store a
`venues` count on `Row` derived from the root set at `leaderboard.py:231` while
leaving `sources` concrete for the breakdown. Add a test that a ticker seen in
two subreddits and nowhere else does **not** clear `min_venues=2`.

### IMPORTANT 4 — the detail panel renders raw internal source names

`personal_apps/features/radar/routes/api.py:229,244` →
`personal_apps/static/radar/src/format.ts:63` →
`Breakdown.tsx:48`, `Posts.tsx:37`

`breakdown.venues[].source` and `posts[].source` now carry
`reddit:wallstreetbets`. `sourceLabel()` falls back to the raw key for anything
it does not know, so the venue table and each post badge print
`reddit:wallstreetbets` next to `Bluesky` and `4chan /biz/`. The venue table
also fragments Reddit into up to eight rows, each with its own `voices` count
and its own share-of-mentions percentage, where it previously showed one pooled
`Reddit` row.

Showing the subreddit may well be *desirable* — but it should be a deliberate
presentation decision with a label (`r/wallstreetbets`), not a raw key leaking
through a fallback. No frontend test covers it and `BoardPage.test.tsx` still
uses only root names.

**Fix.** Either root the label in `sourceLabel` (`SOURCE_LABELS[key] ?? root
label ?? key`) or teach it the prefix form: `if (key.startsWith('reddit:'))
return 'r/' + key.slice(7)`. Add a `format.test.ts` case.

### MINOR 5 — `sources=` is no longer bounded in cardinality

`personal_apps/features/radar/routes/api.py:56-59`

`source_root(s) in SOURCES` accepts `reddit:<anything>`, and nothing caps how
many comma-separated entries the parameter may carry. Before this change the
membership check bounded the list to three values. A logged-in caller can now
send tens of thousands of distinct `reddit:*` names, each of which lands in six
or more `IN (...)` clauses against the partitioned `radar_bucket_sources`
(~300k rows). Login-gated on a three-account instance, so this is a robustness
nit rather than a security hole.

**Fix.** Cap the selection (`if len(selected) > len(SOURCES) + len(REDDIT_SUBS):
raise BadQuery('too many sources')`) or validate concrete names against the
configured set rather than only their root.

### MINOR 6 — a concrete-subreddit link lights no chip

`personal_apps/features/radar/routes/api.py:174`

`?sources=reddit:wallstreetbets` serializes `sources: ['reddit:wallstreetbets']`
against `all_sources: ['bluesky','fourchan','reddit']`, so `Controls.tsx:41`
finds no match and renders every chip off — a state the control otherwise
forbids (`if (on && selection.sources.length === 1) return`). The first chip
click then silently discards the concrete selection. The brief anticipates this
link shape ("a link may name one subreddit"), so it deserves a defined
appearance.

**Fix.** Light the root chip while keeping the concrete filter:
`board.sources = sorted({source_root(s) for s in query.sources})`, or send both
the raw selection and a `selected_roots` field for the control.

### MINOR 7 — the downgrade's `radar_bucket_sources` narrowing has an undocumented width dependency

`personal_apps/migrations/versions/08316d3e4d77_widen_radar_source_columns.py:36-38`

`radar_posts` is normalized before narrowing; `radar_bucket_sources` is narrowed
48→24 with no normalization and no guard. It succeeds today only because the
longest configured name is 22 characters. Adding a subreddit whose name exceeds
17 characters — the model's own comment cites `RobinHoodPennyStocks`, which
would give a 27-character source — makes the downgrade fail with MySQL 1406
midway through, after the `radar_poll_state` DDL has already auto-committed.

**Fix.** State the dependency in a comment, and either delete prefixed
`radar_bucket_sources` rows (they cannot be re-aggregated anyway, per the
report's own rollback boundary) or raise a clear error if any exceed 24.

### MINOR 8 — the migration file does not state what the downgrade cannot restore

Same file. The report documents the semantic rollback limit well; the migration
itself carries only the collision-safety note, so an operator reading the
artifact in front of them would reasonably conclude the downgrade is lossless.

**Fix.** Move the report's rollback-boundary paragraph into the `downgrade()`
docstring.

### MINOR 9 — `RadarBucket.sources_ok` now counts concrete names

`personal_apps/features/radar/buckets.py:149`

"How many sources were ok" now means "how many source names were ok", which
rises with `REDDIT_SUBS_PER_CYCLE` and — while Critical 1 stands — counts the
phantom root. The column is currently write-only outside tests, so nothing
misreads it today; the drift is worth a comment or a rooted count before
something starts reading it.

### MINOR 10 — historical root Reddit buckets are never re-invalidated

`personal_apps/run_radar_ingest.py:227` / `features/radar/scoring.py:113`

`score_all` no longer calls `score_source('reddit', ...)`, so
`invalidate_incompatible_scores(version, since, source='reddit')` never runs for
the root population and those rows keep a `mention_z` computed under stamp
`8106787f1fa72179` indefinitely. Partly mitigated by the unscoped
`invalidate_incompatible_scores(source_config_version(), since)` at daemon start
(`run_radar_ingest.py:525`), which covers the bootstrap window only. Harmless
while Critical 2 keeps those rows unreadable; it becomes load-bearing the moment
the root is re-admitted to any scored read.

---

## Pre-existing, NOT a Task 9 finding

`personal_apps/tests/test_radar_daemon.py:550,573,593,615` use broad
`RadarBucketSource.ticker.like('ZZ%')` teardowns. Verified by
`git diff cf15344..dedc90b` that this diff adds none of them; `git log -L`
attributes them to `7791963 fix(radar): start corrected rollups as a new
baseline generation`. Flagged only because the controller notes this class of
defect has been caught three times on this branch — it is still live in the file
this task touched, and worth a separate cleanup.

Also pre-existing: `test_radar_ingest._wipe` deletes `RadarSourceCursor` rows
for the real `bluesky` and `reddit` sources on every run. The dev DB currently
holds zero cursor rows so nothing is at risk locally, but it is a shared-DB
teardown that reaches beyond owned fixtures.

---

## ⚠️ Cannot verify from diff

- **Production root-`reddit` row counts.** The local dev DB holds
  `radar_posts` / `radar_bucket_sources` / `radar_mention_events` rows for
  `bluesky` and `fourchan` only — **no** root `reddit` rows at all
  (`radar_poll_state` has 18 rooted `reddit` rows). Critical 2's *mechanism* is
  proved with an inserted owned fixture; its *blast radius* depends on how much
  root Reddit history production actually holds. The brief cites 4372 truncated
  + 478 ok root Reddit bucket rows in production, which is where the number
  should come from.
- **Real-world 429/throttle ordering.** The throttle path is exercised only
  through `FakeClient`; I could not observe a live Reddit 429 splitting a
  multi-sub cycle.
- **MariaDB.** Every statement was executed against local MySQL 8 only. The
  statements are engine-neutral by inspection, but the production `MODIFY
  COLUMN` on the partitioned `radar_bucket_sources` has not been run on MariaDB.
- **The downgrade.** Not run by me, per instruction. I am relying on the
  report's account of the round trip and on the end state I did verify (single
  head, 48/48/48).
- **Frontend behaviour.** Important 3 and 4 are read from the TSX source and the
  serializer; I did not build the island (the Vite manifest is absent, which is
  what the two expected test failures are about) or view the rendered page.

---

## Verdict

**NOT APPROVED.**

Critical 1 must be fixed before this merges: it writes a zero into the durable
store for a source that was not read, on the majority of cycles, under exactly
the name hardening requirement #3 forbade.

Critical 2 needs a ruling and then either a fix or an explicit, written
acceptance of the scope of the loss. As it stands the change makes a year of
stored Reddit history unreadable, and in the default mixed selection presents
that absence as a measured number.

Important 3 and 4 should be settled in the same pass, since both are the same
question — what a "venue" is now — showing up in the ranking and in the
rendering.

Everything else is sound. The migration is correct and retry-safe, the
root/concrete boundary is drawn consistently, the config-version bump is the
right call and genuinely moves, the fixtures are exact-identity, and all ten
teeth reproduce. Task 8 should stay blocked until the two Criticals are closed,
because both of them are about which population Task 8 would be scoring.

Worktree left clean: `git status --short` shows only this review file and the
task-9 report; HEAD is still `dedc90b`; every mutation reverted with
`git checkout --`; no migration was run.

---

# Fix round 1 re-review

Reviewer: independent (did not write the fix)
Worktree: `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-pipeline-audit`
Branch: `codex/radar-pipeline-audit`, HEAD `cc2d278`
Fix package: `.superpowers/sdd/review-dedc90b..cc2d278.diff` (23 files, +667/-52)
Date: 2026-08-27

**VERDICT: APPROVED** — 10 of 10 addressed. 0 new Critical, 0 new Important,
4 new Minor (none blocking; two of them pre-existing, all for the final branch
review).

Both Criticals were re-proved against the real dev MySQL database with owned
fixtures, and both were re-mutated by me: the fixes are real and the new
assertions have teeth. The two behavioural questions the first round left
open — what a venue is, and what the panel prints — are now settled the way
the rulings direct, and the venue rooting *does* reach the UI (traced end to
end; the client never counts venues itself).

---

## Finding-by-finding

### CRITICAL 1 — zero-count root `reddit` bucket row on a not-due cycle — **ADDRESSED**

The ruling was applied literally, and the three-state contract is real:

- `features/radar/sources/__init__.py:38-62` — `per_source_status: dict | None
  = None`, with the three states documented on the field (`None` = fetcher does
  not report per-source status; `{...}` = these names were observed; `{}` =
  explicitly nothing was observed) and the instruction that consumers must test
  `is not None`.
- `run_radar_ingest.py:137` — the not-due branch returns
  `FetchResult(posts=[], status='ok', per_source_status={})`.
- `features/radar/ingest.py:256-259` — `if result.per_source_status is None:
  result_statuses = {source: result.status} else: dict(...)`. The
  everything-failed guard became `if not result_statuses or all(...)`, so an
  empty map takes the skip path explicitly rather than through the vacuous
  truth of `all([])`.

**What I did.** Drove `ingest.run_cycle` against the live database with an
owned `ZZQC` / `zz_rr_c1` fixture and exactly the `FetchResult` this branch
returns from the not-due branch, under the key `'reddit'`, alongside a
producing Bluesky fetcher (scratch probe, deleted; every row cleaned by exact
identity, `rows left behind: 0`):

```
cycle per_source   : {'bluesky': 'ok'}
posts_new / mentions: 1 1
bucket child rows  : {'bluesky': ('ok', 1, 1)}
ROOT 'reddit' child rows written: 0
bucket.sources_ok  : {1}
```

No `source='reddit'` child row, and `RadarBucket.sources_ok` counts one, not
two. The absence is genuine: nothing is written, not an `ok` zero and not a
`missing`.

Two secondary paths checked by reading: a Reddit fetcher that *raises* still
lands on `statuses['reddit'] = 'missing'` (ingest.py:246), which is correct
under the ruling — we tried and failed — and `missing` is not in
`buckets._COUNTABLE`, so it still writes no row. `depths['reddit']` is set on
the empty-map path and is cycle-reporting only.

### CRITICAL 2 — `expand_sources` dropped the root — **ADDRESSED**

The two-helper split was adopted with the review's exact call-site list.
`config.py:388-441` carries a block comment explaining why the two must not be
merged, in both directions; each helper's docstring names its callers.

Verified the call sites by grep, not by the report's table — every production
call site of either helper:

| Helper | Call sites (verified) |
|---|---|
| `expand_sources` (strict) | `board._triplets:186`, `leaderboard.build_rows:146`, `detail_panel.window_figures:98`, `scoring.pooled_z:176`, `scoring.window_z:246`, `run_radar_ingest.score_all:237` |
| `expand_sources_for_history` | `board._covered_hours:128`, `board._hourly_counts:143`, `board._tones:232`, `detail.daily_counts:91`, `detail.first_watched_day:115`, `detail.intraday_counts:180`, `detail._watched_from_index:206`, `detail_panel._posts:114`, `detail_panel.breakdown_for:134`, `journal.distinct_voices:200` |

That is the review's list exactly, plus `window_figures` — which the review
listed as affected but assigned to neither family. Strict is the right call
there and the docstring argues it: it returns `expected` and `baseline_days`
alongside `mentions`, and `phrasing.read_clauses` quotes the two against each
other in one sentence.

`routes/api.py:185,296` no longer expands; it hands `query.sources` — the
viewer's selection — to `board_mod.build` and `detail_panel.build`, which is
necessary rather than stylistic: once the list is expanded the root is gone
and no downstream query can tell it was ever asked for. `leaderboard.build_rows`
correctly passes the *unexpanded* selection to `_distinct_authors` /
`_distinct_channels` (leaderboard.py:175-176) so the voice counts expand for
history while the bucket read next to them expands strictly.

**What I did.** The dev DB holds zero root-`reddit` rows (re-confirmed:
`radar_bucket_sources` is `bluesky` 16626 / `fourchan` 12834 and nothing else;
zero root `reddit` posts, events or bucket rows). So I inserted my own owned
fixture — ticker `ZZH2`, channel `zz_rr_c2`: a root `reddit` bucket 135 minutes
back (different HOUR), a second root bucket 200 days back (different DAY), a
concrete `reddit:wallstreetbets` bucket 30 minutes back, root and concrete
posts + mentions, and root and concrete mention events — and asked all sixteen
read paths directly, with the root carrying the real pre-split stamp
`8106787f1fa72179`:

```
raw    board._covered_hours (hours seen)         got=2                          OK
raw    board._hourly_counts (total)              got=17                         OK
raw    board._tones (bullish)                    got=2                          OK
raw    detail.daily_counts (total)               got=21                         OK
raw    detail.daily_counts (the 200-day-old day) got=4                          OK
raw    detail.first_watched_day                  got=2026-02-01                 OK
raw    detail.intraday_counts (total)            got=17                         OK
raw    detail._watched_from_index                got=21                         OK
raw    detail_panel.breakdown_for (reddit row)   got=(2, 2)                     OK
raw    detail_panel.breakdown_for (venue keys)   got=['reddit']                 OK
raw    detail_panel._posts (total)               got=2                          OK
raw    journal.distinct_voices                   got=5                          OK
scored detail_panel.window_figures (mentions)    got=10   (17 with the root)    OK
scored board._triplets (4h z)                    got=6.3640 (7.5 with it)       OK
scored scoring.pooled_z @ the root's bucket      got=(None, 0)                  OK
scored scoring.window_z (component mentions)     got=10                         OK
scored leaderboard.build_rows row.sources        got=['reddit:wallstreetbets']  OK
scored leaderboard.build_rows row.mentions       got=10                         OK
scored leaderboard.build_rows row.venues         got=1                          OK

FAILURES: 0
rows left behind: 0
```

Every raw-count family sees the historical root row; every scored family
excludes it. Also confirmed directly:
`expand_sources_for_history(['reddit:wallstreetbets'])` is
`['reddit:wallstreetbets']` — a concrete selection does not reach the
undifferentiated pre-split history — and a mixed selection
`['bluesky','fourchan','reddit']` does include the root.

### IMPORTANT 3 — two subreddits read as two independent venues — **ADDRESSED**

Counted by ROOT, as one decision, exactly as the ruling directs.
`leaderboard.Row` gained `venues: int` (leaderboard.py:51-56) computed as
`len({source_root(name) for name in contributing})` (leaderboard.py:254), and
`sources` stays concrete because it is the breakdown. Every consumer moved:

- `leaderboard.py:279` — the `single-source` mark is now `venues == 1 and
  selected_venues > 1`, where `selected_venues` is the rooted count of the
  VIEWER's selection (leaderboard.py:150). This fixes the inversion the review
  found: with only the Reddit chip on, the old `len(sources) > 1` was 8 and
  marked every Reddit-only ticker "only one of the selected sources
  contributed"; it is now 1 and the mark is correctly suppressed.
- `leaderboard.py:302` — the `min_venues` gate uses `venues`.
- `board.py:194,199` — `venue_counts['multi']` and the board's own
  `min_venues` filter use `row.venues`.
- `phrasing.py:102` — `venues = row.venues`, so "N venues" never means N
  subreddits.
- `buckets.py:149` (Minor 9, same pass) — `sources_ok` counts distinct roots.

**What I did.** The `ZZH2` probe above reports `leaderboard.build_rows
row.venues == 1` for a ticker whose only scored bucket is
`reddit:wallstreetbets` alongside a root row, and
`row.sources == ['reddit:wallstreetbets']` — the breakdown stayed concrete
while the count went rooted. `RadarBucket.sources_ok` read `{1}` in the
Critical 1 probe. Checked that `leaderboard.Row` has exactly one construction
site (leaderboard.py:313) so the new required field cannot be missed anywhere,
and that `test_radar_phrasing.FakeRow.venues` is a derived property rather
than a settable field — the fake cannot claim breadth its own source list does
not support.

### IMPORTANT 4 — the detail panel rendered raw internal source names — **ADDRESSED**

The ruling was applied: population, not presentation. No `r/<sub>` label and
no per-subreddit rows ship.

- `detail_panel.breakdown_for:154` — the venue map is keyed on
  `source_root(source)`, so the eight `reddit:<sub>` names and the pre-split
  bare `reddit` pool into one `reddit` row with one voices count and one share
  of mentions, exactly as before Task 9. `venues=len(b.venues)` in
  `serialize_detail` (api.py:233) is therefore a rooted count for free.
- `format.ts:74-76` — `sourceLabel` roots at the colon before the lookup and
  falls through as the WHOLE key when the root is unknown, so
  `discord:general` still renders as itself rather than losing half its name.

**What I did.** The `ZZH2` probe asked `breakdown_for` directly with a root
post and a `reddit:wallstreetbets` post in the same window: venue keys came
back `['reddit']` with `(2 mentions, 2 voices)` — one pooled row, both names
inside it. Read `Breakdown.tsx:48` and `Posts.tsx:37`: both render through
`sourceLabel`, and `Breakdown.tsx` keys its rows on `venue.source`, which is
unique again because it is rooted. `format.test.ts` covers `reddit`,
`reddit:wallstreetbets`, `reddit:pennystocks` and the unknown-root-with-suffix
case; the frontend suite is green.

### MINOR 5 — `sources=` cardinality — **ADDRESSED**

`api.py:59` — `MAX_SOURCES = len(SOURCES) + len(REDDIT_SUBS)` (verified live:
11), and `parse_query` raises `BadQuery('too many sources')` above it
(api.py:70). `test_a_selection_longer_than_every_real_name_is_rejected` pins
the boundary in both directions (200 at 11, 400 at 12). The unknown-root check
still runs first, which is the right order: the expensive part is the
`IN (...)` clause and it is never reached.

### MINOR 6 — a concrete-subreddit link lit no chip — **ADDRESSED**

`api.py:195` — `board.sources = sorted({source_root(s) for s in
query.sources})`. This is the first of the two options the review offered.
`test_a_concrete_subreddit_link_lights_the_reddit_chip` asserts the board is
still built from `['reddit:wallstreetbets']` while the payload echoes
`['reddit']`, and that the echoed value is in `all_sources`. Traced the
consequence in `Controls.tsx:41-49` / `BoardPage.tsx:19`: the chip is lit and
the forbidden all-chips-off state is gone. The concrete filter still survives
only the first render — the client seeds `Selection.sources` from the rooted
payload, so the next refetch sends `sources=reddit`. That is inherent to the
option the review itself recommended (the alternative was a separate
`selected_roots` field), so it is not a deviation; recorded below as an
observation rather than a finding.

### MINOR 7 — undocumented width dependency in the downgrade — **ADDRESSED-WITH-NEW-ISSUE**

`08316d3e4d77_widen_radar_source_columns.py:57-65` now states the dependency
(longest configured name `reddit:smallstreetbets` at 22; a sub name over 17
characters breaks it) and `:70-79` guards it with `SELECT COUNT(*) ... WHERE
CHAR_LENGTH(source) > 24`, `int()` at the boundary, raising a readable
`RuntimeError`. I executed the guard's exact SELECT against the live MySQL 8
database without running any migration: it parses and returns `0` as a Python
`int`. `CHAR_LENGTH` is standard on MariaDB too. The guard is worth more than
its docstring claims on MariaDB, where a non-strict session would silently
TRUNCATE rather than error.

New issue (Minor N1 below): the guard is placed after the `radar_poll_state`
narrowing, so the docstring's claim that it turns the failure into a readable
error "instead of a half-applied rollback" is not true — one DDL has already
auto-committed by the time it can fire.

### MINOR 8 — the migration did not state what the downgrade cannot restore — **ADDRESSED**

The rollback boundary now lives in the `downgrade()` docstring (`:37-55`):
what it restores, what it cannot re-aggregate, that the prefixed bucket rows
are left in place and read as absent rather than as a wrong aggregate, and
that a re-upgrade recovers them intact. That is the paragraph the review asked
to be moved out of the report and into the artifact an operator actually
reads at 03:00.

### MINOR 9 — `RadarBucket.sources_ok` counted concrete names — **ADDRESSED**

`buckets.py:148-154` — `len({source_root(source) for source, status in
statuses.items() if status == 'ok'})`, with the reasoning on it. The count no
longer rises and falls with `REDDIT_SUBS_PER_CYCLE`. Verified live in the
Critical 1 probe: one producing Bluesky source and a Reddit that observed
nothing gives `sources_ok == 1`; under the Critical 1 mutation the same bucket
read `2`.

### MINOR 10 — historical root Reddit buckets never re-invalidated — **ADDRESSED (assessed, no code — correctly)**

The ruling was "assess only; code it only if genuinely open". I checked the
three legs of the fixer's argument rather than accepting them:

1. `run_radar_ingest.score_all:237` iterates `expand_sources(SOURCES)` —
   strict — so `score_source('reddit', ...)` never runs. Confirmed by reading.
2. No scored read admits the root. Confirmed empirically for all five
   (`leaderboard.build_rows`, `board._triplets`,
   `detail_panel.window_figures`, `scoring.pooled_z`, `scoring.window_z`) by
   the `ZZH2` probe. The reads that DO see the root select only
   `mention_count` / `bucket_start` / `status` / author columns — I read all
   ten history queries; none touches `expected`, `variance`, `mention_z` or
   `baseline_days`.
3. It cannot contaminate a baseline: `scoring._rows_by_ticker:44-48` filters
   `source_config_version == config_version` AND `source == source` (always a
   concrete name), and `baselines.usable:48` filters
   `o.config_version == config_version`. Verified by reading both, not by
   trusting the report.

So the stale `mention_z` on root rows is genuinely unreadable and
un-baselinable, and an invalidation pass would clear a column nothing reads on
rows nothing baselines from — while having to walk the whole retained history
to do it. Leaving it is the right call.

The residual risk the fixer names — a future change re-admitting the root to a
scored read — is real, and is currently guarded by comments only. See new
finding Minor N2, which I proved by experiment.

---

## Concern adjudication (the fixer's four)

### 1. `pooled_z` / `window_z` have no production caller — **claim VERIFIED; acceptable, flagged for the branch review**

Traced every reference across the repo. `pooled_z` is called only from tests.
`window_z` is called only from `scoring.is_sustained:280`, and `is_sustained`
has **zero** callers anywhere outside `scoring.py` — not the daemon, not the
API, not the board, not the templates. Both functions are dead in production
today.

Plainly: **dead code with two test fixtures bent around it is acceptable here,
and should be flagged for the final branch review rather than unwound now.**
The reasons, in order of weight:

- The bend is small and *more* honest than what it replaced. The fixtures used
  the bare `'reddit'` as a **stored** source name, which since Task 9 is no
  longer a name anything writes. `REDDIT = 'reddit:pennystocks'` makes them
  write what production writes, with the reason on the constant. That is a
  correction, not a distortion — those fixtures were quietly stale the moment
  Reddit started emitting prefixed names.
- The alternative contract (these two take already-expanded stored names) is
  the *inconsistent* one: every other function in the read layer now takes a
  selection and expands for itself, and `pooled_z(ticker, bucket, ['reddit'])`
  is manifestly a selection-shaped call.
- Unwinding it means deleting two `expand_sources` lines and reverting the
  constant, which is a five-minute change whenever the branch review decides
  the functions should die instead. Nothing is locked in.

What the branch review should decide is whether `pooled_z`, `window_z` and
`is_sustained` should exist at all — three functions, ~60 lines, a spec
reference (6.2, 6.9) and now ~15 test cases, none of which anything calls.
That is a Task-9-independent question and I am not treating it as a Task 9
finding.

### 2. `Row.venues` is not serialized to the client — **traced end to end; the fix DOES reach the UI**

This was the concern that mattered, so I traced it rather than reasoned about
it. `_row()` (`api.py:155`) still sends only the concrete `sources`, and there
is no `venues` key on the wire. That is fine, because **nothing on the client
counts venues.** Grepped every `.ts` / `.tsx` under `static/radar/src` for
`sources`, `venue`, `min_venues` and `marks`:

- `row.sources` is declared in `types.ts:145` and **read by no component**.
  The only `sources` reads in the app are `selection.sources` (the chip state)
  and `payload.all_sources` (the chip list).
- The `min_venues` control's label reads `payload.venue_counts.any` /
  `.multi` (`Controls.tsx:113,117`) — computed server-side, now from
  `row.venues`.
- The filter itself is a server-side query parameter (`api.ts:40` →
  `parse_query` → `board.build(min_venues=...)`), applied against `row.venues`
  at `board.py:199`.
- The `single-source` mark is an entry in `row.marks`, decided at
  `leaderboard.py:279`; `format.ts:110-112` only supplies the explanatory
  copy. `TickerRow.tsx:73` renders whatever marks the server sent.
- "N venues" in the written read is a server-rendered `Clause`
  (`phrasing.py:102-104`), and the detail panel's `venues=` is
  `len(b.venues)` on the now-rooted breakdown (`api.py:233`).

So every venue-shaped thing the reader sees is decided on the server, and all
four of them now use the rooted count. **The Important 3 fix lands in the UI;
it does not stop at the server boundary.** The fixer's note stands as a
forward-looking caution only: a future client that wants a venue count must be
given `venues` and must not use `row.sources.length`. Worth one line in
`types.ts` next to `sources`, not worth a finding.

### 3. Pre-existing broad `ZZ%` teardowns — **genuinely pre-existing, and WIDER than reported**

Confirmed by `git show cc2d278 -- personal_apps/tests/ | grep "^+.*like('ZZ%')"`
and the same for `dedc90b`: **neither commit adds or widens a single one.**
`git log -S` attributes each to an earlier commit (`c553c47`, `fb622c8`,
`b1a833a`, `b92423c`), all ancestors of Task 9.

But the fixer under-counted them. It is not two files, it is **five**:

| File | Lines | Deletes |
|---|---|---|
| `tests/test_radar_daemon.py` | 550, 573, 593, 615 | `RadarBucketSource.ticker LIKE 'ZZ%'` |
| `tests/test_radar_journal.py` | 22, 26, 53, 58 | `RadarMentionEvent` + others, `ticker LIKE 'ZZ%'` |
| `tests/test_radar_buckets.py` | 25, 26, 29, 33, 34, 37 | `RadarBucketSource`, `RadarBucket`, `RadarMentionEvent` |
| `tests/test_radar_bucket_sources.py` | 26, 28, 32, 34 | `RadarBucketSource`, `RadarBucket` |
| `tests/test_radar_retention.py` | 42 | `RadarBucket` |

Not a Task 9 finding — but reported below as new-Minor N3 for the final branch
review, because the correct scope is five files and a cleanup scoped to two
would leave the hazard live. (I hit this myself: my own owned `ZZQC` and `ZZH2`
probe rows sit squarely inside `ticker LIKE 'ZZ%'`.)

### 4. The new downgrade guard was never executed — **acceptable**

Acceptable, and I would have ruled the same way. The reasoning:

- Running a real downgrade takes the shared dev database off head, which the
  constraints forbid, and `flask db current` must read `08316d3e4d77`.
- The **DDL statements themselves are already proven**: the fixer ran a full
  `downgrade` → `upgrade` round trip on this exact migration during the
  previous round (task-9-report, Item 4), watching the widths drop to
  24/24/16 and come back to 48/48/48. This round added no DDL.
- The only unrun code is the guard, and I proved its SQL separately: I executed
  `SELECT COUNT(*) FROM radar_bucket_sources WHERE CHAR_LENGTH(source) > 24`
  against the live MySQL 8 database (no migration, read-only) — it parses and
  returns `0` as a Python `int`. `CHAR_LENGTH` is standard on MariaDB.
- What remains unexecuted is `op.get_bind().execute(...).scalar()` and one
  `raise`. On SQLAlchemy 2.0.49 / Alembic 1.18.4, `op.get_bind()` returns a
  `Connection` and `Connection.execute(sa.text(...)).scalar()` is the standard
  form — the same call I ran through `db.session`.

Residual risk: near zero, and its blast radius is a rollback that stops with a
clear Python traceback instead of proceeding. That is strictly better than the
pre-fix behaviour. The one thing genuinely wrong with the guard is *where* it
sits — new finding N1.

---

## Teeth re-verification (the two Criticals)

I re-applied both mutations myself, watched them fail, and reverted by the
inverse edit — never `git checkout --`, since a revert of the file would revert
the fix with the mutation.

| # | Assertion | Mutation | Exact failure observed | Reverted |
|---|---|---|---|---|
| C1 | an explicitly-empty per-source map records NOTHING | `ingest.py:256-259` → `result_statuses = result.per_source_status or {source: result.status}` (truthiness) | pytest: `AssertionError: assert {'bluesky': '...reddit': 'ok'} == {'bluesky': 'ok'}` / `Left contains 1 more item: {'reddit': 'ok'}` at `tests\test_radar_ingest.py:312`. **Live-DB probe under the same mutation**: `bucket child rows : {'bluesky': ('ok', 1, 1), 'reddit': ('ok', 0, 0)}`, `ROOT 'reddit' child rows written: 1`, `bucket.sources_ok : {2}` | ✓ |
| C2 | the pre-split root is visible to every raw-count read | `config.expand_sources_for_history` → returns the strict expansion (the root append deleted) | pytest, 5 failures: `test_the_pre_split_reddit_history_still_counts_on_the_series`, `..._towards_tone`, `test_the_chart_still_draws_the_pre_split_reddit_history`, `test_the_breakdown_still_shows_one_reddit_row`, `test_the_pre_split_reddit_voices_still_count` (`assert 2 == 4` at `tests\test_radar_leaderboard.py:324`). **Live-DB probe under the same mutation**: 11 of 12 raw-count checks flipped — `_covered_hours` 2→1, `_hourly_counts` 17→10, `_tones` 2→1, `daily_counts` 21→10 and the 200-day-old day `4`→`None`, `first_watched_day` 2026-02-01→2026-08-20, `intraday_counts` 17→10, `_watched_from_index` 21→23, `breakdown_for` reddit row (2,2)→(1,1), `_posts` 2→1, `distinct_voices` 5→3. Every scored check stayed put | ✓ |

`git status --short` after each revert showed only this review file and the
task-9 report — no source file modified. Both mutations are gone from the tree.

The one thing worth noting about C1's regression: its assertions are ordered
so that the *cheapest* one (`result['per_source']`) trips first under this
particular mutation, and the durable-row assertions after it are never reached
in that run. They are not decorative — a fix that corrected the cycle report
while still writing the row would fail on them — but the proof that no row is
written came from my probe reading `radar_bucket_sources` directly, not from
watching that line fail.

---

## Gates

| Gate | Command (from `personal_apps/`) | Result |
|---|---|---|
| 1. Radar suite | `python -m pytest tests/ -k radar -q` | `2 failed, 617 passed, 2 skipped, 646 deselected, 2 warnings in 65.82s`. The two are exactly `test_the_page_embeds_the_board_it_would_otherwise_have_to_fetch` and `test_the_page_falls_back_to_the_default_board_on_a_bad_query`, both `ViteManifestError: No Vite manifest`. **No third failure.** Not fixed, per instruction ✅ |
| 2a. Types | `npx tsc --noEmit` | exit 0, no output ✅ |
| 2b. Frontend | `npx vitest run` | `Test Files 32 passed (32) · Tests 403 passed (403)` ✅ |
| 3. Alembic | `python -m flask db current` / `heads` | both `08316d3e4d77 (head)` — single head, no downgrade run ✅ |
| 4. Circular import | four separate `python -c` processes | `buckets` OK, `journal` OK, `ingest` OK, `run_radar_ingest.build_fetchers` OK. The deliberate `buckets` ↔ `journal` cycle survives the new `from .config import expand_sources_for_history` in `journal.py`, as it must: `config` imports nothing from the package ✅ |
| 5. Live widths | `information_schema.COLUMNS` | `radar_posts` 48, `radar_bucket_sources` 48, `radar_poll_state` 48, all NOT NULL / utf8mb4; `radar_source_cursors` still 24 (root-only, correct); `radar_mention_events` 48 ✅ |

Standing constraints:

- **An absence is never a zero.** The one new write path (`per_source_status ==
  {}`) writes nothing at all — proved at row level. The one new read path
  (`expand_sources_for_history`) makes an existing absence stop reading as a
  zero. Both directions verified.
- **Naive UTC.** The diff introduces no `utcnow()` and no tz-aware datetime.
- **`int()`/`float()` at the query boundary.** One new aggregate in the diff —
  the migration's `SELECT COUNT(*)` — and it is wrapped in `int()`.
- **SQL NULL vs Python None.** The new predicates are `CHAR_LENGTH(source) > 24`
  on a NOT NULL column and `source IN (...)` on a NOT NULL column. No
  three-valued logic introduced.
- **MySQL 8 / MariaDB.** New SQL is `CHAR_LENGTH` in a `SELECT COUNT(*)`.
  Standard on both, executed on MySQL 8 here.
- **Protected files.** `git show --stat cc2d278` lists 23 files and contains no
  `discover_telegram_sources.py`, no `telegram_candidates.json`, no
  `reddit_candidates.json` ✅
- **Shared-DB isolation of the fixtures this diff adds.** `test_radar_board.py`
  `BD*` under the file's existing `clean`; `test_radar_detail.py` `DT*` under
  `clean`/`panel_ticker`; `test_radar_leaderboard.py` `LBH` under `board`;
  `test_radar_ingest.py` under the exact-identity `_wipe`. **No broad
  `LIKE 'ZZ%'` teardown is added by this diff** — verified by grepping the
  commit's own `+` lines. My own probe fixtures (`ZZQC`/`zz_rr_c1`,
  `ZZH2`/`zz_rr_c2`) were deleted by exact identity; both probes report
  `rows left behind: 0`, and the pre-run DB inventory (`bluesky` 16626,
  `fourchan` 12834, zero root-`reddit` rows, zero cursor rows) is unchanged.

---

## New findings

### MINOR N1 — the downgrade's width guard fires after a DDL has already committed

`personal_apps/migrations/versions/08316d3e4d77_widen_radar_source_columns.py:67-79`

The guard is the right idea in the wrong place. `op.alter_column(
'radar_poll_state', ...)` runs at `:67`, and MySQL/MariaDB DDL is
non-transactional, so it has auto-committed by the time the `SELECT COUNT(*)`
at `:70` can raise. The docstring's own claim at `:64-65` — "turns that into a
readable error instead of a half-applied rollback" — is therefore false: it
prevents the *truncation* (which on a non-strict MariaDB session would be
silent data loss, so the guard is genuinely valuable), but the rollback is
still half-applied, with `radar_poll_state.source` narrowed to 24 while the
other two columns are still 48.

**Fix.** Move the count check to the very top of `downgrade()`, above the first
`alter_column`, and reword the docstring sentence to "before any DDL runs". One
line moved, one sentence edited. While there, consider a second `CHAR_LENGTH >
16` guard on `radar_posts` after the normalising `UPDATE` at `:86` — the
normalisation covers `reddit:%` but nothing checks the other sources against
the 16-character target.

### MINOR N2 — four of the five scored reads' strictness is untested

`personal_apps/features/radar/board.py:186`,
`personal_apps/features/radar/detail_panel.py:98`,
`personal_apps/features/radar/scoring.py:176,246`

"The pre-split root is NOT in this scored read" is an absence-shaped claim, and
only one of the five scored paths has a test behind it
(`test_the_pre_split_reddit_history_is_kept_out_of_the_ranking`, which pins
`leaderboard.build_rows`).

**Proved by experiment.** I changed `board._triplets` and
`detail_panel.window_figures` from `expand_sources` to
`expand_sources_for_history` — silently re-admitting a different baseline
population to a z-score and to the `mentions`-against-`expected` sentence — and
ran the full suite:

```
python -m pytest tests/ -k radar -q
-> 2 failed, 617 passed, 2 skipped   (the two known ViteManifestError failures)
```

Fully green on a mutation that reintroduces exactly the baseline mixing the
`source_config_version` bump exists to prevent. `pooled_z` / `window_z` are
equally unpinned; their fixtures now write only concrete names, so the history
helper is a no-op for them and the mutation cannot be detected there at all.

This matters more than its severity suggests because the **Minor 10 closure
rests on it**: "no scored read admits the root" is the whole argument for not
writing an invalidation pass, and nothing enforces it. It is also exactly the
class of gap the branch has already been bitten by (`feedback_sdd_assumption_bugs`:
run the teeth experiment before trusting any assertion whose passing state is
an absence).

**Fix.** Extend the existing `_old_root_bucket` fixture in
`tests/test_radar_board.py` and `tests/test_radar_detail.py` with two
assertions and watch each fail under the mutation above:
`board._triplets([T], ['reddit'], NOW)[T][4]` must equal the concrete-only z,
not the pooled one; `detail_panel.window_figures(T, ['reddit'], since, NOW)[0]`
must equal the concrete mention count. (Both values are already computed in my
probe: 6.3640 vs 7.5, and 10 vs 17.) Cheapest possible coverage for the rule the
whole two-helper split rests on.

### MINOR N3 — broad `LIKE 'ZZ%'` teardowns across five test files (pre-existing)

`tests/test_radar_daemon.py:550,573,593,615`,
`tests/test_radar_journal.py:22,26,53,58`,
`tests/test_radar_buckets.py:25,26,29,33,34,37`,
`tests/test_radar_bucket_sources.py:26,28,32,34`,
`tests/test_radar_retention.py:42`

Pre-existing and untouched by Task 9 or this fix round — confirmed by grepping
both commits' own `+` lines and by `git log -S`. Reported here only because the
fixer's note names two files and the real scope is five, and a cleanup scoped
to two would leave the hazard live in the other three. Against a shared real
database, any of these deletes another suite's — or a reviewer's — owned `ZZ`
fixture.

**Fix (branch review, not Task 9).** Replace each with the owning suite's exact
identity, the way `test_radar_ingest._wipe` and the Task 9 fixtures already do.

### MINOR N4 — `board.excluded['one_venue']` is dead in production (pre-existing)

`personal_apps/features/radar/board.py:287-288`,
`personal_apps/features/radar/leaderboard.py:302-304`,
`personal_apps/static/radar/src/list/Excluded.tsx:12`

`board.build` calls `leaderboard.build_rows` without `min_venues`, so the
default `1` makes `if venues < min_venues` at `leaderboard.py:302`
unreachable, and `excluded['one_venue']` is always `0`. The board then applies
its own breadth filter at `board.py:199` without counting what it dropped. The
client renders "N from one venue only" (`Excluded.tsx:12`) for a number that
is never non-zero — so the reader is never told how many rows their own
breadth control removed, which is the one thing the excluded panel exists to
say. Only tests pass `min_venues > 1` to `build_rows`
(`test_radar_leaderboard.py:451`).

Pre-existing: the same shape is in the pre-Task-9 tree. This round moved both
call sites onto `row.venues` without changing which one counts.

**Fix (branch review).** Either pass `min_venues` through from `board.build` and
drop the duplicate filter at `board.py:199`, or count the drop where the filter
actually runs.

### Observations (not findings)

- **A concrete-subreddit deep link survives only the first render.** With
  Minor 6's rooting, `?sources=reddit:wallstreetbets` filters the
  server-rendered board correctly and lights the Reddit chip, but the client
  seeds `Selection.sources` from the rooted payload (`BoardPage.tsx:19`), so
  the next refetch of any kind sends `sources=reddit`. This is inherent to the
  option the review itself recommended; the alternative it also offered (a
  separate `selected_roots` field) is the one that would preserve it.
- **`window_figures` strict vs `breakdown_for` history in the same panel.** For
  the width of one 4-hour window around the deploy, the written read's
  `mentions` (buckets, strict) and the breakdown table's `mentions` (posts,
  history) can differ by the root-named rows in that window. Transient, and
  the two numbers already come from different tables with different filters,
  so they never matched exactly. Not worth code.
- **Duplicate entries in a selection multiply through the expansion**:
  `?sources=reddit,reddit,...` (11 entries, the cap) expands to an 89-element
  `IN (...)` list. Bounded and harmless; noting it only because the cap was
  added in this round.
- **`row.sources` on the wire.** Concrete names still reach the client and are
  never rendered. One comment in `types.ts:145` saying "concrete stored names;
  count venues with the server's `venues`, never `sources.length`" would
  future-proof concern 2 for nothing.

---

## Verdict

**APPROVED.**

All ten findings are genuinely closed. The two Criticals were the ones that
mattered and both are real fixes rather than reworded ones: I proved each
against the live database with my own owned fixtures — no root child row and
`sources_ok == 1` on an unobserved cycle, and the pre-split root visible to all
twelve raw-count checks while excluded from all seven scored ones — then
re-mutated each and watched the regressions and the probes fail exactly as
claimed.

The three rulings were followed rather than paraphrased. Critical 1 records no
observation at all where the review had suggested writing `ok` zeroes, and the
`is not None` / truthiness distinction is documented on the field, applied at
the consumer, and load-bearing. Critical 2's two-helper split covers the
review's exact call-site list, plus `window_figures`, which the review left
unassigned and which belongs on the strict side for the reason the docstring
gives. Important 3 + Minor 9 were decided once, by root. Important 4 changed
the population and not the presentation: the venue table is one pooled `Reddit`
row again, no `r/<sub>` label ships, and the raw key no longer leaks through
`sourceLabel`'s fallback.

The venue rooting reaches the reader. Every venue-shaped thing on screen — the
`2+` count on the breadth control, the filter itself, the `single-source` mark,
"N venues" in the written read, and the panel's venue count — is decided on the
server and now uses the rooted number. The client never counts venues, so
`Row.venues` not being serialized costs nothing today.

Four new Minors, none blocking: a guard that fires one DDL too late (N1), an
untested strictness rule that the Minor 10 closure quietly depends on (N2), and
two pre-existing hazards worth carrying to the final branch review (N3, N4). N2
is the one I would fix before Task 8 touches scoring, because Task 8 is the
change most likely to reach for a source expansion and pick the wrong one.

Worktree left as found: HEAD is still `cc2d278`; `git status --short` shows
exactly one entry, the (intentionally uncommitted) task-9 report, unchanged
from how I found it — `git diff --stat -- personal_apps/` is empty, so no
source file is modified. This review file lives under the gitignored
`.superpowers/` and never appears in status. Every mutation was reverted by its
inverse edit, every probe fixture deleted by exact identity (both probes report
`rows left behind: 0`, and the bucket-source inventory is back to `bluesky`
16626 / `fourchan` 12834 with zero cursor rows), no migration was run in either
direction, and nothing was committed.

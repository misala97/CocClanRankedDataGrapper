# Radar pipeline audit — findings and fix design

**Date:** 2026-08-26
**Scope:** `personal_apps/features/radar/`, end to end — sources → ingest → buckets → scoring/baselines → tone → leaderboard/board → routes/api → `static/radar/src`
**Status:** design, awaiting review

Every finding below was verified against the live VPS database (`root@82.165.240.212`,
`personal_apps`, read-only) or reproduced against the real code. Where production
disagreed with a reading of the source, production wins and the disagreement is
recorded.

---

## 1. What the audit found

### 1.1 The bucket write path loses the busiest quarter-hours

`buckets.roll_up` rebuilds a bucket from **the current cycle's in-memory mentions
only** and writes the totals with `setattr`. Every source advances a cursor, so
cycle N+1 carries only what arrived after cycle N. A 15-minute bucket touched by
several cycles therefore keeps only the last cycle's slice.

Reproduced against the real `roll_up` and the real database:

```
buckets.roll_up([row(author='u1', minute=1)], ALL_OK, start)   # cycle N
buckets.roll_up([row(author='u2', minute=4)], ALL_OK, start)   # cycle N+1
-> AssertionError: lost the first poll: got 1
```

Measured in production by recomputing ground truth from `radar_mentions` joined to
`radar_posts` and comparing against stored `high_confidence_count`:

| true bucket size | groups | truth | stored | lost |
|---|---|---|---|---|
| 1 | 7845 | 7845 | 7502 | 4.4% |
| 2 | 816 | 1632 | 1247 | 23.6% |
| 3–4 | 372 | 1234 | 736 | 40.4% |
| 5–9 | 151 | 889 | 518 | 41.7% |
| 10+ | 15 | 203 | 116 | 42.9% |

Overall 14.1% of Bluesky's high-confidence mentions and 16.0% of Reddit's never
reach a bucket. **The loss scales with how busy the bucket is** — the pipeline
discards 43% of exactly the quarter-hours the board exists to rank.

The existing regression test, `tests/test_radar_buckets.py:108`
`test_rerunning_a_cycle_replaces_rather_than_doubles`, passes because it feeds the
second call a **superset** (`u1`, then `u1 + u2`). That models a full re-read of the
window, which no source performs. The assertion encodes the assumption rather than
testing it.

### 1.2 A status rewrite leaves stale scoring columns behind

`scoring.score_source` refuses to score a row whose `status != 'ok'`. `roll_up`
rewrites `status` on every pass but never clears `expected`, `variance`,
`mention_z` or `baseline_days`. In production **399 rows are marked `truncated` and
still carry a `mention_z`** written while they were `ok`. `leaderboard.build_rows`
filters on `mention_z.isnot(None)`, so those rows are ranked on a score the scorer
would now refuse to produce.

This also corrects an earlier reading of the code: the `partial` mark is *not*
unreachable. It is reachable only through this race, which is worse than being
unreachable, because it fires on rows whose z describes a different status.

### 1.3 `single_letter_cashtags_allowed` is dead and hashed

`config.SINGLE_LETTER_CASHTAGS` is in `source_config_version()`'s payload, so the
stamp claims it is policy. `ingest._extract_for` never passes `allow_single_letter`,
and `extraction.extract_tickers` defaults it to `True`. Live consequence — 353
single-letter cashtag mentions, **3.0% of the entire high-confidence corpus**:

```
$A 76   $S 36   $B 28   $V 28   $D 21   $M 21   $H 18   $U 18   $T 15   $F 14 …
```

on Bluesky, where the config says to reject them and where 119 of 3302 measured
cashtag matches were money shorthand.

This is the fourth instance of the same defect class — the bot filter, the profile
job and the sentiment job were each defined, hashed and called by nothing.

### 1.4 `PAGE_CAP` is dead

Zero references anywhere in `personal_apps/` or `scripts/`, tests included. Its
docstring claims it drives `truncated` marking per spec 4.3; `sources/fourchan.py`
actually paginates under its own `THREAD_CAP`. The constant was superseded and never
removed. It is not hashed, so it gave no false assurance — but it documents a policy
that does nothing.

Everything else defined in `config.py` resolves to a live call site.

### 1.5 StockTwits has never worked

Zero posts, zero `radar_poll_state` rows, no cursor row, five days. The daemon log:

> `stocktwits trending unavailable this cycle: /trending/symbols.json: 403 Client Error: Forbidden`

Diagnosed 2026-08-26. Every endpoint, every user agent, including none:

```
cf-mitigated: challenge
server: cloudflare
<title>Just a moment...</title>
```

Identical from the VPS and from a home connection, so it is not an IP block.
StockTwits placed its whole API behind Cloudflare bot management. Reaching it means
defeating a bot challenge, which is out of scope on principle.

`_stocktwits_fetcher` handles this correctly — it returns `status='missing'`, never a
zero — but the source is still offered in the UI's `all_sources`, so the board
invites a filter on a venue that has never returned anything.

### 1.6 Reddit is 90% truncated, and truncation is total exclusion

```
source    status      rows   scored
bluesky   ok        147813   146855
fourchan  ok        145153   144205
fourchan  truncated   2666      397
reddit    ok           478      458
reddit    truncated   4372        2
```

`truncated` excludes a bucket from `baselines.usable`, from `profile.build_profile`
and from `scoring.score_source`. Reddit's usable set is therefore 478 rows out of
4850, and within it the baseline estimator is self-fulfilling:

| source | obs/expected | mean z | max z | elevated rows |
|---|---|---|---|---|
| bluesky | 5.235 | 0.139 | 200.0 | 3278 |
| fourchan | 15.413 | 0.001 | 4.0 | 43 |
| reddit | **0.952** | 0.032 | 3.5 | **4** |

Four elevated Reddit rows in 4.5 days. The source cannot spike.

Two causes compound. `sources/reddit._roll_up` collapses every subreddit in a cycle
into one worst-case status, and `REDDIT_SUBS_PER_CYCLE = 1` means that is a single
sub's verdict. r/wallstreetbets turns its 25-entry feed over in under two minutes
against a 120-second poll, so it is permanently truncated — and it carries 47% of
all Reddit volume.

### 1.7 The baseline denominator, and where the earlier reading was wrong

A local simulation suggested `baselines.weekly_rate` divides only by the mass of
buckets where the ticker was already mentioned, making `expected` self-fulfilling.
Production disagrees for two of three sources.

`roll_up` writes a child row for **every countable source** on every
`(ticker, bucket)` any source touched, so zeros are recorded:

| source | zero rows | non-zero rows | % zero |
|---|---|---|---|
| bluesky | 139371 | 8442 | 94.3% |
| fourchan | 147763 | 56 | 100.0% |
| reddit | 4113 | 739 | 84.8% |

Bluesky and 4chan therefore get real denominators (obs/expected 5.2 and 15.4).
**Reddit is the exception**, at 0.952, because `usable` drops its truncated 90% and
leaves only the conditioned remainder. The original simulation modelled a source
without the fan-out — the assumption was measured on the wrong population, which is
the same failure mode as the bare-token false-positive rate.

Fixing 1.6 fixes 1.7. No separate work.

### 1.8 The tone pass reaches no pixel

`board._tones` correctly prefers the model verdict over the lexicon and falls back to
the lexicon on a NULL. `routes/api._row` ships it as `tone`. `types.ts:158` declares
`Tone`. **No component renders it** — confirmed by grep over `static/radar/src/` and
over the built bundle `dist/assets/board-*.js`, where the only `bullish` occurrence
belongs to `detail/Breakdown.tsx`.

`Breakdown.tsx` draws the one tone bar that exists. It is fed by
`detail_panel._breakdown`, which selects `RadarMention.lexicon_sentiment` and
**never joins `llm_sentiment`**.

So the model verdict is computed on a path nothing draws, and the path that is drawn
never reads it. In production 11,789 of 11,794 high-confidence mentions carry a
verdict and the pass reports `0 still waiting`.

The bill, from `radar_llm_spend` for 2026-08-25:

```
calls 344   input 798,198   output 89,281   cost $1.2446
```

The module docstring estimates "roughly twenty cents a day" from "about 1335 scored
mentions a day". The measured volume is 6,880 items — **5x the estimate, 6x the
cost** — for output no surface displays.

### 1.9 Every row is permanently `provisional`

`baseline_days = 0` on 147,228 of 147,429 scored Bluesky rows. Two causes:
`span.days` truncates a 23-hour span to zero, and `source_config_version` has
changed nine times in 4.5 days, so `baselines.usable` sees only the current stamp —
presently 1,431 rows spanning one hour.

`PROVISIONAL_BASELINE_DAYS = 14` therefore fires on 100% of the board. A mark that
always fires carries no information.

### 1.10 Remaining absence-shaped defects

The house rule is that an absence is never a zero. These four break it:

- `sources/reddit.fetch_one` returns rate `0.0` when no entry parses. `interval_for_rate(0)` returns the ceiling, now `REDDIT_MAX_POLL = 6 hours`. A parse failure or a transient empty feed is recorded as "genuinely silent" and earns a six-hour backoff. `None` is the value the scheduler already understands as "never measured".
- `ingest.run_cycle` sets `depths[source] = 0` when a fetch raises.
- `spend.cost_micros` returns `0` for a model with no rate on file, and `summary()` returns only dollars — so the tokens that were meant to make the omission visible never surface. A model swap makes the bill read as free.
- `detail._watched_from_index` is `MIN(bucket_start)` over the window, so only the *leading* gap becomes null. A mid-window outage draws zeros. `board._covered_hours` does this correctly, per hour. Same data, two honesty standards.

### 1.11 `medium` is counted in buckets and never stored

`buckets._promote` awards `medium` in memory. `RadarMention.confidence` holds only
`high` and `low` in production (11,794 / 1,201, zero `medium`). Yet
`leaderboard._distinct_authors`, `leaderboard._distinct_channels`, `board._tones` and
`detail_panel._breakdown` all filter `confidence.in_(('high','medium'))` — so they
see the `high` rows only, while `bucket.mention_count` includes the promoted ones.
A post whose tickers were *all* low is never stored at all, so its promoted mention
has no row anywhere.

The eligibility floor consequently reads a smaller author count than the mention
count it is gating.

**Correction, made while planning:** this is *not* a side effect of §2.1, as an
earlier draft of this spec claimed. The journal stores the extractor's verdict —
`high` or `low` — and promotion stays a decision of the rollup, so nothing in the
journal alone tells a reader which bare mentions were vouched for. It needs
`_promote`'s answer written back, and the voice counts re-pointed at the journal
rather than at `radar_mentions`. That is its own task in the plan.

The written verdict is replaceable, not monotonic. Exactly four bare mentions
may be vouched for by one high mention, then a fifth bare mention makes the
whole group incredible under `MAX_BARE_PER_VOUCHER`. Every full-bucket
recompute therefore writes both outcomes: current mediums become
`promoted=True`, and current lows become `promoted=False`. An ever-true flag
would preserve voices that the rollup no longer counts.

### 1.12 A script and the daemon contend for the same budget

`scripts/discover_reddit_sources.py` polls the same `/comments/.rss` feeds at
`SLEEP = 45.0`. The daemon polls one feed per 120 seconds against a budget measured
at `x-ratelimit-remaining = 0.0` after a single request. Run together from one IP
they 429 each other; the daemon's cycle then reports `missing` and writes no buckets.
Nothing in either coordinates.

### 1.13 Minor

- `leaderboard.py:263` hardcodes `max(variance, 0.25)` instead of `VARIANCE_FLOOR`.
- `board.build`'s `min_venues` filter never contributes to `excluded`, though `Board.excluded` is documented as covering the breadth filter.
- `ingest._store_mentioning_posts` calls `_extract_for` twice for every already-stored post, and its docstring claims extraction runs once per post and that history cannot be rewritten. Neither is true.
- `board._tones` uses a fixed 24-hour window (`SERIES_HOURS`) while rows are ranked on 1, 4 or 24 hours, so the tone shown need not describe the window the row was ranked on.
- 4chan is alive but nearly worthless: 20 stored posts in 4.5 days (its `COIN_SYMBOLS_MEAN_STOCKS` entry is `False`, so /biz/'s crypto vocabulary is dropped), against 147,763 zero rows that `score_source` rescores every 15 minutes.

### 1.14 Confirmed clean

`Decimal` does not leak. Every `SUM()` call site coerces at the boundary —
`leaderboard.py:196`, `detail.py:102`, `detail.py:184`, `spend._usd`. Nothing
Decimal-typed reaches float arithmetic or `jsonify`.

---

## 2. The fix design

Five stages, ordered so changes to what is stored land before changes to what reads
it. Each stage is independently shippable.

### Stage 1 — stop the data loss

#### 2.1 A mention journal, and `roll_up` recomputes from it

`roll_up` cannot repair itself by re-reading `radar_posts`, because a post whose
tickers were all `low` is never stored — so stored posts are not a complete record
and recomputing from them would lose promotion.

Add `radar_mention_events`: one row per extracted `buckets.MentionRow`.

| column | type | note |
|---|---|---|
| source | String(24) | |
| external_id | String(128) | |
| ticker | String(12) utf8mb4_bin | |
| created_utc | DATETIME(6) | |
| bucket_start | DATETIME(6) | denormalised, indexed with ticker |
| author | String(64) nullable | |
| simhash | BIGINT unsigned | |
| confidence | Enum(high, low) | pre-promotion |
| sentiment | Float nullable | |
| engagement | Float | |

Unique on `(source, external_id, ticker)`. Index on `(ticker, bucket_start)`.

`roll_up` then:

1. upserts the cycle's events,
2. loads **every** event for each touched `(ticker, bucket_start)`,
3. runs `_promote` over that complete set rather than a cycle slice,
4. writes the bucket totals.

This makes rollup idempotent and self-healing: a cycle that dies mid-bucket no longer
leaves a truncated total behind, and `_promote`'s docstring claim that the window is
the bucket becomes true.

Volume at current rates: ~22k events/hour, ~1.07M rows at 48-hour retention, roughly
120 MB with indexes. VPS disk is 116 GB at 5%.

The extraction decision is unchanged, but the stored-count population is not:
production shows the old rollup understated Bluesky by 14.1% and Reddit by
16.0%, rising to 42.9% in the busiest buckets. A `ROLLUP_GENERATION` therefore
participates in `source_config_version`. Baselines, profiles and board rows from
the old aggregation generation must not mix with corrected rows. The scorer
uses current-generation rows both to build the baseline and as the only rows it
writes scores onto; the weekly profile is current-generation too.

Before the first post-migration cycle, bootstrap the 48-hour journal from the
retained `radar_posts` x `radar_mentions` rows. This exactly recovers stored
high mentions and any low mentions belonging to an otherwise-stored post. A
low-only post was never retained and remains unrecoverable. The bootstrap is
idempotent on the journal's `(source, external_id, ticker)` key and runs before
the scheduler starts, so the first rebuild cannot replace an old full bucket
with only the post-deploy cursor slice.

Startup also clears incompatible score fields before fetchers or the scheduler
can run. If bootstrap recovers zero rows while the overlap window contains a
legacy bucket with observed high-confidence mentions, startup fails closed;
that state is evidence loss, not a quiet period. A fresh or genuinely quiet
database may continue. The scorer repeats score invalidation defensively only
inside its active lookback.

Whenever `roll_up` restamps an existing child row from a NULL or different
generation to the current one, it clears `expected`, `variance`, `mention_z`
and `baseline_days` first, regardless of status. Same-generation `ok` refreshes
may preserve scores. This prevents an old score from being relabelled as
current merely because new counts were written onto the row.

**Backfill.** Recompute `high_confidence_count`, `mention_count`,
`distinct_authors`, `distinct_text_ratio` and `engagement_weighted_count` for the
existing window from `radar_posts` × `radar_mentions` — the same query that measured
the loss. Promoted `medium` mentions are unrecoverable, because the events that
created them were never written anywhere. The repair is therefore partial by
construction; the unrecoverable half is `low`-derived and `low_count` is read by no
surface. Accepted, and recorded here so it is not rediscovered as a bug.

#### 2.2 Clearing scoring columns on a status rewrite

When `roll_up` writes a child row whose status is not `ok`, set `expected`,
`variance`, `mention_z` and `baseline_days` to NULL. One backfill `UPDATE` for the
399 existing rows.

#### 2.3 Wire `single_letter_cashtags_allowed`

`ingest._extract_for` passes `allow_single_letter=config.single_letter_cashtags_allowed(raw.source)`.
Bumps `source_config_version` — correctly this time, because it changes which
mentions count.

#### 2.4 Delete `PAGE_CAP`

#### 2.5 A test that config cannot go dead again

A test that introspects `features.radar.config` for public callables and mappings and
asserts each is **reachable** — either from a call site elsewhere under
`features/radar/`, `personal_apps/` or `scripts/`, or from another `config` member
that is itself reachable. The second clause matters: `COIN_SYMBOLS_MEAN_STOCKS` has
no external reference and is not dead, because `coin_collision_dropped` reads it and
is called from `ingest`. A test without the transitive clause would flag it and be
disabled within a week.

The reachability check runs against the *source text* of the importing modules, not
against runtime coverage, because the failure mode is a name that is imported and
never invoked on any code path.

Four instances of this defect class have now shipped; this is the only fix that
prevents a fifth. Exemptions must be explicit and annotated in the test, not silent.

### Stage 2 — sources that misrepresent themselves

#### 2.6 Retire StockTwits

Diagnosed as a Cloudflare bot challenge (§1.5), not repairable without defeating it.

- Remove `'stocktwits'` from `config.SOURCES` and from the UI source list.
- Remove `sources/stocktwits.py`, `_stocktwits_fetcher`, `STOCKTWITS_REQUESTS_PER_HOUR`, `SYMBOL_BUDGET_PER_CYCLE`.
- Remove its entries from `BARE_TOKENS_ALLOWED`, `SINGLE_LETTER_CASHTAGS`, `COIN_SYMBOLS_MEAN_STOCKS`, `SOURCE_KIND`.
- `COIN_SYMBOLS_MEAN_STOCKS` then has no `True` entry and `coin_collision_dropped` always drops — so 49 real tickers lose their bare and cashtag mentions on every live source. **Revised while planning:** keep it a map rather than collapsing it to a constant, as an earlier draft said. Telegram is the next source and will need its own entry, and the extension point is the point. Annotate the consequence, and pin the override with a monkeypatched test so the mechanism stays covered with no live source using it.
- `scheduling.MIN_INTERVAL` / `MAX_INTERVAL` are documented as StockTwits-shaped and are overridden by every remaining caller. Re-document as generic defaults.
- `scheduling.retire_untracked`'s prohibition ("StockTwits must never call this") loses its subject. Rewrite the reason in terms of the property — a source whose configured list is not exhaustive — rather than the vanished example.
- Every surviving source is `forum`, so `MIN_DISTINCT_CHANNELS`, `_distinct_channels` and `_VOICE_FLOOR['broadcast']` become unexercised by any live source. **Keep them** — they exist for the Telegram work already in the working tree — but annotate that no live source covers them.

Bumps `source_config_version`.

#### 2.7 Score `truncated` buckets

Reddit produces four elevated rows in 4.5 days because 90% of its buckets are
excluded from scoring entirely.

After the per-subreddit source split in §2.8, `scoring.score_source` scores
`truncated` rows using baselines built from `ok` rows
only (`baselines.usable` is unchanged), and those rows keep the `partial` mark. An
undercounted observation against a correctly-scaled expectation biases z **downward**,
so the error is conservative, and the mark is what tells the reader.

`profile.build_profile` continues to exclude `truncated` — a known undercount cannot
describe what normal looks like.

Depends on §2.2 and §2.8: stale z values must be cleared first, and a
subreddit's own incomplete observation must be separated from the aggregate
Reddit status before it becomes scoreable.

#### 2.8 Per-subreddit sources

`source` becomes `reddit:wallstreetbets` rather than `reddit` — 21 characters against
a `String(24)` column. The longest configured sub is `smallstreetbets` at 22
characters prefixed, which still fits, but the margin is two characters. Widen
`RadarBucketSource.source` and `RadarPollState.source` to `String(48)` as part of this
change rather than discovering the ceiling when a longer sub is added; the column
width is not a constraint worth defending.

This stops one sub's permanent feed rollover from marking every other sub's buckets
truncated, and gives the per-subreddit baselines `sources/reddit.py` already says it
wants.

Requires prefix-aware lookup in `config.source_kind`, `bare_tokens_allowed`,
`bare_token_confidence` — a `source.split(':', 1)[0]` fallback, so an unlisted sub
inherits Reddit's policy rather than the strict default.

`routes/api.parse_query` validates against `SOURCES`; it must accept a prefixed name
whose root is a known source. The UI keeps offering `reddit` as one chip, which
expands to the prefixed set.

Bumps `source_config_version`.

### Stage 3 — the remaining absences

- `sources/reddit.fetch_one` returns rate `None`, not `0.0`, when no entry parses.
- `ingest.run_cycle` sets `depths[source] = None` on a failed fetch.
- `spend.cost_micros` returns `None` for an unpriced model. `record` stores NULL rather than 0. `summary()` reports unpriced token counts beside the dollar figures, so a model swap cannot read as free.
- `detail._watched_from_index` gains the interior-gap handling `board._covered_hours` already has: a slot with no bucket row for any ticker on any selected source is null, not zero.
- `board.build`'s `min_venues` filter increments `excluded['one_venue']`.
- `leaderboard.py:263` uses `VARIANCE_FLOOR`.
- `ingest._store_mentioning_posts` extracts **once** per post per call, caching the result across its two loops instead of calling `_extract_for` twice. The docstring's stronger claim — that a post is never re-extracted, so a stopword change cannot rewrite history — is made true by §2.1: the journal row is written on first sight with the confidence that applied then, and a later cycle seeing the same post upserts an identical key rather than re-deciding it.

### Stage 4 — the tone pass earns its bill

#### 2.9 `detail_panel._breakdown` reads the model verdict

Join `RadarMention.llm_sentiment` and apply the same precedence `board._tones` uses:
a model verdict outranks the lexicon; `unclear` votes neither way and blocks the
lexicon; NULL falls back to the lexicon.

This is the smallest change that puts 11,789 paid-for verdicts on a surface that
already exists.

#### 2.10 Surface the disagreement

A post the lexicon reads bullish and the model reads bearish is a post being
sarcastic. Both scores are kept precisely so that comparison is possible, and nothing
performs it. Add the disagreement count to the detail breakdown.

#### 2.11 Render `tone` on the board row

`TickerRow` draws nothing for a field the payload already carries. Visual work —
goes through the `impeccable` skill, not implemented inline. Green and red remain
reserved for price direction; tone needs its own encoding.

#### 2.12 Make `provisional` mean something

Fix `span.days` truncating a sub-day span to zero — report fractional days or hours.
Then split the mark: "thin history" and "config changed recently" are different
facts, and only the first is about the ticker. A badge that fires on 100% of rows is
not a badge.

#### 2.13 Correct the cost record

The docstring's estimate (1,335 mentions/day, ~$0.20) is 5x low on volume and 6x low
on cost against the measured 6,880 items and $1.24. Correct it, and decide whether a
daily spend ceiling is wanted beside the existing per-pass `PASS_LIMIT`.

### Stage 5 — operational

- `scripts/discover_reddit_sources.py` refuses to run while `radar_ingest` is active, unless passed an explicit override flag. It shares an IP and a one-request-per-window budget with the daemon.
- `retention` prunes `radar_mention_events` at 48 hours.

---

## 3. Testing

Each stage carries regression tests written against the failure, not the fix.

- **§2.1** — the sequential-poll test that currently fails (`test_a_second_poll_inside_one_bucket_erases_the_first`). `tests/test_radar_buckets.py:108` is rewritten so its second call is a disjoint slice rather than a superset; the superset case stays as a separate test for genuine overlap.
- **§2.2** — a bucket scored `ok`, then rewritten `truncated`, has NULL scoring columns.
- **§2.3** — `$M` on Bluesky yields nothing; on a source with the flag set it yields Macy's. Plus §2.5's call-site test, which would have caught it.
- **§2.6** — no module imports `sources.stocktwits`; `source_config_version` changes.
- **§2.7** — a truncated bucket receives a z computed from `ok`-only baselines and carries `partial`.
- **§2.8** — two subs, one truncated, and the other's buckets stay `ok`.
- **Stage 3** — one assertion per absence: `None` in, `None` out, for each of the four.
- **§2.9** — a mention with a model verdict opposite to its lexicon score is counted the model's way in the breakdown.

The known trap from prior work applies: an assertion whose passing state is an
absence proves nothing until it has been shown to fail. Every test above that asserts
a NULL or an exclusion must be run against the unfixed code first.

---

## 4. Decisions recorded

- **StockTwits is retired, not repaired.** Cloudflare bot challenge, identical from two networks; defeating it is out of scope.
- **The §2.1 backfill is partial.** Promoted `medium` mentions in existing history are unrecoverable. Accepted.
- **`truncated` buckets become scoreable but never enter baselines or the hour profile.** The undercount biases z downward, which is the safe direction; the `partial` mark carries the caveat.
- **The broadcast path stays despite having no live source.** It exists for Telegram.
- **Not revisited:** using a model to judge whether a token is a ticker (measured and killed — volume-gating selects the junk); dropping either the lexicon or the model sentiment score (their disagreement is the sarcasm detector); green or red for anything but price direction.

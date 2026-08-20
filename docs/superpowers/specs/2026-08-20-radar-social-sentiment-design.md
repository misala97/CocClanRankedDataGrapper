# Radar — social-sentiment stock discovery dashboard

**Date:** 2026-08-20
**App:** `personal_apps`
**Branch:** `dev_personal`
**Database:** MariaDB / InnoDB (production), MySQL 8 (dev)
**Status:** design approved, revision 3 (Reddit closed; sources re-measured)

---

## 1. What this is

A discovery radar for day-trading candidates, driven by online chatter. It
ingests posts and comments from Reddit and StockTwits, extracts stock tickers,
measures how unusual each ticker's mention volume is against its own history,
compares that against the ticker's price move over the same window, and ranks by
the gap between the two.

The question it answers: **what is people talking about far more than usual,
that the price has not yet reflected?**

### Scope boundary

This is a data tool. It surfaces mention volume, sentiment and price context. It
does not recommend trades, does not produce price targets, does not size
positions, and never places an order. Every number on it is a description of
what was observed, not advice.

### Non-goals for v1

- Push alerts on spike (deliberately deferred; the VAPID infrastructure exists
  and can carry it later)
- X/Twitter ingest — see §3.1
- Any form of order placement, broker integration, or portfolio tracking

---

## 2. Product decisions

| Decision | Choice |
|---|---|
| Core job | Discovery radar — surface unknown tickers spiking now |
| Sources v1 | Reddit + StockTwits |
| Ranking | Divergence — bounded transform of mention_z minus bounded transform of \|price_move_z\| |
| Price data | Daily close + intraday quote, radar top-N only |
| Sentiment | Lexicon on everything, Claude Haiku re-read on radar top-N |
| Ingest cadence | Tiered by US market session |
| v1 surfaces | Radar leaderboard, ticker detail, spike history log |
| UI language | English |
| Frontend | React island, Recharts for charts |

### 2.1 Build order

The scoring layer's correctness depends on baselines, and a wrong baseline takes
30 days to age out. Everything in §4, §5 and §6 lands **before first ingest**.
§7's threshold versioning also lands before first ingest, because retrofitting it
means the earliest spikes have no version to be evaluated against.

§6.5 (LLM sentiment), §8.2 (IPO panel) and the P1-tier refinements marked in
place below can land after v1 is running.

---

## 2.2 Revision 3 — the source layer was rebuilt on measurement

Reddit closed self-serve API access in November 2025 under its Responsible
Builder Policy. Confirmed three ways: app creation returns a policy pointer
instead of an app; the public JSON endpoints return 403 to every client that is
not a browser, including one sending a full Chrome user-agent; and the public
support form has no Data API category at all. Getting past that would mean
defeating bot detection, which is circumventing an access control and is out of
scope permanently.

**Reddit is removed as a source.** Only `sources/reddit.py` was Reddit-specific
— extraction, fingerprinting, sentiment, rollup, retention, the market calendar
and the daemon never knew where posts came from, and all of it stands.

Replacements were then **measured rather than argued about**, against the one
question that matters: does the source clear the §6.3 eligibility floor.

| Source | Result | Decision |
|---|---|---|
| StockTwits | 30 trending symbols; median 23.4 msgs/hr; 20–27 distinct authors per 30 messages; ~50% carry native bull/bear | **Primary source** |
| 4chan /biz/ | **Zero** cashtags across 201 catalog threads — crypto culture, not equities, and no `$TICKER` notation | **Rejected** |
| Bluesky | Public search returns 403; needs a self-serve app password (no approval gate) | Pending measurement |

### What this costs

StockTwits' discovery surface is its trending list — **30 symbols someone else
already ranked**. A StockTwits-only radar is therefore closer to "of the things
being discussed, which have not moved yet" than to "surface something nobody has
noticed". The divergence metric (§6.4) is unaffected and remains the product's
core; the discovery half narrows. §3.5's standing set is what widens it back.

---

## 3. Data sources

### 3.1 Why not X/Twitter

As of February 2026, X closed Basic and Pro tiers to new signups and moved new
developers to pay-per-use at **$0.005 per post read**. The free tier is gone. A
broad discovery radar reading on the order of 20k posts/day would cost roughly
$3,000/month. X is therefore out of v1.

The source interface (§4.1) is built so X — or a third-party X data reseller —
can be added later as one new module without touching anything downstream.

### 3.2 Reddit — closed

See §2.2. Retained in this document only so the decision is not relitigated.
The `sources/` interface still accepts it if access is ever granted.

### 3.3 StockTwits — primary source

Free, unauthenticated, and reachable: `trending/symbols.json` and
`streams/symbol/{SYMBOL}.json` both return 200 with no credentials. Twenty
consecutive requests drew no 429, so the ceiling is well above burst size;
ingest budgets **150 requests/hour** against an undocumented limit and backs off
adaptively on 429 rather than assuming a number.

Two properties beyond raw volume:

1. Messages are already `$TICKER`-tagged, so no extraction guesswork.
2. Roughly half carry a native bull/bear label — free sentiment ground truth
   to calibrate the lexicon (§6.11) against.

**Crypto is filtered out.** Roughly a third of trending is crypto (`BTC.X`,
`XRP.X`, `ETH`). Symbols ending `.X` or otherwise flagged crypto are dropped at
ingest: crypto trades 24/7, which breaks the session-tiered cadence (§4.3), the
market-clock forward returns (§7.3) and the SPY baseline (§7.3) simultaneously.
Supporting it properly means a parallel set of rules, and that is not this
version.

### 3.5 Poll cadence is per symbol, driven by message rate

The API returns **30 messages regardless of timespan**, so a fixed interval is
wrong in both directions at once. At 5.8 msgs/hr, MSFT's 30 messages cover five
hours and polling every 15 minutes refetches the same data twenty times. At 63
msgs/hr, BTC.X burns through 30 messages in 28 minutes and an hourly poll loses
data permanently.

```
coverage_hours = 30 / observed_msgs_per_hour
poll_interval  = clamp(coverage_hours * 0.5, 15min, 4h)
```

The rate is measured per symbol from its own returned messages and stored, so
the schedule self-corrects: a symbol that heats up is automatically polled
faster before anything is missed. This is what makes a standing set of several
hundred symbols fit inside the request budget.

Three tiers share that budget:

| Tier | Membership | Purpose |
|---|---|---|
| Trending | the 30 from `trending/symbols.json` | discovery |
| Active | anything that trended recently, or is currently spiking | the working set |
| Standing | a few hundred by market cap, round-robin | baseline history for the long tail |

The standing set exists because a z-score needs history. A symbol first seen the
day it spikes has no baseline and can only ever be `provisional` (§6.8).

**Volume reality:** outside the trending set most symbols produce fewer than 10
messages/hour, so the 1h window (§6.9) is marginal for them and the 4h/24h
windows carry the signal. 15-minute buckets remain the storage grain; the
eligibility floor is judged per window, not per bucket.

### 3.6 Bluesky — pending measurement

Public search endpoints return 403 unauthenticated, but Bluesky issues **app
passwords self-serve** — generated in account settings, no approval, no review.
That is a credentialed path, not a circumvention, and it is the difference
between Bluesky and Reddit.

Its role would be the one StockTwits cannot fill: broad, non-finance-native
discovery, where an unknown ticker surfaces before it trends anywhere. It is not
built until measured against the same floor that rejected 4chan.

### 3.4 Prices

A free-tier market data provider (Finnhub-class, ~60 calls/min):

- intraday quote for radar top-N tickers, 2-minute cache
- daily close for all tickers with recorded mentions
- company profile (market cap, exchange, IPO date, average volume), refreshed
  weekly, feeding the segment filters
- **earnings calendar**, feeding `next_earnings_date` on the same weekly job
- IPO calendar, feeding the upcoming-IPO panel
- SPY daily/intraday series, for the excess-return baseline in §7.3

Every quote snapshot stores `quote_ts` and `quote_volume` alongside the price.
Those two fields are what §6.4's no-print detection reads; a quote without them
is unusable for scoring.

---

## 4. Ingest pipeline

### 4.1 Source interface

Each source module exposes one function returning normalized records:

```
fetch(since: datetime) -> FetchResult

RawPost:
  source        'reddit' | 'stocktwits'
  external_id   provider's own id
  channel       subreddit name, or stocktwits stream
  author        provider username
  created_utc   datetime
  title         str | None
  body          str
  score         int      upvotes / likes
  num_comments  int
  url           str
  native_tickers   list[str]   populated by StockTwits, empty for Reddit
  native_sentiment str | None  StockTwits bull/bear, else None

FetchResult:
  posts         list[RawPost]
  status        'ok' | 'missing' | 'truncated'
  catchup_depth int    pages walked this cycle
```

`status` is per source per cycle and is what §4.5 writes onto buckets. A source
that returns rows is not automatically `ok` — hitting the page cap makes it
`truncated`.

Dedup on a unique index over `(source, external_id)`. Re-fetching an already
stored post updates its score and comment count, since engagement grows after
first sight (§5.5.10 for the upsert).

**Deleted posts.** On refetch, if a post is deleted or removed upstream, blank
`body` and `title` but keep the mention rows and bucket counts. The aggregate
fact that it was mentioned is not the problem; retaining the text of a deleted
post is.

### 4.2 Ticker extraction

Extraction is the highest-risk component: it produces false positives
constantly, and every false positive becomes a fake spike.

A `ticker_universe` table holds symbol, company name, exchange, and the profile
fields from §3.4, seeded from a free symbol listing and refreshed weekly.

**Symbols are stored `utf8mb4_bin` (§5.5.6), so lookups are case-sensitive.
Every candidate token must be uppercased before it is looked up.** Without that
normalization, any lowercase-derived match misses silently — no error, just a
mention that never gets counted.

Matching, in confidence order:

| Pattern | Confidence |
|---|---|
| `$AAPL` cashtag | high |
| Bare `AAPL` with company name elsewhere in the same post | high |
| Bare `AAPL` matching universe, not in stopword blacklist | medium |
| Bare token in stopword blacklist | rejected |

The stopword blacklist covers English words and trading slang that collide with
real symbols: `IT ON ALL FOR ARE CAN NOW ONE OUT NEW DD CEO CFO EPS ATH IMO
USA GDP PM AM EOD OTM ITM FD YOLO PUMP HOLD BUY SELL PUT CALL` and similar. It
is data, not code, and is expected to grow.

Only `high` and `medium` mentions are counted. Confidence is stored per mention
so the leaderboard can require high-confidence support before a ticker is
eligible.

**Symbol reuse.** A delisted symbol later reassigned to a different company
inherits the old company's baseline — rare, and silent when it happens.
`ticker_universe` carries `first_seen` and `delisted_at`; a reassignment resets
the baseline rather than continuing it.

### 4.3 Cadence and catch-up

An APScheduler daemon, `run_radar_ingest.py`, mirroring the deployed
`run_gym_notifier.py` pattern.

| Window (US market clock) | Interval |
|---|---|
| Pre-market | 3 min |
| Regular session | 3 min |
| After-hours | 10 min |
| Overnight / weekend / market holiday | 30 min |

**Pagination is not optional.** 100 items per listing request at a 3-minute
cadence is comfortable at rest; r/wallstreetbets during a squeeze produces more
comments than that per cycle. Without catch-up, ingest silently truncates
exactly when the signal is real, and the truncation leaves no trace in the data.

- Paginate backwards using the **`after`** fullname until an already-stored item
  is reached, with a hard page cap per cycle. `after` walks a `/new` listing
  towards older items; `before` returns items *newer* than the given fullname
  and would loop on an empty page instead of catching up.
- Hitting the cap marks the affected buckets `truncated` (§4.5).
- Log per-cycle `catchup_depth`. Sustained deep catch-up means the cadence needs
  raising, and that must be visible without querying the database.

### 4.4 Timezone handling

**Store UTC. Compute session windows in `America/New_York`. Render in
`Europe/Berlin`.**

The EU and US switch daylight saving on different dates — roughly three weeks
each spring and one each autumn where the offset between them differs from
normal. Hardcoding German clock times for session boundaries would mis-tier the
ingest cadence during exactly those weeks. Session state derives from the NY
exchange calendar, including holidays and early closes; display converts at the
last moment.

Datetime storage rules are in §5.5.4 — `DATETIME(6)` holding UTC, connection
time zone pinned to `+00:00`. `TIMESTAMP` is prohibited here precisely because
it converts against the session time zone and would break this rule the moment a
connection opened with a different setting.

### 4.5 Gap handling, per source

If a source is unavailable or truncated, **its own** buckets record that — not
the bucket as a whole.

A single `status` column cannot express this. With two sources and one column,
StockTwits dropping while Reddit keeps working forces a choice between marking
the bucket `missing` (discarding good Reddit data) and marking it `ok` (silently
halving the count) — the second being exactly the baseline poisoning this
section exists to prevent.

Fixed per-source columns cannot express this once sources are a *set* rather
than a pair. Two sources meant eight columns (`count_`, `status_`, `mention_z_`,
`baseline_days_` each); a third makes twelve, every new source is a migration,
and — decisively — a **user-selectable subset of sources (§8.6) has to be pooled
at query time**, which fixed columns cannot do.

So per-source data lives in its own row, in `radar_bucket_sources` (§5.4), keyed
`(ticker, bucket_start, source)`. Scoring is per source before it is combined
(§6.2), and combining an arbitrary subset is then a `GROUP BY` rather than a
schema change.

| Status | Counted live? | In baseline? |
|---|---|---|
| `ok` | yes | yes |
| `missing` | no | no |
| `truncated` | **yes**, marked partial | no |

`truncated` counts live because an undercounted spike is still a spike, but it
must never enter a baseline it would understate.

---

## 5. Storage

Three layers. Models live in the shared `personal_apps/models.py`, following
this repo's existing convention.

### 5.1 `radar_post`

One row per ingested post or comment: the `RawPost` fields plus first-seen and
last-updated timestamps, plus a **64-bit simhash of the normalized body**
(§6.7).

`body` is `MEDIUMTEXT` — see §5.5.2.

**Retention: 30 days rolling**, deleted in chunks (§5.5.9).

### 5.2 `radar_mention`

One row per (post × ticker): ticker, confidence, lexicon sentiment score, LLM
sentiment (nullable, filled later for top-N only).

**Retention: 30 days rolling**, following its post.

### 5.3 `radar_bucket`

The queryable layer. One row per (ticker × 15-minute bucket):

- `mention_count`, `high_confidence_count`
- `distinct_authors`
- `distinct_text_ratio` — distinct simhashes / mention count (§6.7)
- `engagement_weighted_count`
- `sentiment_mean`, `sentiment_stdev`
- `sources_ok` — how many sources reported `ok` for this bucket
- `source_config_version` (§6.6)

These are the **all-sources** totals: the fast path for the default view. The
per-source breakdown lives in `radar_bucket_sources` and is what a selected
subset reads (§8.6). The redundancy is deliberate — the default view is hit
constantly and should not pay for a join.

**Retention: forever**, partitioned monthly (§5.5.8). Rows are small and this is
what every score, chart and baseline reads. Raw text ageing out does not damage
history.

### 5.4 `radar_bucket_sources`

One row per (ticker × bucket × source). This is what makes the source set open
rather than fixed, and what a UI-selected subset (§8.6) aggregates over.

Key `(ticker, bucket_start, source)`. Columns: `mention_count`,
`distinct_authors`, `distinct_text_ratio`, `engagement_weighted_count`,
`sentiment_mean`, `status` (`ENUM('ok','missing','truncated')`), and — written
by the scoring layer — `expected`, `variance`, `mention_z`, `baseline_days`.

Storing `expected` and `variance` alongside `mention_z` is what lets §6.2 pool
any subset correctly. A weighted mean of z-scores would be wrong; summing the
components is not.

**No foreign key to `radar_buckets`.** InnoDB does not support foreign keys on
partitioned tables, and `radar_buckets` is partitioned monthly. This table is
partitioned on `bucket_start` identically and joined on `(ticker,
bucket_start)`. Retention and partition maintenance must therefore treat the two
tables as one unit — nothing enforces that relationship for us.

### 5.5 MariaDB specifics

Production is MariaDB; dev is MySQL 8. Each item below is a failure that shows
up in production rather than in tests.

1. **Charset.** Every table `CHARACTER SET utf8mb4`. MariaDB's `utf8` alias is
   utf8mb3 and will reject or mangle 4-byte characters. WSB posts are full of
   emoji, and a rejected insert is a silently dropped mention.
2. **Body column size.** Reddit self-posts run to 40,000 characters — up to
   160 KB under utf8mb4, over the 64 KB `TEXT` limit. `radar_post.body` is
   `MEDIUMTEXT`.
3. **Strict mode.** `sql_mode` must include `STRICT_TRANS_TABLES`. Silent
   truncation of a post body corrupts ticker extraction invisibly downstream.
4. **Datetimes.** `DATETIME(6)` holding UTC; `time_zone = '+00:00'` set on every
   connection. `TIMESTAMP` is prohibited (§4.4).
5. **Prices.** `DECIMAL(18,6)`, never float. Return arithmetic accumulates
   drift, and the history log is the last place that belongs.
6. **Symbol collation.** `radar_bucket.ticker` and `ticker_universe.symbol` are
   `utf8mb4_bin`. Default collations are case-insensitive and would match
   unintended rows. This makes uppercase normalization in §4.2 mandatory.
7. **Indexes.**
   - `radar_bucket`: unique `(ticker, bucket_start)`; secondary
     `(bucket_start, ticker)` for the cross-sectional leaderboard read
   - `radar_post`: unique `(source, external_id)`; index `(created_utc)` for
     retention
   - `radar_mention`: `(ticker, post_id)` and `(post_id)`
8. **Partitioning.** `radar_bucket` partitions by RANGE on `bucket_start`,
   monthly. The unique key already includes the partition column, so this is a
   clean addition, and it keeps the 30-day baseline scan inside one or two
   partitions.
9. **Retention deletes.** Chunked:
   `DELETE FROM radar_post WHERE created_utc < ? ORDER BY created_utc LIMIT 5000`
   in a loop with a short sleep. A single unbounded 30-day delete locks the
   table and writes one enormous transaction.
10. **Upsert.** The §4.1 refresh is `INSERT ... ON DUPLICATE KEY UPDATE
    score = VALUES(score), num_comments = VALUES(num_comments),
    last_seen = VALUES(last_seen)`.
11. **Connections.** The daemon idles up to 30 minutes overnight and will meet a
    dropped connection. SQLAlchemy engine with `pool_pre_ping=True` and
    `pool_recycle` below the server's `wait_timeout` — the same settings
    `app.py` already uses.

---

## 6. Scoring

### 6.1 Mention rate and z-score

Two failure modes are guarded here, and both were found by getting the naive
version wrong first.

**Intraday shape.** Chatter volume has a strong daily and weekly profile.
Comparing 03:00 against 16:00 as one population makes every afternoon look like
a spike.

**Variance that does not scale with level.** A single pooled residual standard
deviation is dominated by busy-hour residuals. Under a pooled stdev, a 03:00
bucket with expected 0.3 and observed 6 divides by roughly 4 and reads z ≈ 1.4;
under a count model it is z ≈ 10. Pooled stdev therefore systematically hides
overnight and weekend spikes — a meaningful share of exactly what this tool
exists to catch.

```python
# hour_share: market-wide share of weekly mention volume in each
# bucket-of-week. 96 buckets/day x 7 = 672 buckets. Sums to 1.0 over a week.

# usable = buckets in the trailing 30d that are all of:
#   - not `missing` and not `truncated` for this source
#   - not inside an open radar_spike
#   - sharing the current source_config_version
observed_mass = sum(hour_share(b) for b in usable)      # ~4.29 if nothing dropped
ticker_rate   = sum(count(b) for b in usable) / observed_mass    # mentions per week

expected = ticker_rate * hour_share(bucket)
variance = expected + expected**2 / k                   # negative binomial
z        = (observed - expected) / sqrt(max(variance, FLOOR))
```

`hour_share` is a **weekly** normalization and `ticker_rate` is therefore a
weekly rate. Stating both explicitly avoids the unit ambiguity that a "daily
mean times hour share" formulation invites. 30 days / 7 = 4.2857, which is
`observed_mass` when nothing is dropped.

**Dividing by `observed_mass` rather than by a bucket count is what makes gap
handling and spike exclusion correct rather than merely non-fatal.** Dropping
buckets removes their share from the denominator, so the rate estimate stays
unbiased regardless of which buckets were dropped.

`k` is the negative-binomial dispersion, estimated per ticker by method of
moments over the window and clamped, with a global fallback for thin tickers.
**The upper clamp is the operative guard, not a formality.** Estimating `k` on
spike-excluded buckets biases it upward — variance looks smaller than reality —
which shrinks the denominator, produces more spikes, and excludes more buckets
on the next pass. The upper clamp is what stops that loop from running away.

This count model subsumes the low-count stdev floor. The absolute-count and
distinct-author eligibility gates in §6.3 stay; the separate stdev floor is
dropped.

### 6.2 Combining sources

Each source is scored against **its own** baseline, producing a `mention_z` per
source in `radar_bucket_sources` (§5.4) for display. Nothing enumerates sources
by name — the set is open, and a new source is a config entry plus one module.

The combined figure pools the underlying counts rather than averaging the
z-scores — z-scores are not additive, and a weighted mean of them has no clean
interpretation:

```python
# over sources whose status this bucket is `ok` or `truncated`
expected_total = sum(expected(s) for s in available)
observed_total = sum(observed(s) for s in available)
variance_total = sum(variance(s) for s in available)

mention_z = (observed_total - expected_total) / sqrt(max(variance_total, FLOOR))
```

A `missing` source drops out of all three sums — no imputation, no zero
substitution — and the result remains a properly scaled z. `sources_ok` is
stored so the UI can mark single-source readings, which are weaker evidence than
the same z from both.

### 6.3 Eligibility

A ticker is radar-eligible only above all of:

- a minimum absolute mention count in the window
- a minimum **distinct author** count
- a minimum `distinct_text_ratio` (§6.7)

Distinct authors defeats one account posting fifty times. Distinct text ratio
defeats fifty accounts posting the same thing, which is the actual shape of a
brigade and which the author gate cannot see at all.

### 6.4 Divergence — the primary metric

Two corrections to the naive `mention_z − price_move_z`:

**The terms are not comparable in scale.** Mention counts are heavy-tailed —
expected 2, observed 40 produces a z in the teens. Price moves normalized by
volatility rarely exceed 4–5σ. A raw subtraction is dominated by the mention
term, the "price already ran" case barely deducts anything, and ranking by
divergence collapses into ranking by `mention_z`.

**Price must enter as magnitude.** With a signed term, a ticker at −4σ scores
*higher* than one genuinely flat, and the top of the board fills with things
already dumping. "The price has not yet reflected it" is a magnitude claim.

```python
m = tanh(mention_z / K_M)              # K_M default 4.0
p = tanh(abs(price_move_z) / K_P)      # K_P default 2.0
divergence = m - p                     # bounded (-1, 1)
```

`K_M` and `K_P` are config constants (§12.3). The transform is for **ranking
only** — raw `mention_z` and the signed `price_move` stay on the row unchanged.

Cross-sectional percentile ranking is explicitly rejected as an alternative:
percentiles change meaning day to day, so on a quiet Sunday the 99th percentile
is nothing and the leaderboard would always look equally exciting.

| Mentions | Price | Divergence | Reading |
|---|---|---|---|
| far above normal | flat | **high positive** | loud and unmoved |
| far above normal | far up | **negative** | price already ran |
| far above normal | far down | **negative** | loud and dumping |
| normal | far up | **low** | move without chatter — out of scope |

A `price_direction` mark (`up` / `flat` / `down`) sits on the row so the
loud-and-dumping case is visible at a glance rather than inferred from a signed
column.

### 6.5 No-print detection

A halted stock has a frozen last price, so `price_move` reads ≈0 while mentions
explode *because* it halted. That is maximum divergence produced entirely by an
artifact — and halts cluster on exactly the micro caps that will dominate this
board.

The same signature is produced by a stock so illiquid nobody traded it during
the interval. Both are untradeable and both fake the divergence, so both get one
mark — labelled **NO PRINT** rather than HALT, because the data cannot
distinguish a halt from an empty tape and claiming otherwise would overstate it.

- If `quote_ts` and `quote_volume` are both unchanged across ≥2 consecutive
  polls within a session window, set `price_status = 'stale'`.
- Stale rows render with the NO PRINT mark and **no divergence value**. They are
  not ranked, and they are not hidden from the table.
- `price_status` carries onto `radar_spike` so §7.4 can exclude them from
  aggregates.

### 6.6 Source config versioning

The active source configuration — subreddit list plus StockTwits streams — is
hashed into `source_config_version` on every bucket.

Baselines are computed only over buckets sharing the **current** version. Adding
a subreddit otherwise shifts every ticker's trailing mean overnight and
manufactures a market-wide spike the next morning. A version change starts a
warm-up (§6.8) rather than reading straight through the discontinuity.

### 6.7 Near-duplicate detection

`radar_post` stores a 64-bit simhash of the normalized body.
`radar_bucket.distinct_text_ratio` is distinct simhashes over mention count,
displayed beside distinct authors.

**Scope stated honestly:** exact-hash matching catches copy-paste and low-effort
templating. It does not catch paraphrase. It is not a general bot detector and
must not be described as one.

### 6.8 Cold start and thin baselines

For the first 30 days there is no baseline, and recent-IPO tickers never
accumulate one — unfortunate, since that segment is among the more interesting.

- Shrink the rate estimate toward a segment prior:
  `rate = (n * ticker_rate + n_prior * segment_median_rate) / (n + n_prior)`,
  with `n_prior` equivalent to ~5 days.
- `baseline_days` is stored on the row. Under 14 days renders as
  **provisional** and is excluded from §7.4 aggregates.
- The same treatment applies after a `source_config_version` change (§6.6).

### 6.9 Windows and sustain

z is computed at **1h, 4h and 24h simultaneously**. All three appear on each
row; the user picks which one sorts. Default 4h. A single window is insufficient
in both directions: 1h misses a ticker building steadily over eight hours, 24h
dilutes a fast squeeze into invisibility.

**Sustained is defined over non-overlapping windows.** The three display windows
are nested, so a large 1h spike mechanically lifts the 4h and 24h figures;
"elevated in all three" is close to a restatement of "large 1h spike" and must
not be presented as corroboration. Sustained means **elevated in ≥3 of the last
4 consecutive non-overlapping 1h windows.**

### 6.10 What divergence does not mean

Loud-and-unmoved is not inherently bullish. The identical pattern is produced
by:

- bot or brigade chatter
- a stock too illiquid to fill size in
- a **trading halt** (§6.5)
- a pump whose loud phase is the exit

Distinct-author count, distinct-text ratio, source spread and the NO PRINT mark
are on every row precisely because they separate these cases. All of them stay
visible rather than folded into the score.

### 6.11 Sentiment

**Lexicon on everything.** A finance-tuned VADER-style lexicon scores every
mention at ingest — free, instant, adequate for the long tail.

**Claude Haiku re-read on radar top-N.** Posts belonging to tickers currently on
the radar and not yet LLM-scored are batched to Claude Haiku, which returns
bull/bear/neutral plus a conviction level. WSB runs on sarcasm and inverted
positions ("all in on puts", "this is fine") where lexicons approach coin-flip
accuracy.

Both scores are stored. **Where they disagree, the UI marks the cell** —
disagreement usually indicates sarcasm or an inverted position, so it is
information rather than noise to be resolved away.

**`llm_sentiment` is a selection-biased column and is barred from analysis.** It
exists only for tickers that already made the radar, so any aggregate sliced on
it compares radar tickers against nothing. No aggregate or backtest query may
filter or slice on it; §10 carries a test asserting the history module never
references the column.

---

## 7. Spike history

### 7.1 A spike is an event

A `radar_spike` row opens when a ticker crosses the divergence and eligibility
thresholds. It stays open while the ticker remains elevated and closes after it
falls below for N consecutive buckets. Without this state machine, one squeeze
produces dozens of rows and the log is unreadable.

Recorded at open: ticker, segment, `started_at`, `mention_z`, `divergence`,
distinct authors, distinct text ratio, source spread, `sources_ok`, price,
`price_status`, `days_to_earnings`, `threshold_version`. Peak values update
while open.

Open spikes are excluded from baseline computation (§6.1) — a ticker that
squeezed 10 days ago would otherwise carry an inflated mean and its next spike
would be invisible. This is the same argument §4.5 makes for `missing` buckets,
extended to spikes.

### 7.2 Entry price honesty

The price recorded at spike open is up to one ingest interval plus one cache TTL
stale — five minutes in a fast move. `quote_ts` and `detect_latency_ms` are
recorded on the spike row so the log can state that plainly rather than quietly
reporting an entry nobody could have achieved.

### 7.3 Forward returns

Offsets are session-relative, not wall-clock. A spike detected at 23:00 German
time has no meaningful "+1 hour price" — the market closed an hour earlier.

- next open
- +1 session close
- +3 session closes
- +5 session closes

Each return is stored **three ways**:

1. raw
2. excess vs SPY over the identical window
3. excess vs the same-window median return of the **same segment**

SPY alone is insufficient: raw excess over SPY flatters high-beta names in a
rally, and beta varies systematically by segment — which confounds the "does
this work on micro caps but not large caps" slice specifically, i.e. the slice
most likely to be believed. §7.4 aggregates use the segment-relative figure; the
SPY figure is kept for continuity.

### 7.4 Aggregate view

Hit rate and median segment-relative excess return, sliced by:

- divergence band — did loud-and-unmoved actually outperform already-moved?
- segment
- source spread, and `sources_ok`
- sustained versus single-window
- **earnings proximity** — a large share of mention spikes are scheduled. "Loud
  and unmoved two days before earnings" is a different object from an
  unexplained spike, and mixing them makes every other slice uninterpretable.

**Excluded from aggregates:** provisional rows (`baseline_days` < 14), stale
`price_status` rows, and any slice on `llm_sentiment` (§6.11) or on the lead/lag
mark (§8.1).

**Threshold versioning.** §12.3 tunes thresholds against ingested data, and this
section then evaluates the log using those thresholds — an in-sample hit rate,
which is the one number the sample-size guard exists to keep honest.

- `threshold_version` (string) and `evaluated_out_of_sample` (bool) on every
  spike row.
- Aggregates **group by** `threshold_version` and never pool across versions.
  The UI defaults to the current version and labels earlier ones historical.
- A version is frozen on a date; only spikes opened after that date count as
  out-of-sample for it.

**Sample size appears next to every figure, and any band under n=20 renders as
"thin" rather than as a percentage.** A 3-of-4 hit rate is not 75%, and a
dashboard that prints 75% there will be believed. This guard is what stops the
log from manufacturing false confidence in the tool it exists to audit.

The log is read-only history.

---

## 8. Surfaces

### 8.1 `/radar` — leaderboard

Ranked by divergence, window selectable (1h / 4h / 24h), default 4h.

Per row:

```
SYMBOL · name · divergence · price_direction · mention_z (1h/4h/24h) ·
mentions vs typical · distinct authors · distinct text ratio · sources_ok ·
source spread · days_to_earnings · sentiment split · price % today · sparkline
```

Row marks: **NO PRINT** (§6.5, suppresses divergence), **partial** (truncated
source, §4.5), **provisional** (`baseline_days` < 14, §6.8), **sustained**
(§6.9), **single-source** (`sources_ok` = 1).

A **lead/lag mark** compares when mentions spiked against when price moved:
chatter leading, coincident, or chatter chasing. Cross-correlating 15-minute
buckets over a short window is noisy, so it is **labelled a heuristic in the UI
and §7.4 aggregates never slice on it.**

**Segment filter tabs**, from the weekly profile refresh:

| Tab | Rule |
|---|---|
| Large | market cap > $10B |
| Mid/Small | $300M – $10B |
| Micro/Penny | < $300M or price < $5 |
| Unknown | mentioned but no profile data — OTC, foreign, newly listed |
| Recent IPO | listed within 12 months |

The Unknown bucket is the noisiest and frequently the most interesting; it is a
first-class tab, not a discard pile.

### 8.2 Upcoming IPOs panel

Structurally separate. Pre-listing companies have no ticker, no price and no
mention baseline, so they cannot be rows in the radar table. A small panel fed
by the IPO calendar lists upcoming listings alongside any pre-listing chatter
matched by company name.

### 8.3 `/radar/<ticker>` — detail

- mention timeline overlaid on price, last 7 days, shared x-axis, with
  `missing` and `truncated` intervals visibly gapped rather than drawn as zero
- **quadrant scatter**: x = signed price move σ, y = mention z, all radar
  tickers plotted, upper-middle (loud, unmoved) highlighted
- the actual top posts driving the spike: title, channel, score, timestamp,
  outbound link
- sentiment split over time, with lexicon/LLM disagreement marked
- source breakdown, and per-source z side by side
- this ticker's own spike history, linking into §8.4

### 8.4 `/radar/history` — did-it-work log

Past spikes with their forward returns, plus the §7.4 aggregates, grouped by
`threshold_version`.

### 8.6 Source selector

The leaderboard carries a source selector: which sources feed the ranking is
chosen in the UI, not fixed at build time.

**It is a read-time filter, and never anything more.** The distinction matters
enough to state twice:

- `source_config_version` (§6.6) versions what is **ingested**. Changing it
  starts a baseline warm-up, because the population being measured changed.
- The source selector changes what is **displayed** from data already ingested.
  It must never touch baselines, never start a warm-up, and never write
  anything.

Conflating the two would make every toggle of a checkbox look like a
market-wide spike, which is precisely the failure §6.6 exists to prevent.

Selecting a subset re-pools the per-source components from
`radar_bucket_sources` (§5.4) over the chosen sources only:

```
z = (Σ observed − Σ expected) / sqrt(Σ variance)   over selected sources
```

Rows are marked with which sources actually contributed, since the same
divergence backed by two independent sources is stronger evidence than one
backed by a single source. A ticker no selected source has data for drops out
of the list rather than rendering as a zero — the §4.5 rule, applied at read
time.

### 8.5 Auth

All routes `login_required`. Radar data is **global, not per-user** — mention
data is not personal, and all three accounts see identical rows. No scoping
layer is needed.

---

## 9. Implementation shape

### 9.1 Backend

```
personal_apps/features/radar/
  __init__.py
  routes/
    __init__.py
    _blueprint.py
    leaderboard.py
    detail.py
    history.py
  sources/
    __init__.py
    reddit.py
    stocktwits.py
  extraction.py      ticker matching, stopwords, confidence, normalization
  scoring.py         rates, NB variance, source combination, divergence
  spikes.py          open/close state machine, forward returns
  sentiment.py       lexicon scoring
  llm_sentiment.py   Claude Haiku batch classification
  prices.py          quote/profile/earnings/IPO adapter, no-print detection
  universe.py        symbol listing seed, weekly refresh, reassignment reset
  ingest.py          orchestration, called by the daemon

personal_apps/run_radar_ingest.py    APScheduler daemon
```

Models are added to the existing `personal_apps/models.py`.

### 9.2 Frontend

React island, matching the gym port. React 19, `@tanstack/react-query` for the
polled leaderboard, `zustand` for filter state — all three already dependencies.

**Recharts is added** for the dual-axis timeline and the quadrant scatter. It
renders SVG rather than canvas, which matters: canvas cannot resolve `var()` or
`color-mix()`, so themed colors silently disappear — a failure this codebase has
hit before. The sparkline stays hand-rolled; a 40-point `<polyline>` needs no
library. React 19 support landed in Recharts 3.x; the exact version is pinned at
install.

### 9.3 Vite configuration

The current `vite.config.ts` is gym-specific: `base: '/static/gym/dist/'`,
`outDir: static/gym/dist`, gym-only entries.

Radar gets its **own base path, own outDir and own manifest** —
`/static/radar/dist/` — with `vite_assets.py` growing a per-app manifest lookup.

This is delivered as **one config file**, not two:
`defineConfig(({ mode }) => ...)` keyed on an app env var. Two config files
drift; a single mode-keyed config gives the same isolated outputs, the same
per-app manifest, and the same guarantee that Recharts lands only in the radar
bundle.

Rejected: generalizing to a shared `/static/dist/` relocates gym's built assets
and touches every gym template — real regression risk to a working app for no
gym benefit.

### 9.4 Deploy

`run_radar_ingest.py` needs its own systemd unit and a line in the VPS deploy
script's restart list, alongside the gym notifier. Ships via git to `main` like
all application code.

---

## 10. Testing

`personal_apps/tests/`, pytest, sources mocked — **no live API calls in tests**.

| Target | Assertion |
|---|---|
| Ticker extractor | Golden corpus, both directions: `$GME` is caught; "DD on my ATH puts" yields zero tickers |
| Symbol normalization | A lowercase-derived candidate still resolves against the `utf8mb4_bin` universe |
| Divergence transform | A `mention_z` of 20 does not outrank a `mention_z` of 6 with a flat price by more than the bounded transform permits |
| Signed vs magnitude | Loud + −4σ ranks below loud + flat |
| No-print detection | Two consecutive identical `(quote_ts, quote_volume)` pairs set `price_status='stale'`, and stale rows carry no divergence |
| Per-source outage | StockTwits `missing` + Reddit `ok` yields a usable Reddit-only z; the bucket is excluded from StockTwits baselines only |
| Source combination | Pooled-count z equals the single-source z when the other source is missing |
| Reddit truncation | Hitting the page cap marks buckets `truncated`; truncated buckets are excluded from baselines but still shown live |
| Rate estimator | Dropping an arbitrary subset of buckets leaves `ticker_rate` unbiased — the `observed_mass` divisor works |
| Spike exclusion | A ticker that spiked 10 days ago has the same baseline as one that did not |
| NB dispersion | An overnight bucket with expected 0.3 / observed 6 produces a large z, not a suppressed one |
| Dispersion clamp | An upward-biased `k` estimate is clamped, and does not compound across successive baseline passes |
| Config versioning | Adding a subreddit does not produce a market-wide spike the next cycle |
| Cold start | Under 14 baseline days renders provisional and is absent from history aggregates |
| Threshold versioning | Aggregates never pool spikes across `threshold_version` |
| LLM sentiment leak | No query in the history module references `llm_sentiment` |
| Session windows | Correct cadence tiering across the EU/US DST desync weeks |
| Forward returns | Market-clock offsets when a spike fires after close, over a weekend, and before a holiday |
| Charset | A post body containing 4-byte characters round-trips unchanged |

Frontend: vitest, already configured.

---

## 11. Cost and operations

| Component | Cost |
|---|---|
| Reddit | free — non-commercial personal use, 100 QPM |
| StockTwits | free public endpoints (ToS confirmation pending, §3.3) |
| Price provider | free tier, ~60 calls/min, radar top-N only, 2-min cache |
| Claude Haiku sentiment | top-N only, order of 150k input tokens/day — cents |
| Storage | raw posts 30d rolling; buckets retained but small, partitioned monthly |

---

## 12. Open items

1. **StockTwits ToS** must be confirmed before the source module is built. If it
   does not permit this use, v1 ships Reddit-only and the extractor is
   calibrated against a hand-labelled corpus instead (§3.3).
2. **Price provider selection** — Finnhub is the assumed class of provider; the
   specific one is chosen at implementation time against current free-tier
   limits, and must expose quote timestamp, quote volume, earnings calendar and
   IPO calendar. The adapter boundary in `prices.py` keeps it swappable.
3. **Threshold constants** — `K_M`, `K_P`, eligibility floors, spike open/close
   thresholds, `k` clamp bounds, `n_prior` and top-N size are configuration.
   Initial values are set during implementation, then tuned against real data —
   with each tuning round frozen as a new `threshold_version` (§7.4).

---

## 13. Deferred to later versions

- Push alerts on spike, over the existing VAPID infrastructure
- X/Twitter ingest, official or via reseller
- Watchlist promotion — pinning radar finds for deeper tracking

---

## 14. Decisions that are not to be revisited during implementation

Recorded so they do not get "improved" away:

- `mention_z` and `price_move` stay as separate adjacent columns (§6.4)
- `missing` ≠ zero (§4.5), extended to `truncated` and to open spikes (§6.1)
- the n<20 "thin" guard and sample size beside every figure (§7.4)
- session windows on the NY exchange calendar, display in Berlin (§4.4)
- Recharts as SVG rather than a canvas library (§9.2)
- a separate radar base path and manifest (§9.3) — only two-files-vs-one was in
  question, and that resolved to one
- the Unknown segment as a first-class tab (§8.1)
- the scope boundary in §1: no recommendations, no targets, no orders

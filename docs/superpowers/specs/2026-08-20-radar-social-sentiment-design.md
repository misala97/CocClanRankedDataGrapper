# Radar — social-sentiment stock discovery dashboard

**Date:** 2026-08-20
**App:** `personal_apps`
**Branch:** `dev_personal`
**Status:** design approved, not yet planned

---

## 1. What this is

A discovery radar for day-trading candidates, driven by online chatter. It
ingests posts from Reddit and StockTwits, extracts stock tickers, measures how
unusual each ticker's mention volume is against its own history, compares that
against the ticker's price move over the same window, and ranks by the gap
between the two.

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
| Ranking | Divergence (mention z-score minus price move, both normalized) |
| Price data | Daily close + intraday quote, radar top-N only |
| Sentiment | Lexicon on everything, Claude Haiku re-read on radar top-N |
| Ingest cadence | Tiered by US market session |
| v1 surfaces | Radar leaderboard, ticker detail, spike history log |
| UI language | English |
| Frontend | React island, Recharts for charts |

---

## 3. Data sources

### 3.1 Why not X/Twitter

As of February 2026, X closed Basic and Pro tiers to new signups and moved new
developers to pay-per-use at **$0.005 per post read**. The free tier is gone. A
broad discovery radar reading on the order of 20k posts/day would cost roughly
$3,000/month. X is therefore out of v1.

The source interface (§4.1) is built so X — or a third-party X data reseller —
can be added later as one new module without touching anything downstream.

### 3.2 Reddit

Free for non-commercial use at **100 queries/minute per OAuth client**. Personal
use qualifies. Each listing request returns up to 100 items, so the practical
ceiling is far above what this needs.

Subreddits: `wallstreetbets`, `stocks`, `options`, `pennystocks`,
`shortsqueeze`, `Daytrading`, `smallstreetbets`, `SPACs`. The list is
configuration, not code.

Both posts and comments are ingested — a large share of ticker mentions live in
comment threads, and ingesting only posts would systematically undercount any
ticker that gets discussed rather than announced.

### 3.3 StockTwits

Free public endpoints. Two properties make it valuable beyond raw volume:

1. Posts are already `$TICKER`-tagged, so no extraction guesswork.
2. Messages carry a native bull/bear label.

Because its tickers are unambiguous, StockTwits doubles as ground truth for
calibrating the Reddit extractor (§4.2).

**Open item:** StockTwits' current terms of service must be confirmed to permit
this use before the source module is built. If they do not, v1 ships
Reddit-only and the extractor is calibrated against a hand-labelled corpus
instead.

### 3.4 Prices

A free-tier market data provider (Finnhub-class, ~60 calls/min):

- intraday quote for radar top-N tickers, 2-minute cache
- daily close for all tickers with recorded mentions
- company profile (market cap, exchange, IPO date, average volume), refreshed
  weekly, feeding the segment filters
- IPO calendar, feeding the upcoming-IPO panel
- SPY daily/intraday series, for the excess-return baseline in §7

---

## 4. Ingest pipeline

### 4.1 Source interface

Each source module exposes one function returning normalized records:

```
fetch(since: datetime) -> list[RawPost]

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
  native_tickers list[str]   populated by StockTwits, empty for Reddit
  native_sentiment str|None  StockTwits bull/bear, else None
```

Dedup on a unique index over `(source, external_id)`. Re-fetching an already
stored post updates its score and comment count, since engagement grows after
first sight.

### 4.2 Ticker extraction

Extraction is the highest-risk component: it produces false positives
constantly, and every false positive becomes a fake spike.

A `ticker_universe` table holds symbol, company name, exchange, and the profile
fields from §3.4, seeded from a free symbol listing and refreshed weekly.

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

### 4.3 Cadence

An APScheduler daemon, `run_radar_ingest.py`, mirroring the deployed
`run_gym_notifier.py` pattern.

| Window (US market clock) | Interval |
|---|---|
| Pre-market | 3 min |
| Regular session | 3 min |
| After-hours | 10 min |
| Overnight / weekend / market holiday | 30 min |

### 4.4 Timezone handling

**Store UTC. Compute session windows in `America/New_York`. Render in
`Europe/Berlin`.**

The EU and US switch daylight saving on different dates — roughly three weeks
each spring and one each autumn where the offset between them differs from
normal. Hardcoding German clock times for session boundaries would mis-tier the
ingest cadence during exactly those weeks. Session state derives from the NY
exchange calendar, including holidays and early closes; display converts at the
last moment.

### 4.5 Gap handling

If a source is unavailable, its buckets are recorded as **missing**, not as
zero.

Counting an outage as zero mentions poisons the baseline and manufactures a
false spike the moment ingest resumes. Missing buckets are excluded from
baseline computation and are visibly gapped in timelines.

---

## 5. Storage

Three layers. Models live in the shared `personal_apps/models.py`, following
this repo's existing convention.

### `radar_post`
One row per ingested post or comment: the `RawPost` fields plus first-seen and
last-updated timestamps.
**Retention: 30 days rolling.**

### `radar_mention`
One row per (post × ticker): ticker, confidence, lexicon sentiment score, LLM
sentiment (nullable, filled later for top-N only).
**Retention: 30 days rolling**, following its post.

### `radar_bucket`
The queryable layer. One row per (ticker × 15-minute bucket):

- `mention_count`, `high_confidence_count`
- `distinct_authors`
- `engagement_weighted_count`
- `sentiment_mean`, `sentiment_stdev`
- per-source counts
- `status`: `ok` | `missing`

**Retention: forever.** Rows are small and this is what every score, chart and
baseline reads. Raw text ageing out does not damage history.

---

## 6. Scoring

### 6.1 Mention z-score

Naive z-scores fail in two specific ways here, and both are guarded:

**Intraday shape.** Chatter volume has a strong daily and weekly profile.
Comparing 03:00 against 16:00 as if they were the same population makes every
afternoon look like a spike. Expected count for a ticker in a bucket is
therefore its own trailing daily mean scaled by a **market-wide hour-of-week
share profile**, computed across all tickers. That profile is estimated from
aggregate data, so it is stable even where a single ticker's history is thin.

```
expected = ticker_daily_mean * market_hour_share(bucket)
z        = (observed - expected) / max(ticker_stdev, floor)
```

Both baseline terms are computed over a **trailing 30 days**, at bucket grain:
`ticker_daily_mean` is the ticker's mean mentions per day across that window,
and `ticker_stdev` is the standard deviation of its per-bucket residual
(`observed - expected`) over the same window. `missing` buckets (§4.5) are
excluded from both. The `floor` prevents division by a near-zero standard
deviation.

**Low counts.** Going from 2 mentions to 8 is a large z-score against a tiny
baseline and means nothing. A ticker is radar-eligible only above both:

- a minimum absolute mention count in the window, **and**
- a minimum **distinct author** count

The distinct-author gate is what defeats single-account spam, which raw volume
cannot see at all.

### 6.2 Windows

z is computed at **1h, 4h and 24h simultaneously**. All three appear on each
row; the user picks which one sorts. Default 4h.

A single window is insufficient in both directions: 1h misses a ticker building
steadily over eight hours, 24h dilutes a fast squeeze into invisibility.

A ticker elevated across all three windows is marked **sustained** — a stronger
signal than any single-window reading, and free to compute once all three exist.

### 6.3 Divergence — the primary metric

```
divergence = mention_z − price_move_z      (same window, both normalized)
```

Price move is normalized against the ticker's own volatility, not expressed as
a raw percentage. A 5% move on a micro cap is noise; 5% on a large cap is an
event. Ranking on raw percent would mark every small cap as "already moved" and
would hide genuine large-cap divergence.

| Mentions | Price | Divergence | Reading |
|---|---|---|---|
| far above normal | flat or down | **high positive** | loud and unmoved |
| far above normal | far up | **negative** | price already ran |
| normal | far up | **low** | move without chatter — out of scope |

The leaderboard sorts by divergence but **keeps `mention_z` and `price_move` as
separate adjacent columns**. Collapsing them into one number would make
"loud and flat" indistinguishable from "quiet and dumping", which is the single
most important distinction on the page.

### 6.4 What divergence does not mean

Loud-and-unmoved is not inherently bullish. The identical pattern is produced
by bot or brigade chatter, by a stock too illiquid to fill size in, and by a
pump whose loud phase is the exit. Distinct-author count and source spread are
on every row precisely because they are what separates those cases, and both
must remain visible rather than folded into the score.

### 6.5 Sentiment

**Lexicon on everything.** A finance-tuned VADER-style lexicon scores every
mention at ingest — free, instant, and adequate for the long tail.

**Claude Haiku re-read on radar top-N.** Posts belonging to tickers currently
on the radar and not yet LLM-scored are batched to Claude Haiku, which returns
bull/bear/neutral plus a conviction level. WSB runs on sarcasm and inverted
positions ("all in on puts", "this is fine") where lexicons approach coin-flip
accuracy, and those are exactly the posts worth reading correctly.

Both scores are stored. **Where they disagree, the UI marks the cell** —
disagreement usually indicates sarcasm or an inverted position, so it is
information rather than noise to be resolved away.

---

## 7. Spike history

### 7.1 A spike is an event

A `radar_spike` row opens when a ticker crosses the divergence and eligibility
thresholds. It stays open while the ticker remains elevated and closes after it
falls below for N consecutive buckets. Without this state machine, one squeeze
produces dozens of rows and the log is unreadable.

Recorded at open: ticker, segment, `started_at`, `mention_z`, `divergence`,
distinct authors, source spread, price. Peak values update while open.

### 7.2 Forward returns run on the market clock

A spike detected at 23:00 German time has no meaningful "+1 hour price" — the
market closed an hour earlier. Offsets are therefore session-relative:

- next open
- +1 session close
- +3 session closes
- +5 session closes

A follow-up job stamps each as it becomes available.

### 7.3 Excess return vs SPY

Every forward return is stored both raw and as **excess over SPY across the
identical window**. Without the baseline, a broad market rally makes every
signal look prophetic and the log flatters itself. Aggregates use excess.

### 7.4 Aggregate view

Hit rate and median excess return, sliced by:

- divergence band — did loud-and-unmoved actually outperform already-moved?
- segment — does this work on micro caps but not large caps?
- source spread — one subreddit versus broad pickup
- sustained versus single-window

**Sample size appears next to every figure, and any band under n=20 renders as
"thin" rather than as a percentage.** A 3-of-4 hit rate is not 75%, and a
dashboard that prints 75% there will be believed. This guard is what stops the
log from manufacturing false confidence in the tool it is meant to audit.

The log is read-only history.

---

## 8. Surfaces

### 8.1 `/radar` — leaderboard

Ranked by divergence, window selectable (1h / 4h / 24h), default 4h.

Per row:

```
SYMBOL · name · divergence · mention_z (1h/4h/24h) · mentions vs typical ·
distinct authors · source spread · sentiment split · price % today · sparkline
```

A **lead/lag mark** compares when mentions spiked against when price moved:
chatter leading, coincident, or chatter chasing.

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

- mention timeline overlaid on price, last 7 days, shared x-axis — reading
  lead/lag directly rather than trusting the row's mark
- **quadrant scatter**: x = price move σ, y = mention z, all radar tickers
  plotted, upper-left (loud, unmoved) highlighted
- the actual top posts driving the spike: title, channel, score, timestamp,
  outbound link
- sentiment split over time, with lexicon/LLM disagreement marked
- source breakdown — one subreddit versus broad pickup are different situations
- this ticker's own spike history, linking into §8.4

### 8.4 `/radar/history` — did-it-work log

Past spikes with their forward returns, plus the §7.4 aggregates.

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
  extraction.py      ticker matching, stopwords, confidence
  scoring.py         z-scores, hour-share profile, divergence
  spikes.py          open/close state machine, forward returns
  sentiment.py       lexicon scoring
  llm_sentiment.py   Claude Haiku batch classification
  prices.py          quote/profile/IPO provider adapter
  universe.py        symbol listing seed and weekly refresh
  ingest.py          orchestration, called by the daemon

personal_apps/run_radar_ingest.py    APScheduler daemon
```

Models are added to the existing `personal_apps/models.py`.

### 9.2 Frontend

React island, matching the gym port. React 19, `@tanstack/react-query` for the
polled leaderboard (background refetch and stale marking without hand-rolled
timers), `zustand` for filter state — all three already dependencies.

**Recharts is added** for the dual-axis timeline and the quadrant scatter. It
renders SVG rather than canvas, which matters: canvas cannot resolve `var()` or
`color-mix()`, so themed colors silently disappear — a failure this codebase
has hit before. The sparkline stays hand-rolled; a 40-point `<polyline>` needs
no library. React 19 support landed in Recharts 3.x; the exact version is
pinned at install.

### 9.3 Vite configuration

The current `vite.config.ts` is gym-specific: `base: '/static/gym/dist/'`,
`outDir: static/gym/dist`, gym-only entries.

Radar gets **its own `vite.radar.config.ts`** with base `/static/radar/dist/`
and its own manifest; `vite_assets.py` grows a per-app manifest lookup.

Rejected alternatives: generalizing to a shared `/static/dist/` relocates gym's
built assets and touches every gym template — real regression risk to a working
app for no gym benefit. Adding radar entries to the gym build works but serves
radar's JavaScript from `/static/gym/dist/` permanently. A separate config also
guarantees Recharts lands only in radar's bundle rather than incidentally.

### 9.4 Deploy

`run_radar_ingest.py` needs its own systemd unit and a line in the VPS deploy
script's restart list, alongside the gym notifier. Ships via git to `main` like
all application code.

---

## 10. Testing

`personal_apps/tests/`, pytest, sources mocked — **no live API calls in tests**.

| Target | What it asserts |
|---|---|
| Ticker extractor | Golden corpus of real posts, both directions: `$GME` is caught; "DD on my ATH puts" yields zero tickers |
| z-score math | Synthetic buckets, including the low-count floor and the hour-share profile |
| Session windows | Correct tiering across the EU/US DST desync weeks — the bug that surfaces twice a year |
| Spike state machine | One squeeze produces exactly one row |
| Forward returns | Market-clock offsets when a spike fires after close, over a weekend, and before a holiday |
| Gap handling | A source outage produces `missing` buckets, and those are excluded from baselines |

Frontend: vitest, already configured.

---

## 11. Cost and operations

| Component | Cost |
|---|---|
| Reddit | free — non-commercial personal use, 100 QPM |
| StockTwits | free public endpoints (ToS confirmation pending, §3.3) |
| Price provider | free tier, ~60 calls/min, radar top-N only, 2-min cache |
| Claude Haiku sentiment | top-N only, order of 150k input tokens/day — cents |
| Storage | raw posts 30d rolling; buckets retained but small |

---

## 12. Open items

1. **StockTwits ToS** must be confirmed before the source module is built. If
   it does not permit this use, v1 ships Reddit-only and the extractor is
   calibrated against a hand-labelled corpus instead (§3.3).
2. **Price provider selection** — Finnhub is the assumed class of provider;
   the specific one is chosen at implementation time against current free-tier
   limits. The adapter boundary in `prices.py` makes this swappable.
3. **Threshold constants** — eligibility floors, spike open/close thresholds,
   and top-N size are configuration with initial values set during
   implementation, then tuned against real ingested data.

---

## 13. Deferred to later versions

- Push alerts on spike, over the existing VAPID infrastructure
- X/Twitter ingest, official or via reseller
- Watchlist promotion — pinning radar finds for deeper tracking

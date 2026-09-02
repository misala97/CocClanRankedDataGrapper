# Radar — Reddit through Arctic Shift

**Status:** approved in brainstorm 2026-09-02, spec for review
**Builds on:** `2026-08-24-radar-subreddit-source-list.md` (why single-ticker
and regional subs are out), the source contract in
`features/radar/sources/__init__.py`, and the judge gate
(`2026-09-02-radar-judge-gate-design.md`). Everything not named here is
unchanged.

## Why

The radar hears three feeds and Reddit, its richest one, is read through
anonymous RSS at one feed per ~100 s for every subreddit together: the 25
newest comments of whichever sub is due. Measured 2026-09-02 at 22:00 CEST,
r/wallstreetbets alone produces ~1,300 comments/hour; the RSS path sees a few
percent of it. Reddit's own API now needs manual approval (weeks, may be
refused). **Arctic Shift** — an open Reddit archive with a public
near-real-time API, ~120k requests/hour, no key — returns the full comment
and post stream per subreddit, paged by time, 5–10 minutes behind. Probe:
WSB 1,192 comments/h, Daytrading 119, stocks 94, smallstreetbets 89,
ValueInvesting 62; 34 chosen subs ≈ 1,700 comments/hour and ~350 equity
mentions/hour against ~140 mentions/hour from all three sources today.

Michi's decisions: use it; retire the RSS fetcher but keep it in the tree;
store comment scores; backfill 30 days so baselines are real from day one.

## What the reader gets

Nothing new on the page. Rows fill, baselines mean something, the Watching
tier and the judge gate see ten to twenty times the Reddit chatter. The
masthead's source line reports Arctic Shift's health like any other source.

## The adapter — `features/radar/sources/arctic_shift.py`

`fetch(cursors, client, *, subs, max_pages) -> FetchResult`, the same
contract every source implements. Emits `RawPost`s under the existing names
`reddit:<sub>` with `channel=<sub>`, so the venue root `reddit`, the forum
gate, finance-native bare tokens, the Reddit author rules, the comment
splitting in `sentiment_input`, and the phrasing all apply unchanged.

Per subreddit, per cycle, two reads:

- **comments**: `GET /api/comments/search?subreddit=<sub>&after=<cursor>&sort=asc&limit=100`,
  paged until fewer than 100 come back or `max_pages` (10) is reached;
  fields used: `name` (external id, `t1_…`), `author`, `created_utc`,
  `body`, `score`, `link_id`, `permalink`.
- **posts**: the same on `/api/posts/search`; fields `name` (`t3_…`),
  `author`, `created_utc`, `title`, `selftext`, `score`, `num_comments`,
  `permalink`, `url`.

Mapping:

| RawPost field | comment | post |
|---|---|---|
| `source` | `reddit:<sub>` | `reddit:<sub>` |
| `external_id` | `name` (`t1_<id>`) — the id the RSS path stored, so the switch dedupes | `name` (`t3_<id>`) |
| `channel` | `<sub>` | `<sub>` |
| `title` | `'/u/<author> on <parent title>'` — the shape `reddit_comment_split` decides comments by | `title` |
| `body` | `body` | `selftext` (may be empty) |
| `score` | `score` at fetch time | `score` |
| `num_comments` | 0 | `num_comments` |
| `url` | `https://www.reddit.com` + `permalink` | same |

Parent titles come from one batched `GET /api/posts/ids?ids=<distinct link_ids>`
per cycle (≤100 ids per call; a cache of id → title lives for the process).
A parent the archive does not have gets an empty context (`'/u/<author> on '`),
which the splitter already handles as body-only.

**Scores.** A comment read 5–10 minutes after posting has score 1; the value
is stored for the future weighting Michi asked about, and a later re-read
pass (by id) is out of scope here.

**Cursor.** New table `radar_source_cursors` (`source` varchar(48),
`key` varchar(64), `cursor_utc` datetime, `updated_at` datetime; pk
(source, key)). Keys `<sub>:comments` and `<sub>:posts`; the cursor is the
newest `created_utc` accepted, minus nothing — Arctic Shift's `after` is
exclusive on the second, and ids dedupe the boundary. Cold start (no row):
`now − 1 h`. One Alembic migration, plain DDL.

**Status.** Per sub: `ok` when every page was read; `truncated` when
`max_pages` was hit (more remains — reported as coverage, exactly like the
4chan page cap); `missing` on any HTTP or parse error for that sub. Aggregate
status is the worst of them. `per_source_status` is set for every sub read.
A `429`/`5xx` answer stops the cycle's remaining requests (the archive is one
host); `X-RateLimit-Reset` is honoured as a sleep of at most 10 s inside the
cycle.

**Rate.** 34 subs × (1–2 comment pages + 1 post page) + 1 ids call ≈ 100
requests per 5-minute cycle ≈ 1.2k/hour, about 1 % of the allowance.

## Wiring

- `config.REDDIT_FETCHER = 'arctic_shift'` (`'rss'` restores the old path
  unchanged). `run_radar_ingest.build_fetchers` picks the adapter by it.
  Under `arctic_shift` Reddit runs **inside the main cycle** like Bluesky
  and 4chan (no per-sub budget, no `due_symbols`, no separate job); the
  RSS job and its scheduler bookkeeping stay as they are behind the flag.
- `config.REDDIT_SUBS` becomes the 34 names (list in the appendix). Adding
  a sub is one line and takes effect on the next deploy.
- `reddit_subs` leaves the `source_config_version` hash. Since the
  2026-08-26 split every `reddit:<sub>` is its own population with its own
  baseline; a new sub warms up alone and a dropped one just stops, so a list
  change must not restart every source's baseline. The version is bumped
  ONCE by the RSS→Arctic Shift change itself (`SOURCE_NAME_GENERATION` or an
  explicit `reddit_fetcher` key), which the backfill then fills.

## Backfill — `scripts/backfill_arctic_shift.py`

Runs once on the VPS after deploy, before the daemon's first Arctic Shift
cycle: for each sub, comments and posts for the last `POST_RETENTION_DAYS`
(30), oldest day first, through the same adapter mapping and the same
`ingest` intake (extraction, journal, buckets) the live cycle uses, one
calendar day per transaction, with `--from`/`--to` and a resume file so an
interrupted run continues. Expected ~1.3 M comments and ~100 k posts, ~14 k
requests, one evening. Buckets are written under the current
`source_config_version`, so scoring sees 30 days of history for every
`reddit:<sub>` at once. Old mentions never reach the judge (outside its
24 h window), so the backfill costs no model spend. The daemon is stopped
while it runs (the deploy script's stop/start brackets it).

## Out of scope

- Re-reading comment scores later for weighting.
- Any change to extraction, the floor, or scoring.
- Discord, Telegram, YouTube, TradingView, Yahoo — measured, not worth it.
- Regional subs other than mauerstrassenwetten; Finanzen/Aktien (no tickers,
  false positives).

## Tests

- Mapping: one comment and one post fixture → `RawPost`s with the ids, the
  synthetic comment title, the score, the url.
- Paging: three scripted pages of 100/100/40 → one fetch, cursor at the last
  `created_utc`; a page cap of 2 → `truncated`.
- Cursor: cold start reads `now − 1 h`; the stored cursor is used and
  advanced only on success; a failed sub keeps its cursor.
- Status: HTTP 500 on one sub → that sub `missing`, the others read, aggregate
  `missing`; `429` → the cycle stops requesting.
- Parent titles: batched lookup, cache hit on the second cycle, absent parent
  → empty context.
- `build_fetchers` honours `REDDIT_FETCHER` both ways.
- `source_config_version` no longer changes when `REDDIT_SUBS` changes; it
  does change with the fetcher switch.
- Backfill: day chunking, resume file, idempotent re-run (unique
  (source, external_id)), dry-run counts.

## Deploy

Routine deploy (migration for the cursor table runs in the script). Then,
by hand once: `python scripts/backfill_arctic_shift.py` on the VPS with the
daemon stopped, then start the daemon. First live cycle logs
`sources={'bluesky': 'ok', 'fourchan': 'ok', 'reddit': 'ok'}` with the
per-sub map.

## Appendix — `REDDIT_SUBS`

wallstreetbets, Daytrading, stocks, smallstreetbets, ValueInvesting,
thetagang, pennystocks, Trading, options, Shortsqueeze, StockMarket,
pennystock, stocks_picks, wallstreetbetsHUZZAH, FuturesTrading,
swingtrading, Schwab, weedstocks, Optionswheel, biotech_stocks,
technicalanalysis, Fidelity, Webull, thinkorswim, RealDayTrading,
Burryology, shroomstocks, UraniumSqueeze, SPACs, Spacstocks, squeezeplays,
Biotechplays, investing, mauerstrassenwetten.

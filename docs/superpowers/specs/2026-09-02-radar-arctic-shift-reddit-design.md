# Radar — Reddit through Arctic Shift

**Status:** built 2026-09-02 (plan docs/superpowers/plans/2026-09-02-radar-arctic-shift-reddit.md)
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

## Built as (2026-09-02, deviations from the text above)

- **Reddit keeps its own scheduler job** (`radar_reddit`, every
  `ARCTIC_SHIFT_INTERVAL_SECONDS` = 300 s) rather than joining the main
  cycle: a slow archive must never delay Bluesky and 4chan, and the daemon
  tests pin that wiring. Its cycle still goes through `run_cycle`.
- **Cursor table is `radar_reddit_cursors`** (`sub`, `kind`, `cursor_utc`,
  `updated_at`); `radar_source_cursors` already existed with one root
  cursor per source. Cursor = newest accepted `created_utc`; requests use
  `after = cursor − 1` (the API is exclusive at the second) and ids dedupe.
  Cold start 2 h, the root cursor's own.
- **Authors are stored as `/u/<name>`**, the RSS path's spelling, so voice
  counts and author rules see one person across the switch.
- **A comment whose thread the archive lacks** is titled
  `'/u/<author> on [thread unavailable]'`: the splitter needs a non-empty
  context (`clean_text` strips the trailing space).
- **A subreddit is atomic per cycle**: posts and both cursor advances
  are published only when both reads completed; a failed read leaves the
  sub `missing` with nothing returned and nothing moved (a comments read
  that succeeded would otherwise be stored under a missing source, never
  counted, and never read again).
- **Aggregate status reuses `reddit._roll_up`**: one sub missing among
  ok subs is `truncated`, all missing is `missing`. A `429` ends the
  cycle's requests with no sleep: the job asks again in five minutes, so
  sleeping could not recover work and would only hold the scheduler
  worker. Subs never asked are absent from the per-source map.
- **The backfill runs with the daemon STOPPED** (the script refuses
  `--apply` otherwise): both sides floor to 15-minute buckets, so no time
  cutoff keeps their windows apart. One day across all subs is the unit,
  rolled up once with every sub countable so the quiet subs get their
  zero rows; `roll_up(preserve_parent=True)` leaves existing parent
  buckets alone because the journal only holds 48 h and a rebuild would
  erase the other sources' totals.
- **`ARCTIC_SHIFT_PAGE_SIZE = 'auto'`, and an EMPTY page ends a read.**
  Probed live 2026-09-02: a numeric `limit` above 100 is a 400
  (`'limit' must be between 1 and 100`), so the planned 1000 could not
  work; `limit=auto` answers with ~600 items a page, and a day of
  r/wallstreetbets pages in 12 requests rather than 71. Page length then
  carries no information about whether more is waiting, so the reader
  stops on an empty page and keeps the short-page shortcut only for a
  numeric `page_size`. Cost per live cycle is one confirming request per
  (sub, kind): ~136 requests per 5 minutes, ~1.4 % of the allowance.
- **HTTP 422 is the archive asking us to slow down**, not a bad request:
  `{"data":null,"error":"Timeout. Maybe slow down a bit"}`, hit on the
  first live backfill around page 41 of a 24-hour window (2026-09-03).
  The identical request answered on the next attempt. It is its own
  exception class, `ArcticShiftBusy`; `page_range` and the backfill's
  `parent_titles` wait it out (6 tries, 2 s doubling to 60 s) because a
  day half-read would be written as a complete day, while the live cycle
  does not retry at all — its windows are five minutes, and giving the
  subreddit up with its cursor unmoved costs one cycle.
- **A read timeout is the same fact as a 422** and retries with it
  (2026-09-03, day 23 of the first live backfill died on a `ReadTimeout`
  after the 422 fix had already shipped). `requests.Timeout` and
  `ConnectionError` raise `ArcticShiftBusy`; anything else the transport
  raises stays a hard `ArcticShiftUnavailable`. The backfill's client
  also gets a 90 s timeout against the live cycle's 30 s, because a whole
  day of a busy subreddit is a far heavier query than five minutes of one.
- **The log line** for a cycle shows the concrete map under `sources=`
  (34 `reddit:<sub>` keys) and the root verdict under `aggregate=`.
- **Bucket growth** accepted: ~34 child rows per touched (ticker, window).
- **The 2026-08-25 subreddit cut is marked superseded in `config.py`.**
  That comment block argued Daytrading, stocks, StockMarket, SPACs,
  Biotechplays and UraniumSqueeze out on a ~30-feeds/hour budget; the
  budget is gone and all six are back in the list, so the block now says
  so rather than contradicting the tuple beneath it.
- **`radar_buckets.source_config_version` is NOT NULL**, so the backfill
  test that seeds a pre-existing parent bucket stamps it with
  `source_config_version()`; the plan's fixture omitted the column and
  hit an IntegrityError.
- **Commits are attributed to Claude Opus 5**, the model that built it,
  rather than the plan's Fable 5.1 trailer.

## Appendix — `REDDIT_SUBS`

wallstreetbets, Daytrading, stocks, smallstreetbets, ValueInvesting,
thetagang, pennystocks, Trading, options, Shortsqueeze, StockMarket,
pennystock, stocks_picks, wallstreetbetsHUZZAH, FuturesTrading,
swingtrading, Schwab, weedstocks, Optionswheel, biotech_stocks,
technicalanalysis, Fidelity, Webull, thinkorswim, RealDayTrading,
Burryology, shroomstocks, UraniumSqueeze, SPACs, Spacstocks, squeezeplays,
Biotechplays, investing, mauerstrassenwetten.

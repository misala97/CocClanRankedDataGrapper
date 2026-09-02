# Radar — Watching and search

**Status:** approved in brainstorm 2026-09-02, spec for review
**Builds on:** `2026-09-01-radar-board-layout-round-design.md` (ledger rows,
tiers, views row, folded summary line). Everything not named here is
unchanged.
**Reverses:** PRODUCT.md "Deliberately absent — no watchlist". Michi's call,
2026-09-02. The scope boundary that mattered ("never implies a
recommendation") is untouched: a watch mark is the reader's own, and the
surface still recommends nothing.

## What the reader gets

1. **Search.** A box in the masthead. Type a symbol or a company name and get
   matches from the whole universe, not just today's board. Enter opens the
   stock's panel whether or not it made the board.
2. **Watching.** One mark, ☆, on every row and in the panel. Marked stocks sit
   above the board in a **Watching** tier, in every view and window, with a
   real row each — including a quiet row for a stock that did not clear the
   floor today, saying why. The marks are per account.

Decided in the mockups (`.superpowers/brainstorm/337-*/content/watching-and-search.html`):
Watching is a tier at the top (A), not a view tab; the search dropdown as
drawn in B; a watched stock that also made the board appears **once**, in
Watching, its score still on its row.

## Data

### `radar_watch` (new table, one Alembic migration)

| column | type | notes |
|---|---|---|
| `id` | bigint pk | |
| `user_id` | int, FK → `app_user.id`, on delete cascade | the mark belongs to an account |
| `ticker` | varchar(12), binary collation like `radar_ticker_universe.symbol` | the radar ticker identity, market-independent |
| `created_at` | datetime (naive UTC, like every stored instant) | |

Unique `(user_id, ticker)`. Plain DDL; nothing MariaDB parses differently.
No backfill.

### Search source

`radar_ticker_universe` as it stands: `symbol`, `name`, `exchange`,
`market_cap`, `ipo_date`, `is_etf`. No new columns, no index: the table is
~10k rows and a `LIKE` over it is milliseconds. The DE market shares the
same ticker identities (`radar_instruments` maps them), so one search serves
both markets.

## API

### `GET /radar/api/search?q=<text>`

- `q` trimmed; empty → `{"matches": []}`; capped at 40 characters.
- Ranking: symbol equal to `q` first, then symbol starting with `q`, then
  company name containing `q` (case-insensitive), each group largest company
  first (unknown caps last), then symbol -- decided from the live result on
  2026-09-02, when `nv` showed eight NV* symbols and no NVDA.
- At most **8** matches.
- Each match: `ticker`, `name`, `exchange` (the letter code; the client
  labels it as the panel does), `segment` (from `universe.segment_for`,
  without a price — `unknown` where cap is missing), `watching` (bool, for
  the caller's account).
- **Identity only.** Whether a match is on the current board, and its score,
  the client knows from the rows it already holds; the endpoint does not
  build a board to say so.
- Login-required like every radar route.

### `PUT /radar/api/watch/<ticker>` and `DELETE /radar/api/watch/<ticker>`

- Ticker shape-checked like `?t=` (`^[A-Za-z][A-Za-z0-9.-]{0,9}$`), uppercased.
  A ticker outside the universe is still accepted: watching is a fact about
  the reader, and an obscure symbol that later enters the universe should
  already be marked.
- Idempotent: PUT on a watched ticker and DELETE on an unwatched one both
  return 200.
- Response: `{"watching": [tickers]}` — the caller's full list, sorted by
  `created_at`, so the client never has to merge.

### The board payload

Two new fields:

- `watching`: the caller's tickers, sorted as above.
- `watch_rows`: one `Row` per watched ticker for the **current selection**
  (market, sources, window), in the same order.

The 60-second board memo (`routes/api._build_board`) stays viewer-invariant.
`build_payload` adds the two fields *after* the cached build, per request:
`watch.tickers_for(user)` then `leaderboard.build_pinned(tickers, sources,
now, window_hours, market)`. A handful of tickers, one aggregate query with
`ticker IN (...)`, the existing batched quote and profile lookups —
milliseconds, and uncached because it is per user.

### `leaderboard.build_pinned(tickers, sources, now, window_hours, market)`

Rows for named tickers **regardless of the eligibility floor**. Reuses the
pass-one aggregate query restricted to the tickers (same expansion rules),
the pass-two lookups (`_universe_rows`, `quote_views_for`, `moves_for`,
`_quote_sigmas`), and the same `Row` dataclass with two additions:

- `eligible: bool` — `scoring.is_eligible` over the same contributions the
  floor uses. A row that would have been on the board is `eligible`; a quiet
  one is not.
- `mentions` may be 0 and `clauses` then carries one `warn` clause written by
  `phrasing.py`: `no mentions in 4h` / `2 mentions in 4h, under the floor` /
  `one voice only, under the floor` — the reason the floor gave, in words.
  Absence rules hold: a ticker with no bucket in the window has `ratio`,
  `mention_z`, `divergence` and `normal_per_hour` all `null`, never zero.

A pinned ticker not in the universe gets a row with `name: null` and the
universe-less segment `unknown`; the panel already handles that (it 404s
and offers the fallback).

## The Watching tier

- Rendered by `ListPane` above the scored tier, in every view and window,
  whenever `watch_rows` is non-empty. Caption: **Watching** · *n* — no term,
  because its rows are ordered by the reader (`created_at`), not by a score.
- The ranked tiers omit any ticker in `watching`; the count on their captions
  counts what they show.
- A row from `watch_rows` renders with the same `TickerRow`. When
  `eligible` is false it carries class `quiet`: score cell `—`, no chart
  drawn when nothing was counted, the `warn` clause as the sub-line, price
  and move as usual. `scoredAgainstPrice()` decides the score cell exactly
  as before for eligible rows.
- The Watching tier's rows keep every dimension a board row has: chart,
  score, ratio · price · move, breadth, lean, marks, selection state.
- Empty board + watched stocks: the tier renders, then "Nothing cleared the
  bar" below it as today.
- Below 900px: unchanged structure; the tier stacks like the others.

## The star

- **On rows:** a ☆ button in a new first column of the ledger (22px + gap),
  left of the ticker. A `<button>` may not sit inside the row's `<a>`, so the
  row becomes `div.line > [button.star, a.row]`; the link keeps the grid, the
  button is positioned in the gutter the link leaves. Row walking (arrow
  keys) still targets `.row`; the star is in the tab order with an accessible
  name "Watch NVDA" / "Stop watching NVDA".
- **In the panel:** a ★ *Watching* / ☆ *Watch* button in the identity block,
  beside the name.
- **In search results:** the same star on each match.
- **Toggle behaviour:** optimistic — the star flips at once and the ticker is
  added to / removed from the client's `watching` set — then `PUT`/`DELETE`;
  on success the client refetches the board (memo hit, instant server-side)
  so `watch_rows` gains or loses the row; on failure the star reverts and
  nothing else changes. No banner: a failed mark is a rare, low-stakes event
  and the reverted star is the message.

## Search

- A combobox in the masthead between the market switch and the spend mark:
  `input[type=search]` with `role="combobox"`, `aria-expanded`,
  `aria-controls`, `aria-activedescendant`; results as `ul[role=listbox]` of
  `li[role=option]`.
- `/` anywhere on the page (outside inputs) focuses it, as on GitHub; `Esc`
  closes the list, then clears, then blurs.
- Fetch after 150ms of quiet typing; abort the previous request; ignore a
  stale response.
- Each result: ticker · name · exchange label · segment label, then a status
  the client derives: `on the board · 2.3` (in `payload.rows`, with its
  score), `watching` (in `watching`), or `quiet today`. And the ☆.
- `Enter` / click selects the ticker (`BoardPage.select`), the same path as a
  row click: the panel loads via the detail endpoint, `?t=` in the URL, the
  mobile scroll-to-panel fires. A ticker off the board is fine — the panel
  already serves any universe ticker and offers the fallback for one it
  cannot.
- The list closes on selection; the input keeps the query so the reader can
  star a second match.
- Positioned over the controls (`--z-popover`), inside `.lhead`; the list
  pane has no clipping overflow, so no portal is needed.

## PRODUCT.md

Under "Deliberately absent", replace `No watchlist, no portfolio, no
positions` with `No portfolio, no positions, no alerts. Watching exists —
the reader's own marks, kept per account, never a signal from the tool —
and the surface still recommends nothing.` Keep the alerts line.

## Out of scope

- Alerts on watched stocks (the deliberately-absent decision stands).
- Notes, tags beyond the one mark, ordering the Watching tier by hand.
- Search over posts or by ISIN.

## Tests

Python:
- `radar_watch` is per account: two users, disjoint lists; PUT idempotent;
  DELETE of an unwatched ticker is 200; ticker shape rejected with 400;
  cascade on user delete.
- Search: exact symbol first, prefix next, name-contains last; case-insensitive;
  capped at 8; empty query → empty; `watching` reflects the caller only.
- `build_pinned`: a watched ticker below the floor gets a row with
  `eligible=False`, a `warn` clause and nulls (never zeros) where nothing
  was measured; one above the floor gets the same row it would have had;
  a ticker with no bucket in the window still gets a row.
- The board payload carries `watching` and `watch_rows` for the caller and
  the memoised board is unchanged by who asks (two users, same rows, different
  `watch_rows`).

Vitest:
- Watching tier above the scored tier; a watched ticker appears once; the
  ranked captions count what they show; the tier is absent with nothing
  watched.
- Quiet row: `—` score, warn clause as sub-line, no chart when nothing was
  counted.
- Star: optimistic flip, PUT/DELETE called, board refetched on success,
  revert on failure; accessible names.
- Search: `/` focuses; typing fetches after the debounce with the last
  query only; arrows move `aria-activedescendant`; Enter selects; Esc closes
  then clears; results annotated from the rows the page holds.

Screenshots at 1440×900, 768×1024 and 390×844 with a watched stock on the
board, one below the floor, and the search open — before sign-off.

## Open questions for impeccable

- The star's resting weight: a ☆ on twelve rows is twelve glyphs; how quiet
  can it be and still read as a control.
- The quiet row's colour: muted throughout, or muted score with the price
  still in ink.
- The dropdown's arrival: settle like the filters, or instant like the
  hover readout.

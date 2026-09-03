# Radar — a sortable board list

**Status:** built 2026-09-04 (plan docs/superpowers/plans/2026-09-04-radar-sortable-board-list.md)
**Builds on:** the ledger layout from the 2026-09-01 layout round
(`static/radar/src/list/ListPane.tsx`), the two-tier split from the
2026-09-01 critique, and `features/radar/leaderboard.py`'s ranking.
Everything not named here is unchanged.

## Why

The board has exactly one ranking: divergence where a price could be
measured, `mention_z` everywhere else (`leaderboard.py:427`). It answers
"what is unusual" and nothing else. A reader who wants the loudest ticker
by raw volume, or the biggest price move, cannot get there — the numbers
are all on screen but the order is fixed.

The five header labels already look like column headings. They are
`aria-hidden="true"` decoration and nothing happens when you click them,
which is its own small lie.

## What the reader gets

The header tokens become controls. Each dot-separated word is its own
button:

```
Ticker │ Talk · price │ Score │ Ratio · price · move │ Lean
  ↑       ↑                ↑       ↑             ↑        ↑
 A→Z   Mentions      Divergence  Ratio     Price move   Lean
```

Six sort keys, no new furniture on the page and no change to the ledger's
column widths — the tokens are already rendered, they just stop being
inert.

`price` in "Talk · price" and in "Ratio · price · move" stays inert: the
first is a sparkline and the second is the quoted price, which is a fact
about the listing rather than a ranking anyone wants. Only the six keys
below are controls.

**Voices is deliberately not sortable.** No header token owns it, and
inventing one costs width in a right-aligned column that the 1440×900
ledger target has no room for. It stays visible on the row's sub-line.

## The six keys

| Token | Field | Direction on first click |
|---|---|---|
| `Ticker` | `ticker` | A→Z |
| `Talk` | `mentions` | largest first |
| `Score` | `divergence` | largest first |
| `Ratio` | `ratio` | largest first |
| `move` | `price_move` | largest first |
| `Lean` | `tone.bullish − tone.bearish` (count) | most bullish first |

`Score` sorts on **divergence only**, never on the score cell's rendered
text. `scoreText` shows divergence for price-scored rows and `mention_z`
for the rest (`TickerRow.tsx:28-31`); ranking those two against each
other is precisely what the 2026-09-01 critique caught and what the tier
split exists to prevent.

`Lean` needs a scalar and `Tone` is a distribution, so the net count
`bullish − bearish` is computed for the comparison — the arithmetic on the
two numbers the row actually displays, so the order can be verified by
looking at it. A ticker discussed with no lean either way is a real zero; a
ticker nobody used a sentiment word about has no lean at all and sorts with
the missing.

A SHARE was tried first and reverted the same day (see "Built as"): it was
decided by `neutral`, which the row never shows, and it made a single
bullish post a perfect 1.000 above nine bullish posts.

## Ordering rules

- **First click** applies the direction in the table above. **Second click**
  reverses it. **Third click** clears the sort and returns the default
  two-tier view. No separate reset control: the third click is where a
  reader already reaches, and a Reset that only appears while sorting is
  furniture that exists to undo furniture.
- **Rows with no value sort last in BOTH directions.** A ticker with no
  price is not evidence about its price — the same reasoning
  `leaderboard.py:427` already applies to a null divergence. Reversing
  shows the smallest real number, never a wall of dashes.
- **Ticker sorts case-insensitively**, ascending on first click.

## Tiers while sorting

A sort collapses the two tier captions into one straight list, with a
single line stating what is in force. The tiers exist because divergence
and `mention_z` are different quantities read down one column; a sort key
is one quantity that every row either has or explicitly lacks, so the
split has nothing to say about it.

**Watching stays pinned above the sorted list**, always, in mark order.
It is the reader's own set rather than a ranking, and a sort is a question
about the ranked board.

## Width: desktop only

Below 900px `radar.css` hides the header outright -- `.cols { display: none; }`
-- because the row layout stacks there and, as the rule's own comment says,
"there is no column to head at this width". Sorting is therefore a desktop
feature: the phone board keeps the default ranking and shows no sort
affordance at all.

Decided 2026-09-04 rather than overlooked. The alternative was a second
control (a compact "Sort" menu shown only under 900px), which is a second
mechanism to build, test and keep in step with the first, for a width whose
job is a glance rather than an analysis. If the phone later needs it, that
control is an additive change and nothing here blocks it.

A sort in the URL is still HONOURED at any width -- the server ranks by it
and the phone shows the sorted rows. Only the means of CHANGING it is absent
below 900px, so a link shared from a desktop keeps working on a phone.

## Where the sort lives

`sort` and `dir` join `Selection` beside `market`, `window`, `segment` and
`venues`. That puts them through `queryFor` into the request and into the
address bar through the existing `writeUrl`/`replaceState`, so a sorted
board survives a reload and can be pasted to yourself. Both are omitted
from the query at the default, the way `venues` is omitted at 1.

`replaceState`, not `pushState` — picking a sort is not a navigation, the
same call the controls already make.

## Server

`leaderboard.py` takes the key and direction and **sorts before applying
`limit`**. This is the whole point: sorting the already-limited rows would
give "the loudest among the top 30 by divergence", which reads
indistinguishably from "the loudest 30" and is a different list.

An unknown or malformed key falls back to the default ranking rather than
erroring. A sort arrives from a URL a reader may have edited.

The default ranking is unchanged when no sort is asked for — the same
`(divergence is not None, divergence, mention_z)` tuple, so a board with no
sort in its URL is byte-identical to today's.

## Accessibility

The `cols` div loses `aria-hidden="true"` and its tokens become real
`<button>`s with names that say the action ("Sort by mentions"), not just
the label. The active one carries `aria-sort` with the current direction.
A sort change is announced through the list's existing `role="status"`
region — the one that already announces filter changes, added because
going from ten rows to three was silent to a screen reader.

Not a `<table>`, so this is buttons and `aria-sort` on the container
rather than `<th>` semantics.

## Testing

Vitest:
- each token sorts by its field, and `price` is inert
- second click reverses, third clears to the default view
- rows with a null value sort last in both directions
- the sort round-trips through `queryFor` and the URL, and is absent from
  the query at the default
- Watching stays above the sorted rows

Pytest:
- `leaderboard.py` sorts **before** `limit` — a ticker outside the default
  top N appears first when sorted by its strongest field. The one test
  that would catch the mistake this design exists to avoid.
- each key orders as specified, nulls last both ways
- an unknown key falls back to the default ranking
- no sort asked for produces exactly today's order

## Built as (2026-09-04, deviations from the text above)

- **The sort lives in `board.build`, not `leaderboard.build_rows`.** The spec
  named the wrong file: `board.py` already calls `build_rows` with
  `limit=None`, and the real top-N is `ranked = ranked[:limit]`, after the
  segment and venue filters. The sort goes immediately before that line.
  Measured live 2026-09-04: 106 candidates against a limit of 50, so 56 rows
  are genuinely in play.
- **An invalid `sort` or `dir` raises `BadQuery` (400)** rather than falling
  back to the default ranking as the spec said. `routes/api.py` validates
  every other parameter and refuses rather than coerces, for the reason
  stated there: answering with a board under a selection the viewer never
  made. A silently-ignored sort would draw the default ranking under a
  header claiming otherwise.
- **The sort is part of the board memo's CACHE KEY**, which the spec did not
  mention at all. `_build_board` memoises per selection for 60 s; a key
  without the sort would have served the unsorted board to the next reader
  who asked for a sorted one -- inside the same minute, silently, and only
  sometimes. Found while implementing, pinned by a test that counts the
  cache entries.
- **The payload echoes `sort` and `dir` back, and the island seeds from the
  echo.** The spec said the island would parse the URL; it does not.
  `BoardPage.tsx` hydrates every control from the payload and reads only
  `?t=` from the address bar, so an unechoed sort would have rendered sorted
  rows under a header that believed nothing was sorted.
- **A lean sort fetches tones for the whole candidate set.** `_tones` runs
  inside `_entries`, which sees only the rows that survived the limit -- so
  ranking by lean has to know the tones before choosing which rows those
  are. It doubles one grouped query (106 tickers instead of 50) on a
  candidate build measured at 1.7 s, and only when that key is chosen.
- **`queryFor` also builds every row's detail href**, so the sort rides into
  the detail link and returns with the reader. Wanted rather than tolerated:
  coming back to a board that had forgotten its sort is the lost-place
  complaint `?t=` exists to fix.
- **Verified live 2026-09-04** on a local board of 21 rows: sorting by
  mentions returned CAT 17, GPRO 16, AMZN 15, SPY 14 -- strictly descending,
  with CAT absent from the default top six, so the re-rank demonstrably
  changes WHICH rows lead rather than only their order. Ticker sorted A-Z.
  The header's column edges measured `[42, 134, 254, 326, 485]` against the
  rows' `[42, 134, 254, 326, 493]` -- byte-identical to the same measurement
  taken against the pre-change build, so the buttons did not disturb the
  shared grid. At 390x844 the header is absent and a `?sort=` URL still
  renders sorted rows under its caption.
- **`Lean` sorts on the net COUNT, not a share** — changed hours after
  shipping, on the board. The share was decided by `neutral`, a number the
  row does not display, so BLK on one bullish post outranked CIFR on nine
  and the ordering was unreadable from the screen. It also made that one
  post a perfect 1.000, which is the confident-reading-from-a-handful that
  `Tone`'s own docstring warns about. The count is the arithmetic on the
  two arrows the row shows.
- **Sorting is desktop-only**, recorded above under "Width".

## Out of scope

- Sorting by Voices (no header token owns it).
- Sorting the Watching tier.
- Multi-key sort.
- Any change to which rows pass the floor, or to the default ranking.

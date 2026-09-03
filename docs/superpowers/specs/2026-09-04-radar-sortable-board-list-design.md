# Radar — a sortable board list

**Status:** approved in brainstorm 2026-09-04, spec for review
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
| `Lean` | `tone.bullish − tone.bearish` (share) | most bullish first |

`Score` sorts on **divergence only**, never on the score cell's rendered
text. `scoreText` shows divergence for price-scored rows and `mention_z`
for the rest (`TickerRow.tsx:28-31`); ranking those two against each
other is precisely what the 2026-09-01 critique caught and what the tier
split exists to prevent.

`Lean` needs a scalar and `Tone` is a distribution, so bullish share minus
bearish share is computed for the comparison. Neutral-heavy rows land in
the middle, which is what they are.

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

## Out of scope

- Sorting by Voices (no header token owns it).
- Sorting the Watching tier.
- Multi-key sort.
- Any change to which rows pass the floor, or to the default ranking.

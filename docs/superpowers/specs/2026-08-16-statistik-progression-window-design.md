# Statistik: every lift in Fortschritt, over a window you choose

**Date:** 2026-08-16
**Surface:** `/gym/statistik`, the "Fortschritt seit dem ersten Mal" section
**Status:** design approved, not implemented

## The problem

Two complaints, one section.

**It hides lifts.** `_progression_view(ranking, limit=8)` keeps the top eight by
change, plus every exercise below rank eight whose change is negative. The
asymmetry was deliberate — a section that only shows what went up is a
highlight reel — but the effect is that a lift at +15 % sitting ninth is
invisible while a −3 % at twelfth is not. The section is also capped upward and
unbounded downward, so it grows only when things go wrong.

**It has one fixed horizon.** Every percentage is measured from the exercise's
very first session, forever. There is no way to ask what the last month did.

## Product tension, recorded

`PRODUCT.md` draws the Heute/Statistik line exactly at windowing: *"Heute is
windowed... Statistik has no window"*, and tells the reader to ask of any new
statistic whether it is about now or about everything.

This design puts a window on one Statistik section. That is a deliberate,
owner-approved softening of the rule, scoped as narrowly as possible: the
control governs the Fortschritt section only. Totals, career strip, effort,
drift, rest, records and both neighbouring rankings stay all-time. The page
still answers *what does my training say about me*; one section can now be
asked *and lately?*.

## Scope

In:

- Every qualifying exercise shown, no cap.
- A four-position window control on the Fortschritt section: **Alles** (default),
  **6 Monate**, **3 Monate**, **30 Tage**.

Out:

- Windowing any other figure on the page.
- Persisting the choice across page loads or putting it in the URL.
- Custom date ranges.

## Semantics

Inside a window, an exercise is measured **from its first qualifying session
inside that window to its most recent one**. The window moves both ends, not
just the endpoint: "3 Monate" answers what the lift did over those three months.

Unchanged by the window:

- Deload sessions are excluded (`stats.progression_rows`) — a deliberately
  light week is not an attempt at a heavier one.
- One data point per session, the best e1RM of that session.
- Two qualifying sessions minimum — now two *inside the window*. An exercise
  trained once in the last 30 days has no first-versus-current in that window
  and is absent from that window's list. It is not shown at 0 %.
- A first e1RM of zero (a bodyweight set) skips the exercise; there is nothing
  to measure the change against.

At `Alles` the behaviour is identical to today's, minus the cap.

## Architecture

Chosen from three options. Rejected: recomputing in TypeScript from an enriched
payload (duplicates the e1RM and ranking arithmetic outside `analytics.py`,
which is the one place this codebase keeps it, and two implementations of
"progress" will drift); and a `?seit=` round trip (correct but costs a reload
per click and loses scroll position on a desktop-only page).

**The server precomputes all four windows; the client swaps which one it
renders.** Every number still comes from one Python function, and switching is
instant with no fetch — the same shape as the /cwl day-switch.

### Backend

`analytics.progression_ranking(rows, since=None)` gains an optional cutoff.
When set, rows with `started_at < since` are dropped before grouping, so both
the baseline and the sparkline describe the window. `since=None` is today's
all-time behaviour.

`reports._progression_view(ranking)` loses `limit` and the negative-tail rule
that existed only to survive truncation. Bar widths scale against the widest
absolute change **within that window**, so every view uses the full width.

The route builds the four blocks, deriving each cutoff from the `now` it
already computes. Cutoffs are plain day counts, not calendar arithmetic:
`30 Tage` = `now - 30d`, `3 Monate` = `now - 91d`, `6 Monate` = `now - 182d`.
A month here is a rough span, not a calendar boundary, and no consumer needs
it to land on the same day of the month.

Ordering within a block is unchanged: by `change_pct` descending, ties broken
by name.

### Payload

`progression` becomes a list of blocks, each `{key, entries}`, keys `all`,
`6m`, `3m`, `30d`, in that order. `entries` is exactly today's row shape
(`exercise_id`, `name`, `sessions`, `first_e1rm`, `current_e1rm`, `change_pct`,
`best_weight`, `points`, `spark`, `bar_pct`, `is_up`).

No German in `analytics.py` or the payload: keys are stable identifiers and the
component owns the labels, matching how month and weekday names already work.

### Frontend

A segmented control in the section header, `Alles` preselected. Clicking sets
React state; the section renders the matching block. Real buttons with
`aria-pressed`, matching the career strip's precedent that a custom clickable
must be a real button.

The heading tracks the selection so the label and the number can never
disagree:

| Window | Heading |
|---|---|
| Alles | Fortschritt seit dem ersten Mal |
| 6m | Fortschritt in 6 Monaten |
| 3m | Fortschritt in 3 Monaten |
| 30d | Fortschritt in 30 Tagen |

A window whose block is empty says so ("Keine Übung mit zwei Einheiten in
diesem Zeitraum.") rather than rendering a headed, empty section.

Presets shorter than the log's own age still render. The log is ~2 months old,
so 6 Monate and 3 Monate currently duplicate Alles; hiding them would make the
control change shape as history accumulates, which is worse than a preset that
agrees with its neighbour.

## Testing

Python (`tests/test_gym_analytics.py`):

- The baseline is the first session *inside* the window, not the all-time first.
- An exercise with one qualifying session in the window is absent from it.
- Every qualifying exercise is returned — explicitly more than eight.
- `since=None` matches today's all-time result.
- Deload exclusion still holds inside a window.

React (`StatistikPage.test.tsx`):

- Alles is the default selection.
- Clicking a window renders that window's entries, not the previous set.
- The heading follows the selection.
- An empty window states it.
- Bars scale against the selected window's widest change.

## Known consequence

Showing every lift makes this section roughly 2.5× taller, which re-opens the
column balance closed by the 2026-08-16 layout pass (left and right columns
currently end 19px apart). Deliberately not pre-solved here: the real height is
worth measuring before rebalancing against a guess. Expect a follow-up layout
pass once this is built.

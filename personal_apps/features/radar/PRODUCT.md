# Radar — Product context

This file is the impeccable design context for the **radar** feature of
`personal_apps`. It is scoped to that feature only. The gym feature has its own
`PRODUCT.md` and its own visual identity ("Puls"); radar shares nothing with it
beyond the Flask app it lives in. `coc_stats` is unrelated again.

## Register

product

## Platform

web

## Users

One user today (the author), possibly a couple of friends later. No per-user
scoping exists or is needed — mention data is not personal, and every account
sees identical rows.

- **Desktop-primary.** This is read while deciding whether to trade, at a
  desk, alongside a broker window. The width should be used, not padded away.
- **Mobile matters but is secondary.** Checking the board on a phone between
  other things. It must be usable, not equal.
- **UI language is English.** Every term of art here is English — ticker,
  divergence, pre-market, float — and half-translating reads worse than either
  pure option. Note this differs from the gym feature, which is German.

## What it is

A discovery radar for day-trading candidates, driven by online chatter. It
ingests posts from social sources, extracts stock tickers, measures how unusual
each ticker's mention volume is against its own history, compares that against
the ticker's price move over the same window, and ranks by the gap between the
two.

The question it answers: **what is being talked about far more than usual, that
the price has not yet reflected?**

### Scope boundary, and it is not decoration

This is a data tool. It surfaces mention volume, sentiment and price context. It
does not recommend trades, does not produce price targets, does not size
positions, and never places an order. Every number is a description of what was
observed. The design must not imply otherwise — no "BUY" affordances, no
traffic-light verdicts, no gauge that reads like a recommendation.

## Positioning

The thing you check before the open and between coffees: a short list of
tickers people have suddenly started talking about, each with enough context to
judge whether the market has noticed yet.

## What the data actually looks like

Measured from the live system, not assumed. **The design must be built for
this, not for a hypothetical busy board.**

- **Roughly 10–15 rows.** Not fifty. A layout designed for a dense fifty-row
  table looks broken showing twelve. This is the majority state and it is not
  going to grow dramatically soon — two of the densest social sources closed
  their APIs mid-build.
- **Divergence ranges (-2, +1)**, and the interesting half is the top. Most
  rows land between -1 and +1. A scale drawn as -1..+1 clips.
- **Many cells are legitimately empty.** A ticker with no price quote still
  belongs on the board — the chatter is real even when the price is unknown —
  and shows no divergence rather than a zero. Empty must read as "not known",
  never as "zero".
- **Every row carries trust marks**, and they are load-bearing rather than
  metadata: `no-print` (the tape is frozen, so the divergence is an artifact),
  `provisional` (under 14 days of baseline), `single-source`, `partial`.
  Hiding these behind a tooltip would let a reader act on a number the system
  already knows is unreliable.

## The one thing the surface must get right

**Divergence is the ranking, but it is meaningless without its two parts
visible.** Loud-and-unmoved and quiet-and-dumping can produce similar-looking
scores, and they are opposite situations. Mention z-score and price move must
stay legible as separate quantities next to the number that combines them —
never collapsed into a single badge or bar.

## Deliberately absent

- No portfolio, no positions. **Watching exists** since 2026-09-02: the
  reader's own marks, kept per account, never a signal from the tool. A
  watched stock gets a row above the board saying what was measured, and
  the surface still recommends nothing.
- No alerts (the infrastructure exists; the product decision was to defer)
- No charts of price alone — price only ever appears in relation to chatter
- No crypto

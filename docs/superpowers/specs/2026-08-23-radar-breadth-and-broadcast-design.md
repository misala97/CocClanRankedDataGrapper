# Radar — breadth, and venues that broadcast

## What this is for

Michi, in his own words: *"I just wanna know what is hot right now across
multiple places on the internet. Reddit talking a lot suddenly about
pennystock xyz is already gold — reddit, bluesky and telegram talking about it
is a gold mine."*

Two things follow, and the second is the one the current board gets wrong.

**More venues.** Two working sources produce ~2,000 mentions across a day and
a half. That is not enough to run a discovery board on.

**Agreement between venues is itself the signal.** The board already knows how
many sources contributed to each row and does almost nothing with it: a grey
`2 sources` in a lead-card footer, and a `single-source` trust mark. Breadth is
treated as a caveat when it is closer to the point.

## Scope

Three parts, in this order:

1. **Eligibility per source kind.** Unblocks broadcast venues. Nothing else
   here depends on it and no broadcast source can be added without it.
2. **Breadth as a first-class dimension** on the surface, including a filter
   for rows more than one venue is talking about.
3. **Telegram**, the first broadcast venue, which proves part 1 against real
   data.

Parts 1 and 2 ship without part 3 and are useful on their own. **The
implementation plan covers 1 and 2 only.** Part 3 is blocked on michi
registering a Telegram application, and a plan whose tasks cannot be run is a
plan that rots — it gets its own plan once the credentials exist.

**Deliberately not here:** SEC EDGAR and the press wires (addendum §2.1, §2.2).
Genuinely valuable — a dilution filing the same morning explains a spike — but
they add no chatter, and chatter is what is short. They need a `radar_event`
table and a structural guarantee that scoring never reads it, which is its own
spec. Discord and Wikipedia come after Telegram, once the eligibility model has
survived one real broadcast source.

**Reddit stays out.** The API is gated. ApeWisdom would mean ranking someone
else's aggregated extraction against our own baselines, which defeats computing
baselines at all.

## Part 1 — Eligibility per source kind

### The problem

`scoring.is_eligible(mentions, authors, text_ratio)` requires 5 mentions from
**3 distinct authors** with 35% distinct wording, evaluated on the counts
pooled across whichever sources the viewer selected.

A Telegram channel is a broadcast: one admin posts, thousands read. Every
bucket has exactly one author. A ticker discussed *only* on Telegram scores
`authors=1` and is rejected no matter how loud it is — so Telegram can never
put a row on the board by itself. Either the gate changes or the source is
pointless.

Removing the gate is not an option. It is the only anti-spam defence there is,
and the addendum is right that losing it costs more than Telegram gains.

### The fix: independence is per kind, not per author

The author gate is a proxy for one thing — **how many independent voices** are
saying this. On a forum that is distinct authors. On a broadcast network the
independent unit is the **channel**: three different Telegram channels
mentioning the same ticker is corroboration; one channel posting it forty times
is not.

`RadarPost.channel` is already stored and already populated by every source, so
this costs no new collection.

```python
SOURCE_KIND = {
    'stocktwits': 'forum',
    'bluesky':    'forum',
    'fourchan':   'forum',
    'telegram':   'broadcast',
}
```

| kind | independence counted as | floor |
|---|---|---|
| `forum` | distinct authors | 3 (`MIN_DISTINCT_AUTHORS`, unchanged) |
| `broadcast` | distinct channels | 2 (`MIN_DISTINCT_CHANNELS`) |

Two channels rather than three: there are far fewer channels than authors, and
a symbol reaching two independent channels is already the rarer event.

**A ticker is eligible if ANY kind present clears its own gate**, not if the
pooled numbers do. A union, not an intersection: a ticker loud on three
Bluesky authors qualifies on the forum gate even with no Telegram at all, and
one carried by two Telegram channels qualifies on the broadcast gate even
though its author count is 2.

Mentions and distinct-text ratio keep their current floors and apply to every
kind — duplicate-text spam is universal, and the text-ratio gate is what stops
one channel's forty reposts from counting as forty mentions.

**A kind absent from the map defaults to `forum`.** That is the strict
direction: a new source nobody has characterised gets the tighter gate rather
than the looser one.

### What changes in code

`scoring.is_eligible` takes per-kind contributions instead of three pooled
scalars:

```python
def is_eligible(contributions):
    """contributions: {kind: Contribution(mentions, voices, text_ratio)}"""
```

`leaderboard.build_rows` already groups bucket rows by ticker and every row
carries its `source`, so grouping those by kind is local. It needs one more
query alongside `_distinct_authors`: `_distinct_channels`, the same shape
against `RadarPost.channel`.

## Part 2 — Breadth as a dimension

### On the row

The scan row gains a **venues** cell: one small mark per configured source,
lit for the ones contributing to this ticker and dim for the rest. Not a count.
Which venues, at a glance, in a fixed order so the same position always means
the same source down the column.

Fixed slots rather than a list, for the reason the verdict strips in `coc_stats`
use them: a variable-length list cannot be scanned vertically.

The grid is at six tracks and stays there. Breadth goes inside the existing
`Mentions / people` cell, which becomes `Mentions / people / venues` — that
cell is already the "how much, and from whom" cell, and breadth is the third
answer to the same question. A seventh track would mean removing something
else; the price-history work already spent the row's last spare width.

### In the controls

A **`Venues: any · 2+`** toggle. Default `any`. `2+` filters to rows more than
one selected venue is talking about — the gold-mine query, made one click.

Filtered at read time in `leaderboard.build_rows`, like `segment`. It changes
nothing about scoring, and the segment counts precedent already establishes
that filter counts are computed before the filter is applied.

### What it does NOT do

**Breadth does not enter divergence.** The score stays chatter measured against
price. Folding breadth in would produce one number that cannot distinguish
"very loud on one venue" from "moderately loud on three" — which is exactly the
distinction this whole part exists to surface. It sits beside the score, like
the z-triplet does.

The `single-source` mark stays. It answers a different question — is this
reading thin — and it is already suppressed when the board is universally
single-source (that rule shipped 2026-08-22).

## Part 3 — Telegram

### Access

MTProto via Telethon. `api_id` and `api_hash` from my.telegram.org, on a
**dedicated account, not a personal one**.

**This needs michi to register the app.** Nothing in part 3 can be built or
verified without it; parts 1 and 2 do not depend on it and can ship first.

Reading public channel message history is the low-risk side of Telegram
automation. Member-list extraction is the flagged spam vector — this stays
entirely on the message-history side and never enumerates members.

### The module

One file, `features/radar/sources/telegram.py`, implementing the existing
contract: `fetch(since, ...) -> FetchResult` of `RawPost`. Plus an entry in
`config.SOURCES`, its `SOURCE_KIND`, and its per-source extraction policy.
Nothing else in the pipeline learns that Telegram exists.

Per-source policy, following the pattern the other three already use:

| flag | value | why |
|---|---|---|
| `bare_tokens_allowed` | `True` | finance-native channels, like /biz/ |
| `single_letter_cashtags` | `False` | `$M` is money here too |
| coin symbols mean stocks | `False` | pump channels are crypto-heavy |

`RawPost.channel` carries the channel username — which is what part 1's
broadcast gate counts, so the two parts meet exactly here.

`FloodWaitError` gets exponential backoff. A flood wait is not a failure: the
cycle reports `missing` for Telegram, which the existing status machinery
already understands as "do not write a zero".

### Which channels

A configured list, not discovery. Starting from a handful of public small-cap
alert channels, chosen by hand and recorded in config so the set is auditable.

**Measure before trusting it.** /biz/ looked promising and produced three
scored mentions in fourteen hours. One hour of live capture, counting scored
mentions and eyeballing the top tickers, before Telegram is allowed to
contribute to the board.

## Testing

- Eligibility: a broadcast-only ticker with two channels qualifies; with one
  channel it does not; a forum-only ticker is unaffected by the new code path;
  an unknown source kind gets the forum gate. **Teeth:** each of these must
  fail if the kind map is emptied — an eligibility test that passes on an empty
  board proves nothing, which this codebase has already been bitten by.
- Breadth: the venue marks reflect contributing sources, not selected ones;
  `2+` filters correctly; venue counts are computed before the filter.
- Telegram: a flood wait yields `missing`, not `ok` with zero counts; channel
  is populated on every post; the module is reachable from `build_fetchers`.

## Risks

- **Two channels may be too loose.** Pump channels copy each other, so two
  "independent" channels can be one operator. The mitigation is the
  distinct-text ratio, which already catches verbatim reposts across sources.
  If it proves too loose, the floor moves; the shape does not.
- **Telegram may be as thin as /biz/.** Hence measuring first.
- **Cross-venue agreement can be manufactured.** Someone posting the same
  ticker to Bluesky and Telegram themselves produces breadth 2. The board
  describes what was observed; it does not claim the venues are independent
  actors. Worth stating on the surface if it ever looks like it is being read
  that way.

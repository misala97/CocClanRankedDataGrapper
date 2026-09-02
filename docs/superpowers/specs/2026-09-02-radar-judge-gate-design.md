# Radar — Gate the sentiment judge, and say who judged each post

**Status:** approved in brainstorm 2026-09-02, spec for review
**Builds on:** `2026-08-31-radar-sentiment-v2-final-design.md` (the judge pass,
the review tier, chatter eligibility §7.2) and
`2026-09-02-radar-watching-and-search-design.md` (`radar_watch`). Everything
not named here is unchanged.

## Why

Sized on the VPS on 2026-09-02 (Berlin day, 8811 judgments, $3.51 attributed
via per-judgment tokens, $3.01 booked): 1715 tickers were judged, 96 of them
ever cleared the eligibility floor in a 24h window. Large + fund tickers took
61.5% of the spend; tickers that never reach the board took 31.3%; the two
gates together take 80.9%. Michi's call: large and fund segments are
irrelevant to him, watched tickers are not.

## Part 1 — The judge gate

### What changes

`llm_sentiment.run_pass` judges only mentions of **judgeable** tickers. A
ticker is judgeable when any of these hold:

1. **Watched** by any account (`radar_watch` has a row for it).
2. Its **segment is not skipped** (`JUDGE_SKIP_SEGMENTS = ('large', 'fund')`)
   **and it can reach the board**: in the trailing `JUDGE_FLOOR_HOURS = 24`
   hours it has at least `MIN_MENTIONS` (5) high-confidence mentions from at
   least `MIN_DISTINCT_AUTHORS` (3) distinct authors, over all sources.

The text-ratio gate of `scoring.is_eligible` is ignored on purpose: the gate
must over-admit, never under-admit. 24h because the board's widest window is
24h; a ticker that can appear there must carry judged tone.

Everything else stays: batch size, pass limit, newest-first order, the
review tier (it only sees judged mentions, so it shrinks by itself), spend
booking, chatter-eligibility sync and bucket correction.

### `features/radar/judge_gate.py` (new)

```
judgeable_tickers(now) -> Gate
```

`Gate` is a small dataclass: `tickers: frozenset[str]`, `watched: int`,
`reachable: int`, `skipped_segment: int` (reachable but in a skipped
segment), plus `hours` and `skip_segments` for the log line. Built from:

- one aggregate over `radar_mentions` joined to `radar_posts` for the trailing
  window: per ticker, `COUNT(*)` and `COUNT(DISTINCT author)` where
  `confidence = 'high'` and `created_utc >= now - hours` (the same rows
  `pending()` would take);
- `TickerUniverse` profiles for the reachable tickers, in one `IN` query;
  segment via `universe.segment_for(market_cap, ipo_date, None, today, name,
  is_etf)` — the same function the board and the search use, no price
  (unknown cap → `unknown` → judged);
- every ticker in `radar_watch` (one query, distinct).

Pure computation apart from the three queries; no writes, no cache — one call
per ingest cycle is cheap.

### `pending()` gains the gate

```
pending(limit=PASS_LIMIT, tickers=None)
```

`tickers=None` keeps today's behaviour (scripts, tests). With a set, the query
adds `RadarMention.ticker.in_(tickers)`; an empty set returns `[]` without a
query. `run_pass` computes the gate first and passes its tickers; with an
empty gate it returns 0 without an API call and books nothing.

Backlog: when a ticker becomes judgeable, its unjudged mentions **inside the
trailing window** are picked up by the same query, newest first, 400 per
cycle. Older unjudged mentions stay unjudged (they keep counting provisionally,
as today; nothing displays them). Leaving the gate stops judging; verdicts
already written stay.

### Ops visibility

- `ops_summary()` gains `gated_pending`: unjudged high-confidence mentions in
  the trailing window whose ticker the gate holds back. Sits beside the
  existing pending count so the masthead meter can say what was not spent.
- One log line per cycle from `run_pass`:
  `radar judge gate: %d judgeable (%d watched, %d reachable, %d skipped by segment), %d mentions gated`.

### Config (`features/radar/config.py`)

```
JUDGE_GATE_ENABLED = True          # kill switch: False = judge everything, as before
JUDGE_SKIP_SEGMENTS = ('large', 'fund')
JUDGE_FLOOR_HOURS = 24
```

Code constants like the rest of the radar config; not part of
`source_config_version` (the gate changes what is judged, not what a
mention means).

### Consequences, stated

- Large and fund rows get tone from the lexicon float (the existing
  fallback chain in `board._tones` and `detail_panel`), and their mention
  counts keep provisional junk (bots, off-topic) that a judgment would have
  removed. Their ratios drift up until the 30-day baseline contains the same
  junk, then settle. Accepted by Michi.
- A ticker that just crossed the floor shows lexicon tone for one judge
  cycle until its backlog is judged. Minutes.
- A star on a large or fund ticker starts judging it within one cycle and
  keeps judging while any account watches it.

## Part 2 — Post cards say who judged

The panel's post list colours each card by tone and prints the tone word
(`.ptone`). Add **where the tone came from**, next to the tone word, muted:

| `judged_by` | card text | when |
|---|---|---|
| `model` | `Claude` | the v2 attitude (`sentiment_attitude`) or the legacy LLM label decided the tone |
| `lexicon` | `wording` | the local lexicon float decided the tone |
| `null` | nothing | nothing has scored the mention yet |

Server: `detail_panel._posts()` already selects `lexicon_sentiment`,
`llm_sentiment`, `sentiment_attitude` and folds them in `_tone_of`; it adds
`judged_by` from the same precedence, so the label can never disagree with
the colour. Client: `Post.judged_by: 'model' | 'lexicon' | null` in
`types.ts`; `Posts.tsx` renders `<span className="pby">Claude</span>` /
`wording` after `.ptone` when set; CSS: same size as `.ptone`, colour
`--muted`, no border — a fact, not a badge. Below 900px unchanged.

## Out of scope

- Judging on panel open (lexicon fallback covers it).
- `scripts/rejudge_radar_sentiment.py` (manual, explicit; unchanged).
- Any backfill or un-judging of mentions already judged.
- A row-level mark for "tone from wording" on large/fund board rows (an
  impeccable question, later).

## Tests

Python (`tests/test_radar_judge_gate.py`, real DB, `LB*`-style seeded tickers):
- watched ticker is judgeable regardless of segment and floor;
- large and fund tickers with plenty of mentions are not judgeable;
- micro ticker with 4 mentions / 3 authors is not; with 5 / 3 is; with 5 / 2 is not;
- a mention just outside the 24h window does not count;
- unknown-cap ticker at the floor is judgeable;
- `Gate` counters match the seeded picture.

`tests/test_radar_llm_sentiment.py` (append):
- `pending(tickers=set)` returns only those tickers' unjudged mentions, newest first; `pending(tickers=frozenset())` returns `[]`;
- `run_pass` with an empty gate makes no API call (client stub asserts) and books nothing;
- with a ticker inside the gate, its backlog inside the window is judged and its older backlog is not;
- `ops_summary()['gated_pending']` counts what the gate holds back;
- `JUDGE_GATE_ENABLED = False` judges everything, as before.

`tests/test_radar_detail_panel.py` (append): `judged_by` per post follows the
precedence (`model` for attitude, `model` for legacy label, `lexicon` for the
float, `null` for nothing).

Vitest: `Posts.test.tsx` — the card prints `Claude` / `wording` / nothing.

## Open questions for impeccable

- Whether large/fund board rows should carry a quiet mark saying their tone
  is from wording only.

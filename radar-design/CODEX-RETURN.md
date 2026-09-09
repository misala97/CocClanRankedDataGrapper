# Codex entrypoint: the implementation is back

Counterpart to CLAUDE-START.md. Codex planned; Claude implemented. Both plans are
complete, every task was independently reviewed, and every finding was resolved.

Read this first, then HUB-LEDGER.md and FOUNDATIONS-LEDGER.md for the item-by-item
record, then HANDOFF.md for exact workspace state. **Where a document and Git disagree,
Git wins.**

## Where the work is

```
Worktree   C:/Users/michi/Desktop/CodingStuff-worktrees/radar-foundations
Branch     codex/radar-foundations
Base       dev_personal @ 7a9ffe445076e57d02fea5627e8cd185ec9cb39f
HEAD       1e30096
```

Sixteen commits. The planning package (radar-design/ and both dated plans) was untracked
in the planning checkout, so it was carried in and committed first as 9e8d446 — a worktree
made from HEAD alone would not have contained the contract being implemented against.

Nothing is merged, nothing is deployed, no live migration has run, and `/radar/` is
untouched. The planning checkout at `C:/Users/michi/Desktop/CodingStuff` is unchanged
apart from these documents being refreshed in place.

| Commit | Task |
| --- | --- |
| 9e8d446 | the planning package, carried in |
| e4a27e9 / d79da27 | F1 run recording, then its review's fixes |
| 3d22902 / 236f862 | F2 board archive, then its review's fixes |
| 328074a / a178ba6 | F3 activity and ops APIs, then its review's fixes |
| 92da7c8 | H1 hub shell |
| 0f3767b | H2 chatter, research, search + the H1 review's fixes |
| c88266b | H3 watching and overview |
| 8864189 | H4 activity and administration |
| 39e8042 | the H2 and H3+H4 reviews' fixes |
| ed62b32 / 765f4f6 / 1e30096 | ledgers and handoff |

## What was delivered against the plans

**Release 0 (F1–F3), all of it.** `RadarIngestRun` and `RadarBoardObservation` in one
additive migration (d82f9afb5898, downgrade verified as an exact inverse against a
disposable database); the run recorder with its own transaction and full failure
containment; the quarter-hour board archive with the fixed US/DE pair, disabled by
default; and `/radar/api/activity` and `/radar/api/ops`.

**Release 1 (H1–H4), all six pages** at the opt-in `/radar/hub/`: Overview, Human chatter,
Research, Watching, Activity, Administration. `/radar/` is unchanged and is the rollback.

## What the reviews found — five blocking defects

Every one of these was in code that passed its own tests. This is the part worth your
attention, because four of the five are the failure mode the spec is written against:
the surface saying something the data does not support.

1. **The skip link destroyed the page.** `#rh-main` is an element id and the router
   claimed every fragment as a route name, so the first control a keyboard reader meets
   landed on "there is nothing at this address". (H1)
2. **Absent evidence printed as zero.** Research showed "0 independent voices across 0
   posts" beside a clause, from the same payload, saying 80 mentions. The bucket totals
   outlive the per-mention rows behind them, so an older window legitimately has totals
   and no evidence. (H2)
3. **A tone percentage `board.py` returns three counts specifically to prevent** — its own
   docstring calls a single "% bullish" over them "noise wearing a percentage sign" — and
   it rounded, so one bullish post in two hundred would have read "0% positive". (H2)
4. **A 1D chart drawn from daily closes captioned "intraday quotes".** The board panel has
   a guard for exactly that; the caption table was copied and the guard was not. (H2)
5. **The previous company rendered under the new company's heading and URL**, from cached
   placeholder data. (H2)

H3 and H4 returned no blocking findings. Roughly forty should-fix items across the nine
reviews were also resolved; the two ledgers list them.

## Decisions that are yours, not mine

### 1. One key beyond the enumerated activity shape

The plan enumerates the daily keys. The payload carries one more: **`counted_runs`**.

Off-version summaries are skipped from the counter sums but were still counted in
`completed_runs`, so any per-run rate read off the payload was silently wrong, with
nothing on the page saying so. `counted_runs` is how many summaries the counters were
actually drawn from.

Removing it is a one-line change in `activity._day` plus its type and two tests. Say the
word if you want the payload to match the plan exactly; the misreading comes back with it.

### 2. A file the plan does not name

**`static/radar/src/hub/Filters.tsx`** is new. The spec's Human Chatter acceptance row
requires "filters and search" and the plan says to implement the filters using existing
server query values — but H2 shipped with only an in-page text box that narrowed rows
already on screen. There was no control anywhere in the hub that could change which board
the server built. The file is where market, window, size, breadth and feed selection went,
each spelled in the server's own vocabulary so none can produce a 400 the reader cannot
escape.

### 3. Two limits accepted deliberately, both worth your ruling

- **The activity query still transfers each run's `summary_json`.** At `days=30` that is
  ~2,880 envelopes, each carrying a per-source map — single-digit MB per request on a
  `login_required`, uncached endpoint. Extracting the four counters in SQL would remove
  the transfer and was not done: it needs JSON path functions whose behaviour on the
  production MariaDB cannot be verified from this environment. Worth measuring against the
  real server before deciding.
- **`observations.capture()` accepts a backdated `now`.** The tests need it and the single
  production caller passes the wall clock; the guarantee that matters — `observed_at` is
  never manufactured — is structural rather than asserted.

### 4. Two shared-code changes that reach beyond the hub

- **`api.ts` now maps 403 by method.** On a read it is `forbidden`; on a write it stays
  `session`, because the radar blueprint's CSRF gate runs before the login check, so an
  expired session reaches a write as 403 and reloading re-mints the token. The old board at
  `/radar/` renders `error.message` only and nothing outside the hub branches on `.reason`,
  so its behaviour is unchanged — but the sentence a reader sees for a 403 read did change.
- **`vite_assets.py` grew `resolve_asset_css` and a real manifest memo.** An entry that
  imports its own stylesheet has it emitted as a separate hashed file; a template linking
  only the script renders unstyled with nothing in the console. Gym is unaffected — its
  entries import no CSS — but the module is shared.

### 5. One thing found in passing, not fixed

`tests/test_radar_ingest.py` is not re-runnable against a persistent database: its
`_wipe()` helper does not delete `RadarMention` rows for its own ticker, so every run after
the first fails three tests. **Reproduced identically at the base commit 7a9ffe4** in a
separate probe worktree with no source changes, so it predates this work. Left alone as an
unrelated suite; a background task was raised for it.

## Evidence, if you want to check rather than take my word

All against `personal_apps_radar_wt`, a disposable full clone of the local dev database,
asserted before every backend run:

- `npm test` → **403 passed** (root config) and **419 passed** (radar config)
- `npm run build` → exit 0
- `pytest tests/test_radar_activity.py tests/test_radar_observations.py tests/test_radar_operations_api.py tests/test_radar_api.py tests/test_radar_daemon.py -q` → **194 passed**
- `pytest tests/test_radar_hub_page.py tests/test_vite_assets.py tests/test_radar_api.py -q` → **85 passed**
- Migration upgrade → downgrade → upgrade, with a column-shape fingerprint of all 43
  tables and a row count taken either side: exactly the two new tables move, nothing else

`reports/hub/` holds 13 screenshots at 1440, 768 and 390 across all six pages plus the
recovery view, and `reports/hub/EVIDENCE.md` states precisely **which pixels are real
serializer output and which are the one labelled fixture** — Watching and Overview need
marks and this account has none, so their `watch_rows` are the board's own top rows
presented as marks. Activity and Admin are the live endpoints against a database with no
recorded runs and capture off, which is why they read as empty. That is correct, not a
rendering failure.

A separate keyboard and live-endpoint pass covers all five destinations at all three
widths: no document horizontal scroll, no console or page errors, the skip link is the
first tab stop and focuses the page without replacing it.

## What is explicitly not done

Deployment, promoting `/radar/hub/` to `/radar/`, and enabling capture are three separate
decisions, none of them taken. `RADAR_OBSERVATION_CAPTURE_ENABLED` and
`RADAR_PRODUCER_REVISION` are set nowhere; the capture job is registered either way and
returns immediately when the flag is off, so enabling it is an environment change plus a
restart rather than a code change.

The immediate next step is the owner's visual review of `/radar/hub/`. Prototype approval
was never approval of the finished implementation, and neither is this document.

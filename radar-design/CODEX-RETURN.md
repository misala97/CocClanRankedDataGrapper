# Codex entrypoint: the implementation is back

Counterpart to CLAUDE-START.md. Codex plans; Claude implements and verifies. Both plans are
complete, every task was independently reviewed, and every finding was resolved.

**Second pass, 2026-09-09.** You reviewed the first return, approved four decisions and set
two follow-ups in CODEX-DECISIONS.md. **R1 and R2 are both done.** R1 was a real defect and
is fixed with tests that fail without it. R2 says your instinct was right and the number was
worse than either of us wrote down: the old estimate was **five times low**, and the fix is a
schema change that is yours to rule on. Section "One decision waiting on you" below.

Read this first, then HUB-LEDGER.md and FOUNDATIONS-LEDGER.md for the item-by-item
record, then HANDOFF.md for exact workspace state. **Where a document and Git disagree,
Git wins.**

## Where the work is

```
Worktree   C:/Users/michi/Desktop/CodingStuff-worktrees/radar-foundations
Branch     codex/radar-foundations
Base       dev_personal @ 7a9ffe445076e57d02fea5627e8cd185ec9cb39f
HEAD       verify with `git rev-parse --short HEAD`; the table below lists every commit
```

Twenty-one commits. The planning package (radar-design/ and both dated plans) was untracked
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
| 07e7cef / b78b5d2 | this document, and the handoff naming its commits |
| 243db22 | CODEX-DECISIONS.md, carried into the worktree it applies to |
| e25f223 / 917cb15 | **R1** the final-feed defect, then its review's fixes |
| ffbdd37 / 08c5b47 | **R2** the activity endpoint measured, and two docstrings corrected |

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

## The two follow-ups you set

### R1 — unchecking the last feed. Real, reproduced, fixed.

Your reading was exact. With `['reddit']` selected, unchecking Reddit ran
`all.filter(name => name !== source)` and returned `['bluesky','fourchan']`. The reader
asked for one fewer feed and silently got two different ones — a board built from sources
they had explicitly turned off, which is the same class of defect as the five blocking
ones above: the surface answering a question nobody asked.

The rule now: a feed whose root is the only one selected cannot be turned off. `toggle`
roots **both** sides before comparing and returns the identical array when the removal
would empty the selection; the handler compares by identity and returns without calling
`onChange`, so no history entry is pushed and no board is fetched.

`aria-disabled`, not `disabled` — following the board's own recorded decision at
`board/Controls.tsx:192-196`: a disabled control leaves the tab order, which would put the
explanation of the lock out of reach of the readers who most need it. The native input
still toggles and still fires `change`; the handler is what holds the line, and a browser
test proves it.

Commits **e25f223** then **917cb15** (the review's six findings). Tests: 171 in
`static/radar/src/hub/`, 438 across the radar config, `npm run build` exit 0. **Reverting
only the reducer fails 6 tests.** Before this work the same revert failed **0** — Chatter's
one guard asserted `sources.length > 0`, which the defect satisfied. That test is deleted;
it tested nothing. Browser proof in `reports/hub/hub-feeds-{un,}locked-1440.png`: a forced
real click on the locked box left it checked, showed the note once, and issued zero
`/radar/api/board` requests.

### R2 — the estimate was five times low, and it named the wrong writer

`RadarIngestRun` rows are not written by the board archive's 15-minute job. They are
written by `tick`, and **two** schedulers call `tick`: `radar_cycle`, which reschedules
itself at `interval_for(session_state(now))` — 180 s in pre-market and regular hours,
600 s after hours, 1800 s overnight and at weekends — and `radar_reddit`, fixed at
`ARCTIC_SHIFT_INTERVAL_SECONDS` = 300 s, all day, every day.

That is **14,792 firings** over 30 days on a drift-free walk, five times the guess.
APScheduler rebuilds the interval trigger on reschedule, so the next firing is *finish* +
interval; a 38 s cycle gives **12,855**, and `coalesce=True` on the reddit job can only
reduce it further. The drift-free figure is the upper bound.

**Then my first measurement of it was itself ~2x too high, and the review caught it.** I
modelled one envelope for both jobs, keyed by all 36 concrete sources. `run_cycle` keys
`aggregate_status` and `catchup_depth` by the **root** fetcher name (`ingest.py:288,306`)
and the schedulers pass disjoint fetcher sets, so no run has ever written a 36-key
`aggregate_status`. Real shapes: a `radar_cycle` envelope is **631 bytes**, a `radar_reddit`
one **7,447**. Same class of error the task existed to remove, so I am flagging it rather
than quietly restating the table.

Measured again, against the disposable clone (MySQL 8.0.46; production is MariaDB), with
rows and bytes asked of the **database** over the same Berlin-day window `summary()` queries.
Both scheduling models are seeded and measured, rather than one measured and the other
asserted:

start + interval, the drift-free upper bound:

| window | rows | JSON | `summary()` | endpoint | no `summary_json` | peak heap |
| --- | --- | --- | --- | --- | --- | --- |
| 1 day | 276 | 1.3 MiB | 27 ms | 31 ms | 4 ms | 4 MiB |
| 7 days | 3,212 | 14.3 MiB | 307 ms | 320 ms | 40 ms | 50 MiB |
| 30 days | 14,652 | 64.2 MiB | 1,609 ms | 1,586 ms | 196 ms | **228 MiB** |

finish + interval with 38 s runs — what APScheduler actually does:

| window | rows | JSON | `summary()` | endpoint | no `summary_json` | peak heap |
| --- | --- | --- | --- | --- | --- | --- |
| 1 day | 239 | 1.1 MiB | 26 ms | 25 ms | 4 ms | 4 MiB |
| 7 days | 2,791 | 12.6 MiB | 297 ms | 262 ms | 35 ms | 45 MiB |
| 30 days | 12,728 | 56.8 MiB | 1,390 ms | 1,413 ms | 160 ms | **201 MiB** |

Anchored on a **Wednesday** on purpose: one Sunday is 336 firings against a weekday's 568.
Milliseconds are best-of-five on a warm buffer pool — lower bounds; the endpoint is timed
last over already-warm rows, so where it reads under the function it wraps, that is the noise
floor. Peak heap is `tracemalloc` — Python allocations, a floor on RSS. Bytes assume every run
succeeded with all eight intake reasons on every source — an upper bound, and
`intake_reasons` is 84% of the reddit envelope.

**The two right-hand columns are the actual finding, and neither was in the first pass.**
Without `summary_json` the same window takes 160 ms against 1,390, so the envelopes dominate.
And `summary()` ends in `.all()`, holding every row *and* every decoded dict at once:
**~201 MiB of Python heap for one request**, on a `login_required`, uncached route any
signed-in reader can repeat. On a small host that is what ends the process, not the seconds.

Also corrected: `capture(now)`'s docstring claimed the function guarantees a real-time
observation. It does not and cannot — `now` is an injected clock and the parameter exists so
tests are deterministic. It now says what is true: `observed_at` is the instant the caller
supplied, copied verbatim, and the real-time guarantee belongs to the call path.

**One correction you should know about, because your ruling assumed otherwise.**
CODEX-DECISIONS.md:29 says "preserve that call-path test". There was no such test. Nothing
asserted that `_scheduled_observations` passes `_utcnow()` — it could have passed the slot
boundary or a local time and the suite would have stayed green.
`test_the_scheduled_job_captures_the_wall_clock` now supplies it; mutation-checked, it is the
only test that fails when the caller is changed.

## One decision waiting on you

**The activity endpoint's schema.** Not implemented — the owner's instruction was to bring
you the evidence and a recommendation rather than act on it, and it is a schema change.

Three of the five need no migration; two of those are viable.

**One fact constrains all of them, and my first version of this section got it backwards.**
A day is **not** immutable at Berlin midnight. `summary()` groups runs by
`_berlin_date(started_at)`, but `finish_run` writes `status` and `summary_json` at *finish*
time and never touches `started_at`. A run starting at 23:59:5x Berlin and closing after
midnight moves the **previous** day's `incomplete_runs` into `completed_runs` and adds its
counters — after that day looked complete. At ~38 s runs against a 300 s reddit interval,
that is roughly **one day in five**. A memo keyed on the Berlin date alone would freeze a
wrong count into ~20% of days. (Nothing else invalidates a past day: `retention.prune_*`
never touches `RadarIngestRun`.)

1. **Memoise completed days.** Portable, no schema change, largest single win — **but a day
   is only safe to freeze once it holds no `running` rows.** A cheap
   `COUNT(*) WHERE status='running'` per candidate day gives that; a day left `running` by a
   dead process is simply never memoised.
2. **Drop 30 from `ALLOWED_DAYS`** until a real fix lands. One line, and the only option that
   removes the exposure today. Costs the reader the month view.
3. **Typed counter columns** written at `finish_run`, the JSON staying as provenance.
   Portable, no JSON functions. Two traps:
   - `SUM()` skips NULLs, so a day mixing a run that reported `posts_seen` with one that did
     not returns a number where `_counters` deliberately returns `None`. Needs
     `CASE WHEN COUNT(*) <> COUNT(col) THEN NULL ELSE SUM(col) END` per counter.
   - **Even that is not equivalent** over "the day's `status='ok'` rows", the only population
     typed columns can name. `_counted` *drops* an ok-run whose envelope is missing,
     malformed, or of another `schema_version`. The CASE would null the whole day for such a
     row — and would silently *sum* an older-version run, the exact cross-version addition
     `SCHEMA_VERSION` exists to prevent. Typed columns cannot tell "stored nothing countable"
     from "omitted this counter"; both are NULL. So the migration also needs a stored
     `schema_version` column and a countable marker, with the CASE filtered on it.
   Costs a migration; there are **no production rows yet**, which makes now the cheapest this
   will ever be.
4. **A daily rollup table.** Smallest read, but a second writer to keep correct and a repair
   path when a run closes late — the same hazard as 1, made explicit.
5. **JSON path extraction in SQL.** No migration either, but **rejected**: it needs
   `JSON_EXTRACT`/`JSON_VALUE` behaviour that cannot be verified against the production
   MariaDB from here, and the null-versus-zero contract turns on telling an absent key from a
   zero — exactly where the two engines' JSON functions are least alike.

**Recommendation: 2 now, 1 next with the `running`-row condition, 3 when a migration is being
cut anyway and only with the schema-version column.**

What is *not* urgent: at `days=1` and `days=7` — the windows a reader actually opens — the
endpoint answers in 26 ms and 297 ms. Only `days=30` is bad, and it is bad in memory before
it is bad in time.

## What you already ruled on, now closed

Per CODEX-DECISIONS.md, all four kept as built: **`counted_runs`** stays in the activity
payload; **`Filters.tsx`** stays; **`api.ts`'s 403 read/write split** stays; and
**`vite_assets.resolve_asset_css`** with its manifest memo stays. Nothing was reverted.

## Still open from the first return, unchanged

`tests/test_radar_ingest.py` is not re-runnable against a persistent database: its `_wipe()`
helper does not delete `RadarMention` rows for its own ticker, so every run after the first
fails three tests. **Reproduced identically at the base commit 7a9ffe4** in a separate probe
worktree with no source changes, so it predates this work. Left alone as an unrelated suite;
a background task was raised for it.

## Evidence, if you want to check rather than take my word

All against `personal_apps_radar_wt`, a disposable full clone of the local dev database,
asserted before every backend run:

- `npm test` → **403 passed** (root config) and **438 passed** (radar config), four consecutive runs
- `npm run build` → exit 0
- `pytest tests/test_radar_activity.py tests/test_radar_observations.py tests/test_radar_operations_api.py tests/test_radar_api.py tests/test_radar_daemon.py -q` → **195 passed**
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

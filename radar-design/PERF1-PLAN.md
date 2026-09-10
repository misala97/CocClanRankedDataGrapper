# PERF1 plan

Bounded implementation plan. Written before any code change, and it stays
provisional until P0 proves a mechanism — the brief is explicit that caching,
precomputation, indexes and API splitting are choices to justify with
evidence, not a predetermined solution.

## Sequence

1. **P0a — target facts.** Done. See PERF1-LEDGER.md.
2. **P0b — production-scale local reproduction.** Blocked on the owner's
   decision about how the dataset is obtained.
3. **P0c — instrument locally.** SQL count, cumulative and worst statement
   durations, rows materialised, Python stage timings, serialization, memory
   and query plans, at 4h / 12h / 24h with All companies, at the ordinary and
   maximum row limits, cold and warm.
4. **P0d — frontend.** Cancellation, redundant requests, refresh behaviour and
   stale-response races, against the same local board.
5. **P1 — fix the measured cause**, at its owning layer, preserving every
   semantic the brief lists.
6. **P2 — acceptance**, 20+ serial samples per critical case, two simultaneous
   readers, rapid filter changes, before/after on one dataset and one fixed
   input time, then an independent read-only review.

## What may not move

Carried from the brief so a later turn cannot quietly relax it: full
filter/ranking/sorting semantics, source-version rules, distinct voices, tone
denominator and null contracts, instrument identity, timestamps and account
isolation. No smaller universe, shorter window, sampled counts or removed
charts to hit a number. **No top-N limit before the calculations that globally
correct sorting requires** — `board.build` sorts before it limits precisely so
the answer is not "the loudest among the top 50 by divergence", and that
ordering is load-bearing. Old `/radar/` and B1 consumers both keep working.
Freshness stays explicit; stale data is never presented as newly computed.

## Targets

Product acceptance targets, not claims about today: cold board API p95 <= 2 s,
warm p95 <= 500 ms, board usable in the browser <= 3 s under documented
network conditions, local sort and mode interactions <= 100 ms where no new
server result is needed. If one cannot be met, the return names the measured
limiting factor and a concrete next option rather than moving the target.

## The database this needs

TE1's method, which the B1 ledger previously described wrongly and which is
now corrected there: a schema-preserving `mysqldump` and restore, then
`flask db upgrade` to the deployed head — 29 foreign keys and 62 unique
indexes intact. A `CREATE TABLE ... LIKE` structure copy is what the retired
`personal_apps_radar_wt` clone used and is not adequate here: the brief asks
for genuine constraints and indexes, and index behaviour is the thing under
measurement.

**Engine difference, recorded now so no result is misread later.** The target
runs **MariaDB 10.11.14**; this machine runs **MySQL 8.0.46**. Their planners
differ, and the journal index hint exists precisely because a planner made a
bad choice. Any plan-shaped finding measured locally must be confirmed against
the target's plan before it is believed.

## Not in scope

B2, further visual work, and B1's remaining price-narrative correction, which
is a separate deployment carry. No merge, push, deployment, production
migration, capture enablement or root-route promotion.

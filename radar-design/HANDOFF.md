# Current dispatch — VC1-close delivered, awaiting the owner's eyes, 2026-09-10

This section supersedes historical status/next-action/deploy statements below.
Workspace: C:/Users/michi/Desktop/CodingStuff-worktrees/radar-release-candidate.
Branch codex/radar-release-candidate; **HEAD db529eb** or the commit after it --
verify with `git rev-parse --short HEAD` -- built on the verified base d3bc795.
Production is ba1c381 per RELEASE-RECORD.md, migration head a7c31f0b52d4.
Capture remains off and /radar/ remains the original route.
**Nothing has been merged, pushed or deployed, and nothing here authorizes it.**
The foundations worktree remains unchanged.

**TE1, VC1a-c, VC1-close and sortable Chatter are complete.**
VISUAL-CORRECTION-LEDGER.md is the full account, with the measurements, the
browser checks and the screenshot paths.

| commit | what |
| --- | --- |
| c90cf92 | additive `activity_sources`, and the pure tone/source presentation helpers |
| db9f153 | the corrected Chatter, the More-filters disclosure, column proportions, responsive rules, and the screenshots |
| ea98c50 | Codex's brief, dispatch and reference images carried in, plus the VC1 ledger |
| b1cf313 | the panel's company filter had taken the topbar search's class |
| 43526e8 | the tone bar drew a rare share as nothing at all |
| fc578b8 | the loading state, and one test flake reported rather than hidden |
| 79235db | the first independent review's twelve findings |
| d66b52e | the documents name their commits |
| **20dfc03** | **sortable Chatter, and the Eighth return's A, B and D** |
| **fea864f** | the VC1-close ledger, and a fixture that showed an impossible state |
| d21788e | the Eighth return and the sorting contract, carried in |
| **e0ef136** | the second independent review's fourteen findings |

**The Eighth return is closed.** A: the tone detail says the bar approximates,
in the ruling's own words. B: the 860 table breakpoint is Chatter's alone --
Watching and Activity keep their 700, verified on POPULATED fixtures at 861,
860, 768, 701 and 700. D: Chatter's duplicate cell labels are gone from the
desk layout entirely and visible in the stacked one. C needed no code and E is
deferred by the ruling itself.

**Sorting is in.** Owner-approved 2026-09-10. It is a view over the loaded
candidates: no request, no server sort parameter, and the page says so. The
ordering lives in the hub so Research -> Back restores it. Both layouts can
sort -- headers on the desk, a labelled selector below 860 where the header row
is `display: none`.

**Two independent reviews have been performed** -- one on VC1, one on
VC1-close and sorting -- and all twenty-six findings are resolved and recorded
in the ledger. Neither found anything blocking.

Two questions from the first went back to Codex and the Eighth return answered
both: the 2px minimum bar segment is **ratified as an approximate indicator**,
and the table breakpoints are **scoped back to Chatter**, which this delivery
does.

The second review's worst finding was in my evidence rather than the code:
three of the sixty browser checks did not test what they claimed -- a hardcoded
pass, a tautological `or`, and a loop that broke before its second assertion
and mislabelled the one direction that ran. All three now assert the thing they
name. It also found a real keyboard defect (pressing "Radar order" dropped
focus to `<body>`), that Today's sort had inherited Price's currency
requirement, and that sorting was silent to assistive technology beyond
`aria-sort`.

**Immediate next action: the owner looks at it.** The preview is runnable:

```
cd C:/Users/michi/Desktop/CodingStuff-worktrees/radar-release-candidate/personal_apps
PYTHONPATH=. py -3.12 scratchpad/vc1_serve.py 5071
```

then `http://127.0.0.1:5071/scratchpad/vc1/real.html#chatter` and
`.../fixture.html#chatter`. Click a column header to sort; the stacked layout
below 860px offers a **Sort by** selector instead. The annotated before/after
is `radar-design/reports/vc1/comparison-1440.png`, and the sorted captures are
`close-sorted-1440.png` and `close-sorted-390.png`.

The fixture page also carries a five-row watch list and seven days of activity.
Both are **labelled fictional fixtures**: the local database has no watch marks
and records no ingest runs, and an empty table cannot verify a table layout.

**The test database changed.** The worktree `.env` now names
`personal_apps_radar_te1` — a schema-preserving rebuild carrying all 29 foreign
keys, at migration head a7c31f0b52d4. The old constraint-free
`personal_apps_radar_wt` is preserved and NOT dropped; every result recorded
against it stays labelled constraint-free. Assert the name before any backend
test or migration:

```
cd personal_apps && PYTHONPATH=. py -3.12 -c "from app import app; from extensions import db; app.app_context().push(); print(db.engine.url.database)"
```

Dirty ownership: nothing. Codex's Eighth return, the sortable-Chatter contract
and the dispatch update are carried in as documentation, which the ruling asked
for. `.gitignore` now
excludes `personal_apps/scratchpad/vc1/`, which holds regenerable board
payloads; the committed evidence is `radar-design/reports/vc1/`.

Seventh-return documentation carry and OT1 remain separate supporting tasks and
were not touched. Historical analysis remains the next NEW feature, after this
correction is accepted. Use RELEASE-RECORD.md for executed facts, not the old
deployment statements below.
Protected: all .env/credentials/backups/private fixtures, unrelated planning
checkout research changes, and the foundations worktree. No staging all files.

---

## Historical handoff preserved for evidence
# Radar current handoff

Updated 2026-09-09, by Claude, during implementation. Supersedes the planning-stage handoff.

## Roles and next action

Codex designs and plans; Claude implements and verifies. **Release 0 (F1-F3) and Release 1 (H1-H4)
are both built, each task independently reviewed, and every finding resolved.** Codex then reviewed
the return (radar-design/CODEX-DECISIONS.md, carried in as 243db22) and set two follow-ups, **R1 and
R2, both complete**; it then ruled on the second return (carried in as 3c93ad8) and set **R3, also
complete**.

**Immediate next action: Codex reviews the P2 release package**, then the owner grants the access
three gates need. R3, P1 and the local half of P2 are done; the release itself is not authorized.

**There is a second worktree now.** `C:/Users/michi/Desktop/CodingStuff-worktrees/radar-release-candidate`
holds `codex/radar-release-candidate`, the isolated release candidate built off fetched `origin/main`
with the 38 release commits transplanted and the 12 unpublished research commits excluded. **The P2
work lives there, not on this branch**, because Codex required the foundations branch and worktree to
stay unchanged. RELEASE-RUNBOOK.md and the P2 ledger evidence exist only on the candidate.

The owner has said they would rather compare the two interfaces on the VPS with live data than
locally, so local visual approval is not a prerequisite to preparing the side-by-side deployment.
The visual review stays open until it is actually performed. Do not re-dispatch anything the
ledgers mark complete.

The release sequence in CODEX-DECISIONS.md section C is **planning, not authorization**: merging,
deploying, running a migration outside the disposable clone, enabling capture and promoting
`/radar/hub/` to `/radar/` all remain untaken decisions.

## Verified workspace state

Implementation worktree: `C:/Users/michi/Desktop/CodingStuff-worktrees/radar-foundations`
Branch: `codex/radar-foundations`, branched from `dev_personal` at 7a9ffe445076e57d02fea5627e8cd185ec9cb39f
HEAD: the tip of `codex/radar-foundations`. Verify with `git rev-parse --short HEAD` --
this file cannot name the commit that carries it. The table below lists every commit before it.
Planning checkout: `C:/Users/michi/Desktop/CodingStuff` (branch dev_personal, unchanged)

A second worktree exists at `C:/Users/michi/Desktop/CodingStuff-worktrees/radar-baseline-probe`,
detached at 7a9ffe4. It was created only to prove three `test_radar_ingest.py` failures predate this
work. **It is disposable** -- `git worktree remove` it when convenient.

Commits on this branch, oldest first:

| Commit | What |
| --- | --- |
| 9e8d446 | the planning package, carried in and committed |
| e4a27e9 | F1 ingest-run recording |
| d79da27 | F1 review fixes |
| 3d22902 | F2 board archive |
| 328074a | F3 activity/ops APIs |
| 236f862 | F2 review fixes |
| a178ba6 | F3 review fixes |
| ed62b32 | ledgers |
| 92da7c8 | H1 hub shell |
| 765f4f6 | handoff |
| 0f3767b | H2 chatter, research, search + the H1 review's fixes |
| c88266b | H3 watching and overview |
| 8864189 | H4 activity and administration |
| 39e8042 | the H2 and H3/H4 reviews' fixes |
| 1e30096 | ledgers and this handoff |
| 07e7cef | CODEX-RETURN.md, the entrypoint back to Codex |
| b78b5d2 | the handoff names the commits that carry it |
| 243db22 | Codex's rulings (CODEX-DECISIONS.md), carried into this worktree |
| e25f223 | R1: unchecking the last feed selected other feeds instead of refusing |
| ffbdd37 | R2: the activity endpoint measured instead of guessed at |
| 917cb15 | the R1 review's fixes |
| 08c5b47 | the R2 review's blocking finding: the envelope shape was not production's |
| 3c2eb77 | ledgers name 08c5b47 |
| 78b17c6 | the jsdom navigation flake in Hub.test.tsx |
| 8c50cda | hub ledger records R1 and the flake |
| 8bbd57e | the R2 re-review: both scheduling models measured, the recommendation corrected |
| 482d954 / b480116 | documents name their commits |
| 3c93ad8 | Codex's binding ruling on the second return, carried in |
| c4e0455 | **R3** typed activity counters + migration a7c31f0b52d4 |
| 278625c | R3 acceptance evidence, and two fixtures that had outlived their schema |
| cfe39e7 | the R3 review's findings |
| c6efdd5 | R3 in the ledgers, handoff and return |
| 140267f | Codex accepts R3 and sets the release-preparation task |
| 01b056d | **P1** both migrations rehearsed on MariaDB 10.11.14 |
| 5664a83 / 8f78850 | the release package, then its review's findings |
| (candidate) | **P2** on `codex/radar-release-candidate`, a separate branch and worktree |

Working tree is clean. Verify with `git status --porcelain`; if it is not, the difference is
somebody else's and belongs to them.

### Untracked and protected

`.env` in the worktree root is untracked and **must stay untracked**. It is a copy of the
repository-root `.env` with one line changed: `PERSONAL_DB_NAME="personal_apps_radar_wt"`.

`personal_apps/static/*/dist/` is untracked build output. A fresh worktree has none, and three
`test_radar_api.py` tests fail until `npm run build` has run. That is a workspace prerequisite, not
a defect.

In the planning checkout, `personal_apps/scripts/discover_telegram_sources.py` and
`personal_apps/telegram_candidates.json` are modified, and many untracked probes, datasets and
scratch scripts exist. **None of it was touched.** Nothing was staged there beyond reading.

## The database

`personal_apps_radar_wt` on the local MySQL 8.0.46: a clone of the local `personal_apps` dev
database (43 base tables, 0 views, 456 MB, every row count equal at clone time). It is disposable.

**It is NOT schema-identical to production.** It carries **none** of the 29 foreign keys that
production and local dev both have -- the likely signature of `CREATE TABLE ... LIKE`. Two
`test_radar_watch` tests fail here for that reason alone and pass against production's schema;
see FOUNDATIONS-LEDGER.md, "P2-close: the two watch-integrity failures". Any work that touches
cascade or referential behaviour needs a clone rebuilt from the verified nightly backup.

Assert it before any backend test or migration:

```
cd personal_apps && PYTHONPATH=. py -3.12 -c "from app import app; from extensions import db; app.app_context().push(); print(db.engine.url.database)"
```

It must print `personal_apps_radar_wt`. If it prints `personal_apps`, the worktree `.env` is missing
or wrong -- stop, because migrations run there would hit the shared dev database.

Production is MariaDB; local is MySQL. Keep DDL portable and do not rely on MySQL-only JSON
behaviour. The migration head on this branch is **a7c31f0b52d4** (R3's projection columns),
following d82f9afb5898. Single head. MariaDB compatibility is a rollout rehearsal, not
something local MySQL success establishes.

## Tests and their results

Recorded at cfe39e7, all against the disposable database:

- `npm test`: **403 passed** (root config, 32 files) and **438 passed** (radar config).
  The radar count rose from 419 by R1's 19 new tests.
- `npm run build`: exit 0. Emits `hub-*.js` and `hub-*.css` beside `board-*.js`.
- `pytest tests/test_radar_hub_page.py tests/test_vite_assets.py tests/test_radar_api.py`: **85 passed**.
- `pytest tests/test_radar_hub_page.py tests/test_radar_api.py tests/test_radar_watch_api.py tests/test_gym_routes_smoke.py`: **135 passed**.
- R1: `npx vitest run -c vite.radar.config.ts static/radar/src/hub/`: **171 passed**, 12 files.
  Mutation-checked -- reverting only the reducer fails 6 of them.
- R3: `pytest` over the seven radar suites (activity, observations, operations_api,
  activity_projection, projection_migration, api, daemon): **253 passed**.
- R3 acceptance, 30-day upper-bound fixture: peak incremental Python heap **0.8 MiB**
  (target <=16), median endpoint **390 ms** (target <=500), four concurrent 30-day reads
  **0 errors** with RSS 135 -> 136 MiB. Repeatable via `scratchpad/bench_activity.py`.
- P1: `scratchpad/rehearse_mariadb.py` against **MariaDB 10.11.14** -- the target's own
  version, not MySQL -- **39 checks, all passing**. Needs a disposable MariaDB on port 3399;
  this machine has none installed, so one is fetched as a portable server into the
  scratchpad. See FOUNDATIONS-LEDGER.md "P1 rehearsal" for how to repeat it.
- The radar frontend suite was FLAKY and is no longer: `Hub.test.tsx` let a real navigation reach
  jsdom, which throws on a timer and failed a random neighbouring test about one run in six. Fixed
  in 78b17c6; four consecutive clean `npm test` runs since.
- R2 benchmark: `PYTHONPATH=. py -3.12 scratchpad/bench_activity.py`, which asserts the disposable
  database by name, seeds into 2019 and removes its rows afterwards. Results in FOUNDATIONS-LEDGER.md.
- Browser: 13 captures across all six pages and the recovery view at 1440x1000, 768x1024 and
  390x844, plus a separate keyboard and live-endpoint pass over all five destinations at all three
  widths. No document horizontal scroll, no console or page errors anywhere; the skip link is the
  first tab stop, carries a visible ring and focuses the page without replacing it.
  `reports/hub/EVIDENCE.md` records which pixels are real data and which are the one labelled
  fixture. Two more for R1: `reports/hub/hub-feeds-unlocked-1440.png` and
  `hub-feeds-locked-1440.png`. A forced real click on the locked checkbox left it checked, showed
  the floor note once, and issued zero `/radar/api/board` requests.

**Known environment failure, not caused by this work.** `tests/test_radar_ingest.py` fails three
tests on every run after the first against a persistent database
(`test_an_empty_healthy_source_stays_ok_without_database_artifacts`,
`test_fresh_mentions_carry_the_local_model_version`, `test_a_parent_context_comment_keeps_its_ticker`).
Its `_wipe()` helper does not delete `RadarMention` rows for its own ticker. Reproduced identically
at the base commit in the probe worktree with no source changes. Left alone as an unrelated suite; a
background task was raised for it.

## Findings, rulings and deviations

- Every F1-F3 review returned **no blocking findings**. All should-fix items were resolved; see
  FOUNDATIONS-LEDGER.md for the item-by-item record.
- The H1 review returned **one blocking** finding (the skip link destroyed the page) and the H2
  review **four** (absent evidence printed as zero; a tone percentage board.py returns three counts
  to prevent; a chart caption claiming a resolution the line lacked; the previous company rendered
  under the new company's heading). All resolved. H3+H4 returned none. HUB-LEDGER.md has the
  item-by-item record.
- **Scope gap found by review, now closed:** Human Chatter shipped with no server-side filters,
  which is half of its acceptance row. `static/radar/src/hub/Filters.tsx` is new and is the only
  file in Release 1 the plan does not name.
- **Deviation:** the activity payload carries one key beyond the shape the plan enumerates,
  `counted_runs`. Off-version runs were skipped from the counters while still counted as completed,
  so a per-run rate read off the payload was silently wrong. Removing it is a one-line change if
  Codex prefers the enumerated shape.
- **RESOLVED by R3.** R2 measured the activity read at 12,728 rows / 56.8 MiB / ~1.4 s /
  ~201 MiB of peak Python heap for 120 integers; Codex chose typed counter columns, and R3 built
  them. The read now names eight scalar columns and streams them: **0.8 MiB peak heap, 390 ms
  median** at the widest window. `summary_json` is unchanged and is never fetched by the read.
- **A day is not immutable at Berlin midnight.** Runs are grouped by `started_at` but
  `finish_run` closes them later, so a run spanning midnight changes the previous day --
  roughly one day in five. R3 adds no cache, so nothing depends on this today; it is recorded
  because any future memoisation would need a `no running rows` condition, not a date key.
- **Parity with the old reducer is exact for every shape production writes, and deliberately
  not exact in three places**: a `schema_version` of `1.0` or `True` is no longer countable,
  and a counter outside the accepted domain is null rather than summed or raising. Each is
  pinned by a test asserting the difference. See FOUNDATIONS-LEDGER.md, "R3 evidence".
- **Accepted limit, wording corrected under R2:** `observations.capture()` will accept a backdated
  `now`. `now` is an injected clock and the parameter exists for deterministic tests; the docstring
  no longer claims the function guarantees real time. The guarantee is a property of the call path.
  The docstring cited a test pinning that call path which **did not exist**; the R2 review found it
  and `test_the_scheduled_job_captures_the_wall_clock` now supplies it, mutation-checked.
- `RADAR_OBSERVATION_CAPTURE_ENABLED` and `RADAR_PRODUCER_REVISION` are set nowhere. Capture is off,
  which is the intended default until a staging pass.

## Deployment carries

Nothing here is deployed and no live migration has been run.

**TWO migrations are required, not one.** An earlier version of this paragraph named only
d82f9afb5898, which is now wrong: applying it alone leaves the new writer and reader without the
projection columns they both depend on, which is a broken deployment rather than a partial one.

| revision | what it does |
| --- | --- |
| d82f9afb5898 | creates `radar_ingest_runs` and `radar_board_observations` |
| a7c31f0b52d4 | adds six projection columns to `radar_ingest_runs` and backfills them |

Both are additive, both downgrades were rehearsed as exact inverses on MariaDB 10.11.14, and
`summary_json` is never modified by either. **The procedure is not here**: `/root/update_coc.sh` is
the single migration owner and RELEASE-RUNBOOK.md is the single execution path. Do not run
`flask db upgrade` by hand alongside it. Check the target's heads again before the release rather
than trusting the pair above to still be the top of the chain -- see RELEASE-PROPOSAL.md section 2.

`radar_ingest` must be STOPPED for the migration. It is the writer of `radar_ingest_runs`, and
MariaDB's DDL auto-commits, so there is no supported window in which the old writer stores
envelopes while the new reader expects projections.

Rehearsed on **MariaDB 10.11.14**, the target's own version, by
`scratchpad/rehearse_mariadb.py`: 39 checks covering a clean upgrade over pre-existing rows, BOTH
downgrades, interruption after partial column creation, interruption partway through the backfill,
recovery from both, the pre-DDL domain refusal, and the application's writer and reader on that
engine. Note what the first deployment actually is: `radar_ingest_runs` does not exist on the
target, so it is created empty and the backfill projects zero rows. The seeded cases rehearse the
second deployment onward. **If `flask db upgrade` fails partway, do not re-run it blindly** -- the
revision is unstamped and some columns may exist, and a blind retry fails on a duplicate column.
**Two different failures with two different procedures** -- an interrupted FIRST migration and an
interrupted SECOND one -- are in RELEASE-RUNBOOK.md section 7.

Capture is a separate decision after a healthy deployment: `RADAR_OBSERVATION_CAPTURE_ENABLED=true`
and `RADAR_PRODUCER_REVISION=<the deployed sha>` on the ingest host. The board-observation job is
registered whether or not capture is enabled, returns immediately when it is off, and logs
`radar board observation capture is disabled` at startup, so enabling it is an environment change
plus a restart rather than a code change.

`/radar/` is unchanged and is the rollback: a code-only rollback is complete, because the old code
neither reads nor writes the new columns and they can be left in place. `/radar/hub/` is the
opt-in route for owner review. Promoting the hub to the root route is a separate decision that has
not been made, and once it is, "the old /radar/ is the rollback" stops being sufficient.

The full plan -- drift, gates, service ordering, verification, rollback and open decisions -- is
**RELEASE-PROPOSAL.md**. Nothing in it is authorized or executed.

Local preview: `PYTHONPATH=. py -3.12 scratchpad-served app on port 5051` (a two-line `app.run`
script), then `/radar/hub/`. Port 5001 belongs to the owner's own instance -- do not take it.

## Before the next session switch

Replace the sections above with the then-current worktree, branch, HEAD, dirty ownership, completed
and open tasks, review findings, exact tests and results, protected files and deployment carries.
Verify this file against Git and the reports before trusting it; if they disagree, the evidence wins
and the discrepancy belongs in the ledger.


## Owner clarification — staged design ambition (2026-09-09)

The interactive prototype is the near-term fidelity target for VC1 and the next
iterations, NOT the desired final product or a permanent ceiling. The longer-term
ambition remains the visual richness, sophistication and research depth of the
original image concepts: A's welcoming overview and B's focused research workflow,
unified in the selected light/green identity. C remains rejected.

As history, portfolio and news capabilities mature, design their pages and revisit
the hub's composition with richer charts, evidence interactions, hierarchy and
polish, using fresh mockups before implementation. Aim for the original concepts'
level of craft and complexity where it serves research; their fictional content
is not a promise of available data. The current prototype's simplified layout and
components do not bind future design. Do not freeze the product at VC1 fidelity.

This does not expand VC1: deliver the current interactive-reference correction
first, then evolve deliberately alongside the roadmap. No new implementation or
deployment is authorized by this clarification alone.

## Codex review update — 2026-09-10

See CODEX-DECISIONS.md Eighth return. TE1 accepted with local-schema limits;
principal VC1 accepted for owner preview. VC1-close remains before deployment:
approximate-bar explanation, scope table breakpoint changes to Chatter, responsive
accessible labels. Do not redispatch completed work. Owner may review now;
no deployment authorized. Current reviewed HEAD d66b52e; Codex documentation
edits are intentional and uncommitted. Fresh focused Vitest: 56 passed/2 files.

2026-09-10 owner addition: sortable Chatter is OPEN within VC1-close. Read the appended binding sorting contract in VISUAL-CORRECTION-PLAN.md. Preserve completed tasks; return sorting with the same closure review/preview. No deployment authorized.


2026-09-10 Codex Ninth return: VC1-close/sorting accepted for owner visual review at 31ae58a. A-D settled with no new implementation gate. Fresh focused tests: 78 passed/2 files. Next: owner reviews sortable preview; deployment is a separate decision. See CODEX-DECISIONS.md. These Codex documentation edits are intentional.


## Owner approval — VC1 deployment, 2026-09-10

The owner visually accepted the sortable preview ('Looks good just like I
imagined'), then authorized proceeding with the proposed merge/push/deployment
('lets go ahead') after confirming historical snapshot capture is for later.

Claude is authorized to merge/push the reviewed VC1 candidate 31ae58a plus
reviewed documentation-only ruling updates and deploy the updated hub in the
next suitable window. Preserve /radar/ as the original page and keep observation
capture off. Include the established fresh backup, temporary service stops,
matching build, restart/smoke verification and code-only rollback if needed.
No capture enablement, root promotion, OT1 cleanup, schema downgrade or live
restore is bundled into this authorization.

Execution must use current facts: production was reported at ba1c381 and already
at migration head a7c31f0b52d4. This update introduces no new migration. Do not
reuse the first release's 'both tables absent' preflight or drop/stamp anything
to recreate it. Verify remote/target drift before merging and deploying, record
the exact merge/deployed SHA, and assess unexpected code/schema changes before
continuing. Retain the existing migration chain for routine upgrades/rollback.

Claude should prepare the concise deployment delta and execute within this
approval without asking for the same approval again. Announce the actual window,
follow the accepted service ordering and backup procedure, then verify old Radar,
hub assets/sorting, current activity_sources and tone on real data, service health,
unchanged migration head and capture off. Do not mint an owner login session;
use existing authorized verification methods. Report any authenticated checks
that need the owner's session honestly. Record results in RELEASE-RECORD.md and
HANDOFF.md. Production has not changed merely because this approval is recorded.

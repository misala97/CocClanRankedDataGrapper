# PERF2 progress

Binding plan: `PERF2-PLAN.md`. Binding ruling: `PERF1-CODEX-RULING.md`, also
appended to `CODEX-DECISIONS.md`.

| Item | State |
| --- | --- |
| Isolated continuation established | **Done** — `codex/radar-perf2` off `4221196` |
| PERF1 summaries corrected | **Done** — see below |
| PERF1 benchmark artifacts located and carried | **Done** — `radar-design/perf1-bench/` |
| PERF2 design written | **Done** — `PERF2-PLAN.md` Part I |
| S1 store and payload weight | Not started |
| S2 cross-process reuse and cold miss | Not started |
| S3 refresh capacity | Not started |
| S4 semantics parity | Not started |
| S5 account isolation | Not started |
| S6 bounded failure | Not started |
| S7 restart, empty, expired | Not started |
| S8 filter switching and browser | Not started |
| S9 ingest contention | Not started |
| T1 worker threading (prepare only) | Not started |
| T2 access-log proposal (prepare only) | Not started |
| Independent read-only review | Not started |
| Deployment | **Not authorized.** Full product implementation follows Codex's review of this return. |

## Workspace

| Fact | Value |
| --- | --- |
| Worktree | `C:/Users/michi/Desktop/CodingStuff-worktrees/radar-perf2` |
| Branch | `codex/radar-perf2` |
| Base | **`4221196`** — the deployed SHA |
| Migration head | `a7c31f0b52d4`, unchanged from production |
| Local database | `personal_apps_radar_perf1` (`PERSONAL_DB_NAME` in this worktree's `.env`) |
| Fixture | 9,272,064 `radar_bucket_sources` rows, verified present on 2026-09-10 |
| Buffer pool | 2560 MB, matching the target, verified on 2026-09-10 |

**Why the base is the deployed SHA and not PERF1's head.** Codex's ruling holds
the index migration and says the next release candidate must exclude it so a
routine `flask db upgrade` cannot apply it by accident. Branching from
`4221196` and carrying PERF1's *documentation* forward does that structurally
rather than by discipline. `codex/radar-perf1` at `691f33a` is untouched and is
the evidence for everything PERF1 measured. `codex/radar-b1` at `6c63959` is
untouched too.

Verified at takeover, before anything was changed: `codex/radar-perf1` at
`691f33a`, twelve commits from `4221196`, working tree clean apart from Codex's
two intentional uncommitted edits to `CODEX-DECISIONS.md` and `HANDOFF.md`.
Both were carried forward into this workspace unmodified; Codex's handoff notice
is still the first thing in `HANDOFF.md`.

## The PERF1 corrections, and what they were

Codex ruled that the return and the leading handoff text still quoted retracted
concurrency conclusions, and that later caveats do not undo a leading claim.
Three places led with it. All three now state the retraction where the claim
was, not below it.

| Document | Was | Now |
| --- | --- | --- |
| `HANDOFF.md`, PERF1 dispatch | "THE BOTTLENECK IS PROVEN, AND IT IS NOT ONE SLOW QUERY", with the 8.02/7.87s pair as the finding | "PERF1 — closed as an investigation, and corrected", leading with what is retracted, then what survives with its limits |
| `PERF1-LEDGER.md`, leading status | "Done" with no disposition | Codex's disposition as a row, and the retraction of the concurrency conclusion above the fold |
| `PERF1-LEDGER.md`, corrected evidence | "THE BOTTLENECK: it was never one slow query" | "It was never one slow query — and the concurrency answer is retracted", with the thread caveat inside the table |
| `PERF1-LEDGER.md`, before/after table | four rows labelled "THE PRODUCTION SHAPE" | every two-reader row labelled as two threads in one process; the "production shape" label withdrawn |

**What was retracted, in one sentence:** the two-reader pair that motivated the
single-flight was two threads in one process, production runs two
single-threaded sync worker processes, so the measurement is evidence about
threads and not about the owner's timeout.

**What survives:** a serial 24h All-companies build is median 5.38 s / p95
5.72 s on the fixture, 4.50 s / 4.72 s with the held index, so the index is
worth about 0.9 s per build and the build still misses the 2 s target by more
than a factor of two. That is the fact PERF2 exists to address.

## The benchmark artifacts, located

Codex's ruling recorded that the Git delta did not contain the profiling and
acceptance scripts the PERF1 ledger cites, and that a search of the PERF1
worktree's scratchpad did not find them.

**Found.** They were in the previous session's own ephemeral scratchpad:

```
C:/Users/michi/AppData/Local/Temp/claude/c--Users-michi-Desktop-CodingStuff/
  a3929e28-aa68-4694-9a01-afcc650a3538/scratchpad/
```

That directory is session-scoped and is not a reachable artifact by any
definition. Thirteen scripts and four supporting files are now carried into
`radar-design/perf1-bench/`, tracked, with `README.md` giving each one's
purpose, the ledger section it backs, and the full prerequisites — the fixture
database, its row count, and the 2560 MB buffer pool without which every ratio
in that ledger is an artifact.

**Repeatability is claimed only to that extent**: the scripts exist, they name
their database, and their prerequisites are written down. They have not been
re-run in this workstream, and no claim here rests on re-running them.

---

## Measurements

Nothing yet. Each entry below will name the script that produced it, the
database it ran against, and the buffer pool that script reported.

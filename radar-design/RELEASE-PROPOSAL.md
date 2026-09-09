# Side-by-side VPS release proposal

Written 2026-09-09 by Claude, for Codex's review. **Nothing here is authorized and
nothing here has been executed.** No merge, no deployment, no target migration, no
capture enablement, no root-route change. The owner runs the deploy; this document
is the plan they and Codex review before that happens.

Counterpart documents: CODEX-DECISIONS.md section C (the release sequence),
FOUNDATIONS-LEDGER.md "R3 evidence" and "P1 rehearsal", HANDOFF.md (workspace state).

---

## 1. What is being released, and what stays

| | before | after this release |
| --- | --- | --- |
| `/radar/` | the current board | same URL, same behaviour; **not** untouched code |
| `/radar/hub/` | 404 | the six-page hub, opt-in |
| database | `personal_apps` on MariaDB | same database, two additive migrations |
| account | the owner's | same account, same session, same watch list |
| ingest | `radar_ingest` | **the same unit**, no second process |
| capture | off (unset) | **still off** |

The two interfaces are side by side on the same live data. Nothing is replaced.

**`/radar/` is not untouched code.** `static/radar/src/api.ts` (403 handling) and
`vite_assets.py` (asset resolution) are shared and did change; the old board's
required behaviour is preserved and is covered by regression checks, but returning
to it is a **UI fallback, not a rollback** of shared services or of the schema.

### Why no duplicate ingestion is possible

The hub adds **three routes** — `/radar/hub/` and the two endpoints it reads,
`/radar/api/activity` and `/radar/api/ops`. Both new endpoints depend on the
migrations, which is exactly why "both migrations" is not a detail. Otherwise it
uses the API the board already uses, and it starts no process, no scheduler and no
worker. The only new scheduled job in this
release, `radar_board_observations`, is registered inside the **existing**
`radar_ingest` daemon (`run_radar_ingest.py:1434`) and returns immediately while
`RADAR_OBSERVATION_CAPTURE_ENABLED` is unset. At startup it logs
`radar board observation capture is disabled (RADAR_OBSERVATION_CAPTURE_ENABLED)`,
so the operator can see it is registered and inert. There is no second daemon to start and none should be started.

### Shared state, stated plainly

Both interfaces read and write the same `radar_watch` rows for the same account. A
mark added in the hub appears on the old board and the reverse. That is intended for
a comparison review — it is the same data — but it means the two views are not
independent, and a watch removed in one is removed in both.

---

## 2. Integration-target drift, as measured

Measured 2026-09-09 against the fetched remotes. **This must be re-measured
immediately before the release**; it is a snapshot, not a standing fact.

| ref | commit | relation to this branch's base (7a9ffe4) |
| --- | --- | --- |
| `origin/main` | 2a83905 | 2 commits ahead, 12 behind |
| `origin/dev_personal` | 38f9c79 | 12 behind; identical tree to `origin/main` |
| local `dev_personal` | 7a9ffe4 | the base the release commits were built on |
| `codex/radar-foundations` | this branch | `git rev-list --count 7a9ffe4..HEAD` |

**`origin/main` and `origin/dev_personal` have the same tree**, object
`1bc8bba29e7751c9bcc25c80d22694e058a7c34a`. The two merge commits on `origin/main`
introduce **no file changes at all**: `git diff 38f9c79 origin/main` is empty. An
earlier version of this section credited them with nineteen changed files. That was
wrong, and it double-counted item 1 below under a second heading.

**One thing needs the owner's decision before a merge:**

1. **Local `dev_personal` has 12 commits that are on neither remote.** Those 12 are
   the entire difference between what this branch was built on and what is published:
   19 files, mostly `scratchpad/label_export/` scripts and their tests, plus
   `personal_apps/scripts/sample_new_shape_mentions.py` and a `docs/superpowers/specs`
   entry. The release target is therefore ambiguous, because `origin/dev_personal` is
   not what this branch was built on, and whoever integrates must decide whether
   those 12 are pushed first or whether the target is the local branch.

**File overlap with this branch: none.** This branch changes 50 files under
`personal_apps/`; the 19 above are disjoint from all of them. A trial merge into
`dev_personal`, `origin/main` and `origin/dev_personal` each produced the same tree
with no conflicts. That was measured rather than predicted, but it was measured
today, and must be repeated at release time.


### Alembic heads — no conflict

| ref | revisions | heads |
| --- | --- | --- |
| `origin/main` | 61 | single: `b3d9e1f5a274` |
| `origin/dev_personal` | 61 | single: `b3d9e1f5a274` |
| this branch | 63 | single: `a7c31f0b52d4` |

The chain is linear: `a7c31f0b52d4` → `d82f9afb5898` → `b3d9e1f5a274`, and
`b3d9e1f5a274` is exactly the head both remotes are at. The two new revisions stack
on the target's current head with nothing to reconcile. **Re-check at release time**
— another branch merging a migration first would change this.

---

## 3. The migrations

**Both are required. Applying only `d82f9afb5898` is not a partial success — it is a
broken deployment**, because the new writer and reader both depend on the projection
columns that `a7c31f0b52d4` adds.

| revision | what it does | reversible |
| --- | --- | --- |
| `d82f9afb5898` | creates `radar_ingest_runs` and `radar_board_observations` | yes, drops exactly those two tables |
| `a7c31f0b52d4` | adds six projection columns to `radar_ingest_runs`, backfills them from `summary_json` | yes, drops exactly those six columns |

Both are additive. Neither alters or removes an existing column, table or row.
`summary_json` is never modified by either.

### Rehearsed on the target engine

**MariaDB 10.11.14** — the version the VPS runs, rather than a MySQL substitute. Portable
server, throwaway datadir, port 3399; `scratchpad/rehearse_mariadb.py`, **39 checks,
all passing**. Full results in FOUNDATIONS-LEDGER.md "P1 rehearsal".

Covered: a clean upgrade over twelve pre-existing rows of every shape; the backfill
reproducing `activity.project` exactly for all twelve; **both** downgrades, including
the one that drops the two tables; interruption after only three of six columns
exist; interruption partway through the backfill; recovery from both; the pre-DDL
domain refusal; and the application's own writer and reader against MariaDB.

**What the rehearsal does not establish**: it ran on a fresh database stamped at
`b3d9e1f5a274`, not on a copy of the target's data. It proves the two revisions behave
correctly on this engine and that the recovery procedures work. It seeds twelve rows
deliberately, which is **more than this deployment will encounter**: the target's table
does not exist yet and will be created empty. Those seeded cases rehearse the second
deployment and every one after it, not the first.

It also ran the mariadb.org binary distribution on a default configuration. The VPS
runs the Ubuntu package `10.11.14-MariaDB-0ubuntu0.24.04.1` with its own
`99-tuning.cnf`: same upstream version, different build and settings.

---


## 4. The runbook lives in RELEASE-RUNBOOK.md

**There is one execution path and it is not here.** An earlier version of this
document carried a runbook with a hand-migration branch beside the project's own
deploy script; Codex ruled that out, because two paths through a migration is how a
schema gets migrated twice.

`RELEASE-RUNBOOK.md` is now the single authoritative procedure: the read-only target
preflight, the deploy script as the sole migration owner, service and timer
inhibition, verification with wall-clock deadlines, durable rollback, and two
distinct failure-recovery procedures for the two migrations.

**All three of its access gates are now closed.** The deploy script and the target
were read over SSH, read-only, with the owner's authorization (TARGET-FACTS.md), and
the nightly backup was restored into a disposable MariaDB and verified
(FOUNDATIONS-LEDGER.md, "P2 backup restore"). Four things the runbook had wrong were
found by doing so, which is what the gates were for.


## 5. What is deliberately not in this release

- **Capture stays off.** `RADAR_OBSERVATION_CAPTURE_ENABLED` and
  `RADAR_PRODUCER_REVISION` are set nowhere. The job is registered and inert.
  Enabling it is Codex's section C step 3, after a healthy deployment.
- **`/radar/` is not promoted or replaced.** Root-route promotion is step 4 and needs
  owner acceptance of the deployed hub first, plus its own rollback and deep-link
  plan.
- **No schema beyond the two migrations.**

---
## 6. Decisions, and what is still open

Four of these were open when this document was first written. Codex has since
ruled on three; they are kept with their rulings so the reasoning is not lost.

1. **The integration target — DECIDED.** Fetched `origin/main`, because the VPS
   deploy script resets to it. The 12 unpublished local commits are neither pushed
   nor merged as a prerequisite: the release candidate transplants only the release
   commits above them. See FOUNDATIONS-LEDGER.md "P2 candidate".
2. **Who deploys, and with what — DECIDED.** `/root/update_coc.sh` is the single
   migration owner, and the release is merged and pushed to `origin/main` first so
   the deploy survives that script's hard reset. Claude is the operator once the
   owner separately authorizes deployment with access.
3. **Backup verification — a hard gate, still unmet.** Not something to accept the
   release without. The disposable MariaDB to restore into already exists; **the
   backup file itself is the only part genuinely missing.** RELEASE-RUNBOOK.md
   section 3.
4. **The migration window — open, and not measurable from here.** `radar_ingest` is
   down for the duration. The backfill itself is trivial: the table is created
   empty, so it projects zero rows and the cost is six `ALTER TABLE`s on an empty
   table. **That is not the downtime.** The build, the service restarts, the locks
   and the verification all contribute, and none has been measured on the target.
5. **Two access gates besides the backup — open.** The deploy script's actual
   contents and the read-only target preflight. RELEASE-RUNBOOK.md sections 1 and 2.

Nothing in this package executes against the VPS, and nothing in it is authorized.

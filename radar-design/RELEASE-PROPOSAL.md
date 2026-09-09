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
| `/radar/` | the current board | **unchanged**, same code, same URL |
| `/radar/hub/` | 404 | the six-page hub, opt-in |
| database | `personal_apps` on MariaDB | same database, two additive migrations |
| account | the owner's | same account, same session, same watch list |
| ingest | `radar_ingest` | **the same unit**, no second process |
| capture | off (unset) | **still off** |

The two interfaces are side by side on the same live data. Nothing is replaced, and
`/radar/` is the rollback for the hub in the strongest sense: it is untouched code
on an untouched route.

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
| local `dev_personal` | 7a9ffe4 | this branch's base |
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


## 4. The runbook

Every step is the owner's to run. Steps marked **GATE** stop the release if they fail.

### 0. Before the window

- [ ] Re-measure drift and Alembic heads (section 2). **GATE** if another migration
      has landed on the target since this document was written.
- [ ] Trial-merge this branch into the chosen target locally. **GATE** on conflict.
- [ ] `npm ci && npm test && npm run build` on the merge result. **GATE** on failure.
- [ ] Confirm the target's engine version: `mariadb -e "select version()"`. The
      rehearsal covers 10.11.14. **GATE** if it differs by a minor version or more.
- [ ] Take and **verify** a database backup. Not "run the backup script" — restore it
      somewhere and confirm `radar_buckets` and `radar_watch` row counts. The
      nightly backup exists; a release is not the moment to discover it does not
      restore.
- [ ] Record, from the target, before anything changes:
      `select version_num from alembic_version;` (expect `b3d9e1f5a274`),
      `show tables like 'radar_ingest_runs';` (expect **empty** — the table does not
      exist yet, and if it does, the target is not in the assumed state: **GATE**),
      and the current deployed git SHA.

### 1. Understand what this migration is actually doing here

**`radar_ingest_runs` does not exist on the target.** It is created by
`d82f9afb5898`, and the currently deployed code declares no `RadarIngestRun` model at
all (`git grep RadarIngestRun 7a9ffe4` is empty). Three consequences, and they change
what this release is:

- **The backfill has nothing to backfill.** `d82f9afb5898` creates the table empty and
  `a7c31f0b52d4` immediately adds columns to it, so the expected output is
  `radar_ingest_runs: projected 0 rows`. Anything else means the target is not in the
  state this document assumes. **GATE.**
- **The pre-DDL domain refusal cannot fire on this deployment.** There are no stored
  counters to be out of domain. It becomes meaningful from the second deployment
  onward, once the daemon has written runs, and that is what the rehearsal covers.
- **Do NOT "preflight" by attempting the upgrade.** An earlier version of this runbook
  said the scan would refuse without touching the schema, so attempting it was safe.
  That is false. The scan lives inside the SECOND revision, so `flask db upgrade` from
  `b3d9e1f5a274` applies `d82f9afb5898` first, creates both tables, and then reaches
  an empty table it cannot refuse, **completing the entire release** outside the
  window with the old web process still serving against a migrated schema. Verified on
  a disposable MariaDB: the full upgrade ran and stamped `a7c31f0b52d4`. There is no
  safe partial dry run. The upgrade is the release.

If the domain refusal ever does fire on a later deployment: **stop**. Preserve the
source values, capture the reported ids and value shapes, and return them to Codex for
a ruling. Codex's section A is explicit that "fix the data" is not permission to
rewrite history automatically.


### 2. Stop the writers, deploy the code

**The project already has a deploy script, `/root/update_coc.sh`, and this runbook does
not replace it.** That script stops `radar_ingest`, does `git reset --hard
origin/main`, runs migrations and restarts. Two hazards follow, and the owner must
choose deliberately:

- A manual `git pull` onto a non-`main` branch is **undone** by the next
  `update_coc.sh`, which hard-resets to `origin/main`. A hand-deploy of this branch is
  silently reverted by the next routine deploy unless it is merged and pushed to
  `origin/main` first.
- If `update_coc.sh` is used, **it runs the migrations itself**. Do not also run them
  by hand. Decide which one does, and check `flask db current` afterwards either way.

The recommended path is therefore: merge to the chosen target, push, run the project's
own script, and use the checks below rather than a parallel procedure.

Whichever is used, the required state before migrating is:

```
systemctl stop radar_ingest                       # the writer -- required
systemctl stop personal_apps_web                  # the reader
# code at the reviewed revision, then:
cd /root/coc-stats/personal_apps && npm ci && npm run build   # dist/ is gitignored
```

`radar_ingest` **must** be down before the migration: it is the writer of
`radar_ingest_runs`, and `ALTER TABLE` on MariaDB auto-commits with no surrounding
transaction. There is no supported window in which the old writer stores envelopes
while the new reader expects projections.


### 3. Migrate

```
cd /root/coc-stats/personal_apps
flask db current                                  # expect b3d9e1f5a274
flask db upgrade                                  # applies BOTH revisions
flask db current                                  # expect a7c31f0b52d4
```

Expected output includes `radar_ingest_runs: projected N rows`.

**GATE** on anything other than a clean finish. Recovery is section 5.

### 4. Start, verify, compare

```
systemctl start personal_apps_web
systemctl start radar_ingest
journalctl -u radar_ingest -n 50
```

Verification, all as the authenticated owner:

- [ ] `/radar/` renders and behaves exactly as before. **This is the one that matters
      most** — the release must not have touched it.
- [ ] `/radar/hub/` renders all six pages.
- [ ] `/radar/api/activity?days=1`, `days=7`, `days=30` all return 200. The month
      view is retained by Codex's ruling and must be checked.
- [ ] Activity shows the runs the daemon is now recording; `counted_runs` is present.
- [ ] `/radar/api/ops` returns 200 for the admin account and 302 signed out.
- [ ] A watch added on `/radar/hub/` appears on `/radar/`, and the reverse.
- [ ] Both interfaces show the same board rows for the same filters — that is the
      side-by-side comparison the owner asked for.
- [ ] `journalctl -u radar_ingest -n 50` contains, verbatim,
      `radar board observation capture is disabled (RADAR_OBSERVATION_CAPTURE_ENABLED)`.
- [ ] **After the first cycle completes**, `/radar/api/activity?days=1` reports a day
      with `completed_runs` >= 1 and `counted_runs` equal to it. This is the check
      that actually proves the projection works: a 200 over an empty table would be
      returned by a completely broken one too.
- [ ] No NEW process. `systemctl list-units 'radar*'` should list exactly what it
      listed before: `radar_ingest`, plus `radar-encoder-trial.timer` and its
      service. **That timer is pre-existing and expected** — it fires against the
      same `personal_apps` database and is no part of this release. Anything else
      is a finding.

### 5. Rollback

**The code**: `git checkout <previous SHA>`, rebuild, restart both units. `/radar/`
returns to exactly what it was; `/radar/hub/` 404s again.

**The schema**: the two tables and the six columns can stay. The rollback target
declares no `RadarIngestRun` model at all — `git grep RadarIngestRun 7a9ffe4` and
`git grep radar_board_observations 7a9ffe4` are both empty — so the old code does
not read them, does not write them, and does not know they exist. Nothing anywhere
issues `SELECT *` against that table. A code-only rollback is therefore complete,
and is the preferred one. Only if the schema itself must go back:

```
flask db downgrade b3d9e1f5a274      # both revisions, rehearsed on MariaDB 10.11.14
```

Both downgrades were exercised on the target engine: `a7c31f0b52d4`'s drops exactly
its six columns and preserves every envelope, and `d82f9afb5898`'s drops exactly
`radar_ingest_runs` and `radar_board_observations` and nothing else, leaving
`b3d9e1f5a274` stamped.

**A failed migration is different from a rollback.** If `flask db upgrade` fails
partway, the revision is unstamped and some columns may exist, because each
`ALTER TABLE` commits on its own. Do not re-run the upgrade blindly — it fails with a
duplicate column. Rehearsed recovery:

1. Verify the database identity, the actual `alembic_version` stamp, and the actual
   column inventory (`show columns from radar_ingest_runs`).
2. Confirm `radar_ingest` and `personal_apps_web` are still stopped.
3. Drop **only** the projection columns confirmed present — not the literal six-column
   statement from the migration docstring, which fails when fewer exist.
4. `flask db upgrade` again.

This was rehearsed from both interruption points on MariaDB 10.11.14 and reproduced
the identical projection with every envelope and every row count preserved. Never
stamp the revision to bypass a failure.

---

## 5. What is deliberately not in this release

- **Capture stays off.** `RADAR_OBSERVATION_CAPTURE_ENABLED` and
  `RADAR_PRODUCER_REVISION` are set nowhere. The job is registered and inert.
  Enabling it is Codex's section C step 3, after a healthy deployment.
- **`/radar/` is not promoted or replaced.** Root-route promotion is step 4 and needs
  owner acceptance of the deployed hub first, plus its own rollback and deep-link
  plan.
- **No schema beyond the two migrations.**

---

## 6. Open decisions, for Codex and the owner

1. **The integration target.** `origin/dev_personal` is 12 commits behind local. Which
   is the target, and are those 12 pushed first?
2. **Backup verification.** A restore rehearsal is listed as a gate. Confirm the
   nightly backup can actually be restored, or accept the release without that.
3. **The migration window is short, and measured rather than hoped.** `radar_ingest`
   is down for the duration. The table is created empty, so the backfill projects
   zero rows on this deployment and the cost is six `ALTER TABLE`s on an empty
   table. A later re-run over accumulated runs is one UPDATE per row and should be
   re-estimated then.
4. **Who deploys, and with what.** `/root/update_coc.sh` hard-resets to
   `origin/main`. Either this is merged and pushed to `origin/main` first, or a
   hand-deploy is reverted by the next routine run of that script.
5. **Who runs it.** Every command here is the owner's. Nothing in this package
   executes against the VPS.

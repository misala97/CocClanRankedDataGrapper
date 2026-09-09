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

The hub adds **one route** (`/hub/`) and reads the same API the board already uses.
It starts no process, no scheduler and no worker. The only new scheduled job in this
release, `radar_board_observations`, is registered inside the **existing**
`radar_ingest` daemon (`run_radar_ingest.py:1434`) and returns immediately while
`RADAR_OBSERVATION_CAPTURE_ENABLED` is unset — it logs
`radar board observation capture is disabled` at startup so the operator can see it
is inert. There is no second daemon to start and none should be started.

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
| `origin/main` | 2a83905 | 2 commits ahead, both `Merge branch 'dev_personal'` |
| `origin/dev_personal` | 38f9c79 | **12 commits behind**; local `dev_personal` is ahead |
| local `dev_personal` | 7a9ffe4 | this branch's base |
| `codex/radar-foundations` | this branch | 33 commits since the base |

**Two things need the owner's decision before a merge:**

1. **Local `dev_personal` has 12 commits that are not on the remote.** The release
   target is therefore ambiguous: `origin/dev_personal` is not what this branch was
   built on. Whoever integrates must decide whether those 12 are pushed first or
   whether the target is the local branch.
2. **`origin/main` carries two merge commits this branch's base does not.** They
   touch only `scratchpad/label_export/` scripts and their tests —
   `sample_new_shape_mentions.py`, `test_hard_negatives.py` and eight siblings.

**File overlap between those commits and this branch: none.** This branch changes 49
files under `personal_apps/`; the drift touches ten, and the two sets are disjoint. A
merge is expected to be conflict-free, but that is a prediction from file names and
must be confirmed by an actual trial merge at release time, not assumed from here.

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

**MariaDB 10.11.14** — the version the VPS runs, not a MySQL substitute. Portable
server, throwaway datadir, port 3399; `scratchpad/rehearse_mariadb.py`, **34 checks,
all passing**. Full results in FOUNDATIONS-LEDGER.md "P1 rehearsal".

Covered: a clean upgrade over twelve pre-existing rows of every shape; the backfill
reproducing `activity.project` exactly for all twelve; downgrade and re-upgrade;
interruption after only three of six columns exist; interruption partway through the
backfill; recovery from both; the pre-DDL domain refusal; and the application's own
writer and reader against MariaDB.

**What the rehearsal does not establish**: it ran on a fresh database stamped at
`b3d9e1f5a274`, not on a copy of the target's data. It proves the two revisions
behave correctly on this engine; it does not prove the target's existing rows are
free of surprises. That is what step 3 of the runbook is for.

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
      somewhere and confirm `radar_ingest_runs` and `radar_buckets` row counts. The
      nightly backup exists; a release is not the moment to discover it does not
      restore.
- [ ] Record, from the target, before anything changes:
      `select count(*) from radar_ingest_runs;`,
      `select version_num from alembic_version;`,
      and the current deployed git SHA.

### 1. Preflight the data — with writers stopped

```
systemctl stop radar_ingest
systemctl show radar_ingest -p ActiveState        # must read inactive
```

The domain scan inside `a7c31f0b52d4` runs before any DDL and refuses the upgrade if
any stored counter is outside the accepted domain. To learn that **before** the
window rather than during it, run the upgrade's own scan by attempting the upgrade
(see step 3) — it will refuse without touching the schema, which is safe.

If it refuses: **stop**. Preserve the source values, capture the reported ids and
value shapes, and return them to Codex for a ruling. Codex's section A is explicit
that "fix the data" is not permission to rewrite history automatically.

### 2. Stop the writers, deploy the code

```
systemctl stop radar_ingest
systemctl stop personal_apps_web
cd /root/coc-stats && git pull                    # the reviewed revision
cd personal_apps && npm ci && npm run build       # dist/ is gitignored
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
journalctl -u radar_ingest -n 50                  # expect the capture-disabled line
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
- [ ] `journalctl -u radar_ingest` shows cycles completing and closing runs.
- [ ] No new process: `systemctl list-units 'radar*'` shows only the existing units.

### 5. Rollback

**The code**: `git checkout <previous SHA>`, rebuild, restart both units. `/radar/`
returns to exactly what it was; `/radar/hub/` 404s again.

**The schema**: the projection columns and the two tables can stay. They are additive
and the old code neither reads nor writes them, so a code-only rollback is complete
and is the preferred one. Only if the schema itself must go back:

```
flask db downgrade b3d9e1f5a274      # verified as an exact inverse, both revisions
```

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
3. **The migration window.** `radar_ingest` is down for the duration. The backfill is
   one UPDATE per row; on a target with no `radar_ingest_runs` rows yet it is
   instant, but the row count should be checked first (step 0) rather than assumed.
4. **Who runs it.** Every command here is the owner's. Nothing in this package
   executes against the VPS.

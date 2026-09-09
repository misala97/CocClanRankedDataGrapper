# Release runbook — the single execution path

Written 2026-09-09 by Claude for Codex's review, per CODEX-DECISIONS.md "Fourth
return", section B. **Nothing here is authorized and nothing here has been
executed.** This is the one authoritative path; RELEASE-PROPOSAL.md describes the
architecture and the drift, and does not contain a second procedure.

**Three steps below are marked GATE — PENDING ACCESS.** They cannot be written as
executable commands from this workspace, and the release cannot proceed past them.
What is needed to close each is stated exactly, in section 6.

---

## 0. What this release is

Candidate branch **`codex/radar-release-candidate`**, HEAD recorded in section 7,
branched from fetched `origin/main` (2a83905) with the 38 release commits
transplanted and the 12 unpublished research commits excluded.

`/radar/` keeps serving the existing board. `/radar/hub/` becomes available,
opt-in, on the same database, session, watching list and the single existing
ingest daemon. Capture stays off. Root-route promotion is a separate decision.

**Do not describe the old board as untouched code.** `static/radar/src/api.ts`
(403 handling) and `vite_assets.py` (asset resolution) are shared and did change.
Their required behaviour is preserved and is covered by the regression checks in
step 5; returning to the old page is a UI fallback, not a rollback of shared
services or of the schema.

---

## 1. GATE — PENDING ACCESS: read the deploy script before using it

`/root/update_coc.sh` is the intended **single owner of the migration**. This
runbook must not contain a second, manual migration path, and does not.

**It cannot be finalised until the script's actual contents are read.** A report
of what it does is not evidence. Required before the window:

- [ ] The full text of `/root/update_coc.sh`.
- [ ] `systemctl cat personal_apps_web radar_ingest radar-encoder-trial.service
      radar-encoder-trial.timer` — for `WorkingDirectory`, `ExecStart`, `User`,
      `Environment`/`EnvironmentFile`.

What must be confirmed in that text, each of which changes the procedure if absent:

| # | requirement | if absent |
| --- | --- | --- |
| 1.1 | it stops **`personal_apps_web`**, not only `radar_ingest` | propose a minimal wrapper change for review; do not edit in place during a release |
| 1.2 | it **exits without restarting** when the migration or build fails | same |
| 1.3 | it runs `flask db upgrade` exactly **once**, with the right interpreter and `WorkingDirectory` | same |
| 1.4 | it resets to `origin/main` — the reason the candidate must be merged there first | see step 4 |
| 1.5 | it builds the frontend (`npm ci && npm run build`) with the expected Node | if it does not, the build step must be added, not run alongside |

**Until 1.1 and 1.2 are confirmed, the release does not start.** A script that
restarts services after a failed migration would bring the web process up against
a half-migrated schema, which is the exact failure this sequencing exists to
prevent.

---

## 2. GATE — PENDING ACCESS: read-only target preflight

Every item is a read. Nothing here writes, and **`flask db upgrade` is never a
preflight** — it performs the schema mutation. Do not run `rehearse_mariadb.py` or
`rehearse_first_migration.py` against anything but a throwaway server; both drop
their schema.

```sql
select version(), @@version_comment;
select @@sql_mode, @@transaction_isolation, @@character_set_server,
       @@collation_server, @@lower_case_table_names, @@max_allowed_packet;
select database();
select version_num from alembic_version;
show tables like 'radar\_ingest\_runs';
show tables like 'radar\_board\_observations';
select count(*) from radar_watch;
select count(*) from radar_buckets;
```

Expected, and each mismatch is a stop-and-diagnose:

| check | expected | if different |
| --- | --- | --- |
| `alembic_version` | `b3d9e1f5a274` | **STOP.** Do not stamp, do not replay. Reconcile the chain first. |
| both radar tables | **absent** | **STOP.** Never drop them to make the assumption true; diagnose what created them. |
| engine version | 10.11.14 | assess **any** difference, not only a minor one; the rehearsal used the mariadb.org build on a default config, the target is `10.11.14-MariaDB-0ubuntu0.24.04.1` with `99-tuning.cnf` |
| `sql_mode`, isolation, charset | compare with the rehearsal's `STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_AUTO_CREATE_USER,NO_ENGINE_SUBSTITUTION` | a difference is an assessment, not automatically a stop |

A stamp is evidence of migration state, **not proof that every underlying table
matches it**. If the stamp says `b3d9e1f5a274` but the schema looks unexpected,
that is a diagnosis, not something to migrate over.

Also record, before anything changes:

- [ ] The **currently deployed SHA** on the target (`git -C /root/coc-stats rev-parse HEAD`).
- [ ] The **approved candidate SHA** (section 7) and the **current `origin/main` SHA**.
      **Abort on drift** between what was approved and what is about to deploy.
- [ ] The configured capture flag as the service actually sees it — from the unit's
      `Environment`/`EnvironmentFile`, not from its absence in this worktree.
      **`RADAR_OBSERVATION_CAPTURE_ENABLED` must be false or unset on the target.**

---

## 3. GATE — PENDING ACCESS: backup restore is a hard gate

Not "restore or accept without". The release does not proceed until a backup has
been restored and verified.

**Required, and none of it is available from this workspace:**

- [ ] A **consistent** backup of `personal_apps`, with its **timestamp, the engine
      version that produced it, a checksum, and its scope** (which schemas, whether
      routines/triggers are included) recorded.
- [ ] An **isolated disposable MariaDB** to restore into. Not the live server.
- [ ] The restore commands as actually used, and the storage location and
      permissions of the backup.

Verification, **all from the same snapshot** — comparing an old backup's counts to
a still-changing live database is not a valid check:

```sql
-- in the restored copy only
select count(*) from information_schema.tables where table_schema = database();
select count(*) from radar_watch;
select count(*) from radar_buckets;
select count(*) from app_user;
select version_num from alembic_version;
-- representative rows, not just counts
select * from radar_watch order by id limit 5;
```

- [ ] Table inventory and schema match the snapshot's own expectations.
- [ ] Representative Radar, account and watch rows are present and readable.
- [ ] The achievable **data-loss window** is documented: backup cadence versus the
      restore point.

**Never run either rehearsal harness against the restored copy.** They drop their
schema. Restoring is a read-and-verify exercise.

No live restore and no production write is authorized.

---

## 4. The execution path

Numbered, single-path, and every step has an owner and a stop condition. Claude is
the operator once the owner separately authorizes deployment with access; until
then this is a document.

### 4.1 Reconcile the target (before the window)

1. Fetch and confirm `origin/main` has not moved from the SHA the candidate was
   built on. **A newly changed migration head is a stop-and-reconcile gate**, not a
   permanent rejection: update the candidate's chain, re-run section 5, resume.
2. Merge the candidate into `main` and push. **This is what makes the deploy
   durable** — `update_coc.sh` resets to `origin/main`, so a hand-deploy of the
   candidate branch would be silently reverted by the next routine run.
3. Record the merged SHA. That is the approved deployed SHA from here on.

### 4.2 Inhibit competing writers

4. Inventory what is **actually running**, not merely loaded — units *and* timers,
   because a timer can start a job that undoes a stopped service:

```
systemctl list-units --type=service --state=running 'radar*' 'personal_apps*' 'coc*'
systemctl list-timers --all
systemctl is-enabled radar_ingest personal_apps_web radar-encoder-trial.timer
ps -eo pid,etime,cmd | grep -E 'radar|gunicorn' | grep -v grep
```

5. **Record the prior enabled/running state of every unit touched.** Only
   previously enabled/running services are restarted afterwards.
6. Stop and inhibit for the window: `radar_ingest`, `personal_apps_web`, and
   **`radar-encoder-trial.timer`**. That timer is pre-existing and *not* part of
   this release, but it fires against the same `personal_apps` database — its
   pre-existence does not make it irrelevant. Determine from its unit file whether
   it can write to any affected table; if it can, mask it for the window
   (`systemctl mask`) so the timer cannot restart it, and unmask afterwards.
7. Confirm **one and only one** ingest process is gone, by process list, not by
   unit state alone.

### 4.3 Deploy and migrate — one owner

8. Run `/root/update_coc.sh`. **It performs the checkout, the build and the
   migration.** Do not run `flask db upgrade` by hand before or after; that would
   be the double migration this runbook exists to remove.
9. **Stop conditions**, any of which ends the release and moves to section 5:
   - the script exits non-zero;
   - the migration output is not `radar_ingest_runs: projected 0 rows`;
   - the build fails.

### 4.4 Confirm the schema before anything serves

10. Read-only, after the script and before starting the web process:

```sql
select version_num from alembic_version;          -- expect a7c31f0b52d4
show columns from radar_ingest_runs;              -- expect the six projection columns
show tables like 'radar\_board\_observations';    -- expect present
```

11. **Stop** on anything unexpected. Do not start services against a schema that
    does not match.

### 4.5 Start, in order

12. Start `personal_apps_web`, then `radar_ingest`, then unmask/restore
    `radar-encoder-trial.timer` **only if it was enabled before**.
13. `journalctl -u radar_ingest -n 50` must contain, verbatim:
    `radar board observation capture is disabled (RADAR_OBSERVATION_CAPTURE_ENABLED)`

---

## 5. Verification, with deadlines

Wall-clock deadlines come from the scheduler's own configuration
(`run_radar_ingest.py`): the session cycle is registered with
`next_run_time=now`, the reddit job at `now + 30s`, board observations at the next
quarter-hour, sentiment at `now + 4 minutes`. **An operator should never be left
waiting indefinitely or restarting a healthy slow job.**

| # | check | deadline |
| --- | --- | --- |
| 5.1 | a run row exists: `select count(*), max(status) from radar_ingest_runs` | **5 min** after start |
| 5.2 | the first completed run has BOTH a `summary_json` envelope and matching projection columns, and `counted_runs` on the day equals the completed count | **10 min** |
| 5.3 | `/radar/api/activity?days=1`, `days=7`, `days=30` all 200 | immediate |
| 5.4 | `/radar/api/ops` — **200 admin, 403 non-admin, 302 signed out** | immediate |
| 5.5 | capture still off: no rows in `radar_board_observations` after two quarter-hour boundaries | **35 min** |

If 5.1 misses its deadline, read `journalctl -u radar_ingest` before restarting
anything — a restart loses the evidence and does not fix a configuration fault.

### Side-by-side comparison, which is the point of this release

5.6 Authenticated, same account, both interfaces:

- Open `/radar/` and `/radar/hub/#chatter` with **equivalent filters**.
- Compare against **aligned `generated_at`**. The board is memoised for a minute
  and a live refresh may legitimately differ; a difference is only a finding when
  the two payloads claim the same generation instant.
- Any watch added to compare behaviour must be **removed afterwards**. Watching is
  shared: a mark made in one interface exists in the other and belongs to the
  owner's real list.

### Shared-surface smoke, because the helpers are shared

5.7 `api.ts` and `vite_assets.py` are used beyond the hub:

- `/radar/` renders and its filters work.
- A **gym** page renders with its styles — `vite_asset` resolution is the shared
  helper that changed.
- Any page that 403s or 302s still shows the right message rather than a blank.

---

## 6. Rollback, and it must survive the hard reset

`update_coc.sh` resets to `origin/main`. **A detached `git checkout` on the target
is not a durable rollback** — the next routine deploy undoes it.

### 6.1 Preferred: code-only, reverted on main

1. Stop `personal_apps_web` and `radar_ingest`.
2. `git revert` the release merge on `main`, push.
3. Run `update_coc.sh`, which now deploys the reverted state and rebuilds assets.
4. Verify the deployed SHA is the reverted one — check it, do not assume.
5. Start the previously running services.

**Leave the schema in place.** Both tables and all six columns are additive, and
the rollback target declares no `RadarIngestRun` model at all
(`git grep RadarIngestRun 7a9ffe4` is empty), so the old code does not read them,
write them, or know they exist. Nothing anywhere issues `SELECT *` on them.

### 6.2 Emergency: pinned artifact, routine deploy inhibited

If main cannot be reconciled immediately: check out the previous SHA on the target
**and inhibit `update_coc.sh` from running** until main is reconciled — otherwise
the next routine deploy silently re-applies the release. Rebuild assets to match
the pinned SHA; a rolled-back checkout with the new `dist/` is a different bug.

### 6.3 Schema downgrade — separately authorized only

Order matters and is easy to get wrong:

1. Stop the workers.
2. Run `flask db downgrade b3d9e1f5a274` **while the new migration files and
   runtime are still present** — the downgrade code lives in those files, so
   checking out code that lacks them first makes the downgrade impossible.
3. Only then check out the older code.

**If any runs have been recorded, dropping the tables loses them.** That is not
harmless: back them up and obtain explicit data-loss approval first. Both
downgrades were rehearsed on MariaDB 10.11.14 and drop exactly what they created.

---

## 7. Failure recovery — two different failures, two procedures

The distinction is load-bearing. **Do not apply one recipe to both**, and never
use a blanket `DROP TABLE` or stamp a revision to skip work.

Establish first, by inspection:

```sql
select version_num from alembic_version;
show tables like 'radar\_%';
select count(*) from radar_ingest_runs;   -- only if it exists
```

### 7.1 Stamp `b3d9e1f5a274`, radar tables partly present — the FIRST migration died

`d82f9afb5898` issues four DDL statements, each auto-committing. A kill between
any two leaves the revision unstamped with part of the list applied.

Recovery, rehearsed: **drop only the new tables that are actually present, and
only when they hold no rows**, then re-run the upgrade. A blind re-run fails with
"already exists" and must not be forced.

**If a partial table holds records, stop.** A first deployment cannot have produced
one — the deployed code has no model — so a row means the assumption behind this
procedure is wrong. Back it up and diagnose; do not drop it.

Rehearsed by `scratchpad/rehearse_first_migration.py` on MariaDB 10.11.14:
**25 checks**, covering interruption after each of statements 1, 2 and 3, the
rebuilt schema being byte-identical to a clean run, the refusal to drop a
populated table, and the refusal to apply this procedure when the stamp shows the
first migration completed.

### 7.2 Stamp `d82f9afb5898`, some projection columns present — the SECOND died

Recovery: drop **only the projection columns confirmed present** — not the literal
six-column statement, which fails when fewer exist — then re-run the upgrade.

Rehearsed by `scratchpad/rehearse_mariadb.py`: **39 checks**, covering both
interruption points, both downgrades, the pre-DDL refusal, and the application's
own writer and reader on that engine.

---

## 8. The approved candidate

| | |
| --- | --- |
| candidate branch | `codex/radar-release-candidate` |
| branched from | `origin/main` 2a83905 |
| commits transplanted | 38, chronological, from `7a9ffe4..codex/radar-foundations` |
| commits excluded | 12 unpublished research commits below the base |
| candidate SHA | recorded in FOUNDATIONS-LEDGER.md "P2 candidate"; verify with `git rev-parse HEAD` |

Evidence that the transplant is clean, and that a clean transplant is not by
itself dependency safety, is in FOUNDATIONS-LEDGER.md "P2 candidate".

# Release runbook — the single execution path

Written 2026-09-09 by Claude for Codex's review, per CODEX-DECISIONS.md "Fourth
return", section B. **Nothing here is authorized and nothing here has been
executed.** This is the one authoritative path; RELEASE-PROPOSAL.md describes the
architecture and the drift, and does not contain a second procedure.

**Gates 1 and 2 are CLOSED.** The deploy script and the target were read over SSH,
read-only, with the owner's authorization; the facts are in **TARGET-FACTS.md** and
four of them changed this document. Gate 3, the backup restore, is recorded in
FOUNDATIONS-LEDGER.md.

**One requirement is unmet and is not a formality: `update_coc.sh` does not stop
`personal_apps_web`.** Section 1 says what that does and does not mean for this
release.

---

## 0. What this release is

Candidate branch **`codex/radar-release-candidate`**, HEAD recorded in section 8,
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

## 1. The deploy script — read, and one requirement is unmet

`/root/update_coc.sh` is the **single owner of the migration**. Its full text and
the unit definitions are in TARGET-FACTS.md section 1. Verdict:

| # | requirement | verdict |
| --- | --- | --- |
| 1.1 | stops **`personal_apps_web`** | **NO** — never stopped, only restarted at the end |
| 1.2 | exits without restarting on failure | **YES** — `set -e` aborts before the restart block |
| 1.3 | runs `flask db upgrade` once, right interpreter and directory | **YES**, inside the venv |
| 1.4 | resets to `origin/main` | **YES** |
| 1.5 | builds the frontend | **YES**, `npm ci && npm run build` |

### What 1.1 being unmet means here, and what it does not

The web process serves throughout the migration. **For this release that is not
dangerous**, for a specific reason rather than a general one: the deployed code
declares no `RadarIngestRun` or `RadarBoardObservation` model, and this migration
only creates those two tables and alters one of them. A process cannot touch what
it has no model for, and `radar_ingest` — the actual writer — *is* stopped.

**No wrapper change is proposed for this release**, on that basis. Codex's ruling
allows proposing one; the honest position is that it is not needed here and would
be a production edit made during a release for no benefit.

**It will matter for a later migration.** Any future revision that alters a table
the web app reads must not use this script unmodified. Record that decision here
rather than rediscovering it.

One smaller window to know about: between `git reset --hard` and the restart, the
running gunicorn holds **old Python in memory** while **new files sit on disk**.
Templates are read per request, so a page can render a new template against old
code for the length of the pip install, two migrations, `npm ci` and the build —
minutes. Neither interface breaks on that in practice; it is why 1.1 exists.

---

## 2. Target preflight — run, and the results are recorded

Every item is a read. Nothing here writes, and **`flask db upgrade` is never a
preflight** — it performs the schema mutation. Do not run `rehearse_mariadb.py` or
`rehearse_first_migration.py` against anything but a throwaway server; both drop
their schema.

**Note the variable name.** An earlier version of this block asked for
`@@transaction_isolation`, which does not exist on MariaDB 10.11 and fails with
`ERROR 1193 Unknown system variable`. MariaDB spells it `@@tx_isolation`. That was
a MySQL-ism carried in from the development environment, and finding it is exactly
what this gate is for.

```sql
select version(), @@version_comment;
select @@sql_mode, @@tx_isolation, @@character_set_server,
       @@collation_server, @@lower_case_table_names, @@max_allowed_packet;
select database();
select version_num from alembic_version;
show tables like 'radar\_ingest\_runs';
show tables like 'radar\_board\_observations';
select count(*) from radar_watch;
select count(*) from radar_buckets;
```

**Results as of 2026-09-09 are in TARGET-FACTS.md section 2, and every expectation
below was confirmed.** Re-run them immediately before the window: they are a
snapshot, not a standing fact.

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
      As of 2026-09-09 this is `b7d8adf`, **one commit behind `origin/main`**
      (`2a83905`). Running the deploy therefore ships that commit too. It is a
      merge that changes no files relative to the deployed tree, so the effect is
      nil — but compare against the DEPLOYED SHA, not only against `origin/main`,
      or the drift check misses whatever else has accumulated.
- [ ] The **approved candidate SHA** (section 8) and the **current `origin/main` SHA**.
      **Abort on drift** between what was approved and what is about to deploy.
- [ ] The configured capture flag as the service actually sees it — from the unit's
      `Environment`/`EnvironmentFile`, not from its absence in this worktree.
      **`RADAR_OBSERVATION_CAPTURE_ENABLED` must be false or unset on the target.**

---

## 3. Backup restore — the hard gate, closed

Not "restore or accept without". **Done on 2026-09-09**: `db_2026-09-09_0315`,
SHA-256 verified against the source, restored into the disposable MariaDB and
checked from within that one snapshot. Full evidence in FOUNDATIONS-LEDGER.md,
"P2 backup restore".

The achievable **data-loss window is just under 24 hours** — backups run once
daily at 03:15. Acceptable for this release, which adds two empty tables and
changes nothing existing; weigh it again before any migration that alters existing
data.

Re-verify before the window if the release is far from this date. What that needs:

- [ ] A **consistent** backup of `personal_apps`, with its **timestamp, the engine
      version that produced it, a checksum, and its scope** (which schemas, whether
      routines/triggers are included) recorded.
- [ ] An isolated disposable MariaDB to restore into — the portable 10.11.14 used
      for P1 and P2, started from the instructions in FOUNDATIONS-LEDGER.md.
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

No live restore and no production write was performed or is authorized. Restoring
recreates **both** databases: a partial restore of `personal_apps` alone means
extracting it from the file, not running the file as-is.

---

## 4. The execution path

Numbered and single-path. Claude is the operator once the owner separately
authorizes deployment with access; until then this is a document, and every step
below is Claude's to run under that authorization.

Steps that can end the release carry an explicit stop condition. The rest are
observations and preparation, and their failure mode is that a later step's stop
condition fires — which is the point of ordering them this way.

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
crontab -l                     # NOT optional -- see below
systemctl is-enabled radar_ingest personal_apps_web radar-encoder-trial.timer
ps -eo pid,etime,cmd | grep -E 'radar|gunicorn' | grep -v grep
```

**`crontab -l` is there because `list-timers` does not show the database backup.**
The nightly `mysqldump` is a cron job at **03:15**, not a systemd timer. A window
overlapping it would run a dump of the database being migrated. An earlier version
of this step listed only timers and would have missed it entirely.

5. **Record the prior enabled/running state of every unit touched.** Only
   previously enabled/running services are restarted afterwards.
6. Stop and inhibit for the window: `radar_ingest`, `personal_apps_web`, and
   **`radar-encoder-trial.timer`**.

   **That timer is a confirmed database writer and it fires every minute.** Its
   own unit file says it "persists `recovering` and drains a bounded slice of the
   recovery" and "needs the database and nothing else"; observed cadence is one
   run per minute. `update_coc.sh` does **not** stop it. `systemctl stop` alone is
   not enough — the timer restarts the service — so **mask** it for the window and
   unmask afterwards. Its pre-existence is exactly why it was nearly missed.

   **The named three are a floor, not the list.** Step 4's `list-timers --all` is
   there to be read: for every timer it surfaces, decide whether it can touch
   `personal_apps` or compete for the database, and inhibit it if it can. The
   host's nightly database-backup timer is the obvious one — a dump starting
   mid-migration is a slow, confusing failure. Record each decision, because step
   12 restores only what was previously enabled.
7. Confirm **no ingest process remains**, by process list rather than unit
   state alone — a stopped unit and a surviving process are different facts,
   and only the second one corrupts a migration.

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
(`run_radar_ingest.py:1353, 1359, 1437, 1448`): the session cycle is registered
with `next_run_time=now`, the reddit job at `now + 30s`, board observations at the
next quarter-hour, sentiment at `now + 4 minutes`. The cycle then reschedules
itself on the NYSE session, floor `CYCLE_SECONDS = 180`
(`features/radar/config.py`). **An operator should never be left waiting
indefinitely or restarting a healthy slow job.**

The 5- and 10-minute figures below allow the first cycle to start immediately and
take up to a few minutes; the 35-minute one is two quarter-hour boundaries and is
exact.

| # | check | deadline |
| --- | --- | --- |
| 5.1 | a run row exists: `select count(*) from radar_ingest_runs` and `select status, count(*) from radar_ingest_runs group by status` | **5 min** after start |
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

### 6.1 Preferred: code-only, reverted on main — **keeping the migration files**

**The revert must NOT remove `personal_apps/migrations/versions/`.** This is the
one part of the rollback that is easy to get wrong and fails loudly when you do.

`alembic_version` still holds `a7c31f0b52d4` after the release. `update_coc.sh`
runs `flask db upgrade`. If the revert removed the two migration files, that
upgrade cannot resolve the stamped revision and dies:

```
CommandError: Can't locate revision identified by 'a7c31f0b52d4'
```

Reproduced on the disposable MariaDB. Combined with requirement 1.2 — the script
exits without restarting on a migration failure — a naive full revert leaves the
site **down**, which is a worse outcome than the fault being rolled back.

1. Stop `personal_apps_web` and `radar_ingest`.
2. Revert the release merge on `main` **except** the two migration files:

```
git revert -n -m 1 <release merge sha>
git checkout <release merge sha> -- personal_apps/migrations/versions/d82f9afb5898_add_radar_observations.py
git checkout <release merge sha> -- personal_apps/migrations/versions/a7c31f0b52d4_add_radar_run_counter_projection.py
git commit
git push
```

3. Run `update_coc.sh`. `flask db upgrade` is now a **no-op** — the database is
   already at `a7c31f0b52d4` and the files that define it are present.
4. Verify the deployed SHA is the reverted one. Check it; do not assume.
5. Start the previously running services.

**Leave the schema in place.** Both tables and all six columns are additive, and
the rollback target declares no `RadarIngestRun` model
(`git grep RadarIngestRun 7a9ffe4` is empty), so the application does not read
them, write them, or know they exist, and nothing issues `SELECT *` on them.
**Alembic is the exception**: it does know, through `alembic_version`, which is
why the files stay even though the code that uses them does not.

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

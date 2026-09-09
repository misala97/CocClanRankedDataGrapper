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
section 5; returning to the old page is a UI fallback, not a rollback of shared
services or of the schema.

---

## 1. The deploy script — read, and one requirement is unmet

`/root/update_coc.sh` is the **single owner of the migration**. Its full text and
the unit definitions are in TARGET-FACTS.md section 1. Verdict:

| # | requirement | verdict |
| --- | --- | --- |
| 1.1 | stops **`personal_apps_web`** | **NO** — never stopped, only restarted at the end |
| 1.2 | exits without restarting on failure | **PARTLY** — `set -e` aborts, but the restarts are the script's own last statements, so a tail failure exits non-zero *after* some of them. See 4.3. |
| 1.3 | runs `flask db upgrade` once, right interpreter and directory | **YES**, inside the venv |
| 1.4 | resets to `origin/main` | **YES** |
| 1.5 | builds the frontend | **YES**, `npm ci && npm run build` |

### 1.1 is unmet, and Codex overruled my judgement about it

I argued the web process could keep serving, because the deployed code declares
no model for either new table. **Codex overruled that, and was right to.** "No
model means it cannot touch it" is a narrow schema argument that does not address
what else changes underneath a running worker: templates, static assets and
Python dependencies all move when the checkout does, and I had no mixed-version
test to support "neither interface breaks in practice".

**The ruling: stop `personal_apps_web` BEFORE the checkout and build.** And
because `update_coc.sh` updates the shared checkout and restarts `coc_web` too,
**stop `coc_web` as well** for the window.

**This is a real, recorded outage, and it is short.** Both web applications are
down from step 4.2 until the script's own restarts inside step 10 of 4.3 — a pip
install, two migrations, `npm ci` and a Vite build.

**Measured: 24-27 seconds.** Five real `update_coc.sh` runs on 2026-09-08,
bracketed by `radar_ingest` stopped → started in the journal: 26 s, 24 s, 24 s,
26 s, 27 s. An earlier version of this runbook said "minutes, not seconds", which
was a guess and was wrong in the cautious direction.

Budget ~60 seconds rather than 30: this release's frontend build includes the new
hub entry, and its migration does real DDL where those runs had none. Add the
manual stop and restart either side. That is the cost of the ruling, and it is a
number rather than an adjective.

**No permanent edit to `/root/update_coc.sh` is required.** The stops are
orchestrated around the existing script, which is the single migration owner and
stays unmodified.


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

**A fresh backup is required before the window**, not merely a re-verification of
this one. Codex's ruling: the restored snapshot proves that snapshot is
recoverable, and does not authorize deploying against a nearly-24-hour-old one.
Take one through the same verified mechanism, record its checksum and timestamp,
and confirm `gzip -t` — the full restore rehearsal does **not** need repeating,
because the mechanism is the one already proven here. What that needs:

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
authorizes deployment with access; until then this is a document.

**The one thing to understand before reading it.** `update_coc.sh` restarts
`coc_web` and `personal_apps_web` **itself**, at the end, after a successful
build and migration. So there is no window in which the schema can be checked
while services are still down — an earlier version of this runbook promised one
and it was a false promise. **All schema and API checks below are POST-restart
verification.** What protects the migration is that the units are stopped
*before* the script runs, not that anything is inspected between its steps.

The script carries `set -e`, so a non-zero exit means it stopped **somewhere** —
not necessarily before its restarts. Its last three statements are
`systemctl restart coc_web`, `systemctl restart personal_apps_web` and
`systemctl start coc_scheduler personal_apps_gym_notifier radar_ingest`, followed
by a `cp`/`chmod`. A failure in any of those exits non-zero with the migrations
**complete** and one or both web applications **already serving the new code
against the new schema**.

So the first question on a non-zero exit is never "which migration was in flight"
— it is **where did it stop**. Establish that before choosing anything:

```
systemctl is-active coc_web personal_apps_web radar_ingest \
                    coc_scheduler personal_apps_gym_notifier
cd /root/coc-stats/personal_apps && flask db current
```

- **Migrations complete and services up** → the failure was in the tail. The
  release is effectively deployed; verify (section 5) and decide, and use
  section 6 if it must come out.
- **Migrations incomplete** → section 7, which identifies which of the two was in
  flight and recovers it. Do not start services by hand into an unknown schema.

### 4.1 Reconcile the target (before the window)

1. Fetch and confirm `origin/main` has not moved from the SHA the candidate was
   built on. **A newly changed migration head is a stop-and-reconcile gate**, not
   a permanent rejection: update the candidate's chain, re-run the checks in
   FOUNDATIONS-LEDGER.md "P2 candidate", resume.
2. Merge the candidate into `main` **with `--no-ff`** and push. The explicit
   merge commit is not cosmetic: section 6.1's rollback is `git revert -m 1`,
   which needs a merge parent to reference. A fast-forward leaves nothing to
   revert as a unit.
3. Record the merged SHA. That is the approved deployed SHA from here on.
4. **Choose a window that does not overlap 03:15**, when the backup cron runs.
   Do not disable the backup to make room; move the window.

### 4.2 Stop everything that writes, and the two web units

5. Inventory what is **actually running**, not merely loaded — units *and*
   timers *and* cron, because each can start work the others do not show:

```
systemctl list-units --type=service --state=running 'radar*' 'personal_apps*' 'coc*'
systemctl list-timers --all
crontab -l                     # the backup lives here, not in list-timers
systemctl is-enabled personal_apps_web coc_web radar_ingest coc_scheduler \
                    personal_apps_gym_notifier radar-encoder-trial.timer
systemctl is-active  personal_apps_web coc_web radar_ingest coc_scheduler \
                    personal_apps_gym_notifier radar-encoder-trial.service
systemctl list-timers radar-encoder-trial.timer   # its ACTIVE state, which is-active
                                                  # does not report for a timer
ps -eo pid,etime,cmd | grep -E 'radar|gunicorn' | grep -v grep
```

6. **Record the prior enabled/active/masked state of every unit touched.** Only
   what was previously enabled and running is restored afterwards, and it is
   restored to its *original* state — not to whatever seems reasonable at 2am.

   **Compare that inventory against what the script unconditionally restarts**:
   `coc_web`, `personal_apps_web`, `coc_scheduler`,
   `personal_apps_gym_notifier`, `radar_ingest`. As of 2026-09-09 all five are
   enabled and running, so the script's assumption holds. **If any is masked,
   disabled or deliberately stopped, stop and revise before executing** — the
   script would start something the owner had turned off.

7. Stop, in this order:

```
systemctl stop personal_apps_web        # OUTAGE BEGINS
systemctl stop coc_web                  # shared checkout; the script restarts it
systemctl stop radar_ingest
systemctl stop radar-encoder-trial.timer
systemctl stop radar-encoder-trial.service   # a timer stop does NOT kill a running invocation
systemctl mask radar-encoder-trial.timer     # nothing may re-arm it during the window
```

   **`radar-encoder-trial` needs both.** The timer fires every minute and the
   service writes to `personal_apps`; stopping only the timer leaves whatever is
   already running to finish against a migrating schema.

8. **Do not mask `coc_web`, `personal_apps_web`, `coc_scheduler`,
   `personal_apps_gym_notifier` or `radar_ingest`** — the script must be able to
   restart them, and a masked unit makes it fail at the last step for no reason.
   Mask **only** `radar-encoder-trial.timer`, whose trigger is the thing being
   inhibited, and unmask it in 4.5.

9. Confirm **no ingest or gunicorn process remains**, by process list rather than
   unit state — a stopped unit and a surviving process are different facts, and
   only the second one corrupts a migration.

### 4.3 Run the script — the single migration owner

10. `bash /root/update_coc.sh`

    It stops `coc_scheduler`, `personal_apps_gym_notifier` and `radar_ingest`
    (already down), resets the checkout to `origin/main`, installs Python
    dependencies, runs `flask db upgrade` for **coc_stats first and then
    personal_apps**, builds the frontend, and then restarts `coc_web`,
    `personal_apps_web` and the three background units.

    Do not run `flask db upgrade` by hand before or after. That would be the
    double migration this runbook exists to prevent.

11. Expected in the output: `radar_ingest_runs: projected 0 rows`.

12. **Stop conditions.** Any of these ends the release and goes to **section 7**
    for recovery, or **section 6** for rollback once the state is understood:
    - the script exits non-zero;
    - the projection line is missing or reports a non-zero count;
    - the build fails.

    **A non-zero exit does not tell you whether the restarts happened** — the
    script's own tail can fail after them. Run the two commands at the top of
    this section first. If the migrations are incomplete, go to section 7 and do
    not start services by hand into an unknown schema. If they are complete and
    the services are up, the release is deployed and the choice is verify or
    roll back, not recover.

### 4.4 Verify, after the script has restarted things

13. The script has already brought `coc_web` and `personal_apps_web` back. Read
    the schema now, as verification of what happened rather than as a gate before
    it:

```sql
select version_num from alembic_version;          -- expect a7c31f0b52d4
show columns from radar_ingest_runs;              -- expect the six projection columns
show tables like 'radar\_board\_observations';    -- expect present
```

14. **If any of these is wrong the services are already serving**, which makes it
    urgent but not automatic. Establish the actual state first — section 7's
    opening inspection is three read-only queries — because section 6.1
    deliberately *leaves the schema in place*, and that is the wrong response to
    a schema that is not what it should be. Then choose: section 6 to take the
    code out, section 7 to repair a half-applied migration.

### 4.5 Restore the inhibited trigger

15. `systemctl unmask radar-encoder-trial.timer` and start it **only if it was
    enabled and active before** (4.2 step 6). Restore the original state, not a
    tidier one.
16. `journalctl -u radar_ingest -n 50` must contain, verbatim:
    `radar board observation capture is disabled (RADAR_OBSERVATION_CAPTURE_ENABLED)`
17. **Record the end of the outage.**


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

Reproduced on the disposable MariaDB. `set -e` then stops the script before its
restarts, because this failure happens at the migration step rather than in the
tail — so a naive full revert leaves the site **down**, which is a worse outcome
than the fault being rolled back.

**The rollback is a deployment too, and takes the same stops.** Step 3 below runs
`update_coc.sh` again: another checkout, pip install, `npm ci` and Vite build. The
ruling in section 1 applies here exactly as it does in section 4 — an earlier
version of this section stopped only two units and then hand-started services the
script restarts itself, which is the model 4.3 exists to correct.

1. Stop, in this order, and record what was running first:

```
systemctl stop personal_apps_web        # OUTAGE BEGINS
systemctl stop coc_web                  # the rollback deploy touches the shared checkout too
systemctl stop radar_ingest
systemctl stop radar-encoder-trial.timer
systemctl stop radar-encoder-trial.service
systemctl mask radar-encoder-trial.timer
```

   Do **not** mask anything `update_coc.sh` must restart.

2. Revert the release merge on `main` **except** the two migration files. This is
   why 4.1 requires `--no-ff`: `-m 1` names the first parent of a merge commit, and a
   fast-forwarded release leaves no merge commit to revert as a unit.

```
git revert -n -m 1 <release merge sha>
git checkout <release merge sha> -- personal_apps/migrations/versions/d82f9afb5898_add_radar_observations.py
git checkout <release merge sha> -- personal_apps/migrations/versions/a7c31f0b52d4_add_radar_run_counter_projection.py
git commit -m 'revert the radar hub release, keeping its migration files'
git push
```

3. Run `update_coc.sh`. `flask db upgrade` is a **no-op** — the database is already
   at `a7c31f0b52d4` and the files that define it are present — and the script
   restarts `coc_web`, `personal_apps_web` and the three background units itself,
   exactly as in 4.3. **Do not start them by hand.**
4. Verify the deployed SHA is the reverted one, and that `/radar/` serves and
   `/radar/hub/` 404s. Check it; do not assume.
5. Unmask `radar-encoder-trial.timer` and restore it **only if it was enabled and
   active before**. Record the end of the outage.


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
**33 checks**, covering interruption after each of **all four** statements — including the case where every statement applied but the stamp was never written,
which is where stamping to skip is most tempting — an assertion that each partial
state is one the migration could actually leave, the rebuilt schema being
byte-identical to a clean run, the refusal to drop a populated table, and the
refusal to apply this procedure when the stamp shows the first migration
completed.

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

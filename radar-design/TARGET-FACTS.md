# Target facts, read from the VPS

Read 2026-09-09 by Claude over SSH, **read-only**, with the owner's explicit
authorization ("just read them yourself from the vps if its read only stuff").
Nothing was written, no service was changed, no migration was run, and no
deployment was performed.

These close gates 1 and 2 of RELEASE-RUNBOOK.md. **Four of them change the
runbook**, and two are defects the runbook had precisely because it was written
without this access.

Host `194.164.29.97` (`ubuntu`), the production box.

---

## 1. The deploy script — `/root/update_coc.sh`

Read in full. What it actually does, in order:

```
set -e
systemctl stop coc_scheduler
systemctl stop personal_apps_gym_notifier
systemctl stop radar_ingest
cd /root/coc-stats && git fetch --all && git reset --hard origin/main
source venv/bin/activate && pip install -r requirements.txt
cd coc_stats     && FLASK_APP=app.py flask db upgrade
cd personal_apps && FLASK_APP=app.py flask db upgrade
deactivate
cd personal_apps && npm ci && npm run build
systemctl restart coc_web
systemctl restart personal_apps_web
systemctl start coc_scheduler personal_apps_gym_notifier radar_ingest
```

Against the runbook's five requirements:

| # | requirement | verdict |
| --- | --- | --- |
| 1.1 | stops `personal_apps_web` | **NO.** It is never stopped, only restarted at the end |
| 1.2 | exits without restarting on failure | **PARTLY.** `set -e` aborts, but the restarts are the script's own last statements: a failure *in* them exits non-zero with the web apps already up |
| 1.3 | runs `flask db upgrade` once, right interpreter and directory | **YES**, inside the venv, `WorkingDirectory` correct |
| 1.4 | resets to `origin/main` | **YES**, `git reset --hard origin/main` |
| 1.5 | builds the frontend | **YES**, `npm ci && npm run build` after `deactivate` |

### 1.1 is unmet — and my reading of what that meant was overruled

The web process serves throughout the migration, because the script never stops
it.

I argued this was acceptable for this release: the deployed code declares no
`RadarIngestRun` or `RadarBoardObservation` model, so it cannot touch what the
migration creates, and `radar_ingest` — the actual writer — *is* stopped.
**Codex overruled that** (CODEX-DECISIONS.md, Fifth return, section B) and the
runbook now stops both web units before the checkout. The argument is a narrow
schema one and says nothing about what else moves underneath a running worker.

That second effect is the concrete reason. Between `git reset --hard` and the
restart, the running gunicorn holds **old Python in memory** while **new files
sit on disk**: templates are read per request, static assets are served from the
new tree, and Python dependencies have already been reinstalled. I had no
mixed-version test to support the claim that nothing breaks across it, which is
why the claim does not belong here.

**How long that window is, measured.** Five real `update_coc.sh` runs on
2026-09-08, bracketed by `radar_ingest` stopped → started in the journal:

```
03:32:04 -> 03:32:30   26 s
12:04:23 -> 12:04:47   24 s
12:43:32 -> 12:43:56   24 s
16:53:05 -> 16:53:31   26 s
17:35:27 -> 17:35:54   27 s
```

So the whole script runs in well under half a minute when `pip` and `npm ci` have
nothing new to fetch. Stopping the two web units turns that into a ~25-second
outage rather than the "minutes" an earlier version of this document guessed.

**The read facts above are unchanged.** What changed is the conclusion drawn
from them.

### It also does not stop the encoder-trial timer

See section 3. `update_coc.sh` neither stops nor masks it.

---

## 2. Target preflight — read-only, every value below is a read

```
engine                 10.11.14-MariaDB-0ubuntu0.24.04.1   (Ubuntu 24.04)
sql_mode               STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,
                       NO_AUTO_CREATE_USER,NO_ENGINE_SUBSTITUTION
tx_isolation           REPEATABLE-READ
character_set_server   utf8mb4
collation_server       utf8mb4_general_ci
lower_case_table_names 0
max_allowed_packet     16777216
alembic_version        b3d9e1f5a274
radar_ingest_runs      ABSENT
radar_board_observations ABSENT
radar_watch            4 rows
radar_buckets          1,225,015 rows
deployed SHA           b7d8adf06119b6767b1069e33fe5530c1c5494ea  (branch main)
capture flag           NOT set in .env, NOT in the ingest process environment
```

**Everything the runbook predicted is confirmed.** The stamp is exactly
`b3d9e1f5a274`, both new tables are absent, and `sql_mode` and the isolation
level are **identical** to the rehearsal's. The upstream engine version matches
the rehearsal exactly; the build differs (Ubuntu package versus mariadb.org
binary), which was already stated as a limit and remains one.

Capture is off, confirmed at the process level rather than inferred from this
worktree.

### Two findings the preflight itself produced

**The deployed SHA is one commit behind `origin/main`.** The box is at
`b7d8adf`; `origin/main` is `2a83905`. Running `update_coc.sh` therefore deploys
that extra commit as well as the release. It is a merge of `dev_personal` that
changes no files relative to `b7d8adf`'s tree, so the effect is nil — but the
release is not the only thing that moves, and the runbook's drift check must
compare against the **deployed** SHA, not only against `origin/main`.

**The runbook's own preflight SQL was wrong.** It asked for
`@@transaction_isolation`, which does not exist on MariaDB 10.11:

```
ERROR 1193 (HY000): Unknown system variable 'transaction_isolation'
```

MariaDB spells it `@@tx_isolation`. That is a MySQL-ism I carried in from the
local environment, and it is exactly the class of difference this gate exists to
find. Corrected in RELEASE-RUNBOOK.md.

---

## 3. Services and timers

Running, and all six application units are `enabled`:

```
coc_scheduler  coc_web  mariadb  nginx
personal_apps_gym_notifier  personal_apps_web  radar_ingest
```

`radar_ingest` carries `Restart=always`, `RestartSec=30`. An explicit
`systemctl stop` holds it down; a crash does not.

### `radar-encoder-trial.timer` is a database writer, and it fires every minute

Its unit says so plainly: it "reads the trial row, and when the ten days are up
without a passing audit it **persists `recovering` and drains a bounded slice of
the recovery**", and it "needs the database and nothing else".

Observed cadence: last run 47 s before the inventory, next in 12 s. **Every
minute.**

`update_coc.sh` does not stop it. So during a release window it will fire
repeatedly against `personal_apps` while migrations run. **It must be masked for
the window** — `systemctl stop` alone is not enough, because the timer restarts
the service — and unmasked afterwards.

### The nightly backup is a cron job, not a timer

```
15 3 * * *  /root/backup_db.sh >> /root/db_backups/backup.log 2>&1
```

The runbook told the operator to read `systemctl list-timers`. **That would not
have surfaced the backup**, because it is in root's crontab. A release window
overlapping 03:15 would collide with a `mysqldump` of the database being
migrated. Corrected in RELEASE-RUNBOOK.md: check `crontab -l` as well.

Other timers present, none touching `personal_apps`: `sysstat-collect`,
`sysstat-summary`, `fwupd-refresh`, `apt-daily`, `apt-daily-upgrade`,
`dpkg-db-backup`, `logrotate`, `man-db`, `update-notifier-download`,
`systemd-tmpfiles-clean`, `certbot`.

---

## 4. The backup

```
script     /root/backup_db.sh, cron 03:15 daily
command    mysqldump --single-transaction --quick --routines --events
                    --databases coc_stats personal_apps | gzip
integrity  gzip -t immediately after writing, before the off-box copy
retention  14 days local, 90 days on Drive via rclone
location   /root/db_backups/
```

`--single-transaction` gives a consistent snapshot for InnoDB. `--routines
--events` means the scope includes stored programs. Both application databases
are in one file.

Available locally on the box: `db_2026-09-07_0315`, `db_2026-09-08_0315`,
`db_2026-09-09_0315`.

Restore verification is section 5 of FOUNDATIONS-LEDGER.md's "P2 backup restore".

---

## What was NOT done

No write of any kind. No `systemctl` state change, no migration, no deployment,
no file modified on the host. The only transfer off the box was a copy of the
already-existing nightly backup, whose checksum was verified against the
source before use.

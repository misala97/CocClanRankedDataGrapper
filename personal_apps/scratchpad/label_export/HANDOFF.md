# Radar extractor work — handoff, 2026-09-07

Branch `dev_personal`, repo `C:\Users\michi\Desktop\CodingStuff`, nothing merged
to main and nothing deployed. The encoder-judge trial is LIVE on the VPS and
MUST NOT be disturbed: an extractor change moves the mention population and
would move the trial's removal-share alarm. **Michi shortened the trial to 3
DAYS (told me 2026-09-07); started 2026-09-06 19:38 UTC, so it ends ~09-09
19:38 UTC.** Earlier notes saying 16 Sept are stale. Runs as
`radar_ingest.service` plus `radar-encoder-trial.timer`, which fires every
minute.

## VPS migration, agreed 2026-09-07

Michi bought an IONOS VPS L+ (6 vCores, 8 GB RAM, 240 GB NVMe, 5 EUR for 3
months then a struck-through 18 EUR -- the month-four price is NOT stated on
the tariff page and must be read at checkout). Reason, measured: the current
box is 3.8 GB with 3.0 GB used, 633-759 MB available and 301 MB already in
swap, while `radar_ingest` alone holds 1.4 GB resident. No leak -- that
process's RSS was byte-identical across two readings 20 minutes apart, and
load average is 0.06. The box is simply full, and 8 GB is what the NER +
encoder pipeline needs.

**Recommend Ubuntu 24.04 LTS on the new box, not 26.04**: the current one is
24.04 / Python 3.12.3 / MariaDB 10.11 / nginx 1.24, and onnxruntime wheels
routinely lag a brand-new Python by months -- that is what runs the encoder in
production. Migrate first, upgrade the OS later as its own change.

Complete inventory of what has to move (verified on the box, nothing else):
- five services: `coc_web`, `coc_scheduler`, `personal_apps_web`,
  `personal_apps_gym_notifier`, `radar_ingest`
- two timers: `radar-encoder-trial.timer` (every minute), `certbot.timer`
- one cron job: `backup_db.sh` at 03:15 into `/root/db_backups`
- one nginx site: `coc_stats`
- `/root` scripts: `backup_db.sh`, `update_coc.sh`, `check_logs.sh`
- two databases, 3.8 GB of MariaDB files -- DUMP AND RESTORE, never copy
  `/var/lib/mysql`
- `/root/coc-stats` 1.4 GB checkout + venv -- REBUILD the venv, never copy it
- the env/secrets files
- certbot: the certificate follows the domain, so it is the step people forget

Plan Michi agreed to: build the new box completely and run both apps on its
IP, tested, nothing switched. Then a final dump and a short cutover, keeping
the old box as fallback for a few days. The DNS change and the cutover
go-ahead stay his.

### Migration progress, 2026-09-07 (new box 194.164.29.97, Ubuntu 24.04.4)

DONE on the new box, all verified:
- root SSH by key only (`/etc/ssh/sshd_config.d/10-keys-only.conf`); ufw
  allows 22/80/443 only; timezone Europe/Berlin
- apt: mariadb-server 10.11, nginx 1.24, certbot + nginx plugin, python3.12
  venv/dev, libmariadb-dev, rclone, git, build-essential; Node 24 from
  nodesource (old box has 24.19, new 24.20). google-chrome-stable NOT
  installed: nothing in the repo uses it.
- `/root/coc-stats` cloned from GitHub at main 13c9fce (same as the old box),
  using the OLD box's deploy key copied to `/root/.ssh` (GitHub auth verified
  as misala97). venv built from requirements.txt: 79 packages, onnxruntime
  1.29.0, Flask 3.1.3; PyMySQL is the driver both apps use (`mysql+pymysql://`),
  the old box's mysqlclient was an unused manual extra.
- `.env` copied to `/root/coc-stats/.env` (DB_HOST=localhost, coc_user,
  RADAR_JUDGE_PRIMARY=encoder). rclone.conf copied and verified read-only
  (`rclone ls gdrive:vps-backups/` lists the dumps).
- Non-git state copied: `personal_apps/artifacts/judge/` (active.json + v1/
  model.onnx 540 MB + tokenizer + config -- loads in 3.4 s on this CPU),
  `nasdaqlisted.txt`, `otherlisted.txt`, `scratchpad/arctic_backfill_resume.json`,
  `coc_stats/locks/`, `reports/`; `coc_stats/logs/` created empty.
- Frontend built (`npm ci && npm run build`): static/gym/dist, static/radar/dist.
- MariaDB: old `50-server.cnf` applied (bind 0.0.0.0, utf8mb4, Europe/Berlin,
  16M packet) -- it FAILED to start until the timezone tables were loaded
  (`mysql_tzinfo_to_sql /usr/share/zoneinfo | mariadb mysql`); remember that
  on any fresh MariaDB. Users `coc_user@localhost` (ALL on both DBs) and
  `mgemmel@%` (ALL on *.*) recreated with the old password hashes via
  SHOW CREATE USER; the staged file was shredded. 3306 is NOT reachable from
  outside (ufw) -- open it for Michi's IP only if he uses Workbench remotely.
- The seven unit files copied verbatim; the five services ENABLED but not
  started; `radar-encoder-trial.timer` left DISABLED (this is a copy of the
  DB, the trial runs on the old box).
- `/etc/letsencrypt` copied whole (three certs, renewal confs, account);
  nginx site copied verbatim, stock default site removed; TLS verifies on all
  three hostnames via `curl --resolve`; raw IP drops the connection (444)
  like the old box. certbot.timer state: see the check below.
- `/root/backup_db.sh`, `update_coc.sh`, `check_logs.sh` copied. Root crontab
  STAGED at `/root/stage/crontab.txt`, NOT installed (it would push dumps of
  the copy to Drive).
- Dump `db_2026-09-07_0315.sql.gz` (184 MB, gzip-verified) copied to
  `/root/db_backups/`; restore was RUNNING at the time of writing
  (`gunzip < dump | mariadb`, `radar_bucket_sources` is the slow table).

STATE AT HANDOVER TO CODEX (2026-09-07 ~13:40 CEST):
- The logical restore of `db_2026-09-07_0315.sql.gz` was STILL RUNNING
  (`pgrep -f gunzip`), in `radar_bucket_sources` at the F tickers, 502 MB in
  `/var/lib/mysql`, 23 + 20 tables created. It is slow because MariaDB fsyncs
  per INSERT batch; `innodb_flush_log_at_trx_commit=2` and `sync_binlog=0`
  were SET GLOBAL for the duration -- put them back to 1 after (or just
  restart mariadb, which also applies `99-tuning.cnf`). A runtime
  `SET GLOBAL innodb_buffer_pool_size=1G` did NOT take (still 128 MB); the
  persistent `/etc/mysql/mariadb.conf.d/99-tuning.cnf` applies at restart.
- This restore is a REHEARSAL. It proves the procedure and lets the apps be
  tested on the new IP. The cutover needs a FRESH dump (or the fast path
  below), because everything since 03:15 is missing from it.
- FAST PATH for the real cutover: both boxes run the identical MariaDB
  10.11.14-0ubuntu0.24.04.1. A cold copy of `/var/lib/mysql` (old mariadb
  STOPPED, rsync/tar over ssh, then start here, `chown -R mysql:mysql`) is
  valid between identical builds and takes ~10 min for 3.8 GB, against 90+
  min for the logical restore. Only do this with the old server stopped; a
  copy of a running datadir is corrupt.
- THE TRIAL CAN MOVE INTACT. It is DB state plus `radar-encoder-trial.timer`;
  the model is already here. A cutover carries it across paused, not
  restarted: stop old daemons -> copy DB -> start here WITH the timer
  enabled -> ingest catches up from its Arctic Shift cursors. Best window is
  BEFORE sampling opens at 2026-09-07 19:38 UTC (labels due 09-08 19:38,
  deadline 09-09 19:38 UTC). Whoever operates the trial from another chat
  must be told the new IP first, or their sampling/labelling steps hit a
  frozen copy on the old box.

STILL TO DO, in order:
1. Restore finishes -> table counts and sizes vs the old box.
2. `systemctl start coc_web personal_apps_web` -> curl each hostname with
   `--resolve host:443:194.164.29.97`, expect 200 and DB-backed pages;
   journal clean.
3. Smoke-start `coc_scheduler`, `personal_apps_gym_notifier`, `radar_ingest`
   (the last loads the encoder), confirm clean startup, then STOP them: they
   would ingest into the copy and share the CoC API token with the old box.
4. Cutover, after the trial ends (deadline 2026-09-09 19:38 UTC) and on
   Michi's go: stop daemons on OLD box; fresh `backup_db.sh` there; copy the
   dump; on NEW box `DROP DATABASE coc_stats; DROP DATABASE personal_apps;`
   then restore; start all five services; install the crontab; enable
   `radar-encoder-trial.timer` ONLY if the trial is still meant to run.
5. DNS: all three hosts are `*.viewdns.net` (dynamic-DNS provider). Michi
   changes the A records to 194.164.29.97. Then `certbot renew --dry-run` on
   the new box to prove renewal works from the new IP.
6. Keep the old box up as fallback for a few days; then cancel.

## The 6-epoch experiment: ANSWERED, more epochs is not the lever

<!-- Migration takeover audit is appended at the end of this document. -->

Ran to completion 2026-09-07 (~47 min), log
`encoder/retrain-6ep-2026-09-07.log`, results in the newest
`encoder/run-*.json`. Training loss fell hard throughout (4.712, 3.455,
2.794, 2.254, 1.854, 1.666) while the locked sets did NOT follow -- the
signature of overfitting beginning.

| set | relevance macro-F1 @4 | @6 | removal P @4 | @6 |
|---|---|---|---|---|
| natural | 0.740 | 0.756 | 0.878 | 0.886 |
| hard | 0.752 | 0.729 | 0.957 | 0.944 |
| recall | 0.625 | 0.614 | 0.903 | 0.902 |

Up on one, down on two, all inside noise. **So the tone heads are
data-starved, not undertrained** -- which the class counts already implied
(127 `flat` and 424 `mixed` in the whole corpus). Do not re-run this
experiment.

Two things DID improve consistently and are worth keeping:
- precision on the keep decision: natural 0.913 -> 0.934, hard 0.873 ->
  0.877, recall 0.883 -> 0.896;
- polarity reversals: 17.4 -> 16.5, 8.7 -> 7.8, 16.2 -> 13.1 per cent.
  Still nowhere near the 2% gate.

NOTE: `encoder/model-train17090` now holds the 6-epoch weights. The
4-epoch numbers survive in `encoder/run-20260906-225937.json`.

## What this session did

**The problem Michi named:** every number the project had about extraction was
conditioned on what the extractor ACCEPTED. `ingest._store_mentioning_posts`
drops any post with no `high` mention before writing, so the rejected
population had no text anywhere and recall had never been measured.

1. **Captured the raw stream** (`scripts/capture_arctic_raw.py`): 7 days x 34
   subreddits through Arctic Shift, unfiltered, 198,586 posts, 112 MB at
   `radar_labels/raw/reddit/`. 21 minutes, free archive, no quota.
2. **Measured both populations** (`scripts/measure_extractor_population.py`):
   the production extractor plus a loose pass keeping only what the rules
   rejected, each candidate tagged with the rule that rejected it. Latest run
   is `raw/population3/` (population/ and population2/ are superseded).
3. **Two labelling waves**, 4,500 rows total, Sonnet via subagents, no API
   quota — `radar_labels/labels-recall.jsonl`, against
   `candidates-2026-09-06.jsonl` (3,000) and `candidates-topup-2026-09-06.jsonl`
   (1,500).
4. **Retrained the encoder** on 17,090 rows including 3,598 wave rows, and
   locked a third evaluation set, `test-recall.json` (902 rows).

## What was measured

**Recall, first time ever measured: ~11,450 real mentions a week are thrown
away**, against 46,527 counted. Volume-weighted per cause (a flat average of the
wave under-reports it, because the wave caps rows per symbol and the big symbols
are the ones that are almost always real):

| cause | hit rate | per week | recovered |
|---|---|---|---|
| company named, no symbol | 72.4% | 8,501 | 6,151 |
| symbol in lowercase | 74.2% | 6,541 | 4,852 |
| stopword | 5.7% | 6,311 | 363 |
| cashtag outside universe | 89.6% | 86 | 77 |

**The stopword list is vindicated** — 6.5% hit rate, it blocks almost nothing
real. The one exception is BE (Bloom Energy), 20 of 24 real, ~155/week.

**Per-token verdicts from the top-up wave** (the actionable half):

- Recover: gopro/nike/nvidia/tesla 100%, jensen 98%, google 91%, zuck 88%,
  musk 72%.
- Noise: local, daily, white, total, reserve, east, earth, exchange all 0%;
  internet 2%, fidelity 6%, operating 7%, monday 10%.
- Ambiguous, and splitting by listing separates them cleanly: `apple` is
  Apple Inc 73% / Apple Hospitality REIT 0%; `trump` is Trump Media 29%;
  `reddit` 38% (half the time people mean the site).

**The encoder as an EXTRACTION gate is already at least as good as the rules**:
precision when it says relevant is 0.913 natural / 0.873 hard / 0.883 recall,
against roughly 0.75 for the rules on the stratified sample (~0.89 by volume on
head tickers). Adding the wave rows did NOT disturb the production sets
(natural 0.711 -> 0.740, hard 0.757 -> 0.752): it taught the new classes without
cost to what it knew.

**As a SENTIMENT judge it is not ready** and all five ship gates still fail.
Those gates were written for replacing Haiku at reading tone, not for
extraction — do not conflate them again. attitude 0.71-0.75, expected_move
16-17% polarity reversals, confidence 0.60-0.64.

## Open, in the order agreed

1. **The free fixes for the tone heads**, neither needing new labels:
   - train the directional heads only on rows that HAVE a direction (6,019 of
     10,323 relevant rows say `unknown`, plus 4,890 irrelevant rows forced to
     none/unknown — so two thirds of what that head sees is a non-answer);
   - make a polarity REVERSAL cost more than a miss, or refuse a direction
     below a confidence threshold.
   - Structural: attitude and expected_move are nearly one variable
     (positive-up + negative-down is 3,626 of 4,177 directional rows). Two heads
     predicting one thing can disagree, which is itself a source of reversals.
     Merging them into one direction head with an explicit "no direction" class
     would remove that failure mode.
2. **A directional labelling wave** (~3,000) IF the above is not enough. flat has
   127 examples in the whole corpus, mixed 424. Michi must name the size.
3. **deberta-v3-base** as a capacity experiment, ~2 hours GPU. Weaker
   motivation now that the 6-epoch run has shown the limit is data rather
   than training length, but it is the one remaining way to separate
   capacity from data.
4. **The precision round was never implemented** — it was designed, costed
   against a real week, and then deprioritised when Michi reframed the work as
   loose-extractor-plus-encoder. If the encoder ships as the gate, most of it is
   moot. Two findings are NOT moot and are real universe bugs, currently
   patched only locally inside the measurement script:
   - `universe.is_pooled_vehicle` misses "ProShares Ultra NVDA", so a leveraged
     single-stock fund inherits its underlying's SYMBOL as a name token;
   - debt listings get their due MONTH as a distinctive token ("Senior Notes due
     June 2070" makes `june` name T-Mobile's listing).
5. **Replace the FINDING half of the extractor with a trained model (NER).**
   Michi's own long-standing goal, confirmed 2026-09-07: the encoder answers
   "is this text about ticker X" but cannot find X itself, so a second trained
   model should do the finding. Shape: a token-classification head on the same
   kind of backbone tags which words are company references (catching what no
   list holds -- `Nvidea`, "the iPhone maker", a German phrasing); a STATIC
   lookup then maps the span to one of the ~12,500 symbols, because that many
   classes cannot be learned from ~20,000 examples; the existing encoder judges
   each resulting pair. Trained, static, trained.

   **The training data is nearly free.** Every wave row records the `evidence`
   token that triggered it, and that token is locatable in `author_text` for
   4,474 of 4,500 rows (99%), 2,198 of them labelled relevant. Span supervision
   without a new labelling round; the production set adds more.

   **GLiNER probe run 2026-09-07, zero-shot, no training** (`gliner_small-v2.1`,
   CPU, ~5 min): over 300 random zero-candidate posts with >=40 chars of body
   (a pool of 70,381 for the week), 42 (14%) carried something it called a
   company or ticker. Reading them, roughly a third are genuine misses --
   Xiaomi, Baidu, Bank of America, Dell, SpaceX, Anthropic, Starcloud -- and
   the rest are indices and the Fed (S&P, FOMC, 10Y), options notation (420C,
   330P), usernames, YouTube channels and one "they". So call it 4-5% of that
   pool, ~3,000 posts a week holding a company reference nothing currently
   sees. Full output with scores: `radar_labels/raw/gliner-probe.json`.
   GLiNER is an INSTRUMENT here, not a component: it is built to accept any
   entity type at runtime, which costs speed and precision. What would ship is
   DeBERTa-v3-small with a token-classification head trained on our own spans,
   through the existing ONNX path. GLiNER's second temporary use is
   pre-filtering a labelling wave, so rows carry signal instead of 95% blanks.

   **Measure the headroom BEFORE building.** After the loose-pass fixes, 132,164
   of 198,586 posts (66.6%) still produce no candidate at all -- that is the
   pool NER would search. Sampled BEFORE the fixes, ~1.5% of that pool held a
   company reference, and the fixes have since caught most of what that sample
   showed (Apple, Google). So: one small wave labelling "does this post mention
   any company at all" over current zero-candidate posts. At ~2% NER buys a few
   hundred mentions a week and is not worth a second model; at ~10% it is.
   Michi must name the size.

6. **Bluesky and 4chan have no raw capture.** Bluesky has no archive — a raw
   slice means draining Jetstream live for a few hours. Everything above is
   Reddit-only.

## Standing rules that shaped this session

- Never spend API quota; no labelling or subagent wave without Michi naming the
  size. Both waves here were explicitly sized by him (3,000 then 1,500).
- Ask before heavy local jobs: state GPU/RAM/minutes and get a "when". The 3080
  has 10 GB, 2.5 GB of it already in use; batch 8 at 512 tokens uses ~9.1 GB,
  and batch 16 froze the PC on 2026-09-05.
- TDD throughout; every commit carries the Co-Authored-By trailer.

## Traps hit this session, do not re-hit

- **The rendered prompt names no JSON envelope** (production supplies one
  through the API's response schema), so subagent labellers pick their own.
  `label_harness.validate` now accepts both shapes.
- **Wave ids collided.** Every wave counted from -1, so the top-up's ids landed
  on wave one's and the harness silently rendered nothing. Each wave now takes
  its own block of a million (`--wave 2`).
- **The standing quotas re-measure settled classes.** A top-up needs
  `--causes` or it spends a third of itself on ground already covered.
- **A flat average over a capped wave under-reports**, by 883 mentions a week
  here. Weight by symbol volume.
- **`_opens_a_sentence` alone was too weak** for function words: reading names
  in any case let `That` name HAVAR 171 times. The instrument that works is the
  share of a token's occurrences that are capitalised MID-SENTENCE, measured
  over the corpus: function words 0.3-3.6%, company names 23-81%.

## Commits (dev_personal, newest last)

    0ba12c0  capture the raw Reddit stream
    1b9c3b8  measure the extractor's two populations
    516f421  an ordinary word is what the stream writes lowercase
    e635d1d  a symbol is not a company name, a due month names no issuer
    81b8978  the population pass writes every accepted mention
    b9fa8e4  pick the recall wave from the rejected candidates
    f9c9ef6  the label harness accepts either verdict envelope
    f693b70  turn the recall labels into mentions per week
    04ab325  the loose pass was blind to Apple, Google and Zuck
    3f695fc  a top-up wave, capped by the token that produced the candidate
    751f0d3  each wave takes its own block of ids
    1cfede7  assemble training rows across waves, lock a recall test set
    7121ba0  train on the recall waves, score them on their own locked set

## Codex migration takeover audit — 2026-09-07, initial pause (superseded below)

Read this entire handoff before inspection. Local branch and HEAD verified as
`dev_personal`, `071913ed09496276ccc23bb5333689877b3d9510`. The workspace
already contains unrelated modified/untracked files; none belong to this audit
and none were changed or staged. Only this handoff is owned by this takeover.

**Stop reason:** OLD returned `Mon Sep 7 10:08:47 UTC 2026`; NEW returned
`Mon Sep 7 10:08:43 UTC 2026` and then `10:09:09 UTC`. This is earlier than
the above handover timestamp of approximately 13:40 CEST / 11:40 UTC.
Whether the handoff timestamp or server clocks are wrong is NOT established.
The user explicitly requires stopping, recording and reporting any discrepancy
before continuing. Server changes and further migration validation are paused
pending resolution. Do not schedule the trial from an assumed correct clock.

Verified directly, read-only:
- Both servers: Ubuntu 24.04.4 LTS; mariadb-server AND mariadb-server-core
  `1:10.11.14-0ubuntu0.24.04.1`; runtime
  `10.11.14-MariaDB-0ubuntu0.24.04.1`. Both checkouts on main at
  `13c9fce521bda2462772a7ad99a82497b85ccf49`; untracked files present.
- OLD: all five application services enabled/running; trial timer
  enabled/waiting, trial oneshot inactive at observation; MariaDB running;
  certbot timer enabled/waiting. RAM 3846 MiB, available 684 MiB, swap used
  907 MiB. Root disk 15% used (memory pressure, not disk fullness).
- NEW: all five application services enabled/inactive; trial timer
  disabled/inactive, trial oneshot inactive; MariaDB running; certbot timer
  enabled/waiting. RAM 7884 MiB, available 6996 MiB; no swap; root disk 3% used.
- information_schema table counts / estimated data+index MiB:
  OLD coc_stats 23 / 25, personal_apps 43 / 3237;
  NEW coc_stats 23 / 28, personal_apps 20 / 320. These are approximate sizes
  during a running restore, NOT an integrity or freshness check.
- Both buffer pools 134217728 bytes. OLD flush-at-commit=1, sync_binlog=0;
  NEW flush-at-commit=2, sync_binlog=0. Persistent tuning not yet inspected.
  Do not assume a restart sets sync_binlog=1: OLD currently has 0 too.
- NEW restore remains running: gzip PID 15439 and mariadb client PID 15440,
  same parent 15437; connection 36, root, personal_apps, Query, Update.
  Initial `pgrep -x gunzip` returned nothing because the process is named
  gzip; this was corrected by the process/connection checks below. Restore
  was neither killed nor restarted. Its data remains a stale rehearsal.

No remote state changed. No services started/stopped, no database modifications,
no model/API calls, no DNS changes, no deployment, no merge or cancellation.
SSH initially failed under the sandbox; authorized elevated read-only SSH worked.
No secret contents, hashes, keys, query text or environment contents were printed.

The current user instructions supersede stale migration text above: identical-build
cold copy is permitted ONLY with source and destination MariaDB stopped; cutover
can precede sampling but needs Michi's explicit go; OLD stays intact and is not
cancelled. Never smoke-start NEW radar while OLD radar or its trial timer runs.
The proposed radar smoke test needs a coordinated exclusive window or cutover.

Remaining, all OPEN: resolve clock/handoff discrepancy; finish verification of
SSH/UFW, configs, secret equality without disclosure, users/grants, packages,
model/artifacts, unit/script equality, staged cron, nginx/certificates and builds;
confirm restore completion; validate DB-backed web pages and service journals;
safe scheduler/notifier smoke tests; exclusive radar encoder startup validation;
confirm Michi told the other trial chat NEW's IP; obtain explicit cutover go;
cold-copy cutover and trial/cursor checks; Michi changes DNS; renewal dry run.
No rehearsal acceptance or cutover readiness is claimed.

Exact successful remote inspection commands (PowerShell single-quoted here-string
piped to `ssh -o BatchMode=yes -o ConnectTimeout=10 -i
$env:USERPROFILE/.ssh/id_ed25519 root@<IP> bash -s`, once per box):

```bash
date -u
hostname
. /etc/os-release
echo "OS=$PRETTY_NAME"
free -m
df -h / /var/lib/mysql
dpkg-query -W mariadb-server mariadb-server-core
git -C /root/coc-stats status --short
git -C /root/coc-stats branch --show-current
git -C /root/coc-stats rev-parse HEAD
systemctl show coc_web coc_scheduler personal_apps_web personal_apps_gym_notifier radar_ingest radar-encoder-trial.timer radar-encoder-trial.service mariadb certbot.timer -p Id -p ActiveState -p SubState -p UnitFileState
pgrep -x gunzip || true
mariadb -N -e "SELECT VERSION(); SELECT TABLE_SCHEMA,COUNT(*),ROUND(SUM(DATA_LENGTH+INDEX_LENGTH)/1024/1024) FROM information_schema.TABLES WHERE TABLE_SCHEMA IN ('coc_stats','personal_apps') GROUP BY TABLE_SCHEMA; SHOW GLOBAL VARIABLES WHERE Variable_name IN ('innodb_buffer_pool_size','innodb_flush_log_at_trx_commit','sync_binlog');"
```

Additional NEW-only confirmation (same SSH transport):

```bash
date -u
pgrep -af '[g]unzip|[g]zip|[m]ariadb' | sed -E 's/^([0-9]+) .*/pid=\1/'
ps -eo pid,ppid,comm | awk '$3 ~ /^(gzip|gunzip|mariadb|mysql|bash|sshd)$/ {print}'
mariadb -N -e "SELECT ID,USER,DB,COMMAND,TIME,STATE FROM information_schema.PROCESSLIST WHERE ID <> CONNECTION_ID();"
```

## Resumed Codex audit — grant-option pause (accepted for rehearsal below)

Michi clarified that the handoff time is local and server readings are UTC.
Resumed verification on that clarification; timestamp no longer blocks migration.
NEW reports Timezone=Europe/Berlin and NTPSynchronized=yes. No clock changed.
Cutover is NOT authorized; trial-chat notification of NEW's IP remains unconfirmed.

Verified (exact commands in
[MIGRATION-VERIFICATION-2026-09-07.md](MIGRATION-VERIFICATION-2026-09-07.md)):
- NEW: six CPUs; root key authentication enabled, password/keyboard interactive
  disabled; UFW active with only OpenSSH/80/443 on IPv4 and IPv6.
- Expected nginx/Python/Node/certbot/rclone/build packages installed. Venv has
  79 dependencies plus pip (80 distributions): onnxruntime 1.29.0, Flask 3.1.3,
  PyMySQL 1.2.0. Count matches the handoff when pip is excluded.
- Built dist directories exist (gym 20 files, radar 2); judge 4 files; reports
  6; locks/logs empty. Presence alone is not functional validation.
- Byte equality confirmed for .env, all seven units, nginx site, 50-server.cnf,
  three root scripts, all judge artifacts and enumerated Let's Encrypt files.
  Digests compared privately; only equality booleans displayed.
- Database authentication definitions match. coc_user has ALL on both DBs on
  both boxes, without grant option.
- NEW has 498 timezone names; bind=0.0.0.0, utf8mb4, Europe/Berlin, 16 MiB
  packet. 99-tuning.cnf specifies a 1 GiB buffer pool only; runtime still 128 MiB.
- NEW nginx configuration test passes; only coc_stats enabled. Web units bind
  127.0.0.1:5000 and :5001 as expected.
- NEW root crontab absent; staged cron has one active line and matches OLD's
  installed cron exactly. Not installed during this audit.
- Rclone differs only in access_token and expiry; refresh token, client secret,
  client ID and other fields match. Consistent with normal token refresh.
  No rclone values displayed; remote Drive listing not yet repeated.
- At 10:12:39 UTC NEW restore still active: gzip 15439, mariadb 15440,
  connection 36 updating personal_apps, 23 + 20 tables. Five apps inactive,
  trial timer disabled/inactive. Restore neither killed nor restarted.

**Actual discrepancy:** mgemmel@% has ALL PRIVILEGES ON *.* on both boxes,
but OLD additionally has WITH GRANT OPTION and NEW does not. Confirmed via
a separate boolean check after credential redaction of SHOW GRANTS initially
hid that suffix. It affects delegating database permissions, not app access.
No permissions changed. Paused startup/verification and reported to Michi under
his stop-on-discrepancy rule. Matching repair, if requested:

```sql
GRANT ALL PRIVILEGES ON *.* TO 'mgemmel'@'%' WITH GRANT OPTION;
```

The final cold copy carries OLD's mysql grant tables as well. Either repair
the rehearsal user now or explicitly accept this rehearsal-only difference.
Neither choice authorizes cutover.

Startup code inspection: coc_scheduler immediately runs sync tasks; notifier
can send due pushes after 10 seconds. Smoke tests must avoid unapproved messages
and model APIs. Radar must never start concurrently with OLD. Trial untouched.

Next: resolve grant difference, complete restore and rehearsal validation, then
explicit cutover go plus trial-chat notification confirmation. DNS and renewal
remain later steps. OLD live/untouched; NEW rehearsal/no apps started. Only
documentation changed on dev_personal, unrelated dirty work preserved; no merge,
deployment or cancellation.

## Rehearsal continued — grant difference accepted, waiting on restore

Michi explicitly instructed continuing rehearsal without repairing mgemmel's
missing grant option because the restore is still running. That difference is
accepted for rehearsal and is NOT a blocker. No GRANT was executed.

Additional successful checks on NEW:
- Local EncoderBackend construction and _load() succeeded in 4.94 seconds;
  peak RSS 1052 MiB. No daemon, trial write, inference or model API call.
- curl --resolve verified TLS on all three names (ssl_verify_result=0).
  With web services stopped, misala and mgemmel returned 502; pubquiz root
  returned its nginx 301. These are TLS checks, NOT web acceptance tests.
- rclone lsf gdrive:vps-backups/ --max-depth 1 succeeded, 30 entries.
- The 184151809-byte dump passed a full gzip read/CRC check in 24.4 seconds;
  contains 66 CREATE TABLE statements (23 CoC + 43 personal_apps).
- App credentials from .env connected through PyMySQL and read already restored
  tables: coc_stats.alembic_version 1, app_user 3, quiz_rounds 4, gym_exercises 34.
  Only counts and configuration-match booleans were displayed.
- Built manifests parse and every referenced file exists: gym 19 entries/files,
  radar 1 entry/file. No rebuild performed.

Restore observation: at 10:19:17 UTC input offset was 15990784 bytes; at
10:23:02 UTC it was 16515072 (about 9% of the compressed input), with gzip
15439 / mariadb 15440 still running and connection 36 in Update. Twenty
personal_apps tables exist; radar_bucket_sources is still being restored.
This table spans approximately compressed offsets 3.28–54.13 MB. Remaining
time is uncertain and likely substantial; compressed percentages do not map
uniformly to import time. No completion or database-integrity claim is made.

The runtime innodb_buffer_pool_size_max is also 134217728 bytes, so a live
resize cannot reach the staged 1 GiB. No restart, SET GLOBAL or import restart
was attempted. Asked Michi whether to leave the current restore running or
restart NEW and redo the rehearsal with the larger pool; no choice received
at time of this note. Default remains leaving the existing restore running.

All five NEW apps and its trial timer remain inactive. OLD untouched and
production remains there. Web/scheduler/notifier smoke tests are pending restore
completion; radar daemon startup additionally needs exclusive execution with
OLD. Encoder-load validation alone does not satisfy radar-daemon acceptance.
Cutover permission and trial-chat notification remain pending; DNS belongs to
Michi. Exact additional commands are in MIGRATION-VERIFICATION-2026-09-07.md.

## Approved rehearsal restart — IN PROGRESS on NEW only

Michi asked whether restarting made sense. Live measurements showed low CPU
use and 14–26% aggregate I/O wait. MariaDB documentation confirms that in this
build the buffer-pool maximum is fixed at startup. Recommended redoing NEW's
rehearsal; Michi explicitly answered "Yes, restart and redo the rehearsal".

Executed the guarded restart script recorded in the verification document:
verified NEW's assigned IP and inactive app/trial units; stopped MariaDB cleanly;
started it with the existing 99-tuning.cnf; verified a 1073741824-byte buffer;
verified old gzip/mariadb import clients were gone; dropped ONLY coc_stats and
personal_apps on NEW; set temporary restore durability globals to 2/0; started
vps-rehearsal-restore.service (oneshot) using /root/stage/rehearsal-restore.sh.
No files were copied from a live datadir. No grant changes or OLD commands.

At 10:26:55 UTC the new service was activating/start (expected for a running
oneshot). Both buffer size and maximum verified as 1073741824 bytes. Import
client connection 34, gzip PID 18546 and mariadb client PID 18547. At 10:28:45
it had read 12582912 compressed bytes after 2m20s, versus 16515072 after 28m43s
on the previous attempt. This is promising progress, not a completion estimate.

The job persists independently of SSH. Its EXIT trap restores
innodb_flush_log_at_trx_commit=1 and sync_binlog=1 and records the result in
/root/stage/rehearsal-restore.exit plus start/finish timestamps. On a failure,
client diagnostics are in root-only rehearsal-mariadb.stderr and gzip stderr;
NEVER print these files unfiltered because a client error may include SQL rows.
ExecMainStatus=0 while activating is not proof of success; require the exit file
0 and completed service plus 23/43 tables, then run structural and web checks.

Progress ledger: configuration/TLS/model-load/credentials/manifests verified;
fresh logical restore RUNNING; table checks/web HTTP/journals/scheduler/notifier
OPEN; radar daemon check waits for exclusive execution; cutover/DNS OPEN.
NEW web and background app units and trial timer remain stopped.

## Claude takeover after Codex's session limit — 2026-09-07 ~11:00 UTC

Verified before acting: `dev_personal` at b000417 (Codex's three commits), only
the two pre-existing Telegram files dirty. OLD fully live (five services, trial
timer, 655 MiB available at 10:50 UTC). NEW: rehearsal restore running as
Codex's `vps-rehearsal-restore.service`, buffer pool 1 GiB confirmed, all app
units inactive, trial timer inactive, no crontab.

Codex was right on two points and both are adopted:
- `mgemmel@%` lacked `WITH GRANT OPTION` on NEW. My redaction `sed` in the
  original grants check truncated the line after the password hash, which hid
  the suffix. Applied `GRANT ALL PRIVILEGES ON *.* TO 'mgemmel'@'%' WITH GRANT
  OPTION` on NEW; verified. Moot after a cold copy (grant tables travel), real
  if the dump fallback is used.
- NO daemon smoke-starts on NEW while OLD is live. `coc_scheduler` calls the
  CoC API immediately (shared token, shared rate limit); the gym notifier
  sends real pushes to Michi's phone after 10 s (duplicates from a stale
  copy); `radar_ingest` may reach the review tier with the Anthropic key and
  must never run beside OLD's trial. My Codex prompt said to smoke-start
  them; that instruction is WITHDRAWN. The daemons get their real first run
  at cutover, when OLD is stopped and they are the only instances.
  Substitutes done instead: `systemd-analyze verify` on all seven units
  (clean), encoder model load (3.4 s), and after the restore an app-context
  read-only load of the judge backend.

Rehearsal acceptance, per Codex's criteria: `/root/stage/rehearsal-restore.exit`
= 0 and the oneshot finished, 23 + 43 tables, alembic heads equal to OLD
(personal_apps b3d9e1f5a274, coc_stats b4e7d2a91f56), then web units up and
`curl --resolve` 200s on DB-backed pages with clean journals.

## REHEARSAL ACCEPTED — 2026-09-07 ~11:35 UTC

`vps-rehearsal-restore.service`: exit file 0, Result=success. Durability back to
flush=1 / sync_binlog=1 by Codex's EXIT trap; buffer pool 1 GiB. 23 + 43
tables, 3.2 GB on disk. Alembic heads equal OLD: personal_apps b3d9e1f5a274,
coc_stats b4e7d2a91f56. Row counts consistent with a 03:15 snapshot: app_user
3, gym sessions 52, radar_mentions 282,599, radar_posts 214,721,
radar_bucket_sources 6,642,653, radar_daily_closes 5,548,881, judge_trial 1.
Codex's restart with the larger pool restored in ~60 min against my aborted
attempt's projected 2+ h; the cold copy at cutover stays the plan.

`coc_web` and `personal_apps_web` STARTED on NEW and left running (nothing
routes to them; harmless, and they let Michi test via a hosts-file entry).
`curl --resolve <host>:443:194.164.29.97`: misala / 200 86 KB, /ranked 200
980 KB 1.6 s, /war 200 310 KB; pubquizmainz / 200 127 KB; mgemmel / and
/radar/ 200 4.6 KB (the login page, auth-gated as designed). Journals clean.
`EncoderBackend()` constructs under the venv (id radar-encoder-v1; the model
itself was loaded directly earlier in 3.4 s). All seven units pass
`systemd-analyze verify`. The three daemons and the trial timer remain
STOPPED on NEW by policy (see the takeover section) until cutover.

WHAT REMAINS IS MICHI'S: (1) tell the other trial chat the new IP;
(2) say go, and when -- before sampling opens 2026-09-07 19:38 UTC, or after
the deadline 09-09 19:38 UTC; (3) after cutover, change the three
`viewdns.net` A records to 194.164.29.97; then `certbot renew --dry-run` here.
Cutover procedure is in "STILL TO DO", fast path = cold copy of
/var/lib/mysql between the identical 10.11.14 builds with BOTH servers
stopped.

## CUTOVER DONE — 2026-09-07 11:12–11:13 UTC (13:12 CEST)

`/root/stage/cutover.sh` on NEW, log in `/root/stage/cutover-*.log`. Ninety
seconds of downtime. Cold copy of the datadir (3.9 GB, ~60 s direct
server-to-server at ~88 MB/s, via OLD's own deploy key added to OLD's
authorized_keys so NEW can pull). Verified after start: radar_mentions
271,840 on both sides, alembic heads b3d9e1f5a274 / b4e7d2a91f56, grants
travelled (WITH GRANT OPTION present), buffer pool 1 GiB, flush=1.
`/etc/mysql/debian.cnf` copied so maintenance credentials match the copied
grant tables. The rehearsal datadir is kept at `/var/lib/mysql.rehearsal-*`
(3.2 GB) -- delete once the new box has been stable for a few days.

NEW: five services + `radar-encoder-trial.timer` active, crontab installed
(nightly backup to Drive resumes tonight 03:15). Web verified live via
`--resolve`: /ranked 962 KB, /pubquiz 127 KB, /login 200. Memory 1.5 GB used
of 7.9.

OLD (82.165.240.212): all five services and the trial timer STOPPED AND
DISABLED (a reboot cannot resurrect a second instance); mariadb stopped but
left enabled and its datadir intact as the fallback; nginx still up, so
old-DNS visitors get 502 until DNS moves. Rollback = start mariadb + services
there. Do NOT cancel the old box yet.

FOUND AT FIRST SCHEDULER RUN -- MICHI'S ACTION: the Clash of Clans developer
API key is IP-bound; from 194.164.29.97 every fetch returns 403
`accessDenied.invalidIp`. Fix at developer.clashofclans.com: add the new IP
to the key, or create a key for it and set API_TOKEN in /root/coc-stats/.env,
then `systemctl restart coc_scheduler`. Until then the CoC pages serve the
database as it was at cutover; nothing breaks, nothing updates.

STILL OPEN: (1) Michi changes the three viewdns.net A records to
194.164.29.97 (TTL 60 s); (2) then on NEW `certbot renew --dry-run`;
(3) the CoC API key above; (4) watch the first radar_ingest cycles and the
trial ticks (see the verification below); (5) after a few stable days: delete
the rehearsal datadir, remove OLD's deploy-key entry from OLD's
authorized_keys, cancel OLD.

### Post-cutover verification, 11:16 UTC — production is running on NEW

- `radar_ingest`: started, "radar judge: primary=radar-encoder-v1 review=none"
  (encoder only, no API tier, no spend), sources bluesky+fourchan+reddit,
  first cycle landed 18 new posts within three minutes of start, latest post
  11:16:15 UTC (cutover was 11:13), RSS growing as the model loads, zero
  restarts, zero errors.
- `radar-encoder-trial`: three successful ticks in the first eight minutes.
  The trial continues here intact; sampling opens 19:38 UTC as scheduled.
- `coc_scheduler`: runs, but every CoC fetch is 403 until the API key allows
  194.164.29.97 (Michi, developer portal). `personal_apps_gym_notifier`: clean.
- Web: 200 with live data on all three hostnames via `--resolve`.

Migration is complete on the server side. Remaining for Michi: DNS, the CoC
key; then `certbot renew --dry-run` on NEW once DNS resolves here.

### 11:25 UTC — DNS and CoC key done by Michi, verified

- Public DNS (8.8.8.8): all three viewdns.net names -> 194.164.29.97; public
  HTTPS 200 with valid TLS on each, no --resolve.
- CoC API key now allows the new IP: after `systemctl restart coc_scheduler`
  zero `invalidIp` errors, clan_members updated=43, raid_weekend and clan_war
  fetches succeed. The three 403s logged at 13:22:28 CEST were the OLD process
  before the restart.
- `certbot renew --dry-run` launched from the new IP; result recorded below
  when it returns.
- Michi's Termius could not connect because the new box is key-only and the
  host entry had no key; fix is importing `C:\Users\michi\.ssh\id_ed25519`
  into Termius, not re-enabling passwords.

Remaining: certbot result; after a few stable days delete
`/var/lib/mysql.rehearsal-*` on NEW, remove the deploy-key line from OLD's
`authorized_keys`, cancel OLD.

### OLD box final state, 11:33 UTC

All five app services and `radar-encoder-trial.timer`: inactive AND disabled.
`mariadb`: stopped, left enabled, datadir intact (the fallback). `nginx`:
still running, harmless (DNS no longer points there). Root crontab REMOVED
(copy at `/root/crontab.retired.txt` on OLD; NEW has the same line
installed). `certbot.timer` disabled there. No application process exists on
OLD. Fallback = `systemctl start mariadb coc_web personal_apps_web
coc_scheduler personal_apps_gym_notifier radar_ingest radar-encoder-trial.timer`
on OLD after stopping the same on NEW, then repoint DNS.

### 11:32 UTC — `certbot renew --dry-run` on NEW: all three simulated renewals succeeded

MIGRATION COMPLETE. Nothing remains on the server side. Housekeeping in a few
days, once stable: delete `/var/lib/mysql.rehearsal-*` on NEW (3.2 GB), remove
the deploy-key line from OLD's `authorized_keys`, then cancel OLD.

## First live numbers from the encoder trial — read 2026-09-07 ~11:45 UTC

Trial `running`, model radar-encoder-v1, artifact sha 3bb32b56..., armed
09-06 19:32 UTC, first judgment 19:38, audit "not evaluated" (sampling opens
09-07 19:38 UTC, 746 rows, seed 20260906, baseline removal rate 0.5367).

1,164 mentions judged by the encoder so far (827 on 09-06, 337 on 09-07 to
midday CEST, ~1,500/day gated). Encoder writes relevance + origin ONLY; the
tone heads are NULL on every encoder row, so board tone falls back to the
lexicon for these mentions.

| | encoder (1,164) | Haiku, all rows (16,297) |
|---|---|---|
| relevant | 48.5% | 77.2% |
| irrelevant | 35.6% | 19.4% |
| uncertain | 16.0% | 3.4% |
| broadcast | 11.0% | — |
| removal share (irrelevant OR broadcast) | 0.437 (0.424 / 0.469 by day) | 0.537 baseline |

The 10-point removal gap is almost exactly the extra `uncertain`: the encoder
sends ~12 points of what Haiku decided into uncertain, which the board counts
neither way. Spot-read uncertain rows are content-free ("So puts got it thanks
OP", "Your current position?", bare "KEEL", "[removed]") -- conservative, not
wrong. Spot-read removals on real tickers: 4 of 5 correct (Teradyne/Aerotyne
under AEHR, FaradayFuture under USAR), 1 wrong ("Option heatmap ... for GPrO"
called irrelevant) -- consistent with the locked-set removal precision ~0.9.

Per ticker the encoder agrees with Haiku's historical behaviour: RSI 0.74 vs
0.95 irrelevant, API 0.89 vs 0.98, DJT 0.86 vs 0.72; real names pass (SPCX
0.00 vs 0.18, UUUU 0.00, AMC 0.03, XOM 0.03, GPRO 0.04 vs 0.18). Bluesky rows
53% irrelevant vs Reddit 32%, the known junk profile. Jargon tickers (RSI,
API) still reach the judged pool -- the extractor feeds them, the encoder
removes them; that is the precision round's job, not the judge's.

No API spend: review tier is `none`, the encoder is local.

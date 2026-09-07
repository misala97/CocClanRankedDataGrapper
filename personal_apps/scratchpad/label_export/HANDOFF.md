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

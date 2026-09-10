# Release record — the corrected, sortable Human chatter

**2026-09-10, 01:05–01:12 CEST.** Executed by Claude under the owner's explicit
authorization (CODEX-DECISIONS.md, "Owner approval — VC1 deployment").

**Result: deployed and healthy.** `/radar/` unchanged, capture off, no
migration. Two outage windows rather than one, the second caused by operator
error and recorded below in full.

The first release's record is RELEASE-RECORD.md; this is the second.

---

## SHAs

| | |
| --- | --- |
| reviewed candidate | `31ae58a` |
| documentation-only ruling commit | `8e3fd00` — verified: 3 files, all under `radar-design/` |
| **merge into main** | **`1f8016c`**, `--no-ff`, two parents `ba1c381` + `8e3fd00` |
| previous main and previously deployed | `ba1c381` |
| **deployed now** | **`1f8016c`** |

Pre-push verification, all passing: no excluded research commit is an ancestor;
**no migration added or changed**; the merge tree equals the candidate tree; two
parents with the first being the deployed SHA; nothing changes outside
`personal_apps/` and `radar-design/`; the only non-frontend changes are the two
additive backend files; `models.py` and every template untouched.

## The delta, which is why the preflight differs from the first release

| kind | files |
| --- | --- |
| application | **17** — 13 under `static/radar/src/hub/`, plus `types.ts`, `fixtures.ts`, and the two backend files `leaderboard.py` and `routes/api.py` |
| migrations | **none** |
| documentation | 72, all under `radar-design/` |
| tooling | 7 preview/capture scripts under `personal_apps/scratchpad/` |

The target was already at `a7c31f0b52d4` and this update adds no migration, so
the first release's "both tables absent" preflight does not apply and nothing
was dropped or stamped to recreate it. The runbook's expected
`radar_ingest_runs: projected 0 rows` line is likewise **absent by design** —
that line is a migration's output and there was no migration to print it. Its
absence here is correct rather than a stop condition.

## Preflight

- Window **01:05 CEST**, clear of the 03:15 backup cron by over two hours.
- `origin/main` and the deployed checkout both at `ba1c381`: **no drift**.
- Migration head already `a7c31f0b52d4 (head)`.
- All five units the script restarts — `personal_apps_web`, `coc_web`,
  `radar_ingest`, `coc_scheduler`, `personal_apps_gym_notifier` — **enabled and
  active**, so the script's unconditional restarts were safe.
  `radar-encoder-trial.timer` enabled and active.
- **Fresh backup** `db_2026-09-10_0105.sql.gz`, 204,736,987 bytes,
  sha256 `fac4d38ccfac365aa883f33537dfe9d98368fcb4b2e76f56be030fb61fcac446`,
  `gzip -t` OK, 44 foreign-key definitions, both `personal_apps` and `coc_stats`
  present, mirrored to Drive (`+ gdrive` in the backup log).

## Execution, and the mistake in the middle of it

```
01:08:34  services stopped                    OUTAGE 1 BEGINS
01:08:xx  trial timer disabled; NextElapseUSecRealtime empty, ActiveState inactive
01:08:xx  no surviving gunicorn / ingest / trial process
01:08:xx  bash /root/update_coc.sh
01:09:08  exit 0, all five services restarted OUTAGE 1 ENDS   —  34 SECONDS
01:09:19  services stopped again              OUTAGE 2 BEGINS
01:10:48  services restarted                  OUTAGE 2 ENDS   —  89 SECONDS
01:11:19  trial timer restored to enabled + active
```

**Outage 1: 34 seconds.** The planned deployment. Clean, exit 0.

**Outage 2: 89 seconds, and it was my error.** Wanting to read the head of the
first run's log — I had only captured its tail — I piped the deployment script
over ssh a second time. Piping the script *runs* it; there was nothing to read.
That re-ran the whole sequence against a checkout already at `1f8016c`: it
stopped the services and started `update_coc.sh` again. Then the PowerShell
pipeline that was reading its output closed early, which killed the ssh session
and `update_coc.sh` with it, leaving the services down and the site returning
502.

Recovery was the runbook's own answer to an interrupted run: establish where it
stopped, then act. The migration head was correct (and no migration was in play),
the checkout was at the intended SHA, no `update_coc.sh` process survived, so
`update_coc.sh` was run again to completion — it is idempotent and it is the
single migration owner. It exited 0 at 01:10:48 with all five services up.

The interrupted run had also disabled `radar-encoder-trial.timer` and been
killed before restoring it; it was restored to its recorded prior state of
enabled + active at 01:11:19 and confirmed.

**Nothing was lost and nothing was left half-applied**, but the site was
unavailable for 89 seconds it did not need to be. The lesson is narrow and
worth writing down: piping a script to `ssh` executes it, and
`Select-Object -First n` on a long-running ssh pipeline closes the pipe and
kills the remote process.

## Verification, on live production data

| check | result |
| --- | --- |
| deployed SHA | **`1f8016c`** |
| alembic head | **`a7c31f0b52d4`** — unchanged, as intended |
| services | all five **active + enabled** |
| `radar-encoder-trial.timer` | **enabled + active**, its recorded prior state |
| web errors since restart | **none** |
| `/radar/` | 302 to login when signed out — **unchanged and still there** |
| `/radar/hub/` | 302 to login when signed out |
| `/gym`, `/gym/statistik` | 302 — shared surfaces intact |
| `hub-CM5Pl8zL.js`, `hub-DX7Z0bej.css` | **200** |
| capture | verbatim `radar board observation capture is disabled (RADAR_OBSERVATION_CAPTURE_ENABLED)` at 01:12:24, `radar_board_observations` **0 rows**, and the flag is absent from `.env` entirely |

**`activity_sources` on real production rows — the point of the release.** All
**50** rows carry the field; none is missing it. The first six sampled:

```
ticker  feeds looked at   feeds talking    tone
RARE          36                4          B=8  S=0  U=8   -> 100.0% bullish
PG            36                4          B=4  S=5  U=26  ->  44.4% bullish
FAB           36                2          B=1  S=0  U=14  -> 100.0% bullish
UVXY          34                4          B=1  S=0  U=4   -> 100.0% bullish
DSGX          36                2          B=4  S=1  U=10  ->  80.0% bullish
SCHG          34                3          B=7  S=6  U=28  ->  53.8% bullish
```

Six of six have **fewer feeds talking than looked at** — 2 to 4 out of 34 to 36.
That is exactly the defect the owner rejected: the deployed board printed `36`
for every one of these rows and then listed the word "Reddit" thirty times. And
unlike the local development copy, production has **real directional tone
samples**, so the percentage and the bar render on real data rather than only on
the fixture.

**The sorting really is in the bundle served over HTTPS.** Fetching
`hub-CM5Pl8zL.js` from the public URL and searching it finds `Radar order`,
`Sorts these`, `directional /`, `platform` and `Sort by` — one occurrence each.

## What was deliberately not done

Capture remains off. `/radar/` is unchanged and remains the root route. No root
promotion, no OT1 watchdog cleanup, no schema downgrade, no live restore. The
migration chain is retained intact for routine upgrades and rollback.

## Still open

- **The owner's own authenticated look at the deployed hub.** Everything above
  is unauthenticated or server-side; no owner session was minted, and the
  signed-in view of sorting, the tone bar and the source summary on live data
  has not been checked by anyone but the owner can check it now.
- The named follow-ups in VISUAL-CORRECTION-LEDGER.md: the duplicate cell
  labels on Activity and Watching, Watching's tone/source presentation, and the
  zero-feed question in the legacy breadth filter.

## Rollback, if it is wanted

Code-only, and simpler than the first release's: this update adds no migration,
so there is no schema question at all. `git revert -m 1 1f8016c` on `main`,
push, and run `/root/update_coc.sh`. The previous hub bundle returns and the
additive `activity_sources` field simply stops being serialized — nothing reads
it but the hub.


---

# Second deployment, 2026-09-10 — the two honesty fixes

Same night, same authorization, a separate and smaller release: `4221196`, a
`--no-ff` merge of `c139856` and `e88e00b` onto `main`. Eight application files,
no migration, no new dependency, no configuration change.

## What went out

**A move the board measured is not an unknown move.** `_assemble` discarded the
price move whenever the quote was not score-eligible, so with the exchange shut
every row printed "Move unknown" over a number the board had already computed.
The gate on the DIVERGENCE is untouched and still tests `score_eligible` itself,
so carrying the move through cannot weaken it.

**"not judged yet" is not the same claim as "wording".** The lexicon scores
every mention at ingest, so `judged_by` is `'lexicon'` from the moment a mention
exists, and the evidence row read "wording" whether that was the final word or
merely the only thing that had run so far. `sentiment_judged_at` separates the
two and is the only thing that can. `judged_by` itself is deliberately unchanged
— it drives the tone precedence, and the tone on screen really is the wording
score's read.

## The window

| | |
|---|---|
| Preflight | 02:42:25 CEST — deployed `1f8016c`, five services active, head `a7c31f0b52d4 (head)`, 33 minutes clear of the 03:15 backup cron |
| Backup | `db_2026-09-10_0243.sql.gz`, 198M, `gzip -t` OK, sha256 `dc3b21f2…8b20969e`, 44 foreign keys in the dump, copied to Drive |
| Stop | 02:47:15 — `personal_apps_web`, `coc_web`, `radar_ingest`; no surviving gunicorn or ingest process |
| Build and restart | `/root/update_coc.sh` exit 0, bundle built in 2.16s |
| Up | 02:47:44 — all five units active |
| **Outage** | **29 seconds** |

No pipeline was attached to the ssh session this time. The 89-second outage
recorded above came from `Select-Object -First 30` closing the pipe and killing
`update_coc.sh` mid-run; the deploy script wrote its own log to a file on the
target and printed a bounded tail instead.

## Verified after, on live production data

- `HEAD` on the target: `4221196a32bc83e002758012b8fb992acb985bfd`.
- Migration head `a7c31f0b52d4 (head)` — unchanged, as predicted.
- Five units active since 02:47:44; `personal_apps_web` bound on 127.0.0.1:5001.
- `observations.capture_enabled()` returns **False**. There is no `.env` on the
  target and the unit sets only `PATH`, so `RADAR_OBSERVATION_CAPTURE_ENABLED`
  is unset and capture is off by default rather than by an override that could
  drift.
- `/radar/`, `/radar/hub/`, `/radar/api/board` and `/radar/api/activity` all
  answer `302` to the login page — the app is serving and both surfaces are
  still routed. No owner session was minted, so the checks below go through the
  application's own code inside an app context rather than through HTTP.
- **The move fix.** Building the live US board at 02:59 CEST with the exchange
  shut: 49 rows, 46 priced, **43 carrying a move** — it was 0 before. Sampled:
  `IRD −10.05%`, `YELP −2.34%`, `RR −2.34%`, `MSS −1.70%`, `MAT −0.65%`, all
  `price_status=closed`. Every one of them has `divergence=None`, which is the
  point: the score is still withheld with the tape shut, and only the measured
  number stopped being called unknown. The three priced rows with no move are
  the honest unknown — fewer than two snapshots in the window.
- **The judged-label fix.** Over 208 live posts on the first 25 tickers:
  `'Encoder'` 197, `'not judged yet'` 11, `'wording'` 0. The example that
  motivated the whole fix now reads correctly — `NMCO`, `reddit:pennystock`,
  19 minutes old, lexicon tone, labelled *not judged yet* rather than claiming
  the wording score had decided against it.

## Limitations that remain

- Still no authenticated owner view. Every check above is server-side or
  unauthenticated by design.
- `'wording'` did not appear in the live sample. It is the label for a mention a
  model HAS read and left with no lean, and none of the 208 sampled posts were
  in that state; the case is pinned by test rather than by observation.
- The named follow-ups in VISUAL-CORRECTION-LEDGER.md are untouched: duplicate
  cell labels on Activity and Watching, Watching's tone and source presentation,
  and the zero-feed question in the legacy breadth filter.

## Rollback

`git revert -m 1 4221196` on `main`, push, run `/root/update_coc.sh`. No schema
question — this update adds no migration.

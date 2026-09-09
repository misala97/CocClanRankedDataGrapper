# Release record — the side-by-side hub, deployed

**2026-09-09, 21:52–21:54 CEST.** Executed by Claude under the owner's explicit
authorization, following RELEASE-RUNBOOK.md and CODEX-DECISIONS.md "Sixth return".

**Result: deployed and healthy.** Both interfaces live on the same data, capture
off, `/radar/` unchanged.

---

## The two URLs

| | |
| --- | --- |
| existing board | `https://mgemmel.viewdns.net/radar/` |
| new hub, opt-in | `https://mgemmel.viewdns.net/radar/hub/` |

Both answer 302 to the login redirect when signed out, which is correct. The
hub's bundles serve 200 (`hub-Cr-xj2rB.js`, `hub-QjUPVu92.css`).

## SHAs

| | |
| --- | --- |
| reviewed candidate | `71a5f1b` |
| docs-only ruling commit | `745eb2c` — verified: 3 files, all under `radar-design/` |
| **merge into main** | **`ba1c381`**, `--no-ff`, two parents, tree identical to the candidate |
| previous main | `2a83905` |
| previously deployed | `b7d8adf` |
| **deployed now** | **`ba1c381`** |

Pre-push verification: no excluded research commit is an ancestor; exactly the two
release migrations added; merge tree equals the candidate tree; first parent is the
previous main.

## Preflight, before anything went down

- Window **21:52 CEST**, clear of the 03:15 backup cron.
- `origin/main` unmoved at `2a83905`; deployed `b7d8adf`; no competing deploy.
- Target: stamp `b3d9e1f5a274`, **both new tables absent**, `radar_watch` 4 rows.
- **Fresh backup** `db_2026-09-09_2150.sql.gz`, 198,559,203 bytes,
  sha256 `0d4524d79550558563146a5d20c1a2918b7d63b362bb3df6500c099ed3bfd25e`,
  `gzip -t` passed, 44 foreign-key definitions present. Taken through the verified
  nightly mechanism, mirrored to Drive.
- **Prior service state recorded**: `personal_apps_web`, `coc_web`, `radar_ingest`,
  `coc_scheduler`, `personal_apps_gym_notifier`, `radar-encoder-trial.timer` all
  **enabled + active**; `radar-encoder-trial.service` static + inactive. All five
  units the script restarts were active, so its unconditional restarts were safe.

## Execution

```
21:52:37  stop personal_apps_web, coc_web, radar_ingest,
          radar-encoder-trial.timer, radar-encoder-trial.service   OUTAGE BEGINS
21:52:xx  no surviving gunicorn / ingest / trial process
21:52:xx  bash /root/update_coc.sh
21:53:37  script exit 0, services restarted by the script itself   OUTAGE ENDS
21:54:49  ingest daemon started, sources=bluesky,fourchan,reddit
```

**Outage: 60 seconds.** The estimate was ~60 s against a 24–27 s historical
baseline; it landed at the top of that range, as expected for a build that now
includes the hub entry and a migration doing real DDL.

## Verification

| check | result |
| --- | --- |
| alembic stamp | `b3d9e1f5a274` → **`a7c31f0b52d4`** |
| `radar_ingest_runs` | present, with all six projection columns |
| `radar_board_observations` | present |
| services after | all five **active** |
| `radar-encoder-trial.timer` | restored to **enabled + active**, its recorded prior state |
| capture log line | `radar board observation capture is disabled (RADAR_OBSERVATION_CAPTURE_ENABLED)` — verbatim |
| `radar_board_observations` rows | **0** — capture is off |
| web errors since restart | **0** |

**The projection and the envelope agree on live data**, which is the whole point
of R3:

```
status ok   ver 1   countable 1
posts_seen 15729   posts_new 22   mentions 3211   buckets_written 966
json_valid(summary_json) = 1
json_extract(summary_json,'$.summary.posts_seen') = 15729   <- same value
```

The activity read, against live production data:

```
days=1    48 ms   completed=1  counted=1  posts_seen=15729  incomplete=1
days=7     2 ms   completed=1  counted=1  posts_seen=15729  incomplete=1
days=30    2 ms   completed=1  counted=1  posts_seen=15729  incomplete=1
```

All three windows work and the month view is retained. `counted_runs` equals
`completed_runs`, so the projection is being counted rather than skipped, and the
cycle still in flight is reported as `incomplete` rather than as a measured zero.

Shared surfaces, because `api.ts` and `vite_assets.py` changed: `/radar/`,
`/gym`, `/gym/statistik`, `/radar/api/board`, `/radar/api/ops` all correct, and
the gym bundle serves 200 — the shared asset helper is intact.

## One runbook correction, found by executing it

**`systemctl mask` fails on a unit whose file lives in `/etc/systemd/system`:**

```
Failed to mask unit: File /etc/systemd/system/radar-encoder-trial.timer already exists.
```

The inhibition still held — the timer was stopped and confirmed to have no next
elapse (`NextElapseUSecRealtime=` empty, `ActiveState=inactive`) — but `mask` is
the wrong verb for this unit. Use `systemctl disable --now`, or stop and verify
the next elapse is empty. Corrected in RELEASE-RUNBOOK.md.

## What was deliberately not done

Capture remains off. `/radar/` is unchanged and remains the root route. No schema
downgrade, no live restore, no root-route promotion. Those are separate decisions.

## Still open

- **The owner's visual side-by-side comparison**, signed in, at the two URLs
  above. That needs their eyes and their session; it was not done on their behalf.
- **TE1** — rebuild the disposable test database with constraints preserved,
  before any further backend feature work.
- The retired encoder trial's timer still fires every minute doing nothing.

## Rollback, if it is wanted

RELEASE-RUNBOOK.md section 6.1. Code-only, keeping both migration files, reverting
merge `ba1c381` with `git revert -m 1`. The schema is additive and the previous
code declares no model for either new table.

# Assignment — A-US-USD-ONLY-DEPLOY

You are Radar's Deployer. Return your result to the Mastermind.

The owner explicitly authorized deployment on 2026-09-17 with **“Yes lets deploy.”** This authorizes only the Git integration, backup-first production release, two-name environment cleanup, restarts, bounded smoke checks and rollback actions below. It does not authorize product-code changes, schema/data mutation, unrelated cleanup or workstream B.

## Workspace and release identity

```text
workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
branch: codex/radar-selected-price-charts
base/current HEAD before release commits: 38591e0f5e98faccb5228d84d1677843fcdb2aea
expected origin/main before release: 38591e0f5e98faccb5228d84d1677843fcdb2aea
expected origin/codex/radar-selected-price-charts before release: same SHA
production: root@194.164.29.97:/root/coc-stats
release method: established backup-first /root/update_coc.sh transient-systemd wrapper
```

Current production release `38591e0` has selected-price charts ON, Alpaca ON and Yahoo OFF. Preserve those states and all APCA credential lines exactly. Radar A changes only Radar's active DE/EU/EUR behavior.

Read completely before acting:

1. root `HANDOFF.md`
2. `radar-design/WORKFLOW.md`
3. `radar-design/A-US-USD-ONLY-SPEC.md`
4. `radar-design/A-US-USD-ONLY-LEDGER.md`
5. `radar-design/A-US-USD-ONLY-PLAN.md`
6. `radar-design/A-US-USD-ONLY-WARM-BOARDS-ADDENDUM.md`
7. `radar-design/A-US-USD-ONLY-VERIFY-1-RULING.md`
8. `radar-design/A-US-USD-ONLY-IMPLEMENT-1-RETURN.md`
9. `radar-design/A-US-USD-ONLY-IMPLEMENT-1-RULING.md`
10. `radar-design/A-US-USD-ONLY-REVIEW-1-RETURN.md`
11. `radar-design/A-US-USD-ONLY-REVIEW-1-RULING.md`
12. `radar-design/A-US-USD-ONLY-CORRECTION-1-RETURN.md`
13. `radar-design/A-US-USD-ONLY-CORRECTION-1-RULING.md`
14. `radar-design/MD-SELECTED-PRICE-ALPACA-RELEASE-CLOSURE.md`
15. `radar-design/MD-SELECTED-PRICE-ALPACA-DEPLOY-RETURN.md`

No subagents. Preserve all unrelated dirty/untracked files, other worktrees, production untracked files and services.

## Objective

Commit the exact accepted Radar A application/test delta and its dedicated documentation, fast-forward `main`, deploy through the established backup-first wrapper, remove the two retired production environment names, and prove:

- Radar is US-listings/USD-only on Hub, legacy, APIs, selected price and operations;
- omitted market means US and every explicit unsupported value—including a repeated second value—returns 400;
- exactly eight US boards are warm: All + Discover across 1h/4h/12h/24h;
- Alpaca selected price, US quotes/history/grouped closes, HA1 and ingest remain healthy;
- all archived DE/EUR rows remain byte-for-byte unchanged within canonical exports;
- deleted DE/FX/provider/mapping modules and jobs are absent and no stale environment name controls runtime.

## Exact accepted application manifest

The accepted application delta is exactly the current tracked diff under `personal_apps/` against base `38591e0`:

```text
142 tracked paths total
115 modified
27 deleted
0 untracked personal_apps paths
```

This full path set is listed by the Implementer return and must equal:

```powershell
git diff --name-status 38591e0f5e98faccb5228d84d1677843fcdb2aea -- personal_apps
```

Before staging, create a NUL-safe manifest outside the repository from that exact diff. Verify the counts/statuses above, verify every path is under `personal_apps/`, verify there is no untracked `personal_apps` path, and compare the set to the current accepted working tree. Stop on any discrepancy.

Stage only that verified manifest using an explicit pathspec-file workflow that includes deletions. Do not use `git add -A`, `git add .`, `git add personal_apps`, globs or an inferred hand-written subset. Inspect the complete staged diff, scan it for secrets/private `.env` content, run `git diff --cached --check`, and prove the cached path/status set equals the verified manifest exactly.

Application commit message:

```text
refactor(radar): make market data US USD only
```

## Documentation/evidence commit

After the application commit, create one explicit documentation commit containing only:

```text
radar-design/US-USD-ONLY-DECISION.md
radar-design/A-US-USD-ONLY-SPEC.md
radar-design/A-US-USD-ONLY-LEDGER.md
radar-design/A-US-USD-ONLY-RESEARCH-1-PROMPT.md
radar-design/A-US-USD-ONLY-RESEARCH-1-RETURN.md
radar-design/A-US-USD-ONLY-RESEARCH-1-RULING.md
radar-design/A-US-USD-ONLY-VERIFY-1-PROMPT.md
radar-design/A-US-USD-ONLY-VERIFY-1-RETURN.md
radar-design/A-US-USD-ONLY-VERIFY-1-RULING.md
radar-design/A-US-USD-ONLY-PLAN.md
radar-design/A-US-USD-ONLY-WARM-BOARDS-ADDENDUM.md
radar-design/A-US-USD-ONLY-IMPLEMENT-1-PROMPT.md
radar-design/A-US-USD-ONLY-IMPLEMENT-1-RETURN.md
radar-design/A-US-USD-ONLY-IMPLEMENT-1-RULING.md
radar-design/A-US-USD-ONLY-REVIEW-1-PROMPT.md
radar-design/A-US-USD-ONLY-REVIEW-1-RETURN.md
radar-design/A-US-USD-ONLY-REVIEW-1-RULING.md
radar-design/A-US-USD-ONLY-CORRECTION-1-PROMPT.md
radar-design/A-US-USD-ONLY-CORRECTION-1-RETURN.md
radar-design/A-US-USD-ONLY-CORRECTION-1-RULING.md
radar-design/A-US-USD-ONLY-DEPLOY-PROMPT.md
```

Also include only the `.md`, `.json`, `.txt`, `.xml` and `.py` files under `radar-design/artifacts/a-us-usd-only-implement-1/`. Exclude `.log`, `.png`, caches and generated files. Build and inspect an explicit docs manifest; report every included path. Exclude mixed continuity files (`HANDOFF.md`, `radar-design/HANDOFF.md`, `ASSIGNMENTS.md`, `MASTERMIND-STATE.md`, roadmaps, `WORKFLOW.md`, selected-price ledger), unrelated encoder/HA1/OpenTerminal/selected-price artifacts, and the eventual deploy return/evidence.

Documentation commit message:

```text
docs(radar): record US USD-only removal
```

The deployment return and new CURRENT notices may remain local/uncommitted, matching prior release precedent.

## Local pre-commit and pre-push gates

1. Capture branch, HEAD, both origin refs, full status and hashes for all 142 accepted application paths before staging.
2. `git fetch origin`. If `origin/main` or the feature ref differs from `38591e0`, stop without rebasing, merging, resetting or force-pushing.
3. Run `git diff --check` before staging.
4. From `personal_apps/`, run with bytecode/cache writes disabled where supported:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
py -3.12 -m pytest tests/selected_price_unit --confcutdir=tests/selected_price_unit -q -p no:cacheprovider
py -3.12 -m pytest tests/ha1_unit --confcutdir=tests/ha1_unit -q -p no:cacheprovider
py -3.12 -m pytest tests/test_radar_massive.py --confcutdir=tests -q -p no:cacheprovider
npx vitest run -c vite.radar.config.ts
npx tsc --noEmit
npm run build
```

The full Vitest suite has an accepted baseline of 28 failures, all exact identities in `hub/pending.test.tsx`; compare identity sets, not just totals. Any new identity blocks deployment.

5. Run the focused API/Hub correction tests only through a process-local guard that independently proves both the engine URL and `select database()` identify `personal_apps_radar_wt`, strips destructive opt-in and refuses non-loopback sockets. The accepted result is 92 passed / one exact baseline failure. Do not run the unguarded activity migration test, do not bind `personal_apps`, and do not invent destructive-test authorization.
6. Confirm imports for `app`, `run_radar_ingest` and surviving scripts. Confirm the eight deleted runtime modules fail import.
7. Repeat the residual sweeps and verify active code/bundles contain none of the retired exchange/FX/provider vocabulary except approved archival ORM/migration strings, rejection tests and preserved clock/localization usage. `mauerstrassenwetten` remains intentionally.
8. Record generated Radar asset names and SHA-256 hashes. Generated `dist` is release output, not source-manifest expansion.
9. After both commits, prove every accepted path equals its committed blob, no accepted app/doc path remains dirty, the index is empty, and unrelated dirt remains preserved.

Push the feature branch normally, then fast-forward `main` to the exact two-commit release SHA with a normal push. No force push and no merge commit. Fetch again and prove both `origin/main` and the feature ref equal the release SHA before production access.

## Production preflight and archival-data proof

Before mutation, verify production HEAD is exactly `38591e0`, tracked files are clean, known untracked paths are understood, schema is `b7e3f9c1a2d4`, six expected services are active/enabled, zero units failed, ingest/producer are healthy, no fetch child is stuck, and recent error logs are quiet. Record current Radar flags by **name and normalized on/off state only**; never print values or secrets.

Create a mode-preserving production `.env` backup under `/root/perf3-release/` named for the release SHA. Record its path, mode, line count and SHA-256 without showing content. Confirm these final invariants are intended:

- `RADAR_SELECTED_PRICE_CHARTS_ENABLED=on` preserved;
- `RADAR_SELECTED_PRICE_ALPACA_ENABLED=on` preserved;
- `RADAR_SELECTED_PRICE_YAHOO_ENABLED` absent/off preserved;
- APCA credential names each remain exactly once and nonblank;
- `RADAR_DE_PRICE_MODE` removed;
- `OPENFIGI_API_KEY` removed;
- every unrelated environment line remains byte-for-byte unchanged.

Before the release, generate private canonical exports on the host for archived rows and record only row counts plus SHA-256 hashes—never row content—for:

- `radar_instruments` where `market='de' OR currency='EUR'`;
- `radar_quotes` where `market='de' OR currency='EUR'`;
- `radar_daily_closes` where `market='de' OR currency='EUR'`;
- all `radar_fx_rates`;
- `radar_mapping_generations` where `market='de'`;
- all `radar_market_data_cursors`;
- all `radar_market_data_cycles`;
- all `radar_market_trade_events`.

Use stable primary-key ordering and a private mode-700 scratch directory. Do not place row data in Git/evidence/terminal output. Recompute the same exports after final restart/smoke and require every count and SHA-256 to match. Retain the normal full database backup; remove only the validated temporary canonical-export files after hashes are recorded.

## Backup-first deployment

Use the established `/root/update_coc.sh` transient-systemd release method from the prior release.

1. Start the wrapper against the exact fetched release SHA. Require its normal full database backup, gzip/hash validation and off-host copy before application replacement. Record backup path, size, SHA-256 and off-host listing proof.
2. Require the wrapper's dependency/build, migration/no-op, service restoration and producer-readiness sequence to finish successfully. There is no migration in A; schema must remain `b7e3f9c1a2d4`.
3. Verify production HEAD equals the release SHA, tracked tree is clean, all 142 committed paths match expected hashes/deletions, deleted modules/fixtures are absent, built asset hashes match local output, and six services are healthy.
4. With the stale environment names still present but ignored by the new code, run the bounded US/USD-only application smoke below. If code health fails, roll back before editing `.env`.
5. Remove exactly `RADAR_DE_PRICE_MODE` and `OPENFIGI_API_KEY` using a private host-side editor. Do not print/hash either value. Preserve every other line and restrictive permissions. Restart only `radar_ingest` and `personal_apps_web`, then verify their PIDs/restart counts, producer readiness and logs.
6. Run the final smoke and archival fingerprints. Do not mutate historical rows.

## Production acceptance smoke

Use authenticated Flask-test-client or the established local application smoke without exposing cookies/credentials. Also confirm signed-out public requests redirect appropriately.

### Routes and visible contract

- `/radar/`, `/radar/hub/` and `/radar/legacy/` load successfully with omitted market and with `market=us`.
- All three return readable 400 responses with no embedded Radar payload for `market=de` and `market=us&market=de`.
- Hub and legacy contain no market selector, Germany/EU/EUR/Xetra/Tradegate/ECB/fallback/conversion wording or control gap; prices are `$`/USD and US provenance remains visible.
- Board and ticker APIs default omission to US, accept US and return the existing unsupported-market 400 for single or repeated non-US values.
- An embedded non-US payload is refused, not relabelled.

### Warm boards and operations

- Producer reports exactly 8/8 ready US keys after a bounded wait: All and Discover for 1h, 4h, 12h and 24h, each pair once.
- Key version 3, payload version 2 and observation schema version 2 are active; old keys are not served as current.
- Operations contains the retained US quote basis, grouped closes and post-close claims, and omits German cycles, mapping generations and download-budget panels.
- No DE, ECB or mapping job is registered or running. US history, quote, grouped-close, shared-board and ingest cycles remain healthy.

### Selected price and protected paths

- Preserve charts ON, Alpaca ON and Yahoo OFF.
- Verify one AAPL selected-price request with omitted market follows the same US contract as explicit `market=us`; explicit `market=de` returns `invalid_market`/400 before provider acquisition.
- Reuse cache/stored evidence when possible. Allow at most **one** new Alpaca provider request total, sequential, read-only, and only if needed to prove the deployed protected path. No retry loop and no account/trading/billing/asset endpoint.
- If a provider request occurs, require truthful `alpaca_sip`, delayed/raw provenance, finite positive strictly increasing actual observations, no splice/invented points, truthful bounded ops counters and no lingering child.
- Verify HA1 remains reachable and no unrelated product behavior changed.

### Final health

Require exact release SHA, clean tracked production tree, unchanged schema, archival hashes/counts identical, eight warm boards, six services active/enabled, zero failed units, normal worker counts/restart counters, fresh ingest cycles, no stuck child and no new traceback/5xx/error burst.

## Rollback

Record rollback targets before deployment.

- **Code failure before env cleanup:** durably revert the new application commit (and docs commit if desired) on a clean checkout, push normally, and redeploy through the wrapper. Do not use production `git reset --hard` as the durable rollback.
- **Failure after env cleanup:** restore the pre-release `.env` backup only if no unrelated env change occurred; otherwise reinsert exactly `RADAR_DE_PRICE_MODE` and `OPENFIGI_API_KEY` from the private backup without displaying values. Then perform the durable code rollback and wrapper deploy.
- **Data mismatch:** stop services that could write affected rows, preserve both fingerprints and the full backup, and stop for Mastermind direction. Do not overwrite or delete historical rows automatically.
- **Automatic rollback triggers:** service instability, schema drift, archival fingerprint mismatch, non-US/EUR exposure or relabelling, broken US primary path, selected-price provenance/fallback failure, request storm or credential leakage.

The prior stable code SHA is `38591e0f5e98faccb5228d84d1677843fcdb2aea`. Database schema needs no downgrade. Record whether rollback ran and the actual final state.

## Hard limits

- No product/test/source fix. Stop if one is needed.
- No schema design/migration edit, historical-row change, dependency/service-unit/nginx change, account/trading/billing action, paid action, universe refresh or workstream B.
- No credential or retired-key values in terminal output, commands, logs, hashes, evidence or Git.
- No reset/clean/stash/restore/deletion of user work.
- Do not claim deployment until exact SHA, env-name state, archival fingerprints, warm readiness, route contract and service health are freshly verified.

## Evidence and return

Write sanitized release evidence under:

```text
radar-design/artifacts/a-us-usd-only-release/
```

Write exactly one Deployer return:

```text
radar-design/A-US-USD-ONLY-DEPLOY-RETURN.md
```

Include:

- exact application/docs/release/deployed SHAs and both commit manifests;
- pre/post Git status, fetch/no-drift and origin verification;
- local commands/results, exact accepted Vitest failure-identity comparison and asset hashes;
- database backup path/hash/off-host proof;
- archival table names, counts and before/after hashes only;
- `.env` backup path/hash/mode and names-only change proof;
- final non-secret flag states and confirmation APCA names remained nonblank without value exposure;
- wrapper/migration/build/readiness outcome and outage duration;
- Hub, legacy, API, repeated-market, selected-price, operations and protected-US smoke results;
- eight exact warm selections and readiness;
- service/log/child/ingest health;
- exact rollback targets and whether rollback ran;
- every limitation and preserved dirty/untracked/local/production state;
- confirmation of no product fix, schema/data mutation, unrelated cleanup, provider/account/trading action beyond the single permitted read-only price request, force push or secret exposure.

End with a self-contained copy/paste prompt addressed to Radar's Mastermind / Overview requesting release assessment and closure. Stop after the return; do not begin workstream B.

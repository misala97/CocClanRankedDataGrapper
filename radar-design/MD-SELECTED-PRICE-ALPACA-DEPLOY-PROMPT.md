# Assignment: MD-SELECTED-PRICE-ALPACA-DEPLOY

You are Radar's Deployer. Return your result to the Mastermind.

The owner explicitly authorized deployment and Alpaca activation on 2026-09-16
with: **“Yes lets deploy.”** This assignment authorizes the bounded Git,
production, configuration, restart, smoke, and rollback actions below. It does
not authorize product-code changes or unrelated cleanup.

## Workspace and release identity

- Workspace: `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts`
- Branch: `codex/radar-selected-price-charts`
- Base/current HEAD before release commits:
  `f632e5db5dd92e27480cbfccdf7b0638b26533ed`
- Expected `origin/main` before release: the same SHA.
- Production: `root@194.164.29.97:/root/coc-stats`
- Current recorded production state: release `f632e5d`, selected charts ON,
  Yahoo selected-price acquisition OFF, Alpaca selected-price acquisition OFF.
- Binding closure:
  `radar-design/MD-SELECTED-PRICE-ALPACA-C1-C2-CLOSURE.md`
- Prior release method/evidence:
  `radar-design/MD-SELECTED-PRICE-DEPLOY-RETURN.md` and
  `radar-design/artifacts/md-selected-price-release/`
- Stable role contract: `radar-design/WORKFLOW.md`

Read those artifacts, the current root `HANDOFF.md`,
`radar-design/MD-SELECTED-PRICE-LEDGER.md`, the C1 spec, source ruling, final
review ruling, and M1 return before acting. Verify Git evidence yourself.

No subagents. Preserve every unrelated dirty/untracked file, other worktree,
database, service, Remote Control session, and production untracked path.

## Objective

Integrate the accepted Alpaca selected-price candidate, deploy it through the
established backup-first production release path, install the two existing
owner credentials securely if production does not already have them, activate
`RADAR_SELECTED_PRICE_ALPACA_ENABLED=on`, and prove healthy delayed SIP selected
charts with a tightly bounded read-only smoke. Leave Yahoo acquisition OFF.

## Exact accepted application/test manifest

Only these 25 source/test paths belong in the application commit:

```text
personal_apps/features/radar/config.py
personal_apps/features/radar/price_chart_acquisition.py
personal_apps/features/radar/price_chart_contract.py
personal_apps/features/radar/price_chart_fetch.py
personal_apps/features/radar/price_chart_reader.py
personal_apps/features/radar/prices/alpaca.py
personal_apps/static/radar/src/hub/Admin.test.tsx
personal_apps/static/radar/src/hub/Admin.tsx
personal_apps/static/radar/src/hub/SelectedPriceChart.test.tsx
personal_apps/static/radar/src/hub/SelectedPriceChart.tsx
personal_apps/static/radar/src/hub/priceChart.test.ts
personal_apps/static/radar/src/hub/priceChart.ts
personal_apps/static/radar/src/hub/priceChartFixtures.ts
personal_apps/static/radar/src/hub/selected-price.css
personal_apps/static/radar/src/hub/selectedPriceGeometry.test.ts
personal_apps/static/radar/src/hub/selectedPriceGeometry.ts
personal_apps/tests/selected_price_unit/helpers.py
personal_apps/tests/selected_price_unit/probe_child.py
personal_apps/tests/selected_price_unit/test_acquisition.py
personal_apps/tests/selected_price_unit/test_alpaca_bounded.py
personal_apps/tests/selected_price_unit/test_launcher_isolation.py
personal_apps/tests/selected_price_unit/test_normalize.py
personal_apps/tests/selected_price_unit/test_reader.py
personal_apps/tests/selected_price_unit/test_route_ops.py
personal_apps/tests/selected_price_unit/test_window.py
```

`prices/alpaca.py` and `test_alpaca_bounded.py` are currently untracked and are
mandatory. Omitting `prices/alpaca.py` breaks the chart route at import time
even with the flag off.

Do not use `git add -A`, `git add .`, or stage from the dirty set. Create an
explicit path manifest outside the repository, stage only those paths, inspect
the staged diff, run `git diff --cached --check`, and verify the staged path set
equals the manifest exactly.

Commit message:

```text
feat(radar): add Alpaca SIP selected-price charts
```

## Release documentation commit

After the application commit, make one explicit docs/evidence commit containing
only the Alpaca/free-data decision, validation, C1/C2 prompt/return/ruling/
closure documents, the small text/JSON/Python evidence under
`radar-design/artifacts/md-selected-price-alpaca-*`, and this deploy prompt.
Exclude PNGs, logs, caches, unrelated encoder/HA1/OpenTerminal/US-universe work,
and mixed continuity files whose diffs contain other work. Use an explicit
manifest, inspect it, and report every included path.

Commit message:

```text
docs(radar): record Alpaca selected-price acceptance
```

The post-deployment return and CURRENT notices may remain local/uncommitted, as
in the prior release. Do not create an extra release solely to publish them.

## Pre-commit and pre-push gates

1. Capture branch, HEAD, `origin/main`, complete status, and hashes for all 25
   accepted paths before staging.
2. `git fetch origin`. If `origin/main` is no longer `f632e5d`, stop without
   rebasing, merging, force-pushing, or deploying; report the drift.
3. From `personal_apps`, with bytecode/cache writes disabled where supported:
   - `py -3.12 -m pytest tests/selected_price_unit --confcutdir=tests/selected_price_unit -q -p no:cacheprovider`
   - the five focused Radar Vitest files from the final review
   - `npx tsc --noEmit`
   - `npm run build`
4. From the worktree root, run `git diff --check`.
5. Confirm the build output exists and record its asset names/hashes. Generated
   `static/radar/dist` is deployment build output, not an excuse to widen the
   source manifest.
6. Scan the staged diff for credential values and private `.env` content.
   Variable names and documented test sentinels are allowed; secrets are not.
7. After both commits, verify every accepted working-tree file matches its
   committed blob (LF-normalized where needed), no accepted path remains dirty,
   and all unrelated dirt remains preserved.

Push the feature branch, then fast-forward `main` to the exact two-commit release
SHA using a normal push. No force push and no merge commit. Fetch again and prove
`origin/main` equals the release SHA before touching production.

## Credential handling authorization and constraints

The owner credentials already exist in the private root file
`C:/Users/michi/Desktop/CodingStuff/.env` under exactly:

- `APCA_API_KEY_ID`
- `APCA_API_SECRET_KEY`

You may programmatically read exactly those two values solely to install them
into production's private `/root/coc-stats/.env` over the existing encrypted SSH
path if they are absent or blank there. Never display, echo, log, hash, persist
in a repository/evidence/scratch file, place on a command line, or return either
value. Do not inspect any other private value.

Before changing production `.env`:

- make a mode-preserving backup under `/root/perf3-release/` named for the
  release SHA and record only its path and file hash;
- detect the two names and nonblankness without printing values;
- preserve every unrelated line exactly;
- ensure each name occurs exactly once after the update and preserve restrictive
  permissions;
- keep `RADAR_SELECTED_PRICE_YAHOO_ENABLED` absent/off;
- keep `RADAR_SELECTED_PRICE_ALPACA_ENABLED` absent/off during the initial code
  deployment and off-state smoke.

If secure non-echoing transfer cannot be guaranteed, stop before modifying
production. Do not ask the owner to paste secrets into chat.

## Production deployment and activation

Use the established backup-first `/root/update_coc.sh` transient-systemd release
method from the prior deploy return. Before release, verify production HEAD,
tracked cleanliness, known untracked paths, six service states, schema revision,
capture/shared-board state, and current flags. Preserve unrelated production
state.

1. Produce and verify the normal database backup and off-host copy even though
   no schema change is expected.
2. Deploy the exact fetched release SHA with Alpaca OFF. Require the wrapper to
   build assets, run its normal migration/no-op and readiness sequence, restore
   services, and finish successfully.
3. Verify deployed HEAD, tracked cleanliness, committed source hashes, built
   asset presence, unchanged schema, and all expected services healthy.
4. Run the existing authenticated Flask-test-client selected-price smoke with
   Alpaca OFF. It must remain a coherent stored fallback, start no child, and
   report no Alpaca source.
5. Add exactly `RADAR_SELECTED_PRICE_ALPACA_ENABLED=on` to production `.env`
   while preserving charts ON and Yahoo OFF. Restart only
   `personal_apps_web`, then verify readiness, worker count, restart count, and
   recent error logs.
6. Run one bounded authenticated read-only live smoke through the deployed
   application contract. Prefer a completed AAPL 1W window when the current 1D
   clamp has no eligible range; otherwise AAPL 1D is acceptable. Poll the same
   chart read only until the single child settles. Maximum **two Alpaca provider
   requests total**, sequential, no retry loop, no asset/trading/account/billing
   endpoint.
7. Require the ready response to show `source=alpaca_sip`, `fallback=false`,
   delayed consolidated SIP/raw provenance, positive finite actual observations,
   strictly increasing timestamps inside the modeled intervals, no invented
   points, and no provider/credential text. Confirm ops/admission source and
   counters are truthful and bounded. Also verify one stored fallback case still
   remains whole rather than spliced if a safe no-second-request case is already
   available; do not manufacture an outage.
8. Verify `/radar/` and operations health, signed-out redirects, capture/shared
   boards, ingest recency, six services active/enabled, zero failed units, no
   new traceback/error burst, unchanged schema, and no lingering child.

Do not probe 401/403/429/5xx, the 15-minute boundary, pagination, or malformed
responses in production. Do not run trading, order, account, billing, asset, or
mutating provider calls.

## Rollback

Record rollback targets before activation.

- **Flag rollback:** remove only
  `RADAR_SELECTED_PRICE_ALPACA_ENABLED`, restart `personal_apps_web`, verify
  stored fallback and no new child admissions. Restore the `.env` backup only if
  no unrelated production env change occurred after it; otherwise edit the one
  flag/credential scope surgically.
- **Code rollback:** use durable Git reverts of the new application/docs commits
  on a clean checkout, push normally, and redeploy through the wrapper. Do not
  use a bare production `git reset --hard` as the durable rollback.

Automatically execute flag rollback if live smoke exposes a credential leak,
request storm, repeated crash, false provenance, provider/stored splice, service
instability, or any Critical/Important acceptance failure. If the code release
itself breaks health with the flag off, execute code rollback. Preserve all
evidence and report the actual final state.

## Hard limits

- No product/test/source edits. Stop if a fix appears necessary.
- No new dependency, schema design, service/unit/nginx change, paid-plan action,
  account/trading/billing operation, universe capture, or unrelated cleanup.
- No credential values in terminal output, logs, evidence, Git, or return.
- No deletion/reset/clean/stash/restore of user work.
- Do not claim deployment until exact SHA, flag state, service health, and live
  smoke are freshly verified.

## Evidence and return

Write sanitized release evidence under:

`radar-design/artifacts/md-selected-price-alpaca-release/`

Write exactly one Deployer return:

`radar-design/MD-SELECTED-PRICE-ALPACA-DEPLOY-RETURN.md`

Include:

- exact application/docs/release/deployed SHAs and commit path manifests;
- pre/post status and `origin/main` verification;
- local test/build results and asset hashes;
- production backup path/hash/off-host verification;
- credential-name/nonblank checks without values, exact final flag state, and
  sanitized `.env` change description;
- release-wrapper result, schema/migration state, service health/log checks;
- provider request count and sanitized live smoke results;
- fallback, ops, signed-out, capture/shared-board, ingest and health results;
- exact rollback targets and whether rollback ran;
- preserved dirty/untracked/local/production state;
- every limitation or failed/unverified check;
- no secret or raw provider body.

End with a self-contained copy/paste prompt addressed to Radar's Mastermind /
Overview requesting release assessment and closure. Stop after the return; do
not begin A or B.


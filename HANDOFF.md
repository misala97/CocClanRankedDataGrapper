# HANDOFF — Radar Xetra history-proxy rollout

Read this and
`docs/superpowers/plans/2026-08-31-radar-market-data-v2-ledger.md`
before changing code. Verify prose against Git and fresh tests; evidence wins.

## Exact workspace

- Worktree: `C:\Users\michi\Desktop\CodingStuff-worktrees\radar-xetra-history-proxy-fix`
- Branch: `codex/radar-xetra-history-proxy-fix`
- Implementation HEAD: `47eae41` (the documentation-only handoff commit follows it)
- Design: `1d099e0`; plan: `6ef9d34`
- Implementation: `3bcd648`, `04e6176`, `47eae41`

## Dirty files and ownership

- This worktree was clean before this handoff update.
- Main checkout `C:\Users\michi\Desktop\CodingStuff` contains Michi-owned
  Telegram/candidate, `.agents`/`.codex`, scratchpad/probe, measurement, and
  measurement-test WIP. It is protected: do not edit, stage, clean, or commit it.

## Outcome

The fix is implemented and verified locally, but is **not deployed**.

- An XGAT primary may now carry one separately audited XETR history proxy only
  when both official reference rows are complete, supported, EUR, and have the
  exact same ISIN.
- Optional proxy fields participate in new generation hashes; payloads without
  them retain their old canonical JSON and SHA-256 behavior.
- Activation and rollback atomically govern both rows. Stale proxies become
  unavailable, and duplicate venue identities are rejected before mutation.
- The unchanged German history backfill discovers the mapped non-primary XETR
  row. Chart composition remains exact-ISIN and uses the proxy only before the
  first native XGAT close.
- No schema migration or dependency change is required.

## Production state (operator-observed, not locally verified)

At 2026-09-01 before this fix:

- generation 1: `active`, `openfigi`, hash prefix `7434cf387044`;
- generation 2: `shadow`, `legacy`, hash prefix `2d9e60341d5f`;
- 2,517 mapped German primaries;
- German live collection: `mode=active status=accepted`;
- German backfill found only 13 pre-existing XETR rows and stored all 13,
  ending at `VSEC:XETR`.

Generation 1 predates proxy-aware payloads. Deploying this branch does not
retrofit it; a fresh generation must be built and activated.

## Immediate operator rollout

1. Integrate this branch, push, and deploy through the normal release path.
2. From the deployed `personal_apps` directory, explicitly build a fresh
   shadow generation:

   ```bash
   /root/coc-stats/venv/bin/python run_radar_ingest.py --refresh-mappings
   ```

3. Inspect the new generation ID, source, full hash, decision counts, and proxy
   count. Do not activate an ID selected only by “latest” without reviewing it.
4. Activate that reviewed generation with `instruments.activate_generation(...)`.
   Confirm mapped XGAT primaries and mapped non-primary XETR proxies share the
   new `mapping_generation_id` and exact ISIN.
5. Dry-run, then backfill in bounded batches:

   ```bash
   /root/coc-stats/venv/bin/python -m scripts.backfill_radar_market_history --market de --dry-run
   /root/coc-stats/venv/bin/python -m scripts.backfill_radar_market_history --market de --apply --limit 25
   ```

   Continue with `--resume-after TICKER:XETR` from each batch's final key until
   the dry-run reports zero remaining targets.
6. Verify representative XGAT-primary tickers in 1W/1M/1Y views and confirm
   logs keep reporting accepted German active cycles.

Stop and retain the current active generation if the new build is incomplete,
the audited counts/hash are unexpected, activation refuses, or the proxy ISIN
does not exactly equal the primary ISIN.

## Verification

- Baseline before edits: 89 focused tests passed; `npm run build` passed.
- Task 1 mapping/hash suite: 45 passed.
- Task 2 activation/rollback suite: 22 passed.
- Backfill/history/detail integration: 98 passed.
- Focused mapping/market-data gate: **298 passed** in 141.03s.
- Adjacent quotes/board/leaderboard/migration gate: **108 passed** in 12.72s.
- Full backend gate: **1,813 passed** in 1,385.46s.
- Frontend gates: **403 general + 175 Radar = 578 passed**; TypeScript and
  both production Vite builds passed.
- The new backfill regression was proven non-vacuous: temporarily removing the
  proxy upsert made it fail with `StopIteration`; restoring it returned green.
- Only existing SQLAlchemy/datetime deprecation warnings remain.

## Scope boundary

Do not push, deploy, refresh production mappings, activate a production
generation, or run production backfill without Michi's operator action. Radar
market-data v2 Task 12 remains deliberately delayed for the rollback window.

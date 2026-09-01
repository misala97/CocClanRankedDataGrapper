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

The fix is implemented, verified, deployed, activated, and backfilled.

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

## Production state — verified 2026-09-01

- `main` deployed at `c8a24c1` through `/root/update_coc.sh`; migrations,
  dependencies, frontend builds, and service restarts succeeded.
- Generation 3 is active OpenFIGI with full hash
  `9dc5b062938f07a7fd609a83e2e3385e5db5ce4db39c6bdb363922f7d018f7d9`.
- Generation audit: 12,599 decisions; 2,517 mapped; 10,082 unavailable;
  2,504 XGAT primaries; 13 XETR primaries; 712 XETR proxies; zero invalid
  proxies and zero duplicate identities.
- Persisted authority: 2,517 mapped primaries and 712 mapped non-primary XETR
  proxies on generation 3; zero mapped XETR rows on another generation and
  zero primary/proxy ISIN mismatches.
- Generation 1 is retired. Generation 4 (`legacy`, hash prefix `8b879217f856`)
  is the exact pre-activation rollback snapshot; generation 2 remains an older
  legacy shadow.
- German backfill attempted 725 mapped XETR targets and stored 724. The sole
  refusal is `HIG` / `HFF.DE`: Yahoo returns HTTP 404, so exact-identity policy
  correctly leaves it absent instead of substituting an alias.
- Stored XETR history: 724 tickers, 150,633 rows, earliest 2024-07-10, latest
  2026-09-01. AAPL, NVDA, and TSLA each compose 544 points with
  `history_proxy=True`.
- `personal_apps_web` and `radar_ingest` are active. Post-activation German
  cycles continue `mode=active status=accepted` (latest observed 10/10 files,
  121 selected).

## Immediate next action

No rollout action remains. Visually confirm representative 1W/1M/1Y charts in
the UI and monitor ordinary accepted-cycle logs. Treat the `HIG` gap as an
explicit provider absence unless a future exact-identity Xetra history source
is added.

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

Radar market-data v2 Task 12 remains deliberately delayed for the rollback
window. Do not contract the schema or delete rollback generations yet.

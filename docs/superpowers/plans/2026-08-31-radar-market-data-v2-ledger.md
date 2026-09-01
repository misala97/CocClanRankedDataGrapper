# Radar Market Data v2 — Execution Ledger

Binding docs: `docs/superpowers/specs/2026-08-31-radar-market-data-v2-design.md`
and `docs/superpowers/plans/2026-08-31-radar-market-data-v2.md`, both at commit
`9dadd9c` (includes the 2026-09-01 `[A1]`/`[A2]`/`[A3]` amendments and the
binding Codex amendment-review corrections).

## Workspace

- Worktree: `C:\Users\michi\Desktop\CodingStuff-worktrees\radar-market-data-v2`
- Branch: `radar-market-data-v2` (created from `dev_personal` @ `9dadd9c`)
- Starting HEAD: `9dadd9c` (docs(radar): tighten market data v2 rollout)
- Main checkout: `C:\Users\michi\Desktop\CodingStuff` on `dev_personal` — carries
  protected dirty files that this plan must never touch or commit:
  `personal_apps/scripts/discover_telegram_sources.py`,
  `personal_apps/telegram_candidates.json`, plus untracked Telegram/scratchpad/
  measure-script WIP (see `git status` there). The worktree itself must stay
  clean of them.
- Alembic head before this plan: `f4b2d81c37a9`.
- Dev DB: MySQL 8 `personal_apps` @ localhost:3306 (tests use it directly).

## Operator gates (Michi-only; never bypassed by the worker)

- Task 1 Step 5: accept Deutsche Börse delayed-data terms, download the four
  current `DGAT/DETR` pre/post `.json.gz` files.
- Task 11 Step 8/9: shadow session, identity audit, activation flag changes.
- Any deploy. Provider flags default to legacy behavior throughout.

## Task state

| Task | State | Commit(s) | Focused tests | Independent review | Findings / notes |
|---|---|---|---|---|---|
| 1 | **COMPLETE** | 60c1f71 + review-fix commit | 17 passed (`tests/test_capture_deutsche_boerse_contract.py`) | CHECKPOINT: FINDINGS → all 4 SHOULD-FIX folded in (R6 precondition, fixture/table parity both directions, R2 bucket pinning, auditable aggregates), 4 MINOR: #7 fixed (splitlines), #8 accepted cosmetic, #5 folded into R5 text, #6 noted below | PASS ruling stands; reviewer confirmed no licensed-value leaks |
| 2 | **COMPLETE** | 6fc010b | 41 passed (models+migration) + 49 writer smoke | inline (post-hoc review batched with Task 3) | dev DB migrated to 6a21d4e8c9f0; old-writer compat + teeth variants proven |
| 3 | **COMPLETE** | 27746ec | 233 focused (prices/markets/quotes/batch/calendar/api/board/detail) | inline; batched into next review round | pre-v2 fallback test rewritten to spec §4.2 rule (mapped DE primary + dead feed → no US fallback) |
| 4 | **COMPLETE** | 6b54a9d | 41 (yahoo+prices) incl. dividend/split basis fixtures + semaphore teeth | inline; batched | split-only quote.close pinned |
| 4b | **COMPLETE** | 2845d53 | 38 (massive+prices) | inline; batched | typed GroupedFetch; no DB identity in adapter |
| 5 | **COMPLETE** | f249c54 | 52 (dbag+capture) | inline; batched | R1–R10 enforced; fixture ISINs now valid-length fakes |
| 6 | **COMPLETE** | c9be683 | 76 (openfigi+instruments+daemon) | inline; batched | interface deviation recorded: us_share_classes returns candidate TUPLES (none-vs-ambiguous distinguishable); R6 reference capture still owed before production reference fetch |
| 7 | **COMPLETE** | 0102f7d | 47 (market_data+quotes+retention) | inline; final review pending | one-commit-per-channel-pass; forced-failure atomicity proven |
| 8 | **COMPLETE** | 94c3632 | 197 focused | inline; final review pending | 1D teeth demonstrated (4 tests failed pre-fix); grouped floors + shadow-lane guards |
| 9 | **COMPLETE** | fc5d174 | 165 focused (99 pre-existing untouched) | inline; final review pending | R6: shadow/active mapping build REFUSES until reference capture (operator+worker step owed before German shadow) |
| 10 | **COMPLETE** | e3cbec2 | 175 frontend + 124 backend; builds typecheck | inline; final review pending | two legacy contract pins updated per spec §10 |
| 11 | **COMPLETE** (Steps 1–7; Steps 8–9 are operator gates) | 4fe2eb6 + review fixes 0d3ea22 | 14 report tests; 223 focused; 1752 full backend | Codex whole-branch review: findings fixed and reverified | enforced READ ONLY; independently scoped switches; grouped gate recomputes active coverage and binds audits to report+map hashes |
| 12 | deliberately delayed (post-rollback-window; Michi authorizes) | — | — | — | contraction migration b742e9d13c60 NOT written yet by design |

## Evidence log

- 2026-09-01: worktree created; baseline full backend+frontend suites started
  in background (result recorded below when finished).
- 2026-09-01: Task 1 Steps 1–4 done INLINE (Michi rejected subagent-driven
  execution — all tasks run inline in-session from here on). Capture script
  `scripts/capture_deutsche_boerse_contract.py` + tests green, read-only proof
  `grep requests|extensions|models|db\.` = no matches.
- 2026-09-01 ~10:50 UTC: operator gate satisfied — Michi accepted the DBAG
  delayed-data disclaimer in his browser and explicitly directed the worker
  to download the files itself. Live capture ran during the open session
  (08:34 UTC minute files). Discoveries: NDJSON payloads (capture tool gained
  a tested NDJSON branch), 301→signed-GCS-2s-expiry download transport,
  NO auth/cookie, zero observed corrections, `lastTradeIndicator='C'` =
  Xetra closing auction (observational proof: all C rows 15:35–15:39 UTC),
  no reference channel, XETR-pre = 200 MB/min uncompressed, empty gzip =
  market closed. Supplement written with rulings R1–R11; RULING: **PASS**.
  15 tests green incl. supplement↔fixture pointer-parity with teeth.
- Captured file SHA-256s (raw files NOT committed; local capture dir only):
  - XGAT pre  `DGAT-pretrade-2026-09-01T08_34.json.gz`
    `5bfbcd43d3b3a88ce2bba488b3ee347b9273124a71f6bdbd8928aff65076eb6b`
    (3,199,161 B comp / 42,212,673 B uncomp)
  - XGAT post `DGAT-posttrade-2026-09-01T08_34.json.gz`
    `1305b983cf6b9efe3e722cf090940773ada8e7b2f362a257bcbf72f399fe81ec`
    (12,632 B / 169,726 B)
  - XETR pre  `DETR-pretrade-2026-09-01T08_34.json.gz`
    `8dc542c60e8c1429c04debbd8af12f55265743e8f4bb68b6930b84f743a04b0b`
    (20,303,870 B / 200,552,648 B)
  - XETR post `DETR-posttrade-2026-09-01T08_34.json.gz`
    `5f391ddf43edcf2982c8620a6acebe43d471d8e128f84891718cb825c3e17125`
    (24,768 B / 369,581 B)

## Baseline

- Backend `python -m pytest tests/ -q`: **1557 passed** (507s). First run's
  error band was worktree environment only: the fresh worktree lacked the
  repo-root `.env` (dev MySQL password → "Access denied ... using password:
  NO") and the untracked `static/radar/dist` Vite build. Fixed by copying
  `.env` from the main checkout (git-ignored) and running `npm run build`.
  Any future fresh worktree needs both steps.
- Frontend `npm test`: **167 passed** (11 files).
- Task 1 review MINOR #6 watch item: XETR-pre caps (30 MiB/300 MiB) hold only
  ~1.5× headroom over the single observed minute file; the shadow report
  re-measures.

## Final verification and review fixes — 2026-09-01

- Review-fix commit: `0d3ea22` (`fix(radar): harden market data activation gates`).
- Corrected Yahoo daily-history metadata validation and made every production
  Yahoo history caller supply the mapped MIC; unmapped deep-tail rows refuse.
- Grouped activation now rejects zero active denominators, recomputes every
  expected day's current-active coverage from exact mapped identities and
  shadow rows, blocks duplicate/adjustment-basis conflicts, reports unmatched
  current-universe symbols plus measured/projected row storage, and binds the
  operator audit to both report and instrument-map hashes.
- German and US-close truth/incomplete evidence is carried and evaluated per
  activation track; one track cannot block the other.
- Massive 429 deadlines now survive transport normalization into durable state;
  migration downgrade deletes both shadow close and shadow quote lanes before
  removing discriminators; the legacy unknown-market message is preserved.
- Fresh verification: backend **1752 passed** (642.14s); focused market-data
  **223 passed**; report suite **14 passed**; frontend **578 passed**; TypeScript
  and both Vite builds pass; `git diff --check` passes.

## Independent deploy review — 2026-09-01 (Claude, read-only)

- Scope: review-fix commit `0d3ea22` at branch HEAD `ab111f1`, verified
  against the binding spec/plan. Areas: Yahoo history identity, per-track
  German/US gate independence, report+instrument-map audit hash binding,
  active-coverage recompute, duplicate/adjustment-basis blockers,
  shadow-safe migration downgrade, Massive backoff persistence.
- Findings: **0 BLOCKER, 0 SHOULD-FIX.** All eight claimed corrections are
  real, wired end to end, and pinned by non-vacuous tests (audit
  wrong-hash fails the gate; downgrade shadow-quote deletion asserted by
  row count; zero-active-denominator rejection persists typed state).
- Watch item (non-blocking, activation-time only): the grouped gate
  demands 95% current-active coverage on every trading day of the 2-year
  window; several recently IPO'd tickers in the active set at once could
  hold the gate at exit 2 on pre-IPO days until the chatter set rotates.
  Visible in `active_coverage_gaps`; amend the gate then if it ever bites.
- Verification at `ab111f1`: backend **1753 passed** (632.45s); frontend
  suites all pass (exit 0; Radar project 175); both Vite builds pass.
- Verdict: **clear to deploy in legacy/shadow mode.** Activation flags
  stay legacy until the operator gates above are walked.
- 2026-09-01 (post-review): branch merged fast-forward into `dev_personal`
  and `main` at `c3a0837`, both pushed; Michi deployed via `update_coc.sh`
  (script runs `flask db upgrade` + `npm ci`/build; no new pip deps).

## R6 reference capture — 2026-09-01 (operator gate 1 CLOSED)

- Michi directed the German rollout to proceed; downloads authorized in
  session ("Yes go").
- Captured and frozen as contract supplement **§3.5/§3.6 + rulings
  R12–R16**: DBAG Xetra file (5,106 rows, SHA
  `969b4b93…`), DBAG Börse Frankfurt "BF" file (56,275 rows incl. 4,077
  US-ISIN CS, SHA `63472e31…`) — both public, no terms wall — and the
  Tradegate BSX A–Z crawl (27 pages, 6,485 unique ISINs, raw SHA
  `d3cfa341…`, parsed SHA `594879b1…`; site authority = Tradegate
  Exchange GmbH per imprint). Join evidence: 6,419/6,485 resolve uniquely
  (zero conflicts, equities-only, 66 unmappable ≈ 1%).
- Key deviations ruled: R12 Frankfurt file REQUIRED (Xetra alone lacks US
  mnemonics); R13 XGAT symbol/type derived by ISIN join, unresolvable →
  excluded → refusal-only; R14 Tradegate list is equities-only (no ETFs);
  R15 XGAT currency EUR; R16 completeness floors (2,500/25,000/3,000 +
  7-day staleness + every crawl page non-empty).
- Implementation: `features/radar/reference_universe.py` (parsers,
  completeness gates, catalog builder), daemon `_scheduled_mappings`
  shadow/active branch now BUILDS OpenFIGI generations from these
  catalogs (R6 refusal replaced; incomplete reference / provider outage
  writes nothing and logs loudly). Sanitized fixtures with the real
  153-column header.
- Tests: 23 new reference-universe + 3 new daemon tests; focused set
  128 passed; full radar set **1103 passed** (483s).

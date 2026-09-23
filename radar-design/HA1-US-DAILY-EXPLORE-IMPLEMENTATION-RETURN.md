# HA1 US Daily Explore — implementation return

2026-09-15 · Assignment HA1-US-DAILY-EXPLORE-IMPLEMENT · Radar Implementer (Claude Fable 5.1, owner-dispatched).

**Status: candidate implemented and DB-free/frontend verified; target-bound API, measurement and actual-app visual gates OPEN because no authorized HA1 disposable target exists in this environment.** Not committed, not pushed, not deployed. Reviewer/QA not dispatched. Subagents: none.

## Git and ownership

- Workspace: `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-ha1-us-daily-explore`
- Branch: `codex/radar-ha1-us-daily-explore`; base and current HEAD `1ac39fe4e1a5dd7d04830e96a96563183687b447` (created this session; no collision existed). No commits, no upstream.
- Carried: the 22 manifest documents, SHA256-equal to the planning source; planning source, its preview artifacts, main checkout, other worktrees, B1C DB/5021 and the 3399/5033 promotion target untouched.
- Exact dirty ownership: `radar-design/HA1-US-DAILY-EXPLORE-LEDGER.md`, section "Implementation record". In short: new backend `features/radar/analysis_contract.py`, `features/radar/analysis.py`, `features/radar/routes/analysis.py`; modified `features/radar/routes/__init__.py`; new tests `tests/ha1_unit/test_analysis_contract.py`, `tests/ha1_unit/test_analysis_reader.py`, `tests/test_radar_analysis_api.py` (gated); new frontend `static/radar/src/hub/{analysisTypes,analysisApi,analysisQueries}.ts`, `Analysis.tsx`, `AnalysisChart.tsx`, `analysis.css`, `analysisFixtures.ts` and four test files; modified `navigation.ts`, `Hub.tsx`, `queries.ts` and their tests; new `scratchpad/ha1/{local_runtime,probe_analysis,verify_preview}.py`; continuity notices in root and radar `HANDOFF.md`; `radar-design/artifacts/ha1/implementation-evidence.md`; this return. `npm ci` installed node_modules from the unchanged lockfile.

## What was built (SPEC sections 3-7)

- **Contract** (`analysis_contract.py`, pure): strict repeated-key-aware query validation (`unknown_query`, `duplicate_query`, `missing_query`, `invalid_id`, `invalid_date`, `reversed_range`, `range_too_long`, `range_not_completed`); `default_range` = last seven completed UTC days; `price_days` with observed/missing/invalid/identity_unverified states, reasons, provenance, regime tuple, modeled calendar hints for the seven evidenced MICs, `interior_missing` by set membership (adjacent two closes -> `[]`), per-window first/last, `official_completeness: unknown`; `chatter_days` with 96 UTC slots per represented stored source, ok/truncated counted, missing/absent/invalid excluded, observed-zero vs partial-zero vs unavailable, per-source config versions/transition, cross-day transition flag, bare-reddit/child overlap -> pooled `null` + `overlap_ambiguous`, pre-first_seen slots excluded individually, 64-source / 43,008-row limits -> `analysis_limit`. No mention_z, no returns, no split inference.
- **Reader** (`analysis.py`): `resolve_company` (2 SELECTs, LIMIT 2 candidates, 404/409/422, no `.first()`), `read_company` (4 data SELECTs: company, instrument, closes LIMIT 8, buckets LIMIT 43,009; identity revalidated every call, 409 `identity_changed` never retargets; `fetched_at <= read_start`; statement-scoped `SET STATEMENT max_statement_time=2 FOR` on MariaDB, hint on MySQL, none elsewhere; 5 s reader deadline; DBAPI timeout errno 1969/3024 -> 503 `analysis_limit`, other store errors -> 503 `analysis_unavailable`, session rolled back; payload exactly SPEC 4 plus additive `reason`, `identity_excluded_slots`, merged `warnings`).
- **Routes** (`routes/analysis.py`, `login_required`): `GET /radar/api/analysis/resolve?ticker=` and `GET /radar/api/analysis/company/<id>?instrument_id=&from=&to=`; stable `{error, code}` refusals; no SQL in messages.
- **Hub**: `#analysis`, `#analysis/<TICKER>`, `#analysis/<TICKER>/<company_id>/<instrument_id>` with `analysis_from`/`analysis_to` outside the board selection; resolver replaces (not pushes) the canonical link; range changes push; Back/refresh restore; invalid dates show the typed values and fetch nothing; stale IDs fail visibly; search on Analysis re-resolves; nav item "Analysis"; top bar says "US primary · USD · retrospective"; board polling/expiry/minute-read disabled on Analysis via a new `enabled` input to `useBoard` (other pages unchanged); stale-board banner suppressed on Analysis; Analysis session expiry clears the hub cache and shows Signed out. Page: heading with permanent Retrospective label, company/range controls, identity strip, independent price/chatter coverage panels, two aligned SVG panels (dots, runs joined only within one regime across modeled-closed days, shape-coded missing/invalid/unverified markers; bars with hatched partial, labelled zero tick, `n/a`/`?` gaps), keyboard day buttons (roving tabindex, arrows/Home/End, 44 px), selected-day detail with per-source table, full accessible daily table, provenance rail with this read's warnings; failed refresh keeps the last answer labelled with its read time; 8 s fetch timeout, no retry/polling/refocus, 60 s stale, 5 min GC, no placeholder; rail at >=1100 px, stacked below; stacked columns at 760 px; `.rh` tokens only.

## Evidence (my execution; details in `radar-design/artifacts/ha1/implementation-evidence.md`)

| Check | Result |
| --- | --- |
| `py -3.12 -m pytest --confcutdir=tests/ha1_unit tests/ha1_unit -q` | 95 passed (contract 65 + DB-free reader 30); first run failed on the missing module as expected |
| `navigation.test.ts` before/after routing | 6 failed -> 38 passed |
| Focused Vitest (9 files incl. Chatter/ChatterWorkspace) | 210 passed |
| Whole radar Vitest | 777 passed, 28 failed in `pending.test.tsx`; identical 28/30 failure at the untouched base in the planning-source worktree -> pre-existing |
| `npx tsc --noEmit` / `npm run build` | clean / passed |
| `git diff --check` | clean |
| `scratchpad/ha1/local_runtime.py test` without target | refused before any import or SQL |

Not executed (no target): `tests/test_radar_analysis_api.py` (C11 auth, C02 transport, C01 transport, C13 statement count/EXPLAIN, C14 timeout/session hygiene/recovery), `probe_analysis.py` (C13/C14 zero/typical/43,008-row fixtures, 20 warm + 1 cold, p95, bytes, allocation, 43,009th refusal), `verify_preview.py` (C15/C16 five viewports, keyboard, refresh/Back, DE-entry label, invalid window, stale link). No PNG exists to inspect.

## Findings and limitations

1. **OPEN gate — no authorized HA1 target (environment).** Both `RADAR_DESTRUCTIVE_TEST_TARGET` and `RADAR_DESTRUCTIVE_TEST_REGISTRY` were unset; only protected `localhost:3306` was listening; the old `127.0.0.1:3399` promotion MariaDB was not running and is not authorization anyway. Consequence: MariaDB statement-timeout behaviour, pooled-connection hygiene, EXPLAIN plans, row/byte/latency budgets and every actual-app screenshot remain unproven. Nothing was provisioned or registered.
2. **Pre-existing test failure, medium, out of scope:** `static/radar/src/hub/pending.test.tsx` fails 28/58 at the base itself (reproduced in the planning-source worktree, not by this change). Not diagnosed; listed for the Reviewer/Mastermind.
3. **Calendar** is modeled only (NYSE rules, seven known MICs; other MICs -> `unknown`). A close on a modeled-closed day stays observed with a warning. Official completeness always `unknown`.
4. **Identity**: current mapping applied retrospectively; `first_seen` is a conservative boundary (same-day precision disclosed), never a lineage. Old canonical links with changed mapping return 409 and the page says so; only search re-resolves.
5. **Config/source**: historical configured-source completeness is always `unknown`; config transitions and the bare-reddit overlap are surfaced, never pooled across.
6. **Adjustment**: the `split` stamp is shown as a declared basis with an explicit warning; no return, split or comparability claim.
7. **Additive payload fields** (`reason`, `identity_excluded_slots`, reducer warnings merged) go beyond the SPEC's literal type; the Reviewer should confirm acceptance.
8. **Shell cost**: `hub_page` still embeds the board on first paint; Analysis suppresses further board reads but the cold shell cost is unchanged and unmeasured here (SPEC 7 disclosure).
9. `queries.test.ts` gained non-JSX `createElement` tests to stay a `.ts` file; `queries.ts` gained the `enabled` input (default true) — no behaviour change for existing pages, covered by the passing Chatter/ChatterWorkspace/Hub suites.

## Actions taken

Local application/test/document edits in the candidate only; `npm ci`; test/build runs. No commit, push, merge/rebase, deployment, migration, provider/production access, service change, capture change, registry/provisioning, or B1C/5021 use.

## Requested decision and recommendation

Assess this return. Recommended next bounded action: one owner-selected independent Reviewer with QA duties on this candidate, who is given (or told the absence of) an authorized HA1 target so the gated suite, `probe_analysis.py` and `verify_preview.py` can be executed and the PNGs inspected; if no target can be authorized, the Reviewer reviews the code with C11/C13/C14/C15/C16 explicitly open. No Deployer authorization is requested.

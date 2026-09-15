# MD-SELECTED-PRICE-REVIEW-1 — independent Reviewer / QA return

2026-09-15. Radar independent Reviewer / QA (Claude Opus 5), one reviewer, no subagents. Return to the Mastermind.

## Verdict

**No blocker for the default-off, deterministic local candidate.** The selected US 1D/1W chart, aligned chatter/retained tone, coherent fallback and bounded acquisition match SPEC/PLAN in the paths reviewed, and the worker's key claims reproduce. One **moderate** finding (F1) contradicts an explicit PLAN Task 2 requirement for non-gunicorn launchers and must be fixed or explicitly ruled before `RADAR_SELECTED_PRICE_YAHOO_ENABLED` is used under a file-path launcher. Three **low** findings (F2-F4) are contract-precision issues. D5 and D14 were investigated: **no defect**. Nothing here establishes live-provider, MariaDB or topology readiness.

## Workspace and Git

- Candidate `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts`, branch `codex/radar-selected-price-charts`, base = HEAD `daadf3868caedcb5db858378e919cba68b735f8a`, uncommitted, nothing pushed.
- Fingerprint recomputed read-only at start: `218c1a53aaef9625dd9ec6f8b2c6125d8431b3c42daad732a9181a8b2f612159`, 16 modified / 27 added / 5 generated, 0 mismatches. Final verification is recorded in the copy/paste prompt below.
- `git diff --check` clean. Scratch rebuild of the Radar bundle is byte-identical to the candidate `static/radar/dist` (5 files), so the generated assets correspond to the reviewed sources.

## Findings

### F1 — Moderate: the spawn fetch child re-executes a file-path launcher's top level, bootstrapping the Flask app

- **Where:** `personal_apps/features/radar/price_chart_acquisition.py:83-101` (`spawn_launcher`, `multiprocessing.get_context('spawn')`). Affected launchers: `personal_apps/app.py:1-185` (unguarded bootstrap: `load_dotenv(override=True)` :12, `db.init_app` :46, `from models import *` :49, every blueprint :52-66) with its own documented entry `if __name__ == '__main__'` :188-196; tracked `personal_apps/scratchpad/b1c/serve_b1c.py:5` (`from app import app` at top level).
- **Contract:** PLAN Task 2: "Child import must not bootstrap the Flask app or inherit pooled DB connections." SPEC §6: child "with no Flask context".
- **Reproduction (fresh):** `radar-design/artifacts/md-selected-price-review-1/d17_spawn_main_probe.py` → `d17_probe.json`. With a file-path `__main__`, the production launcher's child (pid 11196) ran the script's unguarded top level as `__mp_main__`; with a `-c` `__main__` it ran none. Python's spawn preparation re-runs a path-based main module in every child; only module-named mains (`python -m …`) and file-less mains are skipped.
- **Impact:** under `python app.py` or `serve_b1c.py` with both flags on, every acquisition child imports and configures the whole app (dotenv override, SQLAlchemy engine config, all models/blueprints) before fetching; startup time counts inside the 6 s deadline. No pooled connection is inherited (spawn), and nothing at app import opens a connection or starts work (app.py:194-195), so this is not a data-safety failure. Production `gunicorn` (pip console script with guarded main), `.claude/launch.json` `flask run`, `python -c "from app import app; …"` and `python -m pytest` are unaffected. The worker's "no heavy modules in child" proof ran under pytest (module-named main) and does not cover file-path launchers; D17 recorded this as a limitation rather than meeting the PLAN requirement. Flags default off, so there is no current runtime exposure.
- **Narrow remedy (choose one):** (a) before starting a child, refuse acquisition in-process (state `unavailable`, reason/counter `launcher`) when `sys.modules['__main__']` has a `__file__` and no module `__spec__` name, with one test using a file-path main; or (b) start the child as `sys.executable -m features.radar.price_chart_fetch` via `subprocess` with pipes and an explicit minimal environment, keeping the existing supervisor/deadline/reap semantics (also resolves F2); or (c) an explicit Mastermind ruling that provider acquisition is supported only under gunicorn/`flask run`/`-c` launchers, recorded as a release carry.

### F2 — Low: the fetch child inherits the web process's whole environment, including dotenv secrets

- **Where:** `price_chart_acquisition.py:91-100` (spawn inherits `os.environ`); `personal_apps/app.py:12` loads `.env` into `os.environ` with override; `price_chart_fetch.py:9-12` says the child does not have "credentials from the environment".
- **Reproduction (fresh):** `d17_probe.json` file mode: the child saw the sentinel variable the parent set before spawn.
- **Impact:** DB password, secret key, VAPID private key and provider keys are present in each child's environment. Existing mitigations hold: `trust_env=False`, all cookies refused, fixed host, no redirects (`prices/yahoo.py` bounded mode), so none are sent. SPEC §6 "no … inherited requests session or credentials" is met for transmission but not for presence; the module docstring overstates it.
- **Remedy:** correct the docstring/return wording and either accept presence by ruling, or give the child a minimal environment (F1 remedy b).

### F3 — Low: a failed refresh keeps the last chart for the query key, not for the same identity/window

- **Where:** `personal_apps/static/radar/src/hub/ResearchContent.tsx:179-225` (`SelectedChartBody` draws retained `data` beside the error notice at :206-218); `hub/queries.ts:768-805` (key = ticker, market, sources, span).
- **Contract:** SPEC §8 "On endpoint failure retain a previous response only for the exact same identity/window/selection with visible age/error".
- **Reproduction (static):** TanStack keeps a query's last successful `data` when a refetch errors; nothing compares the retained answer's `window.session_dates`, `partial` or `identity.fingerprint`. Example: a 1D answer for Tuesday's live session (header "Current session so far · Tue 15 Sep", end label "now HH:MM") remains drawn after a refresh fails past 04:00 ET Wednesday, or after a remap whose first response failed.
- **Impact:** low — the amber notice states when the chart was answered, but the chart's own "now" end label and "current session" title are stale.
- **Remedy:** retain only while the answer is younger than the 15-minute stale limit (otherwise show the chart-local retry), and suppress "now"/"so far" wording while an error notice is shown.

### F4 — Low: ops worker multiplier and start-time fields do not describe the actual topology

- **Where:** `price_chart_acquisition.py:427-429` (`configured_web_workers` reads only `WEB_CONCURRENCY`), :185 and :437 (`process_started_at` is the coordinator's creation time and null before the first acquisition); `hub/Admin.tsx` omits the multiplier when null.
- **Contract:** SPEC §6 "Report configured worker multiplier"; SPEC §7 "process ID/start time".
- **Impact:** the release-attributed production command is `gunicorn --workers 2` (CLI flag, cited in `MD-SELECTED-PRICE-EVIDENCE-1-RETURN.md:139` from the PERF1 ledger), so production would report no multiplier; the "process started" time is not the process start. Topology itself remains a release carry.
- **Remedy:** label the field as coordinator start (or capture module import time), and read an explicit documented worker-count setting or display "unknown" in Admin with the per-worker note.

### Optional polish (not findings)

- P1 `price_chart_acquisition.py:246-247`: the "(its Retry-After was capped at one day for display)" backoff reason is unreachable, because `unavailable` takes precedence for the whole capped period.
- P2 `SelectedPriceChart.tsx:192-194`: the 1W tick for today's partial session is filtered when it lies within 70 units of the end (no "Tue 15 Sep" tick in `ordinary-research-1440.png`); the header still states the dates.
- P3 The chart has no standing identity caveat like HA1's "company record is a conservative boundary"; it warns only when pre-identity rows exist. Low value for 1D/1W windows.
- Disclosed UX tradeoffs (continuous 1W closed time, dominant partial outlines, top-anchored zoom captures) were seen in the screenshots and are not re-raised, per the ruling.

## Focus questions

- **D5 — no defect.** `TickerUniverse.symbol` is the social identity, and its `first_seen`/`delisted_at` exist for symbol reassignment (`models.py:497-526`); `RadarInstrument` answers only which instrument supplies a price (`models.py:546-553`). Bucket rows are keyed by ticker, not instrument. No US mapping history exists (`RadarMappingGeneration` is German-only, `models.py:1033-1040`; searched `mapped_at` writers touch only `market='de'` rows, `instruments.py:403-423, 425-435, 643-679`). The implementation uses the company floor for chatter (`price_chart_reader.py:250,415`; `price_chart_contract.py:716,754`) and the mapping floor for price (`price_chart_contract.py:549,648`). Applying `mapped_at` to chatter would erase genuine company chatter after any remap. Recommend the Mastermind record this reading of SPEC §5's "company/mapping identity floor".
- **D14 — no defect.** `price_chart_fetch.py:38-51,62-64` parses Retry-After (seconds or HTTP-date); `_throttle` (`price_chart_acquisition.py:357-369`) sets `_unavailable_until` to the full value when it exceeds 86,400 s. `_refusal` (:233-262) checks it before backoff, cooldowns and starts, so no child starts early. The 86,400 s cap applies only to the displayed `retry_after_seconds` (:242); the client's next poll receives `unavailable` again without provider I/O. The value is applied at settle time, after receipt, which is conservative. `test_acquisition.py:196-222` asserts `unavailable` at +86,400 s and admission only at the full +100,000 s (passed fresh). Residual: process scope (restart or another worker) is SPEC-accepted.
- **D17 — see F1/F2.**

## P01-P09 assessment

| ID | Reviewer assessment | Basis |
| --- | --- | --- |
| P01 | PASS | Identity re-resolved per request before admission/reads (`price_chart_reader.py:214-255,397`); both caches keyed by fingerprint; unknown form refused upstream; mapping untouched; route codes; fresh 139 unit passes |
| P02 | PASS | `window_for` (`price_chart_contract.py:184-229`) matches SPEC §2 incl. 09:29/09:30 1W boundary, 16-day bound; fresh window tests pass. Calendar is modeled only |
| P03 | PASS | Bars placed at end, provisional at receipt, breaks on null/missing/state/session (`price_chart_contract.py:451-480`), off-grid omitted and disclosed, unknown adjustment; independent-instant geometry (`selectedPriceGeometry.ts`); tests pass |
| P04 | PASS | Slot reduction/unknown-not-zero/overlap/config flags (`price_chart_contract.py:689-830`), tone reconciled to new totals with unavailable on expiry/conflict/failure (:833-868); client refuses non-reconciling tone. Parity with `chatter_tone` is SQLite-tested, a maintained duplication |
| P05 | PASS with F3 | One coherent dataset, source chosen by latest event, pre-mapping/future/shadow rows excluded, overflow refuses; receipt-age staleness; stale switch in saved browser run |
| P06 | PASS locally; F1/F2 open | No provider I/O or process creation on the request thread; one child; 6 s deadline; terminate/kill/reap; quarantine; 512 KiB bounds; 10/60 s, 60 s per key; ladder + Retry-After (D14). Fresh real children: hang terminated at 6.219 s, oversized cut at 0.859 s, normal 0.656 s |
| P07 | PASS (DB-free); F4 low | Flag-off 404 before parsing; `login_required` like `ticker_detail` (`routes/api.py:783-785`) plus app member gate; only three query keys; shell sends only the chart flag; ops admin-only and non-creating. DB-backed ops key-set test not run |
| P08 | PASS on fixtures (SAVED) | 57 cases/744 checks/0 failures recounted from `results.json`; five screenshots viewed across both surfaces, 1440/390/320 and real 200% zoom; bundle reproduces byte-for-byte |
| P09 | PARTIAL, disclosed | ≤6 cold SELECTs, statement-scoped timeout text, sentinels, SQLite syntax; no MariaDB timeout/cancel/plan evidence; live request form unverified |

## Checks executed by the reviewer

All from `personal_apps` unless noted; logs in `radar-design/artifacts/md-selected-price-review-1/logs/`.

1. Git branch/HEAD/status/diff and `git diff --check` → as above, clean.
2. Read-only fingerprint recompute (scratchpad script mirroring `fingerprint.py`; the original was inspected, not run) → match, 0 mismatches.
3. `py -3.12 -m pytest tests/selected_price_unit --confcutdir=tests/selected_price_unit -q -p no:cacheprovider` (evidence file redirected to the review directory) → 139 passed.
4. `py -3.12 -m pytest tests/test_radar_chatter_tone.py tests/test_radar_yahoo.py tests/ha1_unit --noconftest -q -p no:cacheprovider` → 269 passed, 1 skipped, 3 failed (the recorded pre-existing `test_daily_closes_*`).
5. `npx tsc --noEmit` → exit 0.
6. `npx vitest run -c vite.radar.config.ts <11 affected files>` → 180 passed.
7. `npx vite build -c vite.radar.config.ts --outDir <scratchpad> --emptyOutDir` → exit 0, hashes identical to candidate dist.
8. `py -3.12 ../radar-design/artifacts/md-selected-price-review-1/d17_spawn_main_probe.py` → F1/F2 reproduction.
9. Saved `browser/results.json` recount and five screenshots viewed.

## Carried worker evidence (not re-executed)

Whole Radar Vitest 847 passed / 28 pre-existing `pending.test.tsx` failures; baselines before edits; built-hub browser run 3 (57 cases, 744 checks, 109 PNGs); original `child-lifecycle.json`; carry manifest 23/23. All remain worker-attributed.

## Not executed / limitations

No live Yahoo request (period1/period2 form, closed-session/holiday/throttling behaviour). No MariaDB runtime (statement timeout, cancellation, query plans, pool). No DB-backed suites (`test_radar_operations_api.py` key-set change, hub page, API, detail). No gunicorn or multi-worker topology (production launcher safety is inference from the standard console-script shape). No new browser run. Provider usage conditions are not established. These remain release carries, not passes.

## Actions and protection

Reviewer changed no application, test, build or carried document other than the two short notices below. Written: this return; `radar-design/artifacts/md-selected-price-review-1/` (evidence.md, d17 probe script/result, child-lifecycle-review.json, logs); current notices at the top of candidate `HANDOFF.md` and `radar-design/MD-SELECTED-PRICE-LEDGER.md`. Scratch only: `fp_readonly.py` and a scratch bundle under the session scratchpad. No commit, push, merge, deploy, flag activation, DB provisioning/reuse, live provider or production access. Source workspace, main/other worktrees, B1C/5021, promotion/5033, databases 3306/3399, HA1/3461 and `C:/Users/michi/.radar-ha1-local-qa` untouched. No server or port opened (the D17 probe uses IPC only); no process left running.

## Requested decision

Rule on F1 (narrow correction a/b, or launcher-restriction ruling c), F2 (wording plus acceptance, or minimal-env child), F3 and F4 (bundle into the same small correction, or defer as documented polish), and record the D5 interpretation. If corrections are ordered, re-review only the changed behaviour. Live activation stays a separate owner/Deployer decision with the carries above.

# Hub promotion release candidate — 2026-09-14

Owner explicitly requested finishing the bookmark correction and deploying. That supersedes earlier deployment-not-authorized notices for this scoped promotion. Root /radar/ mounts the hub; /radar/hub/ remains alias; /radar/legacy/ retains the board. Valid hashes override legacy t; invalid hashes fall back to valid t; filter-only legacy root links now open Human Chatter, while bare root opens Overview.

Fresh correction evidence: new regression failed before correction and passed after it. Frontend navigation/Hub: 58 passed. Route/auth/admin suite on the existing independently registered disposable MariaDB 10.11.14 at 127.0.0.1:3399/personal_apps_radar_human_chatter_release: 13 passed. Production TypeScript/Vite build passed. Isolated actual-app desktop 1440x1000/mobile 390x844 at port 5033 passed root/alias/legacy, company links, invalid-hash fallback, filter-only links, refresh and return link checks. Screenshots visually inspected. Evidence: radar-design/artifacts/hub-promotion-preview/result.json and root/filters/legacy PNGs. Earlier port-5032 preview script failed login and is not passing evidence; the final script uses the registered DB at port 5033. B1C/5021 untouched.

Preflight verified current production root@194.164.29.97 at 83bc2bf6282b7772fbee07c1eb27cfe41760f417 and the locked backup-first /root/update_coc.sh wrapper. Older root@82.165.240.212 was read-only checked and is not this deployment target. Capture remains off; no provider/schema/ranking changes. Next: scoped commit, normal push and routine release, then production smoke. Record exact final SHA and outcome after release.

---
# Current priority — hub promotion, 2026-09-14

Owner approved the next bounded transition: make /radar/ the hub entry, retain /radar/hub/ as compatibility alias, and preserve the original board at /radar/legacy/. Check important old-only capabilities and preserve bookmarks before promotion. Do not delete legacy UI in this increment. Binding: HUB-PROMOTION-PLAN.md and HUB-PROMOTION-LEDGER.md under radar-design/ (relative to root).

This isolated implementation workspace is `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-hub-promotion`, branch `codex/radar-hub-promotion`, created from `83bc2bf6282b7772fbee07c1eb27cfe41760f417`. Deployment remains unauthorized. Capture stays OFF. The Human Chatter ranking release is closed and must not be redispatched.

Implementation changes: `/radar/` and `/radar/hub/` render the existing hub; `/radar/legacy/` renders the unchanged board. Root `?t=VALID` opens the hub Human Chatter workspace, preserving supported filter context; a nonempty hub hash wins. The hub strips legacy `t` before its board API build, while Legacy Radar retains it. The hub nav links to Legacy Radar; the board returns to root with its query retained. No ranking or backend/shared-board behavior changed.

Evidence: `test_radar_hub_page.py` 13 passed; hub navigation/component Vitest 57 passed; final `npm run build` passed; `git diff --check` passed. Preview server was verified on port 5032, but its Playwright script did not persist screenshots/results; rerun `radar-design/artifacts/hub-promotion-preview/verify_preview.py` before independent review. Do not use port 5021, B1C data, production, migrations, capture, push or deployment.

---

# Current status — independent final review COMPLETE

The owner supplied the completed independent review on 2026-09-14: no material issues found; the implementation satisfies the binding Human Chatter ranking contract. Implementation and independent review are COMPLETE for this uncommitted candidate. No repeat implementation/review assignment is open.

Independent reviewer-reported fresh evidence: backend focused suite 29 passed; frontend focused suite 4 files / 125 tests passed; git diff --check passed. The reviewer reported preserving all dirty files and making no code or documentation changes. The Product Overview planner verified current Git state and read the handoff/plan/ledger/return, but did not rerun those tests or independently reproduce the reviewer results. The production build/typecheck pass remains implementer-reported evidence, not an independent review build.

Residual verification limits remain explicit: direct/shared producer, API and parity integration could not safely run because only protected localhost:3306/personal_apps was available. Do not bypass the gate, use B1C's database or create an improvised target. No safely isolated actual-app preview was available, so no screenshots exist. The 6.5-hour price-period assumption remains unaudited and outside scope. Review completion does not mean these gates passed or that release readiness was demonstrated.

Current candidate: C:/Users/michi/Desktop/CodingStuff-worktrees/radar-human-chatter; branch codex/radar-human-chatter; verified HEAD/base a161dc3793aede70b31e1cb1cf851607f918881f. Implementation and planning changes remain uncommitted. Git's ignore-file/.pytest_cache permission warnings limit untracked enumeration. Existing dirty implementation and historical B1C files were preserved; this status reconciliation changes planning documents only.

Product recommendation: owner approval for a scoped local commit of the reviewed candidate and its planning evidence. Commit, integration, push and deployment are NOT authorized by this record. Keep the integration/visual gaps visible for any later integration/release decision; no automatic test/review loop. Historical analysis remains next after disposition of this candidate. Capture remains OFF. No migrations, root promotion, B1C/PERF3 changes, port-5021 use or production access.

Contract unchanged: default membership/order is independent of price, quotes, freshness, direction and session; price remains visible and explicitly sortable within the selected candidates; existing mention_z with no new score/weights/boosts/predictive claims; original /radar/ defaults unchanged.

This notice supersedes older open-review, worktree-creation and next-action instructions below. Detailed historical evidence is retained.

---
# Current priority — 2026-09-14, Human Chatter ranking

## Implementer update — 2026-09-14

Workspace: `C:\\Users\\michi\\Desktop\\CodingStuff-worktrees\\radar-human-chatter`; branch `codex/radar-human-chatter`; HEAD/base `a161dc3793aede70b31e1cb1cf851607f918881f`. The copied planning artifacts remain dirty and planner-owned. Implementation-owned dirty files are the Radar board sort, Hub request/copy/type changes, focused backend/frontend regression tests, and `radar-design/HUMAN-CHATTER-RANKING-RETURN.md`.

Completed implementation: `chatter` sorts finite `mention_z` before the top-N cut, descending by default, then finite mentions and ticker; missing/nonfinite scores are last and never zeroed. The Human Chatter route derives `sort=chatter&dir=desc` for its board request while leaving other hub routes and `/radar/` defaults alone. The shared-board key includes that sort, so a legacy/default bootstrap cannot seed the chatter cache entry. Alternate workspace sorts only reorder the returned candidates; reset is “Unusual activity.” The page names Human Chatter, explains the price-independent ranking, and distinguishes all-measurable nonpositive, all-unknown, and mixed baseline coverage honestly.

Fresh verification: backend pure sort/key/query suite `29 passed in 0.33s`; affected frontend suites `125 passed` (Hub, queries, Chatter, ChatterWorkspace); `npm run build` passed (TypeScript plus both Vite builds); `git diff --check` passed. The mixed-state test failed against the prior implementation, then passed after its targeted correction.

Integration limitation, not a product failure: the requested producer/shared/direct/parity run stopped at its safety gate on `localhost:3306/personal_apps` (`42 passed, 139 errors`), before destructive setup. No `RADAR_DESTRUCTIVE_TEST_TARGET` or `RADAR_DESTRUCTIVE_TEST_REGISTRY` environment registration exists. Do not bypass this, use B1C's preview/database, or seed a database. No safely isolated actual-app preview was available, so no screenshots were captured; preserve port 5021. The reported universal 6.5-hour price assumption was not audited; quote/currency/freshness/session fields remain visible.

No subagents, deployment, push, migration, capture activation, root promotion, provider change, B1C work, or historical-analysis implementation occurred. Independent final review is complete; next action is the owner decision on a scoped local commit. Do not begin a repeat review cycle.

The owner approved a bounded ranking change before historical analysis. Binding scope: [HUMAN-CHATTER-RANKING-PLAN.md](radar-design/HUMAN-CHATTER-RANKING-PLAN.md); progress: [HUMAN-CHATTER-RANKING-LEDGER.md](radar-design/HUMAN-CHATTER-RANKING-LEDGER.md). For root-level readers these files are under radar-design/.

Human Chatter will select and rank unusual discussion independently of price, before top-N truncation. Price remains visible and explicitly sortable. Use existing mention_z provisionally; no new composite formula or predictive claim. Preserve original /radar/ behavior and PERF3 shared-board architecture. Implementation and independent review are COMPLETE with the recorded verification limits; owner decision on a local commit is pending. No agents have been dispatched by the planner.

Historical analysis remains the next new feature after this bounded interruption, ahead of portfolio/news. Future HA captures must identify the ranking policy and selection; legacy divergence selections and new chatter selections are different populations and must not be silently pooled or relabelled. No HA implementation is included here. Use the actual app for future UI work, not a separate interactive prototype; this supersedes older prototype instructions.

B1/PERF3/B1C remain complete and deployed at 200c51cc402e053575bf9e0008db597ea27b36a5. Bars are owner-confirmed; tone latency is accepted, not a passed target. Capture remains OFF. No push, deployment, migration or root promotion is authorized. Preserve main checkout, PERF3 files, other worktrees, port 5021 preview and the untracked missing-bars-local.png investigation screenshot.

This notice supersedes historical next-action and assignment text below, not the recorded evidence.

---
## Planning continuity

Workspace: C:/Users/michi/Desktop/CodingStuff-worktrees/radar-b1c. Branch: codex/radar-b1c. Last verified HEAD: a161dc3793aede70b31e1cb1cf851607f918881f. This synchronization is uncommitted documentation owned by the Product Overview planner. No application code or tests were changed or executed.

Next implementer: create a separate isolated worktree from the verified HEAD and explicitly copy the current ranking plan/ledger and updated handoff/roadmap/history plan from this workspace, because uncommitted planning files do not follow a Git worktree automatically. Verify current Git evidence before proceeding. Do not modify the running B1C workspace. Read the ranking ledger and begin its first open task.

Planner-owned dirty files: HANDOFF.md; radar-design/HANDOFF.md; radar-design/ROADMAP.md; radar-design/HISTORY-ANALYSIS-PLAN.md; new radar-design/HUMAN-CHATTER-RANKING-PLAN.md and HUMAN-CHATTER-RANKING-LEDGER.md. Unrelated untracked radar-design/artifacts/b1c-resume/missing-bars-local.png remains untouched. Git ignore/.pytest_cache permission warnings limited untracked inspection. No fresh runtime, production or statistical validation is claimed.

---
# Current status — 2026-09-13, B1C live and owner confirmed

B1C deployed at 200c51cc402e053575bf9e0008db597ea27b36a5 with explicit owner authorization. The owner subsequently confirmed the chatter bars work; the apparent missing-bars issue was resolved by scrolling. Investigation cancelled, no product fix required. Busy-ticker tone latency is accepted for this iteration, not a passed performance target. Capture remains OFF; /radar/hub/ remains alongside /radar/; no root promotion.

Deployment evidence and exact operational state: root HANDOFF.md. Prior pending-release, unimplemented-tone and latency-blocker statements below are historical and superseded by this notice. Preserve historical evidence; do not redispatch completed work.

---
# CURRENT — B1C deployed with owner authorization

On 2026-09-13 the owner explicitly requested deployment ("Ok so lets deploy"). Published normal fast-forward origin/main and deployed 200c51cc402e053575bf9e0008db597ea27b36a5 with /root/update_coc.sh in routine mode. Main local checkout and PERF3 worktree were not modified.

Release unit radar-b1c-release-200c51c succeeded at 23:32:31 Europe/Berlin. Fresh backup db_2026-09-13_2329.sql.gz preceded release. All six application/ingestion/producer services active; migration head unchanged b7e3f9c1a2d4. Public hub returned expected unauthenticated 302. Shared boards on; capture unset/off. Root route not promoted. Gallery included in candidate.

Read-only actual MariaDB smoke: AAPL 24h/1D detail plus tone returned successfully, 664ms including detail construction in a fresh Python process. This is one correctness smoke, not a latency benchmark or authenticated browser verification. Existing owner-accepted latency limitations stand. Local preview remains on port5021.

Immediate next action: owner reviews live B1C at https://mgemmel.viewdns.net/radar/hub/. No further deployment required. Historical boundaries below predate explicit authorization.

---
# CURRENT — owner accepts B1C latency limitation

The owner accepted the measured busy-ticker tone latency for now: "if i find it annoying i will call it later". This supersedes the latency-blocker ruling below. No further tone-query optimization is required for this packet unless the owner reports a problem or new evidence warrants it.

The measured100ms median/200ms p95 targets remain unmet; they are waived for this iteration, not reported as passing. Existing evidence remains unchanged: added tone calculation median280–500ms on the local20k-event fixture, not full browser load time or production/MariaDB proof. Other disclosed verification limits remain as recorded.

Reviewed implementation is5297af6. Local preview remains http://127.0.0.1:5021/radar/hub/. This acceptance does not authorize deployment, push, merge main, capture enablement or root promotion. Preserve main/PERF3 and the running local app. Any later release preparation must retain the documented evidence limits.

---
Historical review follows.
# CURRENT — B1C Codex local review, 2026-09-13

This notice supersedes earlier claims that the whole B1C packet is complete. Initial verified HEAD c97583e on codex/radar-b1c was clean. Corrections and evidence are recorded in the following local commit; use git log for its full SHA. No main checkout, PERF3 files, production services or other worktrees were modified.

## Ruling

Local owner preview may continue. Final B1C acceptance is OPEN: the required busy-ticker tone latency target fails. Do not deploy, push, merge main, promote root, enable capture, or redispatch completed B1/PERF work.

## Corrections completed this review

- Bounded tone source-bucket reads to retained48h rather than loading full chart history.
- Fixed double counting of a mismatched source so valid other-source colours survive.
- Eligibility contradictions invalidate their whole source-bin.
- Restored the price line/session context that histogram mode had accidentally removed.
- Preserved pooled gaps and valid count partitions; normal baseline shares the count scale; zero-volume intervals can be selected.
- Bullish/bearish now use independent green/red instead of inheriting cyan price tokens; SVG labels readable. Legend swatch reflects the tone mix.
- Price and histogram use matching912-unit canvases; mobile explanatory text stays pinned while plots pan together.

## Fresh evidence and limits

- Backend9 passed in4.64s, including guarded real-SQL regression cases. Helper source mismatch test failed before its correction.
- Frontend75 tests across4 affected suites passed in12.65s; after the mobile text adjustment Research17 passed in2.93s. Final production build/typecheck passed after the mobile text adjustment.
- Local authenticated actual-app checks: price path plus histogram, correct computed green/red and light axis labels, no document overflow at1440/390/320, keyboard selection/Escape and pointer interval selection. Screenshots/JSON: radar-design/artifacts/b1c-resume/. These are disposable seeded data, not live market evidence; pointer-click emulation is not a physical-phone gesture test.
- Independent read-only corrective review found no new material defect in the backend fixes or restored-price/pooling changes. The subsequent colour/sticky-text changes were directly verified by Codex, not represented as independently reviewed.
- MySQL8.0.46 rollback-only fixture probe: quiet24events, busy20,000events;20samples per span. Two SQL queries per read; max incremental heap0.729MiB, below8MiB. All reserved probe tickers absent after rollback. Preview fixtures preserved.
- Busy added tone calculation:1D median280/p95320ms;1W500/613ms;3Y461/547ms. Targets100ms median/200ms p95 FAIL. Quiet reads7–10ms. Evidence: radar-design/artifacts/b1c-tone-probe.json; executable guarded probe personal_apps/scratchpad/b1c/probe_tone.py.
- Probe measures chart_tone directly, not paired full-detail HTTP requests. It is sufficient to establish the added-work failure, NOT completion of the endpoint acceptance matrix. Target MariaDB correctness/timing for new SQL remains unverified.

## Next bounded assignment

Inspect the new aggregate query's execution plan on the registered disposable target; reduce redundant per-event/per-category aggregation while preserving duplicate-membership and conflict checks. Re-run this same bounded fixture probe after a meaningful fix, then the missing paired endpoint/target-engine gate. Do not add a daemon, cache layer, migration or reopen PERF3 without an explicit ruling. If query-only correction cannot meet the target, return the measured trade-off rather than silently weakening the target.

## Local app and continuity

Keep http://127.0.0.1:5021/radar/hub/ running. Local-only b1cadmin / b1c-local-only; database personal_apps_radar_b1c. Restart from personal_apps using `py -3.12 scratchpad/b1c/serve_b1c.py`; launcher refuses a non-B1C database. Logs .b1c-preview.stdout.log/.stderr.log stay local. Do not seed or run destructive suites just to resume.

Gallery is preserved in the candidate; no remote action performed. Preserve protected owner files and historical evidence. Root HANDOFF.md is current; radar-design/HANDOFF.md contains old history below its pointer.

---
Earlier return is historical where it differs.
# HANDOFF — Radar B1C local implementation

This worktree is the completed local B1C candidate. Read `radar-design/CLAUDE-B1C.md`,
`radar-design/B1C-IMPLEMENTATION-PLAN.md`, `radar-design/B1C-LEDGER.md`, and
`CODEX-RETURN-B1C.md` before continuing. Git and the return packet are the source
of truth if this text ever differs from an older planning note.

## Exact workspace

- Worktree: `C:\Users\michi\Desktop\CodingStuff-worktrees\radar-b1c`
- Branch: `codex/radar-b1c`
- Starting deployed/PERF3 base: `ad531ef6d697eac7c67179a40d7fca56812095fd`
- Carried Claude commits: `020baee`, `df04fcf`
- Final integration SHA is recorded in `CODEX-RETURN-B1C.md` after the local commit.

## Outcome

The candidate now contains Claude’s B1 dark Human Chatter workspace and live gallery,
the ruled descriptive measured-price wording fix, and a B1C opt-in tone extension.
The hub requests `tone=1`, renders a retained-evidence stacked histogram, and keeps
the old `/radar/` detail/area path backward compatible. Tone bars use exact existing
chatter totals, recorded judgments only, and a 48-hour retained evidence horizon.

## Local preview

- URL: `http://127.0.0.1:5021/radar/hub/`
- Account: `b1cadmin` / `b1c-local-only`
- Database: disposable `personal_apps_radar_b1c`, protected by the explicit target
  and independent registry gates in `personal_apps/scratchpad/b1c/`.
- No production or VPS state was changed.

## Verification and review

- `npm test`: general frontend 403 passed; radar suite 737 passed across 45 files.
- `npm run build`: TypeScript, gym build, and radar build passed.
- Backend affected/API/detail gate: 128 passed; tone unit gate: 7 passed.
- Playwright visual/interaction gate: 1440/1920/390/320 screenshots; no 320px
  horizontal overflow; keyboard detail navigation and Escape verified.
- Independent review checked diff scope, protected PERF3 files, old-board compatibility,
  query joins, denominator reconciliation, tone query opt-in, and malformed API input.

## Boundary and next owner decisions

Do not deploy, push, merge main, touch the VPS, alter PERF3 owner scripts, add a capture,
promote the hub, or invent durable historical tone. Remaining product decisions are
whether to promote the hub and when HA should own persistent historical tone.

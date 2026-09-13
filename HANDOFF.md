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



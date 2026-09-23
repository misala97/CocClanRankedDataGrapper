# LOCAL-QA Mastermind ruling — 2026-09-15

Accept local synthetic C02/C11/C13/C14/C15 evidence and hatch fix. C16 PARTIAL: F1 date inputs clip at 320 CSS px and must be corrected before final acceptance. 58/58 automated cases do not supersede the demonstrated clipping. F2 retrospective caveat/company-name wrapping is nonblocking deferred polish; do not expand this correction. No full product review or benchmark rerun required for CSS-only final fix.

Accept observed interruption delays 5/9/14ms and reader 52ms / full HTTP 59ms overshoot for this tested environment under the reader-budget ruling. Expiry returns 503 and recovery succeeds; these observations are not a general new grace allowance or production guarantee. Warm full-request p95 781.18ms meets <=1s. Server statement timeout does not strictly bound client transfer/materialization; retain that limitation.

H3 is an explicit measurement deviation: profiling-only statement limit increased to 30s to offset tracemalloc overhead. Accept 26,195,307 B as isolated incremental memory evidence for the same bounded data/materialization/reduction, not proof of production timeout behavior. Timings/timeout acceptance come from separate untraced normal-limit execution. This ruling ratifies that separation for measurement only; no production limits changed. H1/H2/H4-H8 accepted as disclosed harness corrections with attributed regression/mutation evidence.

Accept headed Chromium page-zoom preference evidence as actual browser zoom, distinct from viewport/DPR emulation and physical-device testing. Mastermind viewed saved 320px full-page and real-zoom top captures, confirming date clipping and caveat wrap. Other screenshots/tests remain operator-attributed. 31 API, 240 guarded pure, 230 frontend tests, 10/10 mutations/build are operator-reported; no rerun by Mastermind. HEAD/base verified 1ac39fe4e1a5dd7d04830e96a96563183687b447, codex/radar-ha1-us-daily-explore. Existing dirty work preserved.

Cleanup accepted as operator-reported: stopped owned processes, clean fixture tables, retained environment at C:/Users/michi/.radar-ha1-local-qa. Hard stop means next restart must check recovery before use; prefer graceful stop next time. Stale runtime records are historical, not live authorization. dashboard.lock disappearance remains unattributed; do not recreate/delete unrelated files or invent an explanation.

Next prepared assignment HA1-US-DAILY-EXPLORE-FINAL-UI-CHECK: narrow F1 CSS fix plus in-control clipping assertion and focused QA in the already authorized HA1-only environment. No new infrastructure or automatic full review. No deployment/commit/push authorized. Successful return enables final readiness assessment, not automatic release.


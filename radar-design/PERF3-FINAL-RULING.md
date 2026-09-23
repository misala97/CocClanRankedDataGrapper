# PERF3 final return ruling — d9b04d7

Reviewed 12 September 2026. Workspace radar-perf3, branch codex/radar-perf3. Git confirms HEAD d9b04d74f1f3556f4c64cf0f9878948b54866d4f and only the two protected untracked preview scripts. Neither script was read or touched. Read current handoff, release path/runner, rollback manifest, relevant ledger/implementer review-fix sections and runner tests. No fresh DB/performance test or target operation performed.

## Six decisions

1. **Release execution: NOT APPROVED at this SHA.** Product performance evidence is accepted with the disclosed limits. The blocker is the release runner's failure handling below, not another measured speed criterion. Intended eventual mode is **first**, provided fresh target facts confirm the recorded no-producer/flag-off state. No SHA is authorized to deploy until the runner correction is reviewed; d9b04d74f1f3556f4c64cf0f9878948b54866d4f is the reviewed candidate, not an approved deployment.
2. **12.5% stale samples:** accept as an observed saturation-case limitation. Keep 120/120/600 unchanged, age/stale labels intact. This is two whole 20-sample cases, not a production stale-rate estimate or an independent random sample. Do not claim strict freshness passed. No second producer, index or capacity rewrite required for this release.
3. **793 ms watched initialization:** accept under the existing once-per-worker exception. Keep reporting it separately from steady-state ready reads. No further optimization required now.
4. **Manual interrupted-migration recovery:** acceptable; a shipped automatic recovery tool is not required. BUT the runner must exit into the documented stopped-consumer state when migration outcome is incomplete/unknown. It cannot restart those consumers and then tell the operator recovery requires them stopped. Exact schema/stamp inspection and the rehearsed policy remain mandatory before repair or restart.
5. **Telemetry:** choose application request/board timing to stdout/journald, enabled alongside eventual activation via PERSONAL_REQUEST_TIMING_LOG=on in the authoritative .env. Use existing journald retention only if fresh inspection establishes bounded disk usage and the logging destination. No global journald-retention change is bundled; if unbounded, prepare a service-specific bounded alternative before activation. No raw unit environment values in logs. This is the approved release configuration choice, not permission to activate it now.
6. **Review gap:** the narrow read-only pass was worth taking and was performed in this ruling. It found the runner blockers below. No repeat full product review or performance matrix is requested. Review only their corrective delta and tests on return.

## Required runner corrections

### A. First rollout must handle an absent producer unit

The runner's initial stop loop unconditionally stops radar_board_producer.service BEFORE installing it. A missing unit is different from an installed inactive one; stop of a missing unit fails under set -e. The fake systemctl currently always succeeds on stop, so first-mode tests do not model the recorded target. Restoration likewise attempts stop/disable of the absent unit.

Capture existence separately from active/enabled state. Skip mutations for a unit genuinely absent at entry until this run installs it; handle removal/restoration consistently. Do not hide failures for existing required units. Add a first-mode fake that actually rejects stop/disable/start of missing units and succeeds only after installation/reload; prove first rollout succeeds and early failure restores both existing web units without being derailed by the absent producer.

### B. Separate migration attempted, completed and activated recovery

MIGRATED=1 is set BEFORE upgrade. If upgrade fails after partial DDL, on_failure calls restore_services yes, restarting both web units despite the manual recovery contract. In routine mode restore_flag restores the original ON value even after readiness failure, while the new namespace may not be ready. The comment calling this flag-off recovery is therefore false for routine mode. ACTIVATED is recorded but never consulted by on_failure; ERR is reinstalled before final health checks, so a post-activation health-check failure can still enter rollback handling despite the declared rule.

Use explicit phase states. Incomplete/unknown migration keeps web/producer consumers stopped, reports the original failure and manual recovery requirement, and restores only services proven safe independently. Completed migration plus pre-activation readiness failure may recover on candidate code only with shared results explicitly OFF; retain schema and stop a failed producer. Once activated, subsequent health/service failures report a degraded activation (exit 75 or documented equivalent) and must not silently restore an earlier flag or invoke pre-activation rollback. Test partial upgrade failure, routine ON readiness timeout, post-activation health failure and interruption in each phase. Preserve unrelated .env keys and original error status.

### C. Remove secret-bearing unit output from the durable log

The sed redaction only matches unquoted `Environment=KEY=value`. Valid `Environment="KEY=value"` and quoted multiple assignments remain visible. Do not log raw systemctl cat with this blacklist. Omit environment assignment values entirely, including continuation lines; prefer an allowlist of required non-secret properties and key names only. Test synthetic quoted, unquoted, multiple and continued environment assignments; no sentinel secret may occur in stdout/stderr or the saved log. Do not use real secret values to test this.

### D. Make the claimed bound and whole-checkout build real

The 180-attempt loop is not a 15-minute wall-clock timeout: each readiness process can take time or hang. Add a real overall deadline and bounded individual probes, preserving explicit timeout exit/recovery. A fake hanging probe must terminate within the declared bound. The runner installs/builds only personal_apps while resetting the whole shared checkout and restarting coc_web; the release text claims both asset builds. Reconcile it with the actual established deploy workflow. Either include the required coc steps, or prove its tracked application/dependency inputs are unchanged for the exact candidate and refuse unsupported drift. Do not claim steps 1-8 including backup and smoke verification are automated if they remain external operator gates.

## Bounded handoff

Implement only these runner/test/runbook corrections in radar-perf3; preserve all accepted product work and protected files. Use realistic failing fakes, not permissive defaults that erase the failure being tested. One narrow independent read-only review after the patch. Return full SHA, test results and corrected first-rollout path. Reuse accepted 256 backend/67 MariaDB/loaded matrix evidence where application/store/migration behavior is unchanged; no new benchmark campaign.

Fresh read-only target preflight and verified backup remain gates to any eventual deployment. Nothing is merged, pushed, deployed, migrated, configured or restarted by this ruling. No capture, threading, held index, B1 or root changes.


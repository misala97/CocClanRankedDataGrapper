# PERF3 DEPLOYED — 2026-09-13

Owner authorized complete deployment. Completed, not awaiting permission.

- Workspace: C:/Users/michi/Desktop/CodingStuff-worktrees/radar-perf3; branch codex/radar-perf3.
- Deployed and published main SHA: ad531ef6d697eac7c67179a40d7fca56812095fd.
- Local runner fixes: 171fdbf; documentation-only integration merge ad531ef. Both history sections preserved. No application delta introduced by integration.
- Final database-free runner tests: 18 passed in 60.28 seconds. Prior product and MariaDB evidence unchanged. Prior independent corrective review reported no blockers.
- First rollout succeeded via /root/perf3-release/deploy-ad531ef.sh, systemd unit perf3-release-ad531ef-run, release lock and durable /var/log/perf3-release log. An earlier invocation rejected a trailing carriage return before mutation; corrected invocation succeeded.
- Migration head b7e3f9c1a2d4. Eight warm boards passed readiness before activation.
- personal_apps_web outage: stopped 04:21:50 CEST, started 04:23:10 CEST (80 seconds).
- Both webs, scheduler, notifier, ingest and board producer active and enabled.
- Shared results ON; timing telemetry ON and verified in journald; observation capture OFF. Original /radar/ and /radar/hub/ retained. No B1, threading, held index or root promotion.
- Fresh backup: /root/db_backups/db_2026-09-13_0415.sql.gz (235 MiB), gzip verified, offsite copy completed. SHA256 546ae63c7d9c079cad8405641013946739c012947fbb4bf22125475015721e9b.
- /root/update_coc.sh now matches tracked producer-aware update_coc_wrapper.sh; syntax verified. Original preserved at /root/perf3-release/update_coc.before-ad531ef.sh. Environment backup retained privately on host.
- Real production build_payload reads, no impersonated account: US/DE x12h/24h, all segments, default50 rows, three samples each. All shared=true, pending=false, stale=false. First read46.7ms; subsequent3.7–5.3ms. Backend-only measurements, not authenticated HTTP or browser timings, and not every selection/limit.
- HTTP /radar/ and /radar/hub/ both return expected unauthenticated302 in2–4ms. No owner session minted; authenticated visual review not claimed.
- Routine deploys must use the installed wrapper so revision-dependent caches are prewarmed. Primary recovery is shared flag off with candidate schema retained, not blind old-code reset.

## Continuity
Deployment is complete. Do not re-deploy this SHA merely to resume. No new implementation or benchmark work is owed for this release. Protected owner files cleanup_preview.py and preview_perf3.py remain untouched and untracked. This record and the current HANDOFF notice are documentation-only post-deployment changes, intentionally not committed/pushed to avoid creating another release namespace.
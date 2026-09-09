# Radar current handoff

Updated 2026-09-09. Supersedes earlier next-step notes.

## Roles and next action

Owner chose Codex to design/write plans and Claude to implement, then said 'Alright. Lets go'. First implementation plans are ready. No production code changed. Claude begins with CLAUDE-START.md and the foundations workspace/baseline gate. Do not restart design discovery.

Read IMPLEMENTATION-SPEC.md, FOUNDATIONS-LEDGER.md and HUB-LEDGER.md completely, then both Radar plans dated 2026-09-09 in docs/superpowers/plans. BRIEF.md and ROADMAP.md preserve the future scope. DESIGN.md and the prototype preserve selected light/green A overview + B research; C rejected. Do not use redesigning-pages-from-data.

## Verified source state

Planning checkout: C:/Users/michi/Desktop/CodingStuff
Artifact folder: C:/Users/michi/Desktop/CodingStuff/radar-design (not a Git worktree)
App: C:/Users/michi/Desktop/CodingStuff/personal_apps
Branch: dev_personal
HEAD: 7a9ffe445076e57d02fea5627e8cd185ec9cb39f
Implementation workspace/branch: not created. Verify on takeover; Git evidence wins.

Unrelated tracked dirty files: personal_apps/scripts/discover_telegram_sources.py and personal_apps/telegram_candidates.json. Many untracked source probes, datasets, scratch scripts and configuration directories also exist. Preserve all. Do not stage the whole checkout.

Planning ownership: radar-design/ and the two dated Radar plan files. Currently untracked: explicitly carry this entire package into the implementation worktree and commit only it there before coding. A worktree from HEAD will omit it. Keep the canonical handoff/ledgers at these reachable repository paths, not only in ignored scratch directories.

## Completed / open

Completed: requirements; direction probes; selected visual identity; 11-view interactive prototype; prototype QA; capability roadmap; first-release binding spec; foundations F1-F3 and hub H1-H4 plans; progress ledgers and Claude entrypoint.

Open: all production implementation/reviews; isolated test DB and baseline; later EUR/FX/manual-ledger design; news pipeline; fuller point-in-time capture and replay/evaluation; qualified recommendations. The first release is Overview, Chatter, Research, Watching, Activity and read-only Admin.

## Findings and rulings

- Existing APIs support board, ticker detail, search and per-account watching. Existing facts are reusable; old layout/product exclusions are not binding.
- Ingest counters are logged today. Stored run outcomes still cannot prove exhaustive daily judged/discarded totals; crashes can leave incomplete accounting.
- The proposed fixed-selection archive is a bounded board-observation history, not a full-universe/raw-evidence replay archive. No backfill claims.
- tests/conftest.py uses a real development database. app.py reads PERSONAL_DB_NAME and load_dotenv(override=True). Verify the resolved disposable database before tests/schema changes; shell overrides alone do not prove isolation.
- auth.admin_required supports the new read-only ops endpoint. Existing board operational fields remain compatible for now.
- Broker availability remains unknown. German quotes do not prove Scalable availability.
- Newest inspected ML record describes v3 deployment; older no-deployment handoff statements are stale. No live health checked by this task.

## Verification and limits

Prototype: check_preview.py recorded 33 viewport/route combinations at1440/768/390 widths, no document overflow/page errors, seven interactions passed. QA.json and screenshots/ hold evidence; REVIEW.md documents fictional data/limits. These are not production tests.

Planning: inspected actual paths, fixture exports, auth, serializers, runner counters, migrations and asset entry conventions. Self-review corrected DB configuration/isolation and archive scope. No app test suite, live database query, migration or deployment performed. Git status emitted access warnings for unrelated ignore/cache paths; source inspection succeeded.

## Preview and deployment carries

Prototype http://127.0.0.1:5187/#overview. Prior node session73154 may have expired; verify before reuse. Restart node serve.cjs from radar-design if needed. Local fictional preview only.

Production implementation begins opt-in at /radar/hub/, preserving /radar/ for rollback. Capture defaults disabled until migration/staging verification. Deployment and root-route promotion are separate release steps. Before switching sessions replace this section with exact implementation workspace/branch/HEAD, dirty ownership, completed/open tasks, review findings, tests/results, protected files and immediate next action.

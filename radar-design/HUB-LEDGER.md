# Research hub progress ledger

Plan: docs/superpowers/plans/2026-09-09-radar-research-hub.md
Spec: radar-design/IMPLEMENTATION-SPEC.md
Updated: 2026-09-09

| Step | Status | Evidence / next action |
| --- | --- | --- |
| Design direction/prototype | Complete | Owner selected light/green A+B; 11 simulated views, QA.json, limitations in REVIEW.md |
| Detailed release planning | Complete | Binding spec and H1–H4 plan written and self-reviewed |
| Workspace/baseline gate | Complete | Shared with foundations; evidence in FOUNDATIONS-LEDGER.md. Sequential execution, one worktree |
| H1 shell/state/navigation | Complete | Commit 92da7c8; 40 hub vitest cases and 8 backend cases pass |
| H1 independent review | In progress | Read-only reviewer dispatched against 92da7c8 |
| H2 chatter/research/search | Open | Depends on H1 |
| H2 independent review | Open | After implementation |
| H3 watching/overview | Open | Depends on H2 |
| H3 independent review | Open | After implementation |
| H4 activity/admin/verification | Open | Depends on H3 and F3 |
| H4 independent review | Open | After implementation |
| Owner visual review | Open | Opt-in /radar/hub/ after verification |
| Root route promotion/deploy | Outside scope | Separate release decision |

Implementation workspace: C:/Users/michi/Desktop/CodingStuff-worktrees/radar-foundations
Branch: codex/radar-foundations (foundations and hub run sequentially in one worktree, as the hub plan's
entry gate permits). Planning source: C:/Users/michi/Desktop/CodingStuff, dev_personal,
7a9ffe445076e57d02fea5627e8cd185ec9cb39f.

## H1 evidence (2026-09-09)

Commit 92da7c8. New: `static/radar/src/hub/{navigation,queries}.ts`, `{Hub,PageState}.tsx`,
`hub.css`, three test modules, `static/radar/src/entries/hub.tsx`, `templates/radar/hub.html`,
`tests/test_radar_hub_page.py`. Modified: `vite.radar.config.ts` (hub entry), `vite_assets.py`
(a CSS resolver), `app.py` (registers it), `features/radar/routes/views.py` (the `/radar/hub/` view).

- `npx vitest run -c vite.radar.config.ts static/radar/src/hub/` -> **40 passed** (3 files).
- `npm test` -> **403 passed** (root) and **307 passed** (radar).
- `npm run build` -> exit 0; emits `hub-*.js` and `hub-*.css`.
- `pytest tests/test_radar_hub_page.py tests/test_radar_api.py tests/test_radar_watch_api.py tests/test_gym_routes_smoke.py -q`
  -> **135 passed**.
- Browser, local server on port 5051: `/radar/hub/#overview` at 1440x1000 and 390x844 and
  `#portfolio` (the recovery view) at 1440x1000. No document overflow, no console or page errors.
  Screenshots inspected: the pine sidebar, grouped navigation, active state, separated
  Administration and the topbar session line match the prototype's composition; at 390 the sidebar
  collapses to a labelled toggle.

Scope note: the six pages are placeholders that say so. H1 is the shell, and a placeholder that
merely looked empty could be read as a measured emptiness.

Found on the way: an entry that imports its own stylesheet has it emitted as a separate hashed file,
and the template must link it. Linking only the script renders the page unstyled with nothing in the
console. `vite_assets.resolve_asset_css` and a test now cover it.

Record commits, exact tests, screenshots, findings and resolutions for each task. Preserve completed tasks across session/model switches. Prototype approval is not approval of finished production implementation.

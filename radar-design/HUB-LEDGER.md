# Research hub progress ledger

Plan: docs/superpowers/plans/2026-09-09-radar-research-hub.md
Spec: radar-design/IMPLEMENTATION-SPEC.md
Updated: 2026-09-09

| Step | Status | Evidence / next action |
| --- | --- | --- |
| Design direction/prototype | Complete | Owner selected light/green A+B; 11 simulated views, QA.json, limitations in REVIEW.md |
| Detailed release planning | Complete | Binding spec and H1–H4 plan written and self-reviewed |
| Workspace/baseline gate | Complete | Shared with foundations; evidence in FOUNDATIONS-LEDGER.md. Sequential execution, one worktree |
| H1 shell/state/navigation | Complete | 92da7c8 |
| H1 independent review | Complete | 1 BLOCKING + 7 should-fix; all resolved in 0f3767b |
| H2 chatter/research/search | Complete | 0f3767b |
| H2 independent review | Complete | 4 BLOCKING + 12 should-fix; all resolved in the H2/H3 fix commit |
| H3 watching/overview | Complete | c88266b |
| H4 activity/admin | Complete | 8864189 |
| H3+H4 independent review | Complete | No blocking; ~15 should-fix, all resolved |
| Verification pass | Complete | 13 captures at 1440/768/390, keyboard and real-API pass; see reports/hub/EVIDENCE.md |
| R1 final-feed deselection | Complete | e25f223; independent review, 6 findings, all resolved in 917cb15; browser proof below |
| Suite flake found and fixed | Complete | 78b17c6; Hub.test.tsx let a real navigation reach jsdom, failing ~1 run in 6 on a random neighbour |
| Owner visual review | Open | Opt-in /radar/hub/ is ready for it |
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

## H2–H4 evidence (2026-09-09)

Commits: 0f3767b (H2 + the H1 review's fixes), c88266b (H3), 8864189 (H4), then one fix
commit for the H2 and H3/H4 reviews.

- `npx vitest run -c vite.radar.config.ts static/radar/src/hub/` -> **152 passed**, 11 files.
- `npm test` -> **403 passed** (root config) and **419 passed** (radar config).
- `npm run build` -> exit 0.
- `pytest tests/test_radar_hub_page.py tests/test_vite_assets.py tests/test_radar_api.py -q`
  -> **85 passed**.
- Browser: 13 captures at 1440x1000, 768x1024 and 390x844 across all six pages and the
  recovery view; a separate keyboard and real-API pass over all five destinations at all
  three widths. No document horizontal scroll, no console or page errors anywhere.
  `reports/hub/EVIDENCE.md` says exactly which pixels are real data and which are the one
  labelled fixture.

### What the reviews found

**H1 — one blocking.** The skip link, the first control a keyboard reader meets,
destroyed the page: `#rh-main` is an element id and the router claimed every fragment as
a route name. Also: `readSelection` was not the inverse of `queryFor`, so the same URL
rendered one board after Back and another when opened fresh; the segment vocabulary was
missing `small`, which the server still accepts; `initialData` could seed a board built
under one filter as the answer to another; 403 still meant "signed out"; the closed
off-canvas nav kept four invisible tab stops; the focus ring was under 3:1; and
`vite_assets` re-read and re-parsed the manifest on every call.

**H2 — four blocking.** Absent evidence printed as zero beside a clause saying 80
mentions. A tone percentage `board.py` returns three counts specifically to prevent, and
one that rounded 1-in-200 to "0% positive". A chart caption claiming intraday resolution a
daily line does not have. Cached placeholder data rendering the previous company under the
new company's heading and URL. Plus: Research had no tests at all, nine of the plan's
thirteen H2 test requirements were missing, five ported CSS rules were absent, the chart
was illegible at 768, and **Human Chatter had no server-side filters at all** — half of
its acceptance row. All fixed; `Filters.tsx` is new.

**H3+H4 — no blocking.** Watching's own guard did not hold across a navigation, so the
mutation moved into the shell and Watching became presentational. Overview reintroduced
the absent-versus-empty conflation Watching exists to prevent. Activity said "partial
coverage" — the one word its endpoint refuses — and called a day with three crashed runs
"Not recorded" beside a cell saying "3 failed". Admin printed a raw float for the p95 age
and no time on its cycle rows. Three tests were vacuous, including one that "walked every
button" on a page that has none.

### Deviations and rulings

- `Filters.tsx` is new work the plan does not name a file for. The spec's Human Chatter
  acceptance row requires filters and the plan says to implement them; the file is where
  they went.
- The H3 commit message says the server's phrase "was removed" from the ranked list. That
  removal is in the H2 commit, not H3. The history is right and the sentence is in the
  wrong commit.
- The mobile stacked table carries explicit ARIA roles and a real labelled element per
  cell, because `display: block` drops a table's implicit roles and `::before` content is
  not part of a cell's accessible name.

## R1 evidence -- the last feed (2026-09-09)

Codex's finding, reproduced first: with `['reddit']` selected, unchecking Reddit called
`toggle`, which returned `all.filter(name => name !== source)` -- `['bluesky','fourchan']`.
The reader asked for one less feed and silently got two different ones.

Commits: **e25f223** (fix + tests), **917cb15** (the review's six findings).
Files: `static/radar/src/hub/Filters.tsx`, `Filters.test.tsx` (new), `Hub.test.tsx`,
`Chatter.test.tsx`, `hub.css`.

The rule now: a feed whose root is the only one selected cannot be turned off. `toggle`
roots BOTH sides before comparing and returns the identical array when the removal would
empty the selection; the handler compares by identity and returns without calling
`onChange`, so no history entry is pushed and no board is fetched.

Tests:
- `npx vitest run -c vite.radar.config.ts static/radar/src/hub/` -> **171 passed**, 12 files.
- `npm test` -> **403 passed** (root config), **438 passed** (radar config).
- `npm run build` -> exit 0.
- Mutation check: reverting only the reducer to `current.filter(...)` fails **6** tests.
  Before this work the same revert failed 0 -- Chatter's one guard asserted only
  `sources.length > 0`, which the defect satisfied. That test is gone; it tested nothing.

Browser proof, local server on 5051, board injected at two selections:
`reports/hub/hub-feeds-unlocked-1440.png` (three feeds, no lock, note absent) and
`reports/hub/hub-feeds-locked-1440.png` (one feed, locked, note shown). A real click on
the locked box -- forced past Playwright's actionability gate, because a browser does let
a click through to a checkbox carrying only `aria-disabled` -- left it checked, showed the
note exactly once, and issued **zero** `/radar/api/board` requests.

### What the R1 review found

Six, all resolved in 917cb15. Two were mine to have caught:

- `disabled` on the locked checkbox contradicted the board's own recorded decision
  (`board/Controls.tsx:192-196`): a disabled control leaves the tab order, so the
  explanation attached to it becomes unreachable by the readers who most need it. Now
  `aria-disabled` plus `aria-describedby`, and the handler enforces the rule.
- `toggle` rooted only the incoming source, so `toggle(['reddit:options'], 'reddit:options')`
  appended a duplicate. Both sides are rooted now.
- The floor note rendered unconditionally while its CSS comment claimed otherwise.
- Two of the new tests still passed under a full revert of the fix.
- No test above the component boundary: nothing proved the SHELL did not fetch. Two
  request-level tests in `Hub.test.tsx` now assert every `fetchBoard` call carries
  `sources: ['reddit']`, with a positive control that a real change does fetch.
- A dead `.rh-sources input:disabled + span` rule left behind by the attribute change.

## The suite was flaky, and it was ours (2026-09-09)

Found while re-verifying for the R2 documentation, not by a review: one `npm test` run
reported **1 failed / 437 passed** in the radar config, and five further runs were green
without ever naming the same test.

`Hub.test.tsx`'s `'leaves a modified click to the browser'` asserts the handler does not
`preventDefault` on a ctrl-click, and proved it by letting the click through to a real
`href`. jsdom cannot navigate, so it throws `Not implemented: navigation (except hash
changes)` -- **asynchronously, on a timer, after the test has already passed**. The error
then attaches to whichever test is running when it fires, which is why it moved around and
why the file passed in isolation.

Fixed in **78b17c6**. A document-level listener runs after the component's handler, records
`event.defaultPrevented` -- the component's own answer -- and then prevents the default
itself, so nothing reaches jsdom's navigation. Mutation-checked: removing the modifier guard
in `Hub.tsx:159` fails this test and only this test. Four consecutive `npm test` runs are
now **403 passed** (root) and **438 passed** (radar), with the jsdom error gone from the
output entirely; `npm run build` exit 0.

Worth recording as a class, not an incident: a green suite that is green only most of the
time reports the same word as one that is actually green. This one had been in the tree
since H1 and nine reviews did not catch it, because every one of them read the code rather
than running the suite six times.

Record commits, exact tests, screenshots, findings and resolutions for each task. Preserve completed tasks across session/model switches. Prototype approval is not approval of finished production implementation.

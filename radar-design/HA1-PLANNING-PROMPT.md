You are Radar's Mastermind / Overview, assigned to prepare the HA1 implementation packet. Return your result to the originating Mastermind.

Assignment: HA1-US-DAILY-EXPLORE-PLAN.
Role: product/architecture planner. Prepare the binding spec, implementation plan and progress ledger. Do not implement application code or deploy.

Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-hub-promotion
Branch: codex/radar-hub-promotion
Expected HEAD and local origin/main: 1ac39fe4e1a5dd7d04830e96a96563183687b447.
No upstream configured. Verify branch, HEAD, status/diff/log before editing; preserve all existing dirty and untracked files. No worktree creation is necessary for planning.

Read in order, relative to the absolute workspace above:
1. radar-design/WORKFLOW.md
2. radar-design/MASTERMIND-STATE.md
3. radar-design/ASSIGNMENTS.md
4. HANDOFF.md
5. radar-design/MD-01C-RULING.md
6. radar-design/MD-01C-RETURN.md
7. radar-design/HISTORY-ANALYSIS-PLAN.md
8. radar-design/HISTORY-ANALYSIS-LEDGER.md
9. radar-design/ROADMAP.md
10. radar-design/MARKET-DATA-ROADMAP.md
11. docs/superpowers/specs/2026-09-10-radar-openterminal-comparison-REVIEW.md

The last two are carried copies from the main planning checkout. Their historical status/provider/scoring statements are superseded by current rulings; read their OpenTerminal reasoning, not as implementation authorization.

Current decision:
Prepare one actual-app HA1-US-Daily-Explore slice using a selected mapped US primary, native USD daily prices and independent retained chatter counts. The owner accepted advancing planning after the MD-01C return. This is a first feature scope, not a global USD-only policy or permission to remove German providers/coverage.

Accepted Researcher evidence:
September 7-13, 2026: 12,599 active catalogue companies, all eligible native-USD US primaries; 12,294 have usable daily prices, 12,075 at least two, 219 one, 305 none. DE rescues zero missing-US daily cases in this window. 8,037 companies have retained chatter buckets, 4,562 none, 2,146 positive mentions. Counts represent the current catalogue and bounded window, not global coverage or long historical depth. Production was changing during sequential SELECTs. No independent rerun is required.

Important evidence qualification:
The report's generic Q4 outer-join SQL can count a synthetic NULL row as a gap when two closes have no interior peer date. The claimed 195 instruments/225 gaps is provisional because the exact separately executed SQL is not preserved. Do not use that number as a test oracle. Design correct gap semantics and include the adjacent-two-close case. This does not block planning or justify another broad research round.

Product scope:
- An authenticated Analysis/Explore destination in the actual dark Radar hub.
- Company selection tied explicitly to one mapped instrument.
- Daily USD closes and chatter counts, independent timing/resolution and availability.
- Default seven-day period; propose an explicit bounded range contract. Wider supported ranges need focused selected-instrument evidence during implementation.
- Coverage, zero/one-close, no chatter, truncated coverage and source-config transition states.
- Price source/MIC/venue/currency/adjustment provenance, no hidden cross-venue or basis splicing.
- Retrospective label; retained evidence limitations; no known-then/replay/study claims.
- Daily chatter aggregation must preserve coverage semantics. Never sum/average mention_z as a daily activity score; chart counts are mentions.
- Human Chatter's current mention_z-before-top-N ranking remains price independent.
- Desktop first with usable mobile, accessibility and loading/error states.
- Use actual-app design and existing code patterns; no separate interactive prototype and do not use redesigning-pages-from-data.
- Backend changes are allowed in the proposed plan where justified; do not invent existing endpoints or make a new schema a prerequisite without need.

OpenTerminal continuity:
Keep selected-instrument intraday/history (MD-02/07), provider selection (MD-05) and adapter cache/coalescing/timeouts/backoff/health (MD-10) as the next enabling packet, ahead of portfolio/news. Broad discovery/venue experiments MD-03/08 remain separate. This daily slice must not freeze price into chatter slots or pretend to implement richer intraday/OHLCV. Current endpoints still need bounded efficient reads and honest failures. No provider calls or provider selection in this assignment.

Deliverables, all within this workspace:
- radar-design/HA1-US-DAILY-EXPLORE-SPEC.md
- radar-design/HA1-US-DAILY-EXPLORE-PLAN.md
- radar-design/HA1-US-DAILY-EXPLORE-LEDGER.md
- radar-design/HA1-US-DAILY-EXPLORE-PLANNING-RETURN.md
Update current state, assignment register, root/radar-design handoffs, roadmap and history ledger only as needed to link these deliverables and record their real status.

Acceptance:
1. Source-grounded scope and UI/data contracts with exact current file/symbol references.
2. Concrete tasks, owned files/interfaces, meaningful regression cases and clear completion checks.
3. Efficient selected-instrument query strategy; no universe-wide measurement SQL on a page request.
4. Missing vs observed-zero/truncated semantics; authoritative calendar vs peer-date limitations; price regime/corporate-action limits.
5. Actual-app desktop/mobile verification plan and safe isolated test/preview strategy that preserves protected environments.
6. One implementation worker followed by independent Reviewer/QA; Deployer only on later owner authorization. Keep roles proportional.
7. A copy-ready Implementer prompt with role, scope, acceptance, authorized actions, evidence and stopping condition; include the mandatory return-to-Mastermind prompt.
8. Explicit artifact carry list for the later isolated implementation worktree, since these planning documents are uncommitted.

Authorization/boundaries:
Local read-only code inspection and planning-document edits only. No application/test code changes, migrations, database/provider/production access, service changes, capture activation, commits, pushes or deployments. Preserve B1C database/port5021, all other worktrees, main checkout and existing preview artifacts. Capture remains OFF by last release report; shared boards ON; migration b7e3f9c1a2d4. Hub promotion/PERF3/B/B1C/ranking are closed/live. Accepted B1C latency and the 6.5-hour assumption are outside scope.
No automatic tasks or subagents. Owner chooses workers/models.

Stop after the completed planning packet and Implementer prompt. Do not execute the plan or dispatch workers. If a material product choice cannot be resolved from scope, return the specific choice with a recommendation, completing independent planning first.

End with a self-contained copy/paste prompt:
You are Radar's Mastermind / Overview. Assess this planning return for HA1-US-DAILY-EXPLORE-PLAN.
Workspace/branch/base/current HEAD: [exact values]
Working tree: [dirty/untracked paths and ownership; commit/push status]
Binding artifacts: [absolute spec/plan/ledger/return paths]
Objective and authorized scope: [summary]
Completed deliverables: [what exists]
Evidence: [current file/symbol references and inspection results]
Evidence attribution: [fresh local inspection vs MD-01C measurements]
Decisions/limitations: [contracts, exclusions, unresolved decisions]
Actions taken: [planning changes; explicitly no implementation/deployment]
Protected state: [preserved environments/files]
Subagents: none
Next worker prompt: [absolute artifact path/section]
Requested Mastermind decision: [accept packet or rule on a specific choice]
Next bounded action: [owner-selected Implementer, not already dispatched]
Verify Git/artifacts, update continuity, and do not implement/deploy yourself.


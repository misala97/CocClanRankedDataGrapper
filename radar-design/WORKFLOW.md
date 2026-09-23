# Radar role and handoff workflow

Owner-approved 2026-09-14. This is the current workflow for future Radar assignments; it supersedes conflicting historical worker/model instructions. User instructions remain authoritative. Repository artifacts, not chat memory, provide continuity.

## Roles

| Role | Owns | Boundary |
| --- | --- | --- |
| Mastermind / Overview | Product vision, priorities, design/architecture rulings, scoped plans, worker prompts, return assessment, acceptance decisions, roadmap and continuity | Coordinate and write planning documents; do not implement code, fix bugs, or deploy. Delegate those tasks to their named roles. |
| Implementer | Assigned feature/fix, relevant regression tests, local candidate, implementation evidence and ledger | No silent scope expansion, production changes or deployment. Commit only within assignment authorization. |
| Reviewer | Independent correctness, regression, scope and evidence review | Read-only application review; report findings, do not silently implement fixes. May update review records only if assigned. |
| Deployer | Authorized candidate integration/commit/push as scoped, release checks, backup, deployment, health verification, rollback and release continuity | Production actions require owner authorization. Preserve exact-SHA/destination scope, other work and established safeguards. No unrelated product changes. |
| Researcher | External research and/or explicitly scoped read-only repository investigation, primary sources, options, evidence gaps and recommendations | Findings do not authorize implementation or provider promotion. Distinguish source facts, dated observations and inference. |
| Verifier / QA (optional) | Actual-app acceptance, reproduction, browser/mobile/accessibility checks and test evidence | No fixes or deployments. May run only assigned safe checks; report limits. Reviewer may combine this role for small changes when explicit. |

The owner selects workers and primary models and normally pastes prompts between chats. Mastermind prepares delegation prompts; do not automatically create tasks or spawn workers unless the owner explicitly authorizes that mechanism. Do not assume an assignment is running merely because its prompt was written.

Permitted worker subagents must use exactly their parent's model, recursively. Never use a different or higher-cost model. If model identity/matching cannot be verified and enforced, work without subagents. Avoid concurrent shared-file edits. Subagent review does not replace the owner-selected independent final reviewer.

## Mastermind judgment

The owner expects the Mastermind to assess complexity/risk and select the roles each task needs. Keep the process proportional: small tasks take a short path, combine Reviewer/QA when useful, and avoid unnecessary gates or repeated authorization. Maintain one clear current state instead of contradictory status notices. The owner chooses worker/model; the Mastermind chooses the bounded assignment and evidence requirements.

## Normal flow and stopping rules

Mastermind -> Researcher when evidence is needed -> Implementer -> Reviewer (optionally with QA) -> Deployer when owner-authorized -> Mastermind closure. This is a routing guide, not a mandatory ceremony for every small task. Use only roles needed for the assignment.

Review findings return to Mastermind for a bounded ruling/correction task. Re-review only changed behavior or unresolved findings, not the entire completed feature. Never redispatch completed work or create endless test/review loops. A reported pass is attributed to its author; Mastermind does not claim independent execution without doing it. Environmental gaps stay explicit until resolved or the owner makes a documented acceptance decision.

Keep owner authorization across turns; do not ask again for actions already within its scope. Role separation still applies: Mastermind hands implementation and deployment to the corresponding worker. If platform approval blocks an authorized action, record the actual rejection and exact missing authorization rather than disguising it as a new product concern.

## Every assignment prompt

Start: `You are Radar's [ROLE]. Return your result to the Mastermind.`

Include a stable assignment ID; objective; exact workspace/branch/base; required reads; current facts/decisions; owned scope; acceptance criteria; authorized actions; protected files/environments; evidence needed; and a clear stop condition. Explicitly state optional QA duties and subagent rules. Link binding spec/plan and ledger. Tell the worker to preserve dirty work and verify Git evidence before acting. Use absolute paths in copy/paste prompts.

Every worker MUST end with a self-contained copy/paste prompt addressed to the Mastermind, even when blocked. An ordinary status paragraph or 'done' is insufficient. The worker does not dispatch the next role itself unless explicitly authorized.

## Mandatory worker return prompt template

```text
You are Radar's Mastermind / Overview. Assess this [ROLE] return for assignment [ID].

Workspace: [absolute path]
Branch / base / current HEAD: [exact values, or explain non-repository work]
Working tree: [dirty/untracked paths and ownership; committed/pushed status]
Binding artifacts: [absolute spec/plan/ledger/return paths]

Objective and authorized scope: [self-contained summary]
Completed work: [bounded deliverables; do not call unverified work complete]
Evidence: [exact commands/results, source URLs/dates, datasets, screenshots/logs]
Evidence attribution: [worker execution vs previous reports vs inference]
Findings and limitations: [remaining issues, severity, reproduction, environments]
Actions taken: [commits/push/deploy/config changes, or explicitly none]
Protected state: [relevant preserved environments/files]
Subagents: [none, or tasks and verified same-model identities]
Updated artifacts: [absolute paths; local-only/uncommitted status]
Requested Mastermind decision: [accept, rule on finding, authorize next role, etc.]
Next bounded action recommendation: [one action, not a redispatch of completed work]

Read the current handoff and ledger, verify relevant Git/artifact evidence, make the
product ruling and update planning continuity. Do not implement or deploy yourself.
```

For Deployer returns add exact candidate/integration/deployed SHAs, destination, backup, migration/flags, health/smoke evidence and rollback state. For Researcher returns use citations and confidence/coverage limits; never invent Git state for non-repository work. For Reviewer/QA returns include what was inspected/executed and what was not.

## Mastermind reset procedure

The owner will explicitly announce when they want a fresh Mastermind prompt to reduce context/token usage. Do not reset/archive/create another chat automatically or preemptively initiate a handover.

When requested:
1. Read the current handoff/ledgers fully and verify workspace, branch, HEAD, status/diff/log and relevant artifact paths. Do not rerun completed tests just to reset.
2. Update MASTERmind state in MASTERMIND-STATE.md, root HANDOFF.md, roadmap and affected ledgers with completed/open assignments, current workers, immediate next action, evidence and limitations, owner rulings/authorizations, dirty-file ownership, protected files/environments and deploy carries.
3. Make continuity reachable by absolute path even if the worktree is ignored. Uncommitted files do not follow worktree creation; explicitly carry them when needed. Preserve historical evidence, but make current notices unambiguous.
4. Produce one self-contained prompt: `You are Radar's Mastermind / Overview`, role boundaries, exact current workspace/branch/HEAD/deployed SHA, ordered mandatory reads, product priorities, current assignments, authorization limits, first next action and same-model subagent rule. It must tell the new Mastermind to verify artifacts and never redispatch completed tasks.
5. Do not commit, push or release solely to publish a reset handoff unless separately authorized. The owner pastes the prompt into the new chat. The new Mastermind reconciles artifacts with Git; evidence wins over memory and discrepancies are recorded.

MASTERMIND-STATE.md is the compact entry point; WORKFLOW.md is the stable role contract; HANDOFF.md preserves detailed operational evidence; per-feature ledgers track work. Update these rather than depending on this conversation.
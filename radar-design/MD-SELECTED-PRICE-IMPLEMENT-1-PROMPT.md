You are Radar's Implementer. Return your result to the Mastermind.

Assignment: MD-SELECTED-PRICE-IMPLEMENT-1

Goal:
Improve selected US stock charts in Radar's Research page and the shared
research panel inside Human Chatter: detailed 1D prices, genuine five-session
1W prices, aligned retained chatter/sentiment bars, honest stored fallback,
and bounded provider acquisition/health. Headline quotes remain unchanged.

Source workspace (read-only):
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-ha1-us-daily-explore
Source branch: codex/radar-ha1-us-daily-explore
Expected source HEAD/base: daadf3868caedcb5db858378e919cba68b735f8a

Candidate workspace to create:
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
Candidate branch: codex/radar-selected-price-charts
Start at the exact base above. Verify branch/HEAD/status/diff/log first;
use per-command safe.directory if required. Preserve all dirty work.
If the candidate already exists, inspect and resume only matching assignment
work; never reset or overwrite another task.

Mandatory reads in the source workspace, then from their carried candidate
copies (each path is relative to the absolute workspace above):
- radar-design/WORKFLOW.md
- radar-design/MASTERMIND-STATE.md
- radar-design/MD-SELECTED-PRICE-SPEC.md
- radar-design/MD-SELECTED-PRICE-PLAN.md
- radar-design/MD-SELECTED-PRICE-LEDGER.md
- radar-design/MD-SELECTED-PRICE-EVIDENCE-1-RULING.md
- radar-design/MD-SELECTED-PRICE-EVIDENCE-1-RETURN.md
- HANDOFF.md

The PLAN has the exact carry manifest. Copy and hash-verify those local,
uncommitted artifacts before implementation; Git worktree creation alone
does not carry them. Preserve originals. Latest notices and the binding
SPEC/PLAN override historical status and generic skill workflow defaults.

Authorization on owner dispatch:
Create the isolated candidate and implement the complete SPEC/PLAN locally.
One worker, no subagents. No automatic next-role dispatch. Keep all changes
uncommitted; no push, merge, deployment, production access, live provider
data requests or source activation.

Implement all three plan tasks:
1. Pure identity/window/bar/chatter contracts and bounded local reader,
   preserving recorded-tone classification and reconciliation.
2. Additive chart endpoint, lazy background acquisition coordinator,
   killable fetch child, flags, cache/traffic limits and process-scoped ops.
3. Shared hub rendering/query integration and focused tests/browser proof.

Binding details:
- Yahoo-only, current mapped US primary, native USD. Existing Yahoo helper
  reuse must preserve old callers. No mapping mutation or alternate-symbol
  retry chain.
- 1D current/last modeled session including extended hours; 1W five modeled
  regular sessions, partial today only from regular open. Explicit dates.
- Prices and chatter/tone share the actual from/to window at independent
  resolutions. Preserve sentiment-coloured bars and missing-vs-zero meaning.
- Unknown adjustment stays unknown. Bar closes are not ticks at bar start.
  Keep missing/null/session gaps and provisional state; no source stitching.
- A separate endpoint is not resource isolation: provider I/O runs outside
  the Flask request thread, using the SPEC's bounded supervisor/child lifecycle.
- Both new flags default off. Fixture QA can enable the new chart with fake
  acquisition. Provider permission/live request compatibility is not claimed.
- HA1 is COMPLETE / DEPLOYED / CLOSED. Do not repeat its reviews or change
  its Analysis page. Preserve headline, scores, poller, German behavior,
  longer spans, legacy chart and the rest of the stock panel.

Verification:
Use saved response arrays and synthetic metadata, fake store/clock/transport,
real local hanging/oversized child tests, focused regression tests,
frontend typecheck/Radar build, and python-playwright against the built hub
with explicitly mocked APIs. Cover both chart surfaces at 1440/768/390/320,
keyboard use and real 200% zoom. View the resulting screenshots.
The PLAN defines the optional new fixture-only local MariaDB target and
strict isolation rules; never reuse an existing database. Report unavailable
DB runtime evidence honestly. Do not install new dependencies or download
a database merely to satisfy optional verification.

Protected:
The source workspace and its dirty continuity/research/HA1 artifacts;
main and other worktrees; B1C/5021; promotion/5033; databases/3306/3399;
HA1 runtime/3461 and C:/Users/michi/.radar-ha1-local-qa.
Only start owned loopback processes on verified-free candidate ports.
Stop/clean up only what you created. Never execute the original provider
research scripts or read/copy production secrets.

Candidate outputs:
- Application/test/generated Radar files within PLAN ownership.
- radar-design/artifacts/md-selected-price-implementation/ with carry hashes,
  test/child/runtime evidence and screenshots.
- Updated candidate MD-SELECTED-PRICE-LEDGER.md and HANDOFF.md.
- radar-design/MD-SELECTED-PRICE-IMPLEMENT-1-RETURN.md.

Record routine bounded implementation choices and continue. Do not broaden
the product or create speculative gates. Stop at the tested candidate and
return, including explicit limitations; do not claim fixture QA is live
provider/production verification.

End with this completed self-contained copy/paste prompt, even if blocked:

You are Radar's Mastermind / Overview. Assess the Implementer return for
MD-SELECTED-PRICE-IMPLEMENT-1.

Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
Branch / base / current HEAD: [verified exact values]
Working tree: [owned edits, copied planner dirt, unrelated dirt preserved;
commit/push status]
Binding spec / plan / ledger / return: [absolute paths]
Objective and authorized scope: [self-contained summary]
Completed work: [implemented capabilities; P01-P09 outcomes]
Evidence: [exact commands/results, candidate fingerprint, carry hashes,
fixture identities, child deadline/cleanup results, screenshot paths]
Evidence attribution: [executed tests/local browser vs saved research;
no live provider/production claim]
Findings and limitations: [unresolved findings, DB runtime availability,
exact upstream request-form/session evidence, usage-condition carry]
Actions taken: [worktree/code/tests/local processes; commit/push/deploy status]
Protected state: [source workspace, dirty files and environments preserved]
Subagents: none
Updated artifacts: [absolute paths; local/uncommitted]
Requested Mastermind decision: [accept for one focused Reviewer/QA, or rule
on a concrete blocker]
Next bounded action: [one action; no repeat HA1/research review]

Read the candidate handoff and ledger completely, verify Git/artifact
evidence, rule on the return and update planning continuity. HA1 stays
closed. Do not implement, deploy or dispatch workers automatically.

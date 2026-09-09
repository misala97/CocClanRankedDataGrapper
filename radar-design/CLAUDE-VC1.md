# Claude dispatch — restore the approved Chatter experience

Work in C:/Users/michi/Desktop/CodingStuff-worktrees/radar-release-candidate,
branch codex/radar-release-candidate (last verified HEAD d3bc795).

Read AGENTS.md, radar-design/HANDOFF.md and the relevant ledgers completely, then
verify Git state. Codex's uncommitted planning/decision files are intentional;
preserve them. Read CODEX-DECISIONS.md Seventh return, then
VISUAL-CORRECTION-PLAN.md and VISUAL-CORRECTION-LEDGER.md. The new plan is binding
for this correction and supersedes the old ban on tone bars/percentages.

Complete existing TE1 first, then execute VC1a–VC1c without an intermediate
handoff just to report TE1 passed. One implementation worker at a time, then
independent read-only review. Do not redispatch completed F/H/R/P work.

The goal is the approved interactive mockup's quality in the actual application:
compact balanced Chatter rows, useful positive-activity source summaries,
visible tone percentage AND horizontal bar, explicit sample denominator,
and polished desktop/mobile behavior. The plan defines the exact meaning and
edge cases. Backend changes needed for its additive source field are allowed
after TE1; no change to ranking/eligibility is bundled in.

Reference prototype: radar-design/index.html, preview.js and preview.css;
owner comparisons: radar-design/references/chatter-*-owner.png. Do not modify
the prototype to make the current implementation pass comparison. If these
prototype files are absent, read them from C:/Users/michi/Desktop/CodingStuff/
radar-design/. Use no redesigning-pages-from-data skill.

Capture matched before/after/prototype screenshots with python-playwright and
actually inspect them. A green test suite is not visual acceptance. Resolve
findings, update the ledger and current handoff, and return a runnable local
preview plus screenshots, commits, exact verification results and limitations.

Do not merge, push, deploy, enable capture, change /radar/, or execute OT1 live
cleanup. The owner reviews the corrected result before another deployment.
Keep documentation carry/OT1 separate from VC1; historical analysis stays ahead
of portfolio/news as the next new feature after this correction.

## Owner clarification — staged design ambition (2026-09-09)

The interactive prototype is the near-term fidelity target for VC1 and the next
iterations, NOT the desired final product or a permanent ceiling. The longer-term
ambition remains the visual richness, sophistication and research depth of the
original image concepts: A's welcoming overview and B's focused research workflow,
unified in the selected light/green identity. C remains rejected.

As history, portfolio and news capabilities mature, design their pages and revisit
the hub's composition with richer charts, evidence interactions, hierarchy and
polish, using fresh mockups before implementation. Aim for the original concepts'
level of craft and complexity where it serves research; their fictional content
is not a promise of available data. The current prototype's simplified layout and
components do not bind future design. Do not freeze the product at VC1 fidelity.

This does not expand VC1: deliver the current interactive-reference correction
first, then evolve deliberately alongside the roadmap. No new implementation or
deployment is authorized by this clarification alone.

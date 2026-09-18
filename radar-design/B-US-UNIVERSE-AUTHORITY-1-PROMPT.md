# Assignment Prompt — `B-US-UNIVERSE-AUTHORITY-1`

You are Radar's Researcher. Return your result to the Mastermind.

## Assignment

- Stable ID: `B-US-UNIVERSE-AUTHORITY-1`
- Objective: confirm or correct Radar's US directory-code-to-MIC contract using current authoritative primary sources before any B1 implementation plan.
- Workspace: `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts`
- Branch: `codex/radar-selected-price-charts`
- Expected `HEAD`, `origin/main`, and feature ref: `0fdad7327292cd3cd0b62dbe3f6b460873263053`
- Role boundary: public-source research only; no implementation, production host, database, provider, or deployment access.

## Owner authorization

When the owner dispatches this exact prompt, the Researcher is authorized to browse and download public documentation only from:

- official Nasdaq Trader/Nasdaq documentation needed to interpret the symbol-directory fields;
- the official ISO 10383 Market Identifier Code registry and its official distribution files/pages.

No other external source is authoritative for the result. Secondary sources may be used only to locate an official source and must not support a conclusion.

## Start gate

1. Verify workspace, branch, `HEAD`, `origin/main`, feature ref, index, and tracked/untracked dirt.
2. Preserve every pre-existing or unrelated modification.
3. If the workspace, branch, or refs differ from the expected state, stop and report the discrepancy. Do not repair Git state.
4. Confirm the Evidence‑2 ruling remains the newest binding B assessment and that no B implementation has begun.

## Required reading

Read completely before browsing:

1. `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts\HANDOFF.md`
2. `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts\radar-design\B-US-UNIVERSE-BRIEF.md`
3. `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts\radar-design\B-US-UNIVERSE-LEDGER.md`
4. `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts\radar-design\B-US-UNIVERSE-EVIDENCE-2-RULING.md`
5. `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts\radar-design\B-US-UNIVERSE-EVIDENCE-2-RETURN.md`
6. `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts\radar-design\US-UNIVERSE-REFRESH-2026-09-16.md`
7. `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts\personal_apps\scripts\seed_radar_universe.py`
8. `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts\personal_apps\migrations\versions\a4c8e2f19b70_add_radar_market_instruments.py`
9. `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts\personal_apps\features\radar\prices\yahoo.py`
10. `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts\radar-design\WORKFLOW.md`

## Questions to answer

### Nasdaq directory fields

From current official Nasdaq Trader/Nasdaq documentation, establish:

- the exact meaning of each `nasdaqlisted.txt` `Market Category` code used by Radar: `Q`, `G`, and `S`;
- the exact meaning of each `otherlisted.txt` `Exchange` code used by Radar: `N`, `A`, `P`, `Z`, and `V`;
- whether those are still the complete valid listing-exchange code sets for the two files;
- whether any new, renamed, retired, or otherwise relevant US listing venue/code is missing from Radar's parser/mapping table;
- whether the same letter has different semantics depending on which file/column it came from.

Do not fetch or analyze a fresh live symbol-directory dataset. This assignment concerns definitions, not a new universe refresh.

### ISO 10383 MICs

From the current official ISO 10383 registry, verify each Radar MIC:

- `XNGS`
- `XNMS`
- `XNCM`
- `XNYS`
- `XASE`
- `ARCX`
- `BATS`
- `IEXG`

For each, return the official market name, operating/segment MIC relationship, country, status, creation/last-update information when available, and whether the MIC is appropriate for identifying the listing segment represented by the corresponding directory code.

Explicitly determine:

- whether Nasdaq tier MICs should remain segment MICs or normalize to operating MIC `XNAS`;
- whether `BATS` is the correct current MIC for the `Z` directory code;
- whether `IEXG` is the correct current MIC for `V`, despite Evidence‑2 finding zero current rows;
- whether cross-venue and tier changes require different mapping/history treatment.

### C1 contract disposition

Return a table with one row per directory source/code containing:

- source file and field;
- code;
- official directory meaning;
- proposed MIC;
- MIC type and operating MIC;
- official status;
- verdict: `CONFIRMED`, `CORRECT_WITH_CHANGE`, `REMOVE`, or `ADD`;
- exact source citation;
- implication for Evidence‑2's 114 safe candidates and seven MIC-drift rows.

If an official source is ambiguous, unavailable, contradictory, or dated, say so explicitly. Do not fill gaps from memory.

## Evidence requirements

- Use primary official sources only for conclusions.
- Record the exact URL, document/file title, retrieval date, relevant version/effective date, and checksum for any downloaded official file.
- Quote only the minimum words needed to identify a field/code; otherwise paraphrase.
- Preserve a compact source manifest and only the relevant extracted official rows/definitions. Do not copy large unrelated registries or pages into the repository.
- Clearly separate official facts from Researcher inference.
- Cite repository path/line evidence for the current C1 table and consumers.

## Owned outputs

The Researcher may create only:

- `radar-design/B-US-UNIVERSE-AUTHORITY-1-RETURN.md`;
- `radar-design/artifacts/b-us-universe-authority-1/` containing a compact source manifest, relevant extracted official rows/definitions, and reproducible analysis notes.

Do not edit the B ledger, rulings, handoffs, roadmaps, product code, tests, migrations, or existing evidence artifacts.

## Prohibited actions

- No production host, SSH, database, `.env`, service, job, timer, or configuration access.
- No fresh `nasdaqlisted.txt` or `otherlisted.txt` universe-data fetch.
- No importer, mapping write, delisting, migration, or product/test code change.
- No provider, Alpaca asset, trading, account, order, or paid API call.
- No user-data or credential access.
- No commit, stage, push, clean, reset, discard, merge, deployment, or release-A action.
- No subagents.

## Acceptance criteria

The return is acceptable only if:

- every Q/G/S and N/A/P/Z/V code has an official-source disposition;
- every XNGS/XNMS/XNCM/XNYS/XASE/ARCX/BATS/IEXG MIC has an official ISO disposition;
- missing/new venue codes are explicitly assessed;
- XNAS normalization, BATS, and IEXG are explicitly ruled;
- any required C1 correction and its cohort impact are exact;
- official fact and inference are separated;
- all citations resolve directly to primary sources;
- no protected state changed.

## Stop condition

Stop after the authoritative definition package and recommendation are complete. If a required official source cannot be obtained, return the precise gap and do not substitute a secondary-source conclusion.

## Required final section — Mastermind return prompt

End with this completed block:

```text
You are Radar's Mastermind / Overview. Resume from repository evidence, not chat memory.

Assignment completed: B-US-UNIVERSE-AUTHORITY-1
Workspace: C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts
Branch: codex/radar-selected-price-charts
Observed HEAD / origin/main / feature ref: <exact hashes>
Observed index and worktree dirt: <exact summary and ownership caveats>

Read completely:
1. HANDOFF.md
2. radar-design/B-US-UNIVERSE-BRIEF.md
3. radar-design/B-US-UNIVERSE-LEDGER.md
4. radar-design/B-US-UNIVERSE-EVIDENCE-2-RULING.md
5. radar-design/B-US-UNIVERSE-AUTHORITY-1-RETURN.md
6. <authority source manifest and extracted-row artifact paths>

Authority result:
- Nasdaq Q/G/S: <result>
- Other-listed N/A/P/Z/V: <result>
- ISO MIC dispositions: <result>
- Missing/new listing venue codes: <result>
- XNAS normalization ruling: <result>
- BATS and IEXG ruling: <result>
- Required C1 corrections: <result>
- Impact on 114 safe candidates and seven drift rows: <result>
- Remaining authoritative gaps: <result>
- Recommended owner decisions D1/D2/D3/D8: <result>
- Smallest safe next assignment: <recommendation>

Release A remains CLOSED. Do not implement, mutate production, or dispatch another worker until the Mastermind reconciles this return into the B ledger and the owner approves the next step.
```


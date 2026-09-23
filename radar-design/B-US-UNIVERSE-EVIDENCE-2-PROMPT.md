# Assignment Prompt — `B-US-UNIVERSE-EVIDENCE-2`

You are Radar's Researcher. Return your result to the Mastermind.

## Assignment

- Stable ID: `B-US-UNIVERSE-EVIDENCE-2`
- Objective: complete the exact 146/51/87 cohort evidence by copying the four retained refresh files read-only, performing one bounded rollback-only production database capture, and running the accepted reconstruction tool locally. Do not implement or mutate anything.
- Workspace: `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts`
- Branch: `codex/radar-selected-price-charts`
- Expected `HEAD`, `origin/main`, and feature ref: `0fdad7327292cd3cd0b62dbe3f6b460873263053`
- Production repository: `/root/coc-stats`
- Retained source directory: `/root/radar-universe-refresh-20260916`

## Owner authorization

The owner explicitly authorizes only:

1. read-only access to the four retained files named below;
2. copying those four files to the local evidence directory with hashes;
3. one bounded production database capture consisting only of the approved `SELECT` queries inside one `READ ONLY` transaction with a 10-second statement limit and final `ROLLBACK`;
4. local offline execution of the accepted reconstruction tool.

This authorization does not include fresh directory downloads, importer execution, database writes, product implementation, service/configuration changes, commits, or deployment.

## Start gate

1. Verify workspace, branch, `HEAD`, `origin/main`, feature ref, index, and tracked/untracked dirt. Preserve every pre-existing modification.
2. Verify the production checkout path and read its `HEAD` without changing it. Expected production `HEAD` is `0fdad7327292cd3cd0b62dbe3f6b460873263053`; if it differs, stop before database access and report.
3. Verify all four retained paths exist as regular files. Do not change their ownership, permissions, timestamps, or contents.
4. If any gate differs, stop and return the discrepancy. Do not repair Git, production, or evidence state.

## Required reading

Read completely:

1. `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts\HANDOFF.md`
2. `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts\radar-design\B-US-UNIVERSE-BRIEF.md`
3. `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts\radar-design\B-US-UNIVERSE-LEDGER.md`
4. `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts\radar-design\B-US-UNIVERSE-EVIDENCE-1-RULING.md`
5. `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts\radar-design\B-US-UNIVERSE-EVIDENCE-1-RETURN.md`
6. `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts\radar-design\US-UNIVERSE-REFRESH-2026-09-16.md`
7. `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts\radar-design\WORKFLOW.md`
8. Every file in `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts\radar-design\artifacts\b-us-universe-evidence-1\`.

## Exact retained inputs

Read and copy only:

- `/root/radar-universe-refresh-20260916/nasdaqlisted.txt`
- `/root/radar-universe-refresh-20260916/otherlisted.txt`
- `/root/radar-universe-refresh-20260916/universe-before.json`
- `/root/radar-universe-refresh-20260916/preflight.json`

Copy them into a new local evidence directory under:

`C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts\radar-design\artifacts\b-us-universe-evidence-2\source\`

Record SHA-256 and byte size on the host before copying and locally afterward. Require equality. Never copy `.env`, credentials, database dumps, logs, or unrelated host files.

## Required sequence

### 1. Reconstruct the historical cohorts offline

Run the accepted `reconstruct_cohorts.py` locally against the copied source files and the current worktree, without `--current`, into a new output directory. It must reproduce every historical count and exit 0 before database access proceeds.

Extract the union of the added, changed, and absent symbols from its machine-readable output. Do not construct the list from chat text or samples.

### 2. Perform one bounded current-state capture

Use `current_state_select.sql` as the approved query specification. Because its `:cohort_symbols` marker is not standalone client syntax, use a small auditable runner that safely expands bound parameters for the exact reconstructed symbol list. Never interpolate symbols into SQL text.

Database rules:

- one connection as the existing application database user;
- read only the exact credential names required for that connection from `/root/coc-stats/.env`, in process memory only;
- never print, log, transmit, or persist credential values or the full connection string;
- select the `personal_apps` database explicitly;
- set `max_statement_time = 10`;
- start one `READ ONLY` transaction;
- execute only Q0–Q8 from the approved query specification, with cohort symbols safely bound;
- write only sanitized result data to the local Evidence‑2 directory;
- always issue `ROLLBACK`, including on failure;
- make no DDL, DML, lock, temp-table, stored-procedure, session-global, or configuration change.

The capture may contain public listing metadata, mapping metadata, and cohort-level quote/close counts and dates. It must not contain price values, user data, credentials, environment values, or unrelated rows beyond Q0–Q8.

Stop immediately if the connection cannot prove the transaction is read-only, a statement exceeds the limit, a query differs from the specification, or any write-like statement is requested.

### 3. Reconstruct with current state

Run `reconstruct_cohorts.py --current` locally into a second new output directory. Require exit 0 and exact reconciliation. Preserve both the historical-only and current-state outputs.

Validate:

- exactly 146 added-unmapped historical rows;
- exactly 51 changed historical rows;
- exactly 87 absent historical rows;
- every row has a classification and proposed disposition;
- historical facts and current drift are separate;
- all conflicts and ambiguous rows are retained, not normalized away;
- the real-data output contains no credentials or private environment values.

## Owned outputs

The Researcher may create only:

- `radar-design/B-US-UNIVERSE-EVIDENCE-2-RETURN.md`;
- `radar-design/artifacts/b-us-universe-evidence-2/` containing copied sources, hash manifest, sanitized current-state capture, the auditable capture runner, commands/results, and both reconstruction output sets.

Do not edit the B ledger, rulings, handoffs, roadmaps, product code, tests, migrations, or existing Evidence‑1 artifacts. Those remain Mastermind-owned or protected evidence.

## Prohibited actions

- No fresh Nasdaq Trader or other network fetch.
- No importer run, including `seed_radar_universe.py`.
- No database write, schema change, migration, temp table, mapping change, delisting, or repair.
- No service/job/timer/configuration/environment modification or restart.
- No product/test code edit.
- No provider, Alpaca asset, trading, account, or order call.
- No commit, stage, push, clean, reset, discard, merge, deployment, or release-A action.
- No subagents.

## Acceptance criteria

The return is acceptable only if:

- all start gates and hashes are recorded;
- source copies match host hashes exactly;
- the historical-only run exits 0 and reproduces 146/51/87;
- the database capture is demonstrably bounded, read-only, rolled back, and sanitized;
- the current-state run exits 0 and returns exact cohort tables;
- classification totals reconcile to each cohort size;
- current drift, mapping conflicts, legacy `XNAS` residue, and unresolved decisions are explicit;
- no protected state changed;
- the smallest next assignment is recommended without implementation.

## Stop condition

Stop after returning the evidence package. Any missing file, hash mismatch, ref drift, read-only proof failure, query failure, timeout, or reconciliation mismatch is a blocker; report it without broadening access or changing state.

## Required final section — Mastermind return prompt

End with this completed block:

```text
You are Radar's Mastermind / Overview. Resume from repository evidence, not chat memory.

Assignment completed: B-US-UNIVERSE-EVIDENCE-2
Workspace: C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts
Branch: codex/radar-selected-price-charts
Observed HEAD / origin/main / feature ref / production HEAD: <exact hashes>
Observed index and worktree dirt: <exact summary and ownership caveats>

Read completely:
1. HANDOFF.md
2. radar-design/B-US-UNIVERSE-BRIEF.md
3. radar-design/B-US-UNIVERSE-LEDGER.md
4. radar-design/B-US-UNIVERSE-EVIDENCE-1-RULING.md
5. radar-design/B-US-UNIVERSE-EVIDENCE-2-RETURN.md
6. <Evidence-2 manifest, capture report, reconciliation and exact cohort artifact paths>

Evidence result:
- Host source hashes: <result>
- Read-only/rollback proof: <result>
- Historical 146 cohort: <classification totals and artifact>
- Historical 51 cohort: <classification totals and artifact>
- Historical 87 cohort: <classification totals and artifact>
- Current-state drift: <exact result>
- Legacy XNAS residue: <exact result>
- Mapping conflicts/manual-review rows: <exact result>
- Remaining decisions and authoritative-definition carries: <list>
- Smallest safe next assignment: <recommendation>

Release A remains CLOSED. Do not rerun the importer, implement, mutate production, or dispatch another worker until the Mastermind reconciles this return into the B ledger and the owner approves the next step.
```


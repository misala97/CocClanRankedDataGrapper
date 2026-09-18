# Mastermind Ruling — `B-US-UNIVERSE-EVIDENCE-1`

Date: 2026-09-17  
Verdict: **REPOSITORY PORTION ACCEPTED; EXACT-COHORT GATE BLOCKED ON OWNER AUTHORIZATION**

## Accepted evidence

- Git continuity is verified at `0fdad7327292cd3cd0b62dbe3f6b460873263053` for `HEAD`, `origin/main`, and `origin/codex/radar-selected-price-charts`; branch is `codex/radar-selected-price-charts`; index is empty.
- The historical arithmetic reconciles without discrepancy: 12,658 incoming, 146 added, 12,512 matched, 51 changed within the matched set, 87 absent, 12,599 pre-import identities, 12,745 active after, and 12,599 mapped after.
- The repository trace is accepted as the planning basis: identity import does not maintain `RadarInstrument`; no active US mapping writer exists; mapping readers require mapped primary US instruments; absence has no production reconciliation caller; and the all-unmapped quote fallback can write default `XNAS` rows.
- The proposed C1–C13 mapping contract, B2 failure-safe maintenance design, schema assessment, test matrix, and B1/B2 split are accepted as research recommendations, not implementation authorization.
- `reconstruct_cohorts.py`, its schema/status artifacts, and `current_state_select.sql` are accepted as prepared evidence tooling. A fresh Mastermind run of the synthetic offline self-test returned `SELFTEST PASS`.

## Qualifications and open gate

- No real 146/51/87 row was reconstructed or classified. `cohort-status.json` correctly records `rows: null`.
- Current database drift and the possible legacy `XNAS` quote residue were not measured.
- The four retained host files and production database were not read; this was correct because the dispatch did not authorize them.
- Exchange-letter and ISO MIC meanings must be checked against authoritative current definitions before implementation.
- `current_state_select.sql` is query specification, not a directly runnable standalone client script: the future reader must safely expand/bind the cohort-symbol list and retain the read-only transaction, timeout, and rollback boundaries.
- The mapping contract and maintenance thresholds remain provisional until exact cohorts are returned and owner decisions D1–D8 are ruled.

## Assignment state

`B-US-UNIVERSE-EVIDENCE-1` is **PARTIAL / BLOCKED ON AUTHORIZATION**. Its repository deliverables are complete, but the brief's exit gate is not met because exact cohort rows, real classifications, and current drift are missing.

This is not a repeated research failure and does not authorize implementation. It is the expected result of the prompt's explicit access boundary.

## Safest next bounded assignment

If the owner authorizes it, prepare `B-US-UNIVERSE-EVIDENCE-2` for one Researcher with only:

1. read-only copying and hash verification of `/root/radar-universe-refresh-20260916/{nasdaqlisted.txt,otherlisted.txt,universe-before.json,preflight.json}`;
2. one bounded production database read in a `READ ONLY` transaction using the prepared query specification, a 10-second statement limit, safely bound cohort symbols, and `ROLLBACK`;
3. local offline execution of `reconstruct_cohorts.py --current` against the copied evidence;
4. return of the exact cohort tables, reconciliation, classifications, and current drift.

No fresh directory fetch, importer run, database write, migration, service/config change, product-code change, provider/trading call, commit, deployment, or release-A action belongs in Evidence‑2.

## Stop

Owner authorization was received after this ruling. `B-US-UNIVERSE-EVIDENCE-2-PROMPT.md` is now prepared under the exact read-only boundary above, but it is not dispatched. Release A remains closed.

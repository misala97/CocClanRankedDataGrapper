# Radar Workstream B — Authority Check Ruling

Status: **COMPLETE / ACCEPTED — OWNER POLICY DECISIONS RECORDED**  
Date: 2026-09-18  
Assignment: `B-US-UNIVERSE-AUTHORITY-1`

## Verdict

The authority return is accepted. The official-source gate is closed; no further Researcher assignment is needed before B1 planning.

Mastermind independently rechecked the current Nasdaq directory definitions and downloaded the current ISO 10383 CSV. The ISO file matched the return's recorded SHA-256 `79de0f7704e260bd49b0d2439f3084891cabc93481da8bdbaa716e15a27211ed` and 2,883-row count. All eight referenced MIC rows are US, ACTIVE, and have no expiry. The saved extracts also match their recorded hashes.

Git continuity is unchanged: workspace `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts`, branch `codex/radar-selected-price-charts`, and `HEAD`, `origin/main`, and `origin/codex/radar-selected-price-charts` all equal `0fdad7327292cd3cd0b62dbe3f6b460873263053`. The index is empty. There are nine pre-existing tracked documentation modifications, no tracked product-code modification, and 408 untracked files. All dirt is preserved.

## Binding authority result

- Nasdaq `Market Category` codes remain Q = Global Select, G = Global Market, and S = Capital Market.
- Nasdaq `otherlisted` exchange codes remain A = NYSE MKT/American, N = NYSE, P = NYSE Arca, Z = BATS/Cboe BZX, and V = IEX/IEXG.
- `XNGS`, `XNMS`, `XNCM`, `XNYS`, `XASE`, `ARCX`, `BATS`, and `IEXG` are confirmed. No code-to-MIC correction, removal, or addition is required.
- Keep Nasdaq segment MICs; do not normalize `XNGS`/`XNMS`/`XNCM` to operating MIC `XNAS`.
- Nothing changes the accepted cohort counts. The first safe insert-only set remains exactly 114 rows.
- The seven existing MIC-drift rows are policy cases, not invalid-MIC repairs: T1 Nasdaq tier moves (`EPRX`, `FSHP`, `FSHPR`, `FSHPU`), T2 same-operator NYSE-group move (`MVPA`), and T3 operator changes (`KHC`, `OPAD`).
- `IEXG` is missing from `analysis_contract.py`'s `KNOWN_US_MICS`; this is a confirmed fail-soft code inconsistency with zero current rows, not a current outage.
- The legacy `XXXX` and default-`XNAS` fallbacks are outside the confirmed listing-MIC contract. Their measured database extent remains zero.
- The seed parser's `Listing Exchange` alias is not documented by the checked Nasdaq definitions. B1 must either remove it or pin a separately verified contract; it must not remain an unexplained permissive alias.

## Qualification

The official registry establishes that `BATS` is ACTIVE with no expiry. The return's explanation that its older update stamp is merely group-wide maintenance lag is an inference, not an official statement, and is not made binding here. It does not alter the keep/confirmed ruling.

The statement that there is no ninth listing code is limited to Nasdaq's currently published allowed-value definitions. The B design must still quarantine any future unknown code and require a new authority check.

## Owner decisions — approved 2026-09-18

- **D1 — APPROVED.** Retain segment MICs; add `mic_type` and `operating_mic`; never rewrite a MIC in place; record T1 tier drift, review T2 continuity, and require explicit history treatment for T3 operator changes.
- **D2 — APPROVED.** Update identity text, but hold any baseline or mapping action for review rather than treating every first-token change as reassignment.
- **D3 — APPROVED.** Keep the 26 non-common listings discoverable as identities, but do not create price mappings yet for warrants, rights, units, preferreds, or notes.
- **D8 — APPROVED.** Include the narrow fix in B1 so unmapped/unknown identities are skipped or quarantined instead of receiving `XNAS`/`XXXX`.

The owner approved all four recommendations after a plain-language explanation. These decisions do not authorize implementation, prompt preparation, worker dispatch, a database write, a manual apply, scheduling, deployment, or production access.

## Next bounded gate

The next proposed action is owner authorization to prepare one B1 Implementer assignment: strict per-file parser/validator, dry-run reconciler, insert-only mapping support for the reviewed 114-row safe set, the D8 fallback correction, `IEXG` calendar recognition, and the parser-alias correction. B1 has no migration, scheduler, identity-upsert expansion, absence lifecycle, MIC rewrite, production apply, or deployment. No prompt is prepared or dispatched by this ruling.

Release A remains CLOSED and must not be reopened.

# Mastermind Ruling — `B-US-UNIVERSE-EVIDENCE-2`

Date: 2026-09-18  
Verdict: **ACCEPTED — EXACT COHORT EVIDENCE GATE COMPLETE**

## Accepted proof

- Local `HEAD`, `origin/main`, and `origin/codex/radar-selected-price-charts` remain `0fdad7327292cd3cd0b62dbe3f6b460873263053`; branch and empty index are correct.
- All four retained source copies match the host-reported SHA-256 and byte sizes exactly. Both directory files match the recorded network-body hashes with no BOM.
- Both reconstruction runs report every recorded and derived check passing. The current tables contain exactly 146, 51, and 87 rows; every row has a classification and disposition.
- Mastermind independently parsed the full 7.7 MB current-state capture, all 284 cohort symbols, both reconciliation files, and every CSV row. All 15 artifact hashes and all four source hashes match `hash-manifest.json`.
- The capture runner contains a literal statement set, safe bound expansion for all 284 symbols, a read-only statement guard, a 10-second session statement limit, one `START TRANSACTION READ ONLY`, and `ROLLBACK` in `finally`.
- The server accepted the read-only transaction and rollback. Engine-level `trx_is_read_only` inspection was unavailable with MariaDB error 1227 because the app user lacks `PROCESS`; this is an unavailable proof layer, not a claimed pass. The remaining evidence is sufficient for this bounded capture because no write-capable statement was reachable or issued.

## Binding evidence result

- **146 newly imported unmapped identities:** 114 safe insert-only mapping candidates, 26 non-common listings awaiting D3, and 6 ticker-change candidates requiring corporate-action review. All 146 remain active, have zero US instrument rows, zero mapped primaries, zero stored quote groups, and zero stored closes.
- **51 changed identities:** 31 first-token-change candidates, 11 likely renames, 4 Nasdaq tier drifts, 3 venue transfers, and 2 metadata-only changes. All remain active with exactly one mapped primary.
- **87 absent identities:** 65 unexplained, 16 likely expired derivatives, and 6 paired ticker-change candidates. All remain active/mapped and all have stored closes. No automatic delisting or unmapping is justified.
- **Current drift:** none at the 2026-09-17 21:55:45 UTC capture. There are 12,745 active identities, 12,599 mapped primaries, exactly 146 unmapped identities, zero multiple primaries, and zero US rows lacking a mapped primary.
- **Legacy default-MIC residue:** zero for the unmapped cohort and zero `XNAS`/`XXXX` instrument rows. F2 remains a latent code defect with measured current extent zero.
- **Mapped-data invariants:** no shared provider symbol and no non-USD US row. Seven existing mappings have directory/MIC drift: EPRX, FSHP, FSHPR, FSHPU, KHC, MVPA, and OPAD.
- **Reassignment heuristic:** 24 of 31 first-token changes are two sponsor-family rebrands; PMA is the strongest apparent genuine ticker reuse. Future breakers must not count raw changed rows as distinct reassignment events.
- **Time basis:** existing backfill `mapped_at` values were stamped in Europe/Berlin local time, while readers compare against naive UTC. A future writer must use explicit naive UTC and document the legacy inconsistency.
- D6 is discharged. Evidence‑1's exact-row blocker is closed.

## Qualifications

- The evidence establishes the state at the capture timestamp; it is not a permanent guarantee against later drift.
- The two missing grouped-close days were flagged but not diagnosed. They do not block this cohort gate and must not be described as a production failure without a schedule/current-state check.
- The 31-row `POSSIBLE_REASSIGNMENT` label is deliberately conservative and is not a finding that 31 symbols were reassigned.
- Exchange-letter meanings and ISO 10383 MICs remain repository-derived. They must be confirmed against current authoritative sources before implementation.
- The Researcher's phrase “offline Researcher” is corrected: current authoritative definitions require bounded external web research. The next assignment needs no production host or database access, but it is not offline.

## Assignment state

- `B-US-UNIVERSE-EVIDENCE-1`: **ACCEPTED / SUPERSEDED**.
- `B-US-UNIVERSE-EVIDENCE-2`: **COMPLETE / ACCEPTED**.
- Workstream B implementation: **NOT STARTED / NOT AUTHORIZED**.

## Safest next bounded assignment

Propose `B-US-UNIVERSE-AUTHORITY-1`, one Researcher using primary official sources only:

1. confirm Nasdaq Trader `Market Category` and `Exchange` code meanings;
2. confirm XNGS, XNMS, XNCM, XNYS, XASE, ARCX, BATS, and IEXG in the current ISO 10383 registry;
3. identify any newly supported US listing venue/code missing from C1;
4. return citations and any required C1 correction.

No production host, database, provider/account endpoint, importer, implementation, or mutation belongs in that assignment. The owner approved prompt preparation after this ruling; `B-US-UNIVERSE-AUTHORITY-1-PROMPT.md` is ready but not dispatched.

After authoritative confirmation, the owner must rule D1, D2, D3, and D8 before any B1 implementation plan. Release A remains closed.

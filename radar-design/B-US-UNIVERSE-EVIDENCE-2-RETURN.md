# B-US-UNIVERSE-EVIDENCE-2 — Researcher return

Date: 2026-09-17 · Role: Researcher (Claude Opus 5, no subagents) · Status: **COMPLETE — exact cohorts reconstructed, current state captured, everything reconciles**

## 0. Result in one paragraph

All four retained files copied with hashes equal to the host. The accepted
reconstruction tool reproduced **every** recorded and derived count and exited 0
before any database access: 5,600 + 7,058 usable rows, 12,658 unique incoming,
**146 added / 51 changed / 87 absent**, 0 reassigned, 0 flagged, 0 revived, 0
cross-file overlap, 12,599 before rows, and both file hashes `exact`. One bounded
`READ ONLY` capture then ran 14 statements in 2.618 s, ended in `ROLLBACK`, and
produced a sanitized export. The `--current` run also exited 0 with identical
cohorts. **There is no drift.** The database today holds 12,745 active
identities, 0 delisted, 12,599 mapped US primaries — and the 146 symbols with no
mapping are *exactly* the reconstructed added set, verified set-for-set. Every
row has a classification and a disposition, and the totals reconcile to 146 / 51
/ 87. Three things the real data settled that the repository could not:
**the legacy `XNAS` residue is zero**; **the mapping gap is total** (none of the
146 has a single stored close); and **the `POSSIBLE_REASSIGNMENT` rule
over-fires badly** — 24 of its 31 hits are two sponsor rebrands, while the one row
that looks like a genuine ticker reuse by a different issuer sits in the same
undifferentiated bucket.

## 1. Start gates

| Gate | Observed | Verdict |
|---|---|---|
| Workspace | `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts` | pass |
| Branch | `codex/radar-selected-price-charts` | pass |
| `HEAD` / `origin/main` / `codex/radar-selected-price-charts` | `0fdad7327292cd3cd0b62dbe3f6b460873263053` (all three) | pass |
| Index | empty (`git diff --cached --name-only` returns nothing) | pass |
| Worktree dirt at start | 9 modified tracked continuity files + 27 untracked entries (36 lines) | preserved, untouched |
| Production checkout `/root/coc-stats` | `git rev-parse HEAD` = `0fdad7327292cd3cd0b62dbe3f6b460873263053` | pass, matches expected |
| Four retained paths | all four present as regular files, mode 644 `root:root`, mtime 2026-09-16 00:52 | pass |

The 9 modified tracked files (`HANDOFF.md`; `radar-design/`
`A-US-USD-ONLY-LEDGER`, `ASSIGNMENTS`, `HANDOFF`, `MARKET-DATA-ROADMAP`,
`MASTERMIND-STATE`, `MD-SELECTED-PRICE-LEDGER`, `ROADMAP`, `WORKFLOW` `.md`) are
Mastermind-owned and were not read-modified by me. Production's own untracked
dirt (`personal_apps/nasdaqlisted.txt`, `otherlisted.txt`, `reports/`, `venv/`,
`scratchpad/arctic_backfill_resume.json`) was left alone; I did **not** read
those two production working-copy directory files, because the dispatch names
only the four retained ones.

## 2. Source copies and hashes

Host hashes were taken before copying, local hashes after. `hash-manifest.json`
records both and reports `source_copies_match_host: true`.

| File | SHA-256 (host = local) | Bytes |
|---|---|---|
| `nasdaqlisted.txt` | `bd5524e05ab8530c482882df7f9eb109b9a9f96cf73dd67872ee911251262ddd` | 348,098 |
| `otherlisted.txt` | `861023735ffebda2ede5059070f622d8ba2fb54175e78e5d73275b2701bd9b96` | 541,154 |
| `universe-before.json` | `7875922b0d00bc88f3f8547eeaf80a978cf3d8be75702f895df7f87a79d56c99` | 4,256,261 |
| `preflight.json` | `c4d6c8a5306659bd47bf8bc6b6a134ac47e822145d8a189b6198358055080c08` | 1,105 |

Nothing else was copied. No `.env`, credential, dump, log or unrelated host file
was read or transferred. Host ownership, permissions, timestamps and contents are
unchanged.

**The BOM question from Evidence‑1 is now closed.** Both directory files hash
`exact` against the recorded network-body SHA-256 and `bom_present` is `false`,
so Nasdaq sent no BOM and the preflight's re-encoding changed nothing. The
`matches_after_restoring_stripped_bom` branch was never needed.

`universe-before.json` and `preflight.json` are not mentioned in the recorded
import note's hash list; their hashes above are first recorded here.

## 3. Historical-only reconstruction — exit 0, every count reproduced

Artifacts: `radar-design/artifacts/b-us-universe-evidence-2/reconstruct-historical/`.

| Check | Basis | Expected | Measured | ok |
|---|---|---|---|---|
| `nasdaq_usable_rows` | recorded | 5,600 | 5,600 | yes |
| `other_usable_rows` | recorded | 7,058 | 7,058 | yes |
| `unique_incoming` | recorded | 12,658 | 12,658 | yes |
| `added` | recorded | 146 | 146 | yes |
| `updated` | recorded | 51 | 51 | yes |
| `absent` | recorded | 87 | 87 | yes |
| `reassigned` | recorded | 0 | 0 | yes |
| `flagged` | recorded | 0 | 0 | yes |
| `nasdaq_sha256` / `other_sha256` | recorded | as above | as above, state `exact` | yes |
| `creation_time` | recorded | `0915202618:01` | `0915202618:01` | yes |
| `before_rows` | derived | 12,599 | 12,599 | yes |
| `before_delisted_rows` | derived | 0 | 0 | yes |
| `revived` | derived | 0 | 0 | yes |
| `cross_file_overlap` | derived | 0 | 0 | yes |

`all_recorded_counts_reproduced: true`, exit **0**.

File facts measured for the first time: `nasdaqlisted.txt` has 5,608 data rows, 8
Test Issues, 0 symbol-form rejections; `otherlisted.txt` has 7,629 data rows, 30
Test Issues and **541 symbol-form rejections** (dotted and space-bearing NYSE-family
forms such as class shares, warrants and preferreds). That 541 is the concrete
size of finding F10's exclusion.

Independent corroboration: all 30 symbols in `preflight.json → add_sample` are in
the reconstructed 146. The three cohorts are pairwise disjoint (0 overlap in each
pair); their union is 284 symbols, written to `cohort-symbols.json` and used as
the bound parameter list.

## 4. Bounded current-state capture

Full detail in `artifacts/b-us-universe-evidence-2/capture-report.md`; the runner
is `capture_current_state.py`, the sanitized output is `current-state.json`
(sha256 `c5d9f7d7c78ef6704f0d8ede2faeb580b731ba7bf6dba34234e0d196c0c67357`,
7,702,510 bytes, byte-identical to the file produced on the host).

- One connection, app user, `personal_apps` selected and re-verified inside the
  transaction, MariaDB `10.11.14-MariaDB-0ubuntu0.24.04.1`.
- `DB_USER`, `DB_PASS`, `DB_HOST`, `PERSONAL_DB_NAME` read by name from
  `/root/coc-stats/.env` in process memory. Never printed, logged or persisted;
  the output text is scanned for the password value before it is written.
- `SET SESSION max_statement_time = 10`, read back as `10.0` inside (it was
  `0.0` before).
- `START TRANSACTION READ ONLY` accepted; `@@in_transaction` 0 → 1.
- Exactly Q0–Q8 from the approved specification. Q5 and Q7 ran with 284 `%s`
  placeholders and 284 bound parameters; **no symbol was ever interpolated into
  SQL text**. Symbols were validated `^[A-Z]{1,5}$`, deduplicated and capped.
- 14 statements, 2.618 s total, slowest 2.042 s (Q7) against the 10 s limit. One
  attempt, no timeout, no error, no retry.
- `ROLLBACK` in a `finally` block; `rolled_back: true`.
- Every statement must pass an allowlist (`SELECT `, `SET SESSION
  max_statement_time = `, `START TRANSACTION READ ONLY`, `ROLLBACK`) plus a
  forbidden-token check, so no DDL, DML, lock, temp table, procedure, global
  variable or configuration change is reachable from this process.

**One proof layer was unavailable and I am not claiming it.**
`information_schema.innodb_trx` returned MariaDB error **1227** (the application
user has no `PROCESS` privilege), so `trx_is_read_only` could not be read; the
output records `"innodb_trx": "unavailable: 1227"`. A row saying *read-write*
would have aborted the run. What stands is: the server accepted `START
TRANSACTION READ ONLY`, reported exactly one open transaction, the statement set
is provably read-only by construction and fully logged, and the transaction was
rolled back. I did not issue a write-like statement to probe the boundary,
because the dispatch forbids requesting one.

`current-state.json` holds only Q0–Q8 columns: public listing metadata, mapping
metadata, cohort-level quote/close **counts and dates**, grouped-day counters and
the invariant checks. No price value, no user data, no credential, no environment
value, no row outside the specification.

## 5. Current-state reconstruction and reconciliation — exit 0

Artifacts: `.../reconstruct-current/`. Exit **0**, `checks_ok: true`, and the two
runs' cohort symbol lists are identical (`runs_agree_on_cohort_symbols: true`).
Historical facts and current drift stay in separate columns: `current_*` and
`mic_drift` are populated only in the `--current` run, and the historical-only
run's rows carry `current_active = NOT_AUTHORIZED`.

### 5.1 Cohort 146 — added, unmapped

`reconstruct-current/cohort-146-added-unmapped.csv` · 146 rows, totals reconcile.

| Classification | Rows | Proposed disposition |
|---|---|---|
| `SAFE_AUTO_MAP_CANDIDATE` | **114** | `INSERT_US_PRIMARY_AFTER_APPLY_TIME_RECHECK` |
| `NON_COMMON_LISTING` | **26** | `OWNER_DECISION_D3` |
| `POSSIBLE_TICKER_CHANGE` | **6** | `MANUAL_REVIEW_CORPORATE_ACTION` |
| total | **146** | |

Current state for all 146: active `true`, `current_us_rows` **0**,
`current_primary_mapped` **0**, `mic_drift` false, `conflicts` empty. The recorded
"unmapped" status is exactly true today, with no contradiction and no conflict.

- Sources: 78 from `otherlisted`, 68 from `nasdaqlisted`. ETF flag Y 86 / N 60.
- Proposed MIC over all 146: ARCX 40, XNMS 44, BATS 28, XNCM 22, XNYS 6, XASE 4,
  XNGS 2. Every row resolved to one of the eight codes, so `VENUE_UNKNOWN` is 0
  and the C1 table covered the whole cohort.
- The 114 safe candidates are 81 ETFs and 33 non-ETFs across ARCX 36, BATS 28,
  XNMS 26, XNCM 15, XNYS 5, XASE 4.
- The 26 non-common rows: 11 warrants, 5 units, 4 rights, 4 notes, 2 preferreds —
  all Nasdaq five-letter forms corroborated by the name, or note/preferred by
  name. `SECURITY_TYPE_UNCLEAR` and `ETF_FLAG_MISSING` are both 0.

### 5.2 Cohort 51 — changed

`reconstruct-current/cohort-51-changed.csv` · 51 rows, totals reconcile.

| Classification | Rows | Proposed disposition |
|---|---|---|
| `POSSIBLE_REASSIGNMENT` | **31** | `MANUAL_REVIEW_BASELINE_INTEGRITY` |
| `RENAME_LIKELY` | **11** | `NO_MAPPING_ACTION_AUDIT_ONLY` |
| `NASDAQ_TIER_DRIFT` | **4** | `HOLD_MIC_UNCHANGED_OWNER_DECISION_D1` |
| `VENUE_TRANSFER` | **3** | `MANUAL_REVIEW_OWNER_DECISION_D1` |
| `IDENTITY_METADATA_ONLY` | **2** | `NO_MAPPING_ACTION` |
| total | **51** | |

Change shape: 44 name-only, 7 exchange-code changes (4 Nasdaq tier, 3
cross-venue). Name kinds: 31 first-token changed, 11 same first token, 2
security-description, 2 cosmetic, 5 none (exchange-only). No ETF flag changed.
All 51 are active with exactly one US row and one mapped primary. Two carry the
`legacy_fallback_quotes_present` conflict (see §6.2). Every current name and
exchange equals the 2026-09-16 directory value, so the identity half of the
import did land and stayed.

**The 7 MIC drifts, in full** — every one is an instance of finding F3, because
`mic` is part of `uq_radar_quote_market` and `uq_radar_daily_close_market` and
every reader filters on it:

| Symbol | Code before → after | Stored MIC | Directory implies | Kind |
|---|---|---|---|---|
| EPRX | S → Q | XNCM | XNGS | Nasdaq tier |
| FSHP | G → S | XNMS | XNCM | Nasdaq tier |
| FSHPR | G → S | XNMS | XNCM | Nasdaq tier |
| FSHPU | G → S | XNMS | XNCM | Nasdaq tier |
| KHC | Q → N | XNGS | XNYS | cross-venue (Nasdaq → NYSE) |
| MVPA | P → N | ARCX | XNYS | cross-venue (NYSE Arca → NYSE) |
| OPAD | N → S | XNYS | XNCM | cross-venue (NYSE → Nasdaq Capital Market) |

I re-derived this independently over **all** 12,599 mapped rows against the
current directory code, not only the cohort: the mismatch count is exactly 7 and
the tickers are exactly those above. There is no older, unrelated MIC residue.

### 5.3 Cohort 87 — absent

`reconstruct-current/cohort-87-absent.csv` · 87 rows, totals reconcile.

| Classification | Rows | Proposed disposition |
|---|---|---|
| `ABSENT_UNEXPLAINED` | **65** | `OBSERVE_ABSENCE_NO_ACTION` |
| `ABSENT_DERIVATIVE_LIKELY_EXPIRED` | **16** | `OBSERVE_ABSENCE_NO_ACTION` |
| `POSSIBLE_TICKER_CHANGE` | **6** | `MANUAL_REVIEW_CORPORATE_ACTION_NO_DELIST` |
| total | **87** | |

All 87 are still active, still hold exactly one mapped US primary, and their
names and exchange codes are byte-identical to the pre-import export — the
importer touched nothing, as recorded. Every row therefore carries the
`mapped_while_absent` conflict (86 rows; 1 row also carries
`legacy_fallback_quotes_present`), which is the intended fail-closed state, not a
defect. Prior exchange codes: G 33, S 23, P 12, A 5, N 5, Q 5, Z 4. 29 were ETFs,
53 were not, 5 had a null flag.

**Absence is not death, and the data says so loudly.** Every one of the 87 has
stored daily closes, and the newest close per symbol falls out as: 26 in
September 2026, 59 in August 2026, 2 older. The single latest is **2026-09-11** —
four days before the directory file was created (2026-09-15 18:01). Twenty-eight
(symbol, source) rows show a close on or after 2026-09-01, including RFDI, RFEM,
MUSI and EASG on 2026-09-11. Nothing here supports automatic delisting from one
snapshot; **B-R3 is confirmed by measurement, not only by policy.**

## 6. Current drift, `XNAS` residue, conflicts

### 6.1 Drift: none

| Quantity | 2026-09-16 record | 2026-09-17 21:55:45 UTC measurement |
|---|---|---|
| Universe rows | 12,745 | 12,745 |
| Active | 12,745 | 12,745 |
| Delisted | 0 (derived) | **0** |
| Mapped US primaries | 12,599 | **12,599** |
| Symbols with a US row but no mapped primary | — | **0** |
| Symbols with more than one mapped primary | — | **0** |
| Unmapped active | 146 | **146** |

Three set-level checks computed offline from the capture close this:

- reconstructed 146 **==** the set of active symbols with no mapped US primary
  today (no symbol on either side only);
- active-now minus the pre-import export **==** the reconstructed 146;
- every pre-import symbol is still active, and every mapped instrument ticker is
  in the active universe (no orphan mapping).

`Q1.first_seen_since_import` returned **0**, which is a calendar artifact, not a
contradiction: the import ran 2026-09-16 00:52 CEST = 2026-09-15 22:52 UTC and
`first_seen` is stamped in naive UTC, so the new rows sort *before* the
`'2026-09-16'` boundary the query used. The set comparison above is the reliable
statement.

### 6.2 Legacy `XNAS` residue: zero

Q5 found **3** quote rows groups for cohort symbols since 2026-09-16, and none is
`XNAS`:

| Ticker | Cohort | MIC | Source | n | Window |
|---|---|---|---|---|---|
| ATAI | absent_87 | XNMS | finnhub | 34 | 2026-09-16 08:08 → 19:28 |
| HYSA | changed_51 | ARCX | finnhub | 47 | 2026-09-16 19:38 → 2026-09-17 21:44 |
| NXT | changed_51 | XNGS | finnhub | 38 | 2026-09-16 16:08 → 2026-09-17 15:44 |

All three are ordinary polls of **mapped** symbols under their real MICs. None of
the 146 unmapped symbols has a single quote row in the window, so finding **F2's
fallback path did not fire**. Independently, Q8's MIC census over all 12,599 US
instrument rows returns only `mapped:ARCX 2707`, `mapped:XNMS 2478`, `mapped:XNYS
2412`, `mapped:XNCM 1667`, `mapped:BATS 1610`, `mapped:XNGS 1448`, `mapped:XASE
277` — sum 12,599, **no `XNAS`, no `XXXX`, no `unverified`, no IEXG**. The
`legacy_fallback_quotes_present` flag on HYSA, NXT and ATAI is the tool being
conservative about Q5's breadth; it is not evidence of the F2 defect. F2 remains
a live latent risk (the code path is unchanged), with a measured present extent
of **0 rows**.

### 6.3 Contract invariants and mapping conflicts

Q8 returned **no** `provider_symbol_shared` row and **no** `us_row_not_usd` row.
Combined with Q2, the proposed contract already holds in the data today:

| Invariant | Result |
|---|---|
| One mapped US primary per active ticker (C5) | holds — 0 multiples, 0 US-row-without-primary |
| Provider symbol unique among mapped US primaries (C6) | holds — 0 shared |
| `market='us'` ⇒ `currency='USD'` (C4) | holds — all 12,599 USD, all `isin` NULL |
| Status vocabulary | all 12,599 `mapped`; no other status exists |
| `mapping_source` | all 12,599 `nasdaq-directory` (the single backfill) |
| `is_primary` | all 12,599 = 1 |
| `history_due_at` | all 12,599 NULL |

Manual-review rows across the three cohorts: **6 + 6** ticker-change candidates
(one pairing, see below), **31** baseline-integrity rows, **3** venue transfers,
**4** tier drifts held, **26** rows awaiting D3, and **87** absence observations.
Nothing is normalized away; all conflicts are retained in the `conflicts` column.

## 7. What the real rows changed about the Evidence‑1 picture

These are new, measured findings. They refine the accepted contract; none of them
is implementation.

**N1 (high value) — the 6+6 ticker-change pairs are real and exact.** Every
pairing is a name-identical corporate action:

| Absent | Added | Issuer |
|---|---|---|
| JAB, JABRR, JABRU, JABRW | ATLQ, ATLQR, ATLQU, ATLQW | JAB Acquisition Corp I — shares / rights / units / warrants |
| MAPP | MATR | Harbor Multi-Asset Explorer ETF |
| VLLU | AELV | Harbor AlphaEdge Large Cap Value ETF |

The issuer-key pairing worked as designed, including the fund exception (no
false iShares/ProShares pairing appeared anywhere). Note what this implies for
absence policy: the four JAB rows are absent **because the ticker changed**, and
their old mappings would keep collecting nothing while the four new symbols have
no mapping at all. A ticker change presents as one absence plus one addition and
must be reviewed as a pair — never as an independent delisting.

**N2 (high) — `POSSIBLE_REASSIGNMENT` over-fires on sponsor rebrands.** 31 of
the 51 hit the first-token rule, but 24 are two family-wide rebrands:
**22** `NYLI … → NYLIM …` funds and **2** `Credit Suisse … → UBS Asset Management
…` funds (CIK, DHY). Only 7 are issuer-level changes worth a human: ASBP and
ASBPW (Aspire Biopharma → Aspire-Lakewood), MBAI (Check-Cap Ltd → MBody AI Ltd),
**PMA (Ming Shing Group Holdings Limited → PMA Graphene Technology Group Inc. —
Class A Ordinary Shares)**, SVRN (OceanPal Inc → SVRN, Inc.), XPON (Expion360 →
Expion Energy), ZONE (CleanCore Solutions → Zone Frontier). **PMA is the one that
looks like a genuine reuse of a symbol by a different issuer**, which is exactly
the F4 hole: production never reaches `_is_reassignment`, so PMA's `first_seen`,
baseline and mapping were kept silently. Two consequences for a later plan: the
classifier needs a sponsor-family suppressor (a first-token change shared by
many symbols on one day is a rebrand, not N reassignments), and the proposed
breaker "first-token changes > 10" would have tripped on this ordinary import —
it must count *distinct new first tokens*, not rows, or it will cry wolf.

**N3 (medium-high) — `mapped_at` is stored in Berlin local time, not UTC.** All
12,599 rows carry `mapped_at` in the single hour `2026-08-30 16:xx`, and Q0 shows
both `@@session.time_zone` and `@@global.time_zone` are **`Europe/Berlin`**
(`captured_utc` 21:55:45 vs `session_now` 23:55:45). The backfill used
`CURRENT_TIMESTAMP`, so its values are local, two hours ahead of the naive-UTC
clock that `analysis.py` and the chart compare against. This is finding F8 made
concrete: a new writer that stamps `CURRENT_TIMESTAMP` would create rows that are
ineligible for up to two hours (`mapped_at > read_start`), while one that stamps
naive UTC (C7) would be correct but inconsistent with every existing row. C7
should be kept **and** the discrepancy recorded, since it means `mapped_at` is
not a single comparable basis across old and new rows.

**N4 (medium) — the mapping gap is total, not partial.** Q7 found stored daily
closes for all 87 absent and all 51 changed symbols, and for **0 of the 146**.
The new identities have no price data of any kind — not a stale line, not one
close. Any UI that shows them will show nothing until a mapping exists.

**N5 (medium) — the 87 keep depressing grouped coverage (F9).** Because all 87
are active and mapped, they stay in the grouped identity map and the acceptance
denominator. Q6's last 14 accepted Massive days show `unmatched_universe` running
544–693 (621 on 2026-09-15) and `unmatched_provider` 468–609, against ~12,500
provider rows. The 87 are a visible slice of that, and B2's absence aging should
be expected to move these counters.

**N6 (informational, unresolved) — no grouped close day exists yet for
2026-09-16 or 2026-09-17.** The newest accepted `massive_grouped` row is
**2026-09-15**; the gaps below it (09-05/06, 09-07, 09-12/13) are the weekend and
Labor Day. Whether the two missing sessions are the normal end-of-day lag (the
capture ran 21:55 UTC, minutes before a typical post-close cycle) or a real gap
was **not** measured — Q6 is summary-only in this specification and the job
schedule was not inspected. Flagged, not concluded.

**N7 (informational) — the parser's exclusion is quantified.** `otherlisted.txt`
rejected 541 rows on symbol form (dotted/space-bearing NYSE-family class shares,
warrants, rights and preferreds) against 0 in `nasdaqlisted.txt`, plus 8 + 30
Test Issues. That is the measured size of F10.

## 8. Remaining decisions and carries

Unchanged and still owner-owned: **D1** (MIC policy — now with 7 concrete rows, 4
tier and 3 cross-venue), **D2** (first-token changes — now with N2's rebrand
problem attached), **D3** (26 non-common listings), **D4** (absence thresholds —
now with N1's ticker-change pairs and the 2026-09-11 close as evidence for
conservatism), **D5** (scheduler home), **D7** (provider presence), **D8** (the F2
one-liner; extent measured at 0 rows today, mechanism unchanged). **D6 is
discharged** by this return.

Carries that are still open:

1. **Authoritative definitions.** The exchange-letter meanings and ISO 10383 MICs
   still come from repository code (migration `a4c8e2f19b70`), not from Nasdaq
   Trader's definitions page or the ISO registry. No network fetch was authorized
   or made. This must be confirmed before implementation. The data adds one
   observation: code `V` (IEXG) has **zero** rows, so that mapping is untested in
   practice.
2. **Read-only engine proof.** `innodb_trx` needs `PROCESS`; the app user lacks
   it. If a future bounded read must prove read-only at engine level, that
   privilege (or a separate read-only account) has to be arranged first.
3. **Two directory files sit untracked in the production working copy**
   (`/root/coc-stats/personal_apps/{nasdaqlisted,otherlisted}.txt`). Their vintage
   is unknown; they were not read. A daily maintenance design should not depend
   on them.
4. **`mapped_at` basis** (N3) needs an explicit ruling alongside C7.
5. **N6**, the two missing grouped days, needs a one-line check by whoever next
   touches the ingest schedule.

## 9. Actions taken and protected state

Actions: read repository, Git and the four retained host files; copied those four
files; created `/root/b-us-universe-evidence-2` (mode 700) on the host, ran the
capture runner there once, copied the result down, and **removed the directory**,
so no evidence-2 data or script persists on the host; ran the accepted tool twice
locally; wrote this return and
`radar-design/artifacts/b-us-universe-evidence-2/`.

Not done, at all: no fresh Nasdaq Trader or other network fetch; no importer run;
no database write, schema change, migration, temp table, mapping change,
delisting or repair; no service, job, timer, configuration or environment change
or restart; no product or test edit; no provider, Alpaca asset, trading, account
or order call; no commit, stage, push, clean, reset, discard, merge, deployment
or release-A action; no subagents.

Protected state verified afterwards: `/root/radar-universe-refresh-20260916`
unchanged (same four files, same sizes, same 2026-09-16 00:52 timestamps);
production `HEAD` still `0fdad73`; local `HEAD`/`origin/main`/feature ref still
`0fdad73`; index still empty; the 9 modified tracked files and all pre-existing
untracked paths untouched; the five Evidence‑1 artifacts unmodified. The only
addition to the worktree is one untracked directory,
`radar-design/artifacts/b-us-universe-evidence-2/`, plus this return.

## 10. Smallest safe next assignment (recommendation, not implementation)

**One Researcher, offline, no host or database access: confirm the C1 exchange
code table against authoritative current definitions** — Nasdaq Trader's
symbol-directory definitions page for the `Market Category` and `Exchange`
letters, and the ISO 10383 registry for XNGS / XNMS / XNCM / XNYS / XASE / ARCX /
BATS / IEXG, including whether any new US listing venue has appeared. That is
carry 1, it is the only remaining input the mapping contract needs before a plan,
it touches nothing, and it is small.

Then, and only after the owner rules D1, D2, D3 and D8, the B1 slice already
recommended in Evidence‑1 (strict parser/validator, dry-run reconciler,
insert-only US primary mapper for the reviewed safe set, the F2 fix; no
migration, no scheduler). This return sizes B1's first apply precisely: **114
rows**, all resolving to six known MICs, none conflicting with anything in the
database today.

## 11. Artifact index

| Path | What |
|---|---|
| `radar-design/artifacts/b-us-universe-evidence-2/source/` | the four retained files, hashes equal to host |
| `…/hash-manifest.json` | host vs local hashes, run agreement, hashes of every artifact |
| `…/cohort-symbols.json` | added / changed / absent lists and the 284-symbol union bound in Q5 and Q7 |
| `…/capture_current_state.py` | the auditable capture runner |
| `…/capture-report.md` | boundary, read-only proof, statement log, sanitization |
| `…/current-state.json` | the sanitized capture (Q0–Q8) |
| `…/commands.md` | every command and its result |
| `…/reconstruct-historical/` | historical-only run: 3 CSVs, `cohorts.json`, `reconciliation.json` |
| `…/reconstruct-current/` | `--current` run: the same five files with current state and drift |

## 12. Mastermind return prompt

```text
You are Radar's Mastermind / Overview. Resume from repository evidence, not chat memory.

Assignment completed: B-US-UNIVERSE-EVIDENCE-2
Workspace: C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts
Branch: codex/radar-selected-price-charts
Observed HEAD / origin/main / feature ref / production HEAD: 0fdad7327292cd3cd0b62dbe3f6b460873263053 / 0fdad7327292cd3cd0b62dbe3f6b460873263053 / 0fdad7327292cd3cd0b62dbe3f6b460873263053 / 0fdad7327292cd3cd0b62dbe3f6b460873263053 (/root/coc-stats, read only)
Observed index and worktree dirt: index empty. 9 modified tracked Mastermind-owned continuity files (HANDOFF.md; radar-design/A-US-USD-ONLY-LEDGER, ASSIGNMENTS, HANDOFF, MARKET-DATA-ROADMAP, MASTERMIND-STATE, MD-SELECTED-PRICE-LEDGER, ROADMAP, WORKFLOW .md) plus 27 pre-existing untracked entries, all untouched. Researcher added only untracked radar-design/B-US-UNIVERSE-EVIDENCE-2-RETURN.md and radar-design/artifacts/b-us-universe-evidence-2/. Nothing staged, committed or pushed; the B ledger, rulings, handoffs and Evidence-1 artifacts were NOT edited (Mastermind-owned / protected).

Read completely:
1. HANDOFF.md
2. radar-design/B-US-UNIVERSE-BRIEF.md
3. radar-design/B-US-UNIVERSE-LEDGER.md
4. radar-design/B-US-UNIVERSE-EVIDENCE-1-RULING.md
5. radar-design/B-US-UNIVERSE-EVIDENCE-2-RETURN.md
6. radar-design/artifacts/b-us-universe-evidence-2/hash-manifest.json, capture-report.md, commands.md, cohort-symbols.json, current-state.json, reconstruct-historical/reconciliation.json, reconstruct-current/reconciliation.json, reconstruct-current/cohort-146-added-unmapped.csv, reconstruct-current/cohort-51-changed.csv, reconstruct-current/cohort-87-absent.csv

Evidence result:
- Host source hashes: all four retained files copied read-only; local SHA-256 and byte size equal the host values exactly (nasdaqlisted.txt bd5524e0… 348098; otherlisted.txt 86102373… 541154; universe-before.json 7875922b… 4256261; preflight.json c4d6c8a5… 1105). hash-manifest.json reports source_copies_match_host: true. Both directory files hash `exact` with bom_present=false, so the Evidence-1 BOM question is closed. Host ownership/permissions/timestamps/contents unchanged.
- Read-only/rollback proof: one connection as the app user on MariaDB 10.11.14; personal_apps selected and re-verified inside the transaction; SET SESSION max_statement_time=10 read back as 10.0; START TRANSACTION READ ONLY accepted with @@in_transaction 0 -> 1; exactly Q0-Q8 plus 3 read-only control probes; Q5/Q7 bound 284 symbols as parameters with zero SQL interpolation; 14 statements in 2.618 s, slowest 2.042 s, no timeout or error; ROLLBACK in a finally block (rolled_back: true); a statement allowlist makes any write unreachable. NOT proved: information_schema.innodb_trx returned error 1227 (app user lacks PROCESS), so trx_is_read_only could not be read; recorded honestly as "unavailable: 1227", not claimed as passed. No write-like statement was issued to probe the boundary.
- Historical 146 cohort: reconstructed exactly, exit 0, every recorded and derived count reproduced (5,600/7,058 usable, 12,658 incoming, 146/51/87, 0 reassigned/flagged/revived/overlap, 12,599 before rows, both hashes exact, creation time 0915202618:01). Classification 114 SAFE_AUTO_MAP_CANDIDATE / 26 NON_COMMON_LISTING (D3) / 6 POSSIBLE_TICKER_CHANGE = 146. All 146 active, 0 US rows, 0 mapped primaries, no conflicts. Proposed MICs ARCX 40, XNMS 44, BATS 28, XNCM 22, XNYS 6, XASE 4, XNGS 2; VENUE_UNKNOWN 0. Artifact reconstruct-current/cohort-146-added-unmapped.csv.
- Historical 51 cohort: 31 POSSIBLE_REASSIGNMENT / 11 RENAME_LIKELY / 4 NASDAQ_TIER_DRIFT / 3 VENUE_TRANSFER / 2 IDENTITY_METADATA_ONLY = 51. All active with exactly one mapped US primary; current name and exchange equal the directory value. Artifact reconstruct-current/cohort-51-changed.csv.
- Historical 87 cohort: 65 ABSENT_UNEXPLAINED / 16 ABSENT_DERIVATIVE_LIKELY_EXPIRED / 6 POSSIBLE_TICKER_CHANGE = 87, every disposition observe-only with no delist. All 87 still active, still mapped, identity byte-identical to the pre-import export. All 87 have stored closes; newest per symbol: 26 in September 2026, 59 in August 2026, 2 older; the latest is 2026-09-11, four days before the 2026-09-15 18:01 file. B-R3 is now measured, not only policy. Artifact reconstruct-current/cohort-87-absent.csv.
- Current-state drift: NONE. Capture at 2026-09-17 21:55:45.660080 UTC: 12,745 universe rows, 12,745 active, 0 delisted, 12,599 mapped US primaries, 0 multiple primaries, 0 US-row-without-primary, 146 unmapped. Set checks: reconstructed 146 == currently unmapped set exactly; active-now minus pre-import export == the 146; every pre-import symbol still active; no orphan mapping. Q1.first_seen_since_import = 0 is a calendar artifact (import 2026-09-15 22:52 UTC), not a contradiction.
- Legacy XNAS residue: ZERO. Q5 returned 3 quote groups for cohort symbols since the import (ATAI/XNMS, HYSA/ARCX, NXT/XNGS, all finnhub, all mapped symbols under real MICs); none of the 146 unmapped symbols has any quote row, so the F2 fallback did not fire. Q8's MIC census over all 12,599 US rows shows only ARCX 2707, XNMS 2478, XNYS 2412, XNCM 1667, BATS 1610, XNGS 1448, XASE 277 — no XNAS, no XXXX, no unverified, no IEXG. F2 stays a latent code risk with present extent 0.
- Mapping conflicts/manual-review rows: Q8 found 0 shared provider symbols and 0 non-USD US rows; all 12,599 rows are mapped/USD/is_primary=1/isin NULL/mapping_source nasdaq-directory/history_due_at NULL, so C4, C5 and C6 already hold. MIC drift is exactly 7 rows, verified over the whole mapped universe, not just the cohort: EPRX S->Q (XNCM vs XNGS), FSHP/FSHPR/FSHPU G->S (XNMS vs XNCM), KHC Q->N (XNGS vs XNYS), MVPA P->N (ARCX vs XNYS), OPAD N->S (XNYS vs XNCM). Manual review: 6+6 ticker-change rows in one exact pairing (JAB/JABRR/JABRU/JABRW -> ATLQ/ATLQR/ATLQU/ATLQW, MAPP -> MATR, VLLU -> AELV), 31 baseline-integrity rows, 3 venue transfers, 4 held tier drifts, 26 D3 rows, 87 absence observations. All conflicts retained, nothing normalized away. The real-data output contains no credential or private environment value.
- Remaining decisions and authoritative-definition carries: D1 (MIC policy, now with the 7 concrete rows), D2 (first-token changes — NEW EVIDENCE: 24 of the 31 POSSIBLE_REASSIGNMENT hits are two sponsor rebrands, 22x NYLI->NYLIM and 2x Credit Suisse->UBS; only 7 are issuer-level, and PMA "Ming Shing Group Holdings Limited" -> "PMA Graphene Technology Group Inc. - Class A Ordinary Shares" looks like a genuine different-issuer reuse that F4 let through silently. The proposed breaker "first-token changes > 10" would have tripped on this ordinary import and must count distinct new first tokens, not rows), D3 (26 rows), D4 (absence thresholds, with the 2026-09-11 close and the JAB pairing as evidence for conservatism), D5, D7, D8 (measured extent 0, mechanism unchanged). D6 is discharged. NEW: mapped_at is stored in Berlin local time — all 12,599 rows are 2026-08-30 16:xx and both session and global time_zone are Europe/Berlin, so CURRENT_TIMESTAMP is +2h from the naive-UTC clock the readers compare against (finding F8 made concrete; C7 needs an explicit ruling). NEW: none of the 146 has any stored close, so the price gap is total. NEW: the 87 remain in the grouped acceptance denominator; Q6's 14 accepted Massive days show unmatched_universe 544-693 and unmatched_provider 468-609. FLAGGED, NOT CONCLUDED: no grouped close day row exists yet for 2026-09-16 or 2026-09-17 (newest accepted is 2026-09-15); normal end-of-day lag versus a real gap was not measured. OPEN CARRIES: exchange-letter and ISO 10383 meanings are still repository-derived and unconfirmed against authoritative current sources (no network fetch was authorized), code V/IEXG has zero rows in practice, information_schema.innodb_trx needs PROCESS which the app user lacks, and two untracked directory files of unknown vintage sit in the production working copy at /root/coc-stats/personal_apps/ (not read).
- Smallest safe next assignment: one offline Researcher, no host or database access, to confirm the C1 exchange-code table and the eight MICs against Nasdaq Trader's current symbol-directory definitions and the ISO 10383 registry, including any new US listing venue. That is the only remaining input the mapping contract needs. Only after that, and after the owner rules D1/D2/D3/D8, the B1 slice already recommended in Evidence-1 — whose first apply this return sizes exactly at 114 insert-only rows across six known MICs, none conflicting with current data.

Release A remains CLOSED. Do not rerun the importer, implement, mutate production, or dispatch another worker until the Mastermind reconciles this return into the B ledger and the owner approves the next step.
```

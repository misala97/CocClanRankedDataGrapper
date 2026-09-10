# PERF1 benchmark artifacts

Carried here on 2026-09-10 because Codex's PERF1 ruling found that the Git
delta did not contain the scripts the ledger cited. They existed only in an
ephemeral per-session scratchpad under `%TEMP%\claude\...`, which is not a
reachable artifact. This directory is the reachable copy. **Nothing here is
application code and nothing here is imported by the app.**

Every claim in `PERF1-LEDGER.md` that has a script behind it names that script
below. Claims with no script are called out in the ledger's own
"CORRECTION — two claims that had no artifact" section.

## Prerequisites, all of them

| | |
| --- | --- |
| Working directory | `personal_apps/` inside a worktree of this repo |
| Interpreter | the repo's Python 3.12 with the app's requirements importable |
| Database | **`personal_apps_radar_perf1`** on local MySQL 8.0.46, named by `PERSONAL_DB_NAME` in that worktree's `.env` |
| Fixture size | 9,272,064 `radar_bucket_sources` rows across six partitions — built by `gen_perf1.py` |
| Buffer pool | **`innodb_buffer_pool_size = 2560M`**, matching the target. At the 128 MB default every timing is disk-bound and every ratio is an artifact. Each script prints the pool it found; check that line before trusting a number. |
| Engine caveat | the target is **MariaDB 10.11.14**. Plan-shaped findings must be confirmed against the target's own `EXPLAIN`. Absolute seconds do not transfer. |
| Invocation | `python <path-to-this-dir>/<script>.py` from `personal_apps/` |

`sf_tests.py` is the exception: it is a pytest module, run as
`python -m pytest <path>/sf_tests.py`, and it exercises the in-process
single-flight that PERF2 replaces. It is kept as the record of what was tested,
not as a suite to maintain.

## What each one is

| Script | What it produces | Ledger section |
| --- | --- | --- |
| `gen_perf1.py` | **Builds the fixture** to the target's measured cardinalities. Run this first; everything else assumes it. | "THE MEASUREMENT — full board build at production scale" |
| `perf_probe.py` | Read-only structural profile of one board build: statement count, cumulative and worst statement, rows, Python time. | "Measured locally: the SHAPE of the work" |
| `local_shape.py` | The same profile broken down per stage of `board.build`. | same |
| `candidates.py` | The three candidate indexes measured against each other on the real aggregate shape, median of 5. | "The candidates, real query shape, pool matched" |
| `index_trial.py` | Earlier candidate comparison; superseded by `candidates.py`, kept because the retraction cites it. Accepts `--baseline-only`. | "RETRACTION — the first P1 evidence was wrong" |
| `end_to_end.py` | Before/after on the whole build plus the first (wrong) write-cost probe. | "The whole board, before and after" |
| `write_cost.py` | The write cost **re-measured on the write ingest actually performs** — one bulk `UPDATE` of an indexed column across 16,793 existing rows, restored afterwards. This is the +50%. | "CORRECTION — the write cost was measured on the wrong write" |
| `acceptance.py` | The P2 acceptance run: 20 serial samples per window, two simultaneous readers, rapid filter changes, payload-parity hashes, index size before/after `ANALYZE`. **Its own write probe is the one that measured the wrong write**; use `write_cost.py` for that number. | "P1 AND P2 — the corrected evidence" |
| `endpoint_pair.py` | Two readers through the endpoint's cache path, five pairs per window — the rows the ledger now labels "threaded workers only". | same |
| `explain_check.py` | Every `radar_bucket_sources` read's plan, captured from the running code through a `before_cursor_execute` listener, then `EXPLAIN`ed with its own parameters. | "Every plan, captured from the running code" |
| `mutate.py` | Puts each single-flight defect back and checks the test named for it actually fails. | "Every test is now mutation-checked" |
| `sf_tests.py` | The single-flight tests as they stood at `691f33a`. | "SECOND REVIEW" |
| `srclist.txt`, `tickers.txt` | The fixture's own source names and ticker list. The source list matters: an earlier run used config's real names against a fixture holding placeholders and aggregated 41% of the rows. | "RETRACTION" §3 |
| `ledger_p1p2.md`, `ledger_r2.md`, `ledger_worker.md` | Drafts of ledger sections, kept only to show the numbers were not retyped by hand. | — |

## What these scripts write

`acceptance.py`, `candidates.py`, `index_trial.py`, `end_to_end.py` and
`write_cost.py` **create and drop indexes** on `personal_apps_radar_perf1` and
`write_cost.py` updates rows in it and restores them. They are safe on the
disposable fixture and must never be pointed at anything else. `DB` is a
module-level constant in each; there is no environment variable that can
redirect them, deliberately.

None of them can reach the target. Nothing here opens an ssh connection.

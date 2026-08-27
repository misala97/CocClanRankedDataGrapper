# SDD ledger - plan: docs/superpowers/plans/2026-08-26-radar-pipeline-audit-fix.md

Spec: docs/superpowers/specs/2026-08-26-radar-pipeline-audit-design.md
Original branch: dev_personal
Continuation branch/worktree: codex/radar-pipeline-audit
Original base commit: 1470424
Continuation base commit: ee44f0d

Task order at continuation: 3b review, 3c, 4, 5, 6, 7, 9, 8, 10, 11,
12, 13, 14, 15, 16, 17, 18, 19.

Task 1: complete (commit 4f4cdf9, review clean) - mention journal table and
  48-hour retention constant; migration c489b7c94875.

Task 2: complete (commits fb622c8 + b9aeb0a, review clean) - roll_up rebuilds
  from the journal; promotion sees the whole quarter-hour. Mutation tests pin
  failed-source exclusion and frozen extractor confidence.
  Deploy carry: the journal is empty at deploy; a partial deployment bucket
  must not be rebuilt as if the journal covered its whole window.

Task 3: complete (commits 86175de + 4575fe0, review clean) - rows leaving
  status ok lose expected, variance, mention_z, and baseline_days. Task 6 must
  clear the 399 historical stale-score rows.

Task 3b: implementation commit ee44f0d; independent review was interrupted
  before a verdict. Continuation starts by completing that review.

Task 3b: review NOT APPROVED - Important: promoted=True is sticky although
  promotion is revocable. One voucher plus four lows promotes; adding a fifth
  low exceeds MAX_BARE_PER_VOUCHER and must revoke the entire group. The brief
  itself mandated the one-way write, so this is a plan defect rather than an
  implementer deviation. Fix round 1/5 pending.

Task 3b fix round 1: implemented in commit f3413b4. `mark_promoted` now
  replaces every recomputed low/medium verdict; the cap-plus-one regression
  proves prior promotions, voice count and bucket count are revoked together.
  Focused test 1/1 and covering tests 66/66 passed. Full radar gate reached
  585 passed and two unrelated template failures caused by the absent ignored
  Vite manifest; local npm build is unavailable because `tsc` is not installed.
  Independent re-review APPROVED: no Critical or Important findings. Minor
  self-referential report SHA wording corrected in the following docs commit.
  Task 3b complete.

Ruling: Task 3b promotion persistence replaces every recomputed bare verdict,
  writing False for current lows and True for current mediums - the journal
  must reflect the same latest full-bucket decision that mention_count uses.
  Cost if wrong is extra UPDATE work per touched bucket; leaving it sticky can
  pass the eligibility floor on voices that are no longer scored.

Ruling: isolate continuation in codex/radar-pipeline-audit - the original
  checkout contains unrelated Telegram changes; cost if wrong is one merge
  step back to dev_personal, while working in place risks staging user work.

Ruling: add Task 3c before further extraction/source changes - corrected
  rollups are a new baseline generation even though extraction membership is
  unchanged. The current scorer also derives from the current version and
  writes onto older-version rows. Cost if wrong is an unnecessary warm-up;
  omitting it mixes known-understated history with corrected counts and defeats
  source_config_version's compatibility boundary.

Ruling: run Task 9 before Task 8 - Reddit's aggregate status is already known
  to be the wrong population. Score truncated rows only after each subreddit
  owns its status. Cost if wrong is sequencing only; the final schema and
  behavior are unchanged.

Ruling: replace Task 5's universal raw-source reachability test with targeted
  behavioral guards - the draft counted comments, docstrings and unused
  imports as call sites, so it could pass the exact dead-hook defect it claimed
  to prevent. PAGE_CAP gets a direct deletion regression; bot filtering,
  single-letter extraction, profile scheduling and sentiment scheduling keep
  their runtime tests. Cost if wrong is that a different future dead constant
  needs another targeted test; the rejected generic test offered false rather
  than broad protection.

Task 3c: architecture review NOT APPROVED - Critical: `roll_up` could stamp a
  corrected generation onto an existing row while preserving its old score,
  and scorer-only invalidation occurred after the daemon's immediate ingest
  path. Important: SQL NULL, startup ordering and bootstrap-evidence failure
  were not pinned strongly enough.

Ruling: Task 3c clears score fields both at startup and on the exact bucket row
  whenever its generation changes; profile version is required; scorer cleanup
  is limited to the active lookback; tests cover explicit old hashes and real
  SQL NULL. Startup aborts before fetchers/scheduler when retained legacy
  evidence exists but bootstrap recovers zero rows. Cost if wrong is a startup
  abort on a genuinely inconsistent migrated database; continuing would make
  missing evidence indistinguishable from zero and serve relabelled scores.

Task 3c: implementation commit 7791963. Covering suite 137/137 passed; broad
  radar gate 595 passed with the two known missing-Vite-manifest failures.
  Independent Claude review found production behavior compliant but review NOT
  APPROVED because eight test/efficiency findings remain. Fix round 1/5 is in
  progress from `task-3c-fix-round-1.md`.

Task 3c review findings: runtime fail-closed `main()` test can be fooled by
  swallowing prepare errors; mixed-generation row scoring is unpinned; four
  global-window tests collide with current dev seed data; startup commit,
  current-version argument, `high_confidence_count > 0`, and score-presence
  update guard are unpinned; scorer invalidation repeats an unscoped 30-day
  scan per source.

Ruling: fix all eight in one scoped round. Add an optional source argument to
  defensive score invalidation while leaving startup all-source; move only the
  Task 3c global-window fixtures to 2027-06-01. Cost if wrong is a slightly
  wider public helper signature and future-dated test data; leaving the gaps
  allows silent fail-open startup, phantom cross-generation spikes, flaky
  counts, or repeated range locks.

Ruling: Task 6 now includes automated dry-run/apply/idempotence/Decimal and
  stale-score tests plus a `ticker_prefix` test-only scope. Repair decisions
  compare every recoverable lower-bound field rather than assuming equal high
  count means an equal aggregate; stale cleanup detects any non-NULL score
  field. Cost if wrong is a slightly larger one-shot script API and one extra
  test file; the old draft could mutate the shared dev corpus during tests,
  skip refreshed secondary aggregates, or ship a production backfill proven
  only by printing `examined 0`.
  The draft's unused `_BUCKET` SQL constant is deleted from the plan rather
  than shipping another defined-but-uncalled promise in the audit that is
  explicitly removing those.

Task 3c: fix round 1/5 (8 original findings addressed, 1 new Important open;
  commit c553c47). New issue: `test_radar_scoring.rows` broadened teardown to
  every `ZZ%` ticker in the shared dev DB, so one suite can erase another
  test's or user's namespaced evidence. Fix round 2/5 pending: exact owned
  ticker set plus sentinel mutation regression.

Task 3c: fix round 2/5 NOT ADDRESSED (commit 4850c9a; 2 Important open).
  Exact cleanup still claims `SSNOPE`, which this file only queries and never
  creates, and the sentinel regression pre-deletes every existing
  `ZZSENTINEL` row. Fix round 3/5 must remove the query-only ticker and use a
  per-run unique <=12-character sentinel with no pre-delete, cleaning only its
  exact identity in `finally`.

Task 3c: fix round 3/5 (2 addressed, 0 open; commit fa66e70). Scoped
  re-review APPROVED: exact ownership excludes query-only `SSNOPE`; the
  collision-safe 12-character sentinel is never pre-deleted and cleans only
  its own identity.

Task 3c: complete (commits 7791963..fa66e70, review clean). Final Task 3c
  covering gate: 141 passed. Latest broad gate: 598 passed with only the two
  established missing-Vite-manifest API template failures.

Task 4: complete (commit c6ff071, spec review approved; no Critical/Important).
  `single_letter_cashtags_allowed` is now a live extraction argument and the
  Bluesky-vs-finance behavior has red/mutation evidence.

Task 5: complete (commit c6ff071, spec review approved; no Critical/Important).
  Superseded `PAGE_CAP` and its dead comment are deleted; targeted deletion,
  bot-filter, profile-job and sentiment-job guards pass.

Task 4+5 minor (deferred to final review): `_extract_for` says there are four
  per-source judgements but its prose enumerates only three, omitting the
  single-letter-cashtag judgement.

Codex-to-Claude stop checkpoint (2026-08-26): Michi requested an immediate
  stop near the Codex session limit. Task 6 implementer Socrates was
  interrupted and shut down before producing any code, tests, report or
  commit; Task 6 remains not started. HEAD before the handoff-only commit is
  ee24d65. No active worker remains. Claude must begin with the hardened
  `task-6-brief.md`, preserve the completed/reviewed Tasks 1-5, and follow the
  remaining order 6, 7, 9, 8, 10-13, 14-17, 18-19, final review. The prepared
  ignored `task-7-brief.md` is included in the handoff checkpoint for later use.

Task 6: complete (commits d11ccb5..8b0a07d, review clean). One-shot backfill
  script plus its test file. Independent review APPROVED the implementation
  with one Important and two Minor findings; fix round 1 closed the Important
  and one Minor, and the scoped re-review returned zero findings at every
  severity. Focused gate 4/4 then 5/5; broad radar gate 605 passed with only
  the two established missing-Vite-manifest API template failures. The real
  dry-run path runs clean and reports 210 bucket rows examined, 165
  understated, against local dev data - so this is measured behaviour, not a
  script proven only by printing `examined 0`.

Task 6 deviation (accepted): equality of `distinct_text_ratio` and
  `engagement_weighted_count` uses `math.isclose`, not `==`. MySQL FLOAT is
  single-precision and round-trips lossily, which broke the brief's literal
  idempotency guarantee; reproduced independently by the reviewer.

Task 6 fix round 1: the stale-score query's `ticker_prefix` scoping passed
  only because this dev database currently holds zero real rows matching
  `status != 'ok' AND any-score-column-not-null` outside `ZZBF` - which is
  precisely the population the production run exists to clear, so the luck was
  temporary. A data-independent sentinel-prefix assertion now pins it, teeth
  confirmed under deletion of the filter. Separately, `_TRUTH`'s computed
  `bs` came back a Python `str` and the ORM lookup relied on implicit
  string-to-datetime coercion; production is MariaDB, so it is now parsed
  explicitly to a naive UTC datetime, guarded for drivers already returning
  one. Dry-run numbers unchanged across the type change.

Task 6 minor (deferred to final review): the `int()`-at-the-boundary comment
  claims COUNT returns Decimal, which is empirically true only of SUM on this
  driver. Left as-is because the same phrasing is an existing house
  convention (features/radar/journal.py:204); it misleads a reader but
  changes no behaviour.

Task 7: IMPLEMENTED, NOT REVIEWED (commit 945c9d7). StockTwits retired:
  module and its 11-test suite deleted, config/daemon/scheduler stripped, six
  test suites moved off the source name, and the UI source label removed from
  static/radar/src/format.ts with BoardPage.test.tsx updated to match.
  `source_config_version()` moved fc1a0ee4cab51d65 -> 8106787f1fa72179 with no
  manual edit, which is the intended bump and a deploy-time baseline warm-up.
  Broad gate 594 passed, 2 skipped, plus only the two established
  missing-Vite-manifest failures. Review package already generated at
  .superpowers/sdd/review-73981db..945c9d7.diff - do not regenerate it.

Task 7 review must go to the most capable model, not Sonnet. Michi's standing
  ruling is Sonnet for every review EXCEPT StockTwits and Reddit; Task 7 is
  StockTwits, and Tasks 9 and 8 are Reddit.

Task 7 scope expansions the review must check, none independently verified:
  three daemon tests DELETED rather than renamed because they called the
  now-deleted `_stocktwits_fetcher` and `SYMBOL_BUDGET_PER_CYCLE` - the claim
  that the missing-vs-ok distinction stays covered at run_cycle level needs a
  mutation, not a reading; three pre-existing config/ingest tests rewritten as
  monkeypatch extension-point tests because no surviving source sets
  BARE_TOKENS_ALLOWED, COIN_SYMBOLS_MEAN_STOCKS or SINGLE_LETTER_CASHTAGS
  True; about twelve prose restatements separating present-tense claims from
  historical measurements. `models.py:660` and the migration files were
  deliberately left - genuine historical column names, correct call.

Ruling: the standing "tsc is not installed, npm run build cannot run" note is
  now DISPROVED. A real npm install gives a clean tsc type-check and vitest
  78/78 including BoardPage.test.tsx. Tasks 11, 15 and 16 were planned around
  that command being unavailable and must be replanned with the runner
  available. Cost if wrong is one npm install; leaving the note stands three
  frontend tasks down on verification they can actually run.

Task 7 review: NEEDS FIXES (0 Critical, 2 Important, 1 Minor; teeth 4/6).
  Production retirement, source list, config-version bump, frontend removal,
  historical references and prose distinctions are compliant. Open Important
  findings: no surviving regression proves an empty healthy fetch remains
  `ok`; the ingest coin-symbol opt-in test calls config directly and does not
  pin ingest's consumer. Fix round 1/5 pending from
  `task-7-fix-round-1.md`.

Task 7 minor (deferred to final review): `test_stocktwits_is_retired` omits
  direct key absence from `COIN_SYMBOLS_MEAN_STOCKS`; adding a false-valued
  StockTwits key survives because `not any(values)` checks values, not keys.

Ruling: harden Task 9 before dispatch — the extracted draft would write a
  zero-valued aggregate `reddit` child beside concrete subreddit rows because
  `statuses` doubled as fetch summary and rollup population; it would discard
  successful earlier subreddits when a later sub made aggregate status
  `missing`; and daemon scoring would continue calling only the root name,
  matching no new rows. Concrete per-sub statuses alone feed rollup, partial
  successes survive, and one shared expansion drives API queries and scoring.
  Cost if wrong is a wider ingest/API change and more regression tests; leaving
  it makes the source split either pollute storage or produce unscored Reddit.

Ruling: Task 9 widens `RadarPost.source` as well as the two planned columns and
  chains its migration from current head `1d26ac48e744` — the post column is
  String(16), shorter than `reddit:wallstreetbets`, and Task 3b already added a
  migration after Task 1. Cost if wrong is one extra online table alter and a
  more explicit downgrade; leaving it makes the first mentioning Reddit post
  fail and/or forks Alembic history.

Ruling: Task 9 adds a dedicated source-name population generation to
  `source_config_version()` — Task 7 already left `SOURCES` at the same three
  roots and Task 9 leaves `REDDIT_SUBS` membership unchanged, so the promised
  bump otherwise does not happen. Cost if wrong is an unnecessary baseline
  warm-up; omitting it mixes aggregate-Reddit and per-subreddit populations.

Task 7: fix round 1/5 (2 addressed, 0 open; commit 3b74f32). Added a
  behavioral empty-healthy `run_cycle` regression and moved the coin-symbol
  opt-in assertion through `ingest._extract_for`; both targeted production
  mutations failed as required, then were restored. The same commit narrowed
  the ingest fixture's shared-DB cleanup from broad `ZZ%`/all-cursor deletion
  to exact owned rows and source keys. Covering gate: 59 passed.

Task 7: complete (commits 945c9d7..3b74f32, review clean). High-capability
  scoped re-review APPROVED both Important findings with no new findings at
  any severity. The one original Minor remains deferred to final review.

Task 9: WIP STOP CHECKPOINT, uncommitted at HEAD 88a2b50. Implementer Curie
  was interrupted safely for the Codex session limit, wrote
  `task-9-report.md`, confirmed no deliberate mutation remains, and was
  closed. Twelve tracked files plus untracked migration
  `08316d3e4d77_widen_radar_source_columns.py` belong to Task 9. The local
  shared MySQL DB is already at that uncommitted revision; Git/DB must not be
  separated by discarding the WIP.

Task 9 completed WIP evidence: source-root policies, shared expansion,
  concrete Reddit status/partial-success ingest, API expansion, concrete
  daemon scoring, three width changes, real config-version bump and root
  cursor/poll-state preservation are implemented. Focused green 15/15;
  covering files 147 passed plus exactly the two known manifest failures. Ten
  teeth mutations failed and were restored. Remaining: policy-helper teeth,
  final focused/broad gates, circular imports, migration rollback decision or
  controlled exercise, self-review, report completion, commit, independent
  high-capability Reddit review. Task 8 remains blocked behind this.

Ruling: harden Task 8's missing-status test into a behavioral row-level guard
  rather than asserting only `SCOREABLE_STATUSES` — a write loop can ignore a
  correct constant. Cost if wrong is one direct DB fixture; leaving it lets a
  missing observation gain a score with the suite green.

Ruling: Task 13 uses explicit membership before caching extraction, not
  `dict.setdefault(key, _extract_for(...))` — Python evaluates the default
  eagerly, so the draft still re-extracts duplicate IDs. Cost if wrong is a
  few lines and a call-count regression; leaving it ships the exact duplicate
  work the task claims to remove.

Task 9: complete (commits dedc90b..cc2d278, review clean). Per-subreddit
  source identity shipped with migration 08316d3e4d77 (three source columns
  widened to 48, chained from 1d26ac48e744). The first high-capability review
  was NOT APPROVED with 2 Critical, 2 Important and 6 Minor; fix round 1
  addressed all ten and the re-review APPROVED with zero new Critical or
  Important. Broad gate 617 passed plus only the two established
  missing-Vite-manifest failures; tsc clean; vitest green; single Alembic head.

Task 9 Critical 1 (fixed): a Reddit cycle with nothing due wrote a zero-count
  root `reddit` child row into every touched bucket, status `ok`, on what the
  code's own comment calls the common path. It also inflated
  RadarBucket.sources_ok. Absence rendered as zero, in the exact task meant to
  stop that.

Ruling: a not-due cycle records NOTHING for Reddit - not an `ok` zero and not
  `missing`. `missing` means we tried and failed; not-due means we never
  tried, so there is no observation to write. The review's suggested fix of
  emitting per-subreddit `ok` entries was overruled because it claims coverage
  for subs whose poll interval may not span the bucket. Implemented by making
  `per_source_status` distinguish None (no information, keep the old
  root fallback) from {} (explicitly nothing observed), tested with
  `is not None` rather than truthiness. Cost if wrong is a bucket missing a
  Reddit child it could have had; the alternative fabricates observations.

Task 9 Critical 2 (fixed): `expand_sources` dropped the root, so every
  pre-deploy root-`reddit` row would have vanished from the board and the
  detail charts - and worse, mixed selections still marked those hours
  measured from Bluesky/4chan while silently omitting Reddit's real stored
  contribution. On a 1Y detail span that is permanent, not a transition.

Ruling: split into strict `expand_sources` (concrete only) for scored reads
  and root-inclusive `expand_sources_for_history` for raw-count reads. Cost if
  wrong is two helpers a future reader might try to merge - documented at the
  definition to prevent exactly that; collapsing them loses either history or
  generation isolation.

Ruling: Task 9 changes the POPULATION, not the PRESENTATION. The detail panel
  keeps its single pooled `Reddit` venue row and user-facing labels are rooted;
  per-subreddit rows and `r/<sub>` labels are NOT introduced. Surfacing
  subreddits is a real product decision and must not ship as a side effect of
  a data-population task. Cost if wrong is a deferred feature; shipping it
  silently forecloses the choice.

Ruling: venues are counted by ROOT (Important 3 + Minor 9, one decision). Two
  subreddits share a platform, a user population and a rate-limit budget, so
  they are not the two independent venues the corroboration signal and its UI
  copy mean. Verified to reach the client, not stop at the server boundary.

Task 9 deferred Minors for the final branch review: N1 the downgrade's width
  guard fires after a DDL has already committed, which on MariaDB cannot be
  rolled back; N2 four of the five scored reads' strictness is untested, which
  weakens the Minor 10 closure argument; N3 broad `LIKE 'ZZ%'` teardowns
  across five test files (PRE-EXISTING, not introduced here) - the shared-DB
  hazard caught three times on this branch, still live; N4
  `board.excluded['one_venue']` is dead in production (pre-existing).

Task 8: complete (commit aee4e2f, independent high-capability review clean).
  Scoring writes scores for statuses exactly `ok` and `truncated`, while
  baseline and profile inputs remain `ok`-only. A persisted current-generation
  `missing` row retains NULL in all four score fields. Exact cleanup ownership
  was extended only for `ZZTRUNCATED` and `ZZMISSING`; no broad `LIKE` cleanup
  was introduced. Focused covering gate: 87 passed. Broad radar gate: 620
  passed, 2 skipped, plus only the two established missing-Vite-manifest API
  template failures. Independent Reddit review APPROVED with 0 Critical,
  0 Important, 0 Minor and teeth 2/2. Both required mutants were killed and
  restored byte-for-byte: the old `status != 'ok'` guard breaks truncated
  scoring, and bypassing the scoreable-status guard scores the real missing
  row and breaks its NULL assertions.

Task 8 ruling: truncated rows are eligible for score WRITES but never for
  baseline/profile INPUTS. Missing rows remain unscored even when they belong
  to the current source generation. Cost if wrong is either discarding most
  Reddit observations from ranking or contaminating expectations with known
  partial/missing measurements.

Continuation order after Task 8: batch Tasks 10-13 under one implementation
  worker and one Sonnet review, then Tasks 14-17, then Tasks 18-19, then final
  branch review. No Task 10 implementation has started at this checkpoint.

Tasks 10-13 implementation batch: COMPLETE BUT NOT REVIEWED (commits
  af11f2c..d5997c9; review base 4264036, head d5997c9). The single worker
  completed each task sequentially under TDD and wrote
  `task-10-13-report.md`; the exact four-commit review input is preserved in
  `task-10-13-review-package.md`. Stop checkpoint was requested before the
  required Sonnet review. No reviewer has been dispatched and no review
  verdict exists.

Task 10 commit af11f2c: empty parsed Reddit feeds return an unknown rate
  (`None`) and raised fetches record unknown catchup depth (`None`), without
  changing Task 9's not-due/no-observation behavior. Covering gate 66 passed.

Task 11 commit 8a23a26: unknown model rates return `None`; token/call facts
  remain recorded, `summary()` reports integer `unpriced_tokens`, and the API,
  TypeScript type and Spend UI surface the caveat using existing secondary
  styling. Backend/API focused gate 43 passed with 2 page tests deselected
  before the build; TypeScript, both frontend test groups (403 + 81), and both
  Vite builds passed.

Task 12 commit e4de0b5: intraday chart coverage is per slot across `ok` and
  `truncated` source rows, so interior unobserved gaps are NULL while measured
  quiet remains zero and `watched_from` remains the first covered slot.
  Covering gate 67 passed.

Task 13 commit d5997c9: breadth-filter removals increment
  `excluded['one_venue']`; leaderboard uses the named `VARIANCE_FLOOR`; ingest
  extracts once per external identity with explicit membership and computes
  the fresh-ID set once. The eager-`setdefault` mutant was killed by the
  duplicate-ID call-count regression and restored. Focused three-test gate and
  51-test covering gate passed.

Tasks 10-13 batch gate: `python -m pytest tests/ -k radar -q` from
  `personal_apps/` produced 633 passed, 646 deselected and 2 warnings, with no
  failures because Task 11's frontend build generated the ignored manifest.
  `git diff --check 4264036..d5997c9` is clean. Shared-DB cleanup added by the
  batch is exact-owned; the older five-file broad `LIKE 'ZZ%'` debt remains.

Immediate continuation: run ONE independent Sonnet review of the full
  `4264036..d5997c9` batch using the four task briefs, implementation report
  and review package. Reviewer writes `task-10-13-review.md` and returns only
  the prescribed verdict status line. Critical/Important findings require the
  SDD fix/re-review loop; Minors go to this ledger for final triage. Do not
  begin Tasks 14-17 until that review is approved.

Controller hardening prepared for later: Task 18 now requires behavioral
  daemon/refusal/override tests and two mutation teeth; a Windows helper
  printout alone is insufficient. Task 19's broad gate explicitly permits only
  the two established missing-manifest failures. These brief edits are
  controller-owned and preserved in the handoff commit.

Tasks 10-13 Sonnet review dispatch attempt: BLOCKED BEFORE START on
  2026-08-27. The explicit local Sonnet command exited 1 with `Failed to
  authenticate: OAuth session expired and could not be refreshed`.
  `claude auth status` reports `loggedIn: false`, `authMethod: none`, provider
  `firstParty`. No reviewer ran, `task-10-13-review.md` is absent, Git remains
  clean, and the fresh pre-review Radar baseline is 633 passed / 646
  deselected / 2 warnings / 0 failures. Ruling: do not substitute a GPT review
  because Michi explicitly bound Tasks 10-19 reviews to Sonnet. Cost if wrong
  is a pause for interactive Claude authentication; substituting would violate
  the review-model decision and create a verdict with the wrong authority.

Immediate continuation after authentication: rerun the one Sonnet review over
  exactly `4264036..d5997c9` using `task-10-brief.md` through
  `task-13-brief.md`, `task-10-13-report.md`, and
  `task-10-13-review-package.md`; write `task-10-13-review.md`; return only the
  prescribed verdict line. Do not begin Tasks 14-17 first.

Tasks 10-13: complete (commits 4264036..d5997c9, review clean). The
  absence-shaped batch: unknown rate/depth instead of a measured zero (10),
  unknown model pricing with visible unpriced tokens (11), honest interior
  intraday gaps (12), and breadth accounting with a named floor and
  extract-once (13). One Sonnet review over the exact four-commit range
  returned APPROVED with 0 Critical, 0 Important, teeth 9/9. Broad gate 633
  passed, 0 failures with the generated manifest present.

Note: the Sonnet review that the previous checkpoint recorded as BLOCKED was
  blocked only for Codex, whose local Claude CLI OAuth had expired. Dispatching
  a Sonnet subagent directly needs no CLI authentication, so the blocker did
  not apply and no `claude auth login` was required. Prefer the direct dispatch
  over shelling out to the CLI for any remaining review.

Tasks 10-13 deferred Minor: `features/radar/spend.py` `summary.unpriced`'s
  local `total` shadows the outer `summary.total` function name. Confirmed not
  a bug by mutation - closures resolve correctly - readability only.
